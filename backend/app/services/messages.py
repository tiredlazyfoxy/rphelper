"""Stream messages — read the record, read the zone, append, file a partner block, edit.

Feature `012`, step `002`. Plain arguments in, frozen `StreamMessage` values out or a typed
`DomainError` raised. This module imports nothing HTTP-shaped and nothing from any
`app.services.` module. Every operation takes a Core `Connection` first and the owner's
`user_id` as a required positional argument after it (after the id generator, for the two
inserts). Reads go only through the schema layer's selectables (`settled_entries`,
`current_zone`, `message_states` — D1, D7); every write bumps the session (D3); nothing here
ever names `related_to` in an insert or update, nor touches the settle columns of an existing
row (D16). Feature `014` step `001` widens the edit to settled rows of any kind (text only;
a buried row stays refused). The one delete in this module is the edited message's cached
`translations` rows, discarded inside the edit's own transaction (feature `023` D11); nothing
else is deleted or discarded here, and there is no settle-state operation.

Feature `024`, step `005` (D5, D8, U1, U5) makes two of these operations record-keeping
writes: `file_partner_entry` (a born-settled row) and `edit_message_text` **on a record row**
refresh that session's `session_vec` through `app.services.session_index`, inside their own
transaction and after the write, so the composed text observes the new state. The posture is
**degraded**: "unavailable" is caught inside that refresh, the row still commits, no vector is
written and any existing one is left stale; the outcome rides home on `StreamMessage` as
`search_coverage_incomplete`, which **defaults to false** so every other construction and
every list read here is untouched. A zone append and a zone-row edit do no vector work at all
(US-115) and answer false. The client factory and the request timeout arrive as keyword-only
parameters with D9's defaults, so nothing here reads settings and every existing positional
call still binds.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal, NamedTuple

from sqlalchemy import Connection, Row, Select, select

from app.db.schema import (
    buried_messages,
    current_zone,
    message_states,
    messages,
    sessions,
    settled_entries,
    translations,
)
from app.errors import MessageNotEditableError, MessageNotFoundError, SessionNotFoundError
from app.ids import SnowflakeGenerator
from app.services.session_index import (
    DEFAULT_EMBED_TIMEOUT_SECONDS,
    LlmClient,
    LlmClientFactory,
    refresh_session_vector_degraded,
)

#: A tool row's derived outcome (feature `022` D3): `"ok"` only on a readable ok payload.
ToolStatus = Literal["ok", "failed"]


class ToolView(NamedTuple):
    """The wire view of one row's tool columns (feature `022` D3) — all `None` on a non-tool row."""

    tool_name: str | None
    tool_status: ToolStatus | None
    tool_args: dict[str, Any] | None


def tool_view(role: str, tool_name: str | None, tool_payload: str | None) -> ToolView:
    """Derive `(tool_name, tool_status, tool_args)` from a row's role and tool columns (022 D3).

    Pure: no I/O, and never raises on any payload string, including invalid JSON.
    """
    if role != "tool":
        return ToolView(tool_name=None, tool_status=None, tool_args=None)
    payload = _json_object(tool_payload)
    if payload is None:
        return ToolView(tool_name=tool_name, tool_status="failed", tool_args={})
    status: ToolStatus = "ok" if payload.get("status") == "ok" else "failed"
    arguments = payload.get("arguments")
    args = _json_object(arguments) if isinstance(arguments, str) else None
    return ToolView(tool_name=tool_name, tool_status=status, tool_args=args if args is not None else {})


def _json_object(text: str | None) -> dict[str, Any] | None:
    """`text` parsed as a JSON object, or `None` when it is absent, unparseable or not an object."""
    if text is None:
        return None
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


@dataclass(frozen=True)
class StreamMessage:
    """One `messages` row as every operation here returns it — and nothing more.

    No `user_id`, no `related_to`. The first eight fields are `MessageResponse`'s, in its
    order (`app.models.stream`, step `001`); the two tool columns (feature `021` D7) follow,
    defaulting to `None`, and never reach the wire. Then the derived tool view (feature `022`
    D3: `tool_status`, `tool_args`, default `None`; `tool_name` is shared with the columns).
    Timestamps are the stored fixed-width UTC text.

    `search_coverage_incomplete` (feature `024`, D8 / Wire contract) is last and **defaults to
    `False`**. The default is load-bearing: every read, every zone write and every other
    construction of this value keeps working unchanged and answers "coverage complete", and
    only the two record-keeping writes ever set it to `True`.
    """

    id: int
    session_id: int
    role: str
    kind: str | None
    text: str
    settled_at: str | None
    created_at: str
    updated_at: str
    tool_name: str | None = None
    tool_payload: str | None = None
    tool_status: ToolStatus | None = None
    tool_args: dict[str, Any] | None = None
    search_coverage_incomplete: bool = False


