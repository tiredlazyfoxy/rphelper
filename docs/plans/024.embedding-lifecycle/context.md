# Feature 024 — Embedding lifecycle · feature-wide context

## What this feature is

024 keeps the searchable copy of the roleplayer's material in step with the material
itself. It builds the two full-text tables (`memo_fts`, `message_fts`) and the two vector
tables (`memo_vec`, `session_vec`) in the same SQLite file. Every write that changes
searchable text then re-embeds what it changed, inside the transaction that made the change.
That includes the fan-out: a persona or setup-text edit re-embeds every session that text
feeds into.

Two failure postures are deliberate and must stay apart:

- **Authoring writes fail hard.** These are memo create, memo body edit, persona edit and
  setup-text edit. If the embedding cannot be made, nothing is stored.
- **Record-keeping writes degrade.** These are settle, re-open, settled-entry text edit and
  partner filing. The row is stored, and the response says search coverage is incomplete.

Flag toggles and reorders do no vector work at all.

The agreed boundary is `brief.md` in this folder. **Out:** querying (`025`), every tool
(`026`–`028`), my-search (`029`) and the administrator's rebuild (`fast/002`). 024 issues
**no KNN query and no FTS `MATCH` in application code**. Tests may query the tables to
observe them.

## Product ids

Delivers **FEAT-009** through **US-112**. The other ids are cited where their DoD is
exercised. "Search reflects the new text" can only be tested here as "the vector or FTS
row is refreshed", because querying belongs to `025`.

| Criterion | Where it lands |
|---|---|
| US-112.AC-1 (no embedding model → settled edit still saves) | `003` (degraded refresh), `005` (edit / settle / re-open / partner filing) |
| US-112.AC-2 (… and the roleplayer is told coverage is incomplete) | `005` (`search_coverage_incomplete` on the wire), `007` (banner) |
| US-110.AC-2, US-109.AC-2 (search reflects an edited settled entry) | `001` (`message_fts` trigger on a settled edit), `005` (`session_vec` refreshed) |
| US-122.AC-2 (a settled decision is findable by `session_search`) | `003` (decisions are in the composed text) |
| US-115 (zone messages are not findable) | `001` (zone rows never in `message_fts`), `003` (zone rows not composed), `005` (zone writes do no vector work) |
| US-138.AC-1 (session match = entries + persona + setup) | `003` (composition, D6), `006` (persona / setup edits re-embed) |
| US-021.AC-1, UC-018 (persona edit saves) | `006` |
| UC-042 / UC-043 / US-104 (memo create / body edit) | `004` |
| UC-044 / UC-075 (flag toggles: no vector work) | `004` |
| UC-076 (reorder: no vector work) | `004` |
| US-119 (a memo is its body alone) | `004` (only `body` is embedded) |
| UC-078 (edit where it sits; the exception flow) | `005`, `007` |

## The brief's open questions — answered

1. **How a failed degraded embed is recorded so the rebuild can find it.** It is **not
   recorded** (user decision U5). A degraded write leaves any existing `session_vec` row as
   it is, which makes it stale, and writes nothing else. There is no staleness column. The
   remedy is the whole-index rebuild (`fast/002`), as `search-and-retrieval.md` "Failure
   mode" already states.
2. **What the sparse-rowid verification resolves to.** Snowflake ids **stay** the `vec0`
   and FTS5 keys, and there is **no surrogate key** (U6). This was resolved empirically, and
   the results are in D3.

## Build prerequisites

- **001..015 are built.** Every backend touch site below exists as harvested.
- **016 must be built and committed first.** `services/memos.py`, `routers/memos.py`,
  `models/memos.py`, `errors.py` and the memo test files carry uncommitted 016 work
  (`reorder_memos`, `MemoOrderMismatchError`). 024 builds on top of it. It never changes
  `reorder_memos` and never touches `errors.py`.
- **017..023 are planned, not built.** The roadmap builds in numeric order. Textual-merge
  awareness, not dependencies:
  - 023 `001` adds a `translations` delete inside `edit_message_text`'s transaction. 024
    `005` adds a refresh in the same block, so both edits are additive.
  - 023's frontend tests build `Message` payloads "with all its keys". D10 keeps the new
    field optional on the TypeScript type so those builders still typecheck.
  - 019 / 021 / 022 edit `streamState.ts` / `SessionStream.tsx`. 024 `007` adds one field,
    four assignments and one banner.
  - 017 adds character configuration writes through its own routes. None of those columns
    is embedded, so 024 adds nothing there.

