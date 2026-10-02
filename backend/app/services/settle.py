"""Settle and re-open — the only writers of the burial and settle columns.

Feature `012`, step `003` (R11, D10, D16). Each operation is one write transaction, takes
the Core `Connection` first and the owner's `user_id` as a required positional argument,
and takes no target message id. This module imports nothing HTTP-shaped and, from
`app.services.`, only `parens` (D11); its session check, session bump and clock are its own
private helpers. Settle is two UPDATEs on `messages` (bury, then stamp the head) and adds or
removes no row; re-open is its exact mirror.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection, select

from app.db.schema import current_zone, messages, sessions, settled_entries
from app.errors import (
    NothingToReopenError,
    SessionNotFoundError,
    ZoneEmptyError,
    ZoneNotEmptyError,
)
from app.services import parens


@dataclass(frozen=True)
class SettleResult:
    """The settled head, the kind it was stamped with, and the ids buried under it (ascending)."""

    entry_id: int
    kind: parens.Kind
    buried_ids: list[int]


@dataclass(frozen=True)
class ReopenResult:
    """The former head and the former group's ids restored to the zone (ascending, never empty)."""

    reopened_id: int
    restored_ids: list[int]


def settle(connection: Connection, user_id: int, session_id: int) -> SettleResult:
    """Settle the session's current zone onto its last row; bury the rest under it."""
    with connection.begin():
        _require_session(connection, user_id, session_id)
        zone_columns = current_zone.selected_columns
        zone_rows = connection.execute(
            current_zone.where(
                zone_columns.session_id == session_id, zone_columns.user_id == user_id
            ).order_by(zone_columns.id.asc())
        ).all()
        if not zone_rows:
            raise ZoneEmptyError()
        head = zone_rows[-1]
        head_id = int(head.id)
        kind = parens.classify(head.text)
        settled_text = head.text if kind == "decision" else parens.strip_fragments(head.text)
        buried_ids = [int(row.id) for row in zone_rows[:-1]]
        now = _now_text()
        # Bury first: once the head carries `settled_at` it has left the zone.
        if buried_ids:
            connection.execute(
                messages.update()
                .where(messages.c.id.in_(buried_ids), messages.c.user_id == user_id)
                .values(related_to=head_id, updated_at=now)
            )
        connection.execute(
            messages.update()
            .where(messages.c.id == head_id, messages.c.user_id == user_id)
            .values(settled_at=now, kind=kind, text=settled_text, updated_at=now)
        )
        _bump_session(connection, user_id, session_id, now)
    return SettleResult(entry_id=head_id, kind=kind, buried_ids=buried_ids)


def reopen(connection: Connection, user_id: int, session_id: int) -> ReopenResult:
    """Re-open the session's last settled group back into an empty zone."""
    with connection.begin():
        _require_session(connection, user_id, session_id)
        zone_columns = current_zone.selected_columns
        zone_row = connection.execute(
            current_zone.where(
                zone_columns.session_id == session_id, zone_columns.user_id == user_id
            ).limit(1)
        ).first()
        if zone_row is not None:
            raise ZoneNotEmptyError()
        settled_columns = settled_entries.selected_columns
        last_settled = connection.execute(
            settled_entries.where(
                settled_columns.session_id == session_id, settled_columns.user_id == user_id
            )
            .order_by(settled_columns.id.desc())
            .limit(1)
        ).first()
        if last_settled is None:
            raise NothingToReopenError()
        head_id = int(last_settled.id)
        group_ids = [
            int(row.id)
            for row in connection.execute(
                select(messages.c.id)
                .where(messages.c.related_to == head_id, messages.c.user_id == user_id)
                .order_by(messages.c.id.asc())
            ).all()
        ]
        if not group_ids:
            raise NothingToReopenError()
        now = _now_text()
        connection.execute(
            messages.update()
            .where(messages.c.id.in_(group_ids), messages.c.user_id == user_id)
            .values(related_to=None, updated_at=now)
        )
        connection.execute(
            messages.update()
            .where(messages.c.id == head_id, messages.c.user_id == user_id)
            .values(settled_at=None, kind=None, updated_at=now)
        )
        _bump_session(connection, user_id, session_id, now)
    return ReopenResult(reopened_id=head_id, restored_ids=group_ids)


def _require_session(connection: Connection, user_id: int, session_id: int) -> None:
    """The owner's session exists, or `SessionNotFoundError` (R5). No `archived_at` predicate (R6)."""
    row = connection.execute(
        select(sessions.c.id).where(sessions.c.id == session_id, sessions.c.user_id == user_id)
    ).first()
    if row is None:
        raise SessionNotFoundError()


def _bump_session(connection: Connection, user_id: int, session_id: int, now: str) -> None:
    """Move the session's `last_used_at` and `updated_at` to the operation's instant (D3)."""
    connection.execute(
        sessions.update()
        .where(sessions.c.id == session_id, sessions.c.user_id == user_id)
        .values(last_used_at=now, updated_at=now)
    )


def _now_text() -> str:
    """Now as the fixed-width UTC ISO-8601 text the other services write."""
    return datetime.now(UTC).isoformat(timespec="microseconds")
