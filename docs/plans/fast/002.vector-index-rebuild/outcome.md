# Fast feature 002 — vector-index-rebuild — outcome

Intended documentation changes, applied by the architect at finalization. Grouped by target file.

## docs/architecture/admin-surfaces.md

- **Section:** "What the page holds, action by action" (row at ~:569). **Change:** Rebuild index → **delivered** (`fast/002`). Update the following paragraph ("Rebuild index is still absent…") to an as-built statement. **Reason:** the action now exists.
- **Section:** "The page's full design — page-level actions" table (row at ~:658). **Change:** state → delivered, `fast/002`; behaviour → "confirm → blocking POST → completion line". **Reason:** as built.
- **Section:** the `fast/002` response paragraph (~:683-691) and "Always available" (~:693-713). **Change:** convert "expected / requirement on that plan" wording to as-built: the response is `{ tables_rebuilt: [the four fixed names] }`, no content-derived count; the button is never disabled by drift state or designation; no designation → 409 `no_embedding_model` in the rebuild's own inline Alert. **Reason:** the requirement is now an as-built fact.
- **Section:** rebuild-after-restore paragraph (~:715-727). **Change:** drop "until `fast/002` exists, there is no button to press". **Reason:** stale.
- **Section:** derived-tables gap (~:629-638). **Change:** note the rebuild re-issues FTS triggers and rebuilds both FTS tables, so rebuild-after-Sync now has a button. **Reason:** as built.

## docs/architecture/search-and-retrieval.md

- **Section:** "Index rebuild — FEAT-005" (:1134-1170). **Change:** record as built: route `POST /api/admin/database/rebuild` (sync, blocking, admin-only); one transaction, all-or-nothing; step 2 is **always** drop + re-create both `vec0` tables at the designated dimension (not only on dimension change), so stale and orphan vectors vanish; embedding in chunks of `REBUILD_EMBED_BATCH_SIZE` with a fresh handle per chunk; `memo_fts` via FTS5 `'rebuild'`, `message_fts` via delete-all + record-row insert (never `'rebuild'`, which would index zone/buried rows); triggers re-issued. Replace "The rebuild is unbuilt (`fast/002…`)" with the as-built response shape. **Reason:** decisions taken at plan time, with reasons in `context.md`.
- **Change (operational note):** the transaction holds the SQLite write lock across embedding calls, so other writes block for the rebuild's duration. **Reason:** consequence of the all-or-nothing decision; record so it is not "fixed" into a partial rebuild unknowingly.

## docs/architecture/forms-and-lists.md

- **Section:** confirm table (~:345). **Change:** "Rebuild the vector index — **not yet realized**" → realized (`fast/002`); drop the deferral sentence. **Reason:** as built.

## docs/architecture/frontend-structure.md

- **Section:** per-entry responsibilities, `admin` row (~:200). **Change:** "the vector rebuild remains unbuilt (`fast/002`)" → built; add UC-016 to the Realizes column. **Reason:** as built.

## docs/architecture/backend-structure.md

- **Section:** admin route surfaces (database family). **Change:** add `POST /api/admin/database/rebuild` → 200 `{ tables_rebuilt: string[] }`; errors 409 `no_embedding_model`, the unreachable-LLM status, 401/403. **Reason:** new route.

## docs/architecture/quick-reference.md

- **Change:** add the route to any route index; drop `fast/002` from any "unbuilt" list. **Reason:** index consistency.