## Architecture this binds to

- `search-and-retrieval.md`: "The sparse-rowid verification item", "What text represents a
  session", "The invalidation fan-out", "Embedding lifecycle" (the trigger table, the
  failure asymmetry, authoring vs record-keeping), "Index rebuild".
- `data-model.md`: Identifiers (the sparse-rowid `_TBD:`), `models`, "Vector tables",
  "FTS5 tables", "As built by FEAT-005" (the drift walk covers `metadata.tables` only).
- `backend-structure.md`: "The two transaction rules, and the asymmetry between them"
  (`no_embedding_model` has two callers), the error model and the per-code status record
  (`no_embedding_model` 409, `llm_unreachable` 502).
- `llm-and-streaming.md`: `embed()` raises only `llm_unreachable`; the no-substitution rule.
  Its "validators ship without call sites" note: **024 is the first caller of
  `validate_embedding_model`**, which is the arrival that note anticipates.
- `workspace-shell.md`: the coverage banner above the stream (US-112).
- `domain-rules.md` R5 (owner scope in SQL) and R11 (readers go through the views).

Cited, never copied.

## Files this feature touches

```
backend/
  app/db/search_tables.py        # NEW — FTS + vec0 ensure, triggers, back-fill, dim read-back   (001)
  app/services/bootstrap.py      # create_first_administrator ensures the FTS half               (001)
  app/services/embedding.py      # NEW — designated-model handle, sync bridge, vector rows       (002)
  app/dependencies.py            # + shared get_llm_client_factory                               (002)
  app/routers/admin_llm.py       # re-imports get_llm_client_factory (same object)               (002)
  app/services/session_index.py  # NEW — session text, refresh (strict / degraded), fan-out ids  (003)
  app/services/memos.py          # create / body edit strict; delete drops vec row               (004)
  app/routers/memos.py           # factory + settings dependencies                               (004)
  app/services/settle.py         # settle / re-open degraded refresh + flag                      (005)
  app/services/messages.py       # partner filing / settled edit degraded refresh + flag         (005)
  app/models/stream.py           # search_coverage_incomplete on three responses                 (005)
  app/routers/stream.py          # factory + settings dependencies on four routes                (005)
  app/services/characters.py     # persona-change fan-out (strict)                               (006)
  app/services/setups.py         # description-change fan-out (strict)                           (006)
  app/routers/characters.py      # factory + settings dependencies on PATCH                      (006)
  app/routers/setups.py          # factory + settings dependencies on PATCH                      (006)
frontend/
  src/app/streamApi.ts           # optional flag on three types                                  (007)
  src/app/streamState.ts         # coverage flag + four assignments                              (007)
  src/app/SessionStream.tsx      # the banner                                                    (007)
  src/shared/embeddingFailure.ts # NEW — code → sentence helper                                  (008)
  src/app/memoLevelState.ts      # saveNote / saveNewNote use it                                 (008)
  src/app/characterScreenState.ts# submitSave uses it                                            (008)
  src/app/setupDraft.ts          # submitSetup uses it                                           (008)
```

**Not touched. A step that touches one is out of scope:** `db/schema.py` (virtual tables
stay out of `metadata`, D2), `db/engine.py` (sqlite-vec is already loaded on every
connection), `db/drift.py`, `db/sync.py`, `errors.py`, `services/llm_registry.py`,
`services/llm/*`, `app/secrets.py`, `config.py`, `main.py` (no startup DDL, since `lifespan`
is empty by contract), `tests/conftest.py`. `reorder_memos` and its route are not touched.
**No new Python or npm dependency.**

## Wire contract

One new response field, boolean, always present on the backend wire:

| Response | Route(s) | `search_coverage_incomplete` |
|---|---|---|
| `SettleResponse` | settle | `true` iff the degraded refresh could not embed |
| `ReopenResponse` | re-open | same |
| `MessageResponse` | `POST /api/sessions/{id}/entries` (partner filing), `PATCH /api/messages/{id}` (edit) | same for a settled row; **always `false`** for a zone row and for a zone append |

Any other route that answers `MessageResponse` carries `false`.

Authoring routes gain two failure answers, each with the standard
`{"error": {code, message, detail}}` body and **nothing stored**:

| Code | Status | When |
|---|---|---|
| `no_embedding_model` | 409 | no designated + enabled embedding model, or a dimension mismatch (D8) |
| `llm_unreachable` | 502 | the embed call failed |

