"""Feature 032 step 002 — the audit world and the route-classification guard (DoD-1..DoD-6).

Spec: `docs/plans/032.privacy-isolation-audit/002.audit-world-and-route-guard.md`
(Definition of done — six `[test]` items, no `[manual/live]` item), `002.context.md`
(coverage list, sentinel fields, guard mechanics) and the feature `context.md` (the 74-row
enumeration table, the class table, the shared vocabulary, the test conventions).
Requirements: **US-083.AC-1** for DoD-1, DoD-2, DoD-4, DoD-5 and DoD-6; **US-084.AC-1**
for DoD-3 (`context.md` routes the role gate to the administrative story).

Every expected value — status, error code, `detail == {}`, which class a route carries,
which table carries which sentinel — comes from the plan. Step 002's frozen `## Skeleton`
record supplied only *how to call* the shared world, which lives in
`tests/privacy_audit_support.py` and is this step's other deliverable.

This is an **audit step** (`context.md` "The audit-step convention"): these cases assert
properties the built code is expected to satisfy already, so a pass is the audit passing,
not a vacuous test. A failure is a leak finding.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine, select
from sqlalchemy import text as sql_text

from app.config import Settings
from app.db import schema
from tests.privacy_audit_support import (
    ENUMERATED_OPERATIONS,
    ENUMERATED_ROUTES,
    EXCLUDED_ROWS,
    FAKE_SEAM_OVERRIDE_KEYS,
    MEMO_REACHES,
    MEMO_SCOPES,
    SENTINEL_CARRIERS,
    UNBUILT_SURFACES,
    AuditWorld,
    SentinelCarrier,
    assert_empty_detail,
    assert_envelope,
    audit_world,
    fill_path,
    memo_carrier_field,
    normalize_path,
    registered_paths_by_operation,
    rendered_text,
    route_operations,
)

#: `context.md`'s enumeration holds 74 rows; rows 5 and 74 are excluded by name with their
#: reason inline (orientation decision 1), leaving exactly 72 for the two-way comparison.
EXPECTED_ROW_COUNT = 72

#: The owner column of every coverage-list table that has one (`002.context.md`'s list,
#: resolved against the real schema: character and session configuration and user settings
#: are **columns**, not tables).
COVERAGE_TABLE_OWNERS: Mapping[str, str] = {
    "users": "id",
    "characters": "user_id",
    "setups": "user_id",
    "sessions": "user_id",
    "messages": "user_id",
    "translations": "user_id",
    "memos": "user_id",
}

#: The anti-vacuity gate for DoD-5. Which of B's own read routes retrieves each carrier's
#: sentinel. Surface names are the keys of `_read_surfaces` below.
READ_SURFACE_OF_CARRIER: Mapping[tuple[str, str], str] = {
    ("characters", "name"): "character",
    ("characters", "sheet"): "character",
    ("characters", "system_prompt"): "character_configuration",
    ("setups", "name"): "setup",
    ("setups", "description"): "setup",
    ("sessions", "system_prompt"): "session_configuration",
    ("users", "rp_language"): "settings",
    ("users", "preferred_language"): "settings",
    ("messages", "text[partner]"): "entries",
    ("messages", "text[turn]"): "entries",
    ("messages", "text[decision]"): "entries",
    ("messages", "text[zone]"): "zone",
    ("messages", "text[buried]"): "discussion",
    ("messages", "text[assistant]"): "discussion",
    # The tool row's `tool_args` carries the parsed arguments on the wire, and the tool row
    # is buried under the turn head, so the discussion read is its surface.
    ("messages", "tool_payload[arguments]"): "discussion",
    **{
        ("memos", memo_carrier_field(scope, reach)): f"memos_{scope}"
        for scope in MEMO_SCOPES
        for reach in MEMO_REACHES
    },
}

#: Carriers with **no** read surface among the routes DoD-5 names, each with its reason.
#: Recorded explicitly so nothing is silently dropped from the positive control.
CARRIERS_WITHOUT_READ_SURFACE: Mapping[tuple[str, str], str] = {
    ("messages", "tool_payload[content]"): (
        "a tool row's wire text is the summary; `tool_payload` never leaves the database"
    ),
    ("translations", "text"): "DoD-5's surface list does not include the translation route",
    ("memo_vec", "embedded_text"): "a binary vector is never substring-readable",
    ("session_vec", "embedded_text"): "a binary vector is never substring-readable",
}

#: Methods that take a request body, for DoD-2 / DoD-3's "an empty JSON body where a body
#: is taken". The guard refuses before any body is validated, so `{}` is enough.
BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


@pytest.fixture
def world(db_settings: Settings, db_engine: Engine) -> Iterator[AuditWorld]:
    """The shared two-user audit world over this test's own SQLite file."""
    with audit_world(db_settings, db_engine) as built:
        yield built


