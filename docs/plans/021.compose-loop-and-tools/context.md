# Feature 021 — Compose loop and tools · feature-wide context

## What this feature is

The assistant actually answers. `POST /api/sessions/{id}/zone/compose` persists the
roleplayer's text **before** any model call (R10), sends the assembled context (020) to the
session's use-time-validated model (017) through the one OpenAI-compatible client, and streams
the candidate back through 019's harness into the current zone. The loop may call tools any
number of times (no cap); a failed tool is a tool *result* and the exchange carries on (R9).
The three tools are **declarations only**: the dispatch seam ships with an empty registry, so
in production no tool is offered yet. `026` / `027` / `028` register implementations.

The agreed boundary is `brief.md` in this folder (Definition and Scope In/Out, not widened).
Its open question — what the seam hands a tool and what it accepts back — is closed by **D6**.

Out, and kept out: every tool implementation (`026`–`028`); the zone's rendering of thinking
and tool blocks, the in-stream retry control and live token rendering (`022`); translation
(`023`).

## Product ids

Delivers **FEAT-010** via **UC-034**, **US-037**, **US-044**; exercises UC-032 (exception
flow), R9's failed-tool path (UC-051 / UC-053 exception flows, cited, tools themselves are
026/027).

| Criterion | Where it lands |
|---|---|
| US-037.AC-1 (candidate in the RP language) | `005` (the assembled system prompt is what is sent, `[test]`); `005` / `006` live check `[manual/live]` — the instruction text itself is 020's |
| US-044.AC-1 (nothing typed lost, incl. before the first token) | `006` (route: persist-before-call, error before / after first token) |
| US-044.AC-2 / AC-4 (failure visible, reason stated, transient) | `006` (typed `error` frame); `007` (`notifyFailure` with the server reason) |
| US-044.AC-3 (retry possible) | `006` (textless compose = retry, no duplicate row); the in-stream control is `022`'s |
| UC-034 (candidate lands in the current zone) | `005`, `006` |

**US-133.AC-1 is a named divergence and is NOT bound** (`llm-and-streaming.md` "Named
divergences"): a stop during a tool call **ends** the exchange. `004` tests only that a stop
mid-tool writes no tool row and propagates.

## Build prerequisites

001..014 are built. **015..020 are planned, not built, and are built before 021.** 021 binds
to their declared interfaces, cited by plan / step / decision id, never re-specified.

| Upstream (planned) | What 021 binds to | Needed by |
|---|---|---|
| 019 `001` | `services/llm/frames.py` frame value types (accepted, token, tool start, tool result, tool fail, error, done) + encoder; `append_assistant_message` (019 D8) and its shared private insert in `services/messages.py` | `001`, `004`, `005` |
| 019 `002` | `sse_response(request, source, on_partial)`, `own_connection_persister(engine, generator, user_id, session_id)`; the persist rule (019 D4): **the harness, never the source, writes the partial row on every non-`done` ending**; a source raising a `DomainError` becomes that `error` frame | `005`, `006` |
| 019 `004` / `005` | frontend `composeZone` (body `{text}`, 019 forward note: **binding point**), `composeMessage`, `stopCompose`, `isStreaming`, the Stop slot | `007` |
| 020 `001` / `002` | `services/llm/chat.py` (`ChatRole`, `ChatMessage`); `services/context.py` (`to_chat_messages`, `assemble_context` → `AssembledContext(system_prompt, messages)`); prompt format contract (020 context "The prompt format") | `001`, `002`, `005` |
| 017 `001` / `003` | `NoModelEnabledError` (`no_model_enabled`, 409), `ModelNotChosenError` (`model_not_chosen`, 409); `get_session_configuration` (`tool_memo_search` / `tool_session_search` / `tool_web_search` as resolved settings whose `value` is a bool); `resolve_model_for_use(conn, user_id, session_id) -> EnabledChatModel` | `004`, `005`, `006` |

Built (committed) code 021 also relies on: `services/llm/client.py` (`LlmClient`),
`services/llm_registry.py` (`EnabledChatModel(server, model_name)`, `LlmServer.base_url`,
`probe_server` pattern), `app/secrets.py` `resolve_secret`, `services/sessions.py`
`get_session`, `services/settle.py`, `services/parens.py`, `routers/stream.py`, `app/errors.py`.

## Architecture this binds to

- `llm-and-streaming.md`: "One OpenAI-compatible client"; "The model registry and use-time
  validation" (resolve → validate → call); "The SSE event protocol" (seven events, ids as
  strings, `call_id` opaque, `tool_result` summary only, `tool_fail` not terminal); "Four ways
  a stream ends"; "Ordering guarantee"; "Stopping model work in flight" (consequence 4:
  stopping mid-tool ends the exchange); "The tool-calling loop" (no cap, disabled tool not
  offered, scoped reads); "`web_search` — seam now, adapter deferred".
