# Domain rules — the cross-cutting invariants

**Realizes:** FEAT-004, FEAT-006, FEAT-007, FEAT-008, FEAT-009, FEAT-010,
FEAT-011, FEAT-012, FEAT-013, FEAT-014, FEAT-015, FEAT-016, FEAT-019, UC-012,
UC-021, UC-025, UC-029, UC-032, UC-035, UC-036, UC-037, UC-038, UC-039, UC-040,
UC-041, UC-042, UC-044, UC-045, UC-046, UC-047, UC-048, UC-049, UC-050, UC-052,
UC-065, UC-066, UC-067, UC-068, UC-075, UC-076, UC-077, UC-078, UC-081, UC-083,
UC-084

Every feature in RPHelper binds to the rules below. They are collected in one
place because each one is violated by the *obvious* implementation, and because
several are deliberate asymmetries that read like bugs until the reason is
written down. Anything here that a plan contradicts is a plan defect, not a
design question.

---

## Roles — the ladder every rule below assumes

Not a rule of its own; a fact the rules refer to. There are exactly **two roles**,
ordered as a numeric ladder:

```
{ roleplayer: 0, admin: 1 }
```

`roleplayer` is ACT-002, `admin` is ACT-001. Authorization is expressed as "at
least this rung": the backend's `require_role(min_role)` dependency factory
resolves the caller and compares (`backend-structure.md`), and it guards **every**
admin route. The role is a column on `users` (`data-model.md`), not a set of
capability flags — a ladder because every check the product actually needs is a
threshold, and adding a rung later is then one line rather than an audit of every
route's flag conjunction.

The ladder **replaces** the sibling project's `{author, admin}`: the low rung is
renamed to RPHelper's actor rather than re-purposed. Frontend route gating
(`admin-surfaces.md`) is **UX only**; the backend check is the boundary.

---

## R1 — Configuration inheritance, and its deliberate asymmetry

**Realizes:** FEAT-013, UC-047, UC-048, UC-049, UC-050

Two resolution chains exist, and they are genuinely different lengths.

```
model, system prompt, tool switches :   user ──► character ──► session
RP language, preferred language     :   user ─────────────────► session
                                                  ▲
                                          character is SKIPPED —
                                          the override does not exist
```

**This asymmetry is deliberate, stated here so it is not "fixed" later.** The
reason is in the domain, not in the code: a character is a persona reused across
many partners and situations (`glossary.md`), and the language a roleplay is
conducted in belongs to the *roleplay*, not to the persona — the same character is
played with different partners in different languages. UC-048's postcondition
says so in the product's own words: RP language and preferred language "are not
offered here — they inherit `user → session`, skipping the character level".

Architectural consequences that must hold:

- The character configuration table has **no** `rp_language` and **no**
  `preferred_language` column. The asymmetry is enforced by the schema's shape,
  not by a resolver that politely declines to read a column. A column that exists
  will eventually be read.
- The resolver exposes two functions, not one parameterised one, so a caller
  cannot accidentally ask for a language through the three-level chain.
- UC-050's postcondition — "a character-level language override does not exist
  and is never consulted" — is a testable claim about the schema. It is not
  satisfied by a null column.

Resolution semantics for both chains: the **lowest level that has a non-null
value wins**; a level that has no value is transparent, not a value of "empty".
So a session that sets nothing resolves exactly to what the user-level default
resolves to, and clearing a session override restores inheritance rather than
setting a blank.

---

## R2 — Memo chain resolution, and correct degradation without a setup

**Realizes:** FEAT-007, FEAT-012, UC-046, UC-021, UC-052

A session's memo chain is the union of memos at four levels:

```
user ──► character ──► setup (optional) ──► session
```

The chain is a **union, not an override chain** — unlike R1. Memos accumulate;
a session-level memo does not shadow a character-level one. They are different
notes about different things, and FEAT-012's purpose is that all of them reach the
assistant (forced) or are reachable by it (searchable).

**Degradation is the rule, not the edge case.** A setup is optional — FEAT-007
calls it "a genuine absence, not a default that is usually filled in". When a
session has no setup, the chain is exactly `user + character + session`, **with no
gap**: not a null level, not an empty result, not a different code path. The
architectural requirement is that chain resolution is expressed as a scope
predicate over the levels that exist, so the no-setup case is arithmetically the
same query with one fewer term:

```sql
-- conceptual shape; concrete tables in data-model.md
WHERE (owner_scope = 'user'      AND scope_id = :user_id)
   OR (owner_scope = 'character' AND scope_id = :character_id)
   OR (owner_scope = 'setup'     AND scope_id = :setup_id)   -- term absent when NULL
   OR (owner_scope = 'session'   AND scope_id = :session_id)
```

Consequences:

- No flow may require choosing a setup before an RP can start (UC-021). That is a
  routing and validation rule as much as a data rule: session creation takes
  `setup_id` as genuinely nullable, with no default and no "(none)" sentinel row.
- `memo_search` returns correct results with no setup level present (UC-051's
  postcondition). The tool must be tested against a no-setup session, not only a
  with-setup one.
- A **sentinel "default setup" row is forbidden.** It would make the absence
  unobservable and would silently give the no-setup case a fourth scope to carry
  through export (FEAT-018) and drift reporting (FEAT-005).

---

## R3 — Two independent axes: `is_enabled` and `is_forced`

**Realizes:** FEAT-012, UC-042, UC-044, UC-045, UC-052, UC-075

A memo's reach is **two booleans, not one three-valued column**. This reverses the
earlier design, which stored a single `state` of `forced` / `searchable` /
`disabled` and recorded that "the prior mode is not remembered, so the schema
stores no previous state; the UI asks". **US-101 overturns that**: disabling a
note never touches whether it is forced, so re-enabling restores the mode the note
had, with nothing to ask. A single column cannot hold the forced flag of a
disabled note; two can. The reversal is deliberate and US-101 is the reason.

| Reach | `is_enabled` | `is_forced` |
|---|---|---|
| forced | true | true |
| searchable | true | false |
| disabled | false | **either — preserved across the disable** |

The three reaches are unchanged; only their storage is:

| Reach | Reaches the assistant | Path |
|---|---|---|
| forced | Always | Assembled into the system prompt for every message in scope (UC-045) |
| searchable | On demand | `memo_search` results only (FEAT-014) |
| disabled | **Never** | No path at all |

Rules that follow:

- **Defaults on creation are `is_enabled = true`, `is_forced = false`** (UC-042
  step 3, US-053) — the "searchable" cell. A created memo is immediately useful
  without being immediately expensive.
