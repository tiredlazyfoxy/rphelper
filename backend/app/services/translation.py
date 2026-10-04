"""Partner-entry translation — the eligible-row read, the cache, and the one model call.

Feature `023`, step `002` (`context.md` D2–D10). The flow is three phases and **no connection
is held across the provider await** (D8), which is why `translate_message` takes an `Engine`
rather than a `Connection`: it opens one short-lived read connection, closes it, calls the
provider, then opens a second short-lived connection for the write transaction. The sync
helpers keep the services' posture — a Core `Connection` first, plain arguments after.

1. **Read** — the eligible row through the `settled_entries` selectable (never raw `messages`,
   R11), owner-scoped in SQL (R5); the target language from 017's `get_session_configuration`,
   falling back to `FALLBACK_TARGET_LANGUAGE` (D3); then the cache. A hit returns
   `cached=True` here, with no model resolution and no call. On a miss, `resolve_model_for_use`
   and `open_chat_client`, whose errors propagate **unchanged** (D5).
2. **Call** — 021's `chat_stream` with the resolved model's name, exactly two `ChatMessage`s
   and **no tools** (D2). Content deltas are joined in arrival order; `reasoning` and
   `tool_calls` are ignored; the iterator is always closed. The joined text goes through 021
   D4's `strip_think` (D10). Only two outcomes become `TranslationFailedError`: an
   `LlmUnreachableError` from `chat_stream`, and a result that is empty after stripping (D5).
3. **Write** — the injected disconnect probe is awaited **once**, immediately before the write
   (D4, best-effort by design). Otherwise one short transaction inserts the row, but only while
   the message is still the caller's settled partner row carrying the same text (D9), ignoring
   a unique-pair conflict (D8). The produced text is returned either way, with `cached=False`.

This module imports no `fastapi` — the disconnect probe arrives as an injected async callable
(`DisconnectProbe`), declared here so the service layer stays HTTP-free. Its `app.services`
imports are limited to `configuration`, `llm_registry`, `llm.chat` and `llm.client`. It is the
only module that reads or writes the `translations` table (R8), the one exception being the
delete inside `services/messages.py`'s edit transaction (D11). Nothing here is ever read by
context assembly, and no log line carries source text, a translation or a prompt
(`deployment.md`'s redaction rule).
"""

import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from loguru import logger
from sqlalchemy import Connection, Engine, select
from sqlalchemy.dialects.sqlite import insert

from app.db.schema import settled_entries, translations
from app.errors import LlmUnreachableError, MessageNotFoundError, TranslationFailedError
from app.ids import SnowflakeGenerator
from app.services.configuration import get_session_configuration, resolve_model_for_use
from app.services.llm.chat import ChatMessage, strip_think
from app.services.llm.client import ChatDelta
from app.services.llm_registry import ChatClientFactory, open_chat_client

FALLBACK_TARGET_LANGUAGE: Final = "English"
"""The target language when no preferred language resolves at user or session level (D3).

The cache key uses the **effective** target, so a fallback translation is stored under this
value. `docs/plans/023.partner-translation/outcome.md` records the conflict with
`features.md`'s FEAT-013 note; the user chose this fallback.
"""


DisconnectProbe = Callable[[], Awaitable[bool]]
"""`() -> awaitable bool`; `True` means the client is gone (D4).

Declared here, not imported, so this module never sees `fastapi`. The route binds it to
`request.is_disconnected`; tests pass a file-local async function.
"""


@dataclass(frozen=True)
class TranslationResult:
    """One translation as the service returns it — `models/translation.py` builds from these.

    `cached` is `True` when the answer came from the `translations` table with no model call,
    and `False` when this call produced the text (whether or not a row was then written).
    """

    message_id: int
    target_language: str
    text: str
    cached: bool


@dataclass(frozen=True)
class _EligibleRow:
    """The three columns the flow needs from an eligible row (D6): its id, session and text."""

    id: int
    session_id: int
    text: str


