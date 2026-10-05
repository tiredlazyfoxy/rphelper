"""Tests for `import_database` — feature 031, step 004 (whole-database replace).

Every expected value comes from the spec — `docs/plans/031.import-and-id-remapping/
004.database-replace.md` (Interface intent + Definition of done), `004.context.md`
(§"Facts this step reads", §"Fixtures guidance"), the feature `context.md`
(§"Database import", §"The failure contract", §"Test conventions") — and from the rows
this file seeds itself. Nothing here was derived from the implementation.

**The only step-004 symbol named here is `import_database`.** The eligibility guard, the
scope-target check, the wipe and the vector drop are module-private by design, so every
behaviour below is observed through `import_database` and the two databases it reads and
writes. No `_`-prefixed name from `app.services.transfer_import` is imported or
referenced, and — per the orchestrator's **ruling 22** — no identity-policy symbol is
looked for: ids are preserved because the validated rows reach the writer unchanged, which
is observable only as "the restored rows carry the source's own ids".

Step 001 contributes `DatabaseNotEmptyError`, `ExportInvalidError` and the `REASON_*`
constants; **no reason string literal is re-typed**. 030 contributes the exporters that
build every envelope and the `DATABASE_EXCLUDED_TABLES` / `SCHEMA_VERSION` constants. 024
contributes `ensure_fts_tables`, `ensure_vector_tables`, `vector_table_dimension` and the
four table-name constants.

**Two databases** (`004.context.md` §"Fixtures guidance", harvest D4, the idiom at
`tests/test_admin_db_router.py:1413-1446`): the **source** lives on a second `Settings`
built with `db_settings.model_copy(update={"data_dir": tmp_path / "source", ...})` plus
`get_engine`, and the **target** is `db_engine` itself. Both files are inside the per-test
`tmp_path`; nothing outside it is ever opened. `conftest.py` is untouched and every schema
is applied with `schema.metadata.create_all`, so `memo_fts` / `message_fts` / `memo_vec` /
`session_vec` do not exist when a test starts unless the test creates them.

Orchestrator corrections honoured here:

- **decision 13** — `memos.scope` reads back as a plain `str`, `users.role` as a `Role`;
- **decision 14** — `settled_entries` and `current_zone` are Core `select()` objects, not
  SQL views, so DoD-10 executes them directly;
- **decision 15** — only FK / UNIQUE / CHECK failures reach the write phase as
  `IntegrityError`, so DoD-6 seeds exactly those three shapes and no enum or
  out-of-range-id case;
- **ruling 22** — no identity-policy value exists, and none is asserted on.
"""

import copy
import json
import struct
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import sqlite_vec
from sqlalchemy import Connection, Engine, Table, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db import schema
from app.db.engine import get_engine
from app.db.search_tables import (
    MEMO_FTS_TABLE,
    MEMO_VEC_TABLE,
    MESSAGE_FTS_TABLE,
    SESSION_VEC_TABLE,
    ensure_fts_tables,
    ensure_vector_tables,
    vector_table_dimension,
)
from app.errors import (
    REASON_MALFORMED_PAYLOAD,
    REASON_WRONG_GRANULARITY,
    DatabaseNotEmptyError,
    ExportInvalidError,
)
from app.roles import Role
from app.services.passwords import hash_password, verify_password
from app.services.transfer import (
    DATABASE_EXCLUDED_TABLES,
    SCHEMA_VERSION,
    export_character,
    export_database,
    export_session,
    export_user,
)
from app.services.transfer_import import import_database

# --- the table sets, derived from the registry and 030's exclusion set ----------------

#: Every table the `database` granularity carries, in `sorted_tables` order. Derived from
#: `schema.metadata` minus 030's `DATABASE_EXCLUDED_TABLES`, never hand-listed
#: (`context.md` §"Granularity table sets").
PAYLOAD_TABLES: tuple[Table, ...] = tuple(
    table
    for table in schema.metadata.sorted_tables
    if table.name not in DATABASE_EXCLUDED_TABLES
)

#: The two `metadata` tables a payload never carries and the replace leaves empty.
EXCLUDED_TABLES: tuple[Table, ...] = tuple(
    table
    for table in schema.metadata.sorted_tables
    if table.name in DATABASE_EXCLUDED_TABLES
)

#: `app.db.schema` exposes no module attribute for 023's table; every delivered test
#: reaches it through the registry (`tests/test_translation_service.py:171`).
TRANSLATIONS: Table = schema.metadata.tables["translations"]


# --- seeded constants ----------------------------------------------------------------

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"
ARCHIVED_AT = "2026-02-01T00:00:00.000000+00:00"
LAST_USED_AT = "2026-03-03T03:03:03.000000+00:00"
EXPIRES_AT = "2026-04-04T04:04:04.000000+00:00"

#: Every seeded id is above `2**60` (`context.md` §"Test conventions"). The source and the
#: target use disjoint id spaces, so "the restored rows carry the source's own ids" and
#: "the target's own rows are gone" are two different observations.
SOURCE_BASE = 1_152_921_504_606_848_000
TARGET_BASE = 1_152_921_504_606_849_000

SRC_ADMIN = SOURCE_BASE + 1
SRC_PLAYER = SOURCE_BASE + 2
SRC_SERVER = SOURCE_BASE + 10
SRC_MODEL = SOURCE_BASE + 11
SRC_CHARACTER_1 = SOURCE_BASE + 20
SRC_CHARACTER_2 = SOURCE_BASE + 21
SRC_SETUP_1 = SOURCE_BASE + 30
SRC_SETUP_2 = SOURCE_BASE + 31
SRC_SESSION_1 = SOURCE_BASE + 40
SRC_SESSION_2 = SOURCE_BASE + 41

#: `messages` of `SRC_SESSION_1`: two settled groups, then the zone. Each buried row has a
#: **lower** id than its own head (030's outcome note), which is why the writer is
#: two-pass — and why DoD-10 is worth asserting at all.
SRC_BURIED_1 = SOURCE_BASE + 50
SRC_HEAD_1 = SOURCE_BASE + 51
SRC_BURIED_2 = SOURCE_BASE + 52
SRC_HEAD_2 = SOURCE_BASE + 53
SRC_ZONE_1 = SOURCE_BASE + 54
SRC_ZONE_2 = SOURCE_BASE + 55

SRC_MEMO_USER = SOURCE_BASE + 60
SRC_MEMO_CHARACTER = SOURCE_BASE + 61
SRC_MEMO_SETUP = SOURCE_BASE + 62
SRC_MEMO_SESSION = SOURCE_BASE + 63

