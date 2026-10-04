# Feature 026 — Memo search tool · feature-wide context

## What this feature is

The assistant's `memo_search` tool. Mid-discussion, the assistant searches the session's
whole memo chain and gets back the notes that are **enabled and not forced**, each as a
snippet plus its level. Forced notes are excluded because they are already in the system
prompt. Disabled notes are excluded because they reach the assistant by no path. The tool
works with no setup level (three levels, no gap), never returns another user's notes, and a
failure is reported to the assistant as "the tool failed" while the exchange carries on.

The agreed boundary is `brief.md` in this folder (Definition, Scope In/Out). It is not
widened. **Out:** the loop and the seam (`021`); the roleplayer's own search (`029`, which
deliberately applies the opposite flag rule); embedding notes (`024`); the port itself
(`025`).

## Product ids

Delivers **FEAT-014** (UC-051, UC-052; US-063..066) and the `memo_search` halves of FEAT-012's
**US-099** and **US-100**.

| Criterion | Where it lands |
|---|---|
| US-063.AC-1 (all four levels reached) | `001` |
| US-064.AC-1 (never another user's memos) | `001` |
| US-065.AC-1 (no setup, no gap) | `001` |
| US-099.AC-2 (enabled, not forced → returned) | `001` |
| US-100.AC-2, UC-052 (forced / disabled → absent); also exercises US-055.AC-2 | `001` |
| UC-051 main flow (assistant receives matching content) | `002` |
| US-066.AC-1, UC-051 exception flow (failure → told, continues) | `002` (dispatch-level `[test]`; end-to-end `[manual/live]`) |

**Not 026's:** US-099.AC-1 and US-100.AC-1 (system-prompt halves) belong to context assembly
(`020`) and are not cited here.

## Build state — what is built and what is only planned

Features 001..015 are built. 016 is in progress (its working-tree edits touch
`services/memos.py`, which 026 does not change). **017, 020, 021, 024 and 025 are planned but
NOT built.** 026 is built after all of them.

**Binding rule for the 026 skeleton agent:** for every interface labelled **(B)** below, bind
to the exact identifier frozen in that plan's `status.md ## Skeleton` record. Only when that
record does not exist yet, fall back to the name used here (taken from the plan's step-file
prose). A frozen name that differs from the one below is not a 026 spec problem; follow the
frozen one.

### (A) Built source

- **`memos` table** (`app/db/schema.py`): `id` (snowflake), `user_id` FK, `scope` enum
  `user|character|setup|session`, `scope_id` NOT NULL with **no FK**, `body`, `is_enabled`
  (default true), `is_forced` (default false), `sort_key`, `created_at`, `updated_at`. The
  user level stores `scope_id = user_id`. No title column (US-119).
- **`sessions`**: `character_id` NOT NULL; `setup_id` nullable.
- **`app/services/memo_chain.py`**: `resolve_chain(connection, user_id, session_id)` →
  list of `MemoChainLevel(scope, scope_id, memos)`; builds one inline OR-term per existing
  level (setup term omitted when `setup_id` is None); `memo_reach(is_enabled, is_forced)`.
  No reusable clause helper exists today (step `001` adds one).
- **`app/models/memos.py`**: the `MemoScope` literal (`user|character|setup|session`).
- **`app/errors.py`**: `DomainError` subclasses with `code` / `http_status`;
  `NoEmbeddingModelError` (`no_embedding_model`). `LlmUnreachableError` (`llm_unreachable`).
- **`app/db/engine.py`**: `create_engine(..., connect_args={"check_same_thread": False,
  "isolation_level": None})`, default pool. A connection may be used from another thread
  provided use is serialized (the basis of D3).
- **Service conventions**: SQLAlchemy Core; `connection` first, then `user_id`; readers roll
  back an autobegun transaction (the `_reading` pattern, private to each module).

### (B) Pending plans

- **025 — the port** (`app/services/search/`):
  - `ports.py`: the scope variant for memos (`MemoSearchScope`: required `user_id`, optional
    extra-predicate builder — a callable from the base relation the port uses as its FROM
    object to a boolean clause over that relation's columns; the port ANDs it with
    `user_id = :user_id`). `SearchHit` fields: kind, id, score, snippet (plain text, never
    none for a memo), memo `scope`, memo `scope_id`, `session_id`. No level name, no title.
  - `hybrid.py`: `search(connection, scope, query, limit, *, client_factory,
    timeout_seconds)` → list of `SearchHit`, best first. **Synchronous**; embeds the query
    through 024's `asyncio.run` bridge, so it must not run on a thread with a running event
    loop. Blank query or `limit <= 0` → `[]`. Raises `NoEmbeddingModelError`,
    `LlmUnreachableError` and the `secret_ref_missing` error; no lexical-only degrade.
    Defaults: `get_llm_client_factory` (`app/dependencies.py`) and
    `DEFAULT_EMBED_TIMEOUT_SECONDS` (`services/embedding.py`).
  - 025 `outcome.md` hands 026: add `services/search/memo_search.py`; build the extra
    predicate (chain + `is_enabled AND NOT is_forced`, in R3 order); run sync `search` off
    the event loop (closed here by D3).
- **021 — the seam** (`app/services/tools/`):
  - `definitions.py`: the `memo_search` declaration, exactly one parameter `query`.
    **026 does not change it.**
  - `seam.py`: `ToolScope(user_id, session_id, character_id, setup_id | None)`, built only
    by the seam from an owner-scoped session read; `ToolOutcome(content, summary)`; the
    `Tool` protocol (`name`, async `run(scope, connection, arguments) -> ToolOutcome`); the
    production registry (name → `Tool`, empty after 021, read by `routers/stream.py`'s
    registry dependency); `offered_tools` (switch on ∩ registered); `dispatch` (any
    `Exception` from `run` → `tool_fail` frame with code `tool_failed`, model message
    `The tool failed. Continue without its result.`, a failed tool row; the exchange
    continues). The seam opens a **fresh short-lived connection** for `run` and closes it.
  - `app/errors.py` gains `ToolFailedError` (`tool_failed`, `detail` carries the tool name)
    in 021 step `001`.
  - 021 implementer rules (021 `outcome.md` forward notes): implement `Tool` and register
    under `memo_search`; build the `SearchScope` from `ToolScope`, never from arguments;
    leave no transaction open; `summary` never contains raw content; raise on failure.
- **024 — the indexes** (test setup only for 026): `memo_fts` (fts5 over `memos.body`,
  external content, kept in sync by triggers), `memo_vec` (vec0, `memo_id` key),
  `app/db/search_tables.py` `ensure_fts_tables` / `ensure_vector_tables`,
  `services/embedding.py` `write_vector`, and `backend/tests/llm_fakes.py` (deterministic
  fake embedder + factory, scriptable to raise `LlmUnreachableError`, passed as
  `client_factory=`). A designated model is raw `llm_servers` + `models` rows
  (`is_embedding_designated`, `embedding_dim`).
- **017 — the switch**: `tool_memo_search` is a resolved session setting whose `value` is a
  bool. 026 does not read it; the seam's `offered_tools` does.

## Architecture this binds to

- `search-and-retrieval.md`: "The narrow port"; "A memo hit is a snippet plus a level — there
  is no title"; "`memo_search` — FEAT-014" (the scope predicate, R3 ordering, no-setup rule,
  failure rule).
