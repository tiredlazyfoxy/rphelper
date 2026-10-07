# fast/008.vite-dev-request-log — plan

## Goal

Make the Vite dev server print one line per request it receives (pages, modules, assets
and Vite internals), in 007's `<METHOD> <path> <status> <ms>ms` shape. `/api` requests
are skipped because 007's proxy logger already covers them. In the same change, remove
both `configLoader: 'native'` advisory items: the extensionless import and `__dirname`.

## Source files

```
frontend/dev/requestLog.ts     # new — request-log middleware factory + Vite plugin factory
frontend/dev/proxyLog.ts       # additive only — expose default sink/clock for reuse (context.md D2)
frontend/vite.config.ts        # add the plugin; ".ts" import specifiers; import.meta.dirname
frontend/tsconfig.json         # add allowImportingTsExtensions: true
frontend/tsconfig.node.json    # add allowImportingTsExtensions: true
```

## Test files

```
frontend/tests/request-log.test.ts
```

`frontend/tests/build-config.test.ts` and `frontend/tests/proxy-log.test.ts` are **not**
in scope. They must not be edited, and they must keep passing as-is (DoD-10).

## Interface intent

**`frontend/dev/requestLog.ts`.** A new module with no side effects: importing it
registers nothing and writes nothing. It must compile under both tsconfigs, use no DOM
API and read no environment (`context.md`, "Typecheck reach"). Relative imports use the
`.ts` extension. It reuses `redactPath`/`formatSuccessLine` and `ProxyLogOptions` from
`./proxyLog.ts`. It does not reimplement them.

- **Request-log middleware factory.** It takes optional `ProxyLogOptions` (the line sink
  and the clock, as in 007). When omitted, it uses the same defaults as 007: stdout with a
  trailing `"\n"`, and `performance.now()`. It returns a Connect-style middleware, a
  function of request, response and `next`. The middleware's per-request behaviour:
  - If the request URL is a string that starts with `/api`, call `next()` and do nothing
    else.
  - Otherwise, read the clock and subscribe once to the response's `finish` and `close`.
    Then call `next()` with no argument, synchronously, exactly once.
  - On the first of the two events, emit exactly one line through the sink, using
    `formatSuccessLine`. The line has:
    - the request method (`-` if missing);
    - the raw URL (redacted by the formatter; `-` if missing);
    - for `finish`, the response's `statusCode` read at that moment;
    - for `close` with no prior `finish`, a missing status, which renders as `-`;
    - `now - start` as the duration.
  - Later events for the same request write nothing.
  - It never throws, out of itself or out of a listener, for missing or malformed
    request/response fields. It never reads headers, cookies or bodies into the line.

  The request and response parameter types must accept Node's `IncomingMessage` /
  `ServerResponse`, so Vite's `server.middlewares.use` takes the middleware without a
  cast. They must also accept plain `EventEmitter`-based fakes with `url`, `method` and
  `statusCode` fields. The skeleton picks a structural or Node-typed shape to satisfy
  both.
- **Dev request-log plugin factory.** It takes the same optional options and returns a
  Vite `Plugin` with:
  - a stable, descriptive `name`, for example `rphelper-dev-request-log`. The skeleton
    freezes the exact string, and the test asserts that frozen name;
  - `apply: "serve"`;
  - a `configureServer` hook that registers one middleware from the factory **directly**
    on `server.middlewares` and returns nothing, so there is no post-hook (`context.md`
    D7).

  Attaching writes nothing and cannot throw. Vitest runs this hook.

**`frontend/dev/proxyLog.ts`.** Additive changes only. If needed, it may expose the
default sink and the default clock, or a small options resolver, so `requestLog.ts`
reuses them instead of duplicating them. The skeleton decides the shape. Every existing
export keeps its frozen signature and behaviour (`fast/007` `## Skeleton`). The module
stays free of import side effects.

**`frontend/vite.config.ts`.**
- The proxy-log import specifier becomes `./dev/proxyLog.ts`. The new plugin is imported
  from `./dev/requestLog.ts`.
- `frontendDir` is `import.meta.dirname`, and `__dirname` no longer appears anywhere in
  the file.
- `plugins` becomes `react()` followed by the dev request-log plugin, called with
  defaults.
- Nothing else changes: the `server` block, the `/api` rule and its `configure`, the
  `build` and `test` blocks, and the literals `8193`/`8184`.

**`frontend/tsconfig.json`, `frontend/tsconfig.node.json`.** Each gains
`"allowImportingTsExtensions": true` in `compilerOptions`. Nothing else changes.

## Definition of done

