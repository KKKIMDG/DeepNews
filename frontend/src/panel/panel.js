import {
  ANALYSIS_STATUS,
  API_BASE_STORAGE_KEY,
  AUTH_STORAGE_KEY,
  BUNDLED_API_ORIGINS,
  DEFAULT_API_BASE,
  DEFAULT_AUTH,
  DEFAULT_ANALYSIS,
  GREETED_STORAGE_KEY,
  INTEREST_TOPICS,
  MAX_INITIAL_KEYWORDS,
  MESSAGE_TYPES,
  MOTION_STORAGE_KEY,
  OVERLAY_STATE_STORAGE_KEY,
  STALE_LOADING_MS,
  STORAGE_KEY,
  THEME_STORAGE_KEY,
  expireStaleLoading,
  isNaverUrl
} from "../shared/constants.js";
import { mountMascots, typeText, wait } from "./mascot.js";

const keywordListNode = document.getElementById("keyword-list");
const chartNode = document.getElementById("keyword-chart");
const summaryNode = document.getElementById("summary");
const recommendationsNode = document.getElementById("recommendations");
const adLikelihoodNode = document.getElementById("ad-likelihood");
const analysisContentNode = document.getElementById("analysis-content");
const authEmailNode = document.getElementById("auth-email");
const authFormNode = document.getElementById("auth-form");
const authMessageNode = document.getElementById("auth-message");
const authPasswordNode = document.getElementById("auth-password");
const authStatusNode = document.getElementById("auth-status");
const authSubmitNode = document.getElementById("auth-submit");
const authInviteNode = document.getElementById("auth-invite");
const inviteFieldNode = document.getElementById("invite-field");
const serverCurrentNode = document.getElementById("server-current");
const serverFormNode = document.getElementById("server-form");
const serverUrlNode = document.getElementById("server-url");
const serverResetNode = document.getElementById("server-reset");
const serverMessageNode = document.getElementById("server-message");
const loginModeNode = document.getElementById("login-mode");
const logoutButtonNode = document.getElementById("logout-button");
const deleteAccountNode = document.getElementById("delete-account");
const deleteAccountFormNode = document.getElementById("delete-account-form");
const deleteAccountPasswordNode = document.getElementById("delete-account-password");
const deleteAccountSubmitNode = document.getElementById("delete-account-submit");
const deleteAccountMessageNode = document.getElementById("delete-account-message");
const signupModeNode = document.getElementById("signup-mode");
const themeToggleNode = document.getElementById("theme-toggle");
const showAdPopupNode = document.getElementById("show-ad-popup");
const showKeywordPopupNode = document.getElementById("show-keyword-popup");
const showKeywordChartPopupNode = document.getElementById("show-keyword-chart-popup");
const showSummaryPopupNode = document.getElementById("show-summary-popup");
const showRecommendationsPopupNode = document.getElementById("show-recommendations-popup");
const showAllPopupsNode = document.getElementById("show-all-popups");
const hideAllPopupsNode = document.getElementById("hide-all-popups");
const feedNode = document.getElementById("feed");
const refreshFeedNode = document.getElementById("refresh-feed");
const profileCaptionNode = document.getElementById("profile-caption");
const interestListNode = document.getElementById("interest-list");
const excludedListNode = document.getElementById("excluded-list");
const keywordFormNode = document.getElementById("keyword-form");
const keywordInputNode = document.getElementById("keyword-input");
const adFilterNode = document.getElementById("ad-filter");
const profileMessageNode = document.getElementById("profile-message");
const historyCaptionNode = document.getElementById("history-caption");
const historyListNode = document.getElementById("history-list");
const analyzeButton = document.getElementById("analyze-article");
const analysisMessage = document.getElementById("analysis-message");
const trustNoteNode = document.getElementById("trust-note");
const trustTextNode = document.getElementById("trust-text");
const reportToggleNode = document.getElementById("report-toggle");
const reportFormNode = document.getElementById("report-form");
const reportReasonNode = document.getElementById("report-reason");
const reportSubmitNode = document.getElementById("report-submit");
const reportCancelNode = document.getElementById("report-cancel");
const reportMessageNode = document.getElementById("report-message");
const reanalyzeNode = document.getElementById("reanalyze");
const changePasswordNode = document.getElementById("change-password");
const changePasswordFormNode = document.getElementById("change-password-form");
const currentPasswordNode = document.getElementById("current-password");
const newPasswordNode = document.getElementById("new-password");
const changePasswordSubmitNode = document.getElementById("change-password-submit");
const changePasswordMessageNode = document.getElementById("change-password-message");
const accountToolsNode = document.getElementById("account-tools");
const exportDataNode = document.getElementById("export-data");
const exportMessageNode = document.getElementById("export-message");
const permissionListNode = document.getElementById("permission-list");
const motionToggleNode = document.getElementById("motion-toggle");
const welcomeNode = document.getElementById("welcome");
const bubbleNode = welcomeNode?.querySelector(".bubble");
const bubbleHelloNode = document.getElementById("bubble-hello");
const bubbleLineNode = document.getElementById("bubble-line");
const greetingNode = document.getElementById("greeting");
const analyzeMascotNode = document.getElementById("analyze-mascot");
const adMeterFillNode = document.getElementById("ad-meter-fill");
const signupStepsNode = document.getElementById("signup-steps");
const authFieldsNode = document.getElementById("auth-fields");
const interestStepNode = document.getElementById("interest-step");
const passwordHintNode = document.getElementById("password-hint");
const signupTopicsNode = document.getElementById("signup-topics");
const signupKeywordNode = document.getElementById("signup-keyword");
const signupKeywordTagsNode = document.getElementById("signup-keyword-tags");
const signupBackNode = document.getElementById("signup-back");
const signupSubmitNode = document.getElementById("signup-submit");
const profileTopicsNode = document.getElementById("profile-topics");
const topicCaptionNode = document.getElementById("topic-caption");
const topicStrengthNode = document.getElementById("topic-strength");
const topicStrengthLabelNode = document.getElementById("topic-strength-label");
const topicStrengthFillNode = document.getElementById("topic-strength-fill");
const topicMessageNode = document.getElementById("topic-message");
const displaySettingsNode = document.getElementById("display-settings");
const serverSettingsNode = document.getElementById("server-settings");
const recommendationsBlockNode = document.getElementById("recommendations-block");
const naverBlockNode = document.getElementById("naver-block");
const naverSearchNode = document.getElementById("naver-search");
const naverSearchCaptionNode = document.getElementById("naver-search-caption");
const naverResultsNode = document.getElementById("naver-results");
const tabButtonNodes = [...document.querySelectorAll(".tab-button")];
const tabPanelNodes = [...document.querySelectorAll(".tab-panel")];

const REPORT_THRESHOLD = 3;

let latestAnalysis = DEFAULT_ANALYSIS;
let latestAuth = DEFAULT_AUTH;
let latestOpenOverlays = {};
let authMode = "login";
// Shown again after the sign-out re-render, which otherwise clears the auth message.
let authNotice = "";
let staleLoadingTimer = null;
let lastAnalysisMessageKey = "";
// Keyword edits and manual refreshes overlap; only the newest feed request may render.
let feedRequestId = 0;
// NAVER search results live only in this panel's memory and belong to one article (검색 API 특약 2.3, 2.4).
let naverResultsUrl = "";
let naverRequestId = 0;
let signupStep = 1;
let signupKeywords = [];
// A newer greeting (e.g. after toggling motion) cancels the one still typing.
let welcomeRun = 0;

mountMascots();
renderTopicChips(signupTopicsNode);
renderTopicChips(profileTopicsNode);
selectTab("analysis");
await initialize();
void chrome.storage.local.get(API_BASE_STORAGE_KEY).then((stored) => renderServer(stored[API_BASE_STORAGE_KEY] || DEFAULT_API_BASE));

serverFormNode?.addEventListener("submit", (event) => {
  event.preventDefault();
  void saveServer(serverUrlNode?.value || "");
});

serverResetNode?.addEventListener("click", () => {
  void saveServer(DEFAULT_API_BASE);
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") {
    return;
  }

  if (changes[STORAGE_KEY]) {
    const nextAnalysis = changes[STORAGE_KEY].newValue || DEFAULT_ANALYSIS;
    render(nextAnalysis);

    // A finished analysis adds to the reading history, so profile, history and feed change too.
    if (
      nextAnalysis.status === ANALYSIS_STATUS.READY &&
      changes[STORAGE_KEY].oldValue?.status !== ANALYSIS_STATUS.READY
    ) {
      void loadPersonalization();
    }
  }

  if (changes[AUTH_STORAGE_KEY]) {
    renderAuth(changes[AUTH_STORAGE_KEY].newValue || DEFAULT_AUTH);
  }

  if (changes[THEME_STORAGE_KEY]) {
    applyTheme(changes[THEME_STORAGE_KEY].newValue || "light");
  }

  if (changes[MOTION_STORAGE_KEY]) {
    applyMotion(changes[MOTION_STORAGE_KEY].newValue);
  }

  if (changes[OVERLAY_STATE_STORAGE_KEY]) {
    latestOpenOverlays = changes[OVERLAY_STATE_STORAGE_KEY].newValue || {};
    render(latestAnalysis);
  }
});

