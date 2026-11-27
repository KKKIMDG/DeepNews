import pandas as pd
import glob, os

input_dir   = "./bigkinds_csv/"
output_file = "./output/merged.csv"

all_dfs = []

for filepath in glob.glob(os.path.join(input_dir, "*.xlsx")):
    try:
        # 빅카인즈 엑셀은 헤더가 첫 번째 행
        df = pd.read_excel(filepath, header=0)
        all_dfs.append(df)
        print(f"읽기 성공: {os.path.basename(filepath)} ({len(df)}건)")
    except Exception as e:
        print(f"오류: {filepath} → {e}")

if not all_dfs:
    print("파일을 찾지 못했습니다. 경로를 확인하세요.")
else:
    merged = pd.concat(all_dfs, ignore_index=True)

    # 중복 기사 제거 (같은 URL이면 같은 기사)
    before = len(merged)
    merged = merged.drop_duplicates(subset=["URL"], keep="first")
    after  = len(merged)
    print(f"\n중복 제거: {before}건 → {after}건")

    os.makedirs("./output", exist_ok=True)
    merged.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"저장 완료: {output_file}")
    print(f"컬럼 목록: {merged.columns.tolist()}")