# Transfer — export and import

**Realizes:** FEAT-001, FEAT-018, FEAT-019, UC-002, UC-061, UC-062, UC-063,
UC-064, UC-065, UC-066, US-077, US-078, US-079, US-080, US-081, US-082, US-136

The export/import contract: the envelope, the id-serialization rules, the two
version constants, the four granularities, what never leaves the instance, the
route surfaces, and the import policy — including the whole-database replace,
which deviates from every other granularity on purpose.

Split out of `backend-structure.md` and `data-model.md` at the finalization of
plans 008..032. **The table and column definitions stay in `data-model.md`** —
only the contract moved. `admin-surfaces.md` owns the Database page's export and
import controls and the opacity the administrator sees; `deployment.md` owns the
nginx body limit the upload runs against.

Built in two plans: plan 030 delivered the export half, plan 031 the import half.
`services/transfer.py` holds **export only** and stays read-only and auditable as
such; `services/transfer_import.py` holds validation, deserialization, the remap
engine, the three roleplayer imports and the database replace;
`routers/transfer.py` owns every roleplayer-facing route of both halves, and
`models/transfer.py` the two import response models.

## The envelope

A single JSON file carrying a header and a body:

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

Six header keys and no more. In particular **there is no root-reference field**,
because the root *is* the single row in the granularity's root table — a
`character` export's `characters` array holds exactly one row, and naming it
twice would be a second thing to keep consistent.

Payload tables appear in `metadata.sorted_tables` order and rows in primary-key
order. Every column is read by a **column-agnostic `select(Table)`**, so a column
added to a table in `db/schema.py` travels without an edit to the exporter. That
is the property the `schema_version` constant exists to police.

### Id serialization — the rule, and the two names it exists for

An integer column is serialized as a **decimal string** when any of three things
is true: it is part of the primary key, it carries a foreign key, or **it is
named `id` or `*_id`**. Booleans are JSON booleans, enums their string value, and
timestamps the stored text, unchanged.

