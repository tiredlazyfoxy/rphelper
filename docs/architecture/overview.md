# System overview

**Realizes:** FEAT-001, FEAT-002, FEAT-003, FEAT-004, FEAT-005, FEAT-019,
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
isolation enforceable — see `domain-rules.md`.

## Actor → surface map

Each actor reaches exactly one frontend entry. The mapping is the reason the
frontend is a multi-entry build rather than one bundle (`frontend-structure.md`).

| Actor | Surface | Vite entry | Route base | Available when |
|---|---|---|---|---|
| ACT-003 first-run operator | Bootstrap | `bootstrap` | `/bootstrap` | Only while the instance is unconfigured (UC-003) |
| ACT-001 / ACT-002 (unauthenticated) | Login | `login` | `/login` | Always, once configured |
| ACT-001 administrator | Admin | `admin` | `/admin` | Authenticated, admin role |
| ACT-002 roleplayer | App | `app` | `/` | Authenticated |
| ACT-004 assistant | — | none | — | Inside a discussion only |

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

**React 19 + TypeScript + Vite, multi-entry.** Four entries because four actor
surfaces with genuinely disjoint code exist (table above). Vite because
multi-entry via `build.rollupOptions.input` is a first-class feature, and its dev
proxy gives the single-origin story for free.

**Mantine 7 as the component library.** The product needs a three-pane
application shell, a markdown editor with live preview (UC-043), forms, tables,
modals and a large set of icon actions. Mantine ships `AppShell`, `Table`,
`Modal` and `@mantine/tiptap` as one coherent set, so none of that is hand-built.
Two of its packages are deliberately *not* used: **`@mantine/form`**, because forms
go through the MobX draft convention in `ui-conventions.md`, and
**`@mantine/notifications`**, because there is no toast system. No
Tailwind, no CSS modules, no styled-components — one small hand-written
`global.css` for resets only. Reason: a single styling authority. Mixing Mantine's
theme with a utility framework produces two sources of truth for spacing and
colour, and the resize behaviours in `ui-conventions.md` depend on knowing
exactly who owns a width.

**MobX 6 + `mobx-react-lite`.** The hot paths are a streaming transcript and a
per-keystroke answer box. MobX's fine-grained observation lets the aside width be
driven by an `autorun` into a CSS custom property with **zero component
re-renders** (`ui-conventions.md` (A)) — a thing that is awkward to express in a
reducer-based store. Per-page store classes are instantiated and passed as props
explicitly; there is no React context, so a store's lifetime is visibly the
page's lifetime.

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

**`sqlite-vec` for vectors, not LanceDB.** A deliberate divergence from
BookWriter, the sibling project these conventions are inherited from. RPHelper's
retrieval is *relational-with-vector-ordering*, not pure vector search:
`memo_search` joins vectors against a four-level memo chain filtered by
`state = 'searchable'` (FEAT-014/UC-052), and `session_search` filters by owner
and character (FEAT-015/UC-054). With a separate vector store, those filter
columns must be denormalized into the vector store and kept in sync — and
FEAT-012/UC-044 lets a memo's state change at any time, so every toggle becomes a
second-store write and a standing source of drift, in a product that has an
entire feature (FEAT-005) about detecting drift. `sqlite-vec` keeps vector writes
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

**HttpOnly `SameSite=Lax` cookie session (FEAT-002).** Single origin in both
topologies means no CORS configuration and no token plumbing in the SPA; HttpOnly
keeps the session out of reach of any script. This was the decisive reason the
four-entry frontend split is safe: cross-entry document navigation carries the
cookie automatically, so the entries need share no auth code.

**SSE for streaming, consumed with `fetch()` + `body.getReader()` +
`TextDecoder`, splitting frames on `"\n\n"` — not native `EventSource`.** The
reason is concrete: sending a discussion message is a **POST with a JSON body**,
and `EventSource` can only issue a GET. Rewriting the request as a GET with a
query string to satisfy the browser API would put discussion text in a URL. SSE
itself (over WebSockets) because the stream is one-directional
server→client, and it survives the nginx hop with two directives rather than an
upgrade dance.

