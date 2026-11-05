"""Isolate model/DB startup; verify service behavior with test doubles."""
import importlib
from pathlib import Path
import sys
import types
import unittest
from contextlib import nullcontext
from unittest.mock import MagicMock, Mock, patch

from fastapi import HTTPException

LEAD = '정부가 용인 반도체 클러스터에 필요한 전력망과 용수 공급 시설을 당초 계획보다 2년 앞당겨 구축하기로 했다. 산업통상자원부는 30일 반도체 산업 경쟁력 강화 방안을 발표했다.'
USER = types.SimpleNamespace(id=7, email='a@b.co', ad_filter_threshold=0.8)
ANALYSIS = dict(summary='요약', ad_probability=.1, is_clickbait=False, named_entities=[])


def stored(url, content='옛 본문', extra=None, analysis=None, published=''):
    return Mock(id=1, url=url, title='저장된 제목', analysis=analysis,
                article_data={'content': content, 'publishedAt': published, 'extraData': extra or {}})


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
                     'backend.domains.news.repository', 'backend.domains.analysis.service',
                     'backend.domains.auth.dependencies', 'backend.domains.personalization.service']:
            sys.modules[name] = Mock()
        analysis = sys.modules['backend.domains.analysis.service']
        analysis.AD_HIGH_THRESHOLD, analysis.AD_REVIEW_THRESHOLD = 0.8, 0.4
        cls.service = importlib.import_module('backend.domains.news.service')
        cls.Request = importlib.import_module('backend.domains.news.schemas').AnalyzeArticleRequest

    @classmethod
    def tearDownClass(cls):
        for name in list(sys.modules):
            if name.startswith('backend'):
                sys.modules.pop(name, None)
        sys.modules.update({k: v for k, v in cls.saved.items() if k.startswith('backend')})

    def run_analyze(self, found=None, refetched=None, content='본문 '*100, url='https://example.com/article', defer=False):
        """Run analyze_or_get with repository lookups returning `found` (first session) and `refetched` (second)."""
        s = self.service
        article = types.SimpleNamespace(url=url, title='제목', content=content, published_at='2026-10-30T09:12:00',
                                        token_counts={'본문': 3})
        self.patches = [patch.object(s, 'prepare_browser_article', return_value=article),
                        patch.object(s, 'get_session', return_value=nullcontext(MagicMock())),
                        patch.object(s, 'repository'),
                        patch.object(s, 'analyze_article', return_value=ANALYSIS),
                        patch.object(s, 'serialize_analysis_response', return_value='response')]
        prepare, _, repo, analyze, serialize = [p.start() for p in self.patches]
        self.addCleanup(lambda: [p.stop() for p in self.patches])
        repo.fetch_news_by_canonical_url.return_value = found
        repo.fetch_news_by_url.return_value = refetched
        repo.report_counts.return_value = (0, False)
        try:
            result = s.analyze_or_get(url, '제목', content, USER, defer_recommendations=defer)
        except HTTPException as error:
            result = error
        return result, prepare, repo, analyze, serialize

    def test_request_validation(self):
        self.Request(url='https://example.com/article', title='제목', content='가'*120)
        for payload in [dict(url='https://example.com/article'),  # URL-only: the server never fetches
                        dict(url='file:///tmp/test', title='제목', content='가'*120),
                        dict(url='https://example.com/' + 'a'*600, title='제목', content='가'*120),
                        dict(url='https://example.com', content='short', title='제목'),
                        dict(url='https://example.com', content='가'*120),
                        dict(url='https://example.com', title='제목', content='가'*100001)]:
            with self.assertRaises(ValueError):
                self.Request(**payload)

    def test_new_article_is_analyzed_and_attributed(self):
        result, _, repo, analyze, _ = self.run_analyze()
        self.assertEqual(result, 'response')
        analyze.assert_called_once()
        data = repo.upsert_news.call_args.args[3]
        self.assertEqual(data['source'], 'example.com')
        self.assertEqual(data['publishedAt'], '2026-10-30T09:12:00')
        self.assertEqual(data['extraData']['content_origin'], 'browser')
        self.assertEqual(data['extraData']['submitted_by'], USER.id)
        repo.upsert_news_analysis.assert_called_once()
        repo.clear_reports.assert_called_once()
        self.service.personalization.record_read.assert_called()

    def test_deferred_recommendations_skip_ranking_but_record_the_read(self):
        personalization = self.service.personalization
        personalization.reset_mock()
        _, _, _, _, serialize = self.run_analyze(defer=True)
        personalization.record_read.assert_called_once()
        personalization.recommend.assert_not_called()
        self.assertEqual(serialize.call_args.args[3], [])
        self.assertTrue(serialize.call_args.kwargs['recommendations_deferred'])

    def test_recommendations_inline_by_default(self):
        personalization = self.service.personalization
        personalization.reset_mock()
        _, _, _, _, serialize = self.run_analyze()
        personalization.recommend.assert_called_once()
        self.assertFalse(serialize.call_args.kwargs['recommendations_deferred'])

    def test_full_text_replaces_bigkinds_lead_keeping_metadata(self):
        lead_row = stored('https://www.newspim.com/news/view/1', content=LEAD, published='2026-10-30',
                          extra={'content_partial': True, 'category': '경제>반도체', 'publisher': '뉴스핌', 'keywords': [1]})
        result, _, repo, _, _ = self.run_analyze(found=lead_row, content=LEAD + ' 이어지는 본문 ' * 20,
                                                 url=lead_row.url)
        data = repo.upsert_news.call_args.args[3]
        self.assertEqual(repo.upsert_news.call_args.args[1], '저장된 제목')
        self.assertNotIn('content_partial', data['extraData'])
        self.assertEqual(data['extraData']['category'], '경제>반도체')
        self.assertTrue(data['extraData']['lead_verified'])
        self.assertEqual(data['extraData']['keywords'], [{'term': '본문', 'count': 3}])
        self.assertEqual(data['publishedAt'], '2026-10-30')

    def test_unrelated_text_cannot_claim_bigkinds_row(self):
        lead_row = stored('https://www.newspim.com/news/view/1', content=LEAD, extra={'content_partial': True})
        result, _, repo, analyze, _ = self.run_analyze(found=lead_row, content='전혀 다른 내용의 광고 문구입니다. ' * 20)
        self.assertEqual(result.status_code, 409)
        analyze.assert_not_called()
        repo.upsert_news.assert_not_called()

    def test_stored_analysis_is_served_not_overwritten(self):
        row = stored('https://example.com/article', analysis=Mock(ad_probability=0.2))
        result, _, repo, analyze, serialize = self.run_analyze(found=row)
        self.assertEqual(result, 'response')
        self.assertIs(serialize.call_args.args[2], True)
        repo.upsert_news.assert_not_called()
        analyze.assert_not_called()

    def test_placeholder_analysis_is_redone(self):
        row = stored('https://example.com/article', analysis=Mock(ad_probability=-1.0))
        _, _, repo, analyze, _ = self.run_analyze(found=row)
        analyze.assert_called_once()
        repo.upsert_news_analysis.assert_called_once()

    def test_concurrent_finish_returns_the_other_result(self):
        winner = stored('https://example.com/article', analysis=Mock(ad_probability=0.3))
        _, _, repo, _, serialize = self.run_analyze(found=None, refetched=winner)
        repo.upsert_news.assert_not_called()
        self.assertIs(serialize.call_args.args[2], True)

    def test_naver_url_variants_share_one_row(self):
        legacy = stored('https://n.news.naver.com/mnews/article/001/0016392704?sid=104')
        _, prepare, repo, _, _ = self.run_analyze(
            found=legacy, url='https://n.news.naver.com/article/001/0016392704?cds=news_edit')
        canonical = 'https://n.news.naver.com/mnews/article/001/0016392704'
        self.assertEqual(repo.fetch_news_by_canonical_url.call_args.args[1], canonical)
        self.assertEqual(prepare.call_args.args[0], legacy.url)
        self.assertEqual(repo.upsert_news.call_args.args[2], legacy.url)  # legacy row updated, no duplicate

    def test_third_report_drops_analysis(self):
        s = self.service
        with patch.object(s, 'get_session', return_value=nullcontext(MagicMock())) as session, \
             patch.object(s, 'repository') as repo:
            session.return_value.enter_result.get.return_value = Mock(analysis=Mock())
            repo.report_counts.return_value = (2, True)
            self.assertFalse(s.report_news(1, USER, '본문이 다름').reanalysis)
            repo.delete_news_analysis.assert_not_called()
            repo.report_counts.return_value = (3, True)
            self.assertTrue(s.report_news(1, USER, '').reanalysis)
            repo.delete_news_analysis.assert_called_once()

    def test_shared_from_other_flag(self):
        s = self.service
        news = Mock(id=1, title='t', url='u', article_data={'extraData': {'submitted_by': 7, 'content_origin': 'browser'}})
        analysis = Mock(ad_probability=0.5, summary='s')
        with patch.object(s, 'extract_keywords_from_article_data', return_value=[]):
            mine = s.serialize_analysis_response(news, analysis, True, [], USER)
            other = s.serialize_analysis_response(news, analysis, True, [], types.SimpleNamespace(id=8))
        self.assertFalse(mine.sharedFromOther)
        self.assertTrue(other.sharedFromOther)
        self.assertEqual(other.adLikelihood.label, '검토 필요')

    def test_lead_matching(self):
        self.assertTrue(self.service.matches_lead(LEAD, '[서울=뉴시스] ' + LEAD + ' 후략'))
        self.assertFalse(self.service.matches_lead(LEAD, '야구 경기에서 홈런이 나왔다. ' * 10))
        self.assertTrue(self.service.matches_lead('짧음', '무엇이든'))


if __name__ == '__main__':
    unittest.main()
