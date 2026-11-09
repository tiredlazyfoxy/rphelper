# fast/001.dev-and-container-harness — context

Brief: `brief.md` (this folder). It sets the scope boundary and is not restated here.
Design: `docs/architecture/deployment.md`, which is authoritative for every directive.
Open seams this feature closes: `docs/architecture/quick-reference.md` `_TBD:` rows
1301 and 1302.

## What exists today (harvested)

- None of the deliverables exist yet: no `start.ps1`, `Dockerfile`, compose files,
  `docker/` folder, `.dockerignore` or `.env.example`.
- **Backend launch.** `uvicorn app.main:app` must run with `backend/` as cwd.
  `Settings` (`backend/app/config.py`) reads `.env` **relative to cwd**, has no
  env prefix and gives every field an explicit alias. Most aliases are `RPHELPER_*`;
  the two exceptions are `SEARCH_CSE_KEY` and `SEARCH_CSE_ID`, which are unprefixed
  on purpose (deployment.md "Configuration conventions": do not "fix" them).
  `RPHELPER_DATA_DIR` defaults to the relative `data`, which becomes `/app/data`
  when the container's working directory is `/app`. The coder reads
  `backend/app/config.py` to enumerate the variables for `.env.example`, and does
  not edit it.
- **Health.** `GET /api/health` exists (`backend/app/routers/health.py`). It
  answers **200 even when the instance is degraded or unconfigured**. The
  healthcheck must therefore assert only the status code and never the body
  (deployment.md :183-198, which explains why this matters). The runtime image needs `curl`.
- **Backend packaging.** `backend/pyproject.toml` has requires-python >=3.12 and
  uses hatchling. `backend/uv.lock` is committed and there is no
  requirements.txt. The image installs with `uv sync --frozen --no-dev` and never
  resolves at build time. `sqlite-vec==0.1.9` needs SQLite extension loading;
  `python:3.12-slim` supports it.
- **Frontend.** `npm run build` runs `vite build` with root `src/`, outDir
  `frontend/dist` and four inputs. It emits `dist/{bootstrap,login,admin,app}/index.html`
  plus `dist/assets/` (absolute `/assets/` URLs) and **no `dist/index.html`**.
  `package-lock.json` exists, so the build uses `npm ci`. No Node version is
  pinned, so choose a current LTS slim image.
  `vite.config.ts` already has port 8193, `strictPort` and the `/api` → `localhost:8184` proxy. It is not touched here.
- **Static ownership.** The backend serves no static files. nginx serves them in
  prod and dev-compose, and Vite serves them in host dev.
- **App entry is root-mounted.** Its routes are `/`, `/sessions/:id` and
  `/characters/:id`. Nothing navigates to `/app/`. A 401 anywhere navigates to
  exactly `/login` (no trailing slash), and the bootstrap refusal links to exactly `/login`.
- **Root `.gitignore`** already covers `.env`, `dist`, `node_modules`, `*.sqlite`,
  `/data/` and `docker-compose.override.yml`. Around line 51 it has a stale
  BookWriter comment ("Dev log file sink (BOOKWRITER_LOG_DIR, set by start.ps1 -app)")
  followed by `/logs/`. The logs now live under `data/logs/`, which `/data/`
  already covers, so both lines are dead.
- No existing test asserts on deployment files.

## Decisions (user-confirmed or planner-chosen)

1. **The "/" seam is a copy in the image build.** The Docker frontend stage first
   fails the build (non-zero exit) if any of the four `dist/<entry>/index.html` is
   missing. It then copies `dist/app/index.html` to `dist/index.html`. The prod
   catch-all `location /` falls back to `/index.html`. *(user)*
2. **Drop `location /app/`** *(planner, user-permitted)*. The app entry is
   root-mounted and nothing navigates to `/app/`, so the block would serve a URL
   space nobody uses. With the block removed, `/app/...` falls to the catch-all,
   which serves the same app document, so nothing breaks.
3. **Slash-less entry paths redirect** *(planner)*. `location = /login` returns a
   **302** to `/login/` (relative). For consistency `= /bootstrap` and `= /admin`
   do the same. Reasons:
   - The redirect lands on the entry's canonical URL, the same one Vite dev
     serves at `/login/`. The prefix block's fallback and the
     `index.html` no-cache rule then apply unchanged, with no extra cache directive on an
     exact-match block.
   - 302, not 301, so browsers do not cache the decision permanently.
   - The extra round-trip on a 401 is negligible.
4. **`absolute_redirect off`** at server level in both configs *(planner)*.
   Container nginx listens on :80 but is published on 8193. Without this, nginx's
   own redirects (the slash-less 302s and the directory-slash 301s) would emit
   absolute `Location` headers pointing at port 80.
