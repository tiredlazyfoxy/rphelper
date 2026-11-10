# Decisions — fast-007.vite-proxy-request-log
**Stage:** — · **Feature:** fast/007.vite-proxy-request-log

The dev proxy's request log: one line per proxied `/api` request on the Vite
process's stdout (the `[ui]` stream under `start.sh`). The contracts are
`deployment.md`'s "Dev topology" (the dev request log) and "Access-log lines
record the path without its query string". Written at finalization (2026-11-09).
The timing reason in DEC-F007-2 has no code comment; this entry is its record.

### DEC-F007-1 — Line shape, sink, and no prefix
- **Status:** accepted
- **Stage:** — · **Feature:** fast/007.vite-proxy-request-log · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** user (shape); planner (sink, no prefix)
- **Question:** What does a proxied request's log line look like, and where is it written?
- **Decision:** `<METHOD> <path> <status> <ms>ms` (e.g. `GET /api/sessions 200 12ms`); on a proxy failure `<METHOD> <path> proxy error <CODE>` (e.g. `GET /api/sessions proxy error ECONNREFUSED`). No prefix, colour or timestamp. The default sink is `process.stdout.write(line + "\n")`, pinned so tests can observe it.
- **Reason:** Under `start.sh` the `[ui]` prefix already identifies the stream. Vite's logger is not reachable from the proxy `configure` hook, and stdout is what both launchers capture.
- **Lands in:** `frontend/dev/proxyLog.ts`
- **Cites:** `deployment.md` "Dev topology"

### DEC-F007-2 — Duration is measured to the response headers, not to the end
- **Status:** accepted
- **Stage:** — · **Feature:** fast/007.vite-proxy-request-log · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** When is a proxied request's line written and its duration read?
- **Decision:** On the proxy's `proxyRes` event — when the upstream response headers arrive — with `proxyRes.statusCode` as the status. The number is time to first byte.
- **Reason:** The compose route is a long-lived SSE stream. Logging at `end` would delay the line by the whole generation, or lose it entirely on a client abort; logging at headers shows the call the moment it is answered, which is what a developer watching the terminal needs.
- **Rejected:** logging at the proxy's `end` event.
- **Lands in:** `frontend/dev/proxyLog.ts`
- **Cites:** `deployment.md` "Dev topology"; `llm-and-streaming.md` (the compose stream)

### DEC-F007-3 — Start time from the earliest per-request event, keyed per request
- **Status:** accepted
- **Stage:** — · **Feature:** fast/007.vite-proxy-request-log · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Where does the clock start, and how are concurrent requests kept apart?
- **Decision:** The start time is taken at the proxy's `start` event, with `proxyReq` as the fallback when no `start` was seen, and is held in a map keyed by the incoming request object (a `WeakMap`).
- **Reason:** Keying by request object keeps concurrent requests from crossing, and a weak map leaks nothing when a request is dropped without a terminal event.
- **Lands in:** `frontend/dev/proxyLog.ts`

### DEC-F007-4 — At most one line per request
- **Status:** accepted
- **Stage:** — · **Feature:** fast/007.vite-proxy-request-log · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** What if both a response and an error are reported for one request?
- **Decision:** Only the first of `proxyRes` and `error` for a request writes a line; the other is ignored.
- **Reason:** One line per request is what makes the log countable and is the invariant the request-log middleware relies on to split the work (DEC-F008-2).
- **Lands in:** `frontend/dev/proxyLog.ts`

### DEC-F007-5 — Redaction: path cut at `?` and `#`; an error carries its code only
- **Status:** accepted
- **Stage:** — · **Feature:** fast/007.vite-proxy-request-log · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** user (path only); planner (error-code fallback)
- **Question:** What of the request may appear in the line?
- **Decision:** The path only, cut at the first `?` and at any `#`. Never headers, cookies, bodies or the upstream target URL. On an error, `err.code` when it is a non-empty string, otherwise the fixed token `unknown`; `err.message` is never used. `frontend/tests/proxy-log.test.ts` is the check.
- **Reason:** The query string can carry message text (`GET /api/search?q=…`), and an error message can embed a URL; method, status and duration are on the redaction rule's allowed list.
- **Lands in:** `frontend/dev/proxyLog.ts` (`redactPath`, the error formatter); `frontend/tests/proxy-log.test.ts`
- **Cites:** `deployment.md` "The redaction rule", "Access-log lines record the path without its query string"

### DEC-F007-6 — Attach through the `/api` rule's `configure` hook; attaching is silent
- **Status:** accepted
- **Stage:** — · **Feature:** fast/007.vite-proxy-request-log · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** How does the logger reach the proxy?
- **Decision:** The `/api` proxy rule moves to object form — still one key, target still `http://localhost:8184` — with `configure: configureProxyLogging`, which attaches listeners to the proxy emitter. The hook's parameter is typed structurally (a minimal emitter shape), because Vite does not export the proxy server class, and so tests can pass a plain Node `EventEmitter`. Attaching writes nothing and never throws.
- **Reason:** The plan's premise that `configure` is inert under Vitest was wrong: Vitest creates a Vite server from this config, so the hook runs during test runs (found by the skeleton here and confirmed by fast/008). Silent, non-throwing attachment is what keeps test output clean; the hook is still inert under `vite build`.
- **Rejected:** a `configureServer` plugin for the proxy log — the plan rejected it for running inside Vitest, which turned out to be true of `configure` as well; the proxy hook remains the natural attach point for proxy events.
- **Lands in:** `frontend/vite.config.ts`; `frontend/dev/proxyLog.ts`
- **Cites:** `deployment.md` "Dev topology"