def get_cached_translation(
    connection: Connection,
    user_id: int,
    message_id: int,
    target_language: str,
) -> str | None:
    """The cached text for exactly `(message_id, target_language)`, owner-scoped, else `None`.

    Reads only: writes nothing and leaves no transaction open. A row belonging to another user
    is invisible (R5).
    """
    with _reading(connection):
        row = connection.execute(
            select(translations.c.text).where(
                translations.c.user_id == user_id,
                translations.c.message_id == message_id,
                translations.c.target_language == target_language,
            )
        ).first()
    if row is None:
        return None
    cached: str = row.text
    return cached


async def translate_message(
    engine: Engine,
    generator: SnowflakeGenerator,
    user_id: int,
    message_id: int,
    timeout_seconds: float,
    client_factory: ChatClientFactory,
    is_disconnected: DisconnectProbe,
) -> TranslationResult:
    """Translate one settled partner row into the session's preferred language (D8's phases).

    Raises `MessageNotFoundError` when the row is not an eligible row (D6: unknown, another
    user's, a zone row, a buried row, a settled turn or decision — all indistinguishable).
    017's and `open_chat_client`'s errors propagate unchanged; only an `LlmUnreachableError` or
    an empty stripped result becomes `TranslationFailedError` (D5). Logs one line per outcome,
    ids, booleans, codes and durations only.
    """
    started = time.monotonic()

    # Phase 1 — one short-lived read connection, closed before the provider call (D8).
    with engine.connect() as connection:
        row = _read_eligible_row(connection, user_id, message_id)
        resolved = get_session_configuration(connection, user_id, row.session_id).preferred_language.value
        target_language = resolved if resolved is not None else FALLBACK_TARGET_LANGUAGE
        hit = get_cached_translation(connection, user_id, row.id, target_language)
        if hit is not None:
            # A hit answers here: no model resolution, no client, no call (D8).
            _log_outcome(
                row.id, cached=True, written=True, elapsed_ms=int((time.monotonic() - started) * 1000)
            )
            return TranslationResult(
                message_id=row.id, target_language=target_language, text=hit, cached=True
            )
        enabled_model = resolve_model_for_use(connection, user_id, row.session_id)
        client = open_chat_client(connection, enabled_model, timeout_seconds, client_factory)

    # Phase 2 — no connection held (D8); no tools (D2).
    try:
        joined = await _join_content(
            client.chat_stream(enabled_model.model_name, _translation_messages(target_language, row.text), [])
        )
    except LlmUnreachableError as error:
        _log_failure(row.id, int((time.monotonic() - started) * 1000))
        raise TranslationFailedError(
            row.id, "Translation failed: the model server could not be reached."
        ) from error
    text = strip_think(joined)
    if not text.strip():
        _log_failure(row.id, int((time.monotonic() - started) * 1000))
        raise TranslationFailedError(row.id, "Translation failed: the model returned no text.")

    # Phase 3 — the probe once, then one short write transaction (D4, D9). Nothing is cached on
    # a disconnect, and the produced text is returned either way.
    written = False
    if not await is_disconnected():
        with engine.connect() as connection:
            written = _write_cache(
                connection, generator, user_id, row.id, target_language, text, row.text
            )
    _log_outcome(
        row.id, cached=False, written=written, elapsed_ms=int((time.monotonic() - started) * 1000)
    )
    return TranslationResult(message_id=row.id, target_language=target_language, text=text, cached=False)


def _read_eligible_row(connection: Connection, user_id: int, message_id: int) -> _EligibleRow:
    """The caller's settled `kind='partner'` row, through `settled_entries` (R11), else raise.

    Owner scope rides in the same statement (R5); no row raises `MessageNotFoundError`. Writes
    nothing and leaves no transaction open.
    """
    columns = settled_entries.selected_columns
    with _reading(connection):
        row = connection.execute(
            settled_entries.where(
                columns.id == message_id,
                columns.user_id == user_id,
                columns.kind == "partner",
            )
        ).first()
    if row is None:
        # D6: unknown, foreign, a zone row, a buried row, a turn or a decision — one answer (R5).
        raise MessageNotFoundError()
    return _EligibleRow(id=row.id, session_id=row.session_id, text=row.text)


