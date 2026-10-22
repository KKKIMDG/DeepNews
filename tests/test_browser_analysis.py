"""Isolate model/DB startup; verify service behavior with test doubles."""
import importlib
from pathlib import Path
import sys
import types
import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch


class BrowserAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = dict(sys.modules)
        root = Path(__file__).resolve().parents[1] / 'backend'
        for name, path in [('backend', root), ('backend.domains', root / 'domains'),
                           ('backend.domains.analysis', root / 'domains/analysis')]:
            module = types.ModuleType(name)
            module.__path__ = [str(path)]
            sys.modules[name] = module
        config = types.ModuleType('backend.config')
        config.settings = types.SimpleNamespace(keyword_stopwords=set(), keyword_limit=8)
        sys.modules['backend.config'] = config
        for name in ['backend.database', 'backend.domains.news.models',
                     'backend.domains.news.repository', 'backend.domains.analysis.service']:
            sys.modules[name] = Mock()
        cls.service = importlib.import_module('backend.domains.news.service')
        cls.Request = importlib.import_module('backend.domains.news.schemas').AnalyzeArticleRequest

    @classmethod
    def tearDownClass(cls):
        for name in list(sys.modules):
            if name.startswith('backend'):
                sys.modules.pop(name, None)
        sys.modules.update({k: v for k, v in cls.saved.items() if k.startswith('backend')})

    def test_request_validation(self):
        self.Request(url='https://example.com/article')  # old URL-only API
        for payload in [dict(url='file:///tmp/test'),
                        dict(url='https://example.com', content='short', title='제목'),
                        dict(url='https://example.com', content='가'*120),
                        dict(url='https://example.com', title='제목', content='가'*100001)]:
            with self.assertRaises(ValueError):
                self.Request(**payload)

    def test_browser_text_skips_fetch_and_saves(self):
        s = self.service
        article = types.SimpleNamespace(url='https://example.com/article', title='제목',
            content='본문 '*100, published_at='', token_counts={'본문': 100})
        with patch.object(s, 'prepare_browser_article', return_value=article), \
             patch.object(s, 'get_session', return_value=nullcontext(Mock())), \
             patch.object(s, 'crawl_article') as crawl, \
             patch.object(s, 'repository') as repo, \
             patch.object(s, 'analyze_article', return_value=dict(summary='요약', ad_probability=.1, is_clickbait=False, named_entities=[])), \
             patch.object(s, 'serialize_analysis_response', return_value='response'):
            repo.fetch_news_by_url.return_value = None
            self.assertEqual(s.analyze_or_get(article.url, article.title, article.content), 'response')
            crawl.assert_not_called()
            data = repo.upsert_news.call_args.args[3]
            self.assertEqual(data['source'], 'example.com')
            self.assertEqual(data['extraData']['content_origin'], 'browser')
            repo.upsert_news_analysis.assert_called_once()

    def test_different_browser_text_cannot_overwrite_existing(self):
        s = self.service
        with patch.object(s, 'prepare_browser_article', return_value=Mock(content='changed')), \
             patch.object(s, 'get_session', return_value=nullcontext(Mock())), \
             patch.object(s, 'repository') as repo:
            repo.fetch_news_by_url.return_value = Mock(article_data={'content': 'original'})
            with self.assertRaises(s.HTTPException) as raised:
                s.analyze_or_get('https://example.com/article', '제목', '본문'*100)
            self.assertEqual(raised.exception.status_code, 409)
            repo.upsert_news.assert_not_called()
