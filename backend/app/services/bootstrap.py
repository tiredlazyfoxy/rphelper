"""First-run bootstrap — the configured fact and the create-first-administrator operation.

A service: takes plain arguments, returns plain results or raises a typed
`app.errors.DomainError`, and **never imports `fastapi`, never sees a `Request` and never
knows a status code**.

`is_configured` is the **only** definition in the backend of "this instance is
configured": a `users` table is present and holds at least one administrator row.
`services/health.py` delegates to it rather than holding its own copy.

`create_first_administrator` applies the registry, mints the id from the generator it is
given, hashes the password, inserts the one `users` row and opens the administrator's
session through `app.services.auth.open_session` on the same connection — all inside a
single `with conn.begin():` block. It returns the session token and expiry as plain data
and sets no cookie; the router is what turns the token into a cookie. It logs at most the
new id (as a decimal string) and the outcome; never the password, the hash or the token.

`restore_from_export` (`fast/003`) is the second way in: inside one `with conn.begin():` block it
re-checks `is_configured`, applies the registry, ensures the FTS5 tables and runs the
whole-database import through `app.services.transfer_import.import_database_in_transaction`, so a
failed restore rolls the DDL back with it. It opens no session and logs the outcome token only.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import Connection, select, text

from app.db.schema import metadata, users
from app.db.search_tables import ensure_fts_tables
from app.errors import AlreadyConfiguredError, DomainError
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services.auth import open_session
from app.services.passwords import hash_password
from app.services.transfer_import import import_database_in_transaction


@dataclass(frozen=True)
class BootstrapResult:
    """The newly created administrator, as plain data."""

    id: int
    username: str
    role: Role
    token: str
    expires_at: datetime


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
    ttl_hours: int,
) -> BootstrapResult:
    """Create the schema and the first administrator in one transaction.

    Inside one `with connection.begin():` block: re-check `is_configured` and raise
    `AlreadyConfiguredError` if true; apply the registry (create-if-missing); ensure the
    FTS5 virtual tables, which live outside `metadata` (024 D2); mint the id from
    `generator`; hash `password`; insert the `users` row with role `admin`; open the
    administrator's session via `open_session(connection, generator, new_id, ttl_hours)`.
    Returns the id, username, role, session token and session expiry. No vector table is
    created: no embedding model is designated at bootstrap.
    """
    with connection.begin():
        if is_configured(connection):
            logger.info("bootstrap outcome=already_configured")
            raise AlreadyConfiguredError()

        metadata.create_all(connection)
        # The FTS5 virtual tables live outside `metadata` (024 D2), so `create_all`
        # cannot make them. Ensuring them here — inside this same block, after the
        # `AlreadyConfiguredError` guard — keeps a refused create leaving an empty
        # database. No vector table: no embedding model is designated at bootstrap.
        ensure_fts_tables(connection)

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

        session = open_session(connection, generator, new_id, ttl_hours)

    logger.info("bootstrap outcome=created id={}", str(new_id))
    return BootstrapResult(
        id=new_id,
        username=username,
        role=Role.ADMIN,
        token=session.token,
        expires_at=session.expires_at,
    )


def restore_from_export(connection: Connection, body: object) -> None:
    """Create the schema and restore a whole-database export into it, in one transaction.

    `fast/003` (UC-002, US-002). Inside one `with connection.begin():` block: re-check
    `is_configured` and raise `AlreadyConfiguredError` if true; apply the registry
    (`metadata.create_all`); ensure the FTS5 virtual tables; call
    `app.services.transfer_import.import_database_in_transaction(connection, body)`. Any error
    raised inside rolls the whole block back, the created DDL included, so a failed restore leaves
    no tables. Returns nothing and opens no session. Logs a single `bootstrap outcome=...` line
    per call — success, refusal or failure — carrying the outcome token only.

    """
    try:
        with connection.begin():
            if is_configured(connection):
                raise AlreadyConfiguredError()

            metadata.create_all(connection)
            # The FTS5 virtual tables live outside `metadata` (024 D2); ensured in this same block
            # so a failed restore rolls them back with the rest of the DDL.
            ensure_fts_tables(connection)
            import_database_in_transaction(connection, body)
    except DomainError as refusal:
        logger.info("bootstrap outcome={}", refusal.code)
        raise
    except Exception:
        logger.info("bootstrap outcome=restore_failed")
        raise

    logger.info("bootstrap outcome=restored")
