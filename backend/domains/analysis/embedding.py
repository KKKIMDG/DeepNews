"""Sentence embeddings that let keyword selection see an article's context (multilingual-e5-small, MIT).

Loaded on first use, not at import, so batch tools that never pick keywords do not pay for it. When the model is
missing or busy, keyword_context returns None and keywords are picked by frequency and position alone.
"""
from __future__ import annotations

import logging
import threading

from ...config import settings

logger = logging.getLogger(__name__)

# e5 was trained with these prefixes: short queries (keyword candidates) against passages (the article).
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "
MAX_TOKENS = 256
# A batch of ~60 short terms takes about 10 ms on the GPU; past this wait the keywords go without context.
SLOT_WAIT_SECONDS = 10

_load_lock = threading.Lock()
_slots = threading.BoundedSemaphore(2)
_loaded = None  # (tokenizer, model, device) once loaded, False if loading failed


def _load():
    global _loaded
    with _load_lock:
        if _loaded is None and not settings.keyword_model_dir.is_dir():
            logger.warning("키워드 문맥 모델이 없습니다(%s). 빈도·위치만으로 키워드를 고릅니다.", settings.keyword_model_dir.name)
            _loaded = False
        if _loaded is None:
            try:
                import torch
                from transformers import AutoModel, AutoTokenizer

                tokenizer = AutoTokenizer.from_pretrained(settings.keyword_model_dir)
                model = AutoModel.from_pretrained(settings.keyword_model_dir)
                device = "cuda" if torch.cuda.is_available() else "cpu"
                _loaded = (tokenizer, model.to(device).eval(), device)
            except Exception:
                logger.warning("키워드 문맥 모델을 불러오지 못했습니다. 빈도·위치만으로 키워드를 고릅니다.", exc_info=True)
                _loaded = False
    return _loaded or None


def ready() -> bool:
    return bool(_loaded)


def _embed(texts: list[str]):
    """Mean-pooled, L2-normalized vectors (numpy, one row per text)."""
    import torch

    tokenizer, model, device = _loaded
    batch = tokenizer(texts, padding=True, truncation=True, max_length=MAX_TOKENS, return_tensors="pt").to(device)
    with torch.inference_mode():
        hidden = model(**batch).last_hidden_state
    mask = batch["attention_mask"].unsqueeze(-1).to(hidden.dtype)
    pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
    return torch.nn.functional.normalize(pooled, dim=-1).float().cpu().numpy()


def keyword_context(document: str, terms: list[str]):
    """(document vector, {term: vector}) for crawl.service.select_keywords, or None without the model."""
    if not terms or not document.strip() or not _load():
        return None
    if not _slots.acquire(timeout=SLOT_WAIT_SECONDS):
        return None
    try:
        vectors = _embed([PASSAGE_PREFIX + document] + [QUERY_PREFIX + term for term in terms])
    except Exception:
        logger.exception("키워드 문맥 계산 실패")
        return None
    finally:
        _slots.release()
    return vectors[0], dict(zip(terms, vectors[1:]))


def warm_up() -> None:
    keyword_context("정부는 오늘 내년도 예산안을 발표했다.", ["예산안"])
