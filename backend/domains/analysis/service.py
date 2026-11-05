from __future__ import annotations

import logging
import threading
from typing import Any

from ...config import settings

logger = logging.getLogger(__name__)

# One place for the ad-probability bands (label, is_ad flag, ranking filter default).
AD_HIGH_THRESHOLD = 0.8
AD_REVIEW_THRESHOLD = 0.4
# The models only read the first 512 / 1024 tokens; tokenizing a 100k-character body is wasted CPU.
MAX_INPUT_CHARS = 6000
# The shared MIG slice runs at most this many inferences at once; the rest wait, then get 503.
# Measured on the MIG (2026-11-03): 2-3 concurrent give ~180 articles/min; 4+ drops to ~70/min.
_INFERENCE_SLOTS = threading.BoundedSemaphore(2)
INFERENCE_WAIT_SECONDS = 120


class AnalysisUnavailable(RuntimeError):
    """Models not loaded or the inference queue is full; the caller should answer 503."""

try:
    import torch
    import torch.nn.functional as F
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        BartForConditionalGeneration,
        PreTrainedTokenizerFast,
    )
except Exception:
    torch = None
    F = None
    AutoModelForSequenceClassification = None
    AutoTokenizer = None
    BartForConditionalGeneration = None
    PreTrainedTokenizerFast = None


device = torch.device("cuda" if torch and torch.cuda.is_available() else "cpu") if torch else "cpu"
logger.info("사용 디바이스: %s", device)

# 광고 판별 모델 로드
ad_tokenizer = None
ad_model = None
AD_MODEL_READY = False

if torch and AutoTokenizer and AutoModelForSequenceClassification and settings.ad_model_dir.exists():
    try:
        ad_tokenizer = AutoTokenizer.from_pretrained(str(settings.ad_model_dir), local_files_only=True)
        ad_model = AutoModelForSequenceClassification.from_pretrained(
            str(settings.ad_model_dir), local_files_only=True
        )
        ad_model.to(device)
        ad_model.eval()
        AD_MODEL_READY = True
        logger.info("광고 판별 모델 로드 완료: %s", settings.ad_model_dir)
    except Exception as exception:
        logger.exception("광고 판별 모델 로드 실패")
else:
    logger.warning("광고 판별 모델이 없습니다. 분석 요청은 503으로 응답합니다.")

# 요약 모델 (KoBART) 로드
summary_tokenizer = None
summary_model = None
SUMMARY_MODEL_READY = False

if torch and PreTrainedTokenizerFast and BartForConditionalGeneration and settings.summary_model_dir.exists():
    try:
        summary_tokenizer = PreTrainedTokenizerFast.from_pretrained(
            str(settings.summary_model_dir), local_files_only=True
        )
        summary_model = BartForConditionalGeneration.from_pretrained(
            str(settings.summary_model_dir), local_files_only=True
        )
        summary_model.to(device)
        summary_model.eval()
        SUMMARY_MODEL_READY = True
        logger.info("요약 모델 로드 완료 (KoBART): %s", settings.summary_model_dir)
    except Exception as exception:
        logger.exception("요약 모델 로드 실패")
else:
    logger.warning("요약 모델이 없습니다. 분석 요청은 503으로 응답합니다.")


def predict_ad(text: str) -> dict[str, Any]:
    if not AD_MODEL_READY or not ad_tokenizer or not ad_model or not torch or not F:
        return {"is_ad": False, "ad_prob": -1.0}

    inputs = ad_tokenizer(
        text,
        truncation=True,
        padding=True,
        max_length=settings.max_len,
        return_tensors="pt",
    ).to(device)

    with torch.no_grad():
        outputs = ad_model(**inputs)
        probs = F.softmax(outputs.logits, dim=-1)
        ad_prob = probs[0][1].item()
        label = 1 if ad_prob >= AD_HIGH_THRESHOLD else 0

    return {
        "is_ad": bool(label),
        "ad_prob": round(ad_prob, 4),
    }


def summarize(text: str) -> str:
    if not SUMMARY_MODEL_READY or not summary_tokenizer or not summary_model:
        fallback = text[:277].rstrip()
        return f"{fallback}..." if len(text) > 280 else text

    inputs = summary_tokenizer(
        text,
        return_tensors="pt",
        max_length=1024,
        truncation=True,
    ).to(device)

    with torch.no_grad():
        outputs = summary_model.generate(
            inputs["input_ids"],
            max_length=150,
            min_length=20,
            num_beams=4,
            do_sample=False,
            early_stopping=True,
            no_repeat_ngram_size=3,
            repetition_penalty=1.2,
        )

    summary = summary_tokenizer.decode(outputs[0], skip_special_tokens=True)
    return summary.strip()


def models_ready() -> bool:
    return AD_MODEL_READY and SUMMARY_MODEL_READY


WARM_UP_TEXT = "정부는 오늘 내년도 예산안을 발표했다. 경제 회복과 일자리 창출에 중점을 두었다고 밝혔다."


def warm_up() -> None:
    # The first CUDA call pays ~2 s of kernel setup; spend it at startup instead of on a user's request.
    if models_ready():
        analyze_article("", "", WARM_UP_TEXT)


def analyze_article(url: str, title: str, text: str) -> dict[str, Any]:
    # Placeholder output (ad_prob=-1, truncated text) must never be stored as a shared result.
    if not models_ready():
        raise AnalysisUnavailable("분석 모델이 준비되지 않았습니다. 잠시 후 다시 시도해 주세요.")
    if not _INFERENCE_SLOTS.acquire(timeout=INFERENCE_WAIT_SECONDS):
        raise AnalysisUnavailable("분석 요청이 많아 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.")
    try:
        text = text[:MAX_INPUT_CHARS]
        ad_result = predict_ad(text)
        summary_text = summarize(text)
    finally:
        _INFERENCE_SLOTS.release()
    return {
        "url": url,
        "title": title,
        "is_clickbait": ad_result["is_ad"],
        "ad_probability": round(ad_result["ad_prob"], 2),
        "summary": summary_text,
        "named_entities": [],
    }
