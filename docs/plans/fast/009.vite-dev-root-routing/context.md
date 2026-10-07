# fast/009.vite-dev-root-routing — context

## Why

User request (2026-10-07): "Both on dev and prod it should answer on `/`, not `/app`."

Prod already does this, as built by `fast/001`: the image copies `dist/app/index.html` to
`dist/index.html`, and nginx's catch-all serves it. This feature makes the **Vite dev
server on :8193** follow the same routing contract. That contract is
`docs/architecture/deployment.md`, "The app document at `/` — prod and dev", and its
routing table is the ground truth. Dev routing mirrors prod nginx routing.

All three dev launch paths run Vite (`start.sh`, `start.ps1 -ui`,
`docker-compose.dev.yml`; deployment.md "Dev topology"). One Vite plugin therefore covers
all of them, and no launcher changes.

## Files involved

| Path | Role in this feature |
|---|---|
| `frontend/dev/entryRouting.ts` | **new**: the routing middleware, the script-src absolutizer and the dev plugin |
| `frontend/vite.config.ts` | wires the new plugin after the request-log plugin |
| `frontend/dev/requestLog.ts` | fast/008's request logger. Touched **only if** it reads `req.url` at finish rather than at entry (decision D4 below) |
| `frontend/tests/entry-routing.test.ts` | **new**: this feature's tests |
| `frontend/src/<entry>/index.html` (×4) | **unchanged**. Each has one `<script type="module" src="./main.tsx">` and `<div id="root">` |
| `frontend/tests/request-log.test.ts`, `build-config.test.ts`, `entries.test.tsx`, `proxy-log.test.ts` | **unchanged**. They must stay green unedited |
| `docker/nginx.conf` | **unchanged**. It is the reference behaviour being mirrored |

## Versions

vite 8.3.1, vitest 5.0.2, @vitejs/plugin-react 6.1.1, @types/node 26.6.3.

## Facts the design rests on

### vite.config.ts today
- `plugins: [react(), devRequestLogPlugin()]` and `root: srcDir` (`frontend/src`).
- Four rollup inputs, `src/<entry>/index.html`.
- `server`: port 8193, `strictPort`, and one proxy rule for `/api` (target
  `http://localhost:8184`, with `configure: configureProxyLogging`).
- A test block with root `frontendDir` and the jsdom environment.
- It imports `./dev/*.ts` with extensions, and `frontendDir` is `import.meta.dirname`.

### Vite 8.3.1 dev middleware order
1. rejectInvalidRequest
2. cors
3. hostValidation
4. **plugins' `configureServer` direct `use`**. Both request-log and entry-routing go
   here, in plugin order.
5. cachedTransform
6. proxy (`/api`)
7. `/__open-in-editor`
8. HMR ping
9. servePublic
10. transform
11. serveRawFs
12. serveStatic
13. htmlFallback
14. post-hooks
15. indexHtml
16. notFound

The routing middleware therefore runs **before the proxy and before every Vite
internal**. That is why it must explicitly pass through `/api`, `/@…`, `/__…`,
`/node_modules/…`, and module or asset requests.

### What Vite does downstream of a rewrite
- **htmlFallback** acts on GET/HEAD with an Accept of html, `*/*`, or no Accept at all.
  - It handles `.html` paths, maps `dir/` to `dir/index.html` and `x` to `x.html`.
  - Otherwise it falls back to `/index.html`. That file does not exist under `src/`, so
    today `/` is a 404.
- **indexHtml** serves `path.join(root, req.url)` for `.html` URLs and calls
  `transformIndexHtml(url, html, req.originalUrl)`. The hook context's `path` is the
  **rewritten** URL, for example `/app/index.html`.
- `req.originalUrl` keeps the browser URL. Connect sets it before the middlewares run.
  The routing middleware rewrites only `req.url`.
- Module requests carry `Accept: */*` and `sec-fetch-dest: script`. That is why the
  routing uses a path-only predicate (file exists, or the path has an extension) and does
  not gate on Accept. This also mirrors nginx's path-only `try_files`.

### The relative-src problem (orchestrator decision D2)
Vite 8.3.1 does **not** absolutize the relative `src="./main.tsx"` in an entry document.
Once `/` or `/sessions/5` is rewritten to `/app/index.html`, the browser resolves
`./main.tsx` against **its own** URL. It then requests `/main.tsx` or
`/sessions/main.tsx`, and the app never boots.

The fix stays inside the plugin. A serve-only `transformIndexHtml` hook rewrites each
relative module-script `src` to an absolute path, resolved against the served document's
directory (from `ctx.path`). For example, `/app/index.html` with `./main.tsx` gives
`/app/main.tsx`.

The entry HTML files are **not** edited: `tests/entries.test.tsx:472-482` resolves each
entry's script src relative to the file, and an absolute src would break it.

deployment.md's "Rewrite, not redirect" bullet is being corrected in parallel to say
this.

### Prod nginx, the behaviour mirrored (`docker/nginx.conf`)
```
location /bootstrap/|/login/|/admin/   try_files $uri $uri/ /<entry>/index.html;
location = /bootstrap|/login|/admin    return 302 /<entry>/;
location /                             try_files $uri $uri/ /index.html;   (index.html = app copy)
absolute_redirect off                  → relative Location header
```
nginx `return 302 /login/;` emits `Location: /login/` with the query string dropped. Dev
does the same.

