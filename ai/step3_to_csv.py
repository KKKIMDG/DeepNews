import json, csv, os

input_file  = "./output/crawled_raw2.jsonl"
output_file = "./output/to_label2.csv"

data = []
with open(input_file, "r", encoding="utf-8") as f:
    for line in f:
        data.append(json.loads(line))

print(f"총 {len(data)}건 변환 시작")

with open(output_file, "w", encoding="utf-8-sig", newline="") as f:
    fieldnames = [
        "article_id", "title", "text",
        "publisher", "date", "url", "keyword",
        "ad_label",   # ← 여기에 0 또는 1 입력할 컬럼
        "note"        # ← 판단 이유 메모
    ]
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for row in data:
        writer.writerow({k: row.get(k, "") for k in fieldnames})

print(f"CSV 저장 완료: {output_file}")
print(f"이제 to_label.csv를 Google Sheets에 업로드해서 라벨링하면 됨")