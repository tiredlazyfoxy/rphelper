"""`/api/sessions/{session_id}/entries|zone|settle|reopen` and `/api/messages/{message_id}`.

Feature `012`, step `004` — the stream router, transport layer only. Seven JSON routes
(`context.md` Wire contract), each calling exactly one operation of `app.services.messages`
or `app.services.settle` and converting its value into the `app.models.stream` models.
`require_user` is attached to the **router** (D12); each handler also names it as a
parameter to receive the `CurrentUser` whose `id` scopes the service call. The router
declares no prefix and carries full paths. Path ids are inbound snowflakes, so a
non-numeric id answers 422.

The router owns HTTP and nothing else: no SQL, no `app.db.schema` import, no
`app.services.parens` import (R12 parse-once lives in the settle service). Domain errors
propagate to the one registered `DomainError` handler; the router catches nothing. No
discard, stop or delete route exists (R11, UC-086).

Feature `021`, step `006` adds the one streaming route, `POST …/zone/compose` (D1, D2):
`begin_compose` commits the text (or, textless, checks there is something to retry) on the
handler's connection — its domain errors answer as JSON before any stream — then the handler
returns 019's `sse_response` over `compose_stream` with the own-connection persister. The
chat-client factory and the tool registry arrive through two overridable dependencies (D14).

Feature `024`, step `005` (D9, Wire contract): the four record-keeping routes — settle, re-open,
`POST …/entries` and `PATCH /api/messages/{message_id}` — also depend on the shared
`get_llm_client_factory` (`app.dependencies`) and on `get_settings`, and pass the factory and
`settings.llm_request_timeout_seconds` to their service call. The handlers stay sync `def` and
gain no body or query parameter, so the two dependencies are invisible on the wire. Every other
handler here is unchanged: the zone append and the three list reads pick
`search_coverage_incomplete` up from `StreamMessage`'s false default.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import Connection

from app.config import Settings, get_settings
from app.db.engine import get_connection, get_engine
from app.dependencies import CurrentUser, get_llm_client_factory, require_user
from app.ids import SnowflakeGenerator
from app.models.ids import SnowflakeIn
from app.models.stream import (
    AppendMessageRequest,
    ComposeRequest,
    DiscussionResponse,
    EditMessageRequest,
    EntryListResponse,
    FilePartnerRequest,
    MessageResponse,
    ReopenResponse,
    SettleResponse,
    ZoneResponse,
)
from app.routers.bootstrap import get_id_generator
from app.services.compose import begin_compose, compose_stream
from app.services.llm.client import LlmClient
from app.services.llm.frames import own_connection_persister, sse_response
from app.services.llm_registry import ChatClientFactory, LlmClientFactory
from app.services.messages import (
    StreamMessage,
    append_message,
    edit_message_text,
    file_partner_entry,
    list_discussion,
    list_entries,
    list_zone,
)
from app.services.settle import ReopenResult, SettleResult, reopen, settle
from app.services.tools import ToolRegistry
from app.services.tools.seam import build_tool_registry

router = APIRouter(
    tags=["stream"],
    dependencies=[Depends(require_user)],
)


def _message_to_response(message: StreamMessage) -> MessageResponse:
    """Render one service `StreamMessage` as the wire `MessageResponse`."""
    return MessageResponse.model_validate(message, from_attributes=True)


def _settle_to_response(result: SettleResult) -> SettleResponse:
    """Render a service `SettleResult` as the wire `SettleResponse`."""
    return SettleResponse(
        entry_id=result.entry_id,
        kind=result.kind,
        buried_ids=list(result.buried_ids),
        search_coverage_incomplete=result.search_coverage_incomplete,
    )


def _reopen_to_response(result: ReopenResult) -> ReopenResponse:
    """Render a service `ReopenResult` as the wire `ReopenResponse`."""
    return ReopenResponse(
        reopened_id=result.reopened_id,
        restored_ids=list(result.restored_ids),
        search_coverage_incomplete=result.search_coverage_incomplete,
    )


@router.get("/api/sessions/{session_id}/entries", status_code=200)
def list_session_entries(
    session_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> EntryListResponse:
    """The session's settled entries via `list_entries(connection, user_id, session_id)`."""
    entries = list_entries(connection, current_user.id, session_id)
    return EntryListResponse(entries=[_message_to_response(entry) for entry in entries])


@router.post("/api/sessions/{session_id}/entries", status_code=201)
def file_partner(
    session_id: SnowflakeIn,
    body: FilePartnerRequest,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
    settings: Annotated[Settings, Depends(get_settings)],
    client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)],
) -> MessageResponse:
    """File a partner block via `file_partner_entry(..., body.text)`; answers 201.

    The body's `kind` is validated by the model and not passed on. 024 D9: the shared client
    factory and `settings.llm_request_timeout_seconds` are forwarded for the degraded refresh.
    """
    message = file_partner_entry(
        connection,
        generator,
        current_user.id,
        session_id,
        body.text,
        client_factory=client_factory,
        timeout_seconds=settings.llm_request_timeout_seconds,
    )
    return _message_to_response(message)


