#!/bin/sh
set -e

echo "Checking database connection..."
python scripts/wait_for_db.py

echo "Running database migrations..."
alembic upgrade head

echo "Running standard data seed..."
python scripts/seed_standard_jobs.py

if [ -n "$SEED_ADMIN_PASSWORD" ]; then
    echo "Running admin seed..."
    python scripts/seed_admin.py
else
    echo "Skipping admin seed because SEED_ADMIN_PASSWORD is not set."
fi

echo "Starting API on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
