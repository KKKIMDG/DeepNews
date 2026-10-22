(() => {
  // Readability mutates its input, so never give it the live page DOM.
  const clone = document.cloneNode(true);
  clone.querySelectorAll('[id^="deepnews-"], nav, footer, aside, form, [hidden], [aria-hidden="true"]').forEach(node => node.remove());
  const knownBody = clone.querySelector('#dic_area, #comp_news_article');
  let title, content;
  if (knownBody) {
    knownBody.querySelectorAll('script, style, template, svg, .img_desc, .byline_s').forEach(node => node.remove());
    title = clone.querySelector('meta[property="og:title"]')?.content || document.title;
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
  return { ok: true, article: { url: location.href, title: title.slice(0, 500), content } };
})();