- `llm-and-streaming.md`: "The tool-calling loop" (a failed tool is a tool result; scoped
  reads; disabled tool not offered).
- `domain-rules.md`: **R2** (chain as a predicate over existing levels; no-setup = one fewer
  term), **R3** (`is_enabled` gates first, then `NOT is_forced`), **R5** (owner scope in
  SQL), **R9** (closed at three tools; failure does not end the discussion).
- 025 `context.md` U1–U3, D3, D4, D7; 021 `context.md` D5, D6, D7, D13 and its literals
  table.

Cited, never copied.

## Files this feature touches

```
backend/app/services/memo_chain.py           # + chain clause builder (built module)      (001)
backend/app/services/search/memo_search.py   # NEW — limit constant, scope, search_memos (001)
backend/app/services/tools/memo_search.py    # NEW — the Tool adapter + formatting       (002)
backend/app/services/tools/seam.py           # production registry gains memo_search
                                             #   (021-owned; the one edit to it)          (002)
```

Test files are listed per step. Two **021-owned** test files are amended in step `002`
(`test_tool_seam.py`, `test_compose_route.py`), only at the assertions the registration
makes false; see `002.context.md`.

**Not touched — a step that touches one is out of scope:** `app/db/schema.py`,
`app/db/search_tables.py`, `app/db/engine.py`, `app/errors.py`, `app/dependencies.py`,
`app/services/memos.py`, `app/models/memos.py`, everything else under
`app/services/search/` and `app/services/tools/` (including `definitions.py` and
`__init__.py`), `app/services/embedding.py`, every router, `main.py`, `tests/conftest.py`,
`tests/llm_fakes.py`, the existing memo-chain test file. No new dependency. No frontend.

## Decisions

### D1 — Result count: fixed 8, no paging (user-confirmed)

The tool returns at most **8** hits. The number is a named constant in
`services/search/memo_search.py`, passed to the port as `limit`. There is no paging, no
offset and no count argument: the declaration stays `query` only. An assistant that wants
more re-queries with different words. Conventional, not measured (the architecture's
`_TBD:` on result count stays open as a relevance question; the value itself is settled).
Closes the brief's open question.

### D2 — The chain predicate has one home

A reusable clause builder lives beside `resolve_chain` in `services/memo_chain.py`, so the
chain (R2) is defined in one place. Given a relation exposing `scope` / `scope_id` columns
and the level ids (user, character, setup or none, session), it returns the OR-disjunction
of `(scope = level AND scope_id = level id)`, **omitting the setup term when setup is none**.
The user level's id is the user id.

The memo-search extra predicate is `is_enabled AND NOT is_forced AND <chain disjunction>`,
**`is_enabled` first** (R3). The port ANDs in `user_id`. Both flags always appear;
`is_enabled` is never dropped as implied. `resolve_chain` may be re-routed through the
builder only if its existing tests stay untouched and green; otherwise it is left alone.

