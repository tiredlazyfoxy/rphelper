"""Resolution of the `"$ENV_VAR"` pointer stored in place of a credential.

`docs/architecture/backend-structure.md` § the `"$ENV_VAR"` secret-pointer pattern: an
LLM server's credential is never stored in the database — the column holds the literal
string `"$OPENAI_API_KEY"`, resolved from the process environment **at call time**, not
at import, not at registration and not at startup, so rotating a key is an environment
change plus a restart. Nothing here caches.

A reference naming an absent variable raises `app.errors.SecretRefError` rather than
returning a `None` that would turn into an unauthenticated provider call. A reference
that does not start with `$`, and a bare `"$"` naming nothing, raise the same error;
rejecting a non-`$` value *on write* is a different mechanism and belongs to feature
`006`. A variable set to the empty string resolves to the empty string —
present-but-empty is present.

The failure names the **variable**, never the resolved value (`deployment.md`'s
redaction rule).
"""

import os

from app.errors import SecretRefError


def resolve_secret(ref: str | None) -> str | None:
    """'$NAME' -> os.environ['NAME']; None -> None; anything else -> SecretRefError."""
    if ref is None:
        return None
    # A bare "$" names no variable, and a value not starting with "$" is not a pointer at
    # all; both are malformed rather than absent. Neither the message nor the `detail`
    # echoes `ref` here — a non-pointer reference may itself be a pasted raw credential.
    if not ref.startswith("$") or ref == "$":
        raise SecretRefError("secret reference is malformed: expected the form '$NAME'")
    name = ref[1:]
    # Read at call time, never at import: rotating a key is an environment change plus a
    # restart. `.get` rather than a truth test, so a variable set to the empty string
    # resolves to the empty string — present-but-empty is present.
    value = os.environ.get(name)
    if value is None:
        raise SecretRefError(
            f"environment variable {name} is not set",
            detail={"variable": name},
        )
    return value
