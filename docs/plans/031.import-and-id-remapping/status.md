# Feature 031 — import-and-id-remapping

| Step | File                                  | Status  | Verifier | Date |
|------|---------------------------------------|---------|----------|------|
| 001  | `001.envelope-validation.md`          | done    | PASS     | 2026-10-05 |
| 002  | `002.remap-and-owned-import.md`       | done    | PASS     | 2026-10-05 |
| 003  | `003.session-import.md`               | done    | PASS     | 2026-10-05 |
| 004  | `004.database-replace.md`             | done    | PASS     | 2026-10-05 |
| 005  | `005.import-routes.md`                | done    | PASS     | 2026-10-05 |
| 006  | `006.import-client.md`                | done    | PASS     | 2026-10-05 |
| 007  | `007.app-import-entry-points.md`      | done    | PASS     | 2026-10-05 |
| 008  | `008.admin-database-import.md`        | done    | PASS     | 2026-10-05 |

## Files Changed

### Step 001 — import errors, envelope validation and deserializer

- `backend/app/services/transfer_import.py` — the two frozen stubs filled: `deserialize_row` (row
  key set equals the table's columns minus `allow_missing`; per-cell arms mirroring 030's
  `_serialize_value` order — null, `Enum` value set, `Boolean`, id, other `Integer`, `String`) and
  `validate_envelope` (the five header/payload checks in `context.md`'s fixed order, returning
  `ValidatedExport` with rows in `sorted_tables` order, reading no database). Private helpers added
  beside them: `_MAX_ID`, the six `_KEY_*` header names and `_HEADER_KEYS`, `_granularity_of`,
  `_is_version`, `_deserialize_payload`, `_deserialize_value`, `_deserialize_id`. Imports widened
  with `Any`, the four SQLAlchemy type families, `Column`, the five `REASON_*` constants and
  `ExportInvalidError`, and 030's `EXPORT_FORMAT` / `ENVELOPE_VERSION` / `SCHEMA_VERSION` /
  `USER_EXCLUDED_COLUMNS` / `is_id_column` (decision 12); nothing of 030's re-declared.
- `backend/app/errors.py` — unchanged by this step: the skeleton already delivered
  `ExportInvalidReason`, the five `REASON_*` constants, `_EXPORT_INVALID_MESSAGES`,
  `ExportInvalidError` and `DatabaseNotEmptyError` implemented, not stubbed.
- `backend/app/services/transfer.py` — unchanged by this step: the skeleton already made 030's
  predicate public as `is_id_column(column, primary_key_names)`, which this step only imports.

### Step 002 — remap engine, and user and character import

- `backend/app/services/transfer_import.py` — the four frozen stubs filled: `_owned_policy` (the step's
  one `if granularity`, outside the engine — `user` → all four scopes plus the payload `users` row's id
  as `required_user_id`; `character` → the three row-targeting scopes and `None`; neither carries an
  override), `_remap_payload` (one read of `models` for the known `(server_id, model_name)` pairs, then
  per-table minting in ascending old-id order, then one rewritten row per payload row, `users` dropped
  unconditionally), `_write_payload` (`ensure_fts_tables` first, one executemany insert per table in
  `schema.metadata.sorted_tables` order with every self-referencing column NULL, then one UPDATE per
  referring row) and `import_owned` (validate against `_OWNED_GRANULARITIES` outside the transaction,
  then policy → remap → write inside one `with connection.begin():`, returning the new character ids
  ascending). Private helpers added below `_write_payload`: `_SCOPE_COLUMN`, `_SCOPE_ID_COLUMN`,
  `_MODEL_SERVER_COLUMN`, `_MODEL_NAME_COLUMN` (all four read off the registry, never typed),
  `_primary_key_column`, `_row_id`, `_mint_ids`, `_known_model_pairs`, `_remap_row`, `_memo_scope`,
  `_resolve_foreign_key`, `_resolve_user_reference`, `_resolve_scope_id`, `_resolve_new_id`,
  `_carries_model_pair`, `_keeps_model_pair`, `_self_reference_names`, `_target_table_name`. Imports
  widened with `ensure_fts_tables` and with `ForeignKey` + `select` from `sqlalchemy`; nothing else in
  the module was touched, and no frozen signature, field or constant changed.

### Step 003 — session import into a chosen character

- `backend/app/services/transfer_import.py` — the three frozen stubs filled: `import_session`
  (`validate_envelope(body, _SESSION_GRANULARITIES)` outside the transaction, then one
  `with connection.begin():` holding `_require_owned_character` → `_session_policy(character_id)` →
  step 002's `_remap_payload` → step 002's `_write_payload`, returning the one `sessions` row's new
  id read off the engine's own output via `_row_id`), `_session_policy` (ruling 23's mapping onto
  the three frozen fields, unchanged: `allowed_memo_scopes=_SESSION_MEMO_SCOPES`,
  `required_user_id=None`, `column_overrides` holding `(sessions, character_id) -> character_id` and
  `(sessions, setup_id) -> None`, both column names read off the registry) and
  `_require_owned_character` (a direct `select(schema.characters.c.id)` filtered on both `id` and
  `user_id` with **no** `archived_at` term, raising `CharacterNotFoundError()` when
  `.first()` is `None`). No new private helper was needed, no engine or writer code was touched, and
  `_ReferencePolicy` was **not** widened — `_remap_payload`, `_write_payload` and `_owned_policy` are
  byte-identical. The one edit outside the three bodies is the single import the stubs could not
  carry: `CharacterNotFoundError` added to the existing `app.errors` import block (`select` was
  already imported by step 002).

### Step 004 — whole-database replace, ids preserved

