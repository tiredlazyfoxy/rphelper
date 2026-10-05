# Feature 029 — my-search

| Step | File                                   | Status  | Verifier | Date |
|------|----------------------------------------|---------|----------|------|
| 001  | `001.like-corpora.md`                  | done    | PASS     | 2026-10-05 |
| 002  | `002.my-search-orchestrator.md`        | done    | PASS     | 2026-10-05 |
| 003  | `003.search-route.md`                  | done    | PASS     | 2026-10-05 |
| 004  | `004.search-api-and-state.md`          | done    | PASS     | 2026-10-05 |
| 005  | `005.search-screen.md`                 | done    | PASS     | 2026-10-05 |
| 006  | `006.tree-input-and-landing.md`        | done    | PASS     | 2026-10-05 |

## Files Changed

### Step 001 — cap, read posture and the two LIKE corpora
- `backend/app/services/search/my_search.py` — `search_characters` / `search_setups` implemented: stripped
  needle, blank → `[]` with no SQL, `contains(..., autoescape=True)` over the two columns per kind,
  owner predicate on every base table, `name` then `id` order, archived included and flagged

### Step 002 — hydration and the `run_my_search` orchestrator
- `backend/app/services/search/my_search.py` — the three `_hydrate_*` reads (session label join, entry
  through the `settled_entries` subquery, memo with the setup outer join and the user-level
  `scope_id` → `None` reduction) and `run_my_search` (blank short-circuit, D5 order, fail-whole)

### Step 003 — `GET /api/search`: response models, router, registration
- `backend/app/models/search.py` — the five `*HitResponse` leaf models and `MySearchResponse` (five
  groups in UC-059 order, ids as `SnowflakeOut`); declared by the skeleton, unchanged here
- `backend/app/routers/search.py` — `_to_response` implemented (outer model by keyword, each leaf via
  `<Kind>HitResponse.model_validate(hit, from_attributes=True)`) and the sync `my_search` body
  (`run_my_search(connection, current_user.id, q, client_factory=…,
  timeout_seconds=settings.llm_request_timeout_seconds)`, nothing caught — U1 fail-whole); import block
  gained `run_my_search` and the five leaf models
- `backend/app/main.py` — search router import, `include_router` last and the two docstring
  enumerations; done by the skeleton, untouched here

### Step 004 — `searchApi.ts` and `searchState.ts`: wire types, load, URL and target helpers
- `frontend/src/app/searchApi.ts` — `fetchMySearch` implemented: `apiGet<MySearchResults | undefined>`
  on `/api/search` with the text appended as `q` through `URLSearchParams` (house idiom, memosApi),
  empty-body fallback to five empty groups; the six frozen types untouched
- `frontend/src/app/searchState.ts` — `isBlankQuery`, `loadSearch` (blank → idle + both fields
  cleared with no request; `"loading"` writes only `status`; terminal writes through `runInAction`
  with an abort check before each; `ApiError` message or the house generic text; never rejects),
  `hasNoHits`, `searchHref` (`encodeURIComponent`, untrimmed) and the five `*Target` helpers over
  two private route builders; the class stayed a pure data contract

### Step 005 — `SearchScreen`: the box, the grouped results, the markings
- `frontend/src/app/SearchScreen.tsx` — the real tree in place of the `void` block: the `q` read, the
  box (`label` `Search query`, value local and reset from `q`, Enter → `void navigate(searchHref(text))`),
  the focus effect keyed on `useLocation().key` (D9), the load effect with a fresh `AbortController`
  per `q` (previous and unmount aborted) plus the same for `Retry`, the four states, and the five
  groups through one private `SearchGroup` region wrapper and one private `SearchRow` list row
  (link = the hit's `*Target`, dimmed/`Archived` and dimmed+struck/`Disabled` markings in Mantine
  props, snippets as plain `Anchor`/`Text` content, level label never a title)
- `frontend/src/app/App.tsx` — `/search` → `<SearchScreen />`; done by the skeleton, untouched here
- **Repair (verify FAIL, Fault CODE — DoD-4/5/6, session group only):** `SearchRow` now renders the
  secondary line **inside** the `Anchor` instead of as a sibling beneath it, so a row's link carries its
  whole label. Only a session row was observably wrong — it has no name, its primary text is just
  `formatSessionStart(created_at)`, and all of its identifying material (character, and setup when
  there is one) lived outside the link, leaving it identifiable and activatable by timestamp alone.
  The tree's `NavLink` session row is the precedent: label **and** description inside the anchor, the
  `Archived` badge an outside sibling. The badge stayed where it was (outside the link, inside the
  `<li>` — DoD-4 depends on it); each line is still its own text node and the secondary one keeps its
  dimmed small styling, with `td="line-through"` moved onto the primary line it marks so the secondary
  line is never struck. No call site, constant or signature changed

### Step 006 — the tree's search input, and landing on an entry or an opened wall
- `frontend/src/app/CharacterTree.tsx` — the Enter handler's body: `void navigate(searchHref(searchText))`
  behind the kept `event.key` guard, plus the `searchHref` import the skeleton deliberately left out;
  `searchHref("")` already answers `/search`, so a blank box needs no branch. The `New character`
  button and the `Show archived` switch untouched
- `frontend/src/app/SessionScreen.tsx` — the `void` block replaced by the real URL read:
  `useSearchParams` imported, `focusEntryId = searchParams.get(ENTRY_PARAM)` forwarded to
  `SessionStream`, and an **open-only** effect keyed on the `notes` value that calls `openWall(wall)`
  when it is exactly `NOTES_OPEN_VALUE` (decision 11: absence, any other value and a later in-entry
  navigation leave the wall and its pin untouched — nothing closes)
- `frontend/src/app/SessionStream.tsx` — **not touched by the coder**; the skeleton's prop and
  forwarding line were already complete (no router hook here — decision 9)
- `frontend/src/app/StreamRecord.tsx` — the `void` block replaced by the anchor effect in
  `StreamEntry`: on becoming the focus entry it scrolls `scrollRef.current` into view centred
  **once** (a `scrolledForId` ref records the id already scrolled for, so no re-render — hover,
  focus, a translation, a discussion group, or the highlight clearing — scrolls again), holds
  `data-highlighted="true"` plus `bg={HIGHLIGHT_BG}` for `HIGHLIGHT_DURATION_MS` and drops both,
  with the timer cleared in the effect's cleanup so it cannot fire after unmount. A non-focus entry
  does nothing; `data-entry-id` was already the skeleton's

## Skeleton

### Step 001 — frozen interface (2026-10-05)

`backend/app/services/search/my_search.py` — **new**, the only file touched. Imports exactly
`from collections.abc import Iterator`, `from contextlib import contextmanager`,
`from dataclasses import dataclass`, `from typing import Final`, `from sqlalchemy import Connection`
— no `fastapi`, no `starlette`, no `sqlite_vec`, no `from __future__ import annotations`. The coder
adds `select` / `and_` / `app.db.schema.characters` / `app.db.schema.setups` himself: only the
unimplemented bodies need them and `F401` is on.

- `MY_SEARCH_PER_KIND_LIMIT: Final[int] = 20` — new. **The value `20` is part of the freeze** (D2).
  Named for the sibling convention in this package (`MEMO_SEARCH_LIMIT`, `SESSION_SEARCH_LIMIT`:
  module-prefixed `*_LIMIT`), with `PER_KIND` spelled out because a bare `MY_SEARCH_LIMIT` would
  read as a budget for the whole search, while this caps **each** of the five groups (so five full
  groups = 100 rows). Step `002` passes this same constant as every port call's `limit`.
- `@contextmanager def _reading(connection: Connection) -> Iterator[None]` — new, private.
  **Implemented for real, deliberately**: a `@contextmanager` whose body raises cannot be used by a
  `with`, so a stub would block both the test-coder and step `002`. The five lines are read posture,
  not feature behaviour — copied verbatim (docstring included) from `services/memos.py:364-372` per
  D6: `opened_here = not connection.in_transaction()` captured **before** the `yield`, rollback in a
  `finally` only `if opened_here and connection.in_transaction()`. Never imported from `memos.py`;
  used by steps `001` **and** `002`.
- `@dataclass(frozen=True) class CharacterHit` — new. Fields in order `id: int`, `name: str`,
  `archived: bool`. Field order is the wire contract's, so step `003` can `model_validate(...,
  from_attributes=True)`.
- `@dataclass(frozen=True) class SetupHit` — new. Fields in order `id: int`, `name: str`,
  `character_id: int`, `character_name: str`, `archived: bool`. `archived` is the **setup's own**
  `archived_at`, never its character's (U3).
- `def search_characters(connection: Connection, user_id: int, query_text: str, limit: int =
  MY_SEARCH_PER_KIND_LIMIT) -> list[CharacterHit]` — new; body `raise NotImplementedError`.
- `def search_setups(connection: Connection, user_id: int, query_text: str, limit: int =
  MY_SEARCH_PER_KIND_LIMIT) -> list[SetupHit]` — new; body `raise NotImplementedError`.
- `query_text` (not `query`) matches `search_memos` / `search_sessions` and the port's own
  parameter name. `limit` is positional-or-keyword with the cap as its default, so `limit=3`
  (DoD-8) and the three-argument call both work. `connection` first, `user_id` second; **no**
  keyword-only arguments on this step's functions — neither search opens a model, so there is no
  `client_factory` / `timeout_seconds` here (those appear on `run_my_search` in step `002`).

**Names deliberately left free for step `002`:** `SessionHit`, `EntryHit`, `MemoHit`,
`MySearchResults`, `run_my_search`, and the private hydration helpers (nothing named `_hydrate_*`,
`_now_text`, `_select_*` or `_scope_*` is taken). The only private name this step claims is
`_reading`.

Caller-compile edits (out of Source-files scope): None — the module is new and nothing imports it
yet.

Gates from `backend/`: `mypy app` — Success, no issues in 88 source files. `ruff check .` — All
checks passed. pytest deliberately not run (red gate's job).

### Step 002 — frozen interface (2026-10-05)

`backend/app/services/search/my_search.py` — **changed**, the only file touched. Everything step
`001` froze is byte-identical: the cap, `_reading`, `CharacterHit`, `SetupHit`, `search_characters`,
`search_setups` and the module docstring are untouched; step `002`'s surface is appended after
`search_setups`. The import block gained `Sequence` and the five names the new signatures need
(`F401` is on, so nothing a body alone would want is imported):

```python
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final

from sqlalchemy import Connection

