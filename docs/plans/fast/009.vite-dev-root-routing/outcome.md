# fast/009.vite-dev-root-routing — outcome

Intended documentation changes, applied by the architect at finalization.

## docs/architecture/deployment.md

1. **Target:** "The app document at `/` — prod and dev", the **"Dev mechanism"**
   paragraph and bullets.
   - **Change:** Retitle the heading from "decided, to be built by an upcoming fast
     feature" to "as built by `fast/009.vite-dev-root-routing`". Name
     `frontend/dev/entryRouting.ts` and the plugin `rphelper-dev-entry-routing` (the
     frozen name from `status.md` `## Skeleton`). Record its position in
     `vite.config.ts`: `[react(), devRequestLogPlugin(), devEntryRoutingPlugin()]`.
   - **Reason:** The mechanism is now built. The doc should point at the file.

2. **Target:** same section, the bullet "It never touches `/api` … The exact predicate
   is the plan's to fix".
   - **Change:** Record the as-built predicate, which applies to GET/HEAD only:
     - pass through `/api` and `/api/…`, `/@…`, `/__…` and `/node_modules/…`;
     - pass through any path whose last segment has an extension;
     - pass through any decoded path resolving to an existing **regular file** inside
       root (a directory such as `/login/` is not a file);
     - exact `/bootstrap|/login|/admin` gets a relative 302 to the slash form, with the
       query dropped;
     - `/<entry>/…` (including the bare `/<entry>/`) is rewritten to
       `/<entry>/index.html`;
     - everything else is rewritten to `/app/index.html`;
     - the rewritten URL carries no query, and `req.originalUrl` is untouched;
     - there is no Accept or `sec-fetch-dest` gating, mirroring nginx's path-only
       `try_files`;
     - on internal error the request passes through unchanged.
   - **Reason:** The doc explicitly left the predicate to the plan.

3. **Target:** same section, the **"Rewrite, not redirect"** bullet.
   - **Change:** Confirm the as-built detail, consistent with the parallel correction.
     Vite 8.3.1 does **not** absolutize the entries' relative
     `<script type="module" src="./main.tsx">`. The plugin's own `transformIndexHtml`
     hook (pre order, serve-only through `apply`) rewrites relative **module** script
     srcs to absolute paths against the served document's directory (`ctx.path`). For
     example, `/app/index.html` gives `/app/main.tsx`. The entry HTML stays relative,
     because `tests/entries.test.tsx` resolves the src against the file.
   - **Reason:** This dependency is non-obvious. Removing the hook breaks `/` in dev
     silently, as a module 404 on `/main.tsx`.

4. **Target:** "Decision history", entry "2026-10-07 — dev serves the app at `/`".
   - **Change:** Append an item 5: `fast/009.vite-dev-root-routing` built the dev
     mechanism. fast/008 DoD-16's `GET / 404` expectation is superseded, and the dev log
     for `/` now reads `GET / 200 <n>ms`. If the coder changed `requestLog.ts`, also
     record that the request log snapshots the URL at middleware entry, so it logs the
     browser path rather than the rewritten one.
   - **Reason:** This closes the history the entry opens.

5. **Target:** "Dev topology", the Vite proxy code block and the line "Vite 6 sets no
   `server.hmr.path`".
   - **Change:** None required by this feature. Optionally add one sentence: the routing
     plugin runs before the proxy in Vite's middleware order and passes `/api` through,
     so the proxy is unaffected.
   - **Reason:** It forestalls a "does the rewrite break the proxy?" question.

## docs/architecture/frontend-structure.md

6. **Target:** wherever the doc lists the `frontend/dev/` Node-side modules
   (`proxyLog.ts`, `requestLog.ts`), or the dev-only Vite plugins beside the emitted
   layout.
   - **Change:** Add `entryRouting.ts`. It is a serve-only plugin: the dev routing
     mirror of nginx, plus relative module-script src absolutization. It does not affect
     `vite build`, and the emitted layout is unchanged (four documents, no `dev/` chunk).
   - **Reason:** It keeps the inventory of build-adjacent TypeScript complete.

## docs/architecture/quick-reference.md

7. **Target:** the paths and ports area, wherever dev URLs are listed.
   - **Change:** Dev and prod answer the same URLs: the app is at `/`, the others at
     `/<entry>/`, and slash-less entries get a 302. Remove any surviving
     "`/<entry>/index.html` in dev" phrasing.
   - **Reason:** This is consistency with the decided contract, now as built.

