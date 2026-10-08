"""`services/search/session_search.py` — feature 027, step 002 (DoD-1..10).

The owner-scoped excerpt read: `SessionExcerpt` and `list_session_excerpts`.

Every expected value comes from the **spec**, never from the implementation:
`docs/plans/027.session-search-tool/002.session-excerpts.md` (Interface intent and Definition
of done), `002.context.md` (the touch sites and the test-seeding notes) and the feature
`context.md` — **D3** (the excerpt is the settled entries' text in ascending id order joined by
`"\\n\\n"`, empties skipped; over `1500` characters it becomes `…` plus the last `1500`;
the date is `created_at` as a UTC calendar date, a naive stored value taken as UTC; an archived
setup still shows its name), **D4** (input order, owner scope, silent drops, empty input runs no
query, no transaction left open), **R5**, **R6**, **R11** and the literals table (`excerpt
length` = `1500`, `truncation marker` = `…`, `excerpt entry separator` = `"\\n\\n"`).

Bindings come from `## Skeleton` → "Step 002 — frozen interface (2026-10-05)" in `status.md`:

    @dataclass(frozen=True)
    class SessionExcerpt:
        session_id: int
        created_date: date        # datetime.date — already parsed, already reduced
        setup_name: str | None
        excerpt: str

    list_session_excerpts(connection, user_id, session_ids) -> list[SessionExcerpt]

Step `001`'s constants, `past_session_predicate` and `search_sessions` are tested in
`tests/test_session_search_service.py` and are not touched here. Step `003`'s formatter — the
header line, the block separator and the `(no settled entries)` substitution — is **not** this
read's job, so DoD-7 expects an empty excerpt string, not that literal.

How the expectations are derived
--------------------------------
Nothing here asks the code under test what the answer is.

* **No vectors, no designated model, no embedder.** This read is plain SQL over seeded rows
  (`002.context.md` "Test seeding notes"), so every row is raw-inserted and every expected value
  is computed from the seeded strings.
* **Order is pinned against an order nothing else could produce.** The three DoD-1 sessions are
  seeded so that ascending-id order (`X, Y, Z`), ascending-creation order (`Y, Z, X`) and the
  requested order (`Z, X, Y`) are three different permutations, and each record is matched to
  its own excerpt, so a record list in the right order cannot be a coincidence.
* **DoD-6's expected tails are computed from the seeded entry strings**, never from the code:
  the joined text is rebuilt in the test with the same `"\\n\\n"` separator the spec names
  (the separator counts toward the length), and the expectation is the literal `…` prepended to
  that string's own last 1500 characters.
* **The decision kind literal is the one the built `messages` table is written with** —
  `"decision"` — and no kind filter is expected on top of `settled_entries` (R11), so the
  decision's text must be in the excerpt.

Each test name ends `__S027_002_DoD<n>` with the DoD item it covers.

Mechanics (`context.md` "Test conventions"): a real SQLite file per test through the shared
`db_engine` fixture (`tests/conftest.py` and `tests/llm_fakes.py` are untouched), raw inserts
only, ids above 2^60, two users A and B, and every helper file-local.
"""

from collections.abc import Iterator, Sequence
from dataclasses import fields
from datetime import date

import pytest
from sqlalchemy import Connection, Engine

from app.db import schema
from app.roles import Role
from app.services.search.session_search import SessionExcerpt, list_session_excerpts

#: The seeded instant, in the project's fixed-width UTC text form
#: (`sessions.py:_now_text` — aware ISO-8601, `+00:00`, six fractional digits).
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: The instant rows seeded already settled carry.
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"

# Every id below is above 2^60 = 1152921504606846976 (snowflake-sized keys).
USER_A = 1_300_000_000_000_000_001
USER_B = 1_300_000_000_000_000_002

CHAR_A = 1_300_000_000_000_000_011
CHAR_B = 1_300_000_000_000_000_012
CHAR_MARKED = 1_300_000_000_000_000_013

