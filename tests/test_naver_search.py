"""Run without importing backend.__init__, which starts DB/model initialization."""
import importlib.util
import io
import json
import urllib.error
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'naver_search_service', Path(__file__).resolve().parents[1] / 'backend/domains/naver_search/service.py'
)
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)

PAYLOAD = {'items': [
    {'title': '&quot;<b>인공지능</b>&quot; 반도체 투자', 'originallink': 'https://www.hankyung.com/article/1',
     'link': 'https://n.news.naver.com/mnews/article/015/0001', 'description': '<b>AI</b> 칩 &amp; 설비',
     'pubDate': 'Mon, 03 Nov 2026 09:12:00 +0900'},
    {'title': '언론사 단독 기사', 'originallink': 'https://news.example/2', 'link': 'https://news.example/2',
     'description': '본문 요약', 'pubDate': 'not a date'},
    {'title': '링크 없음', 'originallink': 'javascript:alert(1)', 'link': '', 'description': '', 'pubDate': ''},
]}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class NaverSearchTests(unittest.TestCase):
    def test_items_keep_order_and_wording(self):
        items = service.parse_items(PAYLOAD)
        self.assertEqual([item['title'] for item in items], ['"인공지능" 반도체 투자', '언론사 단독 기사'])
        first, second = items
        self.assertEqual(first['description'], 'AI 칩 & 설비')
        self.assertEqual(first['url'], 'https://www.hankyung.com/article/1')
        self.assertEqual(first['naverUrl'], 'https://n.news.naver.com/mnews/article/015/0001')
        self.assertEqual(first['source'], 'hankyung.com')
        self.assertEqual(first['publishedAt'], '2026-11-03T09:12:00+09:00')
        # Articles NAVER does not host keep only the original link.
        self.assertEqual(second['naverUrl'], '')
        self.assertEqual(second['publishedAt'], '')

    def test_request_sends_keys_and_query(self):
        seen = {}

        def opener(request, timeout):
            seen['url'], seen['headers'], seen['timeout'] = request.full_url, dict(request.header_items()), timeout
            return FakeResponse(json.dumps(PAYLOAD).encode())

        items = service.search_news('인공지능 반도체', 5, 'id', 'secret', 'date', opener=opener)
        self.assertEqual(len(items), 2)
        self.assertIn('query=%EC%9D%B8%EA%B3%B5%EC%A7%80%EB%8A%A5+%EB%B0%98%EB%8F%84%EC%B2%B4', seen['url'])
        self.assertIn('display=5', seen['url'])
        self.assertIn('sort=date', seen['url'])
        self.assertEqual(seen['headers']['X-naver-client-id'], 'id')
        self.assertEqual(seen['headers']['X-naver-client-secret'], 'secret')
        self.assertEqual(seen['timeout'], service.REQUEST_TIMEOUT_SECONDS)

    def test_missing_keys_and_api_errors_are_unavailable(self):
        with self.assertRaises(service.NaverSearchUnavailable):
            service.search_news('q', 5, '', '')

        def unauthorized(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 401, 'Unauthorized', {}, None)

        with self.assertRaisesRegex(service.NaverSearchUnavailable, '401'):
            service.search_news('q', 5, 'id', 'bad', opener=unauthorized)

        def offline(request, timeout):
            raise urllib.error.URLError('down')

        with self.assertRaises(service.NaverSearchUnavailable):
            service.search_news('q', 5, 'id', 'secret', opener=offline)


if __name__ == '__main__':
    unittest.main()
