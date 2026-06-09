export const STORAGE_KEY = "deepnews.latestAnalysis";
export const THEME_STORAGE_KEY = "deepnews.theme";
export const AUTH_STORAGE_KEY = "deepnews.auth";
export const OVERLAY_STATE_STORAGE_KEY = "deepnews.openOverlays";

export const MESSAGE_TYPES = {
  ANALYZE_ARTICLE: "ANALYZE_ARTICLE",
  ANALYZE_ACTIVE_TAB: "ANALYZE_ACTIVE_TAB",
  GET_LATEST_ANALYSIS: "GET_LATEST_ANALYSIS",
  GET_AUTH_STATE: "GET_AUTH_STATE",
  LOGIN: "LOGIN",
  LOGOUT: "LOGOUT",
  OPEN_SIDE_PANEL: "OPEN_SIDE_PANEL",
  SHOW_AD_LIKELIHOOD: "SHOW_AD_LIKELIHOOD",
  SHOW_KEYWORDS: "SHOW_KEYWORDS",
  SHOW_KEYWORD_CHART: "SHOW_KEYWORD_CHART",
  SIGNUP: "SIGNUP",
  SHOW_SUMMARY: "SHOW_SUMMARY",
  SHOW_RECOMMENDATIONS: "SHOW_RECOMMENDATIONS",
  SHOW_LOADING_OVERLAYS: "SHOW_LOADING_OVERLAYS",
  HIDE_OVERLAY: "HIDE_OVERLAY",
  HIDE_ALL_OVERLAYS: "HIDE_ALL_OVERLAYS"
};

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
  adLikelihood: {
    label: "Not analyzed",
    score: 0
  },
  updatedAt: null
};

export const DEFAULT_AUTH = {
  token: "",
  user: null,
  status: "signed_out"
};
