# Search and retrieval

**Realizes:** FEAT-004, FEAT-005, FEAT-006, FEAT-007, FEAT-009, FEAT-012,
FEAT-014, FEAT-015, FEAT-017, FEAT-019, UC-013, UC-016, UC-018, UC-046, UC-051,
UC-052, UC-053, UC-054, UC-058, UC-059, UC-060, UC-065, UC-075, UC-078, UC-088,
US-110, US-112, US-119, US-121, US-122, US-137, US-138, US-141, US-145, US-147

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

**As built** (025 D1): **`k = 60`, per-arm candidate depth 50, and the final
result count supplied by the caller.** Ties break on **ascending id**, so a
result list is deterministic rather than dependent on which arm happened to be
read first. **A single-arm scope is still fused over its one ranking**, which
reads like a pointless step and is not: it makes `score` mean the same thing on
every surface, so a caller comparing or logging scores never has to know how many
arms its variant runs.

`k = 60` is the conventional default from the RRF literature and is chosen for
that reason alone. **All the numbers in this doc are of that kind**, and the
`_TBD:` covering them stays open:

`_TBD: none of the retrieval constants is measured. k = 60, the per-arm depth of
50, and the result counts — 8 for memo_search, 5 for session_search, 20 per group
for my-search — are conventional and user-confirmed, not tuned. No relevance data
exists to tune them against, and there is no corpus to tune them on until the
product has real use. Recorded together so a later measurement pass has one list._

### The narrow port

All three surfaces go through one port, whose contract and pure helpers live in
`app/services/search/ports.py` and whose implementation is
`app/services/search/hybrid.py` (`backend-structure.md`):

```
search(connection, scope, query, limit, *, client_factory, timeout_seconds)
    -> list[SearchHit]
```

- **`SearchScope`** names the corpus and carries the scope predicates, and
  **`SearchHit`** carries an entity kind, an id, a fused score and a snippet.
- **The embedding parameters are in the signature because the vector arm embeds
  the query** through 024's embedding service (025 U1). They are keyword-only
  with the caller supplying the factory and the configured timeout, so the port
  stays free of `Settings` and of FastAPI.

The port is deliberately narrow **because of the recorded flip condition**
(`overview.md`): if `session_search` ever needs per-entry embeddings *and*
unscoped cross-character search, N climbs and approximate indexing starts to
matter. A narrow port means swapping the backing store touches one module, not
three features. It is also the enforcement point for scoping: a `SearchScope`
that cannot be constructed without an owner id is a scope that cannot be
forgotten.

#### Three variants, and the variant fixes the arms

Plan 025 shipped **three** `SearchScope` variants, and **the variant decides
which arms run — no caller chooses arms**:

| Variant | Arms | Over |
|---|---|---|
| **memo** | vector **+** lexical, fused by RRF | `memo_vec`, `memo_fts` |
| **session** | **vector only** | `session_vec` |
| **entry** | **lexical only** | `message_fts`, scoped to `settled_entries` |

Arms belong to the variant rather than to the call because *which* arms are right
for a corpus is a property of that corpus and its product rules — the session
variant's missing lexical arm is a FEAT-015 decision (below), not a tuning knob —
and a caller that could switch arms could switch off the one that carries the
guarantee.

**Characters and setups are not variants.** No index exists for either, so a port
variant over them would carry no arm at all; my-search matches them with `LIKE`
outside the port (below), which is the one deviation from "all surfaces go through
one port".

#### The extra-predicate mechanism

**The port applies `user_id = :user_id` itself, in every statement — including
hit hydration** (025 U1, D6). A variant *requires* an owner id; there is no shape
of the call that omits it.

Beyond that, a variant accepts an **optional clause builder**: given the
variant's base relation, it returns a boolean clause that the port **ANDs with
the owner predicate**. That is how the callers bring their own filters without
the port learning their rules:

- **`026`** brings the memo chain plus `is_enabled AND NOT is_forced`, in R3's
  order. **The port neither adds nor reorders it** — R3's ordering is the
  caller's to get right, and `memo_search` has a test that pins it on the
  compiled clause.
- **`027`** brings `character_id`, `id != :current_session_id` and
  `archived_at IS NULL`.

A builder rather than a growing union of named filters, because every surface's
predicate is different and a port that knew them all would be the three features
wearing one filename.

**The tools' scope comes from the seam, never from tool arguments** (021 D6).
`memo_search` and `session_search` build their `SearchScope` from the seam's
`ToolScope` ids (R9, `session-stream.md`), so the owner — and, for
`session_search`, the character — reaches the port from the authenticated session
and not from anything the model wrote.

### A memo hit is a snippet plus a level — there is no title

`memos` has **no `title` column** (US-119, `data-model.md`) and `memo_fts` indexes
`body` alone. That changes what a memo looks like in every result list, on every
surface:

- **The snippet is the only identifying text a memo hit has.** It is not a
  fallback for a missing title — there is no title to be missing. **As built**
  (025 U3, D4) the lexical arm uses FTS5 `snippet()` — plain text, **no
  highlight markers**, ellipsis `…`, 16 tokens — and the vector-only arm takes a
  **leading extract of `body`**: whitespace collapsed, 160 characters, `…` when
  truncated. **The same plain-text shape from both arms**, deliberately, so a
  fused list does not render two visibly different kinds of snippet depending on
  which arm found a row.
- **A memo hit carries `scope` and `scope_id`** beside the snippet, so a
  user-level note is distinguishable from a session-level one. **The port does no
  name join** (025 U3): a caller that wants a level's *name* resolves it itself.
  The port's job is retrieval, and joining four possible parent tables to label a
  hit would make every query carry four LEFT JOINs for a string one surface
  shows. On the **tool** surface the level reaches the model as the **scope
  literal only** — no character or setup name, no ids (026 D4).
- Nothing may re-introduce a title to make a list look tidier. The column's
  absence is a product statement (US-119), and `data-model.md` records it as one.

**`SearchHit` as built** (025 D3): kind, id, fused score, snippet, plus a memo's
`scope` / `scope_id` and an entry's `session_id`. **A session hit's snippet is
none** — `sessions` has no text column at all, so there is nothing for the port to
extract; what represents a returned session to the model is `session_search`'s own
decision and is recorded under that tool.

### Query shape

The general pattern, for every surface:

```sql
-- 1. relational filter first: produce the candidate id set
WITH candidates AS (
  SELECT id FROM <base>
  WHERE <owner and surface-specific predicates>
)
-- 2a. vector arm: an exact SCAN over the candidate set, ordered by distance.
--     NOTE: no MATCH and no k — see "The forbidden KNN form" below.
SELECT memo_id FROM memo_vec
WHERE memo_id IN (SELECT id FROM candidates)
ORDER BY vec_distance_l2(embedding, :query_vector) LIMIT :depth
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

