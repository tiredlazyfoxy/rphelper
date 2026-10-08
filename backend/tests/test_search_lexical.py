"""Tests for the candidate sets and the lexical arm — feature 025, step 002 (DoD-1..11).

Every expected value comes from the **spec**, never from the implementation:
`docs/plans/025.hybrid-search-port/002.candidates-and-lexical-arm.md` (Interface intent and
Definition of done), `002.context.md` (the lexical query shape, the fixed snippet parameters,
the test shape) and the feature `context.md` — **U1** (the three variants, their base relations
and the caller's extra predicate), **U2** (an absent FTS table yields no hits and is not an
error), **D5** (filters first: an arm ranks only within the candidate set) and **D6** (the owner
predicate in every statement, tested as an *absence*).

DoD-4's ordering expectation is BM25's **definition** — a term occurring more often in a
*shorter* document scores better than once in a long one — not an observed number. BM25
magnitudes are never asserted, only the order.

Bindings come from `## Skeleton` → "Step 002 — frozen interface" in `status.md`:
`base_relation(scope)`, `candidate_ids(scope) -> Select[tuple[int]]`, `LexicalMatch(id, snippet)`,
`fts_table_exists(connection, table_name)`, `lexical_ranking(connection, table_name,
candidate_select, fts_expression, *, depth=ARM_DEPTH)` (**`depth` is keyword-only**) and
`SNIPPET_TOKENS`; the scope variants come from step 001's record.

Each test name ends `__S025_002_DoD<n>` with the DoD item it covers.

Mechanics (`context.md` "Test conventions", `002.context.md` "Test shape"):
- a real SQLite file per test via the shared `db_engine` fixture, with
  `schema.metadata.create_all`; **`tests/conftest.py` is untouched** and every other fixture
  and helper here is file-local;
- every row is a **raw insert** with an id **above 2^60**, and **two users** are always present
  so owner isolation is observable as an absence;
- the FTS tables are created only through 024's `ensure_fts_tables`, inside a committed
  transaction, **after** the rows are inserted (the back-fill indexes them). The DoD-10 tests
  never ensure;
- the two virtual tables are named only through 024's constants;
- **no monkeypatching**, and no embedding model is needed anywhere in this step.
"""

import pytest
from sqlalchemy import ColumnElement, Engine, FromClause

from app.db import schema
from app.db.search_tables import MEMO_FTS_TABLE, MESSAGE_FTS_TABLE, ensure_fts_tables
from app.roles import Role
from app.services.search.candidates import candidate_ids
from app.services.search.lexical import (
    SNIPPET_TOKENS,
    LexicalMatch,
    fts_table_exists,
    lexical_ranking,
)
from app.services.search.ports import (
    EntrySearchScope,
    ExtraPredicateBuilder,
    MemoSearchScope,
    SearchScope,
    SessionSearchScope,
)

#: The seeded instant, in the project's fixed-width UTC text form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: The instant a record row carries in `settled_at` (non-null ⇒ it is in `settled_entries`).
SETTLED_AT = "2026-01-01T00:10:00.000000+00:00"

#: Every id below is above 2^60 = 1152921504606846976 (snowflake-sized, 024 D3 / DoD-9).
SNOWFLAKE_FLOOR = 2**60

USER_A = 1_500_000_000_000_000_001
USER_B = 1_500_000_000_000_000_002

CHARACTER_A1 = 1_500_000_000_000_000_101
CHARACTER_A2 = 1_500_000_000_000_000_102
CHARACTER_B1 = 1_500_000_000_000_000_103

SESSION_A1 = 1_500_000_000_000_000_201
SESSION_A2 = 1_500_000_000_000_000_202
SESSION_B1 = 1_500_000_000_000_000_203
#: A `USER_B` session deliberately placed under **`USER_A`'s** character: the only way to show
#: that the owner predicate still applies *alongside* a satisfied extra predicate (DoD-2).
SESSION_B2 = 1_500_000_000_000_000_204

MEMO_A1 = 1_500_000_000_000_000_301
MEMO_A2 = 1_500_000_000_000_000_302
MEMO_A_DISABLED = 1_500_000_000_000_000_303
MEMO_B1 = 1_500_000_000_000_000_304
#: DoD-4: the long-body match has the **lower** id and the short-body match the higher one, so
#: an ordering produced by id instead of BM25 would come out reversed and the test would fail.
MEMO_A_LONG = 1_500_000_000_000_000_311
MEMO_A_SHORT = 1_500_000_000_000_000_312
MEMO_A_WITHOUT_TOKEN = 1_500_000_000_000_000_313
MEMO_B_WITH_TOKEN = 1_500_000_000_000_000_314
MEMO_A_DISABLED_WITH_TOKEN = 1_500_000_000_000_000_315

