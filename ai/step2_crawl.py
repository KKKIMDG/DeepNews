"""라벨링 후보 기사 본문 수집 (연구용, 사람이 직접 실행).

- 호스트마다 robots.txt를 먼저 확인하고, 허용되지 않은 기사는 수집하지 않는다.
  (네이버 뉴스 등 robots.txt가 모든 봇을 막는 사이트는 자동으로 제외된다.)
- 프로젝트를 밝히는 User-Agent를 사용한다.
- 요청 사이에 1.5~3.5초를 쉰다.
"""
import json
import os
import random
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import pandas as pd
from newspaper import Article, Config

USER_AGENT = "DeepNewsResearchBot/1.0 (academic project; +https://github.com/KKKIMDG/DeepNews)"

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

_robots_cache: dict[str, RobotFileParser | None] = {}


def load_robots(origin):
    """robots.txt를 프로젝트 User-Agent로 받아 파싱한다. 없으면(4xx) 전체 허용, 401/403이면 전체 금지,
    그 밖의 오류로 확인할 수 없으면 None(수집하지 않음)."""
    parser = RobotFileParser(origin + "/robots.txt")
    request = urllib.request.Request(origin + "/robots.txt", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            parser.parse(response.read().decode("utf-8", errors="ignore").splitlines())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            parser.disallow_all = True
        elif 400 <= e.code < 500:
            parser.allow_all = True
        else:
            return None
    except Exception:
        return None
    return parser


def robots_allows(url):
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in _robots_cache:
        _robots_cache[origin] = load_robots(origin)
    parser = _robots_cache[origin]
    return parser is not None and parser.can_fetch(USER_AGENT, url)


article_config = Config()
article_config.browser_user_agent = USER_AGENT
article_config.request_timeout = 10

results = []
errors  = []

for idx, row in df.iterrows():
    url   = str(row[COL_URL]).strip()
    title = str(row.get(COL_TITLE, "")).strip()
    art_id = str(row.get(COL_ID, idx)).strip()

    if not robots_allows(url):
        errors.append(f"robots.txt 불허 또는 확인 불가: {url}")
        continue

    try:
        article = Article(url, language="ko", config=article_config)
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

    # 서버 과부하 방지 — 1.5~3.5초 대기
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