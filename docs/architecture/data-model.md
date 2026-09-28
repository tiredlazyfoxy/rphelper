# Data model

**Realizes:** FEAT-002, FEAT-003, FEAT-004, FEAT-005, FEAT-006, FEAT-007,
FEAT-008, FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013, FEAT-018, FEAT-019

One SQLite file under `data/`, holding relational rows, `sqlite-vec` vector
tables and FTS5 full-text tables. Reasoning for one store is in `overview.md`;
the retrieval mechanics are in `search-and-retrieval.md`.

Conventions: **snowflake primary keys**, minted in application code (next
section); `created_at` / `updated_at` as UTC ISO-8601 text; every timestamp
column named `*_at`; foreign keys declared and `PRAGMA foreign_keys = ON`. Column
lists below are the *shape* the design requires, not a migration script — a plan
may add bookkeeping columns, but not remove or re-scope one named here without an
architecture change.

## Identifiers — snowflake ids, minted before the INSERT

**Realizes:** FEAT-018, FEAT-019, UC-061..UC-064

Every primary key in this schema is a **snowflake id generated in application code
before the INSERT**. There is no `AUTOINCREMENT` anywhere and no
`INSERT`-then-`UPDATE` to learn an id. The reason is that several writes need the
id *before* the row is durable — settle stamps `messages.related_to` with the head
row's own id inside one transaction — and because the export/import contract wants
ids that can mean the same thing on two instances.

Layout — 64-bit signed, 63 usable bits:

```
 41 bits   milliseconds since epoch 2026-01-01T00:00:00Z   (~69 years)
 10 bits   node id, from config, default 0
 12 bits   per-millisecond sequence                        (4096 ids/ms)
```

Rules, each of which a plan must hold:

- **Storage is `id INTEGER PRIMARY KEY`** in SQLite — the rowid alias, which holds
  a signed int64 natively — and `BigInteger` in SQLAlchemy Core.
- **int64 in SQLite and Python; a decimal STRING in every JSON payload and in all
  TypeScript.** This is not a style preference. A snowflake passes JavaScript's
  `Number.MAX_SAFE_INTEGER` (2^53−1) roughly 25 days after the epoch, so an id
  deserialized into a JS `number` silently rounds — to a value that may be another
  row's id. Pydantic response models serialize id-typed fields to `str`; request
  models parse `str` back to `int`. **A TypeScript `id: number` anywhere in this
  codebase is a defect.** Stated this emphatically because it is the classic
  footgun of this scheme: it fails silently, late, and in production data rather
  than in a test, and a reader who does not see this paragraph will type
  `id: number` without a second thought.
- **The epoch is a constant and can never change.** It is the whole 41-bit budget;
  moving it re-bases every future id against a different origin and invalidates
  the ordering of every row already stored.
- **A clock going backwards refuses to issue and raises.** Silently waiting out
  the drift or carrying on both mint duplicates. A backwards clock step is an
  operational fault and is surfaced as one.
- **Exactly one generator process per node id.** Today that is guaranteed by the
  deployment — one container, one uvicorn (`deployment.md`). Recorded as a
  **deployment guarantee**, not as an accident of the current topology.
- **The node id comes from config** (default 0) so two instances can be given
  different node ids. That is what makes ids minted on two instances
  non-colliding, which matters for FEAT-018 import.
- **Ordering is free.** A snowflake is k-sortable, so `ORDER BY id` is
  chronological. This is why the schema below carries **no `position` column** on
  messages.
- **Import (FEAT-018) can preserve ids** across instances rather than re-map them
  wholesale, which reduces identity-on-import to a collision check. Not
  overclaimed: cross-instance uniqueness holds **only while the two instances were
  configured with different node ids.** Two instances left on the default node id
  0 will collide, and the importer must detect that rather than assume it away.
- **Ids are not secrets.** A snowflake leaks its creation time and is roughly
  sequential, so ids are guessable. That grants nothing: every read path is scoped
  by `user_id` at the query level (R5, FEAT-019), so a guessed id belonging to
  another user resolves to no row. Stated in one line so nobody "hardens" this
  later by swapping in random ids and losing the ordering the schema depends on.

