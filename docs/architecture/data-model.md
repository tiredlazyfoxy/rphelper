# Data model

**Realizes:** FEAT-002, FEAT-003, FEAT-004, FEAT-005, FEAT-006, FEAT-007,
FEAT-008, FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013, FEAT-018, FEAT-019

One SQLite file under `data/`, holding relational rows, `sqlite-vec` vector
tables and FTS5 full-text tables. Reasoning for one store is in `overview.md`;
the retrieval mechanics are in `search-and-retrieval.md`.

Conventions: integer surrogate primary keys; `created_at` / `updated_at` as UTC
ISO-8601 text; every timestamp column named `*_at`; foreign keys declared and
`PRAGMA foreign_keys = ON`. Column lists below are the *shape* the design
requires, not a migration script — a plan may add bookkeeping columns, but not
remove or re-scope one named here without an architecture change.

## Entity map

```
users ──┬─► characters ──┬─► setups ──┐
        │                │            │
        │                └─► sessions ◄┘ (setup_id NULLABLE)
        │                        │
        │                        ├─► entries ──┬─► translations
        │                        │             └─► discussions ─► discussion_messages
        │                        │
        └────── memos ───────────┘   (scoped to user | character | setup | session)

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

### `entries`

**Realizes:** FEAT-009, FEAT-010, UC-027..UC-031, UC-038

| Column | Notes |
|---|---|
| `id` | PK |
| `user_id`, `session_id` | scope + parent |
| `kind` | `'partner'` \| `'answer'` |
| `position` | ordering within the session |
| `text` | always RP-language (UC-027 step 2, UC-028 step 3) |
| `is_settled` | answers only; a settled answer is the durable record |
| `settled_at` | nullable |
| `created_at`, `updated_at` | |

Entries are **independent items added in any order** (UC-031): a session may open
with an answer, carry two answers running, or several partner blocks in sequence.
So there is no enforced alternation, no `replies_to` column and no mandatory
partner→discussion→answer triple. `position` is a plain order key, not a parity
constraint.

`text` is mutable forever (UC-029, US-032.AC-1) and the assistant always reads the
current version (US-032.AC-2) — which means context assembly reads `entries.text`
live and never caches a snapshot of it. No revision history table exists;
`docs/product/` asks for none.

### `translations`

**Realizes:** FEAT-011, UC-039, UC-040, UC-041

`id`, `entry_id`, `target_language`, `text`, `created_at`.

Unique on `(entry_id, target_language)`. A **separate table, deliberately**: R8
requires that a translation never enters session context, and keeping it out of
`entries` keeps it out of reach of context assembly by construction rather than by
discipline. The composite key exists because the target language is the session's
resolved preferred language, which can change.

Only **successful** translations are written (UC-039's exception flow: on failure
nothing is cached). There is no `failed` or `pending` state — absence of a row
means "not translated yet", which is also exactly what "translation failed" should
leave behind.

A row is invalidated when `entries.text` changes. `_TBD: docs/product/ does not
state whether editing a partner entry should discard its cached translation
(UC-029 vs UC-041). The design deletes the cached rows on entry-text change,
because serving a translation of text that no longer exists would show the
roleplayer something false; this is a design inference, not a stated
requirement._`

### `discussions`

**Realizes:** FEAT-010, UC-032, UC-036, UC-037, UC-038

`id`, `user_id`, `entry_id` (the answer entry it belongs to), `state`
(`'open'` \| `'collapsed'`), `collapsed_at`, `created_at`, `updated_at`.

One discussion per answer entry. `state` has exactly the two values of R7's
lifecycle; **there is no third "closed forever" value** — permanent
non-resumability is not stored, it is *derived* from whether any entry exists
after the one this discussion belongs to (UC-037). Deriving it rather than
storing it is deliberate: a stored flag would have to be maintained on every entry
insert and delete, and a missed update would either resurrect a discussion the RP
has moved past or lock one the roleplayer is entitled to undo.

### `discussion_messages`

**Realizes:** FEAT-010, UC-033, UC-034, UC-038

`id`, `discussion_id`, `role` (`'user'` \| `'assistant'` \| `'tool'`),
`position`, `text`, `tool_name`, `tool_payload`, `created_at`.

No language column: the assistant mirrors the language of each message and there
is no fixed discussion language (UC-033). Recording a language would imply a
setting that does not exist.

`role = 'tool'` rows persist tool calls and their results so the transcript is
reconstructable, including a failed tool the assistant carried on without (R9).

**Nothing in this table ever reaches context after collapse** (UC-038, R7).
Context assembly selects from `entries` and forced memos only; it has no join to
`discussions` or `discussion_messages` at all. That absence is the invariant.

### `memos`

**Realizes:** FEAT-012, FEAT-014, UC-042..UC-046, UC-051, UC-052

| Column | Notes |
|---|---|
| `id` | PK |
| `user_id` | direct scope column, always set |
| `scope` | `'user'` \| `'character'` \| `'setup'` \| `'session'` |
| `scope_id` | the id of the level named by `scope`; equals `user_id` when `scope='user'` |
| `title` | |
| `body` | markdown (UC-043) |
| `state` | `'forced'` \| `'searchable'` \| `'disabled'`; **default `'searchable'`** (UC-042) |
| `created_at`, `updated_at` | |

A **single polymorphic scope pair** rather than four nullable foreign keys, and
rather than four separate tables. Reasons, in order of weight:

1. R2's chain resolution becomes one query with a variable number of OR-terms, so
   the no-setup case is the same code path with one term fewer — which is exactly
   the "degrades with no gap" requirement of FEAT-007 and UC-046.
2. `memo_search` (FEAT-014) filters `state = 'searchable'` across the whole chain
   in one pass, and joins to one vector table and one FTS table instead of four.
3. FEAT-018's per-character and per-session exports select memos by
   `(scope, scope_id)` directly.

The cost is that referential integrity for `scope_id` is not expressible as a
single foreign key. That is accepted, and the mitigation is explicit: memo
creation goes through a service that validates the target level exists and belongs
to the same user, and FEAT-005's drift report includes an orphan-scope check.
Recorded as a trade rather than hidden.

`state` has **no archived value** (R3, R6). Memos do not archive; `archived_at`
must not appear on this table.

### `translations`, `entries`, `memos` and the archive rule

Archiving a character, setup or session (R6) does **not** cascade: memos, entries
and discussions under an archived object stay exactly as they are, because
restoring must return the object fully usable with nothing lost (UC-024, UC-025).
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
memo's `state` can change at any time (UC-044) and must not require a second-store
write.

`session_vec` embeds a session-level summary text rather than per-entry vectors,
because FEAT-015's unit of result is a past session. `_TBD: docs/product/ does not
specify what text represents a session for semantic matching (UC-053 says only
"by meaning, for a similar person or situation"). The composition of that text is
left to the plan that builds FEAT-015; note that per-entry embeddings are the
flip condition recorded in overview.md's vector-store decision._`

