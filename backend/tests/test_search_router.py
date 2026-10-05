"""`GET /api/search` — feature 029, step 003 (DoD-1..9).

Every expected value comes from the **spec**, never from the implementation:
`docs/plans/029.my-search/003.search-route.md` (Interface intent and Definition of done),
`003.context.md` (the router pattern, the error codes and the test notes) and the feature
`context.md` — **D1** (one route, five fixed groups, a blank `q` answers five empty lists and
opens no model), **U1** (an embedding failure fails the whole request, envelope unchanged),
**U3** (archived rows are returned and marked), **R5** / **UC-065** (owner scope, tested as an
absence) and above all the **wire contract**, which is this file's specification:

    {
      "characters": [ { "id", "name", "archived" } ],
      "setups":     [ { "id", "name", "character_id", "character_name", "archived" } ],
      "sessions":   [ { "id", "character_name", "setup_name" | null, "created_at", "archived" } ],
      "entries":    [ { "id", "session_id", "snippet", "character_name", "session_created_at" } ],
      "memos":      [ { "id", "scope", "scope_id" | null, "character_id" | null,
                        "snippet", "is_enabled" } ]
    }

Ids are decimal **strings**; memo `scope_id` is **null at the `"user"` level** and `character_id`
is the character page the note routes to (`scope_id` for `"character"`, the setup's
`character_id` for `"setup"`, null for `"user"` and `"session"`). Errors use
`{"error": {"code", "message", "detail"}}`: 401 without a session, `no_embedding_model` 409,
`llm_unreachable` 502.

Bindings come from `## Skeleton` → "Step 003 — frozen interface (2026-10-05)" in `status.md`:
`GET /api/search` with the optional query parameter `q` (default `""`), behind `require_user`.
Nothing here imports `app.models.search` or `app.routers.search`: the wire **is** the surface
this step promises, and every assertion is made against a parsed response body.

How the expectations are derived
-------------------------------
* **Nothing is mocked and the port is never stubbed.** The search tables are the real ones,
  created only through 024's `ensure_fts_tables` / `ensure_vector_tables` at dimension 8;
  vectors are written only through 024's `write_vector` from `tests/llm_fakes.py`'s pure
  `embedding_vector(text, dim)`; a designated model is a raw `llm_servers` + `models` pair with
  `api_key_ref=None`; the provider arrives through `app.dependency_overrides` on the shared
  `get_llm_client_factory` (024 D9), never by patching a module global. The one `monkeypatch`
  below neutralises the app factory's logging call so no test writes into `backend/data/logs/`
  — the house form every router test in this suite uses.
* **A row meant to match carries the token in its text *and* the fake's vector of the query
  text**, so both of the port's arms reach it. An absence is therefore the owner predicate's
  work, never a needle that missed.
* **Owner isolation is proved with twins**: B's character, setup, session, settled entry and
  note carry the same names, texts, bodies and the **same** vectors as A's.
* **Ids are all above 2^60**, so a float round-trip would be visible in the decimal string.
* **Order is asserted only where the spec defines it** — the body's five top-level keys, in
  UC-059 order (US-075.AC-1), read off `json.loads`, which preserves object order. Within a
  group, rows are compared by id; no fused score and no tie order is asserted.

Each test name ends `__S029_003_DoD<n>` with the DoD item it covers. DoD-10 is `[manual/live]`
(the registration position and the docstrings) and carries no test here.

Mechanics (`context.md` "Test conventions"): the real application factory pinned to a per-test
SQLite file through `dependency_overrides[get_settings]`, raw inserts only, two users A and B,
and every helper file-local. `tests/conftest.py` and `tests/llm_fakes.py` are untouched.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Table

from app.config import Settings, get_settings
from app.db import schema
from app.db.search_tables import MEMO_VEC_TABLE, SESSION_VEC_TABLE, ensure_fts_tables, ensure_vector_tables
from app.dependencies import get_llm_client_factory
from app.main import create_app
from app.roles import Role
from app.services.embedding import write_vector
from app.services.passwords import hash_password
from tests.llm_fakes import FakeClientFactory, embedding_vector, fake_factory, unreachable_factory

#: The route and its one parameter (`context.md` Literals: `GET /api/search`, param `q`).
SEARCH_PATH = "/api/search"
LOGIN_PATH = "/api/auth/login"

#: The body's five top-level keys, in UC-059 order (D1, wire contract).
GROUP_KEYS = ["characters", "setups", "sessions", "entries", "memos"]

#: The exact key set of one hit per kind (wire contract; DoD-3 allows no extra key).
CHARACTER_HIT_KEYS = {"id", "name", "archived"}
SETUP_HIT_KEYS = {"id", "name", "character_id", "character_name", "archived"}
SESSION_HIT_KEYS = {"id", "character_name", "setup_name", "created_at", "archived"}
ENTRY_HIT_KEYS = {"id", "session_id", "snippet", "character_name", "session_created_at"}
MEMO_HIT_KEYS = {"id", "scope", "scope_id", "character_id", "snippet", "is_enabled"}

HIT_KEYS = {
    "characters": CHARACTER_HIT_KEYS,
    "setups": SETUP_HIT_KEYS,
    "sessions": SESSION_HIT_KEYS,
    "entries": ENTRY_HIT_KEYS,
    "memos": MEMO_HIT_KEYS,
}

#: Keys no hit of any kind may carry (DoD-3; US-119 — a note row has no title).
FORBIDDEN_HIT_KEYS = ("title", "body", "is_forced")

#: The two groups whose rows carry a snippet; its exact text is the port's, so only the token
#: is asserted (the spec promises plain text holding the match, not a fixed fragment).
SNIPPET_GROUPS = ("entries", "memos")

#: Every id field the wire contract declares, across all five kinds.
ID_FIELDS = ("id", "character_id", "session_id", "scope_id")

NOT_AUTHENTICATED = "not_authenticated"
NO_EMBEDDING_MODEL = "no_embedding_model"
LLM_UNREACHABLE = "llm_unreachable"

#: The standard envelope's inner keys (`context.md` wire contract).
ENVELOPE_KEYS = {"code", "message", "detail"}

#: The seeded instant, in the project's fixed-width UTC text form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: The instant rows seeded already settled carry.
SEEDED_SETTLED_AT = "2025-12-31T00:00:00.000000+00:00"

#: Every id below is above 2^60 = 1152921504606846976, so a float round-trip would show.
SNOWFLAKE_FLOOR = 2**60

#: The designated embedding width throughout; 8 is what 024 and 025 use.
DIMENSION = 8

#: DoD-8's mismatch: the vector tables stay at `DIMENSION`, the designated model declares this.
MISMATCHED_DIMENSION = 16

#: The searched term. Lower case, so FTS5's verbatim snippet text contains it as typed.
TOKEN = "kaelith"

USER_A_ID = 1_292_000_000_000_000_001
USER_A_NAME = "aster"
USER_A_PASSWORD = "a quiet river at dusk"

USER_B_ID = 1_292_000_000_000_000_002
USER_B_NAME = "briar"
USER_B_PASSWORD = "salt and lantern light"

CHAR_A = 1_292_000_000_000_000_101
CHAR_A_ARCHIVED = 1_292_000_000_000_000_102
CHAR_A_SPARE = 1_292_000_000_000_000_103
CHAR_B = 1_292_000_000_000_000_104

SETUP_A = 1_292_000_000_000_000_151
SETUP_A_ARCHIVED = 1_292_000_000_000_000_152
SETUP_A_SPARE = 1_292_000_000_000_000_153
SETUP_B = 1_292_000_000_000_000_154

SESSION_WITH_SETUP = 1_292_000_000_000_000_201
SESSION_NO_SETUP = 1_292_000_000_000_000_202
SESSION_ARCHIVED = 1_292_000_000_000_000_203
SESSION_B = 1_292_000_000_000_000_204

ENTRY_SETTLED = 1_292_000_000_000_000_301
ENTRY_B = 1_292_000_000_000_000_302

MEMO_USER = 1_292_000_000_000_000_401
MEMO_CHARACTER = 1_292_000_000_000_000_402
MEMO_SETUP = 1_292_000_000_000_000_403
MEMO_SESSION = 1_292_000_000_000_000_404
MEMO_DISABLED = 1_292_000_000_000_000_405
MEMO_B = 1_292_000_000_000_000_406

SERVER_ID = 1_292_000_000_000_000_901
MODEL_ID = 1_292_000_000_000_000_902

BASE_URL = "http://embedding.test:8080/v1"
MODEL_NAME = "the-designated-embedding-model"

# --- the seeded texts -------------------------------------------------------------------------

CHARACTER_NAME = "Kaelith"
ARCHIVED_CHARACTER_NAME = "Kaelith of the archive"
SPARE_CHARACTER_NAME = "the understudy"
PERSONA = "The lamplighter who keeps the tide-beacons of the drowned coast."

SETUP_NAME = "Kaelith's observatory"
ARCHIVED_SETUP_NAME = "Kaelith's shuttered observatory"
SPARE_SETUP_NAME = "the spare stage"
SETUP_DESCRIPTION = "The drowned observatory, three nights after the spring tide."

SETTLED_TEXT = f"the {TOKEN} beacon stayed lit until the tide turned"

#: Each session carries its own `created_at`, so hydration cannot pass the wrong one unnoticed.
CREATED_WITH_SETUP = "2026-02-01T00:00:00.000000+00:00"
CREATED_NO_SETUP = "2026-02-02T00:00:00.000000+00:00"
CREATED_ARCHIVED = "2026-02-03T00:00:00.000000+00:00"
CREATED_OTHER_OWNER = "2026-02-04T00:00:00.000000+00:00"

A_SESSION_IDS = (SESSION_WITH_SETUP, SESSION_NO_SETUP, SESSION_ARCHIVED)
A_MEMO_IDS = (MEMO_USER, MEMO_CHARACTER, MEMO_SETUP, MEMO_SESSION, MEMO_DISABLED)

#: Every id of A's that may appear on the wire, and every id of B's (DoD-5 compares both ways).
A_WIRE_IDS = frozenset(
    {CHAR_A, CHAR_A_ARCHIVED, CHAR_A_SPARE, SETUP_A, SETUP_A_ARCHIVED, SETUP_A_SPARE, ENTRY_SETTLED}
    | set(A_SESSION_IDS)
    | set(A_MEMO_IDS)
)
B_WIRE_IDS = frozenset({CHAR_B, SETUP_B, SESSION_B, ENTRY_B, MEMO_B})


def _memo_body(marker: str) -> str:
    """A note body holding the token, so the lexical arm reaches it too."""
    return f"{TOKEN} remembers the {marker}"


# --- the expected wire rows (the contract, row by row) ----------------------------------------
#
# Every value below is read off the wire contract and the seeded data: `archived` is the row's
# own `archived_at` reduced to a bool (U3); a session's `setup_name` is null when it has no
# setup; an entry's `session_created_at` is the **session's** start, not the message's; a note's
# `scope_id` is null at the `"user"` level and its `character_id` is the page it routes to.
# `snippet` is excluded — it is compared separately, by the token it must contain.

EXPECTED_CHARACTERS: dict[str, dict[str, Any]] = {
    str(CHAR_A): {"id": str(CHAR_A), "name": CHARACTER_NAME, "archived": False},
    str(CHAR_A_ARCHIVED): {"id": str(CHAR_A_ARCHIVED), "name": ARCHIVED_CHARACTER_NAME, "archived": True},
}

EXPECTED_SETUPS: dict[str, dict[str, Any]] = {
    str(SETUP_A): {
        "id": str(SETUP_A),
        "name": SETUP_NAME,
        "character_id": str(CHAR_A),
        "character_name": CHARACTER_NAME,
        "archived": False,
    },
    str(SETUP_A_ARCHIVED): {
        "id": str(SETUP_A_ARCHIVED),
        "name": ARCHIVED_SETUP_NAME,
        "character_id": str(CHAR_A),
        "character_name": CHARACTER_NAME,
        "archived": True,
    },
}

EXPECTED_SESSIONS: dict[str, dict[str, Any]] = {
    str(SESSION_WITH_SETUP): {
        "id": str(SESSION_WITH_SETUP),
        "character_name": CHARACTER_NAME,
        "setup_name": SETUP_NAME,
        "created_at": CREATED_WITH_SETUP,
        "archived": False,
    },
    str(SESSION_NO_SETUP): {
        "id": str(SESSION_NO_SETUP),
        "character_name": CHARACTER_NAME,
        "setup_name": None,
        "created_at": CREATED_NO_SETUP,
        "archived": False,
    },
    str(SESSION_ARCHIVED): {
        "id": str(SESSION_ARCHIVED),
        "character_name": CHARACTER_NAME,
        "setup_name": SETUP_NAME,
        "created_at": CREATED_ARCHIVED,
        "archived": True,
    },
}

EXPECTED_ENTRIES: dict[str, dict[str, Any]] = {
    str(ENTRY_SETTLED): {
        "id": str(ENTRY_SETTLED),
        "session_id": str(SESSION_WITH_SETUP),
        "character_name": CHARACTER_NAME,
        "session_created_at": CREATED_WITH_SETUP,
    },
}

EXPECTED_MEMOS: dict[str, dict[str, Any]] = {
    str(MEMO_USER): {
        "id": str(MEMO_USER),
        "scope": "user",
        "scope_id": None,
        "character_id": None,
        "is_enabled": True,
    },
    str(MEMO_CHARACTER): {
        "id": str(MEMO_CHARACTER),
        "scope": "character",
        "scope_id": str(CHAR_A),
        "character_id": str(CHAR_A),
        "is_enabled": True,
    },
    str(MEMO_SETUP): {
        "id": str(MEMO_SETUP),
        "scope": "setup",
        "scope_id": str(SETUP_A_SPARE),
        "character_id": str(CHAR_A_SPARE),
        "is_enabled": True,
    },
    str(MEMO_SESSION): {
        "id": str(MEMO_SESSION),
        "scope": "session",
        "scope_id": str(SESSION_WITH_SETUP),
        "character_id": None,
        "is_enabled": True,
    },
    str(MEMO_DISABLED): {
        "id": str(MEMO_DISABLED),
        "scope": "character",
        "scope_id": str(CHAR_A),
        "character_id": str(CHAR_A),
        "is_enabled": False,
    },
}

EXPECTED_GROUPS: dict[str, dict[str, dict[str, Any]]] = {
    "characters": EXPECTED_CHARACTERS,
    "setups": EXPECTED_SETUPS,
    "sessions": EXPECTED_SESSIONS,
    "entries": EXPECTED_ENTRIES,
    "memos": EXPECTED_MEMOS,
}

#: B's own expected id per group, for the second half of DoD-5.
EXPECTED_B_IDS = {
    "characters": {str(CHAR_B)},
    "setups": {str(SETUP_B)},
    "sessions": {str(SESSION_B)},
    "entries": {str(ENTRY_B)},
    "memos": {str(MEMO_B)},
}


# --- fixtures and raw-insert helpers (file-local; no service is used to seed) -----------------


@pytest.fixture(autouse=True)
def _quiet_factory_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise the factory's logging call so these tests touch no global sinks or log files."""
    monkeypatch.setattr("app.main.configure_logging", lambda settings: None)


