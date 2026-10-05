"""Tests for `app/services/transfer.py` — feature 030, step 002 (DoD-1..14).

Every expected value comes from `docs/plans/030.export-granularities/002.owned-selections.md`
(its Interface intent and Definition of done), from `002.context.md` (the three memo
predicates, the root-row lookup and why `role` / `is_enabled` leave the user export), from
the feature `context.md` (§"Granularity boundaries", §"Row serialization rules",
§"Cross-cutting constraints" — R5 ownership and R6 archived material) and from the rows
this file seeds itself. Nothing is read from the implementation.

`status.md` §"Ultra phase" **decision 4** is binding: `schema.metadata.sorted_tables` is a
stable *topological* sort, in which `memos` comes before `setups`, `sessions` and
`messages`. The DoD-1 and DoD-12 enumerations are therefore **set listings written in
reading order, not orderings**: these tests assert set equality plus the ordering
**computed from `schema.metadata.sorted_tables`**, never a hard-coded sequence. The real
orders are user -> `users, characters, memos, setups, sessions, messages`; character ->
`characters, memos, setups, sessions, messages`; session -> `memos, sessions, messages`.

Seeding: a file-local `engine` fixture applies the registry with
`schema.metadata.create_all` and raw-inserts two owners. Owner A has a live character
`CHAR_A1` (two setups, one archived; two sessions, one archived) and an **archived**
sibling character `CHAR_A2` with its own setup and session, so that every "sibling"
exclusion the DoD names has something real to exclude. Buried rows come from appending a
zone to `SESSION_A1` and settling it through `app/services/settle.py` (`002.context.md`
"Seeding buried messages"): the non-head rows become buried with `related_to` set to the
head. Ids are all above 2**60. `conftest.py` is untouched; the database is the per-test
`tmp_path` file `db_engine` provides.
"""

from typing import Any

import pytest
from sqlalchemy import Column, Engine, Table, select, update

from app.db import schema
from app.errors import CharacterNotFoundError, SessionNotFoundError
from app.roles import Role
from app.services.settle import settle
from app.services.transfer import (
    USER_EXCLUDED_COLUMNS,
    USER_EXCLUDED_TABLES,
    export_character,
    export_session,
    export_user,
)

# --- seeded constants -----------------------------------------------------------------

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"
ARCHIVED_AT = "2026-02-01T00:00:00.000000+00:00"
EXPIRES_AT = "2026-03-01T00:00:00.000000+00:00"

#: Every seeded id is above 2**60 (1152921504606846976).
BASE = 1_152_921_504_606_847_000

USER_A = BASE + 1
USER_B = BASE + 2

SERVER_ID = BASE + 10
MODEL_ID = BASE + 11

CHAR_A1 = BASE + 20
CHAR_A2 = BASE + 21
CHAR_B1 = BASE + 22

SETUP_A1 = BASE + 30
SETUP_A2 = BASE + 31
SETUP_A3 = BASE + 32
SETUP_B1 = BASE + 33

SESSION_A1 = BASE + 40
SESSION_A2 = BASE + 41
SESSION_A3 = BASE + 42
SESSION_B1 = BASE + 43

ZONE_1 = BASE + 50
ZONE_2 = BASE + 51
ZONE_3 = BASE + 52
ZONE_4 = BASE + 53
MSG_A2_SETTLED = BASE + 54
MSG_A2_ZONE = BASE + 55
MSG_A3 = BASE + 56
MSG_B1 = BASE + 57

MEMO_A_USER = BASE + 70
MEMO_A_CHARACTER_1 = BASE + 71
MEMO_A_CHARACTER_2 = BASE + 72
MEMO_A_SETUP_1 = BASE + 73
MEMO_A_SETUP_2 = BASE + 74
MEMO_A_SETUP_3 = BASE + 75
MEMO_A_SESSION_1 = BASE + 76
MEMO_A_SESSION_2 = BASE + 77
MEMO_A_SESSION_3 = BASE + 78
MEMO_B_USER = BASE + 79
MEMO_B_CHARACTER = BASE + 80
MEMO_B_SESSION = BASE + 81

