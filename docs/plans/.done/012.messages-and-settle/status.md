# Feature 012 — messages-and-settle

| Step | File                                        | Status  | Verifier | Date |
|------|---------------------------------------------|---------|----------|------|
| 001  | `001.table-selectables-errors-models.md` | done    | PASS     | 2026-10-02 |
| 002  | `002.messages-service.md` | done    | PASS     | 2026-10-02 |
| 003  | `003.parser-and-settle.md` | done    | PASS     | 2026-10-02 |
| 004  | `004.stream-router.md` | done    | PASS     | 2026-10-02 |

## Files Changed

### Step 001 — The `messages` table, its three selectables, five errors and the stream models
- `backend/app/db/schema.py` — `messages` Table, CHECK, two indexes and the three read selectables (delivered complete by skeleton; reviewed, unchanged)
- `backend/app/errors.py` — the five stream `DomainError` subclasses (delivered complete by skeleton; reviewed, unchanged)
- `backend/app/models/stream.py` — `_require_non_blank` filled: returns the value verbatim when it holds a non-whitespace char, else raises `ValueError`

### Step 002 — The messages service
- `backend/app/services/messages.py` — five operations filled: reads via `settled_entries`/`current_zone` narrowed through `.selected_columns` inside `_reading`; append/partner/edit each in one `begin()` with one `_now_text()` instant and a session bump; edit classifies via `message_states` and reads back through `current_zone`; private helpers `_list_session_rows`, `_require_session`, `_bump_session`, `_to_message`, `_reading`, `_now_text`

### Step 003 — The `(( ))` parser and the settle service
- `backend/app/services/parens.py` — `classify` (trimmed text starts `((` and ends `))`) and `strip_fragments` (no fragment → unchanged; else drop each shortest `((…))` with its preceding spaces/tabs, collapse 3+ line-break runs to `\n\n`, trim); imports only `re`, `typing`
- `backend/app/services/settle.py` — `settle` (session check, zone via `current_zone`, bury by id list before stamping head, bump) and `reopen` (session, zone, last settled via `settled_entries`, group via raw select, unbury + unstamp, bump), one `begin()` and one `_now_text()` instant each; private `_require_session`, `_bump_session`, `_now_text`; module docstring reworded to drop the "INSERT"/"DELETE" words

### Step 004 — The stream router
- `backend/app/routers/stream.py` — seven handler bodies filled, each one service call scoped by `current_user.id` (partner route passes only `body.text`, never `kind`); `_message_to_response` via `model_validate(from_attributes=True)`, `_settle_to_response` / `_reopen_to_response` field-for-field; imports gain the seven service functions only (sqlalchemy `Connection` only, no `app.db.schema`, no `parens`); no SQL, catches nothing
- `backend/app/main.py` — stream router registration after the sessions router (delivered complete by skeleton; reviewed, unchanged)

## Skeleton

