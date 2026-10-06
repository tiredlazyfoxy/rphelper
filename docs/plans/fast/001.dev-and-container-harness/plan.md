# fast/001.dev-and-container-harness — plan

Read `context.md` first. Its Decisions 1–10 are binding. `docs/architecture/deployment.md`
is authoritative for every directive value quoted below.

## Goal

Make both topologies real. Host dev runs as two `start.ps1` invocations. Prod runs
as one container (nginx and a single uvicorn under supervisord) on host port 8193,
with a healthcheck that passes only when nginx-to-uvicorn answers. Both nginx
configs carry every streaming, body, cache and redaction directive, and the open
nginx seams (`/`, `/app/`, `/login`, access_log) are closed.

## Source files

- `start.ps1`: host-dev launcher, `-app`/`-api` and `-ui`/`-web`.
- `Dockerfile`: two-stage build. The Node stage builds the frontend, checks the
  four entries and copies the root document. The Python runtime stage installs
  nginx, supervisor, curl and the uv-locked backend.
- `docker-compose.yml`: the prod service. Publishes 8193:80, uses `.env` as env
  file, mounts `./data:/app/data`, has a curl healthcheck and restarts unless-stopped.
- `docker-compose.dev.yml`: an nginx-only container that serves the local
  `frontend/dist` and proxies to the host uvicorn.
- `docker/nginx.conf`: prod server config.
- `docker/nginx.dev.conf`: dev-compose server config.
- `docker/supervisord.conf`: two programs, nginx and one uvicorn.
- `.env.example`: documents every `Settings` variable plus `SEARCH_CSE_*`.
- `.dockerignore`: keeps local state and build output out of the build context.
- `.gitignore`: remove the stale BookWriter log-sink comment and the dead `/logs/` line.

Read-only reference (not edited): `backend/app/config.py` (for the variable list) and
`frontend/vite.config.ts`.

## Test files

- `backend/tests/test_deployment_files.py`: a file-contract test. It reads the repo-root
  deployment artifacts as text (repo root = the test file's grandparent's parent)
  and asserts the directive contract below. It may import `app.config.Settings`
  to enumerate setting aliases.

## Interface intent

There is no Python or TypeScript interface. The "interface" is the set of
artifacts and the contract each must hold. **For the skeleton:** create each
Source file as a placeholder containing only a header comment (and leave
`.gitignore` untouched), so the red gate fails on assertions rather than on
missing files. Freeze in `## Skeleton` the exact repo-relative paths and the
in-container paths the configs are installed at.

- **`start.ps1`** takes switch parameters `-app` (alias `-api`) and `-ui` (alias
  `-web`). It resolves `backend/` and `frontend/` relative to the script's own
  directory.
  - `-app` launches uvicorn on 127.0.0.1:8184 with reload, using the backend venv
    python and cwd `backend/`.
  - `-ui` launches Vite on port 8193 with cwd `frontend/`.
  - With neither switch, or both, it prints usage and exits non-zero. It never
    spawns both processes.
- **`Dockerfile`, frontend stage** (Node LTS slim): `npm ci`, then `npm run build`.
  Next it runs a check that exits non-zero if any of
  `dist/{bootstrap,login,admin,app}/index.html` is absent. Then it copies
  `dist/app/index.html` to `dist/index.html`.
- **`Dockerfile`, runtime stage** (`python:3.12-slim`, WORKDIR `/app`):
  - Installs `nginx`, `supervisor` and `curl`.
  - Installs uv and runs `uv sync --frozen --no-dev` against the committed
    `backend/uv.lock`, with backend contents placed directly under `/app`.
  - Copies the frontend `dist/` to `/usr/share/nginx/html`.
  - Installs `docker/nginx.conf` as `/etc/nginx/conf.d/default.conf`, removes
    Debian's default site and installs `docker/supervisord.conf`.
  - Does **not** edit the base image's main `/etc/nginx/nginx.conf` (no `sed` or
    other rewrite of it). The server-level `access_log` in our config already
    overrides the main file's http-level one (context Decision 6).
  - Exposes 80, and its CMD runs supervisord in the foreground.
  - Node and `node_modules` never reach this stage.
