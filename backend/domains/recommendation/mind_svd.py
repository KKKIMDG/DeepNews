from __future__ import annotations

import json
import math
import pickle
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix, csr_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize

from ...config import settings

MODEL_PATH = settings.recommendation_runtime_dir / "mind_svd_model.pkl"
STATS_PATH = settings.recommendation_runtime_dir / "mind_svd_stats.json"


def _behavior_path() -> Path:
    return settings.mind_train_dir / "behaviors.tsv"


def _news_path() -> Path:
    return settings.mind_train_dir / "news.tsv"


def parse_impression(item: str) -> tuple[str, int]:
    news_id, clicked = item.rsplit("-", 1)
    return news_id, int(clicked)


def iter_behavior_rows(max_behaviors: int):
    path = _behavior_path()
    if not path.exists():
        raise FileNotFoundError(f"MIND behaviors.tsv not found: {path}")

    columns = ["impression_id", "user_id", "time", "history", "impressions"]
    read_count = 0
    for chunk in pd.read_csv(path, sep="\t", names=columns, chunksize=10_000):
        for row in chunk.itertuples(index=False):
            yield row
            read_count += 1
            if read_count >= max_behaviors:
                return


def build_interaction_matrix(max_behaviors: int) -> tuple[csr_matrix, list[str], list[str], dict[str, int]]:
    """Build a sparse user-item matrix from MIND history and clicked impressions."""
    user_index: dict[str, int] = {}
    item_index: dict[str, int] = {}
    rows: list[int] = []
    cols: list[int] = []
    values: list[float] = []
    user_counts: dict[str, int] = defaultdict(int)

    def index_user(user_id: str) -> int:
        if user_id not in user_index:
            user_index[user_id] = len(user_index)
        return user_index[user_id]

    def index_item(news_id: str) -> int:
        if news_id not in item_index:
            item_index[news_id] = len(item_index)
        return item_index[news_id]

    for row in iter_behavior_rows(max_behaviors):
        user_id = str(row.user_id)
        uidx = index_user(user_id)

        history = "" if pd.isna(row.history) else str(row.history)
        for news_id in history.split():
            rows.append(uidx)
            cols.append(index_item(news_id))
            values.append(0.4)
            user_counts[user_id] += 1

        impressions = "" if pd.isna(row.impressions) else str(row.impressions)
        for raw_item in impressions.split():
            try:
                news_id, clicked = parse_impression(raw_item)
            except ValueError:
                continue
            if clicked:
                rows.append(uidx)
                cols.append(index_item(news_id))
                values.append(1.0)
                user_counts[user_id] += 1

    if not rows:
        raise RuntimeError("No MIND interactions were parsed.")

    matrix = coo_matrix(
        (values, (rows, cols)),
        shape=(len(user_index), len(item_index)),
        dtype=np.float32,
    ).tocsr()

    users = [None] * len(user_index)
    for user_id, index in user_index.items():
        users[index] = user_id
    items = [None] * len(item_index)
    for news_id, index in item_index.items():
        items[index] = news_id
    return matrix, users, items, dict(user_counts)


def train_model(max_behaviors: int = 100_000, n_components: int = 64) -> dict[str, Any]:
    """Train a compact SVD recommender from MIND interactions."""
    matrix, users, items, user_counts = build_interaction_matrix(max_behaviors)
    component_count = max(2, min(n_components, min(matrix.shape) - 1))

    svd = TruncatedSVD(n_components=component_count, random_state=42)
    user_factors = svd.fit_transform(matrix).astype(np.float32)
    item_factors = svd.components_.T.astype(np.float32)
    user_factors = normalize(user_factors).astype(np.float32)
    item_factors = normalize(item_factors).astype(np.float32)

    model = {
        "users": users,
        "items": items,
        "user_index": {user_id: idx for idx, user_id in enumerate(users)},
        "item_index": {news_id: idx for idx, news_id in enumerate(items)},
        "user_factors": user_factors,
        "item_factors": item_factors,
        "seen_items": {
            users[uidx]: matrix.getrow(uidx).indices.astype(np.int32)
            for uidx in range(matrix.shape[0])
        },
        "user_counts": user_counts,
    }

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MODEL_PATH.open("wb") as file:
        pickle.dump(model, file)

    demo_user = choose_demo_user(model)
    stats = {
        "maxBehaviors": max_behaviors,
        "users": len(users),
        "items": len(items),
        "components": component_count,
        "explainedVarianceRatio": float(np.sum(svd.explained_variance_ratio_)),
        "demoUserId": demo_user,
        "modelPath": str(MODEL_PATH),
    }
    STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def load_model() -> dict[str, Any]:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"SVD model not found. Build it first: {MODEL_PATH}")
    with MODEL_PATH.open("rb") as file:
        return pickle.load(file)


def choose_demo_user(model: dict[str, Any]) -> str:
    counts = model.get("user_counts", {})
    if not counts:
        return model["users"][0]
    return max(counts.items(), key=lambda item: item[1])[0]


def recommend_mind_news(user_id: str | None, limit: int = 10, candidate_multiplier: int = 8) -> dict[str, Any]:
    model = load_model()
    resolved_user = user_id if user_id in model["user_index"] else choose_demo_user(model)
    uidx = model["user_index"][resolved_user]

    scores = model["item_factors"] @ model["user_factors"][uidx]
    seen = set(int(index) for index in model["seen_items"].get(resolved_user, []))
    candidate_count = min(len(scores), max(limit * candidate_multiplier, limit + len(seen)))
    ranked_indices = np.argpartition(-scores, candidate_count - 1)[:candidate_count]
    ranked_indices = ranked_indices[np.argsort(-scores[ranked_indices])]

    items = []
    for item_index in ranked_indices:
        if int(item_index) in seen:
            continue
        score = float(scores[item_index])
        if math.isnan(score):
            continue
        items.append({"mindNewsId": model["items"][int(item_index)], "score": round(score, 6)})
        if len(items) >= limit:
            break

    return {"userId": resolved_user, "items": items}


def load_mind_news_metadata(limit: int | None = None) -> dict[str, dict]:
    path = _news_path()
    if not path.exists():
        raise FileNotFoundError(f"MIND news.tsv not found: {path}")
    columns = [
        "news_id",
        "category",
        "subcategory",
        "title",
        "abstract",
        "url",
        "title_entities",
        "abstract_entities",
    ]
    metadata: dict[str, dict] = {}
    for chunk in pd.read_csv(path, sep="\t", names=columns, chunksize=10_000):
        for row in chunk.itertuples(index=False):
            metadata[str(row.news_id)] = {
                "mindNewsId": str(row.news_id),
                "category": str(row.category),
                "subcategory": str(row.subcategory),
                "title": "" if pd.isna(row.title) else str(row.title),
            }
            if limit and len(metadata) >= limit:
                return metadata
    return metadata
