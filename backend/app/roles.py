"""The role vocabulary — the two values the `users.role` column may hold.

A leaf module (decision D7 of `003.first-run-bootstrap`): `db/schema.py`, `services/`,
`models/` and the router dependencies all need these names, and a top-level leaf keeps
`db/` from importing `models/`. It holds the enum, the numeric ladder `domain-rules.md`
states, and one pure "at least this rung" comparison — pure data and pure logic only.
Feature `004` (D8): no `fastapi` import, no `Request`, no dependency lives here, because
`db/schema.py` imports this module; `require_role` lives in `app/dependencies.py`.

The member *values* are exactly the strings `data-model.md` stores in the column.
"""

from enum import StrEnum


class Role(StrEnum):
    """A user's role. `ADMIN` is the role the first-run account is created with (UC-001)."""

    ROLEPLAYER = "roleplayer"
    ADMIN = "admin"


#: The role ladder `domain-rules.md` states: a higher rung includes every lower one. It
#: covers **every** member of `Role`, so a rung added later without an entry fails rather
#: than silently ranking as zero.
ROLE_LADDER: dict[Role, int] = {Role.ROLEPLAYER: 0, Role.ADMIN: 1}


def role_at_least(role: Role, min_role: Role) -> bool:
    """Return whether `role` sits at or above `min_role` on `ROLE_LADDER`."""
    return ROLE_LADDER[role] >= ROLE_LADDER[min_role]