**Flip condition.** The layout above, and the JSON string boundary it forces,
assume one generator process per node id. If RPHelper ever runs more than one
worker, process or replica, or the deployment stops guaranteeing one generator per
node id, both the layout and the string boundary need re-examination before that
change ships.

`_TBD: sqlite-vec's vec0 tables key on rowid, and it is not established here
whether they handle sparse, very large rowids as efficiently as dense ones. The
vector-store decision in overview.md rests on this. Verify before FEAT-014 and
FEAT-015 are planned. The contained fallback, if sparse rowids prove costly: give
memo_vec and session_vec a surrogate dense key of their own, mapped to the
snowflake id, leaving the rest of the schema untouched._

## Entity map

```
users ──┬─► characters ──┬─► setups ──┐
        │                │            │
        │                └─► sessions ◄┘ (setup_id NULLABLE)
        │                        │
        │                        └─► messages ──► translations  (settled rows only)
        │                                 └── related_to ──► messages  (self-FK: burial)
        │
        └────── memos              (scoped to user | character | setup | session;
                                    no FK to the level — see the scope discussion)

llm_servers ──► models        (admin-owned; no user linkage — see R5)
```

`memos` deliberately hangs off none of the four levels by foreign key alone — see
the scope discussion below.

---

## Accounts and instance configuration

### `users`

**Realizes:** FEAT-002, FEAT-003, UC-004..UC-009

| Column | Notes |
|---|---|
| `id` | PK |
| `username` | unique |
| `password_hash` | never a reversible form |
| `role` | `'roleplayer'` \| `'admin'`; the first-run account is created `admin` (UC-001) |
| `is_enabled` | boolean; a disabled account cannot log in (FEAT-002) |
| `rp_language` | user-level default (R1, UC-047) |
| `preferred_language` | user-level default (R1, UC-047) |
| `default_model_ref` | user-level default model **reference**, unvalidated (R4) |
| `default_system_prompt` | user-level default |
| `default_tools` | user-level tool switches |
| `created_at`, `updated_at` | |

**`role` is a single enum column, not an `is_admin` boolean.** It carries the two
rungs of the ladder in `domain-rules.md` — `roleplayer` = ACT-002,
`admin` = ACT-001 — and the backend's `require_role(min_role)` compares it
numerically (`backend-structure.md`). An enum rather than a boolean because the
authorization check the product needs is "at least this rung", so a third rung
would be one enum value and one ladder entry instead of a second boolean plus an
audit of every route's flag conjunction. It is also what the admin Users page
renders as a role badge and changes through UC-008 (`admin-surfaces.md`), where
the backend refuses a self-targeted change so an instance cannot lose its last
administrator.

`is_enabled` is a flag rather than a deletion because FEAT-003 requires disable
**and re-enable**, and because disabling must not touch the user's content.

**Disabling an account also ends that user's login sessions** (FEAT-003's note).
This is a two-table write and it is **one transaction**: `users.is_enabled` goes
false and every live `auth_sessions` row for that user is revoked together. A
disable that flipped the flag but left the sessions alive would leave the person
working in the application until their cookie expired, which is precisely the
outcome FEAT-003 rules out. See `auth_sessions` below, and the
SQLAlchemy Core decision in `backend-structure.md` — explicit transaction scoping
is one of the reasons for it.

The five configuration defaults live on `users` rather than in a separate
settings table because they are exactly one row per user and are read on every
resolution (R1); a join would buy nothing.

### `auth_sessions`

**Realizes:** FEAT-002, FEAT-003, UC-004, UC-005, UC-007

Server-side login sessions, keyed by an opaque token that is what the HttpOnly
cookie carries. Columns: `id`, `user_id`, `token_hash`, `created_at`,
`expires_at`, `revoked_at`.

Server-side rather than a self-contained signed token **because FEAT-003 requires
that disabling an account ends that user's sessions**. A stateless token cannot be
revoked before it expires; a row can. The name is `auth_sessions` and never
`sessions`, because `sessions` is the RP domain entity and a collision there would
be genuinely dangerous.

The linkage, stated explicitly because two other designs depend on it:

- **The disable path revokes rows here, in the same transaction as the flag flip**
  (see `users` above). `revoked_at` is what "ended" means; the row is not deleted,
  so a revocation is observable.
- **Every authenticated request resolves through this table**, which is why
  `GET /api/me` answers 401 for a disabled account and why the admin entry's
  pre-mount gate is a server round-trip rather than a client-side token decode
  (`backend-structure.md`, `admin-surfaces.md`). A JWT-based gate could not
  satisfy FEAT-003 at all — not as an implementation detail, but as a capability.

### `llm_servers`

**Realizes:** FEAT-004, UC-010, UC-011

| Column | Notes |
|---|---|
| `id` | PK |
| `name` | admin-facing label |
| `kind` | `'llamaswap'` \| `'openai'` |
| `base_url` | OpenAI-compatible endpoint root |
| `api_key_ref` | **secret pointer**, not a secret — see below |
| `last_test_at`, `last_test_ok`, `last_test_error` | result of UC-011; registration is unaffected either way |
| `created_at`, `updated_at` | |

`api_key_ref` holds a `"$ENV_VAR"` reference, not a credential. The pattern and
its rationale are in `backend-structure.md`; the data-model consequence is what
matters here: **the database never contains an API key**, so the whole-database
export (FEAT-018/UC-061) does not exfiltrate credentials, and a drift report
(FEAT-005) can be read without redaction.

### `models`

**Realizes:** FEAT-004, UC-012, UC-013

| Column | Notes |
|---|---|
| `id` | PK |
| `server_id` | → `llm_servers` |
| `model_name` | as the server names it |
| `is_enabled` | UC-012; the authority behind R4's use-time validation |
| `is_embedding_designated` | UC-013; at most one row true across the whole table |
| `embedding_dim` | dimensionality of the designated embedding model |
| `created_at`, `updated_at` | |

Unique on `(server_id, model_name)`. Disabling a model is a flag flip and is
**never refused** on account of dependent sessions (UC-012, R5); no reverse-lookup
index or view from `models` to `sessions` exists, and none may be added.

`embedding_dim` is recorded because `vec0` tables are declared with a fixed
dimension. Changing the designated embedding model to one with a different
dimension therefore requires a rebuild (FEAT-005/UC-016), not a silent switch —
see `search-and-retrieval.md`.

---

## Roleplay content

Every table below carries `user_id` directly, even where it could be derived
through a parent. That denormalization is deliberate: R5 requires every read path
to be scoped by owning user **at the query level**, and a direct column makes the
scope predicate impossible to forget and cheap to index. It also makes the
per-user export (UC-062) a set of single-predicate selects.

### `characters`

**Realizes:** FEAT-006, FEAT-013, UC-017..UC-019, UC-048, UC-067

`id`, `user_id`, `name`, `sheet` (the persona/character-sheet body, markdown),
`model_ref`, `system_prompt`, `tools` (the three character-level overrides of
R1), `archived_at` (nullable — R6), `created_at`, `updated_at`.

**No `rp_language` column and no `preferred_language` column.** This absence is
the schema-level enforcement of R1's asymmetry (UC-048, UC-050). It is not an
oversight and must not be added.

### `setups`

**Realizes:** FEAT-007, UC-020..UC-022, UC-068

`id`, `user_id`, `character_id`, `name`, `description`, `archived_at`,
`created_at`, `updated_at`.

A setup carries no configuration overrides — FEAT-007 describes it as a reusable
object carrying its own memos and acting as a search anchor. Configuration
inheritance has three levels (R1); the setup is not one of them.

### `sessions`

**Realizes:** FEAT-008, FEAT-013, UC-023..UC-026, UC-049

| Column | Notes |
|---|---|
| `id` | PK |
| `user_id` | direct scope column |
| `character_id` | required |
| `setup_id` | **nullable, no default, no sentinel** (R2, UC-021) |
| `title` | roleplayer-facing label |
| `partner_label` | free text; the partner is never a first-class entity (`glossary.md`) |
| `rp_language` | session override (R1, two-level chain) |
| `preferred_language` | session override (R1, two-level chain) |
| `model_ref` | session override, unvalidated reference (R4) |
| `system_prompt` | session override |
| `tools` | session override |
| `last_used_at` | drives the working-list order, most recent first (UC-026) |
| `archived_at` | nullable (R6) |
| `created_at`, `updated_at` | |

There is **no status or state column**: FEAT-008 and UC-025 state there is no
"finished" state, and `archived_at` is the only lifecycle change. A `status`
column would invite one.

`last_used_at` is a separate column from `updated_at` because "last use" is a
reading-and-working signal (UC-026) while `updated_at` moves on any write; using
one for the other makes list order jump for reasons the roleplayer did not cause.

**`model_ref` is materialised, not only an override.** R1 resolves a model
reference through `user → character → session`, and US-106 adds a floor: a
character with no model configured resolves to "the first enabled model".
Re-resolved dynamically on every request, that floor is **unstable** — an
administrator enabling a model that sorts earlier would silently change the model
a never-configured session has been using, which is precisely the silent
substitution R4 forbids. So the resolved reference is **written onto
`sessions.model_ref` the first time the session composes**, and the session keeps
it. After that the session's model changes only when the roleplayer changes it
(UC-077, US-105). See R4.

`_TBD: docs/product/ does not state what happens to that materialised value when
the character is configured with a model afterwards. This design keeps the
session's own reference, because overwriting it would be the silent substitution
R4 forbids — but the consequence (a session that never chose a model does not
follow a later character-level change) is a product decision nobody has made.
Raised for /product-spec._

