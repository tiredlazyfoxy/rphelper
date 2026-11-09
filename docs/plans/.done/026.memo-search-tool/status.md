# Feature 026 — memo-search-tool

| Step | File                                    | Status  | Verifier | Date |
|------|-----------------------------------------|---------|----------|------|
| 001  | `001.chain-clause-and-memo-search.md`   | done    | PASS     | 2026-10-05 |
| 002  | `002.memo-search-tool-adapter.md`       | done    | PASS     | 2026-10-05 |

## Files Changed

### Step 001 — the chain clause and `search/memo_search.py`
- `backend/app/services/memo_chain.py` — `chain_clause` implemented: the OR of
  `(scope = level AND scope_id = stored id)` over user, character, setup (omitted when `setup_id`
  is `None`) and session, built from `relation.c["scope"]` / `relation.c["scope_id"]`, pure.
  **`resolve_chain` re-routed** through it (D2's one home): the terms are built in the same order
  over the same stored ids, so the emitted select, its row order, the user level's `scope_id=None`
  and `SessionNotFoundError` are unchanged; one docstring sentence updated to say so.
- `backend/app/services/search/memo_search.py` — `searchable_chain_predicate` returns a builder
  answering `and_(is_enabled, not_(is_forced), chain_clause(relation, ...))` (R3 order, literal);
  `search_memos` builds `MemoSearchScope(user_id, extra_predicate=…)`, calls the port's `search`
  with `MEMO_SEARCH_LIMIT`, returns its hits unchanged, passes `client_factory` /
  `timeout_seconds` straight through, and rolls back in a `finally` whenever
  `connection.in_transaction()` so neither exit leaves a transaction open. Imports added:
  `ColumnElement`/`FromClause`/`and_`/`not_`, `chain_clause`, `hybrid.search`, `MemoSearchScope`.

### Step 002 — the `memo_search` `Tool` adapter
- `backend/app/services/tools/memo_search.py` — the two frozen bodies filled. `format_hits`
  answers `("\n".join(f"[{level}] {snippet}"), f"{len(hits)} memos")` with each snippet's
  whitespace runs collapsed by `" ".join(snippet.split())` (so one line per hit, ends stripped),
  hit order untouched, and `"No matching notes."` with `"0 memos"` for no hits (D4). `run` reads
  only `arguments["query"]`, raises `ToolFailedError(detail={"tool": MEMO_SEARCH_NAME})` when it is
  missing or not a `str`, then `await asyncio.to_thread(search_memos, connection, user_id=…,
  character_id=…, setup_id=…, session_id=…, query_text=query, **injected)` with every id taken
  from the `ToolScope` (D6) and `client_factory` / `timeout_seconds` forwarded **only** when the
  injected field is not `None` (so `search_memos`' own defaults apply otherwise), and returns
  `ToolOutcome(content, summary)`. Search errors propagate unchanged and `run` issues no SQL of its
  own (D3, D5). Imports added: `asyncio`, `Any`, `ToolFailedError`, `search_memos`, and the
  function-local `ToolOutcome` inside `run`.
- `backend/app/services/tools/seam.py` — **not changed by this step**; the skeleton's registration
  (`PRODUCTION_TOOL_REGISTRY` → `{MEMO_SEARCH_NAME: MemoSearchTool()}`) was already in place and
  needed no body.

## Notes & Issues

- Step 001: SQLAlchemy's SQLite dialect is non-native-boolean, so the predicate compiles to
  `memos.is_enabled = 1 AND memos.is_forced = 0 AND (…)`; the literal token `NOT` appears only
  under the default dialect (`memos.is_enabled AND NOT memos.is_forced AND (…)`). Position of
  `is_enabled` before `is_forced` holds in both. No form of `not_()` can render `NOT <col>` under
  the SQLite dialect for a `Boolean` column.
- Step 002: `asyncio.to_thread` is typed with a `ParamSpec`, so mypy rejects `**dict[str, object]`
  for the conditionally-forwarded keywords ("incompatible type \*\*dict[str, object]"). The holder
  is annotated `dict[str, Any]`, which mypy accepts; `Any` is the one import added beyond the
  skeleton's enumerated list, and it appears only inside `run`'s body (no signature moved).

## Ultra phase

- orient: done 2026-10-04
- harvest: done — docs/.cache/ultra/026.memo-search-tool/harvest.md (3 reports)
- skeleton: done — steps 001, 002
- tests: done — steps 001, 002 (approved deviations: step 001 amends `test_search_hybrid.py`'s
  module set; step 002 amends `test_tool_seam.py` ×4, `test_compose_route.py`, `test_compose_source.py`)
- red-gate: PASS (run 2) — run 1 FAIL: 002 TEST (ruff `I001`, a comment inside an amended import block;
  47/47 failures were already `NotImplementedError` and zero regressions, so the fault was lint-only)
- code: done — steps 001, 002 (no re-freeze, no escape valve)
- verify: PASS (run 1) — 3982 passed / 0 failed / 0 errored; mypy 81 files clean; ruff clean;
  frontend untouched so its gates were correctly not run; 1 `[manual/live]` outstanding (002 DoD-16)

### Orchestrator corrections to other agents' records (026)

Two records went stale as the run proceeded. They belong to the skeleton and the coder, so I am
correcting them here rather than editing their sections:

- Step 001's `## Skeleton` record says `resolve_chain` is "unchanged (not re-routed)". The coder
  **did** re-route it through `chain_clause`, which D2 and the step's Interface intent both permit.
  The precondition held: `tests/test_memo_chain_service.py` is untouched on disk and green inside the
  3982, and the verifier re-read the body and confirmed the terms, their order, the stored ids, the
  owner predicate, the `order_by` and the `SessionNotFoundError` path are all unchanged. The frozen
  signature did not move; only the record's parenthetical is stale.
- Step 002's `## Files Changed` says `seam.py` was "not changed by this step". True of the coder's
  pass — the **skeleton** wrote the registration — but the file is changed relative to `HEAD`, and it
  is the feature's one edit to a 021-owned source file. Anyone auditing `## Files Changed` alone
  would miss it.

One air-gap note, disclosed by the step-002 coder unprompted: extracting `## Ultra phase` with an
`awk` range, it read past the Skeleton record into `## Tests` and saw step 001's test-name inventory
and step 002's test/case counts before stopping. It saw no assertion text and no expected value, and
implemented from the DoD and the literals table. The gap was nicked, not broken; recorded for honesty.

### Orchestrator decisions at harvest (026)

1. **Frozen names beat `context.md` prose** (`context.md` binding rule for (B) interfaces).
   `SearchHit`'s memo fields are `memo_scope` / `memo_scope_id` (025 `001` `## Skeleton`), and the
   port's `client_factory` default is `LlmClient`, not `get_llm_client_factory`. Step `001`'s
   Interface intent says "the port's own defaults", so the source defaults are what is mirrored.
2. **Step `002`'s amendment of 021 `004` DoD-2 covers all three `S021_004_DoD2` emptiness
   assertions** (`test_tool_seam.py:351`, `:357`'s trailing length check, `:365`), not only the
   `offered_tools` one. The amendment table's "Was" column names both "the production registry is
   empty" and the `offered_tools` result, and all three tests carry that one DoD tag. The
   read-only test keeps its `pytest.raises(TypeError)` — the registry stays a `MappingProxyType`.
3. **Step `002`'s Test files are extended by `backend/tests/test_compose_source.py`** — a third
   021-owned file. `test_the_production_registry_sends_an_empty_tools_list__S021_005_DoD13`
   (`:1050`) asserts `tools == []` against the real registry and the registration makes it false.
   Same principle and same wording as `context.md`'s "amended only at the assertions the
   registration makes false"; the planner's enumeration was one file short. Amend that one
   assertion and its docstring; every other test in the file stays unchanged.
4. **Step `001`'s Test files are extended by `backend/tests/test_search_hybrid.py`** —
   025-owned. `SEARCH_PACKAGE_MODULES` (`:219`) pins the `*.py` set in `app/services/search/` as
   exactly six names and `test_the_six_search_modules_are_all_present_to_scan__S025_004_DoD15`
   (`:1147`) asserts set equality, so step `001`'s new `memo_search.py` breaks it. Add
   `"memo_search.py"` and rename "six" → "seven". **Deliberate knock-on:** the two sibling scans
   (`:1154`, `:1166`) iterate that tuple, so the new module is then also required to import
   neither `fastapi`/`starlette` nor `sqlite_vec`. Leaving it un-amended would let those scans
   pass while proving less, which is worse than amending them.
5. **The function-local `ToolOutcome` import is sanctioned** (`002.context.md` "Known-good
   form"). Ruff selects only `E,F,I,B,UP,W` — no `PLC0415` — so it is lint-clean, and a
   module-bottom import would instead trip `E402`. `ToolScope`/`ToolOutcome`/`Tool` are defined
   at `seam.py:40-66`, *after* its import block, so a top-level import of them in the adapter
   would hit a partially-initialised module. `app/services/tools/__init__.py` is **not** touched:
   `seam.py` reaches the adapter by submodule path, which `__all__` does not govern.

## Skeleton

### Step 001 — frozen interface (2026-10-05)

- `backend/app/services/memo_chain.py` — **new**, public:
  ```python
  def chain_clause(
      relation: FromClause,
      user_id: int,
      character_id: int,
      setup_id: int | None,
      session_id: int,
  ) -> ColumnElement[bool]:
  ```
- `backend/app/services/memo_chain.py` — `resolve_chain(connection: Connection, user_id: int,
  session_id: int) -> list[MemoChainLevel]` — **unchanged** (not re-routed; re-routing stays the
  coder's optional call per D2). `MemoChainLevel`, `MemoReach`, `memo_reach` unchanged. Only other
  edit: `FromClause` added to the existing `from sqlalchemy import ...` line, plus one sentence in
  the module docstring naming `chain_clause`.
- `backend/app/services/search/memo_search.py` — **new module**, three public names:
  ```python
  MEMO_SEARCH_LIMIT: Final[int] = 8

  def searchable_chain_predicate(
      user_id: int,
      character_id: int,
      setup_id: int | None,
      session_id: int,
  ) -> ExtraPredicateBuilder:

  def search_memos(
      connection: Connection,
      user_id: int,
      character_id: int,
      setup_id: int | None,
      session_id: int,
      query_text: str,
      *,
      client_factory: LlmClientFactory = LlmClient,
      timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
  ) -> list[SearchHit]:
  ```
  Imports as frozen: `Final` from `typing`; `Connection` from `sqlalchemy`;
  `DEFAULT_EMBED_TIMEOUT_SECONDS` from `app.services.embedding`; `LlmClient` from
  `app.services.llm.client`; `LlmClientFactory` from `app.services.llm_registry`;
  `ExtraPredicateBuilder, SearchHit` from `app.services.search.ports`.
- Caller-compile edits (out of Source-files scope): **None.** `chain_clause` is additive and
  `resolve_chain`'s signature did not move, so no call site anywhere needed touching.

**Naming rationale**

- `chain_clause` — `context.md`'s Vocabulary already calls this thing "the chain clause"; the name
  is the vocabulary term verbatim. Noun-style, matching the codebase's other clause/statement
  builders (`base_relation`, `candidate_ids`, `build_fts_query`) rather than `get_`/`build_`.
- `relation` first — the parameter name 025 uses for the same object (`candidates.base_relation`,
  and every extra-predicate builder in the 024/025 tests). `FromClause` (not `Table`) is the
  static type, because that is what `ExtraPredicateBuilder` passes; index columns as
  `relation.c["scope"]` / `relation.c["scope_id"]` — `.c.scope` is untyped on a `FromClause` and
  will not survive `mypy`.
- Id order `user_id, character_id, setup_id, session_id` — the step file's fixed disjunction order,
  so the natural implementation (terms appended in parameter order) produces DoD-1's term order for
  free. Positional-or-keyword, so a caller may pass either way.
- `searchable_chain_predicate` — names both halves of what it builds in `context.md`'s own
  vocabulary: *searchable* (`is_enabled AND NOT is_forced`) AND the *chain* clause. "predicate"
  (not "builder") because the suffix `_predicate` is how 025 names the thing itself
  (`extra_predicate`); it is a factory of one, which the return type says.
- `MEMO_SEARCH_LIMIT` — `MEMO_`-prefixed like `search_tables.py`'s `MEMO_FTS_TABLE` /
  `MEMO_VEC_TABLE`, and `LIMIT` because the value's whole job is to be the port's `limit`
  argument. Reads unambiguously at the step-002 import site.
- `search_memos` — the name the step file and D3 already use; `connection` first then ids, per the
  service convention.
- `query_text` — the port's own parameter name, so the pass-through is nominally identical.

**Notes for the test-coder and the coder**

- `search_memos`' `client_factory` / `timeout_seconds` defaults are mirrored from the frozen port
  (`hybrid.search`): `LlmClient` and `DEFAULT_EMBED_TIMEOUT_SECONDS` — **not**
  `get_llm_client_factory`, despite `context.md` (B). Per the binding rule, frozen source wins.
- Hits are the port's `SearchHit`; its memo fields are `memo_scope` / `memo_scope_id`, and
  `memo_scope_id` is the **raw stored** id (A's user id for a user-level hit). No `scope` field
  exists on a hit, and step `001` adds none.
- Bodies are `raise NotImplementedError` with one exception: `MEMO_SEARCH_LIMIT = 8`, whose value
  is its declaration (DoD-5 is already satisfiable).
- `memo_search.py` deliberately imports **neither** `hybrid.search` **nor** `MemoSearchScope` yet —
  neither appears in a signature and `F401` is on. The coder adds both
  (`from app.services.search.hybrid import search`, `MemoSearchScope` from `.ports`) plus
  `chain_clause` from `app.services.memo_chain` when filling the bodies. Keep the import block
  isort-clean (`I` is selected).
- `chain_clause` is pure and takes no connection, so DoD-1/DoD-4 can compile it with
  `literal_binds` without a database. DoD-4 compares the positions of `is_enabled` and `is_forced`
  in the compiled text, so the predicate must be built with the `is_enabled` term genuinely first
  and `is_forced` negated — the parameter order imposes no obstacle.
- `search_memos`' "no transaction open on return and on raise" is behaviour, not signature: a
  `finally` that rolls back when `connection.in_transaction()`, wrapping the port call (001
  `context.md`).
- `app/services/search/` now holds **seven** `*.py` files; `test_search_hybrid.py`'s
  `SEARCH_PACKAGE_MODULES` tuple (025-owned, amended in this step per Ultra decision 4) must gain
  `"memo_search.py"`. The sibling scans then also require this module to import no web framework
  and no vector extension — it imports neither, and the module's own docstring avoids those literal
  tokens so a text-based DoD-13 check cannot false-positive.

### Step 002 — frozen interface (2026-10-05)

- `backend/app/services/tools/memo_search.py` — **new module**, two public names:
  ```python
  def format_hits(hits: Sequence[SearchHit]) -> tuple[str, str]:

  @dataclass(frozen=True, kw_only=True)
  class MemoSearchTool:
      client_factory: LlmClientFactory | None = None
      timeout_seconds: float | None = None
      name: ClassVar[str] = MEMO_SEARCH_NAME

      async def run(
          self, scope: "ToolScope", connection: Connection, arguments: Mapping[str, object]
      ) -> "ToolOutcome":
  ```
  Imports as frozen: `Mapping, Sequence` from `collections.abc`; `dataclass` from `dataclasses`;
  `TYPE_CHECKING, ClassVar` from `typing`; `Connection` from `sqlalchemy`; `LlmClientFactory` from
  `app.services.llm_registry`; `SearchHit` from `app.services.search.ports`; `MEMO_SEARCH_NAME`
  from `app.services.tools.definitions`; and **under `if TYPE_CHECKING:`** `ToolOutcome, ToolScope`
  from `app.services.tools.seam`.
- `backend/app/services/tools/seam.py` — **changed**, two one-line hunks and nothing else:
  ```python
  from app.services.tools.memo_search import MemoSearchTool          # new, after `...definitions`

  PRODUCTION_TOOL_REGISTRY: Final[ToolRegistry] = MappingProxyType({MEMO_SEARCH_NAME: MemoSearchTool()})
  ```
  was `MappingProxyType({})`. The name, the `Final[ToolRegistry]` annotation, the module and the
  `MappingProxyType` wrapper are all unchanged, so item assignment still raises `TypeError`. Its
  attached docstring is reworded (it claimed the registry is empty); `ToolRegistry`'s own docstring
  ("the production one is empty in `021`") is historical and left alone. `dispatch`,
  `offered_tools`, `build_tool_scope`, `tool_start_frame`, every literal and every other import are
  untouched.
- Caller-compile edits (out of Source-files scope): **None.** `routers/stream.py`'s
  `get_tool_registry` already returns `PRODUCTION_TOOL_REGISTRY`, `app/services/tools/__init__.py`
  re-exports it by name, and no signature moved, so nothing outside the two Source files needed an
  edit.

**Naming and shape rationale**

- `MemoSearchTool` — `<Declaration>Tool`: the declared name `memo_search` plus what it is, so the
  registry line reads `{MEMO_SEARCH_NAME: MemoSearchTool()}`. `027` / `028` get
  `SessionSearchTool` / `WebSearchTool` for free. Not `MemoSearchAdapter`: "the adapter" is
  `context.md`'s vocabulary for the role, not a codebase suffix.
- **Frozen keyword-only dataclass, not a hand-written `__init__`.** The adapter is two injected
  dependencies and no state, which is exactly what the seam's own `ToolScope` / `ToolOutcome` /
  `DispatchResult` use a frozen dataclass for; it also means the skeleton writes **no constructor
  body at all**, so nothing about construction is this step's invention. `kw_only=True` makes both
  arguments keyword-only, as the Interface intent asks.
- **`client_factory: LlmClientFactory | None = None` / `timeout_seconds: float | None = None`.**
  `None` means "not injected", and the coder's `run` then omits that keyword from the
  `search_memos` call so the callee's own default applies. The alternative — defaulting the fields
  to `LlmClient` and `DEFAULT_EMBED_TIMEOUT_SECONDS` — was rejected: it would make this module a
  second source of truth for defaults that step `001` already mirrors from the port, and the two
  would drift silently. `MemoSearchTool()` is therefore the production instance and is what the
  registry holds (DoD-11).
- **`name` is a `ClassVar[str]`, not a `@property` and not a field.** A `ClassVar` satisfies the
  protocol's read-only `name` property structurally (verified: mypy accepts the registry entry, and
  rejects it the moment `run` is renamed, so the structural check is live), it keeps `name` out of
  the generated `__init__`, and it needs no body — a `@property` would have had to either return the
  constant (behaviour this step does not own) or raise, which would break DoD-11's read of
  `.name`. Its value is `MEMO_SEARCH_NAME` imported from `definitions.py`, never the literal
  `"memo_search"` retyped.
- **`run`'s signature is copied from the protocol**: `async`, parameters `scope, connection,
  arguments` in that order, `arguments: Mapping[str, object]`, returning `ToolOutcome`. The two
  seam types are **string annotations** (`"ToolScope"`, `"ToolOutcome"`) because the runtime import
  is `TYPE_CHECKING`-only and `from __future__ import annotations` appears nowhere in `app/`.
- **`format_hits` returns `tuple[str, str]`, content first then summary** — the field order of
  `ToolOutcome(content, summary)`, so the coder's `ToolOutcome(*format_hits(hits))` reads right.
  Chosen over returning a `ToolOutcome` so the formatter stays importable and testable without the
  seam at all, which keeps the one runtime seam import confined to the body of `run` (below).
  `Sequence[SearchHit]` because the formatter only iterates in order and never mutates.

**How the import cycle is resolved, and the proof**

- `seam.py` imports the adapter at module level in the absolute form
  `from app.services.tools.memo_search import MemoSearchTool` (isort puts it right after
  `...tools.definitions`); the adapter imports **nothing from the seam at runtime**. `ToolScope`
  and `ToolOutcome` come in under `if TYPE_CHECKING:`, and the coder imports `ToolOutcome` **inside
  `run`** where it is constructed — the form `002.context.md` sanctions. Ruff selects only
  `E,F,I,B,UP,W`, so a function-local import is clean (no `PLC0415`); a module-bottom import would
  trip `E402`.
- Proof, both from `backend/` in fresh interpreters:
  `.venv/Scripts/python -c "import app.services.tools.memo_search"` → OK;
  `.venv/Scripts/python -c "import app.services.tools.seam"` → OK. Either entry order works
  because the adapter never re-enters the half-initialised `seam` module.

**Notes for the test-coder and the coder**

- The registry is live now, not a stub: `dict(seam.PRODUCTION_TOOL_REGISTRY)` is
  `{'memo_search': MemoSearchTool(client_factory=None, timeout_seconds=None)}`, its type is
  `mappingproxy`, `PRODUCTION_TOOL_REGISTRY['memo_search'].name == "memo_search"`, and item
  assignment raises `TypeError`. DoD-11's three facts are already observable against the stubs;
  only the two bodies raise.
- **DoD-14's "neither module imports `fastapi`" must be checked against the module *source* (AST or
  text), not `sys.modules`.** A `sys.modules` check fails for reasons that predate `026` and are
  outside this step's scope: `app/errors.py:22-23` imports the web framework, the seam imports
  `app.errors`, and `app/services/tools/__init__.py` imports the seam — so importing *any* module in
  the `app.services.tools` package (including `definitions.py`, as built) leaves it in
  `sys.modules`. Verified per-module in subprocesses. Neither of this step's two files contains the
  token anywhere, docstrings included (`grep -c` = 0 in both), so a source-level check passes and a
  text-based one cannot false-positive.
- Bodies are `raise NotImplementedError` — both of them. Nothing else in the module executes, so
  nothing can accidentally satisfy an assertion: `format_hits` produces no literal (`[<level>]
  <snippet>`, `No matching notes.`, `<N> memos` are all the coder's), and `run` reads no argument.
- Imports a **body** needs and the skeleton deliberately omits (`F401` is on, and none of them
  appears in a signature): `asyncio`, `search_memos` from `app.services.search.memo_search`,
  `ToolFailedError` from `app.errors`, and `ToolOutcome` from `app.services.tools.seam` (the
  function-local one). Keep the module-level block isort-clean (`I` is selected).
- `ToolFailedError` takes the tool name as `detail={"tool": MEMO_SEARCH_NAME}` — never positionally
  (021 `001`'s frozen record).
- A hit's level and text are `SearchHit.memo_scope` (`MemoScope | None`) and `SearchHit.snippet`
  (`str | None`) — both statically optional, so the formatter has to narrow them to keep mypy green;
  there is no bare `scope` field. `search_memos` never returns a non-memo hit, so the narrowing is a
  type-level obligation, not a behavioural branch to specify.
- `connection` is only passed through to `search_memos`; `run` issues no SQL itself, so the
  "no transaction left open" guarantee (DoD-10) is step `001`'s `finally`, not a second one here.
- `app/services/tools/__init__.py` is **not** touched and needs no entry: `seam.py` reaches the
  adapter by submodule path, which `__all__` does not govern (Ultra decision 5). `format_hits` and
  `MemoSearchTool` are imported as `from app.services.tools.memo_search import ...`.

## Tests

### Step 001 — tests (2026-10-05)

`backend/tests/test_memo_chain_clause.py` — **new**, 7 tests (DoD-1, 2, 3):

- `test_the_clause_with_a_setup_has_four_scope_terms_naming_the_four_ids__S026_001_DoD1` — DoD-1 —
  four `(scope, scope_id)` terms naming the four ids, in the SQLite-compiled `literal_binds` text.
- `test_the_clause_without_a_setup_has_exactly_three_terms_and_no_setup_term__S026_001_DoD1` — DoD-1 —
  exactly three terms, and neither `'setup'` nor the setup id appears at all.
- `test_the_clause_selects_exactly_the_four_chain_levels_notes__S026_001_DoD2` — DoD-2 — executed as a
  filter, exactly the four levels' notes.
- `test_the_clause_without_a_setup_selects_exactly_three_levels_notes__S026_001_DoD2` — DoD-2 — three
  levels only; the setup note is out.
- `test_the_clause_excludes_notes_outside_the_chain_of_the_same_user__S026_001_DoD2` — DoD-2 — another
  character, setup and session of the **same** user, as absences.
- `test_resolve_chain_with_a_setup_still_returns_the_four_levels__S026_001_DoD3` — DoD-3 — four levels
  in order, user level `scope_id` `None`, each holding its note.
- `test_resolve_chain_without_a_setup_still_returns_three_levels__S026_001_DoD3` — DoD-3 — three
  levels, no gap. (`tests/test_memo_chain_service.py`, 015's guard, is **not** edited — DoD-3's own
  requirement.)

`backend/tests/test_memo_search_service.py` — **new**, 17 tests (DoD-4..13):

- `test_the_predicate_names_is_enabled_before_is_forced__S026_001_DoD4` — DoD-4 — R3 order in the
  compiled text (position of `is_enabled` before `is_forced`).
- `test_the_predicate_keeps_only_enabled_unforced_notes_of_the_chain__S026_001_DoD4` — DoD-4 — the
  `is_forced` term negated, conjoined with `is_enabled`, and the chain disjunction ANDed in, proven
  over the four flag combinations plus an out-of-chain row.
- `test_the_result_count_constant_is_eight__S026_001_DoD5` — DoD-5 — `MEMO_SEARCH_LIMIT == 8` (the
  one place the literal `8` is written out).
- `test_a_with_setup_chain_returns_one_hit_at_each_of_the_four_levels__S026_001_DoD6` — DoD-6 — four
  hits, each `memo_scope` / `memo_scope_id` naming its level, the user level carrying A's own id.
- `test_a_no_setup_chain_returns_the_three_levels_and_raises_nothing__S026_001_DoD7` — DoD-7 — three
  hits, one per level, no gap.
- `test_a_no_setup_chain_reaches_no_setup_level_note__S026_001_DoD7` — DoD-7 — a setup-scoped note
  with the token is unreachable without a setup.
- `test_only_the_enabled_unforced_note_of_the_level_is_returned__S026_001_DoD8` — DoD-8 — forced,
  disabled and disabled-and-forced notes absent; the searchable one present.
- `test_the_forced_and_disabled_notes_texts_never_appear__S026_001_DoD8` — DoD-8 — the same, asserted
  through each excluded note's unique marker word.
- `test_another_users_notes_never_appear_in_the_callers_results__S026_001_DoD9` — DoD-9 — B's own
  user-level note and B's four `(scope, scope_id)` collisions with A's chain, absent.
- `test_another_users_note_texts_never_appear_in_the_callers_results__S026_001_DoD9` — DoD-9 — the
  same, by B's five marker words.
- `test_notes_outside_the_chain_are_absent__S026_001_DoD10` — DoD-10 — another session, character and
  setup of A, absent.
- `test_more_than_the_cap_of_matching_notes_yields_exactly_the_cap__S026_001_DoD11` — DoD-11 — eleven
  searchable matching notes in the chain, exactly `MEMO_SEARCH_LIMIT` hits.
- `test_no_designated_model_raises_no_embedding_model__S026_001_DoD12` — DoD-12 —
  `NoEmbeddingModelError` with `memo_fts` holding a match; no transaction in progress afterwards.
- `test_an_unreachable_provider_raises_llm_unreachable__S026_001_DoD12` — DoD-12 —
  `LlmUnreachableError` from the scripted fake; no transaction in progress afterwards.
- `test_a_successful_search_leaves_no_transaction_in_progress__S026_001_DoD12` — DoD-12 — the same
  guarantee on the ordinary exit.
- `test_the_memo_search_module_imports_no_web_framework__S026_001_DoD13` — DoD-13 — no `fastapi` /
  `starlette` import in the module source (AST over the text).
- `test_the_memo_search_module_imports_nothing_from_the_tools_package__S026_001_DoD13` — DoD-13 —
  nothing from `app.services.tools`.

`backend/tests/test_search_hybrid.py` — **025-owned, one amendment** (Ultra decision 4): added
`"memo_search.py"` to `SEARCH_PACKAGE_MODULES`, and renamed
`test_the_six_search_modules_are_all_present_to_scan__S025_004_DoD15` →
`test_the_seven_search_modules_are_all_present_to_scan__S025_004_DoD15` with its docstring and a
comment naming 026 step 001 as the cause. The `__S025_004_DoD15` tag is kept. The two sibling scans
(no `fastapi`/`starlette`, `sqlite_vec` only in `vector.py`) are left untouched and now also cover
`memo_search.py`. Nothing else in the file changed.

- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓ — all 13 `[test]` items; the step has no `[manual/live]`
  item.

### Step 002 — tests (2026-10-05)

`backend/tests/test_memo_search_tool.py` — **new**, 34 test functions / 41 collected cases
(DoD-1..14). Expected hit order comes
from calling `search_memos` with the same inputs (the one sanctioned exception, `002.context.md`);
the expected **lines** are D4 applied to those hits in the test file, never read out of
`format_hits` or `run`.

- `test_the_content_is_one_level_prefixed_line_per_hit__S026_002_DoD1` — DoD-1 — four notes → four
  `[<level>] <snippet>` lines, each equal to D4 applied to the corresponding hit.
- `test_each_content_line_names_its_own_level__S026_002_DoD1` — DoD-1 — every line's level literal
  is its note's level; all four levels are reached.
- `test_the_line_order_is_the_search_hit_order__S026_002_DoD1` — DoD-1 — the whole content equals
  D4 over `search_memos`' hits in their order.
- `test_the_formatter_renders_the_given_hits_in_order__S026_002_DoD1` — DoD-1 — `format_hits` over
  hand-built hits: `(content, summary)`, content first.
- `test_the_summary_counts_the_four_hits__S026_002_DoD2` — DoD-2 — exactly `4 memos`.
- `test_the_summary_of_one_hit_is_one_memos__S026_002_DoD2` — DoD-2 — exactly `1 memos`, not
  pluralised.
- `test_no_summary_carries_any_note_text__S026_002_DoD2` — DoD-2 — no marker, no body, not even the
  shared token appears in the summary.
- `test_a_single_hit_summary_carries_no_note_text__S026_002_DoD2` — DoD-2 — the same for one hit.
- `test_a_body_with_newlines_and_tabs_gives_one_content_line__S026_002_DoD3` — DoD-3 — a body with
  the token beside newlines and tabs → one line, no `\n`, no `\t`.
- `test_the_formatter_collapses_whitespace_runs_in_a_snippet__S026_002_DoD3` — DoD-3 — the pure
  formatter collapses runs and strips the ends.
- `test_a_chain_matching_nothing_returns_the_no_match_content__S026_002_DoD4` — DoD-4 — content
  exactly `No matching notes.`
- `test_a_chain_matching_nothing_summarises_zero_memos__S026_002_DoD4` — DoD-4 — summary exactly
  `0 memos`, nothing raised.
- `test_the_formatter_with_no_hits_says_no_matching_notes__S026_002_DoD4` — DoD-4 — the two literals
  over an empty sequence.
- `test_no_excluded_notes_text_reaches_the_content__S026_002_DoD5` — DoD-5 — forced, disabled,
  disabled-and-forced, B's colliding note and A's other-session note, each by its own marker.
- `test_the_searchable_notes_line_is_the_content__S026_002_DoD5` — DoD-5 — the searchable note's
  line is what appears.
- `test_a_scope_without_a_setup_gives_the_three_levels_lines__S026_002_DoD6` — DoD-6 — three lines,
  levels `user` / `character` / `session`, nothing raised.
- `test_a_scope_without_a_setup_reaches_no_setup_note__S026_002_DoD6` — DoD-6 — the setup-level note
  is absent, as an absence.
- `test_arguments_naming_another_user_change_nothing__S026_002_DoD7` — DoD-7 — arguments carrying
  B's ids, a `character_id`, a `setup_id` and a `scope` give identical content and summary.
- `test_nothing_of_another_user_appears_however_the_arguments_ask__S026_002_DoD7` — DoD-7 — B's
  markers absent, A's present.
- `test_arguments_without_a_string_query_raise_tool_failed__S026_002_DoD8` — DoD-8 — parametrised
  over `{}`, an int, `None` and a list `query`; `ToolFailedError` with `detail["tool"]`.
- `test_run_awaited_inside_a_running_loop_returns_hits__S026_002_DoD9` — DoD-9 — `run` awaited
  inside a coroutine passed to `asyncio.run`, still returning hits.
- `test_a_successful_run_leaves_no_transaction_in_progress__S026_002_DoD10` — DoD-10.
- `test_a_failed_run_leaves_no_transaction_in_progress__S026_002_DoD10` — DoD-10 — after
  `NoEmbeddingModelError` propagated.
- `test_the_production_registry_holds_exactly_memo_search__S026_002_DoD11` — DoD-11 — one entry,
  keyed `memo_search`, its value's `name` `memo_search`.
- `test_the_adapters_name_is_the_declared_name__S026_002_DoD11` — DoD-11.
- `test_offered_tools_over_the_production_registry_is_the_declaration__S026_002_DoD11` — DoD-11 —
  all three switches on → exactly `MEMO_SEARCH`, single parameter `query`.
- `test_offered_tools_with_the_memo_switch_off_offers_nothing__S026_002_DoD11` — DoD-11.
- `test_dispatch_with_no_designated_model_fails_the_tool_and_raises_nothing__S026_002_DoD12` —
  DoD-12 — through 021's real `dispatch` and `build_tool_scope`: a `ToolFailFrame` with tool
  `memo_search` and code `tool_failed`.
- `test_dispatch_with_no_designated_model_tells_the_model_the_tool_failed__S026_002_DoD12` — DoD-12
  — the tool message content is exactly `The tool failed. Continue without its result.`
- `test_dispatch_with_no_designated_model_writes_one_failed_tool_row__S026_002_DoD12` — DoD-12 —
  one tool row, `tool_name` `memo_search`.
- `test_dispatch_returns_a_tool_result_frame_summarising_the_hits__S026_002_DoD13` — DoD-13 —
  `ToolResultFrame` whose summary is `<N> memos`.
- `test_dispatch_gives_the_model_the_formatted_hits__S026_002_DoD13` — DoD-13 — the tool message
  content equals D4's content for those hits.
- `test_each_module_imports_cleanly_in_a_fresh_interpreter__S026_002_DoD14` — DoD-14 — parametrised
  over four subprocess cases (`sys.executable -c`, cwd `backend/`): each module alone, and both
  orders.
- `test_neither_module_imports_a_web_framework__S026_002_DoD14` — DoD-14 — an AST check over the two
  modules' **source** (not `sys.modules`: `app/errors.py` imports the framework and the seam imports
  `app.errors`, which predates 026).

**Amendments to 021's three test files (DoD-15).** Each amended test keeps its `__S021_…` tag and
carries a comment naming 026 step 002's registration as the cause; nothing else in those files
changed.

`backend/tests/test_tool_seam.py` (four sites, per Ultra decision 2):

- `test_the_production_registry_is_empty__S021_004_DoD2` → renamed
  `test_the_production_registry_holds_exactly_memo_search__S021_004_DoD2`; `len(...) == 1`,
  `list(...) == ["memo_search"]`.
- `test_the_production_registry_is_read_only__S021_004_DoD2` — the `pytest.raises(TypeError)` is
  **unchanged** (still a `MappingProxyType`); the trailing length is now `1`.
- `test_offered_tools_over_the_production_registry_is_empty__S021_004_DoD2` → renamed
  `..._is_memo_search__S021_004_DoD2`; all three switches on → `[MEMO_SEARCH]`, and the added
  other half: memo-search switch off → `[]`.
- `ALLOWED_SERVICE_MODULES` gained `"app.services.tools.memo_search"` (one entry suffices; the
  collector matches on `module` or `module.name`). The two sibling DoD-10 scans are untouched.

`backend/tests/test_compose_route.py` (one site plus the added other half):

- `test_the_production_registry_dependency_sends_an_empty_tools_list__S021_006_DoD10` → renamed
  `..._sends_the_memo_search_tool__S021_006_DoD10`; `tools == [dict(MEMO_SEARCH)]`. Added
  `from app.services.tools.definitions import MEMO_SEARCH` (was not imported).
- Added `test_the_production_registry_with_the_switch_off_sends_no_tools__S021_006_DoD10`: pops the
  registry override, raw-updates `sessions.tool_memo_search = False` for `SESSION_A` inline (with
  the already-imported `update` / `schema`, touching no other test's fixture), and asserts
  `tools == []`.

`backend/tests/test_compose_source.py` (one site, per Ultra decision 3):

- `test_the_production_registry_sends_an_empty_tools_list__S021_005_DoD13` → renamed
  `..._sends_the_memo_search_declaration__S021_005_DoD13`; `tools == [dict(MEMO_SEARCH)]` (the
  form already used at line 769) and the docstring's "empty registry" wording fixed. No new
  import.

- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓ (the amendments themselves),
  DoD-16 [manual/live, no test].
