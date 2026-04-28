from __future__ import annotations

import argparse

from dotenv import load_dotenv

from deepnews_batch.analysis import run_analysis_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DeepNews analysis runner")
    parser.add_argument(
        "--mode",
        choices=["placeholder", "fastapi"],
        default="placeholder",
        help="Analysis backend to use",
    )
    parser.add_argument("--limit", type=int, default=20, help="Number of unanalyzed rows to process")
    parser.add_argument(
        "--ai-service-url",
        default="",
        help="FastAPI base URL, for example http://127.0.0.1:8000",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    count = run_analysis_pipeline(
        mode=args.mode,
        limit=args.limit,
        ai_service_url=args.ai_service_url or None,
    )
    print(f"[DONE] Analysis rows written: {count}")


if __name__ == "__main__":
    main()
