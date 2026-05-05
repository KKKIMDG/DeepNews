import { requestBackendAnalysis } from "./api-client.js";
import { buildHighlightPayload } from "./keyword-analysis.js";
import {
  ANALYSIS_STATUS,
  DEFAULT_ANALYSIS,
  MESSAGE_TYPES,
  STORAGE_KEY
} from "../shared/constants.js";

chrome.runtime.onInstalled.addListener(() => {
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

  return false;
});

async function analyzeArticle(article, sender) {
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
    backendResult = await requestBackendAnalysis(article);
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
