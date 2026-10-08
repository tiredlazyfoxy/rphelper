"""`/api/memos...` and `/api/sessions/{session_id}/memo-chain` — transport layer only.

Feature `015`, step `004`. The router owns HTTP and nothing else: no business rule, no
SQL, no transaction. Its only database contact is `app.db.engine.get_connection`; every
rule lives in `app.services.memos` and `app.services.memo_chain`.

**One router, full literal paths** (`context.md` D9). `require_user` is attached to the
**router**, so a route added later cannot forget the guard; each handler also names it as a
parameter dependency to receive the `CurrentUser` whose `id` scopes the service call.

Five routes (`context.md` Wire contract): `GET` / `POST /api/memos`,
`PATCH` / `DELETE /api/memos/{memo_id}`, and `GET /api/sessions/{session_id}/memo-chain`.
Create answers **201**, delete **204** with an empty body, the rest **200**. The chain
route lives here although its path starts `/api/sessions/`: routers group by feature. The
router is registered in `app.main` **after every other router**.

The router translates no error by hand: `MemoNotFoundError`, `CharacterNotFoundError`,
`SetupNotFoundError` and `SessionNotFoundError` propagate to the one `DomainError` handler
registered in `app.main`. Feature `024` adds two more that travel the same way, from the
create and the body-changing patch: `no_embedding_model` (409) and `llm_unreachable` (502).

**Feature `024`, step `004` — the two embedding dependencies** (`024 D9`). Create and patch
also depend on `app.dependencies.get_llm_client_factory` (the shared factory, overridden in
tests) and on `get_settings`, and hand the service the factory plus
`settings.llm_request_timeout_seconds` as keyword arguments. The service imports no
`fastapi`, so this wiring is the only way those two values reach it. `GET`, `DELETE` and the
reorder route need neither: none of them can require an embedding model.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.exceptions import RequestValidationError
from sqlalchemy import Connection

from app.config import Settings, get_settings
from app.db.engine import get_connection
from app.dependencies import CurrentUser, get_llm_client_factory, require_user
from app.ids import SnowflakeGenerator
from app.models.ids import SnowflakeIn
from app.models.memos import (
    CreateMemoRequest,
    MemoChainLevelResponse,
    MemoChainResponse,
    MemoListResponse,
    MemoResponse,
    MemoScope,
    ReorderMemosRequest,
    UpdateMemoRequest,
)
from app.routers.bootstrap import get_id_generator
from app.services.llm_registry import LlmClientFactory
from app.services.memo_chain import MemoChainLevel, resolve_chain
from app.services.memos import Memo, create_memo, delete_memo, list_memos, reorder_memos, update_memo

router = APIRouter(
    tags=["memos"],
    dependencies=[Depends(require_user)],
)


def _to_response(memo: Memo) -> MemoResponse:
    """Render one service `Memo` as the wire shape (nine keys, no `user_id`)."""
    return MemoResponse.model_validate(memo, from_attributes=True)


def _to_level_response(level: MemoChainLevel) -> MemoChainLevelResponse:
    """Render one `MemoChainLevel` as the wire shape, its memos in the order given."""
    return MemoChainLevelResponse(
        scope=level.scope,
        scope_id=level.scope_id,
        memos=[_to_response(memo) for memo in level.memos],
    )


@router.get("/api/memos", status_code=200)
def list_own_memos(
    scope: MemoScope,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    scope_id: SnowflakeIn | None = None,
) -> MemoListResponse:
    """One level's notes via `list_memos(...)`.

    A non-user `scope` without `scope_id` answers 422; for `"user"` a supplied `scope_id`
    is dropped before the service call.
    """
    if scope == "user":
        scope_id = None
    elif scope_id is None:
        # The pairing rule spans two parameters, so FastAPI cannot express it per
        # parameter; answer the same 422 shape it would, with no domain code.
        raise RequestValidationError(
            [
                {
                    "type": "missing",
                    "loc": ("query", "scope_id"),
                    "msg": f"scope_id is required for scope {scope!r}",
                    "input": None,
                }
            ]
        )
    memos = list_memos(connection, current_user.id, scope, scope_id)
    return MemoListResponse(memos=[_to_response(memo) for memo in memos])


@router.post("/api/memos", status_code=201)
def create_own_memo(
    body: CreateMemoRequest,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
    settings: Annotated[Settings, Depends(get_settings)],
    client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)],
) -> MemoResponse:
    """Create one note via `create_memo(...)` (`scope_id` passed as `None` for `"user"`); 201.

    The factory and the one outbound timeout go in by keyword (024 D9). A create embeds
    strictly, so an unusable designation or a failed embed answers 409 / 502 through the
    global handler and stores nothing.
    """
    scope_id = None if body.scope == "user" else body.scope_id
    memo = create_memo(
        connection,
        generator,
        current_user.id,
        body.scope,
        scope_id,
        body.body,
        client_factory=client_factory,
        timeout_seconds=settings.llm_request_timeout_seconds,
    )
    return _to_response(memo)


@router.put("/api/memos/order", status_code=200)
def reorder_own_memos(
    body: ReorderMemosRequest,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> MemoListResponse:
    """Rewrite one level's order via `reorder_memos(...)` (`scope_id` `None` for `"user"`); 200.

    Declared before the `/api/memos/{memo_id}` handlers (016 D6).
    """
    scope_id = None if body.scope == "user" else body.scope_id
    memos = reorder_memos(connection, current_user.id, body.scope, scope_id, body.memo_ids)
    return MemoListResponse(memos=[_to_response(memo) for memo in memos])


@router.patch("/api/memos/{memo_id}", status_code=200)
def update_own_memo(
    memo_id: SnowflakeIn,
    body: UpdateMemoRequest,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
    client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)],
) -> MemoResponse:
    """Forward to `update_memo(...)` only the fields that were set and are not null.

    The factory and the timeout are passed on every patch (024 D9); whether they are used is
    the service's decision, and a flag-only patch never touches them. Which fields were sent
    stays this handler's business, exactly as before.
    """
    supplied = body.model_fields_set
    memo = update_memo(
        connection,
        current_user.id,
        memo_id,
        body=body.body if "body" in supplied and body.body is not None else None,
        is_enabled=body.is_enabled if "is_enabled" in supplied and body.is_enabled is not None else None,
        is_forced=body.is_forced if "is_forced" in supplied and body.is_forced is not None else None,
        client_factory=client_factory,
        timeout_seconds=settings.llm_request_timeout_seconds,
    )
    return _to_response(memo)


@router.delete("/api/memos/{memo_id}", status_code=204)
def delete_own_memo(
    memo_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> Response:
    """Delete the note via `delete_memo(...)`; answers 204 with an empty body (D2)."""
    delete_memo(connection, current_user.id, memo_id)
    return Response(status_code=204)


@router.get("/api/sessions/{session_id}/memo-chain", status_code=200)
def read_own_memo_chain(
    session_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> MemoChainResponse:
    """The session's memo chain via `resolve_chain(...)`, levels in the order returned."""
    levels = resolve_chain(connection, current_user.id, session_id)
    return MemoChainResponse(levels=[_to_level_response(level) for level in levels])