def list_entries(connection: Connection, user_id: int, session_id: int) -> list[StreamMessage]:
    """The session's settled rows (through `settled_entries`), ascending id."""
    return _list_session_rows(connection, settled_entries, user_id, session_id)


def list_zone(connection: Connection, user_id: int, session_id: int) -> list[StreamMessage]:
    """The session's current-zone rows (through `current_zone`), ascending id."""
    return _list_session_rows(connection, current_zone, user_id, session_id)


def list_discussion(connection: Connection, user_id: int, entry_id: int) -> list[StreamMessage]:
    """The rows buried under the owner's settled entry `entry_id`, ascending id (022 D1).

    The entry is confirmed through `settled_entries` (id and owner) first, else
    `MessageNotFoundError`; the rows are read through `buried_messages`. A read only.
    """
    entry_columns = settled_entries.selected_columns
    buried_columns = buried_messages.selected_columns
    with _reading(connection):
        entry = connection.execute(
            settled_entries.where(entry_columns.id == entry_id, entry_columns.user_id == user_id)
        ).first()
        if entry is None:
            raise MessageNotFoundError()
        rows = connection.execute(
            buried_messages.where(
                buried_columns.related_to == entry_id, buried_columns.user_id == user_id
            ).order_by(buried_columns.id.asc())
        ).all()
    return [_to_message(row) for row in rows]


def append_message(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    session_id: int,
    text: str,
) -> StreamMessage:
    """Insert one roleplayer zone message and bump the session."""
    with connection.begin():
        _require_session(connection, user_id, session_id)
        now = _now_text()
        message = insert_zone_message(connection, generator, user_id, session_id, text, now)
        _bump_session(connection, user_id, session_id, now)
    return message


def append_assistant_message(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    session_id: int,
    text: str,
) -> StreamMessage:
    """Insert one assistant zone message (`kind` NULL) and bump the session — 019 D8.

    The one write of a `role='assistant'` current-zone row; no blank-text check.
    """
    with connection.begin():
        _require_session(connection, user_id, session_id)
        new_id = generator.next_id()
        now = _now_text()
        connection.execute(
            messages.insert().values(
                id=new_id,
                user_id=user_id,
                session_id=session_id,
                role="assistant",
                text=text,
                created_at=now,
                updated_at=now,
            )
        )
        _bump_session(connection, user_id, session_id, now)
        message = StreamMessage(
            id=new_id,
            session_id=session_id,
            role="assistant",
            kind=None,
            text=text,
            settled_at=None,
            created_at=now,
            updated_at=now,
        )
    return message


def append_tool_message(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    session_id: int,
    text: str,
    tool_name: str,
    tool_payload: str,
) -> StreamMessage:
    """Insert one `role='tool'` current-zone row and bump the session — feature `021` D7.

    `kind`, `related_to` and `settled_at` NULL; `tool_name` and `tool_payload` stored verbatim
    (the payload is not interpreted). One transaction, same ownership check
    (`SessionNotFoundError`) and session bump as `append_assistant_message`.
    """
    with connection.begin():
        _require_session(connection, user_id, session_id)
        new_id = generator.next_id()
        now = _now_text()
        connection.execute(
            messages.insert().values(
                id=new_id,
                user_id=user_id,
                session_id=session_id,
                role="tool",
                text=text,
                tool_name=tool_name,
                tool_payload=tool_payload,
                created_at=now,
                updated_at=now,
            )
        )
        _bump_session(connection, user_id, session_id, now)
        view = tool_view("tool", tool_name, tool_payload)
        message = StreamMessage(
            id=new_id,
            session_id=session_id,
            role="tool",
            kind=None,
            text=text,
            settled_at=None,
            created_at=now,
            updated_at=now,
            tool_name=tool_name,
            tool_payload=tool_payload,
            tool_status=view.tool_status,
            tool_args=view.tool_args,
        )
    return message


