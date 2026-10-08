"""`services/search/session_search.py` — feature 027, step 001 (DoD-1..13).

Every expected value comes from the **spec**, never from the implementation:
`docs/plans/027.session-search-tool/001.session-search-service.md` (Interface intent and
Definition of done), `001.context.md` (the port binding and the test-seeding notes) and the
feature `context.md` — **D1** (the extra predicate is
`character_id = :character_id AND id != :current_session_id AND archived_at IS NULL`, with no
`user_id` term of its own), **D2** (the result cap is `5`, no paging), **D3** (the excerpt
length is `1500`), **D5** (port errors propagate unchanged, and no transaction is left open on
either exit), **D6** (this module imports no `fastapi` and nothing from `app.services.tools`),
**R5** and the literals table (`result cap` = `5`, `excerpt length` = `1500`).

Bindings come from `## Skeleton` → "Step 001 — frozen interface (2026-10-05)" in `status.md`:

    SESSION_SEARCH_LIMIT: Final[int] = 5
    SESSION_EXCERPT_CHARS: Final[int] = 1500
    past_session_predicate(character_id, current_session_id) -> ExtraPredicateBuilder
    search_sessions(connection, user_id, character_id, current_session_id, query_text, *,
                    client_factory=LlmClient,
                    timeout_seconds=DEFAULT_EMBED_TIMEOUT_SECONDS) -> list[SearchHit]

A session hit's kind is `"session"`, its `id` is the session id, and `snippet`, `memo_scope`
and `memo_scope_id` are all `None` (025 step 001's frozen record). `SessionExcerpt` and
`list_session_excerpts` are step `002`'s and are not touched here.

How the expectations are derived
--------------------------------
Nothing here asks the code under test what the answer is.

* **The port is never mocked and nothing is monkeypatched.** `session_vec` is built only
  through 024's real path: a raw `llm_servers` + `models` designation at dimension 8 with
  `api_key_ref=None`, then `refresh_session_vectors` with `tests/llm_fakes.py`'s fake factory,
  so the persona, the setup description and the settled entries really are in the embedded
  text. The provider arrives through the frozen `client_factory=` seam.
* **Absences are proved with data that would match** (`context.md` cross-cutting
  constraints): every excluded session is given the **same** persona text on its character,
  the **same** setup description and the **same** settled entries in the same order as the
  included past session, so its composed text — and therefore its fake vector — is identical
  and sits at distance zero from the query. An absence is then the predicate's work, never a
  vector that missed.
* **The query is always a session's exact composed text**, read from 024's
  `compose_session_text` (a verified 024 contract, not the code under test). The fake embedder
  is deterministic, **not** semantic: equal text gives an equal vector, different text an
  unrelated one. So nothing here claims a paraphrase finds a session — that is `[manual/live]`
  in step `003` (`context.md` "What the fake embedder can prove — and what it cannot").
* **Rank is asserted only where it is defined.** A session and its excluded twin both sit at
  distance zero, so their relative order is undefined and DoD-4..7 assert presence and absence
  only. DoD-3 may assert rank because P is the sole zero-distance session in scope, and DoD-10
  may because R's text — and so R's vector — genuinely differs.
* The cap is asserted against `SESSION_SEARCH_LIMIT`, except in DoD-1, which pins the spec's
  literal `5`.

Each test name ends `__S027_001_DoD<n>` with the DoD item it covers.

Mechanics (`context.md` "Test conventions"): a real SQLite file per test through the shared
`db_engine` fixture (`tests/conftest.py` and `tests/llm_fakes.py` are untouched), raw inserts
only, ids above 2^60, two users A and B, and every other helper file-local.
"""

import ast
from collections.abc import Sequence
from pathlib import Path

import pytest
from sqlalchemy import ColumnElement, Connection, Engine, Table, select, text
from sqlalchemy.dialects import sqlite

from app.db import schema
from app.errors import LlmUnreachableError, NoEmbeddingModelError
from app.roles import Role
from app.services.search import session_search as session_search_module
from app.services.search.ports import SearchHit
from app.services.search.session_search import (
    SESSION_EXCERPT_CHARS,
    SESSION_SEARCH_LIMIT,
    past_session_predicate,
    search_sessions,
)
from app.services.session_index import compose_session_text, refresh_session_vectors
from tests.llm_fakes import FakeClientFactory, fake_factory, unreachable_factory