The authoring routes are `POST /api/memos`, `PATCH /api/memos/{id}` with a changed `body`,
`PATCH /api/characters/{id}` with a changed `sheet` while N > 0, and
`PATCH /api/setups/{id}` with a changed `description` while N > 0.

## Cross-cutting constraints every step holds

- **One transaction (U1).** These all happen inside the service's existing
  `with connection.begin():` block, in this order:
  1. the relational write;
  2. composition of the text to embed, **read inside the same transaction after the write**;
  3. the embed call;
  4. the vector write.

  Routes stay sync `def`. Nothing commits the row and embeds afterwards.
- **No substitution (R4).** Only the designated, enabled model embeds. An unusable
  designation is `no_embedding_model`. No other model is ever tried.
- **Owner scope in SQL (R5).** Every read that composes text or selects fan-out sessions
  carries the caller's `user_id` in its own predicate.
- **Readers go through the views (R11).** Session text reads the `settled_entries`
  selectable, never raw `messages`.
- **Services import no `fastapi`.** The client factory and the timeout reach services as
  parameters. Routers obtain them via `Depends`.
- **Backend** is fully typed. `mypy app` and `ruff check .` stay green after every step.
- **Frontend** is TypeScript only, and `npm run typecheck` stays green. Pure data contracts
  apply (memory note): MobX classes hold observable fields only, and effects are free
  functions taking the state first, using `runInAction` after `await`.

## Decisions — settled, with their reasoning

U1–U7 are user-confirmed (binding). The rest are planner decisions.

### D1 — Sync bridge inside the transaction (U1)

`LlmClient.embed` is async. Services call it through one sync wrapper in
`services/embedding.py` that runs the coroutine with `asyncio.run`. That works because
routes are sync `def` on threadpool threads with no running loop.

- **One client per write operation and one `embed` call per write operation.** A fan-out
  over N sessions sends **one** request with N texts, not N requests. This keeps one event
  loop per client and pays one round trip.
- **The cost is stated, not hidden.** The SQLite write lock is held across the provider
  call, so a concurrent writer waits behind a slow embed. That is the price of never-stale
  search (`search-and-retrieval.md`), and `outcome.md` records it.

### D2 — Ensure-on-write DDL; virtual tables live outside `metadata` (U2)

`app/db/search_tables.py` owns all virtual-table DDL. Its ensure functions are idempotent
and run **inside the calling write's transaction**. SQLite DDL is transactional, so a
rolled-back write also rolls back a table it created.

- **The FTS half** creates `memo_fts` / `message_fts` and their triggers when absent. On
  creation it back-fills **once** from existing rows. These run:
  - on every memo write that changes `body` or deletes a memo;
  - on every record-keeping refresh;
  - in bootstrap (`create_first_administrator`, after `create_all`).
- **The vec half** creates `memo_vec` / `session_vec` with the designated model's
  `embedding_dim` when absent. It runs only after a designated model has been resolved.

The virtual tables are **not** added to `db/schema.py`. `create_all`, the drift walk and
the Sync executor would each mishandle a virtual table. The drift walk's gap over virtual
tables is owned by `admin-surfaces.md`, and stays open.

**An instance bootstrapped before 024** gets its FTS tables (back-filled) on its first
qualifying write. Its vector tables start empty, and pre-024 memos and sessions have no
vector until the rebuild (`fast/002`). That is expected, not drift.

### D3 — Snowflake ids are the `vec0` / FTS5 keys; one query form is forbidden (U6)

The empirical probe used sqlite-vec 0.1.9 and SQLite 3.47.1, with 5000 rows of 768-d
vectors:

- **Equal on dense and snowflake ids:** insert, size, and unfiltered KNN. FTS5 external
  content worked at ~2^60 ids, including conditional triggers and `integrity-check`.
- **The defect:** vec0 KNN with a pushed-down id constraint (`WHERE embedding MATCH ? AND
  k = ? AND memo_id IN (...)`) silently drops true candidates when ids are above ~2^50. It
  happened in 18–36% of queries with realistic ids, and only as false negatives.

The forms `025` must use instead are recorded in `outcome.md`:

- a scan over the candidate set ordered by `vec_distance_l2`;
- or an over-fetching KNN followed by a JOIN, or by a `+memo_id IN` (the unary plus blocks
  pushdown).

024 issues no KNN, so it is unaffected. Its tests prove point lookups by snowflake id
round-trip.

### D4 — Vector row writes

- **Upsert** is delete-then-insert by id, or `UPDATE … SET embedding`. `INSERT OR REPLACE`
  fails on vec0 with a UNIQUE error in 0.1.9.
