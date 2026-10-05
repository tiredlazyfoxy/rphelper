# Feature 027 — Session search tool · feature-wide context

## What this feature is

The assistant's `session_search` tool. Mid-discussion, the assistant searches the **past
sessions under the same character** by meaning and gets back, for each match, a header line
(date and setup) and the tail of that session's settled record. The match runs on the vector
arm only, over `session_vec`, whose per-session text is the character's persona, the setup
text and the settled entries (024 composes and maintains it). Results never cross a user or a
character, never include the session being composed in, and never include an archived
session. A failure is reported to the assistant as "the tool failed" and the exchange
carries on.

The agreed boundary is `brief.md` in this folder (Definition, Scope In/Out). It is not
widened. **Out:** the lexical arm over the session index (deliberately not enabled; that
index is `029`'s); the loop and the seam (`021`); maintaining `session_vec` (`024`); the port
itself (`025`).

## Product ids

Delivers **FEAT-015** (UC-053, UC-054; US-067, US-068, US-069, US-138).

| Criterion | Where it lands |
|---|---|
| US-067.AC-1 (past session found) — mechanism | `001`; through the tool `003` |
| US-068.AC-1 (no setup, no partner field, still found) | `001` |
| US-069.AC-1 (never another character's session), UC-054 | `001`; through the tool `003` |
| US-069.AC-2 (never another user's session), UC-054 | `001`; through the tool `003` |
| US-138.AC-1 (entries + persona + setup in the match) | `001` (via 024's real composition) |
| US-138.AC-2 (similar person found though entries don't describe it) — mechanism | `001` |
| UC-053 main flow (assistant receives matching content) | `003` |
| UC-053 exception flow (failure → told, continues) | `003` (dispatch-level `[test]`; end-to-end `[manual/live]`) |
| "By meaning" for US-067.AC-1 / US-138.AC-2 (paraphrase, not identical text) | `003` `[manual/live]` — see "What the fake embedder can prove" |

Cited from FEAT-009, **only at the half 027 owns**:

| Criterion | 027's half | Not 027's |
|---|---|---|
| US-122.AC-2 (a settled decision appears in results) | the excerpt includes decision rows (`002`) | that the decision is in the embedded text — 024 |
| US-109.AC-2, US-110.AC-2 (after an edit, results reflect the new text) | the excerpt is read live, so it shows the current text (`002`) | re-embedding on edit — 024 |

## Build state — what is built and what is only planned

Features 001..015 are built. 016 is in progress (it does not touch any file 027 touches).
**017 and 019..026 are planned but NOT built.** 027 is built after all of them, after 026 in
particular (roadmap order 025 → 026 → 027).

**Binding rule for the 027 skeleton agent:** for every interface labelled **(B)** below, bind
to the exact identifier frozen in that plan's `status.md ## Skeleton` record. Only when that
record does not exist yet, fall back to the name used here (taken from the plan's step-file
prose). A frozen name that differs from the one below is not a 027 spec problem; follow the
frozen one.

### (A) Built source

- **`sessions`** (`app/db/schema.py`): `id`, `user_id`, `character_id` NOT NULL, `setup_id`
  nullable FK, `last_used_at`, `archived_at` nullable, `created_at`, `updated_at`. **No
  title, name or partner column.**
- **`characters`**: `name`, `sheet` (the persona), `archived_at`.
- **`setups`**: `id`, `user_id`, `character_id`, `name`, `description`, `archived_at`.
- **`settled_entries`** (`schema.py`, ~:384): a Core select over `messages` where
  `settled_at IS NOT NULL` — not a SQL view. It is the single definition of "the settled
  record" (R11); 027 adds no kind filter on top of it.
- **`app/services/sessions.py`**: `get_session(connection, user_id, session_id)`,
  `list_character_sessions(...)`, and the private `_reading` rollback pattern (readers roll
  back an autobegun transaction).
- **`app/errors.py`**: `NoEmbeddingModelError` (`no_embedding_model`), `LlmUnreachableError`
  (`llm_unreachable`).
- **`app/db/engine.py`**: `check_same_thread=False`, `isolation_level=None`. A connection may
  be used from another thread provided use is serialized (the basis of D6).
- **Service conventions**: SQLAlchemy Core; `connection` first, then `user_id`.

### (B) Pending plans

- **025 — the port** (`app/services/search/`):
  - `ports.py`: the session scope variant (`SessionSearchScope`, frozen): required `user_id`,
    optional extra-predicate builder — a callable from the base relation (`sessions`, possibly
    aliased) to a boolean clause over that relation's columns. The port ANDs
    `user_id = :user_id`. The variant fixes the arms: `session_vec` vector arm only, no flag.
    The port has **no archive predicate** of its own.
  - A session `SearchHit`: kind `"session"`, id = the session id, score, **snippet none**,
    memo fields none.
  - `hybrid.py`: `search(connection, scope, query, limit, *, client_factory,
    timeout_seconds)` → list of `SearchHit`, best first. **Synchronous**; embeds the query
    through 024's `asyncio.run` bridge, so it must not run on a thread with a running loop.
    Blank query or `limit <= 0` → `[]`. Absent or empty `session_vec` → `[]`. Raises
    `NoEmbeddingModelError`, `LlmUnreachableError` and the `secret_ref_missing` error
    unchanged; no degrade. Defaults: `get_llm_client_factory` (`app/dependencies.py`) and
    `DEFAULT_EMBED_TIMEOUT_SECONDS` (`services/embedding.py`).
  - 025 `outcome.md` "Flags for other owners": the caller runs it off-loop (closed by D6);
    the tool decides the text that represents a session in its result (closed by D3).
    025 `004` DoD-8 already proves a character + `id != current` predicate works.
- **024 — the session index** (test setup only for 027):
  - `session_vec`: vec0, one vector per session. Its text is `characters.sheet` +
    `setups.description` (when there is a setup) + each settled entry's text in ascending
    id, joined by `"\n\n"`, empties dropped. A session whose composed text is empty has no
    vector. Archived sessions are re-embedded too.
  - `compose_session_text(connection, user_id, session_id)` → that text;
    `refresh_session_vectors(...)` re-embeds sessions with a given client factory.
  - `app/db/search_tables.py` `ensure_vector_tables(conn, dim)`; `services/embedding.py`
    `write_vector(conn, table, id, vec)` and `DEFAULT_EMBED_TIMEOUT_SECONDS`;
    `backend/tests/llm_fakes.py` (fake client factory, a pure `(text, dim)` vector function,
    scriptable to raise `LlmUnreachableError`). A designated model is raw `llm_servers` +
    `models` rows (`is_embedding_designated`, `embedding_dim`, small, e.g. 8).
- **021 — the seam** (`app/services/tools/`):
  - `definitions.py`: the `session_search` declaration, exactly one parameter `query`.
    **027 does not change it.**
  - `seam.py`: `ToolScope(user_id, session_id, character_id, setup_id | None)`, built only
    by the seam from an owner-scoped session read; `ToolOutcome(content, summary)`; the
    `Tool` protocol (`name`, async `run(scope, connection, arguments) -> ToolOutcome`); the
    production registry (a read-only mapping, read by `routers/stream.py`'s registry
    dependency); `offered_tools` (switch on ∩ registered; gates `session_search` on the
    `tool_session_search` switch); `dispatch` (any `Exception` from `run` → `tool_fail`
    frame, code `tool_failed`, model message `The tool failed. Continue without its result.`,
    a failed tool row; the exchange continues). The seam opens a fresh short-lived
    connection for `run` and closes it.
  - `app/errors.py` `ToolFailedError` (`tool_failed`, detail carries the tool name) — 021
    step `001`.
  - 021 implementer rules (021 `outcome.md`): build the search scope from `ToolScope`, never
    from arguments; leave no transaction open; `summary` never contains raw content; raise on
    failure.
- **026 — the first tool** (built before 027):
  - The production registry holds exactly `memo_search`.
  - The adapter pattern 027 mirrors: `asyncio.to_thread` on the seam's connection (026 D3);
    seam names imported under `TYPE_CHECKING` only; `ToolOutcome` imported inside the
    function that constructs it (026 `002.context.md` "The import cycle").
  - 026 amended three 021 test assertions to "exactly `memo_search`"; 027 amends them again,
    plus one of 026's own (step `003`).
- **017 — the switch**: `tool_session_search` is a resolved session setting with a bool
  value. 027 does not read it; the seam's `offered_tools` does.

## Architecture this binds to

- `search-and-retrieval.md` "`session_search` — FEAT-015": vector arm only (no BM25, no
  RRF; nobody turns the second arm on); the scope predicate applied before ranking and tested
  with data that would match; "What text represents a session"; the current-session
  exclusion inference; Failure.
- `search-and-retrieval.md` embedding lifecycle `_TBD:` (~L516-521) on the cost of
  re-embedding growing session text: handed to "FEAT-015's plan". **027 does not close it**
  (no measurement exists; bounding the composed text would be 024's code). `outcome.md`
  carries it forward as open.
- `data-model.md`: `session_vec` (vec0, `session_id` key, one vector per session).
- `llm-and-streaming.md` "The tool-calling loop" (~L350-393): a failed tool is a tool result;
  `session_search` additionally carries `character_id` in its scope.
- `domain-rules.md`: **R5** (owner scope in SQL; never cross a character), **R9** (three
  tools; failure does not end the discussion), **R11** (session text composed through
  `settled_entries`).
- 026 `context.md` D3 (off-loop pattern); 025 `context.md` port contract; 021 `context.md`
  D5, D6, D7 and its literals table.

Cited, never copied.

## Files this feature touches

```
backend/app/services/search/session_search.py  # NEW — constants, predicate, search_sessions (001)
                                               #       + owner-scoped excerpt read          (002)
backend/app/services/tools/session_search.py   # NEW — the Tool adapter + formatter         (003)
backend/app/services/tools/seam.py             # production registry gains session_search
                                               #   (021-owned; the one edit to it)          (003)
```

Test files are listed per step. Three **existing** test files are amended in step `003`
(`test_tool_seam.py`, `test_compose_route.py` — 021's; `test_memo_search_tool.py` — 026's),
only at the assertions the registration makes false; see `003.context.md`.

**Not touched — a step that touches one is out of scope:** `app/db/schema.py`,
`app/db/search_tables.py`, `app/db/engine.py`, `app/errors.py`, `app/dependencies.py`,
`app/services/sessions.py`, `app/services/embedding.py`, `app/services/memo_chain.py`,
everything else under `app/services/search/` (the 025 port, 026's `memo_search.py`) and
`app/services/tools/` (including `definitions.py`, `memo_search.py`, `__init__.py`), every
024 module, every router, `main.py`, `tests/conftest.py`, `tests/llm_fakes.py`. No new
dependency. No frontend.

## Decisions

### D1 — Scope predicate (user-confirmed)

The extra predicate 027 hands the port is, over the base relation (`sessions`):

`character_id = :character_id AND id != :current_session_id AND archived_at IS NULL`

The port ANDs `user_id = :user_id`. All four ids come from `ToolScope` (D7).

- **The current session is excluded** — the architecture's recorded inference, adopted.
- **Archived past sessions are excluded** (user-confirmed). This is a predicate the
  architecture does not list; `outcome.md` records it. Restoring a session (clearing
  `archived_at`) makes it findable again with no re-embed, because 024 keeps archived
  sessions' vectors current.
- The archive predicate is on the **session** only. A session whose **setup** is archived is
  still searchable (its setup's name still shows, D3).

### D2 — Result cap: 5, no paging (user-confirmed)

At most **5** hits. A named constant in `services/search/session_search.py`, passed to the
port as `limit`. No paging, no offset, no count argument: the declaration stays `query`
only. Each hit carries a long excerpt, so the cap is lower than `memo_search`'s 8.

### D3 — What the model receives (user-confirmed: header + tail excerpt)

Closes the brief's open question. Per hit, in the port's rank order, one **block**:

```
### Session <YYYY-MM-DD> · setup: <setup name>
<excerpt>
```

or, when the session has no setup, the header `### Session <YYYY-MM-DD> · no setup`.

- **`<YYYY-MM-DD>`** is the session's `created_at` as a UTC calendar date in ISO form (a
  naive stored value is taken as UTC). Planner decision: `created_at` is when the RP
  happened; `last_used_at`/`updated_at` move on unrelated writes.
- The separator in the header is ` · ` (space, U+00B7 MIDDLE DOT, space).
- **`<setup name>`** is `setups.name`, shown even when the setup is archived (it is a name,
  not content; archiving never destroys — R6).
- **`<excerpt>`**: the session's settled entries' text (`settled_entries`, ascending id,
  joined by `"\n\n"`, entries with empty text skipped — the same joining 024 uses). If the
  joined text is longer than **1500** characters, the excerpt is `…` (U+2026, no following
  space) followed by the **last 1500** characters; otherwise it is the joined text
  unchanged. Decisions are included (they are settled rows); current-zone and buried rows
  are not (they are not in `settled_entries`).
- A matched session with **no settled entries** (findable by persona/setup alone) has the
  body line `(no settled entries)` in place of the excerpt.
- Block = header line, `\n`, body. Blocks are joined by `\n\n` (one blank line between).
- **No persona text** (it is the same character, already in context), **no setup
  description**, **no ids** in the content.
- **Zero hits** is a success: content is exactly `No matching sessions.`
- **Summary**: exactly `<N> sessions`, N the number of blocks (`0 sessions`, `1 sessions`,
  `5 sessions`). It never contains content.

### D4 — The excerpt read is 027's own owner-scoped hydration

The port returns ids and scores only (snippet none). The header fields and excerpt are read
by a function in `services/search/session_search.py`: one owner-scoped read by `user_id`
and the hit ids (sessions joined to their setup when present; messages through
`settled_entries`), returning one record per id **in the given id order**. An id that is
not the user's session is dropped (defence in depth; the port already scoped it). It reads
only, and leaves no transaction open. The excerpt bound and marker are applied here, so an
unbounded session text never reaches the adapter.

### D5 — Failure

`run` raises; it never builds its own failure outcome. Port errors propagate unchanged
(`no_embedding_model`, `llm_unreachable`, `secret_ref_missing`), and arguments without a
string `query` raise `ToolFailedError`. The seam converts any `Exception` into the
`tool_fail` frame and the "tool failed" model message (021 D6). No transaction is left open
on success **or** on failure.

### D6 — Placement and off-loop (mirrors 026 D3)

- `services/search/session_search.py`: the two constants, the predicate factory, the sync
  `search_sessions` (port call), and the sync excerpt read (D4). Imports no `fastapi` and
  nothing from `app.services.tools`.
- `services/tools/session_search.py`: the `Tool` adapter and the pure formatter. Its async
  `run` performs the search **and** the excerpt read in **one** `asyncio.to_thread` call on
  the connection the seam handed it, sequentially (safe for the same reason as 026 D3:
  `check_same_thread=False`, one thread at a time; the worker thread has no running loop, so
  the port's `asyncio.run` bridge works).
- Registration: the production registry in `services/tools/seam.py` maps `session_search` to
  a default-constructed adapter, beside `memo_search`. The single edit to a 021-owned source
  file.

### D7 — Ids come only from `ToolScope`

`run` reads exactly one key from `arguments`: `query`. Any other key — `user_id`,
`session_id`, `character_id`, `setup_id`, `current_session_id` — is ignored. `ToolScope`'s
`setup_id` is not used (the search is per character, not per setup).

## Literals — the contract tests bind to

| Name | Exact value | Used by |
|---|---|---|
| result cap | `5` | D2 (`001`) |
| excerpt length | `1500` characters | D3 (`002`) |
| truncation marker | `…` (U+2026), prepended, no space | D3 (`002`) |
| header with setup | `### Session <YYYY-MM-DD> · setup: <setup name>` | D3 (`003`) |
| header without setup | `### Session <YYYY-MM-DD> · no setup` | D3 (`003`) |
| no-entries body | `(no settled entries)` | D3 (`003`) |
| block separator | `\n\n`; header and body separated by `\n` | D3 (`003`) |
| excerpt entry separator | `\n\n` | D3 (`002`) |
| zero-hit content | `No matching sessions.` | D3 (`003`) |
| summary | `<N> sessions` | D3 (`003`) |
| tool name | `session_search` | D6 (`003`) |
| switch (017's) | `tool_session_search` | `003` |
| failed model message (021's) | `The tool failed. Continue without its result.` | D5 (`003`) |
| fail code (021's) | `tool_failed` | D5 (`003`) |

## What the fake embedder can prove — and what it cannot

`llm_fakes.py`'s vector function is **deterministic, not semantic**: equal text gives an
equal vector; different text gives an unrelated vector. So:

- **Can prove (automated):** that a session's vector is consulted and ranks it (a query equal
  to a session's composed text puts that session first, at distance zero); that the scope
  predicate removes a session whose vector is **identical** to the query's (the strongest
  "would match" there is); that a session with no settled entries is findable at all,
  because its persona is in its representation (US-138.AC-2's mechanism); the cap; the
  shape.
- **Cannot prove:** that a *paraphrase* finds the session — "by meaning". That needs a real
  embedding model and is `[manual/live]` in step `003`. Tests must not claim it.

Test expectations about rank therefore use **exact composed text** as the query, obtained
from 024's `compose_session_text` (a verified 024 contract, not the code under test).

## Cross-cutting constraints

- Sync SQLAlchemy Core; `connection` first, then `user_id`.
- Backend fully typed; `mypy app` and `ruff check .` green after every step (commands in the
  root `CLAUDE.md`).
- Vector arm only: 027 passes no flag, builds no FTS query and never touches `session_fts`.
- Absences are tested with data that **would** match: every excluded session has the same
  persona text and the same settled entries as an included one, so its composed text — and
  so its fake vector — is identical, and it carries a `session_vec` row from the real 024
  path. An absence therefore means the predicate excluded it.

## Test conventions

From `backend/`. pytest, flat `tests/`, names `test_<behavior>__S027_<SSS>_DoD<n>`.

- Each new file has its own engine fixture (`schema.metadata.create_all`) and file-local
  raw-insert helpers (`_insert_user`, `_insert_character(sheet=…)`, `_insert_setup(name=…,
  description=…, archived_at=…)`, `_insert_session(setup_id=None|…, archived_at=…,
  created_at=…)`, `_insert_message(settled_at=…, kind=…, text=…)`), ids above 2^60, two
  users A and B. `conftest.py` is untouched.
- Vectors come from the **real 024 path**: `ensure_vector_tables` with a small dim, then
  either 024's `refresh_session_vectors` with the fake factory, or `write_vector` with the
  fake's `(text, dim)` vector of `compose_session_text` — prefer `refresh_session_vectors`
  so persona and setup are really in the embedded text. A designated model is raw
  `llm_servers` + `models` rows; the fake factory is passed as `client_factory=`. **The port
  is never mocked. No monkeypatching.**
- Async code is driven with `asyncio.run(...)` from sync tests (no async plugin).
- Expected values come from this plan (D1–D7, the literals) and from the seeded data — never
  from calling the code under test.

## Vocabulary

| Term | Means here |
|---|---|
| **current session** | `ToolScope.session_id` — the session being composed in; never a result |
| **past session** | another, non-archived session of the same user and character |
| **composed text** | 024's per-session embedded text (persona + setup description + settled entries) |
| **excerpt** | D3's tail of the settled entries only — not the composed text |
| **block** | one hit's header line plus body |
| **extra predicate** | D1's builder handed to the port |
| **the adapter** | the `session_search` `Tool` implementation (D6) |
