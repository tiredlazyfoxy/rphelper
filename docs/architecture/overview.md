# System overview

**Realizes:** FEAT-001, FEAT-002, FEAT-003, FEAT-004, FEAT-005, FEAT-009,
FEAT-010, FEAT-017, FEAT-019, UC-086, US-134, US-135, US-137,
ACT-001, ACT-002, ACT-003, ACT-004

The system context, who reaches which surface, how it runs in dev and prod, every
stack decision with its reason, and what is deliberately not being built.

## What the system is, architecturally

A single-instance, self-hosted web application with one database file. One
FastAPI process serves a JSON + SSE API under `/api`; a React SPA — built as four
separate Vite entries — is the only client. There is no external integration of
any kind: per `vision.md`, the boundary is the clipboard. Nothing crosses it but
text the roleplayer pastes in and text they copy out.

The product's value is the persistent context layer, not the generation
(`vision.md`). That shapes the architecture directly: the durable store is the
centre of the system and the LLM is an interchangeable outbound dependency
behind one narrow client abstraction, not the other way around.

```
 ACT-003 first-run operator ──┐
 ACT-001 administrator ───────┤
 ACT-002 roleplayer ──────────┴──► browser (SPA, 4 entries)
                                      │  same origin, /api/*
                                      ▼
                            ┌──────────────────────┐
                            │  FastAPI (uvicorn)   │
                            │  routers → services  │
                            └───┬──────────────┬───┘
                                │              │
                                ▼              ▼
                  ┌───────────────────┐   ┌──────────────────────┐
                  │ SQLite (one file) │   │ OpenAI-compatible    │
                  │ rows + vec0 + FTS │   │ LLM servers          │
                  └───────────────────┘   │ llamaswap / OpenAI   │
                                          └──────────────────────┘
                                                   ▲
                       ACT-004 composition assistant lives here —
                       it is not a process, it is a prompt + tool loop
```

ACT-004 (composition assistant) is worth stating explicitly: it is **not a
component we build or deploy**. It is the remote model plus the system prompt,
the assembled context, and the three-tool loop defined in
`llm-and-streaming.md`. It has no state of its own and no path to the database
except through the tool implementations, which is what makes FEAT-019's
isolation enforceable — see `domain-rules.md`. It also has no path into the
*record*: it writes only into a session's current zone, and only the roleplayer's
settle files anything (R11).

## Actor → surface map

Each actor reaches exactly one frontend entry. The mapping is the reason the
frontend is a multi-entry build rather than one bundle (`frontend-structure.md`).

| Actor | Surface | Vite entry | Route base | Available when |
|---|---|---|---|---|
| ACT-003 first-run operator | Bootstrap | `bootstrap` | `/bootstrap` | Only while the instance is unconfigured (UC-003) |
| ACT-001 / ACT-002 (unauthenticated) | Login | `login` | `/login` | Always, once configured |
| ACT-001 administrator | Admin | `admin` | `/admin` | Authenticated, admin role |
| ACT-002 roleplayer | App | `app` | `/` | Authenticated |
| ACT-004 assistant | — | none | — | Inside a session's **current zone** only (R11) |

Two consequences are load-bearing:

- **Admin code never ships to the roleplayer.** FEAT-019/UC-066 says
  administrative surfaces expose no user content; the inverse — that the
  roleplayer's bundle carries no administrative surface at all — is free once the
  entries are separate, and it removes a whole class of accidental-exposure bug.
- **Bootstrap is pre-database.** ACT-003 acts before a schema exists, so the
  bootstrap entry cannot share the authenticated shell's stores, session
  assumptions or API surface. A separate entry makes that a build fact rather
  than a runtime guard.

### The administrative surface — three pages and a 404

ACT-001's entire surface, listed here so its smallness is visible at the top
level. Full detail in `admin-surfaces.md`.

| Route (under `/admin`) | Page | Realizes |
|---|---|---|
| `/` | Users — accounts, roles, disable/re-enable, password reset | FEAT-003 |
| `/llm-servers` | LLM Servers — registration, test connection, enabled models, embedding designation | FEAT-004 |
| `/database` | Database — per-table drift report, create missing tables, rebuild vector index, whole-database export/import | FEAT-005, FEAT-018 (admin half) |
| `*` | Not found | — |

