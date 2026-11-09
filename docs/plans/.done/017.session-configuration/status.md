# Feature 017 — session-configuration

| Step | File                                     | Status  | Verifier | Date |
|------|------------------------------------------|---------|----------|------|
| 001  | `001.columns-errors-models.md` | done    | PASS     | 2026-10-03 |
| 002  | `002.registry-reads-and-capture.md` | done    | PASS     | 2026-10-03 |
| 003  | `003.resolver-and-use-time-check.md` | done    | PASS     | 2026-10-03 |
| 004  | `004.configuration-writes.md` | done    | PASS     | 2026-10-03 |
| 005  | `005.configuration-router.md` | done    | PASS     | 2026-10-03 |
| 006  | `006.configuration-api.md` | done    | PASS     | 2026-10-03 |
| 007  | `007.settings-screen.md` | done    | PASS     | 2026-10-03 |
| 008  | `008.session-config-state.md` | done    | PASS     | 2026-10-03 |
| 009  | `009.session-config-draft.md` | done    | PASS     | 2026-10-03 |
| 010  | `010.session-config-modal.md` | done    | PASS     | 2026-10-03 |
| 011  | `011.header-bar-and-send-gate.md` | done    | PASS     | 2026-10-03 |

## Files Changed

### Step 001 — Configuration columns, the two use-time errors, and the wire models
- `backend/app/db/schema.py` — `characters` / `sessions` configuration columns and both-or-neither CHECKs (written in full by the skeleton; no coder change)
- `backend/app/errors.py` — `NoModelEnabledError`, `ModelNotChosenError` (written in full by the skeleton; no coder change)
- `backend/app/models/configuration.py` — filled the language / system-prompt normalisers, the non-blank `model_name` rule and the session request's explicit-null `model` rejection

### Step 002 — Enabled-model reads, and capturing the model at session creation
- `backend/app/services/llm_registry.py` — filled `list_enabled_chat_models` (inner join on `llm_servers`, `is_enabled`, ordered server id then `models.id`, under the existing transaction-neutral `_reading`) and `first_enabled_chat_model`; `validate_chat_model` unchanged (its `_reading` guard already meets D12)
- `backend/app/services/sessions.py` — `start_session` captures the model by D1 after the checks; `_require_parent_character` now also selects and returns the character's model pair; module docstring states D1 and points configuration writes at `services/configuration.py`

### Step 003 — The two resolvers, the session configuration read, and the use-time model check
- `backend/app/services/configuration.py` — filled `resolve_assistant_chain` / `resolve_language_chain` (private `_resolve_text` / `_resolve_tool` apply the Wire contract level rules; model passed through), `get_session_configuration` (one owner-scoped inner-join select, character model columns not selected) and `resolve_model_for_use` (D2 order via `first_enabled_chat_model`, then `validate_chat_model(..., ModelRefLevel.SESSION)`); added private `_model_ref` and module-local `_reading`; `app.services` imports limited to D12's names

### Step 004 — Session, character and user configuration writes
- `backend/app/services/configuration.py` — filled `update_session_configuration` / `update_character_configuration` (one transaction: owner-scoped existence check, then the set-time `validate_chat_model` at level `session` / `character` when a model is supplied, then one owner-scoped `UPDATE` of the supplied columns plus `updated_at`; nothing supplied → no write; result re-read after commit), `get_character_configuration`, `get_user_settings`, `update_user_settings`; added private `_supplied` (drops `UNSET` args, keeps `None` as clear) and fixed-width `_now_text`; no new `app.services` import

### Step 005 — The configuration router
- `backend/app/routers/configuration.py` — filled the seven handlers: `/api/models` maps each `EnabledChatModel` to server id / server name / model name in service order; GETs validate the service dataclasses with `from_attributes`; PATCHes map `model_fields_set` to keyword args via private `_sent` (unsent → `UNSET`, sent `null` → `None`), the `model` sub-object → `ModelRef` (character `null` → `None` clear); added the service imports
- `backend/app/main.py` — no coder change (skeleton already registers `configuration_router` last)
- `backend/app/routers/sessions.py` — no coder change (skeleton already amended the no-PATCH docstring)

### Step 006 — The configuration API module
- `frontend/src/app/configurationApi.ts` — filled the five calls over `apiGet` / `apiPatch` (patch passed through as-is, signal last, `{ models }` unwrapped); removed the `notImplemented` stub helper; added the `shared/api` import, private `EnabledModelListResponse`, path constants and `sessionConfigurationPath` (id only `encodeURIComponent`-escaped)

### Step 007 — The settings screen at `/settings`
- `frontend/src/app/settingsState.ts` — filled `loadSettings` (abort-guarded, never rejects), the two setters, `isDirty` / `canSave` and `saveSettings` (changed keys only, trimmed / blank → null; empty patch sends nothing; fixed "Could not save your settings."); removed `notImplemented`; added private `SAVE_FAILED`, `isAbortRejection`, `wireValue`, `applySaved`, `patchOf` and the `fetchUserSettings` / `updateUserSettings` imports
- `frontend/src/app/SettingsScreen.tsx` — filled the screen: `Title order={2}` "Settings", a `section` "Languages" (`Title order={3}`; Loader / failure + Retry / two `TextInput`s with the description, inline save-failure `Alert`, Save gated by `canSave`), then `MemoLevelGroup` "Your notes" at order 3 (not reorderable); both loads on mount with per-load controllers aborted on unmount and on Retry
- `frontend/src/app/App.tsx` — `/settings` route renders `<SettingsScreen />` (import added)

### Step 008 — The session configuration state
- `frontend/src/app/sessionConfigState.ts` — filled `loadSessionConfig` (two private abort-guarded reads `loadConfiguration` / `loadModels` under `Promise.all`, each with its own status, failure keeps previous data, never rejects), `chooseModel` (skips same model / in-flight; non-optimistic PATCH `{ model }`; `.code === "model_not_enabled"` → fixed sentence then awaited models re-read via `loadModels`; else "Could not change the model."), `applySessionConfiguration`, `sameModel`, `modelUsability` (D2 order) and `sendBlockedReason`; removed `notImplemented`; added the fixed-sentence constants, `isAbortRejection`, and the `runInAction` / `isApiError` / `configurationApi` imports

### Step 009 — The session configuration draft
- `frontend/src/app/sessionConfigDraft.ts` — constructor seeds the nine fields per D18 (source "set" iff `session` non-null; text session → inherited → ""; tool inherit / on / off) then `makeAutoObservable`; filled `clientErrors` (blank "set" text → fixed sentences), `errors` (server merged under client), `canSubmit`, `patchOf` (resulting override `!==` original `session`; prompt verbatim, languages trimmed, tools bool, inherit → null; never `model`) and `submitSessionConfig` (gated by `canSubmit`; empty patch → `onSaved(original)` without a request; PATCH → "done" + `onSaved(response)`; any non-abort failure → general "Could not save the session configuration." and "idle"; abort → returns without writing; never rejects); removed `notImplemented`; added private sentence constants, seed/override helpers, `isAbortRejection`, and the `mobx` / `updateSessionConfiguration` / `Setting` imports

