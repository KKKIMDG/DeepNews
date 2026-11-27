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
const MOTION_STORAGE_KEY = "deepnews.motion";
const BASE_OVERLAY_Z_INDEX = 2147483000;

// Same values as panel.css (:root and [data-theme="dark"]) so the popups on the article match the side panel.
const OVERLAY_TOKENS = {
  light: {
    surface: "#ffffff",
    sunken: "#eceef7",
    ink: "#23308a",
    "on-ink": "#f4f5ff",
    text: "#171a30",
    muted: "#5b6286",
    line: "#dfe2f0",
    marker: "#ffe156",
    hl: "#ffe156",
    safe: "#138a64",
    caution: "#b86e0f",
    danger: "#cf3a45",
    focus: "#5a6cf0",
    shadow: "0 18px 42px rgba(23, 26, 48, 0.18)"
  },
  dark: {
    surface: "#181c39",
    sunken: "#20254a",
    ink: "#2d3a9c",
    "on-ink": "#f1f2ff",
    text: "#eceefb",
    muted: "#a0a7cc",
    line: "#2c325c",
    marker: "#f0cf3c",
    hl: "color-mix(in srgb, #f0cf3c 55%, transparent)",
    safe: "#46c897",
    caution: "#f0a54a",
    danger: "#ff7680",
    focus: "#93a0ff",
    shadow: "0 18px 42px rgba(0, 0, 0, 0.4)"
  }
};

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
    title: "추천 기사",
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
let motionEnabled = true;

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
      background: linear-gradient(transparent 52%, #ffe156 52%, #ffe156 92%, transparent 92%);
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
        ${overlayTokenCss()}
        font-family: "Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", "Segoe UI", sans-serif;
        font-size: 14px;
        line-height: 1.55;
      }

      /* The same card as the panel's .block, lifted off the article with a shadow. */
      .popup {
        box-sizing: border-box;
        width: min(${config.width}px, calc(100vw - 36px));
        padding: 14px 16px 16px;
        border: 1px solid var(--line);
        border-radius: 20px;
        background: var(--surface);
        color: var(--text);
        box-shadow: var(--shadow);
      }

      .top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        margin-bottom: 10px;
        cursor: grab;
        user-select: none;
        touch-action: none;
      }

      .top:active {
        cursor: grabbing;
      }

      .heading {
        display: flex;
        flex: 1 1 auto;
        align-items: center;
        gap: 8px;
        min-width: 0;
      }

      .brand {
        flex: 0 0 auto;
        padding: 2px 8px;
        border-radius: 999px;
        background: var(--ink);
        color: var(--on-ink);
        font-size: 11px;
        font-weight: 800;
      }

      .title {
        overflow: hidden;
        margin: 0;
        font-size: 15px;
        font-weight: 800;
        letter-spacing: -0.01em;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .close {
        flex: 0 0 auto;
        width: 28px;
        height: 28px;
        padding: 0;
        border: 1px solid var(--line);
        border-radius: 999px;
        background: var(--surface);
        color: var(--muted);
        cursor: pointer;
        font: inherit;
        font-size: 16px;
        line-height: 1;
      }

      .close:hover {
        border-color: var(--focus);
        color: var(--text);
      }

      .close:focus-visible,
      a:focus-visible {
        outline: 2px solid var(--focus);
        outline-offset: 2px;
      }

      .state {
        margin: 0;
        color: var(--muted);
        font-size: 13px;
      }

      ${extraCss}
      ${getSubtleScrollbarCss(".popup")}
      ${motionEnabled ? "" : "*, *::before, *::after { animation: none !important; transition: none !important; }"}
    </style>

    <aside class="popup" aria-label="DeepNews ${config.title}">
      <div class="top">
        <div class="heading">
          <span class="brand">DeepNews</span>
          <h2 class="title">${config.title}</h2>
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
    return { analyzed: false, ratio: 0, text: "미분석", tone: "score-none" };
  }

  const score = Math.min(rawScore, 1);
  // Same bands as the backend ad_label_for: >=0.8 high, >=0.4 needs review.
  const tone = score >= 0.8 ? "score-high" : score >= 0.4 ? "score-warn" : "score-good";
  const percent = `${Math.round(score * 100)}%`;
  // A sliver stays visible at 0% so "analyzed, not an ad" differs from "not analyzed" (as in the panel).
  return { analyzed: true, ratio: Math.max(score, 0.03), text: adLikelihood?.label ? `${adLikelihood.label} (${percent})` : percent, tone };
}