### Step 001 — frozen interface (2026-10-02)
- `backend/app/db/schema.py` — `messages = Table("messages", metadata, ...)` — new. Columns in order: `id` (snowflake PK, `autoincrement=False`), `user_id` (NOT NULL, FK `users.id`), `session_id` (NOT NULL, FK `sessions.id`), `role` Text NOT NULL, `kind` Text NULL, `text` Text NOT NULL, `related_to` (snowflake type, NULL, FK `messages.id`), `settled_at` Text NULL, `tool_name` Text NULL, `tool_payload` Text NULL, `created_at` Text NOT NULL, `updated_at` Text NOT NULL; `CheckConstraint("related_to IS NULL OR settled_at IS NULL", name="ck_messages_buried_or_settled")`; `Index("ix_messages_session_id_settled_at", "session_id", "settled_at")`; `Index("ix_messages_related_to", "related_to")`; no `ondelete`. Declared after `sessions`.
- `backend/app/db/schema.py` — `settled_entries = select(messages).where(messages.c.settled_at.is_not(None))` — new (a `Select`, every `messages` column).
- `backend/app/db/schema.py` — `current_zone = select(messages).where(messages.c.related_to.is_(None), messages.c.settled_at.is_(None))` — new.
- `backend/app/db/schema.py` — `message_states = select(messages.c.id, messages.c.user_id, messages.c.session_id, messages.c.related_to, messages.c.settled_at)` — new (no filter).
- `backend/app/db/schema.py` — module docstring sentence about "the two SQL views" rewritten (D1); imports gain `CheckConstraint`, `select`.
- `backend/app/errors.py` — `class ZoneEmptyError(DomainError)`: `code = "zone_empty"`, `http_status = 409`, `__init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None`, default message "There is nothing in the current zone to settle." — new.
- `backend/app/errors.py` — `class ZoneNotEmptyError(DomainError)`: `zone_not_empty`, 409, same `__init__`, default "The current zone still holds a message; re-open needs an empty zone." — new.
- `backend/app/errors.py` — `class NothingToReopenError(DomainError)`: `nothing_to_reopen`, 409, same `__init__`, default "There is no settled group to re-open." — new.
- `backend/app/errors.py` — `class MessageNotEditableError(DomainError)`: `message_not_editable`, 409, same `__init__`, default "That message cannot be edited." — new.
- `backend/app/errors.py` — `class MessageNotFoundError(DomainError)`: `message_not_found`, 404, same `__init__`, default "That message does not exist." — new.
- `backend/app/models/stream.py` — `def _require_non_blank(value: str) -> str` — new, **stub** (raises `NotImplementedError`); contract: return `value` unchanged if it has a non-whitespace char, else raise `ValueError`.
- `backend/app/models/stream.py` — `NonBlankText = Annotated[str, AfterValidator(_require_non_blank)]` — new (no strip, no max length).
- `backend/app/models/stream.py` — `class MessageResponse(BaseModel)`: `id: SnowflakeOut`, `session_id: SnowflakeOut`, `role: str`, `kind: str | None`, `text: str`, `settled_at: str | None`, `created_at: str`, `updated_at: str` — new.
- `backend/app/models/stream.py` — `class EntryListResponse(BaseModel)`: `entries: list[MessageResponse]` — new.
- `backend/app/models/stream.py` — `class ZoneResponse(BaseModel)`: `messages: list[MessageResponse]` — new.
- `backend/app/models/stream.py` — `class AppendMessageRequest(BaseModel)`: `model_config = ConfigDict(extra="ignore")`, `text: NonBlankText` — new.
- `backend/app/models/stream.py` — `class FilePartnerRequest(BaseModel)`: `extra="ignore"`, `kind: Literal["partner"]` (required), `text: NonBlankText` — new.
- `backend/app/models/stream.py` — `class EditMessageRequest(BaseModel)`: `extra="ignore"`, `text: NonBlankText` — new.
- `backend/app/models/stream.py` — `class SettleResponse(BaseModel)`: `entry_id: SnowflakeOut`, `kind: Literal["turn", "decision"]`, `buried_ids: list[SnowflakeOut]` — new.
- `backend/app/models/stream.py` — `class ReopenResponse(BaseModel)`: `reopened_id: SnowflakeOut`, `restored_ids: list[SnowflakeOut]` — new.
- Caller-compile edits (out of Source-files scope): None. `mypy app` clean (49 files); `ruff check app` clean.

### Step 002 — frozen interface (2026-10-02)
- `backend/app/services/messages.py` — `@dataclass(frozen=True) class StreamMessage`: `id: int`, `session_id: int`, `role: str`, `kind: str | None`, `text: str`, `settled_at: str | None`, `created_at: str`, `updated_at: str` (field order = `MessageResponse`) — new, fully declared.
- `backend/app/services/messages.py` — `def list_entries(connection: Connection, user_id: int, session_id: int) -> list[StreamMessage]` — new, stub (raises `NotImplementedError`).
- `backend/app/services/messages.py` — `def list_zone(connection: Connection, user_id: int, session_id: int) -> list[StreamMessage]` — new, stub.
- `backend/app/services/messages.py` — `def append_message(connection: Connection, generator: SnowflakeGenerator, user_id: int, session_id: int, text: str) -> StreamMessage` — new, stub.
- `backend/app/services/messages.py` — `def file_partner_entry(connection: Connection, generator: SnowflakeGenerator, user_id: int, session_id: int, text: str) -> StreamMessage` — new, stub.
- `backend/app/services/messages.py` — `def edit_message_text(connection: Connection, user_id: int, message_id: int, text: str) -> StreamMessage` — new, stub.
- Types: `Connection` from `sqlalchemy`; `SnowflakeGenerator` from `app.ids` (only `.next_id() -> int` is called). Errors raised: `SessionNotFoundError`, `MessageNotFoundError`, `MessageNotEditableError` from `app.errors`.
- Caller-compile edits (out of Source-files scope): None. `mypy app` clean (50 files); `ruff check app` clean.