Three pages, no breadcrumbs, no nested layout. **Two surfaces from the sibling
project were deliberately dropped** — an assistant-modes page and a sub-agents
page — because both are authoring-domain configuration with no RPHelper analogue:
ACT-004's reach is fixed at exactly three tools (R9) and "mode" is not a concept
in `docs/product/`. Named as dropped in `admin-surfaces.md` so they are not
re-added by pattern-matching.

Every route behind this surface is bound by **R5**: administrative pages show
administrative data only, and no count derived from user content
(FEAT-019, UC-066).

**Roles are a two-rung ladder, `{roleplayer: 0, admin: 1}`** (`domain-rules.md`),
enforced by a `require_role(min_role)` dependency on every admin route
(`backend-structure.md`). The frontend gate is UX only.

How ACT-001 *reaches* this surface — a user-menu item shown only to an
administrator, navigating cross-entry to `/admin` (UC-071, US-093) — is recorded
in `admin-surfaces.md`, which owns the entry in full.

## Topology

### Dev

Two processes, two terminals, started separately by `start.ps1`:

```
browser ──► Vite dev server :8193 ──/api──► uvicorn :8184 ──► ./data/*.sqlite
            (serves 4 entries, HMR)   proxy
```

The Vite dev server proxies `/api` to uvicorn, so **the browser sees one
origin**. That is not a convenience — it is the reason the cookie story works
with zero CORS configuration, and it makes dev and prod behave identically for
auth. See `deployment.md`.

### Prod

One all-in-one container, two processes under `supervisord`:

```
host :8193 ──► nginx :80 ──┬── /            static dist/ (4 entries)
                           └── /api/  ────► uvicorn 127.0.0.1:8184
                                             └──► /app/data (volume)
```

uvicorn binds loopback only; nginx is the sole listener. Same single origin as
dev. Full nginx directive list, healthcheck and the `supervisord` startup-order
caveat are in `deployment.md`.

## Stack decisions, with reasons

**Python + FastAPI backend.** The LLM and embedding ecosystem this product
depends on is Python-first, and FastAPI gives typed request/response models that
`mypy` can actually check plus first-class streaming responses, which the SSE
protocol needs. Typed models matter more than usual here because the error model
(`backend-structure.md`) has to carry typed failures — such as "resolved model is
no longer enabled" — all the way to the SPA without being flattened into a
string.

**uv as the backend package and environment manager** (plan 001). One PEP 621
`backend/pyproject.toml`, a `backend/.venv` created by `uv venv`, dependencies
installed with `uv sync`, and a committed `backend/uv.lock`. Reason: a committed
lock is the only way the container build and a developer machine resolve the same
dependency tree. The packaging convention in full is in `quick-reference.md`.

**React 19 + TypeScript + Vite, multi-entry.** Four entries because four actor
surfaces with genuinely disjoint code exist (table above). Vite because
multi-entry via `build.rollupOptions.input` is a first-class feature, and its dev
proxy gives the single-origin story for free.

**TypeScript only — no JavaScript anywhere on the Node side.** Every authored file
under `frontend/`, including Vite/Vitest config and any build script, is `.ts` /
`.tsx`; `allowJs` and `checkJs` stay off. We chose this because the project has no
linter, so `tsc --noEmit` is the only static gate, and a `.js` file walks straight
past it — most dangerously past the "ids are strings" rule below, which only the
type system can hold. A tool that only ships a JavaScript config is configured in a
`.ts` file or not adopted. (The backend is Python; this rule has no backend half.)

**Vitest + Testing Library + jsdom as the frontend test stack** (plan 002).
Vitest because it reuses `vite.config.ts`, so there is no second build pipeline,
no second resolver and no second alias set to keep in step. Testing Library +
jsdom because tests then bind to **rendered behaviour** rather than to
implementation details — which is what the pipeline's test-coder, who never reads
source, must bind to. `npm test` runs once and exits. Before this, the doc set
named no test tooling anywhere.