from app.models.memos import MemoScope
from app.services.embedding import DEFAULT_EMBED_TIMEOUT_SECONDS
from app.services.llm.client import LlmClient
from app.services.llm_registry import LlmClientFactory
from app.services.search.ports import SearchHit
```

Still no `fastapi`, no `starlette`, no `sqlite_vec`, no `from __future__ import annotations`, no
`async`. The coder adds `select` / `and_` / `app.db.schema.sessions` / `characters` / `setups` /
`memos` / `settled_entries` and `app.services.search.hybrid.search` +
`ports.MemoSearchScope` / `SessionSearchScope` / `EntrySearchScope` himself — only the
unimplemented bodies need them.

- `@dataclass(frozen=True) class SessionHit` — new. Fields in order `id: int`,
  `character_name: str`, `setup_name: str | None`, `created_at: str`, `archived: bool`.
  `created_at` is **`str`**: `sessions.created_at` is stored `Text` in the fixed-width UTC form and
  every existing response model carries it as `str` (`SessionResponse.created_at: str`) — no
  `datetime`, no parsing in the service. `archived` is the **session's own** `archived_at` reduced to
  a bool (U3), never its character's or setup's.
- `@dataclass(frozen=True) class EntryHit` — new. Fields in order `id: int`, `session_id: int`,
  `snippet: str`, `character_name: str`, `session_created_at: str`. `id` is the **message** id;
  `session_created_at` is the **session's** `created_at` (same `str` form), not the message's own
  timestamp.
- `@dataclass(frozen=True) class MemoHit` — new. Fields in order `id: int`, `scope: MemoScope`,
  `scope_id: int | None`, `character_id: int | None`, `snippet: str`, `is_enabled: bool`. `scope` is
  `app.models.memos.MemoScope` (the existing four-literal alias the port's `SearchHit.memo_scope`
  already uses) — not a new literal, not `str`.
- `@dataclass(frozen=True) class MySearchResults` — new. Fields in order
  `characters: list[CharacterHit]`, `setups: list[SetupHit]`, `sessions: list[SessionHit]`,
  `entries: list[EntryHit]`, `memos: list[MemoHit]`. Field order **is** UC-059's group order
  (US-075.AC-1); `list[...]` (not `tuple`) so the hydration helpers' returns drop straight in and
  step `003`'s `model_validate(..., from_attributes=True)` sees sequences.
- `def _hydrate_sessions(connection: Connection, user_id: int, hits: Sequence[SearchHit]) ->
  list[SessionHit]` — new, private; body `raise NotImplementedError`.
- `def _hydrate_entries(connection: Connection, user_id: int, hits: Sequence[SearchHit]) ->
  list[EntryHit]` — new, private; body `raise NotImplementedError`.
- `def _hydrate_memos(connection: Connection, user_id: int, hits: Sequence[SearchHit]) ->
  list[MemoHit]` — new, private; body `raise NotImplementedError`.
- `def run_my_search(connection: Connection, user_id: int, query_text: str, *, client_factory:
  LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) ->
  MySearchResults` — new; body `raise NotImplementedError`. The two keyword-only defaults mirror the
  port's own source exactly as `search_memos` (026) and `search_sessions` (027) do, so a caller that
  passes neither gets the port's behaviour unchanged (024 D9). `query_text` again, not `query`.

**Naming and shape rationale.**

- `_hydrate_*` (one per kind, plural, matching the group it fills) — the vocabulary `context.md`
  defines for exactly this read ("hydration"), and step `001` explicitly left the prefix free. They
  are **private**: unlike 027's public `list_session_excerpts` they are not a seam anyone outside
  this module calls — step `003` consumes `MySearchResults` only.
- `(connection, user_id, hits)` — `connection` first and `user_id` second is the house order
  (`context.md` cross-cutting constraints); `hits` third is the step file's "the user id and the
  port's hits". Argument order is the only thing the step file left to decide here.
- **`Sequence[SearchHit]`, not `Sequence[int]`**, for all three. Entry and memo hits carry fields no
  owner-scoped read can recover — the port's `snippet`, and the memo's `memo_scope` /
  `memo_scope_id` — so the hit itself must travel into the helper that builds the value. The session
  helper needs only the ids, but takes hits too so that all three are called identically from
  `run_my_search` and "in the port's order, dropping ids the read misses" is **one** rule with one
  shape rather than three. `Sequence` (not `list`) because the helpers only iterate.
- Hit values stay flat dataclasses whose field order is the wire contract's, continuing step `001`'s
  choice: step `003` can `model_validate(hit, from_attributes=True)` field-for-field for all five
  kinds (`SessionHit` → `{"id", "character_name", "setup_name", "created_at", "archived"}`,
  `EntryHit` → `{"id", "session_id", "snippet", "character_name", "session_created_at"}`,
  `MemoHit` → `{"id", "scope", "scope_id", "character_id", "snippet", "is_enabled"}`), with
  `SnowflakeOut` doing the int→string on the way out.

**How the types carry orchestrator decision 5 (the user-level `scope_id`).** `MemoHit.scope_id` is
`int | None` and its docstring states that `None` **is** the `"user"` level, never a missing read:
the 025 port hands back `SearchHit.memo_scope_id` as the **raw stored** `memos.scope_id`, which for a
user-level note is the owner's own user id. **The body must `None`-ify it** — `None if
hit.memo_scope == "user" else hit.memo_scope_id`, the way `services/memos.py`'s `to_memo` (L72-76)
does — and must not pass the port's value through. Nothing in the type system will catch the miss
(both are `int | None`), which is why it is written into the field's docstring and here.

**Notes the coder must hold (all consequences of the freeze, none of them behaviour decided here).**

- `EntryHit.snippet` and `MemoHit.snippet` are `str`, while `SearchHit.snippet` is `str | None`.
  The port always sets a snippet for an entry and a memo hit, so the body narrows (`hit.snippet or
  ""`) and never propagates `None`. Likewise `MemoHit.scope` is `MemoScope` while
  `SearchHit.memo_scope` is `MemoScope | None`.
- `warn_return_any`: every value taken off a `Row[Any]` is narrowed before it lands in a field —
  `int(row.id)`, `str(row.name)`, `bool(row.is_enabled)`, `None if raw is None else str(raw)` — the
  shape `list_session_excerpts` already uses.
- DoD-12 is a source-text guard (`inspect.getsource`, the house form at
  `tests/test_memos_service.py:950`), so the **string** `is_forced` may not appear anywhere in this
  module — not in code, not in a comment, not in a docstring. The appended docstrings deliberately
  say "the forced flag" instead. Do not reintroduce the token when writing the memo hydration.

Caller-compile edits (out of Source-files scope): None — nothing imports this module yet (step `003`
is its first caller).

Gates from `backend/`: `mypy app` — Success, no issues in 88 source files. `ruff check .` — All
checks passed. pytest deliberately not run (red gate's job).

### Step 003 — frozen interface (2026-10-05)

Three files, exactly the step's Source files: `app/models/search.py` (**new**),
`app/routers/search.py` (**new**), `app/main.py` (**changed** — one import, one
`include_router`, two docstrings). Nothing in `services/search/my_search.py` was touched, and no
test file, `errors.py`, `dependencies.py` or other router was opened for writing.

**`backend/app/models/search.py`** — new. Imports exactly `from pydantic import BaseModel`,
`from app.models.ids import SnowflakeOut`, `from app.models.memos import MemoScope`; no
`ConfigDict`, no `app.services`, no `app.db`, no `fastapi`, no `from __future__ import
annotations`. Five leaf models plus the envelope; **every field below is the freeze** (DoD-3
asserts the exact key set per hit, so nothing may be added):

- `class CharacterHitResponse(BaseModel)` — new. `id: SnowflakeOut`, `name: str`,
  `archived: bool`.
- `class SetupHitResponse(BaseModel)` — new. `id: SnowflakeOut`, `name: str`,
  `character_id: SnowflakeOut`, `character_name: str`, `archived: bool`.
- `class SessionHitResponse(BaseModel)` — new. `id: SnowflakeOut`, `character_name: str`,
  `setup_name: str | None`, `created_at: str`, `archived: bool`.
- `class EntryHitResponse(BaseModel)` — new. `id: SnowflakeOut`, `session_id: SnowflakeOut`,
  `snippet: str`, `character_name: str`, `session_created_at: str`.
- `class MemoHitResponse(BaseModel)` — new. `id: SnowflakeOut`, `scope: MemoScope`,
  `scope_id: SnowflakeOut | None`, `character_id: SnowflakeOut | None`, `snippet: str`,
  `is_enabled: bool`.
- `class MySearchResponse(BaseModel)` — new. `characters: list[CharacterHitResponse]`,
  `setups: list[SetupHitResponse]`, `sessions: list[SessionHitResponse]`,
  `entries: list[EntryHitResponse]`, `memos: list[MemoHitResponse]` — **declaration order is the
  freeze** (DoD-2 reads the 200 body's top-level key order; verified: `model_dump()` yields
  `['characters', 'setups', 'sessions', 'entries', 'memos']`).

Naming: `<Kind>HitResponse`, one per frozen hit dataclass in `services/search/my_search.py`
(`CharacterHit` → `CharacterHitResponse`, …). Not the bare `CharacterResponse` / `SetupResponse`
/ `SessionResponse` / `MemoResponse`: all four names are already taken by the full-row models of
features 009 / 010 / 011 / 015, and a second, five-key `CharacterResponse` in a sibling module
would be a reader trap. `scope` reuses `app.models.memos.MemoScope`, the existing four-literal
alias the service's `MemoHit.scope` already carries — no new `Literal`, no `str`. Every id uses
the outbound alias, so each leaves as a decimal string (verified: `MemoHitResponse(id=2**61,
…).model_dump_json()` renders `"2305843009213693952"`), and the nullable ones are
`SnowflakeOut | None` (`MemoResponse.scope_id`'s spelling). No model declares `model_config`:
the dominant house form (20 sites) passes `from_attributes=True` at the call site instead, and
nothing here parses input.

**`backend/app/routers/search.py`** — new. Imports exactly `from typing import Annotated`,
`from fastapi import APIRouter, Depends`, `from sqlalchemy import Connection`, `from app.config
import Settings, get_settings`, `from app.db.engine import get_connection`, `from
app.dependencies import CurrentUser, get_llm_client_factory, require_user`, `from
app.models.search import MySearchResponse`, `from app.services.llm_registry import
LlmClientFactory`, `from app.services.search.my_search import MySearchResults`. The coder adds
`run_my_search` and the five `*HitResponse` names himself — only the unimplemented bodies need
them and `F401` is on.

- `router = APIRouter(tags=["search"], dependencies=[Depends(require_user)])` — new. No
  `prefix`; the handler spells its full literal path, the memos-router form.
- `def _to_response(results: MySearchResults) -> MySearchResponse` — new, **private**; body
  `raise NotImplementedError`. **This is the frozen conversion** (see below).
- the route, new; body `raise NotImplementedError`:

```python
@router.get("/api/search", status_code=200)
def my_search(
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
    client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)],
    q: str = "",
) -> MySearchResponse:
```

  A **sync `def`**, not `async` — 025's port embeds through 024's `asyncio.run` bridge, so the
  handler must run on a worker thread with no loop. `q` is a plain query parameter with **no
  `Query(...)` wrapper** (this router family uses none) and default `""`, so `/api/search`, `?q=`
  and `?q=%20%20` are all the blank query; verified in the OpenAPI schema as `{"name": "q", "in":
  "query", "required": false, "schema": {"type": "string", "default": ""}}`. Parameter order is
  `list_own_memos`'s: dependencies first, the defaulted query parameter last (Python requires it,
  and FastAPI reads it the same either way). `status_code=200` is explicit, as every handler in
  the backend states it. The return annotation **is** the response model; FastAPI infers
  `response_model` from it. The handler catches nothing — `no_embedding_model` 409,
  `llm_unreachable` 502 and `secret_ref_missing` propagate to the single `DomainError` handler
  (U1). The service call the coder fills in is `run_my_search(connection, current_user.id, q,
  client_factory=client_factory, timeout_seconds=settings.llm_request_timeout_seconds)`, the
  `create_own_memo` spelling (024 D9).

**The frozen conversion shape, and why.** A **private module function in the router**,
`_to_response(results: MySearchResults) -> MySearchResponse`, building the outer model **by
keyword** from five list comprehensions whose leaves go through
`<Kind>HitResponse.model_validate(hit, from_attributes=True)`.

- **Not a `classmethod from_*`** — there is none anywhere in `app/models/` (0 hits for `def
  from_` / `def to_response` / `.from_service` across `app/`), and orchestrator decision 4 says
  not to invent one without a reason. There is no reason: the hit dataclasses' field order and
  names are the wire contract's field-for-field, so `model_validate` needs no renaming and no
  computation.
- **In the router, not in `app/models/search.py`** — the step file left the file open ("a
  classmethod or a module function; the skeleton freezes which") and the router is the only
  placement consistent with `backend-structure.md` § Routers versus services: "Dependency
  direction is one-way: `routers → services → db` … `models/` is imported by both and imports
  neither." Typing the conversion on `MySearchResults` requires importing
  `app.services.search.my_search`, which a `models/` module may not do (every model module's
  docstring states the invariant; `tests/test_models_secret_ref.py:240` asserts it for its own
  module). The precedent is exact: `MemoChainResponse`'s grouped payload is assembled by
  `routers/memos.py`'s private `_to_level_response`, with `_to_response` doing the leaves — this
  is the same two functions collapsed into one, because my-search's outer model has no per-group
  wrapper object.
- Consequence for the coder: `_to_response` re-orders nothing, drops nothing and adds nothing.
  Group order comes from `MySearchResults`' field order, row order from each list.

**`backend/app/main.py`** — changed, three edits, no behaviour:

- Import `from app.routers.search import router as search_router`, placed **between** the `memos`
  and `sessions` router imports (ruff `I` sorts the `app.routers.*` block alphabetically; the
  import position is unrelated to the registration position).
- `app.include_router(search_router)` as the **last** `include_router` call, immediately after
  `app.include_router(translation_router)` — fourteen routers now. Orchestrator decision 6: last
  is deliberate, and it is why `test_configuration_router.py`'s `LATER_FEATURE_ROUTES` must gain
  `("/api/search", "GET")`.
- Both docstring passages that enumerate router order are amended. Module docstring item 5: the
  translation sentence now ends "registered after every earlier router", and a new clause adds
  "After it, last of all, comes `app.include_router(search_router)` (feature `029`), no prefix,
  the single full path `/api/search`, registered **after every other router** so every earlier
  router's routes keep matching first." `create_app`'s docstring gains
  `and app.include_router(search_router)` in the enumeration and now closes "the translation
  router after that (feature `023`), and the search router last (feature `029`)". No test reads
  any module docstring (0 hits for `__doc__` under `backend/tests/`), so these are review items —
  DoD-10.

**What the test-coder must know (consequences of the freeze, not behaviour).**

- **`app.routes` is not flat under the pinned FastAPI (0.141.1).** A top-level walk finds four
  Starlette routes and **fourteen `fastapi.routing._IncludedRouter` wrappers whose `.routes` is
  `None`** — zero `APIRoute`s. DoD-9 must therefore use the house walk
  (`test_configuration_router.py:1048-1063`'s `_ordered_api_routes`, which descends into
  `.routes`, `.router.routes` **and** `.original_router.routes`) or read
  `application.openapi()["paths"]`. Verified through that walk: exactly one `APIRoute` with
  `path == "/api/search"`, methods `{"GET"}`, name `my_search`, on the **last** included router
  (`tags == ["search"]`).
- The route's only declared response codes are 200 and 422; 401, 409 and 502 arrive from the
  dependency and the `DomainError` handler, undeclared, exactly as every other route.
- Overriding `get_llm_client_factory` is enough to intercept the factory; the route also depends
  on `get_settings`, so a test that overrides `get_settings` for its database already supplies
  the timeout.
- With the stubs in place the route answers **500** (`NotImplementedError`) once authenticated,
  and 401 unauthenticated — the router-level `require_user` is real, not stubbed, so DoD-1 is the
  one clause that can pass against the skeleton.

Caller-compile edits (out of Source-files scope): None — `app/main.py` is itself a Source file,
and nothing else imports either new module.

Gates from `backend/`: `mypy app` — Success, no issues in 90 source files. `ruff check .` — All
checks passed. App build probe (`import app.main` with the data dir, db filename and log path
pointed at a throwaway directory) — clean; `backend/data/rphelper.sqlite` untouched. pytest
deliberately not run (red gate's job).

### Step 004 — frozen interface (2026-10-05)

Two files, exactly the step's Source files, both **new**:
`frontend/src/app/searchApi.ts` and `frontend/src/app/searchState.ts`. Nothing else was opened
for writing — not `App.tsx`, `SearchScreen.tsx`, `CharacterTree.tsx`, the stream chain, anything
under `src/shared/`, any stylesheet or any test file.

**`frontend/src/app/searchApi.ts`** — new. Imports exactly
`import type { MemoScope } from "./memosApi";`. `apiGet` is deliberately **not** imported yet
(`noUnusedLocals` is on); the coder adds it with the body. Six exported types mirroring the wire
contract field for field — **every key, its type and the key order are the freeze**; nothing may
be added, renamed or re-ordered, and no renaming layer exists between the server's keys and
these:

- `export type CharacterHit = { id: string; name: string; archived: boolean }` — new.
- `export type SetupHit = { id: string; name: string; character_id: string; character_name: string; archived: boolean }` — new.
- `export type SessionHit = { id: string; character_name: string; setup_name: string | null; created_at: string; archived: boolean }` — new.
- `export type EntryHit = { id: string; session_id: string; snippet: string; character_name: string; session_created_at: string }` — new.
- `export type MemoHit = { id: string; scope: MemoScope; scope_id: string | null; character_id: string | null; snippet: string; is_enabled: boolean }` — new.
- `export type MySearchResults = { characters: CharacterHit[]; setups: SetupHit[]; sessions: SessionHit[]; entries: EntryHit[]; memos: MemoHit[] }` — new.
- `export async function fetchMySearch(query: string, signal?: AbortSignal): Promise<MySearchResults>` — new; unimplemented body.

Naming: `<Kind>Hit`, one per frozen backend hit model (`CharacterHitResponse` → `CharacterHit`,
…) — the bare `Character` / `Setup` / `Session` / `Memo` are already taken by the full-row wire
types of features 009 / 010 / 011 / 015 in `charactersApi.ts`, `setupsApi.ts`, `sessionsApi.ts`
and `memosApi.ts`, and a second five-key `Character` in a sibling module would be a reader trap.
`MySearchResults` is the step file's own name for the envelope (not `MySearchResponse`: it is the
page's results, and the frontend declares no `*Response` type for a payload it only reads).
`scope` reuses **`memosApi.ts`'s existing `MemoScope`** four-literal alias rather than declaring a
second identical union — the exact parallel to step `003` reusing `app.models.memos.MemoScope`.
Every id is `string`; the two nullable ids are `string | null`, the memos module's spelling.
`fetchMySearch` takes the **query text** (not a prebuilt path) and the optional signal, in
`sessionsApi.ts`'s parameter order; errors are the shared client's, rethrown unchanged (U1), and
an abort rejects as the raw `AbortError` (`shared/api.ts`'s `mapFetchRejection` returns it
unwrapped). The coder owns the path spelling and the `apiGet<MySearchResults | undefined>` /
empty-body fallback — `apiGet` returns `undefined as T` for an empty body, so a total body read
needs one, exactly as `fetchSessions`' `?? []`.

**`frontend/src/app/searchState.ts`** — new. Imports exactly
`import { makeAutoObservable } from "mobx";` and
`import type { CharacterHit, EntryHit, MemoHit, MySearchResults, SessionHit, SetupHit } from "./searchApi";`.
`runInAction`, `fetchMySearch`, `isApiError` and the module-private `isAbortRejection` helper are
deliberately **absent** (`noUnusedLocals`, and an unused local function, would fail the gate); the
coder adds all four with the bodies, copying `charactersState.ts`'s
`function isAbortRejection(error: unknown): boolean { return error instanceof Error && error.name === "AbortError"; }`
verbatim — nothing in `src/shared/` exports an equivalent.

- `export type SearchLoadStatus = "idle" | "loading" | "ready" | "failed"` — new; the
  `CharactersLoadStatus` naming, four values, no others.
- `export class SearchState` — new. **Four observable fields, their declared types and their
  initial values are the freeze**; no methods, no computed getters, no constructor parameter:
  - `status: SearchLoadStatus = "idle"`
  - `query = ""` (inferred `string`) — the query the current `results` / `failure` belong to
  - `results: MySearchResults | null = null`
  - `failure: string | null = null`
  - `constructor()` → `makeAutoObservable(this, {}, { autoBind: true });` — **implemented for
    real, deliberately**: it is the data contract itself (and `strictPropertyInitialization` is
    satisfied by the initialisers, so it takes no argument), not behaviour. A constructor that
    threw would make the class unusable by every test and by step `005`.
- `export function isBlankQuery(text: string): boolean` — new; unimplemented body.
- `export async function loadSearch(state: SearchState, query: string, signal?: AbortSignal): Promise<void>` — new; unimplemented body. `(state, …, signal?)` is `loadCharacters`' parameter order.
- `export function hasNoHits(state: SearchState): boolean` — new; unimplemented body. Takes the
  **state**, not the results: "ready **and** five empty groups" is unanswerable from
  `MySearchResults` alone, and `"idle"` / `"failed"` must answer false.
- `export function searchHref(text: string): string` — new; unimplemented body.
- `export function characterTarget(hit: CharacterHit): string` — new; unimplemented body.
- `export function setupTarget(hit: SetupHit): string` — new; unimplemented body.
- `export function sessionTarget(hit: SessionHit): string` — new; unimplemented body.
- `export function entryTarget(hit: EntryHit): string` — new; unimplemented body.
- `export function memoTarget(hit: MemoHit): string` — new; unimplemented body.

**The target helpers: five functions, one per hit kind, the memo case one function branching on
`scope` four ways.** The step file left the shape open; this is the freeze and the reason.
*Five, not one dispatcher:* the wire rows carry **no `kind` discriminator** (the grouping is the
envelope's five keys), so a single `hitTarget(hit)` would need either an invented tag parameter or
a union of four structurally overlapping object types. Step `005` renders one `map` per group, so
the kind is **statically known at every call site**; five one-line functions give each call site
an exactly-typed argument and let TypeScript catch a group/helper mismatch, which a `kind` string
could not. *The memo case is one function, not four:* step `005` renders the notes group as a
single `map` over `results.memos` whose rows differ only in their level label, so branching
outside the helper would push the four-way `scope` switch into JSX; `scope`, `scope_id` and
`character_id` all live on the one row, so the switch has everything it needs. `*Target` is the
plan's own vocabulary word ("target — the in-entry path a hit's row links to"), which also keeps
it distinct from `searchHref`, the one path leading *to* the results page.

**Frozen rule inside `memoTarget` (so the coder has no choice to make).** `"user"` → `/settings`;
`"character"` and `"setup"` → `/characters/<character_id>`; `"session"` →
`/sessions/<scope_id>?notes=open`. The wire contract guarantees the id each branch reads is
non-null, but the type is `string | null`, so the null has to be written somewhere: it is
substituted with the **empty string**, which lands on `App.tsx`'s `*` catch-all ("Page not
found") — never on another user's page and never a thrown render. `noFallthroughCasesInSwitch` is
on, so a `switch` needs a `return` per case.

**What the test-coder and the `005` / `006` skeletons must know.**

- The names above are the binding surface: `005` consumes `SearchState`, `loadSearch`,
  `hasNoHits`, `searchHref` and all five `*Target` helpers plus the six types; `006` consumes
  `searchHref` only.
- Both modules are **import-safe**: nothing runs at module load, and `new SearchState()` is real,
  so a test may construct the state and assert its four initial values (`"idle"`, `""`, `null`,
  `null`) against the skeleton. Every other exported function throws
  `Error("not implemented")` — `loadSearch` is `async`, so it **rejects**; the "never rejects"
  clauses (DoD-3..5) go red as a rejection, which is the right red.
- Unimplemented bodies use the house form: `void <param>;` lines then
  `throw new Error("not implemented")` (`noUnusedParameters` is on). The coder replaces each whole
  body including the `void` lines.
- `fetchMySearch` is a **free function taking text**, so `searchApi.test.ts` reads the request URL
  off the `fetch` stub (`new URL(input, "http://localhost")`) — there is no exported path helper
  to assert against, and `/api/search` appears in no exported constant.
- Nothing here imports `@mantine/notifications`, `shared/notifyFailure`, `shared/notifyWarning`,
  any router hook or any stylesheet; no `.css` file was created and `shell.css` is untouched. No
  id is typed `number` and `parseInt` appears nowhere, so `tests/ids-are-strings.test.ts`,
  `tests/conventions.test.ts` and `tests/stylesheets.test.ts` all stay green.

Caller-compile edits (out of Source-files scope): None — both modules are new and nothing imports
either yet (`005` and `006` are their first callers).

Gate from `frontend/`: `npm run typecheck` — exit 0 (both `tsconfig.json` and
`tsconfig.node.json`). `npm test` and the build deliberately not run (the red gate's job).

### Step 005 — frozen interface (2026-10-05)

Two files, exactly the step's Source files: `frontend/src/app/SearchScreen.tsx` (**new**) and
`frontend/src/app/App.tsx` (**changed** — one import, one route element, one docstring clause).
Nothing else was opened for writing — not `searchApi.ts` / `searchState.ts` (step `004`'s freeze is
byte-identical), not `CharacterTree.tsx` or the stream chain (`006`), not `WorkspaceShell.tsx`
(deliberately unchanged, D9), no stylesheet and no test file.

**`frontend/src/app/SearchScreen.tsx`** — new. Imports exactly `import type * as React from
"react";`, `import { useState } from "react";`, `import { observer } from "mobx-react-lite";`,
`import type { MemoScope } from "./memosApi";`, `import { SearchState } from "./searchState";`.
Everything the real body needs and the stub does not — `useEffect` / `useRef`, `useLocation` /
`useNavigate` / `useSearchParams` / `Link`, every `@mantine/core` component, `formatSessionStart`,
`loadSearch` / `hasNoHits` / `isBlankQuery` / `searchHref` / the five `*Target` helpers and the six
hit types — is deliberately **absent** (`noUnusedLocals` is on); the coder adds them with the body.
Nothing imports `@mantine/notifications`, `shared/notifyFailure` or any `.css`, and no `.css` file
was created (`tests/stylesheets.test.ts`, `tests/conventions.test.ts` stay green). No `number` id,
no `parseInt` (`tests/ids-are-strings.test.ts` stays green).

- **One exported symbol, and only one:**
  `export const SearchScreen = observer(function SearchScreen(): React.JSX.Element { … })` — new.
  **No props at all** (no `SearchScreenProps` type exists), because the page owns its store:
  `const [state] = useState(() => new SearchState());` is in the stub **for real** — orchestrator
  decision 10, the one structural fact the coder may not revisit (per mount, never a prop, never a
  context, never a module singleton, so each arrival starts `"idle"`). `observer`, not a plain
  component: it reads `state.status` / `results` / `failure`. The `observer(function Name(){})` form
  and the `React.JSX.Element` return are `SettingsScreen`'s, the nearest sibling screen.
- **The stub body implements nothing else.** It returns `<></>` — an empty fragment, rendering no
  text, no box, no region and no element. There is no URL read, no effect, no group, no marking.
  Consequence for the red gate: at `/search` the centre is **empty**, so every one of DoD-1..11 goes
  red on a missing element rather than on a wrong value, and nothing the stub renders can
  accidentally satisfy an assertion. It does **not** throw: a throwing component would break
  delivered `App.test.tsx` suites that render `/search` (`NO_SESSION_ROUTES`), which this step does
  not own.

**The eleven module constants are part of the freeze** — their names, their exact string values and
`GROUP_HEADINGS`' key order. All eleven are **private** (not exported): the tests bind to roles,
accessible names and these literals through the rendered DOM, never to the module's internals.

| Constant | Exact value |
|---|---|
| `QUERY_PARAM` | `"q"` |
| `SEARCH_BOX_LABEL` | `"Search query"` |
| `GROUP_HEADINGS` | `{ characters: "Characters", setups: "Setups", sessions: "Sessions", entries: "Entries", memos: "Notes" } as const` |
| `MEMO_LEVEL_LABELS` | `Record<MemoScope, string>` = `{ user: "User note", character: "Character note", setup: "Setup note", session: "Session note" }` |
| `ARCHIVED_BADGE` | `"Archived"` |
| `DISABLED_BADGE` | `"Disabled"` |
| `SECONDARY_SEPARATOR` | `" · "` (U+00B7 between two spaces) |
| `LOADING_TEXT` | `"Searching…"` (U+2026, one character) |
| `NO_HITS_TEXT` | `"Nothing found."` |
| `FAILURE_HEADING` | `"Search failed"` |
| `RETRY_LABEL` | `"Retry"` |

- `GROUP_HEADINGS` is **one object keyed by the five `MySearchResults` keys**, not five separate
  constants and not a tuple: declaration order *is* UC-059's render order (US-075.AC-1), each value
  is simultaneously its heading text and its region's accessible name, and the keying makes the one
  non-obvious mapping — `memos` → `Notes` — impossible to mis-pair at a call site. `as const` so
  each value is its literal type.
- `MEMO_LEVEL_LABELS` is a `Record<MemoScope, string>` over `memosApi.ts`'s existing four-literal
  alias (the same alias `MemoHit.scope` carries), so a missing or misspelled level is a typecheck
  error rather than a runtime `undefined`.
- `SECONDARY_SEPARATOR` is frozen although `context.md`'s literals table does not name it: DoD-5
  asserts `"<character> · <setup>"` exactly, it is used by both the session and the entry row, and
  the character is easy to typo as a hyphen or a bullet.
- **How `noUnusedLocals` stays satisfied without exporting anything:** the stub body ends with one
  `void <NAME>;` line per constant (plus `void state;`), step `004`'s house form, immediately above
  the `return <></>;`. The coder replaces that whole block **and** the return together — the `void`
  lines are scaffolding, not code to keep, and every constant must end up genuinely used.

**The frozen decomposition (what the coder may and may not do inside the module).** The five groups
are rendered by **one private group wrapper used five times** — the region (`<Box
component="section" aria-label={heading}>` + the visible heading + the list) is identical for all
five, while the row content, the hit type and the `*Target` helper differ per kind, so each group's
rows stay **inline at its own call site** (one `.map` per group, each with a statically known hit
type). That wrapper, and any row helper the coder wants beside it, are **module-private and never
exported**; `SearchScreen` stays the module's only export. The `<Box component="section"
aria-label={…}>` idiom is `LiveMessage.tsx:27`'s and is what gives the region role its accessible
name.

**What the test-coder must know (consequences of the freeze, not behaviour).**

- Bind to `import { SearchScreen } from "../../src/app/SearchScreen";` and render
  `<SearchScreen />` with **no props**, inside `<AppProviders>` then `<MemoryRouter>` (that nesting
  order, universally). It needs a router: the real body calls `useLocation` / `useSearchParams` /
  `useNavigate`.
- Against the skeleton the centre is **empty** — not an error boundary, not a thrown render. A test
  that only asserts "no region" or "no `Nothing found.`" would **pass** against the stub; the red
  for DoD-2, DoD-7 and DoD-9 must therefore also assert the positive half (the box exists, the
  envelope's message appears), as those clauses already require.
- `new SearchState()` is real (step `004`), so mounting the stub performs no fetch and writes
  nothing: `fetch` is never called for `/api/search` by the skeleton at all, for any `q`.
- The group headings double as the region names, so `getAllByRole("region")` in document order maps
  one-to-one onto `Characters`, `Setups`, `Sessions`, `Entries`, `Notes`.
- No notification host is ever touched by this module, so DoD-9's "no notification appears" is an
  absence assertion over the rendered tree, as `005.context.md` says.

**`frontend/src/app/App.tsx`** — changed; three edits, no behaviour, nothing else in the route table
touched:

- `import { SearchScreen } from "./SearchScreen";` placed between the `SettingsScreen` and
  `charactersState` imports (the file's existing component-then-state grouping).
- `<Route path="/search" element={null} />` → `<Route path="/search" element={<SearchScreen />} />`,
  in place, at the same position between `/settings` and the `*` catch-all. **`App` passes it
  nothing** — deliberately unlike `CharacterScreen` / `SessionRoute`, which receive the workspace
  states as props; `App` creates no third `useState` and `AppProps` is unchanged.
- The `App` docstring's "Later features (013, 017, 018, 029) fill the remaining centres" clause
  drops `029` and gains "and 029 step 005 fills `/search` with `SearchScreen` — which, unlike the
  other screens, receives no props at all: it owns the one page state it needs (029 decision 10)",
  so the comment no longer claims `/search`'s element is empty on purpose. No frontend test reads a
  docstring; this is a review item.

Caller-compile edits (out of Source-files scope): None — `App.tsx` is itself a Source file, and
nothing else imports `SearchScreen` (`006` does not touch it).

Gate from `frontend/`: `npm run typecheck` — exit 0 (both `tsconfig.json` and
`tsconfig.node.json`). `npm test` and the build deliberately not run (the red gate's job).

### Step 006 — frozen interface (2026-10-05)

Four files, exactly the step's Source files, **all four changed, none new**:
`frontend/src/app/CharacterTree.tsx`, `SessionScreen.tsx`, `SessionStream.tsx`,
`StreamRecord.tsx`. Nothing else was opened for writing — not `searchState.ts` / `searchApi.ts` /
`SearchScreen.tsx` / `App.tsx` (steps `004` / `005` are byte-identical), not `WorkspaceShell.tsx`
(D9), not `noteWallState.ts`, not `shared/IconButton.tsx`, no stylesheet and no test file.
`searchHref` is the **only** `004` symbol this step consumes, and the stub does not import it yet
(`noUnusedLocals`): the coder adds `import { searchHref } from "./searchState";` with the handler
body.

**The line this freeze draws, since all four files already render today.** *Declarations are
real:* the props types, the private constants, the `data-entry-id` attribute, the search box
itself and the prop plumbing down the chain. *Behaviour is not implemented anywhere:* no URL is
read, no effect is added, no timer exists, nothing scrolls, nothing is highlighted, and the Enter
key throws. Apart from the box replacing the button and the new attribute, **every one of the four
components renders exactly what it rendered before**, so the delivered tests this step does not
amend keep passing.

**`frontend/src/app/CharacterTree.tsx`** — changed. Import edits: `TextInput` added to the
`@mantine/core` list (which becomes multi-line) and **`IconSearch` removed** from the
`@tabler/icons-react` import, because a stale import is a `noUnusedLocals` gate failure
(orchestrator decision 12). `IconButton`, `IconPlus`, `IconChevronDown`, `useNavigate` and every
other import stay.

- `const SEARCH_LABEL = "Search"` — **new**, private; **the exact string is part of the freeze**
  (`context.md` literals, "tree input accessible name"). It is the box's `aria-label` and the box's
  **only** labelling: deliberately **not** a visible Mantine `label`, which would add a new text
  node "Search" inside the nav column that a delivered text query could pick up.
- `const SEARCH_PATH = "/search"` — **removed**. Nothing else used it, and `searchHref("")` already
  returns `/search`, so keeping it would both duplicate `004`'s rule and fail `noUnusedLocals`.
  `NEW_CHARACTER_PATH` is untouched; its doc comment now reads "the header's in-entry destination"
  (singular).
- `const [searchText, setSearchText] = useState("")` — **new**, component-local, **implemented for
  real**: it is the "value component-local" half of the contract, and the tree remounts on expand,
  so it is deliberately never seeded from or synced with the URL (U4).
- The header's `Search` `IconButton` is **replaced** by the frozen element:
  `<TextInput size="xs" flex={1} miw={0} aria-label={SEARCH_LABEL} value={searchText}
  onChange={… setSearchText(event.currentTarget.value) …} onKeyDown={…} />`, first child of the same
  `<Group gap="xs" wrap="nowrap">`. `flex={1} miw={0}` is the file's own row idiom (`NavLink`,
  L251-252). **`onChange` is real; `onKeyDown` is the stub**: a non-Enter key returns, and Enter
  `throw new Error("not implemented")` — the loudest available red, reachable by no delivered test
  (the tree has no textbox today). The coder replaces that one `throw` with the in-entry push
  `void navigate(searchHref(searchText));` and keeps the `event.key` guard.
- The `New character` `IconButton` and the `Show archived` `Switch` are **unchanged** — same order,
  same props, same handlers. The component docstring's header sentence now names the "Search" box,
  the "New character" button and the "Show archived" switch.
- `CharacterTreeProps` is **unchanged** (`characters`, `sessions`, `storage`), so nothing that
  renders the tree needs an edit.

**`frontend/src/app/SessionScreen.tsx`** — changed. **`SessionScreenProps` and `SessionRouteProps`
are unchanged**, and so is every render branch: `searchLanding.test.tsx` renders
`<SessionScreen sessionId=… characters=… storage=… />` exactly as `SessionScreen.test.tsx` does.
Three private constants are the whole of the freeze here:

- `const ENTRY_PARAM = "entry"`, `const NOTES_PARAM = "notes"`, `const NOTES_OPEN_VALUE = "open"` —
  **new**; **the three strings are part of the freeze** (D8, `context.md` literals
  `entry=<message id>` and `notes=open`).
- **Not implemented, and the coder's whole job in this file:** `useSearchParams` is **not** imported
  and **not** called (the router import is still `{ Link, useParams }`); no `focusEntryId` is passed
  to `SessionStream`; there is no wall effect. A comment block in the component body, immediately
  after `controllerRef`, states what to add and `void`s the three constants to satisfy
  `noUnusedLocals`; the coder replaces that whole block. The comment pins decision 11 in source: the
  branch may only ever **open** the wall (`openWall(wall)`, already imported) when `NOTES_PARAM` is
  exactly `NOTES_OPEN_VALUE`, and absence, any other value, or a later in-entry navigation must
  leave the wall untouched — never close, never unpin.
- This screen is the **only** place in the chain that may read the URL (decision 9). It already has
  a router, and every delivered test that renders it wraps it in a `MemoryRouter`.

**`frontend/src/app/SessionStream.tsx`** — changed; one prop and one forwarding line, nothing else.

- `SessionStreamProps` gains exactly one member: **`focusEntryId?: string | null`** — optional, and
  read at the point of use as `props.focusEntryId ?? null`, the file's own `sendBlockedReason`
  idiom. The `string | null` spelling (not a bare `string`) is deliberate: the value's origin is
  `URLSearchParams.get()`, which answers `string | null`, so `SessionScreen` can hand the read
  straight down with no massaging, and it matches the sibling optional prop on the same type.
  `sessionId` and `sendBlockedReason` are unchanged, so the seven delivered files that render
  `<SessionStream sessionId={…} />` still compile and still behave identically.
- The forwarding is **real** (plumbing, not behaviour, and nothing feeds it yet):
  `<StreamRecord state={state} signal={signal} translations={translations}
  focusEntryId={props.focusEntryId ?? null} />`.
- **No router hook, no `Link`, no `useSearchParams`, no `useLocation`** — decision 9. Verified by
  grep: `react-router-dom` appears nowhere in this module.

**`frontend/src/app/StreamRecord.tsx`** — changed; the props, two literals, the attribute and the
third ref are real, the anchor's behaviour is not.

- `StreamRecordProps` gains exactly one member: **`focusEntryId?: string | null`** — same spelling
  and same reason as `SessionStream`'s, forwarded by it. `state`, `signal` and `translations` are
  unchanged, so every delivered `<StreamRecord state={…} />` / `… signal={…}` / `… translations={…}`
  render still compiles.
- `StreamEntryProps` (module-private, not exported) gains exactly one member:
  **`isFocusEntry: boolean`** — **required**, like its sibling `isLast`, because `StreamRecord` is
  its only constructor. `StreamRecord` resolves the id once
  (`const focusEntryId = props.focusEntryId ?? null;`) and passes
  `isFocusEntry={entry.id === focusEntryId}` — string equality, never parsed, so a `null` and an id
  naming no loaded entry both simply match nothing. True on at most one item of a record.
- `const HIGHLIGHT_DURATION_MS = 2000` — **new**, private; **the value `2000` is part of the
  freeze** (`context.md` literals; DoD-4 pins 1999 / 2000).
- `const HIGHLIGHT_BG = "yellow.1"` — **new**, private. **This is the skeleton's choice of how the
  highlight is expressed, there being no in-repo precedent (decision 12):** the Mantine **`bg`
  prop** on the item (decision 10 already names `bg`), shade `yellow.1`, applied only while
  highlighted — never a class name, never a stylesheet, never an inline `style`. What the tests bind
  to is `data-highlighted="true"`; the shade is free for the coder to re-tune **as long as it stays
  a Mantine `bg` value**, and `tests/stylesheets.test.ts` forbids any other route.
- `StreamEntry`'s `<li>` is now
  **`<Box component="li" ref={itemRef} data-entry-id={entry.id} mb="md">`** — the attribute is
  **real, on every item, always**, spelled `data-entry-id` (never `data-entry`, the Vite entry
  marker four other suites enumerate exactly). `ref`, `mb`, the key and the entire content are
  unchanged.
- `const scrollRef = useRef<HTMLLIElement>(null)` — **new**, and it **joins** the existing
  composition: `useMergedRef<HTMLLIElement>(hoverRef, focusRef, scrollRef)`. `useHover`'s and
  `useFocusWithin`'s refs are both preserved in place; `itemRef` is still the item's single `ref`.
  `useRef` is added to the `react` import.
- **Not implemented:** `data-highlighted`, the `bg` prop, any `useEffect`, any timer and any
  `scrollIntoView` call. A comment block after the reveal reads states the contract (scroll
  `scrollRef.current` into view **centred, once**, when `isFocusEntry` turns true; hold
  `data-highlighted="true"` + `bg={HIGHLIGHT_BG}` for `HIGHLIGHT_DURATION_MS`, then drop both and
  never scroll again) and `void`s `isFocusEntry`, `HIGHLIGHT_DURATION_MS` and `HIGHLIGHT_BG` for
  `noUnusedLocals`. The coder replaces that block.

**What the test-coder must know (consequences of the freeze, not behaviour).**

- Bind the landing tests to `SessionScreen` with its **unchanged** three props, inside
  `<AppProviders>` then `<MemoryRouter initialEntries={[…]}>`; `focusEntryId` and `isFocusEntry` are
  plumbing a test never passes itself — the URL is the only way in.
- Against the skeleton: the tree **has** a textbox named `Search` whose typing works, so DoD-1's red
  is the navigation half (Enter raises `not implemented`, the probe's path never changes); every
  entry **already** carries `data-entry-id`, so DoD-3's red is the missing `scrollIntoView` call and
  the missing `data-highlighted`; DoD-4 and DoD-6 are red on absence. **DoD-2 and DoD-5 are green
  against the skeleton by construction** — DoD-2 is the amended button / textbox census (the box is
  real) and DoD-5 is a pure absence clause ("an unknown `entry` does nothing"), which no do-nothing
  stub can fail. That is inherent to those two clauses, not a stub leaking behaviour; the red gate
  should expect it.
- `data-entry-id` is a plain DOM attribute on the `<li>`, so `item.getAttribute("data-entry-id")`
  and `container.querySelector('[data-entry-id="…"]')` both work, and the values are the message ids
  verbatim as strings.
- No module here imports `@mantine/notifications`, `shared/notifyFailure`, any `.css` or (in the two
  stream modules) any router hook; no `.css` file was created and `shell.css` is untouched; no id is
  typed `number` and `parseInt` appears nowhere — `tests/conventions.test.ts`,
  `tests/stylesheets.test.ts` and `tests/ids-are-strings.test.ts` all stay green (re-checked by grep
  against all three rule sets).
- The `CharacterTree.test.tsx` amendment sites are the orchestrator's decision 8's **four** (L594,
  L744-753, **L798**, **L763**), not the plan's two; the skeleton's box is what makes L763's "no
  textbox in the tree" assertion false.

Caller-compile edits (out of Source-files scope): **None.** All three new public props are optional
with a default that preserves today's behaviour, `CharacterTreeProps` / `SessionScreenProps` /
`SessionRouteProps` are unchanged, and `StreamEntryProps`' required `isFocusEntry` is module-private
with `StreamRecord` as its only call site — so no file outside the step's Source files needed an edit
to keep compiling.

Gate from `frontend/`: `npm run typecheck` — exit 0 (both `tsconfig.json` and `tsconfig.node.json`).
`npm test` and the build deliberately not run (the red gate's job).

## Tests

### Step 001 — tests (2026-10-05)

- `backend/tests/test_my_search_like.py` — **new**, 19 test functions / 24 collected cases, covers
  DoD-1..10:
  - DoD-1 — `test_the_per_kind_cap_constant_is_twenty` — the cap constant equals the spec's `20`.
  - DoD-2 — `test_characters_match_on_name_and_on_persona_in_name_order` — the whole expected
    `CharacterHit` list, matched on `name` and on `sheet`, case folded, in name order.
  - DoD-3 — `test_setups_match_on_name_and_on_description_in_name_order` — the whole expected
    `SetupHit` list, one row matched in its name and one in its description in another case.
  - DoD-4 — `test_another_users_identical_character_never_appears`,
    `test_another_users_identical_setup_never_appears` — B's twins carry the same names and texts
    as A's; absent from A's results, present in B's own.
  - DoD-5 — `test_an_archived_character_is_returned_and_flagged`,
    `test_an_archived_setup_is_flagged_and_its_characters_archive_is_not` — `archived` is the
    row's own `archived_at`; a live setup under an archived character is `archived` false.
  - DoD-6 — `test_a_wildcard_in_the_query_matches_only_itself` (parametrized `%`, `_`, `100%`,
    `a_b`), `test_a_backslash_in_a_name_is_an_ordinary_character` (decision 3: the declared escape
    character is `/`, so a backslash is literal), `test_a_wildcard_in_the_query_is_literal_for_setups_too`.
  - DoD-7 — `test_a_blank_query_returns_nothing_for_either_kind` (parametrized `""`, `"   "`,
    `"\n\t"`), `test_surrounding_whitespace_is_stripped_from_the_needle`,
    `test_a_two_word_query_is_one_substring_and_is_not_split`.
  - DoD-8 — `test_the_default_limit_is_the_cap_and_keeps_the_first_rows_in_name_order`,
    `test_an_explicit_smaller_limit_keeps_the_first_three_in_name_order` — 25 matching rows, 20 by
    default, 3 with `limit=3`.
  - DoD-9 — `test_a_search_that_hits_leaves_no_transaction_in_progress`,
    `test_a_blank_search_leaves_no_transaction_in_progress`,
    `test_a_search_made_mid_read_opens_no_transaction_of_its_own`.
  - DoD-10 — `test_the_my_search_module_imports_no_web_framework` — imports/AST, not source text.
- `backend/tests/test_search_hybrid.py` — **amended** (orchestrator decision 1, approved mechanical
  knock-on): `"my_search.py"` appended to `SEARCH_PACKAGE_MODULES`, its `#:` comment extended, and
  `test_the_eight_search_modules_are_all_present_to_scan__S025_004_DoD15` renamed to
  `test_the_nine_search_modules_are_all_present_to_scan__S025_004_DoD15` with its docstring and the
  trailing step comment updated. The `__S025_004_DoD15` tag is kept; the two sibling scans are
  untouched, so `my_search.py` now inherits "no `fastapi`/`starlette`" and "no `sqlite_vec`".
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓
  (see the spec concern below on its mid-read clause), DoD-10 ✓.

