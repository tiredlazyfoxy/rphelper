"""`services/search/my_search.py` — feature 029, step 001 (DoD-1..10).

Every expected value comes from the **spec**, never from the implementation:
`docs/plans/029.my-search/001.like-corpora.md` (Interface intent and Definition of done),
`001.context.md` (the two tables, the escaping note and the seeding notes) and the feature
`context.md` — **U2** (characters match on `name` / `sheet`, setups on `name` /
`description`), **U3** (archived rows are included and flagged), **D2** (the per-kind cap is
`20`; characters and setups are ordered by `name` then `id` ascending), **D3** (the needle is
the stripped query, matched as **one** substring, wildcards escaped, ASCII-case-insensitive),
**D6** (read posture) and the literals table (`per-kind cap` = `20`).

Bindings come from `## Skeleton` → "Step 001 — frozen interface (2026-10-05)" in `status.md`:

    MY_SEARCH_PER_KIND_LIMIT: Final[int] = 20
    CharacterHit(id: int, name: str, archived: bool)
    SetupHit(id: int, name: str, character_id: int, character_name: str, archived: bool)
    search_characters(connection, user_id, query_text, limit=MY_SEARCH_PER_KIND_LIMIT) -> list[CharacterHit]
    search_setups(connection, user_id, query_text, limit=MY_SEARCH_PER_KIND_LIMIT) -> list[SetupHit]

Both hit values are frozen dataclasses, so a whole expected row can be written out and
compared by equality — which is how the "with their ids, names and `archived`" clauses below
are asserted.

How the expectations are derived
--------------------------------
Nothing here asks the code under test what the answer is.

* **Nothing is mocked and nothing is monkeypatched.** A real SQLite file per test through the
  shared `db_engine` fixture; raw inserts only; `tests/conftest.py` and `tests/llm_fakes.py`
  are untouched. This step opens no model and needs no search table.
* **Absences are proved with data that would otherwise match** (`context.md` cross-cutting
  constraints): the other user's rows carry the *same* names and the *same* texts as the
  caller's matching ones, so an absence is the owner predicate's work and never a needle that
  missed.
* **The escape character is `/`, not `\\`** (the ultra orchestrator's decision 3: that is what
  SQLAlchemy's `autoescape=True` declares). A literal backslash in a name is therefore an
  **ordinary character**, and DoD-6's backslash cases below are written that way: a name
  holding a backslash is found by a query holding that backslash, and a lone backslash matches
  only that row.
* **Ordering is asserted only where D2 defines it** — `name` ascending, then `id` — which is
  total for every seeded set below, so the expected lists are written in full.

Each test name ends `__S029_001_DoD<n>` with the DoD item it covers.

A note on DoD-9's third case. D6 and the frozen `_reading` are the `opened_here` form: a
transaction the **caller** already opened is deliberately left alone. So the mid-read case
asserts what that posture makes true and still non-vacuous — the call adds no transaction of
its own, and one `rollback()` clears everything that is open afterwards. See the test's
docstring; the literal reading of DoD-9 ("no transaction in progress" even mid-read) is
flagged to the orchestrator as a spec concern.
"""

import ast
from collections.abc import Sequence
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, text

from app.db import schema
from app.roles import Role
from app.services.search import my_search as my_search_module
from app.services.search.my_search import (
    MY_SEARCH_PER_KIND_LIMIT,
    CharacterHit,
    SetupHit,
    search_characters,
    search_setups,
)

#: The seeded instant, in the project's fixed-width UTC text form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: Every id below is above 2^60 = 1152921504606846976 (snowflake-sized).
SNOWFLAKE_FLOOR = 2**60

#: D2's per-kind cap, written out as the **spec's** literal (the literals table).
EXPECTED_PER_KIND_CAP = 20

USER_A = 1_290_000_000_000_000_001
USER_B = 1_290_000_000_000_000_002