### `messages`

**Realizes:** FEAT-009, FEAT-010, UC-027..UC-038, UC-078, UC-081, UC-082,
UC-083, UC-084

**One table replaces the former `entries`, `discussions` and
`discussion_messages`.** This is a deliberate reversal of the three-table design,
forced by the product: there is no answer box any more. A session is a **stream** —
settled record above a **ruler**, and below the ruler exactly one **current
zone**, a live chat between roleplayer and assistant (US-125, UC-083). Settle
takes the last message in the current zone, **whoever wrote it**, files it as
record, and moves the ruler below it (US-126, US-127). The old shape could not
express that at all: an assistant message that becomes the record lived in a
different table from the record.

| Column | Notes |
|---|---|
| `id` | snowflake PK; `ORDER BY id` **is** the stream order |
| `user_id`, `session_id` | scope + parent |
| `role` | `'user'` \| `'assistant'` \| `'tool'` — who produced the text |
| `kind` | `'partner'` \| `'turn'` \| `'decision'`; **NULL until settled** |
| `text` | |
| `related_to` | nullable self-FK → `messages.id`: the settled row this one is buried under |
| `settled_at` | nullable |
| `tool_name`, `tool_payload` | `role='tool'` rows only (R9) |
| `created_at`, `updated_at` | |

