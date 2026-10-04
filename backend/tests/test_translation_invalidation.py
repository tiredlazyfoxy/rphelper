"""Tests for feature 023, step 001 — the server-side discard of a message's cached
translations inside `edit_message_text`'s transaction.

Every expected value comes from
`docs/plans/023.partner-translation/001.table-error-model-invalidation.md` (DoD-6..9 and its
Interface intent), from `001.context.md` ("Built state at the touch sites", "Test shape")
and from the feature `context.md` (**D11**, US-111.AC-1, R5). No expected value is read from
the implementation.

Covers DoD-6 (the edited message's rows go, another message's row stays), DoD-7 (a refused
edit deletes nothing), DoD-8 (the delete rides inside the edit's transaction) and DoD-9 (a
settled turn and a zone row still edit and return as before). Each test name ends
`__S023_001_DoD<n>`.

Seeding follows feature 023's **Test conventions** and 012's service tests: a file-local
`engine` fixture applies the registry with `schema.metadata.create_all`, then raw-inserts
two users (isolation), a character and a session each, four `messages` rows of USER_A (two
settled partner rows, a buried row under a settled turn, a zone row) and one settled partner
row of USER_B. `translations` rows are raw-inserted. One connection per service call. **No
fixture is added to `conftest.py`.**
"""

from typing import Any

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError

from app.db import schema
from app.errors import MessageNotEditableError, MessageNotFoundError
from app.roles import Role
from app.services.messages import StreamMessage, edit_message_text

#: The seeded instant, in the schema's fixed-width timestamp form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
SETTLED_AT = "2026-01-01T00:00:01.000000+00:00"

USER_A = 101
USER_B = 202
CHAR_A = 1_001
CHAR_B = 2_001
SESSION_A = 5_001
SESSION_B = 6_001

#: Raw-seeded `messages` ids. Small, so nothing collides with a minted snowflake.
PARTNER_A = 11
PARTNER_A2 = 12
TURN_A = 13
BURIED_A = 14
ZONE_A = 15
PARTNER_B = 21

#: Raw-seeded `translations` ids.
CACHED_A_RUSSIAN = 901
CACHED_A_FRENCH = 902
CACHED_A2_RUSSIAN = 903
CACHED_BURIED = 904
CACHED_B = 905

PARTNER_A_TEXT = "She waits by the lighthouse."
PARTNER_A2_TEXT = "He answers from the jetty."
TURN_A_TEXT = "I nod and step closer."
BURIED_A_TEXT = "A buried draft."
ZONE_A_TEXT = "A zone draft."
PARTNER_B_TEXT = "Bob's settled partner entry."

EDITED_TEXT = "She waits by the pier instead."
EDITED_TURN_TEXT = "I nod, then step closer."
EDITED_ZONE_TEXT = "A zone draft, rewritten."
REFUSED_TEXT = "Text that must never land."

A2_CACHED_TEXT = "Он отвечает с причала."
BURIED_CACHED_TEXT = "A translation of a buried draft."
B_CACHED_TEXT = "Bob's cached translation."

#: DoD-8 — a `BEFORE DELETE` trigger on `translations` that always aborts, so a delete of a
#: cached row cannot succeed. Modelled on 006/003's `s006_003_block_server_delete`.
BLOCK_TRIGGER_NAME = "s023_001_block_translation_delete"
BLOCK_TRIGGER_DDL = (
    f"CREATE TRIGGER {BLOCK_TRIGGER_NAME} BEFORE DELETE ON translations "
    "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
)


# --- seeding ------------------------------------------------------------------------------


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


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    user_id: int,
    session_id: int,
    body: str,
    role: str = "user",
    kind: str | None = "partner",
    related_to: int | None = None,
    settled_at: str | None = SETTLED_AT,
) -> None:
    """Raw-insert one `messages` row in a chosen state (kind / settled_at / related_to)."""
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


