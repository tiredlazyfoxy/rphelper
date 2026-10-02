# Feature 012 — Messages and settle · feature-wide context

## What this feature is

The backend door into a session's record. One `messages` table holds every row of a
session's stream; two named read selectables split it into the **settled record**
(`settled_entries`) and the single **current zone** (`current_zone`). Appending puts a
roleplayer message into the zone; a pasted partner block is filed born-settled; **settle**
is the only operation that moves the zone into the record (burying every other zone row
under the settled head in the same transaction), and **re-open** is its exact inverse,
allowed only while the zone is empty. A pure `(( ))` parser classifies the settled head as
`decision` or `turn` and strips instruction fragments from a turn, once, at settle.

The agreed boundary is `brief.md` in this folder; its Definition and Scope In/Out bound
every step and are **not** widened. Its two open questions are closed by **D5** (US-120)
and **D1** (views vs query builders).

**Backend only.** No frontend file is touched: the stream, the ruler, the kind switch,
the composer and the API client / state for entries and the zone are `013`'s.

## Product ids

Delivered (per brief): FEAT-009 — UC-028, UC-031, UC-081, US-031, US-034, US-122;
FEAT-010 — UC-037, UC-083, UC-084, US-041, US-042, US-126, US-127, US-128, US-129,
US-130.

| Criterion | Where it lands |
|---|---|
| US-031.AC-1 (write directly, settle, no discussion → settled turn) | `003`, `004` |
| US-034.AC-1 (first entry may be the roleplayer's own) + UC-031 (two turns running; several partner blocks in sequence) | `002`, `003`, `004` |
| US-122.AC-1 / AC-2 — **backend precondition only**: a settled decision is in `settled_entries` with kind `decision`. Context inclusion is `020`'s, `session_search` is `027`'s | `003`, `004` |
| US-041.AC-1 / US-128.AC-1 (re-open while the zone is empty restores the group) | `003`, `004` |
| US-042.AC-1 / US-128.AC-2 (re-open refused while the zone holds a message; group stays buried) | `003`, `004` |
| US-126.AC-1 / AC-2 (settle takes the last zone row, whoever wrote it) | `003` (assistant row raw-inserted — no assistant writer exists in 012), `004` |
| US-127.AC-1 / AC-2 (after settle the head is in the record and the zone is empty) | `003`, `004` |
| US-129.AC-1 (wholly `(( ))` → decision) | `003` |
| US-130.AC-1 (fragment absent from the settled turn) | `003`. **US-130.AC-2** is assistant behaviour — out (`020`/`021`) |
| Supporting, backend half of 013's UI: US-121.AC-1 / AC-2 (born-settled partner, no paren handling), US-125.AC-1 (the zone is a set), US-135.AC-1 (settle with only the roleplayer's message), US-134 (no discard route) | `002`, `003`, `004` |
| 011's forward notes: US-027.AC-3's "every entry intact" half (archive → restore leaves entries and zone untouched), US-024.AC-2's "adding entries with no setup works" half | `004` |

**Not delivered, recorded rather than faked:** US-120 (the kind switch's default — UI,
`013`; see D5), US-115 / US-110 / US-109 settled-row editing (`014`; D2), US-130.AC-2,
US-122's context and search halves, US-040 (reading a collapsed group — no read route for
buried rows exists in 012; `013` designs it).

## Build prerequisite — 011 is planned, not built

001..007 are built; 008 is in progress; **009, 010, 011 are planned, not built.** 012
binds to 011's **declared** interfaces, cited from its step files and not re-specified:

| Upstream artifact (011) | What 012 relies on | Needed by |
|---|---|---|
| `backend/app/db/schema.py` `sessions` Table (011 `001`) | FK target of `messages.session_id`; the owner-scoped session check; the `last_used_at` / `updated_at` bump | `001`, `002`, `003` |
| `backend/app/errors.py` `SessionNotFoundError` (011 `001`; code `session_not_found`, 404, empty `detail`) | raised for a missing or foreign session on every session-addressed operation | `002`, `003`, `004` |
| `backend/app/routers/sessions.py` + its `main.py` registration (011 `003`) | `routers/stream.py` registers **after** it; router tests create a session through `POST /api/characters/{id}/sessions` and archive / restore it through 011's routes | `004` |
| 011's character creation chain (009 `003`'s `POST /api/characters`) | router tests create the parent character | `004` |

