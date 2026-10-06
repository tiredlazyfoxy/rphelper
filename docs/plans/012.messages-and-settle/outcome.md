# Feature 012 — Messages and settle · outcome

Intended changes to `docs/architecture/` once this feature ships, for the architect to
apply at finalization. Grouped by target file. Decisions referenced as D-n are in this
folder's `context.md`; "011 Dn" are in `docs/plans/011.rp-sessions/context.md`.

## `docs/architecture/data-model.md`

| Section | Intended change | Reason |
|---|---|---|
| `messages` — "Mitigation — two SQL views" and its `CREATE VIEW` sketch | Replace the SQL views with **named SQLAlchemy Core selectables** in `db/schema.py`: `settled_entries` (`settled_at IS NOT NULL`) and `current_zone` (`related_to IS NULL AND settled_at IS NULL`), executing no DDL, carrying no session filter and no ordering (callers narrow and order). Keep the paragraph's argument (the predicate in exactly one place) and record why not views: bootstrap `create_all` and the drift page's Create / Sync handle tables only, drift and `/api/health` walk `metadata.tables`, a Sync batch-recreate of `messages` would break a real view at the rename, and no path creates a view on an existing instance (D1, user decision). | The doc describes objects that were deliberately not built. |
| `messages` — same section | Add the third, **text-free** selectable `message_states` (`id`, `user_id`, `session_id`, `related_to`, `settled_at` only), used by the zone-edit route to tell a buried row from a missing one without a raw `select()` on `messages`; it cannot carry content, so R11's purpose holds (D7, planner decision accepted by the user). | The doc names two; the design needed a state-only probe. |
| `messages` — "As built by plan 012" | Record the as-built table: the twelve columns as listed, `role` and `kind` as plain text with **no DB CHECK** (constrained at the pydantic boundary), the named CHECK `related_to IS NULL OR settled_at IS NULL`, indexes `(session_id, settled_at)` and `(related_to)`, no `ON DELETE`; `tool_name` / `tool_payload` declared and unwritten until `021`. Existing instances get the table through **Create**. | As-built record. |
| `messages` — "Raw `messages` is touched by exactly two operations" | Re-word as D16 does: **reads** outside settle / re-open go through the selectables; the **burial and settle columns** (`related_to`, `kind`, `settled_at` on an existing row) are written only by settle / re-open; the zone append and the partner filing each **insert**, and the zone edit **updates `text`** — as the stream route table already says. | The two statements contradicted each other. |
| `messages` — "`position` is dropped" | Add the accepted consequence of D14 (user decision): a partner block may be filed while the zone holds a draft; if that draft is settled afterwards it sorts **above** the partner block (it was begun first) and is not re-openable (the partner block is the last settled row). Accepted as chronologically true and harmless; no backend refusal and no UI guard. | A consequence of `ORDER BY id` the doc does not mention. |
| `messages` — timestamps | Record that every write in one operation uses one instant, and that burial / re-open bump the moved rows' `updated_at` (D3). | As-built. |
| `sessions` — `last_used_at` | Record as built: append, partner filing, zone edit, settle and re-open bump **`last_used_at` and `updated_at`** to the operation's instant in the same transaction; reads and refused operations never write (D3, closing 011 D3's forward note). Compose (`021`) joins the list. | 011's outcome left this as a forward note. |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| "The stream routes" — route table | Mark the seven JSON routes as built by plan 012 (compose stays `021`'s; the character-addressed create is 011 / `018`'s). Record the response shapes: entries `{ entries: [...] }`, zone `{ messages: [...] }`, the eight-key `Message` (no `user_id`, `related_to`, tool columns), settle `{ entry_id, kind, buried_ids }`, re-open `{ reopened_id, restored_ids }`; POSTs that create answer 201 (D12). | As-built wire contract; the doc said only "returns the ids the operation moved". |
| "The stream routes" — the `PATCH` bullet | Add: **as built in 012, `PATCH` edits current-zone rows only**; a settled row answers `message_not_editable` until `014` widens it to settled rows (UC-078, US-110); a missing or foreign id answers `message_not_found` (D2). | The bullet describes the finished route. |
| "The stream routes" — the partner bullet | Record: `kind` is required and must be exactly `"partner"` (422 otherwise); there is **no zone precondition** on filing a partner block (D14, user decision — the ordering consequence is recorded in `data-model.md`). | As built. |
| "The stream routes" — text validation | Record: `text` is required and non-blank, stored verbatim, with **no maximum length** (R10, US-035.AC-2) (D9). | As built. |
| "Settle and re-open" — step 5 | Mark "Refresh `session_vec`" as **not built in 012**: no vector / FTS table exists before `024.embedding-lifecycle`, which adds it to settle's transaction (D4). | The step list reads as complete. |
| "Settle and re-open" — re-open | Record the as-built order (session, zone non-empty → `zone_not_empty`, last settled by id, no group or no settled row → `nothing_to_reopen`), that burial is by the id list read from `current_zone` in the same transaction, that settle and re-open return ids only (services never import each other, D11), and that the pre-strip text is not restored on re-open (D10, R12). | As built. |
| "The `(( ))` seam" | Record D8's exact rules (user decision on the classifier): **decision iff the text, after trimming outer whitespace, starts with `((` and ends with `))`**, filed verbatim (so `((a)) prose ((b))` is a decision, accepted); otherwise a turn, in which every fragment (the shortest `((`…`))` span) is removed with the spaces / tabs before it, runs of three or more line breaks collapse to one blank line, and the ends are trimmed; a fragment-free turn is filed **byte-for-byte**. Record that a turn can **never strip to empty**, malformed input included: text that would strip to nothing starts with `((` and ends with `))` once trimmed, so it is a decision; an unbalanced `((` or a stray parenthesis survives stripping. | The doc names the functions, not their rules; the rules are now the contract the client preview (`013`) must match. |
| "The error model" — named-errors table | Add `message_not_found` (a message route addresses an id that does not exist or belongs to another user; `detail` empty; FEAT-010, UC-083). Amend `message_not_editable`'s "Raised when" to "an edit targets a buried row (US-116) — and, until `014`, a settled row". Amend `nothing_to_reopen`'s "Raised when" to cover every case D10 refuses (no settled row; last settled row has no buried group — a partner block, a lone directly-settled turn or decision). | New code; widened conditions. |
| "The per-code status record" | Add five rows, introduced by plan 012: `zone_empty` **409**, `zone_not_empty` **409**, `nothing_to_reopen` **409**, `message_not_editable` **409** — well formed, the caller owns the target, the stream's state conflicts (the shape of `username_taken` / `setup_archived`); not 404, the target exists; not 422, no field is malformed — and `message_not_found` **404** — the path's id addresses no row of the caller, indistinguishable for nobody's and another user's (R5), sibling of `session_not_found`. Each carries a fixed default `message` (the `already_configured` pattern) (D13). | Per-code record. |
| "Routers versus services" | Record `services/messages.py` and `services/settle.py` as two services over one table that never import each other, each with its own owner-scoped session check and bump (D11); `services/parens.py` is imported only by `settle.py`. | Third instance of the D11 rule, now within one table. |

