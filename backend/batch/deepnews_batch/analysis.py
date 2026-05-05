from __future__ import annotations

from typing import Any

import requests
from urllib.parse import quote_plus

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
    os_module = __import__("os")
    database_url = os_module.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return database_url

    host = os_module.environ.get("DB_HOST", "").strip()
    port = os_module.environ.get("DB_PORT", "").strip()
    name = os_module.environ.get("DB_NAME", "").strip()
    user = os_module.environ.get("DB_USER", "").strip()
    password = os_module.environ.get("DB_PASSWORD", "").strip()
    sslmode = os_module.environ.get("DB_SSLMODE", "require").strip()

    if not all([host, port, name, user, password]):
        raise RuntimeError("DATABASE_URL or DB_* environment variables are required for analysis sync.")

    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{name}?sslmode={quote_plus(sslmode)}"
    )
