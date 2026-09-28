# Deployment

**Realizes:** FEAT-001, FEAT-002, FEAT-009, FEAT-010, FEAT-018, FEAT-019,
UC-003, UC-027, US-035.AC-1, US-035.AC-2

Ports, the dev and prod topologies, every nginx directive with its reason, and the
configuration conventions. Build and test commands live in the root `CLAUDE.md`.

---

## Ports — the sibling project's minus one

RPHelper's ports are BookWriter's minus 1, so **both projects can run in parallel
on the same machine**. That is the entire reason for the numbers; there is nothing
else significant about them.

| Role | BookWriter | RPHelper |
|---|---|---|
| uvicorn / FastAPI | 8185 | **8184** |
| Vite dev server | 8194 | **8193** |
| nginx host-published by compose | 8194 → :80 | **8193** → :80 |
| nginx in-container `listen` | 80 | **80** (container-internal, never collides) |

**Known constraint, inherited and preserved:** the host-run Vite dev-server port
and the dev-compose nginx published port are **the same number** (8193). Run one or
the other, **never both** — the second one to start fails to bind. This is
deliberate in the sibling project (the container and the host dev server are two
ways of serving the same thing on the same URL) and is kept, but it is a trap worth
writing down rather than rediscovering.

The in-container `listen 80` never collides with anything because it is inside the
container's network namespace; only the published `8193` is a host resource.

## TLS — none, deliberately recorded as such

The inherited posture is **HTTP only**: there is no `listen 443`, no certificate
handling and no certificate mount anywhere in the sibling project, and RPHelper
inherits that.

`_TBD: if this instance is ever exposed beyond a trusted LAN, TLS must be
designed — termination point, certificate lifecycle, and the session cookie's
`Secure` flag, which is not set today (FEAT-002). Nothing in docs/product/ states
an exposure model, so nothing is assumed here. Until then the deployment target is
a trusted local network._`

---

## Dev topology

```
terminal 1:  start.ps1 -app        (or -api)   → uvicorn --port 8184 --reload
terminal 2:  start.ps1 -ui         (or -web)   → npx vite --port 8193

browser ──► Vite :8193 ──/api──► uvicorn :8184 ──► ./data/rphelper.sqlite
                         proxy
```

`start.ps1` takes `-app`/`-api` and `-ui`/`-web` as **separate invocations in
separate terminals**, not one command that spawns both. Reason: each process has
its own reload behaviour and its own log stream, and a single supervising script
makes a backend traceback and a Vite compile error compete for the same console.

Vite proxy configuration — **one prefix only**:

```ts
server: {
  port: 8193,
  proxy: { "/api": "http://localhost:8184" },
}
```

The result is that **the browser sees one origin in dev**, so the cookie and CORS
story is *identical* to production: no CORS middleware, no `credentials: "include"`
special-casing, no `SameSite=None`. This is the decisive reason the four-entry
frontend split is safe (`overview.md`) — cross-entry navigation is same-origin, so
the HttpOnly session cookie travels automatically and no entry needs auth
plumbing.

One prefix rather than several because everything the backend serves lives under
`/api` (`backend-structure.md`); a second proxy rule would mean a second place for
dev and prod routing to diverge.

**HMR rides the ordinary route.** Vite 6 sets no `server.hmr.path`, so the HMR
websocket goes over the same origin and port as everything else. There is no
separate HMR port to publish, proxy or firewall.

---

## Prod topology

**One all-in-one container, two processes under `supervisord`:**

```
┌── container ─────────────────────────────────────────┐
│  supervisord                                          │
│    ├── nginx        listen :80                        │
│    └── uvicorn      127.0.0.1:8184   (loopback only)  │
│                                                       │
│  /usr/share/nginx/html    ← dist/ (4 Vite entries)    │
│  /app/data                ← volume: ./data            │
└───────────────────────────────────────────────────────┘
       host :8193 ──► container :80
```

One container rather than two because this is a single-instance, self-hosted
application with a single SQLite file: splitting it would put a network hop and a
shared-volume question between nginx and uvicorn for no isolation benefit, and the
SQLite file must be reachable by exactly one writer anyway.

