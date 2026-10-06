"""Feature 032 step 006 — admin surfaces, reverse lookup and the admin frontend.

Step file: ``docs/plans/032.privacy-isolation-audit/006.admin-surfaces-and-reverse-lookup.md``.
This module covers **DoD-1..DoD-7** (the backend half). DoD-8 and DoD-9 (the ``admin``
frontend entry) live in ``frontend/tests/adminPrivacyAudit.test.ts``; DoD-10 is
``[manual/live]`` and has no test here.

Every item of this step cites **US-084.AC-1**; each test's docstring repeats the citation.

Audit step (``context.md`` "The audit-step convention"): these clauses assert properties the
built code is expected to satisfy already, so a failure is a **leak finding** routed to the
step's fix-allowance, not a test defect. Expected values come from the step file, from
``006.context.md`` and from ``context.md``'s enumeration table — never from application source.

Four world builds, one per test function (``conftest.py``'s ``db_settings`` is function-scoped
and the world is ~120 requests plus two composes), following steps 003..005. The destructive
whole-database-import clause is isolated in the **last** build with nothing after it, so a call
that wiped the instance could not make a later absence assertion vacuously green.

Nothing here installs a model seam: ``audit_world`` installs all four
``FAKE_SEAM_OVERRIDE_KEYS`` atomically and the frozen record forbids a later step touching
them. That is what keeps ``POST …/test``, ``GET …/available-models`` and the embedding
designation off the network.
"""

import re
from collections.abc import Iterable, Iterator, Mapping
from typing import Any, Final, get_args

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Engine

from app.config import Settings
from tests.privacy_audit_support import (
    ENUMERATED_ROUTES,
    EXISTING_TABLE_NAME,
    UNBUILT_SURFACES,
    AuditUser,
    AuditWorld,
    EnumeratedRoute,
    api_routes,
    assert_empty_detail,
    assert_envelope,
    assert_no_sentinel_of_user,
    audit_world,
    normalize_path,
    registered_paths_by_operation,
    rendered_text,
    route_operations,
)

# --- The two identities whose sentinels must never appear in an administrative response ----

CONTENT_USERS: Final[tuple[AuditUser, ...]] = ("A", "B")

ADMIN_PATH_PREFIX: Final[str] = "/api/admin/"

# `006.context.md` "Allowed API prefixes" is the frontend's list; this is the backend's
# analogue: the one admin route deliberately left out of DoD-1 and DoD-2.
DATABASE_EXPORT_PATH: Final[str] = "/api/admin/database/export"
DATABASE_IMPORT_OPERATION: Final[tuple[str, str]] = ("POST", "/api/admin/database/import")

# Excluded from DoD-1 and DoD-2 **by name, with the reason inline** (orchestrator decision 20):
# the whole-database export returns every user's content *by design*, so an "every admin GET"
# loop would find B's sentinels in it and report a leak that is not one. Its opacity rule
# belongs to feature 030 and is cited, never re-tested here (`context.md` "Out"); its role gate
# is asserted by step 002 (enumeration row 72 — "role gate only — opacity is 030's").
DOD1_EXCLUDED_ADMIN_GETS: Final[Mapping[str, str]] = {
    DATABASE_EXPORT_PATH: (
        "the whole-database export carries every user's content by design; opacity is 030's "
        "(context.md Out) and the role gate is step 002's (enumeration row 72)"
    ),
}

# Statuses that mean the request never reached the handler. A mutation answering one of these
# would make DoD-3's absence assertion vacuous, so each exercised route is asserted *not* to
# answer one. DoD-3 itself says nothing about which success status a mutation returns, so no
# status is pinned beyond that — the clause is "the response carries no sentinel of any user".
GATE_STATUSES: Final[frozenset[int]] = frozenset({401, 403, 404, 405, 422})

# `006.context.md` "Snapshot rules": the only fields dropped before the DoD-2 equality.
# **Every numeric field stays in the comparison** — a number that moves with content volume is
# exactly the finding — and `last_login_at` stays too, because the snapshot is taken after
# every login and content is seeded with already-authenticated clients.
VOLATILE_FIELD_NAMES: Final[frozenset[str]] = frozenset({"id", "created_at", "updated_at"})
VOLATILE_FIELD_PREFIXES: Final[tuple[str, ...]] = ("last_test_",)

