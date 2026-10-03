"""Tests for the SSE harness in `app/services/llm/frames.py` — feature 019, step 002.

Every expected value comes from `docs/plans/019.streaming-transport-and-stop/
002.sse-harness.md` (Interface intent + Definition of done), `002.context.md` and the
feature `context.md` (**D3**-**D7**, "Test conventions"). Expected wire bytes are written
out literally from step 001's worked examples (D2: `data: ` + compact JSON with `event`
first + `\\n\\n`, ids as decimal strings, missing `detail` -> `{}`), never produced by
calling the encoder.

Bindings come from `status.md` `## Skeleton`, Step 002:

- `frame_stream(request: DisconnectProbe, source: AsyncIterator[Frame],
  on_partial: Callable[[str], None]) -> AsyncGenerator[str, None]`
- `sse_response(request, source, on_partial) -> StreamingResponse`
- `own_connection_persister(engine, generator, user_id, session_id) -> Callable[[str], None]`

No async plugin is installed: async code runs under `asyncio.run(...)` from sync tests,
and every wait is bounded with `asyncio.wait_for`. Fake sources are file-local async
generators that record entry to their own `finally` (the observable proof that the
source was closed). Each test name ends `__S019_002_DoD<n>`.
"""

import asyncio
import json
from collections.abc import AsyncGenerator, Callable
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select

from app.db import schema
from app.errors import LlmUnreachableError
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services.llm.frames import (
    AcceptedFrame,
    DoneFrame,
    ErrorFrame,
    Frame,
    TokenFrame,
    frame_stream,
    own_connection_persister,
    sse_response,
)
from app.services.messages import append_message
from app.services.passwords import hash_password

#: Upper bound for any single await in these tests, so a broken harness fails, never hangs.
TIMEOUT = 5.0

ACCEPTED_ID = 7_250_000_000_000_000_001
DONE_ID = 7_250_000_000_000_000_002


# --- wire texts, written out from step 001's examples (D2) -------------------------------


def _token_wire(text: str) -> str:
    """`data: {"event":"token","text":<text>}\\n\\n` for plain ASCII text without escapes."""
    return 'data: {"event":"token","text":"' + text + '"}\n\n'


ACCEPTED_WIRE = 'data: {"event":"accepted","message_id":"7250000000000000001"}\n\n'
DONE_WIRE = 'data: {"event":"done","message_id":"7250000000000000002"}\n\n'

UNREACHABLE_EXCEPTION_MESSAGE = "The reply could not be completed."
UNREACHABLE_EXHAUSTION_MESSAGE = "The reply ended before it was complete."


def _parse_wire(chunk: str) -> dict[str, Any]:
    """Parse one wire frame `data: <json>\\n\\n` into its JSON object."""
    assert chunk.startswith("data: "), chunk
    assert chunk.endswith("\n\n"), chunk
    parsed = json.loads(chunk[len("data: ") : -2])
    assert isinstance(parsed, dict)
    return parsed


# --- fakes ------------------------------------------------------------------------------


class FakeRequest:
    """Stands in for the request: only `is_disconnected()` exists (D3)."""

    def __init__(self, gone: bool = False) -> None:
        self.gone = gone

    async def is_disconnected(self) -> bool:
        return self.gone


class SourceRecord:
    """What a fake source observed about itself."""

    def __init__(self) -> None:
        self.finally_ran = False
        self.pulled_after_terminal = False


class Recorder:
    """A synchronous `on_partial` that records each call, optionally into a shared log."""

    def __init__(self, log: list[tuple[str, str]] | None = None) -> None:
        self.calls: list[str] = []
        self._log = log

    def __call__(self, text: str) -> None:
        self.calls.append(text)
        if self._log is not None:
            self._log.append(("partial", text))


async def _frames_source(record: SourceRecord, frames: list[Frame]) -> AsyncGenerator[Frame, None]:
    """Yields `frames` in order, recording entry to its `finally`."""
    try:
        for frame in frames:
            yield frame
    finally:
        record.finally_ran = True


