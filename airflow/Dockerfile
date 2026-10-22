FROM apache/airflow:3.3.2-python3.11
USER root
RUN mkdir -p /opt/deepnews-runtime /opt/deepnews/output && chown airflow:0 /opt/deepnews-runtime /opt/deepnews/output
USER airflow
# Keep application dependencies separate from Airflow's dependency constraints.
RUN python -m venv /opt/deepnews-runtime/venv \
    && /opt/deepnews-runtime/venv/bin/pip install --no-cache-dir \
       requests==2.32.5 beautifulsoup4==4.14.3 pandas==2.3.3 \
       newspaper3k==0.2.8 lxml_html_clean==0.4.3 psycopg2-binary==2.9.11 \
       python-dotenv==1.2.1 SQLAlchemy==2.0.44 fastapi==0.121.0
