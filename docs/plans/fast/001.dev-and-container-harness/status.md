# Fast feature 001 — dev-and-container-harness

| Status  | Verifier | Date |
|---------|----------|------|
| done    | PASS     | 2026-10-06 |

## Files Changed

- `start.ps1` — host-dev launcher, `-app`/`-api` uvicorn 127.0.0.1:8184 --reload, `-ui`/`-web` Vite 8193, usage + exit 1 otherwise
- `Dockerfile` — two-stage build: node:22-slim frontend build + four-entry check + root index copy; python:3.12-slim runtime with nginx/supervisor/curl and `uv sync --frozen --no-dev`; no edit of the base main nginx config
- `docker-compose.yml` — prod service: 8193:80, `.env`, `./data:/app/data`, status-only curl healthcheck, unless-stopped
- `docker-compose.dev.yml` — stock nginx serving `frontend/dist` read-only, proxying to host uvicorn via host.docker.internal
- `docker/nginx.conf` — prod server config: entry fallbacks, slash-less 302s, root catch-all, `^~ /api/` streaming proxy, cache-control, top-level path-only `log_format` with `access_log` as the server block's first directive
- `docker/nginx.dev.conf` — dev-compose server config, identical except upstream host and `/app/index.html` catch-all (same server-level `access_log`)
- `docker/supervisord.conf` — nodaemon, foreground nginx, one loopback uvicorn in `/app`, logs to stdout/stderr
- `.env.example` — every `Settings` alias plus `SEARCH_CSE_*` and the `$ENV_VAR` key note
- `.dockerignore` — excludes VCS, venvs, node_modules, dist, data, .env, caches, docs
- `.gitignore` — removed stale BOOKWRITER log-sink comment and `/logs/`

## Skeleton

### Frozen interface (2026-10-06)

No Python/TypeScript symbols. The interface is the set of artifact paths and the names the file-contract test binds to. Each new file is a one-line comment placeholder (no directives); `.gitignore` is untouched (coder's edit). Repo root = `D:/GitRoot/_TextGens/RPHelper` (the test file's grandparent's parent).

**Repo-relative paths (DoD-1):**
- `start.ps1` — new (placeholder)
- `Dockerfile` — new (placeholder)
- `docker-compose.yml` — new (placeholder)
- `docker-compose.dev.yml` — new (placeholder)
- `docker/nginx.conf` — new (placeholder)
- `docker/nginx.dev.conf` — new (placeholder)
- `docker/supervisord.conf` — new (placeholder, `;` comment)
- `.env.example` — new (placeholder)
- `.dockerignore` — new (placeholder)
- `.gitignore` — existing, unchanged by skeleton (coder removes the BOOKWRITER comment and `/logs/`)

**Bound names (from plan Interface intent / context Decisions 7, 9, 10):**
- `start.ps1` switch parameters: `app` (alias `api`), `ui` (alias `web`). Literals: `.venv/Scripts/python`, `app.main:app`, `--host 127.0.0.1`, `--port 8184`, `--reload`; `vite` with `--port 8193`.
- `docker/supervisord.conf` sections: `[supervisord]` (`nodaemon=true`), `[program:nginx]`, `[program:uvicorn]` (`directory=/app`).
- nginx location forms: `location ^~ /api/`, `location /bootstrap/`, `location /login/`, `location /admin/`, `location = /bootstrap`, `location = /login`, `location = /admin`, `location /`; no `location /app/`.
- Upstreams: prod `http://127.0.0.1:8184/api/`; dev `http://host.docker.internal:8184/api/`.
- Compose service names: not specified by the plan, so the coder picks them and tests must not bind to them. `docker-compose.yml` has exactly one service; `docker-compose.dev.yml` has exactly one (stock nginx image).

**In-container paths:**
- WORKDIR / backend root / uvicorn cwd: `/app`; data volume `./data:/app/data`.
- Static root: `/usr/share/nginx/html` (prod: built `dist/` + copied `dist/index.html`; dev-compose: `./frontend/dist` mounted read-only).
- nginx server config: `docker/nginx.conf` → `/etc/nginx/conf.d/default.conf` (prod); `docker/nginx.dev.conf` → `/etc/nginx/conf.d/default.conf` (dev-compose, read-only mount). Debian `sites-enabled/default` removed in prod.
- supervisord config: `docker/supervisord.conf` → the image's supervisord config location (exact target path is the coder's choice; the plan does not fix it).
- Healthcheck URL (in-container): `http://localhost/api/health`.

- Caller-compile edits (out of Source-files scope): None.

## Tests

### Tests (2026-10-06)
- `backend/tests/test_deployment_files.py` — covers DoD-1..DoD-14 — text-level file contract: artifacts exist; both nginx configs' `^~ /api/` directive set, upstreams, normalised-identical /api/, cache and log blocks, path-only `$uri` log format to stdout, entry try_files + `= /entry` relative 302s + `absolute_redirect off` + no `/app/`, catch-all fallbacks; supervisord nodaemon / single loopback uvicorn / foreground nginx; compose ports/env/volume/restart + status-only curl healthcheck; Dockerfile two stages, python:3.12-slim runtime with `uv sync --frozen --no-dev` and curl/nginx/supervisor, four-entry check and root index copy; start.ps1 switches/aliases/literals; `.env.example` covers every introspected `Settings` alias; `.dockerignore` excludes; `.gitignore` without BOOKWRITER and `/logs/`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 [verifier gate: `ruff check .` from `backend/`], DoD-16..19 [manual/live, no test]

### Tests — DoD-6 amendment (2026-10-06)
- `backend/tests/test_deployment_files.py` — covers amended DoD-6 — both nginx configs have exactly one `server` block; no `access_log` at file top level; an `access_log` directly at server level (outside any location); no location block declares `access_log`; `Dockerfile` contains no `/etc/nginx/nginx.conf`. No existing test asserted top-of-file placement, so none needed changing.
- Coverage: DoD-6 ✓ (amended clauses added); all other coverage unchanged.

## Notes & Issues

- Dev-compose redaction gap (resolved by the DoD-6 amendment): the stock image's main-config `access_log` (`$request`) no longer applies, because both configs now declare `access_log` at server level, which replaces the inherited one; the prod Dockerfile no longer edits the main config.
- Live checks (DoD-16..19) not run here; only the `start.ps1` no-switch usage path was exercised (prints usage, exit 1).
