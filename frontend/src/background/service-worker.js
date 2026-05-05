import { login, recordNewsInteraction, requestBackendAnalysis, signUp } from "./api-client.js";
import { buildHighlightPayload } from "./keyword-analysis.js";
import {
  ANALYSIS_STATUS,
  AUTH_STORAGE_KEY,
  CLIENT_USER_ID_STORAGE_KEY,
  DEFAULT_ANALYSIS,
  MESSAGE_TYPES,
  STORAGE_KEY
} from "../shared/constants.js";

chrome.runtime.onInstalled.addListener(() => {
  void ensureClientUserId();
  chrome.storage.local.set({ [STORAGE_KEY]: DEFAULT_ANALYSIS });
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

  if (message?.type === MESSAGE_TYPES.GET_AUTH_STATE) {
    void chrome.storage.local.get(AUTH_STORAGE_KEY).then((stored) => {
      sendResponse({ ok: true, result: stored[AUTH_STORAGE_KEY] || null });
    });

    return true;
  }

  if (message?.type === MESSAGE_TYPES.AUTH_SIGNUP || message?.type === MESSAGE_TYPES.AUTH_LOGIN) {
    const authRequest = message.type === MESSAGE_TYPES.AUTH_SIGNUP ? signUp : login;
    void authRequest(message.payload || {})
      .then(async (auth) => {
        await chrome.storage.local.set({ [AUTH_STORAGE_KEY]: auth });
        sendResponse({ ok: true, result: auth });
      })
      .catch((error) => sendResponse({ ok: false, error: error.message }));

    return true;
  }

  if (message?.type === MESSAGE_TYPES.AUTH_LOGOUT) {
    void chrome.storage.local.remove(AUTH_STORAGE_KEY).then(() => {
      sendResponse({ ok: true });
    });

    return true;
  }

  if (message?.type === MESSAGE_TYPES.RECORD_INTERACTION) {
    void ensureClientUserId()
      .then((clientUserId) =>
        recordNewsInteraction({
          ...message.payload,
          clientUserId
        })
      )
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));

    return true;
  }

  return false;
});

async function analyzeArticle(article, sender) {
  const clientUserId = await ensureClientUserId();

  await chrome.storage.local.set({
    [STORAGE_KEY]: {
      ...DEFAULT_ANALYSIS,
      status: ANALYSIS_STATUS.LOADING,
      article,
      updatedAt: new Date().toISOString()
    }
  });

  let backendResult;

  try {
    backendResult = await requestBackendAnalysis(article, clientUserId);
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

  const keywords = backendResult.keywords || [];
  const analysis = {
    status: ANALYSIS_STATUS.READY,
    article: backendResult.article || article,
    keywords,
    summary: backendResult.summary,
    recommendations: backendResult.recommendations,
    adLikelihood: backendResult.adLikelihood,
    updatedAt: new Date().toISOString()
  };

  await chrome.storage.local.set({ [STORAGE_KEY]: analysis });

  if (sender.tab?.id) {
    await chrome.tabs.sendMessage(sender.tab.id, {
      type: "HIGHLIGHT_KEYWORDS",
      payload: {
        keywords: buildHighlightPayload(keywords)
      }
    });
  }

  return analysis;
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

async function ensureClientUserId() {
  const authStored = await chrome.storage.local.get(AUTH_STORAGE_KEY);
  if (authStored[AUTH_STORAGE_KEY]?.clientUserId) {
    return authStored[AUTH_STORAGE_KEY].clientUserId;
  }

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
