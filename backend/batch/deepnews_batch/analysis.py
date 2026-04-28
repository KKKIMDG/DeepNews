from __future__ import annotations

from typing import Any

import requests

from .storage import fetch_unanalyzed_news, upsert_news_analysis_results


def run_analysis_pipeline(
    mode: str,
    limit: int,
    ai_service_url: str | None = None,
    database_url: str | None = None,
) -> int:
    dsn = database_url or _database_url_from_env()
    news_rows = fetch_unanalyzed_news(dsn, limit=limit)
    if not news_rows:
        return 0

    if mode == "fastapi":
        if not ai_service_url:
            raise RuntimeError("AI service URL is required for fastapi mode.")
        analysis_rows = analyze_with_fastapi(news_rows, ai_service_url)
    else:
        analysis_rows = analyze_with_placeholder(news_rows)

    return upsert_news_analysis_results(dsn, analysis_rows)


def analyze_with_placeholder(news_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for row in news_rows:
        content = str(row.get("content", ""))
        summary = content if len(content) <= 280 else content[:277].rstrip() + "..."
        results.append(
            {
                "news_id": row["news_id"],
                "summary": summary,
                "ad_probability": 0.0,
                "is_clickbait": False,
                "named_entities": [],
            }
        )
    return results


def analyze_with_fastapi(news_rows: list[dict[str, Any]], ai_service_url: str) -> list[dict[str, Any]]:
    base_url = ai_service_url.rstrip("/")
    results: list[dict[str, Any]] = []

    for row in news_rows:
        response = requests.post(
            f"{base_url}/ai/analyze",
            json={
                "url": row["url"],
                "title": row["title"],
                "text": row["content"],
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        results.append(
            {
                "news_id": row["news_id"],
                "summary": payload.get("summary") or row["content"][:280],
                "ad_probability": payload.get("ad_prob", 0.0),
                "is_clickbait": payload.get("is_clickbait", payload.get("is_ad", False)),
                "named_entities": payload.get("entities", []),
            }
        )

    return results


def _database_url_from_env() -> str:
    database_url = (
        __import__("os").environ.get("DATABASE_URL", "").strip()
    )
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for analysis sync.")
    return database_url
