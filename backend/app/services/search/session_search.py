"""Searching a character's past sessions for the ones that resemble what is being written now.

Feature `027`, step `001` (FEAT-015; UC-053, UC-054). The service half of the `session_search`
tool — the search itself, with the module's two literals:

- **`SESSION_SEARCH_LIMIT`** — the fixed result cap, passed to the port as `limit`. No paging, no
  offset, no count argument; it is lower than `memo_search`'s because each hit carries a long
  excerpt (D2).
- **`SESSION_EXCERPT_CHARS`** — the excerpt's character bound (D3). It lives here, beside the cap,
  so the module's literals are in one place; step `002`'s excerpt read is what applies it.
- **`past_session_predicate`** — the extra predicate the port's session scope variant accepts: the
  same character, not the session being composed in, and not archived (D1). The owner term is the
  port's own (R5) and is not restated here.
- **`search_sessions`** — the synchronous wrapper: build the session scope for the owner and that
  predicate, call the port once with the fixed cap, return its hits unchanged, order included.

Step `002` adds this module's other half beside the search, so that a hit's id becomes a result
block without a second module reading the database: **`SessionExcerpt`**, one matched session's
header fields and bounded excerpt, and **`list_session_excerpts`**, the owner-scoped read that
turns hit ids into those records in the given order (D3, D4).

Vector arm only: the session variant fixes the arms, so nothing here passes a flag, builds a
lexical expression or names the session FTS index — that index is `029`'s.

This module is service-layer only: it imports no web framework, nothing from the tool layer and
nothing from the vector extension, so it can be exercised with a connection and nothing else. Reads
only, writes nothing, and leaves the connection with no transaction open on return **and** on raise
- 027's standing guarantee to the seam, independent of the port's error path (D6, 025 D7).
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Final

from sqlalchemy import ColumnElement, Connection, FromClause, and_, select

from app.db.schema import sessions, settled_entries, setups
from app.services.embedding import DEFAULT_EMBED_TIMEOUT_SECONDS
from app.services.llm.client import LlmClient
from app.services.llm_registry import LlmClientFactory
from app.services.search.hybrid import search
from app.services.search.ports import ExtraPredicateBuilder, SearchHit, SessionSearchScope

SESSION_SEARCH_LIMIT: Final[int] = 5
"""How many hits one session search returns at most. Conventional, not measured; no paging (D2)."""

SESSION_EXCERPT_CHARS: Final[int] = 1500
"""How many trailing characters of a session's settled record one excerpt carries at most (D3)."""


def past_session_predicate(character_id: int, current_session_id: int) -> ExtraPredicateBuilder:
    """The port's extra predicate for one character's findable past sessions (D1, R5).

    The returned builder takes the relation the port selects candidates from - the `sessions` table,
    possibly aliased - and answers the conjunction of three terms over that relation's own columns:
    `character_id` equals `character_id`, `id` is not `current_session_id`, and `archived_at` is
    null. A search therefore never crosses a character, never returns the session being composed in,
    and never returns an archived session; clearing `archived_at` makes a session findable again
    with no re-embed, because `024` keeps archived sessions' vectors current.

    No owner term: the port ANDs `user_id = :user_id` itself (R5, 025 D6). The builder reads nothing
    and executes nothing - it only assembles a clause.
    """

    def build(relation: FromClause) -> ColumnElement[bool]:
        # The three terms of D1, over the relation the port hands in rather than the `sessions`
        # table, so the clause binds to the FROM the candidate select reads from (025 U1). The
        # archive term is the session's own: a session whose *setup* is archived is still in scope.
        return and_(
            relation.c["character_id"] == character_id,
            relation.c["id"] != current_session_id,
            relation.c["archived_at"].is_(None),
        )

    return build


