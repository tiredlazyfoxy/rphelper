# app

<!-- agent-ready:start -->

The FastAPI application package (the `mypy app` target): the app factory plus the routers → services → db layers and the infrastructure modules they share.

## Glossary

**Subfolders:**
- `db/` — SQLAlchemy Core access: the SQLite engine, the schema registry (source of truth), FTS5 / `vec0` virtual tables, drift diagnosis and remediation.
- `models/` — Pydantic request / response wire models; the only layer that converts ids between `int` and string.
- `routers/` — the HTTP transport layer: `/api/...` routes onto services, with auth / role guards.
- `services/` — the domain layer: business rules, ownership checks, transactions, LLM, search and tools.

**Files:**
- `__init__.py` — package marker.
- `config.py` — application configuration (`pydantic-settings` `Settings` and its cached accessor).
- `dependencies.py` — the HTTP authentication seam: who is calling, and the session cookie.
- `errors.py` — the typed domain-error hierarchy, its wire shape and its one handler.
- `ids.py` — the snowflake id generator.
- `logging.py` — logging configuration: loguru's two sinks plus the stdlib bridge.
- `main.py` — the application factory, the lifespan and the uvicorn target.
- `roles.py` — the role vocabulary for the `users.role` column.
- `secrets.py` — resolution of the `"$ENV_VAR"` pointer stored in place of a credential.

See also: docs/architecture/backend-structure.md

<!-- agent-ready:end -->
