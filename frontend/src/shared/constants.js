export const STORAGE_KEY = "deepnews.latestAnalysis";
export const THEME_STORAGE_KEY = "deepnews.theme";
export const CLIENT_USER_ID_STORAGE_KEY = "deepnews.clientUserId";
export const AUTH_STORAGE_KEY = "deepnews.auth";

export const MESSAGE_TYPES = {
  ANALYZE_ARTICLE: "ANALYZE_ARTICLE",
  GET_LATEST_ANALYSIS: "GET_LATEST_ANALYSIS",
  OPEN_SIDE_PANEL: "OPEN_SIDE_PANEL",
  RECORD_INTERACTION: "RECORD_INTERACTION",
  AUTH_SIGNUP: "AUTH_SIGNUP",
  AUTH_LOGIN: "AUTH_LOGIN",
  AUTH_LOGOUT: "AUTH_LOGOUT",
  GET_AUTH_STATE: "GET_AUTH_STATE"
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
