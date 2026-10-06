"""Owner-scoped CRUD and stream sweep — step 003 of feature 032, DoD-1..DoD-11.

Specification: ``docs/plans/032.privacy-isolation-audit/003.owner-scoped-sweep.md``
(Definition of done items 1..11, every one ``[test]``), with the 74-row route
enumeration, the class table and the "refusal identity" definition in
``docs/plans/032.privacy-isolation-audit/context.md``. Every expected status, error
code and absence here comes from those two documents; the frozen support-module
record in ``status.md`` supplies only *how to call*.

Requirement covered by every item: **US-083.AC-1**.

This is an **audit** module: it re-asserts in one place that every ``owner`` row of
the enumeration refuses a foreign id with refusal identity, that an admin is not a
super-reader, and that no list, zone, entry, memo or self surface of one roleplayer
carries another's material. The built code is expected to satisfy all of it; a
failure here is a leak finding, not a test defect.

Four test functions, each building the audit world exactly once, because the world
is expensive (``conftest.py``'s ``db_settings`` is function-scoped). Per-clause
granularity lives in the failure messages — each names the enumeration row, the
method, the path and the acting identity — not in the number of world builds.
"""

import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.config import Settings
from app.models.memos import MemoScope
from tests.privacy_audit_support import (
    ENUMERATED_ROUTES,
    MEMO_REACHES,
    UNKNOWN_ID,
    AuditUser,
    AuditWorld,
    EnumeratedRoute,
    SeededUserContent,
    assert_empty_detail,
    assert_envelope,
    assert_no_identifier_of,
    assert_no_sentinel_of_user,
    assert_refusal_identity,
    audit_world,
    fill_path,
    memo_carrier_field,
    registered_paths_by_operation,
    rendered_text,
)

# --- constants ------------------------------------------------------------------------

# The enumeration's `owner` rows are table rows 19..53 inclusive (context.md). The count is
# asserted so the sweep can never silently iterate a shrunken set.
EXPECTED_OWNER_ROWS = 35

# Tokens A tries to write into B's rows. They are not registry sentinels (so they cannot be
# confused with seeded content) and are single lowercase alphanumeric words, like sentinels,
# so a full-text or LIKE search would see one term.
PROBE = "probewriteaudit032003"
PROBE_NAME = "probename032003"
PROBE_OPENING = "probeopening032003"
PROBE_RP_LANGUAGE = "probelanguage032003"
PROBE_PREFERRED_LANGUAGE = "probepreferred032003"

# context.md's enumeration: the 404 code each owner-scoped resource answers with. Used only
# to cross-check the code carried by the enumeration literal itself (which is the expected
# value the assertions use), so a drift between the literal and the table is visible.
_FOREIGN_CODE_BY_RESOURCE: Mapping[str, str] = {
    "characters": "character_not_found",
    "setups": "setup_not_found",
    "sessions": "session_not_found",
    # Row 47 (POST /api/messages/{}/translation) included: its 404 is the generic message
    # code, per the enumeration as resolved by orchestrator decision 6.
    "messages": "message_not_found",
    "memos": "memo_not_found",
}

# Owner-scoped write rows that take no request body at all (archive/restore x3,
# settle, reopen, translation, memo delete). Declared so `_write_body` can assert that
# every other owner write row really has a body that would be valid for A's own resource —
# a refusal must be the owner predicate, never a 422.
_BODYLESS_WRITES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/characters/{}/archive"),
        ("POST", "/api/characters/{}/restore"),
        ("POST", "/api/setups/{}/archive"),
        ("POST", "/api/setups/{}/restore"),
        ("POST", "/api/sessions/{}/archive"),
        ("POST", "/api/sessions/{}/restore"),
        ("POST", "/api/sessions/{}/settle"),
        ("POST", "/api/sessions/{}/reopen"),
        ("POST", "/api/messages/{}/translation"),
        ("DELETE", "/api/memos/{}"),
    }
)

_ALL_SCOPES: tuple[MemoScope, ...] = ("user", "character", "setup", "session")
_PARENTED_SCOPES: tuple[MemoScope, ...] = ("character", "setup", "session")

# The resource whose owner predicate guards each parented memo scope, so the expected 404
# code comes from the same enumeration mapping the route sweep uses.
_RESOURCE_BY_SCOPE: Mapping[str, str] = {
    "character": "characters",
    "setup": "setups",
    "session": "sessions",
}


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


# --- helpers --------------------------------------------------------------------------


def _resource_of(normalized_path: str) -> str:
    """The leading resource of an owner-scoped path, e.g. `/api/setups/{}` -> `setups`."""
    parts = normalized_path.split("/")
    assert len(parts) > 2 and parts[1] == "api", f"unexpected owner path shape: {normalized_path}"
    return parts[2]