**Two nullable columns carry three states**; the fourth combination is illegal and
is forbidden by a CHECK constraint rather than by discipline:

| `related_to` | `settled_at` | Meaning |
|---|---|---|
| NULL | NULL | **current zone** — live, editable, in context, below the ruler |
| NULL | set | **the record** — a partner block, a turn, or a decision |
| set | NULL | **buried** — scaffolding belonging to the settled row it points at |
| set | set | **illegal** — `CHECK (related_to IS NULL OR settled_at IS NULL)` |

What follows from the shape:

- **`discussions` is dropped entirely.** Its `state` was already derived rather
  than stored; now the *grouping* is derived too, from `related_to`. A discussion
  is not a row — it is the set of rows pointing at one settled head.
- **`position` is dropped.** `ORDER BY id` is chronological (see Identifiers).
  Checked against the product before dropping it, because removing an ordering
  column looks like a mistake: UC-031's "add entries in any order" means the
  *kinds* may appear in any sequence — a session may open with the roleplayer's
  own turn, or carry two turns running — not that the roleplayer may rearrange the
  stream. Nothing in `docs/product/` permits reordering entries. If that ever
  changes, an explicit order key comes back and `ORDER BY id` stops being the
  stream order.
- **"Exactly one current zone" (US-125) needs no constraint at all.** The zone is
  not a row; it is the set of rows in a session matching
  `related_to IS NULL AND settled_at IS NULL`. A set cannot be duplicated, so
  there is nothing to enforce and nothing that can drift. That is a genuine
  structural win of the merge and is recorded as one.
