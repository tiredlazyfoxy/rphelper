# Feature 035 — llm-client-gateway

| Step | File                           | Status  | Verifier | Date |
|------|--------------------------------|---------|----------|------|
| 001  | `001.library-and-probe.md`     | done    | PASS     | 2026-11-09 |
| 002  | `002.embed-and-factory.md`     | done    | PASS     | 2026-11-09 |
| 003  | `003.complete-and-compose.md`  | done    | PASS     | 2026-11-09 |
| 004  | `004.callers-on-gateway.md`    | done    | PASS     | 2026-11-09 |
| 005  | `005.remove-httpx-client.md`   | done    | PASS     | 2026-11-09 |
| 006  | `006.library-0-2-1.md`         | done    | PASS     | 2026-11-09 |

## Files Changed

_populated by the coder as steps complete_

### Step 001 — Library dependency, infrastructure, and the gateway's probe
- `backend/pyproject.toml` — `llm-client` v0.2.0 git pin (skeleton; unchanged by coder)
- `backend/uv.lock` — refreshed lock (skeleton; unchanged by coder)
- `Dockerfile` — `git` added to the runtime stage's apt line (the stage running `uv sync`), with a why-comment
- `backend/app/config.py` — `llm_request_timeout_seconds` default 30.0 → 600.0, alias unchanged
- `backend/app/logging.py` — `_SILENCED_LOGGERS` gains `aiohttp` (children inherit the parent level)
- `backend/app/services/llm/gateway.py` — `LlmGateway.__init__` stores the coordinates + `library_clients` seam; private `_normalise_base_url` (DEC-035-11), `_is_auth_failure`, `_library_class`, `_missing_credential`, `_build_client`; `probe()` per DEC-035-8/-9
- `backend/app/services/llm/client.py` — probe types imported from the gateway (skeleton; unchanged by coder)

### Step 002 — Gateway embed, and the kind-aware probe/embed factory
- `backend/app/services/llm/gateway.py` — `LlmGateway.embed` (one library client per call, `async with`, `embed_batch(list(texts))`, DEC-035-8 failure mapping raised `from None`); private `_embed_unreachable`; imports `LlmUnreachableError`
- `backend/app/services/llm_registry.py` — `probe_server` and `designate_embedding_model` selects read `llm_servers.c.kind`
- `backend/app/services/embedding.py` — `open_embedding_model` restores `api_key`, the 4-arg factory call with `designation.server.kind` first, and the handle return
- `backend/app/models/admin_llm.py` — import already switched by the skeleton (DEC-035-13); module docstring now says "LLM gateway module"
- Factory-default modules (`dependencies.py`, `messages.py`, `session_index.py`, `characters.py`, `setups.py`, `settle.py`, `memos.py`, `search/*.py`, `index_rebuild.py`, `tools/*_search.py`) — verified, no `LlmClient` import remains; no coder edit
- `backend/app/services/llm/gateway.py` — fix round 1: `embed`'s up-front raises (unrecognised kind, missing credential) now `from None` (DEC-035-8)
- `backend/app/services/llm_registry.py` — fix round 1: `LlmClientFactory` note no longer names the provider-kind values (006 D5)

### Step 003 — Gateway complete and compose
- `backend/app/services/llm/gateway.py` — `LlmGateway.complete` (one client, `chat(wire, stream=False)`, DEC-035-8 mapping `from None`) and `LlmGateway.compose` (one task running `chat_with_tools(stream=True, max_loops=sys.maxsize)`, one unbounded queue + done-callback end marker, cancel-and-await `finally`); private `_chat_unreachable`, `_chat_failure_reason`, `_Absent`/`_ABSENT`, `_EndOfStream`, `_declaration_function`/`_name`/`_properties`, `_tool_callable` (keyword-only `__signature__` minted per declaration)
- `backend/app/services/llm/gateway.py` — fix round 1: `complete`/`compose` early raises (unknown kind, openai without key) now `from None` (DEC-035-8); `compose`'s `finally` waits on the cancelled task with `asyncio.wait([task])` and then reads `task.exception()`, instead of `await task` inside `contextlib.suppress` (CPython 3.12 left the generator flagged running after `aclose()`, DoD-12); unused `contextlib` import removed

### Step 004 — Compose and translation run on the gateway
- `backend/app/services/llm_registry.py` — `open_chat_client` resolves the key, then calls the factory `(server.kind, base_url, api_key, timeout_seconds)`
- `backend/app/services/compose.py` — `compose_stream` drains `client.compose` inside `aclosing` (text → `token` + accumulate, runner frames pass through); private runner `run_tool` (tool_start → `dispatch` → frame; any `Exception` → `tool_fail`/`TOOL_FAILED_CONTENT`); `_PendingCall` removed; module docstring updated
- `backend/app/services/translation.py` — `translate_message` awaits `client.complete(...)`; `_await_complete_stub` and `ChatClientLike` import removed; module docstring updated
- `backend/app/routers/stream.py`, `backend/app/routers/translation.py` — verified only (factories return `LlmGateway`; no `client.py` import); unchanged by coder

### Step 005 — Remove the httpx client; port the live tests
- `backend/app/services/llm/client.py` — deleted (preconditions confirmed: no `backend/app/` importer; `tests/llm_fakes.py` and `tests/privacy_audit_support.py` import probe types from the gateway)

### Step 006 — Library 0.2.1: tolerant tool loop
- `backend/app/services/llm/gateway.py` — `_is_auth_failure` reads `LLMError.status in (401, 403)` (DEC-035-20); private `_REJECTION_KINDS` map; `compose`'s private sync `on_tool_event` observer (three kinds → `ComposeRejected` with `call_<n>` from the wrappers' counter, name/arguments verbatim; all else ignored, no id consumed; non-raising); `chat_with_tools` gains `tool_errors="result"`, `on_tool_event=`; stale comments/docstrings updated
- `backend/app/services/compose.py` — `ComposeRejected` drain branch: `tool_start` → `write_failed_tool_row` → warning (name + kind) → `tool_fail` (`tool_failed`), no dispatch; module/function docstrings updated
- (`pyproject.toml`, `uv.lock`, `llm_registry.py`, `seam.py` — delivered by the skeleton, not further edited)

## Skeleton

### Step 001 — frozen interface (2026-11-08)
- `backend/pyproject.toml` — runtime dependency `"llm-client @ git+https://github.com/Iezious/PythonLLMClient.git@v0.2.0"` added (`httpx` kept); `[tool.hatch.metadata] allow-direct-references = true` — new
- `backend/uv.lock` — regenerated by `uv lock` (llm-client 0.2.0 resolved to commit `195abdfc9b29257f681c18be38674a248ace7e01`, plus aiohttp and its deps); `uv sync` installed it; `import llm; llm.__version__` → `0.2.0`
- `backend/app/services/llm/gateway.py` — `class ProbeOutcome(StrEnum)` (`REACHABLE="reachable"`, `UNREACHABLE="unreachable"`, `AUTH_FAILED="auth_failed"`, `MODEL_LIST_EMPTY="model_list_empty"`) — moved verbatim from `client.py`
- `backend/app/services/llm/gateway.py` — `EMBED_NO_VECTOR_REASON: Final = "no_usable_vector"` — moved verbatim from `client.py`
- `backend/app/services/llm/gateway.py` — `@dataclass(frozen=True) class ProbeResult: outcome: ProbeOutcome; model_names: tuple[str, ...] = (); note: str | None = None` — moved verbatim from `client.py`
- `backend/app/services/llm/gateway.py` — `DEFAULT_LIBRARY_CLIENTS: Final[Mapping[str, type[LLMClient]]] = MappingProxyType({"openai": OpenAIAPIClient, "llamaswap": LlamaSwapAPIClient})` — new (real value, per DEC-035-3)
- `backend/app/services/llm/gateway.py` — `class LlmGateway` with `def __init__(self, kind: str, base_url: str, api_key: str | None, timeout_seconds: float, *, library_clients: Mapping[str, type[LLMClient]] = DEFAULT_LIBRARY_CLIENTS) -> None` — new (stub, raises `NotImplementedError`)
- `backend/app/services/llm/gateway.py` — `async def probe(self) -> ProbeResult` — new (stub, raises `NotImplementedError`)
- `backend/app/services/llm/client.py` — the three definitions removed; now `from app.services.llm.gateway import EMBED_NO_VECTOR_REASON, ProbeOutcome, ProbeResult`, re-exported via `__all__` (identity preserved; unused `StrEnum`/`Final` imports dropped) — changed
- Base-URL normaliser: private to the coder (unnamed, not frozen; DEC-035-11). Behaviour left to the coder: 600 s Settings default, `aiohttp` in `_SILENCED_LOGGERS`, `git` in the Dockerfile apt line, constructor body, probe body.
- Caller-compile edits (out of Source-files scope): None.

