"""Export, import and bootstrap-from-export sweep — step 005 of feature 032, DoD-1..DoD-7.

Specification: ``docs/plans/032.privacy-isolation-audit/005.export-import-sweep.md``
(Definition of done items 1..6 are ``[test]``; item 7 is ``[manual/live]`` and is the
**verifier's** task, not a test — see below), with ``005.context.md`` for the gaps this
step closes and the payload mechanics, and ``context.md`` for the shared vocabulary, the
sentinel convention and the leak-fix policy. Every expected value here comes from those
documents; step 002's frozen support-module record in ``status.md`` supplies only *how to
call*.

Requirements covered: **US-083.AC-1** for DoD-1, DoD-2, DoD-3, DoD-4 and DoD-6;
**US-084.AC-1** for DoD-5 (the step file cites it there).

This is an **audit** module: it re-asserts in one place that a user's own export carries
nothing of another user, that an import always lands in the caller's ownership whatever
the payload claims, and that the admin whole-database import refuses a configured
instance without wiping or echoing anything. The built code is expected to satisfy all of
it, so a failure here is a **leak finding**, not a test defect.

Scope boundaries this module deliberately does not cross
-------------------------------------------------------
* Character/session export and character import with a **foreign** id (enumeration rows
  44, 52, 53) are ``owner`` rows swept by **step 003 DoD-1**, not here.
* The admin export and import **role gates** (rows 72, 73) are swept by **step 002
  DoD-2/DoD-3**. 031's own DoD-9/10 own the admin import's contract; DoD-5 here adds only
  "nothing echoed, nothing wiped".
* The whole-database export's **opacity rule is 030's** (``context.md`` "Out":
  ``docs/plans/030.export-granularities/context.md`` ~L121, 030/005 DoD-2..4, 030/008
  DoD-7) and is **cited, never re-tested**. DoD-5 uses that export only as an import
  *payload*; nothing is asserted about its contents. **DoD-7 is the verifier's**: it
  confirms those 030 items are ``done`` rather than re-testing them, so this module
  deliberately contains no DoD-7 test.

DoD-1's two narrow exclusions, each with its reason (orchestrator decision 17)
-----------------------------------------------------------------------------
1. **``translations`` is excluded from the positive control.** The user and database
   exports exclude the ``translations`` table outright, so the translation sentinel
   *cannot* be in A's own export and must not be looked for there — looking for it would
   fail DoD-1 for the wrong reason. It stays in the **absence** set.
2. **``model_server_id`` is an instance-wide server id, not a B id.** A's export carries
   the registry server id that every user's rows share, so a naive "no other-user id"
   sweep over every seeded id would flag it. It is passed through the support module's
   documented ``allowed=`` carve-out channel so the exclusion is visible rather than
   implicit.
Every other sentinel and every other id of the other user stays in the absence set.

DoD-2's payload shape, chosen on purpose (orchestrator decision 16)
-------------------------------------------------------------------
A ``user``-granularity import whose rows' ``user_id`` differs from the payload's own
``users`` row id answers **400 ``export_invalid`` / ``malformed_payload``** — a refusal,
not the ownership rewrite DoD-2 is about. To actually reach the rule "every imported row
is owned by the caller whatever the payload claims", this module uses a **``character``
granularity** payload (``GET /api/characters/{A's character}/export``, then every
``user_id`` set to B's user id and every row id remapped onto B's **live** row ids). The
easier path was not taken by accident: it is named here so a reader can see which
mutation reaches the rule. DoD-3 exercises the other admissible shape — a ``user``
envelope whose ids all agree with each other — by importing A's own export as B.

DoD-6 is a registration check, not a behavioural test
-----------------------------------------------------
Enumeration **row 5** is ``fast/003``'s bootstrap-from-export route. When this module was
written ``fast/003`` was unplanned and unbuilt, so DoD-6 was asserted as the **absence**
of the surface. ``fast/003`` (DoD-22, amendment 2026-10-07) has since built
``POST /api/bootstrap/import``, so DoD-6 now checks **positively** that the route is
registered, still reusing step 002's ``UNBUILT_SURFACES`` row-5 pattern so that any other,
unenumerated bootstrap-from-export-shaped path is still caught. The route's behaviour is
``fast/003``'s own contract and is tested there, not here.

Mechanics
---------
* The shared two-user world comes from step 002's support module. ``audit_world``
  installs all four model seams itself, atomically; **this module never sets one of those
  override keys** and makes no network request.
* **Four test functions, four world builds**, because the world is expensive
  (~120 requests plus two composes, and ``conftest.py``'s ``db_settings`` is
  function-scoped). Per-clause granularity lives in the failure messages, not in the
  number of builds. The split is forced by what each clause mutates: DoD-1/DoD-6 are
  read-only; DoD-2 and DoD-4 both import **into A** and both assert B unchanged, so they
  share a build; DoD-3 imports **into B**, so it needs its own; DoD-5 is the destructive
  call and gets its own build with nothing after it.
* **DoD-5 runs only against the fully seeded world** (orchestrator decision 21).
  ``POST /api/admin/database/import`` answers 409 ``database_not_empty`` while A and B
  hold content — the safe state DoD-5 asserts — but on an **empty** database the same call
  wipes and replaces it. So the 409 is asserted exactly (never "any 2xx tolerated"), the
  world's non-emptiness is asserted first, and every A and B row is read back afterwards.
* "Unchanged" means, per ``005.context.md``, that the user's own read responses —
  characters, setups, sessions, entries, zone, discussions, memos, memo-chain,
  configuration, settings — are **equal before and after**, with nothing excluded. The
  snapshot additionally carries the user's whole export ``payload`` (the envelope header
  is dropped because ``created_at`` moves per call), which makes "unchanged" a row-level
  comparison rather than a listing-level one.
"""

import re
from collections.abc import Iterator, Mapping
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.config import Settings
from tests.privacy_audit_support import (
    MEMO_REACHES,
    MEMO_SCOPES,
    UNBUILT_SURFACES,
    AuditWorld,
    SeededUserContent,
    assert_empty_detail,
    assert_envelope,
    assert_no_identifier_of,
    assert_no_sentinel_of_user,
    audit_world,
    rendered_text,
    route_operations,
)

# --- constants ------------------------------------------------------------------------

#: Fresh tokens this module plants into import payloads. None is a registry sentinel, so
#: none can be confused with seeded content; each is a single lowercase alphanumeric word
#: so a LIKE or an FTS5 MATCH would see exactly one term.
IMPORT_CHARACTER = "importcharname032005"
IMPORT_SETUP = "importsetuptext032005"
IMPORT_MEMO = "importmemobody032005"
IMPORT_MESSAGE = "importmessagetext032005"
SESSION_IMPORT_MESSAGE = "importsessionmessage032005"
SESSION_IMPORT_MEMO = "importsessionmemo032005"
ADMIN_IMPORT_PROBE = "importadminpayload032005"

#: The enumeration's expected refusals, taken from ``context.md``'s table and the step
#: file's DoD — never from the implementation.
DATABASE_NOT_EMPTY = "database_not_empty"
CHARACTER_NOT_FOUND = "character_not_found"
SESSION_NOT_FOUND = "session_not_found"

#: The one built bootstrap route (``context.md`` enumeration row 2). Used as DoD-6's
#: anti-vacuity control: row 5's pattern must really match something registered, or the
#: guard would pass because it matched nothing at all.
BOOTSTRAP_PATH = "/api/bootstrap/create"

#: Enumeration row 5, ``fast/003``'s bootstrap-from-export route (fast/003 DoD-22).
BOOTSTRAP_IMPORT_PATH = "/api/bootstrap/import"


# --- fixture --------------------------------------------------------------------------


@pytest.fixture
def world(db_settings: Settings, db_engine: Engine) -> Iterator[AuditWorld]:
    """The shared two-user audit world.

    ``real_logging=False`` is the default: only step 007 wants the real
    ``configure_logging``. The four model seams are installed by ``audit_world`` itself,
    atomically; this module never sets one of those override keys.
    """
    with audit_world(db_settings, db_engine) as built:
        yield built


# --- generic helpers ------------------------------------------------------------------


def _ok(response: httpx.Response, status: int) -> Any:
    assert response.status_code == status, f"{response.request.method} {response.request.url}: {response.text}"
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def _envelope(client: TestClient, path: str) -> dict[str, Any]:
    """One export envelope, as the route returns it."""
    body = _ok(client.get(path), 200)
    assert isinstance(body, dict), body
    assert isinstance(body.get("payload"), dict), body
    return body


def _scope_id(scope: str, content: SeededUserContent) -> str | None:
    """The ``scope_id`` a memo list read needs at each level; the user level takes none."""
    if scope == "user":
        return None
    if scope == "character":
        return content.character_id
    if scope == "setup":
        return content.setup_id
    return content.session_with_setup_id


def _snapshot(client: TestClient, content: SeededUserContent) -> dict[str, Any]:
    """Every read through which this user sees their own material, keyed by label.

    ``005.context.md``'s "unchanged" is equality of these responses before and after, with
    nothing excluded. The export ``payload`` is included (without the envelope header,
    whose ``created_at`` moves on every call) so the comparison reaches every exported row
    and not only what a listing happens to show.
    """
    snapshot: dict[str, Any] = {}
    snapshot["me"] = _ok(client.get("/api/me"), 200)
    snapshot["settings"] = _ok(client.get("/api/me/settings"), 200)
    snapshot["characters"] = _ok(client.get("/api/characters"), 200)
    snapshot["characters?archived"] = _ok(client.get("/api/characters?include_archived=true"), 200)
    snapshot["character"] = _ok(client.get(f"/api/characters/{content.character_id}"), 200)
    snapshot["character-configuration"] = _ok(
        client.get(f"/api/characters/{content.character_id}/configuration"), 200
    )
    snapshot["setups"] = _ok(
        client.get(f"/api/characters/{content.character_id}/setups?include_archived=true"), 200
    )
    snapshot["setup"] = _ok(client.get(f"/api/setups/{content.setup_id}"), 200)
    snapshot["character-sessions"] = _ok(
        client.get(f"/api/characters/{content.character_id}/sessions?include_archived=true"), 200
    )
    snapshot["sessions"] = _ok(client.get("/api/sessions?include_archived=true"), 200)
    for session_id in content.all_session_ids():
        snapshot[f"session:{session_id}"] = _ok(client.get(f"/api/sessions/{session_id}"), 200)
        entries = _ok(client.get(f"/api/sessions/{session_id}/entries"), 200)
        snapshot[f"entries:{session_id}"] = entries
        snapshot[f"zone:{session_id}"] = _ok(client.get(f"/api/sessions/{session_id}/zone"), 200)
        snapshot[f"memo-chain:{session_id}"] = _ok(client.get(f"/api/sessions/{session_id}/memo-chain"), 200)
        snapshot[f"configuration:{session_id}"] = _ok(
            client.get(f"/api/sessions/{session_id}/configuration"), 200
        )
        for entry in entries["entries"]:
            message_id = entry["id"]
            snapshot[f"discussion:{message_id}"] = _ok(
                client.get(f"/api/messages/{message_id}/discussion"), 200
            )
    for scope in MEMO_SCOPES:
        scope_id = _scope_id(scope, content)
        query = f"/api/memos?scope={scope}" if scope_id is None else f"/api/memos?scope={scope}&scope_id={scope_id}"
        snapshot[f"memos:{scope}"] = _ok(client.get(query), 200)
    snapshot["export-payload"] = _envelope(client, "/api/export")["payload"]
    return snapshot


def _snapshot_problems(label: str, before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Every read of ``label``'s own material that moved, named one per line."""
    problems: list[str] = []
    if set(before) != set(after):
        problems.append(
            f"{label}'s own set of reachable reads changed: "
            f"gained {sorted(set(after) - set(before))}, lost {sorted(set(before) - set(after))}"
        )
    for key in sorted(set(before) & set(after)):
        if after[key] != before[key]:
            problems.append(
                f"{label}'s own `{key}` read changed.\n  before: {before[key]!r}\n  after:  {after[key]!r}"
            )
    return problems


def _character_ids(client: TestClient) -> list[str]:
    body = _ok(client.get("/api/characters?include_archived=true"), 200)
    return [row["id"] for row in body["characters"]]


def _session_ids_of_character(client: TestClient, character_id: str) -> list[str]:
    body = _ok(client.get(f"/api/characters/{character_id}/sessions?include_archived=true"), 200)
    return [row["id"] for row in body["sessions"]]


# --- payload mutation (``005.context.md`` "Mechanics") --------------------------------


def _collision_map(source: SeededUserContent, target: SeededUserContent) -> dict[str, str]:
    """Map every seeded row id of ``source`` onto the **live** row id of ``target``'s twin.

    Built row by row rather than by zipping arbitrary ids, so the mapping is injective and
    every reference inside the payload stays resolvable after the rewrite: a payload whose
    internal references broke would be refused as ``malformed_payload`` and would never
    reach the ownership rule this step is about. 031's id remapping must **remap, never
    overwrite**, which is why these are the target user's *live* ids.
    """
    mapping = {
        source.character_id: target.character_id,
        source.setup_id: target.setup_id,
        source.session_with_setup_id: target.session_with_setup_id,
        source.session_without_setup_id: target.session_without_setup_id,
        source.archived_session_id: target.archived_session_id,
        source.messages.partner_id: target.messages.partner_id,
        source.messages.zone_id: target.messages.zone_id,
        source.messages.turn_head_id: target.messages.turn_head_id,
        source.messages.decision_id: target.messages.decision_id,
        source.messages.assistant_id: target.messages.assistant_id,
        source.messages.tool_id: target.messages.tool_id,
    }
    for source_buried, target_buried in zip(source.messages.buried_ids, target.messages.buried_ids, strict=False):
        mapping[source_buried] = target_buried
    for scope in MEMO_SCOPES:
        for reach in MEMO_REACHES:
            mapping[source.memos.of(scope, reach)] = target.memos.of(scope, reach)
    return mapping


def _claim_other_owner(payload: Mapping[str, Any], *, mapping: Mapping[str, str], user_id: str) -> None:
    """Rewrite a payload **in place** to claim ``user_id`` and to reuse the mapped row ids.

    Every ``user_id`` cell becomes the other user's id (the ownership claim the import must
    ignore), and every id cell the mapping knows becomes that other user's live row id (the
    collision 031's remapping must survive). Cells the mapping does not know — the
    instance-wide ``model_server_id`` among them — are left exactly as exported.
    """
    for rows in payload.values():
        for row in rows:
            for key, value in list(row.items()):
                if key == "user_id" and value is not None:
                    row[key] = user_id
                elif isinstance(value, str) and value in mapping:
                    row[key] = mapping[value]


def _collided_ids(payload: Mapping[str, Any], mapping: Mapping[str, str]) -> list[str]:
    """The target user's live ids the mutated payload actually reuses."""
    text = rendered_text(payload)
    return sorted({new for new in mapping.values() if new in text})


# --- DoD-1 and DoD-6 -------------------------------------------------------------------


def test_own_export_carries_nothing_of_the_other_user__S032_005_DoD1_DoD6(world: AuditWorld) -> None:
    """Covers DoD-1 and DoD-6 (both US-083.AC-1).

    DoD-1 — ``GET /api/export`` as A carries every A sentinel and every A id (the positive
    control, so the absence can never pass vacuously) and **no B sentinel and no B id**;
    symmetrically for B. Two narrow, reasoned exclusions, per orchestrator decision 17:
    the ``translations`` sentinel is dropped from the *positive control* because user and
    database exports exclude that table (it stays in the absence set), and the instance-wide
    ``model_server_id`` is passed through the documented ``allowed=`` carve-out because it
    is a registry id shared by every user, not an id of the other user.

    DoD-6 — the bootstrap-from-export surface (enumeration row 5, ``fast/003``) is built
    (fast/003 DoD-22): ``POST /api/bootstrap/import`` must be registered, and no other
    bootstrap-from-export-shaped path outside row 5's ``allowed_paths`` may have landed.
    """
    problems: list[str] = []

    for user, other in (("A", "B"), ("B", "A")):
        own = world.content_of(user)
        foreign = world.content_of(other)
        response = world.clients.of(user).get("/api/export")
        if response.status_code != 200:
            problems.append(f"DoD-1: {user}'s own `GET /api/export` answered {response.status_code}")
            continue
        payload = response.json()["payload"]

        # Positive control: everything of this user's own must be in their own export.
        # The translation sentinel is excluded with its reason (decision 17): user exports
        # exclude the `translations` table, so it cannot be there and must not be sought.
        translation_sentinel = world.sentinels.get(user=user, table="translations", field="text")
        text = rendered_text(payload)
        expected = [one for one in world.sentinels.of_user(user) if one != translation_sentinel]
        missing = [one for one in expected if one not in text]
        if missing:
            problems.append(f"DoD-1: {user}'s own export is missing {len(missing)} own sentinel(s): {missing}")
        if translation_sentinel in text:
            problems.append(
                f"DoD-1: {user}'s export carries the translation sentinel, which the export excludes — "
                "the exclusion above would then be hiding a real row"
            )
        missing_ids = [one for one in own.all_ids() if one not in text]
        if missing_ids:
            problems.append(f"DoD-1: {user}'s own export is missing {len(missing_ids)} own id(s): {missing_ids}")

        # The absence, with the whole of the other user's sentinel set (translations
        # included — it must not be there either) and the whole of their seeded id set.
        try:
            assert_no_sentinel_of_user(payload, registry=world.sentinels, user=other)
        except AssertionError as failure:
            problems.append(f"DoD-1: {user}'s export carries a {other} sentinel: {failure}")
        try:
            assert_no_identifier_of(
                payload,
                content=foreign,
                # decision 17: the registry server id is instance-wide administrative data
                # shared by every user's rows, not an id of `other`. It is carved out here,
                # through the support module's documented channel, rather than silently.
                allowed=(world.models.server_id,),
            )
        except AssertionError as failure:
            problems.append(f"DoD-1: {user}'s export carries a {other} id: {failure}")

    # DoD-6: row 5's surface is built (fast/003 DoD-22) — assert it positively.
    surfaces = [surface for surface in UNBUILT_SURFACES if surface.row == 5]
    assert len(surfaces) == 1, f"row 5 must be declared exactly once in UNBUILT_SURFACES: {UNBUILT_SURFACES}"
    surface = surfaces[0]
    operations = route_operations(world.application)
    registered = sorted({path for _method, path in operations})
    matching = [path for path in registered if re.search(surface.path_pattern, path, re.IGNORECASE)]
    assert BOOTSTRAP_PATH in matching, (
        f"DoD-6 anti-vacuity: row 5's pattern {surface.path_pattern!r} matches no built bootstrap route, "
        f"so the guard would pass against nothing. Registered paths: {registered}"
    )
    if ("POST", BOOTSTRAP_IMPORT_PATH) not in operations:
        problems.append(
            f"DoD-6: row 5's bootstrap-from-export route `POST {BOOTSTRAP_IMPORT_PATH}` is not registered "
            f"(fast/003). Registered paths: {registered}"
        )
    landed = [path for path in matching if path not in surface.allowed_paths]
    if landed:
        problems.append(
            f"DoD-6: an unenumerated bootstrap-from-export-shaped surface has landed: {landed}. "
            f"{surface.description}. 032's enumeration must be amended before that route ships."
        )

    report = "\n".join(problems)
    assert not problems, f"export isolation sweep found {len(problems)} problem(s):\n{report}"


# --- DoD-2 and DoD-4 -------------------------------------------------------------------


def test_imports_land_in_the_callers_ownership__S032_005_DoD2_DoD4(world: AuditWorld) -> None:
    """Covers DoD-2 and DoD-4 (both US-083.AC-1).

    DoD-2 — ``POST /api/import`` as A with a payload whose rows claim **B's user id** and
    reuse **B's existing row ids**, carrying fresh import sentinels, creates rows that
    appear in A's listings and in **no** B listing, and every B row reads back unchanged.
    The payload is a ``character``-granularity export of A's own character, which is the
    shape that reaches the ownership rewrite: a ``user``-granularity payload whose rows'
    ``user_id`` disagrees with its own ``users`` row id answers 400 ``export_invalid`` /
    ``malformed_payload`` instead (orchestrator decision 16). DoD-3 covers the other
    admissible shape.

    DoD-4 — ``POST /api/characters/{A's character}/import`` with a payload naming B's ids
    attaches the imported rows to **A's character only**; B's rows and listings are
    unchanged.

    Both clauses also pin 031's "remap, never overwrite": the payload collides with B's
    **live** row ids on purpose, so B's colliding rows must survive untouched and the new
    ids must be none of B's.
    """
    a = world.a
    b = world.b
    a_client = world.clients.of("A")
    b_client = world.clients.of("B")
    mapping = _collision_map(a, b)
    problems: list[str] = []

    before_b = _snapshot(b_client, b)
    assert before_b["characters"]["characters"], "anti-vacuity: B must hold content before the imports"

    # --- DoD-2: a `character` envelope of A's own, claiming B's ownership and B's ids.
    envelope = _envelope(a_client, f"/api/characters/{a.character_id}/export")
    payload = envelope["payload"]
    _claim_other_owner(payload, mapping=mapping, user_id=b.identity.user_id)
    collided = _collided_ids(payload, mapping)
    assert len(collided) >= 5, f"the payload must really collide with B's live ids, reused only {collided}"
    payload["characters"][0]["name"] = IMPORT_CHARACTER
    if payload.get("setups"):
        payload["setups"][0]["description"] = IMPORT_SETUP
    if payload.get("memos"):
        payload["memos"][0]["body"] = IMPORT_MEMO
    if payload.get("messages"):
        payload["messages"][0]["text"] = IMPORT_MESSAGE
    planted = [
        token
        for token, present in (
            (IMPORT_CHARACTER, True),
            (IMPORT_SETUP, bool(payload.get("setups"))),
            (IMPORT_MEMO, bool(payload.get("memos"))),
            (IMPORT_MESSAGE, bool(payload.get("messages"))),
        )
        if present
    ]

    characters_before = _character_ids(a_client)
    response = a_client.post("/api/import", json=envelope)
    if response.status_code != 200:
        problems.append(
            "DoD-2: the owned import of a `character` envelope claiming B's ownership was not accepted "
            f"({response.status_code}): {response.text}. The DoD requires rows to be created and rewritten "
            "to the caller, not refused."
        )
    else:
        new_character_ids = [one for one in _character_ids(a_client) if one not in characters_before]
        if not new_character_ids:
            problems.append("DoD-2: the import answered 200 but A's character listing gained no row")
        for new_id in new_character_ids:
            if new_id in b.all_ids() or new_id in a.all_ids():
                problems.append(f"DoD-2: the imported character reused a live row id ({new_id}) instead of a fresh one")
            if a_client.get(f"/api/characters/{new_id}").status_code != 200:
                problems.append(f"DoD-2: A cannot read the character A just imported ({new_id})")
            refusal = b_client.get(f"/api/characters/{new_id}")
            try:
                assert_empty_detail(assert_envelope(refusal, 404, CHARACTER_NOT_FOUND))
            except (AssertionError, KeyError) as failure:
                problems.append(
                    f"DoD-2: B reached the row A imported while claiming B's ownership ({new_id}): {failure}"
                )
        a_text = rendered_text(_envelope(a_client, "/api/export")["payload"])
        a_listing = rendered_text(_ok(a_client.get("/api/characters?include_archived=true"), 200))
        for token in planted:
            if token not in a_text:
                problems.append(f"DoD-2: the fresh import sentinel {token!r} is in none of A's own rows")
        if IMPORT_CHARACTER not in a_listing:
            problems.append("DoD-2: the imported character does not appear in A's own character listing")

    after_b = _snapshot(b_client, b)
    problems += [f"DoD-2: {line}" for line in _snapshot_problems("B", before_b, after_b)]
    b_text = rendered_text(after_b)
    for token in planted:
        if token in b_text:
            problems.append(f"DoD-2: the fresh import sentinel {token!r} reached one of B's own reads")
    for collided_id in collided:
        if collided_id not in b_text:
            problems.append(
                f"DoD-2: B's colliding row {collided_id} is no longer visible in B's own reads — "
                "031's id remapping must remap, never overwrite"
            )

    # --- DoD-4: a `session` envelope of A's own, naming B's ids, imported under A's character.
    session_envelope = _envelope(a_client, f"/api/sessions/{a.session_with_setup_id}/export")
    session_payload = session_envelope["payload"]
    _claim_other_owner(session_payload, mapping=mapping, user_id=b.identity.user_id)
    session_collided = _collided_ids(session_payload, mapping)
    assert session_collided, f"the session payload must name B's ids, named {session_collided}"
    if session_payload.get("messages"):
        session_payload["messages"][0]["text"] = SESSION_IMPORT_MESSAGE
    if session_payload.get("memos"):
        session_payload["memos"][0]["body"] = SESSION_IMPORT_MEMO
    session_planted = [
        token
        for token, present in (
            (SESSION_IMPORT_MESSAGE, bool(session_payload.get("messages"))),
            (SESSION_IMPORT_MEMO, bool(session_payload.get("memos"))),
        )
        if present
    ]

    a_sessions_before = _session_ids_of_character(a_client, a.character_id)
    b_sessions_before = _session_ids_of_character(b_client, b.character_id)
    session_response = a_client.post(f"/api/characters/{a.character_id}/import", json=session_envelope)
    if session_response.status_code != 200:
        problems.append(
            "DoD-4: the character-scoped session import naming B's ids was not accepted "
            f"({session_response.status_code}): {session_response.text}"
        )
    else:
        a_sessions_after = _session_ids_of_character(a_client, a.character_id)
        new_sessions = [one for one in a_sessions_after if one not in a_sessions_before]
        if not new_sessions:
            problems.append("DoD-4: the import answered 200 but A's character gained no session")
        for new_id in new_sessions:
            if new_id in b.all_ids() or new_id in a.all_ids():
                problems.append(f"DoD-4: the imported session reused a live row id ({new_id})")
            if a_client.get(f"/api/sessions/{new_id}").status_code != 200:
                problems.append(f"DoD-4: A cannot read the session A just imported ({new_id})")
            refusal = b_client.get(f"/api/sessions/{new_id}")
            try:
                assert_empty_detail(assert_envelope(refusal, 404, SESSION_NOT_FOUND))
            except (AssertionError, KeyError) as failure:
                problems.append(f"DoD-4: B reached the session A imported ({new_id}): {failure}")
        if _session_ids_of_character(b_client, b.character_id) != b_sessions_before:
            problems.append("DoD-4: B's own character gained or lost a session")
        a_text = rendered_text(_envelope(a_client, "/api/export")["payload"])
        for token in session_planted:
            if token not in a_text:
                problems.append(f"DoD-4: the fresh import sentinel {token!r} is in none of A's own rows")

    final_b = _snapshot(b_client, b)
    problems += [f"DoD-4: {line}" for line in _snapshot_problems("B", before_b, final_b)]
    final_b_text = rendered_text(final_b)
    for token in session_planted:
        if token in final_b_text:
            problems.append(f"DoD-4: the fresh import sentinel {token!r} reached one of B's own reads")

    report = "\n".join(problems)
    assert not problems, f"import ownership sweep found {len(problems)} problem(s):\n{report}"


# --- DoD-3 -----------------------------------------------------------------------------


def test_importing_another_users_export_leaves_the_owner_untouched__S032_005_DoD3(world: AuditWorld) -> None:
    """Covers DoD-3 (US-083.AC-1).

    B importing A's own export (``GET /api/export`` as A, posted unmodified to
    ``POST /api/import`` as B) gets **copies owned by B**, and A's rows and A's listings are
    **unchanged**: nothing moved to A, nothing duplicated into A.

    This is the second admissible ``user``-granularity shape of orchestrator decision 16 —
    an envelope whose ``users`` row id and every ``user_id`` agree with each other, so the
    import reaches the ownership rewrite instead of answering ``malformed_payload``. The
    copies legitimately carry A's sentinel text, because B imported A's file; what must not
    happen is any change on A's side, which is what this asserts.
    """
    a = world.a
    a_client = world.clients.of("A")
    b_client = world.clients.of("B")
    problems: list[str] = []

    envelope = _envelope(a_client, "/api/export")
    before_a = _snapshot(a_client, a)
    a_characters_before = _character_ids(a_client)
    assert a_characters_before, "anti-vacuity: A must hold content before B's import"
    b_characters_before = _character_ids(b_client)

    response = b_client.post("/api/import", json=envelope)
    if response.status_code != 200:
        problems.append(
            f"DoD-3: B's import of A's own export was not accepted ({response.status_code}): {response.text}"
        )
    else:
        new_for_b = [one for one in _character_ids(b_client) if one not in b_characters_before]
        if not new_for_b:
            problems.append("DoD-3: the import answered 200 but B's character listing gained no copy")
        for new_id in new_for_b:
            if new_id in a.all_ids():
                problems.append(f"DoD-3: a copy reused one of A's live row ids ({new_id})")
            if b_client.get(f"/api/characters/{new_id}").status_code != 200:
                problems.append(f"DoD-3: B cannot read the copy B just imported ({new_id})")
            foreign = a_client.get(f"/api/characters/{new_id}")
            try:
                assert_empty_detail(assert_envelope(foreign, 404, CHARACTER_NOT_FOUND))
            except (AssertionError, KeyError) as failure:
                problems.append(f"DoD-3: A reached a row B imported ({new_id}): {failure}")

    after_a = _snapshot(a_client, a)
    problems += [f"DoD-3: {line}" for line in _snapshot_problems("A", before_a, after_a)]
    if _character_ids(a_client) != a_characters_before:
        problems.append("DoD-3: A's own character listing changed — a row moved to or was duplicated into A")

    report = "\n".join(problems)
    assert not problems, f"cross-user import sweep found {len(problems)} problem(s):\n{report}"


# --- DoD-5 -----------------------------------------------------------------------------


def test_admin_database_import_refuses_a_configured_instance__S032_005_DoD5(world: AuditWorld) -> None:
    """Covers DoD-5 (**US-084.AC-1**, as the step file cites it).

    ``POST /api/admin/database/import`` by ADM while A and B hold content gets **409
    ``database_not_empty``**; the response carries no sentinel from the payload or the
    database, and every A and B row reads back unchanged.

    Run only against the fully seeded world, and the 409 is asserted exactly rather than
    "any 2xx tolerated" (orchestrator decision 21): on an **empty** database the same call
    wipes and replaces it, and a wiped world would make every absence assertion in this
    feature vacuously green. The payload is the instance's own whole-database export with a
    fresh token planted in it — used purely as an import payload; nothing is asserted about
    that export's contents, because its opacity rule is 030's and is cited here, never
    re-tested.
    """
    a = world.a
    b = world.b
    a_client = world.clients.of("A")
    b_client = world.clients.of("B")
    adm = world.clients.of("ADM")
    problems: list[str] = []

    before_a = _snapshot(a_client, a)
    before_b = _snapshot(b_client, b)
    before_users = _ok(adm.get("/api/admin/users"), 200)
    assert before_a["characters"]["characters"], "anti-vacuity: A must hold content before the admin import"
    assert before_b["characters"]["characters"], "anti-vacuity: B must hold content before the admin import"

    payload_envelope = _envelope(adm, "/api/admin/database/export")
    characters = payload_envelope["payload"].get("characters") or []
    if characters:
        characters[0]["name"] = ADMIN_IMPORT_PROBE

    response = adm.post("/api/admin/database/import", json=payload_envelope)
    body = assert_envelope(response, 409, DATABASE_NOT_EMPTY)
    assert_empty_detail(body)

    # Nothing echoed: neither the payload's planted token nor any sentinel or id of either
    # roleplayer may appear in the refusal.
    if ADMIN_IMPORT_PROBE in response.text:
        problems.append("DoD-5: the refusal echoed the token planted in the payload")
    for user in ("A", "B"):
        try:
            assert_no_sentinel_of_user(response, registry=world.sentinels, user=user)
        except AssertionError as failure:
            problems.append(f"DoD-5: the refusal carries a {user} sentinel: {failure}")
        try:
            assert_no_identifier_of(response, content=world.content_of(user))
        except AssertionError as failure:
            problems.append(f"DoD-5: the refusal carries a {user} id: {failure}")

    # Nothing wiped.
    problems += [f"DoD-5: {line}" for line in _snapshot_problems("A", before_a, _snapshot(a_client, a))]
    problems += [f"DoD-5: {line}" for line in _snapshot_problems("B", before_b, _snapshot(b_client, b))]
    if _ok(adm.get("/api/admin/users"), 200) != before_users:
        problems.append("DoD-5: the admin account listing changed across the refused whole-database import")

    report = "\n".join(problems)
    assert not problems, f"admin database import sweep found {len(problems)} problem(s):\n{report}"


# DoD-7 is `[manual/live]` and is the **verifier's** task: it confirms that 030's
# whole-database-export opacity items are `done`
# (`docs/plans/030.export-granularities/context.md` ~L121, 030/005 DoD-2..4, 030/008
# DoD-7) rather than re-testing them here. `context.md`'s Out boundary puts that rule in
# 030, cited and never re-implemented or re-tested in 032, so this module deliberately
# contains no test for it.
