FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY app ./app

RUN uv pip install --system --no-cache .

COPY alembic.ini ./
COPY alembic ./alembic
COPY templates ./templates
COPY static ./static
COPY scripts ./scripts

CMD ["sh", "-c", "mkdir -p /app/uploads && alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
