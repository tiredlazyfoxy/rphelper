# LLM integration and streaming

**Realizes:** FEAT-004, FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013,
FEAT-014, FEAT-015, FEAT-016, ACT-004, UC-010..UC-013, UC-032..UC-038, UC-045,
UC-051, UC-053, UC-055..UC-057, UC-081, UC-083, UC-084, UC-085,
US-132, US-133

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

- **FEAT-004 builds construction, `probe()` and `embed()`. `chat_stream` is not
  stubbed** — a stub with no caller is dead code FEAT-009/010 would rewrite.
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

### The model registry and use-time validation

**Realizes:** FEAT-004, FEAT-013, UC-012, UC-050 — see `domain-rules.md` R4

The request path for every generation is exactly three steps, in this order:

```
1. read      sessions.model_ref → the model REFERENCE captured at session creation
2. validate  llm_registry       → is that reference an enabled model right now?
3. call      LlmClient          → chat_stream
```

- **Step 1 is a read, not a resolution.** The model reference was resolved once,
  through `character → session`, **when the session was created**, and written
  onto `sessions.model_ref` (R4, `data-model.md`). The request path does not
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

**Both use-time validators ship with no call site, and that is expected** (plan
006). They live in `services/llm_registry.py` and were built by FEAT-004 with no
consumer — sessions arrive with FEAT-008/FEAT-013's features and embeddings with
FEAT-014/015's — so they are covered by tests against the service rather than
through a session. This is **not an unfinished path**; do not "fix" the missing
end-to-end test by wiring a premature call site. The model validator takes the
**server id and the model name as two plain arguments**, so the encoding of
`sessions.model_ref` stays with the feature that writes it (`data-model.md`'s
`_TBD:`).

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
| `accepted` | the roleplayer's own message is committed to the zone; emitted **once, before the first `token`** | adopt `message_id` for the message just sent, so an in-place edit of it can `PATCH` without waiting for a reload |
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
  per emit call.

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

### Named divergences from `docs/product/` — pending amendment

Two acceptance criteria will **not** match what gets built. This is known and
accepted, and it is recorded here rather than designed around, because designing
to the AC as written would produce either a stop registry or a guarantee the
transport cannot make.

- **US-133.AC-1** — "Given the assistant is waiting on a tool call, when the
  roleplayer stops it, then the discussion continues without that tool's result."
  **It will not continue.** Consequence 4 above: the exchange ends, because the
  stop closes the connection the continuation would have streamed over. The AC
  reads the stop as behaving like a *failed* tool (R9, where the exchange genuinely
  does continue); the two differ precisely in that a failed tool leaves the socket
  open and a stop does not.
- **US-133.AC-2** — "the original text stands and nothing is cached."
  **"Nothing is cached" is best-effort only**, not a guarantee. See the
  translation section below for the mechanism and why.

**Both are pending amendment by `/product-spec`.** `docs/product/` is not edited
here and neither AC is silently reinterpreted; a plan that binds to either as
written will produce a test that cannot pass. Named by id so the amendment
request is unambiguous.

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
- **Tool availability comes from the resolved configuration** (FEAT-013's
  `character → session` chain, R1 — **not** `user → character → session`, which
  is the corrected chain), resolved **live on every request** like the system
  prompt and unlike the model. A disabled tool is **not offered to the model** —
  it is absent from the tool list, not present-and-refused. A tool the model
  cannot see cannot be attempted, which is a cheaper and more honest enforcement
  than rejecting the call.
- **Every tool dispatch is a scoped read** carrying the authenticated `user_id`,
  and `session_search` additionally carries `character_id` (UC-054). The assistant
  has no other database path (R9), which is what makes FEAT-019's isolation
  enforceable at three points rather than everywhere.
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

### `web_search` — seam now, adapter deferred

FEAT-016 is last in the dependency graph. What is specified now:

- Its **tool definition** and its place in the loop, identical in shape to the other
  two.
- Its **switch** in the configuration chain (FEAT-013/UC-048, UC-049) — it is
  disabled like any other tool.
- Its **failure behaviour** — `tool_fail`, the exchange continues.
- Its three justified uses, recorded so the tool description given to the model
  matches the product: a real-world fact; an idiom or naturalness check; a direct,
  roleplayer-initiated lookup (FEAT-016, challenge C2).

What is **not** specified: the provider adapter. `_TBD: no search provider is
chosen; docs/product/ names none. The adapter is deferred to FEAT-016's plan
(overview.md)._`

---

## Context assembly — what the assistant reads

**Realizes:** FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013, UC-029, UC-034,
UC-038, UC-045, UC-081, UC-083, UC-084

