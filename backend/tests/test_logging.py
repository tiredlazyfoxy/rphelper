"""Tests for ``app.logging`` — the two loguru sinks and the stdlib bridge.

Every expected value in this module comes from ``002.logging.md``'s Definition of done
and the sink table in ``docs/plans/001.backend-foundation/002.context.md``. Covers
DoD-1 .. DoD-8; DoD-9 and DoD-10 are ``[manual/live]`` and carry no test.

Two facts about this subject shape the file:

* loguru's ``logger`` and the stdlib root logger are process-global and
  ``configure_logging`` mutates both, so the autouse ``restore_logging_state`` fixture
  below snapshots and restores every mutated logger around each test.
* loguru buffers its file sink, so every assertion about file contents is made *after*
  ``logger.remove()`` has closed the sinks.

Sink counting reads ``logger._core.handlers``: loguru exposes no public handler
inventory, so the private core is the only way to answer "how many sinks are active".
This is a recorded, deliberate choice.
"""

import io
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from loguru import logger

from app.config import Settings
from app.logging import InterceptHandler, configure_logging

# The four framework loggers DoD-6 names, and whose handlers configure_logging clears.
MANAGED_LOGGERS: tuple[str, ...] = ("uvicorn", "uvicorn.access", "uvicorn.error", "sqlalchemy")

# A stdlib level with no name of its own, and therefore no loguru level name either.
CUSTOM_LEVEL = 35

# Assembled at runtime so the value never appears as a literal in this file's source,
# and a traceback quoting this file's source cannot produce a false positive (DoD-5).
_MARKER_PARTS = ("d1agn0se", "l0cal", "7f3a")


@pytest.fixture(autouse=True)
def restore_logging_state() -> Iterator[None]:
    """Put loguru and the stdlib loggers back exactly as they were after each test.

    Setup also normalises loguru to a single stderr handler, so that "loguru's own
    default stderr handler" (DoD-2) is a well-defined thing for a test to observe.
    """
    root = logging.getLogger()
    saved_root_handlers = list(root.handlers)
    saved_root_level = root.level
    saved_named: dict[str, tuple[list[logging.Handler], int, bool]] = {}
    for name in MANAGED_LOGGERS:
        managed = logging.getLogger(name)
        saved_named[name] = (list(managed.handlers), managed.level, managed.propagate)

    logger.remove()
    logger.add(sys.stderr)

    yield

    logger.remove()
    logger.add(sys.stderr)
    root.handlers[:] = saved_root_handlers
    root.setLevel(saved_root_level)
    for name, (handlers, level, propagate) in saved_named.items():
        restored = logging.getLogger(name)
        restored.handlers[:] = handlers
        restored.setLevel(level)
        restored.propagate = propagate


def _settings(
    monkeypatch: pytest.MonkeyPatch,
    log_file_path: Path,
    *,
    console_level: str | None = None,
    file_level: str | None = None,
) -> Settings:
    """A ``Settings`` pointed at ``log_file_path``, populated through its ``RPHELPER_*`` variables.

    Every field of ``Settings`` is declared with an explicit ``validation_alias``, which
    replaces the field name as the input key entirely (``001.context.md`` § Gotchas), so a
    field-name keyword would be silently ignored and the default kept. The environment is
    therefore the only way to override — the same form as ``test_config.py``'s
    ``_hermetic_settings``, ``test_db_engine.py``'s ``_settings_at`` and ``conftest.py``'s
    ``db_settings``.

    ``env_file`` resolves against the process working directory, so a stray
    ``backend/.env`` would otherwise leak into a defaults-based assertion. The autouse
    ``isolated_settings_environment`` fixture in ``conftest.py`` clears every ``RPHELPER_*``
    variable around each test, so the environment form stays hermetic.
    """
    monkeypatch.setenv("RPHELPER_LOG_FILE_PATH", str(log_file_path))
    if console_level is not None:
        monkeypatch.setenv("RPHELPER_LOG_CONSOLE_LEVEL", console_level)
    if file_level is not None:
        monkeypatch.setenv("RPHELPER_LOG_FILE_LEVEL", file_level)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def _sink_ids() -> set[int]:
    """The ids of loguru's currently active handlers (its private core; see module docstring)."""
    return set(logger._core.handlers)  # type: ignore[attr-defined]


