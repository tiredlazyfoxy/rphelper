"""The reusable memo-chain clause — feature 026, step 001 (DoD-1, DoD-2, DoD-3).

Every expected value comes from the **spec**, never from the implementation:
`docs/plans/026.memo-search-tool/001.chain-clause-and-memo-search.md` (Interface intent and
Definition of done), `001.context.md` (the touch-site notes and the seeding notes) and the
feature `context.md` — **D2** (the chain has one home: the OR-disjunction of
`(scope = <level> AND scope_id = <level id>)` over the levels that exist, the setup term
omitted when the setup id is none, the user level's stored id being the user id) and **R2**.

Bindings come from `## Skeleton` → "Step 001 — frozen interface" in `status.md`:

    chain_clause(relation, user_id, character_id, setup_id, session_id) -> ColumnElement[bool]
    resolve_chain(connection, user_id, session_id) -> list[MemoChainLevel]

`chain_clause` is pure — it reads nothing and executes nothing — so DoD-1 compiles it with
`literal_binds` against SQLite's dialect and inspects the text, while DoD-2 runs it as a
filter over seeded rows. DoD-3 is `resolve_chain`'s unchanged behaviour, covered **here** with
new tests: `backend/tests/test_memo_chain_service.py` is 015's and is deliberately not edited.

Each test name ends `__S026_001_DoD<n>` with the DoD item it covers.

Mechanics (`context.md` "Test conventions"):
- a real SQLite file per test through the shared `db_engine` fixture (`tests/conftest.py` is
  untouched) plus `schema.metadata.create_all`;
- every row is a **raw insert** with an id above 2^60, and two users A and B always exist;
- every helper and constant here is file-local.
"""

import re

import pytest
from sqlalchemy import ColumnElement, Engine, select
from sqlalchemy.dialects import sqlite

from app.db import schema
from app.roles import Role
from app.services.memo_chain import chain_clause, resolve_chain

#: The seeded instant, in the project's fixed-width UTC text form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: Every id below is above 2^60 = 1152921504606846976 (snowflake-sized).
SNOWFLAKE_FLOOR = 2**60

USER_A = 1_600_000_000_000_000_001
USER_B = 1_600_000_000_000_000_002

CHARACTER_A1 = 1_600_000_000_000_000_101
CHARACTER_A2 = 1_600_000_000_000_000_102
CHARACTER_B1 = 1_600_000_000_000_000_103

SETUP_A1 = 1_600_000_000_000_000_151
SETUP_A2 = 1_600_000_000_000_000_152

#: `SESSION_A1` carries a setup; `SESSION_A_PLAIN` is the same character with **no** setup.
SESSION_A1 = 1_600_000_000_000_000_201
SESSION_A2 = 1_600_000_000_000_000_202
SESSION_A_PLAIN = 1_600_000_000_000_000_203
SESSION_B1 = 1_600_000_000_000_000_204

#: One note per level of `SESSION_A1`'s chain, plus the setup-less session's own note.
MEMO_USER = 1_600_000_000_000_000_301
MEMO_CHARACTER = 1_600_000_000_000_000_302
MEMO_SETUP = 1_600_000_000_000_000_303
MEMO_SESSION = 1_600_000_000_000_000_304
MEMO_PLAIN_SESSION = 1_600_000_000_000_000_305

#: Notes of the **same** user outside `SESSION_A1`'s chain (R2's absences).
MEMO_OTHER_CHARACTER = 1_600_000_000_000_000_311
MEMO_OTHER_SETUP = 1_600_000_000_000_000_312
MEMO_OTHER_SESSION = 1_600_000_000_000_000_313

BODY_USER = "the user-level note"
BODY_CHARACTER = "the character-level note"
BODY_SETUP = "the setup-level note"
BODY_SESSION = "the session-level note"
BODY_PLAIN_SESSION = "the setup-less session's own note"
BODY_OTHER_CHARACTER = "a note of the other character"
BODY_OTHER_SETUP = "a note of the other setup"
BODY_OTHER_SESSION = "a note of the other session"

#: The four chain levels, in the Interface intent's fixed order.
LEVELS_WITH_SETUP = (("user", USER_A), ("character", CHARACTER_A1), ("setup", SETUP_A1), ("session", SESSION_A1))

#: The same chain with no setup: three levels, in the same order.
LEVELS_WITHOUT_SETUP = (("user", USER_A), ("character", CHARACTER_A1), ("session", SESSION_A_PLAIN))


# --- raw-insert helpers (file-local; no service is used to seed) -----------------------------


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


