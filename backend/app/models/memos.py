"""The memo request and response models — nothing else (feature `015`, D9, D15).

**Scope.** `MemoScope` names exactly the four levels of R2's chain: `"user"`, `"character"`,
`"setup"`, `"session"`. The same four strings are the `memos.scope` CHECK in `db/schema.py`;
this module never imports `app.db`, so a test pins the two sets equal (D10).

**Responses.** `MemoResponse` is the wire `Memo`: exactly nine keys. `id` uses the outbound
snowflake alias and `scope_id` its nullable form, so each id leaves as a **decimal string**
(`data-model.md` § Identifiers); `scope_id` is `None` for a user-level note. `sort_key` is a
small integer, not an id, and crosses as a JSON number. There is **no `user_id`** — ownership
is a server-side scope (R5). Timestamps pass through as the fixed-width UTC text the row
stores. `MemoListResponse` wraps one level under `memos`; `MemoChainResponse` wraps the chain's
levels under `levels`, each a `MemoChainLevelResponse` of `scope`, `scope_id`, `memos`.

**Requests.** Unknown keys are ignored, so `user_id`, `sort_key` and the two flags cannot be
set through a create body (US-053). `body` must be non-blank and is stored **verbatim** — never
trimmed (D15): the rule is an `AfterValidator` that returns its input unchanged. On create, a
non-user `scope` without a `scope_id` fails validation; a `scope_id` sent with `scope` `"user"`
is accepted and ignored downstream. On update, every field is optional and a key sent as
`null` counts as not supplied (the router forwards only set, non-`None` fields).

This module imports neither `app.services`, `app.routers`, `app.db` nor `fastapi`.
"""

from typing import Annotated, Any, Literal, Self

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, model_validator

from app.models.ids import SnowflakeIn, SnowflakeOut

#: The four memo levels, in chain order (R2).
MemoScope = Literal["user", "character", "setup", "session"]


def _require_non_blank_body(value: str) -> str:
    """Return `value` unchanged when it holds a non-whitespace character; else raise `ValueError`."""
    if not value.strip():
        raise ValueError("A note must not be blank.")
    return value


#: A memo body as the routes accept it: non-blank, stored verbatim (D15).
NonBlankBody = Annotated[str, AfterValidator(_require_non_blank_body)]


def _parse_optional_scope_id(value: Any) -> int | None:
    """`None` passes through; anything else goes through `int()`; a `TypeError` becomes a `ValueError`."""
    if value is None:
        return None
    try:
        return int(value)
    except TypeError as exc:
        # pydantic v2 lets a `TypeError` escape as a 500; a `ValueError` becomes a 422.
        raise ValueError("A scope id must be a decimal string.") from exc


#: A nullable inbound snowflake for `scope_id`: JSON `null` and an absent field give `None`, a
#: decimal string gives the `int`, anything else is a validation error (422).
OptionalScopeIdIn = Annotated[int | None, BeforeValidator(_parse_optional_scope_id)]


class MemoResponse(BaseModel):
    """One `memos` row on the wire. Nine keys, never `user_id`."""

    id: SnowflakeOut
    scope: MemoScope
    scope_id: SnowflakeOut | None
    body: str
    is_enabled: bool
    is_forced: bool
    sort_key: int
    created_at: str
    updated_at: str


class MemoListResponse(BaseModel):
    """One level's notes, under the single `memos` field, in the order the service gave."""

    memos: list[MemoResponse]


class MemoChainLevelResponse(BaseModel):
    """One level of a session's chain: its scope, its id (`None` for the user level), its notes."""

    scope: MemoScope
    scope_id: SnowflakeOut | None
    memos: list[MemoResponse]


class MemoChainResponse(BaseModel):
    """A session's chain, under the single `levels` field, in the fixed order user → session."""

    levels: list[MemoChainLevelResponse]


class CreateMemoRequest(BaseModel):
    """The create body: `scope`, an optional nullable `scope_id`, a non-blank `body`."""

    model_config = ConfigDict(extra="ignore")

    scope: MemoScope
    scope_id: OptionalScopeIdIn = None
    body: NonBlankBody

    @model_validator(mode="after")
    def _require_scope_id_for_non_user_scope(self) -> Self:
        """A non-user `scope` without a `scope_id` raises `ValueError` (422)."""
        if self.scope != "user" and self.scope_id is None:
            raise ValueError(f"A {self.scope} note needs a scope_id.")
        return self


class ReorderMemosRequest(BaseModel):
    """The level-reorder body (feature `016`, D6): `scope`, an optional nullable `scope_id`,
    and `memo_ids`, the level's whole order. Unknown keys are ignored."""

    model_config = ConfigDict(extra="ignore")

    scope: MemoScope
    scope_id: OptionalScopeIdIn = None
    memo_ids: list[SnowflakeIn]

    @model_validator(mode="after")
    def _require_scope_id_for_non_user_scope(self) -> Self:
        """A non-user `scope` without a `scope_id` raises `ValueError` (422)."""
        if self.scope != "user" and self.scope_id is None:
            raise ValueError(f"A {self.scope} reorder needs a scope_id.")
        return self


class UpdateMemoRequest(BaseModel):
    """The update body: any subset of `body`, `is_enabled`, `is_forced`. Unknown keys are ignored."""

    model_config = ConfigDict(extra="ignore")

    body: NonBlankBody | None = None
    is_enabled: bool | None = None
    is_forced: bool | None = None