**No ESLint, and no JavaScript linter at all** (plan 002). `npm run typecheck`
(`tsc --noEmit`) is the static gate. Because there is no linter, `tsconfig.json`
carries the compiler's lint-shaped flags: `noUnusedLocals`, `noUnusedParameters`,
`noFallthroughCasesInSwitch`. **`exactOptionalPropertyTypes` and
`noUncheckedIndexedAccess` are deliberately OFF** — both fight Mantine's prop
types at every call site and neither catches a defect this project has — so they
are not to be turned on as a tidy-up, nor assumed forgotten. A rule a linter would
have enforced by grep becomes a Vitest test instead (the "ids are strings" scan in
`frontend-structure.md` is the first).

**The TypeScript configuration layout** (plan 002): a root
`frontend/tsconfig.json` with `strict`, covering `src/` and `tests/`, plus
`frontend/tsconfig.node.json` covering `vite.config.ts` itself. Two files because
the config runs in Node while everything under `src/` runs in a browser, and one
`lib` setting cannot honestly describe both. **No `paths` aliases** — four entries
and one `shared/` folder do not need them, and nothing asks for one.

**Both colour schemes, dark by default** (plan 002). The choice is persisted by
Mantine's own `localStorageColorSchemeManager` under the key
**`rphelper.color-scheme`**, and is deliberately **not** folded into
`rphelper.workspace-layout`: that record is the `app` entry's alone, while the
colour scheme applies to all four entries — folding it in would make the login
page's scheme depend on a workspace record. **Standing constraint: every feature
must be correct in both schemes.** A component that only looks right in one is a
defect, not a polish item. Before this, no doc stated a colour-scheme posture at
all, and "dark only" versus "both" is a constraint every later feature inherits
whether or not it is written down.

**Mantine 7 as the component library.** The product needs a markdown editor with
live preview (UC-043), forms, tables, modals and a large set of icon actions.
Mantine ships `Table`, `Modal` and `@mantine/tiptap` as one coherent set, so none
of that is hand-built. **`AppShell` is used by the `admin` entry and nowhere
else**: the `app` entry's workspace is a hand-written CSS grid, because a note
wall that is a floating overlay in one mode and a real column in the other cannot
be expressed through `AppShell`'s navbar/main/aside model (`workspace-shell.md`,
`admin-surfaces.md`). That asymmetry is deliberate and does not weaken the choice
of Mantine — the shell was one reason among several, not the reason.
**`@mantine/form` is not a dependency**, because forms go through the MobX
draft convention in `ui-conventions.md`, which forbids using it.
**`@mantine/notifications` IS used, for one narrow purpose — this reverses the
earlier "no toast system" note and the reversal is deliberate.** US-044.AC-4
requires a failed generation to show its reason and requires **the reason not to
persist once the notice has gone**, which an inline error above the stream cannot
satisfy: an inline error either stays or is dismissed by hand. So the package is
added for **transient failure reasons only**, `autoClose` 5000. The rule it
replaces was always about *success* noise and that half is unchanged: there are
still **no success toasts**. Full statement, the error codes it covers and the
reviewable boundary are in `ui-conventions.md`. No
Tailwind, no CSS modules, no styled-components — two small hand-written
stylesheets and no more: `global.css` for resets, and `shell.css` for the
workspace's layout rules alone (`frontend-structure.md`,
`workspace-shell.md`). Reason: a single styling authority. Mixing Mantine's
theme with a utility framework produces two sources of truth for spacing and
colour, and the workspace's geometry is a set of fixed constants owned in exactly
one place (`workspace-shell.md`).

**MobX 6 + `mobx-react-lite`.** The hot path is a streaming transcript: a reply
arrives as many small `token` frames (`llm-and-streaming.md`), each appended to an
observable message in the current zone, so only the component observing that
message re-renders and the tree, the wall and the settled record are untouched.
Two further grounds: per-page store classes instantiated and passed as props
explicitly — there is no React context, so a store's lifetime is visibly the
page's lifetime — and blur-save round trips that write one field of one observable
and re-read one row (`frontend-structure.md`, `workspace-shell.md`).

