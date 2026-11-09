# Feature 027 — session-search-tool

| Step | File                                   | Status  | Verifier | Date |
|------|----------------------------------------|---------|----------|------|
| 001  | `001.session-search-service.md`        | done    | PASS     | 2026-10-05 |
| 002  | `002.session-excerpts.md`              | done    | PASS     | 2026-10-05 |
| 003  | `003.session-search-tool-adapter.md`   | done    | PASS     | 2026-10-05 |

## Files Changed

### Step 001 — `search/session_search.py`: predicate, cap and `search_sessions`
- `backend/app/services/search/session_search.py` — filled `past_session_predicate` (D1's three conjoined terms over the port's base relation) and `search_sessions` (session scope + port call at `SESSION_SEARCH_LIMIT`, hits unchanged, `finally` rollback); step `002`'s stubs untouched

### Step 002 — `search/session_search.py`: the owner-scoped excerpt read
- `backend/app/services/search/session_search.py` — filled `list_session_excerpts` (empty input returns before any statement; two statements for any id-list length — the owner-scoped `sessions` ⟕ `setups` header select in `_session_select`'s join shape, then one `settled_entries` read for all found sessions ordered by `session_id, id`; input order restored from `session_ids`, foreign/unknown ids dropped silently) plus the module-private `_reading` (`sessions.py`'s rollback pattern, reproduced not imported), `_utc_date` (`fromisoformat` → naive-as-UTC → `.astimezone(UTC).date()`) and `_bounded_excerpt` (`…` + last `SESSION_EXCERPT_CHARS` characters); step `001`'s code and `SessionExcerpt`'s four frozen fields untouched

### Step 003 — `tools/session_search.py`: the adapter and the formatter
- `backend/app/services/tools/session_search.py` — filled `format_excerpts` (D3's blocks: `### Session <YYYY-MM-DD> · <setup: name|no setup>`, `\n`, excerpt or `(no settled entries)`, blocks joined by `\n\n`; `No matching sessions.` for no records; summary `<N> sessions`, never pluralised, never content) and `SessionSearchTool.run` (only `query` read and `isinstance` checked → `ToolFailedError(detail={"tool": SESSION_SEARCH_NAME})`; ids all from `ToolScope`, its `session_id` as `current_session_id`, `setup_id` unused; `client_factory`/`timeout_seconds` forwarded only when not `None`; one `asyncio.to_thread` call), plus the module-private `_search_and_hydrate` (the unfrozen worker-thread callable: `search_sessions` then `list_session_excerpts` on the hits' ids, sequentially on the handed connection)
- `backend/app/services/tools/seam.py` — not touched by the coder: the skeleton had already landed the registration, the import and the two reworded docstrings

## Notes & Issues

- Step 002: the step file's excerpt rule says "skip rows whose text is **empty**", while `context.md`
  D3 adds "the same joining 024 uses" and 024 drops whitespace-only parts too (`part.strip()`). No
  DoD covers a whitespace-only settled row, so the literal step-file rule was implemented: only `""`
  is skipped, a whitespace-only row is joined as stored. Worth a line in `003`/024 review if that
  divergence ever matters.

## Ultra phase

- orient: done 2026-10-05
- harvest: done — docs/.cache/ultra/027.session-search-tool/harvest.md (2 reports)
- skeleton: done — steps 001, 002, 003
- tests: done — steps 001, 002, 003 (approved deviations: step 001 amends `test_search_hybrid.py`'s
  module set seven → eight; step 003 amends `test_tool_seam.py` ×4, `test_compose_route.py` ×2 plus one
  added switch case, `test_memo_search_tool.py` ×3, `test_compose_source.py` ×1)
- red-gate: PASS (run 1) — 4061 collected, 4000 passed, 61 failed, **61/61 `NotImplementedError`**;
  zero failures outside the three new files; mypy clean (83 files); **ruff clean** on all three new
  test files and all five amendments (no test-coder had a shell this run, so the gate carried the
  lint risk — unlike 026, nothing was found). Step 001's `## Tests` header says 19 tests but lists
  and collects **18**; traceability is unaffected (all 13 `[test]` ids covered).
