# RPHelper — one all-in-one image: nginx + one uvicorn under supervisord.
# Topology and directive reasons: docs/architecture/deployment.md.

# ---- Stage 1: frontend build (Node never reaches the runtime image) ----
FROM node:22-slim AS frontend

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Fail the build if any of the four entry documents is missing.
RUN test -f dist/bootstrap/index.html \
 && test -f dist/login/index.html \
 && test -f dist/admin/index.html \
 && test -f dist/app/index.html \
 || (echo "frontend build is missing an entry index.html" >&2 && exit 1)

# The app entry is root-mounted: serve its document at "/".
RUN cp dist/app/index.html dist/index.html

# ---- Stage 2: runtime ----
FROM python:3.12-slim AS runtime

RUN apt-get update \
 && apt-get install -y --no-install-recommends nginx supervisor curl \
 && rm -rf /var/lib/apt/lists/* \
 && rm -f /etc/nginx/sites-enabled/default

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Backend contents directly under /app, installed from the committed lock.
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/app ./app
RUN uv sync --frozen --no-dev

COPY --from=frontend /build/frontend/dist/ /usr/share/nginx/html/

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/supervisord.conf /etc/supervisor/supervisord.conf

EXPOSE 80

CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
