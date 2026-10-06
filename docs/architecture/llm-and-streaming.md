# LLM integration and streaming

**Realizes:** FEAT-004, FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013,
FEAT-014, FEAT-015, FEAT-016, ACT-004, UC-010..UC-013, UC-032..UC-038, UC-045,
UC-051, UC-053, UC-055..UC-057, UC-077, UC-081, UC-083, UC-084, UC-085,
US-044, US-073.AC-2, US-107, US-111, US-114, US-132, US-133, US-142, US-144,
US-146

One client abstraction for every provider, the SSE frame protocol, the tool loop,
what goes into context and — just as importantly — what must never go into it.

---

## One OpenAI-compatible client

**Realizes:** FEAT-004, UC-010, UC-011, UC-012, UC-013

Both provider kinds RPHelper supports — **llamaswap** and **OpenAI** — speak the
OpenAI chat-completions and embeddings wire format. So there is **one** client, not
one per provider, parameterised by base URL and credential:

```
LlmClient(base_url, api_key)
  chat_stream(model, messages, tools) -> async iterator of provider deltas
  embed(model, texts)                -> list[vector]
  probe()                            -> reachability result   # UC-011
```

One client because the difference between the two kinds is configuration, not
protocol. Writing two adapters would create two code paths that must be kept
behaviourally identical, with no compensating benefit. `llm_servers.kind`
(`data-model.md`) is therefore a **label** used for admin-facing presentation and
for provider-specific defaults, not a dispatch key that selects an implementation.

The credential arrives through `resolve_secret(api_key_ref)` at call time —
the `"$ENV_VAR"` pointer pattern in `backend-structure.md`. A missing variable is
`secret_ref_missing`, raised before any network call.

`probe()` implements UC-011: it reports reachability and **registration is
unaffected either way** (UC-011's postcondition and alternate flow). The result is
recorded on the row (`last_test_at`, `last_test_ok`, `last_test_error`) so the admin
sees the last known state without re-probing on every page load.

### As built by FEAT-004 (plan 006) — and what is deliberately absent

- **FEAT-004 builds construction, `probe()` and `embed()` only**; `chat_stream`
  was deliberately **not** stubbed, because a stub with no caller is dead code
  FEAT-009/010 would rewrite. **Plan 021 built it**, and the two absence tests
  plan 006 shipped to pin the deliberate gap were deleted with the gap (021 D10,
  021 step `003`).
- **`probe()` returns its outcome and raises nothing; `embed()` raises
  `llm_unreachable`.** Every probe state, total failure included, is an answer
  UC-011 requires to be reported, whereas an embedding has no useful partial
  result. The asymmetry is the kind of thing a later contributor would "tidy";
  do not.
- **Base-URL composition tolerates a trailing slash and an already-present
  `/v1`**, because an administrator types the URL by hand and a wrong composition
  presents as `unreachable` against a healthy host.
- The client is `httpx.AsyncClient`; why, and what the async/sync mix costs, is
  `backend-structure.md`'s "The first async code in the backend".

### `chat_stream` as built (plan 021)

A streaming `POST` to `…/v1/chat/completions` with `stream: true`, yielding an
async iterator of **provider deltas** — not frames, not text:

- **Three delta kinds**: content, **reasoning** (from either `reasoning_content`
  or `reasoning`, because the two provider families differ on the key), and
  **per-chunk tool-call fragments, unaccumulated**. The client deliberately does
  no accumulation of its own; the compose loop accumulates fragments by index
  (below), because the loop is what knows when a round ends.
- **`tools` is sent only when non-empty**, and **`tool_choice` is never sent** —
  whether to call a tool is the model's decision (FEAT-014/015/016 all state it
  that way), and a `tool_choice` would be the instance deciding for it.
- **The iterator ends on `[DONE]` or on a clean end of body.** Either is a normal
  completion; neither is an error.
- **Every failure is one code.** A non-2xx, a transport error, a timeout, or an
  unparseable `data:` line all raise **`llm_unreachable`**. One code rather than
  four because the SPA has one rendering for "the provider did not answer", and
  the distinctions are not ones the roleplayer can act on differently.
- **Closing the iterator unwinds the httpx stream.** This is the upstream half of
  a stop: the harness's `aclose()` of its source closes the provider request
  rather than leaving it running against a client that has gone (the stop section
  below).

**The chat client is built per call, not held.** `llm_registry.open_chat_client`
re-reads `api_key_ref`, resolves it **at call time** through
`resolve_secret` and constructs the client through an **injectable chat-client
factory** (021 D14). So this is a second call site of the `"$ENV_VAR"` pointer
pattern, with the same consequence: rotating a key is an environment change plus
a restart, and an absent variable is `secret_ref_missing` before any network
call.

`_TBD: the streaming call reuses "llm_request_timeout_seconds" — 30 s per httpx
phase, including the READ between chunks. Whether a slow first token on a large
context needs a longer read timeout than a connect or a write does is unmeasured
(021 D10); no requirement states a latency bound, and splitting the one setting
into per-phase timeouts before anything has been observed would be a guess with
four numbers instead of one._

### The model registry and use-time validation

**Realizes:** FEAT-004, FEAT-013, UC-012, UC-050 — see `domain-rules.md` R4

The request path for every generation is exactly three steps, in this order:

```
1. read      sessions.model_server_id / model_name
                                → the model REFERENCE captured at session creation
