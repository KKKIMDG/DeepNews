#!/usr/bin/env bash
# GPU 서버의 사용자 영역 PostgreSQL을 켠다. 이미 켜져 있으면 아무것도 하지 않는다.
# 사용: bash ~/deepnews/repo/deploy/start_db.sh   (설치는 setup_postgres.sh)
set -euo pipefail
source "$(dirname "$0")/postgres_env.sh"

if [[ ! -f "$PGDATA/PG_VERSION" ]]; then
  echo "PostgreSQL 데이터 디렉터리가 없습니다. 먼저 deploy/setup_postgres.sh를 실행하세요." >&2
  exit 1
fi
if "$PG_BIN/pg_ctl" status >/dev/null 2>&1; then
  echo "PostgreSQL 실행 중 (127.0.0.1:$PGPORT)"
  exit 0
fi
mkdir -p "$PG_SOCKET_DIR" "$(dirname "$PG_LOG_FILE")"
chmod 700 "$PG_SOCKET_DIR"
# setsid: SSH 세션이 끝나도 같이 종료되지 않게 한다.
setsid "$PG_BIN/pg_ctl" start -w -t 60 -l "$PG_LOG_FILE" >/dev/null
echo "PostgreSQL 시작 (127.0.0.1:$PGPORT, 로그 $PG_LOG_FILE)"
