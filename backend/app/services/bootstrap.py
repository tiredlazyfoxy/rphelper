"""First-run bootstrap — the configured fact and the create-first-administrator operation.

A service: takes plain arguments, returns plain results or raises a typed
`app.errors.DomainError`, and **never imports `fastapi`, never sees a `Request` and never
knows a status code**.

`is_configured` is the **only** definition in the backend of "this instance is
configured": a `users` table is present and holds at least one administrator row.
`services/health.py` delegates to it rather than holding its own copy.

`create_first_administrator` applies the registry, mints the id from the generator it is
given, hashes the password and inserts the one `users` row — all inside a single
`with conn.begin():` block. It sets no cookie, mints no token and writes no
`auth_sessions` row. It logs at most the new id (as a decimal string) and the outcome;
never the password, never the hash.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import Connection, select, text

from app.db.schema import metadata, users
from app.errors import AlreadyConfiguredError
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services.passwords import hash_password


@dataclass(frozen=True)
class BootstrapResult:
    """The newly created administrator, as plain data."""

    id: int
    username: str
    role: Role


def is_configured(connection: Connection) -> bool:
    """Answer whether a `users` table exists and holds at least one administrator row.

    Reads the table's presence from `sqlite_master` first, so a database with no schema
    answers False rather than raising. Opens no transaction and writes nothing.
    """
    # A read autobegins a transaction on a Core connection. When the caller had none open,
    # end that implicit read-only one again so a later `with connection.begin():` on the
    # same connection (the router's guard, then the creation) is not refused.
    opened_here = not connection.in_transaction()
    try:
        present = connection.execute(
            text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name LIMIT 1"),
            {"name": users.name},
        ).first()
        if present is None:
            return False
        administrator = connection.execute(
            select(users.c.id).where(users.c.role == Role.ADMIN).limit(1)
        ).first()
        return administrator is not None
    finally:
        if opened_here and connection.in_transaction():
            connection.rollback()


def create_first_administrator(
    connection: Connection,
    generator: SnowflakeGenerator,
    username: str,
    password: str,
) -> BootstrapResult:
    """Create the schema and the first administrator in one transaction.

    Inside one `with connection.begin():` block: re-check `is_configured` and raise
    `AlreadyConfiguredError` if true; apply the registry (create-if-missing); mint the id
    from `generator`; hash `password`; insert the `users` row with role `admin`.
    """
    with connection.begin():
        if is_configured(connection):
            logger.info("bootstrap outcome=already_configured")
            raise AlreadyConfiguredError()

        metadata.create_all(connection)

        new_id = generator.next_id()
        password_hash = hash_password(password)
        now = datetime.now(UTC).isoformat()
        connection.execute(
            users.insert().values(
                id=new_id,
                username=username,
                password_hash=password_hash,
                role=Role.ADMIN,
                is_enabled=True,
                rp_language=None,
                preferred_language=None,
                created_at=now,
                updated_at=now,
            )
        )

    logger.info("bootstrap outcome=created id={}", str(new_id))
    return BootstrapResult(id=new_id, username=username, role=Role.ADMIN)
