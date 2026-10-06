"""Step 007 — the log sentinel sweep (DoD-1..DoD-9; DoD-10 is ``[manual/live]``).

Written from ``docs/plans/032.privacy-isolation-audit/007.log-sentinel-sweep.md`` (the
ten-item Definition of done **is** the specification), ``007.context.md`` (mechanics, the
step-001 dependency) and ``context.md`` (the citation mapping for logs). Bound to the
support module frozen by ``status.md`` ``## Skeleton`` -> "Step 002 — frozen interface".
Nothing here was derived from reading an implementation body.

Every item cites **US-084.AC-1**: operator-facing logs (console, supervisord, the log
file) are an administrative surface for the purpose of this audit (``context.md``
"Citation mapping for logs"), and the mechanism is ``docs/architecture/deployment.md``
"The redaction rule" — a forbidden list, an allowed list, and **no level exception**.

This is the only step that runs under the **real** ``configure_logging``
(``audit_world(..., real_logging=True)``). The log file is pointed at ``tmp_path`` and
``sys.stderr`` is replaced by an in-memory stream before the application is built, so the
project's ``data/logs/`` is never written and ``backend/.env`` is never read.

Why the stderr redirect lives in the test body, not in the fixture
=================================================================

pytest's capture plugin **re-installs its own ``sys.stderr`` when the call phase starts**:
global capture is suspended around fixture setup and resumed for the call, and resuming
reassigns ``sys.stderr``. A redirect performed during *fixture setup* is therefore silently
clobbered the moment the test body begins, and the real ``configure_logging`` — which runs
inside ``audit_world`` in the **body** — would bind its console sink to pytest's stream
instead of this module's ``StringIO``. The console witness would then observe nothing and
every "no sentinel in the console text" clause would pass vacuously.
So ``harness`` only prepares the stream, and each test enters
``harness.bound_console()`` as the **outermost** context manager of its body: the redirect
is live at the instant ``configure_logging`` runs and is undone before the test returns.
``sys.stderr`` is never closed, and the autouse sink fixture re-binds loguru to the
**real** stderr on both sides of every test, so no test ends holding the ``StringIO``.

The two witnesses, and why the distinction matters
==================================================

Each clause is swept against **two** independent witnesses, and a failure message says
which one matched, because the two have different causes and different owners:

1. **The capture sink** (``captured_logs``) — swept over each record's ``message``,
   ``repr(extra)`` and ``exception_text`` (the exception's type and value). These are
   exactly the three fields the DoD names ("message, extra or exception text"). A hit
   here means **a ``logger.*`` call or an exception-formatting site wrote content**: a
   genuine leak finding, routed to step 007's own fix-allowance.
   The record's ``formatted`` field is deliberately **not** swept: it is rendered by the
   *capture sink's* own loguru options (``captured_logs`` adds its sink with loguru's
   default ``diagnose``/``backtrace``), not by the application, so a frame local showing
   up there would say nothing about the application's sinks. Those sinks' options are
   step 001 DoD-4's subject and are witnessed below instead.
2. **The real console sink's text** (the ``StringIO`` that replaced ``sys.stderr``, at
   ``DEBUG``) — plus the real log file. A hit here that sits inside a rendered traceback's
   frame locals is **step 001's unimplemented ``diagnose=False``** (expected red at the
   red gate for DoD-3..DoD-6, and green at verify); a hit anywhere else is a log-call
   leak. Both possibilities are named in the failure message, with the surrounding text
   quoted so the gate and the verifier can tell them apart.

Errors raised by the application may legitimately carry a sentinel in the **HTTP
response** to the caller who sent it (a 422 echoing their own input, for instance).
**Only log records are asserted here** (``007.context.md``). There is no AST scan of
``logger.*`` call sites — that was a user decision; the proof is dynamic.

Three world builds (DoD-1, DoD-2+DoD-6, DoD-3+DoD-4+DoD-5+DoD-7+DoD-8) plus one
build-free test (DoD-9), following steps 003..006's thin-fixture-and-loop-inside shape:
this is the most expensive world in the feature (real logging plus ~50 driven routes).
No fake seam is installed here — ``audit_world`` owns all four override keys atomically;
this module only re-scripts through ``world.fakes``.
"""

from __future__ import annotations

import io
import json
import logging
import sys
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import httpx
import pytest
from fastapi.testclient import TestClient
from loguru import logger
from sqlalchemy import Engine

from app.config import Settings
from app.errors import LlmUnreachableError
from app.logging import configure_logging
from app.services.llm.client import ProbeOutcome, ProbeResult
from app.services.llm_registry import LlmClientFactory
from tests.privacy_audit_support import (
    ADMIN_SERVERS_PATH,
    BOOTSTRAP_PATH,
    COMPOSE_TIMEOUT_SECONDS,
    ENUMERATED_ROUTES,
    FAKE_SERVER_BASE_URL,
    LOGIN_PATH,
    MEMO_SEARCH_NAME,
    SESSION_SEARCH_NAME,
    WEB_SEARCH_NAME,
    AuditWorld,
    EnumeratedRoute,
    LogCapture,
    ScriptedProbeFactory,
    assert_empty_detail,
    assert_envelope,
    audit_world,
    captured_logs,
    fill_path,
    registered_paths_by_operation,
    restored_logging_state,
    text_round,
    tool_call_round,
)

# --------------------------------------------------------------------------------------
# Per-test tokens. The checked needle set is "every sentinel of every user" from the
# registry **plus** these failure sentinels (``007.context.md``). Each is a single
# lowercase alphanumeric token, like the registry's, so FTS5 and a plain substring search
# agree; the ``sntl7`` prefix keeps them distinct from (and never a substring of) the
# registry's ``sntl<a|b>…`` tokens.
# --------------------------------------------------------------------------------------

