#!/bin/sh
set -e
mkdir -p /app/uploads
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
