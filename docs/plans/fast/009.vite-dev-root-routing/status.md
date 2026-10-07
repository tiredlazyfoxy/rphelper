# Fast feature 009 — vite-dev-root-routing

| Status  | Verifier | Date |
|---------|----------|------|
| done    | PASS     | 2026-10-07 |

## Files Changed

- `frontend/dev/entryRouting.ts` — filled the routing middleware, the module-script src absolutizer and the plugin's `configureServer` (registers the middleware with `server.config.root`)
- `frontend/vite.config.ts` — plugin wiring (done by the skeleton; not changed by the coder)
- `frontend/dev/requestLog.ts` — untouched: it already snapshots `req.url` at middleware entry (D4), so no edit is needed

## Skeleton

### Frozen interface (2026-10-07)
Test import specifier: `../dev/entryRouting.ts` (from `frontend/tests/entry-routing.test.ts`, matching the `.ts`-extension convention of the existing dev/ tests). Vite config for DoD-16: `../vite.config` as the plan states.

- `frontend/dev/entryRouting.ts` — `export const ENTRY_ROUTING_PLUGIN_NAME = "rphelper-dev-entry-routing"` — new
- `frontend/dev/entryRouting.ts` — `export interface EntryRoutingRequest { url?: unknown; method?: unknown }` — new
- `frontend/dev/entryRouting.ts` — `export interface EntryRoutingResponse { statusCode?: unknown; setHeader?: unknown; end?: unknown }` — new (all members optional/`unknown` so a response missing methods fits without a cast; the coder calls `setHeader(name, value)` / `end()` only after a `typeof === "function"` check)
- `frontend/dev/entryRouting.ts` — `export type EntryRoutingMiddleware = (req: EntryRoutingRequest, res: EntryRoutingResponse, next: () => void) => void` — new (verified assignable to `server.middlewares.use` without a cast; `IncomingMessage`/`ServerResponse` verified assignable to the shapes)
- `frontend/dev/entryRouting.ts` — `export interface EntryRoutingOptions { root: string; isFile?: (absolutePath: string) => boolean }` — new
- `frontend/dev/entryRouting.ts` — `export function createEntryRoutingMiddleware(options: EntryRoutingOptions): EntryRoutingMiddleware` — new (stub throws)
- `frontend/dev/entryRouting.ts` — `export function absolutizeModuleScriptSrc(html: string, documentPath: string): string` — new (stub throws)
- `frontend/dev/entryRouting.ts` — `export function devEntryRoutingPlugin(): Plugin` — new. Stub returns `{ name: ENTRY_ROUTING_PLUGIN_NAME, apply: "serve", configureServer(server): void {/* no-op */}, transformIndexHtml: { order: "pre", handler(html, ctx): string { return absolutizeModuleScriptSrc(html, ctx.path) } } }`. `configureServer` is a deliberate no-op (Vitest runs it at startup); the coder makes it `server.middlewares.use(createEntryRoutingMiddleware({ root: server.config.root }))`. The hook shape (object with `order: "pre"` + `handler`) is frozen.
- `frontend/vite.config.ts` — `import { devEntryRoutingPlugin } from "./dev/entryRouting.ts"`; `plugins: [react(), devRequestLogPlugin(), devEntryRoutingPlugin()]` — changed (was `[react(), devRequestLogPlugin()]`)
- Caller-compile edits (out of Source-files scope): None.
- D4 finding: `frontend/dev/requestLog.ts` **already snapshots `req.url` at middleware entry** (`const url = readField(req, "url")` before `next()`, captured in the `log` closure; only `statusCode` is read at finish). DoD-15 therefore implies **no** requestLog edit; it stays untouched.
- Gates at freeze: `npm run typecheck` clean (both configs); `npm run build` succeeds; `npm test` 158 files / 4520 tests pass (no startup abort).

## Tests

### Tests (2026-10-07)
- `frontend/tests/entry-routing.test.ts` — covers DoD-1..DoD-13 — routing middleware (`createEntryRoutingMiddleware`) table: 302 redirects, entry/app rewrites, pass-throughs (/api, Vite internals, extensions, injected and default predicate on a real temp root), path escape, non-GET/HEAD, never-throws cases; `absolutizeModuleScriptSrc` rewrite and unchanged cases
- `frontend/tests/entry-routing.test.ts` — covers DoD-14, DoD-15, DoD-16 — plugin name/apply/`transformIndexHtml` (pre)/`configureServer`; request-log + routing chain logs the browser path; vite.config wiring order and side-effect-free fresh import
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓, DoD-17 [existing test files, unedited], DoD-18..21 [manual/live, no test]

## Notes & Issues

- fast/008 DoD-16 expected `curl http://localhost:8193/` to log `GET / 404 <n>ms`. This
  feature supersedes that, and the expected line is now `GET / 200 <n>ms` (DoD-21). It is
  not a regression of fast/008.
- `frontend/dev/requestLog.ts` is a **conditional** source file (context.md D4). The
  coder edits it only if it reads `req.url` at finish. Either way, record which case held
  under `## Files Changed`.