`services/sessions.py` (011 `002`) is **not imported** by anything in 012 (D11).

## Built state this feature reads

`app/errors.py` `DomainError` + `register_exception_handlers`; `app/models/ids.py`
`SnowflakeOut` / `SnowflakeIn`; `app/ids.py` `SnowflakeGenerator` (`next_id()`);
`app/routers/bootstrap.py` `get_id_generator`; `app/dependencies.py` `require_user` →
`CurrentUser`; `app/db/engine.py` `get_connection`; `app/main.py`; `app/db/schema.py`'s
one `metadata`. Conventions exactly as 011 `context.md` and its `001`–`003` contexts
apply them (snowflake id column form, fixed-width Text timestamps from a private per-module
`_now_text()`, `with connection.begin():` writes, a private read context that leaves no
transaction open, frozen dataclass values, no `fastapi` import in services,
`model_validate(..., from_attributes=True)` in routers).

## The `messages` table (D1, `data-model.md` `messages`)

| Column | Type / nullability | Notes |
|---|---|---|
| `id` | snowflake PK (registry id form) | `ORDER BY id` **is** stream order; no position column |
| `user_id` | NOT NULL, FK `users.id` | owner scope (R5) |
| `session_id` | NOT NULL, FK `sessions.id` | parent |
| `role` | Text, NOT NULL | `'user'` \| `'assistant'` \| `'tool'`. **No DB CHECK**; 012 only ever writes `'user'` |
| `kind` | Text, nullable | `'partner'` \| `'turn'` \| `'decision'`; NULL until settled. **No DB CHECK** |
| `text` | Text, NOT NULL | mutable |
| `related_to` | nullable, FK `messages.id` (self) | the settled head this row is buried under |
| `settled_at` | Text, nullable | |
| `tool_name`, `tool_payload` | Text, nullable | `role='tool'` rows only (R9). Declared now, **never written or read in 012** |
| `created_at`, `updated_at` | Text, NOT NULL | fixed-width |

Plus one named CHECK `related_to IS NULL OR settled_at IS NULL`, a non-unique index on
`(session_id, settled_at)` and one on `(related_to)`. No FK has `ON DELETE`.

**The four states** (`data-model.md`): NULL/NULL = current zone; `related_to` NULL +
`settled_at` set = record; `related_to` set + `settled_at` NULL = buried; both set =
illegal (CHECK).

## Wire contract — the stream routes (`routers/stream.py`, D12)

Router-level `require_user`; full paths; registered in `main.py` after 011's sessions
router. All JSON; nothing streams in 012.

| Route | Body | Answers |
|---|---|---|
| `GET /api/sessions/{session_id}/entries` | — | 200 `{ entries: [Message…] }` — `settled_entries`, ascending id |
| `POST /api/sessions/{session_id}/entries` | `{ kind: "partner", text }` | **201** the filed `Message` (born settled) |
| `GET /api/sessions/{session_id}/zone` | — | 200 `{ messages: [Message…] }` — `current_zone`, ascending id |
| `POST /api/sessions/{session_id}/zone/messages` | `{ text }` | **201** the appended `Message` |
| `POST /api/sessions/{session_id}/settle` | none | 200 `{ entry_id, kind, buried_ids: [id…] }` |
| `POST /api/sessions/{session_id}/reopen` | none | 200 `{ reopened_id, restored_ids: [id…] }` |
| `PATCH /api/messages/{message_id}` | `{ text }` | 200 the edited `Message` |

`Message` on the wire — exactly eight keys:

```
{ id: "<decimal string>", session_id: "<decimal string>",
  role: "user" | "assistant" | "tool",
  kind: "partner" | "turn" | "decision" | null,
  text: string, settled_at: string | null,
  created_at: string, updated_at: string }
```

`user_id`, `related_to`, `tool_name` and `tool_payload` are **never** on the wire
(`related_to` is NULL for every row either selectable returns; the tool columns have no
writer until `021`). Every id — including each element of `buried_ids` /
`restored_ids` — is a decimal string. `buried_ids` / `restored_ids` are ascending by id.

