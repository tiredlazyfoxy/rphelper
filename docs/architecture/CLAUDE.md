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

**Twelve** docs, fixed. A new top-level doc must come from the architect's
briefing — never added unilaterally.

| File | Holds |
|---|---|
| `overview.md` | System context, actor→surface map, topology, the stack decision list, deferrals |
| `quick-reference.md` | Dense agent-first index: doc map, ports, commands, paths, the id rule, invariants, error codes, geometry |
| `data-model.md` | Tables, snowflake identifiers, ownership columns, the merged `messages` table and its two views, archive semantics, vector + FTS tables, export/import contract |
| `domain-rules.md` | The role ladder and the cross-cutting invariants every feature binds to |
| `backend-structure.md` | FastAPI layout, routers/services split, the JSON id boundary, the stream routes, settle/re-open, the `(( ))` seam, persistence access, config, secrets, error model |
| `frontend-structure.md` | Vite multi-entry, MobX convention, routing, "ids are strings", the API client, SSE consumer |
| `workspace-shell.md` | The `app` entry's one screen: the three columns, all geometry, the note wall's two modes, layout persistence, the stream, the ruler and the current zone, the character page, the user menu |
| `ui-conventions.md` | Everything that is **not** the shell: icons and the shared `IconButton`, the icon table, the accessibility floor, and the list/modal/MobX-draft/confirm CRUD conventions |
| `admin-surfaces.md` | The `admin` entry in full: its routes, shell, access gate, and the three administrative pages — what is inherited from the sibling project, what deviates, and why |
| `llm-and-streaming.md` | LLM client abstraction, SSE protocol, tool loop, context assembly |
| `search-and-retrieval.md` | Hybrid vector + FTS search, the three search surfaces, embedding lifecycle |
| `deployment.md` | Ports, dev/prod topology, nginx, compose, config conventions |

### When a doc splits

**Split a doc when it has come to cover two subjects, not when it crosses a line
count. Name the split in `quick-reference.md`.** A doc that is long because its
subject is long is doing its job; a doc that is long because two subjects moved in
under one filename is the thing to fix. Either way the split is a new top-level
doc and therefore needs a briefing.

Current lengths, recorded honestly rather than implied:

| Doc | Lines | |
|---|---|---|
| `backend-structure.md` | 1477 | **split candidate — two subjects; badly over budget** (below) |
| `data-model.md` | 937 | deliberate exception |
| `quick-reference.md` | 889 | exempt; intentionally dense — the count is informational only |
| `frontend-structure.md` | 840 | over |
| `admin-surfaces.md` | 768 | over |
| `llm-and-streaming.md` | 696 | over |
| `domain-rules.md` | 688 | deliberate exception |
| `search-and-retrieval.md` | 640 | deliberate exception |
| `workspace-shell.md` | 630 | deliberate exception |
| `ui-conventions.md` | 629 | **split candidate — two subjects** |
| `deployment.md` | 622 | over |
| `overview.md` | 590 | over |

Re-counted at the finalization of plans 001..007 (2026-10-01), after that pass's
three batches landed. The counts drift with every pass after it, so a reader who
needs the real number opens the file rather than trusting the row. **Every doc is
now over the ~400-line budget**; that is mostly the as-built records the
finalization added, and it is not by itself a reason to split (the rule above).

**`backend-structure.md` is the outlier — roughly three and a half times the
budget, and nearly double its last recorded count.** The finalization added the
three admin route surfaces, the per-code status record and the 500 posture, the
probe's as-built postures, the first async code, and the Sync rebuild's
foreign-key posture, on top of the stream/settle material that already made it a
two-subject doc. **The `session-stream.md` split below is more pressing than when
it was identified and is still not authorized**; that is the part of this section
that binds.

The four deliberate exceptions, each with the reason it stays whole:

- **`data-model.md`** — it is **one schema**. Splitting it puts half the columns
  behind a second filename and makes "which table holds `related_to`?" a lookup.
- **`domain-rules.md`** — it is **one flat R-namespace**. "Which doc has R9?" must
  never be a question anyone has to ask.
- **`search-and-retrieval.md`** — the **contrast** between the assistant's two
  tools and the roleplayer's my-search *is* the point of the doc. Split, the
  distinction the product insisted on stops being visible on one page.
- **`workspace-shell.md`** — it is **one screen**.

Two splits are **identified and not authorized**. Neither is done; each needs a
briefing:

- **`session-stream.md`** — would lift the stream routes, settle/re-open and the
  `(( ))` seam out of `backend-structure.md`. That doc now genuinely carries two
  subjects: the FastAPI application's shape, and the session stream's behaviour.
  It would be the backend counterpart to `workspace-shell.md`.
- **`forms-and-lists.md`** — would lift the CRUD conventions out of
  `ui-conventions.md`, leaving icons and the accessibility floor behind. Already
  named as the split candidate in `quick-reference.md`.

`admin-surfaces.md` was already over budget **before** this delta began — it grew
inside it, but its length is not a consequence of the workspace rework — and is
**not** proposed for a split: it is one subject, the `admin` entry in full.

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
UC-001..087, US-001..140 — treat as a sanity check, not as the source.) Rules:

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
