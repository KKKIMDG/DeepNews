"""DeepNews KoBART v2: reconstruct validation split and evaluate Korean ROUGE.

Run from the DeepNews project root:
    python eval_summary_fixed.py --check-only
    python eval_summary_fixed.py

Requirements: datasets (training used 4.8.5), numpy, rouge-score, torch,
transformers. scikit-learn is optional, for auditing the old evaluation split.
No training, database access, or model downloads are performed.
The original JSONL must have the same rows and row order as at training time.
"""

import argparse
import hashlib
import importlib.metadata
import json
import re
import statistics
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path


class KoreanWordTokenizer:
    """Unicode words separated at spaces/punctuation; not a morpheme tokenizer."""

    def tokenize(self, text):
        text = unicodedata.normalize("NFKC", str(text)).lower()
        return re.findall(r"[^\W_]+", text, flags=re.UNICODE)


def text_hash(text):
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def select_clean_validation(train_rows, validation_rows, size):
    """Remove exact normalized-text overlap with training, keep split order."""
    train_hashes = {text_hash(row["text"]) for row in train_rows}
    selected, skipped, seen = [], [], set()
    for row in validation_rows:
        digest = text_hash(row["text"])
        if digest in train_hashes or digest in seen:
            skipped.append(int(row["__deepnews_row_id"]))
            continue
        seen.add(digest)
        selected.append(row)
        if len(selected) == size:
            break
    if len(selected) != size:
        raise ValueError(f"중복을 제외한 검증 데이터가 부족합니다: {len(selected)}/{size}")
    return selected, skipped


def audit_old_split(total, train_indices, sample_size):
    try:
        from sklearn.model_selection import train_test_split
    except ImportError:
        return {"status": "skipped: scikit-learn not installed"}
    _, old_validation = train_test_split(
        list(range(total)), test_size=0.1, random_state=42
    )
    old_sample = old_validation[:sample_size]
    return {
        "old_sample_size": len(old_sample),
        "old_sample_rows_in_reconstructed_training": sum(
            index in train_indices for index in old_sample
        ),
        "note": "동일한 원본과 순서라는 조건에서의 행 인덱스 비교입니다.",
    }


