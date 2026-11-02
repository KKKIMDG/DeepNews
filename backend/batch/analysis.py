"""Batch analysis of stored articles that have no (or only a placeholder) analysis.

- `service`: runs the real models and writes one row at a time, so a failing article never loses
  the results already computed in the run.
- `placeholder`: dry run. Lists the queued articles and never writes; placeholder output
  (ad_probability=-1, truncated text) must not be stored as a shared result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .storage import fetch_unanalyzed_news, upsert_news_analysis_results

MODES = ("service", "placeholder")


class ModelsNotReady(RuntimeError):
    pass


@dataclass
class AnalysisRunResult:
    fetched: int = 0
    written: int = 0
    failures: list[tuple[int, str]] = field(default_factory=list)
    stopped_reason: str = ""
    dry_run: bool = False


def run_analysis_pipeline(mode: str, limit: int, database_url: str | None = None) -> AnalysisRunResult:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}: {mode!r}")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError(f"limit must be a positive integer: {limit!r}")

    if mode == "placeholder":
        return preview_queue(limit, database_url)

    # Imported here: loading this module loads the models onto the GPU.
    from ..domains.analysis import service as analysis_service

    if not analysis_service.models_ready():
        raise ModelsNotReady(
            "분석 모델이 준비되지 않아 실행하지 않습니다. "
            f"{analysis_service.settings.ad_model_dir}, {analysis_service.settings.summary_model_dir}를 확인하세요."
        )

    news_rows = fetch_unanalyzed_news(database_url=database_url, limit=limit)
    result = AnalysisRunResult(fetched=len(news_rows))
    for row in news_rows:
        try:
            payload = analysis_service.analyze_article(row["url"], row["title"], row["content"])
        except analysis_service.AnalysisUnavailable as exception:
            # Models or GPU slots are unavailable for every row, not just this one.
            result.stopped_reason = str(exception)
            break
        except Exception as exception:
            record_failure(result, row, exception)
            continue

        try:
            result.written += upsert_news_analysis_results([to_analysis_row(row, payload)], database_url=database_url)
        except Exception as exception:
            record_failure(result, row, exception)
    return result


def preview_queue(limit: int, database_url: str | None) -> AnalysisRunResult:
    news_rows = fetch_unanalyzed_news(database_url=database_url, limit=limit)
    for row in news_rows:
        print(f"[DRY RUN] would analyze news_id={row['news_id']} ({len(row['content'])} chars) {row['title'][:60]}")
    return AnalysisRunResult(fetched=len(news_rows), dry_run=True)


def to_analysis_row(row: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "news_id": row["news_id"],
        "summary": payload["summary"],
        "ad_probability": payload["ad_probability"],
        "is_clickbait": payload.get("is_clickbait", False),
        "named_entities": payload.get("named_entities", []),
    }


def record_failure(result: AnalysisRunResult, row: dict[str, Any], exception: Exception) -> None:
    message = f"{type(exception).__name__}: {exception}"
    result.failures.append((row["news_id"], message))
    print(f"[FAIL] news_id={row['news_id']} {message}")