function renderAdLikelihoodOverlay(adLikelihood) {
  if (!adLikelihood) {
    return;
  }

  const view = adScoreView(adLikelihood);
  const { content } = mountOverlay("adLikelihood", {
    data: adLikelihood,
    extraCss: `
      .ad-likelihood {
        margin: 0;
        font-size: 16px;
        font-weight: 800;
      }

      .meter {
        overflow: hidden;
        height: 8px;
        margin-top: 8px;
        border-radius: 999px;
        background: var(--sunken);
      }

      .meter span {
        display: block;
        height: 100%;
        border-radius: inherit;
        background: var(--muted);
      }

      .score-good { color: var(--safe); }
      .score-warn { color: var(--caution); }
      .score-high { color: var(--danger); }
      .score-none { color: var(--muted); }
      .meter .score-good { background: var(--safe); }
      .meter .score-warn { background: var(--caution); }
      .meter .score-high { background: var(--danger); }
    `
  });

  content.appendChild(createElement("p", `ad-likelihood ${view.tone}`, view.text));
  const meter = createElement("div", "meter");
  meter.setAttribute("aria-hidden", "true");
  const fill = createElement("span", view.tone);
  fill.style.width = `${Math.round(view.ratio * 100)}%`;
  meter.appendChild(fill);
  content.appendChild(meter);
}

function renderKeywordOverlay(keywords) {
  if (!keywords.length) {
    return;
  }

  const { content } = mountOverlay("keywords", {
    data: keywords,
    extraCss: `
      /* Keywords read like words swiped with a highlighter, as in the panel. */
      .keyword-list {
        display: flex;
        flex-wrap: wrap;
        gap: 6px 10px;
      }

      .hl {
        padding: 0 3px;
        background: linear-gradient(transparent 52%, var(--hl) 52%, var(--hl) 92%, transparent 92%);
        font-size: 15px;
        font-weight: 700;
      }
    `
  });

  const list = createElement("div", "keyword-list");
  for (const keyword of keywords.slice(0, 8)) {
    list.appendChild(createElement("span", "hl", keywordTerm(keyword)));
  }
  content.appendChild(list);
}