def _translation_messages(target_language: str, source_text: str) -> list[ChatMessage]:
    """Exactly two messages: the `system` instruction naming `target_language`, then the row's
    text verbatim as `user` (`002.context.md` holds the system literal)."""
    return [
        ChatMessage(
            role="system",
            content=(
                f"Translate the user's message into {target_language}. Keep its meaning, tone, "
                "formatting and line breaks. Reply with the translation only — no notes, no "
                "commentary, no quotation marks."
            ),
        ),
        ChatMessage(role="user", content=source_text),
    ]


async def _join_content(deltas: AsyncIterator[ChatDelta]) -> str:
    """The `content` of every delta concatenated in arrival order; the iterator is always closed.

    `reasoning` and `tool_calls` are ignored (D2). An `LlmUnreachableError` raised by the
    iterator propagates to the caller, which maps it (D5).
    """
    pieces: list[str] = []
    try:
        async for delta in deltas:
            if delta.content is not None:
                pieces.append(delta.content)
    finally:
        # 021 `005`'s closing guarantee: `AsyncIterator` declares no `aclose`, so ask the object.
        aclose = getattr(deltas, "aclose", None)
        if aclose is not None:
            await aclose()
    return "".join(pieces)


def _write_cache(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    message_id: int,
    target_language: str,
    text: str,
    source_text: str,
) -> bool:
    """Insert the cache row in one short transaction behind D9's guard; `True` when a row landed.

    Writes only while the message is still the caller's settled partner row **and** its current
    text equals `source_text`; the insert ignores a conflict on the unique pair (D8). Returns
    `False` when the guard refused or the conflict swallowed the insert — the caller logs that
    as `written=false`.
    """
    columns = settled_entries.selected_columns
    with connection.begin():
        current = connection.execute(
            settled_entries.where(
                columns.id == message_id,
                columns.user_id == user_id,
                columns.kind == "partner",
            )
        ).first()
        if current is None or current.text != source_text:
            # D9: the row went away or was edited during the call — a cache row would be stale.
            return False
        result = connection.execute(
            insert(translations)
            .values(
                id=generator.next_id(),
                user_id=user_id,
                message_id=message_id,
                target_language=target_language,
                text=text,
                created_at=_now_text(),
            )
            .on_conflict_do_nothing(index_elements=["message_id", "target_language"])
        )
    return result.rowcount == 1


def _log_outcome(message_id: int, *, cached: bool, written: bool, elapsed_ms: int) -> None:
    """`translate cached=<bool> message=<id> ms=<n>`, plus ` written=false` on a skipped write.

    A cache hit passes `written=True` and gets no suffix. Ids are decimal strings; no text
    (`deployment.md`).
    """
    logger.info(
        "translate cached={} message={} ms={}{}",
        "true" if cached else "false",
        str(message_id),
        elapsed_ms,
        "" if written else " written=false",
    )


def _log_failure(message_id: int, elapsed_ms: int) -> None:
    """`translate failed message=<id> code=translation_failed ms=<n>` — no cause text, no body."""
    logger.warning(
        "translate failed message={} code=translation_failed ms={}", str(message_id), elapsed_ms
    )


def _now_text() -> str:
    """Now as the fixed-width UTC ISO-8601 text the other services write to `created_at`."""
    return datetime.now(UTC).isoformat(timespec="microseconds")


@contextmanager
def _reading(connection: Connection) -> Iterator[None]:
    """A read on a Core connection autobegins; end it again when the caller had none open."""
    opened_here = not connection.in_transaction()
    try:
        yield
    finally:
        if opened_here and connection.in_transaction():
            connection.rollback()
