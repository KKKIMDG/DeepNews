import {
  AuthExpiredError,
  changePassword,
  deleteAccount,
  deleteHistory,
  deleteKeywordPreference,
  exportMyData,
  fetchHistory,
  fetchProfile,
  fetchRecommendations,
  login,
  logout,
  reportNews,
  requestBackendAnalysis,
  setKeywordPreference,
  setTopics,
  signup,
  updateSettings
} from "./api-client.js";
import { buildHighlightPayload } from "./keyword-analysis.js";
import {
  ACTIVE_TAB_STORAGE_KEY,
  ANALYSIS_STATUS,
  AUTH_STORAGE_KEY,
  DEFAULT_AUTH,
  DEFAULT_ANALYSIS,
  MESSAGE_TYPES,
  OVERLAY_NAMES,
  OVERLAY_STATE_STORAGE_KEY,
  STORAGE_KEY,
  TAB_ANALYSIS_KEY_PREFIX,
  TAB_OVERLAYS_KEY_PREFIX,
  expireStaleLoading
} from "../shared/constants.js";

// Tabs whose analysis request is running in this service worker instance.
const analysesInProgress = new Set();

// storage.session is emptied on browser restart and extension reload, so the local mirror must be reset too.
async function resetActiveTabMirror() {
  const stored = await chrome.storage.local.get(AUTH_STORAGE_KEY);
  await chrome.storage.local.set({
    [AUTH_STORAGE_KEY]: stored[AUTH_STORAGE_KEY] || DEFAULT_AUTH,
    [STORAGE_KEY]: DEFAULT_ANALYSIS,
    [OVERLAY_STATE_STORAGE_KEY]: {}
  });
}

chrome.runtime.onInstalled.addListener(() => {
  void resetActiveTabMirror();
});

chrome.runtime.onStartup.addListener(() => {
  void resetActiveTabMirror();
});

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab?.windowId) {
    return;
  }

  await chrome.sidePanel.open({ windowId: tab.windowId });
});

chrome.tabs.onActivated.addListener(({ tabId }) => {
  void syncActiveTab(tabId).catch(() => {});
});

chrome.windows.onFocusChanged.addListener((windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) return;
  void chrome.tabs
    .query({ active: true, windowId })
    .then(([tab]) => (tab?.id ? syncActiveTab(tab.id) : undefined))
    .catch(() => {});
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (!changeInfo.url) {
    return;
  }

  void handleTabUrlChange(tabId, changeInfo.url).catch(() => {});
});

chrome.tabs.onRemoved.addListener((tabId) => {
  analysesInProgress.delete(tabId);
  void chrome.storage.session
    .remove([tabAnalysisKey(tabId), tabOverlaysKey(tabId)])
    .catch(() => {});
});

const AUTH_REQUIRED_HANDLERS = {
  [MESSAGE_TYPES.GET_PROFILE]: fetchProfile,
  [MESSAGE_TYPES.SET_KEYWORD_PREFERENCE]: setKeywordPreference,
  [MESSAGE_TYPES.DELETE_KEYWORD_PREFERENCE]: deleteKeywordPreference,
  [MESSAGE_TYPES.UPDATE_SETTINGS]: updateSettings,
  [MESSAGE_TYPES.SET_TOPICS]: setTopics,
  [MESSAGE_TYPES.GET_HISTORY]: fetchHistory,
  [MESSAGE_TYPES.DELETE_HISTORY]: deleteHistory,
  [MESSAGE_TYPES.GET_FEED]: fetchRecommendations,
  [MESSAGE_TYPES.CHANGE_PASSWORD]: changePassword,
  [MESSAGE_TYPES.EXPORT_MY_DATA]: exportMyData
};