authFormNode?.addEventListener("submit", (event) => {
  event.preventDefault();
  void submitAuthForm();
});

loginModeNode?.addEventListener("click", () => {
  setAuthMode("login");
});

signupModeNode?.addEventListener("click", () => {
  setAuthMode("signup");
});

signupBackNode?.addEventListener("click", () => {
  setAuthMessage("");
  setSignupStep(1);
});

signupTopicsNode?.addEventListener("click", (event) => {
  const chip = event.target.closest(".topic-chip");
  if (chip) chip.setAttribute("aria-pressed", String(chip.getAttribute("aria-pressed") !== "true"));
});

signupKeywordNode?.addEventListener("keydown", (event) => {
  if (event.isComposing) return;
  if (event.key === "Enter" || event.key === ",") {
    event.preventDefault();
    addSignupKeyword(signupKeywordNode.value);
  } else if (event.key === "Backspace" && !signupKeywordNode.value && signupKeywords.length) {
    signupKeywords = signupKeywords.slice(0, -1);
    renderSignupKeywords();
  }
});

signupKeywordTagsNode?.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-index]");
  if (!button) return;
  signupKeywords = signupKeywords.filter((_, index) => index !== Number(button.dataset.index));
  renderSignupKeywords();
  signupKeywordNode?.focus();
});

profileTopicsNode?.addEventListener("click", (event) => {
  const chip = event.target.closest(".topic-chip");
  if (!chip || chip.disabled) return;
  const adding = chip.getAttribute("aria-pressed") !== "true";
  const label = INTEREST_TOPICS.find((topic) => topic.code === chip.dataset.topic)?.label || chip.dataset.topic;
  const next = selectedTopics(profileTopicsNode).filter((code) => code !== chip.dataset.topic);
  if (adding) next.push(chip.dataset.topic);
  void updateProfile(
    MESSAGE_TYPES.SET_TOPICS,
    { topics: next },
    adding ? `'${label}' 분야를 추가했습니다. 맞춤 기사에 바로 반영됩니다.` : `'${label}' 분야를 뺐습니다.`,
    topicMessageNode
  );
});

for (const button of tabButtonNodes) {
  button.addEventListener("click", () => selectTab(button.dataset.tab));
  button.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    const offset = event.key === "ArrowRight" ? 1 : -1;
    const next = tabButtonNodes[(tabButtonNodes.indexOf(button) + offset + tabButtonNodes.length) % tabButtonNodes.length];
    selectTab(next.dataset.tab);
    next.focus();
  });
}

motionToggleNode?.addEventListener("change", async (event) => {
  const value = event.currentTarget.checked ? "on" : "off";
  applyMotion(value);
  await chrome.storage.local.set({ [MOTION_STORAGE_KEY]: value });
  if (!latestAuth.token && value === "on") void playWelcome();
});

logoutButtonNode?.addEventListener("click", () => {
  void logout();
});

deleteAccountFormNode?.addEventListener("submit", (event) => {
  event.preventDefault();
  void deleteAccount();
});

changePasswordFormNode?.addEventListener("submit", (event) => {
  event.preventDefault();
  void changePassword();
});

exportDataNode?.addEventListener("click", () => {
  void exportMyData();
});

for (const link of document.querySelectorAll(".privacy-link")) {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    void chrome.tabs.create({ url: chrome.runtime.getURL("src/panel/privacy.html") });
  });
}

reportToggleNode?.addEventListener("click", () => {
  setReportFormOpen(Boolean(reportFormNode?.hidden));
});

reportCancelNode?.addEventListener("click", () => {
  setReportFormOpen(false);
});

reportFormNode?.addEventListener("submit", (event) => {
  event.preventDefault();
  void submitReport();
});

reanalyzeNode?.addEventListener("click", () => {
  void analyzeCurrentArticle();
});

analyzeButton?.addEventListener("click", () => {
  void analyzeCurrentArticle();
});

permissionListNode?.addEventListener("click", (event) => {
  const button = event.target.closest('button[data-action="revoke-origin"]');
  if (!button) return;

  button.disabled = true;
  void chrome.permissions
    .remove({ origins: [button.dataset.origin] })
    .catch(() => false)
    .then(() => renderSitePermissions());
});

chrome.permissions.onAdded.addListener(() => void renderSitePermissions());
chrome.permissions.onRemoved.addListener(() => void renderSitePermissions());

themeToggleNode?.addEventListener("change", async (event) => {
  const nextTheme = event.currentTarget.checked ? "dark" : "light";
  applyTheme(nextTheme);
  await chrome.storage.local.set({ [THEME_STORAGE_KEY]: nextTheme });
});

showAdPopupNode?.addEventListener("click", () => {
  void showAdLikelihoodPopup();
});

showKeywordPopupNode?.addEventListener("click", () => {
  void showKeywordPopup();
});

showKeywordChartPopupNode?.addEventListener("click", () => {
  void showKeywordChartPopup();
});

showSummaryPopupNode?.addEventListener("click", () => {
  void showSummaryPopup();
});

showRecommendationsPopupNode?.addEventListener("click", () => {
  void showRecommendationsPopup();
});

showAllPopupsNode?.addEventListener("click", () => {
  void showAllPopups();
});

hideAllPopupsNode?.addEventListener("click", () => {
  void hideAllPopups();
});

naverSearchNode?.addEventListener("click", () => {
  void searchNaverNews();
});

refreshFeedNode?.addEventListener("click", () => {
  void loadFeed();
});

keywordFormNode?.addEventListener("submit", (event) => {
  event.preventDefault();
  const term = keywordInputNode?.value.trim() || "";
  const preference = event.submitter?.dataset.preference === "exclude" ? "exclude" : "include";
  if (!term) {
    setProfileMessage("키워드를 입력해 주세요.", "error");
    return;
  }

  void updateProfile(
    MESSAGE_TYPES.SET_KEYWORD_PREFERENCE,
    { term, preference },
    preference === "include" ? `'${term}'을(를) 관심 키워드로 추가했습니다.` : `'${term}'이(가) 들어간 기사는 추천하지 않습니다.`
  ).then((updated) => {
    if (updated && keywordInputNode) keywordInputNode.value = "";
  });
});

for (const listNode of [interestListNode, excludedListNode]) {
  listNode?.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;

    const term = button.dataset.term || "";
    if (button.dataset.action === "include-keyword") {
      void updateProfile(MESSAGE_TYPES.SET_KEYWORD_PREFERENCE, { term, preference: "include" }, `'${term}'을(를) 관심 키워드로 고정했습니다.`);
    } else if (button.dataset.action === "exclude-keyword") {
      void updateProfile(MESSAGE_TYPES.SET_KEYWORD_PREFERENCE, { term, preference: "exclude" }, `'${term}'을(를) 추천에서 제외합니다.`);
    } else if (button.dataset.action === "remove-keyword") {
      void updateProfile(MESSAGE_TYPES.DELETE_KEYWORD_PREFERENCE, { term }, `'${term}' 설정을 해제했습니다.`);
    }
  });
}

adFilterNode?.addEventListener("change", () => {
  const threshold = Number(adFilterNode.value);
  void updateProfile(
    MESSAGE_TYPES.UPDATE_SETTINGS,
    { adFilterThreshold: threshold },
    threshold >= 1 ? "광고성 기사도 추천에 포함합니다." : `광고 확률 ${Math.round(threshold * 100)}% 이상인 기사는 추천하지 않습니다.`
  );
});

historyListNode?.addEventListener("click", (event) => {
  const button = event.target.closest('button[data-action="delete-history"]');
  if (!button) return;

  button.disabled = true;
  void sendPersonalization(MESSAGE_TYPES.DELETE_HISTORY, { newsId: Number(button.dataset.newsId) })
    .then(() => loadPersonalization())
    .catch((error) => {
      button.disabled = false;
      historyCaptionNode.textContent = error.message;
    });
});

