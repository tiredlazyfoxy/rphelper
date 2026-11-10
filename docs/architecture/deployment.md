# Deployment

**Realizes:** FEAT-001, FEAT-002, FEAT-005, FEAT-009, FEAT-010, FEAT-011,
FEAT-016, FEAT-018, FEAT-019, UC-001, UC-003, UC-016, UC-027, UC-061, UC-065,
UC-066, US-035.AC-1, US-035.AC-2

Ports, the dev and prod topologies, every nginx directive with its reason, the
build-and-deploy flow, the configuration conventions, and the logging posture.
Build and test commands live in the root `AGENTS.md`.

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

**Known constraint, inherited and preserved:** the host-run Vite dev server and
the dev compose publish **the same number** (8193), and so does the prod compose's
nginx. Run one at a time — the second one to start fails to bind. This is
deliberate in the sibling project (the container and the host dev server are two
ways of serving the same thing on the same URL) and is kept, but it is a trap
worth writing down rather than rediscovering.

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

### The HTTP-only posture's first visible feature consequence — copy-out

**`navigator.clipboard` does not exist on a non-secure origin**, and every LAN
address this instance is reached at today is a non-secure origin. So the one
operation that crosses the product's outbound boundary — copying a settled turn
out (UC-030, UC-082, US-033.AC-1) — cannot rely on the modern clipboard API at
all: `app/copyOut.ts` falls back to **`execCommand("copy")`** whenever
`navigator.clipboard` is absent (014 D9, `workspace-shell.md`).

Recorded here rather than only beside the control, because it is the **first
place the HTTP-only posture above shows up as a feature decision** rather than as
an operational note. Two consequences follow:

- `execCommand("copy")` is deprecated and is carried deliberately, not by
  oversight. A plan that removes it on the strength of the deprecation breaks
  copy-out on every LAN deployment, and the symptom is a silent clipboard
  failure on the product's main flow. The failure path is visible —
  `notifyFailure` on a clipboard error (`ui-conventions.md`) — but a removed
  fallback would fail on *every* copy, not occasionally.
- **When TLS lands, the fallback becomes dead code.** On a secure origin
  `navigator.clipboard` is always present, so the `execCommand` branch stops
  being reachable and can be deleted. That makes it a checklist entry for the TLS
  work above, beside the cookie's `Secure` flag: two things to change, in two
  named places, rather than a search.

---

## Dev topology

**Three launch paths, one shape.** Each runs the same pair — uvicorn with
`--reload` on 8184 and the Vite dev server on 8193 — and differs only in how the
pair is started:

| Launch path | How the pair runs |
|---|---|
| `start.ps1 -app` (or `-api`) + `start.ps1 -ui` (or `-web`) | two invocations in **two terminals** |
| `start.sh` | **one terminal**, both servers |
| `docker-compose.yml` — the dev compose, started with plain `docker compose up` | the `start.sh` pair in stock images — `api` in `ghcr.io/astral-sh/uv`, `ui` in `node:22` — with the repo bind-mounted |