## `docs/architecture/domain-rules.md`

| Section | Intended change | Reason |
|---|---|---|
| R11 — the re-open bullets | Record as a **decision (user decision at plan 012)**: re-open applies only when the **last settled row of the session has a buried group**; a **lone directly-settled turn, a lone decision and a pasted partner block are all not re-openable** (`nothing_to_reopen`), and so is any earlier group once a later row is settled. Previously only the partner case was stated; the lone-turn and lone-decision cases were implied (D10). | Make the implied rule explicit so it is not "fixed" into a demotion of a settled turn back to draft. |
| R11 — "The predicate lives in one place" | Re-word for D1 / D7 / D16: the predicates live in **named Core selectables** (not SQL views); readers go through them; the burial / settle columns are written only by settle / re-open; inserts and text edits are the append, partner and edit routes. | Matches the as-built design. |
| R12 — "A wholly-parenthesised message is out-of-character" | Define "wholly parenthesised" as D8 does (**trimmed text starts with `((` and ends with `))`**, user decision) and record the accepted consequence: a message with prose between two fragments is filed as a decision, verbatim. Add "a fragment-free turn is filed byte-for-byte" and "a turn cannot strip to empty" (or point to `backend-structure.md`'s seam section once it carries them). | The rule's precise boundary is now decided. |

## `docs/architecture/admin-surfaces.md`

| Section | Intended change | Reason |
|---|---|---|
| "Two recorded gaps — views and virtual tables" | Remove the **views** half: there are no SQL views (D1); the stream selectables are Core expressions, not schema objects, so the drift report has nothing to describe. Only the `vec0` / FTS5 gap remains, owned by stage 004. | The gap closed by not creating the objects. |
| "The views gap has a second edge" | Remove: no view references `messages`, so a Sync rebuild of `messages` (or any table) cannot fail at the rename step on a view. | Moot under D1. |

## `docs/architecture/workspace-shell.md`

| Section | Intended change | Reason |
|---|---|---|
| The kind switch's carried `_TBD:` on decisions (~line 302) | Remove it: **US-120.AC-3** answers it — settled decisions have no effect on the default; it alternates from the last partner-or-turn entry. Every entry from `GET …/entries` carries its `kind`, so `013` computes the default client-side (D5). | Stale `_TBD:`; the product answered it. |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| The US-120 `_TBD:` (~line 810) | Remove, citing US-120.AC-3 (D5). | Same as above. |
| Wherever the two views are named | Replace "SQL views" with "named Core selectables in `db/schema.py`", and add `message_states` (D1, D7). | Dense index. |
| Error codes | Add `message_not_found` (404); confirm `zone_empty`, `zone_not_empty`, `nothing_to_reopen`, `message_not_editable` at 409. | Dense index. |
| Routes / paths | Add the seven stream routes as built. | Dense index. |

## Forward notes (not architecture changes; for the owning plans)

- **`013` (stream UI):** reads `GET …/entries` / `GET …/zone`; computes the kind switch
  default from the last `partner` / `turn` entry (D5); settle / re-open responses carry ids
  only, so re-read both lists after either (D11). The client `(( ))` preview must match
  D8's rules exactly. Reading a buried group (US-040, UC-036) has **no route** in 012 —
  `013` designs it (a read through a selectable named for buried rows, or a narrowing of
  the record read), keeping raw `select()`s on `messages` inside settle / re-open.
- **`014` (edit settled entries):** widen `edit_message_text` to settled rows (UC-078,
  US-110, US-109); a buried row stays `message_not_editable`. Translation invalidation
  (US-111) joins it once `023` exists.
- **`020` (context assembly):** reads `settled_entries` and `current_zone` only; US-122.AC-1
  and US-043 are delivered there.
- **`021` (compose):** writes assistant (and tool) rows into the zone and bumps the session
  as D3 does; adds `tool_name` / `tool_payload` to the wire if the UI needs them.
- **`024` (embedding lifecycle):** adds settle's step 5 (`session_vec` refresh) inside the
  settle transaction, and the edit's degraded embedding path (D4).
- **`027` (`session_search`):** US-122.AC-2 is delivered there, over `settled_entries`.
- **FEAT-008** (011's outcome): US-027.AC-3's entries half and US-024.AC-2's
  adding-entries half are proved by `004` DoD-16.

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B1 (the backend spine — `session-stream.md`, `transfer.md`, `backend-structure.md`, `data-model.md`, `domain-rules.md`) and B2 (the LLM/search/operations layer — `llm-and-streaming.md`, `search-and-retrieval.md`, `deployment.md`, `admin-surfaces.md`, `overview.md`).
Rejected items: Every "until `014`" qualifier was dropped rather than written — 014 widened `PATCH` and 021 added the tool-row refusal, so the final rule is recorded once.
Notes: The `admin-surfaces.md` views gap was removed as asked, but the section was rewritten rather than trimmed, because 024 opens a different gap there (virtual tables outside `metadata`, and a Sync rebuild dropping FTS triggers). The four named Core selectables are recorded with the explicit statement that no SQL view exists anywhere.