def _insert_translation(
    engine: Engine,
    *,
    translation_id: int,
    user_id: int,
    message_id: int,
    target_language: str,
    body: str,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.metadata.tables["translations"].insert().values(
                id=translation_id,
                user_id=user_id,
                message_id=message_id,
                target_language=target_language,
                text=body,
                created_at=TIMESTAMP,
            )
        )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database: the registry, two owners with a character and a session each, and
    USER_A's stream (two settled partner rows, a settled turn with a row buried under it, a
    zone row) plus one settled partner row of USER_B."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob")
    _insert_character(db_engine, character_id=CHAR_A, user_id=USER_A, name="Aria")
    _insert_character(db_engine, character_id=CHAR_B, user_id=USER_B, name="Bob's own")
    _insert_session(db_engine, session_id=SESSION_A, user_id=USER_A, character_id=CHAR_A)
    _insert_session(db_engine, session_id=SESSION_B, user_id=USER_B, character_id=CHAR_B)

    _insert_message(
        db_engine, message_id=PARTNER_A, user_id=USER_A, session_id=SESSION_A, body=PARTNER_A_TEXT
    )
    _insert_message(
        db_engine, message_id=PARTNER_A2, user_id=USER_A, session_id=SESSION_A, body=PARTNER_A2_TEXT
    )
    _insert_message(
        db_engine,
        message_id=TURN_A,
        user_id=USER_A,
        session_id=SESSION_A,
        body=TURN_A_TEXT,
        kind="turn",
    )
    _insert_message(
        db_engine,
        message_id=BURIED_A,
        user_id=USER_A,
        session_id=SESSION_A,
        body=BURIED_A_TEXT,
        kind=None,
        related_to=TURN_A,
        settled_at=None,
    )
    _insert_message(
        db_engine,
        message_id=ZONE_A,
        user_id=USER_A,
        session_id=SESSION_A,
        body=ZONE_A_TEXT,
        kind=None,
        settled_at=None,
    )
    _insert_message(
        db_engine, message_id=PARTNER_B, user_id=USER_B, session_id=SESSION_B, body=PARTNER_B_TEXT
    )
    return db_engine


# --- the service call, and direct reads of stored state ------------------------------------


def _edit(engine: Engine, user_id: int, message_id: int, body: str) -> StreamMessage:
    with engine.connect() as connection:
        return edit_message_text(connection, user_id, message_id, body)


def _stored_message(engine: Engine, message_id: int) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            select(schema.messages).where(schema.messages.c.id == message_id)
        ).one()
    return dict(row._mapping)


def _translation_rows(engine: Engine) -> list[dict[str, Any]]:
    table = schema.metadata.tables["translations"]
    with engine.connect() as connection:
        rows = connection.execute(select(table).order_by(table.c.id)).all()
    return [dict(row._mapping) for row in rows]


def _translation_ids(engine: Engine) -> set[int]:
    return {int(row["id"]) for row in _translation_rows(engine)}


def _install_block_trigger(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(BLOCK_TRIGGER_DDL))


def _seed_partner_a_cache(engine: Engine) -> None:
    """PARTNER_A cached in two languages, PARTNER_A2 cached in one (DoD-6)."""
    _insert_translation(
        engine,
        translation_id=CACHED_A_RUSSIAN,
        user_id=USER_A,
        message_id=PARTNER_A,
        target_language="Russian",
        body="Она ждёт у маяка.",
    )
    _insert_translation(
        engine,
        translation_id=CACHED_A_FRENCH,
        user_id=USER_A,
        message_id=PARTNER_A,
        target_language="French",
        body="Elle attend près du phare.",
    )
    _insert_translation(
        engine,
        translation_id=CACHED_A2_RUSSIAN,
        user_id=USER_A,
        message_id=PARTNER_A2,
        target_language="Russian",
        body=A2_CACHED_TEXT,
    )


# ====================================================================== DoD-6
# US-111.AC-1 / D11 — editing a partner block discards its cached translations, and only
# its own.