The dev compose holds the standard compose file name so the local default is plain
`docker compose up`; the prod compose is `docker-compose.prod.yml` ("Prod
topology" below, `DEC-F013-4`).

```
browser ──► Vite :8193 ──/api──► uvicorn :8184 ──► ./data/rphelper.sqlite
                         proxy
```

`start.ps1` keeps its two flags as **separate invocations in separate
terminals**: each process has its own reload behaviour and its own log stream,
and separate consoles keep a backend traceback and a Vite compile error apart.
`start.sh` is the one-terminal alternative for when that separation is not
wanted. Both launchers resolve the backend and frontend directories from their
own location, not from the caller's working directory (`DEC-F001-9`).

**The dev compose runs no nginx** (as of commit `06baac6`). It runs the
`start.sh` pair, so its routing is Vite's, exactly as on the host. The `ui`
service **shares `api`'s network namespace**, which is why the `/api` →
`localhost:8184` proxy below works unchanged inside the containers, and why
**8193 is published on `api`**, not on `ui`. There is therefore **one nginx
configuration, the prod one**; dev streaming goes through Vite's proxy.

**Port 8193 is shared by all three paths.** Run one launch path at a time; the
second to start fails to bind (`strictPort`, below).

**The app answers at `http://localhost:8193/` in all three paths**, and every
other entry at `/<entry>/`, through the serve-only Vite routing plugin described
in "The app document at `/` — prod and dev" below. Dev and prod share one URL
space.

Vite proxy configuration — **one prefix only**:

```ts
server: {
  port: 8193,
  strictPort: true,
  proxy: {
    "/api": { target: "http://localhost:8184", configure: configureProxyLogging },
  },
}
```

The rule is in **object form** only so it can carry the dev request logger's hook
(below); it is still one prefix and the same target.

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
dev and prod routing to diverge. **The dev routing plugin runs before the proxy in
the dev server's chain and passes `/api` through untouched**, so it never alters
what the proxy sees.

**HMR rides the ordinary route.** The config sets no `server.hmr.path`, so the
HMR websocket goes over the same origin and port as everything else. There is no
separate HMR port to publish, proxy or firewall.

### The dev request log — one line per request on the `[ui]` stream

The Vite process prints **one line for every HTTP request the dev server
receives** to its stdout — the `[ui]` stream under `start.sh`:

```
<METHOD> <path> <status> <ms>ms          GET /api/sessions 200 12ms
<METHOD> <path> proxy error <CODE>       GET /api/sessions proxy error ECONNREFUSED
```

No prefix, colour or timestamp — the launcher's prefix already names the stream
(`DEC-F007-1`). Two loggers split the work so each request gets **exactly one
line**:

| Requests | Logged by | Timed to |
|---|---|---|
| everything under `/api` | the proxy's logger, attached through the `/api` rule's hook (`frontend/dev/proxyLog.ts`) | the **response headers** — so a streaming compose logs when it opens, not when it ends or never (`DEC-F007-2`) |
| everything else — pages, modules, assets, the dev server's internals | a serve-only middleware registered **first** in the dev server's chain (`frontend/dev/requestLog.ts`) | the **response end**; a request the client aborted shows `-` as its status (`DEC-F008-3`) |

- **The split is one shared prefix test.** The middleware skips exactly what the
  proxy claims — the same "starts with `/api`" match — so the two can never both
  log a request or both miss it (`DEC-F008-2`).
- **Both attach silently and never throw.** The proxy hook and the middleware's
  registration both run under Vitest too, because Vitest creates a dev server
  from the same config; attaching must therefore produce no output and no error
  (`DEC-F007-6`, `DEC-F008-5`). Neither affects `vite build`.
- **HMR websocket upgrades are not logged** — they never pass through the
  request middleware chain.
- **Both lines are access-log lines under the redaction rule** — path only
  ("Access-log lines record the path without its query string", below).

The backend's own access log (`[api]`) is separate and unchanged.

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

**The files, as built** (fast/001.dev-and-container-harness, compose layout
revised by fast/013.build-and-deploy-scripts): the root `Dockerfile`, the prod
compose `docker-compose.prod.yml`, and under `docker/` the nginx config
(`nginx.conf`) and the supervisord config (`supervisord.conf`). The nginx file is
a **server-level config** installed in place of the base image's default site,
so one server answers `:80` and the base image's main config is never edited.
Base images and install paths are `DEC-F001-7`.

**`supervisord` starts exactly one uvicorn, with no worker count and no reload,
beside nginx in the foreground** — the single-generator guarantee below, made
concrete. `backend/tests/test_deployment_files.py`, the deployment file-contract
test, guards the single process (`DEC-F001-8`).

**Two-stage Dockerfile:**

1. **Build stage** — `npm ci` and `npm run build` in `frontend/`, producing `dist/`
   with all four entries; then the presence check and the root-document copy
   ("The app document at `/`" below).
2. **Runtime stage** — Python base, backend installed, `dist/` copied to
   `/usr/share/nginx/html`, nginx and supervisord configs installed. **The backend
   dependencies are installed from the committed `backend/uv.lock`**, never
   resolved at build time — a consequence of the uv packaging decision
   (`overview.md`): the lock is what makes the image and a developer machine run
   the same tree.
   **The backend has a git dependency** — the `llm-client` library, pinned to
   its `v0.2.1` tag on GitHub (`llm-and-streaming.md`, 2026-11-08; 0.2.1 from
   2026-11-09, `DEC-arch-llm-client-library-13`). The lock
   pins its revision, but `uv sync` still fetches it from the repository, so the
   stage that installs the backend **needs `git` and network access to
   github.com**. A build environment without either fails at dependency
   installation, not at runtime.

Two stages so Node and the frontend's `node_modules` never reach the runtime
image.

**Compose** — `docker-compose.prod.yml`, **image-based**:

```yaml
image:      iezious/rphelper:latest
ports:      ["8193:80"]
env_file:   .env
volumes:    ["./data:/app/data"]
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost/api/health"]
restart:    unless-stopped
```

- **Prod is deployed from a pre-built image, never built on the server.** The
  prod compose has no `build:` key and is never run from the repository: the
  build flow below stages it into the store under the standard name
  `docker-compose.yml`, because on the server it is the only compose file
  (`DEC-F013-4`).
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
  `backend-structure.md`, because the invariant is visible only once `users` is in
  the registry. **The healthcheck lives in `docker-compose.prod.yml`, with a
  comment carrying this rule beside it.**

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

### Build and deploy

**The image is built on a developer machine, shipped through a shared store as an
archive, and started on the server from that archive.** Two scripts at the repo
root carry the flow (fast/013.build-and-deploy-scripts):

```
developer machine                    $DOCKER_STORE/rphelper/               server
build.sh ─► image :latest + :X.Y.Z ─► rphelper-latest.7z     ─► deploy.sh ─► docker compose up -d
                                     docker-compose.yml (= prod compose)
                                     deploy.sh
```

**`build.sh`:**

- **The version comes from git: HEAD must carry exactly one `vMAJOR.MINOR.PATCH`
  tag.** None fails the build; two or more fail as ambiguous — the build never
  guesses which version it ships (`DEC-F013-1`, `-2`).
- **The tag is resolved on the host, not inside the image build**, because the
  image's build context excludes `.git` — nothing in the Dockerfile can see a tag.
- The image is tagged **`iezious/rphelper:latest` and `iezious/rphelper:<version>`**
  (the tag without its `v`), and the archive carries both references, so the
  server's load restores both.
- **The archive is written atomically**: to a temporary name inside the store,
  renamed to `rphelper-latest.7z` only after the save and compression succeeded.
  A failed build never leaves a truncated archive where deploy would load it, and
  the archiver adds to an existing archive rather than replacing it, so writing
  straight over the last build's archive would be wrong even on success
  (`DEC-F013-6`).
- It stages the prod compose (as `docker-compose.yml`) and `deploy.sh` into the
  store beside the archive.

**The store is `$DOCKER_STORE/rphelper`.** `DOCKER_STORE` is required on both
machines and both scripts refuse to run without it; a trailing slash on it is
harmless. The build creates the store directory; deploy requires it to exist,
because a missing store on the server is a misconfiguration, not something to
create (`DEC-F013-3`).

**`deploy.sh` mirrors the sibling project's update script**: modes
`--images | --config | --all` (default all) and `--no-restart`. Images mode loads
the archive into docker; config mode copies the store's compose file next to the
script; then the `data/` directory is ensured, the stack is brought up detached,
unused images are pruned, and the service status is printed. Every precondition
is checked before any docker call, and images are loaded before the compose file
that names them is copied (`DEC-F013-7`).

**Deliberate deviation from BookWriter: no `.env` templating.** BookWriter's
deploy creates `.env` from `.env.example` when it is missing. RPHelper's never
writes `.env` and **refuses to restart the stack without one**: secrets are placed
on the server by hand, and a template would start the stack with placeholder
credentials — a running instance that looks deployed and cannot do anything. The
compose file's `env_file: .env` would fail anyway; an early, named refusal is the
clearer failure (`DEC-F013-5`).

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
  have to be re-examined before it ships. The deployment file-contract test fails
  such a change to the supervisord config ("Prod topology" above).
- **The node id comes from config** — `RPHELPER_NODE_ID`, default `0`
  (`backend-structure.md`'s `Settings`). It is deliberately configurable so two
  *instances* can be given different node ids, and an operator running a second
  instance should set it. **The FEAT-018 justification this bullet used to give
  is superseded**: import no longer preserves ids — US-136.AC-2 requires imported
  material to arrive under fresh identity, so the importer mints new snowflakes
  and remaps the payload's references (`data-model.md`). The setting survives as
  scheme hygiene, not as an import prerequisite.

The bit layout, the fixed epoch and the backwards-clock tolerance and refusal are
`data-model.md`'s Identifiers section and are not restated here.

The corollary for SQLite is the same shape and already holds: one writer, one
file, one volume mount (`./data:/app/data`). A second instance pointed at the same
volume breaks both guarantees at once.

---

## nginx configuration — every directive, and why

### Static entries and SPA fallback

**Realizes:** FEAT-001, FEAT-002, FEAT-003, FEAT-019

One prefix `location` per non-root Vite entry (`frontend-structure.md`), each with
its own fallback; one exact-match redirect per slash-less entry path; and a
catch-all that serves the `app` document:

```nginx
absolute_redirect off;                       # server level — relative Location headers

location /bootstrap/ { try_files $uri $uri/ /bootstrap/index.html; }
location /login/     { try_files $uri $uri/ /login/index.html; }
location /admin/     { try_files $uri $uri/ /admin/index.html; }

location = /bootstrap { return 302 /bootstrap/; }
location = /login     { return 302 /login/; }
location = /admin     { return 302 /admin/; }

location /           { try_files $uri $uri/ /index.html; }   # index.html = the app document
```

Per-entry fallbacks rather than one global `/index.html` fallback, because each
entry is its own document with its own router: a deep link into `/admin/users`
must land on the **admin** document, not on the roleplayer's app document which
would then 404 the route client-side. The catch-all handles the root, every `app`
client route and anything unmatched.

**Every redirect nginx emits is relative.** The container listens on `:80` but is
published on `8193`, so an absolute `Location` built from the listening port would
send the browser to a port nothing on the host answers (`DEC-F001-4`).

**There is no `location /app/`** (`DEC-F001-2`). The `app` entry is mounted at
the **origin root** with no basename (`frontend-structure.md`): its routes are
`/`, `/sessions/:id`, `/characters/:id` and so on, and every cross-entry link
into it is `<a href="/">`. Nothing navigates to `/app/`, so a block for it would
serve a URL space the entry does not use. Without one, `/app/...` falls to the
catch-all, which serves the same document, so nothing breaks.

#### The app document at `/` — prod and dev

**Decided (user-confirmed 2026-10-07).** The `app` entry's document answers at
the **origin root `/`** and on every one of its client routes (`/sessions/:id`,
`/characters/:id`, …), in **both dev and prod**. **`/app/` is not a user-facing
URL.** The other three entries are reached at `/bootstrap/`, `/login/` and
`/admin/`, deep links included. Slash-less `/bootstrap`, `/login` and `/admin`
get a **relative 302** to the slash form. **Dev routing mirrors prod nginx
routing exactly.**

Why: there is **one URL space** in dev and prod. The `app` entry is root-mounted
with no basename (`overview.md`, `frontend-structure.md`), so a reload, a deep
link, or the client's 401 navigation to `/login` must behave the same on :8193 in
dev as it does in prod. A dev server that answers a different URL space is a dev
server that cannot reproduce a routing bug.

**The routing contract both environments satisfy** (HTML navigations only):

| Request | Answer |
|---|---|
| `/bootstrap`, `/login`, `/admin` (exact, no slash) | **302**, relative `Location` to the slash form |
| `/bootstrap/…` not resolving to a file | `bootstrap/index.html` |
| `/login/…` not resolving to a file | `login/index.html` |
| `/admin/…` not resolving to a file | `admin/index.html` |
| any other navigation — `/`, `/sessions/:id`, `/characters/:id`, … | the **app** document (`app/index.html`) |
| `/api/…` | the backend — untouched by this routing |
| a module or asset request, or a file that exists | served as-is — untouched by this routing |

**Prod mechanism — as built by `fast/001.dev-and-container-harness`.** The
build still emits exactly four documents (`frontend-structure.md`'s emitted
layout). The Docker frontend stage **fails the build if any of the four
`dist/<entry>/index.html` is missing**, then **copies `dist/app/index.html` to
`dist/index.html`**, and the catch-all above serves it for `/` and for every app
client route. The copy is an image-build step, not a fifth build input: plan 002
deliberately created no root HTML document, and that still holds. The build-time
presence check exists so a missing entry fails the image rather than a page load
(`DEC-F001-1`).

**Dev mechanism — as built by `fast/009.vite-dev-root-routing`.** It applies to
the Vite dev server on :8193 under all three dev launch paths (`start.sh`,
`start.ps1 -ui`, the dev compose; "Dev topology" above). It lives in
**`frontend/dev/entryRouting.ts`**, a dev-only Vite plugin
(`rphelper-dev-entry-routing`) wired after the request-log plugin
(`DEC-F009-1`).

- The plugin is **serve-only** (`apply: "serve"`), and its `configureServer`
  registers a middleware **directly** — not in a returned post-hook — so it runs
  **before Vite's internal middlewares**, the proxy included.
- The middleware **rewrites the request URL** of HTML navigations, per the table
  above: an exact slash-less `/bootstrap|/login|/admin` gets the 302; a
  `/bootstrap/…`, `/login/…` or `/admin/…` path that does not resolve to a file is
  rewritten to that entry's `/<entry>/index.html`; any other navigation is
  rewritten to `/app/index.html`.
- **The predicate is path-only, like nginx's `try_files`.** Only GET and HEAD are
  routed. `/api`, the dev server's internal URLs (`/@…`, `/__…`,
  `/node_modules/…`), any path carrying a file extension, and any path naming an
  existing file pass through untouched. There is **no `Accept` or fetch-metadata
  gating**: a module request looks like a navigation by its headers, so a
  header-based predicate would misroute it. The browser's own URL and query are
  kept on the request; the rewritten URL carries no query. **On an internal error
  the request passes through unchanged.** The exact predicate is `DEC-F009-2`.
- **Rewrite, not redirect.** The browser URL stays `/` (or the deep link), and
  Vite's own HTML transform still runs on the rewritten document and injects the
  HMR client. A redirect to `/app/` would put the root-mounted, basename-less app
  router at a path it does not mount, which is a client-side 404.
- **The same plugin owns a `transformIndexHtml` hook that makes each entry
  document's relative module-script `src` absolute**, resolved against the
  served document's directory: `./main.tsx` in `/app/index.html` becomes
  `/app/main.tsx`. Vite's own transform does not do this for us — in Vite 8.3.1
  it adjusts a relative `src` only for `/index.html`, so the entry's
  `<script type="module" src="./main.tsx">` reaches the browser verbatim. Without
  the hook, the browser resolves it against the URL it navigated to: `/` requests
  `/main.tsx`, `/sessions/5` requests `/sessions/main.tsx`, and the document
  served at `/` or at a deep link loads its module from the wrong path. **Removing
  the hook breaks `/` in dev silently**, as a module 404. Only module scripts are
  rewritten (`DEC-F009-3`). Because the plugin is serve-only, the entry HTML files
  keep their relative `src` and `vite build` is unaffected — the build already
  emits absolute hashed `/assets/…` URLs.

**Unchanged by the dev mechanism, deliberately:** Vite's `root` stays `src/`;
the four build inputs stay as they are; there is **no fifth input** and **no
`src/index.html` or `frontend/index.html`**. `frontend/tests/build-config.test.ts`
asserts the root and the four inputs. **The plugin must not affect
`vite build`** — `apply: "serve"` is what guarantees that, and the emitted layout
above is the build's only contract with nginx.

**The dev-side note fast/001 once proposed — that host Vite does not serve `/` —
is superseded by this mechanism.** How that reading arose is recorded in
"Decision history" at the bottom of this doc.

#### Slash-less entry paths — `/login` is load-bearing

**`/login` (no trailing slash) is a load-bearing path, not a convenience**
(plan 004). The shared API client navigates to exactly `/login` on any 401
(`frontend-structure.md`), and FEAT-001's bootstrap refusal links to exactly
`/login`. A prefix `location /login/` does **not** match the slash-less path, and
without a rule of its own it would fall to the catch-all and land on the app
document. The failure mode would be a session expiry that lands on the wrong
document, which presents as "logging out breaks the app" and is diagnosed nowhere
near nginx.

**Resolved by an exact-match redirect**: `/login` answers a **302** to `/login/`,
and `/bootstrap` and `/admin` do the same for consistency (`DEC-F001-3`). The
redirect lands on the entry's **canonical URL** — the same one the dev server
serves — so the prefix fallback and the `index.html` no-cache rule apply
unchanged. **302, not 301**, so browsers do not pin it; the extra round trip on a
401 is negligible. The dev routing plugin answers the same paths the same way.

### `/api/` proxy

```nginx
location ^~ /api/ {
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

**Every `/api/` request reaches this block, whatever its suffix.** nginx lets a
matching regex location outrank a plain prefix, so the asset cache-control
regexes below would otherwise claim an `/api/` path that happens to end like an
asset; the prefix is declared so that regex matching stops once it matches
(`DEC-F001-5`).

**Inherited and kept as-is:**

| Directive | Why |
|---|---|
| `proxy_buffering off` | nginx would otherwise buffer the SSE body and deliver tokens in bursts, destroying the streaming experience FEAT-010 depends on |
| `proxy_cache off` | an event stream must never be cached |
| `proxy_read_timeout 300s` | a long generation with several tool rounds can idle between frames for longer than the 60s default |

**`proxy_read_timeout 300s` is shorter than the LLM timeout, and both are kept
(user decision, 2026-11-08).** Since the move to the `llm-client` library the LLM
timeout is a total per request — per tool round for a compose — at 600 s
(`llm-and-streaming.md`'s timeout section). nginx's read timeout is measured
between frames, so a compose round that sends **no frame for over 300 s** is cut
by nginx before the library's 600 s fires. The user judges that an extreme case
and not relevant in practice: the 600 s is a **ceiling, not an expected
duration**, and a round that streams tokens resets nginx's clock with every
frame. **Flip condition:** observed cuts of legitimately slow rounds — then the
two timeouts are revisited together.

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

**The import is built now, and this limit is its practical bound** (plan 031).
The upload is a **JSON body, not multipart**, and it is **held fully parsed in
memory** (`transfer.md`), so `client_max_body_size` is the only ceiling an import
meets — there is no streaming parse underneath it that would tolerate more.
**Flip condition:** an export that exceeds 64m in practice means either raising
the limit or moving to a streamed upload, and the second is the real fix if the
memory posture becomes the binding constraint rather than nginx.

**4. ~~SSE directives on the dev-compose nginx too~~ — superseded, no dev nginx
exists.**
BookWriter added its streaming directives only to its **prod** config, so its
dev-compose nginx was never hardened for streaming. This deviation used to give
RPHelper's dev-compose nginx the same treatment. **The dev compose now runs no
nginx at all** ("Dev topology" above): there is one nginx configuration, the
prod one, so a dev/prod streaming divergence in nginx cannot arise. Dev
streaming goes through Vite's proxy. Kept as a numbered entry so the five
deviations keep their numbers.

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
- **The root `.env.example` is the documented variable list.** It names every
  variable `Settings` reads, and a deployment file-contract test checks it against
  the `Settings` aliases, so a new setting without a documented variable fails the
  build rather than surprising an operator.
- **The env file is resolved relative to the backend working directory**, which
  `start.ps1` and the container both set explicitly. A path relative to the module
  would break the moment the app is launched from elsewhere.
- **Ports are hardcoded literals**, not environment variables — in `start.ps1`,
  `start.sh`, the dev compose `docker-compose.yml`, the prod compose
  `docker-compose.prod.yml`, the `Dockerfile` and `vite.config.ts`. The sibling
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
  **The web-search API key is a second secret that is not a pointer either**, for
  the opposite reason: it never goes near the database at all, so it lives only in
  the environment (next bullet, and `backend-structure.md`'s `$ENV_VAR` section).
- **Web search takes two environment variables, and they do NOT carry the
  `RPHELPER_` prefix** (plan 028, D2, D3):

  | Variable | Holds |
  |---|---|
  | `SEARCH_CSE_KEY` | the Google Custom Search API key — a secret-string type, **masked in `repr`** |
  | `SEARCH_CSE_ID` | the custom search engine id (`cx`) |

  Both are **optional with no default**, read from the environment like every
  other setting (`env_file` in prod, the backend's `.env` in dev). **When either
  is missing or blank, web search is simply not offered** — no error, no startup
  failure, no degraded mode: the tool is absent from the registry the request
  builds (`llm-and-streaming.md`). An instance that never configures them behaves
  exactly as one whose roleplayers all switched the tool off.

  **The missing `RPHELPER_` prefix is a named deliberate exception, not an
  oversight** (028 U2, user-confirmed). These are **the user's existing
  environment variable names**, already set on the machines this runs on. The
  explicit-alias rule still holds — each field names its variable, so the
  environment contract stays greppable — and **only the prefix differs**. Written
  down so that nobody "fixes" the two aliases to `RPHELPER_SEARCH_CSE_KEY` and
  `RPHELPER_SEARCH_CSE_ID`: that change breaks nothing loudly, it **silently
  unconfigures web search** on every instance that was working, and the symptom
  is a tool quietly no longer being offered.
- **LLM-library tracing takes two environment variables, `LLM_TRACE` and
  `LLM_TRACE_FOLDER`, and both must stay unset in any shared deployment**
  (2026-11-08, user decision). They are read by the `llm-client` library itself,
  not by `Settings`. When both are set, the library writes **full prompts,
  histories, tool arguments and tool results** to files in that folder. RPHelper
  does not disable this: it is an **operator's debug switch, off by default, for
  debugging on their own instance only**. It is **privacy-breaking by design** —
  it bypasses the redaction rule below and the privacy audit, and the files it
  writes hold exactly the roleplayer material that rule forbids in a log
  (`llm-and-streaming.md`). The prefixless names are the library's, not a second
  exception to the `RPHELPER_` convention.
- **`DOCKER_STORE` is a build-and-deploy variable, not an application setting.**
  It is read only by `build.sh` and `deploy.sh` ("Build and deploy" above), on
  both machines, and never reaches the container.

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
- **session names** (`sessions.name`) — a real column since the session-names
  delta (2026-11-05), so this entry now has a call site: the rename route and
  my-search's name arm both handle the text, and neither may log it — log the
  session id instead. A name is the roleplayer's own words about their
  roleplay, exactly as much content as a persona. **Partner labels** stay on the
  list although `sessions` still has no such column: if one ever lands it is
  already covered rather than needing this list to be remembered and extended;
- translations;
- LLM prompt payloads;
- LLM completions;
- **web-search queries** — they are composed from message text, so a query is
  message text by another name (plan 028);
- **web-search results**;
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
translate cached=false message=7250416938275332096 ms=812
translate cached=false message=7250416938275332096 ms=812 written=false
translate failed message=7250416938275332096 code=translation_failed
```

**The translate line as built has no `status=` field** (023 D4): the translation
service has no HTTP status to report — it is a service, not a handler — and the
earlier example here carried one. It gains **` written=false`** when the
disconnect check skipped the cache write (`llm-and-streaming.md`), which is the
one thing that distinguishes a skipped write from a cache miss in the log.

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

#### Third-party request logs are in scope, and a URL can carry message text

**The rule binds records this codebase never wrote.** `configure_logging`
installs an `InterceptHandler` as the stdlib root handler (above), so **every
library's records land in both sinks** — including an HTTP client's own request
log, which logs a URL.

That became concrete with plan 028: it is the first feature to put message text
in a **query string** (`q=<the roleplayer's query>`), and `httpx`'s own request
record was carrying it at `DEBUG`. The mechanism that holds the line is named in
`backend-structure.md`: **`app/logging.py` owns third-party logger suppression**
(`_SILENCED_LOGGERS` beside `_PROPAGATING_LOGGERS`) and **no service module may
touch a third-party logger** — otherwise the redaction surface would depend on
import order.

#### Access-log lines record the path without its query string

**A filter on the `uvicorn.access` logger strips the query string** (plan 032,
step 001), because a query string can carry user text — `GET /api/search?q=…` is
the live example (029). The path is kept, because the path is what an operator
needs; the arguments are what they must not have.

This was the **first leak plan 032 found**, and it is worth seeing why it is easy
to miss: nobody writes an access log line, so nobody reviews one against this
section's forbidden list. **So every access-log surface is named here**, and each
has its check:

| Surface | Rule | Check |
|---|---|---|
| uvicorn's access log | the filter above strips the query string | `backend/tests/test_logging_redaction.py` |
| **nginx's access log** (prod) | a **path-only format** — never the query string, never the full request line | `backend/tests/test_deployment_files.py` |
| **the dev proxy's request line** (`/api`, dev only) | path only, cut at the first `?` and any `#`; no headers, cookies, bodies or upstream URL; an error line carries the error's **code** only, never its message | `frontend/tests/proxy-log.test.ts` |
| **the dev server's request line** (everything else, dev only) | the same path-only rule; no headers, cookies or bodies | `frontend/tests/request-log.test.ts` |

**nginx's access log, as built** (fast/001.dev-and-container-harness,
`DEC-F001-6`): the config logs with a path-only format, and the access-log
declaration sits at the level that **replaces** the base image's inherited
default rather than adding to it. That placement is load-bearing: the base
image's main config declares its own access log, which records the full request
line, query string included, and same-level declarations add up — **moving ours
up to file level silently reintroduces query strings**. No `location` declares an
access log of its own, since that would replace the path-only one for that
location, and the base image's main config is never edited. The file-contract
test checks the format, the placement and the absence of base-config edits. The
`_TBD:` this section used to carry for nginx is **closed**.

