from __future__ import annotations

from pathlib import Path
import sys

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.providers.postgres.hooks.postgres import PostgresHook
from pendulum import datetime

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.append(str(PACKAGE_ROOT))

from deepnews_batch.analysis import run_analysis_pipeline


def _postgres_dsn() -> str:
    hook = PostgresHook(postgres_conn_id="supabase_postgres")
    return hook.get_uri()


@dag(
    dag_id="deepnews_news_analysis",
    schedule="30 */6 * * *",
    start_date=datetime(2026, 4, 29, tz="Asia/Seoul"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1},
    tags=["deepnews", "supabase", "analysis"],
)
def deepnews_news_analysis():
    @task
    def analyze_task() -> str:
        mode = Variable.get("deepnews_analysis_mode", default_var="placeholder")
        limit = int(Variable.get("deepnews_analysis_limit", default_var="20"))
        ai_service_url = Variable.get("deepnews_ai_service_url", default_var="")
        count = run_analysis_pipeline(
            mode=mode,
            limit=limit,
            ai_service_url=ai_service_url or None,
            database_url=_postgres_dsn(),
        )
        return f"Analyzed {count} news rows"

    analyze_task()


deepnews_news_analysis()
