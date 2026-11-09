# Feature 035 — llm-client-gateway: feature-wide context

## Goal and scope

This feature replaces the in-house `httpx` LLM client
(`backend/app/services/llm/client.py`) with the external library
**`llm-client` 0.2.0**, behind one module,
**`backend/app/services/llm/gateway.py`**, exactly as the architecture
revision of 2026-11-08 states. It is a transport migration and adds the OpenAI
Responses protocol. **Nothing the roleplayer or the administrator sees
changes**: frames, persisted rows, replay, the stop, translation, probe
outcomes and embeddings all behave as before, except where the architecture
names a change. The named changes are:

- `call_id` is always minted;
- the timeout default is 600 s, total per request;
- translation uses a non-streamed call;
- `kind` is the dispatch key;
- model-side tool mistakes become stream errors. This is a temporary library
  limitation.

There is no `brief.md`, and no new product behaviour. Every DoD citation names
an existing id whose behaviour is preserved.

Out of scope: any change to the following, beyond what the steps name:

- `chat.py`, other than the fact that it stays;
- `frames.py`, the harness and the tool seam (`services/tools/`);
- context assembly;
- the `web_search` provider (`httpx` stays for it);
- every frontend file.

## Architecture this plan realizes (read these; do not restate)

- `docs/architecture/llm-and-streaming.md`:
  - § The LLM gateway over `llm-client`, all subsections: the four operations,
    one protocol / `kind`, base URL, errors, timeout;
  - § The model registry (the request path);
  - § Thinking;
  - § Stopping model work in flight;
  - § The tool-calling loop;
  - § How one exchange runs;
  - § Temporary library limitation;
  - § Translation;
  - § Decision history.
- `docs/architecture/session-stream.md`: § The compose route and the streaming
  harness, § The compose source, § The tool seam and dispatch.
- `docs/architecture/backend-structure.md`:
  - § Layout (`gateway.py`; `client.py` removed);
  - § Configuration;
  - § The error model (`llm_unreachable` detail; `tool_failed`);
  - § The connection probe;
  - § The first async code in the backend.
- `docs/architecture/deployment.md`: the git-dependency image-build note; the
  library tracing variables (an operator switch that RPHelper leaves alone); the
  nginx 300 s note.
- `docs/architecture/data-model.md`: `llm_servers.kind` is the dispatch key.

## Decisions this plan binds to

- **Architecture-level, already decided:** `DEC-arch-llm-client-library-1` ..
  `-12` (`docs/decisions/arch-llm-client-library.md`). Cite them; never
  re-decide them.
- **Plan-level:** `DEC-035-1` .. `-12` (`docs/decisions/035.llm-client-gateway.md`).
  Steps cite them by id.

## Cross-cutting rules every step holds

- **The gateway is the only module under `app/` that imports the library
  (`llm`).** No library type appears in a signature outside `gateway.py`
  (DEC-035-5).
- **No provider text leaves a failure.** The library's error message and its
  `description` never reach a log line, an exception message or a `detail`.
  Every `llm_unreachable` from the gateway is raised with no chained cause
  (DEC-035-8, `DEC-arch-llm-client-library-10`).
- **One library client per operation.** It is built inside the coroutine that
  uses it, entered with `async with`, and closed when the operation ends. The
  gateway object itself holds no library client. The sync embedding services
  keep calling `embed` through their existing `asyncio.run` bridge, unchanged.
- **The factory seam stays** (DEC-035-1). Factories are called
  `(kind, base_url, api_key, timeout_seconds)`, and the gateway class `LlmGateway`
  is the production factory. Secret resolution (`resolve_secret`, raising
  `secret_ref_missing` before any network call) stays in the registry and is
  unchanged.
- **The gateway raises the existing `llm_unreachable` error class.** It does not
  import `llm_registry`, `frames.py` or `services/tools/`, because each of these
  reaches back to the gateway through an import cycle (DEC-035-6). It may import
  `services/llm/chat.py`, which imports nothing from `app.services`.
- **No reasoning options and no `default_options`** are sent
  (`DEC-arch-llm-client-library-12`). The library's tracing variables are not
  touched.
- **Every step leaves the suite green.** The order below is chosen for that. A
  step changes only the callers it lists, and old and new paths coexist until
  step 005.
