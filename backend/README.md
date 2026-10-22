# DeepNews FastAPI Backend

This package is now the primary backend for DeepNews.

## Responsibilities

- Real-time article crawl and analysis API
- Direct Postgres persistence for `news`, `keyword`, `article_keyword`, `news_analysis`
- Batch ingestion and batch analysis runners

## Run API

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

## Environment

Provide one of the following:

```env
DATABASE_URL=postgresql://user:password@host:5432/postgres?sslmode=require
```

or

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=secret
DB_SSLMODE=require
```

## Run Batch Ingestion

```bash
python -m backend.run_ingestion --query AI --limit 10
```

## Run Batch Analysis

```bash
python -m backend.run_analysis --mode service --limit 20
```

## 브라우저 본문 입력

`POST /api/v1/news/analyze`는 기존 `{ "url": "..." }` 외에
`{ "url": "...", "title": "기사 제목", "content": "기사 본문(100자 이상)" }`도 받습니다.
본문을 전달하면 서버에서 URL을 다시 요청하지 않고 정제·키워드 추출 후 기존 분석/저장
흐름을 사용합니다. 출처는 URL 호스트이며 `extraData.content_origin`에 browser/server를
기록합니다. 기존 URL의 본문과 다르면 409로 거절하여 공유 결과가 조용히 덮어써지는 것을
막습니다. 모델 미설치 placeholder 동작은 기존과 같습니다.

## 수집 배치 검증

프로젝트 루트에서 실행합니다. 수집은 AI 추론을 실행하지 않으며 기사와 키워드만 저장합니다.
DB 스키마는 미리 준비되어 있어야 합니다(기존 API 실행 또는 스키마 초기화).

```bash
python -m backend.run_ingestion --query AI --limit 5
# DB를 변경하지 않고 수집 결과 파일만 확인
python -m backend.run_ingestion --query AI --limit 5 --skip-db-sync
python -m unittest discover -s tests -v
```

결과는 `backend/runtime/output`에 JSON/CSV로 저장됩니다. 실패 기사는 별도 JSON으로
기록하며, 전부 실패하면 명령이 실패합니다. limit은 1~1000이며 검색 결과가 부족하면
요청 개수보다 적을 수 있습니다. 반복된 검색 페이지는 중단하고 최대 검색 범위를 제한합니다.
같은 URL은 기존 DB 행을 갱신하므로 기사 행이 중복 생성되지 않습니다.
현재 배치는 수정된 본문에 대한 기존 분석 무효화를 수행하지 않습니다.
Airflow 수집 실행 방법은 [Airflow README](../airflow/README.md)를 참고하세요.
AI 분석 연결 및 브라우저/서버 추출 본문 차이 정책은 후속 작업입니다.

2026-10-22 검증: AI 검색 기사 5개 수집, Mecab 키워드 추출 및 DB 저장 성공.
동일 배치 재저장 전후 기사 ID와 개수를 확인합니다.
