"""The application factory, the lifespan, and the uvicorn target.

`backend-structure.md` § "The logging call site — once, in the app factory":
`configure_logging(settings)` is called **exactly once, from `main.py`'s app factory,
before any router is registered** — early enough that a failure during registration is
already captured by both sinks. No other module in the backend adds, removes or
reconfigures a sink.

The factory's order is therefore fixed:

1. resolve settings (`get_settings()`);
2. `configure_logging(settings)` — once, **before any router is registered**;
3. `build_id_generator(settings)` once, and hold that **single instance** on
   `app.state.id_generator`. That is the code-level half of `data-model.md`'s "exactly
   one generator process per node id" guarantee: one generator per process, never one
   per request and never a module-level singleton;
4. `register_exception_handlers(app)` — step `003`'s entry point, which installs the one
   handler for `DomainError` so every subclass is covered by one registration;
5. `app.include_router(health_router)` — the health router already carries its own
   `/api` prefix — then `app.include_router(bootstrap_router)`, which carries its own
   `/api/bootstrap` prefix and its router-level `require_unconfigured` guard, then
   `app.include_router(auth_router)` (feature `004`), which carries its own `/api` prefix
   and declares `POST /api/auth/login`, `POST /api/auth/logout` and `GET /api/me`, then
   `app.include_router(admin_users_router)` (feature `005`), which carries its own
   `/api/admin/users` prefix and its router-level `require_role(Role.ADMIN)` guard.

**The lifespan runs no DDL.** No table creation, no upgrade, no schema check, and no
create-if-missing convenience. Remediation is admin-triggered and belongs to feature
`007`; DoD-11 asserts `sqlite_master` holds no application table after startup. It also
opens no database and touches no engine — importing this module must not either.

`configure_logging`, `build_id_generator` and `register_exception_handlers` are imported
as **names into this module's namespace** on purpose: `app.main.configure_logging` is
the seam DoD-8 patches to count calls. Do not switch these to module-qualified calls.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

# These five names are the factory's frozen collaborators. They are imported as names
# into this module's namespace so that `app.main.configure_logging`,
# `app.main.build_id_generator` and `app.main.register_exception_handlers` are the
# patchable seams (DoD-8/9/10). The factory calls them through these names; do not
# switch to module-qualified calls.
from app.config import get_settings
from app.errors import register_exception_handlers
from app.ids import build_id_generator
from app.logging import configure_logging
from app.routers.admin_users import router as admin_users_router
from app.routers.auth import router as auth_router
from app.routers.bootstrap import router as bootstrap_router
from app.routers.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown for the application. Runs **no DDL** and opens no database.

    There is nothing for it to do in this feature, and that emptiness is the contract,
    not an omission: schema creation and repair are admin-triggered actions belonging to
    feature `007`.
    """
    yield


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application.

    Performs, in this order: resolve settings; `configure_logging(settings)` exactly
    once and before any router is registered; construct the process's
    `SnowflakeGenerator` via `build_id_generator(settings)` and store that single
    instance on `app.state.id_generator`; `register_exception_handlers(app)`; then
    `app.include_router(health_router)`, `app.include_router(bootstrap_router)`,
    `app.include_router(auth_router)` and `app.include_router(admin_users_router)`.

    Constructed with `FastAPI(lifespan=lifespan)`.

    Typing note, carried from step `003`'s freeze and re-verified here:
    `app.add_exception_handler(DomainError, handler)` fails mypy with `arg-type` under
    the pinned FastAPI (Starlette's parameter is invariant on `Exception`); the
    decorator form `app.exception_handler(DomainError)(handler)` typechecks clean. That
    choice lives inside `register_exception_handlers`, not here.
    """
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(lifespan=lifespan)
    app.state.id_generator = build_id_generator(settings)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(bootstrap_router)
    app.include_router(auth_router)
    app.include_router(admin_users_router)
    return app


#: The uvicorn target — `uvicorn app.main:app`, built by the factory.
app = create_app()
