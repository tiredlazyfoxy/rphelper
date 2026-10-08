# fast/009.vite-dev-root-routing — plan

## Goal

Make the Vite dev server on :8193 answer the same URL space as prod nginx:
- `/` and every app client route serve the `app` document;
- `/bootstrap/…`, `/login/…` and `/admin/…` serve their own entry documents;
- the slash-less `/bootstrap`, `/login` and `/admin` get a relative 302.

A serve-only plugin delivers this with an early URL-rewriting middleware and a
`transformIndexHtml` hook. The hook makes the entry's relative module script absolute.

## Source files

```
frontend/dev/entryRouting.ts   # new — routing middleware factory, src-absolutizer, dev plugin factory, plugin-name constant
frontend/vite.config.ts        # import ./dev/entryRouting.ts; append the plugin after devRequestLogPlugin()
frontend/dev/requestLog.ts     # CONDITIONAL — only if it reads req.url at finish: snapshot the URL at entry (context.md D4)
```

## Test files

```
frontend/tests/entry-routing.test.ts
```

`frontend/tests/request-log.test.ts`, `build-config.test.ts`, `entries.test.tsx` and
`proxy-log.test.ts` are **not** in scope. Do not edit them. They must keep passing
(DoD-17).

## Interface intent

**`frontend/dev/entryRouting.ts`.** This is a new module with no import side effects:
importing it registers nothing and writes nothing. It follows the `requestLog.ts`
pattern (context.md "Typecheck reach"):
- it compiles under both tsconfigs;
- relative imports end in `.ts`;
- it may import `node:fs` and `node:path`;
- it uses no DOM API.

- **Plugin-name constant.** An exported string constant naming the plugin. The suggested
  value is `"rphelper-dev-entry-routing"`, and the skeleton freezes the exact string. It
  must not contain `react`.

- **Request/response shapes.** Use structural, `unknown`-typed request and response
  interfaces, as in `requestLog.ts`:
  - The request has a mutable `url` and a `method`.
  - The response supports setting the status code and a header, and ending the response.

  Node's `IncomingMessage`/`ServerResponse` must satisfy them, so
  `server.middlewares.use` accepts the middleware without a cast. Plain
  `EventEmitter`-based fakes must satisfy them too. The skeleton picks the exact members.
  The middleware never reads or writes `req.originalUrl`.

- **Routing middleware factory.** It takes an options object:
  - the server **root**, an absolute directory;
  - an optional **file-existence predicate** from an absolute path to a boolean. By
    default the predicate is true only for an existing regular file (a stat-based
    is-file check). A missing path, a directory or an error gives false.

  The factory returns a Connect-style middleware `(req, res, next)`. Per request:
  1. If the method is neither GET nor HEAD, or `req.url` is not a string, call `next()`
     with `req.url` unchanged.
  2. Take the pathname from `req.url` (drop the query and fragment) and percent-decode
     it.
  3. **Pass through** (call `next()`, URL unchanged) when any of these holds:
     - the pathname is `/api` or starts with `/api/`;
     - the pathname starts with `/@`, `/__` or `/node_modules/`;
     - the last path segment contains a `.`, so it has a file extension. Module and
       asset requests are never turned into HTML, even when they are missing;
     - the decoded pathname, resolved under root, stays **inside** root and the
       predicate says it is an existing file. A path that escapes root counts as "not a
       file".
  4. If the pathname is **exactly** `/bootstrap`, `/login` or `/admin`, respond with
     status **302** and `Location: /<entry>/`. The Location is relative, and the query
     string is dropped. End the response and do **not** call `next()`.
  5. If the pathname starts with `/bootstrap/`, `/login/` or `/admin/` (the bare
     `/login/` included), set `req.url` to `/<entry>/index.html` and call `next()`.
  6. Otherwise, set `req.url` to `/app/index.html` and call `next()`.

  A rewritten `req.url` carries no query string. The middleware never inspects `Accept`
  or `sec-fetch-*`.

  It **never throws**. That includes a malformed percent-encoding, missing or odd-typed
  fields, and a throwing predicate. On any internal error before a response is begun,
  it calls `next()` once, with `req.url` restored to its original value. `next()` is
  called at most once per request, synchronously, with no argument.

