"""Tests for the `web_search` Tool adapter (feature 028, step 002).

Covers DoD-1 .. DoD-7, DoD-11, DoD-12 and DoD-13 of
`docs/plans/028.web-search-tool/002.web-search-tool-and-registration.md`. The offering and
gating clauses (DoD-8, DoD-9, DoD-10) live in `tests/test_web_search_offering.py`; the
DoD-14 amendment is one assertion in `tests/test_tool_seam.py`. DoD-15 .. DoD-17 are
`[manual/live]` and carry no test.

Every expected value comes from the spec, never from the implementation: the step file's
Definition of done, `002.context.md` ("What the model receives" — the block form, the
whitespace normalisation, `(untitled)`, `No web results.`, `<N> results` — and the query
rule) and the feature `context.md` (D5 the one failure shape, D6 the outbound boundary, D7
nothing is logged, D8 the scope is unused, D9 the result count, the literals table). The
content and summary strings of DoD-1 .. DoD-4 are written out here from that table applied
to the faked results; only DoD-5 and DoD-11, where the step file itself says "equals the
formatter's output", compare against `format_results`.

Bindings come from `status.md` `## Skeleton` -> "Step 002 — frozen interface":

    RESULT_COUNT: Final = 5
    def format_results(results: Sequence[WebResult]) -> tuple[str, str]   # (content, summary)

    @dataclass(frozen=True)
    class WebSearchTool:
        provider: WebSearchProvider            # required, positional-or-keyword
        name: ClassVar[str] = WEB_SEARCH_NAME
        async def run(self, scope, connection, arguments) -> ToolOutcome

    def configured_web_search_tool(api_key: str | None, engine_id: str | None) -> WebSearchTool | None

plus step 001's `WebResult`, `WebSearchProvider` and `GoogleCustomSearchProvider`, and 021's
`ToolScope(user_id, session_id, character_id, setup_id)`, `ToolOutcome(content, summary)`,
`build_tool_scope`, `dispatch(call, scope, offered, registry, engine, generator)`.

Mechanics (`context.md` "Test conventions"): outbound HTTP is faked with
`httpx.MockTransport` through step 001's frozen `transport=` seam, so no test makes a real
request and nothing is monkeypatched; async code runs under `asyncio.run` bounded by
`asyncio.wait_for`; the seam tests use a real SQLite file per test through the shared
`db_engine` fixture with file-local raw inserts, two users and ids above 2**60; credentials
are obvious fakes. Each test name ends `__S028_002_DoD<n>`.
"""

import ast
import asyncio
import json
import subprocess
import sys
from collections.abc import Callable, Coroutine, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx
import pytest
from loguru import logger
from sqlalchemy import Engine, select

from app.db import schema
from app.errors import ToolFailedError
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services.llm.chat import ToolCall
from app.services.llm.frames import ToolFailFrame, ToolResultFrame
from app.services.tools import seam as seam_module
from app.services.tools import web_search as adapter_module
from app.services.tools.seam import DispatchResult, ToolOutcome, ToolScope, build_tool_scope, dispatch
from app.services.tools.web_search import (
    RESULT_COUNT,
    WebSearchTool,
    configured_web_search_tool,
    format_results,
)
from app.services.web_search.google import GoogleCustomSearchProvider
from app.services.web_search.provider import WebResult

#: The seeded instant, in the project's fixed-width UTC text form.
TIMESTAMP = "2026-01-01T00:00:00.000000+00:00"

#: Obvious fakes (D12). No test may reach Google.
API_KEY = "test-key"
ENGINE_ID = "test-cx"

#: Literals — `context.md`'s table and `002.context.md`'s content table.
EXPECTED_TOOL_NAME = "web_search"
ZERO_RESULT_CONTENT = "No web results."
ZERO_RESULT_SUMMARY = "0 results"
UNTITLED = "(untitled)"
EXPECTED_DETAIL = {"tool": "web_search"}
FAILED_CONTENT = "The tool failed. Continue without its result."
FAILED_ROW_TEXT = "The tool failed."
FAILED_CODE = "tool_failed"

#: Bound for every asyncio run and every subprocess.
TIMEOUT_SECONDS = 10.0
SUBPROCESS_TIMEOUT_SECONDS = 60.0

#: Every id below is above 2**60 = 1152921504606846976 (snowflake-sized).
USER_A = 1_802_000_000_000_000_001
USER_B = 1_802_000_000_000_000_002