AUTH_SESSION_ID = BASE + 90
TRANSLATION_ID = BASE + 91

#: Ids that belong to nobody (DoD-9, DoD-13).
UNKNOWN_CHARACTER_ID = BASE + 900_001
UNKNOWN_SESSION_ID = BASE + 900_002

PASSWORD_HASH = "not-a-real-hash"

#: The model name seeded on `models`, and the companion value the two
#: `model_server_id`-carrying tables store alongside a non-null server reference.
#: `characters` and `sessions` each hold a CHECK (`ck_characters_model_both_or_neither`,
#: `ck_sessions_model_both_or_neither`, frozen by feature 017's skeleton) requiring
#: `model_server_id` and `model_name` to be **both NULL or both non-NULL**, so the two
#: insert helpers below always write them as a pair.
MODEL_NAME = "seeded-model"

#: `context.md` §"Granularity boundaries" — the user granularity's six tables.
USER_TABLE_NAMES = {"users", "characters", "setups", "sessions", "messages", "memos"}
#: DoD-12 — the session granularity's three tables.
SESSION_TABLE_NAMES = {"sessions", "messages", "memos"}
#: §"Granularity boundaries" — the character granularity's five tables (DoD-6..8).
CHARACTER_TABLE_NAMES = {"characters", "setups", "sessions", "messages", "memos"}

#: DoD-1 / DoD-8 — tables that must never appear in an owner-scoped export.
GLOBAL_AND_EXCLUDED_TABLE_NAMES = ("llm_servers", "models", "auth_sessions", "translations")

#: Owner A's whole set, per granularity, as `context.md` §"Granularity boundaries" defines it.
USER_EXPECTED_IDS = {
    "users": {USER_A},
    "characters": {CHAR_A1, CHAR_A2},
    "setups": {SETUP_A1, SETUP_A2, SETUP_A3},
    "sessions": {SESSION_A1, SESSION_A2, SESSION_A3},
    "messages": {ZONE_1, ZONE_2, ZONE_3, ZONE_4, MSG_A2_SETTLED, MSG_A2_ZONE, MSG_A3},
    "memos": {
        MEMO_A_USER,
        MEMO_A_CHARACTER_1,
        MEMO_A_CHARACTER_2,
        MEMO_A_SETUP_1,
        MEMO_A_SETUP_2,
        MEMO_A_SETUP_3,
        MEMO_A_SESSION_1,
        MEMO_A_SESSION_2,
        MEMO_A_SESSION_3,
    },
}

CHARACTER_EXPECTED_IDS = {
    "characters": {CHAR_A1},
    "setups": {SETUP_A1, SETUP_A2},
    "sessions": {SESSION_A1, SESSION_A2},
    "messages": {ZONE_1, ZONE_2, ZONE_3, ZONE_4, MSG_A2_SETTLED, MSG_A2_ZONE},
    "memos": {MEMO_A_CHARACTER_1, MEMO_A_SETUP_1, MEMO_A_SETUP_2, MEMO_A_SESSION_1, MEMO_A_SESSION_2},
}

SESSION_EXPECTED_IDS = {
    "sessions": {SESSION_A1},
    "messages": {ZONE_1, ZONE_2, ZONE_3, ZONE_4},
    "memos": {MEMO_A_SESSION_1},
}

#: DoD-4 — every id that belongs to owner B and must never cross into owner A's export.
OWNER_B_IDS = frozenset(
    {
        USER_B,
        CHAR_B1,
        SETUP_B1,
        SESSION_B1,
        MSG_B1,
        MEMO_B_USER,
        MEMO_B_CHARACTER,
        MEMO_B_SESSION,
    }
)


# --- registry helpers (every expectation is computed, never a literal order) ----------


def _table(name: str) -> Table:
    return schema.metadata.tables[name]


def _primary_key_name(table: Table) -> str:
    names = [column.name for column in table.primary_key.columns]
    assert len(names) == 1, f"{table.name} is expected to have a single-column primary key"
    return names[0]


def _is_id_column(column: Column[Any]) -> bool:
    """`context.md` §"Row serialization rules" — the three arms of the id-column rule."""
    return bool(
        column.primary_key
        or column.foreign_keys
        or column.name == "id"
        or column.name.endswith("_id")
    )


