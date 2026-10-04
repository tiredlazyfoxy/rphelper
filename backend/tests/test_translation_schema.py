"""Tests for feature 023, step 001 — the `translations` table, `TranslationFailedError`
and `TranslationResponse`.

Every expected value comes from
`docs/plans/023.partner-translation/001.table-error-model-invalidation.md` (DoD-1, DoD-2,
DoD-4, DoD-5 and its Interface intent), from `001.context.md` ("Default message", "Test
shape") and from the feature `context.md` (**D5**, **D7** and the **Wire contract**). No
expected value is read from the implementation.

Covers DoD-1 (the declared and created shape), DoD-2 (the unique pair), DoD-4 (the error)
and DoD-5 (the response model's serialisation). Each test name ends
`__S023_001_DoD<n>`.

Seeding follows feature 023's **Test conventions**: a file-local `engine` fixture applies
the registry with `schema.metadata.create_all` and raw-inserts the FK chain (two users for
isolation, a character, a session, two settled partner messages). **No fixture is added to
`conftest.py`.**
"""

import json
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import Engine, Table, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.db import schema
from app.errors import DomainError, TranslationFailedError
from app.models.translation import TranslationResponse
from app.roles import Role

#: The seeded instant, in the schema's fixed-width timestamp form (001.context.md).
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
SETTLED_AT = "2026-01-01T00:00:01.000000+00:00"

USER_A = 101
USER_B = 202
CHAR_A = 1_001
SESSION_A = 5_001

#: Raw-seeded `messages` ids, both settled partner rows of USER_A.
MESSAGE_A = 11
MESSAGE_A2 = 12

#: D7 — the table's columns, and nothing else.
TRANSLATIONS_COLUMNS = {"id", "user_id", "message_id", "target_language", "text", "created_at"}

#: D7 / DoD-1 — the unique constraint is pinned by **name**, not merely by its columns.
UNIQUE_CONSTRAINT_NAME = "uq_translations_message_id_target_language"
UNIQUE_CONSTRAINT_COLUMNS = ["message_id", "target_language"]

#: DoD-4 / DoD-5 — the id the step file names, and the sentence 001.context.md fixes.
ERROR_MESSAGE_ID = 7_250_000_000_000_000_101
DEFAULT_FAILURE_MESSAGE = "The translation failed. Showing the original."
GIVEN_FAILURE_MESSAGE = "The provider could not be reached. Showing the original."

#: The wire contract's success body, for the exact values DoD-5 names.
WIRE_TARGET_LANGUAGE = "Russian"
WIRE_TEXT = "Привет"
EXPECTED_WIRE_BODY = {
    "message_id": "7250000000000000101",
    "target_language": "Russian",
    "text": "Привет",
    "cached": True,
}


def _translations() -> Table:
    return schema.metadata.tables["translations"]


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
    body: str = "A cached translation.",
) -> None:
    """Raw-insert one `translations` row — the only writer this step's tests need."""
    with engine.begin() as connection:
        connection.execute(
            _translations().insert().values(
                id=translation_id,
                user_id=user_id,
                message_id=message_id,
                target_language=target_language,
                text=body,
                created_at=TIMESTAMP,
            )
        )


def _translation_pairs(engine: Engine) -> set[tuple[int, str]]:
    table = _translations()
    with engine.connect() as connection:
        rows = connection.execute(select(table.c.message_id, table.c.target_language)).all()
    return {(int(row[0]), str(row[1])) for row in rows}


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database: the whole registry, two owners, a character, a session and two
    settled partner rows of USER_A (feature 023 Test conventions)."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob")
    _insert_character(db_engine, character_id=CHAR_A, user_id=USER_A, name="Aria")
    _insert_session(db_engine, session_id=SESSION_A, user_id=USER_A, character_id=CHAR_A)
    _insert_message(
        db_engine, message_id=MESSAGE_A, user_id=USER_A, session_id=SESSION_A, body="She waits."
    )
    _insert_message(
        db_engine, message_id=MESSAGE_A2, user_id=USER_A, session_id=SESSION_A, body="He answers."
    )
    return db_engine


# ====================================================================== DoD-1
# D7 — the declared table: exactly six columns, all NOT NULL, two foreign keys, no
# `ON DELETE` action on `message_id`, and the unique pair under its declared name.


def test_the_registry_carries_a_translations_table__S023_001_DoD1() -> None:
    """DoD-1 — `translations` is registered on the one `metadata` (D7)."""
    assert "translations" in schema.metadata.tables
    assert isinstance(_translations(), Table)
    assert _translations().name == "translations"


def test_translations_has_exactly_the_six_declared_columns__S023_001_DoD1() -> None:
    """DoD-1 — exactly `id`, `user_id`, `message_id`, `target_language`, `text`,
    `created_at`: no `updated_at` and no state column (D7)."""
    names = [column.name for column in _translations().columns]
    assert len(names) == len(set(names))
    assert set(names) == TRANSLATIONS_COLUMNS


