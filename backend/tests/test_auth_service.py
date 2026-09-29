"""Tests for ``app.services.auth`` — the uniform refusal and the session lifecycle.

Every expected value comes from ``docs/plans/004.authentication-session/001.auth-sessions-and-service.md``
(Interface intent + Definition of done), ``001.context.md`` and the feature ``context.md``
(D1 the uniform refusal, D4 absolute expiry, D5 token and digest, D7 what resolution
requires, D9 idempotent revocation, D13 no normalization). Bindings come from
``## Skeleton`` → ``Step 001`` in ``status.md``.

Covers step 001 DoD-4 .. DoD-12. DoD-1/2 live in ``test_db_schema.py``, DoD-3 in
``test_errors.py``; DoD-13..15 are ``[manual/live]``.

Connection hygiene: the two writing operations open their own ``with conn.begin():``
block, so every operation here is called on a *fresh* connection, every setup write is
committed, and every post-condition is read on another fresh connection.
"""

import ast
import inspect
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, Table, func, select, update

from app.db import schema
from app.errors import InvalidCredentialsError
from app.ids import NODE_ID_BITS, SEQUENCE_BITS, SnowflakeGenerator
from app.roles import Role
from app.services import auth as auth_module
from app.services.auth import (
    AuthenticatedUser,
    OpenedSession,
    authenticate,
    open_session,
    resolve_session,
    revoke_session,
    revoke_user_sessions,
)
from app.services.passwords import hash_password

TIMESTAMP = "2026-01-01T00:00:00+00:00"

ADMIN_ID = 7_000_001
ADMIN_NAME = "founder"
ADMIN_PASSWORD = "correct horse battery staple"

PLAYER_ID = 7_000_002
PLAYER_NAME = "wanderer"
PLAYER_PASSWORD = "a quiet river at dusk"

DISABLED_ID = 7_000_003
DISABLED_NAME = "sleeper"
DISABLED_PASSWORD = "dormant but correct"

TTL_HOURS = 720


class _FixedIdGenerator:
    """A generator stand-in whose ``next_id()`` always answers one known value."""

    def __init__(self, value: int) -> None:
        self.value = value
        self.calls = 0

    def next_id(self) -> int:
        self.calls += 1
        return self.value


def _sessions() -> Table:
    return schema.metadata.tables["auth_sessions"]


def _users() -> Table:
    return schema.metadata.tables["users"]


# --- setup helpers (all committed, never left with an open transaction) --------------


def _insert_user(
    engine: Engine,
    *,
    user_id: int,
    username: str,
    password: str,
    role: Role,
    enabled: bool = True,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            _users().insert().values(
                id=user_id,
                username=username,
                password_hash=hash_password(password),
                role=role,
                is_enabled=enabled,
                rp_language=None,
                preferred_language=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the registry applied and three accounts seeded."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=ADMIN_ID, username=ADMIN_NAME, password=ADMIN_PASSWORD, role=Role.ADMIN)
    _insert_user(
        db_engine, user_id=PLAYER_ID, username=PLAYER_NAME, password=PLAYER_PASSWORD, role=Role.ROLEPLAYER
    )
    _insert_user(
        db_engine,
        user_id=DISABLED_ID,
        username=DISABLED_NAME,
        password=DISABLED_PASSWORD,
        role=Role.ROLEPLAYER,
        enabled=False,
    )
    return db_engine


def _authenticate(engine: Engine, username: str, password: str) -> AuthenticatedUser:
    with engine.connect() as connection:
        return authenticate(connection, username, password)


def _open(engine: Engine, user_id: int, generator: Any = None, ttl_hours: int = TTL_HOURS) -> OpenedSession:
    gen = generator if generator is not None else SnowflakeGenerator(node_id=1)
    with engine.connect() as connection:
        return open_session(connection, gen, user_id, ttl_hours)


def _resolve(engine: Engine, token: str) -> AuthenticatedUser | None:
    with engine.connect() as connection:
        return resolve_session(connection, token)


def _revoke(engine: Engine, token: str) -> None:
    with engine.connect() as connection:
        revoke_session(connection, token)


def _session_rows(engine: Engine) -> list[dict[str, Any]]:
    query = select(_sessions()).order_by(_sessions().c.id)
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(query).mappings()]


def _session_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(_sessions())).scalar_one())


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _row_for_user(engine: Engine, user_id: int) -> dict[str, Any]:
    rows = [row for row in _session_rows(engine) if row["user_id"] == user_id]
    assert len(rows) == 1
    return rows[0]


def _pushed_to_the_past(stored: str) -> str:
    """The same stored timestamp text, moved back decades by rewriting only the year.

    Every ISO-8601 value starts with its four-digit year, so this keeps the module's own
    fixed-width format intact while placing the instant firmly in the past.
    """
    return "2000" + stored[4:]


def _update_session_row(engine: Engine, row_id: int, **values: Any) -> None:
    with engine.begin() as connection:
        connection.execute(update(_sessions()).where(_sessions().c.id == row_id).values(**values))


def _expire_row(engine: Engine, row: dict[str, Any]) -> None:
    """Move a session row's creation and expiry into the past, in the module's own format."""
    _update_session_row(
        engine,
        row["id"],
        created_at=_pushed_to_the_past(row["created_at"]),
        expires_at=_pushed_to_the_past(row["expires_at"]),
    )


# --- DoD-4: correct credentials for an enabled account return the identity ----------


@pytest.mark.parametrize(
    ("user_id", "username", "password", "role"),
    [
        (ADMIN_ID, ADMIN_NAME, ADMIN_PASSWORD, Role.ADMIN),
        (PLAYER_ID, PLAYER_NAME, PLAYER_PASSWORD, Role.ROLEPLAYER),
    ],
)
def test_correct_credentials_return_id_username_and_role__DoD4(
    engine: Engine, user_id: int, username: str, password: str, role: Role
) -> None:
    """DoD-4 — an enabled account with the right password yields its id, username and role (US-004.AC-1)."""
    result = _authenticate(engine, username, password)
    assert isinstance(result, AuthenticatedUser)
    assert result.id == user_id
    assert result.username == username
    assert result.role == role
    assert isinstance(result.role, Role)