CHARACTER_A = 1_802_000_000_000_000_101
CHARACTER_B = 1_802_000_000_000_000_102

SETUP_A = 1_802_000_000_000_000_151

SESSION_A = 1_802_000_000_000_000_201
SESSION_B = 1_802_000_000_000_000_202

Handler = Callable[[httpx.Request], httpx.Response]


# --- the faked network (no monkeypatching; step 001's `transport=` seam) ---------------------


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion on a fresh event loop, bounded."""
    return asyncio.run(asyncio.wait_for(coro, timeout=TIMEOUT_SECONDS))


class Recorder:
    """An `httpx.MockTransport` handler that records every request it is given."""

    def __init__(self, respond: Handler) -> None:
        self.requests: list[httpx.Request] = []
        self._respond = respond

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._respond(request)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def json_handler(payload: Any, status: int = 200) -> Handler:
    """Answer every request with `status` and `payload` serialised as JSON."""

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return respond


def status_handler(status: int) -> Handler:
    """Answer every request with a non-2xx status and a provider-shaped error body."""
    return json_handler({"error": {"message": "provider says no"}}, status=status)


def raising_handler(error_type: type[httpx.TransportError]) -> Handler:
    """A transport that fails instead of answering."""

    def respond(request: httpx.Request) -> httpx.Response:
        raise error_type("simulated transport failure", request=request)

    return respond


def make_tool(recorder: Recorder) -> WebSearchTool:
    """The adapter over a Google provider whose only transport is the recorder's mock."""
    return WebSearchTool(
        GoogleCustomSearchProvider(API_KEY, ENGINE_ID, transport=recorder.transport)
    )


def _rendered(request: httpx.Request) -> str:
    """The request's URL and headers as one searchable string (no body: the call is a GET)."""
    headers = " ".join(f"{name}:{value}" for name, value in request.headers.items())
    return f"{request.url} {headers}"


def _forbidden_forms(*secrets: str) -> tuple[str, ...]:
    """Each secret plus its URL-encoded form, de-duplicated and order-preserving.

    The redaction rule (`deployment.md`, D7) forbids the value, not one spelling of it. The
    query and the engine id travel in a request URL's query string, where they are
    percent-encoded — `urlencode` turns a space into `+` — so a raw-substring sweep would
    miss exactly the item D7 names first: the query, which is message text composed from the
    discussion. The encoded form comes from the stdlib rather than being written out, so this
    stays honest if the query literal changes.
    """
    return tuple(dict.fromkeys(form for secret in secrets for form in (secret, quote_plus(secret))))


@contextmanager
def _captured_logs() -> Iterator[list[str]]:
    """Every loguru line emitted while the block runs — formatted text, message, extra, exception."""
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


# --- raw-insert helpers (file-local; no service is used to seed) -----------------------------