- **Script-src absolutizer (pure, exported).** It takes an HTML string and the served
  document's URL path (the hook context's `path`, for example `/app/index.html`; any
  query or fragment is ignored). It returns the HTML in which every `<script>` with
  `type="module"` and a **relative** `src` has that src replaced by an absolute path,
  resolved against the document's directory with URL semantics. For example:
  - `./main.tsx` against `/app/index.html` gives `/app/main.tsx`;
  - `./main.tsx` against `/bootstrap/index.html` gives `/bootstrap/main.tsx`;
  - `../x.ts` against `/app/index.html` gives `/x.ts`.

  The following are returned unchanged:
  - a src that is root-absolute (`/…`), protocol-relative (`//…`) or has a scheme
    (`http:`, `data:`, …);
  - a script that is not a module script;
  - all other markup.

  Quote style is preserved, and other attributes are left as they are. The function
  never throws. Given an unusable document path, it returns the input unchanged.

- **Dev plugin factory.** It takes no arguments and returns a Vite `Plugin` with:
  - `name` set to the constant above;
  - `apply: "serve"`;
  - `configureServer(server)`, which registers **exactly one** middleware from the
    factory **directly** with `server.middlewares.use(...)`, passing
    `server.config.root` as root. It **returns nothing**, so there is no post-hook;
  - a `transformIndexHtml` hook, ordered `pre`, that returns the absolutizer's output
    for the incoming HTML and `ctx.path`.

  Attaching the plugin writes nothing and cannot throw.

**`frontend/vite.config.ts`.**
- Import the plugin factory from `./dev/entryRouting.ts`.
- `plugins` becomes `[react(), devRequestLogPlugin(), devEntryRoutingPlugin()]`.
- Nothing else changes: `root`, the inputs, the `server` block, the proxy, the `build`
  and `test` blocks, and the literals.

**`frontend/dev/requestLog.ts` (conditional).** Edit this file **only** if the logged
path is read from `req.url` when `finish`/`close` fires.
- If so, snapshot the URL at middleware entry, before `next()` runs, and format that
  snapshot at finish. The status stays read at finish.
- No exported signature or frozen name changes, and no other behaviour changes.
- If the logger already snapshots at entry, leave the file untouched and say so in
  `## Files Changed`.

## Definition of done

Unless a DoD item states otherwise, "routes to X" means that after one middleware call:
- `req.url === X`;
- `next` has been called exactly once, with no argument;
- the response was not ended, and no status or header was set.

"Untouched" means the same, with `req.url` equal to its input.

1. `[test]` Slash-less entries:
   - `GET /login`, `GET /bootstrap` and `GET /admin` each get status 302, `Location`
     equal to `/login/`, `/bootstrap/` or `/admin/` respectively (relative), and the
     response ended. `next` is **not** called.
   - `GET /login?next=x` also redirects to `Location: /login/`, with the query dropped.
   - `HEAD /login` gets the same 302.
2. `[test]` Entry deep links:
   - `/admin/users` routes to `/admin/index.html`;
   - `/login/reset?x=1` routes to `/login/index.html`;
   - `/bootstrap/step/2` routes to `/bootstrap/index.html`.
3. `[test]` Bare entry directories: `/login/`, `/admin/` and `/bootstrap/` route to
   their own `/<entry>/index.html`.
4. `[test]` App navigations:
   - `/`, `/sessions/5`, `/characters/7?x=1` and `/app/` each route to
     `/app/index.html`;
   - a non-entry slash-less path such as `/loginx` routes to `/app/index.html`;
   - so does `/apiary`.
5. `[test]` `/api`, `/api/`, `/api/x` and `/api/health?q=1` are untouched.
6. `[test]` `/@vite/client`, `/@fs/abs/path`, `/__open-in-editor?file=a`,
   `/__vite_ping` and `/node_modules/x` are untouched, including `/node_modules/.vite/deps/react`.
7. `[test]` Paths with an extension in the last segment are untouched whether or not the
   predicate reports a file. Examples: `/missing.png`, `/app/main.tsx`,
   `/sessions/main.tsx`, `/app/index.html`, `/favicon.ico`.
8. `[test]` An extensionless path for which the injected predicate returns true is
   untouched. The predicate receives an absolute path inside the injected root that
   corresponds to the decoded pathname. When the same path's predicate returns false,
   it routes to `/app/index.html`.
9. `[test]` Default predicate, with a real temporary root directory containing an
   extensionless file and an entry-named sub-directory:
   - the extensionless file is untouched;
   - the directory path with a trailing slash (`/login/`) still routes to
     `/login/index.html`, because a directory is not a file.
10. `[test]` Path escape: a request whose decoded pathname resolves outside root
    (`..` segments, encoded or not) is never passed through as "existing file". The
    predicate is not consulted with an outside path, or its true result is ignored.
11. `[test]` Non-GET/HEAD requests (`POST /`, `PUT /login`, `DELETE /sessions/5`) and
    requests with a missing method are untouched.