async function initialize() {
  const activeTab = await getActiveTab();
  // Passing the tab makes the worker mirror this window's active tab before the mirror is read.
  const [response, authResponse, stored] = await Promise.all([
    chrome.runtime.sendMessage({
      type: MESSAGE_TYPES.GET_LATEST_ANALYSIS,
      payload: { tabId: activeTab?.id }
    }),
    chrome.runtime.sendMessage({
      type: MESSAGE_TYPES.GET_AUTH_STATE
    }),
    chrome.storage.local.get([THEME_STORAGE_KEY, MOTION_STORAGE_KEY, OVERLAY_STATE_STORAGE_KEY])
  ]);

  latestOpenOverlays = stored[OVERLAY_STATE_STORAGE_KEY] || {};
  applyTheme(stored[THEME_STORAGE_KEY] || "light");
  applyMotion(stored[MOTION_STORAGE_KEY]);
  const auth = authResponse?.result || DEFAULT_AUTH;
  renderAuth(auth);
  if (!auth.token) void playWelcome();
  render(response?.result || DEFAULT_ANALYSIS);
  void renderSitePermissions();
}

function render(analysis) {
  const normalizedAnalysis = expireStaleLoading({
    ...DEFAULT_ANALYSIS,
    ...analysis
  });

  latestAnalysis = normalizedAnalysis;
  scheduleStaleLoadingCheck(normalizedAnalysis);
  renderAnalysisStatus(normalizedAnalysis);
  renderTrustNote(normalizedAnalysis);
  renderGlobalActions(normalizedAnalysis);
  renderKeywords(normalizedAnalysis);
  renderChart(normalizedAnalysis);
  renderSummary(normalizedAnalysis);
  renderRecommendations(normalizedAnalysis);
  renderNaverSearch(normalizedAnalysis);
  renderAdLikelihood(normalizedAnalysis);
}

function scheduleStaleLoadingCheck(analysis) {
  window.clearTimeout(staleLoadingTimer);
  if (analysis.status !== ANALYSIS_STATUS.LOADING) return;
  const elapsed = Date.now() - Date.parse(analysis.startedAt || "");
  staleLoadingTimer = window.setTimeout(() => render(latestAnalysis), Math.max(STALE_LOADING_MS - elapsed, 0) + 500);
}

function renderAnalysisStatus(analysis) {
  if (analyzeMascotNode) {
    analyzeMascotNode.dataset.state = analysis.status;
  }
  if (analyzeButton) {
    analyzeButton.disabled = analysis.status === ANALYSIS_STATUS.LOADING;
  }
  if (!analysisMessage) return;

  // Re-renders for overlay or auth changes must not wipe a message the user is still reading.
  const key = `${analysis.status}|${analysis.updatedAt || ""}|${analysis.error || ""}`;
  if (key === lastAnalysisMessageKey) return;
  lastAnalysisMessageKey = key;

  if (analysis.status === ANALYSIS_STATUS.LOADING) {
    analysisMessage.textContent = "기사 본문을 추출하고 분석하는 중입니다.";
  } else if (analysis.status === ANALYSIS_STATUS.ERROR) {
    analysisMessage.textContent = analysis.error || "분석 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.";
  } else if (analysis.status === ANALYSIS_STATUS.READY) {
    analysisMessage.textContent = analysis.cached ? "저장된 분석 결과를 불러왔습니다." : "분석이 완료되었습니다.";
  } else {
    analysisMessage.textContent = "";
  }
}

function renderTrustNote(analysis) {
  if (!trustNoteNode) return;
  const visible =
    analysis.status === ANALYSIS_STATUS.READY &&
    Boolean(analysis.sharedFromOther || analysis.reportedByMe || analysis.reanalysis);
  trustNoteNode.hidden = !visible;
  if (!visible) {
    setReportFormOpen(false);
    return;
  }

  trustTextNode.textContent =
    analysis.contentOrigin === "bigkinds"
      ? "빅카인즈 기사 정보로 분석한 결과입니다. 지금 보고 있는 기사와 다를 수 있습니다."
      : "다른 사용자가 먼저 분석한 결과입니다. 지금 보고 있는 기사와 다를 수 있습니다.";

  const hasNewsId = Number.isInteger(analysis.newsId);
  const canReport = hasNewsId && !analysis.reportedByMe && !analysis.reanalysis;
  reportToggleNode.hidden = !hasNewsId;
  reportToggleNode.disabled = !canReport;
  reportToggleNode.textContent = analysis.reportedByMe ? "신고 완료" : "내용이 다르면 신고";
  if (!canReport) setReportFormOpen(false);

  if (analysis.reanalysis) {
    setNodeMessage(reportMessageNode, "신고가 누적되어 다시 분석할 수 있습니다.", "success");
  } else if (analysis.reportedByMe) {
    const count = Math.min(Math.max(Number(analysis.reportCount) || 1, 1), REPORT_THRESHOLD);
    setNodeMessage(reportMessageNode, `신고되었습니다 (${count}/${REPORT_THRESHOLD})`, "success");
  } else if (!reportMessageNode.classList.contains("error")) {
    setNodeMessage(reportMessageNode, "");
  }
  reanalyzeNode.hidden = !analysis.reanalysis;
}

function setReportFormOpen(isOpen) {
  if (!reportFormNode) return;
  reportFormNode.hidden = !isOpen;
  reportToggleNode?.setAttribute("aria-expanded", String(isOpen));
  if (isOpen) {
    reportReasonNode?.focus();
  } else if (reportReasonNode) {
    reportReasonNode.value = "";
  }
}

async function submitReport() {
  const { newsId } = latestAnalysis;
  if (!Number.isInteger(newsId)) return;

  reportSubmitNode.disabled = true;
  setNodeMessage(reportMessageNode, "신고를 보내는 중입니다.");
  try {
    // The worker stores reportCount/reportedByMe on the tab's analysis, and the storage change re-renders this note.
    await sendPersonalization(MESSAGE_TYPES.REPORT_NEWS, {
      newsId,
      reason: reportReasonNode?.value.trim().slice(0, 300) || ""
    });
    setReportFormOpen(false);
  } catch (error) {
    setNodeMessage(reportMessageNode, error.message, "error");
  } finally {
    reportSubmitNode.disabled = false;
  }
}

async function analyzeCurrentArticle() {
  if (analyzeButton) analyzeButton.disabled = true;
  analysisMessage.textContent = "기사 본문을 추출하고 분석하는 중입니다.";
  try {
    const tab = await getActiveTab();
    if (!isSupportedArticleUrl(tab?.url)) throw new Error("웹 기사 페이지에서 실행해 주세요.");
    const origin = `${new URL(tab.url).origin}/*`;
    const granted = await chrome.permissions.request({ origins: [origin] });
    if (!granted) throw new Error("이 사이트의 본문을 읽으려면 접근 권한이 필요합니다.");
    const response = await chrome.runtime.sendMessage({
      type: MESSAGE_TYPES.ANALYZE_ACTIVE_TAB,
      payload: { tabId: tab.id }
    });
    if (!response?.ok) {
      if (response?.authExpired) noteAuthExpired(response.error);
      throw new Error(response?.error || "분석에 실패했습니다.");
    }
  } catch (error) {
    analysisMessage.textContent = error.message;
  } finally {
    if (analyzeButton) analyzeButton.disabled = latestAnalysis.status === ANALYSIS_STATUS.LOADING;
  }
}

function noteAuthExpired(message) {
  authNotice = message || "로그인이 만료되었습니다. 다시 로그인해 주세요.";
  setAuthMessage(authNotice, "error");
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab || null;
}

function renderAuth(auth) {
  const normalizedAuth = {
    ...DEFAULT_AUTH,
    ...auth
  };
  const wasSignedIn = Boolean(latestAuth.token);
  const isSignedIn = Boolean(normalizedAuth.token);
  latestAuth = normalizedAuth;
  const userLabel =
    normalizedAuth.user?.name ||
    normalizedAuth.user?.email ||
    normalizedAuth.user?.id ||
    "로그인한 사용자";

  if (authStatusNode) {
    authStatusNode.textContent = isSignedIn
      ? `${userLabel} 계정으로 로그인됨`
      : "";
  }

  if (greetingNode) {
    const name = String(normalizedAuth.user?.name || normalizedAuth.user?.email || "").split("@")[0];
    greetingNode.textContent = isSignedIn && name ? `안녕하세요, ${name}님` : "";
  }

  document.body.dataset.auth = isSignedIn ? "signed-in" : "signed-out";
  placeSharedSettings(isSignedIn);

  if (analysisContentNode) {
    analysisContentNode.hidden = !isSignedIn;
  }

  if (authFormNode) {
    authFormNode.hidden = isSignedIn;
  }

  if (logoutButtonNode) {
    logoutButtonNode.hidden = !isSignedIn;
  }

  if (deleteAccountNode && !isSignedIn) {
    deleteAccountNode.open = false;
    deleteAccountFormNode?.reset();
    if (deleteAccountMessageNode) deleteAccountMessageNode.textContent = "";
  }
  if (deleteAccountNode) {
    deleteAccountNode.hidden = !isSignedIn;
  }

  if (changePasswordNode) {
    changePasswordNode.hidden = !isSignedIn;
    if (!isSignedIn) {
      changePasswordNode.open = false;
      changePasswordFormNode?.reset();
      setNodeMessage(changePasswordMessageNode, "");
    }
  }

  if (accountToolsNode) {
    accountToolsNode.hidden = !isSignedIn;
    if (!isSignedIn) setNodeMessage(exportMessageNode, "");
  }

  if (!isSignedIn) {
    // The storage listener re-renders after sign-out; resetting again would wipe the result message.
    if (wasSignedIn) {
      setAuthMode("login");
      if (authNotice) setAuthMessage(authNotice, "error");
      void playWelcome();
    }
    clearPersonalization();
  } else if (!wasSignedIn) {
    authNotice = "";
    void loadPersonalization();
  }

  render(latestAnalysis);
}

