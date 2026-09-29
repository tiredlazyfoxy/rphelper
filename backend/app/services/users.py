"""Account management — list, create, disable, re-enable, set password, set role.

Feature `005`, step `002` (FEAT-003). Plain arguments in, a plain `UserAccount` out or a
typed `DomainError` raised. This module never imports `fastapi`, never sees a `Request`,
never knows a status code and reads no settings. Every operation takes a Core
`Connection` first; every write opens its own `with connection.begin():`.

Logging carries at most ids as decimal strings, an outcome code and a revoked-row count —
never a password, a hash, a token or a username.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import Connection, Row, Select, select
from sqlalchemy.exc import IntegrityError

from app.db.schema import users
from app.errors import SelfRoleChangeRefusedError, UsernameTakenError, UserNotFoundError
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services.auth import revoke_user_sessions
from app.services.passwords import hash_password


@dataclass(frozen=True)
class UserAccount:
    """One account as every operation here returns it — and nothing more.

    No password, no hash, no language defaults, no counts of anything.
    """

    id: int
    username: str
    role: Role
    is_enabled: bool
    last_login_at: datetime | None


def list_users(connection: Connection) -> list[UserAccount]:
    """Every account, ordered by id ascending (creation order). No filter, page or sort."""
    # A read autobegins a transaction on a Core connection; when the caller had none open,
    # end it again so a later `with connection.begin():` on the same connection works.
    opened_here = not connection.in_transaction()
    try:
        rows = connection.execute(_account_select().order_by(users.c.id)).all()
    finally:
        if opened_here and connection.in_transaction():
            connection.rollback()
    return [_to_account(row) for row in rows]


def create_user(
    connection: Connection,
    generator: SnowflakeGenerator,
    username: str,
    password: str,
    role: Role,
) -> UserAccount:
    """Insert one enabled account; a duplicate username raises `UsernameTakenError`."""
    # The unique index on `users.username` is the authority for the refusal — no
    # check-then-insert. `users` has exactly one unique constraint, so an integrity
    # violation on this insert can only be that one. Flip condition: if `users` gains a
    # second unique constraint, narrow this translation to the username one.
    try:
        with connection.begin():
            new_id = generator.next_id()
            password_hash = hash_password(password)
            now = _now_text()
            connection.execute(
                users.insert().values(
                    id=new_id,
                    username=username,
                    password_hash=password_hash,
                    role=role,
                    is_enabled=True,
                    rp_language=None,
                    preferred_language=None,
                    created_at=now,
                    updated_at=now,
                    last_login_at=None,
                )
            )
            account = _fetch_existing(connection, new_id)
    except IntegrityError:
        logger.info("users outcome=username_taken")
        raise UsernameTakenError() from None
    logger.info("users outcome=created id={}", str(new_id))
    return account


def disable_user(connection: Connection, user_id: int) -> UserAccount:
    """Clear `is_enabled` and revoke every live session in one transaction."""
    # One block: the flag flip and the revocations commit together or not at all.
    with connection.begin():
        _require_exists(connection, user_id)
        connection.execute(
            users.update().where(users.c.id == user_id).values(is_enabled=False, updated_at=_now_text())
        )
        revoked = revoke_user_sessions(connection, user_id)
        account = _fetch_existing(connection, user_id)
    logger.info("users outcome=disabled id={} count={}", str(user_id), revoked)
    return account


def enable_user(connection: Connection, user_id: int) -> UserAccount:
    """Set `is_enabled`; revokes nothing and creates no session."""
    with connection.begin():
        _require_exists(connection, user_id)
        connection.execute(
            users.update().where(users.c.id == user_id).values(is_enabled=True, updated_at=_now_text())
        )
        account = _fetch_existing(connection, user_id)
    logger.info("users outcome=enabled id={}", str(user_id))
    return account


def set_user_password(connection: Connection, user_id: int, password: str) -> UserAccount:
    """Replace the stored hash; no current password, no session revocation."""
    with connection.begin():
        _require_exists(connection, user_id)
        password_hash = hash_password(password)
        connection.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(password_hash=password_hash, updated_at=_now_text())
        )
        account = _fetch_existing(connection, user_id)
    logger.info("users outcome=password_set id={}", str(user_id))
    return account


def set_user_role(
    connection: Connection,
    user_id: int,
    role: Role,
    acting_user_id: int,
) -> UserAccount:
    """Write the target's role; refuses with `SelfRoleChangeRefusedError` on self-target."""
    # Refused before any write: an instance must not lose its last administrator through
    # one mis-click. No session is touched — the role is read live on every request.
    if user_id == acting_user_id:
        logger.info("users outcome=self_role_change_refused id={}", str(user_id))
        raise SelfRoleChangeRefusedError()
    with connection.begin():
        _require_exists(connection, user_id)
        connection.execute(
            users.update().where(users.c.id == user_id).values(role=role, updated_at=_now_text())
        )
        account = _fetch_existing(connection, user_id)
    logger.info("users outcome=role_set id={}", str(user_id))
    return account


def _account_select() -> Select[tuple[int, str, Role, bool, str | None]]:
    """The one `users` projection every result is built from — keyed on the account only."""
    return select(users.c.id, users.c.username, users.c.role, users.c.is_enabled, users.c.last_login_at)


def _to_account(row: Row[tuple[int, str, Role, bool, str | None]]) -> UserAccount:
    """Map a projected row to the plain result; `last_login_at` text parsed to aware UTC."""
    last_login_at = datetime.fromisoformat(row.last_login_at) if row.last_login_at is not None else None
    if last_login_at is not None and last_login_at.tzinfo is None:
        last_login_at = last_login_at.replace(tzinfo=UTC)
    return UserAccount(
        id=row.id,
        username=row.username,
        role=Role(row.role),
        is_enabled=bool(row.is_enabled),
        last_login_at=last_login_at,
    )


def _require_exists(connection: Connection, user_id: int) -> None:
    """Raise `UserNotFoundError` when no account has `user_id` — called before any write."""
    found = connection.execute(select(users.c.id).where(users.c.id == user_id)).first()
    if found is None:
        logger.info("users outcome=user_not_found id={}", str(user_id))
        raise UserNotFoundError()


def _fetch_existing(connection: Connection, user_id: int) -> UserAccount:
    """Read back one account known to exist, inside the caller's transaction."""
    row = connection.execute(_account_select().where(users.c.id == user_id)).one()
    return _to_account(row)


def _now_text() -> str:
    """Now as the fixed-width UTC ISO-8601 text `app.services.auth` writes."""
    return datetime.now(UTC).isoformat(timespec="microseconds")
