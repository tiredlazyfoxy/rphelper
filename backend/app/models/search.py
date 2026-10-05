"""My-search's response models — the five groups on the wire and nothing else (feature `029`, `003`).

`context.md`'s wire contract for `GET /api/search` is one object with **five keys in UC-059's
order** — `characters`, `setups`, `sessions`, `entries`, `memos` — each a list that may be empty.
`MySearchResponse` declares them in exactly that order, because a JSON object's key order is its
declaration order and US-075.AC-1 is read off the body (step `003` DoD-2).

One model per kind, each holding **exactly** the contract's keys and nothing convenient on top
(DoD-3): a note is a snippet plus a level and never a title (US-119), a session has no title column
at all, and no model here carries `title`, `body`, `is_forced`, a score, a `user_id` or a paging
cursor. Every id field uses the outbound snowflake alias, so each id leaves as a **decimal string**
(`backend-structure.md` § The JSON id boundary); the nullable ones are spelled
`SnowflakeOut | None`. Timestamps pass through as the fixed-width UTC text the row stores, exactly
as `SessionResponse.created_at` does. `archived` and `is_enabled` are plain booleans: an archived
character, setup or session is **returned and flagged** (U3), and a note's `is_enabled` is reported,
never applied as a filter (US-137.AC-1, US-137.AC-2).

Each model's field order is its kind's hit dataclass's field order in
`app.services.search.my_search`, so one hit converts field-for-field through
`model_validate(hit, from_attributes=True)` — the house form, declared at the call site rather than
through a `model_config` here (`models/memos.py`'s `MemoResponse`). The grouped payload follows the
`MemoChainResponse` precedent: the **outer** model is built by keyword from already-converted leaf
rows. That conversion lives in `app.routers.search` (`_to_response`), not here, because the
dependency direction is one-way — `models/` is imported by routers and services and imports
neither (`backend-structure.md` § Routers versus services).

This module imports neither `app.services`, `app.routers`, `app.db` nor `fastapi`.
"""

from pydantic import BaseModel

from app.models.ids import SnowflakeOut
from app.models.memos import MemoScope


class CharacterHitResponse(BaseModel):
    """One matched character on the wire: exactly `id`, `name`, `archived`."""

    id: SnowflakeOut
    name: str
    archived: bool


class SetupHitResponse(BaseModel):
    """One matched setup: exactly `id`, `name`, `character_id`, `character_name`, `archived`.

    Setups have no route of their own, so the owning character travels with the row (U4);
    `archived` is the setup's own flag, never its character's.
    """

    id: SnowflakeOut
    name: str
    character_id: SnowflakeOut
    character_name: str
    archived: bool


class SessionHitResponse(BaseModel):
    """One matched session: exactly `id`, `character_name`, `setup_name`, `created_at`, `archived`.

    `setup_name` is `null` for a session started without a setup; `created_at` is the stored text.
    """

    id: SnowflakeOut
    character_name: str
    setup_name: str | None
    created_at: str
    archived: bool


class EntryHitResponse(BaseModel):
    """One matched settled entry: exactly `id`, `session_id`, `snippet`, `character_name`,
    `session_created_at`.

    `id` is the **message** id — the `entry=` landing param's value (D8) — and
    `session_created_at` is the owning session's `created_at`, not the message's own timestamp.
    """

    id: SnowflakeOut
    session_id: SnowflakeOut
    snippet: str
    character_name: str
    session_created_at: str


class MemoHitResponse(BaseModel):
    """One matched note: exactly `id`, `scope`, `scope_id`, `character_id`, `snippet`, `is_enabled`.

    `scope` is the shared four-level alias. `scope_id` is `null` at the `"user"` level and the
    level's id otherwise; `character_id` is the character page the row links to — `scope_id` at
    `"character"`, the setup's character at `"setup"`, `null` at `"user"` and `"session"` (U4).
    There is no title and no forced flag: the row is a snippet plus a level (US-119, R3).
    """

    id: SnowflakeOut
    scope: MemoScope
    scope_id: SnowflakeOut | None
    character_id: SnowflakeOut | None
    snippet: str
    is_enabled: bool


class MySearchResponse(BaseModel):
    """One whole my-search answer: the five groups, **in UC-059's order**, each possibly empty.

    The declaration order of these five fields **is** the wire contract (US-075.AC-1, DoD-2):
    `characters`, `setups`, `sessions`, `entries`, `memos`. All five keys are always present — a
    blank query answers five empty lists with a 200 (D1) — and there is no total, no cursor and no
    per-group "has more" flag. A failure in any arm answers the error envelope instead, never a
    partially filled one of these (U1).
    """

    characters: list[CharacterHitResponse]
    setups: list[SetupHitResponse]
    sessions: list[SessionHitResponse]
    entries: list[EntryHitResponse]
    memos: list[MemoHitResponse]