5. **`location ^~ /api/`** *(planner)*. Regex locations, including the asset
   cache-control regex, take precedence over plain prefix locations in nginx. `^~`
   guarantees that every `/api/` request, whatever its suffix, reaches the proxy
   block.
6. **Path-only access log, declared at server level** *(user; placement amended
   by orchestrator after verification)*. Both configs define a `log_format` built
   on `$uri` and never `$args`, `$query_string`, `$request_uri` or `$request`.
   The `log_format` stays at file top (http context), and `error_log` goes to
   stderr there too. The `access_log /dev/stdout <format>` directive sits
   **inside the `server` block**, never at file top. The Dockerfile does not touch
   the base image's main `/etc/nginx/nginx.conf`. See "Amendment: access_log
   placement" below for why.
7. **Layout** *(user)*:
   - At repo root: `Dockerfile`, `docker-compose.yml`, `docker-compose.dev.yml`,
     `start.ps1`, `.env.example`, `.dockerignore`.
   - Under `docker/`: `nginx.conf` (prod), `nginx.dev.conf` (dev-compose),
     `supervisord.conf`.
   - Both nginx files are **server-level configs** installed as
     `/etc/nginx/conf.d/default.conf`. They are included in the `http` context,
     so a top-of-file `log_format` is legal. The prod image removes Debian's
     `sites-enabled/default`.
8. **Dev-compose divergence** *(planner, forced)*. The dev-compose container
   serves the local, unmodified `frontend/dist`, which has no root `index.html`.
   The dev config is allowed exactly two differences from prod, and they are the
   only ones:
   - (a) the upstream is `host.docker.internal:8184` instead of `127.0.0.1:8184`;
   - (b) the catch-all falls back to `/app/index.html` with no `$uri/` term.
     nginx answers 403 on a `$uri/` match of a directory with no index file.

   Every streaming, proxy, body, timeout, cache-control and log directive is
   byte-identical between the two files.
9. **supervisord** *(user)*. `nodaemon`, two programs:
   - nginx in the foreground (`daemon off;`);
   - exactly one uvicorn on `127.0.0.1:8184` with no `--workers` and no
     `--reload`, cwd `/app`.

   Both log to stdout/stderr. There is no wait-for ordering (deployment.md
   :200-207 explains why the early 502 window is accepted).
10. **start.ps1** *(user)*. PowerShell.
    - `-app` (alias `-api`): cd `backend`, then run
      `.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8184 --reload`.
    - `-ui` (alias `-web`): cd `frontend`, then `npx vite --port 8193`.

    These are separate invocations for separate terminals. Ports are literals.
    Directories resolve relative to the script's own location, not the caller's cwd.

## Amendment: access_log placement (post-verification)

The first implementation passed verification, but the verifier found a real leak.
The configs declared `access_log /dev/stdout rphelper_path;` at file top, which is
the http context, because `conf.d/*.conf` is included inside `http { }`. The base
images' main `/etc/nginx/nginx.conf` also declares an http-level access log: the
stock `nginx:stable` image uses `access_log /var/log/nginx/access.log main;`, where
`main` logs `$request`, and Debian's nginx package does something similar.
Several `access_log` directives at the same level **add up**, so both logs were
written and `?q=secret` leaked in dev-compose. Prod only avoided the leak with a
`sed -i '/access_log/d' /etc/nginx/nginx.conf` in the Dockerfile. That was fragile
because it depends on the base image's file text and misses the dev-compose
image entirely.

The fix: an `access_log` declared at a lower level (server) **replaces** all
inherited ones instead of adding to them. Moving the directive into the `server`
block therefore suppresses the main file's default in both images, with no edit
to the base config. The `log_format` stays at http level, because `log_format`
is only valid there. The `sed` line is removed. No `location` may declare its own
`access_log`, since that would replace the server-level one for that location.

## Constraints

- Ports are hardcoded literals everywhere (8184, 8193, 80) and never environment
  variables (deployment.md :459-464).
- One uvicorn process (deployment.md :245-253). This is the snowflake
  single-generator guarantee.
- The healthcheck never inspects the body.
- Out of scope per brief: TLS, metrics and alerting, the app's
  `X-Accel-Buffering` header.
- **Live-run risk to note, not solve.** In dev-compose, uvicorn on the host binds
  `127.0.0.1`. Docker Desktop on Windows forwards `host.docker.internal` to the
  host, so this works there. On native Linux Docker a loopback-bound host
  process is unreachable. The compose file adds
  `extra_hosts: host.docker.internal:host-gateway`, and the residual Linux caveat
  goes in a comment.
- Subagents may lack a shell. The verifier gate runs `ruff check .` and `pytest`
  from `backend/`. `docker build` / `docker compose up` are live-only checks.
