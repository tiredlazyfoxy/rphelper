# Feature 032 — privacy-isolation-audit

| Step | File                                         | Status  | Verifier | Date |
|------|----------------------------------------------|---------|----------|------|
| 001  | `001.logging-redaction-hardening.md`         | done    | PASS     | 2026-10-06 |
| 002  | `002.audit-world-and-route-guard.md`         | done    | PASS     | 2026-10-06 |
| 003  | `003.owner-scoped-sweep.md`                  | done    | PASS     | 2026-10-06 |
| 004  | `004.search-and-tools-sweep.md`              | done    | PASS     | 2026-10-06 |
| 005  | `005.export-import-sweep.md`                 | done    | PASS     | 2026-10-06 |
| 006  | `006.admin-surfaces-and-reverse-lookup.md`   | done    | PASS     | 2026-10-06 |
| 007  | `007.log-sentinel-sweep.md`                  | done    | PASS     | 2026-10-06 |

## Files Changed

### Step 001 — logging and engine redaction hardening
- `backend/app/logging.py` — `AccessQueryRedactionFilter.filter` body implemented (rewrites `record.args[2]` only, drops everything from the first `?`, never drops a record); `configure_logging` installs it on the `uvicorn.access` **logger** idempotently and adds both sinks with `diagnose=False` and `backtrace=False`
- `backend/app/db/engine.py` — engine built with `hide_parameters=True`; URL, `connect_args`, both listeners and the per-path `_engines` cache unchanged

### Step 004 — the audit's one finding (step file says "Source files: None planned")
This entry is non-empty because step 004 is an audit step whose sweep **found a leak**, not
because planned work landed here: `## Ultra phase` decision 19 records the finding and routes
its repair to this step's fix-allowance (024's vector write paths under
`backend/app/services/`). One owner predicate added, nothing else touched.
- `backend/app/services/session_index.py` — in `refresh_session_vectors`, the empty-text
  `delete_vector(session_vec, …)` branch is now driven by an owner-scoped read
  (`sessions.id IN (empty ids) AND sessions.user_id = :user_id`, in the SQL per R5, with no
  `archived_at` predicate per U4/R6), so a session id that is not the caller's is never
  matched and its `session_vec` row is left untouched; signature, name, return type and every
  call site unchanged, and `write_vector` / `delete_vector` themselves untouched (they take no
  user id by design). Two docstring lines made precise ("every session **of the caller's**").

## Skeleton

### Step 001 — frozen interface (2026-10-06)

Two source files, **one new symbol** and **two changed declaration contracts**. Both gates clean:
`mypy app` -> `Success: no issues found in 94 source files`; `ruff check .` -> `All checks passed!`.

**No behaviour is implemented.** The filter body raises `NotImplementedError`,
`configure_logging` does **not** yet install it and still adds the console sink with loguru's
default `diagnose`/`backtrace` (both True) and the file sink with `backtrace` defaulting to True,
and `get_engine` still passes only the URL and `connect_args`. So 001 DoD-1, DoD-2, DoD-4, DoD-5,
DoD-6 and DoD-7 are red against this tree, each for its own right reason (sentinel present /
`hide_parameters` False). DoD-3 ("no query string => emitted unchanged") is the one clause that
passes today, because it asserts the *absence* of a rewrite; that is expected, not vacuous.

#### Frozen symbols

| File | Signature | State |
|---|---|---|
| `backend/app/logging.py` | `class AccessQueryRedactionFilter(logging.Filter)` | **new** |
| `backend/app/logging.py` | `AccessQueryRedactionFilter.filter(self, record: logging.LogRecord) -> bool` | **new** |
| `backend/app/logging.py` | `configure_logging(settings: Settings) -> None` | **changed** — contract only; signature byte-identical to as-built |
| `backend/app/db/engine.py` | `get_engine(settings: Settings) -> Engine` | **changed** — contract only; signature byte-identical to as-built |

- Caller-compile edits (out of Source-files scope): **None.** No signature changed, so no call
  site moved and nothing outside the two Source files was touched.

#### How to bind (the only calling interface either downstream role needs)

- `from app.logging import AccessQueryRedactionFilter, configure_logging` — the filter takes
  **no constructor arguments** (no `__init__` override; stdlib `logging.Filter.__init__`'s
  optional `name` is not used), so it is constructed as `AccessQueryRedactionFilter()`.
