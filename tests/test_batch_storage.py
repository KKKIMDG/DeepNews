"""SQL contract of the batch storage layer, checked against a fake psycopg2 connection.
backend.batch.storage only needs DATABASE_URL to be set; it never connects here."""
from datetime import timezone
import importlib
import unittest
from unittest.mock import MagicMock, patch

storage = importlib.import_module('backend.batch.storage')
bigkinds = importlib.import_module('backend.batch.bigkinds')


def fake_connection():
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    return connection, cursor


def article(url, token_counts):
    return bigkinds.BigKindsArticle(bigkinds_id='1', title='제목', url=url, publisher='뉴스핌',
                                    published_at='2026-10-30', categories=['경제>반도체'], lead='앞 200자',
                                    token_counts=token_counts)


class ImportBigKindsTests(unittest.TestCase):
    def test_inserts_new_urls_only_and_closes(self):
        connection, cursor = fake_connection()
        cursor.fetchall.return_value = [(10, '반도체'), (11, '수출')]
        calls = []

        def fake_execute_values(cur, sql, values, template=None, fetch=False):
            calls.append((sql, values))
            return [(1, 'https://a/1')] if fetch else None

        articles = [article('https://a/1', {'반도체': 2, '수출': 1}), article('https://a/2', {'정치': 1})]
        with patch.object(storage.psycopg2, 'connect', return_value=connection), \
                patch.object(storage, 'execute_values', side_effect=fake_execute_values):
            inserted = storage.import_bigkinds_articles(articles, '2026-10-30T12:00:00', database_url='dsn')

        self.assertEqual(inserted, 1)
        self.assertIn('on conflict (url) do nothing', calls[0][0])
        self.assertNotIn('do update', calls[0][0])
        # Keywords of the article that was already stored are not touched.
        self.assertEqual(calls[1][1], [('반도체',), ('수출',)])
        self.assertEqual(sorted(calls[2][1]), [(1, 10, 2), (1, 11, 1)])
        connection.close.assert_called_once()

    def test_empty_import_does_not_connect(self):
        with patch.object(storage.psycopg2, 'connect') as connect:
            self.assertEqual(storage.import_bigkinds_articles([], 'now'), 0)
        connect.assert_not_called()


class AnalysisQueueTests(unittest.TestCase):
    def test_queue_skips_partial_and_requeues_placeholders(self):
        connection, cursor = fake_connection()
        cursor.fetchall.return_value = [
            (7, '제목', 'https://a/7', {'content': '본문', 'publishedAt': '2026-10-30',
                                         'extraData': {'token_counts': {'반도체': 1}}}),
        ]
        with patch.object(storage.psycopg2, 'connect', return_value=connection):
            rows = storage.fetch_unanalyzed_news(database_url='dsn', limit=5)

        sql, params = cursor.execute.call_args.args
        normalized = ' '.join(sql.split())
        self.assertIn("coalesce((n.article_data->'extraData'->>'content_partial')::boolean, false) = false", normalized)
        self.assertIn('(na.id is null or na.ad_probability < 0)', normalized)
        self.assertEqual(params, (5,))
        self.assertEqual(rows[0]['news_id'], 7)
        self.assertEqual(rows[0]['content'], '본문')
        self.assertEqual(rows[0]['token_counts'], {'반도체': 1})
        connection.close.assert_called_once()

    def test_upsert_uses_aware_utc_time_and_closes(self):
        connection, _ = fake_connection()
        with patch.object(storage.psycopg2, 'connect', return_value=connection), \
                patch.object(storage, 'execute_values') as execute_values:
            written = storage.upsert_news_analysis_results(
                [{'news_id': 7, 'summary': '요약', 'ad_probability': 0.876, 'is_clickbait': True}], database_url='dsn')

        self.assertEqual(written, 1)
        sql, values = execute_values.call_args.args[1:3]
        self.assertIn('on conflict (news_id)', sql)
        news_id, summary, probability, is_ad, analyzed_at, _ = values[0]
        self.assertEqual((news_id, summary, probability, is_ad), (7, '요약', 0.88, True))
        self.assertIs(analyzed_at.tzinfo, timezone.utc)
        connection.close.assert_called_once()

    def test_connection_closed_and_rolled_back_on_error(self):
        connection, _ = fake_connection()
        with patch.object(storage.psycopg2, 'connect', return_value=connection), \
                patch.object(storage, 'execute_values', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                storage.upsert_news_analysis_results(
                    [{'news_id': 7, 'summary': '요약', 'ad_probability': 0.1, 'is_clickbait': False}])

        # `with connection` receives the exception (psycopg2 rolls back), then the connection is closed.
        self.assertIs(connection.__exit__.call_args.args[0], RuntimeError)
        connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