SETUP_HARBOUR = 1_300_000_000_000_000_021
SETUP_ARCHIVED = 1_300_000_000_000_000_022
SETUP_MARKED = 1_300_000_000_000_000_023
SETUP_B = 1_300_000_000_000_000_024

SESSION_X = 1_300_000_000_000_000_101
SESSION_Y = 1_300_000_000_000_000_102
SESSION_Z = 1_300_000_000_000_000_103
SESSION_OF_B = 1_300_000_000_000_000_104
SESSION_DATED = 1_300_000_000_000_000_105
SESSION_NAIVE = 1_300_000_000_000_000_106
SESSION_WITH_SETUP = 1_300_000_000_000_000_107
SESSION_NO_SETUP = 1_300_000_000_000_000_108
SESSION_ARCHIVED_SETUP = 1_300_000_000_000_000_109
SESSION_ENTRIES = 1_300_000_000_000_000_110
SESSION_EXACT = 1_300_000_000_000_000_111
SESSION_OVER = 1_300_000_000_000_000_112
SESSION_LONG = 1_300_000_000_000_000_113
SESSION_UNSETTLED = 1_300_000_000_000_000_114
SESSION_EDITED = 1_300_000_000_000_000_115
SESSION_MARKED = 1_300_000_000_000_000_116
SESSION_TXN = 1_300_000_000_000_000_117

#: Never seeded — DoD-2's id that matches no session.
UNSEEDED_SESSION = 1_300_000_000_000_000_999

#: Message ids are this base plus a per-test offset.
MSG_BASE = 1_300_000_000_000_000_300

#: The three DoD-1 creation instants: ascending creation order is `Y, Z, X`, which is neither
#: ascending-id order (`X, Y, Z`) nor the order DoD-1 asks for (`Z, X, Y`).
CREATED_X = "2026-01-03T00:00:00.000000+00:00"
CREATED_Y = "2026-01-01T00:00:00.000000+00:00"
CREATED_Z = "2026-01-02T00:00:00.000000+00:00"

TEXT_X = "Ex line."
TEXT_Y = "Why line."
TEXT_Z = "Zed line."

#: D3's literals.
SEPARATOR = "\n\n"
TRUNCATION_MARKER = "…"
EXCERPT_CHARS = 1500

#: The `messages.kind` literals the built table is written with.
KIND_TURN = "turn"
KIND_DECISION = "decision"

#: DoD-3's setup name, verbatim.
HARBOUR_NIGHT = "Harbour Night"

#: DoD-5's four rows: three settled (turn, decision, turn) around one unsettled row, whose id
#: sits in the middle so that id order is observable.
ENTRY_FIRST = "The first settled turn."
ENTRY_DECISION = "((Skip ahead to the harbour.))"
ENTRY_UNSETTLED = "An unsettled zone line."
ENTRY_LAST = "The third settled turn."

#: DoD-6, case "exactly 1500": 749 + len(SEPARATOR) + 749 == 1500.
EXACT_FIRST = "a" * 749
EXACT_SECOND = "b" * 749
EXACT_JOINED = EXACT_FIRST + SEPARATOR + EXACT_SECOND

#: DoD-6, case "1501": 749 + len(SEPARATOR) + 750 == 1501.
OVER_FIRST = "c" * 749
OVER_SECOND = "d" * 750
OVER_JOINED = OVER_FIRST + SEPARATOR + OVER_SECOND

#: DoD-6, case "several thousand characters". The marker word sits only at the very start of the
#: first entry, far outside the last 1500 characters.
LONG_MARKER = "zarquon"
LONG_FIRST = LONG_MARKER + " " + "e" * 2000
LONG_SECOND = "f" * 2000
LONG_LAST = "The last settled line of a very long session."
LONG_JOINED = SEPARATOR.join([LONG_FIRST, LONG_SECOND, LONG_LAST])

#: DoD-8's edit.
TEXT_BEFORE_EDIT = "The keeper waits by the old pier."
TEXT_AFTER_EDIT = "The keeper waits by the new pier."