1. `[test]` For a non-`/api` request (e.g. `GET /app/?q=SENTINEL#frag`), the middleware
   with an injected sink and clock writes nothing until the response emits `finish`.
   Then it writes exactly one line, `GET /app/ 200 <d>ms`, where `<d>` is the clock
   difference between middleware entry and `finish`. The line has no trailing newline,
   and the sentinel and fragment are absent.
2. `[test]` The status in the line is the response's `statusCode` at `finish` time, not
   at entry. For example, a response whose status is set to 404 after the middleware ran
   logs `GET / 404 <d>ms`.
3. `[test]` Requests whose URL starts with `/api` (`/api`, `/api/sessions?x=1`,
   `/apiary`) produce no line from this middleware, even after `finish`/`close`.
   `next()` is still called.
4. `[test]` For both logged and skipped requests, `next` is called exactly once,
   synchronously, with no argument. The middleware never ends or writes to the response
   itself.
5. `[test]` `finish` followed by `close` writes exactly one line. `close` without a
   prior `finish` writes exactly one line whose status position is `-`. A request whose
   response emits neither writes nothing.
6. `[test]` Two interleaved requests on distinct request/response objects each get their
   own path, status and duration.
7. `[test]` A request with no `url` and/or no `method` is logged with `-` in the missing
   position(s), not skipped, and nothing throws. Calling the middleware with malformed
   request/response objects does not throw.
8. `[test]` Redaction sentinel sweep: distinct sentinels go into the URL query, the
   fragment, request headers, the cookie, response headers, and request/response body
   writes. No sentinel appears in any sink output.
9. `[test]` The plugin factory returns a plugin with:
   - the frozen `name` and `apply` equal to `"serve"`;
   - a `configureServer` that, when invoked with a fake server whose `middlewares.use`
     records its arguments, registers exactly one function, returns `undefined`, and
     makes no `process.stdout.write` call.

   The registered function, driven with a fake non-`/api` request through `finish`,
   writes one `"\n"`-terminated line via `process.stdout.write` (default sink).
10. `[test]` The loaded Vite config (`../vite.config`) has, among its flattened
    `plugins`, exactly one plugin with the frozen request-log name, placed after the
    React plugin(s). Also, `frontend/tests/build-config.test.ts` and
    `frontend/tests/proxy-log.test.ts` pass **unedited**. This includes the absolute
    `root` / `build.outDir` / `test.root` resolution now computed from
    `import.meta.dirname` (`context.md`, escape valve).
11. `[test]` Source-text checks on `frontend/vite.config.ts`:
    - the identifier `__dirname` does not appear;
    - `import.meta.dirname` does;
    - every relative import specifier (`"./…"` or `"../…"`) ends in `.ts`.

    The same `.ts`-ending check applies to every relative import specifier in each
    `frontend/dev/*.ts` file.
12. `[test]` `frontend/tsconfig.json` and `frontend/tsconfig.node.json` each have
    `compilerOptions.allowImportingTsExtensions === true`, with `noEmit` still `true`.
13. `[test]` Importing `frontend/dev/requestLog.ts` fresh, after a module reset, makes
    zero `process.stdout.write` calls.
14. `[manual/live]` `npm run typecheck` passes for both configs. `npm test` is fully
    green. `npm run build` succeeds with the same set of emitted entry files as before,
    with no chunk originating from `dev/`.
15. `[manual/live]` Starting `npx vite` (or `start.sh`) prints **no** `configLoader:
    'native'` advisory. In particular, it names neither `__dirname` nor an extensionless
    import.
16. `[manual/live]` With the dev pair running:
    - `curl http://localhost:8193/` prints `GET / 404 <n>ms`;
    - `curl http://localhost:8193/app/` prints `GET /app/ 200 <n>ms`;
    - loading `/app/` in a browser prints lines for `/@vite/client` and module/asset
      requests;
    - `curl 'http://localhost:8193/api/health?q=secret'` prints exactly one line, from
      007's proxy logger, `GET /api/health <status> <n>ms`, and `secret` appears nowhere
      in the output.

## Out of scope

- Fixing the `GET /` 404 or the `/app/` vs root seam (`deployment.md`, owned by
  `fast/001.dev-and-container-harness`).
- Logging HMR websocket upgrades, or anything that bypasses Connect middlewares.
- Changing 007's proxy logger behaviour, its line formats, or the `/api` rule.
- Switching Vite to `configLoader: 'native'`, or adding any launcher flag. Only the
  advisory's causes are removed.
- Filtering or sampling noisy requests (HMR pings, assets). Every request is logged by
  user decision.
- Log levels, colours, timestamps, toggles, env-controlled verbosity.
- New npm scripts, new dependencies, and launcher changes (`start.sh`, `start.ps1`).
- Editing `build-config.test.ts`, `proxy-log.test.ts`, or any 002/007 plan document.
