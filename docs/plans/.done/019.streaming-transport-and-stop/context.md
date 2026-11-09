# Feature 019 — Streaming transport and stop · feature-wide context

## What this feature is

This feature builds the pipe the assistant's words travel down, and the brake on it. It is
**transport only**. Nothing is generated, and no route streams yet.

- **Backend.** One module that builds every SSE frame. A **harness** that turns an async
  source of frames into an SSE response, and that persists the partial assistant text
  when the client goes away. The shared service function that appends an assistant row to
  the current zone.
- **Frontend.** The `fetch()`-and-reader SSE consumer, with exactly four terminations. A
  compose call. The streaming state with a compose effect and a stop action on the stream
  store. The Stop control in Send's slot.

The agreed boundary is `brief.md` in this folder. Its Definition and Scope In/Out bound
every step. Its open question, "how the server learns of the abort and what it does with
an in-flight upstream request", is closed by **D6** (detection) and **D4** (what happens
to the text). There is no stop request: the client drops the connection.

## Ownership boundary with 021 / 022 / 023 — read before every step

- **019 mounts no route.** `POST /api/sessions/{id}/zone/compose` is mounted by **021**.
  021 also adds `LlmClient.chat_stream` and owns R10's persist-before-call. 019 leaves
  `routers/stream.py` untouched, and its docstring keeps saying no compose route exists.
- **019 does not add `chat_stream`.** `tests/test_llm_client.py:902` asserts that it is
  absent. That test stays untouched and green.
- **019 does not rewire Send.** Send keeps calling `POST …/zone/messages` (013 D6). 021
  and 022 switch it over. The compose effect therefore has **no UI caller in 019**. It is
  exercised by tests only, and its live end-to-end checks are `[manual/live]` items that
  become runnable once 021 mounts the route.
- **Live rendering of the in-flight assistant text is 022's.** 019 holds the text in
  observable state (D11) and renders nothing from it. Tool frames are parsed and ignored
  (D18).
- **Translation stop (023) and tool-call stop (021) are not built here.**

## Product ids

Delivered (per brief): FEAT-010 — **UC-085**, **US-132**, and US-133, which is **not
bound** (below).

| Criterion | Where it lands |
|---|---|
| US-132.AC-1: partial text remains as a usable, editable candidate | backend: `002`, where the harness persists the partial text as an ordinary current-zone row through `001`'s shared append. Frontend: `005`, which re-reads the zone after a stop. |
| US-132.AC-2: nothing is waiting on the model after a stop | backend: `002`, where the source is closed on disconnect so the upstream request is cancelled. Frontend: `004` (stop aborts) and `005` (streaming state cleared). |
| UC-085: stop any model work in flight | `002`, `003`, `004`, `005`. The generation case only; see the US-133 bullet below. |

**US-133.AC-1 and US-133.AC-2 are NOT bound by any test in 019.** Both are **named
divergences pending `/product-spec` amendment**: see `llm-and-streaming.md` "Named
divergences from `docs/product/`".

- **US-133.AC-1**: a stop during a tool call **ends** the exchange; it does not continue.
  That falls out of **021**'s tool loop dying with the socket. 019's harness closes the
  source on disconnect, and that is all 019 contributes.
- **US-133.AC-2**: "nothing is cached" is best-effort only. The `is_disconnected` check
  before the translation cache write belongs to **023**.

A test written against either AC as worded would be a test that cannot pass. No step
cites them in a DoD.

## Build state this feature binds to

001..013 are built (013 is in the working tree, uncommitted). **014..018 are planned but
not built.** 019 binds to the **current tree**, not to those plans.

- **014** also edits `frontend/src/app/streamState.ts`. Whichever lands second merges by
  hand. 019's additions are new fields, new functions, and one guarded prefix in
  `settleComposer` (`005`).
- **017 step 011** adds a `sendBlockedReason?: string | null` **prop** to `Composer`,
  through `SessionStream`. `canSend` stays untouched (017 context D17). **Rule for the
  merge:** the reason gates **Send only, never Stop**. While streaming, the slot shows
  Stop whatever the reason says. When not streaming, Send renders as 017 specifies.
  Whichever of 017/019 lands second puts its condition on the slot as
  `isStreaming ? Stop : Send(with 017's gating)`, and the merge is trivial.

