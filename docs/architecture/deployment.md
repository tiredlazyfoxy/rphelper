# Deployment

**Realizes:** FEAT-001, FEAT-002, FEAT-005, FEAT-009, FEAT-010, FEAT-018,
FEAT-019, UC-001, UC-003, UC-016, UC-027, UC-061, US-035.AC-1, US-035.AC-2

Ports, the dev and prod topologies, every nginx directive with its reason, the
configuration conventions, and the logging posture. Build and test commands live
in the root `CLAUDE.md`.

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
designed — termination point and certificate lifecycle. Nothing in docs/product/
states an exposure model, so nothing is assumed here. Until then the deployment
target is a trusted local network._`

**The cookie half of that `_TBD:` is now a concrete change surface, not a gap.**
FEAT-002 (plan 004) has shipped the session cookie with **`Secure` off** and the
flip condition attached: TLS termination anywhere in front of the application
makes `Secure` mandatory (`backend-structure.md`'s cookie-flag table). The change
is **one function** — the cookie setter in `app/dependencies.py` — so the TLS
work has a checklist entry rather than a memory.

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
  strictPort: true,
  proxy: { "/api": "http://localhost:8184" },
}
```

**`strictPort` is on**, so a busy 8193 fails loudly rather than moving to 8194.
The `/api` proxy is the only thing connecting the frontend to the backend in dev,
and a silently relocated dev server appears to work until the first API call.

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
   `/usr/share/nginx/html`, nginx and supervisord configs installed. **The backend
   dependencies are installed from the committed `backend/uv.lock`**, never
   resolved at build time — a consequence of the uv packaging decision
   (`overview.md`): the lock is what makes the image and a developer machine run
   the same tree. Forward-looking; no feature has built an image yet.

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
- **The healthcheck asserts the HTTP status code and never the body — deliberate
  and load-bearing, not an implementation detail** (plan 003). `curl -f` fails
  only on an HTTP error status. `/api/health` answers **200 whatever its roll-up
  says** (`backend-structure.md`), so a fresh pre-bootstrap instance reporting
  `status: "degraded"`, `configured: false`, `schema: "missing"` still becomes
  **healthy** and stays reachable. **Do not "harden" it** into a check that
  inspects the body for `"status":"ok"`: a fresh instance would then be
  **permanently unhealthy**, and the rule below — an orchestrator that waits on
  health never routes a user into the window — would mean **nobody can ever reach
  the bootstrap page to configure the instance**. FEAT-001 would be made
  unreachable by the mechanism meant to protect it, and the symptom would present
  as a container fault rather than a bootstrap one. Stated here, and not only in
  `backend-structure.md`, because `fast/001.dev-and-container-harness` writes this
  healthcheck, and the invariant is visible only once `users` is in the registry.

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
  It is rendered as a not-ready-yet state, consistent with FEAT-001's handling —
  the condition is classified by the one shared predicate, `shared/notReady.ts`
  (`frontend-structure.md`).
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
  *instances* can be given different node ids, and an operator running a second
  instance should set it. **The FEAT-018 justification this bullet used to give
  is superseded**: import no longer preserves ids — US-136.AC-2 requires imported
  material to arrive under fresh identity, so the importer mints new snowflakes
  and remaps the payload's references (`data-model.md`). The setting survives as
  scheme hygiene, not as an import prerequisite.

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

#### Open seam — the `/` fallback and the app document

**The last rule above does not line up with the emitted build, and this is
recorded as a real gap rather than as silence.** The build emits exactly four
documents — `dist/bootstrap/index.html`, `dist/login/index.html`,
`dist/admin/index.html`, `dist/app/index.html` (`frontend-structure.md`'s emitted
layout) — and **no `dist/index.html`**. `location / { try_files $uri $uri/
/index.html; }` resolves against that absent file, while the `app` entry's routes
are mounted at the origin root with no basename (`frontend-structure.md`). As
written, the root case has nothing to serve.

Something must bridge `dist/app/index.html` to the root: a copy in the image
build, an nginx `root`/`alias`, or a fifth build input. **This doc does not pick
one.** Plan 002 deliberately created no root HTML document, because that would be
a fifth entry the architecture's input list does not have.

`_TBD: the mechanism that serves the app document at "/" is unchosen. Owned by
fast/001.dev-and-container-harness (roadmapped, not built), whose nginx and image
configuration it belongs to._`

**Dev-side consequence while it is unbridged:** the Vite dev server's root is
`src/`, so `http://localhost:8193/` does not resolve, and the entries are reached
at `/<entry>/index.html`.

