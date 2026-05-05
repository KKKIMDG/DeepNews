import {
  ANALYSIS_STATUS,
  DEFAULT_ANALYSIS,
  MESSAGE_TYPES,
  STORAGE_KEY,
  THEME_STORAGE_KEY
} from "../shared/constants.js";

const keywordListNode = document.getElementById("keyword-list");
const chartNode = document.getElementById("keyword-chart");
const summaryNode = document.getElementById("summary");
const recommendationsNode = document.getElementById("recommendations");
const adLikelihoodNode = document.getElementById("ad-likelihood");
const themeToggleNode = document.getElementById("theme-toggle");
const authFormNode = document.getElementById("auth-form");
const loginIdNode = document.getElementById("login-id");
const loginPasswordNode = document.getElementById("login-password");
const signupButtonNode = document.getElementById("signup-button");
const logoutButtonNode = document.getElementById("logout-button");
const authMessageNode = document.getElementById("auth-message");

await initialize();

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") {
    return;
  }

  if (changes[STORAGE_KEY]) {
    render(changes[STORAGE_KEY].newValue || DEFAULT_ANALYSIS);
  }

  if (changes[THEME_STORAGE_KEY]) {
    applyTheme(changes[THEME_STORAGE_KEY].newValue || "light");
  }
});

themeToggleNode?.addEventListener("change", async (event) => {
  const nextTheme = event.currentTarget.checked ? "dark" : "light";
  applyTheme(nextTheme);
  await chrome.storage.local.set({ [THEME_STORAGE_KEY]: nextTheme });
});

authFormNode?.addEventListener("submit", async (event) => {
  event.preventDefault();
  await submitAuth(MESSAGE_TYPES.AUTH_LOGIN);
});

signupButtonNode?.addEventListener("click", async () => {
  await submitAuth(MESSAGE_TYPES.AUTH_SIGNUP);
});

logoutButtonNode?.addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ type: MESSAGE_TYPES.AUTH_LOGOUT });
  setAuthState(null);
});

recommendationsNode?.addEventListener("click", (event) => {
  if (!(event.target instanceof Element)) {
    return;
  }

  const actionButton = event.target.closest("button[data-interaction-type]");
  if (actionButton) {
    const listItem = actionButton.closest("li[data-news-id], li[data-url]");
    const interactionType = actionButton.dataset.interactionType;

    void chrome.runtime.sendMessage({
      type: MESSAGE_TYPES.RECORD_INTERACTION,
      payload: {
        newsId: listItem?.dataset.newsId ? Number(listItem.dataset.newsId) : null,
        url: listItem?.dataset.url,
        interactionType
      }
    });

    if (interactionType === "DISMISS") {
      listItem?.remove();
      if (!recommendationsNode.children.length) {
        recommendationsNode.innerHTML = "<li>No recommendations yet.</li>";
      }
    }

    if (interactionType === "BOOKMARK") {
      actionButton.classList.add("is-active");
      actionButton.textContent = "Bookmarked";
      actionButton.disabled = true;
    }

    return;
  }

  const link = event.target.closest("a[data-news-id], a[data-url]");
  if (!link) {
    return;
  }

  void chrome.runtime.sendMessage({
    type: MESSAGE_TYPES.RECORD_INTERACTION,
    payload: {
      newsId: link.dataset.newsId ? Number(link.dataset.newsId) : null,
      url: link.dataset.url,
      interactionType: "CLICK"
    }
  });
});

async function initialize() {
  const [response, storedTheme, authState] = await Promise.all([
    chrome.runtime.sendMessage({
      type: MESSAGE_TYPES.GET_LATEST_ANALYSIS
    }),
    chrome.storage.local.get(THEME_STORAGE_KEY),
    chrome.runtime.sendMessage({
      type: MESSAGE_TYPES.GET_AUTH_STATE
    })
  ]);

  applyTheme(storedTheme[THEME_STORAGE_KEY] || "light");
  setAuthState(authState?.result || null);
  render(response?.result || DEFAULT_ANALYSIS);
}

async function submitAuth(messageType) {
  const loginId = loginIdNode?.value?.trim() || "";
  const password = loginPasswordNode?.value || "";
  setAuthMessage("처리 중입니다.");

  const response = await chrome.runtime.sendMessage({
    type: messageType,
    payload: { loginId, password }
  });

  if (!response?.ok) {
    setAuthMessage(response?.error || "계정 처리 중 문제가 발생했습니다.");
    return;
  }

  loginPasswordNode.value = "";
  setAuthState(response.result);
}

