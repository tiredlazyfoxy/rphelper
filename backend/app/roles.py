"""The role vocabulary — the two values the `users.role` column may hold.

A leaf module (decision D7 of `003.first-run-bootstrap`): `db/schema.py`, `services/`,
`models/` and later the router dependency all need these names, and a top-level leaf keeps
`db/` from importing `models/`. It holds the enum and nothing else — the ladder and
`require_role` belong to feature `004`.

The member *values* are exactly the strings `data-model.md` stores in the column.
"""

from enum import StrEnum


class Role(StrEnum):
    """A user's role. `ADMIN` is the role the first-run account is created with (UC-001)."""

    ROLEPLAYER = "roleplayer"
    ADMIN = "admin"