- `backend/app/services/transfer_import.py` — the five frozen stubs filled, nothing else in the
  module touched (steps 001–003's bodies are byte-identical):
  - `import_database` — one `with connection.begin():` holding, in the frozen order,
    `_require_replaceable_database` → `validate_envelope(body, _DATABASE_GRANULARITIES)` →
    `_require_memo_scope_targets(validated.rows)` → `ensure_fts_tables` → `_wipe_registry_rows` →
    `_drop_vector_tables` → `_write_payload(connection, validated.rows)`. The identity path is
    ruling 22's: the validated rows handed to step 002's writer **unchanged**, so no policy value,
    no flag and no call to `_remap_payload` / `_owned_policy` / `_ReferencePolicy` exists here. The
    constraint translation is the frozen inline `try` / `except IntegrityError` around the writer
    call **only**, re-raised as `ExportInvalidError(REASON_MALFORMED_PAYLOAD)` (decision 15: that
    exception class and no other), which leaves the `with` block and rolls the wipe, the drop and
    the inserts back together. The driver's text reaches no log line and no error field.
  - `_require_replaceable_database` — `select(schema.users.c.role).limit(2)`; no rows passes, one
    row passes when it equals `Role.ADMIN` read as stored, anything else raises
    `DatabaseNotEmptyError()`. Read-only, no pragma toggle.
  - `_require_memo_scope_targets` — pure; builds the payload's own id set per table off
    `schema.metadata.sorted_tables` and `_row_id`, then resolves each memo's `scope` through the
    frozen `_DATABASE_MEMO_SCOPE_TABLES` (`user` → `users`) and requires its `scope_id` to be in
    that table's set. A miss is `ExportInvalidError(REASON_MALFORMED_PAYLOAD)`, naming nothing.
  - `_wipe_registry_rows` — one `table.delete()` per table walking `reversed(sorted_tables)`; no
    `PRAGMA foreign_keys` toggle, so a dangling payload reference still becomes an `IntegrityError`.
  - `_drop_vector_tables` — `DROP TABLE` through `text()` for each name in the frozen
    `_VECTOR_TABLES`, only where `vector_table_dimension(...)` is not `None`; no payload value can
    reach the statement.
  - Imports added for the bodies, the only edit outside them: `text` on the existing `sqlalchemy`
    import, a new `from sqlalchemy.exc import IntegrityError`, `vector_table_dimension` on the
    existing `app.db.search_tables` line, `DatabaseNotEmptyError` on the existing `app.errors`
    block, and a new `from app.roles import Role`. No frozen signature, constant, dataclass or
    docstring changed.

### Step 005 — import routes and response models

- `backend/app/models/transfer.py` — unchanged by this step: the skeleton delivered
  `OwnedImportGranularity`, `OwnedImportResponse` (`granularity`, `character_ids`) and
  `SessionImportResponse` (`session_id`) as real models, not stubs, so there was no body to fill.
- `backend/app/routers/transfer.py` — the two frozen handler stubs filled, one delegation each and
  nothing else: `import_own_export` → `import_owned(connection, generator, current_user.id, body)`,
  whose `OwnedImportResult` maps field-for-field onto
  `OwnedImportResponse(granularity=..., character_ids=...)`; `import_own_session` →
  `import_session(connection, generator, current_user.id, character_id, body)`, whose `int` becomes
  `SessionImportResponse(session_id=...)`. The one edit outside the two bodies is the import line the
  stubs could not carry: `from app.services.transfer_import import import_owned, import_session`.
  No route decorator, path, status code, parameter, docstring or 030 handler changed.
- `backend/app/routers/admin_db.py` — `import_whole_database` completed with the cookie clear:
  `clear_session_cookie(response, settings)` after `import_database(connection, body)` returns, plus
  `clear_session_cookie` added to the existing `from app.dependencies import ...` line. Decision 24
  honoured and re-probed on the finished file: `ast.Raise` = 0, `ast.Try`/`ast.TryStar` = 0,
  function-nested imports = 0, forbidden attribute calls = 0, `from sqlalchemy` = `['Connection']`
  only, no `HTTPException`. Every refusal (409 `database_not_empty`, 400 `export_invalid`) still
  propagates out of `import_database` to the one `DomainError` handler.

### Step 006 — shared file-import helper and app import effects

- `frontend/src/shared/notifyWarning.ts` — **unchanged by this step**: the skeleton delivered the
  `"import-search-coverage"` member and its pinned sentence as real code, not a stub, so there was no
  body to fill. `notifyWarning`'s signature and the `"paste-context-cost"` entry are byte-identical.
- `frontend/src/shared/importFile.ts` — both frozen stubs filled, and the two value imports the
  stubs could not carry added (`apiPost` from `./api`, `ApiError` from `./apiError`).
  `readExportFile` reads `text()`, `JSON.parse`s it and rejects every non-plain-object (`null` and
  arrays named explicitly, since `api.ts`'s `isPlainObject` is private); all three causes raise one
  private `unreadableFile()` → `ApiError(CLIENT_UNREADABLE_FILE, "The chosen file is not a readable
  export.", 0)`, and nothing in the module sends a request. `postExportFile` is `readExportFile`
  then `apiPost<T>(path, parsed, signal)`, with no failure handling of its own, so the 401 →
  `/login` and an abort propagate unchanged. Added module-privates: `UNREADABLE_FILE_MESSAGE`,
  `unreadableFile()`. No exported signature, type or docstring changed.
- `frontend/src/app/importUploads.ts` — both path builders and both effects filled, closing
  ruling 27: the module now imports `postExportFile`, `loadCharacters`, `loadSessions`,
  `notifyFailure` **and `notifyWarning`** (the last one was the accepted true-red). `ownedImportPath`
  returns `/api/import`; `sessionImportPath` returns `/api/characters/<encodeURIComponent(id)>/import`
  with the id as a string. Both effects: an `isAborted(signal)` pre-check, the post, then on failure
  one `notifyFailure` unless aborted and never a rethrow; on success a second `isAborted` gate, the
  reloads **sequentially** (`loadCharacters` → `loadSessions` for owned, `reloadSection` →
  `loadSessions` for session), then a single `navigate` to `/characters/<the one id>` for a `character` result
  only, then exactly one `notifyWarning("import-search-coverage")`. Added module-privates:
  `OWNED_IMPORT_PATH`, `COVERAGE_WARNING`, `isAborted(signal)` (read through a call, `logout.ts`'s
  idiom) and the widened constructor-independent `isAbortRejection(error)` (030's
  `exportDownloads.ts` form — a non-null object whose `name` is `"AbortError"`, so a `DOMException`
  is caught and `ApiError` is not). Both halves of the abort contract are present. No frozen
  signature, type or docstring changed; no file outside the step's Source list touched.

### Step 007 — app import entry points: the user menu item and the Sessions section button

Scope as narrowed by decision 6: three Source files, and only three stub handlers to fill. The
frozen surface — `UserMenuProps`' two new required props, the `Import…` label, `IMPORT_ACCEPT`,
`IMPORT_INPUT_LABEL`, the hidden input's placement outside the `Menu`, the `FileButton` /
`resetRef` control in the inline-start row, `ICON_SIZE = 18` / `ICON_STROKE = 1.5` — is
byte-identical; no prop was widened and `SessionsSectionProps` still has no `sessionsState`.

- `frontend/src/app/UserMenu.tsx` — both frozen stubs filled, plus the one value import they could
  not carry (`runOwnedImport` from `./importUploads`). `onImportMyData` is
  `importInputRef.current?.click()` and nothing else — no confirm, no request, no local state.
  `onImportFileChosen` captures `event.currentTarget`, reads `files?.[0] ?? null`, then clears
  `input.value` **before** dispatching (the file is already in hand, and a file input otherwise
  keeps its previous choice, so the second pick of the same file would fire no `change` at all —
  US-136.AC-2), returns on an empty choice, and otherwise is a bare
  `void runOwnedImport(file, props.charactersState, props.sessionsState, navigate)`. `navigate` is
  the component's existing `useNavigate()` result, assignable to step 006's `NavigateTo`; no
  `.catch` was added, since `runOwnedImport` never rejects and already raises the one
  `notifyFailure` / the one `notifyWarning` itself.
- `frontend/src/app/SessionsSection.tsx` — the one frozen stub filled, plus the value import
  (`runSessionImport` from `./importUploads`; `loadSectionSessions` was already imported).
  `onImportSessionFileChosen` returns on a `null` choice, then calls `importResetRef.current?.()`
  **first** rather than after the import settles — judgement call, recorded under Notes & Issues —
  then `setImporting(true)`, then
  `void runSessionImport(characterId, file, props.sessions, () => loadSectionSessions(state, listControllerRef.current?.signal)).then(() => setImporting(false))`.
  The reload callback is the frozen one and satisfies `ReloadSection` as built; the single `.then`
  is the only completion path because `runSessionImport` never rejects. Nothing was added to
  `SessionsSectionState`, and `sessionsSectionState.ts` was not opened for edit. The handler's doc
  comment was re-worded to match the reset ordering.
- `frontend/src/app/WorkspaceShell.tsx` — **unchanged by this step**: the skeleton already passed
  `charactersState={characters}` / `sessionsState={sessions}` at both `UserMenu` call sites (the
  compact rail branch and the wide branch), so there was no body to fill.

Gates, from `frontend/`: `npm run typecheck` → **clean, zero errors** under both `tsconfig.json`
and `tsconfig.node.json` (the two TS2739 errors the skeleton recorded are gone, the test phase
having supplied the props). `npm run build` → **built**, 7503 modules, four entries emitted; the
only output is 030's pre-existing >500 kB chunk advisory and the `__dirname` config warning. **No
test file was read, opened or run.**

### Step 008 — admin Database page: Import with confirm and sign-out redirect

Two Source files, both already carrying the skeleton's frozen JSX and field declarations; only six
bodies to fill. No frozen signature, type, constant or pinned string changed, and
`DatabasePageState` still declares no methods (three observable fields, `makeAutoObservable`
untouched).

- `frontend/src/admin/databasePageState.ts` — the three frozen stubs filled. `chooseImportFile`
  stores `file` in `importFile` and clears `importErrorMessage` in one `runInAction`;
  `cancelImport` clears `importFile` only, so the derived confirm closes and nothing else moves;
  `importDatabase` returns before any write when `signal?.aborted` (and when no file is chosen),
  sets `importStatus = "importing"`, `await postExportFile(DATABASE_IMPORT_PATH, file, signal)`,
  and on success calls `documentNavigation.assign(LOGIN_PATH)` with **no** state write (the page is
  leaving, so the confirm stays loading). A failure stores `failureMessageOf(error, "The database
  could not be replaced.")` in `importErrorMessage`, clears `importFile` and returns
  `importStatus` to `"idle"`, all in one `runInAction`; it raises no notification and reads nothing
  from the 204. Added beside 030's export constant: `DATABASE_IMPORT_PATH =
  "/api/admin/database/import"` and `LOGIN_PATH = "/login"`. Imports widened only as the skeleton
  recorded: `documentNavigation` joined the existing `../shared/api` value import, and
  `postExportFile` joined the existing `../shared/importFile` type import as
  `import { type ReadableTextFile, postExportFile }` (house style of the `api.ts` line above it).
  030's module-private `isAbortRejection` and `failureMessageOf` were reused as built, not
  re-declared or amended.
- `frontend/src/admin/DatabasePage.tsx` — the three frozen stub handlers filled.
  `onImportFileChosen` returns on a `null` choice, otherwise `chooseImportFile(state, file)` (which
  opens the derived confirm) then `importResetRef.current?.()`; it makes no request.
  `cancelImportChoice` is `cancelImport(state)` and nothing else. `confirmImport` is the module's
  existing `void importDatabase(state, currentSignal()).catch(ignoreRejection)` idiom. The Import
  `FileButton`/`Button`, the `IMPORT_*` constants, the replace `ConfirmModal` with
  `opened={state.importFile !== null}` and the fourth inline red `Alert` were already in place from
  the skeleton and are untouched; no control, input or rendered text was added, and nothing about
  the file's contents is rendered.

Gates, from `frontend/`: `npm run typecheck` → **exit 0, zero errors** under both `tsconfig.json`
and `tsconfig.node.json`. `npm run build` → **built**, 7503 modules, four entries emitted; the only
output is 030's pre-existing >500 kB chunk advisory. **No test file was read, opened or run, and no
file outside the step's two Source files was changed.**

## Skeleton

### Step 001 — frozen interface (2026-10-05)

**`backend/app/errors.py`** — the reason vocabulary and the two error classes.

- `backend/app/errors.py` — `ExportInvalidReason = Literal["not_an_export", "unsupported_version", "schema_mismatch", "wrong_granularity", "malformed_payload"]` — new (module-level type alias; the closed reason vocabulary steps 002–005 annotate with)
- `backend/app/errors.py` — `REASON_NOT_AN_EXPORT: Final[ExportInvalidReason] = "not_an_export"` — new
- `backend/app/errors.py` — `REASON_UNSUPPORTED_VERSION: Final[ExportInvalidReason] = "unsupported_version"` — new
- `backend/app/errors.py` — `REASON_SCHEMA_MISMATCH: Final[ExportInvalidReason] = "schema_mismatch"` — new
- `backend/app/errors.py` — `REASON_WRONG_GRANULARITY: Final[ExportInvalidReason] = "wrong_granularity"` — new
- `backend/app/errors.py` — `REASON_MALFORMED_PAYLOAD: Final[ExportInvalidReason] = "malformed_payload"` — new
  (**no step may re-type a reason string literal**: import these five constants from `app.errors`.)
- `backend/app/errors.py` — `_EXPORT_INVALID_MESSAGES: Final[Mapping[ExportInvalidReason, str]]` — new, **private**; the five pinned sentences, verbatim from `001.context.md`. Only `ExportInvalidError.__init__` reads it.
- `backend/app/errors.py` — `class ExportInvalidError(DomainError)` — new. `code = "export_invalid"`, `http_status = 400`, instance attribute `reason: ExportInvalidReason`, and `def __init__(self, reason: ExportInvalidReason) -> None`. **One argument, no `message` and no `detail` parameter**: it sets `detail` to exactly `{"reason": reason}` and the message to that reason's pinned sentence. Raise sites read `raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)`.
- `backend/app/errors.py` — `class DatabaseNotEmptyError(DomainError)` — new. `code = "database_not_empty"`, `http_status = 409`, `def __init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None` following the `already_configured` precedent; default message `"The database can only be replaced while it holds no account other than a single administrator."`, `detail` empty.
- `backend/app/errors.py` — import line widened to `from typing import Any, Final, Literal`.

Probed wire shapes (implemented, not stubbed): `ExportInvalidError(r).to_wire()` is
`{"error": {"code": "export_invalid", "message": <pinned sentence>, "detail": {"reason": r}}}` for each of the
five reasons; `DatabaseNotEmptyError().detail == {}`.

**`backend/app/services/transfer.py`** — the one change: 030's id-column predicate is now public.

- `backend/app/services/transfer.py` — `def is_id_column(column: Column[Any], primary_key_names: Collection[str]) -> bool` — changed (was `_is_id_column(column: Column[Any], primary_key_names: Collection[str]) -> bool`). **Rename only**: same two-argument signature, same body, same position in the file; the docstring gained one paragraph saying why it is public. Its single call site, `serialize_row` (`transfer.py:166`), was updated to `is_id=is_id_column(column, key_names)`; `key_names` is still computed at :163. No wrapper, no behaviour change. **The public name 031's steps 001–004 import is `is_id_column`.**

**`backend/app/services/transfer_import.py`** (new file) — the pure validation half. It imports
`DATABASE_EXCLUDED_TABLES` and `ExportGranularity` from `app.services.transfer` and re-declares none of
030's constants; the coder adds the `EXPORT_FORMAT` / `ENVELOPE_VERSION` / `SCHEMA_VERSION` /
`USER_EXCLUDED_COLUMNS` / `is_id_column` imports as it fills the two bodies (they are unused by the stubs,
and `ruff` rejects an unused import).

- `backend/app/services/transfer_import.py` — `ImportValue = str | int | bool | None` — new (type alias; the deserialized cell. Deliberately **no `float`**: no column in `schema.metadata` is a float.)
- `backend/app/services/transfer_import.py` — `ImportRow = dict[str, ImportValue]` — new (type alias; one deserialized row, column name to Python value)
- `backend/app/services/transfer_import.py` — `EXPORT_GRANULARITIES: Final[frozenset[ExportGranularity]] = frozenset(get_args(ExportGranularity))` — new. **Decision 10's runtime granularity value set**, derived from 030's `Literal` type, probed as `{"database", "user", "character", "session"}`.
- `backend/app/services/transfer_import.py` — `GRANULARITY_TABLES: Final[Mapping[ExportGranularity, frozenset[str]]]` — new. Values, probed:
  - `"database"` → `frozenset(table.name for table in schema.metadata.sorted_tables) - DATABASE_EXCLUDED_TABLES`, i.e. `{characters, llm_servers, memos, messages, models, sessions, setups, users}` — **derived, never hand-listed**;
  - `"user"` → `{users, characters, setups, sessions, messages, memos}`;
  - `"character"` → `{characters, setups, sessions, messages, memos}`;
  - `"session"` → `{sessions, messages, memos}`.

  Table names are written as `schema.<table>.name`, never string literals, following 030's exporters.
- `backend/app/services/transfer_import.py` — `ROOT_TABLES: Final[Mapping[ExportGranularity, str]] = {"user": schema.users.name, "character": schema.characters.name, "session": schema.sessions.name}` — new. Probed as `{'user': 'users', 'character': 'characters', 'session': 'sessions'}`. **No `database` key**, so a lookup for the whole-database granularity is a `KeyError` by design — that granularity has no root.
- `backend/app/services/transfer_import.py` — `@dataclass(frozen=True) class ValidatedExport` — new, with exactly two fields in this order: `granularity: ExportGranularity` and `rows: Mapping[str, list[ImportRow]]` (table name to deserialized rows, keys in `schema.metadata.sorted_tables` order). Constructed positionally as `ValidatedExport(granularity, rows)`.
- `backend/app/services/transfer_import.py` — `def deserialize_row(table: Table, row: object, *, allow_missing: Collection[str] = ()) -> ImportRow` — new, **stub** (`raise NotImplementedError`). `table` is an `app.db.schema` Table; `row` is untrusted JSON, so it is typed `object`; `allow_missing` is keyword-only and is 030's `USER_EXCLUDED_COLUMNS` for a `user` envelope's `users` row, `()` elsewhere. Raises `ExportInvalidError(REASON_MALFORMED_PAYLOAD)`.
- `backend/app/services/transfer_import.py` — `def validate_envelope(body: object, accepted: Collection[ExportGranularity]) -> ValidatedExport` — new, **stub** (`raise NotImplementedError`). `body` is any JSON value, hence `object`; `accepted` is the route's granularity set (a `frozenset`, a `set` or a tuple of granularity literals all satisfy it). Pure: no database read, no transaction, no write. Checks run in the `context.md` order, first failure deciding the reason; it checks **no** references.
- Caller-compile edits (out of Source-files scope): None.

Gates, from `backend/`: `.venv/Scripts/python -m mypy app` → *Success: no issues found in 93 source files*;
`.venv/Scripts/python -m ruff check .` → *All checks passed!*. No tests were run.

### Step 002 — frozen interface (2026-10-05)

All of it in **`backend/app/services/transfer_import.py`**, appended below step 001's validation half.
**Step 001's surface is untouched** (two edits outside the new block, both additive: the `sqlalchemy`
import line is now `from sqlalchemy import Connection, Table`, a new `from app.ids import
SnowflakeGenerator` line joined the imports, and the module docstring's "steps 002–004" sentence now
says what 002 added). The coder adds the imports the stub bodies do not use —
`ensure_fts_tables` (and, if wanted, the FTS name constants) from `app.db.search_tables`,
`ExportInvalidError` + `REASON_MALFORMED_PAYLOAD` from `app.errors`, `is_id_column` from
`app.services.transfer`, and whatever SQLAlchemy constructs (`insert`, `select`, `update`) it needs:
`ruff` rejects an unused import, exactly as recorded for step 001.

**The scope vocabulary and the granularity data — real values, not stubs.**

- `transfer_import.py` — `_SCOPE_USER: Final[str] = "user"`, `_SCOPE_CHARACTER: Final[str] = "character"`, `_SCOPE_SETUP: Final[str] = "setup"`, `_SCOPE_SESSION: Final[str] = "session"` — new, **private**. The four `memos.scope` values named once. Decision 13: `memos.scope`'s `Enum` has `enum_class=None`, so a stored scope reads back as a plain `str` and these compare against it directly.
- `transfer_import.py` — `_MEMO_SCOPE_TABLES: Final[Mapping[str, str]] = {_SCOPE_CHARACTER: schema.characters.name, _SCOPE_SETUP: schema.setups.name, _SCOPE_SESSION: schema.sessions.name}` — new, **private**. Probed as `{'character': 'characters', 'setup': 'setups', 'session': 'sessions'}`. The reference `memos.scope_id` cannot express itself (no FK). **No `_SCOPE_USER` key by design** — that scope resolves to the caller, not to a payload row, the way `ROOT_TABLES` has no `database` key.
- `transfer_import.py` — `_USER_MEMO_SCOPES: Final[frozenset[str]] = frozenset(_MEMO_SCOPE_TABLES) | {_SCOPE_USER}` — new, **private**. Probed as `{'user', 'character', 'setup', 'session'}`.
- `transfer_import.py` — `_CHARACTER_MEMO_SCOPES: Final[frozenset[str]] = frozenset(_MEMO_SCOPE_TABLES)` — new, **private**. Probed as `{'character', 'setup', 'session'}`. Step 003 adds its own `frozenset({_SCOPE_SESSION})` constant; it edits neither of these.
- `transfer_import.py` — `_OWNED_GRANULARITIES: Final[frozenset[ExportGranularity]] = frozenset({"user", "character"})` — new, **private**. The accepted set `import_owned` passes to `validate_envelope`, so DoD-11's `wrong_granularity` comes out of step 001's checker unchanged.

**The reference policy — the shape steps 003 and 004 bind to.**

- `transfer_import.py` — `@dataclass(frozen=True) class _ReferencePolicy` — new, **private**. Exactly **three** fields, in this order:
  1. `allowed_memo_scopes: frozenset[str]` — the `memos.scope` values this granularity accepts; a scope outside the set is `malformed_payload` before its `scope_id` is resolved.
  2. `required_user_id: int | None` — the **old** user id every `user_id` column and every `scope='user'` `scope_id` must equal; `None` is the "any" case. `None` turns the *equality check* off only — every `user_id` still becomes the caller's. A `user` envelope passes the payload `users` row's id; `character` and `session` pass `None`.
  3. `column_overrides: Mapping[tuple[str, str], int | None]` — out-of-payload references resolved by decree, keyed `(table name, column name)`. **Key present with an `int` → write that id; present with `None` → write NULL; absent → remap normally.** The engine tests membership (`in`), never truthiness, so `None` is a value and not a miss. Step 003's session policy is `{(schema.sessions.name, "character_id"): <target id>, (schema.sessions.name, "setup_id"): None}`.

  Constructed with keyword arguments (no `kw_only`, no defaults — every policy states all three). **Built per call, not a module constant**: two of the three fields need a value only the request knows.

  **Why no granularity branch reaches the engine.** Everything that is the *same* at every granularity is engine code and deliberately **not** a field: a fresh snowflake per row; every `users` FK target becoming the caller; the payload `users` row never being written (the engine drops the `users` table from its result unconditionally, at every granularity it serves); `memos.scope_id` resolving through `_MEMO_SCOPE_TABLES`; and the `(model_server_id, model_name)` pair kept only when it exists in `models`, else both nulled. Everything that *differs* is one of the three fields. The one `if granularity` in this step lives in `_owned_policy`, outside the engine, and step 003 writes its own policy beside it rather than adding an arm.

**The result value.**

- `transfer_import.py` — `@dataclass(frozen=True) class OwnedImportResult` — new, **public**. Exactly two fields, in this order: `granularity: ExportGranularity` (`"user"` or `"character"`) and `character_ids: list[int]` (the **new** ids, **ascending**; one entry for a `character` envelope, one per payload character for a `user` envelope, empty when it had none). `list[int]` follows the `SettleResult.buried_ids` precedent. Constructed positionally as `OwnedImportResult(granularity, character_ids)`. Step 005's response model serializes the ids as `SnowflakeOut` decimal strings.

**The four callables** (each body is `raise NotImplementedError`; nothing else is implemented).

- `transfer_import.py` — `def import_owned(connection: Connection, generator: SnowflakeGenerator, user_id: int, body: object) -> OwnedImportResult` — new, **public**, **stub**. The only symbol of this step a test or a route may name. `body` is the raw envelope, typed `object` like `validate_envelope`'s. Order fixed by the docstring: validate against `_OWNED_GRANULARITIES` (pure, outside the transaction) → one `with connection.begin():` → `_owned_policy` → `_remap_payload` → `_write_payload`. Raises `ExportInvalidError`.
- `transfer_import.py` — `def _owned_policy(validated: ValidatedExport) -> _ReferencePolicy` — new, **private**, **stub**. The step's only branch on granularity, kept out of the engine on purpose. `user` → (`_USER_MEMO_SCOPES`, the payload `users` row's id, no overrides); `character` → (`_CHARACTER_MEMO_SCOPES`, `None`, no overrides).
- `transfer_import.py` — `def _remap_payload(validated: ValidatedExport, policy: _ReferencePolicy, generator: SnowflakeGenerator, user_id: int, connection: Connection) -> dict[str, list[ImportRow]]` — new, **private**, **stub**. The remap engine, in the Interface intent's own parameter order (the `(connection, generator, user_id, …)` service convention governs the public entry points, not this private seam). Returns the rows to insert per table, **keys in `schema.metadata.sorted_tables` order**, rows in payload order, each a complete `ImportRow`. `connection` is read **only** for the `(server_id, model_name)` lookup in `models`, inside the caller's transaction — no `_reading`, no write, no `PRAGMA` toggle. **The `users` table is never a key of the result.** Raises `ExportInvalidError(REASON_MALFORMED_PAYLOAD)` for a reference that resolves nowhere, naming neither table, column nor value (R5).
- `transfer_import.py` — `def _write_payload(connection: Connection, rows: Mapping[str, list[ImportRow]]) -> None` — new, **private**, **stub**. The payload writer, called inside the caller's `with connection.begin():`. **It takes final rows and assumes no minting happened**, which is the seam step 004 needs: 004's "identity policy" *is* handing it `validated.rows` unchanged, so the whole-database replace keeps the export's own ids with no second code path and no extra policy value. A table absent from `rows` is not written. Order: `ensure_fts_tables(connection)` before the first insert → one insert per table walking `sorted_tables` → the second pass for self-referencing FK columns, found from each Table's own foreign keys (today only `messages.related_to`): inserted NULL, then one UPDATE per referring row. Both passes satisfy `ck_messages_buried_or_settled`.
- Caller-compile edits (out of Source-files scope): None. Nothing outside `transfer_import.py` was touched, and nothing yet imports the four new callables.

Gates, from `backend/`: `.venv/Scripts/python -m mypy app` → *Success: no issues found in 93 source files*;
`.venv/Scripts/python -m ruff check .` → *All checks passed!*. No tests were run.

### Step 003 — frozen interface (2026-10-05)

All of it in **`backend/app/services/transfer_import.py`**, appended below step 002's block.
**Steps 001's and 002's frozen surfaces are untouched**: no existing signature, constant,
dataclass field or position changed, and the only edit outside the new block is the module
docstring's "steps 003 and 004" sentence, which now says what 003 added. No new import line was
needed — the stubs use `Connection`, `SnowflakeGenerator`, `Final`, `ExportGranularity`,
`_SCOPE_SESSION` and `_ReferencePolicy`, all already imported or declared. The coder adds the
imports the stub bodies do not use: **`from app.errors import CharacterNotFoundError`** for the
target lookup, and whatever SQLAlchemy constructs (`select`, `and_`) it needs — `ruff` rejects an
unused import, exactly as recorded for steps 001 and 002.

**The session vocabulary — real values, not stubs.**

- `transfer_import.py` — `_SESSION_MEMO_SCOPES: Final[frozenset[str]] = frozenset({_SCOPE_SESSION})` — new, **private**. The memo scopes a `session` payload may carry: `session` only. Built from step 002's `_SCOPE_SESSION`, never a re-typed literal. Neither `_USER_MEMO_SCOPES` nor `_CHARACTER_MEMO_SCOPES` was touched.
- `transfer_import.py` — `_SESSION_GRANULARITIES: Final[frozenset[ExportGranularity]] = frozenset({"session"})` — new, **private**. The accepted set `import_session` passes to step 001's `validate_envelope`, so DoD-9's `wrong_granularity` comes out of that checker unchanged. `_OWNED_GRANULARITIES` was not touched.

**The three callables** (each body is `raise NotImplementedError`; nothing else is implemented).

- `transfer_import.py` — `def import_session(connection: Connection, generator: SnowflakeGenerator, user_id: int, character_id: int, body: object) -> int` — new, **public**, **stub**. The only symbol of this step a test or a route may name. Returns the **new** `sessions` row's id (step 005 serializes it as `SnowflakeOut`). `body` is the raw envelope, typed `object` like `validate_envelope`'s and `import_owned`'s; `character_id` is the chosen target. Parameter order follows `context.md`'s `(connection, generator, user_id, …)` service convention, with the target before the body. Order fixed by the docstring and by DoD-9: `validate_envelope(body, _SESSION_GRANULARITIES)` (pure, **outside** the transaction) → one `with connection.begin():` → `_require_owned_character` → `_session_policy(character_id)` → `_remap_payload` → `_write_payload`. Raises `ExportInvalidError` and `CharacterNotFoundError`.
- `transfer_import.py` — `def _session_policy(character_id: int) -> _ReferencePolicy` — new, **private**, **stub**. `_owned_policy`'s **sibling**, not an arm inside it: step 002 deliberately kept the one granularity branch out of the engine, and this step adds a policy beside it. It takes **only** `character_id` and no `ValidatedExport`, because unlike `_owned_policy` nothing in a session policy is read off the payload — the target fully determines it.
- `transfer_import.py` — `def _require_owned_character(connection: Connection, user_id: int, character_id: int) -> None` — new, **private**, **stub**. The target lookup, frozen as a helper rather than left inline so the ordering in `import_session` is readable and the "not the characters getter" decision has one home. A direct `select` on `characters` filtered on **both** `id` and `user_id`, **archived or not** — it must not reuse `services.characters`' getter, which may filter archived rows out, while R6 requires an archived target to be accepted (`003.context.md`); 030's `export_character` made the same choice for its export root. Called **inside** `import_session`'s `with connection.begin():`, after validation; it opens no transaction, writes nothing, toggles no pragma. Returns `None` on success and raises `CharacterNotFoundError()` (`character_not_found`, 404, empty `detail`) when no row comes back — a missing id and a foreign id are indistinguishable, and there is no 403 (R5).

**The policy-field mapping — the four session rules onto `_ReferencePolicy`'s three frozen fields.**
This is the contract the test-coder and the coder both bind to; `_ReferencePolicy` was **not** widened.

| Session rule (`003.session-import.md` §"Interface intent") | Carried by |
|---|---|
| allowed memo scopes = {`session`} | `allowed_memo_scopes = _SESSION_MEMO_SCOPES` |
| …and the target must be the payload session | **no field** — `_SCOPE_SESSION` resolves through step 002's `_MEMO_SCOPE_TABLES` to `sessions`, and a validated `session` payload holds exactly one `sessions` row (`ROOT_TABLES`), so the only `scope_id` that resolves at all is that session's; any other id already fails the engine's ordinary "resolves to no payload row" check and is `malformed_payload` |
| `sessions.character_id` → the target character's id | `column_overrides[(schema.sessions.name, "character_id")] = character_id` (present with an `int` → write that id) |
| `sessions.setup_id` → null whatever the payload held | `column_overrides[(schema.sessions.name, "setup_id")] = None` (present with `None` → write NULL; membership is tested with `in`, never truthiness) |
| every `user_id` → the caller, accepting **any** payload value | `required_user_id = None` — "any" is exactly what `None` means, and it turns off the **equality check only**: the engine still substitutes the caller on every `user_id`. There is no payload `users` row to require a value from |
| the model pair follows the shared rule | **no field** — `_remap_payload` keeps `(model_server_id, model_name)` only when that pair exists in this instance's `models`, else nulls both, at every granularity |

So the whole policy is `_ReferencePolicy(allowed_memo_scopes=_SESSION_MEMO_SCOPES, required_user_id=None, column_overrides={(schema.sessions.name, "character_id"): character_id, (schema.sessions.name, "setup_id"): None})` — the exact shape step 002 predicted, with no fourth field and no engine change.

- Caller-compile edits (out of Source-files scope): None. Nothing outside `transfer_import.py` was touched, and nothing yet imports `import_session` (step 005's route does).

Gates, from `backend/`: `.venv/Scripts/python -m mypy app` → *Success: no issues found in 93 source files*;
`.venv/Scripts/python -m ruff check .` → *All checks passed!*. No tests were run.

### Step 004 — frozen interface (2026-10-05)

All of it in **`backend/app/services/transfer_import.py`**, appended below step 003's block.
**Steps 001's, 002's and 003's frozen surfaces are untouched**: no existing signature, constant,
dataclass field or position changed. The only two edits outside the new block are additive — a new
`from app.db.search_tables import MEMO_VEC_TABLE, SESSION_VEC_TABLE` import line (used by a real
constant, so `ruff` is satisfied), and the module docstring's "step `004`" sentence, which now says
what 004 added. The coder adds the imports the stub bodies do not use: `ensure_fts_tables` and
`vector_table_dimension` from `app.db.search_tables`, `ExportInvalidError` +
`REASON_MALFORMED_PAYLOAD` + `DatabaseNotEmptyError` from `app.errors`, `Role` from `app.roles`,
`IntegrityError` from `sqlalchemy.exc`, and whatever SQLAlchemy constructs (`select`, `delete`,
`text`) it needs — `ruff` rejects an unused import, exactly as recorded for steps 001–003.

**THE IDENTITY-PATH RULING (orchestrator, binding on the test-coder and the coder).**
`004.database-replace.md` §"Interface intent" asks for a module-private **"Database identity
policy"**. **No such symbol exists and none may be added.** Step 002's
`_write_payload(connection, rows: Mapping[str, list[ImportRow]]) -> None` already takes **final**
rows and assumes no minting happened, so the identity path *is* `_write_payload(connection,
validated.rows)` — the validated rows handed over **unchanged**. There is no policy value, no policy
field, no flag, and no second writer. `_remap_payload` mints unconditionally and is **not** on this
step's path: nothing in step 004 calls it, and `_ReferencePolicy` was neither widened nor
instantiated here. Step 004 calls the writer directly.

**The vocabulary and the data — real values, not stubs** (each probed, values below).

- `transfer_import.py` — `_DATABASE_GRANULARITIES: Final[frozenset[ExportGranularity]] = frozenset({"database"})` — new, **private**. Probed `{'database'}`. The accepted set `import_database` passes to step 001's `validate_envelope`, so DoD-7's `wrong_granularity` comes out of that checker unchanged. `_OWNED_GRANULARITIES` and `_SESSION_GRANULARITIES` were not touched.
- `transfer_import.py` — `_DATABASE_MEMO_SCOPE_TABLES: Final[Mapping[str, str]] = {**_MEMO_SCOPE_TABLES, _SCOPE_USER: schema.users.name}` — new, **private**. Probed `{'character': 'characters', 'setup': 'setups', 'session': 'sessions', 'user': 'users'}`. Step 002's `_MEMO_SCOPE_TABLES` deliberately has **no** `user` key (that scope resolves to the caller at the roleplayer granularities); a database payload is the one case where `scope='user'` resolves **inside** the payload, because the payload carries the `users` rows and their ids are preserved. Built **from** step 002's map, not beside it, and step 002's map is unmodified.
- `transfer_import.py` — `_VECTOR_TABLES: Final[tuple[str, ...]] = (MEMO_VEC_TABLE, SESSION_VEC_TABLE)` — new, **private**. Probed `('memo_vec', 'session_vec')`. 024's two `vec0` tables named **once**, from 024's own constants, which is what keeps the `DROP` free of any string that could come from a payload.

**The five callables** (each body is `raise NotImplementedError`; nothing else is implemented).

- `transfer_import.py` — `def import_database(connection: Connection, body: object) -> None` — new, **public**, **stub**. The only symbol of this step a test or a route may name. **No request user and no generator**, so `fast/003`'s bootstrap restore can call it; returns `None`. `body` is the raw envelope, typed `object` like `validate_envelope`'s, `import_owned`'s and `import_session`'s. One `with connection.begin():` block holds every phase, in the order fixed by the docstring and by the DoD:
  1. `_require_replaceable_database(connection)` — **first, before validation** (DoD-5);
  2. `validate_envelope(body, _DATABASE_GRANULARITIES)`;
  3. `_require_memo_scope_targets(validated.rows)`;
  4. `ensure_fts_tables(connection)` — **before** the wipe (DoD-9);
  5. `_wipe_registry_rows(connection)`, then `_drop_vector_tables(connection)`;
  6. `_write_payload(connection, validated.rows)` — ids preserved, see the ruling above;
  7. the constraint translation: `except IntegrityError` **around phase 6 only**, re-raised as `ExportInvalidError(REASON_MALFORMED_PAYLOAD)` so the `with` block exits by exception and rolls back whole. Frozen as **inline `try`/`except` inside `import_database`**, not a helper — decision 3 forbids `try`/`raise` in `routers/admin_db.py`, so the translation lives in this service, and it is four lines around one call.

  Raises `DatabaseNotEmptyError` (409, `detail == {}`) and `ExportInvalidError` (400, `detail == {"reason": "malformed_payload"}` for a bad payload / an absent memo-scope target / a row the database refuses; `wrong_granularity` for any other granularity). Never logs or forwards the driver's text (R5, DoD-11).
- `transfer_import.py` — `def _require_replaceable_database(connection: Connection) -> None` — new, **private**, **stub**. The **eligibility guard**, frozen as a named helper because the step reads it as a named phase and DoD-3/DoD-4/DoD-5 all aim at it. Returns `None` on success; raises `DatabaseNotEmptyError()` otherwise. Allowed when `users` holds **0** rows, or **exactly 1** whose `role` is `Role.ADMIN`, read **as stored** and compared the way `services/bootstrap.py:63` does — not re-derived. Reads only: no write, no pragma toggle, no transaction of its own.
- `transfer_import.py` — `def _require_memo_scope_targets(rows: Mapping[str, list[ImportRow]]) -> None` — new, **private**, **stub**. The **scope-target check**, also a named phase. Takes `ValidatedExport.rows` rather than the whole `ValidatedExport`, because nothing here is granularity-dependent and the header has nothing left to say; the parameter type is step 002's `_write_payload` parameter type, verbatim. **Pure** — no connection, no read, no write. Each `memos` row's `scope` resolves through `_DATABASE_MEMO_SCOPE_TABLES` and its `scope_id` must equal the id of a payload row of that table (`user` → a payload `users` id). A miss raises `ExportInvalidError(REASON_MALFORMED_PAYLOAD)`, naming neither scope, table nor id (R5; DoD-6's third case). `memos.scope_id` has no FK, so the database would never catch this.
- `transfer_import.py` — `def _wipe_registry_rows(connection: Connection) -> None` — new, **private**, **stub**. One DELETE per table, walking `schema.metadata.sorted_tables` in **reverse**, probed as `translations, messages, sessions, setups, models, memos, characters, auth_sessions, users, llm_servers` — children before parents. It does **not** toggle `PRAGMA foreign_keys`. Called after `ensure_fts_tables`, so the FTS delete triggers clear the old entries as the rows go.
- `transfer_import.py` — `def _drop_vector_tables(connection: Connection) -> None` — new, **private**, **stub**. The wipe's second half, frozen as its own helper because it is DDL rather than DML and DoD-8/DoD-12 aim at it alone. Drops each name in `_VECTOR_TABLES` through `text()`, **only** when `vector_table_dimension(connection, name)` is not `None` — no `IF EXISTS` branch, so "they did not exist" is a no-op. DDL is transactional, so a failed import leaves both tables, their rows and their original dimension intact.

**What this step did NOT add, deliberately.** No identity policy symbol (see the ruling). No
`_ReferencePolicy` instance and no call to `_remap_payload` or `_owned_policy`. No generator
parameter anywhere. No new `ExportInvalidReason`. No change to `GRANULARITY_TABLES` — the `database`
key is already derived from `sorted_tables` minus 030's `DATABASE_EXCLUDED_TABLES`, so `auth_sessions`
and `translations` are wiped and never re-filled with no edit here.

- Caller-compile edits (out of Source-files scope): None. Nothing outside `transfer_import.py` was touched, and nothing yet imports `import_database` (step 005's admin-db route does).

Gates, from `backend/`: `.venv/Scripts/python -m mypy app` → *Success: no issues found in 93 source files*;
`.venv/Scripts/python -m ruff check .` → *All checks passed!*. No tests were run.

### Step 005 — frozen interface (2026-10-05)

**Steps 001's, 002's, 003's and 004's frozen surfaces are untouched.** `app/services/transfer_import.py`
was **not edited at all**; this step only *calls* `import_owned`, `import_session` and
`import_database` as frozen. `app/main.py` was not touched — 030 already registers the transfer
router last (`main.py:160`).

#### `backend/app/models/transfer.py` (new file) — the two response models

- `app/models/transfer.py` — `OwnedImportGranularity = Literal["user", "character"]` — new (module-level type alias, **public**). 030's four-value `ExportGranularity` narrowed to the two values `POST /api/import` accepts. Deliberately **re-declared locally, not imported from `app.services.transfer`** — the same local narrowing `models/admin_db.py` does with `TableStatusValue` against `app.db.drift.TableStatus` — which keeps `app/models/transfer.py` free of any `app.services`, `app.db`, `app.routers` or `fastapi` import. (The pydantic mypy plugin runs with `init_typed` off, so handing `OwnedImportResult.granularity` — typed `ExportGranularity` — to this narrower field is not a mypy error; pydantic validates it at runtime.)
- `app/models/transfer.py` — `class OwnedImportResponse(BaseModel)` — new, **public**. Exactly **two** fields, in this order:
  1. `granularity: OwnedImportGranularity`
  2. `character_ids: list[SnowflakeOut]`

  `POST /api/import`'s whole 200 body, and the wire form of step 002's `OwnedImportResult` field-for-field in the same order, so the coder maps it with no reshaping. Probed serialization: `OwnedImportResponse(granularity="user", character_ids=[1234567890123456789, 2]).model_dump_json()` → `{"granularity":"user","character_ids":["1234567890123456789","2"]}` — **decimal strings**, per item, which is the `list[SnowflakeOut]` precedent `models/stream.py`'s `buried_ids` / `restored_ids` set.
- `app/models/transfer.py` — `class SessionImportResponse(BaseModel)` — new, **public**. Exactly **one** field: `session_id: SnowflakeOut`. `POST /api/characters/{character_id}/import`'s whole 200 body — the `int` `import_session` returns, serialized as a decimal string (probed: `{"session_id":"1234567890123456789"}`).
- **No request model, and no model for the admin route.** Both import bodies are raw JSON objects (`005.context.md` §"Why the bodies are raw objects"), and the admin import answers 204 with no body. The module holds nothing else: no row content, no name, no title, no timestamp, no `user_id` (R5).

#### `backend/app/routers/transfer.py` (030's) — two handlers added

The router is unchanged (`APIRouter(tags=["transfer"], dependencies=[Depends(require_user)])`, no
prefix, full literal paths), and 030's three `GET` handlers and `_attachment` are byte-identical.
Both new handlers **re-declare `require_user` as a parameter** even though it is router-level, which
is 030's own idiom and the only way to reach the `CurrentUser` whose `id` scopes the import.
`get_id_generator` is imported **`from app.routers.bootstrap`** — the one line every minting router
uses (`admin_llm`, `admin_users`, `auth`, `characters`, `memos`, `sessions`, `setups`, `stream`,
`translation`) — and declared `generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)]`
with `from app.ids import SnowflakeGenerator`, copied from `routers/characters.py:97`.

- `app/routers/transfer.py` — `@router.post("/api/import", status_code=200)` over

  ```python
  def import_own_export(
      body: dict[str, Any],
      current_user: Annotated[CurrentUser, Depends(require_user)],
      connection: Annotated[Connection, Depends(get_connection)],
      generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
  ) -> OwnedImportResponse
  ```

  — new, **stub** (`raise NotImplementedError`). **Method `POST`, full path `/api/import`, success status `200`**, response model `OwnedImportResponse`. Parameter order is the codebase idiom (body, then `current_user`, then `connection`, then `generator` — `routers/memos.py:107`). Will call `import_owned(connection, generator, current_user.id, body)`.
- `app/routers/transfer.py` — `@router.post("/api/characters/{character_id}/import", status_code=200)` over

  ```python
  def import_own_session(
      character_id: SnowflakeIn,
      body: dict[str, Any],
      current_user: Annotated[CurrentUser, Depends(require_user)],
      connection: Annotated[Connection, Depends(get_connection)],
      generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
  ) -> SessionImportResponse
  ```

  — new, **stub** (`raise NotImplementedError`). **Method `POST`, full path `/api/characters/{character_id}/import`, success status `200`**, response model `SessionImportResponse`. The path id is the **inbound** alias `SnowflakeIn` from `app/models/ids.py`, never a bare `int`, so a non-numeric id is 422 before the service (path id first, then body — `routers/memos.py:151`). Will call `import_session(connection, generator, current_user.id, character_id, body)`.
- Imports added to the module (all module-level): `Any` joined `Annotated` on the `typing` line, plus `from app.ids import SnowflakeGenerator`, `from app.models.transfer import OwnedImportResponse, SessionImportResponse`, `from app.routers.bootstrap import get_id_generator`. **The coder adds the imports the stub bodies do not use** — `from app.services.transfer_import import import_owned, import_session`; `ruff` rejects an unused import, exactly as recorded for steps 001–004.
- The module docstring was updated (three → five routes; the raw-body exception; `ExportInvalidError` named beside the two 404s). No other existing line changed.

#### `backend/app/routers/admin_db.py` — one handler added

- `app/routers/admin_db.py` — `@router.post("/import", status_code=204)` over

  ```python
  def import_whole_database(
      body: dict[str, Any],
      response: Response,
      connection: Annotated[Connection, Depends(get_connection)],
      settings: Annotated[Settings, Depends(get_settings)],
  ) -> None
  ```

  — new. **Method `POST`, full path `/api/admin/database/import`** (router prefix `/api/admin/database` + `/import`), **success status `204`, no body and no response model**. It names **no guard**: `require_admin = require_role(Role.ADMIN)` is router-level and this route inherits it, like the other four. `response: Response` and `settings: Annotated[Settings, Depends(get_settings)]` are declared exactly as `POST /api/auth/logout` declares them (`routers/auth.py:68-83`), because they are what the cookie writer needs.
- **The cookie-clear writer's real name is `clear_session_cookie(response: Response, settings: Settings) -> None`, in `app/dependencies.py`** — the same writer `POST /api/auth/logout` uses. It calls `response.delete_cookie(key=settings.session_cookie_name, path="/", secure=False, httponly=True, samesite="lax")`. **The coder adds `clear_session_cookie` to the `from app.dependencies import ...` line and calls `clear_session_cookie(response, settings)` after `import_database` returns**; `ruff` would reject it as an unused import today. That call is behaviour, so the skeleton declares the two parameters it needs and writes nothing.
- **Deliberate, forced deviation from "a stub body raises `NotImplementedError`".** Decision 3's AST clause forbids `ast.Try`, `ast.TryStar` **and** `ast.Raise` **anywhere** in `app/routers/admin_db.py`, so this one handler body may not contain a `raise`. Its body is the single delegation `import_database(connection, body)` — step 004's own stub, which raises `NotImplementedError`. The route therefore still **fails loudly when executed** (500, no plausible value, nothing written), with zero behaviour in the router. Probed on the file: `ast.Try` / `ast.TryStar` / `ast.Raise` nodes = **0**; forbidden attribute calls (`execute`, `exec_driver_sql`, `begin`, `begin_nested`, `commit`, `rollback`, `scalar`, `scalars`) = **0**; `from sqlalchemy` imports = `['Connection']` only; imports nested inside a function = **0**; `"HTTPException"` present = **False**; no non-docstring string constant was added, so no SQL-keyword constant.
- **Decision 3's OpenAPI vocabulary clause honoured, probed.** JSON-dumping the `/api/admin/database/import` POST operation gives `vector` → absent, `vec0` → absent, `rebuild` → absent, **and `export` → absent too**: `FORBIDDEN_SURFACE` keeps `export` rejected on every operation but 030's one export op, and the error code `export_invalid` contains the substring `export`, so neither the word nor that code is written anywhere in the handler's name, summary or docstring. `operationId` is `import_whole_database_api_admin_database_import_post`. The docstring does not mention the search tables at all.
- Imports added to the module (all module-level, nothing nested): `Any` joined `Annotated` on the `typing` line, plus `from app.config import Settings, get_settings` and `from app.services.transfer_import import import_database`. `from sqlalchemy import Connection` is unchanged; `Response` was already imported.
- The module docstring was updated (four → five routes; a paragraph stating that this module holds no `try`/`except`/`raise` and why). The sentence "there is still **no rebuild and no import route**" became "there is still **no rebuild route**". Docstring text is not in the OpenAPI operation dump and is not scanned by the AST clause.

#### The probed route surface

| Method | Full path | Success status | Response model | Body schema | Path param |
|---|---|---|---|---|---|
| `POST` | `/api/import` | 200 | `OwnedImportResponse` | `{"type":"object","additionalProperties":true}` | — |
| `POST` | `/api/characters/{character_id}/import` | 200 | `SessionImportResponse` | `{"type":"object","additionalProperties":true}` | `character_id` (`SnowflakeIn`) |
| `POST` | `/api/admin/database/import` | 204 | none | `{"type":"object","additionalProperties":true}` | — |

Each also publishes `422`, which is FastAPI's own validation response — the `dict[str, Any]` body is
what makes an array, a scalar, a non-JSON or a missing body a 422 before any service runs.

- Caller-compile edits (out of Source-files scope): **None.** Nothing outside the three Source files was touched. No existing signature, route or model changed, and no existing caller needed adapting — the three service entry points were stubbed by steps 002–004 and until now unreferenced.

Gates, from `backend/`: `.venv/Scripts/python -m mypy app` → *Success: no issues found in 94 source files*;
`.venv/Scripts/python -m ruff check .` → *All checks passed!*. No tests were run.

### Step 006 — frozen interface (2026-10-05)

**Steps 001–005's frozen backend surfaces are untouched; no backend file was opened.** Three
Source files: two new frontend modules of **free functions only** (no MobX class — no control owns
domain state about an import, following 030's `exportDownloads.ts`) and one delivered module that
gains one closed-union member. Function bodies are `throw new Error("not implemented")`, the house
frontend stub idiom 030's skeleton used; `tsconfig.json` has `noUnusedParameters`, so each stub
body discards its parameters with `void <param>;` statements before the throw (030 did the same
with `void setExporting;`).

#### `frontend/src/shared/notifyWarning.ts` (changed) — orchestrator decision 4

- `frontend/src/shared/notifyWarning.ts` — `export type WarningId = "paste-context-cost" | "import-search-coverage"` — **changed** (was `export type WarningId = "paste-context-cost"`). The new member's exact string is **`"import-search-coverage"`**.
- `frontend/src/shared/notifyWarning.ts` — `WARNING_MESSAGES` gains exactly one entry — **changed** (private `const WARNING_MESSAGES: Record<WarningId, string>`, unchanged type):

  ```ts
  "import-search-coverage":
    "Imported material won't appear in semantic search until an administrator rebuilds the search index.",
  ```

  The message is the pinned sentence from `006.context.md`, **verbatim**, including the `'` in
  `won't` and the final full stop.