def test_authentication_writes_nothing__DoD4(engine: Engine) -> None:
    """DoD-4 — authenticating only reads: no session row appears as a side effect."""
    _authenticate(engine, ADMIN_NAME, ADMIN_PASSWORD)
    assert _session_count(engine) == 0


# --- DoD-5: the three failures raise one indistinguishable refusal -------------------


def _refusal(engine: Engine, username: str, password: str) -> InvalidCredentialsError:
    with pytest.raises(InvalidCredentialsError) as excinfo:
        _authenticate(engine, username, password)
    return excinfo.value


def test_unknown_username_is_refused__DoD5(engine: Engine) -> None:
    """DoD-5 — no such user: ``invalid_credentials`` (US-005.AC-1)."""
    error = _refusal(engine, "nobody-by-this-name", ADMIN_PASSWORD)
    assert error.code == "invalid_credentials"
    assert error.http_status == 400


def test_wrong_password_on_existing_account_is_refused__DoD5(engine: Engine) -> None:
    """DoD-5 — right user, wrong password: ``invalid_credentials`` (US-005.AC-1)."""
    error = _refusal(engine, ADMIN_NAME, "definitely not the password")
    assert error.code == "invalid_credentials"
    assert error.http_status == 400


def test_correct_password_on_disabled_account_is_refused__DoD5(engine: Engine) -> None:
    """DoD-5 — the right password for a disabled account is still refused (US-006.AC-1)."""
    error = _refusal(engine, DISABLED_NAME, DISABLED_PASSWORD)
    assert error.code == "invalid_credentials"
    assert error.http_status == 400


def test_three_refusals_are_indistinguishable__DoD5(engine: Engine) -> None:
    """DoD-5 — unknown user, wrong password and disabled account carry the same code, status,
    message and detail, and render identically (context.md D1)."""
    refusals = [
        _refusal(engine, "nobody-by-this-name", ADMIN_PASSWORD),
        _refusal(engine, ADMIN_NAME, "definitely not the password"),
        _refusal(engine, DISABLED_NAME, DISABLED_PASSWORD),
    ]
    assert {type(error) for error in refusals} == {InvalidCredentialsError}
    assert {error.code for error in refusals} == {"invalid_credentials"}
    assert {error.http_status for error in refusals} == {400}
    assert len({error.message for error in refusals}) == 1
    assert all(error.detail == {} for error in refusals)
    wires = [error.to_wire() for error in refusals]
    assert wires[0] == wires[1] == wires[2]
    assert len({str(error) for error in refusals}) == 1


def test_refusal_does_not_echo_the_attempted_username__DoD5(engine: Engine) -> None:
    """DoD-5 — nothing in the refusal reveals which account was tried."""
    for username, password in (
        ("nobody-by-this-name", ADMIN_PASSWORD),
        (ADMIN_NAME, "definitely not the password"),
        (DISABLED_NAME, DISABLED_PASSWORD),
    ):
        rendered = str(_refusal(engine, username, password).to_wire())
        assert username not in rendered
        assert password not in rendered


@pytest.mark.parametrize("variant", ["Founder", "FOUNDER", " founder", "founder ", "founder\n"])
def test_username_must_match_exactly__DoD5(engine: Engine, variant: str) -> None:
    """DoD-5 — lookup is by exact username (D13): a case or whitespace variant is an unknown user."""
    with pytest.raises(InvalidCredentialsError):
        _authenticate(engine, variant, ADMIN_PASSWORD)


def test_password_is_compared_as_received__DoD5(engine: Engine) -> None:
    """DoD-5 — no password normalization (D13): a padded correct password is a wrong password."""
    with pytest.raises(InvalidCredentialsError):
        _authenticate(engine, ADMIN_NAME, f" {ADMIN_PASSWORD} ")


# --- DoD-6: opening a session inserts one row holding the digest ---------------------


def test_open_session_inserts_exactly_one_row_for_that_user__DoD6(engine: Engine) -> None:
    """DoD-6 — one new `auth_sessions` row, owned by the user it was opened for, not revoked."""
    assert _session_count(engine) == 0
    _open(engine, PLAYER_ID)
    rows = _session_rows(engine)
    assert len(rows) == 1
    assert rows[0]["user_id"] == PLAYER_ID
    assert rows[0]["revoked_at"] is None


def test_open_session_expiry_is_creation_plus_ttl__DoD6(engine: Engine) -> None:
    """DoD-6 — the stored `expires_at` is the stored `created_at` plus the TTL given."""
    before = datetime.now(UTC)
    _open(engine, PLAYER_ID, ttl_hours=5)
    after = datetime.now(UTC)
    row = _row_for_user(engine, PLAYER_ID)
    created = _parse_utc(row["created_at"])
    expires = _parse_utc(row["expires_at"])
    assert expires - created == timedelta(hours=5)
    assert before - timedelta(seconds=1) <= created <= after + timedelta(seconds=1)


def test_open_session_uses_the_ttl_it_is_given__DoD6(engine: Engine) -> None:
    """DoD-6 — two different TTLs produce two different lifetimes; nothing reads a setting instead."""
    _open(engine, ADMIN_ID, ttl_hours=1)
    _open(engine, PLAYER_ID, ttl_hours=48)
    admin_row = _row_for_user(engine, ADMIN_ID)
    player_row = _row_for_user(engine, PLAYER_ID)
    assert _parse_utc(admin_row["expires_at"]) - _parse_utc(admin_row["created_at"]) == timedelta(hours=1)
    assert _parse_utc(player_row["expires_at"]) - _parse_utc(player_row["created_at"]) == timedelta(hours=48)


