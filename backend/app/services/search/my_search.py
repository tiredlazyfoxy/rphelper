"""My-search's own corpora — the per-kind cap, the read posture, characters and setups.

Feature `029`, step `001` (FEAT-017; UC-058; US-074, US-076). The roleplayer's own search box
reaches five kinds. Three of them (session, entry, memo) go through feature `025`'s hybrid
port; the two built here do **not**. `characters` and `setups` have no FTS table and no vector
table, they are small, and `context.md` U2 decides they are matched by an escaped,
case-insensitive substring `LIKE` outside the port instead — a recorded deviation from "every
surface goes through one port", not an oversight.

This step is the bottom layer and nothing else:

- **`MY_SEARCH_PER_KIND_LIMIT`** — the cap **each** group is held to, `20` (D2). It is what is
  passed as `limit` to every port call and to both searches below; it is never a budget for the
  whole result.
- **`_reading`** — the posture every 029 read runs inside (D6), replicated from
  `services/memos.py` rather than imported from it: the autobegun read transaction is rolled
  back on the normal return **and** on the raise, while a caller who opened one himself is left
  untouched.
- **`CharacterHit`, `SetupHit`** — the two frozen hit values. `archived` is already reduced to a
  boolean, and a setup's owning character's name is already joined in. Field order is the wire
  contract's, so step `003`'s response models can validate one of these through
  `from_attributes=True`.
- **`search_characters`, `search_setups`** — one owner-scoped read each, with `user_id` on every
  base table the statement names (R5), archived rows included and flagged (U3), ordered by
  `name` then `id` ascending (D2).

Step `002` extends this same module with `SessionHit`, `EntryHit`, `MemoHit`,
`MySearchResults`, the three hydration reads and `run_my_search`, and reuses the cap and
`_reading` from here.

Service layer only: no `fastapi`, no `starlette`, no `sqlite_vec` and nothing else HTTP-shaped
— the search package's own import scans assert it. Reads only; nothing here writes a row.
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final

from sqlalchemy import Connection, and_, or_, select

from app.db.schema import characters, memos, sessions, settled_entries, setups
from app.models.memos import MemoScope
from app.services.embedding import DEFAULT_EMBED_TIMEOUT_SECONDS
from app.services.llm.client import LlmClient
from app.services.llm_registry import LlmClientFactory
from app.services.search.hybrid import search
from app.services.search.ports import EntrySearchScope, MemoSearchScope, SearchHit, SessionSearchScope

MY_SEARCH_PER_KIND_LIMIT: Final[int] = 20
"""How many hits **one group** holds at most (D2). Per kind, not per search: the same number is
the `limit` of every port call and of both searches here, so five full groups answer 100 rows."""


@contextmanager
def _reading(connection: Connection) -> Iterator[None]:
    """A read on a Core connection autobegins; end it again when the caller had none open."""
    opened_here = not connection.in_transaction()
    try:
        yield
    finally:
        if opened_here and connection.in_transaction():
            connection.rollback()


@dataclass(frozen=True)
class CharacterHit:
    """One matched character, as my-search's character group holds it.

    No `user_id` and no timestamps: the owner is the caller's own and the row is a link target,
    not a listing. Field order is the wire contract's `{"id", "name", "archived"}`.
    """

    id: int
    """The character's snowflake id — the character page this row links to."""
    name: str
    """The character's name, exactly as stored."""
    archived: bool
    """True when the character's `archived_at` is not NULL; archived characters are returned (U3)."""


@dataclass(frozen=True)
class SetupHit:
    """One matched setup, as my-search's setup group holds it.

    Setups have no route of their own, so the owning character travels with the hit: `character_id`
    is the page this row links to and `character_name` is what the row reads as. Field order is the
    wire contract's `{"id", "name", "character_id", "character_name", "archived"}`.
    """

    id: int
    """The setup's snowflake id."""
    name: str
    """The setup's name, exactly as stored."""
    character_id: int
    """The owning character's snowflake id — the page this row links to (U4)."""
    character_name: str
    """The owning character's name, joined in by the same owner-scoped read."""
    archived: bool
    """True when the **setup's own** `archived_at` is not NULL — never its character's (U3)."""


