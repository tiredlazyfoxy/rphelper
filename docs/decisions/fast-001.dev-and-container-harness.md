# Decisions — fast-001.dev-and-container-harness
**Stage:** 001.instance · **Feature:** fast/001.dev-and-container-harness

The dev launcher, the all-in-one prod image and its nginx and supervisord
configuration. The contracts these entries realize are `deployment.md`'s "Prod
topology", "Static entries and SPA fallback" (the routing table in "The app
document at `/`"), "`/api/` proxy" and "Access-log lines record the path without
its query string". Written at finalization (2026-11-09) from the feature's
recorded decisions.

### DEC-F001-1 — The `/` seam is a copy in the image build, after a presence check
- **Status:** accepted
- **Stage:** 001.instance · **Feature:** fast/001.dev-and-container-harness · **Step:** —
- **Date:** 2026-10-06 · **Decided by:** user
- **Question:** How does prod serve the `app` entry's document at `/` when the Vite build emits only `dist/<entry>/index.html` and no root document?
- **Decision:** The Docker frontend stage first fails the build (non-zero exit) if any of the four `dist/<entry>/index.html` is missing, then copies `dist/app/index.html` to `dist/index.html`. The prod catch-all `location / { try_files $uri $uri/ /index.html; }` serves it for `/` and every app client route.
- **Reason:** It keeps the build at exactly four documents (plan 002 refused a fifth root document) and moves the bridge to the one place that only prod needs it; the presence check makes a missing entry fail the image instead of a page load.
- **Rejected:** a fifth build input or a `src/index.html` — refused by plan 002 and asserted against by the build-config test.
- **Lands in:** `Dockerfile` (frontend stage); `docker/nginx.conf` (catch-all)
- **Cites:** `deployment.md` "The app document at `/` — prod and dev" (prod mechanism)

### DEC-F001-2 — No `location /app/` block
- **Status:** accepted
- **Stage:** 001.instance · **Feature:** fast/001.dev-and-container-harness · **Step:** —
- **Date:** 2026-10-06 · **Decided by:** planner (confirmed: user)
- **Question:** The design listed a `location /app/` fallback; what is its fate once the app document answers at `/`?
- **Decision:** Dropped. Only the `/bootstrap/`, `/login/` and `/admin/` prefix fallbacks and the catch-all exist.
- **Reason:** The `app` entry is root-mounted with no basename and nothing navigates to `/app/`, so the block would serve a URL space nobody uses; with it removed, `/app/...` falls to the catch-all, which serves the same document, so nothing breaks.
- **Rejected:** keeping the block as the source the root is bridged from — a second URL for one document, which the routing contract says is not user-facing.
- **Lands in:** `docker/nginx.conf`
- **Cites:** `deployment.md` "Static entries and SPA fallback"

### DEC-F001-3 — Slash-less entry paths: exact-match locations returning a relative 302
- **Status:** accepted
- **Stage:** 001.instance · **Feature:** fast/001.dev-and-container-harness · **Step:** —
- **Date:** 2026-10-06 · **Decided by:** planner
- **Question:** `/login` (no slash) is the client's 401 target and the bootstrap refusal's link, and does not match `location /login/`. Which nginx directive resolves it?
- **Decision:** `location = /login { return 302 /login/; }`, and for consistency the same for `= /bootstrap` and `= /admin`. The target is relative.
- **Reason:** The redirect lands on the entry's canonical URL (the one Vite dev serves too), so the prefix block's fallback and the `index.html` no-cache rule apply unchanged with no extra cache directive on an exact-match block. 302 rather than 301 so browsers do not cache the decision permanently. The extra round trip on a 401 is negligible.
- **Rejected:** 301 — browsers pin it; serving the login document straight from the exact-match block — it would need its own cache-control directive and a second definition of what the entry is.
- **Lands in:** `docker/nginx.conf`
- **Cites:** `deployment.md` "Slash-less entry paths"; `frontend-structure.md` "The API client" (the 401 navigation)

### DEC-F001-4 — `absolute_redirect off` at server level
- **Status:** accepted
- **Stage:** 001.instance · **Feature:** fast/001.dev-and-container-harness · **Step:** —
- **Date:** 2026-10-06 · **Decided by:** planner
- **Question:** nginx's own redirects (the slash-less 302s and its directory-slash 301s) emit an absolute `Location` built from the listening port. What stops them pointing at port 80?
- **Decision:** `absolute_redirect off` in the `server` block, so every redirect nginx emits carries a relative `Location`.
- **Reason:** The container listens on `:80` but is published on `8193`; an absolute `Location` would send the browser to `http://host:80/...`, which nothing on the host answers.
- **Lands in:** `docker/nginx.conf`
- **Cites:** `deployment.md` "Static entries and SPA fallback"; the routing table's "relative `Location`"

### DEC-F001-5 — `location ^~ /api/`
- **Status:** accepted
- **Stage:** 001.instance · **Feature:** fast/001.dev-and-container-harness · **Step:** —
- **Date:** 2026-10-06 · **Decided by:** planner
- **Question:** The design's snippet showed a plain `location /api/`. Does every `/api/` request reach the proxy block?
- **Decision:** The block is declared `location ^~ /api/`.
- **Reason:** In nginx a matching regex location outranks a plain prefix location, so an `/api/` path ending in, say, `.png` or `/index.html` would be claimed by the asset cache-control regexes and never proxied. `^~` stops regex evaluation once the prefix matches.
- **Lands in:** `docker/nginx.conf`
- **Cites:** `deployment.md` "`/api/` proxy", "5. Asset cache-control"