#: DoD-8: more matching candidates than the depth the call asks for.
MEMO_BULK_IDS = tuple(1_500_000_000_000_000_321 + offset for offset in range(5))
BULK_DEPTH = 3

MESSAGE_A1 = 1_500_000_000_000_000_401
MESSAGE_A2 = 1_500_000_000_000_000_402
MESSAGE_B1 = 1_500_000_000_000_000_403
#: A `USER_B` record row inside **`USER_A`'s** session — DoD-2's owner-still-applies probe.
MESSAGE_B_IN_A1 = 1_500_000_000_000_000_404
MESSAGE_A_ZONE = 1_500_000_000_000_000_405
MESSAGE_A_BURIED = 1_500_000_000_000_000_406

#: The searched term. Lower case throughout, so `snippet()`'s verbatim text contains it as-is.
TOKEN = "kaelith"

#: The sanitised FTS expression for one token, exactly the shape step 001's `build_fts_query`
#: produces (`001.context.md`: strip quotes, wrap each token in `"`, join with ` OR `). Written
#: out here so step 002's tests are falsifiable on their own.
TOKEN_EXPRESSION = f'"{TOKEN}"'

#: The token twice in a three-word body: the stronger BM25 match by definition (DoD-4).
SHORT_BODY = f"{TOKEN} greets {TOKEN}"

#: The token once in a body far longer than the 16-token snippet window: the weaker BM25 match,
#: and the body whose snippet must therefore be cut with an ellipsis (DoD-6).
LONG_BODY = f"{TOKEN} " + " ".join(["filler"] * (SNIPPET_TOKENS * 3))

#: A body the expression cannot match.
BODY_WITHOUT_TOKEN = "the quiet river at dusk"

#: Markup FTS5 must never put in a snippet — the start/end markers are empty (`002.context.md`).
MARKUP_CHARACTERS = ("<", ">", "[", "]")

#: The ellipsis `snippet()` appends when it truncates (U+2026, one character).
ELLIPSIS = "…"


# --- seeding (file-local raw inserts; no service is used) ---------------------------------


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