### Step 003 — frozen interface (2026-10-02)
- `backend/app/services/parens.py` — `Kind = Literal["turn", "decision"]` — new (type alias; module imports only `typing`).
- `backend/app/services/parens.py` — `def classify(text: str) -> Kind` — new, stub (raises `NotImplementedError`).
- `backend/app/services/parens.py` — `def strip_fragments(text: str) -> str` — new, stub.
- `backend/app/services/settle.py` — `@dataclass(frozen=True) class SettleResult`: `entry_id: int`, `kind: parens.Kind`, `buried_ids: list[int]` — new, fully declared.
- `backend/app/services/settle.py` — `@dataclass(frozen=True) class ReopenResult`: `reopened_id: int`, `restored_ids: list[int]` — new, fully declared.
- `backend/app/services/settle.py` — `def settle(connection: Connection, user_id: int, session_id: int) -> SettleResult` — new, stub.
- `backend/app/services/settle.py` — `def reopen(connection: Connection, user_id: int, session_id: int) -> ReopenResult` — new, stub.
- Types: `Connection` from `sqlalchemy`; `from app.services import parens` (the only `app.services` import). Errors raised: `SessionNotFoundError`, `ZoneEmptyError`, `ZoneNotEmptyError`, `NothingToReopenError` from `app.errors`.
- Caller-compile edits (out of Source-files scope): None. `mypy app` clean (52 files); `ruff check app` clean.

### Step 004 — frozen interface (2026-10-02)
- `backend/app/routers/stream.py` — `router = APIRouter(tags=["stream"], dependencies=[Depends(require_user)])` — new; no prefix, full paths.
- `backend/app/routers/stream.py` — `def _message_to_response(message: StreamMessage) -> MessageResponse` — new, private, stub.
- `backend/app/routers/stream.py` — `def _settle_to_response(result: SettleResult) -> SettleResponse` — new, private, stub.
- `backend/app/routers/stream.py` — `def _reopen_to_response(result: ReopenResult) -> ReopenResponse` — new, private, stub.
- `backend/app/routers/stream.py` — `@router.get("/api/sessions/{session_id}/entries", status_code=200) def list_session_entries(session_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> EntryListResponse` — new, stub.
- `backend/app/routers/stream.py` — `@router.post("/api/sessions/{session_id}/entries", status_code=201) def file_partner(session_id: SnowflakeIn, body: FilePartnerRequest, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)], generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)]) -> MessageResponse` — new, stub.
- `backend/app/routers/stream.py` — `@router.get("/api/sessions/{session_id}/zone", status_code=200) def list_session_zone(session_id: SnowflakeIn, current_user: ..., connection: ...) -> ZoneResponse` — new, stub (dependency annotations as above).
- `backend/app/routers/stream.py` — `@router.post("/api/sessions/{session_id}/zone/messages", status_code=201) def append_zone_message(session_id: SnowflakeIn, body: AppendMessageRequest, current_user: ..., connection: ..., generator: ...) -> MessageResponse` — new, stub.
- `backend/app/routers/stream.py` — `@router.post("/api/sessions/{session_id}/settle", status_code=200) def settle_zone(session_id: SnowflakeIn, current_user: ..., connection: ...) -> SettleResponse` — new, stub; no body parameter.
- `backend/app/routers/stream.py` — `@router.post("/api/sessions/{session_id}/reopen", status_code=200) def reopen_group(session_id: SnowflakeIn, current_user: ..., connection: ...) -> ReopenResponse` — new, stub; no body parameter.
- `backend/app/routers/stream.py` — `@router.patch("/api/messages/{message_id}", status_code=200) def edit_message(message_id: SnowflakeIn, body: EditMessageRequest, current_user: ..., connection: ...) -> MessageResponse` — new, stub.
- Imports in `stream.py`: `Connection` from `sqlalchemy` (only); `get_connection` (`app.db.engine`); `CurrentUser`, `require_user` (`app.dependencies`); `SnowflakeGenerator` (`app.ids`); `SnowflakeIn` (`app.models.ids`); the eight `app.models.stream` models; `get_id_generator` (`app.routers.bootstrap`); `StreamMessage` (`app.services.messages`); `ReopenResult`, `SettleResult` (`app.services.settle`). No `app.db.schema`, no `app.services.parens`. The coder adds the service-function imports (`list_entries`, `list_zone`, `append_message`, `file_partner_entry`, `edit_message_text`, `settle`, `reopen`) when filling bodies.
- `backend/app/main.py` — `from app.routers.stream import router as stream_router`; `app.include_router(stream_router)` immediately after `app.include_router(sessions_router)` (last); module and `create_app` docstrings extended with the stream router's registration — changed (interface wiring, done).
- Caller-compile edits (out of Source-files scope): None. `mypy app` clean (53 files); `ruff check app` clean. OpenAPI lists all seven paths after 011's.