# `006.context.md` "Forbidden-name list", lower-cased for the case-insensitive comparison.
# A response-model field name is a single identifier, so whole-identifier matching here is
# exact (case-insensitive) equality; the phrase family (`sessions use`, `sessions using`,
# `in use by`) cannot occur in a field name and is asserted on the frontend instead (DoD-9).
FORBIDDEN_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "session_count",
        "sessions_count",
        "sessioncount",
        "character_count",
        "charactercount",
        "memo_count",
        "memocount",
        "message_count",
        "messagecount",
        "user_count",
        "usercount",
        "row_count",
        "rowcount",
        "vector_count",
        "vectorcount",
        "usage_count",
        "usagecount",
        "in_use",
        "inuse",
        "used_by",
        "usedby",
        "dependent_sessions",
        "dependentsessions",
    }
)

# Administrative field names `006.context.md` "Built admin facts" states the admin responses
# carry. Used only as DoD-5's anti-vacuity control: if the collection found none of them it
# found nothing, and "no forbidden name" would be a pass against an empty set.
EXPECTED_ADMIN_FIELD_NAMES: Final[tuple[str, ...]] = (
    "username",
    "role",
    "is_enabled",
    "last_login_at",
    "enabled_model_names",
    "embedding_model_name",
    "embedding_dim",
)

# Registry counts `006.context.md` exempts by name, plus the near-misses Report 3 flagged.
EXEMPT_FIELD_NAMES: Final[tuple[str, ...]] = ("embedding_dim", "enabled_model_names", "usage", "independent")

# fast/002's enumeration row (`context.md` row 74), carried by step 002's `UNBUILT_SURFACES`.
REBUILD_SURFACE_ROW: Final[int] = 74
REBUILD_PROBE_PATHS: Final[tuple[str, ...]] = (
    "/api/admin/database/rebuild",
    "/api/admin/database/tables/{}/rebuild",
)


@pytest.fixture
def world(db_settings: Settings, db_engine: Engine) -> Iterator[AuditWorld]:
    """The shared two-user audit world, built once per test function.

    ``real_logging`` keeps its default ``False``: only step 007 needs the real
    ``configure_logging``.
    """
    with audit_world(db_settings, db_engine) as built:
        yield built


# --- helpers ------------------------------------------------------------------------------


def _admin_rows(method: str | None = None) -> tuple[EnumeratedRoute, ...]:
    """The ``admin``-class rows of ``context.md``'s enumeration, optionally one method only."""
    return tuple(
        row
        for row in ENUMERATED_ROUTES
        if row.route_class == "admin" and (method is None or row.method.upper() == method)
    )


def _concrete(registered: str, *, server_id: str, user_id: str) -> str:
    """Substitute real ids into a registered admin path (never ``UNKNOWN_ID``: we want 200s)."""
    return (
        registered.replace("{server_id}", server_id)
        .replace("{table_name}", EXISTING_TABLE_NAME)
        .replace("{user_id}", user_id)
    )


def _without_volatile(payload: Any) -> Any:
    """Drop only ``006.context.md``'s volatile fields, recursively. Numbers always survive."""
    if isinstance(payload, Mapping):
        return {
            key: _without_volatile(value)
            for key, value in payload.items()
            if key not in VOLATILE_FIELD_NAMES and not key.startswith(VOLATILE_FIELD_PREFIXES)
        }
    if isinstance(payload, list):
        return [_without_volatile(item) for item in payload]
    return payload


def _nested_models(annotation: object) -> list[type[BaseModel]]:
    """Every pydantic model reachable from a field annotation, including through containers."""
    found: list[type[BaseModel]] = []
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        found.append(annotation)
    for argument in get_args(annotation):
        found.extend(_nested_models(argument))
    return found


def _declared_field_names(model: type[BaseModel], seen: set[type[BaseModel]] | None = None) -> set[str]:
    """Every declared field name (and alias) of a response model and of its nested models."""
    seen = set() if seen is None else seen
    if model in seen:
        return set()
    seen.add(model)
    names: set[str] = set()
    for field_name, field in model.model_fields.items():
        names.add(field_name)
        if field.alias:
            names.add(field.alias)
        for nested in _nested_models(field.annotation):
            names |= _declared_field_names(nested, seen)
    return names