def _foreign_id(content: SeededUserContent, resource: str) -> str:
    """The seeded id of `content`'s row for that resource — the foreign id A reaches for."""
    if resource == "characters":
        return content.character_id
    if resource == "setups":
        return content.setup_id
    if resource == "sessions":
        return content.session_with_setup_id
    if resource == "messages":
        # A settled partner record row: editable, a settled entry (so discussion-eligible)
        # and translation-eligible, so one id serves all three message rows.
        return content.messages.partner_id
    if resource == "memos":
        return content.memos.of("character", "searchable")
    raise AssertionError(f"no seeded id for resource {resource!r}")


def _with_id(registered_path: str, resource_id: str) -> str:
    substituted, count = re.subn(r"\{[^}]+\}", resource_id, registered_path, count=1)
    assert count == 1, f"{registered_path} carries no path parameter to substitute"
    assert "{" not in substituted, f"{registered_path} carries more than one path parameter"
    return substituted


def _write_body(
    route: EnumeratedRoute, *, text: str, name: str, envelope: Mapping[str, Any]
) -> Any:
    """A request body that would be **valid for A's own resource**, carrying an A sentinel.

    `003.context.md` "Mechanics": a refusal must be the owner predicate and not a 422, and
    the body carries an A-side sentinel so DoD-2 can assert B never gained it.
    """
    bodies: dict[tuple[str, str], Any] = {
        ("PATCH", "/api/characters/{}"): {"name": name, "sheet": text},
        ("POST", "/api/characters/{}/setups"): {"name": name, "description": text},
        ("PATCH", "/api/setups/{}"): {"name": name, "description": text},
        ("POST", "/api/characters/{}/sessions"): {"opening_message": text},
        ("POST", "/api/sessions/{}/entries"): {"kind": "partner", "text": text},
        ("POST", "/api/sessions/{}/zone/messages"): {"text": text},
        ("POST", "/api/sessions/{}/zone/compose"): {"text": text},
        ("PATCH", "/api/sessions/{}/configuration"): {"system_prompt": text},
        ("PATCH", "/api/characters/{}/configuration"): {"system_prompt": text},
        ("PATCH", "/api/messages/{}"): {"text": text},
        ("PATCH", "/api/memos/{}"): {"body": text},
        # The import route validates the envelope before resolving the character, so an
        # empty body would be refused 400 for the wrong reason. A real session export of
        # A's own session is a valid envelope that carries A's own sentinels.
        ("POST", "/api/characters/{}/import"): envelope,
    }
    key = route.key()
    if key in bodies:
        return bodies[key]
    if route.method in {"POST", "PUT", "PATCH", "DELETE"}:
        assert key in _BODYLESS_WRITES, f"owner write row {route.row} {key} has no declared request body"
    return None


def _request(client: TestClient, method: str, path: str, body: Any) -> Any:
    if body is None:
        return client.request(method, path)
    return client.request(method, path, json=body)


def _session_envelope_of_a(world: AuditWorld) -> Mapping[str, Any]:
    response = world.clients.a.get(f"/api/sessions/{world.a.session_with_setup_id}/export")
    assert response.status_code == 200, f"A's own session export failed: {response.status_code} {response.text}"
    envelope = response.json()
    assert isinstance(envelope, dict)
    assert envelope.get("granularity") == "session", f"unexpected export granularity: {envelope.get('granularity')}"
    return envelope


def _owner_rows() -> tuple[EnumeratedRoute, ...]:
    rows = tuple(route for route in ENUMERATED_ROUTES if route.route_class == "owner")
    assert len(rows) == EXPECTED_OWNER_ROWS, (
        f"the enumeration holds {len(rows)} `owner` rows, expected {EXPECTED_OWNER_ROWS} (context.md rows 19..53)"
    )
    return rows


def _sweep_owner_rows(
    world: AuditWorld, actor: AuditUser, *, text: str, name: str, envelope: Mapping[str, Any]
) -> list[str]:
    """Every `owner` row, called by `actor` with B's id, must answer with refusal identity.

    Returns a list of human-readable problems rather than failing on the first one, so one
    leak can never hide another.
    """
    client = world.clients.of(actor)
    registered = registered_paths_by_operation(world.application)
    problems: list[str] = []
    for route in _owner_rows():
        resource = _resource_of(route.path)
        expected_code = route.not_found_code
        if expected_code is None:
            problems.append(f"row {route.row} {route.method} {route.path}: the enumeration carries no 404 code")
            continue
        if expected_code != _FOREIGN_CODE_BY_RESOURCE[resource]:
            problems.append(
                f"row {route.row} {route.method} {route.path}: the enumeration's code {expected_code!r} "
                f"disagrees with the table's code for {resource!r} ({_FOREIGN_CODE_BY_RESOURCE[resource]!r})"
            )
            continue
        template = registered[route.key()]
        body = _write_body(route, text=text, name=name, envelope=envelope)
        foreign = _request(client, route.method, _with_id(template, _foreign_id(world.b, resource)), body)
        unknown = _request(client, route.method, fill_path(template), body)
        try:
            assert_refusal_identity(foreign, unknown, status=404, code=expected_code)
            assert_empty_detail(assert_envelope(foreign, 404, expected_code))
            assert_no_sentinel_of_user(foreign, registry=world.sentinels, user="B")
            assert_no_identifier_of(foreign, content=world.b)
        except AssertionError as failure:
            problems.append(
                f"row {route.row} {route.method} {route.path} as {actor} with B's {resource} id: "
                f"expected 404 {expected_code} identical to the unknown-id answer with an empty detail; "
                f"foreign -> {foreign.status_code} {foreign.text[:400]!r}; "
                f"unknown -> {unknown.status_code} {unknown.text[:400]!r} ({failure})"
            )
    return problems


