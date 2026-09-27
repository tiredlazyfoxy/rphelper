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

**Eleven** docs, fixed. A new top-level doc must come from the architect's
briefing — never added unilaterally.

| File | Holds |
|---|---|
| `overview.md` | System context, actor→surface map, topology, the stack decision list, deferrals |
| `quick-reference.md` | Dense agent-first index: ports, commands, paths, invariants, doc map |
| `data-model.md` | Tables, ownership columns, archive semantics, vector + FTS tables, export/import contract |
| `domain-rules.md` | The role ladder and the cross-cutting invariants every feature binds to |
| `backend-structure.md` | FastAPI layout, routers/services split, persistence access, config, secrets, error model |
| `frontend-structure.md` | Vite multi-entry, MobX convention, routing, SSE consumer |
| `ui-conventions.md` | Layout shell, the two resize behaviours, persistence, icons, the list/modal/form CRUD conventions |
| `admin-surfaces.md` | The `admin` entry in full: its routes, shell, access gate, and the three administrative pages — what is inherited from the sibling project, what deviates, and why |
| `llm-and-streaming.md` | LLM client abstraction, SSE protocol, tool loop, context assembly |
| `search-and-retrieval.md` | Hybrid vector + FTS search, the three search surfaces, embedding lifecycle |
| `deployment.md` | Ports, dev/prod topology, nginx, compose, config conventions |

Line budget: ~400 lines per doc. `quick-reference.md` is the one exception — it
is intentionally dense. A doc that outgrows its budget splits off its largest
subsystem, and the split is named in `quick-reference.md`.

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

Ids come from `docs/product/` (FEAT-001..019, UC-001..068, US-001..087,
acceptance criteria as `US-###.AC-#`). Rules:

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
  inheritance chains, the collapse rule, the two resize performance strategies).
  Each must say *so it is not "fixed" later*.
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
frontend, Mantine 7 + MobX 6 + Tabler icons, SSE over POST, HttpOnly cookie auth,
two roles (`roleplayer` / `admin`), single origin in dev and prod.
Build and test commands live in the **root `CLAUDE.md`** and are never duplicated
here.
