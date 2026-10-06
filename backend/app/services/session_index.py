"""The session side of the search index — composed session text, refresh, fan-out ids.

Feature 024, step `003`. Five things live here and nothing else:

- **`compose_session_text`** builds D6's string for one session: the character's `sheet`,
  then the setup's `description` when `sessions.setup_id` is not null, then every
  `settled_entries` row's `text` in ascending `id`. Empty or whitespace-only parts are
  dropped, the rest are used **as stored** and joined with exactly `"\\n\\n"`. Persona and
  setup come first on purpose — embedding models truncate long input, and US-138.AC-2's
  "similar person" half must survive a long session.
- **`refresh_session_vectors`** is the strict refresh over a collection of sessions: it
  ensures the full-text half, composes every text, drops the vector row of every session
  **of the caller's** whose text came out empty, and — only when at least one text is
  non-empty — opens the designated model, ensures the vector tables at its dimension,
  embeds **all** the non-empty texts in **one** call (D1) and writes each session's vector.
- **`refresh_session_vector_degraded`** is the same work for one session with the
  record-keeping posture (D8): "unavailable" is caught and reported as incomplete
  coverage instead of propagating.
- **`session_ids_for_character` / `session_ids_for_setup`** are the two fan-out selections
  (D5, U4): every session of the owner's character, and every session of the owner whose
  `setup_id` is that setup. **Archived sessions are included** — there is no `archived_at`
  predicate anywhere in this module, because a restored session must not come back
  silently stale.

**Owner scope in SQL (R5).** Every read here — the session row, the character, the setup,
the entries, both fan-out selections — carries the caller's `user_id` in its own predicate.
A session that is not the caller's is therefore invisible: `compose_session_text` returns
`""` for it, and a refresh of its id writes no row **and deletes none** — the empty-text
delete is driven by its own owner-scoped read, because `delete_vector` takes no user id.

**Readers go through the views (R11).** Session text reads the `settled_entries` selectable
and never raw `messages`, so zone rows (US-115) and buried rows are structurally excluded
and settled decisions are structurally included (US-122.AC-2).

**Transactions.** A refresh takes a connection **already inside** the caller's
`with connection.begin():` block and opens none of its own: the relational write, the
composition, the embed call and the vector write are one transaction (U1). The two id
listers and `compose_session_text` are reads with no transaction requirement, and write
nothing.

**No staleness is persisted (U5).** A degraded refresh leaves any existing `session_vec`
row exactly as it was — stale — and records nothing anywhere. The remedy is the
administrator's whole-index rebuild (`fast/002`).

This module imports nothing from the web framework: the client factory and the timeout
arrive as keyword-only parameters with D9's defaults, and the routers supply them. Among
`app.services.` it imports **only** `app.services.embedding` (plus `app.db.search_tables`,
which is not a service); it issues no KNN query and no FTS `MATCH`, which belong to `025`.
"""

from collections.abc import Collection, Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, select

from app.db.schema import characters, sessions, settled_entries, setups
from app.db.search_tables import SESSION_VEC_TABLE, ensure_fts_tables, ensure_vector_tables
from app.errors import LlmUnreachableError, NoEmbeddingModelError
from app.services.embedding import (
    DEFAULT_EMBED_TIMEOUT_SECONDS,
    LlmClient,
    LlmClientFactory,
    delete_vector,
    embed_texts,
    open_embedding_model,
    write_vector,
)