@router.get("/api/sessions/{session_id}/zone", status_code=200)
def list_session_zone(
    session_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> ZoneResponse:
    """The session's current zone via `list_zone(connection, user_id, session_id)`."""
    zone = list_zone(connection, current_user.id, session_id)
    return ZoneResponse(messages=[_message_to_response(message) for message in zone])


@router.post("/api/sessions/{session_id}/zone/messages", status_code=201)
def append_zone_message(
    session_id: SnowflakeIn,
    body: AppendMessageRequest,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
) -> MessageResponse:
    """Append a user message to the zone via `append_message(..., body.text)`; answers 201."""
    message = append_message(connection, generator, current_user.id, session_id, body.text)
    return _message_to_response(message)


def get_chat_client_factory() -> ChatClientFactory:
    """The chat-client factory dependency: the real `LlmClient` class (D14). Tests override it."""
    return LlmClient


def get_tool_registry(settings: Annotated[Settings, Depends(get_settings)]) -> ToolRegistry:
    """The tool-registry dependency: the request's registry (004, D14; 028 D3). Tests override it.

    Still the one overridable dependency `compose_zone` passes to the compose source, and still
    unchanged in that role - only its value is now built rather than constant. It returns
    `build_tool_registry` for the two search credentials: the API key's plain value, unwrapped
    with `get_secret_value()` when the field is set and `None` when it is not, and the engine id
    as it stands. Neither is trimmed or tested here; "configured" is `tools/web_search.py`'s rule
    (028 D3), and this is the only place in the chain that reads `Settings` at all.

    Not cached, and that is the point: building per request is what makes the credentials live, so
    a `get_settings` override or a cache clear takes effect on the next call rather than at import.
    """
    key = settings.search_cse_key
    return build_tool_registry(None if key is None else key.get_secret_value(), settings.search_cse_id)


@router.post("/api/sessions/{session_id}/zone/compose", status_code=200)
def compose_zone(
    session_id: SnowflakeIn,
    body: ComposeRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
    settings: Annotated[Settings, Depends(get_settings)],
    client_factory: Annotated[ChatClientFactory, Depends(get_chat_client_factory)],
    registry: Annotated[ToolRegistry, Depends(get_tool_registry)],
) -> StreamingResponse:
    """Commit (or check) via `begin_compose`, then stream `compose_stream` (D1, D2).

    Returns `sse_response(request, compose_stream(engine=get_engine(settings), ...),
    own_connection_persister(get_engine(settings), generator, user id, session id))`.
    """
    accepted_id = begin_compose(connection, generator, current_user.id, session_id, body.text)
    engine = get_engine(settings)
    source = compose_stream(
        engine,
        generator,
        current_user.id,
        session_id,
        accepted_id,
        settings.llm_request_timeout_seconds,
        client_factory,
        registry,
    )
    on_partial = own_connection_persister(engine, generator, current_user.id, session_id)
    return sse_response(request, source, on_partial)


@router.post("/api/sessions/{session_id}/settle", status_code=200)
def settle_zone(
    session_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
    client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)],
) -> SettleResponse:
    """Settle the current zone via `settle(connection, user_id, session_id)`. No body.

    024 D9: the shared client factory and `settings.llm_request_timeout_seconds` are forwarded
    for the degraded refresh, and the result's coverage flag reaches the response.
    """
    result = settle(
        connection,
        current_user.id,
        session_id,
        client_factory=client_factory,
        timeout_seconds=settings.llm_request_timeout_seconds,
    )
    return _settle_to_response(result)


@router.post("/api/sessions/{session_id}/reopen", status_code=200)
def reopen_group(
    session_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
    client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)],
) -> ReopenResponse:
    """Re-open the last settled group via `reopen(connection, user_id, session_id)`. No body.

    024 D9: the shared client factory and `settings.llm_request_timeout_seconds` are forwarded
    for the degraded refresh, and the result's coverage flag reaches the response.
    """
    result = reopen(
        connection,
        current_user.id,
        session_id,
        client_factory=client_factory,
        timeout_seconds=settings.llm_request_timeout_seconds,
    )
    return _reopen_to_response(result)


@router.patch("/api/messages/{message_id}", status_code=200)
def edit_message(
    message_id: SnowflakeIn,
    body: EditMessageRequest,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
    client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)],
) -> MessageResponse:
    """Replace a zone message's text via `edit_message_text(..., body.text)`.

    024 D9: the shared client factory and `settings.llm_request_timeout_seconds` are forwarded;
    the service uses them only when the edited row is a record row (D5).
    """
    message = edit_message_text(
        connection,
        current_user.id,
        message_id,
        body.text,
        client_factory=client_factory,
        timeout_seconds=settings.llm_request_timeout_seconds,
    )
    return _message_to_response(message)


@router.get("/api/messages/{message_id}/discussion", status_code=200)
def get_discussion(
    message_id: SnowflakeIn,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
) -> DiscussionResponse:
    """A settled entry's buried group via `list_discussion(connection, user_id, message_id)` (022 D1)."""
    messages = list_discussion(connection, current_user.id, message_id)
    return DiscussionResponse(messages=[_message_to_response(message) for message in messages])