uvicorn binds **`127.0.0.1` only**, so nginx is the sole listener and there is no
way to reach the API without passing the directives below.

**Two-stage Dockerfile:**

1. **Build stage** — `npm ci` and `npm run build` in `frontend/`, producing `dist/`
   with all four entries.
2. **Runtime stage** — Python base, backend installed, `dist/` copied to
   `/usr/share/nginx/html`, nginx and supervisord configs installed.

Two stages so Node and the frontend's `node_modules` never reach the runtime
image.

**Compose:**

```yaml
ports:      ["8193:80"]
env_file:   .env
volumes:    ["./data:/app/data"]
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost/api/health"]
restart:    unless-stopped
```

- `./data:/app/data` holds the SQLite file, so the database survives image
  replacement. It is the only stateful mount; everything else in the container is
  disposable.
- `env_file: .env` supplies `RPHELPER_*` settings **and** the API-key environment
  variables that `"$ENV_VAR"` pointers resolve against
  (`backend-structure.md`). This is where the credential that the database
  deliberately does not contain actually lives.
- The healthcheck targets `/api/health`, which goes **through nginx to uvicorn** —
  so a healthy result means the whole chain answers, not just that nginx is up.

**`supervisord` has no wait-for ordering.** nginx will accept connections before
uvicorn is listening, so early requests get a 502. This is not worked around; it is
handled where the product already has a story for an instance that is running but
not yet usable — FEAT-001's readiness handling. Concretely: `/api/health` is the
readiness signal (`backend-structure.md`), it touches the database rather than
returning a static OK, and the bootstrap entry is built to render a
not-ready-yet state. Recorded here because "the app 502s for two seconds after
`docker compose up`" is otherwise reported as a bug.

**The `admin` entry interacts with that ordering directly, and it is the sharpest
case.** Its boot makes **one `GET /api/me` round-trip before it mounts anything at
all** (`frontend-structure.md`, `admin-surfaces.md`). Because nginx serves static
files itself and only `/api/` is proxied, nginx will happily **serve the admin
bundle while uvicorn is not yet accepting connections** — so the very first thing
the freshly-loaded bundle does is exactly the request that cannot succeed yet. The
symptom is a **blank admin page** rather than a 502 page, because the entry
deliberately renders nothing until the gate resolves.

Consequences, stated so neither is mistaken for a bug:

- **A 502 or a network failure on `/api/me` is not a deny.** The gate's deny cases
  are a 401 and a non-admin role (`admin-surfaces.md`); a transport failure or a
  5xx is **neither**, and must not redirect to `/login` — that would bounce an
  administrator out of the admin area for the two seconds after a container start,
  and the redirect would land on a login page whose own API calls fail too.
  It is rendered as a not-ready-yet state, consistent with FEAT-001's handling.
- **The window is bounded by the same healthcheck** the rest of the stack uses:
  compose's `/api/health` probe reports unhealthy until the whole chain answers, so
  an orchestrator that waits on health never routes a user into the window at all.

---

## The single-generator guarantee — one uvicorn, one node id

**Realizes:** FEAT-018, UC-061, UC-062, UC-063, UC-064

