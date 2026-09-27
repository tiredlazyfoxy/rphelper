# Domain rules — the cross-cutting invariants

**Realizes:** FEAT-004, FEAT-006, FEAT-007, FEAT-008, FEAT-009, FEAT-010,
FEAT-012, FEAT-013, FEAT-019, UC-012, UC-029, UC-036, UC-037, UC-038, UC-044,
UC-045, UC-046, UC-050, UC-052, UC-065, UC-066

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

## R3 — `forced` / `searchable` / `disabled`: one setting, three values

**Realizes:** FEAT-012, UC-042, UC-044, UC-045, UC-052

A memo is in **exactly one** of three states at any time (UC-044's
postcondition). This is one column, not two booleans, and not an
`active` × `archived` pair — FEAT-012 states the simpler model was chosen
deliberately and that **memos have no archived state at all** (unlike characters,
setups and sessions — see R6).

| State | Reaches the assistant | Path |
|---|---|---|
| `forced` | Always | Assembled into the system prompt for every message in scope (UC-045) |
| `searchable` | On demand | `memo_search` results only (FEAT-014) |
| `disabled` | **Never** | No path at all |

Rules that follow:

- **Default on creation is `searchable`** (UC-042 step 3). Not `forced`, not
  `disabled`. A created memo is immediately useful without being immediately
  expensive.
- **`forced` is always in the system prompt** and never requires a tool call
  (UC-045's postcondition). Context assembly reads forced memos directly; it does
  not route them through the search layer.
- **`forced` memos are excluded from `memo_search` results** (UC-052) — they are
  already in context, so returning them wastes the call and the tokens.
- **`disabled` reaches the assistant by NO path.** Not context assembly, not
  `memo_search`, not `session_search`, not a tool result, not an error message
  that quotes memo content. This is an absolute exclusion and the single most
  important thing to test negatively: a disabled memo must be shown to be absent
  from *every* outbound surface, not merely filtered from the one query a
  developer remembered.
- Re-enabling a disabled memo requires choosing a mode again (UC-044's alternate
  flow) — the prior mode is **not** remembered. So the schema stores no
  "previous state"; the UI asks.
- **This rule constrains the assistant, not the owner's own UI.** "Reaches the
  assistant by no path" is a statement about ACT-004's inbound surfaces — context
  assembly, the three tools, tool results, error payloads. It says nothing about
  what ACT-002 may see of their own memos. Concretely: **my-search (FEAT-017)
  *does* show `disabled` memos** — a roleplayer must be able to find a disabled
  memo in order to re-enable it, which is the alternate flow in the bullet above.
  The decision and its full reasoning are recorded in `search-and-retrieval.md`.
  The absolute exclusion still holds where it applies: a `disabled` memo is absent
  from `memo_search`, from `session_search` and from context, and the negative
  tests for those three are unaffected.
- Because state is mutable at any time and embeddings live in the same store
  (`overview.md`, vector-store decision), a state change is an ordinary
  same-transaction update with no second store to reconcile.

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

**Realizes:** FEAT-006, FEAT-007, FEAT-008, UC-019, UC-025, UC-068

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

Note the contrast with R3, deliberately: **memos do not archive.** They have
three reach-states and no archived state. Applying the archive rule to memos, or
the three-state rule to sessions, is a design error in either direction.

---

## R7 — The collapse rule, and its deliberate asymmetry against editable answers

**Realizes:** FEAT-009, FEAT-010, UC-029, UC-035, UC-036, UC-037, UC-038

Settling an answer collapses its discussion. The lifecycle:

```
 open ──settle──► collapsed ──┬── re-open  (allowed ONLY while nothing follows)
                              │
                              └── next entry created ──► permanently non-resumable
```

The rules, each of which is separately testable:

- **Settling takes whatever the answer box holds at that moment** (UC-035). The
  box is always the roleplayer's; the assistant never writes into the session
  directly. Three paths reach the box — an assistant candidate promoted, text
  written from scratch, or a candidate edited — and the settle operation cannot
  distinguish them, because it reads only the box.
- **A collapsed discussion stays readable** (UC-036). Collapse is not deletion
  and not archival; every message remains retrievable for display.
- **Re-open is allowed only while nothing follows the answer** (UC-037). It is an
  undo for a mis-click, not a workflow. Once any entry exists after that answer,
  re-open is refused and the discussion is permanently read-only.
- **A settled discussion never reaches the assistant again** (UC-038) — not while
  still re-openable, not after. Only the settled answer text, in the RP language,
  ever entered context; the discussion that produced it never does, then or
  later. Context assembly therefore selects on entry text, never on discussion
  messages. See `llm-and-streaming.md`.

**The deliberate asymmetry, stated so it is not "fixed" later:** a settled answer
is editable **forever**, including one from weeks ago (UC-029, US-032), and the
assistant always reads the current version — so a later edit changes what session
context says happened. Its discussion, by contrast, is re-openable only until the
next entry exists. The product states both and names the asymmetry itself
(FEAT-009's and FEAT-010's notes, UC-038's postcondition).

The reason the two differ: the answer is the durable record of what happened in
the roleplay and must stay correctable; the discussion is scaffolding that was
consumed when the answer was settled, and letting it reopen after the RP moved on
would let it inject stale reasoning into a context that has since changed. Anyone
reading this as an inconsistency should read it as a boundary instead.

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
  architectural consequence: translations live in their own table keyed by entry
  and target language, and context assembly never joins to it. Stated as an
  invariant because the natural instinct — store the translation as a second
  field on the entry — puts it one careless `SELECT *` away from the prompt.

The target language is the session's resolved **preferred language** (R1's
two-level chain), which is what makes the cache key `(entry, target language)`
rather than just `(entry)`: a session whose preferred language changes must not be
served the old translation.

---

## R9 — The assistant's reach is exactly three tools

**Realizes:** ACT-004, FEAT-014, FEAT-015, FEAT-016, UC-065

ACT-004 consumes forced memos and the session's RP-language entries, and reaches
anything else **only** through `memo_search`, `session_search` and `web_search`
(`actors.md`). It never writes into the session directly — only into the
roleplayer's answer box.

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

When the LLM is unreachable mid-discussion, the entry and the discussion survive
intact, the failure is visible, and retry is possible (UC-032's exception flow).

The ordering rule that makes this true: **the roleplayer's text is persisted
before any model call is issued**, and a model failure never rolls back that
write. The stream carries an `error` frame; the transcript keeps everything it
already had. Equally, an enormous paste is warned about but **never refused**
(US-035.AC-1, US-035.AC-2) — the warning is a client-side context-cost notice, and
no layer of the stack may turn it into a rejection. See `deployment.md`'s
`client_max_body_size` note, where nginx's default would otherwise convert a
product guarantee into a 413.
