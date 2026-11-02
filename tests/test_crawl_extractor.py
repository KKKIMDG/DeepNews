"""Run without importing backend.__init__, which starts DB/model initialization."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'crawl_extractor', Path(__file__).resolve().parents[1] / 'backend/domains/crawl/extractor.py'
)
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)


class ExtractionTests(unittest.TestCase):
    def test_canonical_naver_article_url(self):
        canonical = 'https://n.news.naver.com/mnews/article/001/0016392704'
        for url in ['https://n.news.naver.com/mnews/article/001/0016392704?sid=104',
                    'https://n.news.naver.com/article/001/0016392704',
                    'https://n.news.naver.com/article/001/0016392704?cds=news_media_pc&type=editn',
                    'https://news.naver.com/main/read.naver?mode=LSD&oid=001&aid=0016392704',
                    'https://m.news.naver.com/read.naver?oid=001&aid=0016392704']:
            self.assertEqual(extractor.canonical_article_url(url), canonical, url)
        self.assertEqual(extractor.canonical_article_url('https://m.sports.naver.com/kbaseball/article/108/0003480793?sid3=1'),
                         'https://m.sports.naver.com/kbaseball/article/108/0003480793')
        for url in ['https://news.kbs.co.kr/news/view.do?ncd=8699835&ref=DA', 'https://n.news.naver.com/main/ranking',
                    'https://news.naver.com/main/read.naver?oid=001']:
            self.assertEqual(extractor.canonical_article_url(url), url)

    def test_published_at_normalization(self):
        normalize = extractor.normalize_published_at
        self.assertEqual(normalize('2026-10-30 09:12:00'), '2026-10-30T09:12:00')
        self.assertEqual(normalize('2026-10-30T00:12:00.000Z'), '2026-10-30T00:12:00+00:00')
        self.assertEqual(normalize('2026-10-30T09:12:00+09:00'), '2026-10-30T09:12:00+09:00')
        for bad in ['', None, '어제', '1970-01-01T00:00:00', '2999-01-01']:
            self.assertEqual(normalize(bad), '', bad)

    def test_text_cleanup_drops_bylines(self):
        cleaned = extractor.clean_article_text('본문입니다. 홍길동 기자 hong@example.com [사진=연합뉴스]')
        self.assertEqual(cleaned, '본문입니다.')


if __name__ == '__main__':
    unittest.main()