### Step 010 — The session configuration modal
- `frontend/src/app/SessionConfigModal.tsx` — filled `SessionConfigModal` (Mantine `Modal` "Session configuration", body mounted only while `opened`); added the private observer body `SessionConfigBody` (fresh `SessionConfigDraft` via `useState`, draft fields assigned in `runInAction`, errors under each input, general `Alert` above Cancel / Save, Save gated by `canSubmit` and running `submitSessionConfig` without a signal per the mutation posture, its `onSaved` calls the prop `onSaved` then `onClose`), private `SourceControl` (visible label `Text` naming the `SegmentedControl` radio group via `aria-labelledby`) and `ToolControl`, and the inherited-line helpers reading the loaded configuration

### Step 011 — The session header bar and the Send gate
- `frontend/src/app/SessionConfigBar.tsx` — filled the bar: `Group` role "group" "Session configuration"; load on mount with a controller aborted on unmount (Retry aborts and re-runs with a fresh one); `Loader` while either read is idle/loading; failure sentence + "Retry"; "Model" `Select` (served-order options "<model_name> (<server_name>)", disabled "(not enabled)" option for an unlisted captured model, value = captured, "Choose a model" / disabled "No model is enabled" placeholders, disabled while saving, `allowDeselect={false}`, `modelFailure` text under it); "Tools" group (role "group") with three `Badge`s; gear `IconButton` disabled until the configuration is ready, opening `SessionConfigModal` whose `onSaved` calls `applySessionConfiguration`; private `encodeModel` / `decodeModel` (split at first `:`) and `toolLabel`
- `frontend/src/app/Composer.tsx` — replaced the skeleton throw with the D17 gate: Send disabled when `!canSend` or (my turn and reason non-null); reason text rendered in the button row under the same condition; Settle untouched
- `frontend/src/app/SessionStream.tsx` — no coder change (skeleton already passes `sendBlockedReason` through)
- `frontend/src/app/SessionScreen.tsx` — `SessionConfigState` via `useState` with the top hooks; `SessionConfigBar` as the header `Stack`'s last child after the title `Group` (ready render only); `SessionStream` gets `sendBlockedReason(configState)`; module comment updated

## Skeleton

### Step 001 — frozen interface (2026-10-03)
- `backend/app/db/schema.py` — `characters` gains, after `updated_at`: `Column("model_server_id", BigInteger().with_variant(Integer(), "sqlite"), nullable=True)` (no FK), `Column("model_name", Text, nullable=True)`, `Column("system_prompt", Text, nullable=True)`, `Column("tool_memo_search" | "tool_session_search" | "tool_web_search", Boolean, nullable=True)`; plus `CheckConstraint("(model_server_id IS NULL AND model_name IS NULL) OR (model_server_id IS NOT NULL AND model_name IS NOT NULL)", name="ck_characters_model_both_or_neither")` — changed (written in full; comment replaced)
- `backend/app/db/schema.py` — `sessions` gains the same six columns plus `Column("rp_language", Text, nullable=True)`, `Column("preferred_language", Text, nullable=True)`, and the same CHECK named `ck_sessions_model_both_or_neither` — changed (written in full; comment replaced). `users` unchanged.
- `backend/app/errors.py` — `class NoModelEnabledError(DomainError)`: `code = "no_model_enabled"`, `http_status = 409`, `__init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None` (default message "No model is enabled on this instance.") — new (written in full)
- `backend/app/errors.py` — `class ModelNotChosenError(DomainError)`: `code = "model_not_chosen"`, `http_status = 409`, same `__init__` (default message "No model is chosen for this session.") — new (written in full)
- `backend/app/models/configuration.py` — new module:
  - `ConfigurationLevel = Literal["session", "character", "user", "default"]` (the level literal)
  - `LanguageIn = Annotated[str | None, AfterValidator(_normalise_language)]`; `SystemPromptIn = Annotated[str | None, AfterValidator(_normalise_system_prompt)]`; `ModelNameIn = Annotated[str, AfterValidator(_require_non_blank_model_name)]` — the three private validators are stubs (`raise NotImplementedError`)
  - `ModelRefOut(BaseModel)`: `server_id: SnowflakeOut; model_name: str`
  - `EnabledModelResponse(BaseModel)`: `server_id: SnowflakeOut; server_name: str; model_name: str`
  - `EnabledModelListResponse(BaseModel)`: `models: list[EnabledModelResponse]`
  - `UserSettingsResponse(BaseModel)`: `rp_language: str | None; preferred_language: str | None`
  - `CharacterConfigurationResponse(BaseModel)`: `model: ModelRefOut | None; system_prompt: str | None; tool_memo_search / tool_session_search / tool_web_search: bool | None`
  - `TextSettingResponse(BaseModel)` (text setting): `session: str | None; inherited: str | None; inherited_level: ConfigurationLevel | None; value: str | None; level: ConfigurationLevel | None`
  - `BooleanSettingResponse(BaseModel)` (boolean setting): `session: bool | None; inherited: bool | None; inherited_level: ConfigurationLevel | None; value: bool; level: ConfigurationLevel | None`
  - `SessionConfigurationResponse(BaseModel)`: `model: ModelRefOut | None; system_prompt: TextSettingResponse; tool_memo_search / tool_session_search / tool_web_search: BooleanSettingResponse; rp_language: TextSettingResponse; preferred_language: TextSettingResponse`
  - every response model: `model_config = ConfigDict(from_attributes=True)`
  - `ModelRefIn(BaseModel)` (`extra="ignore"`): `server_id: SnowflakeIn; model_name: ModelNameIn`
  - `UpdateUserSettingsRequest(BaseModel)` (`extra="ignore"`): `rp_language: LanguageIn = None; preferred_language: LanguageIn = None`
  - `UpdateSessionConfigurationRequest(BaseModel)` (`extra="ignore"`): `model: ModelRefIn | None = None` with `@field_validator("model", mode="before") _reject_null_model(cls, value: Any) -> Any` (stub); `system_prompt: SystemPromptIn = None`; `tool_memo_search / tool_session_search / tool_web_search: StrictBool | None = None`; `rp_language: LanguageIn = None; preferred_language: LanguageIn = None`
  - `UpdateCharacterConfigurationRequest(BaseModel)` (`extra="ignore"`): `model: ModelRefIn | None = None` (explicit null accepted); `system_prompt: SystemPromptIn = None`; the three `tool_*: StrictBool | None = None`; no language fields
  - "Which keys were sent" = pydantic's `model_fields_set` (no extra accessor). Defaults are not validated, so an absent key never reaches a validator.
- Caller-compile edits (out of Source-files scope): None.