function setAuthMode(mode) {
  authMode = mode === "signup" ? "signup" : "login";
  loginModeNode?.classList.toggle("active", authMode === "login");
  signupModeNode?.classList.toggle("active", authMode === "signup");
  loginModeNode?.setAttribute("aria-selected", String(authMode === "login"));
  signupModeNode?.setAttribute("aria-selected", String(authMode === "signup"));

  if (authSubmitNode) {
    authSubmitNode.textContent = authMode === "login" ? "로그인" : "다음";
  }

  if (passwordHintNode) {
    passwordHintNode.hidden = authMode !== "signup";
  }

  if (authPasswordNode) {
    authPasswordNode.autocomplete =
      authMode === "login" ? "current-password" : "new-password";
  }

  if (inviteFieldNode) {
    inviteFieldNode.hidden = authMode !== "signup";
  }

  setSignupStep(1, { animate: false });
  setAuthMessage("");
}

function setSignupStep(step, { animate = true } = {}) {
  const isSignup = authMode === "signup";
  const previous = signupStep;
  signupStep = isSignup ? step : 1;

  if (signupStepsNode) {
    signupStepsNode.hidden = !isSignup;
    for (const item of signupStepsNode.querySelectorAll("li")) {
      const number = Number(item.dataset.step);
      item.classList.toggle("current", number === signupStep);
      item.classList.toggle("done", number < signupStep);
    }
  }

  const showInterests = isSignup && signupStep === 2;
  if (authFieldsNode) authFieldsNode.hidden = showInterests;
  if (interestStepNode) interestStepNode.hidden = !showInterests;
  if (animate && previous !== signupStep) {
    restartAnimation(showInterests ? interestStepNode : authFieldsNode, "entering");
  }
  if (showInterests) signupTopicsNode?.querySelector(".topic-chip")?.focus();
}

function addSignupKeyword(value) {
  const term = value.trim().replace(/,+$/, "").trim();
  if (signupKeywordNode) signupKeywordNode.value = "";
  if (!term || signupKeywords.includes(term)) return;
  if (signupKeywords.length >= MAX_INITIAL_KEYWORDS) {
    setAuthMessage(`관심 키워드는 ${MAX_INITIAL_KEYWORDS}개까지 넣을 수 있습니다.`, "error");
    return;
  }
  signupKeywords = [...signupKeywords, term.slice(0, 50)];
  renderSignupKeywords();
}

function renderSignupKeywords() {
  if (!signupKeywordTagsNode) return;
  signupKeywordTagsNode.replaceChildren(
    ...signupKeywords.map((term, index) => {
      const tag = document.createElement("span");
      tag.className = "tag";
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "pill-button";
      remove.dataset.index = String(index);
      remove.textContent = "×";
      remove.setAttribute("aria-label", `${term} 빼기`);
      tag.append(term, remove);
      return tag;
    })
  );
}

function resetSignupInterests() {
  signupKeywords = [];
  renderSignupKeywords();
  for (const chip of signupTopicsNode?.querySelectorAll(".topic-chip") || []) {
    chip.setAttribute("aria-pressed", "false");
  }
}

function renderTopicChips(container) {
  if (!container) return;
  container.replaceChildren(
    ...INTEREST_TOPICS.map((topic) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "topic-chip";
      chip.dataset.topic = topic.code;
      chip.setAttribute("aria-pressed", "false");
      const icon = document.createElement("span");
      icon.className = "topic-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = topic.icon;
      chip.append(icon, topic.label);
      return chip;
    })
  );
}

function selectedTopics(container) {
  return [...(container?.querySelectorAll('.topic-chip[aria-pressed="true"]') || [])].map((chip) => chip.dataset.topic);
}

function selectTab(name) {
  for (const button of tabButtonNodes) {
    const active = button.dataset.tab === name;
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  }
  for (const panel of tabPanelNodes) {
    const active = panel.dataset.panel === name;
    if (active && panel.hidden) {
      panel.hidden = false;
      restartAnimation(panel, "entering");
    } else if (!active) {
      panel.hidden = true;
    }
  }
}

function restartAnimation(node, className) {
  if (!node) return;
  node.classList.remove(className);
  void node.offsetWidth; // reflow so the same animation runs again
  node.classList.add(className);
}

// The server and display settings are needed both before sign-in (auth footer) and after (settings tab).
function placeSharedSettings(isSignedIn) {
  const side = isSignedIn ? "in" : "out";
  for (const [node, slot] of [[displaySettingsNode, "display"], [serverSettingsNode, "server"]]) {
    const target = document.querySelector(`[data-slot="${slot}-${side}"]`);
    if (node && target && node.parentNode !== target) target.appendChild(node);
  }
}

function motionEnabled() {
  return document.documentElement.dataset.motion !== "off";
}

function applyMotion(preference) {
  const enabled = preference
    ? preference === "on"
    : !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.documentElement.dataset.motion = enabled ? "on" : "off";
  if (motionToggleNode) motionToggleNode.checked = enabled;
}

async function playWelcome() {
  if (!welcomeNode || !bubbleNode) return;
  const run = ++welcomeRun;
  const stored = await chrome.storage.local.get(GREETED_STORAGE_KEY).catch(() => ({}));
  if (run !== welcomeRun) return;

  const firstVisit = !stored[GREETED_STORAGE_KEY];
  const line = firstVisit ? "저는 기사를 함께 읽는 딥이예요." : "다시 만나서 반가워요.";
  const instant = !motionEnabled();

  restartAnimation(welcomeNode, "play");
  bubbleHelloNode.textContent = "";
  bubbleLineNode.textContent = "";
  if (!instant) await wait(650);
  if (run !== welcomeRun) return;

  bubbleNode.dataset.typing = "hello";
  if (!(await typeText(bubbleHelloNode, "안녕하세요!", { instant, delay: 90 }))) return;
  if (!instant) await wait(350);
  if (run !== welcomeRun) return;
  bubbleNode.dataset.typing = "line";
  if (!(await typeText(bubbleLineNode, line, { instant, delay: 45 }))) return;
  bubbleNode.dataset.typing = "";
  if (firstVisit) await chrome.storage.local.set({ [GREETED_STORAGE_KEY]: true });
}

async function submitAuthForm() {
  const email = authEmailNode?.value.trim() || "";
  const password = authPasswordNode?.value || "";

  if (!email || !password) {
    setAuthMessage("이메일과 비밀번호를 입력해 주세요.", "error");
    return;
  }

  const isSignup = authMode === "signup";
  if (isSignup && signupStep === 1) {
    if (!authEmailNode.checkValidity()) {
      setAuthMessage("올바른 이메일 주소를 입력해 주세요.", "error");
      return;
    }
    if (password.length < 8 || password.length > 128) {
      setAuthMessage("비밀번호는 8자 이상 128자 이하로 정해 주세요.", "error");
      return;
    }
    setAuthMessage("");
    setSignupStep(2);
    return;
  }
  if (isSignup && signupKeywordNode?.value.trim()) addSignupKeyword(signupKeywordNode.value);

  setAuthPending(true);
  setAuthMessage(
    authMode === "login" ? "로그인 중입니다." : "회원가입을 진행하는 중입니다."
  );

  const response = await chrome.runtime.sendMessage({
    type: authMode === "login" ? MESSAGE_TYPES.LOGIN : MESSAGE_TYPES.SIGNUP,
    payload: {
      email,
      password,
      inviteCode: isSignup ? authInviteNode?.value.trim() || "" : "",
      topics: isSignup ? selectedTopics(signupTopicsNode) : [],
      keywords: isSignup ? signupKeywords : []
    }
  });

  setAuthPending(false);

  if (!response?.ok) {
    // Taken e-mail, wrong invite code and the like belong to the account step; chosen interests are kept.
    if (isSignup) setSignupStep(1);
    setAuthMessage(
      response?.error ||
        "인증 요청에 실패했습니다. 백엔드 주소와 회원가입 API 응답 형식을 확인해 주세요.",
      "error"
    );
    return;
  }

  if (authPasswordNode) {
    authPasswordNode.value = "";
  }
  if (isSignup) {
    resetSignupInterests();
    setSignupStep(1, { animate: false });
  }
  renderAuth(response.result || DEFAULT_AUTH);
  // A new account lands on its first tailored feed, built from the interests just chosen.
  selectTab(isSignup ? "feed" : "analysis");
  setAuthMessage(isSignup ? "회원가입이 완료되었습니다." : "로그인되었습니다.", "success");
}

