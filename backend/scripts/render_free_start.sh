#!/usr/bin/env bash
set -euo pipefail

uv run celery -A app.workers.celery_app worker --loglevel=info --concurrency="${CELERY_CONCURRENCY:-1}" &
worker_pid=$!

uv run uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" &
api_pid=$!

shutdown() {
  kill -TERM "$api_pid" "$worker_pid" 2>/dev/null || true
  wait "$api_pid" 2>/dev/null || true
  wait "$worker_pid" 2>/dev/null || true
}

trap shutdown INT TERM

wait "$api_pid"
api_status=$?

kill -TERM "$worker_pid" 2>/dev/null || true
wait "$worker_pid" 2>/dev/null || true

exit "$api_status"
