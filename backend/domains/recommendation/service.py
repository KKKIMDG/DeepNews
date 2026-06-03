from __future__ import annotations

from .mind_svd import choose_demo_user, load_model, recommend_mind_news, train_model
from .mock_mapping import build_mock_mapping, load_mapping
from .naver_collector import DEFAULT_KEYWORDS, collect_naver_news
from .schemas import NaverRecommendationItem


def collect_demo_naver_news(keywords: list[str] | None, per_keyword: int) -> dict:
    return collect_naver_news(keywords or DEFAULT_KEYWORDS, per_keyword=per_keyword)


def build_svd_model(max_behaviors: int, n_components: int) -> dict:
    return train_model(max_behaviors=max_behaviors, n_components=n_components)


def build_mapping(limit_mind_items: int | None = None) -> dict:
    return build_mock_mapping(limit_mind_items=limit_mind_items)


def get_demo_user() -> dict:
    model = load_model()
    user_id = choose_demo_user(model)
    return {"userId": user_id, "interactionCount": int(model["user_counts"].get(user_id, 0))}


def recommend_naver_news(user_id: str | None, limit: int) -> dict:
    recommendation = recommend_mind_news(user_id=user_id, limit=limit)
    mapping = load_mapping()

    items: list[NaverRecommendationItem] = []
    for mind_item in recommendation["items"]:
        mapped = mapping.get(mind_item["mindNewsId"])
        if not mapped:
            continue
        item = NaverRecommendationItem(
                newsId=mapped["newsId"],
                title=mapped["title"],
                url=mapped["url"],
                description=mapped.get("description", ""),
                publisher=mapped.get("publisher", ""),
                pubDate=mapped.get("pubDate", ""),
                category=mapped.get("category", ""),
                score=float(mind_item["score"]),
                reason="MIND SVD collaborative filtering + Naver mock mapping",
            )
        items.append(item.model_dump())

    return {"userId": recommendation["userId"], "items": items}
