const ARTICLE_SELECTORS = {
  body: ["#dic_area", "#newsct_article", ".newsct_article"]
};

const HIGHLIGHT_CLASS = "deepnews-highlight";
const ANALYZE_ARTICLE = "ANALYZE_ARTICLE";

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootstrap, { once: true });
} else {
  bootstrap();
}

function bootstrap() {
  injectHighlightStyle();

  if (!isSupportedArticleUrl(window.location.href)) {
    return;
  }

  chrome.runtime.sendMessage({
    type: ANALYZE_ARTICLE,
    payload: {
      url: window.location.href
    }
  });
}

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "HIGHLIGHT_KEYWORDS") {
    highlightKeywords(message.payload?.keywords || []);
  }
});

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

function isSupportedArticleUrl(url) {
  try {
    const parsed = new URL(url);
    const isNaverNewsHost =
      parsed.hostname === "news.naver.com" || parsed.hostname === "n.news.naver.com";

    return isNaverNewsHost && /\/article\//.test(parsed.pathname);
  } catch {
    return false;
  }
}