def _insert_session(engine: Engine, *, session_id: int, user_id: int, character_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=None,
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
    body: str,
    is_enabled: bool = True,
    sort_key: int = 0,
) -> None:
    """Raw-insert one user-level `memos` row."""
    with engine.begin() as connection:
        connection.execute(
            schema.memos.insert().values(
                id=memo_id,
                user_id=user_id,
                scope="user",
                scope_id=user_id,
                body=body,
                is_enabled=is_enabled,
                is_forced=False,
                sort_key=sort_key,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    user_id: int,
    session_id: int,
    body: str,
    related_to: int | None = None,
    settled_at: str | None = None,
) -> None:
    """Raw-insert one `messages` row in a chosen state.

    The three states DoD-3 names: **record** (`settled_at` set, `related_to` null), **zone**
    (both null) and **buried** (`related_to` set, and therefore `settled_at` null — the
    `ck_messages_buried_or_settled` CHECK forbids anything else).
    """
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=message_id,
                user_id=user_id,
                session_id=session_id,
                role="user",
                kind=None,
                text=body,
                related_to=related_to,
                settled_at=settled_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_record_row(engine: Engine, *, message_id: int, user_id: int, session_id: int, body: str) -> None:
    _insert_message(
        engine,
        message_id=message_id,
        user_id=user_id,
        session_id=session_id,
        body=body,
        settled_at=SETTLED_AT,
    )


def _ensure_search_tables(engine: Engine) -> None:
    """Create the FTS tables with 024's helper, inside a committed transaction."""
    with engine.begin() as connection:
        ensure_fts_tables(connection)


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two users, three characters and three sessions — and **no** virtual table yet.

    `create_all` alone leaves `memo_fts` / `message_fts` absent (they are outside
    `schema.metadata`), which is what DoD-10 needs and what every other test opts out of by
    calling `_ensure_search_tables`.
    """
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="aster")
    _insert_user(db_engine, user_id=USER_B, username="briar")
    _insert_character(db_engine, character_id=CHARACTER_A1, user_id=USER_A, name="first")
    _insert_character(db_engine, character_id=CHARACTER_A2, user_id=USER_A, name="second")
    _insert_character(db_engine, character_id=CHARACTER_B1, user_id=USER_B, name="other owner")
    _insert_session(db_engine, session_id=SESSION_A1, user_id=USER_A, character_id=CHARACTER_A1)
    _insert_session(db_engine, session_id=SESSION_A2, user_id=USER_A, character_id=CHARACTER_A2)
    _insert_session(db_engine, session_id=SESSION_B1, user_id=USER_B, character_id=CHARACTER_B1)
    return db_engine


# --- extra-predicate builders (U1: a clause over the FROM object handed to them) ----------


def _memo_is_enabled(relation: FromClause) -> ColumnElement[bool]:
    """`026`'s shape, reduced to its enabled half."""
    return relation.c["is_enabled"].is_(True)


def _session_of_character(character_id: int) -> ExtraPredicateBuilder:
    """`027`'s shape: one character's sessions."""

    def builder(relation: FromClause) -> ColumnElement[bool]:
        return relation.c["character_id"] == character_id

    return builder


def _entry_of_session(session_id: int) -> ExtraPredicateBuilder:
    """One session's entries."""

    def builder(relation: FromClause) -> ColumnElement[bool]:
        return relation.c["session_id"] == session_id

    return builder


# --- calling the frozen interface --------------------------------------------------------


def _candidates(engine: Engine, scope: SearchScope) -> set[int]:
    with engine.connect() as connection:
        return set(connection.execute(candidate_ids(scope)).scalars().all())


def _ranking(
    engine: Engine,
    table_name: str,
    scope: SearchScope,
    expression: str | None = TOKEN_EXPRESSION,
    *,
    depth: int | None = None,
) -> list[LexicalMatch]:
    """Run the lexical arm over `scope`'s candidate set. `depth` is keyword-only when given."""
    with engine.connect() as connection:
        if depth is None:
            return lexical_ranking(connection, table_name, candidate_ids(scope), expression)
        return lexical_ranking(connection, table_name, candidate_ids(scope), expression, depth=depth)


def _ids(matches: list[LexicalMatch]) -> list[int]:
    return [match.id for match in matches]


# --- DoD-1: the owner predicate, for each variant (D6, UC-065, US-085) -------------------


def test_memo_candidates_are_only_the_scope_users__S025_002_DoD1(engine: Engine) -> None:
    _insert_memo(engine, memo_id=MEMO_A1, user_id=USER_A, body="first")
    _insert_memo(engine, memo_id=MEMO_A2, user_id=USER_A, body="second")
    _insert_memo(engine, memo_id=MEMO_B1, user_id=USER_B, body="the other owner's")

    found = _candidates(engine, MemoSearchScope(user_id=USER_A))

    assert found == {MEMO_A1, MEMO_A2}
    assert MEMO_B1 not in found


def test_session_candidates_are_only_the_scope_users__S025_002_DoD1(engine: Engine) -> None:
    found = _candidates(engine, SessionSearchScope(user_id=USER_A))

    assert found == {SESSION_A1, SESSION_A2}
    assert SESSION_B1 not in found


def test_entry_candidates_are_only_the_scope_users__S025_002_DoD1(engine: Engine) -> None:
    _insert_record_row(engine, message_id=MESSAGE_A1, user_id=USER_A, session_id=SESSION_A1, body="mine")
    _insert_record_row(engine, message_id=MESSAGE_A2, user_id=USER_A, session_id=SESSION_A2, body="also mine")
    _insert_record_row(engine, message_id=MESSAGE_B1, user_id=USER_B, session_id=SESSION_B1, body="theirs")

    found = _candidates(engine, EntrySearchScope(user_id=USER_A))

    assert found == {MESSAGE_A1, MESSAGE_A2}
    assert MESSAGE_B1 not in found


def test_other_users_candidates_are_never_visible_in_either_direction__S025_002_DoD1(engine: Engine) -> None:
    """The absence is symmetric: each owner sees exactly their own ids."""
    _insert_memo(engine, memo_id=MEMO_A1, user_id=USER_A, body="first")
    _insert_memo(engine, memo_id=MEMO_B1, user_id=USER_B, body="the other owner's")

    assert _candidates(engine, MemoSearchScope(user_id=USER_A)) == {MEMO_A1}
    assert _candidates(engine, MemoSearchScope(user_id=USER_B)) == {MEMO_B1}


# --- DoD-2: the caller's extra predicate, ANDed with the owner predicate (U1) -------------


def test_memo_extra_predicate_excludes_a_disabled_memo__S025_002_DoD2(engine: Engine) -> None:
    _insert_memo(engine, memo_id=MEMO_A1, user_id=USER_A, body="enabled")
    _insert_memo(engine, memo_id=MEMO_A_DISABLED, user_id=USER_A, body="disabled", is_enabled=False)
    # The other owner's memo satisfies the extra predicate, so only the owner clause can drop it.
    _insert_memo(engine, memo_id=MEMO_B1, user_id=USER_B, body="the other owner's, enabled")

    found = _candidates(engine, MemoSearchScope(user_id=USER_A, extra_predicate=_memo_is_enabled))

    assert found == {MEMO_A1}
    assert MEMO_A_DISABLED not in found
    assert MEMO_B1 not in found


def test_session_extra_predicate_selects_one_character__S025_002_DoD2(engine: Engine) -> None:
    # `USER_B`'s session sits under `CHARACTER_A1`, so it satisfies the extra predicate and only
    # the owner clause can exclude it.
    _insert_session(engine, session_id=SESSION_B2, user_id=USER_B, character_id=CHARACTER_A1)

    scope = SessionSearchScope(user_id=USER_A, extra_predicate=_session_of_character(CHARACTER_A1))
    found = _candidates(engine, scope)

    assert found == {SESSION_A1}
    assert SESSION_A2 not in found
    assert SESSION_B2 not in found


def test_entry_extra_predicate_selects_one_session__S025_002_DoD2(engine: Engine) -> None:
    _insert_record_row(engine, message_id=MESSAGE_A1, user_id=USER_A, session_id=SESSION_A1, body="in session one")
    _insert_record_row(engine, message_id=MESSAGE_A2, user_id=USER_A, session_id=SESSION_A2, body="in session two")
    # `USER_B`'s record row inside `USER_A`'s session: satisfies the extra predicate, wrong owner.
    _insert_record_row(engine, message_id=MESSAGE_B_IN_A1, user_id=USER_B, session_id=SESSION_A1, body="theirs")

    scope = EntrySearchScope(user_id=USER_A, extra_predicate=_entry_of_session(SESSION_A1))
    found = _candidates(engine, scope)

    assert found == {MESSAGE_A1}
    assert MESSAGE_A2 not in found
    assert MESSAGE_B_IN_A1 not in found


# --- DoD-3: the entry corpus boundary (R11, US-115, UC-038) ------------------------------


def test_entry_candidates_exclude_zone_and_buried_rows__S025_002_DoD3(engine: Engine) -> None:
    """Same user, same session: only the record row is findable as an entry."""
    _insert_record_row(engine, message_id=MESSAGE_A1, user_id=USER_A, session_id=SESSION_A1, body="the record row")
    _insert_message(engine, message_id=MESSAGE_A_ZONE, user_id=USER_A, session_id=SESSION_A1, body="a zone draft")
    _insert_message(
        engine,
        message_id=MESSAGE_A_BURIED,
        user_id=USER_A,
        session_id=SESSION_A1,
        body="a buried alternative",
        related_to=MESSAGE_A1,
    )

    found = _candidates(engine, EntrySearchScope(user_id=USER_A))

    assert found == {MESSAGE_A1}
    assert MESSAGE_A_ZONE not in found
    assert MESSAGE_A_BURIED not in found


# --- DoD-4: BM25 ordering (by BM25's definition, not by magnitude) -----------------------


def test_lexical_ranking_orders_the_stronger_bm25_match_first__S025_002_DoD4(engine: Engine) -> None:
    """Twice in a short body beats once in a long one; the non-matching memo is absent."""
    _insert_memo(engine, memo_id=MEMO_A_LONG, user_id=USER_A, body=LONG_BODY)
    _insert_memo(engine, memo_id=MEMO_A_SHORT, user_id=USER_A, body=SHORT_BODY)
    _insert_memo(engine, memo_id=MEMO_A_WITHOUT_TOKEN, user_id=USER_A, body=BODY_WITHOUT_TOKEN)
    _ensure_search_tables(engine)

    matches = _ranking(engine, MEMO_FTS_TABLE, MemoSearchScope(user_id=USER_A))

    assert _ids(matches) == [MEMO_A_SHORT, MEMO_A_LONG]
    assert MEMO_A_WITHOUT_TOKEN not in _ids(matches)


# --- DoD-5: filters first — the arm ranks only inside the candidate set (D5, D6) ----------


def test_lexical_ranking_omits_another_users_indexed_memo__S025_002_DoD5(engine: Engine) -> None:
    """`memo_fts` indexes every memo, so only a candidate-set restriction can drop this one."""
    _insert_memo(engine, memo_id=MEMO_A_SHORT, user_id=USER_A, body=SHORT_BODY)
    _insert_memo(engine, memo_id=MEMO_B_WITH_TOKEN, user_id=USER_B, body=SHORT_BODY)
    _ensure_search_tables(engine)

    matches = _ranking(engine, MEMO_FTS_TABLE, MemoSearchScope(user_id=USER_A))

    assert _ids(matches) == [MEMO_A_SHORT]
    assert MEMO_B_WITH_TOKEN not in _ids(matches)


def test_lexical_ranking_omits_a_memo_excluded_by_the_extra_predicate__S025_002_DoD5(engine: Engine) -> None:
    _insert_memo(engine, memo_id=MEMO_A_SHORT, user_id=USER_A, body=SHORT_BODY)
    _insert_memo(
        engine,
        memo_id=MEMO_A_DISABLED_WITH_TOKEN,
        user_id=USER_A,
        body=SHORT_BODY,
        is_enabled=False,
    )
    _ensure_search_tables(engine)

    scope = MemoSearchScope(user_id=USER_A, extra_predicate=_memo_is_enabled)
    matches = _ranking(engine, MEMO_FTS_TABLE, scope)

    assert _ids(matches) == [MEMO_A_SHORT]
    assert MEMO_A_DISABLED_WITH_TOKEN not in _ids(matches)


# --- DoD-6: the snippet is plain text, truncated with an ellipsis (D4) -------------------


def test_snippets_are_plain_text_containing_the_token__S025_002_DoD6(engine: Engine) -> None:
    _insert_memo(engine, memo_id=MEMO_A_SHORT, user_id=USER_A, body=SHORT_BODY)
    _insert_memo(engine, memo_id=MEMO_A_LONG, user_id=USER_A, body=LONG_BODY)
    _ensure_search_tables(engine)

    matches = _ranking(engine, MEMO_FTS_TABLE, MemoSearchScope(user_id=USER_A))
    snippets = {match.id: match.snippet for match in matches}

    assert set(snippets) == {MEMO_A_SHORT, MEMO_A_LONG}
    for snippet in snippets.values():
        assert isinstance(snippet, str)
        assert TOKEN in snippet
        for character in MARKUP_CHARACTERS:
            assert character not in snippet


def test_a_body_longer_than_the_snippet_window_is_cut_with_an_ellipsis__S025_002_DoD6(engine: Engine) -> None:
    _insert_memo(engine, memo_id=MEMO_A_LONG, user_id=USER_A, body=LONG_BODY)
    _ensure_search_tables(engine)

    matches = _ranking(engine, MEMO_FTS_TABLE, MemoSearchScope(user_id=USER_A))

    assert _ids(matches) == [MEMO_A_LONG]
    assert ELLIPSIS in matches[0].snippet
    assert TOKEN in matches[0].snippet
    assert matches[0].snippet != LONG_BODY


# --- DoD-7: the entry corpus through `message_fts` (U1) ----------------------------------


def test_entry_lexical_ranking_returns_the_matching_record_row__S025_002_DoD7(engine: Engine) -> None:
    _insert_record_row(engine, message_id=MESSAGE_A1, user_id=USER_A, session_id=SESSION_A1, body=SHORT_BODY)
    _insert_record_row(
        engine,
        message_id=MESSAGE_A2,
        user_id=USER_A,
        session_id=SESSION_A2,
        body=BODY_WITHOUT_TOKEN,
    )
    _insert_record_row(engine, message_id=MESSAGE_B1, user_id=USER_B, session_id=SESSION_B1, body=SHORT_BODY)
    _ensure_search_tables(engine)

    matches = _ranking(engine, MESSAGE_FTS_TABLE, EntrySearchScope(user_id=USER_A))

    assert _ids(matches) == [MESSAGE_A1]
    assert TOKEN in matches[0].snippet
    assert MESSAGE_A2 not in _ids(matches)
    assert MESSAGE_B1 not in _ids(matches)


# --- DoD-8: `depth` caps the result (D1); it is keyword-only -----------------------------


def test_depth_caps_the_number_of_matches__S025_002_DoD8(engine: Engine) -> None:
    for offset, memo_id in enumerate(MEMO_BULK_IDS):
        _insert_memo(engine, memo_id=memo_id, user_id=USER_A, body=SHORT_BODY, sort_key=offset)
    _ensure_search_tables(engine)

    matches = _ranking(engine, MEMO_FTS_TABLE, MemoSearchScope(user_id=USER_A), depth=BULK_DEPTH)

    assert len(MEMO_BULK_IDS) > BULK_DEPTH
    assert len(matches) == BULK_DEPTH
    assert len(set(_ids(matches))) == BULK_DEPTH
    assert set(_ids(matches)) <= set(MEMO_BULK_IDS)


# --- DoD-9: snowflake ids round-trip exactly (024 D3) -----------------------------------


def test_a_snowflake_id_round_trips_through_the_lexical_arm__S025_002_DoD9(engine: Engine) -> None:
    _insert_memo(engine, memo_id=MEMO_A_SHORT, user_id=USER_A, body=SHORT_BODY)
    _ensure_search_tables(engine)

    matches = _ranking(engine, MEMO_FTS_TABLE, MemoSearchScope(user_id=USER_A))

    assert MEMO_A_SHORT > SNOWFLAKE_FLOOR
    assert len(matches) == 1
    assert matches[0].id == MEMO_A_SHORT


def test_a_snowflake_id_round_trips_through_the_candidate_set__S025_002_DoD9(engine: Engine) -> None:
    _insert_record_row(engine, message_id=MESSAGE_A1, user_id=USER_A, session_id=SESSION_A1, body=SHORT_BODY)
    _ensure_search_tables(engine)

    assert MESSAGE_A1 > SNOWFLAKE_FLOOR
    assert _candidates(engine, EntrySearchScope(user_id=USER_A)) == {MESSAGE_A1}
    assert _ids(_ranking(engine, MESSAGE_FTS_TABLE, EntrySearchScope(user_id=USER_A))) == [MESSAGE_A1]


# --- DoD-10: an absent FTS table is empty, not an error (U2) -----------------------------


def test_an_absent_fts_table_yields_no_matches_and_no_error__S025_002_DoD10(engine: Engine) -> None:
    """The tables are never ensured here, so neither exists."""
    _insert_memo(engine, memo_id=MEMO_A_SHORT, user_id=USER_A, body=SHORT_BODY)
    _insert_record_row(engine, message_id=MESSAGE_A1, user_id=USER_A, session_id=SESSION_A1, body=SHORT_BODY)

    assert _ranking(engine, MEMO_FTS_TABLE, MemoSearchScope(user_id=USER_A)) == []
    assert _ranking(engine, MESSAGE_FTS_TABLE, EntrySearchScope(user_id=USER_A)) == []


def test_fts_table_exists_is_false_before_the_ensure_and_true_after__S025_002_DoD10(engine: Engine) -> None:
    with engine.connect() as connection:
        assert fts_table_exists(connection, MEMO_FTS_TABLE) is False
        assert fts_table_exists(connection, MESSAGE_FTS_TABLE) is False

    _ensure_search_tables(engine)

    with engine.connect() as connection:
        assert fts_table_exists(connection, MEMO_FTS_TABLE) is True
        assert fts_table_exists(connection, MESSAGE_FTS_TABLE) is True


# --- DoD-11: a none FTS expression short-circuits (`001.context.md`) ---------------------


def test_a_none_fts_expression_yields_no_matches__S025_002_DoD11(engine: Engine) -> None:
    """The table exists and holds a match, so `[]` can only come from the none guard."""
    _insert_memo(engine, memo_id=MEMO_A_SHORT, user_id=USER_A, body=SHORT_BODY)
    _ensure_search_tables(engine)

    assert _ranking(engine, MEMO_FTS_TABLE, MemoSearchScope(user_id=USER_A), None) == []
    assert _ranking(engine, MESSAGE_FTS_TABLE, EntrySearchScope(user_id=USER_A), None) == []
