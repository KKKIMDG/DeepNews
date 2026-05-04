# fastapi_server.py
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch.nn.functional as F
from fastapi import FastAPI
from pydantic import BaseModel

# ── 설정 ──────────────────────────────────────────
AD_MODEL_DIR = "./model_ad"
MAX_LEN      = 512

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"사용 디바이스: {device}")

# ── 모델 로드 (서버 시작 시 1회만) ─────────────────
ad_tokenizer = AutoTokenizer.from_pretrained(AD_MODEL_DIR)
ad_model     = AutoModelForSequenceClassification.from_pretrained(AD_MODEL_DIR)
ad_model.to(device)
ad_model.eval()

# ── FastAPI 앱 ─────────────────────────────────────
app = FastAPI()

class ArticleRequest(BaseModel):
    url:   str
    title: str
    text:  str

class AnalysisResponse(BaseModel):
    url:          str
    title:        str
    is_clickbait: bool      # is_ad → is_clickbait
    ad_probability: float   # ad_prob → ad_probability
    summary:      str
    named_entities: list    # entities → named_entities

# ── 광고 판별 함수 ─────────────────────────────────
def predict_ad(text: str) -> dict:
    inputs = ad_tokenizer(
        text,
        truncation=True,
        padding=True,
        max_length=MAX_LEN,
        return_tensors="pt"
    ).to(device)

    with torch.no_grad():
        outputs = ad_model(**inputs)
        probs   = F.softmax(outputs.logits, dim=-1)
        ad_prob = probs[0][1].item()
        label   = 1 if ad_prob >= 0.5 else 0

    return {
        "is_ad":   bool(label),
        "ad_prob": round(ad_prob, 4),
    }

# ── 엔드포인트 ─────────────────────────────────────
@app.post("/ai/analyze", response_model=AnalysisResponse)
def analyze(req: ArticleRequest):
    ad_result = predict_ad(req.text)

    return AnalysisResponse(
        url           = req.url,
        title         = req.title,
        is_clickbait  = ad_result["is_ad"],
        ad_probability = round(ad_result["ad_prob"], 2),
        summary        = "",
        named_entities = [],
    )

@app.get("/health")
def health():
    return {"status": "ok"}