# RPHelper

## What this is

RPHelper is a self-hosted assistant that helps one roleplayer compose **their own
side** of a roleplay conducted on external sites and Discord, in a language they
are not a confident writer in. The value is not the generation — three
workarounds already generate text — it is the **persistent per-character context
layer**: prompts, memos and memory that live somewhere so context never has to be
re-explained on every reply. See `docs/product/vision.md` for the problem, the
three success signals and the non-goals. The assistant never writes the partner's
side, there is no platform integration, and the outbound boundary is the
clipboard.

## Build & Test Commands

```
Backend  (run from backend/)
  test       .venv/Scripts/python -m pytest
  typecheck  .venv/Scripts/python -m mypy app
  lint       .venv/Scripts/python -m ruff check .
Frontend (run from frontend/)
  build      npm run build
  test       npm test
  typecheck  npm run typecheck
```

Every downstream agent reads its commands from this section and nowhere else.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI, `pydantic-settings` config, `uvicorn` |
| Store | SQLite — one file for relational rows **and** vectors |
| Vectors | `sqlite-vec` (`vec0` virtual tables, exact brute-force KNN) |
| Full text | SQLite FTS5 (BM25), fused with vectors by reciprocal-rank fusion |
| Schema DDL | Alembic **batch operations only** — the executor behind the admin drift page's `Sync`/`Create`. Not a migration framework: no `versions/`, no version table, no startup upgrade; `db/schema.py` is the source of truth |
| Frontend | React 19 + TypeScript + Vite, **multi-entry** build (4 entries); **TypeScript only — no JavaScript** |
| Components | Mantine 7 (`@mantine/core`, `/form`, `/hooks`, `/tiptap`) |
| State | MobX 6 + `mobx-react-lite`; `react-router-dom` 7 |
| Icons | `@tabler/icons-react` `^3.40` |
| Markdown | TipTap + `tiptap-markdown` (editor), `react-markdown` (render) |
| Streaming | SSE over POST, consumed with `fetch()` + `body.getReader()` |
| Auth | HttpOnly `SameSite=Lax` cookie session |
| Prod runtime | one container: nginx + uvicorn under `supervisord` |

No Tailwind, no CSS modules, no styled-components — two small hand-written
stylesheets and no more: `global.css` for resets, `shell.css` for the `app`
workspace's layout (grid, `--navw` rail, the 820px threshold); everything else
Mantine.

## Repo layout

```
RPHelper/
  CLAUDE.md                 # this file
  backend/
    .venv/                  # backend virtualenv
    app/                    # FastAPI application package (mypy target)
    tests/                  # pytest target
  frontend/
    src/                    # React sources, one folder per Vite entry
    vite.config.ts          # multi-entry + dev proxy
  data/                     # SQLite file; volume-mounted in prod
  docs/
    product/                # requirements — read-only for everyone but /product-spec
    architecture/           # design — owned by /architect
    plans/                  # the work — owned by the planning pipeline
```

## Ports

| Role | Port |
|---|---|
| uvicorn / FastAPI (dev, and loopback in prod) | **8184** |
| Vite dev server | **8193** |
| nginx published by compose | **8193** → container `:80` |

The host-run Vite dev server and the dev-compose nginx publish **the same port**.
Run one or the other, never both. Ports are hardcoded literals in `start.ps1`,
`vite.config.ts`, the Dockerfile and compose — not environment variables. The
frontend never receives a backend base URL; it always calls same-origin
`/api/...`.

## Path rules (non-negotiable)

- Forward slashes only, even on Windows: `D:/GitRoot/_TextGens/RPHelper`, never
  backslashes.
- Uppercase Windows drive letter.
- Wrap full paths in quotes or backticks: `"D:/Folder"`, not bare `D:/Folder`.
- Use **relative** paths when running Python or TypeScript inside the project.
- Use **absolute** paths with `-C` for git commands.
- Python is invoked as `.venv/Scripts/python <args>` from the package root.

## Where to look

- **Requirements** — `docs/product/`. `vision.md`, `actors.md` (ACT-001..004),
  `features.md` (FEAT blocks plus the dependency graph),
  `use-cases/FEAT-*.md`, `stories/FEAT-*.md` (with `US-###.AC-#` criteria).
  **`docs/product/quick-reference.md` is the id registry** — the sole canonical
  list of every id. Verify an id there, never against a range quoted elsewhere.
  Current as of this writing: FEAT-001..020, UC-001..084, US-001..131.
  Requirements are cited by id, never restated elsewhere.
- **Design** — `docs/architecture/`. Start at
  `docs/architecture/quick-reference.md`; it indexes the other eleven docs.
- **The work** — `docs/plans/`. `docs/plans/CLAUDE.md` is the pipeline contract
  every planning and coding agent binds to.

## Conventions every agent must hold

- Backend is fully type-annotated; `mypy app` is a gate, not advice.
- **Frontend and every Node-side file are TypeScript only — no JavaScript.** Every
  authored file under `frontend/` (React, MobX stores, tests, `vite.config.ts`,
  any build script) is `.ts` / `.tsx`. No `.js`, `.jsx`, `.mjs` or `.cjs`; no
  `allowJs` or `checkJs` in any tsconfig. A tool that generates a JS config gets a
  `.ts` equivalent or is not added. Only generated output (`node_modules/`,
  `dist/`, `coverage/`) is exempt. `npm run typecheck` is the gate, and there is
  no linter.
- Requirements live in `docs/product/` and are **cited** (`FEAT-###`, `UC-###`,
  `US-###.AC-#`), never copied into architecture docs or plans.
- Unknowns are marked `_TBD: <reason>_`. Never invent a requirement to close a
  gap.
- `docs/architecture/` is the architect's; `docs/product/` is `/product-spec`'s;
  plans reference both and edit neither.
