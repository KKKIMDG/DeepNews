import json
import torch
import mlflow
import os
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW
from transformers import AutoTokenizer, AutoModelForCausalLM, get_linear_schedule_with_warmup
from peft import LoraConfig, get_peft_model, TaskType
from tqdm import tqdm

# ── 설정 ──────────────────────────────────────────
MODEL_NAME = "google/gemma-2-9b-it"
DATA_FILE  = "/home/capstone/data/aihub_summary.jsonl"
OUTPUT_DIR = "./adapter_summary"
MAX_LEN    = 512
BATCH_SIZE = 4
GRAD_ACCUM = 8
EPOCHS     = 3
LR         = 2e-4
SEED       = 42

torch.manual_seed(SEED)
device = torch.device("cuda:0")
print(f"사용 디바이스: {device}")

# ── 데이터 로드 ────────────────────────────────────
def load_data(file_path):
    data = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            data.append(json.loads(line))
    return data

raw_data = load_data(DATA_FILE)
print(f"총 데이터: {len(raw_data)}건")

# ── 토크나이저 ─────────────────────────────────────
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"

# ── 데이터셋 클래스 ────────────────────────────────
class SummaryDataset(Dataset):
    def __init__(self, data, tokenizer, max_len):
        self.data = data
        self.tokenizer = tokenizer
        self.max_len = max_len

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        example = self.data[idx]
        text = f"""다음 뉴스 기사를 3~5문장으로 요약해줘.

기사:
{example['text']}

요약:
{example['summary']}"""

        encoding = self.tokenizer(
            text,
            truncation=True,
            max_length=self.max_len,
            padding="max_length",
            return_tensors="pt",
        )
        input_ids = encoding["input_ids"].squeeze()
        attention_mask = encoding["attention_mask"].squeeze()
        labels = input_ids.clone()
        labels[labels == self.tokenizer.pad_token_id] = -100

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels,
        }

# ── 데이터 분할 ────────────────────────────────────
split = int(len(raw_data) * 0.9)
train_data = raw_data[:split]
val_data   = raw_data[split:]
print(f"학습: {len(train_data)}건 / 검증: {len(val_data)}건")

train_dataset = SummaryDataset(train_data, tokenizer, MAX_LEN)
val_dataset   = SummaryDataset(val_data,   tokenizer, MAX_LEN)

train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True,  num_workers=4)
val_loader   = DataLoader(val_dataset,   batch_size=BATCH_SIZE, shuffle=False, num_workers=4)

# ── 모델 로드 (GPU 0 하나만 사용) ──────────────────
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    dtype=torch.bfloat16,
    device_map="cuda:0",
)

# ── LoRA 설정 ──────────────────────────────────────
lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    bias="none",
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# ── 옵티마이저 ─────────────────────────────────────
optimizer = AdamW(model.parameters(), lr=LR)
total_steps = len(train_loader) * EPOCHS // GRAD_ACCUM
scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=total_steps // 10,
    num_training_steps=total_steps,
)

# ── MLflow ─────────────────────────────────────────
mlflow.set_experiment("summary_model")

with mlflow.start_run(run_name="v1_268535건"):
    mlflow.log_params({
        "model":      MODEL_NAME,
        "epochs":     EPOCHS,
        "batch_size": BATCH_SIZE,
        "grad_accum": GRAD_ACCUM,
        "lr":         LR,
        "lora_r":     16,
        "max_len":    MAX_LEN,
        "train_size": len(train_data),
    })

    best_val_loss = float("inf")

    for epoch in range(EPOCHS):
        model.train()
        total_loss = 0
        optimizer.zero_grad()

        for step, batch in enumerate(tqdm(train_loader, desc=f"에폭 {epoch+1}/{EPOCHS}")):
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(**batch)
            loss = outputs.loss / GRAD_ACCUM
            loss.backward()
            total_loss += outputs.loss.item()

            if (step + 1) % 10 == 0:
                print(f"스텝 {step+1} | loss: {outputs.loss.item():.4f}", flush=True)

            if (step + 1) % GRAD_ACCUM == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()

        avg_train_loss = total_loss / len(train_loader)

        model.eval()
        val_loss = 0
        with torch.no_grad():
            for batch in tqdm(val_loader, desc="검증 중"):
                batch = {k: v.to(device) for k, v in batch.items()}
                outputs = model(**batch)
                val_loss += outputs.loss.item()

        avg_val_loss = val_loss / len(val_loader)
        print(f"에폭 {epoch+1} | train_loss: {avg_train_loss:.4f} | val_loss: {avg_val_loss:.4f}", flush=True)

        mlflow.log_metrics({
            "train_loss": avg_train_loss,
            "val_loss":   avg_val_loss,
        }, step=epoch)

        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            model.save_pretrained(OUTPUT_DIR)
            tokenizer.save_pretrained(OUTPUT_DIR)
            print(f"모델 저장: {OUTPUT_DIR} (val_loss: {best_val_loss:.4f})", flush=True)

    print("학습 완료")
