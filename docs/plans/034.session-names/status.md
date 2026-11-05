# Feature 034 — session-names

| Step | File                              | Status  | Verifier | Date |
|------|-----------------------------------|---------|----------|------|
| 001  | `001.session-name-column.md`      | done    | PASS     | 2026-11-06 |
| 002  | `002.rename-route.md`             | pending | —        | —    |
| 003  | `003.my-search-names.md`          | pending | —        | —    |
| 004  | `004.session-label-surfaces.md`   | pending | —        | —    |
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

## Notes & Issues

- Step 001: the frozen skeleton declares `RpSession.name` right after `setup_name` with **no default**, not last-with-default-None as DEC-034-6 states. Left as frozen; any test outside this step's list that constructs `RpSession` positionally or without `name` would break (none in `app/`).

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
