# syntax=docker/dockerfile:1.7
# PAZOS panel. Build context: repository root (needs infra/caddy for the runtime image).
#   dev     : Vite dev server with HMR (docker compose)
#   runtime : Caddy serving the static build + reverse proxy to the API (production edge)

FROM node:24-alpine AS base
RUN npm install -g pnpm@12.15.0
WORKDIR /app
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN --mount=type=cache,id=pnpm,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile

FROM base AS dev
COPY frontend/ ./
ENV VITE_DEV_API_PROXY=http://api:8000
EXPOSE 5173
CMD ["pnpm", "dev", "--host", "0.0.0.0"]

FROM base AS build
COPY frontend/ ./
RUN pnpm build

FROM caddy:2.11-alpine AS runtime
COPY --from=build /app/dist /srv
COPY infra/caddy/Caddyfile.prod /etc/caddy/Caddyfile
