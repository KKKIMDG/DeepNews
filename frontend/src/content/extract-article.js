(() => {
  // Publisher body containers in priority order; mirrors GENERIC_BODY_SELECTORS in content-script.js minus the
  // too-broad `article`. #news-contents (Newspim) comes first: its articleBody wrapper also holds the site's AI summary.
  const EXPLICIT_BODY_SELECTORS = [
    '#news-contents', '[itemprop="articleBody"]', '#articleBody', '#article-view-content-div', '#articletxt', '.article_body',
    '.article-body', '.news_text', '.view_con', '#CmAdContent', '#cont_newstext', '#article_body', '.article_txt', '.text_area'
  ];
  const MIN_CONTENT_LENGTH = 100;
  const BODY_COVERAGE_MIN = 0.5;
  const BODY_LENGTH_MAX_RATIO = 2;
  // Readability mutates its input, so never give it the live page DOM.
  const clone = document.cloneNode(true);
  const publishedAt = extractPublishedAt(document);
  clone.querySelectorAll('[id^="deepnews-"], [data-deepnews-overlay], nav, footer, aside, form, [hidden], [aria-hidden="true"]').forEach(node => node.remove());
  const knownBody = clone.querySelector('#dic_area, #comp_news_article');
  let title, content;
  if (knownBody) {
    // Same exclusions as the server extractor: Naver's summary box and photo captions are not article text.
    knownBody.querySelectorAll('script, style, template, svg, .img_desc, .byline_s, .media_end_summary, .end_photo_org').forEach(node => node.remove());
    title = clone.querySelector('#title_area')?.textContent.trim() || clone.querySelector('meta[property="og:title"]')?.content || document.title;
    content = knownBody.textContent;
  } else {
    // Readability gets its own copy; the publisher body is then read from the untouched clone.
    const article = new Readability(clone.cloneNode(true), { charThreshold: 200, maxElemsToParse: 50000 }).parse();
    title = article?.title || clone.querySelector('meta[property="og:title"]')?.content || document.title;
    content = (article?.textContent || '').replace(/\s+/g, ' ').trim();
    // When the publisher marks its body, Readability's pick is checked against it. Readability favours <p>-rich
    // blocks, so it can miss the body (short YTN articles: one <div> of <span>s and <br>s, the "실시간 랭킹" list wins)
    // or take a wrapper holding other stories too (Newspim: "뉴스핌 베스트 기사" bodies, stock tracker).
    const bodyText = explicitBodyText(clone);
    if (bodyText && (coverage(bodyText, content) < BODY_COVERAGE_MIN || content.length > bodyText.length * BODY_LENGTH_MAX_RATIO)) {
      content = bodyText;
    }
  }
  content = (content || '').replace(/\s+/g, ' ').trim();
  title = (title || '').trim();
  if (!title || content.length < MIN_CONTENT_LENGTH) return { ok: false, error: '충분한 기사 본문을 찾지 못했습니다. 기사 상세 페이지에서 다시 시도해 주세요.' };
  if (content.length > 100000) return { ok: false, error: '본문이 너무 깁니다. 기사 상세 페이지인지 확인해 주세요.' };
  return { ok: true, article: { url: location.href, title: title.slice(0, 500), content, publishedAt } };

  function explicitBodyText(root) {
    for (const selector of EXPLICIT_BODY_SELECTORS) {
      let best = null;
      for (const node of root.querySelectorAll(selector)) {
        if (!best || node.textContent.length > best.textContent.length) best = node;
      }
      if (!best) continue;
      best.querySelectorAll('script, style, template, svg, noscript, iframe, figcaption').forEach(node => node.remove());
      const text = best.textContent.replace(/\s+/g, ' ').trim();
      if (text.length >= MIN_CONTENT_LENGTH) return text;
    }
    return '';
  }

  // Share of the body's character bigrams that also occur in the extracted text (same measure as the server's lead check).
  function coverage(body, extracted) {
    const bigrams = (text) => {
      const compact = text.replace(/[^0-9A-Za-z가-힣]/g, '');
      const grams = new Set();
      for (let i = 0; i < compact.length - 1; i++) grams.add(compact.slice(i, i + 2));
      return grams;
    };
    const bodyGrams = bigrams(body);
    if (!bodyGrams.size) return 1;
    const extractedGrams = bigrams(extracted);
    let shared = 0;
    for (const gram of bodyGrams) if (extractedGrams.has(gram)) shared++;
    return shared / bodyGrams.size;
  }

  function extractPublishedAt(root) {
    const candidates = [
      root.querySelector('._ARTICLE_DATE_TIME[data-date-time]')?.dataset.dateTime,
      root.querySelector('.media_end_head_info_datestamp_time[data-date-time]')?.dataset.dateTime,
      root.querySelector('meta[property="article:published_time"]')?.content,
      root.querySelector('meta[name="pubdate"]')?.content,
      root.querySelector('meta[itemprop="datePublished"]')?.content,
      jsonLdDatePublished(root),
      root.querySelector('time[datetime]')?.getAttribute('datetime')
    ];
    for (const value of candidates) {
      const normalized = normalizeDate(value);
      if (normalized) return normalized;
    }
    return '';
  }

  function jsonLdDatePublished(root) {
    for (const script of root.querySelectorAll('script[type="application/ld+json"]')) {
      let data;
      try { data = JSON.parse(script.textContent || ''); } catch { continue; }
      const queue = [data];
      while (queue.length) {
        const item = queue.shift();
        if (Array.isArray(item)) { queue.push(...item); continue; }
        if (!item || typeof item !== 'object') continue;
        if (typeof item.datePublished === 'string') return item.datePublished;
        if (item['@graph']) queue.push(item['@graph']);
      }
    }
    return '';
  }

  function normalizeDate(value) {
    const text = String(value || '').trim();
    if (!text) return '';
    // Naver writes "2026-10-30 09:12:00" in KST without an offset.
    const naive = text.match(/^(\d{4})[-.](\d{1,2})[-.](\d{1,2})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?$/);
    if (naive) {
      const [, y, mo, d, h, mi, s = '00'] = naive;
      const pad = (part) => part.padStart(2, '0');
      return `${y}-${pad(mo)}-${pad(d)}T${pad(h)}:${mi}:${s}+09:00`;
    }
    const time = Date.parse(text);
    return Number.isNaN(time) ? '' : new Date(time).toISOString();
  }
})();
