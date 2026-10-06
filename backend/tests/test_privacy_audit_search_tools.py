"""Search, tools, context and index-write sweep — step 004 of feature 032, DoD-1..DoD-10.

Specification: ``docs/plans/032.privacy-isolation-audit/004.search-and-tools-sweep.md``
(Definition of done items 1..10, every one ``[test]``; there is no ``[manual/live]``
item), with ``004.context.md`` for the declared behaviour each clause re-asserts and
``context.md`` for the shared vocabulary, the sentinel convention and the leak-fix
policy. Every expected value here comes from those documents; the frozen
support-module record in ``status.md`` supplies only *how to call*.

Requirement covered by every item: **US-085.AC-1**.

This is an **audit** module: it re-asserts in one place that my-search, the hybrid
search port, the three assistant tools, context assembly and the vector/FTS write
paths never return, pass on or touch another user's material, even when the model or
the caller names the other user's ids. The built code is expected to satisfy all of
it, so a failure here is a **leak finding**, not a test defect — with exactly one
deliberate exception, named below.

The one case expected to fail before the fix
--------------------------------------------
``test_refresh_session_vectors_keeps_a_foreign_sessions_vector__S032_004_DoD9`` pins
the finding the harvest made (orchestrator decision 19): the session-vector refresh
deletes a session's ``session_vec`` row **without an owner predicate**, so a refresh
run with A's user id and B's session id removes B's vector. It is not reachable from
any route — every caller passes owner-scoped ids — but it is exactly what
``context.md``'s leak-fix policy calls a *small leak* ("an owner predicate missing
from one query") and it sits inside this step's fix-allowance. The test asserts the
spec-correct behaviour (B's row is left intact), so it is **red until the fix lands**
and green afterwards. It lives in a function of its own precisely so that its
failure cannot be mistaken for a DoD-9/DoD-10 route failure.

Two clauses whose stated witness had to change, both narrowings to the guarantee
---------------------------------------------------------------------------------
* **DoD-1 is not "all five groups empty"** (orchestrator decision 10). My-search's
  vector arm has no similarity cutoff: it returns the nearest rows *of the caller's
  own* material whatever the query, so A searching for B's sentinel legitimately
  gets A's own memos and sessions back. The audit's claim — ``brief.md``'s "no
  search reaches another user's material" — is **"no group contains any B id or any
  B sentinel"**, and that is what is asserted, with the positive control (B's
  identical request returns the sentinel's item) kept intact.
* **DoD-6 excludes ``tool_args`` and pins it instead** (orchestrator decision 11).
  ``tool_args`` echoes the model-supplied arguments, and the fake model here is
  instructed *by this test* to name B's ids and sentinels, so a literal "no B id in
  the tool rows" reading would fail on the test's own input. The absence is
  asserted on the tool **results** and the assistant message; ``tool_args`` and the
  stored ``arguments`` are compared by **exact equality** against what the fake was
  scripted to send, so nothing database-derived can hide in them.

Mechanics
---------
* The shared two-user world comes from step 002's support module. ``audit_world``
  installs all four model seams itself, atomically; **this module never sets one of
  those override keys** and never makes a network request (the web search is
  captured at the recorder's ``httpx.MockTransport``).
* Five test functions, each building the world exactly once, because the world is
  expensive (``conftest.py``'s ``db_settings`` is function-scoped). Per-clause
  granularity lives in the failure messages — each names the service, the variant
  and the ids — not in the number of world builds.
* Index snapshots never use a plain ``SELECT`` on an FTS table (decision 18): an
  external-content table reads through to its base table, so the before/after
  comparison uses ``MATCH`` and the ``*_docsize`` shadow tables, as step 002's
  DoD-4 does. There is no ``session_fts``.
"""

import asyncio
import json
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, select, text

from app.config import Settings
from app.db import schema
from app.errors import SessionNotFoundError
from app.services.context import AssembledContext, assemble_context
from app.services.search.hybrid import search
from app.services.search.memo_search import search_memos
from app.services.search.ports import EntrySearchScope, MemoSearchScope, SearchHit, SessionSearchScope
from app.services.search.session_search import SessionExcerpt, list_session_excerpts, search_sessions
from app.services.session_index import refresh_session_vectors
from app.services.tools.seam import Tool, ToolOutcome, ToolScope, build_tool_scope
from app.services.web_search.provider import WebResult
from tests.privacy_audit_support import (
    COMPOSE_TIMEOUT_SECONDS,
    MEMO_REACHES,
    MEMO_SCOPES,
    MEMO_SEARCH_NAME,
    SESSION_SEARCH_NAME,
    UNKNOWN_ID,
    WEB_SEARCH_NAME,
    AuditUser,
    AuditWorld,
    assert_envelope,
    assert_no_identifier_of,
    assert_no_sentinel_of_user,
    audit_world,
    memo_carrier_field,
    rendered_text,
    text_round,
    tool_call_round,
)

# --- constants ------------------------------------------------------------------------

#: The five my-search result groups, in the order the response declares them
#: (029/003 DoD-5 as cited by `004.context.md`). Asserted as the exact top-level key
#: set, so a response that echoed the query back could not hide inside the sweep.
SEARCH_GROUPS: tuple[str, ...] = ("characters", "setups", "sessions", "entries", "memos")

#: The depth every direct port call asks for. The port's own arm depth is 50, so this
#: asks for every candidate the arms can produce: an absence at this depth is not an
#: artefact of a small limit.
PORT_LIMIT = 50

#: Bound on one awaited tool `run`, in seconds. Mirrors the suite's tool-test precedent.
TOOL_TIMEOUT_SECONDS = 30.0

#: Tokens this module writes or sends. They are not registry sentinels, so they can
#: never be confused with seeded content, and each is a single lowercase alphanumeric
#: word so FTS5 and LIKE both see one term.
PROBE_WRITE = "probewriteaudit032004"
PROBE_MEMO = "probecontextmemo032004"
PROBE_WEB = "probewebquery032004"
PROBE_REPLY = "probeassistantreply032004"
PROBE_EDIT = "probeeditedentry032004"

