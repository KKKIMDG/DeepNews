# DeepNews FastAPI 백엔드

확장 프로그램이 보낸 기사 본문을 분석(광고성 판별 RoBERTa, 요약 KoBART)하고 Postgres에 저장하며,
로그인한 사용자에게 개인화 추천을 제공합니다. 서버는 기사 페이지를 직접 가져오지 않습니다.

## 실행

프로젝트 루트에서 실행합니다(`backend`는 패키지로 import됩니다).

```bash
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

`backend.main`을 import하면 `backend/sql/*.sql`이 파일 이름 순서로 실행되고(모두 `if not exists`),
분석 모델을 바로 로드합니다. 모델이 없으면 API는 뜨지만 분석 요청은 실패합니다. `/health`로 확인하세요.

## 환경 변수

루트 `.env`, `backend/.env` 순으로 읽습니다. 둘 중 하나가 필요합니다.

```env
DATABASE_URL=postgresql://user:password@host:5432/postgres?sslmode=require
```

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=secret
DB_SSLMODE=require
```

모델 경로: `model/ad_model/`, `model/kobart_summary_final_v2/` (git에 포함되지 않음).

## API (`/api/v1`)

| 경로 | 설명 |
| --- | --- |
| `POST /news/analyze` | 로그인 필요. `{url, title, content}`(브라우저에서 추출한 본문)를 받아 분석·저장하고 추천 기사를 함께 돌려줍니다. |
| `POST /news/{news_id}/report` | 분석 결과 신고 |
| `/auth/{signup,login,logout,me,password}` | 이메일/비밀번호 계정, Bearer 세션 토큰 |
| `/me/{profile,keywords,topics,settings,history,recommendations,export}` | 개인화 설정(관심 분야 포함)과 추천 |
| `GET /naver/news?query=&display=` | 로그인 필요. 네이버 뉴스 검색 API 결과를 저장 없이 그대로 전달 (`NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET` 필요) |
| `GET /collect/candidates?publisher=&limit=&offset=` | 로그인 필요. 본문이 없는 빅카인즈 후보 기사와 언론사별 개수(수집 도우미용) |
| `GET /health` | 모델 로드 상태 |

- URL은 `canonical_article_url`로 정규화합니다(네이버 기사 URL 형태를 하나로 통일).
- 이미 분석된 기사는 브라우저 본문이 저장된 본문과 달라도 덮어쓰지 않고 저장된 결과를
  `cached=True`로 돌려줍니다(예전에는 409를 냈습니다).
- 빅카인즈로 들어온 부분 본문(`content_partial`) 기사는 사용자가 분석하면 전체 본문으로 교체됩니다.
- 서버 측 크롤링 경로(`/news/crawl`, `/news/crawl/bulk`, `/crawl/article`, `/ai/analyze`)와
  네이버 자동 수집 배치(`run_ingestion`)는 삭제했습니다. 네이버는 robots.txt와 약관으로 자동 수집을 금지합니다.

## 배치

```bash
# 빅카인즈 엑셀 → 추천 후보 기사 (새 URL만 추가, 기존 행은 건드리지 않음)
python -m backend.run_bigkinds_import --file NewsResult_*.xlsx [--dry-run] [--limit N]
python -m backend.run_bigkinds_import --inbox airflow/inbox   # 폴더 안 엑셀 전부 처리 후 processed/·failed/로 이동

# 분석이 없거나 placeholder(ad_probability < 0)인 기사 재분석 (부분 본문 기사는 제외)
python -m backend.run_analysis --limit 20                     # 기본 mode=service
python -m backend.run_analysis --mode placeholder --limit 20  # dry run: 대상만 출력, DB에 쓰지 않음
```

`run_analysis`는 모델이 준비되지 않으면 실행을 거부합니다(종료 코드 2). 기사마다 따로 저장하므로
한 기사가 실패해도 나머지 결과는 남고, 실패 목록을 출력한 뒤 종료 코드 1을 돌려줍니다.
대상은 무작위 순서로 뽑아 계속 실패하는 기사가 큐 앞을 막지 않게 했습니다.
빅카인즈 inbox의 정기 실행은 [Airflow README](../airflow/README.md)를 참고하세요.

## 테스트

```bash
DATABASE_URL=postgresql://x@localhost/x python -m unittest discover -s tests -v
```

테스트는 DB에 연결하지 않고 모델도 로드하지 않습니다.