- **Settle is two UPDATEs and no INSERT.** Inside one transaction: bury every
  other current-zone row by setting its `related_to` to the head row's id, then
  set the head's `settled_at` and `kind`. The text that is settled is the text
  already in the row — nothing is copied into a second table.
- **Re-open (US-128) is the exact mirror**: `related_to` back to NULL for the
  group, `settled_at` and `kind` back to NULL on the head. Ids never move, so
  stream position is unchanged by a settle/re-open round trip. Permitted only
  while the current zone is empty (R11).
- **A pasted partner block (US-121) is born settled** — `kind='partner'`,
  `settled_at` set at insert, nothing buried behind it. There is nothing to settle
  for text the roleplayer did not compose.
- **No language column**, as before: the assistant mirrors the language of each
  message and there is no fixed discussion language (UC-033). Recording a language
  would imply a setting that does not exist.
- `role='tool'` rows persist tool calls and their results so the transcript is
  reconstructable, including a failed tool the assistant carried on without (R9).
- **`text` is mutable forever** (UC-029, UC-078, US-110) and the assistant always
  reads the current version — context assembly reads `messages.text` live and
  never caches a snapshot. No revision history table exists; `docs/product/` asks
  for none.

**The RP-language guarantee narrows, and the narrowing is deliberate.** It applies
to `kind IN ('partner','turn')` only. A current-zone message is in whatever
language was used, because the assistant mirrors it (UC-033); and a
`kind='decision'` row is in the roleplayer's **preferred** language, not the RP
language (US-131). Consequence to hold: decisions are never translated (R8), and
the old blanket claim "`entries.text` is always RP-language" no longer holds for
this table.

**Indexes** the three states need: `(session_id, settled_at)` for the record read
(the common path), and `(related_to)` for burial and re-open.

#### The cost of the merge, named as a deliberate reversal

The three-table design bought a structural guarantee that this one does not:
context assembly *had no join* to `discussions` or `discussion_messages` at all,
and that absence was the invariant. Merging converts a missing join into a `WHERE`
clause, which is weaker — a forgotten predicate now returns buried scaffolding
into the prompt instead of failing to compile. That is a real loss and it is
recorded rather than quietly dropped.

**Mitigation — two SQL views, so the predicate exists in exactly one place:**

```sql
CREATE VIEW settled_entries AS
  SELECT * FROM messages WHERE settled_at IS NOT NULL;

CREATE VIEW current_zone AS
  SELECT * FROM messages WHERE related_to IS NULL AND settled_at IS NULL;
```

- Context assembly unions the two views (`llm-and-streaming.md`).
- `session_vec` composes its text from `settled_entries`.
- My-search (FEAT-017) reads `settled_entries`.
- **Raw `messages` is touched by exactly two operations: settle and re-open.**

Buried rows are therefore invisible to every reader that goes through a view: the
absence is restored one level down, at the view boundary instead of at the table
boundary. A query that names `messages` directly and is not settle or re-open is a
defect, and is the thing to look for in review.

### `translations`

**Realizes:** FEAT-011, UC-039, UC-040, UC-041

`id`, `message_id`, `target_language`, `text`, `created_at`.

`message_id` points **only at settled rows** — a translation of a current-zone
message would be a translation of something that is not yet record. Unique on
`(message_id, target_language)`. A **separate table, deliberately**: R8 requires
that a translation never enters session context, and keeping it out of `messages`
keeps it out of reach of context assembly by construction rather than by
discipline. The composite key exists because the target language is the session's
resolved preferred language, which can change.

