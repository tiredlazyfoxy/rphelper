"""Tests for feature 032 step 001 — logging and engine redaction hardening.

Every expected value in this module comes from
``docs/plans/032.privacy-isolation-audit/001.logging-redaction-hardening.md``'s
Definition of done (DoD-1 .. DoD-7). DoD-8 is ``[manual/live]`` (a real uvicorn run)
and carries no test. Each item cites **US-084.AC-1**: operator-facing logs are an
administrative surface, so no log record at any level may carry user text
(``docs/architecture/deployment.md`` "The redaction rule").

Three facts about this subject shape the file:

* loguru's ``logger`` and the stdlib loggers are process-global, ``configure_logging``
  mutates both, and nothing else in the suite restores a logger's ``.filters``. The
  autouse ``restore_logging_state`` fixture below therefore snapshots and restores the
  ``level``, ``handlers``, ``propagate`` **and** ``.filters`` of every logger these
  tests touch, and resets loguru to a single stderr sink on both sides.
* loguru buffers its file sink, so every assertion about file contents is made after
  ``logger.remove()`` has closed the sinks.
* a traceback is rendered with each frame's **source line**, so every sentinel here is
  assembled at runtime and never appears as a literal in this file's source.

Access records are emitted through ``logging.getLogger("uvicorn.access")`` rather than
handed to a handler, because a record given straight to a handler bypasses
logger-level filters and would make the assertions pass for the wrong reason. The
record shape is uvicorn's own: ``'%s - "%s %s HTTP/%s" %d'`` with
``(client_addr, method, full_path, http_version, status_code)``.

This step predates the shared privacy-audit support module, so the log-capture helper
is local to this file by design (``001.context.md``).
"""

import io
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.db.engine import dispose_engines, get_engine
from app.logging import AccessQueryRedactionFilter, configure_logging

ACCESS_LOGGER_NAME = "uvicorn.access"
SQL_LOGGER_NAME = "sqlalchemy.engine"

# Every logger whose state these tests mutate, directly or through configure_logging.
TOUCHED_LOGGERS: tuple[str, ...] = (
    "",
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "sqlalchemy",
    "sqlalchemy.engine",
    "httpx",
)

# The non-target parts of an access record, which the redaction must leave untouched.
CLIENT_ADDR = "127.0.0.1:52000"
HTTP_VERSION = "1.1"
METHOD = "GET"
STATUS_CODE = 200

SEARCH_PATH = "/api/search"
HEALTH_PATH = "/api/health"

# The scratch table DoD-5 and DoD-6 drive their statements through.
PROBE_TABLE = "redaction_probe"

# Sentinels: single lowercase alphanumeric tokens (feature context.md "Shared
# vocabulary"), assembled at runtime so no sentinel is ever a literal in this source
# and a traceback quoting this file cannot produce a false positive (DoD-4).
_QUERY_SENTINEL = "".join(("sntl", "accessquery", "7c1d"))
_TRACEBACK_SENTINEL = "".join(("sntl", "frameloc", "4b82"))
_BOUND_PARAM_SENTINEL = "".join(("sntl", "boundparam", "9e30"))
_CONSTRAINT_SENTINEL = "".join(("sntl", "constraint", "2f55"))

# Carries no sentinel, so the exception's own message cannot explain an absence.
_FAILURE_MARKER = "redaction-traceback-marker"


@pytest.fixture(autouse=True)
def restore_logging_state() -> Iterator[None]:
    """Put loguru and every stdlib logger these tests touch back exactly as they were.

    ``.filters`` is restored as well as ``level``, ``handlers`` and ``propagate``: the
    redaction filter lives on the ``uvicorn.access`` logger, and no other fixture in the
    suite restores a logger's filter list.
    """
    saved: dict[str, tuple[list[logging.Handler], int, bool, list[Any]]] = {}
    for name in TOUCHED_LOGGERS:
        touched = logging.getLogger(name)
        saved[name] = (
            list(touched.handlers),
            touched.level,
            touched.propagate,
            list(touched.filters),
        )

    logger.remove()
    logger.add(sys.stderr)

    yield

    logger.remove()
    logger.add(sys.stderr)
    for name, (handlers, level, propagate, filters) in saved.items():
        restored = logging.getLogger(name)
        restored.handlers[:] = handlers
        restored.setLevel(level)
        restored.propagate = propagate
        restored.filters[:] = filters


@pytest.fixture(autouse=True)
def dispose_scratch_engines() -> Iterator[None]:
    """Drop every cached engine afterwards, so no scratch database handle outlives a test."""
    yield
    dispose_engines()


def _log_path(tmp_path: Path) -> Path:
    return tmp_path / "logs" / "rphelper.log"