The name rule is not belt-and-braces. Two real columns are FK-less references and
are therefore invisible to metadata-only detection: **`memos.scope_id`** (the
polymorphic scope pair has no single foreign key to declare — `data-model.md`)
and **`model_server_id`** on `characters` and `sessions` (deliberately no FK, so
a deleted server neither cascades into a session nor nulls its reference — R4).
Without the name rule each would be emitted as a JSON number, and a snowflake
read back as a JavaScript number silently rounds, possibly onto another row's id
(`data-model.md`'s Identifiers). The export is a file JavaScript consumers read,
so the JSON id boundary applies to it exactly as it applies to the API.

### Two version constants, kept separate

Both live in `services/transfer.py`:

| Constant | Covers | Moved by |
|---|---|---|
| `version` | the envelope shape and the serialization rules above | a change to either |
| `schema_version` | the registry's shape | **a hand bump whenever `db/schema.py` changes a table's shape** |

They are two constants rather than one because they change independently: a
column added to `memos` does not change the envelope, and an envelope rule change
does not change the schema. Folding them would make every change to either look
like a change to both, and an importer could then reject a file that is perfectly
readable.

**Flip condition:** if a hand bump is ever missed in practice, derive
`schema_version` mechanically — from the registry itself — instead of trusting
discipline. The hand bump is the cheap option taken while the registry changes
once per feature, not a claim that hand bumps are reliable.

## Granularity boundaries

Each carries its own memos, which is FEAT-018's purpose line.

| Granularity | Actor | Contains |
|---|---|---|
| `database` | ACT-001 (UC-061) | **every table in `metadata` except `auth_sessions` and `translations`**; every user; **opaque to the administrator** — no viewer, no search, no rendering (R5) |
| `user` | ACT-002 (UC-062) | one `users` row **without `password_hash`, `role` or `is_enabled`**, its characters, setups, sessions, messages, and all memos at all four scopes |
| `character` | ACT-002 (UC-063) | one character, its setups, **its sessions and their messages — archived ones included**, plus memos scoped to the character and to anything under it |
| `session` | ACT-002 (UC-064) | one session and its messages, plus **only that session's own memos** |

Three of those cells are decisions rather than transcriptions:

- **`auth_sessions` is excluded** because it holds live login tokens. A restored
  instance mints its own; carrying them would move a credential.
- **The `user` granularity strips `password_hash`, `role` and `is_enabled`.**
  Those three are administrator-controlled account state, and carrying `role`
  would put a privilege grant inside a file a roleplayer holds and could hand to
  anyone. The whole-database export **does** carry `password_hash` (Argon2's own
  encoded strings), and that is what lets restored users sign in
  (`US-077.AC-2`). Recorded explicitly because a reader will assume hashes are
  stripped everywhere.
- **The `character` granularity includes archived sessions** (user decision,
  2026-10-03). R6 says archiving destroys nothing and a restore must return the
  object fully usable, so an export that dropped the archive would quietly lose
  material the product promises is recoverable.

**The per-session known consequence, carried forward not resolved.** FEAT-018
records that a single-session export carries only that session's own memos, so an
imported session arrives without the character persona and setup that gave it
meaning (challenge C12). Accepted knowingly, and narrowed rather than closed by
the import side: the session is imported **into a character the roleplayer
chooses** (`US-082`, user decision U1 at plan 031), so it arrives with *a*
persona — that character's — and with **no setup at all**. The architecture does
not paper over the remainder by silently widening the session export; doing so
would change a product decision.

### What is never exported

- **Credentials.** Only `"$ENV_VAR"` pointers travel
  (`backend-structure.md`'s secret-pointer pattern). The web-search key is not
  even a pointer — it is a `Settings` field and is never in the database at all.
- **`auth_sessions`.** Live login tokens, as above.
- **`translations`.** A derived cache, re-creatable on demand, dropped from the
  `user` and `session` rows by user decision (2026-10-03). This diverges from the
  original sketch, which listed it.
- **Every `vec0` and FTS5 table.** Derived data, and a vector is only valid for
  the embedding model that produced it — which the importing instance may not
  have designated. See "Vectors and FTS on import", below.

The one thing a reader expects to be stripped and is not is
`users.password_hash` at `database` granularity. See the table above.

## The export routes

**Realizes:** FEAT-018, UC-061, UC-062, UC-063, UC-064

| Route | Guard | Answers |
|---|---|---|
| `GET /api/export` | `require_user` | the caller's `user` export |
| `GET /api/characters/{character_id}/export` | `require_user` | a `character` export |
| `GET /api/sessions/{session_id}/export` | `require_user` | a `session` export |
| `GET /api/admin/database/export` | router-level `require_role(Role.admin)` | the `database` export |

The three roleplayer routes are owned by `routers/transfer.py` — routers group by
feature, not by path prefix, the same reason `routers/stream.py` owns
`PATCH /api/messages/{id}`. The admin route is the fourth on
`/api/admin/database` and needs no per-handler guard, because that router carries
`require_role(Role.admin)` at router level. None of the four takes a body, a
query parameter or a path id beyond the entity being exported.

**These are the codebase's first file-download responses.** Each sets
`Content-Disposition: attachment; filename="rphelper-<granularity>-<UTC timestamp>.json"`,
and **the filename never embeds user content** — no character name, no session
label. A filename is the one part of a download that reaches a file system, a
chat window and a screen share, so it carries the granularity and the clock and
nothing else.

**Root lookups do not reuse the entity getters.** The character and session
exports fetch their root row with their own `id` + `user_id` select inside the
export's read snapshot, and raise the existing `character_not_found` /
`session_not_found` (404 for foreign and missing alike — refusal identity, R5).
The reason is the getters' archive filtering: reusing them would make an archived
character or session unexportable, contradicting the granularity table above. No
new error codes.

**Memory posture: the export is built and encoded in memory as one response.**
That is the simple thing and it is adequate for a self-hosted instance with one
roleplayer's material. **Flip condition:** an instance whose whole-database
export no longer fits comfortably in process memory needs a streamed response —
at which point the column-agnostic `select(Table)` walk is the part that has to
become incremental.

## The import routes

**Realizes:** FEAT-018, UC-061, UC-062, UC-063, UC-064, US-077, US-136

| Route | Guard | Accepts | Answers |
|---|---|---|---|
| `POST /api/import` | `require_user` | `user`, `character` | **200** `{granularity, character_ids}` |
| `POST /api/characters/{character_id}/import` | `require_user` | `session` | **200** `{session_id}` |
| `POST /api/admin/database/import` | router-level `require_role(Role.admin)` | `database` | **204**, and the session cookie is cleared |

Both roleplayer routes are owned by `routers/transfer.py`, for the same
group-by-feature reason as the exports. **The server decides which granularity it
is looking at from the envelope**, which is why one route accepts two of them —
the roleplayer chose a file, not a mode.

`POST /api/admin/database/import` is the fifth route on `/api/admin/database` and
**the first admin-database route that takes a body**. It answers **204 and
clears the cookie** because every `auth_sessions` row is gone, including the
caller's own; leaving the cookie in place would hand the browser a credential
that resolves to nothing and present as a random logout later instead of a
deliberate one now. The administrator is redirected to `/login`
(`admin-surfaces.md`).

### Two deliberate exceptions to the pydantic boundary

`backend-structure.md`'s rule is that routes return pydantic models and take
pydantic models. Transfer breaks it at both ends, and both exceptions are named
so nobody "fixes" them:

- **The export routes return a raw `Response`** (plan 030), because the envelope
  is column-agnostic and no static model can describe a payload whose keys are
  whatever `metadata` currently declares. The JSON id boundary still holds,
  because `services/transfer.py`'s serializer stringifies every id **before the
  router sees the body**.
- **The import routes take a raw JSON object body** (plan 031), for the same
  reason read backwards. The service's deserializer parses the ids inside it and
  accepts **decimal strings only**. Responses are ordinary pydantic models using
  `SnowflakeOut`.

Plan 030's flip condition — "if a second raw-dict route appears, extract the
serializer into `models/` as the shared mechanism" — is **already discharged**:
the deserializer reuses 030's id-column predicate, so the shared mechanism is the
predicate rather than a module move.

### The two refusals

Both codes are defined in `backend-structure.md`'s error model and per-code
status record; what belongs here is what they mean:

- **`export_invalid` → 400.** The body is malformed or incompatible. `detail` is
  exactly `{"reason": …}`, one of `not_an_export`, `unsupported_version`,
  `schema_mismatch`, `wrong_granularity`, `malformed_payload`. It is the
  codebase's **first typed 400** for malformed input — everything else malformed
  is FastAPI's own 422 — and the reason it is typed is that the SPA must tell
  "this is not an export" apart from "this export is too old" without parsing
  prose. `detail` **never** carries a table name, a column name or row content
  (R5), and a database-import constraint refusal maps to `malformed_payload` and
  never forwards the driver's message.
- **`database_not_empty` → 409.** A well-formed request that conflicts with
  instance state — the same shape as `already_configured`.

## Import policy — the three roleplayer granularities

**US-136 settles both halves.** An import **merges as new material**: it arrives
alongside what is already there and **nothing existing is overwritten or
replaced** (`US-136.AC-1`), and imported material carrying ids that already exist
**arrives under fresh identity** (`US-136.AC-2`). `US-136`'s `Constraint:` line
now scopes both statements to **the roleplayer's three granularities** — see the
database replace below, which is the deliberate exception.

**Mechanism: mint new snowflakes and remap internal references.** As built
(plan 031):

- **Every payload row gets a fresh snowflake from the shared generator.** Ids are
  minted **per table in ascending old-id order**, so the rows' relative order —
  which for `messages` *is* the stream order, `ORDER BY id` (`data-model.md`) —
  survives the import. Minting in payload order without that sort would silently
  reshuffle a session's stream.
- **Every foreign key, plus `messages.related_to` and `memos.scope_id`, is
  rewritten** to the new id of the row it points at. The remap table is local to
  the one import and is discarded after it commits.
- **`user_id` is set to the caller**, and so is the `scope_id` of a
  `scope='user'` memo. References that point *outside* the payload are resolved
  to the caller rather than left dangling: at `character` and `session`
  granularity `user_id` names no payload row, and at `session` granularity
  `character_id` and `setup_id` do not either (challenge C12).
- **The payload's `users` row is never written** (`US-136.AC-1`). An import
  cannot create or alter an account.
- **A model pair is kept only if `(model_server_id, model_name)` exists in the
  importing instance's `models`.** Otherwise both columns are nulled — both or
  neither, matching the table's own CHECK. Only the `database` granularity
  carries the `llm_servers` rows a pair could point at, so at every other
  granularity a dead pair is the normal case, and nulling it is better than
  leaving a reference that would raise `model_not_enabled` on the first compose.
- **Timestamps and archived state are preserved.** An imported session arrives
  archived if it was exported archived (R6).
- **The self-reference is written in two passes** — insert with `related_to` null,
  then `UPDATE` — because foreign keys are **immediate** in this engine. In id
  order a buried row's head has a *higher* id, so the referent arrives after the
  referrer. The rejected alternatives were deferring FK checks and toggling
  `PRAGMA foreign_keys`; the Sync rebuild remains the **one** path in the backend
  that suspends foreign keys (`backend-structure.md`), and widening that to a
  second path would make the suspension look routine.

The interaction with the identifier scheme is worth stating, because it is why
this mechanism costs almost nothing: **ids are minted in application code before
the INSERT** (`data-model.md`), so an import uses **the same generator every
other write uses** and the single-generator guarantee already covers it. There is
no separate id space for imported rows, no "imported" flag, and no way for an
import to mint an id that collides with a live one.

**This supersedes an earlier preserve-ids-and-detect-collisions design, and the
supersession is deliberate.** Preserving ids was an optimisation available
*because* snowflakes are globally meaningful; `US-136.AC-2` makes fresh identity a
requirement rather than a fallback, so the collision check is no longer a branch
— minting is unconditional. The visible consequence, which `docs/product/`
records as accepted: **importing the same export twice yields duplicates, and
nothing warns about it.**

## The whole-database import is a replace that preserves ids

**A deliberate deviation from everything above** (user decision U2, 2026-10-03;
ratified by `UC-061`, `UC-064` and `US-077.AC-3`). Stated as a deviation rather
than folded in, because "mint unconditionally" reads as universal and is not.

- **It is allowed only on an instance with no users, or exactly one user who is
  an administrator.** Any other state answers `database_not_empty` — which is
  what `US-077.AC-3` now requires: a whole-database import onto a database that
  already holds content is refused.
- **In one transaction it:** wipes every `metadata` table, `auth_sessions` and
  `translations` included; **drops** `memo_vec` and `session_vec` if they exist;
  and inserts the export's rows **with their own ids**.
- **Why ids are preserved.** "Mint unconditionally" was written for `US-136`,
  which the product has now scoped to ACT-002's granularities. A restore onto an
  empty or just-wiped instance has nothing to collide with, and preserving ids
  keeps the restored instance **identical to the source** — which is what
  `US-077.AC-2` asks for. Remapping here would buy nothing and would change every
  id in a backup.
- **Flip condition:** a requirement to *merge* a whole-database export into a
  populated instance. At that point ids collide again and the replace has to
  become a remap like the other three — and the guard above has to become a merge
  policy rather than a refusal.

**The vec0 tables are dropped, not cleared** (orchestrator decision, plan 031).
A `vec0` table's declared dimension belongs to the *previous* designation, so a
restore whose designated embedding model measures a different dimension would
strand the instance in `dimension_mismatch` on its next qualifying write.
Dropping both tables inside the replace transaction lets plan 024's
ensure-on-write re-create them at the then-designated model's `embedding_dim`.
Nothing is lost, because restored rows have no vectors until the rebuild either
way; and it is safe because DDL is transactional here
(`backend-structure.md`'s transactional-DDL setting), so a failed import keeps
both tables and their rows. **Their absence after a restore is a legitimate state
transition, not drift** (`data-model.md`'s Vector tables).

This is also **the one path that drops the vec0 tables**, and
`backend-structure.md` records it beside the Sync rebuild's foreign-key
suspension as the second named deviation in the persistence layer.

### R5 and the two services that take no `user_id`

`export_database` and `import_database` are **the only service operations in the
backend that take no `user_id`** — the read-side and write-side twins of the same
exception. Recorded here and in `backend-structure.md` so a reviewer auditing
"every read path takes `user_id`" finds the exception stated rather than
discovering it.

They stay compatible with R5 through **opacity**, not through scoping: the
product offers no viewer, no search, no preview, no diff and no rendering of a
whole-database export, in either direction. The admin page reports a byte size
after an export and shows **nothing at all** of an import — no preview, no
counts, no table list, before or after (`admin-surfaces.md`). Both are reachable
only from an admin route — `import_database` will also be reachable from
`fast/003`'s bootstrap route (UC-002) when that lands — and `import_database`'s
single-admin guard lives **in the service**, not in the router, so a second
caller cannot forget it.

The architecture must therefore not grow an export-preview, export-diff or
export-browse surface. That is R5's own rule, and it is the natural next feature
request.

## Vectors and FTS on import

**No import embeds anything** (plan 031 U3), at any granularity. The reason is
operational: an import must not fail on an instance with no designated embedding
model, and requiring one would make a restore depend on the LLM registry being
configured first.

Consequences, all of them recorded rather than worked around:

- **Imported memos and sessions have no vector until the rebuild**
  (`fast/002.vector-index-rebuild`, UC-016). Rebuild-after-restore is the normal
  operational step, not a repair.
- **A memo without a vector is therefore a normal post-import state, not only an
  anomaly.** `backend-structure.md`'s two-transaction-rules section says a memo
  write and its embedding commit together precisely so that an unembedded memo
  *is* an anomaly; after plan 031 that sentence carries this qualifier, and the
  strict transaction rule is unchanged for writes that go through the API.
- **The FTS half is kept current.** `ensure_fts_tables` runs inside the import
  transaction and the triggers index the inserts, so lexical search works
  immediately after an import even though semantic search does not. The
  asymmetry is not an oversight: FTS costs a trigger, embedding costs a provider
  round trip.
- After an import the client raises **one warning** that imported material will
  not appear in semantic search until the rebuild (`ui-conventions.md`'s
  worked example that a warning attached to a success is permitted).

## The upload's practical bound

The import body is **JSON, not multipart**, and is held fully parsed in memory,
so the practical ceiling on an import is nginx's `client_max_body_size 64m`
(`deployment.md`). **Flip condition:** an export that exceeds it in practice
means either raising the limit or moving to a streamed upload — and the streamed
upload is the same change the export's memory posture would need, so the two
would be done together.
