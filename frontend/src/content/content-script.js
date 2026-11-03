(() => {
if (globalThis.__deepnewsContentScriptLoaded) {
  return;
}

globalThis.__deepnewsContentScriptLoaded = true;

const NAVER_BODY_SELECTORS = [
  "#dic_area",
  "#comp_news_article",
  "#newsct_article",
  ".newsct_article"
];

const GENERIC_BODY_SELECTORS = [
  "#news-contents",
  '[itemprop="articleBody"]',
  "#articleBody",
  "#article-view-content-div",
  "#articletxt",
  ".article_body",
  ".article-body",
  ".news_text",
  ".view_con",
  "#CmAdContent",
  "#cont_newstext",
  "#article_body",
  ".article_txt",
  ".text_area",
  "article"
];
// Inline elements whose text belongs to the surrounding block (YTN puts the whole body in one <div> of <span>s and <br>s).
const INLINE_TAGS = new Set(["SPAN", "B", "STRONG", "EM", "I", "U", "A", "FONT", "MARK", "SMALL", "SUB", "SUP", "BR"]);
const NON_ARTICLE_ANCESTORS = "nav, header, footer, aside, [role='navigation'], [data-deepnews-overlay]";

const HIGHLIGHT_CLASS = "deepnews-highlight";
const MAX_HIGHLIGHT_TERMS = 40;
// Same minimum as the article extractor, so tiny teaser blocks are never mistaken for the body.
const MIN_ARTICLE_TEXT_LENGTH = 100;
const SKIPPED_TEXT_PARENTS = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEXTAREA", "TEMPLATE", "MARK"]);
const SHOW_AD_LIKELIHOOD = "SHOW_AD_LIKELIHOOD";
const SHOW_KEYWORDS = "SHOW_KEYWORDS";
const SHOW_KEYWORD_CHART = "SHOW_KEYWORD_CHART";
const SHOW_SUMMARY = "SHOW_SUMMARY";
const SHOW_RECOMMENDATIONS = "SHOW_RECOMMENDATIONS";
const SHOW_LOADING_OVERLAYS = "SHOW_LOADING_OVERLAYS";
const HIDE_LOADING_OVERLAYS = "HIDE_LOADING_OVERLAYS";
const HIDE_OVERLAY = "HIDE_OVERLAY";
const HIDE_ALL_OVERLAYS = "HIDE_ALL_OVERLAYS";
const OVERLAY_CLOSED = "OVERLAY_CLOSED";
const THEME_STORAGE_KEY = "deepnews.theme";
const BASE_OVERLAY_Z_INDEX = 2147483000;

const OVERLAY_CONFIGS = {
  adLikelihood: {
    sizeKey: "deepnews-ad-likelihood-overlay",
    positionStorageKey: "deepnews.adLikelihoodOverlayPosition",
    title: "광고성 판단",
    top: 18,
    width: 280,
    zIndex: BASE_OVERLAY_Z_INDEX + 7
  },
  keywords: {
    sizeKey: "deepnews-keyword-overlay",
    positionStorageKey: "deepnews.keywordOverlayPosition",
    title: "핵심 키워드",
    top: 168,
    width: 280,
    zIndex: BASE_OVERLAY_Z_INDEX + 6
  },
  keywordChart: {
    sizeKey: "deepnews-keyword-chart-overlay",
    positionStorageKey: "deepnews.keywordChartOverlayPosition",
    title: "키워드 빈도",
    top: 318,
    width: 300,
    zIndex: BASE_OVERLAY_Z_INDEX + 5
  },
  summary: {
    sizeKey: "deepnews-summary-overlay",
    positionStorageKey: "deepnews.summaryOverlayPosition",
    title: "AI 요약",
    top: 468,
    width: 320,
    zIndex: BASE_OVERLAY_Z_INDEX + 4
  },
  recommendations: {
    sizeKey: "deepnews-recommendations-overlay",
    positionStorageKey: "deepnews.recommendationsOverlayPosition",
    title: "유사 기사 추천",
    top: 608,
    width: 320,
    zIndex: BASE_OVERLAY_Z_INDEX + 3
  }
};

// Hosts and their closed shadow roots live only here, never looked up from the page DOM.
const overlays = new Map();
let resizeRepositionTimer = null;
let overlayZIndex = BASE_OVERLAY_Z_INDEX + 20;
let currentTheme = "light";

void bootstrap();
window.addEventListener("resize", scheduleOverlayViewportCheck);

async function bootstrap() {
  await initializeTheme();
  injectHighlightStyle();
}

registerExtensionListeners();

function findArticleRoot() {
  const naverBody = document.querySelector(NAVER_BODY_SELECTORS.join(","));
  if (naverBody) {
    return naverBody;
  }

  for (const selector of GENERIC_BODY_SELECTORS) {
    const best = largestByText(document.querySelectorAll(selector));
    if (best && textLength(best) >= MIN_ARTICLE_TEXT_LENGTH) {
      return best;
    }
  }

  // Fall back to the block holding the most text. Paragraphs count toward their parent, so
  // <p>-per-paragraph articles and single-<div> articles are both found.
  const textByBlock = new Map();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const length = node.nodeValue.replace(/\s+/g, "").length;
    if (!length || SKIPPED_TEXT_PARENTS.has(node.parentElement?.tagName)) continue;
    let block = node.parentElement;
    while (block && INLINE_TAGS.has(block.tagName)) block = block.parentElement;
    if (block?.tagName === "P") block = block.parentElement;
    if (!block || block === document.body || block.closest(NON_ARTICLE_ANCESTORS)) continue;
    textByBlock.set(block, (textByBlock.get(block) || 0) + length);
  }

  let bestBlock = null;
  let bestLength = 0;
  for (const [block, length] of textByBlock) {
    if (length > bestLength) {
      bestBlock = block;
      bestLength = length;
    }
  }
  return bestLength >= MIN_ARTICLE_TEXT_LENGTH ? bestBlock : null;
}

function largestByText(nodes) {
  let best = null;
  let bestLength = 0;
  for (const node of nodes) {
    const length = textLength(node);
    if (length > bestLength) {
      best = node;
      bestLength = length;
    }
  }
  return best;
}

function textLength(node) {
  return (node.textContent || "").replace(/\s+/g, "").length;
}

function highlightKeywords(keywords) {
  removeExistingHighlights();

  const terms = [...new Set(keywords.map((keyword) => String(keyword || "").trim()).filter(Boolean))]
    .sort((left, right) => right.length - left.length)
    .slice(0, MAX_HIGHLIGHT_TERMS);
  const articleNode = findArticleRoot();
  if (!articleNode || !terms.length) {
    return;
  }

  // One alternation with the longest terms first, so "인공지능" wins over "인공" at the same position.
  const pattern = new RegExp(terms.map(escapeRegExp).join("|"), "gi");
  const walker = document.createTreeWalker(articleNode, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.nodeValue?.trim() || SKIPPED_TEXT_PARENTS.has(node.parentElement?.tagName)) {
        return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    }
  });
  const textNodes = [];

  while (walker.nextNode()) {
    textNodes.push(walker.currentNode);
  }

  for (const node of textNodes) {
    const text = node.nodeValue;
    const fragment = document.createDocumentFragment();
    let lastIndex = 0;
    pattern.lastIndex = 0;

    for (let match = pattern.exec(text); match; match = pattern.exec(text)) {
      if (match.index > lastIndex) {
        fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
      }
      const mark = document.createElement("mark");
      mark.className = HIGHLIGHT_CLASS;
      mark.textContent = match[0];
      fragment.appendChild(mark);
      lastIndex = match.index + match[0].length;
    }

    if (lastIndex === 0) {
      continue;
    }

    if (lastIndex < text.length) {
      fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
    }
    node.parentNode?.replaceChild(fragment, node);
  }
}