function renderKeywordChartOverlay(keywords) {
  if (!keywords.length) {
    return;
  }

  const overlaySize = getKeywordOverlaySize(keywords);
  const max = Math.max(...keywords.map(keywordCount), 1);
  const { popup, content } = mountOverlay("keywordChart", {
    data: keywords,
    extraCss: `
      .chart {
        display: grid;
        gap: 8px;
      }

      .bar-row {
        display: grid;
        grid-template-columns: 84px minmax(0, 1fr) 28px;
        gap: 8px;
        align-items: center;
        font-size: 13px;
      }

      .term {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .bar-track {
        overflow: hidden;
        height: 10px;
        border-radius: 999px;
        background: var(--sunken);
      }

      .bar-fill {
        height: 100%;
        border-radius: inherit;
        background: var(--marker);
        transform-origin: left;
        animation: grow 0.6s cubic-bezier(0.2, 0.8, 0.2, 1);
      }

      @keyframes grow {
        from { transform: scaleX(0); }
      }

      .count {
        text-align: right;
        font-variant-numeric: tabular-nums;
      }
    `
  });
  applyOverlaySize(popup, overlaySize);

  const chart = createElement("div", "chart");
  // Same order as the panel chart: by count, ties in importance order.
  for (const keyword of [...keywords.slice(0, 8)].sort((a, b) => keywordCount(b) - keywordCount(a))) {
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

      .summary {
        flex: 1 1 auto;
        overflow: auto;
        min-height: 0;
        margin: 0;
        font-size: 15px;
        line-height: 1.75;
      }

      ${getSubtleScrollbarCss(".summary")}
    `
  });
  applyOverlaySize(popup, getSummaryOverlaySize(normalizedSummary));
  content.appendChild(createElement("p", "summary", normalizedSummary));
}

function renderRecommendationsOverlay(recommendations) {
  if (!recommendations.length) {
    return;
  }

  const { popup, content } = mountOverlay("recommendations", {
    data: recommendations,
    extraCss: `
      .groups {
        overflow: auto;
        display: grid;
        gap: 12px;
        max-height: 320px;
        margin: 0;
        padding: 0;
        list-style: none;
      }

      .publisher {
        margin: 0 0 4px;
        color: var(--muted);
        font-size: 12px;
        font-weight: 800;
      }

      .article-list {
        margin: 0;
        padding: 0;
        list-style: none;
      }

      .article-list li {
        padding: 6px 0;
        border-top: 1px solid var(--line);
      }

      .article-list li:first-child {
        padding-top: 2px;
        border-top: 0;
      }

      a {
        color: inherit;
        font-weight: 600;
        text-decoration: none;
      }

      a:hover {
        color: var(--focus);
        text-decoration: underline;
      }

      .rec-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 4px 10px;
        margin-top: 3px;
        color: var(--muted);
        font-size: 11px;
      }

      .ad-badge {
        padding: 0 6px;
        border-radius: 999px;
        background: color-mix(in srgb, var(--caution) 16%, transparent);
        color: var(--caution);
        font-weight: 800;
      }

      ${getSubtleScrollbarCss(".groups")}
    `
  });
  applyOverlaySize(popup, getRecommendationsOverlaySize(recommendations));

  const groups = createElement("ul", "groups");
  for (const [publisher, items] of groupByPublisher(recommendations.slice(0, 5))) {
    const group = document.createElement("li");
    group.appendChild(createElement("h3", "publisher", publisher));
    const list = createElement("ul", "article-list");
    for (const item of items) {
      list.appendChild(recommendationItem(item));
    }
    group.appendChild(list);
    groups.appendChild(group);
  }
  content.appendChild(groups);
}

// Same grouping as the panel: groups follow each publisher's best-ranked article.
function groupByPublisher(items) {
  const groups = new Map();
  for (const item of items) {
    const publisher = String(item?.publisher || publisherFromUrl(item?.url));
    if (!groups.has(publisher)) groups.set(publisher, []);
    groups.get(publisher).push(item);
  }
  return [...groups];
}

function publisherFromUrl(url) {
  try {
    const { hostname } = new URL(url);
    if (hostname === "naver.com" || hostname.endsWith(".naver.com")) return "네이버뉴스";
    return hostname.replace(/^www\./, "");
  } catch {
    return "기타";
  }
}

function recommendationItem(item) {
  const listItem = document.createElement("li");
  const link = createElement("a", "", String(item?.title || "관련 기사"));
  // Recommendation URLs are server data; only http(s) may become a link.
  if (isHttpUrl(item?.url)) {
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noreferrer";
  }
  listItem.appendChild(link);

  const meta = createElement("div", "rec-meta");
  for (const reason of Array.isArray(item?.reasons) ? item.reasons : []) {
    meta.appendChild(createElement("span", "", String(reason)));
  }
  const adProbability = Number(item?.adProbability);
  // Matches the backend "검토 필요" boundary (ad_label_for >= 0.4).
  if (item?.adProbability != null && Number.isFinite(adProbability) && adProbability >= 0.4) {
    meta.appendChild(createElement("span", "ad-badge", `광고성 ${Math.round(adProbability * 100)}%`));
  }
  if (meta.childElementCount) {
    listItem.appendChild(meta);
  }
  return listItem;
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

  const { content } = mountOverlay(name, {
    loading: true,
    extraCss: `
      .loading {
        display: flex;
        align-items: center;
        gap: 10px;
      }

      .spinner {
        width: 14px;
        height: 14px;
        border: 2px solid var(--sunken);
        border-top-color: var(--focus);
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

  const status = createElement("p", "state loading");
  status.setAttribute("role", "status");
  const spinner = createElement("span", "spinner");
  spinner.setAttribute("aria-hidden", "true");
  status.append(spinner, document.createTextNode("새 기사를 분석하고 있습니다."));
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
  handle.title = "드래그해서 이동";
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
      scrollbar-color: color-mix(in srgb, var(--muted) 45%, transparent) transparent;
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
      background: color-mix(in srgb, var(--muted) 45%, transparent);
    }

    ${selector}:hover::-webkit-scrollbar-thumb:hover {
      background: color-mix(in srgb, var(--muted) 70%, transparent);
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
  const stored = await safeStorageGetAsync([THEME_STORAGE_KEY, MOTION_STORAGE_KEY]);
  currentTheme = normalizeTheme(stored?.[THEME_STORAGE_KEY]);
  motionEnabled = resolveMotion(stored?.[MOTION_STORAGE_KEY]);
}

function normalizeTheme(theme) {
  return theme === "dark" ? "dark" : "light";
}

// Same rule as the panel's applyMotion: an explicit setting wins, otherwise the OS "reduce motion" preference.
function resolveMotion(preference) {
  return preference ? preference === "on" : !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

function overlayTokenCss() {
  return Object.entries(OVERLAY_TOKENS[currentTheme])
    .map(([name, value]) => `--${name}: ${value};`)
    .join(" ");
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
      if (areaName !== "local" || !(changes[THEME_STORAGE_KEY] || changes[MOTION_STORAGE_KEY])) {
        return;
      }

      if (changes[THEME_STORAGE_KEY]) currentTheme = normalizeTheme(changes[THEME_STORAGE_KEY].newValue);
      if (changes[MOTION_STORAGE_KEY]) motionEnabled = resolveMotion(changes[MOTION_STORAGE_KEY].newValue);
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