def _forbidden_names(names: Iterable[str]) -> tuple[str, ...]:
    """The subset of ``names`` matching the forbidden list as a whole identifier."""
    return tuple(sorted({name for name in names if name.lower() in FORBIDDEN_FIELD_NAMES}))


def _sentinel_problems(payload: object, *, world: AuditWorld, where: str) -> list[str]:
    """Collect, rather than raise, so one leaking surface cannot hide another."""
    problems: list[str] = []
    for user in CONTENT_USERS:
        try:
            assert_no_sentinel_of_user(payload, registry=world.sentinels, user=user)
        except AssertionError as failure:
            problems.append(f"{where}: carries a sentinel of {user} — {failure}")
    return problems


def _seed_more_content(client: TestClient, label: str) -> dict[str, str]:
    """Add a character, setup, session, two messages and a memo through an authenticated client.

    This is the DoD-2 / DoD-6 "after" half: the snapshot is taken **after every login**, and
    the extra content is written by clients that are already authenticated, so
    ``last_login_at`` cannot move between the two snapshots. The world builder seeds
    atomically, so "before content is seeded" is realised as "before this additional content
    is seeded"; the invariant asserted is the one DoD-2 names — **no admin field moves with
    content volume**.
    """
    created: dict[str, str] = {}

    character = client.post(
        "/api/characters",
        json={"name": f"audit extra character {label}", "sheet": f"audit extra sheet {label}"},
    )
    assert character.status_code == 201, character.text
    created["character_id"] = str(character.json()["id"])

    setup = client.post(
        f"/api/characters/{created['character_id']}/setups",
        json={"name": f"audit extra setup {label}", "description": f"audit extra description {label}"},
    )
    assert setup.status_code == 201, setup.text
    created["setup_id"] = str(setup.json()["id"])

    session = client.post(
        f"/api/characters/{created['character_id']}/sessions",
        json={"setup_id": created["setup_id"], "opening_message": f"audit extra opening {label}"},
    )
    assert session.status_code == 201, session.text
    created["session_id"] = str(session.json()["id"])

    partner = client.post(
        f"/api/sessions/{created['session_id']}/entries",
        json={"kind": "partner", "text": f"audit extra partner block {label}"},
    )
    assert partner.status_code == 201, partner.text

    zone = client.post(
        f"/api/sessions/{created['session_id']}/zone/messages",
        json={"text": f"audit extra zone line {label}"},
    )
    assert zone.status_code == 201, zone.text

    memo = client.post("/api/memos", json={"scope": "user", "body": f"audit extra memo {label}"})
    assert memo.status_code == 201, memo.text
    created["memo_id"] = str(memo.json()["id"])

    return created


def _admin_response_models(application: FastAPI) -> dict[tuple[str, str], type[BaseModel] | None]:
    """``(METHOD, normalized path) -> declared response model`` for every ``/api/admin/`` route."""
    declared: dict[tuple[str, str], type[BaseModel] | None] = {}
    for route in api_routes(application):
        path = normalize_path(route.path)
        if not path.startswith(ADMIN_PATH_PREFIX):
            continue
        model = getattr(route, "response_model", None)
        usable = model if isinstance(model, type) and issubclass(model, BaseModel) else None
        for method in sorted(route.methods or ()):
            if method.upper() == "HEAD":
                continue
            declared[(method.upper(), path)] = usable
    return declared


# --- DoD-1, DoD-2, DoD-5, DoD-6, DoD-7 ----------------------------------------------------


