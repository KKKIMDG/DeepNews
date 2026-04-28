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

async function initialize() {
  const [response, storedTheme] = await Promise.all([
    chrome.runtime.sendMessage({
      type: MESSAGE_TYPES.GET_LATEST_ANALYSIS
    }),
    chrome.storage.local.get(THEME_STORAGE_KEY)
  ]);

  applyTheme(storedTheme[THEME_STORAGE_KEY] || "light");
  render(response?.result || DEFAULT_ANALYSIS);
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

  recommendationsNode.innerHTML = recommendations
    .map(
      (item) =>
        `<li><a href="${item.url}" target="_blank" rel="noreferrer">${item.title}</a></li>`
    )
    .join("");
}

function renderAdLikelihood(analysis) {
  const { adLikelihood, status } = analysis;

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

function applyTheme(theme) {
  const normalizedTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = normalizedTheme;

  if (themeToggleNode) {
    themeToggleNode.checked = normalizedTheme === "dark";
  }
}
