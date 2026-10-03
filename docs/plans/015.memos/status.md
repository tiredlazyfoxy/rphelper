# Feature 015 — memos

| Step | File                                | Status  | Verifier | Date |
|------|-------------------------------------|---------|----------|------|
| 001  | `001.table-errors-models.md`        | done    | PASS     | 2026-10-03 |
| 002  | `002.memos-service.md`              | done    | PASS     | 2026-10-03 |
| 003  | `003.memo-chain-service.md`         | done    | PASS     | 2026-10-03 |
| 004  | `004.memos-router.md`               | done    | PASS     | 2026-10-03 |
| 005  | `005.memos-api-and-reach.md`        | done    | PASS     | 2026-10-03 |
| 006  | `006.memo-level-state.md`           | done    | PASS     | 2026-10-03 |
| 007  | `007.memo-level-group.md`           | done    | PASS     | 2026-10-03 |
| 008  | `008.memo-chain-section.md`         | done    | PASS     | 2026-10-03 |
| 009  | `009.character-notes-section.md`    | done    | PASS     | 2026-10-03 |

## Files Changed

### Step 001 — The `memos` table, `memo_not_found`, and the memo models
- `backend/app/db/schema.py` — `memos` Table (complete at skeleton; no body change)
- `backend/app/errors.py` — `MemoNotFoundError` (complete at skeleton; no body change)
- `backend/app/models/memos.py` — filled the non-blank-verbatim body validator, the nullable inbound `scope_id` parser, and the non-user-scope-requires-`scope_id` model validator

### Step 002 — The memos service
- `backend/app/services/memos.py` — filled `to_memo` (user-level `scope_id` → `None`), `create_memo` (scoped target check → `COALESCE(MAX(sort_key), -1) + 1` allocation → `next_id()` → insert with explicit flags, one transaction), `list_memos` (target check + `(sort_key, id)` select under a private `_reading` rollback guard), `update_memo` (SET built from supplied columns only, plus `updated_at`), `delete_memo` (owner-scoped DELETE, rowcount 0 → `MemoNotFoundError`); private helpers `_require_target`, `_owned`, `_owned_update`, `_require_memo`, `_fetch_existing`, `_reading`, `_now_text`

### Step 003 — The memo chain service
- `backend/app/services/memo_chain.py` — filled `resolve_chain` (owner-scoped session read with no lifecycle predicate → `SessionNotFoundError`; one `memos` select, owner predicate plus OR of one `(scope, scope_id)` term per existing level, setup term only when `setup_id` is set, ordered `sort_key, id`; rows bucketed into the fixed user/character/[setup]/session level list; local rollback guard leaves no transaction open) and `memo_reach` (`is_enabled` checked first)

### Step 004 — The memos router
- `backend/app/routers/memos.py` — filled `_to_response` (`model_validate(..., from_attributes=True)`), `_to_level_response` (level order and memo order preserved), `list_own_memos` (drops `scope_id` for `"user"`; non-user scope without `scope_id` raises a one-entry `RequestValidationError` → 422), `create_own_memo` (`scope_id` → `None` for `"user"`), `update_own_memo` (forwards only fields in `model_fields_set` and not `None`), `delete_own_memo` (empty `Response(status_code=204)`), `read_own_memo_chain`
- `backend/app/main.py` — registration complete at skeleton; no change

### Step 005 — The memos API client and the reach helper
- `frontend/src/app/memosApi.ts` — filled `fetchMemos` (`?scope=` then `&scope_id=` only when non-null, unwraps `memos`), `createMemo` (exactly `{scope, scope_id, body}`, no signal), `updateMemo` (patch sent as given, no signal), `deleteMemo` (resolves `undefined`, no signal), `fetchMemoChain` (unwraps `levels`); private `memoPath` / `memoChainPath`; removed `notImplemented`
- `frontend/src/app/memoReach.ts` — filled `memoReach` (`is_enabled` first) and `reachStatement` (the three context.md sentences in a private table); removed `notImplemented`

### Step 006 — One level's notes: the shared level state
- `frontend/src/app/memoLevelState.ts` — filled the three derivations, `isBlank` (`trim`), `loadMemoLevel` (setupsSectionState abort pattern), `populateMemoLevel`, `setNoteText`, `saveNote` (unchanged → nothing; blank → DELETE; else PATCH `{body}`; held edit dropped when it equals the applied body), `openNewNote` / `setNewNoteText` / `saveNewNote` (blank dropped with no request; typed-during-request text held on the new row), `toggleEnabled` / `toggleForced` via a private one-key `runToggle`, `applyMemoRow` (`updated_at >=` text compare, unknown id ignored), `flushMemoLevel` (`Promise.allSettled`); per-id Records replaced wholesale inside `runInAction`; private `without` / `findMemo` / `dropHeldEditIfBody` / `isAbortRejection` and the three failure sentences; removed `notImplemented`