- **A forced memo is always in the system prompt** and never requires a tool call
  (UC-045's postcondition). Context assembly selects `is_enabled AND is_forced`
  directly; it does not route those memos through the search layer.
- **Forced memos are excluded from `memo_search` results** (UC-052) — they are
  already in context, so returning them wastes the call and the tokens. The
  tool's predicate is therefore `is_enabled AND NOT is_forced`.
- **`NOT is_enabled` reaches the assistant by NO path**, whatever `is_forced`
  says (US-100). Not context assembly, not `memo_search`, not `session_search`,
  not a tool result, not an error message that quotes memo content. This is an
  absolute exclusion and the single most important thing to test negatively: a
  disabled memo must be shown to be absent from *every* outbound surface, not
  merely filtered from the one query a developer remembered. Note the shape of the
  predicate: **`is_enabled` gates first and `is_forced` is only consulted
  afterwards.** An assembler that selects on `is_forced` alone puts a disabled
  forced note straight into the system prompt, and that is the exact bug the two
  booleans make possible and the ordering rules out.
- **Re-enabling restores the prior mode** (US-101). The UI does not ask, and no
  path may clear `is_forced` on disable "to be tidy" — that would silently
  re-implement the rule this section reverses.
- **This rule constrains the assistant, not the owner's own UI.** "Reaches the
  assistant by no path" is a statement about ACT-004's inbound surfaces — context
  assembly, the three tools, tool results, error payloads. It says nothing about
  what ACT-002 may see of their own memos. Concretely: **my-search (FEAT-017)
  *does* show disabled memos** — a roleplayer must be able to find a disabled memo
  in order to re-enable it, and the note wall (UC-075) shows and toggles both
  flags in place. The decision and its full reasoning are recorded in
  `search-and-retrieval.md`. The absolute exclusion still holds where it applies:
  a disabled memo is absent from `memo_search`, from `session_search` and from
  context, and the negative tests for those three are unaffected.
- Because both flags are mutable at any time and embeddings live in the same store
  (`overview.md`, vector-store decision), a flag change is an ordinary
  same-transaction update with no second store to reconcile.
- **Order is a third, independent thing** (UC-076, US-102): forced memos enter the
  system prompt in the roleplayer's arranged order *within their level*, and the
  level order itself is fixed (US-103). Neither flag carries ordering; the
  `sort_key` column in `data-model.md` does.

---

## R4 — No silent model fallback

**Realizes:** FEAT-004, FEAT-013, UC-012, UC-050

UC-012's exception flow (round-11 amendment) is unusually specific, and the
obvious implementation gets it wrong in two different ways at once.

The product rule, in three parts:

1. An administrator disabling a model **is never refused** on account of sessions
   depending on it. The disable always proceeds.
2. There is **no silent fallback** up the `user → character → session` chain. A
   session never quietly changes model.
3. The next time that session tries to use the model, it **shows an error**, and
   the roleplayer resolves it by choosing another model through FEAT-013's chain.

Architecturally this means:

- **Configuration resolution (R1) yields a model *reference*, not a validated
  model.** The resolver's job is to say which model this session is configured to
  use. It does **not** consult the enabled-models registry, and it must **not**
  skip a disabled level and keep walking up the chain — that walk is precisely
  the silent substitution the product forbids.
- **Validation happens at use time, not at resolution time.** The request path
  is: resolve → validate the resolved reference against the enabled-models
  registry → call. A reference that is no longer enabled produces a **typed
  error** surfaced to the SPA (see `backend-structure.md`'s error model), carrying
  which model was configured and at which level it was set, so the roleplayer
  knows where to go and change it.
- **"Sanitizing" during resolution is forbidden.** A resolver that quietly drops a
  disabled model and returns the next one up satisfies every happy-path test and
  violates the rule invisibly. This is stated as a prohibition rather than left
  to taste.
- The same reasoning applies to the **embedding** designation (UC-013): if the
  designated embedding model is gone, the semantic tools fail loudly rather than
  substituting another model, because a different embedding model silently
  produces vectors that are not comparable with the stored ones. See
  `search-and-retrieval.md`.

**The unstable-default corollary (US-106).** A character with no model configured
resolves to "the first enabled model". Re-resolved on every request, that floor
violates this rule from the other end: an administrator enabling a model that
sorts earlier would silently change the model a never-configured session has been
using — no error, no notice, a different voice in the next reply. "First enabled"
is a *bootstrap* answer, not a standing one. So the resolved reference is
**materialised onto `sessions.model_ref` the first time the session composes**
(`data-model.md`), after which the enabled-model set can change all it likes
without moving an existing session's model. Validation still happens at use time,
so a materialised reference that is later disabled produces the same loud typed
error as any other.

`_TBD: docs/product/ does not state what happens to that materialised value if
the character is configured with a model afterwards — the session keeps its own,
because overwriting it is the silent substitution this rule forbids, but that
consequence has not been ruled on. Raised for /product-spec._

Why the product accepts a loud failure over a helpful substitution: refusing the
admin's disable would require telling the administrator that *other users'
sessions* depend on the model, which FEAT-019 forbids (see R5). Given the admin
cannot be told, the only remaining honest place to surface the consequence is the
affected session, at the moment it matters, to the person who can fix it.

---

## R5 — Privacy forbids a reverse lookup

**Realizes:** FEAT-019, FEAT-004, UC-012, UC-065, UC-066

A query of the shape **`model → dependent sessions`** must not exist on any
administrative surface. Not as an endpoint, not as a count, not as a
confirmation dialog, not as a warning badge.

The reason is that answering it *is* a cross-user disclosure: it tells the
administrator that other users have sessions, how many, and — as soon as the list
is anything more than a bare integer — which. UC-066 says administrative surfaces
show administrative data only. UC-012's exception flow records this as the
explicit reason the disable is never refused.

Enforcement, expressed as design constraints rather than good intentions:

- The admin router exposes **no** endpoint keyed on a model that returns session
  data, session counts, or user counts.
- "Are you sure? N sessions use this model" is a **forbidden UI pattern** here,
  however helpful it looks. Recorded explicitly, because it is the first thing
  anyone will want to add.
- **The likely site is a specific screen: the LLM Servers page** (FEAT-004,
  `admin-surfaces.md`). That page disables models, deletes connections and — since
  destructive admin actions now carry a confirm step (`ui-conventions.md`) — has a
  dialog whose natural next sentence is a blast radius. **The exact string
  "Are you sure? N sessions use this model", and every variant of it, is
  forbidden**, as is any count, badge, tooltip or `detail` field that could power
  it. The confirm sentence describes the *action*, never a number derived from
  other users' data. Named this precisely because "no reverse lookup" reads as
  abstract advice right up until someone is writing that dialog in good faith.
- The general isolation rule this is a special case of: **every read path is
  scoped by owning user**, at the query level, from the authenticated session —
  never by a filter applied after the fact in the service or the client
  (UC-065). ACT-004's three tools are read paths and are scoped the same way;
  `session_search` additionally never crosses a character boundary (UC-054).
- The whole-database export (FEAT-018/UC-061) is the one artifact that
  necessarily contains every user's data. It stays compatible with this rule by
  being **opaque to the administrator**: the product offers no viewer, no search
  and no rendering of it. The architecture must therefore not grow an
  export-preview, export-diff or export-browse surface.

---

## R6 — Archive is removal from the working list, never destruction

**Realizes:** FEAT-006, FEAT-007, FEAT-008, UC-025, UC-067, UC-068

Characters, setups and sessions archive and restore. One rule for all three
(FEAT-006/007/008 each say "same rule as" the other two):

- Archiving takes the object **out of the working list**. Nothing is destroyed.
- Restoring puts it back, fully usable — a restored session resumes with nothing
  lost (UC-024, UC-025).
- **There is no "finished" state** for a session (UC-025's postcondition, UC-026).
  Archiving is the only lifecycle change and it is reversible.

Architecturally: an `archived_at` timestamp column, nullable, and **no delete
path at all** for these three entities. Listing endpoints filter
`archived_at IS NULL` by default and take an explicit flag to see the archive.
Stated as an invariant because the tempting shortcut — a hard delete behind a
"permanently remove" affordance — would contradict "always recoverable", and
because FEAT-018's per-character and per-session exports must be able to carry an
archived object.

Note the contrast with R3, deliberately: **memos do not archive.** They have two
reach flags and no archived state, and `is_enabled = false` is not an archive —
it is an exclusion from the assistant that leaves the note fully visible to its
owner. Applying the archive rule to memos, or R3's flags to sessions, is a design
error in either direction.

---

## R7 — The collapse rule, and its deliberate asymmetry against editable turns

**Realizes:** FEAT-009, FEAT-010, UC-029, UC-035, UC-036, UC-037, UC-038, UC-078,
UC-083

**The mechanism changed; the authority it protected did not.** This rule used to
rest on the answer box and the `discussions` table, and both are gone: the
product replaced the box with a current zone below a ruler, and the schema merged
three tables into `messages` (`data-model.md`). What that removed was plumbing.
Every guarantee below survives, restated on the new mechanism — written out in
full so nobody reads the missing box as a missing rule and "restores" it.

The lifecycle, in the new terms:

```
 current zone ──settle──► buried under the settled head ──┬── re-open (ONLY while
                                                          │   the zone is empty)
                                                          └── anything new in the
                                                              zone ──► permanently
                                                                       non-resumable
```

The rules, each separately testable:

- **Nothing reaches the record without the roleplayer settling it.** Settling
  takes the last message in the current zone, whoever wrote it (US-126, UC-035).
  The old formulation — "the box is always the roleplayer's; the assistant never
  writes into the session directly" — is **restated, not dropped**: every message
  in the current zone is the roleplayer's to rewrite first, the assistant's
  included (US-115, US-126), and settle reads whatever the row holds at that
  moment. The assistant still never files anything itself. The only other door
  into the record is a pasted partner block filing itself (US-121), which is text
  the roleplayer supplied.
- **A buried group stays readable** (UC-036). Burial is not deletion and not
  archival; every message remains retrievable for display, and is not editable
  once buried (US-116).
- **Re-open is allowed only while the current zone below is empty** (UC-037,
  US-128). It is an undo for a mis-click, not a workflow. Once anything new
  exists in the zone, re-open is refused and the group is permanently read-only.
- **A buried group never reaches the assistant again** (UC-038) — not while still
  re-openable, not after. Only the settled row's text ever entered context; the
  scaffolding that produced it never does, then or later. See R11 for where that
  predicate lives.

**The deliberate asymmetry, stated so it is not "fixed" later:** a settled turn is
editable **forever**, including one from weeks ago (UC-029, UC-078, US-110), and
the assistant always reads the current version — so a later edit changes what
session context says happened. Its buried group, by contrast, is re-openable only
until something new appears in the zone. The product states both and names the
asymmetry itself (FEAT-009's and FEAT-010's notes, UC-038's postcondition).

The reason the two differ: the settled turn is the durable record of what happened
in the roleplay and must stay correctable; the buried messages are scaffolding
that was consumed when the turn was settled, and letting them re-enter after the
RP moved on would inject stale reasoning into a context that has since changed.
Anyone reading this as an inconsistency should read it as a boundary instead.

---

## R8 — Translations are a cache, and never enter context

**Realizes:** FEAT-011, FEAT-013, UC-039, UC-040, UC-041

- Nothing is translated until the roleplayer flicks it (UC-039). No eager or
  background translation exists.
- A successful translation is **cached** so the second look is instant and costs
  nothing (UC-041).
- A **failed** translation caches nothing and falls back to the original text with
  a visible error (UC-039's exception flow). So the cache write is conditional on
  success — a failure must not be memoised as an empty translation.
- **A translation never enters session context.** Context holds only the RP
  language (FEAT-011, `glossary.md`'s definition of RP language). The
  architectural consequence: translations live in their own table keyed by
  message and target language, and context assembly never joins to it. Stated as
  an invariant because the natural instinct — store the translation as a second
  field on the message — puts it one careless `SELECT *` away from the prompt.

The target language is the session's resolved **preferred language** (R1's
two-level chain), which is what makes the cache key `(message, target language)`
rather than just `(message)`: a session whose preferred language changes must not
be served the old translation.

**What is translatable narrowed with the stream merge.** Only settled rows are,
and in practice only `kind='partner'` ones: a `kind='decision'` row is already in
the roleplayer's preferred language (US-131), so translating it is a no-op that
would cost a model call, and a current-zone message is not yet record. The
RP-language guarantee that this rule leans on now covers
`kind IN ('partner','turn')` only — see `data-model.md`.

---

## R9 — The assistant's reach is exactly three tools

**Realizes:** ACT-004, FEAT-014, FEAT-015, FEAT-016, UC-065

ACT-004 consumes forced memos and the session's settled entries, and reaches
anything else **only** through `memo_search`, `session_search` and `web_search`
(`actors.md`). It never files anything into the record directly — it writes only
into the current zone, where the roleplayer may rewrite it and must settle it for
it to become record (R7, R11).

This is the enforcement point for R5's isolation: the assistant has no database
access of its own, so every tool implementation is a scoped read path and the set
of paths is closed at three. Adding a fourth tool is an architecture change, not a
feature detail.

A **failed tool does not end the discussion** (UC-051, UC-053 exception flows,
FEAT-010): the assistant is told the tool failed and carries on without it. The
loop treats a tool failure as a tool *result*, not as a stream error. See
`llm-and-streaming.md`.

---

## R10 — Nothing the roleplayer typed is ever lost to a model failure

**Realizes:** FEAT-009, FEAT-010, UC-032

When the LLM is unreachable mid-discussion, the record and every message already
in the current zone survive intact, the failure is visible, and retry is possible
(UC-032's exception flow).

The ordering rule that makes this true: **the roleplayer's text is persisted
before any model call is issued**, and a model failure never rolls back that
write. The stream carries an `error` frame; the transcript keeps everything it
already had. Equally, an enormous paste is warned about but **never refused**
(US-035.AC-1, US-035.AC-2) — the warning is a client-side context-cost notice, and
no layer of the stack may turn it into a rejection. See `deployment.md`'s
`client_max_body_size` note, where nginx's default would otherwise convert a
product guarantee into a 413.

---

## R11 — The ruler: settle is the only door into the record

**Realizes:** FEAT-009, FEAT-010, UC-035, UC-037, UC-083

A session is a **stream**: settled record above a ruler, and below it exactly one
**current zone** (US-125, UC-083). The rule, in four parts:

- **Nothing becomes record except by settling** (US-126, US-127), with the single
  exception of a pasted partner block, which is born settled because there is
  nothing to compose for text the roleplayer did not write (US-121). No other
  path may create a settled row — not an assistant reply, not an autosave, not a
  background tidy-up.
- **The current zone is structurally unique**, not uniquely-constrained. It is not
  a row but the set of a session's messages matching
  `related_to IS NULL AND settled_at IS NULL` (`data-model.md`). A set cannot be
  duplicated, so US-125 needs no constraint, no uniqueness index and no
  reconciliation job. Any design that reintroduces a "current zone" *row* or a
  pointer column to it is reintroducing a state that can drift, and is a defect.
- **Re-open is settle's exact inverse, is gated on an empty current zone, and
  applies only to a settled head that *has* a buried group** (US-128, UC-037). It
  clears `related_to` on the group and `settled_at` and `kind` on the head. Ids do
  not move, so a settle/re-open round trip leaves the stream in the state it
  started in — which is what makes it safe as an undo.
- **A pasted partner block is therefore never re-openable, and the refusal is
  this rule rather than a backend guard.** UC-037 re-opens *a collapsed
  discussion*; a partner block is born settled with nothing buried behind it
  (US-121), so there is no discussion to re-open and nothing the inverse could
  restore. Read literally, the bullet above would clear `settled_at` and `kind`
  on that head and silently demote a filed partner block back into the current
  zone — record turning back into draft, which no requirement permits. The
  operation is **refused**, and the refusal is the named error
  **`nothing_to_reopen`** (`backend-structure.md`'s error model). Stated here
  because a condition written down only in the backend reads as an implementation
  precaution, and an implementation precaution is what gets deleted by the next
  person simplifying the settle module.
- **The predicate lives in one place.** The merge of `entries` and
  `discussion_messages` cost the old structural guarantee that context assembly
  had *no join* to discussion rows; two views, `settled_entries` and
  `current_zone`, restore it one level down (`data-model.md`). Every reader —
  context assembly, `session_vec` composition, my-search — goes through a view.
  **Raw `messages` is touched by exactly two operations, settle and re-open.** A
  query naming `messages` directly anywhere else is a defect, and it is the
  specific thing to look for when reviewing a plan that touches the stream.

---

## R12 — `(( ))` is parsed once, at settle, and stored text is never re-parsed

**Realizes:** FEAT-009, FEAT-010, UC-081, UC-084, US-129, US-130, US-131

The double-parenthesis convention has exactly two readings, and both are resolved
at the moment of settling:

- **A wholly-parenthesised message is out-of-character.** Settling one files
  `kind='decision'` rather than `kind='turn'` (US-129, UC-081). A decision is in
  the roleplayer's preferred language, not the RP language (US-131), so it is
  never translated (R8) and offers no copy-out (US-123).
- **A parenthesised fragment inside a draft is a fast instruction to the
  assistant** (US-130, UC-084). At settle the fragment is **stripped from the head
  row's text in place, in the same transaction**, so it never appears in the
  settled turn.

**The pre-strip text is not preserved.** The fragment was an instruction, not
prose — there is no roleplay content in it to lose — and `docs/product/` asks for
no revision history anywhere (`data-model.md` records that there is no revision
table). Storing a shadow copy would be a revision history for one column,
introduced for a case that does not need one.

**A pasted partner block gets no special treatment** (US-121). The convention is
the roleplayer's own side only: double parentheses in partner text are the
partner's words and are stored verbatim. Recorded as a negative requirement,
because a single parser applied to all inbound text is the obvious implementation
and it is wrong.

Split of responsibility, so three layers do not each grow their own parser:

| Layer | Does |
|---|---|
| Server, at settle | **Decides.** Classifies wholly-parenthesised → `decision`, strips fragments, writes the result once. |
| System prompt | Tells the model how to *read* the convention while text is still in the current zone (`llm-and-streaming.md`). |
| Client | **Previews** what will happen. Never authoritative. |

The invariant: **parse once, at settle; never re-parse stored text.** A settled
row's text is the text, and an edit to it (UC-029, US-110) is taken literally —
re-running the parser on a later edit would silently delete a roleplayer's
deliberately parenthesised prose long after they wrote it.

`_TBD: carried forward from docs/product/ (features.md FEAT-010, US-130,
challenge C21) — nothing states what happens when RP prose itself legitimately
contains double parentheses. A draft could silently lose text at settle. Not
resolved here; resolving it is a product decision._