**The `location /app/` block conflicts with the same fact, under the same
owner.** The `app` entry is mounted at the **origin root** with no basename
(`frontend-structure.md`): its routes are `/`, `/sessions/:id`,
`/characters/:id` and so on, and every cross-entry link into it is
`<a href="/">`. Nothing navigates to `/app/`, so the block above serves a URL
space the entry does not use, while the URL space it does use falls to the
catch-all. Whatever closes the `/` seam must also decide this block's fate
(drop it, or make it the source the root is bridged from). Owned by
`fast/001.dev-and-container-harness` with the seam above; **this doc does not
pick.**

#### Open seam — `/login` without a trailing slash

**`/login` (no trailing slash) is a load-bearing path, not a convenience**
(plan 004). The shared API client navigates to exactly `/login` on any 401
(`frontend-structure.md`), and FEAT-001's bootstrap refusal links to exactly
`/login`. The configured block is `location /login/ { ... }`, which does **not**
match the slash-less path — it falls to the catch-all, which is the unbridged
root seam above. The failure mode is a session expiry that lands on the wrong
document, which presents as "logging out breaks the app" and is diagnosed nowhere
near nginx.

`_TBD: the mechanism that resolves "/login" to the login document — a redirect,
a second "location = /login", or whatever the root fix turns out to be — is
unchosen. Owned by fast/001.dev-and-container-harness, with the "/" fallback
seam._`

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

---

## Logging

**Realizes:** FEAT-019, UC-065, UC-066

**This closes the observability `_TBD:` this doc used to carry.** `docs/product/`
still names no observability requirement; what follows is a technical decision
taken on top of it, and FEAT-019 is what bounds it. Metrics and alerting remain
unspecified and unbuilt — this section is logging only.

### The library — `loguru`, and the one way it fails silently

**`loguru`.** Chosen for two properties this project actually needs: **rotation
and retention are built in** (no `RotatingFileHandler` plumbing, no
`dictConfig`), and the call site is one function — `logger.info(...)` — with no
per-module `getLogger(__name__)` ceremony.

**The trade-off, stated plainly because it is the thing that can fail without
anyone noticing.** loguru is a **parallel logging system**, not a configuration
of the standard library's. `uvicorn.access`, `uvicorn.error`, SQLAlchemy and
every third-party library emit through **stdlib `logging`**, and their records
reach loguru only through an **`InterceptHandler`** installed as the stdlib root
handler, which forwards each record into loguru's sinks.

- **The `InterceptHandler` is load-bearing.** If it is missing, installed after
  uvicorn has configured its own handlers, or wired to the wrong logger,
  uvicorn's output **bypasses the rotating file entirely and nothing errors**.
- **The defect is invisible in dev.** Everything still appears on the console,
  because uvicorn's own default handler writes there. The symptom only appears
  in prod, after an incident, as an empty or half-empty log file.
- Recorded as a prohibition, not advice: a plan that adds loguru without
  installing the `InterceptHandler`, and without a test that asserts a record
  emitted through stdlib `logging` lands in loguru's sinks, has not finished the
  work.

**Flip condition.** If the `InterceptHandler` bridge proves fragile in practice,
or if structured/machine-readable logs are ever needed, the fallback is stdlib
`logging` + `dictConfig`. That was the runner-up for exactly the reason that
makes the bridge necessary — **uvicorn already uses it**, so nothing would need
bridging. The move is a rewrite of one module, not of any call site, provided
call sites stay to plain `logger.<level>("message", ...)`.

### Two sinks

| Sink | Default level | Destination |
|---|---|---|
| Console | `DEBUG` | **stderr** — captured by `supervisord` in prod, the terminal in dev |
| Rotating file | `WARNING` | `data/logs/rphelper.log` |

Both levels are configurable (below). The console is deliberately the noisy one
and the file the quiet one: the console is ephemeral and read while working, the
file is durable and read after something went wrong.

**Why `data/logs/`.** `data/` is the **only writable volume in prod** — the
compose mount is `./data:/app/data`, and everything else in the container is
rebuildable from the image. A log path anywhere else is lost on every redeploy.
It is therefore the second directory under `data/`, beside the SQLite file, and
the operational notes below carry the consequence.