TGT_ADMIN = TARGET_BASE + 1
TGT_SECOND_USER = TARGET_BASE + 2
TGT_SERVER = TARGET_BASE + 10
TGT_MODEL = TARGET_BASE + 11
TGT_CHARACTER = TARGET_BASE + 20
TGT_SETUP = TARGET_BASE + 30
TGT_SESSION = TARGET_BASE + 40
TGT_MESSAGE = TARGET_BASE + 50
TGT_MEMO = TARGET_BASE + 60
TGT_TRANSLATION = TARGET_BASE + 70
TGT_AUTH_SESSION = TARGET_BASE + 80

#: An id no row of any payload carries, for DoD-6's two dangling references.
SPARE_ID = SOURCE_BASE + 900

#: DoD-2: the password is chosen here and hashed through `services/passwords.py`, so the
#: restored hash can be verified through the **same** seam afterwards.
SRC_ADMIN_PASSWORD = "the source administrator's password"
SRC_PLAYER_PASSWORD = "the source roleplayer's password"
TGT_PASSWORD = "the target administrator's password"
WRONG_PASSWORD = "not any seeded password"

#: DoD-1: the `llm_servers` row's key ref is a `"$NAME"` reference, restored verbatim.
SRC_API_KEY_REF = "$SOURCE_SERVER_KEY"
SRC_MODEL_NAME = "source-designated-model"
TGT_MODEL_NAME = "target-model"

#: DoD-11: a username that could only have come from the payload, so finding it in an
#: error is proof the driver's text leaked.
SENTINEL_USERNAME = "sentinel-zarquon-duplicated-username"

# --- full-text tokens (DoD-9): one unique, tokenizable word per indexed body ----------

SRC_RECORD_TOKEN_1 = "obeliskalpha"
SRC_RECORD_TOKEN_2 = "obeliskbeta"
SRC_BURIED_TOKEN_1 = "cryptalpha"
SRC_BURIED_TOKEN_2 = "cryptbeta"
SRC_ZONE_TOKEN_1 = "lanternalpha"
SRC_ZONE_TOKEN_2 = "lanternbeta"

SRC_MEMO_TOKEN_USER = "zephyruser"
SRC_MEMO_TOKEN_CHARACTER = "zephyrcharacter"
SRC_MEMO_TOKEN_SETUP = "zephyrsetup"
SRC_MEMO_TOKEN_SESSION = "zephyrsession"

#: Only ever written into the **target**, so after the wipe neither token may be found.
TGT_MEMO_TOKEN = "vanishedmemotoken"
TGT_RECORD_TOKEN = "vanishedrecordtoken"

# --- vector seeding (DoD-8, DoD-12) --------------------------------------------------

#: The dimension the vec0 tables are seeded at, and the **different** one DoD-12 ensures
#: afterwards (`004.context.md` §"Fixtures guidance": seed at 8, re-ensure at 16).
SEEDED_DIMENSION = 8
LATER_DIMENSION = 16

MEMO_VECTOR = [0.125 * (index + 1) for index in range(SEEDED_DIMENSION)]
SESSION_VECTOR = [-0.0625 * (index + 1) for index in range(SEEDED_DIMENSION)]

SEEDED_VECTORS: tuple[tuple[str, int, list[float]], ...] = (
    (MEMO_VEC_TABLE, TGT_MEMO, MEMO_VECTOR),
    (SESSION_VEC_TABLE, TGT_SESSION, SESSION_VECTOR),
)

#: The four memo scopes DoD-1 requires the source to carry. `memos.scope` reads back as a
#: plain `str` (decision 13), so these compare directly.
SCOPE_USER = "user"
SCOPE_CHARACTER = "character"
SCOPE_SETUP = "setup"
SCOPE_SESSION = "session"


# --- raw-insert helpers (file-local; `conftest.py` is untouched) ----------------------


def _create_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        schema.metadata.create_all(connection)


def _insert(engine: Engine, table: Table, **values: Any) -> None:
    with engine.begin() as connection:
        connection.execute(table.insert().values(**values))