def _capture_stderr(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Redirect ``sys.stderr`` to an in-memory stream before the console sink is added."""
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stream)
    return stream


def _fail_using_a_local() -> None:
    """Raise from a line that mentions a local holding a distinctive value (DoD-5)."""
    marker_value = "-".join(_MARKER_PARTS)
    raise ValueError(marker_value.this_attribute_does_not_exist)  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- DoD-1


@pytest.mark.parametrize("logger_name", ["uvicorn.error", "sqlalchemy", "rphelper.tests.plain"])
def test_stdlib_record_reaches_loguru_sinks__DoD1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, logger_name: str
) -> None:
    """DoD-1: a record emitted through the stdlib logging API lands in loguru's sinks."""
    console = _capture_stderr(monkeypatch)
    configure_logging(_settings(monkeypatch, tmp_path / "logs" / "rphelper.log"))

    logging.getLogger(logger_name).warning("stdlib-bridge-marker")

    assert "stdlib-bridge-marker" in console.getvalue()


# --------------------------------------------------------------------------- DoD-2


def test_configure_logging_leaves_exactly_two_sinks__DoD2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-2: exactly two sinks afterwards, and loguru's default stderr handler is gone."""
    _capture_stderr(monkeypatch)
    default_ids = _sink_ids()
    assert len(default_ids) == 1, "fixture precondition: loguru starts with its single default stderr handler"

    configure_logging(_settings(monkeypatch, tmp_path / "logs" / "rphelper.log"))

    active_ids = _sink_ids()
    assert len(active_ids) == 2
    assert active_ids.isdisjoint(default_ids)


# --------------------------------------------------------------------------- DoD-3


def test_default_levels_apply_to_each_sink_independently__DoD3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-3: at the defaults, DEBUG reaches the console only; WARNING reaches both."""
    console = _capture_stderr(monkeypatch)
    log_file = tmp_path / "logs" / "rphelper.log"
    configure_logging(_settings(monkeypatch, log_file))

    logger.debug("debug-level-marker")
    logger.warning("warning-level-marker")
    logger.remove()  # close the file sink so its buffer is on disk

    console_text = console.getvalue()
    file_text = log_file.read_text(encoding="utf-8")
    assert "debug-level-marker" in console_text
    assert "warning-level-marker" in console_text
    assert "debug-level-marker" not in file_text
    assert "warning-level-marker" in file_text


def test_each_sink_follows_its_own_level_setting__DoD3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-3: the two level settings are honoured independently, not interchangeably."""
    console = _capture_stderr(monkeypatch)
    log_file = tmp_path / "logs" / "rphelper.log"
    settings = _settings(monkeypatch, log_file, console_level="ERROR", file_level="DEBUG")
    assert settings.log_console_level == "ERROR", "precondition: the console level override took effect"
    assert settings.log_file_level == "DEBUG", "precondition: the file level override took effect"
    configure_logging(settings)

    logger.debug("swapped-debug-marker")
    logger.error("swapped-error-marker")
    logger.remove()

    console_text = console.getvalue()
    file_text = log_file.read_text(encoding="utf-8")
    assert "swapped-debug-marker" not in console_text
    assert "swapped-error-marker" in console_text
    assert "swapped-debug-marker" in file_text
    assert "swapped-error-marker" in file_text


# --------------------------------------------------------------------------- DoD-4


def test_missing_log_directory_is_created_and_receives_records__DoD4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-4: the log file's parent directory is created, and the file then receives records."""
    _capture_stderr(monkeypatch)
    log_file = tmp_path / "absent" / "nested" / "rphelper.log"
    assert not log_file.parent.exists(), "precondition: the parent directory does not exist yet"

    configure_logging(_settings(monkeypatch, log_file))
    assert log_file.parent.is_dir()

    logger.warning("directory-creation-marker")
    logger.remove()

    assert log_file.is_file()
    assert "directory-creation-marker" in log_file.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- DoD-5


def test_exception_traceback_carries_no_local_variable_values__DoD5(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-5: the file sink's traceback holds no local variable values (``diagnose=False``)."""
    _capture_stderr(monkeypatch)
    log_file = tmp_path / "logs" / "rphelper.log"
    configure_logging(_settings(monkeypatch, log_file))

    try:
        _fail_using_a_local()
    except AttributeError:
        logger.exception("exception-traceback-marker")
    logger.remove()

    file_text = log_file.read_text(encoding="utf-8")
    assert "exception-traceback-marker" in file_text
    assert "Traceback" in file_text
    assert "_fail_using_a_local" in file_text
    assert "-".join(_MARKER_PARTS) not in file_text


# --------------------------------------------------------------------------- DoD-6


@pytest.mark.parametrize("logger_name", MANAGED_LOGGERS)
def test_framework_logger_has_no_handler_and_propagates__DoD6(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, logger_name: str
) -> None:
    """DoD-6: uvicorn, uvicorn.access, uvicorn.error and sqlalchemy own no handler."""
    _capture_stderr(monkeypatch)
    framework_logger = logging.getLogger(logger_name)
    framework_logger.addHandler(logging.NullHandler())
    assert framework_logger.handlers, "precondition: the logger owns a handler before configuration"

    configure_logging(_settings(monkeypatch, tmp_path / "logs" / "rphelper.log"))

    assert framework_logger.handlers == []
    assert framework_logger.propagate is True


# --------------------------------------------------------------------------- DoD-7


def test_configure_logging_is_idempotent__DoD7(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-7: two calls leave two sinks and one intercept handler on the root."""
    _capture_stderr(monkeypatch)
    settings = _settings(monkeypatch, tmp_path / "logs" / "rphelper.log")

    configure_logging(settings)
    configure_logging(settings)

    assert len(_sink_ids()) == 2
    root_handlers = logging.getLogger().handlers
    assert len(root_handlers) == 1
    assert isinstance(root_handlers[0], InterceptHandler)


# --------------------------------------------------------------------------- DoD-8


def test_intercept_handler_preserves_a_named_level__DoD8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-8: a stdlib ERROR record arrives at loguru as ERROR."""
    _capture_stderr(monkeypatch)
    configure_logging(_settings(monkeypatch, tmp_path / "logs" / "rphelper.log"))
    seen: list[Any] = []
    logger.add(seen.append, level=0, format="{message}")

    logging.getLogger("rphelper.tests.levels").error("named-level-marker")

    matched = [message.record for message in seen if "named-level-marker" in message.record["message"]]
    assert len(matched) == 1
    assert matched[0]["level"].name == "ERROR"
    assert matched[0]["level"].no == logging.ERROR


def test_intercept_handler_passes_through_an_unnamed_numeric_level__DoD8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-8: a record at a custom numeric level loguru has no name for still arrives."""
    _capture_stderr(monkeypatch)
    configure_logging(_settings(monkeypatch, tmp_path / "logs" / "rphelper.log"))
    seen: list[Any] = []
    logger.add(seen.append, level=0, format="{message}")

    logging.getLogger("rphelper.tests.levels").log(CUSTOM_LEVEL, "numeric-level-marker")

    matched = [message.record for message in seen if "numeric-level-marker" in message.record["message"]]
    assert len(matched) == 1
    assert matched[0]["level"].no == CUSTOM_LEVEL