def search_sessions(
    connection: Connection,
    user_id: int,
    character_id: int,
    current_session_id: int,
    query_text: str,
    *,
    client_factory: LlmClientFactory = LlmClient,
    timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
) -> list[SearchHit]:
    """The owner's other, non-archived sessions of one character that match `query_text`, best first.

    The three ids come from the caller's own owner-scoped read - the tool scope - never from the
    assistant's arguments (D7). `current_session_id` is the session being composed in and is
    excluded (D1). `query_text` is the raw text: the port embeds it verbatim. At most
    `SESSION_SEARCH_LIMIT` hits are returned, in the port's rank order, exactly as the port built
    them - nothing is re-read, re-ranked, cut further or reshaped here. A session hit carries no
    snippet; turning its id into a block's header and excerpt is step `002`'s read.

    Synchronous, and it embeds through the port, so it must not run on a thread with a running event
    loop; an async caller hands it to a worker thread (D6). The port's errors propagate unchanged
    (`no_embedding_model`, `llm_unreachable`, `secret_ref_missing`); on every exit, raise included,
    an autobegun read transaction is rolled back so the connection has none open.
    """
    scope = SessionSearchScope(
        user_id=user_id,
        extra_predicate=past_session_predicate(character_id, current_session_id),
    )
    try:
        # The hits are returned as the port built them: same objects, same order, no further cut.
        # The session variant fixes the arms, so no flag is passed and no lexical form is built.
        return search(
            connection,
            scope,
            query_text,
            SESSION_SEARCH_LIMIT,
            client_factory=client_factory,
            timeout_seconds=timeout_seconds,
        )
    finally:
        # 027's own guarantee to the seam, on the error path too: never depend on the port's
        # rollback, because an exception may escape before or around it (D6, 025 D7).
        if connection.in_transaction():
            connection.rollback()


@dataclass(frozen=True)
class SessionExcerpt:
    """One matched past session as a result block needs it: its header fields and its excerpt (D3, D4).

    Everything a block is rendered from and nothing more. No persona text, no setup description, no
    user, character or setup id: the hydration is the only place a session's content is read, so what
    it leaves out can never reach the model through a result (D3). Step `003`'s formatter builds a
    block from one of these alone and re-reads nothing.
    """

    session_id: int
    """The matched session's own snowflake id - the port's hit id, carried through for correlation."""
    created_date: date
    """When the session was created, as a UTC calendar date: `created_at` read as UTC - a naive stored
    value taken as UTC - and reduced to its date, so a header's `<YYYY-MM-DD>` is this field's ISO
    form and the formatter does no time arithmetic and no parsing (D3)."""
    setup_name: str | None
    """The session's setup's name, whatever the setup's `archived_at` is (a name is not content - R6);
    `None` when the session has no setup, which the header renders as `no setup` (D3)."""
    excerpt: str
    """The tail of the session's settled record, already joined and already bounded here (D3) - never
    the composed text, and never longer than the marker plus `SESSION_EXCERPT_CHARS` characters. The
    empty string when the session has no settled entries; the formatter is what substitutes a body
    line for that case."""


