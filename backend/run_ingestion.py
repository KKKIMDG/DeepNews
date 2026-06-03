from __future__ import annotations

import argparse
from pathlib import Path

from .batch.pipeline import run_ingestion_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DeepNews ingestion runner")
    parser.add_argument("--query", default="AI", help="Naver news search query")
    parser.add_argument("--limit", type=int, default=50, help="Number of articles to collect")
    parser.add_argument(
        "--output-dir",
        default="backend_fastapi/runtime/output",
        help="Directory for JSON and CSV outputs",
    )
    parser.add_argument(
        "--skip-db-sync",
        action="store_true",
        help="Skip database sync and only save local artifacts",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_ingestion_pipeline(
        query=args.query,
        limit=args.limit,
        output_dir=Path(args.output_dir),
        skip_db_sync=args.skip_db_sync,
    )
    print(f"[DONE] Articles collected: {result['article_count']}")
    print(f"[DONE] JSON saved: {result['json_path']}")
    print(f"[DONE] CSV saved: {result['csv_path']}")
    print(f"[INFO] Analyzer: {result['analyzer_name']}")
    if result["failure_path"]:
        print(f"[WARN] Failures saved: {result['failure_path']}")
    print(f"[INFO] Database sync: {'skipped' if not result['db_sync'] else 'completed'}")


if __name__ == "__main__":
    main()
