# fast/007.vite-proxy-request-log — plan

## Goal

Make the Vite dev server print one line per proxied `/api` request: method, query-stripped
path, status and duration, or the error code when the backend is unreachable. The
`/api` rule changes from string form to object form, and its `configure` hook attaches a
small, separately testable logger. Build output and Vitest behaviour stay unchanged.

## Source files

```
frontend/dev/proxyLog.ts      # new — path redaction, line formatting, proxy event subscription
frontend/vite.config.ts       # change only the "/api" proxy rule to object form wiring configure
```

## Test files

```
frontend/tests/proxy-log.test.ts
```

`frontend/tests/build-config.test.ts` is **not** in scope and must not be edited. It must
keep passing as-is (see DoD-9).

## Interface intent

**`frontend/dev/proxyLog.ts`**. A side-effect-free module: importing it registers
nothing and writes nothing. It must compile under both `tsconfig.json` and
`tsconfig.node.json` (see `context.md`, "Typecheck reach"). It uses no DOM API and no
environment reads.

- **Path redaction function.** It takes a request URL string, which may be missing, and
  returns the path with everything from the first `?` removed, and everything from the
  first `#` removed. An absent or empty URL yields a fixed placeholder (`-`). It never
  decodes, normalizes or otherwise alters the remaining path.
- **Success-line formatter.** It takes a method (may be missing), a raw URL (may be
  missing), a numeric status (may be missing) and a duration in milliseconds. It returns
  exactly `<METHOD> <path> <status> <ms>ms`:
  - the path is redacted by the function above;
  - the duration is rounded to a whole non-negative integer;
  - a missing method or status renders as `-`.
- **Error-line formatter.** It takes a method (may be missing), a raw URL (may be missing)
  and an error value of unknown shape. It returns exactly `<METHOD> <path> proxy error
  <CODE>`. The code is the error's `code` property when that is a non-empty string, and
  otherwise the token `unknown` (`context.md` D6). The error's message, stack or any
  other property is never read into the line.
- **Minimal proxy-emitter type.** A structural type describing only what the logger
  needs: the ability to subscribe a listener to a named event. Vite's proxy server
  instance must be assignable to it, and so must a plain Node `EventEmitter`.
- **`attachProxyLogging`.** It takes a proxy emitter and optional options: a line sink
  (a function receiving one finished line with no trailing newline) and a clock (a
  function returning the current time in milliseconds). It subscribes to the proxy's
  `start`, `proxyReq`, `proxyRes` and `error` events:
  - It records a start time per incoming request at `start`. If no start time exists yet,
    it records one at `proxyReq` instead (`context.md` D2).
  - On `proxyRes`, it emits a success line using the request's method and URL, the
    upstream response's status code, and `now - start` as the duration.
  - On `error`, it emits an error line.
  - It emits at most one line per request (D3). When there is no recorded start time, the
    duration is 0.
  - It must not throw out of a listener for malformed or missing arguments.
  - Defaults: the sink writes the line plus `"\n"` via `process.stdout.write` (D5). The
    clock is a monotonic or wall-clock millisecond source.
  - It returns nothing meaningful.
- Optionally, a **ready-made `configure` callback**: a function with the shape of
  `ProxyOptions["configure"]` that calls `attachProxyLogging` with defaults. This is so
  `vite.config.ts` stays a one-line wiring. The skeleton decides whether this is a
  separate export or an inline arrow in the config.

**`frontend/vite.config.ts`**. Only the `server.proxy` value changes. `"/api"` maps to an
object with `target: "http://localhost:8184"` (the same string, unchanged) and a
`configure` that attaches the logger with default sink and clock. No other proxy option
is added (no `changeOrigin`, no `rewrite`). Every other key is untouched. The file still
contains the literals `8193` and `8184` and no `process.env`, `import.meta.env` or
`loadEnv`.

## Definition of done

1. `[test]` Path redaction drops everything from the first `?`. For example,
   `/api/search?q=hello world&x=1` yields `/api/search`, and a URL with a second `?` in
   the query is still cut at the first. It also drops a `#` fragment. A URL without
   either is returned unchanged. A missing or empty URL yields `-`.
2. `[test]` The success formatter produces exactly `GET /api/sessions 200 12ms` for
   method `GET`, URL `/api/sessions?limit=5`, status 200 and duration 12. A fractional
   duration is rounded to an integer. A missing method or status renders as `-` in its
   position.
3. `[test]` The error formatter produces exactly `GET /api/sessions proxy error
   ECONNREFUSED` for an error whose `code` is `ECONNREFUSED` and URL
   `/api/sessions?x=secret`. An error with no string `code` (a plain `Error`, a non-object)
   yields `unknown` as the code. The error's message text never appears in the line, even
   when the message contains the URL or query.
4. `[test]` `attachProxyLogging` on a plain `EventEmitter` with an injected sink and clock:
   - Emitting `start` and then `proxyRes` (with a status code) for one request writes
     exactly one line.
   - That line carries the method, the redacted path, the status, and the clock
     difference in ms.
   - The sink receives the line without a trailing newline.
5. `[test]` When only `proxyReq` (no `start`) precedes `proxyRes`, the duration is
   measured from `proxyReq`. When neither was seen, the line still emits, with `0ms`.
6. `[test]` Two interleaved requests, distinct request objects whose start/response
   events overlap, each get their own correct duration and path.
7. `[test]` An `error` event for a request writes exactly one error line. If both
   `proxyRes` and `error` fire for the same request, in either order, only one line is
   written in total. Listener calls with missing or malformed arguments do not throw.
8. `[test]` Nothing written by the logger contains a query string, header value, cookie,
   request or response body, or the upstream target URL. Check this by driving a request
   whose URL query, headers and cookie carry distinct sentinel strings and asserting no
   sentinel appears in any sink output.
9. `[test]` The loaded Vite config's `server.proxy` has exactly one key, `/api`. Its value
   is an object whose `target` is the string `http://localhost:8184` and whose `configure`
   is a function. Invoking that `configure` with a plain `EventEmitter` and driving a
   `start` → `proxyRes` pair results in one line, ending in `"\n"`, written via
   `process.stdout.write`. Additionally, the existing `frontend/tests/build-config.test.ts`
   passes unedited.
10. `[test]` Importing `frontend/dev/proxyLog.ts` has no side effects: no write to
    stdout occurs on import.
11. `[manual/live]` `npm run typecheck` passes for both configs, and `npm run build`
    succeeds with the same set of emitted entry files as before (no new chunk originating
    from `dev/`).
12. `[manual/live]` With the dev pair running (`start.sh`), loading the app prints lines
    like `GET /api/... 200 <n>ms` in the `[ui]` stream. A search request prints its path
    without `?q=…`. With uvicorn stopped, a request prints `<METHOD> <path> proxy error
    ECONNREFUSED`. A compose (SSE) request logs as soon as the response headers arrive,
    not after the stream ends.

## Out of scope

- The backend access log (`[api]`) and its filter.
- Vite's own built-in `http proxy error: <url>` message. It is not suppressed or rewritten.
- Changing the proxy target host (`localhost` stays), or adding `changeOrigin`, `rewrite`,
  `ws` or any other proxy option.
- Launcher changes (`start.sh`, `start.ps1`), new npm scripts, new dependencies.
- Log levels, colours, timestamps, toggles or env-controlled verbosity.
- Logging of non-`/api` Vite traffic (assets, HMR).
- The nginx access-log `_TBD:` in `deployment.md` (prod surface).