### Step 002 — frozen interface (2026-10-03)
- `backend/app/services/llm_registry.py` — `def list_enabled_chat_models(connection: Connection) -> list[EnabledChatModel]` — new (stub raises `NotImplementedError`); placed after `validate_chat_model`
- `backend/app/services/llm_registry.py` — `def first_enabled_chat_model(connection: Connection) -> EnabledChatModel | None` — new (stub raises `NotImplementedError`)
- `backend/app/services/llm_registry.py` — `validate_chat_model(connection: Connection, server_id: int, model_name: str, level: ModelRefLevel) -> EnabledChatModel` — unchanged signature, error and detail. Its existing `_reading` guard already only rolls back a transaction it autobegan (`opened_here = not connection.in_transaction()`), never calls `begin()`; the coder confirms D12 posture and reuses `_reading` for the two new reads.
- `EnabledChatModel(server: LlmServer, model_name: str)` (frozen dataclass) — unchanged; the item type of both new reads.
- `backend/app/services/sessions.py` — `start_session(connection: Connection, generator: SnowflakeGenerator, user_id: int, character_id: int, setup_id: int | None = None) -> RpSession` — unchanged signature and return (`RpSession`, eight fields). Body left as-is (no capture yet; the insert leaves `model_server_id` / `model_name` NULL by default) so 011's existing tests stay green; the coder adds the D1 capture, extends `_require_parent_character`'s select with the two model columns, and rewrites the module docstring. `RpSession`, `_session_select`, `_to_session` unchanged.
- Caller-compile edits (out of Source-files scope): None.

### Step 003 — frozen interface (2026-10-03)
- `backend/app/services/configuration.py` — new module (all classes `@dataclass(frozen=True)` unless noted):
  - `class ConfigLevel(StrEnum)`: `SESSION = "session"`, `CHARACTER = "character"`, `USER = "user"`, `DEFAULT = "default"` — new
  - `ModelRef(server_id: int, model_name: str)` — new
  - `ResolvedSetting[T](session: T | None, inherited: T | None, inherited_level: ConfigLevel | None, value: T | None, level: ConfigLevel | None)` — new; one PEP 695 generic dataclass, used as `ResolvedSetting[str]` / `ResolvedSetting[bool]`
  - `CharacterAssistantLevel(system_prompt: str | None, tool_memo_search: bool | None, tool_session_search: bool | None, tool_web_search: bool | None)` — new (no model, no language field)
  - `SessionAssistantLevel(model: ModelRef | None, system_prompt: str | None, tool_memo_search: bool | None, tool_session_search: bool | None, tool_web_search: bool | None)` — new
  - `UserLanguageLevel(rp_language: str | None, preferred_language: str | None)` — new (exactly these two fields)
  - `SessionLanguageLevel(rp_language: str | None, preferred_language: str | None)` — new
  - `AssistantConfiguration(model: ModelRef | None, system_prompt: ResolvedSetting[str], tool_memo_search: ResolvedSetting[bool], tool_session_search: ResolvedSetting[bool], tool_web_search: ResolvedSetting[bool])` — new
  - `LanguageConfiguration(rp_language: ResolvedSetting[str], preferred_language: ResolvedSetting[str])` — new
  - `SessionConfiguration(model: ModelRef | None, system_prompt: ResolvedSetting[str], tool_memo_search: ResolvedSetting[bool], tool_session_search: ResolvedSetting[bool], tool_web_search: ResolvedSetting[bool], rp_language: ResolvedSetting[str], preferred_language: ResolvedSetting[str])` — new
  - `def resolve_assistant_chain(character: CharacterAssistantLevel, session: SessionAssistantLevel) -> AssistantConfiguration` — new (stub raises `NotImplementedError`)
  - `def resolve_language_chain(user: UserLanguageLevel, session: SessionLanguageLevel) -> LanguageConfiguration` — new (stub)
  - `def get_session_configuration(connection: Connection, user_id: int, session_id: int) -> SessionConfiguration` — new (stub)
  - `def resolve_model_for_use(connection: Connection, user_id: int, session_id: int) -> EnabledChatModel` — new (stub); `EnabledChatModel` is `app.services.llm_registry.EnabledChatModel`
  - Stub imports from `app.services`: only `EnabledChatModel` from `llm_registry`; the coder adds `first_enabled_chat_model`, `validate_chat_model`, `ModelRefLevel` (D12 list) and the errors as needed. The module docstring states `resolve_model_for_use` has no call site until `021`.
- Caller-compile edits (out of Source-files scope): None.

### Step 004 — frozen interface (2026-10-03)
- `backend/app/services/configuration.py` — extended (module docstring now names steps 003 and 004); new import `from app.services.llm_registry import UNSET, EnabledChatModel, Unset` (D12 sentinel reuse; no second sentinel):
  - `CharacterConfiguration(model: ModelRef | None, system_prompt: str | None, tool_memo_search: bool | None, tool_session_search: bool | None, tool_web_search: bool | None)` — `@dataclass(frozen=True)`, new
  - `UserSettings(rp_language: str | None, preferred_language: str | None)` — `@dataclass(frozen=True)`, new
  - `def update_session_configuration(connection: Connection, user_id: int, session_id: int, *, model: ModelRef | Unset = UNSET, system_prompt: str | None | Unset = UNSET, tool_memo_search: bool | None | Unset = UNSET, tool_session_search: bool | None | Unset = UNSET, tool_web_search: bool | None | Unset = UNSET, rp_language: str | None | Unset = UNSET, preferred_language: str | None | Unset = UNSET) -> SessionConfiguration` — new (stub)
  - `def get_character_configuration(connection: Connection, user_id: int, character_id: int) -> CharacterConfiguration` — new (stub)
  - `def update_character_configuration(connection: Connection, user_id: int, character_id: int, *, model: ModelRef | None | Unset = UNSET, system_prompt: str | None | Unset = UNSET, tool_memo_search: bool | None | Unset = UNSET, tool_session_search: bool | None | Unset = UNSET, tool_web_search: bool | None | Unset = UNSET) -> CharacterConfiguration` — new (stub)
  - `def get_user_settings(connection: Connection, user_id: int) -> UserSettings` — new (stub)
  - `def update_user_settings(connection: Connection, user_id: int, *, rp_language: str | None | Unset = UNSET, preferred_language: str | None | Unset = UNSET) -> UserSettings` — new (stub)
  - All update keyword arguments are keyword-only. The private fixed-width `_now_text()` helper is the coder's to add (not frozen).
- Caller-compile edits (out of Source-files scope): None.

### Step 005 — frozen interface (2026-10-03)
- `backend/app/routers/configuration.py` — new module; `router = APIRouter(tags=["configuration"], dependencies=[Depends(require_user)])`, no prefix, full literal paths. Every handler takes `current_user: Annotated[CurrentUser, Depends(require_user)]` and `connection: Annotated[Connection, Depends(get_connection)]`; path ids are `SnowflakeIn`; bodies are stubs (`raise NotImplementedError`):
  - `@router.get("/api/models", status_code=200) def list_models(current_user, connection) -> EnabledModelListResponse` — new
  - `@router.get("/api/me/settings", status_code=200) def read_own_settings(current_user, connection) -> UserSettingsResponse` — new
  - `@router.patch("/api/me/settings", status_code=200) def update_own_settings(body: UpdateUserSettingsRequest, current_user, connection) -> UserSettingsResponse` — new
  - `@router.get("/api/sessions/{session_id}/configuration", status_code=200) def read_session_configuration(session_id: SnowflakeIn, current_user, connection) -> SessionConfigurationResponse` — new
  - `@router.patch("/api/sessions/{session_id}/configuration", status_code=200) def update_session_configuration_route(session_id: SnowflakeIn, body: UpdateSessionConfigurationRequest, current_user, connection) -> SessionConfigurationResponse` — new
  - `@router.get("/api/characters/{character_id}/configuration", status_code=200) def read_character_configuration(character_id: SnowflakeIn, current_user, connection) -> CharacterConfigurationResponse` — new
  - `@router.patch("/api/characters/{character_id}/configuration", status_code=200) def update_character_configuration_route(character_id: SnowflakeIn, body: UpdateCharacterConfigurationRequest, current_user, connection) -> CharacterConfigurationResponse` — new
  - Service imports (`app.services.configuration` getters/updaters, `ModelRef`, `UNSET`, `app.services.llm_registry.list_enabled_chat_models`) are not in the stub (ruff F401); the coder adds them. Private helpers (e.g. response converters) are the coder's, not frozen.