const EXTENSION_PAGE_HANDLERS = {
  [MESSAGE_TYPES.GET_LATEST_ANALYSIS]: handleGetLatestAnalysis,
  // The panel names the tab it is showing; make it the published one even if another window has focus.
  [MESSAGE_TYPES.ANALYZE_ACTIVE_TAB]: async (payload) => {
    if (Number.isInteger(payload.tabId)) await syncActiveTab(payload.tabId);
    return analyzeTab(payload.tabId);
  },
  [MESSAGE_TYPES.GET_AUTH_STATE]: getAuthState,
  [MESSAGE_TYPES.LOGIN]: handleLogin,
  [MESSAGE_TYPES.SIGNUP]: handleSignup,
  [MESSAGE_TYPES.LOGOUT]: handleLogout,
  [MESSAGE_TYPES.DELETE_ACCOUNT]: (payload) =>
    withAuth((token) => deleteAccount(token, payload.password || "")).then(() => clearAuth()),
  [MESSAGE_TYPES.REPORT_NEWS]: handleReportNews,
  [MESSAGE_TYPES.SET_OVERLAY_STATE]: (payload) => updateTabOverlays(payload.tabId, payload.state)
};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // The only message a page's content script may send: the user closed an overlay with its × button.
  if (message?.type === MESSAGE_TYPES.OVERLAY_CLOSED) {
    if (isOwnContentScript(sender) && OVERLAY_NAMES.includes(message.payload?.name)) {
      void updateTabOverlays(sender.tab.id, { [message.payload.name]: false }).catch(() => {});
    }
    return false;
  }

  if (!isExtensionPage(sender)) {
    return false;
  }

  const authHandler = AUTH_REQUIRED_HANDLERS[message?.type];
  const handler = authHandler
    ? (payload) => withAuth((token) => authHandler(token, payload))
    : EXTENSION_PAGE_HANDLERS[message?.type];
  if (!handler) {
    return false;
  }

  void Promise.resolve()
    .then(() => handler(message.payload || {}))
    .then((result) => sendResponse({ ok: true, result }))
    .catch((error) =>
      sendResponse({
        ok: false,
        error: error?.message || "요청에 실패했습니다.",
        authExpired: error instanceof AuthExpiredError
      })
    );

  return true;
});

// Content scripts report the web page's URL, so only our own pages (side panel, or the panel/privacy page
// opened in a tab) carry a chrome-extension:// URL here.
function isExtensionPage(sender) {
  return (
    sender?.id === chrome.runtime.id &&
    typeof sender.url === "string" &&
    sender.url.startsWith(chrome.runtime.getURL(""))
  );
}

function isOwnContentScript(sender) {
  return sender?.id === chrome.runtime.id && Number.isInteger(sender.tab?.id) && sender.frameId === 0;
}

function tabAnalysisKey(tabId) {
  return `${TAB_ANALYSIS_KEY_PREFIX}${tabId}`;
}

function tabOverlaysKey(tabId) {
  return `${TAB_OVERLAYS_KEY_PREFIX}${tabId}`;
}

async function getTabAnalysis(tabId) {
  const key = tabAnalysisKey(tabId);
  const analysis = (await chrome.storage.session.get(key))[key] || DEFAULT_ANALYSIS;
  return analysesInProgress.has(tabId) ? analysis : expireStaleLoading(analysis);
}

async function setTabAnalysis(tabId, analysis) {
  await chrome.storage.session.set({ [tabAnalysisKey(tabId)]: analysis });
  await publishTabState(tabId);
}

async function getTabOverlays(tabId) {
  const key = tabOverlaysKey(tabId);
  return (await chrome.storage.session.get(key))[key]?.open || {};
}

async function updateTabOverlays(tabId, patch = {}) {
  if (!Number.isInteger(tabId)) throw new Error("탭 정보를 찾을 수 없습니다.");
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab) throw new Error("탭 정보를 찾을 수 없습니다.");

  const key = tabOverlaysKey(tabId);
  const stored = (await chrome.storage.session.get(key))[key];
  const origin = originOf(tab.url);
  const open = stored?.origin === origin ? { ...stored.open } : {};
  for (const name of OVERLAY_NAMES) {
    if (typeof patch?.[name] === "boolean") open[name] = patch[name];
  }

  await chrome.storage.session.set({ [key]: { origin, open } });
  await publishTabState(tabId);
  return open;
}

async function getActiveTabId() {
  return (await chrome.storage.session.get(ACTIVE_TAB_STORAGE_KEY))[ACTIVE_TAB_STORAGE_KEY];
}