def search_characters(
    connection: Connection,
    user_id: int,
    query_text: str,
    limit: int = MY_SEARCH_PER_KIND_LIMIT,
) -> list[CharacterHit]:
    """The owner's characters matching `query_text` by name or persona, in name order (U2, D2, D3).

    `query_text` is the raw text from the box. It is stripped of leading and trailing whitespace
    and matched as **one substring**, never split into words: a blank or whitespace-only query
    answers `[]` and **issues no SQL at all**. A character matches when its `name` **or** its
    `sheet` contains that substring case-insensitively, and appears **once** either way — the
    statement is a single table read with no join, so no de-duplication is needed. `%`, `_` and the
    escape character in the needle are escaped and the escape character is declared on the `LIKE`,
    so typed input can never act as a wildcard; the needle reaches SQL as a bound parameter.
    Case-insensitivity is SQLite `LIKE`'s own, i.e. ASCII letters only (D3, a known limitation).

    Ordered by `name` then `id` ascending and cut to `limit` rows (`characters` has no
    `updated_at`, hence name order — D2). Archived characters are included and come back with
    `archived` true (U3). `user_id` is in the `WHERE` clause, so another owner's character is
    absent rather than filtered afterwards (R5). Reads only, and leaves no transaction open on
    return or on raise (D6).
    """
    # D3's needle: the box's text with both ends stripped, matched as **one** substring and never
    # split into words. The blank case is answered before a statement is even built, so no SQL is
    # issued at all.
    needle = query_text.strip()
    if not needle:
        return []
    # `contains(..., autoescape=True)` escapes `%`, `_` and the escape character inside the bound
    # needle and declares that escape character on the `LIKE`, so typed input can never act as a
    # wildcard (D3). The case-insensitivity is SQLite's own `LIKE`, left at its default pragma -
    # ASCII letters only, a known limitation. No `archived_at` term: archived rows are returned (U3).
    statement = (
        select(characters.c.id, characters.c.name, characters.c.archived_at)
        .where(
            characters.c.user_id == user_id,
            or_(
                characters.c.name.contains(needle, autoescape=True),
                characters.c.sheet.contains(needle, autoescape=True),
            ),
        )
        .order_by(characters.c.name.asc(), characters.c.id.asc())
        .limit(limit)
    )
    with _reading(connection):
        rows = connection.execute(statement).all()
    return [
        CharacterHit(id=int(row.id), name=str(row.name), archived=row.archived_at is not None)
        for row in rows
    ]


def search_setups(
    connection: Connection,
    user_id: int,
    query_text: str,
    limit: int = MY_SEARCH_PER_KIND_LIMIT,
) -> list[SetupHit]:
    """The owner's setups matching `query_text` by name or description, in name order (U2, D2, D3).

    `search_characters`'s contract over `setups`, matching `name` **or** `description`: same
    stripping, same blank-query `[]` with no SQL, same escaped single-substring `LIKE` with the
    escape character declared, same `name` then `id` ordering and same `limit`.

    The owning character's name is hydrated by the same statement, through a join that carries its
    **own** `user_id` predicate as well, so every base table the read names is owner-scoped (R5).
    `archived` reports the **setup's** `archived_at`: an archived setup comes back true, and a
    working setup under an archived character comes back false (U3). Reads only, and leaves no
    transaction open on return or on raise (D6).
    """
    needle = query_text.strip()
    if not needle:
        return []
    # The owner travels inside the join condition as well as in the WHERE clause, so every base
    # table the statement names is owner-scoped and another owner's character can never label a
    # setup (R5). No `archived_at` term on either table: a setup under an archived character is
    # still returned, and `archived` below reports the setup's own flag (U3).
    owner_join = and_(characters.c.id == setups.c.character_id, characters.c.user_id == user_id)
    statement = (
        select(
            setups.c.id,
            setups.c.name,
            setups.c.character_id,
            characters.c.name.label("character_name"),
            setups.c.archived_at,
        )
        .select_from(setups.join(characters, owner_join))
        .where(
            setups.c.user_id == user_id,
            or_(
                setups.c.name.contains(needle, autoescape=True),
                setups.c.description.contains(needle, autoescape=True),
            ),
        )
        .order_by(setups.c.name.asc(), setups.c.id.asc())
        .limit(limit)
    )
    with _reading(connection):
        rows = connection.execute(statement).all()
    return [
        SetupHit(
            id=int(row.id),
            name=str(row.name),
            character_id=int(row.character_id),
            character_name=str(row.character_name),
            archived=row.archived_at is not None,
        )
        for row in rows
    ]