#: DoD-10's two markers, one per field that must not leak.
PERSONA_MARKER = "zygomorph"
DESCRIPTION_MARKER = "quibbleflux"
MARKED_SHEET = f"A persona containing {PERSONA_MARKER} as its only oddity."
MARKED_DESCRIPTION = f"A scene containing {DESCRIPTION_MARKER} as its only oddity."
MARKED_ENTRY = "A plain settled line."


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
    user_id: int = USER_A,
    character_id: int = CHAR_A,
    name: str,
    description: str = "An ordinary scene.",
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
    character_id: int = CHAR_A,
    setup_id: int | None = None,
    archived_at: str | None = None,
    created_at: str = TIMESTAMP,
) -> None:
    """Raw-insert one `sessions` row (no title and no partner column exist to seed)."""
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
    text: str,
    user_id: int = USER_A,
    role: str = "user",
    kind: str | None = None,
    related_to: int | None = None,
    settled_at: str | None = None,
) -> None:
    """Raw-insert one `messages` row in a chosen state (settled, zone or buried)."""
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=message_id,
                user_id=user_id,
                session_id=session_id,
                role=role,
                kind=kind,
                text=text,
                related_to=related_to,
                settled_at=settled_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _settled(
    engine: Engine,
    message_id: int,
    text: str,
    *,
    session_id: int,
    user_id: int = USER_A,
    kind: str | None = KIND_TURN,
) -> None:
    """One row of the settled record."""
    _insert_message(
        engine,
        message_id=message_id,
        session_id=session_id,
        text=text,
        user_id=user_id,
        kind=kind,
        settled_at=SEEDED_SETTLED_AT,
    )


def _zone(engine: Engine, message_id: int, text: str, *, session_id: int, user_id: int = USER_A) -> None:
    """One current-zone row: `settled_at` null, so it is not in `settled_entries`."""
    _insert_message(engine, message_id=message_id, session_id=session_id, text=text, user_id=user_id)


def _rewrite_message_text(engine: Engine, message_id: int, text: str) -> None:
    """A raw `messages` update, made without any service (DoD-8's edit)."""
    with engine.begin() as connection:
        connection.execute(schema.messages.update().where(schema.messages.c.id == message_id).values(text=text))


def _read(engine: Engine, user_id: int, session_ids: Sequence[int]) -> list[SessionExcerpt]:
    with engine.connect() as connection:
        return list_session_excerpts(connection, user_id, session_ids)


def _ids(records: Sequence[SessionExcerpt]) -> list[int]:
    return [record.session_id for record in records]


def _one(records: Sequence[SessionExcerpt]) -> SessionExcerpt:
    assert len(records) == 1
    return records[0]


def _assert_no_open_transaction(connection: Connection) -> None:
    assert not connection.in_transaction()
    transaction = connection.begin()
    transaction.rollback()


@pytest.fixture
def engine(db_engine: Engine) -> Iterator[Engine]:
    """The schema applied, two owners and their characters. Setups and sessions are per test."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob")
    _insert_character(db_engine, character_id=CHAR_A, user_id=USER_A, name="Aria", sheet="Persona A.")
    _insert_character(db_engine, character_id=CHAR_B, user_id=USER_B, name="Brynn", sheet="Persona B.")
    _insert_character(db_engine, character_id=CHAR_MARKED, user_id=USER_A, name="Marked", sheet=MARKED_SHEET)
    yield db_engine


def _seed_three_sessions(engine: Engine) -> None:
    """A's X, Y and Z, with distinct creation instants and one distinct settled line each."""
    _insert_session(engine, session_id=SESSION_X, created_at=CREATED_X)
    _insert_session(engine, session_id=SESSION_Y, created_at=CREATED_Y)
    _insert_session(engine, session_id=SESSION_Z, created_at=CREATED_Z)
    _settled(engine, MSG_BASE + 1, TEXT_X, session_id=SESSION_X)
    _settled(engine, MSG_BASE + 2, TEXT_Y, session_id=SESSION_Y)
    _settled(engine, MSG_BASE + 3, TEXT_Z, session_id=SESSION_Z)


