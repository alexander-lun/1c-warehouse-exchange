#!/usr/bin/env bash
# Интеграционные тесты: поднимает заглушку маркетплейса и гоняет pytest против опубликованной базы.
#   API_URL=... API_KEY=... scripts/test.sh [аргументы pytest]
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON=${PYTHON:-python3}
MOCK_PORT=${MOCK_PORT:-8090}
export MOCK_URL=http://127.0.0.1:$MOCK_PORT

"$PYTHON" -m uvicorn marketplace:app --app-dir mock --port "$MOCK_PORT" --log-level warning &
MOCK_PID=$!
trap 'kill $MOCK_PID 2>/dev/null' EXIT

for _ in {1..20}; do
  curl -sf -o /dev/null -X POST "$MOCK_URL/_test/reset" && break
  sleep 0.5
done

"$PYTHON" -m pytest tests "$@"