def compose_session_text(connection: Connection, user_id: int, session_id: int) -> str:
    """Return D6's session text for the owner's session, or `""` when there is nothing.

    The parts, in this order: the character's `sheet`; the setup's `description`, **only**
    when the session's `setup_id` is not null; then the `text` of every `settled_entries`
    row of that session in ascending `id`, every kind included. A part that is empty or
    whitespace-only is dropped; the surviving parts are used **as stored**, untrimmed, and
    joined with exactly `"\\n\\n"`.

    Reads the session row with `user_id = :user` first, so a session that is not the
    caller's (or does not exist) yields `""` without the character, setup or entries ever
    being read (R5). An empty return is the signal that there is nothing to embed: the
    caller deletes the `session_vec` row and resolves no model (D6).

    Writes nothing, raises nothing for a missing session, and needs no open transaction —
    though it is normally called inside the caller's one.
    """
    entry_columns = settled_entries.selected_columns
    with _reading(connection):
        # The owner predicate sits on this first read, so a foreign or unknown id stops here
        # and the character, the setup and the entries are never read at all (R5).
        session_row = connection.execute(
            select(sessions.c.character_id, sessions.c.setup_id).where(
                sessions.c.id == session_id, sessions.c.user_id == user_id
            )
        ).first()
        if session_row is None:
            return ""
        # Persona first, then the setup, then the entries — D6's order, kept because an
        # embedding model truncates long input and the "similar person" half must survive.
        parts: list[str] = []
        character_row = connection.execute(
            select(characters.c.sheet).where(
                characters.c.id == session_row.character_id, characters.c.user_id == user_id
            )
        ).first()
        if character_row is not None:
            parts.append(character_row.sheet)
        # Only when `sessions.setup_id` is not null: a session with no setup has no setup part,
        # rather than an empty one (D6).
        if session_row.setup_id is not None:
            setup_row = connection.execute(
                select(setups.c.description).where(
                    setups.c.id == session_row.setup_id, setups.c.user_id == user_id
                )
            ).first()
            if setup_row is not None:
                parts.append(setup_row.description)
        # Through the `settled_entries` selectable, never raw `messages` (R11): zone and buried
        # rows are excluded structurally and settled decisions are included structurally.
        entry_rows = connection.execute(
            settled_entries.where(
                entry_columns.session_id == session_id, entry_columns.user_id == user_id
            ).order_by(entry_columns.id.asc())
        ).all()
        parts.extend(row.text for row in entry_rows)
    # Empty and whitespace-only parts are dropped; what survives is used as stored, untrimmed.
    return "\n\n".join(part for part in parts if part.strip())


def refresh_session_vectors(
    connection: Connection,
    user_id: int,
    session_ids: Collection[int],
    *,
    client_factory: LlmClientFactory = LlmClient,
    timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
) -> None:
    """Bring every named session's `session_vec` row up to date — the strict posture (D8).

    `connection` is **already inside** the caller's transaction. `session_ids` is any
    collection (a `list`, `tuple` or `set`); ids that are not the caller's contribute
    nothing. In order:

    1. ensure the two FTS tables (`001`), which back-fills them on an index-less database;
    2. compose every session's text;
    3. delete the `session_vec` row of every session **of the caller's** whose text is empty
       (D6) — the delete is driven by an owner-scoped read, so a session id that is not the
       caller's is never deleted; tolerated on a database that has no vector table at all;
    4. **only** when at least one text is non-empty, open the designated model (`002`) and
       ensure the vector tables at its `embedding_dim` (`001`);
    5. embed **all** the non-empty texts in **one** `embed_texts` call (D1) and write each
       session's vector.

    Opening the model before the vector ensure is deliberate: a missing designation then
    fails before any DDL. Ensuring before writing is equally deliberate: a dimension
    mismatch then fails before any vector write.

    `NoEmbeddingModelError` (missing or unusable designation, and dimension mismatch) and
    `LlmUnreachableError` propagate unchanged, so the caller's transaction rolls back and
    nothing — DDL included — is stored. An **empty** `session_ids` does nothing beyond the
    FTS ensure, opens no model and makes no embed call (N = 0); the same holds when every
    text is empty. Returns nothing.
    """
    # Step 1. The FTS half first, so even a refresh that needs no model (every text empty,
    # or N = 0) leaves an index-less database with its back-filled full-text tables (D2).
    ensure_fts_tables(connection)
    # Step 2. Compose every text before anything is written, so the deletes below and the one
    # embed call both work from the same snapshot.
    composed = [(session_id, compose_session_text(connection, user_id, session_id)) for session_id in session_ids]
    # Step 3. An empty text means no vector: drop the row and do not count the session towards
    # needing a model (D6). `delete_vector` tolerates a database with no vector table.
    pending: list[tuple[int, str]] = []
    empty_ids = {session_id for session_id, session_text in composed if not session_text}
    owned_empty_ids: set[int] = set()
    if empty_ids:
        # `delete_vector` takes no user id, so the owner term travels in this read's own WHERE
        # (R5): a session id that is not the caller's is not matched here and its `session_vec`
        # row is therefore left untouched. No `archived_at` predicate (U4) — an archived session
        # is still the owner's.
        with _reading(connection):
            owned_empty_ids = {
                int(row.id)
                for row in connection.execute(
                    select(sessions.c.id).where(
                        sessions.c.id.in_(empty_ids), sessions.c.user_id == user_id
                    )
                ).all()
            }
    for session_id, session_text in composed:
        if session_text:
            pending.append((session_id, session_text))
        elif session_id in owned_empty_ids:
            delete_vector(connection, SESSION_VEC_TABLE, session_id)
    if not pending:
        # No designation is resolved and no embed call is made — N = 0, or nothing to embed.
        return
    # Step 4. The model is opened **before** the vector ensure, so a missing or unusable
    # designation fails before any DDL; the ensure then runs before any write, so a dimension
    # mismatch fails before any vector row is touched.
    handle = open_embedding_model(
        connection, client_factory=client_factory, timeout_seconds=timeout_seconds
    )
    ensure_vector_tables(connection, handle.embedding_dim)
    # Step 5. One `embed_texts` call carries all N texts (D1), in `pending`'s order, which is
    # the order the id collection yielded them in.
    vectors = embed_texts(handle, [session_text for _, session_text in pending])
    for (session_id, _), vector in zip(pending, vectors, strict=True):
        write_vector(connection, SESSION_VEC_TABLE, session_id, vector)