# --- DoD-1: order preserved ---------------------------------------------------------------


def test_the_records_come_back_in_the_requested_id_order__S027_002_DoD1(engine: Engine) -> None:
    """DoD-1 — the read with `[Z, X, Y]` answers in exactly that order (D4).

    Ascending-id order is `X, Y, Z` and ascending-creation order is `Y, Z, X`, so neither an
    id sort nor a date sort could produce this list. Each record is matched to its own excerpt,
    so the pairing is checked as well as the sequence.
    """
    _seed_three_sessions(engine)

    records = _read(engine, USER_A, [SESSION_Z, SESSION_X, SESSION_Y])

    assert _ids(records) == [SESSION_Z, SESSION_X, SESSION_Y]
    assert [record.excerpt for record in records] == [TEXT_Z, TEXT_X, TEXT_Y]


# --- DoD-2: owner scope and silent drops --------------------------------------------------


def test_another_users_session_id_is_dropped__S027_002_DoD2(engine: Engine) -> None:
    """DoD-2 — given A's id and B's, the read for A answers with A's record only (R5)."""
    _insert_session(engine, session_id=SESSION_X, created_at=CREATED_X)
    _settled(engine, MSG_BASE + 1, TEXT_X, session_id=SESSION_X)
    _insert_setup(engine, setup_id=SETUP_B, user_id=USER_B, character_id=CHAR_B, name="B's scene")
    _insert_session(engine, session_id=SESSION_OF_B, user_id=USER_B, character_id=CHAR_B, setup_id=SETUP_B)
    _settled(engine, MSG_BASE + 4, "B's settled line.", session_id=SESSION_OF_B, user_id=USER_B)

    records = _read(engine, USER_A, [SESSION_X, SESSION_OF_B])

    assert _ids(records) == [SESSION_X]
    assert _one(records).excerpt == TEXT_X


def test_the_other_user_gets_nothing_for_as_session_id__S027_002_DoD2(engine: Engine) -> None:
    """DoD-2 — the read for B, given A's id alone, answers `[]` (R5, US-069.AC-2)."""
    _insert_session(engine, session_id=SESSION_X, created_at=CREATED_X)
    _settled(engine, MSG_BASE + 1, TEXT_X, session_id=SESSION_X)

    assert _read(engine, USER_B, [SESSION_X]) == []


def test_an_id_matching_no_session_is_dropped_silently__S027_002_DoD2(engine: Engine) -> None:
    """DoD-2 — an unseeded id beside A's ids is dropped; A's records stay intact and in order."""
    _seed_three_sessions(engine)

    records = _read(engine, USER_A, [SESSION_Z, UNSEEDED_SESSION, SESSION_X, SESSION_Y])

    assert _ids(records) == [SESSION_Z, SESSION_X, SESSION_Y]
    assert [record.excerpt for record in records] == [TEXT_Z, TEXT_X, TEXT_Y]


def test_an_empty_id_list_gives_an_empty_result__S027_002_DoD2(engine: Engine) -> None:
    """DoD-2 — an empty input gives an empty list (D4)."""
    _seed_three_sessions(engine)

    assert _read(engine, USER_A, []) == []


# --- DoD-3: header fields -----------------------------------------------------------------


def test_the_setup_name_is_returned_for_a_session_with_a_setup__S027_002_DoD3(engine: Engine) -> None:
    """DoD-3 — a session whose setup is named `Harbour Night` reports that name (D3)."""
    _insert_setup(engine, setup_id=SETUP_HARBOUR, name=HARBOUR_NIGHT)
    _insert_session(engine, session_id=SESSION_WITH_SETUP, setup_id=SETUP_HARBOUR)

    record = _one(_read(engine, USER_A, [SESSION_WITH_SETUP]))

    assert record.setup_name == HARBOUR_NIGHT