def test_translations_id_is_the_sole_primary_key__S023_001_DoD1() -> None:
    """DoD-1 — `id` alone is the primary key, in the schema's snowflake idiom (D7)."""
    assert [column.name for column in _translations().primary_key.columns] == ["id"]
    assert _translations().c.id.primary_key is True


@pytest.mark.parametrize("column", sorted(TRANSLATIONS_COLUMNS))
def test_every_translations_column_is_not_null__S023_001_DoD1(column: str) -> None:
    """DoD-1 — every column is NOT NULL; a row carries no optional field (D7)."""
    assert _translations().c[column].nullable is False


def test_translations_declares_exactly_the_two_foreign_keys__S023_001_DoD1() -> None:
    """DoD-1 — `user_id` references `users.id` and `message_id` references `messages.id`;
    there is no third foreign key (D7)."""
    pairs = {(fk.parent.name, fk.target_fullname) for fk in _translations().foreign_keys}
    assert pairs == {("user_id", "users.id"), ("message_id", "messages.id")}


def test_the_message_id_foreign_key_declares_no_on_delete_action__S023_001_DoD1() -> None:
    """DoD-1 — `message_id` carries one foreign key and **no cascade**: no `ON DELETE`
    action is declared (D7)."""
    foreign_keys = list(_translations().c.message_id.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "messages.id"
    assert foreign_keys[0].ondelete is None


def test_translations_declares_the_named_unique_constraint_over_the_pair__S023_001_DoD1() -> None:
    """DoD-1 — a unique constraint named `uq_translations_message_id_target_language` covers
    `(message_id, target_language)`, in that order (D7)."""
    named = [
        constraint
        for constraint in _translations().constraints
        if constraint.name == UNIQUE_CONSTRAINT_NAME
    ]
    assert len(named) == 1
    assert [column.name for column in named[0].columns] == UNIQUE_CONSTRAINT_COLUMNS


def test_the_created_translations_table_matches_the_declaration__S023_001_DoD1(
    engine: Engine,
) -> None:
    """DoD-1 — after `create_all`, the real table reports the same six NOT NULL columns, the
    same two foreign keys and a unique constraint over the pair (001.context.md "Test
    shape")."""
    inspector = inspect(engine)
    assert "translations" in inspector.get_table_names()

    columns = inspector.get_columns("translations")
    assert {column["name"] for column in columns} == TRANSLATIONS_COLUMNS
    for column in columns:
        assert column["nullable"] is False, column["name"]

    targets = {
        (tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]))
        for fk in inspector.get_foreign_keys("translations")
    }
    assert targets == {
        (("user_id",), "users", ("id",)),
        (("message_id",), "messages", ("id",)),
    }

    pair_constraints = [
        constraint
        for constraint in inspector.get_unique_constraints("translations")
        if list(constraint["column_names"]) == UNIQUE_CONSTRAINT_COLUMNS
    ]
    assert len(pair_constraints) == 1


def test_the_created_message_id_foreign_key_has_no_on_delete_action__S023_001_DoD1(
    engine: Engine,
) -> None:
    """DoD-1 — SQLite reports the `message_id` foreign key with no `ON DELETE` action (D7)."""
    with engine.connect() as connection:
        rows = connection.execute(text("PRAGMA foreign_key_list(translations)")).all()
    # PRAGMA foreign_key_list columns: id, seq, table, from, to, on_update, on_delete, match
    matching = [row for row in rows if row[2] == "messages" and row[3] == "message_id"]
    assert len(matching) == 1
    assert matching[0][4] == "id"
    assert str(matching[0][6]).upper() == "NO ACTION"


# ====================================================================== DoD-2
# D7 / UC-041 — one translation per (message, language): the pair is unique, two languages
# for one message are two legal rows.


def test_a_duplicate_message_and_language_pair_is_refused__S023_001_DoD2(engine: Engine) -> None:
    """DoD-2 — a second row with the same `message_id` and `target_language` raises an
    integrity error (D7)."""
    _insert_translation(
        engine, translation_id=901, user_id=USER_A, message_id=MESSAGE_A, target_language="Russian"
    )
    with pytest.raises(IntegrityError):
        _insert_translation(
            engine,
            translation_id=902,
            user_id=USER_A,
            message_id=MESSAGE_A,
            target_language="Russian",
            body="A second Russian translation.",
        )


def test_two_languages_for_one_message_are_accepted__S023_001_DoD2(engine: Engine) -> None:
    """DoD-2 — the constraint is on the pair: one message cached in two languages is two
    legal rows (D7, UC-041)."""
    _insert_translation(
        engine, translation_id=903, user_id=USER_A, message_id=MESSAGE_A, target_language="Russian"
    )
    _insert_translation(
        engine, translation_id=904, user_id=USER_A, message_id=MESSAGE_A, target_language="French"
    )
    assert _translation_pairs(engine) == {(MESSAGE_A, "Russian"), (MESSAGE_A, "French")}


