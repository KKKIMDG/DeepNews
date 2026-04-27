# sample_bigkinds.py
import pandas as pd
import glob, os, random

input_dir   = "./bigkinds_csv/"   # xlsx 파일들 있는 폴더
output_file = "./output/sampled_for_labeling.csv"

# 키워드 분류
normal_keywords = [
    "경제활동인구", "지진", "태풍", "대사관", "합계출산율",
    "휴전", "집중호우", "유네스코", "인구구조", "IMF",
    "탄소중립", "무역수지", "기준금리", "공직선거법", "소비자물가지수"
]
ad_keywords = [
    "런칭", "보조제", "공동구매", "부트캠프", "홍보관",
    "오피스텔", "모발이식", "지방흡입", "한의원", "효능",
    "청약", "모델하우스", "실비보험", "라식", "치아교정",
    "임플란트", "탈모", "성형", "분양", "다이어트",
    "영양제", "피부과", "체험기", "건강기능식품", "시술"
]

# 파일당 샘플 수
NORMAL_PER_FILE = 50   # 15 × 50 = 750건
AD_PER_FILE     = 30   # 25 × 30 = 750건

results = []
missing = []

def load_and_sample(keyword, n_sample, ad_label):
    filepath = os.path.join(input_dir, f"{keyword}.xlsx")

    if not os.path.exists(filepath):
        missing.append(keyword)
        return None

    try:
        df = pd.read_excel(filepath, header=0)
    except Exception as e:
        print(f"읽기 오류: {keyword} → {e}")
        return None

    # 본문 없는 행 제거
    df = df.dropna(subset=["본문"])
    df = df[df["본문"].str.strip() != ""]

    # 분석제외 여부 컬럼 있으면 제외 처리
    if "분석제외 여부" in df.columns:
        df = df[df["분석제외 여부"].isna() | (df["분석제외 여부"] == "")]

    total = len(df)
    n = min(n_sample, total)   # 데이터가 샘플 수보다 적으면 전체 사용

    sampled = df.sample(n=n, random_state=42)

    sampled = sampled[["뉴스 식별자", "제목", "본문", "URL", "언론사", "일자"]].copy()
    sampled["keyword"]  = keyword
    sampled["ad_label"] = ad_label   # -1: 라벨링 전
    sampled["note"]     = ""

    print(f"[{'광고' if ad_label == -1 else '일반'}] {keyword}: 전체 {total}건 → {n}건 샘플링")
    return sampled

# 일반 키워드 처리
for kw in normal_keywords:
    df = load_and_sample(kw, NORMAL_PER_FILE, ad_label=-1)
    if df is not None:
        results.append(df)

# 광고 키워드 처리
for kw in ad_keywords:
    df = load_and_sample(kw, AD_PER_FILE, ad_label=-1)
    if df is not None:
        results.append(df)

# 합치기
final = pd.concat(results, ignore_index=True)

# 섞기 (키워드 순서 편향 방지)
final = final.sample(frac=1, random_state=42).reset_index(drop=True)

# 저장
os.makedirs("./output", exist_ok=True)
final.to_csv(output_file, index=False, encoding="utf-8-sig")

# 결과 요약
ad_count     = len([r for r in results if r["ad_label"].iloc[0] == -1 and r["keyword"].iloc[0] in ad_keywords])
normal_count = len(results) - ad_count

print(f"\n완료: 총 {len(final)}건")
print(f"일반 키워드 파일: {normal_count}개 / 광고 키워드 파일: {ad_count}개")
print(f"저장: {output_file}")

if missing:
    print(f"\n파일 없는 키워드: {missing}")