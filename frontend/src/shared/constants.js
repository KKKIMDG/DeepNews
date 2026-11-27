// storage.local: the analysis and open overlays of the active tab, mirrored by the service worker for the panel.
export const STORAGE_KEY = "deepnews.latestAnalysis";
export const THEME_STORAGE_KEY = "deepnews.theme";
// "on" | "off"; unset follows the OS reduced-motion setting.
export const MOTION_STORAGE_KEY = "deepnews.motion";
// Set after the first greeting so returning visitors get a shorter hello.
export const GREETED_STORAGE_KEY = "deepnews.greeted";
export const AUTH_STORAGE_KEY = "deepnews.auth";
export const OVERLAY_STATE_STORAGE_KEY = "deepnews.openOverlays";
// Analysis server origin chosen in the panel (team testing goes through a temporary public tunnel).
export const API_BASE_STORAGE_KEY = "deepnews.apiBase";
export const DEFAULT_API_BASE = "http://127.0.0.1:8000";
// Covered by manifest host_permissions; any other server needs a runtime permission grant.
export const BUNDLED_API_ORIGINS = ["http://127.0.0.1:8000", "http://localhost:8000"];

// storage.session (extension pages and the service worker only): per-tab state.
export const TAB_ANALYSIS_KEY_PREFIX = "deepnews.tabAnalysis.";
export const TAB_OVERLAYS_KEY_PREFIX = "deepnews.tabOverlays.";
export const ACTIVE_TAB_STORAGE_KEY = "deepnews.activeTabId";
// 수집 도우미: tabs it opened (tabId -> request) and the latest result per article.
export const COLLECT_TABS_KEY = "deepnews.collectTabs";
export const COLLECT_RESULTS_KEY = "deepnews.collectResults";
// storage.local: analyze every 네이버 뉴스 article the user opens.
export const NAVER_AUTO_COLLECT_KEY = "deepnews.naverAutoCollect";
// Page loading, not inference (~0.5 s each), limits collection; the server queue absorbs 6 tabs.
export const COLLECT_LIMIT = 6;
export const NAVER_NEWS_ORIGINS = [
  "https://n.news.naver.com/*",
  "https://m.news.naver.com/*",
  "https://news.naver.com/*",
  "https://m.sports.naver.com/*",
  "https://m.entertain.naver.com/*"
];

// A LOADING state older than this was left behind by an interrupted service worker.
export const STALE_LOADING_MS = 200000;
export const STALE_LOADING_MESSAGE = "분석 시간이 초과되었습니다. 다시 시도해 주세요.";

export const MESSAGE_TYPES = {
  ANALYZE_ACTIVE_TAB: "ANALYZE_ACTIVE_TAB",
  GET_LATEST_ANALYSIS: "GET_LATEST_ANALYSIS",
  GET_AUTH_STATE: "GET_AUTH_STATE",
  LOGIN: "LOGIN",
  LOGOUT: "LOGOUT",
  DELETE_ACCOUNT: "DELETE_ACCOUNT",
  CHANGE_PASSWORD: "CHANGE_PASSWORD",
  EXPORT_MY_DATA: "EXPORT_MY_DATA",
  REPORT_NEWS: "REPORT_NEWS",
  SET_OVERLAY_STATE: "SET_OVERLAY_STATE",
  OVERLAY_CLOSED: "OVERLAY_CLOSED",
  SHOW_AD_LIKELIHOOD: "SHOW_AD_LIKELIHOOD",
  SHOW_KEYWORDS: "SHOW_KEYWORDS",
  SHOW_KEYWORD_CHART: "SHOW_KEYWORD_CHART",
  SIGNUP: "SIGNUP",
  SHOW_SUMMARY: "SHOW_SUMMARY",
  SHOW_RECOMMENDATIONS: "SHOW_RECOMMENDATIONS",
  SHOW_LOADING_OVERLAYS: "SHOW_LOADING_OVERLAYS",
  HIDE_LOADING_OVERLAYS: "HIDE_LOADING_OVERLAYS",
  HIDE_OVERLAY: "HIDE_OVERLAY",
  HIDE_ALL_OVERLAYS: "HIDE_ALL_OVERLAYS",
  GET_PROFILE: "GET_PROFILE",
  SET_KEYWORD_PREFERENCE: "SET_KEYWORD_PREFERENCE",
  DELETE_KEYWORD_PREFERENCE: "DELETE_KEYWORD_PREFERENCE",
  UPDATE_SETTINGS: "UPDATE_SETTINGS",
  GET_HISTORY: "GET_HISTORY",
  DELETE_HISTORY: "DELETE_HISTORY",
  GET_FEED: "GET_FEED",
  SET_TOPICS: "SET_TOPICS",
  SEARCH_NAVER_NEWS: "SEARCH_NAVER_NEWS",
  COLLECT_OPEN: "COLLECT_OPEN",
  GET_COLLECT_CANDIDATES: "GET_COLLECT_CANDIDATES"
};

