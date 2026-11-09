# Fast feature 008 — vite-dev-request-log

| Status  | Verifier | Date |
|---------|----------|------|
| done    | PASS     | 2026-10-07 |

## Files Changed

- `frontend/dev/requestLog.ts` — filled `createRequestLogMiddleware` (skip `/api`, one line on first `finish`/`close`, guarded) and `devRequestLogPlugin.configureServer` (registers the middleware directly); added private `readField` helper
- `frontend/dev/proxyLog.ts` — skeleton-stage only (exported `defaultSink`/`defaultNow`); no coder change
- `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json` — skeleton-stage only; no coder change

## Skeleton

### Frozen interface (2026-10-07)
- `frontend/dev/proxyLog.ts` — `export function defaultSink(line: string): void` — changed (was module-private `function defaultSink`; now exported, body unchanged: `process.stdout.write(line + "\n")`). D2 shared default.
- `frontend/dev/proxyLog.ts` — `export function defaultNow(): number` — changed (was module-private `function defaultNow`; now exported, body unchanged: `performance.now()`). D2 shared default. All other 007 exports untouched.
- `frontend/dev/requestLog.ts` — `export interface RequestLike { url?: unknown; method?: unknown; }` — new (structural; `IncomingMessage` and `EventEmitter` fakes both fit).
- `frontend/dev/requestLog.ts` — `export interface ResponseLike { statusCode?: unknown; on(event: string, listener: (...args: unknown[]) => void): unknown; }` — new (structural; `ServerResponse` and `EventEmitter` fakes both fit).
- `frontend/dev/requestLog.ts` — `export type RequestLogMiddleware = (req: RequestLike, res: ResponseLike, next: () => void) => void` — new. Verified assignable to `ViteDevServer["middlewares"].use(...)` without a cast, and callable with `Object.assign(new EventEmitter(), {...})` fakes.
- `frontend/dev/requestLog.ts` — `export const REQUEST_LOG_PLUGIN_NAME = "rphelper-dev-request-log"` — new. **Frozen plugin name: `rphelper-dev-request-log`.**
- `frontend/dev/requestLog.ts` — `export function createRequestLogMiddleware(options?: ProxyLogOptions): RequestLogMiddleware` — new (**stub throws** `not implemented`).
- `frontend/dev/requestLog.ts` — `export function devRequestLogPlugin(options?: ProxyLogOptions): Plugin` (`Plugin` type-imported from `"vite"`) — new. Returns `{ name: REQUEST_LOG_PLUGIN_NAME, apply: "serve", configureServer(): void }`. **Stub `configureServer` is a no-op, not a throw** (Vitest runs it at startup; a no-op registers zero middlewares, so DoD-9 stays red). Coder fills it with `server.middlewares.use(createRequestLogMiddleware(options))`, no return value.
- `frontend/dev/requestLog.ts` imports only `import type { ProxyLogOptions } from "./proxyLog.ts"` so far (value imports of `redactPath`/`formatSuccessLine`/`defaultSink`/`defaultNow` are the coder's to add once used; `noUnusedLocals`). Module has no import side effects.
- `frontend/vite.config.ts` — imports now `./dev/proxyLog.ts` and `./dev/requestLog.ts` (`devRequestLogPlugin`); `frontendDir = import.meta.dirname` (no `__dirname` left); `plugins: [react(), devRequestLogPlugin()]`. Nothing else changed.
- `frontend/tsconfig.json`, `frontend/tsconfig.node.json` — added `"allowImportingTsExtensions": true` (after `noEmit: true`). Nothing else changed.
- Test import specifier: `../dev/requestLog` (or `../dev/requestLog.ts`) from `frontend/tests/`.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean (both configs); `npm run build` succeeds, same 4 HTML entries, no `dev/` chunk, no `configLoader: 'native'` advisory printed; `npm test` 157 files / 4484 tests pass. `import.meta.dirname` checked under Vitest: `tests/build-config.test.ts` and `tests/proxy-log.test.ts` (unedited) pass, including the `root` / `build.outDir` / `test.root` path assertions, so the escape valve did not fire.

## Tests

### Tests (2026-10-07)
- `frontend/tests/request-log.test.ts` — covers DoD-1..DoD-13 — middleware (injected sink/clock, EventEmitter fakes): finish-time line shape/redaction, status read at finish, `/api` prefix skip, `next()` once/sync/no-arg and response untouched, finish/close once-only with close-only status `-`, interleaving, missing url/method as `-` and no-throw on malformed inputs, sentinel sweep; plugin name/apply/configureServer (one registration, returns undefined, silent; registered fn writes one `\n`-terminated stdout line; injected options pass through); vite.config plugin order; source-text `__dirname`/`import.meta.dirname`/`.ts` specifiers in `vite.config.ts` and `dev/*.ts`; tsconfig flags; side-effect-free import.
- DoD-10's "build-config.test.ts and proxy-log.test.ts pass unedited" part is covered by those existing files themselves (not edited).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14..16 [manual/live, no test]

## Notes & Issues

_populated by the coder when worth saying_
