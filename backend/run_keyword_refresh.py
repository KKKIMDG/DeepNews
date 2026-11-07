from __future__ import annotations

import argparse
import sys

from .batch.keywords import AnalyzerUnavailable, refresh_keywords
from .run_analysis import positive_int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-pick stored articles' keywords with the current extractor")
    parser.add_argument("--apply", action="store_true", help="Write the new keywords (default: dry run, DB not modified)")
    parser.add_argument("--limit", type=positive_int, default=None, help="Only the first N full-text rows")
    parser.add_argument("--sample", type=int, default=10, help="Number of before/after examples to print")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = refresh_keywords(apply=args.apply, limit=args.limit, sample=args.sample)
    except AnalyzerUnavailable as exception:
        print(f"[ERROR] {exception}", file=sys.stderr)
        return 2

    for news_id, title, before, after in result.samples:
        print(f"\n#{news_id} {title}\n  이전: {', '.join(before)}\n  이후: {', '.join(after)}")
    label = "[DONE]" if result.applied else "[DRY RUN]"
    suffix = "" if result.applied else " | DB not modified"
    print(f"\n{label} scanned: {result.scanned} | changed: {result.changed}{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