- `backend-structure.md`: "The stream routes", "The streaming route" (rules 1–3), "Settle and
  re-open", "The `(( ))` seam", "The error model" + "The per-code status record".
- `domain-rules.md`: **R4**, **R5**, **R9**, **R10**, **R11**, **R12**.
- `data-model.md` `messages` (`role` incl. `'tool'`, `tool_name` / `tool_payload`, the three
  states).
- `search-and-retrieval.md` "The narrow port" (026/027 build a `SearchScope` from D6's
  `ToolScope`).
- `ui-conventions.md` "Async feedback" and "The tension with US-044.AC-3"; `workspace-shell.md`
  "The ruler and the current zone".

Cited, never copied.

## Files this feature touches

```
backend/
  app/errors.py                       # + ToolFailedError                               (001)
  app/services/messages.py            # StreamMessage tool fields; append_tool_message;
                                      #   edit refuses tool rows                         (001)
  app/services/settle.py              # head = last non-tool row; <think> strip          (001)
  app/services/llm/chat.py            # <think> convention (001); tool-capable chat
                                      #   values + wire form (002)
  app/services/context.py             # tool-row replay; <think> strip on zone replies   (002)
  app/services/llm/client.py          # + chat_stream and its delta values               (003)
  app/services/llm_registry.py        # chat-client protocol/factory + open_chat_client  (003)
  app/services/tools/__init__.py      # NEW package                                      (004)
  app/services/tools/definitions.py   # NEW — the three declarations                     (004)
  app/services/tools/seam.py          # NEW — ToolScope, ToolOutcome, Tool, registry,
                                      #   offered tools, dispatch                        (004)
  app/services/compose.py             # NEW — the compose source (005); begin_compose (006)
  app/routers/stream.py               # + POST …/zone/compose, two dependencies         (006)
  app/models/stream.py                # + compose request model                          (006)
frontend/
  src/app/streamApi.ts                # composeZone: text optional                       (007)
  src/app/streamState.ts              # sendComposer's my-turn branch → composeMessage   (007)
```

