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
    build_summary,
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
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
except Exception:
    torch = None
    F = None
    AutoModelForSequenceClassification = None
    AutoTokenizer = None


AD_MODEL_DIR = Path(__file__).resolve().parent / "model_ad"
MAX_LEN = 512
KEYWORD_LIMIT = 8

KEYWORD_STOPWORDS = {
    "이번",
    "관련",
    "통해",
    "대한",
    "위한",
    "지난",
    "이날",
    "정도",
    "이후",
    "현재",
    "기준",
    "가장",
    "매우",
}

device = torch.device("cuda" if torch and torch.cuda.is_available() else "cpu") if torch else "cpu"
print(f"사용 디바이스: {device}")

ad_tokenizer = None
ad_model = None
MODEL_READY = False

if torch and AutoTokenizer and AutoModelForSequenceClassification and AD_MODEL_DIR.exists():
    try:
        ad_tokenizer = AutoTokenizer.from_pretrained(str(AD_MODEL_DIR), local_files_only=True)
        ad_model = AutoModelForSequenceClassification.from_pretrained(str(AD_MODEL_DIR), local_files_only=True)
        ad_model.to(device)
        ad_model.eval()
        MODEL_READY = True
        print(f"광고 판별 모델 로드 완료: {AD_MODEL_DIR}")
    except Exception as exception:
        print(f"광고 판별 모델 로드 실패, placeholder 모드로 실행합니다: {exception}")
else:
    print("광고 판별 모델이 없어 placeholder 모드로 실행합니다.")


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
    if not MODEL_READY or not ad_tokenizer or not ad_model or not torch or not F:
        return {
            "is_ad": False,
            "ad_prob": 0.0,
        }

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
        "is_ad": bool(label),
        "ad_prob": round(ad_prob, 4),
    }


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

    return AnalysisResponse(
        url=req.url,
        title=req.title,
        is_clickbait=ad_result["is_ad"],
        ad_probability=round(ad_result["ad_prob"], 2),
        summary=build_summary(req.text),
        named_entities=[],
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_ready": MODEL_READY,
        "model_path": str(AD_MODEL_DIR),
    }