def _call(client: Any, method: str, url: str) -> httpx.Response:
    if method in BODY_METHODS:
        return client.request(method, url, json={})
    return client.request(method, url)


def _column_of(carrier: SentinelCarrier) -> str:
    """`text[partner]` -> `text`; `body[user/forced]` -> `body`."""
    return carrier.field.split("[", 1)[0]


def _owner_column(table_name: str) -> str:
    return COVERAGE_TABLE_OWNERS[table_name]


# --------------------------------------------------------------------------------------
# DoD-1 — the route-classification guard
# --------------------------------------------------------------------------------------


def test_app_routes_and_the_enumeration_agree_exactly__S032_002_DoD1(world: AuditWorld) -> None:
    """DoD-1 (US-083.AC-1): the set of (method, normalized path) over every FastAPI API
    route equals the enumeration literal's set exactly, in both directions."""
    assert len(ENUMERATED_ROUTES) == EXPECTED_ROW_COUNT
    assert len(ENUMERATED_OPERATIONS) == EXPECTED_ROW_COUNT, "the literal holds a duplicate key"
    assert set(EXCLUDED_ROWS) == {5, 74}
    for row, reason in EXCLUDED_ROWS.items():
        assert reason.strip(), f"row {row} is excluded without a recorded reason"

    registered = route_operations(world.application)
    unclassified = sorted(registered - ENUMERATED_OPERATIONS)
    without_route = sorted(
        (route.row, route.method, route.path)
        for route in ENUMERATED_ROUTES
        if route.key() not in registered
    )
    assert not unclassified and not without_route, (
        "the application and the enumeration table disagree.\n"
        f"routes the table does not classify ({len(unclassified)}): {unclassified}\n"
        f"table rows with no route ({len(without_route)}): {without_route}"
    )


def test_no_unbuilt_surface_has_landed__S032_002_DoD1(world: AuditWorld) -> None:
    """DoD-1 (US-083.AC-1): rows 5 and 74 name surfaces no built feature delivers, so no
    registered route may match a bootstrap-from-export or a vector-rebuild shape."""
    registered_paths = {path for _method, path in route_operations(world.application)}
    for surface in UNBUILT_SURFACES:
        pattern = re.compile(surface.path_pattern, re.IGNORECASE)
        matched = {path for path in registered_paths if pattern.search(path)}
        unexpected = sorted(matched - surface.allowed_paths)
        assert not unexpected, (
            f"row {surface.row} ({surface.description}) appears to have landed: {unexpected}. "
            "032's enumeration must be amended before the route ships."
        )


# --------------------------------------------------------------------------------------
# DoD-2 — every guarded route refuses anon
# --------------------------------------------------------------------------------------


