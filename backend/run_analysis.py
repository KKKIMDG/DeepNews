from __future__ import annotations

import argparse
import sys

from .batch.analysis import MODES, ModelsNotReady, run_analysis_pipeline


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"positive integer required: {value!r}")
    if number <= 0:
        raise argparse.ArgumentTypeError(f"positive integer required: {value!r}")
    return number


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DeepNews analysis runner")
    parser.add_argument(
        "--mode",
        choices=MODES,
        default="service",
        help="service: run the models and store results / placeholder: dry run, lists the queue without writing",
    )
    parser.add_argument("--limit", type=positive_int, default=20, help="Number of queued rows to process")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_analysis_pipeline(mode=args.mode, limit=args.limit)
    except ModelsNotReady as exception:
        print(f"[ERROR] {exception}", file=sys.stderr)
        return 2

    if result.dry_run:
        print(f"[DRY RUN] queued rows: {result.fetched} | DB not modified")
        return 0

    print(f"[DONE] fetched: {result.fetched} | written: {result.written} | failed: {len(result.failures)}")
    if result.stopped_reason:
        print(f"[STOPPED] {result.stopped_reason}", file=sys.stderr)
        return 2
    return 1 if result.failures else 0


if __name__ == "__main__":
    sys.exit(main())