- `backend/app/main.py` — `from app.routers.configuration import router as configuration_router`; `create_app()` calls `app.include_router(configuration_router)` **last**, after `memos_router`. Module and `create_app` docstrings name it. Signature of `create_app() -> FastAPI` unchanged.
- `backend/app/routers/sessions.py` — docstring only: the no-PATCH note now points at `PATCH /api/sessions/{id}/configuration` in `routers/configuration.py` and says `PATCH /api/sessions/{id}` still does not exist. No code change.
- Caller-compile edits (out of Source-files scope): None.

### Step 006 — frozen interface (2026-10-03)
- `frontend/src/app/configurationApi.ts` — new module; wire types (all `export type`, snake_case as sent, ids `string`):
  - `ModelRef = { server_id: string; model_name: string }` — new
  - `EnabledModel = { server_id: string; server_name: string; model_name: string }` — new
  - `UserSettings = { rp_language: string | null; preferred_language: string | null }` — new
  - `ConfigLevel = "session" | "character" | "user" | "default"` — new
  - `Setting<T extends string | boolean> = { session: T | null; inherited: T | null; inherited_level: ConfigLevel | null; value: T | null; level: ConfigLevel | null }` — new. **Choice:** one uniform generic, `value: T | null` for booleans too (no separate boolean type); consumers treat a null tool value as "unknown".
  - `SessionConfiguration = { model: ModelRef | null; system_prompt: Setting<string>; tool_memo_search: Setting<boolean>; tool_session_search: Setting<boolean>; tool_web_search: Setting<boolean>; rp_language: Setting<string>; preferred_language: Setting<string> }` — new
  - `UserSettingsPatch = { rp_language?: string | null; preferred_language?: string | null }` — new
  - `SessionConfigurationPatch = { model?: ModelRef; system_prompt?: string | null; tool_memo_search?: boolean | null; tool_session_search?: boolean | null; tool_web_search?: boolean | null; rp_language?: string | null; preferred_language?: string | null }` — new (`model` not nullable, D10)
  - `async function fetchEnabledModels(signal?: AbortSignal): Promise<EnabledModel[]>` — new (stub throws)
  - `async function fetchUserSettings(signal?: AbortSignal): Promise<UserSettings>` — new (stub)
  - `async function updateUserSettings(patch: UserSettingsPatch, signal?: AbortSignal): Promise<UserSettings>` — new (stub)
  - `async function fetchSessionConfiguration(sessionId: string, signal?: AbortSignal): Promise<SessionConfiguration>` — new (stub)
  - `async function updateSessionConfiguration(sessionId: string, patch: SessionConfigurationPatch, signal?: AbortSignal): Promise<SessionConfiguration>` — new (stub)
  - Private `notImplemented(...args: unknown[]): never` stub helper (keeps `noUnusedParameters` green); the coder removes it and adds the `apiGet` / `apiPatch` import and private path helpers (not frozen). No character-configuration export (D20).
- Caller-compile edits (out of Source-files scope): None.

### Step 007 — frozen interface (2026-10-03)
- `frontend/src/app/settingsState.ts` — new module:
  - `type SettingsStatus = "idle" | "loading" | "ready" | "failed"` — new
  - `type SettingsSaveStatus = "idle" | "saving"` — new
  - `class SettingsState { status: SettingsStatus = "idle"; saved: UserSettings | null = null; rpLanguage: string = ""; preferredLanguage: string = ""; saveStatus: SettingsSaveStatus = "idle"; saveFailure: string | null = null; constructor() }` — new; no-arg constructor calls `makeAutoObservable(this, {}, { autoBind: true })`; `UserSettings` is `./configurationApi`'s
  - `async function loadSettings(state: SettingsState, signal?: AbortSignal): Promise<void>` — new (stub throws)
  - `function setRpLanguage(state: SettingsState, text: string): void` — new (stub)
  - `function setPreferredLanguage(state: SettingsState, text: string): void` — new (stub)
  - `function isDirty(state: SettingsState): boolean` — new (stub)
  - `function canSave(state: SettingsState): boolean` — new (stub)
  - `async function saveSettings(state: SettingsState): Promise<void>` — new (stub); no signal parameter
  - Private `notImplemented(...args: unknown[]): never` stub helper; the coder removes it. Fixed sentence constant and abort helper are the coder's (not frozen).
- `frontend/src/app/SettingsScreen.tsx` — `const SettingsScreen = observer(function SettingsScreen(): React.JSX.Element)` — new, no props (stub body throws)
- `frontend/src/app/App.tsx` — **not edited by the skeleton**: the `/settings` route element `null` → `<SettingsScreen />` is the coder's one-line change (no signature changes; `AppProps` unchanged). Left unwired so existing App/entries tests do not hit the throwing stub before the test-coder amends them.
- Caller-compile edits (out of Source-files scope): None.

