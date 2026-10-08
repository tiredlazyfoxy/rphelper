"""The password-hashing seam — a service by construction (decision D1 of `003`).

Argon2id via `argon2-cffi`, with the library's own current default parameters: this module
names no cost, memory or parallelism literal. The stored value is the library's
self-describing encoded string, so the parameters live inside the hash.

Imports no `fastapi`, opens no connection, reads no settings, logs nothing, and offers no
rehash-on-verify affordance.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

#: The one hasher, constructed with the library's defaults (Argon2id).
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a plaintext password into an Argon2id encoded string (`$argon2id$v=19$m=...`)."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Return whether `password` matches `password_hash`.

    Answers False, never raises, for a wrong password and for a value that is not a valid
    encoded hash.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False