### Step 002 — tests (2026-10-05)

- `backend/tests/test_my_search_service.py` — **new**, 23 test functions / 26 collected cases,
  covers DoD-1..12:
  - DoD-1 — `test_one_query_returns_a_hit_in_each_of_the_five_groups`.
  - DoD-2 — `test_the_result_exposes_the_five_groups_in_uc059_order` (`MySearchResults`' field
    order), `test_each_group_holds_only_its_own_kinds_ids`.
  - DoD-3 — `test_all_four_flag_combinations_are_returned_with_their_stored_state` — enabled+forced,
    enabled+plain, disabled+forced, disabled+plain all returned, `is_enabled` as stored.
  - DoD-4 — `test_a_memo_hit_names_its_level_and_the_page_it_routes_to`,
    `test_the_user_levels_none_scope_id_is_not_a_missing_row` (the stored `scope_id` **is** the
    owner's id and the hit still carries `None` — decision 5), `test_a_memo_hit_carries_no_title`.
  - DoD-5 — `test_a_session_hit_carries_its_character_setup_start_and_archive_state` — three whole
    `SessionHit` values (with setup, setup-less, archived), `created_at` as the seeded text.
  - DoD-6 — `test_a_settled_entry_is_returned_with_its_session_and_character`,
    `test_a_zone_row_and_a_buried_row_are_outside_the_entry_corpus` (both excluded rows carry the
    token), `test_an_entry_hit_carries_the_frozen_five_fields`.
  - DoD-7 — `test_no_row_of_another_user_appears_in_any_group` (B's session has the **same** vector,
    B's note the same body and vector), `test_the_other_user_finds_only_their_own_rows`.
  - DoD-8 — `test_the_memo_group_is_capped_and_led_by_the_zero_distance_note` (25 notes, no body
    holds the token so the lexical arm ranks nothing; the sole zero-distance vector leads),
    `test_the_memo_group_is_in_the_ports_own_order` (expected order = 025's answer to the exact port
    call step 002's Interface intent specifies), `test_the_character_group_is_capped_too`.
  - DoD-9 — `test_a_blank_query_returns_five_empty_groups_and_opens_no_model` (parametrized `""`,
    `"   "`; `factory.call_count == 0` and `factory.embed_calls == []`).
  - DoD-10 — `test_no_designated_model_fails_the_whole_search`,
    `test_a_dimension_mismatch_fails_the_whole_search` (detail exactly
    `{"reason": "dimension_mismatch"}`), `test_an_unreachable_provider_fails_the_whole_search` — the
    vector tables are created **first** in every case.
  - DoD-11 — `test_a_successful_search_leaves_no_transaction_in_progress`,
    `test_a_blank_search_leaves_no_transaction_in_progress`,
    `test_a_failing_search_leaves_no_transaction_in_progress` (parametrized over DoD-10's three).
  - DoD-12 — `test_the_my_search_module_still_imports_no_web_framework` (imports/AST),
    `test_the_my_search_module_never_names_the_forced_flag` (`inspect.getsource` + `not in`).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓, DoD-12 ✓.

### Step 003 — tests (2026-10-05)

- `backend/tests/test_search_router.py` — **new**, 15 test functions / 19 collected cases, covers
  DoD-1..9. Nothing in it imports `app.models.search` or `app.routers.search`: the binding is the
  frozen route (`GET /api/search`, optional `q` defaulting to `""`, behind `require_user`) and every
  expected value is the **wire contract**, read off a body parsed with `json.loads`.
  - DoD-1 — `test_the_route_answers_401_without_a_session_cookie__S029_003_DoD1` (parametrized
    `?q=x` and the bare path) — 401, envelope exactly `{"error": {"code", "message", "detail"}}`,
    code `not_authenticated`, and no group key in the body.
  - DoD-2 — `test_the_five_groups_arrive_in_uc059_order__S029_003_DoD2` (the parsed body's
    top-level key order **is** `characters, setups, sessions, entries, memos`, and all five are
    non-empty), `test_each_group_holds_exactly_the_seeded_rows__S029_003_DoD2` (every row compared
    whole against the contract's fields, snippet aside — which is asserted to hold the token),
    `test_every_id_on_the_wire_is_the_decimal_string_of_its_snowflake__S029_003_DoD2` (`id`,
    `character_id`, `session_id`, `scope_id` are JSON **strings**, decimal, above 2^60, and each one
    a seeded id).
  - DoD-3 — `test_each_hit_carries_exactly_its_contract_keys__S029_003_DoD3` (the exact key set per
    kind, no extra key), `test_no_hit_carries_a_title_a_body_or_the_forced_flag__S029_003_DoD3`.
  - DoD-4 — `test_a_disabled_note_is_returned_beside_an_enabled_one__S029_003_DoD4`,
    `test_a_user_level_note_reports_a_null_scope_id__S029_003_DoD4` (the stored `scope_id` is the
    owner's own id; the wire shows `null`, and the owner's id appears nowhere in the row).
  - DoD-5 — `test_signed_in_as_a_no_id_of_bs_appears_anywhere__S029_003_DoD5`,
    `test_signed_in_as_b_no_id_of_as_appears_anywhere__S029_003_DoD5` — B's character, setup,
    session, settled entry and note are twins of A's (same names, texts, bodies and the **same**
    vectors), so both absences are the owner predicate's work. Every decimal-string leaf of the
    whole body is collected, whatever the nesting; each test also asserts the signed-in user's own
    rows **are** there, so neither absence can pass vacuously.
  - DoD-6 — `test_an_archived_character_setup_and_session_are_flagged_on_the_wire__S029_003_DoD6`
    (`archived` true for the archived row of each archivable kind, false for the live one beside it).
  - DoD-7 — `test_a_blank_query_answers_five_empty_groups_and_opens_no_model__S029_003_DoD7`,
    parametrized over `/api/search`, `?q=` and `?q=%20%20`: 200, the five keys present in order,
    every list empty **although the database holds a match of every kind**, and the overridden fake
    factory records `call_count == 0` and no embed call.
  - DoD-8 — `test_no_designated_model_fails_the_request_with_409__S029_003_DoD8` (409
    `no_embedding_model`, and no group key in the body),
    `test_a_vector_dimension_mismatch_fails_the_request_with_409__S029_003_DoD8` (`detail` exactly
    `{"reason": "dimension_mismatch"}`),
    `test_an_unreachable_provider_fails_the_request_with_502__S029_003_DoD8` (the scripted fake
    through a second `dependency_overrides` application; 502 `llm_unreachable`). The vector tables
    are created **first** in all three.
  - DoD-9 — `test_the_route_table_holds_get_api_search_exactly_once__S029_003_DoD9` — the house
    `_ordered_api_routes`-shaped walk (file-local copy, descending into `.routes`, `.router.routes`
    and `.original_router.routes`), asserting the walk found routes at all, then exactly one
    `APIRoute` at `/api/search` with methods `{"GET"}`, cross-checked against
    `openapi()["paths"]["/api/search"]` holding only `get`. **No flat `isinstance` scan** (the
    skeleton's note: it would find zero routes and pass vacuously).
  - DoD-10 is `[manual/live]` — no test.
- `backend/tests/test_configuration_router.py` — **amended** (orchestrator decision 2, approved
  mechanical knock-on): `("/api/search", "GET")` added to `LATER_FEATURE_ROUTES` and its `#:`
  comment extended the way 023 did, citing 029 step 003 (D1, decision 6). The test **body**, and
  everything else in the file, is unchanged.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 [manual/live, no test].
- Mechanics: the real factory's application pinned to the per-test database through
  `dependency_overrides[get_settings]`, the fake provider through
  `dependency_overrides[get_llm_client_factory]` (024 D9) — the port is never mocked. The one
  `monkeypatch` in the file is the house `_quiet_factory_logging` autouse fixture every router
  suite uses (`app.main.configure_logging` → no-op), so no test writes a log file outside
  `tmp_path`; nothing else is patched. `conftest.py` and `llm_fakes.py` untouched.
- Expected to be green against the skeleton: **DoD-1 only** (the router-level `require_user` is
  real) and **DoD-9** (registration is a declaration, not a body). Every other case goes red on the
  stub's `NotImplementedError` surfacing as 500.

### What the red gate should expect to be green already

These clauses pin declarations the skeleton froze for real, so they pass against the stubs by
construction — not vacuous, they are the freeze's regression guards:
`test_the_per_kind_cap_constant_is_twenty__S029_001_DoD1`,
`test_the_my_search_module_imports_no_web_framework__S029_001_DoD10`,
`test_the_result_exposes_the_five_groups_in_uc059_order__S029_002_DoD2`,
`test_a_memo_hit_carries_no_title__S029_002_DoD4`,
`test_an_entry_hit_carries_the_frozen_five_fields__S029_002_DoD6` and both
`__S029_002_DoD12` guards. Every other test above goes red on `NotImplementedError`.

### Spec concern — step 001 DoD-9's mid-read clause

DoD-9 asks that "after each call — … and a call made while the connection is mid-read — the
connection reports no transaction in progress". The read posture D6 mandates, and that the skeleton
**implemented for real**, is `services/memos.py`'s `_reading`: it captures
`opened_here = not connection.in_transaction()` **before** the `yield` and rolls back only when it
opened the transaction itself, so a transaction the caller already opened is deliberately left
open. The literal clause is therefore unsatisfiable by the frozen module, and
`test_a_search_made_mid_read_opens_no_transaction_of_its_own__S029_001_DoD9` asserts the
orchestrator's own gloss instead ("the call left nothing open"): the search reads through the
caller's transaction, adds none of its own (`connection.get_transaction()` is either `None` or
still the caller's root transaction), and one `rollback()` clears everything. If the intent was the
stronger posture 026/027's `search_memos` / `search_sessions` use (roll back regardless of who
opened), that is a D6 change and a `SPEC` decision, not a test fix.

### Step 004 — tests (2026-10-05)

- `frontend/tests/app/searchApi.test.ts` — **new**, 4 `it`s, covers DoD-1, DoD-2 — one GET on the
  exact pathname `/api/search` with `q` read back **decoded** (`url.searchParams.get("q")`, so no
  `%20`-versus-`+` pinning), the resolved value equal to the stubbed five-group body, every id
  asserted character for character (all ids above 2^53), and a stubbed 409 envelope rejecting as an
  `ApiError` whose `code` is `no_embedding_model`.
- `frontend/tests/app/searchState.test.ts` — **new**, 22 `it`s, covers DoD-3..DoD-8 — the four
  frozen initial values; `isBlankQuery`; the blank-query no-request clause from a fresh **and** from
  an already-ready state; `"loading"` observed on a deferred stub then `"ready"` with the results and
  `query`; a 502 `llm_unreachable` envelope giving `"failed"` + the envelope's message with the
  promise **resolving**; two abort cases; `hasNoHits` across five one-hit-per-group states and five
  non-ready states; `searchHref`; and all eight targets, each compared to a template literal holding
  the id string verbatim.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓.
- Mechanics: Vitest with `globals: false` (every symbol imported from `"vitest"`); `fetch` stubbed
  per file with `vi.stubGlobal` and routed by exact pathname, anything else answering 404;
  `afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); })`; the house `deferred<T>()` +
  `flush()` (`setImmediate`, no `act` — these are pure-module tests, so no React, no
  `MemoryRouter`, no `AppProviders`); `"loading"` is observed between a deferred stub's creation and
  its resolution; the abort cases are (a) a stub that rejects with an `AbortError` on the signal and
  (b) a deferred stub resolved *after* `controller.abort()`, both asserted via
  `await expect(running).resolves.toBeUndefined()` plus a whole-state snapshot comparison. No `.css`
  file, no `@mantine/notifications` import, no id typed `number`, no `parseInt`; no existing test
  file amended.
- Expected to be green against the skeleton: **only** the `SearchState` initial-values clause under
  DoD-3 (the constructor is implemented for real). Every other clause goes red — the pure helpers on
  `throw new Error("not implemented")`, and the DoD-3/4/5 "never rejects" clauses as a **rejection**
  of `loadSearch`, which is the right red.

### Step 005 — tests (2026-10-05)

- `frontend/tests/app/SearchScreen.test.tsx` — **new**, 15 `it` declarations / 23 collected cases
  (two `it.each` blocks: eight targets and two blank queries), covers DoD-1..DoD-10. `SearchScreen` is rendered with **no props** inside `<AppProviders>` then
  `<MemoryRouter initialEntries={[…]}>`, in a host `div` so the probes beside it are invisible to
  every scoped query; the `useLocation` probe reads `pathname + search`. The eleven module
  constants are private, so every expectation is a role, an accessible name or one of
  `context.md`'s literal strings read off the DOM.
  - DoD-1 — `…five regions named Characters, Setups, Sessions, Entries, Notes render in that
    order, each holding its hit, from one request carrying q=mira — DoD-1`:
    `queryAllByRole("region")` (document order) compared element-for-element to the five
    `getByRole("region", { name })` lookups, plus each group's own primary text and the recorded
    `q` list `["mira"]`.
  - DoD-2 — two `it`s: hits only in Sessions and Notes → those two texts present **and** the
    region list exactly `[Sessions, Notes]`; five empty groups → `Nothing found.` present (the
    positive half) **and** no region.
  - DoD-3 — two `it`s: a disabled setup note beside an enabled user note (badge on the disabled
    row only, strike-through found by walking inline `text-decoration` from the snippet up to the
    row block, level labels `Setup note` / `User note`), and a character note + session note
    naming `Character note` / `Session note`.
  - DoD-4 — an archived character, setup and session each carry `Archived`; the live sibling in
    each of the three groups carries none (badge looked up on the row **block**, so a badge
    rendered beside the link is in scope).
  - DoD-5 — four `it`s: the setup row's two names; the session row's `formatSessionStart`
    (computed by calling the function DoD-5 names — never a pinned local-time string) plus
    `<character> · <setup>`, and a setup-less row whose text holds no `·` at all; the entry row's
    snippet plus `<character> · <formatted session start>`; and `A **bold** cut of the reply`
    rendered literally with no `strong` / `em` in the row.
  - DoD-6 — `it.each` over the eight rows of `004.context.md`'s Targets table, each asserting the
    row link's `href` **and** the probe after a click: `/characters/<id>`,
    `/characters/<character_id>` (setup), `/sessions/<id>`, `/sessions/<session_id>?entry=<id>`,
    `/settings`, `/characters/<character_id>` (character note and setup note), and
    `/sessions/<scope_id>?notes=open`.
  - DoD-7 — `it.each` over `/search` and `/search?q=%20`: the box exists and holds `""` / `" "`
    (the positive half), no region, no `Nothing found.`, and **no** `/api/search` request — the
    stub would have answered a hit in every group, so a request would be plainly visible.
  - DoD-8 — the box holds `mira`; `clear` + `type("kael{Enter}")` moves the probe to
    `/search?q=kael`, the recorded `q` list is `["mira", "kael"]`, the kael result shows, the mira
    result is gone and the box holds `kael`.
  - DoD-9 — a 409 `no_embedding_model` envelope renders `Search failed` **and** the envelope's
    message (both positive halves), no region and no `.mantine-Notification-root`; `Retry`
    re-requests the same `q` (`["mira", "mira"]`) and the 200 then shows all five regions.
  - DoD-10 — rendering at `/search` focuses the box; a click on a plain probe button takes focus
    away (asserted); a click on a `useNavigate` probe that pushes `/search` **again** (same path,
    new location key, no remount) must focus it back. A mount-only focus effect fails the second
    half by construction.
- `frontend/tests/app/App.test.tsx` — **amended**, exactly the amendment `005.context.md` assigns
  to this step, covers DoD-11, DoD-12:
  - `EMPTY_CENTRE_ROUTES` is now `["/"]` — `"/search"` removed; its doc comment gained the 029
    sentence in the 011-step-009 / 017-step-007 form, and the file header gained an "Amended by
    feature 029, step 005" paragraph. Both `it.each(EMPTY_CENTRE_ROUTES)` bodies and titles are
    untouched; they simply iterate one path now.
  - `NO_SESSION_ROUTES` **keeps** `"/search"`; that clause and its body are untouched.
  - `stubWorkspace` needed **no** `/api/search` branch: every render here reaches `/search` with a
    blank `q`, which makes no request (decision 10 / step 005 DoD-7). Verified by inspection of
    the two new clauses' paths — no other suite in the file visits `/search?q=…`.
  - Added at the bottom: a file-local `collapsedStorage()` (a stored `navCollapsed: true`, the
    `WorkspaceShell.test.tsx` mechanism) and a `searchBox()` helper scoped to the main region.
    DoD-11 is two `it`s — the rail's `Search` button lands on `/search` with the box focused, and
    `/search` with the tree expanded renders the focused box in the centre beside the tree. DoD-12
    is two `it`s — `/search` has left the empty-centre set (its centre is non-empty and holds the
    box) and stays in the no-note-wall set (the box renders and, even with a pinned layout, there
    is no `complementary`, no `Note wall` and no `Open notes`).
  - No existing assertion was dropped or weakened; `WorkspaceShell.test.tsx` is not amended.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 [manual/live, no test].
- Mechanics: Vitest with `globals: false` (every symbol imported from `"vitest"`); `fetch` stubbed
  with `vi.stubGlobal` and routed by the exact pathname `/api/search`, anything else 404;
  `afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); })`; the house `flush()`
  (`setImmediate` inside `act`, 6 rounds) and `userEvent.setup({ pointerEventsCheck: 0 })`; no
  fake timers. Ids are decimal strings above 2^60; no `number` id, no `parseInt`; no `.css` file
  created and `shell.css` untouched, so `tests/conventions.test.ts`,
  `tests/stylesheets.test.ts` and `tests/ids-are-strings.test.ts` stay green. The only `src`
  imports are the bound component, step `004`'s six frozen hit types and
  `formatSessionStart` — which DoD-5 names as the expected value itself.
- Expected against the skeleton: **every** clause of DoD-1..DoD-12 goes red, each on a missing
  element rather than a wrong value (the placeholder returns an empty fragment). The three
  absence-bearing clauses carry their positive halves as the skeleton note requires — DoD-2's two
  cases assert the two groups' texts / `Nothing found.`, DoD-7 asserts the box exists and holds
  the URL's query, DoD-9 asserts `Search failed` plus the envelope's message and then the five
  groups after `Retry` — so none of them can pass against the stub.
- Not run: `npm test` (the red gate's job) and `npm run typecheck` (no shell available to this
  agent; the verifier should treat a typecheck error in either file as a TEST fault).

### Step 006 — tests (2026-10-05)

- `frontend/tests/app/searchLanding.test.tsx` — **new**, 8 `it`s, covers DoD-3, DoD-4, DoD-5, DoD-6.
  `SessionScreen` is rendered with its **unchanged** three props (`sessionId`, `characters`,
  `storage={null}`) inside `<AppProviders>` then `<MemoryRouter initialEntries={[…]}>`, in a `<main>`
  landmark, at `/sessions/<s>` with and without the landing params — the URL is the only way in.
  `fetch` is stubbed with `vi.stubGlobal` and routed by the **exact** pathname over
  `SessionScreen.test.tsx`'s own set (`/api/sessions/<s>`, `…/entries`, `…/zone`, `…/memo-chain`,
  `…/configuration`, `/api/models`), anything else 404. The record is four settled entries with
  decimal-string ids above 2^60.
  - DoD-3 — two `it`s: at `?entry=<third>` every entry's `data-entry-id` equals its id **in the
    record's order** (`entryIds()` compared to the payload's id list), the third entry is the only
    element scrolled and the only one carrying `data-highlighted="true"`; and the same for the
    **first** and the **last** entry, so "the focus entry" is not an off-by-one.
  - DoD-4 — two `it`s with fake timers: the highlight is present after `advance(1999)` and gone
    after one further millisecond (2000 total), nothing scrolled a second time, and neither a
    genuine re-render of the entry (a `mouseEnter`, which flips its reveal state) nor one of the
    screen above it (pressing `Open notes`) scrolls again or brings the highlight back; plus a
    further 2000 ms changes nothing.
  - DoD-5 — two `it`s: `?entry=<id of no entry in the record>` renders all four entries (ids and
    texts both asserted — the positive half) with **no** entry scrolled, nothing highlighted and
    neither `Session not found` nor `Could not load the session` anywhere in the main region; and
    without the param the record renders with nothing highlighted and nothing scrolled.
  - DoD-6 — three `it`s: `?notes=open` renders the accessible complementary `Note wall` inside the
    main region holding the region `Notes`, with **no** `Open notes` control; the same URL without
    the param has no accessible wall and does offer `Open notes`; and `?entry=<m>&notes=open`
    satisfies both halves at once.
- `frontend/tests/app/CharacterTree.test.tsx` — **amended**, exactly the four sites orchestrator
  decision 8 names, covers DoD-1, DoD-2. Each amended line carries an `S029_006_DoD1` /
  `S029_006_DoD2` note and the file header gained an "Amended by feature 029, step 006" paragraph;
  the 009-era recognition line now says the header holds a **search box** named `Search`.
  - **L594** (`Search moves the in-entry router to /search — DoD-3`) — replaced by **three**
    DoD-1 clauses in the same `describe`, which drive the **textbox** (`user.type`, Enter) instead
    of clicking a button: `mira` → `/search` with `q` decoding to `mira`; `a&b c` → `q` decoding to
    `a&b c`; Enter on an empty box → `/search` with an empty query string. All three keep
    `expect(currentPath()).toBe(SEARCH_PATH)` and `expect(navigate).not.toHaveBeenCalled()`. The
    sibling `New character` clause is untouched.
  - **L744-753** (`the ready tree's only buttons are Search and New character — DoD-6`) — the
    button-name set is now `["New character"]`; the title names one button. Nothing else changed.
  - **L763** (`the switch is the tree's only other control and the rows are links — DoD-6`) — the
    `queryAllByRole("textbox")` assertion flipped from "empty" to **exactly one, the search field**
    (length 1, identical to `searchBox()`); the `switchCount()`, switch and link assertions are
    untouched. *(The plan missed this site; decision 8 adds it.)*
  - **L798** (`no chevron, no session row, and the characters keep the payload's order — DoD-13`) —
    the second button-name-set assertion also becomes `["New character"]`; its title and every
    other assertion in the clause are untouched. *(Also decision 8's addition.)*
  - Two small additions to the harness: `LocationProbe` now also renders `location.search` as
    `data-testid="probe-search"` (so `q` can be read back **decoded** via `URLSearchParams.get`,
    never as a pinned `%`-encoding), and a `searchBox()` query (`getByRole("textbox", { name:
    SEARCH_NAME })`). No existing assertion was dropped or weakened, and no id tag was removed.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 [manual/live, no test].
- Mechanics: Vitest with `globals: false` (every symbol imported from `"vitest"`);
  `afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); })`; the house
  `flush()` (`setImmediate` inside `act`, 6 rounds) and `AppBoot.test.tsx`'s fake-timer idiom with
  the explicit `toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"]` allow-list,
  so `setImmediate` stays real and `flush()` still settles. The scroll is observed with
  `vi.spyOn(Element.prototype, "scrollIntoView").mockImplementation(function (this: Element) { … })`,
  recording the **element** of each call; the counts are taken over the calls whose element sits in
  an entry (`closest('[data-entry-id]')`), so an unrelated `scrollIntoView` from a component library
  cannot make a clause lie in either direction. The highlight is recognised **only** by
  `data-highlighted="true"`; the Mantine `bg` shade is never asserted. `src/shared/MarkdownEditor`
  is stubbed exactly as `SessionScreen.test.tsx` stubs it (harness setup, so TipTap is not mounted).
  No `.css` file created, `shell.css` untouched, no `number` id, no `parseInt` — the three guard
  suites stay green. Only `SessionScreen` is imported from `src/`, with its unchanged props.
- Not amended, by design: `SessionScreen.test.tsx`, `SessionStream.test.tsx`,
  `SessionStreamCoverage.test.tsx`, `SessionStreamTranslation.test.tsx`, `StreamRecord.test.tsx`,
  `StreamRecordActions.test.tsx`, `StreamRecordTranslation.test.tsx` and
  `StreamRecordDiscussion.test.tsx` — the new props are optional and neither stream component uses a
  router hook (decision 9).
- Expected against the skeleton: DoD-1's three clauses go red on the navigation half (the box exists
  and typing works, but Enter raises `not implemented`, so the probe never leaves `/`); DoD-3 red on
  the missing `scrollIntoView` call and the missing `data-highlighted` (the `data-entry-id` half
  already passes); DoD-4 and DoD-6's first and third clauses red on absence. **DoD-2 and DoD-5 pass
  against the skeleton by construction**, as the skeleton's note says — the amended census is a
  regression guard for a real declaration, and DoD-5 is an absence clause, which is why both its
  cases also assert the record's ids and texts so neither can pass vacuously.
- Not run: `npm test` (the red gate's job) and `npm run typecheck` (no shell available to this
  agent; the verifier should treat a typecheck error in either file as a TEST fault).

## Notes & Issues
- Steps 001/002: `ports.py`'s `SearchHit.memo_scope_id` docstring claims it is "`None` for the `"user"`
  level", but `hybrid._memo_hits` passes the **raw stored** `memos.scope_id` through, which at the user
  level is the owner's user id (exactly what orchestrator decision 5 warns about). 029's memo hydration
  does the `None`-ification; the misleading 025 docstring is out of 029's scope and left untouched.

## Ultra phase

- orient: done 2026-10-05
- harvest: part 1 done — docs/.cache/ultra/029.my-search/harvest.md (backend + sweep)

### Orchestrator decisions at harvest, part 1 (029)

1. **Step `001`'s Test files are extended by `backend/tests/test_search_hybrid.py`.** Step `001`
   creates a **ninth** module in `app/services/search/`, and that file pins the directory's `*.py`
   set (six at 025, seven after 026, eight after 027). Append `"my_search.py"`, rename the test
   eight → nine. **Deliberate knock-on:** the two sibling scans read the same tuple, so the new
   module must import neither `fastapi`/`starlette` nor `sqlite_vec` — which step 001's own DoD-10
   already half-requires. This is the third feature in a row to hit this; it is now a known pattern.
2. **Step `003`'s Test files are extended by `backend/tests/test_configuration_router.py`.**
   `test_the_configuration_router_is_included_last__S017_005_DoD9` asserts that the only routes
   following the configuration router belong to later features, via a `LATER_FEATURE_ROUTES`
   allow-set that 023 already widened once for the translation route. Add `("/api/search", "GET")`
   and extend its comment the way 023 did. The test **body** does not change.
3. **The LIKE spelling is `contains(..., autoescape=True)`, not `icontains`.** SQLite's `LIKE` is
   already ASCII-case-insensitive by default (and nothing in the repo sets
   `PRAGMA case_sensitive_like`), so `contains` satisfies D3 as written; `icontains` would add
   `lower()` on both sides for no behavioural gain on this dialect. **Note the escape character
   SQLAlchemy declares is `/`, not `\`** — step 001 DoD-6's backslash case therefore tests a
   *literal* backslash in the needle, which is not the escape character.
4. **The response conversion follows the `MemoChainResponse` precedent.** There is **no**
   `classmethod from_*` anywhere in `app/models/` — the house forms are
   `Model.model_validate(obj, from_attributes=True)` at the router (20 sites) and the same with
   `model_config = ConfigDict(from_attributes=True)` on the model. For a grouped payload the nearest
   precedent is `MemoChainResponse`: the outer model built by keyword, the leaf rows through
   `model_validate`. Step `003`'s skeleton freezes the exact shape; it should not invent a
   classmethod without reason.
5. **The memo hydration must `None`-ify `scope_id` for the user level.** The 025 port returns
   `memo_scope_id` as the **raw stored** `memos.scope_id`, which for a user-level memo is the owner's
   own id; step `002`'s Interface intent and the wire contract both require `None` there. The port
   will not do it — 029's hydration must, the way `services/memos.py`'s `to_memo` does. Flagged to
   the skeleton and the coder because it is silent data corruption if missed, not a crash.
6. **`/api/search` is registered last, after `translation_router`**, per step `003`. That is what
   makes decision 2's amendment necessary; registering it *before* `configuration_router` would
   instead break 017's "nothing that pre-dates the configuration router may follow it" clause.
7. **No "no SQL construct" test for `routers/search.py`.** `test_memos_router.py` has that guard for
   its own router, but step `003`'s DoD declares no equivalent clause, so none is added — noted so
   its absence is a recorded choice rather than an oversight.

### Orchestrator decisions at harvest, part 2 — the frontend (029)

8. **Step `006`'s `CharacterTree.test.tsx` amendments cover FOUR sites, not the two the plan names.**
   Declared: L594 (`Search moves the in-entry router to /search`) and L744-753 (`the ready tree's only
   buttons are Search and New character`). **Additions the plan missed:** **L798**, inside
   `no chevron, no session row, and the characters keep the payload's order — DoD-13`, which carries a
   second button-name-set assertion; and **L763**, inside `the switch is the tree's only other control
   and the rows are links — DoD-6`, which asserts `queryAllByRole("textbox")` is **empty** — exactly
   false once the header holds a search field. Both button sets become `["New character"]`; L763
   becomes "exactly one textbox, the search field". Recorded as mechanical knock-ons under the same
   policy as decisions 1 and 2.
9. **`SessionStream` and `StreamRecord` must not use any router hook.** This is the decisive
   constraint behind the plan's claim that `SessionScreen.test.tsx`, `SessionStream.test.tsx` and
   `StreamRecord.test.tsx` need no amendment — and the plan never states it.
   `SessionStream.test.tsx`, `SessionStreamCoverage.test.tsx`, `SessionStreamTranslation.test.tsx`,
   `StreamRecord.test.tsx`, `StreamRecordActions.test.tsx`, `StreamRecordTranslation.test.tsx` and
   `StreamRecordDiscussion.test.tsx` all render those components with **no `MemoryRouter`**, so a
   `useSearchParams` or `useLocation` call inside either would throw in seven delivered files. The
   focus-entry id must therefore arrive as a **prop** from `SessionScreen` (which does have a router),
   exactly as step `006`'s Interface intent says. The claim holds; the reason is load-bearing and is
   now written down.
10. **Settled by the plan, not open:** `SearchState` is created **inside `SearchScreen`** with
    `useState` (step `005` Interface intent), so it is fresh per mount; a blank `q` issues **no**
    request (step `005` DoD-7 asserts `fetch` is never called for `/api/search`), so neither
    `App.test.tsx`'s `stubWorkspace` nor `entries.test.tsx`'s stub needs an `/api/search` branch for
    the blank case; the tree's `TextInput` **navigates** on Enter to `searchHref(value)` rather than
    filtering in place; and the highlight is expressed as a Mantine `bg` prop plus
    `data-highlighted="true"`, never CSS — the stylesheet guards forbid a new stylesheet.
11. **The `notes=open` effect must only ever *open*, never force-close.**
    `SessionScreen.test.tsx:1155` navigates between two query-less session URLs and asserts the wall is
    closed again, so the branch has to be "open when `notes=open` is present" and silent otherwise. A
    `searchParams`-keyed effect that closes on absence would break that delivered test.
12. **Firsts to be aware of — no in-repo precedent for any of these:** `useSearchParams` and
    `URLSearchParams` appear nowhere in `src/` (029 is the first caller of the router's search API);
    nothing calls `scrollIntoView` in `src/` and nothing spies on it in `tests/`; and no component
    highlights anything with `Mark`, `Highlight` or a `bg` prop. Also: `IconSearch` must be dropped
    from `CharacterTree.tsx`'s import when the button goes — `noUnusedLocals: true` turns a stale
    import into a typecheck failure. Session-time assertions use the shape
    `/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/`, never an exact local-time string.
- harvest: done — docs/.cache/ultra/029.my-search/harvest.md (2 reports, both with sweeps)
- skeleton: done — steps 001, 002, 003, 004, 005, 006
- tests: done — steps 001..006 (approved deviations: step 001 amends `test_search_hybrid.py`'s
  module set eight → nine; step 003 amends `test_configuration_router.py`'s `LATER_FEATURE_ROUTES`;
  step 005 amends `App.test.tsx`'s `EMPTY_CENTRE_ROUTES`; step 006 amends `CharacterTree.test.tsx`
  at **four** sites per decision 8. No test-coder had a shell, so no lint or typecheck has run on
  any of the six new test files — the red gate carries that risk.)
- red-gate: PASS (run 1) — backend **4275 collected / 61 failed, 61/61 `NotImplementedError`**;
  frontend **4082 collected / 61 failed**, all missing-element or thrown `not implemented`, no
  module-resolution or render-setup failure. `mypy app` clean (90 files), `ruff check .` clean,
  `npm run typecheck` clean, `npm run build` clean, and the three frontend guards
  (`conventions`, `stylesheets`, `ids-are-strings`) green unchanged — **all on first execution**,
  though no test-coder had a shell. The green set was exactly the declared expected-green set
  plus one benign extra (006 DoD-6's no-param negative control, whose siblings are red).
  **Baseline correction:** the frontend total before 029 was **4018**, not the 4020 recorded at
  025; 029 adds 64 (58 new + net 6 from the two amendments). Inventory drift to fix in the
  test-coders' own records: step 002 collects 28 cases (recorded 26), step 006's new file 9
  (recorded 8).
- code: done — steps 001..006 (no re-freeze, no escape valve)
- verify: **PASS (run 2)** — run 1 FAIL: **005 CODE**. Backend **4275 passed / 0 failed**; frontend
  **4082 passed / 0 failed** (137 files); `mypy app` clean (90 files), `ruff check .` clean,
  `npm run typecheck` clean, `npm run build` clean; the three frontend guards green; the **eight**
  unamended stream/session suites green. **3 `[manual/live]` outstanding** (003 DoD-10, 005 DoD-13,
  006 DoD-7).

### The one CODE fault, and why it was worth catching (029 step 005)

Five of six steps passed run 1. Step 005's row helper put only the **primary** text inside each
row's link and rendered the secondary line as a sibling **outside** it. For four of the five kinds
that is invisible — a character's or setup's name, an entry's or a note's snippet, identifies the row
on its own. For a **session** it is not: a session has no name, its primary text is only the
formatted start, and **all** of its identifying material (the character name, and the setup name
when there is one) lives in the secondary line. So a session row could be identified and activated
only by its timestamp, and DoD-4 (archived marking), DoD-5 (row labels) and DoD-6 (navigation) each
failed on that single structural choice — for the session group alone.

The repair brought the secondary line **inside** the link and left the badge where it was (a sibling
of the link inside the row item — DoD-4's lookup depends on that). It is also the house idiom
`005.context.md` already pointed at: `CharacterTree.tsx`'s session `NavLink` carries both its label
and its description inside the anchor, with only the `Archived` badge outside. The 20 cases that
were green stayed green — nothing was traded away.

Two consequences the coder flagged and the verifier adjudicated: every row's link accessible name
now folds in the secondary line, which **no DoD clause covers and no test binds to**, and is a
better name besides (a setup link now names its character); and the feared loss of link colour does
not occur — Mantine 7's `Text` sets `color: var(--text-color)` with no fallback, and an unset custom
property on an inherited property resolves to `inherit`, so an unmarked row's lines take the
anchor's colour exactly as before.

### The air-gap smudges, adjudicated (029)

Three coders disclosed, unprompted, that reading `status.md` with a wide `grep -A` / `sed` range
scrolled part of `## Tests` into view — test **names and case counts**, never assertion bodies, and
none opened a file under `tests/`. This is the third feature in the run where the same mechanism has
bitten. The verifier judged the implementations **spec-derived, not test-shaped**, on four grounds,
the first decisive: **step 005's coder shipped a row decomposition that fails three of its own
step's clauses** — the opposite of test-shaping; no fixture value, id, token or test name appears
anywhere in the twelve source files; every non-obvious choice traces to a document the coder was
entitled to read (D5 and `to_memo`, D6 by name, D3, decision 11, the enumerated re-render causes);
and the two judgement calls that happen to match the tests both had independent spec grounds.
**Standing risk, worth fixing upstream for 030–032:** brief coders to extract `## Skeleton` and
`## Ultra phase` by anchored, bounded ranges that stop at the next `##`, which is what I did from
step 005's coder onward and what the last three honoured.

### Adjudicated: step 001 DoD-9's "mid-read" clause (not a SPEC hand-back)

The step-001 test-coder raised a `## Spec concern`: DoD-9 asks that after "a call made while the
connection is mid-read" the connection "reports no transaction in progress", but the frozen
`_reading` — which **D6 mandates by name and line number** — captures `opened_here` before the
yield and rolls back only what it opened itself, deliberately leaving a caller's transaction alone.

**Adjudicated here; no plan change, no code change, no re-freeze.** D6 is the specific, deliberate
statement and it wins over DoD-9's loose phrasing: a service that rolled back its *caller's*
transaction would be a defect, not a feature. Note 026's `search_memos` and 027's `search_sessions`
do use the stronger `finally: if in_transaction(): rollback()` posture — but only because that was
their explicit contract to 021's seam; 029's D6 chose the `_reading` posture instead, and 029's
caller is a route whose `get_connection` opens no transaction, so the two never differ in
production.

The test therefore asserts D6's actual contract: the call leaves **no transaction of its own** open,
the caller's transaction survives, and one `rollback()` clears everything. The verifier should
confirm that reading rather than the literal sentence.

### Notes carried from the skeletons that the test-coders must honour (029)

- **Step 002 DoD-12's two halves need different mechanisms.** The `is_forced` clause is a
  **source-text** guard (`inspect.getsource` + `not in`), so the literal token may not appear
  anywhere in `my_search.py` — code, comment or docstring; the skeleton wrote "the forced flag"
  instead. The `fastapi` clause must be checked by **imports / AST**, because step 001's frozen
  module docstring legitimately contains the words "no `fastapi`".
- **Step 003 DoD-9 cannot use a flat `isinstance(route, APIRoute)` scan.** Under the pinned FastAPI
  version `application.routes` holds Starlette routes plus `_IncludedRouter` wrappers whose
  `.routes` is `None`, so a flat scan finds **zero** API routes. Use
  `test_configuration_router.py`'s `_ordered_api_routes` walk (it descends into
  `.original_router.routes`) or `openapi()["paths"]`.
- **Step 005's placeholder renders an empty fragment**, deliberately not a throw, so delivered
  `App.test.tsx` suites that render `/search` keep passing. Consequence: any clause asserting only
  an **absence** passes against the skeleton. DoD-2, DoD-7 and DoD-9 must each also assert their
  positive half (the box exists; the envelope's message appears).
- **Step 006 DoD-2 and DoD-5 are green against the skeleton by construction** — the search box is
  real, so the amended census passes, and a do-nothing stub cannot fail "an unknown `entry` does
  nothing". Expected, not vacuous: both are regression guards for an amendment and an absence.
- **Step 006's `SEARCH_PATH` is gone** from `CharacterTree.tsx` (nothing else used it and
  `searchHref("")` already yields `/search`), so a test may no longer import it from there.
- **The highlight is Mantine `bg="yellow.1"` plus `data-highlighted="true"`** — frozen as
  `HIGHLIGHT_BG`; the shade is the coder's to tune, the mechanism is not.