- **`docker-compose.yml`** defines one service built from the root Dockerfile with
  `ports ["8193:80"]`, `env_file .env`, `volumes ["./data:/app/data"]` and
  `restart unless-stopped`. Its healthcheck test is
  `["CMD", "curl", "-f", "http://localhost/api/health"]` (interval, timeout and
  retries are the coder's choice). It never inspects the body.
- **`docker-compose.dev.yml`** defines one stock nginx-image service:
  - publishes `8193:80`;
  - mounts `./frontend/dist` read-only at `/usr/share/nginx/html`;
  - mounts `docker/nginx.dev.conf` read-only as `/etc/nginx/conf.d/default.conf`;
  - sets `extra_hosts host.docker.internal:host-gateway`.

  A comment states that this container and host Vite share 8193 (run one, never
  both), and gives the Linux loopback caveat.
- **`docker/nginx.conf`** is a server-level config, included in the `http`
  context. At file top (http level): a path-only `log_format` named once, plus
  `error_log /dev/stderr`. There is **no** `access_log` at file top. The server
  block holds:
  - `access_log /dev/stdout` using that named format. It sits inside the server
    block on purpose: a server-level `access_log` replaces every inherited
    http-level one, including the main `nginx.conf`'s query-string-bearing default
    (context Decision 6).
  - `listen 80`, root `/usr/share/nginx/html` and `absolute_redirect off`.
  - Prefix locations `/bootstrap/`, `/login/` and `/admin/`, each with
    `try_files $uri $uri/ /<entry>/index.html`.
  - Exact-match `= /bootstrap`, `= /login` and `= /admin`, each returning a 302
    to the slash form.
  - Catch-all `/` with `try_files $uri $uri/ /index.html`. There is **no**
    `location /app/`.
  - `location ^~ /api/`, which proxies to `http://127.0.0.1:8184/api/` with the
    directive set from deployment.md :348-363: Host / X-Real-IP / X-Forwarded-For
    headers, `proxy_http_version 1.1`, `Connection ''`, `proxy_buffering off`,
    `proxy_cache off`, `proxy_read_timeout 300s` and `client_max_body_size 64m`.
  - The two cache-control regex locations from deployment.md :434-441.

  No `location` block declares its own `access_log`, so the server-level one
  applies everywhere.
- **`docker/nginx.dev.conf`** is identical to the prod config, including the
  `log_format` at file top and the `access_log` inside the server block, except
  for the two permitted differences in context Decision 8:
  - the upstream host is `host.docker.internal:8184`;
  - the catch-all is `try_files $uri /app/index.html`.
- **`docker/supervisord.conf`** contains:
  - a `[supervisord]` section with `nodaemon=true`;
  - `[program:nginx]`, which runs nginx with `daemon off;`;
  - `[program:uvicorn]`, which runs the venv's uvicorn with `app.main:app` on
    `--host 127.0.0.1 --port 8184` (no `--workers`, no `--reload`) and
    `directory=/app`.

  Both programs send stdout/stderr to the container's stdout/stderr with log
  rotation disabled. There is no priority-based wait-for logic beyond supervisord defaults.
- **`.env.example`** lists every alias that `Settings` reads, one per line, as
  commented or blank-valued assignments with a one-line description each. That
  includes `SEARCH_CSE_KEY` and `SEARCH_CSE_ID` (noted as unprefixed on purpose,
  and optional). It also explains that an `llm_servers` API key stored as
  `"$ENV_VAR"` resolves against this environment, so the named variable belongs
  here too. It holds no real secret values.
- **`.dockerignore`** excludes at least `.git`, `**/.venv`, `**/node_modules`,
  `frontend/dist`, `data`, `.env`, `**/__pycache__`, `**/.pytest_cache`,
  `**/.mypy_cache`, `**/.ruff_cache` and `docs`.
- **`.gitignore`**: drop the "Dev log file sink (BOOKWRITER_LOG_DIR …)" comment and
  the `/logs/` entry. Nothing else changes.

## Definition of done

Static file contract, covered by `backend/tests/test_deployment_files.py`:

- **DoD-1 [test]**: Every Source file listed above exists at its repo-root path.
- **DoD-2 [test]**: Both nginx configs contain a `location ^~ /api/` block with
  every one of: `proxy_http_version 1.1`, `proxy_set_header Connection ''`,
  `proxy_buffering off`, `proxy_cache off`, `proxy_read_timeout 300s`,
  `client_max_body_size 64m`, and the Host, X-Real-IP and X-Forwarded-For
  `proxy_set_header` lines.
- **DoD-3 [test]**: The prod config's `/api/` block proxies to `http://127.0.0.1:8184/api/`.
  The dev config's proxies to `http://host.docker.internal:8184/api/`.
- **DoD-4 [test]**: The `/api/` block bodies are identical in the two configs
  once the upstream host is normalised. The same holds for both cache-control
  location blocks, the `log_format` line and the `access_log` line.
- **DoD-5 [test]**: Both configs contain the hashed-asset cache block
  (`public, max-age=31536000, immutable`) and the `index.html` `no-cache` block.
- **DoD-6 [test]**: Both configs declare a `log_format` that contains `$uri`. No
  `log_format`/`access_log` line in either file contains `$args`, `$query_string`,
  `$request_uri` or `$request` (as a whole variable token, so `$request_method`
  and `$request_time` are allowed). `access_log` uses that named format. In both
  configs the `access_log` directive is declared **inside the `server { … }`
  block** and never at file top level (http context), so it replaces the base
  image's inherited http-level access log. The `Dockerfile` does not edit the base
  image's nginx main config: it contains no reference to `/etc/nginx/nginx.conf`.
- **DoD-7 [test]**: Both configs contain `try_files` fallbacks for `/bootstrap/`,
  `/login/` and `/admin/` to their own `index.html`. Neither contains
  `location /app/`. Both contain `location = /login` returning a 302 to `/login/`.
  Both set `absolute_redirect off`.
- **DoD-8 [test]**: The prod catch-all `location /` falls back to `/index.html`.
  The dev catch-all falls back to `/app/index.html`.
- **DoD-9 [test]**: `docker/supervisord.conf` has `nodaemon=true`, exactly one
  program whose command runs uvicorn, and that command binds `127.0.0.1` and
  port `8184` and contains neither `--workers` nor `--reload`. It also has a
  program running nginx with `daemon off`.
- **DoD-10 [test]**: `docker-compose.yml` publishes `8193:80`, has `env_file`
  `.env`, mounts `./data:/app/data` and has `restart: unless-stopped`. Its
  healthcheck test invokes `curl -f` against `http://localhost/api/health` and
  carries no body assertion: no `grep`, `jq`, `"status"` or `ok` matching.
- **DoD-11 [test]**: The `Dockerfile` has two `FROM` stages, the runtime one based
  on `python:3.12-slim`, and runs `uv sync --frozen --no-dev`. It references all
  four `dist/<entry>/index.html` paths in a fail-fast check and copies
  `app/index.html` to the root `index.html`. It installs `curl`.
- **DoD-12 [test]**: `start.ps1` declares the `app`/`api` and `ui`/`web`
  parameters. It contains the literal `--port 8184`, `--host 127.0.0.1`,
  `--reload`, `app.main:app` and `.venv/Scripts/python`, and the literal
  `--port 8193` with `vite`.
- **DoD-13 [test]**: `.env.example` mentions every validation alias of every
  `app.config.Settings` field, enumerated by introspection, including
  `SEARCH_CSE_KEY` and `SEARCH_CSE_ID`.
- **DoD-14 [test]**: `.dockerignore` excludes `.venv`, `node_modules`, `dist`,
  `data` and `.git`. `.gitignore` no longer contains `BOOKWRITER`.
- **DoD-15 [test]**: `ruff check .` from `backend/` is clean on the new test file
  (verifier gate).

Live behaviour, recorded by the verifier as requires-live-run:

- **DoD-16 [manual/live]**: `docker compose build` succeeds. Deleting any one
  entry's `index.html` from the build makes it fail non-zero.
- **DoD-17 [manual/live]**: After `docker compose up`, the container becomes
  `healthy` on a fresh, unconfigured `./data`. `http://localhost:8193/` serves the
  app document. `/login` lands on the login document via the 302 with a relative
  `Location`. `/admin/users` serves the admin document. `/api/health` answers 200.
- **DoD-18 [manual/live]**: A `GET /api/search?q=secret` through nginx produces
  exactly one nginx access-log line, on container stdout, without `secret`. This
  holds in both the prod container and the dev-compose container (stock
  `nginx:stable` image), and neither writes a second access log under
  `/var/log/nginx/`.
- **DoD-19 [manual/live]**: `start.ps1 -app` and `start.ps1 -ui` in two terminals
  give a working dev instance at `http://localhost:8193/<entry>/`. With
  `docker-compose.dev.yml` up (Vite stopped) and `frontend/dist` built,
  `http://localhost:8193/` serves the app and `/api/health` reaches the host uvicorn.

## Out of scope

- TLS, certificates, `listen 443` and the cookie `Secure` flip.
- Metrics, alerting and log shipping.
- The application's own `X-Accel-Buffering: no` header (feature 019).
- Any change to `vite.config.ts`, `backend/app/**` or the frontend sources.
- A fifth Vite entry or an nginx `alias` approach to the root document.
- A Linux-native workaround for host-loopback reachability in dev-compose (comment only).
- CI wiring, image publishing and multi-arch builds.
- Replacing or editing the base images' main `/etc/nginx/nginx.conf`.
