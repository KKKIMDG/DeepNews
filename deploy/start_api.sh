#!/usr/bin/env bash
# GPU 서버에서 DeepNews API를 tmux 세션 deepnews-api로 (재)시작하고 /health가 응답할 때까지 기다린다.
# 사용: bash ~/deepnews/repo/deploy/start_api.sh
# GPU 지정(CUDA_VISIBLE_DEVICES)은 env.sh가 맡는다. 이 스크립트는 그 값을 바꾸지 않는다.
set -eo pipefail

DEEPNEWS_HOME="${DEEPNEWS_HOME:-$HOME/deepnews}"
SESSION="deepnews-api"
PORT=8010
HEALTH_URL="http://127.0.0.1:${PORT}/health"
LOG_FILE="$DEEPNEWS_HOME/logs/api.log"
WAIT_SECONDS=120

source "$DEEPNEWS_HOME/env.sh"
set -u
mkdir -p "$DEEPNEWS_HOME/logs"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "기존 세션 종료: $SESSION"
  tmux kill-session -t "$SESSION"
  for _ in $(seq 1 15); do
    curl -fsS -o /dev/null --max-time 2 "$HEALTH_URL" 2>/dev/null || break
    sleep 1
  done
fi

if curl -fsS -o /dev/null --max-time 2 "$HEALTH_URL" 2>/dev/null; then
  echo "포트 ${PORT}에서 다른 프로세스가 아직 응답합니다. 직접 확인하세요." >&2
  exit 1
fi

# 이미 떠 있는 tmux 서버는 이 셸의 환경변수를 물려주지 않으므로 세션 안에서 env.sh를 다시 읽는다.
tmux new-session -d -s "$SESSION" \
  "bash -c 'set -o pipefail; source \"$DEEPNEWS_HOME/env.sh\" && cd \"$DEEPNEWS_HOME/repo\" && \
\"$DEEPNEWS_HOME/.venv/bin/python\" -m uvicorn backend.main:app --host 127.0.0.1 --port $PORT 2>&1 | tee -a \"$LOG_FILE\"'"

echo "API 시작 대기 (최대 ${WAIT_SECONDS}초): $HEALTH_URL"
deadline=$((SECONDS + WAIT_SECONDS))
body=""
while (( SECONDS < deadline )); do
  # Wait for the warm-up too (형태소 분석기, 모델, 분야 대표어), so the first user request is not slow.
  if body=$(curl -fsS --max-time 5 "$HEALTH_URL" 2>/dev/null) && [[ "$body" == *'"warmed_up":true'* ]]; then
    echo "정상 기동: $body"
    exit 0
  fi
  if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "tmux 세션이 종료되었습니다. 로그 마지막 부분:" >&2
    tail -n 40 "$LOG_FILE" >&2
    exit 1
  fi
  sleep 2
done

if [[ -n "$body" ]]; then
  echo "기동했지만 ${WAIT_SECONDS}초 안에 예열이 끝나지 않았습니다: $body" >&2
  exit 0
fi
echo "${WAIT_SECONDS}초 안에 /health가 응답하지 않았습니다. 로그 마지막 부분:" >&2
tail -n 40 "$LOG_FILE" >&2
exit 1
