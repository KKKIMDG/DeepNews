from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ...config import settings
from .mind_svd import load_model, load_mind_news_metadata
from .naver_collector import NAVER_NEWS_PATH, load_collected_news

MAPPING_PATH = settings.recommendation_runtime_dir / "mind_naver_mapping.json"


def _stable_index(value: str, size: int) -> int:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % size


def build_mock_mapping(limit_mind_items: int | None = None, path: Path = MAPPING_PATH) -> dict:
    """Map MIND news IDs to collected Naver metadata for capstone demo output."""
    naver_news = load_collected_news(NAVER_NEWS_PATH)
    if not naver_news:
        raise RuntimeError("No collected Naver news found. Run Naver collection first.")

    model = load_model()
    mind_ids = model["items"][:limit_mind_items] if limit_mind_items else model["items"]
    mind_metadata = load_mind_news_metadata(limit=None)

    mapping = {}
    for mind_id in mind_ids:
        naver_item = naver_news[_stable_index(mind_id, len(naver_news))]
        mind_item = mind_metadata.get(mind_id, {})
        mapping[mind_id] = {
            "mindNewsId": mind_id,
            "mindCategory": mind_item.get("category", ""),
            "newsId": naver_item["news_id"],
            "title": naver_item["title"],
            "url": naver_item["url"],
            "description": naver_item.get("description", ""),
            "publisher": naver_item.get("publisher", ""),
            "pubDate": naver_item.get("pubDate", ""),
            "category": naver_item.get("category", ""),
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"mappedCount": len(mapping), "path": str(path), "naverNewsCount": len(naver_news)}


def load_mapping(path: Path = MAPPING_PATH) -> dict[str, dict]:
    if not path.exists():
        raise FileNotFoundError(f"Mock mapping not found. Build it first: {path}")
    return json.loads(path.read_text(encoding="utf-8"))
