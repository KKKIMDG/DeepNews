from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BATCH_ROOT = PROJECT_ROOT / "backend" / "batch"
if str(BATCH_ROOT) not in sys.path:
    sys.path.append(str(BATCH_ROOT))

from deepnews_batch.pipeline import (  # noqa: E402
    clean_article_text,
    extract_article,
    extract_token_counts,
    get_article_config,
    get_konlpy_analyzer,
    to_iso_datetime,
)

try:
    import torch
    import torch.nn.functional as F
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
except Exception:
    torch = None
    F = None
    AutoModelForSequenceClassification = None
    AutoTokenizer = None
    AutoModelForCausalLM = None
    PeftModel = None


AD_MODEL_DIR        = Path("/home/capstone/model_ad")
SUMMARY_BASE_MODEL  = "google/gemma-2-9b-it"
SUMMARY_ADAPTER_DIR = Path("/home/capstone/ai/adapter_summary/")
MAX_LEN            = 512
SUMMARY_MAX_TOKENS = 200
KEYWORD_LIMIT      = 8

KEYWORD_STOPWORDS = {
    "이번", "관련", "통해", "대한", "위한", "지난",
    "이날", "정도", "이후", "현재", "기준", "가장", "매우",
}

device = torch.device("cuda" if torch and torch.cuda.is_available() else "cpu") if torch else "cpu"
print(f"사용 디바이스: {device}")

# ── 광고 판별 모델 로드 ────────────────────────────
ad_tokenizer = None
ad_model = None
AD_MODEL_READY = False

if torch and AutoTokenizer and AutoModelForSequenceClassification and AD_MODEL_DIR.exists():
    try:
        ad_tokenizer = AutoTokenizer.from_pretrained(str(AD_MODEL_DIR), local_files_only=True)
        ad_model = AutoModelForSequenceClassification.from_pretrained(str(AD_MODEL_DIR), local_files_only=True)
        ad_model.to(device)
        ad_model.eval()
        AD_MODEL_READY = True
        print(f"광고 판별 모델 로드 완료: {AD_MODEL_DIR}")
    except Exception as exception:
        print(f"광고 판별 모델 로드 실패: {exception}")
else:
    print("광고 판별 모델이 없어 placeholder 모드로 실행합니다.")

# ── 요약 모델 로드 ────────────────────────────────
summary_tokenizer = None
summary_model = None
SUMMARY_MODEL_READY = False

if torch and AutoTokenizer and AutoModelForCausalLM and PeftModel and SUMMARY_ADAPTER_DIR.exists():
    try:
        summary_tokenizer = AutoTokenizer.from_pretrained(SUMMARY_BASE_MODEL)
        summary_tokenizer.pad_token = summary_tokenizer.eos_token

        base_model = AutoModelForCausalLM.from_pretrained(
            SUMMARY_BASE_MODEL,
            dtype=torch.bfloat16,
            device_map="cuda:0",
        )
        summary_model = PeftModel.from_pretrained(base_model, str(SUMMARY_ADAPTER_DIR))
        summary_model.eval()
        SUMMARY_MODEL_READY = True
        print(f"요약 모델 로드 완료: {SUMMARY_ADAPTER_DIR}")
    except Exception as exception:
        print(f"요약 모델 로드 실패: {exception}")
else:
    print("요약 모델이 없어 placeholder 모드로 실행합니다.")


app = FastAPI()


class ArticleRequest(BaseModel):
    url: str
    title: str
    text: str


class AnalysisResponse(BaseModel):
    url: str
    title: str
    is_clickbait: bool
    ad_probability: float
    summary: str
    named_entities: list[Any]


class CrawlResponse(BaseModel):
    title: str
    url: str
    content: str
    published_at: str
    token_counts: dict[str, int]
    keywords: list[str]


def predict_ad(text: str) -> dict[str, Any]:
    if not AD_MODEL_READY or not ad_tokenizer or not ad_model or not torch or not F:
        return {"is_ad": False, "ad_prob": 0.0}

    inputs = ad_tokenizer(
        text,
        truncation=True,
        padding=True,
        max_length=MAX_LEN,
        return_tensors="pt",
    ).to(device)

    with torch.no_grad():
        outputs = ad_model(**inputs)
        probs = F.softmax(outputs.logits, dim=-1)
        ad_prob = probs[0][1].item()
        label = 1 if ad_prob >= 0.5 else 0

    return {
        "is_ad":   bool(label),
        "ad_prob": round(ad_prob, 4),
    }


def summarize(text: str) -> str:
    if not SUMMARY_MODEL_READY or not summary_tokenizer or not summary_model:
        return ""

    prompt = f"""다음 뉴스 기사를 3~5문장으로 요약해줘.

기사:
{text}

요약:
"""
    inputs = summary_tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=MAX_LEN,
    ).to(device)

    with torch.no_grad():
        outputs = summary_model.generate(
            **inputs,
            max_new_tokens=SUMMARY_MAX_TOKENS,
            do_sample=False,
            pad_token_id=summary_tokenizer.eos_token_id,
            eos_token_id=summary_tokenizer.eos_token_id,
            repetition_penalty=1.1,
        )

    generated = summary_tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True,
    )

    # 후처리
    if "\n요약" in generated:
        generated = generated.split("\n요약")[0]
    for stop in ["\n##", "\n#", "\n▲", "\n[", "\n="]:
        if stop in generated:
            generated = generated.split(stop)[0]

    return generated.strip()


def limit_token_counts(token_counts: dict[str, int], limit: int = KEYWORD_LIMIT) -> dict[str, int]:
    filtered = {
        word: count
        for word, count in token_counts.items()
        if word not in KEYWORD_STOPWORDS and count > 0
    }
    return dict(sorted(filtered.items(), key=lambda item: (-item[1], item[0]))[:limit])


@app.post("/crawl/article", response_model=CrawlResponse)
def crawl_article(url: str = Query(..., description="크롤링할 기사 URL")):
    config = get_article_config()
    analyzer, analyzer_name = get_konlpy_analyzer()
    print(f"단건 크롤링 요청: {url} / analyzer={analyzer_name}")

    title, original_content, published_at = extract_article(url, config)
    if not original_content:
        raise ValueError("Empty article content")

    content = clean_article_text(original_content)
    token_counts = extract_token_counts(content, analyzer)
    limited_token_counts = limit_token_counts(token_counts)
    keywords = list(limited_token_counts.keys())

    if not content:
        raise ValueError("Cleaned article content is empty")

    return CrawlResponse(
        title=title,
        url=url,
        content=content,
        published_at=to_iso_datetime(published_at),
        token_counts=limited_token_counts,
        keywords=keywords,
    )


@app.post("/ai/analyze", response_model=AnalysisResponse)
def analyze(req: ArticleRequest):
    ad_result = predict_ad(req.text)
    summary_text = summarize(req.text)

    return AnalysisResponse(
        url            = req.url,
        title          = req.title,
        is_clickbait   = ad_result["is_ad"],
        ad_probability = round(ad_result["ad_prob"], 2),
        summary        = summary_text,
        named_entities = [],
    )


@app.get("/health")
def health():
    return {
        "status":              "ok",
        "ad_model_ready":      AD_MODEL_READY,
        "summary_model_ready": SUMMARY_MODEL_READY,
        "ad_model_path":       str(AD_MODEL_DIR),
        "summary_model_path":  str(SUMMARY_ADAPTER_DIR),
    }