def _servers() -> Table:
    return schema.metadata.tables["llm_servers"]


def _models() -> Table:
    return schema.metadata.tables["models"]


def _insert_user(engine: Engine, *, user_id: int, username: str, password: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash=hash_password(password),
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
    user_id: int = USER_A_ID,
    name: str,
    sheet: str = "",
    archived_at: str | None = None,
) -> None:
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
    user_id: int = USER_A_ID,
    name: str,
    description: str = "",
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
    user_id: int = USER_A_ID,
    character_id: int = CHAR_A,
    setup_id: int | None = None,
    archived_at: str | None = None,
    created_at: str = TIMESTAMP,
) -> None:
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
    user_id: int = USER_A_ID,
    settled_at: str | None = SEEDED_SETTLED_AT,
) -> None:
    """Raw-insert one settled `messages` row — the only entry corpus my-search reads (R11)."""
    with engine.begin() as connection:
        connection.execute(
            schema.messages.insert().values(
                id=message_id,
                user_id=user_id,
                session_id=session_id,
                role="user",
                kind=None,
                text=body,
                related_to=None,
                settled_at=settled_at,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_memo(
    engine: Engine,
    *,
    memo_id: int,
    scope: str,
    scope_id: int,
    body: str,
    user_id: int = USER_A_ID,
    is_enabled: bool = True,
    forced: bool = False,
) -> None:
    """Raw-insert one `memos` row; `scope_id` is the **stored** id (the user id at user level).

    The flag 029 must never read is named `forced` on this helper's own keyword, so the seeding
    says what it seeds while no assertion below ever expects that column on the wire.
    """
    with engine.begin() as connection:
        connection.execute(
            schema.memos.insert().values(
                id=memo_id,
                user_id=user_id,
                scope=scope,
                scope_id=scope_id,
                body=body,
                is_enabled=is_enabled,
                is_forced=forced,
                sort_key=0,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
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


def _build_search_tables(engine: Engine) -> None:
    """024's two helpers, after the rows: the FTS back-fill indexes what is already there."""
    with engine.begin() as connection:
        ensure_fts_tables(connection)
        ensure_vector_tables(connection, DIMENSION)


def _write_vectors(engine: Engine, *, memo_ids: tuple[int, ...], session_ids: tuple[int, ...]) -> None:
    """One vector per row, each `embedding_vector(TOKEN, 8)` — the fake's vector of the query, so
    every seeded row sits at distance zero and no absence can be a vector that missed."""
    with engine.begin() as connection:
        for memo_id in memo_ids:
            write_vector(connection, MEMO_VEC_TABLE, memo_id, embedding_vector(TOKEN, DIMENSION))
        for session_id in session_ids:
            write_vector(connection, SESSION_VEC_TABLE, session_id, embedding_vector(TOKEN, DIMENSION))


def _seed_owner_a(engine: Engine) -> None:
    """A's matching material in all five kinds, plus two non-matching rows the notes hang off.

    The setup-level note lives on `SETUP_A_SPARE`, which hangs off `CHAR_A_SPARE`, so that
    level's `scope_id` and `character_id` are two different ids and cannot be confused.
    """
    _insert_character(engine, character_id=CHAR_A, name=CHARACTER_NAME, sheet=PERSONA)
    _insert_character(engine, character_id=CHAR_A_ARCHIVED, name=ARCHIVED_CHARACTER_NAME, archived_at=TIMESTAMP)
    _insert_character(engine, character_id=CHAR_A_SPARE, name=SPARE_CHARACTER_NAME)
    _insert_setup(engine, setup_id=SETUP_A, character_id=CHAR_A, name=SETUP_NAME, description=SETUP_DESCRIPTION)
    _insert_setup(
        engine,
        setup_id=SETUP_A_ARCHIVED,
        character_id=CHAR_A,
        name=ARCHIVED_SETUP_NAME,
        archived_at=TIMESTAMP,
    )
    _insert_setup(engine, setup_id=SETUP_A_SPARE, character_id=CHAR_A_SPARE, name=SPARE_SETUP_NAME)
    _insert_session(engine, session_id=SESSION_WITH_SETUP, setup_id=SETUP_A, created_at=CREATED_WITH_SETUP)
    _insert_session(engine, session_id=SESSION_NO_SETUP, setup_id=None, created_at=CREATED_NO_SETUP)
    _insert_session(
        engine,
        session_id=SESSION_ARCHIVED,
        setup_id=SETUP_A,
        archived_at=TIMESTAMP,
        created_at=CREATED_ARCHIVED,
    )
    _insert_message(engine, message_id=ENTRY_SETTLED, session_id=SESSION_WITH_SETUP, body=SETTLED_TEXT)
    _insert_memo(engine, memo_id=MEMO_USER, scope="user", scope_id=USER_A_ID, body=_memo_body("aurelian"))
    _insert_memo(engine, memo_id=MEMO_CHARACTER, scope="character", scope_id=CHAR_A, body=_memo_body("bellringer"))
    _insert_memo(engine, memo_id=MEMO_SETUP, scope="setup", scope_id=SETUP_A_SPARE, body=_memo_body("cindermoor"))
    _insert_memo(
        engine,
        memo_id=MEMO_SESSION,
        scope="session",
        scope_id=SESSION_WITH_SETUP,
        body=_memo_body("dawnwarden"),
    )
    _insert_memo(
        engine,
        memo_id=MEMO_DISABLED,
        scope="character",
        scope_id=CHAR_A,
        body=_memo_body("emberlight"),
        is_enabled=False,
        forced=True,
    )


def _seed_owner_b(engine: Engine) -> None:
    """B's five twins: the same names, texts, bodies and (below) the same vectors as A's."""
    _insert_character(engine, character_id=CHAR_B, user_id=USER_B_ID, name=CHARACTER_NAME, sheet=PERSONA)
    _insert_setup(
        engine,
        setup_id=SETUP_B,
        user_id=USER_B_ID,
        character_id=CHAR_B,
        name=SETUP_NAME,
        description=SETUP_DESCRIPTION,
    )
    _insert_session(
        engine,
        session_id=SESSION_B,
        user_id=USER_B_ID,
        character_id=CHAR_B,
        setup_id=SETUP_B,
        created_at=CREATED_OTHER_OWNER,
    )
    _insert_message(engine, message_id=ENTRY_B, session_id=SESSION_B, body=SETTLED_TEXT, user_id=USER_B_ID)
    _insert_memo(
        engine,
        memo_id=MEMO_B,
        scope="user",
        scope_id=USER_B_ID,
        body=_memo_body("aurelian"),
        user_id=USER_B_ID,
    )


def _seed_everything(engine: Engine, *, other_owner: bool = False, dimension: int = DIMENSION) -> None:
    """A's five kinds (optionally B's twins), the designation, the index and the vectors."""
    _seed_owner_a(engine)
    if other_owner:
        _seed_owner_b(engine)
    _seed_designation(engine, dimension=dimension)
    _build_search_tables(engine)
    memo_ids = A_MEMO_IDS + ((MEMO_B,) if other_owner else ())
    session_ids = A_SESSION_IDS + ((SESSION_B,) if other_owner else ())
    _write_vectors(engine, memo_ids=memo_ids, session_ids=session_ids)


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the schema and the two roleplayers; each test seeds the rest."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A_ID, username=USER_A_NAME, password=USER_A_PASSWORD)
    _insert_user(db_engine, user_id=USER_B_ID, username=USER_B_NAME, password=USER_B_PASSWORD)
    return db_engine


@pytest.fixture
def embedding_factory() -> FakeClientFactory:
    """The provider the overridden shared dependency hands the route (024 D9)."""
    return fake_factory(DIMENSION)


@contextmanager
def _application_with(settings: Settings, factory: FakeClientFactory) -> Iterator[FastAPI]:
    """The real factory's application, pinned to the per-test database and to `factory`."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_llm_client_factory] = lambda: factory
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def application(
    db_settings: Settings, engine: Engine, embedding_factory: FakeClientFactory
) -> Iterator[FastAPI]:
    with _application_with(db_settings, embedding_factory) as app:
        yield app


# --- login helpers -----------------------------------------------------------------------------


def _parse_set_cookie(header: str) -> tuple[str, str]:
    first = header.split(";")[0]
    name, _, value = first.partition("=")
    return name.strip(), value.strip().strip('"')


def _login_token(application: FastAPI, settings: Settings, username: str, password: str) -> str:
    response = TestClient(application).post(LOGIN_PATH, json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    tokens = [
        value
        for name, value in (_parse_set_cookie(header) for header in response.headers.get_list("set-cookie"))
        if name == settings.session_cookie_name
    ]
    assert len(tokens) == 1
    assert tokens[0]
    return tokens[0]


def _as(application: FastAPI, settings: Settings, username: str, password: str) -> TestClient:
    """A fresh client carrying exactly this account's session cookie — never shared."""
    fresh = TestClient(application)
    fresh.cookies.set(settings.session_cookie_name, _login_token(application, settings, username, password))
    return fresh


def _anonymous(application: FastAPI) -> TestClient:
    return TestClient(application)


def _player_a(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, USER_A_NAME, USER_A_PASSWORD)


def _player_b(application: FastAPI, settings: Settings) -> TestClient:
    return _as(application, settings, USER_B_NAME, USER_B_PASSWORD)


# --- response helpers --------------------------------------------------------------------------


def _parsed(response: httpx.Response, status: int) -> dict[str, Any]:
    """The body parsed with `json.loads`, which preserves the object's key order (DoD-2)."""
    assert response.status_code == status, response.text
    body = json.loads(response.text)
    assert isinstance(body, dict)
    return body


def _search(client: TestClient, query: str = TOKEN) -> dict[str, Any]:
    return _parsed(client.get(SEARCH_PATH, params={"q": query}), 200)


def _rows_by_id(body: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    group = body[key]
    assert isinstance(group, list)
    rows = {row["id"]: row for row in group}
    assert len(rows) == len(group), f"{key} holds the same id twice"
    return rows


def _without_snippet(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "snippet"}


def _assert_envelope(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    """The standard envelope: one `error` key holding exactly `code`, `message` and `detail`."""
    body = _parsed(response, status)
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert set(error) == ENVELOPE_KEYS
    assert error["code"] == code
    return error


def _id_strings(value: Any) -> set[str]:
    """Every decimal-string leaf anywhere in the body — the ids it names, whatever the nesting."""
    if isinstance(value, dict):
        return {found for item in value.values() for found in _id_strings(item)}
    if isinstance(value, list):
        return {found for item in value for found in _id_strings(item)}
    if isinstance(value, str) and value.isdigit():
        return {value}
    return set()


# --- DoD-1: no session cookie, no search (wire contract: 401) ---------------------------------


@pytest.mark.parametrize("path", [f"{SEARCH_PATH}?q=x", SEARCH_PATH], ids=["with-query", "bare"])
def test_the_route_answers_401_without_a_session_cookie__S029_003_DoD1(
    application: FastAPI, path: str
) -> None:
    """DoD-1 — `require_user` sits on the router, so an anonymous call never searches: 401 with
    the standard envelope and no group on the wire."""
    body = _parsed(_anonymous(application).get(path), 401)

    assert set(body) == {"error"}
    assert set(body["error"]) == ENVELOPE_KEYS
    assert body["error"]["code"] == NOT_AUTHENTICATED
    assert all(key not in body for key in GROUP_KEYS)


# --- DoD-2: five groups, in order, every id a decimal string ----------------------------------


def test_the_five_groups_arrive_in_uc059_order__S029_003_DoD2(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-2 — US-075.AC-1: the 200 body's top-level keys are exactly `characters`, `setups`,
    `sessions`, `entries`, `memos`, in that order, and the one query reaches all five
    (US-074.AC-1)."""
    _seed_everything(engine)

    body = _search(_player_a(application, db_settings))

    assert list(body) == GROUP_KEYS
    for key in GROUP_KEYS:
        assert body[key], f"{key} is empty although A owns a match of that kind"


def test_each_group_holds_exactly_the_seeded_rows__S029_003_DoD2(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-2 — each group holds its seeded hit, field for field as the wire contract declares
    it; the snippet is compared by the token it must contain."""
    _seed_everything(engine)

    body = _search(_player_a(application, db_settings))

    for key, expected in EXPECTED_GROUPS.items():
        rows = _rows_by_id(body, key)
        assert set(rows) == set(expected)
        for row_id, row in rows.items():
            assert _without_snippet(row) == expected[row_id]
        if key in SNIPPET_GROUPS:
            for row in rows.values():
                assert TOKEN in row["snippet"].lower()


def test_every_id_on_the_wire_is_the_decimal_string_of_its_snowflake__S029_003_DoD2(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-2 — ids are JSON **strings** (`SnowflakeOut`), never numbers: every `id`,
    `character_id`, `session_id` and `scope_id` is the decimal of a seeded snowflake above
    2**60, where a float round-trip would be visible."""
    _seed_everything(engine)

    body = _search(_player_a(application, db_settings))

    seen = 0
    for key in GROUP_KEYS:
        for row in body[key]:
            for field in ID_FIELDS:
                if field not in row or row[field] is None:
                    continue
                value = row[field]
                assert isinstance(value, str), f"{key}.{field} is not a string"
                assert value.isdigit()
                assert int(value) > SNOWFLAKE_FLOOR
                assert int(value) in A_WIRE_IDS
                seen += 1
    assert seen > 0


# --- DoD-3: the exact field shapes (wire contract, US-119) ------------------------------------


def test_each_hit_carries_exactly_its_contract_keys__S029_003_DoD3(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-3 — one key set per kind, with no extra key anywhere."""
    _seed_everything(engine)

    body = _search(_player_a(application, db_settings))

    for key in GROUP_KEYS:
        for row in body[key]:
            assert set(row) == HIT_KEYS[key], f"{key} hit carries the wrong keys"


def test_no_hit_carries_a_title_a_body_or_the_forced_flag__S029_003_DoD3(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-3 — US-119: no `title`, no `body` and no `is_forced` key in any of the five groups."""
    _seed_everything(engine)

    body = _search(_player_a(application, db_settings))

    for key in GROUP_KEYS:
        for row in body[key]:
            for forbidden in FORBIDDEN_HIT_KEYS:
                assert forbidden not in row, f"{key} hit carries {forbidden}"


# --- DoD-4: a note's state is reported, never a filter (US-137.AC-1, US-137.AC-2) -------------


def test_a_disabled_note_is_returned_beside_an_enabled_one__S029_003_DoD4(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-4 — the disabled note is on the wire with `is_enabled` false, the enabled one with
    true: the state is reported, not applied."""
    _seed_everything(engine)

    rows = _rows_by_id(_search(_player_a(application, db_settings)), "memos")

    assert str(MEMO_DISABLED) in rows
    assert str(MEMO_CHARACTER) in rows
    assert rows[str(MEMO_DISABLED)]["is_enabled"] is False
    assert rows[str(MEMO_CHARACTER)]["is_enabled"] is True


def test_a_user_level_note_reports_a_null_scope_id__S029_003_DoD4(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-4 — the stored `scope_id` of a user-level note is the owner's own id; the wire
    contract says the client sees `scope` `"user"` and `scope_id` **null**."""
    _seed_everything(engine)

    rows = _rows_by_id(_search(_player_a(application, db_settings)), "memos")

    assert rows[str(MEMO_USER)]["scope"] == "user"
    assert rows[str(MEMO_USER)]["scope_id"] is None
    assert rows[str(MEMO_USER)]["character_id"] is None
    assert str(USER_A_ID) not in _id_strings(rows[str(MEMO_USER)])


# --- DoD-5: owner isolation, tested as an absence (US-076.AC-1, UC-065, R5) -------------------


def test_signed_in_as_a_no_id_of_bs_appears_anywhere__S029_003_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 — B's twins match on every arm (same names, same texts, same vectors). A's body
    names A's rows and not one of B's ids, anywhere in it."""
    _seed_everything(engine, other_owner=True)

    body = _search(_player_a(application, db_settings))

    found = _id_strings(body)
    assert found & {str(row_id) for row_id in B_WIRE_IDS} == set()
    assert {str(CHAR_A), str(SETUP_A), str(SESSION_WITH_SETUP), str(ENTRY_SETTLED), str(MEMO_USER)} <= found


def test_signed_in_as_b_no_id_of_as_appears_anywhere__S029_003_DoD5(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-5 — the same the other way round: B sees B's own five rows and nothing of A's."""
    _seed_everything(engine, other_owner=True)

    body = _search(_player_b(application, db_settings))

    found = _id_strings(body)
    assert found & {str(row_id) for row_id in A_WIRE_IDS} == set()
    for key, expected_ids in EXPECTED_B_IDS.items():
        assert set(_rows_by_id(body, key)) == expected_ids


# --- DoD-6: archived rows are returned and marked (U3) ----------------------------------------


def test_an_archived_character_setup_and_session_are_flagged_on_the_wire__S029_003_DoD6(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-6 — U3: the archived row of each archivable kind is returned with `archived` true,
    and the live rows beside it with `archived` false."""
    _seed_everything(engine)

    body = _search(_player_a(application, db_settings))

    characters = _rows_by_id(body, "characters")
    setups = _rows_by_id(body, "setups")
    sessions = _rows_by_id(body, "sessions")

    assert characters[str(CHAR_A_ARCHIVED)]["archived"] is True
    assert characters[str(CHAR_A)]["archived"] is False
    assert setups[str(SETUP_A_ARCHIVED)]["archived"] is True
    assert setups[str(SETUP_A)]["archived"] is False
    assert sessions[str(SESSION_ARCHIVED)]["archived"] is True
    assert sessions[str(SESSION_WITH_SETUP)]["archived"] is False


# --- DoD-7: a blank query answers five empty groups and opens no model (D1) -------------------


@pytest.mark.parametrize(
    "path",
    [SEARCH_PATH, f"{SEARCH_PATH}?q=", f"{SEARCH_PATH}?q=%20%20"],
    ids=["absent", "empty", "whitespace"],
)
def test_a_blank_query_answers_five_empty_groups_and_opens_no_model__S029_003_DoD7(
    application: FastAPI,
    db_settings: Settings,
    engine: Engine,
    embedding_factory: FakeClientFactory,
    path: str,
) -> None:
    """DoD-7 — D1: absent, empty and whitespace-only `q` are all the blank query. 200, the five
    keys present and every list empty — although the database holds a match of every kind — and
    the overridden fake factory records **zero** constructions, so no model was opened."""
    _seed_everything(engine)
    client = _player_a(application, db_settings)

    body = _parsed(client.get(path), 200)

    assert list(body) == GROUP_KEYS
    for key in GROUP_KEYS:
        assert body[key] == []
    assert embedding_factory.call_count == 0
    assert embedding_factory.embed_calls == []


# --- DoD-8: an embedding failure fails the whole request (U1) ---------------------------------


def test_no_designated_model_fails_the_request_with_409__S029_003_DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-8 — U1: with the vector tables present but nothing designated, the request answers
    409 `no_embedding_model` and the body carries no group at all — not even the character name
    match sitting right there."""
    _seed_owner_a(engine)
    _build_search_tables(engine)
    client = _player_a(application, db_settings)

    response = client.get(SEARCH_PATH, params={"q": TOKEN})

    _assert_envelope(response, 409, NO_EMBEDDING_MODEL)
    assert all(key not in json.loads(response.text) for key in GROUP_KEYS)


def test_a_vector_dimension_mismatch_fails_the_request_with_409__S029_003_DoD8(
    application: FastAPI, db_settings: Settings, engine: Engine
) -> None:
    """DoD-8 — U1: the vector tables are at dimension 8 and the designated model declares 16, so
    the envelope's `detail` is exactly `{"reason": "dimension_mismatch"}`, unchanged."""
    _seed_everything(engine, dimension=MISMATCHED_DIMENSION)
    client = _player_a(application, db_settings)

    error = _assert_envelope(client.get(SEARCH_PATH, params={"q": TOKEN}), 409, NO_EMBEDDING_MODEL)

    assert error["detail"] == {"reason": "dimension_mismatch"}


def test_an_unreachable_provider_fails_the_request_with_502__S029_003_DoD8(
    db_settings: Settings, engine: Engine
) -> None:
    """DoD-8 — U1: the scripted fake raises `LlmUnreachableError` from `embed`, and the request
    answers 502 `llm_unreachable` with no group on the wire."""
    _seed_everything(engine)

    with _application_with(db_settings, unreachable_factory(DIMENSION)) as app:
        response = _player_a(app, db_settings).get(SEARCH_PATH, params={"q": TOKEN})

        _assert_envelope(response, 502, LLM_UNREACHABLE)
        assert all(key not in json.loads(response.text) for key in GROUP_KEYS)


# --- DoD-9: the route is mounted exactly once (D1) --------------------------------------------


def _api_routes(routes: Any, found: list[APIRoute], seen: set[int]) -> None:
    """Depth-first, registration-order walk of every `APIRoute`, descending into included-router
    wrappers (entries exposing `.routes`, `.router.routes` or `.original_router.routes`) whatever
    the framework's top-level layout — a flat scan of `app.routes` finds none."""
    if routes is None or id(routes) in seen:
        return
    seen.add(id(routes))
    for route in routes:
        if isinstance(route, APIRoute):
            if id(route) not in seen:
                seen.add(id(route))
                found.append(route)
            continue
        _api_routes(getattr(route, "routes", None), found, seen)
        _api_routes(getattr(getattr(route, "router", None), "routes", None), found, seen)
        _api_routes(getattr(getattr(route, "original_router", None), "routes", None), found, seen)


def test_the_route_table_holds_get_api_search_exactly_once__S029_003_DoD9(application: FastAPI) -> None:
    """DoD-9 — D1: one route, mounted once, answering `GET`. Read through the house walk, which
    descends into the included-router wrappers, and cross-checked against the OpenAPI paths."""
    found: list[APIRoute] = []
    _api_routes(application.routes, found, set())
    assert found, "the walk found no API routes at all"

    matching = [route for route in found if route.path == SEARCH_PATH]
    assert len(matching) == 1
    assert {method.upper() for method in matching[0].methods} == {"GET"}

    operations = application.openapi()["paths"][SEARCH_PATH]
    assert set(operations) == {"get"}