## Constraints from existing tests (must stay green, unedited)
- `request-log.test.ts:622-640`: exactly one plugin named `rphelper-dev-request-log`,
  placed after any plugin whose name contains `react`. The new plugin's name must
  **not** contain `react`.
- `request-log.test.ts:644-670` scans **every** `frontend/dev/*.ts` and
  `vite.config.ts`. Every relative import specifier must end in `.ts`, and `__dirname`
  must not appear. `node:` built-in specifiers are not relative and are unaffected.
- `build-config.test.ts` asserts:
  - `root` is `src`;
  - the input keys are `[admin, app, bootstrap, login]`;
  - the proxy keys are `["/api"]`;
  - the scripts are `[build, dev, test, typecheck]`;
  - there are no JS files.
- `entries.test.tsx:472-482`: each entry's script src resolves relative to its file.
- `request-log.test.ts` DoD-1..13 constrain the request logger. None of them pins
  *when* the URL is read; DoD-2 pins only the **status**, read at finish.

## Typecheck reach
`tsconfig.json` (DOM lib, no explicit `types` restriction, includes `src` and `tests`)
and `tsconfig.node.json` (`vite.config.ts`, node types) both reach `dev/*.ts`
transitively. The new module must compile under both. `node:fs` and `node:path` imports
are fine: `@types/node` is visible to both configs, as `proxyLog.ts` already relies on
`process`. Pattern to follow: `frontend/dev/requestLog.ts`.
- Structural `unknown`-typed request/response interfaces.
- A middleware factory plus a plugin factory.
- An exported plugin-name constant.
- `apply: "serve"`.
- A `configureServer` that calls `server.middlewares.use(...)` directly and returns
  nothing.
- No import side effects.

## Decisions taken in this plan

- **D1 — Plugin home.** A new `frontend/dev/entryRouting.ts`, wired as
  `plugins: [react(), devRequestLogPlugin(), devEntryRoutingPlugin()]`. The suggested
  plugin name is `rphelper-dev-entry-routing`; the skeleton freezes it. The middleware
  factory takes the server root and an optional file-existence predicate, so tests can
  inject both. `configureServer` passes `server.config.root`.
- **D2 — Relative script src.** The plugin's own `transformIndexHtml` hook, delegating to
  a pure exported function. **Only `type="module"` scripts are touched.** Classic scripts
  and every other tag are left alone. No entry document has a classic script, so the
  narrower rewrite has the smaller blast radius. A relative src is one with no scheme,
  not starting with `/`, and not protocol-relative (`//`). `./x`, `../x` and bare `x` all
  count. The hook runs before Vite's own HTML transforms (pre order), so Vite sees an
  absolute src.
- **D3 — Routing table.** As briefed and in `plan.md`. Two choices made here:
  - **`/login/` (with a trailing slash) is rewritten to `/login/index.html`**, and the
    same holds for `/bootstrap/` and `/admin/`. It is a directory, not a file, so it
    falls under the "`/<entry>/…` not resolving to a file" row. This matches what nginx
    produces (`$uri/` with index gives the entry document), and the result does not
    depend on Vite's htmlFallback directory handling.
  - **A rewritten URL carries no query string.** For example, `/characters/7?x=1`
    becomes exactly `/app/index.html`. The browser keeps the query in its own URL, and
    `req.originalUrl` keeps it on the request. Dropping it keeps indexHtml's file lookup
    trivially correct.
- **D4 — Request-log interplay. Capture the URL at entry.** The request-log middleware
  is registered before the routing middleware. If it reads `req.url` when `finish` fires,
  the line for `/` reads `GET /app/index.html 200`. The desired line is `GET / 200 <n>ms`.
  - The planner cannot read source, so the coder checks `frontend/dev/requestLog.ts`.
    - If it already snapshots the URL at middleware entry, it is **not edited**.
    - If it reads the URL at finish, the **minimal fix** is to snapshot `req.url` at
      middleware entry and format that snapshot at finish. This is chosen over "prefer
      `originalUrl`" for three reasons:
      - it does not depend on Connect having set `originalUrl`, which the
        EventEmitter fakes in `request-log.test.ts` do not set;
      - it keeps the existing fakes valid;
      - it satisfies every 008 DoD, because none of them pins the URL read time.
  - The status is still read at finish (008 DoD-2).
  - No 008 frozen signature changes.
  - The routing middleware never touches `req.originalUrl`.
- **D5 — Scope.** Unchanged:
  - `start.sh`, `start.ps1`, the compose files, the nginx configs, the Dockerfile and
    the entry HTML;
  - `vite build` output: four HTML entries, no `dev/` chunk.

  `docker/nginx.dev.conf` is unused by dev-compose. Removing it belongs to `fast/001`'s
  finalization.

## Supersedes
`fast/008` DoD-16 expected `curl http://localhost:8193/` to print `GET / 404 <n>ms`.
After this feature the expected line is `GET / 200 <n>ms`. That 008 manual expectation
is superseded. It is not a regression.