def test_editing_a_partner_entry_discards_both_of_its_cached_translations__S023_001_DoD6(
    engine: Engine,
) -> None:
    """DoD-6 — a settled partner row cached in two languages is edited; afterwards both of
    its `translations` rows are gone (US-111.AC-1)."""
    _seed_partner_a_cache(engine)

    edited = _edit(engine, USER_A, PARTNER_A, EDITED_TEXT)

    assert edited.id == PARTNER_A
    assert edited.text == EDITED_TEXT
    assert _stored_message(engine, PARTNER_A)["text"] == EDITED_TEXT
    assert CACHED_A_RUSSIAN not in _translation_ids(engine)
    assert CACHED_A_FRENCH not in _translation_ids(engine)
    assert [row for row in _translation_rows(engine) if row["message_id"] == PARTNER_A] == []


def test_the_discard_leaves_another_messages_cached_translation_alone__S023_001_DoD6(
    engine: Engine,
) -> None:
    """DoD-6 — the delete is scoped to the edited id: a `translations` row belonging to a
    different message is untouched, contents included (D11)."""
    _seed_partner_a_cache(engine)
    before = [row for row in _translation_rows(engine) if row["message_id"] == PARTNER_A2]

    _edit(engine, USER_A, PARTNER_A, EDITED_TEXT)

    assert _translation_ids(engine) == {CACHED_A2_RUSSIAN}
    after = [row for row in _translation_rows(engine) if row["message_id"] == PARTNER_A2]
    assert after == before
    assert after[0]["target_language"] == "Russian"
    assert after[0]["text"] == A2_CACHED_TEXT
    assert _stored_message(engine, PARTNER_A2)["text"] == PARTNER_A2_TEXT


def test_the_next_read_of_the_edited_message_finds_no_cached_translation__S023_001_DoD6(
    engine: Engine,
) -> None:
    """DoD-6 — US-111.AC-2's premise: after the edit, no cached row exists for the edited
    message in either language, so the next flick is a cache miss."""
    _seed_partner_a_cache(engine)

    _edit(engine, USER_A, PARTNER_A, EDITED_TEXT)

    pairs = {(row["message_id"], row["target_language"]) for row in _translation_rows(engine)}
    assert (PARTNER_A, "Russian") not in pairs
    assert (PARTNER_A, "French") not in pairs


# ====================================================================== DoD-7
# D11 / R5 — a refused edit deletes nothing, on both refusal paths.


def test_a_refused_edit_of_a_buried_row_deletes_nothing__S023_001_DoD7(engine: Engine) -> None:
    """DoD-7 — a buried row raises `MessageNotEditableError`, and its raw-inserted
    `translations` row is still there (D11)."""
    _insert_translation(
        engine,
        translation_id=CACHED_BURIED,
        user_id=USER_A,
        message_id=BURIED_A,
        target_language="Russian",
        body=BURIED_CACHED_TEXT,
    )
    before = _translation_rows(engine)

    with pytest.raises(MessageNotEditableError) as caught:
        _edit(engine, USER_A, BURIED_A, REFUSED_TEXT)
    assert caught.value.code == "message_not_editable"

    assert _translation_rows(engine) == before
    assert _translation_ids(engine) == {CACHED_BURIED}
    assert _stored_message(engine, BURIED_A)["text"] == BURIED_A_TEXT


def test_a_refused_edit_of_another_users_row_deletes_nothing__S023_001_DoD7(
    engine: Engine,
) -> None:
    """DoD-7 — another user's settled partner row raises `MessageNotFoundError` (R5: a
    foreign row is indistinguishable from a missing one), and that owner's cached
    translation survives (D11)."""
    _insert_translation(
        engine,
        translation_id=CACHED_B,
        user_id=USER_B,
        message_id=PARTNER_B,
        target_language="Russian",
        body=B_CACHED_TEXT,
    )
    before = _translation_rows(engine)

    with pytest.raises(MessageNotFoundError) as caught:
        _edit(engine, USER_A, PARTNER_B, REFUSED_TEXT)
    assert caught.value.code == "message_not_found"

    assert _translation_rows(engine) == before
    assert _translation_ids(engine) == {CACHED_B}
    assert _stored_message(engine, PARTNER_B)["text"] == PARTNER_B_TEXT


