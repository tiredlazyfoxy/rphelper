# Data model

**Realizes:** FEAT-002, FEAT-003, FEAT-004, FEAT-005, FEAT-006, FEAT-007,
FEAT-008, FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013, FEAT-014, FEAT-015,
FEAT-017, FEAT-018, FEAT-019, UC-088, US-111, US-112, US-119, US-136, US-138,
US-139, US-141, US-143, US-145

One SQLite file under `data/`, holding relational rows, `sqlite-vec` vector
tables and FTS5 full-text tables. Reasoning for one store is in `overview.md`;
the retrieval mechanics are in `search-and-retrieval.md`; the **export/import
contract moved to `transfer.md`** at the finalization of plans 008..032, while
the tables and columns it reads stayed here.

Conventions: **snowflake primary keys**, minted in application code (next
section); every timestamp column named `*_at`; foreign keys declared and
`PRAGMA foreign_keys = ON`. Column lists below are the *shape* the design
requires, not a migration script — a plan may add bookkeeping columns, but not
remove or re-scope one named here without an architecture change.

**Timestamps — one fixed-width text form, everywhere.** Every stored timestamp
is UTC ISO-8601 **text** in exactly one form: **microsecond precision and an
explicit `+00:00` offset** (`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`) — the form
`auth_sessions` and `users.last_login_at` already write. One fixed-width form
because these columns are compared **as text** (`expires_at` against "now" on
every authenticated request), and text comparison of mixed forms is silently
wrong: a value that drops its microseconds when they are zero sorts against a
six-digit fraction by the character that happens to sit there, not by time.
Decided at the finalization of plans 001..007 (user decision H2), resolving plan
004's observation.

**Known deviation, not yet fixed:** `users.created_at` and `users.updated_at`, as
written by plan 003's first-administrator insert, use the plain `isoformat()`
form, which **drops the microseconds when they are zero** — so they do not share
the fixed width. Owned by a **`/bug-fixer` pass against plan 003**. Until it
lands, nothing may compare those two columns as text against a fixed-width
value.

## Identifiers — snowflake ids, minted before the INSERT

**Realizes:** FEAT-018, FEAT-019, UC-061..UC-064

Every primary key in this schema is a **snowflake id generated in application code
before the INSERT**. There is no `AUTOINCREMENT` anywhere and no
`INSERT`-then-`UPDATE` to learn an id. The reason is that several writes need the
id *before* the row is durable — settle stamps `messages.related_to` with the head
row's own id inside one transaction. (This sentence used to carry a second reason,
that the export/import contract wants ids meaning the same thing on two instances;
US-136 withdrew it — see the import bullet below and `overview.md`.)

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
  different node ids, which makes ids minted on two instances non-colliding.
  **Its old justification is superseded and the setting survives it**: this
  bullet used to say the node id mattered "for FEAT-018 import", and US-136 has
  since made the roleplayer's imports mint fresh ids (`transfer.md`), so import
  no longer depends on it — and the whole-database import, which does preserve
  ids, is a replace onto an empty instance and so has nothing to collide with. It stays configurable as scheme
  hygiene — two instances writing to distinct databases should not be issuing the
  same id values — and because the flip condition below is stated in terms of it.
- **Ordering is free.** A snowflake is k-sortable, so `ORDER BY id` is
  chronological. This is why the schema below carries **no `position` column** on
  messages.
- **Import mints fresh ids at the roleplayer's three granularities, and preserves
  them at the fourth.** `US-136.AC-2` requires imported material to arrive under
  fresh identity, and `US-136`'s `Constraint:` now scopes that — and
  merge-as-new — to **ACT-002's `user`, `character` and `session` granularities**.
  The **whole-database import is a replace that preserves the export's own ids**
  (`UC-061`, `US-077.AC-2`, `US-077.AC-3`), which is a deliberate deviation and
  not an oversight. `transfer.md` has both halves and the reasoning. The relevant
  fact for this section is that the three minting granularities use **the same
  generator every other write uses**, so the single-generator guarantee already
  covers them and there is no separate id space, no "imported" flag and no way for
  an import to mint an id that collides with a live one.
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

### Sparse snowflake rowids in the derived tables — verified, with one defect

**The `_TBD:` that stood here is closed** (plan 024, U6). It asked whether
`sqlite-vec`'s `vec0` tables handle sparse, very large rowids as efficiently as
dense ones, because the vector-store decision in `overview.md` rests on it. They
do. **Snowflake ids stay the `vec0` and FTS5 keys and there is no surrogate dense
key**, so the contained fallback this `_TBD:` reserved is not taken.

The measurement, recorded because the conclusion is only as good as it:
sqlite-vec 0.1.9, SQLite 3.47.1, 5000 × 768-dimension vectors — insert time,
on-disk size and **unfiltered** KNN are identical for dense ids and snowflakes,
and FTS5 external content with conditional triggers passes `integrity-check` at
rowids around 2^60.

**One real defect came with that result, and it constrains the query layer rather
than the schema.** `vec0` KNN with a **pushed-down id constraint** —
`embedding MATCH ? AND k = ? AND <id> IN (...)` — silently drops true candidates
for ids above roughly 2^50, as **false negatives only**, in 18–36% of queries.
**That query form is forbidden.** The correct forms, and the "Query shape"
example they replace, are in `search-and-retrieval.md`, which owns the query
layer; they are recorded there **once** and deliberately not duplicated here.

**Flip condition:** a `sqlite-vec` release that fixes pushdown at large rowids.
At that point the forbidden form becomes available again and the workarounds in
`search-and-retrieval.md` become optional rather than required.

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

**Realizes:** FEAT-002, FEAT-003, UC-004..UC-009, UC-087

| Column | Notes |
|---|---|
| `id` | PK |
| `username` | unique |
| `password_hash` | never a reversible form — `argon2-cffi`'s own self-describing encoded string (below) |
| `role` | `'roleplayer'` \| `'admin'`; the first-run account is created `admin` (UC-001) |
| `is_enabled` | boolean; a disabled account cannot log in (FEAT-002) |
| `rp_language` | user-level default (R1, UC-047); **nullable** |
| `preferred_language` | user-level default (R1, UC-047); **nullable** |
| `last_login_at` | **nullable**; the fixed-width timestamp form (Conventions, above); the instant the account's most recent session was opened; NULL until the account logs in for the first time. Added by FEAT-003 (plan 005) — below |
| `created_at`, `updated_at` | see the timestamp convention's known deviation, above |