function removeExistingHighlights() {
  const parents = new Set();
  document.querySelectorAll(`mark.${HIGHLIGHT_CLASS}`).forEach((mark) => {
    if (mark.parentNode) parents.add(mark.parentNode);
    mark.replaceWith(document.createTextNode(mark.textContent || ""));
  });
  parents.forEach((parent) => parent.normalize());
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

// Builds the overlay frame. Only extension-owned constants reach this markup; page and server data
// are inserted afterwards with textContent/createElement by the caller.
function mountOverlay(name, { extraCss = "", loading = false, data = null }) {
  const config = OVERLAY_CONFIGS[name];
  const theme = getOverlayTheme();
  let entry = overlays.get(name);

  if (!entry || !entry.host.isConnected) {
    const host = document.createElement("div");
    host.setAttribute("data-deepnews-overlay", "");
    const shadow = host.attachShadow({ mode: "closed" });
    entry = { name, config, host, shadow, dragging: false, resizing: false, focusable: false };
    overlays.set(name, entry);
    document.documentElement.appendChild(host);
  }

  entry.loading = loading;
  entry.data = data;
  entry.shadow.innerHTML = `
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

      .top:active {
        cursor: grabbing;
      }

      .heading {
        flex: 1 1 auto;
        min-width: 0;
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

      ${extraCss}
      ${getSubtleScrollbarCss(".popup")}
    </style>

    <aside class="popup" aria-label="DeepNews ${config.title}">
      <div class="top">
        <div class="heading">
          <p class="eyebrow">DeepNews</p>
          <p class="title">${config.title}</p>
        </div>
        <button class="close" type="button" title="닫기" aria-label="${config.title} 팝업 닫기">×</button>
      </div>
      <div class="content"></div>
    </aside>
  `;

  const popup = entry.shadow.querySelector(".popup");
  entry.shadow.querySelector(".close")?.addEventListener("click", (event) => {
    event.stopPropagation();
    removeOverlay(name);
    safeRuntimeSendMessage({ type: OVERLAY_CLOSED, payload: { name } });
  });

  applyStoredOverlayPosition(entry);
  makeOverlayResizable(entry, popup);
  makeOverlayDraggable(entry, entry.shadow.querySelector(".top"));

  return {
    popup,
    top: entry.shadow.querySelector(".top"),
    content: entry.shadow.querySelector(".content")
  };
}

function createElement(tagName, className = "", text = "") {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  if (text) element.textContent = text;
  return element;
}

function adScoreView(adLikelihood) {
  const rawScore = Number(adLikelihood?.score);
  if (!Number.isFinite(rawScore) || rawScore < 0) {
    return { analyzed: false, percent: 0, text: "미분석", color: "#9aa4ad", label: adLikelihood?.label || "아직 광고성을 분석하지 않았습니다." };
  }

  const score = Math.min(rawScore, 1);
  // Same bands as the backend ad_label_for: >=0.8 high, >=0.4 needs review.
  const color = score >= 0.8 ? "#ff6b6b" : score >= 0.4 ? "#ffb84d" : "#4ade80";
  const percent = Math.round(score * 100);
  return { analyzed: true, percent, text: `${percent}%`, color, label: adLikelihood?.label || "" };
}

function renderAdLikelihoodOverlay(adLikelihood) {
  if (!adLikelihood) {
    return;
  }

  const theme = getOverlayTheme();
  const view = adScoreView(adLikelihood);
  const { top, content } = mountOverlay("adLikelihood", {
    data: adLikelihood,
    extraCss: `
      .top {
        align-items: center;
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
          conic-gradient(var(--score-color) 0 var(--score), ${theme.track} var(--score) 100%);
        color: var(--score-color);
        font-size: 17px;
        font-weight: 900;
        line-height: 1;
      }

      .donut.unanalyzed {
        font-size: 13px;
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
    `
  });

  const donut = createElement("strong", view.analyzed ? "donut" : "donut unanalyzed");
  donut.style.setProperty("--score", `${view.percent}%`);
  donut.style.setProperty("--score-color", view.color);
  donut.setAttribute("aria-label", view.analyzed ? `광고성 ${view.text}` : "광고성 미분석");
  donut.appendChild(createElement("span", "", view.text));
  top.insertBefore(donut, top.querySelector(".close"));
  content.appendChild(createElement("p", "label", view.label));
}

function renderKeywordOverlay(keywords) {
  if (!keywords.length) {
    return;
  }

  const theme = getOverlayTheme();
  const { content } = mountOverlay("keywords", {
    data: keywords,
    extraCss: `
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
    `
  });

  const pills = createElement("div", "pills");
  for (const keyword of keywords.slice(0, 8)) {
    pills.appendChild(createElement("span", "pill", keywordTerm(keyword)));
  }
  content.appendChild(pills);
}

function renderKeywordChartOverlay(keywords) {
  if (!keywords.length) {
    return;
  }

  const theme = getOverlayTheme();
  const overlaySize = getKeywordOverlaySize(keywords);
  const max = Math.max(...keywords.map(keywordCount), 1);
  const { popup, content } = mountOverlay("keywordChart", {
    data: keywords,
    extraCss: `
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

      .count {
        color: ${theme.muted};
        font-size: 12px;
        font-weight: 900;
        text-align: right;
      }
    `
  });
  applyOverlaySize(popup, overlaySize);

  const chart = createElement("div", "chart");
  for (const keyword of keywords.slice(0, 8)) {
    const count = keywordCount(keyword);
    const row = createElement("div", "bar-row");
    const track = createElement("div", "bar-track");
    const fill = createElement("div", "bar-fill");
    fill.style.width = `${Math.round((count / max) * 100)}%`;
    track.appendChild(fill);
    row.append(createElement("span", "term", keywordTerm(keyword)), track, createElement("strong", "count", String(count)));
    chart.appendChild(row);
  }
  content.appendChild(chart);
}

function renderSummaryOverlay(summary) {
  const normalizedSummary = String(summary || "").trim();
  if (!normalizedSummary) {
    return;
  }

  const theme = getOverlayTheme();
  const { popup, content } = mountOverlay("summary", {
    data: normalizedSummary,
    extraCss: `
      .popup {
        display: flex;
        flex-direction: column;
      }

      .content {
        display: flex;
        flex: 1 1 auto;
        min-height: 0;
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

      ${getSubtleScrollbarCss(".body")}
    `
  });
  applyOverlaySize(popup, getSummaryOverlaySize(normalizedSummary));
  content.appendChild(createElement("p", "body", normalizedSummary));
}

function renderRecommendationsOverlay(recommendations) {
  if (!recommendations.length) {
    return;
  }

  const theme = getOverlayTheme();
  const { popup, content } = mountOverlay("recommendations", {
    data: recommendations,
    extraCss: `
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

      .reason {
        display: block;
        margin-top: 2px;
        color: ${theme.text};
        font-size: 11px;
        opacity: 0.62;
      }

      ${getSubtleScrollbarCss(".list")}
    `
  });
  applyOverlaySize(popup, getRecommendationsOverlaySize(recommendations));

  const list = createElement("ul", "list");
  for (const item of recommendations.slice(0, 5)) {
    const listItem = document.createElement("li");
    const link = createElement("a", "", String(item?.title || "관련 기사"));
    // Recommendation URLs are server data; only http(s) may become a link.
    if (isHttpUrl(item?.url)) {
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noreferrer";
    }
    listItem.appendChild(link);
    if (Array.isArray(item?.reasons) && item.reasons.length) {
      listItem.appendChild(createElement("span", "reason", item.reasons.map(String).join(" · ")));
    }
    list.appendChild(listItem);
  }
  content.appendChild(list);
}

function renderLoadingOverlays(openOverlays) {
  for (const name of Object.keys(OVERLAY_CONFIGS)) {
    if (openOverlays?.[name]) {
      renderLoadingOverlay(name);
    }
  }
}

function renderLoadingOverlay(name) {
  if (!OVERLAY_CONFIGS[name]) {
    return;
  }

  const theme = getOverlayTheme();
  const { content } = mountOverlay(name, {
    loading: true,
    extraCss: `
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
    `
  });

  const status = createElement("p", "loading");
  status.setAttribute("role", "status");
  const spinner = createElement("span", "spinner");
  spinner.setAttribute("aria-hidden", "true");
  status.append(spinner, document.createTextNode("새 기사 분석 중입니다."));
  content.appendChild(status);
}

function keywordTerm(keyword) {
  return String(typeof keyword === "string" ? keyword : keyword?.term || "");
}

function keywordCount(keyword) {
  const count = typeof keyword === "string" ? 1 : Number(keyword?.count) || 1;
  return Math.max(count, 1);
}

function isHttpUrl(url) {
  try { return ["http:", "https:"].includes(new URL(url).protocol); }
  catch { return false; }
}

function applyOverlaySize(popup, size) {
  // A manually resized width restored from storage arrives later and overrides this default.
  popup.style.width = `min(${size.width}px, calc(100vw - 36px))`;
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

function makeOverlayDraggable(entry, handle) {
  if (!handle) {
    return;
  }

  const { host } = entry;
  styleDragHandle(handle);
  makeOverlayFocusable(entry);

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

    entry.dragging = true;
    handle.setPointerCapture?.(event.pointerId);

    const moveOverlay = (moveEvent) => {
      const nextLeft = startRect.left + moveEvent.clientX - startX;
      const nextTop = startRect.top + moveEvent.clientY - startY;
      applyOverlayPosition(host, nextLeft, nextTop);
    };

    const stopDrag = () => {
      entry.dragging = false;
      document.removeEventListener("pointermove", moveOverlay);
      document.removeEventListener("pointerup", stopDrag);
      persistOverlayPosition(entry);
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

function makeOverlayFocusable(entry) {
  bringOverlayToFront(entry.host);
  if (entry.focusable) {
    return;
  }

  entry.focusable = true;
  entry.host.addEventListener("pointerdown", () => {
    bringOverlayToFront(entry.host);
  });
}

function bringOverlayToFront(host) {
  overlayZIndex += 1;
  if (overlayZIndex > BASE_OVERLAY_Z_INDEX + 500) {
    overlayZIndex = BASE_OVERLAY_Z_INDEX + 20;
  }
  host.style.zIndex = String(overlayZIndex);
}

function makeOverlayResizable(entry, popup) {
  if (!popup) {
    return;
  }

  makeOverlayFocusable(entry);
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

    entry.resizing = true;
    const stopResize = () => {
      entry.resizing = false;
      persistOverlaySize(entry, popup);
      document.removeEventListener("pointerup", stopResize);
    };

    document.addEventListener("pointerup", stopResize);
  });

  const storageKey = getOverlaySizeStorageKey(entry);
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
    if (!entries[0] || !entry.resizing) {
      return;
    }

    window.clearTimeout(persistTimer);
    persistTimer = window.setTimeout(() => {
      persistOverlaySize(entry, popup);
      scheduleOverlayViewportCheck();
    }, 120);
  });

  observer.observe(popup);
}

