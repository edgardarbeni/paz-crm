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
# supercronic runs the scheduled jobs (D-84): pinned release, verified by SHA-256 per architecture.
ARG SUPERCRONIC_VERSION=v0.2.51
RUN python - <<'PY'
import hashlib, os, subprocess, urllib.request
arch = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
sha = {
    "amd64": "cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123",
    "arm64": "4ae22576a78223d8ccdf5f3b3660a5cbb5288416bf0ca96afc4a36d195932b94",
}[arch]
url = f"https://github.com/aptible/supercronic/releases/download/{os.environ['SUPERCRONIC_VERSION']}/supercronic-linux-{arch}"
data = urllib.request.urlopen(url, timeout=60).read()
assert hashlib.sha256(data).hexdigest() == sha, "supercronic checksum mismatch"
with open("/usr/local/bin/supercronic", "wb") as f:
    f.write(data)
os.chmod("/usr/local/bin/supercronic", 0o755)
PY

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY alembic.ini crontab ./
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