- **`notifyWarning`'s signature is untouched**: `export function notifyWarning(id: WarningId): void` — one parameter, `notifyWarning.length === 1`, still the only export. `"paste-context-cost"` and its message are byte-identical.
- **`color` is not per-entry.** The existing shape puts it in the single `notifications.show({ message: WARNING_MESSAGES[id], color: "yellow" })` call, so the new warning is `yellow` by construction; no colour was added anywhere.
- Why here and nowhere else: `WarningId` is a **closed union** and free text is `@ts-expect-error`-pinned in its own test, so the coverage sentence cannot be passed as a string. This is also the only placement that keeps the `@mantine/notifications` importer set at exactly `["src/shared/notifyFailure.ts", "src/shared/notifyWarning.ts"]` (`tests/conventions.test.ts`), which no step may widen.

#### `frontend/src/shared/importFile.ts` (new file) — the shared read-and-post helper

- `frontend/src/shared/importFile.ts` — `export const CLIENT_UNREADABLE_FILE = "client_unreadable_file"` — new. Name follows `apiError.ts`'s `CLIENT_MALFORMED_ERROR` / `CLIENT_TRANSPORT_FAILED`; value is the code `031/context.md` §"Frontend shared facts" pins.
- `frontend/src/shared/importFile.ts` — `export type ReadableTextFile = { text(): Promise<string> }` — new. The structural "anything with an async `text()`" contract the step asks for. A real `File` satisfies it via `Blob.prototype.text`, which **jsdom 30.1.1 does implement** (decision 19), so step 007's `FileButton` `File` and a hand-rolled test double are both assignable.
- `frontend/src/shared/importFile.ts` — `export async function readExportFile(file: ReadableTextFile): Promise<Record<string, unknown>>` — new, **stub**. Resolves to the parsed JSON object; sends nothing.
- `frontend/src/shared/importFile.ts` — `export async function postExportFile<T = unknown>(path: string, file: ReadableTextFile, signal?: AbortSignal): Promise<T>` — new, **stub**. Reads with `readExportFile`, then `apiPost<T>(path, parsed, signal)`, and resolves to its decoded result. **This is the signature step 008 binds to**; the `<T = unknown>` default mirrors `apiPost`'s own, so `await postExportFile(path, file)` on the 204 admin route resolves `unknown` (`apiRequest` returns `undefined as T` for an empty 2xx body) and `postExportFile<OwnedImportResponse>(…)` types the two app routes.
- **The unreadable-file message is documented in jsdoc, not frozen as a constant** — exactly 030's step-004 precedent for `rphelper-export.json`. An unexported constant would trip `noUnusedLocals` while the body is a stub, and an exported one is surface the step did not ask for. The literal is spec (`006.import-client.md` DoD-2 / `context.md` §"Frontend shared facts"): **`The chosen file is not a readable export.`**, with status `0` and code `CLIENT_UNREADABLE_FILE`.
- **The module imports nothing at all** (decision 18): no `notifyFailure`, no `@mantine/notifications`, and — while the bodies are stubs — not yet `ApiError` or `apiPost` either. **The coder adds `import { ApiError } from "../shared/apiError"`** (relative to this file: `./apiError`) **and `apiPost` from `./api`** — `ApiError` lives in `apiError.ts`, **not** `api.ts`, per decision 16, and its `detail` parameter is optional. `noUnusedLocals` rejects an unused import today, exactly as recorded for the backend steps. `api.ts`'s `isPlainObject` is private, so the plain-object check is this module's own.

#### `frontend/src/app/importUploads.ts` (new file) — the `app` entry's two import effects

