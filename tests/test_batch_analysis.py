"""Batch analysis runner with the model service and storage replaced by fakes.
The real backend.domains.analysis.service is never imported (it loads the models)."""
import importlib
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import sys
import types
import unittest
from unittest.mock import Mock, patch

analysis = importlib.import_module('backend.batch.analysis')
run_analysis = importlib.import_module('backend.run_analysis')
analysis_package = importlib.import_module('backend.domains.analysis')

SERVICE_MODULE = 'backend.domains.analysis.service'


class AnalysisUnavailable(RuntimeError):
    pass


def news(news_id):
    return {'news_id': news_id, 'title': f'기사 {news_id}', 'url': f'https://a/{news_id}', 'content': '본문' * 100}


def default_analyze(url, title, text):
    return {'summary': f'{title} 요약', 'ad_probability': 0.12, 'is_clickbait': False, 'named_entities': []}


def fake_service(ready=True, analyze=default_analyze):
    service = types.ModuleType(SERVICE_MODULE)
    service.AnalysisUnavailable = AnalysisUnavailable
    service.models_ready = Mock(return_value=ready)
    service.settings = types.SimpleNamespace(ad_model_dir='model/ad_model', summary_model_dir='model/kobart')
    service.analyze_article = Mock(side_effect=analyze)
    return service


class BatchAnalysisTests(unittest.TestCase):
    def run_pipeline(self, service, rows, mode='service', store=None):
        fetch = Mock(return_value=rows)
        store = store or Mock(return_value=1)
        with patch.dict(sys.modules, {SERVICE_MODULE: service}), \
                patch.object(analysis_package, 'service', service, create=True), \
                patch.object(analysis, 'fetch_unanalyzed_news', fetch), \
                patch.object(analysis, 'upsert_news_analysis_results', store), \
                redirect_stdout(StringIO()):
            result = analysis.run_analysis_pipeline(mode=mode, limit=10)
        return result, fetch, store

    def test_placeholder_is_a_dry_run(self):
        service = fake_service()
        service.models_ready.side_effect = AssertionError('placeholder mode must not touch the models')
        result, fetch, store = self.run_pipeline(service, [news(1), news(2)], mode='placeholder')
        self.assertTrue(result.dry_run)
        self.assertEqual((result.fetched, result.written), (2, 0))
        fetch.assert_called_once()
        store.assert_not_called()
        service.analyze_article.assert_not_called()

    def test_refuses_without_models(self):
        fetch = Mock()
        with patch.dict(sys.modules, {SERVICE_MODULE: fake_service(ready=False)}), \
                patch.object(analysis_package, 'service', sys.modules[SERVICE_MODULE], create=True), \
                patch.object(analysis, 'fetch_unanalyzed_news', fetch):
            with self.assertRaises(analysis.ModelsNotReady):
                analysis.run_analysis_pipeline(mode='service', limit=10)
        fetch.assert_not_called()

    def test_failing_row_does_not_lose_the_batch(self):
        def analyze(url, title, text):
            if url.endswith('/2'):
                raise ValueError('bad input')
            return {'summary': '요약', 'ad_probability': 0.9, 'is_clickbait': True}

        result, _, store = self.run_pipeline(fake_service(analyze=analyze), [news(1), news(2), news(3)])
        self.assertEqual(result.written, 2)
        self.assertEqual([news_id for news_id, _ in result.failures], [2])
        # One commit per row, so earlier results survive a later failure.
        self.assertEqual([call.args[0][0]['news_id'] for call in store.call_args_list], [1, 3])

    def test_storage_failure_is_recorded_per_row(self):
        store = Mock(side_effect=[1, RuntimeError('db'), 1])
        result, _, _ = self.run_pipeline(fake_service(), [news(1), news(2), news(3)], store=store)
        self.assertEqual(result.written, 2)
        self.assertEqual([news_id for news_id, _ in result.failures], [2])

    def test_unavailable_stops_the_run(self):
        def analyze(url, title, text):
            if url.endswith('/2'):
                raise AnalysisUnavailable('GPU busy')
            return {'summary': '요약', 'ad_probability': 0.1}

        result, _, store = self.run_pipeline(fake_service(analyze=analyze), [news(1), news(2), news(3)])
        self.assertEqual(result.written, 1)
        self.assertEqual(result.stopped_reason, 'GPU busy')
        self.assertEqual(result.failures, [])
        self.assertEqual(store.call_count, 1)

    def test_limit_must_be_positive(self):
        for limit in (0, -1, True, '5'):
            with self.assertRaises(ValueError):
                analysis.run_analysis_pipeline(mode='placeholder', limit=limit)


class RunAnalysisCliTests(unittest.TestCase):
    def test_defaults_to_service(self):
        args = run_analysis.parse_args([])
        self.assertEqual((args.mode, args.limit), ('service', 20))

    def test_rejects_non_positive_limit(self):
        for value in ('0', '-3', 'abc'):
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                run_analysis.parse_args(['--limit', value])

    def test_exit_codes(self):
        cases = [
            (analysis.AnalysisRunResult(fetched=1, written=1), 0),
            (analysis.AnalysisRunResult(fetched=2, written=1, failures=[(2, 'x')]), 1),
            (analysis.AnalysisRunResult(fetched=2, written=1, stopped_reason='GPU busy'), 2),
            (analysis.AnalysisRunResult(fetched=2, dry_run=True), 0),
        ]
        for result, code in cases:
            with patch.object(run_analysis, 'run_analysis_pipeline', return_value=result), \
                    redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(run_analysis.main([]), code)
        with patch.object(run_analysis, 'run_analysis_pipeline', side_effect=analysis.ModelsNotReady('no model')), \
                redirect_stderr(StringIO()):
            self.assertEqual(run_analysis.main([]), 2)


if __name__ == '__main__':
    unittest.main()