#: `context.md`'s enumeration: the 404 code each foreign-id write attempt answers with
#: (rows 37, 39, 40, 45, 48, 49). The expected code is the table's, never the code's.
FOREIGN_WRITE_CODES: Mapping[str, str] = {
    "zone message": "session_not_found",
    "settle": "session_not_found",
    "reopen": "session_not_found",
    "message edit": "message_not_found",
    "memo edit": "memo_not_found",
    "memo delete": "memo_not_found",
}

#: The derived stores a write path can touch, as step 002 froze them. There is no
#: `session_fts`; `message_fts` indexes settled, unburied rows only.
MEMO_VEC = "memo_vec"
SESSION_VEC = "session_vec"
MEMO_FTS = "memo_fts"
MESSAGE_FTS = "message_fts"


# --- fixture --------------------------------------------------------------------------


@pytest.fixture
def world(db_settings: Settings, db_engine: Engine) -> Iterator[AuditWorld]:
    """The shared two-user audit world.

    `real_logging=False` is the default: only step 007 wants the real
    `configure_logging`. The four model seams are installed by `audit_world` itself,
    atomically; this module never sets one of those override keys.
    """
    with audit_world(db_settings, db_engine) as built:
        yield built


# --- generic helpers ------------------------------------------------------------------


def _ok(response: Any, status: int) -> Any:
    assert response.status_code == status, f"{response.request.method} {response.request.url}: {response.text}"
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def _frames(body: str) -> list[dict[str, Any]]:
    """Parse an SSE body into its `data:` frames."""
    frames: list[dict[str, Any]] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("data:"):
            frames.append(json.loads(stripped.removeprefix("data:").strip()))
    return frames


def _compose(client: TestClient, session_id: str, body_text: str) -> list[dict[str, Any]]:
    """One compose exchange, posted on a worker thread with a bound (compose streams SSE)."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            client.post, f"/api/sessions/{session_id}/zone/compose", json={"text": body_text}
        )
        response = future.result(timeout=COMPOSE_TIMEOUT_SECONDS)
    assert response.status_code == 200, response.text
    frames = _frames(response.text)
    errors = [frame for frame in frames if frame.get("event") == "error"]
    assert not errors, errors
    return frames


def _zone_rows(client: TestClient, session_id: str) -> list[dict[str, Any]]:
    body = _ok(client.get(f"/api/sessions/{session_id}/zone"), 200)
    rows = body["messages"]
    assert isinstance(rows, list), body
    return [dict(row) for row in rows]


def _stored_tool_ids(engine: Engine, session_id: str) -> set[str]:
    """Every stored tool-row id of one session, zone and buried alike."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(schema.messages.c.id)
            .where(schema.messages.c.role == "tool")
            .where(schema.messages.c.session_id == int(session_id))
        ).all()
    return {str(row[0]) for row in rows}


def _hit_ids(hits: Sequence[SearchHit]) -> set[int]:
    return {hit.id for hit in hits}


def _hit_payload(hits: Sequence[SearchHit]) -> list[dict[str, Any]]:
    """Every hit field as JSON-able data, with ids as decimal strings.

    Ids are rendered as strings so the absence assertions — which search the rendered
    text for a decimal id — really see them.
    """
    return [
        {
            "kind": str(hit.kind),
            "id": str(hit.id),
            "score": hit.score,
            "snippet": hit.snippet,
            "memo_scope": None if hit.memo_scope is None else str(hit.memo_scope),
            "memo_scope_id": None if hit.memo_scope_id is None else str(hit.memo_scope_id),
            "session_id": None if hit.session_id is None else str(hit.session_id),
        }
        for hit in hits
    ]


def _excerpt_payload(records: Sequence[SessionExcerpt]) -> list[dict[str, Any]]:
    return [
        {
            "session_id": str(record.session_id),
            "created_date": str(record.created_date),
            "setup_name": record.setup_name,
            "excerpt": record.excerpt,
        }
        for record in records
    ]


def _context_payload(context: AssembledContext) -> dict[str, Any]:
    """The whole assembled context as JSON-able data: nothing it carries is skipped."""
    messages: list[dict[str, Any]] = []
    for message in context.messages:
        messages.append(
            {
                "role": str(message.role),
                "content": message.content,
                "tool_calls": [
                    {"call_id": call.call_id, "name": call.name, "arguments": call.arguments}
                    for call in message.tool_calls
                ],
                "tool_call_id": message.tool_call_id,
            }
        )
    return {"system_prompt": context.system_prompt, "messages": messages}


def _run_tool(tool: Tool, scope: ToolScope, engine: Engine, arguments: Mapping[str, object]) -> ToolOutcome:
    """Await one adapter's `run` on a connection of its own, from a sync test."""
    with engine.connect() as connection:
        return asyncio.run(
            asyncio.wait_for(tool.run(scope, connection, arguments), timeout=TOOL_TIMEOUT_SECONDS)
        )


def _rendered_request(request: Any) -> str:
    """The outbound request's URL plus every header name and value, as one string."""
    headers = " ".join(f"{name}:{value}" for name, value in request.headers.items())
    return f"{request.url} {headers}"


# --- derived-store reads (decision 18: never a plain SELECT on an FTS table) ----------


def _table_exists(connection: Connection, table_name: str) -> bool:
    row = connection.execute(
        text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
        {"name": table_name},
    ).first()
    return row is not None


def _key_column(connection: Connection, table_name: str) -> str | None:
    """A `vec0` table's key column, or `None` when the table does not exist."""
    rows = connection.execute(
        text("SELECT name FROM pragma_table_info(:table_name) WHERE pk = 1"),
        {"table_name": table_name},
    ).all()
    return None if not rows else str(rows[0][0])


def _vector_rows(connection: Connection, table_name: str, row_ids: Sequence[int]) -> dict[str, str]:
    """The stored blob of each named key, hex-encoded so a diff is readable."""
    key = _key_column(connection, table_name)
    if key is None:
        return {}
    stored: dict[str, str] = {}
    for row_id in row_ids:
        blob = connection.execute(
            text(f"SELECT embedding FROM {table_name} WHERE {key} = :row_id"),
            {"row_id": row_id},
        ).scalar_one_or_none()
        if blob is not None:
            stored[str(row_id)] = bytes(blob).hex()
    return stored