CH_MIRA = 1_290_000_000_000_000_101
CH_CORVIN = 1_290_000_000_000_000_102
CH_TESS = 1_290_000_000_000_000_103
CH_B_MIRA = 1_290_000_000_000_000_104
CH_ARCHIVED = 1_290_000_000_000_000_105
CH_LIVE = 1_290_000_000_000_000_106
CH_PERCENT = 1_290_000_000_000_000_107
CH_HUNDRED = 1_290_000_000_000_000_108
CH_UNDERSCORE = 1_290_000_000_000_000_109
CH_AXB = 1_290_000_000_000_000_110
CH_BACKSLASH = 1_290_000_000_000_000_111
CH_SILVER_LANTERN = 1_290_000_000_000_000_112
CH_LANTERN_SILVER = 1_290_000_000_000_000_113
CH_WILDCARD_HOST = 1_290_000_000_000_000_114
CH_LIMIT_HOST = 1_290_000_000_000_000_115

SETUP_AWRY = 1_290_000_000_000_000_151
SETUP_BEACON = 1_290_000_000_000_000_152
SETUP_QUIET = 1_290_000_000_000_000_153
SETUP_B_BEACON = 1_290_000_000_000_000_154
SETUP_ARCHIVED = 1_290_000_000_000_000_155
SETUP_LIVE = 1_290_000_000_000_000_156
SETUP_UNDER_ARCHIVED_CHARACTER = 1_290_000_000_000_000_157
SETUP_PERCENT = 1_290_000_000_000_000_158
SETUP_PLAIN = 1_290_000_000_000_000_159

#: DoD-8's 25 matching characters, one per offset, named so that `name` order is `00`..`24`.
LIMIT_CHARACTER_BASE = 1_290_000_000_000_000_201
LIMIT_CHARACTER_COUNT = 25

# --- the texts the two corpora are matched on ------------------------------------------------

#: DoD-2's three personas. Only the first two mention "Mira"; the third mentions nothing of it.
MIRA_SHEET = "The keeper of the lighthouse on the north spit."
CORVIN_SHEET = "Mira's brother, a boatwright who never leaves the harbour."
TESS_SHEET = "A cartwright who argues about axle grease in a dry inland town."

#: DoD-3's setup texts. The needle is lower-case `beacon`; one row holds it capitalised in its
#: **name**, the other upper-cased in its **description**, and the third holds it nowhere.
AWRY_DESCRIPTION = "The BEACON burns above the strait, all night and every night."
BEACON_DESCRIPTION = "A quiet slope of gorse, well inland of the water."
QUIET_DESCRIPTION = "Nothing here but dust and a shuttered window."


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