@dataclass(frozen=True)
class SessionHit:
    """One matched session, as my-search's session group holds it.

    A session has no title column: it is labelled by its character, its setup and when it started
    (`002.context.md`), so the label travels with the hit and the group needs no second read. Field
    order is the wire contract's `{"id", "character_name", "setup_name", "created_at", "archived"}`.
    """

    id: int
    """The session's snowflake id — the session page this row links to (U4)."""
    character_name: str
    """The owning character's name, joined in by the hydration read (D4)."""
    setup_name: str | None
    """The session's setup's name, or `None` when the session has no setup (D4)."""
    created_at: str
    """When the session was created, the stored fixed-width UTC text exactly as `sessions` holds it —
    no parsing and no reformatting here; the screen formats it."""
    archived: bool
    """True when the **session's own** `archived_at` is not NULL — never its character's and never its
    setup's. Archived sessions are returned and marked (U3)."""


@dataclass(frozen=True)
class EntryHit:
    """One matched settled entry, as my-search's entry group holds it.

    The row reads as a fragment of a session, so the session's label fields travel with it and the
    link lands on the session with the entry anchored (U4, D8). The text comes from the port's
    snippet and is never re-read here, so the whole entry body never leaves the service. Field order
    is the wire contract's `{"id", "session_id", "snippet", "character_name", "session_created_at"}`.
    """

    id: int
    """The message's snowflake id — the `entry=` landing param's value (D8)."""
    session_id: int
    """The owning session's snowflake id — the session page this row links to."""
    snippet: str
    """The port's plain-text snippet for this entry, carried through unchanged. Never the full entry
    text, and never markdown-rendered downstream (D7)."""
    character_name: str
    """The owning session's character's name, joined in by the hydration read (D4)."""
    session_created_at: str
    """The owning **session's** `created_at`, the stored fixed-width UTC text as held — not the
    message's own timestamp, which my-search never shows."""


@dataclass(frozen=True)
class MemoHit:
    """One matched note, as my-search's memo group holds it.

    A note has no title, so the row is a snippet plus a level (US-119). It is returned whatever its
    state: nothing in 029 filters on `is_enabled`, and the forced flag is named nowhere in this
    module at all (U2, R3). Field order is the wire contract's `{"id", "scope", "scope_id",
    "character_id", "snippet", "is_enabled"}`.
    """

    id: int
    """The memo's snowflake id."""
    scope: MemoScope
    """The note's level — one of `"user"`, `"character"`, `"setup"`, `"session"`: the port's own
    `memo_scope`, carried through."""
    scope_id: int | None
    """The level's target id, and **`None` for the `"user"` level**. The port hands back the *raw
    stored* `memos.scope_id`, which at the user level is the owner's own user id — a value the client
    has no use for — so the hydration reduces it to `None`, the way `services/memos.py`'s `to_memo`
    does. `None` here means the user level, never a missing read."""
    character_id: int | None
    """The character page this note routes to (U4): the note's own `scope_id` at the `"character"`
    level, the setup's `character_id` at the `"setup"` level (the only field the hydration's LEFT
    OUTER JOIN to `setups` exists for), and `None` at the `"user"` and `"session"` levels."""
    snippet: str
    """The port's plain-text snippet for this note, carried through unchanged — never the whole body,
    and never a title (US-119)."""
    is_enabled: bool
    """The note's stored `is_enabled`, read **only to report it** (US-137.AC-2): a disabled note is
    returned and the screen marks it disabled. It is never a predicate (US-137.AC-1, R3)."""


@dataclass(frozen=True)
class MySearchResults:
    """One whole my-search answer: the five groups, in UC-059's order and nothing else.

    The order of the fields **is** the contract (US-075.AC-1) — `characters`, `setups`, `sessions`,
    `entries`, `memos` — and step `003`'s response model declares its keys in the same order. Each
    list is capped at `MY_SEARCH_PER_KIND_LIMIT` independently and may be empty; there is no total,
    no paging cursor and no per-group "has more" flag. One of these is only ever built when every arm
    has succeeded: a failure propagates instead of producing a partially filled one (U1).
    """

    characters: list[CharacterHit]
    """The matched characters, by `name` then `id` ascending (D2)."""
    setups: list[SetupHit]
    """The matched setups, by `name` then `id` ascending (D2)."""
    sessions: list[SessionHit]
    """The matched sessions, in the port's own order (D2)."""
    entries: list[EntryHit]
    """The matched settled entries, in the port's own order (D2)."""
    memos: list[MemoHit]
    """The matched notes, in the port's own order (D2), whatever their state (U2)."""