- **Gates:** `mypy app` and `ruff check .` (commands in the root `AGENTS.md`;
  on Linux the interpreter is `.venv/bin/python`).

## Vocabulary

- **The library** is `llm-client` 0.2.0, the importable package `llm`. Its client
  classes are `OpenAIAPIClient` (`kind = 'openai'`) and `LlamaSwapAPIClient`
  (`kind = 'llamaswap'`), and its error is `LLMError(message, description)`.
- **The gateway** is `LlmGateway` in `services/llm/gateway.py`, with four async
  operations: `probe`, `embed`, `complete` and `compose`.
- **A library client** is one instance of a library class, built per operation
  through the gateway's `library_clients` seam (DEC-035-3).
- **The factory** is anything called `(kind, base_url, api_key, timeout_seconds)`
  that returns a gateway-shaped object. In production it is `LlmGateway`; in
  tests it is a fake.
- **The runner** is `compose.py`'s per-call half of the tool wrapper. The
  gateway's half presents the call to the library (DEC-035-6).

## Library facts every step relies on (0.2.0)

- `base_url` must include `/v1`. The library appends `/models`, `/responses` and
  `/embeddings`. The gateway normalises the URL (DEC-035-11).
- Clients are async context managers and have no `close()`.
  `OpenAIAPIClient` raises `ValueError` at construction on an empty bearer token;
  `LlamaSwapAPIClient` accepts none.
- `LLMError` messages:
  - non-2xx → `"Request to <url> failed with status <n>"`, with the body in
    `.description`;
  - transport → `"Request to <url> failed: timeout|interrupted transfer|connection failure"`;
  - reply-shape failures → messages starting `"Invalid response"` or
    `"Unreadable reply"`.
- The timeout is the total per request, so for a streamed compose it applies per
  tool round.

## Files touched, by step

| Step | Source | Tests |
|---|---|---|
| 001 | `backend/pyproject.toml`, `backend/uv.lock`, `Dockerfile`, `app/config.py`, `app/logging.py`, `app/services/llm/gateway.py` (new), `app/services/llm/client.py` | `test_config.py`, `test_logging.py`, `test_logging_redaction.py`, `test_deployment_files.py`, `test_llm_gateway_probe.py` (new) |
| 002 | `gateway.py`, `llm_registry.py`, `embedding.py`, `dependencies.py`, and every module with an `LlmClient` factory default | `llm_fakes.py`, `privacy_audit_support.py`, `test_llm_gateway_embed.py` (new), the probe/embed router, registry, dependency and embedding tests |
| 003 | `gateway.py` | `test_llm_gateway_complete.py` (new), `test_llm_gateway_compose.py` (new) |
| 004 | `llm_registry.py`, `compose.py`, `translation.py`, `routers/stream.py`, `routers/translation.py` | `privacy_audit_support.py`, `test_open_chat_client.py`, the compose, translation and web-search-offering tests |
| 005 | `app/services/llm/client.py` (deleted) | `test_llm_client.py` and `test_llm_chat_stream.py` (deleted), `test_live_llm.py`, `test_llm_gateway_boundary.py` (new) |

All paths are under `backend/` except the repository-root `Dockerfile`.

## Fakes — the shared test helpers keep their names

`backend/tests/llm_fakes.py` and `backend/tests/privacy_audit_support.py` are
shared by dozens of test modules that only pass a fake factory through. Their
public helper names stay, and only the call shape and the scripted behaviour
change (DEC-035-1, `DEC-arch-llm-client-library-11`). The helpers are:

- in `llm_fakes.py`: `FakeEmbeddingClient`, `FakeClientFactory`, `fake_factory`,
  `wrong_length_factory`, `unreachable_factory`;
- in `privacy_audit_support.py`: `FakeChatClient`, `FakeChatClientFactory`,
  `text_round`, `tool_call_round`, `failure_round`, `script_text`,
  `script_tool_call`, `script_failure`, `ScriptedProbeClient`,
  `ScriptedProbeFactory`, `delegating_embedding_factory`.

Every other test module is therefore untouched.

## Folder glossaries

`app/AGENTS.md`, `app/services/AGENTS.md` and `tests/AGENTS.md` mention
`client.py`, `test_llm_client.py` and `test_llm_chat_stream.py` inside their
fenced glossaries. The post-coding glossary writer refreshes those entries once
step 005 has removed the files. The fenced glossary is not in any coder's
Source files.
