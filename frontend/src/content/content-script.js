const ARTICLE_SELECTORS = {
  title: [
    ".media_end_head_headline",
    "#title_area",
    "h2#title_area",
    ".end_tit"
  ],
  body: [
    "#dic_area",
    "#newsct_article",
    ".newsct_article"
  ],
  titleMeta: [
    'meta[property="og:title"]',
    'meta[name="twitter:title"]'
  ]
};

const HIGHLIGHT_CLASS = "deepnews-highlight";
const ANALYZE_ARTICLE = "ANALYZE_ARTICLE";

bootstrap();

function bootstrap() {
  injectHighlightStyle();

  const article = extractArticle();
  if (!article) {
    return;
  }

  chrome.runtime.sendMessage({
    type: ANALYZE_ARTICLE,
    payload: article
  });
}

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "HIGHLIGHT_KEYWORDS") {
    highlightKeywords(message.payload?.keywords || []);
  }
});

function extractArticle() {
  const title =
    queryFirstText(ARTICLE_SELECTORS.title) ||
    queryFirstMetaContent(ARTICLE_SELECTORS.titleMeta);
  const body = queryFirstText(ARTICLE_SELECTORS.body);

  if (!title || !body) {
    return null;
  }

  return {
    title,
    body,
    url: window.location.href
  };
}

function queryFirstText(selectors) {
  for (const selector of selectors) {
    const element = document.querySelector(selector);
    const text = element?.textContent?.trim();

    if (text) {
      return text;
    }
  }

  return "";
}

function queryFirstMetaContent(selectors) {
  for (const selector of selectors) {
    const content = document.querySelector(selector)?.getAttribute("content")?.trim();

    if (content) {
      return content;
    }
  }

  return "";
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

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
