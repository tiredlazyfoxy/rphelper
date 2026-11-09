# fast/001.dev-and-container-harness — outcome

Intended doc changes, for the architect to apply at finalization.

## docs/architecture/deployment.md

- **Section:** "Static entries and SPA fallback"
  **Change:** Replace the five-block listing with the as-built set:
  - the `/bootstrap/`, `/login/` and `/admin/` prefix fallbacks;
  - exact-match `= /bootstrap`, `= /login` and `= /admin` 302s to the slash form;
  - the catch-all `/` falling back to `/index.html`;
  - no `location /app/`.

  Add `absolute_redirect off` with its reason: the container listens on :80 but
  is published on 8193.
  **Reason:** Closes the three seams this doc assigned to fast/001.

- **Section:** "Open seam — the `/` fallback and the app document"
  **Change:** Convert to a decision. The Docker frontend stage fails the build if
  any of the four `dist/<entry>/index.html` is missing, then copies
  `dist/app/index.html` to `dist/index.html`. The prod catch-all serves it.
  dev-compose serves an unmodified local `dist/`, so its catch-all falls back to
  `/app/index.html` with no `$uri/` term, because nginx would 403 on an index-less
  directory. That is the sole static-routing divergence between the two configs.
  Remove the `_TBD:`.
  **Reason:** Mechanism chosen (user-confirmed) and built.

- **Section:** "Open seam — the `/` fallback …" (the `location /app/` paragraph)
  **Change:** Record that the block was dropped. The entry is root-mounted and
  nothing navigates to `/app/`, and `/app/...` still resolves via the catch-all.
  **Reason:** Seam closed.

- **Section:** "Open seam — `/login` without a trailing slash"
  **Change:** Record that `location = /login` returns a 302 to `/login/` (and the
  same for `/bootstrap` and `/admin`). The redirect lands on the entry's
  canonical URL, so the prefix fallback and `index.html` no-cache rule apply
  unchanged. It is 302, not 301, so browsers do not pin it. Remove the `_TBD:`.
  **Reason:** Seam closed.

- **Section:** "`/api/` proxy"
  **Change:** The block is `location ^~ /api/`. Note why: regex locations
  (the asset cache-control regex) otherwise outrank a plain prefix match.
  **Reason:** As-built deviation from the doc's snippet.

- **Section:** "Access-log lines record the path without its query string"
  **Change:** Replace the `_TBD:` with the decision:
  - Both nginx configs log with a path-only `log_format` built on `$uri` (no
    `$args` / `$query_string` / `$request_uri` / `$request`). `access_log` goes
    to stdout and `error_log` to stderr.
  - The `log_format` sits at http level (file top of the `conf.d` include). The
    `access_log` directive sits **inside the `server` block**. That placement is
    load-bearing: a server-level `access_log` replaces every inherited http-level
    one. Without it, the base images' main `nginx.conf` default access log
    (`$request`, query string included) would also apply, because same-level
    `access_log` directives add up. The image does not edit the base
    `nginx.conf`.
  - No `location` may declare its own `access_log`.
  - `backend/tests/test_deployment_files.py` enforces the format, the placement
    and the absence of base-config edits.
  **Reason:** Closes quick-reference row 1302. Records the inheritance trap the
  verifier found in dev-compose.

- **Section:** "Prod topology" (Dockerfile / Compose / supervisord)
  **Change:**
  - Mark the image as built and drop the "Forward-looking; no feature has built
    an image yet" sentence.
  - Name the file layout: root `Dockerfile` / `docker-compose.yml` /
    `docker-compose.dev.yml`, and `docker/{nginx.conf,nginx.dev.conf,supervisord.conf}`.
  - Note that both configs are installed as `conf.d/default.conf`.
  - State that supervisord runs exactly one uvicorn without `--workers`, and that
    the file-contract test guards it. This ties to the single-generator section.
  **Reason:** As-built record.

- **Section:** "Dev topology"
  **Change:** Add the dev-compose shape:
  - nginx-only, serving local `frontend/dist`;
  - upstream `host.docker.internal:8184` with `extra_hosts: host-gateway`;
  - the caveat that a host uvicorn bound to `127.0.0.1` is reachable from the
    container on Docker Desktop but not on native Linux.

  Also update the "dev-side consequence while it is unbridged" note: host Vite
  still does not serve `/`, because the copy is image-only.
  **Reason:** As-built record and a recorded asymmetry.

- **Section:** "Configuration conventions"
  **Change:** Mention the root `.env.example` as the documented variable list,
  and that a file-contract test checks it against `Settings` aliases.
  **Reason:** As-built record.

## docs/architecture/quick-reference.md

- **Section:** "Open `_TBD:` items across the doc set"
  **Change:** Remove rows 1301 (the three nginx seams) and 1302 (nginx
  access_log). Add a path entry for the deployment files if the paths table lists
  them.
  **Reason:** Both closed by this feature.

## Observations

- The earlier Dockerfile `sed` that stripped `access_log` from the base image's main nginx config is gone; suppression of the main-file default access log (`$request`, query string included) now rests entirely on our `access_log` sitting at server level in both configs, which replaces the inherited http-level one in prod and dev-compose alike. Possible impact: deployment.md Logging / redaction section should state that the server-level placement is what suppresses the base default log, and that moving it to file top silently reintroduces query strings.
- supervisord config is installed at `/etc/supervisor/supervisord.conf` (replacing Debian's, so no `supervisorctl` socket), with CMD `supervisord -n -c` that path; uv comes from `ghcr.io/astral-sh/uv:latest`, Node stage is `node:22-slim`. Possible impact: deployment.md "Two-stage Dockerfile" as-built record.