Request bodies ignore unknown keys (as 011). `text` is validated per **D9**. The entries
POST's `kind` is **required and must be exactly `"partner"`**; any other value or an
absent `kind` → 422 (R11's single exception, enforced at the boundary).

Failures (all with the `{ error: { code, message, detail } }` envelope, `detail` `{}`):

| Code | Status | When |
|---|---|---|
| `session_not_found` | 404 | any `/api/sessions/{id}/…` route whose session is missing **or another user's** (011's code) |
| `message_not_found` | 404 | `PATCH` on a message id that is missing **or another user's** (new, R5) |
| `message_not_editable` | 409 | `PATCH` on a buried row, or (until `014`) on a settled row (new, D2) |
| `zone_empty` | 409 | settle with an empty zone (new) |
| `zone_not_empty` | 409 | re-open while the zone holds a row (new) |
| `nothing_to_reopen` | 409 | re-open with an empty zone where the last settled row has no buried group, or there is no settled row (new, D10) |
| — | 422 | non-numeric path id; blank / missing `text`; entries `kind` not `"partner"` |
| `not_authenticated` | 401 | no login cookie |

## Architecture this binds to

- `docs/architecture/data-model.md`: **`messages`** (columns, the four states, "Settle is
  two UPDATEs and no INSERT", "Re-open … exact mirror", born-settled partner, `text`
  mutable, indexes, "The cost of the merge" — the views, re-shaped by D1), **"… and the
  archive rule"** (no cascade), Identifiers, the timestamp convention, `sessions`
  (`last_used_at` versus `updated_at`).
- `docs/architecture/domain-rules.md`: **R5**, **R6** (archive is not a lock), **R7**,
  **R10** (an enormous paste is never refused), **R11** in full, **R12** in full.
- `docs/architecture/backend-structure.md`: "The stream routes — FEAT-009 and FEAT-010 in
  one router" (route table and its bullets), "Settle and re-open — one transaction each,
  one module", "The `(( ))` seam", "The error model" + "The per-code status record",
  "Routers versus services", "The JSON id boundary", "Database access" (transactional
  DDL; a read then `begin()` on one connection must end the read first), "Persistence
  access — SQLAlchemy Core".
- `docs/architecture/admin-surfaces.md`: the "Two recorded gaps — views and virtual
  tables" paragraph and its "second edge" (moot for the views under D1).
- Product: `use-cases/FEAT-009.session-entries.md`, `stories/FEAT-009.session-entries.md`,
  `use-cases/FEAT-010.compose-discussion.md`, `stories/FEAT-010.compose-discussion.md`.

Cited, never copied.

## Files this feature touches

```
backend/
  app/db/schema.py          # + messages Table, + 3 named selectables, docstring line   (001)
  app/errors.py             # + 5 DomainError subclasses                                (001)
  app/models/stream.py      # NEW — request / response models                            (001)
  app/services/messages.py  # NEW — read zone / entries, append, file partner, edit     (002)
  app/services/parens.py    # NEW — pure classify / strip_fragments                     (003)
  app/services/settle.py    # NEW — settle + re-open                                    (003)
  app/routers/stream.py     # NEW — the seven routes                                    (004)
  app/main.py               # registers the stream router after sessions                (004)
  tests/test_db_schema.py (012 delta), tests/test_stream_models.py,
  tests/test_admin_db_router.py (checked; conditional)                                  (001)
  tests/test_messages_service.py                                                        (002)
  tests/test_parens.py, tests/test_settle_service.py                                    (003)
  tests/test_stream_router.py                                                           (004)
```

**Not touched. A step that touches one is out of scope:** every 009 / 010 / 011 module
(`models/`, `services/`, `routers/` for characters, setups, sessions),
`services/auth.py`, `services/bootstrap.py`, `dependencies.py`, `ids.py`,
`models/ids.py`, `db/engine.py`, `db/drift.py`, `db/sync.py`, every other router and
service, `backend/tests/conftest.py`, 009 / 010 / 011 tests, and **everything under
`frontend/`**. No new Python dependency.

## Cross-cutting constraints every step holds

