"""Step 005 — the SQLite engine, the connect listener and the connection dependency.

Covers DoD-1 (foreign keys), DoD-2 (WAL), DoD-3 (`sqlite-vec` on every connection),
DoD-4 (a loud extension-load failure), DoD-5 (the database path), DoD-6 (the connection
dependency), DoD-8 (engine caching and disposal) and DoD-9 (two threads).

DoD-10 and DoD-11 are `[manual/live]` and carry no test here.
"""

import threading
from pathlib import Path
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine

from app.config import Settings, get_settings
from app.db.engine import (
    ExtensionLoadError,
    dispose_engines,
    get_connection,
    get_engine,
    resolve_db_path,
)
from app.errors import DomainError

THROWAWAY_VEC_TABLE = "throwaway_vec_probe"


def _settings_at(monkeypatch: pytest.MonkeyPatch, data_dir: Path, db_filename: str) -> Settings:
    """Build a `Settings` instance pointed at a given directory and filename.

    Settings are populated through their `RPHELPER_*` variables, per this feature's test
    conventions — never by monkey-patching a module global.
    """
    monkeypatch.setenv("RPHELPER_DATA_DIR", str(data_dir))
    monkeypatch.setenv("RPHELPER_DB_FILENAME", db_filename)
    return Settings()


# --- DoD-1: PRAGMA foreign_keys -----------------------------------------------------


def test_foreign_keys_are_enabled_on_a_fresh_connection__DoD1(db_engine: Engine) -> None:
    """DoD-1 — `PRAGMA foreign_keys` reports enabled on a freshly acquired connection."""
    with db_engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_foreign_keys_are_enabled_on_a_second_separate_connection__DoD1(db_engine: Engine) -> None:
    """DoD-1 — it is re-set every time: a second, separately acquired connection reports it too.

    Both connections are held open at once so the second one cannot be the first one
    handed back out of the pool.
    """
    with db_engine.connect() as first, db_engine.connect() as second:
        assert first.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert second.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


# --- DoD-2: PRAGMA journal_mode -----------------------------------------------------


def test_journal_mode_is_wal_on_a_file_database__DoD2(db_engine: Engine) -> None:
    """DoD-2 — `PRAGMA journal_mode` reports WAL on a connection to a file database."""
    with db_engine.connect() as connection:
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
    assert isinstance(journal_mode, str)
    assert journal_mode.lower() == "wal"


# --- DoD-3: sqlite-vec on every connection ------------------------------------------


def test_extension_version_function_answers_on_a_later_connection__DoD3(db_engine: Engine) -> None:
    """DoD-3 — the extension's version function answers on a connection acquired after the first."""
    with db_engine.connect() as first:
        first.exec_driver_sql("SELECT 1")
        with db_engine.connect() as second:
            version = second.exec_driver_sql("SELECT vec_version()").scalar()
    assert isinstance(version, str)
    assert version != ""


def test_vec0_table_can_be_created_and_queried_on_a_later_connection__DoD3(db_engine: Engine) -> None:
    """DoD-3 — a `vec0` virtual table can be created and queried on a connection acquired after the first.

    The table is a throwaway in this test, never a schema object: it is not declared in
    the registry and its dimension is arbitrary.
    """
    with db_engine.connect() as first:
        first.exec_driver_sql("SELECT 1")
        with db_engine.connect() as second:
            second.exec_driver_sql(f"CREATE VIRTUAL TABLE {THROWAWAY_VEC_TABLE} USING vec0(embedding float[4])")
            second.exec_driver_sql(
                f"INSERT INTO {THROWAWAY_VEC_TABLE}(rowid, embedding) VALUES (1, '[1.0, 2.0, 3.0, 4.0]')"
            )
            rows = second.exec_driver_sql(f"SELECT rowid FROM {THROWAWAY_VEC_TABLE}").fetchall()
    assert [row[0] for row in rows] == [1]


# --- DoD-4: a failed extension load is loud -----------------------------------------


