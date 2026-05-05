import json
import torch
import numpy as np
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from torch.optim import AdamW
from transformers import get_linear_schedule_with_warmup
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import mlflow
import os

# ── 설정 ──────────────────────────────────────────
MODEL_NAME   = "klue/roberta-base"
DATA_FILE    = "./output/labeled_balanced.jsonl"
OUTPUT_DIR   = "./model_ad"
MAX_LEN      = 512
BATCH_SIZE   = 8    
EPOCHS       = 5
LR           = 2e-5
SEED         = 42

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"사용 디바이스: {device}")

# ── 데이터 로드 ────────────────────────────────────
data = []
with open(DATA_FILE, "r", encoding="utf-8") as f:
    for line in f:
        data.append(json.loads(line))

texts  = [d["text"]  for d in data]
labels = [d["label"] for d in data]

train_texts, val_texts, train_labels, val_labels = train_test_split(
    texts, labels, test_size=0.2, random_state=SEED, stratify=labels
)

print(f"학습: {len(train_texts)}건 / 검증: {len(val_texts)}건")

# ── 토크나이저 ─────────────────────────────────────
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

class AdDataset(Dataset):
    def __init__(self, texts, labels):
        self.encodings = tokenizer(
            texts,
            truncation=True,
            padding=True,
            max_length=MAX_LEN,
            return_tensors="pt"
        )
        self.labels = labels

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: v[idx] for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx], dtype=torch.long)
        return item

train_dataset = AdDataset(train_texts, train_labels)
val_dataset   = AdDataset(val_texts,   val_labels)

train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
val_loader   = DataLoader(val_dataset,   batch_size=BATCH_SIZE, shuffle=False)

# ── 모델 ───────────────────────────────────────────
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=2)
model.to(device)

optimizer = AdamW(model.parameters(), lr=LR)
total_steps = len(train_loader) * EPOCHS
scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=total_steps // 10,
    num_training_steps=total_steps
)

# ── 학습 함수 ──────────────────────────────────────
def train_epoch(model, loader):
    model.train()
    total_loss = 0
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        outputs = model(**batch)
        loss = outputs.loss
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
            outputs = model(**batch)
            logits = outputs.logits
            preds.extend(torch.argmax(logits, dim=-1).cpu().numpy())
            true_labels.extend(batch["labels"].cpu().numpy())
    return preds, true_labels

# ── MLflow 실험 기록 ───────────────────────────────
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
    })

    best_f1 = 0

    for epoch in range(EPOCHS):
        print(f"\n에폭 {epoch+1}/{EPOCHS}")
        train_loss = train_epoch(model, train_loader)
        preds, true_labels = evaluate(model, val_loader)

        report = classification_report(
            true_labels, preds,
            target_names=["일반(0)", "광고(1)"],
            output_dict=True
        )

        f1_ad     = report["광고(1)"]["f1-score"]
        f1_macro  = report["macro avg"]["f1-score"]
        accuracy  = report["accuracy"]

        print(f"Loss: {train_loss:.4f} | Accuracy: {accuracy:.4f} | F1(광고): {f1_ad:.4f} | F1(macro): {f1_macro:.4f}")
        print(classification_report(true_labels, preds, target_names=["일반(0)", "광고(1)"]))

        mlflow.log_metrics({
            "train_loss": train_loss,
            "accuracy":   accuracy,
            "f1_ad":      f1_ad,
            "f1_macro":   f1_macro,
        }, step=epoch)

        # 최고 성능 모델 저장
        if f1_macro > best_f1:
            best_f1 = f1_macro
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            model.save_pretrained(OUTPUT_DIR)
            tokenizer.save_pretrained(OUTPUT_DIR)
            print(f"모델 저장: {OUTPUT_DIR} (F1: {best_f1:.4f})")

    mlflow.log_metric("best_f1_macro", best_f1)
    print(f"\n학습 완료. 최고 F1(macro): {best_f1:.4f}")