def test_returned_expiry_is_the_stored_expiry_as_an_aware_utc_instant__DoD6(engine: Engine) -> None:
    """DoD-6 — the returned expiry instant is the row's `expires_at`, timezone-aware UTC."""
    opened = _open(engine, PLAYER_ID, ttl_hours=TTL_HOURS)
    assert isinstance(opened, OpenedSession)
    assert isinstance(opened.expires_at, datetime)
    assert opened.expires_at.tzinfo is not None
    assert opened.expires_at.utcoffset() == timedelta(0)
    stored = _parse_utc(_row_for_user(engine, PLAYER_ID)["expires_at"])
    assert abs(opened.expires_at - stored) < timedelta(seconds=1)
    assert abs(opened.expires_at - (datetime.now(UTC) + timedelta(hours=TTL_HOURS))) < timedelta(minutes=1)


def test_stored_token_hash_is_not_the_returned_token__DoD6(engine: Engine) -> None:
    """DoD-6 — the row stores a digest; the plaintext token is stored nowhere in it (D5)."""
    opened = _open(engine, PLAYER_ID)
    row = _row_for_user(engine, PLAYER_ID)
    assert isinstance(row["token_hash"], str)
    assert row["token_hash"] != ""
    assert row["token_hash"] != opened.token
    for value in row.values():
        assert opened.token not in str(value)


def test_returned_token_is_high_entropy__DoD6(engine: Engine) -> None:
    """DoD-6 — the token is a long random string (D5: 32 bytes of entropy)."""
    opened = _open(engine, PLAYER_ID)
    assert isinstance(opened.token, str)
    assert len(opened.token) >= 32
    assert len(set(opened.token)) >= 10


def test_successive_sessions_return_different_tokens__DoD6(engine: Engine) -> None:
    """DoD-6 — two calls return two different tokens and store two different digests."""
    first = _open(engine, PLAYER_ID)
    second = _open(engine, PLAYER_ID)
    assert first.token != second.token
    rows = _session_rows(engine)
    assert len(rows) == 2
    assert rows[0]["token_hash"] != rows[1]["token_hash"]


# --- DoD-7: the row id comes from the generator passed in ----------------------------


def test_row_id_comes_from_the_given_generator__DoD7(engine: Engine) -> None:
    """DoD-7 — two calls with two generators produce exactly those generators' ids."""
    first_generator = _FixedIdGenerator(4_242_424_242)
    second_generator = _FixedIdGenerator(9_191_919_191)
    _open(engine, ADMIN_ID, generator=first_generator)
    _open(engine, PLAYER_ID, generator=second_generator)
    assert first_generator.calls >= 1
    assert second_generator.calls >= 1
    assert _row_for_user(engine, ADMIN_ID)["id"] == 4_242_424_242
    assert _row_for_user(engine, PLAYER_ID)["id"] == 9_191_919_191


def test_row_id_carries_the_given_real_generators_node__DoD7(engine: Engine) -> None:
    """DoD-7 — with real snowflake generators on two nodes, each row carries its generator's node id."""
    node_mask = (1 << NODE_ID_BITS) - 1
    _open(engine, ADMIN_ID, generator=SnowflakeGenerator(node_id=5))
    _open(engine, PLAYER_ID, generator=SnowflakeGenerator(node_id=9))
    admin_id = _row_for_user(engine, ADMIN_ID)["id"]
    player_id = _row_for_user(engine, PLAYER_ID)["id"]
    assert (admin_id >> SEQUENCE_BITS) & node_mask == 5
    assert (player_id >> SEQUENCE_BITS) & node_mask == 9


def _module_tree() -> ast.Module:
    return ast.parse(inspect.getsource(auth_module))


def test_module_reaches_no_process_wide_generator__DoD7() -> None:
    """DoD-7 — nothing in the module builds, holds or fetches a generator of its own."""
    held = [name for name, value in vars(auth_module).items() if isinstance(value, SnowflakeGenerator)]
    assert held == []
    offenders: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Call):
            callee = node.func
            name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", "")
            if name in {"SnowflakeGenerator", "build_id_generator"}:
                offenders.append(name)
        elif isinstance(node, ast.Attribute) and node.attr in {"id_generator", "state"}:
            offenders.append(node.attr)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            offenders.extend(alias.name for alias in node.names if alias.name == "build_id_generator")
    assert offenders == []


# --- DoD-8: a fresh session's token resolves to its user -----------------------------


@pytest.mark.parametrize(
    ("user_id", "username", "role"),
    [(ADMIN_ID, ADMIN_NAME, Role.ADMIN), (PLAYER_ID, PLAYER_NAME, Role.ROLEPLAYER)],
)
def test_fresh_token_resolves_to_its_user__DoD8(engine: Engine, user_id: int, username: str, role: Role) -> None:
    """DoD-8 — resolving the returned token yields the user's id, username and role (US-004.AC-1)."""
    opened = _open(engine, user_id)
    resolved = _resolve(engine, opened.token)
    assert isinstance(resolved, AuthenticatedUser)
    assert resolved.id == user_id
    assert resolved.username == username
    assert resolved.role == role


def test_resolving_does_not_move_the_expiry__DoD8(engine: Engine) -> None:
    """DoD-8 — a resolve is a read: the row is unchanged after it (D4, no sliding)."""
    opened = _open(engine, PLAYER_ID)
    before = _row_for_user(engine, PLAYER_ID)
    assert _resolve(engine, opened.token) is not None
    assert _resolve(engine, opened.token) is not None
    assert _row_for_user(engine, PLAYER_ID) == before


# --- DoD-9: resolution yields nothing for dead tokens, and never raises --------------


def test_never_issued_token_resolves_to_nothing__DoD9(engine: Engine) -> None:
    """DoD-9 — an unknown token yields None, not an error."""
    _open(engine, PLAYER_ID)
    assert _resolve(engine, "this-token-was-never-issued-by-anyone-at-all-0000") is None
    assert _resolve(engine, "") is None


def test_revoked_row_resolves_to_nothing__DoD9(engine: Engine) -> None:
    """DoD-9 — a row whose `revoked_at` is set yields None (US-007.AC-2)."""
    opened = _open(engine, PLAYER_ID)
    row = _row_for_user(engine, PLAYER_ID)
    _update_session_row(engine, row["id"], revoked_at=row["created_at"])
    assert _resolve(engine, opened.token) is None