Every primary key in RPHelper is a snowflake minted in application code, and the
scheme requires **exactly one generator process per node id**. The topology above
is what supplies that today — **one container, one uvicorn process, one generator
instance held on application state** (`backend-structure.md`'s `app/ids.py`). This
doc owns the topology, so it owns the guarantee: it is a **deployment
commitment**, not a happy accident of how the container is currently started.

What it forbids, stated concretely because the change looks routine:

- **A second uvicorn worker on the same node id mints duplicate ids.** Each
  process keeps its own last-millisecond-and-sequence pair, so two workers sharing
  a node id collide the first time their inserts land in the same millisecond.
  Adding `--workers 2`, or a second replica behind the same volume, is therefore
  **not** a configuration tweak — it is the flip condition recorded against the id
  decision in `overview.md`, and the bit layout and the JSON string boundary both
  have to be re-examined before it ships.
- **The node id comes from config** — `RPHELPER_NODE_ID`, default `0`
  (`backend-structure.md`'s `Settings`). It is deliberately configurable so two
  *instances* can be given different node ids, which is what lets FEAT-018 import
  preserve ids instead of re-mapping them. Two instances left on the default `0`
  will collide, and `data-model.md` requires the importer to detect that rather
  than assume it away — so an operator running a second instance should set it.

The bit layout, the fixed epoch and the backwards-clock refusal are
`data-model.md`'s Identifiers section and are not restated here.

The corollary for SQLite is the same shape and already holds: one writer, one
file, one volume mount (`./data:/app/data`). A second instance pointed at the same
volume breaks both guarantees at once.

---

## nginx configuration — every directive, and why

### Static entries and SPA fallback

**Realizes:** FEAT-001, FEAT-002, FEAT-003, FEAT-019

One `location` block per Vite entry (four entries, `frontend-structure.md`), each
with its own fallback, plus a catch-all:

```nginx
location /bootstrap/ { try_files $uri $uri/ /bootstrap/index.html; }
location /login/     { try_files $uri $uri/ /login/index.html; }
location /admin/     { try_files $uri $uri/ /admin/index.html; }
location /app/       { try_files $uri $uri/ /app/index.html; }
location /           { try_files $uri $uri/ /index.html; }
```

Per-entry fallbacks rather than one global `/index.html` fallback, because each
entry is its own document with its own router: a deep link into `/admin/users`
must land on the **admin** document, not on the roleplayer's app document which
would then 404 the route client-side. The catch-all handles the root and anything
unmatched.

### `/api/` proxy

```nginx
location /api/ {
    proxy_pass              http://127.0.0.1:8184/api/;
    proxy_set_header        Host              $host;
    proxy_set_header        X-Real-IP         $remote_addr;
    proxy_set_header        X-Forwarded-For   $proxy_add_x_forwarded_for;

    # --- streaming (SSE) ---
    proxy_http_version      1.1;          # deviation, see below
    proxy_set_header        Connection '';# deviation, see below
    proxy_buffering         off;
    proxy_cache             off;
    proxy_read_timeout      300s;

    client_max_body_size    64m;          # deviation, see below
}
```

**Inherited and kept as-is:**

| Directive | Why |
|---|---|
| `proxy_buffering off` | nginx would otherwise buffer the SSE body and deliver tokens in bursts, destroying the streaming experience FEAT-010 depends on |
| `proxy_cache off` | an event stream must never be cached |
| `proxy_read_timeout 300s` | a long generation with several tool rounds can idle between frames for longer than the 60s default |

### Gaps in the sibling project that RPHelper closes

Each of the following is a **deliberate deviation** from BookWriter, with its
reason. They are listed as deviations rather than silently included so that a
future comparison between the two projects reads as intentional divergence, not
drift.

**1. `proxy_http_version 1.1` + `proxy_set_header Connection ''` on the `/api/`
block.**
Absent in BookWriter's **dev and prod** configs alike. nginx proxies with HTTP/1.0
and `Connection: close` by default, which is a poor fit for a long-lived streaming
response. The inconsistency worth noting: BookWriter gives careful
`Upgrade` / `Connection: upgrade` / `proxy_http_version 1.1` treatment to its
**HMR** proxy but gives its **SSE** path none of it. That inconsistency is not
worth inheriting, so the directives are applied here. `Connection ''` (empty)
rather than `keep-alive` because it clears the hop-by-hop header and lets nginx
manage the upstream connection itself.

**2. `X-Accel-Buffering: no` emitted by the FastAPI application** on streaming
responses (`backend-structure.md`).
Absent everywhere in BookWriter, which relies **solely** on nginx-level
`proxy_buffering off`. That is a single point of control: if any intermediary is
ever added — another reverse proxy, a tunnel, a corporate gateway — buffering
silently returns and the symptom is "streaming stopped working" with no
configuration change to point at. Having the application assert its own
non-buffering intent makes the requirement travel with the response. Both
mechanisms are used; they are complementary, not redundant.

**3. `client_max_body_size 64m`.**
Unset project-wide in BookWriter, so nginx's ~1MB default governs. **For RPHelper
that default would turn a product guarantee into a 413.** FEAT-009/UC-027 and
US-035.AC-2 require that an enormous paste *warns about its context cost but is
never refused* — and a 413 from nginx is a refusal, delivered before the
application ever sees the request, so no amount of application-side care can
honour the guarantee. FEAT-018 imports are the second reason: a whole-database or
per-user export is an upload, and it is not small. Set generously and deliberately.
`_TBD: 64m is a judgement, not a measured figure — docs/product/ states no size
bound, only that a paste is never refused. Raise it if a real import exceeds it;
never lower it below what US-035.AC-2 implies._`

**4. SSE directives on the dev-compose nginx too.**
BookWriter added its streaming directives only to the **prod** config, so its
dev-compose nginx path has never been hardened for streaming — meaning a developer
testing through the dev container sees buffering behaviour that production does
not have. Both configs get the same streaming treatment here. A dev environment
whose streaming behaviour differs from prod is a dev environment that cannot
reproduce the bug you care about most.

**5. Asset cache-control.**
Absent in BookWriter — hashed assets and `index.html` receive identical default
headers. Specified here:

```nginx
location ~* \.(js|css|woff2?|png|svg|jpg|webp)$ {
    add_header Cache-Control "public, max-age=31536000, immutable";
}
location ~* /index\.html$ {
    add_header Cache-Control "no-cache";
}
```

Vite emits content-hashed asset filenames, so those files are genuinely immutable
and can be cached for a year. `index.html` is **not** hashed and is the document
that references the hashed assets — so caching it is how a browser ends up
requesting an asset bundle that no longer exists after a deploy. `no-cache`
(revalidate) rather than `no-store`, because a 304 is cheap and correct.

---

## Configuration conventions

- **`pydantic-settings`**, one `Settings` model, **`RPHELPER_<FIELD>`** validation
  aliases per field, `lru_cache` singleton accessor. Full shape and reasoning in
  `backend-structure.md`.
- **The env file is resolved relative to the backend working directory**, which
  `start.ps1` and the container both set explicitly. A path relative to the module
  would break the moment the app is launched from elsewhere.
- **Ports are hardcoded literals**, not environment variables — in `start.ps1`,
  `docker-compose.yml`, the `Dockerfile` and `vite.config.ts`. The sibling
  project's convention, preserved for a concrete reason: the Vite proxy target and
  the uvicorn bind port must agree, and making both configurable creates a way for
  them to disagree while every config file still looks correct. They are topology,
  not configuration.
- **The frontend never receives a backend base-URL variable.** It always calls
  same-origin `/api/...` (`frontend-structure.md`). There is consequently no
  build-time environment difference between dev and prod bundles.
- **Secrets are never in the database.** `llm_servers.api_key_ref` holds a
  `"$ENV_VAR"` pointer resolved at call time; the variables themselves come from
  `env_file` in prod and from the backend's `.env` in dev
  (`backend-structure.md`). The operational consequence, stated in
  `data-model.md`: a restored whole-database export needs its environment supplied
  separately, because the export deliberately carries no credentials.

## Operational notes

- **Backup is a file copy.** One SQLite file under `data/`. The supported logical
  path is FEAT-018's whole-database export (UC-061); a file-level copy of the
  WAL-mode database should be taken with the application stopped, or via SQLite's
  own backup mechanism, not with `cp` on a live file.
- **The database file is the only state.** Everything else in the container is
  rebuildable from the image, and vectors are re-derivable via FEAT-005's rebuild
  (UC-016) — which is why they are not exported (`data-model.md`).
- `_TBD: no logging, metrics or alerting posture is specified. docs/product/ names
  no observability requirement, so none is designed; note that FEAT-019 constrains
  whatever is eventually added — logs must not record memo bodies or message text,
  settled, buried or current-zone alike._`
