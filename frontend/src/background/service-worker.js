import { login, requestBackendAnalysis, signup } from "./api-client.js";
import { buildHighlightPayload } from "./keyword-analysis.js";
import {
  ANALYSIS_STATUS,
  AUTH_STORAGE_KEY,
  DEFAULT_AUTH,
  DEFAULT_ANALYSIS,
  MESSAGE_TYPES,
  OVERLAY_STATE_STORAGE_KEY,
  STORAGE_KEY
} from "../shared/constants.js";

chrome.runtime.onInstalled.addListener(async () => {
  const stored = await chrome.storage.local.get([AUTH_STORAGE_KEY, STORAGE_KEY]);
  await chrome.storage.local.set({
    [AUTH_STORAGE_KEY]: stored[AUTH_STORAGE_KEY] || DEFAULT_AUTH,
    [STORAGE_KEY]: stored[STORAGE_KEY] || DEFAULT_ANALYSIS
  });
});

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab?.windowId) {
    return;
  }

  await chrome.sidePanel.open({ windowId: tab.windowId });
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  const tab = await chrome.tabs.get(tabId);
  await syncAnalysisForTab(tab);
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete" && !changeInfo.url) {
    return;
  }

  void syncAnalysisForTab(tab);
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === MESSAGE_TYPES.ANALYZE_ARTICLE) {
    void analyzeArticle(message.payload, sender)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));

    return true;
  }

  if (message?.type === MESSAGE_TYPES.GET_LATEST_ANALYSIS) {
    void chrome.storage.local.get(STORAGE_KEY).then((stored) => {
      sendResponse({
        ok: true,
        result: stored[STORAGE_KEY] || DEFAULT_ANALYSIS
      });
    });

    return true;
  }

  if (message?.type === MESSAGE_TYPES.ANALYZE_ACTIVE_TAB) {
    void analyzeActiveTab()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));

    return true;
  }

  if (message?.type === MESSAGE_TYPES.GET_AUTH_STATE) {
    void getAuthState().then((auth) => {
      sendResponse({
        ok: true,
        result: auth
      });
    });

    return true;
  }

  if (message?.type === MESSAGE_TYPES.LOGIN) {
    void handleLogin(message.payload)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));

    return true;
  }

  if (message?.type === MESSAGE_TYPES.SIGNUP) {
    void handleSignup(message.payload)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));

    return true;
  }

  if (message?.type === MESSAGE_TYPES.LOGOUT) {
    void handleLogout().then((result) => {
      sendResponse({ ok: true, result });
    });

    return true;
  }

  return false;
});

async function analyzeArticle(article, sender) {
  const auth = await getAuthState();
  if (!auth.token) {
    await chrome.storage.local.set({ [STORAGE_KEY]: DEFAULT_ANALYSIS });
    return DEFAULT_ANALYSIS;
  }

  if (!isSupportedArticleUrl(article?.url)) {
    await chrome.storage.local.set({ [STORAGE_KEY]: DEFAULT_ANALYSIS });
    return DEFAULT_ANALYSIS;
  }

  await chrome.storage.local.set({
    [STORAGE_KEY]: {
      ...DEFAULT_ANALYSIS,
      status: ANALYSIS_STATUS.LOADING,
      article: { url: article.url, title: article.title },
      updatedAt: new Date().toISOString()
    }
  });

  if (sender.tab?.id) {
    await showLoadingOverlays(sender.tab.id);
  }

  let backendResult;

  try {
    backendResult = await requestBackendAnalysis(article, auth.token);
  } catch (error) {
    await chrome.storage.local.set({
      [STORAGE_KEY]: {
        ...DEFAULT_ANALYSIS,
        status: ANALYSIS_STATUS.ERROR,
        article: { url: article.url, title: article.title },
        summary: "분석 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        updatedAt: new Date().toISOString()
      }
    });
    throw error;
  }

  const keywords = normalizeKeywords(backendResult.keywords);
  const analysis = {
    status: ANALYSIS_STATUS.READY,
    article: { url: article.url, title: article.title },
    keywords,
    summary: backendResult.summary,
    recommendations: backendResult.recommendations,
    adLikelihood: backendResult.adLikelihood,
    updatedAt: new Date().toISOString()
  };

  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (activeTab?.id !== sender.tab?.id || activeTab?.url !== article.url) {
    return analysis;
  }
  await chrome.storage.local.set({ [STORAGE_KEY]: analysis });

  if (sender.tab?.id) {
    await sendTabMessageWithContentScript(sender.tab.id, {
      type: "HIGHLIGHT_KEYWORDS",
      payload: {
        keywords: buildHighlightPayload(keywords)
      }
    });

    await restoreOpenOverlays(sender.tab.id, analysis);
  }

  return analysis;
}

async function restoreOpenOverlays(tabId, analysis) {
  const stored = await chrome.storage.local.get(OVERLAY_STATE_STORAGE_KEY);
  const openOverlays = stored[OVERLAY_STATE_STORAGE_KEY] || {};

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
}

async function showLoadingOverlays(tabId) {
  const stored = await chrome.storage.local.get(OVERLAY_STATE_STORAGE_KEY);
  const openOverlays = stored[OVERLAY_STATE_STORAGE_KEY] || {};

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
  const auth = await signup(payload.email || "", payload.password || "");
  const nextAuth = {
    ...auth,
    status: "signed_in"
  };

  await chrome.storage.local.set({ [AUTH_STORAGE_KEY]: nextAuth });
  return nextAuth;
}

async function handleLogout() {
  await chrome.storage.local.set({
    [AUTH_STORAGE_KEY]: DEFAULT_AUTH,
    [STORAGE_KEY]: DEFAULT_ANALYSIS
  });
  return DEFAULT_AUTH;
}

let analysisInProgress = false;

async function analyzeActiveTab() {
  if (analysisInProgress) throw new Error("이미 분석 중입니다. 잠시 기다려 주세요.");
  const auth = await getAuthState();
  if (!auth.token) throw new Error("로그인 후 분석해 주세요.");
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!isSupportedArticleUrl(tab?.url)) throw new Error("HTTP 또는 HTTPS 기사 페이지에서 실행해 주세요.");
  analysisInProgress = true;
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["src/vendor/readability/Readability.js", "src/content/content-script.js"]
    });
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, files: ["src/content/extract-article.js"]
    });
    const extracted = results[0]?.result;
    if (!extracted?.ok) throw new Error(extracted?.error || "기사 본문을 추출하지 못했습니다.");
    const current = await chrome.tabs.get(tab.id);
    if (current.url !== extracted.article.url) throw new Error("페이지가 변경되었습니다. 다시 분석해 주세요.");
    return await analyzeArticle(extracted.article, { tab });
  } finally {
    analysisInProgress = false;
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

async function syncAnalysisForTab(tab) {
  const stored = await chrome.storage.local.get(STORAGE_KEY);
  if (stored[STORAGE_KEY]?.article?.url === tab?.url) return;
  await chrome.storage.local.set({ [STORAGE_KEY]: DEFAULT_ANALYSIS });
}

function isSupportedArticleUrl(url) {
  try { return ["http:", "https:"].includes(new URL(url).protocol); }
  catch { return false; }
}
