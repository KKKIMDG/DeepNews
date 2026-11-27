FROM apache/airflow:3.3.2-python3.11
USER root
RUN mkdir -p /opt/deepnews-runtime /opt/deepnews/inbox && chown airflow:0 /opt/deepnews-runtime /opt/deepnews/inbox
USER airflow
# Keep application dependencies separate from Airflow's dependency constraints.
# Only what `backend.run_bigkinds_import` needs; versions match requirements.txt.
RUN python -m venv /opt/deepnews-runtime/venv \
    && /opt/deepnews-runtime/venv/bin/pip install --no-cache-dir \
       pandas==2.3.3 openpyxl==3.1.5 psycopg2-binary==2.9.13 \
       python-dotenv==1.2.4 fastapi==0.162.0