async function logout() {
  setAuthMessage("로그아웃 중입니다.");
  const response = await chrome.runtime.sendMessage({
    type: MESSAGE_TYPES.LOGOUT
  });

  if (!response?.ok) {
    setAuthMessage(response?.error || "로그아웃에 실패했습니다.", "error");
    return;
  }

  renderAuth(response.result || DEFAULT_AUTH);
  setAuthMessage("로그아웃되었습니다.", "success");
}

async function deleteAccount() {
  const password = deleteAccountPasswordNode?.value || "";
  if (!password) return;

  deleteAccountSubmitNode.disabled = true;
  deleteAccountMessageNode.className = "auth-message";
  deleteAccountMessageNode.textContent = "탈퇴를 처리하는 중입니다.";
  const response = await chrome.runtime.sendMessage({
    type: MESSAGE_TYPES.DELETE_ACCOUNT,
    payload: { password }
  });
  deleteAccountSubmitNode.disabled = false;

  if (!response?.ok) {
    deleteAccountMessageNode.className = "auth-message error";
    deleteAccountMessageNode.textContent = response?.error || "탈퇴에 실패했습니다.";
    return;
  }

  renderAuth(response.result || DEFAULT_AUTH);
  setAuthMessage("탈퇴가 완료되었습니다. 계정과 기록이 삭제되었습니다.", "success");
}

async function changePassword() {
  const currentPassword = currentPasswordNode?.value || "";
  const newPassword = newPasswordNode?.value || "";
  if (!currentPassword || !newPassword) return;
  if (newPassword.length < 8 || newPassword.length > 128) {
    setNodeMessage(changePasswordMessageNode, "새 비밀번호는 8자 이상 128자 이하로 입력해 주세요.", "error");
    return;
  }

  changePasswordSubmitNode.disabled = true;
  setNodeMessage(changePasswordMessageNode, "비밀번호를 변경하는 중입니다.");
  try {
    await sendPersonalization(MESSAGE_TYPES.CHANGE_PASSWORD, { currentPassword, newPassword });
    changePasswordFormNode?.reset();
    setNodeMessage(changePasswordMessageNode, "비밀번호가 변경되었습니다. 다른 기기의 로그인은 해제되었습니다.", "success");
  } catch (error) {
    // A wrong current password is a 403 and keeps this session signed in.
    setNodeMessage(changePasswordMessageNode, error.message, "error");
  } finally {
    changePasswordSubmitNode.disabled = false;
  }
}

async function exportMyData() {
  exportDataNode.disabled = true;
  setNodeMessage(exportMessageNode, "내 데이터를 준비하는 중입니다.");
  try {
    const data = await sendPersonalization(MESSAGE_TYPES.EXPORT_MY_DATA);
    const blob = new Blob([JSON.stringify(data ?? {}, null, 2)], { type: "application/json" });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = "deepnews-내데이터.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 10000);
    setNodeMessage(exportMessageNode, "파일을 내려받았습니다.", "success");
  } catch (error) {
    setNodeMessage(exportMessageNode, error.message, "error");
  } finally {
    exportDataNode.disabled = false;
  }
}

function setNodeMessage(node, message, tone = "") {
  if (!node) return;
  node.textContent = message;
  node.className = `auth-message ${tone}`.trim();
}

async function renderSitePermissions() {
  if (!permissionListNode) return;

  const manifestHosts = new Set(chrome.runtime.getManifest().host_permissions || []);
  let origins = [];
  try {
    origins = ((await chrome.permissions.getAll()).origins || []).filter((origin) => !manifestHosts.has(origin));
  } catch {
    origins = [];
  }

  permissionListNode.replaceChildren();
  if (!origins.length) {
    const empty = document.createElement("li");
    empty.className = "state-message";
    empty.textContent = "허용한 사이트가 없습니다.";
    permissionListNode.appendChild(empty);
    return;
  }

  for (const origin of origins.sort()) {
    const item = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = origin.replace(/\/\*$/, "");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pill-action";
    button.dataset.action = "revoke-origin";
    button.dataset.origin = origin;
    button.textContent = "해제";
    button.setAttribute("aria-label", `${label.textContent} 권한 해제`);
    item.append(label, button);
    permissionListNode.appendChild(item);
  }
}

function setAuthPending(isPending) {
  if (authSubmitNode) {
    authSubmitNode.disabled = isPending;
  }

  if (loginModeNode) {
    loginModeNode.disabled = isPending;
  }

  if (signupModeNode) {
    signupModeNode.disabled = isPending;
  }

  for (const node of [signupSubmitNode, signupBackNode]) {
    if (node) node.disabled = isPending;
  }
}

function setAuthMessage(message, tone = "") {
  if (!authMessageNode) {
    return;
  }

  authMessageNode.textContent = message;
  authMessageNode.className = `auth-message ${tone}`.trim();
}

function renderGlobalActions(analysis) {
  if (showAllPopupsNode) {
    showAllPopupsNode.disabled =
      !latestAuth.token || analysis.status !== ANALYSIS_STATUS.READY;
  }

  if (hideAllPopupsNode) {
    hideAllPopupsNode.disabled = !Object.values(latestOpenOverlays).some(Boolean);
  }
}

function renderKeywords(analysis) {
  const { keywords = [], status } = analysis;
  if (showKeywordPopupNode) {
    showKeywordPopupNode.disabled =
      !latestOpenOverlays.keywords && (status !== ANALYSIS_STATUS.READY || !keywords.length);
    setPopupButtonLabel(showKeywordPopupNode, latestOpenOverlays.keywords, "핵심 키워드");
  }

  if (status === ANALYSIS_STATUS.LOADING) {
    keywordListNode.innerHTML = '<p class="state-message">기사를 분석하고 있습니다.</p>';
    return;
  }

  if (!keywords.length) {
    keywordListNode.innerHTML = '<p class="state-message">아직 키워드가 없습니다.</p>';
    return;
  }

  keywordListNode.innerHTML = keywords
    .map((keyword) => `<mark class="hl">${escapeHtml(keyword.term)}</mark>`)
    .join("");
}

function renderChart(analysis) {
  const { keywords = [], status } = analysis;
  if (showKeywordChartPopupNode) {
    showKeywordChartPopupNode.disabled =
      !latestOpenOverlays.keywordChart && (status !== ANALYSIS_STATUS.READY || !keywords.length);
    setPopupButtonLabel(showKeywordChartPopupNode, latestOpenOverlays.keywordChart, "키워드 빈도");
  }

  if (status === ANALYSIS_STATUS.LOADING) {
    chartNode.innerHTML = '<p class="state-message">키워드 빈도를 계산하고 있습니다.</p>';
    return;
  }

  if (!keywords.length) {
    chartNode.innerHTML = '<p class="state-message">아직 표시할 빈도 데이터가 없습니다.</p>';
    return;
  }

  // Keywords arrive in importance order; the frequency chart reads better sorted by count (ties keep that order).
  const byCount = [...keywords].sort((a, b) => (Number(b.count) || 0) - (Number(a.count) || 0));
  const counts = byCount.map((keyword) => Math.max(Number(keyword.count) || 0, 0));
  const max = Math.max(...counts, 1);
  chartNode.innerHTML = byCount
    .map((keyword, index) => {
      const width = Math.round((counts[index] / max) * 100);
      return `
        <div class="bar-row">
          <span>${escapeHtml(keyword.term)}</span>
          <div class="bar-track"><div class="bar-fill" style="width: ${width}%"></div></div>
          <strong>${counts[index]}</strong>
        </div>
      `;
    })
    .join("");
}

function renderSummary(analysis) {
  const { summary = "", status } = analysis;
  if (showSummaryPopupNode) {
    showSummaryPopupNode.disabled =
      !latestOpenOverlays.summary && (status !== ANALYSIS_STATUS.READY || !summary);
    setPopupButtonLabel(showSummaryPopupNode, latestOpenOverlays.summary, "AI 요약");
  }

  if (status === ANALYSIS_STATUS.LOADING) {
    summaryNode.textContent = "기사 내용을 분석하고 있습니다.";
    return;
  }

  summaryNode.textContent = summary || "아직 요약이 없습니다.";
}

