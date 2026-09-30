"""Tests for ``app.config`` — the ``Settings`` model and its cached accessor.

Every expected value in this module comes from the field table in
``docs/plans/001.backend-foundation/001.context.md``. Covers DoD-1 .. DoD-7 of
``001.scaffold-and-config.md``.
"""

import ast
import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.config import Settings, get_settings

# The ten fields, verbatim from 001.context.md: name -> (default, validation alias).
# 006/001 DoD-10 (feature 006 context.md D13) deliberately adds an eleventh field, the
# outbound-call timeout; the ten original entries are unchanged.
EXPECTED_FIELDS: dict[str, tuple[Any, str]] = {
    "data_dir": (Path("data"), "RPHELPER_DATA_DIR"),
    "db_filename": ("rphelper.sqlite", "RPHELPER_DB_FILENAME"),
    "node_id": (0, "RPHELPER_NODE_ID"),
    "session_cookie_name": ("rphelper_session", "RPHELPER_SESSION_COOKIE_NAME"),
    "session_ttl_hours": (720, "RPHELPER_SESSION_TTL_HOURS"),
    "log_console_level": ("DEBUG", "RPHELPER_LOG_CONSOLE_LEVEL"),
    "log_file_level": ("WARNING", "RPHELPER_LOG_FILE_LEVEL"),
    "log_file_path": (Path("data/logs/rphelper.log"), "RPHELPER_LOG_FILE_PATH"),
    "log_file_rotation": ("10 MB", "RPHELPER_LOG_FILE_ROTATION"),
    "log_file_retention": (5, "RPHELPER_LOG_FILE_RETENTION"),
    "llm_request_timeout_seconds": (30.0, "RPHELPER_LLM_REQUEST_TIMEOUT_SECONDS"),
}

# The ten fields as 001.context.md recorded them, before feature 006 added the eleventh.
ORIGINAL_TEN_FIELDS: dict[str, tuple[Any, str]] = {
    name: value for name, value in EXPECTED_FIELDS.items() if name != "llm_request_timeout_seconds"
}

# Per-field override probes: field -> (raw environment string, expected parsed value).
# Every value differs from the field's default so the assertion cannot pass vacuously.
OVERRIDES: dict[str, tuple[str, Any]] = {
    "data_dir": ("custom-data", Path("custom-data")),
    "db_filename": ("other.sqlite", "other.sqlite"),
    "node_id": ("7", 7),
    "session_cookie_name": ("other_session", "other_session"),
    "session_ttl_hours": ("24", 24),
    "log_console_level": ("INFO", "INFO"),
    "log_file_level": ("ERROR", "ERROR"),
    "log_file_path": ("custom/logs/other.log", Path("custom/logs/other.log")),
    "log_file_rotation": ("50 MB", "50 MB"),
    "log_file_retention": ("9", 9),
    "llm_request_timeout_seconds": ("2.5", 2.5),
}


def _hermetic_settings() -> Settings:
    """A ``Settings`` built without any ``.env`` file.

    ``env_file`` resolves relative to the process working directory (``backend/``), so a
    stray local ``backend/.env`` would otherwise leak into a defaults assertion. Passing
    ``_env_file=None`` neutralises it; the autouse fixture handles the environment itself.
    """
    return Settings(_env_file=None)  # type: ignore[call-arg]


# --------------------------------------------------------------------------- DoD-1


def test_settings_declares_exactly_the_named_fields__DoD1() -> None:
    """DoD-1: exactly the named fields, and nothing else.

    006/001 DoD-10: updated deliberately from ten to eleven — the outbound-call timeout joins.
    """
    assert set(Settings.model_fields) == set(EXPECTED_FIELDS)
    assert len(Settings.model_fields) == 11


@pytest.mark.parametrize("field_name", sorted(EXPECTED_FIELDS))
def test_each_field_carries_its_recorded_default__DoD1(field_name: str) -> None:
    """DoD-1: each field carries the default recorded in the field table."""
    expected_default = EXPECTED_FIELDS[field_name][0]
    settings = _hermetic_settings()
    assert getattr(settings, field_name) == expected_default


# --------------------------------------------------------------------------- DoD-2


