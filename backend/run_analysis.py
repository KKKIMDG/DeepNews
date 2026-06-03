from __future__ import annotations

import argparse

from .batch.analysis import run_analysis_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DeepNews analysis runner")
    parser.add_argument(
        "--mode",
        choices=["placeholder", "service"],
        default="placeholder",
        help="Analysis backend to use",
    )
    parser.add_argument("--limit", type=int, default=20, help="Number of unanalyzed rows to process")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    count = run_analysis_pipeline(
        mode=args.mode,
        limit=args.limit,
    )
    print(f"[DONE] Analysis rows written: {count}")


if __name__ == "__main__":
    main()
