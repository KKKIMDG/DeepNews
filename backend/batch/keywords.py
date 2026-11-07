"""Re-pick stored articles' keywords with the current extractor (Kiwi noun phrases + crawl.service.select_keywords,
with the analysis.embedding context model).

Only rows with full text are touched (browser-submitted or crawled before that path was removed); BigKinds
candidates keep BigKinds' own keyword column. Only extraData.token_counts/keywords and article_keyword change:
the text, summary and analysis stay as they are. Everything is written in one transaction.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from psycopg2.extras import Json, execute_values

from ..config import settings
from ..domains.analysis import embedding
from ..domains.crawl.extractor import extract_token_counts, get_analyzer
from ..domains.crawl.service import keyword_candidates, keyword_document, select_keywords
from .storage import connect, get_keyword_ids, refresh_keyword_stats, upsert_keywords

FULL_TEXT_ROWS = """
    select n.id, n.title, n.article_data->>'content', coalesce(na.summary, ''),
           coalesce(n.article_data->'extraData'->'token_counts', '{}'::jsonb)
    from news n
    left join news_analysis na on na.news_id = n.id
    where not coalesce((n.article_data->'extraData'->>'content_partial')::boolean, false)
      and length(coalesce(n.article_data->>'content', '')) >= 80
    order by n.id
"""


class AnalyzerUnavailable(RuntimeError):
    pass


@dataclass
class KeywordRefreshResult:
    scanned: int = 0
    changed: int = 0
    applied: bool = False
    samples: list[tuple[int, str, list[str], list[str]]] = field(default_factory=list)


def refresh_keywords(apply: bool, limit: int | None = None, sample: int = 10,
                     database_url: str | None = None) -> KeywordRefreshResult:
    analyzer, name = get_analyzer()
    if name != "Kiwi":
        # The regex fallback would replace good keywords with worse ones.
        raise AnalyzerUnavailable("kiwipiepy가 설치되어 있지 않습니다. pip install -r requirements.txt")
    if embedding.keyword_context("모델 확인", ["확인"]) is None:
        # Without context the API would pick different keywords than this batch; run it where the model is.
        raise AnalyzerUnavailable(f"키워드 문맥 모델이 없습니다: {settings.keyword_model_dir}")

    result = KeywordRefreshResult(applied=apply)
    with connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("select count(*) from news")
        total_docs = cursor.fetchone()[0]
        # IDF snapshot taken before any change, so every article is scored against the same statistics.
        cursor.execute("select word, article_count from keyword where article_count > 0")
        doc_freq = dict(cursor.fetchall())
        cursor.execute(FULL_TEXT_ROWS + (" limit %s" if limit else ""), (limit,) if limit else None)
        rows = cursor.fetchall()

        updates: list[tuple[int, dict[str, int]]] = []
        for news_id, title, content, summary, old in rows:
            candidates = extract_token_counts(content, analyzer)
            title = title or ""
            context = embedding.keyword_context(keyword_document(title, summary, content),
                                                keyword_candidates(candidates, title=title, summary=summary))
            keywords = select_keywords(candidates, title=title, summary=summary, content=content,
                                       doc_freq=doc_freq, total_docs=total_docs, context=context)
            result.scanned += 1
            if keywords != old:
                updates.append((news_id, keywords))
                if len(result.samples) < sample:
                    result.samples.append((news_id, title or "", list(old), list(keywords)))
        result.changed = len(updates)
        if apply and updates:
            write_keywords(cursor, updates)
    return result


def write_keywords(cursor, updates: list[tuple[int, dict[str, int]]]) -> None:
    news_ids = [news_id for news_id, _ in updates]
    execute_values(
        cursor,
        """
        update news n
        set article_data = n.article_data || jsonb_build_object('extraData',
            coalesce(n.article_data->'extraData', '{}'::jsonb)
            || jsonb_build_object('token_counts', v.token_counts, 'keywords', v.keywords))
        from (values %s) as v(id, token_counts, keywords)
        where n.id = v.id
        """,
        [(news_id, Json(keywords), Json([{"term": term, "count": count} for term, count in keywords.items()]))
         for news_id, keywords in updates],
        template="(%s, %s::jsonb, %s::jsonb)",
    )

    cursor.execute("select distinct keyword_id from article_keyword where news_id = any(%s)", (news_ids,))
    affected = {row[0] for row in cursor.fetchall()}
    cursor.execute("delete from article_keyword where news_id = any(%s)", (news_ids,))

    words = sorted({word for _, keywords in updates for word in keywords})
    upsert_keywords(cursor, words)
    keyword_ids = get_keyword_ids(cursor, words)
    mappings = [(news_id, keyword_ids[word], count) for news_id, keywords in updates for word, count in keywords.items()]
    if mappings:
        execute_values(cursor, "insert into article_keyword (news_id, keyword_id, count) values %s", mappings,
                       template="(%s, %s, %s)")
    refresh_keyword_stats(cursor, affected | {keyword_id for _, keyword_id, _ in mappings})
