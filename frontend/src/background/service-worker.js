import { login, requestBackendAnalysis, signup } from "./api-client.js";
import { buildHighlightPayload } from "./keyword-analysis.js";
import {
  ANALYSIS_STATUS,
  AUTH_STORAGE_KEY,
  CLIENT_USER_ID_STORAGE_KEY,
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
      article,
      updatedAt: new Date().toISOString()
    }
  });

  if (sender.tab?.id) {
    await showLoadingOverlays(sender.tab.id);
  }

  let backendResult;

  try {
    backendResult = await requestBackendAnalysis(article.url, auth.token, await ensureClientUserId());
  } catch (error) {
    await chrome.storage.local.set({
      [STORAGE_KEY]: {
        ...DEFAULT_ANALYSIS,
        status: ANALYSIS_STATUS.ERROR,
        article,
        summary: "분석 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        updatedAt: new Date().toISOString()
      }
    });
    throw error;
  }

  const keywords = normalizeKeywords(backendResult.keywords);
  const analysis = {
    status: ANALYSIS_STATUS.READY,
    article,
    keywords,
    summary: backendResult.summary,
    recommendations: backendResult.recommendations,
    adLikelihood: backendResult.adLikelihood,
    updatedAt: new Date().toISOString()
  };

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
  await analyzeActiveTab();
  return nextAuth;
}

async function handleSignup(payload = {}) {
  const auth = await signup(payload.email || "", payload.password || "");
  const nextAuth = {
    ...auth,
    status: "signed_in"
  };

  await chrome.storage.local.set({ [AUTH_STORAGE_KEY]: nextAuth });
  await analyzeActiveTab();
  return nextAuth;
}

async function handleLogout() {
  await chrome.storage.local.set({
    [AUTH_STORAGE_KEY]: DEFAULT_AUTH,
    [STORAGE_KEY]: DEFAULT_ANALYSIS
  });
  return DEFAULT_AUTH;
}

async function analyzeActiveTab() {
  const [tab] = await chrome.tabs.query({
    active: true,
    currentWindow: true
  });

  if (!isSupportedArticleUrl(tab?.url)) {
    return DEFAULT_ANALYSIS;
  }

  try {
    return await analyzeArticle(
      {
        url: tab.url
      },
      {
        tab
      }
    );
  } catch {
    return DEFAULT_ANALYSIS;
  }
}

async function getAuthState() {
  const stored = await chrome.storage.local.get(AUTH_STORAGE_KEY);
  return {
    ...DEFAULT_AUTH,
    ...(stored[AUTH_STORAGE_KEY] || {})
  };
}

async function ensureClientUserId() {
  const stored = await chrome.storage.local.get(CLIENT_USER_ID_STORAGE_KEY);
  if (stored[CLIENT_USER_ID_STORAGE_KEY]) {
    return stored[CLIENT_USER_ID_STORAGE_KEY];
  }

  const clientUserId =
    typeof globalThis.crypto?.randomUUID === "function"
      ? globalThis.crypto.randomUUID()
      : `client-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  await chrome.storage.local.set({ [CLIENT_USER_ID_STORAGE_KEY]: clientUserId });
  return clientUserId;
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
  if (isSupportedArticleUrl(tab?.url)) {
    return;
  }

  await chrome.storage.local.set({ [STORAGE_KEY]: DEFAULT_ANALYSIS });
}

function isSupportedArticleUrl(url) {
  if (!url) {
    return false;
  }

  try {
    const parsed = new URL(url);
    const isNaverNewsHost =
      parsed.hostname === "news.naver.com" || parsed.hostname === "n.news.naver.com";

    if (!isNaverNewsHost) {
      return false;
    }

    return /\/article\//.test(parsed.pathname);
  } catch {
    return false;
  }
}