## Tests

### Step 001 — tests (2026-10-02)
- `backend/tests/test_db_schema.py` — covers DoD-1..6 — "messages" appended to `LATER_THAN_006/009/010_TABLES`, `LATER_THAN_011_TABLES` now `{"messages"}`; new 012 block (`PRE_012`/`NEW_012`/`LATER_THAN_012 = set()`) asserting the delta, later-table-proofness, 006/009/010/011 deltas still holding, every earlier later-set naming `messages`; twelve columns, PK, nullability, no `position`/`discussion_id`/`language`/`status`; three FKs (incl. self-reference) with no `ON DELETE`; exactly two non-unique indexes `(session_id, settled_at)` and `(related_to)`; CHECK and FK enforcement plus assistant/NULL-kind insert on a seeded DB; `settled_entries`/`current_zone`/`message_states` row splits and column sets; selectables are `Select`s, not registry tables, and `create_all` creates no SQL view.
- `backend/tests/test_stream_models.py` (new) — covers DoD-7..11 — the five errors (subclass, class-level code/status, non-empty default message, empty detail, envelope from a route); `MessageResponse` decimal-string ids, nulls, exactly eight keys; `EntryListResponse`/`ZoneResponse` single key + order; `SettleResponse`/`ReopenResponse` decimal-string ids and empty lists; append/edit text rules (verbatim, blank/null/absent refused, 1M chars, unknown keys ignored); `FilePartnerRequest` kind exactly `"partner"`, blank text refused, `((ooc))` intact.
- `backend/tests/test_admin_db_router.py` — DoD-12: unchanged. Its `UNDECLARED_NAMES` holds no `"messages"` entry (harvest report 2 §1), so the conditional replacement is not triggered; the existing undeclared-name 404 `unknown_table` tests are the coverage.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓ (existing tests, file unchanged), DoD-13 [manual/live, no test]

### Step 002 — tests (2026-10-02)
- `backend/tests/test_messages_service.py` (new) — covers DoD-1..13 — append returns the minted id / role `user` / null kind+settled_at / verbatim text / one fixed-width instant, in zone not entries, stored `related_to` NULL; three appends stay in the zone in call order; partner block born settled (`settled_at == created_at == updated_at`), in entries not zone, `((…))` texts byte-for-byte with kind `partner`; several partner blocks and filing over a zone draft (draft untouched); seeded zone/settled/buried split with the buried row in neither read; foreign and unknown session/message ids raise `SessionNotFoundError`/`MessageNotFoundError` with no row or session change; zone edit verbatim, `created_at` kept, `updated_at` non-decreasing (strictly later vs an older seed), state columns NULL, same zone position, assistant row editable; buried/filed-partner/settled-turn edits raise `MessageNotEditableError` with nothing moved; bump equality after each write, none after reads or refusals, only the addressed session; archived session works for all five and stays archived; reads leave no transaction open (both exits); AST source checks for no `select(...)` over `messages`, no `delete(`/`DELETE`, no fastapi/`app.services`/parens import, no `related_to` assignment.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓

