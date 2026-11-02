// npm run test:js  (or NODE_PATH=<dir>/node_modules node tests/test_article_extraction.cjs)
const { JSDOM } = require('jsdom');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const reader = fs.readFileSync('frontend/src/vendor/readability/Readability.js', 'utf8');
const extract = fs.readFileSync('frontend/src/content/extract-article.js', 'utf8');
const paragraph = '지역 주민들은 새롭게 개관한 도서관에서 다양한 문화 프로그램에 참여했다. 도서관은 주말에도 운영하며 어린이와 청소년을 위한 독서 활동을 제공한다. 관계자는 앞으로 주민 의견을 반영해 운영 시간을 조정할 계획이라고 설명했다. ';
function run(html) {
 const dom = new JSDOM(html, {url: 'https://publisher.example/news/123', runScripts: 'outside-only'});
 dom.window.eval(reader);
 const before=dom.window.document.body.innerHTML;
 const result=dom.window.eval(extract);
 assert.equal(dom.window.document.body.innerHTML, before, 'Live DOM is unchanged');
 return result;
}
for (const body of [`<article><h1>도서관 개관 소식</h1>${`<p>${paragraph}</p>`.repeat(5)}</article>`, `<div id="dic_area">${paragraph.repeat(3)}</div>`, `<article id="comp_news_article">${paragraph.repeat(3)}</article>`]) {
 const r=run(`<title>도서관 개관 소식</title><nav>메뉴오염</nav>${body}<aside>추천오염</aside>`);
 assert(r.ok); assert(r.article.content.includes('도서관')); assert(!r.article.content.includes('메뉴오염')); assert(!r.article.content.includes('추천오염'));
}
const naver = run(`<title>네이버 뉴스</title><meta property="og:title" content="og 제목"><h2 id="title_area"><span>도서관 개관 소식</span></h2>
 <span class="media_end_head_info_datestamp_time _ARTICLE_DATE_TIME" data-date-time="2026-10-30 09:12:00">2026.10.30. 오전 9:12</span>
 <div id="dic_area"><strong class="media_end_summary">요약오염</strong><span class="end_photo_org"><img><em class="img_desc">사진오염</em></span>${paragraph.repeat(3)}</div>`);
assert(naver.ok); assert.equal(naver.article.title, '도서관 개관 소식');
assert(!naver.article.content.includes('요약오염')); assert(!naver.article.content.includes('사진오염'));
assert.equal(naver.article.publishedAt, '2026-10-30T09:12:00+09:00');
const articleBody = `<article><h1>도서관 개관 소식</h1>${`<p>${paragraph}</p>`.repeat(5)}</article>`;
const withMeta = run(`<title>도서관 개관 소식</title><meta property="article:published_time" content="2026-10-29T08:30:00+09:00">${articleBody}`);
assert.equal(withMeta.article.publishedAt, '2026-10-28T23:30:00.000Z');
const withJsonLd = run(`<title>도서관 개관 소식</title><script type="application/ld+json">{"@graph":[{"@type":"NewsArticle","datePublished":"2026-10-28T10:00:00Z"}]}</script>${articleBody}`);
assert.equal(withJsonLd.article.publishedAt, '2026-10-28T10:00:00.000Z');
const withTime = run(`<title>도서관 개관 소식</title><time datetime="2026-10-27T12:00:00+09:00">10월 27일</time>${articleBody}`);
assert.equal(withTime.article.publishedAt, '2026-10-27T03:00:00.000Z');
const noDate = run(`<title>도서관 개관 소식</title><meta name="pubdate" content="날짜 없음">${articleBody}`);
assert.equal(noDate.article.publishedAt, '');
assert(!run('<title>로그인</title><form>이메일 비밀번호</form>').ok);
assert(!run('<title>짧은 페이지</title><article>짧음</article>').ok);
console.log('PASS: generic/news/sports extraction, publishedAt, non-article rejection, live DOM preservation');

