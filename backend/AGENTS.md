# backend

<!-- agent-ready:start -->

The Python / FastAPI backend: the API the frontend calls same-origin under `/api/...`, backed by one SQLite file holding relational rows, FTS5 and vectors. Commands (test, typecheck, lint) are in the root `AGENTS.md`.

## Glossary

**Subfolders:**
- `app/` — the FastAPI application package (routers, services, models, db, infrastructure); the mypy target.
- `data/` — local runtime data, not code: the dev SQLite database and logs.
- `tests/` — the pytest suite, shared fixtures and fakes.

**Files:**
- `.gitignore` — keeps the venvs, tool caches and `.env` out of git.
- `pyproject.toml` — project metadata, dependencies and the pytest / mypy / ruff configuration.
- `uv.lock` — the `uv` lockfile.

See also: docs/architecture/backend-structure.md

<!-- agent-ready:end -->
