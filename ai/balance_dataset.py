# balance_dataset.py
import pandas as pd
import json, os

input_file  = "./output/labeled_train.jsonl"
output_file = "./output/labeled_balanced.jsonl"

data = []
with open(input_file, "r", encoding="utf-8") as f:
    for line in f:
        data.append(json.loads(line))

df = pd.DataFrame(data)

ad_df     = df[df["label"] == 1]
normal_df = df[df["label"] == 0].sample(n=len(ad_df), random_state=42)

balanced = pd.concat([ad_df, normal_df]).sample(frac=1, random_state=42).reset_index(drop=True)

with open(output_file, "w", encoding="utf-8") as f:
    for _, row in balanced.iterrows():
        f.write(json.dumps(row.to_dict(), ensure_ascii=False) + "\n")

print(f"완료: 총 {len(balanced)}건")
print(f"광고(1): {len(balanced[balanced['label']==1])}건")
print(f"일반(0): {len(balanced[balanced['label']==0])}건")