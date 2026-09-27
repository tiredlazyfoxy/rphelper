# Search and retrieval

**Realizes:** FEAT-004, FEAT-005, FEAT-007, FEAT-012, FEAT-014, FEAT-015,
FEAT-017, FEAT-019, UC-013, UC-016, UC-046, UC-051, UC-052, UC-053, UC-054,
UC-058, UC-059, UC-060, UC-065

Three distinct search surfaces, one hybrid retrieval engine, one store. The
store decision and its flip condition are in `overview.md`; the tables are in
`data-model.md`.

---

## Hybrid search: vectors + FTS5, fused by reciprocal rank

### Why hybrid rather than one of the two

**Vector-only fails on the exact token.** Memos and entries in this product are
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
same database file and both queries run against an already-filtered candidate set
(below).

### Why one store

Recorded in full in `overview.md`. The short form, because it drives everything in
this doc: `memo_search` must filter by a four-level memo chain and by
`state = 'searchable'` — and a memo's state changes at any time (UC-044). With a
separate vector store those filter columns must be denormalized and kept in sync,
making every state toggle a second-store write and a standing drift source in a
product with a whole feature (FEAT-005) about detecting drift. `sqlite-vec` writes
vectors **in the same transaction** as the relational row, and lets the filter be a
plain SQL join.

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
(`overview.md`): if `session_search` ever needs per-entry embeddings *and* unscoped
cross-character search, N climbs and approximate indexing starts to matter. A
narrow port means swapping the backing store touches one module, not three
features. It is also the enforcement point for scoping: a `SearchScope` that
cannot be constructed without an owner id is a scope that cannot be forgotten.

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
brute-force KNN — which is **exact**, with no recall parameter to tune and no index
to rebuild after every write — is comfortably fast enough. Filtering *after*
ranking would be both slower and wrong: a top-k over the whole corpus can return k
results the caller is not allowed to see, leaving fewer than k it is.

---

## `memo_search` — FEAT-014

**Realizes:** FEAT-007, FEAT-012, FEAT-014, UC-046, UC-051, UC-052

The assistant's tool for reaching searchable memos across the session's resolved
memo chain.

**Scope predicate**, assembled from the chain (R2 in `domain-rules.md`):

```sql
WHERE memos.user_id = :user_id                    -- FEAT-019, always
  AND memos.state = 'searchable'                  -- UC-052, always
  AND (  (scope='user'      AND scope_id = :user_id)
      OR (scope='character' AND scope_id = :character_id)
      OR (scope='setup'     AND scope_id = :setup_id)     -- term OMITTED when NULL
      OR (scope='session'   AND scope_id = :session_id) )
```

Three exclusions, each with its reason from the product:

- **`forced` memos are excluded** — they are already in the system prompt (UC-052,
  UC-045), so returning them spends a tool call and tokens to tell the model
  something it can already see.
- **`disabled` memos are excluded** — they reach the assistant by no path (R3,
  UC-052). This must be tested as an absence, not inferred from the
  `state = 'searchable'` predicate looking correct.
- **Another user's memos are excluded** — by the `user_id` predicate, at the query
  level (UC-065).

**It works with no setup level present.** The setup term is simply absent from the
disjunction when `sessions.setup_id IS NULL`, so the chain is `user + character +
session` with **no gap** (FEAT-007, UC-046, UC-051's postcondition). This is the
same query with one fewer OR-term — not a second code path — which is why the memo
table uses one polymorphic `(scope, scope_id)` pair (`data-model.md`). A no-setup
session is a required test case for this tool, not an edge case.

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
the signal that is absent in the cases the feature exists to serve. Adding the arm
would make the tool *look* better on queries that name a partner and no better at
all on "a similar person or situation", which is the promise.

**`session_fts` is kept.** It serves FEAT-017's my-search (`data-model.md`,
UC-058), which is a different surface, a different caller and a different rule —
a roleplayer typing a partner's name into their own search box wants exactly the
lexical match the assistant must not get. The table's existence is therefore not
evidence that `session_search` should use it.

**Reversible at low cost, and the flip condition is named.** Turning the arm on
later is a one-surface change: `session_fts` already exists, the port already
fuses two arms for the other surfaces, and nothing in the schema would move. The
condition that would justify it: if FEAT-015's promise — finding "the same person
or situation" **when neither is recorded** — turns out in practice to need lexical
recall, because the semantic signal alone misses sessions a roleplayer knows are
there. That is a relevance finding, not a design argument, so it needs evidence
from real use rather than a plan's judgement. Until then: nobody "improves"
`session_search` by turning the second arm on.

**Scope predicate — a privacy boundary, not a filter:**

```sql
WHERE sessions.user_id     = :user_id       -- never crosses a user   (UC-054)
  AND sessions.character_id = :character_id -- never crosses a character (UC-054)
  AND sessions.id          != :current_session_id
```

Both predicates are in the query, applied before ranking. UC-054's postcondition —
"No session belonging to another character or another user is ever returned" — is
tested with data that would match semantically and must still be absent.

The unit of result is a **past session**, not an entry, which is why
`session_vec` embeds a session-level text (`data-model.md`). `_TBD: docs/product/
does not specify what text represents a session for semantic matching; UC-053 says
only "by meaning, for a similar person or situation". The composition of that
text, and when it is recomputed as the session grows, are left to FEAT-015's
plan._`

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
| Memo state filter | `searchable` only | **all three states, including `disabled`** — see below |
| Result unit | content for the model | a navigable pointer for a human (UC-060) |
| Output | tool message into the model's context | grouped result list (UC-059) |

