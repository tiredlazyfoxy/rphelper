# Search and retrieval

**Realizes:** FEAT-004, FEAT-005, FEAT-007, FEAT-009, FEAT-012, FEAT-014,
FEAT-015, FEAT-017, FEAT-019, UC-013, UC-016, UC-046, UC-051, UC-052, UC-053,
UC-054, UC-058, UC-059, UC-060, UC-065, UC-075, UC-078

Three distinct search surfaces, one hybrid retrieval engine, one store. The
store decision and its flip condition are in `overview.md`; the tables are in
`data-model.md`.

---

## Hybrid search: vectors + FTS5, fused by reciprocal rank

### Why hybrid rather than one of the two

**Vector-only fails on the exact token.** Notes and entries in this product are
full of proper nouns: character names, partner names, place names, invented terms
from a specific roleplay. An embedding blurs exactly those — "Kaelith" and
"Kaelin" land near each other, and a query for one happily returns the other.
FEAT-012's memos are precisely where a roleplayer writes down "the innkeeper is
called X", so getting that lookup wrong is getting the feature wrong.

**Lexical-only fails on the promise FEAT-015 makes.** UC-053 asks for past
sessions matching "a similar person or situation", found **by meaning**, and
FEAT-015 states semantic-only deliberately: there is no structured matching on
partner name or setup, because the partner is free text and the setup is optional
(challenge C5). BM25 cannot answer "a similar situation".

So: both, fused. The cost of running both is low because both indexes live in the
same database file and both queries run against an already-filtered candidate set.

### Why one store

Recorded in full in `overview.md`. The short form, because it drives everything in
this doc: `memo_search` must filter by a four-level memo chain and by
`is_enabled AND NOT is_forced` — and **both** of those flags change at any time
(UC-044, UC-075). With a separate vector store those filter columns must be
denormalized and kept in sync, making every toggle a second-store write and a
standing drift source in a product with a whole feature (FEAT-005) about
detecting drift. `sqlite-vec` writes vectors **in the same transaction** as the
relational row, and lets the filter be a plain SQL join.

### Reciprocal-rank fusion

Results from the two retrievers are combined by RRF:

```
score(d) = Σ over retrievers r:  1 / (k + rank_r(d))        k = 60
```

RRF rather than a weighted blend of the raw scores, because a cosine distance and
a BM25 score are **not on a comparable scale** and their distributions shift with
corpus size and query length. Normalising them would require tuning constants
against a corpus that does not exist yet. RRF consumes only **ranks**, so it needs
no tuning and no per-corpus calibration — the right default for a greenfield
product with no relevance data.

`k = 60` is the conventional default from the RRF literature and is chosen for
that reason alone. `_TBD: no relevance data exists to tune k, the per-retriever
candidate depth, or the final result count. Defaults are conventional, not
measured._`

### The narrow port

All three surfaces go through one port
(`app/services/search/ports.py`, `backend-structure.md`):

```
search(scope: SearchScope, query: str, limit: int) -> list[SearchHit]
```

where `SearchScope` names the corpus and carries the scope predicates (owner, and
whatever else the surface requires) and `SearchHit` carries an entity kind, an id,
a fused score and a snippet.

The port is deliberately narrow **because of the recorded flip condition**
(`overview.md`): if `session_search` ever needs per-entry embeddings *and*
unscoped cross-character search, N climbs and approximate indexing starts to
matter. A narrow port means swapping the backing store touches one module, not
three features. It is also the enforcement point for scoping: a `SearchScope`
that cannot be constructed without an owner id is a scope that cannot be
forgotten.

### A memo hit is a snippet plus a level — there is no title

`memos` has **no `title` column** (US-119, `data-model.md`) and `memo_fts` indexes
`body` alone. That changes what a memo looks like in every result list, on every
surface:

- **The snippet is the only identifying text a memo hit has.** It is not a
  fallback for a missing title — there is no title to be missing. FTS5's
  `snippet()` over `memo_fts` produces it for the lexical arm; the vector arm
  takes a leading extract of `body`, so both arms yield the same shape.
