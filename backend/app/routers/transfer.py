"""The roleplayer's export and import routes — transport layer only.

Feature `030`, step `003` (`context.md` §Routes; FEAT-018; UC-061; US-079, US-080, US-081) for the
three exports, and feature `031`, step `005` (`context.md` §"Wire contract"; UC-062..UC-064;
US-079.AC-2, US-080.AC-2, US-082.AC-1, US-082.AC-2, US-136.AC-2) for the two imports.
The router owns HTTP and nothing else: no business rule, no SQL, no transaction, no ownership
check. Its only database contact is `app.db.engine.get_connection`; every rule lives in
`app.services.transfer` and `app.services.transfer_import`, neither of which imports `fastapi`.

**Five routes, five full literal paths**, no prefix — `/api/export`,
`/api/characters/{character_id}/export` and `/api/sessions/{session_id}/export` for the exports,
`/api/import` and `/api/characters/{character_id}/import` for the imports. The module is
pre-named in `backend-structure.md` §Layout for FEAT-018, and routers group by **feature**, not
by path prefix (the precedent `routers/stream.py` set by owning `PATCH /api/messages/{id}`), so
the four nested paths live here and not in `routers/characters.py` / `routers/sessions.py`.
They carry one segment more than those routers' item routes, so they cannot collide with them.
The whole-database import is **not** here: like 030's whole-database export it lives in
`routers/admin_db.py`, so it inherits that router's admin guard.

`require_user` is attached to the **router**, so a route added later cannot forget the guard;
each handler also names it as a parameter dependency to receive the `CurrentUser` whose `id`
scopes the export. Without a session cookie the router answers **401** `not_authenticated` with
the standard envelope before the handler runs.

**Path ids are `SnowflakeIn`, never a bare `int`** (`app/models/ids.py`, the JSON id boundary),
so a non-numeric path id is refused with **422** by validation and the service is never reached.

**Every export handler answers a raw `Response`, not a pydantic model, and every import handler
takes a raw `dict[str, Any]` body, not a request model.** Both are the same deliberate, recorded
exception to "routes return/accept pydantic models" (`030/003.context.md`, `031/005.context.md`,
`outcome.md`): the envelope is column-agnostic, so no static model can describe it. The JSON id
boundary still holds — `services/transfer.py`'s row serializer stringifies every id on the way
out, `services/transfer_import.py`'s deserializer parses every id on the way in, and the two
import answers (`app/models/transfer.py`) carry their ids as `SnowflakeOut`. FastAPI turns the
`dict[str, Any]` body into "must be a JSON object", so an array or a scalar body is **422** before
any service runs. Each router builds the attachment response **locally** — this module and
`routers/admin_db.py` share the shape, not an import.

**No error is translated here.** `CharacterNotFoundError` (404 `character_not_found`),
`SessionNotFoundError` (404 `session_not_found`) and `ExportInvalidError` (400 `export_invalid`,
`detail == {"reason": …}`) are raised by the services — a foreign or missing row is scoped at
query level (R5, `domain-rules.md`), and there is no 403 for a foreign row — and are rendered by
the single `DomainError` handler registered in `app.main`.

Registered in `app.main` **after every other router**, so every earlier router's routes keep
matching first.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy import Connection

from app.db.engine import get_connection
from app.dependencies import CurrentUser, require_user
from app.ids import SnowflakeGenerator
from app.models.ids import SnowflakeIn
from app.models.transfer import OwnedImportResponse, SessionImportResponse
from app.routers.bootstrap import get_id_generator
from app.services.transfer import (
    ExportEnvelope,
    encode_envelope,
    export_character,
    export_filename,
    export_session,
    export_user,
)
from app.services.transfer_import import import_owned, import_session

router = APIRouter(
    tags=["transfer"],
    dependencies=[Depends(require_user)],
)


def _attachment(envelope: ExportEnvelope) -> Response:
    """Render one envelope as the JSON-file download every export route answers with.

    Exactly: status **200**, body `encode_envelope(envelope)`, media type
    `application/json`, and `Content-Disposition: attachment;
    filename="<export_filename(envelope)>"`. Nothing else is set and nothing is computed from the
    payload here — the filename comes from the envelope's `granularity` and `created_at` alone,
    so it can carry no row content: no character name, no session title, no id (US-078 opacity).
    """
    return Response(
        content=encode_envelope(envelope),
        status_code=200,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{export_filename(envelope)}"'},
    )


@router.get("/api/export", status_code=200)
def export_own_user(
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> Response:
    """The caller's whole account at `user` granularity via `export_user(connection, current_user.id)`.

    The caller's own id is the only scope: no query parameter can widen it. Answers the
    `_attachment` response for the returned envelope.
    """
    return _attachment(export_user(connection, current_user.id))


@router.get("/api/characters/{character_id}/export", status_code=200)
def export_own_character(
    character_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> Response:
    """One character at `character` granularity via `export_character(connection, current_user.id, character_id)`.

    A foreign or missing character answers 404 `character_not_found` from the service, through the
    one `DomainError` handler. Answers the `_attachment` response for the returned envelope.
    """
    return _attachment(export_character(connection, current_user.id, character_id))


@router.get("/api/sessions/{session_id}/export", status_code=200)
def export_own_session(
    session_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> Response:
    """One session at `session` granularity via `export_session(connection, current_user.id, session_id)`.

    A foreign or missing session answers 404 `session_not_found` from the service, through the one
    `DomainError` handler. Answers the `_attachment` response for the returned envelope.
    """
    return _attachment(export_session(connection, current_user.id, session_id))


@router.post("/api/import", status_code=200)
def import_own_export(
    body: dict[str, Any],
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
) -> OwnedImportResponse:
    """A `user` or `character` export back into the caller's own account, 200 with the new ids.

    `import_owned(connection, generator, current_user.id, body)` and nothing else; the returned
    `OwnedImportResult`'s two fields map one-for-one onto `OwnedImportResponse`, whose
    `character_ids` serialize as decimal strings. The caller's own id is the only account the
    import can write to: no body field and no query parameter can widen it (R5, US-136.AC-1).

    `body` is the untrusted request object, taken raw because the envelope is column-agnostic. A
    body that is not a JSON object answers **422** before this handler runs; a body that is an
    object but not an export answers **400** `export_invalid` from the service.

    A `session` or `database` envelope answers 400 `export_invalid` with `detail`
    `{"reason": "wrong_granularity"}` — the service's accepted set decides that, not this router.
    """
    result = import_owned(connection, generator, current_user.id, body)
    return OwnedImportResponse(granularity=result.granularity, character_ids=result.character_ids)


@router.post("/api/characters/{character_id}/import", status_code=200)
def import_own_session(
    character_id: SnowflakeIn,
    body: dict[str, Any],
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
) -> SessionImportResponse:
    """A `session` export under the caller's character `character_id`, 200 with the new session id.

    `import_session(connection, generator, current_user.id, character_id, body)` and nothing else;
    the `int` it returns becomes `SessionImportResponse.session_id`, a decimal string.

    A foreign or missing target character answers 404 `character_not_found` from the service, with
    no 403 and no hint about whether the id exists (R5); an **archived** character is a legal
    target (R6). A non-numeric `character_id` answers **422** from `SnowflakeIn`, before the
    service is reached. A `user`, `character` or `database` envelope answers 400 `export_invalid`
    with `detail` `{"reason": "wrong_granularity"}`.
    """
    session_id = import_session(connection, generator, current_user.id, character_id, body)
    return SessionImportResponse(session_id=session_id)
