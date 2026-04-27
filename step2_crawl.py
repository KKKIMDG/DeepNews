import pandas as pd
import json, time, os
from newspaper import Article
import random

input_csv   = "./output/sampled_for_labeling.csv"
output_file = "./output/crawled_raw2.jsonl"
error_file  = "./output/errors2.txt"

df = pd.read_csv(input_csv, encoding="utf-8-sig")

# ── 컬럼명 확인 후 맞게 수정 ──────────────────────
# step1 실행 시 출력된 컬럼명으로 아래를 수정할 것
# 예) "뉴스 식별자" 대신 "뉴스식별자" 일 수도 있음
COL_ID        = "뉴스 식별자"
COL_TITLE     = "제목"
COL_URL       = "URL"
COL_PUBLISHER = "언론사"
COL_DATE      = "일자"

# URL이 없는 행 제거
df = df.dropna(subset=[COL_URL])
df = df[df[COL_URL].str.startswith("http")]
print(f"크롤링 대상: {len(df)}건")

results = []
errors  = []

for idx, row in df.iterrows():
    url   = str(row[COL_URL]).strip()
    title = str(row.get(COL_TITLE, "")).strip()
    art_id = str(row.get(COL_ID, idx)).strip()

    try:
        article = Article(url, language="ko")
        article.download()
        article.parse()

        text = article.text.strip()

        # 본문이 너무 짧으면 크롤링 실패로 간주
        if len(text) < 150:
            errors.append(f"짧음({len(text)}자): {url}")
            continue

        result = {
            "article_id": art_id,
            "title":      title,
            "text":       text,
            "url":        url,
            "publisher":  str(row.get(COL_PUBLISHER, "")).strip(),
            "date":       str(row.get(COL_DATE, "")).strip(),
            "keyword":    str(row.get("keyword", "")).strip(),
            "ad_label":   -1,    # 라벨링 전 — 나중에 채움
            "note":       ""
        }
        results.append(result)

        # 진행 상황 출력
        if len(results) % 10 == 0:
            print(f"진행: {len(results)}건 완료 / 실패: {len(errors)}건")

    except Exception as e:
        errors.append(f"오류: {url} → {str(e)[:60]}")

    # 서버 과부하 방지 — 1초 대기
    time.sleep(random.uniform(1.5, 3.5))

# 결과 저장
os.makedirs("./output", exist_ok=True)
with open(output_file, "w", encoding="utf-8") as f:
    for r in results:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

# 오류 목록 저장
with open(error_file, "w", encoding="utf-8") as f:
    f.write("\n".join(errors))

print(f"\n완료: 성공 {len(results)}건 / 실패 {len(errors)}건")
print(f"결과 저장: {output_file}")