def _docsize_rows(connection: Connection, table_name: str, row_ids: Sequence[int]) -> dict[str, str]:
    """The `*_docsize` shadow row of each named id — a real index snapshot."""
    shadow = f"{table_name}_docsize"
    if not _table_exists(connection, shadow):
        return {}
    wanted = {int(one) for one in row_ids}
    rows = connection.execute(text(f"SELECT id, sz FROM {shadow}")).all()
    return {
        str(int(row[0])): _readable(row[1]) for row in rows if int(row[0]) in wanted
    }


def _readable(value: Any) -> str:
    """A stable, printable form of a shadow-table cell, blob or integer alike."""
    if isinstance(value, bytes | bytearray):
        return bytes(value).hex()
    return str(value)


def _match_ids(connection: Connection, table_name: str, token: str) -> list[str]:
    """The rowids an FTS `MATCH` returns, ascending; `[]` when the table does not exist."""
    if not _table_exists(connection, table_name):
        return []
    rows = connection.execute(
        text(f"SELECT rowid FROM {table_name} WHERE {table_name} MATCH :token ORDER BY rowid"),
        {"token": token},
    ).all()
    return [str(int(row[0])) for row in rows]


def _memo_sentinels_of(world: AuditWorld, user: AuditUser) -> dict[str, str]:
    """Every memo-body sentinel of one user, by its carrier field."""
    found: dict[str, str] = {}
    for scope in MEMO_SCOPES:
        for reach in MEMO_REACHES:
            field = memo_carrier_field(scope, reach)
            found[field] = world.sentinels.get(user=user, table="memos", field=field)
    return found


def _record_message_sentinels_of(world: AuditWorld, user: AuditUser) -> dict[str, str]:
    """The sentinels of one user that sit in a settled, unburied row — all `message_fts` holds."""
    return {
        field: world.sentinels.get(user=user, table="messages", field=field)
        for field in ("text[partner]", "text[turn]", "text[decision]")
    }


def _index_snapshot(world: AuditWorld, user: AuditUser) -> dict[str, Any]:
    """Every derived-store row keyed to one user's ids, plus what a `MATCH` finds.

    Four readings per store, because any of them could change independently: the stored
    vector blob, the FTS `*_docsize` shadow row, and the rowid list a `MATCH` on each of
    that user's sentinels returns.
    """
    content = world.content_of(user)
    memo_ids = [int(one) for one in content.memos.all_ids()]
    session_ids = [int(one) for one in content.all_session_ids()]
    message_ids = [int(one) for one in content.messages.all_ids()]
    with world.engine.connect() as connection:
        return {
            "memo_vec": _vector_rows(connection, MEMO_VEC, memo_ids),
            "session_vec": _vector_rows(connection, SESSION_VEC, session_ids),
            "memo_fts_docsize": _docsize_rows(connection, MEMO_FTS, memo_ids),
            "message_fts_docsize": _docsize_rows(connection, MESSAGE_FTS, message_ids),
            "memo_fts_match": {
                field: _match_ids(connection, MEMO_FTS, sentinel)
                for field, sentinel in _memo_sentinels_of(world, user).items()
            },
            "message_fts_match": {
                field: _match_ids(connection, MESSAGE_FTS, sentinel)
                for field, sentinel in _record_message_sentinels_of(world, user).items()
            },
        }


