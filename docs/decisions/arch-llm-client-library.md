# Decisions — arch-llm-client-library
**Stage:** architecture revision · **Feature:** arch-llm-client-library (architect session, 2026-11-08: every LLM call moves to the `llm-client` 0.2.0 library)

Decisions taken in the /architect session that moved RPHelper's LLM calls from
the in-house `httpx` client to the shared `llm-client` library. The contracts
they sit under — the LLM gateway and its four operations, `kind` as the dispatch
key, the library-owned tool loop and RPHelper's per-tool wrapper, the stop, the
errors-and-privacy rules, the one timeout — are stated in `llm-and-streaming.md`;
these entries carry the mechanisms, the numbers and what was weighed and
rejected. The user approved all of them on 2026-11-08. They are implemented by
feature 035.llm-client-gateway (delivered 2026-11-09), whose planner cited these
ids without re-deciding them; that feature's own mechanisms are `DEC-035-1` ..
`-20`.

Entries 13 onward are a second revision (2026-11-09): the library moves from
0.2.0 to 0.2.1. The user approved them on 2026-11-09, and they were built the
same day as feature 035.llm-client-gateway step 006. Earlier entries are not
rewritten — each carries a pointer line to the entry that refines or partly
supersedes it.

### DEC-arch-llm-client-library-1 — Adopt `llm-client` 0.2.0 as a git dependency; Responses clients only, selected by `kind`
- **Status:** accepted
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** —
- **Date:** 2026-11-08 · **Decided by:** user
- **Question:** How does RPHelper get the OpenAI Responses protocol, which OpenAI's reasoning models need in order to call function tools — and in what form is the client it uses brought in?
- **Decision:** Depend on the shared library `llm-client`, pinned as the runtime dependency `llm-client @ git+https://github.com/Iezious/PythonLLMClient.git@v0.2.0` in `backend/pyproject.toml`, locked in `backend/uv.lock`. Use only its Responses-protocol classes: `OpenAIAPIClient` for `llm_servers.kind = 'openai'`, `LlamaSwapAPIClient` for `'llamaswap'`. The gateway builds them with `async with`, one per operation, inside the coroutine. `probe` is built on `list_models()`, `embed` on `embed_batch()`, `complete` on `chat()`, `compose` on `chat_with_tools(stream=True)`. `httpx` stays a runtime dependency for the `web_search` Google provider only.
- **Reason:** One maintained client shared with other projects, which already implements the Responses protocol, including carrying reasoning between tool rounds. The two backends differ in small ways (bearer token required vs optional; reasoning-summary requests) that the library encodes per class.
- **Rejected:** Keep the in-house `httpx` client and add the Responses protocol to it — a second implementation of a protocol the shared library already maintains. A local path dependency on the library — breaks the container build and every other machine. The library's chat-completions classes — OpenAI's reasoning models refuse function tools there; flip condition: a llama-swap engine without Responses support has to be served, which adds a per-server protocol field.
- **Supersedes:** the as-built `httpx.AsyncClient` client of plans 006, 021 and 024 (`chat_stream` / `embed` / `probe`); 023 D2 / D8 (translation reusing `chat_stream` and joining deltas); the rule "one client; `kind` is a presentation label, never a dispatch key". Plan-local decisions, no DEC ids.
- **Lands in:** `backend/pyproject.toml`, `backend/uv.lock`; the LLM gateway `backend/app/services/llm/gateway.py`, the only module that imports `llm` (replacing `client.py`, which the building plan removes; `chat.py` and `frames.py` stay); `backend/app/services/llm_registry.py`, `backend/app/services/embedding.py`, `backend/app/services/translation.py`, `backend/app/services/compose.py` as callers; the image build (needs `git` + network access to github.com)
- **Cites:** `llm-and-streaming.md` § The LLM gateway over `llm-client`, § One protocol; `kind` selects the library class; `overview.md` § stack decisions; `deployment.md` § Prod topology
- **Refined by:** `DEC-arch-llm-client-library-13` — the pinned tag is `v0.2.1` (2026-11-09).
- **Resolved (2026-11-09):** `client.py` was removed by 035.llm-client-gateway (step 005); the gateway is the only importer of `llm`.