def _b_read_snapshot(world: AuditWorld) -> dict[str, tuple[int, Any]]:
    """Every read through which B can see its own material, as (status, JSON body)."""
    client = world.clients.b
    b = world.b
    reads: tuple[tuple[str, str], ...] = (
        ("characters", "/api/characters"),
        ("characters+archived", "/api/characters?include_archived=true"),
        ("sessions", "/api/sessions"),
        ("sessions+archived", "/api/sessions?include_archived=true"),
        ("character", f"/api/characters/{b.character_id}"),
        ("character-configuration", f"/api/characters/{b.character_id}/configuration"),
        ("setups+archived", f"/api/characters/{b.character_id}/setups?include_archived=true"),
        ("character-sessions+archived", f"/api/characters/{b.character_id}/sessions?include_archived=true"),
        ("setup", f"/api/setups/{b.setup_id}"),
        ("session", f"/api/sessions/{b.session_with_setup_id}"),
        ("session-without-setup", f"/api/sessions/{b.session_without_setup_id}"),
        ("archived-session", f"/api/sessions/{b.archived_session_id}"),
        ("session-configuration", f"/api/sessions/{b.session_with_setup_id}/configuration"),
        ("entries", f"/api/sessions/{b.session_with_setup_id}/entries"),
        ("zone", f"/api/sessions/{b.session_with_setup_id}/zone"),
        ("memo-chain", f"/api/sessions/{b.session_with_setup_id}/memo-chain"),
        ("discussion", f"/api/messages/{b.messages.turn_head_id}/discussion"),
        ("memos:user", "/api/memos?scope=user"),
        ("memos:character", f"/api/memos?scope=character&scope_id={b.character_id}"),
        ("memos:setup", f"/api/memos?scope=setup&scope_id={b.setup_id}"),
        ("memos:session", f"/api/memos?scope=session&scope_id={b.session_with_setup_id}"),
        ("settings", "/api/me/settings"),
        ("me", "/api/me"),
    )
    snapshot: dict[str, tuple[int, Any]] = {}
    for label, path in reads:
        response = client.get(path)
        assert response.status_code == 200, (
            f"B's own {label} read must succeed (positive control): {response.status_code} {response.text[:300]}"
        )
        snapshot[label] = (response.status_code, response.json())
    return snapshot


def _b_memo_snapshot(world: AuditWorld) -> dict[str, Any]:
    """B's four memo lists plus B's memo-chain — the surfaces DoD-6 keeps armed."""
    client = world.clients.b
    b = world.b
    scope_ids: dict[MemoScope, str | None] = {
        "user": None,
        "character": b.character_id,
        "setup": b.setup_id,
        "session": b.session_with_setup_id,
    }
    snapshot: dict[str, Any] = {}
    for scope, scope_id in scope_ids.items():
        path = "/api/memos?scope=user" if scope_id is None else f"/api/memos?scope={scope}&scope_id={scope_id}"
        response = client.get(path)
        assert response.status_code == 200, f"B's own {scope}-scope memo list failed: {response.status_code}"
        snapshot[f"memos:{scope}"] = response.json()
    chain = client.get(f"/api/sessions/{b.session_with_setup_id}/memo-chain")
    assert chain.status_code == 200
    snapshot["memo-chain"] = chain.json()
    return snapshot


