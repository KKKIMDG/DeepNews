import {
  ANALYSIS_STATUS,
  AUTH_STORAGE_KEY,
  DEFAULT_AUTH,
  DEFAULT_ANALYSIS,
  MESSAGE_TYPES,
  OVERLAY_STATE_STORAGE_KEY,
  STORAGE_KEY,
  THEME_STORAGE_KEY
} from "../shared/constants.js";

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
const loginModeNode = document.getElementById("login-mode");
const logoutButtonNode = document.getElementById("logout-button");
const signupModeNode = document.getElementById("signup-mode");
const themeToggleNode = document.getElementById("theme-toggle");
const showAdPopupNode = document.getElementById("show-ad-popup");
const showKeywordPopupNode = document.getElementById("show-keyword-popup");
const showKeywordChartPopupNode = document.getElementById("show-keyword-chart-popup");
const showSummaryPopupNode = insertInlineActionButton("show-summary-popup", summaryNode);
const showRecommendationsPopupNode = insertInlineActionButton(
  "show-recommendations-popup",
  recommendationsNode
);
insertGlobalActionButtons();
const showAllPopupsNode = document.getElementById("show-all-popups");
const hideAllPopupsNode = document.getElementById("hide-all-popups");

let latestAnalysis = DEFAULT_ANALYSIS;
let latestAuth = DEFAULT_AUTH;
let latestOpenOverlays = {};
let authMode = "login";