def _insert_user(engine: Engine, *, user_id: int, username: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.users.insert().values(
                id=user_id,
                username=username,
                password_hash="not-a-real-hash",
                role=Role.ROLEPLAYER,
                is_enabled=True,
                rp_language=None,
                preferred_language=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_character(engine: Engine, *, character_id: int, user_id: int, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.characters.insert().values(
                id=character_id,
                user_id=user_id,
                name=name,
                sheet="",
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_setup(engine: Engine, *, setup_id: int, user_id: int, character_id: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.setups.insert().values(
                id=setup_id,
                user_id=user_id,
                character_id=character_id,
                name="the quayside",
                description="",
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


def _insert_session(
    engine: Engine, *, session_id: int, user_id: int, character_id: int, setup_id: int | None
) -> None:
    with engine.begin() as connection:
        connection.execute(
            schema.sessions.insert().values(
                id=session_id,
                user_id=user_id,
                character_id=character_id,
                setup_id=setup_id,
                last_used_at=TIMESTAMP,
                archived_at=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """Two owners: user A with a character, a setup and a session; user B with their own."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=USER_A, username="aster")
    _insert_user(db_engine, user_id=USER_B, username="briar")
    _insert_character(db_engine, character_id=CHARACTER_A, user_id=USER_A, name="Aria")
    _insert_character(db_engine, character_id=CHARACTER_B, user_id=USER_B, name="Bram")
    _insert_setup(db_engine, setup_id=SETUP_A, user_id=USER_A, character_id=CHARACTER_A)
    _insert_session(
        db_engine, session_id=SESSION_A, user_id=USER_A, character_id=CHARACTER_A, setup_id=SETUP_A
    )
    _insert_session(
        db_engine, session_id=SESSION_B, user_id=USER_B, character_id=CHARACTER_B, setup_id=None
    )
    return db_engine


@pytest.fixture
def generator() -> SnowflakeGenerator:
    return SnowflakeGenerator(node_id=1)


#: The caller's scope, as 021's D6 defines it. The adapter uses none of it (D8).
SCOPE_A = ToolScope(
    user_id=USER_A, session_id=SESSION_A, character_id=CHARACTER_A, setup_id=SETUP_A
)


def _build_scope(engine: Engine, user_id: int, session_id: int) -> ToolScope:
    """021's owner-scoped scope builder, on a connection of its own."""
    with engine.connect() as connection:
        return build_tool_scope(connection, user_id, session_id)


def _run(
    engine: Engine,
    recorder: Recorder,
    arguments: Mapping[str, object],
    scope: ToolScope = SCOPE_A,
) -> ToolOutcome:
    """Await `run` from a sync test, on a real connection the adapter is free to ignore (D8)."""
    with engine.connect() as connection:
        return run(make_tool(recorder).run(scope, connection, arguments))


def _tool_rows(engine: Engine, session_id: int) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            select(schema.messages)
            .where(schema.messages.c.session_id == session_id)
            .where(schema.messages.c.role == "tool")
            .order_by(schema.messages.c.id)
        ).all()
    return [dict(row._mapping) for row in rows]


def _dispatch(
    engine: Engine,
    generator: SnowflakeGenerator,
    scope: ToolScope,
    recorder: Recorder,
    query: str,
) -> DispatchResult:
    """One call through 021's real `dispatch`, with the real adapter in the registry."""
    call = ToolCall(
        call_id="call-028-002",
        name=EXPECTED_TOOL_NAME,
        arguments=json.dumps({"query": query}),
    )
    registry = {EXPECTED_TOOL_NAME: make_tool(recorder)}
    return run(dispatch(call, scope, [EXPECTED_TOOL_NAME], registry, engine, generator))


# =========================================================================================
# DoD-1: the content — three blocks in order, each `<title>\n<url>\n<snippet>`
# =========================================================================================

RESULT_A = WebResult(title="Alpha", url="https://example.test/a", snippet="The first snippet.")
RESULT_B = WebResult(title="Beta", url="https://example.test/b", snippet="The second snippet.")
RESULT_C = WebResult(title="Gamma", url="https://example.test/c", snippet="The third snippet.")

#: `002.context.md`: blocks in provider order, joined by `\n\n`; each block three lines.
THREE_BLOCK_CONTENT = (
    "Alpha\nhttps://example.test/a\nThe first snippet."
    "\n\n"
    "Beta\nhttps://example.test/b\nThe second snippet."
    "\n\n"
    "Gamma\nhttps://example.test/c\nThe third snippet."
)

#: One result whose title and snippet carry newlines, tabs, runs of spaces and ragged ends.
RAGGED_RESULT = WebResult(
    title="  Ragged\ttitle\nwith   runs  ",
    url="  https://example.test/ragged  ",
    snippet="\n a snippet  over\tseveral\nlines \n",
)
RAGGED_BLOCK = "Ragged title with runs\nhttps://example.test/ragged\na snippet over several lines"


def test_three_results_render_as_three_ordered_blocks__S028_002_DoD1() -> None:
    """DoD-1 — A, B, C in that order, blocks joined by `\\n\\n`, each title / url / snippet."""
    content, _ = format_results([RESULT_A, RESULT_B, RESULT_C])

    assert content == THREE_BLOCK_CONTENT
    assert content.split("\n\n") == [
        "Alpha\nhttps://example.test/a\nThe first snippet.",
        "Beta\nhttps://example.test/b\nThe second snippet.",
        "Gamma\nhttps://example.test/c\nThe third snippet.",
    ]


def test_the_block_order_follows_the_results__S028_002_DoD1() -> None:
    """DoD-1 — the order is the results' order, not any sort of their own."""
    content, _ = format_results([RESULT_C, RESULT_A, RESULT_B])

    assert content.split("\n\n")[0].startswith("Gamma\n")
    assert [block.split("\n")[0] for block in content.split("\n\n")] == ["Gamma", "Alpha", "Beta"]


def test_whitespace_runs_in_a_title_and_a_snippet_collapse_to_one_line__S028_002_DoD1() -> None:
    """DoD-1 / `002.context.md` — every whitespace run becomes one space and the ends are trimmed."""
    content, _ = format_results([RAGGED_RESULT])

    assert content == RAGGED_BLOCK
    lines = content.split("\n")
    assert len(lines) == 3
    for line in lines:
        assert line == line.strip()
        assert "\t" not in line
        assert "  " not in line


def test_a_ragged_result_beside_plain_ones_keeps_the_block_shape__S028_002_DoD1() -> None:
    """DoD-1 — normalisation is per field; the separator and the order are unaffected."""
    content, _ = format_results([RESULT_A, RAGGED_RESULT, RESULT_C])

    assert content.split("\n\n") == [
        "Alpha\nhttps://example.test/a\nThe first snippet.",
        RAGGED_BLOCK,
        "Gamma\nhttps://example.test/c\nThe third snippet.",
    ]


# =========================================================================================
# DoD-2: empty fields — `(untitled)` for a blank title, no snippet line for a blank snippet
# =========================================================================================

BLANK_FORMS = ("", "   ", "\n\t ", " \n ")


@pytest.mark.parametrize("blank", BLANK_FORMS, ids=["empty", "spaces", "mixed", "newlines"])
def test_a_blank_title_renders_the_untitled_marker__S028_002_DoD2(blank: str) -> None:
    """DoD-2 — "blank" is empty after the normalisation, and the title line is `(untitled)`."""
    content, _ = format_results(
        [WebResult(title=blank, url="https://example.test/a", snippet="A snippet.")]
    )

    assert content == f"{UNTITLED}\nhttps://example.test/a\nA snippet."


@pytest.mark.parametrize("blank", BLANK_FORMS, ids=["empty", "spaces", "mixed", "newlines"])
def test_a_blank_snippet_leaves_the_block_without_a_snippet_line__S028_002_DoD2(blank: str) -> None:
    """DoD-2 — the block is the title line, `\\n`, the url line, and nothing more."""
    content, _ = format_results(
        [WebResult(title="Alpha", url="https://example.test/a", snippet=blank)]
    )

    assert content == "Alpha\nhttps://example.test/a"
    assert len(content.split("\n")) == 2


def test_a_blank_title_and_a_blank_snippet_together__S028_002_DoD2() -> None:
    """DoD-2 — both rules apply at once: `(untitled)` then the url line alone."""
    content, _ = format_results([WebResult(title="  ", url="https://example.test/a", snippet="")])

    assert content == f"{UNTITLED}\nhttps://example.test/a"


def test_a_snippetless_block_still_separates_from_its_neighbours__S028_002_DoD2() -> None:
    """DoD-2 / DoD-1 — a two-line block does not disturb the `\\n\\n` separator."""
    content, _ = format_results(
        [RESULT_A, WebResult(title="Beta", url="https://example.test/b", snippet="  "), RESULT_C]
    )

    assert content.split("\n\n") == [
        "Alpha\nhttps://example.test/a\nThe first snippet.",
        "Beta\nhttps://example.test/b",
        "Gamma\nhttps://example.test/c\nThe third snippet.",
    ]


# =========================================================================================
# DoD-3: zero results is a success
# =========================================================================================


def test_no_results_gives_the_zero_result_content_and_summary__S028_002_DoD3() -> None:
    """DoD-3 — content exactly `No web results.`, summary exactly `0 results`."""
    content, summary = format_results([])

    assert content == ZERO_RESULT_CONTENT
    assert summary == ZERO_RESULT_SUMMARY


# =========================================================================================
# DoD-4: the summary is `<N> results`, never pluralised and never carrying content
# =========================================================================================


def test_three_results_summarise_as_three_results__S028_002_DoD4() -> None:
    """DoD-4 — exactly `3 results`."""
    _, summary = format_results([RESULT_A, RESULT_B, RESULT_C])

    assert summary == "3 results"


def test_one_result_summarises_as_one_results_unpluralised__S028_002_DoD4() -> None:
    """DoD-4 — exactly `1 results`: the noun is never adjusted for the count."""
    _, summary = format_results([RESULT_A])

    assert summary == "1 results"


def test_the_summary_carries_no_title_url_or_snippet_text__S028_002_DoD4() -> None:
    """DoD-4 / 021 D6 — the summary is a count and a noun; no content leaks into it."""
    marked = [
        WebResult(title="umbercoil", url="https://example.test/thornvale", snippet="wyrmgate"),
        WebResult(title="valebrook", url="https://example.test/cindermoor", snippet="dawnwarden"),
    ]

    _, summary = format_results(marked)

    assert summary == "2 results"
    for marker in ("umbercoil", "thornvale", "wyrmgate", "valebrook", "cindermoor", "dawnwarden"):
        assert marker not in summary


def test_the_outcome_summary_never_echoes_the_query__S028_002_DoD4(engine: Engine) -> None:
    """DoD-4 / D7 — through `run`, the summary is still the bare count: no query echo."""
    marked_query = "quillraven idiom check"
    recorder = Recorder(
        json_handler(
            {
                "items": [
                    {"title": "umbercoil", "link": "https://example.test/one", "snippet": "wyrmgate"},
                    {"title": "valebrook", "link": "https://example.test/two", "snippet": "dawnwarden"},
                ]
            }
        )
    )

    outcome = _run(engine, recorder, {"query": marked_query})

    assert outcome.summary == "2 results"
    for marker in ("quillraven", "umbercoil", "wyrmgate", "valebrook", "dawnwarden"):
        assert marker not in outcome.summary


# =========================================================================================
# DoD-5: what leaves the instance — the query, the engine id, the count, and nothing else
# =========================================================================================

QUERY_IDIOM = "Kentish idiom 'to be in the doldrums'"

TWO_ITEMS: list[dict[str, Any]] = [
    {
        "title": "In the doldrums",
        "link": "https://example.test/doldrums",
        "snippet": "A phrase borrowed from sailing.",
    },
    {
        "title": "Kentish idioms",
        "link": "https://example.test/kentish",
        "snippet": "A short list of them.",
    },
]

TWO_RESULTS = [
    WebResult(
        title="In the doldrums",
        url="https://example.test/doldrums",
        snippet="A phrase borrowed from sailing.",
    ),
    WebResult(
        title="Kentish idioms",
        url="https://example.test/kentish",
        snippet="A short list of them.",
    ),
]

#: The arguments the model could send: the query, plus another user's ids (D8 ignores them).
SPOOFING_ARGUMENTS: dict[str, object] = {
    "query": QUERY_IDIOM,
    "user_id": str(USER_B),
    "session_id": str(SESSION_B),
}

#: Every id the call could possibly leak, as the decimal string it would appear as.
ID_DECIMALS = tuple(
    str(value) for value in (USER_A, SESSION_A, CHARACTER_A, SETUP_A, USER_B, SESSION_B)
)


def test_the_result_count_constant_is_five__S028_002_DoD5() -> None:
    """DoD-5 / D9 — the adapter asks for five results; no paging and no count argument."""
    assert RESULT_COUNT == 5


def test_run_sends_exactly_one_request_with_the_query_and_the_count__S028_002_DoD5(
    engine: Engine,
) -> None:
    """DoD-5 / D6 — one request; `q` is the query verbatim and `num` is `5`."""
    recorder = Recorder(json_handler({"items": TWO_ITEMS}))

    _run(engine, recorder, SPOOFING_ARGUMENTS, _build_scope(engine, USER_A, SESSION_A))

    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.url.params["q"] == QUERY_IDIOM
    assert int(request.url.params["num"]) == 5


def test_no_id_of_the_scope_or_the_arguments_leaves_the_instance__S028_002_DoD5(
    engine: Engine,
) -> None:
    """DoD-5 / D6 / D8 / R5 — no id appears anywhere in the request URL or its headers."""
    recorder = Recorder(json_handler({"items": TWO_ITEMS}))

    _run(engine, recorder, SPOOFING_ARGUMENTS, _build_scope(engine, USER_A, SESSION_A))

    rendered = _rendered(recorder.requests[0])
    for decimal in ID_DECIMALS:
        assert decimal not in rendered


def test_the_outcome_is_the_formatters_answer_for_the_two_items__S028_002_DoD5(
    engine: Engine,
) -> None:
    """DoD-5 — the outcome equals the formatter's output for the two returned results."""
    recorder = Recorder(json_handler({"items": TWO_ITEMS}))

    outcome = _run(engine, recorder, SPOOFING_ARGUMENTS, _build_scope(engine, USER_A, SESSION_A))

    expected_content, expected_summary = format_results(TWO_RESULTS)
    assert outcome.content == expected_content
    assert outcome.summary == expected_summary


def test_the_query_is_passed_untrimmed__S028_002_DoD5(engine: Engine) -> None:
    """`002.context.md` "Query rule" — a non-blank query reaches the provider verbatim."""
    padded = f"  {QUERY_IDIOM}  "
    recorder = Recorder(json_handler({"items": TWO_ITEMS}))

    _run(engine, recorder, {"query": padded})

    assert recorder.requests[0].url.params["q"] == padded


# =========================================================================================
# DoD-6: bad arguments fail before any request
# =========================================================================================

BAD_ARGUMENTS: tuple[dict[str, object], ...] = ({}, {"query": 7}, {"query": "   "})


@pytest.mark.parametrize(
    "arguments", BAD_ARGUMENTS, ids=["missing", "not-a-string", "blank-after-trimming"]
)
def test_bad_arguments_raise_tool_failed_and_send_nothing__S028_002_DoD6(
    engine: Engine, arguments: Mapping[str, object]
) -> None:
    """DoD-6 / D5 — one failure shape, detail `{"tool": "web_search"}`, and no outbound call."""
    recorder = Recorder(json_handler({"items": TWO_ITEMS}))

    with pytest.raises(ToolFailedError) as raised:
        _run(engine, recorder, arguments)

    assert raised.value.detail == EXPECTED_DETAIL
    assert raised.value.code == FAILED_CODE
    assert recorder.requests == []


# =========================================================================================
# DoD-7: the factory is the one place that decides "configured" (D3)
# =========================================================================================

UNUSABLE_COMBINATIONS: tuple[tuple[str | None, str | None], ...] = (
    (None, None),
    (None, ENGINE_ID),
    (API_KEY, None),
    ("", ""),
    ("", ENGINE_ID),
    (API_KEY, ""),
    ("   ", "   "),
    ("   ", ENGINE_ID),
    (API_KEY, "   "),
    (None, ""),
    ("", None),
    ("\t\n", ENGINE_ID),
)


@pytest.mark.parametrize(("api_key", "engine_id"), UNUSABLE_COMBINATIONS)
def test_the_factory_returns_none_unless_both_credentials_are_usable__S028_002_DoD7(
    api_key: str | None, engine_id: str | None
) -> None:
    """DoD-7 / D3 — none, empty or whitespace-only in either position means not configured."""
    assert configured_web_search_tool(api_key, engine_id) is None


def test_the_factory_returns_the_adapter_when_both_credentials_are_set__S028_002_DoD7() -> None:
    """DoD-7 / D3 — with `test-key` / `test-cx` it returns an adapter named `web_search`."""
    tool = configured_web_search_tool(API_KEY, ENGINE_ID)

    assert tool is not None
    assert tool.name == EXPECTED_TOOL_NAME


# =========================================================================================
# DoD-11: success through the real seam (US-070.AC-1, US-071.AC-1, UC-055 main flow)
# =========================================================================================

SEAM_QUERY = "Valmy 1792 weather"

THREE_ITEMS: list[dict[str, Any]] = [
    {
        "title": "Bataille de Valmy",
        "link": "https://example.test/valmy",
        "snippet": "20 September 1792.",
    },
    {
        "title": "The cannonade",
        "link": "https://example.test/cannonade",
        "snippet": "Rain and mud all morning.",
    },
    {
        "title": "Kellermann",
        "link": "https://example.test/kellermann",
        "snippet": "He held the ridge.",
    },
]

THREE_SEAM_RESULTS = [
    WebResult(
        title="Bataille de Valmy", url="https://example.test/valmy", snippet="20 September 1792."
    ),
    WebResult(
        title="The cannonade",
        url="https://example.test/cannonade",
        snippet="Rain and mud all morning.",
    ),
    WebResult(
        title="Kellermann", url="https://example.test/kellermann", snippet="He held the ridge."
    ),
]


def test_dispatch_returns_a_tool_result_frame_with_the_count_summary__S028_002_DoD11(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-11 — a `tool_result` frame for `web_search` carrying the summary `3 results`."""
    scope = _build_scope(engine, USER_A, SESSION_A)
    recorder = Recorder(json_handler({"items": THREE_ITEMS}))

    result = _dispatch(engine, generator, scope, recorder, SEAM_QUERY)

    assert isinstance(result.frame, ToolResultFrame)
    assert result.frame.tool == EXPECTED_TOOL_NAME
    assert result.frame.summary == "3 results"


def test_dispatch_gives_the_model_the_formatted_content__S028_002_DoD11(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-11 / UC-055 main flow — the tool message content is the formatter's content."""
    scope = _build_scope(engine, USER_A, SESSION_A)
    recorder = Recorder(json_handler({"items": THREE_ITEMS}))

    result = _dispatch(engine, generator, scope, recorder, SEAM_QUERY)

    expected_content, _ = format_results(THREE_SEAM_RESULTS)
    assert result.message.content == expected_content


def test_dispatch_writes_one_ok_tool_row_for_web_search__S028_002_DoD11(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-11 / 021 D7 — exactly one tool row, naming `web_search`, its text the summary."""
    scope = _build_scope(engine, USER_A, SESSION_A)
    recorder = Recorder(json_handler({"items": THREE_ITEMS}))

    _dispatch(engine, generator, scope, recorder, SEAM_QUERY)

    rows = _tool_rows(engine, SESSION_A)
    assert len(rows) == 1
    assert rows[0]["tool_name"] == EXPECTED_TOOL_NAME
    assert rows[0]["text"] == "3 results"


# =========================================================================================
# DoD-12: failure through the real seam (UC-055 exception flow, R9, D5, D7)
# =========================================================================================

#: DoD-12's two failures: the transport answering 500, and the transport raising.
FAILURE_HANDLERS: tuple[Handler, ...] = (status_handler(500), raising_handler(httpx.ConnectError))
FAILURE_IDS = ["server-error", "connect-error"]


@pytest.mark.parametrize("handler", FAILURE_HANDLERS, ids=FAILURE_IDS)
def test_dispatch_turns_a_provider_failure_into_a_tool_fail_frame__S028_002_DoD12(
    engine: Engine, generator: SnowflakeGenerator, handler: Handler
) -> None:
    """DoD-12 / R9 — nothing is raised; the frame is `tool_fail` with code `tool_failed`."""
    scope = _build_scope(engine, USER_A, SESSION_A)
    recorder = Recorder(handler)

    result = _dispatch(engine, generator, scope, recorder, SEAM_QUERY)

    assert len(recorder.requests) == 1
    assert isinstance(result.frame, ToolFailFrame)
    assert result.frame.tool == EXPECTED_TOOL_NAME
    assert result.frame.code == FAILED_CODE


@pytest.mark.parametrize("handler", FAILURE_HANDLERS, ids=FAILURE_IDS)
def test_dispatch_tells_the_model_the_tool_failed__S028_002_DoD12(
    engine: Engine, generator: SnowflakeGenerator, handler: Handler
) -> None:
    """DoD-12 — the tool message content is exactly 021's failure sentence.

    The provider must really have been reached: DoD-12's setup is "the transport answering
    500" / "the transport raising", and DoD-5 pins exactly one request.
    """
    scope = _build_scope(engine, USER_A, SESSION_A)
    recorder = Recorder(handler)

    result = _dispatch(engine, generator, scope, recorder, SEAM_QUERY)

    assert len(recorder.requests) == 1
    assert result.message.content == FAILED_CONTENT


@pytest.mark.parametrize("handler", FAILURE_HANDLERS, ids=FAILURE_IDS)
def test_dispatch_writes_one_failed_tool_row__S028_002_DoD12(
    engine: Engine, generator: SnowflakeGenerator, handler: Handler
) -> None:
    """DoD-12 / 021 D7 — exactly one failed tool row, naming `web_search`."""
    scope = _build_scope(engine, USER_A, SESSION_A)
    recorder = Recorder(handler)

    _dispatch(engine, generator, scope, recorder, SEAM_QUERY)

    assert len(recorder.requests) == 1
    rows = _tool_rows(engine, SESSION_A)
    assert len(rows) == 1
    assert rows[0]["tool_name"] == EXPECTED_TOOL_NAME
    assert rows[0]["text"] == FAILED_ROW_TEXT


@pytest.mark.parametrize("handler", FAILURE_HANDLERS, ids=FAILURE_IDS)
def test_no_log_record_of_the_failure_carries_the_query_or_a_credential__S028_002_DoD12(
    engine: Engine, generator: SnowflakeGenerator, handler: Handler
) -> None:
    """DoD-12 / D7 — a sink at every level sees neither the query nor either credential.

    The seam's own record (tool name, call id, exception class) is expected and fine. Each of
    the three is forbidden in both its raw and its URL-encoded spelling: the query and the
    engine id travel in the provider's request URL, so a record quoting that URL carries the
    engine id verbatim but the query percent-encoded.
    """
    scope = _build_scope(engine, USER_A, SESSION_A)
    recorder = Recorder(handler)

    with _captured_logs() as lines:
        result = _dispatch(engine, generator, scope, recorder, SEAM_QUERY)

    assert len(recorder.requests) == 1
    assert isinstance(result.frame, ToolFailFrame)
    for line in lines:
        for forbidden in _forbidden_forms(SEAM_QUERY, API_KEY, ENGINE_ID):
            assert forbidden not in line


def test_a_successful_dispatch_logs_neither_the_query_nor_a_credential__S028_002_DoD12(
    engine: Engine, generator: SnowflakeGenerator
) -> None:
    """DoD-12 / D7 — the success path is silent about all three as well.

    The dispatch it observes must be the successful one: a `tool_result` frame whose summary
    is `3 results` (DoD-11's literal for three items), sent after exactly one request. Each of
    the three is forbidden in both its raw and its URL-encoded spelling, for the reason given
    on the failure-path case above.
    """
    scope = _build_scope(engine, USER_A, SESSION_A)
    recorder = Recorder(json_handler({"items": THREE_ITEMS}))

    with _captured_logs() as lines:
        result = _dispatch(engine, generator, scope, recorder, SEAM_QUERY)

    assert len(recorder.requests) == 1
    assert isinstance(result.frame, ToolResultFrame)
    assert result.frame.tool == EXPECTED_TOOL_NAME
    assert result.frame.summary == "3 results"
    for line in lines:
        for forbidden in _forbidden_forms(SEAM_QUERY, API_KEY, ENGINE_ID):
            assert forbidden not in line


# =========================================================================================
# DoD-13: the import shape (D3, D4)
# =========================================================================================

BACKEND_DIRECTORY = Path(__file__).resolve().parent.parent

ADAPTER_MODULE = "app.services.tools.web_search"
SEAM_MODULE = "app.services.tools.seam"

IMPORT_CASES = (
    f"import {ADAPTER_MODULE}",
    f"import {SEAM_MODULE}",
    f"import {ADAPTER_MODULE}; import {SEAM_MODULE}",
    f"import {SEAM_MODULE}; import {ADAPTER_MODULE}",
)

#: `tools/web_search.py` reads no settings, resolves no secret and touches no database (D3, D4).
BANNED_FOR_THE_ADAPTER = ("app.config", "app.secrets", "app.db")


def _module_source(module: object) -> str:
    module_file = getattr(module, "__file__", None)
    assert module_file is not None
    return Path(module_file).read_text(encoding="utf-8")


def _imported_modules(source: str) -> set[str]:
    """Every imported dotted name in the source, read as text (never through `sys.modules`)."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _under(name: str, package: str) -> bool:
    return name == package or name.startswith(package + ".")


@pytest.mark.parametrize("code", IMPORT_CASES, ids=["adapter", "seam", "adapter-first", "seam-first"])
def test_each_module_imports_cleanly_in_a_fresh_interpreter__S028_002_DoD13(code: str) -> None:
    """DoD-13 — either module imports alone, and either order works: no import cycle."""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIRECTORY,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("which", ["adapter", "seam"])
def test_neither_module_imports_a_web_framework__S028_002_DoD13(which: str) -> None:
    """DoD-13 — neither module imports `fastapi`.

    Checked against the module **source**, not `sys.modules`: `app/errors.py` imports the web
    framework and the adapter imports `ToolFailedError` from it, so a `sys.modules` probe would
    answer a different question.
    """
    module = adapter_module if which == "adapter" else seam_module

    offenders = [
        name
        for name in _imported_modules(_module_source(module))
        if _under(name, "fastapi") or _under(name, "starlette")
    ]

    assert offenders == []


@pytest.mark.parametrize("package", BANNED_FOR_THE_ADAPTER)
def test_the_adapter_imports_nothing_from_settings_secrets_or_the_database__S028_002_DoD13(
    package: str,
) -> None:
    """DoD-13 / D3 — only the router reads settings; the adapter takes plain values."""
    offenders = [
        name for name in _imported_modules(_module_source(adapter_module)) if _under(name, package)
    ]

    assert offenders == []