**Configuration happens once, at application startup, in one module** —
`app/logging.py`, called from `main.py`'s app factory before routers are
registered, so that a failure during registration is already captured. It sits
beside `config.py`, `ids.py` and `secrets.py` as infrastructure, not under
`services/` (`backend-structure.md`'s reasoning for `ids.py` applies unchanged).
Nothing else in the codebase adds, removes or reconfigures a sink.

### Settings

Ordinary `pydantic-settings` fields on the one `Settings` model, with explicit
`RPHELPER_` validation aliases like every other field. The model's full shape and
the reasoning for the convention are in `backend-structure.md`; these are the
five fields it gains:

| Variable | Default |
|---|---|
| `RPHELPER_LOG_CONSOLE_LEVEL` | `DEBUG` |
| `RPHELPER_LOG_FILE_LEVEL` | `WARNING` |
| `RPHELPER_LOG_FILE_PATH` | `data/logs/rphelper.log` |
| `RPHELPER_LOG_FILE_ROTATION` | `"10 MB"` |
| `RPHELPER_LOG_FILE_RETENTION` | `5` |

`rotation` and `retention` are passed to loguru's file sink as-is — a size string
and a file count. They are settings rather than constants because a self-hosted
operator with a small volume and one with a large one want different answers, and
neither is a topology fact the way a port is.

### The redaction rule — a prohibition, with no level exception

**FEAT-019 constrains logging absolutely.** This is written as a prohibition
rather than a guideline because it is enforceable only as one.

**No log record, at ANY level including `DEBUG`, may contain:**

- message text — settled, buried or current-zone alike;
- memo bodies;
- character persona / sheet text;
- setup text;
- session titles or partner labels;
- translations;
- LLM prompt payloads;
- LLM completions;
- API keys or resolved secret values.

**Allowed, and sufficient to debug with:**

- **snowflake ids**, written as decimal **strings** — the JSON id boundary
  (`backend-structure.md`) does not formally reach a log line, but write them as
  strings anyway so a line can be pasted straight into a query;
- error codes from the typed error table (`backend-structure.md`);
- model references and tool names;
- token counts, row counts, durations, HTTP status.

**Why there is no level exception.** A rule conditioned on level — "no message
text above `DEBUG`" — is violated the first time somebody adds a log line without
checking which level it is under, and the violation is invisible until a `DEBUG`
console is turned on in prod or a file level is lowered during an incident. **A
single unconditional rule is the only one that survives review.** The cost is
real and is accepted: debugging is done by logging the **id** and opening the row
in SQLite, not by logging the text.

Concrete shapes, so a coder can pattern-match. **Allowed:**

```
compose start session=7250416938275332095 model=llamaswap/qwen3-30b
tool_failed tool=memo_search code=no_embedding_model session=7250416938275332095
settle session=7250416938275332095 rows=3 kind=turn
translate cached=false message=7250416938275332096 status=200 ms=812
```

**Forbidden**, each an instance of the list above:

```
compose prompt=<the assembled system prompt>
settle text="He turned away without answering."
memo saved body="the innkeeper is calledВарда"
llm request api_key=sk-...
```

**`detail` and log lines are bound by the same privacy rules.** R5 already
forbids a `detail` carrying another user's data or a count derived from it, and
R3 forbids memo body text for a note where `is_enabled` is false. A log line is
the same kind of outbound surface and is bound the same way — more strictly, in
fact, since the list above forbids *all* memo bodies rather than only disabled
ones.

### loguru's `diagnose` / backtrace must be off for the file sink

loguru's exception formatting can print **local variable values** alongside a
traceback. That would defeat the rule above the moment an exception is raised
inside a function holding message text, a memo body or a resolved API key —
which is most of the compose path. **`diagnose=False` on the file sink**, and the
`backtrace` frame expansion is not what makes a traceback useful here anyway; the
frames are.

Named explicitly because `diagnose=True` is loguru's own default in several
configurations and reads as a debugging convenience rather than as a data-leak
path.

---

## Operational notes

- **Backup is a file copy, and `data/` now holds two things.** The SQLite file
  and `data/logs/`. The supported logical path for the database is FEAT-018's
  whole-database export (UC-061); a file-level copy of the WAL-mode database
  should be taken with the application stopped, or via SQLite's own backup
  mechanism, not with `cp` on a live file. **A whole-database export carries no
  logs** — the export's payload is tables (`data-model.md`), so logs are backed
  up only by copying the directory, and an export-based restore starts with an
  empty log.
- **The database file and the log directory are the only state.** Everything
  else in the container is rebuildable from the image, and vectors are
  re-derivable via FEAT-005's rebuild (UC-016) — which is why they are not
  exported (`data-model.md`).
- **The vector-rebuild remedy requires a running application.** UC-016's rebuild
  is reachable only through the Database page's button (`admin-surfaces.md`);
  there is **no standalone recalc-vectors CLI script**, considered and declined
  so that one surface owns the operation rather than two that can diverge. The
  consequence is worth stating because it is exactly backwards from when you
  want it: the remedy is unavailable precisely when the app will not start.