def _insert_character(engine: Engine, *, character_id: int, user_id: int, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.characters.insert().values(
                id=character_id,
                user_id=user_id,
                name=name,
                sheet="",
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_setup(engine: Engine, *, setup_id: int, user_id: int, character_id: int, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.setups.insert().values(
                id=setup_id,
                user_id=user_id,
                character_id=character_id,
                name=name,
                description="",
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_session(
    engine: Engine, *, session_id: int, user_id: int, character_id: int, setup_id: int | None
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=setup_id,
                last_used_at=TIMESTAMP,
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_memo(
    engine: Engine,
    *,
    memo_id: int,
    user_id: int,
    scope: str,
    scope_id: int,
    body: str,
    is_enabled: bool = True,
    is_forced: bool = False,
    sort_key: int = 0,
) -> None:
    """Raw-insert one `memos` row; `scope_id` is the **stored** id (the user id at user level)."""
    with engine.begin() as connection:
        connection.execute(
            schema.memos.insert().values(
                id=memo_id,
                user_id=user_id,
                scope=scope,
                scope_id=scope_id,
                body=body,
                is_enabled=is_enabled,
                is_forced=is_forced,
                sort_key=sort_key,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


# --- fixtures and seeds ---------------------------------------------------------------------


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two users, three characters, two setups and four sessions — one of them setup-less."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="aster")
    _insert_user(db_engine, user_id=USER_B, username="briar")
    _insert_character(db_engine, character_id=CHARACTER_A1, user_id=USER_A, name="first")
    _insert_character(db_engine, character_id=CHARACTER_A2, user_id=USER_A, name="second")
    _insert_character(db_engine, character_id=CHARACTER_B1, user_id=USER_B, name="other owner")
    _insert_setup(db_engine, setup_id=SETUP_A1, user_id=USER_A, character_id=CHARACTER_A1, name="the inn")
    _insert_setup(db_engine, setup_id=SETUP_A2, user_id=USER_A, character_id=CHARACTER_A2, name="the road")
    _insert_session(
        db_engine, session_id=SESSION_A1, user_id=USER_A, character_id=CHARACTER_A1, setup_id=SETUP_A1
    )
    _insert_session(
        db_engine, session_id=SESSION_A2, user_id=USER_A, character_id=CHARACTER_A2, setup_id=SETUP_A2
    )
    _insert_session(
        db_engine, session_id=SESSION_A_PLAIN, user_id=USER_A, character_id=CHARACTER_A1, setup_id=None
    )
    _insert_session(
        db_engine, session_id=SESSION_B1, user_id=USER_B, character_id=CHARACTER_B1, setup_id=None
    )
    return db_engine


def _seed_notes(engine: Engine) -> None:
    """One note at each of A's levels, plus three of A's notes outside `SESSION_A1`'s chain."""
    _insert_memo(engine, memo_id=MEMO_USER, user_id=USER_A, scope="user", scope_id=USER_A, body=BODY_USER)
    _insert_memo(
        engine,
        memo_id=MEMO_CHARACTER,
        user_id=USER_A,
        scope="character",
        scope_id=CHARACTER_A1,
        body=BODY_CHARACTER,
    )
    _insert_memo(engine, memo_id=MEMO_SETUP, user_id=USER_A, scope="setup", scope_id=SETUP_A1, body=BODY_SETUP)
    _insert_memo(
        engine, memo_id=MEMO_SESSION, user_id=USER_A, scope="session", scope_id=SESSION_A1, body=BODY_SESSION
    )
    _insert_memo(
        engine,
        memo_id=MEMO_PLAIN_SESSION,
        user_id=USER_A,
        scope="session",
        scope_id=SESSION_A_PLAIN,
        body=BODY_PLAIN_SESSION,
    )
    _insert_memo(
        engine,
        memo_id=MEMO_OTHER_CHARACTER,
        user_id=USER_A,
        scope="character",
        scope_id=CHARACTER_A2,
        body=BODY_OTHER_CHARACTER,
    )
    _insert_memo(
        engine,
        memo_id=MEMO_OTHER_SETUP,
        user_id=USER_A,
        scope="setup",
        scope_id=SETUP_A2,
        body=BODY_OTHER_SETUP,
    )
    _insert_memo(
        engine,
        memo_id=MEMO_OTHER_SESSION,
        user_id=USER_A,
        scope="session",
        scope_id=SESSION_A2,
        body=BODY_OTHER_SESSION,
    )


# --- reading the compiled clause as text ----------------------------------------------------


def _compiled(clause: ColumnElement[bool]) -> str:
    """The clause as SQLite would see it, with every bind rendered inline (001 `context.md`)."""
    return str(clause.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))


def _scope_term_count(compiled: str) -> int:
    """How many times the `scope` **column** is named; `scope_id` cannot match (`\\b` stops at `_`)."""
    return len(re.findall(r"\bscope\b", compiled))


def _scope_id_term_count(compiled: str) -> int:
    return len(re.findall(r"\bscope_id\b", compiled))


def _selected_ids(engine: Engine, clause: ColumnElement[bool]) -> set[int]:
    with engine.connect() as connection:
        rows = connection.execute(select(schema.memos.c.id).where(clause)).all()
    return {row.id for row in rows}


# --- DoD-1: the compiled shape — four terms with a setup, three without (R2, D2) ------------


def test_the_clause_with_a_setup_has_four_scope_terms_naming_the_four_ids__S026_001_DoD1() -> None:
    """D2: one `(scope = <level> AND scope_id = <level id>)` term per existing level."""
    compiled = _compiled(
        chain_clause(
            schema.memos,
            user_id=USER_A,
            character_id=CHARACTER_A1,
            setup_id=SETUP_A1,
            session_id=SESSION_A1,
        )
    )

    assert _scope_term_count(compiled) == 4
    assert _scope_id_term_count(compiled) == 4
    for level, level_id in LEVELS_WITH_SETUP:
        assert re.search(rf"\bscope\b\s*=\s*'{level}'", compiled) is not None
        assert re.search(rf"\bscope_id\b\s*=\s*{level_id}\b", compiled) is not None


def test_the_clause_without_a_setup_has_exactly_three_terms_and_no_setup_term__S026_001_DoD1() -> None:
    """R2: no setup level, one fewer term — and the word `setup` appears nowhere."""
    compiled = _compiled(
        chain_clause(
            schema.memos,
            user_id=USER_A,
            character_id=CHARACTER_A1,
            setup_id=None,
            session_id=SESSION_A_PLAIN,
        )
    )

    assert _scope_term_count(compiled) == 3
    assert _scope_id_term_count(compiled) == 3
    assert "'setup'" not in compiled
    assert str(SETUP_A1) not in compiled
    for level, level_id in LEVELS_WITHOUT_SETUP:
        assert re.search(rf"\bscope\b\s*=\s*'{level}'", compiled) is not None
        assert re.search(rf"\bscope_id\b\s*=\s*{level_id}\b", compiled) is not None


# --- DoD-2: the clause as a filter — exactly the chain's notes (R2, D2) ---------------------


def test_the_clause_selects_exactly_the_four_chain_levels_notes__S026_001_DoD2(engine: Engine) -> None:
    """The four levels' notes, and nothing of another character, setup or session of A."""
    _seed_notes(engine)

    selected = _selected_ids(
        engine,
        chain_clause(
            schema.memos,
            user_id=USER_A,
            character_id=CHARACTER_A1,
            setup_id=SETUP_A1,
            session_id=SESSION_A1,
        ),
    )

    assert selected == {MEMO_USER, MEMO_CHARACTER, MEMO_SETUP, MEMO_SESSION}


def test_the_clause_without_a_setup_selects_exactly_three_levels_notes__S026_001_DoD2(engine: Engine) -> None:
    """Three levels only: the setup note and the other session's note are both out."""
    _seed_notes(engine)

    selected = _selected_ids(
        engine,
        chain_clause(
            schema.memos,
            user_id=USER_A,
            character_id=CHARACTER_A1,
            setup_id=None,
            session_id=SESSION_A_PLAIN,
        ),
    )

    assert selected == {MEMO_USER, MEMO_CHARACTER, MEMO_PLAIN_SESSION}


def test_the_clause_excludes_notes_outside_the_chain_of_the_same_user__S026_001_DoD2(engine: Engine) -> None:
    """Stated as an absence: the other character, setup and session of A are all unreachable."""
    _seed_notes(engine)

    selected = _selected_ids(
        engine,
        chain_clause(
            schema.memos,
            user_id=USER_A,
            character_id=CHARACTER_A1,
            setup_id=SETUP_A1,
            session_id=SESSION_A1,
        ),
    )

    assert MEMO_OTHER_CHARACTER not in selected
    assert MEMO_OTHER_SETUP not in selected
    assert MEMO_OTHER_SESSION not in selected
    assert MEMO_PLAIN_SESSION not in selected


# --- DoD-3: `resolve_chain` is unchanged (D2) ----------------------------------------------
# `backend/tests/test_memo_chain_service.py` is 015's regression guard and is **not** edited;
# these two tests are 026's own restatement of the behaviour the re-route may not disturb.


def test_resolve_chain_with_a_setup_still_returns_the_four_levels__S026_001_DoD3(engine: Engine) -> None:
    """Four levels in chain order, the user level reporting `scope_id = None`, each with its note."""
    _seed_notes(engine)

    with engine.connect() as connection:
        levels = resolve_chain(connection, USER_A, SESSION_A1)

    assert [(level.scope, level.scope_id) for level in levels] == [
        ("user", None),
        ("character", CHARACTER_A1),
        ("setup", SETUP_A1),
        ("session", SESSION_A1),
    ]
    assert [[memo.body for memo in level.memos] for level in levels] == [
        [BODY_USER],
        [BODY_CHARACTER],
        [BODY_SETUP],
        [BODY_SESSION],
    ]


def test_resolve_chain_without_a_setup_still_returns_three_levels__S026_001_DoD3(engine: Engine) -> None:
    """Three levels, no gap and no setup entry; the setup note stays out of the result."""
    _seed_notes(engine)

    with engine.connect() as connection:
        levels = resolve_chain(connection, USER_A, SESSION_A_PLAIN)

    assert [(level.scope, level.scope_id) for level in levels] == [
        ("user", None),
        ("character", CHARACTER_A1),
        ("session", SESSION_A_PLAIN),
    ]
    assert [[memo.body for memo in level.memos] for level in levels] == [
        [BODY_USER],
        [BODY_CHARACTER],
        [BODY_PLAIN_SESSION],
    ]
    assert BODY_SETUP not in [memo.body for level in levels for memo in level.memos]