### DEC-arch-llm-client-library-2 — One timeout: total time per request, default 600 s
- **Status:** accepted
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** —
- **Date:** 2026-11-08 · **Decided by:** user
- **Question:** What does `llm_request_timeout_seconds` mean once the library makes the request, and what is its default?
- **Decision:** It stays the single LLM timeout and is passed to the library as its total time per request; for a streamed compose that is per tool round. The default rises from 30.0 to **600.0** seconds, the library's own default.
- **Reason:** The library offers only a total timeout, and a 30 s total would cut off any long generation mid-reply. 600 s matches the library's default rather than inventing a number.
- **Rejected:** Keeping 30 s — a total of 30 s ends ordinary long replies. Splitting into per-phase or per-read settings — the library has no per-read timeout to configure.
- **Supersedes:** plan 006's 30.0 default and plan 021's per-`httpx`-phase meaning; closes the streaming-read-timeout `_TBD:` (021 D10).
- **Lands in:** `backend/app/config.py` (`llm_request_timeout_seconds`, `RPHELPER_LLM_REQUEST_TIMEOUT_SECONDS`); `backend/app/services/llm/gateway.py`
- **Cites:** `llm-and-streaming.md` § The timeout; `backend-structure.md` § Configuration; `deployment.md`'s note after the nginx directive table (`proxy_read_timeout 300s` is kept below this timeout by user decision, 2026-11-08). Accepted consequence: a probe or embedding against a hanging host waits up to 600 s. Flip condition: the library gains a per-read/idle timeout and probes against dead hosts become a real annoyance.
- **Refined by:** `DEC-arch-llm-client-library-17` — 0.2.1's streamed-only silence limit is not used; this one total stands (2026-11-09).

### DEC-arch-llm-client-library-3 — `auth_failed` is read from the library error's message
- **Status:** accepted
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** —
- **Date:** 2026-11-08 · **Decided by:** user
- **Question:** The library's `LLMError` has no status attribute in 0.2.0. How does the gateway tell `auth_failed` from `unreachable` for the probe, and set an embed failure's reason?
- **Decision:** On a non-2xx the library raises `LLMError` with the message `"Request to <url> failed with status <n>"`. `status 401` or `status 403` in that message gives **`auth_failed`**. Any other status, a transport failure (`"failed: timeout|interrupted transfer|connection failure"`) or an unreadable listing (`"Invalid response ..."` / `"Unreadable reply ..."`) gives **`unreachable`**. An empty model list gives **`model_list_empty`**. `embed` uses the same status split for its `llm_unreachable` `detail.reason` (`auth_failed` / `unreachable`); an `LLMError` raised by the library's vector validation gives `detail.reason` **`no_usable_vector`**. Only the status is read from the message; the message and the error's `description` are never logged or forwarded (`DEC-arch-llm-client-library-10`).
- **Reason:** It keeps the probe's four-value taxonomy without patching the library first.
- **Rejected:** Patching the library before adoption — delays the move for one attribute.
- **Lands in:** `backend/app/services/llm/gateway.py`
- **Cites:** `llm-and-streaming.md` § The gateway, § Errors. Flip condition: the library adds a status attribute (asked in the library follow-up notes, item 4) — read it instead of the message.
- **Refined by:** `DEC-arch-llm-client-library-16` — the flip condition is met in 0.2.1; the status split reads the error's status attribute (2026-11-09).

### DEC-arch-llm-client-library-4 — The tool-loop cap is `max_loops=sys.maxsize`
- **Status:** accepted
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** —
- **Date:** 2026-11-08 · **Decided by:** user
- **Question:** The library's `chat_with_tools` takes a loop cap; RPHelper's rule is that there is no iteration cap. What is passed?
- **Decision:** `max_loops=sys.maxsize`.
- **Reason:** `None` is a `TypeError` in 0.2.0, and any real number would be an iteration cap the product rules out. The stop bounds a runaway loop.
- **Lands in:** `compose` in `backend/app/services/llm/gateway.py`
- **Cites:** `llm-and-streaming.md` § The tool-calling loop (no iteration cap)

