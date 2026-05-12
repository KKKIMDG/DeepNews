# inference_summary.py
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

BASE_MODEL = "google/gemma-2-9b-it"
ADAPTER_DIR = "./adapter_summary"
MAX_NEW_TOKENS = 200

device = torch.device("cuda:0")

# 모델 로드
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
tokenizer.pad_token = tokenizer.eos_token

base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    dtype=torch.bfloat16,
    device_map="cuda:0",
)
model = PeftModel.from_pretrained(base_model, ADAPTER_DIR)
model.eval()

def summarize(text: str) -> str:
    prompt = f"""다음 뉴스 기사를 3~5문장으로 요약해줘.

기사:
{text}

요약:
"""
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512).to(device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
            repetition_penalty=1.1,
        )

    generated = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    # "요약:" 이후 반복 제거
    if "\n요약" in generated:
      generated = generated.split("\n요약")[0]

    # "##" 같은 마크다운 헤더나 추가 내용 제거
    for stop in ["\n##", "\n#", "\n▲", "\n[", "\n="]:
        if stop in generated:
            generated = generated.split(stop)[0]

    return generated.strip()

# 테스트
if __name__ == "__main__":
    test_article = """
    삼성전자가 미국 텍사스 테일러시에 건설 중인 신규 반도체 공장 가동을 2026년 하반기로 연기했다고 28일 밝혔다. 
    당초 2024년 가동 예정이었으나 반도체 시장 침체와 미국 정부의 보조금 지급 지연이 겹치면서 가동 시점이 미뤄지게 됐다.
    삼성전자는 텍사스 공장에 총 250억 달러를 투자해 4나노미터 첨단 공정 반도체를 생산할 계획이었다. 
    이 공장은 미국 내 최대 규모의 외국인 투자 프로젝트 중 하나로, 완공 시 약 2,000개의 일자리를 창출할 것으로 기대된다.
    업계 관계자는 "글로벌 반도체 수요 둔화와 더불어 미국 칩스법에 따른 보조금 협상이 지연되면서 삼성도 투자 속도를 조절하는 것"이라며 
    "내년 상반기 메모리 반도체 시장 회복 시점과 맞춰 공장 가동 계획을 재조정한 것으로 보인다"고 분석했다.
    한편 삼성전자는 한국 평택 캠퍼스에도 신규 라인 증설을 진행 중이며, 
    파운드리 시장에서 TSMC와의 격차를 줄이기 위한 투자를 지속할 방침이라고 밝혔다.
    """

    summary = summarize(test_article)
    print(f"요약 결과:\n{summary}")
