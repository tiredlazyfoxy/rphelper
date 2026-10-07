# fast/008.vite-dev-request-log — outcome

Intended doc changes for the architect to apply at finalization. These are written on
top of 007's outcome entries, which may not be applied yet. Apply 007's first.

## docs/architecture/deployment.md

- **Section:** "Dev topology". This covers the Vite proxy snippet and the dev-proxy
  logging paragraph that 007's outcome adds.
  **Change:**
  - State that the dev server logs **every** HTTP request it receives, one line each,
    as `<METHOD> <path> <status> <ms>ms`. That includes pages, modules, assets and Vite
    internals.
  - Explain the split. A plugin middleware from `frontend/dev/requestLog.ts`, registered
    first in `configureServer`, logs everything except URLs starting with `/api`. Those
    are left to 007's proxy logger, so each request gets exactly one line.
  - Say the skip rule mirrors Vite's string-key proxy match (`startsWith("/api")`) on
    purpose, so the two cannot diverge.
  - Give the duration semantics: non-`/api` lines time to response end, and an aborted
    request shows `-` as its status. `/api` lines time to response headers (007).
  - Note that the plugin is `apply: "serve"`, so it is inert under `vite build`.
  - Note the correction to 007's outcome text: both the proxy `configure` hook and the
    plugin's `configureServer` **do run under Vitest**, because Vitest creates a Vite
    server. Attaching is silent by design.
  - Note that HMR websocket upgrades are not logged.

  **Reason:** This is the as-built record. 007's outcome says the dev log covers proxied
  requests only and that the hook is inert under Vitest. Both statements are now wrong.
- **Section:** "The redaction rule" → "Access-log lines record the path without its query
  string"
  **Change:**
  - Extend 007's sentence so it covers both dev-server log surfaces, the proxy logger and
    the request-log middleware. Both are path-only (query and fragment cut), and neither
    logs headers, cookies or bodies.
  - Name `frontend/tests/request-log.test.ts` beside `frontend/tests/proxy-log.test.ts`
    as the frontend-side checks.

  **Reason:** A second dev access-log surface now exists, and the section says that
  every such surface gets named.

## docs/architecture/frontend-structure.md

- **Section:** where `vite.config.ts` and the `frontend/dev/` folder (from 007's outcome)
  are described.
  **Change:**
  - `vite.config.ts` resolves its own directory with **`import.meta.dirname`**, not
    `__dirname` (Vite 8's native config loader flags `__dirname`).
  - Relative imports from the config, and between `frontend/dev/` modules, carry the
    `.ts` extension. Both tsconfigs set `allowImportingTsExtensions: true`, which is
    legal because both are `noEmit`.
  - `frontend/dev/` now holds `proxyLog.ts` and `requestLog.ts`.
  - If any text still records 002's `__dirname` mandate, mark it superseded. Give the
    reason: the mandate was about `import.meta.url` under jsdom, and `import.meta.dirname`
    is a different value, verified by `build-config.test.ts` staying green.

  **Reason:** A config convention changed, and the old mandate's reasoning must not be
  re-applied to the new value.

## docs/architecture/quick-reference.md

- **Section:** Paths
  **Change:** Add a row for `frontend/dev/requestLog.ts`: "dev-server request logger
  (every non-`/api` request: path, status, ms)".
  **Reason:** As-built record.

## Flags for other owners

- `docs/plans/002.frontend-foundation/001.context.md` (around line 27, "use `__dirname`,
  not `import.meta.url`") and `docs/plans/002.frontend-foundation/status.md` (around
  line 87) record the `__dirname` mandate. They are stale after this plan. They are
  informational only, and no edit is required.
- `docs/plans/fast/007.vite-proxy-request-log/status.md` line 22 records the
  extensionless `./dev/proxyLog` import, and its Notes & Issues describe the advisory as
  left as-is. Both are stale after this plan. They are informational only.
- `deployment.md`'s dev-proxy snippet still shows the string form until 007's outcome is
  applied. Apply 007's entry first.

## Observations