def _insert_character(
    engine: Engine,
    *,
    character_id: int,
    user_id: int = USER_A,
    name: str,
    sheet: str = "",
    archived_at: str | None = None,
) -> None:
    """Raw-insert one `characters` row. `name` and `sheet` are both `Text, nullable=False`."""
    with engine.begin() as connection:
        connection.execute(
            schema.characters.insert().values(
                id=character_id,
                user_id=user_id,
                name=name,
                sheet=sheet,
                archived_at=archived_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_setup(
    engine: Engine,
    *,
    setup_id: int,
    character_id: int,
    user_id: int = USER_A,
    name: str,
    description: str = "",
    archived_at: str | None = None,
) -> None:
    """Raw-insert one `setups` row. `name` and `description` are both `Text, nullable=False`."""
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


def _characters(engine: Engine, query_text: str, *, user_id: int = USER_A) -> list[CharacterHit]:
    """`search_characters` with the frozen three-argument call, so the default limit applies."""
    with engine.connect() as connection:
        return search_characters(connection, user_id, query_text)


def _setups(engine: Engine, query_text: str, *, user_id: int = USER_A) -> list[SetupHit]:
    with engine.connect() as connection:
        return search_setups(connection, user_id, query_text)


def _ids(hits: Sequence[CharacterHit] | Sequence[SetupHit]) -> list[int]:
    return [hit.id for hit in hits]


def _archived_by_id(hits: Sequence[CharacterHit] | Sequence[SetupHit]) -> dict[int, bool]:
    return {hit.id: hit.archived for hit in hits}


def _assert_no_open_transaction(connection: Connection) -> None:
    assert not connection.in_transaction()
    transaction = connection.begin()
    transaction.rollback()


# --- seeds ----------------------------------------------------------------------------------


def _seed_personas(engine: Engine) -> None:
    """DoD-2's three characters: a name match, a persona match and a non-match."""
    _insert_character(engine, character_id=CH_MIRA, name="Mira", sheet=MIRA_SHEET)
    _insert_character(engine, character_id=CH_CORVIN, name="Corvin", sheet=CORVIN_SHEET)
    _insert_character(engine, character_id=CH_TESS, name="Tess", sheet=TESS_SHEET)


def _seed_setups(engine: Engine) -> None:
    """DoD-3's three setups, under two different characters (so the join is observable)."""
    _insert_setup(
        engine,
        setup_id=SETUP_AWRY,
        character_id=CH_MIRA,
        name="Awry Tower",
        description=AWRY_DESCRIPTION,
    )
    _insert_setup(
        engine,
        setup_id=SETUP_BEACON,
        character_id=CH_CORVIN,
        name="Beacon Hill",
        description=BEACON_DESCRIPTION,
    )
    _insert_setup(
        engine,
        setup_id=SETUP_QUIET,
        character_id=CH_CORVIN,
        name="Quiet Room",
        description=QUIET_DESCRIPTION,
    )


# --- fixtures -------------------------------------------------------------------------------


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """The schema and the two users A and B; every other row is seeded by the test itself.

    No search table and no designated model: this step's two searches open no model and read
    no index, so nothing else belongs in the fixture.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="aster")
    _insert_user(db_engine, user_id=USER_B, username="briar")
    return db_engine


# --- DoD-1: the cap constant (D2, the literals table) ---------------------------------------


def test_the_per_kind_cap_constant_is_twenty__S029_001_DoD1() -> None:
    """D2 and the literals table: each group holds at most a fixed `20` hits."""
    assert MY_SEARCH_PER_KIND_LIMIT == EXPECTED_PER_KIND_CAP


# --- DoD-2: characters by name and by persona (US-074.AC-1, U2, D2, D3) ---------------------


def test_characters_match_on_name_and_on_persona_in_name_order__S029_001_DoD2(engine: Engine) -> None:
    """Mira matches on her name and Corvin on his sheet, case folded, once each, in name order.

    Tess's sheet mentions nothing of the needle, so she is absent — and the whole expected
    list is written out, which also pins the ids, the names and `archived` false.
    """
    _seed_personas(engine)

    hits = _characters(engine, "mira")

    assert hits == [
        CharacterHit(id=CH_CORVIN, name="Corvin", archived=False),
        CharacterHit(id=CH_MIRA, name="Mira", archived=False),
    ]


# --- DoD-3: setups by name and by description (US-074.AC-1, U2) -----------------------------


def test_setups_match_on_name_and_on_description_in_name_order__S029_001_DoD3(engine: Engine) -> None:
    """One setup matches in its name, another in its description in a different case, and both
    carry their own id and name plus their character's id and name. The third is absent."""
    _seed_personas(engine)
    _seed_setups(engine)

    hits = _setups(engine, "beacon")

    assert hits == [
        SetupHit(
            id=SETUP_AWRY,
            name="Awry Tower",
            character_id=CH_MIRA,
            character_name="Mira",
            archived=False,
        ),
        SetupHit(
            id=SETUP_BEACON,
            name="Beacon Hill",
            character_id=CH_CORVIN,
            character_name="Corvin",
            archived=False,
        ),
    ]


# --- DoD-4: owner isolation, as an absence (US-076.AC-1, UC-065, R5) ------------------------


def _seed_other_owners_twins(engine: Engine) -> None:
    """B's character and setup carry **the same** names and texts as A's matching ones."""
    _insert_character(engine, character_id=CH_B_MIRA, user_id=USER_B, name="Mira", sheet=MIRA_SHEET)
    _insert_setup(
        engine,
        setup_id=SETUP_B_BEACON,
        user_id=USER_B,
        character_id=CH_B_MIRA,
        name="Beacon Hill",
        description=AWRY_DESCRIPTION,
    )


def test_another_users_identical_character_never_appears__S029_001_DoD4(engine: Engine) -> None:
    """R5: B's twin would match on every column A's does, and is still absent from A's results;
    B's own search returns only B's row."""
    _seed_personas(engine)
    _seed_other_owners_twins(engine)

    for_a = _characters(engine, "mira")
    for_b = _characters(engine, "mira", user_id=USER_B)

    assert CH_B_MIRA not in _ids(for_a)
    assert _ids(for_a) == [CH_CORVIN, CH_MIRA]
    assert _ids(for_b) == [CH_B_MIRA]


def test_another_users_identical_setup_never_appears__S029_001_DoD4(engine: Engine) -> None:
    """R5: the setup search carries the owner predicate on **both** tables it names."""
    _seed_personas(engine)
    _seed_setups(engine)
    _seed_other_owners_twins(engine)

    for_a = _setups(engine, "beacon")
    for_b = _setups(engine, "beacon", user_id=USER_B)

    assert SETUP_B_BEACON not in _ids(for_a)
    assert _ids(for_a) == [SETUP_AWRY, SETUP_BEACON]
    assert _ids(for_b) == [SETUP_B_BEACON]


# --- DoD-5: archived rows are included and flagged (U3) -------------------------------------


def _seed_archive_cases(engine: Engine) -> None:
    """Two characters and three setups, all matching `lamp`; the archive flags differ."""
    _insert_character(engine, character_id=CH_ARCHIVED, name="Lamp archived", archived_at=TIMESTAMP)
    _insert_character(engine, character_id=CH_LIVE, name="Lamp live")
    _insert_setup(
        engine,
        setup_id=SETUP_ARCHIVED,
        character_id=CH_LIVE,
        name="Lamp setup archived",
        archived_at=TIMESTAMP,
    )
    _insert_setup(engine, setup_id=SETUP_LIVE, character_id=CH_LIVE, name="Lamp setup live")
    _insert_setup(
        engine,
        setup_id=SETUP_UNDER_ARCHIVED_CHARACTER,
        character_id=CH_ARCHIVED,
        name="Lamp setup under an archived character",
    )


def test_an_archived_character_is_returned_and_flagged__S029_001_DoD5(engine: Engine) -> None:
    """U3: the owner predicate is the only filter, and the archived row carries `archived` true."""
    _seed_archive_cases(engine)

    hits = _characters(engine, "lamp")

    assert _archived_by_id(hits) == {CH_ARCHIVED: True, CH_LIVE: False}


def test_an_archived_setup_is_flagged_and_its_characters_archive_is_not__S029_001_DoD5(engine: Engine) -> None:
    """U3: `archived` is the **setup's own** `archived_at`, so a working setup under an archived
    character is returned with `archived` false — and still carries that character's name."""
    _seed_archive_cases(engine)

    hits = _setups(engine, "lamp")

    assert _archived_by_id(hits) == {
        SETUP_ARCHIVED: True,
        SETUP_LIVE: False,
        SETUP_UNDER_ARCHIVED_CHARACTER: False,
    }
    under_archived = [hit for hit in hits if hit.id == SETUP_UNDER_ARCHIVED_CHARACTER]
    assert [hit.character_name for hit in under_archived] == ["Lamp archived"]


# --- DoD-6: wildcards and the backslash are literal (D3) ------------------------------------


def _seed_wildcard_characters(engine: Engine) -> None:
    """Four names differing only in the characters a `LIKE` would treat as wildcards, plus one
    holding a literal backslash. Every sheet is empty, so only the names can match."""
    _insert_character(engine, character_id=CH_PERCENT, name="100% sure")
    _insert_character(engine, character_id=CH_HUNDRED, name="100 sure")
    _insert_character(engine, character_id=CH_UNDERSCORE, name="a_b")
    _insert_character(engine, character_id=CH_AXB, name="axb")
    _insert_character(engine, character_id=CH_BACKSLASH, name="back\\slash")


@pytest.mark.parametrize(
    ("query_text", "expected"),
    [
        ("%", [CH_PERCENT]),
        ("_", [CH_UNDERSCORE]),
        ("100%", [CH_PERCENT]),
        ("a_b", [CH_UNDERSCORE]),
    ],
)
def test_a_wildcard_in_the_query_matches_only_itself__S029_001_DoD6(
    engine: Engine, query_text: str, expected: list[int]
) -> None:
    """D3: `%` and `_` are escaped and the statement declares its escape character, so user
    input can never act as a wildcard — each query finds the one row holding it literally."""
    _seed_wildcard_characters(engine)

    assert _ids(_characters(engine, query_text)) == expected


def test_a_backslash_in_a_name_is_an_ordinary_character__S029_001_DoD6(engine: Engine) -> None:
    """The escape character the statement declares is `/` (orchestrator decision 3), so a
    backslash is nothing special: the name holding one is found by a query holding it, and a
    lone backslash matches that row and nothing else."""
    _seed_wildcard_characters(engine)

    assert _ids(_characters(engine, "back\\slash")) == [CH_BACKSLASH]
    assert _ids(_characters(engine, "\\")) == [CH_BACKSLASH]


def test_a_wildcard_in_the_query_is_literal_for_setups_too__S029_001_DoD6(engine: Engine) -> None:
    """The representative setup case: `%` finds the setup whose name holds a per-cent sign."""
    _insert_character(engine, character_id=CH_WILDCARD_HOST, name="the wildcard host")
    _insert_setup(engine, setup_id=SETUP_PERCENT, character_id=CH_WILDCARD_HOST, name="50% done")
    _insert_setup(engine, setup_id=SETUP_PLAIN, character_id=CH_WILDCARD_HOST, name="50 done")

    assert _ids(_setups(engine, "%")) == [SETUP_PERCENT]


# --- DoD-7: blank queries, stripping, and one substring (D3) --------------------------------


@pytest.mark.parametrize("query_text", ["", "   ", "\n\t"])
def test_a_blank_query_returns_nothing_for_either_kind__S029_001_DoD7(engine: Engine, query_text: str) -> None:
    """D3: the needle is the **stripped** query, so an empty or whitespace-only query is blank
    and answers `[]` — even with rows present that any non-blank needle would reach."""
    _seed_personas(engine)
    _seed_setups(engine)

    assert _characters(engine, query_text) == []
    assert _setups(engine, query_text) == []


def test_surrounding_whitespace_is_stripped_from_the_needle__S029_001_DoD7(engine: Engine) -> None:
    """D3: `"  Mira  "` and `"Mira"` are the same search."""
    _seed_personas(engine)

    assert _characters(engine, "  Mira  ") == _characters(engine, "Mira")
    assert _ids(_characters(engine, "  Mira  ")) == [CH_CORVIN, CH_MIRA]


def test_a_two_word_query_is_one_substring_and_is_not_split__S029_001_DoD7(engine: Engine) -> None:
    """D3: the needle is matched as one substring, so only the row holding both words adjacent
    and in the order typed matches — the row holding them swapped does not."""
    _insert_character(engine, character_id=CH_SILVER_LANTERN, name="Silver Lantern")
    _insert_character(engine, character_id=CH_LANTERN_SILVER, name="Lantern Silver")

    assert _ids(_characters(engine, "silver lantern")) == [CH_SILVER_LANTERN]


# --- DoD-8: the limit (D2) ------------------------------------------------------------------


def _limit_name(offset: int) -> str:
    """`limit case 00` .. `limit case 24` — zero-padded, so `name` order is `offset` order."""
    return f"limit case {offset:02d}"


def _seed_limit_characters(engine: Engine) -> None:
    for offset in range(LIMIT_CHARACTER_COUNT):
        _insert_character(
            engine,
            character_id=LIMIT_CHARACTER_BASE + offset,
            name=_limit_name(offset),
        )


def test_the_default_limit_is_the_cap_and_keeps_the_first_rows_in_name_order__S029_001_DoD8(
    engine: Engine,
) -> None:
    """D2: twenty-five matching characters, and the three-argument call answers exactly the cap,
    the first `MY_SEARCH_PER_KIND_LIMIT` in name order."""
    assert LIMIT_CHARACTER_COUNT > EXPECTED_PER_KIND_CAP
    _seed_limit_characters(engine)

    hits = _characters(engine, "limit case")

    assert len(hits) == EXPECTED_PER_KIND_CAP
    assert [hit.name for hit in hits] == [_limit_name(offset) for offset in range(EXPECTED_PER_KIND_CAP)]


def test_an_explicit_smaller_limit_keeps_the_first_three_in_name_order__S029_001_DoD8(engine: Engine) -> None:
    """D2: `limit=3` answers exactly three hits, the first three in name order."""
    _seed_limit_characters(engine)

    with engine.connect() as connection:
        hits = search_characters(connection, USER_A, "limit case", 3)

    assert [hit.name for hit in hits] == [_limit_name(0), _limit_name(1), _limit_name(2)]
    assert _ids(hits) == [LIMIT_CHARACTER_BASE, LIMIT_CHARACTER_BASE + 1, LIMIT_CHARACTER_BASE + 2]


# --- DoD-9: no transaction left open (D6) ---------------------------------------------------


def test_a_search_that_hits_leaves_no_transaction_in_progress__S029_001_DoD9(engine: Engine) -> None:
    """D6: the autobegun read is ended again, on the ordinary exit, for both kinds."""
    _seed_personas(engine)
    _seed_setups(engine)

    with engine.connect() as connection:
        assert _ids(search_characters(connection, USER_A, "mira")) == [CH_CORVIN, CH_MIRA]
        _assert_no_open_transaction(connection)

        assert _ids(search_setups(connection, USER_A, "beacon")) == [SETUP_AWRY, SETUP_BEACON]
        _assert_no_open_transaction(connection)


def test_a_blank_search_leaves_no_transaction_in_progress__S029_001_DoD9(engine: Engine) -> None:
    """D6 and D3 together: the blank early exit issues no SQL, so there is nothing to end."""
    _seed_personas(engine)
    _seed_setups(engine)

    with engine.connect() as connection:
        assert search_characters(connection, USER_A, "   ") == []
        _assert_no_open_transaction(connection)

        assert search_setups(connection, USER_A, "   ") == []
        _assert_no_open_transaction(connection)


def test_a_search_made_mid_read_opens_no_transaction_of_its_own__S029_001_DoD9(engine: Engine) -> None:
    """D6: called while the connection is already mid-read, the search reads through that
    transaction and leaves nothing of its own behind.

    `_reading` is the `opened_here` form (D6, and the skeleton's frozen record), so a
    transaction the **caller** opened is deliberately not rolled back. What the call must not
    do is stack a transaction of its own or abandon one: afterwards at most the caller's own
    root transaction is open, and a single `rollback()` clears everything.
    """
    _seed_personas(engine)

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        caller_transaction = connection.get_transaction()
        assert caller_transaction is not None

        hits = search_characters(connection, USER_A, "mira")

        assert _ids(hits) == [CH_CORVIN, CH_MIRA]
        after = connection.get_transaction()
        assert after is None or after is caller_transaction

        connection.rollback()
        _assert_no_open_transaction(connection)


# --- DoD-10: the module's imports (`context.md` cross-cutting constraints) -------------------


def _imported_names() -> set[str]:
    """Every module named by an import in `my_search.py`, read from its **AST**.

    Deliberately not a text scan: the module's frozen docstring legitimately contains the word
    `fastapi` (it records that the module imports none), so only the import statements count.
    """
    module_file = my_search_module.__file__
    assert module_file is not None
    names: set[str] = set()
    for node in ast.walk(ast.parse(Path(module_file).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_the_my_search_module_imports_no_web_framework__S029_001_DoD10() -> None:
    """`context.md` cross-cutting constraints: `my_search.py` imports no `fastapi`."""
    offenders = {name for name in _imported_names() if name.split(".")[0] in {"fastapi", "starlette"}}

    assert offenders == set()