Only **successful** translations are written (UC-039's exception flow: on failure
nothing is cached). There is no `failed` or `pending` state — absence of a row
means "not translated yet", which is also exactly what "translation failed" should
leave behind.

A row is invalidated when `messages.text` changes (US-111). `_TBD: docs/product/
does not state whether editing a non-partner settled message should discard a
cached translation (UC-029 vs UC-041); US-111 settles only the partner case. The
design deletes the cached rows on any text change, because serving a translation
of text that no longer exists would show the roleplayer something false; this is a
design inference beyond US-111, not a stated requirement._`

### `memos`

**Realizes:** FEAT-012, FEAT-014, UC-042..UC-046, UC-051, UC-052, UC-075, UC-076

| Column | Notes |
|---|---|
| `id` | snowflake PK |
| `user_id` | direct scope column, always set |
| `scope` | `'user'` \| `'character'` \| `'setup'` \| `'session'` |
| `scope_id` | the id of the level named by `scope`; equals `user_id` when `scope='user'` |
| `body` | markdown (UC-043) |
| `is_enabled` | boolean; **default true** (UC-042, US-053) |
| `is_forced` | boolean; **default false** (UC-042, US-053); preserved while disabled |
| `sort_key` | mutable order **within `(scope, scope_id)`** (UC-076, US-102) |
| `created_at`, `updated_at` | |

**There is no `title` column.** US-119 states a note is one body of text with no
title, name or header field. A memo in a result list is identified by a snippet of
its body plus its chain level, which is what FEAT-012 already specifies — so the
column would have had no reader. This is a change from the earlier design, which
carried a `title`; the column must not be re-added to make a list look tidier.

**`sort_key` is explicit and mutable, unlike every other ordering in this
schema.** Snowflake ordering cannot serve here: US-102 lets the roleplayer
rearrange forced notes within a level and the arrangement changes what the system
prompt contains, so the order must be editable after the fact rather than fixed at
creation. It is scoped **within `(scope, scope_id)` and nowhere wider**, because
US-103 forbids a note moving between levels by dragging and the level order itself
is fixed — an order key that spanned levels would make an illegal move
expressible.

**Two booleans, not one three-valued state column.** The reasoning is R3's and is
written there; the schema consequence is that a disabled note keeps its `is_forced`
value, so re-enabling restores the mode it had (US-101).

A **single polymorphic scope pair** rather than four nullable foreign keys, and
rather than four separate tables. Reasons, in order of weight:

1. R2's chain resolution becomes one query with a variable number of OR-terms, so
   the no-setup case is the same code path with one term fewer — which is exactly
   the "degrades with no gap" requirement of FEAT-007 and UC-046.
2. `memo_search` (FEAT-014) filters `is_enabled AND NOT is_forced` across the
   whole chain in one pass, and joins to one vector table and one FTS table
   instead of four.
3. FEAT-018's per-character and per-session exports select memos by
   `(scope, scope_id)` directly.

The cost is that referential integrity for `scope_id` is not expressible as a
single foreign key. That is accepted, and the mitigation is explicit: memo
creation goes through a service that validates the target level exists and belongs
to the same user, and FEAT-005's drift report includes an orphan-scope check.
Recorded as a trade rather than hidden.

There is **no archived state and no `archived_at`** on this table (R3, R6). Memos
do not archive; the column must not appear here, and `is_enabled` is not a
stand-in for one.

### `translations`, `messages`, `memos` and the archive rule

Archiving a character, setup or session (R6) does **not** cascade: memos and
messages under an archived object stay exactly as they are — settled, buried and
current-zone rows alike — because restoring must return the object fully usable
with nothing lost (UC-024, UC-025).
There is no `ON DELETE CASCADE` reachable from an archive operation, because
archiving is not a delete.

---

## Vector tables (`sqlite-vec`)

**Realizes:** FEAT-005, FEAT-014, FEAT-015, FEAT-017, UC-016, UC-051, UC-053

Two `vec0` virtual tables, each declared with the designated embedding model's
dimension (`models.embedding_dim`):

