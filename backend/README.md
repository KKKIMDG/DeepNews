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