def test_every_admin_read_carries_only_administrative_data__S032_006_DoD1_DoD2_DoD5_DoD6_DoD7(
    world: AuditWorld,
) -> None:
    """Admin reads carry administrative data only, and nothing that moves with content volume.

    US-084.AC-1.

    DoD-1 — every admin GET as ADM, with A and B seeded, carries no sentinel of either user.
    DoD-2 — every admin GET response is identical before and after more content is seeded.
    DoD-5 — no admin route's declared response model has a forbidden field name (R5).
    DoD-6 — ``GET /api/health`` carries no sentinel and is identical across the same seeding.
    DoD-7 — fast/002's vector-rebuild surface still does not exist (``[blocked/unbuilt-dependency]``).

    All five clauses are read-only apart from DoD-2's additional seeding, so they share one
    world build; each problem message names its clause and its surface.
    """
    adm = world.clients.adm
    anon = world.clients.anon
    application = world.application
    registered = registered_paths_by_operation(application)

    # Anti-vacuity for every absence clause below: there really are sentinels to find, and the
    # matcher really finds one when it is present.
    assert world.sentinels.of_user("A"), "A registered no sentinel: every absence clause would be vacuous"
    assert world.sentinels.of_user("B"), "B registered no sentinel: every absence clause would be vacuous"
    planted = world.sentinels.of_user("B")[0]
    with pytest.raises(AssertionError):
        assert_no_sentinel_of_user({"probe": planted}, registry=world.sentinels, user="B")

    # ---- the admin GET sweep (DoD-1) ----
    admin_gets = _admin_rows("GET")
    swept = tuple(row for row in admin_gets if row.path not in DOD1_EXCLUDED_ADMIN_GETS)
    assert DATABASE_EXPORT_PATH in {row.path for row in admin_gets}, (
        "the named DoD-1/DoD-2 exclusion is stale: the enumeration no longer holds "
        f"GET {DATABASE_EXPORT_PATH}"
    )
    assert len(swept) == 4, (
        "the enumeration gained or lost an admin GET row. The sweep is derived from the table, "
        "so the new row is already covered; update this count deliberately. Swept: "
        f"{[(row.row, row.path) for row in swept]}"
    )

    problems: list[str] = []
    before: dict[str, Any] = {}
    for row in swept:
        url = _concrete(
            registered[(row.method, row.path)],
            server_id=world.models.server_id,
            user_id=world.a.identity.user_id,
        )
        response = adm.get(url)
        assert response.status_code == 200, f"row {row.row} GET {url} answered {response.status_code}: {response.text}"
        payload = response.json()
        before[row.path] = payload
        problems.extend(_sentinel_problems(payload, world=world, where=f"DoD-1 row {row.row} GET {row.path}"))

    # Positive control: these responses really do carry administrative data, so "no sentinel"
    # is not a pass against empty bodies.
    users_text = rendered_text(before["/api/admin/users"])
    for username in (world.adm.username, world.a.identity.username, world.b.identity.username):
        assert username in users_text, f"GET /api/admin/users does not name {username!r}"
    servers_text = rendered_text(before["/api/admin/llm-servers"])
    assert world.models.server_name in servers_text, "GET /api/admin/llm-servers does not name the seeded server"
    assert world.models.chat_model_name in servers_text, "GET /api/admin/llm-servers lists no enabled chat model"
    assert world.models.chat_model_name in rendered_text(
        before["/api/admin/llm-servers/{}/available-models"]
    ), "GET …/available-models offers no model name"
    assert EXISTING_TABLE_NAME in rendered_text(
        before["/api/admin/database/tables"]
    ), f"GET /api/admin/database/tables does not name {EXISTING_TABLE_NAME!r}"

    # ---- health, before (DoD-6) ----
    health_before = {label: client.get("/api/health") for label, client in (("anon", anon), ("ADM", adm))}
    for label, response in health_before.items():
        assert response.status_code == 200, f"GET /api/health as {label} answered {response.status_code}"
        problems.extend(_sentinel_problems(response.json(), world=world, where=f"DoD-6 GET /api/health as {label}"))

    # ---- seed more content through already-authenticated clients (DoD-2 / DoD-6) ----
    extra = {
        "A": _seed_more_content(world.clients.a, "a"),
        "B": _seed_more_content(world.clients.b, "b"),
    }
    for label, client in (("A", world.clients.a), ("B", world.clients.b)):
        listing = client.get("/api/characters")
        assert listing.status_code == 200, listing.text
        assert extra[label]["character_id"] in rendered_text(listing.json()), (
            f"{label}'s additional character did not land: DoD-2's comparison would be vacuous"
        )

    # ---- DoD-2: every admin GET is identical across that seeding ----
    for row in swept:
        url = _concrete(
            registered[(row.method, row.path)],
            server_id=world.models.server_id,
            user_id=world.a.identity.user_id,
        )
        response = adm.get(url)
        assert response.status_code == 200, f"row {row.row} GET {url} answered {response.status_code}: {response.text}"
        if _without_volatile(response.json()) != _without_volatile(before[row.path]):
            problems.append(
                f"DoD-2 row {row.row} GET {row.path}: the response moved when content was seeded — "
                f"before={_without_volatile(before[row.path])!r} after={_without_volatile(response.json())!r}"
            )

    # ---- DoD-6: health is identical across that seeding, with nothing excluded ----
    for label, client in (("anon", anon), ("ADM", adm)):
        after = client.get("/api/health")
        if after.json() != health_before[label].json():
            problems.append(
                f"DoD-6 GET /api/health as {label}: the response moved when content was seeded — "
                f"before={health_before[label].json()!r} after={after.json()!r}"
            )
        problems.extend(
            _sentinel_problems(after.json(), world=world, where=f"DoD-6 GET /api/health as {label}, after seeding")
        )

    # ---- DoD-5: declared response models carry no forbidden field name (R5) ----
    # The matcher first proves itself, so a broken matcher cannot pass by matching nothing.
    # Compared as a set: the clause is *which* names the matcher flags, never the order it
    # returns them in.
    assert set(_forbidden_names(["session_count", "inUse", "sessionCount", "dependentSessions"])) == {
        "dependentSessions",
        "inUse",
        "session_count",
        "sessionCount",
    }, "the forbidden-name matcher does not flag the names the list names"
    assert _forbidden_names(EXPECTED_ADMIN_FIELD_NAMES + EXEMPT_FIELD_NAMES) == (), (
        "the forbidden-name matcher flags a legitimate administrative or registry field name"
    )

    declared = _admin_response_models(application)
    assert declared, "no /api/admin/ route was walked: DoD-5 would pass against nothing"
    collected: set[str] = set()
    without_model: set[tuple[str, str]] = set()
    for operation, model in sorted(declared.items()):
        if model is None:
            without_model.add(operation)
            continue
        names = _declared_field_names(model)
        collected |= names
        offending = _forbidden_names(names)
        if offending:
            problems.append(
                f"DoD-5 {operation[0]} {operation[1]}: response model {model.__name__} declares "
                f"forbidden field name(s) {list(offending)} (R5)"
            )
    for expected in EXPECTED_ADMIN_FIELD_NAMES:
        assert expected in collected, (
            f"the response-model walk found no field named {expected!r}, which `006.context.md` "
            "records as built: DoD-5 would be checking an incomplete field set"
        )

    # `006.context.md`: "a route without a declared response model is covered by DoD-1..3
    # instead". Assert that is true of every such route, so one can never slip through both.
    covered_elsewhere = (
        {(row.method, row.path) for row in swept}
        | {(row.method, row.path) for row in _admin_rows() if row.method != "GET"}
        | {("GET", DATABASE_EXPORT_PATH)}
    )
    uncovered = sorted(without_model - covered_elsewhere)
    assert uncovered == [], (
        "these admin routes declare no response model and are covered by no other clause: "
        f"{uncovered}"
    )

    # ---- DoD-7: fast/002's rebuild surface still does not exist ----
    surface = next((item for item in UNBUILT_SURFACES if item.row == REBUILD_SURFACE_ROW), None)
    assert surface is not None, f"step 002's UNBUILT_SURFACES holds no row {REBUILD_SURFACE_ROW} entry"
    assert surface.allowed_paths == frozenset(), (
        "row 74 is the unbuilt fast/002 vector-rebuild surface, so no registered path is "
        f"legitimately allowed to match it; allowed_paths={sorted(surface.allowed_paths)}"
    )
    for probe in REBUILD_PROBE_PATHS:
        assert re.search(surface.path_pattern, probe, re.IGNORECASE), (
            f"row 74's path pattern {surface.path_pattern!r} does not match {probe!r}: the guard "
            "would pass by matching nothing"
        )
    operations = route_operations(application)
    assert operations, "the route walk found no operations: the DoD-7 guard would pass vacuously"
    landed = sorted({path for _, path in operations if re.search(surface.path_pattern, path, re.IGNORECASE)})
    assert landed == [], (
        "fast/002's vector-rebuild surface has landed. DoD-7 (the rebuild response and every "
        "progress payload carry no count derived from content volume) has no behavioural test "
        "here — it is recorded [blocked/unbuilt-dependency], owner fast/002 — and 032's "
        f"enumeration row {REBUILD_SURFACE_ROW} must be amended before the route ships: {landed}"
    )

    assert problems == [], "\n".join(problems)