# ====================================================================== DoD-8
# D11 — atomicity: the edit and the discard commit or fail together.


def test_a_blocked_discard_rolls_the_whole_edit_back__S023_001_DoD8(engine: Engine) -> None:
    """DoD-8 — with a `BEFORE DELETE` trigger on `translations` that aborts, the edit of a
    partner row with a cached translation fails; afterwards the message text is unchanged
    **and** the cached row is still present, which is what proves the delete rides inside the
    edit's transaction (D11)."""
    _insert_translation(
        engine,
        translation_id=CACHED_A_RUSSIAN,
        user_id=USER_A,
        message_id=PARTNER_A,
        target_language="Russian",
        body="Она ждёт у маяка.",
    )
    message_before = _stored_message(engine, PARTNER_A)
    translations_before = _translation_rows(engine)
    _install_block_trigger(engine)

    with pytest.raises(DBAPIError):
        _edit(engine, USER_A, PARTNER_A, EDITED_TEXT)

    assert _stored_message(engine, PARTNER_A)["text"] == PARTNER_A_TEXT
    assert _stored_message(engine, PARTNER_A) == message_before
    assert _translation_rows(engine) == translations_before
    assert _translation_ids(engine) == {CACHED_A_RUSSIAN}


# ====================================================================== DoD-9
# D11 / 014 D1 — the regression clause: rows with no cached translations edit exactly as
# they did before this step.


def test_editing_a_settled_turn_still_succeeds_and_returns_the_row__S023_001_DoD9(
    engine: Engine,
) -> None:
    """DoD-9 — a settled turn has no `translations` rows, so the discard is a no-op: the edit
    succeeds and returns the edited row as before (014 D1)."""
    edited = _edit(engine, USER_A, TURN_A, EDITED_TURN_TEXT)

    assert isinstance(edited, StreamMessage)
    assert edited.id == TURN_A
    assert edited.session_id == SESSION_A
    assert edited.role == "user"
    assert edited.kind == "turn"
    assert edited.settled_at == SETTLED_AT
    assert edited.text == EDITED_TURN_TEXT
    assert edited.created_at == TIMESTAMP
    assert edited.updated_at >= TIMESTAMP
    assert _stored_message(engine, TURN_A)["text"] == EDITED_TURN_TEXT
    assert _translation_rows(engine) == []


def test_editing_a_zone_row_still_succeeds_and_returns_the_row__S023_001_DoD9(
    engine: Engine,
) -> None:
    """DoD-9 — a zone row has no `translations` rows either: the edit succeeds, the state
    columns stay NULL and the row comes back as before (014 D1)."""
    edited = _edit(engine, USER_A, ZONE_A, EDITED_ZONE_TEXT)

    assert isinstance(edited, StreamMessage)
    assert edited.id == ZONE_A
    assert edited.session_id == SESSION_A
    assert edited.role == "user"
    assert edited.kind is None
    assert edited.settled_at is None
    assert edited.text == EDITED_ZONE_TEXT
    assert edited.created_at == TIMESTAMP
    assert edited.updated_at >= TIMESTAMP
    assert _stored_message(engine, ZONE_A)["text"] == EDITED_ZONE_TEXT
    assert _translation_rows(engine) == []


def test_an_edit_with_no_cached_rows_anywhere_leaves_the_table_empty__S023_001_DoD9(
    engine: Engine,
) -> None:
    """DoD-9 — editing a partner row that was never translated is the same no-op: nothing is
    deleted because nothing is cached (D11)."""
    edited = _edit(engine, USER_A, PARTNER_A, EDITED_TEXT)

    assert edited.text == EDITED_TEXT
    assert _stored_message(engine, PARTNER_A)["text"] == EDITED_TEXT
    assert _translation_rows(engine) == []