- `AccessQueryRedactionFilter.filter` overrides `logging.Filter.filter` and returns `bool`
  (narrower than typeshed's `bool | LogRecord`; mypy accepts the narrowing).
- `from app.db.engine import get_engine` — unchanged; the read-back accessor DoD-7 binds to is
  the public SQLAlchemy attribute **`engine.hide_parameters`** (`bool`), e.g.
  `get_engine(db_settings).hide_parameters`.

#### Frozen contract — `AccessQueryRedactionFilter`

Recorded in the class docstring, and this is the contract the coder must satisfy:

- It rewrites a `uvicorn.access` record so the request **target keeps the path and loses
  everything from the first `?` onward**. The client address, method, HTTP version and status
  survive untouched.
- The target is **`record.args[2]`**: uvicorn logs `'%s - "%s %s HTTP/%s" %d'` with
  `record.args == (client_addr, method, full_path, http_version, status_code)`. That argument is
  the **only** thing the filter rewrites.
- A target with **no query string is left exactly as it was**.
- It is a redactor, not a gate: it **never drops a record**. `filter` returns a **truthy** value
  for every record it is handed, including a record whose shape is not uvicorn's.
- It is installed on the **logger**, so it runs before `InterceptHandler` pre-formats via
  `record.getMessage()` and drops `record.args` — which is why every sink, console and file
  alike, sees the rewritten target. A record handed straight to a handler bypasses logger
  filters.

#### Frozen contract — `configure_logging(settings)`

Signature unchanged. Docstring now states, in addition to everything the function already does
(which is unchanged):

- The redaction filter goes on the `uvicorn.access` **logger**, **not** on a handler, so it
  covers whichever handler emits the record (uvicorn's own dictConfig may attach one of its own).
- **Every** loguru sink — console **and** file — is added with `diagnose=False` **and**
  `backtrace=False`. As built, the console sink passes only `level=` (so both default to True)
  and the file sink passes `diagnose=False` with `backtrace` defaulting to True.
- **Idempotence is part of the frozen contract** (orchestrator decision 9). `app/main.py:165`
  runs `create_app()` at import, so `configure_logging` can run more than once in a process, and
  no fixture anywhere restores a logger's `.filters`. After two calls the `uvicorn.access` logger
  must carry **exactly one** redaction filter, never two. The mechanism is the coder's to choose;
  the stated outcome is not.
- Everything else `configure_logging` does today is untouched and must stay so — including
  `_SILENCED_LOGGERS` silencing `httpx` at `CRITICAL + 1`, `_PROPAGATING_LOGGERS`, the root
  `InterceptHandler` at `NOTSET`, and the fact that no level is set on `sqlalchemy` /
  `sqlalchemy.engine` (both effectively WARNING).

#### Frozen contract — `get_engine(settings)`

Signature unchanged. Docstring now states:

- **Bound parameters are hidden**, so no SQLAlchemy log record at **any** level and no rendered
  statement error (`str(exc)` of `DBAPIError` and its subclasses) carries a bound value;
  SQLAlchemy writes a placeholder in their place.
- Read back as **`engine.hide_parameters`**, which every engine this factory returns reports as
  true.
- That is the **only** engine option added. The URL, `connect_args={"check_same_thread": False,
  "isolation_level": None}`, the `connect` and `begin` listeners and the **per-path caching are
  unchanged**. Because engines are cached per resolved path in `_engines`, the flag is fixed at
  first creation for that path.

The four rows above are the whole contract: the test-coder binds to them and the coder may not
change them.

### Step 002 — frozen interface (2026-10-06)

**No file was written.** Step 002's Source files are "None planned" and
`backend/tests/privacy_audit_support.py` is a **Test file** — the test-coder's to author. This record
is the whole deliverable: it is the *only* thing steps 003..007's test-coders have for **how to
call** the shared world. Expected values come from `context.md`'s enumeration table and each step's
DoD, never from here.

Gates re-run unchanged against the tree as left by step 001's skeleton (from `backend/`):
`.venv/Scripts/python -m mypy app` -> `Success: no issues found in 94 source files`;
`.venv/Scripts/python -m ruff check .` -> `All checks passed!`.

- Caller-compile edits (out of Source-files scope): **None.** No source file was read for edit and
  none was touched.

#### How to bind

- Module path `backend/tests/privacy_audit_support.py`. `backend/tests/__init__.py` exists, so the
  import form is `from tests.privacy_audit_support import ...` (precedent: `from tests.llm_fakes
  import ...`).
- The name does **not** match `test_*`, so pytest never collects it; `[tool.mypy] files = ["app"]`,
  so it is **not** a mypy target, but `ruff check .` **does** lint it (line-length 120, rules
  `E,F,I,B,UP,W`).
- **`backend/tests/llm_fakes.py` must not be modified** (orchestrator decision 8). The support
  module *imports* from it (`FAKE_EMBEDDING_DIM`, `FakeClientFactory`, `FakeEmbeddingClient`,
  `embedding_vector`, `fake_factory`, `vectors_for`) and *adds* the chat/probe/web fakes beside it.
- Types borrowed from the application, with their declaring modules, for the signatures below:
  `app.config.Settings`; `sqlalchemy.Engine`; `fastapi.FastAPI`; `fastapi.routing.APIRoute`;
  `fastapi.testclient.TestClient`; `httpx.Response` / `httpx.Request` / `httpx.MockTransport`;
  `app.services.llm_registry.ChatClientFactory`, `.LlmClientFactory`;
  `app.services.llm.chat.ChatMessage`; `app.services.llm.client.ChatDelta`, `.ToolCallDelta`,
  `.ProbeResult`, `.ProbeOutcome`; `app.services.tools.seam.ToolRegistry`;
  `app.services.web_search.provider.WebResult`; `app.models.memos.MemoScope` (`Literal["user",
  "character", "setup", "session"]`); `app.services.memo_chain.MemoReach` (`Literal["forced",
  "searchable", "disabled"]`).

#### 1. Module constants

| Name | Type | Value / meaning |
|---|---|---|
| `UNKNOWN_ID` | `Final[str]` | `"7250000000000000002"` — the well-formed id that exists nowhere (`context.md` "Unknown id"). |
| `EXISTING_TABLE_NAME` | `Final[str]` | `"characters"` — the substitution for the `{table_name}` path parameter (`002.context.md` "Guard mechanics"). |
| `FAKE_SEAM_OVERRIDE_KEYS` | `Final[tuple[Callable[..., Any], ...]]` | The **four** dependency callables `install_fake_model_seam` replaces, in this order: `app.dependencies.get_llm_client_factory`, `app.routers.stream.get_chat_client_factory`, `app.routers.translation.get_translation_chat_client_factory`, `app.routers.stream.get_tool_registry`. Exposed so a test can assert all four are present in `application.dependency_overrides` (decision 7). |
| `FAKE_SERVER_BASE_URL` | `Final[str]` | The base URL the single seeded LLM server row carries. It is never reached: all four seams are faked. |
| `FAKE_CHAT_MODEL_NAME` | `Final[str]` | The enabled chat model name. Administrative data — **carries no sentinel** (DoD-6). |
| `FAKE_EMBEDDING_MODEL_NAME` | `Final[str]` | The enabled-then-designated embedding model name. **No sentinel** (DoD-6). |
| `DERIVED_STORE_TABLES` | `Final[tuple[str, ...]]` | `("memo_vec", "session_vec", "memo_fts", "message_fts")` — the four real derived-store names (`app/db/search_tables.py:32-39`). There is **no `session_fts`**. |
| `RESTORED_LOGGER_NAMES` | `Final[tuple[str, ...]]` | Every stdlib logger whose `level`, `handlers`, `propagate` **and `.filters`** the log-capture manager snapshots and restores: `("", "uvicorn", "uvicorn.access", "uvicorn.error", "sqlalchemy", "sqlalchemy.engine", "httpx")` (decision 9). |

#### 2. Identities and clients

```python
AuditUser = Literal["A", "B", "ADM"]

@dataclass(frozen=True)
class AuditIdentity:
    label: AuditUser
    user_id: str          # decimal string, as the JSON id boundary carries it
    username: str         # administrative data: never carries a sentinel (DoD-6)
    password: str

@dataclass(frozen=True)
class AuditClients:
    a: TestClient         # cookie-authenticated as A
    b: TestClient         # cookie-authenticated as B
    adm: TestClient       # cookie-authenticated as the bootstrapped admin
    anon: TestClient      # no cookie
    def of(self, user: AuditUser) -> TestClient: ...   # "A" | "B" | "ADM"; anon has no label
```

All four are `TestClient` instances over **the same `FastAPI` application object** (`world.application`),
one client per identity so cookies never cross users (precedent `_as`, `test_characters_router.py:156`).

#### 3. Seeded content — per-user ids for every seeded row

```python
@dataclass(frozen=True)
class SeededMessages:
    partner_id: str                   # POST /entries {"kind":"partner"} — born settled
    zone_id: str                      # POST /zone/messages — current-zone roleplayer message
    turn_head_id: str                 # settle -> kind "turn"
    buried_ids: tuple[str, ...]       # rows related_to turn_head_id (readable only via discussion)
    decision_id: str                  # settle -> kind "decision"
    assistant_id: str                 # the assistant row written by compose
    tool_id: str                      # the tool row written by the scripted tool call
    def all_ids(self) -> tuple[str, ...]: ...

@dataclass(frozen=True)
class SeededMemos:
    ids: Mapping[tuple[MemoScope, MemoReach], str]   # all twelve scope x reach combinations
    reordered_scope: MemoScope                       # the level put into a non-default order
    reordered_ids: tuple[str, ...]                   # that level's ids in the order PUT /api/memos/order set
    def of(self, scope: MemoScope, reach: MemoReach) -> str: ...
    def all_ids(self) -> tuple[str, ...]: ...

@dataclass(frozen=True)
class SeededUserContent:
    identity: AuditIdentity
    character_id: str
    setup_id: str
    session_with_setup_id: str        # holds `messages`
    session_without_setup_id: str
    archived_session_id: str          # archived last (decision 13 order)
    messages: SeededMessages
    memos: SeededMemos
    translated_message_id: str        # == messages.partner_id; only a settled partner row is eligible
    translation_target_language: str
    def all_ids(self) -> tuple[str, ...]:  ...   # every id above, including identity.user_id
    def all_session_ids(self) -> tuple[str, ...]: ...

@dataclass(frozen=True)
class SeededModels:
    server_id: str
    server_name: str                  # administrative: no sentinel (DoD-6)
    chat_model_name: str
    embedding_model_name: str
```

`SeededMemos.ids` holds the **cross product** of the four scopes and the three reaches (12 memos per
user), which satisfies both readings of `002.context.md`'s "each scope …; each reach …".

#### 4. Sentinel registry

```python
SentinelKey = tuple[AuditUser, str, str]          # (user, table, field)

@dataclass(frozen=True)
class SentinelCarrier:
    table: str        # a real table name from app/db/schema.py
    field: str        # a real column name, row-qualified where one table carries several sentinels
    stored: bool      # True => a SELECT on table.field must find the sentinel (DoD-4)
    note: str         # why, when `stored` is False, or which row the qualifier names

SENTINEL_CARRIERS: Final[tuple[SentinelCarrier, ...]]    # the canonical set, seeded for each of A and B

class SentinelRegistry:
    def __init__(self) -> None: ...
    def register(self, *, user: AuditUser, table: str, field: str, sentinel: str) -> str: ...
    def get(self, *, user: AuditUser, table: str, field: str) -> str: ...
    def of_user(self, user: AuditUser) -> tuple[str, ...]: ...
    def all_sentinels(self) -> tuple[str, ...]: ...
    def keys(self) -> tuple[SentinelKey, ...]: ...
    def carriers_of_user(self, user: AuditUser) -> tuple[SentinelCarrier, ...]: ...
    def owner_of(self, sentinel: str) -> AuditUser: ...
```

`all_sentinels()` rather than `all()` deliberately: no builtin shadowing. ADM registers nothing
(`002.context.md`: "ADM owns no content"), so `of_user("ADM") == ()`.

**The carriers, as they really exist** (decision 14 — the `field` strings below are the exact third
component of `SentinelKey`):

| `table` | `field` | `stored` | Note |
|---|---|---|---|
| `characters` | `name` | yes | |
| `characters` | `sheet` | yes | the persona text |
| `characters` | `system_prompt` | yes | *character configuration is columns on `characters`, not a table* |
| `setups` | `name` | yes | `002.context.md`'s "setup title" |
| `setups` | `description` | yes | `002.context.md`'s "setup text" |
| `sessions` | `system_prompt` | yes | **`schema.sessions` has no content text column** — no `title`, no `partner_label`. This and `session_vec` are the only session-level carriers. |
| `users` | `rp_language` | yes | *user settings are two columns on `users`, not a table* |
| `users` | `preferred_language` | yes | second user-settings column |
| `messages` | `text[partner]` | yes | |
| `messages` | `text[zone]` | yes | |
| `messages` | `text[turn]` | yes | the settled turn head |
| `messages` | `text[buried]` | yes | a row buried under the turn head |
| `messages` | `text[decision]` | yes | |
| `messages` | `text[assistant]` | yes | written by compose from the scripted completion |
| `messages` | `tool_payload[arguments]` | yes | the scripted tool call's `query` — the "tool-call query" sentinel |
| `messages` | `tool_payload[content]` | yes | the "tool-result text" sentinel |
| `translations` | `text` | yes | |
| `memos` | `body[<scope>/<reach>]` x 12 | yes | `<scope>` in `user|character|setup|session`, `<reach>` in `forced|searchable|disabled` |
| `memo_vec` | `embedded_text` | **no** | binary vector; witnessed by row presence / a `memo_fts` `MATCH`, never by substring |
| `session_vec` | `embedded_text` | **no** | same |

Two items in `002.context.md`'s sentinel-field list have **no own key** and must not be looked up:

- **"memo title"** — `memos` has only a `body` column (`schema.py`, memos table: `scope`, `scope_id`,
  `body`, `is_enabled`, `is_forced`, `sort_key`, timestamps). The memo sentinel is `body[...]` alone.
- **"my-search target words"** — not a carrier. My-search's targets *are* the stored sentinels above;
  no separate registry key exists for it.

#### 5. The fake model seam — one atomic installation (decision 7)

```python
ChatRound = Sequence[ChatDelta | BaseException]

@dataclass(frozen=True)
class ChatCall:
    model: str
    messages: tuple[ChatMessage, ...]
    tools: tuple[Mapping[str, object], ...]

class FakeChatClient:                       # satisfies app.services.llm_registry.ChatClientLike
    def __init__(self, rounds: Sequence[ChatRound] = (), *, on_enter: Callable[[], None] | None = None) -> None: ...
    calls: list[ChatCall]
    def chat_stream(self, model: str, messages: Sequence[ChatMessage],
                    tools: Sequence[Mapping[str, object]]) -> AsyncIterator[ChatDelta]: ...

class FakeChatClientFactory:                # satisfies ChatClientFactory = (base_url, api_key, timeout) -> client
    def __init__(self, *, rounds: Sequence[ChatRound] = ()) -> None: ...
    calls: list[tuple[str, str | None, float]]
    clients: list[FakeChatClient]
    def __call__(self, base_url: str, api_key: str | None, timeout_seconds: float) -> FakeChatClient: ...
    @property
    def call_count(self) -> int: ...
    @property
    def chat_calls(self) -> list[ChatCall]: ...          # every ChatCall of every client, in order
    def script(self, *rounds: ChatRound) -> None: ...    # replaces the script; clears nothing recorded
    def script_text(self, text: str) -> None: ...        # one completion round, then end of exchange
    def script_tool_call(self, *, name: str, arguments: str, call_id: str | None = None,
                         then_text: str | None = None) -> None: ...
    def script_failure(self, error: BaseException) -> None: ...   # caller-chosen class AND message (decision 12)

def text_round(text: str) -> ChatRound: ...
def tool_call_round(*, name: str, arguments: str, call_id: str | None = None, index: int = 0) -> ChatRound: ...
def failure_round(error: BaseException) -> ChatRound: ...
```

```python
class ScriptedProbeClient:                  # satisfies LlmClientLike; llm_fakes' probe is always REACHABLE
    def __init__(self, *, dim: int = FAKE_EMBEDDING_DIM, probe_result: ProbeResult | None = None,
                 probe_error: BaseException | None = None, embed_error: BaseException | None = None) -> None: ...
    embed_calls: list[tuple[str, tuple[str, ...]]]
    probe_calls: int
    async def probe(self) -> ProbeResult: ...
    async def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]: ...

class ScriptedProbeFactory:                 # satisfies LlmClientFactory
    def __init__(self, *, dim: int = FAKE_EMBEDDING_DIM, probe_result: ProbeResult | None = None,
                 probe_error: BaseException | None = None, embed_error: BaseException | None = None) -> None: ...
    calls: list[tuple[str, str | None, float]]
    clients: list[ScriptedProbeClient]
    def __call__(self, base_url: str, api_key: str | None, timeout_seconds: float) -> ScriptedProbeClient: ...
    @property
    def call_count(self) -> int: ...
    @property
    def embed_calls(self) -> list[tuple[str, tuple[str, ...]]]: ...
    @property
    def probe_calls(self) -> int: ...

class WebSearchRecorder:                    # the httpx.MockTransport seam of GoogleCustomSearchProvider
    def __init__(self, *, results: Sequence[WebResult] = (), status_code: int = 200,
                 error: BaseException | None = None) -> None: ...
    requests: list[httpx.Request]
    @property
    def transport(self) -> httpx.MockTransport: ...
    @property
    def queries(self) -> list[str]: ...     # the `q` parameter of each recorded request
    def script(self, *results: WebResult) -> None: ...
```

```python
@dataclass
class FakeModelSeam:
    application: FastAPI
    embedding_factory: LlmClientFactory        # installed at app.dependencies.get_llm_client_factory
    chat_factory: FakeChatClientFactory        # installed at app.routers.stream.get_chat_client_factory
    translation_factory: FakeChatClientFactory # installed at app.routers.translation.get_translation_chat_client_factory
    tool_registry: ToolRegistry                # installed at app.routers.stream.get_tool_registry
    web_recorder: WebSearchRecorder            # the transport inside tool_registry["web_search"]'s provider
    def use_embedding_factory(self, factory: LlmClientFactory) -> None: ...   # re-points the live override
    def override_keys(self) -> tuple[Callable[..., Any], ...]: ...            # == FAKE_SEAM_OVERRIDE_KEYS
    def reset_records(self) -> None: ...                                      # clears calls/requests, keeps scripts

@contextmanager
def install_fake_model_seam(
    application: FastAPI,
    settings: Settings,
    *,
    embedding_dim: int = FAKE_EMBEDDING_DIM,
    tool_names: Sequence[str] = (MEMO_SEARCH_NAME, SESSION_SEARCH_NAME, WEB_SEARCH_NAME),
) -> Iterator[FakeModelSeam]: ...
```

**This is the single entry point, and it is atomic.** It replaces **all four** keys of
`FAKE_SEAM_OVERRIDE_KEYS` or none, and removes exactly those four on exit. `audit_world` calls it
**exactly once**; **no later step may set any of those four keys itself** — a half-installed seam
lets the real `app.services.llm.client.LlmClient` run and the suite makes a real network request to
the user's configured server. Later steps re-script through `world.fakes.chat_factory.script_*`,
`world.fakes.translation_factory.script_*`, `world.fakes.web_recorder.script`, and
`world.fakes.use_embedding_factory`.

Two seams are **not** module-level factories and are the reason `get_tool_registry` must be
overridden rather than left alone: the production `MemoSearchTool` / `SessionSearchTool` take their
`client_factory` by **constructor injection** (`client_factory: LlmClientFactory | None = None`,
`timeout_seconds: float | None = None`, both defaulting to the real client), and `WebSearchTool`
takes the **whole provider** as its one required argument. So the registry
`install_fake_model_seam` builds is
`{MEMO_SEARCH_NAME: MemoSearchTool(client_factory=<fake>), SESSION_SEARCH_NAME:
SessionSearchTool(client_factory=<fake>), WEB_SEARCH_NAME:
WebSearchTool(GoogleCustomSearchProvider(<dummy key>, <dummy id>, transport=recorder.transport))}`,
restricted to `tool_names`. Note `conftest.py`'s autouse fixture blanks `SEARCH_CSE_KEY` and
`SEARCH_CSE_ID`, so the production `get_tool_registry` would omit `web_search` entirely; the
override supplies non-blank dummies that never leave the `MockTransport`.

#### 6. Assertions

```python
def assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]: ...
def assert_empty_detail(body: Mapping[str, Any]) -> None: ...
def assert_refusal_identity(foreign: httpx.Response, unknown: httpx.Response, *,
                            status: int, code: str) -> None: ...
def rendered_text(payload: object) -> str: ...
def assert_no_sentinel_of_user(payload: object, *, registry: SentinelRegistry, user: AuditUser,
                               allowed: Iterable[str] = ()) -> None: ...
def assert_no_identifier_of(payload: object, *, content: SeededUserContent,
                            allowed: Iterable[str] = ()) -> None: ...
```

- `assert_envelope` returns the parsed body, so `assert_empty_detail(assert_envelope(r, 404, code))`
  reads as one line (precedent `test_characters_router.py:179`, `test_stream_router.py:259`).
- `assert_refusal_identity` is the `context.md` "refusal identity" in one call: same status, same
  `error.code`, `error.detail == {}`, and **byte-identical JSON body**. Both responses are passed in;
  the expected `status` and `code` come from the step's DoD, never from here.
- `rendered_text(payload)` accepts `httpx.Response`, `str`, `bytes`, `Mapping`, `Sequence` or any
  JSON-able object and returns the one string the two absence assertions search — so
  "in this text/JSON" is one code path and an SSE body, a JSON body and a DB column are all searched
  the same way.
- `allowed=` is the **documented** carve-out channel, and the only one: 004 DoD-6's `tool_args`
  (decision 11) and 005 DoD-1's `translations` / `model_server_id` exclusions (decision 17) pass
  their exclusions here with a comment, rather than weakening the assertion.

#### 7. Log capture (decision 9)

```python
@dataclass(frozen=True)
class CapturedRecord:
    level: str
    name: str | None
    message: str            # record["message"] — the unformatted message
    formatted: str          # str(message) — the sink's rendered line
    extra_repr: str         # repr(record["extra"])
    exception_text: str | None   # repr(record["exception"].value) or None

class LogCapture:
    records: list[CapturedRecord]
    @property
    def texts(self) -> list[str]: ...    # every string of every record, flattened
    def joined(self) -> str: ...         # "\n".join(self.texts)

@contextmanager
def captured_logs(*, logger_names: Sequence[str] = RESTORED_LOGGER_NAMES,
                  restore_stdlib: bool = True) -> Iterator[LogCapture]: ...

@contextmanager
def restored_logging_state(*, logger_names: Sequence[str] = RESTORED_LOGGER_NAMES) -> Iterator[None]: ...
```

`captured_logs` attaches a **level-0 loguru sink** and removes it by id on exit — the precedent is
`tests/test_sync_executor.py:223` `_captured_logs()` (`logger.add(sink, level=0, format="{level}
{name} {message}")`, `finally: logger.remove(handler_id)`), with the same four pieces per record.
Frozen beyond the precedent, because of decision 9: it **snapshots and restores every logger
attribute it touches** — for each name in `logger_names`, the `level`, the `handlers` list, the
`propagate` flag **and the `.filters` list**. No fixture anywhere in the delivered suite restores
`.filters`, and `app/main.py:165` runs `create_app()` at import, so the real `configure_logging` has
already mutated global loguru and stdlib state before any fixture runs. `restore_stdlib=False` is for
a caller that is already inside `restored_logging_state` (step 007, which calls the **real**
`configure_logging` after replacing `sys.stderr`, per `tests/test_logging.py`).

#### 8. The enumeration literal, the route walk, and the unbuilt-surface guard (decision 4)

```python
RouteClass = Literal["public", "self", "registry", "owner", "admin"]

@dataclass(frozen=True)
class EnumeratedRoute:
    row: int                  # the `#` column of context.md's table
    method: str               # upper case
    path: str                 # parameters normalized to `{}`
    route_class: RouteClass
    not_found_code: str | None
    def key(self) -> tuple[str, str]: ...        # (method, path)

ENUMERATED_ROUTES: Final[tuple[EnumeratedRoute, ...]]        # exactly 72 entries; rows 5 and 74 excluded
ENUMERATED_OPERATIONS: Final[frozenset[tuple[str, str]]]     # {r.key() for r in ENUMERATED_ROUTES}
EXCLUDED_ROWS: Final[Mapping[int, str]]                      # {5: <reason>, 74: <reason>} — by name, with the reason inline

@dataclass(frozen=True)
class UnbuiltSurface:
    row: int
    description: str
    path_pattern: str                 # re.search, case-insensitive, against each normalized path
    allowed_paths: frozenset[str]     # registered paths that match and are legitimately built

UNBUILT_SURFACES: Final[tuple[UnbuiltSurface, ...]]          # one entry for row 5, one for row 74
```

```python
def api_routes(application: FastAPI) -> tuple[APIRoute, ...]: ...
def normalize_path(path: str) -> str: ...
def route_operations(application: FastAPI) -> frozenset[tuple[str, str]]: ...
def fill_path(path: str, *, unknown_id: str = UNKNOWN_ID,
              table_name: str = EXISTING_TABLE_NAME) -> str: ...
```

- `api_routes` is the **existing in-suite recursive walk**, not `isinstance(r, APIRoute)` over
  `app.routes`. Under the installed FastAPI **0.141.1** `app.routes` holds **no `APIRoute` at all** —
  four plain documentation `Route`s plus fifteen `_IncludedRouter` wrappers — so
  `002.context.md`'s stated "iterate FastAPI's `APIRoute`" would compare an **empty set** against the
  table and pass against nothing. The frozen shape is the delivered precedent
  `tests/test_configuration_router.py:1048` `_ordered_api_routes(routes, found, seen)` and
  `tests/test_search_router.py:1041` `_api_routes(routes, found, seen)`, both
  `(routes: Any, found: list[APIRoute], seen: set[int]) -> None`, depth-first through
  `getattr(route, "routes")`, `getattr(route.router, "routes")` and
  `getattr(route.original_router, "routes")`. `api_routes` wraps that private recursion and returns
  the collected tuple; it **raises `AssertionError` when the walk found nothing** ("the walk found no
  API routes at all", as `test_search_router.py:1064` already does), and so does
  `route_operations` — an inventory guard that can silently iterate an empty set is worse than none.
- `normalize_path` rewrites every `{param}` / `{param:type}` segment to `{}`. The registered
  parameter names are `{character_id}`, `{setup_id}`, `{session_id}`, `{message_id}`, `{memo_id}`,
  `{user_id}`, `{server_id}`, `{table_name}`; no route uses a typed segment.
- `route_operations` yields `(METHOD, normalized path)` for every walked `APIRoute` and every method
  on it, **excluding `HEAD`**. FastAPI's four documentation routes are not `APIRoute`s and so never
  appear.
- `fill_path` substitutes `UNKNOWN_ID` into every `{...}` segment **except** `{table_name}`, which
  takes `EXISTING_TABLE_NAME`. It is applied to the **registered** path (named parameters), not the
  normalized one.

#### 9. The world builder

```python
@dataclass(frozen=True)
class AuditWorld:
    settings: Settings
    engine: Engine
    application: FastAPI
    clients: AuditClients
    adm: AuditIdentity
    a: SeededUserContent
    b: SeededUserContent
    models: SeededModels
    sentinels: SentinelRegistry
    fakes: FakeModelSeam
    def content_of(self, user: AuditUser) -> SeededUserContent: ...   # "A" | "B"; "ADM" owns no content
    def identity_of(self, user: AuditUser) -> AuditIdentity: ...

@contextmanager
def audit_world(
    settings: Settings,
    engine: Engine,
    *,
    real_logging: bool = False,
    embedding_dim: int = FAKE_EMBEDDING_DIM,
) -> Iterator[AuditWorld]: ...
```

`audit_world` is the single entry point for steps 003..007; each step module declares its own thin
fixture around it over `conftest.py`'s `db_settings` / `db_engine` (the suite's per-module fixture
precedent). What the signature fixes:

- `settings` / `engine` are the per-test pair from `conftest.py`. The application is the **real**
  one: `create_app()` with `application.dependency_overrides[get_settings] = lambda: settings`
  (precedent `test_characters_router.py:115`). Overrides are cleared on exit.
- **`real_logging` is the caller's choice**, as the step file requires: `False` (the default) replaces
  `app.main.configure_logging` with a no-op for the duration of the `create_app()` call, exactly as
  the 28 delivered router-test modules do; `True` lets the real `configure_logging` run, which is
  what step 007 needs. Nothing else about the application differs between the two.
- The seam is installed **before any seeding** and is `world.fakes`.
- ADM is bootstrapped through `POST /api/bootstrap/create` (201, sets the `rphelper_session` cookie),
  and A and B are created through `POST /api/admin/users` with `{"username", "password", "role":
  "roleplayer"}` (201) then logged in through `POST /api/auth/login` (200). Roleplayers are never
  raw-inserted and nothing is ever raw-inserted into a user-content table.

**Forced seeding order (decision 13).** A wrong order produces 409s that would read as findings, so
the order is part of the frozen contract:

1. bootstrap ADM, log ADM in;
2. `POST /api/admin/llm-servers`, then `POST /api/admin/llm-servers/{id}/models` with **both** model
   names — **enable the models before creating any session**, because a session captures its model at
   creation and a session created earlier composes to 409 `model_not_chosen`;
3. `POST /api/admin/llm-servers/{id}/embedding-model` — **designate only after enabling**
   (`validate_embedding_model` rejects an unenabled model). Designation runs through the fake
   factory and makes **no network request**;
4. **only then** any memo create, character-sheet `PATCH` or setup-description `PATCH`: those embed
   **strictly** and answer 409 `no_embedding_model` without a designation;
5. create A and B, log each in, then per user: character -> character configuration -> setup ->
   sessions -> messages/settle/compose/translation -> memos -> memo order -> user settings;
6. archive the archived session **last**.

Settle, reopen, partner-file and record-edit never fail on a missing designation — they skip vectors
silently and return `search_coverage_incomplete: true` — so a world built in the wrong order has no
`session_vec` rows and DoD-4 would be the only thing to notice.

#### 10. Task 2 — the exact method of every `†` enumeration row, confirmed from the built routers

Confirmed by reading the decorators, not by trusting the harvest. Each `†` path has exactly one
registered method; no sibling method shares a path. Prefixes: `characters.py:62`
`APIRouter(prefix="/api/characters")`, `admin_users.py:54` `prefix="/api/admin/users"`,
`admin_llm.py:75` `prefix="/api/admin/llm-servers"`; `setups.py` and `sessions.py` declare full paths
on each decorator.

| Row | Path | **Method** | Declared at |
|---|---|---|---|
| 21 | `/api/characters/{}/archive` | **POST** | `app/routers/characters.py:147` `archive_own_character`, 200 |
| 22 | `/api/characters/{}/restore` | **POST** | `app/routers/characters.py:158` `restore_own_character`, 200 |
| 27 | `/api/setups/{}/archive` | **POST** | `app/routers/setups.py:157` `archive_own_setup`, 200 |
| 28 | `/api/setups/{}/restore` | **POST** | `app/routers/setups.py:168` `restore_own_setup`, 200 |
| 32 | `/api/sessions/{}/archive` | **POST** | `app/routers/sessions.py:177` `archive_own_session`, 200 |
| 33 | `/api/sessions/{}/restore` | **POST** | `app/routers/sessions.py:188` `restore_own_session`, 200 |
| 56 | `/api/admin/users/{}/disable` | **POST** | `app/routers/admin_users.py:83` `disable_account`, 200 |
| 57 | `/api/admin/users/{}/enable` | **POST** | `app/routers/admin_users.py:93` `enable_account`, 200 |
| 58 | `/api/admin/users/{}/password` | **POST** | `app/routers/admin_users.py:103` `set_account_password`, 200 |
| 59 | `/api/admin/users/{}/role` | **POST** | `app/routers/admin_users.py:114` `set_account_role`, 200 |
| 64 | `/api/admin/llm-servers/{}/test` | **POST** | `app/routers/admin_llm.py:140` `run_connection_test`, 200 |
| 65 | `/api/admin/llm-servers/{}/available-models` | **GET** | `app/routers/admin_llm.py:160` `list_llm_server_available_models`, 200 |
| 66 | `/api/admin/llm-servers/{}/models` | **POST** | `app/routers/admin_llm.py:174` `set_llm_server_enabled_models`, 200 |

**No disagreement with harvest Report 1 §C13**: twelve POST, one GET (row 65), identical row by row.
The class and the expected outcome of each row stay `context.md`'s; only the method is recorded here.
Row 47's 404 code is `message_not_found` (decision 6) and `EnumeratedRoute.not_found_code` carries it
like any other.

#### 11. Task 3 — rows 5 and 74 **cannot be frozen**, and the recorded resolution

`002.context.md` task 3 names `docs/plans/fast/003.*/plan.md` and `docs/plans/fast/002.*/plan.md`.
**Confirmed by listing the folders: those files do not exist.** All three `fast/` folders hold
**only `brief.md`** — `fast/001.dev-and-container-harness/`, `fast/002.vector-index-rebuild/`,
`fast/003.bootstrap-from-export/` — so both features are unplanned and therefore unbuilt, and there
is no `status.md` and no `## Skeleton` to read either. **No method, path, payload or response is
invented for either row.**

Orientation decision 1 is the resolution, and it binds the test-coder:

- Rows **5** (fast/003 bootstrap-from-export, `public`, swept by 005) and **74** (fast/002
  vector-rebuild, `admin`, swept by 006) are **excluded from `ENUMERATED_ROUTES` by name, through
  `EXCLUDED_ROWS`, with this reason recorded inline**. They are never silently dropped.
- **DoD-1 is not loosened.** It stays an exact two-way set comparison —
  `route_operations(application) == ENUMERATED_OPERATIONS` — over the remaining **72** rows, in both
  directions, so an unclassified route is still a finding and a table row with no route is still a
  finding. No subset check.
- `UNBUILT_SURFACES` arms the absence. For row 74 the pattern matches a rebuild/reindex/vector shape
  and `allowed_paths` is **empty**: nothing registered matches, and `app/routers/admin_db.py:24`'s own
  module docstring states there is "**no rebuild route** anywhere on this router". For row 5 the
  pattern matches a bootstrap-from-export/restore shape and `allowed_paths` is exactly
  `{"/api/bootstrap/create"}` — row 2, the one built bootstrap route. The guard asserts every matching
  registered path is in `allowed_paths`; if either surface ever lands, it fails and 032's table must be
  amended before the route ships. The only paths containing `vector`/`embedding` today are
  `/api/admin/llm-servers/{}/embedding-model` (POST designate, DELETE clear — rows 67 and 68).
- `context.md`'s "the table names a route that does not exist => `SPEC`" is **not** triggered: the
  table already marks both rows `_TBD`, the owning features were never planned, and the cause is known
  exactly.

## Tests

### Step 001 — tests (2026-10-06)

- `backend/tests/test_logging_redaction.py` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-6, DoD-7
  — access-log query redaction, traceback frame-local redaction, and engine parameter hiding.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓,
  DoD-8 [manual/live, no test].

| DoD | Test function | Asserts | Expected at red gate |
|---|---|---|---|
| 1 | `test_access_query_sentinel_reaches_no_sink__S032_001_DoD1` | a `uvicorn.access` record whose target carries `?q=<sentinel>` leaves the sentinel in none of the three sinks (captured stderr, the `tmp_path` log file, a level-0 loguru sink), with the path asserted present in all three as the positive control | **RED** (sentinel present today) |
| 1 | `test_redaction_filter_is_installed_once_after_two_calls__S032_001_DoD1` | after two `configure_logging` calls, `logging.getLogger("uvicorn.access").filters` holds **exactly one** `AccessQueryRedactionFilter` (frozen idempotence contract / decision 9) | **RED** (zero filters today) |
| 2 | `test_redacted_access_line_still_names_method_path_and_status__S032_001_DoD2` | the line written to console and file still contains the method, `/api/search` and `200`, and contains no `/api/search?` — the path survives, the query does not | **RED** (`/api/search?` present today) |
| 3 | `test_access_line_without_a_query_string_is_unchanged__S032_001_DoD3` | a target with no query string renders the whole uvicorn-format line byte-for-byte unchanged in all three sinks | **GREEN** (expected and accepted: it asserts the *absence* of a rewrite; it is the guard against over-rewriting, not a vacuous pass) |
| 4 | `test_traceback_keeps_the_frame_and_drops_frame_locals__S032_001_DoD4` | a logged traceback shows `Traceback`, the marker message and the frame name `_raise_from_a_frame_holding_a_sentinel` in console and file, but not the runtime-built sentinel held by that frame's local | **RED** (console sink's `diagnose=True` prints the local today) |
| 5 | `test_sql_log_records_carry_no_bound_parameter_value__S032_001_DoD5` | with `sqlalchemy.engine` lowered to INFO and a level-0 sink attached, an INSERT through a factory engine on a scratch `tmp_path` database with the sentinel as a bound parameter leaves no captured record containing it; the table name is asserted present as the positive control | **RED** (parameters rendered today) |
| 6 | `test_constraint_violation_string_form_carries_no_bound_value__S032_001_DoD6` | a UNIQUE violation whose bound parameter is a sentinel has `str(IntegrityError)` free of the sentinel while still naming the statement (the placeholder's wording is deliberately not pinned) | **RED** (`[parameters: (...)]` renders the value today) |
| 7 | `test_factory_engine_reports_hidden_parameters__S032_001_DoD7` | `get_engine(settings).hide_parameters is True` | **RED** (`False` today) |

State hygiene (decision 9): an autouse `restore_logging_state` fixture snapshots and restores
`level`, `handlers`, `propagate` **and `.filters`** for `""`, `uvicorn`, `uvicorn.access`,
`uvicorn.error`, `sqlalchemy`, `sqlalchemy.engine`, `httpx`, and resets loguru to one stderr sink
on both sides; every capture sink is removed by id; an autouse fixture calls `dispose_engines()`
after each test. Settings are built with `Settings(_env_file=None)` and all of
`RPHELPER_DATA_DIR`, `RPHELPER_DB_FILENAME`, `RPHELPER_LOG_FILE_PATH` (plus both sink levels)
pointed at `tmp_path`, so `backend/.env` and the real database are never opened.

### Step 002 — tests (2026-10-06)

- `backend/tests/privacy_audit_support.py` — the shared support module (not collected; no `test_`
  prefix). Imported by steps 003..007 as `from tests.privacy_audit_support import ...`.
- `backend/tests/test_privacy_audit_routes.py` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-6 —
  the route-classification guard, the anon and role gates, the world's anti-vacuity gate, the
  positive control and sentinel hygiene.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓ (no `[manual/live]` item in this
  step).

#### Per-DoD test inventory

| DoD | Test function | Asserts | Expected at the gate |
|---|---|---|---|
| 1 | `test_app_routes_and_the_enumeration_agree_exactly__S032_002_DoD1` | `route_operations(app) == ENUMERATED_OPERATIONS` as **exact two-way set equality** over the 72 rows; `EXCLUDED_ROWS == {5, 74}` each with a non-empty reason; the failure message names every unclassified route **and** every table row with no route | **GREEN** (harvest reconciled 72 against 72 with zero differences) |
| 1 | `test_no_unbuilt_surface_has_landed__S032_002_DoD1` | every registered normalized path matching a bootstrap-from-export shape is in `{"/api/bootstrap/create"}`, and none matches a rebuild/reindex/vector shape | **GREEN** (neither surface is built) |
| 1 | `test_the_route_walk_and_path_helpers_behave__S032_002_DoD1` | the walk really reaches the tree (`GET /api/health`, `GET /api/characters/{}` present, no `HEAD`), `normalize_path` collapses `{p}` and `{p:type}`, `fill_path` substitutes `UNKNOWN_ID` everywhere but `{table_name}`, and the unknown id really answers 404 `character_not_found` with `detail == {}` | **GREEN** |
| 2 | `test_every_non_public_route_refuses_anon_with_401__S032_002_DoD2` | all 68 non-`public` rows answer anon **401 `not_authenticated`** with `detail == {}`, unknown ids substituted, `{}` body on POST/PUT/PATCH; every `public` row skipped; the checked count is asserted | **GREEN** |
| 3 | `test_every_admin_route_refuses_a_roleplayer_with_403__S032_002_DoD3` | all 20 `admin` rows answer A **403 `insufficient_role`** with `detail == {}` (cites **US-084.AC-1**) | **GREEN** |
| 4 | `test_every_coverage_table_holds_a_row_for_each_user__S032_002_DoD4` | `users`, `characters`, `setups`, `sessions`, `messages`, `translations`, `memos` each hold a row owned by A and by B; `memo_vec` / `session_vec` hold a row keyed on each user's own ids; `memo_fts` / `message_fts` index each user's rows (witnessed by `MATCH`, never a plain `SELECT`) | **GREEN** |
| 4 | `test_every_registered_sentinel_is_stored_somewhere__S032_002_DoD4` | every `stored=True` carrier's sentinel is found by a `LIKE` on that table.column **under that user's owner predicate**; the only `stored=False` carriers are exactly the two vector stores; `of_user("ADM") == ()` | **GREEN** |
| 4 | `test_the_world_installs_all_four_model_seams__S032_002_DoD4` | all four `FAKE_SEAM_OVERRIDE_KEYS` are present in `dependency_overrides`, compose ran for both users, both translations ran, and **no web-search request was made** | **GREEN** |
| 5 | `test_b_reads_every_own_sentinel_back_through_own_routes__S032_002_DoD5` | B retrieves 27 of its 31 sentinels through its own character / character-configuration / setup / session / session-configuration / settings / entries / zone / discussion / memos-per-scope / memo-chain reads; the 4 carriers with no read surface are named with their reason and the two sets are asserted to partition the carrier set | **GREEN** |
| 5 | `test_my_search_returns_bs_own_material_for_bs_own_sentinels__S032_002_DoD5` | `GET /api/search?q=<B's character-name sentinel>` returns B's character; `q=<B's session/searchable memo sentinel>` returns that memo | **GREEN** |
| 6 | `test_sentinels_are_unique_non_nested_and_absent_from_administrative_data__S032_002_DoD6` | 62 sentinels, all distinct, each a single lowercase alphanumeric token, **none a substring of another**, none inside either username, the admin username, the server name or either model name — plus a non-vacuity check that those administrative strings really are the instance's | **GREEN** |

Sentinel design that makes DoD-6 structural rather than accidental: every sentinel is
`"sntl" + <a|b> + <10-char carrier tag padded with x>`, so **all 62 have the same length**; equal-length
distinct strings cannot contain one another, and no administrative name contains `sntl`.

#### The support module's delivered surface (bind steps 003..007 to this)

Everything frozen in `## Skeleton` → "Step 002 — frozen interface" is delivered with the frozen name,
signature and types: `UNKNOWN_ID`, `EXISTING_TABLE_NAME`, `FAKE_SEAM_OVERRIDE_KEYS` (the four keys, in
the frozen order), `FAKE_SERVER_BASE_URL`, `FAKE_CHAT_MODEL_NAME`, `FAKE_EMBEDDING_MODEL_NAME`,
`DERIVED_STORE_TABLES`, `RESTORED_LOGGER_NAMES`; `AuditUser` / `AuditIdentity` / `AuditClients.of`;
`SeededMessages` / `SeededMemos` (the 12-combination cross product) / `SeededUserContent` /
`SeededModels`; `SentinelKey` / `SentinelCarrier` / `SENTINEL_CARRIERS` (31 carriers, exactly the
decision-14/30/31/32 table) / `SentinelRegistry` with all seven methods; `ChatRound` / `ChatCall` /
`FakeChatClient` / `FakeChatClientFactory` (`script`, `script_text`, `script_tool_call`,
`script_failure`, `chat_calls`, `call_count`) / `text_round` / `tool_call_round` / `failure_round` /
`ScriptedProbeClient` / `ScriptedProbeFactory` / `WebSearchRecorder` / `FakeModelSeam` /
`install_fake_model_seam`; `assert_envelope` / `assert_empty_detail` / `assert_refusal_identity` /
`rendered_text` / `assert_no_sentinel_of_user` / `assert_no_identifier_of`; `CapturedRecord` /
`LogCapture` / `captured_logs` / `restored_logging_state`; `RouteClass` / `EnumeratedRoute` /
`ENUMERATED_ROUTES` (72) / `ENUMERATED_OPERATIONS` / `EXCLUDED_ROWS` / `UnbuiltSurface` /
`UNBUILT_SURFACES`; `api_routes` / `normalize_path` / `route_operations` / `fill_path`; `AuditWorld` /
`audit_world`.

**Additions beyond the frozen record** (additive only; nothing frozen was renamed or re-shaped):

- `MEMO_SEARCH_NAME`, `SESSION_SEARCH_NAME`, `WEB_SEARCH_NAME` — the record's
  `install_fake_model_seam` default argument names them but its constants table did not list them.
- `MEMO_SCOPES`, `MEMO_REACHES` — the four scopes and three reaches as tuples, so a later step can
  iterate the 12 combinations without re-writing them.
- `memo_carrier_field(scope, reach)` → `"body[<scope>/<reach>]"` — the exact third component of a memo
  `SentinelKey`, so no step has to build that string by hand.
- `registered_paths_by_operation(application)` → `(METHOD, normalized path) -> registered path`.
  Needed because `fill_path` applies to the **registered** path (named parameters) while the
  enumeration is keyed on the normalized one.
- `FAKE_SERVER_NAME`, `LOGIN_PATH`, `BOOTSTRAP_PATH`, `ADMIN_USERS_PATH`, `ADMIN_SERVERS_PATH`,
  `COMPOSE_TIMEOUT_SECONDS`, `sentinel_for(user, table, field)`.

**Divergences from the frozen record, with their reasons** — two, both inside the world builder's
behaviour, neither touching a frozen signature:

1. **Seeding order: memos are created before the compose exchange**, not after as step 9's list
   ("messages/settle/compose/translation -> memos -> memo order") has it. Reason: the carrier
   `messages.tool_payload[content]` ("the tool-result text") can only be stored if the scripted
   `memo_search` call finds something, and the memo_search tool reaches only *searchable chain*
   memos. With memos created after compose the tool answers "No matching notes." and that sentinel
   would be stored nowhere, failing DoD-4 for a reason that is a test defect, not a leak. Every
   validation constraint decision 13 exists to protect is still honoured: the models are enabled and
   the embedding model designated before any memo create, the memo `scope_id` parents already exist,
   and the archived session is still archived last.
2. **The tool-result sentinel is planted in the searchable session-scope memo body**, which is the
   text `memo_search` echoes into `tool_payload.content`. Reason: the tool content is derived from
   the memos the tool finds, so a free-standing token could not appear there, and the web-search
   route to a tool result was rejected deliberately — it would have made the world depend on the
   Google response shape, which no frozen record or plan document states. The `web_search` fake is
   still installed (the seam is atomic) and the world asserts it was never called. Consequently the
   `memo_vec` carrier's token is likewise planted in the searchable user-scope memo body, which is
   the text embedded into `memo_vec`, and the `session_vec` carrier's token in the settled partner
   block, which is part of the composed session text.

Mechanics: `audit_world` is the only entry point; it calls `install_fake_model_seam` **exactly once**
and that call sets all four keys or none (it raises if any of the four is already overridden).
Settings are the per-test `db_settings`; nothing is raw-inserted into any table; `backend/.env` and
the real database are never opened. The compose POST runs on a worker thread with a 30 s bound,
following `test_compose_route.py`.

**`ruff check` was not run: the Bash tool is disabled in this session**, so linting both files is left
to the gate. Both were written to the configured rules by inspection (line-length 120, `E,F,I,B,UP,W`,
isort grouping and `order-by-type` ordering matching `test_search_hybrid.py`'s precedent) and both are
fully annotated even though `mypy`'s target is `app` only.

### Step 003 — tests (2026-10-06)

- `backend/tests/test_privacy_audit_owner_sweep.py` — covers DoD-1..DoD-11 — every `owner` row of the
  enumeration refuses a foreign id with refusal identity (as A **and** as ADM), B reads back unchanged
  after every refused write, and no list / zone / entry / memo / self surface of one roleplayer carries
  the other's material.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓ (no `[manual/live]` item in this step).

**Four test functions, four world builds** — deliberately few, per the performance note: the world is
~120 requests plus two composes and `conftest.py`'s `db_settings` is function-scoped, so each function
builds it once and loops inside. Per-clause granularity lives in the failure messages (each names the
enumeration row, the method, the path and the acting identity), not in the number of builds. The module
binds to step 002's delivered surface only (`audit_world` with the default `real_logging=False`,
`AuditClients.of`, `ENUMERATED_ROUTES` / `EnumeratedRoute`, `UNKNOWN_ID`, `fill_path`,
`registered_paths_by_operation`, `memo_carrier_field`, `MEMO_REACHES`, `SentinelRegistry`,
`assert_envelope` / `assert_empty_detail` / `assert_refusal_identity` / `rendered_text` /
`assert_no_sentinel_of_user` / `assert_no_identifier_of`) and **installs no fake seam itself** — none of
the four `FAKE_SEAM_OVERRIDE_KEYS` is touched anywhere in the file.

| DoD | Test function | Cases | Asserts | Expected at the gate |
|---|---|---|---|---|
| 1 | `test_every_owner_row_refuses_a_foreign_id_and_b_is_untouched__S032_003_DoD1_DoD2_DoD3` | **35** owner rows (table rows 19..53, count asserted) | for each row, A's request with B's id for the path's leading resource answers **404 with the row's `not_found_code` taken from `ENUMERATED_ROUTES`**, `detail == {}`, and a body **identical to A's unknown-id answer** (`assert_refusal_identity`). The 12 write rows send a body valid for A's own resource carrying an A sentinel + a probe token; the 10 bodyless writes are declared and the partition (12 + 10 + 13 reads = 35) is asserted, so a row can never silently lose its body and refuse with a 422 instead. Row 47 expects `message_not_found` (decision 6) and row 53 sends a **real session export of A's own session**, because the import route validates the envelope before resolving the character. Problems are collected, not raised, so one leak cannot hide another | **GREEN** (audit) |
| 2 | same function | 23 B-side reads × 2 | B's own characters / sessions (both views) / character / character-configuration / setups / per-character sessions / setup / three sessions / session-configuration / entries / zone / memo-chain / discussion / four memo lists / settings / me are **equal before and after** both sweeps, excluding nothing (no timestamp moves); neither probe token nor any A sentinel reaches any of them | **GREEN** (audit) |
| 3 | same function | the same **35** rows as ADM | ADM gets the identical refusal identity — an admin is **not** a super-reader of user content (the gap `003.context.md` records as untested by any feature) | **GREEN** (audit) |
| 4 | `test_as_own_surfaces_carry_no_b_material__S032_003_DoD4_DoD10_DoD11` | 15 list/read surfaces | each of A's characters/sessions (working **and** `include_archived`), per-character setups and sessions (both views), the memo list at each of A's four scopes, A's entries, zone and memo-chain carries **no B sentinel and no B id**; positive controls per surface: A's own character/setup/session ids and name sentinels present, the archived session absent from the working view and present in the archived view, all three reaches of A's memos present at every scope, A's forced memo present at all four chain levels | **GREEN** (audit) |
| 10 | same function | 3 reads + 1 write | `GET /api/me`, `/api/me/settings`, `/api/models` carry no B sentinel and no B id; `PATCH /api/me/settings` by A takes effect on A (positive control: the response equals the two probe values) and leaves B's `GET /api/me/settings` byte-identical | **GREEN** (audit) |
| 11 | same function | A's full visible message set | the walk collects **entries + zone + the discussion of every settled entry** for every one of A's sessions, so buried tool rows are included. Positive controls: A's own tool row and a `role == "tool"` row are reachable that way, and **B's own tool row is likewise reachable through B's own surfaces** — so the absence cannot pass vacuously. Then: B's tool row id is absent, A's visible id set is disjoint from every B id, and every row A sees belongs to one of A's sessions | **GREEN** (audit) |
| 5 | `test_memo_scope_crossing_is_refused_and_changes_nothing__S032_003_DoD5_DoD6_DoD7` | 4 scopes | `character` / `setup` / `session` with B's id answer 404 `character_not_found` / `setup_not_found` / `session_not_found` with refusal identity against the unknown id, with B's own list at the same scope id as the positive control. **The `user` scope asserts decision 23's narrowing**: the response is byte-equal to A's `scope=user` answer with no `scope_id`, holds exactly A's three user memos (positive control), holds **no B memo** and does not echo B's user id as `scope_id` | **GREEN** (audit) |
| 6 | same function | 4 creates | `POST /api/memos` with B's character / setup / session `scope_id` answers **404** with refusal identity (decision 15's first branch). The `user` scope drops `scope_id`, so that create is a 201 **owned by A** with `scope_id: null`, and the disjunction's second branch is asserted too: B's four memo lists and B's memo-chain are unchanged, and neither the new memo id nor the probe text appears in them — so the clause stays armed if the behaviour ever changes | **GREEN** (audit) |
| 7 | same function | 2 refused + 1 accepted | an order mixing A's and B's session-scope memo ids, and an order of B's ids only, both answer **409 `memo_order_mismatch`**; A's and B's session-level memo lists are byte-equal before and after; a valid reorder of A's own level then succeeds (positive control) and still leaves B's order untouched. The refusal is asserted to carry no B **sentinel**; B **ids** are deliberately not asserted absent, since A supplied them in the request itself (cf. decision 11) | **GREEN** (audit) |
| 8 | `test_foreign_setup_and_foreign_compose_are_refused__S032_003_DoD8_DoD9` | 1 refused + 1 unknown + 1 accepted | `POST /api/characters/{A}/sessions` with B's `setup_id` **and an `opening_message`** answers 404 `setup_not_found`, `detail == {}`, identical to the unknown-setup answer; A's session list (archived view) and A's full visible message set are byte-equal before and after, and the probe reaches neither A's nor B's messages — so no session and no opening message were written. The same call with A's own setup is accepted 201 with its opening message (positive control: the refusal is the owner predicate, not a rejected body) | **GREEN** (audit) |
| 9 | same function | 1 refused + 1 unknown | `POST /api/sessions/{B}/zone/compose` by A answers **404 `session_not_found` as JSON**: no `text/event-stream` content type, no `data:` in the body, top-level key set exactly `{"error"}`, `detail == {}`, identical to the unknown-session answer. B's visible messages and B's zone are byte-equal before and after. The chat fake records **no call of its own** — `call_count > 0` is asserted **first** (the world's own composes did reach the fake, so the clause cannot pass because the fake never records), then `reset_records()`, then the factory-call count and the `chat_calls` length are asserted **unchanged across the refused compose**. A delta rather than an absolute zero, so the clause asserts "no model call" and not how much `reset_records` happens to clear | **GREEN** (audit) |

Resolutions and narrowings applied, each from a recorded decision rather than from code:

1. **Row 47's code** is `message_not_found` (decision 6), taken from `EnumeratedRoute.not_found_code`; the
   test additionally cross-checks the literal against the table's per-resource mapping, so a drift
   between the two is reported as its own problem rather than silently changing the expectation.
2. **DoD-5's `user` scope** narrows to its operative clause "never a B memo" (decision 23); the other
   three scopes keep DoD-5's literal wording (404).
3. **DoD-6** resolves to its first branch for the three parented scopes (decision 15); the `user` scope
   exercises the second branch, which keeps the whole disjunction armed.
4. **Row 30's second case** is DoD-8, not part of the DoD-1 sweep; the sweep uses row 30's first case
   (B's character ⇒ `character_not_found`).
5. **No inconsistent-owner row is seeded** — `PATCH /api/messages/{}` is swept through the API with B's
   real message id only, per `context.md` "Known risks".
6. **Archive is not destruction (R6)**: B's archived session is read back through `GET /api/sessions/{id}`
   and through the `include_archived` views in the DoD-2 snapshot, so an archived resource is still
   proved owned.
7. **One reporting caveat for the verifier**: DoD-1, DoD-2 and DoD-3 share one test function and one
   aggregated assertion, so all three clauses' problems are reported together in a single failure
   message (each line names the row, method, path and actor). DoD-4/10/11, DoD-5/6/7 and DoD-8/9
   likewise share a function each; their assertions are separate and name their clause.

**`ruff check` was not run from this session either — no shell tool was available to this agent**, so
linting is left to the gate. The file was written to the configured rules by inspection (line length
≤ 120, `E,F,I,B,UP,W`, isort `order-by-type` ordering in the one `from tests.privacy_audit_support
import (...)` block, no `str.format` so `UP032` cannot fire) and is fully annotated even though
`mypy`'s target is `app` only.

### Step 004 — tests (2026-10-06)

- `backend/tests/test_privacy_audit_search_tools.py` — covers DoD-1..DoD-10 — my-search, the three
  hybrid-port variants, 026/027's search services, the three tool adapters, the tool scope, an
  end-to-end compose with scripted B-naming tool calls, the outbound web-search request, context
  assembly, and the `memo_vec` / `session_vec` / FTS write paths.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓ (no `[manual/live]` item in this step).

**Five test functions, five world builds.** Four of them batch several clauses into one build, per the
performance note (the world is ~120 requests plus two composes and `conftest.py`'s `db_settings` is
function-scoped); per-clause granularity lives in the failure messages, which name the service, the
variant and the ids. The fifth build exists only to isolate the decision-19 pin, whose **expected
pre-fix failure must not be mistaken for a DoD-9/DoD-10 route failure**. The module binds to step
002's delivered surface only (`audit_world` with the default `real_logging=False`, `AuditClients`,
`SentinelRegistry` via `world.sentinels`, `MEMO_SCOPES` / `MEMO_REACHES`, `memo_carrier_field`,
`UNKNOWN_ID`, `COMPOSE_TIMEOUT_SECONDS`, `tool_call_round` / `text_round`,
`world.fakes.chat_factory` / `.web_recorder` / `.embedding_factory` / `.tool_registry`,
`assert_envelope`, `assert_no_sentinel_of_user`, `assert_no_identifier_of`, `rendered_text`) and
**installs no fake seam itself** — none of the four `FAKE_SEAM_OVERRIDE_KEYS` is touched anywhere in
the file, so no network request is possible.

| DoD | Test function | Cases | Asserts | Expected at the gate |
|---|---|---|---|---|
| 1 | `test_my_search_reaches_no_other_users_material__S032_004_DoD1` | **21** searchable B sentinels × 2 requests | for each, A's `GET /api/search?q=<B sentinel>` answers 200 with exactly the five group keys and **no B id and no B sentinel** in any group; B's identical request returns the sentinel's own item in the expected group (positive control). The 21 targets are only the sentinels my-search can reach: `characters.name`/`sheet`, `setups.name`/`description` (LIKE), the three settled record texts plus the `session_vec` carrier (FTS over settled unburied rows), and all twelve memo bodies plus the `memo_vec` carrier (every reach — R3). Problems are collected, not raised, so one leak cannot hide another | **GREEN** (audit) |
| 2 | `test_search_services_scope_every_read_to_the_caller__S032_004_DoD2_DoD3` | 3 variants × 2 user ids | `search(...)` with `MemoSearchScope` / `SessionSearchScope` / `EntrySearchScope` at A's user id and a B-targeting query returns **no** hit id belonging to B and no B sentinel in any hit field; the same call at B's user id returns the targeted row (positive control). Limit 50 = the port's own arm depth, so an absence is not an artefact of a small limit | **GREEN** (audit) |
| 3 | same function | 3 services × 2 scopes | `search_memos` with A's scope, `search_sessions` with A's scope and `list_session_excerpts(A, [B session])` return no B memo, session or excerpt; B's own calls return B's searchable session-scope memo, B's past session and an excerpt **carrying B's settled partner sentinel** (so the excerpt absence cannot pass vacuously) | **GREEN** (audit) |
| 4 | `test_tools_and_context_never_cross_the_owner_boundary__S032_004_DoD4_DoD5_DoD6_DoD7_DoD8` | 2 adapters × 2 scopes | `memo_search` and `session_search` adapters (from the world's injected registry, awaited through `run`) given the scope built from **A's** session and arguments that add B's user, session, character and setup ids **as extra keys** plus a B-targeting query return no B sentinel and no B id in `content` or `summary`; the same adapters with a scope built from B's own session and the *same* arguments do return B's material | **GREEN** (audit) |
| 5 | same function | 1 foreign + 1 unknown + 1 accepted | `build_tool_scope(conn, A, B's session)` raises `SessionNotFoundError` with `code == "session_not_found"`, identically to the unknown id, and **returns no scope**; A's own session does produce one whose four fields are exactly A's ids (positive control) | **GREEN** (audit) |
| 6 | same function | 1 compose, 2 scripted calls, wire **and** stored rows | A composes in A's session while the fake model issues `memo_search` then `session_search` calls whose arguments name B's user/session/character/setup ids and two B sentinels. Every new zone tool row and the assistant row carry no B sentinel and no B id — **with `tool_args` excluded and pinned by exact equality** to the scripted literal (decision 11). The stored rows are swept too: `tool_payload.content` never reaches the wire, so it is checked in the database, with the raw `arguments` string pinned by the same exact equality. The seeded tool row of A's session is buried, so the "new rows" sets are computed by id difference from both a zone snapshot and a stored-tool-id snapshot | **GREEN** (audit) |
| 7 | same function | 1 compose, 1 captured request | the recorder's request list is asserted **empty first** (the world asserts `web_search` was never called during seeding), then exactly one request is captured at the `httpx.MockTransport`; `url.params["q"]` equals the model-supplied query **exactly**, and the rendered request (URL + every header) carries no seeded id of **either** user and no sentinel but the one the query itself contains | **GREEN** (audit) |
| 8 | same function | 2 contexts + the `003` DoD-6 case | `assemble_context` for A's session carries no B sentinel and for B's session no A sentinel. The `003` DoD-6 case is exercised as its surviving shape: A creates a **forced** `user`-scope memo whose body names B's session id (the three parented scopes answer 404 for a foreign `scope_id` and the `user` scope drops it), and that memo is present in A's own context (positive control) and absent from B's. Asserted **before** the composes above, because those deliberately put B's ids into A's own tool-call arguments, which context assembly legitimately replays; the probe memo is deleted again afterwards | **GREEN** (audit) |
| 9 | `test_index_writes_never_touch_another_users_rows__S032_004_DoD9_DoD10` | **6** foreign write attempts | zone message, settle, reopen, message edit, memo edit and memo delete against B's ids each answer **404** with the enumeration's code, and B's snapshot is **byte-identical** across all six: `memo_vec` and `session_vec` blobs for B's ids, `memo_fts_docsize` / `message_fts_docsize` rows for B's ids, and the rowid list a `MATCH` on each of B's twelve memo sentinels and three record-text sentinels returns. Never a plain `SELECT` on an FTS table (decision 18). Anti-vacuity: the snapshot is asserted non-empty in all four stores first | **GREEN** (audit) |
| 10 | same function | 6 own writes | A's own memo create / edit / delete, zone message, settle, reopen and record-row edit leave B's whole snapshot unchanged, while A's **own** snapshot is asserted to have moved (positive control, so "B unchanged" is a scoping fact rather than a no-op) | **GREEN** (audit) |
| 9 | `test_refresh_session_vectors_keeps_a_foreign_sessions_vector__S032_004_DoD9` | 1 foreign + 1 own | **the decision-19 pin.** `refresh_session_vectors(conn, A's user id, [B's session id])` must leave B's `session_vec` row — and B's whole snapshot — identical. B's row is asserted present first, so the pin cannot pass vacuously; A's own refresh is the positive control. Called directly against the service because **no route reaches it** | **RED until the coder adds the owner term; must be GREEN at verify** |

Resolutions and narrowings applied, each from a recorded decision rather than from code:

1. **DoD-1 is not "all five groups empty"** (decision 10): the vector arm has no similarity cutoff, so
   A searching for B's sentinel legitimately gets A's own memos and sessions back. The asserted
   guarantee is `brief.md`'s "no search reaches another user's material" — **no B id and no B sentinel
   in any group** — with the positive control intact. The queried sentinel is the single `allowed=`
   carve-out (it is A's own request text), and the exact five-key assertion leaves the response nowhere
   to echo it.
2. **DoD-6's `tool_args` carve-out is bounded by an exact pin** (decision 11), applied to both the wire
   `tool_args` and the stored raw `arguments`. Nothing database-derived can hide in a field whose entire
   contents are compared to a known literal.
3. **Index snapshots use `MATCH` and the `*_docsize` shadow tables** (decision 18). There is no
   `session_fts`, and `message_fts` holds only settled unburied rows — which is also why DoD-1's target
   list excludes the zone, buried, assistant and tool-payload sentinels: no search of **either** user
   could ever return them, so a positive control for them does not exist.
4. **DoD-8's "memo A created naming B's scope id"** resolves to a forced `user`-scope memo of A's whose
   **body** names B's session id, because a foreign `scope_id` answers 404 at the three parented scopes
   and is dropped at the `user` scope (decision 15 / step 003 DoD-6). The probe token, not a sentinel,
   is what must be absent from B's context.
5. **DoD-9 is asserted at two levels**: the six route-level foreign write attempts (one test) and the
   one service-level path no route reaches (its own test). The second is the audit's actual catch.
6. **One reporting caveat for the verifier**: DoD-2/DoD-3 share one function and DoD-4..DoD-8 share
   another, so those clauses' failures surface together in one message each; every message names its
   clause, the service and the ids. DoD-9 appears in two functions, and only the `refresh_session_vectors`
   one is expected red.

**`ruff check` was not run from this session — no shell tool was available to this agent**, so linting
is left to the gate. The file was written to the configured rules by inspection (line length ≤ 120,
`E,F,I,B,UP,W`, isort `order-by-type` ordering in the `from tests.privacy_audit_support import (...)`
block, no function defined inside a loop so `B023` cannot fire) and is fully annotated even though
`mypy`'s target is `app` only.

### Step 005 — tests (2026-10-06)

- `backend/tests/test_privacy_audit_export_import.py` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5 and
  DoD-6 (DoD-6 as an unbuilt-surface guard) — the own-export absence sweep, the two import-ownership
  rewrite paths, the character-scoped session import, and the admin whole-database import's refusal.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓,
  **DoD-6 `[blocked/unbuilt-dependency]` — owner `fast/003`** (guard only, no behavioural test),
  DoD-7 **[manual/live — the verifier's task]**: it confirms 030's whole-database-export opacity items
  are `done` (`030.export-granularities/context.md` ~L121, 030/005 DoD-2..4, 030/008 DoD-7) rather than
  re-testing them; `context.md`'s Out boundary forbids re-testing them here, so the module contains no
  DoD-7 test (recorded in a trailing comment so the absence is deliberate and visible).

**Four test functions, four world builds**, per the performance note (the world is ~120 requests plus
two composes and `conftest.py`'s `db_settings` is function-scoped). The split is forced by what each
clause mutates: DoD-1/DoD-6 are read-only; DoD-2 and DoD-4 both import **into A** and both assert B
unchanged, so they share one build; DoD-3 imports **into B** and needs its own; **DoD-5 gets its own
build with nothing after it** (decision 21 — it is the destructive call, and it runs only against the
fully seeded world). The module binds to step 002's delivered surface only (`audit_world` with the
default `real_logging=False`, `AuditClients.of`, `world.sentinels`, `world.content_of`,
`MEMO_SCOPES` / `MEMO_REACHES`, `UNBUILT_SURFACES`, `route_operations`, `assert_envelope` /
`assert_empty_detail` / `assert_no_sentinel_of_user` / `assert_no_identifier_of` / `rendered_text`) and
**installs no fake seam itself** — none of the four `FAKE_SEAM_OVERRIDE_KEYS` is touched anywhere in
the file, so no network request is possible.

| DoD | Test function | Cases | Asserts | Expected at the gate |
|---|---|---|---|---|
| 1 | `test_own_export_carries_nothing_of_the_other_user__S032_005_DoD1_DoD6` | 2 exports (A and B) | `GET /api/export` as each user carries **every own sentinel** (minus the translation one) and **every own seeded id** as the positive control, and **no sentinel and no id of the other user**. Problems are collected, not raised, so one leak cannot hide another | **GREEN** (audit) |
| 6 | same function | 1 guard | the bootstrap-from-export surface (row 5) **still does not exist**: every registered normalized path matching `UNBUILT_SURFACES[row 5].path_pattern` is in `allowed_paths` (`{"/api/bootstrap/create"}`), with `/api/bootstrap/create` asserted **present** first so the guard cannot pass by matching nothing | **GREEN** (the surface is unbuilt) |
| 2 | `test_imports_land_in_the_callers_ownership__S032_005_DoD2_DoD4` | 1 import, ≥5 id collisions | A posts a **`character`-granularity** export of A's own character to `POST /api/import` with every `user_id` set to **B's user id** and every row id remapped onto **B's live row ids**, carrying four fresh import tokens. 200; the new character ids are **fresh** (none of A's or B's live ids); A reads the new character 200 and **B gets 404 `character_not_found` with `detail == {}`**; every planted token is in A's own rows and the new character is in A's listing; **B's full snapshot is byte-equal before and after**; no token reaches any B read; and **every collided B id is still visible in B's own reads** (031 must remap, never overwrite) | **GREEN** (audit) |
| 4 | same function | 1 import | `POST /api/characters/{A's character}/import` with A's own **session** envelope whose ids name B's: 200; the new session is **fresh**, readable by A, 404 `session_not_found` for B, present under A's character and **absent from B's character's sessions**; B's snapshot unchanged again and neither fresh token reaches a B read | **GREEN** (audit) |
| 3 | `test_importing_another_users_export_leaves_the_owner_untouched__S032_005_DoD3` | 1 import | B posts **A's own `GET /api/export` envelope unmodified** to `POST /api/import`: 200, B's listing gains copies with **fresh ids** that B can read and **A cannot (404 `character_not_found`, `detail == {}`)**; **A's whole snapshot is equal before and after** and A's character listing is identical — nothing moved to A, nothing duplicated into A | **GREEN** (audit) |
| 5 | `test_admin_database_import_refuses_a_configured_instance__S032_005_DoD5` | 1 refused call | `POST /api/admin/database/import` by ADM against the **fully seeded** world answers **409 `database_not_empty`** with `detail == {}` (the exact status, never "any 2xx"); the refusal echoes neither the token planted in the payload nor any sentinel or id of A or B; **A's and B's full snapshots and the admin account listing are unchanged**. Anti-vacuity: both users are asserted to hold content before the call | **GREEN** (audit) |

Resolutions and narrowings applied, each from a recorded decision rather than from code:

1. **DoD-2's payload shape is `character` granularity** (decision 16), stated in the test's docstring so
   no reader thinks the easier path was taken by accident: a `user`-granularity payload whose rows'
   `user_id` disagrees with its own `users` row id answers 400 `export_invalid` / `malformed_payload`
   and never reaches the ownership rewrite. **DoD-3 exercises the other admissible shape** — A's own
   `user` envelope, whose ids all agree — so both branches of decision 16 are covered.
2. **DoD-1's two exclusions, both inline with their reason** (decision 17): the `translations` sentinel
   is dropped from the **positive control** only (user/database exports exclude that table, so looking
   for it there would fail for the wrong reason) and stays in the absence set — the test additionally
   asserts it is *not* present, so the exclusion cannot hide a real row; and the instance-wide
   `model_server_id` is passed through `assert_no_identifier_of(..., allowed=(world.models.server_id,))`,
   the support module's single documented carve-out channel, because it is a registry id shared by every
   user rather than an id of the other user. Every other sentinel and id stays in the set.
3. **DoD-6 has no built target** (orientation decision 1): no route, payload or response was invented.
   It is recorded `[blocked/unbuilt-dependency]`, owner `fast/003`, and is asserted only as the
   surface's continued absence through step 002's `UNBUILT_SURFACES`. Not a leak finding, not a `SPEC`
   defect in 032's table.
4. **DoD-5 is isolated and asserted exactly** (decision 21): its own world build, nothing after it, the
   409 asserted rather than tolerated, and the payload is the instance's own whole-database export used
   **purely as a payload** — nothing is asserted about that export's contents, because its opacity rule
   is 030's and is cited, never re-tested (`context.md` Out, DoD-7).
5. **"Unchanged" is a snapshot of the user's own read responses** (`005.context.md`): me, settings,
   characters (both views), character + configuration, setups, setup, sessions (both views), each
   session + entries + zone + memo-chain + configuration, every entry's discussion, the memo list at all
   four scopes — **plus the user's whole export `payload`** (the envelope header is dropped because
   `created_at` moves per call), which makes the comparison row-level rather than listing-level. Nothing
   is excluded.
6. **One reporting caveat for the verifier**: DoD-1/DoD-6 share one function and DoD-2/DoD-4 share
   another, so those clauses' problems surface together in one aggregated message each; every line is
   prefixed with its DoD id and names the ids involved.

**`ruff check` was not run — no shell tool was available to this agent either**, so linting is left to
the gate. The file was written to the configured rules by inspection (line length ≤ 120, `E,F,I,B,UP,W`,
isort `order-by-type` ordering in the single `from tests.privacy_audit_support import (...)` block, no
function defined inside a loop so `B023` cannot fire, no unused import) and is fully annotated even
though `mypy`'s target is `app` only.

### Step 006 — tests (2026-10-06)

- `backend/tests/test_privacy_audit_admin.py` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-6 and
  DoD-7 (DoD-7 as an unbuilt-surface guard) — the admin-GET absence sweep, the content-volume
  snapshot, the fourteen admin mutations, the R5 enabled-model removal, the declared-response-model
  name scan, `/api/health`, and fast/002's continued absence.
- `frontend/tests/adminPrivacyAudit.test.ts` — covers DoD-8 and DoD-9 — a comment-stripped,
  whole-identifier source scan of `frontend/src/admin/` for `/api/` prefixes and forbidden names.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓,
  **DoD-7 `[blocked/unbuilt-dependency]` — owner `fast/002`** (guard only, no behavioural test),
  DoD-8 ✓, DoD-9 ✓, DoD-10 **[manual/live, no test]**.

**Four test functions, four world builds** (the world is ~120 requests plus two composes and
`conftest.py`'s `db_settings` is function-scoped), following steps 003..005. The split is forced by
what each clause mutates: build 1 is read-only apart from DoD-2's extra content; build 2 runs the
fourteen mutations; build 3 rewrites the enabled-model set for DoD-4; **build 4 is the destructive
whole-database-import clause, isolated with nothing after it** (decision 21). The module binds to
step 002's delivered surface only (`audit_world` with the default `real_logging=False`,
`world.clients`, `world.sentinels`, `world.models`, `world.fakes.chat_factory`, `ENUMERATED_ROUTES`,
`EXISTING_TABLE_NAME`, `UNBUILT_SURFACES`, `api_routes`, `normalize_path`, `route_operations`,
`registered_paths_by_operation`, `assert_envelope` / `assert_empty_detail` /
`assert_no_sentinel_of_user` / `rendered_text`) and **installs no fake seam itself** — none of the
four `FAKE_SEAM_OVERRIDE_KEYS` is touched anywhere in either file, so `POST …/test`,
`GET …/available-models` and the embedding designation cannot reach the network.

#### Per-DoD test inventory

| DoD | File / test function | Cases | Asserts | Expected at the gate |
|---|---|---|---|---|
| 1 | `test_every_admin_read_carries_only_administrative_data__S032_006_DoD1_DoD2_DoD5_DoD6_DoD7` | **4** admin GETs | every `admin`-class GET row of the enumeration except the named export answers 200 as ADM and carries **no sentinel of A and none of B**. Positive controls per surface: `/api/admin/users` names all three usernames, `/api/admin/llm-servers` names the server and the enabled chat model, `…/available-models` offers a model name, `/api/admin/database/tables` names `characters`. Anti-vacuity: both registries are non-empty and the matcher is shown to raise on a planted sentinel. Problems are collected, not raised | **GREEN** (audit) |
| 2 | same function | 4 GETs × 2 snapshots | each response is **equal before and after** A and B each add a character, setup, session, pasted partner block, zone message and memo through their **already-authenticated** clients, excluding only `006.context.md`'s volatile fields (`id`, `created_at`, `updated_at`, `last_test_*`) — **every numeric field stays in the comparison**, and `last_login_at` stays because no login happens between the snapshots. Anti-vacuity: each user's new character is asserted present in their own listing | **GREEN** (audit) |
| 5 | same function | 20 admin routes | for every walked `/api/admin/` route the **declared response model and every nested model** is collected through `model_fields` (names and aliases) and no name matches the forbidden list as a whole identifier (R5). Matcher self-test first (`session_count`, `inUse`, `sessionCount`, `dependentSessions` flagged; `embedding_dim`, `enabled_model_names`, `username`, `usage`, `independent` not). Anti-vacuity: the walk must have found the seven administrative field names `006.context.md` records as built. Routes with **no** declared response model are asserted to be covered by DoD-1/DoD-3/the import clause/the named export exclusion, so none slips through both | **GREEN** (audit) |
| 6 | same function | 2 callers × 2 snapshots | `GET /api/health` as anon **and** as ADM carries no sentinel of either user and is **byte-equal** across the same seeding, with nothing excluded | **GREEN** (audit) |
| 7 | same function | 1 guard | fast/002's vector-rebuild surface **still does not exist**: no registered normalized path matches `UNBUILT_SURFACES[row 74].path_pattern`, whose `allowed_paths` is asserted empty. Anti-vacuity: the route walk is non-empty and the pattern is shown to match two synthetic rebuild paths, so the guard cannot pass by matching nothing (same device as step 005 DoD-6) | **GREEN** (the surface is unbuilt) |
| 3 | `test_every_admin_mutation_response_carries_no_user_content__S032_006_DoD3` | **14** mutations | the fourteen mutations DoD-3's parenthetical names (user create/disable/enable/password/role on a throwaway roleplayer; llm-server create/patch/delete on a throwaway registration; test / models / embedding-model set / embedding-model unset on the world's own server; database table create and sync) each carry **no sentinel of A and none of B**. The exercised `(method, path)` set **plus** the named import equals the enumeration's fifteen admin mutations exactly, so a new admin mutation route can never go unswept. Positive controls: the user-create response echoes the username and the server-create response the name | **GREEN** (audit) |
| 4 | `test_removing_a_model_a_session_uses_is_never_refused__S032_006_DoD4` | 2 removals | **the R5 reverse-lookup clause.** Removing the model B's session uses answers **200, never a refusal**, and its body is **byte-equal** to the body of removing a twin model no session has ever referenced — the two scenarios are made structurally symmetric (both leave the same remaining enabled set) so "equal field for field apart from the model name" needs no normalisation at all. Both bodies carry no sentinel of either user and **no session id of B's**. Anti-vacuity: the used model is asserted to appear among the models the world's composes actually called, and each removal is asserted to have taken effect | **GREEN** (audit) |
| 3 | `test_admin_database_import_refuses_without_echoing_content__S032_006_DoD3` | 1 refused call | the fifteenth admin mutation, isolated (decision 21): `POST /api/admin/database/import` by ADM against the **fully seeded** world answers **409 `database_not_empty`** with `detail == {}` (the exact status, never "any 2xx"), echoes no sentinel, and **wipes nothing** — all three accounts and both roleplayers' own content are still there afterwards. Anti-vacuity: both users are asserted to hold a character first. Nothing is asserted about the whole-database export used as the payload (opacity is 030's) | **GREEN** (audit) |
| 8 | `adminPrivacyAudit.test.ts` — "every /api/ path literal … begins with an allowed prefix" | 6 flagged + 12 clean self-tests + 1 real scan | every `/api/…` run of path characters in the **comment-stripped** source of every `.ts`/`.tsx` file under `frontend/src/admin/` begins with one of `006.context.md`'s four allowed prefixes; the offence list is an **exact empty set**. The allowed list itself is pinned to the four names so it cannot be widened silently. Anti-vacuity: the scan is shown to reach the three admin pages, to find a non-zero number of literals, and to contain `/api/admin/users`, `/api/admin/llm-servers` and `/api/admin/database/tables`; the matcher flags `/api/sessions`, `/api/search`, `/api/export`, `/api/memos`, `/api/members` and bare `/api/`, and does not flag the four allowed prefixes, `/api/me/settings`, `/api/me?x=1`, `/login`, a `${PREFIX}`-composed template or a commented route. The two bare-path prefixes match on a **segment boundary** — after `/api/me` and `/api/health` the literal must end or continue with `/` or `?` (fix round 1) | **GREEN** (decision 25) |
| 9 | same file — "no admin file names a count of … another user's material" | 20 flagged + 14 clean self-tests + 1 real scan | no comment-stripped admin file matches any of the 23 forbidden identifiers as a **whole identifier** (`(?<![A-Za-z0-9_$])…(?![A-Za-z0-9_$])`, case-insensitive), any of the three forbidden phrases as whole words, or the "N sessions use this model" family (a digit or an interpolation read as a quantity of sessions); the offence list is an **exact empty set**. The 23-name list and the 3-phrase list are pinned to `006.context.md`. Matcher self-tests prove it flags every forbidden shape **and** does not flag `AdminUserRow` / `AdminUserRole` / `AdminUserListResponse`, `account`, `independent`, `usage`, `embedding_dim`, `enabled_model_names.length`, `formatByteSize(exportSizeBytes)`, or a bare `count` sitting in a comment | **GREEN** (decisions 24, 27) |

#### Resolutions and narrowings applied, each from a recorded decision rather than from code

1. **`GET /api/admin/database/export` is excluded from DoD-1 and DoD-2 by name, with the reason
   inline** (decision 20): it returns the whole database **including every user's content by
   design**, so an "every admin GET" loop would find B's sentinels in it and report a leak that is
   not one. Its opacity rule belongs to 030 and is cited, never re-tested here (`context.md` "Out");
   its role gate stays armed in step 002 DoD-2/DoD-3 (enumeration row 72). The test asserts the
   exclusion is **not stale** — the enumeration must still hold that GET row — so the carve-out
   cannot outlive its subject.
2. **`POST /api/admin/database/import` is held out of DoD-3's loop and given its own final build**
   (decision 21). DoD-3's parenthetical names fourteen mutations and omits the import; the import is
   destructive on an empty instance, so a loop that reached it could have wiped the world and made
   every later absence assertion vacuously green. The exclusion is not a hole: the coverage clause
   asserts `exercised ∪ {import} == every admin non-GET row`, and the import is asserted to answer
   the **exact** 409 rather than "any 2xx".
3. **DoD-7 has no built target** (decision 22 / orientation decision 1): enumeration row 74 is
   `fast/002`'s vector-rebuild route, `fast/002.vector-index-rebuild/` holds only a `brief.md`, and
   no route under `backend/app/` matches a rebuild shape. **No route, payload, progress shape or
   response was invented.** DoD-7 is recorded **`[blocked/unbuilt-dependency]`, owner `fast/002`**,
   and is asserted only as the surface's continued absence through step 002's `UNBUILT_SURFACES`
   (the same device step 005 used for row 5), with an anti-vacuity control on the pattern. It is
   **not** a leak finding and **not** a `SPEC` defect in 032's table. DoD-1's parenthetical "the
   fast/002 progress/status read if any" resolves to **none**, which narrows DoD-1 not at all — it
   still sweeps every admin GET that exists.
4. **DoD-2's snapshot pair** (`006.context.md` "Snapshot rules"): `audit_world` seeds the whole world
   atomically, so the "before" snapshot is taken **after the world is built and after every login**,
   and the "after" snapshot follows additional content written by A's and B's **already
   authenticated** clients. `last_login_at` therefore cannot move between the two, and the invariant
   asserted is exactly DoD-2's: no admin field moves with content volume. Only `id`, `created_at`,
   `updated_at` and `last_test_*` are dropped; every numeric field — `embedding_dim` included —
   stays in the comparison.
5. **DoD-3 pins no success status.** Its clause is "the response contains no sentinel of any user",
   so each of the fourteen responses is swept unconditionally and asserted only **not** to answer a
   gate/validation status (401/403/404/405/422), which proves the handler ran. Pinning a status for
   `…/tables/{}/create` against an already-created table would have meant inventing an expected
   value the step file does not state. The two 204 routes are allowed an empty body.
6. **DoD-4 is asserted as byte equality, not as a normalised comparison.** The two removals are made
   structurally symmetric — both leave the same remaining enabled set, and the only difference is
   whether the removed model was one a session uses — so "equal field for field apart from the model
   name" becomes the sharpest available form: identical status, identical body. A difference of any
   kind would be the reverse lookup leaking.
7. **DoD-9's matcher is whole-identifier *and* comment-stripped** (decision 24). A naive substring
   match produces about fifty false positives (`inUse` inside `AdminUser…`, `count` inside
   `account`), and the bare word `count` appears **eight times, all in comments**, so an
   un-stripped scan would fail on prose that renders nothing. Comments are blanked **keeping every
   newline**, so reported line numbers stay true. Registry counts not derived from user content
   (`embedding_dim`, the length of `enabled_model_names`) are proved non-matching by a clean
   self-test rather than by an exception list.
8. **DoD-8 is scanned over the admin entry's own files only** (decision 25), exactly the boundary
   `006.context.md` draws: the actual `/api/me` request lives in `shared/currentUser.ts`, outside
   the scanned directory, and the `/api/me` occurrences inside `src/admin/` are comments. The
   "exact set" device is applied to the **offence list** (asserted exactly empty) and to the
   **allowed-prefix list** (pinned to `006.context.md`'s four names). Pinning the full set of
   literals found was **deliberately rejected**: it would fail when the admin entry legitimately
   adds a path under an allowed prefix, which DoD-8's own wording permits — that would be a false
   finding rather than a regression.
9. **Decision 27 — one adjudicated non-finding, considered and not flagged.** The admin Database
   page renders "Export downloaded" plus a **formatted file size**, a number derived from
   user-content volume, while `brief.md` forbids "a count derived from any of it". It is **not** a
   finding: **US-078 authorises it**, the whole-DB export is governed by 030's opacity rule rather
   than this sweep, and the admin who just downloaded the file already holds it, so the number
   discloses nothing. It matches no forbidden name, and a clean self-test
   (`formatByteSize(state.exportSizeBytes)`) pins that it must stay unflagged.
10. **DoD-10's `[manual/live]` wording outruns the UI** (decision 26). There is **no confirm for
    disabling a model** — `EnabledModelsModal` is a checkbox list plus Save — so "the model-disable
    confirm shows no number" has no target. The live check is therefore against the **five confirms
    that do exist**: user disable, server delete, embedding clear, lossy table Sync and
    whole-database replace, none of which contains a number; plus the Users and Database pages
    showing no content. No test is written for it.
11. **One reporting caveat for the verifier**: DoD-1, DoD-2, DoD-5, DoD-6 and DoD-7 share one test
    function (one world build), so their problems surface together in one aggregated message; every
    line is prefixed with its DoD id and names the enumeration row, the method and the path. DoD-3
    appears in two functions — the fourteen-mutation loop and the isolated import clause.

**Neither gate could be run: the Bash tool is disabled in this session**, so `ruff check .` is owed
on this backend file and `npm run typecheck` on the frontend file, exactly as for steps 002..005.
Both were written to the configured rules by inspection: the backend file is ≤ 120 columns
throughout (verified by regex), fully annotated, `E,F,I,B,UP,W`-clean by construction (isort
`order-by-type` ordering in the single `from tests.privacy_audit_support import (...)` block, no
unused import, no closure defined inside a loop so `B023` cannot fire); the frontend file is
TypeScript only, imports `describe` / `expect` / `it` explicitly because `globals: false`, declares
`Rule = [string, RegExp]` and `Offence` so every helper is typed, and uses only `node:fs`,
`node:path` and `__dirname` — the same three the existing `tests/conventions.test.ts` and
`tests/ids-are-strings.test.ts` scanners use from the same directory depth.

#### Red-gate fix round 1 (2026-10-06) — two faults, both in self-tests

1. **Backend, an ordering assumption of mine, not a matcher miss.** The DoD-9/DoD-5
   forbidden-name matcher self-test at the head of
   `test_every_admin_read_carries_only_administrative_data__S032_006_DoD1_DoD2_DoD5_DoD6_DoD7`
   compared `_forbidden_names([...])` as an **ordered tuple** and so failed on a differently
   ordered — but correct — result. Now compared as a **set**: the clause is *which* names are
   flagged, never the order. The matcher and the expected name set are unchanged. Because this
   assertion sits first in the function, DoD-1, DoD-2, DoD-5, DoD-6 and DoD-7's route assertions
   behind it were never reached at the gate; they will be reached for the first time next run, and
   anything they then report is a **leak finding to be reported, not adjusted away**.
2. **Frontend — a genuine guard weakness my own self-test caught, which is what the self-tests are
   for.** `isAllowedLiteral` used a bare `startsWith`, so `/api/memos` and `/api/members` counted as
   allowed under the `/api/me` prefix: a real admin-entry call to the user-content route
   `/api/memos` would have **passed DoD-8**. The planted case `const memos = "/api/memos";` failed
   as expected-0-to-be-greater-than-0 and exposed it. Fixed by requiring a **segment boundary**
   after the two bare-path prefixes (`/api/me`, `/api/health`): the literal must end or continue
   with `/` or `?`. `/api/admin/` and `/api/auth/` already end in `/` and are untouched.
   `006.context.md`'s allowed list is still exactly those four names. New self-test cases:
   `/api/members` flagged (pinning the boundary from the second side), and `/api/me/settings` and
   `/api/me?x=1` clean (pinning that the boundary does not reject the allowed route itself).
   This is evidence the matcher self-tests are load-bearing rather than decorative.

Nothing else changed: no assertion weakened, the 23-name forbidden list, the four allowed prefixes,
the comment-stripping behaviour (decision 24), the whole-identifier semantics, the four world builds,
the isolation of `POST /api/admin/database/import` as the last build (decision 21) and decision 27's
`formatByteSize(state.exportSizeBytes)` clean case all stand. The real directory scan is still
expected **green** on decision 25 — every `/api/` literal under `frontend/src/admin/` begins with
`/api/admin/`, the only `/api/me` occurrences there are comments, and the real `/api/me` request
lives in `shared/currentUser.ts` outside the scanned directory — and the boundary rule narrows only
what *would* be allowed, never what is present. **Neither gate could be run in this round either: no
shell tool is available in this session**, so `ruff check .` and `npm run typecheck` remain owed.
Both edits were written to the configured rules by inspection (the new backend line is 102 columns,
under the 120 limit; the frontend change adds no import and no untyped binding).

### Step 007 — tests (2026-10-06)

- `backend/tests/test_privacy_audit_logs.py` — covers DoD-1..DoD-9 — the whole-world log
  sentinel sweep under the **real** `configure_logging`: the build phase, every `self` /
  `owner` / `registry` success path, every refusal path, every sentinel-bearing failure at
  the model / tool / translation / auth / probe seams, my-search, and the SQLAlchemy levels.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
  DoD-9 ✓, DoD-10 **[manual/live, no test]** (the production container).

**Three world builds plus one build-free test.** The world is ~120 requests plus two
composes and `conftest.py`'s `db_settings` is function-scoped, and this is the most
expensive world in the feature (real logging plus ~50 driven routes), so the split is the
minimum each clause's state allows: build 1 = DoD-1 (read-mostly, plus the success-path
writes); build 2 = DoD-2 + DoD-6 (refusals, **ending** with the destructive admin import,
decision 21, with nothing after it); build 3 = DoD-3 + DoD-4 + DoD-5 + DoD-7 + DoD-8
(failure paths, each in its own capture window); DoD-9 needs no world at all. The module
binds to step 002's delivered surface only (`audit_world(..., real_logging=True)`,
`captured_logs(restore_stdlib=False)`, `restored_logging_state`, `LogCapture`,
`ENUMERATED_ROUTES` / `EnumeratedRoute`, `fill_path`, `registered_paths_by_operation`,
`ScriptedProbeFactory`, `text_round` / `tool_call_round`, `world.fakes.*`,
`assert_envelope` / `assert_empty_detail`, the path and timeout constants) plus
`app.logging.configure_logging` as frozen by step 001's record, and **installs no fake
seam itself** — none of the four `FAKE_SEAM_OVERRIDE_KEYS` is touched anywhere in the
file, so no network request is possible.

#### Per-DoD test inventory

| DoD | Test function | Cases | Asserts | Expected at the gate |
|---|---|---|---|---|
| 1 | `test_world_build_and_every_success_path_log_no_sentinel__S032_007_DoD1` | world build + **48** driven rows | the world is built with `real_logging=True`; then every `self` (12), `registry` (1) and `owner` (35) row is driven as its owner, in an order the built validation accepts (settle needs a non-empty zone; reopen an empty one plus a buried group; the translation is made uncached by editing its source row first; rows 53/18 post real envelopes from rows 44/17). No record's message, `repr(extra)` or exception text carries any sentinel, and neither does the real console sink's text. **Coverage is exact and two-way**: the driven row set equals `{row for row in ENUMERATED_ROUTES if class in (self, owner, registry)}`, asserted to be 48, with no row driven twice; every driven row is asserted to have answered 200/201/204 | **GREEN** (audit) |
| 2 | `test_refusal_paths_log_no_sentinel__S032_007_DoD2_DoD6` | 35 + 4 + 1 + 1 | all **35** owner rows refused with B's id; 409 `memo_order_mismatch`, `zone_empty`, `nothing_to_reopen`, `already_configured` each asserted by code with `detail == {}`; a 422 whose body carries a sentinel; and **last**, `POST /api/admin/database/import` answering **409 `database_not_empty`** against the fully seeded world (anti-vacuity: A is asserted to hold content first). No capture record and no console text carries a sentinel; `capture.records` is asserted non-empty | **GREEN** (audit) |
| 6 | same function | 1 import | A's **own real export**, with `version` forced to 99 and a planted token added to the sheet, is refused **400 `export_invalid`**; the posted payload is asserted to really contain A's `characters.sheet` sentinel and the planted one, so the absence in logs is about redaction and not about an empty payload | **GREEN** (audit) |
| 3 | `test_failure_paths_log_no_sentinel__S032_007_DoD3_DoD4_DoD5_DoD7_DoD8` | 2 composes | the fake model raises a sentinel-bearing `LlmUnreachableError` (a `DomainError`, whose message legitimately reaches the SSE error frame) and then a sentinel-bearing `RuntimeError`; both composes are asserted to have produced an `error` frame, and the recorded prompt is asserted to carry a sentinel of A — so "whose prompt carries sentinels" is a fact, not an assumption | **GREEN** for the capture sink; the **console** clause may be red at the red gate (see below) |
| 4 | same function | 1 compose, 3 tool calls | one compose dispatches `memo_search`, `session_search` and `web_search` in three scripted rounds; the two search adapters fail with `RuntimeError(<sentinel>)` raised from the re-pointed embedding factory, the web call fails with `httpx.ConnectError(<sentinel>)` raised at 028's `MockTransport` seam (set on the recorder `audit_world` built — this step may not rebuild the seam). The frame set is asserted to be exactly three `tool_fail`s, one per tool, so every clause of DoD-4 really failed; both the factory and the recorder error are restored in a `finally` | **GREEN** for the capture sink; console as below |
| 5 | same function | 2 translations | decision 12 in full: the **handled** path with `LlmUnreachableError(<sentinel>)` answering 502 `translation_failed`, and the **unhandled** path with a `RuntimeError(<sentinel>)` of another class, asserted to propagate (`pytest.raises`) with the sentinel in its own message. A fresh settled partner block is filed first, so neither call can be answered from the cache | **GREEN** for the capture sink; console as below |
| 7 | same function | 1 login + 2 probes | a failed login with a **sentinel password** answering 400 `invalid_credentials` with `detail == {}`; then a second LLM server whose `api_key_ref` points at an env variable holding a **sentinel API key**, probed through `POST …/test` (200) and `GET …/available-models` (502 `llm_unreachable`) with an `AUTH_FAILED` scripted probe. Anti-vacuity: the probe ran at least twice and **every** api_key the factory was handed equals the sentinel, so the key really was in play | **GREEN** (audit) |
| 8 | same function | 2 searches | `GET /api/search?q=<B's sentinel>` and `?q=<A's own sentinel>` as A, the second asserted to return a character (so my-search really ran and matched). This is the application's own records; 029's query string in **uvicorn's access line** is step 001 DoD-1's subject and is not re-asserted here | **GREEN** (audit) |
| 9 | `test_sqlalchemy_loggers_stay_at_warning_or_higher__S032_007_DoD9` | 2 loggers | after `configure_logging(settings)`, `sqlalchemy` and `sqlalchemy.engine` both report an **effective level ≥ WARNING**; the root bridge is asserted wide open (≤ DEBUG) first, so the two levels are shown to be the only thing between a statement log and the sinks. No world is built | **GREEN** (Report 1 §A measured both at an effective WARNING as built) |

#### The two witnesses, and how a red case is attributed

Every clause is swept against two independent witnesses, and the failure message says
which matched, because the causes and the owners differ:

1. **The capture sink** (`captured_logs`), swept over each record's `message`,
   `repr(extra)` and `exception_text` — exactly the three fields every DoD item names. A
   hit here is a **genuine leak finding**: a `logger.*` call or an exception-formatting
   site wrote content. Routed to step 007's fix-allowance. The record's `formatted` field
   is deliberately **not** swept, and the module says why: it is rendered with the
   *capture sink's* own loguru options (`captured_logs` adds its sink with loguru's default
   `diagnose`/`backtrace`, which this step may not change — the signature is frozen), so a
   frame local appearing there would say nothing about the application's sinks.