def _visible_messages(client: TestClient, session_ids: Sequence[str]) -> list[dict[str, Any]]:
    """Every message row this client can reach: entries, zone and each entry's discussion.

    Buried rows (tool rows among them) are reachable only through the discussion of their
    settled head, so the walk has to follow every entry.
    """
    rows: list[dict[str, Any]] = []
    for session_id in session_ids:
        entries = client.get(f"/api/sessions/{session_id}/entries")
        assert entries.status_code == 200, f"own entries read failed for {session_id}: {entries.status_code}"
        entry_rows = list(entries.json()["entries"])
        rows.extend(entry_rows)
        zone = client.get(f"/api/sessions/{session_id}/zone")
        assert zone.status_code == 200, f"own zone read failed for {session_id}: {zone.status_code}"
        rows.extend(zone.json()["messages"])
        for entry in entry_rows:
            discussion = client.get(f"/api/messages/{entry['id']}/discussion")
            assert discussion.status_code == 200, f"own discussion read failed for {entry['id']}"
            rows.extend(discussion.json()["messages"])
    return rows


# --- DoD-1, DoD-2, DoD-3 --------------------------------------------------------------


def test_every_owner_row_refuses_a_foreign_id_and_b_is_untouched__S032_003_DoD1_DoD2_DoD3(
    world: AuditWorld,
) -> None:
    """Covers DoD-1, DoD-2 and DoD-3 (US-083.AC-1).

    DoD-1 — every `owner` row of the enumeration, called by A with B's id for the path's
    resource, answers with refusal identity and the row's 404 code: the response equals A's
    response for the unknown id, body for body, with `detail == {}`.
    DoD-3 — the identical sweep performed by ADM: an admin is not a super-reader of user
    content.
    DoD-2 — after every write attempt of those sweeps, every read through which B sees its
    own material returns exactly what it returned before: same sentinels, same archive
    state, same zone/entries rows, same memos and order. "Unchanged" excludes nothing — no
    timestamp moves on a refused write — and A's probe token and A's sentinel reach none of
    B's reads.
    """
    envelope = _session_envelope_of_a(world)
    a_sentinel = world.sentinels.get(user="A", table="characters", field="name")
    text = f"{a_sentinel} {PROBE}"
    name = f"{PROBE_NAME} {a_sentinel}"

    before = _b_read_snapshot(world)

    problems = _sweep_owner_rows(world, "A", text=text, name=name, envelope=envelope)
    problems += _sweep_owner_rows(world, "ADM", text=text, name=name, envelope=envelope)

    after = _b_read_snapshot(world)
    for label in before:
        if after[label] != before[label]:
            problems.append(
                f"DoD-2: B's own {label} read changed after the refused writes.\n"
                f"  before: {before[label]!r}\n  after:  {after[label]!r}"
            )
    payloads = [payload for _status, payload in after.values()]
    if PROBE in rendered_text(payloads):
        problems.append(f"DoD-2: the write probe {PROBE!r} reached one of B's own reads")
    if PROBE_NAME in rendered_text(payloads):
        problems.append(f"DoD-2: the write probe {PROBE_NAME!r} reached one of B's own reads")
    try:
        assert_no_sentinel_of_user(payloads, registry=world.sentinels, user="A")
    except AssertionError as failure:
        problems.append(f"DoD-2: an A sentinel reached one of B's own reads: {failure}")

    report = "\n".join(problems)
    assert not problems, f"owner-scoped cross-user sweep found {len(problems)} problem(s):\n{report}"


# --- DoD-4, DoD-10, DoD-11 ------------------------------------------------------------