def _snapshot_differences(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Every section that moved, named with both values — one line per section."""
    differences: list[str] = []
    for section in before:
        if before[section] != after[section]:
            differences.append(f"{section}: before={before[section]!r} after={after[section]!r}")
    return differences


def _assert_snapshot_is_not_empty(snapshot: Mapping[str, Any], *, user: str) -> None:
    """Anti-vacuity: the stores really hold rows of this user, so "unchanged" means something."""
    assert snapshot["memo_vec"], f"{user} has no memo_vec row: an unchanged-index assertion would be vacuous"
    assert snapshot["session_vec"], f"{user} has no session_vec row: the snapshot would be vacuous"
    assert snapshot["memo_fts_docsize"], f"{user} has no memo_fts index row: the snapshot would be vacuous"
    assert snapshot["message_fts_docsize"], f"{user} has no message_fts index row: the snapshot would be vacuous"


# --- DoD-1 -----------------------------------------------------------------------------


def _searchable_b_targets(world: AuditWorld) -> list[tuple[str, str, str, str]]:
    """`(label, B's sentinel, the group it belongs to, the id of the item carrying it)`.

    Only sentinels my-search can actually reach are listed, because DoD-1's positive
    control has to hold for each one: the two LIKE corpora (`characters` by name and
    sheet, `setups` by name and description), the FTS corpus over **settled, unburied**
    record rows (`entries`), and the memo corpus (every reach — my-search legitimately
    shows the owner's disabled memos, R3). The zone, buried, assistant and tool-payload
    sentinels are deliberately absent: `message_fts` does not index those rows, so no
    search of either user could ever return them.
    """
    b = world.b

    def sentinel(table: str, field: str) -> str:
        return world.sentinels.get(user="B", table=table, field=field)

    targets: list[tuple[str, str, str, str]] = [
        ("characters.name", sentinel("characters", "name"), "characters", b.character_id),
        ("characters.sheet", sentinel("characters", "sheet"), "characters", b.character_id),
        ("setups.name", sentinel("setups", "name"), "setups", b.setup_id),
        ("setups.description", sentinel("setups", "description"), "setups", b.setup_id),
        ("messages.text[partner]", sentinel("messages", "text[partner]"), "entries", b.messages.partner_id),
        ("messages.text[turn]", sentinel("messages", "text[turn]"), "entries", b.messages.turn_head_id),
        ("messages.text[decision]", sentinel("messages", "text[decision]"), "entries", b.messages.decision_id),
        # The session_vec sentinel is seeded into the settled partner block, so the
        # entries corpus is where B's own request finds it.
        ("session_vec.embedded_text", sentinel("session_vec", "embedded_text"), "entries", b.messages.partner_id),
        # The memo_vec sentinel is seeded into the searchable user-scope memo body.
        (
            "memo_vec.embedded_text",
            sentinel("memo_vec", "embedded_text"),
            "memos",
            b.memos.of("user", "searchable"),
        ),
    ]
    for scope in MEMO_SCOPES:
        for reach in MEMO_REACHES:
            field = memo_carrier_field(scope, reach)
            targets.append((f"memos.{field}", sentinel("memos", field), "memos", b.memos.of(scope, reach)))
    return targets


def test_my_search_reaches_no_other_users_material__S032_004_DoD1(world: AuditWorld) -> None:
    """Covers DoD-1 (US-085.AC-1).

    `GET /api/search?q=<B sentinel>` as A, for every searchable B sentinel: the response
    carries the five groups and **no B id and no B sentinel in any of them**, while B's
    identical request returns the sentinel's own item (the positive control, so the
    absence can never pass vacuously).

    Narrowing, deliberate and recorded (orchestrator decision 10): the DoD's "all five
    result groups empty" is impossible for `sessions` and `memos` while the caller owns
    indexed rows, because the vector arm has no similarity cutoff and always returns the
    nearest of **the caller's own** candidates. The guarantee the clause exists to prove
    — `brief.md`'s "no search reaches another user's material" — is the id/sentinel
    absence asserted here, and a leak would still fail it.

    The queried sentinel itself is the one carve-out passed to `allowed=`, for the same
    reason decision 11 gives for `tool_args`: it is A's own request text, not B material.
    The exact five-key assertion keeps that carve-out from hiding anything, since the
    response has nowhere else to echo it.
    """
    problems: list[str] = []
    targets = _searchable_b_targets(world)
    assert len(targets) == 21, f"the searchable-target list changed shape: {len(targets)}"

    for label, sentinel, group, expected_id in targets:
        as_a = _ok(world.clients.a.get("/api/search", params={"q": sentinel}), 200)
        try:
            assert list(as_a) == list(SEARCH_GROUPS), f"group keys are {list(as_a)}"
            assert_no_identifier_of(as_a, content=world.b)
            assert_no_sentinel_of_user(as_a, registry=world.sentinels, user="B", allowed=(sentinel,))
        except AssertionError as error:
            problems.append(f"GET /api/search?q=<B {label}> as A: {error}")

        as_b = _ok(world.clients.b.get("/api/search", params={"q": sentinel}), 200)
        returned = [str(one["id"]) for one in as_b[group]]
        if expected_id not in returned:
            problems.append(
                f"positive control failed: B's own GET /api/search?q=<B {label}> did not return "
                f"{group} item {expected_id}; {group} held {returned}"
            )

    assert not problems, "my-search reached another user's material:\n" + "\n".join(problems)


# --- DoD-2, DoD-3 ----------------------------------------------------------------------


def test_search_services_scope_every_read_to_the_caller__S032_004_DoD2_DoD3(world: AuditWorld) -> None:
    """Covers DoD-2 and DoD-3 (US-085.AC-1).

    DoD-2 — each of the hybrid port's three scope variants, called with **A's** user id
    and a query that matches only B's material, returns no candidate belonging to B; the
    same call with **B's** user id returns it. Both halves matter: the `vec0` and FTS5
    tables carry **no** user column (`004.context.md`), so the whole guarantee rests on
    the candidate subquery, and the embedding fake maps each sentinel to a distinct
    stable vector — a nearest-neighbour hit on B's row would be certain if the user
    predicate were missing.

    DoD-3 — the memo-search and session-search services called with **A's** scope and a
    B-targeting query return no B memo, session or excerpt, with B's own call as the
    positive control for each. 026's predicate is `is_enabled AND NOT is_forced` (R3),
    so B's *searchable* memos are the meaningful targets.
    """
    a, b = world.a, world.b
    factory = world.fakes.embedding_factory
    b_ids = {int(one) for one in b.all_ids()}
    b_memo_sentinel = world.sentinels.get(user="B", table="memos", field=memo_carrier_field("user", "searchable"))
    b_session_sentinel = world.sentinels.get(user="B", table="session_vec", field="embedded_text")
    b_entry_sentinel = world.sentinels.get(user="B", table="messages", field="text[partner]")
    b_chain_memo = int(b.memos.of("session", "searchable"))
    problems: list[str] = []

    def port(scope: Any, query_text: str) -> list[SearchHit]:
        with world.engine.connect() as connection:
            return search(connection, scope, query_text, PORT_LIMIT, client_factory=factory)

    # --- DoD-2: the three variants, A's id then B's id, same query each time.
    variants: tuple[tuple[str, Any, Any, str, int], ...] = (
        (
            "MemoSearchScope",
            MemoSearchScope(user_id=int(a.identity.user_id)),
            MemoSearchScope(user_id=int(b.identity.user_id)),
            b_memo_sentinel,
            int(b.memos.of("user", "searchable")),
        ),
        (
            "SessionSearchScope",
            SessionSearchScope(user_id=int(a.identity.user_id)),
            SessionSearchScope(user_id=int(b.identity.user_id)),
            b_session_sentinel,
            int(b.session_with_setup_id),
        ),
        (
            "EntrySearchScope",
            EntrySearchScope(user_id=int(a.identity.user_id)),
            EntrySearchScope(user_id=int(b.identity.user_id)),
            b_entry_sentinel,
            int(b.messages.partner_id),
        ),
    )
    for name, a_scope, b_scope, query, expected_id in variants:
        hits = port(a_scope, query)
        crossed = sorted(_hit_ids(hits) & b_ids)
        if crossed:
            problems.append(f"{name} with A's user id and a B-targeting query returned B rows {crossed}")
        try:
            assert_no_sentinel_of_user(_hit_payload(hits), registry=world.sentinels, user="B")
        except AssertionError as error:
            problems.append(f"{name} with A's user id: {error}")

        owner_hits = port(b_scope, query)
        if expected_id not in _hit_ids(owner_hits):
            problems.append(
                f"positive control failed: {name} with B's own user id did not return {expected_id}; "
                f"it returned {sorted(_hit_ids(owner_hits))}"
            )

    # --- DoD-3: 026's memo search and 027's session search and excerpts.
    query = f"{b_memo_sentinel} {b_session_sentinel} {b_entry_sentinel}"
    with world.engine.connect() as connection:
        a_memo_hits = search_memos(
            connection,
            user_id=int(a.identity.user_id),
            character_id=int(a.character_id),
            setup_id=int(a.setup_id),
            session_id=int(a.session_with_setup_id),
            query_text=query,
            client_factory=factory,
        )
        b_memo_hits = search_memos(
            connection,
            user_id=int(b.identity.user_id),
            character_id=int(b.character_id),
            setup_id=int(b.setup_id),
            session_id=int(b.session_with_setup_id),
            query_text=query,
            client_factory=factory,
        )
        a_session_hits = search_sessions(
            connection,
            user_id=int(a.identity.user_id),
            character_id=int(a.character_id),
            current_session_id=int(a.session_without_setup_id),
            query_text=query,
            client_factory=factory,
        )
        b_session_hits = search_sessions(
            connection,
            user_id=int(b.identity.user_id),
            character_id=int(b.character_id),
            current_session_id=int(b.session_without_setup_id),
            query_text=query,
            client_factory=factory,
        )
        a_excerpts = list_session_excerpts(
            connection, int(a.identity.user_id), [int(b.session_with_setup_id)]
        )
        b_excerpts = list_session_excerpts(
            connection, int(b.identity.user_id), [int(b.session_with_setup_id)]
        )

    crossed = sorted(_hit_ids(a_memo_hits) & b_ids)
    if crossed:
        problems.append(f"search_memos with A's scope returned B memos {crossed}")
    try:
        assert_no_sentinel_of_user(_hit_payload(a_memo_hits), registry=world.sentinels, user="B")
    except AssertionError as error:
        problems.append(f"search_memos with A's scope: {error}")
    if b_chain_memo not in _hit_ids(b_memo_hits):
        problems.append(
            "positive control failed: search_memos with B's own scope did not return B's searchable "
            f"session-scope memo {b_chain_memo}; it returned {sorted(_hit_ids(b_memo_hits))}"
        )

    crossed = sorted(_hit_ids(a_session_hits) & b_ids)
    if crossed:
        problems.append(f"search_sessions with A's scope returned B sessions {crossed}")
    try:
        assert_no_sentinel_of_user(_hit_payload(a_session_hits), registry=world.sentinels, user="B")
    except AssertionError as error:
        problems.append(f"search_sessions with A's scope: {error}")
    if int(b.session_with_setup_id) not in _hit_ids(b_session_hits):
        problems.append(
            "positive control failed: search_sessions with B's own scope did not return B's past "
            f"session {b.session_with_setup_id}; it returned {sorted(_hit_ids(b_session_hits))}"
        )

    if a_excerpts:
        problems.append(
            f"list_session_excerpts with A's user id and B's session id returned {_excerpt_payload(a_excerpts)}"
        )
    try:
        assert_no_sentinel_of_user(_excerpt_payload(a_excerpts), registry=world.sentinels, user="B")
    except AssertionError as error:
        problems.append(f"list_session_excerpts with A's user id: {error}")
    if [record.session_id for record in b_excerpts] != [int(b.session_with_setup_id)]:
        problems.append(
            "positive control failed: list_session_excerpts with B's own user id did not return B's "
            f"session; it returned {_excerpt_payload(b_excerpts)}"
        )
    elif b_entry_sentinel not in b_excerpts[0].excerpt:
        problems.append(
            "positive control failed: B's own excerpt does not carry B's settled partner sentinel, so "
            "the excerpt absence above would be vacuous"
        )

    assert not problems, "a search service reached another user's material:\n" + "\n".join(problems)


# --- DoD-4, DoD-5, DoD-6, DoD-7, DoD-8 -------------------------------------------------


def test_tools_and_context_never_cross_the_owner_boundary__S032_004_DoD4_DoD5_DoD6_DoD7_DoD8(
    world: AuditWorld,
) -> None:
    """Covers DoD-4, DoD-5, DoD-6, DoD-7 and DoD-8 (US-085.AC-1).

    DoD-5 first, because it is the cheapest: building a tool scope for B's session on
    A's behalf fails with `session_not_found` and produces no scope — indistinguishably
    from an unknown id.

    DoD-4 — the two database-backed adapters, given the scope built from **A's** session
    and model-supplied arguments that add B's user, session, character and setup ids as
    **extra keys** plus a B-targeting query, return no B material. 021's declarations
    expose only `query`, so extra keys must never alter scope. The same adapters with a
    scope built from B's own session do return B's material: the positive control.

    DoD-8 — context assembled for A's session carries no B sentinel and vice versa,
    including the `003` DoD-6 case: a memo A created naming B's scope id. Asserted
    **before** the compose exchanges below, because those deliberately put B's ids into
    A's own tool-call arguments, which context assembly legitimately replays.

    DoD-6 — end to end: A composes in A's session while the fake model issues
    `memo_search` and `session_search` calls whose arguments name B's ids and B's
    sentinels; the tool rows and the assistant message written to A's zone carry no B
    sentinel and no B id. `tool_args` (and the stored raw `arguments`) are excluded from
    the absence sweep and **pinned by exact equality** to what the fake was scripted to
    send, per orchestrator decision 11 — so nothing database-derived can hide there.

    DoD-7 — the outbound web-search request carries the model-supplied query and nothing
    else from the instance: no seeded row id of **either** user, and no sentinel other
    than the one the query itself contains. Captured at the recorder's
    `httpx.MockTransport`, which is also the safety mechanism that makes this step
    network-free.
    """
    a, b = world.a, world.b
    engine = world.engine
    registry = world.fakes.tool_registry
    b_memo_sentinel = world.sentinels.get(user="B", table="memos", field=memo_carrier_field("user", "searchable"))
    b_entry_sentinel = world.sentinels.get(user="B", table="messages", field="text[partner]")
    b_chain_sentinel = world.sentinels.get(
        user="B", table="memos", field=memo_carrier_field("session", "searchable")
    )

    # --- DoD-5 -------------------------------------------------------------------------
    with engine.connect() as connection:
        with pytest.raises(SessionNotFoundError) as foreign:
            build_tool_scope(connection, int(a.identity.user_id), int(b.session_with_setup_id))
        with pytest.raises(SessionNotFoundError) as unknown:
            build_tool_scope(connection, int(a.identity.user_id), int(UNKNOWN_ID))
        scope_a_main = build_tool_scope(
            connection, int(a.identity.user_id), int(a.session_with_setup_id)
        )
        scope_a_other = build_tool_scope(
            connection, int(a.identity.user_id), int(a.session_without_setup_id)
        )
        scope_b_main = build_tool_scope(
            connection, int(b.identity.user_id), int(b.session_with_setup_id)
        )
        scope_b_other = build_tool_scope(
            connection, int(b.identity.user_id), int(b.session_without_setup_id)
        )

    assert foreign.value.code == "session_not_found", foreign.value
    assert unknown.value.code == "session_not_found", unknown.value
    # The positive control for "no scope is produced": the same call for A's own session
    # does produce one, carrying only A's ids.
    assert scope_a_main.user_id == int(a.identity.user_id), scope_a_main
    assert scope_a_main.session_id == int(a.session_with_setup_id), scope_a_main
    assert scope_a_main.character_id == int(a.character_id), scope_a_main
    assert scope_a_main.setup_id == int(a.setup_id), scope_a_main

    # --- DoD-4 -------------------------------------------------------------------------
    arguments: Mapping[str, object] = {
        "query": f"{b_memo_sentinel} {b_chain_sentinel} {b_entry_sentinel}",
        "user_id": b.identity.user_id,
        "session_id": b.session_with_setup_id,
        "character_id": b.character_id,
        "setup_id": b.setup_id,
    }
    problems: list[str] = []
    adapter_cases: tuple[tuple[str, ToolScope, ToolScope, str], ...] = (
        (MEMO_SEARCH_NAME, scope_a_main, scope_b_main, b_chain_sentinel),
        (SESSION_SEARCH_NAME, scope_a_other, scope_b_other, b_entry_sentinel),
    )
    for name, a_scope, b_scope, owner_marker in adapter_cases:
        outcome = _run_tool(registry[name], a_scope, engine, arguments)
        rendered = {"content": outcome.content, "summary": outcome.summary}
        try:
            assert_no_sentinel_of_user(rendered, registry=world.sentinels, user="B")
            assert_no_identifier_of(rendered, content=b)
        except AssertionError as error:
            problems.append(f"{name} with A's scope and B-naming arguments: {error}")

        owner_outcome = _run_tool(registry[name], b_scope, engine, arguments)
        if owner_marker not in owner_outcome.content:
            problems.append(
                f"positive control failed: {name} with B's own scope and the same arguments did not "
                f"return B's material; content was {owner_outcome.content!r}"
            )
    assert not problems, "a tool adapter reached another user's material:\n" + "\n".join(problems)

    # --- DoD-8 -------------------------------------------------------------------------
    # The `003` DoD-6 case: a memo A created naming B's scope id. The three parented
    # scopes answer 404 for a foreign `scope_id`, and the `user` scope drops `scope_id`
    # altogether, so the surviving shape of that case is a memo of A's own whose body
    # names B's session id. It is made **forced** so it really reaches context assembly
    # (only reach "forced" does), and removed again afterwards so it cannot colour the
    # compose clauses below.
    probe_memo = _ok(
        world.clients.a.post(
            "/api/memos",
            json={"scope": "user", "body": f"{PROBE_MEMO} {b.session_with_setup_id}"},
        ),
        201,
    )
    probe_memo_id = str(probe_memo["id"])
    _ok(world.clients.a.patch(f"/api/memos/{probe_memo_id}", json={"is_forced": True}), 200)

    with engine.connect() as connection:
        a_context = _context_payload(
            assemble_context(connection, int(a.identity.user_id), int(a.session_with_setup_id))
        )
        b_context = _context_payload(
            assemble_context(connection, int(b.identity.user_id), int(b.session_with_setup_id))
        )

    assert_no_sentinel_of_user(a_context, registry=world.sentinels, user="B")
    assert_no_sentinel_of_user(b_context, registry=world.sentinels, user="A")
    assert PROBE_MEMO in rendered_text(a_context), (
        "positive control failed: A's own forced memo naming B's scope id is absent from A's own "
        "context, so the absence from B's context would be vacuous"
    )
    assert PROBE_MEMO not in rendered_text(b_context), "A's memo naming B's scope id reached B's context"
    _ok(world.clients.a.delete(f"/api/memos/{probe_memo_id}"), 204)

    # --- DoD-6 -------------------------------------------------------------------------
    memo_arguments = json.dumps(
        {
            "query": f"{b_memo_sentinel} {b_chain_sentinel}",
            "user_id": b.identity.user_id,
            "session_id": b.session_with_setup_id,
            "character_id": b.character_id,
            "setup_id": b.setup_id,
        }
    )
    session_arguments = json.dumps(
        {
            "query": f"{b_entry_sentinel} {b_memo_sentinel}",
            "user_id": b.identity.user_id,
            "session_id": b.session_with_setup_id,
            "character_id": b.character_id,
            "setup_id": b.setup_id,
        }
    )
    scripted: Mapping[str, str] = {
        MEMO_SEARCH_NAME: memo_arguments,
        SESSION_SEARCH_NAME: session_arguments,
    }
    world.fakes.chat_factory.script(
        tool_call_round(name=MEMO_SEARCH_NAME, arguments=memo_arguments, call_id="audit-004-memo"),
        tool_call_round(name=SESSION_SEARCH_NAME, arguments=session_arguments, call_id="audit-004-session"),
        text_round(f"{PROBE_REPLY} reply"),
    )
    before_ids = {str(row["id"]) for row in _zone_rows(world.clients.a, a.session_with_setup_id)}
    # The seeded tool row of A's session is **buried**, so it is not in the zone snapshot
    # above; the stored sweep below needs its own "before" set or it would compare the
    # seeded row's arguments against this test's script.
    before_tool_ids = _stored_tool_ids(engine, a.session_with_setup_id)
    frames = _compose(world.clients.a, a.session_with_setup_id, f"{PROBE_WRITE} compose")
    done = [frame for frame in frames if frame.get("event") == "done"]
    assert len(done) == 1, frames
    assistant_id = str(done[0]["message_id"])

    rows = _zone_rows(world.clients.a, a.session_with_setup_id)
    new_rows = [row for row in rows if str(row["id"]) not in before_ids]
    tool_rows = [row for row in new_rows if row["role"] == "tool"]
    assistant_rows = [row for row in new_rows if str(row["id"]) == assistant_id]
    assert len(assistant_rows) == 1, new_rows
    assert {str(row["tool_name"]) for row in tool_rows} == set(scripted), (
        f"the compose exchange did not write one tool row per scripted call: {tool_rows}"
    )

    for row in tool_rows:
        name = str(row["tool_name"])
        # decision 11: `tool_args` echoes the arguments this very test told the fake to
        # send, so it is excluded from the absence sweep — and pinned here by exact
        # equality to the whole scripted literal, which is what keeps it armed.
        assert row["tool_args"] == json.loads(scripted[name]), (name, row["tool_args"])
        remainder = {key: value for key, value in row.items() if key != "tool_args"}
        assert_no_sentinel_of_user(remainder, registry=world.sentinels, user="B")
        assert_no_identifier_of(remainder, content=b)
    assert_no_sentinel_of_user(assistant_rows[0], registry=world.sentinels, user="B")
    assert_no_identifier_of(assistant_rows[0], content=b)

    # The stored rows, not just the wire: `tool_payload.content` is the full tool result
    # and never reaches the wire, so it is swept here, with the raw `arguments` string
    # pinned by the same exact equality.
    with engine.connect() as connection:
        stored = connection.execute(
            select(schema.messages.c.id, schema.messages.c.tool_name, schema.messages.c.tool_payload)
            .where(schema.messages.c.role == "tool")
            .where(schema.messages.c.session_id == int(a.session_with_setup_id))
            .order_by(schema.messages.c.id)
        ).all()
    fresh = [row for row in stored if str(row[0]) not in before_tool_ids]
    assert {str(row[1]) for row in fresh} == set(scripted), fresh
    for row in fresh:
        payload = json.loads(str(row[2]))
        assert json.loads(str(payload["arguments"])) == json.loads(scripted[str(row[1])]), payload
        remainder = {key: value for key, value in payload.items() if key != "arguments"}
        assert_no_sentinel_of_user(remainder, registry=world.sentinels, user="B")
        assert_no_identifier_of(remainder, content=b)

    # --- DoD-7 -------------------------------------------------------------------------
    assert not world.fakes.web_recorder.requests, (
        "the world asserts web_search was never called during seeding; the request count must start clean"
    )
    web_query = f"{PROBE_WEB} {b_memo_sentinel}"
    world.fakes.web_recorder.script(
        WebResult(title="probe title", url="https://example.invalid/probe", snippet="probe snippet")
    )
    world.fakes.chat_factory.script(
        tool_call_round(
            name=WEB_SEARCH_NAME,
            arguments=json.dumps({"query": web_query}),
            call_id="audit-004-web",
        ),
        text_round(f"{PROBE_REPLY} web"),
    )
    _compose(world.clients.a, a.session_with_setup_id, f"{PROBE_WRITE} web compose")

    requests = world.fakes.web_recorder.requests
    assert len(requests) == 1, [str(one.url) for one in requests]
    request = requests[0]
    assert request.url.params["q"] == web_query, str(request.url)
    rendered = _rendered_request(request)
    # "nothing else from the instance": no seeded row id of *either* user, and no
    # sentinel but the one the model-supplied query itself carries.
    assert_no_identifier_of(rendered, content=a)
    assert_no_identifier_of(rendered, content=b)
    assert_no_sentinel_of_user(rendered, registry=world.sentinels, user="A")
    assert_no_sentinel_of_user(rendered, registry=world.sentinels, user="B", allowed=(b_memo_sentinel,))


# --- DoD-9, DoD-10 ---------------------------------------------------------------------


def _foreign_write_attempts(world: AuditWorld) -> list[tuple[str, Any]]:
    """Every foreign-id write attempt DoD-9 names, as `(label, response)`, performed as A."""
    client = world.clients.a
    b = world.b
    return [
        (
            "zone message",
            client.post(
                f"/api/sessions/{b.session_with_setup_id}/zone/messages", json={"text": PROBE_WRITE}
            ),
        ),
        ("settle", client.post(f"/api/sessions/{b.session_with_setup_id}/settle", json=None)),
        ("reopen", client.post(f"/api/sessions/{b.session_with_setup_id}/reopen", json=None)),
        ("message edit", client.patch(f"/api/messages/{b.messages.partner_id}", json={"text": PROBE_WRITE})),
        (
            "memo edit",
            client.patch(
                f"/api/memos/{b.memos.of('session', 'searchable')}", json={"body": PROBE_WRITE}
            ),
        ),
        ("memo delete", client.delete(f"/api/memos/{b.memos.of('user', 'searchable')}")),
    ]


def _own_successful_writes(world: AuditWorld) -> dict[str, Any]:
    """Every write DoD-10 names, performed by A on A's own rows, with its own evidence.

    Returns the ids and texts the positive controls need: a memo created, edited and
    deleted on A's own session scope, a settle and a reopen of A's own zone, and an edit
    of A's own settled partner row.
    """
    client = world.clients.a
    a = world.a

    created = _ok(
        client.post(
            "/api/memos",
            json={
                "scope": "session",
                "scope_id": a.session_with_setup_id,
                "body": f"{PROBE_WRITE} created",
            },
        ),
        201,
    )
    memo_id = str(created["id"])
    _ok(client.patch(f"/api/memos/{memo_id}", json={"body": f"{PROBE_WRITE} edited"}), 200)

    # Two zone rows, so the settle produces a head plus a buried group and the reopen
    # has something to restore.
    _ok(
        client.post(
            f"/api/sessions/{a.session_with_setup_id}/zone/messages",
            json={"text": f"{PROBE_WRITE} zone"},
        ),
        201,
    )
    settled = _ok(client.post(f"/api/sessions/{a.session_with_setup_id}/settle", json=None), 200)
    reopened = _ok(client.post(f"/api/sessions/{a.session_with_setup_id}/reopen", json=None), 200)
    edited = _ok(
        client.patch(f"/api/messages/{a.messages.partner_id}", json={"text": f"{PROBE_EDIT} partner"}),
        200,
    )
    _ok(client.delete(f"/api/memos/{memo_id}"), 204)
    return {"memo_id": memo_id, "settled": settled, "reopened": reopened, "edited": edited}


def test_index_writes_never_touch_another_users_rows__S032_004_DoD9_DoD10(world: AuditWorld) -> None:
    """Covers DoD-9 and DoD-10 (US-085.AC-1).

    DoD-9 — every foreign-id write attempt by A (zone message, settle, reopen, message
    edit, memo edit, memo delete against B's ids) is refused with the enumeration's 404
    code and leaves B's rows in `memo_vec`, `session_vec` and their FTS tables
    **identical to before**.

    DoD-10 — A's own *successful* writes on the same paths (memo create / edit / delete,
    settle, reopen, message edit) change no `memo_vec`, `session_vec` or FTS row keyed
    to a B id. The positive control is that they really did move A's own derived rows,
    so "B unchanged" is a scoping fact rather than a no-op.

    Snapshots use `MATCH` and the `*_docsize` shadow tables, never a plain `SELECT` on
    an FTS table: an external-content table reads through to its base table, so a plain
    select would compare the wrong thing (decision 18).

    The service-level finding this step fixes is pinned in a test of its own, so its
    expected pre-fix failure cannot be read as a failure of either clause here.
    """
    before_b = _index_snapshot(world, "B")
    before_a = _index_snapshot(world, "A")
    _assert_snapshot_is_not_empty(before_b, user="B")
    _assert_snapshot_is_not_empty(before_a, user="A")

    # --- DoD-9 -------------------------------------------------------------------------
    for label, response in _foreign_write_attempts(world):
        assert_envelope(response, 404, FOREIGN_WRITE_CODES[label])
    after_foreign = _index_snapshot(world, "B")
    differences = _snapshot_differences(before_b, after_foreign)
    assert not differences, (
        "a refused foreign-id write changed B's derived-store rows:\n" + "\n".join(differences)
    )

    # --- DoD-10 ------------------------------------------------------------------------
    evidence = _own_successful_writes(world)
    after_own_b = _index_snapshot(world, "B")
    differences = _snapshot_differences(after_foreign, after_own_b)
    assert not differences, (
        "A's own successful writes changed a derived-store row keyed to a B id:\n" + "\n".join(differences)
    )

    after_own_a = _index_snapshot(world, "A")
    assert _snapshot_differences(before_a, after_own_a), (
        "positive control failed: A's own writes moved none of A's derived-store rows "
        f"(memo {evidence['memo_id']} created, edited and deleted; settle {evidence['settled']}; "
        f"reopen {evidence['reopened']}), so the B-side absences above would be vacuous"
    )


def test_refresh_session_vectors_keeps_a_foreign_sessions_vector__S032_004_DoD9(world: AuditWorld) -> None:
    """Covers DoD-9 (US-085.AC-1) — the one case this step is expected to **fix**.

    DoD-9's words: "every foreign-id write attempt by A ... leaves B's rows in
    `memo_vec`, `session_vec` and their FTS tables identical to before". The harvest
    found that the session-vector refresh deletes a session's `session_vec` row with no
    owner predicate (orchestrator decision 19), so a refresh run with **A's** user id and
    **B's** session id removes B's vector — contradicting the module's own docstring.

    No route reaches it (every caller passes owner-scoped ids), so the call here is made
    directly against the service, which is legitimate in a test and the only way to pin
    the clause. The assertion is the spec-correct behaviour and is therefore **red until
    the owner term is added**, and it must be green at verify. It is not weakened.

    Its own test function, and its own world, so that this expected pre-fix failure
    cannot be confused with a DoD-9 route failure or a DoD-10 failure.
    """
    a, b = world.a, world.b
    factory = world.fakes.embedding_factory
    b_session = int(b.session_with_setup_id)

    before = _index_snapshot(world, "B")
    assert before["session_vec"].get(str(b_session)), (
        "B's session_vec row is missing before the call: the pin would be vacuous"
    )

    with world.engine.begin() as connection:
        refresh_session_vectors(
            connection, int(a.identity.user_id), [b_session], client_factory=factory
        )

    after = _index_snapshot(world, "B")
    assert after["session_vec"] == before["session_vec"], (
        "refresh_session_vectors(conn, A's user id, [B's session id]) changed B's session_vec rows: "
        f"before={before['session_vec']!r} after={after['session_vec']!r}"
    )
    assert not _snapshot_differences(before, after), (
        "refresh_session_vectors(conn, A's user id, [B's session id]) changed B's derived-store rows:\n"
        + "\n".join(_snapshot_differences(before, after))
    )

    # The positive control: the same refresh for A's own session is accepted and really
    # does rewrite A's own row, so the absence above is a scoping fact, not a no-op.
    before_a = _index_snapshot(world, "A")
    assert before_a["session_vec"].get(str(int(a.session_with_setup_id))), (
        "A's own session_vec row is missing: the positive control would be vacuous"
    )
    with world.engine.begin() as connection:
        refresh_session_vectors(
            connection,
            int(a.identity.user_id),
            [int(a.session_with_setup_id)],
            client_factory=factory,
        )
    after_a = _index_snapshot(world, "A")
    assert after_a["session_vec"].get(str(int(a.session_with_setup_id))), (
        "A's own refresh removed A's own session_vec row"
    )


# --- coverage map ----------------------------------------------------------------------
#
# DoD-1  -> test_my_search_reaches_no_other_users_material__S032_004_DoD1
# DoD-2  -> test_search_services_scope_every_read_to_the_caller__S032_004_DoD2_DoD3
# DoD-3  -> test_search_services_scope_every_read_to_the_caller__S032_004_DoD2_DoD3
# DoD-4  -> test_tools_and_context_never_cross_the_owner_boundary__S032_004_DoD4_DoD5_DoD6_DoD7_DoD8
# DoD-5  -> same
# DoD-6  -> same
# DoD-7  -> same
# DoD-8  -> same
# DoD-9  -> test_index_writes_never_touch_another_users_rows__S032_004_DoD9_DoD10
#           and test_refresh_session_vectors_keeps_a_foreign_sessions_vector__S032_004_DoD9
# DoD-10 -> test_index_writes_never_touch_another_users_rows__S032_004_DoD9_DoD10
#
# No `[manual/live]` item in this step: every DoD item is covered by a test above.