2. **The real console sink's text** — `sys.stderr` is replaced by an in-memory stream
   *before* `create_app()` **and from inside the test body** (see "Red-gate fix round 1"
   below), so the sink the real `configure_logging` installs writes there
   at `DEBUG`. This is the only witness that can see the **world build** (DoD-1's first
   clause), because `configure_logging` itself calls `logger.remove()` and so no capture
   sink can predate it. DoD-1 additionally sweeps the real **log file** (flushed by
   `logger.remove()` as the test's last act) — the same surface DoD-10 checks live.

**Expected red at the red gate solely because step 001 is unimplemented** (and therefore
**must be GREEN at verify**): the **console-text** clause of DoD-3, DoD-4 and DoD-5 (and,
in principle, DoD-6, which drives no exception and so is expected green on both
witnesses). Step 001's skeleton left `configure_logging` adding the console sink with
loguru's default `diagnose=True`, so **if** any record reaches the sink with an exception
attached, the rendered traceback prints frame locals — including the sentinel-bearing
exception the test just raised. Each such failure message quotes the surrounding text and
states both readings explicitly: a hit inside frame locals is step 001's behaviour, a hit
anywhere else is a step 007 leak. The capture-sink clause of the same items is
step-001-independent and is predicted **green** (harvest §A5: the frame harness logs
`type(error).__name__`, `dispatch` logs the tool name, call id and exception class, and
`domain_error_handler` logs the code and status — none attaches the exception or formats
its message).

**No leak finding was identified at write time.** Nothing here was derived from reading an
implementation body; the predictions above come from the harvest's record of the declared
log lines (`007.context.md` "Declared log lines in planned features") and are predictions,
not measurements.

#### Red-gate fix round 1 (2026-10-06) — the console witness was not armed

The red gate returned **Fault TEST**: DoD-1, DoD-2/6 and DoD-3/4/5/7/8 all failed inside
`_control` on `"the real console sink wrote nothing: this witness is not armed"`, with the
records instead appearing under pytest's *Captured stderr call*. Cause: the `harness`
fixture installed the redirect with `monkeypatch.setattr(sys, "stderr", console)` during
**fixture setup**, and pytest's capture plugin **re-installs its own `sys.stderr` when the
call phase starts**. loguru binds the stream object current at `add()` time, and the real
`configure_logging` runs inside `audit_world` in the **call phase** — so the console sink
bound pytest's stream, not the module's `StringIO`, and every console-text clause would
have passed vacuously had the control not caught it. The control did exactly its job and
was **not** softened.

Fix: the fixture now only *constructs* the `StringIO`; the redirect moved into the call
phase as `LogHarness.bound_console()`, a `@contextmanager` that assigns `sys.stderr` and
restores the previous object in a `finally`. Every test enters it as the **outermost**
context manager of its body (`with harness.bound_console(), restored_logging_state(),
audit_world(..., real_logging=True) as world:`), so the stream is current at the instant
`configure_logging` adds the sink and is undone before the test returns. The `StringIO` is
never closed, and the autouse `_loguru_sinks` fixture still resets loguru to a single
**real**-stderr sink on both sides of every test, so no test ends holding it. DoD-9 is
wrapped the same way for consistency (it never reads the console). This is a trap any
future test that wants the *real* console sink will hit: a stderr redirect for a real-sink
witness must be installed in the call phase, never in a fixture.

Unchanged by the fix: every sentinel sweep, every assertion, which fields are swept
(`message`, `repr(extra)`, `exception_text`; `formatted` still deliberately excluded), the
dual-witness failure message stating both readings, the real log-file sweep, the
anti-vacuity control's loguru **and** stdlib-bridge records against **both** witnesses,
`real_logging=True` on every world build, `RPHELPER_LOG_FILE_PATH` set under `tmp_path`
before `db_settings` resolves plus the fixture's assertion that `settings.log_file_path` is
that path, decision 9's state restoration, decision 21's ordering, and the world-build
count (**3**).

#### Resolutions and narrowings applied, each from the plan or a recorded decision

1. **Anti-vacuity is explicit, not assumed.** Every capture window opens with a control
   that emits one loguru record **and** one stdlib record (through the `InterceptHandler`
   bridge the real `configure_logging` installs) and asserts both markers reached the
   capture sink **and** the real console sink. So "no sentinel" can never pass because a
   sink was dead. DoD-2 additionally asserts `capture.records` is non-empty.
2. **DoD-2's per-row 404 exactness is narrowed where this step supplies a body, and only
   there.** A row driven with **no** body must answer exactly 404 with the row's
   `not_found_code` from `ENUMERATED_ROUTES`. A row this step must give a body to may
   answer 404 **or 422** — a 422 means the declared body is not that row's shape, the
   request is still a refusal path (which is all DoD-2 sweeps), and the exact per-row 404
   contract with valid bodies is **step 003 DoD-1's**, asserted there with its own payload
   table and not re-asserted here (`context.md` "Out"). Both outcomes are reported in a
   separate, labelled `driver` problem list, so a body-shape mismatch can never be read as
   a log leak.
3. **DoD-2's 422 asserts the status only.** `007.context.md` scopes responses out ("errors
   may legitimately carry a sentinel in the HTTP response"), so whether FastAPI's
   validation body echoes the sentinel is not asserted — the body *sent* carries it, which
   is what the clause requires.
4. **DoD-5 drives both exception classes** (decision 12), the unhandled one included,
   because that is the more dangerous case for a log leak and both are inside DoD-5's
   words.
5. **DoD-7's sentinel is the API key**, resolved through an `api_key_ref` pointer and an
   env variable (the delivered `test_admin_llm_router.py` pattern), with the probe failing
   as `AUTH_FAILED`. The variable is deliberately **not** `RPHELPER_`-prefixed, so
   `conftest.py`'s isolation fixture leaves it alone, and it is set with `monkeypatch`
   only — `backend/.env` is never read or written.
6. **No AST scan of `logger.*` call sites** (user decision, `007.context.md`): the proof is
   dynamic throughout.
7. **One reporting caveat for the verifier**: DoD-2 and DoD-6 share one function and
   DoD-3/4/5/7/8 share another. Inside the shared functions each clause has its **own
   capture window and its own assertion**, and every problem line is prefixed with its DoD
   id and its witness, so the clauses never report together.

#### Safety and state hygiene

- `real_logging=True` is passed on every world build in this module — the only step that
  does (`context.md`: "Step 007 calls the **real** `configure_logging`").
- The log file is pointed at `tmp_path` through `RPHELPER_LOG_FILE_PATH` **before**
  `db_settings` is built (the fixture resolves `db_settings` / `db_engine` with
  `request.getfixturevalue`, so the ordering is explicit rather than incidental), and the
  fixture **asserts** `settings.log_file_path == tmp_path/logs/audit-007.log`. The
  project's `data/logs/` is never written, `backend/.env` is never read (settings come from
  `conftest.py`'s `db_settings`, i.e. `Settings(_env_file=None)` under `tmp_path`), and
  `backend/data/rphelper.sqlite` is never touched.
- Decision 9: `restored_logging_state()` wraps every test body and `captured_logs(...)` is
  always entered with `restore_stdlib=False` inside it, so `level`, `handlers`,
  `propagate` **and `.filters`** are snapshotted and restored for all seven
  `RESTORED_LOGGER_NAMES`; every capture sink is removed by id; and an autouse fixture
  resets loguru to a single **real**-stderr sink on both sides of every test, so neither
  the in-memory console stream nor the `tmp_path` file sink outlives it.
- No network request is possible: all four seams stay as `audit_world` installed them, the
  web failure is induced at the `httpx.MockTransport` recorder, and the probe failure at
  the scripted probe factory.

**`ruff check` was not run — no shell tool was available to this agent either** (as for
steps 002..006), so linting is left to the gate. The file was written to the configured
rules by inspection (line length ≤ 120, `E,F,I,B,UP,W`, isort `order-by-type` ordering in
the single `from tests.privacy_audit_support import (...)` block, no unused import, no
closure defined inside a loop so `B023` cannot fire) and is fully annotated even though
`mypy`'s target is `app` only.

## Notes & Issues

_populated by the coder when worth saying_

## Ultra phase

- orient: done 2026-10-05

### Step list built at orient

| Step | Source files | Test files | Kind |
|---|---|---|---|
| 001 | `backend/app/logging.py`, `backend/app/db/engine.py` | `test_logging_redaction.py` | **real source change, normal red gate** |
| 002 | none planned (fix-allowance: a router missing `require_user`/`require_role`) | `privacy_audit_support.py`, `test_privacy_audit_routes.py` | audit + the shared world |
| 003 | none planned (fix-allowance: the owner predicate of a failing surface) | `test_privacy_audit_owner_sweep.py` | audit |
| 004 | none planned (fix-allowance: the user predicate of a failing read/write path) | `test_privacy_audit_search_tools.py` | audit |
| 005 | none planned (fix-allowance: export/import owner predicate) | `test_privacy_audit_export_import.py` | audit |
| 006 | none planned (fix-allowance: admin routers/services, `frontend/src/admin/`) | `test_privacy_audit_admin.py`, `adminPrivacyAudit.test.ts` | audit |
| 007 | none planned (fix-allowance: `logging.py` or an offending `logger.*` site) | `test_privacy_audit_logs.py` | audit |

**62 DoD items total: 8 + 6 + 11 + 10 + 7 + 10 + 10, of which 58 are `[test]` and 4 are
`[manual/live]`** (001 DoD-8, 005 DoD-7, 006 DoD-10, 007 DoD-10 — and 005 DoD-7 is a verifier
confirmation of 030's items rather than a live check).

_Corrected at verify: this line first read "86 DoD items total" and "57 `[test]` and 5
`[manual/live]`". The sum of the per-step counts is **62**, the `[manual/live]` items are the **four**
this line itself names, and so the `[test]` items are **58**. The global verifier caught the
off-by-one in both halves. All 58 are covered and green._

Dependencies: 001 none · 002 none · 003..006 depend on 002 · 007 depends on 001 and 002. So the step
order is also the dependency order, which is what the phased cadence needs.

### Build state confirmed at orient, and the one place it diverges from the plan's assumption

Every numbered feature **001..031 is built and `done`** — I confirmed each folder's `status.md` rows,
and 031 was committed as `0519775` immediately before this feature began. The plan's "Build state this
plan is written against" is therefore satisfied for every numbered dependency, and every frozen
`## Skeleton` record the later phases need (019, 020, 021, 024, 025, 026, 027, 028, 029, 030, 031) is
present and readable.

**It is not satisfied for the `fast/` track.** `docs/plans/fast/001.dev-and-container-harness/`,
`fast/002.vector-index-rebuild/` and `fast/003.bootstrap-from-export/` each hold **only `brief.md`** —
unplanned, so unbuilt. `context.md` anticipated this only at *plan* time ("`fast/002` and `fast/003`
have only a `brief.md` at plan time … the harvest for the step that touches them reads that
`plan.md`"); it assumed both would be planned and built before 032. They were not.

### Orientation decision 1 — enumeration rows 5 and 74 are carried forward, not invented

The two `_TBD` rows name surfaces that **do not exist in the application**:

- **Row 5** — `_TBD: fast/003 bootstrap-from-export path_`, class `public`, swept by step 005.
- **Row 74** — `_TBD: fast/002 vector-rebuild route(s)_`, class `admin`, swept by step 006.

`docs/plans/CLAUDE.md` forbids inventing a requirement to close a gap, and `002.context.md`'s skeleton
job 3 ("record the exact method + path of rows 5 and 74 from `fast/003.*/plan.md` and
`fast/002.*/plan.md`") is **unresolvable** — those files do not exist. I will not guess a route, a
payload shape or a response for either.

So, as a **narrowing and never a disarming**, for this run:

1. **Rows 5 and 74 are excluded from the enumeration literal** that step 002 DoD-1 compares against
   `app.routes`. They are excluded *explicitly and by name*, as a recorded, commented exclusion carrying
   this decision's reason — never silently dropped, and never by loosening DoD-1 from set **equality**
   to a subset check. DoD-1 stays an exact two-way comparison over the remaining 72 rows, so an
   unclassified route is still a finding and a missing route is still a finding.
2. **The guard must additionally assert that neither surface exists yet** — no registered route matches
   a bootstrap-from-export or a vector-rebuild/reindex shape. That converts the absence from an
   untested assumption into an armed guard, and it is the same device the delivered suites already use:
   `fast/002`'s "Rebuild guards" (`OUT_OF_SCOPE_CONTROL` = `/\b(rebuild|re-?index)(s|ed|ing)?\b/i`,
   confirmed still armed and passing by 031's verifier) exist precisely to prove the rebuild surface has
   not landed early. If either surface ever appears, this guard fails and 032's enumeration must be
   amended before the route ships — which is the outcome the plan wanted.
3. **The two DoD items that can only be asserted against those surfaces are carried forward, not
   failed and not quietly passed:** **005 DoD-6** (bootstrap-from-export on a configured instance ⇒ 409
   `already_configured`, nothing wiped, nothing echoed) and **006 DoD-7** (the rebuild response and
   progress payload carry no count derived from content volume). Both are recorded as
   `[blocked/unbuilt-dependency]` — neither is a leak finding, neither is a `SPEC` defect in 032's
   table, and both must be asserted by, or against, `fast/002` and `fast/003` when those are planned.
   **006 DoD-1**'s parenthetical "the fast/002 progress/status read if any" resolves to *none*, which is
   not a narrowing of DoD-1 at all — it sweeps every admin GET that exists.
4. `context.md`'s rule "the table names a route that does not exist ⇒ `SPEC`, back to the planner" is
   **not** triggered. That rule is for a route the table believes a *built* feature delivers; here the
   owning features were never planned, the cause is known exactly, and the table already marked both
   rows `_TBD`. Raising `SPEC` would stop all seven steps to re-state a fact the table itself records.

Also carried forward from `context.md`, unchanged and not this feature's to fix: **nginx's own
`access_log` records query strings** (deployment surface, `fast/001` — likewise unplanned). Step 001
fixes uvicorn's access log; nginx's belongs to `fast/001` and is already recorded in `outcome.md` for
the architect.

### Orientation decision 2 — the audit-step red gate, as `context.md` defines it

Steps 002..007 assert properties the built code is **expected already to satisfy**, so the usual
"every new case must be red" rule is inverted for them and the red gate must not be read as a failure
when they pass. Per `context.md` "The audit-step convention": the red gate for an audit step is *tests
compile and import, every `[test]` item is covered and cited, and the tests run*. A test that **fails
against built code is a leak finding** routed to the coder under that step's fix-allowance, not a test
defect — unless the verifier judges the test itself wrong, which is a `TEST` fault. A step whose tests
all pass is `done` with Files Changed = none.

**Step 001 is the sole exception and takes a normal red gate**: the three leaks it closes exist in
built code today, so DoD-1, DoD-4 and DoD-5..7 must be red against current code for the right reason
(sentinel present / `hide_parameters` false).

This also means the global red gate (Phase 4) will be dispatched with an explicitly split expectation —
normal red for 001, compile-and-cover-only for 002..007 — and the global verify (Phase 6) is where a
leak finding would surface. I will tell both verifiers this in writing, because a verifier applying the
default rule would report 002..007's green cases as vacuous and fail the gate, which is exactly the
false FAIL I had to adjudicate on 031's red gate.

### Orientation decision 3 — the skeleton phase is a no-op for six of seven steps

`context.md`: "Skeleton for audit steps is a no-op, except step 002". Step 001 needs a real skeleton
(two changed source files, a new filter). Step 002's skeleton writes **no file** — it freezes the
support module's signatures into `## Skeleton` so steps 003..007 bind to them, and records the exact
HTTP method of every `†` enumeration row from the built routers. Steps 003..007 get no skeleton
dispatch at all; their tests bind to step 002's record. I will record that explicitly in the
`skeleton:` phase line so a resume does not re-dispatch five no-ops.

- harvest: done — docs/.cache/ultra/032.privacy-isolation-audit/harvest.md (3 reports: logging/engine/route-inventory/test-precedent, service seams and seeding paths, admin surfaces and admin frontend)

### Orchestrator decisions forced by the harvest (032)

Every one of these is a **narrowing or a mechanics correction**, never a weakening of a guarantee the
feature exists to prove. Each says what the plan assumed, what is actually built, and what the later
phases must do instead. Numbering continues from the three orientation decisions above.

#### Mechanics the plan got wrong about the platform

4. **`app.routes` holds no `APIRoute`, so DoD-1's stated iteration is impossible.** Under the installed
   FastAPI **0.141.1** `app.routes` holds four plain documentation `Route`s plus fifteen
   `_IncludedRouter` wrappers, so `[r for r in app.routes if isinstance(r, APIRoute)]` is **empty** —
   `002.context.md`'s "Iterate API routes only (FastAPI's `APIRoute`)" would make DoD-1 pass against
   nothing at all, the worst possible failure for an inventory guard. Three mechanisms give the correct
   answer and **all three agree on 72 operations**: `fastapi.routing.iter_route_contexts(app.routes)`
   (reading `.original_route`, `.path`, `.methods`), the recursive walk already used by
   `tests/test_configuration_router.py:1048` and `tests/test_search_router.py:1041`, or
   `app.openapi()["paths"]`. The test-coder uses the **existing in-suite recursive walk**, because it is
   delivered precedent rather than a private FastAPI helper that a future upgrade may move, and must
   assert the walk found a non-zero number of routes before comparing — an inventory guard that can
   silently iterate an empty set is worse than none.
5. **The reconciliation is already clean, which raises the bar for DoD-1 rather than lowering it.**
   72 registered routes against the table's 72 non-TBD rows: **no unclassified route, no table row
   without a route, no method mismatch.** The thirteen `†` methods resolve to **POST** for rows 21, 22,
   27, 28, 32, 33, 56, 57, 58, 59, 64 and 66, with row 65 (`…/available-models`) the only **GET**. So
   DoD-1 is expected green, and the skeleton records these methods as calling interface exactly as
   `002.context.md` instructs.
6. **Enumeration row 47's translation 404 is `message_not_found`** — the generic message code, not a
   translation-specific one. That resolves `context.md`'s "code as declared by 023/003 DoD-3" to a
   concrete literal for step 003 DoD-1.

#### A safety fact that outranks everything else in this feature

7. **Four override seams must all be replaced or the suite makes a real network request.** Missing any
   one lets the real `LlmClient` run. They are: `app.dependencies.get_llm_client_factory` (probe and
   embed), `app.routers.stream.get_chat_client_factory` (compose),
   `app.routers.translation.get_translation_chat_client_factory` (translation), and
   `app.routers.stream.get_tool_registry` (compose tools). The production memo and session tool adapters
   take **no** injected factory and the web adapter takes **no** injected transport, so a compose with
   scripted tool calls needs a **registry override** whose adapters are constructed with injected fakes;
   web search is captured at `GoogleCustomSearchProvider(..., transport=httpx.MockTransport)`, not at a
   module-level factory. **Step 002's world builder owns all four, as one atomic installation**, and
   every later step takes the seam from it rather than re-deriving it. This is a hard constraint, not a
   convenience: a half-installed seam in a privacy audit would reach the user's real configured server.
8. **`tests/llm_fakes.py` is embedding-only.** It has no chat fake, no scripted completions or tool
   calls and no failable probe; chat fakes exist only as file-local copies in `test_compose_route.py`,
   `test_compose_source.py` and `test_translation_router.py`, and **no existing test drives the compose
   route with a scripted tool call and a real tool**. Step 002's support module must therefore *build*
   the chat fake (scripted completions, scripted tool calls with caller-chosen arguments, failure with a
   caller-chosen message, and a record of what it was asked), consolidating those three file-local
   copies rather than importing from a test module. It must not modify `llm_fakes.py`, which is
   delivered and used elsewhere.
9. **`app/main.py:165` runs `create_app()` at import, so the real `configure_logging` runs at collection
   and reads `backend/.env`.** That is pre-existing, is how all 4515 delivered tests already run, and is
   **not** this feature's to change. Its consequence is for steps 001 and 007: global loguru and stdlib
   logger state is already mutated before any fixture runs, `logging.py` additionally silences `httpx`
   at `CRITICAL+1` via `_SILENCED_LOGGERS` (which `001.context.md` does not mention), **no fixture
   anywhere restores a logger's `.filters`**, and `test_web_search_google.py` restores neither the named
   loggers nor the `httpx` level. So both step 001's and step 007's tests must **snapshot and restore**
   every logger attribute they touch — level, handlers, `propagate` and `.filters` — and step 001's
   filter installation must be **idempotent**, since `configure_logging` can run more than once per
   process and a filter appended twice would be a latent bug the tests would not otherwise catch.

#### DoD items whose stated witness is impossible, and the witness that replaces it

10. **004 DoD-1 cannot be "all five groups empty", and the privacy property it exists to prove is a
    different sentence.** My-search's vector arm has **no similarity cutoff**: it returns the nearest 50
    of *the caller's own* rows whatever the query, so A searching for B's sentinel legitimately gets
    A's own memos and sessions back. Only `characters` and `setups` (LIKE) and `entries` (full-text
    only) can be empty. The audit's actual claim — `brief.md`'s "no search reaches another user's
    material" — is **"no group contains any B id or any B sentinel"**, and that is what DoD-1 is
    asserted as, with the positive control (B's identical request returns the item) kept intact. This
    narrows the literal wording to the real guarantee; it does **not** narrow the guarantee. A leak
    would still fail it.
11. **004 DoD-6's `tool_args` carve-out, bounded so it cannot hide anything.** `tool_args` echoes the
    model-supplied arguments onto the wire, and DoD-6's fake model is *instructed by the test* to name
    B's ids and sentinels — so a literal "no B id in the tool rows" reading fails on the test's own
    input, which is not a leak: those values never came from the database. DoD-6 is therefore asserted
    on the tool **results** and the assistant message, with `tool_args` excluded **and** pinned by an
    exact equality against what the fake was scripted to send. The exact pin is what keeps it armed:
    nothing database-derived can hide in a field whose entire contents are compared to a known literal.
12. **007 DoD-5 needs the right exception class, and the wrong one is worth asserting too.**
    `translate_message` maps only `LlmUnreachableError` to a handled failure; any other class
    **propagates unhandled**. So the handled path is driven with `LlmUnreachableError` carrying a
    sentinel message, and the unhandled path — where an exception's own message reaches a generic
    handler or the traceback — is the more dangerous one for a log leak and is asserted as well. Both
    are inside DoD-5's words ("a translation whose fake model fails with a sentinel-bearing exception").

#### Seeding and payload mechanics the test-coders must follow exactly

13. **Seeding order is forced by built validation**, and a wrong order produces 409s that would look
    like findings: enable models **before** creating any session (a session captures its model at
    creation); enable the embedding model **before** designating it (`validate_embedding_model` rejects
    an unenabled one); designate the embedding model **before** any memo create, character-sheet PATCH
    or setup-description PATCH (those embed **strictly** and answer 409 without a designation). Settle,
    reopen, partner-file and record-edit instead **skip vectors silently** and return
    `search_coverage_incomplete: true`. Designation through the route works with the fake factory and
    needs no network.
14. **Several of `002.context.md`'s sentinel carriers do not exist.** `schema.sessions` has **no** text
    column, so "session title, partner label" cannot carry a sentinel; the session-level carriers are
    `system_prompt` and the text embedded into `session_vec`. "User settings" are two **columns on
    `users`**, and character and session configuration are **columns, not tables**. The coverage list's
    intent ("every table with a user-owned row") is satisfied against the real schema; the skeleton
    records the actual carrier for each listed item so DoD-4's "every registered sentinel is stored
    somewhere" is checkable rather than aspirational.
15. **Memo reach is derived, not stored.** There is no `reach` column: it is computed from `is_enabled`
    and `is_forced`, and both scope and reach are `Literal`s rather than enums. A memo with a **foreign
    `scope_id` answers 404**, so step 003 DoD-6's disjunction ("refused with 404 **or** creates an inert
    row") resolves to its first branch — the DoD passes as written and the second branch is dead.
16. **005 DoD-2 only reaches the rewrite path under a specific payload shape.** A `user`-granularity
    import whose rows' `user_id` differs from the payload's own `users` row id answers **400
    `export_invalid` / `malformed_payload`**, not a rewrite. To exercise "every imported row owned by
    the caller whatever the payload says", the payload must either carry B's id as the `users` row id
    too, or be at `character` granularity. `005.context.md` already says to build payloads from a real
    export and mutate ids; this fixes *which* mutation reaches the rule.
17. **005 DoD-1's absence set must exclude two things or it fails for the wrong reason.** User and
    database exports **exclude `translations`**, so the translation sentinel cannot be in A's export and
    must not be looked for there; and `model_server_id` is an **instance-wide server id**, not a B id,
    so a naive "no B id" sweep over every seeded id would flag it. Both exclusions are recorded with
    their reason and are narrow: every other B id and every other B sentinel stays in the set.
18. **Index snapshots cannot use a plain `SELECT`.** There is **no `session_fts`**; `message_fts` holds
    only settled, unburied rows; and a plain `SELECT` on an external-content FTS table **reads through
    to the base table**, so a before/after comparison over it would compare the wrong thing. Step 004's
    DoD-9/10 snapshots use `MATCH` or the `*_docsize` shadow tables.

#### The audit's first real finding, found during the harvest

19. **`refresh_session_vectors(conn, user_id, session_ids)` deletes a session's `session_vec` row
    without an owner predicate**, so `refresh_session_vectors(conn, A, [B_session])` removes B's vector —
    contradicting the module's own docstring. **Not reachable from any route**: every caller passes
    owner-scoped ids, so there is no attack path and no user-visible leak today. It is nevertheless
    exactly what `context.md`'s leak-fix policy calls a **small leak** — "an owner predicate missing
    from one query" — and it sits squarely inside **step 004's fix-allowance** (024's vector write
    paths, `backend/app/services/`). So: step 004 **fixes it** by adding the owner term to that
    statement, and step 004's tests **pin it** so a future refactor cannot reopen it. This is a finding
    the audit was built to catch, and it is being closed rather than merely recorded.
    Note for the verifier: this makes step 004 the one audit step expected to have a **non-empty Files
    Changed**, which must not be read as scope creep.

#### Decisions forced by report 3 (admin surfaces and the admin frontend)

20. **`GET /api/admin/database/export` must be excluded from step 006 DoD-1 and DoD-2, and the reason is
    the plan's own boundary.** `admin_db.py` has **five** routes, not three, and that one returns the
    whole database **including every user's content by design**. An "every admin GET" loop would find
    B's sentinels in it and report a leak that is not one. The enumeration already routes row 72 to
    **step 002** ("role gate only — opacity is 030's"), and `context.md`'s **Out** says the
    whole-database export's opacity rule is 030's, cited and never re-tested here. So DoD-1 and DoD-2
    sweep every admin GET **except** that one, by name and with this reason recorded inline; its role
    gate stays armed in step 002 DoD-2/DoD-3, and 005 DoD-7 remains the verifier's confirmation that
    030's opacity items are `done`.
21. **`POST /api/admin/database/import` is destructive and DoD-3's mutation loop must never reach it on
    an empty instance.** With A and B holding content it answers **409 `database_not_empty`**, which is
    the safe state and exactly what 005 DoD-5 asserts — but on an empty database the same call **wipes
    and replaces it**. Step 006 DoD-3's "every admin mutation" loop therefore runs it only against the
    fully seeded world, never after a teardown or in a fixture whose ordering could leave the database
    empty, and the test must assert the 409 rather than tolerating any 2xx. A mutation loop that wiped
    the audit world mid-run would turn every later absence assertion vacuously green — the precise
    failure mode this feature exists to prevent.
22. **Step 006 DoD-7 is confirmed to have no built target**, independently of orientation decision 1:
    `admin_db.py`'s own docstring records that there is no rebuild route, and `fast/002` holds only
    `brief.md`. It stays `[blocked/unbuilt-dependency]`, as does 005 DoD-6.
23. **Step 003 DoD-5's witness narrows for the `user` scope only.**
    `GET /api/memos?scope=user&scope_id=<B's user id>` **drops `scope_id`** and returns the caller's own
    user-scope memos, so "an empty list or a 404" holds there only if A happens to own no user memos —
    and the audit world deliberately seeds some. This is correct behaviour, not a leak: user scope *is*
    the caller. DoD-5's operative clause is its last one, **"and never a B memo"**, and that is what is
    asserted for the `user` scope, with the positive control kept. The `character`, `setup` and
    `session` scopes **do** answer 404 with B's ids, so DoD-5's literal wording holds unchanged for
    three of its four cases.
24. **Step 006 DoD-9's matcher must be whole-identifier *and* comment-stripped**, and the harvest shows
    why both halves matter. A naive substring match produces about fifty false positives: `inUse`
    matches inside `AdminUser…` (`Adm-inUse-r`), and `account` contains `count`. `006.context.md`
    already requires whole-identifier matching, so that half is the plan's. The comment half is mine:
    the bare word `count` appears **eight times, all in comments**, so an un-stripped scan would fail
    DoD-9 on prose that renders nothing. The scan strips comments first, following the repo's existing
    source-scan helpers, which already do. Confirmed clean either way on the real forbidden list:
    **zero whole-word hits** for every name and for `used_by`, `usedBy`, `dependent`, `sessions use`,
    `sessions using` and `in use by`.
25. **Step 006 DoD-8 is already clean and its boundary is confirmed.** Every `/api/` literal under
    `frontend/src/admin/` begins with `/api/admin/`; the only `/api/me` occurrences are in **comments**,
    and the actual `/api/me` request lives in `shared/currentUser.ts`, outside the scanned directory —
    which is exactly the boundary `006.context.md` draws ("shared client code the admin entry imports
    from outside is not scanned"). No non-allowed prefix exists.
26. **Step 006 DoD-10's `[manual/live]` wording outruns the UI, and narrows to the confirms that
    exist.** There is **no confirm for disabling a model** — `EnabledModelsModal` is a checkbox list
    plus Save — so "the model-disable confirm shows no number" has no target. The confirms that do
    exist are user-disable, server-delete, embedding-clear, lossy Sync and whole-database replace, and
    **none contains a number**. The live check is against those five.
27. **One adjudicated non-finding worth stating out loud, because it is a real tension in the brief's
    absolute wording.** The admin Database page renders "Export downloaded" plus a **formatted file
    size**, which *is* a number derived from user-content volume — and `brief.md` forbids "a count
    derived from any of it". It is nevertheless not a finding: **US-078 authorises it**, the whole-DB
    export is governed by 030's opacity rule rather than by this sweep, and the admin who just
    downloaded the file already holds it, so the number discloses nothing they do not have. It matches
    no forbidden name. Recorded here, and worth an `outcome.md` line for the architect, because the
    brief's phrasing is absolute while the delivered product has one authorised exception to it.
28. **A correction to my own earlier note, so no one chases it:** `FORBIDDEN_SURFACE` is a **backend**
    symbol, in `backend/tests/test_admin_db_router.py`'s OpenAPI-vocabulary clause — not a frontend one.
    It is not in `frontend/tests/`, and step 006's frontend test binds to the frontend source-scan
    precedents quoted in report 3 §C instead.
29. **`GET /api/sessions` does accept `include_archived`** — as do `/api/characters`,
    `/api/characters/{}/setups` and `/api/characters/{}/sessions` — returning the union of working and
    archived items, with `archived_at` the only marker. This does **not** contradict 031's record that
    the frontend's `loadSessions` never sends a query: that was the *store's* behaviour, this is the
    *route's* capability, and both are true. Noted so no later step "fixes" the frontend to send a
    parameter it deliberately omits.

- skeleton: done — steps **001 and 002 only**, by design (orientation decision 3: `context.md` says
  "Skeleton for audit steps is a no-op, except step 002"). Steps 003..007 get **no skeleton dispatch**;
  their tests bind to step 002's frozen record. No escape valve from either step. Both gates clean after
  each: `mypy app` "Success: no issues found in 94 source files", `ruff check .` "All checks passed!".

### Step 001's skeleton — one new symbol, two changed contracts

`AccessQueryRedactionFilter(logging.Filter)` with `filter(self, record) -> bool` (return type narrowed
from typeshed's `bool | LogRecord`), constructed no-arg, placed between `InterceptHandler` and
`configure_logging`. Its docstring freezes that it rewrites **`record.args[2]`** only, keeps the path,
drops everything from the first `?`, leaves a query-less target exactly as it was, **never drops a
record**, and is installed on the **logger** so it runs before `InterceptHandler` pre-formats via
`record.getMessage()`. `configure_logging(settings)` and `get_engine(settings)` keep byte-identical
signatures; only their docstring contracts changed — every sink gets `diagnose=False` **and**
`backtrace=False`, the filter install is **idempotent** (decision 9), and `get_engine` hides bound
parameters with `engine.hide_parameters` as the read-back accessor, the per-path `_engines` cache and
every other option unchanged. No caller-compile edit was needed anywhere.

**One clause passes against the stub and must not be read as vacuous: 001 DoD-3** ("a target with no
query string is emitted unchanged") asserts the *absence* of a rewrite, which a stub trivially
satisfies. The red gate is told so explicitly. DoD-1, DoD-2, DoD-4, DoD-5, DoD-6 and DoD-7 are red for
the right reason (sentinel present / `hide_parameters` False).

### Step 002's skeleton — a record only, no file written

`backend/tests/privacy_audit_support.py` is a Test file, so the skeleton wrote **none of it** and froze
its signatures instead: constants (`UNKNOWN_ID`, the four `FAKE_SEAM_OVERRIDE_KEYS`, the derived-store
table names), the identity/client types, the seeded-content types (including a **12-combination** memo
cross product of scope × reach), the `SentinelRegistry` with its full carrier table, the atomic
`install_fake_model_seam` context manager, the assertion helpers, the log-capture manager, the
enumeration literal and the route-walk helpers, and the `audit_world` builder with its `real_logging`
switch. Module is importable as `from tests.privacy_audit_support import …` (`tests/__init__.py`
exists), is **not** collected (no `test_` prefix), is **not** a mypy target (`files = ["app"]`) but
**is** ruff-linted.

Three parts of that record matter more than the rest:

1. **The fake seam is frozen as one atomic install with a single entry point** — `install_fake_model
   seam(...)` sets **all four** override keys or none, is called exactly once by `audit_world`, and
   **no later step may set any of the four itself**. Decision 7 is the reason: a half-installed seam
   lets the real `LlmClient` run, which in a privacy audit would mean a real request to the user's
   configured server. The registry it builds uses constructor-injected `MemoSearchTool` /
   `SessionSearchTool` and a `GoogleCustomSearchProvider` over an `httpx.MockTransport` recorder. Noted
   in the record: `conftest.py` blanks `SEARCH_CSE_KEY`/`SEARCH_CSE_ID`, so the *production* registry
   would omit `web_search` entirely — another reason the override is required rather than optional.
2. **`ENUMERATED_ROUTES` is exactly 72**, with `EXCLUDED_ROWS` naming rows 5 and 74 **inline with their
   reason**, and `UNBUILT_SURFACES` arming the absence of both (row 74 with no allowed path; row 5
   allowing only `/api/bootstrap/create`). DoD-1 stays exact two-way set equality. Per decision 4 the
   walk is the delivered `_api_routes(routes, found, seen)` shape from `test_search_router.py:1041` /
   `test_configuration_router.py:1048`, and **both `api_routes` and `route_operations` raise
   `AssertionError` when the walk finds nothing** — an inventory guard that can iterate an empty set is
   worse than no guard at all.
3. **The log capture restores more than the precedent does** — `level`, `handlers`, `propagate` **and**
   `.filters` per logger, because nothing in the suite restores `.filters` today and step 001 is adding
   one.

### The thirteen `†` methods — independently confirmed, no disagreement

Read from the decorators a second time and identical to the harvest: **POST** for rows 21
(`characters.py:147`), 22 (`:158`), 27 (`setups.py:157`), 28 (`:168`), 32 (`sessions.py:177`), 33
(`:188`), 56 (`admin_users.py:83`), 57 (`:93`), 58 (`:103`), 59 (`:114`), 64 (`admin_llm.py:140`), 66
(`admin_llm.py:174`); **GET** for row 65 (`admin_llm.py:160`, `list_llm_server_available_models`). Each
`†` path has exactly one registered method. The route guard's foundation holds.

### Rows 5 and 74 — confirmed unbuilt a third time, nothing invented

`docs/plans/fast/001.dev-and-container-harness/`, `fast/002.vector-index-rebuild/` and
`fast/003.bootstrap-from-export/` each hold **only `brief.md`** — no `plan.md`, no `status.md`, no
`## Skeleton`. No route under `backend/app/` contains `rebuild`, `reindex` or `vector`;
`app/routers/admin_db.py:24`'s own docstring states there is "no rebuild route anywhere on this
router"; `bootstrap.py` registers only `POST /create`. No method, path, payload or response was
invented for either row.

### Four more plan-versus-schema corrections the skeleton found (decision 14 extended)

30. **`memos` has no `title` column** — the table is `scope`, `scope_id`, `body`, `is_enabled`,
    `is_forced`, `sort_key`, timestamps. `002.context.md`'s "memo title/body per memo" resolves to
    **`body` alone** as the sentinel carrier.
31. **"my-search target words" is not a carrier at all** — it has no registry key, because my-search's
    targets *are* the stored sentinels. Recorded so no step looks one up and reports a missing sentinel.
32. Confirming decision 14 against the real schema: the session-level carriers are
    `sessions.system_prompt` plus the text embedded into `session_vec`; "user settings" are
    `users.rp_language` and `users.preferred_language`; character configuration is
    `characters.system_prompt`; session configuration is `sessions.system_prompt`.
33. The step file's "**the** client-factory seam declared by 019/021" (singular) is frozen as **four**
    seams in one atomic install, and the chat, probe and web fakes are **new** support-module code
    consolidating the file-local copies in `test_compose_route.py`, `test_compose_source.py` and
    `test_translation_router.py`. `tests/llm_fakes.py` is embedding-only and is **not** modified.

- tests: done — steps 001..007. **Nine new files: one shared support module, seven backend test modules
  and one frontend test module.** No step amended a delivered test file — 032 adds guards and does not
  touch other features' tests, so this is the first feature of the run with **no blast-radius sweep and
  no amendment site**.

### Test inventory going into the red gate

| Step | New file(s) | Size | Test functions | World builds |
|---|---|---|---|---|
| 001 | `backend/tests/test_logging_redaction.py` | 8 functions | 8 | — (no world) |
| 002 | `backend/tests/privacy_audit_support.py` (**support, never collected**) + `test_privacy_audit_routes.py` | ~1575 + ~400 lines | 11 | 11 |
| 003 | `backend/tests/test_privacy_audit_owner_sweep.py` | 740 lines | 4 | 4 |
| 004 | `backend/tests/test_privacy_audit_search_tools.py` | 1108 lines | 5 | 5 |
| 005 | `backend/tests/test_privacy_audit_export_import.py` | ~630 lines | 4 | 4 |
| 006 | `backend/tests/test_privacy_audit_admin.py` + `frontend/tests/adminPrivacyAudit.test.ts` | ~660 + ~290 lines | 4 + 2 | 4 |
| 007 | `backend/tests/test_privacy_audit_logs.py` | ~960 lines | 4 | 3 |

**All 58 `[test]` DoD items covered and cited.** `privacy_audit_support.py` carries no `test_` prefix so
it is never collected; it **is** ruff-linted and is **not** a mypy target (`files = ["app"]`).

### What the red gate must expect, because this feature inverts the usual rule

Per `context.md` "The audit-step convention" and orientation decision 2, **steps 002..007 are audit steps
and their cases are expected GREEN** — the gate for them is *the files import and compile, every `[test]`
item is covered and cited, and the tests run*. A green is the audit passing, not a vacuous test. Only
**step 001** takes a normal red gate.

| Expectation | Items |
|---|---|
| **Red for the right reason** (step 001's three leaks exist in built code today) | 001 DoD-1, DoD-2, DoD-4, DoD-5, DoD-6, DoD-7 |
| **Green against the stub, accepted and recorded in advance** | 001 DoD-3 — it asserts the *absence* of a rewrite (no query string ⇒ emitted unchanged), which a do-nothing filter satisfies trivially. It is the guard that stops the coder over-rewriting. **Not** a vacuous pass. |
| **Deliberate true-red — the audit's one real catch** | 004's `refresh_session_vectors` pin (decision 19), isolated in its own test function and its own world build so its pre-fix failure cannot be misread as a DoD-9 route failure or a DoD-10 failure. **Must be green at verify.** |
| **Red at the gate only because step 001's coder has not run yet** | the **console-text** clause of 007 DoD-3, DoD-4 and DoD-5. The console sink still carries loguru's default `diagnose=True`, so a traceback rendered there prints frame locals holding the sentinel the test just raised. Each failure message quotes the surrounding text and states both readings so the gate can attribute the cause. **Must be green at verify.** The **capture-sink** clause of those same three items is step-001-independent and is expected green now. |
| **Green** (everything else) | 002 DoD-1..6 · 003 DoD-1..11 · 004 DoD-1..8, DoD-10 and the route half of DoD-9 · 005 DoD-1..5 · 006 DoD-1..6, DoD-8, DoD-9 · 007 DoD-1, DoD-2, DoD-6..9 |

### Two DoD items carried as `[blocked/unbuilt-dependency]` — not failed, not quietly passed

- **005 DoD-6** — bootstrap-from-export on a configured instance. Owner **`fast/003`**, which holds only a
  `brief.md`.
- **006 DoD-7** — the vector-rebuild response and progress payload carrying no content-derived count.
  Owner **`fast/002`**, likewise `brief.md`-only.

Neither has a behavioural test, and **no route, payload, progress shape or response was invented for
either**. Both instead reuse step 002's `UNBUILT_SURFACES` to assert the surface **still does not exist**,
each with an anti-vacuity control so the guard cannot pass by matching nothing: step 005 pins
`/api/bootstrap/create` present, step 006 shows the pattern matches two synthetic rebuild paths and that
the route walk is non-empty. If either surface ever lands, the guard fails and the DoD must be
implemented before the route ships — the outcome the plan wanted.

### The anti-vacuity devices, recorded because they are what make a green mean something

An audit that passes is otherwise indistinguishable from an audit that asserts nothing, so every step
built a control:

- **002 DoD-4** is the anti-vacuity gate for all five later sweeps: every coverage table holds a row owned
  by A **and** one owned by B, and every `stored=True` sentinel is found by an owner-scoped `LIKE`. 62
  sentinels, each a single lowercase alphanumeric token, all distinct, none a substring of another, none
  appearing in any username, server name or model name.
- **003** partitions and asserts the write-body table — **12 bodied writes + 10 declared bodyless writes +
  13 reads = 35** — so a row can never silently lose its body and refuse with a 422 instead of by the
  owner predicate. DoD-9's "the fake model receives no call" is asserted as a **delta** with
  `call_count > 0` checked first, so the clause cannot pass because the fake never records anything.
- **004** asserts B's `session_vec` row is present *before* the decision-19 pin, with A's own refresh as
  the positive control.
- **005** asserts both users' content is non-empty *before* the destructive 409 call, and drops the
  `translations` sentinel from the positive control only while still asserting it **absent**.
- **006** ships **matcher self-tests** — 5 flagged + 10 clean cases for DoD-8, 20 flagged + 14 clean for
  DoD-9 — pinning both what must match and what must not, including `formatByteSize(state.exportSizeBytes)`
  as a must-stay-unflagged case (decision 27). DoD-3's coverage is an exact set:
  `exercised ∪ {import} == 15 admin non-GET rows`.
- **007** opens every capture window with a control emitting one loguru record **and** one stdlib record
  through the `InterceptHandler` bridge, asserting both reached the capture sink *and* the real console
  sink. DoD-1's 48 driven rows are matched **two-way** against `ENUMERATED_ROUTES`. DoD-9 asserts the root
  logger is at or below DEBUG first, so the two WARNING levels are shown to be load-bearing.
- **002's route guard** raises `AssertionError` when the walk finds nothing (decision 4) — an inventory
  guard that can iterate an empty set is worse than no guard at all.

### Test-coder resolutions the verifier should see

1. **002 — memos are seeded before the compose exchange**, not after as the frozen order list sketched,
   because the `messages.tool_payload[content]` carrier can only be stored if the scripted `memo_search`
   finds something, and that tool reaches only *searchable chain* memos. Every constraint decision 13
   protects still holds. The tool-result sentinel is planted in the searchable session-scope memo body
   rather than routed through `web_search`, which would have made the world depend on the Google response
   shape that no plan document or frozen record states. The `web_search` fake is still installed — the
   seam is atomic — and the world asserts it was **never called**.
2. **003 DoD-7's 409** asserts no B *sentinel* in the refusal but deliberately **not** the absence of B
   *ids*: A supplied those ids in the request itself, so echoing them back discloses nothing. Same logic
   as decision 11's `tool_args` carve-out; asserting their absence would have manufactured a false
   finding.
3. **003 row 53** (`POST /api/characters/{}/import`) sends a **real session export of A's own session**, so
   the 404 is the owner predicate rather than a 400 on a malformed body.
4. **004 DoD-8's "003 DoD-6 case"** resolves to a forced `user`-scope memo of A's whose body names B's
   session id, asserted *before* the composes (which deliberately put B's ids into A's own tool-call
   arguments, and context legitimately replays those), then deleted again.
5. **005 exercises both branches of decision 16** — DoD-2 takes `character` granularity with every row id
   remapped **injectively onto B's live twin ids**, so payload-internal references stay resolvable and the
   refusal path is not hit; DoD-3 takes A's own self-consistent `user` envelope.
6. **006 DoD-8's "exact set"** applies to the offence list (exactly empty) and to the allowed-prefix list,
   **not** to the set of found literals — pinning every literal would fail when the admin entry
   legitimately adds a path under an allowed prefix, which DoD-8's own wording permits. **DoD-3 pins no
   success status**, only "carries no sentinel", asserting instead that the response is not
   401/403/404/405/422 so the handler is known to have run; that avoids inventing an expected status for
   `…/tables/{}/create` against an already-created table.
7. **007 deliberately does not sweep the captured record's `formatted` field**: it is rendered with the
   *capture sink's own* `diagnose`/`backtrace`, so a frame local there would say nothing about the
   application's sinks. The three fields every DoD item names — `message`, `repr(extra)` and
   `exception_text` — are swept, plus the **real console sink's text** and the real **log file**, the
   latter being the surface DoD-10 checks live. DoD-2 allows a bodied row to answer 404 **or** 422 (a 422
   means the body is not that row's shape, which is still a refusal path), because the
   exact-404-with-valid-bodies contract is step 003 DoD-1's and is not re-asserted here; driver problems
   are collected in a separately labelled list so a body-shape mismatch can never read as a log leak.

### Two things the red gate must do that are not usually its job

1. **Run `ruff check .` — it has not been run on a single one of these nine files.** None of the seven
   test-coders had a shell tool in its session, so every file was written to the configured rules by
   inspection only (≤120 columns, `E,F,I,B,UP,W`, isort `order-by-type`, no unused imports, no closure
   defined in a loop, no `str.format`). Likewise `npm run typecheck` has not been run against
   `frontend/tests/adminPrivacyAudit.test.ts`. A lint or typecheck failure here is a **mechanical** fault
   to route back to the owning test-coder — not a leak finding.
2. **Report the wall-clock cost.** The six world-building steps build the audit world **31 times** in all
   (002: 11, 003: 4, 004: 5, 005: 4, 006: 4, 007: 3), each build about 120 requests plus two composes,
   because `conftest.py`'s `db_settings` is function-scoped. The backend suite already ran **434s** at
   031's verify. If the added cost is disproportionate, the remedy is a **coarser fixture, never a weaker
   assertion** — steps 003..007 already batch clauses into few builds, so step 002's eleven per-clause
   builds are the obvious place to consolidate first.

- red-gate: **PASS (run 2)** — all seven steps PASS. Run 1 returned **FAIL / Fault TEST** on steps 002,
  006 and 007 for **four mechanical faults**, every one of them real; all four were fixed by their owning
  test-coders in a single round and verified in run 2. **All four static gates clean**: `ruff check .`
  "All checks passed!", `mypy app` 94 files, `npm run typecheck` exit 0, `npm run build` 779ms. Backend
  **4555 collected — `8 failed, 4547 passed, 1 warning in 462.94s`**; frontend **151 files / 4363 tests,
  all passed**. **No pre-existing test regressed on either side.** Every one of the 8 failures is
  category (b), **expected red**: step 001's seven, plus the decision-19 pin. No leak finding beyond
  decision 19, and no `TEST` fault left standing.

### The four run-1 faults, all genuine

| # | Step | Fault | Why it mattered |
|---|---|---|---|
| 1 | 002 | `ruff` **I001** at `test_privacy_audit_routes.py:20` | The **first** time `ruff` had ever run against any of the nine new files — no test-coder on this feature had a shell tool, so every file was written to the rules by inspection only. One file failed. |
| 2 | 006 backend | The DoD-9 matcher self-test compared the matcher's output as an **ordered tuple** | Not a matcher miss — an ordering assumption. But it sat at the **start** of the function carrying DoD-1, DoD-2, DoD-5, DoD-6 **and** DoD-7, so **five DoD items were never reached in run 1**. Fixed to a set comparison; run 2 reached all five and the whole function is **green — no leak**. |
| 3 | 006 frontend | `isAllowedLiteral` used `startsWith("/api/me")`, admitting **`/api/memos`** and `/api/members` | **A genuine hole in the DoD-8 guard**, not a test bug: a real admin-entry call to the user-content memos route would have passed. Fixed to require a segment boundary (end, `/` or `?`) after the bare prefixes; `/api/admin/` and `/api/auth/` already end in `/`. Self-tests now **6 flagged + 12 clean**. |
| 4 | 007 | The console witness was **never armed** | `monkeypatch.setattr(sys, "stderr", console)` ran in **fixture setup**, but pytest's capture plugin re-installs its own `sys.stderr` at the start of the **call phase**, discarding it — and loguru binds the stream current at `add()` time, with the real `configure_logging` running inside `audit_world` in the call phase. So the sink bound pytest's stderr and the second witness observed nothing, which also left the step-001 attribution unverifiable. Fixed with a `bound_console()` context manager opened as the **outermost** `with` inside each test body. |

**Fault 3 is the single best argument for the matcher self-tests.** They were written to pin both what
must match and what must not, and they immediately caught a real weakness in the guard they test. That is
the difference between an audit and a test that asserts nothing — and the reason a feature whose expected
outcome is *green* still needs them.

### A recorded expectation that did not materialise, and the correction

I recorded that the **console-text** clauses of **007 DoD-3, DoD-4 and DoD-5** would be *red at the gate
only because step 001 is unimplemented, and green at verify*. With the witness now armed, **they are
green already**, and the verifier established why: nothing in `app/` emits an exception through a loguru
sink on those paths. The only `exception=` site is `InterceptHandler`, reached via `exc_info`, and under
`TestClient` an unhandled exception is **re-raised to the test** rather than logged — uvicorn, which would
log it in production, is not in the loop. So no traceback is rendered to the console and `diagnose=True`
has nothing to render.

**The consequence matters: those three clauses do not guard step 001's `diagnose=False` at all.** The only
guard for it is **001 DoD-4**, which is red now and must be green at verify. My prediction was wrong in a
way that would have been invisible had the witness stayed unarmed — recorded here rather than quietly
dropped, because the next person to touch `diagnose` needs to know which test actually protects it.

### Timing — the performance concern is closed

Backend **462.94s** against 031's **434s**: **+29s, about +7%**, for **+40 cases** and 31 audit-world
builds. Run 1 measured 473.06s, so run 2 is 10s faster. Per new module: 002 **14.1s** (eleven builds),
003 **6.8s**, 004 **6.8s**, 005 **6.8s**, 006 **5.2s**, 007 **4.0s**, 001 **0.1s**. Nothing is
disproportionate, so **no fixture consolidation is wanted** — the remedy would have been a coarser
fixture and never a weaker assertion, and it is not needed.

### Confirmations carried into the code phase

- **The four-seam check is clean.** Only `backend/tests/privacy_audit_support.py` references any of
  `get_llm_client_factory`, `get_chat_client_factory`, `get_translation_chat_client_factory` or
  `get_tool_registry`, and `install_fake_model_seam` **raises** if any is already overridden. **No network
  request was made** across the whole suite. This was the feature's largest risk and it is held.
- **Rows 5 and 74**: `EXCLUDED_ROWS` is still `{5, 74}` with the reason inline against the 74-row
  enumeration, and step 002 DoD-1 remains exact set equality over the other 72 rows, green.
- `tests/llm_fakes.py` and `tests/conftest.py` **unmodified**. No new file references
  `rphelper.sqlite` or sets `RPHELPER_DB_PATH`. Steps 002..007 wrote **no** source file; the only modified
  tracked sources are `app/logging.py` (the `AccessQueryRedactionFilter` stub, whose `filter` raises, plus
  docstrings) and `app/db/engine.py` (docstring only) — **skeleton changes with no behaviour implemented**.

### Two record corrections from the gate

34. **`005.export-import-sweep.md` DoD-7 cites "030/008 DoD-7", and 030 has no step 008.** 030 has steps
    001..006 only. The citation is a **plan typo**. What DoD-7 actually asks for is satisfiable: 030/005
    (`005.admin-database-export.md`) is **`done / PASS`**, and it is the step that owns the
    whole-database export's opacity rule. Recorded for `outcome.md` so the planner can correct the
    citation. 030/005 carries **12** DoD items (10 `[test]`, 2 `[manual/live]`), not the 9 stated in the
    gate's first pass — the gate corrected itself on re-read.
35. **`backend/data/logs/rphelper.log` is appended to by any suite run, and it pre-dates 032.**
    `app/main.py:141` calls `configure_logging(settings)` in the app factory, last changed by **`e5b25a0`
    (feature 030)**; 032 does not modify `main.py`, and changes only `configure_logging`'s **docstring**
    plus the new stub class, leaving the body untouched. So no 032 file causes it. Step 007's own tests
    correctly point `RPHELPER_LOG_FILE_PATH` at `tmp_path`. Not a leak and not this feature's to fix —
    recorded for `outcome.md` as an operator-side observation for the architect, alongside nginx's
    `access_log` (`fast/001`).

- code: done — **steps 001 and 004 only**. The other five steps are audits that **passed with no source
  change at all**, which is `context.md`'s stated outcome for an audit step ("a step whose tests all pass
  is `done` with Files Changed = none"), so no coder was dispatched for 002, 003, 005, 006 or 007. No
  re-freeze, no escape valve. Both coders reported `mypy app` "Success: no issues found in 94 source
  files" and `ruff check .` "All checks passed!".

### Step 001 — the three plan-time leaks, closed

`backend/app/logging.py`: `AccessQueryRedactionFilter.filter` rewrites **only** `record.args[2]`, and only
when `args` is a tuple of length ≥ 3 whose index 2 is a `str` containing `"?"` —
`args[:2] + (target.split("?", 1)[0],) + args[3:]`. It **always returns `True`**: `None` args, mapping
args, a short tuple and a non-string at index 2 all pass through untouched, so no record is ever dropped
or mangled. Both sinks now carry `diagnose=False` **and** `backtrace=False` (the console sink previously
passed only `level=`; the file sink left `backtrace` defaulting). The filter is installed on the
`uvicorn.access` **logger**, after the `_PROPAGATING_LOGGERS` loop and before `_SILENCED_LOGGERS`.
`backend/app/db/engine.py`: `create_engine` gains exactly one option, `hide_parameters=True`; URL,
`connect_args`, both event listeners and the per-path `_engines` cache unchanged.

**Idempotence (decision 9)** is remove-then-add by type: iterate a copy of `access_logger.filters`,
`removeFilter` every `isinstance(..., AccessQueryRedactionFilter)`, then add one. Two
`configure_logging` calls leave exactly one, and it self-heals if a fixture restores a filter list —
which matters because `app/main.py` runs `create_app()` at import and nothing in the suite restores
`.filters`.

**A judgement call to flag at verify:** the shape guard accepts any positional tuple reaching index 2
(`len(args) >= 3`) rather than pinning uvicorn's exact `len(args) == 5`. The frozen contract says the
filter "rewrites `record.args[2]`" and no more. The cost is that a hypothetical 3- or 4-argument record on
`uvicorn.access` whose third argument happened to contain `?` would also be stripped. Tightening to
exactly five arguments is a one-line change if the verifier judges DoD-3 to require it.

**Probe:** 15 checks, all passing — exactly one filter after two `configure_logging` calls; the sentinel
absent from console, log file and a level-0 sink while `GET`, `/api/search` and `200` survive; a
query-less target unchanged; three non-uvicorn shapes neither dropped nor mangled; a frame-local sentinel
absent while the raising frame's name is still printed; `engine.hide_parameters is True`; 8 SQL records at
INFO with no bound sentinel; and the `IntegrityError` reading
`[SQL: INSERT INTO probe (id, body) VALUES (2, ?)] [SQL parameters hidden due to hide_parameters=True]`.

### Step 004 — the audit's one finding, closed

`backend/app/services/session_index.py`, in `refresh_session_vectors`. The empty-text branch deleted the
`session_vec` row of **any** id whose composed text was empty — and a **foreign** session composes to
`""`, so a foreign id's row was deleted. The empty-text ids are now resolved through **one owner-scoped
read** before the loop, and only the caller's are deleted:

```python
empty_ids = {session_id for session_id, session_text in composed if not session_text}
owned_empty_ids: set[int] = set()
if empty_ids:
    with _reading(connection):
        owned_empty_ids = {int(row.id) for row in connection.execute(
            select(sessions.c.id).where(sessions.c.id.in_(empty_ids), sessions.c.user_id == user_id)
        ).all()}
```

The predicate is **in the SQL** (R5), with **no `archived_at` term** (R6). `_reading` is the module's own
read wrapper, matching `compose_session_text` and both fan-out listers, and cannot roll back the caller's
transaction. Signature, name, return type, defaults and every call site unchanged; `write_vector` /
`delete_vector` untouched, since Report 2 §C records they take no user id by design — the gap was in the
caller, not the primitives.

**No sibling statement needed the same fix**: step 5's `write_vector` only receives ids from `pending`,
which requires a non-empty `compose_session_text`, and that read is already owner-scoped;
`ensure_fts_tables` / `ensure_vector_tables` resolve no session; `refresh_session_vector_degraded`
inherits the fix through its single delegation. The docstring already claimed the correct behaviour but
two lines over-stated the delete's reach, so they were made precise — prose only, no behavioural claim
added.

**The probe included a non-vacuity check, which is the part worth keeping.** Run against
`git show HEAD:…/session_index.py`, the same probe printed `after A refresh of [A-empty, B-session]: []`
— B's row deleted — and `A's vector survived B's call: False`. So the probe demonstrably detects the
pre-fix bug, and the fix is what flips it. Post-fix: `refresh_session_vectors(conn, A, [101, 200])` took
`session_vec` from `[101, 200]` to `[200]` — **B's row survived while A's own empty-text row was still
cleared** — B's call left A's row alone, and A's own non-empty refresh still **wrote** A's vector. The
positive half matters as much as the negative: a fix that scoped too tightly and stopped refreshing the
owner's own vectors would have been worse than the bug.

### An `outcome.md` observation the coder added

The `vec0` and FTS tables have **no user column** *and* their write primitives take **no user id**, so
every caller must resolve row ids through an owner-scoped query. Suggested for
`docs/architecture/search-and-retrieval.md`. That is precisely the shape that allowed this finding, so it
is worth stating as a rule rather than leaving implicit.

### Air-gap disclosure, recorded rather than glossed

Step 001's coder ran `grep -n 'decision 9' status.md` and one of the matches was a single line from inside
the `## Tests` table, restating the frozen idempotence contract it **already held** from `## Skeleton`. It
read no other test line and no test file, and scoped every subsequent grep to line ranges. The
implementation choice was already fixed by the frozen docstring, so nothing material leaked — but the air
gap is only meaningful if its near-misses are recorded, so it is recorded. Step 004's coder restricted its
`status.md` reads to three line ranges and its greps to heading and decision lines.

- verify: **PASS (run 1)** — all seven steps PASS, no fault of any type, no re-freeze, no escape valve, no
  coder or test-coder round needed. Backend **`4555 passed, 1 warning in 474.68s`** — 4555 collected, **0
  failed, 0 errored, 0 skipped, 0 xfailed** (the one warning is the pre-existing
  `StarletteDeprecationWarning`). Frontend **`Test Files 151 passed (151)` / `Tests 4363 passed (4363)`**
  in 42.55s, nothing skipped. All four static gates clean: `mypy app` (94 files), `ruff check .`,
  `npm run typecheck` (both tsconfigs, no diagnostics), `npm run build` (740ms). **No pre-existing test
  regressed on either side**, and **all 58 `[test]` DoD items are covered, cited and green.**

**The eight expected reds from the red gate are all green**: 001 DoD-1 (both cases), DoD-2, DoD-4, DoD-5,
DoD-6, DoD-7 — the three plan-time leaks, now closed — and 004's `refresh_session_vectors` pin, the
audit's one finding, now fixed.

**Reported first by the verifier, as asked: the four-seam safety property has not moved.** Only
`backend/tests/privacy_audit_support.py` references any of the four override keys; `install_fake_model_seam`
raises if any is already overridden, sets all four or none, and removes exactly those four on exit;
`audit_world` calls it exactly once; the single seam reference in `test_privacy_audit_routes.py:339` is a
read-only assertion that all four are present. **No network request is possible or was made.** This was
the feature's largest risk and it held throughout.

### Scope — three source files for the whole feature, and five steps that changed nothing

Confirmed from the **diff**, not from the record: `backend/app/logging.py` (+86/−8) and
`backend/app/db/engine.py` (+13) for step 001, and `backend/app/services/session_index.py` (+32/−11, of
which ~16 are the fix) for step 004's fix-allowance. **Steps 002, 003, 005, 006 and 007 changed no source
at all**, which is `context.md`'s designed outcome for an audit step whose tests all pass. Nine new test
files, each in exactly its step's Test files list; **no delivered test file was amended anywhere in this
feature** — no blast-radius edits at all, the only feature of the run with none.
`backend/tests/llm_fakes.py` and `backend/tests/conftest.py` are unmodified. No file references
`rphelper.sqlite` or sets `RPHELPER_DB_PATH`, and `backend/data/rphelper.sqlite`'s mtime is still Oct 4
19:18 — every world and every destructive whole-database-replace case ran against `tmp_path`.

### The five deferred adjudications, all resolved

1. **Step 001's filter arity guard (`len(args) >= 3` rather than uvicorn's exact `== 5`) is acceptable;
   no change required.** DoD-3's clause is conditioned on *"whose target has no query string"*, and the
   guard deciding that case is `"?" not in target`, which is arity-independent — a 5-argument query-less
   record is returned untouched and the test asserts the whole rendered line byte-for-byte in all three
   sinks. The frozen contract holds in all three parts: only index 2 is rewritten
   (`args[:2] + (path,) + args[3:]`), every branch returns `True`, and a query-less target is unchanged.
   The record names uvicorn's 5-tuple as the *reason* index 2 is the target, not as a precondition. The
   over-reach is nil in practice — stdlib filters run only for records emitted on `uvicorn.access`
   itself (a child's record passes the parent's *handlers*, not its *filters*), and nothing in the repo
   emits another shape there. The verifier judged `>= 3` the **safer** failure mode for a redactor:
   pinning `== 5` would make it silently stop redacting if uvicorn changed its argument count.
2. **Idempotence holds and genuinely matters.** Remove-every-instance-by-type then add one, so two calls
   leave exactly one, self-healing if a filter list is ever restored. `app/main.py:141` configures inside
   `create_app`, `:165` runs `create_app()` **at import**, and `audit_world` calls it again for **31**
   world builds, three with real logging — so without the remove step the filter would have accumulated
   for the life of the process. No pre-existing test broke: only `tests/test_logging.py` touches
   `uvicorn.access` at all, asserting handlers, level and `propagate`, **never** filters, and no test
   outside 032 emits through that logger. **Ordering cannot change that answer** — installation is
   idempotent by type so no accumulation is possible in any order, the residue is at most one filter
   object on one logger, and no test asserts `uvicorn.access.filters == []`.
3. **Step 004's fix is minimal and correct in both directions.** Signature, name, return type, defaults
   and all three call sites byte-identical; `write_vector` / `delete_vector` untouched (correctly —
   `app/services/embedding.py` is unmodified, and they take no user id **by design**, so the gap was in
   the caller); `refresh_session_vector_degraded` inherits through its single delegation. **No sibling
   has the same gap** — the only other `delete_vector` calls are `app/services/memos.py:239,351`, both
   owner-scoped, and `write_vector` is driven from `pending`, which requires a non-empty
   `compose_session_text` that is itself owner-scoped. Predicate in the SQL (**R5**), no `archived_at`
   term (**R6**). **The positive half is proved too**: the owner's own empty-text deletion is still
   guarded by two delivered 024 tests (`…__S024_003_DoD8`, strict and degraded), both green, and the
   owner's own writes by the pin's positive control plus 026/027's session-search tests — a fix that
   scoped too tightly would have failed those.
4. **My recorded expectation about 007's console-text clauses was wrong, and the correction is
   confirmed from source.** The only site in `app/` attaching an exception to a loguru record is
   `InterceptHandler` (`app/logging.py:58`, `logger.opt(..., exception=record.exc_info)`); every other
   candidate logs the **class name only** (`app/services/llm/frames.py:155,210` and
   `app/services/tools/seam.py:183,212` all pass `type(error).__name__`), and there is **no
   `logger.exception` anywhere in `app/`**. Under `TestClient` an unhandled exception is re-raised to the
   test rather than logged. **So, stated plainly: the console-text halves of 007 DoD-3/4/5 do not guard
   `diagnose=False` at all, and 001 DoD-4 is the sole automated guard for it on the console sink.** The
   *file* sink has a second, pre-existing guard (`tests/test_logging.py::…__DoD5`, from feature 001/002).
   The verifier added a refinement worth keeping: **`backtrace=False` has no test witness anywhere** —
   001 DoD-4's sentinel is a frame *local*, which `diagnose` renders, while `backtrace` only extends the
   frame chain. No DoD item asks for one, so it is advisory — but anyone changing either sink option
   should know `diagnose` is held by exactly one test and `backtrace` by none.
5. **Carrying the two unbuilt-dependency items forward was the right call.** All three `fast/` folders
   hold only `brief.md` — no `plan.md`, no `status.md`, no `## Skeleton`. Neither step wrote a
   behavioural test and **nothing was invented**: one guard clause each. Both absence guards are armed
   with working anti-vacuity controls (005 proves row 5's pattern matches the built
   `/api/bootstrap/create` *before* asserting every match is allowed; 006 asserts an empty
   `allowed_paths`, a non-empty route walk, and that row 74's pattern matches two synthetic rebuild
   paths). Rows 5 and 74 stay excluded **by name with a full prose reason**, and step 002 DoD-1 remains
   **exact two-way set equality** over the other 72 rows with both difference directions reported.
   `docs/plans/CLAUDE.md` forbids inventing a requirement to close a gap; `context.md`'s "a route that
   does not exist ⇒ SPEC" is scoped to a route a *built* feature was believed to deliver, and raising
   SPEC would have blocked all seven steps to restate what the table already marks `_TBD`. Failing them
   would have been a false negative, passing them silently would have been vacuous; the armed-absence
   guard is the third option and the correct one.

### Anti-vacuity — every control verified armed, which is what makes a green audit mean anything

**002 DoD-4**, the gate for all five later sweeps: **ARMED** — 62 single-token sentinels, every
`stored=True` one found by an owner-scoped `LIKE` on its real table.column, a row owned by A **and** by B
in all seven coverage tables, vec stores by own-id key, FTS by `MATCH`, and `of_user("ADM") == ()`.
**003**: the write-body partition is armed in substance — `_write_body` **raises** for any write row that
is in neither the 12-entry body table nor the 10-entry bodyless set, so a row cannot silently lose its
body and refuse with a 422; DoD-9's "no model call" is a delta with `call_count > 0` asserted first.
**004**: B's row asserted present before the pin, all four stores asserted non-empty first, `MATCH` and
`*_docsize` only. **005**: both users' content asserted non-empty before the destructive call, the 409
pinned exactly. **006**: the matcher self-tests are **demonstrably load-bearing** — 6 flagged + 12 clean
for DoD-8 (`/api/memos` **and** `/api/members` flagged; `/api/me`, `/api/me/settings`, `/api/me?x=1`
clean), 20 + 14 for DoD-9 including decision 27's must-stay-unflagged case, and both real scans assert an
**exactly empty** offence list. **007**: every capture window opens with the dual-witness control — one
loguru record and one stdlib record through the `InterceptHandler` bridge, both asserted to reach both
witnesses — the control that caught the unarmed-witness fault at red-gate run 1 and was not softened.
**Carve-outs are narrow**: decision 11's `tool_args` is excluded **and pinned by exact equality** to the
scripted literal on both the wire field and the stored raw `arguments`; decision 17's `translations`
exclusion is dropped from the positive control only while the sentinel is still asserted **absent**, and
`model_server_id` goes through the single documented `allowed=` channel.

### Domain rules

**R5** — the new predicate is in the SQL. **R6** — no `archived_at` term anywhere in it. **R9** — the
assistant's reach is still exactly `memo_search` / `session_search` / `web_search`, in both the production
registry and the fake. **R11** — `compose_session_text` still reads `settled_entries`, never raw
`messages`.

### `[manual/live]` items — 1 discharged here, 4 carried forward

- **005 DoD-7 — DISCHARGED by the verifier**, as the item itself asks. 030's whole-database-export
  opacity items are `done`: all six of 030's steps are `done / PASS` (2026-10-05), `030/005` carries the
  opacity clauses as DoD-2..4, and `030/context.md` ~L121 states the rule ("No viewer, preview, search,
  diff, row count or table-name listing of any export, anywhere. The admin page reports only the file's
  size.", US-078/R5). Nothing was re-tested in 032, per the **Out** boundary.
- **001 DoD-8** — a real uvicorn run: `GET /api/search?q=<sentinel>` must show `/api/search` with no
  query and no sentinel in console/supervisord output. The automated half (DoD-1, DoD-2) is green.
- **006 DoD-10** — in a running instance with a second user's content, the five confirms that **actually
  exist** (user disable, server delete, embedding clear, lossy table Sync, whole-database replace) show
  no number, and the Users and Database pages show no content. Narrowed by decision 26: there is **no**
  model-disable confirm, so that half of the original wording has no target.
- **007 DoD-10** — in the production container, after compose / settle / sentinel-search / translate,
  neither supervisord output nor `data/logs/` holds the sentinel. nginx's own access log is explicitly
  outside this item.
- **The two `[blocked/unbuilt-dependency]` `[test]` items stay open against their owners**: **005 DoD-6**
  (`fast/003`) and **006 DoD-7** (`fast/002`). Both are guard-only and green today — the surface does not
  exist — and each must be asserted behaviourally when its owning feature is planned.

### Record corrections made at verify

36. **The DoD arithmetic in my own orient record was wrong in both halves and is now fixed.** It read
    "86 DoD items total" and "57 `[test]` and 5 `[manual/live]`". The per-step sum is **62**, the
    `[manual/live]` items are the **four** that line itself names, so the `[test]` items are **58**. The
    verifier caught the off-by-one; the line now carries the correct figures and a note recording what it
    previously said. **All 58 are covered and green** — it was never a coverage gap, only a counting
    error, the same class of slip I made twice on feature 030.
37. **Two advisory concerns for `outcome.md`, neither a finding.** (a) `backtrace=False` has no test
    witness, per adjudication 4. (b) The frontend `API_LITERAL` regex excludes `?`, so
    `isAllowedLiteral`'s `next.startsWith("?")` branch is unreachable in practice — the `/api/me?x=1`
    clean case passes because the match truncates to `/api/me`. Harmless belt-and-braces; the
    `/api/memos` / `/api/members` hole is genuinely closed and `ALLOWED_PREFIXES` is still exactly the
    four names, pinned by its own assertion.
38. **Decision 35 reconfirmed with fresh evidence.** `backend/data/logs/rphelper.log` was appended to
    during the verify run (mtime 03:23, 6.8 MB; stat only, never opened), caused by `app/main.py:141` +
    `:165` running the real `configure_logging` at import — last changed by `e5b25a0` (feature 030), not
    032's to fix. Worth noting that now 001's sinks are hardened, the log **file** is the better-behaved
    of the two operator surfaces, while **nginx's `access_log` still records query strings** and belongs
    to the unplanned `fast/001`.