- code: done — steps 001, 002, 003 (no re-freeze, no escape valve)
- verify: PASS (run 1) — 4061 passed / 0 failed / 0 errored; mypy clean (83 files); ruff clean;
  frontend untouched so its gates were correctly not run; **2 `[manual/live]` outstanding**
  (003 DoD-16 "by meaning", 003 DoD-17 failure end to end)

### Orchestrator notes on the verified result (027)

- **The whitespace-only settled row is a known, adjudicated divergence, not a fault.** The step
  file says skip rows whose text is "empty" and the coder skipped exactly `""`; no `[test]` DoD
  seeds a whitespace-only row, so the implementation satisfies the clause as written. But
  `context.md` D3's own parenthetical says "the same joining 024 uses", and **024 drops
  whitespace-only parts** (`part.strip()`), so a strip-based rule is the better reading of the
  spec. Consequence to carry forward: such a row currently renders as a whitespace block body
  instead of `(no settled entries)`. The coder recorded it in `outcome.md` `## Observations`;
  its home is a 024-side fix or a later plan, **not** a 027 re-code.
- **Step 002's "a small fixed number of statements" is unpinned by any `[test]` DoD.** It holds
  (two statements for any id-list length, zero for empty input, verified by inspection), but
  nothing would catch a regression to one-query-per-id. Worth a `[test]` clause if a later plan
  revisits this read.
- **Record nit, uncorrected in its own section:** the `## Tests` header for step 001 says 19
  tests while its body lists and the file collects **18**. The test-coder owns that section, so I
  note the correction here rather than editing it. Traceability is unaffected.

### Orchestrator decisions at harvest (027)

The harvest swept the whole suite for what breaks when the production registry gains a second
entry and when `app/services/search/` gains an eighth module. The plan names three amendment
files; the sweep found **five**. Both additions are the same classes of miss 026 had.

1. **Step `003`'s Test files are extended by `backend/tests/test_compose_source.py`** — a third
   021-owned file. `test_the_production_registry_sends_the_memo_search_declaration__S021_005_DoD13`
   (`:1045`) asserts the real registry sends exactly `[dict(MEMO_SEARCH)]`; a second registration
   makes it false. Amend that one assertion to both declarations in `TOOL_DECLARATIONS` order, add
   `SESSION_SEARCH` to its import, and fix the docstring. Every other test in the file survives —
   the sweep confirmed its other production-registry call sites assert frames and rows, never
   `.tools`, and no fake client emits a `session_search` call, so the new adapter never runs there.
2. **Step `001`'s Test files are extended by `backend/tests/test_search_hybrid.py`** — 025-owned.
   `SEARCH_PACKAGE_MODULES` (`:219`) names seven files after 026; step `001` adds an eighth. Add
   `"session_search.py"` and rename "seven" → "eight". **Deliberate knock-on:** the two sibling
   scans iterate that tuple, so step `001`'s module must import neither `fastapi`/`starlette` nor
   `sqlite_vec`. 026's `memo_search.py` already satisfies both, so the mirrored pattern complies by
   construction.
3. **The switch matrix is wider than the plan's table implies.** 026 *added* a test asserting an
   empty tools list when the memo switch is off (`test_compose_route.py:910`). It flips only
   `tool_memo_search`, and both compose test files seed sessions with **all three switches on**, so
   with `session_search` registered that test receives `[dict(SESSION_SEARCH)]`, not `[]`. The same
   trap hits `test_memo_search_tool.py:989` and `test_tool_seam.py:369`'s second half. Each needs
   its off-case widened to switch both tools off, which is what 027's own amendment table intends.
4. **The seam's two stale docstrings are fixed as part of step `003`'s registry edit.**
   `ToolRegistry`'s says "the production one is empty in `021`" and the registry's own will be a
   feature out of date. 026's verifier flagged them and suggested exactly this. No test reads
   either string, and the edit is inside the one hunk 027 already owns.
