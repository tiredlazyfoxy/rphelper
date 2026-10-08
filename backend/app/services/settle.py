"""Settle and re-open — the only writers of the burial and settle columns.

Feature `012`, step `003` (R11, D10, D16). Each operation is one write transaction, takes
the Core `Connection` first and the owner's `user_id` as a required positional argument,
and takes no target message id. This module imports nothing HTTP-shaped and, from
`app.services.`, only `parens` (D11) and `llm.chat`'s `strip_think` (feature `021` D4); its
session check, session bump and clock are its own private helpers. Settle is two UPDATEs on
`messages` (bury, then stamp the head) and adds or removes no row; re-open is its exact mirror.

Feature `024`, step `005` (D5, D8, U1, U5) makes both operations record-keeping writes: each
refreshes its session's `session_vec` through `app.services.session_index` — the one
`app.services.` import this module gains — as the **last** statement of its own transaction,
after every relational write, so the composed text observes the new state (the head's
rewritten text and its `settled_at`, or their removal). The posture is **degraded**:
"unavailable" is caught inside that refresh, the relational write still commits, no vector is
written and any existing row is left stale; the outcome rides home on the result as
`search_coverage_incomplete` (**true** means coverage is incomplete). The client factory and
the request timeout arrive as keyword-only parameters with D9's defaults, so nothing here
reads settings and every existing positional call still binds.
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
from app.services.llm.chat import strip_think
from app.services.session_index import (
    DEFAULT_EMBED_TIMEOUT_SECONDS,
    LlmClient,
    LlmClientFactory,
    refresh_session_vector_degraded,
)


@dataclass(frozen=True)
class SettleResult:
    """The settled head, the kind it was stamped with, and the ids buried under it (ascending).

    `search_coverage_incomplete` is 024's coverage flag (D8, Wire contract): **true** when the
    degraded `session_vec` refresh could not embed. Required, with no default — settle always
    decides it, and a default would let a caller silently answer "complete".
    """

    entry_id: int
    kind: parens.Kind
    buried_ids: list[int]
    search_coverage_incomplete: bool


@dataclass(frozen=True)
class ReopenResult:
    """The former head and the former group's ids restored to the zone (ascending, never empty).

    `search_coverage_incomplete` is 024's coverage flag (D8, Wire contract): **true** when the
    degraded `session_vec` refresh could not embed. Required, with no default, exactly as on
    `SettleResult`.
    """

    reopened_id: int
    restored_ids: list[int]
    search_coverage_incomplete: bool


def settle(
    connection: Connection,
    user_id: int,
    session_id: int,
    *,
    client_factory: LlmClientFactory = LlmClient,
    timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
) -> SettleResult:
    """Settle the session's current zone onto its last row; bury the rest under it.

    The positional inputs are unchanged. `client_factory` and `timeout_seconds` are 024 D9's
    keyword-only pair, defaulted to the real client and to `Settings`' own declared timeout, and
    are forwarded to the degraded refresh. Every existing refusal (`ZoneEmptyError`, a foreign
    or missing session) still happens before any refresh and before any client is built.
    """
    with connection.begin():
        _require_session(connection, user_id, session_id)
        zone_columns = current_zone.selected_columns
        zone_rows = connection.execute(
            current_zone.where(
                zone_columns.session_id == session_id, zone_columns.user_id == user_id
            ).order_by(zone_columns.id.asc())
        ).all()
        # 021 D8: the head is the last non-tool row; a zone of only tool rows counts as empty.
        heads = [row for row in zone_rows if row.role != "tool"]
        if not heads:
            raise ZoneEmptyError()
        head = heads[-1]
        head_id = int(head.id)
        # 021 D4: an assistant head loses its think blocks before the `(( ))` classification.
        head_text = strip_think(head.text) if head.role == "assistant" else head.text
        kind = parens.classify(head_text)
        settled_text = head_text if kind == "decision" else parens.strip_fragments(head_text)
        buried_ids = [int(row.id) for row in zone_rows if int(row.id) != head_id]
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
        # 024 D5 / U1: the LAST statement of this transaction, after every relational write, so
        # 003's composition observes the new state — the head's rewritten `settled_text` and its
        # `settled_at`, which the UPDATE above stamped in one go. D8 / U5: the degraded posture
        # lives inside this call — it catches `NoEmbeddingModelError` and `LlmUnreachableError`,
        # writes no vector, leaves any existing row untouched (stale) and returns True, meaning
        # coverage is INCOMPLETE. Any other exception propagates and rolls this transaction back.
        search_coverage_incomplete = refresh_session_vector_degraded(
            connection,
            user_id,
            session_id,
            client_factory=client_factory,
            timeout_seconds=timeout_seconds,
        )
    return SettleResult(
        entry_id=head_id,
        kind=kind,
        buried_ids=buried_ids,
        search_coverage_incomplete=search_coverage_incomplete,
    )


def reopen(
    connection: Connection,
    user_id: int,
    session_id: int,
    *,
    client_factory: LlmClientFactory = LlmClient,
    timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
) -> ReopenResult:
    """Re-open the session's last settled group back into an empty zone.

    The positional inputs are unchanged; `client_factory` and `timeout_seconds` are 024 D9's
    keyword-only pair, as on `settle`. `ZoneNotEmptyError` and `NothingToReopenError` still
    refuse before any refresh and before any client is built.
    """
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
        # 024 D5 / U1: the LAST statement of this transaction, after every relational write, so
        # 003's composition observes the new state — the re-opened head has left
        # `settled_entries` and its text is no longer part of the session text. D8 / U5: the
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
    return ReopenResult(
        reopened_id=head_id,
        restored_ids=group_ids,
        search_coverage_incomplete=search_coverage_incomplete,
    )


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