def _hydrate_sessions(
    connection: Connection,
    user_id: int,
    hits: Sequence[SearchHit],
) -> list[SessionHit]:
    """The owner's sessions among `hits`, labelled, in the hits' own order (D4).

    `hits` is the port's session result, best first. One owner-scoped read labels them all:
    `sessions` inner-joined to `characters` for the character name and LEFT OUTER joined to `setups`
    for the setup name, with `user_id = :user_id` on **every** base table the statement names,
    inside the join conditions included, so another owner's character or setup can never label a
    session (R5). `archived` is the session's own `archived_at` reduced to a boolean (U3).

    Ranking lives in `hits` and nowhere else: the result is one `SessionHit` per hit whose id the read
    returned, in the sequence's own order — never re-sorted, never longer than `hits`. A hit whose id
    the read does not return (another owner's, or a row gone between the port call and this read) is
    **dropped silently**, not raised (D4). An empty `hits` answers `[]` and executes no statement at
    all. A session hit carries no snippet, so no text is read here.

    Reads only, and leaves no transaction open on return or on raise (D6).
    """
    # An empty port result executes no statement at all.
    if not hits:
        return []
    wanted = [hit.id for hit in hits]
    character_join = and_(characters.c.id == sessions.c.character_id, characters.c.user_id == user_id)
    # `sessions.py`'s established label join: a NULL `setup_id` matches no `setups` row, which is
    # exactly "joined only when the session has one", and the owner sits in the condition too (R5).
    setup_join = and_(setups.c.id == sessions.c.setup_id, setups.c.user_id == user_id)
    statement = (
        select(
            sessions.c.id,
            characters.c.name.label("character_name"),
            setups.c.name.label("setup_name"),
            sessions.c.created_at,
            sessions.c.archived_at,
        )
        .select_from(sessions.join(characters, character_join).outerjoin(setups, setup_join))
        .where(sessions.c.user_id == user_id, sessions.c.id.in_(wanted))
    )
    with _reading(connection):
        labelled = {int(row.id): row for row in connection.execute(statement).all()}
    group: list[SessionHit] = []
    # The hits' own order is the result's order; ranking lives in `hits` and is never recomputed.
    for hit in hits:
        row = labelled.get(hit.id)
        # Another owner's id, or a row gone since the port call: dropped silently, never raised (D4).
        if row is None:
            continue
        raw_setup_name = row.setup_name
        group.append(
            SessionHit(
                id=hit.id,
                character_name=str(row.character_name),
                setup_name=None if raw_setup_name is None else str(raw_setup_name),
                created_at=str(row.created_at),
                archived=row.archived_at is not None,
            )
        )
    return group


def _hydrate_entries(
    connection: Connection,
    user_id: int,
    hits: Sequence[SearchHit],
) -> list[EntryHit]:
    """The owner's settled entries among `hits`, labelled, in the hits' own order (D4, R11).

    `hits` is the port's entry result, best first; each hit carries the snippet and the `session_id`
    that travel straight through — the snippet is never recomputed and the entry's body is never
    read. One owner-scoped read supplies the rest: the **`settled_entries`** selectable (used as a
    subquery — never raw `messages`, so a current-zone row and a buried row are excluded
    structurally, R11) joined to `sessions` and on to `characters`, for the character name and the
    session's `created_at`, with `user_id = :user_id` on every base relation the statement names (R5).

    Same order and same dropping rule as `_hydrate_sessions`: the hits' order is kept, an id the read
    does not return is dropped silently, and an empty `hits` executes no statement. Reads only, and
    leaves no transaction open on return or on raise (D6).
    """
    if not hits:
        return []
    wanted = [hit.id for hit in hits]
    # `settled_entries` is a Core `select`, not a FROM object, so it enters the statement as a
    # subquery. The settled record is therefore the whole corpus structurally: a current-zone row
    # and a buried row cannot appear, and raw `messages` is never read (R11).
    entries = settled_entries.subquery()
    session_join = and_(sessions.c.id == entries.c.session_id, sessions.c.user_id == user_id)
    character_join = and_(characters.c.id == sessions.c.character_id, characters.c.user_id == user_id)
    statement = (
        select(
            entries.c.id,
            entries.c.session_id,
            characters.c.name.label("character_name"),
            sessions.c.created_at.label("session_created_at"),
        )
        .select_from(entries.join(sessions, session_join).join(characters, character_join))
        .where(entries.c.user_id == user_id, entries.c.id.in_(wanted))
    )
    with _reading(connection):
        labelled = {int(row.id): row for row in connection.execute(statement).all()}
    group: list[EntryHit] = []
    for hit in hits:
        row = labelled.get(hit.id)
        if row is None:
            continue
        group.append(
            EntryHit(
                id=hit.id,
                session_id=int(row.session_id),
                # The port's snippet travels through unchanged; the entry's body is never read here.
                snippet=hit.snippet or "",
                character_name=str(row.character_name),
                session_created_at=str(row.session_created_at),
            )
        )
    return group