5. **Carried from 026, unchanged:** the import-cycle form (seam names under `TYPE_CHECKING`,
   `ToolOutcome` imported inside the constructing function) is sanctioned and lint-clean — ruff
   selects no `PL*` rule, and a module-bottom import would trip `E402`. `app/services/tools/`'s
   `__init__.py` is **not** touched: `seam.py` reaches an adapter by submodule path, which
   `__all__` does not govern, and no test asserts `__all__`.

## Skeleton

### Step 001 — frozen interface (2026-10-05)

- `backend/app/services/search/session_search.py` — `SESSION_SEARCH_LIMIT: Final[int] = 5` — new
- `backend/app/services/search/session_search.py` — `SESSION_EXCERPT_CHARS: Final[int] = 1500` — new (declared here, consumed by step `002`)
- `backend/app/services/search/session_search.py` — `past_session_predicate(character_id: int, current_session_id: int) -> ExtraPredicateBuilder` — new
- `backend/app/services/search/session_search.py` — `search_sessions(connection: Connection, user_id: int, character_id: int, current_session_id: int, query_text: str, *, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> list[SearchHit]` — new
- Caller-compile edits (out of Source-files scope): None.

Bindings used: `ExtraPredicateBuilder`, `SearchHit`, `SessionSearchScope` from
`app.services.search.ports`; `search` from `app.services.search.hybrid`;
`LlmClient` (`app.services.llm.client`), `LlmClientFactory` (`app.services.llm_registry`),
`DEFAULT_EMBED_TIMEOUT_SECONDS` (`app.services.embedding`). `SessionSearchScope` and `search` are
the coder's body imports and are deliberately absent from the stub (`F401`).

Names left free for step `002` (not frozen here): the excerpt record and the excerpt read.

### Step 002 — frozen interface (2026-10-05)

- `backend/app/services/search/session_search.py` — `@dataclass(frozen=True) class SessionExcerpt` with exactly four required, defaultless fields in this order: `session_id: int`, `created_date: date`, `setup_name: str | None`, `excerpt: str` — new
- `backend/app/services/search/session_search.py` — `list_session_excerpts(connection: Connection, user_id: int, session_ids: Sequence[int]) -> list[SessionExcerpt]` — new
- `backend/app/services/search/session_search.py` — module docstring gained one sentence naming step `002`'s two additions; step `001`'s constants, `past_session_predicate`, `search_sessions` and their docstrings are byte-for-byte unchanged
- Caller-compile edits (out of Source-files scope): None.

Naming: `SessionExcerpt` + `list_session_excerpts` — the `list_*` verb is the project's convention
for an owner-scoped read returning a list (`list_character_sessions`, `list_entries`, `list_memos`),
and `SessionExcerpt` matches the frozen-dataclass-per-record form of `services/search/ports.py` and
`RpSession`. `search_*` was not reused: this is hydration, not a search. The field name
`created_date` deliberately differs from the stored `created_at` (a `str` everywhere else in `app/`)
to mark that this field is already parsed and already reduced to a calendar date.

`created_date` is `datetime.date`, not `datetime`: `sessions.created_at` is a `Text` column holding
aware ISO-8601 with an explicit `+00:00` offset and six fractional digits (harvest Part 1 Q4;
`sessions.py:_now_text`), nothing in `app/` parses any `sessions`/`messages` timestamp today, and D3
reduces the value to `<YYYY-MM-DD>` — so the reduction happens in this read and step `003`'s
formatter does no parsing and no time arithmetic. The coder's conversion is the established spelling
(`llm_registry.py:_parse_time`, `users.py`): `datetime.fromisoformat(stored)`, `replace(tzinfo=UTC)`
when naive, then `.astimezone(UTC).date()`.

`session_ids: Sequence[int]` — ordered (the records come back in input order), satisfied by a plain
`list[int]`, and it supports the `len`/iteration/indexing a one-statement `IN (:ids)` read plus an
order-restoring pass needs. Imports added for the signatures only: `Sequence`, `dataclass`, `date`.
The body's imports (`select`, `and_`, the three tables, `settled_entries`, `contextmanager`,
`Iterator`, `UTC`, `datetime`) are deliberately absent (`F401`), as are the locally reproduced
`_reading` helper and any private row-mapping helper — those are the coder's to add.

Names still free for step `003`: the adapter class and the formatter.