// Copies the active tab's state into storage.local, which the panel renders from.
async function publishTabState(tabId) {
  if ((await getActiveTabId()) !== tabId) return;
  const [analysis, openOverlays] = await Promise.all([getTabAnalysis(tabId), getTabOverlays(tabId)]);
  await chrome.storage.local.set({
    [STORAGE_KEY]: analysis,
    [OVERLAY_STATE_STORAGE_KEY]: openOverlays
  });
}

async function syncActiveTab(tabId) {
  await chrome.storage.session.set({ [ACTIVE_TAB_STORAGE_KEY]: tabId });
  await publishTabState(tabId);
}

async function handleGetLatestAnalysis(payload) {
  if (Number.isInteger(payload.tabId)) {
    await syncActiveTab(payload.tabId);
    return getTabAnalysis(payload.tabId);
  }
  return (await chrome.storage.local.get(STORAGE_KEY))[STORAGE_KEY] || DEFAULT_ANALYSIS;
}

async function handleTabUrlChange(tabId, url) {
  const analysisKey = tabAnalysisKey(tabId);
  const overlaysKey = tabOverlaysKey(tabId);
  const stored = await chrome.storage.session.get([analysisKey, overlaysKey]);
  const analysis = stored[analysisKey];
  const overlays = stored[overlaysKey];
  // Tabs this extension never touched have no state; ignore their navigation.
  if (!analysis && !overlays) return;

  const removals = [];
  if (analysis && withoutHash(analysis.article?.url) !== withoutHash(url)) removals.push(analysisKey);
  if (overlays && overlays.origin !== originOf(url)) removals.push(overlaysKey);
  if (!removals.length) return;

  await chrome.storage.session.remove(removals);
  await publishTabState(tabId);
  // Single-page sites change the URL without reloading, so the old overlays would stay on screen.
  await chrome.tabs.sendMessage(tabId, { type: MESSAGE_TYPES.HIDE_ALL_OVERLAYS }).catch(() => {});
}

async function analyzeTab(requestedTabId) {
  const auth = await getAuthState();
  if (!auth.token) throw new Error("로그인 후 분석해 주세요.");

  let tabId = requestedTabId;
  if (!Number.isInteger(tabId)) {
    const [activeTab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    tabId = activeTab?.id;
  }
  const tab = Number.isInteger(tabId) ? await chrome.tabs.get(tabId).catch(() => null) : null;
  if (!tab || !isSupportedArticleUrl(tab.url)) throw new Error("HTTP 또는 HTTPS 기사 페이지에서 실행해 주세요.");
  if (analysesInProgress.has(tabId)) throw new Error("이 탭의 기사를 이미 분석 중입니다. 잠시 기다려 주세요.");

  analysesInProgress.add(tabId);
  const runId = crypto.randomUUID();
  const startedAt = new Date().toISOString();
  let articleInfo = { url: tab.url, title: tab.title || "" };

  try {
    await setTabAnalysis(tabId, {
      ...DEFAULT_ANALYSIS,
      status: ANALYSIS_STATUS.LOADING,
      article: articleInfo,
      runId,
      startedAt,
      updatedAt: startedAt
    });
    await showLoadingOverlays(tabId);

    const article = await extractArticle(tabId);
    articleInfo = { url: article.url, title: article.title };
    const current = await chrome.tabs.get(tabId).catch(() => null);
    if (withoutHash(current?.url) !== withoutHash(article.url)) {
      throw new Error("페이지가 변경되었습니다. 다시 분석해 주세요.");
    }

    const backendResult = await requestBackendAnalysis(
      {
        url: article.url,
        title: article.title,
        content: article.content,
        publishedAt: article.publishedAt || ""
      },
      auth.token
    );

    if (!(await isCurrentRun(tabId, runId))) {
      throw new Error("분석하는 동안 페이지가 바뀌어 결과를 표시하지 않았습니다.");
    }

    const analysis = buildAnalysis(backendResult, articleInfo);
    await setTabAnalysis(tabId, analysis);
    await sendTabMessageWithContentScript(tabId, {
      type: "HIGHLIGHT_KEYWORDS",
      payload: { keywords: buildHighlightPayload(analysis.keywords) }
    });
    await restoreOpenOverlays(tabId, analysis);
    return analysis;
  } catch (error) {
    if (error instanceof AuthExpiredError) {
      await clearAuth();
    } else if (await isCurrentRun(tabId, runId)) {
      const now = new Date().toISOString();
      await setTabAnalysis(tabId, {
        ...DEFAULT_ANALYSIS,
        status: ANALYSIS_STATUS.ERROR,
        article: articleInfo,
        error: error?.message || "분석 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        updatedAt: now
      });
    }
    await hideLoadingOverlays(tabId);
    throw error;
  } finally {
    analysesInProgress.delete(tabId);
  }
}

async function extractArticle(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["src/vendor/readability/Readability.js", "src/content/content-script.js"]
  });
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    files: ["src/content/extract-article.js"]
  });
  const extracted = results[0]?.result;
  if (!extracted?.ok) throw new Error(extracted?.error || "기사 본문을 추출하지 못했습니다.");
  return extracted.article;
}

