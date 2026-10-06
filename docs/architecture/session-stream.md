# Session stream — the zone, settle, compose and the tool seam

**Realizes:** FEAT-008, FEAT-009, FEAT-010, FEAT-013, FEAT-014, FEAT-015,
FEAT-016, FEAT-019, UC-027, UC-028, UC-029, UC-031, UC-032, UC-033, UC-034,
UC-035, UC-036, UC-037, UC-038, UC-078, UC-079, UC-080, UC-081, UC-082,
UC-083, UC-084, UC-085, UC-086, US-030, US-031, US-032, US-034, US-035,
US-037, US-038, US-039, US-040, US-041, US-042, US-043, US-044, US-109,
US-110, US-113, US-114, US-115, US-116, US-117, US-120, US-121, US-122,
US-125, US-126, US-127, US-128, US-129, US-130, US-131, US-132, US-134,
US-135, US-146

The backend behaviour of one session's stream: the record above the ruler, the
current zone below it, settle and re-open, the `(( ))` seam, the compose loop
with its streaming harness, the tool seam the three tools plug into, and the
buried-discussion read. This is the backend counterpart to `workspace-shell.md`,
which owns the one screen these routes serve.

Split out of `backend-structure.md` at the finalization of plans 008..032,
because that doc had come to carry two subjects: the FastAPI application's shape,
and the session stream's behaviour. `backend-structure.md` keeps the application
shape — layout, the routers/services split, the JSON id boundary, configuration,
secrets, the error model and the per-code status record — and is where the codes
raised here are defined. `llm-and-streaming.md` owns the SSE frame protocol, the
prompt, context assembly and the tool-calling loop's protocol detail; this doc
owns the routes, the transactions and the seams.

## The route surface — FEAT-009 and FEAT-010 in one router

One table, four named selectables, one router (`routers/stream.py`). The merge in
`data-model.md` removed the surface the old two routers were named after: **the
`discussions` table is gone, so there is no discussion id to address**, and the
current zone has no id of its own either — it is the *set* of a session's
messages matching `related_to IS NULL AND settled_at IS NULL` (R11), and a set is
not addressable. Every zone operation is therefore addressed **through its
session**, and the route shape follows the selectables exactly:

| Route | Does | Touches |
|---|---|---|
| `GET /api/sessions/{id}/entries` | the record above the ruler → `{ entries: [...] }` | `settled_entries`, `ORDER BY id` |
| `POST /api/sessions/{id}/entries` | file a pasted partner block, born settled (US-121) → **201** | one insert, `settled_at` set at insert |
| `GET /api/sessions/{id}/zone` | the live zone below the ruler → `{ messages: [...] }` | `current_zone`, `ORDER BY id` |
| `POST /api/sessions/{id}/zone/messages` | append one message; **no model call** → **201** | one insert |
| `POST /api/sessions/{id}/zone/compose` | append the roleplayer's message, then **stream** the assistant's reply | SSE; "The compose route" below |
| `POST /api/sessions/{id}/settle` | settle the zone (R11, R12) → `{ entry_id, kind, buried_ids, search_coverage_incomplete }` | `services/settle.py` |
| `POST /api/sessions/{id}/reopen` | settle's exact inverse (R11) → `{ reopened_id, restored_ids, search_coverage_incomplete }` | `services/settle.py` |
| `PATCH /api/messages/{message_id}` | edit one message's text in place | one update |
| `GET /api/messages/{message_id}/discussion` | a settled entry's buried group, read-only → `{ messages: [...] }` | `buried_messages`, ascending by id |
| `POST /api/characters/{character_id}/sessions` | create a session under the character **and**, when an opening message is supplied, seed its zone, in one transaction (UC-080, US-117) | `services/sessions.py`; owned by `routers/sessions.py` |

**The table is complete.** There is no stop route and no discard route; the
reasons are below, under "The compose route" and R11 respectively.

