# labeled_to_jsonl.py
import pandas as pd
import json, os

input_file  = "./output/labeled.csv"
output_file = "./output/labeled_train.jsonl"

df = pd.read_csv(input_file, encoding="utf-8-sig")

# ad_label이 0 또는 1인 것만 사용 (미라벨링 -1 제외)
df = df[df["ad_label"].isin([0, 1])]

print(f"총 {len(df)}건 변환 시작")
print(f"광고(1): {len(df[df['ad_label']==1])}건")
print(f"일반(0): {len(df[df['ad_label']==0])}건")

os.makedirs("./output", exist_ok=True)

with open(output_file, "w", encoding="utf-8") as f:
    for _, row in df.iterrows():
        record = {
            "text":      str(row["text"]).strip(),
            "label":     int(row["ad_label"]),
            "title":     str(row.get("title", "")).strip(),
            "keyword":   str(row.get("keyword", "")).strip(),
        }
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

print(f"저장 완료: {output_file}")