def test_token_revoked_through_the_service_resolves_to_nothing__DoD9(engine: Engine) -> None:
    """DoD-9 — after the revoke operation, the same token yields None."""
    opened = _open(engine, PLAYER_ID)
    _revoke(engine, opened.token)
    assert _resolve(engine, opened.token) is None


def test_expired_row_resolves_to_nothing__DoD9(engine: Engine) -> None:
    """DoD-9 — a row past `expires_at` yields None (US-007.AC-2)."""
    opened = _open(engine, PLAYER_ID)
    _expire_row(engine, _row_for_user(engine, PLAYER_ID))
    assert _resolve(engine, opened.token) is None


def test_session_of_a_since_disabled_user_resolves_to_nothing__DoD9(engine: Engine) -> None:
    """DoD-9 — disabling the user after login makes the same token yield None (US-006.AC-1)."""
    opened = _open(engine, PLAYER_ID)
    assert _resolve(engine, opened.token) is not None
    with engine.begin() as connection:
        connection.execute(update(_users()).where(_users().c.id == PLAYER_ID).values(is_enabled=False))
    assert _resolve(engine, opened.token) is None


def test_dead_tokens_leave_other_live_sessions_resolvable__DoD9(engine: Engine) -> None:
    """DoD-9 — a revoked session of one user does not stop another user's live token."""
    dead = _open(engine, ADMIN_ID)
    live = _open(engine, PLAYER_ID)
    _revoke(engine, dead.token)
    assert _resolve(engine, dead.token) is None
    resolved = _resolve(engine, live.token)
    assert resolved is not None
    assert resolved.id == PLAYER_ID


# --- DoD-10: the role is read live ---------------------------------------------------


def test_role_change_is_seen_by_the_same_token__DoD10(engine: Engine) -> None:
    """DoD-10 — changing `users.role` changes what the same token resolves to (D7)."""
    opened = _open(engine, PLAYER_ID)
    first = _resolve(engine, opened.token)
    assert first is not None
    assert first.role == Role.ROLEPLAYER

    with engine.begin() as connection:
        connection.execute(update(_users()).where(_users().c.id == PLAYER_ID).values(role=Role.ADMIN))
    promoted = _resolve(engine, opened.token)
    assert promoted is not None
    assert promoted.role == Role.ADMIN
    assert promoted.id == PLAYER_ID

    with engine.begin() as connection:
        connection.execute(update(_users()).where(_users().c.id == PLAYER_ID).values(role=Role.ROLEPLAYER))
    demoted = _resolve(engine, opened.token)
    assert demoted is not None
    assert demoted.role == Role.ROLEPLAYER
    assert _session_count(engine) == 1


# --- DoD-11: revocation marks, deletes nothing, and is idempotent --------------------


def test_revoke_sets_revoked_at_and_deletes_nothing__DoD11(engine: Engine) -> None:
    """DoD-11 — the matching row gains a `revoked_at`; the row is still there (US-007.AC-1)."""
    opened = _open(engine, PLAYER_ID)
    before = _row_for_user(engine, PLAYER_ID)
    _revoke(engine, opened.token)
    after = _row_for_user(engine, PLAYER_ID)
    assert after["revoked_at"] is not None
    assert after["id"] == before["id"]
    assert after["token_hash"] == before["token_hash"]
    assert after["expires_at"] == before["expires_at"]
    assert _session_count(engine) == 1


def test_revoke_leaves_the_users_other_sessions_untouched__DoD11(engine: Engine) -> None:
    """DoD-11 — only the matching row is revoked; the same user's other session stays live."""
    first = _open(engine, PLAYER_ID)
    second = _open(engine, PLAYER_ID)
    other_user = _open(engine, ADMIN_ID)
    _revoke(engine, first.token)

    rows = _session_rows(engine)
    assert len(rows) == 3
    revoked = [row for row in rows if row["revoked_at"] is not None]
    assert len(revoked) == 1
    assert revoked[0]["user_id"] == PLAYER_ID

    still_live = _resolve(engine, second.token)
    assert still_live is not None
    assert still_live.id == PLAYER_ID
    assert _resolve(engine, other_user.token) is not None


def test_revoking_an_unknown_token_is_a_no_op__DoD11(engine: Engine) -> None:
    """DoD-11 — an unknown token revokes nothing and raises nothing (D9)."""
    opened = _open(engine, PLAYER_ID)
    before = _session_rows(engine)
    _revoke(engine, "this-token-was-never-issued-by-anyone-at-all-0000")
    assert _session_rows(engine) == before
    assert _resolve(engine, opened.token) is not None


def test_revoking_an_already_revoked_token_is_a_no_op__DoD11(engine: Engine) -> None:
    """DoD-11 — revoking twice succeeds; the row stays revoked and nothing is deleted (D9)."""
    opened = _open(engine, PLAYER_ID)
    _revoke(engine, opened.token)
    first = _row_for_user(engine, PLAYER_ID)
    _revoke(engine, opened.token)
    second = _row_for_user(engine, PLAYER_ID)
    assert second["revoked_at"] is not None
    assert second["revoked_at"] == first["revoked_at"]
    assert _session_count(engine) == 1


def test_revoking_an_expired_token_succeeds_and_deletes_nothing__DoD11(engine: Engine) -> None:
    """DoD-11 — an expired row is an ordinary success: no raise, row still present (D9)."""
    opened = _open(engine, PLAYER_ID)
    _expire_row(engine, _row_for_user(engine, PLAYER_ID))
    _revoke(engine, opened.token)
    assert _session_count(engine) == 1
    assert _resolve(engine, opened.token) is None


def test_revoke_returns_nothing__DoD11(engine: Engine) -> None:
    """DoD-11 — revocation is a plain command; its result is None."""
    opened = _open(engine, PLAYER_ID)
    with engine.connect() as connection:
        assert revoke_session(connection, opened.token) is None


# --- DoD-12: no fastapi, no status codes, no Request, no settings --------------------


def _imported_modules() -> list[str]:
    imported: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    return imported