def test_one_language_for_two_messages_is_accepted__S023_001_DoD2(engine: Engine) -> None:
    """DoD-2 — the pair again: the same language cached for two messages is two legal rows."""
    _insert_translation(
        engine, translation_id=905, user_id=USER_A, message_id=MESSAGE_A, target_language="Russian"
    )
    _insert_translation(
        engine, translation_id=906, user_id=USER_A, message_id=MESSAGE_A2, target_language="Russian"
    )
    assert _translation_pairs(engine) == {(MESSAGE_A, "Russian"), (MESSAGE_A2, "Russian")}


# ====================================================================== DoD-4
# D5 / US-048.AC-1 — `TranslationFailedError`: code `translation_failed`, HTTP 502, the
# message id in `detail` as a **string**, a fixed default message a caller may replace.


def test_translation_failed_error_is_a_domain_error__S023_001_DoD4() -> None:
    """DoD-4 — it follows the base's pattern as a `DomainError` subclass (D5)."""
    assert issubclass(TranslationFailedError, DomainError)
    assert isinstance(TranslationFailedError(ERROR_MESSAGE_ID), Exception)


def test_translation_failed_error_sets_code_and_status_on_the_class__S023_001_DoD4() -> None:
    """DoD-4 — `translation_failed` and 502 are class-level attributes, as on every other
    error (D5; the failing party is a dependency)."""
    assert "code" in vars(TranslationFailedError)
    assert "http_status" in vars(TranslationFailedError)
    assert TranslationFailedError.code == "translation_failed"
    assert TranslationFailedError.http_status == 502

    error = TranslationFailedError(ERROR_MESSAGE_ID)
    assert error.code == "translation_failed"
    assert error.http_status == 502


def test_translation_failed_error_details_the_message_id_as_a_string__S023_001_DoD4() -> None:
    """DoD-4 — `detail` is `{"message_id": "7250000000000000101"}`, the id as a decimal
    string and never a JSON number (D5, the JSON id boundary)."""
    error = TranslationFailedError(ERROR_MESSAGE_ID)
    assert error.detail == {"message_id": "7250000000000000101"}
    assert isinstance(error.detail["message_id"], str)


def test_translation_failed_error_carries_its_fixed_default_message__S023_001_DoD4() -> None:
    """DoD-4 — constructed with the id alone, the message is the fixed non-empty sentence
    001.context.md names."""
    error = TranslationFailedError(ERROR_MESSAGE_ID)
    assert isinstance(error.message, str)
    assert error.message != ""
    assert error.message == DEFAULT_FAILURE_MESSAGE


def test_a_given_message_replaces_the_default__S023_001_DoD4() -> None:
    """DoD-4 — step 002 passes cause-specific sentences, so a given message wins and the
    detail is unaffected (D5)."""
    error = TranslationFailedError(ERROR_MESSAGE_ID, GIVEN_FAILURE_MESSAGE)
    assert error.message == GIVEN_FAILURE_MESSAGE
    assert error.detail == {"message_id": "7250000000000000101"}


# ====================================================================== DoD-5
# The Wire contract — `Translation { message_id, target_language, text, cached }`, with
# `message_id` a decimal string.


@dataclass(frozen=True)
class _ResultLike:
    """A stand-in for step 002's result: the attributes the response model is built from."""

    message_id: int
    target_language: str
    text: str
    cached: bool


def _wire(model: TranslationResponse) -> Any:
    """What the model actually serialises to on the wire."""
    return json.loads(model.model_dump_json())


def test_translation_response_serialises_the_wire_contract_exactly__S023_001_DoD5() -> None:
    """DoD-5 — built from an object, it serialises to exactly the Wire contract's four keys,
    with `message_id` as a decimal **string**."""
    result = _ResultLike(
        message_id=ERROR_MESSAGE_ID,
        target_language=WIRE_TARGET_LANGUAGE,
        text=WIRE_TEXT,
        cached=True,
    )
    payload = _wire(TranslationResponse.model_validate(result))

    assert payload == EXPECTED_WIRE_BODY
    assert isinstance(payload["message_id"], str)
    assert payload["cached"] is True


def test_translation_response_serialises_a_fresh_translation_as_not_cached__S023_001_DoD5() -> None:
    """DoD-5 — `cached` is the boolean it was built from: `false` when this request produced
    the text (Wire contract)."""
    result = _ResultLike(
        message_id=ERROR_MESSAGE_ID,
        target_language=WIRE_TARGET_LANGUAGE,
        text=WIRE_TEXT,
        cached=False,
    )
    payload = _wire(TranslationResponse.model_validate(result))

    assert payload == {**EXPECTED_WIRE_BODY, "cached": False}
    assert payload["cached"] is False