## FTS5 tables

**Realizes:** FEAT-014, FEAT-017, UC-051, UC-058

```sql
CREATE VIRTUAL TABLE memo_fts    USING fts5(title, body,    content='memos',   content_rowid='id');
CREATE VIRTUAL TABLE entry_fts   USING fts5(text,           content='entries', content_rowid='id');
CREATE VIRTUAL TABLE session_fts USING fts5(title, partner_label, content='sessions', content_rowid='id');
```

External-content (`content=`) tables so the text is not stored twice, kept in sync
by triggers on the base tables. `entry_fts` and `session_fts` exist for FEAT-017's
my-search, which reaches characters, setups, sessions, entries and memos
(UC-058) — a lexical index is what makes "find the session where I mentioned X"
work. BM25 ranking, fused with vector results by reciprocal-rank fusion; see
`search-and-retrieval.md`.

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
| `user` | ACT-002 (UC-062) | one `users` row, its characters, setups, sessions, entries, discussions, translations, and all memos at all four scopes |
| `character` | ACT-002 (UC-063) | one character, its setups and sessions and their contents, plus memos scoped to the character and to anything under it |
| `session` | ACT-002 (UC-064) | one session and its entries/discussions/translations, plus **only that session's own memos** |

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

**Identity on import.** `_TBD: docs/product/ does not state whether import
merges into existing data or requires an empty target (UC-062/UC-063/UC-064 say
only "restores"). UC-002 is the one unambiguous case — whole-database import into
an unconfigured instance. Collision policy for the other three granularities is
left to FEAT-018's plan; the schema's integer surrogate keys mean the importer
must re-map ids rather than preserve them, whichever policy is chosen._`

**Vectors are not exported.** They are derived data, re-computable by FEAT-005's
rebuild (UC-016), and they are only valid for the embedding model that produced
them — which the importing instance may not have designated. Re-embedding on
import is correct; shipping stale vectors is not.
