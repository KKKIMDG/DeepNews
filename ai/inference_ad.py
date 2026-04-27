# inference_ad.py
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch.nn.functional as F

MODEL_DIR = "./model_ad"
MAX_LEN   = 512

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# 모델 로드
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
model     = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
model.to(device)
model.eval()

def predict_ad(text: str) -> dict:
    inputs = tokenizer(
        text,
        truncation=True,
        padding=True,
        max_length=MAX_LEN,
        return_tensors="pt"
    ).to(device)

    with torch.no_grad():
        outputs = model(**inputs)
        probs   = F.softmax(outputs.logits, dim=-1)
        ad_prob = probs[0][1].item()   # 광고 확률
        label   = 1 if ad_prob >= 0.5 else 0

    return {
        "is_ad":   bool(label),
        "ad_prob": round(ad_prob, 4),
    }

# ── 테스트 ─────────────────────────────────────────
if __name__ == "__main__":
    # 광고 예시
    ad_text = """
    강남 최고의 모발이식 전문 병원! 자연스러운 헤어라인 시술로
    탈모 걱정 끝! 지금 바로 상담 예약하세요.
    전화: 02-1234-5678 | 선착순 20명 무료 상담 이벤트 진행 중!
    """

    # 일반 뉴스 예시
    normal_text = """
    한국은행이 기준금리를 0.25%포인트 인상했다.
    이번 결정은 물가 안정을 위한 조치로, 금융통화위원회는
    만장일치로 이를 결정했다고 밝혔다.
    """

    print("=== 광고 예시 ===")
    result = predict_ad(ad_text)
    print(f"광고 여부: {result['is_ad']} | 광고 확률: {result['ad_prob']}")

    print("\n=== 일반 뉴스 예시 ===")
    result = predict_ad(normal_text)
    print(f"광고 여부: {result['is_ad']} | 광고 확률: {result['ad_prob']}")