def test_as_own_surfaces_carry_no_b_material__S032_003_DoD4_DoD10_DoD11(world: AuditWorld) -> None:
    """Covers DoD-4, DoD-10 and DoD-11 (US-083.AC-1).

    DoD-4 — A's list routes (characters and sessions including the archived views, the
    per-character setups and sessions, the memo list for each of A's own scopes, A's
    entries, zone and memo-chain) contain no B sentinel and no B id, while containing A's
    own rows as the positive control.
    DoD-10 — `GET /api/me`, `GET /api/me/settings` and `GET /api/models` as A carry no B
    sentinel and no B id, and `PATCH /api/me/settings` by A leaves B's settings unchanged.
    DoD-11 — B's zone and entries containing tool rows are unreachable by A (the refusal
    direction is DoD-1 rows 34 and 36); here, additionally, A's own zone and entries never
    contain a B tool row — with B's own tool row proved visible through B's own surfaces so
    the absence cannot pass vacuously.
    """
    a, b = world.a, world.b
    client = world.clients.a
    a_name_sentinel = world.sentinels.get(user="A", table="characters", field="name")
    a_setup_sentinel = world.sentinels.get(user="A", table="setups", field="name")

    surfaces: tuple[tuple[str, str], ...] = (
        # DoD-4 list routes
        ("characters", "/api/characters"),
        ("characters+archived", "/api/characters?include_archived=true"),
        ("sessions", "/api/sessions"),
        ("sessions+archived", "/api/sessions?include_archived=true"),
        ("setups", f"/api/characters/{a.character_id}/setups"),
        ("setups+archived", f"/api/characters/{a.character_id}/setups?include_archived=true"),
        ("character-sessions", f"/api/characters/{a.character_id}/sessions"),
        ("character-sessions+archived", f"/api/characters/{a.character_id}/sessions?include_archived=true"),
        ("memos:user", "/api/memos?scope=user"),
        ("memos:character", f"/api/memos?scope=character&scope_id={a.character_id}"),
        ("memos:setup", f"/api/memos?scope=setup&scope_id={a.setup_id}"),
        ("memos:session", f"/api/memos?scope=session&scope_id={a.session_with_setup_id}"),
        ("entries", f"/api/sessions/{a.session_with_setup_id}/entries"),
        ("zone", f"/api/sessions/{a.session_with_setup_id}/zone"),
        ("memo-chain", f"/api/sessions/{a.session_with_setup_id}/memo-chain"),
        # DoD-10 self and registry reads
        ("me", "/api/me"),
        ("settings", "/api/me/settings"),
        ("models", "/api/models"),
    )
    problems: list[str] = []
    for label, path in surfaces:
        response = client.get(path)
        if response.status_code != 200:
            problems.append(f"A's own {label} read failed: {response.status_code} {response.text[:300]}")
            continue
        try:
            assert_no_sentinel_of_user(response, registry=world.sentinels, user="B")
            assert_no_identifier_of(response, content=b)
        except AssertionError as failure:
            problems.append(f"A's {label} ({path}) carries B material: {failure}")
    assert not problems, "A's own surfaces carry another user's material:\n" + "\n".join(problems)

    # --- DoD-4 positive controls: A really does reach its own rows through each surface.
    character_ids = {item["id"] for item in client.get("/api/characters").json()["characters"]}
    assert a.character_id in character_ids
    assert b.character_id not in character_ids
    assert a_name_sentinel in rendered_text(client.get("/api/characters").json())

    working_sessions = {item["id"] for item in client.get("/api/sessions").json()["sessions"]}
    all_sessions = {item["id"] for item in client.get("/api/sessions?include_archived=true").json()["sessions"]}
    assert a.session_with_setup_id in working_sessions
    assert a.archived_session_id not in working_sessions, "the working view must exclude the archived session"
    assert a.archived_session_id in all_sessions, "the archived view must include the archived session"
    assert all_sessions.isdisjoint(set(b.all_session_ids()))

    setups = client.get(f"/api/characters/{a.character_id}/setups").json()["setups"]
    setup_ids = {item["id"] for item in setups}
    assert a.setup_id in setup_ids
    assert b.setup_id not in setup_ids
    assert a_setup_sentinel in rendered_text(setups)

    per_character_sessions = client.get(f"/api/characters/{a.character_id}/sessions?include_archived=true").json()
    per_character_ids = {item["id"] for item in per_character_sessions["sessions"]}
    assert a.session_with_setup_id in per_character_ids
    assert per_character_ids.isdisjoint(set(b.all_session_ids()))

    scope_ids: dict[MemoScope, str | None] = {
        "user": None,
        "character": a.character_id,
        "setup": a.setup_id,
        "session": a.session_with_setup_id,
    }
    for scope, scope_id in scope_ids.items():
        path = "/api/memos?scope=user" if scope_id is None else f"/api/memos?scope={scope}&scope_id={scope_id}"
        listed = {item["id"] for item in client.get(path).json()["memos"]}
        for reach in MEMO_REACHES:
            assert a.memos.of(scope, reach) in listed, f"A's own {scope}/{reach} memo is missing from {path}"
            assert b.memos.of(scope, reach) not in listed, f"B's {scope}/{reach} memo reached {path}"

    chain = client.get(f"/api/sessions/{a.session_with_setup_id}/memo-chain").json()
    chain_ids = {memo["id"] for level in chain["levels"] for memo in level["memos"]}
    for scope in _ALL_SCOPES:
        assert a.memos.of(scope, "forced") in chain_ids, f"A's forced {scope}-scope memo is missing from its chain"
        assert b.memos.of(scope, "forced") not in chain_ids, f"B's forced {scope}-scope memo reached A's chain"

    # --- DoD-4 / DoD-11: every message row A can reach, across entries, zone and discussions.
    a_visible = _visible_messages(client, a.all_session_ids())
    b_visible = _visible_messages(world.clients.b, b.all_session_ids())
    a_visible_ids = {row["id"] for row in a_visible}
    b_visible_ids = {row["id"] for row in b_visible}

    # Positive controls first, so the absences below cannot be vacuous.
    assert a.messages.partner_id in a_visible_ids
    assert a.messages.tool_id in a_visible_ids, "A's own tool row must be reachable through A's own surfaces"
    assert any(row["role"] == "tool" for row in a_visible), "A's own surfaces must show at least one tool row"
    assert b.messages.tool_id in b_visible_ids, "B's own tool row must be reachable through B's own surfaces"
    assert any(row["role"] == "tool" for row in b_visible), "B's own surfaces must show at least one tool row"

    # DoD-11: no B row at all, and in particular no B tool row, in anything A can see.
    assert b.messages.tool_id not in a_visible_ids, "B's tool row reached A's zone/entries"
    assert a_visible_ids.isdisjoint(set(b.messages.all_ids()))
    assert a_visible_ids.isdisjoint(set(b.all_ids()))
    a_session_ids = set(a.all_session_ids())
    for row in a_visible:
        assert row["session_id"] in a_session_ids, f"A sees a row of session {row['session_id']}, which is not A's"
    assert_no_sentinel_of_user(a_visible, registry=world.sentinels, user="B")
    assert_no_identifier_of(a_visible, content=b)

    # --- DoD-10: A's own settings write cannot reach B's settings.
    b_settings_before = world.clients.b.get("/api/me/settings")
    assert b_settings_before.status_code == 200
    patched = client.patch(
        "/api/me/settings",
        json={"rp_language": PROBE_RP_LANGUAGE, "preferred_language": PROBE_PREFERRED_LANGUAGE},
    )
    assert patched.status_code == 200, f"A's own settings write failed: {patched.status_code} {patched.text[:300]}"
    assert patched.json() == {
        "rp_language": PROBE_RP_LANGUAGE,
        "preferred_language": PROBE_PREFERRED_LANGUAGE,
    }, "positive control: A's own settings write must take effect"
    b_settings_after = world.clients.b.get("/api/me/settings")
    assert b_settings_after.status_code == 200
    assert b_settings_after.json() == b_settings_before.json(), "A's settings write changed B's settings"
    assert PROBE_RP_LANGUAGE not in rendered_text(b_settings_after.json())
    assert PROBE_PREFERRED_LANGUAGE not in rendered_text(b_settings_after.json())