#: The seeded instant, in the project's fixed-width UTC text form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: The instant rows seeded already settled carry.
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"

#: Every id below is above 2^60 = 1152921504606846976 (snowflake-sized).
SNOWFLAKE_FLOOR = 2**60

#: The designated embedding width throughout; 8 is what 024 and 025 use.
DIMENSION = 8

#: D2's result cap, written out as the **spec's** literal (the literals table).
EXPECTED_RESULT_CAP = 5

#: D3's excerpt length, written out as the **spec's** literal (the literals table).
EXPECTED_EXCERPT_CHARS = 1500

# --- the texts the composed session text is built from (024's three sources) ----------------

#: The one persona shared by A's two characters and B's character, so twins compose equally.
PERSONA = "Kaelith the lamplighter, who keeps the tide-beacons of the drowned coast."

#: The one setup description shared by every twinned setup, for the same reason.
SETUP_DESCRIPTION = "The drowned observatory, three nights after the spring tide."

ENTRY_ONE = "Kaelith climbed the observatory stair and found the great lens cracked."
ENTRY_TWO = "((Agreed: the beacon stays lit until the tide turns.))"

#: Deliberately unlike `PERSONA` and unlike P's entries, so its vector is unrelated.
OTHER_ENTRY = "A ledger of salt prices, copied twice and never once read."

#: The session being composed in carries its own distinct text wherever it is not a twin.
CURRENT_ENTRY = "The current page, still being written tonight, unfinished."

#: DoD-10's R: entries that do not contain the persona text at all.
UNRELATED_ENTRY = "A cartwright argues about axle grease in a dry inland town."

USER_A = 1_270_000_000_000_000_001
USER_B = 1_270_000_000_000_000_002

CHAR_A1 = 1_270_000_000_000_000_101
CHAR_A2 = 1_270_000_000_000_000_102
CHAR_B1 = 1_270_000_000_000_000_103

SETUP_A1 = 1_270_000_000_000_000_151
SETUP_A2 = 1_270_000_000_000_000_152
SETUP_B1 = 1_270_000_000_000_000_153
SETUP_ARCHIVED = 1_270_000_000_000_000_154

SERVER_ID = 1_270_000_000_000_000_901
MODEL_ID = 1_270_000_000_000_000_902

#: Session ids are spaced by ten; a session's settled rows take `session_id + 1`, `+ 2`, …
SESSION_PAST = 1_270_000_000_000_002_001
SESSION_CURRENT = 1_270_000_000_000_002_011
SESSION_OTHER = 1_270_000_000_000_002_021
SESSION_TWIN_CHARACTER = 1_270_000_000_000_002_031
SESSION_TWIN_USER = 1_270_000_000_000_002_041
SESSION_ARCHIVED = 1_270_000_000_000_002_051
SESSION_WITH_ARCHIVED_SETUP = 1_270_000_000_000_002_061
SESSION_NO_SETUP_PAST = 1_270_000_000_000_002_071
SESSION_NO_SETUP_CURRENT = 1_270_000_000_000_002_081
SESSION_PERSONA_ONLY = 1_270_000_000_000_002_091
SESSION_UNRELATED = 1_270_000_000_000_002_101

#: DoD-11's seven in-scope past sessions.
CAP_SESSIONS = tuple(1_270_000_000_000_003_001 + 10 * index for index in range(7))

BASE_URL = "http://embedding.test:8080/v1"
MODEL_NAME = "the-designated-embedding-model"


# --- raw-insert helpers (file-local; no service is used to seed) -----------------------------


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