- `frontend/src/app/importUploads.ts` — `export type OwnedImportGranularity = "user" | "character"` — new.
- `frontend/src/app/importUploads.ts` — `export type OwnedImportResponse = { granularity: OwnedImportGranularity; character_ids: string[] }` — new. The whole 200 body of `POST /api/import`, field order matching step 005's `OwnedImportResponse` pydantic model. `character_ids` is `string[]` — decimal strings, never numbers.
- `frontend/src/app/importUploads.ts` — `export type SessionImportResponse = { session_id: string }` — new. The whole 200 body of `POST /api/characters/{character_id}/import`.
- `frontend/src/app/importUploads.ts` — `export type NavigateTo = (path: string) => void` — new. The navigation seam. `useNavigate()`'s `NavigateFunction` (two overloads, `(to: To, options?) => void | Promise<void>` and `(delta: number) => …`) **is assignable to it**, so step 007 passes `navigate` straight through, and a test double is a one-parameter `vi.fn()`. Typing the parameter as `NavigateFunction` itself was rejected: an overloaded target would reject a simple `(to: string) => void` double.
- `frontend/src/app/importUploads.ts` — `export type ReloadSection = () => Promise<void>` — new. Step 007 supplies `() => loadSectionSessions(state, signal)`, which already returns `Promise<void>`; a test double must therefore be `async` (`vi.fn(async () => {})`), since a bare `vi.fn()` resolving `undefined` is not assignable.
- `frontend/src/app/importUploads.ts` — `export function ownedImportPath(): string` — new, **stub**. No parameter; returns the literal `/api/import`. A function rather than a constant, so both builders are one callable surface (030's `ownDataExportPath` precedent).
- `frontend/src/app/importUploads.ts` — `export function sessionImportPath(characterId: string): string` — new, **stub**. Returns `/api/characters/<characterId>/import`; the id is a **string**, escaped and never parsed (030's `characterExportPath` precedent, and `tests/ids-are-strings.test.ts`).
- `frontend/src/app/importUploads.ts` — `export async function runOwnedImport(file: ReadableTextFile, charactersState: CharactersState, sessionsState: SessionsState, navigate: NavigateTo, signal?: AbortSignal): Promise<void>` — new, **stub**. Resolves on success and on handled failure alike and **never rethrows**.
- `frontend/src/app/importUploads.ts` — `export async function runSessionImport(characterId: string, file: ReadableTextFile, sessionsState: SessionsState, reloadSection: ReloadSection, signal?: AbortSignal): Promise<void>` — new, **stub**. Same never-rethrow contract.
- **Imports present while the bodies are stubs:** `import type { ReadableTextFile } from "../shared/importFile"`, `import type { CharactersState } from "./charactersState"`, `import type { SessionsState } from "./sessionsState"` — type-only, so they survive `noUnusedLocals`. **The coder adds the value imports**: `postExportFile` from `../shared/importFile`, `loadCharacters` from `./charactersState`, `loadSessions` from `./sessionsState`, `notifyFailure` from `../shared/notifyFailure`, `notifyWarning` from `../shared/notifyWarning`. Until the coder adds the last of those, `tests/app/ComposerCore.test.tsx`'s amended importer set (decision 5) cannot go green — that is expected at the red gate.
- **The abort predicate is this module's own, and needs both halves** (decision 17): a `signal?.aborted === true` check read **through a function call** so the compiler does not narrow it across an `await` (`logout.ts`'s idiom), **and** the widened, constructor-independent name predicate 030 landed in `exportDownloads.ts` — `typeof error === "object" && error !== null && "name" in error && error.name === "AbortError"` — not the `instanceof Error` form still present in five `admin/` copies. Neither reference module does both; the skeleton declares the `signal` parameter and writes no predicate.
- `src/app` imports nothing from `src/admin` (`tests/app/entryIsolation.test.ts`); no `parseInt`, no `…Id: number`, no `…id: number` anywhere in either new file, comments included (`tests/ids-are-strings.test.ts`); no new stylesheet, no new npm script, `.ts` only.

#### The three list-reload URL paths (recorded here and nowhere else)

The test-coders for steps 006 and 007 key their `fetch` stubs on these. Read out of the built
source, not out of the plan.

| Reload function | Module | Request |
|---|---|---|
| `loadCharacters(state, signal?)` | `src/app/charactersState.ts:36` → `charactersApi.ts:45-53` | **`GET /api/characters`**, with **`?include_archived=true` appended only when `state.showArchived` is `true`**. Response `{ characters: [...] }`. |
| `loadSessions(state, signal?)` | `src/app/sessionsState.ts:32` → `sessionsApi.ts:62-71` | **`GET /api/sessions`**, **never** with a query — it calls `fetchSessions(false, signal)` because the workspace list is working-only. Response `{ sessions: [...] }`. |
| `loadSectionSessions(state, signal?)` | `src/app/sessionsSectionState.ts:86` → `sessionsApi.ts:38-40, 74-87` | **`GET /api/characters/<encodeURIComponent(state.characterId)>/sessions`**, with **`?include_archived=true` appended only when `state.showArchived` is `true`**. Response `{ sessions: [...] }`. |

The two POST paths the effects issue are `POST /api/import` and
`POST /api/characters/<characterId>/import`. All three reload functions **never reject**: a failure
is swallowed into `status = "failed"`, and each already checks `signal?.aborted` plus
`error instanceof Error && error.name === "AbortError"`.

- Caller-compile edits (out of Source-files scope): **None.** Both new modules are unimported by anything in `src/` today (steps 007 and 008 are their first callers), and `notifyWarning`'s only existing caller, `src/app/ComposerCore.tsx:61` (`notifyWarning("paste-context-cost")`), still compiles unchanged — widening a union never breaks an existing member. No existing signature changed.

Gates, from `frontend/`: `npm run typecheck` → clean (both `tsconfig.json` and
`tsconfig.node.json`); `npm run build` → built, 7501 modules, four entries emitted (the >500 kB
chunk advisory is 030's pre-existing one). **No tests were run.**

### Step 007 — frozen interface (2026-10-05)

**Scope as narrowed by orchestrator decision 6: three Source files, not five.** `App.tsx` and
`CharacterScreen.tsx` are **untouched** — `App` already creates both states and passes them to
`WorkspaceShell` and the character routes, and `CharacterScreen` already receives
`sessions: SessionsState` and passes it to `SessionsSection`. `SessionsSection` gains **no new
prop**: the existing `sessions` prop (`SessionsSection.tsx:107`, passed at
`CharacterScreen.tsx:329`) is reused, which is what keeps the unlisted pre-030
`tests/app/SessionsSection.test.tsx` and `CharacterScreen.test.tsx` green. The step file's own
escape clause ("any file in this list that turns out to be unneeded is left untouched") authorises
this. **No behaviour was implemented:** every new handler is `throw new Error("not implemented")`,
with its parameters and the state it will read discarded first as `void <x>;` (`noUnusedParameters`
/ `noUnusedLocals` are hard errors; step 006 and 030's `void setExporting;` are the precedent).

#### `frontend/src/app/UserMenu.tsx` (changed) — the only new component signature

- `frontend/src/app/UserMenu.tsx` — `export type UserMenuProps` — **changed** (was
  `{ user: CurrentUser; compact: boolean }`). Frozen verbatim, doc comments elided:

  ```ts
  export type UserMenuProps = {
    user: CurrentUser;
    compact: boolean;
    charactersState: CharactersState;
    sessionsState: SessionsState;
  };
  ```

  Both new props are **required**, both are the single state `App` creates, and the names are
  `charactersState` / `sessionsState` exactly as the step file asks — there is no name clash here,
  unlike in `SessionsSection`. Type-only imports were added:
  `import type { CharactersState } from "./charactersState"` and
  `import type { SessionsState } from "./sessionsState"`.
- `frontend/src/app/UserMenu.tsx` — `export function UserMenu(props: UserMenuProps): React.JSX.Element`
  — **unchanged signature**; its return is now a **fragment** (`<>…</>`) holding the `Menu` and,
  as its sibling, the hidden file input. The gotcha is real: a `Menu` dropdown is portalled and
  unmounts on close, and clicking an item closes it, so a `FileButton` inside a `Menu.Item` takes
  its input with it and the `change` event never reaches React.
- **The menu item.** Label exactly **`Import…`** (one U+2026 HORIZONTAL ELLIPSIS, not three dots),
  `leftSection={<IconUpload size={ITEM_ICON_SIZE} stroke={ITEM_ICON_STROKE} />}` (= `size={16}`
  `stroke={1.5}`), `onClick={onImportMyData}`. Rendered for **every** role — it is outside the
  `user.role === "admin"` guard — immediately **after** 030's "Export my data" and **above**
  "Log out". No confirm, no dialog.
- **The hidden input**, rendered outside the `Menu`:

  ```tsx
  <input
    ref={importInputRef}
    type="file"
    accept={IMPORT_ACCEPT}
    aria-label={IMPORT_INPUT_LABEL}
    style={{ display: "none" }}
    onChange={onImportFileChosen}
  />
  ```

  - `const IMPORT_ACCEPT = ".json,application/json"` (module-private) — **`accept` is exactly
    `.json,application/json`**, extension and media type, in that order.
  - `const IMPORT_INPUT_LABEL = "Choose a file to import"` (module-private) — **the accessible
    name is exactly `Choose a file to import`**, per orchestrator decision 9. `007.context.md`'s
    suggested "Choose export file to import" is **not** used: it contains `export`, which the
    delivered admin control-name clauses reject. The name also avoids `view`, `open`, `show`,
    `browse`, `preview`, `inspect`, `reveal`, `peek`, `details`, `contents`, `display` and
    `expand`. It is the input's **whole** accessible name — there is no visible text and no
    `<label>` element.
  - `importInputRef` is `useRef<HTMLInputElement | null>(null)`.
  - `display: none` follows Mantine's own `FileButton`, so `userEvent.upload` reaches it.
- **Two stub handlers, both `throw new Error("not implemented")`:**
  - `const onImportMyData = (): void` — the item's click. Will call `importInputRef.current?.click()`
    and nothing else.
  - `const onImportFileChosen = (event: React.ChangeEvent<HTMLInputElement>): void` — the input's
    `change`. Will run `runOwnedImport(file, props.charactersState, props.sessionsState, navigate)`
    for the first chosen file and then clear the input's value so the same file can be chosen again
    (US-136.AC-2).
- **Value imports the coder must add:** `runOwnedImport` from `./importUploads` (step 006's frozen
  `runOwnedImport(file, charactersState, sessionsState, navigate, signal?)`). It is **not** imported
  yet — `noUnusedLocals` rejects an unused import while the bodies are stubs, exactly as recorded
  for step 006. `navigate` already exists in the component (`useNavigate()`), and
  `NavigateTo = (path: string) => void` accepts it directly.

#### `frontend/src/app/WorkspaceShell.tsx` (changed) — threading only

- **`WorkspaceShellProps` is unchanged.** It already receives `characters: CharactersState` and
  `sessions: SessionsState`.
- **Both** `UserMenu` call sites were updated — missing one would ship a half-wired control, since
  the two are mutually exclusive branches of the `showsRail(shell, narrow)` ternary:
  - the **rail / compact** site (was `:123`, inside `<Box mt="auto" w="100%">`) →
    `<UserMenu user={user} compact charactersState={characters} sessionsState={sessions} />`;
  - the **expanded / wide** site (was `:142`, inside `<Box w="100%">`) →
    `<UserMenu user={user} compact={false} charactersState={characters} sessionsState={sessions} />`.
- Two prop doc comments were corrected, because `sessions` said "read by nothing in this file" and
  that is no longer true.

#### `frontend/src/app/SessionsSection.tsx` (changed) — no prop change, one new control

- **`SessionsSectionProps` is unchanged:** `{ characterId: string; sessions: SessionsState }`. The
  existing `sessions` prop is reused and **no `sessionsState` prop was added.**
- `export const SessionsSection = observer(function SessionsSection(props: SessionsSectionProps): React.JSX.Element)`
  — **unchanged signature.**
- **Where the button sits: in the inline-start row, immediately after the "Start session" `Button`,
  inside the existing `<Group gap="sm" align="flex-end">` that also holds the "Setup" `Select`** —
  *not* in the header `Group gap="sm"` that holds the `Title` and the "Show archived sessions"
  `Switch`. Rationale: "Start session" and "Import session" both bring a session into being, so
  they read as a pair; that row already aligns buttons against a labelled `Select`; and the header
  stays the heading plus its one view toggle. It renders in every list state (loading, failed,
  empty, ready), because the start row is outside `renderList()`.
- **The control**, frozen:

  ```tsx
  <FileButton
    accept={IMPORT_ACCEPT}
    resetRef={importResetRef}
    onChange={onImportSessionFileChosen}
  >
    {(fileButtonProps) => (
      <Button
        {...fileButtonProps}
        variant="default"
        leftSection={<IconUpload size={ICON_SIZE} stroke={ICON_STROKE} />}
        loading={importing}
      >
        Import session
      </Button>
    )}
  </FileButton>
  ```

  - Label exactly **`Import session`**; `variant="default"`; icon `IconUpload` at this module's
    `ICON_SIZE = 18` / `ICON_STROKE = 1.5` — the metric its sibling "Start session" `IconPlus`
    uses. (The `16` in the brief is the *menu* metric, and this is not a menu item.)
  - `const IMPORT_ACCEPT = ".json,application/json"` (module-private, same literal as `UserMenu`'s).
  - Mantine `FileButton` is used here because the row is not inside a `Menu`; `@mantine/core` is
    7.17.8, `children` is the render prop `({ onClick }) => ReactNode` and is spread onto the
    `Button`, and `onChange` receives `File | null`.
- **Component-local in-flight state:** `const [importing, setImporting] = useState(false)`, read by
  `loading={importing}`. Nothing about an import was added to `SessionsSectionState`, and
  `sessionsSectionState.ts` was **not** edited.
- `const importResetRef = useRef<() => void>(null)` — Mantine fills it with `FileButton`'s `reset`,
  which clears the hidden input's value for a repeat choice.
- **One stub handler:** `const onImportSessionFileChosen = (file: File | null): void` —
  `throw new Error("not implemented")`. Will set `importing`, run
  `runSessionImport(characterId, file, props.sessions, () => loadSectionSessions(state, listControllerRef.current?.signal))`
  — step 006's frozen `runSessionImport(characterId, file, sessionsState, reloadSection, signal?)`,
  whose `ReloadSection = () => Promise<void>` the existing loader already satisfies — then clear
  `importing` and call `importResetRef.current?.()`.
- **Value import the coder must add:** `runSessionImport` from `./importUploads`.
  `loadSectionSessions` is **already imported** in this module.

#### Cross-cutting

- Caller-compile edits (out of Source-files scope): **None.** `UserMenu`'s only caller in `src/` is
  `WorkspaceShell`, which is itself a Source file; `WorkspaceShellProps`, `AppProps`,
  `CharacterScreenProps`, `CharacterRouteProps` and `SessionsSectionProps` are all unchanged, so
  nothing else in `src/` needed a line.
- Decision 20 honoured: no `parseInt` and no `…Id: number` anywhere added (`characterId` and
  `session_id` stay strings); `src/app` imports nothing from `src/admin`; no new stylesheet, no new
  npm script, `.tsx` only; no case-colliding module name (no new module at all).
- Neither control opens a confirm or any `role="dialog"` element. No notification call site was
  added to either file.

**Expected typecheck failures — authorised in advance, left unfixed, no test file touched.**
`UserMenu` gaining two *required* props breaks exactly two delivered test files, both already in
step 007's Test files; the test-coder supplies the props next phase. The new props were **not** made
optional to silence this. Verbatim, and these are the **only** two errors `npm run typecheck`
reports:

```
tests/app/UserMenu.export.test.tsx(161,10): error TS2739: Type '{ user: CurrentUser; compact: false; }' is missing the following properties from type 'UserMenuProps': charactersState, sessionsState
tests/app/UserMenu.test.tsx(57,10): error TS2739: Type '{ user: CurrentUser; compact: boolean; }' is missing the following properties from type 'UserMenuProps': charactersState, sessionsState
```

Gates, from `frontend/`: `npm run typecheck` → **the two expected test-file errors above and
nothing else**; zero errors under `src/`, and `tsconfig.node.json` is clean. `npm run build` →
**built**, 7501 modules transformed, four entries emitted (the >500 kB chunk advisory and the
`__dirname` config warning are 030's pre-existing ones). **No tests were run.**

### Step 008 — frozen interface (2026-10-05)

**Two Source files, both delivered by 030, both changed.** No new module, no new type outside
`databasePageState.ts`, and `DatabasePageState` gains **three observable fields and no methods** —
`Object.getOwnPropertyNames(DatabasePageState.prototype)` is still `["constructor"]` and
`makeAutoObservable(this, {}, { autoBind: true })` is untouched. Every new function body and every
new handler is `throw new Error("not implemented")`, with its parameters and the symbols it will
call discarded first as `void <x>;` (`noUnusedParameters` / `noUnusedLocals` are hard errors; steps
006 and 007 set the idiom). **No behaviour was implemented.**

#### The three new fields (decision 8) — `ALLOWED_FIELDS` must list exactly these names

**`importFile` / `importStatus` / `importErrorMessage`** — the recommended set, taken as frozen.
Verbatim declarations, doc comments elided:

```ts
importFile: ReadableTextFile | null = null;
importStatus: DatabaseImportStatus = "idle";
importErrorMessage: string | null = null;
```

- **`importFile: ReadableTextFile | null = null`** — the chosen file, `null` when none. **Non-null
  is what makes the replace confirm open**; there is no stored open/confirm flag, so
  `databaseActions.test.tsx:875-878` keeps its premise. The type is step 006's structural
  `ReadableTextFile` (`{ text(): Promise<string> }`), imported type-only as
  `import type { ReadableTextFile } from "../shared/importFile"` — a real `File` from
  `FileButton`'s `onChange` is assignable, and so is a hand-rolled `{ text: async () => "..." }`
  double, which is why the field is not typed `File | null`. MobX leaves a `File` instance
  unconverted (class instances are not made deeply observable); a plain-object double becomes an
  observable object whose `text()` still resolves.
- **`importStatus: DatabaseImportStatus = "idle"`** — the named union below, not a boolean.
- **`importErrorMessage: string | null = null`** — the import's **own** message slot, separate from
  the drift `errorMessage` and from 030's `exportErrorMessage`, so no failure overwrites another's.

All three names pass the two **unamended** delivered guards: none matches
`/open|modal|confirm|target|dialog|lossy|pending/i` (the plan's own phrase "pending import file"
would have tripped it) and none matches `/^id$|Id$|_id$|ID/`. The **full, sorted** own-field set of
a fresh `DatabasePageState` is now, for both independent `ALLOWED_FIELDS` arrays
(`databasePage.test.tsx:946-955` and `databaseActions.test.tsx:1256-1264`):

```
applyingTable, errorMessage, exportErrorMessage, exportSizeBytes, exportStatus,
importErrorMessage, importFile, importStatus, rows, status
```

#### `frontend/src/admin/databasePageState.ts` (changed)

- `frontend/src/admin/databasePageState.ts` — `export type DatabaseImportStatus = "idle" | "importing"` — **new**. The named two-value union, shaped exactly like 030's `DatabaseExportStatus` (`"idle" | "exporting"`), declared immediately after it.
- `frontend/src/admin/databasePageState.ts` — `export function chooseImportFile(state: DatabasePageState, file: ReadableTextFile): void` — **new, stub**. Synchronous, returns `void`. Will store `file` in `importFile` and clear `importErrorMessage` in one `runInAction`. The parameter is **non-nullable**: the page guards `FileButton`'s `File | null` before calling. Sends nothing and reads nothing from the file.
- `frontend/src/admin/databasePageState.ts` — `export function cancelImport(state: DatabasePageState): void` — **new, stub**. Synchronous, returns `void`. Will clear `importFile` (which closes the confirm) inside `runInAction` and touch nothing else.
- `frontend/src/admin/databasePageState.ts` — `export async function importDatabase(state: DatabasePageState, signal?: AbortSignal): Promise<void>` — **new, stub**. 030's `exportDatabase(state, signal?)` naming and shape idiom, including the never-reject contract.
- **The import route path is documented in `importDatabase`'s jsdoc, not frozen as a constant** — 030's `DATABASE_EXPORT_PATH` is module-private, and an unused module-private const trips `noUnusedLocals` while the body is a stub (same precedent as step 006's unreadable-file message). The path is **`/api/admin/database/import`**, `POST`, answering **204**. The coder adds `const DATABASE_IMPORT_PATH = "/api/admin/database/import";` beside 030's export constant.
- **Value imports the coder must add:** `postExportFile` from `../shared/importFile` (step 006's frozen `postExportFile<T = unknown>(path, file, signal?)`; called as `await postExportFile(DATABASE_IMPORT_PATH, file, signal)` — the 204 resolves `undefined` as `unknown` and nothing is read from it) and `documentNavigation` added to the **existing** `from "../shared/api"` value import (decision 16: `documentNavigation` is exported from `api.ts`; `ApiError` is not). Only the type import is present today.
- **Reused as built, not re-declared:** the module-private `isAbortRejection` and `failureMessageOf(error, fallback)` already give `importDatabase` both halves of the abort check and the `ApiError`-message pass-through for `The chosen file is not a readable export.`.
- No notification import was added (decision 18); the module still imports nothing from `@mantine/notifications` or `notifyFailure`.

#### `frontend/src/admin/DatabasePage.tsx` (changed)

- **`DatabasePageProps` and both component signatures are unchanged**: `export type DatabasePageProps = { state: DatabasePageState }`, `export const DatabasePage = observer(function DatabasePage(props: DatabasePageProps): React.JSX.Element)`, `export function DatabaseRoute(): React.JSX.Element`.
- **The Import control**, in 030's existing page-level `<Group gap="sm" wrap="nowrap">`, **immediately after the Export `Button`** — so the DOM order of controls outside the report table is Export button, the hidden file input, Import button, which is the `["Export","Import"]` order decision 7's amended clause pins once `input[type="file"]` is filtered out:

  ```tsx
  <FileButton accept={IMPORT_ACCEPT} resetRef={importResetRef} onChange={onImportFileChosen}>
    {(fileButtonProps) => (
      <Button
        {...fileButtonProps}
        variant="default"
        leftSection={<IconUpload size={ICON_SIZE} stroke={ICON_STROKE} />}
        loading={state.importStatus === "importing"}
      >
        Import
      </Button>
    )}
  </FileButton>
  ```

  - Button label exactly **`Import`** — one word, no ellipsis; `variant="default"` and
    `leftSection` `IconUpload` at this module's existing `ICON_SIZE = 18` / `ICON_STROKE = 1.5`
    (the metric its neighbour Export's `IconDownload` uses).
  - **`const IMPORT_ACCEPT = ".json,application/json"`** (module-private) — the `accept` value is
    exactly **`.json,application/json`**, extension then media type, the same literal step 007's
    two controls use.
  - **The hidden `<input type="file">` has no accessible name**: no `aria-label`, no `inputProps`,
    no `<label>`. It is the only `input` on the page, so the test-coder locates it with
    `container.querySelector('input[type="file"]')` for `userEvent.upload`. Leaving it unnamed
    satisfies decision 9 by construction — it carries none of `export`, `view`, `open`, `preview`,
    `browse`, `inspect`, `reveal`, `peek`, `details`, `contents`, `display`, `expand`, `show` — and
    matches 007's `SessionsSection` `FileButton`, which is also unnamed.
  - It renders **outside** the `state.status !== "ready"` gate, so it is present and not disabled in
    every drift state (DoD-1), and it is never `disabled`.
- **`const importResetRef = useRef<() => void>(null)`** — Mantine fills it with `FileButton`'s
  `reset`, which clears the input's value for a repeat choice.
- **Three stub handlers**, all `throw new Error("not implemented")`:
  - `const onImportFileChosen = (file: File | null): void` — `FileButton`'s `onChange`. Will call
    `chooseImportFile(state, file)` for a non-null file (which **opens** the confirm) and then
    `importResetRef.current?.()`. **Makes no request** (DoD-2).
  - `const cancelImportChoice = (): void` — the confirm's `onCancel`. Will call
    `cancelImport(state)` and nothing else. Named so it does not shadow the imported
    `cancelImport`.
  - `const confirmImport = (): void` — the confirm's `onConfirm`. Will call
    `importDatabase(state, currentSignal())` through the existing
    `void ... .catch(ignoreRejection)` idiom.
- **The replace `ConfirmModal`**, rendered as a second, always-mounted sibling after 030's sync
  confirm (a closed Mantine `Modal` mounts nothing, so only one dialog is ever in the DOM). Props
  frozen verbatim, with the `008.context.md` strings in module-private constants:

  ```tsx
  <ConfirmModal
    opened={state.importFile !== null}
    title={IMPORT_CONFIRM_TITLE}
    consequence={IMPORT_CONFIRM_CONSEQUENCE}
    confirmLabel={IMPORT_CONFIRM_LABEL}
    confirmColor="red"
    loading={state.importStatus === "importing"}
    onCancel={cancelImportChoice}
    onConfirm={confirmImport}
  />
  ```

  - `IMPORT_CONFIRM_TITLE = "Replace the whole database?"`
  - `IMPORT_CONFIRM_CONSEQUENCE` is one sentence, written as two concatenated literals, whose value
    is exactly `Everything in this instance, including your own account, is replaced by the contents of the file, and you will be signed out.`
  - `IMPORT_CONFIRM_LABEL = "Replace database"` → the confirm button's accessible name. Cancel's is
    `Cancel`, fixed in `ConfirmModal`.
  - `opened` is **derived**, not stored: the dialog is open exactly while `state.importFile !== null`.
- **A fourth inline red `Alert`**, in its own slot immediately after 030's export-error Alert and
  **before** the export size line, so no message ever overwrites another and the size line is
  untouched: `{state.importErrorMessage !== null && (<Alert color="red" mb="md">{state.importErrorMessage}</Alert>)}`.
- **Nothing about the file's contents is rendered** anywhere, before or after a choice (DoD-7): no
  row count, no table listing, no name, no size. The confirm text names the action only.
- Neither file imports `notifyFailure` or `@mantine/notifications` (decision 18,
  `databasePage.test.tsx:815-822`). No `parseInt`, no `Id`-shaped name and no bare word `id` was
  added to either file's code or string literals (decision 8 / 20; verified by scan — the single
  pre-existing match is a stripped comment in `databasePageState.ts:34`). No placeholder for Rebuild
  index, and neither file's new text contains `rebuild` or `re-index`. No new stylesheet, no new npm
  script, `.ts`/`.tsx` only.

- Caller-compile edits (out of Source-files scope): **None.** No existing signature changed —
  `DatabasePageProps`, `DatabaseRoute` and every 030 free function are untouched, so the admin
  entry's route mount needed no line.

Gates, from `frontend/`: `npm run typecheck` → **only step 007's two authorised test-file errors**
(`tests/app/UserMenu.export.test.tsx(161,10)` and `tests/app/UserMenu.test.tsx(57,10)`, both
TS2739 missing `charactersState`/`sessionsState`); **zero** errors under `src/`, and
`tsconfig.node.json` is clean. `npm run build` → **built**, 7501 modules transformed, four entries
emitted (the >500 kB chunk advisory and the `__dirname` config warning are 030's pre-existing
ones). **No tests were run, and no file under `frontend/tests/` was read or touched.**


## Tests

### Step 001 — tests (2026-10-05)

- `backend/tests/test_transfer_import_validation.py` (new) — **24 test functions, 76 collected cases** — covers DoD-1..DoD-12.
  - Fixtures: a file-local `engine` over `db_engine` that runs `schema.metadata.create_all` and seeds two
    users (isolation), an `llm_servers` + `models` pair, a character carrying the designated model pair,
    a setup, two sessions, the three message states (settled head, buried row, current zone) and a memo at
    each of the four scopes — so **every exported table has at least one row at every granularity**. All ids
    above 2**60. No monkeypatching; no SQL beyond the seed and the test side's own `select` snapshots.
  - Every body under test is a **deep copy of a 030 exporter's envelope with exactly one mutation**
    (`export_user` / `export_character` / `export_session` / `export_database`).
  - Case groups → DoD ids:
    - DoD-1 (5 cases) — all four granularities validate when accepted; keys in `sorted_tables` order; every row
      equals the stored row column-for-column with the declared Python types; a second case pins ids/bools/both
      enum columns (`users.role` as a `Role` value, `memos.scope` as `str`)/timestamps/nulls cell by cell.
    - DoD-2 (14) — each of the six header keys missing; four non-object bodies; an extra header key; a wrong
      `format`; `granularity` `"everything"`; and the precedence case (wrong `format` **and** wrong `version`
      still answers `not_an_export`).
    - DoD-3 (5) — `version` one higher, `version` as a string, version-before-schema precedence;
      `schema_version` one higher and one lower.
    - DoD-4 (2) — a valid `session` and a valid `database` envelope against accepted {`user`,`character`}.
    - DoD-5 (7) — user payload missing `memos`; a character payload with an extra `llm_servers` / `models` /
      `auth_sessions` / `translations`; `messages` as an object; a row that is a string.
    - DoD-6 (19) — the nine named cell/row faults through `validate_envelope`, the same faults through
      `deserialize_row` directly, plus a positive "the unmutated row deserializes" anchor. Decision 15's three
      only-catchable-here cases (bad enum string, id above `2**63-1`, JSON `1` in a `Boolean`) are explicit.
    - DoD-7 (3) — the `user` `users` row omitting exactly `USER_EXCLUDED_COLUMNS` validates (envelope and
      `allow_missing` paths); including `password_hash` is refused; at `database` granularity omitting it is refused.
    - DoD-8 (5) — two / zero `characters`, two `sessions`, two `users` rows; plus `ROOT_TABLES`'s content.
    - DoD-9 (9) — `detail` is exactly `{"reason": …}`; a payload-only sentinel seeded on the malformed memo
      appears in neither `detail`, message, `repr` nor `to_wire()`; each of the five reasons' message equals the
      sentence pinned in `001.context.md`; the five reason constants are distinct.
    - DoD-10 (1) — `DatabaseNotEmptyError`: `database_not_empty`, 409, `detail == {}`, pinned default message.
    - DoD-11 (4) — `GRANULARITY_TABLES["database"]` **derived** from `sorted_tables` minus the two exclusions;
      keys equal `EXPORT_GRANULARITIES`; the other three sets equal the key sets 030's exporters produce.
    - DoD-12 (2) — `is_id_column(column, primary_key_names)` agrees with 030's rule for every column of every
      registry table (and on four named columns); a database export's `memos.scope_id` and
      `characters.model_server_id` are still decimal strings and deserialize back to the seeded ints.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓,
  DoD-11 ✓, DoD-12 ✓, DoD-13 [manual/live, no test].
- No reason string literal is re-typed: the five `REASON_*` constants from `app.errors` key the pinned-message
  table. No existing test file was read or touched; no test was run.

### Step 002 — tests (2026-10-05)

- `backend/tests/test_transfer_import_owned.py` (new) — **19 test functions, 25 collected cases** —
  covers DoD-1..DoD-11.
  - **`import_owned` and `OwnedImportResult` are the only step-002 symbols named.** No `_`-prefixed
    name from `transfer_import.py` is imported or referenced: the remap engine, the reference policy
    and the payload writer are exercised only through `import_owned` and the database it writes
    (`002.context.md`: "Do not call the remap engine directly"). Step 001 contributes
    `ExportInvalidError` and the `REASON_*` constants; **no reason string literal is re-typed**.
  - Fixtures: a file-local `engine` over `db_engine` that runs `schema.metadata.create_all` and seeds
    **three** users — A owns the exported tree, B is the isolation witness (R5), C owns nothing and is
    the caller, so a second `export_user(C)` *is* the import. A's tree: one server with **two**
    `models` rows (so every seeded `(model_server_id, model_name)` pair exists and DoD-1 can compare
    `model_name` like any other column), two characters (one archived), three setups (one archived),
    three sessions (one archived, one with no setup), **two** settled groups plus two zone rows in one
    session, a memo at each of the four scopes, and one memo on the second character. Every id above
    `2**60`. `related_to` is set by a second UPDATE, so each buried row carries a **lower** id than its
    own head (030's outcome note) — the case the two-pass write exists for. No FTS and no vec0 table is
    created by the fixture, which is DoD-10's premise. A **real** `SnowflakeGenerator`; no
    monkeypatching.
  - Envelopes come from 030's exporters (`export_user` / `export_character` / `export_session` /
    `export_database`) over the seeded rows; a malformed body is a deep copy with exactly one mutation.
  - The id correspondence is recovered by **pairing rows by ascending id per table** — either payload
    against payload, or payload against the ids a before/after snapshot shows the import added. Sound
    because DoD-6 fixes the minting order, which is why DoD-6 is asserted **independently**, on message
    text sequences and the two settled groups, never on the pairing.
  - Case groups → DoD ids:
    - DoD-1 (2) — A's `user` export imported as C, then re-exported: the same table set, the same counts,
      every **value column derived from `schema.metadata`** equal (so a new registry column cannot slip
      past), every reference rewritten through the correspondence, and `character_ids` ascending; the
      second case walks all four memo scopes.
    - DoD-2 (1) — the payload `users` row's `username`, `rp_language` and `preferred_language` are
      mutated before the import; C's row is unchanged in **every** column, the id set of `users` is
      unchanged, and the mutated username exists nowhere.
    - DoD-3 (1) — a `character` export: exactly one new character owned by the caller, its setups, its
      sessions (an archived one asserted present first, R6), their messages, the three in-payload memo
      scopes each naming the new row of the right table, and `character_ids == [that one id]`.
    - DoD-4 (2) — imported ids intersect neither the pre-import id set nor the payload id set, and no
      table outside the payload gains a row; re-importing into A's own account leaves every pre-existing
      row of every table byte-for-byte identical while writing a full second copy.
    - DoD-5 (1) — the same `character` export twice through **one shared generator** (two generators on
      one node id could collide inside a millisecond): disjoint id sets across every table, two complete
      copies, both calls returning normally. "Nothing warns" has no service-level channel —
      `OwnedImportResult` carries only the granularity and the ids — and that is stated in the test.
    - DoD-6 (3) — per-session message **texts** in new-id order equal the originals in old-id order;
      each of the two buried rows points at the new id of **its own** head (two distinct heads seeded) and
      still has `settled_at IS NULL`; the record and zone text sets come back out of `schema.settled_entries`
      / `schema.current_zone`, executed as Core `select()` objects (decision 14).
    - DoD-7 (2) — a pair that exists in `models` is kept on both a character and a session; a pair whose
      model name is in no `models` row, and one naming an unknown `model_server_id`, leave **both** columns
      null while an untouched pair survives. Both tests re-assert the both-or-neither CHECK over every
      `characters` / `sessions` row.
    - DoD-8 (6 cases, one parametrized test) — the six named faults (setup→absent character, session→absent
      setup, buried→absent message, `scope='user'` at character granularity, `scope='setup'`→absent setup,
      a `characters` row carrying another user's `user_id`). Each asserts `ExportInvalidError` **and**
      `detail == {"reason": REASON_MALFORMED_PAYLOAD}` **and** that the row counts of **every**
      `schema.metadata.sorted_tables` table are unchanged.
    - DoD-9 (2) — every written row of every imported table carries C's `user_id` (the payload is asserted
      to carry A's first); A's and B's rows are compared row-by-row before and after, so nothing changed and
      no row landed under them.
    - DoD-10 (3) — `memo_fts` / `message_fts` are asserted **absent** first, then exist; **every** imported
      memo body matches under its **new** id, both imported record rows match under theirs, and every zone
      **and** buried token returns nothing (harvest E9's two precisions). Two further cases: no `memo_vec` /
      `session_vec` row exists after an import when the tables are absent (they are not created), and when
      they are pre-created with 024's `ensure_vector_tables` they stay empty — each paired with a positive
      "rows were in fact imported" anchor.
    - DoD-11 (2) — a `session` and a `database` envelope each raise `ExportInvalidError` with
      `detail == {"reason": REASON_WRONG_GRANULARITY}`, and store nothing.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓,
  DoD-11 ✓, DoD-12 [manual/live, no test].
- No refusal clause is satisfiable by the skeleton's `NotImplementedError`: every one pins the specific
  error class, its `reason` and its exact `detail`. No existing test file was read or touched; no test was
  run; no source file was opened.

### Step 003 — tests (2026-10-05)

- `backend/tests/test_transfer_import_session.py` (new) — **16 test functions, 20 collected cases** —
  covers DoD-1..DoD-10.
  - **`import_session` is the only step-003 symbol named.** The session reference policy and the
    target-character lookup are module-private, so both are exercised only through `import_session` and
    the database it writes; no `_`-prefixed name from `transfer_import.py` is imported or referenced.
    Step 001 contributes `ExportInvalidError` and the `REASON_*` constants (**no reason string literal
    is re-typed**); `CharacterNotFoundError` comes from `app/errors.py`.
  - Seeding shape per `003.context.md`: a file-local `engine` over `db_engine` runs
    `schema.metadata.create_all` and seeds two users. **A** owns character **X** (the source session's
    character, which stays present in every test), the target **C**, and an **archived** target;
    **B** owns one character and one session as the R5 witness. X holds a setup, the source session
    (with a setup, a non-null `archived_at`, and a distinguishable value in each of DoD-8's five
    fields, and a `(model_server_id, model_name)` pair that **does** exist in `models`), a second
    session whose pair does **not** exist in `models`, six messages in two settled groups plus two zone
    rows, two session memos, and a character / setup / user memo that a session export never carries
    (DoD-2's witnesses). Every id above `2**60`; each buried row carries a **lower** id than its own
    head (set by a second UPDATE), the case the two-pass write exists for. No FTS and no vec0 table is
    created by the fixture (DoD-10's premise). A **real** `SnowflakeGenerator`; no monkeypatching.
  - Envelopes come from 030's exporters (`export_session`, plus `export_user` / `export_character` for
    DoD-9); a malformed body is a deep copy with exactly one mutation. The id correspondence is
    recovered by **pairing rows by ascending id**, as step 002's tests do; message *order* is asserted
    independently on the text sequence and on the three message states.
  - Case groups → DoD ids:
    - DoD-1 (2) — exactly one new session, under C, owned by the caller; all six messages in the same
      order with every value column (derived from `schema.metadata`) preserved, `session_id` re-pointed
      and each buried row naming the new id of **its own** head; the record / buried / zone text sets
      read out of `schema.settled_entries` / `buried_messages` / `current_zone` as Core `select()`
      objects (decision 14); both session memos re-pointed at the new session id; and the returned int
      *is* the one added `sessions` id.
    - DoD-2 (1) — the payload's `character_id` is asserted to be X and X's row to still exist, then the
      stored `character_id` is C; X's session id set is unchanged (non-empty first) and every memo the
      import added is `scope='session'` on the new id, so X gains no session and no memo.
    - DoD-3 (1) — the payload `setup_id` is asserted non-null first, then the stored `setup_id` is
      null, the `setups` id set is unchanged, and no added memo has scope `setup`.
    - DoD-4 (1) — the target's `archived_at` is asserted first, then the import adds exactly one
      session under it and the target is still archived.
    - DoD-5 (3 cases, 2 tests) — a foreign target and a nonexistent id each raise
      `CharacterNotFoundError` with `code == "character_not_found"` and `http_status == 404`, with the
      row counts of **every** `sorted_tables` table unchanged; a second test proves the two are
      indistinguishable (same type, code, status, message, `detail == {}`) after asserting that one
      target exists under B and the other exists nowhere.
    - DoD-6 (4 cases, one parametrized test) — a memo whose scope is `character`, `setup` or `user`,
      and a `session` memo whose `scope_id` is not the payload session's id, each raise
      `ExportInvalidError` with `detail == {"reason": REASON_MALFORMED_PAYLOAD}` and leave every
      table's row count unchanged.
    - DoD-7 (1) — two imports of one export through **one shared generator** (two generators on one
      node id could collide inside a millisecond): two distinct sessions, disjoint message id sets and
      disjoint memo id sets each of the original's size, and the original session row, its messages and
      its memos byte-for-byte identical to the snapshot taken first.
    - DoD-8 (3) — `archived_at`, `last_used_at`, `rp_language`, `preferred_language` and
      `system_prompt` equal the exported values (and the seeded literals), with the source session
      asserted archived; a pair that exists in `models` is kept on both columns; a pair that does not
      leaves **both** null while the other preserved fields still come across.
    - DoD-9 (3) — a `user` and a `character` envelope each give `wrong_granularity` and store nothing;
      the order test first proves the chosen target answers `CharacterNotFoundError`, then sends the
      same envelope with `schema_version = SCHEMA_VERSION + 1` to that same foreign target and asserts
      `schema_mismatch` instead, i.e. validation precedes the lookup.
    - DoD-10 (1) — `message_fts` is asserted absent first and the vec0 tables are pre-created with
      024's `ensure_vector_tables` (so "no row" is measured against tables that exist); after the
      import both imported record tokens match under their **new** ids, the imported buried and zone
      ids are absent from their tokens' matches (harvest E9: `message_fts` skips buried rows as well as
      zone rows), `session_vec` still exists and holds no row, and `memo_vec` holds none either.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 [manual/live, no test].
- No clause is satisfiable by the skeleton's `NotImplementedError`: every refusal pins the specific
  error class **and** its exact `detail`, every "stores nothing" clause is paired with before/after row
  counts of every `sorted_tables` table, and every "nothing changed" clause first proves the rows it is
  about exist. No test was run; no source file was opened.

### Step 004 — tests (2026-10-05)

- `backend/tests/test_transfer_import_database.py` (new) — **16 test functions, 22 collected cases** —
  covers DoD-1..DoD-12.
  - **`import_database(connection, body)` is the only step-004 symbol named**, called with no request
    user and no generator. The eligibility guard, the scope-target check, the wipe and the vector drop
    are module-private, so each is observed only through `import_database` and the two databases it
    touches; no `_`-prefixed name from `transfer_import.py` is imported or referenced. **Ruling 22
    honoured:** no identity-policy symbol is looked for or asserted on — "ids are preserved" is
    asserted as restored rows carrying the source's own seeded ids. Step 001 contributes
    `DatabaseNotEmptyError`, `ExportInvalidError` and the `REASON_*` constants (**no reason string
    literal is re-typed**); 030 contributes the four exporters, `DATABASE_EXCLUDED_TABLES` and
    `SCHEMA_VERSION`; 024 contributes `ensure_fts_tables`, `ensure_vector_tables`,
    `vector_table_dimension` and the four table-name constants.
  - **Two databases** (`004.context.md` §"Fixtures guidance", harvest D4): the **source** is a second
    engine built from `db_settings.model_copy(update={"data_dir": tmp_path / "source",
    "db_filename": "source.sqlite"})` plus `get_engine`, exactly the
    `tests/test_admin_db_router.py:1413-1446` idiom; the **target** is `db_engine` itself. Both files
    sit inside the per-test `tmp_path`; no path under `backend/data/` and no `RPHELPER_DB_PATH` appears
    anywhere, and `backend/.env` was never opened. `conftest.py` is untouched; every schema comes from
    `schema.metadata.create_all`, so the FTS and vec0 tables are absent unless a test creates them.
  - Seeds. **Source:** two users (an admin and a roleplayer, each password hashed through
    `services/passwords.py`), two characters of which one is archived, two setups, two sessions of
    which one is archived, six messages as two settled groups plus two zone rows (each buried row
    carrying a **lower** id than its own head), a memo at **each of the four scopes**, an `llm_servers`
    row whose `api_key_ref` is `"$SOURCE_SERVER_KEY"`, and a **designated** `models` row with
    `embedding_dim = 8`. **Target:** exactly one admin, plus a character, a setup, a session, a settled
    message, a memo, a `translations` row, an `auth_sessions` row, a server and a model — every one of
    them something `context.md` §"Database import" says the wipe deletes. The two id spaces are
    disjoint. The table lists are derived from `schema.metadata.sorted_tables` minus
    `DATABASE_EXCLUDED_TABLES`, never hand-listed; `translations` is reached as
    `schema.metadata.tables["translations"]` (the house idiom — `app.db.schema` exposes no attribute).
  - Case groups → DoD ids:
    - DoD-1 (2) — the source is first asserted to be the instance DoD-1 lists and the target to be
      non-empty (one admin, their character, their `auth_sessions` row); then every payload table's
      `SELECT *` ordered by primary key equals the source's, the users / characters / sessions / memos
      id lists equal the **seeded source constants**, and the source itself is unchanged. A second test
      names the carried columns one by one under their source ids: the archived character's
      `archived_at`, the `"$NAME"` key ref, `is_embedding_designated` + `embedding_dim`, the admin's
      `Role.ADMIN`, and the four `(scope, scope_id)` pairs.
    - DoD-2 (2) — the previous admin, their character, session and memo ids are asserted present first,
      then absent; both excluded tables hold no rows. The password test hashes a chosen password
      through `services/passwords.py` at seed time and verifies it against the **restored** hash
      through `verify_password`, with the wrong password proving the check discriminates.
    - DoD-3 (1) — every `sorted_tables` table is asserted empty first, then the import restores the
      whole payload onto that bootstrap shape.
    - DoD-4 (3 cases, one parametrized test) — two admins / an admin + a roleplayer / one roleplayer:
      each raises `DatabaseNotEmptyError` with `detail == {}`, and a whole-database snapshot (every row
      of every `sorted_tables` table, taken after proving it is non-empty) is unchanged.
    - DoD-5 (1) — on two admins, an envelope whose `schema_version` is `SCHEMA_VERSION + 1` still
      raises `DatabaseNotEmptyError` (not `ExportInvalidError`), `detail == {}`, snapshot unchanged.
    - DoD-6 (3 cases, one parametrized test) — two `users` rows sharing a username (UNIQUE), a `setups`
      row whose `character_id` names no payload character (FK), and a `scope='character'` memo whose
      `scope_id` names no payload character: each `ExportInvalidError` with
      `reason == REASON_MALFORMED_PAYLOAD` **and** `detail == {"reason": "malformed_payload"}`, with
      the full snapshot unchanged and the original admin plus their `auth_sessions` row still there.
      Decision 15 respected: no enum and no out-of-range-id case is written here.
    - DoD-7 (3 cases, one parametrized test) — `user`, `character` and `session` envelopes from 030's
      exporters each raise `wrong_granularity` with the exact `detail`, snapshot unchanged.
    - DoD-8 (3 tests) — seeded with `ensure_vector_tables(conn, 8)` and serialized float32 rows:
      present-with-rows (dimension **and** stored vectors asserted) → after a successful import both
      `vector_table_dimension` answers are `None` and `sqlite_master` has neither; absent before →
      absent after and the import still restores the payload; the DoD-6 UNIQUE case → both tables still
      exist, still at dimension 8, still holding the same keys and the same float values.
    - DoD-9 (1) — `ensure_fts_tables` is called on the target **before** the import and the target's
      memo and record tokens are asserted to match under the target ids, so their later absence is the
      wipe's delete triggers; afterwards both FTS tables exist, two restored memo tokens and both
      restored record tokens match under their **preserved** ids, both target-only tokens match
      nothing, and FTS5 `integrity-check` passes on both tables.
    - DoD-10 (1) — the source's `settled_entries` and `current_zone` id lists are pinned against the
      seeded head and zone constants first (Core `select()` objects executed directly, decision 14);
      after the import both buried rows name their own **preserved** head id and both selectables
      return the same ids as the source.
    - DoD-11 (1) — the duplicated row carries a sentinel username that could only come from the
      payload; `detail` is exactly `{"reason": "malformed_payload"}`, and the sentinel appears in
      neither `str(error)`, `error.message`, `error.args` nor the JSON of `to_wire()`.
    - DoD-12 (1) — seeded at 8 (asserted), replaced, then `ensure_vector_tables(conn, 16)` is called:
      it does not raise, and both tables report dimension 16 and hold no rows.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 [manual/live, no test].
- No clause is satisfiable by the skeleton's `NotImplementedError`: every refusal pins the specific
  error class **and** its exact `detail`, every "unchanged" clause first proves the rows it is about
  exist, and every vector limb asserts dimension and stored contents rather than mere presence. No
  test was run; no source file was opened.

### Step 005 — tests (2026-10-05)

**Two new files, 15 test functions in total.**

- `backend/tests/test_transfer_import_router.py` — **10 tests** — covers DoD-1 .. DoD-7 and DoD-11 for
  the two roleplayer routes `POST /api/import` and `POST /api/characters/{character_id}/import`.
  File-local harness only (`_insert_*`, `_seed`, `engine`, `application`, `_as`, `_anonymous`), the
  real `create_app()` pinned through `dependency_overrides[get_settings]`; one admin plus two
  roleplayers, owner A holding **two** characters, a setup, a session on that setup, a message and a
  memo at each of the four scopes; ids above 2**60. **Every envelope is fetched from one of 030's
  `GET` export routes in the same test** (`GET /api/export`, `GET /api/characters/{id}/export`,
  `GET /api/sessions/{id}/export`, and `GET /api/admin/database/export` for the `database`-granularity
  case) — no valid envelope is hand-built.
  - DoD-1 (1) — A's own `user` export: 200, body keys exactly `{granularity, character_ids}`,
    `granularity == "user"`, every id a decimal **string**, count equal to the exported `characters`
    row count, ascending, disjoint from the exported ids, and `GET /api/characters/<id>` answers 200
    for each returned id with the same `id` back.
  - DoD-2 (1) — a `character` export: 200, `granularity == "character"`, exactly one id, `!=` the
    exported character's id.
  - DoD-3 (1) — a `session` export posted under character A2: 200, body keys exactly `{session_id}`, a
    decimal string `!=` the exported session id, and `GET /api/sessions/<id>` answers 200 with
    `character_id == str(CHAR_A2)` and `setup_id is None`.
  - DoD-4 (2) — another owner's character **and** an id nobody holds both answer 404
    `character_not_found` in the full `{"error": {code, message, detail}}` envelope, and the two error
    objects are asserted **equal** (R5, no existence leak); a non-numeric path id answers 422 in
    FastAPI's own shape (`"error"` absent, `"detail"` present).
  - DoD-5 (3) — `session` → `/api/import`; `character` → `/api/characters/{C}/import`; the real
    `database` envelope → **both** routes. Each 400 `export_invalid` with `detail` exactly
    `{"reason": "wrong_granularity"}`.
  - DoD-6 (2) — `{"format": "nope"}` on both routes: 400 `export_invalid`, `detail` exactly
    `{"reason": "not_an_export"}`; a JSON array body on both routes: native 422, `{"detail": ...}`
    shape, **not** the error envelope (harvest E13).
  - DoD-7 (1) — anonymous on both routes: 401 `not_authenticated` with the standard envelope, posting
    an otherwise valid envelope (E13: the guard precedes body validation).
  - DoD-11 (1) — 030's three roleplayer `GET` export routes still answer 200 with their own
    granularities.
- `backend/tests/test_admin_db_import.py` — **6 tests** — covers DoD-6, DoD-8, DoD-9, DoD-10 and
  DoD-11 for `POST /api/admin/database/import`. Two primary instances as fixtures: `eligible_*` (one
  administrator and nothing else) and `occupied_*` (that administrator plus a roleplayer with a small
  tree). DoD-8's second instance is a `db_settings.model_copy` pointing inside the same `tmp_path`
  (`other-instance/other.sqlite`) plus `get_engine`, its export fetched through a **temporary**
  `dependency_overrides[get_connection]` that is popped straight afterwards (harvest D4's idiom). No
  database outside the per-test `tmp_path` is ever opened.
  - DoD-8 (1) — the only administrator posts the other instance's real `database` envelope: **204**,
    `response.content == b""`, exactly one `Set-Cookie` for the session cookie whose value is empty
    and which expires it (`max-age=0`/`expires=`), the **old token replayed** on a fresh client
    answers 401 `not_authenticated`, and a **restored** account logs in with its original password
    (200 plus exactly one session cookie).
  - DoD-9 (1) — on the two-account instance: 409 `database_not_empty` with `detail == {}`, and the
    administrator's next authenticated `GET .../tables` still answers 200.
  - DoD-10 (2) — a roleplayer posting a valid `database` envelope: 403 `insufficient_role`; anonymous:
    401 `not_authenticated`.
  - DoD-6 (2) — on an **eligible** instance (so the 409 guard cannot answer first)
    `{"format": "nope"}` gives 400 `export_invalid` with `detail` exactly
    `{"reason": "not_an_export"}`; a JSON array gives the native 422.
  - DoD-11 (1) — `GET /api/admin/database/tables` still answers 200.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓, DoD-12 [manual/live, no test], DoD-13 [manual/live, no test].
- No clause is satisfiable by the skeleton: every success clause pins the exact status **and** the
  response body's keys and values, and every failure clause pins the exact status **and** the exact
  error code (plus the exact `detail` for `export_invalid` / `database_not_empty`), so the
  `NotImplementedError` 500 satisfies none of them. **DoD-11 is a deliberate regression smoke and is
  expected to be green at the red gate** — it asserts that routes 030 already delivers are untouched.

**Amendments to delivered test files (orchestrator decisions 1 and 2) — narrowings only, nothing
disarmed.**

- `backend/tests/test_configuration_router.py` — **two edits, one site.** `LATER_FEATURE_ROUTES` gains
  `("/api/import", "POST")` and `("/api/characters/{character_id}/import", "POST")`; the explanatory
  comment above it gains an `S031_005_DoD11` paragraph in the pattern 023/029/030 used, stating that
  `POST /api/admin/database/import` is deliberately **not** in the set because `admin_db` is included
  before the configuration router. No test body, no other constant and no other file touched.
- `backend/tests/test_admin_db_router.py` — **exactly the four approved sites.**
  1. `EXPECTED_OPERATIONS` gains `("POST", f"{PREFIX}/import")`, with an `S031_005_DoD11` comment
     beside 030's. The set is still asserted equal to the live operation set in both tests.
  2. `test_router_declares_no_query_parameter_and_no_non_table_key__DoD3`: the arm
     `path.endswith(("/tables", "/export"))` became `path.endswith(("/tables", "/export", "/import"))`
     and the docstring gained one sentence. **The query-parameter half is byte-identical**, and the
     `["table_name"]` arm is unchanged.
  3. The surface guard: `FORBIDDEN_SURFACE` **keeps all four words**; a new
     `PERMITTED_IMPORT_OPERATION = ("POST", f"{PREFIX}/import")` sits beside
     `PERMITTED_EXPORT_OPERATION`, and the loop now `continue`s on the word `"import"` **only** when
     the operation is exactly that one — `rebuild`, `vector` and `vec0` stay rejected on every
     operation, and `export` on everything but 030's one export operation. The test was renamed
     `test_route_surface_has_no_rebuild_import_or_vector_route__DoD14` →
     `test_route_surface_has_no_rebuild_or_vector_route_and_one_import_route__DoD14` for accuracy
     (nothing references it by name) and the docstring gained an `S031_005_DoD11` paragraph.
  4. `test_out_of_scope_routes_do_not_exist__DoD14`: the parametrization entry
     `("POST", f"{PREFIX}/import")` was **replaced** by `("GET", f"{PREFIX}/import")` (405, pinning the
     route POST-only), with a comment saying so. The `rebuild`, `vector-index/rebuild`,
     `tables/models/rebuild`, `POST .../export` and `GET .../vector-index` entries are untouched, as is
     the assertion body.
  Nothing else in the file changed: the AST clause, the OpenAPI vocabulary guard
  (`vector`/`vec0`/`rebuild`), the 403/401 guards and the spies fixture are all as delivered.
- No other delivered test file was opened for editing, and no source file was read.

### Step 006 — tests (2026-10-05)

Two new frontend test files, plus the two delivered-file amendments orchestrator decisions 4 and 5
authorise. No source file was read; every expected value comes from `006.import-client.md`,
`006.context.md`, `context.md` §§"Frontend shared facts" / "Transport" / "Wire contract", and the
bindings come from `### Step 006 — frozen interface` (including the three recorded reload URLs).

- `frontend/tests/shared/importFile.test.ts` — **new, 18 cases** (4 `describe`s: 5 + 7 + 4 + 2; two
  `it.each` blocks expand to 3 and 5) — covers DoD-1, DoD-2, DoD-3, DoD-4 — `readExportFile` parses and sends
  nothing, the five unreadable cases all raise the pinned `ApiError` with **zero** `fetch` calls,
  `postExportFile` makes exactly one JSON `POST` to the given path whose parsed body is the file's
  object re-serialized, and a 400 `export_invalid` envelope comes back as that code and message.
- `frontend/tests/app/importUploads.test.ts` — **new, 27 cases** (6 `describe`s: 7 + 4 + 3 + 4 + 5 + 4;
  the id `it.each` expands to 4 and each abort `it.each` to 2) — covers DoD-5, DoD-6, DoD-7, DoD-8, DoD-9, DoD-10 —
  the two path builders (19-digit id verbatim), the two success paths asserted as an **ordered
  request sequence** (`POST`, then the section-or-characters reload, then `GET /api/sessions`), the
  navigate / no-navigate split, exactly one warning carrying the pinned coverage sentence in yellow,
  the four failure cases (server failure and unreadable file, per effect) and the two abort shapes.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 [manual/live, no test].

**Observation seams** (chosen so call counts and arguments are both assertable):
`src/shared/notifyFailure` is replaced by a mock module, so DoD-9's "exactly once **with the thrown
`ApiError`**" is observable as the argument; `notifyWarning` is left **real** and
`@mantine/notifications`' `notifications.show` is spied instead, so a warning is observed as the
pinned **sentence** and the colour, not as an identifier — and with `notifyFailure` mocked away every
`show` call is a warning. `fetch` is stubbed with `vi.fn<FetchFn>` + `vi.stubGlobal`, keyed on
`<METHOD> <pathname>`, appending every request to one ordered log shared with the `reloadSection`
double (which logs a start and an end around several ticks, so "awaits it" is distinguishable from
"fires it off"); an unmatched request **rejects loudly**. `documentNavigation.assign` is spied, as the
only navigation seam `runSessionImport` could reach. Aborts use a real `AbortController`: one shape
rejects with a real `DOMException` named `AbortError` (not an `instanceof Error` in jsdom), the other
with an unnamed error so the signal's `aborted` state is the only tell — decision 17's two halves.

**Amendments to delivered test files (orchestrator decisions 4 and 5) — narrowings only.**

- `frontend/tests/app/ComposerCore.test.tsx` — **one clause, one site** (was :496-503). The exact
  one-element importer set became the exact **two**-element set
  `["src/app/ComposerCore.tsx", "src/app/importUploads.ts"]`, compared after `[...importers].sort()`
  so directory-read order cannot make it flaky; a third `src/app` warner still fails it. The title was
  retitled only as far as accuracy requires (it still ends `— DoD-6`, feature 014's id), and a
  three-line comment records decision 5. Nothing else in the file changed.
- `frontend/tests/shared/notifyWarning.test.ts` — **additive only.** The file pins **no** exact id set
  and no exact message map, so nothing needed widening; what the new id requires is that the new
  member's message be pinned, so a second `describe` with **two** cases was appended, asserting
  `notifyWarning("import-search-coverage")` shows exactly the pinned coverage sentence in `yellow`,
  and that the two ids map to two different sentences. The existing `describe`, the paste id, its
  message and the `@ts-expect-error` free-text clause are **byte-identical**.
- No other delivered test file was opened for editing, and no source file was read.

**Green/red prediction for the red gate.**

- **Red (every clause)** in both new files: all four `importFile` entry points and both
  `importUploads` effects are stubs that `throw new Error("not implemented")`, and every case either
  awaits a resolved value / parsed object, or enters through
  `await expect(run…).resolves.toBeUndefined()` before any absence assertion — so no absence clause
  can pass vacuously. The path-builder clauses (DoD-5) are red for the same reason.
- **Red, deliberately (ruling 27)**: the amended `ComposerCore.test.tsx` importer clause.
  `src/app/importUploads.ts` cannot import `notifyWarning` while its bodies are stubs
  (`noUnusedLocals`), so the observed importer set is one element at the red gate and two at verify.
- **Green (expected)**: the two new `notifyWarning.test.ts` cases — the skeleton already landed the
  real `WarningId` member and `WARNING_MESSAGES` entry, so that module is implemented, not stubbed.
  The pre-existing `notifyWarning.test.ts` cases also stay green.

### Step 007 — tests (2026-10-05)

Two new files, bound to `### Step 007`'s frozen surface (`UserMenuProps` with `charactersState` /
`sessionsState`; the item label `Import…` with one U+2026; the hidden input outside the `Menu` whose
whole accessible name is `Choose a file to import`; `SessionsSectionProps` unchanged and the
`FileButton`'s input unnamed) and to the three reload paths recorded in `### Step 006`
(`POST /api/import`, `POST /api/characters/<id>/import`, `GET /api/characters`, `GET /api/sessions`
with **no** query, `GET /api/characters/<id>/sessions`). Every expected value comes from the step
file's DoD, `007.context.md`, `006.context.md`'s pinned coverage sentence and `context.md`
("Frontend shared facts", "Reload scope after a roleplayer import", "Wire contract", "Confirm").
**No source file was read.**

- `frontend/tests/app/UserMenu.import.test.tsx` — **new, 19 cases** (8 `describe`s, 17 `it`
  declarations; two `it.each(ROLES)` blocks expand to 2 each) — covers DoD-1, DoD-2, DoD-3, DoD-4,
  DoD-5, DoD-8, DoD-9 — the item is offered to a roleplayer and an admin alike; a `character`
  envelope is posted **parsed and verbatim** to `POST /api/import`, then the characters list and the
  sessions list are each requested exactly once with no query, and the route becomes
  `/characters/<the returned id>` (observed with the `LocationProbe` idiom); a `user` envelope does
  the same but the route is unchanged **even though character ids came back**; a success raises
  **exactly one** notification carrying the pinned coverage sentence and no second one arrives behind
  it; a `.json` file whose text is not JSON raises one notification carrying
  `The chosen file is not a readable export.` with **no** `POST` and no reload, and a 400
  `export_invalid` raises one notification with the **server's** message and no reload; choosing the
  **same `File` twice in a row** posts twice and reloads both lists twice (the input-reset clause);
  no `role="dialog"` / `role="alertdialog"` element exists either side of the choice, paired with the
  `POST` having happened; the item's trimmed accessible name is exactly `Import…` and it renders
  `.tabler-icon-upload`.
- `frontend/tests/app/SessionsSection.import.test.tsx` — **new, 12 cases** (4 `describe`s, 12 `it`
  declarations) — covers DoD-6, DoD-7, DoD-8, DoD-9 — the button sits in the section beside the
  still-present "Start session"; a `session` envelope is posted parsed to
  `POST /api/characters/<that character's id>/import`; after success the section list is requested a
  **second** time and the new session **renders** (the stub server only holds the extra row after the
  `POST`, and its absence is asserted as a baseline first), and the `SessionsState` list is requested
  for the first time (the section's mount never asks for it); a success raises one notification
  carrying the coverage sentence; a 404 `character_not_found`, a 400 `export_invalid` and an
  unreadable file each raise exactly one notification with the right message and leave the section
  list at its single mount call and the `SessionsState` list unrequested; no dialog either side of the
  choice; the button's trimmed name is exactly `Import session` and it renders `.tabler-icon-upload`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓ (one clause per
  file), DoD-9 ✓ (two clauses per file), **DoD-10 ✓ — discharged by the two amended delivered files
  below passing, per ruling 26; no new clause duplicates them**, DoD-11 [manual/live, no test],
  DoD-12 [manual/live, no test].

**Observation seams.** `fetch` is stubbed with `vi.fn<FetchFn>` + `vi.stubGlobal`, keyed on method +
exact pathname, recording method, pathname, search **and body** per call and answering anything else
with a loud 404 envelope — so every absence clause ("no `POST`", "neither list reloaded") is read off
the request log and is paired with a positive observation (the notification, or the `POST` that did
happen). This matters because each new handler is `throw new Error("not implemented")` and React
swallows a throw from an event handler. The file choice is driven with `userEvent.upload` on the
hidden input — found by `Choose a file to import` in `UserMenu`, by `input[type="file"]` for
`SessionsSection`'s unnamed `FileButton` input — with real `File`s named `*.json` and typed
`application/json` so `userEvent`'s own `accept` filter passes them. Notifications are observed
through `.mantine-Notification-root` inside `AppProviders` (`notifyFailure` / `notifyWarning` are
deliberately **not** mocked: the clauses are about what the user is shown) and cleaned with
`act(() => notifications.clean())`. `documentNavigation.assign` is spied so no answer can navigate
jsdom.

**Amendments to delivered test files — rulings 25 and 26, props only.**

- `frontend/tests/app/UserMenu.test.tsx` — two sites: `CharactersState` / `SessionsState` added to the
  import block, and `renderMenu`'s `<UserMenu …>` now passes
  `charactersState={new CharactersState()} sessionsState={new SessionsState()}`. Nothing else changed
  — no clause, name, fixture or title.
- `frontend/tests/app/UserMenu.export.test.tsx` — the identical two-site fix at `renderMenu(role)`.
  Both constructors are no-arg and inert, so the clause asserting the fetch spy has length 1 after
  choosing Export (no request on mount or on open) is undisturbed.
- **Not touched, per ruling 26:** `SessionsSection.export.test.tsx`, `CharacterScreen.export.test.tsx`
  and the unlisted pre-030 `SessionsSection.test.tsx`, `CharacterScreen.test.tsx`,
  `WorkspaceShell.test.tsx`, `App.test.tsx`. No delivered file outside the two above was found to
  break, so there is no `SPEC` concern.

**Green/red prediction for the red gate.**

- **Green (expected), 7 of the 31 cases** — the clauses that only read rendered markup, which the
  skeleton already landed: `UserMenu.import` DoD-1's two role-presence cases plus both DoD-9 cases
  (4), and `SessionsSection.import` DoD-6's "shows an Import session button" case plus both DoD-9
  cases (3).
- **Red, the other 24 cases** — everything that needs a request, a reload, a notification, a navigation or a
  repeat choice: all three handlers (`onImportMyData`, `onImportFileChosen`,
  `onImportSessionFileChosen`) throw `not implemented`, and step 006's `runOwnedImport` /
  `runSessionImport` are stubs too, so no `POST` is ever made. Each such clause asserts a positive
  fact first (`toHaveLength(1)` on the `POST`, or a notification appearing), so none can pass
  vacuously and none is a pure-absence clause.
- **Green (expected)** — both amended delivered files in full; the amendment is purely the two
  missing props, which also clears ruling 25's two authorised TS2739 typecheck errors.

### Step 008 — tests (2026-10-05)

- `frontend/tests/admin/databasePageImport.test.ts` (new) — **15 test functions, 15 collected cases** —
  the store half: the three frozen fields and `chooseImportFile` / `cancelImport` / `importDatabase`.
  `postExportFile` is replaced at module level (030's `databasePageExport.test.ts` idiom with
  `apiDownload`), so no request leaves the process; `documentNavigation.assign` is spied. File doubles
  are real `File` objects, because a class instance is stored by MobX unconverted and identity holds.
  - DoD-4 (4) — posts `("/api/admin/database/import", <the stored file>, <the signal>)`; is
    `importing` while in flight; on success calls `documentNavigation.assign("/login")` exactly once.
  - DoD-5 (2) — a 409 `database_not_empty` stores the **server's** message in `importErrorMessage`,
    clears `importFile`, returns to `idle` and does not navigate; a second case seeds `errorMessage`,
    `exportErrorMessage` and `exportSizeBytes` first and pins all three unchanged afterwards.
  - DoD-6 (2) — a 400 `export_invalid` message, and the pinned unreadable-file message, each stored
    unchanged, with no navigation.
  - DoD-8 (2) — an already-aborted signal writes nothing, posts nothing and navigates nowhere (the
    effect's first step is a write, so "writes nothing" entails it never began); `chooseImportFile`
    clears a previous import error.
  - DoD-2 (1) — `chooseImportFile` stores the file (the positive anchor: non-null is what opens the
    confirm) and still sends nothing.
  - DoD-3 (1) — `cancelImport` clears `importFile` and leaves every other field, including the import
    error and the two other message slots, exactly as it found them; sends nothing.
  - DoD-9 (3) — the prototype is exactly `["constructor"]`; each of the three new names is an
    observable field, never computed, never a function; a fresh store is `null` / `"idle"` / `null`.
- `frontend/tests/admin/DatabasePage.import.test.tsx` (new) — **14 test functions, 16 collected cases**
  (one `it.each` of three drift states) — the page half, rendered as
  `<AppProviders><MemoryRouter initialEntries={["/database"]}><DatabasePage state={state} /></MemoryRouter></AppProviders>`
  then `await flush()`; `fetch` stubbed per test by method + exact pathname (the mount's
  `GET /api/admin/database/tables` included, anything else a loud 404); the file choice driven with
  `userEvent.upload` on the unnamed `input[type="file"]`; `documentNavigation.assign` spied.
  - DoD-1 (5) — an `Import` button carrying `.tabler-icon-upload` beside `Export`; present and **not
    disabled** with the report **in sync, drifted and missing** (each anchored on the report really
    having rendered); the picker's `accept` is exactly `.json,application/json`.
  - DoD-2 (2) — choosing a file opens a dialog whose text carries the pinned title and consequence
    **verbatim** and which holds buttons named `Replace database` and `Cancel`, and **no `POST` has
    been made** — anchored on the dialog actually being open; a second case pins no notification and
    no navigation at that point.
  - DoD-3 (1) — `Cancel` closes the dialog, makes no `POST`, raises nothing, opens no Alert, and
    leaves the report rows and both enabled actions as they were, with the consequence gone.
  - DoD-4 (2) — confirming makes exactly one `POST /api/admin/database/import` whose **parsed body
    equals the file's object**; on a 204 `documentNavigation.assign("/login")` is called exactly once.
  - DoD-5 (2) — a 409 closes the dialog, renders the server's message in a red `role="alert"`, raises
    no notification and does not navigate; the second case seeds a drift error, an export error and an
    export size line, asserts all three are on the page **before** the import, and pins all three
    still present beside the new import message afterwards.
  - DoD-6 (2) — a 400 `export_invalid` renders the server's message in a red Alert (anchored on the
    `POST` having happened); a non-JSON file renders exactly `The chosen file is not a readable
    export.` and makes **no `POST`** — the appearing Alert is that clause's positive anchor. Neither
    notifies nor navigates.
  - DoD-7 (3) — a vacuity guard proving the fixture really carries the sentinels and that none of them
    is a drift-report table name; then, before choosing (anchored on the Import button) and after
    choosing (anchored on the open dialog, whose text is the pinned consequence), no sentinel
    username / character name / memo text / id / table name appears anywhere in the document, no
    digit-bearing row-count claim appears in the page or the dialog, and the only tables named are
    the drift report's own three.
  - DoD-10 (1) — see the coverage map below.
- **How DoD-10 is covered.** 030's own `DatabasePage.export.test.tsx` and `databasePageExport.test.ts`
  still run in full and carry the export contract; they are not duplicated. This step adds the single
  regression case the DoD asks for, in `DatabasePage.import.test.tsx`: with the Import control on the
  page, clicking `Export` still makes exactly one `GET /api/admin/database/export`, still shows its
  size line, and makes no import `POST`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓ (one regression case here + 030's two delivered files), DoD-11 [manual/live, no test],
  DoD-12 [manual/live, no test].

**Amendment audit — the three delivered files, decision 7. Nothing else in them was touched, and no
guard was disarmed.**

1. `frontend/tests/admin/databasePage.test.tsx` — four edits.
   - `OUT_OF_SCOPE_CONTROL` (was :107) narrowed from `/\b(import|rebuild|re-?index)(s|ed|ing)?\b/i` to
     **`/\b(rebuild|re-?index)(s|ed|ing)?\b/i`**, with its doc comment extended to say why and to
     repeat that it may never be widened to admit `rebuild` / `re-index`. `fast/002`'s words stay
     rejected by all five dependent clauses.
   - The three pure-regex clauses (was :904-910, :912-915, :926-930) and the source-literal scan (was
     :932-938) keep their **assertions byte-identical**; only their titles changed from "Import or
     Rebuild" to "Rebuild or Re-index", and one shared comment was updated.
   - The "only control outside the report table" clause (was :920-924): the filter now also drops
     `input[type="file"]` and the pinned set is exactly **`["Export", "Import"]`** (DOM order Export
     button, hidden input, Import button, per the frozen record). Still an exact set, so a stray third
     control outside the table fails it.
   - `ALLOWED_FIELDS` (was :946-955) gained `importErrorMessage`, `importFile`, `importStatus`,
     keeping the array alphabetical. `REQUIRED_FIELDS`, the prototype clause and the
     observable/computed/function loop are untouched.
2. `frontend/tests/admin/databaseActions.test.tsx` — two edits.
   - `OUT_OF_SCOPE_ITEM` (was :111) narrowed from `/rebuild|import|re-?index/i` to
     **`/rebuild|re-?index/i`**, comment extended; the clause at :1240-1248 keeps its assertion and
     was retitled to "Rebuild or Re-index".
   - its independent `ALLOWED_FIELDS` copy (was :1256-1264) gained the same three names.
   - **Untouched, verbatim:** `OUT_OF_SCOPE_ROW_ITEM` (:116, the full
     `/rebuild|export|import|re-?index/i`) and its row-menu clause — 031 adds no row-menu item, so an
     Import item in a dropdown still fails; and the no-open-flag clause at :875-878
     (`/open|modal|confirm|target|dialog|lossy|pending/i`), which the three frozen field names pass
     because the confirm's openness is derived from `importFile !== null` and no flag is stored.
3. `frontend/tests/admin/DatabasePage.export.test.tsx` — two edits, both 030 DoD-4.
   - The clauses at :419-423 and :435-439 now filter `input[type="file"]` out of
     `querySelectorAll("input, textarea")` before pinning the result empty, each with a comment
     naming `FileButton`'s unconditional hidden input as the reason. The three `queryAllByRole`
     assertions in each clause (`textbox`, `searchbox`, `combobox`) are unchanged, so 030's intent —
     no search, filter or free-text input — is fully preserved.
   - **Untouched:** `EXPORT_NAME` (:398, :412) and every `VIEWER_CONTROL` clause; the new control is
     named `Import` and the file input is deliberately unnamed, so neither can match.

No delivered test file outside those three was found to break, so there is no `SPEC` concern.

**Green/red prediction for the red gate.**

- **Green (expected), 10 of the 31 new cases** — the clauses that only read markup or the store's
  declared shape, both of which the skeleton already landed: `DatabasePage.import` DoD-1's five cases,
  DoD-7's fixture guard and its before-choosing case, and `databasePageImport` DoD-9's three cases.
- **Red, the other 20 cases** (the 21st, DoD-10's, is the green one named below) — every clause that needs a choice, a request, a dialog, an Alert or a
  navigation: `chooseImportFile`, `cancelImport`, `importDatabase` and the page's three handlers all
  `throw new Error("not implemented")`, so the confirm never opens and no `POST` is ever made. Each
  of those clauses asserts a positive fact first (the dialog open, the `POST` counted, the Alert
  present), so none can pass vacuously and none is a pure-absence clause. DoD-7's after-choosing case
  is red for the right reason: its anchor (the open dialog) fails.
- **DoD-10's regression case is expected GREEN** — 030's export is delivered and untouched.
- **The three amended delivered files are expected green in full**, since every amendment is either a
  narrowing of a word set 031 legitimately retires or an exclusion of `FileButton`'s hidden input;
  against the skeleton the Import button and that input already exist.

## Notes & Issues

_populated by the coder when worth saying_

- Step 007 judgement call: the Sessions section's `FileButton` is reset **at the start** of
  `onImportSessionFileChosen`, not after the import settles as the frozen record's prose sketched.
  Both wordings satisfy "the `FileButton` is reset after each choice", but resetting first makes the
  repeat choice work whatever the caller's timing, whereas a trailing reset only clears the input
  once the POST and both reloads have resolved. Nothing observable depends on the later ordering —
  the `loading` flag is still cleared on completion — and `UserMenu`'s hidden input clears in the
  same place, so the two controls now behave identically on a repeat pick.

- Step 008 judgement call: `importDatabase` reuses `databasePageState.ts`'s module-private
  `isAbortRejection`, which 030 wrote as `error instanceof Error && error.name === "AbortError"` —
  so a platform `DOMException` abort is matched only by the `signal?.aborted` half of the
  `signal?.aborted || isAbortRejection(error)` guard, the idiom `exportDatabase` already uses. That
  covers every abort the DoD names (the signal is what aborts), and amending a delivered 030 helper
  was out of this step's scope. Worth a one-line fix in a later pass: `exportDownloads.ts` carries
  the constructor-independent predicate (`typeof error === "object" && error !== null && "name" in
  error && error.name === "AbortError"`) and this module does not.
- Step 008: `importDatabase` returns without writing when `importFile` is `null`. The confirm can
  only open with a file chosen, so the guard is unreachable through the UI; it exists so the free
  function has no undefined behaviour when called directly.

## Ultra phase

- orient: done 2026-10-05

Step list as read (Source files · Test files · `[test]` DoD count):

| Step | Source | Tests | `[test]` | Deps |
|---|---|---|---|---|
| 001 envelope-validation | `app/errors.py`, `app/services/transfer_import.py` (new), `app/services/transfer.py` | `tests/test_transfer_import_validation.py` | 12 | — |
| 002 remap-and-owned-import | `app/services/transfer_import.py` | `tests/test_transfer_import_owned.py` | 11 | 001 |
| 003 session-import | `app/services/transfer_import.py` | `tests/test_transfer_import_session.py` | 10 | 002 |
| 004 database-replace | `app/services/transfer_import.py` | `tests/test_transfer_import_database.py` | 12 | 001, 002 |
| 005 import-routes | `app/models/transfer.py` (new), `app/routers/transfer.py`, `app/routers/admin_db.py` | `tests/test_transfer_import_router.py`, `tests/test_admin_db_import.py` | 11 | 001..004 |
| 006 import-client | `src/shared/importFile.ts` (new), `src/app/importUploads.ts` (new) | `tests/shared/importFile.test.ts`, `tests/app/importUploads.test.ts` | 10 | 005 (live only) |
| 007 app-import-entry-points | `src/app/UserMenu.tsx`, `WorkspaceShell.tsx`, `App.tsx`, `CharacterScreen.tsx`, `SessionsSection.tsx` | `tests/app/UserMenu.import.test.tsx`, `SessionsSection.import.test.tsx` + 4 delivered files re-propped | 10 | 006 |
| 008 admin-database-import | `src/admin/databasePageState.ts`, `DatabasePage.tsx` | `tests/admin/databasePageImport.test.ts`, `DatabasePage.import.test.tsx` | 10 | 006, 005 |

**86 `[test]` items and 11 `[manual/live]`.** Steps 001–005 are backend, 006–008 frontend; 004 is the
only step that needs two databases, and 007 is the only step that changes existing component
signatures.

- harvest: done — docs/.cache/ultra/031.import-and-id-remapping/harvest.md (2 reports: backend 001-005, frontend 006-008, each with a whole-suite sweep)

### Orchestrator decisions at harvest (031)

The two sweeps found **eight amendment sites across five delivered test files, none of them in any
step's Test files**, plus one missing Source file, one shrunk step, and thirteen factual corrections.
As in 030, several of those guards were planted by earlier features to assert the **absence** of
exactly what 031 adds, so flipping them is the designed hand-off. Every amendment below **narrows**;
none disarms. `fast/002`'s Rebuild guards and 030's Export guards stay armed throughout.

#### Backend amendments

1. **Step `005`'s Test files are extended by `backend/tests/test_configuration_router.py`.** Add
   `("/api/import","POST")` and `("/api/characters/{character_id}/import","POST")` to
   `LATER_FEATURE_ROUTES` (:1077-1083). **Do not add the admin-db import route** — `admin_db` is
   included *before* the configuration router, so the allow-set covers only what follows. Identical
   in shape to 030's decision 1.
2. **Step `005`'s Test files are also extended by `backend/tests/test_admin_db_router.py`**, at four
   amendment sites:
   - `EXPECTED_OPERATIONS` (:452-457) gains `("POST", f"{PREFIX}/import")`;
   - the path-parameter branch in `..._no_non_table_key__DoD3` (:638-649) widens its
     `path.endswith(("/tables","/export"))` arm to include `"/import"` — the new path has no path
     parameter, so it would otherwise fall into the `["table_name"]` arm. 030 widened this same line
     for `/export`;
   - `FORBIDDEN_SURFACE` (:1459) keeps **all four** words. Add
     `PERMITTED_IMPORT_OPERATION = ("POST", f"{PREFIX}/import")` beside 030's
     `PERMITTED_EXPORT_OPERATION` and skip the word `"import"` **only** for that one operation,
     exactly as 030 did for `"export"`. `rebuild`, `vector` and `vec0` stay rejected on every
     operation, and `export` stays rejected on everything but the one export op;
   - the out-of-scope parametrization (:1496-1522): **replace** `("POST", f"{PREFIX}/import")` with
     `("GET", f"{PREFIX}/import")`, which answers 405 and so pins the route as POST-only. Do not
     simply delete the entry, and do not touch the `rebuild`, `vector-index` or
     `POST .../export` entries.
3. **Two constraints on step 005's coder, not amendments.**
   - `test_route_surface_documents_nothing_about_a_vector_index__DoD14` (:1483-1500) JSON-dumps every
     admin-db operation and asserts the words `vector`, `vec0` and `rebuild` are **absent**. FastAPI
     publishes the handler's docstring as the operation description and its function name as the
     `operationId`, so the new handler's name, summary and docstring must not contain any of those
     three words — however natural it would be to mention dropping `memo_vec` or the later rebuild.
   - The AST clause (:1268-1317) forbids `ast.Try`, `ast.TryStar` **and** `ast.Raise` anywhere in
     `app/routers/admin_db.py` — stricter than 030's note, which said only `raise`. So the new
     handler contains no `try`/`except` and no `raise`; **step 004's `IntegrityError` translation
     lives in the service**, which is where `004.database-replace.md` already puts it. The same
     clause also forbids `execute`/`begin`/`commit`/`rollback`/`scalar` attribute calls,
     `HTTPException`, importing `text` or `sqlite3`, and any `from sqlalchemy ...` import outside
     `{"Connection"}` in that file.

#### Frontend amendments

4. **Step `006` gains a Source file: `frontend/src/shared/notifyWarning.ts`.** `006.context.md` says
   the call "passes the pinned sentence". That is **impossible as built**: the signature is
   `notifyWarning(id: WarningId)` with `WarningId = "paste-context-cost"`, a closed union, and free
   text is `@ts-expect-error`-pinned against in its own test. The coverage sentence therefore needs a
   **new `WarningId` member and a new `WARNING_MESSAGES` entry** in that module. It is the only
   placement that keeps the `@mantine/notifications` importer set at exactly
   `["src/shared/notifyFailure.ts","src/shared/notifyWarning.ts"]` (`tests/conventions.test.ts`
   :132-138), which no step may widen. `tests/shared/notifyWarning.test.ts` joins step 006's Test
   files for the new id only.
5. **Step `006`'s Test files are extended by `frontend/tests/app/ComposerCore.test.tsx`.** Its
   clause at :497-503 asserts `ComposerCore.tsx` is the **only** `src/app` module importing
   `notifyWarning`, pinned as an exact one-element list. `importUploads.ts` lives in `src/app` and
   raises the coverage warning, so it breaks regardless of where the message text lives. Narrow the
   set to exactly `["src/app/ComposerCore.tsx","src/app/importUploads.ts"]` — still an exact set, so
   a third warner still fails it. Rejected alternative: routing the warning through a new `shared/`
   indirection purely to dodge the assertion, which would preserve a guard whose premise 031
   legitimately retires while making the code worse.
6. **Step `007` shrinks: `App.tsx` and `CharacterScreen.tsx` are left untouched, and
   `SessionsSection` gains no new prop.** The plan invents a required `sessionsState` prop, but the
   prop **already exists as `sessions`** (`SessionsSection.tsx:107`), and `CharacterScreen.tsx:329`
   already passes it (`<SessionsSection key={id} characterId={id} sessions={sessions} />`), and
   `WorkspaceShell` already receives both `characters` and `sessions`. So:
   - real Source files are `UserMenu.tsx`, `WorkspaceShell.tsx` and `SessionsSection.tsx`;
   - only **`UserMenu`** gains new required props, and `WorkspaceShell`'s sole edit is passing the
     states it already holds to its **two** `UserMenu` call sites (:123 and :142 — a compact and a
     wide variant; both must be updated);
   - `SessionsSection.export.test.tsx` and `CharacterScreen.export.test.tsx` need **no** edit, and
     the pre-030 `tests/app/SessionsSection.test.tsx:301` and `CharacterScreen.test.tsx:455,460` —
     neither of which any step lists — stay green **only because** the existing prop is reused. A new
     `sessionsState` prop would have broken two unlisted files. `tests/app/WorkspaceShell.test.tsx`
     :223-230 already passes both states and needs no edit either.

   The step file's own escape clause ("any file in this list that turns out to be unneeded is left
   untouched") authorises this; `007`'s Source list is narrowed, never widened.
7. **Step `008`'s Test files are extended by three delivered files.**
   - `frontend/tests/admin/databasePage.test.tsx`: narrow `OUT_OF_SCOPE_CONTROL` (:107) from
     `/\b(import|rebuild|re-?index)(s|ed|ing)?\b/i` to `/\b(rebuild|re-?index)(s|ed|ing)?\b/i`,
     which flows into five clauses (:904-910, :912-915, :926-930, :932-938 — the last being a scan of
     `DatabasePage.tsx`'s own string literals). **Never widen it to admit `rebuild` or `re-index`**:
     `fast/002` owns those and its guards must stay armed. Separately, the "only control outside the
     report table" clause (:920-924) is amended to filter `input[type="file"]` out of `controls()`
     and pin the set to exactly `["Export","Import"]` — a stray third control still fails it. And
     both independent `ALLOWED_FIELDS` copies gain step 008's three frozen field names.
   - `frontend/tests/admin/databaseActions.test.tsx`: narrow the page-wide `OUT_OF_SCOPE_ITEM`
     (:111) the same way, for the clause at :1240-1248. **`OUT_OF_SCOPE_ROW_ITEM` (:116) stays
     verbatim** — it is the full `/rebuild|export|import|re-?index/i` and 031 adds **no row-menu
     item**, so an Import item in a row dropdown must still fail. Its `ALLOWED_FIELDS` copy gains the
     same three names.
   - `frontend/tests/admin/DatabasePage.export.test.tsx`: 030's DoD-4 clauses at :419-423 and
     :435-439 assert `querySelectorAll("input, textarea")` is **empty** before and after an export.
     Mantine's `FileButton` renders a hidden `<input type="file">` unconditionally, so both break.
     Amend each to exclude `input[type="file"]` — preserving 030's actual intent (no search, filter
     or free-text input on the page) while admitting the file picker.
8. **The three new `DatabasePageState` fields must dodge two unamended regexes.**
   `databaseActions.test.tsx:875-878` asserts the store has no field matching
   `/open|modal|confirm|target|dialog|lossy|pending/i`, and `databasePage.test.tsx:849-852` asserts
   none matching `/^id$|Id$|_id$|ID/`. The plan's own words for the first field are "the **pending**
   import file", which would trip the first regex. **Both clauses stay verbatim**: the skeleton names
   the fields so they pass — `importFile` / `importStatus` / `importErrorMessage` is the recommended
   set. This is not evasion: the design genuinely has **no** stored open/confirm flag, since the
   confirm's openness is *derived* from the file being non-null, so the guard's premise still holds.
   Also unamended and binding on both step-008 files: no `parseInt`, no `Id`-shaped name, and no
   bare word `id` in their source (`databasePage.test.tsx:838-840`).
9. **The hidden file input's accessible label is constrained.** `DatabasePage.export.test.tsx`'s
   `EXPORT_NAME` (:398, :412) and `VIEWER_CONTROL` clauses scan **control names**, so no new control
   may carry `export`, `view`, `open`, `preview`, `browse`, `inspect`, `reveal`, `peek`, `details`,
   `contents`, `display`, `expand` or `show` in its accessible name. `007.context.md`'s suggested
   label "Choose export file to import" contains `export`. Use a label with none of those words —
   **"Choose a file to import"**.

#### Factual corrections to the plan, carried into every brief

10. **`ExportGranularity` is a `Literal` type only** (`transfer.py:40`); there is no runtime
    granularity constant. Step 001 derives the value set with `typing.get_args(...)`, probed as
    `('database','user','character','session')`.
11. **030's id-column predicate is `_is_id_column(column, primary_key_names)` — two arguments, not
    one.** Its single call site is `transfer.py:166`, which computes the key names at :163. Step 001
    exposes it under a public name **with that same two-argument signature** and leaves 030's call
    site working. Its name arm uses the private `_ID_NAME = "id"` / `_ID_SUFFIX = "_id"`; it does not
    look at column type.
12. **The real 030 constant names** are `EXPORT_FORMAT`, `ENVELOPE_VERSION`, `SCHEMA_VERSION`,
    `DATABASE_EXCLUDED_TABLES`, `USER_EXCLUDED_COLUMNS` — and, unmentioned by the plan, a separate
    `USER_EXCLUDED_TABLES` with the same two names. Import from `transfer.py`; re-declare nothing.
13. **Only two columns in the whole registry are `Enum`: `users.role` and `memos.scope`.**
    `001.context.md`'s "`messages.role` / `messages.kind` may be enums or text" is wrong — both are
    plain `Text`. `memos.scope`'s `Enum` has `enum_class=None`, so reads give a plain `str`, while
    `users.role` reads give a `Role` member. `Boolean` is **not** an `Integer` subclass, so that
    half of the arm-ordering advice is harmless but unnecessary.
14. **`settled_entries` and `current_zone` are Core `select()` objects, not SQL views**
    (`schema.py:448-461`); tests execute them directly. `buried_messages` and `message_states`
    exist too. Steps 002/004 call them "views" — harmless wording, but no DDL exists to query.
15. **Step 004's `IntegrityError` contract is incomplete as written.** A bad enum string raises
    `StatementError` wrapping `LookupError`, not `IntegrityError`; an id above `2**63-1` raises
    `OverflowError` at bind time; and a JSON `1` in a nullable Boolean column is **accepted** by
    SQLAlchemy and SQLite. So the write phase must not rely on `IntegrityError` for any of them —
    **step 001's deserializer rejects all three before any write**, which is what `context.md`'s
    "all validation happens before any write" already requires. Step 004 catches `IntegrityError`
    only, for the FK / UNIQUE / CHECK cases its DoD-6 names.
16. **`ApiError`, `CLIENT_MALFORMED_ERROR` and `CLIENT_TRANSPORT_FAILED` live in
    `src/shared/apiError.ts`**, not `api.ts`; `api.ts` merely re-imports them. `documentNavigation`
    **is** exported from `api.ts`, as `008.context.md` says. `ApiError`'s `detail` parameter is
    optional.
17. **Neither reference module does what `006.context.md` says about aborts.** 030's
    `exportDownloads.ts` is name-only (any non-null object whose `name === "AbortError"`, and it has
    no signal parameter); `logout.ts` is `signal?.aborted === true` only. Step 006's effects take a
    signal, so they need **both** halves, and the name half must be the widened,
    constructor-independent form 030 just landed — not the `instanceof Error` form that still exists
    in five `admin/` copies.
18. **`shared/importFile.ts` raises no notification.** It throws; each entry routes the error its own
    way (`notifyFailure` in `app`, the inline `Alert` in `admin`). If it imported `notifyFailure`,
    the admin page would start notifying, breaking its inline-only rule.
19. **Harness facts the plan's gotchas get wrong or omit:** jsdom 30.1.1 **does** implement
    `Blob.prototype.text()`, so `006.context.md`'s "may lack it" gotcha is moot and a real `File`
    works; `userEvent` is 14.6.7, so `upload` is available; `@mantine/core` is **7.17.8** with
    `FileButton`, `resetRef`, `accept` and `inputProps` all present, its `children` being a render
    prop receiving `{onClick}` and its `reset()` clearing `input.value`; `vitest` runs with
    `globals: false`, so every test file imports `describe`/`it`/`expect` explicitly; and
    `tests/setup.ts` installs **no** fetch stub.
20. **Unamended guards every frontend step must respect:** `tests/ids-are-strings.test.ts` (no
    `...Id: number`, no `parseInt`, anywhere in `src/`, comments included),
    `tests/app/entryIsolation.test.ts` (`app` may not import `admin`),
    `tests/build-config.test.ts` (the npm script set is exactly
    `["build","dev","test","typecheck"]`; `.ts`/`.tsx` only), `tests/stylesheets.test.ts` (no new
    stylesheet), and `tests/app/appBootState.test.ts` (no case-colliding module names).
21. **Backend guards that stay green but constrain:** `tests/test_config.py:244-258` requires
    `app/services/__init__.py` to hold **only** its docstring, so `transfer_import.py` is never
    re-exported there; and no test enumerates `app/services/`, `app/routers/`, `app/models/` or the
    `DomainError` subclass set, so the two new modules and two new error classes break no exact set.

#### Baselines going in

Backend **4353** collected across 105 files. Frontend **144** test files. Both are 030's verified
post-commit numbers, so the red gate measures against them.

- skeleton: done — steps 001, 002, 003, 004, 005, 006, 007, 008 (no escape valve from any step)

### Cross-step rulings made during the skeleton phase (031)

22. **Step 004 has no identity-policy value, by orchestrator ruling.** `004.database-replace.md` asked
    for a private "database identity policy — the step-002 seam that hands rows to the writer without
    minting new ids". Step 002's `_write_payload(connection, rows)` takes **final** rows and assumes
    no minting, so the identity path is simply `_write_payload(connection, validated.rows)`.
    `_remap_payload` mints unconditionally and is the wrong seam. Step 004 therefore calls the writer
    directly and adds **no** policy value, field or flag — nothing in it touches `_remap_payload`,
    `_owned_policy` or `_ReferencePolicy`. The test-coder must not expect an identity-policy symbol.
23. **The session policy fits step 002's three frozen fields; `_ReferencePolicy` was not widened.**
    Allowed scopes → `allowed_memo_scopes`; `sessions.character_id` → `column_overrides[(sessions,
    "character_id")] = <target>`; `sessions.setup_id` → the same map with `None` (present-with-`None`
    writes NULL); "every `user_id` becomes the caller, accepting any payload value" →
    `required_user_id = None`. Two session rules need **no** field at all: "the memo target must be
    the payload session" is the engine's ordinary reference check, and the model pair is engine-wide.
24. **A forced deviation in step 005's admin handler.** Decision 3's AST clause forbids `ast.Raise`
    anywhere in `app/routers/admin_db.py`, so that handler's stub body **cannot** be
    `raise NotImplementedError`. It is instead the single delegation `import_database(connection,
    body)` — step 004's stub, which raises — so the route still fails loudly with zero behaviour in
    the router. The skeleton probed the file: 0 `Try`/`TryStar`/`Raise` nodes, 0 forbidden attribute
    calls, `from sqlalchemy import Connection` only, 0 function-nested imports, no `HTTPException`,
    no SQL-keyword string constant, and the new operation's JSON dump contains none of `vector`,
    `vec0`, `rebuild` — nor `export`, excluded deliberately because `FORBIDDEN_SURFACE` rejects that
    word on every operation but 030's one export op.
25. **Two authorised typecheck errors stand until the tests phase.** `UserMenu` gained two *required*
    props, so the delivered `tests/app/UserMenu.test.tsx:57` and `tests/app/UserMenu.export.test.tsx:161`
    fail `npm run typecheck` with TS2739 (missing `charactersState`, `sessionsState`). Both files are
    already in step 007's Test files; the skeleton was instructed **not** to fix them, not to edit any
    test file, and not to weaken the props to silence them. Zero errors exist under `src/`. The step
    007 test-coder clears both by supplying the two no-arg constructors at those render sites.
26. **Step 007's DoD-10 is partly moot.** It claims 030's `SessionsSection.export.test.tsx` and
    `CharacterScreen.export.test.tsx` need re-propping. Neither signature changed (decision 6), so
    neither file needs an edit; only the two `UserMenu` files do. Those two stay in the Test files
    list as regression witnesses, not as edit targets.
27. **An accepted true-red for the red gate.** `tests/app/ComposerCore.test.tsx`'s importer clause,
    amended under decision 5 to the exact set `["src/app/ComposerCore.tsx","src/app/importUploads.ts"]`,
    **cannot be green against the skeleton**: `importUploads.ts` does not import `notifyWarning` until
    the coder fills the bodies (`noUnusedLocals` forbids the import in a stub). This is a deliberate
    true-red, taken to avoid a vacuous pass, and it must be green at verify. Same shape as 028's
    stubbed registry and 030's `raise NotImplementedError` in `admin_db.py`.

### Names the later phases bind to

- Public backend surface: `is_id_column(column, primary_key_names)` (030's predicate, renamed public
  in `transfer.py`); in `app/errors.py` `ExportInvalidReason` + `REASON_NOT_AN_EXPORT` /
  `REASON_UNSUPPORTED_VERSION` / `REASON_SCHEMA_MISMATCH` / `REASON_WRONG_GRANULARITY` /
  `REASON_MALFORMED_PAYLOAD`, `ExportInvalidError(reason)` (**one** argument), `DatabaseNotEmptyError`;
  in `transfer_import.py` `ImportValue`, `ImportRow`, `EXPORT_GRANULARITIES`, `GRANULARITY_TABLES`,
  `ROOT_TABLES`, `ValidatedExport(granularity, rows)`, `deserialize_row`, `validate_envelope`,
  `OwnedImportResult(granularity, character_ids)`, `import_owned`, `import_session`,
  `import_database`; in `models/transfer.py` `OwnedImportGranularity`, `OwnedImportResponse`,
  `SessionImportResponse`. Everything else in `transfer_import.py` is module-private and is exercised
  only through the three public imports.
- Routes: `POST /api/import` (200), `POST /api/characters/{character_id}/import` (200),
  `POST /api/admin/database/import` (204, clearing the cookie through
  `clear_session_cookie(response, settings)` from `app/dependencies.py`).
- Frontend: `WarningId` gained `"import-search-coverage"`; `CLIENT_UNREADABLE_FILE`,
  `ReadableTextFile`, `readExportFile`, `postExportFile<T = unknown>`; `OwnedImportResponse`,
  `SessionImportResponse`, `NavigateTo`, `ReloadSection`, `ownedImportPath`, `sessionImportPath`,
  `runOwnedImport`, `runSessionImport`; `UserMenuProps` gained `charactersState` and `sessionsState`;
  `DatabaseImportStatus` with `importFile` / `importStatus` / `importErrorMessage`,
  `chooseImportFile`, `cancelImport`, `importDatabase`.
- **The three list-reload paths every frontend `fetch` stub keys on**, recorded because nothing else
  holds them: `loadCharacters` → `GET /api/characters` (plus `?include_archived=true` only when
  `state.showArchived`); `loadSessions` → `GET /api/sessions`, **never** with a query;
  `loadSectionSessions` → `GET /api/characters/<encodeURIComponent(characterId)>/sessions` (plus
  `?include_archived=true` only when `state.showArchived`). None of the three ever rejects — a failure
  becomes `status = "failed"`.

- tests: done — steps 001..008 (approved deviations: step 005 amends `backend/tests/test_configuration_router.py`
  and `backend/tests/test_admin_db_router.py`; step 006 amends `frontend/tests/app/ComposerCore.test.tsx`
  and `frontend/tests/shared/notifyWarning.test.ts`; step 007 amends `frontend/tests/app/UserMenu.test.tsx`
  and `frontend/tests/app/UserMenu.export.test.tsx`; step 008 amends `frontend/tests/admin/databasePage.test.tsx`,
  `frontend/tests/admin/databaseActions.test.tsx` and `frontend/tests/admin/DatabasePage.export.test.tsx`
  — nine amendment sites across **seven** delivered files, every one a narrowing under decisions 1, 2, 4,
  5 and 7)

### Test inventory going into the red gate

| Step | New test file(s) | Cases |
|---|---|---|
| 001 | `backend/tests/test_transfer_import_validation.py` | 76 |
| 002 | `backend/tests/test_transfer_import_owned.py` | 25 |
| 003 | `backend/tests/test_transfer_import_session.py` | 20 |
| 004 | `backend/tests/test_transfer_import_database.py` | 22 |
| 005 | `backend/tests/test_transfer_import_router.py` · `backend/tests/test_admin_db_import.py` | 10 + 6 |
| 006 | `frontend/tests/shared/importFile.test.ts` · `frontend/tests/app/importUploads.test.ts` | 18 + 27 |
| 007 | `frontend/tests/app/UserMenu.import.test.tsx` · `frontend/tests/app/SessionsSection.import.test.tsx` | 19 + 12 |
| 008 | `frontend/tests/admin/databasePageImport.test.ts` · `frontend/tests/admin/DatabasePage.import.test.tsx` | 15 + 16 |

**12 new files, 266 cases, covering all 86 `[test]` DoD items.** Backend 159, frontend 107.

### Accepted true-reds, taken deliberately to avoid vacuous passes

- **`frontend/tests/app/ComposerCore.test.tsx`'s importer clause** (ruling 27). Narrowed to the exact
  set `["src/app/ComposerCore.tsx","src/app/importUploads.ts"]`, it cannot be green against the
  skeleton, because `importUploads.ts` does not import `notifyWarning` until the coder fills the
  bodies — `noUnusedLocals` forbids an unused import in a stub. **Must be green at verify.**
- **Step 008's DoD-4 parsed-body clause** exercises step 006's real `postExportFile`, so it stays red
  until step 006's coder lands that function. Expected, and green at verify.
- The two authorised TS2739 typecheck errors from ruling 25 are **cleared by this phase**: step 007's
  test-coder supplied `charactersState` / `sessionsState` at both `renderMenu` sites.

### The test-coders' own green/red predictions, for the red gate to check

- **001–005 (backend): every new case red.** Each refusal pins the specific error class **and** its
  exact `detail`, so the stubs' `NotImplementedError` satisfies none; the router failure clauses pin
  the exact status **and** error code, so the stubs' 500 satisfies none. Two exceptions, expected
  **green**: step 005's two DoD-11 regression smokes, which assert 030's three export routes and
  `GET /api/admin/database/tables` still answer 200.
- **006: every case in both new files red**, each entering through
  `await expect(run…).resolves.toBeUndefined()` before any absence assertion. The two new
  `notifyWarning.test.ts` cases are **green**, because the skeleton landed the real `WarningId` member
  and its message.
- **007: 7 green, 24 red.** Green are the markup-only clauses the skeleton already satisfies — the two
  role-presence cases and two icon/name cases in `UserMenu.import`, and the button-present case plus
  two icon/name cases in `SessionsSection.import`. Everything needing a request, reload, notification,
  navigation or repeat choice is red.
- **008: 11 green, 20 red.** Green are DoD-1's five presence cases, DoD-7's fixture guard and its
  before-choosing sweep, DoD-9's three store-shape cases, and DoD-10's export regression.
- **All nine delivered-file amendments are expected green in full**, except `ComposerCore.test.tsx`'s
  one clause above.

### Spec concerns raised and adjudicated by the orchestrator, no planner round trip

- **Step 002 DoD-5's "nothing warns or fails".** A service has no notification channel, and
  `OwnedImportResult` carries only `granularity` and `character_ids`. The phrase refers to
  `brief.md`'s **Out** — no duplicate-import warning is built — and the only warning this feature
  raises at all is step 006's client-side coverage sentence. Adjudicated: the correct witness is
  "both calls return normally and both copies are complete and disjoint". A Python-`warnings`
  assertion would test the wrong layer and would risk failing on unrelated SQLAlchemy warnings.
- **Step 003 DoD-1's "owned by the caller"** is only weakly observable in the seeding shape
  `003.context.md` pins (the caller is also the exporting user), so it is asserted as
  `user_id == caller` on every imported row rather than by contrasting two users. Importing another
  user's export into one's own character would be legitimate under `required_user_id = None`, but the
  context file fixes the same-caller shape. Accepted as written.
- **Step 006 DoD-8's "does not navigate"** — `runSessionImport` takes no `navigate` parameter, so the
  only reachable navigation seam, `documentNavigation.assign`, is asserted untouched. Accepted.
- **Step 004's fixture widening.** DoD-2's "`translations` holds no rows" would be vacuous against a
  target seeded only as DoD-1 words it, so the target also holds a session, a settled message, a
  `translations` row, a server and a model. Backed by `context.md` §"Database import" item 2, which
  lists exactly those as what the wipe deletes. A fixture widening, not an added assertion.
- **`app.db.schema` exposes no `translations` attribute**; step 004's tests reach it as
  `schema.metadata.tables["translations"]`, the idiom every delivered translation test uses.

- red-gate: **PASS (run 1) — the verifier returned FAIL / Fault TEST on steps 001, 005 and 006, and I
  overruled that classification as orchestrator.** Reasoning and the audit that justified it are below.
  All four static gates clean: `mypy app` (94 files), `ruff check .`, `npm run typecheck` (exit 0 — the
  two authorised TS2739 errors are gone), `npm run build`. Backend **4515** collected (4353 baseline +
  **162** new): 141 failed, 4374 passed. Frontend **4304** tests across **150** files (144 + 6): 91
  failed, 4213 passed. **No pre-existing test fails on either side**, with the single accepted true-red
  exception below, and steps 002, 003, 004, 007 and 008 matched their predictions exactly.

### Why the TEST fault was overruled (orchestrator adjudication)

The verifier flagged 21 cases as "vacuous green — they pass against bare stubs and therefore gate
nothing": 13 in step 001, 6 in step 005, 1 in step 006, plus one it had itself predicted. **Every one
of them has frozen interface as its subject**, not behaviour:

- **001** — `ROOT_TABLES`, `GRANULARITY_TABLES` and its `database` derivation, the five reason
  constants' distinctness, `ExportInvalidError`'s `code` / `http_status` / `detail` shape and the five
  pinned messages, `DatabaseNotEmptyError`'s pinned 409 shape, and `is_id_column`'s rule over every
  registry column.
- **005** — the 401, 403 and native-422 answers. These are produced by the **route decorators, the
  router-level and parameter-level auth dependencies, and the `SnowflakeIn` / `dict[str, Any]`
  parameter declarations**, all of which run *before* any handler body. FastAPI, not step 005's
  behaviour, answers them.
- **006** — `CLIENT_UNREADABLE_FILE`'s value.

All three skeletons were instructed, in writing, that exactly these declarations **are** interface and
must be real — step 005's brief said "route decorators, paths, status codes, dependency declarations,
parameter types and the response models **are** interface and must be real, because the red gate checks
the surface against the frozen record". A clause pinning a frozen declaration **cannot** be red against
the skeleton, and the only way to make it red would be to move the declaration out of the skeleton and
into the coder's hands — which would break the skeleton contract these same tests bind to. 030's
verifier ruled the identical category legitimate ("the only structural bindings are legitimate contract
pins — the frozen field-name allow-lists, the route-operation set, the prototype check"), and this
gate's own prediction already accepted 18 such clauses as expected-green in steps 007 and 008. The
report itself concedes several of the 001 cases "are genuine regression checks".

**The one thing that would have made this a real fault — a behavioural DoD item gated by green cases
alone — I had audited explicitly, and it is absent.** Per-item red coverage, confirmed by a verbose
re-run:

| Item | Red coverage |
|---|---|
| 001 DoD-8 | **red** — 4 parametrised wrong-root-count cases; only the `ROOT_TABLES` pin is green |
| 001 DoD-9 | **red** — 3 sentinel cases (bad id, bad enum, missing column); only the error-shape cases are green |
| 001 DoD-10 | green-only — a single case, the pinned 409 shape. No behavioural half exists |
| 001 DoD-11 | green-only — four table-set cases. No behavioural half exists |
| 005 DoD-7 / DoD-10 | green-only — guard wiring only (anonymous 401; roleplayer 403) |
| 005 DoD-11 | green-only by design — 030 regression smokes |
| 006 DoD-2 | **red** — 6 of 7 cases; only the constant-equality case is green |
| 007 DoD-9 · 008 DoD-1 / DoD-9 / DoD-10 | green-only — icon/name presence, store shape, 030 export regression |
| 001 DoD-12 · 005 DoD-4, DoD-6 · 007 DoD-1 · 008 DoD-2, DoD-7 | mixed green and red |

**No green-only item carries a behavioural clause a coder could leave unimplemented.** Every green-only
item is presence, shape or regression. Sending the three steps back to their test-coders would therefore
have churned sound clauses with no gain, and risked damaging the contract pins that protect 030's
delivered surface.

### The accepted true-red, still red for the stated reason

`frontend/tests/app/ComposerCore.test.tsx`'s importer clause receives `["src/app/ComposerCore.tsx"]`
and expects the exact two-element set — because `importUploads.ts` cannot import `notifyWarning` while
its bodies are stubs (`noUnusedLocals`). **It must be green at verify** (ruling 27). Step 008's DoD-4
parsed-body clause is likewise red pending step 006's `postExportFile`.

### Amendment audit — all nine sites narrowed, nothing disarmed

The verifier initially audited seven of the nine by diff and left the two largest unread —
`databasePage.test.tsx` (48 lines) and `DatabasePage.export.test.tsx` (16 lines) — concluding only that
both files pass. **Passing is exactly what a disarmed guard does**, so I sent it back to read both line
by line. Result, confirmed:

- `OUT_OF_SCOPE_CONTROL` is exactly `/\b(rebuild|re-?index)(s|ed|ing)?\b/i` — only `import|` removed,
  with the word boundaries, the `(s|ed|ing)?` group and the `i` flag intact. Its four consuming clauses'
  **assertion lines are not in the diff at all**, so they are byte-identical; only titles and comments
  changed. The source-scan clause's literal-extraction regex and exclusion filter were not widened.
- The "only control outside the report table" clause filters `!el.matches('input[type="file"]')` —
  **only** file inputs, not all inputs and not a name-emptiness test — and pins
  `toEqual(["Export","Import"])`, an exact ordered set, so a stray third control still fails.
- `DatabasePage.export.test.tsx`'s two 030 DoD-4 clauses still assert `toEqual([])` with only
  `input[type="file"]` excluded, so `textarea` and every non-file `input` are still rejected; the
  `searchbox` / `combobox` role assertions above them, and `EXPORT_NAME` and `VIEWER_CONTROL`, are
  byte-identical.
- Both `ALLOWED_FIELDS` copies gained exactly three names and lost none.
- `OUT_OF_SCOPE_ROW_ITEM` and the no-open-flag clause do not appear in any diff — byte-identical, so an
  Import item in a **row** dropdown would still fail, and a stored open/confirm flag would still fail.
- `test_admin_db_router.py`'s AST clause and OpenAPI vocabulary clause are untouched **and passing**,
  which means step 005's new handler already satisfies both.
- **`fast/002`'s Rebuild guards and 030's Export guards are all still armed and passing.**

### Corrected case counts (my inventory was three low on the backend and two on step 008)

Backend, six new files: `test_transfer_import_validation.py` 76 · `test_transfer_import_owned.py` 25 ·
`test_transfer_import_session.py` 20 · `test_transfer_import_database.py` 22 ·
`test_transfer_import_router.py` **12** (recorded 10) · `test_admin_db_import.py` **7** (recorded 6) =
**162**. Frontend: `DatabasePage.import.test.tsx` **18** (recorded 16, an `it.each` over the report
states) and `databasePageImport.test.ts` 15, the rest as recorded = **109**. **271 new cases in 12
files**, not 266. The earlier figures were hand counts of function definitions rather than collected
cases.

### Baselines the verify run must hold

Backend **4515** collected, frontend **4304** across **150** files. A verify PASS means both numbers
fully green, 0 failed, 0 errored.

- code: done — steps 001, 002, 003, 004, 005, 006, 007, 008 (no re-freeze, no escape valve from any
  step; every coder reported `mypy app` "Success: no issues found in 94 source files" / `ruff check .`
  "All checks passed!" on the backend side, and `npm run typecheck` exit 0 / `npm run build` succeeded
  on the frontend side, and every coder confirmed in writing that it read no test file)

### What each step landed

| Step | Source files filled | Note |
|---|---|---|
| 001 | `services/transfer_import.py` — `deserialize_row`, `validate_envelope` | arm order mirrors 030's serializer |
| 002 | same — `_owned_policy`, `_remap_payload`, `_write_payload`, `import_owned` | one defensive refusal, below |
| 003 | same — `_session_policy`, `_require_owned_character`, `import_session` | no `archived_at` term (R6) |
| 004 | same — `import_database` and its four helpers | ruling 22 held: `_write_payload(connection, validated.rows)` |
| 005 | `routers/transfer.py`, `routers/admin_db.py` | `models/transfer.py` needed no edit |
| 006 | `shared/importFile.ts`, `app/importUploads.ts` | `shared/notifyWarning.ts` needed no edit |
| 007 | `app/UserMenu.tsx`, `app/SessionsSection.tsx` | `app/WorkspaceShell.tsx` needed no edit |
| 008 | `admin/databasePageState.ts`, `admin/DatabasePage.tsx` | confirm stays derived; no stored open flag |

Four of the twelve listed Source files needed no edit at all, because the skeleton had delivered their
contribution as real code rather than as a stub: `models/transfer.py`'s two response models,
`notifyWarning.ts`'s new `WarningId` member and pinned sentence, and `WorkspaceShell.tsx`'s two new
`UserMenu` props. Recorded so the verifier does not read their absence from a diff as an omission.

### Ruling 27 is closed by step 006

`app/importUploads.ts` now really imports and calls `notifyWarning("import-search-coverage")`, so the
deliberate true-red in `tests/app/ComposerCore.test.tsx`'s importer clause — the exact set
`["src/app/ComposerCore.tsx","src/app/importUploads.ts"]`, unreachable while the bodies were stubs
because `noUnusedLocals` forbids an unused import — must now be **green**. Step 008's DoD-4 parsed-body
clause, red pending step 006's `postExportFile`, must likewise be green.

### Coder judgement calls carried to the verify run

1. **Step 002 — a defensive refusal the spec does not enumerate.** Two rows of one table sharing a
   primary key answer `malformed_payload`; "otherwise it would be a 500 from a duplicate insert".
2. **Step 006 — four calls.** `navigate` guarded by `granularity === "character" && character_ids.length > 0`
   (`=== undefined` on a `string` would be TS2367); the client-route id interpolated raw, matching
   `CharacterScreen.tsx:148`, while the API path builder escapes as 030 does; `signal` forwarded to
   `loadCharacters`/`loadSessions`; the warning id referenced through a module-private const.
3. **Step 007 — reset-first.** `importResetRef.current?.()` fires at the *start* of the sessions handler,
   not after the import settles as the frozen prose sketched, so a repeat pick of the same file re-fires
   regardless of caller timing, matching `UserMenu`'s synchronous `input.value = ""`.
4. **Step 008 — the abort predicate.** It reuses 030's module-private `isAbortRejection` **as the
   skeleton instructed**, which is the *pre-fix* narrow form `error instanceof Error && error.name ===
   "AbortError"`; a platform `DOMException` is therefore caught only by the `signal?.aborted` half of
   `signal?.aborted || isAbortRejection(error)`. **The verifier must rule on this**: 030's verify round 1
   found exactly this narrow form to be a real fault in `exportDownloads.ts`, and step 006 used the
   widened constructor-independent form. If any DoD clause can abort without `signal.aborted` being
   observable, this is a CODE fault. Also: `importDatabase` returns without writing when `importFile`
   is `null`, and writes no state on success, so the confirm stays loading while the browser navigates.

### The two abort predicates now in the tree, deliberately noted

`app/importUploads.ts` (step 006) uses the widened form — a non-null object whose `name` is exactly
`"AbortError"`, constructor-independent, 030's post-fix shape. `admin/databasePageState.ts` (step 008)
routes through 030's `isAbortRejection`, still the narrow `instanceof Error` form, paired with an
`aborted` check. Not a contradiction by construction, but the asymmetry is recorded rather than left for
someone to find.

- verify: **PASS (run 1)** — all eight steps PASS, no fault of any type, no re-freeze, no escape valve,
  no coder or test-coder round needed. Backend `4515 passed, 1 warning in 434.59s` (the one warning is
  the pre-existing `StarletteDeprecationWarning` from `fastapi/testclient.py`); frontend
  `Test Files 150 passed (150)` / `Tests 4304 passed (4304)`. **0 failed, 0 errored, 0 skipped on both
  sides**, matching the red gate's baselines exactly. All four static gates clean: `mypy app` (94
  files), `ruff check .`, `npm run typecheck` **exit 0** (the two authorised ruling-25 TS2739 errors are
  gone), `npm run build` (7503 modules, four entries). All **86 `[test]` DoD items** covered and green;
  per-file counts independently re-measured and matching the corrected inventory — **271 new cases in 12
  files**. No file touched outside any step's Source list; every frozen signature, constant, `Literal`,
  dataclass field order, route declaration, label and pinned string byte-identical; `Import…` verified
  by codepoint to carry one U+2026.

### The five deferred adjudications, all resolved in the code's favour

1. **Both accepted true-reds are now green.** `ComposerCore.test.tsx`'s importer clause is still the
   exact set `["src/app/ComposerCore.tsx","src/app/importUploads.ts"]` — a third `src/app` warner would
   still fail it — and `importUploads.ts` genuinely imports `notifyWarning` and calls it on both
   success paths. **Ruling 27 is closed.** Step 008's DoD-4 clause carries no `vi.mock` of
   `shared/importFile`, so it drives the real `postExportFile` → `readExportFile` → `apiPost` chain
   against a stubbed `fetch`, and passes.
2. **Step 008's narrow abort predicate is NOT a CODE fault**, and the reason is structural, not
   incidental. `shared/api.ts` has exactly two sites that let a raw rejection escape — `mapFetchRejection`
   (`:78-83`) and the body-read catch (`:119-127`) — and **both are themselves gated on `signal?.aborted`**,
   substituting an `ApiError` otherwise. An `AbortError` `DOMException` can therefore only reach
   `importDatabase`'s catch when `signal.aborted` is already true, and `abort()` sets that synchronously
   before the fetch promise rejects; `signal?.aborted || isAbortRejection(error)` short-circuits on the
   first operand. Step 008's only abort clause (DoD-8) is answered by the pre-check before any write.
   **Why 030's identical narrow form *was* a real fault there:** `exportDownloads.ts` has no `signal`
   parameter at all, so the name predicate was its only guard. Step 006, whose effects can be aborted
   mid-flight and whose DoD-10 tests a real `DOMException`, correctly uses the widened form — it needed
   both halves and has both.
3. **Step 002's duplicate-primary-key refusal is authorised, not invented.** `context.md`'s failure
   contract introduces `malformed_payload` as covering *everything about the payload*, with the bullets
   beneath as instances rather than a closed list, and the same section requires that all validation
   precede any write and that any failure store nothing — the only in-transaction exception being the
   database replace. Letting a duplicate reach the insert would produce an untyped 500 outside the
   five-reason contract. It contradicts no pinned case: step 001's DoD-8 duplicate-root cases give the
   extra row a **distinct** id, so they never touch this path, and `_mint_ids` is reachable only through
   `_remap_payload`, which ruling 22 keeps off step 004's path.
4. **Step 007's reset-first meets the DoD and violates no frozen record.** The step file asks only that
   the `FileButton` be reset after each choice; DoD-5's explicit repeat clause is the **user menu's**.
   Reset-first satisfies the words and is strictly more robust — a trailing reset clears the input only
   after the POST and both reloads resolve, so a second pick during that window would fire no `change`
   event. What `## Skeleton` freezes is signatures, types, constants, labels, placements and pinned
   strings, every one of which is byte-identical; the record's prose sketch of a stub body is body
   content, which the coder owns.
5. **Step 006's four smaller calls are all sound.** The `length > 0` navigate guard is always true for a
   spec-conformant response and is the only thing preventing `/characters/undefined` otherwise
   (`=== undefined` on a `string` would be TS2367). The raw client-route id matches
   `CharacterScreen.tsx:148` while the API path escapes as 030 does — an HTTP path and a react-router
   path, and `encodeURIComponent` is the identity on a decimal string anyway. Forwarding `signal` to the
   loaders is what makes "does nothing further once aborted" true for the reload phase, and neither
   loader rejects. `COVERAGE_WARNING` keeps the literal type via `as const`, so the closed `WarningId`
   union still holds and the pinned sentence is unchanged.

### No test was weakened — all nine amendment sites re-read and confirmed

`OUT_OF_SCOPE_CONTROL` is exactly `/\b(rebuild|re-?index)(s|ed|ing)?\b/i` with its four consumers'
assertion lines absent from the diff; the admin outside-table clause filters only `input[type="file"]`
and pins the exact ordered `toEqual(["Export","Import"])`; `DatabasePage.export.test.tsx`'s two 030
DoD-4 clauses still assert `toEqual([])`; `OUT_OF_SCOPE_ROW_ITEM` is still the full
`/rebuild|export|import|re-?index/i` and the no-stored-open-flag clause is byte-identical; both
`ALLOWED_FIELDS` copies gained exactly three names and lost none; `test_admin_db_router.py`'s
parametrization **replaced** `("POST", …/import)` with `("GET", …/import)`, pinning the route POST-only
at 405, and left the `rebuild`, `vector-index`, `tables/models/rebuild` and `POST …/export` entries
armed; `FORBIDDEN_SURFACE` keeps all four words with `import` admitted on exactly one operation.
**030's Export guards and `fast/002`'s Rebuild guards are all still armed and passing.**

### Domain rules

**R5** — owner scope is in the SQL (`_require_owned_character` filters on both `id` and `user_id`), every
roleplayer-written `user_id` is the caller's unconditionally, and no error `detail` or message carries a
table, column, value or row; the new backend modules contain no logging call at all. **R6** — an archived
target is accepted (no `archived_at` term) and `archived_at` and every timestamp are carried across
verbatim. **R11** — the feature adds no reader.

### `[manual/live]` items carried forward (3 genuine, 8 discharged)

Discharged by the static gates the verifier ran: 001 DoD-13, 002 DoD-12, 003 DoD-11, 004 DoD-13, 005
DoD-13 (`mypy app` + `ruff check .`); 006 DoD-11, 007 DoD-12, 008 DoD-12 (`npm run typecheck`).

Genuinely outstanding, needing a live run:

- **005 DoD-12** — through the dev proxy and nginx (`client_max_body_size 64m`), a multi-megabyte user
  export imports successfully. Not reachable from the suite.
- **007 DoD-11** — in a browser: export a character and import it through the user menu (the page opens
  on the new copy, the tree shows its sessions); export a session and import it from another
  character's Sessions section (listed in that section and under that character in the tree).
- **008 DoD-11** — in a browser, on an instance holding only the admin, import a database export from
  another instance: you land on `/login` and a restored user can sign in.

### Advisory concerns recorded by the verifier, no status effect

- **Two abort predicates in one tree** — the widened form in `app/importUploads.ts`, 030's narrow one in
  `admin/databasePageState.ts`. Not a fault (adjudication 2), but the asymmetry invites a future reader
  to assume one is wrong. Worth a one-line unification in a later pass that owns
  `admin/databasePageState.ts`; amending a delivered 030 helper was correctly outside step 008's scope.
- **Step 002's duplicate-primary-key refusal is unenumerated and therefore untested.** Sound and
  necessary, but nothing in the suite pins it, so a refactor could silently turn it back into a 500. If
  the behaviour matters, a DoD clause should name it.
- **`importDatabase` writes no state on success**, so the confirm stays `loading` until
  `documentNavigation.assign("/login")` takes effect — a navigation the browser blocked would leave the
  modal spinning. Deliberate and acceptable here; worth a note if a later feature makes that navigation
  conditional.
- **`importDatabase`'s `importFile === null` early return is unreachable through the UI** (the confirm
  opens only with a file chosen). Free-function hygiene rather than dead code.
- **`SessionsSection`'s Import button is `loading`, and so disabled, while an import is in flight**, so a
  repeat pick there is possible only once it settles. No DoD requires otherwise — US-136.AC-2's repeat
  clause is the user menu's — but the two controls differ in repeat-pick timing even though they now
  agree on reset ordering.
- **`ROOT_TABLES` has no `database` key by design**, so a direct subscript for that granularity is a
  `KeyError`. `_deserialize_payload` correctly uses `.get`; the docstring is the mitigation.
