# Feature 023 — partner-translation

| Step | File                                       | Status  | Verifier | Date |
|------|--------------------------------------------|---------|----------|------|
| 001  | `001.table-error-model-invalidation.md`    | done    | PASS        | 2026-10-04    |
| 002  | `002.translation-service.md`               | done    | PASS        | 2026-10-04    |
| 003  | `003.translation-route.md`                 | done    | PASS        | 2026-10-04    |
| 004  | `004.translation-client-state.md`          | done    | PASS        | 2026-10-04    |
| 005  | `005.flicker-ui.md`                        | done    | PASS        | 2026-10-04    |

## Files Changed

### Step 001 — the translations table, its error, its model and edit invalidation
- `backend/app/db/schema.py` — verified unchanged: the skeleton's `translations` Table already matches D7 exactly (six NOT NULL columns, `user_id` FK `users.id`, bare `message_id` FK `messages.id` with no `ondelete`, `uq_translations_message_id_target_language` on `(message_id, target_language)`, no `updated_at`, no state column). No edit made.
- `backend/app/models/translation.py` — verified unchanged: `TranslationResponse` already carries the four wire keys with `SnowflakeOut` + `from_attributes`; serialises `message_id` as a decimal string. No edit made.
- `backend/app/errors.py` — filled `TranslationFailedError.__init__` (the only stub): default message "The translation failed. Showing the original." when none is given, an explicit message wins, `detail={"message_id": str(message_id)}`, through `super().__init__(message, detail)`. Frozen signature untouched.
- `backend/app/services/messages.py` — D11: imported `translations` and, inside `edit_message_text`'s existing `with connection.begin():` immediately after the `messages.update(...)` execute, discards every `translations` row for the edited id scoped to the caller's `user_id` (R5). Signature and return value unchanged; refusal paths never reach it; the discard shares the edit's transaction. Module docstring's "no delete" sentence amended to name this one delete. **This lands under the user's recorded D11 resolution (2026-10-04, `## Ultra phase`): 012's no-delete guard narrowed to permit exactly one delete targeting `translations`.** The module names no `messages` delete, contains no uppercase raw SQL keyword, and imports `delete` under no alias.

### Step 002 — the translation service
- `backend/app/services/translation.py` — filled all five public bodies and the nine private helpers behind the frozen signatures; no signature, docstring-contract or constant value changed. `translate_message` runs D8's three phases: one short-lived `engine.connect()` for the eligible read, the target language (`get_session_configuration(...).preferred_language.value`, else `FALLBACK_TARGET_LANGUAGE`) and `get_cached_translation` — a hit returns `cached=True` there, before any model resolution or client — then `resolve_model_for_use` + `open_chat_client`, with the connection **closed before** `chat_stream` (so no lock spans the call); the probe is awaited once after the iterator finishes, and the write is one short `connection.begin()` on a fresh connection. `_read_eligible_row` selects through `settled_entries.selected_columns` (`id`, `user_id`, `kind='partner'` in one statement, R5/R11) and raises `MessageNotFoundError`; `_write_cache` re-reads the same eligible row inside the transaction, continues only while its `text` still equals the translated source (D9), and inserts with `sqlalchemy.dialects.sqlite.insert(...).on_conflict_do_nothing(index_elements=["message_id", "target_language"])`, reporting `written` from `result.rowcount == 1`. Failure mapping is only the two D5 outcomes (`LlmUnreachableError` raised `from`, and an empty `.strip()` after `strip_think`); 017's / `open_chat_client`'s errors are never caught. Logs are `logger.info("translate cached=… message=… ms=…")` plus ` written=false`, and `logger.warning("translate failed … code=translation_failed ms=…")` — ids as decimal strings, never text.

Decisions worth knowing, all non-signature:
- **`aclosing` not imported.** `_join_content`'s parameter is `AsyncIterator[ChatDelta]`, which declares no `aclose`, so `contextlib.aclosing` would not typecheck. The module uses 021 `005`'s precedent instead — a `try/finally` that asks the object for `aclose` and awaits it — which the step context allows ("an explicit `aclose()` in a `finally`"). `aclosing` is therefore absent from the imports, since an unused import fails `ruff`.
- **`messages` not imported.** The skeleton's suggested import list named it, but the D9 re-read goes through `settled_entries` like the first read, so nothing in the module needs the raw table; importing it would be F401 (and naming raw `messages` would weaken R11).
- **No `related_to` predicate.** A buried row cannot be settled — `messages` carries `CheckConstraint("related_to IS NULL OR settled_at IS NULL", name="ck_messages_buried_or_settled")` — so `settled_entries` already excludes buried rows and the extra predicate would be dead code.
- **No tenth helper.** Elapsed milliseconds are computed inline (`int((time.monotonic() - started) * 1000)`) rather than in a new private function, to add no symbol beyond the frozen set.
- Verified by an ad-hoc scratchpad run (not a repo test, no pytest): the happy path and its stored row, the hit paths including a disabled model, the session-override second row, the English fallback, all six ineligible rows, both unreachable shapes with the iterator closed, the four empty-result shapes, the reasoning/think mix, the four propagated 017/021 errors, the disconnect-before-write order (`stream-finished` then one probe), the concurrent insert (one row, the earlier text), the concurrent edit (no row, next call sends the new text), a committed write on a second connection inside `chat_stream`, and the log lines carrying no marker text. `mypy app` and `ruff check .` are clean.

### Step 003 — the translate route
- `backend/app/routers/translation.py` — filled the one stub body, `translate_partner_message`, behind the frozen signature: a module-local `async def is_disconnected() -> bool` closure over the handler's own `Request` returning `await request.is_disconnected()` (D4), then `await translate_message(get_engine(settings), generator, current_user.id, message_id, settings.llm_request_timeout_seconds, client_factory, is_disconnected)` — the generator second, `get_engine` called with the **injected** settings (process-level cache, not a dependency, so an overridden `get_settings` gets its own engine) — and `return TranslationResponse.model_validate(result, from_attributes=True)`, the repo's conversion form. Added only the two deferred F401 imports in isort position: `from app.db.engine import get_engine` and `from app.services.translation import translate_message`. `DisconnectProbe` is **not** imported: the closure is annotated `-> bool` and structurally satisfies `Callable[[], Awaitable[bool]]`, so importing the alias would be unused. The router catches nothing — `MessageNotFoundError`, 017's model errors, `secret_ref_missing` and `TranslationFailedError` all reach the one registered `DomainError` handler — holds no SQL and does not import `app.db.schema` (its only `app.db` import is the engine accessor). `get_translation_chat_client_factory`, the router object, the path, `status_code=200` and the parameter list are untouched. No other handler was converted to `async`.
- `backend/app/main.py` — **no change needed**: the skeleton's edit is already final and verified here — `from app.routers.translation import router as translation_router` in isort position after the stream-router import, `app.include_router(translation_router)` as the last `include_router` call in `create_app()` after `configuration_router`, and both docstring updates (the module's router list and `create_app`'s own list) present.

Verified by a throwaway `TestClient` run (deleted, no test file added, pytest deliberately not run): two POSTs to `/api/messages/40/translation` on a settled owner-owned partner row with a file-local fake factory answered 200 `{"message_id":"40","target_language":"Russian","text":"Привет","cached":false}` then the same text with `"cached":true`, with the fake client called exactly once in total; an unknown id answered 404 `message_not_found`; a non-numeric id answered 422; the recursive route walk found `POST /api/messages/{message_id}/translation` exactly once. `mypy app` → *Success: no issues found in 70 source files*; `ruff check .` → *All checks passed!*.

### Step 004 — the translate call and the per-row flicker state
- `frontend/src/app/translationApi.ts` — filled the one stub body, `translateMessage`, behind the frozen signature: a single `return apiPost<Translation>(`/api/messages/${encodeURIComponent(messageId)}/translation`, undefined, signal)` — `undefined` as the body is how no request body is sent, and the signal threads through to `fetch`, so a non-2xx rejects with the shared client's `ApiError` (502 `translation_failed` included) and an abort is rethrown raw. Added only the deferred `import { apiPost } from "../shared/api";`. The `Translation` type and the header comment are untouched; the id is interpolated as the string it is, never parsed or coerced.
- `frontend/src/app/translationState.ts` — filled all five stub bodies behind the frozen signatures and added the deferred imports (`runInAction` onto the existing `mobx` import, `notifyFailure`, `translateMessage`). `TranslationState`'s fields and constructor are untouched, and the module still declares no method and no getter, so the prototype carries only `constructor`. `translationView` returns `{ status: "pending" }` when the row is in `pending`, `{ status: "translated", text }` when it is in `shown` **and** `texts` holds a text, else `{ status: "original" }`. `flickTranslation` tests its four branches in order — pending → `cancelTranslation` and return; shown → `shown.delete`; `texts.has` → `shown.add` (no request, which is what keeps the total at one request across show/hide/show); otherwise a fresh `AbortController`, `pending.add`, `controllers.set`, then `await translateMessage(messageId, controller.signal)`. Every branch but the request settles **before** the first `await`, so a flick's effect on the view is visible without awaiting the promise. On success it caches the text and shows the row only while `!controller.signal.aborted`; the `catch` notifies exactly once **only** when the rejection is neither `controller.signal.aborted` nor an `AbortError` by name, so a stop and a late aborted answer write nothing and notify nothing; the promise always resolves. One module-private `abortRow(state, messageId)` backs `cancelTranslation`, `invalidateTranslation` (which additionally deletes from `texts` and `shown`) and `disposeTranslations` (which walks a copy of `controllers.keys()`); it returns early when the row has no controller, and otherwise drops the controller from the map **before** calling `abort()`, so nothing is notified anywhere on this path.
- **The controller-identity guard**: `flickTranslation`'s `finally` clears `pending` and the controller **only** when `state.controllers.get(messageId) === controller`, the controller that this call created. `abortRow` deletes the map entry (and clears `pending`) up front, so after an invalidate-or-cancel the row is immediately free for a new flick, and when the first call's `finally` finally runs it sees the second call's controller under that id and writes nothing — the second call's pending flag survives, and a late answer to the aborted request writes nothing at all. Every observable write in the module is inside `runInAction`; the `controllers` map is the non-observable field, so aborting never triggers a render.

