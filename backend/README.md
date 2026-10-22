# DeepNews FastAPI Backend

This package is now the primary backend for DeepNews.

## Responsibilities

- Real-time article crawl and analysis API
- Direct Postgres persistence for `news`, `keyword`, `article_keyword`, `news_analysis`
- Batch ingestion and batch analysis runners

## Run API

```bash
uvicorn backend_fastapi.main:app --host 127.0.0.1 --port 8000 --reload
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
python -m backend_fastapi.run_ingestion --query AI --limit 10
```

## Run Batch Analysis

```bash
python -m backend_fastapi.run_analysis --mode service --limit 20
```

## 브라우저 본문 입력

`POST /api/v1/news/analyze`는 기존 `{ "url": "..." }` 외에
`{ "url": "...", "title": "기사 제목", "content": "기사 본문(100자 이상)" }`도 받습니다.
본문을 전달하면 서버에서 URL을 다시 요청하지 않고 정제·키워드 추출 후 기존 분석/저장
흐름을 사용합니다. 출처는 URL 호스트이며 `extraData.content_origin`에 browser/server를
기록합니다. 기존 URL의 본문과 다르면 409로 거절하여 공유 결과가 조용히 덮어써지는 것을
막습니다. 모델 미설치 placeholder 동작은 기존과 같습니다.
