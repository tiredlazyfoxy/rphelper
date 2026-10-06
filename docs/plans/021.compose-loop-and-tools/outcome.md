# Feature 021 — Compose loop and tools · outcome

Intended changes to `docs/architecture/` once this feature ships, for the architect to apply
at finalization. Grouped by target file. D-n refers to this folder's `context.md`; U1–U4 are
the user-confirmed decisions it records.

## `docs/architecture/llm-and-streaming.md`

| Section | Intended change | Reason |
|---|---|---|
| "One OpenAI-compatible client" — "As built … deliberately absent" | Replace "`chat_stream` is not stubbed" with the as-built `chat_stream`: async iterator of provider deltas (content, reasoning from `reasoning_content` / `reasoning`, per-chunk tool-call fragments — unaccumulated), httpx streaming POST to `…/v1/chat/completions` with `stream: true`, `tools` only when non-empty, no `tool_choice`; `[DONE]` or a clean end of body ends it; non-2xx, transport error, timeout or an unparseable `data:` line → `llm_unreachable`; closing the iterator unwinds the httpx stream (the upstream cancel on a stop). Record that plan 006's two absence tests were deleted by 021 `003` (D10) | As built |
| "One OpenAI-compatible client" | Record chat-client construction: `llm_registry.open_chat_client` re-reads `api_key_ref`, resolves it at call time and builds the client through an injectable chat-client factory (D14) | New call site of the secret-pointer pattern |
| "One OpenAI-compatible client" — timeout | `_TBD: the streaming call reuses llm_request_timeout_seconds (30 s per httpx phase, incl. read between chunks); whether a slow first token on a large context needs a longer read timeout is unmeasured_` (D10) | Unknown, flagged |
| "The SSE event protocol" — `accepted` row | Amend "emitted **once, before the first `token`**" to: emitted once, before the first `token`, **when the compose carried text**; a textless compose (the retry) emits no `accepted` (D2, U1) | Wording adjustment requested by the user decision |
| "The SSE event protocol" / new subsection "Thinking" | Record the `<think>` convention: provider reasoning deltas stream as ordinary `token` frames wrapped in `<think>` … `</think>` (open before the first reasoning delta of a run, close when content begins or the round's provider stream ends); inline `<think>` content passes through; no new frame type; a stop keeps reasoning in the partial row (D4, U2) | New convention |
| "Ordering guarantee" | Add the retry: a textless `POST …/zone/compose` re-runs generation over the zone as it stands with no insert, refused with `zone_empty` (JSON, before any stream) when the zone has no non-tool row; the model is re-read at use, so changing the session's model before retrying takes effect (D2) | US-044.AC-3 mechanism; the control itself is 022's |
| "Ordering guarantee" | Record that the use-time model check runs **inside** the stream after `accepted`, so `no_model_enabled` / `model_not_chosen` / `model_not_enabled` / `secret_ref_missing` arrive as `error` frames with the text already safe (D3) | As built |
| "The tool-calling loop" | Record the seam (D6): package `app/services/tools/`; `ToolScope(user_id, session_id, character_id, setup_id)` built only by the seam from an owner-scoped session read; `ToolOutcome(content, summary)`; `Tool` protocol `name` + async `run(scope, connection, arguments) -> ToolOutcome`, any `Exception` = failure; dispatch on its own short-lived connection; failure (not offered, unknown, non-object arguments, `run` raising) → `tool_fail` `tool_failed` + the fixed model message; a cancellation propagates and writes nothing. **This is the signature 026 / 027 / 028 bind to** | Closes 021's brief question |
| "The tool-calling loop" — availability rule | Amend: offered = resolved switch on **∩ an implementation registered** under that name (U3, D5); declarations are the seam's (`tools/definitions.py`), not the implementation's; production registry empty after 021; offered order `memo_search`, `session_search`, `web_search`; tools reach the model only via the API `tools` parameter (confirms 020 D2) | As built |
| "The tool-calling loop" — loop detail | Record D11: tool-call fragments accumulated by index; per round the assistant message carries content without reasoning plus the calls in index order; one assistant row per exchange holding all streamed token text across rounds (think tags included); fallback call id `call_<n>`; the provider iterator is always closed with the source. No cap, as already stated | As built |
| "Context assembly" — "The message list …" | Replace 020's "tool rows skipped" with D9's replay: each zone tool row → an assistant message with empty content and that one call, then a `tool` message (payload content, or the failed literal); unreplayable rows skipped; current-zone assistant rows are `<think>`-stripped; settled rows never are (D4, D9) | Supersedes 020 D3 |
| "`web_search` — seam now, adapter deferred" | Record that the declaration (with the three justified uses in its description) shipped in `tools/definitions.py` with no implementation registered (D5) | As built |
| "Named divergences" | No change. Note that 021 binds US-133.AC-1 nowhere: a stop during `run` propagates a cancellation and writes no tool row; the exchange ends | Status note |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| Layout — `services/` | Add `compose.py` (the compose source `compose_stream` and the handler-side `begin_compose`) and the package `tools/` (`definitions.py` — the three declarations; `seam.py` — scope, outcome, protocol, registry, offered tools, dispatch) (D6, D15) | New modules |
| Layout — `services/llm/` | `chat.py` now also holds `ToolCall`, the four-role `ChatMessage` with `tool_calls` / `tool_call_id`, `to_wire_message`, and the `<think>` tag literals + `strip_think`; `client.py` holds `chat_stream` and its delta values (D4, D10) | As built |
| "Routers versus services" | Record the service-import exceptions: `compose.py` (configuration, context, messages, llm_registry, tools, llm.*) and `tools/seam.py` (sessions, messages, configuration types). Neither opens a transaction of its own; each called operation owns its own (D15) | Same shape as 020 D9 |
| "The streaming route" | Record as built: the handler calls `begin_compose` (text → `append_message`, committed; textless → ownership + `zone_empty` check), then returns `sse_response(request, compose_stream(...), own_connection_persister(...))`; the chat-client factory and the tool registry are two overridable FastAPI dependencies in `routers/stream.py`; the request body is `{text?}` — absent/null = retry, blank = 422 (D1, D2, D14) | As built |
| "Settle and re-open" — settle step 1 | Amend: the head is the **last non-tool zone row**; tool rows are buried with the group as scaffolding; a zone holding only tool rows is `zone_empty` (D8). Flag for review | Tool-row invariant |
| "Settle and re-open" — settle step 2 | Add: when the head's role is `assistant`, `<think>` blocks are stripped (`chat.strip_think`) **before** `(( ))` classification; user heads are never think-stripped. Note that a head whose stripped text is empty still settles (no refusal invented) — 022 may want to surface it (D4) | New settle rule (R12-adjacent) |
| "The stream routes" — `PATCH /api/messages/{message_id}` bullet | Add: a `role='tool'` row is refused with `message_not_editable` (its text summarises its payload) (D8). Flag: `message_not_editable` now also means "tool row" | Widened meaning |
| "The error model" — table and "The per-code status record" | `tool_failed`: introduced by plan 021 as `ToolFailedError`, **502** — a dependency's failure, like `llm_unreachable`; never an HTTP response in 021, only the `tool_fail` frame's code; `detail` carries the tool name (D13). Flag for review | Status recorded where the code is born |

## `docs/architecture/domain-rules.md`

| Section | Intended change | Reason |
|---|---|---|
| R9 | Name the enforcement point: `ToolScope`, built only by `tools/seam.py` from an owner-scoped session read, is the one place a tool's scope comes from; tool arguments never carry ids (D6) | Isolation lives once, in the seam |
| R10 | Add the retry mechanism (textless compose, no re-insert) and that model-resolution failures arrive after the text is committed (D2, D3) | As built |
| R11 | Add: settle's "last message in the zone" excludes `role='tool'` rows; a tool-only zone counts as empty (D8). Flag for review | Tool-row invariant |
| R12 (adjacent) | Record the parallel `<think>` rule: reasoning is stripped from an **assistant** head at settle and from current-zone assistant replies in context; user text and settled text are never think-stripped; the record and copy-out never carry reasoning (D4, U2) | New convention |

## `docs/architecture/data-model.md`

| Section | Intended change | Reason |
|---|---|---|
| `messages` — tool rows | Record the as-built writer and shape: one `role='tool'` current-zone row per completed call; `text` = summary or `The tool failed.`; `tool_name` as the model gave it; `tool_payload` JSON `{call_id, arguments (raw string), status ok\|failed, content \| code}`; a call stopped mid-run writes none; `tool_name` / `tool_payload` are not on the wire in 021 (D7) | As built |
| `messages` — assistant text | Note that a current-zone assistant row may contain `<think>` … `</think>` blocks (persisted reasoning); they are stripped at settle (D4) | Data-shape note |

## `docs/architecture/workspace-shell.md` / `ui-conventions.md`

| Section | Intended change | Reason |
|---|---|---|
| `workspace-shell.md` "The ruler and the current zone" | Record that Send on *my turn* now composes (021 `007`); the persistent retry is a **textless compose** whose control is `022`'s; `022` renders `<think>` blocks as the collapsible thinking block (US-114) (D2, D4, D12) | Ownership as built |
| `ui-conventions.md` "Async feedback" | Note that `tool_failed` is never a notification in 021 (`tool_fail` is non-terminal and 019's effect ignores tool frames); the four compose failure codes reach `notifyFailure` with the server message (D12) | As built |

## `docs/architecture/search-and-retrieval.md`

| Section | Intended change | Reason |
|---|---|---|
| "The narrow port" | Note that `memo_search` / `session_search` implementations (026 / 027) build their `SearchScope` from the seam's `ToolScope`, so the owner (and character) predicate comes from the seam, never from tool arguments (D6) | Ties the port to the seam |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Paths | Add `services/compose.py`, `services/tools/` (`definitions.py`, `seam.py`) | Dense index |
| Error codes | `tool_failed` → 502 (plan 021) | Dense index |
| Invariants | `<think>` stripped at settle (assistant heads) and in context (zone assistant rows); settle head = last non-tool row | Dense index |

## Forward notes (not architecture changes; for the owning plans)

- **022:**
  - Render `<think>` … `</think>` in assistant text as the collapsible thinking block, and
    tool rows (and live `tool_*` frames) as collapsible tool blocks (US-114).
  - The in-stream retry control: call `composeZone` with **no text** at the failed exchange;
    show it from persisted zone state (it survives reload) (D2).
  - Hide the edit control on tool rows — `PATCH` now answers `message_not_editable` (D8).
  - Decide `showsDiscard` / `canSettle` for a zone holding only tool rows (backend treats it as
    empty) (D8).
  - A settled head that was only a think block settles as empty text; consider surfacing it.
- **026 / 027 / 028:** implement `Tool` (`name`, async `run(scope, connection, arguments) ->
  ToolOutcome`) and register it under the declared name; build any `SearchScope` from
  `ToolScope`; never read ids from arguments; leave no transaction open; return a `summary`
  that never contains raw content; raise on failure (the seam maps it to `tool_failed`); do
  not change the declaration from the implementation side — a schema change is an edit to
  `tools/definitions.py`.
- **/product-spec:**
  - US-133.AC-1 remains a named divergence (unchanged).
  - The textless-compose retry, the `<think>` strip from the record, and tool rows being
    non-editable (US-115.AC-1 says "whoever wrote it") are plan-time decisions with no
    criterion behind them; raised so the product layer can record them or rule otherwise.

## Observations

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B1 (the backend spine — `session-stream.md`, `transfer.md`, `backend-structure.md`, `data-model.md`, `domain-rules.md`), B2 (the LLM/search/operations layer — `llm-and-streaming.md`, `search-and-retrieval.md`, `deployment.md`, `admin-surfaces.md`, `overview.md`) and B3 (the frontend layer — `workspace-shell.md`, `frontend-structure.md`, `ui-conventions.md`, `forms-and-lists.md`).
Rejected items: Its "Named divergences" status note is rejected (as 019's); its "tool columns are not on the wire" (D7) is superseded by 022 D3's twelve-key `MessageResponse`, and its "production registry empty" by the final three-tool state.
Notes: All three items flagged for review are accepted — settle's head is the last non-tool zone row, `message_not_editable` now also means a tool row, and `tool_failed` is 502. The R11 change is recorded as deliberate so it is not read as a slip, and its three `/product-spec` flags are discharged by `US-044.AC-5`, `US-146` and `US-115.AC-1`'s `Constraint:`.
