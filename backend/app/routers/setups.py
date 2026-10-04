"""`/api/characters/{character_id}/setups` and `/api/setups/...` — transport layer only.

Feature `010`, step `003` (FEAT-007, UC-020/068). The router owns HTTP and nothing else:
no business rule, no SQL, no transaction. Its only database contact is
`app.db.engine.get_connection`; every rule lives in `app.services.setups`.

**One router, two path families** (`context.md` D5, `003.context.md`). The two families
share no prefix longer than `/api`, so the router is declared with **no prefix** and each
handler carries its own full path. `require_user` is attached to the **router**, never only
to a handler (`backend-structure.md`, "Authorization as router dependencies"; 009 D6), so a
route added later cannot forget the guard. Each handler *also* names `require_user` as a
parameter dependency to receive the `CurrentUser` whose `id` scopes the service call;
FastAPI's per-request dependency cache resolves the guard once, so that is the router's
guard handing over its value, not a second authorization check.

Six routes (`context.md` Wire contract): `GET` and `POST` on
`/api/characters/{character_id}/setups`, and `GET`, `PATCH` on `/api/setups/{setup_id}`
plus `POST /api/setups/{setup_id}/archive|restore`. Create answers **201**, the rest
**200**. Both path ids are declared with the inbound snowflake alias, so a non-numeric path
id fails validation and answers 422. The router is registered in `app.main` **after** the
characters router, and no path of 009's is shadowed: `/api/characters/{character_id}`'s two
segments and its literal `archive` / `restore` third segments never collide with the
literal `setups` third segment here.

**No `DELETE` route exists** (`context.md` R6, UC-068). Nothing here destroys a setup;
Starlette answers 405 for `DELETE` on either matching path, with no code of ours.

The router translates no error by hand: `SetupNotFoundError` (a setup that is nobody's or
another user's) and `CharacterNotFoundError` (the same for the parent character on list and
create) propagate to the one `DomainError` handler registered in `app.main`, which renders
the 404 and the `setup_not_found` / `character_not_found` code with an empty `detail`
(D8). A blank or whitespace-only `name` is FastAPI's native 422, produced by the request
models and never by a check here. Listing and creating under an **archived** character are
allowed (D5), and nothing here inspects the parent's `archived_at`.

Timestamps are the stored fixed-width UTC text in both the service's `Setup` and
`SetupResponse`, so the conversion hands them straight through: nothing here parses or
re-formats a timestamp, and `user_id` never reaches the wire.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Connection

from app.config import Settings, get_settings
from app.db.engine import get_connection
from app.dependencies import CurrentUser, get_llm_client_factory, require_user
from app.ids import SnowflakeGenerator
from app.models.ids import SnowflakeIn
from app.models.setups import (
    CreateSetupRequest,
    SetupListResponse,
    SetupResponse,
    UpdateSetupRequest,
)
from app.routers.bootstrap import get_id_generator
from app.services.llm_registry import LlmClientFactory
from app.services.setups import (
    Setup,
    archive_setup,
    create_setup,
    get_setup,
    list_setups,
    restore_setup,
    update_setup,
)

router = APIRouter(
    tags=["setups"],
    dependencies=[Depends(require_user)],
)


def _to_response(setup: Setup) -> SetupResponse:
    """Render one service `Setup` as the wire shape, timestamps passed through as text."""
    # `Setup` is a frozen dataclass with exactly the wire's seven fields, so this is a
    # field-for-field read: `from_attributes` takes them off the object, `SnowflakeOut`
    # renders `id` and `character_id` as decimal strings, and the timestamps are already
    # the stored fixed-width UTC text — nothing is parsed or re-formatted here.
    return SetupResponse.model_validate(setup, from_attributes=True)


@router.get("/api/characters/{character_id}/setups", status_code=200)
def list_own_setups(
    character_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    include_archived: bool = False,
) -> SetupListResponse:
    """The character's setups via `list_setups(connection, user_id, character_id, include_archived)`.

    Working list only unless the `include_archived` query parameter is true. The character
    must be the caller's, archived or not; otherwise `CharacterNotFoundError` propagates.
    """
    owned = list_setups(connection, current_user.id, character_id, include_archived)
    return SetupListResponse(setups=[_to_response(setup) for setup in owned])


@router.post("/api/characters/{character_id}/setups", status_code=201)
def create_own_setup(
    character_id: SnowflakeIn,
    body: CreateSetupRequest,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
) -> SetupResponse:
    """Create one setup under the caller's character via `create_setup(...)`; answers 201."""
    setup = create_setup(connection, generator, current_user.id, character_id, body.name, body.description)
    return _to_response(setup)


@router.get("/api/setups/{setup_id}", status_code=200)
def read_own_setup(
    setup_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> SetupResponse:
    """One of the caller's setups, archived or not, via `get_setup(...)`."""
    setup = get_setup(connection, current_user.id, setup_id)
    return _to_response(setup)


@router.patch("/api/setups/{setup_id}", status_code=200)
def update_own_setup(
    setup_id: SnowflakeIn,
    body: UpdateSetupRequest,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
    client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)],
) -> SetupResponse:
    """Write the supplied fields via `update_setup(...)`; `None` means not supplied.

    The shared client factory and the one outbound timeout go in by keyword (024 D9),
    because a changed `description` re-indexes every session on this setup strictly: an
    unusable designation or a failed embed answers 409 `no_embedding_model` / 502
    `llm_unreachable` through the global `DomainError` handler and stores nothing. Neither
    dependency shows on the wire, and no other route of this router needs them.
    """
    # An unsupplied field and an explicit `null` are both `None` on the model, which is
    # exactly the service's "not supplied" (D5, 009 D7): a PATCH supplying neither writes
    # nothing and answers the unchanged setup. `character_id` is not a field of the model,
    # so a body carrying it is ignored and the setup never moves.
    setup = update_setup(
        connection,
        current_user.id,
        setup_id,
        body.name,
        body.description,
        client_factory=client_factory,
        timeout_seconds=settings.llm_request_timeout_seconds,
    )
    return _to_response(setup)


@router.post("/api/setups/{setup_id}/archive", status_code=200)
def archive_own_setup(
    setup_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> SetupResponse:
    """Take the setup out of the working list via `archive_setup(...)`; idempotent (D9)."""
    setup = archive_setup(connection, current_user.id, setup_id)
    return _to_response(setup)


@router.post("/api/setups/{setup_id}/restore", status_code=200)
def restore_own_setup(
    setup_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> SetupResponse:
    """Put the setup back into the working list via `restore_setup(...)`; idempotent (D9)."""
    setup = restore_setup(connection, current_user.id, setup_id)
    return _to_response(setup)
