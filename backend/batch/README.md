# DeepNews Batch

This folder contains the Python batch pipeline that is meant to run separately from the Spring backend.

## Goals

- Crawl Naver news search results
- Normalize article text and keyword counts
- Bulk upsert into Supabase Postgres
- Orchestrate ingestion and analysis with Airflow

## Folder Layout

- `deepnews_batch/`: reusable Python modules
- `airflow/dags/`: Airflow DAG definitions
- `sql/`: schema SQL for Supabase
- `run_ingestion.py`: local/manual ingestion entrypoint
- `run_analysis.py`: local/manual analysis entrypoint

## Runtime Responsibilities

- Airflow handles schedule, retries, secrets, and task orchestration
- Supabase stores `news`, `keyword`, `article_keyword`, and `news_analysis`
- Spring backend keeps user-facing service logic
- AI analysis is optional for now and can run in placeholder mode until the API server is ready

## Local Setup

1. Create a Python virtual environment inside `backend/batch`
2. Install requirements

```powershell
pip install -r backend/batch/requirements.txt
```

3. Set environment variables for local testing

```powershell
$env:DATABASE_URL="postgresql://user:password@host:6543/postgres?sslmode=require"
```

4. Run ingestion locally

```powershell
python backend/batch/run_ingestion.py --query AI --limit 10 --output-dir backend/batch/runtime/output
```

5. Run placeholder analysis locally

```powershell
python backend/batch/run_analysis.py --mode placeholder --limit 20
```

## Airflow Secrets

- Postgres connection id: `supabase_postgres`
- Variables
  - `deepnews_query`
  - `deepnews_limit`
  - `deepnews_output_dir`
  - `deepnews_artifact_dir`
  - `deepnews_analysis_mode`
  - `deepnews_ai_service_url`

## DDL Ownership

The pipeline does not create tables at runtime.

Apply `sql/001_supabase_news_pipeline.sql` in Supabase SQL editor first, or move the same SQL into the migration tool the backend team decides to use later.