#### SQL parameters never reach a log line — defence in depth

Two settings rather than one, because a bound value can escape by two routes:

- **The engine is built with bound parameters hidden**, so a rendered statement
  in an exception message carries placeholders rather than values.
- **The `sqlalchemy` loggers stay at WARNING or above**, so statement echoing
  never turns itself on.

Either alone would be enough on a good day; both are set because a SQLite error
text can embed a column **value** (`backend-structure.md`'s 500 posture makes the
same point for `schema_apply_failed`'s `detail`), and a value here is the
roleplayer's prose.

#### The rule is proved, not only stated

Two enforcement tests, named so a change to this section comes with a check:
**`backend/tests/test_logging_redaction.py`** and
**`backend/tests/test_privacy_audit_logs.py`**, the second a **dynamic sentinel
sweep at level 0** — it drives the application with recognisable content and
asserts the sentinels appear in no record at any level. A prohibition that is only
written down is a prohibition that drifts; this one fails a build. The access-log
surfaces above add their own checks, one per surface.

### loguru's `diagnose` and `backtrace` must be off on **every** sink

loguru's exception formatting can print **local variable values** alongside a
traceback. That would defeat the rule above the moment an exception is raised
inside a function holding message text, a memo body or a resolved API key —
which is most of the compose path.

**So `diagnose=False` and `backtrace=False` on both sinks — the rotating file
*and* the console/stderr.** The `backtrace` frame expansion is not what makes a
traceback useful here anyway; the frames are.

**This was broadened from the file sink alone, and the reason is a real leak**
(plan 032, step 001). The console sink kept loguru's default `diagnose=True` and
was printing traceback locals into console output — which in prod is
`supervisord`'s captured stream, i.e. a durable operator-facing log. "The file
sink is the durable one" was the assumption behind the narrower rule, and it was
wrong.

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
- **A restored export needs the search credentials supplied with the rest of the
  environment**, if web search is wanted: `SEARCH_CSE_KEY` and `SEARCH_CSE_ID`
  live only in the environment and are in no export, exactly like the
  `"$ENV_VAR"` targets. A restored instance with the database back and these two
  unset is working correctly and simply does not offer `web_search`.
- **A deploy needs `.env` on the server first.** `deploy.sh` refuses to restart
  the stack without it ("Build and deploy" above); the file is placed by hand and
  never generated.
- **Watch item with a date: Google's Custom Search JSON API transition,
  `2027-01-01`.** The API is closed to new customers and existing customers must
  transition by that date. The code-side flip condition is recorded in
  `llm-and-streaming.md` — one provider class plus a factory — but the **first
  symptom is operational**: `web_search` starts failing as `tool_failed` for every
  call while everything else keeps working. Listed here so the date is in the
  operator's notes and not only in a design doc.

---

## Decision history

### 2026-11-09 — the `llm-client` pin moves to `v0.2.1`

Approved and built 2026-11-09 (feature 035 step 006). The only deployment
consequence is the pinned tag: the build still needs `git` and github.com, the
HTTP stack is unchanged, and the trace variables keep their meaning — RPHelper
leaves the library's trace switch to the environment. The library's new
streamed-only silence limit is not used, so nginx's `proxy_read_timeout` note
above is unchanged. `DEC-arch-llm-client-library-13`, `-17`.

### 2026-11-08 — LLM calls move to the `llm-client` library

Two deployment consequences, both recorded above: the image build needs `git`
and network access to github.com for the backend's git dependency, and the
library's `LLM_TRACE` / `LLM_TRACE_FOLDER` variables are an operator-only,
privacy-breaking debug switch that must stay unset in a shared deployment.
`DEC-arch-llm-client-library-1`.

### 2026-10-08 — prod deploys from a pre-built image; the dev compose takes the standard name

fast/013.build-and-deploy-scripts. The prod compose became image-based
(`docker-compose.prod.yml`, no `build:`), staged into a shared store by
`build.sh` and started on the server by `deploy.sh`; the dev compose was renamed
`docker-compose.yml`. "Build and deploy" above. `DEC-F013-1` .. `-8`.

### 2026-10-07 — dev serves the app at `/`, mirroring prod

**Before:** this doc recorded that the Vite dev server did not resolve
`http://localhost:8193/` and that entries were reached at `/<entry>/index.html`
in dev. **After:** dev and prod share one URL space, and dev answers `/` through
a serve-only Vite routing plugin ("The app document at `/` — prod and dev").

How the earlier reading arose — **no requirement ever said dev should differ from
prod; the dev half of the gap was simply never owned**:

1. **Plan 002.frontend-foundation, D13 / seam S1** rooted the Vite build at
   `src/`, refused a fifth root document, deferred the `/` bridge to `fast/001`,
   and recorded "`http://localhost:8193/` does not resolve … entries reached at
   `/<entry>/index.html`" as a **known wart**.
2. Commit `75c7166` applied that outcome here as "Dev-side consequence while it
   is unbridged", and the wart then read as documented dev behaviour.
3. **`fast/001.dev-and-container-harness`** closed only the prod half, with the
   image-only copy. It scoped Vite dev to `/<entry>/` and promised `/` only
   through a dev-compose nginx that no longer exists; its outcome proposed
   restating that host Vite still does not serve `/`. **That dev-side note is
   superseded by this decision.**
4. **`fast/008.vite-dev-request-log`** then encoded `GET / 404` as expected dev
   output.
5. **`fast/009.vite-dev-root-routing` built the dev mechanism** (2026-10-07).
   fast/008's `GET / 404` expectation is superseded: the dev log for `/` now
   reads `GET / 200 <n>ms`, because the request log captures the browser's URL
   when the request enters, before the routing plugin rewrites it — so the
   request logger needed no change (`DEC-F009-4`).

### 2026-10-06 — the nginx seams and the nginx access log are closed

fast/001.dev-and-container-harness built the image and closed the open items
this doc assigned to it: no `location /app/`; slash-less entry paths answer a
relative 302; `/api/` is matched ahead of the regex locations; nginx's access
log is path-only, declared where it replaces the base image's default.
`DEC-F001-1` .. `-6`.
