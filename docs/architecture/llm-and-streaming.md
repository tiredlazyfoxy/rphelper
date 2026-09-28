# LLM integration and streaming

**Realizes:** FEAT-004, FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013,
FEAT-014, FEAT-015, FEAT-016, ACT-004, UC-010..UC-013, UC-032..UC-038, UC-045,
UC-051, UC-053, UC-055..UC-057, UC-081, UC-083, UC-084

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

### The model registry and use-time validation

**Realizes:** FEAT-004, FEAT-013, UC-012, UC-050 — see `domain-rules.md` R4

The request path for every generation is exactly three steps, in this order:

```
1. resolve   config_resolver → a model REFERENCE (user → character → session)
2. validate  llm_registry    → is that reference an enabled model right now?
3. call      LlmClient       → chat_stream
```

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
results rather than an error. See `search-and-retrieval.md`.

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

- **`done` is mandatory on success.** A stream that closes without it is treated as
  `llm_unreachable` by the client. Silence is never success.
- **`error` and `done` are mutually exclusive and terminal.** Exactly one of them
  ends every stream.
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
  `user → character → session` chain, R1). A disabled tool is **not offered to the
  model** — it is absent from the tool list, not present-and-refused. A tool the
  model cannot see cannot be attempted, which is a cheaper and more honest
  enforcement than rejecting the call.
- **Every tool dispatch is a scoped read** carrying the authenticated `user_id`,
  and `session_search` additionally carries `character_id` (UC-054). The assistant
  has no other database path (R9), which is what makes FEAT-019's isolation
  enforceable at three points rather than everywhere.
- **The assistant never writes into the record.** No tool mutates anything, and a
  candidate lands in the **current zone** and nowhere else (UC-035, R11) — where
  the roleplayer may rewrite it in place, the assistant's text included (US-115),
  and must **settle** it for it to become record (US-126). The only other door
  into the record is a pasted partner block, which is born settled (US-121).
- `_TBD: no iteration cap is stated in docs/product/. A bounded number of tool
  rounds per exchange is an implementation necessity — an unbounded loop can spin —
  but no limit is specified, so the plan that builds FEAT-010 must choose one and
  record it. Note that a cap is a loop guard, not context compaction, which is a
  non-goal (overview.md)._`

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
system prompt  = resolved system_prompt (R1: user → character → session)
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

`_TBD: a long RP will eventually exceed what the model can hold, and nothing warns
the roleplayer first — carried from vision.md's non-goals and FEAT-009/FEAT-010's
own _TBD:. An enormous paste warns about context cost (US-035.AC-1) but the
session's own accumulated size does not._`

Note what this means concretely for anyone building FEAT-010: a provider error
caused by exceeding the context window arrives as `llm_unreachable` or a
provider-specific failure, and the design contains no special handling that
distinguishes it. That is a consequence of the non-goal, recorded rather than
quietly fixed.

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