SENTINEL_COMPOSE_DOMAIN: Final[str] = "sntl7composedomain"
SENTINEL_COMPOSE_PLAIN: Final[str] = "sntl7composeplain"
SENTINEL_TOOL_EMBED: Final[str] = "sntl7toolembed"
SENTINEL_TOOL_WEB: Final[str] = "sntl7toolweb"
SENTINEL_TOOL_QUERY: Final[str] = "sntl7toolquery"
SENTINEL_TRANSLATION_HANDLED: Final[str] = "sntl7translationhandled"
SENTINEL_TRANSLATION_UNHANDLED: Final[str] = "sntl7translationunhandled"
SENTINEL_LOGIN_PASSWORD: Final[str] = "sntl7loginpassword"
SENTINEL_PROBE_API_KEY: Final[str] = "sntl7probeapikey"
SENTINEL_IMPORT_PAYLOAD: Final[str] = "sntl7importpayload"
SENTINEL_INVALID_BODY: Final[str] = "sntl7invalidbody"

FAILURE_SENTINELS: Final[tuple[str, ...]] = (
    SENTINEL_COMPOSE_DOMAIN,
    SENTINEL_COMPOSE_PLAIN,
    SENTINEL_TOOL_EMBED,
    SENTINEL_TOOL_WEB,
    SENTINEL_TOOL_QUERY,
    SENTINEL_TRANSLATION_HANDLED,
    SENTINEL_TRANSLATION_UNHANDLED,
    SENTINEL_LOGIN_PASSWORD,
    SENTINEL_PROBE_API_KEY,
    SENTINEL_IMPORT_PAYLOAD,
    SENTINEL_INVALID_BODY,
)

#: Harmless filler. Never asserted absent — it only keeps driven bodies non-blank.
PROBE: Final[str] = "s032007probe"

#: The environment variable the DoD-7 server's ``api_key_ref`` points at. Deliberately
#: not ``RPHELPER_``-prefixed, so ``conftest.py``'s isolation fixture leaves it alone.
PROBE_KEY_VARIABLE: Final[str] = "S032_007_PROBE_API_KEY"
PROBE_KEY_POINTER: Final[str] = "$" + PROBE_KEY_VARIABLE

CONTEXT_WINDOW: Final[int] = 160


# --------------------------------------------------------------------------------------
# Fixtures. Decision 9: the state hazard is severe here, because this is the one step
# using real logging. Every logger this module touches has its ``level``, ``handlers``,
# ``propagate`` **and** ``.filters`` snapshotted and restored (``restored_logging_state``
# / ``captured_logs``), every capture sink is removed by id, and loguru is reset to a
# single real-stderr sink on both sides of every test.
# --------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _loguru_sinks() -> Iterator[None]:
    """Reset loguru's sinks around every test, as ``tests/test_logging.py`` does.

    ``app/main.py`` runs ``create_app()`` at **import**, so the real
    ``configure_logging`` has already added sinks (console plus the operator's own log
    file) before any fixture runs. Those are dropped here and one plain stderr sink is
    put back afterwards, so neither this module's ``tmp_path`` file sink nor its
    in-memory console stream outlives the test.
    """
    real_stderr = sys.stderr
    logger.remove()
    logger.add(real_stderr)
    try:
        yield
    finally:
        logger.remove()
        logger.add(real_stderr)


@dataclass
class LogHarness:
    """The per-test settings/engine pair plus the two real-sink witnesses."""

    settings: Settings
    engine: Engine
    console: io.StringIO
    log_file: Path

    @contextmanager
    def bound_console(self) -> Iterator[None]:
        """Redirect ``sys.stderr`` to :attr:`console` for the duration of the test body.

        This must run in the **call phase** (see the module docstring): pytest's capture
        plugin re-installs its own ``sys.stderr`` when the call phase starts, so a redirect
        installed during fixture setup is gone by the time ``configure_logging`` binds
        loguru's console sink, leaving the console witness unarmed. Entering this as the
        outermost context manager of the body makes the stream current at ``add()`` time
        and restores the previous one before the test returns. The ``StringIO`` is never
        closed, so a sink that outlives the block cannot raise.
        """
        previous = sys.stderr
        sys.stderr = self.console
        try:
            yield
        finally:
            sys.stderr = previous

    def console_text(self) -> str:
        return self.console.getvalue()

    def log_file_text(self) -> str:
        """The file sink's text. ``logger.remove()`` must have run first (loguru buffers)."""
        if not self.log_file.exists():
            return ""
        return self.log_file.read_text(encoding="utf-8", errors="replace")


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> Iterator[LogHarness]:
    """Point every sink at ``tmp_path``/memory, then build ``conftest.py``'s pair.

    The two ``getfixturevalue`` calls are deliberate: ``db_settings`` reads the
    environment, so ``RPHELPER_LOG_FILE_PATH`` must already be set when it runs. Nothing
    constructs ``Settings`` from the real env file, and the project's ``data/logs/`` is
    never opened — asserted below rather than assumed.

    The in-memory console stream is only *prepared* here. The ``sys.stderr`` redirect
    itself is deliberately **not** installed in this fixture: pytest reassigns
    ``sys.stderr`` when the call phase begins, which would discard it before
    ``configure_logging`` runs. Each test enters :meth:`LogHarness.bound_console` instead.
    """
    log_file = tmp_path / "logs" / "audit-007.log"
    monkeypatch.setenv("RPHELPER_LOG_FILE_PATH", str(log_file))
    monkeypatch.setenv("RPHELPER_LOG_FILE_LEVEL", "DEBUG")
    # DoD-1's words: "the real ``configure_logging`` (console at ``DEBUG``)".
    monkeypatch.setenv("RPHELPER_LOG_CONSOLE_LEVEL", "DEBUG")

    console = io.StringIO()

    settings: Settings = request.getfixturevalue("db_settings")
    engine: Engine = request.getfixturevalue("db_engine")

    assert settings.log_file_path == log_file, settings.log_file_path
    assert str(tmp_path) in str(settings.log_file_path), settings.log_file_path
    yield LogHarness(settings=settings, engine=engine, console=console, log_file=log_file)