**No benchmark is claimed, and the one measurement-shaped argument this decision
used to carry is gone with its subject** — it cited a per-keystroke answer box and
an aside width driven into a CSS custom property by one `autorun`. The product has
**no answer box** and nothing in the workspace resizes (`workspace-shell.md`'s
reversal record); `frontend-structure.md` re-argued MobX on the three grounds
above and invented no replacement measurement. Neither does this line.

**`react-router-dom` 7** inside each entry, for in-entry navigation only.
Cross-entry navigation is a plain document navigation, because the entries are
separate documents.

**TipTap + `tiptap-markdown` for editing, `react-markdown` for rendering.**
FEAT-012/UC-043 wants a markdown editor with live preview; `@mantine/tiptap`
gives the toolbar, `tiptap-markdown` gives markdown in/out, and `react-markdown`
renders memos everywhere they are merely displayed.

**`@tabler/icons-react` `^3.40`.** One icon family, tree-shakable, matching
Mantine's visual weight. Sizing and the mandatory `IconButton` wrapper are
specified in `ui-conventions.md`.

**SQLite, one file for rows and vectors.** Single-instance, single-writer,
self-hosted: a client/server database would add an operational component with no
benefit. One file also makes FEAT-018's export a file-level or
logical-dump problem rather than a distributed-consistency problem, and makes
FEAT-005's drift report answerable from `PRAGMA` introspection.

**Alembic, for batch DDL only — not as the schema's source of truth.** The
unusual part is worth stating plainly, because the library's name carries an
assumption with it: RPHelper has **no migration history, no `versions/`
directory, no version table and no automatic upgrade at startup.** The
table-definition registry in `db/schema.py` is the source of truth, and the
administrator applies shape changes from the drift page's per-row `Create` and
`Sync` actions (`admin-surfaces.md`), which is a deliberate human-in-the-loop
gate over a table holding the roleplayer's own material. Alembic is present for
exactly one capability: SQLite cannot drop or retype a column in place, so a
`Sync` needs the create-copy-drop-rename table rebuild, and Alembic's **batch
operations** are the well-tested implementation of it. Adopted as an executor,
not as a framework. The decision follows the sibling project BookWriter's "DB
shape check" page, which works the same way. Full statement in
`backend-structure.md`. **Flip condition:** if the registry ever stops being able
to express a structure the product needs, or if an **unattended** upgrade becomes
a requirement — an instance nobody logs into as an administrator before it is
used — the migration-files trade gets re-opened, because both cases want an
ordered, replayable change history that a registry plus a button does not
provide.

**`sqlite-vec` for vectors, not LanceDB.** A deliberate divergence from
BookWriter, the sibling project these conventions are inherited from. RPHelper's
retrieval is *relational-with-vector-ordering*, not pure vector search:
`memo_search` joins vectors against a four-level memo chain filtered by
`is_enabled AND NOT is_forced` (R3, FEAT-014/UC-052), and `session_search` filters
by owner and character (FEAT-015/UC-054). With a separate vector store, those
filter columns must be denormalized into the vector store and kept in sync — and
both flags are togglable at any time, from the note wall as readily as from
anywhere else (FEAT-012/UC-044, UC-075), so every toggle becomes a second-store
write and a standing source of drift, in a product that has an
entire feature (FEAT-005) about detecting drift.

**The schema change strengthened this argument rather than weakening it.** The
single `memos.state` column of `forced` / `searchable` / `disabled` became the two
booleans `is_enabled` and `is_forced` (R3, `data-model.md`) — still relational,
still in the same database, and a toggle is still **one row updated in one
transaction with no vector work at all** (`search-and-retrieval.md`'s embedding
lifecycle). Where a split store owed one denormalized column per toggle, it now
owes two. `sqlite-vec` keeps vector writes
in the **same transaction** as relational writes, gives real SQL joins, and keeps
FEAT-018's four export granularities and FEAT-005's rebuild a one-store problem.
Its brute-force KNN is **exact**, so there is no recall tuning, and the relational
filters collapse N to hundreds or low thousands before any vector work happens.
**Flip condition, recorded so the decision can be re-checked rather than
defended:** if `session_search` ever needs per-entry embeddings *and* unscoped
cross-character search, N climbs and approximate indexing starts to matter. The
search layer is therefore kept behind a narrow port (`search-and-retrieval.md`)
so the backing store is swappable without touching callers.

