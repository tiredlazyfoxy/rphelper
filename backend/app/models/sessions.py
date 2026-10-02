"""The RP-session request and response models — nothing else.

"Session" here is always the **RP session** (one `sessions` row), never the login session
(`auth_sessions`, `services/auth.py`).

**Responses.** `SessionResponse` is the one session shape every route in
`routers/sessions.py` answers with — both lists, create, read, archive and restore
(`context.md` Wire contract). `id` and `character_id` use the outbound snowflake alias and
`setup_id` its nullable form, so every id leaves as a **decimal string**; a bare `int` would
put a JS-unsafe number on the wire (`data-model.md` § Identifiers). It carries **no
`user_id`**: ownership is a server-side scope, never wire data (R5). The four timestamps are
passed through as the fixed-width UTC text the row stores (`data-model.md` § Timestamps), so
they are `str`, not `datetime` — nothing here re-formats them; `last_used_at` is a different
instant from `updated_at` (D3). `archived_at` is `None` for a working session. `setup_name`
is the referenced setup's **current** name, joined at read time by the service and present
even when that setup is archived (D10), and `None` when the session has no setup.
`SessionListResponse` wraps the rows under one `sessions` field — a route never returns a
bare list.

**Requests.** `StartSessionRequest` is the create body, and the whole body is optional
(D2): omitted, `{}`, `{"setup_id": null}` and `{"setup_id": "<decimal string>"}` are all
legal, and the first three all mean "no setup" (R2 — no default, no sentinel). There is no
`character_id` field: the parent comes from the path and a session never moves. Undeclared
request fields are **ignored**, so `character_id`, `user_id`, `last_used_at` and `title`
cannot be set through a body.

`setup_id` is the codebase's first **nullable inbound** id, so it cannot use `SnowflakeIn`
directly: that alias is `BeforeValidator(lambda v: int(v))`, and `int(None)` raises
`TypeError`, which pydantic v2 does not convert into a 422. `OptionalSnowflakeIn` below
short-circuits `None` ahead of the conversion and re-raises a `TypeError` as a `ValueError`
so that *any* non-numeric JSON value answers 422 rather than 500 (`context.md`'s "a
non-numeric path id or `setup_id` → 422"). It lives here rather than in `models/ids.py`
because it has exactly one call site so far.

This module imports neither `app.services`, `app.routers`, `app.db` nor `fastapi`.
"""

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict

from app.models.ids import SnowflakeOut


def _parse_optional_snowflake(value: Any) -> int | None:
    """`None` passes straight through; anything else goes through `int()` as `SnowflakeIn` does."""
    if value is None:
        return None
    try:
        return int(value)
    except TypeError as exc:
        # `int()` raises `TypeError` for a JSON object, array or boolean-shaped oddity, and
        # pydantic v2 lets a `TypeError` escape as a 500. A `ValueError` becomes a 422, which
        # is what a malformed id field must answer. `int("abc")` already raises `ValueError`.
        raise ValueError("A setup id must be a decimal string.") from exc


#: A nullable inbound snowflake: JSON `null` and an absent field both give `None`, a decimal
#: string gives the `int`, and anything else is a validation error (422).
OptionalSnowflakeIn = Annotated[int | None, BeforeValidator(_parse_optional_snowflake)]


class SessionResponse(BaseModel):
    """One RP session on the wire. Eight keys, never `user_id`."""

    id: SnowflakeOut
    character_id: SnowflakeOut
    setup_id: SnowflakeOut | None
    setup_name: str | None
    archived_at: str | None
    last_used_at: str
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    """The caller's sessions, under the single `sessions` field, in the order the service gave."""

    sessions: list[SessionResponse]


class StartSessionRequest(BaseModel):
    """The start-session body: one optional, nullable `setup_id`. Unknown keys are ignored."""

    model_config = ConfigDict(extra="ignore")

    setup_id: OptionalSnowflakeIn = None