def test_failed_extension_load_raises_the_extension_load_error__DoD4(
    db_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-4 — when the loader fails, acquiring a connection raises the dedicated exception.

    `app.db.engine.load_sqlite_vec` is the seam the plan names for exactly this.
    """

    def failing_loader(*args: Any, **kwargs: Any) -> None:
        raise ExtensionLoadError("simulated sqlite-vec load failure")

    monkeypatch.setattr("app.db.engine.load_sqlite_vec", failing_loader)
    engine = get_engine(db_settings)

    with pytest.raises(ExtensionLoadError):
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")


def test_failed_extension_load_yields_no_usable_connection__DoD4(
    db_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-4 — the failure is loud, never a silent degrade: no connection object comes back."""

    def failing_loader(*args: Any, **kwargs: Any) -> None:
        raise ExtensionLoadError("simulated sqlite-vec load failure")

    monkeypatch.setattr("app.db.engine.load_sqlite_vec", failing_loader)
    engine = get_engine(db_settings)

    obtained: Connection | None = None
    with pytest.raises(ExtensionLoadError):
        obtained = engine.connect()
    assert obtained is None


def test_extension_load_error_is_not_a_domain_error_subclass__DoD4() -> None:
    """DoD-4 — it is an operational fault, not a domain error."""
    assert not issubclass(ExtensionLoadError, DomainError)


def test_raised_extension_load_error_is_not_a_domain_error__DoD4() -> None:
    """DoD-4 — the raised instance is not a `DomainError` either."""
    with pytest.raises(ExtensionLoadError) as caught:
        raise ExtensionLoadError("simulated sqlite-vec load failure")
    assert not isinstance(caught.value, DomainError)


# --- DoD-5: the database path -------------------------------------------------------


def test_database_path_is_data_dir_over_db_filename__DoD5(db_settings: Settings) -> None:
    """DoD-5 — the path resolves to `data_dir / db_filename` from the supplied settings."""
    assert resolve_db_path(db_settings) == db_settings.data_dir / db_settings.db_filename


def test_missing_data_dir_is_created_rather_than_raising__DoD5(db_settings: Settings) -> None:
    """DoD-5 — a missing `data_dir` is created, not an error."""
    assert not db_settings.data_dir.exists()
    resolve_db_path(db_settings)
    assert db_settings.data_dir.is_dir()


def test_database_file_is_created_at_the_resolved_path__DoD5(db_settings: Settings) -> None:
    """DoD-5 — the database file itself lands at `data_dir / db_filename`."""
    expected = db_settings.data_dir / db_settings.db_filename
    engine = get_engine(db_settings)
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")
    assert expected.is_file()


# --- DoD-6: the connection dependency -----------------------------------------------


def _app_with_probe(db_settings: Settings, seen: list[Connection]) -> FastAPI:
    """A throwaway application whose one route depends on `get_connection`."""
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: db_settings

    @app.get("/probe")
    def probe(connection: Annotated[Connection, Depends(get_connection)]) -> dict[str, int]:
        seen.append(connection)
        return {"value": connection.exec_driver_sql("SELECT 42").scalar_one()}

    return app


def test_dependency_yields_a_working_core_connection__DoD6(db_settings: Settings) -> None:
    """DoD-6 — the dependency yields a Core `Connection` that answers a query."""
    seen: list[Connection] = []
    with TestClient(_app_with_probe(db_settings, seen)) as client:
        response = client.get("/probe")

    assert response.status_code == 200
    assert response.json() == {"value": 42}
    assert len(seen) == 1
    assert isinstance(seen[0], Connection)


def test_dependency_closes_the_connection_after_the_request__DoD6(db_settings: Settings) -> None:
    """DoD-6 — the connection is closed once the dependent request has completed."""
    seen: list[Connection] = []
    with TestClient(_app_with_probe(db_settings, seen)) as client:
        response = client.get("/probe")

    assert response.status_code == 200
    assert len(seen) == 1
    assert seen[0].closed is True


# --- DoD-8: engine caching and disposal ---------------------------------------------


def test_same_settings_yield_the_same_engine__DoD8(db_settings: Settings) -> None:
    """DoD-8 — the factory returns the same engine for the same database path."""
    assert get_engine(db_settings) is get_engine(db_settings)


def test_a_second_settings_object_for_the_same_path_yields_the_same_engine__DoD8(
    db_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-8 — sameness is keyed on the resolved path, not on the settings object."""
    first = get_engine(db_settings)
    equivalent = _settings_at(monkeypatch, db_settings.data_dir, db_settings.db_filename)
    assert equivalent is not db_settings
    assert get_engine(equivalent) is first


def test_a_different_path_yields_a_different_engine__DoD8(
    db_settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """DoD-8 — a different database path gets a different engine."""
    first = get_engine(db_settings)
    other = _settings_at(monkeypatch, tmp_path / "other-data", "other.sqlite")
    assert resolve_db_path(other) != resolve_db_path(db_settings)
    assert get_engine(other) is not first


def test_disposal_clears_the_cache_so_a_later_call_builds_a_fresh_engine__DoD8(db_settings: Settings) -> None:
    """DoD-8 — disposal clears the cache; the next call builds a fresh engine."""
    first = get_engine(db_settings)
    dispose_engines()
    second = get_engine(db_settings)
    assert second is not first
    with second.connect() as connection:
        assert connection.exec_driver_sql("SELECT 1").scalar() == 1


# --- DoD-9: two threads -------------------------------------------------------------


def test_connections_from_two_different_threads_both_work__DoD9(db_engine: Engine) -> None:
    """DoD-9 — two threads each acquire a connection and each gets a working one."""
    barrier = threading.Barrier(2)
    results: dict[int, Any] = {}
    failures: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=15)
            with db_engine.connect() as connection:
                results[index] = connection.exec_driver_sql("SELECT 7").scalar_one()
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert failures == []
    assert results == {0: 7, 1: 7}


def test_a_pooled_connection_is_usable_from_another_thread__DoD9(db_engine: Engine) -> None:
    """DoD-9 — the same-thread assertion does not fire: a connection first opened on this
    thread and returned to the pool still works when handed to another thread."""
    with db_engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")

    results: dict[str, Any] = {}
    failures: list[BaseException] = []

    def worker() -> None:
        try:
            with db_engine.connect() as connection:
                results["value"] = connection.exec_driver_sql("SELECT 7").scalar_one()
        except BaseException as exc:
            failures.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=30)

    assert failures == []
    assert results == {"value": 7}


# ====================================================================================
# Feature 003, step 002 (``002.bootstrap-service-and-error.md``) — the engine runs
# transactional DDL (DoD-15), and the 001/005 guarantees still hold with it on (DoD-16).
# Appended only; every test above is unmodified and is DoD-16's regression gate.
# ====================================================================================

DDL_PROBE_TABLE = "s002_ddl_probe"


class _AbortBlock(Exception):
    """Raised inside a ``with conn.begin():`` block to make it exit by exception."""


def _table_present_on(connection: Connection, name: str) -> bool:
    count = connection.exec_driver_sql(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).scalar_one()
    return int(count) == 1


# --- DoD-15: DDL commits or rolls back with the block --------------------------------


def test_create_table_in_a_block_exiting_by_exception_is_absent_on_that_connection__S002_DoD15(
    db_engine: Engine,
) -> None:
    """003/002 DoD-15 — a rolled-back ``CREATE TABLE`` leaves no table on the connection that ran it."""
    with db_engine.connect() as connection:
        with pytest.raises(_AbortBlock):
            with connection.begin():
                connection.exec_driver_sql(f"CREATE TABLE {DDL_PROBE_TABLE} (value INTEGER)")
                raise _AbortBlock()
        assert _table_present_on(connection, DDL_PROBE_TABLE) is False


def test_create_table_in_a_block_exiting_by_exception_is_absent_on_a_fresh_connection__S002_DoD15(
    db_engine: Engine,
) -> None:
    """003/002 DoD-15 — a freshly acquired connection sees no such table either."""
    with db_engine.connect() as connection:
        with pytest.raises(_AbortBlock):
            with connection.begin():
                connection.exec_driver_sql(f"CREATE TABLE {DDL_PROBE_TABLE} (value INTEGER)")
                raise _AbortBlock()
    with db_engine.connect() as fresh:
        assert _table_present_on(fresh, DDL_PROBE_TABLE) is False


def test_create_table_in_a_block_exiting_normally_persists__S002_DoD15(db_engine: Engine) -> None:
    """003/002 DoD-15 — the same ``CREATE TABLE`` in a block that exits normally is present afterwards,
    on that connection and on a fresh one."""
    with db_engine.connect() as connection:
        with connection.begin():
            connection.exec_driver_sql(f"CREATE TABLE {DDL_PROBE_TABLE} (value INTEGER)")
        assert _table_present_on(connection, DDL_PROBE_TABLE) is True
    with db_engine.connect() as fresh:
        assert _table_present_on(fresh, DDL_PROBE_TABLE) is True


def test_rolled_back_create_table_can_be_run_again_and_committed__S002_DoD15(db_engine: Engine) -> None:
    """003/002 DoD-15 — after the rollback the same statement succeeds in a normal block (no leftover table)."""
    with db_engine.connect() as connection:
        with pytest.raises(_AbortBlock):
            with connection.begin():
                connection.exec_driver_sql(f"CREATE TABLE {DDL_PROBE_TABLE} (value INTEGER)")
                raise _AbortBlock()
        with connection.begin():
            connection.exec_driver_sql(f"CREATE TABLE {DDL_PROBE_TABLE} (value INTEGER)")
    with db_engine.connect() as fresh:
        assert _table_present_on(fresh, DDL_PROBE_TABLE) is True


# --- DoD-16: the 001/005 guarantees with transactional DDL on ------------------------
#
# Already covered above (unmodified): foreign_keys on a first and a second connection,
# WAL on one connection, sqlite-vec on a later connection, loud load failure. Added here
# only what is not: WAL on *each* freshly acquired connection, and all three guarantees
# still holding on fresh connections acquired after a transactional-DDL rollback/commit.


def _assert_engine_guarantees(connection: Connection) -> None:
    assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
    assert isinstance(journal_mode, str)
    assert journal_mode.lower() == "wal"
    version = connection.exec_driver_sql("SELECT vec_version()").scalar()
    assert isinstance(version, str)
    assert version != ""


def test_each_freshly_acquired_connection_has_the_engine_guarantees__S002_DoD16(db_engine: Engine) -> None:
    """003/002 DoD-16 — two separately acquired connections, held at once, each report
    foreign_keys on, journal_mode wal and a loaded sqlite-vec."""
    with db_engine.connect() as first, db_engine.connect() as second:
        _assert_engine_guarantees(first)
        _assert_engine_guarantees(second)


def test_engine_guarantees_hold_on_connections_after_transactional_ddl__S002_DoD16(db_engine: Engine) -> None:
    """003/002 DoD-16 — after a DDL block rolled back and another committed, fresh connections
    still report foreign_keys on, journal_mode wal and a loaded sqlite-vec."""
    with db_engine.connect() as connection:
        with pytest.raises(_AbortBlock):
            with connection.begin():
                connection.exec_driver_sql(f"CREATE TABLE {DDL_PROBE_TABLE} (value INTEGER)")
                raise _AbortBlock()
        with connection.begin():
            connection.exec_driver_sql(f"CREATE TABLE {DDL_PROBE_TABLE} (value INTEGER)")
        with db_engine.connect() as other:
            _assert_engine_guarantees(other)
    with db_engine.connect() as fresh:
        _assert_engine_guarantees(fresh)


def test_sqlite_vec_is_usable_inside_a_transaction_block__S002_DoD16(db_engine: Engine) -> None:
    """003/002 DoD-16 — with transactional DDL on, a `vec0` table can still be created and
    queried inside a ``with conn.begin():`` block on a fresh connection."""
    with db_engine.connect() as connection:
        with connection.begin():
            connection.exec_driver_sql(f"CREATE VIRTUAL TABLE {THROWAWAY_VEC_TABLE} USING vec0(embedding float[4])")
            connection.exec_driver_sql(
                f"INSERT INTO {THROWAWAY_VEC_TABLE}(rowid, embedding) VALUES (1, '[1.0, 2.0, 3.0, 4.0]')"
            )
            rows = connection.exec_driver_sql(f"SELECT rowid FROM {THROWAWAY_VEC_TABLE}").fetchall()
    assert [row[0] for row in rows] == [1]