**SQLite FTS5 alongside vectors, fused by reciprocal-rank fusion.** Reasoning in
`search-and-retrieval.md`; summarised: memos and entries contain proper nouns and
exact phrases that embeddings blur, and lexical-only search misses the
"same person or situation" semantics FEAT-015 promises. Both, fused, is cheap
when both indexes live in the same file.

**Snowflake ids, minted in application code before the INSERT.** Every primary key
is a 64-bit snowflake, not an `AUTOINCREMENT` rowid. The load-bearing product
reason: settle stamps the head row's own id onto `messages.related_to` for every
row it buries, **inside one transaction** (R11), so the id has to exist before the
row is durable. A snowflake is also k-sortable, so `ORDER BY id` *is* the stream
order and the schema carries no `position` column.

**The second reason this decision used to give has been withdrawn, and is
recorded as withdrawn rather than deleted.** It was that FEAT-018's import wants
ids meaning the same thing on two instances, turning identity-on-import from a
re-mapping problem into a collision check. **US-136.AC-2 rules that out**:
imported material must arrive under fresh identity, so the importer mints new
snowflakes and remaps the payload's internal references (`data-model.md`). The
decision stands on the first reason alone, which was always the stronger one —
and the withdrawal *simplifies* import rather than costing it anything, because
there is no longer a collision case to detect.

The mechanism — bit layout, the fixed epoch, the node-id rule, the
backwards-clock refusal — is in `data-model.md`'s Identifiers section and is not
restated here.

The cost is one rule that has to hold at every boundary: **an id is an `int` in
SQLite and Python and a decimal string in every JSON payload and every SSE
frame**, because a snowflake passes JavaScript's `Number.MAX_SAFE_INTEGER` about
25 days after the epoch, and an id that reaches JS as a `number` rounds silently —
possibly onto another row's id (`backend-structure.md`'s JSON id boundary,
`frontend-structure.md`'s "ids are strings"). Accepted as the price of the two
reasons above; it fails silently and late, which is why three docs state it.

**Flip condition, recorded because the whole scheme rests on one assumption.** The
41/10/12 layout **and** the JSON string boundary both assume **exactly one
generator process per node id**. Today that is a deployment guarantee — one
container, one uvicorn, the node id from config (`deployment.md`,
`backend-structure.md`) — not an accident of how it happens to be started. If
RPHelper ever runs more than one generator process — **a second uvicorn worker, or
a second instance that syncs rather than imports** — both need re-examining before
that change ships: a second worker left on the same node id mints a duplicate the
first time two inserts land in the same millisecond, and a syncing pair has no
import step at which ids would be re-minted, so it inherits the collision risk
that import itself no longer carries.

**HttpOnly `SameSite=Lax` cookie session (FEAT-002).** Single origin in both
topologies means no CORS configuration and no token plumbing in the SPA; HttpOnly
keeps the session out of reach of any script. This was the decisive reason the
four-entry frontend split is safe: cross-entry document navigation carries the
cookie automatically, so the entries need share no auth code.

**Server-side sessions behind that cookie (plan 004).** Sessions are rows in
`auth_sessions`; the cookie carries an **opaque 32-byte random token**, stored
server-side only as a **SHA-256 digest**, with an **absolute 720-hour expiry**
that is never extended. Server-side because FEAT-003's disable must end live
sessions, which a stateless token cannot do. The reasoning for the lifetime (no
sliding — every read would become a write on a single-writer database), the
digest (deliberately not Argon2) and each cookie flag is in
`backend-structure.md`'s authentication section and is not repeated here.

**Argon2id via `argon2-cffi` for password hashing (plan 003).** A memory-hard,
salted KDF whose parameters travel **inside** the stored encoded string
(`$argon2id$v=19$m=...`), so a parameter change is a rehash-on-verify concern and
never a schema change. **The parameters are the library's own current defaults,
deliberately not hand-picked**, so the project tracks a maintained baseline
instead of pinning a guess. The algorithm sits behind one module,
`app/services/passwords.py`, exposing a hash and a verify operation, so it is
swappable in one file and FEAT-002's login verifies through the same seam
(`backend-structure.md`). No doc fixed an algorithm before plan 003; its brief
recorded it as an open question and the user settled it. **Flip condition:** if
`argon2-cffi` stops being maintained, or a deployment target cannot supply its
native build, the seam module is the whole change surface — and the moment the
defaults are raised, a **rehash-on-verify** path becomes necessary in the login
flow, which no feature has built (see the deferred list).

