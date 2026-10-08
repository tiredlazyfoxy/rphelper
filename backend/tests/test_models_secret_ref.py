"""Tests for ``app.models.secret_ref`` — the write-time half of the ``"$ENV_VAR"`` pattern.

Feature 006, step 001 (``001.tables-errors-and-secret-ref.md``). Every expected value here
comes from that step's Interface intent and DoD-11 .. DoD-13, ``001.context.md``
("The empty-string case"), and feature 006 ``context.md`` D8 / D9:

- the empty string is valid ("no pointer" / "clear the stored pointer");
- ``$`` followed by at least one character is valid;
- everything else — a raw key, a bare ``$``, anything before the ``$`` — is invalid;
- nothing is trimmed, case-folded or otherwise altered;
- a request model using the annotated alias answers a pydantic validation error (FastAPI's
  own 422), never a ``DomainError``;
- ``app/secrets.py`` is unchanged and is not imported at module scope for the predicate.

Tests are suffixed ``__S006_001_DoD<n>``.
"""

import ast
import importlib
import inspect
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

import app.models.secret_ref as secret_ref_module
from app.errors import DomainError, SecretRefError
from app.models.secret_ref import SecretRefIn, is_valid_secret_ref
from app.secrets import resolve_secret

VALID_POINTERS = [
    "",
    "$A",
    "$x",
    "$1",
    "$OPENAI_API_KEY",
    "$openai_api_key",
    "$Mixed_Case_Name",
    "$KEY ",
    "$ KEY",
    "$$",
    "$a-b.c",
]

INVALID_POINTERS = [
    "sk-abc123def456",
    "OPENAI_API_KEY",
    "$",
    " $KEY",
    "\t$KEY",
    "\n$KEY",
    "a$KEY",
    "KEY$",
    " ",
    "  ",
    "Bearer $KEY",
]


class PointerBody(BaseModel):
    """A request model whose pointer field uses the annotated alias."""

    api_key_ref: SecretRefIn


# --------------------------------------------------------------------------- DoD-11


@pytest.mark.parametrize("value", VALID_POINTERS)
def test_predicate_accepts_empty_or_dollar_followed_by_a_character__S006_001_DoD11(value: str) -> None:
    """006/001 DoD-11: the empty string and ``$`` + at least one character are valid."""
    assert is_valid_secret_ref(value) is True


@pytest.mark.parametrize("value", INVALID_POINTERS)
def test_predicate_rejects_raw_keys_bare_dollar_and_leading_text__S006_001_DoD11(value: str) -> None:
    """006/001 DoD-11: a raw key, a bare ``$`` and anything before the ``$`` are invalid."""
    assert is_valid_secret_ref(value) is False


def test_predicate_accepts_the_empty_string__S006_001_DoD11() -> None:
    """006/001 DoD-11: the empty string — "no pointer" / "clear" (D9) — is valid, not a fallback."""
    assert is_valid_secret_ref("") is True


def test_predicate_rejects_a_bare_dollar__S006_001_DoD11() -> None:
    """006/001 DoD-11: ``$`` with nothing after it is not a pointer."""
    assert is_valid_secret_ref("$") is False


def test_predicate_does_not_trim_leading_whitespace__S006_001_DoD11() -> None:
    """006/001 DoD-11: leading whitespace before the ``$`` is not trimmed away into validity."""
    assert is_valid_secret_ref(" $KEY") is False
    assert is_valid_secret_ref("$KEY") is True


def test_predicate_is_usable_with_no_pydantic_model__S006_001_DoD11() -> None:
    """006/001 DoD-11: the predicate is a plain callable over a string returning a bool."""
    assert callable(is_valid_secret_ref)
    assert isinstance(is_valid_secret_ref("$KEY"), bool)
    assert isinstance(is_valid_secret_ref("raw"), bool)


@pytest.mark.parametrize("value", VALID_POINTERS)
def test_valid_pointer_is_stored_exactly_as_received__S006_001_DoD11(value: str) -> None:
    """006/001 DoD-11: no trimming, no case folding, no normalisation — the value is kept verbatim."""
    body = PointerBody(api_key_ref=value)
    assert body.api_key_ref == value
    assert len(body.api_key_ref) == len(value)


def test_trailing_whitespace_and_case_survive_unaltered__S006_001_DoD11() -> None:
    """006/001 DoD-11: ``"$My_Key "`` keeps both its case and its trailing space."""
    assert PointerBody(api_key_ref="$My_Key ").api_key_ref == "$My_Key "
    assert PointerBody.model_validate({"api_key_ref": "$lower"}).api_key_ref == "$lower"


# --------------------------------------------------------------------------- DoD-12


@pytest.mark.parametrize("value", INVALID_POINTERS)
def test_model_rejects_an_invalid_pointer_with_a_validation_error__S006_001_DoD12(value: str) -> None:
    """006/001 DoD-12: a pydantic model using the alias raises ``ValidationError`` for a bad pointer."""
    with pytest.raises(ValidationError):
        PointerBody(api_key_ref=value)


@pytest.mark.parametrize("value", INVALID_POINTERS)
def test_invalid_pointer_does_not_raise_a_domain_error__S006_001_DoD12(value: str) -> None:
    """006/001 DoD-12: the rejection is a validation error, never a ``DomainError``."""
    try:
        PointerBody(api_key_ref=value)
    except DomainError:  # pragma: no cover - the failure this test exists to catch
        pytest.fail("an invalid pointer raised a DomainError instead of a validation error")
    except ValidationError as error:
        assert not isinstance(error, DomainError)
        assert len(error.errors()) >= 1
        assert all(item["loc"][0] == "api_key_ref" for item in error.errors())
    else:  # pragma: no cover - the failure this test exists to catch
        pytest.fail("an invalid pointer was accepted")