function renderRecommendations(analysis) {
  const { recommendations = [], status } = analysis;
  if (showRecommendationsPopupNode) {
    showRecommendationsPopupNode.disabled =
      !latestOpenOverlays.recommendations &&
      (status !== ANALYSIS_STATUS.READY || !recommendations.length);
    setPopupButtonLabel(showRecommendationsPopupNode, latestOpenOverlays.recommendations, "추천 기사");
  }

  if (status === ANALYSIS_STATUS.LOADING || analysis.recommendationsPending) {
    recommendationsNode.innerHTML = '<li class="state-message">관련 기사를 찾고 있습니다.</li>';
    return;
  }

  if (!recommendations.length) {
    recommendationsNode.innerHTML = '<li class="state-message">아직 추천 기사가 없습니다.</li>';
    return;
  }

  recommendationsNode.innerHTML = groupByPublisher(recommendations)
    .map(([publisher, items]) => `<li class="publisher-group"><h3>${escapeHtml(publisher)}</h3>
      <ul class="article-list">${renderArticleItems(items)}</ul></li>`)
    .join("");
}

// Groups follow each publisher's best-ranked article, and items keep their rank inside a group.
function groupByPublisher(items) {
  const groups = new Map();
  for (const item of items) {
    const publisher = item.publisher || publisherFromUrl(item.url);
    if (!groups.has(publisher)) groups.set(publisher, []);
    groups.get(publisher).push(item);
  }
  return [...groups];
}

function publisherFromUrl(url) {
  if (isNaverUrl(url)) return "네이버뉴스";
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch { return "기타"; }
}

function renderArticleItems(items) {
  return items
    .map((item) => {
      const reasons = (Array.isArray(item.reasons) ? item.reasons : []).map((reason) => `<span>${escapeHtml(reason)}</span>`).join("");
      const badge = adBadge(item.adProbability);
      const meta = reasons || badge ? `<div class="rec-meta">${reasons}${badge}</div>` : "";
      return `<li><a href="${safeHref(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>${meta}</li>`;
    })
    .join("");
}

function safeHref(url) {
  // Stored article URLs are data; only http(s) links may become clickable.
  return isSupportedArticleUrl(url) ? escapeHtml(url) : "#";
}

function adBadge(adProbability) {
  // Matches the backend "검토 필요" boundary (ad_label_for >= 0.4).
  if (!Number.isFinite(adProbability) || adProbability < 0.4) return "";
  return `<span class="ad-badge">광고성 ${Math.round(adProbability * 100)}%</span>`;
}

const NAVER_INTEREST_LISTS = 3;

function articleTerms(analysis, count = 3) {
  return analysis.keywords.slice(0, count).map((keyword) => keyword.term);
}

function renderNaverSearch(analysis) {
  const articleUrl = analysis.article?.url || "";
  const onNaver = isNaverUrl(articleUrl);
  // The NAVER search section and its notice appear only while a 네이버 뉴스 article is open.
  naverBlockNode.hidden = !onNaver;
  recommendationsBlockNode.hidden = onNaver && !analysis.recommendations.length && !analysis.recommendationsPending;
  const ready = onNaver && analysis.status === ANALYSIS_STATUS.READY && articleTerms(analysis).length > 0;
  naverSearchNode.disabled = !ready;
  if (articleUrl === naverResultsUrl) return;

  naverResultsUrl = "";
  naverRequestId += 1;
  naverResultsNode.replaceChildren();
  naverSearchCaptionNode.textContent = "기사를 분석하면 핵심 키워드와 관심 키워드로 네이버 뉴스를 검색합니다.";
  if (ready && latestAuth.token) void searchNaverNews();
}

// Personalization only shapes the queries; every list is shown exactly as NAVER returns it (특약 2.2, 2.3).
async function searchNaverNews() {
  const keywords = articleTerms(latestAnalysis);
  if (!keywords.length) return;
  const requestId = ++naverRequestId;
  // Claimed up front so re-renders during the request do not start another search for the same article.
  naverResultsUrl = latestAnalysis.article?.url || "";
  naverSearchNode.disabled = true;
  naverSearchCaptionNode.textContent = "네이버 뉴스를 검색하고 있습니다.";
  try {
    const profile = await sendPersonalization(MESSAGE_TYPES.GET_PROFILE).catch(() => null);
    const interests = interestTerms(profile, keywords);
    const lead = interests[0];
    let query = lead ? [...keywords.slice(0, 2), lead].join(" ") : keywords.join(" ");
    let items = await searchNaver(query, "sim", 5);
    if (!items.length && lead) {
      // The interest made the query too narrow; search the article's own keywords instead.
      query = keywords.join(" ");
      items = await searchNaver(query, "sim", 5);
    }
    const groups = [{ title: lead && query.endsWith(lead) ? `이 기사 + 관심 키워드 '${lead}'` : "이 기사 관련 뉴스", query, items }];
    const interestGroups = await Promise.all(
      interests.slice(0, NAVER_INTEREST_LISTS).map((term) =>
        searchNaver(term, "date", 3)
          .then((found) => ({ title: `관심 키워드 '${term}' 최신 뉴스`, query: term, items: found }))
          .catch(() => null)
      )
    );
    groups.push(...interestGroups.filter(Boolean));
    if (requestId !== naverRequestId) return;
    naverSearchCaptionNode.textContent = interests.length
      ? "관심 키워드를 넣은 검색어로 찾았습니다."
      : "맞춤 탭에서 관심 키워드나 관심 분야를 정하면 관심사별 뉴스도 함께 찾아 드립니다.";
    naverResultsNode.innerHTML = groups.map(renderNaverGroup).join("");
  } catch (error) {
    if (requestId === naverRequestId) naverSearchCaptionNode.textContent = error.message;
  } finally {
    if (requestId === naverRequestId) naverSearchNode.disabled = false;
  }
}

async function searchNaver(query, sort, display) {
  const result = await sendPersonalization(MESSAGE_TYPES.SEARCH_NAVER_NEWS, { query, sort, display });
  return result?.items || [];
}

// Manual interest keywords first, then ones learned from reading, then chosen topics as a fallback.
function interestTerms(profile, articleKeywords) {
  const topicLabels = (profile?.topics || []).map(
    (code) => INTEREST_TOPICS.find((topic) => topic.code === code)?.label || code
  );
  const terms = [...(profile?.interests || []).map((interest) => interest.term), ...topicLabels];
  return [...new Set(terms)].filter((term) => term && !articleKeywords.includes(term));
}

function renderNaverGroup(group) {
  const items = group.items.length
    ? group.items.map(renderNaverItem).join("")
    : '<li class="state-message">검색 결과가 없습니다.</li>';
  return `<section class="naver-group"><h3>${escapeHtml(group.title)}</h3>
    <p>검색어: ${escapeHtml(group.query)}</p><ul class="article-list">${items}</ul></section>`;
}

function renderNaverItem(item) {
  const date = formatReadAt(item.publishedAt);
  // Opens inside 네이버 뉴스 when NAVER hosts the article; the original source stays linked (특약 2.2).
  const href = isNaverUrl(item.naverUrl) ? item.naverUrl : item.url;
  const original = href !== item.url
    ? `<a href="${safeHref(item.url)}" target="_blank" rel="noreferrer">원문</a>`
    : "";
  return `<li><a href="${safeHref(href)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>
    <p>${escapeHtml(item.description)}</p>
    <div class="rec-meta"><span>출처 ${escapeHtml(item.source)}</span>${date ? `<span>${escapeHtml(date)}</span>` : ""}${original}</div></li>`;
}

async function sendPersonalization(type, payload = {}) {
  const response = await chrome.runtime.sendMessage({ type, payload });
  if (!response?.ok) {
    if (response?.authExpired) noteAuthExpired(response.error);
    throw new Error(response?.error || "요청에 실패했습니다.");
  }
  return response.result;
}

function setPopupButtonLabel(button, isOpen, sectionName) {
  const text = isOpen ? "팝업 닫기" : "팝업 띄우기";
  button.textContent = text;
  button.setAttribute("aria-label", `${sectionName} ${text}`);
}

function describeAdScore(adLikelihood) {
  const score = Number(adLikelihood?.score);
  if (!Number.isFinite(score) || score < 0) {
    return { text: "미분석", toneClass: "score-none" };
  }

  // Same bands as the backend ad_label_for: >=0.8 high, >=0.4 needs review.
  const toneClass = score >= 0.8 ? "score-high" : score >= 0.4 ? "score-warn" : "score-good";
  const percent = `${Math.round(Math.min(score, 1) * 100)}%`;
  return { text: adLikelihood?.label ? `${adLikelihood.label} (${percent})` : percent, toneClass };
}

async function loadPersonalization() {
  if (!latestAuth.token) return;
  await Promise.all([loadProfile(), loadHistory(), loadFeed()]);
}

