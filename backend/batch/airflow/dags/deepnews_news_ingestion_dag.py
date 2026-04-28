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

from deepnews_batch.pipeline import (
    collect_news_batch,
    load_batch_artifact,
    save_batch_artifact,
    save_batch_outputs,
)
from deepnews_batch.storage import sync_news_batch_to_supabase


def _postgres_dsn() -> str:
    hook = PostgresHook(postgres_conn_id="supabase_postgres")
    return hook.get_uri()


@dag(
    dag_id="deepnews_news_ingestion",
    schedule="0 */6 * * *",
    start_date=datetime(2026, 4, 29, tz="Asia/Seoul"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1},
    tags=["deepnews", "supabase", "news"],
)
def deepnews_news_ingestion():
    @task
    def collect_task() -> str:
        query = Variable.get("deepnews_query", default_var="AI")
        limit = int(Variable.get("deepnews_limit", default_var="50"))
        artifact_dir = Path(Variable.get("deepnews_artifact_dir", default_var="/tmp/deepnews_batch/artifacts"))
        batch = collect_news_batch(query=query, limit=limit)
        artifact_path = save_batch_artifact(batch, artifact_dir)
        return str(artifact_path)

    @task
    def save_outputs_task(artifact_path: str) -> dict[str, str | None]:
        output_dir = Path(Variable.get("deepnews_output_dir", default_var="/tmp/deepnews_batch/output"))
        batch = load_batch_artifact(Path(artifact_path))
        outputs = save_batch_outputs(batch, output_dir)
        return {
            "json_path": str(outputs["json_path"]),
            "csv_path": str(outputs["csv_path"]),
            "failure_path": str(outputs["failure_path"]) if outputs["failure_path"] else None,
        }

    @task
    def sync_supabase_task(artifact_path: str) -> str:
        batch = load_batch_artifact(Path(artifact_path))
        sync_news_batch_to_supabase(batch, database_url=_postgres_dsn())
        return f"Synced {len(batch.articles)} news rows"

    artifact_path = collect_task()
    save_outputs_task(artifact_path)
    sync_supabase_task(artifact_path)


deepnews_news_ingestion()