### Step 002 — frozen interface (2026-11-08)
- `backend/app/services/llm/gateway.py` — `async def LlmGateway.embed(self, model: str, texts: Sequence[str]) -> list[list[float]]` — new (stub, raises `NotImplementedError`; `Sequence` from `collections.abc`)
- `backend/app/services/llm_registry.py` — `LlmClientFactory = Callable[[str, str, str | None, float], LlmClientLike]` i.e. `(kind, base_url, api_key, timeout_seconds)` — changed (was `Callable[[str, str | None, float], LlmClientLike]`)
- `backend/app/services/llm_registry.py` — `class LlmClientLike(Protocol)`: `async def probe(self) -> ProbeResult`, `async def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]` — unchanged signatures; probe types now imported from `app.services.llm.gateway` (`EMBED_NO_VECTOR_REASON, LlmGateway, ProbeOutcome, ProbeResult`); `app.services.llm.client` import reduced to `ChatDelta` (the `LlmClient` import had no remaining use — no chat default names it — so it is dropped; `ChatClientLike`, `ChatClientFactory`, `open_chat_client` untouched)
- `LlmGateway` (class) satisfies `LlmClientFactory` structurally — verified by mypy through every `client_factory: LlmClientFactory = LlmGateway` default
- Factory defaults `client_factory: LlmClientFactory = LlmClient` → `= LlmGateway` (names/positions unchanged), `LlmGateway` imported from `app.services.llm.gateway` directly: `llm_registry.py` (`probe_server`, `check_server_connection`, `list_available_models`, `designate_embedding_model`), `embedding.py` (`open_embedding_model`), `search/{vector,my_search,hybrid,session_search,memo_search}.py`, and the former re-export importers `messages.py`, `session_index.py`, `characters.py`, `setups.py`, `settle.py`, `memos.py` (`LlmClient` dropped from their `app.services.embedding` / `app.services.session_index` imports). `index_rebuild.py`, `tools/memo_search.py`, `tools/session_search.py` confirmed: no `LlmClient` (no default / `None` default) — no edit.
- `backend/app/dependencies.py` — `def get_llm_client_factory() -> LlmClientFactory` returns `LlmGateway` — changed (was `LlmClient`)
- `backend/app/models/admin_llm.py` — `from app.services.llm.gateway import ProbeOutcome` (DEC-035-13) — changed (was `app.services.llm.client`)
- Compile-only stubs at the construction sites — **coder still owes**:
  - A `probe_server` (`llm_registry.py`): call is now `client_factory(row.kind, row.base_url, api_key, timeout)` but the select still reads only `base_url, api_key_ref`, so it fails loudly at runtime (`AttributeError` on `row.kind`). Coder adds `llm_servers.c.kind` to the select.
  - B `designate_embedding_model` (`llm_registry.py`): same state as A; coder adds `llm_servers.c.kind` to the select.
  - D `open_embedding_model` (`embedding.py`): after `resolve_secret(...)` (kept, unassigned) the body raises `NotImplementedError`; coder restores `api_key = resolve_secret(...)`, `client = client_factory(designation.server.kind, designation.server.base_url, api_key, timeout_seconds)` and `return EmbeddingModelHandle(client, designation.model_name, designation.embedding_dim)`.
- Caller-compile edits (out of Source-files scope): None. (`routers/admin_llm.py` module docstring still says the production factory is `LlmClient` — doc only, not edited.)