- **Delete** is by id. Deleting an absent id is not an error.
- Vectors are serialised with `sqlite_vec.serialize_float32`.

### D5 — Which writes do vector work (the trigger table, as built)

| Write | Vector work | Posture |
|---|---|---|
| memo create | embed `body` → `memo_vec` | strict |
| memo `body` changed (differs from stored) | re-embed → `memo_vec` | strict |
| memo `body` sent but equal to stored; `is_enabled` / `is_forced` only; reorder | **none, and no embed call** | — |
| memo delete | delete its `memo_vec` row (no model needed) | — |
| settle, re-open, settled-row text edit, partner filing | refresh that session's `session_vec` | degraded |
| zone append, zone-row edit | **none** | — |
| `characters.sheet` changed (differs from stored) | refresh every session of the character | strict, only when N > 0 |
| `setups.description` changed (differs from stored) | refresh every session using the setup | strict, only when N > 0 |
| character / setup create, name-only edit, sheet / description equal to stored, archive / restore | **none** | — |

**Archived sessions are included** in both fan-outs, with no archive predicate (U4). A
restored session must not come back silently stale.

"Changed" means the submitted value differs from the stored one. A save that resends the
unchanged persona alongside a new name is therefore a name-only edit and does no vector
work.

### D6 — What text represents a session (exact form; tests bind to it)

The **session text** has these parts, in this order:

1. the character's `sheet`;
2. the setup's `description`, only when `sessions.setup_id` is not null;
3. the `text` of each row of `settled_entries` for that session, in ascending `id`. This
   covers every kind, decisions included.

A part that is empty or whitespace-only is dropped. The remaining parts are used **as
stored** and joined with exactly `"\n\n"`.

Persona and setup come **first**. Embedding models truncate long input, and US-138.AC-2's
"similar person" half must survive a long session. `outcome.md` records this ordering.

**If the session text is empty, there is nothing to embed.** The session's `session_vec`
row is deleted if the table exists, no model is resolved and no embed call is made. The
outcome counts as complete, not degraded.

### D7 — A memo embeds its body alone; a blank body has no vector

The embedded text is `body` as stored, because US-119 means there is no title. A blank
(whitespace-only) body has no vector. Its `memo_vec` row is removed if present, no model is
resolved and no embed call is made. A blank memo has nothing to retrieve, and an empty
string is an invalid embed input for common providers.

### D8 — The two failure codes, and dimension mismatch

- **The strict path** lets `NoEmbeddingModelError` (409) and `LlmUnreachableError` (502)
  propagate. The transaction rolls back and nothing is stored, including DDL.
- **The degraded path** catches **both** (U3), writes no vector, and reports
  `search_coverage_incomplete = true`. Any other exception propagates as before.
- **Dimension mismatch is "unavailable".** It is raised as `NoEmbeddingModelError` with
  `detail` exactly `{"reason": "dimension_mismatch"}` in two places:
  - an existing vec0 table's declared dimension ≠ the designation's `embedding_dim`
    (`001`);
  - a returned vector whose length ≠ `embedding_dim` (`002`).

  The raise site passes its own fixed message, and `errors.py` is not changed. The tables
  are **not** re-declared here, because that is the rebuild's job (`fast/002`).

### D9 — Shared client-factory dependency

`get_llm_client_factory` moves to `app/dependencies.py` and still returns the real
`LlmClient` class. `routers/admin_llm.py` imports it from there, so the name it exposes is
**the same function object**. Existing `dependency_overrides` keyed on the admin router's
name therefore keep working.

The routes 024 touches depend on it and on `get_settings`. They pass
`settings.llm_request_timeout_seconds` to the service.

Services take the factory and the timeout as **keyword-only parameters with defaults**:

- the factory defaults to the real `LlmClient`, the existing pattern;
- the timeout defaults to `Settings`' declared default for that field, taken from the
  field, never re-typed.

Existing positional callers therefore still compile.

### D10 — The frontend flag is optional in the types

`search_coverage_incomplete?: boolean` is added to `SettleResult`, `ReopenResult` and
`Message` in `src/app/streamApi.ts`. **Absent is read as `false`.** This keeps every
existing full-`Message` test builder, 023's included, typechecking.

### D11 — Scope of the coverage notice

`StreamState` holds the flag for the current mount. It is set by the latest record-keeping
response:

- settle;
- re-open;
- an edit or partner filing whose returned row has a non-null `settled_at`.

Zone appends and zone edits leave it unchanged. It starts `false` on mount, because no
staleness is persisted (U5).

