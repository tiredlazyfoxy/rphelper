# fast/007.vite-proxy-request-log — outcome

Intended doc changes, for the architect to apply at finalization.

## docs/architecture/deployment.md

- **Section:** "Dev topology", the Vite proxy configuration snippet and the sentence
  "Vite proxy configuration — **one prefix only**"
  **Change:** Show the `/api` rule in **object form**: `target: "http://localhost:8184"`
  plus a `configure` hook that attaches the dev request logger from
  `frontend/dev/proxyLog.ts`. State that it is still one prefix and the same target.
  Add a short paragraph covering the following:
  - The dev proxy prints one line per proxied request to Vite's stdout, which is the
    `[ui]` stream under `start.sh`. The line is `<METHOD> <path> <status> <ms>ms`, or
    `<METHOD> <path> proxy error <CODE>` when the backend is unreachable.
  - The duration is measured to response headers, so an SSE compose stream logs when it
    opens rather than when it ends.
  - The hook runs only when the dev server instantiates the proxy, so it is inert under
    `vite build` and Vitest.

  **Reason:** As-built record. The snippet currently shows the string form, which no
  longer matches `vite.config.ts`.
- **Section:** "The redaction rule" → "Access-log lines record the path without its query
  string"
  **Change:** Add one sentence saying the dev proxy's request line follows the same rule:
  - path only, cut at the first `?` and any `#`;
  - no headers, bodies, cookies or upstream URL;
  - the error line carries `err.code` only, never the error message.

  Name `frontend/tests/proxy-log.test.ts` beside the two backend enforcement tests as the
  frontend-side check.
  **Reason:** A second access-log-shaped surface now exists in dev, and the section's
  point is that nobody reviews an access log line unless it is named.

## docs/architecture/frontend-structure.md

- **Section:** wherever `vite.config.ts` and the frontend folder layout are described
  **Change:** Note the new `frontend/dev/` folder. It holds dev-server-only helpers
  imported by `vite.config.ts`. They are not part of any entry, are not bundled by
  `vite build`, and are typechecked transitively through `tsconfig.node.json`, with no
  include change.
  **Reason:** A new top-level frontend folder with no prior pattern.

## docs/architecture/quick-reference.md

- **Section:** Paths
  **Change:** Add a row for `frontend/dev/proxyLog.ts`, described as "dev proxy request
  logger (query-stripped path, status, ms)".
  **Reason:** As-built record.

## Flags for other owners

- `docs/plans/002.frontend-foundation/status.md` records the `/api` proxy rule as the
  string form. After this plan, that note is stale. It is informational only, and
  002's DoD-2 test already accepts the object form. No edit is required. A reader
  should know the object form is deliberate.

## Observations