// Content script: keyword highlighting must build DOM nodes, never parse page or server text as HTML.
const contentScript = fs.readFileSync('frontend/src/content/content-script.js', 'utf8');
function loadContentScript(html) {
 const dom = new JSDOM(html, {url: 'https://publisher.example/news/123', runScripts: 'outside-only'});
 const listeners = [];
 const sent = [];
 dom.window.ResizeObserver = class { observe() {} };
 dom.window.chrome = {
  runtime: {id: 'deepnews-test', onMessage: {addListener: (fn) => listeners.push(fn)}, sendMessage: (message) => { sent.push(message); return Promise.resolve(); }},
  storage: {local: {get: (key, callback) => (callback ? callback({}) : Promise.resolve({})), set: () => {}}, onChanged: {addListener: () => {}}}
 };
 dom.window.eval(contentScript);
 const send = (message) => listeners.forEach((fn) => fn(message, {id: 'deepnews-test'}));
 return {dom, send, sent};
}
const hostile = '&lt;img src=x onerror="window.pwned=1"&gt;';
const page = loadContentScript(`<div class="layout"><article class="article-body"><p>인공지능 기술이 발전했다. ${hostile} 인공 지능과 인공지능 연구.</p><p>${paragraph}</p></article></div>`);
page.send({type: 'HIGHLIGHT_KEYWORDS', payload: {keywords: ['인공', '인공지능', '<img src=x onerror="window.pwned=1">']}});
const doc = page.dom.window.document;
const marks = [...doc.querySelectorAll('mark.deepnews-highlight')].map((mark) => mark.textContent);
assert.deepEqual(marks, ['인공지능', '<img src=x onerror="window.pwned=1">', '인공', '인공지능'], 'longest keyword wins and text is matched literally');
assert.equal(doc.querySelectorAll('img').length, 0, 'page text is never parsed as HTML');
assert.equal(page.dom.window.pwned, undefined);
page.send({type: 'HIGHLIGHT_KEYWORDS', payload: {keywords: ['도서관']}});
assert(doc.querySelectorAll('mark.deepnews-highlight').length > 0);
assert(![...doc.querySelectorAll('mark')].some((mark) => mark.textContent === '인공지능'), 'previous highlights are removed');

// Non-Naver page without known containers: the element with the most paragraph text is used.
const generic = loadContentScript(`<div id="menu"><p>메뉴 도서관</p></div><div id="story"><p>${paragraph}</p><p>${paragraph}</p></div>`);
generic.send({type: 'HIGHLIGHT_KEYWORDS', payload: {keywords: ['도서관']}});
const genericDoc = generic.dom.window.document;
assert.equal(genericDoc.querySelectorAll('#menu mark').length, 0);
assert(genericDoc.querySelectorAll('#story mark').length > 0);

// YTN style: the whole body sits in one <div> as <span> text and <br>s, with no <p> at all.
const singleDiv = loadContentScript(`<header><a>도서관 메뉴</a></header><div class="related"><a>도서관 관련 기사</a></div><div id="body"><span>${paragraph}<br><br>${paragraph}</span></div>`);
singleDiv.send({type: 'HIGHLIGHT_KEYWORDS', payload: {keywords: ['도서관']}});
const singleDoc = singleDiv.dom.window.document;
assert(singleDoc.querySelectorAll('#body mark').length > 0);
assert.equal(singleDoc.querySelectorAll('header mark, .related mark').length, 0);

// Overlays use closed shadow roots and render server text as text.
page.send({type: 'SHOW_SUMMARY', payload: {summary: '<img src=x onerror="window.pwned=2">요약'}});
page.send({type: 'SHOW_AD_LIKELIHOOD', payload: {adLikelihood: {label: '미분석', score: -1}}});
const hosts = doc.querySelectorAll('[data-deepnews-overlay]');
assert.equal(hosts.length, 2);
assert([...hosts].every((host) => host.shadowRoot === null), 'shadow roots are closed');
assert.equal(doc.querySelectorAll('img').length, 0);
page.send({type: 'HIDE_ALL_OVERLAYS'});
assert.equal(doc.querySelectorAll('[data-deepnews-overlay]').length, 0);
page.send({type: 'SHOW_LOADING_OVERLAYS', payload: {openOverlays: {summary: true, keywords: true}}});
page.send({type: 'SHOW_SUMMARY', payload: {summary: '요약'}});
page.send({type: 'HIDE_LOADING_OVERLAYS'});
assert.equal(doc.querySelectorAll('[data-deepnews-overlay]').length, 1, 'only the still-loading overlay is removed');
console.log('PASS: content script highlighting without innerHTML, generic article fallback, closed overlays');
