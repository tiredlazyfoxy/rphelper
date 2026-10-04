"""The stream request and response models — nothing else (feature `012`, D9, D12).

**Responses.** `MessageResponse` is the wire `Message`: exactly twelve keys (the eight of
012, 022 D3's tool view and 024's `search_coverage_incomplete`). `id` and `session_id` use the
outbound snowflake alias, so each leaves as a **decimal string** (`data-model.md` §
Identifiers). `user_id`, `related_to` and `tool_payload` are never on the wire. Timestamps pass
through as the fixed-width UTC text the row stores.
`EntryListResponse` wraps the settled record under `entries`, `ZoneResponse` the current zone
under `messages`. `SettleResponse` / `ReopenResponse` carry the ids the operation moved
(D11), every one a decimal string, plus the same coverage flag.

Feature `024`, step `005` (Wire contract) adds `search_coverage_incomplete: bool` to those
three responses. It is **required and always present** on the backend wire, and is read off the
service value's attribute of the same name. `StreamMessage` defaults that attribute to false,
so every other route answering a `MessageResponse` — the zone append, the three list reads and
the seeded-session opening message — carries `false` with no handler change. A zone row and a
zone append are always `false`.

**Requests.** `text` in all three bodies is required, a string and **not blank** (D9): one
shared `NonBlankText` type checks it. The value is stored **verbatim** — never trimmed — so
the rule is an `AfterValidator` that returns its input unchanged, not
`StringConstraints(strip_whitespace=True)`. No maximum length (R10). `FilePartnerRequest`'s
`kind` is required and accepts exactly `"partner"` (R11's single exception). Unknown keys are
ignored. `ComposeRequest` (feature `021`) is the one exception to "required": its `text` may
be absent or null (the retry, D2), and is `NonBlankText` when present.

This module imports neither `app.services`, `app.routers`, `app.db` nor `fastapi`.
"""

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict

from app.models.ids import SnowflakeOut


def _require_non_blank(value: str) -> str:
    """Return `value` unchanged when it holds a non-whitespace character; else raise `ValueError`."""
    if not value.strip():
        raise ValueError("text must not be blank")
    return value


#: Message text as the stream routes accept it: non-blank, stored verbatim (D9).
NonBlankText = Annotated[str, AfterValidator(_require_non_blank)]


class MessageResponse(BaseModel):
    """One `messages` row on the wire. Twelve keys: the eight 012 keys, 022 D3's tool view
    `tool_name` / `tool_status` / `tool_args` (null on a non-tool row) and 024's
    `search_coverage_incomplete`. Never `user_id`, `related_to` or `tool_payload`."""

    id: SnowflakeOut
    session_id: SnowflakeOut
    role: str
    kind: str | None
    text: str
    settled_at: str | None
    created_at: str
    updated_at: str
    tool_name: str | None = None
    tool_status: Literal["ok", "failed"] | None = None
    tool_args: dict[str, Any] | None = None
    #: 024 D8 / Wire contract: true only when a record-keeping write could not re-embed this
    #: row's session. Required here; the source `StreamMessage` defaults it to false.
    search_coverage_incomplete: bool


class EntryListResponse(BaseModel):
    """The settled record of one session, under the single `entries` field."""

    entries: list[MessageResponse]


class ZoneResponse(BaseModel):
    """The current zone of one session, under the single `messages` field."""

    messages: list[MessageResponse]


class DiscussionResponse(BaseModel):
    """The buried group of one settled entry (022 D1), under the single `messages` field."""

    messages: list[MessageResponse]


class AppendMessageRequest(BaseModel):
    """The append-to-zone body: one non-blank verbatim `text`."""

    model_config = ConfigDict(extra="ignore")

    text: NonBlankText


class ComposeRequest(BaseModel):
    """The compose body (feature `021`, D1/D2): `text` optional — absent or null is the retry.

    When present, `text` is refused as blank exactly as `AppendMessageRequest` refuses it (422).
    """

    model_config = ConfigDict(extra="ignore")

    text: NonBlankText | None = None


class FilePartnerRequest(BaseModel):
    """The file-partner-block body: `kind` exactly `"partner"` (required) and non-blank `text`."""

    model_config = ConfigDict(extra="ignore")

    kind: Literal["partner"]
    text: NonBlankText


class EditMessageRequest(BaseModel):
    """The PATCH body: one non-blank verbatim `text`."""

    model_config = ConfigDict(extra="ignore")

    text: NonBlankText


class SettleResponse(BaseModel):
    """What settle moved: the head's id, its kind and the ids buried under it (ascending), plus
    024's coverage flag."""

    entry_id: SnowflakeOut
    kind: Literal["turn", "decision"]
    buried_ids: list[SnowflakeOut]
    search_coverage_incomplete: bool


class ReopenResponse(BaseModel):
    """What re-open moved: the head's id and the ids restored to the zone (ascending), plus
    024's coverage flag."""

    reopened_id: SnowflakeOut
    restored_ids: list[SnowflakeOut]
    search_coverage_incomplete: bool