# --------------------------------------------------------------------------------------
# The sweep itself
# --------------------------------------------------------------------------------------


def _needles(world: AuditWorld) -> tuple[str, ...]:
    """Every sentinel of every user, plus this module's failure sentinels."""
    return (*world.sentinels.all_sentinels(), *FAILURE_SENTINELS)


def _capture_problems(capture: LogCapture, needles: Sequence[str], *, clause: str) -> list[str]:
    """Sentinels in a record's message, extra or exception text — a genuine leak finding.

    Only the three fields the DoD names are swept; see the module docstring for why the
    sink's own ``formatted`` rendering is not one of them.
    """
    problems: list[str] = []
    for record in capture.records:
        fields: list[tuple[str, str]] = [("message", record.message), ("extra", record.extra_repr)]
        if record.exception_text is not None:
            fields.append(("exception", record.exception_text))
        for name, text in fields:
            for needle in needles:
                if needle in text:
                    problems.append(
                        f"{clause}: LOG LEAK FINDING (a logger.* call or an exception-formatting site "
                        f"wrote content) — sentinel={needle} field={name} level={record.level} "
                        f"logger={record.name} text={text[:CONTEXT_WINDOW * 2]!r}"
                    )
    return problems


def _text_problems(text: str, needles: Sequence[str], *, clause: str, witness: str) -> list[str]:
    """Sentinels in a real sink's rendered text (console or file).

    A hit inside a rendered traceback's frame locals is step 001's unimplemented
    ``diagnose=False`` — expected red at the red gate, and it must be green at verify. A
    hit anywhere else is a log-call leak owned by step 007. The surrounding text is
    quoted so the two can be told apart without re-running anything.
    """
    problems: list[str] = []
    for needle in needles:
        index = text.find(needle)
        if index < 0:
            continue
        start = max(0, index - CONTEXT_WINDOW)
        problems.append(
            f"{clause}: {witness} carries sentinel={needle}. If the quoted context is a traceback frame "
            f"local, this is step 001's unimplemented diagnose=False (expected at the red gate, must be "
            f"GREEN at verify); otherwise it is a log-call leak owned by step 007. "
            f"context={text[start : index + CONTEXT_WINDOW]!r}"
        )
    return problems


def _control(capture: LogCapture, harness: LogHarness, token: str) -> None:
    """Prove both witnesses are armed, so no absence below can pass vacuously.

    One loguru record and one stdlib record (which reaches loguru only through the
    ``InterceptHandler`` the real ``configure_logging`` installs on the root logger) must
    appear in the capture sink **and** in the real console sink's text.
    """
    loguru_marker = f"s032007-loguru-control-{token}"
    stdlib_marker = f"s032007-stdlib-control-{token}"
    logger.info("audit log capture control {}", loguru_marker)
    logging.getLogger("uvicorn.error").warning("audit stdlib bridge control %s", stdlib_marker)

    captured = "\n".join(capture.texts)
    assert loguru_marker in captured, "the level-0 capture sink recorded no loguru record"
    assert stdlib_marker in captured, "no stdlib record reached loguru: the InterceptHandler bridge is not armed"
    console = harness.console_text()
    assert loguru_marker in console, "the real console sink wrote nothing: this witness is not armed"
    assert stdlib_marker in console, "no stdlib record reached the real console sink"


