"""Authentication and the login-session lifecycle — authenticate, open, resolve, revoke.

A service: takes plain arguments, returns plain results or raises a typed
`app.errors.DomainError`, and **never imports `fastapi`, never sees a `Request`, never
knows a status code and reads no settings** — the TTL arrives as an argument and the
cookie is the router's business.

- `authenticate` refuses an unknown username, a wrong password and a disabled account
  with the one `InvalidCredentialsError` (feature `004`, D1). When no row matched it still
  verifies against a fixed decoy *encoded hash*, so the refusal is not measurably faster
  for an unknown username. Username is matched exactly, password compared as received
  (D13). Read-only; opens no transaction.
- `open_session` mints the row id from the generator it is **given**, generates a
  high-entropy random token, and inserts only the token's SHA-256 digest (D5) inside one
  `with conn.begin():` block. The plaintext token is returned and stored nowhere.
  `expires_at` is written once and never moved (D4).
- `resolve_session` looks the row up by digest and yields an identity only when the row is
  not revoked, not expired, and its `users` row is enabled — role read live (D7). Raises
  nothing; opens no transaction.
- `revoke_session` sets `revoked_at` on the matching row in its own `with conn.begin():`
  block; unknown, already-revoked and expired tokens are ordinary no-ops (D9). Deletes
  nothing.

Every timestamp this module writes uses **one** fixed-width UTC ISO-8601 format, so text
comparison of `expires_at` stays valid. Logging carries at most a user id as a decimal
string plus an outcome code — never a token, a digest, a password, or a username on a
failed login.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import Connection, select

from app.db.schema import auth_sessions, users
from app.errors import InvalidCredentialsError
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services.passwords import hash_password, verify_password

#: A real Argon2id encoded hash over a constant, computed once at import. Verified against
#: when no `users` row matched, so the refusal does the same work as a wrong password (D1).
#: An arbitrary non-hash string would make `verify_password` return False with no work.
_DECOY_PASSWORD_HASH: str = hash_password("rphelper-decoy-password-never-issued")

#: Bytes of entropy in a session token (`secrets.token_urlsafe`, D5).
_TOKEN_BYTES = 32


@dataclass(frozen=True)
class AuthenticatedUser:
    """An authenticated, enabled account's identity, as plain data."""

    id: int
    username: str
    role: Role


@dataclass(frozen=True)
class OpenedSession:
    """A freshly opened session: the plaintext token and its absolute expiry (aware UTC)."""

    token: str
    expires_at: datetime


def authenticate(connection: Connection, username: str, password: str) -> AuthenticatedUser:
    """Return the identity for a valid credential pair on an enabled account.

    Raises `InvalidCredentialsError` for an unknown username, a wrong password or a
    disabled account, indistinguishably.
    """
    opened_here = not connection.in_transaction()
    try:
        row = connection.execute(
            select(users.c.id, users.c.username, users.c.password_hash, users.c.role, users.c.is_enabled).where(
                users.c.username == username
            )
        ).first()
    finally:
        _end_implicit_read(connection, opened_here)

    if row is None:
        # Same verification work as a real account, then the same refusal (D1).
        verify_password(_DECOY_PASSWORD_HASH, password)
        logger.info("auth outcome=invalid_credentials")
        raise InvalidCredentialsError()

    password_ok = verify_password(row.password_hash, password)
    if not password_ok or not row.is_enabled:
        logger.info("auth outcome=invalid_credentials")
        raise InvalidCredentialsError()

    logger.info("auth outcome=authenticated id={}", str(row.id))
    return AuthenticatedUser(id=row.id, username=row.username, role=Role(row.role))


def open_session(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    ttl_hours: int,
) -> OpenedSession:
    """Insert one `auth_sessions` row for `user_id` and return the plaintext token."""
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    now = _utc_now()
    expires_at = now + timedelta(hours=ttl_hours)
    values = {
        "user_id": user_id,
        "token_hash": _digest(token),
        "created_at": _format_timestamp(now),
        "expires_at": _format_timestamp(expires_at),
        "revoked_at": None,
    }
    # The account's last login is the same instant as the new row's `created_at`; its
    # `updated_at` is not touched (feature `005`, D2).
    stamp_last_login = users.update().where(users.c.id == user_id).values(last_login_at=values["created_at"])
    if connection.in_transaction():
        # A caller that already holds a transaction (bootstrap's creation block, feature
        # `004` step 004) gets the insert inside it: created-and-signed-in, or nothing.
        connection.execute(auth_sessions.insert().values(id=generator.next_id(), **values))
        connection.execute(stamp_last_login)
    else:
        with connection.begin():
            connection.execute(auth_sessions.insert().values(id=generator.next_id(), **values))
            connection.execute(stamp_last_login)
    logger.info("session outcome=opened id={}", str(user_id))
    return OpenedSession(token=token, expires_at=expires_at)


def resolve_session(connection: Connection, token: str) -> AuthenticatedUser | None:
    """Return the live identity behind `token`, or `None` when it does not resolve."""
    now_text = _format_timestamp(_utc_now())
    opened_here = not connection.in_transaction()
    try:
        row = connection.execute(
            select(users.c.id, users.c.username, users.c.role)
            .select_from(auth_sessions.join(users, auth_sessions.c.user_id == users.c.id))
            .where(
                auth_sessions.c.token_hash == _digest(token),
                auth_sessions.c.revoked_at.is_(None),
                auth_sessions.c.expires_at > now_text,
                users.c.is_enabled.is_(True),
            )
        ).first()
    finally:
        _end_implicit_read(connection, opened_here)

    if row is None:
        return None
    return AuthenticatedUser(id=row.id, username=row.username, role=Role(row.role))


def revoke_session(connection: Connection, token: str) -> None:
    """Set `revoked_at` on the row matching `token`; a no-op when there is none live."""
    now_text = _format_timestamp(_utc_now())
    with connection.begin():
        connection.execute(
            auth_sessions.update()
            .where(
                auth_sessions.c.token_hash == _digest(token),
                auth_sessions.c.revoked_at.is_(None),
                auth_sessions.c.expires_at > now_text,
            )
            .values(revoked_at=now_text)
        )


def revoke_user_sessions(connection: Connection, user_id: int) -> int:
    """Set `revoked_at` on every live session of `user_id`; return how many rows it revoked.

    Opens no transaction of its own — the caller's transaction is the boundary. Deletes
    nothing, raises nothing; an unknown user id is zero rows.
    """
    now_text = _format_timestamp(_utc_now())
    result = connection.execute(
        auth_sessions.update()
        .where(auth_sessions.c.user_id == user_id, auth_sessions.c.revoked_at.is_(None))
        .values(revoked_at=now_text)
    )
    revoked = result.rowcount
    logger.info("session outcome=revoked_all id={} count={}", str(user_id), revoked)
    return revoked


def _utc_now() -> datetime:
    """Now, timezone-aware UTC."""
    return datetime.now(UTC)


def _format_timestamp(instant: datetime) -> str:
    """The module's one fixed-width UTC ISO-8601 text form (always with microseconds)."""
    return instant.astimezone(UTC).isoformat(timespec="microseconds")


def _digest(token: str) -> str:
    """The SHA-256 hex digest stored and looked up in place of the token (D5)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _end_implicit_read(connection: Connection, opened_here: bool) -> None:
    """End a read transaction the Core connection autobegan, when the caller had none open.

    Leaves a later `with connection.begin():` on the same connection possible, as
    `app.services.bootstrap.is_configured` does.
    """
    if opened_here and connection.in_transaction():
        connection.rollback()
