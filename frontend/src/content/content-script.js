(() => {
if (globalThis.__deepnewsContentScriptLoaded) {
  return;
}

globalThis.__deepnewsContentScriptLoaded = true;

const ARTICLE_SELECTORS = {
  body: [
    "#dic_area",
    "#newsct_article",
    ".newsct_article"
  ]
};

const HIGHLIGHT_CLASS = "deepnews-highlight";
const ANALYZE_ARTICLE = "ANALYZE_ARTICLE";
const SHOW_AD_LIKELIHOOD = "SHOW_AD_LIKELIHOOD";
const SHOW_KEYWORDS = "SHOW_KEYWORDS";
const SHOW_KEYWORD_CHART = "SHOW_KEYWORD_CHART";
const SHOW_SUMMARY = "SHOW_SUMMARY";
const SHOW_RECOMMENDATIONS = "SHOW_RECOMMENDATIONS";
const SHOW_LOADING_OVERLAYS = "SHOW_LOADING_OVERLAYS";
const HIDE_OVERLAY = "HIDE_OVERLAY";
const HIDE_ALL_OVERLAYS = "HIDE_ALL_OVERLAYS";
const OVERLAY_HOST_ID = "deepnews-ad-likelihood-overlay";
const KEYWORD_OVERLAY_HOST_ID = "deepnews-keyword-overlay";
const KEYWORD_CHART_OVERLAY_HOST_ID = "deepnews-keyword-chart-overlay";
const SUMMARY_OVERLAY_HOST_ID = "deepnews-summary-overlay";
const RECOMMENDATIONS_OVERLAY_HOST_ID = "deepnews-recommendations-overlay";
const OVERLAY_POSITION_STORAGE_KEY = "deepnews.adLikelihoodOverlayPosition";
const KEYWORD_OVERLAY_POSITION_STORAGE_KEY = "deepnews.keywordOverlayPosition";
const KEYWORD_CHART_OVERLAY_POSITION_STORAGE_KEY = "deepnews.keywordChartOverlayPosition";
const SUMMARY_OVERLAY_POSITION_STORAGE_KEY = "deepnews.summaryOverlayPosition";
const RECOMMENDATIONS_OVERLAY_POSITION_STORAGE_KEY = "deepnews.recommendationsOverlayPosition";
const OPEN_OVERLAYS_STORAGE_KEY = "deepnews.openOverlays";
const THEME_STORAGE_KEY = "deepnews.theme";
const BASE_OVERLAY_Z_INDEX = 2147483000;
let resizeRepositionTimer = null;
let overlayZIndex = BASE_OVERLAY_Z_INDEX + 20;
let currentTheme = "light";
let latestAdLikelihood = null;
let latestKeywords = [];
let latestKeywordChart = [];
let latestSummary = "";
let latestRecommendations = [];

void bootstrap();
window.addEventListener("resize", scheduleOverlayViewportCheck);

async function bootstrap() {
  await initializeTheme();
  injectHighlightStyle();

  const article = extractArticleUrl();
  if (!article) {
    return;
  }

  safeRuntimeSendMessage({
    type: ANALYZE_ARTICLE,
    payload: article
  });
}

registerExtensionListeners();

function extractArticleUrl() {
  if (!window.location.href) {
    return null;
  }

  return {
    url: window.location.href
  };
}

function highlightKeywords(keywords) {
  const articleNode = document.querySelector(ARTICLE_SELECTORS.body.join(","));
  if (!articleNode || !keywords.length) {
    return;
  }

  removeExistingHighlights(articleNode);

  const walker = document.createTreeWalker(articleNode, NodeFilter.SHOW_TEXT);
  const textNodes = [];

  while (walker.nextNode()) {
    const current = walker.currentNode;
    if (current.nodeValue?.trim()) {
      textNodes.push(current);
    }
  }

  for (const node of textNodes) {
    let html = node.nodeValue;
    let changed = false;

    for (const keyword of keywords) {
      const escaped = escapeRegExp(keyword);
      const regex = new RegExp(`(${escaped})`, "gi");
      if (regex.test(html)) {
        changed = true;
        html = html.replace(regex, `<mark class="${HIGHLIGHT_CLASS}">$1</mark>`);
      }
    }

    if (!changed) {
      continue;
    }

    const wrapper = document.createElement("span");
    wrapper.innerHTML = html;
    node.parentNode?.replaceChild(wrapper, node);
  }
}

function removeExistingHighlights(root) {
  root.querySelectorAll(`mark.${HIGHLIGHT_CLASS}`).forEach((mark) => {
    mark.replaceWith(document.createTextNode(mark.textContent || ""));
  });
}

function injectHighlightStyle() {
  const style = document.createElement("style");
  style.textContent = `
    .${HIGHLIGHT_CLASS} {
      background: linear-gradient(transparent 55%, #ffe082 55%);
      color: inherit;
      padding: 0;
    }
  `;

  document.documentElement.appendChild(style);
}

function renderAdLikelihoodOverlay(adLikelihood) {
  if (!adLikelihood) {
    return;
  }

  markOverlayOpen("adLikelihood", true);
  latestAdLikelihood = adLikelihood;
  const score = Math.round((adLikelihood.score || 0) * 100);
  const boundedScore = Math.max(0, Math.min(score, 100));
  const label = adLikelihood.label || "Not analyzed";
  const tone = score >= 70 ? "warning" : "normal";
  const scoreColor = tone === "warning" ? "#ffb84d" : "#4ade80";
  const theme = getOverlayTheme();
  const existingHost = document.getElementById(OVERLAY_HOST_ID);
  const host = existingHost || document.createElement("div");

  if (!existingHost) {
    host.id = OVERLAY_HOST_ID;
    host.dataset.positionStorageKey = OVERLAY_POSITION_STORAGE_KEY;
    document.documentElement.appendChild(host);
  }

  const shadow = host.shadowRoot || host.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      :host {
        all: initial;
        position: fixed;
        right: 18px;
        top: 18px;
        z-index: ${BASE_OVERLAY_Z_INDEX + 7};
        font-family: "Segoe UI", "Malgun Gothic", sans-serif;
      }

      .popup {
        width: min(280px, calc(100vw - 36px));
        padding: 14px 14px 12px;
        border: 1px solid ${theme.border};
        border-radius: 16px;
        background: ${theme.surface};
        color: ${theme.text};
        box-shadow: ${theme.shadow};
        backdrop-filter: blur(12px);
      }

      .top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        cursor: grab;
        user-select: none;
        touch-action: none;
      }

      .top:active {
        cursor: grabbing;
      }

      .eyebrow {
        margin: 0 0 4px;
        color: #03c75a;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }

      .title {
        margin: 0;
        font-size: 15px;
        font-weight: 800;
        line-height: 1.35;
      }

      .donut {
        flex: 0 0 auto;
        display: grid;
        width: 70px;
        height: 70px;
        place-items: center;
        border-radius: 50%;
        background:
          radial-gradient(circle, ${theme.surface} 0 57%, transparent 58%),
          conic-gradient(${scoreColor} 0 ${boundedScore}%, ${theme.track} ${boundedScore}% 100%);
        color: ${scoreColor};
        font-size: 17px;
        font-weight: 900;
        line-height: 1;
      }

      .donut span {
        transform: translateY(1px);
      }

      .label {
        margin: 10px 0 0;
        color: ${theme.muted};
        font-size: 12px;
        font-weight: 700;
        line-height: 1.45;
      }

      .close {
        position: absolute;
        top: 8px;
        right: 8px;
        width: 26px;
        height: 26px;
        border: 0;
        border-radius: 50%;
        background: transparent;
        color: ${theme.close};
        cursor: pointer;
        font-size: 18px;
        line-height: 1;
      }

      .close:hover {
        background: ${theme.closeHoverBg};
        color: ${theme.closeHover};
      }

      ${getSubtleScrollbarCss(".popup")}
    </style>

    <aside class="popup" role="status" aria-live="polite">
      <button class="close" type="button" title="닫기" aria-label="Close DeepNews popup">×</button>
      <div class="top">
        <div>
          <p class="eyebrow">DeepNews</p>
          <p class="title">광고성 판단</p>
        </div>
        <strong class="donut" aria-label="광고성 ${boundedScore}%"><span>${boundedScore}%</span></strong>
      </div>
      <p class="label">${escapeHtml(label)}</p>
    </aside>
  `;

  shadow.querySelector(".close")?.addEventListener("click", (event) => {
    event.stopPropagation();
    markOverlayOpen("adLikelihood", false);
    host.remove();
  });

  applyStoredOverlayPosition(host);
  makeOverlayResizable(host, shadow.querySelector(".popup"));
  makeOverlayDraggable(host, shadow.querySelector(".top"));
}

function renderKeywordOverlay(keywords) {
  if (!keywords.length) {
    return;
  }

  markOverlayOpen("keywords", true);
  latestKeywords = keywords;
  const theme = getOverlayTheme();
  const existingHost = document.getElementById(KEYWORD_OVERLAY_HOST_ID);
  const host = existingHost || document.createElement("div");

  if (!existingHost) {
    host.id = KEYWORD_OVERLAY_HOST_ID;
    host.dataset.positionStorageKey = KEYWORD_OVERLAY_POSITION_STORAGE_KEY;
    document.documentElement.appendChild(host);
  }

  const keywordItems = keywords
    .slice(0, 8)
    .map((keyword) => {
      const term = typeof keyword === "string" ? keyword : keyword.term;
      return `
        <span class="pill">
          ${escapeHtml(term)}
        </span>
      `;
    })
    .join("");

  const shadow = host.shadowRoot || host.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      :host {
        all: initial;
        position: fixed;
        right: 18px;
        top: 168px;
        z-index: ${BASE_OVERLAY_Z_INDEX + 6};
        font-family: "Segoe UI", "Malgun Gothic", sans-serif;
      }

      .popup {
        width: min(280px, calc(100vw - 36px));
        padding: 14px;
        border: 1px solid ${theme.border};
        border-radius: 16px;
        background: ${theme.surface};
        color: ${theme.text};
        box-shadow: ${theme.shadow};
        backdrop-filter: blur(12px);
      }

      .top {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        cursor: grab;
        user-select: none;
        touch-action: none;
      }

      .top:active {
        cursor: grabbing;
      }

      .eyebrow {
        margin: 0 0 4px;
        color: #03c75a;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }

      .title {
        margin: 0;
        font-size: 15px;
        font-weight: 800;
        line-height: 1.35;
      }

      .close {
        flex: 0 0 auto;
        width: 26px;
        height: 26px;
        border: 0;
        border-radius: 50%;
        background: transparent;
        color: ${theme.close};
        cursor: pointer;
        font-size: 18px;
        line-height: 1;
      }

      .close:hover {
        background: ${theme.closeHoverBg};
        color: ${theme.closeHover};
      }

      .pills {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 12px;
      }

      .pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        max-width: 100%;
        padding: 7px 10px;
        border: 1px solid rgba(3, 199, 90, 0.26);
        border-radius: 999px;
        background: rgba(3, 199, 90, 0.16);
        color: ${theme.text};
        font-size: 12px;
        font-weight: 800;
        line-height: 1.2;
      }

      ${getSubtleScrollbarCss(".popup")}
    </style>

    <aside class="popup" role="status" aria-live="polite">
      <div class="top">
        <div>
          <p class="eyebrow">DeepNews</p>
          <p class="title">핵심 키워드</p>
        </div>
        <button class="close" type="button" title="닫기" aria-label="Close DeepNews keyword popup">×</button>
      </div>
      <div class="pills">${keywordItems}</div>
    </aside>
  `;

  shadow.querySelector(".close")?.addEventListener("click", (event) => {
    event.stopPropagation();
    markOverlayOpen("keywords", false);
    host.remove();
  });

  applyStoredOverlayPosition(host);
  makeOverlayResizable(host, shadow.querySelector(".popup"));
  makeOverlayDraggable(host, shadow.querySelector(".top"));
}

function renderKeywordChartOverlay(keywords) {
  if (!keywords.length) {
    return;
  }

  markOverlayOpen("keywordChart", true);
  latestKeywordChart = keywords;
  const theme = getOverlayTheme();
  const overlaySize = getKeywordOverlaySize(keywords);
  const max = Math.max(
    ...keywords.map((keyword) => (typeof keyword === "string" ? 1 : keyword.count || 1)),
    1
  );
  const existingHost = document.getElementById(KEYWORD_CHART_OVERLAY_HOST_ID);
  const host = existingHost || document.createElement("div");

  if (!existingHost) {
    host.id = KEYWORD_CHART_OVERLAY_HOST_ID;
    host.dataset.positionStorageKey = KEYWORD_CHART_OVERLAY_POSITION_STORAGE_KEY;
    document.documentElement.appendChild(host);
  }

  const rows = keywords
    .slice(0, 8)
    .map((keyword) => {
      const term = typeof keyword === "string" ? keyword : keyword.term;
      const count = typeof keyword === "string" ? 1 : keyword.count || 1;
      const width = Math.round((count / max) * 100);
      return `
        <div class="bar-row">
          <span class="term">${escapeHtml(term)}</span>
          <div class="bar-track">
            <div class="bar-fill" style="width: ${width}%"></div>
          </div>
          <strong>${escapeHtml(count)}</strong>
        </div>
      `;
    })
    .join("");

  const shadow = host.shadowRoot || host.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      :host {
        all: initial;
        position: fixed;
        right: 18px;
        top: 318px;
        z-index: ${BASE_OVERLAY_Z_INDEX + 5};
        font-family: "Segoe UI", "Malgun Gothic", sans-serif;
      }

      .popup {
        width: min(${overlaySize.width}px, calc(100vw - 36px));
        max-height: min(${overlaySize.maxHeight}px, calc(100vh - 36px));
        padding: 14px;
        border: 1px solid ${theme.border};
        border-radius: 16px;
        background: ${theme.surface};
        color: ${theme.text};
        box-shadow: ${theme.shadow};
        backdrop-filter: blur(12px);
      }

      .top {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        cursor: grab;
        user-select: none;
        touch-action: none;
      }

      .top:active {
        cursor: grabbing;
      }

      .eyebrow {
        margin: 0 0 4px;
        color: #03c75a;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }

      .title {
        margin: 0;
        font-size: 15px;
        font-weight: 800;
        line-height: 1.35;
      }

      .close {
        flex: 0 0 auto;
        width: 26px;
        height: 26px;
        border: 0;
        border-radius: 50%;
        background: transparent;
        color: ${theme.close};
        cursor: pointer;
        font-size: 18px;
        line-height: 1;
      }

      .close:hover {
        background: ${theme.closeHoverBg};
        color: ${theme.closeHover};
      }

      .chart {
        display: grid;
        gap: 9px;
        margin-top: 12px;
      }

      .bar-row {
        display: grid;
        grid-template-columns: minmax(52px, 82px) minmax(0, 1fr) 28px;
        gap: 8px;
        align-items: center;
        min-width: 0;
      }

      .term {
        overflow: hidden;
        color: ${theme.text};
        font-size: 12px;
        font-weight: 800;
        line-height: 1.2;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .bar-track {
        overflow: hidden;
        min-width: 0;
        height: 10px;
        border-radius: 999px;
        background: ${theme.track};
      }

      .bar-fill {
        height: 100%;
        border-radius: inherit;
        background: linear-gradient(90deg, #03c75a, #4ade80);
      }

      strong {
        color: ${theme.muted};
        font-size: 12px;
        font-weight: 900;
        text-align: right;
      }

      ${getSubtleScrollbarCss(".popup")}
    </style>

    <aside class="popup" role="status" aria-live="polite">
      <div class="top">
        <div>
          <p class="eyebrow">DeepNews</p>
          <p class="title">키워드 빈도</p>
        </div>
        <button class="close" type="button" title="닫기" aria-label="Close DeepNews keyword chart popup">×</button>
      </div>
      <div class="chart">${rows}</div>
    </aside>
  `;

  shadow.querySelector(".close")?.addEventListener("click", (event) => {
    event.stopPropagation();
    markOverlayOpen("keywordChart", false);
    host.remove();
  });

  applyStoredOverlayPosition(host);
  makeOverlayResizable(host, shadow.querySelector(".popup"));
  makeOverlayDraggable(host, shadow.querySelector(".top"));
}

function renderSummaryOverlay(summary) {
  const normalizedSummary = summary?.trim();
  if (!normalizedSummary) {
    return;
  }

  markOverlayOpen("summary", true);
  latestSummary = normalizedSummary;
  const theme = getOverlayTheme();
  const overlaySize = getSummaryOverlaySize(normalizedSummary);
  const existingHost = document.getElementById(SUMMARY_OVERLAY_HOST_ID);
  const host = existingHost || document.createElement("div");

  if (!existingHost) {
    host.id = SUMMARY_OVERLAY_HOST_ID;
    host.dataset.positionStorageKey = SUMMARY_OVERLAY_POSITION_STORAGE_KEY;
    document.documentElement.appendChild(host);
  }

  const shadow = host.shadowRoot || host.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      :host {
        all: initial;
        position: fixed;
        right: 18px;
        top: 468px;
        z-index: ${BASE_OVERLAY_Z_INDEX + 4};
        font-family: "Segoe UI", "Malgun Gothic", sans-serif;
      }

      .popup {
        display: flex;
        flex-direction: column;
        width: min(${overlaySize.width}px, calc(100vw - 36px));
        max-height: min(${overlaySize.maxHeight}px, calc(100vh - 36px));
        padding: 14px;
        border: 1px solid ${theme.border};
        border-radius: 16px;
        background: ${theme.surface};
        color: ${theme.text};
        box-shadow: ${theme.shadow};
        backdrop-filter: blur(12px);
      }

      .top {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        cursor: grab;
        user-select: none;
        touch-action: none;
      }

      .top:active {
        cursor: grabbing;
      }

      .eyebrow {
        margin: 0 0 4px;
        color: #03c75a;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }

      .title {
        margin: 0;
        font-size: 15px;
        font-weight: 800;
        line-height: 1.35;
      }

      .close {
        flex: 0 0 auto;
        width: 26px;
        height: 26px;
        border: 0;
        border-radius: 50%;
        background: transparent;
        color: ${theme.close};
        cursor: pointer;
        font-size: 18px;
        line-height: 1;
      }

      .close:hover {
        background: ${theme.closeHoverBg};
        color: ${theme.closeHover};
      }

      .body {
        flex: 1 1 auto;
        overflow: auto;
        min-height: 0;
        margin: 12px 0 0;
        color: ${theme.muted};
        font-size: 13px;
        font-weight: 700;
        line-height: 1.65;
      }

      ${getSubtleScrollbarCss(".popup")}
      ${getSubtleScrollbarCss(".body")}
    </style>

    <aside class="popup" role="status" aria-live="polite">
      <div class="top">
        <div>
          <p class="eyebrow">DeepNews</p>
          <p class="title">AI 요약</p>
        </div>
        <button class="close" type="button" title="닫기" aria-label="Close DeepNews summary popup">×</button>
      </div>
      <p class="body">${escapeHtml(normalizedSummary)}</p>
    </aside>
  `;

  shadow.querySelector(".close")?.addEventListener("click", (event) => {
    event.stopPropagation();
    markOverlayOpen("summary", false);
    host.remove();
  });

  applyStoredOverlayPosition(host);
  makeOverlayResizable(host, shadow.querySelector(".popup"));
  makeOverlayDraggable(host, shadow.querySelector(".top"));
}

function renderRecommendationsOverlay(recommendations) {
  if (!recommendations.length) {
    return;
  }

  markOverlayOpen("recommendations", true);
  latestRecommendations = recommendations;
  const theme = getOverlayTheme();
  const overlaySize = getRecommendationsOverlaySize(recommendations);
  const existingHost = document.getElementById(RECOMMENDATIONS_OVERLAY_HOST_ID);
  const host = existingHost || document.createElement("div");

  if (!existingHost) {
    host.id = RECOMMENDATIONS_OVERLAY_HOST_ID;
    host.dataset.positionStorageKey = RECOMMENDATIONS_OVERLAY_POSITION_STORAGE_KEY;
    document.documentElement.appendChild(host);
  }

  const items = recommendations
    .slice(0, 5)
    .map((item) => {
      const title = item?.title || "Related article";
      const url = item?.url || "#";
      return `
        <li>
          <a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">
            ${escapeHtml(title)}
          </a>
        </li>
      `;
    })
    .join("");

  const shadow = host.shadowRoot || host.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      :host {
        all: initial;
        position: fixed;
        right: 18px;
        top: 608px;
        z-index: ${BASE_OVERLAY_Z_INDEX + 3};
        font-family: "Segoe UI", "Malgun Gothic", sans-serif;
      }

      .popup {
        width: min(${overlaySize.width}px, calc(100vw - 36px));
        max-height: min(${overlaySize.maxHeight}px, calc(100vh - 36px));
        padding: 14px;
        border: 1px solid ${theme.border};
        border-radius: 16px;
        background: ${theme.surface};
        color: ${theme.text};
        box-shadow: ${theme.shadow};
        backdrop-filter: blur(12px);
      }

      .top {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        cursor: grab;
        user-select: none;
        touch-action: none;
      }

      .top:active {
        cursor: grabbing;
      }

      .eyebrow {
        margin: 0 0 4px;
        color: #03c75a;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }

      .title {
        margin: 0;
        font-size: 15px;
        font-weight: 800;
        line-height: 1.35;
      }

      .close {
        flex: 0 0 auto;
        width: 26px;
        height: 26px;
        border: 0;
        border-radius: 50%;
        background: transparent;
        color: ${theme.close};
        cursor: pointer;
        font-size: 18px;
        line-height: 1;
      }

      .close:hover {
        background: ${theme.closeHoverBg};
        color: ${theme.closeHover};
      }

      .list {
        overflow: auto;
        display: grid;
        gap: 10px;
        max-height: 204px;
        margin: 12px 0 0;
        padding: 0;
        list-style: none;
      }

      a {
        display: block;
        overflow: hidden;
        color: ${theme.text};
        font-size: 13px;
        font-weight: 800;
        line-height: 1.45;
        text-decoration: none;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      a:hover {
        color: #03c75a;
      }

      ${getSubtleScrollbarCss(".popup")}
      ${getSubtleScrollbarCss(".list")}
    </style>

    <aside class="popup" role="status" aria-live="polite">
      <div class="top">
        <div>
          <p class="eyebrow">DeepNews</p>
          <p class="title">유사 기사 추천</p>
        </div>
        <button class="close" type="button" title="닫기" aria-label="Close DeepNews recommendations popup">×</button>
      </div>
      <ul class="list">${items}</ul>
    </aside>
  `;

  shadow.querySelector(".close")?.addEventListener("click", (event) => {
    event.stopPropagation();
    markOverlayOpen("recommendations", false);
    host.remove();
  });

  applyStoredOverlayPosition(host);
  makeOverlayResizable(host, shadow.querySelector(".popup"));
  makeOverlayDraggable(host, shadow.querySelector(".top"));
}

function renderLoadingOverlays(openOverlays) {
  if (openOverlays?.keywords) {
    renderLoadingOverlay("keywords");
  }

  if (openOverlays?.keywordChart) {
    renderLoadingOverlay("keywordChart");
  }

  if (openOverlays?.summary) {
    renderLoadingOverlay("summary");
  }

  if (openOverlays?.recommendations) {
    renderLoadingOverlay("recommendations");
  }

  if (openOverlays?.adLikelihood) {
    renderLoadingOverlay("adLikelihood");
  }
}

function renderLoadingOverlay(name) {
  const config = getOverlayConfig(name);
  if (!config) {
    return;
  }

  const theme = getOverlayTheme();
  const existingHost = document.getElementById(config.hostId);
  const host = existingHost || document.createElement("div");

  if (!existingHost) {
    host.id = config.hostId;
    host.dataset.positionStorageKey = config.positionStorageKey;
    document.documentElement.appendChild(host);
  }

  const shadow = host.shadowRoot || host.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      :host {
        all: initial;
        position: fixed;
        right: 18px;
        top: ${config.top}px;
        z-index: ${config.zIndex};
        font-family: "Segoe UI", "Malgun Gothic", sans-serif;
      }

      .popup {
        width: min(${config.width}px, calc(100vw - 36px));
        padding: 14px;
        border: 1px solid ${theme.border};
        border-radius: 16px;
        background: ${theme.surface};
        color: ${theme.text};
        box-shadow: ${theme.shadow};
        backdrop-filter: blur(12px);
      }

      .top {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        cursor: grab;
        user-select: none;
        touch-action: none;
      }

      .eyebrow {
        margin: 0 0 4px;
        color: #03c75a;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }

      .title {
        margin: 0;
        font-size: 15px;
        font-weight: 800;
        line-height: 1.35;
      }

      .close {
        flex: 0 0 auto;
        width: 26px;
        height: 26px;
        border: 0;
        border-radius: 50%;
        background: transparent;
        color: ${theme.close};
        cursor: pointer;
        font-size: 18px;
        line-height: 1;
      }

      .close:hover {
        background: ${theme.closeHoverBg};
        color: ${theme.closeHover};
      }

      .loading {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 12px 0 0;
        color: ${theme.muted};
        font-size: 13px;
        font-weight: 800;
        line-height: 1.45;
      }

      .spinner {
        width: 14px;
        height: 14px;
        border: 2px solid ${theme.track};
        border-top-color: #03c75a;
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
      }

      @keyframes spin {
        to {
          transform: rotate(360deg);
        }
      }

      ${getSubtleScrollbarCss(".popup")}
    </style>

    <aside class="popup" role="status" aria-live="polite">
      <div class="top">
        <div>
          <p class="eyebrow">DeepNews</p>
          <p class="title">${config.title}</p>
        </div>
        <button class="close" type="button" title="닫기" aria-label="Close DeepNews loading popup">×</button>
      </div>
      <p class="loading"><span class="spinner" aria-hidden="true"></span>새 기사 분석 중입니다.</p>
    </aside>
  `;

  shadow.querySelector(".close")?.addEventListener("click", (event) => {
    event.stopPropagation();
    markOverlayOpen(name, false);
    host.remove();
  });

  applyStoredOverlayPosition(host);
  makeOverlayResizable(host, shadow.querySelector(".popup"));
  makeOverlayDraggable(host, shadow.querySelector(".top"));
}

function getOverlayConfig(name) {
  const configs = {
    adLikelihood: {
      hostId: OVERLAY_HOST_ID,
      positionStorageKey: OVERLAY_POSITION_STORAGE_KEY,
      title: "광고성 판단",
      top: 18,
      width: 280,
      zIndex: BASE_OVERLAY_Z_INDEX + 7
    },
    keywords: {
      hostId: KEYWORD_OVERLAY_HOST_ID,
      positionStorageKey: KEYWORD_OVERLAY_POSITION_STORAGE_KEY,
      title: "핵심 키워드",
      top: 168,
      width: 280,
      zIndex: BASE_OVERLAY_Z_INDEX + 6
    },
    keywordChart: {
      hostId: KEYWORD_CHART_OVERLAY_HOST_ID,
      positionStorageKey: KEYWORD_CHART_OVERLAY_POSITION_STORAGE_KEY,
      title: "키워드 빈도",
      top: 318,
      width: 300,
      zIndex: BASE_OVERLAY_Z_INDEX + 5
    },
    summary: {
      hostId: SUMMARY_OVERLAY_HOST_ID,
      positionStorageKey: SUMMARY_OVERLAY_POSITION_STORAGE_KEY,
      title: "AI 요약",
      top: 468,
      width: 320,
      zIndex: BASE_OVERLAY_Z_INDEX + 4
    },
    recommendations: {
      hostId: RECOMMENDATIONS_OVERLAY_HOST_ID,
      positionStorageKey: RECOMMENDATIONS_OVERLAY_POSITION_STORAGE_KEY,
      title: "유사 기사 추천",
      top: 608,
      width: 320,
      zIndex: BASE_OVERLAY_Z_INDEX + 3
    }
  };

  return configs[name] || null;
}

function getKeywordOverlaySize(keywords) {
  const count = Math.min(keywords.length, 8);
  return {
    width: count >= 6 ? 360 : 320,
    maxHeight: Math.min(420, 150 + count * 34)
  };
}

function getSummaryOverlaySize(summary) {
  const length = summary.length;
  return {
    width: length > 420 ? 560 : length > 220 ? 480 : 380,
    maxHeight: length > 420 ? 620 : length > 220 ? 500 : 360
  };
}

function getRecommendationsOverlaySize(recommendations) {
  const count = Math.min(recommendations.length, 5);
  return {
    width: 420,
    maxHeight: Math.min(440, 150 + count * 48)
  };
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => {
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

function makeOverlayDraggable(host, handle) {
  if (!handle) {
    return;
  }

  styleDragHandle(handle);
  makeOverlayFocusable(host);

  handle.addEventListener("pointerdown", (event) => {
    if (event.target?.closest?.(".close")) {
      return;
    }

    if (event.button !== 0) {
      return;
    }

    bringOverlayToFront(host);
    const startRect = host.getBoundingClientRect();
    const startX = event.clientX;
    const startY = event.clientY;

    host.dataset.dragging = "true";
    handle.setPointerCapture?.(event.pointerId);

    const moveOverlay = (moveEvent) => {
      const nextLeft = startRect.left + moveEvent.clientX - startX;
      const nextTop = startRect.top + moveEvent.clientY - startY;
      applyOverlayPosition(host, nextLeft, nextTop);
    };

    const stopDrag = () => {
      host.dataset.dragging = "false";
      document.removeEventListener("pointermove", moveOverlay);
      document.removeEventListener("pointerup", stopDrag);
      persistOverlayPosition(host);
    };

    document.addEventListener("pointermove", moveOverlay);
    document.addEventListener("pointerup", stopDrag, { once: true });
  });
}

function styleDragHandle(handle) {
  const theme = getOverlayTheme();
  handle.title = "드래그해서 이동";
  handle.style.margin = "-6px -6px 0";
  handle.style.padding = "8px 10px";
  handle.style.border = `1px solid ${theme.border}`;
  handle.style.borderRadius = "12px";
  handle.style.background =
    currentTheme === "dark" ? "rgba(255, 255, 255, 0.06)" : "rgba(3, 199, 90, 0.07)";
  handle.style.boxShadow =
    currentTheme === "dark"
      ? "inset 0 -1px 0 rgba(255, 255, 255, 0.04)"
      : "inset 0 -1px 0 rgba(31, 35, 40, 0.04)";
}

function makeOverlayFocusable(host) {
  if (host.dataset.deepnewsFocusable === "true") {
    bringOverlayToFront(host);
    return;
  }

  host.dataset.deepnewsFocusable = "true";
  bringOverlayToFront(host);
  host.addEventListener("pointerdown", () => {
    bringOverlayToFront(host);
  });
}

function bringOverlayToFront(host) {
  overlayZIndex += 1;
  if (overlayZIndex > BASE_OVERLAY_Z_INDEX + 500) {
    overlayZIndex = BASE_OVERLAY_Z_INDEX + 20;
  }
  host.style.zIndex = String(overlayZIndex);
}

function makeOverlayResizable(host, popup) {
  if (!popup) {
    return;
  }

  makeOverlayFocusable(host);
  popup.style.boxSizing = "border-box";
  popup.style.resize = "both";
  popup.style.overflowX = "hidden";
  popup.style.overflowY = "auto";
  popup.style.minWidth = "220px";
  popup.style.minHeight = "110px";
  popup.style.maxWidth = "calc(100vw - 24px)";
  popup.style.maxHeight = "calc(100vh - 24px)";
  popup.addEventListener("pointerdown", (event) => {
    const rect = popup.getBoundingClientRect();
    const isResizeCorner =
      event.clientX >= rect.right - 18 && event.clientY >= rect.bottom - 18;

    if (!isResizeCorner) {
      return;
    }

    host.dataset.resizing = "true";
    const stopResize = () => {
      host.dataset.resizing = "false";
      persistOverlaySize(host, popup);
      document.removeEventListener("pointerup", stopResize);
    };

    document.addEventListener("pointerup", stopResize);
  });

  const storageKey = getOverlaySizeStorageKey(host);
  safeStorageGet(storageKey, (stored) => {
    const size = stored?.[storageKey];
    if (!size?.manual) {
      return;
    }

    if (Number.isFinite(size.width)) {
      popup.style.width = `${size.width}px`;
    }

    if (Number.isFinite(size.height)) {
      popup.style.height = `${size.height}px`;
    }
  });

  let persistTimer = null;
  const observer = new ResizeObserver((entries) => {
    const entry = entries[0];
    if (!entry || host.dataset.resizing !== "true") {
      return;
    }

    window.clearTimeout(persistTimer);
    persistTimer = window.setTimeout(() => {
      persistOverlaySize(host, popup);
      scheduleOverlayViewportCheck();
    }, 120);
  });

  observer.observe(popup);
}

function persistOverlaySize(host, popup) {
  const rect = popup.getBoundingClientRect();
  safeStorageSet({
    [getOverlaySizeStorageKey(host)]: {
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      manual: true
    }
  });
}

function getSubtleScrollbarCss(selector) {
  return `
    ${selector} {
      scrollbar-width: thin;
      scrollbar-color: transparent transparent;
    }

    ${selector}:hover {
      scrollbar-color: rgba(3, 199, 90, 0.28) transparent;
    }

    ${selector}::-webkit-scrollbar {
      width: 6px;
      height: 6px;
    }

    ${selector}::-webkit-scrollbar-track {
      background: transparent;
    }

    ${selector}::-webkit-scrollbar-thumb {
      border-radius: 999px;
      background: transparent;
    }

    ${selector}:hover::-webkit-scrollbar-thumb {
      background: rgba(3, 199, 90, 0.28);
    }

    ${selector}:hover::-webkit-scrollbar-thumb:hover {
      background: rgba(3, 199, 90, 0.44);
    }
  `;
}

function getOverlaySizeStorageKey(host) {
  return `deepnews.overlaySize.${host.id || "default"}`;
}

function applyOverlayPosition(host, left, top) {
  const { left: boundedLeft, top: boundedTop } = getBoundedOverlayPosition(host, left, top);

  host.style.left = `${boundedLeft}px`;
  host.style.top = `${boundedTop}px`;
  host.style.right = "auto";
  host.style.bottom = "auto";
}

function keepOverlaysInViewport() {
  getOverlayHosts().forEach((host) => {
    if (!host || host.dataset.dragging === "true") {
      return;
    }

    const storageKey = host.dataset.positionStorageKey || OVERLAY_POSITION_STORAGE_KEY;
    safeStorageGet(storageKey, (stored) => {
      const savedPosition = stored?.[storageKey];

      if (savedPosition) {
        applyOverlayPosition(host, savedPosition.left, savedPosition.top);
        return;
      }

      if (!host.style.left) {
        return;
      }

      const rect = host.getBoundingClientRect();
      applyOverlayPosition(host, rect.left, rect.top);
    });
  });
}

function scheduleOverlayViewportCheck() {
  window.clearTimeout(resizeRepositionTimer);
  resizeRepositionTimer = window.setTimeout(keepOverlaysInViewport, 80);
}

function getBoundedOverlayPosition(host, left, top) {
  const rect = host.getBoundingClientRect();
  const edgeMargin = 12;
  const maxLeft = Math.max(edgeMargin, window.innerWidth - rect.width - edgeMargin);
  const maxTop = Math.max(edgeMargin, window.innerHeight - rect.height - edgeMargin);

  return {
    left: Math.min(Math.max(edgeMargin, left), maxLeft),
    top: Math.min(Math.max(edgeMargin, top), maxTop)
  };
}

function persistOverlayPosition(host) {
  const rect = host.getBoundingClientRect();
  const storageKey = host.dataset.positionStorageKey || OVERLAY_POSITION_STORAGE_KEY;
  safeStorageSet({
    [storageKey]: {
      left: Math.round(rect.left),
      top: Math.round(rect.top)
    }
  });
}

function applyStoredOverlayPosition(host) {
  const storageKey = host.dataset.positionStorageKey || OVERLAY_POSITION_STORAGE_KEY;
  safeStorageGet(storageKey, (stored) => {
    const position = stored?.[storageKey];

    if (!position || host.dataset.dragging === "true") {
      return;
    }

    applyOverlayPosition(host, position.left, position.top);
  });
}

async function initializeTheme() {
  const stored = await safeStorageGetAsync(THEME_STORAGE_KEY);
  currentTheme = normalizeTheme(stored?.[THEME_STORAGE_KEY]);
}

function normalizeTheme(theme) {
  return theme === "dark" ? "dark" : "light";
}

function getOverlayTheme() {
  if (currentTheme === "dark") {
    return {
      surface: "rgba(17, 20, 23, 0.94)",
      text: "#f3f5f7",
      muted: "rgba(243, 245, 247, 0.78)",
      border: "rgba(255, 255, 255, 0.12)",
      shadow: "0 18px 42px rgba(0, 0, 0, 0.28)",
      close: "rgba(243, 245, 247, 0.68)",
      closeHover: "#ffffff",
      closeHoverBg: "rgba(255, 255, 255, 0.1)",
      track: "rgba(255, 255, 255, 0.12)"
    };
  }

  return {
    surface: "rgba(255, 255, 255, 0.96)",
    text: "#1f2328",
    muted: "rgba(31, 35, 40, 0.7)",
    border: "rgba(31, 35, 40, 0.1)",
    shadow: "0 18px 42px rgba(15, 23, 42, 0.16)",
    close: "rgba(31, 35, 40, 0.58)",
    closeHover: "#1f2328",
    closeHoverBg: "rgba(31, 35, 40, 0.08)",
    track: "rgba(31, 35, 40, 0.1)"
  };
}

function rerenderVisibleOverlays() {
  if (document.getElementById(OVERLAY_HOST_ID) && latestAdLikelihood) {
    renderAdLikelihoodOverlay(latestAdLikelihood);
  }

  if (document.getElementById(KEYWORD_OVERLAY_HOST_ID) && latestKeywords.length) {
    renderKeywordOverlay(latestKeywords);
  }

  if (document.getElementById(KEYWORD_CHART_OVERLAY_HOST_ID) && latestKeywordChart.length) {
    renderKeywordChartOverlay(latestKeywordChart);
  }

  if (document.getElementById(SUMMARY_OVERLAY_HOST_ID) && latestSummary) {
    renderSummaryOverlay(latestSummary);
  }

  if (document.getElementById(RECOMMENDATIONS_OVERLAY_HOST_ID) && latestRecommendations.length) {
    renderRecommendationsOverlay(latestRecommendations);
  }
}

function hideAllOverlays() {
  safeStorageSet({
    [OPEN_OVERLAYS_STORAGE_KEY]: {
      keywords: false,
      keywordChart: false,
      summary: false,
      recommendations: false,
      adLikelihood: false
    }
  });
  getOverlayHosts().forEach((host) => host?.remove());
}

function hideOverlay(name) {
  const config = getOverlayConfig(name);
  if (!config) {
    return;
  }

  markOverlayOpen(name, false);
  document.getElementById(config.hostId)?.remove();
}

function markOverlayOpen(name, isOpen) {
  safeStorageGet(OPEN_OVERLAYS_STORAGE_KEY, (stored) => {
    safeStorageSet({
      [OPEN_OVERLAYS_STORAGE_KEY]: {
        ...(stored?.[OPEN_OVERLAYS_STORAGE_KEY] || {}),
        [name]: isOpen
      }
    });
  });
}

function getOverlayHosts() {
  return [
    document.getElementById(OVERLAY_HOST_ID),
    document.getElementById(KEYWORD_OVERLAY_HOST_ID),
    document.getElementById(KEYWORD_CHART_OVERLAY_HOST_ID),
    document.getElementById(SUMMARY_OVERLAY_HOST_ID),
    document.getElementById(RECOMMENDATIONS_OVERLAY_HOST_ID)
  ];
}

function registerExtensionListeners() {
  if (!hasValidExtensionContext()) {
    return;
  }

  try {
    chrome.storage.onChanged.addListener((changes, areaName) => {
      if (areaName !== "local" || !changes[THEME_STORAGE_KEY]) {
        return;
      }

      currentTheme = normalizeTheme(changes[THEME_STORAGE_KEY].newValue);
      rerenderVisibleOverlays();
    });

    chrome.runtime.onMessage.addListener((message) => {
      if (message?.type === "HIGHLIGHT_KEYWORDS") {
        highlightKeywords(message.payload?.keywords || []);
      }

      if (message?.type === SHOW_AD_LIKELIHOOD) {
        renderAdLikelihoodOverlay(message.payload?.adLikelihood);
      }

      if (message?.type === SHOW_KEYWORDS) {
        renderKeywordOverlay(message.payload?.keywords || []);
      }

      if (message?.type === SHOW_KEYWORD_CHART) {
        renderKeywordChartOverlay(message.payload?.keywords || []);
      }

      if (message?.type === SHOW_SUMMARY) {
        renderSummaryOverlay(message.payload?.summary || "");
      }

      if (message?.type === SHOW_RECOMMENDATIONS) {
        renderRecommendationsOverlay(message.payload?.recommendations || []);
      }

      if (message?.type === SHOW_LOADING_OVERLAYS) {
        renderLoadingOverlays(message.payload?.openOverlays || {});
      }

      if (message?.type === HIDE_OVERLAY) {
        hideOverlay(message.payload?.name || "");
      }

      if (message?.type === HIDE_ALL_OVERLAYS) {
        hideAllOverlays();
      }
    });
  } catch {
    // Existing page scripts can outlive the extension context during development reloads.
  }
}

function safeRuntimeSendMessage(message) {
  if (!hasValidExtensionContext()) {
    return;
  }

  try {
    chrome.runtime.sendMessage(message);
  } catch {
    // Ignore stale content scripts after extension reload.
  }
}

function safeStorageSet(value) {
  if (!hasValidExtensionContext()) {
    return;
  }

  try {
    chrome.storage.local.set(value);
  } catch {
    // Ignore stale content scripts after extension reload.
  }
}

function safeStorageGet(key, callback) {
  if (!hasValidExtensionContext()) {
    callback({});
    return;
  }

  try {
    chrome.storage.local.get(key, callback);
  } catch {
    callback({});
  }
}

async function safeStorageGetAsync(key) {
  if (!hasValidExtensionContext()) {
    return {};
  }

  try {
    return await chrome.storage.local.get(key);
  } catch {
    return {};
  }
}

function hasValidExtensionContext() {
  try {
    return Boolean(chrome?.runtime?.id);
  } catch {
    return false;
  }
}
})();
