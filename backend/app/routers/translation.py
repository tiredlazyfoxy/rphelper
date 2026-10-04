"""`POST /api/messages/{message_id}/translation` — the partner-entry translate route.

Feature `023`, step `003` (`context.md` D1, D4, D12). Transport layer only: no SQL, no
`app.db.schema` import, no business rule. The one handler calls
`app.services.translation.translate_message` and renders its result as
`app.models.translation.TranslationResponse`.

**Not streamed (D1).** A translation replaces the whole body of a read-only flicker, so
partial output has no use: this is a plain JSON request/response with no request body, no SSE
and no frame types. It is nonetheless an **`async def`**, because it awaits the service and
`request.is_disconnected()`; every other handler in the backend stays a sync `def`.

**The disconnect probe (D4).** The handler passes a closure over its own `Request` that awaits
`request.is_disconnected()`. The service awaits it once, immediately before the cache write, so
a stop that lands earlier leaves nothing cached. That is **best-effort, not a guarantee**: a
disconnect arriving after the probe still gets its row written, which is the named divergence
from US-133.AC-2 recorded in `llm-and-streaming.md`.

Declared with **no prefix**; the handler carries its full literal path. `require_user` is
attached to the **router** so a route added later cannot forget the guard, and the handler also
names it as a parameter to receive the `CurrentUser` whose `id` scopes the service call. The
path id uses the inbound snowflake alias, so a non-numeric id answers 422 before the handler
runs. The engine comes from `get_engine(settings)` — a process-level cache keyed on the
resolved database path, not a dependency — so a test overriding `get_settings` gets its own
engine.

The chat-client factory arrives through **this module's own** overridable dependency,
`get_translation_chat_client_factory` (021 `006`'s pattern, named distinctly from
`app.routers.stream.get_chat_client_factory` so `dependency_overrides` targets one of them
unambiguously). The router catches nothing: `MessageNotFoundError` (404), 017's model errors
(409), `secret_ref_missing` and `TranslationFailedError` (502) all propagate to the one
registered `DomainError` handler in `app.main`. Registered **after every other router** there.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.config import Settings, get_settings
from app.db.engine import get_engine
from app.dependencies import CurrentUser, require_user
from app.ids import SnowflakeGenerator
from app.models.ids import SnowflakeIn
from app.models.translation import TranslationResponse
from app.routers.bootstrap import get_id_generator
from app.services.llm.client import LlmClient
from app.services.llm_registry import ChatClientFactory
from app.services.translation import translate_message

router = APIRouter(
    tags=["translation"],
    dependencies=[Depends(require_user)],
)


def get_translation_chat_client_factory() -> ChatClientFactory:
    """The translate route's chat-client factory dependency: the real `LlmClient` class (D12).

    Named distinctly from `app.routers.stream.get_chat_client_factory` on purpose — tests
    override **this** name with `dependency_overrides`, and `routers/stream.py` is untouched.
    """
    return LlmClient


@router.post("/api/messages/{message_id}/translation", status_code=200)
async def translate_partner_message(
    message_id: SnowflakeIn,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    generator: Annotated[SnowflakeGenerator, Depends(get_id_generator)],
    client_factory: Annotated[ChatClientFactory, Depends(get_translation_chat_client_factory)],
) -> TranslationResponse:
    """Translate one settled partner row, answering 200 with the wire `Translation` (D12).

    Awaits `translate_message(get_engine(settings), generator, current_user.id, message_id,
    settings.llm_request_timeout_seconds, client_factory, <probe>)`, where `<probe>` is an async
    closure returning `await request.is_disconnected()` (D4), and returns
    `TranslationResponse.model_validate(result)` — `cached` is `True` when the answer came from
    the `translations` table with no model call. No request body. Domain errors are not caught.
    """

    async def is_disconnected() -> bool:
        """The disconnect probe (D4): `True` once this request's client has gone away.

        A closure over the handler's own `Request`, so the service — which imports no
        `fastapi` — can await it once, immediately before the cache write.
        """
        return await request.is_disconnected()

    result = await translate_message(
        get_engine(settings),
        generator,
        current_user.id,
        message_id,
        settings.llm_request_timeout_seconds,
        client_factory,
        is_disconnected,
    )
    return TranslationResponse.model_validate(result, from_attributes=True)