```sql
CREATE VIRTUAL TABLE memo_vec USING vec0(
  memo_id   INTEGER PRIMARY KEY,
  embedding FLOAT[<dim>]
);

CREATE VIRTUAL TABLE session_vec USING vec0(
  session_id INTEGER PRIMARY KEY,
  embedding  FLOAT[<dim>]
);
```

Two tables rather than one polymorphic table because the two searches have
different units and different scope predicates: `memo_search` ranks memos within a
chain (UC-051), `session_search` ranks *sessions* within one character
(UC-053/UC-054). Keeping them apart means neither query can accidentally return
the other's rows — which for `session_search` is a privacy boundary, not a
tidiness preference.

The vector tables hold **no filter columns**. Filtering is done by joining to the
relational tables in the same database (`search-and-retrieval.md`), which is the
entire reason `sqlite-vec` was chosen over a separate store (`overview.md`): a
memo's `is_enabled` / `is_forced` pair can change at any time (UC-044, UC-075) and
must not require a second-store write.

Both tables key on rowid, which here is a snowflake — see the `_TBD:` under
Identifiers on sparse rowids, which must be verified before FEAT-014 and FEAT-015
are planned.

`session_vec` embeds a session-level summary text rather than per-entry vectors,
because FEAT-015's unit of result is a past session. `_TBD: docs/product/ does not
specify what text represents a session for semantic matching (UC-053 says only
"by meaning, for a similar person or situation"). The composition of that text is
left to the plan that builds FEAT-015; note that per-entry embeddings are the
flip condition recorded in overview.md's vector-store decision._`

## FTS5 tables

**Realizes:** FEAT-014, FEAT-017, UC-051, UC-058

```sql
CREATE VIRTUAL TABLE memo_fts    USING fts5(body,  content='memos',    content_rowid='id');
CREATE VIRTUAL TABLE message_fts USING fts5(text,  content='messages', content_rowid='id');
CREATE VIRTUAL TABLE session_fts USING fts5(title, partner_label, content='sessions', content_rowid='id');
```

External-content (`content=`) tables so the text is not stored twice, kept in sync
by triggers on the base tables. `message_fts` and `session_fts` exist for
FEAT-017's my-search, which reaches characters, setups, sessions, entries and
memos (UC-058) — a lexical index is what makes "find the session where I mentioned
X" work. BM25 ranking, fused with vector results by reciprocal-rank fusion; see
`search-and-retrieval.md`.

`memo_fts` indexes `body` alone because `memos` has no `title` column (US-119).

**`message_fts` keeps its external content on the base table `messages`, not on
the `settled_entries` view** — fts5 external content requires a real rowid table.
The index is still restricted to settled rows, by the triggers rather than by the
declaration: insert on the settle transition, delete on re-open, update on a text
edit of a settled row. So a current-zone or buried message is never lexically
findable (US-115), which is what my-search requires, and the view boundary above
and the trigger condition here say the same thing in two places on purpose.
FTS5 external content keys on the same snowflake rowids as the vector tables, so
the sparse-rowid `_TBD:` under Identifiers covers it too.

`characters` and `setups` are searched by their own columns via `LIKE`/FTS as the
plan for FEAT-017 decides; they are small enough that an index is not obviously
worth its sync cost. `_TBD: whether characters and setups get their own FTS tables
is left to FEAT-017's plan._`

## Schema drift and rebuild

**Realizes:** FEAT-005, UC-014, UC-015, UC-016

FEAT-005 needs a per-table status (in sync / missing / drifted) and a remediation
that creates missing tables and brings drifted structures into sync. The design
requirement on the data layer is therefore that the schema is **declared as data**
the backend can introspect against: one authoritative table-definition registry
that both the creation path and the drift report read, compared against
`PRAGMA table_info` / `PRAGMA index_list` and `sqlite_master`.

A single registry rather than migration files as the source of truth, because
UC-014 asks for the *current* structural truth per table, which a migration
history cannot answer directly — a database that skipped a migration and a
database that was hand-edited look identical to a migration ledger and different
to an introspection check.

