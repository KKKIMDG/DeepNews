# GPU 서버의 사용자 영역 PostgreSQL 경로. setup_postgres.sh, start_db.sh, migrate_from_supabase.sh가 source한다.
# 모든 파일은 ~/deepnews 안에 있다(공용 서버라 시스템 패키지를 설치하지 않는다).
DEEPNEWS_HOME="${DEEPNEWS_HOME:-$HOME/deepnews}"
PG_MAJOR=17
PG_ROOT="$DEEPNEWS_HOME/postgres"
PG_BIN="$PG_ROOT/usr/lib/postgresql/$PG_MAJOR/bin"
PGDATA="$DEEPNEWS_HOME/pgdata"
PG_SOCKET_DIR="$DEEPNEWS_HOME/pg-run"
PG_LOG_FILE="$DEEPNEWS_HOME/logs/postgres.log"
PG_PASSWORD_FILE="$DEEPNEWS_HOME/pg-password"
PG_APP_USER=deepnews
PG_APP_DB=deepnews
PGPORT=5433
export PGDATA PGPORT
export PGHOST="$PG_SOCKET_DIR"
export LD_LIBRARY_PATH="$PG_ROOT/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