2. validate  llm_registry       → is that reference an enabled model right now?
3. call      LlmClient          → chat_stream
```

- **Step 1 is a read, not a resolution.** The model reference was resolved once,
  through `character → session`, **when the session was created**, and written
  onto **`sessions.model_server_id` / `sessions.model_name`** — two columns with
  a both-or-neither CHECK and no FK, never a single encoded `model_ref`
  (017 D4, R4, `data-model.md`). The request path does not
  re-walk the chain, so a character configured with a different model afterwards
  does not move an existing session (US-139.AC-1). **Note the chain is
  `character → session` — there is no user level** (UC-050; R1 carries the
  correction).
- **The system prompt and the enabled tool set are different**: those *are*
  resolved live on every request, through `character → session`, against whatever
  the character holds today. The split is deliberate and R4 states why
  harmonising it in either direction is a defect.
- Step 1 **does not** consult the enabled-models registry and **does not** skip a
  level whose model is disabled. Skipping is the silent fallback UC-012 forbids.
- Step 2 is where a dead reference is caught, and it raises
  **`model_not_enabled`** carrying the reference **and which level set it**, so the
  roleplayer can go and change it (`backend-structure.md`'s error model).
- There is no step that substitutes a model. Not a default, not "the first enabled
  one", not the previous session's model.

The same applies to embeddings, with a sharper reason. The designated embedding
model (UC-013) is validated at use time and a missing or changed designation raises
**`no_embedding_model`** rather than falling back to another model — because
vectors produced by a different embedding model are **not comparable** with the
stored ones, so a silent substitution would return confidently wrong search
results rather than an error. See `search-and-retrieval.md`. The designated model
must be **both designated and enabled** (`data-model.md`'s `models`).

**Both use-time validators shipped with no call site, and both have callers
now.** They live in `services/llm_registry.py` and were built by FEAT-004 (plan
006) with no consumer — which was correct at the time and is recorded because the
"covered by service tests rather than through a session" posture is what a reader
of plan 006's tests will otherwise read as an unfinished path. The chat validator
gained its caller through `resolve_model_for_use` (plans 017, 021) and the
embedding validator through the embedding writes (plan 024). The model validator
takes the **server id and the model name as two plain arguments**, which is the
shape the as-built column pair gives it.

### The enabled set, the first-enabled order, and `resolve_model_for_use`

Three facts plans 017 and 021 fixed, recorded here because the capture, the
header picker and the compose path all read the same two of them.

- **The enabled set** is every model whose `is_enabled` is true on a server that
  still exists. **The embedding designation is irrelevant to it** (017 D7): a
  designated embedding model is not thereby a chat model, and an undesignated
  model is not thereby unusable for chat — `models.is_embedding_designated` and
  `models.is_enabled` are independent columns (`data-model.md`).
- **The first-enabled order is `llm_servers.id`, then `models.id`, both
  ascending** (017 D7) — which is the LLM Servers page's own order. It is used by
  the creation-time capture (R4's US-106 floor) and by `GET /api/models`, and
  having one order rather than two is what keeps "the first enabled model" from
  meaning something different to the picker than to the capture.
- **`resolve_model_for_use`** (017 D2) is steps 1 and 2 of the request path in
  one call, and the **order of its three refusals is the design**: no model
  enabled on the instance → `no_model_enabled` (US-107); the session captured
  none → `model_not_chosen` (US-144, UC-077); the captured reference is not
  enabled → `model_not_enabled`. Instance before session before reference,
  because that is the order in which the roleplayer can act. R4 carries the full
  reasoning and `backend-structure.md` the statuses; it is not restated here.
  It shipped in plan 017 **with no call site**, in the same posture as plan 006's
  validators, and **plan 021 wired it into the compose source** — where it runs
  *inside* the stream, after `accepted`, so the roleplayer's text is already
  committed when a refusal surfaces (R10).

**The system prompt and the tool switches resolve live, through
`get_session_configuration`** (017 D8), which plans 020 and 021 consume — the
assembler for the prompt, the loop for the offered tool set. That is the live
half of R4's deliberate split, and the split is R4's to state.

---

## The SSE event protocol

**Realizes:** FEAT-010, FEAT-014, FEAT-015, FEAT-016, UC-032, UC-034, UC-083

**One streaming route: `POST /api/sessions/{id}/zone/compose`**, owned by
`routers/stream.py`. `routers/discussions.py` is gone with the `discussions` table
(`data-model.md`, `backend-structure.md`), and the current zone has no id of its
own, so the route is addressed through its **session**. A second append route,
`POST /api/sessions/{id}/zone/messages`, is **not** streamed and performs no model
call; `backend-structure.md` records why the split exists, and that argument is
not repeated here. Everything below governs the streaming route alone.

Frames are `data:` lines terminated by a blank line, so the client splits on
`"\n\n"` (`frontend-structure.md`).

```
data: {"event":"accepted","message_id":"7250416938275332095"}                  \n\n
data: {"event":"token","text":"..."}                                           \n\n
data: {"event":"tool_start","tool":"memo_search","call_id":"c1","args":{...}}  \n\n
data: {"event":"tool_result","tool":"memo_search","call_id":"c1","summary":"3 memos"} \n\n
data: {"event":"tool_fail","tool":"web_search","call_id":"c2","code":"tool_failed"}   \n\n
data: {"event":"error","code":"llm_unreachable","message":"...","detail":{}}   \n\n
data: {"event":"done","message_id":"7250416938275332096"}                      \n\n
```

| Event | Meaning | Client effect |
|---|---|---|
| `accepted` | the roleplayer's own message is committed to the zone; emitted **once, before the first `token`, and only when the compose carried text** — a textless compose (the retry) emits no `accepted`, because no row was inserted (021 D2, U1) | adopt `message_id` for the message just sent, so an in-place edit of it can `PATCH` without waiting for a reload |
| `token` | an increment of assistant text | append to the in-flight message in the current zone |
| `tool_start` | a tool call has been issued | show the tool as running |
| `tool_result` | the tool returned | mark it complete |
| `tool_fail` | the tool failed; **the exchange continues** | mark it failed, keep streaming |
| `error` | the exchange failed | render the failure; **discard nothing** |
| `done` | the exchange completed and is persisted | finalise; `message_id` identifies the assistant's row **in the current zone** |

### Ids in frames are decimal strings — the rule reaches here too

`backend-structure.md`'s JSON id boundary is written in terms of request and
response bodies, and an SSE frame is the easy thing to overlook: it goes through
no pydantic response model and does not look like "an API payload". It is JSON on
the wire, parsed by `JSON.parse` in the browser, and it is bound by the rule **in
full**.

- **`accepted.message_id` and `done.message_id` are decimal strings**, never JSON
  numbers. As a number either would pass `Number.MAX_SAFE_INTEGER` and round
  exactly as a response body would — onto a value that may be another row's id
  (`data-model.md`, Identifiers). These two frames are the likeliest site of that
  defect in the codebase, because they are emitted by hand rather than serialized
  by a model. They carry **different rows**: `accepted` the roleplayer's committed
  message, `done` the assistant's.
- **Any id inside an `error` frame's `detail` is a decimal string too** — the
  `detail` object is the JSON error body's shape and carries its rule.
- **`call_id` is not an id in this sense.** It is the provider's own tool-call
  identifier, an opaque string carried verbatim: not a snowflake, not minted by
  `app/ids.py`, and no ordering may be read into it. Named so the two are not
  confused in either direction.
- **Frames are constructed in one place, `services/llm/frames.py`**
  (`backend-structure.md`), so the string conversion has one site rather than one
  per emit call. **As built** (019 D2) that module holds **seven immutable frame
  value types and exactly one encoder** — `data: ` plus compact JSON with `event`
  first plus `\n\n`, UTF-8, every id through `str()`. The consequence is the rule
  that matters: **a frame source yields frame *values*, never strings**, so no
  producer can hand-roll a `data:` line and no producer can forget the id
  conversion. The **`error` frame is built from a `DomainError`'s inner fields**
  (`code`, `message`, `detail`) and **not** from `to_wire()`'s `{"error": {…}}`
  wrapper — the frame already names itself `"event":"error"`, so wrapping it
  again would nest the body one level deeper than the JSON error responses the
  SPA's one renderer expects.

Rules the protocol enforces:

- **`done` is mandatory on success.** A stream that closes without it means the
  exchange did not complete — but **"did not complete" is no longer the same as
  `llm_unreachable`**, because a stop is now a fourth way a stream can end. See
  the termination table below.
- **`error` and `done` are mutually exclusive and terminal.** Exactly one of them
  ends every stream that the *server* ends.
- **`tool_fail` is not terminal.** This is the protocol expression of UC-051's and
  UC-053's exception flows: a failed tool does not end the exchange. It is a
  distinct event from `error` precisely so the client cannot conflate them.
- **`error` uses the same `{code, message, detail}` shape** as the JSON error body,
  so the SPA has one error renderer (`backend-structure.md`).
- **`tool_result` carries a summary, never the raw retrieved content.** The content
  goes to the model, not to the screen. Two reasons: the zone should show
  that a search happened, not paste its results into the reading surface; and a raw
  payload on the wire is an easy way for content to reach a surface it was not
  scoped for.
- `X-Accel-Buffering: no` is set on the response by the application
  (`deployment.md`), independently of nginx's `proxy_buffering off`.

### Four ways a stream ends — and no new frame for the fourth

**No frame is added for the stop.** A stopped stream is a **fourth termination**,
not a fifth event:

| Termination | Server emitted | Client renders |
|---|---|---|
| Success | `done` | finalise on the assistant's row id |
| Server-side failure | `error` | the typed failure, discarding nothing (R10) |
| Unexpected close | nothing | `llm_unreachable` |
| **Stop (UC-085)** | **nothing — the client closed the connection** | **nothing failed**; reload the zone |

**The server never ends a stream silently, and that is enforced by the harness
rather than trusted to each source** (019 D5). The table above was written as
though a source always ends with a terminal frame of its own. It need not: a
source may raise a non-domain exception, or exhaust without emitting either
`error` or `done`. In both cases **the harness synthesizes an `error` frame,
`llm_unreachable`, with a fixed message**, and that is what reaches the client.

The payoff is a sharp reading of silence: **a stream that produced no terminal
frame means the connection went away** — row 3 or row 4 of the table, never a
server-side fault that forgot to announce itself. Without the synthesis, a bug in
one source would present to the client as a network problem, which is the
diagnosis that sends somebody to look at nginx.

**The inference "a stream ending without `done` = `llm_unreachable`" is now wrong
for one of the four cases, and this is the correction.** The client **knows
whether it aborted**, because it is the party that called `abort()`. So:

> **A client that initiated the stop must not surface `llm_unreachable` for it.**
> The distinction is made on the client's own `AbortController` state, never by
> inspecting the stream — there is nothing in the byte stream to inspect, which is
> the point. `frontend-structure.md` owns the consumer half.

This is the one place the protocol's "silence is never success" rule needs a
qualifier: silence is never success, but it is also not always a failure. The
server side genuinely cannot tell the three silent cases apart, and deliberately
does not try — see the stop section below.

### Thinking — a text convention, not a frame

**Realizes:** US-114, US-146

Reasoning models emit a second delta stream beside their content, and the
protocol carries it with **no new frame type** (021 D4, U2): **provider reasoning
deltas stream as ordinary `token` frames wrapped in `<think>` … `</think>`.** The
open tag is emitted before the first reasoning delta of a run, and the close when
content begins or the round's provider stream ends.

- **No new frame, because the client already renders `token` text.** A
  `reasoning` frame would need its own client path, its own persistence question
  and its own answer for a stop landing mid-thought. A tag inside the token
  stream needs none: the text flows, is persisted and is re-read by the one
  mechanism that already exists. `022` renders the tags as the collapsible
  thinking block (US-114, `workspace-shell.md`).
- **Inline `<think>` content passes through.** A model that writes the tags
  itself produces the same stream, and the design does not try to tell the two
  apart — there is nothing in the bytes to tell apart, and a heuristic would make
  the rendering depend on which provider answered.
- **A stop keeps the reasoning in the partial row.** R10's persist rule writes
  the accumulated token text, tags included; no special-casing strips it on the
  way out, because the roleplayer may want to see what the model was doing when
  they stopped it.

**The record never carries reasoning — `US-146`.** `chat.strip_think` is applied
in exactly **three** places, and the count is worth stating because it grew:

| Where | What is stripped | Plan |
|---|---|---|
| **settle**, when the head's role is `assistant` — **before** `(( ))` classification | the head's `<think>` blocks | 021 D4 |
| **context assembly**, current-zone **assistant** rows | their `<think>` blocks | 021 D4 |
| **translation**, the provider's result before it is cached | the result's `<think>` blocks | 023 D10 |

**User text and settled text are never think-stripped.** A user head carries no
reasoning to strip, and stripping settled text would mean re-parsing stored
prose, which R12's "parse once, at settle" forbids for the same reason. A settled
head whose stripped text is empty **still settles** — no refusal was invented for
it (021 D4) — and the copy-out therefore never carries reasoning either, because
there is none left in the row.

### Ordering guarantee that protects the roleplayer's text

Before the response begins, the handler has already committed the roleplayer's
message row into the current zone (`domain-rules.md` R10, UC-032,
`backend-structure.md`). Consequently an `error` frame — at any point, including
before the first `token` — loses nothing: the settled record and everything
already in the zone survive intact, the failure is visible, and retry is possible.
The client's `error` handler is forbidden from clearing the record or the zone.

**The `accepted` frame makes that ordering observable rather than merely
promised.** R10 already requires the roleplayer's text to be persisted *before*
any model call, so at the instant the stream opens the row exists and its id is
known: the frame reports a fact the handler is already holding, and costs nothing
to emit. It carries that row's id as a decimal string, and it is emitted **once,
ahead of the first `token`**.

That is why this is the right shape rather than a convenience. R10's guarantee is
otherwise something the client takes on trust — it has no way to observe that its
text survived until it re-reads the zone. A frame arriving *before* any model
output turns the guarantee into something the client can see, and it arrives on
the failure path too: if the exchange dies at the first byte, the client already
holds the id of the text it just typed and can edit it in place (US-115) through
`PATCH /api/messages/{message_id}`. The rejected alternative — re-reading after
`done` — delivers the id only on the success path, which is precisely the path
where having it matters least.

`accepted` and `done` are not interchangeable and neither replaces the other:
`accepted` names the roleplayer's committed message, `done` the assistant's, and
both are strings.

**This closes the `_TBD:` previously recorded here** — that no frame carried the
id of the roleplayer's own committed row, leaving an in-place edit of a
just-sent message with nothing to `PATCH` until the next
`GET /api/sessions/{id}/zone`, so US-115 failed until a reload. It was recorded
rather than silently fixed because a new frame is a protocol change; it is closed
by making one.

#### The retry is a textless compose — nothing is re-inserted

**Realizes:** US-044.AC-3, US-044.AC-5

Asking for a different candidate is **the same route with no text** (021 D2): a
`POST /api/sessions/{id}/zone/compose` whose body carries no `text` re-runs
generation **over the zone as it stands**, inserting no row. Consequences, each
load-bearing:

- **No `accepted` frame** (the event table above), because there is no committed
  row to name.
- **The model is re-read at use time**, so changing the session's model in the
  header and then retrying takes effect — which is what makes the retry a remedy
  for `model_not_enabled` rather than a repeat of it.
- **It is refused with `zone_empty`** — as JSON, **before any stream opens** —
  when the zone holds no non-tool row (R11). A pre-stream refusal rather than an
  `error` frame because nothing has been committed and nothing is in flight;
  there is no text to protect by getting the stream open first.
- `US-044.AC-3`'s widened form and `US-044.AC-5` make this available on **any**
  exchange, failed or not, so the control is not a failure affordance. The
  control itself is `022`'s (`workspace-shell.md`).

#### Model-resolution failures arrive *inside* the stream

`no_model_enabled`, `model_not_chosen`, `model_not_enabled` and
`secret_ref_missing` are raised by `resolve_model_for_use` **inside the streaming
source, after `accepted`** — not as a pre-flight check before the route answers
(021 D3). So they arrive as `error` frames with the roleplayer's text already
committed, which is R10 applied to the one failure class that looks like it
belongs in a guard. A pre-flight check would be the shorter code and would refuse
the request **with the text still in the browser**, which is exactly the loss R10
exists to prevent.

---

## Stopping model work in flight — UC-085

**Realizes:** FEAT-010, FEAT-011, FEAT-014, FEAT-015, FEAT-016, UC-085, US-132,
US-133

**The mechanism: the client calls `controller.abort()` on the existing
`fetch()`.** That is the whole of it.

- **No stop route.** There is no `POST /api/sessions/{id}/stop`.
- **No in-process registry of in-flight work.** Nothing maps a session, a user or
  a request id to a running generator.
- The server **detects the disconnect inside its streaming generator**, persists
  whatever assistant text was produced so far as an ordinary current-zone row,
  and unwinds.

**The detection, as built** (019 D6): **one `finally` keyed on "no terminal frame
was emitted"**, which covers all three ways the harness learns the client is gone
— task cancellation, generator close, and an `is_disconnected()` poll before each
write. One predicate rather than three handlers, because the three are the same
fact arriving by different routes and a per-route handler is a per-route chance to
get the persist wrong. The persist itself is **synchronous**, and the source is
then closed with a **shielded, error-suppressed `aclose()`** — shielded because
the surrounding task is usually already cancelled and an unshielded close would
not run; error-suppressed because a failure *while cleaning up after a client
that has gone* has nobody to report to. That `aclose()` is what unwinds the
upstream `httpx` request, so a stop does not leave a provider call running for a
reply nobody will read.

Why this shape rather than a control route: a stop route needs a name for the
work being stopped, and the work has no name — the current zone has no id (R11)
and the exchange is a request, not an entity. Naming it would mean a registry,
and a registry is server state that can outlive the thing it describes. Closing
the socket needs no name and cannot leak.

**Four consequences, chosen knowingly. They are written out because a planner who
rediscovers the last two will otherwise conclude the design is wrong and quietly
build something else.**

**1. Partial text survives, as an ordinary candidate.** The partial assistant row
is persisted on the way out, so it lands in the current zone as a normal,
editable message the roleplayer can promote, rewrite or settle (US-132.AC-1).
This is **R10's principle extended to the assistant's side**: R10 says a model
failure loses none of the roleplayer's text; this says a stop loses none of the
model's either. A coherent extension of an existing rule, not an ad-hoc addition —
and the same reason applies, that the roleplayer's next action should never be
retyping something the system already had.

**The rule as built is wider than the stop, and the widening was accepted at
finalization** (019 D4). The harness persists the accumulated `token` text
**whenever no `done` frame passed through** — so a client disconnect, a *domain*
error, a *synthesized* error (the harness's own `llm_unreachable` above) and a
terminal-less exhaustion all keep whatever the model produced. The row is written
**before** the `error` frame, so the frame never announces a failure that then
loses text. Two edges worth having in writing:

- **Whitespace-only accumulated text writes no row.** An empty candidate is not a
  candidate, and a blank zone row would be something the roleplayer has to clear
  by hand.
- **On the success path the *source* writes the row, before it yields `done`** —
  not the harness. That is why the predicate is "no `done` passed through" rather
  than "an error happened": one writer per outcome, and no path where both write.

Why this is a strict improvement rather than scope creep: R10 exists so nothing
produced for the roleplayer is thrown away, and **a mid-stream failure discards
exactly as much as a stop does**. Treating the two differently would have meant a
flaky provider losing partial output that a deliberate stop preserves.

**2. The client gets no terminal frame and no row id, so it reloads the zone.**
There is no `done`, so there is no `done.message_id` naming the persisted partial
row. After a stop the client **re-reads `GET /api/sessions/{id}/zone`** and picks
up the candidate from there.

**This is not a compromise and must not be read as one.**
`ui-conventions.md` already mandates **never-optimistic mutations with a re-load
after every one**, and a stop is a mutation whose result the client did not
observe. The reload is the house rule applying, not an exception to it. The only
thing the abort costs is the round trip the `done` frame would have saved, which
is the same round trip every other mutation in the product already pays.

**3. A stop, a network drop and a closed tab are indistinguishable — and all
three are handled identically.** The server sees one thing: the client is gone.
It persists the partial row and unwinds, for all three.

**Frame this as a benefit, because it is one.** A flaky connection now also
preserves partial output, having previously produced nothing. And there is **no
code path that needs to tell the three apart** — no heuristic, no "was this
deliberate?" flag, no timeout that guesses. The only party that can distinguish
them is the client, which needs to only for the one purpose in the termination
table above: not showing `llm_unreachable` for its own stop.

**4. Stopping mid-tool-call ends the exchange.** There is no wrap-up pass and no
final answer, because **the connection the answer would stream over is the one
that just closed**. The loop does not resume, does not re-enter with a "the tool
was cancelled" message, and does not produce a closing sentence.

The candidate left behind is whatever prose had already streamed — **which may be
empty**, if the stop landed during the first tool call before any `token` frame.
Recorded bluntly: an empty current zone after a stop is a correct outcome, not a
lost row, and it is then abandonable under UC-086/US-134 like any other empty
zone.

### Stopping, and what a stop is not

Two things about a stop read like the same thing and are **deliberately
different**. Both were once recorded here as named divergences from
`docs/product/`; **both acceptance criteria now state what the build does**, so
what follows is settled design and not a gap. The engineering reasons are
unchanged and are kept, because they are what makes the difference principled
rather than accidental.

- **A stopped tool call ends the exchange — `US-133.AC-1`.** Consequence 4 above
  is the whole mechanism: there is no wrap-up pass and no closing sentence,
  because **the connection the continuation would have streamed over is the one
  that just closed**. Whatever prose had already streamed survives as an ordinary
  candidate (US-132) — which may be nothing at all, if the stop landed inside the
  first tool call. The alternative — designing the stop so the exchange could
  continue — needs a server-side registry of in-flight work, which is the state
  this design removed and which the "Why this shape rather than a control route"
  paragraph above rejects for its own reasons.
- **A *failed* tool leaves the exchange alive** (UC-051, UC-053, R9). The loop
  appends a message telling the model the tool failed and the assistant carries
  on without it. **The two differ precisely because a failed tool leaves the
  socket open and a stop does not** — which is also why `tool_fail` is a
  non-terminal frame while a stop emits no frame whatever. A reader meeting the
  two together should read them as a boundary, not as an inconsistency: the
  failure is a *result* the loop can react to, and the stop is the loop's
  transport going away underneath it.
- **Not caching a stopped translation is best-effort — `US-133.AC-2`'s
  `Constraint:`.** It is a constraint on the criterion rather than a divergence
  from it. The mechanism and the reason a guarantee is not available are in the
  translation section below: translation is **not streamed**, so aborting the
  `fetch()` stops the client waiting while the server handler runs to completion.
  The user-visible half of the criterion — *the original text stands* — holds
  unconditionally, because nothing about the flicker's rendering depends on
  whether the cache row landed.

**There are two stop controls, not one, and that is design** (023 D4, user
decision). The composer's `IconPlayerStop` governs a compose exchange and
**does not reach a translation**; a pending translation is cancelled by its own
flicker, which reads "Cancel translation" while pending. The reason is the same
asymmetry as above — the compose stop *is* an `abort()` on the stream the
exchange is riding, and a translation has no stream to abort, so one control
over both would promise an identical effect it cannot deliver on the second.
Each control cancels the work its own surface started.

---

## The tool-calling loop

**Realizes:** ACT-004, FEAT-013, FEAT-014, FEAT-015, FEAT-016

Three tools, and only three (`domain-rules.md` R9): `memo_search`,
`session_search`, `web_search`. The loop:

```
 assemble context ──► chat_stream ──┬── text delta ──────────────► token frame
                        ▲           │
                        │           └── tool call ──► tool_start frame
                        │                              │
                        │                     dispatch (scoped read)
                        │                              │
                        │                   ┌──────────┴──────────┐
                        │                success                fail
                        │                   │                     │
                        │            tool_result frame      tool_fail frame
                        │                   │                     │
                        │            append tool result    append "tool failed"
                        │            message to the        message to the
                        │            conversation          conversation
                        └───────────────────┴─────────────────────┘
                                   re-enter with the tool output
 ...until the model produces a final answer ──► done frame