# --- DoD-3 ---------------------------------------------------------------------------------


def test_every_admin_mutation_response_carries_no_user_content__S032_006_DoD3(world: AuditWorld) -> None:
    """Every admin mutation named by DoD-3 answers without a sentinel of either user.

    US-084.AC-1.

    DoD-3's parenthetical names fourteen mutations: user create/disable/enable/password/role;
    llm-server create/patch/test/delete; models set; embedding model set/unset; database
    create/sync. The fifteenth admin mutation, ``POST /api/admin/database/import``, is
    **excluded from this loop by name** (orchestrator decision 21): it is destructive — on an
    empty instance it wipes and replaces the database — so it is exercised in its own isolated
    build at the end of this module, and the exclusion is therefore not a hole.

    DoD-3 says nothing about which success status a mutation returns, so none is pinned; each
    response is asserted **not** to answer a gate/validation status, which proves the handler
    really ran, and every response is swept for both users' sentinels.
    """
    adm = world.clients.adm
    server_id = world.models.server_id
    calls: list[tuple[int, str, str, Any]] = []

    def run(row: int, method: str, normalized: str, url: str, body: Any = None) -> Any:
        response = adm.request(method, url, json=body)
        calls.append((row, method, normalized, response))
        return response

    # Users — a throwaway roleplayer is the target, never ADM itself.
    created = run(
        55,
        "POST",
        "/api/admin/users",
        "/api/admin/users",
        {"username": "auditmutationuser", "password": "auditmutationpassword", "role": "roleplayer"},
    )
    assert created.status_code == 201, created.text
    target_id = str(created.json()["id"])
    assert "auditmutationuser" in rendered_text(created.json()), (
        "the user-create response does not echo the username: DoD-3's sweep would be looking at "
        "an empty body"
    )

    run(56, "POST", "/api/admin/users/{}/disable", f"/api/admin/users/{target_id}/disable")
    run(57, "POST", "/api/admin/users/{}/enable", f"/api/admin/users/{target_id}/enable")
    run(
        58,
        "POST",
        "/api/admin/users/{}/password",
        f"/api/admin/users/{target_id}/password",
        {"password": "auditmutationpassword2"},
    )
    run(59, "POST", "/api/admin/users/{}/role", f"/api/admin/users/{target_id}/role", {"role": "admin"})

    # LLM servers — a throwaway registration takes create/patch/delete so the world's own
    # server survives for the registry mutations below.
    probe_server = run(
        61,
        "POST",
        "/api/admin/llm-servers",
        "/api/admin/llm-servers",
        {"name": "audit probe registration", "kind": "llamaswap", "base_url": "http://127.0.0.1:1/v1"},
    )
    assert probe_server.status_code == 201, probe_server.text
    probe_id = str(probe_server.json()["id"])
    assert "audit probe registration" in rendered_text(probe_server.json()), (
        "the llm-server create response does not echo the name: DoD-3's sweep would be looking "
        "at an empty body"
    )

    run(
        62,
        "PATCH",
        "/api/admin/llm-servers/{}",
        f"/api/admin/llm-servers/{probe_id}",
        {"name": "audit probe registration renamed"},
    )
    run(64, "POST", "/api/admin/llm-servers/{}/test", f"/api/admin/llm-servers/{server_id}/test")
    run(
        66,
        "POST",
        "/api/admin/llm-servers/{}/models",
        f"/api/admin/llm-servers/{server_id}/models",
        {"model_names": [world.models.chat_model_name, world.models.embedding_model_name]},
    )
    run(
        67,
        "POST",
        "/api/admin/llm-servers/{}/embedding-model",
        f"/api/admin/llm-servers/{server_id}/embedding-model",
        {"model_name": world.models.embedding_model_name},
    )
    run(
        68,
        "DELETE",
        "/api/admin/llm-servers/{}/embedding-model",
        f"/api/admin/llm-servers/{server_id}/embedding-model",
    )
    run(63, "DELETE", "/api/admin/llm-servers/{}", f"/api/admin/llm-servers/{probe_id}")

    # Database schema mutations — schema metadata only.
    run(
        70,
        "POST",
        "/api/admin/database/tables/{}/create",
        f"/api/admin/database/tables/{EXISTING_TABLE_NAME}/create",
    )
    run(
        71,
        "POST",
        "/api/admin/database/tables/{}/sync",
        f"/api/admin/database/tables/{EXISTING_TABLE_NAME}/sync",
    )

    # Coverage: the exercised set plus the named, separately-tested import must be exactly the
    # enumeration's admin mutations, so a new admin mutation route can never go unswept.
    exercised = {(method, path) for _, method, path, _ in calls}
    expected = {(row.method, row.path) for row in _admin_rows() if row.method != "GET"}
    assert exercised | {DATABASE_IMPORT_OPERATION} == expected, (
        "DoD-3's mutation sweep and the enumeration's admin mutations disagree — "
        f"missing={sorted(expected - exercised - {DATABASE_IMPORT_OPERATION})} "
        f"unexpected={sorted(exercised - expected)}"
    )
    assert len(exercised) == 14, f"DoD-3 names fourteen mutations; {len(exercised)} were exercised"

    problems: list[str] = []
    for row, method, path, response in calls:
        where = f"DoD-3 row {row} {method} {path}"
        if response.status_code in GATE_STATUSES:
            problems.append(f"{where}: answered {response.status_code} — the handler never ran: {response.text}")
            continue
        body: object = response.text if not response.content else response.json()
        problems.extend(_sentinel_problems(body, world=world, where=where))
    assert problems == [], "\n".join(problems)


