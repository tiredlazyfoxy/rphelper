"""Tests for ``app.secrets`` — the ``"$ENV_VAR"`` secret-pointer resolver.

Every expected value here comes from ``003.errors-and-secrets.md`` (Definition of done)
and the boundary rulings in ``003.context.md`` § "Boundary rulings for ``resolve_secret``"
and § "Redaction, specifically here". Covers DoD-6 .. DoD-11.

Variables are set and unset through ``monkeypatch`` so pytest restores the process
environment; ``conftest.py``'s autouse fixture only clears ``RPHELPER_*`` names.
"""

import json

import pytest

from app.errors import SecretRefError
from app.secrets import resolve_secret

# A name no fixture and no Settings alias touches.
VARIABLE = "RPHELPER_TEST_SECRET_POINTER"

# A distinctive resolved value for DoD-11: it must never surface in an error.
MARKER_VALUE = "marker-value-a4f19c7b-never-in-an-error"


# --------------------------------------------------------------------------- DoD-6


def test_none_reference_resolves_to_none__DoD6() -> None:
    """DoD-6: ``resolve_secret(None)`` returns ``None``."""
    assert resolve_secret(None) is None


# --------------------------------------------------------------------------- DoD-7


def test_dollar_reference_returns_the_variables_value__DoD7(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-7: ``"$NAME"`` with ``NAME`` set returns that variable's value."""
    monkeypatch.setenv(VARIABLE, "first-value")
    assert resolve_secret(f"${VARIABLE}") == "first-value"


def test_resolution_reads_the_environment_at_call_time__DoD7(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-7: changing the environment between two calls changes the result.

    No re-registration and no cache clear happens in between — resolution is at call time.
    """
    monkeypatch.setenv(VARIABLE, "first-value")
    first = resolve_secret(f"${VARIABLE}")

    monkeypatch.setenv(VARIABLE, "second-value")
    second = resolve_secret(f"${VARIABLE}")

    assert first == "first-value"
    assert second == "second-value"


# --------------------------------------------------------------------------- DoD-8


def test_absent_variable_raises_the_typed_error__DoD8(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-8: ``"$NAME"`` naming an absent variable raises, rather than returning ``None``."""
    monkeypatch.delenv(VARIABLE, raising=False)
    with pytest.raises(SecretRefError):
        resolve_secret(f"${VARIABLE}")


def test_absent_variable_error_detail_names_the_variable__DoD8(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-8: the raised error's ``detail`` names the variable under the frozen ``variable`` key."""
    monkeypatch.delenv(VARIABLE, raising=False)
    with pytest.raises(SecretRefError) as raised:
        resolve_secret(f"${VARIABLE}")
    assert raised.value.detail == {"variable": VARIABLE}


# --------------------------------------------------------------------------- DoD-9


@pytest.mark.parametrize(
    "reference",
    [
        pytest.param("plain-not-a-pointer", id="no-leading-dollar"),
        pytest.param(VARIABLE, id="bare-variable-name-without-dollar"),
        pytest.param("$", id="bare-dollar-naming-nothing"),
    ],
)
def test_malformed_reference_raises_the_typed_error__DoD9(reference: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-9: a non-``$`` reference and a bare ``"$"`` both raise, per 003.context.md."""
    monkeypatch.delenv(VARIABLE, raising=False)
    with pytest.raises(SecretRefError):
        resolve_secret(reference)


def test_non_dollar_reference_raises_even_when_a_variable_of_that_name_exists__DoD9(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DoD-9: a reference without ``$`` raises rather than being returned or looked up."""
    monkeypatch.setenv(VARIABLE, "some-value")
    with pytest.raises(SecretRefError):
        resolve_secret(VARIABLE)


# --------------------------------------------------------------------------- DoD-10


def test_present_but_empty_variable_resolves_to_the_empty_string__DoD10(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-10: present-but-empty is present — the empty string resolves to the empty string."""
    monkeypatch.setenv(VARIABLE, "")
    result = resolve_secret(f"${VARIABLE}")
    assert result == ""
    assert result is not None


# --------------------------------------------------------------------------- DoD-11


@pytest.mark.parametrize(
    "reference",
    [
        pytest.param(VARIABLE, id="no-leading-dollar"),
        pytest.param("$", id="bare-dollar-naming-nothing"),
    ],
)
def test_error_never_carries_a_resolved_secret_value__DoD11(reference: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-11: the variable's value appears nowhere in the raised error — only the name may."""
    monkeypatch.setenv(VARIABLE, MARKER_VALUE)
    with pytest.raises(SecretRefError) as raised:
        resolve_secret(reference)

    error = raised.value
    assert MARKER_VALUE not in json.dumps(error.detail)
    assert MARKER_VALUE not in (error.message or "")
    assert MARKER_VALUE not in str(error)
    assert MARKER_VALUE not in repr(error)
    assert MARKER_VALUE not in json.dumps(error.to_wire())


def test_absent_variable_error_carries_no_other_variables_value__DoD11(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD-11: the failure for an absent variable names the variable and leaks no value."""
    neighbour = f"{VARIABLE}_NEIGHBOUR"
    monkeypatch.setenv(neighbour, MARKER_VALUE)
    monkeypatch.delenv(VARIABLE, raising=False)

    with pytest.raises(SecretRefError) as raised:
        resolve_secret(f"${VARIABLE}")

    error = raised.value
    assert error.detail == {"variable": VARIABLE}
    assert MARKER_VALUE not in json.dumps(error.to_wire())
    assert MARKER_VALUE not in str(error)
