# fast/007.vite-proxy-request-log — context

## Problem

In the dev pair (`start.sh` / `start.ps1`), Vite serves on 8193 and proxies `/api` to
uvicorn on 8184. The Vite output (the `[ui]` stream under `start.sh`) prints nothing for
proxied API calls, so a developer watching the UI terminal cannot see what was called.
The backend's own access log (`[api]`) already works and is out of scope.

## Files involved

| Path | Role |
|---|---|
| `frontend/vite.config.ts` | Existing. Single config file: React plugin, four-entry build, `server` block (port 8193, `strictPort`, one proxy rule `"/api": "http://localhost:8184"` in string form), Vitest `test` block. Uses `defineConfig` from `vitest/config`. |
| `frontend/dev/proxyLog.ts` | New. Dev-only helper the config imports. No `frontend/dev/` folder exists yet; there is no prior pattern for config helper modules. |
| `frontend/tests/build-config.test.ts` | Existing (plan 002 step 001). Not touched by this plan, but it constrains it — see below. |
| `start.sh`, `start.ps1` | Existing launchers. Unchanged: anything Vite's process writes to stdout lands in the `[ui]` stream (`start.sh` prefixes it; `start.ps1` runs `npx vite --port 8193` plain). |

## External facts (Vite 8.3.1 / http-proxy-3)

- Vite's dev proxy is `http-proxy-3`. The object form of a proxy rule (`ProxyOptions`,
  exported from `vite`) accepts `configure(proxy, options)`, called **once when the dev
  server instantiates the proxy**. It is therefore inert under `vite build` and under
  Vitest. A `configureServer` plugin is the wrong mechanism — it can run inside Vitest's
  internal server.
- The proxy server is an EventEmitter. Relevant events and their arguments:
  - `start` — `(req, res, target)`, when the proxy begins handling a request;
  - `proxyReq` — `(proxyReq, req, res, options, socket)`, when the outgoing request is created;
  - `proxyRes` — `(proxyRes, req, res)`, when the upstream response **headers** arrive
    (`proxyRes.statusCode` carries the status);
  - `end` — `(req, res, proxyRes)`;
  - `error` — `(err, req, resOrSocket, target?)`; `err.code` is e.g. `ECONNREFUSED`
    when uvicorn is not running.
- The `ProxyServer` class is **not** exported from `vite`. Type the hook parameter
  structurally (a minimal emitter shape) or derive it from `ProxyOptions["configure"]`.
  A structural shape is preferred so tests can pass a plain Node `EventEmitter`.
- Vite's own proxy middleware already logs `http proxy error: <url>` on errors (unverified;
  it may include the query string). That message is Vite's, not ours, and is out of
  scope. Our listener is additive.

## Constraints the existing 002 test imposes (must keep passing unchanged)

From `frontend/tests/build-config.test.ts` (002 step 001 DoD-2, DoD-3, DoD-7, DoD-8, DoD-11):

- The proxy has **exactly one** key, `/api`. The object form is already accepted, but its
  `target` must be a **string** whose URL hostname is `localhost` and port `8184`.
  **Keep `http://localhost:8184`** (user decision 3; `deployment.md` pins it).
- The text of `vite.config.ts` must not contain `process.env`, `import.meta.env` or
  `loadEnv`, and must contain the literals `8193` and `8184`.
- `package.json` keeps exactly four scripts (`build`, `test`, `typecheck`, `dev`) and its
  dependency allow/deny lists are asserted. So this plan adds **no npm script and no
  dependency**.
- No `.js` / `.jsx` / `.mjs` / `.cjs` file anywhere under `frontend/`. TypeScript only.

## Typecheck reach

`npm run typecheck` runs `tsc --noEmit` over `tsconfig.json` (include `src`, `tests`; DOM
lib; `@types/node` ambient) **and** `tsconfig.node.json` (include `vite.config.ts`; lib
ES2022; `types: ["node"]`). Both are strict with `noUnusedLocals` and
`noUnusedParameters`. `frontend/dev/proxyLog.ts` is outside both includes, but it is
compiled transitively under **both**: through `vite.config.ts`'s import (node config) and
through the test's import (`tsconfig.json`). It must compile cleanly under each. In
particular it must use no DOM-only API, and unused listener parameters must be avoided or
underscore-handled per the strict flags. The import specifier style (extensionless or
not) must satisfy both configs' module resolution. The skeleton agent settles this
against the real tsconfigs.

## Redaction rule (binding)

`docs/architecture/deployment.md` → "The redaction rule": no log line at any level may
carry message text, and **web-search queries are message text**. `GET /api/search?q=…` is
the live example. The backend's access-log filter strips the query string for exactly
this reason ("Access-log lines record the path without its query string"). The dev proxy
line follows the same rule:

- **path only** — everything from the first `?` is dropped, and so is any `#` fragment;
- never headers, bodies, cookies, or the upstream target URL;
- never `err.message`. An error message can embed a URL, and the error line carries only
  the code.

Durations and HTTP status are explicitly on the allowed list.

## User-confirmed decisions

1. Line shape: `<METHOD> <path> <status> <ms>ms`, e.g. `GET /api/sessions 200 12ms`. On
   proxy failure: `<METHOD> <path> proxy error <CODE>`, e.g.
   `GET /api/sessions proxy error ECONNREFUSED`.
2. Path only: strip from the first `?` (and any fragment).
3. Proxy target stays `http://localhost:8184`.
4. Dev-only: `npm run build` output and Vitest runs are unaffected.

## Planner decisions

- **D1 — Duration is measured to response headers (`proxyRes`), not to `end`.** The
  compose route is a long-lived SSE stream. Logging at `end` would delay the line by the
  whole generation, or lose it on a client abort. Logging at headers shows the call the
  moment it is answered. The number is time-to-first-byte, which is what the developer
  needs to see.
- **D2 — Start time is taken at the earliest per-request event the proxy emits** (`start`,
  with `proxyReq` as the fallback when no `start` was seen). It is keyed per incoming
  request object (e.g. a `WeakMap`), so concurrent requests do not cross and nothing leaks
  when a request is dropped.
- **D3 — At most one line per request.** If an `error` follows a `proxyRes` for the same
  request, or the reverse, only the first is written.
- **D4 — No prefix or timestamp on the line.** The user confirmed the exact shape. Under
  `start.sh`, the `[ui]` prefix already identifies the stream.
- **D5 — Default sink is `process.stdout.write(line + "\n")`.** It is pinned so tests
  can observe it. Vite's logger is not reachable from `configure`, and stdout is what
  both launchers capture.
- **D6 — Error code fallback.** Use `err.code` when it is a non-empty string. Otherwise
  use the fixed token `unknown`. The error's message is never used.