def refresh_session_vector_degraded(
    connection: Connection,
    user_id: int,
    session_id: int,
    *,
    client_factory: LlmClientFactory = LlmClient,
    timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
) -> bool:
    """Refresh one session's vector, reporting instead of raising — **`True` = incomplete**.

    Runs `refresh_session_vectors` for that one session on the caller's already-open
    transaction and catches exactly `NoEmbeddingModelError` and `LlmUnreachableError`
    (D8, U3). On a catch it writes no vector, leaves any existing `session_vec` row as it
    was — stale, and recorded nowhere (U5) — and returns `True`. Otherwise it returns
    `False`, which includes the empty-text case: deleting the row of a session with no
    text is complete coverage, not degraded (D6).

    Every other exception propagates, `SecretRefError` (`secret_ref_missing`) included.
    **The caller's transaction stays usable after a catch**, and the relational write that
    preceded it commits: no SQL statement failed at either raise point, so no savepoint is
    needed and none is taken.

    The returned boolean is what the record-keeping routes put on the wire as
    `search_coverage_incomplete`.
    """
    try:
        refresh_session_vectors(
            connection,
            user_id,
            (session_id,),
            client_factory=client_factory,
            timeout_seconds=timeout_seconds,
        )
    except (NoEmbeddingModelError, LlmUnreachableError):
        # Exactly the two "unavailable" classes (D8, U3) — a `SecretRefError` is not one of
        # them and goes on propagating. Both raise points are Python-level, no SQL statement
        # failed, so the caller's transaction is intact here and needs no savepoint: the
        # relational write that preceded this still commits, and any existing `session_vec`
        # row is left exactly as it was (stale, recorded nowhere — U5).
        return True
    return False


def session_ids_for_character(connection: Connection, user_id: int, character_id: int) -> list[int]:
    """The ids of every session of the owner's character, **ascending**, archived included.

    One read scoped by `user_id` **and** `character_id` (R5), with **no `archived_at`
    predicate** (U4). The list is the persona fan-out's input, and the ascending order is
    what makes the one embed call's text order deterministic. Empty for another user's
    character, for an unknown id, and for a character with no session. Writes nothing and
    needs no open transaction.
    """
    with _reading(connection):
        # `user_id` and `character_id` both in this read's own predicate (R5), and deliberately
        # no `archived_at` predicate (U4): a restored session must not come back silently stale.
        rows = connection.execute(
            select(sessions.c.id)
            .where(sessions.c.user_id == user_id, sessions.c.character_id == character_id)
            .order_by(sessions.c.id.asc())
        ).all()
    return [int(row.id) for row in rows]


def session_ids_for_setup(connection: Connection, user_id: int, setup_id: int) -> list[int]:
    """The ids of every session of the owner whose `setup_id` is `setup_id`, **ascending**.

    One read scoped by `user_id` **and** `setup_id` (R5), with **no `archived_at`
    predicate** (U4); sessions with a null `setup_id` are excluded by the predicate itself.
    The list is the setup-description fan-out's input, ascending for the same determinism.
    Empty for another user's setup, for an unknown id, and for a setup no session uses.
    Writes nothing and needs no open transaction.
    """
    with _reading(connection):
        # `setup_id` equality excludes the null-setup sessions on its own; still no
        # `archived_at` predicate (U4), and the owner travels in this read's own WHERE (R5).
        rows = connection.execute(
            select(sessions.c.id)
            .where(sessions.c.user_id == user_id, sessions.c.setup_id == setup_id)
            .order_by(sessions.c.id.asc())
        ).all()
    return [int(row.id) for row in rows]


@contextmanager
def _reading(connection: Connection) -> Iterator[None]:
    """A read on a Core connection autobegins; end it again when the caller had none open.

    A refresh never uses this: it runs inside the caller's `begin()` block, where
    `opened_here` is false and nothing is rolled back anyway (U1).
    """
    opened_here = not connection.in_transaction()
    try:
        yield
    finally:
        if opened_here and connection.in_transaction():
            connection.rollback()
