"""Evaluate the saved advertising classifier on its original 80/20 validation split.

Run from the project root: python ai/eval_ad.py
Requires the original JSONL with the same row order as during training.
This does not create an independent test set or retrain the model.
"""
import json
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix, classification_report

MODEL_DIR = "./model/ad_model"
DATA_FILE = "./ai/data/labeled_balanced.jsonl"
MAX_LEN = 512
BATCH_SIZE = 8
SEED = 42

def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = [json.loads(line) for line in f]
    texts = [d["text"] for d in data]
    labels = [d["label"] for d in data]
    _, val_texts, _, val_labels = train_test_split(
        texts, labels, test_size=0.2, random_state=SEED, stratify=labels)
    print(f"Validation samples: {len(val_texts)}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR, local_files_only=True)
    model.to(device).eval()

    class AdDataset(Dataset):
        def __init__(self, texts, labels):
            self.encodings = tokenizer(texts, truncation=True, padding=True,
                                       max_length=MAX_LEN, return_tensors="pt")
            self.labels = labels
        def __len__(self):
            return len(self.labels)
        def __getitem__(self, idx):
            item = {k: v[idx] for k, v in self.encodings.items()}
            item["labels"] = torch.tensor(self.labels[idx], dtype=torch.long)
            return item

    loader = DataLoader(AdDataset(val_texts, val_labels), batch_size=BATCH_SIZE, shuffle=False)
    preds, true_labels = [], []
    with torch.no_grad():
        for batch in loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(**batch)
            preds.extend(torch.argmax(outputs.logits, dim=-1).cpu().numpy())
            true_labels.extend(batch["labels"].cpu().numpy())
    acc = accuracy_score(true_labels, preds)
    precision, recall, f1, _ = precision_recall_fscore_support(
        true_labels, preds, average="binary", pos_label=1, zero_division=0)
    print(f"Accuracy: {acc:.4f}")
    print(f"Precision (ad): {precision:.4f}")
    print(f"Recall (ad): {recall:.4f}")
    print(f"F1 (ad): {f1:.4f}")
    print("Confusion matrix: rows=true, columns=predicted; labels=[normal, ad]")
    print(confusion_matrix(true_labels, preds, labels=[0, 1]))
    print(classification_report(true_labels, preds, labels=[0, 1],
                                target_names=["normal", "ad"], zero_division=0))

if __name__ == "__main__":
    main()