async function isCurrentRun(tabId, runId) {
  const key = tabAnalysisKey(tabId);
  return (await chrome.storage.session.get(key))[key]?.runId === runId;
}

function buildAnalysis(result, articleInfo) {
  const score = Number(result?.adLikelihood?.score);
  return {
    ...DEFAULT_ANALYSIS,
    status: ANALYSIS_STATUS.READY,
    article: articleInfo,
    keywords: normalizeKeywords(result?.keywords),
    summary: typeof result?.summary === "string" ? result.summary : "",
    recommendations: Array.isArray(result?.recommendations) ? result.recommendations : [],
    adLikelihood: {
      label: String(result?.adLikelihood?.label || ""),
      score: Number.isFinite(score) ? score : -1
    },
    newsId: Number.isInteger(result?.newsId) ? result.newsId : null,
    cached: Boolean(result?.cached),
    contentOrigin: typeof result?.contentOrigin === "string" ? result.contentOrigin : "",
    sharedFromOther: Boolean(result?.sharedFromOther),
    reportCount: Number.isFinite(Number(result?.reportCount)) ? Number(result.reportCount) : 0,
    reportedByMe: Boolean(result?.reportedByMe),
    updatedAt: new Date().toISOString()
  };
}

async function handleReportNews(payload) {
  const newsId = Number(payload.newsId);
  if (!Number.isInteger(newsId) || newsId <= 0) throw new Error("신고할 기사 정보를 찾을 수 없습니다.");
  const reason = String(payload.reason || "").trim().slice(0, 300);
  const result = await withAuth((token) => reportNews(token, { newsId, reason }));

  const all = await chrome.storage.session.get(null);
  for (const [key, analysis] of Object.entries(all)) {
    if (!key.startsWith(TAB_ANALYSIS_KEY_PREFIX) || analysis?.newsId !== newsId) continue;
    const tabId = Number(key.slice(TAB_ANALYSIS_KEY_PREFIX.length));
    await setTabAnalysis(tabId, {
      ...analysis,
      reportCount: Number(result?.reportCount) || analysis.reportCount,
      reportedByMe: true,
      reanalysis: Boolean(result?.reanalysis)
    });
  }
  return result;
}

async function restoreOpenOverlays(tabId, analysis) {
  const openOverlays = await getTabOverlays(tabId);

  const messages = [];
  if (openOverlays.keywords && analysis.keywords.length) {
    messages.push({
      type: MESSAGE_TYPES.SHOW_KEYWORDS,
      payload: { keywords: analysis.keywords }
    });
  }

  if (openOverlays.keywordChart && analysis.keywords.length) {
    messages.push({
      type: MESSAGE_TYPES.SHOW_KEYWORD_CHART,
      payload: { keywords: analysis.keywords }
    });
  }

  if (openOverlays.summary && analysis.summary) {
    messages.push({
      type: MESSAGE_TYPES.SHOW_SUMMARY,
      payload: { summary: analysis.summary }
    });
  }

  if (openOverlays.recommendations && analysis.recommendations?.length) {
    messages.push({
      type: MESSAGE_TYPES.SHOW_RECOMMENDATIONS,
      payload: { recommendations: analysis.recommendations }
    });
  }

  if (openOverlays.adLikelihood && analysis.adLikelihood) {
    messages.push({
      type: MESSAGE_TYPES.SHOW_AD_LIKELIHOOD,
      payload: { adLikelihood: analysis.adLikelihood }
    });
  }

  for (const message of messages) {
    await sendTabMessageWithContentScript(tabId, message);
  }

  // Overlays without data for this article (e.g. no recommendations) would otherwise keep spinning.
  await hideLoadingOverlays(tabId);
}

