#!/usr/bin/env bash
# GPU 서버의 ~/deepnews 안에 PostgreSQL 17을 root 없이 설치하고 앱 DB(deepnews)를 만든다. 여러 번 실행해도 안전하다.
# 사용: bash ~/deepnews/repo/deploy/setup_postgres.sh
# PGDG 저장소의 .deb를 내려받아 SHA256을 확인한 뒤 dpkg-deb -x로 풀기만 한다(apt·sudo를 쓰지 않는다).
set -euo pipefail
source "$(dirname "$0")/postgres_env.sh"

REPO="https://apt.postgresql.org/pub/repos/apt"
PACKAGES=(postgresql-$PG_MAJOR postgresql-client-$PG_MAJOR libpq5)
mkdir -p "$DEEPNEWS_HOME/logs" "$DEEPNEWS_HOME/cache/pg-debs"

if [[ ! -x "$PG_BIN/postgres" ]]; then
  index=$(curl -fsS --max-time 60 "$REPO/dists/jammy-pgdg/main/binary-amd64/Packages.gz" | gunzip)
  for package in "${PACKAGES[@]}"; do
    # 한 패키지의 여러 버전 중 가장 높은 버전: "버전 경로 sha256"
    entry=$(awk -v want="$package" '
      /^Package: / { name = $2 } /^Version: / { version = $2 } /^Filename: / { file = $2 } /^SHA256: / { sha = $2 }
      /^$/ { if (name == want) print version, file, sha; name = "" }
    ' <<<"$index" | sort -V | tail -n 1)
    read -r version file sha <<<"$entry"
    [[ -n "$file" ]] || { echo "패키지를 찾지 못했습니다: $package" >&2; exit 1; }
    deb="$DEEPNEWS_HOME/cache/pg-debs/$(basename "$file")"
    [[ -f "$deb" ]] || curl -fsS --max-time 300 -o "$deb" "$REPO/$file"
    echo "$sha  $deb" | sha256sum -c --quiet - || { rm -f "$deb"; echo "SHA256 불일치: $deb" >&2; exit 1; }
    dpkg-deb -x "$deb" "$PG_ROOT"
    echo "설치: $package $version"
  done
fi

missing=$(ldd "$PG_BIN/postgres" "$PG_BIN/psql" "$PG_BIN/pg_dump" | grep "not found" || true)
[[ -z "$missing" ]] || { echo "없는 라이브러리:"$'\n'"$missing" >&2; exit 1; }

if [[ ! -f "$PGDATA/PG_VERSION" ]]; then
  # 관리자 계정은 OS 사용자 이름(peer 인증), 앱 계정은 비밀번호 인증. 로케일은 OS에 의존하지 않는 builtin C.UTF-8.
  "$PG_BIN/initdb" -D "$PGDATA" -U "$USER" -E UTF8 --locale-provider=builtin --builtin-locale=C.UTF-8 \
    --auth-local=peer --auth-host=scram-sha-256 >/dev/null
  cat >>"$PGDATA/postgresql.conf" <<EOF

# --- DeepNews (deploy/setup_postgres.sh) ---
# 공용 서버: 외부 인터페이스에는 열지 않는다. 로컬 PC에서는 SSH 터널로 접속한다.
listen_addresses = '127.0.0.1'
port = $PGPORT
unix_socket_directories = '$PG_SOCKET_DIR'
unix_socket_permissions = 0700
max_connections = 50
shared_buffers = 512MB
jit = off
timezone = 'UTC'
log_timezone = 'UTC'
EOF
  cat >"$PGDATA/pg_hba.conf" <<EOF
# TYPE  DATABASE  USER  ADDRESS       METHOD
local   all       all                 peer
host    all       all   127.0.0.1/32  scram-sha-256
EOF
  echo "데이터 디렉터리 생성: $PGDATA"
fi

mkdir -p "$PG_SOCKET_DIR"
chmod 700 "$PG_SOCKET_DIR" "$PGDATA"
bash "$(dirname "$0")/start_db.sh"

if [[ ! -s "$PG_PASSWORD_FILE" ]]; then
  (umask 077; head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32 >"$PG_PASSWORD_FILE")
fi
psql_admin() { "$PG_BIN/psql" -X -q -v ON_ERROR_STOP=1 -d postgres "$@"; }
if [[ -z $(psql_admin -tAc "select 1 from pg_roles where rolname = '$PG_APP_USER'") ]]; then
  psql_admin -c "create role $PG_APP_USER login"
fi
# 비밀번호는 psql이 파일에서 읽는다. 명령줄 인자로 넘기면 공용 서버의 다른 사용자가 ps로 볼 수 있다.
psql_admin <<SQL
\\set pw \`cat '$PG_PASSWORD_FILE'\`
alter role $PG_APP_USER password :'pw';
-- Supabase(postgres 역할)와 같은 상한: 멈춘 쿼리가 커넥션을 계속 잡지 않게 한다.
alter role $PG_APP_USER set statement_timeout = '2min';
SQL
if [[ -z $(psql_admin -tAc "select 1 from pg_database where datname = '$PG_APP_DB'") ]]; then
  psql_admin -c "create database $PG_APP_DB owner $PG_APP_USER"
fi
echo "준비 완료. DATABASE_URL=postgresql://$PG_APP_USER:<$PG_PASSWORD_FILE>@127.0.0.1:$PGPORT/$PG_APP_DB?sslmode=disable"