def synchronize(torch, device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-file", type=Path, default=Path("ai/data/aihub_summary.jsonl"))
    parser.add_argument("--model-dir", type=Path, default=Path("model/kobart_summary_final_v2"))
    parser.add_argument("--sample-size", type=int, default=500)
    parser.add_argument("--expected-total", type=int, default=268535)
    parser.add_argument("--expected-datasets-version", default="4.8.5")
    parser.add_argument("--output-dir", type=Path, default=Path("eval_results"))
    parser.add_argument("--check-only", action="store_true", help="모델을 로드하지 않고 분할만 확인")
    args = parser.parse_args()
    if args.sample_size < 1:
        raise ValueError("sample-size는 1 이상이어야 합니다.")
    if not args.data_file.is_file():
        raise FileNotFoundError(f"데이터 파일을 찾지 못했습니다: {args.data_file.resolve()}")

    actual_version = package_version("datasets")
    if actual_version != args.expected_datasets_version:
        raise RuntimeError(
            f"datasets 버전: {actual_version or '미설치'} / 학습 환경에서 보고한 버전: "
            f"{args.expected_datasets_version}. 평가용 환경에서 동일 버전을 준비해 주세요.\n"
            f'설치 명령: python -m pip install "datasets=={args.expected_datasets_version}"\n'
            "보고한 학습 버전이 틀렸다면 실제 버전을 확인한 뒤 "
            "--expected-datasets-version 옵션으로 지정하세요."
        )
    from datasets import load_dataset

    print("학습 당시와 동일한 원본 파일과 행 순서가 필요합니다.", flush=True)
    raw = load_dataset("json", data_files=str(args.data_file))["train"]
    if len(raw) != args.expected_total:
        raise ValueError(
            f"원본 건수 불일치: 현재 {len(raw):,} / 예상 {args.expected_total:,}. "
            "학습 원본이 맞는지 먼저 확인해 주세요."
        )
    if "__deepnews_row_id" in raw.column_names:
        raise ValueError("원본에 예약된 행 ID 열이 있습니다.")
    for index, row in enumerate(raw):
        if any(not isinstance(row.get(key), str) or not row[key].strip()
               for key in ("text", "summary")):
            raise ValueError(f"원본 {index}행의 text 또는 summary가 비어 있거나 문자열이 아닙니다.")
    raw = raw.add_column("__deepnews_row_id", list(range(len(raw))))
    split = raw.train_test_split(test_size=0.1, seed=42, load_from_cache_file=False)
    train_ids = {int(index) for index in split["train"]["__deepnews_row_id"]}
    validation_ids = {int(index) for index in split["test"]["__deepnews_row_id"]}
    if train_ids & validation_ids or len(train_ids | validation_ids) != len(raw):
        raise RuntimeError("학습/검증 행 인덱스 분리 검사가 실패했습니다.")
    print(f"학습 {len(train_ids):,}건 / 검증 {len(validation_ids):,}건", flush=True)
    print("학습 기사와 본문이 같은 검증 항목을 확인하는 중...", flush=True)
    selected, skipped = select_clean_validation(split["train"], split["test"], args.sample_size)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output = args.output_dir / f"kobart_validation_{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    audit = {
        "status": "split_checked" if args.check_only else "evaluation_pending",
        "data_file": str(args.data_file.resolve()),
        "data_file_sha256": file_hash(args.data_file),
        "split_library": "datasets", "split_seed": 42, "validation_fraction": 0.1,
        "total": len(raw), "train_count": len(train_ids), "validation_count": len(validation_ids),
        "evaluation_type": "validation; not independent test",
        "sample_selection": "first N in reconstructed validation order, excluding normalized-text duplicates",
        "sample_size": len(selected), "skipped_duplicate_row_ids_before_sample_filled": skipped,
        "selected_rows": [{"row_id": int(row["__deepnews_row_id"]),
                           "text_sha256": text_hash(row["text"])} for row in selected],
        "old_split_audit": audit_old_split(len(raw), train_ids, args.sample_size),
        "rouge_tokenization": "NFKC + lowercase + Unicode words; spaces/punctuation separate tokens",
        "rouge_aggregation": "mean of per-example F1 for each ROUGE variant",
        "source_identity_limitation": (
            "학습 당시 원본 해시/분할 인덱스가 제공되지 않았으므로, 동일한 원본과 행 순서라는 "
            "조건에서 검증셋을 재구성합니다. 근접 중복이나 기반 모델의 사전학습 중복은 검사하지 않습니다."
        ),
        "versions": {name: package_version(name) for name in
                     ("datasets", "numpy", "transformers", "torch", "rouge-score", "scikit-learn")},
    }
    write_json(output / "audit.json", audit)
    print(json.dumps(audit["old_split_audit"], ensure_ascii=False, indent=2), flush=True)
    print(f"평가 대상 {len(selected)}건 / 검사 기록: {output.resolve()}", flush=True)
    if args.check_only:
        print("분할 검사 완료. 모델 학습이나 추론은 실행하지 않았습니다.")
        return

    import torch
    from rouge_score import rouge_scorer
    from transformers import BartForConditionalGeneration, PreTrainedTokenizerFast

    if not args.model_dir.is_dir():
        raise FileNotFoundError(f"모델 폴더를 찾지 못했습니다: {args.model_dir.resolve()}")
    scorer = rouge_scorer.RougeScorer(
        ["rouge1", "rouge2", "rougeL"], use_stemmer=False, tokenizer=KoreanWordTokenizer()
    )
    if scorer.score("정부가 대책을 발표했다", "정부가 대책을 발표했다")["rougeL"].fmeasure != 1.0:
        raise RuntimeError("한국어 토큰화 검사가 실패했습니다.")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"모델 로드 중: {args.model_dir} / {device}", flush=True)
    tokenizer = PreTrainedTokenizerFast.from_pretrained(str(args.model_dir), local_files_only=True)
    model = BartForConditionalGeneration.from_pretrained(str(args.model_dir), local_files_only=True)
    model.to(device).eval()
    generation = dict(max_length=150, min_length=20, num_beams=4, do_sample=False,
                      early_stopping=True, no_repeat_ngram_size=3, repetition_penalty=1.2)

    def encode(text):
        encoded = tokenizer(text, return_tensors="pt", max_length=1024, truncation=True)
        return {key: value.to(device) for key, value in encoded.items()
                if key in {"input_ids", "attention_mask"}}

    with torch.inference_mode():
        model.generate(**encode(selected[0]["text"]), **generation)
    synchronize(torch, device)
    scores_by_name = {name: [] for name in ("rouge1", "rouge2", "rougeL")}
    times = []
    with (output / "predictions.jsonl").open("w", encoding="utf-8") as handle:
        for index, row in enumerate(selected, 1):
            inputs = encode(row["text"])
            synchronize(torch, device)
            start = time.perf_counter()
            with torch.inference_mode():
                generated = model.generate(**inputs, **generation)
            synchronize(torch, device)
            seconds = time.perf_counter() - start
            prediction = tokenizer.decode(generated[0], skip_special_tokens=True).strip()
            scores = scorer.score(row["summary"], prediction)
            f1 = {name: float(score.fmeasure) for name, score in scores.items()}
            for name, value in f1.items():
                scores_by_name[name].append(value)
            times.append(seconds)
            handle.write(json.dumps({"row_id": int(row["__deepnews_row_id"]),
                                     "reference": row["summary"], "prediction": prediction,
                                     "rouge_f1": f1, "generation_seconds": seconds},
                                    ensure_ascii=False) + "\n")
            if index % 50 == 0 or index == len(selected):
                print(f"평가 진행: {index}/{len(selected)}", flush=True)
    metrics = {
        "sample_size": len(selected),
        "rouge_f1": {name: statistics.mean(values) for name, values in scores_by_name.items()},
        "mean_generation_seconds": statistics.mean(times),
        "timing_scope": "model.generate only, after warmup; CUDA synchronized; excludes tokenization/ROUGE/network",
        "device": str(device),
        "gpu_name": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        "model_dir": str(args.model_dir.resolve()), "generation_parameters": generation,
        "note": "한국어 보존 단어 단위 검증 ROUGE F1. 기존 기본 토크나이저 점수와 직접 비교하지 않습니다.",
    }
    write_json(output / "metrics.json", metrics)
    audit["status"] = "evaluation_complete"
    write_json(output / "audit.json", audit)
    print("\n=== KoBART v2 검증 결과 ===")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"결과 저장: {output.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\n실행 중단: {error}", file=sys.stderr)
        raise SystemExit(1)