**As built by FEAT-001 (plan 003).** The whole column list is declared even
though bootstrap writes only part of it: the registry is the single source of
truth, and a partial table would be drift FEAT-005 reports against itself.
`rp_language` and `preferred_language` are **left NULL** by the first-run insert,
because they are FEAT-013/UC-047's and bootstrap offers no field for them.
`username` is unique, but FEAT-001 has **no duplicate-username path** —
`require_unconfigured` makes a second creation unreachable; the first such path
arrived with FEAT-003's account creation (plan 005), answered as
`username_taken` (`backend-structure.md`).

**`last_login_at` — added by FEAT-003 (plan 005), by user decision.**
`admin-surfaces.md`'s Users page specifies a **last login** column and no backing
column existed; plan 003 had declared exactly nine. The preamble above authorises
it — a plan may add bookkeeping columns — and it is bookkeeping **about an
account, not user content**, so R5 is untouched.

- **It is stamped by the open-session operation in `services/auth.py`**, inside
  the same `with conn.begin():` that inserts the `auth_sessions` row, with the
  **same instant** that row's `created_at` carries. So the first administrator,
  created and signed in by FEAT-001's bootstrap transaction, is stamped too. Two
  alternatives were rejected: the credential-authentication path is
  deliberately read-only and opens no transaction, and a separate write from the
  router would break the routers-versus-services split. Recorded here because it
  is a cross-feature edit to code FEAT-002 owns.
- **`updated_at` is deliberately NOT bumped by a login.** A column that moves on
  every sign-in stops meaning "the account record changed".

**FEAT-013 added no column here** (plan 017). The two language defaults were
already declared, and the user level carries nothing else (UC-047 step 2, R1), so
the settings screen writes `rp_language`, `preferred_language` and `updated_at`
— the last in the fixed-width timestamp form above — and touches nothing new.

**`password_hash` stores a self-describing encoded string**
(`$argon2id$v=19$m=...`): the algorithm, version and parameters live **in the
value** and no schema column records them. That is why a hashing-parameter change
is not a migration, and why there is no `hash_algorithm` column to add later
(`overview.md`, `backend-structure.md`).

**Correction — `users` carries no model, system-prompt or tools default, and the
three columns that used to be listed here are removed.** This table previously
declared `default_model_ref`, `default_system_prompt` and `default_tools`, which
matched R1's old (wrong) three-level diagram. **UC-050's postcondition states
there is no user-level default for model, system prompt or tools**, and UC-047
step 2 says the user level carries "the RP language and the preferred language —
the only two settings at the user level". The columns therefore had no
requirement behind them, and their removal is enforcement of the same kind as
`characters` having no language columns: **a column that exists will eventually
be read**, and a resolver reading one here would produce exactly the user-level
model default UC-050 says does not exist. Marked as a correction rather than
silently dropped, because three deleted columns look like an editing slip.

**`role` is a single enum column, not an `is_admin` boolean.** It carries the two
rungs of the ladder in `domain-rules.md` — `roleplayer` = ACT-002,
`admin` = ACT-001 — and the backend's `require_role(min_role)` compares it
numerically (`backend-structure.md`). An enum rather than a boolean because the
authorization check the product needs is "at least this rung", so a third rung
would be one enum value and one ladder entry instead of a second boolean plus an
audit of every route's flag conjunction. It is also what the admin Users page
renders as a role badge and changes through UC-087 / US-140 (`admin-surfaces.md`;
this sentence used to cite UC-008, which is the password reset), where the
backend refuses a self-targeted change so an instance cannot lose its last
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

