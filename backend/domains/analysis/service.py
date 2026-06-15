from __future__ import annotations

from pathlib import Path
from typing import Any

from ...config import settings

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
print(f"사용 디바이스: {device}")

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
        print(f"광고 판별 모델 로드 완료: {settings.ad_model_dir}")
    except Exception as exception:
        print(f"광고 판별 모델 로드 실패: {exception}")
else:
    print("광고 판별 모델이 없어 placeholder 모드로 실행합니다.")

# 요약 모델 (KoBART) 로드
summary_tokenizer = None
summary_model = None
SUMMARY_MODEL_READY = False

KOBART_DIR = Path("./model/kobart_summary_final_v2")

if torch and PreTrainedTokenizerFast and BartForConditionalGeneration and KOBART_DIR.exists():
    try:
        summary_tokenizer = PreTrainedTokenizerFast.from_pretrained(
            str(KOBART_DIR), local_files_only=True
        )
        summary_model = BartForConditionalGeneration.from_pretrained(
            str(KOBART_DIR), local_files_only=True
        )
        summary_model.to(device)
        summary_model.eval()
        SUMMARY_MODEL_READY = True
        print(f"요약 모델 로드 완료 (KoBART): {KOBART_DIR}")
    except Exception as exception:
        print(f"요약 모델 로드 실패: {exception}")
else:
    print("요약 모델이 없어 placeholder 모드로 실행합니다.")


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
        label = 1 if ad_prob >= 0.5 else 0

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


def analyze_article(url: str, title: str, text: str) -> dict[str, Any]:
    ad_result = predict_ad(text)
    summary_text = summarize(text)
    return {
        "url": url,
        "title": title,
        "is_clickbait": ad_result["is_ad"],
        "ad_probability": round(ad_result["ad_prob"], 2),
        "summary": summary_text,
        "named_entities": [],
    }
