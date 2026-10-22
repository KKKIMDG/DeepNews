import sys
import unittest
from unittest.mock import Mock, patch
from bs4 import BeautifulSoup
from backend.batch import pipeline
from backend.domains.crawl.extractor import is_naver_news_link


class IngestionTests(unittest.TestCase):
    def test_article_url_validation(self):
        self.assertTrue(is_naver_news_link('https://n.news.naver.com/mnews/article/001/123?sid=1'))
        for url in ['https://n.news.naver.com.evil.test/article/001/123',
                    'https://n.news.naver.com/section/100', 'file:///article/001/123']:
            self.assertFalse(is_naver_news_link(url))

    def test_links_deduplicated(self):
        soup = BeautifulSoup('<a href="https://n.news.naver.com/article/001/123">a</a>'*2, 'html.parser')
        self.assertEqual(len(pipeline.extract_naver_links_from_search_page(soup)), 1)

    def test_repeated_page_stops(self):
        response = Mock(text='<a href="https://n.news.naver.com/article/001/123">a</a>')
        with patch.object(pipeline, 'build_session') as build:
            build.return_value.get.return_value = response
            links = pipeline.collect_naver_news_links('AI', 5, sleep_seconds=0)
            self.assertEqual(len(links), 1)
            self.assertEqual(build.return_value.get.call_count, 2)

    def test_empty_batch_not_saved_to_database(self):
        batch = pipeline.BatchResult('AI', '', 'Regex')
        with patch.object(pipeline, 'collect_news_batch', return_value=batch), \
             patch.object(pipeline, 'save_batch_outputs', return_value={}), \
             patch.object(pipeline, 'sync_news_batch_to_database') as sync:
            with self.assertRaisesRegex(RuntimeError, 'All article'):
                pipeline.run_ingestion_pipeline('AI', 5, None)
            sync.assert_not_called()

    def test_invalid_limit(self):
        with self.assertRaises(ValueError):
            pipeline.run_ingestion_pipeline('AI', 0, None)