// Codes are BigKinds top-level categories, as the backend (personalization.ranking.TOPIC_LABELS) expects.
export const INTEREST_TOPICS = [
  { code: "정치", label: "정치", icon: "🏛️" },
  { code: "경제", label: "경제", icon: "📈" },
  { code: "사회", label: "사회", icon: "👥" },
  { code: "국제", label: "국제", icon: "🌏" },
  { code: "IT_과학", label: "IT·과학", icon: "🔬" },
  { code: "문화", label: "문화·연예", icon: "🎬" },
  { code: "스포츠", label: "스포츠", icon: "⚽" },
  { code: "지역", label: "지역", icon: "📍" }
];
export const MAX_INITIAL_KEYWORDS = 10;

export const OVERLAY_NAMES = ["keywords", "keywordChart", "summary", "recommendations", "adLikelihood"];

export const ANALYSIS_STATUS = {
  IDLE: "idle",
  LOADING: "loading",
  READY: "ready",
  ERROR: "error"
};

export const DEFAULT_ANALYSIS = {
  status: ANALYSIS_STATUS.IDLE,
  article: null,
  keywords: [],
  summary: "",
  recommendations: [],
  // The analysis is shown first; related articles arrive in a second request.
  recommendationsPending: false,
  adLikelihood: {
    label: "미분석",
    score: -1
  },
  newsId: null,
  contentOrigin: "",
  sharedFromOther: false,
  reportCount: 0,
  reportedByMe: false,
  error: "",
  startedAt: null,
  updatedAt: null
};

export const DEFAULT_AUTH = {
  token: "",
  user: null,
  status: "signed_out"
};

export function expireStaleLoading(analysis, now = Date.now()) {
  if (analysis?.recommendationsPending) {
    const updatedAt = Date.parse(analysis.updatedAt || "");
    if (!Number.isFinite(updatedAt) || now - updatedAt > STALE_LOADING_MS) {
      return { ...analysis, recommendationsPending: false };
    }
  }
  if (analysis?.status !== ANALYSIS_STATUS.LOADING) return analysis;
  const startedAt = Date.parse(analysis.startedAt || "");
  if (Number.isFinite(startedAt) && now - startedAt <= STALE_LOADING_MS) return analysis;
  return { ...analysis, status: ANALYSIS_STATUS.ERROR, error: STALE_LOADING_MESSAGE };
}

export function isNaverUrl(url) {
  try {
    const { hostname } = new URL(url);
    return hostname === "naver.com" || hostname.endsWith(".naver.com");
  } catch {
    return false;
  }
}

export function isNaverArticleUrl(url) {
  try {
    const { hostname, pathname, searchParams } = new URL(url);
    if (["n.news.naver.com", "m.news.naver.com", "m.sports.naver.com", "m.entertain.naver.com"].includes(hostname)) {
      return /\/article\/\d+\/\d+/.test(pathname);
    }
    return hostname === "news.naver.com" && pathname.endsWith("read.naver") && searchParams.has("aid");
  } catch {
    return false;
  }
}