@pytest.mark.parametrize("field_name", sorted(EXPECTED_FIELDS))
def test_field_is_populated_from_its_prefixed_environment_variable__DoD2(
    field_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DoD-2: setting ``RPHELPER_<FIELD>`` changes the field."""
    env_var = EXPECTED_FIELDS[field_name][1]
    raw_value, expected = OVERRIDES[field_name]
    assert expected != EXPECTED_FIELDS[field_name][0]

    monkeypatch.setenv(env_var, raw_value)
    settings = _hermetic_settings()
    assert getattr(settings, field_name) == expected


# --------------------------------------------------------------------------- DoD-3


@pytest.mark.parametrize("field_name", sorted(EXPECTED_FIELDS))
def test_unprefixed_variable_does_not_populate_the_field__DoD3(
    field_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DoD-3: a variable named after the field without the ``RPHELPER_`` prefix is ignored.

    The validation alias replaces the field name as the environment key entirely, so the
    bare name has no effect and the default survives.
    """
    default_value = EXPECTED_FIELDS[field_name][0]
    raw_value = OVERRIDES[field_name][0]

    monkeypatch.setenv(field_name.upper(), raw_value)
    settings = _hermetic_settings()
    assert getattr(settings, field_name) == default_value


# --------------------------------------------------------------------------- DoD-4


def test_unrelated_environment_variables_do_not_break_construction__DoD4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DoD-4: extra keys are ignored — construction still succeeds and defaults hold."""
    monkeypatch.setenv("SOME_UNRELATED_VARIABLE", "whatever")
    monkeypatch.setenv("RPHELPER_NOT_A_REAL_SETTING", "whatever")

    settings = _hermetic_settings()

    for field_name, (default_value, _alias) in EXPECTED_FIELDS.items():
        assert getattr(settings, field_name) == default_value


# --------------------------------------------------------------------------- DoD-5


def test_there_is_no_port_field__DoD5() -> None:
    """DoD-5: no ``port`` field and no port-shaped setting — ports are topology."""
    field_names = set(Settings.model_fields)
    assert "port" not in field_names
    port_shaped = [name for name in field_names if "port" in name.lower()]
    assert port_shaped == []

    settings = _hermetic_settings()
    assert not hasattr(settings, "port")


# --------------------------------------------------------------------------- DoD-6


def test_accessor_returns_the_identical_object_on_repeated_calls__DoD6() -> None:
    """DoD-6: the accessor is memoised — repeated calls return the same object."""
    first = get_settings()
    second = get_settings()
    assert first is second


def test_accessor_rereads_the_environment_after_cache_clear__DoD6(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DoD-6: after the cache is cleared the accessor re-reads the environment."""
    first = get_settings()
    assert first.node_id == 0
    assert first.db_filename == "rphelper.sqlite"

    monkeypatch.setenv("RPHELPER_NODE_ID", "7")
    monkeypatch.setenv("RPHELPER_DB_FILENAME", "other.sqlite")

    cached_again = get_settings()
    assert cached_again is first

    get_settings.cache_clear()
    refreshed = get_settings()

    assert refreshed is not first
    assert refreshed.node_id == 7
    assert refreshed.db_filename == "other.sqlite"


# --------------------------------------------------------------------------- DoD-7


@pytest.mark.parametrize("module_name", ["app", "app.routers", "app.services"])
def test_packages_import_cleanly__DoD7(module_name: str) -> None:
    """DoD-7: ``app``, ``app.routers`` and ``app.services`` import cleanly."""
    module = importlib.import_module(module_name)
    assert module.__name__ == module_name


def test_services_package_defines_nothing_beyond_its_docstring__DoD7() -> None:
    """DoD-7: ``app/services/__init__.py`` holds its docstring and no other statement.

    The assertion is made against the package marker's own source, so it is independent
    of which other modules the process has imported: importing a sibling module inside a
    package binds that module as an attribute on the package object, and that binding is
    Python's import machinery, not a name the marker defines.
    """
    module = importlib.import_module("app.services")
    marker = getattr(module, "__file__", None)
    assert marker is not None, "app.services has no package marker on disk"

    tree = ast.parse(Path(marker).read_text(encoding="utf-8"))

    docstring = ast.get_docstring(tree)
    assert docstring is not None, "app/services/__init__.py carries no module docstring"
    assert docstring.strip() != ""

    # The docstring is the module body's first statement; nothing may follow it.
    statements_after_the_docstring = [type(node).__name__ for node in tree.body[1:]]
    assert statements_after_the_docstring == []


def test_services_package_binds_no_name_of_its_own__DoD7() -> None:
    """DoD-7: at runtime ``app.services`` carries no public name it defined itself.

    Submodules of the package are excluded: they are attributes bound by the import
    machinery when some other module imports them, so counting them would make this
    assertion depend on test ordering. Anything else public — a constant, a function, a
    re-export — is a name the package marker defined, and fails here.
    """
    module = importlib.import_module("app.services")

    def is_own_submodule(value: object) -> bool:
        return isinstance(value, ModuleType) and value.__name__.startswith("app.services.")

    own_names = [
        name
        for name, value in vars(module).items()
        if not name.startswith("_") and not is_own_submodule(value)
    ]
    assert own_names == []


# ============================================================================
# Feature 006, step 001 (``001.tables-errors-and-secret-ref.md``) — DoD-10:
# ``Settings`` gains the outbound-call timeout (feature 006 ``context.md`` D13): a float,
# default 30.0, read from ``RPHELPER_LLM_REQUEST_TIMEOUT_SECONDS`` only. No other field's
# default or alias changes. (The shared tables above were extended with the new field, so
# the DoD-1..DoD-4 parametrised tests cover it too.)
# ============================================================================

TIMEOUT_FIELD = "llm_request_timeout_seconds"
TIMEOUT_ALIAS = "RPHELPER_LLM_REQUEST_TIMEOUT_SECONDS"


def test_settings_exposes_the_timeout_field__S006_001_DoD10() -> None:
    """006/001 DoD-10: ``Settings`` declares the outbound-call timeout field."""
    assert TIMEOUT_FIELD in Settings.model_fields


def test_timeout_defaults_to_thirty_seconds_as_a_float__S006_001_DoD10() -> None:
    """006/001 DoD-10: the default is 30.0, a float."""
    value = getattr(_hermetic_settings(), TIMEOUT_FIELD)
    assert value == 30.0
    assert isinstance(value, float)


def test_timeout_declares_its_prefixed_validation_alias__S006_001_DoD10() -> None:
    """006/001 DoD-10: the field's explicit validation alias is ``RPHELPER_LLM_REQUEST_TIMEOUT_SECONDS``."""
    assert Settings.model_fields[TIMEOUT_FIELD].validation_alias == TIMEOUT_ALIAS


@pytest.mark.parametrize(("raw", "expected"), [("2.5", 2.5), ("0.25", 0.25), ("45", 45.0)])
def test_timeout_is_read_from_its_prefixed_variable__S006_001_DoD10(
    raw: str,
    expected: float,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """006/001 DoD-10: the prefixed variable sets the timeout, sub-second values included, as a float."""
    monkeypatch.setenv(TIMEOUT_ALIAS, raw)
    value = getattr(_hermetic_settings(), TIMEOUT_FIELD)
    assert value == expected
    assert isinstance(value, float)


def test_timeout_is_read_through_the_cached_accessor__S006_001_DoD10(monkeypatch: pytest.MonkeyPatch) -> None:
    """006/001 DoD-10: ``get_settings()`` picks the prefixed variable up like every other field."""
    monkeypatch.setenv(TIMEOUT_ALIAS, "12.5")
    get_settings.cache_clear()
    assert getattr(get_settings(), TIMEOUT_FIELD) == 12.5


@pytest.mark.parametrize(
    "unprefixed_name",
    [
        "LLM_REQUEST_TIMEOUT_SECONDS",
        "REQUEST_TIMEOUT_SECONDS",
        "LLM_TIMEOUT_SECONDS",
        "LLM_REQUEST_TIMEOUT",
        "TIMEOUT_SECONDS",
    ],
)
def test_unprefixed_similar_variable_is_ignored__S006_001_DoD10(
    unprefixed_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """006/001 DoD-10: an unprefixed variable of a similar name leaves the default in place."""
    monkeypatch.setenv(unprefixed_name, "3.0")
    assert getattr(_hermetic_settings(), TIMEOUT_FIELD) == 30.0


@pytest.mark.parametrize("field_name", sorted(ORIGINAL_TEN_FIELDS))
def test_no_other_field_default_or_alias_changed__S006_001_DoD10(field_name: str) -> None:
    """006/001 DoD-10: each of the ten pre-existing fields keeps its recorded default and alias."""
    expected_default, expected_alias = ORIGINAL_TEN_FIELDS[field_name]
    assert Settings.model_fields[field_name].validation_alias == expected_alias
    assert getattr(_hermetic_settings(), field_name) == expected_default


def test_setting_the_timeout_changes_no_other_field__S006_001_DoD10(monkeypatch: pytest.MonkeyPatch) -> None:
    """006/001 DoD-10: overriding the timeout leaves every other field at its default."""
    monkeypatch.setenv(TIMEOUT_ALIAS, "5.0")
    settings = _hermetic_settings()
    for field_name, (default_value, _alias) in ORIGINAL_TEN_FIELDS.items():
        assert getattr(settings, field_name) == default_value