`npm run typecheck` (both tsconfigs) → clean. `npm test` deliberately not run (the verifier owns it). No file outside the two Source files was touched.

### Step 005 — the flicker on partner entries and its owner
- `frontend/src/app/StreamRecord.tsx` — filled the two seams and nothing else. **Seam 1 `PartnerFlicker`**: one `shared/IconButton` with `IconLanguage`, its `label` derived from `translationView(translations, entry.id)` — `"translated"` → "Show original", `"pending"` → "Cancel translation", otherwise "Show translation" — feeding both tooltip and `aria-label`, with **no `aria-pressed`** (the name carries the state, D15), and `onClick` → `void flickTranslation(translations, entry.id)`. It stayed where the skeleton placed it: inside the **existing** actions `Group`, immediately after "Edit entry", so 014 D6's `data-revealed` / opacity reveal covers it; no second group, and turns and decisions still render none (the `flicker` guard is untouched). **Seam 2 `partnerBodyText`**: returns `view.text` when the view is `"translated"`, else `entry.text` — so the pending case keeps the original showing — and because it is fed to `EntryBody`'s optional `text` override, the translation renders through the **same** body renderer (partner `Blockquote` + `MessageBody variant="plain"`). The editing branch is untouched, so the in-place editor is still seeded and committed with `entry.text`, never the translation.
- `frontend/src/app/StreamRecord.tsx` — **one internal reshape, inside the skeleton's explicit latitude for non-exported symbols:** `PartnerFlicker` is wrapped in `observer`. Its label is derived from `pending` / `shown` / `texts`, and a non-`observer` child's reads are *not* tracked by the enclosing `StreamEntry` reaction, so without this the label would not change when the press itself changes the state. Its prop shape, placement and name are as frozen. `partnerBodyText` stays a plain function: it is called inside `StreamEntry`'s own render, which is already tracked.
- `frontend/src/app/StreamRecord.tsx` — **colour chosen: `teal`**, held in one named module constant `TRANSLATED_COLOR` and passed through `IconButton`'s existing `color` prop (the `MemoLevelGroup` / `NoteWallLayout` precedent: `color={active ? CONST : undefined}`). Deliberately **not** `blue` — `shared/theme.ts` sets `primaryColor: "blue"`, so blue would be indistinguishable from the unset default. Applied only while the view is `"translated"`; "Show translation" and "Cancel translation" pass `undefined`. `shared/IconButton.tsx` was **not** touched or widened. No test asserts the colour (DoD-10 is the manual check).
- `frontend/src/app/StreamRecord.tsx` — imports added only for what the filled bodies use: `IconLanguage` onto the existing `@tabler/icons-react` import, and `flickTranslation` + `translationView` onto the existing `./translationState` import. `StreamRecordProps.translations` **stays optional** — DoD-7 and 013 / 014 / 022's existing callers depend on it. No id is parsed or annotated `number`, and the added comments carry no numeric id.
- `frontend/src/app/SessionStream.tsx` — **no change needed.** The skeleton's wiring was already real and verified here, matching D13 exactly: `const [translations] = useState(() => new TranslationState());` right after the `StreamState` one, its own `useEffect(() => () => { disposeTranslations(translations); }, [translations])` placed before the load effect, `translations={translations}` on `StreamRecord`, and the `TranslationState, disposeTranslations` import. `SessionStreamProps` is unchanged, so the state is never passed in.
- **022 `007` is intact**: `StreamEntry` still ends with `{entry.kind !== "partner" ? <DiscussionGroup key={entry.id} entryId={entry.id} state={state} /> : null}` and keeps its `DiscussionGroup` import, verbatim and unmoved. 023's additions all sit in the disjoint partner branch; the reviewed diff against `HEAD` contains the skeleton's own changes plus the two seam fills and nothing else.

`npm run typecheck` (both tsconfigs, `include: ["src", "tests"]`) → clean. `npm test` deliberately not run (the verifier owns it, and this is the last step before the global run). No file outside the two Source files was touched.

## Skeleton

