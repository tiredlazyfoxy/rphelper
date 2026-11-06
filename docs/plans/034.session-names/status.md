# Feature 034 — session-names

| Step | File                              | Status  | Verifier | Date |
|------|-----------------------------------|---------|----------|------|
| 001  | `001.session-name-column.md`      | done    | PASS     | 2026-11-06 |
| 002  | `002.rename-route.md`             | done    | PASS     | 2026-11-06 |
| 003  | `003.my-search-names.md`          | done    | PASS     | 2026-11-06 |
| 004  | `004.session-label-surfaces.md`   | done    | PASS     | 2026-11-06 |
| 005  | `005.rename-editor.md`            | pending | —        | —    |
| 006  | `006.rename-surfaces.md`          | pending | —        | —    |

## Files Changed

### Step 001 — session-name-column
- `backend/app/db/schema.py` — nullable `sessions.name` column and doc comment (skeleton)
- `backend/app/models/sessions.py` — `SessionResponse.name`, nine-key docstrings
- `backend/app/services/sessions.py` — session select labels the setup name `setup_name` and selects `sessions.name`; `_to_session` maps both; `RpSession.name`
- `backend/app/routers/sessions.py` — docstrings only (nine keys)
- `backend/app/services/transfer.py` — `SCHEMA_VERSION` = 2
- `backend/app/services/transfer_import.py` — `validate_envelope` accepts schema version 2 or 1 (strict int) and passes the file's version; `_deserialize_payload` upgrades v1 `sessions` rows (`name` allowed missing, set to None); `_is_version` docstring
- `backend/app/errors.py` — `REASON_SCHEMA_MISMATCH` docstring

### Step 002 — rename-route
- `backend/app/models/sessions.py` — `_normalise_session_name` body (strip, blank → None, None passes)
- `backend/app/services/sessions.py` — `rename_session` body (normalise; one transaction: owner-scoped require incl. archived, write `name` + `updated_at`, re-read)
- `backend/app/routers/sessions.py` — no change beyond the skeleton (handler body was final)

### Step 003 — my-search-names
- `backend/app/services/search/my_search.py` — `search_session_names` body (strip, blank → [] with no SQL; owner-scoped, non-NULL, `_folded_contains` on `sessions.name`, archived included, name/id order, `limit`, inside `_reading`); `merge_session_hits` body (name ids, then unseen vector ids, capped); `run_my_search` calls the name arm after `search_setups` and hydrates the merged order; module docstring records the unnamed-session-by-date limitation
- `backend/app/models/search.py`, `backend/app/routers/search.py` — no change beyond the skeleton

### Step 004 — session-label-surfaces
- `frontend/src/app/sessionsApi.ts` — `renameSession` body (`apiPatch<Session>(sessionPath(id), { name }, signal)`), `apiPatch` import
- `frontend/src/app/sessionLabel.ts` — `sessionLabel` body (name, else `formatLocalDate`); `formatLocalDate` body (Intl `formatToParts`, local `YYYY-MM-DD`)
- `frontend/src/app/CharacterTree.tsx` — tree row label (line 1) uses `sessionLabel`; comments updated
- `frontend/src/app/SessionScreen.tsx` — header `Title` uses `sessionLabel`; comments updated
- `frontend/src/app/SessionsSection.tsx` — row label and `Actions for <label>` use `sessionLabel`; no rename control; comments updated
- `frontend/src/app/SearchScreen.tsx` — session row primary and entry row session text use `sessionLabel` (entry via `{ name: session_name, created_at: session_created_at }`)
- `frontend/src/app/searchApi.ts` — no change beyond the skeleton
- `frontend/src/app/characterComposerState.ts` — skeleton's caller-compile edit only (`name: started.name`); no coder change

## Notes & Issues

- Step 001: the frozen skeleton declares `RpSession.name` right after `setup_name` with **no default**, not last-with-default-None as DEC-034-6 states. Left as frozen; any test outside this step's list that constructs `RpSession` positionally or without `name` would break (none in `app/`).
- Step 002 (orchestrator, 2026-11-06): verify run found `backend/tests/test_configuration_router.py::test_patch_on_the_session_itself_still_answers_405__S017_005_DoD9` asserting 405 on `PATCH /api/sessions/{id}` — obsolete once step 002 adds the route (DoD-4 requires 422). The file was missing from step 002's Test files; the orchestrator widened step 002's test scope to that one test (step file not edited).