def _hydrate_memos(
    connection: Connection,
    user_id: int,
    hits: Sequence[SearchHit],
) -> list[MemoHit]:
    """The owner's notes among `hits`, levelled and routed, in the hits' own order (D4).

    `hits` is the port's memo result, best first; each hit carries the snippet, the level
    (`memo_scope`) and the level's raw stored id (`memo_scope_id`). One owner-scoped read supplies the
    two fields the port does not know: `memos.is_enabled` (read **only to report it** — never a
    predicate, US-137.AC-1, R3) and, through a LEFT OUTER JOIN to `setups` on `memos.scope = 'setup'
    AND setups.id = memos.scope_id` carrying its own `setups.user_id = :user_id`, the `character_id` a
    setup-level note routes to. `memos.user_id = :user_id` scopes the read itself (R5). The read
    selects the enabled flag and never the forced one, which this module names nowhere.

    Two reductions are this function's own, and the port performs **neither**:

    - **`scope_id` becomes `None` at the `"user"` level.** The port returns the raw stored
      `memos.scope_id`, which for a user-level note is the owner's own user id; the hit must carry
      `None` there, exactly as `services/memos.py`'s `to_memo` does. Every other level keeps its id.
    - **`character_id` is derived from the level**: the note's own `scope_id` at `"character"`, the
      joined setup's `character_id` at `"setup"`, `None` at `"user"` and at `"session"` (U4).

    Same order and same dropping rule as `_hydrate_sessions`: the hits' order is kept, an id the read
    does not return is dropped silently, and an empty `hits` executes no statement. Reads only, and
    leaves no transaction open on return or on raise (D6).
    """
    if not hits:
        return []
    wanted = [hit.id for hit in hits]
    # The LEFT OUTER JOIN exists for exactly one field: the character a setup-level note routes to.
    # The level test sits in the join condition, so a note at any other level joins nothing, and the
    # joined table carries its own owner predicate (R5).
    setup_join = and_(
        memos.c.scope == "setup",
        setups.c.id == memos.c.scope_id,
        setups.c.user_id == user_id,
    )
    # `is_enabled` is selected to be reported and never to narrow (US-137.AC-1, R3); the module reads
    # no other flag of a note at all.
    statement = (
        select(memos.c.id, memos.c.is_enabled, setups.c.character_id.label("setup_character_id"))
        .select_from(memos.outerjoin(setups, setup_join))
        .where(memos.c.user_id == user_id, memos.c.id.in_(wanted))
    )
    with _reading(connection):
        read_rows = {int(row.id): row for row in connection.execute(statement).all()}
    group: list[MemoHit] = []
    for hit in hits:
        row = read_rows.get(hit.id)
        scope = hit.memo_scope
        # Dropped silently, never raised: an id the read does not return, and - a shape the port
        # does not produce for a memo hit - a hit carrying no level.
        if row is None or scope is None:
            continue
        character_id: int | None
        if scope == "character":
            character_id = hit.memo_scope_id
        elif scope == "setup":
            raw_character_id = row.setup_character_id
            character_id = None if raw_character_id is None else int(raw_character_id)
        else:
            character_id = None
        group.append(
            MemoHit(
                id=hit.id,
                scope=scope,
                # The port hands back the *raw stored* `scope_id`, which at the user level is the
                # owner's own user id; the hit carries `None` there, as `to_memo` does.
                scope_id=None if scope == "user" else hit.memo_scope_id,
                character_id=character_id,
                snippet=hit.snippet or "",
                is_enabled=bool(row.is_enabled),
            )
        )
    return group


