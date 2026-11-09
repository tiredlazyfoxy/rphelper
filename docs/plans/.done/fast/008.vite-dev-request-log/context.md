# fast/008.vite-dev-request-log — context

## Problem

`fast/007.vite-proxy-request-log` (done, PASS) logs proxied `/api` calls only. The user
ran `start.sh`, opened `http://localhost:8193/` and saw nothing in the `[ui]` stream. The
request was a 404 for `/`, which is known and out of scope here (`deployment.md`, "Open
seam — the `/` fallback"). It never reached the proxy, so 007 never saw it. Vite 8 also
printed a startup advisory:

```
(!) Your Vite config uses features that are unsupported by `configLoader: 'native'` ...:
  - `__dirname` (vite.config.ts:6:21). Use `import.meta.dirname` instead
  - import "./dev/proxyLog" without a file extension (vite.config.ts:4:39). Add the file extension
```

This feature does two things in one change. It logs every request the dev server
receives, and it removes both advisory items.

## Files involved

| Path | Role |
|---|---|
| `frontend/vite.config.ts` | Existing. Imports `configureProxyLogging` from `./dev/proxyLog` with no extension. Sets `frontendDir = __dirname` and `srcDir = path.resolve(frontendDir, "src")`. Has `plugins: [react()]`, `root: srcDir`, build `outDir`/inputs via `path.resolve`, and `server` with port 8193, `strictPort`, and the `/api` object rule (target `http://localhost:8184`, `configure: configureProxyLogging`). Also has `test: { root: frontendDir, ... }`. |
| `frontend/dev/proxyLog.ts` | Existing (007). Exports `ProxyEmitter`, `ProxyLogOptions { sink?, now? }`, `redactPath`, `formatSuccessLine`, `formatErrorLine`, `attachProxyLogging`, `configureProxyLogging`. Its default sink (`process.stdout.write(line + "\n")`) and default clock (`performance.now()`) are module-private today. The module has no import side effects (007 DoD-10). |
| `frontend/dev/requestLog.ts` | New. The dev-server request logger: a connect-style middleware factory and a Vite plugin factory. |
| `frontend/tsconfig.json`, `frontend/tsconfig.node.json` | Existing. Both have `strict`, `noUnused*`, `noEmit: true`, `moduleResolution: "bundler"`, TS 5.9.3. Neither has `allowImportingTsExtensions` today. |
| `frontend/tests/build-config.test.ts` | Existing (002). Constrains this plan. It must stay green and unedited. |
| `frontend/tests/proxy-log.test.ts` | Existing (007). Imports `../dev/proxyLog` (no extension) and `../vite.config`. It must stay green and unedited. |

## External facts (Vite 8.3.1, Node 22.22, TS 5.9.3)

- `Plugin.configureServer` receives the dev server. `server.middlewares` is a Connect
  app.
- A middleware registered **directly** inside `configureServer` (not through the returned
  post-hook) runs **before** Vite's proxy, transform, static, HTML-fallback and
  not-found middlewares. So it sees every HTTP request with its original `req.url`. That
  includes pages, modules, assets and Vite internals (`/@vite/client`, `/@fs/...`,
  `/__vite_ping`).
- The HMR websocket upgrade does not pass through Connect middlewares, so it will not be
  logged. That is acceptable.
- Status and duration are only known at response end. `res` emits `finish` when the
  response has been fully handed off. In current Node it emits `close` after `finish` as
  well, and emits `close` alone when the client aborts.
- **Vitest invokes `configureServer`.** Vitest creates a real Vite server from this
  config. The plugin hook therefore runs during every test run. It may only register the
  middleware. At attach time it must not write output and must not throw. This mirrors
  007's skeleton finding about `configure`.
- Vite's proxy matches a string key `"/api"` by `url.startsWith("/api")`. The skip rule
  copies that exactly (user decision 1), so a request is either logged by the proxy
  logger or by this middleware, never both and never neither. `/apiary` is skipped
  because the proxy would also claim it.
- `import.meta.dirname` is declared on `ImportMeta` by `@types/node` 26, and Node 22.22
  supplies it at runtime.
- `allowImportingTsExtensions` is legal only with `noEmit` (or `emitDeclarationOnly`).
  Both tsconfigs already have `noEmit: true`.

## The `import.meta.dirname` risk (load-bearing)

`docs/plans/002.frontend-foundation/001.context.md` ("Building the absolute paths — use
`__dirname`, not `import.meta.url`") required `__dirname`. The reason: `build-config.test.ts`
imports `vite.config.ts` under Vitest's jsdom environment, and there `import.meta.url` is
an `http://localhost/@fs/...` URL, which made `fileURLToPath` throw.

Nobody has checked what `import.meta.dirname` evaluates to when the config is imported
from a test under Vitest's module runner. It could be correct, `undefined`, or something
URL-shaped. The existing `build-config.test.ts` assertions that `root`, `build.outDir`
and `test.root` resolve to `frontend/src`, `frontend/dist` and `frontend/` are the
check. They must pass **unedited**.

**Escape valve (binding on skeleton and coder).** If `import.meta.dirname` is wrong or
undefined under Vitest, or under Vite's config loader:

- stop;
- set status `blocked`;
- report what it evaluated to.

Do **not** work around it. No env sniffing, no `typeof __dirname` fallback, no
`process.cwd()` and no `fileURLToPath(import.meta.url)`. The user then decides whether to
keep `__dirname` and accept that advisory item.

## Constraints from existing tests (must hold unchanged)

- `vite.config.ts` source must not contain `process.env`, `import.meta.env` or `loadEnv`.
  It must contain the literals `8193` and `8184`. `import.meta.dirname` does not match
  `/import\.meta\.env/`.
- The proxy keeps exactly one key, `/api`, with target `http://localhost:8184` and the
  `configure` hook from 007. 007's DoD-9 test drives that hook and keeps only stdout
  chunks with a matching prefix, so the new middleware's output elsewhere is tolerated.
- `package.json` keeps exactly four scripts and gets no new dependency.
- TypeScript only: no `.js`/`.mjs`/`.cjs` under `frontend/`.
- The tsconfig tests assert `strict`, `noUnused*` and `noEmit` are true, that there are
  no `paths`, that `include` covers `src` and `tests`, and that there is no
  `allowJs`/`checkJs`. They do not check exact equality, so adding
  `allowImportingTsExtensions` is safe.
- 007's test imports `../dev/proxyLog` without an extension. Under
  `moduleResolution: "bundler"` that keeps resolving after the flag is added, because the
  flag permits `.ts` specifiers and does not require them.

## Typecheck reach

As in 007, `frontend/dev/*.ts` is compiled transitively under **both** tsconfigs:

- `tsconfig.node.json` reaches it through `vite.config.ts`;
- `tsconfig.json` reaches it through the tests.

So the rules from 007 apply to the new module too: no DOM API, no env reads, and no
unused locals or parameters. Because the config is also reached from `tsconfig.json`, its
`import.meta.dirname` must typecheck there as well. Node types are ambient in that
config.

**Import specifiers.** Use `.ts` for every relative import in `vite.config.ts`, and for
any relative import between `frontend/dev/` modules. Under the native config loader, Node
imports those files directly, and Node will not resolve an extensionless relative
specifier.

## Redaction rule (binding)

This follows `docs/architecture/deployment.md` → "The redaction rule" and "Access-log
lines record the path without its query string". The new line is another
access-log-shaped surface, so it obeys the same rule as 007:

- path only, cut at the first `?` and any `#`, using 007's `redactPath`;
- never headers, cookies, bodies or the query.

Method, status and duration are on the allowed list.

## User-confirmed decisions

1. Log every request the dev server receives, one line each, as
   `<METHOD> <path> <status> <ms>ms`. Reuse 007's `redactPath` and `formatSuccessLine`.
2. `/api` requests are not logged by the new middleware. The skip rule is
   `url.startsWith("/api")`.
3. Import `./dev/proxyLog.ts` with its extension, and add `allowImportingTsExtensions:
   true` to both tsconfigs.
4. Replace `__dirname` with `import.meta.dirname`.
5. Acceptance: starting `npx vite` prints no `configLoader: 'native'` advisory.

## Planner decisions

- **D1 — A separate module, `frontend/dev/requestLog.ts`.** `proxyLog.ts` stays the proxy
  logger. The new module imports the formatter from it. A plugin and middleware are a
  different mechanism from a proxy `configure` hook, and keeping them apart keeps 007's
  frozen surface untouched apart from additive exports.
- **D2 — Defaults are shared, not duplicated.** The new logger's default sink and clock
  must be the same as 007's: `process.stdout.write(line + "\n")` and `performance.now()`.
  `proxyLog.ts` may gain **additive** exports so `requestLog.ts` can reuse them, for
  example the default sink and clock, or a resolver that fills `ProxyLogOptions`. The
  skeleton picks the shape. No existing export changes signature or behaviour.
- **D3 — Duration runs from middleware entry to response end.** The clock is read when
  the middleware is invoked. The line is emitted on the first of `finish` or `close`.
  - On `finish`, the status is `res.statusCode` read at that moment, not at entry,
    because Vite's later middlewares set it.
  - On `close` with no prior `finish` (an aborted request), the status renders as `-`
    (`formatSuccessLine` with a missing status). An aborted request is visible without
    showing a status it never sent.
- **D4 — At most one line per request.** `finish` followed by `close` writes once.
- **D5 — The middleware always calls `next()` exactly once, synchronously, without an
  error argument**, for both logged and skipped requests. It never ends the response
  itself, and never throws out of itself or its listeners.
- **D6 — A missing `req.url` is logged, not skipped.** The path renders as `-`. Only a
  string URL starting with `/api` is skipped.
- **D7 — The plugin registers the middleware directly inside `configureServer` and
  returns no post-hook**, so the middleware runs first and sees the original URL. The
  plugin is `apply: "serve"`, so `vite build` does not load it. Vitest still runs it,
  which is why attaching must be silent and must not throw.
- **D8 — No prefix, colour or timestamp**, as in 007 D4.