def test_model_accepts_the_empty_string__S006_001_DoD12() -> None:
    """006/001 DoD-12: the empty string — the "clear" state of D9 — is accepted as ``""``."""
    body = PointerBody(api_key_ref="")
    assert body.api_key_ref == ""
    assert PointerBody.model_validate({"api_key_ref": ""}).api_key_ref == ""


def test_model_accepts_a_valid_pointer_from_a_json_body__S006_001_DoD12() -> None:
    """006/001 DoD-12: validation from JSON behaves like construction."""
    body = PointerBody.model_validate_json('{"api_key_ref": "$OPENAI_API_KEY"}')
    assert body.api_key_ref == "$OPENAI_API_KEY"


def _pointer_app() -> FastAPI:
    app = FastAPI()

    @app.post("/pointer")
    def accept(body: PointerBody) -> dict[str, str]:
        return {"api_key_ref": body.api_key_ref}

    return app


@pytest.mark.parametrize("value", ["sk-abc123def456", "$", " $KEY"])
def test_request_with_an_invalid_pointer_answers_fastapis_422__S006_001_DoD12(value: str) -> None:
    """006/001 DoD-12 (D8): a request body using the alias answers FastAPI's own 422, no domain code."""
    response = TestClient(_pointer_app()).post("/pointer", json={"api_key_ref": value})
    assert response.status_code == 422
    payload = response.json()
    assert "error" not in payload
    assert "detail" in payload


@pytest.mark.parametrize("value", ["", "$OPENAI_API_KEY"])
def test_request_with_a_valid_pointer_is_accepted_verbatim__S006_001_DoD12(value: str) -> None:
    """006/001 DoD-12: an empty string or a ``$NAME`` pointer passes through the route unaltered."""
    response = TestClient(_pointer_app()).post("/pointer", json={"api_key_ref": value})
    assert response.status_code == 200
    assert response.json() == {"api_key_ref": value}


# --------------------------------------------------------------------------- DoD-13


def test_resolve_secret_maps_a_dollar_name_to_the_environment_variable__S006_001_DoD13(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """006/001 DoD-13: ``resolve_secret('$NAME')`` still returns the variable's value."""
    monkeypatch.setenv("S006_TEST_PROVIDER_KEY", "the-resolved-credential")
    assert resolve_secret("$S006_TEST_PROVIDER_KEY") == "the-resolved-credential"


def test_resolve_secret_maps_none_to_none__S006_001_DoD13() -> None:
    """006/001 DoD-13: ``resolve_secret(None)`` is still ``None``."""
    assert resolve_secret(None) is None


@pytest.mark.parametrize("value", ["sk-abc123def456", "OPENAI_API_KEY", "$", " $KEY"])
def test_resolve_secret_rejects_anything_else_as_secret_ref_missing__S006_001_DoD13(value: str) -> None:
    """006/001 DoD-13: any other value still raises the ``secret_ref_missing`` error."""
    with pytest.raises(SecretRefError) as caught:
        resolve_secret(value)
    assert caught.value.code == "secret_ref_missing"


def test_resolve_secret_is_still_defined_in_app_secrets__S006_001_DoD13() -> None:
    """006/001 DoD-13: ``resolve_secret`` still lives in ``app.secrets``, not in the new module."""
    assert resolve_secret.__module__ == "app.secrets"
    assert is_valid_secret_ref.__module__ == "app.models.secret_ref"
    assert is_valid_secret_ref is not resolve_secret


def _module_scope_imports(tree: ast.Module) -> list[str]:
    """Every module name imported by a top-level statement of the parsed module."""
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            names.append(base)
            names.extend(f"{base.rstrip('.')}.{alias.name}" if node.module else f"{base}{alias.name}"
                         for alias in node.names)
    return names


def _names_app_secrets(name: str) -> bool:
    """True when an imported name refers to ``app.secrets`` (absolute, or relative from ``app.models``)."""
    if name == "app.secrets" or name.startswith("app.secrets."):
        return True
    # From inside ``app.models``, ``..secrets`` (and ``..`` + ``secrets``) is ``app.secrets``.
    return name == "..secrets" or name.startswith("..secrets.")


def test_new_module_does_not_import_app_secrets_at_module_scope__S006_001_DoD13() -> None:
    """006/001 DoD-13: ``app/models/secret_ref.py`` imports nothing from ``app.secrets`` at module scope."""
    source_file = inspect.getsourcefile(secret_ref_module)
    assert source_file is not None
    tree = ast.parse(Path(source_file).read_text(encoding="utf-8"))
    imported = _module_scope_imports(tree)
    assert not [name for name in imported if _names_app_secrets(name)]


def test_new_module_binds_nothing_from_app_secrets__S006_001_DoD13() -> None:
    """006/001 DoD-13: no name in the new module is ``app.secrets`` or one of its functions."""
    secrets_module = importlib.import_module("app.secrets")
    for name, value in vars(secret_ref_module).items():
        if name.startswith("__"):
            continue
        assert value is not secrets_module, name
        assert value is not resolve_secret, name
