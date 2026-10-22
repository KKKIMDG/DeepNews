"""Run without importing backend.__init__, which starts DB/model initialization."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from bs4 import BeautifulSoup

spec = importlib.util.spec_from_file_location(
    'crawl_extractor', Path(__file__).resolve().parents[1] / 'backend/domains/crawl/extractor.py'
)
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)


class ExtractionTests(unittest.TestCase):
    def test_sports_body_excludes_navigation(self):
        soup = BeautifulSoup('''<meta property="og:title" content="경기 결과">
        <nav>메뉴</nav><article id="comp_news_article">실제 본문
        <script>noise</script><svg>noise</svg></article><aside>추천 기사</aside>
        <div class="article_head_info"><em class="date">2026.10.22. 오후 12:05</em></div>''', 'html.parser')
        self.assertEqual(extractor.extract_from_naver_html(soup, '', ''),
                         ('경기 결과', '실제 본문', '2026-10-22 12:05:00'))

    def test_regular_news_unchanged(self):
        soup = BeautifulSoup('''<h2 id="title_area">일반 기사</h2>
        <div id="dic_area">본문<em class="img_desc">사진 설명</em></div>
        <span class="_ARTICLE_DATE_TIME" data-date-time="2026-10-22 10:00:00"></span>''', 'html.parser')
        self.assertEqual(extractor.extract_from_naver_html(soup, '', ''),
                         ('일반 기사', '본문', '2026-10-22 10:00:00'))

    def test_missing_sports_body_fails(self):
        response = Mock(url='https://m.sports.naver.com/kbaseball/article/001/123', text='<nav>메뉴</nav>')
        with patch.object(extractor, 'build_session') as session:
            session.return_value.get.return_value = response
            with self.assertRaisesRegex(ValueError, 'body not found'):
                extractor.extract_article(response.url, extractor.get_article_config())


if __name__ == '__main__':
    unittest.main()
