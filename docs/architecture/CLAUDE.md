# Architecture Folder

The design layer for RPHelper: **how** the system is built. Answers questions the
product layer deliberately refuses to answer. Read by `/planner`,
`/fast-feature`, skeleton, coder and verifier agents before any code is written.

## Scope — three layers, three questions

| Layer | Question | Folder |
|-------|----------|--------|
| Product | why / who-for / what-for-whom | `docs/product/` |
| Architecture | **how** | `docs/architecture/` (this folder) |
| Plans | the work | `docs/plans/` |

Architecture sits **after or alongside** the product layer. It reads product ids
to know what it is designing for; the product layer never reads back.

## File set

**Fifteen** docs, fixed. A new top-level doc must come from the architect's
briefing — never added unilaterally. (It was twelve until the finalization of
plans 008..032, which performed three authorized splits — see "When a doc
splits".)

| File | Holds |
|---|---|
| `overview.md` | System context, actor→surface map, the outbound surface in full, topology, the stack decision list, deferrals |
| `quick-reference.md` | Dense agent-first index: doc map, ports, commands, paths, the id rule, invariants, error codes with statuses, geometry, the flip-condition index, the `_TBD:` registry, the defects block |
| `data-model.md` | Tables, snowflake identifiers, ownership columns, the merged `messages` table and **the four named Core selectables over it**, archive semantics, vector + FTS tables and their trigger conditions. **Not the export/import contract — that moved to `transfer.md`; the tables and columns it reads stayed here** |
| `domain-rules.md` | The role ladder and the cross-cutting invariants every feature binds to |
| `backend-structure.md` | FastAPI layout, routers/services split and the service-to-service import pattern, the JSON id boundary, the route surfaces, persistence access, config, secrets, the error model and the per-code status record, schema evolution, the two transaction rules. **Not the stream routes, not settle/re-open, not the `(( ))` seam — those moved to `session-stream.md`; not the export/import contract — that moved to `transfer.md`** |
| `session-stream.md` | The session stream's **backend**: the route surface and wire shape, `PATCH`'s reach, create-and-seed, settle and re-open, the degraded embedding path, the `(( ))` seam, the compose route and its streaming harness, the tool seam and dispatch, the discussion read. The backend counterpart to `workspace-shell.md` |
| `transfer.md` | Export and import: the envelope, the id-serialization rules, the two version constants, the four granularities, what is never exported, the export and import route surfaces, the import policy, the whole-database replace |
| `frontend-structure.md` | Vite multi-entry, the four entries' boot shapes, the case-collision naming rule, MobX convention, routing, "ids are strings", the API client, the SSE consumer, markdown, the two stylesheets |
| `workspace-shell.md` | The `app` entry's screens: the three columns, all geometry, the note wall's two modes, layout persistence, the stream, the ruler and the current zone, the kind switch and settle, the stop control, the wall's contents, the character page, the draft page, the user menu, the model picker |
| `ui-conventions.md` | Icons and the shared `IconButton`, the icon table, the accessibility floor, async feedback, the inherited frontend facts. **Not the CRUD conventions — those moved to `forms-and-lists.md`** |
| `forms-and-lists.md` | Tables and lists, the modal rule and its named exceptions, the MobX draft form, the confirm convention, empty states, mutations-are-never-optimistic and its one exception, page state |
| `admin-surfaces.md` | The `admin` entry in full: its routes, shell, access gate, and the three administrative pages — what is inherited from the sibling project, what deviates, and why |
| `llm-and-streaming.md` | LLM client abstraction, SSE protocol, the stop, the tool loop, `web_search`'s provider seam, context assembly, language handling, translation |
| `search-and-retrieval.md` | Hybrid vector + FTS search, the narrow port, the three search surfaces, the embedding lifecycle, rebuild |
| `deployment.md` | Ports, TLS, dev/prod topology, nginx, compose, config conventions, logging |

### When a doc splits

**Split a doc when it has come to cover two subjects, not when it crosses a line
count. Name the split in `quick-reference.md`.** A doc that is long because its
subject is long is doing its job; a doc that is long because two subjects moved in
under one filename is the thing to fix. Either way the split is a new top-level
doc and therefore needs a briefing.

Current lengths, re-counted at the finalization of plans 008..032 (2026-10-06),
after that pass's four batches landed:

| Doc | Lines | |
|---|---|---|
| `backend-structure.md` | 1892 | **split candidate — two subjects; badly over budget** (below) |
| `quick-reference.md` | 1412 | exempt; intentionally dense — the count is informational only |
| `workspace-shell.md` | 1338 | **split candidate — the "one screen" exception is strained** (below) |
| `data-model.md` | 1288 | deliberate exception |
| `frontend-structure.md` | 1231 | over |
| `llm-and-streaming.md` | 1198 | **split candidate — two subjects** (below) |
| `search-and-retrieval.md` | 1196 | deliberate exception, **under pressure** (below) |
| `domain-rules.md` | 1036 | deliberate exception |
| `admin-surfaces.md` | 884 | over |
| `deployment.md` | 776 | over |
| `overview.md` | 634 | over |
| `ui-conventions.md` | 580 | over |
| `session-stream.md` | 572 | over — new at this pass |
| `forms-and-lists.md` | 451 | over — new at this pass |
| `transfer.md` | 394 | within budget — new at this pass |

The counts drift with every pass, so a reader who needs the real number opens the
file rather than trusting the row. **Every doc is over the ~400-line budget**
(`transfer.md` is at it), and that is mostly the as-built records of
**twenty-five plans** across two finalizations. **Per the rule above, length is
not by itself a reason to split.** What follows is about subjects, and the counts
are evidence rather than the argument.

The four deliberate exceptions, each with the reason it stays whole:

- **`data-model.md`** — it is **one schema**. Splitting it puts half the columns
  behind a second filename and makes "which table holds `related_to`?" a lookup.
  This is why the 008..032 split moved only the export/import **contract** to
  `transfer.md` and left every table and column definition here.
- **`domain-rules.md`** — it is **one flat R-namespace**. "Which doc has R9?" must
  never be a question anyone has to ask.
- **`search-and-retrieval.md`** — the **contrast** between the assistant's two
  tools and the roleplayer's my-search *is* the point of the doc. Split, the
  distinction the product insisted on stops being visible on one page.
- **`workspace-shell.md`** — it is **one screen**. (Now strained — below.)

### The three splits authorized at the finalization of plans 008..032 — all done

The doc set went from twelve to fifteen. Content was **moved, not re-derived**;
each new doc opens with a `**Realizes:**` line and each origin doc keeps a
one-line pointer where the content left.

- **`session-stream.md`** — lifted the stream routes, settle/re-open, the `(( ))`
  seam, the compose route and its harness, the tool seam and the discussion read
  out of `backend-structure.md`. It is the backend counterpart to
  `workspace-shell.md`. **Done.**
- **`transfer.md`** — lifted the export/import contract out of
  `backend-structure.md` and `data-model.md`. **Done.**
- **`forms-and-lists.md`** — lifted the CRUD conventions out of
  `ui-conventions.md`, leaving icons, the icon table, the shared `IconButton`,
  the accessibility floor and async feedback behind. **Done.**

**What actually happened to `backend-structure.md` is worth recording, because it
is the opposite of what a split is supposed to achieve.** The two splits moved
roughly 230 lines out of it, and **seventeen plans' as-built records more than
replaced them**: it went 1477 → 1737 → 1871 → **1892** across the pass's four
batches. The doc is no smaller than when it was first identified as a split
candidate; it is smaller than it would have been. That is the honest post-round
reality, and it is why a further split is identified below rather than treated as
discharged by the two that happened.

### Newly identified and not authorized — three candidates, none performed

Each needs a briefing, by the same rule as the three above. **The user authorized
three splits at the 008..032 finalization and has not seen these; none is done,
and none may be performed without being asked for.**

- **`backend-structure.md` — 1892 lines.** It still carries two subjects, and the
  seam is clean: **the route surfaces** (bootstrap, auth, the three admin
  families, the six roleplayer families) away from **the application and
  persistence layer** (layout, the routers/services split, the JSON id boundary,
  configuration, secrets, the error model and the per-code status record,
  database access, schema evolution). The route surfaces are a reference a
  planner looks things up in; the rest is a contract a planner reads once.
- **`workspace-shell.md` — 1338 lines.** The **"it is one screen" exception above
  is strained**: the doc now covers the session workspace *and* the character
  page, the draft page, the user menu and the model picker. The seam is **the
  character page** — it has its own route, two columns instead of three, no wall,
  no ruler, no zone and no stop control, and it is the only screen that creates a
  session by writing. Lifting it would leave `workspace-shell.md` near 900 lines
  and genuinely about one screen again.
- **`llm-and-streaming.md` — 1198 lines.** Two subjects: the client, the SSE and
  stop protocol and the tool loop on one side; **context assembly** on the other.
  The seam is a new `context-assembly.md`. The two share only the fact that the
  prompt is what the client is handed, and `services/context.py` already has no
  caller but `compose.py`.

**`search-and-retrieval.md` — 1196 lines — is named as a pressure on its
exception, NOT as a candidate.** It is a recorded deliberate exception above
because the contrast between the assistant's two tools and the roleplayer's
my-search is the point of the doc, and the product insisted on that distinction.
Splitting it would **overturn the exception**, which is a different and larger
decision from performing a split the exception does not cover. Recorded here so
the count is not mistaken for an unexamined omission.

`admin-surfaces.md` is **not** proposed for a split: it is one subject, the
`admin` entry in full.

## Who writes, who reads

- **Writer**: the `/architect` agent only. Planners, skeletons, coders,
  test-coders and verifiers read these files and never edit them.
- **Never write outside this folder**, with two named exceptions the briefing
  must grant: the root `CLAUDE.md` and `docs/plans/CLAUDE.md` during bootstrap,
  and an `Applied` status footer on a plan's `outcome.md` during finalization.
- **Never write into `docs/product/`.** A requirement you disagree with is a
  hand-back concern, not an edit.

## Requirements are cited, never restated

Every doc that realizes product requirements opens with:

```
**Realizes:** FEAT-003, UC-007, UC-008
```

Ids come from `docs/product/`, and **`docs/product/quick-reference.md` is the
registry of record** — the sole canonical list of every `ACT-###`, `FEAT-###`,
`UC-###`, `US-###` and `US-###.AC-#`. Check an id there, never against a range
quoted in a design doc or a briefing: a range goes stale the moment a feature
lands, and a range that spans ids owned by several features is how a citation ends
up attributed to the wrong one. (Current as of this writing: FEAT-001..020,
UC-001..088, US-001..147 — treat as a sanity check, not as the source.) Rules:

- **Cite, do not copy.** If a reader needs the behavioural detail, they open the
  product doc. Architecture states the *mechanism* that satisfies the
  requirement, not the requirement itself.
- **Never invent an id.** An id not present in `docs/product/` does not exist.
- **Never invent a requirement.** Unspecified → `_TBD: <reason>_`, never a
  plausible guess dressed as a decision.
- Where a product doc records a `_TBD:`, carry it forward rather than silently
  resolving it in design.

## Write-rules

- **State decisions with reasoning.** "We chose X because Y" — never a bare "We
  chose X". A decision with no recorded reason is re-litigated within a month.
- **Name deliberate asymmetries as deliberate.** RPHelper has several (the
  inheritance chains, the collapse rule, the hand-written `app` grid beside
  `admin`'s `AppShell`). Each must say *so it is not "fixed" later*.
- **State what is not in scope.** Deferrals belong in `overview.md`'s deferred
  section with the reason for deferring.
- **Record the flip condition** on any decision taken under uncertainty (for
  example the vector-store choice): what would have to become true for the
  decision to be wrong.
- ASCII diagrams and tables where shape matters; prose for reasoning; lists for
  enumerable things. No marketing language.
- No application code here. No step files, no feature plans — those are
  `docs/plans/`.

## Stack facts a reader can assume

Python + FastAPI backend, **SQLAlchemy Core (not the ORM)**, SQLite (one file for
rows and vectors, `sqlite-vec` + FTS5), React 19 + TypeScript + Vite multi-entry
frontend (**TypeScript only — no JavaScript source, config included, no
`allowJs`**), Mantine 7 + MobX 6 + Tabler icons, SSE over POST, HttpOnly cookie auth,
two roles (`roleplayer` / `admin`), single origin in dev and prod.
**Alembic is present as a batch-DDL executor only** — it is what the drift page's
`Create` / `Sync` runs behind; `db/schema.py` stays the schema's source of truth,
and there is no `versions/` directory, no revision chain, no version table and no
DDL at startup (`backend-structure.md`, `overview.md`). Styling is **two
hand-written stylesheets, not one**: `global.css` for resets across every entry,
`shell.css` for the `app` workspace's layout alone — the grid, the `--navw` rail,
the 820px threshold (`frontend-structure.md`). Everything else is Mantine;
Tailwind, CSS Modules and styled-components stay forbidden.
Build and test commands live in the **root `CLAUDE.md`** and are never duplicated
here.