async function showLoadingOverlays(tabId) {
  const openOverlays = await getTabOverlays(tabId);

  if (!Object.values(openOverlays).some(Boolean)) {
    return;
  }

  await sendTabMessageWithContentScript(tabId, {
    type: MESSAGE_TYPES.SHOW_LOADING_OVERLAYS,
    payload: {
      openOverlays
    }
  });
}

async function hideLoadingOverlays(tabId) {
  await chrome.tabs.sendMessage(tabId, { type: MESSAGE_TYPES.HIDE_LOADING_OVERLAYS }).catch(() => {});
}

async function sendTabMessageWithContentScript(tabId, message) {
  try {
    await chrome.tabs.sendMessage(tabId, message);
    return;
  } catch {
    // Try to recover when the tab was opened before this extension version loaded.
  }

  try {
    await chrome.scripting.executeScript({
      target: {
        tabId
      },
      files: ["src/content/content-script.js"]
    });
    await chrome.tabs.sendMessage(tabId, message);
  } catch {
    // The tab can disappear or become non-injectable while navigating.
  }
}

async function handleLogin(payload = {}) {
  const auth = await login(payload.email || "", payload.password || "");
  const nextAuth = {
    ...auth,
    status: "signed_in"
  };

  await chrome.storage.local.set({ [AUTH_STORAGE_KEY]: nextAuth });
  return nextAuth;
}

async function handleSignup(payload = {}) {
  const auth = await signup(payload.email || "", payload.password || "", payload.inviteCode || "", {
    topics: stringList(payload.topics),
    keywords: stringList(payload.keywords)
  });
  const nextAuth = {
    ...auth,
    status: "signed_in"
  };

  await chrome.storage.local.set({ [AUTH_STORAGE_KEY]: nextAuth });
  return nextAuth;
}

function stringList(value) {
  return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
}

async function handleLogout() {
  const auth = await getAuthState();
  if (auth.token) {
    // Revoke the server session, but never block local sign-out on network errors.
    await logout(auth.token).catch(() => {});
  }
  return clearAuth();
}

async function clearAuth() {
  // Analyses carry personalized recommendations, so they must not outlive the session.
  const all = await chrome.storage.session.get(null);
  const analysisKeys = Object.keys(all).filter((key) => key.startsWith(TAB_ANALYSIS_KEY_PREFIX));
  if (analysisKeys.length) await chrome.storage.session.remove(analysisKeys);

  await chrome.storage.local.set({
    [AUTH_STORAGE_KEY]: DEFAULT_AUTH,
    [STORAGE_KEY]: DEFAULT_ANALYSIS
  });
  return DEFAULT_AUTH;
}

async function withAuth(request) {
  const auth = await getAuthState();
  if (!auth.token) throw new Error("로그인 후 이용해 주세요.");
  try {
    return await request(auth.token);
  } catch (error) {
    if (error instanceof AuthExpiredError) await clearAuth();
    throw error;
  }
}

async function getAuthState() {
  const stored = await chrome.storage.local.get(AUTH_STORAGE_KEY);
  return {
    ...DEFAULT_AUTH,
    ...(stored[AUTH_STORAGE_KEY] || {})
  };
}

function normalizeKeywords(keywords) {
  if (!Array.isArray(keywords)) {
    return [];
  }

  return keywords
    .map((keyword) => {
      if (typeof keyword === "string") {
        return {
          term: keyword,
          count: 1
        };
      }

      const count = Number(keyword?.count);
      return {
        term: String(keyword?.term || "").trim(),
        count: Number.isFinite(count) ? count : 1
      };
    })
    .filter((keyword) => keyword.term);
}

function isSupportedArticleUrl(url) {
  try { return ["http:", "https:"].includes(new URL(url).protocol); }
  catch { return false; }
}

function originOf(url) {
  try { return new URL(url).origin; }
  catch { return ""; }
}

function withoutHash(url) {
  try {
    const parsed = new URL(url);
    parsed.hash = "";
    return parsed.href;
  } catch {
    return "";
  }
}