### Step 003 — frozen interface (2026-11-08)
- `backend/app/services/llm/gateway.py` — `@dataclass(frozen=True) class ComposeText: text: str` — new (real value type)
- `backend/app/services/llm/gateway.py` — `@dataclass(frozen=True) class ComposeTools[E]: declarations: Sequence[Mapping[str, object]]; runner: Callable[[ToolCall, Callable[[E], None]], Awaitable[str]]` — new (real value type; PEP 695 generic in the runner's event type `E`; `emit` is `Callable[[E], None]`, sync)
- `backend/app/services/llm/gateway.py` — `async def LlmGateway.complete(self, model: str, messages: Sequence[ChatMessage]) -> str` — new (stub, raises `NotImplementedError`)
- `backend/app/services/llm/gateway.py` — `async def LlmGateway.compose[E](self, model: str, messages: Sequence[ChatMessage], tools: ComposeTools[E]) -> AsyncGenerator[ComposeText | E, None]` — new (stub: a real async generator whose body raises `NotImplementedError` on the first `__anext__`; calling `compose(...)` itself does not raise). Return type is `AsyncGenerator` (a subtype of `AsyncIterator`) so `aclose()` and `contextlib.aclosing` type-check for step 004.
- New imports in `gateway.py`: `AsyncGenerator, Awaitable, Callable` from `collections.abc`; `ChatMessage, ToolCall` from `app.services.llm.chat`. No import of `services/tools/`, `llm_registry` or `frames.py`.
- Private, not frozen: the per-declaration library callable (signature-minting wrapper, absent-marker, `call_<n>` counter), the queue/end marker, the error mapping helper — coder's choice of names.
- Test binding:
  - Construct: `ComposeTools(declarations=[{"type": "function", "function": {"name": "search_memos", "description": "…", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}}}], runner=runner)` where `async def runner(call: ToolCall, emit: Callable[[Ev], None]) -> str: emit(Ev(...)); return "out"` (any event type; `ComposeTools[str]` etc. also fine). Empty tools: `ComposeTools(declarations=(), runner=runner)`.
  - Drain: `events = [e async for e in gateway.compose("m", messages, tools)]`; error cases `with pytest.raises(LlmUnreachableError): async for e in agen: seen.append(e)` (collect pre-failure events). Close: `agen = gateway.compose(...)`; `first = await agen.__anext__()` (or `anext(agen)`), then `await agen.aclose()`.
  - Gateway built as `LlmGateway(kind, base_url, api_key, timeout, library_clients={kind: FakeClient})` (step 001 seam).
- Caller-compile edits (out of Source-files scope): None.

### Step 004 — frozen interface (2026-11-08)
- `backend/app/services/llm_registry.py` — `class ChatClientLike(Protocol)`: `async def complete(self, model: str, messages: Sequence[ChatMessage]) -> str` and `def compose[E](self, model: str, messages: Sequence[ChatMessage], tools: ComposeTools[E]) -> AsyncGenerator[ComposeText | E, None]` — changed (was `def chat_stream(self, model, messages, tools: Sequence[Mapping[str, object]]) -> AsyncIterator[ChatDelta]`). `compose` is a plain `def` returning `AsyncGenerator` (so `async def` generator methods satisfy it and `contextlib.aclosing` type-checks — verified), generic in `E` (no import of `frames.py` into the registry; avoids the `frames → messages → … → llm_registry` cycle).
- `backend/app/services/llm_registry.py` — `ChatClientFactory = Callable[[str, str, str | None, float], ChatClientLike]` i.e. `(kind, base_url, api_key, timeout_seconds)` — changed (was `Callable[[str, str | None, float], ChatClientLike]`). Imports: `ComposeText, ComposeTools` from `app.services.llm.gateway`; `app.services.llm.client` import gone; `AsyncIterator`/`Mapping` dropped, `AsyncGenerator` added.
- `LlmGateway` (class) satisfies `ChatClientFactory` structurally — verified by mypy through `get_chat_client_factory()` / `get_translation_chat_client_factory()` returning it.
- `backend/app/services/llm_registry.py` — `open_chat_client(connection, enabled_model, timeout_seconds, client_factory: ChatClientFactory) -> ChatClientLike` — signature unchanged.
- `backend/app/services/compose.py` — `compose_stream(engine, generator, user_id, session_id, accepted_id, timeout_seconds, client_factory: ChatClientFactory, registry: ToolRegistry) -> AsyncGenerator[Frame, None]` — signature unchanged; docstring rewritten to the new contract. Runner: private, unnamed, not frozen.
- `backend/app/services/translation.py` — `translate_message(engine, generator, user_id, message_id, timeout_seconds, client_factory: ChatClientFactory, is_disconnected: DisconnectProbe) -> TranslationResult` — signature unchanged.
- `backend/app/routers/stream.py` — `def get_chat_client_factory() -> ChatClientFactory` returns `LlmGateway` — changed (was `LlmClient`); `from app.services.llm.gateway import LlmGateway`, `client.py` import dropped.
- `backend/app/routers/translation.py` — `def get_translation_chat_client_factory() -> ChatClientFactory` returns `LlmGateway` — changed (was `LlmClient`); same import swap.
- After this step none of `llm_registry.py`, `translation.py`, `compose.py`, `routers/stream.py`, `routers/translation.py` imports `app.services.llm.client`.
- Compile-only stubs — **coder still owes**:
  - A `open_chat_client`: after the select and `resolve_secret(row.api_key_ref)` (kept, now unassigned — `secret_ref_missing` still raises first) the body raises `NotImplementedError`; coder restores `api_key = resolve_secret(...)` and `return client_factory(enabled_model.server.kind, row.base_url, api_key, timeout_seconds)`.
  - B `compose_stream`: setup phase unchanged; then `offered_names`, `conversation`, `exchange_parts` are built, `del client, scope, offered_names, conversation` (lint placeholder — delete it), and `raise NotImplementedError`; the success write + `DoneFrame` are kept below (unreachable). Coder writes the drain of `client.compose(enabled_model.model_name, conversation, ComposeTools(declarations=tools, runner=<private runner>))` inside `contextlib.aclosing`, `ComposeText` → `TokenFrame` + accumulate, runner frames pass through, and the private runner (tool_start_frame → `dispatch(call, scope, offered_names, registry, engine, generator)` → `result.frame` → return `result.message.content`; on `Exception` emit a `ToolFailFrame` `tool_failed` as the seam builds it and return `TOOL_FAILED_CONTENT`). Coder also deletes `_PendingCall` (and the then-unused `field` import), re-imports what it needs (`ToolCall`, `TokenFrame`, `dispatch`, `tool_start_frame`, `TOOL_FAILED_CONTENT`, `ComposeText`/`ComposeTools`, `aclosing`, the `ToolFailFrame` construction — the skeleton removed the now-unused `THINK_OPEN`/`THINK_CLOSE`/`ToolCall`/`TokenFrame`/`dispatch`/`tool_start_frame` imports to keep ruff clean), and updates the module docstring (still describes `chat_stream` rounds).
  - C `translate_message`: the call is `joined: str = _await_complete_stub(client, enabled_model.model_name, target_language, row.text)` (private helper, always raises `NotImplementedError`); coder replaces it with `joined = await client.complete(enabled_model.model_name, _translation_messages(target_language, row.text))` and deletes `_await_complete_stub` (and the `ChatClientLike` import if then unused). `_join_content` and the `ChatDelta` / `AsyncIterator` imports were already removed (required to drop the `client.py` import). Strip, cache, failure mapping and disconnect check untouched.
- Test binding (fakes):
  - Chat client fake — any class with `async def complete(self, model: str, messages: Sequence[ChatMessage]) -> str` and a **generic** `async def compose[E](self, model: str, messages: Sequence[ChatMessage], tools: ComposeTools[E]) -> AsyncGenerator[ComposeText | E, None]` (an async generator: `yield ComposeText("…")`; for a scripted tool call collect `emitted: list[E] = []`, `out = await tools.runner(ToolCall(call_id="call_1", name=..., arguments=...), emitted.append)`, yield each `emitted` item, then continue with the scripted text; a failure script raises `LlmUnreachableError` from inside the generator). A non-generic `compose` (e.g. `tools: ComposeTools[Frame]`) does **not** satisfy the protocol. Verified with mypy incl. `aclosing(c.compose(...))`.
  - Factory fake — any callable `(kind: str, base_url: str, api_key: str | None, timeout_seconds: float) -> <fake client>`, e.g. a class whose `__call__` records the four positional args.
  - Overrides: `app.dependency_overrides[get_chat_client_factory]` / `[get_translation_chat_client_factory]` as before; DoD-13 asserts `get_chat_client_factory() is LlmGateway` and likewise for translation.
- Caller-compile edits (out of Source-files scope): None.

### Step 006 — frozen interface (2026-11-09)
- `backend/pyproject.toml` — runtime dependency now `"llm-client @ git+https://github.com/Iezious/PythonLLMClient.git@v0.2.1"` — changed (was `@v0.2.0`); `httpx` and the Dockerfile untouched
- `backend/uv.lock` — regenerated by `uv lock` (llm-client v0.2.0 `195abdfc` → v0.2.1 `2964ac868d990400a2d05aa91f64f233a8388129`); `uv sync` installed it; `import llm; llm.__version__` → `0.2.1`. mypy was already clean against 0.2.1 before any other edit (no cast/ignore needed adjusting).
- `backend/app/services/llm/gateway.py` — `class ComposeRejectionKind(StrEnum)`: `NOT_OFFERED = "not_offered"`, `BAD_ARGUMENTS = "bad_arguments"`, `UNKNOWN_ARGUMENT = "unknown_argument"` — new (real value type; gateway-owned, not the library's `ToolErrorKind`)
- `backend/app/services/llm/gateway.py` — `@dataclass(frozen=True) class ComposeRejected: call: ToolCall; kind: ComposeRejectionKind` — new (real value type)
- `backend/app/services/llm/gateway.py` — `async def LlmGateway.compose[E](self, model: str, messages: Sequence[ChatMessage], tools: ComposeTools[E]) -> AsyncGenerator[ComposeText | ComposeRejected | E, None]` — changed (was `-> AsyncGenerator[ComposeText | E, None]`); internal queue type widened to match; docstring states the step 006 contract. Body otherwise unchanged — **coder still owes**: the private synchronous `on_tool_event` observer (nested in `compose`, closed over `queue` and `call_numbers`; unnamed, not frozen) and passing `tool_errors="result", on_tool_event=<observer>` to `chat_with_tools`. Not stubbed in the body, since a raising observer would break the existing tool path.
- `backend/app/services/llm/gateway.py` — `_is_auth_failure(exc: LLMError) -> bool` — signature unchanged; **coder still owes** the switch to `exc.status in (401, 403)` (DEC-035-20). It still reads the message, so 0.2.0 behaviour is kept until then.
- `backend/app/services/llm_registry.py` — `ChatClientLike.compose[E](self, model: str, messages: Sequence[ChatMessage], tools: ComposeTools[E]) -> AsyncGenerator[ComposeText | ComposeRejected | E, None]` — changed (was `-> AsyncGenerator[ComposeText | E, None]`); `ComposeRejected` imported from `app.services.llm.gateway`. Existing fakes that yield only `ComposeText | E` still satisfy it (covariant).
- `backend/app/services/tools/seam.py` — `def write_failed_tool_row(engine: Engine, generator: SnowflakeGenerator, scope: ToolScope, call: ToolCall) -> None` — new public wrapper (real body, pure exposure): `_write_row(engine, generator, scope, call, TOOL_FAILED_ROW_TEXT, _failed_payload(call))`. Sync, own short-lived connection, log-and-swallow as before.
- `backend/app/services/tools/seam.py` — `def _failed_payload(call: ToolCall) -> str` — new private helper, extracted verbatim from `dispatch`'s failure branch (same keys, order and compaction); `dispatch` now calls it. `dispatch`'s behaviour is unchanged.
- `backend/app/services/compose.py` — `compose_stream(...)` — signature unchanged; `ComposeRejected` imported; the drain gains `elif isinstance(item, ComposeRejected): raise NotImplementedError(...)` before the pass-through `else`. **Coder owes**: `yield tool_start_frame(item.call)` → `write_failed_tool_row(engine, generator, scope, item.call)` (import it from `app.services.tools.seam`) → `logger.warning(...)` with tool name and `item.kind` only → `yield ToolFailFrame(tool=item.call.name, call_id=item.call.call_id, code=ToolFailedError.code)`.
- Test binding: `ComposeRejected(call=ToolCall(call_id="call_2", name="", arguments="{not json"), kind=ComposeRejectionKind.BAD_ARGUMENTS)`. `ComposeRejectionKind` is a `StrEnum`, so `kind == "bad_arguments"` holds. A gateway-shaped fake for `test_compose_source.py` is `async def compose[E](self, model, messages, tools: ComposeTools[E]) -> AsyncGenerator[ComposeText | ComposeRejected | E, None]` that yields `ComposeRejected` values between `ComposeText` pieces.
- Caller-compile edits (out of Source-files scope): None.


## Tests

### Step 001 — tests (2026-11-08)
- `backend/tests/test_config.py` — covers DoD-1 — default 600.0 (field default and hermetic `Settings`), alias unchanged, `RPHELPER_LLM_REQUEST_TIMEOUT_SECONDS` still overrides (`*__S035_001_DoD1`); the 006/001 assertions that pinned 30.0 (`EXPECTED_FIELDS`, the default test now `test_timeout_defaults_to_six_hundred_seconds_as_a_float__S006_001_DoD10__S035_001_DoD1`, the unprefixed-variable test) now pin 600.0
- `backend/tests/test_logging.py` — covers DoD-2 — `test_library_logger_tree_record_reaches_neither_sink__S035_001_DoD2`: records at DEBUG..CRITICAL on `aiohttp`, `aiohttp.client`, `aiohttp.internal` (and unchanged `httpx`, `httpx._client`) reach neither the console nor the file sink (both sinks at DEBUG, control record proves the sinks are live); restore fixture also snapshots those loggers
- `backend/tests/test_logging_redaction.py` — supports DoD-2 — `aiohttp` added to `TOUCHED_LOGGERS` so its state is restored (no new assertion)
- `backend/tests/test_deployment_files.py` — covers DoD-3 — `test_s035_001_dod3_*`: pyproject has exactly one `llm-client` runtime requirement with url `git+https://github.com/Iezious/PythonLLMClient.git@v0.2.0` and the verbatim `llm-client @ <url>` entry; `httpx` still a runtime dependency; the single Dockerfile stage running `uv sync` installs `git` on its apt line
- `backend/tests/test_llm_gateway_probe.py` (new) — covers DoD-4..DoD-14 — fake library classes injected through `library_clients` (real `llm.LLMError`; the openai fake refuses a falsy token with `ValueError` like the real class):
  - DoD-4 `test_kind_selects_its_library_class_with_timeout_token_and_url__S035_001_DoD4` — kind builds its own entry only, with `timeout`, `bearer_token`, normalised `base_url`; construction builds nothing
  - DoD-5 `test_base_url_reaches_the_library_normalised__S035_001_DoD5` — the five URLs, both kinds
  - DoD-6 `test_a_listing_gives_reachable_with_names_in_library_order__S035_001_DoD6` — `reachable`, `model_names` tuple in library order (non-sorted)
  - DoD-7 `test_an_empty_listing_gives_model_list_empty__S035_001_DoD7`
  - DoD-8 `test_library_error_maps_to_its_probe_outcome__S035_001_DoD8` — 401/403 → `auth_failed`; 500, `failed: timeout`, `failed: connection failure`, `Invalid response …` → `unreachable`; both kinds
  - DoD-9 `test_openai_without_a_key_is_auth_failed_without_listing__S035_001_DoD9`, `test_llamaswap_without_a_key_is_built_tokenless_and_proceeds__S035_001_DoD9` — `None` and `""`
  - DoD-10 `test_an_unrecognised_kind_is_unreachable_and_builds_nothing__S035_001_DoD10` — `ollama`, `bogus`, `""`
  - DoD-11 `test_any_exception_from_list_models_gives_unreachable__S035_001_DoD11`, `test_an_exception_entering_the_client_gives_unreachable__S035_001_DoD11`, `test_an_exception_building_the_client_gives_unreachable__S035_001_DoD11`
  - DoD-12 `test_a_successful_probe_enters_and_exits_one_client__S035_001_DoD12`, `test_a_failed_probe_still_enters_and_exits_one_client__S035_001_DoD12`, `test_each_probe_call_uses_its_own_single_client__S035_001_DoD12`
  - DoD-13 `test_provider_text_reaches_neither_the_result_nor_a_log__S035_001_DoD13`, `test_provider_text_in_a_non_library_exception_reaches_no_log__S035_001_DoD13` (loguru level-0 sink + stdlib `caplog`), `test_note_is_none_in_every_outcome__S035_001_DoD13` (six outcomes incl. openai-no-key and unknown kind)
  - DoD-14 `test_probe_outcome_is_one_object_in_gateway_and_client__S035_001_DoD14`, `test_probe_outcome_values_are_unchanged__S035_001_DoD14`, `test_probe_result_and_no_vector_reason_are_re_homed_unchanged__S035_001_DoD14` (Interface intent: `ProbeResult` identity + defaults, `EMBED_NO_VECTOR_REASON` value)
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 [manual/live, no test]

### Step 002 — tests (2026-11-08)
- `backend/tests/test_llm_gateway_embed.py` (new) — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5 — real `LlmGateway` over fake library classes (`library_clients`, real `llm.LLMError`): vectors returned in order, one client built with the model, `embed_batch` gets the texts (DoD-1); 401/403 → `auth_failed`, `Invalid response…` → `no_usable_vector`, other statuses / transport / `Unreadable reply…` → `unreachable`, the rule reads the message not the description (DoD-2); openai with no key → `auth_failed` and no library method, unrecognised kind → `unreachable` with no client built (DoD-3); message + description sentinels absent from the error's message, args, detail, the loguru and stdlib records and the formatted traceback, `__cause__ is None`, `__suppress_context__` true (DoD-4); exactly one client entered and exited per call, on success, on every failure, per call on a reused gateway, and none at construction (DoD-5)
- `backend/tests/test_admin_llm_router.py` — covers DoD-6, DoD-7, DoD-9 — `_FakeFactory.calls` is now four-wide; `__S035_002_DoD6` tests: test route and available-models call the factory `(kind, base_url, key, timeout)`, the test route still answers 200 and writes `last_test_*` for failing outcomes, available-models still answers 502 `llm_unreachable`; `__S035_002_DoD7`: designation calls with the kind first and returns the measured dimension; `__S035_002_DoD9`: an absent key variable gives 500 `secret_ref_missing` on all three outbound routes with no factory call. Existing index/tuple reads moved to four-wide; the default-timeout test now expects 600.0 (step 001)
- `backend/tests/test_llm_registry_servers.py` — covers DoD-6, DoD-9 — `FakeFactory.calls` is four-wide; `__S035_002_DoD6`: `probe_server` calls `(kind, base_url, resolved key, timeout)` for both kinds, uses the stored kind after an update, `check_server_connection` still records failing outcomes, `list_available_models` still raises `llm_unreachable` with the outcome reason; `__S035_002_DoD9`: absent variable → `secret_ref_missing` with no factory call (probe / check / available). The 006 DoD-20 "both kinds identical" test is narrowed to "identical except the kind"; the AST "no direct construction" check now counts `LlmGateway` too; default timeout expects 600.0
- `backend/tests/test_llm_registry_models.py` — covers DoD-1, DoD-2, DoD-7, DoD-9 — the real-`LlmClient`-over-`httpx.MockTransport` tests now drive the real gateway via `llm_fakes.gateway_factory` (transport / timeout / 401 / `Invalid response` → `llm_unreachable` with that reason and nothing written; healthy library → measured dimension; the one library client is built for the designated model and `embed_batch` gets exactly `EMBEDDING_PROBE_TEXT`); `__S035_002_DoD7`: designation calls the factory with the kind first (both kinds), uses the stored kind after an update, and through the gateway the kind selects the library class; `__S035_002_DoD9`: absent variable raises before the factory. The 006 DoD-21 "both kinds identical" test narrowed as above. No `httpx` / `LlmClient` import remains
- `backend/tests/test_embedding_service.py` — covers DoD-8, DoD-9 — `_seed_designation(kind=...)`; `__S035_002_DoD8`: `open_embedding_model` calls the factory with the designated server's kind first (both kinds); writes through the shared fake behave as before, incl. wrong-length (`dimension_mismatch`) and no-vector (`no_usable_vector`); through the real gateway (fake library) the sync bridge answers the library vectors, wrong-length is `dimension_mismatch`, an `Invalid response` reply is `llm_unreachable` / `no_usable_vector`; `__S035_002_DoD9`: absent variable raises before the factory
- `backend/tests/test_dependencies.py` — covers DoD-10 — `get_llm_client_factory() is LlmGateway`; the override example uses `LlmGateway`; `client.py` import gone
- `backend/tests/llm_fakes.py` — shared helper (no DoD of its own; serves DoD-1, DoD-6..8) — `FakeClientFactory.__call__(kind, base_url, api_key, timeout_seconds)`; `calls` stays three-wide, new `kinds` and `full_calls`; probe types from the gateway; new `LibraryEmbedRecorder` (fake library classes for `llamaswap` / `openai`, openai refuses an empty token like `OpenAIAPIClient`) and `gateway_factory(recorder)`
- `backend/tests/privacy_audit_support.py` — shared helper — `ScriptedProbeFactory` and `delegating_embedding_factory` take four arguments; `ScriptedProbeClient(kind=...)` and `ScriptedProbeFactory.kinds`; `ProbeOutcome` / `ProbeResult` from the gateway. Chat fakes and their `ChatDelta` / `ToolCallDelta` import from `client.py` untouched (step 004)
- `backend/tests/test_privacy_audit_logs.py` — DEC-035-13 — probe-type import switched to `app.services.llm.gateway`, nothing else
- `backend/tests/test_session_index.py`, `backend/tests/test_record_keeping_embedding.py` — DEC-035-14 — `_ExplodingFactory.__call__` takes `kind` first; nothing else changed (F005 DoD-10 tests still expect the `RuntimeError`)
- `backend/tests/test_memos_service.py`, `backend/tests/test_messages_service.py`, `backend/tests/test_settle_service.py` — DEC-035-14 — each import guard also accepts `app.services.llm.gateway` as an exact-match approved deviation, cited in a comment; every other `app.services` import still offends
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓

### Step 003 — tests (2026-11-08)
- `backend/tests/test_llm_gateway_complete.py` — covers DoD-1, DoD-2 — `complete` over a fake library class (DEC-035-3 seam): one client built with the model, entered/exited, `chat` non-streamed with no system/options, wire messages in order (system first), text returned verbatim; failure mapping (401/403 → `auth_failed`; other status, transport, `Invalid response`, `Unreadable reply`, `ValueError` → `unreachable`; `openai` + no key → `auth_failed`, chat never called), no provider text in message/args/detail/log (loguru sink + caplog), `__cause__ is None`, `__suppress_context__ is True`
  - `test_complete_builds_one_client_with_the_model__DoD1` → DoD-1
  - `test_complete_calls_chat_inside_the_entered_client__DoD1` → DoD-1
  - `test_complete_calls_chat_non_streamed_without_system_or_options__DoD1` → DoD-1
  - `test_complete_passes_the_wire_messages_in_order__DoD1` → DoD-1
  - `test_complete_returns_the_library_text_unchanged__DoD1` → DoD-1
  - `test_complete_maps_library_failures_to_llm_unreachable__DoD2` (10 params) → DoD-2
  - `test_complete_failure_has_no_chained_cause__DoD2` (10 params) → DoD-2
  - `test_complete_openai_without_api_key_is_auth_failed_and_calls_nothing__DoD2` → DoD-2
- `backend/tests/test_llm_gateway_compose.py` — covers DoD-3..DoD-14 — `compose` over a fake library class whose `chat_with_tools` imitates the 0.2.0 tool-call contract (pre-flight callable check, `on_delta` awaited-if-awaitable, offered-name check → `LLMError`, `inspect.signature` argument-name check → `ValueError`, callable `Exception` → `RuntimeError`, `CancelledError` passes through and is recorded; a `Block` step waits on a test-controlled event; enter/exit/open-during-call recorded)
  - `test_compose_builds_one_client_with_the_model__DoD3` → DoD-3
  - `test_compose_streams_with_no_loop_cap_system_or_options__DoD3` → DoD-3
  - `test_compose_passes_declarations_as_given_in_order__DoD3` → DoD-3
  - `test_compose_passes_one_callable_per_declaration_name__DoD3` → DoD-3
  - `test_compose_replays_tool_calls_and_tool_results_intact__DoD4` → DoD-4
  - `test_compose_yields_one_compose_text_per_piece_verbatim__DoD5` → DoD-5
  - `test_compose_passes_think_tags_through_inside_pieces__DoD5` → DoD-5
  - `test_compose_mints_call_ids_in_invocation_order__DoD6` → DoD-6
  - `test_compose_call_ids_restart_for_the_next_compose__DoD6` → DoD-6
  - `test_compose_tool_call_carries_the_declaration_name__DoD6` → DoD-6
  - `test_compose_tool_call_arguments_are_json_of_the_kwargs_non_ascii_kept__DoD6` → DoD-6
  - `test_compose_tool_call_arguments_hold_every_given_kwarg__DoD6` → DoD-6
  - `test_compose_returns_the_runner_text_to_the_library__DoD6` → DoD-6
  - `test_compose_tool_callable_signature_is_the_declared_properties__DoD7` (2 params) → DoD-7
  - `test_compose_absent_declared_argument_is_left_out_of_the_json__DoD7` → DoD-7
  - `test_compose_runner_events_appear_in_emit_order_between_the_text__DoD8` → DoD-8
  - `test_compose_ends_after_the_last_event_and_drops_the_returned_text__DoD9` → DoD-9
  - `test_compose_with_no_pieces_ends_empty__DoD9` → DoD-9
  - `test_compose_failure_yields_queued_events_then_raises_mapped__DoD10` (7 params: 401, 403, 500, transport, invalid-response, RuntimeError, ValueError) → DoD-10
  - `test_compose_unoffered_tool_name_is_unreachable__DoD10` → DoD-10
  - `test_compose_unknown_argument_name_is_unreachable__DoD10` → DoD-10
  - `test_compose_unparseable_arguments_is_unreachable__DoD10` → DoD-10
  - `test_compose_runner_exception_surfacing_as_runtime_error_is_unreachable__DoD10` → DoD-10
  - `test_compose_openai_without_api_key_is_auth_failed_before_any_event__DoD11` → DoD-11
  - `test_compose_aclose_cancels_the_running_library_call__DoD12` → DoD-12
  - `test_compose_aclose_cancels_a_runner_awaiting_inside_a_tool__DoD12` → DoD-12
  - `test_compose_with_no_declarations_still_uses_the_tool_loop__DoD13` → DoD-13
  - `test_compose_completed_call_enters_and_exits_one_client__DoD14` → DoD-14
  - `test_compose_failed_call_enters_and_exits_one_client__DoD14` → DoD-14
  - `test_compose_closed_call_enters_and_exits_one_client__DoD14` → DoD-14
  - `test_compose_each_call_uses_its_own_client__DoD14` → DoD-14
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓ (no `[manual/live]` items in this step)

### Step 004 — tests (2026-11-09)
- `backend/tests/privacy_audit_support.py` — supports DoD-14 — the shared chat fakes (`FakeChatClient`, `FakeChatClientFactory`, `text_round`, `tool_call_round`, `failure_round`, `script_*`) are now gateway-shaped: `complete` plus generic `compose` playing text steps, whole `ToolCall`s through `tools.runner`, and raised errors; the factory records `(kind, base_url, api_key, timeout)`. Probe/embed fakes are untouched.
- `backend/tests/test_open_chat_client.py` — covers DoD-1 — the factory gets `(kind, base_url, key, timeout)` from the model's own server (servers with different kinds); `secret_ref_missing` is raised before any factory call; the key ref is re-read at call time.
- `backend/tests/test_compose_source.py` — covers DoD-1..DoD-9 and DoD-14 — `compose` gets the model, the messages and the declarations in fixed order. The source-level checks:
  - DoD-2: each text piece becomes one verbatim token (`<think>` included), and the assistant row holds the joined text.
  - DoD-3: a tool exchange emits start/result with `call_1`, then a tool row before the assistant row, and the runner returns the content (30-call case included).
  - DoD-4: a raising tool gives `tool_fail` and the fixed content.
  - DoD-5: a raising `dispatch` is mapped to `tool_failed`.
  - DoD-6: the offering matrix, including empty.
  - DoD-7: failure after text gives no `done` and no row from the source.
  - DoD-8: `aclose` finalizes the client stream, and a stop during a tool cancels the tool, writes no tool row, and persists the partial as an unsettled zone row via `frame_stream`.
  - DoD-9: refusals.
  - DoD-14: the shared fakes drive a tool exchange.
  - AST check: compose imports neither `app.services.llm.client` nor `llm`.
- `backend/tests/test_compose_route.py` — covers DoD-1, DoD-2, DoD-3, DoD-6, DoD-7, DoD-9, DoD-13 — the route-level checks:
  - DoD-1: the factory gets the server's `kind` first.
  - DoD-2: pieces arrive verbatim, the zone assistant row is the joined text, and `done.message_id` is that row's id as a string.
  - DoD-3: the tool exchange appears on the wire.
  - DoD-6: the production registry offers declarations according to the switches.
  - DoD-7: failure after text gives `error llm_unreachable`, no `done`, and a partial row.
  - DoD-9: refusals become an `error` after `accepted`.
  - DoD-13: `get_chat_client_factory() is LlmGateway`.
  - The fakes are gateway-shaped, with one script per `compose` call.
- `backend/tests/test_translation_service.py` — covers DoD-10, DoD-11, DoD-12 — the service-level checks:
  - DoD-10: a miss calls `complete` once (never `compose`) with the model and the two messages; the factory gets `(llamaswap, base_url, None, timeout)`; the `<think>` strip result is cached and returned; AST check: translation imports neither `app.services.llm.client` nor `llm`.
  - DoD-11: `llm_unreachable` (including the `auth_failed` reason) becomes `translation_failed` with nothing cached; results that are empty after the strip fail; refusals and `secret_ref_missing` propagate unchanged.
  - DoD-12: the probe runs once, after `complete` returned; a disconnect means nothing is cached but the text is still returned.
- `backend/tests/test_translation_router.py` — covers DoD-10, DoD-11, DoD-13 — the router-level checks:
  - DoD-10: `complete` is called with the server's kind first.
  - DoD-11: unreachable gives 502 `translation_failed`; the real-factory test now goes through the real `LlmGateway` at `http://127.0.0.1:9` and still expects 502.
  - DoD-13: `get_translation_chat_client_factory() is LlmGateway`.
- `backend/tests/test_web_search_offering.py` — covers DoD-6 — the route offers all three declarations (memo, session, web) when configured; the fake is gateway-shaped and records the factory as a 4-tuple.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓. For DoD-14, the existing `test_privacy_audit_*.py` modules also run on the moved shared fakes.

### Step 005 — tests (2026-11-08)
- `backend/tests/test_llm_gateway_boundary.py` (new) — covers DoD-1, DoD-2, DoD-3 — `ast` import scans over every `.py` under `backend/app/` (relative imports resolved against the file's package; `llm` matched as the exact top-level package of absolute imports only)
  - `test_client_module_file_does_not_exist__S035_005_DoD1` — DoD-1: `app/services/llm/client.py` absent (red until the coder deletes it)
  - `test_no_app_module_imports_the_client_module__S035_005_DoD1` — DoD-1: no module imports `app.services.llm.client` (absolute, `from app.services.llm import client`, relative forms)
  - `test_module_scan_detects_every_client_import_form__S035_005_DoD1` (parametrized), `test_module_scan_does_not_flag_sibling_modules__S035_005_DoD1` — DoD-1 scanner sanity on synthetic sources
  - `test_only_the_gateway_imports_the_llm_library__S035_005_DoD2` — DoD-2: the set of `llm`/`llm.*` importers equals `{app/services/llm/gateway.py}`
  - `test_root_scan_detects_the_library_package__S035_005_DoD2`, `test_root_scan_ignores_rphelpers_own_llm_package__S035_005_DoD2` (parametrized) — DoD-2 scanner sanity (`app.services.llm`, relative and look-alike names never count)
  - `test_httpx_is_imported_only_by_the_web_search_package__S035_005_DoD3` — DoD-3: every `httpx` importer is under `app/services/web_search/`
  - `test_root_scan_detects_httpx__S035_005_DoD3` (parametrized) — DoD-3 scanner sanity
  - `test_app_scan_finds_python_files__S035_005_DoD1_DoD2_DoD3` — scan root non-empty and contains the gateway (no vacuous pass)
- `backend/tests/test_live_llm.py` (ported, DEC-035-12) — covers DoD-4, DoD-5 `[manual/live]`, `-m live`, skipped without `LLAMA_SWITCH_URL` — every check builds `LlmGateway("llamaswap", LIVE_URL, None, t)`
  - `test_live_server_probes_reachable_with_models__S035_005_DoD4` — probe reachable, non-empty model list incl. the embed model
  - `test_live_embedding_returns_one_vector_per_input_in_order__S035_005_DoD4` — non-empty vectors, one per input
  - `test_closed_port_probes_unreachable__S035_005_DoD4` — `http://127.0.0.1:9/`, 2 s timeout, probe outcome `unreachable`
  - `test_closed_port_embed_fails_fast_as_unreachable__S035_005_DoD4` — kept closed-port embed case, raises `LlmUnreachableError`
  - `test_live_complete_returns_text__S035_005_DoD5` — `complete` returns non-empty text (also skips without `LLAMA_SWITCH_CHAT_MODEL`)
  - `test_live_compose_without_tools_streams_text__S035_005_DoD5` — `compose` with `ComposeTools(declarations=(), runner=…)` yields >= 1 `ComposeText` and ends without error (DEC-035-10 flip check; also skips without `LLAMA_SWITCH_CHAT_MODEL`)
- Deleted (with the module they test, `DEC-arch-llm-client-library-11`): `backend/tests/test_llm_client.py`, `backend/tests/test_llm_chat_stream.py` — deleted by the orchestrator on the test-coder's behalf (2026-11-09)
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 [manual/live, live tests above], DoD-5 [manual/live, live tests above], DoD-6 [manual/live, no test]

### Step 005 — tests (fix 1, DEC-035-15) (2026-11-09)
- `backend/tests/test_llm_gateway_probe.py` (step 001's module, now also in step 005's Test files per DEC-035-15) — TEST-fault fix: module failed to collect after step 005 DoD-1 deleted `app/services/llm/client.py`
  - Removed the `from app.services.llm import client as client_module` import
  - Removed `test_probe_outcome_is_one_object_in_gateway_and_client__S035_001_DoD14` (client-vs-gateway identity, retired by DEC-035-15)
  - `test_probe_result_and_no_vector_reason_are_re_homed_unchanged__S035_001_DoD14` — dropped the `ProbeResult` identity and `client_module.EMBED_NO_VECTOR_REASON` asserts; keeps `gateway.EMBED_NO_VECTOR_REASON == "no_usable_vector"` and `ProbeResult` defaults (`model_names == ()`, `note is None`)
  - `test_probe_outcome_values_are_unchanged__S035_001_DoD14` — unchanged (the four `ProbeOutcome` values)
  - DoD-14 section comment cites DEC-035-15; step 001 DoD-4..DoD-13 tests unchanged and back in the suite
- Coverage: step 001 DoD-14 ✓ (gateway side only, per DEC-035-15); step 005 coverage unchanged

### Step 006 — tests (2026-11-09)
- `backend/tests/test_deployment_files.py` — DoD-1: the pin constant moves to `@v0.2.1` (replaces step 001's `v0.2.0` assertion; the three pyproject tests are renamed `test_s035_001_dod3_s035_006_dod1_*`); new `test_s035_006_dod1_installed_library_reports_version_0_2_1` (`llm.__version__ == "0.2.1"`); `httpx` still a runtime dependency
- `backend/tests/llm_fakes.py` — helper `library_status_error(status, *, message, description)` builds a real `LLMError(..., status=n, kind="status")` (DEC-035-20); documented in the module contract
- `backend/tests/test_llm_gateway_probe.py` — DoD-2: `status_error` / `_sentinel_error` carry `status=`; new `test_probe_auth_failed_is_read_from_the_error_status__S035_006_DoD2` (13 cases × 2 kinds) and `test_probe_auth_failure_leaks_no_provider_text__S035_006_DoD2`
- `backend/tests/test_llm_gateway_embed.py` — DoD-2, DoD-3: status cases built status-bearing; new `test_embed_auth_failed_is_read_from_the_error_status__S035_006_DoD2`, `test_embed_auth_failure_leaks_no_provider_text_and_has_no_cause__S035_006_DoD2`, `test_embed_no_usable_vector_keeps_the_message_prefix_test__S035_006_DoD3` (`Invalid response…` → `no_usable_vector` with or without `kind="invalid_reply"`; `invalid_reply` errors whose message does not start that way → `unreachable`)
- `backend/tests/test_llm_gateway_complete.py` — DoD-2: status cases carry `status=`; new `test_complete_auth_failed_is_read_from_the_error_status__S035_006_DoD2` (reason, no provider text in message/args/detail/log, no cause)
- `backend/tests/test_llm_registry_models.py` — DoD-2 (DEC-035-20): the `auth` case of `_LIBRARY_FAILURES` (~:889) gains `status=401`
- `backend/tests/test_llm_gateway_compose.py` — DoD-2, DoD-4..DoD-8, DoD-14. The fake `chat_with_tools` gains `tool_errors` / `on_tool_event` (and records any other keyword); with `tool_errors="result"` it plays the tolerant loop (`start` event, then `not_offered` / `bad_arguments` / `unknown_argument` error event with the fixed model text and no invocation, or invoke + `result`); without it, the 0.2.0 strict raising. New step types `RawCall(name, arguments, provider_call_id)` and `Emit(event)`. Library errors carry `status=`. The three strict-mode tests are retired with a comment citing `DEC-arch-llm-client-library-15`; `test_compose_runner_exception_surfacing_as_runtime_error_is_unreachable__DoD10` is kept as a generic `RuntimeError` mapping check (runner emits, then the library raises `RuntimeError`)
- `backend/tests/test_compose_source.py` — DoD-9..DoD-13. The gateway-shaped fake gains a `Reject(name, arguments, kind)` step yielding `ComposeRejected(call=ToolCall("call_<n>", …), kind=ComposeRejectionKind(kind))` from the same counter as `Call`; `dispatch_calls` fixture wraps `dispatch` at its three bindings (records, then delegates)
- `backend/tests/test_live_llm.py` — DoD-15 `[manual/live]`: optional `test_live_rejection_is_yielded_and_the_exchange_continues__S035_006_DoD15` (needs `LLAMA_SWITCH_CHAT_MODEL`; skips when the model makes no mistake or keeps repeating it past 180 s); step 005 checks unchanged

| DoD | Tests |
|---|---|
| DoD-1 | `test_deployment_files.py`: `test_s035_001_dod3_s035_006_dod1_pyproject_declares_llm_client_git_dependency`, `…_pyproject_dependency_string_is_verbatim`, `…_pyproject_still_declares_httpx`, `test_s035_006_dod1_installed_library_reports_version_0_2_1` |
| DoD-2 | `test_probe_auth_failed_is_read_from_the_error_status__S035_006_DoD2`, `test_probe_auth_failure_leaks_no_provider_text__S035_006_DoD2`; `test_embed_auth_failed_is_read_from_the_error_status__S035_006_DoD2`, `test_embed_auth_failure_leaks_no_provider_text_and_has_no_cause__S035_006_DoD2`; `test_complete_auth_failed_is_read_from_the_error_status__S035_006_DoD2`; `test_compose_auth_failed_is_read_from_the_error_status__S035_006_DoD2`; plus status-bearing step 001/002/003 mapping tables and `test_real_client_failures_block_the_designation__S006_004_DoD10[auth]` |
| DoD-3 | `test_embed_no_usable_vector_keeps_the_message_prefix_test__S035_006_DoD3` |
| DoD-4 | `test_compose_passes_tolerant_tool_errors_and_a_callable_observer__S035_006_DoD4`, `test_compose_builds_the_client_with_exactly_four_keywords__S035_006_DoD4` |
| DoD-5 | `test_compose_yields_one_rejection_between_the_surrounding_text__S035_006_DoD5` (6 cases incl. `""` name), `test_compose_rejection_kinds_are_the_three_gateway_values__S035_006_DoD5`, `test_compose_rejection_ids_share_the_wrappers_counter__S035_006_DoD5`, `test_compose_never_uses_the_events_own_call_id__S035_006_DoD5`, `test_compose_each_error_event_of_a_rejection_kind_yields_exactly_one_rejection__S035_006_DoD5`, `test_compose_undeclared_argument_is_rejected_by_the_explicit_signature__S035_006_DoD5` (DEC-035-19) |
| DoD-6 | `test_compose_ignores_start_result_and_non_rejection_errors__S035_006_DoD6`, `test_compose_a_wrapper_call_appears_once_through_the_runner__S035_006_DoD6` |
| DoD-7 | `test_compose_never_passes_on_output_call_id_or_library_text__S035_006_DoD7` |
| DoD-8 | `test_compose_stream_continues_after_rejections_and_ends_normally__S035_006_DoD8`, `test_compose_a_rejection_as_the_last_step_still_ends_normally__S035_006_DoD8` |
| DoD-9 | `test_a_rejection_streams_tool_start_then_tool_fail_in_place_and_reaches_done__S035_006_DoD9` (3 kinds), `test_a_rejection_with_object_arguments_starts_with_those_arguments__S035_006_DoD9`, `test_a_rejection_with_an_empty_name_keeps_the_name_empty__S035_006_DoD9`, `test_rejections_and_wrapper_calls_keep_their_ids_and_order__S035_006_DoD9` |
| DoD-10 | `test_a_rejection_writes_one_failed_tool_row_before_the_assistant_row__S035_006_DoD10` (3 kinds; payload fields, verbatim irregular-spacing arguments, `list_zone` `tool_status == "failed"`), `test_a_rejection_with_an_empty_name_writes_an_empty_tool_name__S035_006_DoD10`, `test_each_rejection_writes_its_own_row_with_its_own_id__S035_006_DoD10` |
| DoD-11 | `test_closing_the_source_at_a_rejections_tool_start_writes_no_tool_row__S035_006_DoD11`, `test_a_stop_at_a_rejections_tool_start_keeps_the_text_and_writes_no_tool_row__S035_006_DoD11` (SSE harness pulled chunk by chunk, then `aclose()` as a server does) |
| DoD-12 | `test_a_rejection_is_logged_once_with_its_name_and_kind_and_no_arguments__S035_006_DoD12` (3 kinds), `test_two_rejections_give_two_log_records__S035_006_DoD12` |
| DoD-13 | `test_a_not_offered_rejection_with_object_arguments_replays_as_the_pair__S035_006_DoD13`, `test_any_rejected_row_replays_as_the_pair_or_is_skipped_never_an_orphan__S035_006_DoD13` (5 cases) |
| DoD-14 | every step 003 test in `test_llm_gateway_compose.py` now runs against the tolerant fake (the gateway passes `tool_errors="result"`), plus `test_compose_wrapper_path_runs_unchanged_against_the_tolerant_library__S035_006_DoD14`; step 003 DoD-10 via `test_compose_failure_yields_queued_events_then_raises_mapped__DoD10` (status-bearing 401/403) and the kept `RuntimeError` test; three strict-mode tests retired (`DEC-arch-llm-client-library-15`); step 004 DoD-3..5, 8 unchanged in `test_compose_source.py` |
| DoD-15 | `[manual/live]` — optional `test_live_rejection_is_yielded_and_the_exchange_continues__S035_006_DoD15` |

- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 [manual/live, optional live test]
- Notes:
  - DoD-12 is asserted as "exactly one loguru record contains both the tool name and the kind value" (format `{message} {extra}`, so a bound field also counts) and "no record contains the argument sentinel".
  - DoD-11 (harness clause) closes the `frame_stream` with `aclose()` after pulling the `tool_start` chunk (019 DoD-8's "disconnect by close"), since a cancellation can only reach the source while it is suspended at that frame.
  - DoD-9's object-arguments test asserts `tool_start.args == {"query": "inn"}` for argument text `{"query":"inn"}` — the same `tool_start` the step 004 DoD-3 test expects for that text.
  - DoD-14's step 004 clauses run against the gateway-shaped fake in `test_compose_source.py`, not the fake library; no end-to-end source → real gateway → fake library test was added.
  - No out-of-scope module builds a 401/403 `LLMError` (grep over `backend/tests`): only the five step 006 modules did.

## Notes & Issues

_populated by the coder when worth saying_

- Step 001 tests: DoD-9 "built with no bearer token" is asserted as a falsy `bearer_token` keyword (absent, `None` or `""` all satisfy it). DoD-2 asserts suppression at every level DEBUG..CRITICAL, matching the existing `httpx` treatment; it pins the observable absence, not the mechanism.
- Step 002 tests: out-of-scope test modules break because of this step's own interface, and none of them is in any step's Test files. (a) Local three-argument embedding factories `_ExplodingFactory.__call__(base_url, api_key, timeout_seconds)` in `backend/tests/test_session_index.py:881` and `backend/tests/test_record_keeping_embedding.py:797`. Called with four arguments they raise `TypeError`, not the `RuntimeError` those F005 DoD-10 tests expect; each needs a `kind` first parameter. (b) Import guards that permit exactly one `app.services` module: `test_memos_service.py` `_PERMITTED_SERVICE_IMPORT = "app.services.embedding"`, `test_messages_service.py` `_PERMITTED_SERVICE_IMPORT = "app.services.session_index"`, and `test_settle_service.py` `_ALLOWED_INDEX_MODULE` (settle DoD-23). The skeleton (and 002.context.md) has `memos.py`, `messages.py` and `settle.py` import `LlmGateway` from `app.services.llm.gateway` directly, so these guards now flag it. Each guard needs the same "approved deviation" narrowing for `app.services.llm.gateway` / `LlmGateway`, or else a re-export through the permitted module. I did not check whether `characters.py` / `setups.py` / `session_index.py` have similar guards; my greps found none. Context.md's "every other test module is therefore untouched" does not hold for these five modules. **Resolved:** the user accepted DEC-035-14 (2026-11-09), and the five edits were made as described above.
- Step 002 tests: feature-006 default-timeout assertions in `test_admin_llm_router.py` and `test_llm_registry_servers.py` were moved from 30.0 to 600.0, following step 001's 600 s default (`test_config.py` already expects 600.0).
- Step 003 tests: the fake library classes accept exactly the DEC-035-3 construction keywords (`model`, `base_url`, `timeout`, `bearer_token`); the `openai` fake imitates `OpenAIAPIClient` by raising `ValueError` at construction on an empty token, so DoD-2/DoD-11 hold whether the gateway checks the key first or catches the constructor's refusal. "No system keyword / no options" is asserted as `system is None` / `options is None` (absent or explicit `None` both pass). The compose failure tests also assert `__suppress_context__ is True` (DEC-035-8, "no chained cause or context"), which DoD-10 implies but does not spell out.
- 2026-11-09 (step 004 tests): the DoD-5 test (`test_compose_source.py`) monkeypatches `dispatch` at three bindings: `app.services.compose.dispatch` (with `raising=False`), `app.services.tools.dispatch` and `app.services.tools.seam.dispatch`. This makes the raise observable whichever binding compose uses, without reading its source.
- 2026-11-09 (step 004 tests): two 023 translation clauses have no `complete`-era meaning: "the stream iterator is closed" and "reasoning deltas ignored". Their tests now assert the 035 equivalents, which are a single `complete` call with nothing cached on failure, and a stripped `<think>` block.
- 2026-11-09 (step 004 tests): `backend/tests/test_privacy_audit_logs.py:92` imports `ProbeOutcome`/`ProbeResult` from `app.services.llm.client`. Resolved: DEC-035-13 moved it to step 002, whose test-coder switched the import.
- Step 005 tests: the DoD-5 live chat checks read the chat model name from a new opt-in variable `LLAMA_SWITCH_CHAT_MODEL` (no chat model is named in the spec; the server's model set is deployment-specific) and skip without it.
- Step 001 (coder): no `# type: ignore` was needed for `async with` on a library client — mypy's config does not flag the unannotated `__aenter__`/`__aexit__`, contrary to 001.context.md § Mypy; DEC-035-5 holds trivially so far.
- Step 003 (coder): `complete` and `compose` map *every* `Exception` out of the library (not only `LLMError`/`RuntimeError`/`ValueError`) to `unreachable`, matching `embed`, so no stray exception type can carry provider text past the gateway. A malformed declaration (no `function` object or name) or a property name that is not a Python identifier also surfaces as `unreachable`. The only `# type: ignore` added is `[attr-defined]` on the minted callable's `__signature__`, which is a stdlib typing gap, not a library one. Library-typing casts (`messages`, `tools_definitions`) are `cast(Any, …)`.
- Step 005 (coder): stale docstring mentions of the deleted client remain in out-of-scope files, left for the glossary/finalize pass: `backend/app/routers/admin_llm.py:21` ("production answer is the class `LlmClient`"), `backend/app/services/web_search/google.py:36` and `:74` ("as in / mirroring `app.services.llm.client`"), and `backend/app/services/llm/__init__.py` module docstring ("the one OpenAI-compatible client"). After deletion, `httpx` is imported under `backend/app/` only by `services/web_search/google.py`.

## Ultra phase

- orient: done 2026-11-08 — typecheck: isolated (mypy) · pairable: 0
- waves: skeleton W1 001 · W2 002 (alone: changes existing symbol) · W3 003 (shares gateway.py with 002) · W4 004 (alone: changes existing symbol) · W5 005 — tests T1 001,002,003,005 · T2 004 (shares privacy_audit_support.py with 002)
- harvest: done — docs/.cache/ultra/035.llm-client-gateway/harvest.md (3 reports)
- mode: serial — 0 pairable steps (gateway.py shared by 001/002/003, llm_registry.py by 002/004, client.py by 001/005) · profile: light (Python 3.12 + uv, one package)
- skeleton: W1 done · W2 done · W3 done · W4 done — steps 001, 002, 003, 004 frozen · 005 none (deletion step, no interface; DEC-035-13 adds `app/models/admin_llm.py` to 002)
- note: test_llm_client.py, test_llm_chat_stream.py deleted by the orchestrator on step 005 test-coder's behalf (it has no delete tool); deletion is in 005's Test files
- tests: done — steps 001, 002, 003, 004, 005 (T1 001,002,003,005 · T2 004; DEC-035-14 added five out-of-set test modules to 002)
- red-gate: PASS (run 1)
- code: done — steps 001, 002, 003, 004, 005 (no re-freeze)
- verify: FAIL (run 1) — 001 SPEC (DoD-14 binds to client.py, which 005 deletes), 002 CODE, 003 CODE; 004, 005 PASS
- verify: PASS (run 2) — 5372 passed; mypy, ruff clean. Fixes after run 1: DEC-035-15 (001 SPEC), 002 CODE r1, 003 CODE r1
- glossary: done — services/AGENTS.md, tests/AGENTS.md updated; services/llm/AGENTS.md created; stale client.py docstrings fixed (admin_llm, google, llm/__init__, chat, compose)
- step 006 added (2026-11-09, user: llm-client 0.2.1 as part of 035; DEC-arch-llm-client-library-13..17, DEC-035-17..20). Build: harvest → skeleton → tests → red gate → code → verify (single-step wave)
- skeleton 006: done — ComposeRejected, ComposeRejectionKind, widened compose yield, write_failed_tool_row; llm 0.2.1 locked (2964ac86)
- tests 006: done — DoD-1..14 [test], DoD-15 live opt-in; three 0.2.0-strict compose tests retired (DEC-arch-llm-client-library-15)
- red-gate 006: PASS (run 1) — 76 red for reason, no regressions outside step files
- code 006: done (round 1, no re-freeze)
- verify 006: PASS (run 3) — 5492 passed; mypy, ruff clean; live 4 passed, 3 skipped (LLAMA_SWITCH_CHAT_MODEL unset)
- glossary 006: done — llm/, services/, tests/ AGENTS.md; comment fixes (gateway _tool_callable docstring, max_loops cites -4, compose docstring wrap)