# --- DoD-4 ---------------------------------------------------------------------------------


def test_removing_a_model_a_session_uses_is_never_refused__S032_006_DoD4(world: AuditWorld) -> None:
    """R5: the enabled-model set answers the same way whether or not a session uses the model.

    US-084.AC-1.

    DoD-4: removing from the enabled set a model that B's session uses **succeeds — never is
    refused** — and its response equals, field for field apart from the model name, the
    response for removing a model no session uses.

    The two scenarios are made structurally symmetric so that "equal apart from the model
    name" becomes **byte equality** and needs no normalisation at all: both calls leave the
    same remaining enabled set, and the only difference between them is *which* model was
    removed — the used one, or a twin no session has ever referenced. A response that differed
    would be a reverse lookup leaking through (``context.md`` R5: no ``model → dependent
    sessions`` endpoint, count, badge, tooltip, ``detail`` field or confirm text).
    """
    adm = world.clients.adm
    models_path = f"/api/admin/llm-servers/{world.models.server_id}/models"
    used = world.models.chat_model_name
    embedding = world.models.embedding_model_name
    twin = "audit-twin-model-no-session-uses"

    # Anti-vacuity: the used model really was in use by a session. The world composed for both
    # users through the captured model, which is the observable form of "B's session uses it".
    chat_models = {call.model for call in world.fakes.chat_factory.chat_calls}
    assert used in chat_models, (
        "no composed session ever called the chat model, so 'a model B's session uses' would "
        f"have no referent; models seen: {sorted(chat_models)}"
    )

    baseline = adm.post(models_path, json={"model_names": [embedding, used]})
    assert baseline.status_code == 200, baseline.text

    # 1. Remove the model B's session uses. It must succeed — never be refused.
    removed_used = adm.post(models_path, json={"model_names": [embedding]})
    assert removed_used.status_code == 200, (
        "removing a model a session uses was refused — that is the R5 reverse lookup leaking "
        f"as a refusal: {removed_used.status_code} {removed_used.text}"
    )
    assert "error" not in removed_used.json(), f"the response is an error envelope: {removed_used.text}"
    assert used not in rendered_text(removed_used.json()), (
        "the removed model is still reported as enabled: the removal did not take effect, so "
        "the comparison below would be vacuous"
    )
    assert embedding in rendered_text(removed_used.json()), "the response reports no remaining enabled model"

    # 2. Enable a twin no session has ever referenced, then remove it the same way.
    enabled_twin = adm.post(models_path, json={"model_names": [embedding, twin]})
    assert enabled_twin.status_code == 200, enabled_twin.text
    assert twin in rendered_text(enabled_twin.json()), "the twin model was not enabled"

    removed_twin = adm.post(models_path, json={"model_names": [embedding]})
    assert removed_twin.status_code == 200, removed_twin.text
    assert twin not in rendered_text(removed_twin.json()), "the twin model is still reported as enabled"

    # 3. The two removals are indistinguishable.
    assert removed_used.status_code == removed_twin.status_code, (
        "removing a used model and removing an unused model answer different statuses: "
        f"{removed_used.status_code} vs {removed_twin.status_code}"
    )
    assert removed_used.json() == removed_twin.json(), (
        "removing a model a session uses answers differently from removing a model no session "
        f"uses — that difference is a reverse lookup (R5): {removed_used.json()!r} vs "
        f"{removed_twin.json()!r}"
    )

    # 4. Neither response carries a sentinel of either user, nor any session id of B's.
    problems: list[str] = []
    for label, response in (("used", removed_used), ("unused", removed_twin)):
        problems.extend(_sentinel_problems(response.json(), world=world, where=f"DoD-4 {label}-model removal"))
        text = rendered_text(response.json())
        for session_id in world.b.all_session_ids():
            if session_id in text:
                problems.append(f"DoD-4 {label}-model removal: the response names B's session {session_id} (R5)")
    assert problems == [], "\n".join(problems)


