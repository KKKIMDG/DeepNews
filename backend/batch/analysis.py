from __future__ import annotations

from typing import Any

from ..domains.analysis.service import analyze_article
from .storage import fetch_unanalyzed_news, upsert_news_analysis_results


def run_analysis_pipeline(mode: str, limit: int, database_url: str | None = None) -> int:
    news_rows = fetch_unanalyzed_news(database_url=database_url, limit=limit)
    if not news_rows:
        return 0

    if mode == "placeholder":
        analysis_rows = analyze_with_placeholder(news_rows)
    else:
        analysis_rows = analyze_with_service(news_rows)

    return upsert_news_analysis_results(analysis_rows, database_url=database_url)


def analyze_with_placeholder(news_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for row in news_rows:
        content = str(row.get("content", ""))
        summary = content if len(content) <= 280 else content[:277].rstrip() + "..."
        results.append(
            {
                "news_id": row["news_id"],
                "summary": summary,
                "ad_probability": -1.0,
                "is_clickbait": False,
                "named_entities": [],
            }
        )
    return results


def analyze_with_service(news_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for row in news_rows:
        payload = analyze_article(row["url"], row["title"], row["content"])
        results.append(
            {
                "news_id": row["news_id"],
                "summary": payload.get("summary") or row["content"][:280],
                "ad_probability": payload.get("ad_probability", -1.0),
                "is_clickbait": payload.get("is_clickbait", False),
                "named_entities": payload.get("named_entities", []),
            }
        )
    return results
