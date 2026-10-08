"""fast/006.unicode-name-matching — `rp_casefold` on engine connections and Unicode my-search.

Every expected value comes from the **spec**: `docs/plans/fast/006.unicode-name-matching/plan.md`
(Interface intent, DoD-1..16) and its `context.md` Decisions 1-4 — the fold is Python
`str.casefold` on both sides of the comparison, NULL stays NULL, a non-text value comes back
unchanged, no accent folding and no normalization, SQLAlchemy's `autoescape=True` (escape
character `/`) is kept, and ordering stays `name, id` over the raw stored `name` with SQLite's
binary collation.

Bindings come from `## Skeleton` → "Frozen interface (2026-10-07)" in `status.md`:

    app.db.engine.CASEFOLD_FUNCTION_NAME: Final[str] = "rp_casefold"
    app.db.engine.casefold_sqlite_value(value: SqliteValue) -> SqliteValue
    app.services.search.my_search.search_characters(connection, user_id, query_text, limit=...)
    app.services.search.my_search.search_setups(connection, user_id, query_text, limit=...)

Nothing is mocked: a real per-test SQLite file through the shared `db_engine` fixture (which
is `get_engine`), raw inserts only. Absences are proved with rows that a correct match would
otherwise be tempted by (decoys), never by an empty table.

Binary ordering note (DoD-16): SQLite's default collation compares UTF-8 bytes, which orders
the same as Python code points — upper-case Cyrillic `А` (U+0410) sorts before lower-case `а`
(U+0430), and `Н` (U+041D) before `н` (U+043D). Expected lists are written out by hand.

Each test name ends `__F006_DoD<n>` with the DoD item it covers.
"""

from collections.abc import Sequence

import pytest
from sqlalchemy import Engine

from app.db import schema
from app.db.engine import CASEFOLD_FUNCTION_NAME, casefold_sqlite_value
from app.roles import Role
from app.services.search.my_search import (
    CharacterHit,
    SetupHit,
    search_characters,
    search_setups,
)

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

USER_A = 1_300_600_000_000_000_001
USER_B = 1_300_600_000_000_000_002

# Characters.
CH_DMITRY = 1_300_600_000_000_000_101
CH_MARIA = 1_300_600_000_000_000_102
CH_KORVIN = 1_300_600_000_000_000_103
CH_TESSA = 1_300_600_000_000_000_104
CH_BOTH = 1_300_600_000_000_000_105
CH_STRASSE_SZ = 1_300_600_000_000_000_106
CH_STRASSE_UPPER = 1_300_600_000_000_000_107
CH_ELODIE = 1_300_600_000_000_000_108
CH_DOM = 1_300_600_000_000_000_109
CH_D_PERCENT_M = 1_300_600_000_000_000_110
CH_D_UNDERSCORE_M = 1_300_600_000_000_000_111
CH_D_BACKSLASH_M = 1_300_600_000_000_000_112
CH_D_SLASH_M = 1_300_600_000_000_000_113
CH_DM = 1_300_600_000_000_000_114
CH_B_DMITRY = 1_300_600_000_000_000_115
CH_KAELITH = 1_300_600_000_000_000_116
CH_HOST = 1_300_600_000_000_000_117
CH_ANNA_UPPER = 1_300_600_000_000_000_118
CH_ANNA_TITLE_LOW_ID = 1_300_600_000_000_000_119
CH_ANNA_TITLE_HIGH_ID = 1_300_600_000_000_000_120
CH_ANNA_LOWER = 1_300_600_000_000_000_121
CH_B_HOST = 1_300_600_000_000_000_122

# Setups.
SU_SOFIA = 1_300_600_000_000_000_151
SU_GREEK_DECOY = 1_300_600_000_000_000_152
SU_QUIET_ROOM = 1_300_600_000_000_000_153
SU_EMPTY_YARD = 1_300_600_000_000_000_154
SU_BOTH = 1_300_600_000_000_000_155
SU_HOUSE = 1_300_600_000_000_000_156
SU_B_HOUSE = 1_300_600_000_000_000_157


