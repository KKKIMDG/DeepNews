"""광고성 기사 분류기(klue/roberta-base) 학습.

데이터는 학습/검증/테스트(70/15/15, 라벨 층화)로 나눈다. 에폭 선택(최고 모델 저장)은 검증 세트로만 하고,
최종 성능은 학습·선택에 한 번도 쓰지 않은 테스트 세트로만 보고한다.

주의 — 주제 편향: sample_bigkinds.py는 광고 후보를 소비재·의료·부동산 키워드(분양, 탈모, 영양제 등)로,
일반 기사를 경성 뉴스 키워드(지진, 기준금리 등)로 모았다. 그대로 학습하면 모델이 "광고성"이 아니라
"주제"를 배울 수 있고, 같은 데이터에서 나눈 테스트 점수도 이 편향을 드러내지 못한다.
sample_bigkinds.py의 카테고리 매칭 일반 기사(keyword="category_matched")를 함께 라벨링해 쓰고,
가능하면 학습에 쓰지 않은 키워드·기간의 기사로 별도 평가한다.
"""
import json
import os

import mlflow
import torch
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

# ── 설정 ──────────────────────────────────────────
MODEL_NAME   = "klue/roberta-base"
DATA_FILE    = "./output/labeled_balanced.jsonl"
OUTPUT_DIR   = "./model_ad"
MAX_LEN      = 512
BATCH_SIZE   = 8
EPOCHS       = 5
LR           = 2e-5
SEED         = 42
VAL_RATIO    = 0.15
TEST_RATIO   = 0.15
TARGET_NAMES = ["일반(0)", "광고(1)"]

torch.manual_seed(SEED)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"사용 디바이스: {device}")

# ── 데이터 로드 및 분할 ─────────────────────────────
with open(DATA_FILE, "r", encoding="utf-8") as f:
    data = [json.loads(line) for line in f]

texts  = [d["text"]  for d in data]
labels = [d["label"] for d in data]

train_texts, holdout_texts, train_labels, holdout_labels = train_test_split(
    texts, labels, test_size=VAL_RATIO + TEST_RATIO, random_state=SEED, stratify=labels
)
val_texts, test_texts, val_labels, test_labels = train_test_split(
    holdout_texts, holdout_labels,
    test_size=TEST_RATIO / (VAL_RATIO + TEST_RATIO), random_state=SEED, stratify=holdout_labels
)
print(f"학습: {len(train_texts)}건 / 검증: {len(val_texts)}건 / 테스트: {len(test_texts)}건")

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)


class AdDataset(Dataset):
    def __init__(self, texts, labels):
        self.encodings = tokenizer(texts, truncation=True, padding=True, max_length=MAX_LEN, return_tensors="pt")
        self.labels = labels

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: v[idx] for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx], dtype=torch.long)
        return item


train_loader = DataLoader(AdDataset(train_texts, train_labels), batch_size=BATCH_SIZE, shuffle=True)
val_loader   = DataLoader(AdDataset(val_texts, val_labels), batch_size=BATCH_SIZE, shuffle=False)
test_loader  = DataLoader(AdDataset(test_texts, test_labels), batch_size=BATCH_SIZE, shuffle=False)

model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=2)
model.to(device)

optimizer = AdamW(model.parameters(), lr=LR)
total_steps = len(train_loader) * EPOCHS
scheduler = get_linear_schedule_with_warmup(
    optimizer, num_warmup_steps=total_steps // 10, num_training_steps=total_steps
)


def train_epoch(model, loader):
    model.train()
    total_loss = 0
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        loss = model(**batch).loss
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        scheduler.step()
        optimizer.zero_grad()
        total_loss += loss.item()
    return total_loss / len(loader)


def evaluate(model, loader):
    model.eval()
    preds, true_labels = [], []
    with torch.no_grad():
        for batch in loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            logits = model(**batch).logits
            preds.extend(torch.argmax(logits, dim=-1).cpu().numpy())
            true_labels.extend(batch["labels"].cpu().numpy())
    return classification_report(true_labels, preds, target_names=TARGET_NAMES, output_dict=True, zero_division=0)


def summary_metrics(report, prefix):
    return {
        f"{prefix}_accuracy": report["accuracy"],
        f"{prefix}_f1_ad":    report["광고(1)"]["f1-score"],
        f"{prefix}_f1_macro": report["macro avg"]["f1-score"],
    }


mlflow.set_experiment("ad_classifier")

with mlflow.start_run():
    mlflow.log_params({
        "model":      MODEL_NAME,
        "epochs":     EPOCHS,
        "batch_size": BATCH_SIZE,
        "lr":         LR,
        "max_len":    MAX_LEN,
        "train_size": len(train_texts),
        "val_size":   len(val_texts),
        "test_size":  len(test_texts),
    })

    best_f1, best_epoch = -1.0, -1
    for epoch in range(EPOCHS):
        print(f"\n에폭 {epoch + 1}/{EPOCHS}")
        train_loss = train_epoch(model, train_loader)
        val_metrics = summary_metrics(evaluate(model, val_loader), "val")
        print(f"Loss: {train_loss:.4f} | " + " | ".join(f"{k}: {v:.4f}" for k, v in val_metrics.items()))
        mlflow.log_metrics({"train_loss": train_loss, **val_metrics}, step=epoch)

        # 에폭 선택은 검증 세트로만 한다.
        if val_metrics["val_f1_macro"] > best_f1:
            best_f1, best_epoch = val_metrics["val_f1_macro"], epoch + 1
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            model.save_pretrained(OUTPUT_DIR)
            tokenizer.save_pretrained(OUTPUT_DIR)
            print(f"모델 저장: {OUTPUT_DIR} (val F1 macro: {best_f1:.4f})")

    mlflow.log_metrics({"best_val_f1_macro": best_f1, "best_epoch": best_epoch})

    # 선택된 모델을 테스트 세트로 한 번만 평가한다.
    best_model = AutoModelForSequenceClassification.from_pretrained(OUTPUT_DIR).to(device)
    test_report = evaluate(best_model, test_loader)
    test_metrics = summary_metrics(test_report, "test")
    mlflow.log_metrics(test_metrics)

    print(f"\n학습 완료. 선택 에폭: {best_epoch} (val F1 macro {best_f1:.4f})")
    print("테스트 세트 결과:")
    for name in TARGET_NAMES:
        row = test_report[name]
        print(f"  {name}: precision {row['precision']:.4f} | recall {row['recall']:.4f} | f1 {row['f1-score']:.4f}")
    print("  " + " | ".join(f"{k}: {v:.4f}" for k, v in test_metrics.items()))