def test_module_imports_no_fastapi_or_starlette__DoD12() -> None:
    """DoD-12 — no `fastapi` (or its `starlette` base) import anywhere in the module."""
    offenders = [name for name in _imported_modules() if name.split(".")[0] in {"fastapi", "starlette"}]
    assert offenders == []


def test_module_binds_no_fastapi_symbol__DoD12() -> None:
    """DoD-12 — no module-level name is a fastapi/starlette object."""
    offenders = []
    for name, value in vars(auth_module).items():
        origin = getattr(value, "__module__", None) or getattr(value, "__name__", "")
        if isinstance(origin, str) and origin.split(".")[0] in {"fastapi", "starlette"}:
            offenders.append(name)
    assert offenders == []


HTTP_STATUS_LITERALS = {200, 201, 204, 400, 401, 403, 404, 409, 422, 500}


def test_module_references_no_http_status_code__DoD12() -> None:
    """DoD-12 — no HTTP status literal and no status-code name appears in the module."""
    status_words = {"HTTPStatus", "HTTPException", "status_code", "http_status"}
    literal_statuses: list[int] = []
    status_names: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Constant) and type(node.value) is int and node.value in HTTP_STATUS_LITERALS:
            literal_statuses.append(node.value)
        elif isinstance(node, ast.Name) and (node.id in status_words or node.id.startswith("HTTP_")):
            status_names.append(node.id)
        elif isinstance(node, ast.Attribute) and (node.attr in status_words or node.attr.startswith("HTTP_")):
            status_names.append(node.attr)
    assert literal_statuses == []
    assert status_names == []


def test_module_reads_no_settings__DoD12() -> None:
    """DoD-12 — the module imports no config and names no settings object or TTL setting."""
    assert not any(name == "app.config" or name.startswith("app.config.") for name in _imported_modules())
    forbidden = {"get_settings", "Settings", "session_ttl_hours", "session_cookie_name"}
    seen: list[str] = []
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Name) and node.id in forbidden:
            seen.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in forbidden:
            seen.append(node.attr)
        elif isinstance(node, ast.alias) and node.name in forbidden:
            seen.append(node.name)
    assert seen == []


@pytest.mark.parametrize(
    ("function", "expected_parameters"),
    [
        (authenticate, ["connection", "username", "password"]),
        (open_session, ["connection", "generator", "user_id", "ttl_hours"]),
        (resolve_session, ["connection", "token"]),
        (revoke_session, ["connection", "token"]),
    ],
)
def test_entry_points_take_plain_arguments_and_no_request__DoD12(
    function: Callable[..., Any], expected_parameters: list[str]
) -> None:
    """DoD-12 — plain parameters only; no `Request`, no fastapi/starlette type in the contract."""
    signature = inspect.signature(function)
    assert list(signature.parameters) == expected_parameters
    rendered = " ".join(str(parameter) for parameter in signature.parameters.values())
    rendered = f"{rendered} {signature.return_annotation}"
    assert "fastapi" not in rendered.lower()
    assert "starlette" not in rendered.lower()
    assert "Request" not in rendered
    assert "Settings" not in rendered


# ======================================================================================
# Feature 005, step 001 (`docs/plans/005.admin-shell-and-users/001.last-login-and-session-revoke.md`)
# — the `users.last_login_at` stamp in the open-session operation, and the bulk
# revoke-every-session-for-one-user helper. Expected values come from that step's DoD-3..12,
# `001.context.md` and feature `context.md` D2 / D4. Bindings come from `## Skeleton` →
# `Step 001` in feature 005's `status.md`. Tests are suffixed `__S005_001_DoD<n>`.
#
# The bulk helper opens no transaction of its own, so every call here is made inside a
# transaction the test owns (`engine.begin()` to commit, or an explicit rollback).
# ======================================================================================

UNKNOWN_USER_ID = 9_999_999_999


def _user_row(engine: Engine, user_id: int) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(select(_users()).where(_users().c.id == user_id)).mappings().one()
        return dict(row)


def _rows_of(engine: Engine, user_id: int) -> list[dict[str, Any]]:
    return [row for row in _session_rows(engine) if row["user_id"] == user_id]


def _open_in_caller_transaction(engine: Engine, user_id: int, ttl_hours: int = TTL_HOURS) -> OpenedSession:
    """Open a session inside a transaction the caller already holds (the bootstrap shape)."""
    with engine.connect() as connection:
        with connection.begin():
            return open_session(connection, SnowflakeGenerator(node_id=1), user_id, ttl_hours)


def _revoke_all(engine: Engine, user_id: int) -> int:
    """Call the bulk helper inside a caller-owned transaction that commits."""
    with engine.begin() as connection:
        return revoke_user_sessions(connection, user_id)


# --- 005/001 DoD-3: a freshly created account has `last_login_at` NULL ---------------


@pytest.mark.parametrize("user_id", [ADMIN_ID, PLAYER_ID, DISABLED_ID])
def test_fresh_account_has_null_last_login_at__S005_001_DoD3(engine: Engine, user_id: int) -> None:
    """005/001 DoD-3 — a newly inserted account carries no last-login instant."""
    assert _user_row(engine, user_id)["last_login_at"] is None


def test_authentication_does_not_write_last_login_at__S005_001_DoD3(engine: Engine) -> None:
    """005/001 DoD-3 — a successful or refused credential check is not a session opening."""
    _authenticate(engine, PLAYER_NAME, PLAYER_PASSWORD)
    with pytest.raises(InvalidCredentialsError):
        _authenticate(engine, ADMIN_NAME, "definitely not the password")
    assert _user_row(engine, PLAYER_ID)["last_login_at"] is None
    assert _user_row(engine, ADMIN_ID)["last_login_at"] is None


def test_other_operations_do_not_write_last_login_at__S005_001_DoD3(engine: Engine) -> None:
    """005/001 DoD-3 — resolve, single revoke and bulk revoke of another user's sessions
    leave an account that never opened a session at NULL; only opening writes it."""
    opened = _open(engine, ADMIN_ID)
    _resolve(engine, opened.token)
    _revoke(engine, opened.token)
    _revoke_all(engine, PLAYER_ID)
    _revoke_all(engine, ADMIN_ID)
    assert _user_row(engine, PLAYER_ID)["last_login_at"] is None
    assert _user_row(engine, DISABLED_ID)["last_login_at"] is None


