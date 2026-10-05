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
   `/api/admin/users` prefix and its router-level `require_role(Role.ADMIN)` guard, then
   `app.include_router(admin_llm_router)` (feature `006`, `/api/admin/llm-servers`), then
   `app.include_router(admin_db_router)` (feature `007`, `/api/admin/database`) — each with
   the same router-level admin guard — then `app.include_router(characters_router)`
   (feature `009`, `/api/characters`), and finally `app.include_router(setups_router)`
   (feature `010`), which carries no prefix of its own and declares the full paths
   `/api/characters/{character_id}/setups` and `/api/setups/{setup_id}...`. It is
   registered **after** the characters router on purpose: Starlette matches routes in
   registration order, so 009's routes keep matching first. Last comes
   `app.include_router(sessions_router)` (feature `011`), which likewise carries no prefix
   and declares the full paths `/api/sessions...` and
   `/api/characters/{character_id}/sessions`, registered **after** the setups router for
   the same reason: 009's and 010's routes keep matching first. Last of all comes
   `app.include_router(stream_router)` (feature `012`), no prefix, full paths
   `/api/sessions/{session_id}/entries|zone|zone/messages|settle|reopen` and
   `/api/messages/{message_id}`, registered **after** the sessions router so 011's routes
   keep matching first. Last of everything comes `app.include_router(memos_router)`
   (feature `015`), no prefix, full paths `/api/memos`, `/api/memos/{memo_id}` and
   `/api/sessions/{session_id}/memo-chain`, registered **after** the stream router so
   every earlier router's routes keep matching first. After it, last, comes
   `app.include_router(configuration_router)` (feature `017`), no prefix, full paths
   `/api/models`, `/api/me/settings`, `/api/sessions/{session_id}/configuration` and
   `/api/characters/{character_id}/configuration`, registered after every earlier router.
   After it comes `app.include_router(translation_router)` (feature `023`), no prefix, the
   single full path `/api/messages/{message_id}/translation`, registered after every
   earlier router. After it comes `app.include_router(search_router)`
   (feature `029`), no prefix, the single full path `/api/search`, registered after every
   earlier router so every earlier router's routes keep matching first. After it, last of all,
   comes `app.include_router(transfer_router)` (feature `030`), no prefix, the full paths
   `/api/export`, `/api/characters/{character_id}/export` and
   `/api/sessions/{session_id}/export`, registered **after every other router** for the same
   reason: 009's `/api/characters/{character_id}` and 011's `/api/sessions/{session_id}` keep
   matching first.

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
from app.routers.admin_db import router as admin_db_router
from app.routers.admin_llm import router as admin_llm_router
from app.routers.admin_users import router as admin_users_router
from app.routers.auth import router as auth_router
from app.routers.bootstrap import router as bootstrap_router
from app.routers.characters import router as characters_router
from app.routers.configuration import router as configuration_router
from app.routers.health import router as health_router
from app.routers.memos import router as memos_router
from app.routers.search import router as search_router
from app.routers.sessions import router as sessions_router
from app.routers.setups import router as setups_router
from app.routers.stream import router as stream_router
from app.routers.transfer import router as transfer_router
from app.routers.translation import router as translation_router


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
    `app.include_router(auth_router)`, `app.include_router(admin_users_router)`,
    `app.include_router(admin_llm_router)`, `app.include_router(admin_db_router)`,
    `app.include_router(characters_router)`, `app.include_router(setups_router)`,
    `app.include_router(sessions_router)`, `app.include_router(stream_router)`,
    `app.include_router(memos_router)`, `app.include_router(configuration_router)`,
    `app.include_router(translation_router)`, `app.include_router(search_router)` and
    `app.include_router(transfer_router)` — the
    setups router immediately after the characters router, the sessions router immediately
    after setups, the stream router immediately after sessions, the memos router immediately
    after stream, the configuration router after those (feature `017`), the translation
    router after that (feature `023`), the search router after that (feature `029`), and the
    transfer router last (feature `030`).

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
    app.include_router(admin_llm_router)
    app.include_router(admin_db_router)
    app.include_router(characters_router)
    app.include_router(setups_router)
    app.include_router(sessions_router)
    app.include_router(stream_router)
    app.include_router(memos_router)
    app.include_router(configuration_router)
    app.include_router(translation_router)
    app.include_router(search_router)
    app.include_router(transfer_router)
    return app


#: The uvicorn target — `uvicorn app.main:app`, built by the factory.
app = create_app()
