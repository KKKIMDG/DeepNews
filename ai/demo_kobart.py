"""Manual summary examples; this is not the 500-example ROUGE evaluation.
Run from project root: python ai/demo_kobart.py
"""
import time
import torch
from transformers import BartForConditionalGeneration, PreTrainedTokenizerFast

MODEL_DIR = "./model/kobart_summary_final_v2"
TEST_ARTICLES = [
    {"title": "삼성전자 노조 파업", "text": "삼성전자 노조가 14일 부분 파업을 강행했다. 사측이 임금 협상에 응하지 않자 노조는 결국 파업을 결정했다. 파업에는 약 1,000명이 참여했으며 생산 차질이 우려된다. 중앙노동위원회는 양측에 협상 재개를 요청한 상태다. 노조는 임금 5% 인상과 근로조건 개선을 요구하고 있으며, 사측은 경영 상황을 고려해 3% 인상안을 제시했다."},
    {"title": "실업급여 역대 최대", "text": "지난해 실업급여 지급액이 처음으로 17조원을 넘어서면서 고용보험기금 재정 부담이 커진 것으로 나타났다. 고용노동부에 따르면 지난해 실업급여 지급액은 17조 2,000억원으로 전년 대비 12% 증가했다. 고용보험기금은 5,920억원 적자를 기록했다. 정부는 실업급여 부정수급 단속을 강화하고 재정 안정화 방안을 마련할 계획이다."},
    {"title": "AI 기술 발전", "text": "인공지능 기술이 빠르게 발전하면서 다양한 산업 분야에서 활용되고 있다. 특히 의료, 금융, 교육 분야에서 AI 도입이 활발하다. 의료 분야에서는 AI가 영상 진단을 보조하고 있으며, 금융권에서는 사기 탐지에 활용되고 있다. 교육 분야에서는 개인 맞춤형 학습 시스템 개발에 사용된다. 전문가들은 AI 기술이 향후 10년 안에 거의 모든 산업을 변화시킬 것이라고 전망한다."},
]

def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = PreTrainedTokenizerFast.from_pretrained(MODEL_DIR, local_files_only=True)
    model = BartForConditionalGeneration.from_pretrained(MODEL_DIR, local_files_only=True).to(device).eval()
    for item in TEST_ARTICLES:
        inputs = tokenizer(item["text"], return_tensors="pt", max_length=1024, truncation=True).to(device)
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        start = time.perf_counter()
        with torch.no_grad():
            outputs = model.generate(inputs["input_ids"], max_length=150, min_length=20,
                num_beams=4, do_sample=False, early_stopping=True,
                no_repeat_ngram_size=3, repetition_penalty=1.2)
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        seconds = time.perf_counter() - start
        print(item["title"])
        print(tokenizer.decode(outputs[0], skip_special_tokens=True))
        print(f"Generation seconds (no warmup): {seconds:.3f}")

if __name__ == "__main__":
    main()