# --- 005/001 DoD-4: opening a session stamps `last_login_at` = the row's `created_at` --


@pytest.mark.parametrize("path", ["own_transaction", "caller_transaction"])
def test_open_session_writes_last_login_at_equal_to_session_created_at__S005_001_DoD4(
    engine: Engine, path: str
) -> None:
    """005/001 DoD-4 — the account's `last_login_at` is the same instant as the new
    `auth_sessions` row's `created_at`, whether or not the caller already holds a transaction."""
    if path == "own_transaction":
        _open(engine, PLAYER_ID)
    else:
        _open_in_caller_transaction(engine, PLAYER_ID)
    stamped = _user_row(engine, PLAYER_ID)["last_login_at"]
    assert isinstance(stamped, str)
    session_row = _row_for_user(engine, PLAYER_ID)
    assert _parse_utc(stamped) == _parse_utc(session_row["created_at"])


def test_last_login_at_is_a_current_utc_instant__S005_001_DoD4(engine: Engine) -> None:
    """005/001 DoD-4 — the stamp is a UTC ISO-8601 instant taken at the time of the open."""
    before = datetime.now(UTC)
    _open(engine, PLAYER_ID)
    after = datetime.now(UTC)
    stamped = _parse_utc(_user_row(engine, PLAYER_ID)["last_login_at"])
    assert stamped.utcoffset() == timedelta(0)
    assert before - timedelta(seconds=1) <= stamped <= after + timedelta(seconds=1)


def test_open_session_stamps_only_the_target_account__S005_001_DoD4(engine: Engine) -> None:
    """005/001 DoD-4 — the stamp lands on the account the session was opened for, no other."""
    _open(engine, PLAYER_ID)
    assert _user_row(engine, PLAYER_ID)["last_login_at"] is not None
    assert _user_row(engine, ADMIN_ID)["last_login_at"] is None
    assert _user_row(engine, DISABLED_ID)["last_login_at"] is None


# --- 005/001 DoD-5: opening a session leaves `updated_at` unchanged ------------------


@pytest.mark.parametrize("path", ["own_transaction", "caller_transaction"])
def test_open_session_leaves_updated_at_unchanged__S005_001_DoD5(engine: Engine, path: str) -> None:
    """005/001 DoD-5 — the login stamp is not an account edit: `updated_at` stays put (D2)."""
    before = _user_row(engine, PLAYER_ID)
    assert before["updated_at"] == TIMESTAMP
    if path == "own_transaction":
        _open(engine, PLAYER_ID)
    else:
        _open_in_caller_transaction(engine, PLAYER_ID)
    after = _user_row(engine, PLAYER_ID)
    assert after["updated_at"] == TIMESTAMP
    assert after["created_at"] == before["created_at"]


def test_open_session_changes_nothing_on_the_account_but_last_login_at__S005_001_DoD5(
    engine: Engine,
) -> None:
    """005/001 DoD-5 — every account column other than `last_login_at` is unchanged."""
    before = _user_row(engine, PLAYER_ID)
    _open(engine, PLAYER_ID)
    after = _user_row(engine, PLAYER_ID)
    before.pop("last_login_at")
    after.pop("last_login_at")
    assert after == before


# --- 005/001 DoD-6: a second session advances the stamp, first row untouched ---------


def test_second_session_advances_last_login_at__S005_001_DoD6(engine: Engine) -> None:
    """005/001 DoD-6 — the second open moves `last_login_at` forward to its own creation instant."""
    _open(engine, PLAYER_ID)
    first_stamp = _user_row(engine, PLAYER_ID)["last_login_at"]
    first_row = _row_for_user(engine, PLAYER_ID)
    time.sleep(0.05)
    _open(engine, PLAYER_ID)
    second_stamp = _user_row(engine, PLAYER_ID)["last_login_at"]
    assert _parse_utc(second_stamp) > _parse_utc(first_stamp)
    second_row = next(row for row in _rows_of(engine, PLAYER_ID) if row["id"] != first_row["id"])
    assert _parse_utc(second_stamp) == _parse_utc(second_row["created_at"])


def test_second_session_leaves_the_first_session_row_untouched__S005_001_DoD6(engine: Engine) -> None:
    """005/001 DoD-6 — opening again adds a row and does not modify the earlier one."""
    first = _open(engine, PLAYER_ID)
    first_row = _row_for_user(engine, PLAYER_ID)
    time.sleep(0.05)
    _open(engine, PLAYER_ID)
    rows = _rows_of(engine, PLAYER_ID)
    assert len(rows) == 2
    assert [row for row in rows if row["id"] == first_row["id"]] == [first_row]
    assert _resolve(engine, first.token) is not None


# --- 005/001 DoD-7: the bulk revoke revokes every live row for the user --------------


def test_bulk_revoke_sets_revoked_at_on_every_live_row__S005_001_DoD7(engine: Engine) -> None:
    """005/001 DoD-7 — every live session of the user gains a `revoked_at` (US-009.AC-1)."""
    for _ in range(3):
        _open(engine, PLAYER_ID)
    assert all(row["revoked_at"] is None for row in _rows_of(engine, PLAYER_ID))
    _revoke_all(engine, PLAYER_ID)
    rows = _rows_of(engine, PLAYER_ID)
    assert len(rows) == 3
    assert all(row["revoked_at"] is not None for row in rows)


def test_bulk_revoke_stamps_the_current_utc_instant__S005_001_DoD7(engine: Engine) -> None:
    """005/001 DoD-7 — `revoked_at` is set to the current UTC ISO-8601 instant."""
    _open(engine, PLAYER_ID)
    _open(engine, PLAYER_ID)
    before = datetime.now(UTC)
    _revoke_all(engine, PLAYER_ID)
    after = datetime.now(UTC)
    for row in _rows_of(engine, PLAYER_ID):
        revoked = _parse_utc(row["revoked_at"])
        assert revoked.utcoffset() == timedelta(0)
        assert before - timedelta(seconds=1) <= revoked <= after + timedelta(seconds=1)