12. `[test]` The middleware never throws. Each of these leaves `req.url` equal to its
    input (or absent) and calls `next` exactly once:
    - a malformed percent-encoding (e.g. `/%E0%A4%A`);
    - a non-string or missing `url`;
    - a predicate that throws;
    - a response object missing methods.
13. `[test]` Script-src absolutizer:
    - `<script type="module" src="./main.tsx">` against `/app/index.html` gives
      `src="/app/main.tsx"`;
    - against `/bootstrap/index.html` it gives `/bootstrap/main.tsx`;
    - a bare `main.tsx` and a `../shared/x.ts` resolve the same way;
    - root-absolute, protocol-relative, `http(s):` and `data:` srcs are unchanged;
    - a non-module `<script src="./legacy.js">` is unchanged;
    - the rest of the document (the `<div id="root">`, other tags) is byte-identical;
    - a query on the document path is ignored;
    - an unusable document path returns the input unchanged, and nothing throws.
14. `[test]` The plugin factory returns a plugin with:
    - `name` equal to the frozen constant, which does not contain `react`;
    - `apply === "serve"`;
    - a `transformIndexHtml` hook, which with HTML and a context `path` of
      `/app/index.html` yields HTML whose module script src is `/app/main.tsx`.

    Its `configureServer`, invoked with a fake server providing `config.root` and a
    `middlewares.use` that records its arguments:
    - registers exactly one function;
    - returns `undefined`;
    - writes nothing to stdout.

    That registered function routes `GET /` to `/app/index.html`.
15. `[test]` Log interplay. A fake request is chained through fast/008's request-log
    middleware (injected sink and clock) and then through this routing middleware, and
    the response emits `finish` with status 200. For `GET /`, the logged line is
    `GET / 200 <d>ms`, not `/app/index.html`. For `GET /sessions/5?q=SECRET`, it is
    `GET /sessions/5 200 <d>ms`.
16. `[test]` Wiring and hygiene:
    - The loaded Vite config (`../vite.config`) has, among its flattened plugins,
      exactly one plugin with the frozen entry-routing name, placed after the
      request-log plugin.
    - `frontend/dev/entryRouting.ts`, imported fresh after a module reset, makes zero
      `process.stdout.write` calls.
17. `[test]` `frontend/tests/build-config.test.ts`, `entries.test.tsx`,
    `request-log.test.ts` and `proxy-log.test.ts` pass **unedited**. Those existing
    files cover this item; nothing new is written for it.
18. `[manual/live]` `npm run typecheck` passes for both configs. `npm test` is fully
    green. `npm run build` succeeds and emits the same four HTML entries as before, with
    no chunk originating from `dev/`.
19. `[manual/live]` With `npm run dev` (or `start.sh`) running:
    - `curl -i http://localhost:8193/` gives 200 HTML whose module script src is
      `/app/main.tsx`;
    - `curl -i http://localhost:8193/sessions/5` gives 200 with the app document;
    - `curl -i http://localhost:8193/admin/users` gives 200 with the admin document
      (src `/admin/main.tsx`);
    - `curl -i http://localhost:8193/login` gives 302 with `Location: /login/`;
    - `curl -i http://localhost:8193/api/health` still reaches the backend.
20. `[manual/live]` In a browser, `http://localhost:8193/` renders the app: the module
    loads, the network panel shows no 404 for `/main.tsx`, and HMR connects. A reload on
    `/sessions/<id>` stays on the app document.
21. `[manual/live]` The dev console shows `GET / 200 <n>ms` for `curl
    http://localhost:8193/`. This supersedes fast/008 DoD-16's `GET / 404` expectation.

## Out of scope

- Editing the entry HTML files, `root`, the build inputs, or adding a root/fifth HTML
  document.
- Changes to `start.sh`, `start.ps1`, the compose files, the Dockerfile, `docker/nginx.conf`,
  or `docker/nginx.dev.conf`. Removing that unused file belongs to fast/001's
  finalization.
- Serving `/index.html` itself in dev. Prod has it as an image-time copy; in dev the
  extension rule passes it through untouched. Nothing links to it.
- Accept-header or `sec-fetch-dest` gating, and any HTML-vs-asset sniffing beyond the
  path predicate.
- Changing fast/008's line format, its `/api` skip, or its status-at-finish rule.
- Editing `request-log.test.ts`, `build-config.test.ts`, `entries.test.tsx`,
  `proxy-log.test.ts`, or any earlier plan document.
- WebSocket upgrades (HMR). They bypass Connect middlewares.
