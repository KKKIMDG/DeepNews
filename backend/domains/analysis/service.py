from __future__ import annotations

from typing import Any

from ...config import settings

try:
    import torch
    import torch.nn.functional as F
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoModelForSequenceClassification, AutoTokenizer
except Exception:
    torch = None
    F = None
    PeftModel = None
    AutoModelForCausalLM = None
    AutoModelForSequenceClassification = None
    AutoTokenizer = None


device = torch.device("cuda" if torch and torch.cuda.is_available() else "cpu") if torch else "cpu"
print(f"사용 디바이스: {device}")

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

summary_tokenizer = None
summary_model = None
SUMMARY_MODEL_READY = False

if torch and AutoTokenizer and AutoModelForCausalLM and PeftModel and settings.summary_adapter_dir.exists():
    try:
        summary_tokenizer = AutoTokenizer.from_pretrained(settings.summary_base_model)
        summary_tokenizer.pad_token = summary_tokenizer.eos_token

        base_model = AutoModelForCausalLM.from_pretrained(
            settings.summary_base_model,
            dtype=torch.bfloat16,
            device_map="cuda:0",
        )
        summary_model = PeftModel.from_pretrained(base_model, str(settings.summary_adapter_dir))
        summary_model.eval()
        SUMMARY_MODEL_READY = True
        print(f"요약 모델 로드 완료: {settings.summary_adapter_dir}")
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

    prompt = f"""다음 뉴스 기사를 3~5문장으로 요약해줘.

기사:
{text}

요약:
"""
    inputs = summary_tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=settings.max_len,
    ).to(device)

    with torch.no_grad():
        outputs = summary_model.generate(
            **inputs,
            max_new_tokens=settings.summary_max_tokens,
            do_sample=False,
            pad_token_id=summary_tokenizer.eos_token_id,
            eos_token_id=summary_tokenizer.eos_token_id,
            repetition_penalty=1.1,
        )

    generated = summary_tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[1] :],
        skip_special_tokens=True,
    )

    if "\n요약" in generated:
        generated = generated.split("\n요약")[0]
    for stop in ["\n##", "\n#", "\n▲", "\n[", "\n="]:
        if stop in generated:
            generated = generated.split(stop)[0]

    return generated.strip()


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