## Architecture this binds to

- `docs/architecture/llm-and-streaming.md`: "The SSE event protocol" (the seven events,
  ids as decimal strings, `call_id` opaque, `tool_result` summary only, `error` shape,
  `X-Accel-Buffering: no`); "Four ways a stream ends"; "Ordering guarantee"; "Stopping
  model work in flight — UC-085" (no stop route, no registry, the four consequences,
  named divergences).
- `docs/architecture/backend-structure.md`: layout (`services/llm/frames.py` is "SSE frame
  emission"; `services/messages.py` appends to the zone); "The JSON id boundary"; "The
  streaming route" (the three ordering rules; the partial-row write is the same write as
  the success path); "The error model" (`DomainError`, `llm_unreachable`, `detail` ids as
  strings, no user text in logs).
- `docs/architecture/frontend-structure.md`: "State — MobX 6" (four rules), "The API
  client" (every failure is an `ApiError`; an abort is not wrapped; 401 navigates to
  `/login`), "The SSE consumer".
- `docs/architecture/workspace-shell.md`: "The stop control" (Stop replaces Send in the
  same slot; Settle unaffected and **stays enabled during a generation**); "The kind
  switch and settle".
- `docs/architecture/ui-conventions.md`: icon table (`IconPlayerStop` for stop), `IconButton`
  is the only icon-only control, never-optimistic re-load.
- `docs/architecture/domain-rules.md`: **R10** (nothing typed is lost; error clears nothing),
  **R11** (zone = `related_to IS NULL AND settled_at IS NULL`; no discard route).
- Product: `use-cases/FEAT-010.compose-discussion.md` UC-085;
  `stories/FEAT-010.compose-discussion.md` US-132, US-133.

Cited, never copied.

## Files this feature touches

```
backend/
  app/services/llm/frames.py        # NEW — frame value types + encoder (001);
                                    #   harness + own-connection persister (002)
  app/services/messages.py          # + append_assistant_message, shared insert (001)
  app/models/stream.py              # checked; widened only if role excludes
                                    #   "assistant" (001, conditional)
  tests/test_llm_frames.py          # (001)
  tests/test_assistant_append.py    # (001)
  tests/test_llm_sse_harness.py     # (002)
frontend/
  src/shared/api.ts                 # export the shared non-2xx / transport decode (003)
  src/shared/sse.ts                 # NEW — the consumer (003)
  src/app/streamApi.ts              # + compose call (004)
  src/app/streamState.ts            # streaming fields, isStreaming, stop (004);
                                    #   compose effect, settle-mid-stream (005)
  src/app/Composer.tsx              # Stop in Send's slot (004)
  tests/shared/sse.test.ts          # (003)
  tests/app/streamStreaming.test.ts, tests/app/ComposerStop.test.tsx   # (004)
  tests/app/streamCompose.test.ts   # (005)
```

**Not touched. A step that touches one is out of scope:**

- `backend/app/routers/*`, including `stream.py` and `bootstrap.py`;
- `app/services/llm/client.py` and `llm_registry.py`;
- `app/errors.py`, `app/db/*`, `app/main.py`;
- `tests/test_llm_client.py`;
- `frontend/src/app/SessionStream.tsx`, `ZoneList.tsx` and every other component;
- `src/shared/apiError.ts`, `notifyFailure.ts` and `IconButton.tsx`;
- `tests/setup.ts` and every existing test file.

No new dependency on either side. `@tabler/icons-react` already ships `IconPlayerStop`.

## Cross-cutting constraints every step holds