### Step 007 — The shared level group component
- `frontend/src/app/MemoLevelGroup.tsx` — filled `MemoLevelGroup`: `<section aria-labelledby>` + `Title order={headingOrder}` region; loader for idle/loading, "Could not load notes" + "Retry" (`onRetry`) for failed; ready → dimmed "No notes yet." or a bare `<ul>` (one `<li>` per memo in state order, then the new note) plus the "New note" button (`IconPlus`, disabled while a new note exists); per note a focus-leave wrapper (`relatedTarget` outside `currentTarget` → `saveNote`, dimmed + struck through via `Box` `c`/`td` when disabled) around `MarkdownEditor` "Note", the enabled (`IconCircleCheck`/`IconCircleOff`) and forced (`IconPin`, `color="orange"` only while forced) inline `IconButton`s disabled while a flag write is in flight, the reach line and the red inline failure; the new note with no flags/reach line, saved by `saveNewNote` on focus leave; mount-captured `flushMemoLevel` on unmount; removed `notImplemented`

### Step 008 — The chain's Notes section on the session screen
- `frontend/src/app/memoChainState.ts` — filled `loadMemoChain` (abort-guarded like `loadMemoLevel`; one `fetchMemoChain`, then one `MemoLevelState(scope, scope_id)` per level populated via `populateMemoLevel` in received order, all in one `runInAction`; failure → `"failed"` keeping `levels`); private `isAbortRejection`; removed `notImplemented`
- `frontend/src/app/MemoChainSection.tsx` — filled `MemoChainSection`: `<section aria-labelledby>` + `Title order={3}` "Notes"; small `Loader` for idle/loading; "Could not load notes" + "Retry" (aborts the current controller, loads with a fresh one); ready → one `MemoLevelGroup` per level keyed by scope, private scope-to-title map, `headingOrder={4}`, no-op `onRetry`; removed `notImplemented`
- `frontend/src/app/SessionScreen.tsx` — import + `<MemoChainSection sessionId={props.sessionId} />` as the last child of the ready render's `Stack`, after `SessionStream`

### Step 009 — The character page's Notes section
- `frontend/src/app/CharacterNotesSection.tsx` — filled `CharacterNotesSection`: one `MemoLevelState("character", characterId)` via `useState`; mount load with its own `AbortController` (kept in a ref, aborted on unmount); `MemoLevelGroup` titled "Notes", `headingOrder={3}`, `onRetry` aborting the current controller and loading with a fresh one; no markup of its own; removed `notImplemented`
- `frontend/src/app/CharacterScreen.tsx` — import + `<CharacterNotesSection key={state.characterId} characterId={state.characterId} />` after `SessionsSection` in the existing-mode ready render only

## Skeleton

