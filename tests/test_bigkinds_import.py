"""backend/__init__.py, backend/batch/__init__.py and the crawl extractor have no import-time side
effects, so the parser is imported as a package module (it needs canonical_article_url).
run_bigkinds_import imports backend.config, which only needs DATABASE_URL to be set."""
import importlib
import os
from pathlib import Path
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch

import psycopg2

bigkinds = importlib.import_module('backend.batch.bigkinds')
importer = importlib.import_module('backend.run_bigkinds_import')

NAN = float('nan')  # what pandas yields for empty cells


def row(**overrides):
    base = {'뉴스 식별자': '02100101.20261030123456789', '일자': '20261030', '언론사': '뉴스핌',
            '제목': '반도체 수출 3개월 연속 증가', '통합 분류1': '경제>반도체', '통합 분류2': ' 경제>무역',
            '통합 분류3': NAN, '키워드': '반도체,수출,증가,반도체,수,', '본문': '[서울=뉴스핌] 반도체 수출이...',
            'URL': 'https://www.newspim.com/news/view/1', '분석제외 여부': NAN}
    base.update(overrides)
    return base


def parse(rows):
    return bigkinds.parse_rows(rows, lambda counts: counts)


class BigKindsParseTests(unittest.TestCase):
    def test_row_becomes_partial_candidate(self):
        result = parse([row()])
        article = result.articles[0]
        self.assertEqual(article.bigkinds_id, '02100101.20261030123456789')
        self.assertEqual(article.published_at, '2026-10-30')
        self.assertEqual(article.categories, ['경제>반도체', '경제>무역'])
        self.assertEqual(article.token_counts, {'반도체': 2, '수출': 1, '증가': 1})  # 1-char '수' dropped

        data = article.article_data('2026-10-30T12:00:00')
        self.assertEqual(data['source'], 'www.newspim.com')
        self.assertTrue(data['extraData']['content_partial'])
        self.assertEqual(data['extraData']['content_origin'], 'bigkinds')
        self.assertEqual(data['extraData']['category'], '경제>반도체')

    def test_skips_rows_bigkinds_excluded_or_unlinkable(self):
        result = parse([row(**{'분석제외 여부': '중복'}), row(URL=NAN), row(URL='ftp://x/1'),
                        row(URL='https://x/' + 'a' * 600), row(제목=NAN, URL='https://x/2'),
                        row(), row()])
        self.assertEqual(len(result.articles), 1)
        self.assertEqual(dict(result.skipped), {'bigkinds_excluded': 1, 'no_url': 1, 'invalid_url': 2,
                                                'no_title': 1, 'duplicate_url': 1})

    def test_limiter_is_applied(self):
        result = bigkinds.parse_rows([row()], lambda counts: dict(list(counts.items())[:1]))
        self.assertEqual(result.articles[0].token_counts, {'반도체': 2})

    def test_html_escaped_url_is_unescaped(self):
        url = 'https://news.kbs.co.kr/news/view.do?ncd=1&amp;ref=DA'
        self.assertEqual(parse([row(URL=url)]).articles[0].url, 'https://news.kbs.co.kr/news/view.do?ncd=1&ref=DA')

    def test_bad_date_is_blank(self):
        self.assertEqual(parse([row(일자='날짜없음')]).articles[0].published_at, '')

    def test_naver_url_is_canonical_like_the_extension(self):
        canonical = 'https://n.news.naver.com/mnews/article/001/0016392704'
        result = parse([row(URL='https://n.news.naver.com/article/001/0016392704?sid=104'),
                        row(URL='https://news.naver.com/main/read.naver?mode=LSD&amp;oid=001&amp;aid=0016392704')])
        self.assertEqual([article.url for article in result.articles], [canonical])
        self.assertEqual(dict(result.skipped), {'duplicate_url': 1})

    def test_other_publisher_url_is_kept(self):
        url = 'https://news.kbs.co.kr/news/view.do?ncd=1&ref=DA'
        self.assertEqual(parse([row(URL=url)]).articles[0].url, url)


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.inbox = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def make(self, name, age_seconds=600):
        path = self.inbox / name
        path.write_bytes(b'xlsx')
        stamp = time.time() - age_seconds
        os.utime(path, (stamp, stamp))
        return path

    def test_pending_skips_lock_fresh_and_other_files(self):
        self.make('a.xlsx')
        self.make('~$a.xlsx')
        self.make('copying.xlsx', age_seconds=5)
        self.make('notes.txt')
        self.assertEqual([path.name for path in importer.pending_exports(self.inbox)], ['a.xlsx'])

    def test_files_are_moved_by_outcome(self):
        for name in ('ok.xlsx', 'broken.xlsx', 'db_down.xlsx'):
            self.make(name)

        def fake_import(path, limit=0):
            if path.name == 'broken.xlsx':
                raise ValueError('BigKinds 엑셀 형식이 아닙니다.')
            if path.name == 'db_down.xlsx':
                raise psycopg2.OperationalError('connection refused')
            return 3

        with patch.object(importer, 'import_file', side_effect=fake_import),                 redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            problems = importer.process_inbox(self.inbox)

        self.assertEqual(problems, 2)
        self.assertEqual(sorted(path.name for path in self.inbox.glob('*.xlsx')), ['db_down.xlsx'])
        processed = list((self.inbox / 'processed').iterdir())
        self.assertEqual(len(processed), 1)
        self.assertTrue(processed[0].name.endswith('_ok.xlsx'))
        failed = sorted(path.name for path in (self.inbox / 'failed').iterdir())
        self.assertEqual(len(failed), 2)
        self.assertTrue(failed[0].endswith('_broken.xlsx'))
        error_text = (self.inbox / 'failed' / failed[1]).read_text(encoding='utf-8')
        self.assertIn('ValueError', error_text)

    def test_main_exit_code(self):
        self.make('ok.xlsx')
        with patch.object(importer, 'import_file', return_value=1), redirect_stdout(StringIO()):
            self.assertEqual(importer.main(['--inbox', str(self.inbox)]), 0)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            importer.parse_args(['--inbox', str(self.inbox), '--dry-run'])


if __name__ == '__main__':
    unittest.main()