def test_every_non_public_route_refuses_anon_with_401__S032_002_DoD2(world: AuditWorld) -> None:
    """DoD-2 (US-083.AC-1): every route not classed `public` answers anon with 401
    `not_authenticated`, with the unknown id substituted for every path parameter and an
    empty JSON body where a body is taken. Every `public` row is skipped."""
    registered = registered_paths_by_operation(world.application)
    anon = world.clients.anon
    checked = 0
    offences: list[str] = []
    for route in ENUMERATED_ROUTES:
        if route.route_class == "public":
            continue
        path = registered.get(route.key())
        if path is None:
            offences.append(f"{route.row} {route.method} {route.path} -> the application registers no such route")
            continue
        response = _call(anon, route.method, fill_path(path))
        checked += 1
        body = response.json() if response.content else {}
        code = body.get("error", {}).get("code") if isinstance(body, dict) else None
        detail = body.get("error", {}).get("detail") if isinstance(body, dict) else None
        if response.status_code != 401 or code != "not_authenticated" or detail != {}:
            offences.append(f"{route.row} {route.method} {route.path} -> {response.status_code} {code} {detail}")
    assert not offences, "routes that did not refuse anon with 401 not_authenticated:\n" + "\n".join(offences)
    assert checked == EXPECTED_ROW_COUNT - sum(
        1 for route in ENUMERATED_ROUTES if route.route_class == "public"
    )


# --------------------------------------------------------------------------------------
# DoD-3 — every admin route refuses a roleplayer
# --------------------------------------------------------------------------------------


def test_every_admin_route_refuses_a_roleplayer_with_403__S032_002_DoD3(world: AuditWorld) -> None:
    """DoD-3 (US-084.AC-1): every `admin` route answers A with 403 `insufficient_role`."""
    registered = registered_paths_by_operation(world.application)
    admin_rows = [route for route in ENUMERATED_ROUTES if route.route_class == "admin"]
    assert admin_rows, "the enumeration classifies no admin route"
    offences: list[str] = []
    for route in admin_rows:
        response = _call(world.clients.a, route.method, fill_path(registered[route.key()]))
        body = response.json() if response.content else {}
        code = body.get("error", {}).get("code") if isinstance(body, dict) else None
        detail = body.get("error", {}).get("detail") if isinstance(body, dict) else None
        if response.status_code != 403 or code != "insufficient_role" or detail != {}:
            offences.append(f"{route.row} {route.method} {route.path} -> {response.status_code} {code} {detail}")
    assert not offences, (
        "admin routes that did not refuse a roleplayer with 403 insufficient_role:\n" + "\n".join(offences)
    )


# --------------------------------------------------------------------------------------
# DoD-4 — the world is not vacuous
# --------------------------------------------------------------------------------------


def test_every_coverage_table_holds_a_row_for_each_user__S032_002_DoD4(world: AuditWorld) -> None:
    """DoD-4 (US-083.AC-1): every table in `002.context.md`'s coverage list holds at least
    one row owned by A and one owned by B, derived stores included."""
    a_id = int(world.a.identity.user_id)
    b_id = int(world.b.identity.user_id)
    missing: list[str] = []
    with world.engine.connect() as connection:
        for table_name, owner in COVERAGE_TABLE_OWNERS.items():
            table = schema.metadata.tables[table_name]
            for label, user_id in (("A", a_id), ("B", b_id)):
                found = connection.execute(
                    select(table.c[owner]).where(table.c[owner] == user_id).limit(1)
                ).first()
                if found is None:
                    missing.append(f"{table_name} has no row owned by {label}")

        # memo_vec / session_vec carry no user column: ownership is witnessed by a row
        # keyed on one of that user's ids.
        memo_vec_keys = {row[0] for row in connection.execute(sql_text("SELECT memo_id FROM memo_vec"))}
        session_vec_keys = {row[0] for row in connection.execute(sql_text("SELECT session_id FROM session_vec"))}
        for label, content in (("A", world.a), ("B", world.b)):
            owned_memos = {int(one) for one in content.memos.all_ids()}
            if not owned_memos & memo_vec_keys:
                missing.append(f"memo_vec holds no vector for a memo of {label}")
            if int(content.session_with_setup_id) not in session_vec_keys:
                missing.append(f"session_vec holds no vector for the seeded session of {label}")

            # The FTS tables are external-content: a plain SELECT reads through to the base
            # table, so the index itself is witnessed with MATCH.
            memo_sentinel = world.sentinels.get(
                user=content.identity.label,
                table="memos",
                field=memo_carrier_field("session", "searchable"),
            )
            memo_hits = {
                row[0]
                for row in connection.execute(
                    sql_text("SELECT rowid FROM memo_fts WHERE memo_fts MATCH :token"),
                    {"token": memo_sentinel},
                )
            }
            if int(content.memos.of("session", "searchable")) not in memo_hits:
                missing.append(f"memo_fts does not index the searchable session memo of {label}")

            partner_sentinel = world.sentinels.get(
                user=content.identity.label, table="messages", field="text[partner]"
            )
            message_hits = {
                row[0]
                for row in connection.execute(
                    sql_text("SELECT rowid FROM message_fts WHERE message_fts MATCH :token"),
                    {"token": partner_sentinel},
                )
            }
            if int(content.messages.partner_id) not in message_hits:
                missing.append(f"message_fts does not index the partner block of {label}")
    assert not missing, "the audit world is incomplete, so every later sweep could pass vacuously:\n" + "\n".join(
        missing
    )


def test_every_registered_sentinel_is_stored_somewhere__S032_002_DoD4(world: AuditWorld) -> None:
    """DoD-4 (US-083.AC-1): every registered sentinel is stored in the database — the one
    thing that stops all five later sweeps from passing vacuously."""
    registry = world.sentinels
    assert registry.of_user("ADM") == (), "ADM owns no content (002.context.md)"
    assert registry.carriers_of_user("A") == SENTINEL_CARRIERS
    assert registry.carriers_of_user("B") == SENTINEL_CARRIERS

    not_stored_keys = {(carrier.table, carrier.field) for carrier in SENTINEL_CARRIERS if not carrier.stored}
    assert not_stored_keys == {
        key for key in CARRIERS_WITHOUT_READ_SURFACE if key[0].endswith("_vec")
    }, "the binary carriers must be exactly the two vector stores"

    missing: list[str] = []
    with world.engine.connect() as connection:
        for user in ("A", "B"):
            user_id = int(world.content_of(user).identity.user_id)
            for carrier in SENTINEL_CARRIERS:
                sentinel = registry.get(user=user, table=carrier.table, field=carrier.field)
                if not carrier.stored:
                    continue
                table = schema.metadata.tables[carrier.table]
                owner = _owner_column(carrier.table)
                found = connection.execute(
                    select(table.c[owner])
                    .where(table.c[owner] == user_id)
                    .where(table.c[_column_of(carrier)].like(f"%{sentinel}%"))
                    .limit(1)
                ).first()
                if found is None:
                    missing.append(f"{user} {carrier.table}.{carrier.field} ({sentinel}) is stored nowhere")
    assert not missing, "registered sentinels that reached no row:\n" + "\n".join(missing)


def test_the_world_installs_all_four_model_seams__S032_002_DoD4(world: AuditWorld) -> None:
    """DoD-4 (US-083.AC-1): the world's integrity precondition — all four model seams are
    installed, so no sweep can reach the operator's configured server, and every scripted
    fake really was exercised while seeding."""
    overrides = world.application.dependency_overrides
    assert len(FAKE_SEAM_OVERRIDE_KEYS) == 4
    installed = [key for key in FAKE_SEAM_OVERRIDE_KEYS if key in overrides]
    assert len(installed) == 4, [getattr(key, "__name__", repr(key)) for key in FAKE_SEAM_OVERRIDE_KEYS]
    assert world.fakes.override_keys() == FAKE_SEAM_OVERRIDE_KEYS
    assert world.fakes.chat_factory.call_count >= 2, "compose ran for neither A nor B"
    assert world.fakes.translation_factory.call_count >= 2, "no translation ran for A and B"
    assert world.fakes.web_recorder.requests == [], "the world makes no web-search request"


# --------------------------------------------------------------------------------------
# DoD-5 — the positive control
# --------------------------------------------------------------------------------------


def _read_surfaces(world: AuditWorld) -> dict[str, httpx.Response]:
    """B's own read routes, exactly the ones DoD-5 names."""
    b = world.b
    client = world.clients.b
    surfaces: dict[str, httpx.Response] = {
        "character": client.get(f"/api/characters/{b.character_id}"),
        "character_configuration": client.get(f"/api/characters/{b.character_id}/configuration"),
        "setup": client.get(f"/api/setups/{b.setup_id}"),
        "session": client.get(f"/api/sessions/{b.session_with_setup_id}"),
        "session_configuration": client.get(f"/api/sessions/{b.session_with_setup_id}/configuration"),
        "settings": client.get("/api/me/settings"),
        "entries": client.get(f"/api/sessions/{b.session_with_setup_id}/entries"),
        "zone": client.get(f"/api/sessions/{b.session_with_setup_id}/zone"),
        "discussion": client.get(f"/api/messages/{b.messages.turn_head_id}/discussion"),
        "memo_chain": client.get(f"/api/sessions/{b.session_with_setup_id}/memo-chain"),
    }
    scope_ids = {
        "user": None,
        "character": b.character_id,
        "setup": b.setup_id,
        "session": b.session_with_setup_id,
    }
    for scope, scope_id in scope_ids.items():
        query = f"scope={scope}" if scope_id is None else f"scope={scope}&scope_id={scope_id}"
        surfaces[f"memos_{scope}"] = client.get(f"/api/memos?{query}")
    for name, response in surfaces.items():
        assert response.status_code == 200, f"{name}: {response.status_code} {response.text}"
    return surfaces


def test_b_reads_every_own_sentinel_back_through_own_routes__S032_002_DoD5(world: AuditWorld) -> None:
    """DoD-5 (US-083.AC-1): the positive control. B, through B's own read routes, retrieves
    every one of B's sentinels that has a read surface; the carriers that have none are
    named with their reason, so nothing is silently dropped."""
    carrier_keys = {(carrier.table, carrier.field) for carrier in SENTINEL_CARRIERS}
    assert set(READ_SURFACE_OF_CARRIER) | set(CARRIERS_WITHOUT_READ_SURFACE) == carrier_keys
    assert not set(READ_SURFACE_OF_CARRIER) & set(CARRIERS_WITHOUT_READ_SURFACE)

    surfaces = _read_surfaces(world)
    rendered = {name: rendered_text(response) for name, response in surfaces.items()}
    unreachable: list[str] = []
    for (table, carrier_field), surface in READ_SURFACE_OF_CARRIER.items():
        sentinel = world.sentinels.get(user="B", table=table, field=carrier_field)
        if sentinel not in rendered[surface]:
            unreachable.append(f"{table}.{carrier_field} ({sentinel}) absent from B's own {surface} read")
    assert not unreachable, (
        "B cannot read back B's own material, so every matching absence assertion in steps "
        "003..007 would pass vacuously:\n" + "\n".join(unreachable)
    )

    # The memo chain is the second named surface for memos: all twelve appear there too.
    chain = rendered["memo_chain"]
    for scope in MEMO_SCOPES:
        for reach in MEMO_REACHES:
            sentinel = world.sentinels.get(user="B", table="memos", field=memo_carrier_field(scope, reach))
            assert sentinel in chain, f"the memo chain omits B's {scope}/{reach} memo"


def test_my_search_returns_bs_own_material_for_bs_own_sentinels__S032_002_DoD5(world: AuditWorld) -> None:
    """DoD-5 (US-083.AC-1): my-search is one of the read routes the positive control names;
    B's own query for B's own sentinel returns B's own row."""
    client = world.clients.b
    character_sentinel = world.sentinels.get(user="B", table="characters", field="name")
    body = client.get(f"/api/search?q={character_sentinel}")
    assert body.status_code == 200, body.text
    payload = body.json()
    assert world.b.character_id in {str(one["id"]) for one in payload["characters"]}, payload["characters"]

    memo_sentinel = world.sentinels.get(
        user="B", table="memos", field=memo_carrier_field("session", "searchable")
    )
    memo_body = client.get(f"/api/search?q={memo_sentinel}")
    assert memo_body.status_code == 200, memo_body.text
    memo_payload = memo_body.json()
    expected_memo = world.b.memos.of("session", "searchable")
    assert expected_memo in {str(one["id"]) for one in memo_payload["memos"]}, memo_payload["memos"]


# --------------------------------------------------------------------------------------
# DoD-6 — sentinel hygiene
# --------------------------------------------------------------------------------------


def test_sentinels_are_unique_non_nested_and_absent_from_administrative_data__S032_002_DoD6(
    world: AuditWorld,
) -> None:
    """DoD-6 (US-083.AC-1): no two sentinels are equal, none is a substring of another, and
    none appears in any username, server name or model name."""
    sentinels = world.sentinels.all_sentinels()
    assert len(sentinels) == 2 * len(SENTINEL_CARRIERS)
    assert len(set(sentinels)) == len(sentinels), "two sentinels are equal"

    token = re.compile(r"^[a-z0-9]+$")
    for sentinel in sentinels:
        assert token.match(sentinel), f"{sentinel!r} is not a single lowercase alphanumeric token"

    nested = sorted(
        (one, other)
        for one in sentinels
        for other in sentinels
        if one != other and one in other
    )
    assert not nested, f"a sentinel is a substring of another: {nested}"

    administrative = (
        world.identity_of("A").username,
        world.identity_of("B").username,
        world.adm.username,
        world.models.server_name,
        world.models.chat_model_name,
        world.models.embedding_model_name,
    )
    carried = sorted(
        (value, sentinel) for value in administrative for sentinel in sentinels if sentinel in value
    )
    assert not carried, f"administrative data carries a sentinel: {carried}"

    # Not vacuous: the administrative strings really are the ones the instance holds.
    accounts = world.clients.adm.get("/api/admin/users")
    assert accounts.status_code == 200, accounts.text
    usernames = {one["username"] for one in accounts.json()["users"]}
    assert {world.identity_of("A").username, world.identity_of("B").username, world.adm.username} <= usernames
    servers = world.clients.adm.get("/api/admin/llm-servers")
    assert servers.status_code == 200, servers.text
    rendered = rendered_text(servers)
    assert world.models.server_name in rendered
    assert world.models.chat_model_name in rendered
    assert world.models.embedding_model_name in rendered


# --------------------------------------------------------------------------------------
# Guard-helper self-checks (DoD-1's mechanics; a guard that cannot see the tree is no guard)
# --------------------------------------------------------------------------------------


def test_the_route_walk_and_path_helpers_behave__S032_002_DoD1(world: AuditWorld) -> None:
    """DoD-1 (US-083.AC-1): the walk really reaches the application's API routes and the
    normalizer and substitution behave, so the two-way comparison above cannot pass against
    nothing."""
    operations = route_operations(world.application)
    assert ("GET", "/api/health") in operations
    assert ("GET", "/api/characters/{}") in operations
    assert all(method != "HEAD" for method, _path in operations)

    assert normalize_path("/api/characters/{character_id}/setups") == "/api/characters/{}/setups"
    assert normalize_path("/api/admin/database/tables/{table_name:str}/sync") == (
        "/api/admin/database/tables/{}/sync"
    )
    assert fill_path("/api/sessions/{session_id}/entries") == (
        "/api/sessions/7250000000000000002/entries"
    )
    assert fill_path("/api/admin/database/tables/{table_name}/sync") == (
        "/api/admin/database/tables/characters/sync"
    )

    # The unknown-id substitution is a real refusal, not a validation error: A asking for
    # an id that exists nowhere gets the enumeration's 404 code with an empty detail.
    unknown = world.clients.a.get(fill_path("/api/characters/{character_id}"))
    assert_empty_detail(assert_envelope(unknown, 404, "character_not_found"))