def test_bulk_revoke_leaves_no_token_of_the_user_resolvable__S005_001_DoD7(engine: Engine) -> None:
    """005/001 DoD-7 — none of the user's tokens resolve afterwards (US-009.AC-1)."""
    tokens = [_open(engine, PLAYER_ID).token for _ in range(3)]
    assert all(_resolve(engine, token) is not None for token in tokens)
    _revoke_all(engine, PLAYER_ID)
    assert all(_resolve(engine, token) is None for token in tokens)


def test_bulk_revoke_returns_the_number_of_rows_it_revoked__S005_001_DoD7(engine: Engine) -> None:
    """005/001 DoD-7 — the helper reports how many rows it revoked."""
    for _ in range(3):
        _open(engine, PLAYER_ID)
    count = _revoke_all(engine, PLAYER_ID)
    assert isinstance(count, int)
    assert count == 3


def test_bulk_revoke_includes_an_expired_but_unrevoked_row__S005_001_DoD7(engine: Engine) -> None:
    """005/001 DoD-7 — "live" is `revoked_at IS NULL` alone: an expired, unrevoked row is
    stamped too (001.context.md: the predicate is not filtered by `expires_at`)."""
    _open(engine, PLAYER_ID)
    _expire_row(engine, _row_for_user(engine, PLAYER_ID))
    _open(engine, PLAYER_ID)
    count = _revoke_all(engine, PLAYER_ID)
    assert count == 2
    assert all(row["revoked_at"] is not None for row in _rows_of(engine, PLAYER_ID))


# --- 005/001 DoD-8: the bulk revoke deletes nothing and keeps old revocations --------


def test_bulk_revoke_deletes_no_row__S005_001_DoD8(engine: Engine) -> None:
    """005/001 DoD-8 — the same number of rows exists before and after, with the same ids."""
    for _ in range(3):
        _open(engine, PLAYER_ID)
    _open(engine, ADMIN_ID)
    before = _session_rows(engine)
    _revoke_all(engine, PLAYER_ID)
    after = _session_rows(engine)
    assert _session_count(engine) == len(before) == 4
    assert [row["id"] for row in after] == [row["id"] for row in before]
    for old, new in zip(before, after, strict=True):
        assert new["user_id"] == old["user_id"]
        assert new["token_hash"] == old["token_hash"]
        assert new["created_at"] == old["created_at"]
        assert new["expires_at"] == old["expires_at"]


def test_bulk_revoke_keeps_an_already_revoked_rows_timestamp__S005_001_DoD8(engine: Engine) -> None:
    """005/001 DoD-8 — a row revoked earlier keeps its original `revoked_at`, not restamped."""
    earlier = _open(engine, PLAYER_ID)
    _revoke(engine, earlier.token)
    earlier_row = _row_for_user(engine, PLAYER_ID)
    original = earlier_row["revoked_at"]
    assert original is not None
    time.sleep(0.05)
    _open(engine, PLAYER_ID)
    count = _revoke_all(engine, PLAYER_ID)
    assert count == 1
    rows = {row["id"]: row for row in _rows_of(engine, PLAYER_ID)}
    assert rows[earlier_row["id"]]["revoked_at"] == original
    assert all(row["revoked_at"] is not None for row in rows.values())


def test_bulk_revoke_keeps_a_historic_revoked_at_value_verbatim__S005_001_DoD8(engine: Engine) -> None:
    """005/001 DoD-8 — a known, long-past `revoked_at` survives the bulk revoke unchanged."""
    _open(engine, PLAYER_ID)
    row = _row_for_user(engine, PLAYER_ID)
    historic = _pushed_to_the_past(row["created_at"])
    _update_session_row(engine, row["id"], revoked_at=historic)
    count = _revoke_all(engine, PLAYER_ID)
    assert count == 0
    assert _row_for_user(engine, PLAYER_ID)["revoked_at"] == historic


# --- 005/001 DoD-9: no other user's sessions are touched -----------------------------


def test_bulk_revoke_touches_no_other_users_sessions__S005_001_DoD9(engine: Engine) -> None:
    """005/001 DoD-9 — another user's rows are unchanged and their tokens still resolve."""
    admin_tokens = [_open(engine, ADMIN_ID).token for _ in range(2)]
    for _ in range(2):
        _open(engine, PLAYER_ID)
    admin_before = _rows_of(engine, ADMIN_ID)
    count = _revoke_all(engine, PLAYER_ID)
    assert count == 2
    assert _rows_of(engine, ADMIN_ID) == admin_before
    assert all(row["revoked_at"] is None for row in _rows_of(engine, ADMIN_ID))
    for token in admin_tokens:
        resolved = _resolve(engine, token)
        assert resolved is not None
        assert resolved.id == ADMIN_ID


def test_bulk_revoke_does_not_change_any_account_row__S005_001_DoD9(engine: Engine) -> None:
    """005/001 DoD-9 — the helper writes `auth_sessions` only; no `users` row changes."""
    _open(engine, ADMIN_ID)
    _open(engine, PLAYER_ID)
    accounts_before = [_user_row(engine, uid) for uid in (ADMIN_ID, PLAYER_ID, DISABLED_ID)]
    _revoke_all(engine, PLAYER_ID)
    accounts_after = [_user_row(engine, uid) for uid in (ADMIN_ID, PLAYER_ID, DISABLED_ID)]
    assert accounts_after == accounts_before


# --- 005/001 DoD-10: idempotent and total --------------------------------------------


def test_bulk_revoke_called_twice_reports_zero_the_second_time__S005_001_DoD10(engine: Engine) -> None:
    """005/001 DoD-10 — a second call raises nothing, revokes nothing new and reports zero."""
    for _ in range(2):
        _open(engine, PLAYER_ID)
    first = _revoke_all(engine, PLAYER_ID)
    after_first = _session_rows(engine)
    second = _revoke_all(engine, PLAYER_ID)
    third = _revoke_all(engine, PLAYER_ID)
    assert first == 2
    assert second == 0
    assert third == 0
    assert _session_rows(engine) == after_first


