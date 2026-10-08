# Fast feature 007 — vite-proxy-request-log

| Status  | Verifier | Date |
|---------|----------|------|
| done    | PASS     | 2026-10-07 |

## Files Changed

- `frontend/dev/proxyLog.ts` — filled stubs: path redaction, line formatters, per-request proxy event logger, `configure` hook
- `frontend/vite.config.ts` — `/api` proxy rule in object form wiring `configureProxyLogging` (skeleton wiring, unchanged by coder)

## Skeleton

### Frozen interface (2026-10-07)
- `frontend/dev/proxyLog.ts` — `export interface ProxyEmitter { on(event: string, listener: (...args: unknown[]) => void): unknown; }` — new (verified: Vite's `ProxyServer` and a plain `node:events` `EventEmitter` are both assignable, under both tsconfigs)
- `frontend/dev/proxyLog.ts` — `export interface ProxyLogOptions { sink?: (line: string) => void; now?: () => number; }` — new
- `frontend/dev/proxyLog.ts` — `export function redactPath(url: string | undefined): string` — new (stub throws)
- `frontend/dev/proxyLog.ts` — `export function formatSuccessLine(method: string | undefined, url: string | undefined, status: number | undefined, durationMs: number): string` — new (stub throws)
- `frontend/dev/proxyLog.ts` — `export function formatErrorLine(method: string | undefined, url: string | undefined, err: unknown): string` — new (stub throws)
- `frontend/dev/proxyLog.ts` — `export function attachProxyLogging(proxy: ProxyEmitter, options?: ProxyLogOptions): void` — new (stub throws)
- `frontend/dev/proxyLog.ts` — `export const configureProxyLogging: NonNullable<ProxyOptions["configure"]>` (`ProxyOptions` type-imported from `"vite"`), i.e. `(proxy) => void` — new. **Stub is a no-op, not a throw** — see Notes & Issues. Coder fills it as `attachProxyLogging(proxy)`.
- `frontend/vite.config.ts` — added `import { configureProxyLogging } from "./dev/proxyLog";` (extensionless; resolves under `moduleResolution: "bundler"` in both tsconfigs and in Vite's config bundler); `server.proxy` is now `{ "/api": { target: "http://localhost:8184", configure: configureProxyLogging } }` — changed (was `{ "/api": "http://localhost:8184" }`). No other key touched.
- Test import specifier: `../dev/proxyLog` from `frontend/tests/`.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean (both configs); `npm run build` succeeds with the same entry/asset set, no chunk from `dev/`; `npm test` 156 files / 4441 tests pass, incl. `tests/build-config.test.ts` unedited.

## Tests

### Tests (2026-10-07)
- `frontend/tests/proxy-log.test.ts` — covers DoD-1 — `redactPath` cuts at first `?` and at `#`, leaves other paths byte-identical, `-` for missing/empty.
- `frontend/tests/proxy-log.test.ts` — covers DoD-2 — `formatSuccessLine` exact `GET /api/sessions 200 12ms`, rounding (12.4→12, 12.6→13), `-` for missing method/status.
- `frontend/tests/proxy-log.test.ts` — covers DoD-3 — `formatErrorLine` exact `... proxy error ECONNREFUSED`, `unknown` for codeless/non-object/empty/non-string code, message text never appears.
- `frontend/tests/proxy-log.test.ts` — covers DoD-4, DoD-5, DoD-6 — `attachProxyLogging` on a plain `EventEmitter` with injected sink/clock: one line per start→proxyRes, no trailing newline, proxyReq fallback, `0ms` with no start, interleaved requests keep their own durations/paths.
- `frontend/tests/proxy-log.test.ts` — covers DoD-7 — one error line per `error`; proxyRes+error in either order yields only the first line; malformed listener args never throw.
- `frontend/tests/proxy-log.test.ts` — covers DoD-8 — sentinels in query, fragment, headers, cookie, response headers, bodies, target and error message never reach the sink.
- `frontend/tests/proxy-log.test.ts` — covers DoD-9 — loaded config `server.proxy` keys = [`/api`], target `http://localhost:8184`, `configure` is a function; driving it with a fake `EventEmitter` writes one `\n`-terminated line via a spied `process.stdout.write`. (`build-config.test.ts` unedited — verifier runs it.)
- `frontend/tests/proxy-log.test.ts` — covers DoD-10 — fresh `import("../dev/proxyLog")` after `vi.resetModules()` makes zero `process.stdout.write` calls.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 [manual/live, no test], DoD-12 [manual/live, no test]

## Notes & Issues

- **Skeleton (2026-10-07): `configure` is NOT inert under Vitest.** `context.md` states `configure` is "inert under `vite build` and under Vitest". Verified false for Vitest: Vitest creates a Vite server via `createViteServer`, whose `proxyMiddleware` calls every rule's `configure` at startup. A throwing `configureProxyLogging` stub aborted every Vitest run with a startup error. Consequences: (1) the skeleton's `configureProxyLogging` is a no-op instead of a throw (it cannot accidentally satisfy DoD-9, which requires a stdout write); (2) the final implementation **must not throw or write at attach time** — `attachProxyLogging` with defaults will run once per Vitest startup, so it may only subscribe listeners (no output occurs since no request crosses Vitest's proxy). `vite build` does not call it. Vite also prints a non-fatal `configLoader: 'native'` advisory about the extensionless `./dev/proxyLog` import (alongside the pre-existing `__dirname` one); left as-is because `.ts` specifiers would require `allowImportingTsExtensions`.