**Owner scope lives in SQL (R5).** Every statement that reads or writes `messages` carries
`user_id = <caller>` in its own `WHERE` (or `VALUES`), and so does every statement on
`sessions`. A session that is missing and one that is another user's take the same path
and raise the same error; likewise for messages.

**Readers go through the named selectables (D1, D7).** No module outside `services/settle.py`
issues a `select()` over the raw `messages` Table. `services/messages.py` reads only
through `settled_entries`, `current_zone` and `message_states`; `routers/stream.py` has no
SQL at all.

**Who writes which column (D16).** `services/settle.py` is the **only** writer of
`related_to`, of `kind`, and of `settled_at` on an existing row. `services/messages.py`
inserts zone rows (`related_to`, `settled_at`, `kind` all NULL), inserts the born-settled
partner row, and updates `text` / `updated_at` on **current-zone rows only**. Nothing
deletes a `messages` row; no `DELETE` statement or route exists.

**No discard route, no stop route** (R11, UC-086, US-134; `backend-structure.md`'s "There
is no stop route"). Abandoning an empty zone is frontend-only.

**Parse once, at settle (R12).** `services/parens.py` is called from `services/settle.py`
only. Append, partner filing and `PATCH` take text literally.

**Archive is not a lock (R6).** Every read and write works identically on an archived
session; no operation reads `sessions.archived_at`.

**Every content write bumps the session (D3); refusals and reads write nothing.**

**Routers own HTTP; services own SQL; services never import each other (D11).**

## Decisions — settled, with their reasoning

"011 Dn" are in `docs/plans/011.rp-sessions/context.md`.

### D1 — The two views are SQLAlchemy Core selectables, not SQL VIEWs (user decision; closes brief open question 2)

`settled_entries` (`settled_at IS NOT NULL`) and `current_zone` (`related_to IS NULL AND
settled_at IS NULL`) are two **named, module-level `select()` objects over `messages`** in
`db/schema.py`, executing no DDL. Callers narrow them (session, owner, id) and order them;
the selectables themselves carry no session filter and no ordering.

Reasoning: nothing in the codebase can manage a view. Bootstrap's `create_all` and the
admin page's Create / Sync handle tables only; drift and `/api/health` walk
`metadata.tables`; a Sync batch-recreate of `messages` would break a real view at the
rename step (`admin-surfaces.md`'s "second edge"); and there is no creation path for a
view on an existing instance. A Core selectable keeps the property the views existed for —
**the predicate exists in exactly one place** — with none of those costs. R11's reader
invariant holds unchanged: every reader outside settle / re-open goes through a selectable.
The `schema.py` module docstring line that says "the two SQL views … live here too" is
updated by `001`.

### D2 — `PATCH /api/messages/{message_id}` ships for current-zone rows only

`013` needs in-place editing of zone messages (US-115.AC-1) and has no backend scope;
`014`'s brief owns editing a settled row. So 012's PATCH edits the text of a
**current-zone** row literally (no parens parsing, R12), bumps the row's `updated_at` and
the session (D3). A **buried** row → `message_not_editable` (US-116). A **settled** row →
also `message_not_editable` for now; `014` widens it. Missing or foreign →
`message_not_found`.

### D3 — Every content write bumps the session (closes 011 D3's forward note)

Append, file partner block, zone edit, settle and re-open each set `sessions.last_used_at`
**and** `sessions.updated_at` to the operation's instant, in the **same transaction** as
the message write. Reads never bump (011 D3). A refused operation writes nothing at all,
the bump included. `updated_at` moves too because `data-model.md`'s `sessions` section
says it "moves on any write", and setting `last_used_at` is a write to the row.

Within one operation every timestamp it writes (`created_at`, `updated_at`, `settled_at`,
the session bump) is **one instant**.

### D4 — No `session_vec` / FTS refresh in 012

`backend-structure.md` lists "refresh `session_vec`" as settle's step 5, but no vector or
FTS table exists until `024.embedding-lifecycle` (which depends on 012 and owns
embed-on-write). No seam, no stub, no hook. `outcome.md` records that settle's step 5
lands with `024`.

### D5 — US-120 is answered by the product docs (closes brief open question 1)

US-120.AC-3: settled decisions have no effect on the kind switch's default; it alternates
from the last partner-or-turn entry. The brief's open question and the `_TBD:` carried in
`workspace-shell.md` / `quick-reference.md` are stale. 012's only contribution: every
entry returned by `GET …/entries` carries its `kind`, so `013` computes the default
client-side.

### D6 — Brief open question 2 is closed by D1

The "registry must describe whatever they are" concern disappears: selectables are not
schema objects, so the drift registry has nothing to describe.

### D7 — A third, text-free selectable for the edit target (planner decision, accepted by the user)

`PATCH` must tell a buried row (`message_not_editable`) from a missing one
(`message_not_found`), and a buried row is in neither `settled_entries` nor
`current_zone`. Rather than a raw `select()` on `messages` inside `services/messages.py`,
the schema layer declares **`message_states`**: a named `select()` over `messages`
projecting **only** `id`, `user_id`, `session_id`, `related_to`, `settled_at` — **no
`text`, no `kind`**. It can classify a row's state but cannot carry content, so no buried
scaffolding can leak through it to any reader (R11's purpose). `outcome.md` records it for
the architect (the doc names two views).

### D8 — The `(( ))` rules (user decision on the classifier; planner spec for stripping)

The exact rules and examples are `003.context.md` "The parser, as spec". In short:

- **Decision** iff the text, **after trimming outer whitespace, starts with `((` and ends
  with `))`**. A decision keeps its text **verbatim** — no stripping, no trimming. So
  `"((a)) prose ((b))"` is a decision stored as-is; the user accepts that consequence.
- Otherwise a **turn**: every fragment (the shortest `((`…`))` span) is stripped with the
  stated whitespace tidy-up; a turn with **no fragment** settles **byte-for-byte
  unchanged** (US-135 "as-is").
- **The empty-turn edge case cannot occur, malformed input included.** If stripping left
  nothing but whitespace, every non-whitespace character lay inside some fragment, so the
  trimmed text begins with the first fragment's `((` and ends with the last fragment's
  `))` — which makes it a decision, never a turn. An unbalanced `((` with no later `))`
  is not a fragment and survives stripping, and a stray `)` or `(` outside a fragment
  survives too, so neither can produce an empty turn. No settle refusal for an empty turn
  is therefore needed.

### D9 — Text validation at the boundary

`text` in all three request bodies is required, a string, and **not blank**: empty or
whitespace-only → 422. It is **stored verbatim** — not trimmed, not normalised — because
R12 takes text literally. **No maximum length**: an enormous paste is never refused (R10,
US-035.AC-2). Services trust the router's validation.

### D10 — Re-open is the literal R11 rule (user decision)

Re-open, in one transaction: session check; zone non-empty → `zone_not_empty`; take the
**last settled row of the session by id**; if there is none, or **no row has
`related_to` = its id** → `nothing_to_reopen`; otherwise clear `related_to` on the group
and `settled_at` + `kind` on the head. So a **lone directly-settled turn, a lone decision
and a pasted partner block are all not re-openable**, and an earlier group followed by any
later settled row is unreachable (UC-037). Ids never move. The head's text is **not**
restored to its pre-strip form (R12). Check order: session, zone, last settled, group.

### D11 — Service isolation (011 D11's rule)

`services/messages.py` and `services/settle.py` never import each other or any other
`app.services.` module. Each does its own owner-scoped session check, its own bump and has
its own `_now_text()`. Because no value type can be shared without an import, **settle and
re-open return ids, not message values** — which is also what `backend-structure.md`
specifies ("the response returns the ids the operation moved, so the client can
reconcile"); the client re-reads `GET …/entries` and `GET …/zone`.

### D12 — The route surface

The Wire contract above. One router named `routers/stream.py` (`backend-structure.md`'s
name; `019`–`022` later add the SSE compose route to it). Settle and re-open take **no
target id** (structural, `backend-structure.md`). Models live in `app/models/stream.py`.

### D13 — Five new error codes and their statuses (012 is the introducing feature)

`zone_empty` 409, `zone_not_empty` 409, `nothing_to_reopen` 409,
`message_not_editable` 409 — the request is well formed and the caller owns the target,
but the stream's state conflicts with the operation (the shape of `username_taken` /
`setup_archived`); not 404, the target exists; not 422, no field is malformed.
`message_not_found` 404 — the path's message id addresses no row of the caller (R5:
nobody's and another user's are indistinguishable), sibling of `session_not_found`. Each
subclass carries a fixed non-empty default `message` (the `already_configured` pattern) and
an empty `detail`.

### D14 — Filing a partner block does not require an empty zone (user decision: allow, no UI guard)

`POST …/entries` has no zone precondition: `backend-structure.md` lists none and UC-027
says a paste is never refused. A partner block filed while the zone holds a draft gets a
**larger** id than that draft, so if the draft is settled afterwards it sorts **above**
the partner block in the record (`ORDER BY id` is stream order), and the partner block —
not the draft — is then the last settled row, so the draft's group is not re-openable.
**The user accepted this as chronologically true and harmless:** the draft was begun before
the partner block arrived. No backend refusal, and no UI guard is asked of `013`.

### D15 — Four steps

Table + selectables + errors + models; the messages service; the parser with the settle
service (the parser alone is ~40 LoC, below the 50-line floor, and `settle` is its only
caller, so they share a step); the router. Suggested five became four for that reason.

### D16 — R11's "two operations" read as a rule about the record columns

R11 / `data-model.md` say raw `messages` is touched by exactly two operations, while the
same docs' route table gives the append and the partner filing an insert each and `PATCH`
an update. 012 reads the rule as: **reads** go through selectables everywhere but settle /
re-open, and the **burial and settle columns** (`related_to`, `kind`, `settled_at` on an
existing row) are written only by settle / re-open. `outcome.md` asks the architect to
word R11 that way.

## Step map

| Step | Subject | Est. LoC | Depends on |
|------|---------|----------|------------|
| 001 | `messages` Table, three selectables, five errors, `models/stream.py` | ~150 | 011 `001` delivered |
| 002 | `services/messages.py` — reads, append, file partner, zone edit | ~170 | 001; 011 `001` delivered |
| 003 | `services/parens.py` + `services/settle.py` | ~160 | 001; 011 `001` delivered |
| 004 | `routers/stream.py` + `main.py` registration | ~120 | 001, 002, 003; 009 / 011 `001`–`003` delivered |

`002` and `003` are independent of each other.

## Test conventions

Inherited from 011 `context.md` "Test conventions" (backend paragraph: pytest from
`backend/`, no shared fixtures added, schema from `create_all`, per-file `application` /
`client` fixtures with a file-local `_insert_user` and `_login`, two users for isolation).
Additions for 012:

- **FK chain.** A `messages` row needs its user, character and session rows. Service tests
  raw-insert users, characters (009's columns) and sessions (011 D8's eight columns,
  `setup_id` NULL), then build stream state through the services, raw-inserting
  `messages` rows only where 012 has no writer (an `role='assistant'` zone row) or to set
  up a state precisely. Router tests create the character through `POST /api/characters`
  and the session through `POST /api/characters/{id}/sessions`; they raw-insert an
  assistant row through the test engine where a DoD needs one.
- **Expected values come from this plan,** never from calling `classify` /
  `strip_fragments` to compute an expectation.
- **Ordering assertions** compare ids as integers server-side (service tests) and as the
  order of the returned list (router tests); never by `created_at` (one instant may repeat).
- **Timestamps** are asserted by their fixed-width shape
  (`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`) and by equality / non-decrease, never by exact value.

## Vocabulary

| Term | Means here |
|---|---|
| **zone** / **current zone** | a session's rows with `related_to` and `settled_at` both NULL; read through `current_zone` |
| **record** / **entries** | a session's rows with `settled_at` set; read through `settled_entries` |
| **head** | the zone row settle takes (the last by id), and afterwards the settled row it became |
| **group** / **buried rows** | the rows whose `related_to` is a head's id |
| **fragment** | the shortest `((`…`))` span (D8) |
| **bump** | setting `sessions.last_used_at` and `sessions.updated_at` to the operation's instant (D3) |
| **born settled** | a partner row inserted with `kind='partner'` and `settled_at` set (US-121) |