def _settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    """A ``Settings`` whose data directory, database file and log file all live in ``tmp_path``.

    Every ``Settings`` field is declared with an explicit ``validation_alias``, so a
    field-name keyword would be silently ignored; the ``RPHELPER_*`` environment is the
    only way to override (precedent: ``test_logging.py::_settings``, ``conftest.py``'s
    ``db_settings``). ``_env_file=None`` keeps ``backend/.env`` out of it entirely, and
    both sink levels are lowered to DEBUG so console and file alike see every record
    under test.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RPHELPER_DATA_DIR", str(data_dir))
    monkeypatch.setenv("RPHELPER_DB_FILENAME", "redaction.sqlite")
    monkeypatch.setenv("RPHELPER_LOG_FILE_PATH", str(_log_path(tmp_path)))
    monkeypatch.setenv("RPHELPER_LOG_CONSOLE_LEVEL", "DEBUG")
    monkeypatch.setenv("RPHELPER_LOG_FILE_LEVEL", "DEBUG")
    return Settings(_env_file=None)  # type: ignore[call-arg]


def _capture_stderr(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Redirect ``sys.stderr`` to an in-memory stream *before* the console sink binds it."""
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stream)
    return stream


@contextmanager
def _captured_logs() -> Iterator[list[str]]:
    """Every loguru line emitted while the block runs — rendered text, message, extra, exception.

    A level-0 sink, removed by id on exit (precedent ``test_sync_executor.py:223``).
    """
    lines: list[str] = []

    def sink(message: Any) -> None:
        record = message.record
        lines.append(str(message))
        lines.append(str(record["message"]))
        lines.append(repr(record["extra"]))
        if record["exception"] is not None:
            lines.append(repr(record["exception"].value))

    handler_id = logger.add(sink, level=0, format="{level} {name} {message}")
    try:
        yield lines
    finally:
        logger.remove(handler_id)


def _emit_access_record(target: str) -> None:
    """Emit one record in uvicorn's access shape on the ``uvicorn.access`` logger."""
    logging.getLogger(ACCESS_LOGGER_NAME).info(
        '%s - "%s %s HTTP/%s" %d',
        CLIENT_ADDR,
        METHOD,
        target,
        HTTP_VERSION,
        STATUS_CODE,
    )


def _rendered_access_line(target: str) -> str:
    """The access line as uvicorn's format string renders it for ``target``."""
    return f'{CLIENT_ADDR} - "{METHOD} {target} HTTP/{HTTP_VERSION}" {STATUS_CODE}'


def _raise_from_a_frame_holding_a_sentinel() -> None:
    """Raise from a line that names a local holding a sentinel, but never its value (DoD-4)."""
    hidden_local = _TRACEBACK_SENTINEL
    raise RuntimeError(hidden_local.this_attribute_does_not_exist)  # type: ignore[attr-defined]


def _create_probe_table(settings: Settings) -> None:
    """Create the scratch table whose single column is unique and not null."""
    engine = get_engine(settings)
    with engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE TABLE {PROBE_TABLE} (value TEXT NOT NULL UNIQUE)")


def _insert_probe_value(settings: Settings, value: str) -> None:
    """Insert ``value`` as a bound parameter, so the value never appears in the statement text."""
    engine = get_engine(settings)
    with engine.begin() as connection:
        connection.execute(text(f"INSERT INTO {PROBE_TABLE} (value) VALUES (:value)"), {"value": value})


# --------------------------------------------------------------------------- DoD-1


def test_access_query_sentinel_reaches_no_sink__S032_001_DoD1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-1 (US-084.AC-1): a query-string sentinel reaches neither console, file nor a level-0 sink."""
    console = _capture_stderr(monkeypatch)
    log_file = _log_path(tmp_path)
    configure_logging(_settings(monkeypatch, tmp_path))

    with _captured_logs() as captured:
        _emit_access_record(f"{SEARCH_PATH}?q={_QUERY_SENTINEL}")
    logger.remove()  # close the file sink so its buffer is on disk

    console_text = console.getvalue()
    file_text = log_file.read_text(encoding="utf-8")
    captured_text = "\n".join(captured)

    # Positive controls: the record really did reach all three sinks, so no absence below
    # can pass vacuously.
    assert SEARCH_PATH in console_text
    assert SEARCH_PATH in file_text
    assert SEARCH_PATH in captured_text

    assert _QUERY_SENTINEL not in console_text
    assert _QUERY_SENTINEL not in file_text
    assert _QUERY_SENTINEL not in captured_text


def test_redaction_filter_is_installed_once_after_two_calls__S032_001_DoD1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-1 (US-084.AC-1): the ``uvicorn.access`` logger carries exactly one redaction filter.

    ``create_app()`` runs at import of ``app.main``, so ``configure_logging`` genuinely
    runs more than once per process; two calls must still leave one filter, never two.
    """
    _capture_stderr(monkeypatch)
    settings = _settings(monkeypatch, tmp_path)

    configure_logging(settings)
    configure_logging(settings)

    access_logger = logging.getLogger(ACCESS_LOGGER_NAME)
    installed = [f for f in access_logger.filters if isinstance(f, AccessQueryRedactionFilter)]
    assert len(installed) == 1