def test_a_setupless_session_reports_no_setup_name__S027_002_DoD3(engine: Engine) -> None:
    """DoD-3 — a session with no setup reports `None`, and still gets a record (D3)."""
    _insert_session(engine, session_id=SESSION_NO_SETUP, setup_id=None)

    record = _one(_read(engine, USER_A, [SESSION_NO_SETUP]))

    assert record.setup_name is None
    assert record.session_id == SESSION_NO_SETUP


def test_the_creation_date_is_the_utc_calendar_date__S027_002_DoD3(engine: Engine) -> None:
    """DoD-3 — `2026-03-14T23:30:00Z` reduces to the calendar date 2026-03-14 (D3).

    Seeded in the stored form `sessions.py:_now_text` writes: aware ISO-8601 with an explicit
    `+00:00` offset and six fractional digits.
    """
    _insert_session(engine, session_id=SESSION_DATED, created_at="2026-03-14T23:30:00.000000+00:00")

    record = _one(_read(engine, USER_A, [SESSION_DATED]))

    assert record.created_date == date(2026, 3, 14)


def test_a_naive_created_at_is_taken_as_utc__S027_002_DoD3(engine: Engine) -> None:
    """DoD-3 — a stored value with no offset is read as UTC, not rejected (Interface intent)."""
    _insert_session(engine, session_id=SESSION_NAIVE, created_at="2026-03-14T23:30:00.000000")

    record = _one(_read(engine, USER_A, [SESSION_NAIVE]))

    assert record.created_date == date(2026, 3, 14)


# --- DoD-4: an archived setup still names itself ------------------------------------------


def test_an_archived_setups_name_is_still_returned__S027_002_DoD4(engine: Engine) -> None:
    """DoD-4 — archiving never destroys: the setup's name still labels its session (D3, R6)."""
    _insert_setup(
        engine,
        setup_id=SETUP_ARCHIVED,
        name=HARBOUR_NIGHT,
        archived_at="2026-02-02T00:00:00.000000+00:00",
    )
    _insert_session(engine, session_id=SESSION_ARCHIVED_SETUP, setup_id=SETUP_ARCHIVED)

    record = _one(_read(engine, USER_A, [SESSION_ARCHIVED_SETUP]))

    assert record.setup_name == HARBOUR_NIGHT


# --- DoD-5: excerpt content and order ----------------------------------------------------


def test_the_excerpt_is_the_settled_texts_in_id_order__S027_002_DoD5(engine: Engine) -> None:
    """DoD-5 — the three settled texts in ascending id order, joined by `"\\n\\n"` (D3, R11).

    The decision row is settled, so its text is in (`settled_entries` carries no kind filter and
    none is added — US-122.AC-2's excerpt half). The zone row, whose id sits between two settled
    rows, is not settled and so is absent.
    """
    _insert_session(engine, session_id=SESSION_ENTRIES)
    _settled(engine, MSG_BASE + 11, ENTRY_FIRST, session_id=SESSION_ENTRIES, kind=KIND_TURN)
    _settled(engine, MSG_BASE + 12, ENTRY_DECISION, session_id=SESSION_ENTRIES, kind=KIND_DECISION)
    _zone(engine, MSG_BASE + 13, ENTRY_UNSETTLED, session_id=SESSION_ENTRIES)
    _settled(engine, MSG_BASE + 14, ENTRY_LAST, session_id=SESSION_ENTRIES, kind=KIND_TURN)

    record = _one(_read(engine, USER_A, [SESSION_ENTRIES]))

    assert record.excerpt == SEPARATOR.join([ENTRY_FIRST, ENTRY_DECISION, ENTRY_LAST])
    assert ENTRY_DECISION in record.excerpt
    assert ENTRY_UNSETTLED not in record.excerpt