# --- DoD-5, DoD-6, DoD-7 --------------------------------------------------------------


def test_memo_scope_crossing_is_refused_and_changes_nothing__S032_003_DoD5_DoD6_DoD7(
    world: AuditWorld,
) -> None:
    """Covers DoD-5, DoD-6 and DoD-7 (US-083.AC-1).

    DoD-5 — `GET /api/memos` as A with each of B's scope ids. For the `character`, `setup`
    and `session` scopes the answer is a 404 identical to the unknown-id answer, and never a
    B memo. For the `user` scope the route drops `scope_id` and returns the caller's own
    user-scope memos (orchestrator decision 23), so the operative clause asserted there is
    DoD-5's last one — **never a B memo** — with the positive control kept.
    DoD-6 — `POST /api/memos` naming one of B's scope ids. The disjunction's first branch is
    what the route answers for a parented scope (404, decision 15); the `user` scope drops
    `scope_id` and so creates a row owned by A. Either way nothing appears in any of B's
    memo lists or B's memo-chain, so the clause stays armed if the behaviour ever changes.
    DoD-7 — `PUT /api/memos/order` with an order mixing A's and B's memo ids, and with B's
    ids only, gets 409 `memo_order_mismatch`; neither A's nor B's memo order changes.
    """
    a, b = world.a, world.b
    a_client, b_client = world.clients.a, world.clients.b
    a_sentinel = world.sentinels.get(user="A", table="memos", field=memo_carrier_field("session", "searchable"))
    text = f"{a_sentinel} {PROBE}"

    # --- DoD-5: the three parented scopes answer 404 with refusal identity.
    for scope in _PARENTED_SCOPES:
        foreign_id = _foreign_id(b, _RESOURCE_BY_SCOPE[scope])
        code = _FOREIGN_CODE_BY_RESOURCE[_RESOURCE_BY_SCOPE[scope]]
        foreign = a_client.get(f"/api/memos?scope={scope}&scope_id={foreign_id}")
        unknown = a_client.get(f"/api/memos?scope={scope}&scope_id={UNKNOWN_ID}")
        assert_refusal_identity(foreign, unknown, status=404, code=code)
        assert_empty_detail(assert_envelope(foreign, 404, code))
        assert_no_sentinel_of_user(foreign, registry=world.sentinels, user="B")
        assert_no_identifier_of(foreign, content=b)
        # Positive control: B reaches its own memos at that very scope id.
        own = b_client.get(f"/api/memos?scope={scope}&scope_id={foreign_id}")
        assert own.status_code == 200, f"B's own {scope}-scope memo list failed: {own.status_code}"
        assert {item["id"] for item in own.json()["memos"]} == {b.memos.of(scope, r) for r in MEMO_REACHES}

    # --- DoD-5, `user` scope (decision 23): scope_id is dropped; never a B memo.
    with_bs_user_id = a_client.get(f"/api/memos?scope=user&scope_id={b.identity.user_id}")
    own_user_memos = a_client.get("/api/memos?scope=user")
    assert with_bs_user_id.status_code == 200
    assert own_user_memos.status_code == 200
    assert with_bs_user_id.json() == own_user_memos.json(), "a supplied scope_id must be dropped at user scope"
    returned = {item["id"] for item in with_bs_user_id.json()["memos"]}
    assert returned == {a.memos.of("user", r) for r in MEMO_REACHES}, "positive control: A's own user memos"
    assert returned.isdisjoint({b.memos.of("user", r) for r in MEMO_REACHES}), "a B memo reached A at user scope"
    assert_no_sentinel_of_user(with_bs_user_id, registry=world.sentinels, user="B")
    assert_no_identifier_of(with_bs_user_id, content=b)

    # --- DoD-6: creating a memo against one of B's scope ids.
    memos_before = _b_memo_snapshot(world)
    for scope in _PARENTED_SCOPES:
        resource = _RESOURCE_BY_SCOPE[scope]
        code = _FOREIGN_CODE_BY_RESOURCE[resource]
        refused = a_client.post(
            "/api/memos", json={"scope": scope, "scope_id": _foreign_id(b, resource), "body": text}
        )
        unknown = a_client.post("/api/memos", json={"scope": scope, "scope_id": UNKNOWN_ID, "body": text})
        assert_refusal_identity(refused, unknown, status=404, code=code)
        assert_empty_detail(assert_envelope(refused, 404, code))
    # The user scope drops scope_id, so this one is created — and must be A's alone.
    at_user_scope = a_client.post(
        "/api/memos", json={"scope": "user", "scope_id": b.identity.user_id, "body": text}
    )
    assert at_user_scope.status_code == 201, (
        f"user-scope create failed: {at_user_scope.status_code} {at_user_scope.text[:300]}"
    )
    created_id = at_user_scope.json()["id"]
    assert at_user_scope.json()["scope_id"] is None, "B's user id must not be echoed as the new memo's scope_id"
    assert created_id in {item["id"] for item in a_client.get("/api/memos?scope=user").json()["memos"]}

    memos_after = _b_memo_snapshot(world)
    assert memos_after == memos_before, "B's memo lists or memo-chain changed after A's cross-scope memo writes"
    assert created_id not in rendered_text(memos_after), "A's new memo id appeared in one of B's memo surfaces"
    assert PROBE not in rendered_text(memos_after), "A's probe text appeared in one of B's memo surfaces"

    # --- DoD-7: an order naming B's memo ids is refused and reorders nothing.
    order_path = "/api/memos/order"
    a_level_path = f"/api/memos?scope=session&scope_id={a.session_with_setup_id}"
    b_level_path = f"/api/memos?scope=session&scope_id={b.session_with_setup_id}"
    a_order_before = a_client.get(a_level_path).json()
    b_order_before = b_client.get(b_level_path).json()
    assert [item["id"] for item in a_order_before["memos"]], "positive control: A's session level holds memos"

    mixed = [
        a.memos.of("session", "forced"),
        a.memos.of("session", "searchable"),
        b.memos.of("session", "disabled"),
    ]
    bs_only = [b.memos.of("session", reach) for reach in MEMO_REACHES]
    for order in (mixed, bs_only):
        refused = a_client.put(
            order_path, json={"scope": "session", "scope_id": a.session_with_setup_id, "memo_ids": order}
        )
        assert_envelope(refused, 409, "memo_order_mismatch")
        # No B sentinel: a memo *body* of B's in the refusal would be disclosure. The ids
        # are deliberately not asserted absent — A supplied them in the request itself, so
        # echoing them back discloses nothing A did not already hold (cf. decision 11).
        assert_no_sentinel_of_user(refused, registry=world.sentinels, user="B")

    assert a_client.get(a_level_path).json() == a_order_before, "A's own memo order changed after a refused reorder"
    assert b_client.get(b_level_path).json() == b_order_before, "B's memo order changed after A's refused reorder"

    # Positive control: A's own valid reorder of the same level does succeed.
    valid_order = list(reversed([item["id"] for item in a_order_before["memos"]]))
    accepted = a_client.put(
        order_path, json={"scope": "session", "scope_id": a.session_with_setup_id, "memo_ids": valid_order}
    )
    assert accepted.status_code == 200, f"A's own reorder failed: {accepted.status_code} {accepted.text[:300]}"
    assert [item["id"] for item in accepted.json()["memos"]] == valid_order
    assert b_client.get(b_level_path).json() == b_order_before, "A's accepted reorder changed B's memo order"