```

Rules:

- **A failed tool is a tool *result*, not a stream error.** The loop appends a
  message telling the model the tool failed, and continues (UC-051, UC-053
  exception flows; FEAT-010's exception flows). The assistant carries on without
  it. This is the single most commonly mis-implemented rule in this document, and
  it is tested by making a tool fail and asserting the exchange still produces
  an answer.
- **Tool availability is an intersection, not a single switch** (021 D5, U3).
  A tool is offered iff **its resolved switch is on** *and* **an implementation is
  registered under that name** — and `web_search` carries a third condition of its
  own, that the instance holds search credentials (below). The switch comes from
  FEAT-013's `character → session` chain (R1 — **not** `user → character →
  session`, which is the corrected chain), resolved **live on every request** like
  the system prompt and unlike the model. A disabled tool is **not offered to the
  model** — it is absent from the tool list, not present-and-refused. A tool the
  model cannot see cannot be attempted, which is a cheaper and more honest
  enforcement than rejecting the call.
  - **Declarations are the seam's, not the implementation's.** The three live in
    `services/tools/definitions.py`, so a schema change is an edit to that file
    and never a change made from an adapter — which keeps "what the model is told
    the tool takes" in one readable place.
  - **The offered order is fixed**: `memo_search`, `session_search`,
    `web_search`.
  - **Tools reach the model only through the API's `tools` parameter**, never as
    prose in the system prompt (020 D2, confirmed by 021). The prompt carries no
    tool description at all.
  - **All three are implemented and registered** (plans 026, 027, 028), so the
    production registry holds three entries. Earlier states of this sentence —
    empty after 021, one after 026, two after 027 — are history, not current.
- **Every tool dispatch of the roleplayer's own material is a scoped read**, and
  the scope comes from **`ToolScope`**, built only by the seam from an
  owner-scoped session read (021 D6, R9, `session-stream.md`). `memo_search`
  receives `user_id` plus the chain's level ids; `session_search` receives
  `user_id` and `character_id` and never `setup_id` (UC-054, 027 D7). **Tool
  arguments never carry ids**, so a tool cannot widen its own scope even in
  principle. That is what makes FEAT-019's isolation a property of one seam rather
  than of three implementations.
- **`web_search` is the one tool that is not a scoped read of the user's data**,
  and the exception is deliberate (028 D6, D8). It receives **no scope ids** and
  reads **nothing** from the database; it is bounded instead by its outbound rule
  — the only content that leaves the instance is the query. R9 carries the rule;
  the `web_search` section below carries the mechanism. Named here so the "every
  dispatch is a scoped read" sentence is not read as covering a tool that has
  nothing to scope.
- **The assistant never writes into the record.** No tool mutates anything, and a
  candidate lands in the **current zone** and nowhere else (UC-035, R11) — where
  the roleplayer may rewrite it in place, the assistant's text included (US-115),
  and must **settle** it for it to become record (US-126). The only other door
  into the record is a pasted partner block, which is born settled (US-121).
- **There is no iteration cap, and the `_TBD:` that asked for one is closed.**
  `docs/product/` decided: FEAT-010 states "there is no cap on tool iterations,
  the stop is what bounds a runaway loop", and FEAT-014/015/016 each repeat
  "there is no limit on how many times the assistant may call tools before
  answering". So the loop has no round counter and no `max_iterations`.

  **The rationale survives the abort mechanism intact, and the connection is the
  whole reason no cap is needed.** The objection a cap answered was that an
  unbounded loop can spin forever. It cannot, here: **the loop dies with the
  socket.** The roleplayer watching `tool_start` frames repeat presses stop, the
  `fetch()` aborts, the generator detects the disconnect and unwinds (above) —
  so the bound is the roleplayer's patience, applied through a control the
  product gives them, rather than a number nobody can choose correctly. A cap
  would additionally have to fail *somehow* when it tripped, and every option
  (silent truncation, an `error` frame, a forced final answer) is worse than the
  roleplayer deciding.

  The two facts that make this safe are worth keeping together: the loop is
  bounded by the connection, and **a stopped exchange keeps its partial text**
  (US-132), so aborting a runaway loop is cheap for the roleplayer rather than
  destructive. A cap is a loop guard and was never context compaction, which
  remains a separate non-goal (`overview.md`).

### How one round is assembled (021 D11)

The client yields fragments, not calls, so the loop does the assembling:

- **Tool-call fragments are accumulated by index.** A provider streams a call's
  name and arguments across several chunks, keyed by position, and the loop joins
  them; `chat_stream` deliberately does none of this (above), because only the
  loop knows when a round has ended.
- **Per round, the assistant message sent back carries its content *without*
  reasoning, plus the round's calls in index order.** Reasoning is for the
  roleplayer's screen and the persisted row, not for the next request — sending it
  back would spend context on the model's own scratch work.
- **One assistant row per exchange**, holding all streamed token text across every
  round, `<think>` tags included. Not one row per round: the roleplayer settles a
  *candidate*, and a candidate assembled across three tool rounds is still one
  candidate.
- **A call with no id from the provider gets the fallback `call_<n>`**, so the
  `tool` message can be paired with its call. `call_id` remains opaque and
  unordered (the id rule above).
- **The provider iterator is always closed with the source**, which is the
  upstream half of the stop.

### `web_search` — the provider seam and Google

**Realizes:** FEAT-016, UC-055, UC-056, UC-057, US-073.AC-2

The `_TBD:` this section carried — no provider chosen, the adapter deferred to
FEAT-016's plan — **is closed** (plan 028). What is built:

- **A provider protocol in `services/web_search/`**: `search(query, limit)`
  returning ordered plain-text results. **One implementation**, the **Google
  Custom Search JSON API** — `GET …/customsearch/v1`, parameters `cx`, `q` and
  `num`, with the **key in the `X-goog-api-key` header and never in the URL**
  (028 D1, D4, U1). **Five results, a 10 s timeout, no caching.** No caching
  because a roleplay's lookups are one-off and a cache would be a second store of
  roleplayer-derived queries for no benefit.
- **The key is in the header deliberately.** A key in a query string reaches every
  intermediary's access log, including this instance's own (`deployment.md`'s
  redaction rule, which plan 028 extended for exactly this reason).
- Its **tool definition** and its place in the loop, identical in shape to the
  other two, with its three justified uses in the description so what the model is
  told matches the product: a real-world fact; an idiom or naturalness check; a
  direct, roleplayer-initiated lookup (FEAT-016, challenge C2).
- Its **failure behaviour** — `tool_fail`, the exchange continues.

**Availability needs credentials as well as the switch** (028 D3, U3).
`web_search` is offered **iff the instance holds both search credentials and
`tool_web_search` resolves true**. An unconfigured instance therefore never
offers it — which is the same enforcement the other two tools get, applied to a
second condition: a tool the model cannot see cannot be attempted. The mechanism
is that **`routers/stream.py`'s registry dependency builds the registry per
request from settings** — the static two plus `web_search` when configured — so
021's `offered_tools` is unchanged and the credential check is not a fourth kind
of rule inside the loop.

**The indicator and the offer can disagree, and `US-073.AC-2` ratifies that.**
The session header's "Web search: on" shows the **resolved chain**, not whether
the instance holds credentials, so on an instance with no key the indicator reads
on while the tool is never offered. That was recorded as a requirements gap by
plan 028 and the product has since spoken: the criterion requires the indicator
to reflect the resolved switch. It is the as-built behaviour, ratified.

**Failures carry nothing.** Every provider failure becomes `ToolFailedError`
(`tool_failed`, `detail {"tool": "web_search"}`), **raised with no chained cause**
and carrying **no query, key, URL or response body** (028 D5); the seam's
`tool_fail` path does the rest. The chaining matters: an exception chained to the
transport error would put the URL — and therefore the query — into any traceback
that is ever formatted.

**The outbound boundary.** Only the **query** leaves the instance, plus the engine
id, the result count and the key. No ids, no persona, no message text beyond
whatever the model put in the query, and **neither the provider nor the adapter
logs anything** (028 D6, D7). `overview.md` records this as the instance's one
outbound call carrying roleplayer-derived text other than to an LLM server.

**Known risk, and it has a date.** **Google has closed the Custom Search JSON API
to new customers, and existing customers must transition by `2027-01-01`.** The
seam is what keeps a replacement small: one provider class plus the factory in
`tools/web_search.py`. **Flip condition:** the API stops answering for this key,
or the transition date arrives — a new provider is then a plan, not a redesign.
`deployment.md` carries the same date as an operational watch item, because the
first symptom will be an operator's, not a developer's.

---

## Context assembly — what the assistant reads

**Realizes:** FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013, UC-029, UC-034,
UC-038, UC-045, UC-081, UC-083, UC-084

ACT-004 "consumes forced memos and the session's settled entries" (`actors.md`,
R9). That is the whole list, and it is a closed list.

```
system prompt  = resolved system_prompt (R1: character → session, LIVE —
                   no user level exists; not captured at creation, unlike
                   the model, which is read from sessions.model_server_id /
                   model_name)
               + character sheet
               + FORCED memos: is_enabled AND is_forced over the resolved chain
                 (R2/R3, UC-045), ordered — see below
               + three fixed instruction sections, always present:
                   · the message tags           (the [partner] / [my turn] /
                                                 [decision] convention below)
                   · the languages              (resolved rp_language and
                                                 preferred_language, R1)
                   · the double parentheses     (R12, US-129, US-130)