def _expected_order(names: set[str]) -> list[str]:
    """Decision 4 — `sorted_tables` order restricted to `names`, computed from `metadata`."""
    return [table.name for table in schema.metadata.sorted_tables if table.name in names]


def _ids(rows: list[dict[str, Any]], table_name: str) -> set[int]:
    key = _primary_key_name(_table(table_name))
    return {int(row[key]) for row in rows}


# --- raw-insert helpers (file-local; `conftest.py` is untouched) ----------------------


def _insert(engine: Engine, table: Table, **values: Any) -> None:
    with engine.begin() as connection:
        connection.execute(table.insert().values(**values))


def _insert_user(engine: Engine, *, user_id: int, username: str) -> None:
    _insert(
        engine,
        schema.users,
        id=user_id,
        username=username,
        password_hash=PASSWORD_HASH,
        role=Role.ROLEPLAYER,
        is_enabled=True,
        rp_language=None,
        preferred_language=None,
        last_login_at=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_character(
    engine: Engine,
    *,
    character_id: int,
    user_id: int,
    name: str,
    archived_at: str | None = None,
    model_server_id: int | None = None,
) -> None:
    # `ck_characters_model_both_or_neither`: the designated-model pair is written together.
    _insert(
        engine,
        schema.characters,
        id=character_id,
        user_id=user_id,
        name=name,
        sheet="",
        archived_at=archived_at,
        model_server_id=model_server_id,
        model_name=MODEL_NAME if model_server_id is not None else None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_setup(
    engine: Engine,
    *,
    setup_id: int,
    user_id: int,
    character_id: int,
    name: str,
    archived_at: str | None = None,
) -> None:
    _insert(
        engine,
        schema.setups,
        id=setup_id,
        user_id=user_id,
        character_id=character_id,
        name=name,
        description="",
        archived_at=archived_at,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_session(
    engine: Engine,
    *,
    session_id: int,
    user_id: int,
    character_id: int,
    setup_id: int | None = None,
    model_server_id: int | None = None,
) -> None:
    # `ck_sessions_model_both_or_neither`: the designated-model pair is written together.
    _insert(
        engine,
        schema.sessions,
        id=session_id,
        user_id=user_id,
        character_id=character_id,
        setup_id=setup_id,
        archived_at=None,
        model_server_id=model_server_id,
        model_name=MODEL_NAME if model_server_id is not None else None,
        last_used_at=TIMESTAMP,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    user_id: int,
    session_id: int,
    text: str,
    role: str = "user",
    kind: str | None = None,
    related_to: int | None = None,
    settled_at: str | None = None,
) -> None:
    _insert(
        engine,
        schema.messages,
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


def _insert_memo(
    engine: Engine, *, memo_id: int, user_id: int, scope: str, scope_id: int, body: str
) -> None:
    _insert(
        engine,
        schema.memos,
        id=memo_id,
        user_id=user_id,
        scope=scope,
        scope_id=scope_id,
        body=body,
        is_enabled=True,
        is_forced=False,
        sort_key=100,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _archive_session(engine: Engine, session_id: int) -> None:
    """R6 — archiving by setting `archived_at` directly (`002.context.md` "Seeding")."""
    with engine.begin() as connection:
        connection.execute(
            update(schema.sessions)
            .where(schema.sessions.c.id == session_id)
            .values(archived_at=ARCHIVED_AT)
        )


def _stored_rows(engine: Engine, table: Table) -> dict[int, dict[str, Any]]:
    key = _primary_key_name(table)
    with engine.connect() as connection:
        rows = connection.execute(select(table)).all()
    return {int(row._mapping[key]): dict(row._mapping) for row in rows}


# --- fixture --------------------------------------------------------------------------


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two owners; owner A has a live character, an archived sibling character, an
    archived setup, an archived session and a memo at every scope on every root."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)

    _insert_user(db_engine, user_id=USER_A, username="alice")
    _insert_user(db_engine, user_id=USER_B, username="bob")

    _insert(
        db_engine,
        _table("llm_servers"),
        id=SERVER_ID,
        name="the seeded server",
        kind="llamaswap",
        base_url="http://127.0.0.1:9999",
        api_key_ref=None,
        last_test_at=None,
        last_test_ok=None,
        last_test_error=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )
    _insert(
        db_engine,
        _table("models"),
        id=MODEL_ID,
        server_id=SERVER_ID,
        model_name=MODEL_NAME,
        is_enabled=True,
        is_embedding_designated=False,
        embedding_dim=8,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )

    _insert_character(
        db_engine, character_id=CHAR_A1, user_id=USER_A, name="Aria", model_server_id=SERVER_ID
    )
    # The sibling is archived, so DoD-9's "an archived root still exports" has a subject.
    _insert_character(
        db_engine, character_id=CHAR_A2, user_id=USER_A, name="Understudy", archived_at=ARCHIVED_AT
    )
    _insert_character(db_engine, character_id=CHAR_B1, user_id=USER_B, name="Bob's own")

    _insert_setup(db_engine, setup_id=SETUP_A1, user_id=USER_A, character_id=CHAR_A1, name="Inn")
    _insert_setup(
        db_engine,
        setup_id=SETUP_A2,
        user_id=USER_A,
        character_id=CHAR_A1,
        name="Old inn",
        archived_at=ARCHIVED_AT,
    )
    _insert_setup(db_engine, setup_id=SETUP_A3, user_id=USER_A, character_id=CHAR_A2, name="Spare")
    _insert_setup(db_engine, setup_id=SETUP_B1, user_id=USER_B, character_id=CHAR_B1, name="Road")

    _insert_session(
        db_engine,
        session_id=SESSION_A1,
        user_id=USER_A,
        character_id=CHAR_A1,
        setup_id=SETUP_A1,
        model_server_id=SERVER_ID,
    )
    _insert_session(db_engine, session_id=SESSION_A2, user_id=USER_A, character_id=CHAR_A1)
    _archive_session(db_engine, SESSION_A2)
    _insert_session(db_engine, session_id=SESSION_A3, user_id=USER_A, character_id=CHAR_A2)
    _insert_session(db_engine, session_id=SESSION_B1, user_id=USER_B, character_id=CHAR_B1)

    # `SESSION_A1` gets all three message states: settle buries the two earlier zone rows
    # under the head, then one more zone row is appended.
    for message_id, text in ((ZONE_1, "First draft."), (ZONE_2, "Second draft."), (ZONE_3, "Head.")):
        _insert_message(
            db_engine, message_id=message_id, user_id=USER_A, session_id=SESSION_A1, text=text
        )
    with db_engine.connect() as connection:
        settle(connection, USER_A, SESSION_A1)
    _insert_message(
        db_engine, message_id=ZONE_4, user_id=USER_A, session_id=SESSION_A1, text="Still drafting."
    )

    _insert_message(
        db_engine,
        message_id=MSG_A2_SETTLED,
        user_id=USER_A,
        session_id=SESSION_A2,
        text="Settled in the archived session.",
        settled_at=SEEDED_SETTLED_AT,
    )
    _insert_message(
        db_engine,
        message_id=MSG_A2_ZONE,
        user_id=USER_A,
        session_id=SESSION_A2,
        text="Unsettled in the archived session.",
    )
    _insert_message(
        db_engine, message_id=MSG_A3, user_id=USER_A, session_id=SESSION_A3, text="Sibling line."
    )
    _insert_message(
        db_engine, message_id=MSG_B1, user_id=USER_B, session_id=SESSION_B1, text="Bob's line."
    )

    for memo_id, scope, scope_id, body in (
        (MEMO_A_USER, "user", USER_A, "Everywhere."),
        (MEMO_A_CHARACTER_1, "character", CHAR_A1, "About Aria."),
        (MEMO_A_CHARACTER_2, "character", CHAR_A2, "About the understudy."),
        (MEMO_A_SETUP_1, "setup", SETUP_A1, "At the inn."),
        (MEMO_A_SETUP_2, "setup", SETUP_A2, "At the old inn."),
        (MEMO_A_SETUP_3, "setup", SETUP_A3, "In the spare setup."),
        (MEMO_A_SESSION_1, "session", SESSION_A1, "This session only."),
        (MEMO_A_SESSION_2, "session", SESSION_A2, "The archived session only."),
        (MEMO_A_SESSION_3, "session", SESSION_A3, "The sibling session only."),
    ):
        _insert_memo(
            db_engine, memo_id=memo_id, user_id=USER_A, scope=scope, scope_id=scope_id, body=body
        )
    for memo_id, scope, scope_id in (
        (MEMO_B_USER, "user", USER_B),
        (MEMO_B_CHARACTER, "character", CHAR_B1),
        (MEMO_B_SESSION, "session", SESSION_B1),
    ):
        _insert_memo(
            db_engine, memo_id=memo_id, user_id=USER_B, scope=scope, scope_id=scope_id, body="Bob's."
        )

    _insert(
        db_engine,
        _table("auth_sessions"),
        id=AUTH_SESSION_ID,
        user_id=USER_A,
        token_hash="a-live-login-token-hash",
        created_at=TIMESTAMP,
        expires_at=EXPIRES_AT,
        revoked_at=None,
    )
    _insert(
        db_engine,
        _table("translations"),
        id=TRANSLATION_ID,
        user_id=USER_A,
        message_id=ZONE_3,
        target_language="Russian",
        text="Переведённый текст.",
        created_at=TIMESTAMP,
    )
    return db_engine


# --- export call wrappers (one connection per call) -----------------------------------


def _user_envelope(engine: Engine, user_id: int = USER_A) -> dict[str, Any]:
    with engine.connect() as connection:
        return dict(export_user(connection, user_id))


def _character_envelope(
    engine: Engine, character_id: int = CHAR_A1, user_id: int = USER_A
) -> dict[str, Any]:
    with engine.connect() as connection:
        return dict(export_character(connection, user_id, character_id))


def _session_envelope(
    engine: Engine, session_id: int = SESSION_A1, user_id: int = USER_A
) -> dict[str, Any]:
    with engine.connect() as connection:
        return dict(export_session(connection, user_id, session_id))


def _payload_of(envelope: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    payload = envelope["payload"]
    assert isinstance(payload, dict)
    return payload


# =====================================================================================
# DoD-1 / DoD-2 / DoD-3 / DoD-4 / DoD-5 — the user export
# =====================================================================================


def test_user_payload_keys_are_the_six_owned_tables_in_registry_order__S030_002_DoD1(
    engine: Engine,
) -> None:
    """DoD-1 — the keys are exactly the six user-owned tables, ordered by
    `sorted_tables`, and the granularity is `"user"`.

    Decision 4: the DoD's enumeration is a set listing in reading order, so the expected
    sequence is computed from `schema.metadata.sorted_tables`, not written out.
    """
    envelope = _user_envelope(engine)
    assert envelope["granularity"] == "user"
    payload = _payload_of(envelope)
    assert set(payload) == USER_TABLE_NAMES
    assert list(payload) == _expected_order(USER_TABLE_NAMES)


def test_user_export_has_no_global_or_excluded_table_key__S030_002_DoD1(engine: Engine) -> None:
    """DoD-1 — no `llm_servers`, `models`, `auth_sessions` or `translations` key, even
    though a row of each is seeded."""
    payload = _payload_of(_user_envelope(engine))
    for name in GLOBAL_AND_EXCLUDED_TABLE_NAMES:
        assert _stored_rows(engine, _table(name)) != {}, name
        assert name not in payload, name


def test_user_export_carries_the_callers_row_without_account_state__S030_002_DoD2(
    engine: Engine,
) -> None:
    """DoD-2 / `002.context.md` "Why `role` and `is_enabled` leave the user export" — one
    `users` row, the caller's, with the three excluded columns absent and every other
    declared column still present (`id` and `username` among them)."""
    assert USER_EXCLUDED_COLUMNS == frozenset({"password_hash", "role", "is_enabled"})
    rows = _payload_of(_user_envelope(engine))["users"]
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == str(USER_A)
    assert row["username"] == "alice"
    for column_name in USER_EXCLUDED_COLUMNS:
        assert column_name not in row
    declared = {column.name for column in schema.users.columns}
    assert set(row) == declared - set(USER_EXCLUDED_COLUMNS)


def test_user_export_includes_memos_at_all_four_scopes__S030_002_DoD3(engine: Engine) -> None:
    """DoD-3 / US-079.AC-1 — all of the caller's memos, every scope, and the
    `scope='user'` memo's `scope_id` is the caller's own id."""
    rows = _payload_of(_user_envelope(engine))["memos"]
    assert _ids(rows, "memos") == USER_EXPECTED_IDS["memos"]
    by_id = {int(row["id"]): row for row in rows}
    assert {row["scope"] for row in rows} == {"user", "character", "setup", "session"}
    assert by_id[MEMO_A_USER]["scope"] == "user"
    assert by_id[MEMO_A_USER]["scope_id"] == str(USER_A)


def test_user_export_holds_every_owned_row_and_nothing_of_the_other_user__S030_002_DoD4(
    engine: Engine,
) -> None:
    """DoD-4 / UC-062 / R5 — each table's rows are exactly the caller's, and no id
    belonging to the second owner appears as any serialized value anywhere (which also
    catches a leaked `user_id` or `scope_id`)."""
    payload = _payload_of(_user_envelope(engine))
    for name, expected in USER_EXPECTED_IDS.items():
        assert _ids(payload[name], name) == expected, name
    for name, rows in payload.items():
        for row in rows:
            for column_name, value in row.items():
                if type(value) is str and value.isdigit():
                    assert int(value) not in OWNER_B_IDS, f"{name}.{column_name}"


def test_every_user_owned_metadata_table_is_classified__S030_002_DoD5(engine: Engine) -> None:
    """DoD-5 — a guard against future features: every table in the registry that carries
    a `user_id` column is either exported at user granularity or named in the
    user-granularity exclusion constant. A later feature that adds user-owned material
    without classifying it fails here."""
    assert USER_EXCLUDED_TABLES == frozenset({"auth_sessions", "translations"})
    owned = {
        table.name for table in schema.metadata.sorted_tables if "user_id" in table.c
    }
    assert owned != set()
    exported = set(_payload_of(_user_envelope(engine)))
    unclassified = owned - exported - set(USER_EXCLUDED_TABLES)
    assert unclassified == set(), f"unclassified user-owned tables: {sorted(unclassified)}"


# =====================================================================================
# DoD-6 / DoD-7 / DoD-8 / DoD-9 — the character export
# =====================================================================================


def test_character_export_returns_only_the_requested_character__S030_002_DoD6(
    engine: Engine,
) -> None:
    """DoD-6 / UC-063 — exactly one `characters` row, and it is the requested one (the
    root, since the envelope carries no root-reference field)."""
    envelope = _character_envelope(engine)
    assert envelope["granularity"] == "character"
    rows = _payload_of(envelope)["characters"]
    assert len(rows) == 1
    assert rows[0]["id"] == str(CHAR_A1)


def test_character_export_holds_its_archived_children_and_all_messages__S030_002_DoD6(
    engine: Engine,
) -> None:
    """DoD-6 / R6 — all of the character's setups and sessions including the archived
    ones, and every message of those sessions: the settled head, the buried rows and the
    current-zone row."""
    payload = _payload_of(_character_envelope(engine))
    assert list(payload) == _expected_order(CHARACTER_TABLE_NAMES)
    assert _ids(payload["setups"], "setups") == CHARACTER_EXPECTED_IDS["setups"]
    assert _ids(payload["sessions"], "sessions") == CHARACTER_EXPECTED_IDS["sessions"]
    assert _ids(payload["messages"], "messages") == CHARACTER_EXPECTED_IDS["messages"]


def test_character_export_memos_are_its_own_three_scopes_only__S030_002_DoD7(
    engine: Engine,
) -> None:
    """DoD-7 / US-080.AC-1 / `002.context.md` "Memo selection predicates" — exactly the
    memos scoped to the character, to its setups and to its sessions. No `scope='user'`
    memo, and none from the sibling character, the sibling's setup or the sibling's
    session."""
    rows = _payload_of(_character_envelope(engine))["memos"]
    assert _ids(rows, "memos") == CHARACTER_EXPECTED_IDS["memos"]
    excluded = {
        MEMO_A_USER,
        MEMO_A_CHARACTER_2,
        MEMO_A_SETUP_3,
        MEMO_A_SESSION_3,
        MEMO_B_USER,
        MEMO_B_CHARACTER,
        MEMO_B_SESSION,
    }
    assert _ids(rows, "memos") & excluded == set()
    assert "user" not in {row["scope"] for row in rows}


def test_character_export_has_no_users_global_or_excluded_key__S030_002_DoD8(
    engine: Engine,
) -> None:
    """DoD-8 — no `users`, `llm_servers`, `models`, `auth_sessions` or `translations`."""
    payload = _payload_of(_character_envelope(engine))
    for name in ("users", *GLOBAL_AND_EXCLUDED_TABLE_NAMES):
        assert name not in payload, name


@pytest.mark.parametrize(
    ("character_id", "label"),
    [(CHAR_B1, "another owner's character"), (UNKNOWN_CHARACTER_ID, "an id that does not exist")],
)
def test_character_export_raises_for_a_foreign_or_unknown_id__S030_002_DoD9(
    engine: Engine, character_id: int, label: str
) -> None:
    """DoD-9 / R5 / `002.context.md` — foreign and missing are the same answer: there is
    no 403, both raise `CharacterNotFoundError`."""
    with engine.connect() as connection, pytest.raises(CharacterNotFoundError):
        export_character(connection, USER_A, character_id)


def test_an_archived_character_still_exports__S030_002_DoD9(engine: Engine) -> None:
    """DoD-9 / R6 — the root lookup must not filter archived rows: the archived sibling
    character exports, carrying its own setup, session and memos."""
    payload = _payload_of(_character_envelope(engine, character_id=CHAR_A2))
    assert _ids(payload["characters"], "characters") == {CHAR_A2}
    assert _ids(payload["setups"], "setups") == {SETUP_A3}
    assert _ids(payload["sessions"], "sessions") == {SESSION_A3}
    assert _ids(payload["memos"], "memos") == {MEMO_A_CHARACTER_2, MEMO_A_SETUP_3, MEMO_A_SESSION_3}


# =====================================================================================
# DoD-10 / DoD-11 / DoD-12 / DoD-13 — the session export
# =====================================================================================


def test_session_export_returns_the_one_requested_session_even_archived__S030_002_DoD10(
    engine: Engine,
) -> None:
    """DoD-10 / R6 / UC-064 — exactly one `sessions` row, the requested one, and an
    archived session is still exported."""
    live = _payload_of(_session_envelope(engine))
    assert len(live["sessions"]) == 1
    assert live["sessions"][0]["id"] == str(SESSION_A1)
    assert live["sessions"][0]["archived_at"] is None

    archived = _payload_of(_session_envelope(engine, session_id=SESSION_A2))
    assert len(archived["sessions"]) == 1
    assert archived["sessions"][0]["id"] == str(SESSION_A2)
    assert archived["sessions"][0]["archived_at"] == ARCHIVED_AT
    assert _ids(archived["messages"], "messages") == {MSG_A2_SETTLED, MSG_A2_ZONE}


def test_session_export_returns_every_message_and_resolves_buried_refs__S030_002_DoD10(
    engine: Engine,
) -> None:
    """DoD-10 / `002.context.md` "Messages are selected from the raw `messages` Table" —
    every message of the session whether settled, buried or current-zone, and each buried
    row's `related_to` names a message id that is itself in the payload. A read through
    `settled_entries` or `current_zone` would drop the buried rows and leave the reference
    dangling."""
    payload = _payload_of(_session_envelope(engine))
    message_ids = _ids(payload["messages"], "messages")
    assert message_ids == SESSION_EXPECTED_IDS["messages"]

    referencing = [row for row in payload["messages"] if row["related_to"] is not None]
    assert referencing != [], "settling a three-row zone must leave buried rows behind"
    for row in referencing:
        related = row["related_to"]
        assert type(related) is str
        assert related.isdigit()
        assert int(related) in message_ids

    # All three states are represented: a settled head, the buried rows, an unsettled row.
    settled_flags = {row["settled_at"] is not None for row in payload["messages"]}
    assert settled_flags == {True, False}


def test_session_export_memos_are_only_that_sessions_memos__S030_002_DoD11(
    engine: Engine,
) -> None:
    """DoD-11 / US-081.AC-1 — only `scope='session'` memos whose `scope_id` is this
    session: no character, setup or user memo, and none from the sibling session under the
    same character."""
    rows = _payload_of(_session_envelope(engine))["memos"]
    assert _ids(rows, "memos") == SESSION_EXPECTED_IDS["memos"]
    assert {row["scope"] for row in rows} == {"session"}
    assert {row["scope_id"] for row in rows} == {str(SESSION_A1)}
    excluded = {
        MEMO_A_USER,
        MEMO_A_CHARACTER_1,
        MEMO_A_SETUP_1,
        MEMO_A_SESSION_2,
        MEMO_A_SESSION_3,
    }
    assert _ids(rows, "memos") & excluded == set()


def test_session_payload_keys_are_sessions_messages_and_memos__S030_002_DoD12(
    engine: Engine,
) -> None:
    """DoD-12 — exactly those three keys, ordered by `sorted_tables` (decision 4: the
    DoD's sequence is a set listing in reading order, so the order is computed)."""
    envelope = _session_envelope(engine)
    assert envelope["granularity"] == "session"
    payload = _payload_of(envelope)
    assert set(payload) == SESSION_TABLE_NAMES
    assert list(payload) == _expected_order(SESSION_TABLE_NAMES)


@pytest.mark.parametrize(
    ("session_id", "label"),
    [(SESSION_B1, "another owner's session"), (UNKNOWN_SESSION_ID, "an id that does not exist")],
)
def test_session_export_raises_for_a_foreign_or_unknown_id__S030_002_DoD13(
    engine: Engine, session_id: int, label: str
) -> None:
    """DoD-13 / R5 — foreign and missing both raise `SessionNotFoundError`; there is no
    403."""
    with engine.connect() as connection, pytest.raises(SessionNotFoundError):
        export_session(connection, USER_A, session_id)


# =====================================================================================
# DoD-14 — the id rule holds in all three exports
# =====================================================================================


def _assert_id_columns_are_decimal_strings(engine: Engine, envelope: dict[str, Any]) -> None:
    for name, rows in _payload_of(envelope).items():
        table = _table(name)
        key = _primary_key_name(table)
        stored = _stored_rows(engine, table)
        assert rows != [], name
        for row in rows:
            source = stored[int(row[key])]
            for column_name, value in row.items():
                if not _is_id_column(table.c[column_name]):
                    continue
                expected = source[column_name]
                if expected is None:
                    assert value is None, f"{name}.{column_name}"
                    continue
                assert type(value) is str, f"{name}.{column_name}"
                assert value.isdigit(), f"{name}.{column_name}"
                assert int(value) == int(expected), f"{name}.{column_name}"


def test_id_columns_are_decimal_strings_in_the_user_export__S030_002_DoD14(
    engine: Engine,
) -> None:
    """DoD-14 — the step-001 id rule, unchanged, at user granularity."""
    _assert_id_columns_are_decimal_strings(engine, _user_envelope(engine))


def test_id_columns_are_decimal_strings_in_the_character_export__S030_002_DoD14(
    engine: Engine,
) -> None:
    """DoD-14 — the step-001 id rule, unchanged, at character granularity (the dangling
    `user_id` and `model_server_id` refs are still decimal strings)."""
    _assert_id_columns_are_decimal_strings(engine, _character_envelope(engine))


def test_id_columns_are_decimal_strings_in_the_session_export__S030_002_DoD14(
    engine: Engine,
) -> None:
    """DoD-14 — the step-001 id rule, unchanged, at session granularity (the dangling
    `character_id` / `setup_id` refs of UC-064 are still decimal strings, and a null one
    stays null)."""
    _assert_id_columns_are_decimal_strings(engine, _session_envelope(engine))