function clearPersonalization() {
  for (const node of [feedNode, interestListNode, excludedListNode, historyListNode]) {
    if (node) node.innerHTML = "";
  }
  for (const node of [profileCaptionNode, historyCaptionNode, topicCaptionNode]) {
    if (node) node.textContent = "";
  }
  for (const chip of profileTopicsNode?.querySelectorAll(".topic-chip") || []) {
    chip.setAttribute("aria-pressed", "false");
  }
  if (topicStrengthNode) topicStrengthNode.hidden = true;
  setProfileMessage("");
  setNodeMessage(topicMessageNode, "");
}

async function loadFeed() {
  if (!feedNode) return;
  const requestId = ++feedRequestId;
  feedNode.innerHTML = '<li class="state-message">맞춤 기사를 고르는 중입니다.</li>';
  try {
    const items = await sendPersonalization(MESSAGE_TYPES.GET_FEED, { limit: 8 });
    if (requestId !== feedRequestId) return;
    feedNode.innerHTML = items?.length
      ? renderArticleItems(items)
      : '<li class="state-message">추천할 기사가 아직 없습니다.</li>';
  } catch (error) {
    if (requestId !== feedRequestId) return;
    feedNode.innerHTML = `<li class="state-message">${escapeHtml(error.message)}</li>`;
  }
}

async function loadProfile() {
  try {
    renderProfile(await sendPersonalization(MESSAGE_TYPES.GET_PROFILE));
  } catch (error) {
    setProfileMessage(error.message, "error");
  }
}

async function updateProfile(type, payload, successMessage, messageNode = profileMessageNode) {
  setProfilePending(true);
  try {
    renderProfile(await sendPersonalization(type, payload));
    setNodeMessage(messageNode, successMessage, "success");
    void loadFeed();
    return true;
  } catch (error) {
    setNodeMessage(messageNode, error.message, "error");
    return false;
  } finally {
    setProfilePending(false);
  }
}

function renderProfile(profile) {
  const interests = profile?.interests || [];
  const excluded = profile?.excluded || [];
  renderTopics(profile);

  if (profileCaptionNode) {
    profileCaptionNode.textContent = profile?.historyCount
      ? `읽은 기사 ${profile.historyCount}건에서 찾은 관심사입니다. ＋는 고정, －는 추천 제외입니다.`
      : "기사를 분석하면 관심사가 자동으로 쌓입니다. 직접 추가할 수도 있습니다.";
  }

  if (interestListNode) {
    interestListNode.innerHTML = interests.length
      ? interests.map(renderInterestPill).join("")
      : '<p class="state-message">아직 관심 키워드가 없습니다.</p>';
  }

  if (excludedListNode) {
    excludedListNode.innerHTML = excluded.length
      ? excluded
          .map((term) => {
            const safeTerm = escapeHtml(term);
            return `<span class="keyword-pill excluded">${safeTerm}${pillButton("remove-keyword", term, "×", `${term} 제외 해제`)}</span>`;
          })
          .join("")
      : '<p class="state-message">제외한 키워드가 없습니다.</p>';
  }

  if (adFilterNode && Number.isFinite(profile?.adFilterThreshold)) {
    const value = String(Number(profile.adFilterThreshold));
    if (![...adFilterNode.options].some((option) => option.value === value)) {
      adFilterNode.add(new Option(`광고 확률 ${Math.round(Number(value) * 100)}% 이상`, value));
    }
    adFilterNode.value = value;
  }
}

function renderTopics(profile) {
  const topics = new Set(profile?.topics || []);
  for (const chip of profileTopicsNode?.querySelectorAll(".topic-chip") || []) {
    chip.setAttribute("aria-pressed", String(topics.has(chip.dataset.topic)));
  }

  if (topicCaptionNode) {
    topicCaptionNode.textContent = topics.size
      ? "고른 분야의 기사를 맞춤 기사에 더 자주 넣습니다. 누르면 바로 바뀝니다."
      : "관심 분야를 고르면 읽은 기사가 없어도 맞춤 기사를 바로 받아 볼 수 있어요.";
  }

  if (!topicStrengthNode) return;
  topicStrengthNode.hidden = !topics.size;
  // Mirrors ranking.topic_strength: full for a new account, fading toward 30% as reads accumulate.
  const weight = Math.min(Math.max(Number(profile?.topicWeight) || 0, 0), 1);
  topicStrengthLabelNode.textContent =
    weight >= 0.7
      ? "관심 분야 반영 높음: 읽은 기사가 쌓이면 점점 읽은 기사 위주로 바뀝니다."
      : weight >= 0.45
        ? "관심 분야 반영 보통: 읽은 기사와 관심 분야를 함께 봅니다."
        : "관심 분야 반영 낮음: 주로 읽은 기사를 보고 추천합니다.";
  topicStrengthFillNode.style.width = `${Math.round(weight * 100)}%`;
}

function renderInterestPill(interest) {
  const term = interest.term;
  if (interest.source === "manual") {
    return `<span class="keyword-pill interest manual" title="직접 추가한 관심 키워드">★ ${escapeHtml(term)}${pillButton("remove-keyword", term, "×", `${term} 관심 해제`)}</span>`;
  }

  const weight = Math.min(Math.max(Number(interest.weight) || 0, 0), 1);
  return `<span class="keyword-pill interest" style="--weight: ${weight}" title="읽은 기사에서 찾은 관심사 (강도 ${Math.round(weight * 100)}%)">${escapeHtml(term)}${pillButton("include-keyword", term, "＋", `${term} 관심 키워드로 고정`)}${pillButton("exclude-keyword", term, "－", `${term} 추천에서 제외`)}</span>`;
}

function pillButton(action, term, label, description) {
  return `<button class="pill-button" type="button" data-action="${action}" data-term="${escapeHtml(term)}" title="${escapeHtml(description)}" aria-label="${escapeHtml(description)}">${label}</button>`;
}

function setProfilePending(isPending) {
  for (const node of [
    ...(keywordFormNode?.querySelectorAll("button") || []),
    ...(profileTopicsNode?.querySelectorAll(".topic-chip") || []),
    adFilterNode
  ]) {
    if (node) node.disabled = isPending;
  }
}

function setProfileMessage(message, tone = "") {
  if (!profileMessageNode) return;
  profileMessageNode.textContent = message;
  profileMessageNode.className = `auth-message ${tone}`.trim();
}

async function loadHistory() {
  try {
    renderHistory(await sendPersonalization(MESSAGE_TYPES.GET_HISTORY, { limit: 20 }));
  } catch (error) {
    if (historyCaptionNode) historyCaptionNode.textContent = error.message;
  }
}

function renderHistory(history) {
  const items = history?.items || [];
  const total = history?.total || 0;

  if (historyCaptionNode) {
    historyCaptionNode.textContent = total
      ? `최근 읽은 순 · 전체 ${total}건${total > items.length ? ` 중 ${items.length}건` : ""}. 삭제하면 관심사에서도 빠집니다.`
      : "";
  }

  if (!historyListNode) return;
  historyListNode.innerHTML = items.length
    ? items
        .map((item) => {
          const readCount = Number(item.readCount) > 1 ? `<span>${Number(item.readCount)}회 읽음</span>` : "";
          return `
            <li>
              <div>
                <a href="${safeHref(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>
                <div class="rec-meta"><span>${escapeHtml(formatReadAt(item.lastReadAt))}</span>${readCount}${adBadge(item.adProbability)}</div>
              </div>
              <button class="pill-button" type="button" data-action="delete-history" data-news-id="${Number(item.newsId)}" title="읽은 기록 삭제" aria-label="읽은 기록 삭제">×</button>
            </li>
          `;
        })
        .join("")
    : '<li class="state-message">아직 읽은 기사가 없습니다. 기사를 분석하면 기록됩니다.</li>';
}