ACT-004 "consumes forced memos and the session's settled entries" (`actors.md`,
R9). That is the whole list, and it is a closed list.

```
system prompt  = resolved system_prompt (R1: character → session, LIVE —
                   no user level exists; not captured at creation, unlike
                   the model, which is read from sessions.model_ref)
               + character sheet
               + FORCED memos: is_enabled AND is_forced over the resolved chain
                 (R2/R3, UC-045), ordered — see below
               + RP-language instruction (resolved rp_language, R1: user → session)
               + the (( )) reading instruction (R12, US-129, US-130)
               + tool descriptions for ENABLED tools only

messages       = settled_entries ∪ current_zone   for this session,
                 ORDER BY id                      (data-model.md's two views)
```

### The message list is the union of the two views

The three-table shape this doc used to describe is gone: `entries`, `discussions`
and `discussion_messages` merged into one `messages` table, and **`discussions` no
longer exists** (`data-model.md`). Assembly now reads the **`settled_entries`**
view unioned with the **`current_zone`** view, both scoped to the session and
ordered by `id` — a snowflake is k-sortable, so `ORDER BY id` *is* stream order
and there is no `position` column to consult.

**Buried rows are excluded by construction, not by a predicate this module
writes.** That is the whole purpose of the two views: the merge converted a
missing join into a `WHERE` clause, and the views put that clause in exactly one
place (`data-model.md`, R11). Assembly therefore names **no** table — a query here
selecting from raw `messages` is a defect, and R11 says the same from the other
side: settle and re-open are the only two operations that touch it.

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
| Buried rows | a settled group's scaffolding never reaches the assistant again, then or later (UC-038, R7) — excluded by the `settled_entries` / `current_zone` views rather than by a predicate here (R11) |
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
  reads `messages.text` through the views at request time and never caches a
  snapshot. The same holds for a current-zone message the roleplayer rewrote
  before sending again (US-115).
- **Forced memos are read live too.** A memo whose `is_enabled` or `is_forced`
  flips, or whose `sort_key` moves, takes effect on the next message in every
  session in its scope (UC-044, UC-045, UC-075, UC-076), with no invalidation
  step, because nothing was cached.

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

### No context compaction

Session context grows forever: no ceiling, no warning, no pruning. This is an
explicit **non-goal** (`vision.md`), knowingly chosen by the user over three bounded
alternatives, and nothing in the assembly above mitigates it.

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

It is **not streamed**. A translation is a whole-text replacement for a
read-only flicker (UC-039), so partial output has no use — the flicker either shows
the translation or shows the original.

- **Only settled rows are translatable**, and in practice only `kind='partner'`
  ones (R8): a current-zone message is not yet record, and a `kind='decision'` row
  is already in the preferred language (US-131).
- On **success**, the result is cached in `translations` keyed by
  **`(message_id, target_language)`** (UC-041, `data-model.md`), so the second look
  is instant. The key is a message id, not an entry id — `entries` no longer
  exists.
- On **failure**, `translation_failed` is raised, the flicker falls back to the
  original text with a visible error, and **nothing is cached** (UC-039's exception
  flow).
- A cached row is discarded when the message's text changes (US-111,
  `data-model.md`).
- The translation never enters context (R8).

### Stopping a translation — best-effort, and explicitly not a guarantee

UC-085 and US-133 put a translation in flight within the stop's reach, and
**translation is the one place where the abort mechanism cannot deliver what the
AC asks for**. The reason is structural: translation is **not streamed** (above) —
it is a plain JSON request — so aborting the `fetch()` stops the *client*
waiting, while the server handler runs to completion, gets its result and writes
the `translations` cache row. There is no open stream whose closure the handler is
already watching.

What is specified:

- A **best-effort `await request.is_disconnected()` check immediately before the
  cache write.** If the client is already gone, the row is not written and the
  handler returns.
- **It is best-effort and it is not a guarantee.** The check samples the
  connection at one instant; the disconnect can land between the check and the
  write, and the write still happens. Stated as a non-guarantee rather than
  described in a way that reads like one.

**US-133.AC-2's "nothing is cached" therefore holds usually and not always**, and
that divergence is named above with the other one, pending amendment by
`/product-spec`. The alternatives were considered and rejected: a transaction
spanning the model call would hold a write lock on the single-writer SQLite file
for the duration of a network round trip, and a delete-after-the-fact compensating
write is a second code path to get a cache row into and back out of existence for
a case the roleplayer will not notice — a stale cache entry for text they asked to
translate and then stopped is, at worst, a translation they get instantly next
time.

The **user-visible** half of US-133.AC-2 does hold unconditionally: the original
text stands. Nothing about the flicker's rendering depends on whether the row
landed.
