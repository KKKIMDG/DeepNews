# sample_bigkinds.py
"""빅카인즈 키워드별 엑셀에서 라벨링 후보를 뽑는다.

주제 편향 주의: 광고 후보는 소비재·의료·부동산 키워드로, 일반 후보는 경성 뉴스 키워드로 모으므로
두 그룹의 주제(카테고리)가 크게 다르다. 그대로 학습하면 분류기가 광고성 대신 주제를 배운다.
이를 줄이기 위해 general_dir(키워드 없이 기간만 지정해 내려받은 빅카인즈 엑셀)이 있으면
광고 후보와 같은 상위 카테고리 비율로 일반 후보를 추가로 뽑는다(keyword="category_matched").
"""
import glob
import os

import pandas as pd

input_dir   = "./bigkinds_csv/"            # 키워드별 xlsx 파일들 있는 폴더
general_dir = "./bigkinds_csv/general/"    # 키워드 없이 받은 일반 기사 xlsx (선택)
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
SEED            = 42

COLUMNS = ["뉴스 식별자", "제목", "본문", "URL", "언론사", "일자", "통합 분류1"]

missing = []


def read_bigkinds(filepath):
    # dtype=str: 뉴스 식별자(예: 02100101.20261030123456789)가 float로 바뀌어 잘리는 것을 막는다.
    df = pd.read_excel(filepath, header=0, dtype=str)
    df = df.dropna(subset=["본문"])
    df = df[df["본문"].str.strip() != ""]
    if "분석제외 여부" in df.columns:
        df = df[df["분석제외 여부"].isna() | (df["분석제외 여부"].str.strip() == "")]
    if "통합 분류1" not in df.columns:
        df["통합 분류1"] = ""
    df["top_category"] = df["통합 분류1"].fillna("").str.split(">").str[0].str.strip()
    return df


def load_and_sample(keyword, n_sample, group):
    filepath = os.path.join(input_dir, f"{keyword}.xlsx")
    if not os.path.exists(filepath):
        missing.append(keyword)
        return None

    try:
        df = read_bigkinds(filepath)
    except Exception as e:
        print(f"읽기 오류: {keyword} → {e}")
        return None

    total = len(df)
    n = min(n_sample, total)   # 데이터가 샘플 수보다 적으면 전체 사용
    sampled = df.sample(n=n, random_state=SEED)[COLUMNS + ["top_category"]].copy()
    sampled["keyword"]  = keyword
    sampled["group"]    = group
    sampled["ad_label"] = -1   # -1: 라벨링 전
    sampled["note"]     = ""

    print(f"[{group}] {keyword}: 전체 {total}건 → {n}건 샘플링")
    return sampled


def sample_category_matched(ad_samples, exclude_urls):
    """광고 후보와 같은 상위 카테고리 분포로 일반 기사 후보를 뽑는다."""
    paths = glob.glob(os.path.join(general_dir, "*.xlsx"))
    if not paths:
        print(f"\n[경고] {general_dir}에 일반 기사 엑셀이 없어 카테고리 매칭 샘플을 만들지 않습니다. "
              "광고/일반 후보의 주제가 달라 분류기가 주제를 학습할 수 있습니다.")
        return None

    pool = pd.concat([read_bigkinds(path) for path in paths], ignore_index=True)
    pool = pool.drop_duplicates(subset=["URL"])
    pool = pool[~pool["URL"].isin(exclude_urls)]
    # 광고 키워드가 들어간 기사는 일반 기사 대조군에서 뺀다.
    pattern = "|".join(ad_keywords)
    pool = pool[~(pool["제목"].fillna("").str.contains(pattern) | pool["본문"].str.contains(pattern))]

    picked = []
    for category, count in ad_samples["top_category"].value_counts().items():
        candidates = pool[pool["top_category"] == category]
        n = min(count, len(candidates))
        if n < count:
            print(f"[category_matched] {category or '(분류 없음)'}: 필요 {count}건, 가능 {len(candidates)}건")
        if n:
            picked.append(candidates.sample(n=n, random_state=SEED))
    if not picked:
        return None

    matched = pd.concat(picked)[COLUMNS + ["top_category"]].copy()
    matched["keyword"]  = "category_matched"
    matched["group"]    = "카테고리매칭"
    matched["ad_label"] = -1
    matched["note"]     = ""
    print(f"[카테고리매칭] 일반 후보 {len(matched)}건 샘플링")
    return matched


normal_results = [df for kw in normal_keywords if (df := load_and_sample(kw, NORMAL_PER_FILE, "일반")) is not None]
ad_results     = [df for kw in ad_keywords if (df := load_and_sample(kw, AD_PER_FILE, "광고")) is not None]

results = normal_results + ad_results
if ad_results:
    ad_samples = pd.concat(ad_results, ignore_index=True)
    sampled_urls = set(pd.concat(results)["URL"])
    matched = sample_category_matched(ad_samples, sampled_urls)
    if matched is not None:
        results.append(matched)

final = pd.concat(results, ignore_index=True)
# 섞기 (키워드 순서 편향 방지)
final = final.sample(frac=1, random_state=SEED).reset_index(drop=True)

os.makedirs("./output", exist_ok=True)
final.to_csv(output_file, index=False, encoding="utf-8-sig")

print(f"\n완료: 총 {len(final)}건")
print(f"일반 키워드 파일: {len(normal_results)}개 / 광고 키워드 파일: {len(ad_results)}개")
print("그룹별 상위 카테고리 분포(편향 확인용):")
print(pd.crosstab(final["top_category"], final["group"]))
print(f"저장: {output_file}")

if missing:
    print(f"\n파일 없는 키워드: {missing}")