function formatReadAt(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function renderAdLikelihood(analysis) {
  const { adLikelihood, status } = analysis;
  if (showAdPopupNode) {
    showAdPopupNode.disabled =
      !latestOpenOverlays.adLikelihood && (status !== ANALYSIS_STATUS.READY || !adLikelihood);
    setPopupButtonLabel(showAdPopupNode, latestOpenOverlays.adLikelihood, "광고성 판단");
  }

  if (status === ANALYSIS_STATUS.LOADING) {
    adLikelihoodNode.className = "ad-likelihood";
    adLikelihoodNode.textContent = "광고성을 확인하고 있습니다.";
    setAdMeter(0, "");
    return;
  }

  const view = status === ANALYSIS_STATUS.READY ? describeAdScore(adLikelihood) : describeAdScore(null);
  adLikelihoodNode.className = `ad-likelihood ${view.toneClass}`;
  adLikelihoodNode.textContent = view.text;
  const score = Number(adLikelihood?.score);
  const known = status === ANALYSIS_STATUS.READY && Number.isFinite(score) && score >= 0;
  // A sliver stays visible at 0% so "analyzed, not an ad" differs from "not analyzed".
  setAdMeter(known ? Math.max(Math.min(score, 1), 0.03) : 0, known ? view.toneClass : "");
}

function setAdMeter(ratio, toneClass) {
  if (!adMeterFillNode) return;
  adMeterFillNode.style.width = `${Math.round(ratio * 100)}%`;
  adMeterFillNode.className = toneClass;
}

async function showAdLikelihoodPopup() {
  if (latestOpenOverlays.adLikelihood) {
    await closeOverlay("adLikelihood");
    return;
  }

  if (
    !latestAuth.token ||
    latestAnalysis.status !== ANALYSIS_STATUS.READY ||
    !latestAnalysis.adLikelihood
  ) {
    return;
  }

  await setOpenOverlayState({ adLikelihood: true });
  await sendActiveTabMessage({
    type: MESSAGE_TYPES.SHOW_AD_LIKELIHOOD,
    payload: {
      adLikelihood: latestAnalysis.adLikelihood
    }
  });
}

async function showKeywordPopup() {
  if (latestOpenOverlays.keywords) {
    await closeOverlay("keywords");
    return;
  }

  if (
    !latestAuth.token ||
    latestAnalysis.status !== ANALYSIS_STATUS.READY ||
    !latestAnalysis.keywords.length
  ) {
    return;
  }

  await setOpenOverlayState({ keywords: true });
  await sendActiveTabMessage({
    type: MESSAGE_TYPES.SHOW_KEYWORDS,
    payload: {
      keywords: latestAnalysis.keywords
    }
  });
}

async function showKeywordChartPopup() {
  if (latestOpenOverlays.keywordChart) {
    await closeOverlay("keywordChart");
    return;
  }

  if (
    !latestAuth.token ||
    latestAnalysis.status !== ANALYSIS_STATUS.READY ||
    !latestAnalysis.keywords.length
  ) {
    return;
  }

  await setOpenOverlayState({ keywordChart: true });
  await sendActiveTabMessage({
    type: MESSAGE_TYPES.SHOW_KEYWORD_CHART,
    payload: {
      keywords: latestAnalysis.keywords
    }
  });
}

async function showSummaryPopup() {
  if (latestOpenOverlays.summary) {
    await closeOverlay("summary");
    return;
  }

  if (
    !latestAuth.token ||
    latestAnalysis.status !== ANALYSIS_STATUS.READY ||
    !latestAnalysis.summary
  ) {
    return;
  }

  await setOpenOverlayState({ summary: true });
  await sendActiveTabMessage({
    type: MESSAGE_TYPES.SHOW_SUMMARY,
    payload: {
      summary: latestAnalysis.summary
    }
  });
}

async function showRecommendationsPopup() {
  if (latestOpenOverlays.recommendations) {
    await closeOverlay("recommendations");
    return;
  }

  if (
    !latestAuth.token ||
    latestAnalysis.status !== ANALYSIS_STATUS.READY ||
    !latestAnalysis.recommendations?.length
  ) {
    return;
  }

  await setOpenOverlayState({ recommendations: true });
  await sendActiveTabMessage({
    type: MESSAGE_TYPES.SHOW_RECOMMENDATIONS,
    payload: {
      recommendations: latestAnalysis.recommendations
    }
  });
}

async function showAllPopups() {
  if (!latestAuth.token || latestAnalysis.status !== ANALYSIS_STATUS.READY) {
    return;
  }

  await setOpenOverlayState({
    keywords: true,
    keywordChart: true,
    summary: true,
    recommendations: true,
    adLikelihood: true
  });

  await sendActiveTabMessage({
    type: MESSAGE_TYPES.SHOW_KEYWORDS,
    payload: {
      keywords: latestAnalysis.keywords || []
    }
  });

  await sendActiveTabMessage({
    type: MESSAGE_TYPES.SHOW_KEYWORD_CHART,
    payload: {
      keywords: latestAnalysis.keywords || []
    }
  });

  await sendActiveTabMessage({
    type: MESSAGE_TYPES.SHOW_SUMMARY,
    payload: {
      summary: latestAnalysis.summary || ""
    }
  });

  await sendActiveTabMessage({
    type: MESSAGE_TYPES.SHOW_RECOMMENDATIONS,
    payload: {
      recommendations: latestAnalysis.recommendations || []
    }
  });

  await sendActiveTabMessage({
    type: MESSAGE_TYPES.SHOW_AD_LIKELIHOOD,
    payload: {
      adLikelihood: latestAnalysis.adLikelihood
    }
  });
}

async function hideAllPopups() {
  await setOpenOverlayState({
    keywords: false,
    keywordChart: false,
    summary: false,
    recommendations: false,
    adLikelihood: false
  });

  await sendActiveTabMessage({
    type: MESSAGE_TYPES.HIDE_ALL_OVERLAYS
  });
}

async function closeOverlay(name) {
  await setOpenOverlayState({ [name]: false });
  await sendActiveTabMessage({
    type: MESSAGE_TYPES.HIDE_OVERLAY,
    payload: {
      name
    }
  });
}

async function setOpenOverlayState(nextState) {
  const tab = await getActiveTab();
  if (!tab?.id) return;

  // Open overlays are tracked per tab by the service worker.
  const response = await chrome.runtime.sendMessage({
    type: MESSAGE_TYPES.SET_OVERLAY_STATE,
    payload: { tabId: tab.id, state: nextState }
  });
  if (response?.ok) {
    latestOpenOverlays = response.result || {};
  }
  render(latestAnalysis);
}

async function sendActiveTabMessage(message) {
  const tab = await getActiveTab();

  if (!tab?.id || withoutHash(tab.url) !== withoutHash(latestAnalysis.article?.url)) {
    return;
  }

  try {
    await chrome.tabs.sendMessage(tab.id, message);
  } catch {
    if (!isSupportedArticleUrl(tab.url)) {
      return;
    }

    try {
      await chrome.scripting.executeScript({
        target: {
          tabId: tab.id
        },
        files: ["src/content/content-script.js"]
      });
      await chrome.tabs.sendMessage(tab.id, message);
    } catch {
      // The active tab may not be injectable, for example during navigation.
    }
  }
}

function isSupportedArticleUrl(url) {
  try { return ["http:", "https:"].includes(new URL(url).protocol); }
  catch { return false; }
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

function applyTheme(theme) {
  const normalizedTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = normalizedTheme;

  if (themeToggleNode) {
    themeToggleNode.checked = normalizedTheme === "dark";
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => {
    const replacements = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;"
    };

    return replacements[character];
  });
}

function renderServer(base) {
  if (serverUrlNode) serverUrlNode.value = base;
  if (serverCurrentNode) {
    serverCurrentNode.textContent = base === DEFAULT_API_BASE ? "(기본: 로컬 터널)" : `(${new URL(base).host})`;
  }
}

async function saveServer(value) {
  let base;
  try {
    const url = new URL(value.trim());
    if (!["http:", "https:"].includes(url.protocol)) throw new Error("unsupported protocol");
    base = url.origin;
  } catch {
    setNodeMessage(serverMessageNode, "http:// 또는 https://로 시작하는 서버 주소를 입력해 주세요.", "error");
    return;
  }

  // Requested before any other await so Chrome still counts the click as the user gesture.
  const granted = BUNDLED_API_ORIGINS.includes(base) || (await chrome.permissions.request({ origins: [`${base}/*`] }));
  if (!granted) {
    setNodeMessage(serverMessageNode, "이 서버에 연결하려면 접근 권한을 허용해야 합니다.", "error");
    return;
  }

  setNodeMessage(serverMessageNode, "연결을 확인하는 중입니다.");
  let health;
  try {
    const response = await fetch(`${base}/health`, { signal: AbortSignal.timeout(10000) });
    health = await response.json();
    if (!response.ok || typeof health?.status !== "string") throw new Error("not a DeepNews server");
  } catch {
    setNodeMessage(serverMessageNode, "서버에 연결할 수 없습니다. 주소와 서버 상태를 확인해 주세요.", "error");
    return;
  }

  const previous = (await chrome.storage.local.get(API_BASE_STORAGE_KEY))[API_BASE_STORAGE_KEY] || DEFAULT_API_BASE;
  if (previous !== base && latestAuth.token) {
    // Accounts live on each server; the old token means nothing to the new one.
    await chrome.runtime.sendMessage({ type: MESSAGE_TYPES.LOGOUT });
  }
  await chrome.storage.local.set({ [API_BASE_STORAGE_KEY]: base });
  renderServer(base);
  const models = health.ad_model_ready && health.summary_model_ready ? "분석 모델 준비됨" : "분석 모델 준비 안 됨";
  const invite = health.signup_invite_required ? " · 회원가입에 초대 코드 필요" : "";
  setNodeMessage(serverMessageNode, `연결되었습니다 (${models}${invite}).`, "success");
}
