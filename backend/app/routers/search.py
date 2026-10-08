"""`GET /api/search` — my-search's one route, transport layer only.

Feature `029`, step `003` (`context.md` D1, U1; FEAT-017; UC-058, UC-059; US-074, US-075, US-076).
The router owns HTTP and nothing else: no business rule, no SQL, no transaction. Its only database
contact is `app.db.engine.get_connection`; every rule lives in
`app.services.search.my_search.run_my_search`.

**One route, one full literal path** (D1). `require_user` is attached to the **router**, so a route
added later cannot forget the guard; the handler also names it as a parameter dependency to receive
the `CurrentUser` whose `id` scopes the search. There is no prefix: the handler spells `/api/search`
in full. Without a session cookie the router answers **401** with the standard envelope before the
handler runs.

**The handler is a sync `def`, and that is load-bearing, not style.** 025's port embeds the query
through 024's `asyncio.run` bridge, which raises if a loop is already running in the thread, so the
handler must not sit on the event loop: a sync `def` route is run by FastAPI in a worker thread with
no loop. Every other handler in the backend except the translate route is sync as well, but here it
is a correctness requirement.

`q` is an ordinary query parameter — no `Query(...)` wrapper, matching this router family — and is
**optional with an empty default**, so `/api/search`, `?q=` and `?q=%20%20` are all the blank query
and all answer 200 with five empty groups and no embedding call (D1). The shared client factory and
the one outbound timeout go into the service by keyword (024 D9), exactly as
`routers/memos.py`'s `create_own_memo` passes them: `client_factory=client_factory` and
`timeout_seconds=settings.llm_request_timeout_seconds`.

**No error is translated here (U1).** `NoEmbeddingModelError` (409, its
`{"reason": "dimension_mismatch"}` detail included), `LlmUnreachableError` (502) and the
`secret_ref_missing` error propagate to the single `DomainError` handler registered in `app.main`,
so a failed search answers that envelope and **no** result keys. There is no partial answer and no
lexical-only degrade.

Registered in `app.main` **after every other router**, so every earlier router's routes keep
matching first.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Connection

from app.config import Settings, get_settings
from app.db.engine import get_connection
from app.dependencies import CurrentUser, get_llm_client_factory, require_user
from app.models.search import (
    CharacterHitResponse,
    EntryHitResponse,
    MemoHitResponse,
    MySearchResponse,
    SessionHitResponse,
    SetupHitResponse,
)
from app.services.llm_registry import LlmClientFactory
from app.services.search.my_search import MySearchResults, run_my_search

router = APIRouter(
    tags=["search"],
    dependencies=[Depends(require_user)],
)


def _to_response(results: MySearchResults) -> MySearchResponse:
    """Render one `MySearchResults` as the wire shape: five keys, in UC-059's order, ids as strings.

    The `MemoChainResponse` form (`routers/memos.py`'s `_to_level_response`): the outer
    `MySearchResponse` is built **by keyword** from five lists, and each leaf row goes through
    `<Kind>HitResponse.model_validate(hit, from_attributes=True)` — the hit dataclasses' field
    order is the contract's, so every kind converts field-for-field with no renaming and no
    computation. Each group keeps the order the service gave it; nothing is re-sorted, dropped or
    added here, and no hit field is read or reshaped by hand.
    """
    return MySearchResponse(
        characters=[CharacterHitResponse.model_validate(hit, from_attributes=True) for hit in results.characters],
        setups=[SetupHitResponse.model_validate(hit, from_attributes=True) for hit in results.setups],
        sessions=[SessionHitResponse.model_validate(hit, from_attributes=True) for hit in results.sessions],
        entries=[EntryHitResponse.model_validate(hit, from_attributes=True) for hit in results.entries],
        memos=[MemoHitResponse.model_validate(hit, from_attributes=True) for hit in results.memos],
    )


@router.get("/api/search", status_code=200)
def my_search(
    current_user: Annotated[CurrentUser, Depends(require_user)],
    connection: Annotated[Connection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
    client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)],
    q: str = "",
) -> MySearchResponse:
    """The owner's whole search for `q` via `run_my_search(...)`, as five grouped lists; 200.

    Calls `run_my_search(connection, current_user.id, q, client_factory=client_factory,
    timeout_seconds=settings.llm_request_timeout_seconds)` and renders the result through
    `_to_response`. The caller's own id is the only scope: no query parameter can widen it, and
    nothing here filters by a note's state or an archive flag (US-076.AC-1, U2, U3).

    A blank or whitespace-only `q` — and an absent one — answers the five empty groups the service
    returns, having opened no model. Any domain error raised by the service leaves this handler
    untouched and is rendered by the one `DomainError` handler (U1).
    """
    return _to_response(
        run_my_search(
            connection,
            current_user.id,
            q,
            client_factory=client_factory,
            timeout_seconds=settings.llm_request_timeout_seconds,
        )
    )