# --------------------------------------------------------------------------- DoD-2


def test_redacted_access_line_still_names_method_path_and_status__S032_001_DoD2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-2 (US-084.AC-1): the written line still names the method, the query-less path and the status."""
    console = _capture_stderr(monkeypatch)
    log_file = _log_path(tmp_path)
    configure_logging(_settings(monkeypatch, tmp_path))

    _emit_access_record(f"{SEARCH_PATH}?q={_QUERY_SENTINEL}")
    logger.remove()

    for written in (console.getvalue(), log_file.read_text(encoding="utf-8")):
        assert METHOD in written
        assert SEARCH_PATH in written
        assert str(STATUS_CODE) in written
        # The path survives, and nothing hangs off it: the target lost its query string.
        assert f"{SEARCH_PATH}?" not in written


# --------------------------------------------------------------------------- DoD-3


def test_access_line_without_a_query_string_is_unchanged__S032_001_DoD3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-3 (US-084.AC-1): a target with no query string is emitted exactly as it was."""
    console = _capture_stderr(monkeypatch)
    log_file = _log_path(tmp_path)
    configure_logging(_settings(monkeypatch, tmp_path))

    with _captured_logs() as captured:
        _emit_access_record(HEALTH_PATH)
    logger.remove()

    expected = _rendered_access_line(HEALTH_PATH)
    assert expected in console.getvalue()
    assert expected in log_file.read_text(encoding="utf-8")
    assert expected in "\n".join(captured)


# --------------------------------------------------------------------------- DoD-4


def test_traceback_keeps_the_frame_and_drops_frame_locals__S032_001_DoD4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-4 (US-084.AC-1): a logged traceback names its frame but renders no local's value."""
    console = _capture_stderr(monkeypatch)
    log_file = _log_path(tmp_path)
    configure_logging(_settings(monkeypatch, tmp_path))

    try:
        _raise_from_a_frame_holding_a_sentinel()
    except AttributeError:
        logger.exception(_FAILURE_MARKER)
    logger.remove()

    for written in (console.getvalue(), log_file.read_text(encoding="utf-8")):
        # Positive controls: the traceback was rendered, and its frame is still named.
        assert _FAILURE_MARKER in written
        assert "Traceback" in written
        assert "_raise_from_a_frame_holding_a_sentinel" in written

        assert _TRACEBACK_SENTINEL not in written


# --------------------------------------------------------------------------- DoD-5


def test_sql_log_records_carry_no_bound_parameter_value__S032_001_DoD5(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-5 (US-084.AC-1): with ``sqlalchemy.engine`` at INFO, no record carries a bound value."""
    _capture_stderr(monkeypatch)
    settings = _settings(monkeypatch, tmp_path)
    configure_logging(settings)
    _create_probe_table(settings)

    logging.getLogger(SQL_LOGGER_NAME).setLevel(logging.INFO)
    with _captured_logs() as captured:
        _insert_probe_value(settings, _BOUND_PARAM_SENTINEL)
    logger.remove()

    captured_text = "\n".join(captured)
    # Positive control: the statement really was logged, so the absence is not vacuous.
    assert PROBE_TABLE in captured_text

    assert _BOUND_PARAM_SENTINEL not in captured_text


# --------------------------------------------------------------------------- DoD-6


def test_constraint_violation_string_form_carries_no_bound_value__S032_001_DoD6(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-6 (US-084.AC-1): the rendered constraint error names the statement, never the value."""
    _capture_stderr(monkeypatch)
    settings = _settings(monkeypatch, tmp_path)
    _create_probe_table(settings)
    _insert_probe_value(settings, _CONSTRAINT_SENTINEL)

    with pytest.raises(IntegrityError) as excinfo:
        _insert_probe_value(settings, _CONSTRAINT_SENTINEL)

    rendered = str(excinfo.value)
    # Positive control: the error does render the statement, so a parameter section was
    # there to redact.
    assert PROBE_TABLE in rendered

    assert _CONSTRAINT_SENTINEL not in rendered


# --------------------------------------------------------------------------- DoD-7


def test_factory_engine_reports_hidden_parameters__S032_001_DoD7(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-7 (US-084.AC-1): an engine from the factory reports that it hides parameters."""
    settings = _settings(monkeypatch, tmp_path)

    assert get_engine(settings).hide_parameters is True