The banner is therefore "the latest record-keeping write in this view could not be
indexed", not a standing instance-state indicator. `outcome.md` records this for
`workspace-shell.md`.

### D12 — Eight steps

| Step | Subject | Est. source LoC | Depends on |
|------|---------|-----------------|------------|
| 001 | `db/search_tables.py` (FTS + vec0 ensure, triggers, back-fill, dim read-back) + bootstrap hook | ~140 | none |
| 002 | `services/embedding.py` (model handle, sync bridge, length check, vector rows) + shared factory dependency | ~120 | 001 |
| 003 | `services/session_index.py` (session text, strict / degraded refresh, fan-out ids) | ~130 | 001, 002 |
| 004 | memo write paths + memo router wiring | ~90 | 001, 002; 016 built |
| 005 | record-keeping paths + `search_coverage_incomplete` on the wire | ~85 | 003 |
| 006 | persona / setup-description fan-out + routers | ~75 | 003 |
| 007 | frontend: stream types, `StreamState` flag, banner | ~55 | 005 (wire; tests stub `fetch`) |
| 008 | frontend: authoring-failure sentences (memo, character, setup) | ~55 | 004, 006 (wire; tests stub `fetch`) |

## Test conventions

**Backend** (from `backend/`):

- pytest, flat `tests/`, test names `test_<behavior>__S024_<SSS>_DoD<n>`.
- The DB is a temp file via the existing `db_settings` / `db_engine` fixtures. Each test
  creates the schema itself with `schema.metadata.create_all`. Rows are raw-inserted with
  file-local helpers, using snowflake-sized ids (above 2^60) and two users for isolation.
- A designated model is `llm_servers` + `models` rows with `is_enabled`,
  `is_embedding_designated` and `embedding_dim` set. A small dimension such as 8 keeps
  tests fast.
- **No monkeypatching** (conftest policy). Service tests pass `client_factory=`. Router
  tests use `app.dependency_overrides` for the shared factory dependency and for
  `get_settings`.

**`backend/tests/llm_fakes.py`** (new, owned by step `002`'s test-coder) is the shared
provider fake. Its contract:

- the fake client's `embed` returns **one deterministic vector per input text** of a
  configured dimension, from a pure function of the text that tests can call to compute
  expected vectors;
- it can be scripted to raise `LlmUnreachableError` or to return vectors of the wrong
  length;
- it records every `embed` call (model name, texts in order);
- the fake factory records every construction (base URL, API key, timeout) and counts
  calls.

The file-local fakes in `tests/test_llm_registry_models.py` stay where they are.

**Frontend** (from `frontend/`): Vitest/jsdom. `tests/` mirrors `src/`, and each `it`
title ends `— DoD-N`. `fetch` is stubbed with `vi.stubGlobal`, keyed on pathname and
method. Ids are strings. Rendered components sit inside `<AppProviders>`.

**Expected values come from this plan:**

- D6's composition and D7's body rule;
- D8's `detail`;
- the wire contract above;
- the sentences pinned in `007.context.md` / `008.context.md`.

They never come from calling the code under test.

### Regression fallout — a known, intended behaviour change

Memo create and memo body edit now **require a designated embedding model**. Any existing
test that creates a memo through the service or the route without one will fail by design.
Settle / re-open / message responses also gain a key.

Each step lists the existing test files **known** to be affected. Its test-coder updates
those tests to designate a model and inject the fake, or to accept the new key. **If the
red-gate run shows a failure in an existing test file not listed in that step, it is a
`SPEC` hand-back.** The orchestrator then extends that step's Test files. Nobody edits an
unlisted file.

## Vocabulary

| Term | Means here |
|---|---|
| **strict / fail-hard** | an embed failure propagates and the whole transaction rolls back (authoring writes) |
| **degraded** | an embed failure is caught, the relational write commits, and the response flags incomplete coverage (record-keeping writes) |
| **unavailable** | `NoEmbeddingModelError` (including dimension mismatch) or `LlmUnreachableError` |
| **session text** | D6's composed string for one session |
| **refresh** | recompute a session's text and write or delete its `session_vec` row |
| **fan-out** | refreshing every session fed by one persona or setup text (D5) |
| **N** | the number of sessions a fan-out would refresh |
| **ensure** | idempotent create-if-absent of the virtual tables (D2) |
| **record row** | a `messages` row in `settled_entries`: `settled_at` set and `related_to` null |
| **coverage flag** | `search_coverage_incomplete` |
