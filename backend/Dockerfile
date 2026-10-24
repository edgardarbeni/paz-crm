# syntax=docker/dockerfile:1.7
# PAZOS API — multi-stage build with uv.
#   dev     : dependencies incl. dev group, hot reload (docker compose)
#   runtime : minimal non-root production image

FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH
WORKDIR /app

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

FROM builder AS dev
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen
EXPOSE 8000
CMD ["uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--proxy-headers", "--forwarded-allow-ips", "*"]

FROM base AS runtime
RUN groupadd --system --gid 10001 paz && useradd --system --uid 10001 --gid paz --no-create-home paz
COPY --from=builder --chown=paz:paz /opt/venv /opt/venv
COPY --from=builder --chown=paz:paz /app /app
USER paz
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
CMD ["uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