## Skeleton

### Step 001 — frozen interface (2026-11-06)
- `backend/app/db/schema.py` — `sessions` gains `Column("name", Text, nullable=True)` (last column, no default/index); doc comment updated — changed
- `backend/app/services/sessions.py` — `RpSession.name: str | None` (field placed after `setup_name`) — changed. STUB: `_to_session` sets `name=None` (coder must select `sessions.c.name` with a label distinct from the setup name, e.g. label setups' name `setup_name`, and read it); `_insert_session` result `name=None` is final behaviour.
- `backend/app/models/sessions.py` — `SessionResponse.name: str | None` (after `setup_name`; nine keys; `StartedSessionResponse` inherits) — changed
- `backend/app/routers/sessions.py` — `_to_response` unchanged (from_attributes copies `name`); docstrings only — changed
- `backend/app/services/transfer.py` — `SCHEMA_VERSION: Final[int] = 2` — changed (was 1)
- `backend/app/services/transfer_import.py` — `_deserialize_payload(payload: object, granularity: ExportGranularity, schema_version: int) -> dict[str, list[ImportRow]]` — changed (added `schema_version`). STUB: `validate_envelope` signature unchanged and still accepts only `SCHEMA_VERSION` (2), passing it through; coder must accept 1 or 2 (strict, no bool), pass the file's version, and in `_deserialize_payload` for version 1 treat `name` as allow_missing on `sessions` rows and inject `name: None`; update `_is_version` doc.
- `backend/app/errors.py` — `REASON_SCHEMA_MISMATCH` comment reworded (version 1 upgraded).
- Caller-compile edits (out of Source-files scope): None.

### Step 002 — frozen interface (2026-11-06)
- `backend/app/models/sessions.py` — `def _normalise_session_name(value: str | None) -> str | None` — new (STUB: raises `NotImplementedError`; coder: strip, blank → None, None passes)
- `backend/app/models/sessions.py` — `SessionNameIn = Annotated[str | None, AfterValidator(_normalise_session_name)]` — new
- `backend/app/models/sessions.py` — `class RenameSessionRequest(BaseModel)`: `model_config = ConfigDict(extra="forbid")` (comment cites DEC-034-2); `name: SessionNameIn` (required, no default, no length cap — `SetupName` has no max either, DEC-034-3) — new. Note: `extra="forbid"` and the required key are declarative, so the 422s of DoD-4/DoD-5 hold already on the stub.
- `backend/app/services/sessions.py` — `def rename_session(connection: Connection, user_id: int, session_id: int, name: str | None) -> RpSession` — new (STUB: raises `NotImplementedError`; placed before `_session_select`)
- `backend/app/routers/sessions.py` — `@router.patch("/api/sessions/{session_id}", status_code=200) def rename_own_session(session_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)], body: RenameSessionRequest) -> SessionResponse` — new; body already final (`return _to_response(rename_session(connection, current_user.id, session_id, body.name))`, the service stub throws). Module docstring: "No PATCH" paragraph replaced with the narrow-PATCH paragraph; route count six → seven. Verified: `route_operations(app)` lists `("PATCH", "/api/sessions/{}")`.
- Caller-compile edits (out of Source-files scope): None.

### Step 003 — frozen interface (2026-11-06)
- `backend/app/services/search/my_search.py` — `def search_session_names(connection: Connection, user_id: int, query_text: str, limit: int = MY_SEARCH_PER_KIND_LIMIT) -> list[int]` — new (STUB: raises `NotImplementedError`; placed after `MySearchResults`, before `_hydrate_sessions`)
- `backend/app/services/search/my_search.py` — `def merge_session_hits(name_ids: Sequence[int], vector_hits: Sequence[SearchHit], limit: int) -> list[int]` — new, pure (STUB: raises `NotImplementedError`)
- `backend/app/services/search/my_search.py` — `def _hydrate_sessions(connection: Connection, user_id: int, session_ids: Sequence[int]) -> list[SessionHit]` — changed (was `hits: Sequence[SearchHit]`); body final: reads `sessions.name` and keeps the ids' order.
- `backend/app/services/search/my_search.py` — `SessionHit` field order `id, character_name, setup_name, name: str | None, created_at, archived` — changed (`name` added after `setup_name`, no default). Final (data shape).
- `backend/app/services/search/my_search.py` — `EntryHit` field order `id, session_id, snippet, character_name, session_name: str | None, session_created_at` — changed (`session_name` added before `session_created_at`, no default); `_hydrate_entries` selects `sessions.name` labelled `session_name`. Final (data shape).
- `backend/app/services/search/my_search.py` — `run_my_search` signature unchanged. STUB state: body still runs the old path, only adapted mechanically to `_hydrate_sessions(connection, user_id, [hit.id for hit in session_hits])`; the coder must call `search_session_names(connection, user_id, query_text, MY_SEARCH_PER_KIND_LIMIT)` after `search_setups` (the vector session arm stays first, so fail-whole is unchanged) and hydrate `merge_session_hits(name_ids, session_hits, MY_SEARCH_PER_KIND_LIMIT)`. Docstrings (module, `run_my_search`, `MySearchResults.sessions`) already describe the target contract.
- `backend/app/models/search.py` — `SessionHitResponse` gains `name: str | None` (after `setup_name`); `EntryHitResponse` gains `session_name: str | None` (after `character_name`) — changed, final.
- `backend/app/routers/search.py` — no change (`_to_response` converts via `from_attributes`, so the new fields flow through).
- Caller-compile edits (out of Source-files scope): None.

### Step 004 — frozen interface (2026-11-06)
- `frontend/src/app/sessionsApi.ts` — `Session` gains `name: string | null` (required key, after `setup_name`; nine keys) — changed, final. `toSession` copies `name` — final. Header comment now "one update call (rename), no delete"; "eight keys" doc mentions → nine.
- `frontend/src/app/sessionsApi.ts` — `export async function renameSession(sessionId: string, name: string | null, signal?: AbortSignal): Promise<Session>` — new (STUB: throws `Error("not implemented")`; placed before `archiveSession`). Coder: `return apiPatch<Session>(sessionPath(sessionId), { name }, signal);` and add `apiPatch` to the `../shared/api` import (left out of the stub because `noUnusedLocals` rejects an unused import).
- `frontend/src/app/sessionLabel.ts` — `export type SessionLabelSource = { name: string | null; created_at: string }` — new, final.
- `frontend/src/app/sessionLabel.ts` — `export function sessionLabel(source: SessionLabelSource, timeZone?: string): string` — new (STUB: throws). An `EntryHit` is labelled by passing `{ name: hit.session_name, created_at: hit.session_created_at }`.
- `frontend/src/app/sessionLabel.ts` — `export function formatLocalDate(timestamp: string, timeZone?: string): string` — new, the label's local `YYYY-MM-DD` fallback (STUB: throws).
- `frontend/src/app/sessionLabel.ts` — `export function formatLocalDateTime(createdAt: string, timeZone?: string): string` — changed (was `formatSessionStart(createdAt: string, timeZone?: string): string`); body unchanged, already final.
- `frontend/src/app/searchApi.ts` — `SessionHit` gains `name: string | null` (after `setup_name`); `EntryHit` gains `session_name: string | null` (before `session_created_at`) — changed, final.
- `CharacterTree.tsx`, `SessionScreen.tsx`, `SessionsSection.tsx`, `SearchScreen.tsx` — STUB STATE: import and call sites only renamed mechanically to `formatLocalDateTime(...)`; they still show the start date-time. The **call-site switch to `sessionLabel` is the coder's** (tree row label :299, header `Title` :217, Sessions row `label` :179 incl. `Actions for ${label}`, search session primary :282, entry secondary :302). It was not wired because `sessionLabel` throws and would crash every existing render test. After the switch, these four files should no longer import `formatLocalDateTime` (step 006 brings it back in the tree's line 2).
- Caller-compile edits (out of Source-files scope): `frontend/src/app/characterComposerState.ts` (~:130) — the explicit `Session` literal built from `startSessionWithMessage`'s result gains `name: started.name` and its comment reads "nine" keys. This is a mechanical change: without it the `src` typecheck fails.
- Typecheck (`npm run typecheck`): `src` is clean. 43 errors remain, all in this step's listed Test files: `Session` fixture literals are missing `name`, `SessionHit`/`EntryHit` fixtures are missing `name`/`session_name`, and `SearchScreen.test.tsx` and `sessionLabel.test.ts` still import `formatSessionStart`. Only the test-coder can fix these. No unlisted test file is flagged.