### DEC-F001-6 — Path-only access log, declared inside the `server` block
- **Status:** accepted
- **Stage:** 001.instance · **Feature:** fast/001.dev-and-container-harness · **Step:** —
- **Date:** 2026-10-06 · **Decided by:** user (placement amended by the orchestrator after verification found a leak)
- **Question:** nginx's access log recorded full request URIs, so `GET /api/search?q=<user text>` reached it. How is the query string kept out?
- **Decision:** The config defines a `log_format` built on `$uri` — never `$args`, `$query_string`, `$request_uri` or `$request` — at the top of the file (http context; the file is included inside `http { }`), with `error_log` to stderr there too. The `access_log /dev/stdout <format>` directive sits **inside the `server` block**, never at file top. No `location` declares its own `access_log`. The base image's main `/etc/nginx/nginx.conf` is not edited. `backend/tests/test_deployment_files.py` checks the format, the placement and the absence of base-config edits.
- **Reason:** `access_log` directives at the same level add up, while one declared at a lower level replaces every inherited one. The base image's main config declares an http-level access log whose format logs `$request` (query included); a server-level declaration suppresses it without touching that file. A `location`-level `access_log` would in turn replace the server-level one for that location. `log_format` is only valid at http level, so it stays at file top.
- **Rejected:** `access_log` at file top — it is added to the inherited default, and verification saw `?q=secret` leak; `sed -i '/access_log/d'` on the base `nginx.conf` — depends on the base image's file text and misses any other image using the config; `access_log off` for `/api/` — loses the API lines an operator needs.
- **Lands in:** `docker/nginx.conf`; `Dockerfile` (no base-config edit); `backend/tests/test_deployment_files.py`
- **Cites:** `deployment.md` "Access-log lines record the path without its query string", "The redaction rule"

### DEC-F001-7 — Deployment file layout and how the image installs its configs
- **Status:** accepted; compose layout superseded by DEC-F013-4
- **Stage:** 001.instance · **Feature:** fast/001.dev-and-container-harness · **Step:** —
- **Date:** 2026-10-06 · **Decided by:** user (layout); planner (installation details)
- **Question:** Where do the deployment files live, and how does the image install them?
- **Decision:** At repo root: `Dockerfile`, the compose files, `start.ps1`, `.env.example`, `.dockerignore`. Under `docker/`: `nginx.conf` and `supervisord.conf`. The nginx file is a server-level config installed as `/etc/nginx/conf.d/default.conf`, and the image removes Debian's `sites-enabled/default`. `supervisord.conf` is installed at `/etc/supervisor/supervisord.conf`, replacing Debian's (so there is no `supervisorctl` socket), and the image's command is `supervisord -n -c` that path. The build stage is `node:22-slim` (`npm ci`, `npm run build`); `uv` is copied from `ghcr.io/astral-sh/uv:latest`; the backend installs with `uv sync --frozen --no-dev`; the runtime image carries `curl` for the healthcheck. The compose file names are as revised by `DEC-F013-4`.
- **Reason:** A server-level include is what makes a top-of-file `log_format` legal (DEC-F001-6) and keeps the base image's main config untouched; removing the default site leaves one server answering `:80`. No Node version was pinned by the project, so the current LTS slim image was taken; `--frozen` keeps the image on the committed lock.
- **Lands in:** `Dockerfile`, `docker/nginx.conf`, `docker/supervisord.conf`
- **Cites:** `deployment.md` "Prod topology"

### DEC-F001-8 — supervisord runs nginx and exactly one uvicorn, with no wait-for ordering
- **Status:** accepted
- **Stage:** 001.instance · **Feature:** fast/001.dev-and-container-harness · **Step:** —
- **Date:** 2026-10-06 · **Decided by:** user
- **Question:** What does the process supervisor start, and how?
- **Decision:** `nodaemon`, two programs: nginx in the foreground (`daemon off;`), and exactly one uvicorn on `127.0.0.1:8184` with no `--workers` and no `--reload`, working directory `/app`. Both log to stdout/stderr. No startup ordering between them. `backend/tests/test_deployment_files.py` guards the single process.
- **Reason:** One uvicorn process is the single-generator guarantee; the early-502 window that no ordering leaves is accepted and handled by the readiness story.
- **Lands in:** `docker/supervisord.conf`; `backend/tests/test_deployment_files.py`
- **Cites:** `deployment.md` "The single-generator guarantee", "Prod topology" (`supervisord` has no wait-for ordering)

### DEC-F001-9 — `start.ps1`: two flags, two terminals, literal ports
- **Status:** accepted
- **Stage:** 001.instance · **Feature:** fast/001.dev-and-container-harness · **Step:** —
- **Date:** 2026-10-06 · **Decided by:** user
- **Question:** How does the Windows dev launcher start the pair?
- **Decision:** `-app` (alias `-api`) changes to `backend/` and runs `.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8184 --reload`; `-ui` (alias `-web`) changes to `frontend/` and runs `npx vite --port 8193`. Separate invocations for separate terminals. Directories resolve from the script's own location, not the caller's working directory. Ports are literals.
- **Reason:** Separate consoles keep a backend traceback and a Vite compile error apart; resolving from the script's location makes the launcher work from any working directory; literal ports follow the configuration convention.
- **Lands in:** `start.ps1`
- **Cites:** `deployment.md` "Dev topology", "Configuration conventions"