### Step 008 — frozen interface (2026-10-03)
- `frontend/src/app/sessionConfigState.ts` — new module (`EnabledModel`, `ModelRef`, `SessionConfiguration` are `./configurationApi`'s):
  - `type SessionConfigStatus = "idle" | "loading" | "ready" | "failed"` — new (used by both statuses)
  - `type ModelUsability = "unknown" | "no_model_enabled" | "not_chosen" | "not_enabled" | "usable"` — new
  - `class SessionConfigState { readonly sessionId: string; configuration: SessionConfiguration | null = null; configStatus: SessionConfigStatus = "idle"; modelsStatus: SessionConfigStatus = "idle"; models: EnabledModel[] = []; modelSaving: boolean = false; modelFailure: string | null = null; constructor(sessionId: string) }` — new; constructor assigns `sessionId` then calls `makeAutoObservable(this, {}, { autoBind: true })`
  - `async function loadSessionConfig(state: SessionConfigState, signal?: AbortSignal): Promise<void>` — new (stub throws)
  - `async function chooseModel(state: SessionConfigState, model: ModelRef): Promise<void>` — new (stub); no signal parameter
  - `function applySessionConfiguration(state: SessionConfigState, configuration: SessionConfiguration): void` — new (stub)
  - `function sameModel(a: ModelRef, b: ModelRef): boolean` — new (stub)
  - `function modelUsability(state: SessionConfigState): ModelUsability` — new (stub)
  - `function sendBlockedReason(state: SessionConfigState): string | null` — new (stub)
  - Private `notImplemented(...args: unknown[]): never` stub helper; the coder removes it. Fixed-sentence constants, abort helper and the `configurationApi` call imports are the coder's (not frozen).
- Caller-compile edits (out of Source-files scope): None.

### Step 009 — frozen interface (2026-10-03)
- `frontend/src/app/sessionConfigDraft.ts` — new module (`SessionConfiguration`, `SessionConfigurationPatch` are `./configurationApi`'s):
  - `type TextSource = "inherit" | "set"` — new
  - `type ToolChoice = "inherit" | "on" | "off"` — new
  - `type SessionConfigField = "systemPrompt" | "rpLanguage" | "preferredLanguage"` — new (client-error keys)
  - `type SessionConfigClientErrors = Partial<Record<SessionConfigField, string>>` — new
  - `type SessionConfigServerErrorKey = SessionConfigField | "general"` — new (general key `"general"`, as `createUserDraft.ts`)
  - `type SessionConfigServerErrors = Partial<Record<SessionConfigServerErrorKey, string>>` — new
  - `type SessionConfigErrors = Partial<Record<SessionConfigServerErrorKey, string>>` — new
  - `type SessionConfigSubmitStatus = "idle" | "submitting" | "done"` — new
  - `class SessionConfigDraft { readonly sessionId: string; readonly original: SessionConfiguration; systemPromptSource: TextSource; systemPrompt: string; rpLanguageSource: TextSource; rpLanguage: string; preferredLanguageSource: TextSource; preferredLanguage: string; toolMemoSearch: ToolChoice; toolSessionSearch: ToolChoice; toolWebSearch: ToolChoice; serverErrors: SessionConfigServerErrors = {}; submitStatus: SessionConfigSubmitStatus = "idle"; constructor(sessionId: string, configuration: SessionConfiguration) }` — new; stub constructor assigns `sessionId` / `original` then throws; the coder seeds the nine fields and calls `makeAutoObservable(this, {}, { autoBind: true })`. Fields are plain-assignable (no setter functions frozen; intent names none).
  - `function clientErrors(draft: SessionConfigDraft): SessionConfigClientErrors` — new (stub throws)
  - `function errors(draft: SessionConfigDraft): SessionConfigErrors` — new (stub)
  - `function canSubmit(draft: SessionConfigDraft): boolean` — new (stub)
  - `function patchOf(draft: SessionConfigDraft): SessionConfigurationPatch` — new (stub)
  - `async function submitSessionConfig(draft: SessionConfigDraft, onSaved: (saved: SessionConfiguration) => void, signal?: AbortSignal): Promise<void>` — new (stub)
  - Private `notImplemented(...args: unknown[]): never` stub helper; the coder removes it. Fixed-sentence constants, abort helper and the `updateSessionConfiguration` / `mobx` imports are the coder's (not frozen).
- Caller-compile edits (out of Source-files scope): None.

### Step 010 — frozen interface (2026-10-03)
- `frontend/src/app/SessionConfigModal.tsx` — new module (`SessionConfiguration` is `./configurationApi`'s):
  - `type SessionConfigModalProps = { opened: boolean; sessionId: string; configuration: SessionConfiguration; onClose: () => void; onSaved: (saved: SessionConfiguration) => void }` — new (exported)
  - `function SessionConfigModal(props: SessionConfigModalProps): React.JSX.Element` — new, named export (stub body throws). The outer component always renders the Mantine `Modal` (`opened={props.opened}`, title "Session configuration") and mounts its body only while `opened`; the body is a private `observer` component that creates `new SessionConfigDraft(sessionId, configuration)` once via `useState` — the body component, its name, and any abort-ref handling are the coder's (not frozen). Draft fields are assigned directly in `runInAction` (step 009 froze no setters).
- Caller-compile edits (out of Source-files scope): None. Not wired into any host (the bar in `011` opens it).

### Step 011 — frozen interface (2026-10-03)
- `frontend/src/app/SessionConfigBar.tsx` — new module:
  - `type SessionConfigBarProps = { state: SessionConfigState }` — new (exported); `SessionConfigState` is `./sessionConfigState`'s
  - `const SessionConfigBar = observer(function SessionConfigBar(props: SessionConfigBarProps): React.JSX.Element)` — new, named export (stub body throws). The Select value encode/decode helper is component-local (not exported, not frozen); the modal open flag is local `useState`.
- `frontend/src/app/Composer.tsx` — `type ComposerProps = { state: StreamState; signal?: AbortSignal; sendBlockedReason?: string | null }` — changed (was `{ state: StreamState; signal?: AbortSignal }`). Body: existing behavior intact; destructures `sendBlockedReason = null`; the new D17 branch (`sendBlockedReason !== null && effectiveKind(state) === "turn"`) throws `not implemented` — the coder replaces it with the Send-disabled gate and the reason text. Partner / null-reason paths are unchanged.
- `frontend/src/app/SessionStream.tsx` — `type SessionStreamProps = { sessionId: string; sendBlockedReason?: string | null }` — changed (was `{ sessionId: string }`). Passes `sendBlockedReason={props.sendBlockedReason ?? null}` to `Composer` (signature plumbing only).
- `frontend/src/app/SessionScreen.tsx` — **not edited by the skeleton**: `SessionScreenProps` unchanged. The coder adds `const [configState] = useState(() => new SessionConfigState(props.sessionId))` with the other top-of-component hooks, mounts `<SessionConfigBar state={configState} />` as the header's last child (inside the header `Stack gap="xs"`, after the title `Group`) in the ready render only, and passes `sendBlockedReason={sendBlockedReason(configState)}` to `SessionStream`. Left unwired so the existing SessionScreen / App / entries ready renders do not hit the throwing bar stub before the test-coder amends their stubs (same posture as 007's `App.tsx`).
- Caller-compile edits (out of Source-files scope): None. `npm run typecheck` clean; no existing test file fails typecheck (both new props are optional).

## Tests

### Step 001 — tests (2026-10-03)
- `backend/tests/test_db_schema.py` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5 — new `__S017_001_DoD<n>` section at the end: `characters` = 009's seven + six new, `sessions` = 011's eight + eight new, new columns nullable / no default / no FK (metadata and PRAGMA), forbidden names still absent; both-or-neither CHECK refuses either half alone and accepts both-set / both-NULL / omitted, a `model_server_id` naming no server inserts with FKs on (both tables); DoD-3 `users` tests placed beside the 003/001 users tests.
- `backend/tests/test_db_schema.py` — DoD-5 amendments in place: `CHARACTERS_COLUMNS` (now `CHARACTERS_009_COLUMNS | CHARACTERS_017_COLUMNS`) and the "exactly the seven" test renamed to `…_thirteen_…`; `FORBIDDEN_CHARACTERS_COLUMNS` drops `system_prompt`; `SESSIONS_COLUMNS` (now `SESSIONS_011_COLUMNS | SESSIONS_017_COLUMNS`) and "exactly the eight" renamed to `…_sixteen_…`; `FORBIDDEN_SESSIONS_COLUMNS` drops `rp_language`, `preferred_language`, `system_prompt`; the two "other columns are not nullable" docstrings reworded (parametrize lists unchanged). Plus pin tests that the amended constants are exactly that.
- `backend/tests/test_configuration_models.py` — covers DoD-6..DoD-10 — the two 409 errors (class, bare message/detail, route envelope); user / session / character request normalisation and `model_fields_set` (trim, blank→null-as-sent, verbatim prompt and model_name, session `model: null` refused, character `model: null` accepted, StrictBool tools, non-numeric/blank model refs refused, unknown/language keys ignored); response wire shapes (decimal-string `server_id`, null model, exactly 7 / 5 / 3 / 5 keys, level literal).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 [manual/live, no test]

### Step 002 — tests (2026-10-03)
- `backend/tests/test_llm_registry_enabled.py` — covers DoD-1, DoD-2, DoD-3 — new file: D7 order (server id then models.id, with ids disagreeing so server B's model is first), disabled / deleted-server models absent, enabled embedding-designated model present, `[]` when none; first enabled = first of that order, none when nothing enabled, disabling it promotes the next; each of the two reads and `validate_chat_model` (enabled and disabled ref) inside a caller's `begin()` block keeps rows written before and after it on commit, and standalone leaves `in_transaction()` false and permits a later `begin()`.
- `backend/tests/test_sessions_capture.py` — covers DoD-4 .. DoD-10 — new file: NULL capture with nothing enabled (also with only disabled rows); `RpSession` keeps its eight fields; first-enabled capture (D7 order); character's enabled pair beats first enabled; a disabled or missing-server character pair captured unchanged with/without others enabled; captured pair fixed after character change and first-enabled change, new session takes the character's new pair; prompt / tools / languages not copied (NULL); refusals (other user's / unknown character, unknown / foreign / other-character / archived setup) keep 011's codes, insert nothing, same outcome with and without enabled models.
- `backend/tests/test_sessions_service.py` — covers DoD-11 — amended in place (only this test): 011's import guard renamed `test_the_service_module_imports_no_other_service__S011_002_DoD16__S017_002_DoD11`; AST check now allows exactly `from app.services.llm_registry import <D12 names>` (`list_enabled_chat_models`, `first_enabled_chat_model`, `validate_chat_model`, `ModelRefLevel`, `EnabledChatModel`, `UNSET`, `Unset`); any other `app.services.*` import, other `llm_registry` name, star import, `from app.services import llm_registry` / `import app.services.llm_registry`, or relative import still fails.
- DoD-10's "`test_sessions_service.py` passes with only the DoD-11 amendment / `test_sessions_router.py` passes unmodified" is a verifier run, not a new test.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓

### Step 003 — tests (2026-10-03)
- `backend/tests/test_configuration_resolver.py` — covers DoD-1 .. DoD-5 — pure resolvers on hand-built inputs: `ConfigLevel` values are the four wire strings; prompt character-inherited / session-wins / all-null (plus session-over-nothing); tools independent, unset tool on with level `default`, session beats contrary character; model passed through unchanged (pair, dead reference, none); character input has no model / language field; languages user-inherited / session-wins / all-null; `inspect.signature` parameter names `character, session` and `user, session`; user input fields exactly the two languages.
- `backend/tests/test_configuration_resolver.py` — covers DoD-6, DoD-7 — `get_session_configuration` on raw rows: combined seven-field result; prompt live after character change while captured model fixed after character model columns set; no write, no open transaction; another user's / missing session → `session_not_found`; archived session and session under archived character read normally.
- `backend/tests/test_configuration_resolver.py` — covers DoD-8, DoD-9 — `resolve_model_for_use`: D2 order across nothing-registered / only-disabled / enabled registries with NULL, disabled, dead and enabled captured pairs; empty `detail` and codes for the two new errors; `model_not_enabled` detail `{server_id: "<decimal>", model_name, level: "session"}`; other user's / missing session not found under both registry states; session row identical before/after every case; captured non-first model returned, no fallback.
- `backend/tests/test_configuration_resolver.py` — covers DoD-10 — AST check: only `app.services.llm_registry` imported, names ⊆ D12 list (incl. 004's `UNSET` / `Unset`); no `fastapi`.
- No pre-existing test file amended.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓

### Step 004 — tests (2026-10-03)
- `backend/tests/test_configuration_writes.py` — covers DoD-1 .. DoD-5 — `update_session_configuration`: enabled model written, returned, re-read on a fresh connection; disabled / no-such-server model → `model_not_enabled` detail `{server_id: "<decimal>", model_name, level: "session"}` and the whole row (prompt, model, `updated_at`) unchanged; prompt-only write leaves other columns; `None` clears prompt / tools / languages back to character / default / user; `updated_at` bumped fixed-width and later, `last_used_at` unchanged; empty update leaves the row and returns the configuration; archived session updates; other user's / missing session → `session_not_found` for settings, enabled, disabled and empty updates, no session row changed.
- `backend/tests/test_configuration_writes.py` — covers DoD-6 .. DoD-9 — `update_character_configuration` / `get_character_configuration`: model + prompt + web search off written and read back; a session started afterwards (`start_session`) resolves prompt and web search at level `character`; model changes leave every session row identical; `model=None` nulls both columns; not-enabled model → level `character` (never `user`), character and sessions unchanged; name / sheet / archived_at kept, `updated_at` bumped; other user's / missing character → `character_not_found` on read and on every update shape; archived character reads and updates.
- `backend/tests/test_configuration_writes.py` — covers DoD-10, DoD-11 — `update_user_settings` / `get_user_settings`: both languages persist and resolve at level `user` for a session with no override; `preferred_language=None` clears only that one; user B's row unchanged; username / password_hash / role / is_enabled / last_login_at unchanged, `updated_at` bumped fixed-width; empty update leaves the row.
- No pre-existing test file amended.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓

### Step 005 — tests (2026-10-03)
- `backend/tests/test_configuration_router.py` — covers DoD-1 .. DoD-10 — real `create_app()` with per-user cookie clients; registry raw-inserted with server-id / models.id orders disagreeing. DoD-1: `GET /api/models` D7 order, exactly three keys per item, `[]` empty / only-disabled, admin == roleplayer, all seven routes 401 anonymously. DoD-2: settings PATCH trims and persists (fresh login re-reads), B unaffected, `""` → null leaving the other key, `GET /api/me` exactly `id`/`username`/`role`. DoD-3: 8-key `Session`, first enabled captured, tools `{null, true, default, true, default}`, prompt all-null, languages at level `user` after settings saved. DoD-4: character PATCH answers and re-reads; earlier session keeps captured model with prompt / memo search at level `character`; later session captures the character's model. DoD-5: session model PATCH persists; disabled / missing-server model → 409 detail `{server_id, model_name, level: "session"}` and nothing (incl. other fields) written; `model: null` → 422. DoD-6: session overrides at level `session` with `inherited` character / user; null clears back, web search stays off. DoD-7: language keys on character route change nothing and session languages stay `user`; disabled model → 409 level `character`, unchanged; `model: null` clears (later session takes first enabled). DoD-8: other user's / missing session and character, GET and PATCH → 404 codes, owner's state unchanged; archived session and character readable and writable. DoD-9: `Session` 8 keys after a config write, `PATCH /api/sessions/{id}` 405, router holds exactly the seven pairs, its routes are the last `APIRoute`s of the app. DoD-10: `last_used_at` unchanged, `updated_at` advances.
- No pre-existing test file amended.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 [manual/live, no test]

### Step 006 — tests (2026-10-03)
- `frontend/tests/app/configurationApi.test.ts` — covers DoD-1 .. DoD-6 — `fetch` stubbed per file, matched by exact path/query/method. DoD-1: exactly `GET /api/models`, unwrapped `models` in served (unsorted) order, `server_id` identical strings, `[]`. DoD-2: `GET /api/me/settings`; `PATCH /api/me/settings` raw bodies exactly `{"rp_language":"Japanese"}` and `{"preferred_language":null}`; each resolves to the served settings. DoD-3: exactly `GET /api/sessions/7250000000000000101/configuration`, served object strict-equal (seven keys, five per setting), null model kept, id verbatim. DoD-4: session PATCH with exactly `model` (string `server_id`), and exactly `system_prompt: null` + `tool_web_search: false`; resolves to served. DoD-5: 409 `model_not_enabled` → `ApiError` code + `detail.level` `"session"`; 404 passthrough; in-flight and pre-aborted signals reject with the `AbortError`, not an `ApiError`. DoD-6: no export name matches `/character/i`; runtime function exports are exactly the five calls, none requests `/api/characters`.
- No pre-existing test file amended.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓

### Step 007 — tests (2026-10-03)
- `frontend/tests/app/settingsState.test.ts` — covers DoD-1, DoD-2, DoD-3 — fresh state idle / null / `""`; load requests exactly `GET /api/me/settings`, `"loading"` in flight, `{Japanese, null}` → ready with `"Japanese"` / `""`, 500 / 401 / transport → `"failed"` and resolves, mid-flight abort and response-after-abort write nothing; `isDirty` / `canSave` (unchanged, `" Japanese "`, `""`, blank vs null, saving, not-ready); `saveSettings` PATCH bodies exactly `{"rp_language":"French"}` / `{"preferred_language":null}` / trimmed / both keys, texts and `saved` from the response, not dirty after, `"saving"` in flight, failures set "Could not save your settings." keeping typed text, later success clears it, empty patch sends nothing.
- `frontend/tests/app/SettingsScreen.test.tsx` — covers DoD-4, DoD-5, DoD-6, DoD-7 — "Settings" heading → "Languages" region → "Your notes" region in document order; served values, null → empty, both descriptions, Save disabled unchanged; user notes from exactly `GET /api/memos?scope=user`; typing both + Save PATCHes both keys, inputs show served values, Save disabled; failed load shows the sentence + Retry in Languages while Your notes renders, Retry re-requests; failed save sentence in Languages, typed text kept; `notifyFailure` spy never called, no notification; New note POST `{scope:"user", scope_id:null, body}`; no `Note <n> of <total>` listitem (with and without a new note open).
- `frontend/tests/app/App.test.tsx` — covers DoD-8, DoD-9 — amended: `/settings` removed from `EMPTY_CENTRE_ROUTES`; `stubWorkspace` answers `GET /api/me/settings` and `GET /api/memos?scope=user` by exact path + query (so 016's `NO_SESSION_ROUTES` `/settings` clause sees a well-formed screen). Added: `/settings` renders the Settings heading, Languages and Your notes regions in main with the tree present and one request each (DoD-8); user menu "Settings" → location `/settings` and the screen renders (DoD-9).
- `frontend/tests/entries.test.tsx` — covers DoD-8 — amended `stubAppIdentity` to answer the two reads by exact path + query; added a clause booting the app entry at `/settings` (shell, both reads seen, "Settings" heading).
- `frontend/tests/app/WorkspaceShell.test.tsx` — DoD-8 reviewed, header comment only: it renders fixed children, never `/settings` as an empty centre, so no stub or assertion changed.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 [manual/live, no test]

### Step 008 — tests (2026-10-03)
- `frontend/tests/app/sessionConfigState.test.ts` — covers DoD-1 .. DoD-8 — `fetch` stubbed by exact method + path + query with a request log; `notifyFailure` mocked at file level. DoD-1: fresh `SessionConfigState("s1")` snapshot. DoD-2: exactly the two GETs, both issued before either answers, served config and (unsorted) models kept verbatim with string ids, `[]` ready; models-only / config-only failure (500, 404, transport) splits the statuses; both failing resolves; failed reload keeps previous data; mid-flight abort, response-after-abort and pre-aborted signal write nothing. DoD-3: `sameModel` (equal, other server, other name, ids as strings past 2^53); `no_model_enabled` (with and without captured), `not_chosen`, `not_enabled` (unknown pair; same name on other `server_id`), `usable` with the strings-table sentences / null. DoD-4: every non-both-ready status pair (incl. empty list) → `unknown` / null; pending and failed real loads. DoD-5: PATCH raw body exactly `{"model":{...}}`, saving true and old model while pending, served configuration after, failure cleared, from null captured. DoD-6: 409 `model_not_enabled` → sentence, config kept, then `GET /api/models` with the re-read list; 500 / other-code 409 / 422 / transport → "Could not change the model.", nothing re-read; `notifyFailure` never called. DoD-7: equal-by-value captured ref sends nothing; overlapping second choice sends nothing. DoD-8: `applySessionConfiguration` replaces; autorun on `sendBlockedReason` re-runs after load, after `chooseModel` success (and after apply).
- No pre-existing test file amended.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓

### Step 009 — tests (2026-10-03)
- `frontend/tests/app/sessionConfigDraft.test.ts` — covers DoD-1 .. DoD-7 — draft fields assigned in `runInAction` (no setters frozen); `fetch` stubbed by exact method + path + query; `notifyFailure` mocked at file level. DoD-1: seeding from the "S" / web-off / "C" / "Japanese" configuration (prompt `set` "S", web `off`, other tools `inherit`, RP `inherit` "Japanese", preferred `inherit` ""), plus session `true` → `on`, session language → `set`, `sessionId` / `original` kept, idle, no errors. DoD-2: untouched `{}`; prompt → inherit `{system_prompt: null}`; memo off `{tool_memo_search: false}`; session search on `true`; web off → inherit `{tool_web_search: null}`; set back → `{}`; no `model` key with everything changed. DoD-3: `"  French "` → `"French"`, preferred trimmed, prompt `"  Be terse.\n"` verbatim, trimmed text equal to original session → omitted, inherit texts ignored (also no client error). DoD-4: blank / whitespace-only prompt and each language on `set` → the strings-table error keyed `systemPrompt` / `rpLanguage` / `preferredLanguage`, `canSubmit` false, inherit removes it; submit with a client error sends nothing. DoD-5: PATCH `/api/sessions/7250000000000000101/configuration` body exactly patchOf's keys, no `model`; 200 → `"done"`, `onSaved` gets served config; `"submitting"` + `canSubmit` false in flight; second submit in flight sends nothing. DoD-6: empty patch (incl. edited inherit text) → no request, `onSaved(original)`. DoD-7: 500 / 422 (FastAPI and envelope) / 409 / transport → `serverErrors` only `general` "Could not save the session configuration.", `"idle"`, fields as typed, no `onSaved`, resolves, `notifyFailure` not called; `original` unchanged.
- No pre-existing test file amended.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓

### Step 010 — tests (2026-10-03)
- `frontend/tests/app/SessionConfigModal.test.tsx` — covers DoD-1 .. DoD-8 — `SessionConfigModal` rendered in `AppProviders` with `opened` toggled by `rerender`; dialog found by role + name "Session configuration", each `SegmentedControl` as a `radiogroup` named by its label; `fetch` stubbed (only `PATCH /api/sessions/7250000000000000101/configuration` answers), `notifyFailure` mocked. DoD-1: all six groups on "Inherit", options Inherit/Set vs Inherit/On/Off, no session input, prompt line "Inherited from the character:" + "Stay in character.", tool lines in order [character: off, on (default), on (default)], language lines [your settings: Japanese, nothing-to-inherit]. DoD-2: Set prefills "Stay in character."; "Be terse." + Save → one PATCH body exactly `{system_prompt}`, `onSaved(served)` then `onClose`. DoD-3: web "Off", RP "Set" "French"; both → Inherit sends exactly `{tool_web_search: null, rp_language: null}`. DoD-4: empty Set preferred → sentence + Save disabled; typing enables, sentence gone. DoD-5: unchanged Save → no request, `onSaved(original)`, `onClose`; Cancel → no request, `onClose` only. DoD-6: 500 and transport failure → sentence in dialog, typed values kept, no callbacks, no notification. DoD-7: close + reopen resets to the prop's seeding (all-inherited and overridden variants). DoD-8: no control named /model/i; language groups/inputs not named /character/i; language lines name "your settings" and "character" appears only in the prompt's nothing-to-inherit sentence when the character supplies nothing.
- No pre-existing test file amended.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 [manual/live, no test]

### Step 011 — tests (2026-10-03)
- `frontend/tests/app/SessionConfigBar.test.tsx` — covers DoD-1 .. DoD-5 — new file; `SessionConfigBar` over a fresh `SessionConfigState` in `AppProviders`, `fetch` stubbed by exact method + path + query, `notifyFailure` mocked. DoD-1: "Model" shows "A (S1)", options exactly ["A (S1)", "B (S2)"] in served order (and reversed served order), "Tools" badges exactly "Memo search: on" / "Session search: off" / "Web search: on", gear enabled; gear disabled and no Tools while the configuration is pending. DoD-2: choosing "B (S2)" PATCHes body exactly `{model:{server_id:S2,model_name:"B"}}`, picker disabled and still "A (S1)" while pending, "B (S2)" after the 200. DoD-3: null captured → empty value + placeholder "Choose a model"; captured A absent from [B] (also same name on another server) → "A (not enabled)", that option disabled and pressing it sends nothing; empty list → picker disabled, placeholder "No model is enabled". DoD-4: 409 `model_not_enabled` → "That model is no longer enabled." in the bar, "A (S1)" kept, `GET /api/models` re-requested after the PATCH, configuration not re-read; config / models / both-transport load failures → "Could not load the session configuration" + "Retry", Retry re-requests both; no `notifyFailure`, no notification. DoD-5: gear opens the "Session configuration" dialog; Web search "Off" + Save PATCHes `{tool_web_search:false}`, dialog closes, badge "Web search: off", no configuration GET after the PATCH.
- `frontend/tests/app/Composer.test.tsx` — covers DoD-6, DoD-7 — new last block (013 cases untouched): my turn + reason + "Hello" → Send disabled, sentence shown, Settle enabled; typing never enables Send and pressing it posts nothing; Settle appends then settles (and settles alone with a zone row); partner + reason → no sentence, Send files `{"kind":"partner","text":"Typed partner text"}`, paste files immediately, Settle disabled as before; switching partner → my turn shows the reason and disables Send; reason `null` → Send / preview / Discard / partner paste behave as 013 006.
- `frontend/tests/app/SessionScreen.test.tsx` — covers DoD-8, DoD-9, DoD-10, DoD-11 — amended: `streamAnswer` also answers `GET <id>/configuration` (seven-key, captured A) and `GET /api/models` (`[A]`, usable) by exact path; 011 DoD-5's exact request list gains those two GETs; 011 DoD-4's header residue check subtracts the bar group's text. No "no button outside the Notes region / wall controls" clause exists in this file any more, so nothing else to exclude. New last block: DoD-8 bar inside the header after the heading and before the composer, no-model reason + Send disabled after typing (Settle enabled); models [A] + null → choose-a-model reason, choosing "A (S1)" PATCHes `{model:A}`, reason gone, Send enabled with the draft. DoD-9 captured A vs [B] → not-enabled reason; config pending, config 500 / transport (models []), models 500 → Send enabled, no "Cannot send:" text. DoD-10 loading / not found / failed (500, transport) → no bar group (even hidden), no configuration or models request; a → b requests b's configuration once and shows "B (S2)".
- `frontend/tests/app/App.test.tsx` — covers DoD-11 — amended: `stubWorkspace` answers `GET /api/sessions/<id>/configuration` (held session; else 404 `session_not_found`) and `GET /api/models` by exact path. Added: `/sessions/1` holds the "Session configuration" group with one read of each; `/` makes neither read.
- `frontend/tests/entries.test.tsx` — covers DoD-11 — amended `stubAppIdentity` to answer `/api/sessions/abc123/configuration` and `/api/models` with the 404 envelope; added a clause booting at `/sessions/abc123` (shell + user menu) whose stub answers both paths.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 [manual/live, no test]

## Notes & Issues

_populated by the coder when worth saying_

## Ultra phase

- orient: done 2026-10-03
- harvest: done — docs/.cache/ultra/017.session-configuration/harvest.md (2 reports)
- skeleton: done — steps 001–011
- tests: done — steps 001–011
- red-gate: PASS (run 1)
- code: done — steps 001–011
- verify: FAIL (run 1) — 002 SPEC, 005 TEST, 008 TEST, 011 TEST
- blocked 2026-10-03 — 002 SPEC: D12 makes services/sessions.py import first_enabled_chat_model from llm_registry, but 002 DoD-10 / context "Not touched" require 011's tests/test_sessions_service.py (S011_002_DoD16: sessions.py imports no app.services module) to pass unmodified. User chose: stop for /planner. Pending TEST faults to route on resume (verify run 1): 005 DoD-9 (route-order check walks only top-level APIRoute; included routers are wrapper entries in FastAPI 0.141 — use nested walk or OpenAPI order, cf. tests/test_stream_router.py helper); 008 DoD-7 (snapshot helper structured-clones a MobX proxy — use toJS / JSON round-trip); 011 DoD-7 (asserts gate reason absent after the paste, but filing a partner entry flips the position to my turn — assert before the paste or drop it). Advisory: configuration.py module docstring still says "skeleton".
- unblocked 2026-10-03 — /planner revised 002: DoD-11 (amend 011 S011_002_DoD16 import guard to D12 exception), DoD-10 reworded. Routing: 002 test-coder (DoD-11), then TEST round 1 for 005, 008, 011, then verify run 2.
- verify: FAIL (run 2) — 005 TEST (DoD-9 walk still finds no routes)
- verify: PASS (run 3)