messages       = settled_entries ∪ current_zone   for this session,
                 ORDER BY id                      (data-model.md's named
                                                    selectables — not SQL views)
```

**Tool descriptions are NOT in the prompt**, and the line that said they were is
removed (020 D2, confirmed by 021). Enabled tools reach the model through the
API's **`tools` parameter**, which the loop sets from 017's resolved switches.
Two places describing one tool set is how the prompt and the parameter come to
disagree about what is available.

**Two further absences in the prompt, both deliberate** (020 D2, U2): **no setup
description** and **no character name**. The setup's text is in the session's
`session_vec` match text (`search-and-retrieval.md`) but not in the prompt,
because what the assistant needs about the situation is in the settled record it
is reading; and the character's *name* is a label for the roleplayer's own lists,
not an instruction to the model, whose persona is the sheet and the system
prompt. Named as absences so neither is added as an obvious improvement.

### Prompt layout — the markers are the contract (020 D10)

The assembled prompt has a fixed textual layout: **section headings, a heading
per memo level, a `[note]` delimiter between notes, and a fixed lead-in sentence
per instruction section.** `services/context.py` owns the exact strings.

**Tests bind to the markers, never to the instruction prose.** That split is the
whole reason the layout is recorded as a contract: the wording of an instruction
is something a later feature may well improve against a real model's behaviour,
while the *structure* is what a test can assert without pinning prose nobody
wants frozen.

**What is omitted when it is absent** (020 D5):

| Part | When absent |
|---|---|
| resolved system prompt | the section is **omitted entirely** — there is **no default persona**, and inventing one would be the instance speaking in the roleplayer's voice |
| character sheet | omitted when empty or whitespace-only |
| forced notes | the whole notes section is omitted when the chain yields none |
| the three instruction sections | **never omitted** — they describe how to read what *is* there, so they are correct even on an otherwise empty prompt |

### The message list is the union of the two selectables

The three-table shape this doc used to describe is gone: `entries`, `discussions`
and `discussion_messages` merged into one `messages` table, and **`discussions` no
longer exists** (`data-model.md`). Assembly now reads the **`settled_entries`**
selectable unioned with the **`current_zone`** selectable, both scoped to the
session and ordered by `id` — a snowflake is k-sortable, so `ORDER BY id` *is*
stream order and there is no `position` column to consult. They are **named Core
selectables, not SQL views**; there are four of them and the schema holds no view
at all (`data-model.md`).

**As built the union is two reads, not one query** (020 D3, D7): plan 012's
`list_entries` and `list_zone`, **merged by id** in the assembler. The merge is a
merge rather than a concatenation because **the two lists can interleave** — a
partner block filed while a draft sits in the zone is a settled row with a higher
id than an unsettled one (`data-model.md`'s `position` note) — so appending one
list to the other would hand the model the turns out of order.

**Buried rows are excluded by construction, not by a predicate this module
writes.** That is the whole purpose of the two selectables: the merge converted a
missing join into a `WHERE` clause, and the selectables put that clause in exactly
one place (`data-model.md`, R11). Assembly therefore names **no** table — a query
here selecting from raw `messages` is a defect, and R11 says the same from the
other side: settle and re-open are the only two operations that touch it.

#### Each settled row is tagged with its kind (020 D1, U1)

A settled row keeps its **stored role**, and its content is **prefixed
`[partner]`, `[my turn]` or `[decision]` plus a line feed**. Zone rows carry no
tag, and the prompt's message-tags section explains the convention.

The reason is a consequence of the schema rather than a presentation choice:
**partner blocks and the roleplayer's own turns are both `role='user'`**, so
without a tag the model cannot tell which side of the roleplay a settled line
came from — which is the one distinction the whole product is about. The
alternative, mapping partner blocks onto `role='assistant'`, was rejected because
the assistant's own candidates are that role and conflating them would make the
model read the partner as its own earlier output.

**Stored text is never changed** (R12). The tag is added on the way into the
request and exists nowhere in the database.

#### Tool rows are replayed, not skipped (021 D9)

This **supersedes plan 020's "`role='tool'` rows are skipped"**, which was
correct only for as long as no tool existed. Each zone tool row becomes **two**
messages:

1. an **assistant** message with empty content carrying that **one** call, then
2. a **`tool`** message carrying the call's payload content — or the fixed failed
   literal, when the recorded status is `failed`.

**An unreplayable row is skipped**, not reconstructed: a row whose payload cannot
be read back into a call/result pair would otherwise produce a `tool` message
with no matching call, which providers reject outright.

The reason the replay exists at all: a retry (above) re-runs generation **over the
zone as it stands**, so the zone may already contain the record of tool calls from
the previous attempt. Skipping them would make the model re-issue the same
searches; replaying them hands it what it already found. Pairing a call with its
result is the seam's own id discipline, which is why plan 020 deferred this to
021 rather than guessing at it.

**Current-zone assistant rows are `<think>`-stripped on the way into context;
settled rows never are** (021 D4) — see the Thinking section above for the three
strip sites and why stored text is not re-parsed.

### Decisions are context like anything else

A `kind='decision'` row is a settled entry, so from the moment it is settled it
reaches the assistant as context with every other settled row (US-122, UC-081).
**Nothing special is required** — it arrives through `settled_entries`, by the
same path as a `partner` block or a `turn`. Said explicitly because a reader will
look for a special case: filing a decision as a settled row rather than a side
note is precisely what makes the assistant see it. What *is* special about a
decision is its language and its copy-out, not its reach.

### What must NOT be in context — each with the requirement that forbids it

| Excluded | Why |
|---|---|
| Memos where `NOT is_enabled` | reach the assistant by **no path** (R3, US-100, UC-052) — not context, not tools, not error payloads. Absolute, whatever `is_forced` says |
| Memos where `is_enabled AND NOT is_forced` | searchable: reachable only through `memo_search` (R3, FEAT-012) |
| Buried rows | a settled group's scaffolding never reaches the assistant again, then or later (UC-038, R7) — excluded by the `settled_entries` / `current_zone` selectables rather than by a predicate here (R11) |
| Translations | a translation never enters session context; context holds only the RP language (R8, FEAT-011) — assembly never reads the `translations` table |
| Any other user's material | FEAT-019, UC-065; assembly is scoped by `user_id` |
| Another character's sessions | FEAT-015/UC-054 boundary; assembly reads only this session |

The absences are the invariant. A test that proves the right things are present is
half a test here; the negative cases above are the ones that protect product
guarantees.

### Forced-memo selection: `is_enabled` gates first

This is the most dangerous paragraph in the document, and it is dangerous
**because of the two-boolean split**. The memo `state` column is gone; `is_enabled`
and `is_forced` replaced it (R3, `data-model.md`). The predicate is
`is_enabled AND is_forced`, and **`is_enabled` gates first — `is_forced` is only
consulted afterwards** (R3). An assembler that selects on `is_forced` alone puts a
**disabled, forced** memo straight into the system prompt, which is exactly the
absolute exclusion R3 states, breached where it is hardest to notice: the prompt
is not a surface anybody reads in a test assertion.

Name it plainly: **this bug did not exist in the old design; the split made it
expressible.** A single `state` of `forced` / `searchable` / `disabled` could not
represent a disabled-and-forced memo at all, so `state = 'forced'` was
self-gating. Two booleans can represent it — deliberately, because US-101 requires
disabling to preserve the forced flag so re-enabling restores the mode — and the
cost of that capability is a conjunction that must now be written correctly by
hand, here and in `memo_search`'s mirror predicate (`is_enabled AND NOT
is_forced`). The negative test is not "a disabled memo is filtered from the memo
list"; it is **a memo that is disabled *and* forced does not appear in the
assembled system prompt.**

**As built, the conjunction is not written here at all — and that is the point**
(020 D6, 015 D7). Selection is `resolve_chain` (`services/memo_chain.py`)
filtered by **`memo_reach(...) == "forced"`**: the one derivation that tests
`is_enabled` first, shared with `memo_search`'s `"searchable"` reading
(R3 names both copies). **No hand-written conjunction exists in the assembler,
and a source test pins that** — which turns "the ordering must survive into every
query" from a review convention into something a test can fail. A later assembler
that re-derives the predicate inline is the defect, even if it gets it right.

### Forced-memo order is part of this contract

Order was previously unspecified here. It is now specified in two parts:
**levels in fixed order — user → character → setup → session** (US-103.AC-1, R2's
chain order, with the setup term simply absent when the session has none), and
**within a level by the memo's `sort_key`** (`data-model.md`), which the
roleplayer controls by dragging on the note wall (UC-076, US-102,
`workspace-shell.md`).

**Recorded here rather than left as a UI detail because reordering notes changes
what the model receives.** `sort_key` is the one mutable ordering in the schema
and exists for exactly this reason: the arrangement is an authoring act on the
prompt, not a display preference. An assembler that emits forced memos in `id`
order, or in whatever order the chain query happened to return, silently discards
the roleplayer's arrangement and builds a different prompt from the one the wall
shows.

### The `(( ))` convention is a system-prompt responsibility

R12 splits the double-parenthesis convention across three layers — the server
decides at settle, the client previews, and **the system prompt is what makes the
model honour the convention while text is still in the current zone.** That third
layer is owned here, in R12's two readings:

- **A wholly-parenthesised message is out-of-character** (US-129, UC-081). The
  model treats it as talk *about* the roleplay, not a line *in* it, and answers in
  kind rather than in prose.
- **A parenthesised fragment inside a draft is an instruction to act on**
  (US-130, UC-084): the model applies it to the surrounding prose and **must never
  reproduce the fragment itself**. The server strips it at settle, but only from
  the row being settled — a candidate that echoes the fragment back puts it into
  text the roleplayer then has to clean by hand.

The invariant these instructions live under is R12's: **parse once, at settle,
never re-parse stored text.** Nothing in this module classifies or strips
anything; the prompt tells the model how to *read* the convention in the zone,
and the one parser is `services/parens.py`, called from exactly one place
(`backend-structure.md`).

### Two facts that follow from mutability

- **Messages are read live.** A settled entry is editable forever and the
  assistant always reads the current version (UC-029, UC-078, US-110), so assembly
  reads `messages.text` through the selectables at request time and never caches a
  snapshot. The same holds for a current-zone message the roleplayer rewrote
  before sending again (US-115).
- **Forced memos are read live too.** A memo whose `is_enabled` or `is_forced`
  flips, or whose `sort_key` moves, takes effect on the next message in every
  session in its scope (UC-044, UC-045, UC-075, UC-076), with no invalidation
  step, because nothing was cached.
- **The sub-reads are separate reads, not one snapshot — accepted** (020 D11).
  Assembly composes the session, the character, the configuration, the memo chain
  and the two message lists through five read operations, so a concurrent write
  landing between two of them could in principle be reflected in one and not the
  other. It is accepted rather than wrapped in a transaction for a plain reason:
  the only writer in a single-roleplayer instance is the same person who is
  composing, the worst outcome is a prompt that is a fraction of a second old in
  one of its parts, and holding a read transaction open across the assembly would
  put a lock on the single-writer database in front of every generation.
  **Flip condition:** a concurrency target (`overview.md`'s `_TBD:`) or a second
  concurrent writer per session would make the snapshot worth its cost.

### Language handling

- **Candidates are always produced in the RP language** (UC-034, US-037),
  regardless of the language the roleplayer is currently writing in and regardless
  of whether the exchange around them is out-of-character. That instruction is
  part of the system prompt and is separate from the mirroring rule below.
- **The assistant mirrors the language of each message in the zone** (UC-033,
  US-036). There is **no fixed discussion language and none is stored** —
  `messages` has no language column (`data-model.md`), deliberately, because
  recording one would imply a setting that does not exist. Mirroring is a
  system-prompt instruction, not a detected-and-recorded state; the roleplayer may
  switch language message to message and the assistant keeps mirroring.
- **Out-of-character text is in the roleplayer's *preferred* language, not the RP
  language** (US-131), and the assistant answers OOC in kind. The two rules
  compose rather than conflict: the model mirrors the OOC message's language for
  the OOC reply, while a candidate produced in the same exchange is still in the
  RP language.
- **`kind='decision'` rows are therefore not RP-language, and are never
  translated** — a decision is already in the preferred language, so translating
  it is a model call that changes nothing. `data-model.md` and R8 record the
  narrowing (the guarantee covers `kind IN ('partner','turn')` only); it is cited,
  not restated.
- **"Context holds only the RP language"** means what R8 means by it: no
  *translation* ever enters context. It is a rule about the `translations` table,
  not a claim that every row in context is RP-language prose — which the decision
  and zone cases above make plainly untrue.
- **With no language resolved at any level, the instruction names English —
  `US-142`** (020 D4, U4). A null resolved RP language or a null resolved
  preferred language puts **English** in the instruction section, and **nothing is
  refused**: a session with no language configured still composes. This realizes
  the product's rule rather than deciding anything here, and `US-142`'s own
  wording is the part to keep: English is **a last resort, never a configured
  default**. Nothing writes it to a column, nothing shows it in a picker as a
  selection, and a level that sets a language is unaffected by it. (The same
  fallback governs translation's target — see the translation section.)

### No context compaction

Session context grows forever: no ceiling, no warning, no pruning. This is an
explicit **non-goal** (`vision.md`), knowingly chosen by the user over three bounded
alternatives, and nothing in the assembly above mitigates it.

**Confirmed as built** (020 D12): there is **no pruning, no summarisation, no
token count and no truncation anywhere in assembly** — the full record goes
through. Recorded as a positive assertion rather than left implied by the
non-goal, because "add a token budget" is the first thing a reader of a growing
prompt reaches for, and the absence is a decision with a product behind it.

**The `_TBD:` this section carried is closed — downgraded to a recorded non-goal,
not answered.** It asked what happens when a long RP exceeds what the model can
hold with nothing warning first. `docs/product/` has since stated that outcome as
the chosen one rather than as an unexamined gap: `vision.md`'s "No context
compaction" non-goal now says in its own words that "a long RP will eventually
exceed what the model can hold, nothing warns first, and the refusal surfaces as
an ordinary generation failure (US-044) whose reason is shown", and **FEAT-009**
and **FEAT-010** each restate it — "context is unbounded by choice — nothing warns
the roleplayer as a session grows". So it is decided, not open.

**The reasoning stays visible, because a planner still needs it.** What was a
question is now a recorded operational reality:

- A provider error caused by exceeding the context window arrives as
  `llm_unreachable` or a provider-specific failure, and the design contains **no
  special handling that distinguishes it**. Deliberate.
- An enormous *paste* warns about context cost (US-035.AC-1); the session's **own
  accumulated size never does**. The asymmetry is the product's, not an oversight
  in assembly.
- What the roleplayer sees at that point is US-044's failure notice with its
  reason — transient, five seconds, gone (US-044.AC-4, `ui-conventions.md`). That
  is the entire user-facing treatment of the ceiling, and it is enough only
  because the product says nothing more is wanted.

---

## Translation

**Realizes:** FEAT-011, UC-039, UC-040, UC-041

Translation uses the same `LlmClient` and the same resolve→validate→call path as
generation, against the session's resolved model, targeting the session's resolved
**preferred language** (R1's two-level chain).

**The route is not streamed, although it consumes the streaming client.** The two
facts sit together and are easy to read as a contradiction. A translation is a
whole-text replacement for a read-only flicker (UC-039), so partial output has no
use — the flicker either shows the translation or shows the original — and the
route answers **JSON**. Internally, as built, it **reuses `chat_stream` with no
tools** and **joins the content deltas**, ignoring reasoning and tool-call deltas
(023 D2, D8). Reusing the one client rather than adding a non-streaming call is
what keeps the provider surface at one function; the joining happens in the
service, so nothing downstream of it knows a stream was involved.

The request is **two messages**: one system message instructing a faithful
translation into the target language and **nothing but the translation** as
output, and the **stored text verbatim** as the user message. Verbatim because the
row is the record — normalising it on the way to the translator would translate
something the roleplayer cannot see.

- **Only settled rows are translatable**, and in practice only `kind='partner'`
  ones (R8): a current-zone message is not yet record, and a `kind='decision'` row
  is already in the preferred language (US-131).
- **The target falls back to English — `US-142`.** With no preferred language
  resolved at any level, the target is the literal `English`, held in **one
  constant in `services/translation.py`** (023 D3), and the **cache key uses the
  effective target** so a later configured language is a different key rather than
  a stale hit. This realizes the product's rule and is not a plan-time choice:
  English is a **last resort, never a configured default**, which is `US-142`'s
  own wording. The same fallback governs the prompt's language instruction
  (020 D4), so the two surfaces cannot disagree about what "no language" means.
- On **success**, the result is cached in `translations` keyed by
  **`(message_id, target_language)`** (UC-041, `data-model.md`), so the second look
  is instant. The key is a message id, not an entry id — `entries` no longer
  exists. The result is **`<think>`-stripped before caching** (023 D10 — the third
  strip site in the Thinking table above).
- **A cache hit resolves no model at all** (023 D8). Only a miss runs 017's
  use-time check, so **a cached translation still shows when the session's model
  has been disabled** — which is right rather than lenient: the work is already
  done, and refusing to show it would punish the roleplayer for an administrator's
  change to something the answer no longer needs.
- On **failure**, `translation_failed` is raised, the flicker falls back to the
  original text with a visible error, and **nothing is cached** (UC-039's exception
  flow). **The mapping is narrow** (023 D5): only a provider failure out of
  `chat_stream`, **or an empty result after the `<think>` strip**, becomes
  `translation_failed`. 017's model errors (`no_model_enabled`,
  `model_not_chosen`, `model_not_enabled`) and `secret_ref_missing` **propagate
  under their own codes**, because each of those is a configuration condition the
  roleplayer or the administrator can act on, and collapsing them into "the
  translation failed" would hide the remedy.
- **Three phases, and no connection or transaction is held across the provider
  await** (023 D8): read, call, write. The service takes the **engine** rather
  than a connection (the precedent is 021 step `005`), so it opens its own
  short-lived connections either side of the call. The reason is the single-writer
  database: holding a transaction open across a network round trip is what the
  embedding path pays for deliberately (`search-and-retrieval.md`) and what this
  path has no reason to.
- A cached row is discarded when the message's text changes — **on *any* settled
  entry's text change, not only a partner block** (`US-111`, `US-111.AC-3`,
  `data-model.md`).
- The translation never enters context (R8).

### Stopping a translation — best-effort, and explicitly not a guarantee

UC-085 and US-133 put a translation in flight within the stop's reach, and
**translation is the one place where an abort cannot deliver a guarantee**. The
reason is structural: the route is **not streamed** (above) — it answers JSON —
so aborting the `fetch()` stops the *client* waiting, while the server handler
runs to completion, gets its result and writes the `translations` cache row.
There is no open stream whose closure the handler is already watching.

What is specified:

- A **best-effort disconnect check immediately before the cache write.** If the
  client is already gone, the row is not written and the handler returns. **As
  built** (023 D4) the probe is **injected into the FastAPI-free service as an
  async callable** and awaited **once**, at that one point — which is how a
  service that may not import `fastapi` gets to ask a question only the request
  object can answer, without the service learning what a `Request` is.
- **The log line records the outcome**: the translate line gains
  **` written=false`** when the write is skipped (`deployment.md`'s allowed
  shapes). Without it, a skipped write and a cache miss look identical in the log,
  which is the one thing anybody investigating this path wants to tell apart.
- **It is best-effort and it is not a guarantee.** The check samples the
  connection at one instant; the disconnect can land between the check and the
  write, and the write still happens. Stated as a non-guarantee rather than
  described in a way that reads like one.

**`US-133.AC-2`'s "nothing is cached" therefore holds usually and not always, and
the criterion says so** — its `Constraint:` line records the best-effort nature,
so this is a stated limit on a settled requirement rather than a divergence from
one (see "Stopping, and what a stop is not" above). The alternatives were
considered and rejected: a transaction spanning the model call would hold a write
lock on the single-writer SQLite file for the duration of a network round trip,
and a delete-after-the-fact compensating write is a second code path to get a
cache row into and back out of existence for a case the roleplayer will not
notice — a stale cache entry for text they asked to translate and then stopped
is, at worst, a translation they get instantly next time.

The **user-visible** half of US-133.AC-2 does hold unconditionally: the original
text stands. Nothing about the flicker's rendering depends on whether the row
landed.

**The control that performs this stop is the flicker's own, not the composer's**
(023 D4, user decision). While a translation is pending, the flicker reads
"Cancel translation" and cancelling it is what triggers the check above; the
composer's `IconPlayerStop` governs a compose exchange and does not reach here.
Two controls because the two cancellations are different mechanisms with
different guarantees — an `abort()` on a live stream versus a best-effort sample
before a write — and one control over both would promise the stream's behaviour
for a request that cannot provide it.
