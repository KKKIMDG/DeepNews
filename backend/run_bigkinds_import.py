from __future__ import annotations

import argparse
import shutil
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import psycopg2

from .batch.bigkinds import parse_rows, read_export
from .batch.storage import import_bigkinds_articles
from .domains.crawl.service import limit_token_counts

PROCESSED_DIR = "processed"
FAILED_DIR = "failed"
# A file still being copied into the inbox may be read half-written.
MIN_FILE_AGE_SECONDS = 60


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a BigKinds Excel export as recommendation candidates")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", help="BigKinds 뉴스검색 엑셀(.xlsx) 경로")
    source.add_argument(
        "--inbox",
        help=f"Import every *.xlsx in this folder, then move each to {PROCESSED_DIR}/ or {FAILED_DIR}/",
    )
    parser.add_argument("--limit", type=int, default=0, help="Import at most N articles per file (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report only; do not touch the DB")
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit must be 0 or positive")
    if args.inbox and args.dry_run:
        parser.error("--dry-run is only supported with --file")
    return args


def import_file(path: str | Path, limit: int = 0, dry_run: bool = False) -> int:
    rows = read_export(str(path))
    result = parse_rows(rows, limit_token_counts)
    articles = result.articles[:limit] if limit else result.articles

    print(f"rows: {len(rows)} | importable: {len(result.articles)} | skipped: {dict(result.skipped)}")
    categories = Counter(article.categories[0].split(">")[0] for article in articles if article.categories)
    print(f"top-level categories: {dict(categories.most_common())}")
    dates = sorted({article.published_at for article in articles if article.published_at})
    if dates:
        print(f"published: {dates[0]} ~ {dates[-1]}")

    if dry_run:
        print("dry run: DB not modified")
        return 0

    inserted = import_bigkinds_articles(articles, import_time=datetime.now().isoformat(timespec="seconds"))
    print(f"inserted: {inserted} | already in DB (left untouched): {len(articles) - inserted}")
    return inserted


def pending_exports(inbox: Path, now: float | None = None) -> list[Path]:
    now = time.time() if now is None else now
    return sorted(
        path
        for path in inbox.glob("*.xlsx")
        # '~$name.xlsx' is Excel's lock file for a workbook that is open.
        if path.is_file() and not path.name.startswith("~$") and now - path.stat().st_mtime >= MIN_FILE_AGE_SECONDS
    )


def move_to(path: Path, folder: str) -> Path:
    target_dir = path.parent / folder
    target_dir.mkdir(exist_ok=True)
    target = target_dir / f"{datetime.now():%Y%m%d-%H%M%S}_{path.name}"
    shutil.move(str(path), str(target))
    return target


def process_inbox(inbox: Path, limit: int = 0) -> int:
    """Returns the number of files that could not be imported."""
    if not inbox.is_dir():
        raise SystemExit(f"inbox folder not found: {inbox}")
    exports = pending_exports(inbox)
    print(f"inbox: {inbox} | files to import: {len(exports)}")
    problems = 0
    for path in exports:
        print(f"== {path.name}")
        try:
            import_file(path, limit=limit)
        except psycopg2.OperationalError as exception:
            # DB unreachable: the file itself is fine, so leave it for the next run.
            print(f"[RETRY LATER] {path.name}: {exception}", file=sys.stderr)
            problems += 1
            continue
        except Exception as exception:
            target = move_to(path, FAILED_DIR)
            target.with_name(target.name + ".error.txt").write_text(
                f"{type(exception).__name__}: {exception}\n", encoding="utf-8"
            )
            print(f"[FAILED] {path.name} -> {target}: {type(exception).__name__}: {exception}", file=sys.stderr)
            problems += 1
            continue
        print(f"[DONE] {path.name} -> {move_to(path, PROCESSED_DIR)}")
    return problems


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.inbox:
        return 1 if process_inbox(Path(args.inbox), limit=args.limit) else 0
    import_file(args.file, limit=args.limit, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
