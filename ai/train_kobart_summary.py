"""KoBART 요약 모델 파인튜닝 (백엔드가 쓰는 model/kobart_summary_final_v2 재현용).

사용:
    python ai/train_kobart_summary.py --data ./output/summary.jsonl --output-dir ./kobart_summary_v3

데이터: JSONL, 한 줄에 {"text": 기사 본문, "summary": 정답 요약}. (삭제된 Gemma 학습 스크립트가 쓰던
aihub_summary.jsonl과 같은 형식이다. ai/에는 요약 데이터 전처리 스크립트가 없다.) 빈 행은 건너뛴다.
데이터를 학습/검증/테스트로 나누고, 체크포인트 선택은 검증 eval_loss로만, ROUGE는 마지막에
테스트 세트에서 한 번만 계산한다.

설정 출처
- model/kobart_summary_final_v2/training_args.bin(우리가 저장한 TrainingArguments)에서 복원한 값:
  learning_rate=3e-5, num_train_epochs=3, per_device_train/eval_batch_size=16,
  gradient_accumulation_steps=1, weight_decay=0.01, warmup_steps=500, lr_scheduler=linear,
  optim=adamw_torch, max_grad_norm=1.0, label_smoothing=0.0, fp16=True, seed=42,
  eval/save_strategy=epoch, save_total_limit=2, load_best_model_at_end=True,
  metric_for_best_model=eval_loss(greater_is_better=False), logging_steps=100.
  (원래 객체는 Seq2Seq가 아닌 일반 TrainingArguments였다. 즉 학습 중 생성 기반 평가는 하지 않았다.)
- config.json에서 확인한 값: BartForConditionalGeneration, d_model 768, 인코더/디코더 6층, vocab 30000,
  pad=3, bos=0, eos=1, decoder_start=2, author Heewon Jeon → 베이스는 gogamza/kobart-base-v2로 추정.
- 가정(파일에 기록이 없음):
  * 베이스 모델 이름 gogamza/kobart-base-v2
  * 데이터 분할 80/10/10(seed 42)
  * 입력 최대 1024토큰(max_position_embeddings 1026, 백엔드 추론도 1024에서 자름), 정답 최대 128토큰
  * 입력은 <s> 본문 </s>, 정답은 요약 </s> (KoBART 토크나이저는 특수 토큰을 자동으로 붙이지 않는다)
  * 테스트 생성 파라미터는 백엔드 summarize()와 같게: num_beams=4, max_length=150, min_length=20,
    no_repeat_ngram_size=3, repetition_penalty=1.2
  * ROUGE는 공백 단위 토큰의 ROUGE-1/2/L F1로 직접 계산한다(rouge_score 패키지는 한글을 지운다).
    형태소 단위로 계산한 다른 논문 수치와 직접 비교할 수 없다.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import torch
from torch.utils.data import Dataset
from transformers import (
    BartForConditionalGeneration,
    DataCollatorForSeq2Seq,
    PreTrainedTokenizerFast,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
)

BASE_MODEL = "gogamza/kobart-base-v2"
MAX_SOURCE_TOKENS = 1024
MAX_TARGET_TOKENS = 128
GENERATION_KWARGS = {
    "max_length": 150,
    "min_length": 20,
    "num_beams": 4,
    "do_sample": False,
    "early_stopping": True,
    "no_repeat_ngram_size": 3,
    "repetition_penalty": 1.2,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune KoBART for Korean news summarization")
    parser.add_argument("--data", required=True, help="JSONL with {text, summary} per line")
    parser.add_argument("--output-dir", default="./kobart_summary_v3")
    parser.add_argument("--base-model", default=BASE_MODEL)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--epochs", type=float, default=3)
    parser.add_argument("--learning-rate", type=float, default=3e-5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-test-samples", type=int, default=0, help="Limit ROUGE evaluation (0 = all)")
    return parser.parse_args()


def load_jsonl(path: str) -> list[dict[str, str]]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            text, summary = str(item.get("text", "")).strip(), str(item.get("summary", "")).strip()
            if text and summary:
                records.append({"text": text, "summary": summary})
    return records


def split(records: list, val_ratio: float, test_ratio: float, seed: int) -> tuple[list, list, list]:
    shuffled = records[:]
    random.Random(seed).shuffle(shuffled)
    n_test = int(len(shuffled) * test_ratio)
    n_val = int(len(shuffled) * val_ratio)
    return shuffled[n_test + n_val:], shuffled[n_test:n_test + n_val], shuffled[:n_test]


class SummaryDataset(Dataset):
    def __init__(self, records, tokenizer):
        self.records = records
        self.tokenizer = tokenizer

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        record = self.records[idx]
        tok = self.tokenizer
        source = tok(record["text"], add_special_tokens=False)["input_ids"][: MAX_SOURCE_TOKENS - 2]
        target = tok(record["summary"], add_special_tokens=False)["input_ids"][: MAX_TARGET_TOKENS - 1]
        input_ids = [tok.bos_token_id] + source + [tok.eos_token_id]
        return {
            "input_ids": input_ids,
            "attention_mask": [1] * len(input_ids),
            "labels": target + [tok.eos_token_id],
        }


def ngrams(tokens: list[str], n: int) -> dict[tuple, int]:
    counts: dict[tuple, int] = {}
    for i in range(len(tokens) - n + 1):
        gram = tuple(tokens[i:i + n])
        counts[gram] = counts.get(gram, 0) + 1
    return counts


def f1(overlap: int, predicted: int, reference: int) -> float:
    if not overlap or not predicted or not reference:
        return 0.0
    precision, recall = overlap / predicted, overlap / reference
    return 2 * precision * recall / (precision + recall)


def lcs_length(a: list[str], b: list[str]) -> int:
    previous = [0] * (len(b) + 1)
    for token in a:
        current = [0]
        for j, other in enumerate(b):
            current.append(previous[j] + 1 if token == other else max(previous[j + 1], current[j]))
        previous = current
    return previous[-1]


def rouge_scores(predictions: list[str], references: list[str]) -> dict[str, float]:
    totals = {"rouge1": 0.0, "rouge2": 0.0, "rougeL": 0.0}
    for prediction, reference in zip(predictions, references):
        pred, ref = prediction.split(), reference.split()
        for n, key in ((1, "rouge1"), (2, "rouge2")):
            p, r = ngrams(pred, n), ngrams(ref, n)
            overlap = sum(min(count, r.get(gram, 0)) for gram, count in p.items())
            totals[key] += f1(overlap, sum(p.values()), sum(r.values()))
        totals["rougeL"] += f1(lcs_length(pred, ref), len(pred), len(ref))
    return {key: value / max(len(predictions), 1) for key, value in totals.items()}


def generate_summaries(model, tokenizer, texts: list[str], batch_size: int) -> list[str]:
    model.eval()
    summaries = []
    for start in range(0, len(texts), batch_size):
        batch = tokenizer(
            texts[start:start + batch_size], return_tensors="pt", max_length=MAX_SOURCE_TOKENS,
            truncation=True, padding=True,
        ).to(model.device)
        with torch.no_grad():
            outputs = model.generate(
                input_ids=batch["input_ids"], attention_mask=batch["attention_mask"], **GENERATION_KWARGS
            )
        summaries.extend(tokenizer.batch_decode(outputs, skip_special_tokens=True))
    return [summary.strip() for summary in summaries]


def main() -> None:
    args = parse_args()
    records = load_jsonl(args.data)
    train_records, val_records, test_records = split(records, args.val_ratio, args.test_ratio, args.seed)
    print(f"학습: {len(train_records)}건 / 검증: {len(val_records)}건 / 테스트: {len(test_records)}건")
    if not (train_records and val_records and test_records):
        raise SystemExit("데이터가 부족해 학습/검증/테스트로 나눌 수 없습니다.")

    tokenizer = PreTrainedTokenizerFast.from_pretrained(args.base_model)
    model = BartForConditionalGeneration.from_pretrained(args.base_model)
    use_cuda = torch.cuda.is_available()

    training_args = Seq2SeqTrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        learning_rate=args.learning_rate,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=1,
        weight_decay=0.01,
        warmup_steps=500,
        lr_scheduler_type="linear",
        optim="adamw_torch",
        max_grad_norm=1.0,
        fp16=use_cuda,
        seed=args.seed,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        logging_steps=100,
        predict_with_generate=False,
        report_to=[],
    )
    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=SummaryDataset(train_records, tokenizer),
        eval_dataset=SummaryDataset(val_records, tokenizer),
        data_collator=DataCollatorForSeq2Seq(tokenizer, model=model, label_pad_token_id=-100),
        processing_class=tokenizer,
    )
    trainer.train()

    final_dir = Path(args.output_dir) / "final"
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))
    print(f"검증 eval_loss 기준 최고 모델 저장: {final_dir}")

    # 학습·체크포인트 선택에 쓰지 않은 테스트 세트에서만 ROUGE를 계산한다.
    evaluated = test_records[: args.max_test_samples] if args.max_test_samples else test_records
    predictions = generate_summaries(trainer.model, tokenizer, [r["text"] for r in evaluated], args.batch_size)
    scores = rouge_scores(predictions, [r["summary"] for r in evaluated])
    scores["test_size"] = len(evaluated)
    print("테스트 ROUGE F1 (공백 토큰): " + " | ".join(f"{k}: {v:.4f}" for k, v in scores.items() if k != "test_size"))
    (final_dir / "test_metrics.json").write_text(json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(final_dir / "test_predictions.jsonl", "w", encoding="utf-8") as f:
        for record, prediction in zip(evaluated, predictions):
            f.write(json.dumps({**record, "prediction": prediction}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