def _insert_user(engine: Engine, *, user_id: int, username: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash="not-a-real-hash",
                role=Role.ROLEPLAYER,
                is_enabled=True,
                rp_language=None,
                preferred_language=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_character(engine: Engine, *, character_id: int, user_id: int, name: str, sheet: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.characters.insert().values(
                id=character_id,
                user_id=user_id,
                name=name,
                sheet=sheet,
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_setup(
    engine: Engine,
    *,
    setup_id: int,
    user_id: int,
    character_id: int,
    name: str,
    description: str,
    archived_at: str | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.setups.insert().values(
                id=setup_id,
                user_id=user_id,
                character_id=character_id,
                name=name,
                description=description,
                archived_at=archived_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_session(
    engine: Engine,
    *,
    session_id: int,
    user_id: int = USER_A,
    character_id: int = CHAR_A1,
    setup_id: int | None = None,
    archived_at: str | None = None,
    created_at: str = TIMESTAMP,
) -> None:
    """Raw-insert one `sessions` row (`context.md` (A): no title, name or partner column)."""
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=setup_id,
                last_used_at=TIMESTAMP,
                archived_at=archived_at,
                created_at=created_at,
                updated_at=TIMESTAMP,
            )
        )


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    session_id: int,
    body: str,
    user_id: int = USER_A,
    role: str = "user",
    kind: str | None = None,
    related_to: int | None = None,
    settled_at: str | None = SEEDED_SETTLED_AT,
) -> None:
    """Raw-insert one `messages` row; `settled_at` set and `related_to` null is a record row."""
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=message_id,
                user_id=user_id,
                session_id=session_id,
                role=role,
                kind=kind,
                text=body,
                related_to=related_to,
                settled_at=settled_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _seed_session(
    engine: Engine,
    *,
    session_id: int,
    entries: Sequence[str] = (),
    user_id: int = USER_A,
    character_id: int = CHAR_A1,
    setup_id: int | None = None,
    archived_at: str | None = None,
    created_at: str = TIMESTAMP,
) -> None:
    """One session plus its settled entries, in the given order (ascending message id)."""
    _insert_session(
        engine,
        session_id=session_id,
        user_id=user_id,
        character_id=character_id,
        setup_id=setup_id,
        archived_at=archived_at,
        created_at=created_at,
    )
    for offset, body in enumerate(entries, start=1):
        _insert_message(
            engine,
            message_id=session_id + offset,
            session_id=session_id,
            body=body,
            user_id=user_id,
        )


def _seed_designation(engine: Engine, *, dimension: int = DIMENSION) -> None:
    """Raw-insert one server and one enabled, designated embedding model — no service used."""
    with engine.begin() as connection:
        connection.execute(
            _servers().insert().values(
                id=SERVER_ID,
                name="the embedding server",
                kind="llamaswap",
                base_url=BASE_URL,
                api_key_ref=None,
                last_test_at=None,
                last_test_ok=None,
                last_test_error=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )
        connection.execute(
            _models().insert().values(
                id=MODEL_ID,
                server_id=SERVER_ID,
                model_name=MODEL_NAME,
                is_enabled=True,
                is_embedding_designated=True,
                embedding_dim=dimension,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _remove_designation(engine: Engine) -> None:
    """Undesignate every model, leaving the vectors already written in place (DoD-12)."""
    with engine.begin() as connection:
        connection.execute(_models().update().values(is_embedding_designated=False))


def _seed_vectors(engine: Engine, owned: Sequence[tuple[int, int]]) -> None:
    """Build `session_vec` through 024's real path for each `(user_id, session_id)` pair."""
    _seed_designation(engine)
    factory = fake_factory(DIMENSION)
    with engine.begin() as connection:
        for user_id, session_id in owned:
            refresh_session_vectors(connection, user_id, [session_id], client_factory=factory)


def _compose(engine: Engine, session_id: int, *, user_id: int = USER_A) -> str:
    """024's composed text for one session — the only expected value read from other code."""
    with engine.connect() as connection:
        return compose_session_text(connection, user_id, session_id)


def _vector_row_count(engine: Engine) -> int:
    """A file-local `session_vec` probe, so "the index holds a match" needs no app code."""
    with engine.connect() as connection:
        return int(connection.execute(text("SELECT count(*) FROM session_vec")).scalar_one())


def _clear_archived_at(engine: Engine, session_id: int) -> None:
    """DoD-7's restore: a raw update of `archived_at` only, with no re-embed."""
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.update().where(schema.sessions.c.id == session_id).values(archived_at=None)
        )


def _run(
    engine: Engine,
    *,
    query_text: str,
    current_session_id: int,
    character_id: int = CHAR_A1,
    user_id: int = USER_A,
    factory: FakeClientFactory | None = None,
) -> list[SearchHit]:
    with engine.connect() as connection:
        return search_sessions(
            connection,
            user_id=user_id,
            character_id=character_id,
            current_session_id=current_session_id,
            query_text=query_text,
            client_factory=factory if factory is not None else fake_factory(DIMENSION),
        )


def _ids(hits: Sequence[SearchHit]) -> list[int]:
    return [hit.id for hit in hits]


def _assert_no_open_transaction(connection: Connection) -> None:
    assert not connection.in_transaction()
    transaction = connection.begin()
    transaction.rollback()


# --- fixtures -------------------------------------------------------------------------------


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two users, three characters sharing one persona, and four setups sharing one description.

    Sessions are seeded per test. No virtual table and no designated model: `create_all` leaves
    the search tables absent and designates nothing, so each test opts into what it needs.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="aster")
    _insert_user(db_engine, user_id=USER_B, username="briar")
    _insert_character(db_engine, character_id=CHAR_A1, user_id=USER_A, name="Kaelith", sheet=PERSONA)
    _insert_character(db_engine, character_id=CHAR_A2, user_id=USER_A, name="Kaelith again", sheet=PERSONA)
    _insert_character(db_engine, character_id=CHAR_B1, user_id=USER_B, name="Kaelith of B", sheet=PERSONA)
    _insert_setup(
        db_engine,
        setup_id=SETUP_A1,
        user_id=USER_A,
        character_id=CHAR_A1,
        name="the observatory",
        description=SETUP_DESCRIPTION,
    )
    _insert_setup(
        db_engine,
        setup_id=SETUP_A2,
        user_id=USER_A,
        character_id=CHAR_A2,
        name="the twin observatory",
        description=SETUP_DESCRIPTION,
    )
    _insert_setup(
        db_engine,
        setup_id=SETUP_B1,
        user_id=USER_B,
        character_id=CHAR_B1,
        name="B's observatory",
        description=SETUP_DESCRIPTION,
    )
    _insert_setup(
        db_engine,
        setup_id=SETUP_ARCHIVED,
        user_id=USER_A,
        character_id=CHAR_A1,
        name="the shuttered observatory",
        description=SETUP_DESCRIPTION,
        archived_at=TIMESTAMP,
    )
    return db_engine


# --- DoD-1: the two constants (D2, D3, the literals table) ----------------------------------


def test_the_result_cap_and_excerpt_length_constants__S027_001_DoD1() -> None:
    """D2 and D3: the cap is a fixed `5` and the excerpt bound a fixed `1500` characters."""
    assert SESSION_SEARCH_LIMIT == EXPECTED_RESULT_CAP
    assert SESSION_EXCERPT_CHARS == EXPECTED_EXCERPT_CHARS


# --- DoD-2: the predicate's compiled text and its semantics (D1) ----------------------------


def _predicate_clause() -> ColumnElement[bool]:
    """D1's builder, applied to the `sessions` table — the relation the port passes for a session."""
    builder = past_session_predicate(character_id=CHAR_A1, current_session_id=SESSION_CURRENT)
    return builder(schema.sessions)


def test_the_predicate_compiles_to_the_three_conjoined_terms__S027_001_DoD2() -> None:
    """D1: `character_id` names the character, `id` names the current session, `archived_at` is
    tested against null, and the three are conjoined.

    Only what D1 specifies is asserted: the columns, the two literal ids and the conjunction. A
    null test and an inequality each have several valid spellings, so the exact operator text is
    left to the semantic test below.
    """
    compiled = str(
        _predicate_clause().compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "character_id" in compiled
    assert str(CHAR_A1) in compiled
    assert str(SESSION_CURRENT) in compiled
    assert "archived_at" in compiled
    assert "NULL" in compiled
    assert compiled.count(" AND ") >= 2


def test_the_predicate_keeps_only_the_characters_other_unarchived_sessions__S027_001_DoD2(
    engine: Engine,
) -> None:
    """D1: each of the three terms does its work, and they are ANDed, not ORed.

    The predicate carries no `user_id` term of its own — the port ANDs that — so this selects
    with the clause alone.
    """
    _seed_session(engine, session_id=SESSION_PAST, character_id=CHAR_A1, setup_id=SETUP_A1)
    _seed_session(engine, session_id=SESSION_CURRENT, character_id=CHAR_A1, setup_id=SETUP_A1)
    _seed_session(engine, session_id=SESSION_TWIN_CHARACTER, character_id=CHAR_A2, setup_id=SETUP_A2)
    _seed_session(
        engine,
        session_id=SESSION_ARCHIVED,
        character_id=CHAR_A1,
        setup_id=SETUP_A1,
        archived_at=TIMESTAMP,
    )

    with engine.connect() as connection:
        rows = connection.execute(select(schema.sessions.c.id).where(_predicate_clause())).all()

    assert {row.id for row in rows} == {SESSION_PAST}


# --- DoD-3: found, three sources (US-067.AC-1 mechanism, US-138.AC-1, UC-053) ---------------


def test_a_past_session_is_the_first_hit_for_its_composed_text__S027_001_DoD3(engine: Engine) -> None:
    """P's representation carries the persona, the setup description and the settled entries, and
    a query equal to that text ranks P first.

    P is the **sole** zero-distance session in scope — the current session is out of scope and
    the other past session's text differs — so the rank is defined here.
    """
    _seed_session(engine, session_id=SESSION_PAST, setup_id=SETUP_A1, entries=(ENTRY_ONE, ENTRY_TWO))
    _seed_session(engine, session_id=SESSION_OTHER, setup_id=None, entries=(OTHER_ENTRY,))
    _seed_session(engine, session_id=SESSION_CURRENT, setup_id=None, entries=(CURRENT_ENTRY,))
    _seed_vectors(
        engine,
        [(USER_A, SESSION_PAST), (USER_A, SESSION_OTHER), (USER_A, SESSION_CURRENT)],
    )
    query = _compose(engine, SESSION_PAST)
    assert PERSONA in query
    assert SETUP_DESCRIPTION in query
    assert ENTRY_ONE in query
    assert ENTRY_TWO in query

    hits = _run(engine, query_text=query, current_session_id=SESSION_CURRENT)

    assert hits[0].id == SESSION_PAST
    assert hits[0].kind == "session"
    assert hits[0].snippet is None
    assert hits[0].memo_scope is None
    assert hits[0].memo_scope_id is None


# --- DoD-4: another character, as an absence (US-069.AC-1, UC-054, R5) ----------------------


def test_another_characters_identical_session_is_absent__S027_001_DoD4(engine: Engine) -> None:
    """R5: the twin under A's second character has the same composed text, hence the same vector
    at distance zero, and is still absent. P is present.

    No rank is asserted between P and the twin: both sit at distance zero, so their order is
    undefined (`001.context.md` "Ties").
    """
    _seed_session(engine, session_id=SESSION_PAST, setup_id=SETUP_A1, entries=(ENTRY_ONE, ENTRY_TWO))
    _seed_session(
        engine,
        session_id=SESSION_TWIN_CHARACTER,
        character_id=CHAR_A2,
        setup_id=SETUP_A2,
        entries=(ENTRY_ONE, ENTRY_TWO),
    )
    _seed_session(engine, session_id=SESSION_CURRENT, setup_id=None, entries=(CURRENT_ENTRY,))
    _seed_vectors(
        engine,
        [(USER_A, SESSION_PAST), (USER_A, SESSION_TWIN_CHARACTER), (USER_A, SESSION_CURRENT)],
    )
    query = _compose(engine, SESSION_PAST)
    assert _compose(engine, SESSION_TWIN_CHARACTER) == query

    hits = _run(engine, query_text=query, current_session_id=SESSION_CURRENT)

    assert SESSION_PAST in _ids(hits)
    assert SESSION_TWIN_CHARACTER not in _ids(hits)


# --- DoD-5: another user, as an absence (US-069.AC-2, UC-054, R5) ---------------------------


def test_another_users_identical_session_is_absent__S027_001_DoD5(engine: Engine) -> None:
    """R5: B owns a character with A's persona and a session composing to exactly P's text; it is
    absent from A's results. P is present.

    B cannot hold a session under A's character id — the character FK forbids it — so B's own
    character stands in, and the owner predicate is what must exclude it.
    """
    _seed_session(engine, session_id=SESSION_PAST, setup_id=SETUP_A1, entries=(ENTRY_ONE, ENTRY_TWO))
    _seed_session(
        engine,
        session_id=SESSION_TWIN_USER,
        user_id=USER_B,
        character_id=CHAR_B1,
        setup_id=SETUP_B1,
        entries=(ENTRY_ONE, ENTRY_TWO),
    )
    _seed_session(engine, session_id=SESSION_CURRENT, setup_id=None, entries=(CURRENT_ENTRY,))
    _seed_vectors(
        engine,
        [(USER_A, SESSION_PAST), (USER_B, SESSION_TWIN_USER), (USER_A, SESSION_CURRENT)],
    )
    query = _compose(engine, SESSION_PAST)
    assert _compose(engine, SESSION_TWIN_USER, user_id=USER_B) == query

    hits = _run(engine, query_text=query, current_session_id=SESSION_CURRENT)

    assert SESSION_PAST in _ids(hits)
    assert SESSION_TWIN_USER not in _ids(hits)


# --- DoD-6: the current session, as an absence (D1) -----------------------------------------


def test_the_current_session_is_absent_even_when_identical__S027_001_DoD6(engine: Engine) -> None:
    """D1: the session being composed in is never a result, though its composed text — and so its
    vector — equals P's exactly. P is present."""
    _seed_session(engine, session_id=SESSION_PAST, setup_id=SETUP_A1, entries=(ENTRY_ONE, ENTRY_TWO))
    _seed_session(engine, session_id=SESSION_CURRENT, setup_id=SETUP_A1, entries=(ENTRY_ONE, ENTRY_TWO))
    _seed_vectors(engine, [(USER_A, SESSION_PAST), (USER_A, SESSION_CURRENT)])
    query = _compose(engine, SESSION_PAST)
    assert _compose(engine, SESSION_CURRENT) == query

    hits = _run(engine, query_text=query, current_session_id=SESSION_CURRENT)

    assert SESSION_PAST in _ids(hits)
    assert SESSION_CURRENT not in _ids(hits)


# --- DoD-7: archived, as a reversible absence (D1) ------------------------------------------


def test_an_archived_session_is_absent_until_it_is_restored__S027_001_DoD7(engine: Engine) -> None:
    """D1: an archived past session with P's exact composed text is absent; clearing `archived_at`
    makes it findable again with **no** re-embed, because 024 embeds archived sessions too."""
    _seed_session(engine, session_id=SESSION_PAST, setup_id=SETUP_A1, entries=(ENTRY_ONE, ENTRY_TWO))
    _seed_session(
        engine,
        session_id=SESSION_ARCHIVED,
        setup_id=SETUP_A1,
        entries=(ENTRY_ONE, ENTRY_TWO),
        archived_at=TIMESTAMP,
    )
    _seed_session(engine, session_id=SESSION_CURRENT, setup_id=None, entries=(CURRENT_ENTRY,))
    _seed_vectors(
        engine,
        [(USER_A, SESSION_PAST), (USER_A, SESSION_ARCHIVED), (USER_A, SESSION_CURRENT)],
    )
    query = _compose(engine, SESSION_PAST)
    assert _compose(engine, SESSION_ARCHIVED) == query

    before = _run(engine, query_text=query, current_session_id=SESSION_CURRENT)
    assert SESSION_PAST in _ids(before)
    assert SESSION_ARCHIVED not in _ids(before)

    _clear_archived_at(engine, SESSION_ARCHIVED)
    after = _run(engine, query_text=query, current_session_id=SESSION_CURRENT)

    assert SESSION_ARCHIVED in _ids(after)


# --- DoD-8: an archived setup does not hide its session (D1) --------------------------------


def test_a_session_whose_setup_is_archived_is_returned__S027_001_DoD8(engine: Engine) -> None:
    """D1: the archive predicate is on the **session** only, so a working session under an
    archived setup is still searchable."""
    _seed_session(
        engine,
        session_id=SESSION_WITH_ARCHIVED_SETUP,
        setup_id=SETUP_ARCHIVED,
        entries=(ENTRY_ONE, ENTRY_TWO),
    )
    _seed_session(engine, session_id=SESSION_CURRENT, setup_id=None, entries=(CURRENT_ENTRY,))
    _seed_vectors(engine, [(USER_A, SESSION_WITH_ARCHIVED_SETUP), (USER_A, SESSION_CURRENT)])
    query = _compose(engine, SESSION_WITH_ARCHIVED_SETUP)

    hits = _run(engine, query_text=query, current_session_id=SESSION_CURRENT)

    assert SESSION_WITH_ARCHIVED_SETUP in _ids(hits)


# --- DoD-9: no setup, no partner field (US-068.AC-1, UC-053 postcondition) ------------------


def test_a_setupless_past_session_is_found_from_a_setupless_current_one__S027_001_DoD9(
    engine: Engine,
) -> None:
    """US-068.AC-1: with neither session carrying a setup, the search raises nothing and returns
    the past session for a query equal to its composed text."""
    _seed_session(
        engine, session_id=SESSION_NO_SETUP_PAST, setup_id=None, entries=(ENTRY_ONE, ENTRY_TWO)
    )
    _seed_session(engine, session_id=SESSION_NO_SETUP_CURRENT, setup_id=None, entries=(CURRENT_ENTRY,))
    _seed_vectors(engine, [(USER_A, SESSION_NO_SETUP_PAST), (USER_A, SESSION_NO_SETUP_CURRENT)])
    query = _compose(engine, SESSION_NO_SETUP_PAST)
    assert SETUP_DESCRIPTION not in query

    hits = _run(engine, query_text=query, current_session_id=SESSION_NO_SETUP_CURRENT)

    assert SESSION_NO_SETUP_PAST in _ids(hits)


def test_sessions_carry_no_partner_column_to_search_on__S027_001_DoD9() -> None:
    """`context.md` (A): `sessions` has no partner column, so nothing in the search can rely on
    one — US-068.AC-1's "no partner field" is a property of the schema."""
    column_names = set(schema.sessions.c.keys())

    assert {name for name in column_names if "partner" in name} == set()


# --- DoD-10: the persona is part of the representation (US-138.AC-2 mechanism) --------------


def test_a_session_with_no_entries_is_found_by_its_persona__S027_001_DoD10(engine: Engine) -> None:
    """Q has no setup and no settled entries, so its composed text is the persona alone. With the
    persona as the query Q comes back, and ahead of R, whose entries — and so whose vector —
    genuinely differ.

    Q holds no entry text at all, so being found proves its vector carries the persona. This is
    the mechanism only: it claims **no** paraphrase matching (`context.md` "What the fake
    embedder can prove — and what it cannot").
    """
    _seed_session(engine, session_id=SESSION_PERSONA_ONLY, setup_id=None, entries=())
    _seed_session(engine, session_id=SESSION_UNRELATED, setup_id=None, entries=(UNRELATED_ENTRY,))
    _seed_session(engine, session_id=SESSION_CURRENT, setup_id=SETUP_A1, entries=(CURRENT_ENTRY,))
    _seed_vectors(
        engine,
        [(USER_A, SESSION_PERSONA_ONLY), (USER_A, SESSION_UNRELATED), (USER_A, SESSION_CURRENT)],
    )
    query = _compose(engine, SESSION_PERSONA_ONLY)
    assert query == PERSONA
    assert UNRELATED_ENTRY not in query

    hits = _run(engine, query_text=query, current_session_id=SESSION_CURRENT)
    returned = _ids(hits)

    assert SESSION_PERSONA_ONLY in returned
    assert SESSION_UNRELATED in returned
    assert returned.index(SESSION_PERSONA_ONLY) < returned.index(SESSION_UNRELATED)


# --- DoD-11: the cap (D2) -------------------------------------------------------------------


def test_seven_in_scope_sessions_yield_exactly_the_capped_number__S027_001_DoD11(engine: Engine) -> None:
    """D2: seven past sessions of the character all carry vectors, and exactly
    `SESSION_SEARCH_LIMIT` hits come back, all of them from those seven."""
    for index, session_id in enumerate(CAP_SESSIONS):
        _seed_session(
            engine,
            session_id=session_id,
            setup_id=SETUP_A1,
            entries=(f"{ENTRY_ONE} The {index}th night of the watch.",),
        )
    _seed_session(engine, session_id=SESSION_CURRENT, setup_id=None, entries=(CURRENT_ENTRY,))
    _seed_vectors(
        engine,
        [(USER_A, session_id) for session_id in CAP_SESSIONS] + [(USER_A, SESSION_CURRENT)],
    )
    query = _compose(engine, CAP_SESSIONS[0])

    hits = _run(engine, query_text=query, current_session_id=SESSION_CURRENT)
    returned = _ids(hits)

    assert len(returned) == SESSION_SEARCH_LIMIT
    assert set(returned) <= set(CAP_SESSIONS)


# --- DoD-12: errors propagate, no transaction left open (D5) --------------------------------


def _seed_one_reachable_past_session(engine: Engine) -> str:
    """P plus a distinct current session, both embedded while a model is designated."""
    _seed_session(engine, session_id=SESSION_PAST, setup_id=SETUP_A1, entries=(ENTRY_ONE, ENTRY_TWO))
    _seed_session(engine, session_id=SESSION_CURRENT, setup_id=None, entries=(CURRENT_ENTRY,))
    _seed_vectors(engine, [(USER_A, SESSION_PAST), (USER_A, SESSION_CURRENT)])
    return _compose(engine, SESSION_PAST)


def test_no_designated_model_raises_no_embedding_model__S027_001_DoD12(engine: Engine) -> None:
    """D5: the port's error propagates unchanged, even though `session_vec` holds the match — the
    vectors were written while a model was designated, and the designation was then removed."""
    query = _seed_one_reachable_past_session(engine)
    _remove_designation(engine)
    assert _vector_row_count(engine) >= 1

    with engine.connect() as connection:
        with pytest.raises(NoEmbeddingModelError):
            search_sessions(
                connection,
                user_id=USER_A,
                character_id=CHAR_A1,
                current_session_id=SESSION_CURRENT,
                query_text=query,
                client_factory=fake_factory(DIMENSION),
            )

        _assert_no_open_transaction(connection)


def test_an_unreachable_provider_raises_llm_unreachable__S027_001_DoD12(engine: Engine) -> None:
    """D5: the scripted fake's `LlmUnreachableError` reaches the caller unchanged."""
    query = _seed_one_reachable_past_session(engine)

    with engine.connect() as connection:
        with pytest.raises(LlmUnreachableError):
            search_sessions(
                connection,
                user_id=USER_A,
                character_id=CHAR_A1,
                current_session_id=SESSION_CURRENT,
                query_text=query,
                client_factory=unreachable_factory(DIMENSION),
            )

        _assert_no_open_transaction(connection)


def test_a_successful_search_leaves_no_transaction_in_progress__S027_001_DoD12(engine: Engine) -> None:
    """D5: the guarantee holds on the ordinary exit too, not only on a raise."""
    query = _seed_one_reachable_past_session(engine)

    with engine.connect() as connection:
        hits = search_sessions(
            connection,
            user_id=USER_A,
            character_id=CHAR_A1,
            current_session_id=SESSION_CURRENT,
            query_text=query,
            client_factory=fake_factory(DIMENSION),
        )

        assert _ids(hits) == [SESSION_PAST]
        _assert_no_open_transaction(connection)


# --- DoD-13: the module's imports (D6) ------------------------------------------------------


def _imported_names() -> set[str]:
    """Every module named by an import in `session_search.py`'s source, read as text."""
    module_file = session_search_module.__file__
    assert module_file is not None
    names: set[str] = set()
    for node in ast.walk(ast.parse(Path(module_file).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_the_session_search_module_imports_no_web_framework__S027_001_DoD13() -> None:
    """D6: a service imports no web framework."""
    offenders = {name for name in _imported_names() if name.split(".")[0] in {"fastapi", "starlette"}}

    assert offenders == set()


def test_the_session_search_module_imports_nothing_from_the_tools_package__S027_001_DoD13() -> None:
    """D6: this module knows nothing of tools; the dependency runs the other way."""
    offenders = {name for name in _imported_names() if name.startswith("app.services.tools")}

    assert offenders == set()