def test_a_settled_row_with_empty_text_adds_no_separator__S027_002_DoD5(engine: Engine) -> None:
    """DoD-5 — an empty settled text is skipped, so the joined text is byte-identical (D3)."""
    _insert_session(engine, session_id=SESSION_ENTRIES)
    _settled(engine, MSG_BASE + 11, ENTRY_FIRST, session_id=SESSION_ENTRIES, kind=KIND_TURN)
    _settled(engine, MSG_BASE + 12, ENTRY_DECISION, session_id=SESSION_ENTRIES, kind=KIND_DECISION)
    _settled(engine, MSG_BASE + 14, ENTRY_LAST, session_id=SESSION_ENTRIES, kind=KIND_TURN)
    expected = SEPARATOR.join([ENTRY_FIRST, ENTRY_DECISION, ENTRY_LAST])
    assert _one(_read(engine, USER_A, [SESSION_ENTRIES])).excerpt == expected

    _settled(engine, MSG_BASE + 15, "", session_id=SESSION_ENTRIES, kind=KIND_TURN)

    assert _one(_read(engine, USER_A, [SESSION_ENTRIES])).excerpt == expected


# --- DoD-6: the bound and the marker -----------------------------------------------------


def test_a_joined_text_of_exactly_1500_is_unchanged__S027_002_DoD6(engine: Engine) -> None:
    """DoD-6 — exactly 1500 characters is not longer than the bound, so no marker appears (D3).

    The two seeded entries are 749 characters each and the separator is 2, so the joined text
    the spec describes is 1500 characters long.
    """
    assert len(EXACT_JOINED) == EXCERPT_CHARS
    _insert_session(engine, session_id=SESSION_EXACT)
    _settled(engine, MSG_BASE + 21, EXACT_FIRST, session_id=SESSION_EXACT)
    _settled(engine, MSG_BASE + 22, EXACT_SECOND, session_id=SESSION_EXACT)

    record = _one(_read(engine, USER_A, [SESSION_EXACT]))

    assert record.excerpt == EXACT_JOINED
    assert TRUNCATION_MARKER not in record.excerpt
    assert len(record.excerpt) == EXCERPT_CHARS


def test_a_joined_text_of_1501_is_marked_and_tail_cut__S027_002_DoD6(engine: Engine) -> None:
    """DoD-6 — 1501 characters gives `…` plus the last 1500, 1501 characters in all (D3).

    The marker is one character and replaces nothing, so the result is exactly as long as the
    joined text it cut. The expected tail is sliced from the seeded strings, never read back.
    """
    assert len(OVER_JOINED) == EXCERPT_CHARS + 1
    _insert_session(engine, session_id=SESSION_OVER)
    _settled(engine, MSG_BASE + 23, OVER_FIRST, session_id=SESSION_OVER)
    _settled(engine, MSG_BASE + 24, OVER_SECOND, session_id=SESSION_OVER)

    record = _one(_read(engine, USER_A, [SESSION_OVER]))

    assert record.excerpt == TRUNCATION_MARKER + OVER_JOINED[-EXCERPT_CHARS:]
    assert len(record.excerpt) == EXCERPT_CHARS + 1


def test_a_long_session_keeps_only_its_marked_tail__S027_002_DoD6(engine: Engine) -> None:
    """DoD-6 — a several-thousand-character session is cut from the end (D3).

    The excerpt opens with the marker, closes with the last settled entry's text, and has lost
    the marker word that was placed only at the start of the first entry.
    """
    assert len(LONG_JOINED) > 4000
    _insert_session(engine, session_id=SESSION_LONG)
    _settled(engine, MSG_BASE + 25, LONG_FIRST, session_id=SESSION_LONG)
    _settled(engine, MSG_BASE + 26, LONG_SECOND, session_id=SESSION_LONG)
    _settled(engine, MSG_BASE + 27, LONG_LAST, session_id=SESSION_LONG)

    record = _one(_read(engine, USER_A, [SESSION_LONG]))

    assert record.excerpt.startswith(TRUNCATION_MARKER)
    assert record.excerpt.endswith(LONG_LAST)
    assert LONG_MARKER not in record.excerpt
    assert record.excerpt == TRUNCATION_MARKER + LONG_JOINED[-EXCERPT_CHARS:]


# --- DoD-7: no settled entries -----------------------------------------------------------