def run_my_search(
    connection: Connection,
    user_id: int,
    query_text: str,
    *,
    client_factory: LlmClientFactory = LlmClient,
    timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
) -> MySearchResults:
    """One whole my-search: five groups for `query_text`, or the failure that stopped it (D1, D5, U1).

    `query_text` is the raw text from the box. **Blank after stripping** (empty or whitespace only)
    answers five empty groups having made no port call, constructed no client through
    `client_factory` and issued no SQL at all (D1). `client_factory` and `timeout_seconds` are
    keyword-only with the port's own defaults (024 D9), mirroring `search_memos` and
    `search_sessions`; the route passes the shared factory and the configured timeout.

    Otherwise the arms run in D5's order — the port's **session** scope, then its **memo** scope, then
    its **entry** scope, each built from `user_id` alone with **no extra predicate** (passing one is a
    defect: neither a note's state nor an archive flag may narrow an owner's own search — U2, U3,
    US-137.AC-1), each given `MY_SEARCH_PER_KIND_LIMIT` as `limit` and both keyword arguments; then
    `search_characters` and `search_setups`; then the three hydration reads; and only then the
    result. The two model-opening scopes go first, so a missing or unreachable model costs no other
    work. The query is therefore embedded **twice** per search, once per model-opening scope, because
    the port takes text rather than a vector (D5, a recorded cost).

    **Fail-whole (U1):** any exception from any arm — `NoEmbeddingModelError` (its
    `{"reason": "dimension_mismatch"}` detail included), `LlmUnreachableError`, the
    `secret_ref_missing` error, anything else — propagates **unchanged** to the single `DomainError`
    handler. No group is answered without the others, there is no lexical-only degrade, and no
    half-built `MySearchResults` is ever returned: with no usable embedding model my-search answers
    nothing, not even a character-name match.

    Reads only, writes nothing, and leaves the connection with no transaction open on the normal
    return **and** on the raise (D6) — 029's own guarantee to the route, independent of the port's.
    """
    # D1's blank case comes before every arm: no port call, no client constructed through
    # `client_factory`, no statement issued - five empty groups by construction.
    if not query_text.strip():
        return MySearchResults(characters=[], setups=[], sessions=[], entries=[], memos=[])
    # D5's order: the two model-opening scopes first, so a missing or unreachable model costs no
    # other work, then the entry scope. Each scope carries the owner and nothing else - **no** extra
    # predicate, so neither a note's state nor an archive flag narrows the owner's own search (U2,
    # U3, US-137.AC-1) - and each is given the per-kind cap and both keyword arguments. The raw
    # query text reaches the port, which embeds it verbatim.
    session_hits = search(
        connection,
        SessionSearchScope(user_id=user_id),
        query_text,
        MY_SEARCH_PER_KIND_LIMIT,
        client_factory=client_factory,
        timeout_seconds=timeout_seconds,
    )
    memo_hits = search(
        connection,
        MemoSearchScope(user_id=user_id),
        query_text,
        MY_SEARCH_PER_KIND_LIMIT,
        client_factory=client_factory,
        timeout_seconds=timeout_seconds,
    )
    entry_hits = search(
        connection,
        EntrySearchScope(user_id=user_id),
        query_text,
        MY_SEARCH_PER_KIND_LIMIT,
        client_factory=client_factory,
        timeout_seconds=timeout_seconds,
    )
    # Then this module's own two corpora (U2), and only then one hydration read per ported kind (D4).
    character_group = search_characters(connection, user_id, query_text, MY_SEARCH_PER_KIND_LIMIT)
    setup_group = search_setups(connection, user_id, query_text, MY_SEARCH_PER_KIND_LIMIT)
    session_group = _hydrate_sessions(connection, user_id, session_hits)
    entry_group = _hydrate_entries(connection, user_id, entry_hits)
    memo_group = _hydrate_memos(connection, user_id, memo_hits)
    # Built only once every arm has succeeded: anything that raised propagated unchanged instead,
    # so no partially filled result can exist (U1).
    return MySearchResults(
        characters=character_group,
        setups=setup_group,
        sessions=session_group,
        entries=entry_group,
        memos=memo_group,
    )
