(() => {
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
    const article = new Readability(clone, { charThreshold: 200, maxElemsToParse: 50000 }).parse();
    title = article?.title;
    content = article?.textContent;
  }
  content = (content || '').replace(/\s+/g, ' ').trim();
  title = (title || '').trim();
  if (!title || content.length < 100) return { ok: false, error: '충분한 기사 본문을 찾지 못했습니다. 기사 상세 페이지에서 다시 시도해 주세요.' };
  if (content.length > 100000) return { ok: false, error: '본문이 너무 깁니다. 기사 상세 페이지인지 확인해 주세요.' };
  return { ok: true, article: { url: location.href, title: title.slice(0, 500), content, publishedAt } };

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