**`web_search`: seam now, adapter later.** FEAT-016 is last in the dependency
graph (`features.md`). The tool seam, its switch in the configuration chain
(FEAT-013/UC-048), and its failure behaviour are specified in
`llm-and-streaming.md`; the provider adapter is not.

### Five decisions taken after the first pass

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
which the R-rules require — a memo and its embedding commit together, and a
disable flips the flag and revokes `auth_sessions` together; (b) a **`text()`
escape hatch** for `vec0 MATCH` and FTS5 `MATCH`/`bm25()`, which no ORM
expression language covers; (c) declarative models would fight FEAT-005/UC-014's
need for **`PRAGMA`-based introspection against a single schema registry** —
`db/schema.py` stays the introspectable source of truth. Schema *evolution*
(migration files versus registry-only create-if-missing) is deliberately still
open there.

**3. My-search shows `disabled` memos.**
(`search-and-retrieval.md`, cross-referenced from R3.) R3 constrains **the
assistant's** reach, not the owner's own UI — and re-enabling a memo (UC-044)
requires being able to find it first, so hiding it would make it unreachable. The
absolute exclusion still holds for `memo_search`, `session_search` and context
assembly. **This is a requirements gap resolved at the architecture layer:
`/product-spec` should ratify it into FEAT-017's acceptance criteria.**

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

## Deliberately deferred

Stated here so no reader mistakes an absence for an oversight.

- **FEAT-018's four export granularities in full detail.** The contract is
  *sketched* in `data-model.md` — envelope shape, granularity boundaries, the
  known consequence recorded at FEAT-018's `_TBD:` — because the data model has
  to be shaped compatibly with it. Full field-level detail is written when the
  feature is planned. FEAT-018 is last but one in the dependency graph.
- **FEAT-016's search-provider adapter.** Seam only, per above.
- **Context compaction — an explicit non-goal, not a gap.** `vision.md` records
  that session context grows forever with no ceiling, no warning and no pruning,
  and that the user chose this knowingly over three bounded alternatives. The
  architecture therefore contains no pruning, no summarisation and no token
  budget. `_TBD: a long RP will eventually exceed what the model can hold, and
  nothing warns the user first — carried forward from vision.md's non-goals and
  FEAT-009/FEAT-010's own _TBD:. No mechanism in this doc set mitigates it._`
- **TLS.** The inherited posture is HTTP only — no `listen 443`, no certificates,
  anywhere. `_TBD: if the instance is ever reachable beyond a trusted LAN, TLS
  termination and cookie `Secure` flags must be designed; neither is specified
  today._` See `deployment.md`.

## Non-functional posture

The product states no throughput, latency or availability numbers, so none are
invented here. What the product *does* state, and what the design must therefore
satisfy:

| Stated requirement | Where the design satisfies it |
|---|---|
| S2 — a reply takes minutes, not tens of minutes (`vision.md`) | Streaming candidates (SSE) so first tokens appear immediately; cached translations (UC-041); zero re-typing of context (S1) via the memo chain |
| No cross-user visibility of any kind, including for the admin | `domain-rules.md` isolation rules; separate admin entry; the forbidden reverse lookup |
| An enormous paste warns but is never refused (US-035.AC-2) | `client_max_body_size` set generously (`deployment.md`); the warning is a client-side context-cost notice, never a server rejection |
| Nothing the roleplayer typed is lost when the LLM fails (UC-032) | Roleplayer text is persisted before any model call (`llm-and-streaming.md`) |
| Archived material is never destroyed (UC-019/UC-068/UC-025) | `archived_at` column, never a delete (`data-model.md`) |

`_TBD: no concurrency target exists. The design assumes one active roleplayer at
a time per instance, which SQLite's single-writer model suits; nothing in
docs/product/ states a multi-user-concurrency expectation either way._`