**SSE for streaming, consumed with `fetch()` + `body.getReader()` +
`TextDecoder`, splitting frames on `"\n\n"` — not native `EventSource`.** The
reason is concrete: composing in the current zone is a **POST with a JSON body**
(`POST /api/sessions/{id}/zone/compose`, `backend-structure.md`), and
`EventSource` can only issue a GET. Rewriting the request as a GET with a query
string to satisfy the browser API would put the roleplayer's text in a URL. SSE
itself (over WebSockets) because the stream is one-directional
server→client, and it survives the nginx hop with two directives rather than an
upgrade dance.

**`loguru` for logging, not stdlib `logging` + `dictConfig`.** Rotation and
retention are built in, and the call site is one function rather than a
`getLogger(__name__)` per module. The cost is the thing to know about it: loguru
is a **parallel** logging system, so uvicorn's and SQLAlchemy's stdlib records
reach it **only** through an `InterceptHandler` installed as the stdlib root
handler — and if that bridge is missing, the rotating file is silently empty
while the console still looks right. Two sinks (console `DEBUG`, rotating file
`WARNING` under `data/logs/`), five `RPHELPER_LOG_*` settings, and an absolute
redaction rule that FEAT-019 imposes at **every** level: full statement, flip
condition and the forbidden/allowed lists in `deployment.md`.

**`web_search`: seam now, adapter later.** FEAT-016 is last in the dependency
graph (`features.md`). The tool seam, its switch in the configuration chain
(FEAT-013/UC-048), and its failure behaviour are specified in
`llm-and-streaming.md`; the provider adapter is not.

### Six decisions taken after the first pass

These were open when the doc set was first written and are now settled. Each is
recorded in full in the doc named beside it; the reasoning is repeated here
because a decision list that omits the *why* gets re-litigated.

**1. `session_search` runs the vector arm only — no BM25.**
(`search-and-retrieval.md`.) Enabling the lexical arm over `session_fts` would
reintroduce the structured partner-and-setup matching FEAT-015 deliberately
rejects (challenge C5): that index's columns are `title` and `partner_label`, so a
BM25 arm is in practice a partner-name matcher — precisely the signal that is
*absent* in the cases the feature exists to serve. `session_fts` is kept, because
FEAT-017's my-search is a different surface with a different rule. **Flip
condition:** reversible at low cost — nothing in the schema moves — if the promise
of finding "the same person or situation" **when neither is recorded** is found in
real use to need lexical recall.

**2. Persistence access is SQLAlchemy Core, not the ORM.**
(`backend-structure.md`.) Three reasons: (a) **explicit transaction scoping**,
which the R-rules require — a memo and its embedding commit together, a disable
flips the flag and revokes `auth_sessions` together, and settle's two UPDATEs plus
its `session_vec` refresh commit together or not at all (R11); (b) a **`text()`
escape hatch** for `vec0 MATCH` and FTS5 `MATCH`/`bm25()`, which no ORM
expression language covers; (c) declarative models would fight FEAT-005/UC-014's
need for **`PRAGMA`-based introspection against a single schema registry** —
`db/schema.py` stays the introspectable source of truth. Schema *evolution* was
left open here in the first pass and is now settled — the registry stays the
truth and the administrator applies shape changes with Alembic batch DDL; see
the Alembic entry in the stack list above.

