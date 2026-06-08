"""
DeepNews AI 추론 모듈
- 광고 판별 (klue/roberta-base 파인튜닝)
- 요약 (Gemma-2-9B + LoRA 파인튜닝)

사용 방법:
    from ai_inference import AIAnalyzer
    
    # 서버 시작 시 1회만 실행
    analyzer = AIAnalyzer()
    
    # 매 요청마다 호출
    result = analyzer.analyze(article_text)
"""

import torch
import torch.nn.functional as F
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    AutoModelForCausalLM,
)
from peft import PeftModel


class AIAnalyzer:
    """광고 판별 + 요약 통합 분석기"""
    
    AD_MODEL_DIR = "./ad_model"
    SUMMARY_BASE_MODEL = "google/gemma-2-9b-it"
    SUMMARY_ADAPTER_DIR = "./summary_model"
    
    # 추론 설정
    MAX_LEN = 512
    SUMMARY_MAX_TOKENS = 200
    AD_THRESHOLD = 0.5
    
    def __init__(self):
        """모델 로드 (서버 시작 시 1회만 실행)"""
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"사용 디바이스: {self.device}")
        
        self._load_ad_model()
        self._load_summary_model()
    
    def _load_ad_model(self):
        """광고 판별 모델 로드"""
        self.ad_tokenizer = AutoTokenizer.from_pretrained(
            self.AD_MODEL_DIR, local_files_only=True
        )
        self.ad_model = AutoModelForSequenceClassification.from_pretrained(
            self.AD_MODEL_DIR, local_files_only=True
        )
        self.ad_model.to(self.device)
        self.ad_model.eval()
        print("광고 판별 모델 로드 완료")
    
    def _load_summary_model(self):
        """요약 모델 로드 (Gemma + LoRA 어댑터)"""
        self.summary_tokenizer = AutoTokenizer.from_pretrained(self.SUMMARY_BASE_MODEL)
        self.summary_tokenizer.pad_token = self.summary_tokenizer.eos_token
        
        # 베이스 모델 (Gemma-2-9B)
        base_model = AutoModelForCausalLM.from_pretrained(
            self.SUMMARY_BASE_MODEL,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )
        
        # LoRA 어댑터 결합
        self.summary_model = PeftModel.from_pretrained(base_model, self.SUMMARY_ADAPTER_DIR)
        self.summary_model.eval()
        print("요약 모델 로드 완료")
    
    def predict_ad(self, text: str) -> dict:
        """
        광고 판별 추론
        
        Args:
            text: 기사 본문
        
        Returns:
            {"is_ad": bool, "ad_prob": float}
        """
        inputs = self.ad_tokenizer(
            text,
            truncation=True,
            padding=True,
            max_length=self.MAX_LEN,
            return_tensors="pt",
        ).to(self.device)
        
        with torch.no_grad():
            outputs = self.ad_model(**inputs)
            probs = F.softmax(outputs.logits, dim=-1)
            ad_prob = probs[0][1].item()
            is_ad = ad_prob >= self.AD_THRESHOLD
        
        return {
            "is_ad": bool(is_ad),
            "ad_prob": round(ad_prob, 4),
        }
    
    def summarize(self, text: str) -> str:
        """
        요약 추론
        
        Args:
            text: 기사 본문
        
        Returns:
            요약된 텍스트
        """
        # 학습 시 사용한 프롬프트 형식 (변경 금지)
        prompt = f"""다음 뉴스 기사를 3~5문장으로 요약해줘.

기사:
{text}

요약:
"""
        inputs = self.summary_tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self.MAX_LEN,
        ).to(self.device)
        
        with torch.no_grad():
            outputs = self.summary_model.generate(
                **inputs,
                max_new_tokens=self.SUMMARY_MAX_TOKENS,
                do_sample=False,
                pad_token_id=self.summary_tokenizer.eos_token_id,
                eos_token_id=self.summary_tokenizer.eos_token_id,
                repetition_penalty=1.1,
            )
        
        generated = self.summary_tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )
        
        if "\n요약" in generated:
            generated = generated.split("\n요약")[0]
        for stop in ["\n##", "\n#", "\n▲", "\n[", "\n="]:
            if stop in generated:
                generated = generated.split(stop)[0]
        
        return generated.strip()
    
    def analyze(self, text: str) -> dict:
        """
        기사 전체 분석 (백엔드가 호출하는 메인 함수)
        
        Args:
            text: 크롤링한 기사 본문
        
        Returns:
            {
                "is_clickbait": bool,
                "ad_probability": float,
                "summary": str
            }
        """
        ad_result = self.predict_ad(text)
        summary = self.summarize(text)
        
        return {
            "is_clickbait": ad_result["is_ad"],
            "ad_probability": ad_result["ad_prob"],
            "summary": summary,
        }
