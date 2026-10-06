"""The SQLite connection factory — SQLAlchemy **Core**, never the ORM.

`docs/architecture/backend-structure.md` § Database access: one connection factory,
which **on every connection** loads the `sqlite-vec` extension, sets
`PRAGMA foreign_keys = ON` and sets `PRAGMA journal_mode = WAL`. One `connect` event
listener does all three, in that order — the extension first, so that a load that is
going to fail fails before anything has been asserted on a connection about to be
discarded (`005.context.md`).

Why one listener rather than two mechanisms: `foreign_keys` genuinely is per-connection
and must be re-set every time; `journal_mode` is a persistent file-level property, so
re-asserting it is a cheap idempotent no-op rather than a second mechanism with its own
ordering question. Neither PRAGMA is ever set inside a `begin()` block.

`load_sqlite_vec` is a **named module-level function** on purpose: it is the seam a test
patches to make the load fail. A failed load raises `ExtensionLoadError` — loud at
connection time — rather than handing back a connection without the extension, because
the extension is a hard requirement from stage `004` onward and a silently missing one
surfaces as an inexplicable query error much later, in a feature that did nothing wrong.

`ExtensionLoadError` is deliberately a plain `Exception` and **not** a subclass of
`app.errors.DomainError`, for the same reason `ids.BackwardsClockError` is not: it is an
operational fault — a 500 — not a domain failure the SPA is expected to render. Do not
tidy it into the error hierarchy.

Engines are cached on the **resolved database path**, not on the settings object:
settings instances are not hashable, and per-test databases under different `tmp_path`
directories must coexist in one process. The pysqlite dialect's default pool for a file
database is used, with the DBAPI's same-thread assertion disabled — uvicorn hands a
pooled connection to whichever worker thread runs the request, and the pool already
guarantees one connection is never used by two threads at once.

No ORM construct appears here: no `DeclarativeBase`, no mapped class, no `Session`, no
identity map, no `sqlalchemy.orm` import. `get_connection` opens **no transaction** —
transaction boundaries are `with conn.begin():` blocks at the service's own level, which
is one of the three reasons Core was chosen over the ORM. No DDL runs anywhere in this
module, including at import.

**Transactional DDL** (feature `003`, decision D8). Under the stdlib `sqlite3` driver's
legacy transaction control, SQLAlchemy's `begin()` sends no `BEGIN`: the driver opens a
transaction lazily, only before DML, so a `CREATE TABLE` issued first autocommits and
survives a rollback. The engine therefore uses SQLAlchemy's documented pysqlite recipe:
the driver's implicit transaction handling is switched off (`isolation_level=None` in
the connect arguments, so the driver never begins or commits anything on its own), and a
`begin` listener emits the real `BEGIN`. Every statement inside a `with conn.begin():`
block — DDL included — then commits or rolls back with the block, and savepoints work.
Python 3.12's PEP 249 mode (`autocommit=False`) is deliberately **not** used: it keeps a
transaction open from connect onward, and `PRAGMA journal_mode = WAL` cannot be entered
inside one. With implicit transactions off, the `connect` listener's PRAGMAs run in
autocommit, outside any transaction. An autobegun read (a Core `Connection`'s first
`execute` outside a block) also sends a real, deferred `BEGIN`; it is ended by the
caller's `rollback()`/`commit()`, or by the pool's reset-on-return.
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

import sqlite_vec  # type: ignore[import-untyped]
from fastapi import Depends
from sqlalchemy import Connection, Engine, create_engine, event

from app.config import Settings, get_settings

#: One `Engine` per resolved database path, per process (decision D9). Keyed on the
#: path so two tests pointing at different directories get different engines.
_engines: dict[Path, Engine] = {}


class ExtensionLoadError(Exception):
    """Raised when the `sqlite-vec` extension cannot be loaded into a connection.

    An operational fault, not a domain error — deliberately **not** a subclass of
    `app.errors.DomainError`.
    """


def resolve_db_path(settings: Settings) -> Path:
    """Return `settings.data_dir / settings.db_filename`, creating the directory.

    A missing `data_dir` is created rather than raising. The returned path is also the
    key the engine cache uses.
    """
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / settings.db_filename


def load_sqlite_vec(dbapi_connection: sqlite3.Connection) -> None:
    """Load the `sqlite-vec` extension into a raw DBAPI connection.

    Enables extension loading, loads the extension, disables extension loading again.
    Raises `ExtensionLoadError` if the load fails — never returns a connection without
    the extension.

    Module-level and named, so that it is a patchable seam.
    """
    try:
        dbapi_connection.enable_load_extension(True)
        try:
            sqlite_vec.load(dbapi_connection)
        finally:
            dbapi_connection.enable_load_extension(False)
    except Exception as exc:
        raise ExtensionLoadError("could not load the sqlite-vec extension") from exc


def get_engine(settings: Settings) -> Engine:
    """Return the process-wide `Engine` for this settings instance's database path.

    Built once per resolved path and cached. Uses the pysqlite dialect's default pool
    for a file database with `check_same_thread=False`, and registers the single
    `connect` listener that — on every new connection, in this order — loads
    `sqlite-vec`, sets `PRAGMA foreign_keys = ON` and sets `PRAGMA journal_mode = WAL`.
    The driver's implicit transactions are off and a `begin` listener sends the real
    `BEGIN`, so DDL inside a `with conn.begin():` block is transactional.

    **Bound parameters are hidden**, so no SQLAlchemy log record at any level and no
    rendered statement error (`str(exc)` of a `DBAPIError` and its subclasses) carries a
    bound value — SQLAlchemy writes a placeholder in their place. The redaction rule has
    no level exception (`docs/architecture/deployment.md` § "The redaction rule"), and a
    bound parameter is the one place user text reaches the SQL layer verbatim. Read back
    as **`engine.hide_parameters`**, which every engine this factory returns reports as
    true. That is the *only* engine option added: the URL, the `connect_args` below, the
    two listeners and the per-path caching are unchanged, and because engines are cached
    per resolved path the flag is fixed at first creation for that path.
    """
    path = resolve_db_path(settings)
    cached = _engines.get(path)
    if cached is not None:
        return cached

    engine = create_engine(
        f"sqlite+pysqlite:///{path.as_posix()}",
        # `isolation_level=None`: the driver's own implicit BEGIN/COMMIT handling is off;
        # `_on_begin` below sends the real `BEGIN` (transactional DDL, see module doc).
        connect_args={"check_same_thread": False, "isolation_level": None},
        # The one option this factory adds beyond the URL and `connect_args`: no SQLAlchemy
        # log record and no rendered `DBAPIError` carries a bound value (see the docstring).
        hide_parameters=True,
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: sqlite3.Connection, connection_record: Any) -> None:
        # Extension first: a load that is going to fail should fail before anything has
        # been asserted on a connection that is about to be discarded.
        try:
            load_sqlite_vec(dbapi_connection)
        except ExtensionLoadError:
            raise
        except Exception as exc:
            raise ExtensionLoadError("could not load the sqlite-vec extension") from exc

        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA journal_mode = WAL")
        finally:
            cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(connection: Connection) -> None:
        # The driver no longer begins on its own, so SQLAlchemy's `begin` (explicit or
        # autobegin) emits the real `BEGIN`; everything after it, DDL included, belongs
        # to the transaction.
        connection.exec_driver_sql("BEGIN")

    _engines[path] = engine
    return engine


def dispose_engines() -> None:
    """Dispose every cached engine and empty the cache. For fixture teardown."""
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()


def get_connection(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[Connection]:
    """FastAPI dependency yielding a Core `Connection` for the life of the request.

    The only way a router obtains a connection; closed when the request completes.
    It opens **no** transaction — callers use `with conn.begin():` at their own level.
    """
    connection = get_engine(settings).connect()
    try:
        yield connection
    finally:
        connection.close()
