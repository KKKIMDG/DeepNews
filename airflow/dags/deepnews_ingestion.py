"""Local scheduled ingestion. Model inference is intentionally not part of this DAG."""
from datetime import timedelta

import pendulum
from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

with DAG(
    dag_id="deepnews_news_ingestion",
    description="네이버 기사 수집 및 DB 저장 (모델 불필요)",
    schedule="*/30 * * * *",
    start_date=pendulum.datetime(2026, 10, 22, tz="Asia/Seoul"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=2)},
    tags=["deepnews", "ingestion"],
) as dag:
    collect_and_store = BashOperator(
        task_id="collect_and_store",
        bash_command=(
            '/opt/deepnews-runtime/venv/bin/python -m backend.run_ingestion '
            '--query "$DEEPNEWS_QUERY" --limit "$DEEPNEWS_LIMIT" '
            '--output-dir /opt/deepnews/output'
        ),
        cwd="/opt/deepnews",
        execution_timeout=timedelta(minutes=20),
        do_xcom_push=False,
    )