### Step 003 — tests (2026-10-02)
- `backend/tests/test_parens.py` (new) — covers DoD-1..6 — `classify` decisions (DoD list plus the spec's `((x))`, `(((x)))`) and turns (incl. `""`); `strip_fragments` returns fragment-free text byte-for-byte; the six DoD strip examples plus spec-rule cases (spaces/tabs before a fragment removed, line breaks kept, several fragments, shortest span, 3+ `\n` runs with only spaces/tabs between collapse to `\n\n`, result trimmed); malformed `"((a)) (("` → `"(("`, `"x ((a))"` → `"x"`, both turns; AST check of the module file read from disk: no `app` / `sqlalchemy` / `fastapi` / relative import.
- `backend/tests/test_settle_service.py` (new) — covers DoD-7..23 — all `messages` rows raw-inserted with chosen ascending ids (no step-002 dependency); reads through `current_zone` / `settled_entries` narrowed by session+owner. Empty zone (new session, all-settled session) → `ZoneEmptyError` with messages+sessions snapshots unchanged; lone user row settles as `turn` byte-for-byte, id/created_at kept; last row by id is the head whoever wrote it, earlier rows buried (`related_to`=head, `settled_at` NULL, in neither selectable), `buried_ids` ascending; decisions verbatim incl. `"  ((a)) prose ((b))\n"`; turn head stripped, buried `((x))` text kept; two turns running; one-instant D3 equality and fixed-width shape, only the addressed session bumped; re-open restores the group in id order with NULL state columns, head keeps stripped text, earlier partner entry stays; settle→reopen→settle same result, ids/created_at never move; `ZoneNotEmptyError` (group + new zone row; zone row and no settled row); `NothingToReopenError` for no rows / lone turn / lone decision / born-settled partner last / group then partner (snapshots unchanged, group stays buried); re-open one instant; refused settle/reopen leave `last_used_at`/`updated_at` unchanged; foreign and unknown session ids → `SessionNotFoundError`, A's rows unchanged; archived session works and stays archived; AST source checks: imports `parens` and no other `app.services` module, no `fastapi`, no `delete(`/`insert(` call, no `DELETE` in non-docstring strings.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓, DoD-17 ✓, DoD-18 ✓, DoD-19 ✓, DoD-20 ✓, DoD-21 ✓, DoD-22 ✓, DoD-23 ✓

### Step 004 — tests (2026-10-02)
- `backend/tests/test_stream_router.py` (new) — covers DoD-1..20 — real `create_app()` with file-local seed/login helpers (users A/B, character via `POST /api/characters`, no-setup session via 011's start route): 401 `not_authenticated` on all seven routes; append 201 eight-key `Message` (decimal ids, role `user` even when the body says `assistant`, null kind/settled_at), zone/entries reads; lone settle → `{entry_id, "turn", []}` and recorded turn; fragment stripped on a turn, `((Let's skip ahead))` a verbatim decision; raw-inserted assistant row (via `schema.messages`) becomes head with the two appends buried ascending and invisible; partner block born settled, verbatim, posting order; entries `kind` turn/decision/missing/null → 422 with entries unchanged; blank/whitespace/missing/null text → 422 on append/partner/PATCH with nothing changed, 500 000 chars → 201; `zone_empty` envelope; re-open restores three in order and the head becomes editable; `zone_not_empty`; `nothing_to_reopen` (new session, lone turn, lone partner, group then partner); PATCH zone 200 verbatim, 409 `message_not_editable` on partner / settled turn / buried (text verified unchanged, buried via a later re-open); B gets 404 `session_not_found` / `message_not_found` bodies equal to nobody's and A's state unchanged; `last_used_at` unchanged by reads and refused settle, not earlier after each write, older session moves to top of `GET /api/sessions`; archived session accepts all writes and archive→restore leaves entries/zone identical; route enumeration via `app.openapi()["paths"]` plus a `.path`-tolerant walk finds no discard/stop/DELETE under `/api/sessions/`/`/api/messages/` (sanity: the seven stream paths are present), `DELETE /api/messages/<id>` 405 and message still in zone; non-numeric ids → 422; AST check of `app/routers/stream.py` imports; 011 read/archive/restore still 200.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓, DoD-17 ✓, DoD-18 ✓, DoD-19 ✓, DoD-20 ✓, DoD-21 [manual/live, no test]

## Notes & Issues

_populated by the coder when worth saying_

## Ultra phase

- orient: done 2026-10-02
- harvest: done — docs/.cache/ultra/012.messages-and-settle/harvest.md (2 reports)
- skeleton: done — steps 001, 002, 003, 004
- tests: done — steps 001, 002, 003, 004
- red-gate: PASS (run 1)
- code: done — steps 001, 002, 003, 004 (no re-freeze, no escape valve)
- verify: PASS (run 1) — backend 2409 passed, 0 failed (615 in 012 files); mypy + ruff clean; 2 `[manual/live]` outstanding (001 DoD-13, 004 DoD-21)