async def _raising_source(
    record: SourceRecord, frames: list[Frame], error: BaseException
) -> AsyncGenerator[Frame, None]:
    """Yields `frames`, then raises `error`."""
    try:
        for frame in frames:
            yield frame
        raise error
    finally:
        record.finally_ran = True


async def _terminal_then_more_source(
    record: SourceRecord, before: list[Frame], terminal: Frame, after: Frame
) -> AsyncGenerator[Frame, None]:
    """Yields `before`, the terminal frame, then (only if pulled again) `after`."""
    try:
        for frame in before:
            yield frame
        yield terminal
        record.pulled_after_terminal = True
        yield after
    finally:
        record.finally_ran = True


async def _blocking_source(record: SourceRecord, frames: list[Frame]) -> AsyncGenerator[Frame, None]:
    """Yields `frames`, then blocks forever — a model still generating."""
    try:
        for frame in frames:
            yield frame
        await asyncio.Event().wait()
        yield TokenFrame(text="never reached")
    finally:
        record.finally_ran = True


# --- driving helpers --------------------------------------------------------------------

_END = object()


async def _next_or_end(stream: AsyncGenerator[str, None]) -> object:
    try:
        return await stream.__anext__()
    except StopAsyncIteration:
        return _END


async def _step(stream: AsyncGenerator[str, None]) -> object:
    return await asyncio.wait_for(_next_or_end(stream), TIMEOUT)


def _drain(
    source: AsyncGenerator[Frame, None],
    on_partial: Callable[[str], None],
    log: list[tuple[str, str]] | None = None,
) -> list[str]:
    """Run `frame_stream` to its end with a never-disconnecting request; return every chunk."""

    async def main() -> list[str]:
        stream = frame_stream(FakeRequest(), source, on_partial)
        chunks: list[str] = []
        while True:
            item = await _step(stream)
            if item is _END:
                return chunks
            assert isinstance(item, str)
            chunks.append(item)
            if log is not None:
                log.append(("frame", item))

    return asyncio.run(main())


def _run_poll_disconnect(
    pre: list[Frame], on_partial: Callable[[str], None]
) -> tuple[list[str], object, SourceRecord]:
    """Pull `len(pre)` chunks, flip the request to disconnected, pull once more.

    The source would go on yielding a further token and a `done` after `pre`.
    Returns (chunks before the flip, the item after the flip, the source record).
    """
    record = SourceRecord()
    frames: list[Frame] = [*pre, TokenFrame(text="after the drop"), DoneFrame(message_id=DONE_ID)]

    async def main() -> tuple[list[str], object]:
        request = FakeRequest()
        stream = frame_stream(request, _frames_source(record, frames), on_partial)
        chunks: list[str] = []
        for _ in pre:
            item = await _step(stream)
            assert isinstance(item, str), item
            chunks.append(item)
        request.gone = True
        after = await _step(stream)
        if after is not _END:
            await asyncio.wait_for(stream.aclose(), TIMEOUT)
        return chunks, after

    chunks, after = asyncio.run(main())
    return chunks, after, record


def _run_close_disconnect(pre: list[Frame], on_partial: Callable[[str], None]) -> tuple[list[str], SourceRecord]:
    """Pull `len(pre)` chunks, then `aclose()` the stream itself, as a server does."""
    record = SourceRecord()
    frames: list[Frame] = [*pre, TokenFrame(text="after the drop"), DoneFrame(message_id=DONE_ID)]

    async def main() -> list[str]:
        stream = frame_stream(FakeRequest(), _frames_source(record, frames), on_partial)
        chunks: list[str] = []
        for _ in pre:
            item = await _step(stream)
            assert isinstance(item, str), item
            chunks.append(item)
        await asyncio.wait_for(stream.aclose(), TIMEOUT)
        return chunks

    return asyncio.run(main()), record