def _compose_response(client: TestClient, session_id: str, body: Any) -> httpx.Response:
    """One compose POST on a worker thread with a bound — compose answers an SSE stream."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, f"/api/sessions/{session_id}/zone/compose", json=body)
        return future.result(timeout=COMPOSE_TIMEOUT_SECONDS)


def _frames(body: str) -> list[dict[str, Any]]:
    """Parse an SSE body into its ``data:`` frames."""
    frames: list[dict[str, Any]] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("data:"):
            frames.append(json.loads(stripped.removeprefix("data:").strip()))
    return frames


def _events(frames: Sequence[dict[str, Any]], event: str) -> list[dict[str, Any]]:
    return [frame for frame in frames if frame.get("event") == event]


# --------------------------------------------------------------------------------------
# DoD-1 — the world build and every self / owner / registry success path
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Drive:
    """One driven request, tagged with the enumeration row it covers."""

    row: int
    method: str
    path: str
    body: Any = None
    accepted: tuple[int, ...] = (200, 201, 204)


@dataclass
class _DriveLog:
    rows: list[int] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _send(client: TestClient, drive: _Drive, log: _DriveLog) -> httpx.Response:
    log.rows.append(drive.row)
    if drive.body is None:
        response = client.request(drive.method, drive.path)
    else:
        response = client.request(drive.method, drive.path, json=drive.body)
    if response.status_code not in drive.accepted:
        log.problems.append(
            f"DoD-1: enumeration row {drive.row} {drive.method} {drive.path} answered "
            f"{response.status_code}, not one of {drive.accepted}: {response.text[:400]}"
        )
    return response


def _drive_every_success_path(world: AuditWorld, log: _DriveLog) -> None:
    """Drive every ``self``, ``owner`` and ``registry`` row as its owner, in an order the
    built validation accepts (a settle needs a non-empty zone, a reopen needs an empty one
    and a buried group, a translation needs an uncached eligible row, an import needs a
    real envelope). Every row of the enumeration with one of those three classes is
    covered; the coverage is asserted by the caller, two-way, against
    ``ENUMERATED_ROUTES``.
    """
    a = world.clients.a
    content = world.a
    registry = world.sentinels
    session_id = content.session_with_setup_id
    character_id = content.character_id
    setup_id = content.setup_id

    # --- the twelve `self` rows and the one `registry` row -----------------------------
    _send(a, _Drive(6, "GET", "/api/me"), log)
    _send(a, _Drive(7, "GET", "/api/me/settings"), log)
    _send(
        a,
        _Drive(
            8,
            "PATCH",
            "/api/me/settings",
            # The world's own values, written back unchanged: the translation target
            # language is read from them, so nothing downstream shifts.
            {
                "rp_language": registry.get(user="A", table="users", field="rp_language"),
                "preferred_language": registry.get(user="A", table="users", field="preferred_language"),
            },
        ),
        log,
    )
    _send(a, _Drive(9, "GET", "/api/models"), log)
    _send(a, _Drive(10, "GET", "/api/characters?include_archived=true"), log)
    extra_character = _send(
        a,
        _Drive(11, "POST", "/api/characters", {"name": f"audit 007 character {PROBE}", "sheet": "audit 007 sheet"}),
        log,
    ).json()
    extra_character_id = str(extra_character["id"])
    _send(a, _Drive(12, "GET", "/api/sessions?include_archived=true"), log)
    _send(a, _Drive(13, "GET", "/api/memos?scope=user"), log)
    extra_memo = _send(
        a,
        _Drive(
            14,
            "POST",
            "/api/memos",
            {"scope": "session", "scope_id": session_id, "body": f"audit 007 memo {PROBE}"},
        ),
        log,
    ).json()
    extra_memo_id = str(extra_memo["id"])
    _send(
        a,
        _Drive(
            15,
            "PUT",
            "/api/memos/order",
            # The level's exact id set, in the order the world already set.
            {
                "scope": content.memos.reordered_scope,
                "scope_id": character_id,
                "memo_ids": list(content.memos.reordered_ids),
            },
        ),
        log,
    )
    own_sentinel = registry.get(user="A", table="characters", field="name")
    _send(a, _Drive(16, "GET", f"/api/search?q={own_sentinel}"), log)

    # --- the thirty-five `owner` rows, as their owner ----------------------------------
    _send(a, _Drive(19, "GET", f"/api/characters/{character_id}"), log)
    _send(
        a,
        _Drive(20, "PATCH", f"/api/characters/{character_id}", {"name": f"audit character {own_sentinel}"}),
        log,
    )
    _send(a, _Drive(50, "GET", f"/api/characters/{character_id}/configuration"), log)
    _send(
        a,
        _Drive(
            51,
            "PATCH",
            f"/api/characters/{character_id}/configuration",
            {
                "model": {"server_id": world.models.server_id, "model_name": world.models.chat_model_name},
                "system_prompt": (
                    "audit character prompt "
                    f"{registry.get(user='A', table='characters', field='system_prompt')}"
                ),
            },
        ),
        log,
    )
    _send(a, _Drive(23, "GET", f"/api/characters/{character_id}/setups?include_archived=true"), log)
    extra_setup = _send(
        a,
        _Drive(
            24,
            "POST",
            f"/api/characters/{character_id}/setups",
            {"name": f"audit 007 setup {PROBE}", "description": "audit 007 setup text"},
        ),
        log,
    ).json()
    extra_setup_id = str(extra_setup["id"])
    _send(a, _Drive(25, "GET", f"/api/setups/{setup_id}"), log)
    _send(
        a,
        _Drive(
            26,
            "PATCH",
            f"/api/setups/{setup_id}",
            {"name": f"audit setup {registry.get(user='A', table='setups', field='name')}"},
        ),
        log,
    )
    # Archive/restore run on the throwaway setup, so the world's own one stays choosable.
    _send(a, _Drive(27, "POST", f"/api/setups/{extra_setup_id}/archive"), log)
    _send(a, _Drive(28, "POST", f"/api/setups/{extra_setup_id}/restore"), log)
    _send(a, _Drive(29, "GET", f"/api/characters/{character_id}/sessions?include_archived=true"), log)
    _send(
        a,
        _Drive(
            30,
            "POST",
            f"/api/characters/{character_id}/sessions",
            {"setup_id": setup_id, "opening_message": f"audit 007 opening {PROBE}"},
        ),
        log,
    )
    _send(a, _Drive(31, "GET", f"/api/sessions/{session_id}"), log)
    _send(a, _Drive(42, "GET", f"/api/sessions/{session_id}/configuration"), log)
    _send(
        a,
        _Drive(
            43,
            "PATCH",
            f"/api/sessions/{session_id}/configuration",
            {
                "system_prompt": (
                    f"audit session prompt {registry.get(user='A', table='sessions', field='system_prompt')}"
                )
            },
        ),
        log,
    )
    _send(a, _Drive(34, "GET", f"/api/sessions/{session_id}/entries"), log)
    _send(a, _Drive(36, "GET", f"/api/sessions/{session_id}/zone"), log)
    _send(a, _Drive(41, "GET", f"/api/sessions/{session_id}/memo-chain"), log)
    _send(
        a,
        _Drive(
            35,
            "POST",
            f"/api/sessions/{session_id}/entries",
            {"kind": "partner", "text": f"audit 007 partner {PROBE}"},
        ),
        log,
    )
    _send(a, _Drive(37, "POST", f"/api/sessions/{session_id}/zone/messages", {"text": f"audit 007 zone {PROBE}"}), log)

    # compose: SSE, so it is driven through the threaded helper rather than ``_send``.
    world.fakes.chat_factory.script_text(f"audit 007 assistant reply {PROBE}")
    log.rows.append(38)
    compose = _compose_response(a, session_id, {"text": f"audit 007 compose prompt {PROBE}"})
    if compose.status_code != 200:
        log.problems.append(f"DoD-1: enumeration row 38 compose answered {compose.status_code}: {compose.text[:400]}")
    compose_frames = _frames(compose.text)
    if _events(compose_frames, "error"):
        log.problems.append(f"DoD-1: enumeration row 38 compose carried an error frame: {compose_frames}")
    if len(_events(compose_frames, "done")) != 1:
        log.problems.append(f"DoD-1: enumeration row 38 compose did not finish: {compose_frames}")

    settled = _send(a, _Drive(39, "POST", f"/api/sessions/{session_id}/settle"), log).json()
    head_id = str(settled["entry_id"])
    if not settled["buried_ids"]:
        log.problems.append(f"DoD-1: the settled head carries no buried group, so row 40 cannot run: {settled}")
    _send(a, _Drive(46, "GET", f"/api/messages/{head_id}/discussion"), log)
    _send(a, _Drive(40, "POST", f"/api/sessions/{session_id}/reopen"), log)

    # Editing the settled partner block drops its cached translation, which is what makes
    # row 47 a real model call rather than a cache read.
    partner_id = content.messages.partner_id
    _send(
        a,
        _Drive(
            45,
            "PATCH",
            f"/api/messages/{partner_id}",
            {
                "text": (
                    "audit partner block "
                    f"{registry.get(user='A', table='messages', field='text[partner]')} "
                    f"{registry.get(user='A', table='session_vec', field='embedded_text')}"
                )
            },
        ),
        log,
    )
    world.fakes.translation_factory.script_text(
        f"audit translation {registry.get(user='A', table='translations', field='text')}"
    )
    _send(a, _Drive(47, "POST", f"/api/messages/{partner_id}/translation"), log)

    session_envelope = _send(a, _Drive(44, "GET", f"/api/sessions/{session_id}/export"), log).json()
    _send(a, _Drive(52, "GET", f"/api/characters/{character_id}/export"), log)
    user_envelope = _send(a, _Drive(17, "GET", "/api/export"), log).json()
    _send(a, _Drive(53, "POST", f"/api/characters/{character_id}/import", session_envelope), log)
    _send(a, _Drive(18, "POST", "/api/import", user_envelope), log)

    _send(a, _Drive(21, "POST", f"/api/characters/{extra_character_id}/archive"), log)
    _send(a, _Drive(22, "POST", f"/api/characters/{extra_character_id}/restore"), log)
    _send(a, _Drive(32, "POST", f"/api/sessions/{content.session_without_setup_id}/archive"), log)
    _send(a, _Drive(33, "POST", f"/api/sessions/{content.session_without_setup_id}/restore"), log)
    _send(a, _Drive(48, "PATCH", f"/api/memos/{extra_memo_id}", {"body": f"audit 007 memo edited {PROBE}"}), log)
    _send(a, _Drive(49, "DELETE", f"/api/memos/{extra_memo_id}"), log)


def test_world_build_and_every_success_path_log_no_sentinel__S032_007_DoD1(harness: LogHarness) -> None:
    """DoD-1 (US-084.AC-1) — building the full audit world and driving every ``self``,
    ``owner`` and ``registry`` route's success path, under the real ``configure_logging``
    with the console at ``DEBUG`` and a level-0 capture sink, emits no record whose
    message, extra or exception text contains any sentinel.

    Mechanism: ``docs/architecture/deployment.md`` "The redaction rule" (no level
    exception). The build phase is witnessed through the **real console sink's text**,
    because ``configure_logging`` itself calls ``logger.remove()``, so no capture sink can
    predate it; the driven phase is witnessed by both the capture sink and the console.

    ``bound_console()`` is entered here, in the call phase, so the console sink
    ``configure_logging`` adds inside ``audit_world`` really is this module's stream.
    """
    with (
        harness.bound_console(),
        restored_logging_state(),
        audit_world(harness.settings, harness.engine, real_logging=True) as world,
    ):
        needles = _needles(world)
        build_console = harness.console_text()
        problems = _text_problems(
            build_console, needles, clause="DoD-1 (world build)", witness="the real console sink"
        )

        log = _DriveLog()
        with captured_logs(restore_stdlib=False) as capture:
            _control(capture, harness, "dod1")
            _drive_every_success_path(world, log)
        problems += _capture_problems(capture, needles, clause="DoD-1 (success paths)")
        problems += _text_problems(
            harness.console_text()[len(build_console) :],
            needles,
            clause="DoD-1 (success paths)",
            witness="the real console sink",
        )

        # Coverage, two-way and exact: no row of the three swept classes may be skipped,
        # and nothing outside them may be counted as covering one.
        expected = {route.row for route in ENUMERATED_ROUTES if route.route_class in ("self", "owner", "registry")}
        assert len(expected) == 48, sorted(expected)
        assert set(log.rows) == expected, (
            f"rows driven but not swept: {sorted(set(log.rows) - expected)}; "
            f"rows of class self/owner/registry never driven: {sorted(expected - set(log.rows))}"
        )
        assert len(log.rows) == len(expected), f"a row was driven twice: {sorted(log.rows)}"

        assert not problems, "\n".join(problems)
        assert not log.problems, "\n".join(log.problems)

        # The file sink is the third real sink. loguru buffers it, so it is flushed by
        # removing every sink; this is the last act of the test. An empty file is not a
        # positive control (the console stream above is the armed one), but a sentinel in
        # it would be a finding exactly as DoD-10 describes for ``data/logs/``.
        logger.remove()
        assert not _text_problems(
            harness.log_file_text(), needles, clause="DoD-1 (log file)", witness="the real log file sink"
        )


# --------------------------------------------------------------------------------------
# DoD-2 and DoD-6 — refusal paths
# --------------------------------------------------------------------------------------

#: The body each owner row is driven with when it needs one. Keyed on the normalized path
#: of ``ENUMERATED_ROUTES``. A row absent from this mapping is driven with no body.
_FOREIGN_BODIES: Final[dict[tuple[str, str], Any]] = {
    ("PATCH", "/api/characters/{}"): {"name": f"audit refusal {PROBE}"},
    ("POST", "/api/characters/{}/setups"): {"name": f"audit refusal {PROBE}", "description": "audit refusal"},
    ("POST", "/api/characters/{}/sessions"): {},
    ("PATCH", "/api/characters/{}/configuration"): {"system_prompt": f"audit refusal {PROBE}"},
    ("PATCH", "/api/setups/{}"): {"name": f"audit refusal {PROBE}"},
    ("POST", "/api/sessions/{}/entries"): {"kind": "partner", "text": f"audit refusal {PROBE}"},
    ("POST", "/api/sessions/{}/zone/messages"): {"text": f"audit refusal {PROBE}"},
    ("POST", "/api/sessions/{}/zone/compose"): {"text": f"audit refusal {PROBE}"},
    ("PATCH", "/api/sessions/{}/configuration"): {"system_prompt": f"audit refusal {PROBE}"},
    ("PATCH", "/api/messages/{}"): {"text": f"audit refusal {PROBE}"},
    ("PATCH", "/api/memos/{}"): {"body": f"audit refusal {PROBE}"},
}


def _foreign_id(route: EnumeratedRoute, world: AuditWorld) -> str:
    """B's id for the resource the row's leading path segment names."""
    b = world.b
    if route.path.startswith("/api/characters/"):
        return b.character_id
    if route.path.startswith("/api/setups/"):
        return b.setup_id
    if route.path.startswith("/api/sessions/"):
        return b.session_with_setup_id
    if route.path.startswith("/api/messages/"):
        return b.messages.partner_id
    if route.path.startswith("/api/memos/"):
        return b.memos.of("session", "searchable")
    raise AssertionError(f"no foreign id is defined for owner row {route.row} {route.path}")


def test_refusal_paths_log_no_sentinel__S032_007_DoD2_DoD6(harness: LogHarness) -> None:
    """DoD-2 and DoD-6 (US-084.AC-1) — refusal paths emit no sentinel: every foreign-id
    404 of step 003, 409 ``memo_order_mismatch`` / ``zone_empty`` / ``nothing_to_reopen``
    / ``already_configured`` / ``database_not_empty``, a 422 whose invalid body carries a
    sentinel (DoD-2), and an import rejected as ``export_invalid`` whose payload carries
    sentinels (DoD-6).

    Mechanism: ``docs/architecture/deployment.md`` "The redaction rule". A refusal's
    **response** may legitimately echo the caller's own input (a 422 does); only log
    records are asserted (``007.context.md``). The destructive admin import runs **last**
    against the fully seeded world and nothing after it depends on the world surviving
    (decision 21).
    """
    with (
        harness.bound_console(),
        restored_logging_state(),
        audit_world(harness.settings, harness.engine, real_logging=True) as world,
    ):
        needles = _needles(world)
        baseline = len(harness.console_text())
        a = world.clients.a
        registered = registered_paths_by_operation(world.application)
        problems: list[str] = []
        driver: list[str] = []

        with captured_logs(restore_stdlib=False) as capture:
            _control(capture, harness, "dod2")

            # (a) every foreign-id refusal of the thirty-five owner rows.
            owner_rows = [route for route in ENUMERATED_ROUTES if route.route_class == "owner"]
            assert len(owner_rows) == 35, sorted(route.row for route in owner_rows)
            for route in owner_rows:
                path = fill_path(registered[route.key()], unknown_id=_foreign_id(route, world))
                body = _FOREIGN_BODIES.get(route.key())
                if route.key() == ("POST", "/api/characters/{}/import"):
                    # The envelope is validated before the character is resolved, so a
                    # bogus body would be refused as ``export_invalid`` instead.
                    body = a.get(f"/api/sessions/{world.a.session_with_setup_id}/export").json()
                if body is None:
                    response = a.request(route.method, path)
                else:
                    response = a.request(route.method, path, json=body)
                if body is None:
                    # No body of mine to be rejected first: the refusal must be the 404.
                    if response.status_code != 404 or response.json()["error"]["code"] != route.not_found_code:
                        driver.append(
                            f"DoD-2 driver: owner row {route.row} {route.method} {path} answered "
                            f"{response.status_code} {response.text[:200]} — expected 404 "
                            f"{route.not_found_code}"
                        )
                elif response.status_code not in (404, 422):
                    # A 422 means my declared body is not the shape this row wants; the
                    # request is still a refusal path, which is what DoD-2 sweeps. The
                    # per-row exact 404 contract is step 003 DoD-1's and is asserted there.
                    driver.append(
                        f"DoD-2 driver: owner row {route.row} {route.method} {path} answered "
                        f"{response.status_code}, not a refusal: {response.text[:200]}"
                    )

            # (b) the named 409s.
            mismatched = a.put(
                "/api/memos/order",
                json={
                    "scope": "session",
                    "scope_id": world.a.session_with_setup_id,
                    "memo_ids": [world.b.memos.of("session", "searchable")],
                },
            )
            assert_empty_detail(assert_envelope(mismatched, 409, "memo_order_mismatch"))
            empty_zone = a.post(f"/api/sessions/{world.a.session_without_setup_id}/settle")
            assert_empty_detail(assert_envelope(empty_zone, 409, "zone_empty"))
            nothing = a.post(f"/api/sessions/{world.a.session_without_setup_id}/reopen")
            assert_empty_detail(assert_envelope(nothing, 409, "nothing_to_reopen"))
            configured = world.clients.anon.post(
                BOOTSTRAP_PATH, json={"username": "audit second founder", "password": f"audit {PROBE}"}
            )
            assert_empty_detail(assert_envelope(configured, 409, "already_configured"))

            # (c) a 422 whose invalid body carries a sentinel (``name`` is missing, so the
            # validation error reports the whole body — including the sentinel — back).
            invalid = a.post("/api/characters", json={"sheet": f"audit invalid {SENTINEL_INVALID_BODY}"})
            assert invalid.status_code == 422, invalid.text

            # (d) DoD-6: an import rejected as ``export_invalid`` whose payload carries
            # every one of A's sentinels, plus a planted one of this module's.
            envelope = a.get("/api/export").json()
            envelope["version"] = 99
            envelope["payload"]["characters"][0]["sheet"] += f" {SENTINEL_IMPORT_PAYLOAD}"
            posted = json.dumps(envelope)
            assert SENTINEL_IMPORT_PAYLOAD in posted
            assert world.sentinels.get(user="A", table="characters", field="sheet") in posted
            rejected = a.post("/api/import", json=envelope)
            assert_envelope(rejected, 400, "export_invalid")

            # (e) the destructive one, last: 409 against the seeded world (decision 21).
            assert a.get("/api/characters").json()["characters"], "anti-vacuity: A must hold content"
            refused = world.clients.adm.post(
                "/api/admin/database/import", json={"audit_probe": SENTINEL_IMPORT_PAYLOAD}
            )
            assert_empty_detail(assert_envelope(refused, 409, "database_not_empty"))

        assert capture.records, "no record at all was captured while driving every refusal path"
        problems += _capture_problems(capture, needles, clause="DoD-2/DoD-6 (refusals)")
        problems += _text_problems(
            harness.console_text()[baseline:],
            needles,
            clause="DoD-2/DoD-6 (refusals)",
            witness="the real console sink",
        )
        assert not problems, "\n".join(problems)
        assert not driver, "\n".join(driver)


# --------------------------------------------------------------------------------------
# DoD-3, DoD-4, DoD-5, DoD-7, DoD-8 — failure paths
# --------------------------------------------------------------------------------------


def _assert_clean(
    capture: LogCapture,
    harness: LogHarness,
    needles: Sequence[str],
    *,
    clause: str,
    baseline: int,
) -> None:
    problems = _capture_problems(capture, needles, clause=clause)
    problems += _text_problems(
        harness.console_text()[baseline:], needles, clause=clause, witness="the real console sink"
    )
    assert not problems, "\n".join(problems)


def test_failure_paths_log_no_sentinel__S032_007_DoD3_DoD4_DoD5_DoD7_DoD8(
    harness: LogHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD-3, DoD-4, DoD-5, DoD-7, DoD-8 (US-084.AC-1) — a sentinel-bearing failure at
    every seam emits no record containing the sentinel.

    Mechanism: ``docs/architecture/deployment.md`` "The redaction rule". Each clause gets
    its own capture window, so a failure names its own clause; they share one world build
    because this is the most expensive world in the feature. All failures are induced at
    the fakes ``audit_world`` installed (re-scripted through ``world.fakes``) or at
    028's ``httpx.MockTransport`` seam — **no network request is made**, and this module
    installs none of the four seam keys itself.
    """
    with (
        harness.bound_console(),
        restored_logging_state(),
        audit_world(harness.settings, harness.engine, real_logging=True) as world,
    ):
        needles = _needles(world)
        a = world.clients.a
        session_id = world.a.session_with_setup_id
        original_embedding: LlmClientFactory = world.fakes.embedding_factory

        # --- DoD-3: a compose whose fake model raises a sentinel-bearing exception, with
        # a prompt that carries sentinels (A's persona, prompts, forced memos and settled
        # entries all do). Both classes are driven: a ``DomainError`` (whose message
        # legitimately reaches the SSE error frame) and a plain one (which does not).
        baseline = len(harness.console_text())
        with captured_logs(restore_stdlib=False) as capture:
            _control(capture, harness, "dod3")
            world.fakes.reset_records()
            world.fakes.chat_factory.script_failure(LlmUnreachableError(f"audit compose {SENTINEL_COMPOSE_DOMAIN}"))
            domain_frames = _frames(_compose_response(a, session_id, {"text": f"audit 007 compose {PROBE}"}).text)
            assert _events(domain_frames, "error"), domain_frames

            world.fakes.chat_factory.script_failure(RuntimeError(f"audit compose {SENTINEL_COMPOSE_PLAIN}"))
            plain_frames = _frames(_compose_response(a, session_id, {"text": f"audit 007 compose {PROBE}"}).text)
            assert _events(plain_frames, "error"), plain_frames

            # Anti-vacuity: the prompt really carried content.
            prompt = "\n".join(
                str(message) for call in world.fakes.chat_factory.chat_calls for message in call.messages
            )
            assert any(one in prompt for one in world.sentinels.of_user("A")), (
                "the composed prompt carried no sentinel of A, so DoD-3's premise is not met"
            )
        _assert_clean(capture, harness, needles, clause="DoD-3 (compose failure)", baseline=baseline)

        # --- DoD-5: a translation whose fake model fails with a sentinel-bearing
        # exception. Decision 12: ``LlmUnreachableError`` is the one class mapped to a
        # handled failure; any other class propagates unhandled, which is the more
        # dangerous case for a log leak, and both are inside DoD-5's words. A fresh
        # settled partner block is filed so the call is never answered from the cache.
        fresh = a.post(
            f"/api/sessions/{session_id}/entries",
            json={"kind": "partner", "text": f"audit 007 translation source {PROBE}"},
        )
        assert fresh.status_code == 201, fresh.text
        fresh_id = str(fresh.json()["id"])

        baseline = len(harness.console_text())
        with captured_logs(restore_stdlib=False) as capture:
            _control(capture, harness, "dod5")
            world.fakes.translation_factory.script_failure(
                LlmUnreachableError(f"audit translation {SENTINEL_TRANSLATION_HANDLED}")
            )
            handled = a.post(f"/api/messages/{fresh_id}/translation")
            assert_envelope(handled, 502, "translation_failed")

            unhandled = RuntimeError(f"audit translation {SENTINEL_TRANSLATION_UNHANDLED}")
            world.fakes.translation_factory.script_failure(unhandled)
            with pytest.raises(RuntimeError) as raised:
                a.post(f"/api/messages/{fresh_id}/translation")
            assert SENTINEL_TRANSLATION_UNHANDLED in str(raised.value), raised.value
        _assert_clean(capture, harness, needles, clause="DoD-5 (translation failure)", baseline=baseline)

        # --- DoD-4: each of ``memo_search``, ``session_search`` and ``web_search``
        # failing with a sentinel-bearing exception. The two search adapters delegate
        # through the live embedding factory (re-pointed, then restored); the web failure
        # is induced at 028's HTTP seam, on the recorder ``audit_world`` built — this step
        # may not rebuild the seam, so the scripted error is set on the live recorder.
        baseline = len(harness.console_text())
        with captured_logs(restore_stdlib=False) as capture:
            _control(capture, harness, "dod4")
            world.fakes.use_embedding_factory(
                ScriptedProbeFactory(embed_error=RuntimeError(f"audit tool {SENTINEL_TOOL_EMBED}"))
            )
            world.fakes.web_recorder._error = httpx.ConnectError(f"audit tool {SENTINEL_TOOL_WEB}")
            try:
                arguments = json.dumps({"query": f"audit tool query {SENTINEL_TOOL_QUERY}"})
                world.fakes.chat_factory.script(
                    tool_call_round(name=MEMO_SEARCH_NAME, arguments=arguments, call_id="audit-007-memo"),
                    tool_call_round(name=SESSION_SEARCH_NAME, arguments=arguments, call_id="audit-007-session"),
                    tool_call_round(name=WEB_SEARCH_NAME, arguments=arguments, call_id="audit-007-web"),
                    text_round(f"audit 007 after tool failures {PROBE}"),
                )
                tool_frames = _frames(_compose_response(a, session_id, {"text": f"audit 007 tools {PROBE}"}).text)
            finally:
                world.fakes.web_recorder._error = None
                world.fakes.use_embedding_factory(original_embedding)

            failed = {str(frame.get("tool")) for frame in _events(tool_frames, "tool_fail")}
            assert failed == {MEMO_SEARCH_NAME, SESSION_SEARCH_NAME, WEB_SEARCH_NAME}, tool_frames
        _assert_clean(capture, harness, needles, clause="DoD-4 (tool failure)", baseline=baseline)

        # --- DoD-7: a failed login with a sentinel password, and an LLM-server probe
        # (test / available-models) failing against a server whose API key is a sentinel.
        monkeypatch.setenv(PROBE_KEY_VARIABLE, SENTINEL_PROBE_API_KEY)
        created = world.clients.adm.post(
            ADMIN_SERVERS_PATH,
            json={
                "name": "audit probe server",
                "kind": "llamaswap",
                "base_url": FAKE_SERVER_BASE_URL,
                "api_key_ref": PROBE_KEY_POINTER,
            },
        )
        assert created.status_code == 201, created.text
        probe_server_id = str(created.json()["id"])

        baseline = len(harness.console_text())
        with captured_logs(restore_stdlib=False) as capture:
            _control(capture, harness, "dod7")
            failed_login = world.clients.anon.post(
                LOGIN_PATH,
                json={"username": world.a.identity.username, "password": SENTINEL_LOGIN_PASSWORD},
            )
            assert_empty_detail(assert_envelope(failed_login, 400, "invalid_credentials"))

            probe_factory = ScriptedProbeFactory(
                probe_result=ProbeResult(outcome=ProbeOutcome.AUTH_FAILED, model_names=())
            )
            world.fakes.use_embedding_factory(probe_factory)
            try:
                tested = world.clients.adm.post(f"{ADMIN_SERVERS_PATH}/{probe_server_id}/test")
                assert tested.status_code == 200, tested.text
                listed = world.clients.adm.get(f"{ADMIN_SERVERS_PATH}/{probe_server_id}/available-models")
                assert_envelope(listed, 502, "llm_unreachable")
            finally:
                world.fakes.use_embedding_factory(original_embedding)

            # Anti-vacuity: the probe really ran, and the sentinel key really reached the
            # client, so "the sentinel is in no log record" is a fact about redaction.
            assert probe_factory.probe_calls >= 2, probe_factory.probe_calls
            handed = [key for _, key, _ in probe_factory.calls]
            assert handed and all(key == SENTINEL_PROBE_API_KEY for key in handed), handed
        _assert_clean(capture, harness, needles, clause="DoD-7 (login and probe failure)", baseline=baseline)

        # --- DoD-8: my-search with a sentinel query. (029's ``GET /api/search?q=<text>``
        # is also what put user text in uvicorn's access line; that access-log record is
        # step 001 DoD-1's subject. Asserted here: the application's own records.)
        baseline = len(harness.console_text())
        with captured_logs(restore_stdlib=False) as capture:
            _control(capture, harness, "dod8")
            foreign_query = world.sentinels.get(user="B", table="characters", field="name")
            own_query = world.sentinels.get(user="A", table="characters", field="name")
            foreign = a.get(f"/api/search?q={foreign_query}")
            assert foreign.status_code == 200, foreign.text
            own = a.get(f"/api/search?q={own_query}")
            assert own.status_code == 200, own.text
            # Anti-vacuity: my-search really searched and really matched.
            assert own.json()["characters"], own.text
        _assert_clean(capture, harness, needles, clause="DoD-8 (my-search)", baseline=baseline)


# --------------------------------------------------------------------------------------
# DoD-9 — the SQLAlchemy loggers
# --------------------------------------------------------------------------------------


def test_sqlalchemy_loggers_stay_at_warning_or_higher__S032_007_DoD9(harness: LogHarness) -> None:
    """DoD-9 (US-084.AC-1) — after ``configure_logging``, the ``sqlalchemy`` and
    ``sqlalchemy.engine`` loggers' effective level is WARNING or higher.

    Mechanism: ``docs/architecture/deployment.md`` "The redaction rule". This complements
    step 001 DoD-7 (the engine hides bound parameters): together they keep SQL parameters
    out of logs even if someone lowers a level. No world is built — the clause is about
    ``configure_logging`` alone.
    """
    with harness.bound_console(), restored_logging_state():
        configure_logging(harness.settings)
        levels = {
            name: logging.getLogger(name).getEffectiveLevel() for name in ("sqlalchemy", "sqlalchemy.engine")
        }
        assert all(level >= logging.WARNING for level in levels.values()), levels
        # Not vacuous: the root bridge really is wide open, so these two levels are the
        # only thing standing between a statement log and the sinks.
        assert logging.getLogger().getEffectiveLevel() <= logging.DEBUG, logging.getLogger().level