### Step 003 — frozen interface (2026-10-05)

- `backend/app/services/tools/session_search.py` — `format_excerpts(excerpts: Sequence[SessionExcerpt]) -> tuple[str, str]` — new (returns `(content, summary)`)
- `backend/app/services/tools/session_search.py` — `@dataclass(frozen=True, kw_only=True) class SessionSearchTool` with `client_factory: LlmClientFactory | None = None`, `timeout_seconds: float | None = None`, `name: ClassVar[str] = SESSION_SEARCH_NAME` — new
- `backend/app/services/tools/session_search.py` — `async def SessionSearchTool.run(self, scope: "ToolScope", connection: Connection, arguments: Mapping[str, object]) -> "ToolOutcome"` — new
- `backend/app/services/tools/seam.py` — `PRODUCTION_TOOL_REGISTRY: Final[ToolRegistry] = MappingProxyType({MEMO_SEARCH_NAME: MemoSearchTool(), SESSION_SEARCH_NAME: SessionSearchTool()})` — changed (was `MappingProxyType({MEMO_SEARCH_NAME: MemoSearchTool()})`); same name, same `Final[ToolRegistry]` annotation, still a `mappingproxy`, key order `memo_search`, `session_search`
- `backend/app/services/tools/seam.py` — `from app.services.tools.session_search import SessionSearchTool` — new module-level import, absolute form, beside the `memo_search` one
- `backend/app/services/tools/seam.py` — two stale docstrings reworded (orchestrator decision 4): `ToolRegistry`'s no longer claims the production mapping is empty, `PRODUCTION_TOOL_REGISTRY`'s now names both registered tools. No test reads either string; no other line of the seam changed (`dispatch`, `offered_tools`, `_switches`, `_NAMED_DECLARATIONS`, every literal are byte-for-byte as 026 left them).
- Caller-compile edits (out of Source-files scope): None. `definitions.py`, `app/services/tools/__init__.py` and `app/routers/stream.py` were read and need no change.

Naming: `SessionSearchTool` + `format_excerpts`, the 026 parallel (`MemoSearchTool` + `format_hits`).
`format_excerpts` rather than `format_hits`: the formatter's input is step `002`'s `SessionExcerpt`
records, not the port's `SearchHit`s, and the plural noun names what it is handed. The formatter
returns `tuple[str, str]` as `(content, summary)` — 026's precedent, and it keeps the runtime seam
import confined to `run`.