def _insert_user(
    engine: Engine, *, user_id: int, username: str, role: Role, password: str
) -> None:
    _insert(
        engine,
        schema.users,
        id=user_id,
        username=username,
        password_hash=hash_password(password),
        role=role,
        is_enabled=True,
        rp_language="Russian",
        preferred_language="English",
        last_login_at=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_server(engine: Engine, *, server_id: int, api_key_ref: str | None) -> None:
    _insert(
        engine,
        schema.llm_servers,
        id=server_id,
        name=f"server {server_id}",
        kind="llamaswap",
        base_url="http://127.0.0.1:9999",
        api_key_ref=api_key_ref,
        last_test_at=TIMESTAMP,
        last_test_ok=True,
        last_test_error=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_model(
    engine: Engine,
    *,
    model_id: int,
    server_id: int,
    model_name: str,
    designated: bool,
    embedding_dim: int | None,
) -> None:
    _insert(
        engine,
        schema.models,
        id=model_id,
        server_id=server_id,
        model_name=model_name,
        is_enabled=True,
        is_embedding_designated=designated,
        embedding_dim=embedding_dim,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_character(
    engine: Engine,
    *,
    character_id: int,
    user_id: int,
    name: str,
    model_pair: tuple[int, str] | None = None,
    archived_at: str | None = None,
) -> None:
    # `ck_characters_model_both_or_neither`: the pair is written together or not at all.
    _insert(
        engine,
        schema.characters,
        id=character_id,
        user_id=user_id,
        name=name,
        sheet=f"The sheet of {name}.",
        archived_at=archived_at,
        model_server_id=None if model_pair is None else model_pair[0],
        model_name=None if model_pair is None else model_pair[1],
        system_prompt=None if model_pair is None else "Stay in character.",
        tool_memo_search=True,
        tool_session_search=False,
        tool_web_search=None,
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
        description=f"A description of {name}.",
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
    model_pair: tuple[int, str] | None = None,
    archived_at: str | None = None,
) -> None:
    # `ck_sessions_model_both_or_neither`: the pair is written together or not at all.
    _insert(
        engine,
        schema.sessions,
        id=session_id,
        user_id=user_id,
        character_id=character_id,
        setup_id=setup_id,
        last_used_at=LAST_USED_AT,
        archived_at=archived_at,
        model_server_id=None if model_pair is None else model_pair[0],
        model_name=None if model_pair is None else model_pair[1],
        system_prompt=None,
        tool_memo_search=False,
        tool_session_search=None,
        tool_web_search=True,
        rp_language="Russian",
        preferred_language=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_message(
    engine: Engine,
    *,
    message_id: int,
    user_id: int,
    session_id: int,
    token: str,
    role: str = "user",
    kind: str | None = None,
    settled_at: str | None = None,
) -> None:
    # `related_to` is always NULL here; `_bury` sets it afterwards, so a buried row may
    # carry a **lower** id than its own head. `ck_messages_buried_or_settled` holds at
    # both steps.
    _insert(
        engine,
        schema.messages,
        id=message_id,
        user_id=user_id,
        session_id=session_id,
        role=role,
        kind=kind,
        text=f"{token} spoken aloud.",
        related_to=None,
        settled_at=settled_at,
        tool_name=None,
        tool_payload=None,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _bury(engine: Engine, *, message_id: int, head_id: int) -> None:
    """Point a zone-shaped row at its head, the way settling does."""
    with engine.begin() as connection:
        connection.execute(
            schema.messages.update()
            .where(schema.messages.c.id == message_id)
            .values(related_to=head_id)
        )


def _insert_memo(
    engine: Engine,
    *,
    memo_id: int,
    user_id: int,
    scope: str,
    scope_id: int,
    token: str,
    sort_key: int = 100,
) -> None:
    _insert(
        engine,
        schema.memos,
        id=memo_id,
        user_id=user_id,
        scope=scope,
        scope_id=scope_id,
        body=f"{token} remembered.",
        is_enabled=True,
        is_forced=False,
        sort_key=sort_key,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _insert_translation(
    engine: Engine, *, translation_id: int, user_id: int, message_id: int
) -> None:
    _insert(
        engine,
        TRANSLATIONS,
        id=translation_id,
        user_id=user_id,
        message_id=message_id,
        target_language="English",
        text="A translated line.",
        created_at=TIMESTAMP,
    )


def _insert_auth_session(engine: Engine, *, auth_id: int, user_id: int) -> None:
    _insert(
        engine,
        schema.auth_sessions,
        id=auth_id,
        user_id=user_id,
        token_hash=f"token-hash-{auth_id}",
        created_at=TIMESTAMP,
        expires_at=EXPIRES_AT,
        revoked_at=None,
    )


# --- the two instances ----------------------------------------------------------------


def _seed_source(engine: Engine) -> None:
    """The exported instance, exactly as DoD-1 lists it.

    Two users (an admin and a roleplayer), two characters of which one is archived, two
    setups, two sessions of which one is archived, settled **and** buried **and** zone
    messages, a memo at each of the four scopes, an `llm_servers` row whose `api_key_ref`
    is a `"$NAME"` reference, and a designated `models` row. `auth_sessions` and
    `translations` are deliberately left empty: a `database` payload never carries them,
    so the source's payload tables are exactly what the target must end up holding.
    """
    _insert_user(
        engine,
        user_id=SRC_ADMIN,
        username="source-admin",
        role=Role.ADMIN,
        password=SRC_ADMIN_PASSWORD,
    )
    _insert_user(
        engine,
        user_id=SRC_PLAYER,
        username="source-player",
        role=Role.ROLEPLAYER,
        password=SRC_PLAYER_PASSWORD,
    )

    _insert_server(engine, server_id=SRC_SERVER, api_key_ref=SRC_API_KEY_REF)
    _insert_model(
        engine,
        model_id=SRC_MODEL,
        server_id=SRC_SERVER,
        model_name=SRC_MODEL_NAME,
        designated=True,
        embedding_dim=SEEDED_DIMENSION,
    )

    _insert_character(
        engine,
        character_id=SRC_CHARACTER_1,
        user_id=SRC_PLAYER,
        name="Aria",
        model_pair=(SRC_SERVER, SRC_MODEL_NAME),
    )
    _insert_character(
        engine,
        character_id=SRC_CHARACTER_2,
        user_id=SRC_PLAYER,
        name="Brio",
        archived_at=ARCHIVED_AT,
    )

    _insert_setup(
        engine,
        setup_id=SRC_SETUP_1,
        user_id=SRC_PLAYER,
        character_id=SRC_CHARACTER_1,
        name="Inn",
    )
    _insert_setup(
        engine,
        setup_id=SRC_SETUP_2,
        user_id=SRC_PLAYER,
        character_id=SRC_CHARACTER_2,
        name="Keep",
        archived_at=ARCHIVED_AT,
    )

    _insert_session(
        engine,
        session_id=SRC_SESSION_1,
        user_id=SRC_PLAYER,
        character_id=SRC_CHARACTER_1,
        setup_id=SRC_SETUP_1,
        model_pair=(SRC_SERVER, SRC_MODEL_NAME),
    )
    _insert_session(
        engine,
        session_id=SRC_SESSION_2,
        user_id=SRC_PLAYER,
        character_id=SRC_CHARACTER_2,
        setup_id=SRC_SETUP_2,
        archived_at=ARCHIVED_AT,
    )

    for message_id, token, settled_at, role, kind in (
        (SRC_BURIED_1, SRC_BURIED_TOKEN_1, None, "user", None),
        (SRC_HEAD_1, SRC_RECORD_TOKEN_1, SETTLED_AT, "assistant", "partner"),
        (SRC_BURIED_2, SRC_BURIED_TOKEN_2, None, "user", None),
        (SRC_HEAD_2, SRC_RECORD_TOKEN_2, SETTLED_AT, "assistant", "partner"),
        (SRC_ZONE_1, SRC_ZONE_TOKEN_1, None, "user", None),
        (SRC_ZONE_2, SRC_ZONE_TOKEN_2, None, "assistant", "draft"),
    ):
        _insert_message(
            engine,
            message_id=message_id,
            user_id=SRC_PLAYER,
            session_id=SRC_SESSION_1,
            token=token,
            role=role,
            kind=kind,
            settled_at=settled_at,
        )
    _bury(engine, message_id=SRC_BURIED_1, head_id=SRC_HEAD_1)
    _bury(engine, message_id=SRC_BURIED_2, head_id=SRC_HEAD_2)

    for memo_id, scope, scope_id, token in (
        (SRC_MEMO_USER, SCOPE_USER, SRC_PLAYER, SRC_MEMO_TOKEN_USER),
        (SRC_MEMO_CHARACTER, SCOPE_CHARACTER, SRC_CHARACTER_1, SRC_MEMO_TOKEN_CHARACTER),
        (SRC_MEMO_SETUP, SCOPE_SETUP, SRC_SETUP_1, SRC_MEMO_TOKEN_SETUP),
        (SRC_MEMO_SESSION, SCOPE_SESSION, SRC_SESSION_1, SRC_MEMO_TOKEN_SESSION),
    ):
        _insert_memo(
            engine,
            memo_id=memo_id,
            user_id=SRC_PLAYER,
            scope=scope,
            scope_id=scope_id,
            token=token,
        )


#: The eligible target: **exactly one** user, an admin (`004.context.md` §U2).
ELIGIBLE_USERS: tuple[tuple[int, str, Role], ...] = (
    (TGT_ADMIN, "target-admin", Role.ADMIN),
)
#: DoD-4's three ineligible shapes.
TWO_ADMINS: tuple[tuple[int, str, Role], ...] = (
    (TGT_ADMIN, "target-admin", Role.ADMIN),
    (TGT_SECOND_USER, "target-second-admin", Role.ADMIN),
)
ADMIN_AND_ROLEPLAYER: tuple[tuple[int, str, Role], ...] = (
    (TGT_ADMIN, "target-admin", Role.ADMIN),
    (TGT_SECOND_USER, "target-roleplayer", Role.ROLEPLAYER),
)
ONE_ROLEPLAYER: tuple[tuple[int, str, Role], ...] = (
    (TGT_ADMIN, "target-roleplayer", Role.ROLEPLAYER),
)


def _seed_target(engine: Engine, users: Sequence[tuple[int, str, Role]]) -> None:
    """The instance being replaced: the given accounts, and a whole tree under the first.

    Besides the character and the `auth_sessions` row DoD-1 names, it holds a server, a
    model, a setup, a session, a settled message, a memo and a `translations` row — every
    one of them something `context.md` §"Database import" says the wipe deletes, so
    "`translations` holds no rows" and "every table holds exactly the source rows" are
    both observations about rows that demonstrably existed first.
    """
    for user_id, username, role in users:
        _insert_user(
            engine, user_id=user_id, username=username, role=role, password=TGT_PASSWORD
        )
    owner = users[0][0]

    _insert_server(engine, server_id=TGT_SERVER, api_key_ref=None)
    _insert_model(
        engine,
        model_id=TGT_MODEL,
        server_id=TGT_SERVER,
        model_name=TGT_MODEL_NAME,
        designated=False,
        embedding_dim=None,
    )
    _insert_character(
        engine, character_id=TGT_CHARACTER, user_id=owner, name="The target's own"
    )
    _insert_setup(
        engine,
        setup_id=TGT_SETUP,
        user_id=owner,
        character_id=TGT_CHARACTER,
        name="Target setup",
    )
    _insert_session(
        engine,
        session_id=TGT_SESSION,
        user_id=owner,
        character_id=TGT_CHARACTER,
        setup_id=TGT_SETUP,
    )
    _insert_message(
        engine,
        message_id=TGT_MESSAGE,
        user_id=owner,
        session_id=TGT_SESSION,
        token=TGT_RECORD_TOKEN,
        role="assistant",
        kind="partner",
        settled_at=SETTLED_AT,
    )
    _insert_memo(
        engine,
        memo_id=TGT_MEMO,
        user_id=owner,
        scope=SCOPE_CHARACTER,
        scope_id=TGT_CHARACTER,
        token=TGT_MEMO_TOKEN,
    )
    _insert_translation(
        engine, translation_id=TGT_TRANSLATION, user_id=owner, message_id=TGT_MESSAGE
    )
    _insert_auth_session(engine, auth_id=TGT_AUTH_SESSION, user_id=owner)


@pytest.fixture
def source_engine(db_settings: Settings, tmp_path: Path) -> Engine:
    """The **second** database, on its own file inside the per-test `tmp_path`.

    Built the way `tests/test_admin_db_router.py:1413-1446` builds its alternate database:
    a `model_copy` of `db_settings` with a different `data_dir` and `db_filename`, then
    `get_engine`. The `db_settings` fixture's `dispose_engines()` teardown clears it.
    """
    source_settings = db_settings.model_copy(
        update={"data_dir": tmp_path / "source", "db_filename": "source.sqlite"}
    )
    engine = get_engine(source_settings)
    _create_schema(engine)
    _seed_source(engine)
    return engine


@pytest.fixture
def target_engine(db_engine: Engine) -> Engine:
    """The instance `import_database` runs on: eligible, and far from empty."""
    _create_schema(db_engine)
    _seed_target(db_engine, ELIGIBLE_USERS)
    return db_engine


@pytest.fixture
def blank_engine(db_engine: Engine) -> Engine:
    """DoD-3's bootstrap shape: the registry applied, and not one row anywhere."""
    _create_schema(db_engine)
    return db_engine


# --- observation helpers --------------------------------------------------------------


def _envelope(engine: Engine) -> dict[str, Any]:
    """030's `database` envelope, as the JSON object a route would hand the service."""
    with engine.connect() as connection:
        built = export_database(connection)
    decoded: dict[str, Any] = json.loads(json.dumps(built))
    return decoded


def _owned_envelope(engine: Engine, granularity: str) -> dict[str, Any]:
    """One of the three roleplayer envelopes, for DoD-7."""
    with engine.connect() as connection:
        if granularity == "user":
            built = export_user(connection, SRC_PLAYER)
        elif granularity == "character":
            built = export_character(connection, SRC_PLAYER, SRC_CHARACTER_1)
        else:
            built = export_session(connection, SRC_PLAYER, SRC_SESSION_1)
    decoded: dict[str, Any] = json.loads(json.dumps(built))
    return decoded


def _run_import(engine: Engine, body: object) -> None:
    """The one call under test. The service owns the transaction."""
    with engine.connect() as connection:
        import_database(connection, body)


def _table_rows(engine: Engine, table: Table) -> list[tuple[Any, ...]]:
    """One table's whole content, primary-key ascending (`004.context.md` §Comparison)."""
    query = select(table).order_by(*table.primary_key.columns)
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(query).all()]


def _payload_rows(engine: Engine) -> dict[str, list[tuple[Any, ...]]]:
    return {table.name: _table_rows(engine, table) for table in PAYLOAD_TABLES}


def _snapshot(engine: Engine) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of every `metadata` table — what DoD-4 and DoD-6 compare."""
    return {
        table.name: _table_rows(engine, table)
        for table in schema.metadata.sorted_tables
    }


def _ids(engine: Engine, table: Table) -> list[int]:
    with engine.connect() as connection:
        rows = connection.execute(
            select(table.c.id).order_by(table.c.id)
        ).all()
    return [int(row[0]) for row in rows]


def _password_hash(engine: Engine, user_id: int) -> str | None:
    with engine.connect() as connection:
        stored = connection.execute(
            select(schema.users.c.password_hash).where(schema.users.c.id == user_id)
        ).scalar_one_or_none()
    return None if stored is None else str(stored)


def _related_to(engine: Engine, message_id: int) -> int | None:
    with engine.connect() as connection:
        stored = connection.execute(
            select(schema.messages.c.related_to).where(
                schema.messages.c.id == message_id
            )
        ).scalar_one_or_none()
    return None if stored is None else int(stored)


def _selectable_ids(engine: Engine, selectable: Any, session_id: int) -> list[int]:
    """The ids one of 023/decision-14's Core `select()` objects returns for a session."""
    query = (
        selectable.where(schema.messages.c.session_id == session_id)
        .order_by(schema.messages.c.id)
    )
    with engine.connect() as connection:
        return [int(row.id) for row in connection.execute(query).all()]


def _table_exists(engine: Engine, table_name: str) -> bool:
    """A file-local `sqlite_master` probe, so presence is observed without the code."""
    with engine.connect() as connection:
        found = connection.execute(
            text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
            {"name": table_name},
        ).first()
    return found is not None


def _dimension(engine: Engine, table_name: str) -> int | None:
    """024's own answer: `None` when that vec0 table is absent."""
    with engine.connect() as connection:
        return vector_table_dimension(connection, table_name)


def _vec_key_column(connection: Connection, table_name: str) -> str | None:
    rows = connection.execute(
        text("SELECT name FROM pragma_table_info(:table_name) WHERE pk = 1"),
        {"table_name": table_name},
    ).all()
    return None if not rows else str(rows[0][0])


def _seed_vectors(engine: Engine) -> None:
    """024's ensure at `SEEDED_DIMENSION`, then one serialized float32 row per table."""
    with engine.begin() as connection:
        ensure_vector_tables(connection, SEEDED_DIMENSION)
        for table_name, row_id, vector in SEEDED_VECTORS:
            key = _vec_key_column(connection, table_name)
            assert key is not None
            statement = text(
                f"INSERT INTO {table_name}({key}, embedding) VALUES (:row_id, :blob)"
            )
            connection.execute(
                statement,
                {"row_id": row_id, "blob": sqlite_vec.serialize_float32(vector)},
            )


def _vector_rows(engine: Engine, table_name: str) -> list[tuple[int, list[float]]]:
    """Every stored vector, key ascending; `[]` when the table is absent."""
    with engine.connect() as connection:
        key = _vec_key_column(connection, table_name)
        if key is None:
            return []
        query = text(f"SELECT {key}, embedding FROM {table_name} ORDER BY {key}")
        rows = connection.execute(query).all()
        return [
            (int(row[0]), list(struct.unpack(f"<{SEEDED_DIMENSION}f", bytes(row[1]))))
            for row in rows
        ]


def _match_ids(engine: Engine, table_name: str, token: str) -> list[int]:
    """The rowids a full-text `MATCH` on one token returns, ascending."""
    query = text(
        f"SELECT rowid FROM {table_name} "
        f"WHERE {table_name} MATCH :token ORDER BY rowid"
    )
    with engine.connect() as connection:
        return [int(row[0]) for row in connection.execute(query, {"token": token}).all()]


def _integrity_ok(engine: Engine, table_name: str) -> bool:
    """FTS5's own `integrity-check`; False when the index disagrees with its content."""
    with engine.connect() as connection:
        try:
            connection.exec_driver_sql(
                f"INSERT INTO {table_name}({table_name}) VALUES('integrity-check')"
            )
        except SQLAlchemyError:
            return False
    return True


# --- envelope mutators (DoD-5, DoD-6, DoD-11) ----------------------------------------


def _with_wrong_schema_version(body: dict[str, Any]) -> dict[str, Any]:
    mutated = copy.deepcopy(body)
    mutated["schema_version"] = SCHEMA_VERSION + 1
    return mutated


def _with_duplicate_username(body: dict[str, Any]) -> dict[str, Any]:
    """Two `users` rows sharing one username — the UNIQUE refusal, with the sentinel."""
    mutated = copy.deepcopy(body)
    rows = mutated["payload"][schema.users.name]
    assert len(rows) == 2, "the source seeds exactly two users"
    for row in rows:
        row["username"] = SENTINEL_USERNAME
    return mutated


def _with_dangling_setup_character(body: dict[str, Any]) -> dict[str, Any]:
    """A `setups` row naming no payload character — the FK refusal."""
    mutated = copy.deepcopy(body)
    rows = mutated["payload"][schema.setups.name]
    assert rows, "the source seeds setups"
    rows[0]["character_id"] = str(SPARE_ID)
    return mutated


def _with_dangling_memo_scope(body: dict[str, Any]) -> dict[str, Any]:
    """A `scope='character'` memo naming no payload character — the scope-target miss."""
    mutated = copy.deepcopy(body)
    rows = mutated["payload"][schema.memos.name]
    targets = [row for row in rows if row["scope"] == SCOPE_CHARACTER]
    assert targets, "the source seeds a character-scoped memo"
    targets[0]["scope_id"] = str(SPARE_ID)
    return mutated


REFUSED_ENVELOPES = {
    "duplicate_username": _with_duplicate_username,
    "dangling_setup_character": _with_dangling_setup_character,
    "dangling_memo_scope": _with_dangling_memo_scope,
}

INELIGIBLE_SHAPES = {
    "two_admins": TWO_ADMINS,
    "admin_and_roleplayer": ADMIN_AND_ROLEPLAYER,
    "one_roleplayer": ONE_ROLEPLAYER,
}


# === DoD-1 ============================================================================


def test_replaces_a_non_empty_instance_with_the_source_rows__S031_004_DoD1(
    source_engine: Engine, target_engine: Engine
) -> None:
    """DoD-1 — after the replace every payload table holds exactly the source rows.

    US-077.AC-2, UC-061. The comparison is per-table `SELECT *` ordered by primary key,
    over the table list derived from `schema.metadata` minus 030's exclusion set.
    """
    source_rows = _payload_rows(source_engine)

    # The source really is the instance DoD-1 describes.
    assert _ids(source_engine, schema.users) == sorted([SRC_ADMIN, SRC_PLAYER])
    assert _ids(source_engine, schema.characters) == sorted(
        [SRC_CHARACTER_1, SRC_CHARACTER_2]
    )
    assert source_rows[schema.setups.name], "setups seeded"
    assert source_rows[schema.sessions.name], "sessions seeded"
    assert source_rows[schema.llm_servers.name], "an llm_servers row seeded"
    assert source_rows[schema.models.name], "a models row seeded"
    assert len(source_rows[schema.memos.name]) == 4, "a memo at each of the four scopes"
    assert len(source_rows[schema.messages.name]) == 6, "settled, buried and zone rows"

    # The target really is non-empty first.
    before = _snapshot(target_engine)
    assert before[schema.users.name] and len(before[schema.users.name]) == 1
    assert TGT_CHARACTER in _ids(target_engine, schema.characters)
    assert before[schema.auth_sessions.name], "the target holds an auth_sessions row"

    _run_import(target_engine, _envelope(source_engine))

    assert _payload_rows(target_engine) == source_rows
    # Ids are preserved, stated against the seeded constants and not against the read.
    assert _ids(target_engine, schema.users) == sorted([SRC_ADMIN, SRC_PLAYER])
    assert _ids(target_engine, schema.characters) == sorted(
        [SRC_CHARACTER_1, SRC_CHARACTER_2]
    )
    assert _ids(target_engine, schema.sessions) == sorted([SRC_SESSION_1, SRC_SESSION_2])
    assert _ids(target_engine, schema.memos) == sorted(
        [SRC_MEMO_USER, SRC_MEMO_CHARACTER, SRC_MEMO_SETUP, SRC_MEMO_SESSION]
    )
    # The source itself is untouched by the import.
    assert _payload_rows(source_engine) == source_rows


def test_every_restored_column_survives_verbatim__S031_004_DoD1(
    source_engine: Engine, target_engine: Engine
) -> None:
    """DoD-1 — the columns the replace exists to carry, named one by one.

    The archived character, the `"$NAME"` key ref, the designated model and the four memo
    scopes are each read back under their **source** id, so a wholesale row comparison
    cannot be satisfied by a table that merely happens to be equal.
    """
    _run_import(target_engine, _envelope(source_engine))

    with target_engine.connect() as connection:
        character = connection.execute(
            select(schema.characters).where(schema.characters.c.id == SRC_CHARACTER_2)
        ).one()
        assert character.archived_at == ARCHIVED_AT
        assert character.user_id == SRC_PLAYER

        server = connection.execute(
            select(schema.llm_servers).where(schema.llm_servers.c.id == SRC_SERVER)
        ).one()
        assert server.api_key_ref == SRC_API_KEY_REF

        model = connection.execute(
            select(schema.models).where(schema.models.c.id == SRC_MODEL)
        ).one()
        assert model.is_embedding_designated is True
        assert model.embedding_dim == SEEDED_DIMENSION
        assert model.server_id == SRC_SERVER

        admin = connection.execute(
            select(schema.users).where(schema.users.c.id == SRC_ADMIN)
        ).one()
        assert admin.role == Role.ADMIN
        assert admin.username == "source-admin"

        scopes = connection.execute(
            select(schema.memos.c.id, schema.memos.c.scope, schema.memos.c.scope_id)
            .order_by(schema.memos.c.id)
        ).all()
    assert [(int(row[0]), row[1], int(row[2])) for row in scopes] == [
        (SRC_MEMO_USER, SCOPE_USER, SRC_PLAYER),
        (SRC_MEMO_CHARACTER, SCOPE_CHARACTER, SRC_CHARACTER_1),
        (SRC_MEMO_SETUP, SCOPE_SETUP, SRC_SETUP_1),
        (SRC_MEMO_SESSION, SCOPE_SESSION, SRC_SESSION_1),
    ]


# === DoD-2 ============================================================================


def test_the_replaced_account_and_its_rows_are_gone__S031_004_DoD2(
    source_engine: Engine, target_engine: Engine
) -> None:
    """DoD-2 — US-077.AC-2: the previous admin, their character and their login are gone,
    and `auth_sessions` / `translations` hold no rows at all."""
    assert TGT_ADMIN in _ids(target_engine, schema.users)
    assert TGT_CHARACTER in _ids(target_engine, schema.characters)
    assert _ids(target_engine, schema.auth_sessions) == [TGT_AUTH_SESSION]
    assert _ids(target_engine, TRANSLATIONS) == [TGT_TRANSLATION]

    _run_import(target_engine, _envelope(source_engine))

    assert TGT_ADMIN not in _ids(target_engine, schema.users)
    assert TGT_CHARACTER not in _ids(target_engine, schema.characters)
    assert TGT_SESSION not in _ids(target_engine, schema.sessions)
    assert TGT_MEMO not in _ids(target_engine, schema.memos)
    for table in EXCLUDED_TABLES:
        assert _table_rows(target_engine, table) == []


def test_a_restored_password_still_verifies__S031_004_DoD2(
    source_engine: Engine, target_engine: Engine
) -> None:
    """DoD-2 — the password chosen at seed time and hashed through
    `services/passwords.py` verifies against the restored hash through the same seam."""
    source_hash = _password_hash(source_engine, SRC_ADMIN)
    assert source_hash is not None
    assert verify_password(source_hash, SRC_ADMIN_PASSWORD) is True

    _run_import(target_engine, _envelope(source_engine))

    restored = _password_hash(target_engine, SRC_ADMIN)
    assert restored is not None
    assert verify_password(restored, SRC_ADMIN_PASSWORD) is True
    assert verify_password(restored, WRONG_PASSWORD) is False

    player_hash = _password_hash(target_engine, SRC_PLAYER)
    assert player_hash is not None
    assert verify_password(player_hash, SRC_PLAYER_PASSWORD) is True
    assert verify_password(player_hash, SRC_ADMIN_PASSWORD) is False


# === DoD-3 ============================================================================


def test_restores_onto_a_database_with_no_users__S031_004_DoD3(
    source_engine: Engine, blank_engine: Engine
) -> None:
    """DoD-3 — the bootstrap path `fast/003` will use: tables created, every one empty."""
    for table in schema.metadata.sorted_tables:
        assert _table_rows(blank_engine, table) == []

    _run_import(blank_engine, _envelope(source_engine))

    assert _payload_rows(blank_engine) == _payload_rows(source_engine)
    assert _ids(blank_engine, schema.users) == sorted([SRC_ADMIN, SRC_PLAYER])
    for table in EXCLUDED_TABLES:
        assert _table_rows(blank_engine, table) == []


# === DoD-4 ============================================================================


@pytest.mark.parametrize("shape", sorted(INELIGIBLE_SHAPES))
def test_refuses_an_ineligible_instance_and_changes_nothing__S031_004_DoD4(
    source_engine: Engine, db_engine: Engine, shape: str
) -> None:
    """DoD-4 — two admins, an admin plus a roleplayer, and a lone roleplayer are each
    `database_not_empty`, and every row of every table survives."""
    users = INELIGIBLE_SHAPES[shape]
    _create_schema(db_engine)
    _seed_target(db_engine, users)

    before = _snapshot(db_engine)
    assert len(before[schema.users.name]) == len(users)
    assert before[schema.characters.name], "the instance holds rows to preserve"
    assert before[schema.auth_sessions.name], "including an auth_sessions row"
    assert before[TRANSLATIONS.name], "and a translations row"

    with pytest.raises(DatabaseNotEmptyError) as refusal:
        _run_import(db_engine, _envelope(source_engine))

    assert refusal.value.detail == {}
    assert _snapshot(db_engine) == before


# === DoD-5 ============================================================================


def test_the_eligibility_guard_runs_before_validation__S031_004_DoD5(
    source_engine: Engine, db_engine: Engine
) -> None:
    """DoD-5 — on an ineligible instance a malformed envelope still answers
    `database_not_empty`, never `export_invalid`."""
    _create_schema(db_engine)
    _seed_target(db_engine, TWO_ADMINS)
    before = _snapshot(db_engine)
    assert len(before[schema.users.name]) == 2

    malformed = _with_wrong_schema_version(_envelope(source_engine))
    assert malformed["schema_version"] != SCHEMA_VERSION

    with pytest.raises(DatabaseNotEmptyError) as refusal:
        _run_import(db_engine, malformed)

    assert not isinstance(refusal.value, ExportInvalidError)
    assert refusal.value.detail == {}
    assert _snapshot(db_engine) == before


# === DoD-6 ============================================================================


@pytest.mark.parametrize("case", sorted(REFUSED_ENVELOPES))
def test_a_refused_row_rolls_the_whole_replace_back__S031_004_DoD6(
    source_engine: Engine, target_engine: Engine, case: str
) -> None:
    """DoD-6 — a UNIQUE clash, a dangling `setups.character_id` and a dangling
    character-scoped `memos.scope_id` are each `malformed_payload`, and the original
    admin, their rows and their `auth_sessions` row are all still there, unchanged.

    Decision 15: only FK / UNIQUE / CHECK failures reach the write phase as an
    `IntegrityError`, so no enum or out-of-range-id case belongs here.
    """
    before = _snapshot(target_engine)
    assert before[schema.users.name] and len(before[schema.users.name]) == 1
    assert before[schema.characters.name]
    assert before[schema.auth_sessions.name]

    body = REFUSED_ENVELOPES[case](_envelope(source_engine))

    with pytest.raises(ExportInvalidError) as refusal:
        _run_import(target_engine, body)

    assert refusal.value.reason == REASON_MALFORMED_PAYLOAD
    assert refusal.value.detail == {"reason": REASON_MALFORMED_PAYLOAD}
    assert _snapshot(target_engine) == before
    assert TGT_ADMIN in _ids(target_engine, schema.users)
    assert _ids(target_engine, schema.auth_sessions) == [TGT_AUTH_SESSION]


# === DoD-7 ============================================================================


@pytest.mark.parametrize("granularity", ["user", "character", "session"])
def test_another_granularity_is_refused__S031_004_DoD7(
    source_engine: Engine, target_engine: Engine, granularity: str
) -> None:
    """DoD-7 — a `user`, `character` or `session` envelope is `wrong_granularity`, and
    nothing on the instance changes."""
    before = _snapshot(target_engine)
    assert before[schema.users.name], "there is state that could have been lost"

    body = _owned_envelope(source_engine, granularity)
    assert body["granularity"] == granularity

    with pytest.raises(ExportInvalidError) as refusal:
        _run_import(target_engine, body)

    assert refusal.value.reason == REASON_WRONG_GRANULARITY
    assert refusal.value.detail == {"reason": REASON_WRONG_GRANULARITY}
    assert _snapshot(target_engine) == before


# === DoD-8 ============================================================================


def test_existing_vector_tables_are_dropped_on_success__S031_004_DoD8(
    source_engine: Engine, target_engine: Engine
) -> None:
    """DoD-8, first limb — present with rows before, absent afterwards."""
    _seed_vectors(target_engine)
    assert _dimension(target_engine, MEMO_VEC_TABLE) == SEEDED_DIMENSION
    assert _dimension(target_engine, SESSION_VEC_TABLE) == SEEDED_DIMENSION
    assert _vector_rows(target_engine, MEMO_VEC_TABLE) == [(TGT_MEMO, MEMO_VECTOR)]
    assert _vector_rows(target_engine, SESSION_VEC_TABLE) == [
        (TGT_SESSION, SESSION_VECTOR)
    ]

    _run_import(target_engine, _envelope(source_engine))

    assert _ids(target_engine, schema.users) == sorted([SRC_ADMIN, SRC_PLAYER])
    for table_name in (MEMO_VEC_TABLE, SESSION_VEC_TABLE):
        assert _dimension(target_engine, table_name) is None
        assert _table_exists(target_engine, table_name) is False


def test_absent_vector_tables_stay_absent__S031_004_DoD8(
    source_engine: Engine, target_engine: Engine
) -> None:
    """DoD-8, second limb — they did not exist, so nothing is dropped and nothing fails."""
    for table_name in (MEMO_VEC_TABLE, SESSION_VEC_TABLE):
        assert _dimension(target_engine, table_name) is None

    _run_import(target_engine, _envelope(source_engine))

    assert _payload_rows(target_engine) == _payload_rows(source_engine)
    for table_name in (MEMO_VEC_TABLE, SESSION_VEC_TABLE):
        assert _dimension(target_engine, table_name) is None
        assert _table_exists(target_engine, table_name) is False


def test_a_failed_replace_leaves_the_vector_tables__S031_004_DoD8(
    source_engine: Engine, target_engine: Engine
) -> None:
    """DoD-8, third limb — the UNIQUE refusal rolls the DDL back too: both tables are
    still there, with their rows and their original dimension."""
    _seed_vectors(target_engine)
    assert _dimension(target_engine, MEMO_VEC_TABLE) == SEEDED_DIMENSION
    assert _dimension(target_engine, SESSION_VEC_TABLE) == SEEDED_DIMENSION

    body = _with_duplicate_username(_envelope(source_engine))
    with pytest.raises(ExportInvalidError) as refusal:
        _run_import(target_engine, body)
    assert refusal.value.reason == REASON_MALFORMED_PAYLOAD

    assert _dimension(target_engine, MEMO_VEC_TABLE) == SEEDED_DIMENSION
    assert _dimension(target_engine, SESSION_VEC_TABLE) == SEEDED_DIMENSION
    assert _vector_rows(target_engine, MEMO_VEC_TABLE) == [(TGT_MEMO, MEMO_VECTOR)]
    assert _vector_rows(target_engine, SESSION_VEC_TABLE) == [
        (TGT_SESSION, SESSION_VECTOR)
    ]


# === DoD-9 ============================================================================


def test_the_full_text_indexes_follow_the_restored_rows__S031_004_DoD9(
    source_engine: Engine, target_engine: Engine
) -> None:
    """DoD-9 — both FTS tables exist, a restored memo token and a restored record token
    are each found **under the preserved id**, a token only the wiped target held is not
    found, and FTS5's own `integrity-check` passes on both tables."""
    # The target's own memo is indexed first, so its later absence is the wipe's triggers.
    with target_engine.begin() as connection:
        ensure_fts_tables(connection)
    assert _match_ids(target_engine, MEMO_FTS_TABLE, TGT_MEMO_TOKEN) == [TGT_MEMO]
    assert _match_ids(target_engine, MESSAGE_FTS_TABLE, TGT_RECORD_TOKEN) == [TGT_MESSAGE]

    _run_import(target_engine, _envelope(source_engine))

    assert _table_exists(target_engine, MEMO_FTS_TABLE) is True
    assert _table_exists(target_engine, MESSAGE_FTS_TABLE) is True

    assert _match_ids(target_engine, MEMO_FTS_TABLE, SRC_MEMO_TOKEN_CHARACTER) == [
        SRC_MEMO_CHARACTER
    ]
    assert _match_ids(target_engine, MEMO_FTS_TABLE, SRC_MEMO_TOKEN_SESSION) == [
        SRC_MEMO_SESSION
    ]
    assert _match_ids(target_engine, MESSAGE_FTS_TABLE, SRC_RECORD_TOKEN_1) == [
        SRC_HEAD_1
    ]
    assert _match_ids(target_engine, MESSAGE_FTS_TABLE, SRC_RECORD_TOKEN_2) == [
        SRC_HEAD_2
    ]

    assert _match_ids(target_engine, MEMO_FTS_TABLE, TGT_MEMO_TOKEN) == []
    assert _match_ids(target_engine, MESSAGE_FTS_TABLE, TGT_RECORD_TOKEN) == []

    assert _integrity_ok(target_engine, MEMO_FTS_TABLE) is True
    assert _integrity_ok(target_engine, MESSAGE_FTS_TABLE) is True


# === DoD-10 ===========================================================================


def test_buried_rows_and_the_two_selectables_match_the_source__S031_004_DoD10(
    source_engine: Engine, target_engine: Engine
) -> None:
    """DoD-10 — buried messages keep their `related_to`, which is the **preserved** head
    id, and `settled_entries` / `current_zone` show the source's record and zone.

    Decision 14: both are Core `select()` objects, so they are executed directly.
    """
    source_record = _selectable_ids(source_engine, schema.settled_entries, SRC_SESSION_1)
    source_zone = _selectable_ids(source_engine, schema.current_zone, SRC_SESSION_1)
    assert source_record == [SRC_HEAD_1, SRC_HEAD_2]
    assert source_zone == [SRC_ZONE_1, SRC_ZONE_2]
    assert _related_to(source_engine, SRC_BURIED_1) == SRC_HEAD_1

    _run_import(target_engine, _envelope(source_engine))

    assert _related_to(target_engine, SRC_BURIED_1) == SRC_HEAD_1
    assert _related_to(target_engine, SRC_BURIED_2) == SRC_HEAD_2
    assert (
        _selectable_ids(target_engine, schema.settled_entries, SRC_SESSION_1)
        == source_record
    )
    assert (
        _selectable_ids(target_engine, schema.current_zone, SRC_SESSION_1) == source_zone
    )


# === DoD-11 ===========================================================================


def test_a_constraint_refusal_leaks_no_payload_value__S031_004_DoD11(
    source_engine: Engine, target_engine: Engine
) -> None:
    """DoD-11 — `detail` is exactly `{"reason": "malformed_payload"}`, and the duplicated
    row's sentinel username appears in neither the message nor the detail."""
    body = _with_duplicate_username(_envelope(source_engine))
    assert all(
        row["username"] == SENTINEL_USERNAME
        for row in body["payload"][schema.users.name]
    )

    with pytest.raises(ExportInvalidError) as refusal:
        _run_import(target_engine, body)

    error = refusal.value
    assert error.detail == {"reason": REASON_MALFORMED_PAYLOAD}
    assert SENTINEL_USERNAME not in str(error)
    assert error.message is not None
    assert SENTINEL_USERNAME not in error.message
    assert SENTINEL_USERNAME not in json.dumps(error.to_wire())
    assert SENTINEL_USERNAME not in repr(error.args)


# === DoD-12 ===========================================================================


def test_a_new_dimension_is_accepted_after_the_replace__S031_004_DoD12(
    source_engine: Engine, target_engine: Engine
) -> None:
    """DoD-12 — because the tables were dropped rather than cleared, 024's
    `ensure_vector_tables(conn, 16)` creates them at the new dimension without raising
    `dimension_mismatch`."""
    _seed_vectors(target_engine)
    assert _dimension(target_engine, MEMO_VEC_TABLE) == SEEDED_DIMENSION
    assert _dimension(target_engine, SESSION_VEC_TABLE) == SEEDED_DIMENSION
    assert LATER_DIMENSION != SEEDED_DIMENSION

    _run_import(target_engine, _envelope(source_engine))

    with target_engine.begin() as connection:
        ensure_vector_tables(connection, LATER_DIMENSION)

    assert _dimension(target_engine, MEMO_VEC_TABLE) == LATER_DIMENSION
    assert _dimension(target_engine, SESSION_VEC_TABLE) == LATER_DIMENSION
    assert _vector_rows(target_engine, MEMO_VEC_TABLE) == []
    assert _vector_rows(target_engine, SESSION_VEC_TABLE) == []
