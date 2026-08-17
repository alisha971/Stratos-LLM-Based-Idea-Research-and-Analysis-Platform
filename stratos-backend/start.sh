#!/usr/bin/env bash
# Fast-ship single-container entrypoint (fast-ship task 3.1).
# Runs BOTH the API and the Celery worker in one container so they share the
# local filesystem (local-disk PDFs work) and one Railway service suffices.
# Premium B7.2/B6 splits these into separate services later.
set -euo pipefail

# API server (background)
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" &

# Celery worker (background). On Linux the default pool is fine; concurrency=2
# keeps a small instance within memory limits.
celery -A app.workers.celery_app worker --loglevel=info --concurrency=2 &

# Exit (and let the platform restart) if EITHER process dies.
wait -n