Shape mirrored from 026's adapter deliberately, so the two registry values are interchangeable in
shape: frozen `kw_only` dataclass, both injections `| None = None` meaning "let `search_sessions`'
own default win" (so `SessionSearchTool()` is the production instance, which is what the registry
holds — DoD-11), `name` a `ClassVar[str]` bound to `definitions.py`'s `SESSION_SEARCH_NAME` and not
a bare literal (so it reads off the class as well as off an instance), and `run`'s parameter names
and types identical to the `Tool` protocol's (`scope`, `connection`, `arguments: Mapping[str,
object]`). Protocol conformance is enforced statically by the registry literal's `Final[ToolRegistry]`
annotation and was additionally checked with an explicit `_t: Tool = SessionSearchTool()` under mypy.

The import cycle: 026's sanctioned form, unchanged. `ToolOutcome` and `ToolScope` come in under
`if TYPE_CHECKING:` and are used as **string** annotations; `ToolOutcome` is imported inside `run`,
where it is constructed (the coder keeps that import in the body). No `from __future__ import
annotations`. Ruff selects only `E,F,I,B,UP,W`, so the function-local import needs no `noqa`, and a
module-bottom import would have tripped `E402`. Proof the cycle is gone: fresh interpreters imported
`app.services.tools.session_search`, `...seam`, `...memo_search` and `app.services.tools` each
alone, plus seam→adapter, adapter→seam and memo→adapter→seam in one process; all succeeded.

**The worker-thread callable is deliberately NOT frozen.** `run` must make exactly one
`asyncio.to_thread` call that runs `search_sessions` and then `list_session_excerpts` sequentially,
but whether the sync callable is a module-private function or a closure inside `run` is invisible to
every test (DoD-9 pins the behaviour, not the form) and is the coder's decomposition — the same
reason 025 `004` left its private helpers unfrozen. Nothing may bind to its name.

Imports present are exactly the ones the signatures need: `Mapping`, `Sequence`, `dataclass`,
`TYPE_CHECKING`, `ClassVar`, `Connection`, `LlmClientFactory`, `SessionExcerpt` (from
`app.services.search.session_search`) and `SESSION_SEARCH_NAME`. The body-only imports are
deliberately absent (`F401`): `asyncio`, `typing.Any` (needed for the `injected: dict[str, Any]`
kwargs dict that `**`-expands past mypy), `ToolFailedError` (`app.errors`), and `search_sessions` /
`list_session_excerpts` from `app.services.search.session_search`.

Behaviour left unimplemented, per the plan: both bodies `raise NotImplementedError`. No block
format, no `(no settled entries)`, no `No matching sessions.`, no `<N> sessions`, no argument
reading, no `ToolFailedError`, no `to_thread` call exists yet. The registry entry, by contrast, is
real and live.

Gates: `.venv/Scripts/python -m mypy app` → clean (83 files); `.venv/Scripts/python -m ruff check .`
→ clean. pytest not run (skeleton phase).

## Tests

### Step 001 — tests (2026-10-05)

New file `backend/tests/test_session_search_service.py` — 19 tests, all named `__S027_001_DoD<n>`:

- `test_the_result_cap_and_excerpt_length_constants` — DoD-1 — the two constants are the spec's `5` and `1500`
- `test_the_predicate_compiles_to_the_three_conjoined_terms` — DoD-2 — the SQLite-compiled, literal-bound text names `character_id`, both ids, `archived_at` and a null test, conjoined
- `test_the_predicate_keeps_only_the_characters_other_unarchived_sessions` — DoD-2 — the three terms' semantics, selected with the clause alone (no `user_id` term of its own)
- `test_a_past_session_is_the_first_hit_for_its_composed_text` — DoD-3 — P first for a query equal to its composed text; kind `session`, id P, snippet/memo fields `None`
- `test_another_characters_identical_session_is_absent` — DoD-4 — identical-text twin under A's second character absent, P present
- `test_another_users_identical_session_is_absent` — DoD-5 — identical-text session under B's own character absent, P present
- `test_the_current_session_is_absent_even_when_identical` — DoD-6 — the current session absent though its composed text equals P's
- `test_an_archived_session_is_absent_until_it_is_restored` — DoD-7 — archived twin absent, then returned after a raw `archived_at` clear with no re-embed
- `test_a_session_whose_setup_is_archived_is_returned` — DoD-8 — an archived setup does not hide its working session
- `test_a_setupless_past_session_is_found_from_a_setupless_current_one` — DoD-9 — neither session has a setup; P is returned and nothing raises
- `test_sessions_carry_no_partner_column_to_search_on` — DoD-9 — `sessions` has no partner column
- `test_a_session_with_no_entries_is_found_by_its_persona` — DoD-10 — Q (persona only) returned and ahead of R, whose entry text differs; no paraphrase claim
- `test_seven_in_scope_sessions_yield_exactly_the_capped_number` — DoD-11 — exactly `SESSION_SEARCH_LIMIT` hits, all from the seven
- `test_no_designated_model_raises_no_embedding_model` — DoD-12 — vectors seeded while designated, designation then removed; `NoEmbeddingModelError`, no transaction open
- `test_an_unreachable_provider_raises_llm_unreachable` — DoD-12 — scripted fake raises; `LlmUnreachableError`, no transaction open
- `test_a_successful_search_leaves_no_transaction_in_progress` — DoD-12 — the guarantee on the ordinary exit
- `test_the_session_search_module_imports_no_web_framework` — DoD-13 — no `fastapi` / `starlette`
- `test_the_session_search_module_imports_nothing_from_the_tools_package` — DoD-13 — nothing from `app.services.tools`

Amendment (orchestrator decision 2), `backend/tests/test_search_hybrid.py` — 025-owned, one amendment only:
`SEARCH_PACKAGE_MODULES` gains `"session_search.py"` (eighth entry, comment updated), and
`test_the_seven_search_modules_are_all_present_to_scan__S025_004_DoD15` is renamed
`test_the_eight_search_modules_are_all_present_to_scan__S025_004_DoD15` with "eight, not seven" in its
docstring; the `__S025_004_DoD15` tag is kept and the trailing comment notes 027 step 001 added the
eighth. The two sibling scans (`fastapi`/`starlette`, `sqlite_vec`) are untouched and now also cover
`session_search.py` deliberately. Nothing else in that file changed.

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓,
DoD-11 ✓, DoD-12 ✓, DoD-13 ✓. No `[manual/live]` items in step 001.

### Step 002 — tests (2026-10-05)

New file `backend/tests/test_session_search_excerpts.py` — 20 tests, all named `__S027_002_DoD<n>`,
bound to `SessionExcerpt` / `list_session_excerpts` as frozen in "Step 002 — frozen interface":

- `test_the_records_come_back_in_the_requested_id_order` — DoD-1 — `[Z, X, Y]` in, `[Z, X, Y]` out,
  each record paired with its own excerpt; ascending-id order (`X, Y, Z`) and ascending-creation
  order (`Y, Z, X`) are deliberately two other permutations
- `test_another_users_session_id_is_dropped` — DoD-2 — A's id plus B's, read for A, gives A's only
- `test_the_other_user_gets_nothing_for_as_session_id` — DoD-2 — the read for B given A's id is `[]`
- `test_an_id_matching_no_session_is_dropped_silently` — DoD-2 — an unseeded snowflake-sized id is
  dropped and A's three records stay intact and in order
- `test_an_empty_id_list_gives_an_empty_result` — DoD-2 — empty input gives `[]`
- `test_the_setup_name_is_returned_for_a_session_with_a_setup` — DoD-3 — `Harbour Night`
- `test_a_setupless_session_reports_no_setup_name` — DoD-3 — `setup_name is None`, record still made
- `test_the_creation_date_is_the_utc_calendar_date` — DoD-3 — `2026-03-14T23:30:00.000000+00:00`
  (the stored form `sessions.py:_now_text` writes) gives `date(2026, 3, 14)`
- `test_a_naive_created_at_is_taken_as_utc` — DoD-3 — an offsetless stored value still parses to
  that same date (the Interface intent's naive rule)
- `test_an_archived_setups_name_is_still_returned` — DoD-4 — an archived setup still names itself (R6)
- `test_the_excerpt_is_the_settled_texts_in_id_order` — DoD-5 — turn, **decision**, turn joined by
  `"\n\n"` in id order; the decision's text is in, the interleaved `settled_at`-null row's is out
- `test_a_settled_row_with_empty_text_adds_no_separator` — DoD-5 — adding an empty settled row leaves
  the excerpt byte-identical
- `test_a_joined_text_of_exactly_1500_is_unchanged` — DoD-6 — 749 + `"\n\n"` + 749 returns unchanged,
  no marker, length 1500
- `test_a_joined_text_of_1501_is_marked_and_tail_cut` — DoD-6 — 749 + `"\n\n"` + 750 gives
  `"…" + joined[-1500:]`, 1501 characters in all
- `test_a_long_session_keeps_only_its_marked_tail` — DoD-6 — a 4056-character joined text starts with
  `…`, ends with the last entry, and has lost the marker word placed only in the first entry
- `test_a_session_with_no_settled_rows_gets_an_empty_excerpt` — DoD-7 — excerpt `""` (the
  `(no settled entries)` substitution is step `003`'s, not asserted here)
- `test_an_edited_settled_row_shows_its_new_text` — DoD-8 — after a raw `messages` update the new text
  is returned and the old is absent; the re-embed half is 024's and is not tested
- `test_a_read_leaves_no_transaction_in_progress` — DoD-9 — ordinary exit, plus a later `begin()`
- `test_the_empty_input_read_leaves_no_transaction_in_progress` — DoD-9 — the empty-input case
- `test_neither_the_persona_nor_the_setup_description_leaks` — DoD-10 — `dataclasses.fields` sweep of
  all four fields; neither the persona marker nor the description marker appears in any of them

Mechanics: the shared `db_engine` fixture (a `tmp_path` SQLite file; `conftest.py` and `llm_fakes.py`
untouched), a file-local `engine` fixture doing `schema.metadata.create_all` plus two users and three
characters, file-local raw-insert helpers (`_insert_user`, `_insert_character`, `_insert_setup`,
`_insert_session(created_at=…)`, `_insert_message(kind=…, text=…, settled_at=…)`, `_settled`, `_zone`),
ids above 2^60. No vectors, no designated model and no embedder — the read is plain SQL. DoD-6's
expected tails are sliced from the seeded entry strings rejoined with the spec's `"\n\n"`, never read
back from the code. No amendment to any delivered file.

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓.
No `[manual/live]` items in step 002.

### Step 003 — tests (2026-10-05)

New file `backend/tests/test_session_search_tool.py` — 33 test functions, 40 collected cases (three
are parametrised: DoD-8 ×4 argument shapes, DoD-14 ×4 import orders and ×2 modules), all named
`__S027_003_DoD<n>`, bound to `format_excerpts` / `SessionSearchTool` as frozen in "Step 003 —
frozen interface". Nothing binds to the unfrozen worker-thread callable.

- `test_the_content_is_one_block_per_hit_in_hit_order` — DoD-1 — content equals D3's blocks for
  `search_sessions`' hits, joined by `\n\n`
- `test_the_block_order_equals_the_search_hit_order` — DoD-1 — the header lines in content order
  are the hit sessions' headers in hit order
- `test_each_seeded_session_contributes_its_own_block` — DoD-1 — the `setup: Harbour Night` form,
  the `no setup` form and the `(no settled entries)` body all appear
- `test_the_formatter_renders_the_given_records_in_order` — DoD-1 — `format_excerpts` over three
  hand-built `SessionExcerpt` records
- `test_a_long_sessions_body_is_marked_and_exactly_1501_characters` — DoD-2 — single in-scope past
  session, body starts with `…` and is 1501 characters
- `test_the_summary_counts_the_three_hits` / `..._of_one_hit_is_one_sessions` — DoD-3 —
  `3 sessions` and `1 sessions`, not pluralised
- `test_no_summary_carries_any_entry_text_or_the_token` / `test_a_single_hit_summary_carries_no_entry_text_or_token` — DoD-3
- `test_neither_the_persona_nor_the_setup_description_reaches_the_content` — DoD-4 — the two marker
  words are absent
- `test_no_seeded_id_appears_in_the_content` — DoD-4 — no decimal id string (all ids above 2^60)
- `test_no_in_scope_session_gives_the_zero_hit_content` / `..._summarises_zero_sessions` /
  `test_the_formatter_with_no_records_says_no_matching_sessions` — DoD-5 — `No matching sessions.`
  and `0 sessions`, nothing raised
- `test_no_excluded_sessions_marker_reaches_the_content` — DoD-6 — none of the four markers appears
- `test_only_the_in_scope_past_sessions_block_comes_back` — DoD-6 — the content is exactly P's
  block and the summary is `1 sessions`
- `test_arguments_naming_other_ids_change_nothing` / `test_nothing_of_the_other_user_appears_however_the_arguments_ask` — DoD-7
- `test_arguments_without_a_string_query_raise_tool_failed` — DoD-8 — `{}`, `7`, `None`, `[…]`;
  `detail["tool"] == "session_search"`
- `test_run_awaited_inside_a_running_loop_returns_blocks` — DoD-9 — awaited inside the test's own
  coroutine under `asyncio.run`
- `test_a_successful_run_leaves_no_transaction_in_progress` / `test_a_failed_run_leaves_no_transaction_in_progress` — DoD-10
- `test_the_production_registry_holds_the_two_tools` /
  `test_the_registered_session_search_value_names_itself` /
  `test_offered_tools_over_the_production_registry_is_both_declarations` /
  `test_offered_tools_with_the_session_switch_off_is_memo_search_alone` — DoD-11
- three `test_dispatch_with_no_designated_model_*` — DoD-12 — frame, message content, one failed
  tool row through 021's real `dispatch`
- `test_dispatch_returns_a_tool_result_frame_summarising_the_hits` /
  `test_dispatch_gives_the_model_the_formatted_blocks` — DoD-13
- `test_each_module_imports_cleanly_in_a_fresh_interpreter` (subprocess, four orders) /
  `test_neither_module_imports_a_web_framework` (source/AST check, not `sys.modules`) — DoD-14

Mechanics: the shared `db_engine` fixture (a `tmp_path` SQLite file; `conftest.py` and
`llm_fakes.py` untouched), a file-local `engine` fixture (`create_all`, two users, three characters
sharing one persona, three setups sharing one description), file-local raw-insert helpers, ids above
2^60, dimension 8, a raw `llm_servers` + `models` designation, `session_vec` built only through
024's `refresh_session_vectors` with the fake factory, the port never mocked and nothing
monkeypatched. Queries are a session's exact composed text from 024's `compose_session_text`; hit
order comes from step `001`'s `search_sessions`; blocks are D3 applied here to the seeded rows. No
test claims a paraphrase finds a session (DoD-16's `[manual/live]` business).

Amendments (DoD-15), four files, only at the assertions the second registration makes false; every
other test in them is untouched, each original tag kept and `S027_003_DoD15` noted beside it:

- `backend/tests/test_tool_seam.py` (021) — `..._holds_exactly_memo_search__S021_004_DoD2` renamed
  `..._holds_the_two_registered_tools...`, `len == 2`, `list == ["memo_search", "session_search"]`;
  `..._is_read_only...`'s trailing `len` is `2` (the `pytest.raises(TypeError)` untouched);
  `..._is_memo_search__S021_004_DoD2` renamed `..._is_the_switched_on_subset...` and widened to the
  three-case matrix (all on → `[MEMO_SEARCH, SESSION_SEARCH]`; `memo=False` → `[SESSION_SEARCH]`;
  both off → `[]`); `ALLOWED_SERVICE_MODULES` gains `"app.services.tools.session_search"`.
- `backend/tests/test_compose_route.py` (021) — `..._sends_the_memo_search_tool__S021_006_DoD10`
  renamed `..._sends_both_registered_tools...` and asserts
  `[dict(MEMO_SEARCH), dict(SESSION_SEARCH)]`; the switch-off test now flips **both**
  `tool_memo_search` and `tool_session_search` to keep `tools == []` (renamed accordingly); a third
  case was added that flips only `tool_session_search`, giving `[dict(MEMO_SEARCH)]`.
  `SESSION_SEARCH` added to the `definitions` import.
- `backend/tests/test_memo_search_tool.py` (026) — the exactness claims dropped, per 027's own
  amendment table: `..._holds_exactly_memo_search__S026_002_DoD11` renamed `..._holds_memo_search...`
  and now asserts the key is present and its value's `name` is `memo_search`;
  `..._is_the_declaration...` renamed `..._includes_the_declaration...` (the `function["name"]` /
  `properties` / `required` assertions byte-for-byte unchanged); `..._with_the_memo_switch_off...`
  renamed `..._with_the_tool_switches_off...` and widened to `memo=False, session=False`. No
  `memo_search` value check was weakened.
- `backend/tests/test_compose_source.py` (021, orchestrator decision 1 — the plan missed it) —
  `..._sends_the_memo_search_declaration__S021_005_DoD13` renamed
  `..._sends_both_registered_declarations...`, asserts
  `[dict(MEMO_SEARCH), dict(SESSION_SEARCH)]`, docstring reworded, `SESSION_SEARCH` added to the
  `definitions` import.

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓ (the four amendments above),
DoD-16 [manual/live, no test], DoD-17 [manual/live, no test].

Note on DoD-6's "identical composed text **and** a unique marker": the two cannot both hold, so each
excluded session was given P's persona, P's setup description and P's two settled entries with one
marker word appended to the second entry — the marker is the only difference, and absence is
asserted by marker. The "would match" premise is additionally defended by the scenario holding
exactly one in-scope past session, so `1 sessions` shows no twin came back.