def _run_cancel_disconnect(
    pre: list[Frame], on_partial: Callable[[str], None]
) -> tuple[list[str], bool, SourceRecord]:
    """Consume `frame_stream` in a task over a source that blocks after `pre`; cancel it.

    Returns (chunks received, whether the task ended cancelled, the source record).
    """
    record = SourceRecord()

    async def main() -> tuple[list[str], bool]:
        chunks: list[str] = []
        received_all = asyncio.Event()

        async def consume() -> None:
            async for chunk in frame_stream(FakeRequest(), _blocking_source(record, pre), on_partial):
                chunks.append(chunk)
                if len(chunks) == len(pre):
                    received_all.set()

        task = asyncio.create_task(consume())
        await asyncio.wait_for(received_all.wait(), TIMEOUT)
        # Let the consumer go back into the harness, which is now awaiting the blocked source.
        await asyncio.sleep(0.05)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=TIMEOUT)
        assert task in done, "the cancelled consumer did not finish"
        return chunks, task.cancelled()

    chunks, cancelled = asyncio.run(main())
    return chunks, cancelled, record


# --- DoD-1 / DoD-2: the response through a throwaway FastAPI route ------------------------


def _success_frames() -> list[Frame]:
    return [
        AcceptedFrame(message_id=ACCEPTED_ID),
        TokenFrame(text="Hel"),
        TokenFrame(text="lo"),
        DoneFrame(message_id=DONE_ID),
    ]


EXPECTED_SUCCESS_BODY = ACCEPTED_WIRE + _token_wire("Hel") + _token_wire("lo") + DONE_WIRE


def _throwaway_app(recorder: Recorder, record: SourceRecord) -> FastAPI:
    app = FastAPI()

    @app.post("/stream")
    async def stream(request: Request) -> StreamingResponse:
        return sse_response(request, _frames_source(record, _success_frames()), recorder)

    return app