### DEC-arch-llm-client-library-5 — Minted call ids, and the persisted `arguments`
- **Status:** accepted
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** —
- **Date:** 2026-11-08 · **Decided by:** user
- **Question:** The library never exposes the provider's call id or raw argument string to a tool callable. What does the wrapper put in `call_id` and in the persisted tool row's arguments?
- **Decision:** The wrapper mints `call_<n>` from a per-exchange counter — the form the old client used as its fallback. The persisted `arguments` is the JSON re-serialisation of the keyword arguments the library parsed (`json.dumps(..., ensure_ascii=False)`). `call_id` stays opaque; its only job is to pair a call with its output.
- **Reason:** Replay and the frames need a stable pairing id within the exchange, and the raw provider string is not available.
- **Supersedes:** "the provider's own call id, with a `call_<n>` fallback" (021 D11), plan-local.
- **Lands in:** `backend/app/services/compose.py` (the wrapper) or `backend/app/services/llm/gateway.py`, per the building plan
- **Cites:** `llm-and-streaming.md` § Ids in frames, § How one exchange runs
- **Refined by:** `DEC-arch-llm-client-library-15` (a model-side rejection draws its `call_id` from the same counter, and its row's `arguments` is the model's own text) and `-17` (0.2.1 reports the provider's call id; minting stays) (2026-11-09).
- **Resolved (2026-11-09):** the building feature settled the "per the building plan" choice in `DEC-035-6`: the id is minted and the `arguments` re-serialised in the gateway's half of the wrapper, `backend/app/services/llm/gateway.py`; the compose source's half runs the per-call tool rules.

### DEC-arch-llm-client-library-6 — Each wrapper carries an explicit signature from its declaration
- **Status:** accepted
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** —
- **Date:** 2026-11-08 · **Decided by:** user
- **Question:** 0.2.0 checks a call's argument names against `inspect.signature(callable).parameters`, which rejects a bare `**kwargs` wrapper. How does a generic wrapper pass that check?
- **Decision:** Each tool wrapper gets an explicit signature built from its declaration's JSON-schema `properties`, set through `__signature__`: keyword-only parameters, each defaulting to absent.
- **Reason:** One generic wrapper serves all three tools, and the declarations in `services/tools/definitions.py` stay the single statement of what each tool takes.
- **Rejected:** A hand-written wrapper per tool — three copies of the same five steps, and a second place a tool's parameters are stated.
- **Lands in:** the wrapper (where `DEC-arch-llm-client-library-5` places it); reads `backend/app/services/tools/definitions.py`
- **Cites:** `llm-and-streaming.md` § How one exchange runs. Flip condition: the library accepts `VAR_KEYWORD` callables (follow-up notes, item 3).

### DEC-arch-llm-client-library-7 — The wrapper never raises a tool's exception into the library
- **Status:** accepted; temporary-limitation clause superseded by DEC-arch-llm-client-library-15
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** —
- **Date:** 2026-11-08 · **Decided by:** user
- **Question:** 0.2.0 turns an exception raised by a tool callable into `RuntimeError` and ends the loop. How is "a failed tool is a tool result" kept?
- **Decision:** The wrapper catches every tool failure and returns the fixed "tool failed" text as the tool output, after emitting `tool_fail`. `CancelledError` and `GeneratorExit` still propagate, so a stop during a tool ends the exchange and writes no tool row. The model-side mistakes the library rejects before any wrapper runs (a tool that was not offered, an unknown or empty name, non-object arguments, undeclared argument names) are outside the wrapper's reach in 0.2.0. The `tool_fail` rule for them stands; this is a **temporary library limitation**, not a deviation from the rule: until a library release makes those cases tool results, they surface as a stream error (`llm_unreachable`) and the harness keeps the partial text. When that release lands, the gateway relies on it and this limitation is closed, with no rule change.
- **Reason:** The wrapper is the only point where RPHelper can turn a tool's own failure into a result in 0.2.0.
- **Lands in:** the wrapper
- **Cites:** `llm-and-streaming.md` § The tool-calling loop, § Temporary library limitation — model-side tool mistakes (0.2.0); `session-stream.md` § The tool seam and dispatch. Closing condition: a library release that makes those cases tool results (follow-up notes, item 1; no release version is fixed).
- **Superseded in part by:** `DEC-arch-llm-client-library-15` — the closing condition is met by 0.2.1; model-side mistakes become `tool_fail` through the observer. The wrapper's never-raise rule stands (2026-11-09).

### DEC-arch-llm-client-library-8 — How a compose exchange ends
- **Status:** accepted; temporary-limitation clause superseded by DEC-arch-llm-client-library-15
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** —
- **Date:** 2026-11-08 · **Decided by:** user
- **Question:** What does the compose source do with the library task's result and its exceptions?
- **Decision:** The task's return value (the library's final text) is ignored; the persisted assistant row is the joined token text, as today. Library exceptions (`LLMError`, `RuntimeError`, `ValueError`) surface from the source as `llm_unreachable` (this includes, until the library release named in `DEC-arch-llm-client-library-7`, the model-side tool mistakes); the harness keeps the partial text. Closing the source cancels the task, and that cancellation closes the library's in-flight `aiohttp` request.
- **Reason:** The joined token text is exactly what streamed to the roleplayer, `<think>` tags included, and the persist rule already depends on it; a second text source could disagree with what was shown.
- **Lands in:** `backend/app/services/compose.py`
- **Cites:** `llm-and-streaming.md` § How one exchange runs, § Stopping model work in flight
- **Superseded in part by:** `DEC-arch-llm-client-library-15` — model-side tool mistakes no longer reach this path as library exceptions; the rest of this entry stands (2026-11-09).
- **Refined by:** `DEC-035-16` — every exception out of the library, not only the three classes named above, surfaces as `llm_unreachable`.