### Step 001 — frozen interface (2026-10-02)
- `backend/app/db/schema.py` — `memos = Table("memos", metadata, ...)` — new; declared after `messages`, before the `settled_entries` / `current_zone` / `message_states` selectables. Columns in order: `id` (`BigInteger().with_variant(Integer(), "sqlite")`, PK, `autoincrement=False`); `user_id` (same type, `ForeignKey("users.id")`, NOT NULL, no `ondelete`); `scope` (`Enum("user", "character", "setup", "session", name="memos_scope", native_enum=False, create_constraint=True, validate_strings=True, length=16)`, NOT NULL; permitted values readable as `schema.memos.c.scope.type.enums`); `scope_id` (snowflake type, NOT NULL, no FK); `body` (`Text`, NOT NULL); `is_enabled` (`Boolean`, NOT NULL, `default=True`, `server_default=true()`); `is_forced` (`Boolean`, NOT NULL, `default=False`, `server_default=false()`); `sort_key` (`Integer`, NOT NULL, no default); `created_at`, `updated_at` (`Text`, NOT NULL). `Index("ix_memos_user_id_scope_scope_id_sort_key", "user_id", "scope", "scope_id", "sort_key")` (non-unique). `true` added to the sqlalchemy import. Complete (declarative).
- `backend/app/errors.py` — `class MemoNotFoundError(DomainError)`: `code = "memo_not_found"`, `http_status = 404`, `__init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None` (default message "That memo does not exist.") — new; declared after `MessageNotFoundError`. Complete (declarative, same shape as `SessionNotFoundError`).
- `backend/app/models/memos.py` — new module:
  - `MemoScope = Literal["user", "character", "setup", "session"]` — new (the scope literal; read with `typing.get_args`).
  - `_require_non_blank_body(value: str) -> str` — new, **stub** (raises `NotImplementedError`).
  - `NonBlankBody = Annotated[str, AfterValidator(_require_non_blank_body)]` — new.
  - `_parse_optional_scope_id(value: Any) -> int | None` — new, **stub**.
  - `OptionalScopeIdIn = Annotated[int | None, BeforeValidator(_parse_optional_scope_id)]` — new (local nullable inbound snowflake; `models/sessions.py`'s `OptionalSnowflakeIn` not reused because its error text names a setup).
  - `class MemoResponse(BaseModel)`: `id: SnowflakeOut`, `scope: MemoScope`, `scope_id: SnowflakeOut | None`, `body: str`, `is_enabled: bool`, `is_forced: bool`, `sort_key: int`, `created_at: str`, `updated_at: str` — new; build with `MemoResponse.model_validate(value, from_attributes=True)`.
  - `class MemoListResponse(BaseModel)`: `memos: list[MemoResponse]` — new.
  - `class MemoChainLevelResponse(BaseModel)`: `scope: MemoScope`, `scope_id: SnowflakeOut | None`, `memos: list[MemoResponse]` — new.
  - `class MemoChainResponse(BaseModel)`: `levels: list[MemoChainLevelResponse]` — new.
  - `class CreateMemoRequest(BaseModel)`: `model_config = ConfigDict(extra="ignore")`; `scope: MemoScope`; `scope_id: OptionalScopeIdIn = None`; `body: NonBlankBody`; `@model_validator(mode="after") _require_scope_id_for_non_user_scope(self) -> Self` — new, validator **stub**.
  - `class UpdateMemoRequest(BaseModel)`: `model_config = ConfigDict(extra="ignore")`; `body: NonBlankBody | None = None`; `is_enabled: bool | None = None`; `is_forced: bool | None = None` — new.
- No name collisions in `app/models/`; no renames.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `mypy app` clean (54 files), `ruff check .` clean.

### Step 002 — frozen interface (2026-10-02)
- `backend/app/services/memos.py` — new module (imports only `sqlalchemy.Connection`, `sqlalchemy.Row`, `typing.Any`, `app.ids.SnowflakeGenerator`, `app.models.memos.MemoScope` at stub time; the coder adds the schema Tables and errors):
  - `@dataclass(frozen=True) class Memo`: `id: int`, `scope: MemoScope`, `scope_id: int | None`, `body: str`, `is_enabled: bool`, `is_forced: bool`, `sort_key: int`, `created_at: str`, `updated_at: str` — new. Complete (declarative); no `user_id`.
  - `to_memo(row: Row[Any]) -> Memo` — new, **stub** (the public pure row mapper; input is a row of all ten `memos` columns; `003` imports this and `Memo`).
  - `create_memo(connection: Connection, generator: SnowflakeGenerator, user_id: int, scope: MemoScope, scope_id: int | None, body: str) -> Memo` — new, **stub**.
  - `list_memos(connection: Connection, user_id: int, scope: MemoScope, scope_id: int | None) -> list[Memo]` — new, **stub**.
  - `update_memo(connection: Connection, user_id: int, memo_id: int, body: str | None = None, is_enabled: bool | None = None, is_forced: bool | None = None) -> Memo` — new, **stub** (`None` = not supplied).
  - `delete_memo(connection: Connection, user_id: int, memo_id: int) -> None` — new, **stub**.
- Errors raised (existing, `app.errors`): `MemoNotFoundError`, `CharacterNotFoundError`, `SetupNotFoundError`, `SessionNotFoundError`.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `mypy app` clean (55 files), `ruff check .` clean.

### Step 003 — frozen interface (2026-10-02)
- `backend/app/services/memo_chain.py` — new module (imports at stub time: `dataclasses.dataclass`, `typing.Literal`, `sqlalchemy.Connection`, `app.models.memos.MemoScope`, `app.services.memos.Memo`; the coder adds `to_memo` from `app.services.memos` — and nothing else from it — plus the `memos` / `sessions` Tables and `SessionNotFoundError`):
  - `MemoReach = Literal["forced", "searchable", "disabled"]` — new (the reach literal; read with `typing.get_args`). Complete (declarative).
  - `@dataclass(frozen=True) class MemoChainLevel`: `scope: MemoScope`, `scope_id: int | None`, `memos: list[Memo]` — new. Complete (declarative); `MemoChainLevelResponse.model_validate(level, from_attributes=True)` builds from it.
  - `resolve_chain(connection: Connection, user_id: int, session_id: int) -> list[MemoChainLevel]` — new, **stub** (raises `NotImplementedError`; raises `app.errors.SessionNotFoundError` once implemented).
  - `memo_reach(is_enabled: bool, is_forced: bool) -> MemoReach` — new, **stub**.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `mypy app` clean (56 files), `ruff check .` clean.

### Step 004 — frozen interface (2026-10-02)
- `backend/app/routers/memos.py` — new module (imports at stub time: `Annotated`, `APIRouter`, `Depends`, `Response` from fastapi, `Connection`, `get_connection`, `CurrentUser`, `require_user`, `SnowflakeGenerator`, `SnowflakeIn`, the six request/response models plus `MemoScope` from `app.models.memos`, `get_id_generator`, `MemoChainLevel`, `Memo`; the coder adds the service functions `create_memo` / `list_memos` / `update_memo` / `delete_memo` / `resolve_chain` and whatever builds the handler's 422):
  - `router = APIRouter(tags=["memos"], dependencies=[Depends(require_user)])` — new; no prefix, full literal paths. Complete (declarative).
  - `_to_response(memo: Memo) -> MemoResponse` — new, **stub**.
  - `_to_level_response(level: MemoChainLevel) -> MemoChainLevelResponse` — new, **stub**.
  - `@router.get("/api/memos", status_code=200) list_own_memos(scope: MemoScope, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)], scope_id: SnowflakeIn | None = None) -> MemoListResponse` — new, **stub** (`scope` required query param, `scope_id` optional query param; verified in OpenAPI).
  - `@router.post("/api/memos", status_code=201) create_own_memo(body: CreateMemoRequest, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)], generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)]) -> MemoResponse` — new, **stub**.
  - `@router.patch("/api/memos/{memo_id}", status_code=200) update_own_memo(memo_id: SnowflakeIn, body: UpdateMemoRequest, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> MemoResponse` — new, **stub**.
  - `@router.delete("/api/memos/{memo_id}", status_code=204) delete_own_memo(memo_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> Response` — new, **stub** (returns an empty `Response`; no `response_model`).
  - `@router.get("/api/sessions/{session_id}/memo-chain", status_code=200) read_own_memo_chain(session_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> MemoChainResponse` — new, **stub**.
- `backend/app/main.py` — `from app.routers.memos import router as memos_router`; `app.include_router(memos_router)` appended after `app.include_router(stream_router)` (last) — changed; module and `create_app` docstrings' registration-order prose extended. Complete (wiring).
- Caller-compile edits (out of Source-files scope): None.
- Gates: `mypy app` clean (57 files), `ruff check .` clean. Unauthenticated `GET /api/memos?scope=user` answers 401 with the router registered.

### Step 005 — frozen interface (2026-10-02)
Frontend stub convention: each skeleton file has a private `function notImplemented(name: string, ...args: unknown[]): never` (throws); every stub body is `return notImplemented("<name>", ...params)`. Type declarations are real. The coder deletes the helper when the bodies land and adds the `../shared/api` imports (not imported at stub time).
- `frontend/src/app/memosApi.ts` — new module:
  - `export type MemoScope = "user" | "character" | "setup" | "session"` — new. Complete (declarative).
  - `export type Memo = { id: string; scope: MemoScope; scope_id: string | null; body: string; is_enabled: boolean; is_forced: boolean; sort_key: number; created_at: string; updated_at: string }` — new. Complete.
  - `export type MemoChainLevel = { scope: MemoScope; scope_id: string | null; memos: Memo[] }` — new. Complete.
  - `export type MemoPatch = { body?: string; is_enabled?: boolean; is_forced?: boolean }` — new. Complete.
  - `export type MemoListResponse = { memos: Memo[] }` — new (wire envelope). Complete.
  - `export type MemoChainResponse = { levels: MemoChainLevel[] }` — new (wire envelope). Complete.
  - `export async function fetchMemos(scope: MemoScope, scopeId: string | null, signal?: AbortSignal): Promise<Memo[]>` — new, **stub**.
  - `export async function createMemo(scope: MemoScope, scopeId: string | null, body: string): Promise<Memo>` — new, **stub** (no signal, D5).
  - `export async function updateMemo(memoId: string, patch: MemoPatch): Promise<Memo>` — new, **stub** (no signal).
  - `export async function deleteMemo(memoId: string): Promise<void>` — new, **stub** (no signal; resolves `undefined`).
  - `export async function fetchMemoChain(sessionId: string, signal?: AbortSignal): Promise<MemoChainLevel[]>` — new, **stub**.
- `frontend/src/app/memoReach.ts` — new module:
  - `export type MemoReach = "forced" | "searchable" | "disabled"` — new. Complete.
  - `export type MemoReachFlags = { is_enabled: boolean; is_forced: boolean }` — new (structural input; a `Memo` satisfies it). Complete.
  - `export function memoReach(memo: MemoReachFlags): MemoReach` — new, **stub**.
  - `export function reachStatement(reach: MemoReach): string` — new, **stub**.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean.

### Step 006 — frozen interface (2026-10-02)
Same frontend stub convention as 005 (private `notImplemented`). Imports at stub time: `makeAutoObservable` from `mobx`, `type { Memo, MemoScope }` from `./memosApi`; the coder adds `runInAction` and `fetchMemos` / `createMemo` / `updateMemo` / `deleteMemo`.
- `frontend/src/app/memoLevelState.ts` — new module:
  - `export type MemoLevelStatus = "idle" | "loading" | "ready" | "failed"` — new. Complete.
  - `export type MemoNewNote = { text: string; saving: boolean; failure: string | null }` — new (the new note; no id). Complete.
  - `export class MemoLevelState` — new. Complete (declarative): `constructor(scope: MemoScope, scopeId: string | null)` calling `makeAutoObservable(this, {}, { autoBind: true })`; fields `scope: MemoScope`; `scopeId: string | null`; `status: MemoLevelStatus = "idle"`; `memos: Memo[] = []`; `editorTexts: Record<string, string> = {}` (held edit by memo id, absent = the body); `newNote: MemoNewNote | null = null`; `failures: Record<string, string> = {}` (absent = no failure); `flagWritesInFlight: Record<string, true> = {}` (absent = none). Tests read `editorTexts` / `failures` / `flagWritesInFlight` only through the derivations below; `newNote` is read directly (`newNote.text`, `newNote.saving`, `newNote.failure`).
  - `export function noteText(state: MemoLevelState, memoId: string): string` — new, **stub**.
  - `export function noteFailure(state: MemoLevelState, memoId: string): string | null` — new, **stub**.
  - `export function isFlagWriteInFlight(state: MemoLevelState, memoId: string): boolean` — new, **stub**.
  - `export function isBlank(text: string): boolean` — new, **stub**.
  - `export async function loadMemoLevel(state: MemoLevelState, signal?: AbortSignal): Promise<void>` — new, **stub**.
  - `export function populateMemoLevel(state: MemoLevelState, memos: Memo[]): void` — new, **stub**.
  - `export function setNoteText(state: MemoLevelState, memoId: string, text: string): void` — new, **stub**.
  - `export async function saveNote(state: MemoLevelState, memoId: string): Promise<void>` — new, **stub**.
  - `export function openNewNote(state: MemoLevelState): void` — new, **stub**.
  - `export function setNewNoteText(state: MemoLevelState, text: string): void` — new, **stub**.
  - `export async function saveNewNote(state: MemoLevelState): Promise<void>` — new, **stub**.
  - `export async function toggleEnabled(state: MemoLevelState, memoId: string): Promise<void>` — new, **stub**.
  - `export async function toggleForced(state: MemoLevelState, memoId: string): Promise<void>` — new, **stub**.
  - `export function applyMemoRow(state: MemoLevelState, memo: Memo): void` — new, **stub**.
  - `export async function flushMemoLevel(state: MemoLevelState): Promise<void>` — new, **stub**.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean.

### Step 007 — frozen interface (2026-10-02)
Same frontend stub convention as 005 (private `notImplemented`). Imports at stub time: `type { TitleOrder }` from `@mantine/core`, `observer` from `mobx-react-lite`, `type { MemoLevelState }` from `./memoLevelState`; the coder adds the 006 free functions, `memoReach` / `reachStatement`, `MarkdownEditor`, `IconButton`, the Tabler icons and the Mantine layout components.
- `frontend/src/app/MemoLevelGroup.tsx` — new module:
  - `export type MemoLevelGroupProps = { state: MemoLevelState; title: string; headingOrder: TitleOrder; onRetry: () => void }` — new (`TitleOrder` is Mantine's `1 | 2 | 3 | 4 | 5 | 6`). Complete (declarative).
  - `export const MemoLevelGroup = observer(function MemoLevelGroup(props: MemoLevelGroupProps): React.JSX.Element)` — new, **stub** (body throws). Named export; usage `<MemoLevelGroup state={...} title="..." headingOrder={3} onRetry={...} />`.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean.

### Step 008 — frozen interface (2026-10-02)
Same frontend stub convention as 005 (private `notImplemented`). Imports at stub time: `makeAutoObservable` from `mobx` and `type { MemoLevelState }` from `./memoLevelState` (chain state); `observer` from `mobx-react-lite` (section). The coder adds `runInAction`, `fetchMemoChain`, the `MemoLevelState` value import and `populateMemoLevel` (state), and `useState` / `useEffect`, `MemoChainState` / `loadMemoChain`, `MemoLevelGroup`, Mantine components (section).
- `frontend/src/app/memoChainState.ts` — new module:
  - `export type MemoChainStatus = "idle" | "loading" | "ready" | "failed"` — new. Complete.
  - `export class MemoChainState` — new. Complete (declarative): `constructor(sessionId: string)` calling `makeAutoObservable(this, {}, { autoBind: true })`; fields `sessionId: string`; `status: MemoChainStatus = "idle"`; `levels: MemoLevelState[] = []`.
  - `export async function loadMemoChain(state: MemoChainState, signal?: AbortSignal): Promise<void>` — new, **stub**.
- `frontend/src/app/MemoChainSection.tsx` — new module:
  - `export type MemoChainSectionProps = { sessionId: string }` — new. Complete.
  - `export const MemoChainSection = observer(function MemoChainSection(props: MemoChainSectionProps): React.JSX.Element)` — new, **stub** (body throws). Named export; usage `<MemoChainSection sessionId={...} />`.
- `frontend/src/app/SessionScreen.tsx` — **not edited at skeleton time** (Source file, no signature change). Mounting `<MemoChainSection sessionId={…} />` as the last child of the ready render is behavior left to the coder; mounting the throwing stub now would break the currently-passing screen tests.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean.

### Step 009 — frozen interface (2026-10-02)
Same frontend stub convention as 005 (private `notImplemented`). Imports at stub time: `observer` from `mobx-react-lite`. The coder adds `useState` / `useEffect` / `useRef`, `MemoLevelState` / `loadMemoLevel` from `./memoLevelState`, and `MemoLevelGroup` from `./MemoLevelGroup` (title "Notes", `headingOrder={3}` — the `Title order={3}` the page's Setups/Sessions headings use).
- `frontend/src/app/CharacterNotesSection.tsx` — new module:
  - `export type CharacterNotesSectionProps = { characterId: string }` — new. Complete.
  - `export const CharacterNotesSection = observer(function CharacterNotesSection(props: CharacterNotesSectionProps): React.JSX.Element)` — new, **stub** (body throws). Named export; usage `<CharacterNotesSection key={id} characterId={id} />`.
- `frontend/src/app/CharacterScreen.tsx` — **not edited at skeleton time** (Source file, no signature change). Mounting `<CharacterNotesSection key={character.id} characterId={character.id} />` after `SessionsSection` in the existing-mode ready render is behavior left to the coder; mounting the throwing stub now would break the currently-passing screen tests.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean.

## Tests

### Step 001 — tests (2026-10-02)
- `backend/tests/test_db_schema.py` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-11 — `"memos"` added to `LATER_THAN_006/009/010/011/012_TABLES`; new 015 section (`PRE_015_TABLES`, `NEW_015_TABLES = {"memos"}`, empty `LATER_THAN_015_TABLES`): later-table-proof delta incl. `create_all`, ten NOT NULL columns + `id` PK + no title/name/archived_at/state/status, single `user_id` → `users.id` FK with no `ON DELETE` and none on `scope_id`, exactly one non-unique index `(user_id, scope, scope_id, sort_key)`, flag server defaults (enabled / not forced), scope CHECK refuses `world` and accepts the four, `users` FK enforced, duplicate level+sort_key allowed; earlier 006/009/010/011/012 deltas re-asserted.
- `backend/tests/test_memos_models.py` — covers DoD-6, DoD-7, DoD-8, DoD-9, DoD-10 — scope literal == column `Enum.enums` == the four scopes; `MemoNotFoundError` class attrs, empty detail, 404 envelope through `register_exception_handlers`; `MemoResponse` ids as decimal strings / null `scope_id` / numeric `sort_key` / exactly nine keys, list and chain envelopes; `CreateMemoRequest` and `UpdateMemoRequest` parse/refuse cases, verbatim body, unknown keys ignored.
- `backend/tests/test_admin_db_router.py` — DoD-12: checked, `UNDECLARED_NAMES` holds no `"memos"`; unchanged (its existing tests are the coverage).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓ (no edit needed), DoD-13 [manual/live, no test]

### Step 002 — tests (2026-10-02)
- `backend/tests/test_memos_service.py` — covers DoD-1..DoD-15 — create at all four levels (minted id from a recording generator, defaults, sort_key 0, fixed-width equal timestamps, stored `user_id`, user-level stored `scope_id` = caller, no `user_id` on the value); user-level create ignores a supplied `scope_id` and is invisible to another user; verbatim markdown body returned/stored/listed; D4 allocation (0,1,2; per-level; raw 2,5 → 6; another user's 40 ignored at character and user level; gaps kept, highest-deleted → remaining max + 1); foreign/unknown character/setup/session refused on create (no row, generator not called) and list; archived targets accepted; list scoping, `(sort_key, id)` order with a tie, disabled included, null user-level `scope_id`; body-only update; `is_enabled` alone keeps `is_forced` (forced and not-forced sequences); `is_forced` alone keeps `is_enabled`; empty update writes nothing; foreign/unknown update/delete → `MemoNotFoundError` with the owner's row intact; delete removes only that row, then update/delete raise; list leaves no transaction open on success and refusal; source has no fastapi import, no `app.services` import, no `archived_at`, no `title`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓

### Step 003 — tests (2026-10-02)
- `backend/tests/test_memo_chain_service.py` — covers DoD-1..DoD-10 — all seeding raw-inserted (users, characters, setups, sessions, memos; no dependency on `create_memo`): with-setup chain has four levels `user/character/setup/session` with scope_ids `None`/character/setup/session and per-level ids ordered by `(sort_key, id)` incl. a tie, disabled and disabled+forced notes included with their flags; no-setup chain has exactly three levels, every note present, setup notes of the same character absent; empty levels still listed (4 or 3 all-empty, and a partially-empty chain); excludes other session/character/setup notes and every note of another user incl. raw rows matching this session's levels; foreign/unknown session → `SessionNotFoundError`; archived session+character+setup still resolve all four levels; exactly two `SELECT`s via a `before_cursor_execute` recorder (with and without setup); no open transaction after success and refusal, `memos` rows unchanged; `memo_reach` four combinations plus `MemoReach` literal values; AST check that `app.services` imports are only `Memo` and `to_memo` from `app.services.memos`, no fastapi, no `insert(`/`update(`/`delete(` text.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓

### Step 004 — tests (2026-10-02)
- `backend/tests/test_memos_router.py` — covers DoD-1..DoD-15 — real `create_app()` with `dependency_overrides[get_settings]`, two roleplayers each on their own cookie client, parents/archives through 009/010/011 routes: five routes 401 `not_authenticated` anonymously; create at all four levels → 201 nine-key wire object (decimal-string id, null user `scope_id`, defaults, sort_key 0, equal fixed-width timestamps, no `user_id`) then listed; flags/sort_key/user_id/title in a create ignored (user and character level), note the caller's and not B's; verbatim body; user create with another `scope_id` lands at the caller's user level; 422 with zero `memos` rows for blank/missing body, missing `scope_id`, `world`, non-numeric `scope_id`, bad list queries, blank PATCH body, `/api/memos/abc` PATCH/DELETE, `/api/sessions/abc/memo-chain`; B against A's character/setup/session/memo/chain → 404 codes with empty `detail`, body equal to the unknown-id body, A's data unchanged; enable toggle never touches `is_forced` (forced and not-forced); forced alone keeps disabled; body-only PATCH, `body: null` ignored, `PATCH {}` unchanged; DELETE 204 empty then gone from list/chain and 404 on PATCH/DELETE; four-level and three-level (no setup) chain order, scope_ids and per-level notes; disabled (and disabled+forced) listed and chained with flags; archived C/S/X list/create/chain succeed; sort_key 0,1,2 → delete middle → 3 listed last; `GET /api/sessions/<X>`, `/api/characters/<C>/sessions` and `/setups` still 200.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 [manual/live, no test]

### Step 005 — tests (2026-10-02)
- `frontend/tests/app/memosApi.test.ts` — covers DoD-1..DoD-7 — `fetch` stubbed per test with `vi.stubGlobal`, requests matched by exact pathname + search + method: listing query exactly `?scope=user` (no `scope_id`) and `?scope=<s>&scope_id=<id>` for character/setup/session, unwrapped `memos` in order, ids/scope_ids identical strings past MAX_SAFE_INTEGER, user `scope_id` null; create body exactly `{scope, scope_id, body}` (session with verbatim `"  # h\n"`, user with `scope_id: null`), never a flag or `sort_key`, resolves to the 201 row; PATCH bodies exactly `{is_enabled:false}` / `{is_forced:true}` / `{body:"y"}`; DELETE resolves `undefined` on 204; chain GET path, levels in payload order (four and three), level `scope_id`s string/null; 404 `memo_not_found` on update/delete, 404 `session_not_found` on chain, 422 on create all reject with `ApiError`; no signal on create/update/delete, given signal passed by `fetchMemos` / `fetchMemoChain`.
- `frontend/tests/app/memoReach.test.ts` — covers DoD-8, DoD-9 — four flag combinations (disabled+forced → `"disabled"`), also with bare flag objects; the three statements compared to the literal strings.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓

### Step 006 — tests (2026-10-02)
- `frontend/tests/app/memoLevelState.test.ts` — covers DoD-1..DoD-18 — `fetch` stubbed per test (`stubBackend` recording method + pathname + search + parsed JSON body; `stubHeld` deferred responses for in-flight assertions; `serveEcho` server that merges PATCH keys with a later `updated_at`, answers DELETE 204 and POST 201): fresh character/user state; load GET exact queries (`?scope=character&scope_id=c1`, `?scope=user`), `"loading"` while pending, server order with disabled rows, failure keeps rows and resolves, abort (late response and AbortError rejection) writes nothing; populate writes in order with no request; `noteText`/`setNoteText` never touch `body`; unchanged text sends nothing; PATCH exactly `{body}`, old body while pending, returned row applied, text typed mid-request kept; save/delete/change failure sentences, text kept, failure cleared before retry; `""`/`"  \n"` delete with no PATCH, failed delete keeps note; one new note, blank new note sends nothing; POST exactly `{scope, scope_id, body}` (setup `s1`, user `null`), saving while pending, second save sends nothing, row appended last enabled/not forced, mid-request text becomes `noteText`, failed create retried; enable/forced toggles send exactly one key and keep the other flag (forced/not-forced/disabled cases); in-flight mark and never-optimistic flags; `applyMemoRow` later/equal/older/unknown id plus newer-first concurrent save+toggle; flush sends exactly PATCH+DELETE+POST (no POST for blank new note) and resolves on failures; `isBlank` cases; autoruns on `memos` and `noteText`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓, DoD-17 ✓, DoD-18 ✓

### Step 007 — tests (2026-10-02)
- `frontend/tests/app/MemoLevelGroup.test.tsx` — covers DoD-1..DoD-16 — `<AppProviders><MemoLevelGroup …/></AppProviders>` over a `MemoLevelState` built directly (`populateMemoLevel` for ready, `loadMemoLevel` with a held / 500 stub for loading / failed); `MarkdownEditor` mocked as the SetupsSection labelled-`<textarea>` stub, with the id from `useId` (several "Note" editors at once) and the received `label`/`value` recorded; `fetch` stubbed by exact method + path + query with parsed bodies (`serveNotes` echo server with per-method 500s, `stubHeld` for pending): region named by title + heading (level from `headingOrder`), one list of two listitems in state order, one "Note" textbox each and none other; mock props label "Note" + bodies; reach lines and flag-control labels for all four flag combinations; Disable/Enable sequences send exactly `{is_enabled:false}` then `{is_enabled:true}` ending forced / searchable; Force on disabled sends `{is_forced:true}` and stays disabled; pending toggle disables both buttons with labels and reach unchanged; blur PATCHes `{body}`, unchanged blur sends nothing; cleared blur DELETEs with no PATCH/dialog and removes the item; save/delete/change failure sentences inside the item, typed text kept, no notification; New note item (empty, no flags, no reach line, button disabled), blank / `"  \n"` blur drops it with no request; "Plan" POSTs exactly `{scope, scope_id, body}` (character and user/null) then searchable saved item, New note re-enabled; failed create keeps item + text + failure, button disabled; empty line; loader without New note; "Could not load notes" + Retry calls `onRetry` once; unmount flushes a typed-unblurred PATCH, a "Later" POST, and nothing when unchanged.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓, DoD-17 [manual/live, no test]

### Step 008 — tests (2026-10-02)
- `frontend/tests/app/memoChainState.test.ts` — covers DoD-1 — fresh `MemoChainState("s1")` (sessionId, `"idle"`, no levels); `"loading"` while a held request is pending, calls exactly `[GET /api/sessions/s1/memo-chain]` and no `/api/memos` request; four- and three-level answers become `MemoLevelState` instances in the received order (also a non-canonical order) with `scope`, `scopeId` (null for user), notes in order and status `"ready"`; 500 / transport → `"failed"`, resolves, previously loaded levels kept; pre-aborted signal leaves `"idle"`, mid-flight abort (late success or AbortError rejection) writes no levels, no ready/failed.
- `frontend/tests/app/MemoChainSection.test.tsx` — covers DoD-2..DoD-6 — section alone in `AppProviders`, `MarkdownEditor` mocked as step 007's `useId` textarea stub: "Notes" region + heading holding "Your/Character/Setup/Session notes" regions in order, each listing exactly its level's note texts, group headings one level below "Notes"; three-level chain → exactly three regions, no "Setup notes" region/heading/text, every note listed; empty level shows "No notes yet."; disabled note shows "Enable note"; per group (it.each) New note → type → blur POSTs exactly `{scope, scope_id, body}` (user null, character/setup/session ids), note appears in that group only, one chain read total, none after the POST, no `/api/memos` listing; held chain → loader in "Notes"; 500 / transport → "Could not load notes" + "Retry" in "Notes", no notification; Retry re-requests and renders the groups.
- `frontend/tests/app/SessionScreen.test.tsx` — covers DoD-7, DoD-8, DoD-9, DoD-10 — DoD-10 amendments: `streamAnswer` also answers `GET /api/sessions/<id>/memo-chain` by exact path (`{levels: []}` default), 011 DoD-5's exact request list gains the memo-chain GET, `Seen` records parsed bodies, `MarkdownEditor` mocked (useId stub); 011 DoD-10's no-textbox/no-button clause was already replaced by 013 DoD-6 (Archive/Restore/"Actions for" absence), so nothing to scope; no assertion dropped. New 015 block: ready → "Notes" region in main after the header, character link and composer, outside the header block, one chain read, a's notes shown; loading / "Session not found" / 500 / transport → no "Notes" region and no chain request; a→b navigation requests b's chain and shows only b's notes; typing (no blur) into a's note then navigating PATCHes `/api/memos/<id>` with exactly `{body: typed}`.
- `frontend/tests/app/App.test.tsx` — covers DoD-7, DoD-10 — `stubWorkspace` answers `GET /api/sessions/<id>/memo-chain` by exact pathname (`{levels: []}` for a held session, 404 `session_not_found` otherwise); one route clause: at `/sessions/1` the main region holds the "Notes" region after the start-time heading, from one chain read.
- `frontend/tests/entries.test.tsx` — DoD-10: checked, unchanged — its only `/sessions/abc123` mounts answer the session GET 404, so the screen never reaches ready and no memo-chain request is made (008.context.md: change only if a clause's session GET succeeds).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 [manual/live, no test]

### Step 009 — tests (2026-10-02)
- `frontend/tests/app/CharacterNotesSection.test.tsx` — covers DoD-1, DoD-2, DoD-3 — section alone in `AppProviders`, `MarkdownEditor` mocked as step 007's `useId` textarea stub, `fetch` recorded by exact method + path + query + parsed body: the only request is `GET /api/memos?scope=character&scope_id=<C>`; "Notes" region + heading listing the payload's three bodies in order, the disabled one with "Enable note"; empty listing → "No notes yet."; New note → "Voice: dry" → blur POSTs exactly `{scope:"character", scope_id:C, body}`, then the saved note shows "Searchable: …" and no listing follows the POST (one listing total); 500 / transport → "Could not load notes" + "Retry" in the region, no notification; Retry re-requests the same query and renders the notes.
- `frontend/tests/app/CharacterScreen.test.tsx` — covers DoD-4, DoD-5, DoD-6, DoD-7 — DoD-7 amendments: `sectionListing` answers `GET /api/memos?scope=character&scope_id=<id>` with `{memos: []}` by exact path + query (`isNotesListing`), the hand-written stubs of 010 DoD-12 and 011 DoD-14 gain the same branch, `MarkdownEditor` mock switched to the `useId` id (queries are by label); no assertion dropped. New 015 blocks: loaded → "Notes" region + heading in main, after Sessions (and Setups), heading level equal to the Sessions heading's, exactly one memo request with the exact query; new mode / "Character not found" / "Could not load the character" → no Notes region and no `/api/memos` request; archived character → region present, New note + blur POSTs `{scope:"character", scope_id:ID_A, body}`; a→b navigation requests b's listing once and shows only b's note, none of a's.
- `frontend/tests/app/App.test.tsx` — covers DoD-4, DoD-7 — `/characters/1` stub and `stubWorkspace` answer the character notes listing by exact pathname + query (`{memos: []}` for a held character, 404 otherwise); step 008's amendments kept. One clause: at `/characters/<A>` the main region holds the "Notes" region after the "Sessions" region from one listing with the exact query.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 [manual/live, no test]

## Notes & Issues

_populated by the coder when worth saying_

## Ultra phase

- orient: done 2026-10-02
- harvest: done — docs/.cache/ultra/015.memos/harvest.md (2 reports)
- skeleton: done — steps 001, 002, 003, 004, 005, 006, 007, 008, 009
- tests: done — steps 001, 002, 003, 004, 005, 006, 007, 008, 009
- red-gate: PASS (run 1)
- code: done — steps 001, 002, 003, 004, 005, 006, 007, 008, 009
- verify: PASS (run 1)
