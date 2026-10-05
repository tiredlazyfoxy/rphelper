"""Logging configuration — loguru's two sinks plus the stdlib bridge.

This module is `app/logging.py` and it imports the standard library's `logging`.
Under Python 3's absolute imports that resolves to the stdlib module, not to this
one; it reads oddly but is correct, and the filename is fixed by
`docs/architecture/backend-structure.md` § Layout.

`configure_logging` is called exactly once, from `main.py`'s app factory, before any
router is registered. No other module in this backend adds, removes or reconfigures a
sink — call sites use loguru's logger directly and log ids, codes and counts, never
text.
"""

import inspect
import logging
import sys
from types import FrameType

from loguru import logger

from app.config import Settings

#: Stdlib loggers whose own handlers are cleared so their records propagate to the root.
_PROPAGATING_LOGGERS = ("uvicorn", "uvicorn.access", "uvicorn.error", "sqlalchemy")

#: Stdlib loggers whose records must never reach a sink. `httpx` logs every completed request
#: as its full URL, and **a URL can carry message text** — a search provider puts the
#: roleplayer's query in `q=` — so the HTTP client's own request log is part of the redaction
#: rule's surface (`docs/architecture/deployment.md` § "The redaction rule"). Only this logger
#: tree is silenced; every other library keeps logging exactly as before.
_SILENCED_LOGGERS = ("httpx",)

#: Above every stdlib level, because the redaction rule has no level exception: a threshold set
#: anywhere inside the scale would re-open the leak the moment a URL is logged at that level.
_SILENCED_LEVEL = logging.CRITICAL + 1


class InterceptHandler(logging.Handler):
    """Stdlib `logging` handler that forwards every record into loguru's sinks."""

    def emit(self, record: logging.LogRecord) -> None:
        # Map the stdlib level onto loguru's by name where loguru knows that name, and by
        # numeric value otherwise, so a record at a custom level still arrives.
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Walk out of the stdlib logging machinery so loguru attributes the line to the
        # module that logged it rather than to this handler.
        frame: FrameType | None = inspect.currentframe()
        depth = 0
        while frame is not None and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(settings: Settings) -> None:
    """Install loguru's two sinks and the stdlib bridge. Idempotent."""
    settings.log_file_path.parent.mkdir(parents=True, exist_ok=True)

    # `remove()` with no argument drops loguru's default stderr handler and anything a
    # previous call added, so two calls leave two sinks rather than four.
    logger.remove()
    logger.add(sys.stderr, level=settings.log_console_level)
    logger.add(
        settings.log_file_path,
        level=settings.log_file_level,
        rotation=settings.log_file_rotation,
        retention=settings.log_file_retention,
        # Load-bearing: loguru's diagnosed tracebacks print local variable values, which
        # would defeat the redaction rule exactly when it matters most.
        diagnose=False,
    )

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.addHandler(InterceptHandler())
    # NOTSET on the root filters nothing, so even a record at a custom level below DEBUG
    # reaches loguru, which then applies each sink's own threshold.
    root.setLevel(logging.NOTSET)

    for name in _PROPAGATING_LOGGERS:
        stdlib_logger = logging.getLogger(name)
        for handler in list(stdlib_logger.handlers):
            stdlib_logger.removeHandler(handler)
        stdlib_logger.propagate = True

    for name in _SILENCED_LOGGERS:
        # A level on the parent is what the child inherits, so this silences the request log
        # wherever httpx emits it from (`httpx._client` today). Propagation and the root bridge
        # are left alone: the record is never created, rather than created and then dropped.
        logging.getLogger(name).setLevel(_SILENCED_LEVEL)
