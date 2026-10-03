"""`/api/sessions...` and `/api/characters/{character_id}/sessions` — transport layer only.

Feature `011`, step `003` (FEAT-008 via UC-023/024/025/026, FEAT-007 via UC-021/022,
FEAT-020 via UC-069). "Session" here is always the **RP session** (one `sessions` row),
never the login session. The router owns HTTP and nothing else: no business rule, no SQL,
no transaction, no `app.db.schema` import. Its only database contact is
`app.db.engine.get_connection`; every rule lives in `app.services.sessions`.

**One router, two path families** (`context.md` D9, `003.context.md`). The families share
no prefix longer than `/api`, so the router is declared with **no prefix** and each handler
carries its own full path. `require_user` is attached to the **router**, never only to a
handler (`backend-structure.md`, "Authorization as router dependencies"; 009 D6), so a
route added later cannot forget the guard. Each handler *also* names `require_user` as a
parameter dependency to receive the `CurrentUser` whose `id` scopes the service call;
FastAPI's per-request dependency cache resolves the guard once, so that is the router's
guard handing over its value, not a second authorization check.

Six routes (`context.md` Wire contract): `GET /api/sessions`, `GET` and
`POST /api/characters/{character_id}/sessions`, `GET /api/sessions/{session_id}` and
`POST /api/sessions/{session_id}/archive|restore`. Start answers **201**, the rest **200**.
Both path ids are declared with the inbound snowflake alias, so a non-numeric path id fails
validation and answers 422. The router is registered in `app.main` **after** the setups
router, and no path of 009's or 010's is shadowed: the literal third segment `sessions`
never collides with `setups`, `archive` or `restore` under `/api/characters/{id}`.

**The start body is optional** (`context.md` D2, `003.context.md` "The optional body"). The
body parameter is annotated `StartSessionRequest | None` with the default `None`, so no body
at all, `{}` and `{"setup_id": null}` all reach the handler and all mean "no setup" (R2 — no
default, no sentinel); `{"setup_id": "abc"}` is refused by the model's validator as a 422
before the handler runs. Because the parameter carries a default it is declared **last**,
after the dependencies, the same way `include_archived` is on the two list routes. `018`
later adds an optional opening-message field to this same model and route.

**No `PATCH` and no `DELETE` handler exists here** (`context.md` R6, D9). Nothing in this
router edits a session and nothing deletes one; Starlette answers 405 for either method on
any matching path, with no code of ours. Since `017`, a session's configuration is edited
through `routers/configuration.py`'s `PATCH /api/sessions/{id}/configuration`;
`PATCH /api/sessions/{id}` itself still does not exist.

The router translates no error by hand: `SessionNotFoundError`, `CharacterNotFoundError`,
`SetupNotFoundError` and `SetupArchivedError` propagate to the one `DomainError` handler
registered in `app.main`, which renders 404 `session_not_found` / `character_not_found`,
404 `setup_not_found` and 409 `setup_archived` with an empty `detail` (D12). The router
catches nothing.

Timestamps are the stored fixed-width UTC text in both the service's `RpSession` and
`SessionResponse`, so the conversion hands them straight through: nothing here parses or
re-formats a timestamp, and `user_id` never reaches the wire (R5).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Connection

from app.db.engine import get_connection
from app.dependencies import CurrentUser, require_user
from app.ids import SnowflakeGenerator
from app.models.ids import SnowflakeIn
from app.models.sessions import (
    SessionListResponse,
    SessionResponse,
    StartSessionRequest,
)
from app.routers.bootstrap import get_id_generator
from app.services.sessions import (
    RpSession,
    archive_session,
    get_session,
    list_character_sessions,
    list_sessions,
    restore_session,
    start_session,
)

router = APIRouter(
    tags=["sessions"],
    dependencies=[Depends(require_user)],
)


def _to_response(session: RpSession) -> SessionResponse:
    """Render one service `RpSession` as the wire shape, timestamps passed through as text."""
    # `RpSession` is a frozen dataclass carrying exactly the wire's eight fields and no
    # `user_id`, so this is a field-for-field read: `from_attributes` takes them off the
    # object, `SnowflakeOut` renders `id`, `character_id` and `setup_id` as decimal strings
    # (a `None` `setup_id` staying JSON `null`), and `archived_at`, `last_used_at`,
    # `created_at` and `updated_at` are already the stored fixed-width UTC text — nothing
    # here parses, re-formats or recomputes a timestamp.
    return SessionResponse.model_validate(session, from_attributes=True)


@router.get("/api/sessions", status_code=200)
def list_own_sessions(
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    include_archived: bool = False,
) -> SessionListResponse:
    """The caller's sessions across all characters via `list_sessions(connection, user_id, include_archived)`.

    Working list only unless the `include_archived` query parameter is true. Order is the
    service's (D14). Feeds the tree.
    """
    owned = list_sessions(connection, current_user.id, include_archived)
    return SessionListResponse(sessions=[_to_response(session) for session in owned])


@router.get("/api/characters/{character_id}/sessions", status_code=200)
def list_own_character_sessions(
    character_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    include_archived: bool = False,
) -> SessionListResponse:
    """That character's sessions via `list_character_sessions(connection, user_id, character_id, include_archived)`.

    Working list only unless the `include_archived` query parameter is true. The character
    must be the caller's, archived or not; otherwise `CharacterNotFoundError` propagates.
    """
    owned = list_character_sessions(connection, current_user.id, character_id, include_archived)
    return SessionListResponse(sessions=[_to_response(session) for session in owned])


@router.post("/api/characters/{character_id}/sessions", status_code=201)
def start_own_session(
    character_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
    body: StartSessionRequest | None = None,
) -> SessionResponse:
    """Start one session under the caller's character via `start_session(...)`; answers 201.

    A `None` body (no body at all) and a body whose `setup_id` is absent or `null` are the
    same request: `setup_id` `None`, a session with no setup. An archived character of the
    caller's is allowed (D2).
    """
    # No body at all leaves `body` `None`; `{}` and `{"setup_id": null}` both leave
    # `body.setup_id` `None` (the model's validator resolves absent and `null` alike). All
    # three are therefore the same call: `setup_id` `None`, a session with no setup — no
    # default and no sentinel is substituted here or anywhere below (R2, D2).
    setup_id = None if body is None else body.setup_id
    session = start_session(connection, generator, current_user.id, character_id, setup_id)
    return _to_response(session)


@router.get("/api/sessions/{session_id}", status_code=200)
def read_own_session(
    session_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> SessionResponse:
    """One of the caller's sessions, archived or not, via `get_session(...)`. Reads only (D3)."""
    session = get_session(connection, current_user.id, session_id)
    return _to_response(session)


@router.post("/api/sessions/{session_id}/archive", status_code=200)
def archive_own_session(
    session_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> SessionResponse:
    """Take the session out of the working lists via `archive_session(...)`; idempotent (D13)."""
    session = archive_session(connection, current_user.id, session_id)
    return _to_response(session)


@router.post("/api/sessions/{session_id}/restore", status_code=200)
def restore_own_session(
    session_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> SessionResponse:
    """Put the session back into the working lists via `restore_session(...)`; idempotent (D13)."""
    session = restore_session(connection, current_user.id, session_id)
    return _to_response(session)
