#!/usr/bin/env bash
# Supabase의 public 스키마 전체(테이블·데이터·시퀀스·인덱스)를 GPU 서버의 PostgreSQL(deepnews DB)로 복사한다.
# 사용: bash ~/deepnews/repo/deploy/migrate_from_supabase.sh
# - 원본 주소는 backend/.env의 SUPABASE_DATABASE_URL(없으면 DATABASE_URL)이다. Supabase 데이터는 바꾸지 않는다.
# - 대상 DB에 public 테이블이 이미 있으면 멈춘다(덮어쓰지 않는다). 다시 하려면 DB를 지우고 setup_postgres.sh부터 실행한다.
# - 덤프 파일은 ~/deepnews/backup/에 남는다(사용자 이메일·비밀번호 해시가 들어 있으므로 권한 600).
# 이전 중 쓰기가 섞이지 않게 API를 먼저 멈춘다: tmux kill-session -t deepnews-api
set -euo pipefail
source "$(dirname "$0")/postgres_env.sh"
REPO_DIR="$DEEPNEWS_HOME/repo"
DUMP="$DEEPNEWS_HOME/backup/supabase-public-$(date +%Y%m%d-%H%M%S).dump"
mkdir -p "$DEEPNEWS_HOME/backup"

existing=$("$PG_BIN/psql" -X -d "$PG_APP_DB" -tAc "select count(*) from pg_tables where schemaname = 'public'")
if [[ "$existing" != "0" ]]; then
  echo "대상 DB에 이미 public 테이블이 ${existing}개 있습니다. 덮어쓰지 않고 멈춥니다." >&2
  exit 1
fi

# 비밀번호를 명령줄 인자에 넣지 않도록 libpq 환경변수로 넘긴다(공용 서버의 ps에 보이지 않는다).
eval "$("$DEEPNEWS_HOME/.venv/bin/python" - "$REPO_DIR" <<'PY'
import os, shlex, sys
from urllib.parse import parse_qs, unquote, urlparse
from dotenv import dotenv_values
env = {**dotenv_values(os.path.join(sys.argv[1], ".env")), **dotenv_values(os.path.join(sys.argv[1], "backend", ".env"))}
url = urlparse(env.get("SUPABASE_DATABASE_URL") or env.get("DATABASE_URL") or "")
if "supabase" not in (url.hostname or ""):
    sys.exit("backend/.env에 Supabase 주소(SUPABASE_DATABASE_URL)가 없습니다.")
values = {"SB_HOST": url.hostname, "SB_PORT": str(url.port or 5432), "SB_USER": unquote(url.username or ""),
          "SB_PASSWORD": unquote(url.password or ""), "SB_DB": url.path.lstrip("/") or "postgres",
          "SB_SSLMODE": parse_qs(url.query).get("sslmode", ["require"])[0]}
print("\n".join(f"{key}={shlex.quote(value)}" for key, value in values.items()))
PY
)"

echo "덤프: $SB_HOST → $DUMP"
(umask 077
 PGPASSWORD="$SB_PASSWORD" PGSSLMODE="$SB_SSLMODE" "$PG_BIN/pg_dump" -h "$SB_HOST" -p "$SB_PORT" -U "$SB_USER" -d "$SB_DB" \
   --schema=public --format=custom --no-owner --no-privileges --file="$DUMP")

echo "복원: $PG_APP_DB (소유자 $PG_APP_USER)"
# 관리자(peer)로 접속해 SET ROLE deepnews로 만든다. 그래서 모든 객체의 소유자가 앱 계정이 된다.
# public 스키마는 새 DB에 이미 있으므로 그 생성문만 실패하지 않게 거른다.
"$PG_BIN/pg_restore" --list "$DUMP" | grep -v -E ' SCHEMA - public | COMMENT - SCHEMA public ' >"$DUMP.list"
"$PG_BIN/psql" -X -q -d "$PG_APP_DB" -c "alter schema public owner to $PG_APP_USER"
"$PG_BIN/pg_restore" -d "$PG_APP_DB" --role="$PG_APP_USER" --no-owner --no-privileges --exit-on-error \
  --use-list="$DUMP.list" "$DUMP"
rm -f "$DUMP.list"
"$PG_BIN/psql" -X -q -d "$PG_APP_DB" -c "analyze"

echo "행 수 비교 (Supabase / 로컬):"
tables=$("$PG_BIN/psql" -X -d "$PG_APP_DB" -tAc "select tablename from pg_tables where schemaname = 'public' order by 1")
mismatch=0
for table in $tables; do
  remote=$(PGPASSWORD="$SB_PASSWORD" PGSSLMODE="$SB_SSLMODE" "$PG_BIN/psql" -X -h "$SB_HOST" -p "$SB_PORT" -U "$SB_USER" -d "$SB_DB" \
    -tAc "select count(*) from public.\"$table\"")
  local_count=$("$PG_BIN/psql" -X -d "$PG_APP_DB" -tAc "select count(*) from public.\"$table\"")
  flag=""; [[ "$remote" == "$local_count" ]] || { flag="  <-- 다름"; mismatch=1; }
  printf '  %-26s %8s / %8s%s\n' "$table" "$remote" "$local_count" "$flag"
done
[[ $mismatch == 0 ]] || { echo "행 수가 다른 테이블이 있습니다." >&2; exit 1; }
echo "이전 완료. backend/.env의 DATABASE_URL을 로컬 DB로 바꾸고 deploy/start_api.sh로 재시작한다."