# --- DoD-8, DoD-9 ---------------------------------------------------------------------


def test_foreign_setup_and_foreign_compose_are_refused__S032_003_DoD8_DoD9(world: AuditWorld) -> None:
    """Covers DoD-8 and DoD-9 (US-083.AC-1).

    DoD-8 — `POST /api/characters/{A's character}/sessions` with B's `setup_id` gets 404
    `setup_not_found`; no session is created for A and no opening message is written. This is
    the second case of enumeration row 30.
    DoD-9 — `POST /api/sessions/{B's session}/zone/compose` by A gets a 404
    `session_not_found` **JSON** response before any stream frame, writes no row in B's
    session, and the chat fake receives no call at all.
    """
    a, b = world.a, world.b
    a_client, b_client = world.clients.a, world.clients.b
    a_sentinel = world.sentinels.get(user="A", table="characters", field="sheet")
    text = f"{a_sentinel} {PROBE}"

    # --- DoD-8
    sessions_before = a_client.get("/api/sessions?include_archived=true").json()
    a_visible_before = _visible_messages(a_client, a.all_session_ids())
    refused = a_client.post(
        f"/api/characters/{a.character_id}/sessions",
        json={"setup_id": b.setup_id, "opening_message": text},
    )
    assert_empty_detail(assert_envelope(refused, 404, "setup_not_found"))
    unknown = a_client.post(
        f"/api/characters/{a.character_id}/sessions",
        json={"setup_id": UNKNOWN_ID, "opening_message": text},
    )
    assert_refusal_identity(refused, unknown, status=404, code="setup_not_found")
    assert_no_sentinel_of_user(refused, registry=world.sentinels, user="B")
    assert_no_identifier_of(refused, content=b)

    sessions_after = a_client.get("/api/sessions?include_archived=true").json()
    assert sessions_after == sessions_before, "a session was created for A despite the refused setup"
    a_visible_after = _visible_messages(a_client, a.all_session_ids())
    assert a_visible_after == a_visible_before, "a message was written for A despite the refused setup"
    assert PROBE not in rendered_text(sessions_after)
    assert PROBE not in rendered_text(a_visible_after)
    assert PROBE not in rendered_text(_visible_messages(b_client, b.all_session_ids()))

    # Positive control: the same call with A's own setup does start a session with its
    # opening message, so the refusal above is the owner predicate and not a rejected body.
    accepted = a_client.post(
        f"/api/characters/{a.character_id}/sessions",
        json={"setup_id": a.setup_id, "opening_message": PROBE_OPENING},
    )
    assert accepted.status_code == 201, f"A's own session start failed: {accepted.status_code} {accepted.text[:300]}"
    assert accepted.json()["setup_id"] == a.setup_id
    assert accepted.json()["opening_message"] is not None

    # --- DoD-9
    b_visible_before = _visible_messages(b_client, b.all_session_ids())
    b_zone_before = b_client.get(f"/api/sessions/{b.session_with_setup_id}/zone").json()
    # Anti-vacuity: the world's own composes did reach the chat fake, so a zero count below
    # really means "no call", not "this fake never records anything".
    assert world.fakes.chat_factory.call_count > 0, "the audit world's own composes must have reached the chat fake"
    world.fakes.reset_records()
    # The refused compose must add no call of its own. A delta rather than an absolute zero,
    # so the clause asserts the behaviour ("no model call") and not how much `reset_records`
    # happens to clear.
    factory_calls_before = world.fakes.chat_factory.call_count
    chat_calls_before = len(world.fakes.chat_factory.chat_calls)

    composed = a_client.post(f"/api/sessions/{b.session_with_setup_id}/zone/compose", json={"text": text})
    assert composed.status_code == 404, (
        f"compose on B's session answered {composed.status_code}: {composed.text[:400]}"
    )
    content_type = composed.headers.get("content-type", "")
    assert "text/event-stream" not in content_type, f"the refusal was streamed, not JSON: {content_type}"
    assert "data:" not in composed.text, "a stream frame was emitted before the refusal"
    body = assert_envelope(composed, 404, "session_not_found")
    assert set(body) == {"error"}
    assert_empty_detail(body)
    unknown_compose = a_client.post(f"/api/sessions/{UNKNOWN_ID}/zone/compose", json={"text": text})
    assert_refusal_identity(composed, unknown_compose, status=404, code="session_not_found")

    assert world.fakes.chat_factory.call_count == factory_calls_before, (
        "the chat fake was constructed for a refused compose"
    )
    assert len(world.fakes.chat_factory.chat_calls) == chat_calls_before, (
        "the chat fake received a call for a refused compose"
    )

    b_visible_after = _visible_messages(b_client, b.all_session_ids())
    assert b_visible_after == b_visible_before, "the refused compose wrote a row in B's session"
    assert b_client.get(f"/api/sessions/{b.session_with_setup_id}/zone").json() == b_zone_before
    assert PROBE not in rendered_text(b_visible_after)