def insert_zone_message(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    session_id: int,
    text: str,
    now: str,
) -> StreamMessage:
    """Insert one current-zone user row stamped `now` — transaction-neutral (018 D3).

    Opens no transaction, checks nothing about the session and does not bump it: the caller
    owns all three.
    """
    new_id = generator.next_id()
    connection.execute(
        messages.insert().values(
            id=new_id,
            user_id=user_id,
            session_id=session_id,
            role="user",
            text=text,
            created_at=now,
            updated_at=now,
        )
    )
    return StreamMessage(
        id=new_id,
        session_id=session_id,
        role="user",
        kind=None,
        text=text,
        settled_at=None,
        created_at=now,
        updated_at=now,
    )


def file_partner_entry(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    session_id: int,
    text: str,
    *,
    client_factory: LlmClientFactory = LlmClient,
    timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
) -> StreamMessage:
    """Insert one born-settled partner block (`kind` 'partner') and bump the session.

    The positional inputs are unchanged. `client_factory` and `timeout_seconds` are 024 D9's
    keyword-only pair, defaulted to the real client and to `Settings`' own declared timeout, and
    are forwarded to the degraded refresh. `SessionNotFoundError` still refuses before any write
    and before any client is built.
    """
    with connection.begin():
        _require_session(connection, user_id, session_id)
        new_id = generator.next_id()
        now = _now_text()
        connection.execute(
            messages.insert().values(
                id=new_id,
                user_id=user_id,
                session_id=session_id,
                role="user",
                kind="partner",
                text=text,
                settled_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        _bump_session(connection, user_id, session_id, now)
        # 024 D5 / U1: after the insert and the session bump, inside this transaction, so 003's
        # composition sees the filed row among the session's settled entries. D8 / U5: the
        # degraded posture lives inside this call — it catches `NoEmbeddingModelError` and
        # `LlmUnreachableError`, writes no vector, leaves any existing row untouched (stale) and
        # returns True, meaning coverage is INCOMPLETE. Any other exception propagates and rolls
        # this transaction back.
        search_coverage_incomplete = refresh_session_vector_degraded(
            connection,
            user_id,
            session_id,
            client_factory=client_factory,
            timeout_seconds=timeout_seconds,
        )
        message = StreamMessage(
            id=new_id,
            session_id=session_id,
            role="user",
            kind="partner",
            text=text,
            settled_at=now,
            created_at=now,
            updated_at=now,
            search_coverage_incomplete=search_coverage_incomplete,
        )
    return message


def edit_message_text(
    connection: Connection,
    user_id: int,
    message_id: int,
    text: str,
    *,
    client_factory: LlmClientFactory = LlmClient,
    timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
) -> StreamMessage:
    """Replace a zone or settled message's text verbatim, bump its session, return the stored row.

    A buried row (`related_to` set) is refused with `MessageNotEditableError`; `kind`,
    `settled_at` and `related_to` are never written (014 D1). The row is read back through
    `settled_entries` when settled, `current_zone` otherwise.

    The positional inputs are unchanged. `client_factory` and `timeout_seconds` are 024 D9's
    keyword-only pair, as on `file_partner_entry`, and are used only on the record-row branch
    (D5): a zone-row edit builds no client at all. Every refusal (missing, foreign, buried,
    tool) still happens before any write and before any client is built.
    """
    with connection.begin():
        state_columns = message_states.selected_columns
        state = connection.execute(
            message_states.where(state_columns.id == message_id, state_columns.user_id == user_id)
        ).first()
        if state is None:
            raise MessageNotFoundError()
        if state.related_to is not None:
            raise MessageNotEditableError()
        selectable = settled_entries if state.settled_at is not None else current_zone
        columns = selectable.selected_columns
        current = connection.execute(
            selectable.where(columns.id == message_id, columns.user_id == user_id)
        ).one()
        if current.role == "tool":
            # 021 D8: a tool row's text summarises its payload; editing one half desyncs them.
            raise MessageNotEditableError()
        now = _now_text()
        connection.execute(
            messages.update()
            .where(messages.c.id == message_id, messages.c.user_id == user_id)
            .values(text=text, updated_at=now)
        )
        # 023 D11 / US-111.AC-1: new text invalidates every cached translation of this row, in
        # every target language. Inside the same transaction as the update, so the edit and the
        # discard commit or fail together, and a refused edit (missing, foreign, buried, tool)
        # never reaches here. Owner-scoped like every other statement (R5). A no-op for zone
        # rows and turns, which never have cached rows.
        connection.execute(
            translations.delete().where(
                translations.c.message_id == message_id,
                translations.c.user_id == user_id,
            )
        )
        # 024 D5 — the record-row vs. zone-row dispatch, on the classification `message_states`
        # already gave above and which this module keeps using: a buried row was refused, so
        # `state.settled_at is not None` is exactly "a record row" (`context.md` Vocabulary) and
        # the NULL case is a zone row, which does no vector work, builds no client and keeps the
        # flag false (US-115). It sits here, right after the text update and the
        # cached-translation discard of feature 023 (their order between each other is
        # immaterial), inside this one transaction, so 003's composition reads the new text.
        # D8 / U5: the degraded posture lives inside the refresh — it catches
        # `NoEmbeddingModelError` and `LlmUnreachableError`, writes no vector, leaves any existing
        # row untouched (stale) and returns True, meaning coverage is INCOMPLETE; anything else
        # propagates and rolls this transaction back.
        search_coverage_incomplete = False
        if state.settled_at is not None:
            search_coverage_incomplete = refresh_session_vector_degraded(
                connection,
                user_id,
                state.session_id,
                client_factory=client_factory,
                timeout_seconds=timeout_seconds,
            )
        _bump_session(connection, user_id, state.session_id, now)
        row = connection.execute(selectable.where(columns.id == message_id, columns.user_id == user_id)).one()
        # `_to_message` is shared with the read paths, so the flag is put on afterwards rather
        # than threaded through it.
        message = replace(_to_message(row), search_coverage_incomplete=search_coverage_incomplete)
    return message


def _list_session_rows(
    connection: Connection, selectable: Select[Any], user_id: int, session_id: int
) -> list[StreamMessage]:
    """Session check, then `selectable` narrowed to the owner's session, ascending id — a read."""
    columns = selectable.selected_columns
    with _reading(connection):
        _require_session(connection, user_id, session_id)
        rows = connection.execute(
            selectable.where(columns.session_id == session_id, columns.user_id == user_id).order_by(
                columns.id.asc()
            )
        ).all()
    return [_to_message(row) for row in rows]


def _require_session(connection: Connection, user_id: int, session_id: int) -> None:
    """The owner's session exists, or `SessionNotFoundError` (R5). No `archived_at` predicate (R6)."""
    row = connection.execute(
        select(sessions.c.id).where(sessions.c.id == session_id, sessions.c.user_id == user_id)
    ).first()
    if row is None:
        raise SessionNotFoundError()


def _bump_session(connection: Connection, user_id: int, session_id: int, now: str) -> None:
    """Move the session's `last_used_at` and `updated_at` to the write's instant (D3)."""
    connection.execute(
        sessions.update()
        .where(sessions.c.id == session_id, sessions.c.user_id == user_id)
        .values(last_used_at=now, updated_at=now)
    )


def _to_message(row: Row[Any]) -> StreamMessage:
    """A full `messages` row (from a selectable) as the returned value, with its tool view."""
    view = tool_view(row.role, row.tool_name, row.tool_payload)
    return StreamMessage(
        id=row.id,
        session_id=row.session_id,
        role=row.role,
        kind=row.kind,
        text=row.text,
        settled_at=row.settled_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        tool_name=row.tool_name,
        tool_payload=row.tool_payload,
        tool_status=view.tool_status,
        tool_args=view.tool_args,
    )


@contextmanager
def _reading(connection: Connection) -> Iterator[None]:
    """A read on a Core connection autobegins; end it again when the caller had none open."""
    opened_here = not connection.in_transaction()
    try:
        yield
    finally:
        if opened_here and connection.in_transaction():
            connection.rollback()


def _now_text() -> str:
    """Now as the fixed-width UTC ISO-8601 text the other services write."""
    return datetime.now(UTC).isoformat(timespec="microseconds")