**Who executes a remediation, now decided.** The registry stays the truth and the
**administrator applies** it, from the drift page's per-row `Create` and `Sync`
actions (`admin-surfaces.md`). The DDL itself is executed by `db/sync.py` using
**Alembic's batch operations** — adopted for that one capability, because SQLite
cannot drop or retype a column in place and the create-copy-drop-rename table
rebuild is what a shape change actually costs. There is **no migration history,
no version table and no automatic upgrade at startup**: remediation is
admin-triggered, never implicit, because a DDL rebuild of a table holding the
roleplayer's own material must not happen silently at boot. Full statement and
reasoning in `backend-structure.md`; the flip condition in `overview.md`.

**The structure/content split below is unaffected by that decision.**

Vector-index rebuild (UC-016) is a separate operation from drift remediation
(UC-015): remediation fixes *structure*, rebuild re-computes *content*. They are
kept separate because a rebuild re-embeds every memo and session against the
designated embedding model and therefore costs real time and real LLM calls,
while remediation is a DDL operation. Conflating them would make a cheap fix
expensive and an expensive one look routine.

## Export / import contract — sketch

**Realizes:** FEAT-018, UC-061..UC-064, UC-002, FEAT-019

Full detail is deferred to FEAT-018's plan (`overview.md`). What the data model
commits to now, because the schema must be shaped compatibly:

**Envelope.** A single file carrying a header and a body:

```
{
  "format": "rphelper-export",
  "version": <int>,
  "granularity": "database" | "user" | "character" | "session",
  "created_at": "<UTC ISO-8601>",
  "schema_version": <int>,
  "payload": { "<table>": [ {row}, ... ], ... }
}
```

**Granularity boundaries**, each carrying its own memos (FEAT-018's purpose line):

| Granularity | Actor | Contains |
|---|---|---|
| `database` | ACT-001 (UC-061) | every table, every user; **opaque to the administrator** — no viewer, no search, no rendering (R5) |
| `user` | ACT-002 (UC-062) | one `users` row, its characters, setups, sessions, messages, translations, and all memos at all four scopes |
| `character` | ACT-002 (UC-063) | one character, its setups and sessions and their contents, plus memos scoped to the character and to anything under it |
| `session` | ACT-002 (UC-064) | one session and its messages and translations, plus **only that session's own memos** |

Messages export whole — settled, buried and current-zone rows together — because
`related_to` is an internal self-reference and dropping buried rows would leave
dangling pointers in the settled ones.

**The per-session known consequence, carried forward not resolved.** FEAT-018's
`_TBD:` records that a single-session export carries only that session's own
memos, so an imported session arrives without the character persona and setup that
gave it meaning (challenge C12). Accepted knowingly. The architecture does not
paper over it by silently widening the session export — doing so would change a
product decision.

**What is never exported:** API keys. `llm_servers.api_key_ref` holds a
`"$ENV_VAR"` pointer, so the whole-database export moves configuration without
moving credentials, and a restored instance needs its environment supplied
separately. Stated here because it is a visible operational consequence of the
secret-pointer pattern.

**Identity on import.** Snowflake ids change this from a re-mapping problem into a
collision check: ids are globally meaningful, so the importer can **preserve**
them and the `related_to` and `scope_id` references inside the payload stay valid
untouched. The qualifier from the Identifiers section applies in full — that only
holds while the exporting and importing instances were configured with different
node ids, so the importer detects collisions rather than assuming there are none,
and falls back to re-mapping when it finds one.

`_TBD: docs/product/ does not state whether import merges into existing data or
requires an empty target (UC-062/UC-063/UC-064 say only "restores"). UC-002 is the
one unambiguous case — whole-database import into an unconfigured instance.
Collision policy for the other three granularities is left to FEAT-018's plan._`

**Vectors are not exported.** They are derived data, re-computable by FEAT-005's
rebuild (UC-016), and they are only valid for the embedding model that produced
them — which the importing instance may not have designated. Re-embedding on
import is correct; shipping stale vectors is not.
