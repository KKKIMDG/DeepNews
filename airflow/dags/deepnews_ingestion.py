"""Import BigKinds Excel exports dropped into the inbox folder.

No scraping and no model inference: each file goes through the same code path as
`python -m backend.run_bigkinds_import --file X`, then moves to inbox/processed/ or inbox/failed/.
"""
from datetime import timedelta

import pendulum
from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

with DAG(
    dag_id="deepnews_bigkinds_import",
    description="빅카인즈 엑셀(inbox) → 추천 후보 기사 DB 저장 (수집·모델 추론 없음)",
    schedule="0 * * * *",
    start_date=pendulum.datetime(2026, 10, 31, tz="Asia/Seoul"),
    catchup=False,
    max_active_runs=1,
    # A file with a format error is moved to failed/ and never retried; only DB outages leave
    # files in the inbox, and the next hourly run picks them up.
    default_args={"retries": 0},
    tags=["deepnews", "bigkinds"],
) as dag:
    import_inbox = BashOperator(
        task_id="import_bigkinds_inbox",
        bash_command="/opt/deepnews-runtime/venv/bin/python -m backend.run_bigkinds_import --inbox /opt/deepnews/inbox",
        cwd="/opt/deepnews",
        execution_timeout=timedelta(minutes=30),
        do_xcom_push=False,
    )