- **Ids are decimal strings on the wire, both directions.** The backend formats a frame
  id with `str(id)` in the encoder (D2), never as a JSON number. The frontend keeps every
  frame id a string, never coerced, compared or sorted (`frontend-structure.md` "Ids are
  strings").
- **Exactly one of `error` or `done` ends every stream the server ends.** A stopped
  stream (client disconnect) gets **nothing**.
- **No stop route, no registry of in-flight work, no new frame for the stop.**
- **Nothing streamed is lost.** On the server, see D4. On the client, an `error` or a
  stop clears nothing from `zone`, `entries` or a changed draft (R10).
- **Logs carry ids, codes and counts, never text** (`deployment.md` redaction rule). That
  covers the persist-failure log line too.
- **Backend:** fully typed; `mypy app` and `ruff check .` are gates. Sync DB access through
  SQLAlchemy Core only.
- **Frontend (pure data contracts):**
  - MobX classes hold observable fields only (one non-observable handle, D12).
  - Derivations and effects are free functions.
  - Effects write inside `runInAction`, never reject, and write nothing once the mount
    signal is aborted.
  - TypeScript only.
  - Every icon-only control goes through `shared/IconButton`.
  - No success notification anywhere.

## Decisions — settled, with their reasoning

### D1 — The harness lives in `services/llm/frames.py` (planner; briefing preference)

The architecture lists `frames.py` as "SSE frame emission". The harness *is* frame
emission plus the stream's end-of-life, so it stays in that module rather than in a new
one. That means no layout change; `outcome.md` only records what the module now holds.
At about 200 LoC across two steps (`001`, `002`) the module stays one subject.

### D2 — Frames are seven value types and one encoder (planner)

`frames.py` defines one immutable value type per event:

- `accepted` (message id, an int)
- `token` (text)
- `tool_start` (tool, call id, args object)
- `tool_result` (tool, call id, summary string)
- `tool_fail` (tool, call id, code)
- `error` (code, message, detail)
- `done` (message id, an int)

It also defines a union of the seven, and **one encoder** that turns any frame into the
wire text `data: <json>\n\n`. A source yields frame **values**, not strings, so the
harness can tell a `token` and a terminal frame apart without re-parsing its own output.
The encoder is the "builder per event" of the briefing: the one site where the int→str
id conversion happens.

Wire JSON:

- **`event` is the first key**, then the event's fields in the order of
  `llm-and-streaming.md`'s example.
- Compact separators (`,` and `:`, no spaces).
- `ensure_ascii` off, so non-ASCII RP text is sent as UTF-8.
- `call_id` is passed through verbatim as a string.
- `tool_result` has **no** field for raw content; a summary string is all it carries.

A constructor turns a `DomainError` into an `error` frame. It takes the **inner** fields
`code`, `message`, `detail`, not `to_wire()`'s `{"error": …}` wrapper. `detail` is
passed through as the raiser built it: per the error model, a raiser already stringifies
ids in `detail`. A missing `detail` becomes `{}`. A `None` message stays JSON `null`,
the same as the JSON error body.

### D3 — Harness interface (planner; 021 binds to it)

Two public functions in `frames.py`:

- **`frame_stream`**: an async generator yielding wire strings. Inputs:
  - the request, used **only** for its async `is_disconnected()`, so any object with that
    method will do;
  - the source, an async iterator of frame values; normally an async generator, which the
    harness `aclose()`s;
  - `on_partial`, a **synchronous** callable taking the accumulated assistant text.
- **`sse_response`**: the same three inputs. Returns a
  `StreamingResponse(media_type="text/event-stream")` over `frame_stream`, with header
  **`X-Accel-Buffering: no`**. No other header is added.

`frame_stream` is public so the disconnect behaviour can be driven in tests without
ASGI (`002.context.md`).

### D4 — The persist rule: everything except `done` keeps the partial text (planner; flag for review)

The harness accumulates the text of every `token` frame it passes through. **Whenever
the stream ends without a `done` frame having passed through**, it calls `on_partial`
with the accumulated text, **unless that text is empty or whitespace only**. In that case
no row is written, and an empty zone after a stop is correct (`llm-and-streaming.md`
consequence 4). "Ends without a `done`" covers four endings:

| Ending | What the harness does, in order |
|---|---|
| client disconnect: poll, cancellation or generator close | persist the partial text, `aclose()` the source, emit **nothing** |
| source raises a `DomainError` | persist the partial text, emit that error as an `error` frame, end |
| source raises any other exception | persist the partial text, emit an `error` frame `llm_unreachable` (D5), end |
| source exhausts with no terminal frame | persist the partial text, emit an `error` frame `llm_unreachable` (D5), end |
| source yields `error` itself | pass it through, then persist the partial text, then end |
| source yields `done` | pass it through, persist **nothing**, close the source, end |

- **Persist before the error frame**, so a client that re-reads the zone on `error` sees
  the row.
- When the source yields its own `error`, the frame is already in hand, and the harness
  persists right after emitting it, before it ends the stream.
- **The success path's write belongs to the source, not the harness.** On success, 021's
  source writes the assistant row through `append_assistant_message` (D8) **before**
  yielding `done`, because `done` carries that row's id.
- **Reasoning.** `llm-and-streaming.md` consequence 1 extends R10 to the assistant's side
  for a stop. The same reasoning applies to a server-side failure after some tokens: the
  roleplayer's next action should never be retyping text the system already had. One rule
  ("no `done` ⇒ keep what streamed") is also simpler than distinguishing errors from
  stops, and the server cannot tell the silent cases apart anyway.
- **021 binds to this.** Its source must not write the partial row itself on any failure
  path.

The harness emits nothing after a terminal frame. Anything the source would yield after
`error`/`done` is never pulled.

### D5 — A non-domain exception and a terminal-less exhaustion both end as `llm_unreachable` (planner; resolves the briefing's open point)

The architecture says every server-ended stream ends in exactly one of `error` or `done`.
A source that raises something that is not a `DomainError`, or that finishes without a
terminal frame, is still a server-ended stream, so it gets an `error` frame. The code is
**`llm_unreachable`**: the client's own fallback for a silent end is the same code, and
it means "the reply did not complete". Fixed messages:

- **"The reply could not be completed."** for an exception;
- **"The reply ended before it was complete."** for exhaustion.

Both have `detail` `{}`. A non-domain exception is logged with its class name only, never
the message, which may embed provider text. This keeps the termination table intact:
the server never ends a stream silently, and silence on the wire always means the
connection itself went away.

### D6 — Disconnect detection: one `finally`, plus a poll as the backstop (planner; closes the brief's open question)

Depending on the Starlette/ASGI version, a disconnect reaches the body generator in one
of three ways: task cancellation (`CancelledError`), the generator being closed
(`GeneratorExit`/`aclose`), or only through `request.is_disconnected()`. The harness
handles all three on **one path**:

- Before writing each frame, it awaits `request.is_disconnected()`. If true, it stops
  iterating.
- A `finally` keyed on **"no terminal frame was emitted"** runs the persist rule (D4) and
  closes the source.
- The persist is **synchronous** (D7), so it needs no shielding. The source's `aclose()`
  is awaited under `asyncio.shield` and any exception from it is suppressed, so a
  cancellation in progress cannot skip it and a broken source cannot mask the unwind.
- A `CancelledError` or `GeneratorExit` is re-raised after cleanup, never swallowed.

So a stop, a network drop and a closed tab take the same path, with no flag that tells
them apart (`llm-and-streaming.md` consequence 3). Closing the source is what cancels the
upstream request: 021's `chat_stream` runs inside an `httpx.AsyncClient` context, and
`aclose()` unwinds it (US-132.AC-2).

### D7 — The partial row is written on its own short-lived connection (briefing; shape chosen here)

How the request-scoped `get_connection` dependency is torn down relative to streaming
body iteration is unverified for the installed FastAPI, so the harness never touches the
handler's connection. `frames.py` provides **`own_connection_persister`**:

- **Inputs.** An `Engine`, the id generator, the user id and the session id. The caller
  obtains the engine with `get_engine(settings)`; the generator comes from `app.state`
  through `get_id_generator`.
- **Output.** The synchronous `on_partial` callable that D3 takes.
- **When called.** It opens one connection from the engine, calls
  `append_assistant_message` (D8), and closes the connection.
- **On any exception** (for example `SessionNotFoundError` because the session vanished,
  or a locked database), it **logs** the session id and the exception class and
  **returns**. The exception is never re-raised: the stream is already ending, and a
  persist failure must not turn a stop into a 500 or mask the `error` frame.

The engine is passed in rather than `Settings`, so `frames.py` does not read configuration.

021's binding:

```
sse_response(request, source, own_connection_persister(get_engine(settings), generator, user.id, session_id))
```

### D8 — `append_assistant_message` is the one assistant-row write (briefing)

It lives in `services/messages.py` beside `append_message` and shares its body: the same
`_require_session` ownership check (raises `SessionNotFoundError`), `generator.next_id()`,
`_now_text()`, the insert, and `_bump_session`, inside one `with connection.begin():`.
The role is `"assistant"` and the kind is NULL. Factoring the shared insert into a
private helper parameterised by role is the coder's choice. `append_message`'s behaviour
must not change.

The service does not check for blank text. The harness filters blanks (D4), and 021's
success path writes whatever the model produced. This is the write used on both
paths (`backend-structure.md` "The streaming route").

### D9 — The consumer reports exactly one of four outcomes and never rejects (planner)

`shared/sse.ts` exposes one function. Inputs: the path (must start with `/api/`), the JSON
body, a frame callback, and the signal. It resolves to one **outcome**:

| Outcome | When |
|---|---|
| **done**, with the message id (a string) | a `done` frame was read |
| **error**, with an `ApiError` | an `error` frame was read (its `code`, `message`, `detail`, status = the response's HTTP status); **or** a non-2xx response, decoded exactly as `apiRequest` decodes it, including the 401 navigation to `/login`; **or** a fetch/read rejection that is not an abort, giving `client_transport_failed`, status 0; **or** a frame whose `data` is not valid JSON or has no `event` string, giving `client_malformed_error` |
| **stopped** | the stream ended or rejected while **the passed signal was aborted**. Decided on `signal.aborted` at that moment, never on the bytes; an abort is never wrapped |
| **unexpected end** | the body ended with no `done`, no `error`, and the signal not aborted |

- The frame callback receives every **non-terminal** frame (`accepted`, `token`,
  `tool_start`, `tool_result`, `tool_fail`) in arrival order.
- A frame with an unknown `event` name is skipped (forward compatibility).
- After a terminal frame the consumer stops reading, cancels the reader, and resolves; a
  later abort cannot change a terminal outcome already read.
- A trailing fragment with no terminating blank line when the body ends is discarded.
- **Parsing.** Lines beginning `data:` are joined with `\n` and one leading space is
  stripped; comment lines (`:`) and other fields are ignored.
- **Reading.** `TextDecoder` with `{stream: true}`; split on `"\n\n"`, keeping the trailing
  partial.
- **The fetch.** `method: "POST"`, `Content-Type: application/json`,
  `credentials: "same-origin"`, `signal`.

The consumer itself constructs no `llm_unreachable`: the caller renders an unexpected end
(D14).

### D10 — `api.ts` exports its failure decoding instead of `sse.ts` duplicating it (briefing)

`api.ts` gains two exported helpers, which `apiRequest` itself then uses:

- **The non-2xx decode.** From a non-2xx `Response`, perform the 401 navigation when the
  status is 401, then produce the `ApiError` from the envelope, or the
  `client_malformed_error` fallback.
- **The rejection mapping.** An abort rejection is returned unchanged; anything else
  becomes `ApiError(client_transport_failed, "The server could not be reached.", 0)`.

`decodeEnvelope` and `malformed` may stay private behind these. `apiRequest`'s observable
behaviour does not change; the existing `tests/shared/api.test.ts` must still pass
unchanged.

### D11 — In-flight assistant text is a dedicated observable field, not a zone row (planner; divergence recorded in `outcome.md`)

`StreamState` gains a **streaming text** field: `null` when no compose is in flight, a
string (initially `""`) while one is. `token` frames append to it. **Nothing is inserted
into `zone`.**

Reasoning:

- 013's `ZoneList` offers an edit control on **every** zone row. A placeholder row
  would carry a client-minted id that `PATCH /api/messages/{id}` must never receive, and
  guarding that is a cross-component rule for a row that exists for seconds.
- Live rendering is 022's, so 019 needs only the data.
- On every outcome, the server's row replaces the in-flight text through a zone re-read.
  Nothing is "copied over at `done`".

`frontend-structure.md` says tokens append to "the in-flight message in the zone" so it
can be edited while streaming. That editing is not possible in 019, and an edit made
during a stream would race the server's own write of that row anyway. `outcome.md` asks
the architect to record the as-built shape and leaves "edit while streaming" to 022.

### D12 — The compose handle: one non-observable field (planner)

`StreamState` gains one **non-observable** field, excluded from `makeAutoObservable` with
annotation `false`. It holds the in-flight compose's **own `AbortController`** and a
**promise that settles when that compose has fully wound down**, re-read included; it is
`null` when no compose is in flight. A controller and a promise are not data any view
renders, and making them observable would wrap them for nothing. Reactivity comes from
the streaming-text field (D11): **`isStreaming(state)`** is `streaming text !== null`.

- **Per compose, separate from the mount.** The controller is distinct from
  `SessionStream`'s mount-level controller. The compose effect takes the mount signal
  and **links** them: a mount abort (unmount) aborts the compose controller. The listener
  is registered once and removed when the compose ends.
- **What a mount abort means.** After a mount abort the effect writes nothing, re-reads
  nothing, and notifies nothing.
- **What a user stop means.** A user stop aborts only the compose controller, and the
  store stays fully usable (D13).

### D13 — `busy` and streaming are separate (013 outcome; architecture binds)

- **Compose never sets or clears `busy`.** A stop leaves `busy` exactly as it was. The
  existing "busy stays true after a mount abort" is unchanged, and harmless because the
  store is dead.
- **`canSend`** additionally requires **not streaming**. Send is absent while streaming
  anyway (Stop holds the slot), but the derivation stays truthful.
- **`canSettle` is unchanged.** Settle stays **enabled during a stream** on its existing
  rules: disabled only on an empty zone with a blank draft, the *partner* position, or
  `busy`. This follows `workspace-shell.md` "The stop control". **No amendment is needed
  for the enablement rule.**
- **`showsDiscard`** is false while streaming. An exchange is being written into the zone,
  so it is not an empty zone to abandon, even before its first row lands.
- The compose effect is a no-op when a compose is already in flight or the draft is
  blank.

### D14 — What each outcome does on the client (briefing)

| Outcome | Notification | Zone re-read | Streaming state |
|---|---|---|---|
| done | none | yes | cleared |
| error | `notifyFailure(apiError)` | yes; **clears nothing else** (R10) | cleared |
| stopped by the user | **none**: nothing failed | yes (US-132.AC-1) | cleared (US-132.AC-2) |
| stopped by unmount | none | **no** | not written |
| unexpected end | `notifyFailure(ApiError("llm_unreachable", "The reply ended unexpectedly.", 0, {}))` | yes | cleared |

"Cleared" means the streaming text goes to `null` and the handle to `null`. It is written
in the same action as the re-read result, so the in-flight text is replaced by the
server's rows, not blanked first. If the re-read fails, `notifyFailure` is called with
that error and the streaming state is cleared regardless.

### D15 — `accepted`: clear the sent draft, re-read the zone, keep re-reads ordered (planner)

On `accepted`, R10's guarantee is now observable: the roleplayer's text is a row. The
effect:

- clears the draft **only if it still equals the text that was sent** (013's rule; text
  typed meanwhile stays);
- starts a zone re-read so the committed message appears with its real id. That is the
  id adoption: it arrives through the served row, with no client-side id write.

The terminal re-read (D14) is issued **only after** that accepted-triggered re-read has
settled. A slow early `GET` can then never land after, and overwrite, the final one. If no
`accepted` arrives (a non-2xx, or a failure before it), the draft is untouched (R10).

### D16 — Pressing Settle mid-stream stops the compose first, then settles (user-confirmed)

`settleComposer` gains a prefix. When a compose is in flight it:

1. sets `busy`;
2. aborts the compose controller, exactly as Stop does, so **no notification**;
3. **awaits the handle's wind-down promise**, which includes the compose's own post-stop
   zone re-read and the clearing of the streaming state;
4. continues with the existing settle flow, unchanged (013 `003`): append a non-blank
   draft, settle, then re-read entries and zone.

Sequencing the stop's re-read **before** the settle request and its re-reads means the
two can never interleave destructively on the client: there is no stale zone list
landing after the settle's fresh one.

### D17 — Accepted residual races (user-accepted, recorded; not engineered around)

The server persists the partial row when it **detects** the disconnect. Nothing on the
client can wait for that write, so two orderings are possible, and both are accepted:

- **Settle mid-stream (D16).** The partial row may be committed **before** the settle
  request, so it is the last zone row and is the row settled, or **after** it. In the
  "after" case it lands in the fresh zone below the newly settled entry, appearing as a
  candidate there on the next re-read. **It is not lost, only one zone later.**
- **Plain stop.** The post-stop zone re-read may run **before** the server's persist has
  committed, in which case the partial appears on the **next** re-read rather than this
  one. The row is not lost; it is late. No retry or delay is added.

Both are recorded in `outcome.md` for `workspace-shell.md`'s stop-control section, and
the live check of each is `[manual/live]`.

### D18 — Tool frames are parsed and ignored in 019 (planner)

The consumer types and delivers `tool_start`/`tool_result`/`tool_fail`. The compose
effect ignores them: the collapsible tool blocks are 022's (brief Out).

### D19 — Five steps (planner)

1. The pure frame layer and the shared append. The harness depends on both.
2. The harness and the persister.
3. The consumer with its `api.ts` export.
4. The streaming state surface, plus the Composer's Stop slot. Both are small and read
   the same two derivations.
5. The compose effect with the settle prefix. Both need a live compose to test.

## Step map

| Step | Subject | Est. source LoC | Depends on |
|------|---------|-----------------|------------|
| 001 | `frames.py` value types + encoder; `append_assistant_message` | ~120 | none |
| 002 | `frames.py` harness (`frame_stream`, `sse_response`) + `own_connection_persister` | ~140 | 001 |
| 003 | `shared/sse.ts` consumer + `api.ts` failure-decode export | ~160 | none |
| 004 | compose call in `streamApi.ts`; streaming fields, `isStreaming`, `stopCompose`, derivation updates; Composer Stop slot | ~90 | 003 |
| 005 | compose effect; settle-mid-stream prefix | ~130 | 003, 004 |

The backend steps (`001`, `002`) and the frontend steps (`003`–`005`) are independent of
each other.

## Test conventions

**Backend**, run from `backend/`:

- pytest, flat `tests/`; each test name ends `__S019_<step>_DoD<n>`.
- No async plugin is installed. Async code is driven with `asyncio.run(...)`, as in
  `tests/test_llm_client.py`.
- DB fixtures come from `conftest.py`: `db_settings(tmp_path, monkeypatch)` and
  `db_engine`.
- Router-level reads build `create_app()` with `app.dependency_overrides[get_settings]`
  and a `TestClient`, logged in for the cookie (existing pattern).
- Fake sources are file-local async generators.
- Expected bytes come from this plan's worked examples, never from calling the encoder.

**Frontend**, run from `frontend/`:

- Vitest/jsdom, `tests/` mirrors `src/`; each `it` title ends **`— DoD-N`**.
- `fetch` is stubbed per file with `vi.stubGlobal`, with file-local helpers and no shared
  helpers module.
- A streamed body is a `Response` over a `ReadableStream` of `Uint8Array` chunks (the
  pattern exists in `tests/shared/api.test.ts`).
- `notifyFailure` is observed through `vi.mock` of `src/shared/notifyFailure`, asserting
  the code of the `ApiError` it got, never notification text.
- Stubs key on exact pathname + method, and request order comes from the stub's log.
- Ids are strings like `"7250000000000000101"`.

## Vocabulary

| Term | Means here |
|---|---|
| **frame** | one SSE event: a value in Python (D2), wire text `data: <json>\n\n` |
| **source** | the async iterator of frame values the harness drains; 021's compose loop |
| **terminal frame** | `error` or `done` |
| **partial text** | the concatenated text of every `token` frame passed through so far |
| **persist** | `on_partial(partial text)` → one `role='assistant'`, `kind=NULL` current-zone row |
| **disconnect** | the client is gone: stop, network drop or closed tab, indistinguishable by design |
| **outcome** | the consumer's single result: done / error / stopped / unexpected end (D9) |
| **compose handle** | the non-observable `{controller, wound-down promise}` of the in-flight compose (D12) |
| **streaming text** | the observable in-flight assistant text; `null` = not streaming (D11) |
| **mount signal** | `SessionStream`'s unmount controller's signal, passed to every effect |
| **stop** | `abort()` on the compose controller; no request |