### Step 001 — frozen interface (2026-10-04)
- `backend/app/db/schema.py` — `translations = Table("translations", metadata, Column("id", BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=False), Column("user_id", <id type>, ForeignKey("users.id"), nullable=False), Column("message_id", <id type>, ForeignKey("messages.id"), nullable=False), Column("target_language", Text, nullable=False), Column("text", Text, nullable=False), Column("created_at", Text, nullable=False), UniqueConstraint("message_id", "target_language", name="uq_translations_message_id_target_language"))` — new (complete declaration; no `ondelete`, no index, no `updated_at`)
- `backend/app/errors.py` — `class TranslationFailedError(DomainError)`: `code = "translation_failed"`, `http_status = 502`, `def __init__(self, message_id: int, message: str | None = None) -> None` — new; `__init__` body raises `NotImplementedError` (coder: default message "The translation failed. Showing the original.", `detail={"message_id": str(message_id)}`, via `super().__init__(message, detail)`)
- `backend/app/models/translation.py` — `class TranslationResponse(BaseModel)`: `model_config = ConfigDict(from_attributes=True)`; `message_id: SnowflakeOut`, `target_language: str`, `text: str`, `cached: bool` — new (complete; imports only `pydantic` and `app.models.ids`)
- `backend/app/services/messages.py` — `edit_message_text(connection: Connection, user_id: int, message_id: int, text: str) -> StreamMessage` — unchanged signature; **file not modified** (body and docstring left intact, see Notes & Issues "Step 001 — D11 delete vs 012 guard"). Coder's change, once resolved: import `translations` from `app.db.schema`; inside the existing `with connection.begin():`, right after the `messages.update(...)` execute, delete `translations` rows where `message_id == message_id` and `user_id == user_id`; amend only the module docstring's "There is no delete…" sentence (L11).
- Caller-compile edits (out of Source-files scope): None.
- Existing tests now failing against the stubs: 26 in `tests/test_db_schema.py` (the `PRE_*`/`LATER_THAN_*` table-set ladder and `_created_table_names` checks — DoD-3's amendment, in scope). `test_messages_service.py`, `test_llm_registry_models.py`, `test_llm_registry_servers.py` and the 24 other files referencing `metadata.tables`/`sqlite_master` pass (1262 passed).

### Step 002 — frozen interface (2026-10-04)

Source file: `backend/app/services/translation.py` — **new**, the whole module. `mypy app` and `ruff check .` both clean. Every body raises `NotImplementedError("<name> — step 023/002")`; no SQL, no model call, no joining, no logging.

**Public — the test-coder binds to these, the coder may not change them:**
- `backend/app/services/translation.py` — `FALLBACK_TARGET_LANGUAGE: Final = "English"` — new (module constant; the **value is part of the freeze**, DoD-16; public name, no leading underscore)
- `backend/app/services/translation.py` — `DisconnectProbe = Callable[[], Awaitable[bool]]` — new (type alias; `True` = the client is gone. Declared here, never imported, so the module stays `fastapi`-free, D4)
- `backend/app/services/translation.py` — `@dataclass(frozen=True) class TranslationResult:` `message_id: int`, `target_language: str`, `text: str`, `cached: bool` — new (field order as written; keyword construction valid; `TranslationResponse.model_validate(result)` works through 001's `from_attributes`)
- `backend/app/services/translation.py` — `get_cached_translation(connection: Connection, user_id: int, message_id: int, target_language: str) -> str | None` — new
- `backend/app/services/translation.py` — `async def translate_message(engine: Engine, generator: SnowflakeGenerator, user_id: int, message_id: int, timeout_seconds: float, client_factory: ChatClientFactory, is_disconnected: DisconnectProbe) -> TranslationResult` — new

**Private — declared with their signatures; bodies are the coder's:**
- `@dataclass(frozen=True) class _EligibleRow:` `id: int`, `session_id: int`, `text: str`
- `_read_eligible_row(connection: Connection, user_id: int, message_id: int) -> _EligibleRow`
- `_translation_messages(target_language: str, source_text: str) -> list[ChatMessage]`
- `async def _join_content(deltas: AsyncIterator[ChatDelta]) -> str`
- `_write_cache(connection: Connection, generator: SnowflakeGenerator, user_id: int, message_id: int, target_language: str, text: str, source_text: str) -> bool` (`True` when a row landed; `False` when D9's guard refused or the unique-pair conflict swallowed the insert — that is what the caller logs as `written=false`)
- `_log_outcome(message_id: int, *, cached: bool, written: bool, elapsed_ms: int) -> None` (a cache hit passes `written=True` and gets no suffix)
- `_log_failure(message_id: int, elapsed_ms: int) -> None`
- `_now_text() -> str`
- `@contextmanager def _reading(connection: Connection) -> Iterator[None]`

**The id generator — resolved: a parameter, not a module accessor.** `app/ids.py` exposes **no** module-level accessor and no singleton: only `EPOCH_MS` / `NODE_ID_BITS` / `SEQUENCE_BITS`, `BackwardsClockError`, `class SnowflakeGenerator(node_id: int, clock: Callable[[], int] = _system_clock_ms)` with `.next_id() -> int`, and `build_id_generator(settings: Settings) -> SnowflakeGenerator`. The process's single instance lives on `app.state.id_generator` and reaches code only through `app.routers.bootstrap.get_id_generator(request) -> SnowflakeGenerator` (eight routers use it). The 021 `005` precedent is `compose_stream(engine, generator, user_id, session_id, ...)` and `begin_compose(connection, generator, ...)` — the generator sits immediately after the engine/connection. So `translate_message` takes `generator: SnowflakeGenerator` as its **second** positional parameter, after `engine`.

**Consequence for step 003:** the route must take `generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)]` (`from app.ids import SnowflakeGenerator`, `from app.routers.bootstrap import get_id_generator`) and pass it as `translate_message`'s second argument. Service tests build their own `SnowflakeGenerator(node_id=0)`.

**Upstream bindings — exact paths and signatures read from the live tree (016..022 are built):**
- `app.services.llm.chat` — `ChatRole = Literal["system", "user", "assistant", "tool"]`; `@dataclass(frozen=True) ChatMessage(role: ChatRole, content: str, tool_calls: tuple[ToolCall, ...] = (), tool_call_id: str | None = None)` (two-field construction valid, so a `system` message is `ChatMessage(role="system", content=...)`); `strip_think(text: str) -> str` (removes `<think>…</think>` left to right, an unterminated opener runs to the end, and it trims **only** when it removed a block); `THINK_OPEN` / `THINK_CLOSE`.
- `app.services.llm.client` — `@dataclass(frozen=True) ChatDelta(content: str | None = None, reasoning: str | None = None, tool_calls: tuple[ToolCallDelta, ...] = ())`; `LlmClient(base_url, api_key, timeout_seconds, *, transport=None)`; `LlmClient.chat_stream(model, messages, tools)` is an async generator.
- `app.errors` — **`LlmUnreachableError` lives here, not in `llm/client.py`** (`client.py` imports it from `app.errors`); also `MessageNotFoundError`, and 001's `TranslationFailedError(message_id: int, message: str | None = None)` with `code = "translation_failed"`, `http_status = 502`.
- `app.services.llm_registry` — `ChatClientLike` is a `Protocol` with `chat_stream(self, model: str, messages: Sequence[ChatMessage], tools: Sequence[Mapping[str, object]]) -> AsyncIterator[ChatDelta]`; `ChatClientFactory = Callable[[str, str | None, float], ChatClientLike]` (`(base_url, resolved_api_key, timeout_seconds)`); `open_chat_client(connection: Connection, enabled_model: EnabledChatModel, timeout_seconds: float, client_factory: ChatClientFactory) -> ChatClientLike` (re-reads the server, `resolve_secret` before the factory, so `secret_ref_missing` precedes any client; writes nothing); `EnabledChatModel` carries `.server` (an `LlmServer` with `.id`, `.base_url`) and `.model_name`.
- `app.services.configuration` — `get_session_configuration(connection: Connection, user_id: int, session_id: int) -> SessionConfiguration`; `.preferred_language` is a `ResolvedSetting[str]` whose `.value` is `str | None` (already trimmed / non-blank); raises `SessionNotFoundError`. `resolve_model_for_use(connection: Connection, user_id: int, session_id: int) -> EnabledChatModel` checks in order `SessionNotFoundError`, `NoModelEnabledError`, `ModelNotChosenError`, then `validate_chat_model(..., ModelRefLevel.SESSION)` which raises `ModelNotEnabledError` with `detail.level == "session"`.
- `app.db.schema` — `settled_entries = select(messages).where(messages.c.settled_at.is_not(None))`, a `Select` carrying **every** `messages` column; `messages` has its own `user_id` column, so owner scope (R5) is a predicate on the row's own column and **no join to `sessions` is needed**. `translations` exactly as step 001 froze it.

**Imports the coder must add — F401 only, not a signature change.** The stub imports only what its signatures use (`AsyncIterator`, `Awaitable`, `Callable`, `Iterator`, `contextmanager`, `dataclass`, `Final`, `Connection`, `Engine`, `SnowflakeGenerator`, `ChatMessage`, `ChatDelta`, `ChatClientFactory`), because `ruff` flags anything unused. The coder adds, keeping isort order: `datetime` / `UTC` and `time` (for `_now_text` and the elapsed milliseconds), `from loguru import logger`, `aclosing` beside `contextmanager`, `from sqlalchemy import select`, `from sqlalchemy.dialects.sqlite import insert`, `from app.db.schema import messages, settled_entries, translations`, `from app.errors import LlmUnreachableError, MessageNotFoundError, TranslationFailedError`, `from app.services.configuration import get_session_configuration, resolve_model_for_use`, `strip_think` beside `ChatMessage`, and `open_chat_client` beside `ChatClientFactory`.

**Note for the test-coder (DoD-16).** The module docstring mentions `fastapi` in prose ("imports no `fastapi`"), exactly as `services/llm_registry.py`'s docstring does. Assert the no-`fastapi` clause **AST-wise**, on the model of `tests/test_compose_source.py`'s `_compose_imports` / `test_compose_imports_no_fastapi__S021_005_DoD14`, not by substring on the source.

- Caller-compile edits (out of Source-files scope): None. New module, no callers until step 003.

### Step 003 — frozen interface (2026-10-04)

Source files: `backend/app/routers/translation.py` (**new**, the whole module) and
`backend/app/main.py` (**the real final edit**, not a stub). `mypy app` → *Success: no issues found in
70 source files*; `ruff check .` → *All checks passed!*. The handler body raises
`NotImplementedError("translate_partner_message — step 023/003")`; no SQL, no probe closure, no service
call yet.

**Public — the test-coder binds to these, the coder may not change them:**

- `backend/app/routers/translation.py` — `router = APIRouter(tags=["translation"], dependencies=[Depends(require_user)])` — new (**no prefix**; the handler carries the full literal path, as 012/017 do)
- `backend/app/routers/translation.py` — **`def get_translation_chat_client_factory() -> ChatClientFactory`** — new. **This is the name tests override.** `app.dependency_overrides[get_translation_chat_client_factory] = lambda: <fake factory>`, imported as `from app.routers.translation import get_translation_chat_client_factory`. Body is final, not a stub: `return LlmClient` (the real class, 021 `006`'s pattern, D12). Named distinctly from `app.routers.stream.get_chat_client_factory` so an override targets exactly one of them; `routers/stream.py` is untouched.
- `backend/app/routers/translation.py` — the route: **`POST /api/messages/{message_id}/translation`**, `status_code=200`, decorated `@router.post("/api/messages/{message_id}/translation", status_code=200)`.
- `backend/app/routers/translation.py` — the handler, **`async def`** (the only async handler in the backend; no other handler was converted):

  ```python
  async def translate_partner_message(
      message_id: SnowflakeIn,
      request: Request,
      current_user: Annotated[CurrentUser, Depends(require_user)],
      settings: Annotated[Settings, Depends(get_settings)],
      generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
      client_factory: Annotated[ChatClientFactory, Depends(get_translation_chat_client_factory)],
  ) -> TranslationResponse:
  ```

  Parameter order as written (it is keyword-resolved by FastAPI, so order is not load-bearing for callers). No request body. `require_user` is both router-level and a parameter, because the handler needs `.id`. `Request` is Starlette's, imported from `fastapi`.

**Bindings this freeze commits to (read from the live tree, all already present):**
`from app.config import Settings, get_settings`; `from app.dependencies import CurrentUser, require_user`;
`from app.ids import SnowflakeGenerator`; `from app.models.ids import SnowflakeIn`;
`from app.models.translation import TranslationResponse` (step 001, `from_attributes=True`);
`from app.routers.bootstrap import get_id_generator` (`(request) -> SnowflakeGenerator`, off `app.state`);
`from app.services.llm.client import LlmClient`; `from app.services.llm_registry import ChatClientFactory`
(`Callable[[str, str | None, float], ChatClientLike]`).

**What the coder fills in (behaviour, not signature).** The body must await step 002's frozen
`translate_message(get_engine(settings), generator, current_user.id, message_id,
settings.llm_request_timeout_seconds, client_factory, <probe>)` — **the generator is the second
positional argument** — and return `TranslationResponse.model_validate(result)`. `<probe>` is an async
closure over the handler's `request` returning `await request.is_disconnected()` (D4). `get_engine` is
called with the **injected** settings (process-level cache, not a dependency), so a test overriding
`get_settings` gets its own engine. The router catches nothing.

**`main.py` — the precise edit, already applied and final:**
1. one import line, in isort order immediately after `from app.routers.stream import router as stream_router`: `from app.routers.translation import router as translation_router`;
2. one call in `create_app()`, immediately after `app.include_router(configuration_router)` and last of all: `app.include_router(translation_router)`;
3. the module docstring's router list (item 5) gains a closing sentence for the translation router after the configuration-router sentence, whose tail was reworded from "registered after every other router" to "registered after every earlier router";
4. `create_app`'s own docstring list gains `app.include_router(translation_router)` and the clause "the configuration router after those (feature `017`), and the translation router last (feature `023`)".
No other line of `main.py` changed; the lifespan, the settings/logging/generator/handler order and the patchable-seam imports are untouched.

**Imports the coder must add — F401 only, not a signature change.** The stub imports only what its
signatures use, because `ruff`'s `F` rules are on. The coder adds, keeping isort order:
`from app.db.engine import get_engine` and `from app.services.translation import translate_message`
(plus `DisconnectProbe` from the same module only if the probe closure is annotated with it).

**Observed facts the sanity check confirmed (throwaway `TestClient`, deleted; no test file added):**
- The route resolves: an unauthenticated POST to `/api/messages/7250000000000000101/translation` answers **401** `not_authenticated` through the router-level guard, not 404.
- Authenticated, a non-numeric path id answers **422** `value_error` on `["path","message_id"]` before the handler runs — identical to the existing `/api/messages/{message_id}/discussion` route. Unauthenticated **and** non-numeric answers 401, because router-level dependencies are solved before path validation.
- Under the pinned **FastAPI 0.141.1 / Starlette 1.7.0**, `app.routes` does **not** flatten included routers: each `include_router` appears as a `_IncludedRouter` whose `APIRoute`s hang off `.original_router.routes`. A route-inventory assertion must recurse through `.routes` / `.router.routes` / `.original_router.routes`, as `tests/test_configuration_router.py`'s `_ordered_api_routes` and `tests/test_stream_router.py`'s `_flatten_routes` already do.

- Caller-compile edits (out of Source-files scope): None.
- Existing tests now failing because of this step: not run (pytest deliberately not run here). The one knock-on already recorded under `## Ultra phase` stands — `tests/test_configuration_router.py::test_the_configuration_router_is_included_last__S017_005_DoD9` now sees the translation router after configuration, to be amended as an approved mechanical knock-on. The ~26 reds in `tests/test_db_schema.py` are step 001's.

### Step 004 — frozen interface (2026-10-04)

Source files: `frontend/src/app/translationApi.ts` and `frontend/src/app/translationState.ts` — both **new**, the whole modules. `npm run typecheck` (both tsconfigs) → clean; `npm test` deliberately not run. Every function body is `void <each param>;` then `throw new Error("<name> — step 023/004: not implemented")`: no `fetch`, no `runInAction`, no notification, no caching, no derivation. **`TranslationState`'s fields, their initial values and its constructor body are real** — they are the declaration the tests bind to.

**`frontend/src/app/translationApi.ts` — public:**
- `export type Translation = { message_id: string; target_language: string; text: string; cached: boolean }` — new (field order as written; mirrors step 001's `TranslationResponse`; `message_id` is a decimal string, never parsed or coerced)
- `export async function translateMessage(messageId: string, signal?: AbortSignal): Promise<Translation>` — new

**`frontend/src/app/translationState.ts` — public:**
- `export type TranslationView = { status: "original" } | { status: "pending" } | { status: "translated"; text: string }` — new. **This is the view derivation's exact return shape, and the only thing step `005` reads.** A three-member union discriminated on `status` (`shared/sse.ts`'s `SseOutcome` and `app/thinking.ts`'s `ThinkingSegment` are the in-repo precedent). `text` exists **only** on the `"translated"` member, and the other two members carry no further property — so `toEqual({ status: "original" })`, `toEqual({ status: "pending" })` and `toEqual({ status: "translated", text: "Привет" })` are exact assertions, and reading `.text` requires narrowing on `status === "translated"`. No standalone status alias is exported: the union *is* the contract.
- `export class TranslationState` — new. `constructor()` takes **no parameters**; its body is final and not a stub: `makeAutoObservable(this, { controllers: false }, { autoBind: true })`. Observable fields only — no methods, no getters, so `TranslationState.prototype` has no own property besides `constructor` (DoD-11). Fields in declaration order, with their real initial values:

  | Field | Type | Initial value | Observability |
  |---|---|---|---|
  | `shown` | `Set<string>` | `new Set<string>()` | observable (auto) |
  | `texts` | `Map<string, string>` | `new Map<string, string>()` | observable (auto) |
  | `pending` | `Set<string>` | `new Set<string>()` | observable (auto) |
  | `controllers` | `Map<string, AbortController>` | `new Map<string, AbortController>()` | **non-observable — the one field annotated `false`** (D13: aborting never triggers a render) |

  Every key is a message id string. `shown` = the rows displaying their translation; `texts` = each row's text from its last success, absent meaning nothing cached; `pending` = the rows with a request in flight; `controllers` = each pending row's `AbortController`.
- `export function translationView(state: TranslationState, messageId: string): TranslationView` — new
- `export async function flickTranslation(state: TranslationState, messageId: string): Promise<void>` — new (**no signal parameter**: the effect creates the row's own controller)
- `export function cancelTranslation(state: TranslationState, messageId: string): void` — new
- `export function invalidateTranslation(state: TranslationState, messageId: string): void` — new
- `export function disposeTranslations(state: TranslationState): void` — new

**Imports the coder must add — `noUnusedLocals` only, not a signature change.** `noUnusedLocals` / `noUnusedParameters` are both on, so the stubs import only what their declarations use. `translationApi.ts` imports **nothing** today; the coder adds `import { apiPost } from "../shared/api";` and calls

  ```ts
  apiPost<Translation>(`/api/messages/${encodeURIComponent(messageId)}/translation`, undefined, signal)
  ```

  — **`undefined` as the second argument is how no request body is sent**. `translationState.ts` imports only `makeAutoObservable` from `mobx`; the coder adds `runInAction` to that same import, `import { notifyFailure } from "../shared/notifyFailure";` (expected here — `tests/conventions.test.ts` restricts only direct `@mantine/notifications` imports) and `import { translateMessage } from "./translationApi";`. The leading `void <param>;` lines exist solely to satisfy `noUnusedParameters` and are deleted as each body is filled.

**Behaviour the coder owns (the plan's, restated for orientation, not part of the freeze):** an abort is recognised as `signal?.aborted || (error instanceof Error && error.name === "AbortError")`; `flickTranslation` never rejects; every write after an `await` goes inside `runInAction`; pending and the controller are cleared only while `state.controllers.get(messageId)` is still the controller that call created; `src/app/streamState.ts` is the pattern to copy, never to import.

- Caller-compile edits (out of Source-files scope): None. Both modules are new and have no callers until step `005`.
- Existing tests now failing because of this step: none expected (two new modules, no callers); the frontend suite was not run.

### Step 005 — frozen interface (2026-10-04)

Source files: `frontend/src/app/StreamRecord.tsx` and `frontend/src/app/SessionStream.tsx` — both **existing**, changed in place. `npm run typecheck` (both tsconfigs, `include: ["src", "tests"]`) → **clean, zero test-file fallout**; `npm test` deliberately not run. Everything 013 / 014 / 022 renders still renders: the kind label, `EntryBody` by kind, the actions group with "Edit entry" (absent while editing), "Copy as plain text" on turns, 013's "Re-open last entry" on the last entry, the "Edit entry text" `Textarea` committing on blur, `commit()`'s `editEntry(state, entry.id, text, signal)` call, and 022 `007`'s `DiscussionGroup` on non-partner entries.

**Public — the test-coder binds to these, the coder may not change them:**

- `frontend/src/app/StreamRecord.tsx` — `export type StreamRecordProps = { state: StreamState; signal?: AbortSignal; translations?: TranslationState }` — changed (was `{ state: StreamState; signal?: AbortSignal }`). **`translations` is optional and that is load-bearing** (DoD-7): `undefined` → no entry renders a flicker and no edit invalidates, so every 013 / 014 / 022 caller and test is untouched. Field order as written; `TranslationState` imported `import type { TranslationState } from "./translationState"`.
- `frontend/src/app/StreamRecord.tsx` — `export const StreamRecord: (props: StreamRecordProps) => React.JSX.Element` (an `observer`) — unchanged shape; it now destructures `translations` and passes it to every `StreamEntry` verbatim.
- `frontend/src/app/SessionStream.tsx` — `export type SessionStreamProps = { sessionId: string; sendBlockedReason?: string | null }` — **unchanged**. The flicker state is created inside, never passed in.
- `frontend/src/app/SessionStream.tsx` — **the wiring is real, not a stub** (three additions, nothing else in the component changed): (1) `const [translations] = useState(() => new TranslationState());` immediately after the existing `const [state] = useState(() => new StreamState(props.sessionId));`; (2) its own `useEffect(() => { return () => { disposeTranslations(translations); }; }, [translations]);` placed before the existing load effect; (3) `<StreamRecord state={state} signal={signal} translations={translations} />`. Imports added: `import { TranslationState, disposeTranslations } from "./translationState";`.

**Internal to `StreamRecord.tsx` — the coder may reshape these freely (not exported, no test sees them):**

- `type StreamEntryProps = { state: StreamState; entry: Message; isLast: boolean; signal?: AbortSignal; translations?: TranslationState }` — changed (gained the same optional `translations`).
- `function EntryBody(props: { entry: Message; text?: string }): React.JSX.Element` — changed (gained an optional `text` override; body now renders `props.text ?? entry.text` through the same `MessageBody` variants, so behaviour with `text` omitted is identical to 013's). This is how a shown translation goes through **the same body renderer**.
- `const flicker: TranslationState | undefined = entry.kind === "partner" ? translations : undefined;` in `StreamEntry` — the one guard (partner **and** a state given) that narrows for all three touch points below. Turn and decision entries are untouched (US-131).
- **Seam 1 — unimplemented:** `function PartnerFlicker(props: { translations: TranslationState; entry: Message }): React.JSX.Element` → `throw new Error("PartnerFlicker — step 023/005: not implemented")`. Rendered as `{flicker === undefined ? null : <PartnerFlicker translations={flicker} entry={entry} />}` **inside the existing actions `Group`, immediately after the "Edit entry" button** — no second group, so 014 D6's reveal (`data-revealed`, opacity) covers it. The coder fills it with one `shared/IconButton` (`IconLanguage`, `color`, no `aria-pressed`), label from `translationView(translations, entry.id)`: `"original"` → **"Show translation"**, `"pending"` → **"Cancel translation"**, `"translated"` → **"Show original"**, `onClick` → `flickTranslation(translations, entry.id)`.
- **Seam 2 — unimplemented:** `function partnerBodyText(translations: TranslationState, entry: Message): string` → `throw new Error("partnerBodyText — step 023/005: not implemented")`. Called as `<EntryBody entry={entry} text={flicker === undefined ? undefined : partnerBodyText(flicker, entry)} />` in the non-editing branch only, so the open editor still holds `entry.text`. The coder returns the view's `text` when `translationView` is `"translated"`, else `entry.text` (the `"pending"` case included).
- **Not a seam — real:** D14's invalidation. `commit()`'s existing `.then((mayClose) => { … })` gained, after the `setEditing(false)` guard, `if (flicker !== undefined) { invalidateTranslation(flicker, entry.id); }` — unconditional on the edit's outcome, partner-only, `editEntry` and `streamState.ts` unchanged. It fails loudly today because step 004's `invalidateTranslation` is itself a throwing stub, so no extra stub was invented here.

**Imports the coder must add — `noUnusedLocals` only, not a signature change.** `StreamRecord.tsx` imports today only what its declarations use: `invalidateTranslation` and `import type { TranslationState }` from `./translationState`. The coder adds `IconLanguage` to the existing `@tabler/icons-react` import (isort-free, alphabetical as written: `IconArrowBackUp, IconCopy, IconEdit, IconLanguage`) and `flickTranslation, translationView` to the `./translationState` import. No other module is imported, and `shared/IconButton.tsx` is **not** widened.

**022 `007` was present and is preserved verbatim.** `StreamEntry` already ended with `{entry.kind !== "partner" ? <DiscussionGroup key={entry.id} entryId={entry.id} state={state} /> : null}` plus the `DiscussionGroup` import; both are untouched, and 023's additions sit in the disjoint partner branch. No textual conflict remained to resolve.

**No `aria-pressed` anywhere; no id is parsed or annotated `number`** (`tests/ids-are-strings.test.ts` scans `src/` including comments — the added code and comments carry only string ids).

- Caller-compile edits (out of Source-files scope): **None.** `StreamRecord`'s only non-test caller is `SessionStream` (a Source file); the prop is optional, so `tests/app/StreamRecord.test.tsx`, `StreamRecordActions.test.tsx`, `StreamRecordDiscussion.test.tsx` and `SessionStream.test.tsx` all still typecheck unchanged.
- Existing tests now failing against the stubs (frontend suite deliberately not run; this is the predicted fan-out, all from calls into step 004's throwing stubs): any test that renders a **partner** entry while a `TranslationState` is in play hits `PartnerFlicker` / `partnerBodyText` during render, and any test that **unmounts `SessionStream`** hits `disposeTranslations`. Since `SessionStream` now always passes a state, that means `tests/app/SessionStream.test.tsx` (all of it, via RTL's unmount in `afterEach`) and whatever in `tests/app/SessionScreen.test.tsx` / `tests/app/App.test.tsx` mounts a ready `SessionStream` — those two files render the real component (no `vi.mock`). `tests/app/StreamRecord*.test.tsx` pass no state and are expected to stay green. All of it goes green once steps 004 and 005 are filled in; nothing here needs a test amendment beyond the button-count cases `005.context.md` already permits.

## Tests

### Step 001 — tests (2026-10-04)

New files:

- `backend/tests/test_translation_schema.py` — covers **DoD-1, DoD-2, DoD-4, DoD-5**.
  - DoD-1 (8 tests): `translations` registered on the one `metadata`; exactly the six columns
    `id, user_id, message_id, target_language, text, created_at` (no `updated_at`, no state
    column); `id` the sole PK; every column NOT NULL (parametrised); exactly the two FKs
    `user_id → users.id` and `message_id → messages.id`; `message_id`'s FK declares **no
    `ON DELETE`** action (metadata, and `PRAGMA foreign_key_list` on the created table); a
    unique constraint **named** `uq_translations_message_id_target_language` over
    `(message_id, target_language)` in that order; and an `inspect(engine)` pass over the
    `create_all` database re-checking columns / NOT NULL / FK targets / the unique pair.
  - DoD-2 (3 tests): a duplicate `(message_id, target_language)` raises `IntegrityError`; two
    languages for one message are accepted; one language for two messages is accepted.
  - DoD-4 (5 tests): `DomainError` subclass; class-level `code = "translation_failed"` and
    `http_status = 502`; `detail == {"message_id": "7250000000000000101"}` with the value a
    **string**; the fixed default message `"The translation failed. Showing the original."`
    (001.context.md); a given message replaces it and leaves `detail` alone.
  - DoD-5 (2 tests): `TranslationResponse.model_validate(<object>)` serialises to **exactly**
    `{"message_id":"7250000000000000101","target_language":"Russian","text":"Привет","cached":true}`,
    and the `cached: false` counterpart (Wire contract).
- `backend/tests/test_translation_invalidation.py` — covers **DoD-6, DoD-7, DoD-8, DoD-9**,
  against `edit_message_text` directly, with raw-inserted users (two, for isolation),
  characters, sessions, `messages` (two settled partner rows, a settled turn, a row buried
  under it, a zone row, plus another user's settled partner row) and raw-inserted
  `translations` rows.
  - DoD-6 (3 tests): both cached rows (two languages) of the edited partner row are gone; a
    `translations` row of a **different** message is untouched contents and all; no cached
    pair remains for the edited id (US-111.AC-2's premise).
  - DoD-7 (2 tests): a buried row raises `message_not_editable` and a foreign row raises
    `message_not_found` (R5), each keeping its raw-inserted `translations` row and its stored
    text.
  - DoD-8 (1 test): a `BEFORE DELETE ... RAISE(ABORT, …)` trigger on `translations` (the
    006/003 `s006_003_block_server_delete` idiom) makes the edit raise `DBAPIError`, after
    which the message row is byte-for-byte unchanged **and** the cached row is still present
    — the proof the delete rides inside the edit's transaction.
  - DoD-9 (3 tests): a settled turn and a zone row (no cached rows) still edit and return as
    before — id, `session_id`, `role`, `kind`, `settled_at`, `created_at`, new text, and
    `updated_at` not moving backward — and a never-translated partner row edits the same way.

Amended files — **table-set pins only, no other assertion changed** (DoD-3):

- `backend/tests/test_db_schema.py` — repairs the 26 reds the skeleton's new table caused.
  Following the file's own ladder idiom (the rule stated in its 009/001 DoD-11 comment),
  `"translations"` was **added** to `LATER_THAN_006_TABLES`, `LATER_THAN_009_TABLES`,
  `LATER_THAN_010_TABLES`, `LATER_THAN_011_TABLES`, `LATER_THAN_012_TABLES` and
  `LATER_THAN_015_TABLES`, so every earlier `set(metadata.tables) - PRE - LATER == NEW`
  delta and every `_created_table_names` check still means what it meant. No earlier
  assertion was rewritten. 023 then gets its own delta in the same shape, in a new
  feature-023 section at the end of the file: `PRE_023_TABLES`, `NEW_023_TABLES =
  {"translations"}`, `LATER_THAN_023_TABLES = set()`, plus **11 tests** suffixed
  `__S023_001_DoD3` (023's delta; every pre-023 table still registered; the delta survives a
  future table; `create_all` creates it; the 006 / 009 / 010 / 011 / 012 / 015 deltas still
  hold; every earlier later-features set now names `translations`). The table's columns, FKs
  and named unique constraint are **not** duplicated here — they live in
  `test_translation_schema.py`.
- `backend/tests/test_llm_registry_models.py` (`test_set_enabled_models_touches_only_the_two_registry_tables__S006_004_DoD6`)
  and `backend/tests/test_llm_registry_servers.py` (`test_delete_touches_only_the_two_registry_tables__S006_003_DoD10`)
  — neither pins the full table set (both compute `set(metadata.tables) - {llm_servers,
  models}` dynamically, so `translations` was already covered); `"translations"` was added to
  the explicit belt-and-braces literal `{"sessions", "characters", "memos"}` in each, one
  line plus a comment. Nothing else touched. `test_listing_reads_only_the_two_registry_tables__S006_003_DoD4`
  needs no change (it asserts `tables_touched() <= {...}`).

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓.
No `[manual/live]` item in this step.

#### Approved deviation — the 012 "no delete path" guard, narrowed

`backend/tests/test_messages_service.py` is **not** in step 001's Test files, so this is an
approved deviation under the 2026-10-03 mechanical-knock-on policy, implementing the user's
decision of **2026-10-04** recorded in `## Ultra phase` and raised by the skeleton in
`## Notes & Issues` ("Step 001 — D11 delete vs 012 guard"):

> Narrow the guard so the **only permitted delete** in `services/messages.py` **targets
> `translations`**; there must still be **no delete on `messages`** and **no raw `DELETE`
> SQL keyword**.

What changed in that file, and nothing else:

- `test_the_module_has_no_delete_path__S012_002_DoD13` keeps its **name and DoD suffix**. Its
  body no longer greps `\bdelete\s*\(` (case-insensitive) over the source. It now parses the
  module (`_module_tree()`, the file's existing helper) and, for **every** `delete(...)` /
  `<x>.delete(...)` call, asserts the call's operands (its arguments plus a `<table>.delete()`
  receiver) **name `translations`** and **do not name `messages`** — reusing the file's
  existing `_names_the_messages_table`. `\bDELETE\b` (the raw SQL keyword) stays forbidden.
- The check is **AST-based on purpose**: the original guard existed to stop a `messages`
  delete path (012 D16), and a regex could be evaded by an alias. For the same reason the
  test also refuses any import that rebinds `delete` under another name
  (`from sqlalchemy import delete as _drop`).
- Added above it: the constant `_PERMITTED_DELETE_TABLE = "translations"` (with the decision
  cited in its comment) and the helpers `_names_table`, `_is_delete_call`,
  `_delete_operands`, `_delete_aliases`. The now-unused `_DELETE_CALL` regex was removed;
  `_DELETE_SQL_KEYWORD` is kept and still asserted. No other test, helper or assertion in
  the file was touched.

This keeps D11 shipping as planned: 023's one delete in `services/messages.py` is permitted,
and a `messages` delete path still fails the suite.

### Step 002 — tests (2026-10-04)

New file:

- `backend/tests/test_translation_service.py` — covers **DoD-1 … DoD-18** (every `[test]` item;
  the step has no `[manual/live]` item). Bound to `## Skeleton` → Step 002: `translate_message(
  engine, generator, user_id, message_id, timeout_seconds, client_factory, is_disconnected)`
  (the generator second, a file-local `SnowflakeGenerator(node_id=0)`), `get_cached_translation`,
  `TranslationResult`, `FALLBACK_TARGET_LANGUAGE`, and `LlmUnreachableError` from `app.errors`.
  File-local seeding (`_insert_user/_character/_session/_message/_translation/_server/_model`,
  two users, SERVER_A with three models), a file-local fake chat client + factory, and
  `asyncio.run(asyncio.wait_for(...))`. `conftest.py` untouched.

  | DoD | Tests |
  |---|---|
  | DoD-1 | `…translates_caches_and_reports_the_target_language`, `…stored_row_is_readable_only_by_its_owner`, `…model_is_called_with_the_captured_name_and_no_tools`, `…exactly_two_messages_a_system_then_the_row_text`, `…factory_receives_the_servers_base_url_and_the_given_timeout` |
  | DoD-2 | `…a_second_call_answers_from_the_cache` (factory and client untouched) |
  | DoD-3 | `…a_cache_hit_needs_no_enabled_model` (parametrised: session model disabled / every model disabled) |
  | DoD-4 | `…session_override_beats_the_users_language_and_caches_separately` (both rows remain) |
  | DoD-5 | `…no_preferred_language_falls_back_to_english`, `…fallback_translation_is_cached_under_english` |
  | DoD-6 | `…an_ineligible_row_is_indistinguishable_from_a_missing_one` (6 cases: foreign, zone, buried, turn, decision, unknown — factory never called, no row) |
  | DoD-7 | `…an_unreachable_provider_fails_with_translation_failed` (before any delta / mid-stream; `code`, `detail`, no row, iterator closed) |
  | DoD-8 | `…a_call_after_a_failure_tries_the_model_again` |
  | DoD-9 | `…an_empty_result_fails_and_caches_nothing` (4 cases: nothing, reasoning only, `"   \n"`, bare `<think>`) |
  | DoD-10 | `…reasoning_is_ignored_and_a_think_block_is_stripped` |
  | DoD-11 | `…the_upstream_refusals_propagate_unchanged` (4 cases), `…disabled_captured_model_names_the_session_level`, `…unset_key_variable_refuses_with_secret_ref_missing` |
  | DoD-12 | `…disconnect_before_the_write_skips_the_row_but_returns_the_text`, `…probe_is_awaited_once_after_the_stream_finished` (one shared ordered list), `…probe_reporting_no_disconnect_lets_the_row_land` |
  | DoD-13 | `…a_row_inserted_during_the_call_is_kept_and_nothing_raises` (one row, the "Earlier" one) |
  | DoD-14 | `…an_edit_during_the_call_writes_no_row`, `…next_call_after_an_edit_sends_the_new_text` |
  | DoD-15 | `…a_cached_translation_does_not_change_the_assembled_context` (`assemble_context` equal before/after; text in neither) |
  | DoD-16 | `…translation_service_imports_no_fastapi` (**AST-based**, per the skeleton's note), `…no_context_feeding_module_imports_the_translation_service`, `…no_context_feeding_module_names_the_translations_table`, `…fallback_target_language_is_english` |
  | DoD-17 | `…miss_logs_cached_false_with_the_id_and_a_duration`, `…hit_logs_cached_true_with_the_id`, `…failure_logs_its_code_with_the_id_and_a_duration`, `…no_log_record_carries_the_source_or_translated_text` (3 paths, marker strings, loguru sink added and removed) |
  | DoD-18 | `…another_writer_can_commit_during_the_model_call` (separate connection, unrelated table) |

Notes bearing on the red gate:

- The fake's `chat_stream` returns a small async-iterator **object** with an explicit `aclose()`
  rather than a bare async generator, so DoD-7's "the iterator was closed" is observable on the
  path where the stream raised (a generator's `GeneratorExit` never fires there). Both are
  recorded, so either closing idiom from `002.context.md` satisfies it.
- DoD-6's buried row is seeded exactly as step 001 seeded it (`kind=None`, `related_to` set,
  `settled_at=None`), so it is ineligible on every reading of "visible through
  `settled_entries`".
- The log-shape assertions are only those the DoD and `002.context.md` "Logging" state; the
  optional ` written=false` suffix is deliberately **not** asserted anywhere.

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓, DoD-17 ✓, DoD-18 ✓.
No `[manual/live]` item in this step.

### Step 003 — tests (2026-10-04)

New file:

- `backend/tests/test_translation_router.py` — covers **DoD-1 … DoD-6**. Bound to `## Skeleton` →
  Step 003: `POST /api/messages/{message_id}/translation` (`status_code=200`, `async def`
  `translate_partner_message`) and **`get_translation_chat_client_factory`** — the one dependency
  the tests override, imported `from app.routers.translation import
  get_translation_chat_client_factory`. The application is the real `create_app()`, pinned to a
  per-test SQLite file through `dependency_overrides[get_settings]`; callers log in through the
  real login route with a file-local `_as(...)`, modelled on `tests/test_stream_router.py`.
  File-local seeding (`_insert_user/_character/_session/_message/_server/_model`, two users for
  isolation, SERVER_A with the captured model plus one spare, USER_A's settled partner row, a
  settled turn, a zone row, and USER_B's settled partner row; USER_A's preferred language
  "Russian"), plus a file-local fake chat client and factory (`FakeFactory.yields/raises`, keeping
  every client it handed out so "called once in total" is observable across two requests).
  `conftest.py` untouched.

  The `application` fixture overrides **only** `get_settings`; a separate `factory` fixture
  installs the fake over the router's factory dependency. DoD-5 therefore simply does not request
  `factory`.

  | DoD | Tests |
  |---|---|
  | DoD-1 | `…a_flick_answers_200_with_the_translation` (the body **exactly**, `message_id` a string), `…a_second_flick_answers_cached_without_a_second_model_call` (`cached: true`, same text, one chat call in total, one cached row) |
  | DoD-2 | `…an_unreachable_provider_answers_502_translation_failed` (`{"error":{"code","message","detail"}}`, `code == "translation_failed"`, **non-empty** message asserted without pinning the prose, `detail == {"message_id": "<id>"}`, no cached row), `…a_flick_after_a_failure_reaches_the_model_again` (200 `cached: false` with fresh text) |
  | DoD-3 | `…an_ineligible_row_answers_404_message_not_found` (parametrised: another user's partner row, a settled turn, a zone row, an unknown id — 404 `message_not_found`, the factory never called), `…a_non_numeric_path_id_answers_422`, `…no_cookie_answers_401_not_authenticated` |
  | DoD-4 | `…no_enabled_model_answers_409_no_model_enabled`, `…a_disabled_captured_model_answers_409_model_not_enabled` |
  | DoD-5 | `…the_unoverridden_factory_reaches_the_real_client` — overrides **only** `get_settings` (`db_settings.model_copy(update={"llm_request_timeout_seconds": 0.5})`, the `test_admin_llm_router.py` idiom), points SERVER_A's `base_url` at `http://127.0.0.1:9`, expects 502 `translation_failed` with its `detail` and no cached row |
  | DoD-6 | `…the_translate_route_is_mounted_exactly_once_as_post` — a **recursive** route inventory (`_ordered_api_routes`, the `tests/test_configuration_router.py` idiom descending into `.routes` / `.router.routes` / `.original_router.routes`), path present exactly once, methods `{"POST"}` |

Notes bearing on the red gate:

- The disconnected probe path is **not** tested here: `003.context.md` "The probe" records that
  under `TestClient` `request.is_disconnected()` reports `False`, and step 002 DoD-12 covers the
  disconnected branch at the service level.
- No assertion pins the failure prose, the log shape, or any detail of the system/user messages —
  those belong to step 002's suite.

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓,
DoD-7 **[manual/live, no test]** — requires a live run (browser cancel mid-call; the log line).

#### Approved deviation — 017's "configuration router included last", amended

`backend/tests/test_configuration_router.py` is **not** in step 003's Test files, so this is an
approved deviation under the 2026-10-03 mechanical-knock-on policy recorded in `## Ultra phase`
("mechanical knock-on test amendments outside a step's Test files are approved deviations,
recorded under that step's `## Tests`"), implementing the resolution recorded at orient:

> amend it so configuration precedes only later-feature routers (translation) and follows every
> earlier one.

Cause: step 003's D12 (and its `## Skeleton` record) registers the translation router in
`main.py` **after** `configuration_router`, so "last of all" became "last before later features".

What changed in that file, and nothing else:

- `test_the_configuration_router_is_included_last__S017_005_DoD9` keeps its **name and its
  `__S017_005_DoD9` suffix** — it is still 017 D13's clause. It still walks the app with the
  file's existing recursive `_ordered_api_routes` helper (no second traversal), still asserts the
  seven configuration routes are all present, and still asserts that **no route of any router
  that pre-dates it follows it** — the half 017 actually cared about. The routes now permitted
  after it are exactly the later-feature ones.
- Added directly above it: the constant `LATER_FEATURE_ROUTES = {("/api/messages/{message_id}/translation",
  "POST")}` (the 023 route, from `## Skeleton` → Step 003), with the knock-on named in its comment.
  The old blanket `all(is_configuration[first_configuration:])` became "configuration **or** a
  later-feature route", plus `not any(is_later_feature[:first_configuration])` (no later-feature
  route sneaks in ahead) and `first_configuration > 0` (earlier routers still precede it, in place
  of the former `not all(is_configuration)`).
- Not weakened to a tautology and not deleted: a regression that moved the configuration router
  ahead of, say, the stream or messages router still fails this test.
- No other test, helper, fixture or constant in the file was touched.

### Step 004 — tests (2026-10-04)

New files, bound to `## Skeleton` → Step 004: `translateMessage(messageId, signal?)`,
`Translation`, `TranslationState` (fields `shown` / `texts` / `pending` / non-observable
`controllers`), `translationView(state, messageId)` → the three-member `TranslationView`
union, and `flickTranslation` / `cancelTranslation` / `invalidateTranslation` /
`disposeTranslations` (state first). Pure state tests: no rendering, no `AppProviders`.
Vitest symbols imported explicitly (`globals: false`). Expected values come from the step
file's DoD and Interface intent, `context.md` D4 / D13 / D14 and the Wire contract.

- `frontend/tests/app/translationApi.test.ts` — covers **DoD-1** (6 tests): exactly one
  `POST /api/messages/7250000000000000101/translation` (keyed on exact pathname and method,
  empty query); the given `AbortSignal` is the one handed to `fetch`; **no request body**
  (Wire contract); resolves to the stubbed `Translation` exactly, with `message_id` the
  identical **string**; a `cached: true` answer comes through unchanged; a **502**
  `translation_failed` envelope rejects with an `ApiError` whose `code` is
  `translation_failed` (code only, never the prose).
- `frontend/tests/app/translationState.test.ts` — covers **DoD-2 … DoD-11** (20 tests).
  File-local harness: a `vi.stubGlobal("fetch", …)` stub with **one deferred promise per
  call**, keyed on `"METHOD pathname"`, each call exposing `respond(body, status)` /
  `rejectWith(reason)` and its `signal`; by default a call rejects with a `DOMException`
  named `"AbortError"` the moment its signal aborts. `notifyFailure` is observed through
  `vi.hoisted` + `vi.mock("../../src/shared/notifyFailure")`, asserted by `ApiError.code`
  only. Ids are the strings `"7250000000000000101"` / `"7250000000000000102"`.

  | DoD | Tests |
  |---|---|
  | DoD-2 | `…is on the original before any flick`, `…exactly one POST to that row's path and the view is pending while it is unresolved`, `…shows the answered text once the request resolves` ("Привет"), `…the effect resolves and notifies nothing on success` |
  | DoD-3 | `…flicking the translated row again shows the original and makes no request` (`fetch` still once) |
  | DoD-4 | `…a third flick shows the cached translation immediately, without awaiting, with fetch still called once in total` (the view is asserted **before** awaiting the returned promise) |
  | DoD-5 | `…leaves the view on the original, notifies exactly once with that code, and resolves`, `…caches nothing, so the next flick makes a new POST` (then the new answer shows) |
  | DoD-6 | `…leaves the view on the original, notifies exactly once, and resolves` (fetch rejects with a `TypeError`; the notified argument's **type is not pinned**, only the one call), `…caches nothing, so the next flick makes a new POST` |
  | DoD-7 | `…flicking a pending row aborts its signal, returns the view to the original, notifies nothing and issues no second request`, `…cancelTranslation on a pending row aborts its signal, returns the view to the original and notifies nothing`, `…after a cancel the next flick makes a new POST, whose answer is shown`, `…cancelTranslation on a row with nothing in flight changes nothing and notifies nothing` |
  | DoD-8 | `…on a translated row shows the original, and the next flick POSTs again and shows the new answer`, `…on a pending row aborts the request, leaves the original showing and notifies nothing`, `…a response arriving after an invalidation writes nothing: the view stays original and nothing is cached` |
  | DoD-9 | `…with A pending and B translated, flicking B shows its original and cancelling A leaves B's cached text intact, each on its own path` |
  | DoD-10 | `…aborts both pending rows' signals and notifies neither`, `…with nothing pending it notifies nothing and issues no request` |
  | DoD-11 | `…its prototype has no own property besides constructor (no methods, no getters)` — `Object.getOwnPropertyNames(TranslationState.prototype)` is exactly `["constructor"]`; **string-named keys only**, symbols deliberately not checked (see the red-gate repair below) |

Notes bearing on the red gate:

- Every view assertion is an **exact** `toEqual` against one member of the frozen
  `TranslationView` union (`{ status: "original" }`, `{ status: "pending" }`,
  `{ status: "translated", text: … }`), never a property read, so the discriminated shape is
  itself pinned.
- DoD-8's "a late answer writes nothing" test uses the harness's `rejectOnAbort: false`
  mode: the deferred stays open past the abort and is then **resolved with a success body**,
  so the controller-identity / `signal?.aborted` guard is what has to bite. That is the only
  test that departs from the platform's abort behaviour, deliberately.
- The abort assertions read `call.signal?.aborted`, which presumes the effect passes a
  signal — the step file's Interface intent ("marks the row pending with a fresh controller,
  then calls `translateMessage` with its signal").
- `npm run typecheck` and `npm test` were **not run**: no execution tool was available to
  this agent (and running tests is the verifier's). Both files are TypeScript only and import
  every Vitest symbol explicitly.

Red-gate repair (2026-10-04, DoD-11 only): the DoD-11 test originally carried a second
assertion, `Reflect.ownKeys(TranslationState.prototype).filter((k) => k !== "constructor")`
equals `[]`. That was **unsatisfiable with or without the implementation**: `Reflect.ownKeys`
returns symbol keys, and MobX puts a `Symbol(mobx-keys)` bookkeeping key on the prototype of
any class whose instances have been built with `makeAutoObservable` — earlier tests in the
file construct instances, so the symbol is present by the time DoD-11 runs, and a *correct*
implementation keeps it there. The assertion therefore failed on a MobX internal, not on the
clause. Settled form: the `Reflect.ownKeys` assertion is **dropped**, leaving the single
`Object.getOwnPropertyNames(...)` `toEqual(["constructor"])` check plus a comment recording
why symbols are out of scope. The guard is undiminished — a method or a getter on
`TranslationState` is a string-named prototype property and still fails. Test name and its
`— DoD-11` suffix unchanged; no other test in the file was touched, and no other assertion in
it is `Reflect.ownKeys`- or symbol-sensitive.

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
DoD-10 ✓, DoD-11 ✓. No `[manual/live]` item in this step.

### Step 005 — tests (2026-10-04)

New files, bound to `## Skeleton` → Step 005 (`StreamRecordProps.translations?: TranslationState`,
optional and load-bearing; `SessionStreamProps` unchanged; `SessionStream` creating one
`TranslationState` per mount and disposing it on unmount) and to Step 004's
`TranslationView` / effects. Expected values come from the step file's DoD and Interface
intent, `context.md` D4 / D13 / D14 / D15 and the "Wire contract", and `005.context.md`'s
**UI strings** table — "Show translation" (original), "Cancel translation" (pending),
"Show original" (translated), one `IconButton` label feeding tooltip and `aria-label`. The
**colour is never asserted**, and the failure **prose is never asserted** (only the
`ApiError.code`). Rendered components sit inside `<AppProviders>`; `fetch` is stubbed per
test with `vi.stubGlobal`, keyed on exact method + pathname, with one deferred promise per
call so "while unresolved" and "aborted on unmount" are observable; `notifyFailure` is
observed through `vi.mock`. Every `it` title ends `— DoD-N`.

- `frontend/tests/app/StreamRecordTranslation.test.tsx` — covers **DoD-1 … DoD-7** and
  **DoD-9** (22 tests). Renders `StreamRecord` with a `StreamState` (entries set directly:
  partner "They wave.", turn "I wave back.", decision "((skip))") and a `TranslationState`;
  controls are found by accessible name **inside the partner entry's `listitem`** (`within`);
  `PATCH /api/messages/<id>` answers the edited settled partner row.

  | DoD | Tests |
  |---|---|
  | DoD-1 | `…the partner entry offers "Show translation" and the turn and decision entries offer none` (exactly one in the whole record; on the other two neither `queryByRole` nor `queryByLabelText` finds any of the three labels, so absent not disabled), `…a fresh partner entry starts on the original` |
  | DoD-2 | `…issues exactly one POST to that row's translation path`, `…while unresolved the control reads "Cancel translation" and the body still shows the original`, `…once it answers the body shows the translation, the original is gone and the control reads "Show original"` (POST still once; nothing notified), `…the other entries are untouched` |
  | DoD-3 | `…"Show original" shows the stored text again with no request`, `…flicking again shows the cached translation, with one POST in total` |
  | DoD-4 | `…a 502 translation_failed keeps the original and the control reads "Show translation"`, `…the failure is notified once, with an ApiError of code translation_failed`, `…pressing it again after the failure issues a second POST` |
  | DoD-5 | `…"Cancel translation" aborts the request's signal and leaves the original showing` (control back to "Show translation"), `…cancelling notifies nothing and issues no second request` |
  | DoD-6 | `…"Edit entry" opens the editor holding the original` ("They wave." while the translation is showing), `…typing the new text and blurring issues the PATCH for that row` (body `{"text":"They bow."}`), `…after the edit the entry shows the edited text, not the translation, and the control reads "Show translation"`, `…the next flick after the edit issues a new POST, whose answer is shown` |
  | DoD-7 | `…a partner entry rendered with no translation state shows no flicker control` (none of the three labels anywhere), `…"Edit entry" stays available on that partner entry` (and still opens the editor) |
  | DoD-9 | `…the partner entry keeps its Partner heading, its blockquote body and Edit entry, and offers no Copy`, `…the turn and decision entries keep their own controls and bodies`, `…the flicker sits in the partner entry's one actions group, revealed with the others` (exactly one `[data-revealed]` element in the item, which contains both the flicker and Edit; reveal still flips on `mouseEnter`), `…no flicker state carries aria-pressed` (all three states, D15) |

- `frontend/tests/app/SessionStreamTranslation.test.tsx` — covers **DoD-8** (3 tests). Mounts
  `SessionStream` with the stubs its mount needs (`GET …/entries`, `GET …/zone`), the
  translate POST left **deferred**: `…a partner row served by GET …/entries shows the flicker,
  and a turn row does not`; `…pressing it from the mounted stream POSTs that row's translation
  path, which shows once answered`; `…unmounting while a translation POST is pending aborts
  that request's signal, and nothing is notified` (the deferred call's `signal.aborted` is
  `false` before the unmount and `true` after it; `notifyFailure` never called).

Delivered files — **the conditional amendments were not needed**:

- `frontend/tests/app/StreamRecordActions.test.tsx` (014) — **untouched**. It renders
  `StreamRecord` with no translation state, so no flicker appears; its per-item counts are of
  "Edit entry" / "Copy as plain text" by name, never of *all* buttons in an item, so nothing
  breaks. Needed no change because the prop is optional.
- `frontend/tests/app/StreamRecord.test.tsx` (013 / 014) — **untouched**, same reason: no
  translation state is passed, and its only count assertions are of `listitem`s and of
  name-scoped controls (`/copy/i`, "Re-open last entry").
- `frontend/tests/app/SessionStream.test.tsx` (013) — **untouched**. `SessionStream` does now
  pass a state, so its partner rows gain one button, but the file counts `listitem`s,
  separators, loaders and request lines only; it pins no button count and no full
  accessible-name list of a partner entry, so there is nothing to amend. (Its reds against the
  stubs are the freeze's predicted fan-out through step 004's throwing `disposeTranslations`,
  not an assertion fault — see `## Skeleton` → Step 005.)

Notes bearing on the red gate:

- The predicted reds outside this step's new files — all of `SessionStream.test.tsx` plus any
  ready-`SessionStream` mount in `SessionScreen.test.tsx` / `App.test.tsx` — come from step
  004's throwing stubs and need **no** test amendment; they go green when steps 004 and 005 are
  filled in.
- Abort assertions read the stubbed call's `signal?.aborted`, which presumes the effect passes
  its controller's signal (step 004's Interface intent and `## Skeleton` → Step 004).
- `npm run typecheck` and `npm test` were **not run**: no execution tool was available to this
  agent (and running tests is the verifier's). Both new files are TypeScript only and import
  every Vitest symbol explicitly (`globals: false`).

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
DoD-10 **[manual/live, no test]** — requires a live run (hover/focus reveal, the visible colour
difference, a real model's translation, a mid-call cancel, a ~5 s failure notice).

## Notes & Issues

_populated by the coder when worth saying_

### Step 001 — D11 delete vs 012 guard (skeleton, 2026-10-04)
- **Step:** 001 (`001.table-error-model-invalidation.md`).
- **What intent asked for:** "`edit_message_text`: after its `messages` update, inside the same transaction, it deletes every `translations` row whose `message_id` is the edited id" (D11), plus amending the module docstring's "no delete" statement.
- **What conflicts:** `backend/tests/test_messages_service.py::test_the_module_has_no_delete_path__S012_002_DoD13` (L1051) asserts `inspect.getsource(app.services.messages)` matches neither `\bdelete\s*\(` (case-insensitive) nor `\bDELETE\b`. Any idiomatic form — `translations.delete()`, `sqlalchemy.delete(translations)`, `text("DELETE …")` — trips it. That file is not in step 001's Test files, and the plan never mentions the guard. The other guards are fine: the delete names no `messages` select (L1034), needs no `app.services` import (L1059), and assigns no `related_to` (L1090). Only an evasion such as `from sqlalchemy import delete as _drop` would pass the regex, and that defeats the guard's intent (012 D16 "no delete path"), so the skeleton did not write it.
- **Suggested resolutions:** (a) Treat it as a mechanical knock-on under the 2026-10-03 policy: the test-coder narrows the 012 guard so the only permitted delete is on the `translations` table (for example, an AST check that every `.delete()` / `delete(...)` targets `translations`, and still no `DELETE` SQL keyword or delete on `messages`), recorded under step 001's `## Tests`. This keeps D11 as planned, and the plan's own docstring amendment already implies the invariant changes. (b) Move the delete into a non-`app.services` helper module that `messages.py` calls inside its transaction (for example, in `app/db/`). That keeps 012's guard verbatim, but it adds a Source file and departs from D11's wording and R8's "one exception" location. (c) Re-plan D11 (planner/user).

## Ultra phase

- orient: done 2026-10-04
- policy 2026-10-03 (user): mechanical knock-on test amendments outside a step's Test files are approved deviations, recorded under that step's ## Tests.
- knock-on noted at orient: 023 003 appends the translation router after every router (plan), which breaks 017 tests/test_configuration_router.py::test_the_configuration_router_is_included_last__S017_005_DoD9. Treated as a mechanical knock-on under the policy: amend it so configuration precedes only later-feature routers (translation) and follows every earlier one.
- harvest: done — docs/.cache/ultra/023.partner-translation/harvest.md (1 report)
- D11 conflict resolved (user, 2026-10-04): **narrow 012's guard**. The test-coder reshapes
  `test_the_module_has_no_delete_path__S012_002_DoD13` so the only permitted delete in
  `services/messages.py` targets `translations`; no delete on `messages`, no raw `DELETE`
  keyword. Recorded as an approved deviation under step 001's `## Tests`. D11 ships as planned.
- skeleton: done — steps 001, 002, 003, 004, 005
- tests: done — steps 001, 002, 003, 004, 005 (approved deviations: 012's no-delete guard narrowed to permit only a `translations` delete; 017's router-last assertion narrowed to "last before later features")
- red-gate: PASS (run 2) — run 1 FAIL: 004 TEST (DoD-11 asserted `Reflect.ownKeys`, unsatisfiable because MobX puts `Symbol(mobx-keys)` on the prototype); assertion narrowed to string-named keys
- code: done — steps 001, 002, 003, 004, 005 (no re-freeze, no escape valve)
- verify: PASS (run 1) — 7630 tests, 0 failures (backend 3646, frontend 3984); 2 `[manual/live]` outstanding (003 DoD-7, 005 DoD-10)
