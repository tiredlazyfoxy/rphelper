"""The write-time half of the `"$ENV_VAR"` secret-pointer pattern.

`docs/architecture/backend-structure.md` § the secret-pointer pattern: a stored
`api_key_ref` is a **pointer** (`"$NAME"`), never a credential. `app/secrets.py` resolves
a pointer at call time; this module decides, at the wire boundary, what a request body may
carry (feature `006`, `context.md` D8). It mirrors `models/ids.py` as the home for an
annotated boundary type and does not import from `app/secrets.py`.

Valid values: the empty string (no pointer on create, "clear" on update — D9), or `$`
followed by at least one character. Everything else — a raw key, a bare `$`, anything
before the `$` — is invalid. Values are never trimmed, case-folded or normalised.

`SecretRefIn` applies the predicate as a field validator, so an invalid value is a pydantic
validation error (FastAPI's 422) and never a `DomainError`.
"""

from typing import Annotated

from pydantic import AfterValidator


def is_valid_secret_ref(value: str) -> bool:
    """True for `""` or `"$"` plus at least one character; False for everything else."""
    return value == "" or (len(value) >= 2 and value.startswith("$"))


def _validate_secret_ref(value: str) -> str:
    """Return `value` unchanged when `is_valid_secret_ref` accepts it; else raise `ValueError`."""
    if not is_valid_secret_ref(value):
        raise ValueError('must be empty or a "$ENV_VAR" pointer: "$" followed by a variable name')
    return value


SecretRefIn = Annotated[str, AfterValidator(_validate_secret_ref)]
