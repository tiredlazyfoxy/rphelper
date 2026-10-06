"""Shared pytest fixtures for the backend test suite.

Step 001 establishes the environment-isolation fixture. Step 005 adds the temp-file
database fixture (decision D4), which could not land before ``app/db/engine.py`` existed.
"""

import ipaddress
import os
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from argon2 import PasswordHasher
from sqlalchemy import Engine

import app.services.passwords as passwords
from app.config import Settings, get_settings
from app.db.engine import dispose_engines, get_engine

ENV_PREFIX = "RPHELPER_"

# --- Test-speed and network guards ---------------------------------------------------

#: Minimal-cost Argon2id. Still a real `$argon2id$` hash; only the cost parameters drop.
CHEAP_HASHER = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)

_LOOPBACK_NAMES = {"localhost", "localhost.localdomain"}
_real_getaddrinfo = socket.getaddrinfo
_real_connect = socket.socket.connect


def _is_loopback(host: Any) -> bool:
    if isinstance(host, bytes):
        host = host.decode()
    if not isinstance(host, str):
        return True  # AF_UNIX paths and the like
    if host.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
    if not _is_loopback(host):
        raise socket.gaierror(socket.EAI_NONAME, f"network disabled in tests: {host!r}")
    return _real_getaddrinfo(host, *args, **kwargs)


def _guarded_connect(self: socket.socket, address: Any) -> Any:
    host = address[0] if isinstance(address, tuple) else address
    if not _is_loopback(host):
        raise ConnectionRefusedError(f"network disabled in tests: {host!r}")
    return _real_connect(self, address)


@pytest.fixture(autouse=True)
def no_external_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail every non-loopback lookup or connect **instantly**.

    A fake URL (``http://llm.test:8080``) therefore answers like an unreachable server
    at once, never after a DNS or request timeout. Tests marked ``live`` are exempt.
    """
    if request.node.get_closest_marker("live"):
        return
    monkeypatch.setattr(socket, "getaddrinfo", _guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)


@pytest.fixture(autouse=True)
def cheap_password_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap production-cost Argon2id for minimal cost; hashing dominated per-test setup."""
    monkeypatch.setattr(passwords, "_hasher", CHEAP_HASHER)

# Feature 028 D2 reads these two from the environment without the ``RPHELPER_`` prefix.
SEARCH_CREDENTIAL_VARIABLES = ("SEARCH_CSE_KEY", "SEARCH_CSE_ID")


@pytest.fixture(autouse=True)
def isolated_settings_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear every ``RPHELPER_*`` variable and the settings cache around each test.

    No test may observe another test's configuration. Settings are overridden through
    the accessor's cache or through ``dependency_overrides``, never by monkey-patching a
    module global.

    Feature 028 step 001 (D12) adds the two **unprefixed** search credentials, which the
    ``RPHELPER_`` sweep above cannot reach. They are set to ``""`` rather than deleted:
    pydantic-settings reads the environment above ``env_file``, so a present-but-blank
    value is what stops a developer's ``backend/.env`` from supplying a live credential.
    Every test therefore sees an **unconfigured** instance unless it supplies values
    itself (its own ``monkeypatch.setenv``, init arguments, or a ``get_settings``
    override), and no test can reach Google by accident. ``monkeypatch`` restores the
    original values afterwards.
    """
    for key in list(os.environ):
        if key.upper().startswith(ENV_PREFIX):
            monkeypatch.delenv(key, raising=False)
    for name in SEARCH_CREDENTIAL_VARIABLES:
        monkeypatch.setenv(name, "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- Step 005: the temp-file database fixture (decision D4) -------------------------


@pytest.fixture
def db_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    """Settings pointing at a per-test SQLite **file** under ``tmp_path``.

    D4: a real ``.sqlite`` file, one per test, never ``:memory:`` — WAL is a no-op in
    memory and the extension load takes a different path there.

    ``data_dir`` is deliberately **not** created: the engine layer is what must create a
    missing one. The engine cache is process-global, so the cache is emptied on both
    sides of the test to keep engine identity independent of test ordering.
    """
    data_dir = tmp_path / "data"
    monkeypatch.setenv("RPHELPER_DATA_DIR", str(data_dir))
    monkeypatch.setenv("RPHELPER_DB_FILENAME", "test.sqlite")
    get_settings.cache_clear()
    dispose_engines()
    try:
        yield get_settings()
    finally:
        dispose_engines()
        get_settings.cache_clear()


@pytest.fixture
def db_engine(db_settings: Settings) -> Engine:
    """The engine for the per-test database, obtained through the production factory.

    Teardown is ``db_settings``'s ``dispose_engines()``, which runs after this fixture.
    """
    return get_engine(db_settings)