function setAuthState(auth) {
  if (auth?.loginId) {
    authFormNode?.classList.add("is-logged-in");
    logoutButtonNode.hidden = false;
    loginIdNode.value = auth.loginId;
    loginIdNode.disabled = true;
    loginPasswordNode.value = "";
    loginPasswordNode.disabled = true;
    setAuthMessage(`${auth.loginId} 계정으로 추천을 개인화합니다.`);
    return;
  }

  authFormNode?.classList.remove("is-logged-in");
  logoutButtonNode.hidden = true;
  loginIdNode.disabled = false;
  loginPasswordNode.disabled = false;
  setAuthMessage("로그인하면 협업필터링 추천이 계정 기준으로 누적됩니다.");
}

function setAuthMessage(message) {
  if (authMessageNode) {
    authMessageNode.textContent = message;
  }
}

function render(analysis) {
  const normalizedAnalysis = {
    ...DEFAULT_ANALYSIS,
    ...analysis
  };

  renderKeywords(normalizedAnalysis);
  renderChart(normalizedAnalysis);
  renderSummary(normalizedAnalysis);
  renderRecommendations(normalizedAnalysis);
  renderAdLikelihood(normalizedAnalysis);
}

function renderKeywords(analysis) {
  const { keywords = [], status } = analysis;

  if (status === ANALYSIS_STATUS.LOADING) {
    keywordListNode.innerHTML = '<p class="state-message">Analyzing article...</p>';
    return;
  }

  if (!keywords.length) {
    keywordListNode.innerHTML = '<p class="state-message">No keywords yet.</p>';
    return;
  }

  keywordListNode.innerHTML = keywords
    .map((keyword) => `<span class="keyword-pill">${keyword.term}</span>`)
    .join("");
}

function renderChart(analysis) {
  const { keywords = [], status } = analysis;

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
          <span>${keyword.term}</span>
          <div class="bar-track"><div class="bar-fill" style="width: ${width}%"></div></div>
          <strong>${keyword.count}</strong>
        </div>
      `;
    })
    .join("");
}

function renderSummary(analysis) {
  const { summary = "", status } = analysis;
  if (status === ANALYSIS_STATUS.LOADING) {
    summaryNode.textContent = "기사 내용을 분석하고 있습니다.";
    return;
  }

  summaryNode.textContent = summary || "No summary yet.";
}

function renderRecommendations(analysis) {
  const { recommendations = [], status } = analysis;
  if (status === ANALYSIS_STATUS.LOADING) {
    recommendationsNode.innerHTML = '<li class="state-message">Finding related articles...</li>';
    return;
  }

  if (!recommendations.length) {
    recommendationsNode.innerHTML = "<li>No recommendations yet.</li>";
    return;
  }

  recommendationsNode.replaceChildren(
    ...recommendations.map((item) => {
      const listItem = document.createElement("li");
      listItem.className = "recommendation-item";
      listItem.dataset.url = item.url;
      if (item.newsId) {
        listItem.dataset.newsId = String(item.newsId);
      }

      const link = document.createElement("a");
      link.className = "recommendation-title";
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = item.title;
      link.dataset.url = item.url;
      if (item.newsId) {
        link.dataset.newsId = String(item.newsId);
      }

      const meta = document.createElement("p");
      meta.className = "recommendation-reason";
      meta.textContent = item.reason || "Recommended for this article";

      const actions = document.createElement("div");
      actions.className = "recommendation-actions";

      const bookmarkButton = document.createElement("button");
      bookmarkButton.type = "button";
      bookmarkButton.className = "recommendation-action";
      bookmarkButton.dataset.interactionType = "BOOKMARK";
      bookmarkButton.textContent = "Bookmark";

      const dismissButton = document.createElement("button");
      dismissButton.type = "button";
      dismissButton.className = "recommendation-action";
      dismissButton.dataset.interactionType = "DISMISS";
      dismissButton.textContent = "Not interested";

      actions.append(bookmarkButton, dismissButton);
      listItem.append(link);
      listItem.append(meta, actions);
      return listItem;
    })
  );
}

function renderAdLikelihood(analysis) {
  const { adLikelihood, status } = analysis;

  if (status === ANALYSIS_STATUS.LOADING) {
    adLikelihoodNode.className = "ad-likelihood";
    adLikelihoodNode.textContent = "Checking promotional tone...";
    return;
  }

  const rawScore = adLikelihood?.score ?? 0;
  if (rawScore < 0) {
    adLikelihoodNode.className = "ad-likelihood";
    adLikelihoodNode.textContent = adLikelihood?.label || "Not analyzed";
    return;
  }

  const score = Math.round(rawScore * 100);
  const toneClass = score >= 70 ? "score-warn" : "score-good";
  adLikelihoodNode.className = `ad-likelihood ${toneClass}`;
  adLikelihoodNode.textContent = `${adLikelihood?.label || "Not analyzed"} (${score} points)`;
}

function applyTheme(theme) {
  const normalizedTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = normalizedTheme;

  if (themeToggleNode) {
    themeToggleNode.checked = normalizedTheme === "dark";
  }
}