# --- raw-insert helpers ---------------------------------------------------------------------


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
    name: str,
    sheet: str = "",
    user_id: int = USER_A,
) -> None:
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
    name: str,
    description: str = "",
    character_id: int = CH_HOST,
    user_id: int = USER_A,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.setups.insert().values(
                id=setup_id,
                user_id=user_id,
                character_id=character_id,
                name=name,
                description=description,
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _characters(engine: Engine, query_text: str, *, user_id: int = USER_A) -> list[CharacterHit]:
    with engine.connect() as connection:
        return search_characters(connection, user_id, query_text)


def _setups(engine: Engine, query_text: str, *, user_id: int = USER_A) -> list[SetupHit]:
    with engine.connect() as connection:
        return search_setups(connection, user_id, query_text)


def _ids(hits: Sequence[CharacterHit] | Sequence[SetupHit]) -> list[int]:
    return [hit.id for hit in hits]


# --- fixtures -------------------------------------------------------------------------------


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Schema, users A and B, and one ASCII-named host character per user for setups.

    The host's name holds none of the needles used below, and `search_setups` matches only
    the setup's own `name` / `description`, so the host never decides a setup match.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="aster")
    _insert_user(db_engine, user_id=USER_B, username="briar")
    _insert_character(db_engine, character_id=CH_HOST, name="Host")
    _insert_character(db_engine, character_id=CH_B_HOST, name="Host", user_id=USER_B)
    return db_engine


# --- DoD-1: the SQL function folds Cyrillic and Greek on a get_engine connection -------------


def test_rp_casefold_folds_cyrillic_on_an_engine_connection__F006_DoD1(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT rp_casefold('ДОМ')").scalar() == "дом"


def test_rp_casefold_folds_greek_on_an_engine_connection__F006_DoD1(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT rp_casefold('ΣΟΦΙΑ')").scalar() == "σοφια"


# --- DoD-2: NULL and integer inputs ---------------------------------------------------------


def test_rp_casefold_of_null_is_null__F006_DoD2(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT rp_casefold(NULL)").scalar() is None
        assert connection.exec_driver_sql("SELECT rp_casefold(NULL) IS NULL").scalar() == 1


def test_rp_casefold_returns_an_integer_unchanged__F006_DoD2(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        row = connection.exec_driver_sql("SELECT rp_casefold(42), typeof(rp_casefold(42))").one()
    assert row[0] == 42
    assert row[1] == "integer"


# --- DoD-3: present on every pooled connection ----------------------------------------------


def test_rp_casefold_answers_on_two_connections_held_at_once__F006_DoD3(db_engine: Engine) -> None:
    """Both connections are open together, so the second cannot be the first handed back."""
    with db_engine.connect() as first, db_engine.connect() as second:
        assert first.connection.dbapi_connection is not second.connection.dbapi_connection
        assert first.exec_driver_sql("SELECT rp_casefold('ДОМ')").scalar() == "дом"
        assert second.exec_driver_sql("SELECT rp_casefold('ДОМ')").scalar() == "дом"
        assert first.exec_driver_sql("SELECT rp_casefold('ΣΟΦΙΑ')").scalar() == "σοφια"
        assert second.exec_driver_sql("SELECT rp_casefold('ΣΟΦΙΑ')").scalar() == "σοφια"


# --- DoD-4: the Python callable and the name constant ---------------------------------------


def test_the_function_name_constant_is_rp_casefold__F006_DoD4() -> None:
    assert CASEFOLD_FUNCTION_NAME == "rp_casefold"


def test_the_python_fold_maps_none_to_none__F006_DoD4() -> None:
    assert casefold_sqlite_value(None) is None


def test_the_python_fold_casefolds_text__F006_DoD4() -> None:
    assert casefold_sqlite_value("Straße") == "strasse"
    assert casefold_sqlite_value("ДОМ") == "дом"


def test_the_python_fold_returns_a_non_text_value_unchanged__F006_DoD4() -> None:
    """Interface intent: any other value comes back unchanged, and the callable never raises."""
    assert casefold_sqlite_value(42) == 42
    assert casefold_sqlite_value(b"\x00\x01") == b"\x00\x01"


# --- DoD-5: Cyrillic name, any case of the needle --------------------------------------------


@pytest.mark.parametrize("needle", ["ДМИТРИЙ", "дмитрий", "дМИТрий"])
def test_a_cyrillic_name_is_found_in_any_case__F006_DoD5(engine: Engine, needle: str) -> None:
    _insert_character(engine, character_id=CH_DMITRY, name="Дмитрий")
    _insert_character(engine, character_id=CH_MARIA, name="Мария")

    assert _characters(engine, needle) == [CharacterHit(id=CH_DMITRY, name="Дмитрий", archived=False)]


# --- DoD-6: found only through the sheet ----------------------------------------------------


def test_a_character_is_found_through_its_sheet_by_a_case_different_cyrillic_needle__F006_DoD6(
    engine: Engine,
) -> None:
    _insert_character(engine, character_id=CH_KORVIN, name="Корвин", sheet="Брат Марии, лодочник из гавани.")
    _insert_character(engine, character_id=CH_TESSA, name="Тесса", sheet="Возчица из сухого городка.")

    assert _ids(_characters(engine, "ЛОДОЧНИК")) == [CH_KORVIN]


# --- DoD-7: setup name, Greek needle --------------------------------------------------------


@pytest.mark.parametrize("needle", ["σοφια", "ΣΟΦΙΑ"])
def test_a_setup_is_found_through_its_name_by_a_greek_needle__F006_DoD7(engine: Engine, needle: str) -> None:
    _insert_setup(engine, setup_id=SU_SOFIA, name="Ναός Σοφια")
    _insert_setup(engine, setup_id=SU_GREEK_DECOY, name="Ναός Αθηνα")

    assert _ids(_setups(engine, needle)) == [SU_SOFIA]


# --- DoD-8: setup found only through its description ----------------------------------------


def test_a_setup_is_found_through_its_description_by_a_case_different_cyrillic_needle__F006_DoD8(
    engine: Engine,
) -> None:
    _insert_setup(engine, setup_id=SU_QUIET_ROOM, name="Тихая комната", description="Маяк горит над проливом.")
    _insert_setup(engine, setup_id=SU_EMPTY_YARD, name="Пустой двор", description="Ничего, кроме пыли.")

    assert _ids(_setups(engine, "МАЯК")) == [SU_QUIET_ROOM]


# --- DoD-9: both columns match, row appears once --------------------------------------------


def test_a_character_matching_on_name_and_sheet_appears_once__F006_DoD9(engine: Engine) -> None:
    _insert_character(engine, character_id=CH_BOTH, name="Дмитрий", sheet="ДМИТРИЙ — кузнец, а не дмитрий-пекарь.")

    assert _ids(_characters(engine, "дМиТрИй")) == [CH_BOTH]


def test_a_setup_matching_on_name_and_description_appears_once__F006_DoD9(engine: Engine) -> None:
    _insert_setup(engine, setup_id=SU_BOTH, name="Маяк", description="МАЯК на скале.")

    assert _ids(_setups(engine, "маяк")) == [SU_BOTH]


# --- DoD-10: ß folds both ways --------------------------------------------------------------


def test_sharp_s_folds_both_ways__F006_DoD10(engine: Engine) -> None:
    """Both names fold to `strasse`, so each needle finds both rows, in binary `name` order
    (`STRASSE` before `Straße`: `T` U+0054 < `t` U+0074)."""
    _insert_character(engine, character_id=CH_STRASSE_SZ, name="Straße")
    _insert_character(engine, character_id=CH_STRASSE_UPPER, name="STRASSE")

    found_by_upper = _ids(_characters(engine, "STRASSE"))
    found_by_sz = _ids(_characters(engine, "straße"))

    assert CH_STRASSE_SZ in found_by_upper
    assert CH_STRASSE_UPPER in found_by_sz
    assert found_by_upper == [CH_STRASSE_UPPER, CH_STRASSE_SZ]
    assert found_by_sz == [CH_STRASSE_UPPER, CH_STRASSE_SZ]


# --- DoD-11: case folded, accents not -------------------------------------------------------


def test_an_accented_name_is_found_by_case_but_not_by_dropping_the_accent__F006_DoD11(engine: Engine) -> None:
    _insert_character(engine, character_id=CH_ELODIE, name="Élodie")

    assert _ids(_characters(engine, "élodie")) == [CH_ELODIE]
    assert _characters(engine, "elodie") == []


# --- DoD-12 / DoD-13: wildcards and escape characters stay literal with Cyrillic ------------


def _seed_escape_rows(engine: Engine) -> None:
    """`Дом` and `Дм` are the decoys a broken escape would let through: an unescaped `%` or
    `_` would match `Дом`, and a `/` swallowed as the escape character would match `Дм`."""
    _insert_character(engine, character_id=CH_DOM, name="Дом")
    _insert_character(engine, character_id=CH_DM, name="Дм")
    _insert_character(engine, character_id=CH_D_PERCENT_M, name="Д%М")
    _insert_character(engine, character_id=CH_D_UNDERSCORE_M, name="Д_М")
    _insert_character(engine, character_id=CH_D_BACKSLASH_M, name="Д\\М")
    _insert_character(engine, character_id=CH_D_SLASH_M, name="Д/М")


@pytest.mark.parametrize("needle", ["д%м", "Д%м"])
def test_a_percent_mixed_with_cyrillic_matches_only_the_literal_row__F006_DoD12(engine: Engine, needle: str) -> None:
    _seed_escape_rows(engine)

    hits = _ids(_characters(engine, needle))

    assert CH_DOM not in hits
    assert hits == [CH_D_PERCENT_M]


@pytest.mark.parametrize(
    ("needle", "expected"),
    [
        ("д_м", CH_D_UNDERSCORE_M),
        ("Д_м", CH_D_UNDERSCORE_M),
        ("д\\м", CH_D_BACKSLASH_M),
        ("Д\\м", CH_D_BACKSLASH_M),
        ("д/м", CH_D_SLASH_M),
        ("Д/м", CH_D_SLASH_M),
    ],
)
def test_underscore_backslash_and_slash_mixed_with_cyrillic_match_only_the_literal_row__F006_DoD13(
    engine: Engine, needle: str, expected: int
) -> None:
    _seed_escape_rows(engine)

    hits = _ids(_characters(engine, needle))

    assert CH_DOM not in hits
    assert CH_DM not in hits
    assert hits == [expected]


def test_wildcards_mixed_with_cyrillic_stay_literal_for_setups__F006_DoD12(engine: Engine) -> None:
    _insert_setup(engine, setup_id=SU_HOUSE, name="Дом")
    _insert_setup(engine, setup_id=SU_QUIET_ROOM, name="Д%М")
    _insert_setup(engine, setup_id=SU_EMPTY_YARD, name="Д_М")

    assert _ids(_setups(engine, "д%м")) == [SU_QUIET_ROOM]
    assert _ids(_setups(engine, "д_м")) == [SU_EMPTY_YARD]


# --- DoD-14: owner scope with Cyrillic names ------------------------------------------------


@pytest.mark.parametrize("needle", ["ДМИТРИЙ", "дмитрий", "Дмитрий", "дМИТРИЙ"])
def test_another_users_cyrillic_character_never_appears__F006_DoD14(engine: Engine, needle: str) -> None:
    _insert_character(engine, character_id=CH_DMITRY, name="Дмитрий")
    _insert_character(engine, character_id=CH_B_DMITRY, name="Дмитрий", user_id=USER_B)

    for_a = _ids(_characters(engine, needle))
    for_b = _ids(_characters(engine, needle, user_id=USER_B))

    assert CH_B_DMITRY not in for_a
    assert for_a == [CH_DMITRY]
    assert for_b == [CH_B_DMITRY]


@pytest.mark.parametrize("needle", ["ДОМ У МОРЯ", "дом у моря", "Дом У Моря"])
def test_another_users_cyrillic_setup_never_appears__F006_DoD14(engine: Engine, needle: str) -> None:
    _insert_setup(engine, setup_id=SU_HOUSE, name="Дом у моря")
    _insert_setup(engine, setup_id=SU_B_HOUSE, name="Дом у моря", character_id=CH_B_HOST, user_id=USER_B)

    for_a = _ids(_setups(engine, needle))
    for_b = _ids(_setups(engine, needle, user_id=USER_B))

    assert SU_B_HOUSE not in for_a
    assert for_a == [SU_HOUSE]
    assert for_b == [SU_B_HOUSE]


# --- DoD-15: ASCII case-insensitivity unchanged ---------------------------------------------


@pytest.mark.parametrize("needle", ["KAELITH", "kaeLITH"])
def test_ascii_names_still_match_case_insensitively__F006_DoD15(engine: Engine, needle: str) -> None:
    _insert_character(engine, character_id=CH_KAELITH, name="Kaelith")

    assert _ids(_characters(engine, needle)) == [CH_KAELITH]


# --- DoD-16: ordering by raw name then id; blank needle -------------------------------------


def test_several_non_ascii_matches_are_ordered_by_stored_name_then_id__F006_DoD16(engine: Engine) -> None:
    """Binary order of the raw names: `АННА` < `Анна` < `анна`; the two `Анна` rows tie on
    name and are ordered by id. Inserted out of order so insertion order proves nothing."""
    _insert_character(engine, character_id=CH_ANNA_LOWER, name="анна")
    _insert_character(engine, character_id=CH_ANNA_TITLE_HIGH_ID, name="Анна")
    _insert_character(engine, character_id=CH_ANNA_UPPER, name="АННА")
    _insert_character(engine, character_id=CH_ANNA_TITLE_LOW_ID, name="Анна")

    assert _ids(_characters(engine, "аННа")) == [
        CH_ANNA_UPPER,
        CH_ANNA_TITLE_LOW_ID,
        CH_ANNA_TITLE_HIGH_ID,
        CH_ANNA_LOWER,
    ]


@pytest.mark.parametrize("query_text", ["", "   ", "\n\t"])
def test_a_blank_needle_still_returns_nothing__F006_DoD16(engine: Engine, query_text: str) -> None:
    _insert_character(engine, character_id=CH_DMITRY, name="Дмитрий")
    _insert_setup(engine, setup_id=SU_HOUSE, name="Дом у моря")

    assert _characters(engine, query_text) == []
    assert _setups(engine, query_text) == []