function persistOverlaySize(entry, popup) {
  const rect = popup.getBoundingClientRect();
  safeStorageSet({
    [getOverlaySizeStorageKey(entry)]: {
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

function getOverlaySizeStorageKey(entry) {
  return `deepnews.overlaySize.${entry.config.sizeKey}`;
}

function applyOverlayPosition(host, left, top) {
  const { left: boundedLeft, top: boundedTop } = getBoundedOverlayPosition(host, left, top);

  host.style.left = `${boundedLeft}px`;
  host.style.top = `${boundedTop}px`;
  host.style.right = "auto";
  host.style.bottom = "auto";
}

function keepOverlaysInViewport() {
  overlays.forEach((entry) => {
    const { host } = entry;
    if (!host.isConnected || entry.dragging) {
      return;
    }

    const storageKey = entry.config.positionStorageKey;
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

function persistOverlayPosition(entry) {
  const rect = entry.host.getBoundingClientRect();
  safeStorageSet({
    [entry.config.positionStorageKey]: {
      left: Math.round(rect.left),
      top: Math.round(rect.top)
    }
  });
}

function applyStoredOverlayPosition(entry) {
  const storageKey = entry.config.positionStorageKey;
  safeStorageGet(storageKey, (stored) => {
    const position = stored?.[storageKey];

    if (!position || entry.dragging) {
      return;
    }

    applyOverlayPosition(entry.host, position.left, position.top);
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

const OVERLAY_RENDERERS = {
  adLikelihood: renderAdLikelihoodOverlay,
  keywords: renderKeywordOverlay,
  keywordChart: renderKeywordChartOverlay,
  summary: renderSummaryOverlay,
  recommendations: renderRecommendationsOverlay
};

function rerenderVisibleOverlays() {
  for (const [name, entry] of [...overlays]) {
    if (!entry.host.isConnected) {
      overlays.delete(name);
    } else if (entry.loading) {
      renderLoadingOverlay(name);
    } else if (entry.data) {
      OVERLAY_RENDERERS[name](entry.data);
    }
  }
}

function removeOverlay(name) {
  overlays.get(name)?.host.remove();
  overlays.delete(name);
}

function hideAllOverlays() {
  for (const name of [...overlays.keys()]) {
    removeOverlay(name);
  }
}

function hideLoadingOverlays() {
  for (const [name, entry] of [...overlays]) {
    if (entry.loading) {
      removeOverlay(name);
    }
  }
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

    chrome.runtime.onMessage.addListener((message, sender) => {
      // Only the extension itself (service worker or panel) may drive the overlays.
      if (sender?.id !== chrome.runtime.id) {
        return;
      }

      const payload = message?.payload || {};
      switch (message?.type) {
        case "HIGHLIGHT_KEYWORDS":
          highlightKeywords(Array.isArray(payload.keywords) ? payload.keywords : []);
          break;
        case SHOW_AD_LIKELIHOOD:
          renderAdLikelihoodOverlay(payload.adLikelihood);
          break;
        case SHOW_KEYWORDS:
          renderKeywordOverlay(Array.isArray(payload.keywords) ? payload.keywords : []);
          break;
        case SHOW_KEYWORD_CHART:
          renderKeywordChartOverlay(Array.isArray(payload.keywords) ? payload.keywords : []);
          break;
        case SHOW_SUMMARY:
          renderSummaryOverlay(payload.summary || "");
          break;
        case SHOW_RECOMMENDATIONS:
          renderRecommendationsOverlay(Array.isArray(payload.recommendations) ? payload.recommendations : []);
          break;
        case SHOW_LOADING_OVERLAYS:
          renderLoadingOverlays(payload.openOverlays || {});
          break;
        case HIDE_LOADING_OVERLAYS:
          hideLoadingOverlays();
          break;
        case HIDE_OVERLAY:
          removeOverlay(payload.name || "");
          break;
        case HIDE_ALL_OVERLAYS:
          hideAllOverlays();
          break;
        default:
          break;
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
    void chrome.runtime.sendMessage(message)?.catch?.(() => {});
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