def test_bulk_revoke_for_a_user_with_no_sessions_is_zero__S005_001_DoD10(engine: Engine) -> None:
    """005/001 DoD-10 — an account that never signed in is an ordinary zero, not an error."""
    _open(engine, PLAYER_ID)
    before = _session_rows(engine)
    assert _revoke_all(engine, ADMIN_ID) == 0
    assert _session_rows(engine) == before


def test_bulk_revoke_for_an_unknown_user_id_is_zero__S005_001_DoD10(engine: Engine) -> None:
    """005/001 DoD-10 — an id no account has raises nothing and reports zero."""
    _open(engine, PLAYER_ID)
    before = _session_rows(engine)
    assert _revoke_all(engine, UNKNOWN_USER_ID) == 0
    assert _revoke_all(engine, UNKNOWN_USER_ID) == 0
    assert _session_rows(engine) == before


def test_bulk_revoke_on_an_empty_table_is_zero__S005_001_DoD10(engine: Engine) -> None:
    """005/001 DoD-10 — with no sessions at all, every call is a zero."""
    assert _session_count(engine) == 0
    assert _revoke_all(engine, PLAYER_ID) == 0
    assert _revoke_all(engine, UNKNOWN_USER_ID) == 0
    assert _session_count(engine) == 0


# --- 005/001 DoD-11: the helper opens no transaction of its own ----------------------


def test_bulk_revoke_writes_do_not_survive_a_caller_rollback__S005_001_DoD11(engine: Engine) -> None:
    """005/001 DoD-11 — called inside a caller's transaction that is rolled back, none of its
    writes persist: the caller's transaction is the boundary (context.md D4)."""
    tokens = [_open(engine, PLAYER_ID).token for _ in range(2)]
    before = _session_rows(engine)
    with engine.connect() as connection:
        transaction = connection.begin()
        count = revoke_user_sessions(connection, PLAYER_ID)
        transaction.rollback()
    assert count == 2
    assert _session_rows(engine) == before
    assert all(row["revoked_at"] is None for row in _rows_of(engine, PLAYER_ID))
    assert all(_resolve(engine, token) is not None for token in tokens)


def test_bulk_revoke_runs_inside_the_callers_open_transaction__S005_001_DoD11(engine: Engine) -> None:
    """005/001 DoD-11 — the helper accepts a connection already inside a transaction, leaves
    that transaction open, and its writes are visible to the caller before the caller decides."""
    _open(engine, PLAYER_ID)
    _open(engine, PLAYER_ID)
    with engine.connect() as connection:
        transaction = connection.begin()
        revoke_user_sessions(connection, PLAYER_ID)
        assert connection.in_transaction()
        assert transaction.is_active
        seen = connection.execute(
            select(_sessions().c.revoked_at).where(_sessions().c.user_id == PLAYER_ID)
        ).scalars().all()
        assert len(seen) == 2
        assert all(value is not None for value in seen)
        transaction.rollback()
    assert all(row["revoked_at"] is None for row in _rows_of(engine, PLAYER_ID))


def test_bulk_revoke_writes_commit_with_the_callers_other_writes__S005_001_DoD11(engine: Engine) -> None:
    """005/001 DoD-11 — a caller's own write and the revocations commit, or roll back, together
    (the one-transaction disable step 002 needs)."""
    _open(engine, PLAYER_ID)
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(update(_users()).where(_users().c.id == PLAYER_ID).values(is_enabled=False))
        revoke_user_sessions(connection, PLAYER_ID)
        transaction.rollback()
    assert _user_row(engine, PLAYER_ID)["is_enabled"] is True
    assert _row_for_user(engine, PLAYER_ID)["revoked_at"] is None

    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(update(_users()).where(_users().c.id == PLAYER_ID).values(is_enabled=False))
        revoke_user_sessions(connection, PLAYER_ID)
        transaction.commit()
    assert _user_row(engine, PLAYER_ID)["is_enabled"] is False
    assert _row_for_user(engine, PLAYER_ID)["revoked_at"] is not None


# --- 005/001 DoD-12: the module stays free of fastapi, status codes, Request, settings --


def test_module_purity_scans_still_hold_after_this_steps_additions__S005_001_DoD12() -> None:
    """005/001 DoD-12 — 004/001 DoD-12's module-wide scans hold for the extended module."""
    test_module_imports_no_fastapi_or_starlette__DoD12()
    test_module_binds_no_fastapi_symbol__DoD12()
    test_module_references_no_http_status_code__DoD12()
    test_module_reads_no_settings__DoD12()


def test_bulk_revoke_lives_in_the_auth_service_module__S005_001_DoD12() -> None:
    """005/001 DoD-12 — the helper is defined in `services/auth.py`, so the scans above cover it."""
    assert getattr(auth_module, "revoke_user_sessions", None) is revoke_user_sessions
    assert revoke_user_sessions.__module__ == auth_module.__name__


@pytest.mark.parametrize(
    ("function", "expected_parameters"),
    [
        (open_session, ["connection", "generator", "user_id", "ttl_hours"]),
        (revoke_user_sessions, ["connection", "user_id"]),
    ],
)
def test_entry_points_take_plain_arguments_and_no_request__S005_001_DoD12(
    function: Callable[..., Any], expected_parameters: list[str]
) -> None:
    """005/001 DoD-12 — the new helper and the edited open operation take plain arguments; no
    `Request`, settings or fastapi/starlette type in either contract."""
    signature = inspect.signature(function)
    assert list(signature.parameters) == expected_parameters
    rendered = " ".join(str(parameter) for parameter in signature.parameters.values())
    rendered = f"{rendered} {signature.return_annotation}"
    assert "fastapi" not in rendered.lower()
    assert "starlette" not in rendered.lower()
    assert "Request" not in rendered
    assert "Settings" not in rendered