await initialize();

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") {
    return;
  }

  if (changes[STORAGE_KEY]) {
    render(changes[STORAGE_KEY].newValue || DEFAULT_ANALYSIS);
  }

  if (changes[AUTH_STORAGE_KEY]) {
    renderAuth(changes[AUTH_STORAGE_KEY].newValue || DEFAULT_AUTH);
  }

  if (changes[THEME_STORAGE_KEY]) {
    applyTheme(changes[THEME_STORAGE_KEY].newValue || "light");
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

logoutButtonNode?.addEventListener("click", () => {
  void logout();
});

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

async function initialize() {
  const [response, authResponse, storedTheme, storedOverlays] = await Promise.all([
    chrome.runtime.sendMessage({
      type: MESSAGE_TYPES.GET_LATEST_ANALYSIS
    }),
    chrome.runtime.sendMessage({
      type: MESSAGE_TYPES.GET_AUTH_STATE
    }),
    chrome.storage.local.get(THEME_STORAGE_KEY),
    chrome.storage.local.get(OVERLAY_STATE_STORAGE_KEY)
  ]);

  latestOpenOverlays = storedOverlays[OVERLAY_STATE_STORAGE_KEY] || {};
  applyTheme(storedTheme[THEME_STORAGE_KEY] || "light");
  renderAuth(authResponse?.result || DEFAULT_AUTH);
  render(response?.result || DEFAULT_ANALYSIS);
}

function render(analysis) {
  const normalizedAnalysis = {
    ...DEFAULT_ANALYSIS,
    ...analysis
  };

  latestAnalysis = normalizedAnalysis;
  renderGlobalActions(normalizedAnalysis);
  renderKeywords(normalizedAnalysis);
  renderChart(normalizedAnalysis);
  renderSummary(normalizedAnalysis);
  renderRecommendations(normalizedAnalysis);
  renderAdLikelihood(normalizedAnalysis);
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

  document.body.dataset.auth = isSignedIn ? "signed-in" : "signed-out";

  if (analysisContentNode) {
    analysisContentNode.hidden = !isSignedIn;
  }

  if (authFormNode) {
    authFormNode.hidden = isSignedIn;
  }

  if (logoutButtonNode) {
    logoutButtonNode.hidden = !isSignedIn;
  }

  if (!isSignedIn) {
    setAuthMode(authMode);
  }

  render(latestAnalysis);
}

function setAuthMode(mode) {
  authMode = mode === "signup" ? "signup" : "login";
  loginModeNode?.classList.toggle("active", authMode === "login");
  signupModeNode?.classList.toggle("active", authMode === "signup");

  if (authSubmitNode) {
    authSubmitNode.textContent = authMode === "login" ? "로그인" : "회원가입";
  }

  if (authPasswordNode) {
    authPasswordNode.autocomplete =
      authMode === "login" ? "current-password" : "new-password";
  }

  setAuthMessage("");
}

async function submitAuthForm() {
  const email = authEmailNode?.value.trim() || "";
  const password = authPasswordNode?.value || "";

  if (!email || !password) {
    setAuthMessage("이메일과 비밀번호를 입력해 주세요.", "error");
    return;
  }

  setAuthPending(true);
  setAuthMessage(
    authMode === "login" ? "로그인 중입니다." : "회원가입을 진행하는 중입니다."
  );

  const response = await chrome.runtime.sendMessage({
    type: authMode === "login" ? MESSAGE_TYPES.LOGIN : MESSAGE_TYPES.SIGNUP,
    payload: {
      email,
      password
    }
  });

  setAuthPending(false);

  if (!response?.ok) {
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
  renderAuth(response.result || DEFAULT_AUTH);
  setAuthMessage(authMode === "login" ? "로그인되었습니다." : "회원가입이 완료되었습니다.", "success");
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
    showKeywordPopupNode.textContent = latestOpenOverlays.keywords ? "팝업 닫기" : "팝업 띄우기";
  }

  if (status === ANALYSIS_STATUS.LOADING) {
    keywordListNode.innerHTML = '<p class="state-message">Analyzing article...</p>';
    return;
  }

  if (!keywords.length) {
    keywordListNode.innerHTML = '<p class="state-message">No keywords yet.</p>';
    return;
  }

  keywordListNode.innerHTML = keywords
    .map((keyword) => `<span class="keyword-pill">${escapeHtml(keyword.term)}</span>`)
    .join("");
}

function renderChart(analysis) {
  const { keywords = [], status } = analysis;
  if (showKeywordChartPopupNode) {
    showKeywordChartPopupNode.disabled =
      !latestOpenOverlays.keywordChart && (status !== ANALYSIS_STATUS.READY || !keywords.length);
    showKeywordChartPopupNode.textContent = latestOpenOverlays.keywordChart
      ? "팝업 닫기"
      : "팝업 띄우기";
  }

  if (status === ANALYSIS_STATUS.LOADING) {
    chartNode.innerHTML = '<p class="state-message">Building keyword chart...</p>';
    return;
  }

  if (!keywords.length) {
    chartNode.innerHTML = '<p class="state-message">No chart data yet.</p>';
    return;
  }

  const max = Math.max(...keywords.map((keyword) => keyword.count), 1);
  chartNode.innerHTML = keywords
    .map((keyword) => {
      const width = Math.round((keyword.count / max) * 100);
      return `
        <div class="bar-row">
          <span>${escapeHtml(keyword.term)}</span>
          <div class="bar-track"><div class="bar-fill" style="width: ${width}%"></div></div>
          <strong>${keyword.count}</strong>
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
    showSummaryPopupNode.textContent = latestOpenOverlays.summary ? "팝업 닫기" : "팝업 띄우기";
  }

  if (status === ANALYSIS_STATUS.LOADING) {
    summaryNode.textContent = "기사 내용을 분석하고 있습니다.";
    return;
  }

  summaryNode.textContent = summary || "No summary yet.";
}

function renderRecommendations(analysis) {
  const { recommendations = [], status } = analysis;
  if (showRecommendationsPopupNode) {
    showRecommendationsPopupNode.disabled =
      !latestOpenOverlays.recommendations &&
      (status !== ANALYSIS_STATUS.READY || !recommendations.length);
    showRecommendationsPopupNode.textContent = latestOpenOverlays.recommendations
      ? "팝업 닫기"
      : "팝업 띄우기";
  }

  if (status === ANALYSIS_STATUS.LOADING) {
    recommendationsNode.innerHTML = '<li class="state-message">Finding related articles...</li>';
    return;
  }

  if (!recommendations.length) {
    recommendationsNode.innerHTML = "<li>No recommendations yet.</li>";
    return;
  }

  recommendationsNode.innerHTML = recommendations
    .map(
      (item) =>
        `<li><a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a></li>`
    )
    .join("");
}

function renderAdLikelihood(analysis) {
  const { adLikelihood, status } = analysis;
  if (showAdPopupNode) {
    showAdPopupNode.disabled =
      !latestOpenOverlays.adLikelihood && (status !== ANALYSIS_STATUS.READY || !adLikelihood);
    showAdPopupNode.textContent = latestOpenOverlays.adLikelihood ? "팝업 닫기" : "팝업 띄우기";
  }

  if (status === ANALYSIS_STATUS.LOADING) {
    adLikelihoodNode.className = "ad-likelihood";
    adLikelihoodNode.textContent = "Checking promotional tone...";
    return;
  }

  const score = Math.round((adLikelihood?.score || 0) * 100);
  const toneClass = score >= 70 ? "score-warn" : "score-good";
  adLikelihoodNode.className = `ad-likelihood ${toneClass}`;
  adLikelihoodNode.textContent = `${adLikelihood?.label || "Not analyzed"} (${score} points)`;
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
  const stored = await chrome.storage.local.get(OVERLAY_STATE_STORAGE_KEY);
  latestOpenOverlays = {
    ...(stored[OVERLAY_STATE_STORAGE_KEY] || {}),
    ...nextState
  };
  await chrome.storage.local.set({
    [OVERLAY_STATE_STORAGE_KEY]: latestOpenOverlays
  });
  render(latestAnalysis);
}

async function sendActiveTabMessage(message) {
  const [tab] = await chrome.tabs.query({
    active: true,
    currentWindow: true
  });

  if (!tab?.id) {
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
  if (!url) {
    return false;
  }

  try {
    const parsed = new URL(url);
    const isNaverNewsHost =
      parsed.hostname === "news.naver.com" || parsed.hostname === "n.news.naver.com";

    return isNaverNewsHost && /\/article\//.test(parsed.pathname);
  } catch {
    return false;
  }
}

function insertInlineActionButton(id, targetNode) {
  if (!targetNode?.parentNode) {
    return null;
  }

  const existingButton = document.getElementById(id);
  if (existingButton) {
    return existingButton;
  }

  const button = document.createElement("button");
  button.id = id;
  button.className = "inline-action";
  button.type = "button";
  button.textContent = "팝업 띄우기";
  targetNode.parentNode.insertBefore(button, targetNode);

  return button;
}

function insertGlobalActionButtons() {
  const heroNode = document.querySelector(".hero");
  if (!heroNode || document.getElementById("show-all-popups")) {
    return;
  }

  const actionsNode = document.createElement("div");
  actionsNode.className = "global-actions";
  actionsNode.innerHTML = `
    <button id="show-all-popups" class="global-action primary" type="button">전체 띄우기</button>
    <button id="hide-all-popups" class="global-action" type="button">전체 삭제</button>
  `;
  heroNode.appendChild(actionsNode);
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