**The wire shape.** `MessageResponse` carries **twelve keys**, which arrived from
three plans for three different reasons — the structure is kept visible here
because a reader counting them will otherwise assume one decision:

- **The eight message fields** of plan 012: no `user_id`, no `related_to`, no raw
  tool columns.
- **Three tool fields** — `tool_name`, `tool_status` (`ok` / `failed`) and
  `tool_args` (the call's arguments as a JSON object, `{}` when unreadable) — all
  **null on a non-tool row**. **This supersedes plan 021's "tool columns are not
  on the wire"** (021 D7): plan 022 needed them to render a tool block, and the
  derivation lives in `services/messages.py` (022 D3). `tool_payload`, the
  provider's `call_id` and the raw tool content never leave the backend — the
  wire carries a *view* of the payload, not the payload.
- **The coverage flag**, `search_coverage_incomplete: bool` (plan 024), **false
  for zone rows and plain appends**. It is the degraded-embedding signal ("The
  degraded embedding path", below) and it rides on `SettleResponse`,
  `ReopenResponse` and the `PATCH` response alike, so every record-keeping write
  reports it in its own response.

Every route on `routers/stream.py` is behind router-level `require_user`, and
every service call takes `user_id` as a required positional argument. A message
id that does not exist and one belonging to another user answer **identically**
(`message_not_found`, 404) — refusal identity, R5.

### The decisions behind that shape

Each of these could have gone another way, so each carries its reason.

- **Settle and re-open take no target id.** R11 defines both structurally:
  settle takes *the last message in the zone* (US-126) and re-open applies to
  *the last settled row* — anything earlier has entries after it and is refused
  by definition (UC-037). The rejected alternative was
  `POST /api/entries/{message_id}/reopen`, matching where the control sits in the
  UI (`workspace-shell.md`). It was rejected because it lets a client name a row
  that is *not* the structural target, which turns an invariant the schema
  guarantees into a condition the server has to re-check and a client can get
  wrong. Session-addressed, the request cannot express an illegal target at all.
  Both responses return the ids the operation moved, and **nothing else** — the
  client re-reads both lists afterwards (012 D11), which is
  `ui-conventions.md`'s never-optimistic re-load rule applying normally.
- **Two appends, not one route with a `reply: bool`.** UC-028/US-031 require text
  to reach the record with no model call at all, and UC-032/UC-034 require the
  streaming exchange. One route serving both would make the **response media
  type depend on a request field** — and the client picks its SSE reader or its
  JSON error renderer *before* the response arrives (`frontend-structure.md`).
  Two routes, two contracts, one media type each. That the composer's Send may
  map onto either is a UI decision, not a transport one; `docs/product/` does not
  describe the composer's send semantics beyond UC-028, so the split is recorded
  as a design inference (decided in plan 012) rather than a read of a
  requirement.
- **A pasted partner block never passes through the zone** (US-121). It is born
  settled, and `POST /api/sessions/{id}/entries` is the only route that may
  create a settled row without settling. As built in plan 012 its `kind` is
  **required and must be exactly `"partner"`** — every other value is a native
  422 — which is R11's single exception enforced at the router boundary rather
  than trusted to a caller. It runs no `(( ))` parsing (R12) and returns JSON;
  there is nothing to stream for text the roleplayer did not compose. **There is
  no zone precondition on filing one** (012 D14, user decision): a partner block
  may be filed while the zone holds a draft, and the ordering consequence of that
  is recorded in `data-model.md` under `position`.
- **`text` is required and non-blank, stored verbatim, with no maximum length**
  (012 D9). R10 and US-035.AC-2 forbid refusing an enormous paste, so no layer of
  the stack may introduce a length ceiling; the only warning is the client-side
  context-cost notice (R10).

### `PATCH /api/messages/{message_id}` — the final reach

**One operation on one column, spanning the record and the zone on purpose.** As
built after plans 012, 014 and 021 the rule is settled and is stated once here,
with no interim qualifier:

| Target row | Outcome |
|---|---|
| a settled row, **any** kind — `partner`, `turn` or `decision` | edited; `text` and `updated_at` only. `kind`, `settled_at` and `related_to` are never written. Read back through `settled_entries` |
| a current-zone row, including the assistant's | edited; read back through `current_zone` |
| a **buried** row | refused — `message_not_editable` |
| a `role='tool'` row | refused — `message_not_editable` |
| a missing id, or another user's | refused — `message_not_found` (404) |

The service classifies the target through the text-free `message_states`
selectable, so it can tell a buried row from a missing one without a raw
`select()` on `messages` (012 D7). Every accepted edit bumps the session
(`last_used_at` and `updated_at`) in the same transaction (014 D1, D2).

A settled row is editable forever (UC-078, US-110) and a zone message is editable
in place including the assistant's (US-115); it is the same operation on the same
column, which is why it is one route. **`message_not_editable` therefore means
exactly two things — a buried row (US-116) and a tool row** — and nothing else.
Plan 014 removed the settled case it had shipped as an interim; plan 021 added
the tool case, **deliberately and with a reason**: a tool row's `text` is a
*summary the server wrote of the tool's own payload*, not prose anyone composed,
so editing it would desynchronise the summary from `tool_payload` while changing
nothing the model reads (021 D8). This now realizes `US-115.AC-1`'s `Constraint:`
line, which states that a tool's own record is not a message anyone wrote and is
not editable. It is a narrowing of "whoever wrote it" that the product has since
ratified, not a slip.

An assistant zone row is edited as **raw stored text, `<think>` tags included**
(022 D10); the server strips them at settle, not at edit ("Settle", below).

**The live reply, while it is still streaming, carries no edit control** — and
that is **defect D-02**, not a design decision this doc endorses.
`US-115.AC-1` requires any message in the current zone to be editable in place.
As built (022 D6, from user decision U4), the in-flight reply renders read-only
beneath the zone rows and only the persisted row — after the post-stream zone
re-read — is editable. The reason given is real rather than an oversight: an edit
would race the server's own write of that row (019 D11), and exposing the editor
without resolving that race loses or clobbers text. `docs/plans/defects.md` D-02
is the record, and it carries an **open alternative reading**: US-115.AC-1 is
conditioned on a message *sitting in* the current zone, which an unpersisted
in-flight reply is not — on that reading D-02 is a clarification to the criterion
rather than a defect. That reading is recorded here, not resolved.

### Starting a session by writing — one route, one transaction

It is the only row in the table not addressed through a session, because when the
request is made there is **no session to address**: UC-080 puts a composer on the
character's page (`workspace-shell.md`), and the first message written there
creates the session and becomes the opening message of the turn being drafted.

The body is omitted, `{}`, or `{ setup_id?, opening_message? }`. It answers
**201 `StartedSession`** — the eight `Session` keys plus `opening_message`, which
is a `MessageResponse` when one was sent and null exactly when none was (018).
A whitespace-only `opening_message` is a **422** and nothing is created.

**US-117.AC-1 makes creating the session and seeding its zone a single outcome**,
so they are a single `with connection.begin():` in `services/sessions.py`, in
this order (018 D3, 017 D1):

1. the owner-scoped parent check on the character, and the setup check when a
   `setup_id` was supplied — the setup must be the caller's, under that character
   (404 `setup_not_found`) and **not archived** (409 `setup_archived`); an
   archived *character* is allowed;
2. mint the session id;
3. **capture the model** — the character's `(model_server_id, model_name)` pair
   as configured at that instant, unvalidated; otherwise the first enabled model
   in the instance's order; otherwise **both columns NULL** (R4, US-143);
4. insert the `sessions` row;
5. insert the opening message as a current-zone `role='user'` row with the
   **same** timestamp.

A failure in the message insert leaves **no session** (018 D3). The rejected
alternative was leaving the client to call a create route and then
`POST /api/sessions/{id}/zone/messages`: two round trips that can fail between,
stranding an empty session under the character that the roleplayer never asked
for and now has to archive by hand. A partial failure the *user* has to clean up
is worse than a request that failed.

**It is character-addressed, and it creates nothing settled.** The path is
`/api/characters/{character_id}/sessions` because the character is the only
entity that exists at request time. It is owned by `routers/sessions.py`
(FEAT-008) rather than `characters.py` — routers here group by feature, not by
path prefix, which is the same reason `routers/stream.py` owns
`PATCH /api/messages/{message_id}`. The seeded message lands in the **current
zone** and is never settled: UC-080's "opening message of that turn's discussion"
*is* a zone row, inserted through the same transaction-neutral zone-insert helper
the stream's append uses (018 D3), so R11's "settle is the only door into the
record" is untouched and this route is not a second exception beside the pasted
partner block. When no `setup_id` is supplied the session is created with
`setup_id` NULL — UC-080 names no setup, and R2 makes that the first-class case
rather than a degraded one.

**The opening message draws no assistant reply, and that is defect D-01.**
The design question is **closed**: `US-117.AC-3` and UC-080 step 5 require the
assistant to answer that message as it would any other discussion message, and
the route **stays JSON** because the compose happens on the session once it
exists (018 D2) — so the media type does not change and no second contract is
needed. What is missing is the trigger. Plan 018 shipped the JSON, no-model-call
route and deferred the reply; no later plan took it. See
`docs/plans/defects.md` D-01 for what a fix must settle. Nothing in this doc
should be read as describing a reply that exists.

## Settle and re-open — one transaction each, one module

**Realizes:** FEAT-010, UC-035, UC-036, UC-037, UC-081, UC-084, US-126, US-128,
US-135, US-146

`services/settle.py` holds **both** operations and nothing else. R11 states that
the burial and settle columns on `messages` are written by exactly two
operations; keeping those two in one module turns that rule into a grep. It
imports no other service, and no other service imports it (012 D11).

**Settle**, entirely inside one `with conn.begin():`

1. Read the zone through `current_zone`; take the **last non-tool row** by id
   (US-126). An empty zone raises `zone_empty` — and **a zone holding only
   `role='tool'` rows counts as empty** and raises the same (021 D8).
   **That is the only precondition.** In particular there is **no requirement
   that the assistant has answered**: a zone holding only the roleplayer's own
   message settles that text as-is (US-135, UC-083 step 5 — "the last message in
   the current zone, **whoever wrote it**"). A check for an assistant row here
   would be a defect, and it is the kind of check that arrives disguised as
   validation.
2. When the head's `role` is `assistant`, strip `<think>` … `</think>` blocks
   (`services/llm/chat.strip_think`) **before** anything else. A user head is
   never think-stripped. This realizes `US-146` — the assistant's thinking never
   enters the settled record. A head whose stripped text is empty **still
   settles**; no refusal was invented for it, and surfacing it before settle is
   `workspace-shell.md`'s open candidate rather than a server rule.
3. Classify and strip through `services/parens.py` (R12): wholly parenthesised →
   `kind='decision'`, otherwise `kind='turn'` with any `(( ))` fragment removed
   from the head row's text.
4. `UPDATE messages SET related_to = <head id>` for every other zone row — bury
   the group. **Tool rows are buried with the group as scaffolding**, exactly
   like any other non-head zone row (021 D8).
5. `UPDATE messages SET settled_at, kind, text` on the head row.
6. Refresh `session_vec` (`search-and-retrieval.md`). **Built by plan 024**, not
   by plan 012 — no vector or FTS table existed before then — and it runs inside
   this same transaction, under the degraded path below.

**Step 4 precedes step 5 and the order is load-bearing.** The burial predicate is
zone membership; once the head carries `settled_at` it is no longer in the zone,
and the set the burial is supposed to sweep no longer identifies itself. Two
UPDATEs and no INSERT — the settled text is the text already in the row
(`data-model.md`). The burial is driven by the **id list read from `current_zone`
in the same transaction**, so nothing re-derives the set (012 D10).

**Why the head excludes tool rows, named as deliberate so it is not "simplified"
back.** A tool row is scaffolding the server wrote, not a candidate anyone
composed; if it were eligible to be the head, a tool call that happened to land
last would become the settled record of the turn, and the roleplayer's own
candidate would be buried under it. The matching client rule — `canSettle` and
the settle preview count non-tool rows only — is in `workspace-shell.md`
(022 D9), and client and server agree on the head by construction.

**Re-open** is the mirror, also one transaction, in this order (012 D10):

1. resolve the session, owner-scoped;
2. the current zone must be **empty** (R11, US-128) — otherwise `zone_not_empty`;
3. take the last settled row by id;
4. no settled row at all, **or** a last settled row with no buried group, raises
   `nothing_to_reopen`;
5. `related_to` back to NULL for the group, `settled_at` and `kind` back to NULL
   on the head;
6. refresh `session_vec` (plan 024).

**The `nothing_to_reopen` cases are R11's own rule, not guards this module
invented**, and all three are explicit (user decision at plan 012, 012 D10): a
pasted partner block, a **lone directly-settled turn** and a **lone decision**
are each a settled head with nothing behind it, so there is no discussion to
re-open and nothing the inverse could restore. Read literally, step 5 would clear
`settled_at` on such a head and silently demote record back into draft, which no
requirement permits. Any earlier group is refused for the same structural
reason once a later row is settled.

Ids never move, so a settle/re-open round trip leaves the stream exactly as it
started, which is what makes it safe as an undo. **The pre-strip `(( ))` text is
not restored on re-open** (012 D10, R12) — it was never stored, and a revision
table does not exist.

Neither operation may commit partially: a buried group whose head was never
flagged is a session with no record and no zone. This is one of the reasons the
persistence layer is SQLAlchemy Core (`backend-structure.md`) — the transaction
boundary is a block in this module, not a flush the ORM schedules.

Both operations bump `sessions.last_used_at` **and** `updated_at` to the
operation's instant, in the same transaction; a refused operation writes nothing
(012 D3).

### The degraded embedding path

Settle, re-open and an accepted `PATCH` are **record-keeping** writes, and
US-112 is explicit that a platform-level embedding gap must never block the
roleplayer's own record-keeping. So the `session_vec` refresh in step 6 is
wrapped: `no_embedding_model` (including the dimension-mismatch form) and
`llm_unreachable` are **caught**, the relational write commits, and the response
carries `search_coverage_incomplete: true` (024 U3, D8). The asymmetry with memo
writes, which fail the whole transaction, is deliberate and is stated in
`backend-structure.md`'s "two transaction rules" and `search-and-retrieval.md`.

Two defects live on this path, and both are recorded rather than designed
around:

- **`secret_ref_missing` is not caught — defect D-03.** The built catch set is
  `no_embedding_model` and `llm_unreachable` only, so an unset `$ENV_VAR` key on
  the designated server makes a settle or a settled edit fail with a **500** and
  refuses the roleplayer's own text. `US-112.AC-1` was widened at the 2026-10-06
  product finalization to cover "credentials the instance cannot use", so the
  built behaviour does not satisfy it. See `docs/plans/defects.md` D-03.
- **A failed degraded embed leaves any existing `session_vec` row stale —
  defect D-04.** There is **no staleness marker and no staleness column**
  (024 U5), and the recorded remedy is the whole-index rebuild (UC-016). The
  design question of *whether to mark* is answered — no — but `US-112.AC-3`, new
  at the same finalization, requires the material's existing vectors to be
  **cleared** rather than left in place. The build leaves them. See
  `docs/plans/defects.md` D-04, which also records the accepted consequence of
  the fix: material that could not be embedded drops out of semantic search
  entirely until the rebuild.

## The `(( ))` seam — one parser, server-side, at settle only

**Realizes:** FEAT-009, FEAT-010, UC-081, UC-084, US-129, US-130, US-131

`services/parens.py`. Two pure functions, no I/O, no `user_id`, no connection:

```
classify(text)        -> "decision" | "turn"
strip_fragments(text) -> str
```

It is called from **exactly one place: step 3 of settle**, and is imported by
`services/settle.py` alone. R12 splits the responsibility three ways — the server
decides, the system prompt tells the model how to read the convention, the client
previews — and only the server's half is code in this backend. The rule is cited,
not restated; what belongs here is the exact boundary the client's preview must
match (012 D8, user decision on the classifier):

- **A message is a decision iff, after trimming outer whitespace, its text
  starts with `((` and ends with `))`.** It is then filed **verbatim**. The
  accepted consequence: `((a)) prose ((b))` is a decision, carrying the prose
  between the fragments.
- Otherwise it is a **turn**, and every fragment — the shortest `((`…`))` span —
  is removed **together with the spaces and tabs before it**; runs of three or
  more line breaks collapse to one blank line; the ends are trimmed.
- **A fragment-free turn is filed byte-for-byte.** Nothing normalises text that
  held no fragment.
- **A turn can never strip to empty**, malformed input included. Text that would
  strip to nothing necessarily starts with `((` and ends with `))` once trimmed,
  so it is a decision instead; an unbalanced `((` or a stray parenthesis survives
  stripping unchanged.

The invariant this doc owns: **stored text is never re-parsed.** `PATCH
/api/messages/{message_id}` takes the new text literally and does **not** call
this module, on a settled row or a zone row; re-parsing a later edit would
silently delete prose a roleplayer deliberately parenthesised. Nor does
`POST /api/sessions/{id}/entries` call it — partner text gets no special
treatment (US-121). The pre-strip text is not preserved anywhere; there is no
revision table (`data-model.md`).

A pure module rather than a method on the settle service so the classification
and stripping cases are testable from the spec with no database at all, which is
what the pipeline's test-coder needs.

## The compose route and the streaming harness

**Realizes:** FEAT-010, FEAT-013, UC-032, UC-034, UC-079, UC-085, US-037,
US-044, US-107, US-132, US-144

`POST /api/sessions/{id}/zone/compose` is the one streaming route, mounted by
plan 021 (plan 019 built the harness and **mounted no route**, leaving
`routers/stream.py` untouched). Its handler is two phases:

1. **`begin_compose`** — synchronous, before anything streams. With text, it
   appends the roleplayer's zone row through `append_message` and **commits**
   (R10). Textless — the retry — it performs the ownership check and the
   `zone_empty` check (no non-tool zone row → `zone_empty`, as JSON, before any
   stream opens) and **inserts nothing**.
2. **the harness** —
   `sse_response(request, compose_stream(...), own_connection_persister(get_engine(settings), generator, user_id, session_id))`.

The response is `StreamingResponse(media_type="text/event-stream")` with
**`X-Accel-Buffering: no`** set by the application, deliberately, rather than
relying only on nginx's `proxy_buffering off` (`deployment.md`). The request is a
**POST with a JSON body** — `{ text? }`, where absent or null means retry and a
blank string is a 422 — which is why the client is `fetch()` +
`body.getReader()` rather than `EventSource` (`overview.md`,
`frontend-structure.md`). The chat-client factory and the tool registry are two
**overridable FastAPI dependencies** declared in `routers/stream.py` (021 D1, D2,
D14).

### The harness contract — `services/llm/frames.py`

The harness lives beside the frame types rather than in a module of its own
(019 D1). Its three pieces:

- `frame_stream` / `sse_response(request, source, persister)` — `request` is used
  **only** for `is_disconnected()`; `source` is an async iterator of frame
  *values*, never strings; `persister` is a **synchronous** callable taking the
  partial text.
- `own_connection_persister(engine, generator, user_id, session_id)` — writes the
  partial assistant row on the harness's **own short-lived connection** from
  `get_engine(settings)`, never the request-scoped `get_connection`, whose
  teardown relative to body iteration is unverified for the installed FastAPI
  (019 D7). A persist failure is logged — ids and exception class only — and
  swallowed.
- `append_assistant_message(connection, generator, user_id, session_id, text)` in
  `services/messages.py` — `role='assistant'`, `kind` NULL, the same ownership
  check and session bump as `append_message` (019 D8). **The partial-row write is
  the same write the success path performs**, not a special one; the only
  difference is that no `done` frame reports its id.

Four route-level ordering rules:

1. **The roleplayer's message is committed before the stream opens** (R10), so
   `llm_unreachable` cannot lose typed text. The use-time model check runs
   *inside* the stream, after `accepted`, so `no_model_enabled`,
   `model_not_chosen`, `model_not_enabled` and `secret_ref_missing` arrive as
   `error` frames with the text already safe (021 D3).
2. **A domain error mid-stream becomes an `error` frame, not an HTTP status.**
   The status was already sent. The frame carries the same `{code, message,
   detail}` shape as the JSON error body so the SPA has one error renderer.
3. **The server never ends a stream silently.** A source that raises a non-domain
   exception, or exhausts without emitting `error` or `done`, is ended by the
   harness with a synthesized `error` frame (`llm_unreachable`, fixed message)
   (019 D5). Silence therefore always means the connection went away.
4. **The persist rule is widened past a stop: the harness persists the
   accumulated `token` text whenever no `done` passed through** (019 D4). That
   covers a client disconnect, a domain `error`, a synthesized `error` and
   terminal-less exhaustion, and the row is written **before** the `error` frame.
   **Whitespace-only accumulated text writes no row.** This is a strict
   improvement on R10's extension — it was flagged for review by plan 019 and is
   **accepted**: the reason the rule exists (nothing the model produced for the
   roleplayer is thrown away) applies to a failure exactly as it applies to a
   stop. On the success path the *source* writes the row before yielding `done`,
   and the source must not write a partial row on any failure path.

Disconnect detection is **one `finally` keyed on "no terminal frame emitted"**,
covering cancellation, generator close and an `is_disconnected()` poll before
each write. The persist is synchronous; the source is then closed with a
shielded, error-suppressed `aclose()`, which unwinds the upstream `httpx`
request (019 D6).

### The stop is a client disconnect and nothing else

`llm-and-streaming.md` owns the mechanism and its consequences. Three route-level
facts follow, each stated because the absent thing is what a reader will look
for:

- **There is no stop route.** No `POST /api/sessions/{id}/stop`, and none may be
  added.
- **There is no registry of in-flight work.** Nothing on application state maps a
  session, a user or a request to a running generator. The current zone has no id
  (R11), so there is nothing to key such a registry on, and adding one would put
  server state beside a request that may already be gone.
- **The client re-reads `GET /api/sessions/{id}/zone` after every outcome** to
  pick up whatever was persisted.

Because a stop, a network drop and a closed tab are the same event at this layer,
**the handler makes no attempt to distinguish them** — there is one disconnect
path, and a flaky connection gets the same partial-text preservation a deliberate
stop does.

### The compose source — `services/compose.py`

`compose_stream` is the async source the harness drives; `begin_compose` is its
synchronous handler-side half. Its loop detail, the `<think>` convention and the
frame protocol are `llm-and-streaming.md`'s. What belongs here:

- **One assistant row per exchange**, holding all streamed token text across all
  tool rounds, `<think>` tags included (021 D11). A current-zone assistant row
  may therefore contain persisted reasoning; settle strips it (above).
- **The retry is a textless compose** (021 D2): it re-runs generation over the
  zone as it stands, inserts nothing, and re-reads the model at use time, so
  changing the session's model before retrying takes effect. It realizes
  `US-044.AC-3`'s widened form and `US-044.AC-5`; the control itself — an
  always-available "Regenerate", not a failure-only retry — is
  `workspace-shell.md`'s.
- **Service imports.** `compose.py` imports `configuration`, the context
  assembler, `messages`, `llm_registry`, `tools` and `llm.*`. None of them opens a
  transaction of its own on its behalf; each called operation owns its own. This
  is a named instance of the service-to-service import exception recorded in
  `backend-structure.md` (021 D15).

## The tool seam and dispatch

**Realizes:** FEAT-014, FEAT-015, FEAT-016, FEAT-019, UC-051, UC-053, UC-055,
UC-065, US-063, US-064, US-066, US-069

The seam is the backend half of R9: the assistant has no database access of its
own, so every tool is a scoped read and the **scope comes from the seam, never
from the model's arguments**. `llm-and-streaming.md` owns the loop and the
availability rule; the shapes below are the contract plans 026, 027 and 028 bound
to, and they live in the package `app/services/tools/` —
`definitions.py` (the three declarations) and `seam.py` (scope, outcome,
protocol, registry, offered tools, dispatch) (021 D6).

| Piece | Shape | Rule |
|---|---|---|
| `ToolScope` | `(user_id, session_id, character_id, setup_id)` | built **only** by the seam, from an owner-scoped session read. The one place a tool's scope comes from |
| `ToolOutcome` | `(content, summary)` | `summary` never carries raw content |
| `Tool` | `name` + `async run(scope, connection, arguments) -> ToolOutcome` | **any** `Exception` is a failure |
| dispatch | on the seam's **own short-lived connection** | leaves no transaction open |

**Tool arguments never carry ids** (021 D6). That is what makes R5's isolation a
property of the seam rather than of three separate implementations: a tool cannot
widen its own scope, because the only scope it is given is the one the seam
derived from the authenticated session.

A failure — the tool not offered, an unknown name, non-object arguments, or
`run` raising — produces a `tool_fail` frame carrying `tool_failed` plus the
fixed model-facing message, and the loop continues (R9: a failed tool does not
end the discussion). A **cancellation** propagates and writes **no** tool row, so
a stop during `run` ends the exchange — which is what `US-133.AC-1` now states.
`tool_failed` is a **502** (021 D13) — a dependency's failure, like
`llm_unreachable` — and in plan 021 it was never an HTTP response, only the
frame's code; `backend-structure.md`'s per-code status record is where that lives.
Its status was flagged for review by plan 021 and is **accepted**.

A declaration is edited in `tools/definitions.py` and never from an
implementation. The three tools are all implemented and registered;
`web_search` additionally requires instance credentials to be offered at all
(`llm-and-streaming.md`).

## The discussion read

**Realizes:** FEAT-010, UC-036, US-040, US-116

`GET /api/messages/{message_id}/discussion` is an owner-scoped read of a settled
entry's buried rows, ascending by id, answering `{ "messages": [...] }`
(022 D1, user decision U1). An owned settled entry with nothing buried answers
`[]`. **An unknown id, another user's id, a zone row and a buried row all answer
404 `message_not_found`** — the same refusal identity as every other message
route, which is why no new code was needed for the widened condition.

It is **read-only**, and it is the one reader of the `buried_messages` selectable
(022 D2). The rows render with no edit control, and the server half of that is
`PATCH`'s `message_not_editable` refusal above — the two say the same thing at
the two boundaries on purpose (R7, US-116).

**It carries no count**, by omission rather than design: `GET …/entries` does not
report how many rows a group holds, so a client cannot show a count before it
fetches. The client consequence — "Discussion", then "Discussion (N)" after the
first expand — is `workspace-shell.md`'s, and it now also carries
`US-040.AC-2` / `US-040.AC-3`, which require that no message show before the
group is opened.

`services/messages.py` owns the read (`list_discussion`), so the reader goes
through a named selectable and raw `messages` stays untouched outside settle and
re-open (R11).