The two language defaults live on `users` rather than in a separate settings
table because they are exactly one row per user and are read on every language
resolution (R1); a join would buy nothing. (This paragraph used to say "five
defaults" — see the correction above.)

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
- **Where the bulk revocation lives** (plan 005): a **connection-taking helper in
  `services/auth.py` that opens no transaction of its own**, called by
  `services/users.py`'s disable inside the single `with conn.begin():` that also
  flips `users.is_enabled`. It sets `revoked_at` where it is NULL, deletes
  nothing, is idempotent, and returns a count used for logging only. The
  placement is load-bearing rather than organisational: a helper that opened its
  own block would make the one-transaction requirement unimplementable.
- **A password reset revokes nothing here** — US-010.AC-3 requires the user's
  live sessions to stay active (`admin-surfaces.md`).
- **Every authenticated request resolves through this table**, which is why
  `GET /api/me` answers 401 for a disabled account and why the admin entry's
  pre-mount gate is a server round-trip rather than a client-side token decode
  (`backend-structure.md`, `admin-surfaces.md`). A JWT-based gate could not
  satisfy FEAT-003 at all — not as an implementation detail, but as a capability.

**As built by FEAT-002 (plan 004):**

| Column | Notes |
|---|---|
| `id` | PK |
| `user_id` | **declared foreign key → `users.id`, indexed** — FEAT-003's disable path revokes every row for one user in one transaction |
| `token_hash` | **unique index** — the lookup key on every authenticated request; holds a SHA-256 digest, never the token (`backend-structure.md`) |
| `created_at`, `expires_at` | the fixed-width timestamp form (Conventions, above) — `expires_at` is compared as text on every request; written once, never moved |
| `revoked_at` | **nullable, NULL until revoked**; the row is never deleted, so a revocation stays observable |

The table is created by **FEAT-001's bootstrap `create_all`** — the registry is
the single source of truth and there is no DDL at startup. An instance
bootstrapped **before** FEAT-002 shipped would lack it; that is FEAT-005's drift
surface (`Create`), not FEAT-002's problem.

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

**As built by FEAT-004 (plan 006):**

- **`kind` is plain text with no `CHECK`.** The two-member constraint lives at the
  pydantic boundary. A database `CHECK` would make a third provider a schema
  change, which contradicts "a label, not a dispatch key"
  (`llm-and-streaming.md`).
- **`last_test_error` stores the typed probe outcome value itself** — never a
  provider message and never prose (`admin-surfaces.md`'s result taxonomy).
- There is **no `active` column**, and the LLM Servers page carries no active
  switch (`admin-surfaces.md`).

### `models`

**Realizes:** FEAT-004, UC-012, UC-013

| Column | Notes |
|---|---|
| `id` | PK |
| `server_id` | → `llm_servers` |
| `model_name` | as the server names it |
| `is_enabled` | UC-012; membership in the **chat** model set — the authority behind R4's chat use-time validation; **not consulted for embeddings** |
| `is_embedding_designated` | UC-013; at most one row true across the whole table |
| `embedding_dim` | dimensionality of the designated embedding model |
| `created_at`, `updated_at` | |

Unique on `(server_id, model_name)`. Disabling a model is a flag flip and is
**never refused** on account of dependent sessions (UC-012, R5); no reverse-lookup
index or view from `models` to `sessions` exists, and none may be added.

**As built by FEAT-004 (plan 006)** — three properties later features rely on:

- **`server_id` is declared `ON DELETE CASCADE`**, and the delete operation
  **also** removes the child rows explicitly inside its own transaction, so the
  behaviour does not depend on a connection pragma.
- **`models` rows are never deleted by an enable or a disable.** That is what
  makes the models modal's `available ∪ already-enabled` union work
  (`admin-surfaces.md`).
- **Designation is independent of `is_enabled`** (user decision, plan 006,
  resolving the brief's first open question; **revised 2026-10-08**, see "Decision
  history" at the bottom). `is_enabled` means **only** "in the chat model set" —
  the chat selector and R4's chat model resolution — and has nothing to do with
  embeddings. Disabling a model **never** clears a designation and is never
  refused; designating does **not** enable, so a row created by designation has
  `is_enabled` false. The use-time embedding validator (`validate_embedding_model`
  in `services/llm_registry.py`) requires only that **a designated row exists, it
  has a measured `embedding_dim`, and its server exists**; it does **not** consult
  `is_enabled`. It raises `no_embedding_model` for no designation, a designation
  gone or cleared, no dimension, and (plan 024) a dimension mismatch against the
  live `vec0` table. There is **no cross-flag cascade** between the two flags. We
  chose this because an embedding model is not a chat model and must never appear
  in the chat selector; requiring enablement forced the admin to pollute the chat
  model list. _Code pending: the validator still checks `is_enabled`; a bug fix
  against plan 006 step 004 will align it._
- **`embedding_dim` is measured, not read from metadata**: designating embeds one
  short fixed string against the chosen model and records the returned vector's
  length (`admin-surfaces.md`, US-015.AC-3/AC-4).

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

**What the ownership columns do not guarantee** (observed by plan 032's audit;
**recorded, not changed**). `messages.user_id` is **not** constrained to equal
its parent `sessions.user_id`, and `memos.scope_id` has **no foreign key** at
all. So the schema cannot by itself rule out a row whose owner column disagrees
with its parent's. Isolation therefore rests entirely on **the owner predicate
being present in every query** — which is R5's own formulation, and which plan
032's route-classification guard (`backend-structure.md`) is the build-time check
for. No API path writes an inconsistent row, and the audit deliberately did not
seed one: a test that proves the system behaves correctly on rows it cannot
create proves nothing about the system. Stated here so that "the column is right
there" is not mistaken for a constraint.

### `characters`

**Realizes:** FEAT-006, FEAT-013, UC-017..UC-019, UC-048, UC-067

| Column | Notes |
|---|---|
| `id` | PK |
| `user_id` | FK → `users.id`, NOT NULL, **no `ON DELETE`**; one index on it |
| `name` | |
| `sheet` | the persona, **one markdown body** — see below. Text NOT NULL, no server default; `""` when omitted |
| `model_server_id` | id type, **nullable, no FK** (plan 017) |
| `model_name` | Text; named **both-or-neither CHECK** with `model_server_id` |
| `system_prompt` | Text, stored verbatim; **blank is stored as NULL** |
| `tool_memo_search`, `tool_session_search`, `tool_web_search` | Boolean, **nullable, no default** — three independent switches (R1) |
| `archived_at` | nullable (R6) |
| `created_at`, `updated_at` | |

**`sheet` is one markdown body, not a set of fields** (009 D2). FEAT-006 asks for
a persona; splitting it into name/appearance/voice fields would make the product
decide what a persona consists of, which it deliberately does not.

**No `rp_language` column and no `preferred_language` column.** This absence is
the schema-level enforcement of R1's asymmetry (UC-048, UC-050). It is not an
oversight and must not be added.

**Delivered in two parts, and the gap is not drift.** Plan 009 declared `id`,
`user_id`, `name`, `sheet`, `archived_at`, `created_at`, `updated_at` and the
`user_id` index; **plan 017 added the six configuration columns**, whose
encodings it fixed. A database created between the two picks up plan 017's
columns through the drift page's **Sync**, and the table itself through
**Create** (009 D5). Recorded because a reader of the plan-009 registry would
otherwise read three or six missing columns as a defect.

**The model reference is two columns with no foreign key, and `model_ref` as a
literal column name is deliberately absent** (017 D4). A bare model name is
ambiguous across two registered servers offering the same name — `models` is
unique on `(server_id, model_name)` — so the reference is the pair. **No FK**,
because a deleted server must neither cascade into a character nor null its
reference: the dead reference has to survive in order to raise
`model_not_enabled` at use time (R4). The CHECK makes the pair both-or-neither,
so "half a reference" is not a state.

**Configuration is written only through the configuration routes**
(`…/configuration`), and a character configuration write **never touches a
session row** and **never triggers the persona fan-out** (017 D9). The first half
is `US-139.AC-1` — configuring a character's model does not reach existing
sessions. The second is a cost fact: only `sheet` feeds `session_vec`, so a model
or prompt change has nothing to re-embed.

### `setups`

**Realizes:** FEAT-007, UC-020..UC-022, UC-068

`id`, `user_id`, `character_id`, `name`, `description`, `archived_at`,
`created_at`, `updated_at` — eight columns, delivered whole by plan 010.

A setup carries no configuration overrides — FEAT-007 describes it as a reusable
object carrying its own memos and acting as a search anchor. Configuration
inheritance has three levels (R1); the setup is not one of them.

**As built by FEAT-007 (plan 010).** `user_id` → `users.id` and `character_id` →
`characters.id`, both NOT NULL and with **no `ON DELETE`**; `description` is Text
NOT NULL with no server default (`""` when omitted, and **never stripped** — a
description's leading or trailing whitespace is the author's); one **non-unique
index on `(user_id, character_id)`**, which is the shape every read of this table
uses. An existing database picks the table up through **Create** (010 D7).

**`character_id` is fixed for a setup's life.** No route moves a setup between
characters (010 D5), which is why the single-resource path is flat
(`/api/setups/{id}`) rather than nested — addressing it through its parent would
be a second way to state something immutable. Plan 015's memo scope check relies
on it: a setup-level note's chain position cannot change under it.

### `sessions`

**Realizes:** FEAT-008, FEAT-013, UC-023..UC-026, UC-049

| Column | Notes |
|---|---|
| Column | Notes |
|---|---|
| `id` | PK |
| `user_id` | direct scope column; FK → `users.id` |
| `character_id` | required; FK → `characters.id` |
| `setup_id` | FK → `setups.id`, **nullable, no server default, no sentinel** (R2, UC-021) |
| `rp_language` | session override (R1, two-level chain); trimmed free text, blank = NULL, **no language list** |
| `preferred_language` | the same |
| `model_server_id` | the captured model's server id; **nullable, no FK** (plan 017) |
| `model_name` | Text; named **both-or-neither CHECK** with `model_server_id` |
| `system_prompt` | session override, verbatim; blank stored as NULL |
| `tool_memo_search`, `tool_session_search`, `tool_web_search` | Boolean, nullable, no default |
| `last_used_at` | drives the working-list order, most recent first (UC-026) |
| `archived_at` | nullable (R6) |
| `created_at`, `updated_at` | |

No FK carries `ON DELETE`; one **non-unique index on `(user_id, character_id)`**
and **none on `setup_id`** — nothing reads sessions by setup.

**Delivered in two parts.** Plan 011 declared `id`, `user_id`, `character_id`,
`setup_id`, `last_used_at`, `archived_at`, `created_at`, `updated_at` and the
index; **plan 017 added the two languages, the model pair and the four
configuration columns.** An existing database picks the table up through the
drift page's **Create** and the later columns through **Sync** (011 D8). As with
`characters`, the staging is recorded so the plan-011 registry does not read as
six columns of drift.

There is **no status or state column**: FEAT-008 and UC-025 state there is no
"finished" state, and `archived_at` is the only lifecycle change. A `status`
column would invite one.

**There is no `title` and no `partner_label` column, and that is now a product
rule rather than a deferral.** Plan 011 declared neither, because no requirement
set them (011 D4); `US-145` has since made it explicit — **a session is
identified by its start time, not a title** — so the UI labels a session with
`created_at` rendered `YYYY-MM-DD HH:MM` local. The consequence for the lexical
index is in the FTS5 section below: `session_fts` is declared over two columns
that do not exist.

`last_used_at` is a separate column from `updated_at` because "last use" is a
reading-and-working signal (UC-026) while `updated_at` moves on any write; using
one for the other makes list order jump for reasons the roleplayer did not cause.

**What moves `last_used_at`, as built** (011 D3, 012 D3). It is set at creation,
equal to `created_at`, and is afterwards bumped **only by content writes** — the
zone append, a partner filing, a zone or settled-entry edit, settle, re-open and
compose — each in its own transaction, to the operation's one instant, together
with `updated_at`. It is **never** moved by opening or reading a session, by
archive, or by restore, and a **refused** operation writes nothing. There is no
resume or touch route: resuming is a read (011 D3). Before plan 012 shipped the
content writes, last-use order was therefore identical to creation order.

**Every session read carries `setup_name`** — the referenced setup's **current**
name, by an owner-scoped LEFT JOIN, shown **even when the setup is archived**
(011 D10, 010 D3). It is on the read rather than denormalized onto the row so
that renaming a setup relabels every session referencing it with **no fan-out
write**, and so that `US-088`'s label costs no second request.

**The model is captured at session CREATION, and it is the only thing that is
captured.** R1 resolves a model reference through `character → session`, and
US-106 adds a floor: a character with no model configured resolves to "the first
enabled model". Re-resolved dynamically on every request, that floor is
**unstable** — an administrator enabling a model that sorts earlier would
silently change the model a never-configured session has been using, which is
precisely the silent substitution R4 forbids. So the resolved reference is
**written onto `sessions.model_server_id` / `model_name` when the row is
inserted**, in the same transaction as the rest of session creation, and the
session keeps it. After that the session's model changes only when the roleplayer
changes it (UC-077, US-105).

**As built (017 D1, D7; 018 D3).** The capture runs **inside `start_session`'s
one transaction, after the character and setup checks**, in this precedence:

1. the character's `(model_server_id, model_name)` pair, **captured as-is and
   unvalidated** — even when nothing on the instance is currently enabled, which
   is what `US-139.AC-2` requires;
2. otherwise the **first enabled model** in the instance's order (`llm_servers.id`
   then `models.id`, ascending — the LLM Servers page's own order);
3. otherwise **both columns NULL**.

The system prompt, the tool switches and the two languages are **never copied**
at creation; they stay overrides resolved live. **Sessions created before plan
017 hold NULL, and there is no backfill** (017 D1) — a backfill would be the
system choosing a model for a session the roleplayer never configured, which is
the substitution R4 forbids wearing a different hat.

**Two corrections in one paragraph, both marked:** the chain is
`character → session`, not `user → character → session` (see the `users`
correction above and R1); and the moment is **creation**, not "the first time the
session composes", which is what this doc used to say. `docs/product/` states
creation in three places — UC-050's main flow step 2, US-059.AC-1 and US-139.

**The capture applies to the MODEL ONLY, and the split is deliberate.** The
`system_prompt` and `tools` columns on this table are **overrides, not
captures**: they are consulted as one level of a chain that still resolves
**live** on every request, against whatever the character holds today
(US-059.AC-1, UC-050's postcondition). A session created under a character with
no system prompt has NULL here and picks up a system prompt the character gains
next week; a session created under a character with no model has the first
enabled model **written into `model_ref`** and does not pick up a model the
character gains next week (US-139.AC-1).

Stated here as well as in R4 because this table is where somebody will try to
tidy it. **Harmonising the three columns in either direction is a defect**:
capture the system prompt too and a character-level prompt edit stops reaching
existing sessions; stop capturing the model and a character-level model change
moves a session mid-roleplay. It is examined and intended, not an inconsistency.

**The `_TBD:` this section carried is closed.** It asked what happens to the
materialised value when the character is configured with a model afterwards.
**US-139 answers it: nothing happens — the session keeps its captured model**, and
only sessions created from that point on capture the new one. R4 carried the same
question and it is closed there too.

**What creation does when no model is enabled at all is settled, and the `_TBD:`
is closed.** `US-143` answers it: **a session is created even when no model is
enabled**, and it captures none until the roleplayer picks one. The row is
inserted with **both columns NULL**, and **nothing fills them later on its own** —
the only writer after creation is the roleplayer's choice in the stream header
(UC-077, US-105). Creation is therefore never refused for want of a model, which
is what keeps UC-080's start-a-session-by-writing reachable on a fresh instance.
The refusal the roleplayer meets instead is at **send** time, and it is a
distinct one: `model_not_chosen` (`US-144`), not US-107's `no_model_enabled`.
R4 carries the same closure.

**The encoding `_TBD:` is closed too** (017 D4). It asked how `model_ref` encodes
a model, given that a bare name is ambiguous across two servers offering the same
one. The answer is the two-column pair with no FK and a both-or-neither CHECK,
described under `characters` above; `model_ref` and `tools` as literal column
names are deliberately absent from this schema, so a reader looking for them is
reading a superseded draft.

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
  **One accepted consequence of `ORDER BY id`** (012 D14, user decision): a
  partner block may be filed while the zone holds a draft, and if that draft is
  settled afterwards it sorts **above** the partner block — it was begun first —
  and is not re-openable, because the partner block is then the last settled row.
  This is chronologically true and harmless, so there is **no backend refusal and
  no UI guard**. Recorded because it looks like a bug the first time it is seen.
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

### As built by plan 012, with the tool columns filled by plan 021

The twelve columns exactly as listed. **`role` and `kind` are plain text with no
database CHECK** — their value sets are constrained at the pydantic boundary, the
same choice `llm_servers.kind` makes and for the same reason: a fourth role or a
fourth kind must not be a schema change. The **one** named CHECK is the state
constraint above, `related_to IS NULL OR settled_at IS NULL`. No foreign key
carries `ON DELETE`. An existing instance picks the table up through **Create**.

**`tool_name` and `tool_payload` were declared by plan 012 and unwritten until
plan 021**, which is the writer. As built (021 D7):

- **One `role='tool'` current-zone row per completed call.**
- `text` is the tool's **summary**, or the literal `The tool failed.`
- `tool_payload` is JSON:
  `{call_id, arguments (the raw string), status: ok|failed, content | code}`.
- **A call stopped mid-run writes no row at all** — a cancellation propagates and
  the exchange ends (`US-133.AC-1`).
- The **wire** carries a *derived view* of the payload, never the payload:
  `tool_name`, `tool_status` and `tool_args` on `MessageResponse`, derived in
  `services/messages.py` (022 D3). `tool_payload` itself, the provider's
  `call_id` and the raw tool content stay server-side.

**A current-zone assistant row may contain `<think>` … `</think>` blocks** —
persisted reasoning, stored exactly as it streamed (021 D4). They are stripped
from an assistant head **at settle** (`session-stream.md`), never at edit, so the
column holds reasoning while the row is a candidate and never once it is record
(`US-146`).

**Every write in one operation uses one instant**, and burial and re-open bump
the moved rows' `updated_at` to it (012 D3) — a row that changed state did change,
even though its text did not.

#### The cost of the merge, named as a deliberate reversal

The three-table design bought a structural guarantee that this one does not:
context assembly *had no join* to `discussions` or `discussion_messages` at all,
and that absence was the invariant. Merging converts a missing join into a `WHERE`
clause, which is weaker — a forgotten predicate now returns buried scaffolding
into the prompt instead of failing to compile. That is a real loss and it is
recorded rather than quietly dropped.

**Mitigation — four named Core selectables, so each predicate exists in exactly
one place.** They are **module-level SQLAlchemy Core selectables declared in
`db/schema.py`**, not SQL views:

| Selectable | Predicate | Carries | Readers |
|---|---|---|---|
| `settled_entries` | `settled_at IS NOT NULL` | every column | the record read, context assembly, `session_vec` composition, my-search, `session_search`'s excerpt |
| `current_zone` | `related_to IS NULL AND settled_at IS NULL` | every column | the zone read, context assembly, settle's head and burial set |
| `message_states` | none of its own | **`id`, `user_id`, `session_id`, `related_to`, `settled_at` only — no text** | the edit route, to tell a buried row from a missing one |
| `buried_messages` | `related_to IS NOT NULL` | every column | **the discussion read, and nothing else. Read-only** |

None of them carries a session filter or an ordering — callers narrow and order,
because the predicate they exist to hold is the *state* predicate and adding a
second concern would make them the only query shape anyone could express.

**There are no SQL views anywhere in this schema, and that is a decision**
(012 D1, user decision), not an abbreviation of one. The four reasons:
bootstrap's `create_all` and the drift page's `Create` / `Sync` handle **tables
only**; the drift walk and `/api/health` walk `metadata.tables`; a Sync
batch-recreate of `messages` would **break a real view at the rename step**; and
**no path creates a view on an already-running instance**, so a view declared now
would exist only on databases bootstrapped later. The phrase "two SQL views" in
earlier drafts of this doc described objects that were deliberately never built.

`message_states` is the one addition the design needed rather than inherited
(012 D7, planner decision accepted by the user): the edit route must distinguish
a buried row from a nonexistent one, and doing that through `settled_entries` or
`current_zone` is impossible by construction while doing it with a raw `select()`
on `messages` would breach R11. **It cannot carry content**, so R11's purpose —
buried text never reaches a reader by accident — holds even though a fourth
reader of the table now exists. `buried_messages` (022 D2) is the fourth
predicate and is **read-only**: the discussion read is its only consumer, and no
write path goes through it.

**What is written where, stated precisely** (012 D16), because the older wording
("raw `messages` is touched by exactly two operations") contradicted the route
table:

- **Reads** outside settle and re-open go through a selectable. A `select()`
  naming `messages` directly anywhere else is a defect and is the thing to look
  for in review.
- **The burial and settle columns** — `related_to`, `kind` and `settled_at` on an
  existing row — are written **only by settle and re-open**.
- **Inserts** are the zone append, the partner filing, the assistant row and the
  character page's opening message.
- **`text` and `updated_at`** are written by the edit route, on a zone row and on
  a settled row alike (plan 014).

Buried rows remain invisible to every reader that goes through a selectable other
than `buried_messages`: the absence the three-table design got for free is
restored one level down, at the selectable boundary instead of at the table
boundary.

### `translations`

**Realizes:** FEAT-011, UC-039, UC-040, UC-041

| Column | Notes |
|---|---|
| `id` | PK |
| `user_id` | FK → `users.id`, NOT NULL — the owner column this list used to omit (plan 023) |
| `message_id` | FK → `messages.id`, **no cascade** |
| `target_language` | the session's resolved preferred language at write time |
| `text` | |
| `created_at` | Text, the fixed-width form |

**There is no `updated_at`**, deliberately: a row here is only ever inserted or
deleted, never edited, so a column recording its last change would always equal
`created_at`. The unique constraint is named
`uq_translations_message_id_target_language`.

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

**The write is insert-or-ignore on the unique pair, and only if the message's
current text still equals the text that was translated** (023 D8, D9). The second
condition is the one a reader would omit: the provider round trip is not inside
the message's transaction, so a concurrent edit can land while the translation is
in flight, and writing anyway would cache a translation of text that no longer
exists. Insert-or-ignore rather than upsert because a row that already exists is
already correct for that pair.

**Invalidation: the `_TBD:` that stood here is closed.** It asked whether editing
a **non-partner** settled message should discard a cached translation (UC-029
versus UC-041), noting that US-111 settled only the partner case. **`US-111.AC-3`
now requires exactly what the build does**: editing **any** settled entry
discards its cached translation. So `edit_message_text` deletes the message's
rows on **any** text change, inside the edit transaction, and what was a design
inference is now the requirement it inferred. The reason it was inferred that way
is unchanged and worth keeping: serving a translation of text that no longer
exists would show the roleplayer something false.

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

**As built by FEAT-012 (plan 015, D10).** Ten columns exactly as listed — **no
`title`, no `archived_at`, no `state`**. `scope` is constrained by a **CHECK over
the four values**, in the same non-native-Enum form `users.role` uses, and the
reasoning is stronger here than there: **the four scopes *are* R2's chain**, so a
fifth is an architecture change by definition, not a configuration change.
`scope_id` carries **no foreign key** (the polymorphic pair cannot express one —
below). One **non-unique index on `(user_id, scope, scope_id, sort_key)`**, which
is exactly the shape every list and the chain resolution reads. **A user-level
note stores `scope_id` = its owner's own id** rather than NULL, so the chain
predicate has one form at all four levels; the wire sends `scope_id` as null for
the user level, which is the API's choice and not the column's
(`backend-structure.md`).

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

**Allocation, as built** (016 D5, D6; user decision U3 — this **supersedes** plan
015's `COALESCE(MAX(sort_key), -1) + 1` and the earlier rule must not be
reinstated):

- **A new note gets `COALESCE(MIN(sort_key), 1) - 1`** over the owner's notes at
  the same `(user_id, scope, scope_id)`, inside the create transaction, **so a
  new note lists first**. `US-102.AC-2` now requires exactly that: a newly
  created note holds the first position in its level until reordered.
- **`sort_key` is a signed integer** and runs downwards from the first note —
  0, then −1, −2, … That is the direct consequence of allocating at the minimum,
  and it is why the column may not be made unsigned.
- **A reorder rewrites one whole level to `0..n-1`** in one transaction.
- Lists and the chain order by **`sort_key, id`**. Gaps left by deletes are
  harmless.
- **No unique constraint**, because the rewrite passes through duplicate keys
  mid-transaction and a unique index would collide there. This is the one place
  the absence of a constraint is load-bearing rather than merely untidy.
- **A reorder does not move `updated_at`.** Order is arrangement, not content,
  and a note whose text nobody touched has not changed.

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
   `(scope, scope_id)` directly. **As built** (plan 030): the character
   granularity selects memos scoped to the character, its setups and its
   sessions; the session granularity selects that one session's memos only
   (`transfer.md`).

The cost is that referential integrity for `scope_id` is not expressible as a
single foreign key. That is accepted, and the mitigation is explicit: memo
creation goes through a service that validates the target level exists and belongs
to the same user. Recorded as a trade rather than hidden.

**The orphan-scope check is not built, and this doc deliberately names no owner
for it.** It was never part of FEAT-005's drift report — plan 007 shipped without
it, and it does not belong there anyway: it is a **content** check over
`(scope, scope_id)`, not a structural one. Plan 015 then created `memos` without
building it either (015 D3, user decision). The reason that is acceptable rather
than a gap:

- **An orphan cannot arise today.** Nothing a memo scopes to is ever deleted —
  characters, setups and sessions archive instead (R6) — and create validates its
  target. The one whole-instance delete that exists, plan 031's database replace,
  wipes **both** sides of every scope (`transfer.md`).
- **The earlier wording named "the feature that creates `memos`" as owner, and
  that owner has shipped.** Re-assigning it to a named future plan would be
  inventing work no requirement asks for, so none is named.
- **Flip condition: the first per-entity delete path.** The moment any one
  character, setup or session can be destroyed rather than archived, an orphaned
  `(scope, scope_id)` becomes reachable and this check acquires a reason to
  exist.

There is **no archived state and no `archived_at`** on this table (R3, R6). Memos
do not archive; the column must not appear here, and `is_enabled` is not a
stand-in for one.

**A memo's removal is an explicit, hard delete** —
`DELETE /api/memos/{memo_id}` — and it is the **only** removal a memo has
(015 D2). The roleplayer reaches it by **emptying a saved note**, which
`UC-088` / `US-141` now require: a saved note is removed by emptying it, and a
new note with no text is never persisted at all. Plan 015 shipped that as a
plan-time decision with no story behind it; the product has since supplied one.

The contrast with R6 is deliberate and stated on both pages: characters, setups
and sessions **never** delete, because they archive; memos have **no** archive
state, so delete is their removal. Applying either rule to the other side is a
design error in either direction. The delete also removes the memo's `memo_vec`
and `memo_fts` rows **in the same transaction** (plan 024) — a vector with no
memo would be a hit that resolves to nothing.

### `translations`, `messages`, `memos` and the archive rule

Archiving a character, setup or session (R6) does **not** cascade: memos and
messages under an archived object stay exactly as they are — settled, buried and
current-zone rows alike — because restoring must return the object fully usable
with nothing lost (UC-024, UC-025).
There is no `ON DELETE CASCADE` reachable from an archive operation, because
archiving is not a delete.

### The as-built archive semantics, one rule for all three entities

Set by plan 009 for characters and matched by plans 010 and 011 (009 D9, 010 D5,
010 D9, 011 D2, 011 D13). R6 fixes *what* archiving means; these are the
postures it leaves open, and they are recorded so the three entities do not
diverge:

- **Archive is idempotent and keeps the original `archived_at`.** Archiving an
  already-archived object does not re-stamp it — the timestamp answers "when was
  this put away", and a second click must not rewrite the answer.
- **Restore sets `archived_at` to NULL.**
- **A no-op writes nothing**, including no `updated_at` bump. Archiving something
  already archived is not a change.
- **A real state change bumps `updated_at` and never `last_used_at`** — archiving
  is not use (011 D2).
- **Editing an archived object is allowed** and leaves `archived_at` unchanged.
  R6 says a restored object comes back fully usable; refusing edits meanwhile
  would make archiving a soft freeze, which it is not.
- **An archived parent stays a valid parent.** An archived character still lists
  and accepts **new setups**; an archived character, setup or session is a valid
  target for a memo list, a memo create and the chain (015 D8). The one
  exception is the only one the product states: a **new** session may not adopt
  an archived setup (`setup_archived`, UC-021). Archiving a setup that sessions
  already reference is **always silent and always succeeds** — existing sessions
  keep their `setup_id` and keep working, and keeping a reference count out of
  the UI also keeps R5's reverse-lookup pattern off that screen.
- **Notes are untouched by any of it** (015 D8). Archiving a character, setup or
  session changes nothing on its memos.

---

## Vector tables (`sqlite-vec`)

**Realizes:** FEAT-005, FEAT-014, FEAT-015, FEAT-017, UC-016, UC-051, UC-053

Two `vec0` virtual tables, each declared with the designated embedding model's
dimension (`models.embedding_dim`). **They are not in `metadata` and not in
`db/schema.py`** (plan 024): they live in `db/search_tables.py` and are
**ensured on write** — created, if absent, inside the transaction of the write
that needs them, at the designated model's `embedding_dim`, which is read back
from the stored DDL when they already exist. The reason they cannot be `Table`
literals is that their dimension is **measured** at designation time
(`models.embedding_dim`, below) and is therefore not a static property of the
schema. A dimension that no longer matches the designation raises
`no_embedding_model` with `detail {"reason": "dimension_mismatch"}`, and **only
the rebuild re-declares** them. **Upsert is delete-then-insert or `UPDATE`**,
because `INSERT OR REPLACE` fails on `vec0` 0.1.9.

Consequences of living outside `metadata`: they are outside FEAT-005's drift
report (a recorded gap with a named owner, `admin-surfaces.md`), and ensuring
them is **not** DDL at startup, so `backend-structure.md`'s "no DDL at startup"
rule is untouched.

**They may legitimately be absent.** The whole-database import **drops both
tables inside its transaction** (plan 031, `transfer.md`), so that a restore
whose designated model measures a different dimension cannot strand the instance
in `dimension_mismatch`; the next qualifying write re-creates them at the right
dimension. **Their absence after a restore is a legitimate state transition, not
drift.**

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

Both tables key on rowid, which here is a snowflake. That is **verified**, with
one forbidden query form — see "Sparse snowflake rowids in the derived tables"
under Identifiers, and `search-and-retrieval.md` for the query forms themselves.

`session_vec` embeds a session-level summary text rather than per-entry vectors,
because FEAT-015's unit of result is a past session. Per-entry embeddings remain
the flip condition recorded in `overview.md`'s vector-store decision.

**What text composes it is now specified, and the `_TBD:` here is closed.**
US-138 settles it: a match must consider a session's entries **together with its
character's persona and setup**, so that a query describing a *person* finds the
session even when its entries do not describe the query (US-138.AC-2). The
composition is therefore three sources:

```
session_vec text  =  the session's settled entries          (settled_entries,
                                                             INCLUDING decisions —
                                                             US-122.AC-2, unchanged)
                  +  the character's persona                (characters.sheet)
                  +  the setup text                         (setups.description,
                                                             absent when setup_id IS NULL)
```

The two constraints that were already fixed are unchanged: it reads the
**`settled_entries` selectable** and never raw `messages` (R11), and it **must
include `kind='decision'` rows** (US-122.AC-2).

**As built the order is persona, then setup text, then settled entries in id
order** (024 D6) — not the order the formula above happens to list. Empty parts
are dropped and the rest joined with a blank line. **Persona and setup lead so
that model-side truncation of a long session cannot drop them**, which is exactly
what `US-138.AC-2` depends on: a query describing a *person* must find the session
even when its entries do not describe the query. An empty composed text means
**no `session_vec` row at all**.

**The invalidation edge this creates is a fan-out, and it is the first one in the
system.** Until now every `session_vec` write was one session per relational
write — settle, a settled-text edit, re-open. **Editing a character's persona, or
a setup's text, now invalidates every session vector under that character.**
`search-and-retrieval.md` owns the write policy, its cost, the deliberate
fail-hard behaviour it puts character and setup writes under, and the flip
condition; it is cited here rather than restated, but the schema consequence
belongs on this page: `characters.sheet` and `setups.description` are now inputs
to `session_vec`, so they are no longer purely relational columns.

## FTS5 tables

**Realizes:** FEAT-014, FEAT-017, UC-051, UC-058

```sql
CREATE VIRTUAL TABLE memo_fts    USING fts5(body, content='memos',    content_rowid='id');
CREATE VIRTUAL TABLE message_fts USING fts5(text, content='messages', content_rowid='id');
```

**Two tables exist. A third, `session_fts`, is declared in this doc's history and
was never created** (plan 024, U7). Its declaration indexes `title` and
`partner_label` — **columns `sessions` does not have** and, after `US-145`, is
not going to have as a title (plan 011 D4). So it could not be created against
the built registry at all. It waits on **the feature that gives a session text
columns**, and until then there is no owner to name and nothing to create.
Recorded because the earlier sentence here — that `message_fts` and `session_fts`
"exist for FEAT-017's my-search" — was **stale**: `session_fts` does not exist,
and FEAT-017's my-search was built (plan 029) without it. The same correction is
made in `search-and-retrieval.md`.

External-content (`content=`) tables so the text is not stored twice, kept in
sync by triggers on the base tables. `message_fts` exists for FEAT-017's
my-search, which reaches characters, setups, sessions, entries and memos (UC-058)
— a lexical index is what makes "find the entry where I mentioned X" work. BM25
ranking, fused with vector results by reciprocal-rank fusion; see
`search-and-retrieval.md`.

`memo_fts` indexes `body` alone because `memos` has no `title` column (US-119).

### The trigger conditions, exactly

Recorded to this level of detail because **an unconditional update trigger
corrupts external-content FTS5** — the index keeps a row the base table no longer
matches, and the corruption surfaces much later as a hit that resolves to nothing
(plan 024, D2):

- **`memo_fts`** — on insert, on delete, and on **`UPDATE OF body` only**. Scoping
  the update trigger to one column is what keeps a flag toggle (UC-044) and a
  reorder (UC-076) from churning the index; both are frequent and neither changes
  text.
- **`message_fts`** — insert **when the row is born a record row** (a pasted
  partner block); delete **iff OLD was a record row**; and **one** update trigger
  that first issues `'delete'` with the OLD values **iff OLD was a record row**,
  then inserts NEW **iff NEW is a record row**. One trigger rather than two
  because the settle and re-open transitions change the predicate and the text in
  the same statement, and two triggers would each see half of it.
- **Back-fill on creation** — `memo_fts` via `'rebuild'`; `message_fts` via an
  `INSERT…SELECT` of record rows only, because `'rebuild'` would index every
  current-zone and buried row.

So the index is restricted to settled rows **by the triggers rather than by the
declaration** — fts5 external content requires a real rowid table, which is why
`message_fts` keeps its content on `messages` and not on the `settled_entries`
selectable. A current-zone or buried message is therefore never lexically
findable (US-115), which is what my-search requires, and the selectable boundary
above and the trigger conditions here state the same rule in two places on
purpose.

FTS5 external content keys on the same snowflake rowids as the vector tables, and
the verification under Identifiers covers it: `integrity-check` passes at rowids
around 2^60.

**`characters` and `setups` get no FTS table, and that `_TBD:` is closed.** It
had left the question to FEAT-017's plan, and plan 029 answered it: both are
matched by a SQLite **`LIKE` substring** over their own columns — `name` plus
`sheet` for a character, `name` plus `description` for a setup — because the two
tables are small enough that an index is not worth its sync cost. The as-built
limitation that comes with `LIKE`, and **defect D-05** against `US-147`, are
recorded **once**, in `search-and-retrieval.md`, which owns the query layer.

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

### As built by FEAT-005 (plan 007)

**Realizes:** FEAT-005, UC-014, UC-015, US-018.AC-3..AC-7

- **Three statuses, fixed: in sync, missing, drifted.** Declared once in
  `db/drift.py` and reused by the router model and the frontend row type.
  BookWriter's fourth (`seed-missing`) was looked at and declined
  (`admin-surfaces.md`'s Seed `_TBD:`, still open).
- **What is compared:** a table's **column set**, each surviving column's
  **declared SQLite type** and **NOT NULL** flag, and its **index set keyed on
  (column list, uniqueness)**, not on index name. **Deliberately not compared:**
  server defaults, `CHECK` constraint text and foreign-key clauses — SQLite stores
  them as raw SQL text that does not round-trip against a SQLAlchemy declaration,
  and a false `drifted` row invites a destructive rebuild that fixes nothing.
  The two normalisations, the type compiled through the SQLite dialect and the
  implicit `UNIQUE`/`PRIMARY KEY` indexes excluded, are in `admin-surfaces.md`.
- **The walk covers `metadata.tables` only.** The `vec0` / FTS5 virtual tables
  are outside the report, a recorded gap with a named owner
  (`admin-surfaces.md`). There is **no views half to that gap**: no SQL view
  exists, so the drift report has nothing about one to describe (plan 012 D1).
  **A second edge to the surviving gap, added by plan 024:** the virtual tables
  live in `db/search_tables.py`, and a Sync **rebuild of `memos` or `messages`
  drops that table's FTS triggers**. The next ensure-on-write restores the
  triggers but does not back-fill an existing FTS table, so that index is stale
  for everything written between the Sync and the next full rebuild
  (`backend-structure.md`'s Schema evolution has the mechanism).
- **A Sync rebuild preserves every surviving column's data**; only columns the
  registry no longer declares lose theirs, and a rebuild that cannot complete
  rolls back completely (`admin-surfaces.md`, `backend-structure.md`).
- **Only the structural half shipped.** UC-016's rebuild is
  `fast/002.vector-index-rebuild`'s.
- **`db/schema.py` was not edited by FEAT-005's feature**: the registry gained no
  table and no column. This is what "the registry stays the truth" looks like in
  practice.

## Export / import — the contract moved to `transfer.md`

**Realizes:** FEAT-018, FEAT-019, UC-002, UC-061, UC-062, UC-063, UC-064

**The export/import contract now lives in `transfer.md`** — the envelope, the
id-serialization rules, the two version constants, the granularity table, what is
never exported, the import policy and the whole-database replace. It was split
out at the finalization of plans 008..032, once it had grown from a sketch into
the full as-built contract of two plans. **The tables and columns it reads stayed
here**, which is the whole point of the split: "which table holds `related_to`?"
must not become a two-file lookup.

Three facts belong on this page because they are properties of the **schema**
rather than of the envelope:

- **Messages export whole** — settled, buried and current-zone rows together —
  because `related_to` is an internal self-reference and dropping buried rows
  would leave dangling pointers in the settled ones. The same self-reference is
  why an import writes `messages` in two passes (`transfer.md`): in id order a
  buried row's head has a *higher* id, so the referent arrives after the
  referrer, and foreign keys here are immediate.
- **Two FK-less integer references must be serialized by name rather than by
  metadata**: `memos.scope_id` (the polymorphic scope pair has no single foreign
  key to declare) and `model_server_id` on `characters` and `sessions`
  (deliberately no FK, R4). Both carry snowflakes, so both must cross as decimal
  strings; `transfer.md`'s id-column predicate exists for exactly these two.
- **Nothing derived is exported.** No `vec0` table, no FTS5 table, and no
  `translations` row — each is re-creatable, and a vector is only valid for the
  embedding model that produced it, which the importing instance may not have
  designated. `auth_sessions` is excluded too, as live credentials.

## Decision history

- **2026-10-08 — the embedding validator no longer requires `is_enabled`.** Plan
  006 shipped a use-time embedding validator that required the designated model
  to be **both designated and enabled**. Reversed by user decision: `is_enabled`
  is the chat model set only, and the validator now needs only the designation
  with its measured dimension (and an existing server) — see `models` above.
  Reason: an embedding model is not a chat model, so requiring enablement forced
  it into the chat selector, and it produced an index rebuild refusing with
  `no_embedding_model` while a model was designated with dimension 1024. FEAT-004
  (US-015, UC-013) never required enablement, so no product change. _Code pending
  a bug fix against plan 006 step 004._
