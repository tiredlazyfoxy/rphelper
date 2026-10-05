# Feature 027 — Session search tool · intended documentation changes

Planner section: the doc changes the architect applies once 027 ships. Grouped by target
file. "Dn" refers to decisions in this folder's `context.md`.

## `docs/architecture/search-and-retrieval.md`

| Section | Intended change | Reason |
|---|---|---|
| `session_search` — FEAT-015 — Scope predicate | Add a fourth term, **`sessions.archived_at IS NULL`**: archived past sessions are never returned. The predicate is built in `services/search/session_search.py` as `character_id = :character_id AND id != :current_session_id AND archived_at IS NULL`, and the port ANDs `user_id`. The archive term is on the session only, so a session whose setup is archived stays searchable. Restoring a session makes it findable again with no re-embed, because 024 keeps archived sessions' vectors current. This term is a user-confirmed decision, not an inference | D1 |
| `session_search` — FEAT-015 — the current-session paragraph | Change "a design inference, not a stated requirement" to **implemented**: `id != current_session_id` is in the predicate and is tested with a current session whose vector is identical to the query's. It remains an inference about value (the assistant already reads the current session), not a product requirement | D1 |
| `session_search` — FEAT-015 — the archived re-embed fan-out `_TBD:` (~L335) | Update the premise: "session_search excludes nothing on archive state today" is no longer true. The tool now excludes archived sessions. The `_TBD:` itself stays open because it is 024's and product's question. It does gain one fact: if archived sessions were skipped by the fan-out, a restored session would come back into `session_search` with a stale vector, so "re-embed on restore" would become mandatory | D1 |
| `session_search` — FEAT-015 | Record the **result count: at most 5, no paging**. The count is a named constant passed as `limit`, and the declaration stays `query` only. Each hit carries a long excerpt, which is why the cap is lower than `memo_search`'s 8. The count is conventional and user-confirmed, not measured | D2 |
| `session_search` — FEAT-015 | Record **what the model receives**, which closes 027's brief question and 025's "the tool decides the text that represents a session". Results come in rank order, one block per hit. Each block is a header `### Session <YYYY-MM-DD> · setup: <name>` or `… · no setup`, where the date is `created_at` as a UTC date and the setup name is shown even when the setup is archived. The header is followed by the **last 1500 characters** of the session's `settled_entries` text, which is in ascending id and joined by `\n\n` (decisions included). A cut excerpt starts with `…`. A session with no settled entries shows `(no settled entries)`. There is no persona, no setup description and no id. Zero hits is a success with `No matching sessions.` The summary is `<N> sessions`. State the asymmetry as deliberate: the **match** text (024's composed text) includes persona and setup, but the **result** text does not | D3 |
| `session_search` — FEAT-015 | Record that the port returns ids and scores only for sessions. The header and excerpt come from 027's own **owner-scoped read** by `user_id` and hit ids, in hit order, with the bound applied in the service | D4 |
| `session_search` — FEAT-015 — Failure | Add that the tool **raises** and never builds its own failure outcome. `no_embedding_model`, `llm_unreachable` and `secret_ref_missing` propagate, and a missing or non-string `query` raises `tool_failed`. 021's seam produces the `tool_fail` frame and the "tool failed" model message. This is proven through the real seam with no designated embedding model | D5 |
| `session_search` — FEAT-015 | Record the **off-loop** form, which is 026's pattern reused. Search and excerpt read run in one `asyncio.to_thread` call on the seam's connection | D6 |
| Embedding lifecycle — the cost `_TBD:` (~L516-521) | **Stays open.** It was handed to "FEAT-015's plan", and 027 does not close it: no measurement of re-embed cost against session length exists, and bounding the **composed** (embedded) text would be 024's code, not the tool's. Add a note that 027 bounds only the **result excerpt** (1500 characters), which has no effect on embedding cost. The question goes back to 024's owner, or to a measured follow-up | not decided here |

## `docs/architecture/llm-and-streaming.md`

| Section | Intended change | Reason |
|---|---|---|
| The tool-calling loop | The production registry holds **`memo_search` and `session_search`**, so with each session's switch on, both are offered in production. `web_search` stays unregistered until 028. `session_search`'s scope uses `user_id`, `character_id` and `session_id` from `ToolScope`, and never uses `setup_id` | D6, D7 |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| Layout — `services/search/` | Add `session_search.py`. It holds the cap and excerpt-length constants, the session predicate factory, the sync `search_sessions`, and the sync owner-scoped excerpt read with its record type | D4, D6 |
| Layout — `services/tools/` | Add `session_search.py`, the `session_search` `Tool` adapter and its formatter. `seam.py`'s production registry now registers it beside `memo_search` | D6 |
| Routers versus services | Add three service-to-service imports, none of which opens a transaction of its own: `tools/session_search.py` imports `search/session_search.py`, `search/session_search.py` imports the port (and reads `settled_entries` from `db/schema.py`), and `tools/seam.py` imports `tools/session_search.py` for registration. The adapter imports seam types for type-checking only, as `memo_search` does | D6 |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Paths | Add `services/search/session_search.py` and `services/tools/session_search.py` | D6 |
| Invariants | `session_search` runs the vector arm only. Its scope is user AND character AND `id != current` AND `archived_at IS NULL`. It returns at most 5 hits, and each excerpt is at most 1500 characters plus the marker. The sync port and the excerpt read run via one `asyncio.to_thread` | D1–D3, D6 |

## Plan supersessions (for the record, not architecture)

- 027 `003` amends three assertions that 026 had already amended, and that 021 had
  originally written to pin the production registry or the seam's import list. They are
  021 `004` DoD-2 and DoD-10 in `test_tool_seam.py`, and 021 `006` DoD-10 in
  `test_compose_route.py`. Each now reflects the two-tool registry.
- 027 `003` amends 026 `002` DoD-11 in `test_memo_search_tool.py`. That test claimed the
  registry held "exactly one entry". The claim is dropped, the `memo_search` value checks
  are kept, and the two-entry claim now lives in 027 `003` DoD-11.
- The amendments are listed in `003.context.md`.

## Notes for other owners

- **029 (my-search) / data-model.md:** `session_fts(title, partner_label)`
  (`data-model.md` ~:761, `search-and-retrieval.md` ~:231) indexes columns that the built
  `sessions` table does not have: there is no title and no partner column. This does not
  affect 027, which never touches `session_fts`. It also weakens the architecture's stated
  reason for leaving BM25 off (the reason is "the lexical index's columns are `title` and
  `partner_label`"). The product reason, FEAT-015's rejection of structured matching, still
  stands. 029's planner should reconcile the index definition.

## Observations

- Step 003: the adapter's source imports no `fastapi`, but it imports `ToolFailedError` from
  `app/errors.py`, which imports `fastapi` at module level — so importing
  `app.services.tools.session_search` in a fresh interpreter does put `fastapi` in `sys.modules`.
  026's `memo_search.py` has had the identical property since it shipped. A "no web framework"
  check over `app/services/` therefore has to read the module's own imports, never `sys.modules`.
  Possible impact: a sentence in `backend/CLAUDE.md` (or `docs/architecture/backend-structure.md`'s
  layer-separation note) saying that `app/errors.py` is the framework-coupled leaf every service
  may import, and that framework-freedom is a source-level property.