### DEC-arch-llm-client-library-9 — An OpenAI server with no credential
- **Status:** accepted
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** —
- **Date:** 2026-11-08 · **Decided by:** user
- **Question:** `OpenAIAPIClient` refuses an empty bearer token with a `ValueError` at construction. How does the gateway report it?
- **Decision:** As `llm_unreachable` with `detail.reason` `auth_failed`, before any network call; for a probe the outcome is `auth_failed`. A llama-swap server accepts no token and is built without one.
- **Reason:** A missing token on an OpenAI server is an authentication failure the administrator can act on, and the library refuses it before any request.
- **Lands in:** `backend/app/services/llm/gateway.py`
- **Cites:** `llm-and-streaming.md` § One protocol; `kind` selects the library class. A pointer that names an absent variable is still `secret_ref_missing`, raised earlier by `resolve_secret`.

### DEC-arch-llm-client-library-10 — Logging: the `aiohttp` logger tree is silenced
- **Status:** accepted
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** —
- **Date:** 2026-11-08 · **Decided by:** user
- **Question:** The library's HTTP stack is `aiohttp`, whose stdlib records reach both loguru sinks through the `InterceptHandler`. What is done about them?
- **Decision:** The `aiohttp` logger tree is added to `_SILENCED_LOGGERS` beside `httpx`, by the same rule (URLs and bodies). The library itself logs nothing to stdlib or loguru. `LLMError.description` (the provider's response body) is never logged and never put into `detail` or an error message.
- **Reason:** The redaction rule binds third-party records, and `app/logging.py` is the one place third-party loggers are silenced.
- **Lands in:** `backend/app/logging.py`; `backend/app/services/llm/gateway.py`
- **Cites:** `llm-and-streaming.md` § Errors; `deployment.md` § The redaction rule; `backend-structure.md` (no service module touches a third-party logger)

### DEC-arch-llm-client-library-11 — Testing: fakes at the gateway/factory level
- **Status:** accepted
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** —
- **Date:** 2026-11-08 · **Decided by:** user
- **Question:** The old client was tested through a mocked `httpx` transport. How is the gateway tested?
- **Decision:** Chat and embed fakes move to the gateway/factory level, with no HTTP. The `httpx`-transport tests of the old client are removed with it. Gateway adapter tests drive fake library clients rather than a mocked transport. Live tests (`-m live`) exercise the real library.
- **Reason:** RPHelper no longer owns HTTP code for LLMs, so a transport mock would test the library rather than RPHelper.
- **Lands in:** `backend/tests/`
- **Cites:** `llm-and-streaming.md` § The gateway (injectable client factory)

### DEC-arch-llm-client-library-12 — No reasoning options are sent by default
- **Status:** accepted
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** —
- **Date:** 2026-11-08 · **Decided by:** user
- **Question:** Does the gateway request reasoning or thinking options (for example OpenAI reasoning summaries)?
- **Decision:** No. No `reasoning` / thinking options are sent, and no `default_options` are set.
- **Reason:** The roleplayer has not asked to see OpenAI reasoning on screen, and local servers already stream their reasoning.
- **Rejected:** Requesting OpenAI reasoning summaries now — revisit when the roleplayer wants OpenAI reasoning on screen.
- **Lands in:** `backend/app/services/llm/gateway.py`
- **Cites:** `llm-and-streaming.md` § How one exchange runs (reasoning within one exchange), § Thinking

### DEC-arch-llm-client-library-13 — Pin `llm-client` `v0.2.1`
- **Status:** accepted
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** — (built by 035.llm-client-gateway step 006)
- **Date:** 2026-11-09 · **Decided by:** user
- **Question:** Which library release does RPHelper pin, now that 0.2.1 returns model-side tool mistakes to the model, exposes a tool-event observer and puts a status and a kind on its error?
- **Decision:** Pin `llm-client @ git+https://github.com/Iezious/PythonLLMClient.git@v0.2.1`, locked in `backend/uv.lock`. Everything else in `DEC-arch-llm-client-library-1` stands: the Responses classes selected by `kind`, one client per operation, `httpx` for `web_search` only. 0.2.1 leaves constructors, exports, the Responses classes, `aiohttp` and the library's no-logging posture unchanged, so nothing else in the gateway's construction path moves.
- **Reason:** 0.2.1 is the release that closes the temporary library limitation (`DEC-arch-llm-client-library-7`) and meets `-3`'s flip condition, with no breaking change to what RPHelper already uses.
- **Rejected:** Staying on 0.2.0 — keeps model-side tool mistakes ending the exchange, against the `tool_fail` rule.
- **Supersedes:** the `v0.2.0` tag named in `DEC-arch-llm-client-library-1` (that entry is refined, not replaced).
- **Lands in:** `backend/pyproject.toml`, `backend/uv.lock`
- **Cites:** `llm-and-streaming.md` § The LLM gateway over `llm-client`; `overview.md` § stack decisions; `deployment.md` § Prod topology

### DEC-arch-llm-client-library-14 — `compose` passes `tool_errors="result"` explicitly
- **Status:** accepted
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** — (built by 035.llm-client-gateway step 006)
- **Date:** 2026-11-09 · **Decided by:** user
- **Question:** 0.2.1's `chat_with_tools` takes `tool_errors="result" | "raise"` and defaults to `"result"` (tolerant). Does the gateway rely on the default?
- **Decision:** No. `compose` passes `tool_errors="result"` on every `chat_with_tools` call.
- **Reason:** The architecture rule (a model-side mistake is a `tool_fail` and the exchange continues) depends on tolerant handling; stating it at the call site means a future change of the library's default cannot silently restore 0.2.0's strict behaviour.
- **Rejected:** Relying on the default — correct today, silently wrong on a default flip. `"raise"` — that is 0.2.0's strict behaviour, which ends the exchange.
- **Lands in:** `compose` in `backend/app/services/llm/gateway.py`
- **Cites:** `llm-and-streaming.md` § How one exchange runs, § Model-side tool mistakes — the observer

### DEC-arch-llm-client-library-15 — Model-side tool mistakes become tool frames through the observer
- **Status:** accepted
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** — (built by 035.llm-client-gateway step 006)
- **Date:** 2026-11-09 · **Decided by:** user
- **Question:** Under `tool_errors="result"` the library answers a model-side mistake itself, before RPHelper's tool callable runs, and continues the loop — so no wrapper emits `tool_start` / `tool_fail` for it. How does the call still produce the frames and the tool row the `tool_fail` rule requires?
- **Decision:** `compose` passes `on_tool_event` an observer. The library calls it inline, in call order, on the loop's own task: one `start` event per call, then exactly one `result` or `error`. The observer acts **only** on an `error` event whose `error_kind` is `not_offered`, `bad_arguments` or `unknown_argument`: it mints a `call_id` from the **same per-compose `call_<n>` counter** the wrappers use (so ids follow invocation order) and puts one model-side-rejection item, carrying that `call_id`, the event's `name` exactly as sent (an empty name stays `""`) and its `arguments` string, into the **same ordered queue** as text pieces and wrapper events. Every other event — `start`, `result`, and any event for a call that reached a wrapper — is ignored, because the wrapper already emitted that call's frames; so no call is emitted twice. The compose source turns a rejection item into `tool_start` then `tool_fail` (code `tool_failed`) **without dispatching** and writes the failed tool row through the seam's tool-row write: status failed, code `tool_failed`, `text` the fixed failed literal, `tool_name` the model's name, payload `arguments` the event's argument string (not a re-serialisation — there are no parsed arguments). Replay treats the row like every failed tool row (the recorded call, then the fixed failed literal). Inside the exchange the model sees the library's own fixed text for the mistake (`Tool '<n>' is not available.` / `Invalid arguments for tool '<n>'.` / `Tool '<n>' has no argument '<a>'.`). `tool_raised` cannot occur, because the wrapper never raises (`-7`); if it ever does it is treated as the wrapper's own failure path, not as a second call. `unserialisable_result` is treated the same way: the call reached the wrapper, whose result is always text. The observer emits only RPHelper's own values plus the model's own name and arguments — never `output`, never the library's message, never provider text — and it never uses the event's `call_id`.
- **Reason:** It honours the `tool_fail` rule for every model-side mistake with the same frames, row and replay as any other failed call, without RPHelper re-implementing the library's validation; the one queue keeps frame order equal to call order.
- **Rejected:** Leaving 0.2.0's behaviour (ending the exchange) — breaks the rule. Driving all tool frames from the observer and dropping the wrapper's own emission — moves working code for no gain, and the wrapper still has to run dispatch. Using the library's own error text in the frame or row — it is library text; the frame carries RPHelper's code and the row RPHelper's literal.
- **Supersedes:** the temporary-limitation clauses of `DEC-arch-llm-client-library-7` and `-8`.
- **Lands in:** `compose` and the observer in `backend/app/services/llm/gateway.py`; the rejection-to-frames step and the tool-row write in `backend/app/services/compose.py` (the counter is shared with the wrapper wherever `-5` places it)
- **Cites:** `llm-and-streaming.md` § Model-side tool mistakes — the observer, § How one exchange runs, § Tool rows are replayed, not skipped; `session-stream.md` § The tool seam and dispatch; `data-model.md` § messages (tool columns). Accepted exposure: with `max_loops=sys.maxsize` (`-4`) a model that repeats a mistake loops until the roleplayer stops it.

### DEC-arch-llm-client-library-16 — `auth_failed` is read from `LLMError.status`
- **Status:** accepted
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** — (built by 035.llm-client-gateway step 006)
- **Date:** 2026-11-09 · **Decided by:** user
- **Question:** 0.2.1's `LLMError` carries `status` (the HTTP status of a non-2xx) and `kind` (a closed set). `DEC-arch-llm-client-library-3`'s flip condition is met. What does the gateway read now?
- **Decision:** `status` 401 or 403 gives `auth_failed` — for the probe outcome and for `embed`'s `llm_unreachable` `detail.reason`. Any other `LLMError` gives `unreachable`, as before; an empty model list is still `model_list_empty`. **One exception keeps a message test:** `embed`'s `no_usable_vector` is still recognised by the library message's `"Invalid response"` prefix, because `kind == "invalid_reply"` also covers an empty embedding result and an unreadable reply, which would mislabel those as `no_usable_vector`. Messages and `description` are still never logged or forwarded (`-10`).
- **Reason:** A structured status is the reliable signal the flip condition asked for; the kind is too coarse for the one distinction it would replace.
- **Rejected:** Mapping `no_usable_vector` from `kind == "invalid_reply"` — conflates three different failures under one reason.
- **Lands in:** `backend/app/services/llm/gateway.py`
- **Cites:** `llm-and-streaming.md` § The gateway, § Errors, and what never leaves a failure; refines `DEC-arch-llm-client-library-3`

### DEC-arch-llm-client-library-17 — 0.2.1 options left unused: `read_timeout`, the trace switch, the provider call id
- **Status:** accepted
- **Stage:** architecture revision · **Feature:** arch-llm-client-library · **Step:** — (built by 035.llm-client-gateway step 006)
- **Date:** 2026-11-09 · **Decided by:** user
- **Question:** 0.2.1 adds an optional `read_timeout` (a silence limit on streamed requests, default `None`), keeps its trace switch three-state (`None` = the environment decides) and reports the provider's call id on each `ToolEvent`. Does RPHelper use any of them?
- **Decision:** None of them. `read_timeout` is not passed: the 600 s total of `DEC-arch-llm-client-library-2` stays the one timeout. The trace switch is not passed: the environment decides, as before. `ToolEvent.call_id` is not read: RPHelper keeps minting `call_<n>` for every call (`-5`, `-15`).
- **Reason:** The silence limit covers streamed requests only, so it would not help the probe/embed hang `-2` accepted; RPHelper's tracing posture is the operator's environment switch; the provider id may be absent and one id form for every call keeps pairing and replay provider-independent.
- **Lands in:** `backend/app/services/llm/gateway.py` (nothing passed); `backend/app/config.py` unchanged
- **Cites:** `llm-and-streaming.md` § The timeout, § Errors (tracing), § Ids in frames; refines `DEC-arch-llm-client-library-2` and `-5`