# --- DoD-3, the destructive clause — isolated, with nothing after it -----------------------


def test_admin_database_import_refuses_without_echoing_content__S032_006_DoD3(world: AuditWorld) -> None:
    """``POST /api/admin/database/import`` refuses a populated instance and echoes nothing.

    US-084.AC-1.

    The fifteenth admin mutation, held out of DoD-3's loop above (orchestrator decision 21).
    It is **destructive**: on an empty instance the same call wipes and replaces the database,
    which would make every later absence assertion vacuously green. So it runs only against
    the fully seeded world, its own build, with nothing after it, and the safe state — 409
    ``database_not_empty`` — is asserted exactly rather than "any 2xx" being tolerated.

    Nothing is asserted about the whole-database export used as the payload: its opacity rule
    belongs to feature 030 and is cited, never re-tested here (``context.md`` "Out").
    """
    adm = world.clients.adm

    # Anti-vacuity: both roleplayers really do hold content before the call.
    for label, client in (("A", world.clients.a), ("B", world.clients.b)):
        listing = client.get("/api/characters")
        assert listing.status_code == 200, listing.text
        assert listing.json()["characters"], f"{label} holds no character: the refusal would not be about content"

    exported = adm.get("/api/admin/database/export")
    assert exported.status_code == 200, exported.text

    refused = adm.post("/api/admin/database/import", json=exported.json())
    body = assert_envelope(refused, 409, "database_not_empty")
    assert_empty_detail(body)

    problems = _sentinel_problems(body, world=world, where="DoD-3 POST /api/admin/database/import (refusal)")

    # Nothing was wiped: the accounts and both roleplayers' own content are still there.
    users = adm.get("/api/admin/users")
    assert users.status_code == 200, users.text
    users_text = rendered_text(users.json())
    for username in (world.adm.username, world.a.identity.username, world.b.identity.username):
        if username not in users_text:
            problems.append(f"the refused import removed the account {username!r}")
    for label, client in (("A", world.clients.a), ("B", world.clients.b)):
        listing = client.get("/api/characters")
        if listing.status_code != 200 or not listing.json()["characters"]:
            problems.append(f"the refused import removed {label}'s content: {listing.status_code} {listing.text}")
    assert problems == [], "\n".join(problems)
