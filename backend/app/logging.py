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


class AccessQueryRedactionFilter(logging.Filter):
    """Stdlib filter that strips the query string from a `uvicorn.access` record.

    `configure_logging` installs it on the `uvicorn.access` **logger**, never on a
    handler, so it applies whichever handler emits the record and runs before
    `InterceptHandler` pre-formats the message through `record.getMessage()` — which means
    every sink, console and file alike, sees the rewritten target.

    uvicorn logs access lines as `'%s - "%s %s HTTP/%s" %d'` with
    `record.args == (client_addr, method, full_path, http_version, status_code)`, so the
    request target is **`record.args[2]`** and that argument is the only thing this filter
    rewrites: the path is kept and everything from the first `?` onward is dropped. The
    client address, method, HTTP version and status survive untouched, and a target that
    carries no query string is left exactly as it was.

    It is a redactor, not a gate: it **never drops a record**. `filter` returns a truthy
    value for every record it is handed, including one whose shape is not uvicorn's.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        # Anything that is not a positional tuple reaching at least index 2 is not an
        # access record: `%`-style mapping args, no args at all, or a shorter tuple. Such a
        # record is handed on untouched — mangling an unrelated record would be a worse
        # fault than the leak this filter closes.
        if not isinstance(args, tuple) or len(args) < 3:
            return True

        target = args[2]
        if not isinstance(target, str) or "?" not in target:
            # No query string (or not a string at all) means there is nothing to strip, and
            # the target must then be left exactly as it was.
            return True

        # Everything from the first `?` onward goes; the path, and every other argument,
        # survives in place.
        path = target.split("?", 1)[0]
        record.args = args[:2] + (path,) + args[3:]
        return True


def configure_logging(settings: Settings) -> None:
    """Install loguru's sinks, the stdlib bridge and the access-log redaction filter.

    Idempotent. `main.py` runs the app factory at import, so this can run more than once
    in a process: `logger.remove()` with no argument makes the sinks idempotent, and
    **installing `AccessQueryRedactionFilter` must be idempotent too** — after two calls
    the `uvicorn.access` logger carries exactly one of them, never two. No fixture
    anywhere restores a logger's `.filters`, so a filter appended twice would persist for
    the life of the process.

    Contract, in addition to everything this function already does:

    - the redaction filter goes on the `uvicorn.access` **logger**, not on a handler, so
      it covers whichever handler emits the record — uvicorn's own dictConfig may attach
      one of its own;
    - **every** sink, console and file alike, is added with `diagnose=False` **and**
      `backtrace=False`. loguru defaults both to True and either one renders frame
      content: `diagnose` prints frame locals, `backtrace` extends the traceback past the
      catching frame. The redaction rule has no level exception
      (`docs/architecture/deployment.md` § "The redaction rule"), so neither may be left
      at its default on any sink.
    """
    settings.log_file_path.parent.mkdir(parents=True, exist_ok=True)

    # `remove()` with no argument drops loguru's default stderr handler and anything a
    # previous call added, so two calls leave two sinks rather than four.
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_console_level,
        # Load-bearing on both sinks: loguru's diagnosed tracebacks print local variable
        # values, and an extended backtrace renders frames past the catching one — either
        # would defeat the redaction rule exactly when it matters most.
        diagnose=False,
        backtrace=False,
    )
    logger.add(
        settings.log_file_path,
        level=settings.log_file_level,
        rotation=settings.log_file_rotation,
        retention=settings.log_file_retention,
        diagnose=False,
        backtrace=False,
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

    access_logger = logging.getLogger("uvicorn.access")
    # Idempotent by construction: drop any filter a previous call left behind before adding
    # this call's one, so two calls leave exactly one redaction filter rather than two.
    # Nothing restores a logger's `.filters`, so an appended duplicate would live for the
    # life of the process.
    for access_filter in list(access_logger.filters):
        if isinstance(access_filter, AccessQueryRedactionFilter):
            access_logger.removeFilter(access_filter)
    access_logger.addFilter(AccessQueryRedactionFilter())

    for name in _SILENCED_LOGGERS:
        # A level on the parent is what the child inherits, so this silences the request log
        # wherever httpx emits it from (`httpx._client` today). Propagation and the root bridge
        # are left alone: the record is never created, rather than created and then dropped.
        logging.getLogger(name).setLevel(_SILENCED_LEVEL)