**L2 is the metric, and the metric's scale does not matter.** Only the **rank**
reaches fusion (RRF consumes ranks alone), so nothing downstream depends on
whether the distance is L2, cosine or anything else monotonic in the same order.
Recorded so a later change of metric is understood to be a relevance decision and
not a compatibility one.

#### The forbidden KNN form, and the two correct ones

**This is the single most important query rule in the doc.** `data-model.md`
records the empirical result and the sqlite-vec defect behind it; the query forms
are owned here, once, and `data-model.md` cross-references this section rather
than repeating it.

> **FORBIDDEN:** a `vec0` KNN with a **pushed-down id constraint** —
> `… WHERE embedding MATCH ? AND k = ? AND <id> IN (...)`.
> On sqlite-vec 0.1.9 it **silently drops true candidates** for ids above roughly
> 2^50 — false negatives only, in 18–36% of queries. Snowflake ids are in that
> range from the start (`data-model.md`'s Identifiers).

It is forbidden rather than discouraged because the failure is **silent and
partial**: the query returns results, they are simply missing rows that should
have been there, and nothing in the result set says so. A search that quietly
loses a third of its hits is worse than one that errors.

The two correct forms:

- **(a) an exact scan over the candidate set** —
  `SELECT memo_id FROM memo_vec WHERE memo_id IN (SELECT id FROM candidates)
  ORDER BY vec_distance_l2(embedding, :q) LIMIT :n`. No `MATCH`, no `k`. Exact,
  and fast for the hundreds of rows the relational filter leaves.
- **(b) an over-fetching KNN, then a join** — run the KNN unfiltered with a
  larger `k`, then JOIN to candidates or use **`+memo_id IN (...)`**. The
  **unary plus is what blocks the pushdown** and therefore the defect; without it
  this form *is* the forbidden one.

**As built, plan 025 uses form (a) only** and does not use (b) (025 D5). Form (a)
needs no over-fetch factor to guess at and cannot be accidentally written as the
forbidden form, which is worth more here than the theoretical speed of an index
scan over a candidate set this small. **Flip condition:** a sqlite-vec release
that fixes pushdown at large rowids makes the natural form safe again, and (b)
becomes worth revisiting if the candidate sets ever grow past "fast enough".

**The FTS5 lexical arm is unaffected** by any of this.

#### User text can never raise an FTS5 syntax error

FTS5 `MATCH` takes a query *language*, so raw user text reaches it as syntax — a
stray `"` or a bare `NEAR` is a parse error, not a search for those characters.
**The sanitising rule** (025, step `001`): split the user's text on whitespace,
remove `"`, quote each token as an FTS5 **phrase**, and OR-join the phrases. **No
usable token means the lexical arm is skipped entirely**, not that it runs with an
empty query.

Stated as an invariant because the alternative — catching the syntax error — turns
a roleplayer's punctuation into a failed search, and in my-search it would fail
the whole request (below).

### Sparse snowflake rowids — verified, and the `_TBD:` is closed

The question this section carried — whether `vec0` and FTS5 external content
handle sparse, very large snowflake rowids as well as dense ones — **was measured
and is closed** (024 D3, U6). `data-model.md` holds the result; the short form:

- **Snowflake ids stay the keys, and there is no surrogate dense key.** The
  contained fallback that was held in reserve is not needed and was not built.
- **Measured** on sqlite-vec 0.1.9 / SQLite 3.47.1 with 5000 × 768-d vectors:
  insert, table size and **unfiltered** KNN are identical for dense and snowflake
  ids, and FTS5 external content with conditional triggers passes
  `integrity-check` at around 2^60.
- **The one real defect is the pushdown form above**, which is why it is forbidden
  rather than merely avoided.

It reached further than the vector tables and that is why it was worth measuring:
`memo_vec` and `session_vec` key on snowflake rowids (FEAT-014, FEAT-015) and
**FTS5 external content keys on the same ids** (`content_rowid='id'` on `memo_fts`
and `message_fts`), so my-search's lexical arm had the same exposure (FEAT-017).

### Every write to a derived store resolves its ids through an owner-scoped query

**The `vec0` and FTS5 tables have no user column** — `memo_vec`, `session_vec`,
`memo_fts` and `message_fts` carry a row id and the derived data, nothing else.
Reads are safe because the port's candidate set is built from an owner-scoped
relational query first (above), and a hit can only name a row the filter already
allowed.

**Writes have no such protection, and this is the rule that supplies it**
(plan 032, step 004). `write_vector` and `delete_vector` take **no user id**, so
**the owner predicate must live in the calling service's own SQL**: every write to
a derived store resolves the row ids it is going to touch through an
**owner-scoped query first**, and then writes those ids.

Recorded as a rule rather than a note because it is the **one leak plan 032's
audit actually found** — a `session_vec` empty-text delete that computed its ids
without the owner predicate. The proof that the rest holds is
`backend/tests/test_privacy_audit_search_tools.py`, which is the cross-user
evidence for my-search, the hybrid port, the three tools and the vector/FTS write
paths together. A fix to defect D-04 (below) adds a delete on the degraded path
and is therefore directly bound by this rule.

### The query-side no-model rule — no lexical-only degrade

**Whenever a variant's vector arm runs, the designated embedding model is
required** (025 U2). `no_embedding_model` — including the
`{"reason": "dimension_mismatch"}` form — `secret_ref_missing` and
`llm_unreachable` **propagate unchanged**, and **there is no lexical-only
fallback**.

That is R4 applied to the query side: a hybrid result computed from one arm is not
a worse version of the same answer, it is a *different* answer presented as the
same one, and the caller has no way to tell. Failing is the honest outcome, and
the remedy is visible (designate a model, or fix the credential).

Two boundaries on it:

- **An absent or empty `vec` / FTS table is not an error.** That arm simply yields
  no hits. The tables are ensured on write (`data-model.md`), so "not created yet"
  is a normal early state, and after a whole-database replace it is a normal
  post-restore state (`transfer.md`).
- **A `vec` table whose declared dimension differs from the designation raises
  `no_embedding_model` with `{"reason": "dimension_mismatch"}` before any
  provider call** — there is no point embedding a query into a space the stored
  vectors are not in.
- **The entry variant never opens the model at all**, being lexical-only.

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

**Where the scope predicate lives — one home, two consumers** (026 D2). The chain
disjunction above is **one clause builder in `services/memo_chain.py`, beside
`resolve_chain`**, taking a relation and the level ids and omitting the setup term
when there is no setup. `services/search/memo_search.py` builds the port's extra
predicate as **`is_enabled AND NOT is_forced AND <chain>`**, with `is_enabled`
first, and the port ANDs `user_id`. **A test pins R3's order on the compiled
clause**, which is what turns the ordering rule into something a build can fail.
One home because R2's chain is one rule: the prompt's forced selection and the
tool's searchable selection must agree about what "this session's chain" means,
and two hand-written disjunctions are two chances for them to drift.

**Result count: at most 8, no paging** (026 D1). The count is a **named constant
in `services/search/memo_search.py`** passed to the port as `limit`, and the tool
**declaration stays `query` only** — no `limit`, no offset, no cursor. An
assistant that wants different notes re-queries with different words, which is the
behaviour the product describes; a paging parameter would invite the model to walk
a corpus instead of searching it. 8 is conventional and user-confirmed, **not
measured** (the fusion `_TBD:` above).

**What the model receives** (026 D4). One line per hit, in fused-rank order:

```
[<level>] <snippet>
```

where `<level>` is the **scope literal** and the snippet's whitespace is collapsed
so each hit is exactly one line; lines are joined by `\n`. **No title, no
character or setup name, no ids.** Zero hits is a **success** whose content is
`No matching notes.` — not a failure, because "nothing matched" is an answer the
assistant can act on. The `tool_result` summary is `<N> memos` and **never carries
content** (the SSE protocol's summary rule).

**Failure: the tool raises and never builds its own failure outcome** (026 D5).
`no_embedding_model`, `llm_unreachable` and `secret_ref_missing` propagate from
the port, and arguments without a string `query` raise `tool_failed`. **021's seam
is what turns any of them into the `tool_fail` frame and the fixed "tool failed"
model message** (R9, UC-051's exception flow) — so the discussion continues and
the assistant is told. One failure path rather than two: a tool that constructed
its own "I failed" outcome would bypass the frame the client renders.

**It runs the sync port off the event loop** (026 D3), which closes the flag plan
025 raised. `run` is async and the port is sync — and, on the vector arm, embeds
through 024's `asyncio.run` bridge, which raises inside a running loop. So the
adapter calls the port through **`asyncio.to_thread`, on the connection the seam
handed it**. Safe because the engine sets `check_same_thread=False` and the
connection is used by one thread at a time (`backend-structure.md`), and the
worker thread has **no running loop**, so the embed bridge works there.
`session_search` reuses the pattern.

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
arm**. The vector ranking *is* the ranking — it still passes through fusion over
that one ranking, so `score` means the same thing here as everywhere else
(025 D1), but nothing is being blended.

**The product reason stands on its own, and it is the one that matters.**
FEAT-015 deliberately rejected structured matching on partner name or setup
(challenge C5), because the partner is free text and the setup is optional — so a
name match is exactly the signal that is *absent* in the cases the feature exists
to serve. A lexical arm over session-level text would reintroduce that matching by
the back door.

**The engineering half of the old argument has gone with its subject, and the
correction matters.** This section used to add that `session_fts`'s columns are
`title` and `partner_label`, "so a BM25 arm is in practice a partner-name
matcher". **`sessions` has neither column** (011 D4): a session is identified by
its start time, not a title (`US-145`), and there is no partner column. So
**`session_fts` was declared and never created** (024 U7) — it waits on a feature
that gives a session text columns, and no feature has. The sentence that claimed
it "exists for FEAT-017's my-search" was **stale and is removed**:
**my-search's session corpus is the vector arm over `session_vec`** (029 U2), not
a lexical index.

**The flip condition is named, and it is now larger than one switch.** Turning a
lexical arm on would require **first creating a session text index at all**, which
in turn requires a session to have text columns to index. The relevance condition
that would justify starting that work: if FEAT-015's promise — finding "the same
person or situation" **when neither is recorded** — turns out in practice to need
lexical recall. That is a relevance finding, not a design argument, so it needs
evidence from real use. Until then: nobody "improves" `session_search` by turning
a second arm on, and nobody creates `session_fts` because its declaration exists.

**Scope predicate — a privacy boundary, not a filter:**

```sql
WHERE sessions.user_id      = :user_id       -- never crosses a user      (UC-054)
  AND sessions.character_id = :character_id  -- never crosses a character (UC-054)
  AND sessions.id          != :current_session_id
  AND sessions.archived_at IS NULL           -- archived sessions never returned (027 D1)
```

The owner term is the **port's own** (it ANDs `user_id` in every statement); the
other three are built in `services/search/session_search.py` as the extra
predicate. All of them are in the query, applied before ranking. UC-054's
postcondition — "No session belonging to another character or another user is ever
returned" — is tested with data that would match semantically and must still be
absent.

**The archive term is a user-confirmed decision, not an inference** (027 D1), and
three things follow:

- **The term is on the *session* only.** A session whose *setup* is archived stays
  searchable — R6 does not cascade, and the session itself is still in the working
  record.
- **Restoring a session makes it findable again with no re-embed**, because the
  fan-out keeps archived sessions' vectors current (below). The archive filter is
  a *query* decision; the index is maintained either way.
- It is a **deliberate asymmetry with my-search**, which *includes* archived
  material and marks it "Archived" (below). The owner looking for their own past
  work wants the archive; the assistant composing the current turn does not —
  R6's whole statement is that archiving removes something from the working list,
  and the assistant only ever works in the present one.

**Excluding the current session is implemented** (027 D1): `id !=
:current_session_id` is in the predicate, tested with a current session whose
vector is identical to the query's. It remains an inference about *value* — the
assistant is already reading the current session in full, so returning it would
spend a tool call to say nothing — rather than a product requirement. Recorded as
an inference so it can be challenged, now with the note that it is built.

### What text represents a session — settled; the `_TBD:` here is closed

The unit of result is a **past session**, not an entry, which is why `session_vec`
embeds a session-level text (`data-model.md`). **US-138 settles what that text
is**, closing the `_TBD:` this section carried. It spans **three sources**:

```
session_vec text  =  the character's persona            (characters.sheet)
                  +  the setup text                     (setups.description,
                                                         absent when there is no setup)
                  +  the session's settled entries      (settled_entries selectable,
                                                         id order, INCLUDING decisions)
```

**The order is persona, then setup, then entries — and the order is load-bearing**
(024 D6). Empty parts are dropped and the rest joined with a blank line.
**Persona and setup lead so that model-side truncation of a long session cannot
drop them**: an embedding provider that truncates its input does so at the end, and
US-138.AC-2's "similar person" half is satisfiable *only* from the persona. Put
last, the two parts that make the feature's second promise true would be the first
things a long session loses. **An empty composed text means no `session_vec` row
at all** — nothing is embedded and nothing is stored.

The two constraints that were already fixed are unchanged by the addition:

- It is composed from the **`settled_entries` selectable** (`data-model.md`, R11),
  so a current-zone message is never findable by `session_search` (US-115) and
  buried scaffolding never is either (UC-038).
- It must include settled **decisions**: US-122.AC-2 requires a settled decision
  to appear in `session_search` results, so the composition cannot be narrowed to
  `kind='turn'` rows.

**Why the persona and the setup are in there at all**, since a session's own
entries look like the obvious and complete answer: US-138.AC-2 asks for a query
describing a **similar person** rather than a similar situation to find the
session **even when its entries do not describe the query**. That is not
satisfiable from the entries — the person is described in the character's
persona, and the situation in the setup, and a session's prose frequently assumes
both rather than restating them. Adding them is the only way the feature's
"similar person" half is true at all; without them `session_search` matches
*what happened*, never *who it was with*.

The setup term is simply absent when `sessions.setup_id IS NULL` — the same
degrades-with-no-gap shape as R2's memo chain, not a second composition path.

### What the model receives — and the deliberate asymmetry with the match text

This closes the question of what represents a returned session to the model
(027 D3, which is also where plan 025's "the tool decides" flag lands).

**Result count: at most 5, no paging** (027 D2). A named constant passed as
`limit`; the declaration stays `query` only. **Lower than `memo_search`'s 8
because each hit carries a long excerpt** — five sessions of 1500 characters is
already a large share of a context window, and eight would be most of one. The
count is conventional and user-confirmed, **not measured** (the retrieval-constants
`_TBD:` above).

Results arrive in rank order, **one block per hit** (027 D3):

```
### Session <YYYY-MM-DD> · setup: <name>        (or "… · no setup")
<the last 1500 characters of the session's settled_entries text>
```

- The date is `created_at` as a **UTC date**; the setup's name is shown **even
  when the setup is archived**, because the label is what identifies the session
  to the model and R6 does not cascade.
- The excerpt is the session's `settled_entries` text in **ascending id**, joined
  by a blank line, **decisions included**. A cut excerpt **starts with `…`**.
- A session with **no settled entries** shows `(no settled entries)`.
- **No persona, no setup description, no ids.**
- **Zero hits is a success** with content `No matching sessions.`; the
  `tool_result` summary is `<N> sessions`.

**The asymmetry with the match text is deliberate.** The text a session is
*matched* by includes the persona and the setup description (above); the text a
result *shows* does not. They are answering different questions: the persona is
what makes "a similar person" findable, and once the session has been found,
repeating the persona of the character the assistant is *already playing* would
spend context restating what the system prompt already says. The result's job is
to show what happened in that session.

**The port returns ids and scores only for sessions** (027 D4) — it has no text
column to snippet. The header and the excerpt come from `session_search`'s **own
owner-scoped read** by `user_id` and the hit ids, **in hit order**, with the
1500-character bound applied in the service. So the excerpt is not a port feature
that other callers inherit.

**Failure: the tool raises** (027 D5), exactly as `memo_search` does.
`no_embedding_model`, `llm_unreachable` and `secret_ref_missing` propagate; a
missing or non-string `query` raises `tool_failed`; 021's seam produces the
`tool_fail` frame and the fixed model message. Proven through the real seam with
no designated embedding model.

**Off-loop in one call** (027 D6): the search *and* the excerpt read run inside a
single `asyncio.to_thread` on the seam's connection — 026's pattern reused, with
both sync pieces in the same hop rather than two.

### The invalidation fan-out this creates — the first one-to-many in the system

**Until now every `session_vec` write was one session per relational write**:
settle, a settled-text edit, re-open. Each is a write *to that session*, so the
refresh was one embedding call in the transaction that caused it.

**Editing a character's persona — or a setup's text — now invalidates every
session vector under that character.** One relational write, N embedding writes.
This is the system's **first one-to-many embedding invalidation**, and it is
named as such because nothing else in the embedding lifecycle behaves this way
and a reader will size the cost from the wrong precedent.

**Decision: re-embed inline, in the same transaction as the relational write.**
Consistent with the rule that governs every other embedding in this design
(embeddings are written in the same transaction as the relational row), and it
means **search is never stale** — a persona edit and the search results that
depend on it commit together or not at all.

**The cost, stated honestly rather than left to be discovered:** a persona edit
on a character with **N sessions performs N embedding calls inside one request**,
and the edit is as slow as that takes. On a character with a long history and a
metered provider, that is a real and visible pause on what looks like a text
edit. That is the price of never-stale, and it is paid at the moment the
roleplayer edits rather than at the moment the assistant searches.

**Validation and fail-hard apply only when N > 0** (024 D1, D5, D6), where N means
**at least one non-empty session text to embed**. So **creating** a character or a
setup, **editing one that has no sessions**, a **name-only** edit, and an
**unchanged** sheet or description all need **no embedding model at all** and
cannot fail for want of one. That is not a loophole in the fail-hard rule but its
precise scope: the rule exists so authored material is never stored unindexed, and
a write that changes no indexed text has nothing to index.

**A fan-out sends one embed request carrying all N texts**, not N requests. One
round trip rather than N is the difference between a persona edit on a long
history being slow and being unusable, and the client's `embed` already takes a
list of texts (`LlmClient.embed`).

**Flip condition — recorded so this is one decision away, not a redesign.** If
persona edits become slow enough to be disruptive, the fallback is
**mark-stale-plus-rebuild**: flag the affected sessions with a staleness marker,
let FEAT-005's rebuild (UC-016) reconcile them, and accept temporarily stale
search results in between. That was the runner-up, and the design is **partly**
shaped for it: the degraded-write path already tolerates a stale `session_vec`
row as an expected state rather than as drift. **The marker itself does not
exist** — "no staleness marker and no staleness column" is a decision, not an
open question (024 U5, and the embedding lifecycle below) — so taking this flip
means adding the column that was declined, which is the one piece of work it
carries.

**Archived sessions participate — the `_TBD:` is closed** (024 U4). The fan-out
applies **no archive predicate**, so every session under the character is
re-embedded, archived ones included.

The reason is the consequence of the alternative: R6 never destroys an archived
session and always restores it fully usable, so **skipping them would make a
restored session's vector silently stale** — findable again (`session_search`
drops its archive term for it the moment it is restored) and matching on text it
no longer contains. The price is that the fan-out is proportional to a character's
**whole history** rather than to its live sessions, which is the cost recorded
above. The rejected alternative — skip archived sessions and re-embed on restore —
was rejected because it makes restore a write that needs an embedding model, which
would let a platform gap block a pure R6 operation.

**027 sharpens why this is the right half of the trade.** `session_search` now
excludes archived sessions from its *results* (above), so the premise this
`_TBD:` was written against — "`session_search` excludes nothing on archive
state" — no longer holds. But the exclusion is a query filter, not an index
decision: a restored session re-enters results immediately, which is exactly the
moment a stale vector would be wrong. Had the fan-out skipped archived sessions,
"re-embed on restore" would have become **mandatory** rather than an alternative.

`_TBD: whether a persona edit touching many sessions needs a PROGRESS SURFACE.
Inline re-embedding makes the edit a single long request with no feedback — the
roleplayer presses nothing and waits. docs/product/ describes no progress
indication for any operation except UC-016's completion report, which is an
admin surface and not this one. Whether a blur-save that takes thirty seconds
needs to say so, and what it says, is not designed here. Raised for
/product-spec._

That one **stays open and is unmeasured**: nothing has observed how long a
fan-out takes on a real history, and the surface it would need is a product
question about feedback rather than a retrieval decision.

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
  sessions, entries and memos. **The product's count of five corpora is
  unchanged.** What changed is the mechanism: **five corpora are served by three
  port variants plus two `LIKE` corpora outside the port** (029 U2) —
  this section used to say "five corpora, so five `SearchScope` variants", and
  that is no longer the shape.
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

### Three port variants and two `LIKE` corpora (029 U2)

| Corpus | Mechanism |
|---|---|
| sessions | **port**, session variant — vector only, over `session_vec` |
| entries | **port**, entry variant — lexical over `message_fts` / `settled_entries` |
| memos | **port**, memo variant — hybrid, **no extra predicate** (no flag filter at all) |
| characters | **`LIKE`, outside the port** — over `name` and `sheet` |
| setups | **`LIKE`, outside the port** — over `name` and `description` |

**The `LIKE` path is the one deviation from "all three surfaces go through one
port", and it is recorded as a deviation rather than quietly admitted.** There is
**no index for characters or setups** — no FTS table and no vectors
(`data-model.md` closes that `_TBD:` with "no FTS tables for either") — so a port
variant over them would carry **no arm at all**: nothing to rank, nothing to fuse,
a `SearchScope` whose only content is a `WHERE`. The match is a plain
**escaped, case-insensitive substring over one needle, not tokenised**.

**Flip condition:** if characters or setups ever gain an FTS or vector index, they
**become port variants and the `LIKE` path goes**. That is the single change that
would make the port universal again, and it is worth naming because the `LIKE`
path is otherwise the kind of shortcut that gets copied.

**Defect D-05 — `LIKE` folds case for ASCII letters only.** SQLite's `LIKE` is
case-insensitive for ASCII and **case-sensitive for every other script**, so a
character or setup whose name is written in a non-Latin script matches **only in
the case typed** (029 D3). `US-147` requires name matching to be case-insensitive
**in any script**, so the build does not satisfy it. This is a defect, not an open
question: the requirement is settled and only the code is short. See
`docs/plans/defects.md` D-05 — which also records why it matters more here than it
looks (`vision.md`'s premise is a roleplayer composing in a language they are not
confident in, so a non-Latin script is the expected case) and the constraint any
fix must preserve: **the escape handling must survive, because user input may
never be allowed to act as a wildcard.** Entries and memos go through the
FTS/vector arms and are unaffected.

### Fail-whole: no partial groups, no lexical-only degrade (029 U1)

When the memo or session **vector arm raises** — `no_embedding_model` (including
`dimension_mismatch`), `secret_ref_missing` or `llm_unreachable` — **the whole
request fails with that envelope.** No partial groups, no lexical-only fallback.

**The consequence is blunt and is stated rather than softened: with no usable
embedding model, my-search returns nothing — not even a character-name match
the `LIKE` path could have answered on its own.** The page shows the failure
inline.

It is the right trade because the alternative is worse in a way the roleplayer
cannot see: three of five groups returning, with no indication that the other two
were not searched, is a search that silently answers a narrower question than the
one that was asked. A visible failure names a remedy (designate a model, fix the
credential); a half-answer names nothing. It is also the same posture the port
takes for the tools (the query-side no-model rule above), so there is one rule
rather than two.

### Archived material is included, and marked (029 U3)

My-search returns **archived characters, setups and sessions** — the owner
predicate is the only filter — and marks them **"Archived"** in the result row.

**This is a deliberate asymmetry with `session_search`, which excludes archived
sessions** (027 D1), and it is the same asymmetry as the memo flags: **R3 and R6
constrain what the assistant reaches, not what the owner can find in their own
material.** A roleplayer searching for something they put away months ago is
searching *because* it is put away; the assistant composing the current turn has
no business in it. Marked rather than silently mixed in, so the roleplayer knows
why a hit is not in their working list.

### The result shape (029 D2, D4)

**Five groups, in UC-059's order, at most 20 rows per group.** 20 is
conventional, not measured — the same posture as the retrieval constants above.
Within a group: **port order** for sessions, entries and memos; **`name`, then
`id`** for characters and setups.

**Hydration is my-search's own owner-scoped read**, not a port feature:

| Group | Hydrated with |
|---|---|
| session | character name, setup name, start time, archived flag |
| entry | session id, character name, session start |
| memo | `is_enabled`, and the character id needed to route to it |

The port returns ids, scores and snippets; everything a human needs to recognise
a hit is read afterwards, by `user_id` and hit ids. Same division as
`session_search`'s excerpt read, for the same reason — the port stays a retrieval
contract rather than a presentation one.

**A disabled memo hit is marked, and the presentation `_TBD:` is closed**
(029 D7). `US-137.AC-2` requires the fact to be shown and says nothing about its
anatomy; as built the snippet uses **the note wall's disabled idiom — dimmed and
struck through — plus a gray "Disabled" badge**. **Enabled and forced hits carry
no marker at all**, and the row shows **snippet plus level label, never a title**
(there is none). Reusing the wall's idiom rather than inventing a second one means
a roleplayer who has seen a disabled note on the wall recognises it in a result
list without learning anything new.

**Known cost: each search embeds the query twice** (029 D5). The memo scope and
the session scope each open the model, because the port takes **text** rather than
a vector. A port entry accepting a pre-computed query vector — or a multi-scope
call — would halve it; **not done here**, and recorded so the duplicate provider
call is a known cost rather than a surprise in a bill. **Flip condition:** the
second provider call becoming visible in latency or cost.

### Where a result goes (029 U4, D8)

Every result jumps to the thing it points at (UC-060):

| Hit | Lands on |
|---|---|
| character | `/characters/:id` |
| setup | its character's page |
| session | `/sessions/:id` |
| entry | `/sessions/:sessionId?entry=<messageId>` — scrolled into view and highlighted briefly |
| memo | its level's page: user → `/settings`; character or setup → the character page; session → `/sessions/:id?notes=open` |

**There is no per-note focus.** A memo hit lands on the screen that holds its
level, not on the note itself — the wall and the level groups render every note
in the level, so the roleplayer finds it by reading rather than by being scrolled
to it. The route-level halves of this (`?entry=`, `?notes=open`) are
`frontend-structure.md`'s and `workspace-shell.md`'s.

### The entry corpus is the `settled_entries` selectable

The `entries` table is gone: entries, discussions and discussion messages are one
`messages` table with four named Core selectables over it — **not SQL views**
(`data-model.md`). My-search's "entry" corpus therefore reads the
**`settled_entries` selectable**, never raw `messages` (R11). Two guarantees
follow and both are testable as absences:

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

### Settled and ratified: my-search **does** show disabled notes

Decided, and now **ratified by `docs/product/`**. My-search applies **no
`is_enabled` / `is_forced` predicate at all** — forced, searchable and disabled
notes are all returned. Only the `user_id` predicate applies.

**US-137 is the ratification.** This was recorded here as a requirements gap
resolved at the architecture layer, flagged for `/product-spec` to ratify into
FEAT-017's acceptance criteria. It has: **US-137.AC-1** states that a disabled or
not-forced memo is returned like any other and that **note state never filters
results**, and **US-137.AC-2** that a returned memo which is currently disabled
is **shown as disabled**. Both halves of what this doc decided are now product,
so FEAT-017's plan binds to the criteria rather than to this doc alone, and the
flagged-for-another-owner note that stood at the end of this section is removed.

The reasoning is unchanged and is kept because it is still the reasoning:

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

**A disabled hit is visibly marked as disabled** (US-137.AC-2), so the roleplayer
is not misled into thinking the assistant can see it. The note wall already
renders both flags in place (UC-075, `workspace-shell.md`).

**How it is marked is no longer open.** The `_TBD:` this section carried — the
anatomy of a disabled hit's row — **is closed** by 029 D7: dimmed and struck
through, plus a gray "Disabled" badge, reusing the note wall's idiom. The result
shape section above has it with the reasoning.

**What does not change:** a note with `is_enabled = false` remains absent from
`memo_search`, from `session_search` and from context assembly, and the negative
tests for those three stand exactly as R3 states them. Showing a note to its owner
is not a path to the assistant.

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
| memo body **sent but unchanged** | **nothing** — no model is needed, so the write cannot fail for want of one |
| memo body edited to **blank** | **no vector** — the `memo_vec` row is removed; no model needed |
| memo **deleted** (`UC-088`, `US-141`) | its `memo_vec` **and** `memo_fts` rows go in the same transaction; no model needed |
| `is_enabled` or `is_forced` changed (UC-044, UC-075) | **nothing** — both are filter columns, read at query time |
| memo reordered (`sort_key`, UC-076) | **nothing** — order is not embedded |
| settle (R11) | the session's `session_vec` row |
| a settled message's text edited (UC-078, US-110) | the session's `session_vec` row |
| re-open (R11) | the session's `session_vec` row |
| **a partner block filed** (US-121) | the session's `session_vec` row — it is born settled, so it changes the record (degraded path) |
| a current-zone message written or edited | **nothing** — the zone is not record (US-115) |
| **character or setup created**, or a **name-only** edit | **nothing** — no session text changed, so no model is needed |
| **a character's persona edited (UC-018, US-021)** | **every `session_vec` row under that character** — the fan-out (US-138) |
| **a setup's text edited (FEAT-007)** | **every `session_vec` row for sessions using that setup** (US-138) |

The two "nothing" rows for the reach flags are the payoff of the store decision,
stated plainly: because the filters live in relational columns in the same
database, toggling `is_enabled` or `is_forced` is a one-row update with **no
vector work and no second store to reconcile**. In a split-store design each
toggle would be a cross-store write, and FEAT-012 makes those toggles routine.

### The mechanism — one transaction, and what it costs (024 D1, U1)

Four things happen inside the service's **single** `with conn.begin():`, in this
order:

1. the **relational write**;
2. the **composition read**, *after* the write and in the same transaction — so
   the text embedded is the text just stored, not the text as it was a moment
   before;
3. the **embed call**, through a **sync `asyncio.run` bridge** out of a
   synchronous service (`backend-structure.md`'s "The first async code");
4. the **vector write**.

**The cost, named because it is paid by everybody and visible to nobody:** step 3
is a network round trip, and the **SQLite write lock is held across it**. SQLite
has a single writer, so **concurrent writers wait for a provider**. That is the
price of "search is never stale", and it is accepted because the design assumes
one active roleplayer per instance (`overview.md`'s concurrency `_TBD:`).

**Flip condition:** if that wait becomes visible, the shape changes to
**mark-stale-plus-rebuild** — which is already the recorded runner-up for the
fan-out above, so the two would move together rather than one at a time.

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

`_TBD: the COST of that policy is not measured, and it no longer has an owner.
session_vec embeds a session-level text composed from settled_entries, so every
settled edit re-embeds a text that grows with the session, and a long RP makes
each edit more expensive than the last. This was handed to "FEAT-015's plan";
plan 027 did NOT close it — no measurement of re-embed cost against session
length exists, and bounding the COMPOSED (embedded) text would be 024's code, not
the tool's. It goes back to the embedding owner or to a measured follow-up. What
is NOT open is whether the refresh happens: US-110.AC-2 requires it._`

**One thing that reads like a bound on this and is not.** Plan 027 bounds the
**result excerpt** `session_search` hands the model to 1500 characters (above).
That is a context-window decision on the *read* side and has **no effect on
embedding cost**: the text that gets embedded is 024's composition, unbounded, and
the excerpt never touches it. Named because the two numbers are easy to conflate
and conflating them would read as a `_TBD:` closed when it is not.

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
| **character persona edit, setup text edit** | **fails the transaction** — nothing is stored |
| message edit, settle, re-open, **partner filing** (`session_vec`) | **succeeds, degraded** — the row is stored and the response says search coverage is incomplete (US-112) |

**The caught set on the degraded path is `no_embedding_model` — including the
`dimension_mismatch` form — and `llm_unreachable`** (024 U3, D8).
`llm_unreachable` is in the set because "the designated server did not answer" is
exactly as much a platform gap as "no model is designated", and US-112 is about
platform gaps never blocking the record. **The strict path catches neither** and
lets both propagate, at **409** and **502** respectively. So `no_embedding_model`
has two callers — one that lets it out of the transaction and one that swallows it
and reports degradation in the write's own response — and that split *is* the
asymmetry's implementation (`backend-structure.md` carries the same table).

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

**Character and setup writes join the fail-hard side, and that extends the
asymmetry rather than contradicting it.** With no embedding model designated, a
persona edit **fails entirely** — nothing is stored — which is the memo rule, not
the message rule. The line the asymmetry has always been drawn along is not
"which table" but **what kind of act the write is**:

| | Authoring act | Record-keeping |
|---|---|---|
| Writes | memo create/edit, **persona edit, setup edit** | settle, re-open, settled-text edit |
| On no embedding model | **fails** | **succeeds, degraded** |
| Why | the roleplayer is composing material *in order for it to be retrieved*; storing it unindexed produces something that silently does nothing | US-112: an instance-level omission must never block the record of what happened in the roleplay |

A persona edit is a deliberate authoring act like a memo edit — the roleplayer is
writing the material that the assistant and `session_search` will later reach —
and US-138 has just made it *literally* an input to an index. A settle is
record-keeping, and **the record must never be blocked** (US-112). Same rule,
applied to a new write, not a new rule.

Consequences to hold:

- **A missing or stale `session_vec` row is an expected state, not drift.**
  FEAT-005's report must not flag it the way it flags a memo with no `memo_vec`
  row; UC-016's rebuild is its remedy. The memo-side invariant is unaffected.
- **Nothing records *which* sessions carry a stale vector**, so the remedy is the
  whole-index rebuild (UC-016) rather than a targeted re-embed. **The design
  question is answered: no staleness marker and no staleness column** (024 U5).
  A per-session marker was considered and declined — it would be a data-model
  change, and the rebuild already reconciles everything with no record of what
  needed it.
- The roleplayer-facing half is a banner above the stream (US-112,
  `workspace-shell.md`); the backend half is a caught `no_embedding_model` or
  `llm_unreachable` reported in the write's own response
  (`backend-structure.md`, which carries the same table).

#### Two defects live on the degraded path

Recorded as defects rather than as design, because in both cases the design
question is answered and only the code is short.

- **A failed degraded embed leaves the existing vector stale — defect D-04.**
  "No marker, no column" stands as the *recording* decision, but
  **`US-112.AC-3`** — new at the 2026-10-06 product finalization — requires
  material that could not be embedded to have its **existing vectors cleared**,
  not left in place. The build leaves them, so after a degraded edit
  `session_search` can still return that session on the strength of text it no
  longer contains. The product reversed 024's U5 on this point; U5 was applied
  correctly at the time. See `docs/plans/defects.md` D-04, which also records the
  **accepted consequence of the fix** — material that could not be embedded drops
  out of semantic search entirely until the rebuild — and note that any such
  delete is bound by the owner-scoped-ids rule above, because the derived tables
  carry no user column.
- **`secret_ref_missing` is not in the caught set — defect D-03.** An unset
  `$ENV_VAR` key on the designated server makes a settle or a settled edit fail
  with a **500**, refusing the roleplayer's own text. `US-112.AC-1` was widened at
  the same finalization to cover "credentials the instance cannot use", so the
  build does not satisfy it. See `docs/plans/defects.md` D-03. The strict path is
  unaffected — it is allowed to fail loudly.

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
administrator — the report carries **completion, and at most counts that are not
derived from user content** (UC-066, R5). No per-user breakdown, no sample, no
progress line naming a character. The administrator learns that the index was
rebuilt, not what is in it.

**That narrowing is deliberate, and "counts and completion" is the wording it
replaces.** A rebuild's "N rows indexed" is an aggregate over *every* user's
material, so publishing it tells the administrator that other users have content
and roughly how much — which is the count R5 forbids, arriving by the one route
nobody checks. A count of *tables* rebuilt would qualify; a memo, session or row
count would not. The rebuild is unbuilt (`fast/002.vector-index-rebuild`), so
this is a requirement on that plan rather than an as-built fact;
`admin-surfaces.md` carries the same statement on the page that will show it.

### Changing the embedding designation neither forces nor prompts a rebuild

**Decided by product; the `_TBD:` this section carried is closed.** It asked
whether changing the designation should force, prompt for, or merely permit a
rebuild. **UC-013's postcondition answers it: neither.** Changing the designation
"neither forces nor prompts a rebuild"; the two stay separate operations, and the
remedy is UC-016, **always available**.

**The sharp edge, recorded plainly because it is sharp.** Existing vectors were
produced by the **superseded** model and are **not comparable** with vectors the
new one produces — and **nothing indicates this**. There is no staleness marker,
no banner, no warning on the designation screen and no degradation the semantic
tools can detect: `memo_search` and `session_search` keep answering, confidently,
from an index built against a model that is no longer in use. `docs/product/`
records this as an accepted consequence (FEAT-018's sibling list of accepted
consequences: "nothing indicates that the vector index was built by a superseded
embedding model; semantic results degrade silently until the rebuild is run"), so
the architecture does **not** invent a marker to soften it.

The remedy is the Database page's rebuild (UC-016), which is **always available
to the administrator with no precondition beyond authentication**
(`admin-surfaces.md`). An administrator who changes the designation and does not
rebuild has a working search over a stale index, and the only thing standing
between that state and a correct one is knowing to press the button.