- **A memo hit carries its chain level** (`scope`, plus the level's name) beside
  the snippet, so a user-level note is distinguishable from a session-level one.
  Snippet plus level is the whole identity of a memo in a result list.
- Nothing may re-introduce a title to make a list look tidier. The column's
  absence is a product statement (US-119), and `data-model.md` records it as one.

### Query shape

The general pattern, for every surface:

```sql
-- 1. relational filter first: produce the candidate id set
WITH candidates AS (
  SELECT id FROM <base>
  WHERE <owner and surface-specific predicates>
)
-- 2a. vector arm: exact KNN over the candidate set
SELECT memo_id, distance FROM memo_vec
WHERE memo_id IN (SELECT id FROM candidates)
  AND embedding MATCH :query_vector
ORDER BY distance LIMIT :depth
-- 2b. lexical arm: BM25 over the same candidate set
SELECT rowid, bm25(memo_fts) AS score FROM memo_fts
WHERE memo_fts MATCH :query_text
  AND rowid IN (SELECT id FROM candidates)
ORDER BY score LIMIT :depth
-- 3. fuse by RRF in the service
```

**Filter first, then rank.** This ordering is the whole basis of the store
decision: the relational predicates collapse N from "every memo in the database"
to the hundreds or low thousands inside one memo chain, so `sqlite-vec`'s
brute-force KNN — **exact**, with no recall parameter to tune and no index to
rebuild after every write — is comfortably fast enough. Filtering *after* ranking
would be both slower and wrong: a top-k over the whole corpus can return k results
the caller is not allowed to see, leaving fewer than k it is.

### The sparse-rowid verification item, carried forward

`data-model.md` records a `_TBD:` under Identifiers: `vec0` tables key on rowid,
and it is **not established** whether they handle sparse, very large snowflake
rowids as efficiently as dense ones. That is not re-decided here — it is
cross-referenced because this doc is where the consequence lands.

It is wider than the vector tables:

- `memo_vec` and `session_vec` key on snowflake rowids — FEAT-014, FEAT-015.
- **FTS5 external content keys on the same rowids** (`content_rowid='id'` on
  `memo_fts`, `message_fts` and `session_fts`), so my-search's lexical arm is
  exposed to the same question — **FEAT-017**.

The contained fallback recorded in `data-model.md` — a surrogate dense key on the
vector tables, mapped to snowflake ids — leaves the rest of the schema untouched,
but note that it covers only the vector half. Verify before FEAT-014 and FEAT-015
are planned, as `data-model.md` requires, and read the result as covering FEAT-017
as well.

---

## `memo_search` — FEAT-014

**Realizes:** FEAT-007, FEAT-012, FEAT-014, UC-046, UC-051, UC-052, UC-075

The assistant's tool for reaching searchable notes across the session's resolved
memo chain.

**Scope predicate**, assembled from the chain (R2) and the two reach flags (R3):

```sql
WHERE memos.user_id = :user_id                    -- FEAT-019, always
  AND memos.is_enabled                            -- R3: gates first
  AND NOT memos.is_forced                         -- R3: consulted only afterwards
  AND (  (scope='user'      AND scope_id = :user_id)
      OR (scope='character' AND scope_id = :character_id)
      OR (scope='setup'     AND scope_id = :setup_id)     -- term OMITTED when NULL
      OR (scope='session'   AND scope_id = :session_id) )
```

Three exclusions, each with its reason from the product:

- **Forced notes are excluded** (`NOT is_forced`) — they are already in the system
  prompt (UC-045, UC-052), so returning them spends a tool call and tokens to tell
  the model something it can already see.
- **Disabled notes are excluded** (`NOT is_enabled`) — they reach the assistant by
  no path (R3, UC-052, US-100). This must be tested as an **absence**, not
  inferred from the predicate looking correct.
- **Another user's notes are excluded** — by the `user_id` predicate, at the query
  level (UC-065).

**Predicate ordering is part of the rule, not a style note.** R3 requires
`is_enabled` to gate first and `is_forced` to be consulted only afterwards, and
that ordering must survive into every query written here. Under the earlier single
`state` column a three-valued equality made the mistake unexpressible; **two
booleans make it expressible**, and selecting on `is_forced` alone now returns —
or, in context assembly, prompts — a *disabled* forced note. That is the exact
leak R3 forbids. Both predicates appear in every memo query and `is_enabled` is
never dropped as "implied by the other one". Context assembly's mirror predicate
is `is_enabled AND is_forced`, for the same reason
(`llm-and-streaming.md`, UC-045).

**It works with no setup level present.** The setup term is simply absent from the
disjunction when `sessions.setup_id IS NULL`, so the chain is
`user + character + session` with **no gap** (FEAT-007, UC-046, UC-051's
postcondition). This is the same query with one fewer OR-term — not a second code
path — which is why the memo table uses one polymorphic `(scope, scope_id)` pair
(`data-model.md`). A no-setup session is a required test case for this tool, not
an edge case.

**Failure**: `tool_failed` → a `tool_fail` frame → the discussion continues and the
assistant is told (R9, UC-051's exception flow).

---

## `session_search` — FEAT-015

**Realizes:** FEAT-015, FEAT-019, UC-053, UC-054

The assistant's tool for finding past sessions under the same character, by
meaning.

**Semantic only.** FEAT-015 states this deliberately: no structured matching on
partner name or setup, because the partner is free text and the setup is optional
(challenge C5). Semantic search is what keeps the "same person or situation"
promise true when neither is present.

### Settled: `session_search` runs the **vector arm only**

**This is the one surface where the lexical arm is switched off.** It was an open
question and it is now decided: `session_search` runs the vector arm and **no BM25
arm**, so there is no RRF step in this surface at all — the vector ranking *is* the
ranking.

The reason is a product decision rather than an engineering preference. Enabling
BM25 over `session_fts` would **reintroduce by the back door the structured
partner-and-setup matching FEAT-015 deliberately rejected** (challenge C5): the
lexical index's columns are `title` and `partner_label`, so a BM25 arm is, in
practice, a partner-name matcher. FEAT-015 rejected structured matching because
the partner is free text and the setup is optional — so a name match is exactly
the signal that is absent in the cases the feature exists to serve.

**`session_fts` is kept.** It serves FEAT-017's my-search (UC-058), which is a
different surface, a different caller and a different rule — a roleplayer typing a
partner's name into their own search box wants exactly the lexical match the
assistant must not get. The table's existence is not evidence that
`session_search` should use it.

**Reversible at low cost, and the flip condition is named.** Turning the arm on
later is a one-surface change: `session_fts` already exists, the port already
fuses two arms elsewhere, and nothing in the schema would move. The condition that
would justify it: if FEAT-015's promise — finding "the same person or situation"
**when neither is recorded** — turns out in practice to need lexical recall.
That is a relevance finding, not a design argument, so it needs evidence from real
use. Until then: nobody "improves" `session_search` by turning the second arm on.

**Scope predicate — a privacy boundary, not a filter:**

```sql
WHERE sessions.user_id     = :user_id       -- never crosses a user   (UC-054)
  AND sessions.character_id = :character_id -- never crosses a character (UC-054)
  AND sessions.id          != :current_session_id
```

Both predicates are in the query, applied before ranking. UC-054's postcondition —
"No session belonging to another character or another user is ever returned" — is
tested with data that would match semantically and must still be absent.

The unit of result is a **past session**, not an entry, which is why `session_vec`
embeds a session-level text (`data-model.md`). Two things about that text are
already fixed and are not the plan's to choose:

- It is composed from the **`settled_entries` view** (`data-model.md`, R11), so a
  current-zone message is never findable by `session_search` (US-115) and buried
  scaffolding never is either (UC-038).
- It must include settled **decisions**: US-122.AC-2 requires a settled decision
  to appear in `session_search` results, so the composition cannot be narrowed to
  `kind='turn'` rows.

`_TBD: docs/product/ does not specify what text represents a session for semantic
matching beyond those two constraints; UC-053 says only "by meaning, for a similar
person or situation". The composition is left to FEAT-015's plan. When it is
recomputed is no longer open — see the embedding lifecycle below._`

Excluding the current session is a design inference, not a stated requirement:
returning the session the assistant is already fully reading would waste the call.
Recorded as an inference so it can be challenged.

**Failure**: `tool_fail`, discussion continues (UC-053's exception flow).

---

## My-search — FEAT-017

**Realizes:** FEAT-017, FEAT-019, UC-058, UC-059, UC-060, UC-065

**This is not the same thing as the two tools above**, and the product says so
outright. Challenge C7 proposed they were an overlap and the user rejected it:
"tool search is the content search, my search is on user level UI to find the
sessions i did. Totally different functionality." FEAT-014/015 are **content
retrieval performed by the assistant mid-discussion**; FEAT-017 is a **user-level
UI for finding sessions the roleplayer ran**.

The distinction has real architectural consequences, which is why it is restated
here rather than treated as a naming nicety:

| | `memo_search` / `session_search` | my-search |
|---|---|---|
| Caller | ACT-004, inside a discussion | ACT-002, from any screen (UC-058) |
| Corpus | one memo chain / one character's sessions | characters, setups, sessions, entries **and** memos (UC-058) |
| Memo flag predicate | `is_enabled AND NOT is_forced` | **none at all** — disabled notes included; see below |
| Result unit | content for the model | a navigable pointer for a human (UC-060) |
| Output | tool message into the model's context | grouped result list (UC-059) |

- **Reaches everything the roleplayer owns** (UC-058): characters, setups,
  sessions, entries and memos. Five corpora, so five `SearchScope` variants
  through the same port. That count is unchanged as a product matter; what changed
  is the mechanism behind "entries" — see below.
- **Results are grouped by kind** (UC-059) — character, setup, session, entry, memo
  — so RRF fuses *within* a kind and the groups are presented separately. There is
  no cross-kind global ranking, because UC-059 asks the roleplayer to scan by kind
  rather than as one flat list. A memo group's rows are **snippet plus chain
  level** (see the port section); there is no title column to show.
- **Every result jumps to the session or entry it points to** (UC-060), so a hit
  carries enough identity to route: for an entry, its **session id and its own
  message id**. There is no position to cite — `ORDER BY id` *is* the stream order
  and the `position` column is gone (`data-model.md`).
- **Never includes another user's material** (FEAT-017's note, UC-065) — the
  `user_id` predicate is in every one of the five queries.
- It is a **UI surface, not a tool.** It is never exposed to ACT-004; the
  assistant's reach is exactly three tools (R9).

### The entry corpus is the `settled_entries` view

The `entries` table is gone: entries, discussions and discussion messages are one
`messages` table with two views over it (`data-model.md`). My-search's "entry"
corpus therefore reads the **`settled_entries` view**, never raw `messages`
(R11). Two guarantees follow and both are testable as absences:

- **Buried current-zone chatter can never surface in my-search** (UC-038's
  boundary, US-116) — it is not in the view.
- **A live draft can never surface either** (US-115) — a current-zone message is
  not record, and the roleplayer searching their own material is looking for the
  record.

The lexical index is **`message_fts`**, renamed from `entry_fts` with the table it
indexes. It keeps its external content on the base table `messages`, because FTS5
external content requires a real rowid table, and the triggers — insert on the
settle transition, delete on re-open, update on a settled text edit — restrict it
to settled rows (`data-model.md`). The view boundary and the trigger condition say
the same thing in two places on purpose: whichever arm a reviewer checks, the
answer is the same.

### Settled: my-search **does** show disabled notes

Decided. My-search applies **no `is_enabled` / `is_forced` predicate at all** —
forced, searchable and disabled notes are all returned. Only the `user_id`
predicate applies.

The reasoning, in two parts:

- **R3 constrains the assistant, not the owner.** "Reaches the assistant by no
  path" is a statement about ACT-004's inbound surfaces: context assembly,
  `memo_search`, `session_search`, tool results and error payloads. My-search is
  **ACT-002's own UI over their own material** (UC-058) and is never exposed to
  ACT-004 (R9). Applying R3 here would apply a rule about the model's reach to the
  author's own filing cabinet. R3 itself now says so.
- **Hiding a disabled note makes it unreachable, which breaks UC-044.**
  Re-enabling requires *finding* it first, and re-enabling is an explicit alternate
  flow (UC-044) that restores the note's prior forced state (US-101). A roleplayer
  who disabled a note months ago and now wants it back has my-search as the tool
  for finding it. A search surface that cannot find the thing whose only route back
  is being found is a dead end.

**A disabled hit is visibly marked as disabled** in the result list, so the
roleplayer is not misled into thinking the assistant can see it. The note wall
already renders both flags in place (UC-075, `workspace-shell.md`). `_TBD: the
exact presentation of a disabled hit in the my-search result row — a badge, a
muted row, a state column — is not specified; nothing in docs/product/ describes
the result row's anatomy beyond UC-059's grouping and UC-060's navigability._`

**What does not change:** a note with `is_enabled = false` remains absent from
`memo_search`, from `session_search` and from context assembly, and the negative
tests for those three stand exactly as R3 states them. Showing a note to its owner
is not a path to the assistant.

**This is a requirements gap resolved at the architecture layer.**
`docs/product/` does not state either way — UC-058 says my-search reaches the
roleplayer's own memos and says nothing about reach flags, and FEAT-017's
acceptance criteria are silent. **`/product-spec` should ratify it into FEAT-017's
acceptance criteria**; until it does, FEAT-017's plan binds to this doc and this
doc is the only record of the choice.

---

## Embedding lifecycle

**Realizes:** FEAT-004, FEAT-005, FEAT-009, FEAT-012, FEAT-014, FEAT-015,
UC-013, UC-016, UC-044, UC-078

**The designated embedding model** (UC-013) is the single source of vectors. Its
dimension is recorded on the `models` row and is what the `vec0` tables are
declared with (`data-model.md`).

**When embeddings are written.** In the **same transaction** as the relational
write that made them stale:

| Trigger | Re-embed |
|---|---|
| memo created | its `memo_vec` row |
| memo body edited (UC-043, US-104) | its `memo_vec` row |
| `is_enabled` or `is_forced` changed (UC-044, UC-075) | **nothing** — both are filter columns, read at query time |
| memo reordered (`sort_key`, UC-076) | **nothing** — order is not embedded |
| settle (R11) | the session's `session_vec` row |
| a settled message's text edited (UC-078, US-110) | the session's `session_vec` row |
| re-open (R11) | the session's `session_vec` row |
| a current-zone message written or edited | **nothing** — the zone is not record (US-115) |

The two "nothing" rows for the reach flags are the payoff of the store decision,
stated plainly: because the filters live in relational columns in the same
database, toggling `is_enabled` or `is_forced` is a one-row update with **no
vector work and no second store to reconcile**. In a split-store design each
toggle would be a cross-store write, and FEAT-012 makes those toggles routine.

### Settled: the session-refresh policy, decided by product

The earlier `_TBD:` here deferred to FEAT-015's plan whether and when
`session_vec` is refreshed as a session grows. **US-110.AC-2 closes it**: after an
edit to any settled entry, `session_search` must reflect the new text, not the
original. A policy of "re-embed occasionally", "on session close" or "on a
schedule" cannot satisfy an acceptance criterion phrased as *when the assistant
later calls `session_search`* — any gap is a window in which the criterion is
false.

So `session_vec` is refreshed **in the same transaction** as each of the three
writes that change what the record says: **settle, a settled-message text edit,
and re-open**. Those are the only writes that move a row into, out of, or within
`settled_entries`, so nothing else needs a refresh — which is why the current
zone contributes none.

`_TBD: the COST of that policy is not measured. session_vec embeds a
session-level text composed from settled_entries, so every settled edit re-embeds
a text that grows with the session, and a long RP makes each edit more expensive
than the last. Whether that stays acceptable, and whether the composed text should
be bounded, is for FEAT-015's plan. What is NOT open is whether the refresh
happens: US-110.AC-2 requires it._`

### Failure mode, and a deliberate asymmetry between two write paths

If the designated embedding model is absent or has changed, the embed call raises
**`no_embedding_model`** and **never substitutes another model**
(`llm-and-streaming.md`, R4). A different embedding model produces vectors that
are not comparable with the stored ones, so a substitution returns confidently
wrong results — strictly worse than an error. A *tool* that cannot embed its query
fails as `tool_fail` and the discussion continues (R9).

What differs is what the **write** paths do with that error:

| Write | Embedding unavailable |
|---|---|
| memo create / body edit | **fails the transaction** — nothing is stored |
| message edit, settle, re-open (`session_vec`) | **succeeds, degraded** — the row is stored and the response says search coverage is incomplete (US-112) |

**This reverses, for one of the two paths, what this doc previously stated for
both — and the asymmetry is deliberate, recorded so nobody harmonises it later.**
They are right for different reasons:

- A memo exists **in order to be retrieved**. A memo with no vector is a note that
  silently does nothing, and FEAT-005's drift check is the mechanism that would
  have caught it — which only stays meaningful while a memo without a vector row
  is genuinely an anomaly. So the whole transaction fails.
- A settled entry is **the record of what happened in the roleplay**. Refusing to
  save it because an instance-level designation is missing would let an
  administrator's omission block a roleplayer's own record-keeping, which US-112
  rules out in exactly those terms: the edit saves, and the roleplayer is told
  search coverage is incomplete (UC-078's exception flow).

Consequences to hold:

- **A missing or stale `session_vec` row is an expected state, not drift.**
  FEAT-005's report must not flag it the way it flags a memo with no `memo_vec`
  row; UC-016's rebuild is its remedy. The memo-side invariant is unaffected.
- **Nothing records *which* sessions carry a stale vector**, so the remedy is the
  whole-index rebuild (UC-016) rather than a targeted re-embed. `_TBD: whether a
  per-session staleness marker earns its column is raised, not decided — it would
  be a data-model change and is not made here. Today's answer is the rebuild._`
- The roleplayer-facing half is a banner above the stream (US-112,
  `workspace-shell.md`); the backend half is a caught `no_embedding_model`
  reported in the write's own response (`backend-structure.md`, which carries the
  same table).

---

## Index rebuild — FEAT-005

**Realizes:** FEAT-005, UC-014, UC-015, UC-016

UC-016 is a distinct admin operation from drift remediation (UC-015), and
`data-model.md` records why: remediation fixes **structure** (DDL, cheap), rebuild
recomputes **content** (re-embeds every memo and session against the designated
embedding model — real time, real LLM calls, real cost on a metered provider).

Rebuild does:

1. Validate the designated embedding model (`no_embedding_model` if absent).
2. Re-declare the `vec0` tables if `embedding_dim` has changed.
3. Re-embed every memo and every session, **for every user**.
4. Rebuild the FTS5 indexes from their external content tables.
5. Report completion (UC-016 step 3).

It is also the remedy for the degraded path above: every session whose
`session_vec` went stale while no embedding model was designated comes back into
coverage at step 3, with no record of which sessions those were and none needed.

**Step 3 is the one place in the system where a single operation touches every
user's content, and it must not become a privacy hole.** The rebuild reads memo
bodies and session text to embed them; it returns **no content** to the
administrator — the report is counts and completion only (UC-066, R5). No per-user
breakdown, no sample, no progress line naming a character. The administrator
learns that the index was rebuilt, not what is in it.

Changing the designated embedding model requires a rebuild rather than taking
effect silently, because pre-existing vectors came from the old model and are not
comparable with new ones. `_TBD: docs/product/ does not say whether changing the
designation should force, prompt for, or merely permit a rebuild (UC-013 and
UC-016 are separate use cases with no stated linkage). Until it does, the two stay
separate operations and the semantic tools may return degraded results in
between — recorded as a known consequence rather than resolved by invention._`