def test_a_session_with_no_settled_rows_gets_an_empty_excerpt__S027_002_DoD7(engine: Engine) -> None:
    """DoD-7 — a record is still produced, with an empty excerpt (D3).

    The `(no settled entries)` body is step `003`'s formatter substitution, not this read's.
    """
    _insert_session(engine, session_id=SESSION_UNSETTLED)
    _zone(engine, MSG_BASE + 31, ENTRY_UNSETTLED, session_id=SESSION_UNSETTLED)

    record = _one(_read(engine, USER_A, [SESSION_UNSETTLED]))

    assert record.session_id == SESSION_UNSETTLED
    assert record.excerpt == ""


# --- DoD-8: the excerpt is read live -----------------------------------------------------


def test_an_edited_settled_row_shows_its_new_text__S027_002_DoD8(engine: Engine) -> None:
    """DoD-8 — the excerpt is read live, so it carries the current text (US-109/110.AC-2 half).

    The re-embed half of those criteria is 024's and is not tested here.
    """
    _insert_session(engine, session_id=SESSION_EDITED)
    _settled(engine, MSG_BASE + 41, TEXT_BEFORE_EDIT, session_id=SESSION_EDITED)
    assert _one(_read(engine, USER_A, [SESSION_EDITED])).excerpt == TEXT_BEFORE_EDIT

    _rewrite_message_text(engine, MSG_BASE + 41, TEXT_AFTER_EDIT)

    record = _one(_read(engine, USER_A, [SESSION_EDITED]))
    assert record.excerpt == TEXT_AFTER_EDIT
    assert TEXT_BEFORE_EDIT not in record.excerpt


# --- DoD-9: no transaction left open -----------------------------------------------------


def test_a_read_leaves_no_transaction_in_progress__S027_002_DoD9(engine: Engine) -> None:
    """DoD-9 — the ordinary exit ends the autobegun transaction (D4, D5).

    A later `begin()` on the same connection must still work, which is what the second half of
    the check proves.
    """
    _insert_session(engine, session_id=SESSION_TXN)
    _settled(engine, MSG_BASE + 51, ENTRY_FIRST, session_id=SESSION_TXN)

    with engine.connect() as connection:
        records = list_session_excerpts(connection, USER_A, [SESSION_TXN])

        assert _ids(records) == [SESSION_TXN]
        _assert_no_open_transaction(connection)


def test_the_empty_input_read_leaves_no_transaction_in_progress__S027_002_DoD9(engine: Engine) -> None:
    """DoD-9 — the empty-input case runs no query and so leaves nothing open (D4)."""
    with engine.connect() as connection:
        assert list_session_excerpts(connection, USER_A, []) == []

        _assert_no_open_transaction(connection)


# --- DoD-10: nothing else leaks ----------------------------------------------------------


def test_neither_the_persona_nor_the_setup_description_leaks__S027_002_DoD10(engine: Engine) -> None:
    """DoD-10 — the record carries four fields and neither marker word is in any of them (D3).

    The persona is the same character already in the discussion's context, and the setup's
    description is not part of the excerpt; only the setup's *name* is a header field.
    """
    _insert_setup(
        engine,
        setup_id=SETUP_MARKED,
        character_id=CHAR_MARKED,
        name=HARBOUR_NIGHT,
        description=MARKED_DESCRIPTION,
    )
    _insert_session(engine, session_id=SESSION_MARKED, character_id=CHAR_MARKED, setup_id=SETUP_MARKED)
    _settled(engine, MSG_BASE + 61, MARKED_ENTRY, session_id=SESSION_MARKED)

    record = _one(_read(engine, USER_A, [SESSION_MARKED]))

    values = [getattr(record, field.name) for field in fields(SessionExcerpt)]
    assert len(values) == 4
    for value in values:
        assert PERSONA_MARKER not in str(value)
        assert DESCRIPTION_MARKER not in str(value)
    assert record.excerpt == MARKED_ENTRY
    assert record.setup_name == HARBOUR_NIGHT