Test files are listed per step. Existing test files amended by this feature (each named in its
step's Test files): `tests/test_llm_client.py` (`003`), `tests/test_context_render.py` and
`tests/test_context_assembly.py` (`002`), `tests/test_stream_router.py` (`006`, conditional),
`frontend/tests/app/streamMutations.test.ts` and `frontend/tests/app/Composer.test.tsx`
(`007`, conditional).

**Not touched. A step that touches one is out of scope:** `db/schema.py` (no schema change:
`tool_name` / `tool_payload` exist, `role` has no CHECK), `db/engine.py`, `main.py`,
`dependencies.py`, `secrets.py`, `config.py`, `services/parens.py`, `services/sessions.py`,
`services/configuration.py`, `services/llm/frames.py` (019's), every other router and service,
`tests/conftest.py`; frontend `Composer.tsx`, `ZoneList.tsx`, `SessionStream.tsx`,
`src/shared/*` (`notifyFailure`, `sse.ts`, `api.ts`), every stylesheet. No new dependency on
either side.

## Cross-cutting constraints every step holds

- **R10 ordering.** The roleplayer's text is committed on the handler connection before the
  stream opens and before any model call. Nothing in 021 deletes or rewrites a user row.
- **019 D4 binds the source.** The source writes the assistant row only on success, via
  `append_assistant_message`, **before** yielding `done`. On every failure path it writes
  **nothing** and simply raises; the harness persists the partial text and emits the `error`
  frame.
- **Connections.** The source and the seam never touch the handler's request-scoped
  connection. Each opens short-lived connections from the engine (same reasoning as 019 D7).
  No connection is held across a network await to the provider.
- **No iteration cap, no round counter** anywhere (FEAT-010; `llm-and-streaming.md`).
- **Tools never receive ids from the model.** Isolation (R5, FEAT-019, R9) lives once, in the
  seam's `ToolScope` (D6).
- **Logs carry ids, codes, tool names and exception class names — never text** (no message
  text, no arguments, no tool content, no provider body).
- **`services/llm/client.py` imports no `fastapi`, no `app.secrets`, no `app.db`** (existing
  structural tests). Services import no `fastapi`.
- **Backend:** fully typed; `mypy app` and `ruff check .` stay green. **Frontend:** TypeScript
  only; `npm run typecheck` stays green; pure data contracts (free-function effects,
  `runInAction`, never reject); no success notification.

## Decisions — settled, with their reasoning

U1–U4 are the user-confirmed decisions from the briefing; the rest are planner decisions.

### D1 — The route commits the text, then streams (R10)

`POST /api/sessions/{id}/zone/compose` (in `routers/stream.py`, the one streaming route). In
order, on the handler's connection: (1) with `text`: `append_message` (012's write, commits in
its own transaction); ownership failures and a blank text are plain JSON errors before any
stream; (2) return `sse_response(request, source, own_connection_persister(get_engine(settings),
generator, user.id, session_id))`. The handler-side part lives in a service function
(`begin_compose`, `006`) so the router stays thin.

### D2 — A textless compose is the retry (U1)

Same route, body `{text}` with `text` **absent or null**: no insert, **no `accepted` frame**,
generation over the zone exactly as it stands. Before the stream the handler checks ownership
and refuses a zone with no non-tool row as `zone_empty` (409 JSON). A `text` that is present
but blank is refused exactly as 012's append refuses it (422). The model is re-read at use time
on every compose (R4 step 1), so changing the session's model before retrying takes effect;
context and text are otherwise identical. Retry availability is derivable from persisted zone
rows, so it survives a reload. The in-stream retry control is `022`'s; 021 ships the backend
semantics and `composeZone`'s optional text (`007`). **Wording adjustment for /architect:**
`accepted` is emitted "once, before the first `token`" **only when text was sent**.

### D3 — Model resolution happens inside the source; its failures are `error` frames

The source calls `resolve_model_for_use` (017) on its own connection after `accepted`. The text
is already safe, so `no_model_enabled` / `model_not_chosen` / `model_not_enabled` (and
`secret_ref_missing`, `llm_unreachable`) arrive as typed `error` frames, and the roleplayer
can fix the model and retry (D2). Resolving before the stream would turn them into JSON errors
with the text already committed and no `accepted` id to show for it.

### D4 — Thinking is streamed as `<think>`-wrapped tokens (U2)

- **Tags:** exactly `<think>` and `</think>` (lowercase, case-sensitive). Both literals live in
  `services/llm/chat.py`, the one home of the convention (`001`).
- **Stream (`005`).** A provider reasoning delta (`reasoning_content` or `reasoning`) becomes an
  ordinary `token` frame. Before the first reasoning delta of a run, a `token` `<think>` is
  emitted; the run closes with a `token` `</think>` when content begins **or** when that
  round's provider stream ends. No new frame type. Content that already carries inline
  `<think>` passes through untouched (no added tags). The tags are token text, so the
  success-path row and the harness's partial row both carry them.
- **Strip rule** (one pure function in `chat.py`): a block is `<think>` through the nearest
  following `</think>` inclusive; an unterminated `<think>` runs to the end of the text; blocks
  are removed left to right; **if at least one block was removed** the result is trimmed of
  leading and trailing whitespace, otherwise the text is returned byte-for-byte unchanged. A
  stray `</think>` with no opener is left alone.
- **Applied in exactly two places, to assistant rows only:** at **settle**, on the head row
  when its role is `assistant`, **before** 012's `(( ))` classification (`001`); and in
  **context**, when a current-zone `assistant` row is mapped (`002`). User rows are never
  stripped (the convention is model output; R12's spirit: the roleplayer's text is taken
  literally). Settled rows are never stripped in context (already stripped at settle; a later
  edit is taken literally). Record and copy-out therefore never carry reasoning.
- **Worked examples** (tests bind to these):

| Input | Output |
|---|---|
| `<think>plan</think>\n\nHello` | `Hello` |
| `Hello` | `Hello` |
| `  Hello  ` | `  Hello  ` (no block: unchanged) |
| `<think>a</think>One<think>b</think> two` | `One two` |
| `Start<think>never closed` | `Start` |
| `<think>only</think>` | `` (empty) |
| `a </think> b` | `a </think> b` |
| `<think>x\ny</think>\n((ooc))` | `((ooc))` |

Collapsible rendering is `022`'s.

### D5 — Tools offered = config-enabled ∩ registered (U3)

The seam owns the three **declarations** (`definitions.py`). A tool is offered to the model iff
its resolved switch (017) is on **and** an implementation is registered under its name. The
production registry is **empty** in 021, so no `tools` parameter is sent in production; the loop
is proven with fake tools in tests. Offered order is fixed: `memo_search`, `session_search`,
`web_search`. Enabled tools reach the model only through the API `tools` parameter, never the
prompt (020 D2). A registered name outside the three is never offered (R9: closed at three).
Implementations cannot change what the model sees: the declaration is the seam's.

### D6 — The seam (closes the brief's open question; `026`–`028` bind to it)

Package `app/services/tools/`:

- **`ToolScope`** (frozen): `user_id`, `session_id`, `character_id`, `setup_id` (or none).
  Built **only** by the seam, from an owner-scoped session read (`sessions.get_session`;
  missing or foreign → `SessionNotFoundError`). Tools never receive an id from the model;
  arguments carry only query parameters. This is where R5 / FEAT-019 / R9 isolation lives,
  once.
- **`ToolOutcome`** (frozen): `content` (the string sent to the model as the tool message) and
  `summary` (a short string for the `tool_result` frame and the persisted row; never the raw
  content).
- **`Tool`** protocol: a `name` and an async `run(scope, connection, arguments)` returning a
  `ToolOutcome`. `arguments` is the parsed JSON object (a mapping). **Any `Exception` raised by
  `run` is a failure.** `run` must leave no transaction open on the connection it is given.
- **Registry:** a mapping name → `Tool`, empty in production, injectable (tests, `006`'s
  dependency).
- **Dispatch** of one provider tool call (call id, name, raw arguments string): the caller
  emits the `tool_start` frame (args = the parsed object, or `{}` when unparseable or not an
  object); dispatch then resolves the outcome:
  - name not among the **offered** tools, arguments not a JSON object, or `run` raising an
    `Exception` → **failure**: frame `tool_fail(tool, call_id, "tool_failed")`, model message
    = the failed literal (below), row status `failed`. `run` is never called for the first two.
  - success → frame `tool_result(tool, call_id, summary)`, model message = `content`, row
    status `ok`.
  - The seam opens its **own short-lived connection** from the engine for `run` and closes it
    whatever happens.
  - A cancellation (`CancelledError` / `GeneratorExit`, i.e. a stop) is **not** a failure: it
    propagates, and no row is written.
- A failed tool never ends the exchange (R9).

### D7 — Persisted tool rows

One `role='tool'` current-zone row per **completed** call (ok or failed), written by the seam
through `messages.append_tool_message` on its own short-lived connection, after the outcome is
known and before dispatch returns. A call interrupted by a stop writes no row. A failure to
write the row is logged (session id, tool name, exception class) and swallowed: a transcript
write must not end the exchange (R9's posture; 019 D7's). Columns: `kind` NULL, `text` = the
summary (ok) or the failed-row literal (failed), `tool_name` = the called name as given by the
model, `tool_payload` = compact JSON:

| status | `tool_payload` |
|---|---|
| ok | `{"call_id": <string>, "arguments": <raw arguments string, verbatim>, "status": "ok", "content": <tool content>}` |
| failed | `{"call_id": <string>, "arguments": <raw arguments string, verbatim>, "status": "failed", "code": "tool_failed"}` |

`MessageResponse` (wire) is unchanged: `tool_name` / `tool_payload` never leave the backend in
021 (022 decides what the zone reads).

### D8 — Tool-row invariants, minimal (flagged for /architect)

- **Settle's head is the last non-tool zone row**; every other zone row, tool rows included,
  is buried under it. A zone holding **only tool rows** counts as empty: settle raises
  `zone_empty`, and a textless compose is refused the same way (D2).
- **`PATCH` of a tool row → `message_not_editable`** (409): its text is a summary of its
  payload, and editing one half would desync them.
- Re-open is unchanged (a buried tool row comes back with its group).
- Frontend treatment of a tool-only zone (`showsDiscard`, `canSettle`) and hiding the edit
  control on tool rows are **forward notes to 022** — unreachable in production while the
  registry is empty.

### D9 — Tool-row replay into context

020 skipped `role='tool'` rows (020 D3); 021 replays them. **Each zone tool row, at its id
position, becomes two chat messages:** an `assistant` message with empty content carrying
exactly that one call (`call_id`, `tool_name`, the raw `arguments`), then a `tool` message
with that `call_id` whose content is the payload's `content` (ok) or the failed literal
(failed). A tool row whose payload is unparseable or lacks `call_id` / `arguments` / `status`,
or whose `tool_name` is null, is skipped. Buried tool rows never reach context (R11, the
views). One pair per row rather than one grouped assistant message: unambiguous, valid
OpenAI form, and needs no notion of "round" that the rows do not store.

### D10 — `chat_stream` as built

`LlmClient.chat_stream(model, messages, tools)` is an async iterator of **provider deltas**
(content, reasoning, tool-call fragments, each passed through per chunk — accumulation is the
source's), over `httpx` streaming `POST <base>/v1/chat/completions` with `stream: true`. `tools`
is in the body only when non-empty; no `tool_choice`. It parses SSE `data:` lines, stops at
`[DONE]`, treats a clean end of body as the end, and turns a non-2xx status, a transport error,
a timeout or an unparseable data line into `LlmUnreachableError`. Closing the iterator unwinds
the httpx stream, which is what cancels the upstream request on a stop (US-132.AC-2, 019 D6).
Timeout: `Settings.llm_request_timeout_seconds` as for `embed` (`_TBD: whether a 30 s read
timeout suits a slow first token on a large context is unmeasured; flagged in outcome.md`).

### D11 — The loop

One exchange = repeated rounds of `chat_stream`. Per round: content → `token`; reasoning →
D4; tool-call fragments are accumulated **by index** (id and name from the first fragment that
carries them, argument fragments concatenated in arrival order). When a round ends with
accumulated calls, the source appends an `assistant` message (content = that round's content
text **without** reasoning, `tool_calls` = the calls in index order) to the in-memory
conversation, then for each call in index order emits `tool_start`, awaits dispatch, emits its
frame and appends its `tool` message, and re-enters. A round with no calls is the final answer:
the source writes **one** assistant row holding **all** token text streamed across every round
(think tags included) and yields `done(message_id)`. A call whose provider id never arrives gets
the fallback id `call_<n>`, `n` counting calls within the exchange from 1. The provider stream
is always closed when the source is closed (stop), so the upstream request is cancelled.

### D12 — Frontend, minimal (U4)

Send on *my turn* goes through 019's `composeMessage` (via `sendComposer`'s my-turn branch);
partner filing is unchanged. A failed compose's reason reaches the roleplayer through 019's
existing `notifyFailure` path (server message; covers `llm_unreachable`, `no_model_enabled`,
`model_not_chosen`, `model_not_enabled`); the zone is re-read after every outcome; nothing is
optimistic. `composeZone`'s text becomes optional (absent → body `{}`). Live token rendering,
tool / thinking blocks and the in-stream retry control stay `022`'s.

### D13 — `tool_failed` is a `DomainError` answering 502 (planner; flag)

`ToolFailedError` (`code` `tool_failed`, `detail` carries the tool name) gives the code one
source string and gives `026`–`028` a typed failure to raise. In 021 it is **never** an HTTP
response — it only names the `tool_fail` frame's code. 502 because, like `llm_unreachable`, a
tool's failure is a dependency's (search index, embedding model, web provider), not the
caller's. Recorded for the per-code status record.

### D14 — Chat-client construction and injection

`llm_registry.py` gains a chat-capable client protocol and factory type (separate from the
existing probe/embed `LlmClientLike`, so existing fakes stay valid) and one helper,
`open_chat_client`, that re-reads the server's `api_key_ref`, resolves it with `resolve_secret`
(missing variable → `secret_ref_missing`) and calls the factory with the base URL, the key and
the timeout — the `probe_server` pattern. `routers/stream.py` exposes the factory and the tool
registry as two FastAPI dependencies so tests override them with `dependency_overrides`.

### D15 — Service-import exceptions, taken deliberately

`services/compose.py` composes reads and writes from `configuration`, `context`, `messages`,
`llm_registry`, `tools`, `llm.*`; `services/tools/seam.py` imports `sessions` and `messages`.
The no-import rule's reason (a service operation owns its transaction, 010 D6) holds: each
called operation owns its own transaction on a connection the caller opened, and neither
module opens a transaction itself. Same shape as 020 D9.

### D16 — Seven steps

| Step | Subject | Est. source LoC | Depends on |
|------|---------|-----------------|------------|
| 001 | `ToolFailedError`; tool-row write + fields; edit guard; settle head rule; `<think>` strip at settle | ~95 | 019 `001`, 020 `001` built |
| 002 | tool-capable chat values + wire form; tool-row replay; `<think>` strip in context | ~85 | 001; 020 `002` built |
| 003 | `chat_stream` + deltas; chat-client protocol, factory, `open_chat_client` | ~125 | 002 |
| 004 | `services/tools/`: declarations, scope, outcome, protocol, registry, offered tools, dispatch | ~155 | 001, 002; 017 `003` built |
| 005 | `services/compose.py`: the compose source (the loop) | ~145 | 002, 003, 004; 019 `002`, 020 `002`, 017 `003` built |
| 006 | `begin_compose`; the route; request model; two dependencies | ~85 | 005 |
| 007 | frontend: `composeZone` optional text; Send → compose | ~20 | 019 `004`/`005` built; `006` for live checks |

`007` is under the 50-line floor and stays separate: it is the only frontend change and cannot
merge with a backend step.

## Test conventions

**Backend** (from `backend/`): pytest, flat `tests/`, names
`test_<behavior>__S021_<SSS>_DoD<n>`; no async plugin — async code is driven with
`asyncio.run(...)` from sync tests, as in `tests/test_llm_client.py`; file-local engine
fixture with `schema.metadata.create_all`, file-local raw-insert helpers (`_insert_user`,
`_insert_character`, `_insert_session`, `_insert_message`, registry rows `llm_servers` +
`models` as in 017's conventions), two users for isolation; `conftest.py` untouched. Provider
fakes: `httpx.MockTransport` through the client's `transport=` seam for `003`; file-local fake
chat clients (scripted rounds of deltas, recording each call's model, messages and tools, and
whether their iterator was closed) and fake tools (recording scope, arguments, connection) for
`004`–`006`. Router tests build `create_app()` with `dependency_overrides` (settings, the chat
client factory, the tool registry) and a logged-in `TestClient`; SSE bodies are split on
`"\n\n"` and each `data:` line JSON-parsed. **Expected values come from this plan** (D4's
table, D7's payload, the literals below, 020's prompt-format markers, 019's frame wire shapes),
never from calling the code under test.

**Frontend** (from `frontend/`): Vitest/jsdom, `tests/` mirrors `src/`, each `it` title ends
`— DoD-N`; `fetch` stubbed per file with `vi.stubGlobal` keyed on exact pathname + method;
streamed bodies as a `Response` over a `ReadableStream` of `Uint8Array` chunks; `notifyFailure`
observed through `vi.mock` of `src/shared/notifyFailure`, asserting the `ApiError` code only;
ids are strings like `"7250000000000000101"`.

## Literals — the contract tests bind to

| Name | Exact value | Used by |
|---|---|---|
| think open / close tags | `<think>` / `</think>` | D4 (`001`, `002`, `005`) |
| failed tool → model message content | `The tool failed. Continue without its result.` | D6, D9 (`002`, `004`, `005`) |
| failed tool row `text` | `The tool failed.` | D7 (`004`) |
| `tool_fail` / payload code | `tool_failed` | D6, D7, D13 |
| tool names, offered order | `memo_search`, `session_search`, `web_search` | D5 |
| fallback call id | `call_<n>`, n from 1 per exchange | D11 (`005`) |

## Vocabulary

| Term | Means here |
|---|---|
| **compose** | one `POST …/zone/compose`; **textless compose** = the retry (D2) |
| **exchange** | everything one compose streams, across all rounds, ending in `done` / `error` / disconnect |
| **round** | one `chat_stream` call within an exchange |
| **delta** | one provider chunk as `chat_stream` yields it (D10) |
| **source** | 005's async generator of frame values that 019's harness drains |
| **declaration** | a tool's name, description and parameter schema, owned by the seam (D5) |
| **offered tools** | declarations whose switch is on and whose name is registered (D5) |
| **dispatch** | resolving one tool call into a frame, a model message and a row (D6, D7) |
| **tool row** | a `role='tool'` current-zone row (D7) |
| **replay** | mapping a tool row back into chat messages for context (D9) |
| **think block** | `<think>` … `</think>` in assistant text (D4) |
