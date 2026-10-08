"""Feature 003, step 001 — the password-hashing seam (`app/services/passwords.py`).

Covers 003/001 DoD-5 (Argon2id encoded string, per-hash salt), DoD-6 (verify: true for
the right password, false for a wrong one, false rather than raising for a non-hash) and
DoD-8 (no FastAPI, no connection, no settings: two plain strings are enough).
"""

import inspect
import types

import pytest

from app.services import passwords
from app.services.passwords import hash_password, verify_password

PASSWORD = "correct horse battery staple"
OTHER_PASSWORD = "Tr0ub4dor&3"


# --- DoD-5: the hash operation --------------------------------------------------------


def test_hash_returns_a_string__DoD5() -> None:
    """003/001 DoD-5 — the hash operation returns the encoded form as a `str`."""
    encoded = hash_password(PASSWORD)
    assert isinstance(encoded, str)


def test_hash_is_an_argon2id_encoded_string__DoD5() -> None:
    """003/001 DoD-5 — the self-describing prefix names the Argon2**id** variant."""
    encoded = hash_password(PASSWORD)
    assert encoded.startswith("$argon2id$")


def test_hash_does_not_contain_the_plaintext__DoD5() -> None:
    """003/001 DoD-5 — the encoded string is a hash, never the password itself."""
    encoded = hash_password(PASSWORD)
    assert PASSWORD not in encoded


def test_two_hashes_of_the_same_password_differ__DoD5() -> None:
    """003/001 DoD-5 — a per-hash salt is in use: same input, different outputs."""
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)
    assert first.startswith("$argon2id$")
    assert second.startswith("$argon2id$")
    assert first != second


# --- DoD-6: the verification operation ------------------------------------------------


def test_verify_accepts_the_password_that_produced_the_hash__DoD6() -> None:
    """003/001 DoD-6 — the matching password verifies as `True`."""
    encoded = hash_password(PASSWORD)
    assert verify_password(encoded, PASSWORD) is True


def test_verify_accepts_each_of_two_distinct_hashes_of_the_same_password__DoD6() -> None:
    """003/001 DoD-6 — salted hashes differ, yet each verifies its own password."""
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)
    assert verify_password(first, PASSWORD) is True
    assert verify_password(second, PASSWORD) is True


@pytest.mark.parametrize(
    "candidate",
    [
        OTHER_PASSWORD,
        "",
        PASSWORD.upper(),
        PASSWORD + " ",
        PASSWORD[:-1],
    ],
)
def test_verify_rejects_any_other_password__DoD6(candidate: str) -> None:
    """003/001 DoD-6 — any other password answers `False`, not an exception."""
    encoded = hash_password(PASSWORD)
    assert verify_password(encoded, candidate) is False


@pytest.mark.parametrize(
    "not_a_hash",
    [
        "",
        "not-a-hash",
        PASSWORD,
        "$argon2id$",
        "$argon2id$v=19$m=garbage",
        "$2b$12$abcdefghijklmnopqrstuuABCDEFGHIJKLMNOPQRSTUVWXYZ01234",
    ],
)
def test_verify_answers_false_rather_than_raising_for_a_non_hash__DoD6(not_a_hash: str) -> None:
    """003/001 DoD-6 — a value that is not a valid encoded hash yields `False`, no raise."""
    assert verify_password(not_a_hash, PASSWORD) is False


def test_verify_answers_false_for_a_corrupted_hash__DoD6() -> None:
    """003/001 DoD-6 — a truncated encoded hash is not valid: `False`, no raise."""
    encoded = hash_password(PASSWORD)
    truncated = encoded[: len(encoded) // 2]
    assert verify_password(truncated, PASSWORD) is False


# --- DoD-8: FastAPI-free, connection-free, settings-free ------------------------------


def test_hash_takes_exactly_one_plain_string__DoD8() -> None:
    """003/001 DoD-8 — the hash operation's only parameter is the plaintext password."""
    parameters = list(inspect.signature(hash_password).parameters.values())
    assert [parameter.name for parameter in parameters] == ["password"]
    assert all(parameter.annotation in (str, "str") for parameter in parameters)


def test_verify_takes_exactly_two_plain_strings__DoD8() -> None:
    """003/001 DoD-8 — verification takes the encoded hash and the candidate, nothing else."""
    parameters = list(inspect.signature(verify_password).parameters.values())
    assert [parameter.name for parameter in parameters] == ["password_hash", "password"]
    assert all(parameter.annotation in (str, "str") for parameter in parameters)


def test_operations_are_callable_with_plain_strings_and_nothing_else__DoD8() -> None:
    """003/001 DoD-8 — no connection, no settings object, no application is needed."""
    encoded = hash_password(PASSWORD)
    assert verify_password(encoded, PASSWORD) is True


def test_signatures_name_no_fastapi_connection_or_settings_type__DoD8() -> None:
    """003/001 DoD-8 — neither contract mentions FastAPI, a connection or settings."""
    for operation in (hash_password, verify_password):
        signature = inspect.signature(operation)
        rendered = " ".join(str(parameter.annotation) for parameter in signature.parameters.values())
        rendered = f"{rendered} {signature.return_annotation}".lower()
        assert "fastapi" not in rendered
        assert "starlette" not in rendered
        assert "connection" not in rendered
        assert "engine" not in rendered
        assert "settings" not in rendered


def _module_origin(value: object) -> str:
    if isinstance(value, types.ModuleType):
        return value.__name__
    return str(getattr(value, "__module__", "") or "")


def test_module_imports_no_fastapi_symbol__DoD8() -> None:
    """003/001 DoD-8 — nothing bound in the module comes from `fastapi` or `starlette`."""
    origins = {name: _module_origin(value) for name, value in vars(passwords).items()}
    offending = {
        name: origin
        for name, origin in origins.items()
        if origin.split(".")[0] in {"fastapi", "starlette"}
    }
    assert offending == {}


def test_module_binds_no_settings_or_database_access__DoD8() -> None:
    """003/001 DoD-8 — the module reaches for neither the settings nor the database layer."""
    origins = {name: _module_origin(value) for name, value in vars(passwords).items()}
    offending = {
        name: origin
        for name, origin in origins.items()
        if origin in {"app.config", "app.db.engine", "app.db"}
        or origin.startswith("app.db.")
        or origin.split(".")[0] == "sqlalchemy"
    }
    assert offending == {}
    assert "get_settings" not in vars(passwords)
    assert "Settings" not in vars(passwords)
    assert "get_engine" not in vars(passwords)
    assert "get_connection" not in vars(passwords)