**3. My-search shows disabled notes.**
(`search-and-retrieval.md`, cross-referenced from R3.) My-search applies **no
`is_enabled` / `is_forced` predicate at all** — only the owner predicate. Stated
as a predicate rather than as a state, because the single `state` column this
decision was first written against is gone: reach is two booleans now (R3,
`data-model.md`), and "shows disabled memos" became "applies neither flag". The
reasoning is unchanged. R3 constrains **the assistant's** reach, not the owner's
own UI — and re-enabling a note (UC-044) requires being able to find it first, so
hiding it would make it unreachable. A disabled hit is visibly marked as disabled
in the result list. The absolute exclusion still holds for `memo_search`,
`session_search` and context assembly. **Ratified.** This was recorded here as a
requirements gap resolved at the architecture layer with a note that
`/product-spec` should ratify it; it has — **US-137.AC-1** states that note state
never filters a result out, and **US-137.AC-2** that a disabled hit is shown as
disabled. The decision is now a read of the product rather than an architectural
judgement standing in for one. Only the *presentation* of a disabled hit stays
open (`search-and-retrieval.md`).

**4. Destructive admin actions get a confirm step.**
(`ui-conventions.md`.) A **deliberate addition** — the sibling project has no
confirm pattern anywhere, every delete and disable being a single unconfirmed
click. One shared confirm modal, used for: disabling an account (FEAT-003 — it
ends that user's sessions, so someone is signed out mid-roleplay), deleting an LLM
connection (FEAT-004 — irreversible), and rebuilding the vector index (FEAT-005 —
expensive in time and metered LLM calls). **No acceptance criterion requires
this**; it is an architectural judgement about irreversible and expensive
operations, so FEAT-003/004/005's planners may revisit it. The confirm text may
never name a blast radius R5 forbids it to know.

**5. "Test connection" gets a dedicated endpoint.**
(`backend-structure.md`, `admin-surfaces.md`.) The sibling project tests a
connection by reusing its model-listing probe; RPHelper does not. FEAT-004's
purpose line treats testing a connection as **its own capability** (UC-011), and
overloading model-listing conflates "can I reach and authenticate against this
server" with "what can it run". The **backend probe primitive is reused** — one
implementation — but exposed as its own route with its own **typed** result, so the
UI can report a bad base URL without opening a model picker.

**6. Abandoning a current zone is resolved, and it is frontend-only.**
(`workspace-shell.md`, `backend-structure.md`.) This was carried in the deferred
list below as a **product gap**; UC-086, US-134 and US-135 close it. An empty
current zone **has no rows at all** — R11 defines the zone as the rows matching
`related_to IS NULL AND settled_at IS NULL`, so an empty one is an empty set and
there is nothing for the server to discard. Abandoning therefore clears the
unsent composer draft and the kind switch, **in the client, with no route and no
backend surface**. That is the reason this option was chosen over a discard
endpoint: **R11 is left exactly as it was** — raw `messages` is still touched by
exactly two operations, settle and re-open — and a discard route would weaken
that invariant while removing nothing, because there is nothing to remove. The
paired half is US-135: settling never requires an assistant answer, so a zone
holding only the roleplayer's own text can always be settled. **The two rules are
a pair** — without US-135 a zone holding text could be neither discarded (US-134)
nor settled, which is an inescapable state.

## Deliberately deferred, and known gaps

Stated here so no reader mistakes an absence for an oversight. The first four
are deferrals the architecture chose; the fifth is a product non-goal it must not
quietly mitigate; the last two are unspecified postures. **There is no longer a
product-gap entry here** — the one that used to sit at the bottom, abandoning a
current zone without settling, is **resolved** and is decision 6 above.

- **FEAT-018's four export granularities in full detail.** The contract is
  *sketched* in `data-model.md` — envelope shape, granularity boundaries, the
  known consequence recorded at FEAT-018's `_TBD:` — because the data model has
  to be shaped compatibly with it. Full field-level detail is written when the
  feature is planned. FEAT-018 is last but one in the dependency graph.
- **FEAT-016's search-provider adapter.** Seam only, per above.
- **Frontend dependencies the foundation deliberately does not install** (plan
  002), each owned by the feature that first needs it: TipTap, `tiptap-markdown`
  and `@mantine/tiptap` (the markdown editor, plan `015`); `react-markdown` (plan
  `015`); `@dnd-kit` (note reordering, plan `008` — and no doc names a sub-package
  or version, so that feature chooses). **`postcss-preset-mantine` is not
  installed** either: it is needed only to author CSS with Mantine's mixins, and
  with `global.css` holding resets and `shell.css` empty there is no call site;
  plan `008` adds it if the workspace grid wants the mixins. **`mobx` and
  `mobx-react-lite` ARE installed** although the foundation ships no store,
  because the MobX conventions are the foundation's to fix. Reason for the rest:
  an unused dependency in a foundation is a version pinned against no call site
  and a bundle weighed down for nothing — and without this list the next planner
  re-derives why five packages the docs name are absent. These are deferrals of
  *installation*, not of the stack choices above, which stand.
- **What FEAT-002 deliberately does not build** (plan 004), each the first thing
  a reviewer of an authentication feature looks for:
  - **no session refresh and no sliding expiry** — every read would become a
    write on a single-writer database (`backend-structure.md`, with its flip
    condition);
  - **no rate limiting, lockout or attempt counting** — nothing in
    `docs/product/` asks for one, and a self-hosted instance on a trusted LAN is
    not the threat model `deployment.md` describes; recorded so it is a decision
    rather than an oversight;
  - **no "remember me"** — not built; listed so its absence is not read as an
    oversight;
  - **no password reset or change-password path** in FEAT-002 — that is
    FEAT-003's;
  - **no rehash-on-verify** — the standing consequence of the Argon2id decision's
    flip condition above, still unbuilt and **owned by no feature**;
  - **no session-listing or sign-out-everywhere surface** — logout revokes the
    calling session only.
- **Context compaction — an explicit non-goal, and no longer an open question.**
  `vision.md` records that session context grows forever with no ceiling, no
  warning and no pruning, and that the user chose this knowingly over three
  bounded alternatives. The architecture therefore contains no pruning, no
  summarisation and no token budget. **The `_TBD:` this bullet used to carry is
  closed — downgraded to a recorded non-goal, not answered.** `vision.md`'s "No
  context compaction" non-goal now states the consequence in its own words
  ("a long RP will eventually exceed what the model can hold, nothing warns
  first, and the refusal surfaces as an ordinary generation failure (US-044)
  whose reason is shown"), and FEAT-009 and FEAT-010 both restate it as
  deliberate. So the operational reality is **decided**, not unknown. It stays
  written down because a planner still needs to see it: nothing in this doc set
  mitigates it, a context-window refusal arrives as an ordinary provider failure
  with no special handling, and US-044.AC-4's transient failure notice is the
  only thing the roleplayer ever sees of it (`llm-and-streaming.md`,
  `ui-conventions.md`).
- **TLS.** The inherited posture is HTTP only — no `listen 443`, no certificates,
  anywhere. `_TBD: if the instance is ever reachable beyond a trusted LAN, TLS
  termination must be designed, and the session cookie's `Secure` flag — shipped
  OFF by FEAT-002 with that flip condition attached — must be turned on._` See
  `deployment.md`.
- **Metrics and alerting.** Logging is now specified (`deployment.md`); metrics
  and alerting are not, and `docs/product/` names neither. Recorded as an
  absence rather than left implied by the logging section beside it.

## Non-functional posture

The product states no throughput, latency or availability numbers, so none are
invented here. What the product *does* state, and what the design must therefore
satisfy:

| Stated requirement | Where the design satisfies it |
|---|---|
| S2 — a reply takes minutes, not tens of minutes (`vision.md`) | A candidate streams into the current zone over SSE (UC-034) so first tokens appear immediately; cached translations (UC-041); no re-explaining of context on every reply (S1) via the memo chain (R2) |
| No cross-user visibility of any kind, including for the admin | `domain-rules.md` isolation rules; separate admin entry; the forbidden reverse lookup |
| An enormous paste warns but is never refused (US-035.AC-2) | `client_max_body_size` set generously (`deployment.md`); the warning is a client-side context-cost notice, never a server rejection |
| Nothing the roleplayer typed is lost when the LLM fails (UC-032) | Roleplayer text is persisted before any model call (R10, `llm-and-streaming.md`) |
| Archived material is never destroyed (UC-067/UC-068/UC-025) | `archived_at` column, never a delete (R6, `data-model.md`) |

`_TBD: no concurrency target exists. The design assumes one active roleplayer at
a time per instance, which SQLite's single-writer model suits; nothing in
docs/product/ states a multi-user-concurrency expectation either way._`
