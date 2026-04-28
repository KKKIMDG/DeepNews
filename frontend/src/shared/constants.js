export const STORAGE_KEY = "deepnews.latestAnalysis";
export const THEME_STORAGE_KEY = "deepnews.theme";

export const MESSAGE_TYPES = {
  ANALYZE_ARTICLE: "ANALYZE_ARTICLE",
  GET_LATEST_ANALYSIS: "GET_LATEST_ANALYSIS",
  OPEN_SIDE_PANEL: "OPEN_SIDE_PANEL"
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
