from __future__ import annotations

import argparse
import json

from backend.domains.recommendation.service import (
    build_mapping,
    build_svd_model,
    collect_demo_naver_news,
    get_demo_user,
    recommend_naver_news,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the MIND SVD + Naver mock recommendation demo.")
    parser.add_argument("--per-keyword", type=int, default=100)
    parser.add_argument("--max-behaviors", type=int, default=100_000)
    parser.add_argument("--components", type=int, default=64)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--skip-collect", action="store_true")
    args = parser.parse_args()

    if not args.skip_collect:
        print(json.dumps(collect_demo_naver_news(None, args.per_keyword), ensure_ascii=False, indent=2))
    print(json.dumps(build_svd_model(args.max_behaviors, args.components), ensure_ascii=False, indent=2))
    print(json.dumps(build_mapping(), ensure_ascii=False, indent=2))
    demo_user = get_demo_user()
    print(json.dumps(demo_user, ensure_ascii=False, indent=2))
    print(json.dumps(recommend_naver_news(demo_user["userId"], args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