- **Reaches everything the roleplayer owns** (UC-058): characters, setups,
  sessions, entries and memos. Five corpora, so five `SearchScope` variants
  through the same port.
- **Results are grouped by kind** (UC-059) — character, setup, session, entry, memo
  — so RRF fuses *within* a kind and the groups are presented separately. There is
  no cross-kind global ranking, because UC-059 asks the roleplayer to scan by kind
  rather than as one flat list.
- **Every result jumps to the session or entry it points to** (UC-060), so a hit
  carries enough identity to route: for an entry, its session plus its position.
- **Never includes another user's material** (FEAT-017's note, UC-065) — the
  `user_id` predicate is in every one of the five queries.
- It is a **UI surface, not a tool.** It is never exposed to ACT-004; the
  assistant's reach is exactly three tools (R9).

### Settled: my-search **does** show `disabled` memos

Decided. My-search returns memos in **all three states** — `forced`, `searchable`
and `disabled` — with no state predicate at all. Only the `user_id` predicate
applies.

The reasoning, in two parts:

- **R3 constrains the assistant, not the owner.** "Reaches the assistant by no
  path" is a statement about ACT-004's inbound surfaces: context assembly,
  `memo_search`, `session_search`, tool results and error payloads. My-search is
  **ACT-002's own UI over their own material** (UC-058) and is never exposed to
  ACT-004 (R9). Applying R3 here would be applying a rule about the model's reach
  to the author's own filing cabinet.
- **Hiding a disabled memo makes it unreachable, which breaks UC-044.**
  Re-enabling a memo requires *finding* it first, and re-enabling is an explicit
  alternate flow (UC-044). A roleplayer who disabled a memo months ago and now
  wants it back has my-search as the tool for finding it. A search surface that
  cannot find the thing whose only route back is being found is a dead end.

**A disabled hit should be visibly marked** as disabled in the result list, so the
roleplayer is not misled into thinking the assistant can see it. `_TBD: the exact
presentation — a badge, a muted row, a state column — is not specified; nothing in
docs/product/ describes the result row's anatomy beyond UC-059's grouping and
UC-060's navigability._`

**What does not change:** a `disabled` memo remains absent from `memo_search`,
from `session_search` and from context assembly, and the negative tests for those
three stand exactly as R3 states them. Showing a memo to its owner is not a path
to the assistant.

**This is a requirements gap resolved at the architecture layer.** `docs/product/`
does not state either way — UC-058 says my-search reaches the roleplayer's own
memos and says nothing about state, and FEAT-017's acceptance criteria are silent.
The decision above is a design judgement filling that silence, and it is the kind
of judgement that belongs in a requirement rather than in a design doc.
**`/product-spec` should ratify it into FEAT-017's acceptance criteria**; until it
does, FEAT-017's plan binds to this doc and this doc is the only record of the
choice.

---

## Embedding lifecycle

**Realizes:** FEAT-004, FEAT-005, FEAT-012, FEAT-014, FEAT-015, UC-013, UC-016,
UC-044

**The designated embedding model** (UC-013) is the single source of vectors. Its
dimension is recorded on the `models` row and is what the `vec0` tables are
declared with (`data-model.md`).

**When embeddings are written.** In the **same transaction** as the relational
write that made them stale:

| Trigger | Re-embed |
|---|---|
| memo created | its `memo_vec` row |
| memo body edited (UC-043) | its `memo_vec` row |
| memo state changed (UC-044) | **nothing** — state is a filter column, read at query time |
| session content changes | its `session_vec` row |

The third row is the payoff of the store decision, stated plainly: because the
filter lives in a relational column in the same database, a `forced` ⇄
`searchable` ⇄ `disabled` toggle is a one-row update with **no vector work and no
second store to reconcile**. In a split-store design each toggle would be a
cross-store write, and FEAT-012 makes those toggles routine.

`_TBD: docs/product/ does not state when a session's embedding is refreshed as
entries accumulate. Re-embedding on every entry is wasteful; never re-embedding
makes session_search stale. FEAT-015's plan must choose and record a policy._`

**Failure mode.** If the designated embedding model is absent or has changed, the
embed call raises **`no_embedding_model`** and **never substitutes another model**
(`llm-and-streaming.md`, R4). A different embedding model produces vectors that are
not comparable with the stored ones, so a substitution returns confidently wrong
results — strictly worse than an error. A tool that cannot embed its query fails as
`tool_fail` and the discussion continues (R9).

Because a write path can fail to embed while its relational write must still
succeed, the transaction rule needs one qualification: **a failed embedding fails
the whole transaction** for memo writes, so the store never holds a memo whose
vector is silently missing. That keeps FEAT-005's drift check meaningful — a memo
with no vector row is then genuinely an anomaly rather than an expected state.

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

**Step 3 is the one place in the system where a single operation touches every
user's content, and it must not become a privacy hole.** The rebuild reads memo
bodies and session text to embed them; it returns **no content** to the
administrator — the report is counts and completion only (UC-066, R5). No
per-user breakdown, no sample, no progress line naming a character. The
administrator learns that the index was rebuilt, not what is in it.

Changing the designated embedding model requires a rebuild rather than taking
effect silently, because pre-existing vectors came from the old model and are not
comparable with new ones. `_TBD: docs/product/ does not say whether changing the
designation should force, prompt for, or merely permit a rebuild (UC-013 and
UC-016 are separate use cases with no stated linkage). Until it does, the two stay
separate operations and the semantic tools may return degraded results in between —
recorded as a known consequence rather than resolved by invention._`
