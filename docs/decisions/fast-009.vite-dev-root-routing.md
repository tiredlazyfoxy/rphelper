# Decisions — fast-009.vite-dev-root-routing
**Stage:** — · **Feature:** fast/009.vite-dev-root-routing

The serve-only Vite plugin that makes the dev server on 8193 answer the same URL
space as prod nginx. The contract is `deployment.md`'s "The app document at `/` —
prod and dev" (its routing table and dev mechanism). Written at finalization
(2026-11-09).

### DEC-F009-1 — Plugin home, name and position
- **Status:** accepted
- **Stage:** — · **Feature:** fast/009.vite-dev-root-routing · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Where does the dev routing mechanism live and where does it sit in the dev server's chain?
- **Decision:** `frontend/dev/entryRouting.ts` holds the routing middleware, the script-src absolutizer and the plugin `rphelper-dev-entry-routing` (`apply: "serve"`). It is wired as `plugins: [react(), devRequestLogPlugin(), devEntryRoutingPlugin()]`. The middleware factory takes the server root and an optional file-existence predicate, so tests can inject both; `configureServer` passes `server.config.root` and registers the middleware directly, returning nothing.
- **Reason:** Direct registration puts the middleware before Vite's proxy and every Vite internal, which is why it must pass `/api` and internals through explicitly. After the request-log plugin, so the log still sees the browser's URL (DEC-F009-4). The name must not contain `react`, because the request-log test locates its plugin relative to any plugin so named.
- **Lands in:** `frontend/dev/entryRouting.ts`; `frontend/vite.config.ts`
- **Cites:** `deployment.md` "The app document at `/` — prod and dev" (dev mechanism)

### DEC-F009-2 — The routing predicate
- **Status:** accepted
- **Stage:** — · **Feature:** fast/009.vite-dev-root-routing · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Exactly which requests are routed, and to what? (The architecture left the predicate to the plan.)
- **Decision:** GET and HEAD only; every other method passes through. In order:
  - pass through `/api` and `/api/…`, `/@…`, `/__…` and `/node_modules/…`;
  - pass through any path whose last segment has an extension;
  - pass through any decoded path resolving to an existing **regular file** inside the root (a directory such as `/login/` is not a file);
  - exact `/bootstrap`, `/login`, `/admin` → a relative 302 to the slash form, query dropped;
  - `/<entry>/…`, including the bare `/<entry>/`, → rewritten to `/<entry>/index.html`;
  - everything else → rewritten to `/app/index.html`.

  The rewritten URL carries no query; `req.originalUrl` is never touched. No `Accept` or `sec-fetch-dest` gating. On an internal error the request passes through unchanged.
- **Reason:** Module requests carry `Accept: */*` and look like navigations by header, so a header-based predicate misroutes them; nginx's `try_files` is path-only too, and mirroring it is the contract. Rewriting `/login/` itself (rather than leaving it to Vite's HTML fallback) gives the entry document without depending on that fallback's directory handling, matching nginx's `$uri/`. Dropping the query keeps the index-HTML file lookup trivially correct while the browser keeps the query in its own URL. Nginx's `return 302 /login/;` also drops the query.
- **Lands in:** `frontend/dev/entryRouting.ts`
- **Cites:** `deployment.md` the routing table; DEC-F001-3

### DEC-F009-3 — Only `type="module"` script srcs are absolutized, by the plugin's own HTML hook
- **Status:** accepted
- **Stage:** — · **Feature:** fast/009.vite-dev-root-routing · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner (orchestrator decision)
- **Question:** Vite 8.3.1 leaves an entry document's relative `<script type="module" src="./main.tsx">` as written, so a document served at `/` or a deep link loads `/main.tsx` or `/sessions/main.tsx`. How is it fixed?
- **Decision:** The plugin's own `transformIndexHtml` hook (pre order, serve-only through `apply`) delegates to a pure exported function that rewrites each relative module-script `src` to an absolute path against the served document's directory (`ctx.path`) — `/app/index.html` with `./main.tsx` gives `/app/main.tsx`. A src is relative when it has no scheme, does not start with `/` and is not protocol-relative (`//`); `./x`, `../x` and bare `x` all count. Classic scripts and every other tag are untouched. The entry HTML files are not edited.
- **Reason:** No entry document has a classic script, so the narrower rewrite has the smaller blast radius. Pre order means Vite's own HTML transforms see an absolute src. The entry files stay relative because `frontend/tests/entries.test.tsx` resolves each src against its file, and the build already emits absolute hashed URLs.
- **Rejected:** editing the entry HTML to absolute srcs — breaks the entries test and couples the source files to the dev URL space.
- **Lands in:** `frontend/dev/entryRouting.ts`
- **Cites:** `deployment.md` "The app document at `/` — prod and dev" (the `transformIndexHtml` bullet)

### DEC-F009-4 — The request log keeps the browser's URL
- **Status:** accepted
- **Stage:** — · **Feature:** fast/009.vite-dev-root-routing · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** The request-log middleware runs before the routing middleware. Does its line for `/` show `/` or the rewritten `/app/index.html`?
- **Decision:** `/`: the request log snapshots `req.url` at middleware entry and formats that snapshot at finish (status still read at finish, DEC-F008-3). The coder found `requestLog.ts` already did this, so it was not edited. The dev log for `/` reads `GET / 200 <n>ms`.
- **Reason:** Snapshotting at entry does not depend on connect having set `originalUrl` (the request-log test fakes do not set it), keeps those fakes valid, and breaks none of fast/008's checks, none of which pins when the URL is read.
- **Rejected:** preferring `req.originalUrl` at finish — the reasons above.
- **Supersedes:** fast/008's manual expectation that `curl http://localhost:8193/` prints `GET / 404 <n>ms` (its DoD-16); that was the pre-routing behaviour, not a regression.
- **Lands in:** `frontend/dev/requestLog.ts` (unchanged)
- **Cites:** `deployment.md` "Decision history" (2026-10-07)