## Tests

### Step 001 — tests (2026-11-06)
- `backend/tests/test_db_schema.py` — covers DoD-1 — `sessions.name` is nullable Text with no default, index or FK, and reads NULL when an insert omits it; the exact column sets now include `name` (17 columns).
- `backend/tests/test_sessions_router.py` — covers DoD-2, DoD-3, DoD-4 — the nine-key wire shape; `name` is null on start, create-and-seed, list, per-character list, get, archive and restore; a body `name` is ignored; a stored name reads back exactly on every route.
- `backend/tests/test_sessions_service.py` — covers DoD-2, DoD-3, DoD-4 — `RpSession.name` is None from start, start_seeded and every read; a stored name reads back with `setup_name` intact; names are per session.
- `backend/tests/test_sessions_models.py` — covers DoD-2, DoD-3, DoD-4 — `name` is declared on `SessionResponse` and `StartedSessionResponse`; null and stored values pass through; `StartSessionRequest` ignores `name`.
- `backend/tests/test_sessions_capture.py` — covers DoD-2 — `RpSession` has the nine fields (compared as a set) and a captured session's `name` is None.
- `backend/tests/test_configuration_router.py` — covers DoD-2 — the session key set includes `name`.
- `backend/tests/test_transfer_core.py`, `test_transfer_router.py`, `test_transfer_selections.py`, `test_admin_db_export.py` — cover DoD-5 — `SCHEMA_VERSION` is 2; every granularity (and the admin route) emits 2; every session row carries `name`, stored or null.
- `backend/tests/test_transfer_import_validation.py` — covers DoD-7, DoD-8, DoD-9, DoD-10 — v1 validates at every granularity with `name` None; v1 with any other missing or extra column, or with a session row carrying `name`, is malformed; the users allowance is unchanged; v2 without `name` is malformed; 0, 3, a string or a bool is `schema_mismatch`.
- `backend/tests/test_transfer_import_session.py` — covers DoD-6, DoD-7, DoD-8, DoD-9, DoD-10 — the session import round-trips a name; a v1 file imports with NULL; the refusals store nothing.
- `backend/tests/test_transfer_import_owned.py` — covers DoD-6, DoD-7, DoD-8, DoD-9 — user and character imports keep names; v1 imports give NULL names and keep every other column; the refusals store nothing.
- `backend/tests/test_transfer_import_database.py` — covers DoD-6, DoD-7, DoD-8, DoD-9, DoD-10 — the database replace keeps a name; v1 replaces with NULL names (also onto a blank db); malformed and mismatch refusals change nothing.
- `backend/tests/test_transfer_import_router.py` — covers DoD-6, DoD-7, DoD-8, DoD-9 — end to end through both roleplayer import routes: names kept, v1 gives null, column violations give `malformed_payload`.
- `backend/tests/test_admin_db_import.py` — covers DoD-6, DoD-7 — the admin replace route keeps a name; a v1 file gives NULL.
- `backend/tests/test_bootstrap_import.py` — covers DoD-6, DoD-7, DoD-8 — bootstrap from a v1 file gives NULL names; from a v2 file it keeps the name; a v1 session row carrying `name` is refused and the instance stays unconfigured.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓

### Step 002 — tests (2026-11-06)
- `backend/tests/test_sessions_router.py` — covers DoD-1..DoD-9, DoD-11 — `PATCH /api/sessions/{id}`: trimmed name answered (200, nine keys, other keys unchanged) and read back on get + both lists; `""`/whitespace/`null` clear to null (stored NULL); `updated_at` advances, stored `last_used_at` byte-identical, both list orders unchanged; extra keys (alone or with `name`) and `{}`/non-object/`null` bodies/non-string names are 422 with the row unchanged; foreign id 404 `session_not_found` identical to unknown id, foreign row unchanged; `abc` 422; archived session renamable and stays archived; duplicate names allowed; no provider client built with and without a designated embedding model; anonymous 401. 011 DoD-13's "PATCH answers 405" clause replaced (that body is now 422, DoD-4).
- `backend/tests/test_sessions_service.py` — covers DoD-3, DoD-6, DoD-7, DoD-8, DoD-10 — `rename_session` stores trimmed / NULL-for-blank / NULL-for-None, returns the re-read session; `updated_at` advances, `last_used_at` and order unchanged; foreign and unknown ids raise `SessionNotFoundError` with the foreign row unchanged; archived allowed; same name twice.
- `backend/tests/test_sessions_models.py` — covers DoD-1, DoD-2, DoD-4, DoD-5 — `RenameSessionRequest` has exactly `name`; trims, keeps inner text, no length cap; blank/null -> None; any other key, a missing key, a non-object body and a non-string `name` raise `ValidationError` (dict and raw JSON).
- `backend/tests/privacy_audit_support.py` — supports DoD-11, DoD-12 — `_CARRIER_ROWS` gains `("sessions", "name", "sessname", ...)` (the stale "no content text column" note reworded); `ENUMERATED_ROUTES` gains row 76 `PATCH /api/sessions/{}` owner / `session_not_found` (appended, no row renumbered); the world seeds A's and B's `session_with_setup_id` name **through the rename route**, so every privacy-audit world build depends on the route.
- `backend/tests/test_privacy_audit_routes.py` — covers DoD-11, DoD-12 — row count 76 and two-way equality; row 76 classified owner/`session_not_found`; anonymous rename 401 with empty detail (unknown id and B's real id); `("sessions", "name")` read surface = the single-session read (positive control + stored check).
- `backend/tests/test_privacy_audit_owner_sweep.py` — covers DoD-6, DoD-12 — 37 owner rows, row 76 swept by A and ADM with B's id; B's session name unchanged; A's lists/read carry A's session name and never B's.
- `backend/tests/test_privacy_audit_logs.py` — covers DoD-12 — row 76 driven as A with A's session-name sentinel (50 driven rows); foreign rename and a 422 rename carrying the sentinel log nothing; world build (which renames) swept on the console.
- `backend/tests/test_privacy_audit_export_import.py` — covers DoD-12 — each user's export carries their own session name and never the other's.
- `backend/tests/test_configuration_router.py` — covers DoD-4 (Test files widened by the orchestrator after verify) — 017 DoD-9's "PATCH on the session itself answers 405" replaced: a `system_prompt` body now answers 422 and the session configuration is unchanged (renamed `test_patch_on_the_session_itself_cannot_write_configuration__S017_005_DoD9__S034_002_DoD4`).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓

### Step 003 — tests (2026-11-06)
- `backend/tests/test_my_search_service.py` — covers DoD-1..DoD-9 — `search_session_names`: substring in any case, Latin and Cyrillic; NULL names never matched and a start-date query finds only a stored date-like name; owner-scoped (B's same-named session); `%`/`_` literal; blank query `[]` with zero SQL statements; name-then-id order; default cap 20 and explicit limit. `merge_session_hits` (pure): name ids first, unmatched vector hits in given order, a both-matched id once in name position, empty arms, cap 20 incl. overlap, smaller limit. `run_my_search`: name-only sessions (no vector) reach the group; merged order = name order + port order (port called as oracle); 15+10 → 20; 25 names → 20 names; blank query five empty groups with no SQL and no model; vector-arm failure (no model, dimension mismatch, unreachable) raises although the name arm matched; `SessionHit` field order with `name`, full equality with `name` for a name hit and a vector hit, `EntryHit.session_name` next to `session_created_at`; archived named session returned with `archived=True`. Existing 029 tests updated: `SessionHit(...)` gains `name=None`, `EntryHit` field list gains `session_name` (renamed `..._six_fields__S029_002_DoD6__S034_003_DoD8`), entry hit `session_name is None`.
- `backend/tests/test_search_router.py` — covers DoD-1, DoD-3, DoD-4, DoD-5, DoD-7, DoD-8, DoD-9 — wire: `SESSION_HIT_KEYS` gains `name`, `ENTRY_HIT_KEYS` gains `session_name` (key-set test renamed `..._S029_003_DoD3__S034_003_DoD8`), expected 029 rows carry null; named session found by mixed-case Latin / Cyrillic substring; a name set through `PATCH /api/sessions/{id}` is found, leads the group, full row with `name`; B's same-named session absent from A's body (and vice versa); `%`/`_` literal; blank `q` five empty groups with named sessions present; 409 / 502 fail-whole although a name matched; renamed session's entry hit carries `session_name` + unchanged `session_created_at`, its session hit `name`, others null; archived named session `archived: true`.
- `backend/tests/test_privacy_audit_routes.py` — covers DoD-11 — `FURTHER_READ_SURFACES_OF_CARRIER` lists `/api/search` (`search_session_name` surface, queried with B's own session-name sentinel) as a reader of `sessions.name`, checked in the 032 DoD-5 positive control; dedicated test: B's search for B's sentinel returns B's renamed session first with the name, nothing of A's.
- `backend/tests/test_privacy_audit_search_tools.py` — covers DoD-10, DoD-11 — DoD-1 sweep gains the `sessions.name` target (22 targets); new world test: a search for the shared name stem returns each user's own renamed session with its name and no sentinel/id of the other; the `session_search` tool run in B's other session returns B's renamed session (positive control) and its output carries neither the sentinel nor the full name.
- `backend/tests/test_session_search_excerpts.py` — covers DoD-10 — a renamed session's `SessionExcerpt` still has exactly four fields and no field carries the name (guard).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓

### Step 004 — tests (2026-11-06)
- `frontend/tests/app/sessionLabel.test.ts` — covers DoD-1, DoD-2, DoD-3 — 011 clauses now call `formatLocalDateTime` (values unchanged); `sessionLabel` returns a non-null name verbatim (plain, date-like, date-time-like, Cyrillic, no zone); null name → local `YYYY-MM-DD` of `created_at` (`2026-11-05T23:30:00Z` Berlin → `2026-11-06`, UTC → `2026-11-05`, New York rolls back, Tokyo), date-only shape / length 10 / no `:` in four zones, zone-less = resolved zone, extra keys ignored, `formatLocalDate` agrees; `formatLocalDateTime` zero-padded, 24-hour, midnight `00`, exactly 16 characters.
- `frontend/tests/app/sessionsApi.test.ts` — covers DoD-4, DoD-5 — fixtures gain `name`; `SESSION_KEYS` is nine keys (018 clauses retitled nine/ten); every read (both listings, get, archive, restore, start, start-with-message) carries `name` string or null as served; `startSession` yields exactly nine keys; `renameSession` sends one `PATCH /api/sessions/<id>` with body exactly `{ name }` (string as given incl. spaces, `null` not omitted), resolves to the server's session, id verbatim, 404 `session_not_found` and 422 reject as `ApiError`.
- `frontend/tests/app/searchApi.test.ts` — covers DoD-6 — fixtures gain `name`/`session_name`; session hit `name` and entry hit `session_name` arrive as sent (string and null), whole payload unchanged.
- `frontend/tests/app/SearchScreen.test.tsx` — covers DoD-7 — `formatSessionStart` import dropped; expected unnamed labels from an Intl `localDate` oracle (runtime zone); 029 DoD-5 clauses now expect the local date; named session row shows its name (and a date-like name verbatim) without the start date/time; unnamed row date with no `HH:MM`; entry row `<character> · <name>` / `<character> · <local date>`.
- `frontend/tests/app/SessionsSection.test.tsx` — covers DoD-7, DoD-8 — fixtures `name: null`; 011 shape clause now date-only and equal to `localDate(created_at)`; named row link text is the name, no date/time; `Actions for <name>` / `Actions for <local date>` trigger names; no rename-named button/label/title, no textbox in rows, no Rename menu item (active and archived), no PATCH issued.
- `frontend/tests/app/SessionScreen.test.tsx` — covers DoD-7 — `START_LABEL_HEADING`/`_ANYWHERE` now date-only; named session's heading is its name (date-like verbatim), no start-date heading; unnamed heading text equals `localDate(created_at)` with no time; navigating named → unnamed switches the title.
- `frontend/tests/app/CharacterTree.test.tsx` — covers DoD-7 — `session()` builder gains optional `name` (default null); 011 DoD-3 shape clauses date-only, unnamed row text = local date of `created_at` (not `last_used_at`); named row text is the name with no date/time; date-like name verbatim beside the setup label; applying a renamed row relabels with no fetch.
- `frontend/tests/app/characterComposerState.test.ts` — covers DoD-4 — `SESSION_KEYS` nine keys; workspace row holds exactly the nine keys.
- Fixture-only (`name: null` / `session_name: null`, typecheck): `searchState.test.ts`, `searchLanding.test.tsx`, `SessionsSection.export.test.tsx` (header comment: labels are dates now), `SessionsSection.import.test.tsx`, `sessionsState.test.ts`, `sessionsSectionState.test.ts`, `sessionScreenState.test.ts`, `App.test.tsx` (also `START_LABEL_HEADING` date-only), `WorkspaceShell.test.tsx`, `CharacterScreen.test.tsx`, `CharacterComposer.test.tsx`, `CharacterComposer.setup.test.tsx`, `sessionFirstReply.test.tsx`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓
