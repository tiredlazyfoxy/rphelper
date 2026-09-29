"""Tests for the role ladder (``app.roles``) and the HTTP authentication seam (``app.dependencies``).

Every expected value comes from ``docs/plans/004.authentication-session/002.ladder-and-dependencies.md``
(Interface intent + Definition of done), ``002.context.md`` and the feature ``context.md``
(D3 the typed 401/403, D6 the cookie flags, D7 what resolution requires, D8 where the ladder
and the dependencies live). Bindings come from ``## Skeleton`` -> ``Step 002`` (and
``Step 001`` for seeding sessions) in ``status.md``.

Covers step 002 DoD-1, DoD-2, DoD-3 (the new-surface half), DoD-5 .. DoD-12. DoD-4 lives in
``test_errors.py``; the deleted ``003/001`` purity clause is in ``test_db_schema.py``.
DoD-13 and DoD-14 are ``[manual/live]``.

Test applications are built locally: a bare ``FastAPI()`` with the one registered error
handler, settings pinned through ``app.dependency_overrides[get_settings]``. The
``require_role(...)`` factory is only ever called inside fixtures or test bodies.
"""

import ast
import inspect
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Depends, FastAPI, Response
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Table, select, update

from app import roles as roles_module
from app.config import Settings, get_settings
from app.db import schema
from app.dependencies import (
    CurrentUser,
    clear_session_cookie,
    require_role,
    require_user,
    set_session_cookie,
)
from app.errors import register_exception_handlers
from app.ids import SnowflakeGenerator
from app.roles import ROLE_LADDER, Role, role_at_least
from app.services.auth import open_session, revoke_session

BACKEND_DIR = Path(__file__).resolve().parent.parent

TIMESTAMP = "2026-01-01T00:00:00+00:00"
FAKE_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$aGFzaGhhc2hoYXNoaGFzaA"

# Usernames deliberately contain neither role name, so DoD-10's "names no role" scan is clean.
ADMIN_ID = 8_000_001
ADMIN_NAME = "founder"
PLAYER_ID = 8_000_002
PLAYER_NAME = "wanderer"

TTL_HOURS = 720
OTHER_COOKIE_NAME = "a_differently_named_session_cookie"

USER_PATH = "/probe/user"
ADMIN_PATH = "/probe/admin"
ROUTER_USER_PATH = "/router-guarded/user/probe"
ROUTER_ADMIN_PATH = "/router-guarded/admin/probe"

NOT_AUTHENTICATED = "not_authenticated"
INSUFFICIENT_ROLE = "insufficient_role"


# --------------------------------------------------------------------------- seeding


def _users() -> Table:
    return schema.metadata.tables["users"]


def _sessions() -> Table:
    return schema.metadata.tables["auth_sessions"]


def _insert_user(engine: Engine, *, user_id: int, username: str, role: Role, enabled: bool = True) -> None:
    with engine.begin() as connection:
        connection.execute(
            _users().insert().values(
                id=user_id,
                username=username,
                password_hash=FAKE_HASH,
                role=role,
                is_enabled=enabled,
                rp_language=None,
                preferred_language=None,
                created_at=TIMESTAMP,
                updated_at=TIMESTAMP,
            )
        )


@pytest.fixture
def engine(db_engine: Engine) -> Engine:
    """A per-test database with the registry applied and one administrator + one roleplayer."""
    with db_engine.begin() as connection:
        schema.metadata.create_all(connection)
    _insert_user(db_engine, user_id=ADMIN_ID, username=ADMIN_NAME, role=Role.ADMIN)
    _insert_user(db_engine, user_id=PLAYER_ID, username=PLAYER_NAME, role=Role.ROLEPLAYER)
    return db_engine


def _open(engine: Engine, user_id: int) -> str:
    """Open a live session through step 001's service and return its plaintext token."""
    with engine.connect() as connection:
        return open_session(connection, SnowflakeGenerator(node_id=1), user_id, TTL_HOURS).token


def _revoke(engine: Engine, token: str) -> None:
    with engine.connect() as connection:
        revoke_session(connection, token)


def _session_row_for(engine: Engine, user_id: int) -> dict[str, Any]:
    with engine.connect() as connection:
        mappings = connection.execute(select(_sessions())).mappings()
        rows = [dict(row) for row in mappings if row["user_id"] == user_id]
    assert len(rows) == 1
    return rows[0]


def _expire_session_of(engine: Engine, user_id: int) -> None:
    """Move the user's session into the past by rewriting only the year of its stored timestamps."""
    row = _session_row_for(engine, user_id)
    with engine.begin() as connection:
        connection.execute(
            update(_sessions())
            .where(_sessions().c.id == row["id"])
            .values(created_at="2000" + row["created_at"][4:], expires_at="2000" + row["expires_at"][4:])
        )


def _set_user(engine: Engine, user_id: int, **values: Any) -> None:
    with engine.begin() as connection:
        connection.execute(update(_users()).where(_users().c.id == user_id).values(**values))


# --------------------------------------------------------------------------- the probe app


@dataclass
class Probe:
    """A locally built application plus a record of what its handlers received."""

    app: FastAPI
    received: list[tuple[str, CurrentUser]] = field(default_factory=list)
    reached: list[str] = field(default_factory=list)


def _build_probe(settings: Settings) -> Probe:
    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    probe = Probe(app=app)

    # Handler-level guards.
    @app.get(USER_PATH)
    def user_probe(current: Annotated[CurrentUser, Depends(require_user)]) -> dict[str, Any]:
        probe.reached.append(USER_PATH)
        probe.received.append((USER_PATH, current))
        return {"reached": True}

    @app.get(ADMIN_PATH)
    def admin_probe(current: Annotated[CurrentUser, Depends(require_role(Role.ADMIN))]) -> dict[str, Any]:
        probe.reached.append(ADMIN_PATH)
        probe.received.append((ADMIN_PATH, current))
        return {"reached": True}

    # Router-level guards: the routes below declare nothing of their own (DoD-12).
    user_router = APIRouter(prefix="/router-guarded/user", dependencies=[Depends(require_user)])

    @user_router.get("/probe")
    def router_user_probe() -> dict[str, Any]:
        probe.reached.append(ROUTER_USER_PATH)
        return {"reached": True}

    admin_router = APIRouter(prefix="/router-guarded/admin", dependencies=[Depends(require_role(Role.ADMIN))])

    @admin_router.get("/probe")
    def router_admin_probe() -> dict[str, Any]:
        probe.reached.append(ROUTER_ADMIN_PATH)
        return {"reached": True}

    app.include_router(user_router)
    app.include_router(admin_router)
    return probe


@pytest.fixture
def probe(db_settings: Settings, engine: Engine) -> Iterator[Probe]:
    built = _build_probe(db_settings)
    try:
        yield built
    finally:
        built.app.dependency_overrides.clear()


def _get(probe: Probe, path: str, cookie: tuple[str, str] | None = None) -> Any:
    headers = {} if cookie is None else {"Cookie": f"{cookie[0]}={cookie[1]}"}
    return TestClient(probe.app).get(path, headers=headers)


def _assert_envelope(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    payload = response.json()
    assert isinstance(payload, dict)
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"code", "message", "detail"}
    assert payload["error"]["code"] == code
    assert payload["error"]["detail"] == {}
    return payload


# =========================================================================== DoD-1


def test_ladder_covers_every_role_member__DoD1() -> None:
    """DoD-1 — every member of the enum has a rung; a member without one is a failure."""
    assert set(ROLE_LADDER) == set(Role)
    assert all(isinstance(key, Role) for key in ROLE_LADDER)


def test_ladder_is_exactly_the_documented_rungs__DoD1() -> None:
    """DoD-1 — ``{roleplayer: 0, admin: 1}`` as domain-rules.md states."""
    assert ROLE_LADDER == {Role.ROLEPLAYER: 0, Role.ADMIN: 1}
    assert ROLE_LADDER[Role.ROLEPLAYER] < ROLE_LADDER[Role.ADMIN]
    assert all(type(rung) is int for rung in ROLE_LADDER.values())


# =========================================================================== DoD-2


@pytest.mark.parametrize("role", list(Role))
def test_equal_roles_are_at_least_each_other__DoD2(role: Role) -> None:
    """DoD-2 — true for equal roles."""
    assert role_at_least(role, role) is True


def test_higher_role_meets_a_lower_minimum__DoD2() -> None:
    """DoD-2 — true for a higher role against a lower minimum."""
    assert role_at_least(Role.ADMIN, Role.ROLEPLAYER) is True


def test_lower_role_does_not_meet_a_higher_minimum__DoD2() -> None:
    """DoD-2 — false for a lower role against a higher minimum."""
    assert role_at_least(Role.ROLEPLAYER, Role.ADMIN) is False


# =========================================================================== DoD-3


def _roles_imports() -> list[str]:
    tree = ast.parse(inspect.getsource(roles_module))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    return imported


def test_roles_module_exposes_the_ladder_and_the_comparison__DoD3() -> None:
    """DoD-3 — the module now exposes the ladder and the comparison beside the enum."""
    assert roles_module.ROLE_LADDER is ROLE_LADDER
    assert roles_module.role_at_least is role_at_least
    assert roles_module.Role is Role


def test_roles_module_imports_no_fastapi__DoD3() -> None:
    """DoD-3 — no ``fastapi`` (or its ``starlette`` base) import in ``app/roles.py``."""
    offenders = [name for name in _roles_imports() if name.split(".")[0] in {"fastapi", "starlette"}]
    assert offenders == []


def test_roles_module_exposes_no_dependency_and_no_request__DoD3() -> None:
    """DoD-3 — no dependency, no ``Request``, no fastapi/starlette object in the module namespace."""
    names = set(vars(roles_module))
    for forbidden in ("Request", "Depends", "CurrentUser", "require_user", "require_role"):
        assert forbidden not in names
    offenders = []
    for name, value in vars(roles_module).items():
        origin = getattr(value, "__module__", None) or ""
        if isinstance(origin, str) and origin.split(".")[0] in {"fastapi", "starlette"}:
            offenders.append(name)
    assert offenders == []


def test_roles_module_is_importable_without_importing_fastapi__DoD3() -> None:
    """DoD-3 — in a fresh interpreter, importing ``app.roles`` loads no ``fastapi`` module (D8)."""
    script = (
        "import sys\n"
        "import app.roles\n"
        "loaded = sorted(m for m in sys.modules if m.split('.')[0] in ('fastapi', 'starlette'))\n"
        "print(','.join(loaded))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == ""


# =========================================================================== DoD-5


def test_no_cookie_answers_401_not_authenticated__DoD5(probe: Probe) -> None:
    """DoD-5 — no cookie: 401 with the ``not_authenticated`` envelope."""
    response = _get(probe, USER_PATH)
    _assert_envelope(response, 401, NOT_AUTHENTICATED)


def test_no_cookie_never_reaches_the_handler__DoD5(probe: Probe) -> None:
    """DoD-5 — the guarded handler is not run for a cookieless call."""
    _get(probe, USER_PATH)
    assert probe.reached == []
    assert probe.received == []


def test_empty_cookie_answers_the_same_401__DoD5(probe: Probe, db_settings: Settings) -> None:
    """DoD-5 / Interface intent — an empty cookie is the same branch as a missing one."""
    response = _get(probe, USER_PATH, (db_settings.session_cookie_name, ""))
    _assert_envelope(response, 401, NOT_AUTHENTICATED)
    assert probe.reached == []


# =========================================================================== DoD-6


def _dead_token(kind: str, engine: Engine) -> str:
    if kind == "unissued":
        _open(engine, PLAYER_ID)  # a live session exists, but not for this token
        return "this-token-was-never-issued-by-anyone-at-all-0000"
    token = _open(engine, PLAYER_ID)
    if kind == "revoked":
        _revoke(engine, token)
    elif kind == "expired":
        _expire_session_of(engine, PLAYER_ID)
    elif kind == "disabled":
        _set_user(engine, PLAYER_ID, is_enabled=False)
    else:  # pragma: no cover - parametrization guard
        raise AssertionError(kind)
    return token


@pytest.mark.parametrize("kind", ["unissued", "revoked", "expired", "disabled"])
def test_dead_session_cookie_answers_401__DoD6(
    probe: Probe, engine: Engine, db_settings: Settings, kind: str
) -> None:
    """DoD-6 — unissued, revoked, expired or disabled-user tokens all answer 401 (US-007.AC-2)."""
    token = _dead_token(kind, engine)
    response = _get(probe, USER_PATH, (db_settings.session_cookie_name, token))
    _assert_envelope(response, 401, NOT_AUTHENTICATED)
    assert probe.reached == []


def test_every_dead_session_answers_the_identical_response__DoD6(engine: Engine, db_settings: Settings) -> None:
    """DoD-6 — the four cases, and the cookieless case, are indistinguishable on the wire."""
    bodies = []
    for kind in ("unissued", "revoked", "expired", "disabled"):
        # A fresh token per case: re-enable the player so each case stands on its own.
        _set_user(engine, PLAYER_ID, is_enabled=True)
        with engine.begin() as connection:
            connection.execute(_sessions().delete())
        built = _build_probe(db_settings)
        token = _dead_token(kind, engine)
        response = _get(built, USER_PATH, (db_settings.session_cookie_name, token))
        assert response.status_code == 401
        bodies.append(response.json())
    cookieless = _get(_build_probe(db_settings), USER_PATH)
    bodies.append(cookieless.json())
    assert all(body == bodies[0] for body in bodies)


# =========================================================================== DoD-7


@pytest.mark.parametrize(
    ("user_id", "username", "role"),
    [(ADMIN_ID, ADMIN_NAME, Role.ADMIN), (PLAYER_ID, PLAYER_NAME, Role.ROLEPLAYER)],
)
def test_live_session_reaches_the_handler_with_the_current_user__DoD7(
    probe: Probe, engine: Engine, db_settings: Settings, user_id: int, username: str, role: Role
) -> None:
    """DoD-7 — a live token reaches the handler, which receives that user's id, username and role."""
    token = _open(engine, user_id)
    response = _get(probe, USER_PATH, (db_settings.session_cookie_name, token))
    assert response.status_code == 200
    assert probe.reached == [USER_PATH]
    (path, current), = probe.received
    assert path == USER_PATH
    assert isinstance(current, CurrentUser)
    assert current.id == user_id
    assert current.username == username
    assert current.role == role


def test_role_change_is_seen_on_the_next_call_without_a_new_session__DoD7(
    probe: Probe, engine: Engine, db_settings: Settings
) -> None:
    """DoD-7 — the role is read live from ``users``: changing it changes the next ``CurrentUser`` (D7)."""
    token = _open(engine, PLAYER_ID)
    cookie = (db_settings.session_cookie_name, token)

    assert _get(probe, USER_PATH, cookie).status_code == 200
    _set_user(engine, PLAYER_ID, role=Role.ADMIN)
    assert _get(probe, USER_PATH, cookie).status_code == 200
    _set_user(engine, PLAYER_ID, role=Role.ROLEPLAYER)
    assert _get(probe, USER_PATH, cookie).status_code == 200

    roles_seen = [current.role for _, current in probe.received]
    assert roles_seen == [Role.ROLEPLAYER, Role.ADMIN, Role.ROLEPLAYER]
    assert {current.id for _, current in probe.received} == {PLAYER_ID}
    with engine.connect() as connection:
        assert len(connection.execute(select(_sessions())).all()) == 1


# =========================================================================== DoD-8


def test_overridden_cookie_name_is_honoured__DoD8(engine: Engine, db_settings: Settings) -> None:
    """DoD-8 — with the setting overridden, a live token under the new name is accepted."""
    renamed = db_settings.model_copy(update={"session_cookie_name": OTHER_COOKIE_NAME})
    built = _build_probe(renamed)
    token = _open(engine, PLAYER_ID)
    response = _get(built, USER_PATH, (OTHER_COOKIE_NAME, token))
    assert response.status_code == 200
    assert [current.id for _, current in built.received] == [PLAYER_ID]


def test_default_named_cookie_is_ignored_when_the_setting_says_otherwise__DoD8(
    engine: Engine, db_settings: Settings
) -> None:
    """DoD-8 — a live token under the default name answers 401 once the setting names another cookie."""
    default_name = db_settings.session_cookie_name
    assert default_name != OTHER_COOKIE_NAME
    renamed = db_settings.model_copy(update={"session_cookie_name": OTHER_COOKIE_NAME})
    built = _build_probe(renamed)
    token = _open(engine, PLAYER_ID)
    response = _get(built, USER_PATH, (default_name, token))
    _assert_envelope(response, 401, NOT_AUTHENTICATED)
    assert built.reached == []


def test_default_setting_honours_the_default_name_only__DoD8(
    probe: Probe, engine: Engine, db_settings: Settings
) -> None:
    """DoD-8 — under unmodified settings, the same live token under another name is not honoured."""
    token = _open(engine, PLAYER_ID)
    _assert_envelope(_get(probe, USER_PATH, (OTHER_COOKIE_NAME, token)), 401, NOT_AUTHENTICATED)
    assert _get(probe, USER_PATH, (db_settings.session_cookie_name, token)).status_code == 200


# =========================================================================== DoD-9


def test_roleplayer_below_the_admin_rung_answers_403__DoD9(
    probe: Probe, engine: Engine, db_settings: Settings
) -> None:
    """DoD-9 — a live roleplayer session on an admin-guarded route: 403 ``insufficient_role``."""
    token = _open(engine, PLAYER_ID)
    response = _get(probe, ADMIN_PATH, (db_settings.session_cookie_name, token))
    _assert_envelope(response, 403, INSUFFICIENT_ROLE)
    assert probe.reached == []


def test_administrator_reaches_the_admin_guarded_handler__DoD9(
    probe: Probe, engine: Engine, db_settings: Settings
) -> None:
    """DoD-9 — a live administrator session reaches the handler with the same ``CurrentUser``."""
    token = _open(engine, ADMIN_ID)
    response = _get(probe, ADMIN_PATH, (db_settings.session_cookie_name, token))
    assert response.status_code == 200
    assert probe.reached == [ADMIN_PATH]
    (_, current), = probe.received
    assert isinstance(current, CurrentUser)
    assert (current.id, current.username, current.role) == (ADMIN_ID, ADMIN_NAME, Role.ADMIN)


def test_no_session_on_an_admin_guarded_route_is_401_not_403__DoD9(probe: Probe) -> None:
    """DoD-9 — authentication precedes authorization: no session gives 401."""
    response = _get(probe, ADMIN_PATH)
    _assert_envelope(response, 401, NOT_AUTHENTICATED)
    assert probe.reached == []


def test_dead_session_on_an_admin_guarded_route_is_401_not_403__DoD9(
    probe: Probe, engine: Engine, db_settings: Settings
) -> None:
    """DoD-9 — a revoked roleplayer session is still "no live session": 401, not 403."""
    token = _open(engine, PLAYER_ID)
    _revoke(engine, token)
    response = _get(probe, ADMIN_PATH, (db_settings.session_cookie_name, token))
    _assert_envelope(response, 401, NOT_AUTHENTICATED)


def test_demoted_admin_is_refused_on_the_next_call__DoD9(
    probe: Probe, engine: Engine, db_settings: Settings
) -> None:
    """DoD-9 / D7 — the rung is compared against the live role, not the one at login."""
    token = _open(engine, ADMIN_ID)
    cookie = (db_settings.session_cookie_name, token)
    assert _get(probe, ADMIN_PATH, cookie).status_code == 200
    _set_user(engine, ADMIN_ID, role=Role.ROLEPLAYER)
    _assert_envelope(_get(probe, ADMIN_PATH, cookie), 403, INSUFFICIENT_ROLE)


# =========================================================================== DoD-10


def test_insufficient_role_body_names_no_role__DoD10(probe: Probe, engine: Engine, db_settings: Settings) -> None:
    """DoD-10 — the 403 body names neither the caller's role nor the required one."""
    token = _open(engine, PLAYER_ID)
    response = _get(probe, ADMIN_PATH, (db_settings.session_cookie_name, token))
    payload = _assert_envelope(response, 403, INSUFFICIENT_ROLE)
    assert payload["error"]["detail"] == {}
    rendered = response.text.lower()
    for role in Role:
        assert role.value.lower() not in rendered
    assert "admin" not in rendered


# =========================================================================== DoD-11


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key.decode("latin-1").lower() == "set-cookie"
    ]


def _parse_set_cookie(header: str) -> tuple[str, str, dict[str, str | None]]:
    """Split one ``Set-Cookie`` header into (name, value, lower-cased attribute map)."""
    parts = [part.strip() for part in header.split(";")]
    name, _, value = parts[0].partition("=")
    attributes: dict[str, str | None] = {}
    for part in parts[1:]:
        if not part:
            continue
        key, sep, attr_value = part.partition("=")
        attributes[key.strip().lower()] = attr_value.strip() if sep else None
    return name.strip(), value.strip().strip('"'), attributes


def _only_cookie(response: Response) -> tuple[str, str, dict[str, str | None]]:
    headers = _set_cookie_headers(response)
    assert len(headers) == 1
    return _parse_set_cookie(headers[0])


@pytest.mark.parametrize("ttl_hours", [720, 3])
def test_writer_sets_the_cookie_with_the_d6_flags__DoD11(db_settings: Settings, ttl_hours: int) -> None:
    """DoD-11 — configured name, the token, HttpOnly, SameSite=Lax, Path=/, no Secure, Max-Age = TTL (D6)."""
    response = Response()
    set_session_cookie(response, "the-opaque-token-value", ttl_hours, db_settings)
    name, value, attributes = _only_cookie(response)
    assert name == db_settings.session_cookie_name
    assert value == "the-opaque-token-value"
    assert "httponly" in attributes
    assert (attributes.get("samesite") or "").lower() == "lax"
    assert attributes.get("path") == "/"
    assert "secure" not in attributes
    assert attributes.get("max-age") == str(ttl_hours * 3600)


def test_writer_uses_the_configured_name__DoD11(db_settings: Settings) -> None:
    """DoD-11 — overriding the setting changes the name the writer sets."""
    renamed = db_settings.model_copy(update={"session_cookie_name": OTHER_COOKIE_NAME})
    response = Response()
    set_session_cookie(response, "the-opaque-token-value", TTL_HOURS, renamed)
    name, value, _ = _only_cookie(response)
    assert name == OTHER_COOKIE_NAME
    assert value == "the-opaque-token-value"


def _is_cleared(value: str, attributes: dict[str, str | None]) -> bool:
    """True when the header tells the browser to drop the cookie now."""
    max_age = attributes.get("max-age")
    if max_age is not None:
        try:
            if int(max_age) <= 0:
                return True
        except ValueError:
            pass
    expires = attributes.get("expires")
    if expires:
        try:
            when = parsedate_to_datetime(expires)
        except (TypeError, ValueError):
            return False
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return when <= datetime.now(UTC)
    return False


@pytest.mark.parametrize("renamed", [False, True])
def test_clearer_clears_the_same_name_at_the_same_path__DoD11(db_settings: Settings, renamed: bool) -> None:
    """DoD-11 — the clearer targets the configured name at ``Path=/`` and expires it immediately."""
    settings = (
        db_settings.model_copy(update={"session_cookie_name": OTHER_COOKIE_NAME}) if renamed else db_settings
    )
    written = Response()
    set_session_cookie(written, "the-opaque-token-value", TTL_HOURS, settings)
    written_name, _, written_attributes = _only_cookie(written)

    cleared = Response()
    clear_session_cookie(cleared, settings)
    name, value, attributes = _only_cookie(cleared)
    assert name == settings.session_cookie_name
    assert name == written_name
    assert attributes.get("path") == "/"
    assert attributes.get("path") == written_attributes.get("path")
    assert value != "the-opaque-token-value"
    assert _is_cleared(value, attributes)


def test_writer_and_clearer_work_through_a_route__DoD11(db_settings: Settings) -> None:
    """DoD-11 — called on FastAPI's injected response, the cookie reaches the client with the D6 flags."""
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: db_settings

    @app.post("/write")
    def write(response: Response, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, bool]:
        set_session_cookie(response, "route-token", 2, settings)
        return {"ok": True}

    @app.post("/clear")
    def clear(response: Response, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, bool]:
        clear_session_cookie(response, settings)
        return {"ok": True}

    client = TestClient(app)
    write_headers = client.post("/write").headers.get_list("set-cookie")
    assert len(write_headers) == 1
    name, value, attributes = _parse_set_cookie(write_headers[0])
    assert (name, value) == (db_settings.session_cookie_name, "route-token")
    assert "httponly" in attributes
    assert (attributes.get("samesite") or "").lower() == "lax"
    assert attributes.get("path") == "/"
    assert "secure" not in attributes
    assert attributes.get("max-age") == str(2 * 3600)

    clear_headers = client.post("/clear").headers.get_list("set-cookie")
    assert len(clear_headers) == 1
    name, value, attributes = _parse_set_cookie(clear_headers[0])
    assert name == db_settings.session_cookie_name
    assert attributes.get("path") == "/"
    assert _is_cleared(value, attributes)


# =========================================================================== DoD-12


def test_router_level_require_user_guards_a_route_that_declares_nothing__DoD12(
    probe: Probe, engine: Engine, db_settings: Settings
) -> None:
    """DoD-12 — a router carrying ``require_user`` guards its route: 401 without, 200 with a live session."""
    _assert_envelope(_get(probe, ROUTER_USER_PATH), 401, NOT_AUTHENTICATED)
    assert probe.reached == []
    token = _open(engine, PLAYER_ID)
    assert _get(probe, ROUTER_USER_PATH, (db_settings.session_cookie_name, token)).status_code == 200
    assert probe.reached == [ROUTER_USER_PATH]


def test_router_level_require_role_guards_a_route_that_declares_nothing__DoD12(
    probe: Probe, engine: Engine, db_settings: Settings
) -> None:
    """DoD-12 — a router carrying ``require_role(ADMIN)``: 401 / 403 / 200 by caller.

    The route itself declares nothing.
    """
    _assert_envelope(_get(probe, ROUTER_ADMIN_PATH), 401, NOT_AUTHENTICATED)
    player = _open(engine, PLAYER_ID)
    _assert_envelope(
        _get(probe, ROUTER_ADMIN_PATH, (db_settings.session_cookie_name, player)), 403, INSUFFICIENT_ROLE
    )
    assert probe.reached == []
    admin = _open(engine, ADMIN_ID)
    assert _get(probe, ROUTER_ADMIN_PATH, (db_settings.session_cookie_name, admin)).status_code == 200
    assert probe.reached == [ROUTER_ADMIN_PATH]


def test_require_role_is_a_factory_returning_a_dependency__DoD12() -> None:
    """DoD-12 / Interface intent — ``require_role(min_role)`` returns a callable usable in ``Depends``."""
    dependency: Callable[..., CurrentUser] = require_role(Role.ADMIN)
    assert callable(dependency)
    router = APIRouter(dependencies=[Depends(dependency)])  # constructible at router level
    assert len(router.dependencies) == 1
