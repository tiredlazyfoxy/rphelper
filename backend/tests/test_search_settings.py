"""Tests for the two search credentials on ``Settings`` (feature 028, step 001).

Covers DoD-1 .. DoD-4 of ``docs/plans/028.web-search-tool/001.search-settings-and-google-provider.md``.
Every expected value comes from that step file, from feature 028's ``context.md`` (D2, D12)
and from ``001.context.md`` ("The settings fields", "The conftest amendment").

The aliases are deliberately **unprefixed** (D2): exactly ``SEARCH_CSE_KEY`` and
``SEARCH_CSE_ID``, never ``RPHELPER_SEARCH_CSE_*``. Nothing here reads the developer's real
``backend/.env``: every ``Settings`` is built with ``_env_file=None``, or under a working
directory changed to a temporary folder holding a fabricated ``.env``.
"""

from pathlib import Path

import pytest

from app.config import Settings, get_settings

KEY_ALIAS = "SEARCH_CSE_KEY"
ID_ALIAS = "SEARCH_CSE_ID"

KEY_FIELD = "search_cse_key"
ID_FIELD = "search_cse_id"

# Obvious fakes, the values the step file names in DoD-1.
KEY_VALUE = "k-123"
ID_VALUE = "cx-456"

PREFIXED_KEY_ALIAS = "RPHELPER_SEARCH_CSE_KEY"
PREFIXED_ID_ALIAS = "RPHELPER_SEARCH_CSE_ID"


def _hermetic_settings() -> Settings:
    """A ``Settings`` built without any ``.env`` file.

    ``_env_file=None`` neutralises the env file only, never ``os.environ``; tests that need
    a variable absent remove it themselves.
    """
    return Settings(_env_file=None)  # type: ignore[call-arg]


# --------------------------------------------------------------------------- DoD-1


def test_the_unprefixed_variables_populate_both_fields__S028_001_DoD1(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-1 (D2): `SEARCH_CSE_KEY` / `SEARCH_CSE_ID` give the key's secret value and the engine id."""
    monkeypatch.setenv(KEY_ALIAS, KEY_VALUE)
    monkeypatch.setenv(ID_ALIAS, ID_VALUE)

    settings = _hermetic_settings()

    key = getattr(settings, KEY_FIELD)
    assert key is not None
    assert key.get_secret_value() == KEY_VALUE
    assert getattr(settings, ID_FIELD) == ID_VALUE


def test_the_prefixed_variables_populate_neither_field__S028_001_DoD1(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-1 (D2): `RPHELPER_SEARCH_CSE_*` is **not** read — the prefix is deliberately dropped."""
    monkeypatch.delenv(KEY_ALIAS, raising=False)
    monkeypatch.delenv(ID_ALIAS, raising=False)
    monkeypatch.setenv(PREFIXED_KEY_ALIAS, KEY_VALUE)
    monkeypatch.setenv(PREFIXED_ID_ALIAS, ID_VALUE)

    settings = _hermetic_settings()

    assert getattr(settings, KEY_FIELD) is None
    assert getattr(settings, ID_FIELD) is None


def test_both_aliases_are_declared_exactly__S028_001_DoD1() -> None:
    """DoD-1 (D2): the two explicit validation aliases, verbatim and unprefixed."""
    assert Settings.model_fields[KEY_FIELD].validation_alias == KEY_ALIAS
    assert Settings.model_fields[ID_FIELD].validation_alias == ID_ALIAS


# --------------------------------------------------------------------------- DoD-2


def test_both_fields_are_none_with_no_variable_and_no_env_file__S028_001_DoD2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DoD-2 (D2): absent variables plus a disabled env file leave both fields none.

    The autouse isolation sets both variables to `""` — present but blank — so the test
    removes them itself; `_env_file=None` closes the other input.
    """
    monkeypatch.delenv(KEY_ALIAS, raising=False)
    monkeypatch.delenv(ID_ALIAS, raising=False)

    settings = _hermetic_settings()

    assert getattr(settings, KEY_FIELD) is None
    assert getattr(settings, ID_FIELD) is None


# --------------------------------------------------------------------------- DoD-3


def test_neither_repr_nor_str_of_settings_carries_the_key__S028_001_DoD3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DoD-3 (D2, deployment.md redaction rule): the key value renders nowhere on a `Settings`."""
    monkeypatch.setenv(KEY_ALIAS, KEY_VALUE)
    monkeypatch.setenv(ID_ALIAS, ID_VALUE)

    settings = _hermetic_settings()

    # The field is still readable — otherwise the two assertions below could pass vacuously.
    key = getattr(settings, KEY_FIELD)
    assert key is not None
    assert key.get_secret_value() == KEY_VALUE

    assert KEY_VALUE not in repr(settings)
    assert KEY_VALUE not in str(settings)


# --------------------------------------------------------------------------- DoD-4


def test_the_shared_isolation_hides_an_env_file_credential__S028_001_DoD4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DoD-4 (D12): an ordinary test sees an unconfigured instance even with a `.env` holding both.

    The blank variables the autouse fixture exports beat the env file, because
    pydantic-settings reads the environment above `env_file`. `SecretStr("")` is falsy, so
    "non-blank" is the truthiness test. `RPHELPER_DB_FILENAME` is the control: the fixture
    deletes every `RPHELPER_*` variable, so that one *does* come from the env file, which
    proves the file was read and the two credentials were blanked rather than ignored.
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"{KEY_ALIAS}=env-file-key\n{ID_ALIAS}=env-file-cx\nRPHELPER_DB_FILENAME=from-env-file.sqlite\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(env_file.parent)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.db_filename == "from-env-file.sqlite"
    assert not getattr(settings, KEY_FIELD)
    assert not getattr(settings, ID_FIELD)