def list_session_excerpts(
    connection: Connection, user_id: int, session_ids: Sequence[int]
) -> list[SessionExcerpt]:
    """The owner's sessions among `session_ids`, hydrated into result records in that same order (D4).

    `session_ids` is normally `search_sessions`' hit ids, best first, and the result is one record per
    id that is a session of `user_id`, in the sequence's own order - ranking lives in the sequence,
    never in this read. An id that is not the owner's session is dropped silently (defence in depth:
    the port scoped it already, R5), so the result may be shorter than the input but never longer and
    never reordered. An empty sequence answers `[]` and executes no statement at all.

    Each record's date comes from the session's `created_at`, its setup name from the setup it points
    at - joined only when `setup_id` is set, and matching the owner there too - and its excerpt from
    that session's `settled_entries` rows, which is the single definition of the settled record (R11)
    and gets no kind filter here, so a settled decision is part of the excerpt. The bound and its `…`
    marker are applied in this read, so an unbounded session text never leaves the service.

    One read for the whole list, or a small fixed number - never one per id or per entry. Reads only,
    writes nothing, and returns with no transaction open, on the raise as well (D4, D5).
    """
    if not session_ids:
        # An empty sequence is answered without touching the database at all: no statement, so no
        # transaction is autobegun either (D4).
        return []
    # Two statements for the whole list, whatever its length: the headers, then every session's
    # settled rows at once. Duplicate ids are collapsed for the `IN (...)` sets only - the records
    # themselves are rebuilt from `session_ids` below, so the input's own order and length decide.
    wanted = list(dict.fromkeys(session_ids))
    # `sessions.py:_session_select`'s established join shape: the owner travels inside the join
    # condition, so another user's setup can never label a session, and there is no `archived_at`
    # term on the setup - a name is not content (R5, R6). A null `setup_id` matches no `setups` row,
    # which is exactly "joined only when `setup_id` is set".
    label_join = (setups.c.id == sessions.c.setup_id) & (setups.c.user_id == user_id)
    header_statement = (
        select(sessions.c.id, sessions.c.created_at, setups.c.name)
        .select_from(sessions.outerjoin(setups, label_join))
        .where(sessions.c.user_id == user_id, sessions.c.id.in_(wanted))
    )
    # Through the `settled_entries` selectable, never raw `messages` (R11): zone and buried rows are
    # excluded structurally and settled decisions are included structurally. No kind filter is added
    # on top of it here, and no buried or zone term of this read's own.
    entry_columns = settled_entries.selected_columns
    headers: dict[int, tuple[date, str | None]] = {}
    texts: dict[int, list[str]] = {}
    # Both reads sit in the one guard, so the autobegun transaction ends on the normal return and on
    # a raise alike (D4, D5).
    with _reading(connection):
        for row in connection.execute(header_statement).all():
            raw_name = row.name
            headers[int(row.id)] = (
                _utc_date(str(row.created_at)),
                None if raw_name is None else str(raw_name),
            )
        texts.update({session_id: [] for session_id in headers})
        if headers:
            entry_rows = connection.execute(
                settled_entries.where(
                    entry_columns.user_id == user_id,
                    entry_columns.session_id.in_(list(headers)),
                ).order_by(entry_columns.session_id.asc(), entry_columns.id.asc())
            ).all()
            for entry_row in entry_rows:
                text = str(entry_row.text)
                # Empty texts are skipped, so they contribute no separator either.
                if text:
                    texts[int(entry_row.session_id)].append(text)
    # Input order, one record per id that was one of the owner's sessions; everything else is dropped
    # silently, the port having scoped the ids already (D4).
    return [
        SessionExcerpt(
            session_id=session_id,
            created_date=headers[session_id][0],
            setup_name=headers[session_id][1],
            excerpt=_bounded_excerpt("\n\n".join(texts[session_id])),
        )
        for session_id in session_ids
        if session_id in headers
    ]


@contextmanager
def _reading(connection: Connection) -> Iterator[None]:
    """A read on a Core connection autobegins; end it again when the caller had none open."""
    opened_here = not connection.in_transaction()
    try:
        yield
    finally:
        if opened_here and connection.in_transaction():
            connection.rollback()


def _utc_date(stored: str) -> date:
    """Stored ISO-8601 text as a UTC calendar date; a naive value is taken as UTC (D3).

    The project's established spelling (`llm_registry.py:_parse_time`, `users.py`), plus the date
    reduction this read owns - no helper for that step exists anywhere in `app/`.
    """
    value = datetime.fromisoformat(stored)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).date()


def _bounded_excerpt(joined: str) -> str:
    """`joined` unchanged, or its last `SESSION_EXCERPT_CHARS` characters behind the marker (D3)."""
    if len(joined) > SESSION_EXCERPT_CHARS:
        # U+2026 HORIZONTAL ELLIPSIS with no following space, then the tail. The cut is by characters
        # and may land mid-word; the marker is what shows the reader the excerpt was cut.
        return "…" + joined[-SESSION_EXCERPT_CHARS:]
    return joined
