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

    def test_text_cleanup_keeps_meaningful_symbols(self):
        cleaned = extractor.clean_article_text('李대통령 “예산 3원칙”이라며 5·18 기념식에서 에쓰오일(S-OIL)은 11.85% 내렸다고 했다.')
        self.assertEqual(cleaned, '李대통령 “예산 3원칙”이라며 5·18 기념식에서 에쓰오일은 11.85% 내렸다고 했다.')

    def test_publisher_footer_removed(self):
        body = '대구 달서구 아파트에서 불이 나 1명이 중상을 입었다. 소방당국은 정확한 화재 원인을 조사하고 있다.'
        footers = [
            ' GoodNews paper ⓒ 국민일보(www.kmib.co.kr), 무단전재, 수집, 재배포 및 AI학습 이용 금지',
            " YTN 김철희 (kchee21@ytn.co.kr) ※ '당신의 제보가 뉴스가 됩니다' [카카오톡] YTN 검색해 채널 추가 [전화] 02-398-8585",
            ' 제호 브릿지경제신문 서울특별시 종로구 새문안로5길 13, 9층 인터넷신문등록번호 서울,아03028 등록일자 2014년 3월 3일'
            ' 대표 겸 발행인 편집인 권경훈 청소년보호책임자 안의식 Copyright Bridgenews Co.,Ltd. All Rights Reserved',
        ]
        for footer in footers:
            self.assertTrue(extractor.clean_article_text(body + footer).startswith(body), footer)
            self.assertLess(len(extractor.clean_article_text(body + footer)), len(body) + 12, footer)
        # A title-only page leaves nothing but the masthead.
        self.assertLess(len(extractor.clean_article_text(footers[2])), 80)
        # The same words inside the article body are not footers.
        ai_story = '정부가 의료데이터를 AI 학습에 활용하는 방안을 논의했다. ' * 3 + '저작권 침해 소송에서 Copyright 조항이 쟁점이 됐다. ' * 20
        self.assertGreater(len(extractor.clean_article_text(ai_story)), 600)


if __name__ == '__main__':
    unittest.main()
