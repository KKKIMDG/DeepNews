// NODE_PATH=/tmp/deepnews-browser-tests/node_modules node tests/test_article_extraction.cjs
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
assert(!run('<title>로그인</title><form>이메일 비밀번호</form>').ok);
assert(!run('<title>짧은 페이지</title><article>짧음</article>').ok);
console.log('PASS: generic/news/sports extraction, non-article rejection, live DOM preservation');
