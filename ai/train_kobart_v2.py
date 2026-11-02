# Actual KoBART v2 training script supplied by the AI developer.
import torch
from transformers import (
    BartForConditionalGeneration,
    PreTrainedTokenizerFast,
    Trainer,
    TrainingArguments,
    DataCollatorForSeq2Seq,
)
from datasets import load_dataset

model_name = "gogamza/kobart-summarization"
tokenizer = PreTrainedTokenizerFast.from_pretrained(model_name)
model = BartForConditionalGeneration.from_pretrained(model_name)

dataset = load_dataset("json", data_files="/home/capstone/data/aihub_summary.jsonl")
dataset = dataset["train"].train_test_split(test_size=0.1, seed=42)
EOS = tokenizer.eos_token

def preprocess(examples):
    model_inputs = tokenizer(examples["text"], max_length=1024, truncation=True, padding=False)
    targets = [s + EOS for s in examples["summary"]]
    labels = tokenizer(targets, max_length=200, truncation=True,
                       padding=False, add_special_tokens=False)
    model_inputs["labels"] = labels["input_ids"]
    return model_inputs

tokenized_dataset = dataset.map(preprocess, batched=True,
                                remove_columns=dataset["train"].column_names)
data_collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model, padding=True)
training_args = TrainingArguments(
    output_dir="./kobart_summary_v2",
    num_train_epochs=3,
    per_device_train_batch_size=16,
    per_device_eval_batch_size=16,
    eval_strategy="epoch",
    save_strategy="epoch",
    learning_rate=3e-5,
    weight_decay=0.01,
    warmup_steps=500,
    logging_steps=100,
    fp16=True,
    save_total_limit=2,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    greater_is_better=False,
    report_to="none",
)
trainer = Trainer(
    model=model, args=training_args,
    train_dataset=tokenized_dataset["train"],
    eval_dataset=tokenized_dataset["test"],
    processing_class=tokenizer,
    data_collator=data_collator,
)
trainer.train()
trainer.save_model("./kobart_summary_final_v2")
tokenizer.save_pretrained("./kobart_summary_final_v2")
