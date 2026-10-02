"""`/api/characters` — the roleplayer's characters, transport layer only.

Feature `009`, step `003` (FEAT-006, UC-017/018/019/067). The router owns HTTP and
nothing else: no business rule, no SQL, no transaction. Its only database contact is
`app.db.engine.get_connection`; every rule lives in `app.services.characters`.

**`require_user` is attached to the router, never only to a handler**
(`backend-structure.md`, "Authorization as router dependencies"; `context.md` D6), so a
route added later cannot forget the guard. Any authenticated, enabled account owns
characters — an administrator included, scoped by its own id. Each handler *also* names
`require_user` as a parameter dependency to receive the `CurrentUser` whose `id` scopes
the service call; FastAPI's per-request dependency cache resolves the guard once, so that
is the router's guard handing over its value, not a second authorization check.

Six routes (`context.md` D7, Wire contract): `GET ""` and `POST ""` on the collection, and
`GET`, `PATCH` on `/{character_id}` plus `POST /{character_id}/archive|restore`. Create
answers **201**, the rest **200**. `{character_id}` is declared with the inbound snowflake
alias, so a non-numeric path id fails validation and answers 422.

**No `DELETE` route exists** (`context.md` R6, US-086.AC-3). Nothing here destroys a
character; Starlette answers 405 for `DELETE` on either matching path, with no code of
ours.

The router translates no error by hand: `CharacterNotFoundError` propagates to the one
`DomainError` handler registered in `app.main`, which renders the 404 and the
`character_not_found` code. A blank or whitespace-only `name` is FastAPI's native 422,
produced by the request models and never by a check here.

Timestamps are the stored fixed-width UTC text in both the service's `Character` and
`CharacterResponse`, so the conversion hands them straight through: nothing here parses
or re-formats a timestamp, and `user_id` never reaches the wire.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Connection

from app.db.engine import get_connection
from app.dependencies import CurrentUser, require_user
from app.ids import SnowflakeGenerator
from app.models.characters import (
    CharacterListResponse,
    CharacterResponse,
    CreateCharacterRequest,
    UpdateCharacterRequest,
)
from app.models.ids import SnowflakeIn
from app.routers.bootstrap import get_id_generator
from app.services.characters import (
    Character,
    archive_character,
    create_character,
    get_character,
    list_characters,
    restore_character,
    update_character,
)

router = APIRouter(
    prefix="/api/characters",
    tags=["characters"],
    dependencies=[Depends(require_user)],
)


def _to_response(character: Character) -> CharacterResponse:
    """Render one service `Character` as the wire shape, timestamps passed through as text."""
    # `Character` is a frozen dataclass with exactly the wire's six fields, so this is a
    # field-for-field read: `from_attributes` takes them off the object, `SnowflakeOut`
    # renders `id` as a decimal string, and the three timestamps are already the stored
    # fixed-width UTC text — nothing is parsed or re-formatted here.
    return CharacterResponse.model_validate(character, from_attributes=True)


@router.get("", status_code=200)
def list_own_characters(
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    include_archived: bool = False,
) -> CharacterListResponse:
    """The caller's characters via `list_characters(connection, user_id, include_archived)`.

    Working list only unless the `include_archived` query parameter is true.
    """
    owned = list_characters(connection, current_user.id, include_archived)
    return CharacterListResponse(characters=[_to_response(character) for character in owned])


@router.post("", status_code=201)
def create_own_character(
    body: CreateCharacterRequest,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
) -> CharacterResponse:
    """Create one character owned by the caller via `create_character(...)`; answers 201."""
    character = create_character(connection, generator, current_user.id, body.name, body.sheet)
    return _to_response(character)


@router.get("/{character_id}", status_code=200)
def read_own_character(
    character_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> CharacterResponse:
    """One of the caller's characters, archived or not, via `get_character(...)`."""
    character = get_character(connection, current_user.id, character_id)
    return _to_response(character)


@router.patch("/{character_id}", status_code=200)
def update_own_character(
    character_id: SnowflakeIn,
    body: UpdateCharacterRequest,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> CharacterResponse:
    """Write the supplied fields via `update_character(...)`; `None` means not supplied."""
    # An unsupplied field and an explicit `null` are both `None` on the model, which is
    # exactly the service's "not supplied" (D7): a PATCH supplying neither writes nothing
    # and answers the unchanged character.
    character = update_character(connection, current_user.id, character_id, body.name, body.sheet)
    return _to_response(character)


@router.post("/{character_id}/archive", status_code=200)
def archive_own_character(
    character_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> CharacterResponse:
    """Take the character out of the working list via `archive_character(...)`; idempotent."""
    character = archive_character(connection, current_user.id, character_id)
    return _to_response(character)


@router.post("/{character_id}/restore", status_code=200)
def restore_own_character(
    character_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> CharacterResponse:
    """Put the character back into the working list via `restore_character(...)`; idempotent."""
    character = restore_character(connection, current_user.id, character_id)
    return _to_response(character)
