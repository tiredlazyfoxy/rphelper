# Decisions — fast-008.vite-dev-request-log
**Stage:** — · **Feature:** fast/008.vite-dev-request-log

The dev server's request log for every request the proxy does not see, and the
removal of Vite 8's native-config-loader advisory. The contracts are
`deployment.md`'s "Dev topology" (the dev request log) and "Access-log lines
record the path without its query string", and `frontend-structure.md`'s
"Node-side config conventions". Written at finalization (2026-11-09). The
skip-rule reason in DEC-F008-2 has no code comment; this entry is its record.

### DEC-F008-1 — A separate module; defaults shared with the proxy logger
- **Status:** accepted
- **Stage:** — · **Feature:** fast/008.vite-dev-request-log · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Where does the request logger live, and how does it stay in step with fast/007's proxy logger?
- **Decision:** A new `frontend/dev/requestLog.ts` holds a connect-style middleware factory and a Vite plugin factory. It reuses `proxyLog.ts`'s `redactPath` and `formatSuccessLine`, and the same default sink (`process.stdout.write(line + "\n")`) and clock (`performance.now()`), which `proxyLog.ts` exposes through additive exports only. No existing export of `proxyLog.ts` changes signature or behaviour.
- **Reason:** A plugin middleware is a different mechanism from a proxy `configure` hook, so they stay in two modules; sharing the formatter and defaults keeps the two log surfaces byte-compatible.
- **Lands in:** `frontend/dev/requestLog.ts`, `frontend/dev/proxyLog.ts`

### DEC-F008-2 — The skip rule mirrors the proxy's match exactly
- **Status:** accepted
- **Stage:** — · **Feature:** fast/008.vite-dev-request-log · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** user (rule); planner (reason)
- **Question:** Which requests does the middleware leave to the proxy logger?
- **Decision:** A request whose `req.url` is a string starting with `/api` — `url.startsWith("/api")` — is skipped; every other request is logged. `/apiary` is therefore skipped.
- **Reason:** Vite's proxy claims a string key `"/api"` by the same `startsWith` test, so a request is logged by exactly one of the two loggers — never both and never neither. Any other rule (say `/api/` with the slash) would open a gap or a double line at the boundary.
- **Lands in:** `frontend/dev/requestLog.ts`
- **Cites:** `deployment.md` "Dev topology"; DEC-F007-4

### DEC-F008-3 — Duration to response end; status read at finish; an aborted request shows `-`
- **Status:** accepted
- **Stage:** — · **Feature:** fast/008.vite-dev-request-log · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** When is a non-`/api` line written, and with what status?
- **Decision:** The clock is read when the middleware is invoked; the line is written on the first of the response's `finish` or `close`. On `finish` the status is `res.statusCode` read at that moment. On `close` with no prior `finish` (a client abort) the status renders as `-`. `finish` followed by `close` writes once.
- **Reason:** Vite's later middlewares set the status, so it is only known at the end; an aborted request should be visible without showing a status it never sent. These requests are not streams, so timing to the end costs nothing (contrast DEC-F007-2).
- **Lands in:** `frontend/dev/requestLog.ts`

### DEC-F008-4 — A missing URL is logged, not skipped
- **Status:** accepted
- **Stage:** — · **Feature:** fast/008.vite-dev-request-log · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** What happens to a request with no `req.url`?
- **Decision:** It is logged with the path rendered as `-`. Only a string URL starting with `/api` is skipped.
- **Reason:** "Every request gets one line" has no exception for malformed requests; skipping them would hide exactly the odd case a developer looks for.
- **Lands in:** `frontend/dev/requestLog.ts`

### DEC-F008-5 — Registration: first in the chain, serve-only, silent, always `next()`
- **Status:** accepted
- **Stage:** — · **Feature:** fast/008.vite-dev-request-log · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** How is the middleware installed so it sees every request with its original URL?
- **Decision:** A plugin named `rphelper-dev-request-log`, `apply: "serve"`, whose `configureServer` registers the middleware directly (no returned post-hook), so it runs before Vite's proxy, transform, static, HTML-fallback and not-found middlewares. The middleware calls `next()` exactly once, synchronously, with no error argument, for logged and skipped requests alike; it never ends the response and never throws out of itself or its listeners. Attaching writes nothing. HMR websocket upgrades do not pass through connect middlewares and are not logged.
- **Reason:** Registering first is the only way to see pages, modules, assets and Vite internals with their original URL. Vitest creates a Vite server from this config and so runs `configureServer`; attaching must therefore be silent and must not throw (the same finding as DEC-F007-6). `apply: "serve"` keeps the plugin out of `vite build`.
- **Lands in:** `frontend/dev/requestLog.ts`; `frontend/vite.config.ts` (`plugins`)
- **Cites:** `deployment.md` "Dev topology"

### DEC-F008-6 — `import.meta.dirname`, `.ts` specifiers, and `allowImportingTsExtensions` in both tsconfigs
- **Status:** accepted
- **Stage:** — · **Feature:** fast/008.vite-dev-request-log · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** user
- **Question:** Vite 8's native config loader warned about `__dirname` and an extensionless `./dev/proxyLog` import in `vite.config.ts`. How are both removed?
- **Decision:** `vite.config.ts` resolves its own directory as `import.meta.dirname`. Every relative import in `vite.config.ts`, and every relative import between `frontend/dev/` modules, carries the `.ts` extension. Both `tsconfig.json` and `tsconfig.node.json` set `allowImportingTsExtensions: true`, which is legal because both are `noEmit`. Acceptance: starting Vite prints no native-loader advisory.
- **Reason:** Under the native loader Node imports these files directly, and Node resolves neither `__dirname` in an ES module nor an extensionless relative specifier. The flag permits `.ts` specifiers without requiring them, so existing extensionless imports under `src/` and `tests/` keep resolving.
- **Supersedes:** plan 002.frontend-foundation step 001's plan-local mandate "use `__dirname`, not `import.meta.url`" (no DEC id). That mandate was about `import.meta.url`, which under Vitest's jsdom environment is an `http://localhost/@fs/...` URL that made `fileURLToPath` throw. `import.meta.dirname` is a different value; `frontend/tests/build-config.test.ts` passing unedited (root `frontend/src`, out dir `frontend/dist`, test root `frontend/`) is the evidence. Also supersedes fast/007's extensionless `./dev/proxyLog` import.
- **Lands in:** `frontend/vite.config.ts`; `frontend/tsconfig.json`; `frontend/tsconfig.node.json`; `frontend/dev/*.ts`
- **Cites:** `frontend-structure.md` "Node-side config conventions"