### D3 — Placement, and how the sync port runs under the async loop

- `services/search/memo_search.py`: the constant, the scope construction and a **sync**
  `search_memos` that wraps the port with the constant limit. Knows nothing of tools.
- `services/tools/memo_search.py`: the `Tool` adapter. Its async `run` calls `search_memos`
  through **`asyncio.to_thread`**, on the connection the seam handed it. Safe because the
  engine sets `check_same_thread=False` and the connection is used by one thread at a time
  (the awaiting coroutine does nothing with it meanwhile). The worker thread has no running
  loop, so the port's internal `asyncio.run` works (024 `002` DoD-7 proves the bridge from a
  worker thread). This closes 025's off-loop flag.
- Registration: the production registry in **`services/tools/seam.py`** (where 021 defines
  it) maps `memo_search` to an instance of the adapter. This is the single edit to a
  021-owned source file.

### D4 — What the model receives

- **Content:** one line per hit, in the port's fused-rank order, `[<level>] <snippet>`,
  where `<level>` is the hit's scope literal (`user`, `character`, `setup`, `session`).
  Lines are joined with `\n`. The snippet's whitespace runs (including newlines) are
  collapsed to one space and the ends stripped, so each hit is exactly one line (planner
  decision: FTS5 snippets of markdown bodies can contain newlines).
- **Zero hits** is a success, not a failure: content is exactly `No matching notes.`
- **Summary:** exactly `<N> memos`, N the number of hits (`0 memos`, `1 memos`, `8 memos`;
  architecture frame example `3 memos`). It never contains any content.
- No titles (US-119), no character or setup names, no ids in the content.

### D5 — Failure

`run` raises; it never builds its own failure outcome. Domain and LLM errors propagate
unchanged (`no_embedding_model`, `llm_unreachable`, `secret_ref_missing`), and arguments
without a string `query` raise `ToolFailedError`. The seam converts any `Exception` into the
`tool_fail` frame and the "tool failed" model message (021 D6). `run` leaves no transaction
open on success **and** on failure.

### D6 — Ids come only from `ToolScope`

`run` reads exactly one key from `arguments`: `query`. Any other key — `user_id`,
`session_id`, `character_id`, `setup_id`, `scope` — is ignored. The level ids passed to
`search_memos` are the `ToolScope`'s.

## Literals — the contract tests bind to

| Name | Exact value | Used by |
|---|---|---|
| result cap | `8` | D1 (`001`) |
| content line | `[<level>] <snippet>`, lines joined by `\n` | D4 (`002`) |
| zero-hit content | `No matching notes.` | D4 (`002`) |
| summary | `<N> memos` | D4 (`002`) |
| tool name | `memo_search` | D3 (`002`) |
| failed model message (021's) | `The tool failed. Continue without its result.` | D5 (`002`) |
| fail code (021's) | `tool_failed` | D5 (`002`) |

## Cross-cutting constraints

- Sync SQLAlchemy Core; `connection` first. `services/search/memo_search.py` imports no
  `fastapi` and nothing from `app.services.tools`. `services/tools/memo_search.py` imports no
  `fastapi`.
- Backend fully typed; `mypy app` and `ruff check .` green after every step (commands in the
  root `CLAUDE.md`).
- R3 ordering survives into the predicate as written: `is_enabled` before `is_forced`.
- Absences are tested as absences, with data that **would** match: every excluded note
  carries the same distinctive token as the included ones, in its body (so it hits
  `memo_fts`) and with a vector (so it hits `memo_vec`).

## Test conventions

From `backend/`. pytest, flat `tests/`, names `test_<behavior>__S026_<SSS>_DoD<n>`.

- Each new file has its own engine fixture (`schema.metadata.create_all`) and file-local
  raw-insert helpers (`_insert_user`, `_insert_character`, `_insert_setup`,
  `_insert_session` — one variant with `setup_id=None` — `_insert_memo(..., is_enabled,
  is_forced)`), ids above 2^60, two users A and B. `conftest.py` is untouched.
- The search tables are real: created with 024's `ensure_fts_tables` /
  `ensure_vector_tables` (so the `memo_fts` triggers index raw-inserted memos), vectors
  written with 024's `write_vector` from `llm_fakes.py`'s pure `(text, dim)` function, a
  designated model as raw `llm_servers` + `models` rows (small dim, e.g. 8), the fake
  factory passed as `client_factory=`. **The port is never mocked. No monkeypatching.**
- Async code is driven with `asyncio.run(...)` from sync tests (no async plugin), as 021's
  tests do.
- Expected values come from this plan (D1–D6, the literals) and from the seeded data —
  never from calling the code under test.

## Vocabulary

| Term | Means here |
|---|---|
| **level** | one of `user`, `character`, `setup`, `session`; a hit's memo `scope` |
| **chain** | the session's existing levels with their ids (R2) |
| **chain clause** | D2's OR-disjunction over the chain |
| **extra predicate** | the builder 026 hands the port: flags (R3 order) AND chain clause |
| **searchable** | `is_enabled AND NOT is_forced` |
| **the adapter** | the `memo_search` `Tool` implementation (D3) |