def test_the_response_is_an_unbuffered_event_stream_of_the_four_frames__S019_002_DoD1() -> None:
    """DoD-1 — 200; `text/event-stream`; `x-accel-buffering: no`; the body is exactly the
    four frames' wire texts concatenated (D3, `deployment.md`)."""
    recorder = Recorder()
    client = TestClient(_throwaway_app(recorder, SourceRecord()))

    response = client.post("/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert response.content == EXPECTED_SUCCESS_BODY.encode("utf-8")


def test_the_success_path_never_calls_on_partial__S019_002_DoD2() -> None:
    """DoD-2 — a stream that passes `done` persists nothing through the harness (D4)."""
    recorder = Recorder()
    client = TestClient(_throwaway_app(recorder, SourceRecord()))

    response = client.post("/stream")

    assert response.status_code == 200
    assert response.content == EXPECTED_SUCCESS_BODY.encode("utf-8")
    assert recorder.calls == []


def test_the_success_path_never_calls_on_partial_when_driven_directly__S019_002_DoD2() -> None:
    """DoD-2 — the same success source drained through `frame_stream`: no `on_partial`."""
    recorder = Recorder()

    chunks = _drain(_frames_source(SourceRecord(), _success_frames()), recorder)

    assert "".join(chunks) == EXPECTED_SUCCESS_BODY
    assert recorder.calls == []


# --- DoD-3: a DomainError ends with its error frame, after the persist --------------------


def test_a_domain_error_ends_with_one_error_frame_after_the_tokens__S019_002_DoD3() -> None:
    """DoD-3 — two token frames, then exactly one `error` frame `llm_unreachable` / "down",
    and nothing after it (D4, termination table)."""
    record = SourceRecord()
    source = _raising_source(
        record,
        [TokenFrame(text="Partial "), TokenFrame(text="answer")],
        LlmUnreachableError("down"),
    )

    chunks = _drain(source, Recorder())

    assert len(chunks) == 3
    assert chunks[0] == _token_wire("Partial ")
    assert chunks[1] == _token_wire("answer")
    assert _parse_wire(chunks[2]) == {
        "event": "error",
        "code": "llm_unreachable",
        "message": "down",
        "detail": {},
    }


def test_a_domain_error_persists_once_before_the_error_frame__S019_002_DoD3() -> None:
    """DoD-3 — `on_partial` is called once with "Partial answer", and that call happens
    before the error frame is yielded (D4: persist before the error frame)."""
    log: list[tuple[str, str]] = []
    recorder = Recorder(log)
    source = _raising_source(
        SourceRecord(),
        [TokenFrame(text="Partial "), TokenFrame(text="answer")],
        LlmUnreachableError("down"),
    )

    chunks = _drain(source, recorder, log)

    assert recorder.calls == ["Partial answer"]
    error_chunk = chunks[-1]
    assert _parse_wire(error_chunk)["event"] == "error"
    partial_index = log.index(("partial", "Partial answer"))
    error_index = log.index(("frame", error_chunk))
    assert partial_index < error_index


# --- DoD-4: a non-domain exception -> fixed llm_unreachable, no leaked text ---------------


def test_a_plain_exception_ends_with_the_fixed_unreachable_frame__S019_002_DoD4() -> None:
    """DoD-4 — final frame `llm_unreachable`, message exactly "The reply could not be
    completed.", detail `{}`; the exception text appears in no frame; `on_partial` gets the
    token's text (D5)."""
    recorder = Recorder()
    source = _raising_source(
        SourceRecord(),
        [TokenFrame(text="Visible words")],
        RuntimeError("secret provider text"),
    )

    chunks = _drain(source, recorder)

    assert chunks[0] == _token_wire("Visible words")
    assert len(chunks) == 2
    assert _parse_wire(chunks[-1]) == {
        "event": "error",
        "code": "llm_unreachable",
        "message": UNREACHABLE_EXCEPTION_MESSAGE,
        "detail": {},
    }
    for chunk in chunks:
        assert "secret provider text" not in chunk
    assert recorder.calls == ["Visible words"]


# --- DoD-5: exhaustion without a terminal frame -> fixed llm_unreachable ------------------


def test_a_source_that_just_ends_gets_the_fixed_unreachable_frame__S019_002_DoD5() -> None:
    """DoD-5 — two tokens and then the source ends: a final `llm_unreachable` frame with
    message exactly "The reply ended before it was complete.", detail `{}`; `on_partial`
    gets the joined token text (D5)."""
    recorder = Recorder()
    source = _frames_source(SourceRecord(), [TokenFrame(text="Half "), TokenFrame(text="done")])

    chunks = _drain(source, recorder)

    assert chunks[:2] == [_token_wire("Half "), _token_wire("done")]
    assert len(chunks) == 3
    assert _parse_wire(chunks[-1]) == {
        "event": "error",
        "code": "llm_unreachable",
        "message": UNREACHABLE_EXHAUSTION_MESSAGE,
        "detail": {},
    }
    assert recorder.calls == ["Half done"]


# --- DoD-6: a terminal frame from the source ends the stream ------------------------------

MODEL_ERROR = ErrorFrame(
    code="model_not_enabled",
    message="That model is not enabled.",
    detail={"model_id": "7250000000000000009"},
)
MODEL_ERROR_WIRE = (
    'data: {"event":"error","code":"model_not_enabled","message":"That model is not enabled.",'
    '"detail":{"model_id":"7250000000000000009"}}\n\n'
)


def test_a_source_error_frame_is_passed_verbatim_as_the_last_frame__S019_002_DoD6() -> None:
    """DoD-6 — the source's own `error` frame is the last frame, verbatim; the source is
    never pulled again; `on_partial` gets the token text (D4)."""
    record = SourceRecord()
    recorder = Recorder()
    source = _terminal_then_more_source(
        record, [TokenFrame(text="Before the error")], MODEL_ERROR, TokenFrame(text="must not appear")
    )

    chunks = _drain(source, recorder)

    assert chunks == [_token_wire("Before the error"), MODEL_ERROR_WIRE]
    assert record.pulled_after_terminal is False
    assert recorder.calls == ["Before the error"]


def test_nothing_follows_a_done_frame__S019_002_DoD6() -> None:
    """DoD-6 — a source that yields `done` and then a further token: nothing after `done`,
    and the source is not pulled past it (D4)."""
    record = SourceRecord()
    recorder = Recorder()
    source = _terminal_then_more_source(
        record,
        [AcceptedFrame(message_id=ACCEPTED_ID), TokenFrame(text="Hel")],
        DoneFrame(message_id=DONE_ID),
        TokenFrame(text="must not appear"),
    )

    chunks = _drain(source, recorder)

    assert chunks == [ACCEPTED_WIRE, _token_wire("Hel"), DONE_WIRE]
    assert record.pulled_after_terminal is False
    assert recorder.calls == []


# --- DoD-7: disconnect by poll -------------------------------------------------------------


def test_disconnect_by_poll_stops_silently_and_persists__S019_002_DoD7() -> None:
    """DoD-7 — after two tokens `is_disconnected()` turns true: no further frame and no
    terminal frame; `on_partial` once with the two tokens' text; the source's `finally`
    ran (D6, US-132.AC-1, US-132.AC-2)."""
    recorder = Recorder()

    chunks, after, record = _run_poll_disconnect(
        [TokenFrame(text="First "), TokenFrame(text="second")], recorder
    )

    assert chunks == [_token_wire("First "), _token_wire("second")]
    assert after is _END
    assert recorder.calls == ["First second"]
    assert record.finally_ran is True


# --- DoD-8: disconnect by close ------------------------------------------------------------


def test_disconnect_by_close_persists_and_closes_the_source__S019_002_DoD8() -> None:
    """DoD-8 — two tokens, then the stream itself is `aclose()`d: `on_partial` once with the
    two tokens' text, and the source's `finally` ran (D6, US-132.AC-1, US-132.AC-2)."""
    recorder = Recorder()

    chunks, record = _run_close_disconnect([TokenFrame(text="First "), TokenFrame(text="second")], recorder)

    assert chunks == [_token_wire("First "), _token_wire("second")]
    assert recorder.calls == ["First second"]
    assert record.finally_ran is True


# --- DoD-9: disconnect by cancellation -----------------------------------------------------


def test_disconnect_by_cancellation_persists_closes_and_stays_cancelled__S019_002_DoD9() -> None:
    """DoD-9 — the source blocks after one token; the consuming task is cancelled:
    `on_partial` once with the token's text, the source's `finally` ran, and the task ends
    cancelled (the `CancelledError` is not swallowed) (D6, US-132.AC-1, US-132.AC-2)."""
    recorder = Recorder()

    chunks, cancelled, record = _run_cancel_disconnect([TokenFrame(text="Still thinking")], recorder)

    assert chunks == [_token_wire("Still thinking")]
    assert recorder.calls == ["Still thinking"]
    assert record.finally_ran is True
    assert cancelled is True


# --- DoD-10: a disconnect with nothing (or only whitespace) streamed persists nothing -----

_BLANK_CASES: dict[str, list[Frame]] = {
    "no_token": [AcceptedFrame(message_id=ACCEPTED_ID)],
    "whitespace_tokens": [
        AcceptedFrame(message_id=ACCEPTED_ID),
        TokenFrame(text="  "),
        TokenFrame(text="\n\t "),
    ],
}


@pytest.mark.parametrize("case", sorted(_BLANK_CASES))
def test_disconnect_by_poll_with_blank_text_persists_nothing__S019_002_DoD10(case: str) -> None:
    """DoD-10 — poll disconnect with no token / whitespace-only tokens: no `on_partial`
    (D4, consequence 4)."""
    recorder = Recorder()

    _run_poll_disconnect(_BLANK_CASES[case], recorder)

    assert recorder.calls == []


@pytest.mark.parametrize("case", sorted(_BLANK_CASES))
def test_disconnect_by_close_with_blank_text_persists_nothing__S019_002_DoD10(case: str) -> None:
    """DoD-10 — close disconnect with no token / whitespace-only tokens: no `on_partial`."""
    recorder = Recorder()

    _run_close_disconnect(_BLANK_CASES[case], recorder)

    assert recorder.calls == []


@pytest.mark.parametrize("case", sorted(_BLANK_CASES))
def test_disconnect_by_cancellation_with_blank_text_persists_nothing__S019_002_DoD10(case: str) -> None:
    """DoD-10 — cancellation disconnect with no token / whitespace-only tokens: no
    `on_partial`."""
    recorder = Recorder()

    _run_cancel_disconnect(_BLANK_CASES[case], recorder)

    assert recorder.calls == []


# --- DoD-11 / DoD-12: the own-connection persister against a real database ----------------

TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"
USER_ID = 9_402_001
CHARACTER_ID = 1_101
SESSION_ID = 5_101
#: An id that belongs to no session.
MISSING_SESSION_ID = 7_250_000_000_000_000_777


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the registry, one user, one character and one session."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
        connection.execute(
            schema.users.insert().values(
                id=USER_ID,
                username="harness_owner",
                password_hash=hash_password("a long enough password"),
                role=Role.ROLEPLAYER,
                is_enabled=True,
                rp_language=None,
                preferred_language=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )
        connection.execute(
            schema.characters.insert().values(
                id=CHARACTER_ID,
                user_id=USER_ID,
                name="Aria",
                sheet="",
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )
        connection.execute(
            schema.sessions.insert().values(
                id=SESSION_ID,
                user_id=USER_ID,
                character_id=CHARACTER_ID,
                setup_id=None,
                last_used_at=TIMESTAMP,
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    return SnowflakeGenerator(node_id=1)


def _zone_rows(engine: Engine, session_id: int) -> list[dict[str, Any]]:
    """The session's current zone through the `current_zone` selectable, id ascending."""
    statement = schema.current_zone.where(schema.messages.c.session_id == session_id).order_by(
        schema.messages.c.id
    )
    with engine.connect() as connection:
        return [dict(row._mapping) for row in connection.execute(statement)]


def _count_messages(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(schema.messages)).scalar_one())


def test_the_persister_writes_one_assistant_zone_row_on_its_own_connection__S019_002_DoD11(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-11 — called with "kept text", it leaves one current-zone row, role 'assistant',
    kind NULL, text "kept text", for that session; the caller supplies no connection (D7)."""
    persist = own_connection_persister(engine, generator, USER_ID, SESSION_ID)

    result = persist("kept text")

    assert result is None
    rows = _zone_rows(engine, SESSION_ID)
    assert len(rows) == 1
    (row,) = rows
    assert row["role"] == "assistant"
    assert row["kind"] is None
    assert row["text"] == "kept text"
    assert row["session_id"] == SESSION_ID
    assert row["user_id"] == USER_ID


def test_the_persister_swallows_a_missing_session_and_writes_nothing__S019_002_DoD11(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-11 — for a session that does not exist it returns normally and writes nothing
    (D7: any exception is logged and swallowed)."""
    persist = own_connection_persister(engine, generator, USER_ID, MISSING_SESSION_ID)

    persist("kept text")

    assert _count_messages(engine) == 0


def test_a_polled_disconnect_leaves_the_streamed_text_as_an_assistant_row__S019_002_DoD12(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-12 — end to end: a disconnect-by-poll stream wired to `own_connection_persister`
    for a real seeded session leaves exactly one new current-zone row, role 'assistant',
    holding the streamed text (D4, D7, US-132.AC-1)."""
    with engine.connect() as connection:
        committed = append_message(connection, generator, USER_ID, SESSION_ID, "Aria leans in.")
    before = _zone_rows(engine, SESSION_ID)
    assert [row["id"] for row in before] == [committed.id]

    persist = own_connection_persister(engine, generator, USER_ID, SESSION_ID)
    chunks, after, _ = _run_poll_disconnect(
        [AcceptedFrame(message_id=committed.id), TokenFrame(text="Half a "), TokenFrame(text="reply")],
        persist,
    )

    assert after is _END
    assert len(chunks) == 3
    rows = _zone_rows(engine, SESSION_ID)
    new_rows = [row for row in rows if row["id"] != committed.id]
    assert len(new_rows) == 1
    (row,) = new_rows
    assert row["role"] == "assistant"
    assert row["kind"] is None
    assert row["text"] == "Half a reply"
