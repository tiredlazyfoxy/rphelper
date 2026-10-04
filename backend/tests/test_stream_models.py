"""Feature 012, step 001 — the five new domain errors and `app/models/stream.py`.

Expected values come from `docs/plans/012.messages-and-settle/001.table-selectables-errors-models.md`
(DoD-7..11) and feature 012's `context.md`: the **Wire contract** (`Message` on the wire —
exactly eight keys, every id a decimal string, never `user_id` / `related_to` / the tool
columns), **D13** (the five codes and their statuses, a fixed non-empty default message,
an empty `detail`), **D9** (request `text` required, non-blank, stored verbatim, no maximum
length; unknown keys ignored) and R11's single exception (the entries POST's `kind` is
exactly `"partner"`). Tests are suffixed `__S012_001_DoD<n>`.

`test_errors.py` is not this step's file, so the error classes' own coverage lives here
alongside the models they answer for, exactly as 009, 010 and 011 placed theirs.
"""

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.errors import (
    DomainError,
    MessageNotEditableError,
    MessageNotFoundError,
    NothingToReopenError,
    ZoneEmptyError,
    ZoneNotEmptyError,
    register_exception_handlers,
)
from app.models.stream import (
    AppendMessageRequest,
    EditMessageRequest,
    EntryListResponse,
    FilePartnerRequest,
    MessageResponse,
    ReopenResponse,
    SettleResponse,
    ZoneResponse,
)

# context.md: the fixed-width timestamp form, passed through as text.
CREATED_AT = "2026-09-29T12:00:00.000000+00:00"
UPDATED_AT = "2026-09-30T08:15:30.123456+00:00"
SETTLED_AT = "2026-09-30T08:15:30.123456+00:00"

# context.md "Wire contract" — `Message` on the wire had exactly these eight keys.
# Amended by feature 022, step 001 (D3, DoD-4): the eight plus `tool_name`, `tool_status`
# and `tool_args` — eleven keys; `tool_payload` (and `call_id`) never reach the wire.
MESSAGE_WIRE_KEYS = {
    "id",
    "session_id",
    "role",
    "kind",
    "text",
    "settled_at",
    "created_at",
    "updated_at",
    "tool_name",
    "tool_status",
    "tool_args",
}
NEVER_ON_THE_WIRE = ("user_id", "related_to", "tool_payload", "call_id")

# The error envelope `errors.py` renders: one `error` key over exactly three.
ENVELOPE_KEYS = {"error"}
ERROR_KEYS = {"code", "message", "detail"}

# D13 — (class, code, status).
NEW_ERRORS: list[tuple[type[DomainError], str, int]] = [
    (ZoneEmptyError, "zone_empty", 409),
    (ZoneNotEmptyError, "zone_not_empty", 409),
    (NothingToReopenError, "nothing_to_reopen", 409),
    (MessageNotEditableError, "message_not_editable", 409),
    (MessageNotFoundError, "message_not_found", 404),
]
NEW_ERROR_IDS = [code for _, code, _ in NEW_ERRORS]

# D9 — blank bodies the boundary refuses (each must fail validation).
BLANK_TEXT_BODIES: list[dict[str, Any]] = [
    {},
    {"text": ""},
    {"text": "   \n\t"},
    {"text": None},
]
BLANK_TEXT_IDS = ["absent", "empty", "whitespace", "null"]

TEXT_REQUEST_MODELS: list[type[BaseModel]] = [AppendMessageRequest, EditMessageRequest]
TEXT_REQUEST_IDS = ["append", "edit"]


def _app_raising(exc: BaseException) -> FastAPI:
    """A throwaway application with the handlers registered and one route that raises ``exc``."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise exc

    return app


def _wire(model: BaseModel) -> Any:
    """What the model actually serialises to on the wire."""
    return json.loads(model.model_dump_json())


def _message(**overrides: Any) -> MessageResponse:
    values: dict[str, Any] = {
        "id": 7_205_759_403_792_793_600,
        "session_id": 7_205_759_403_792_793_601,
        "role": "user",
        "kind": "turn",
        "text": "She leans on the rail.",
        "settled_at": SETTLED_AT,
        "created_at": CREATED_AT,
        "updated_at": UPDATED_AT,
    }
    values.update(overrides)
    return MessageResponse(**values)


# ====================================================================== DoD-7
# The five new errors (D13): each a `DomainError` with its class-level code and status, a
# fixed non-empty default message and an empty `detail`, rendered in the wire envelope.


@pytest.mark.parametrize(("error_class", "code", "status"), NEW_ERRORS, ids=NEW_ERROR_IDS)
def test_each_new_error_is_a_domain_error_subclass__S012_001_DoD7(
    error_class: type[DomainError], code: str, status: int
) -> None:
    """012/001 DoD-7 — each error follows the base's pattern as a subclass."""
    assert issubclass(error_class, DomainError)
    assert isinstance(error_class(), Exception)


@pytest.mark.parametrize(("error_class", "code", "status"), NEW_ERRORS, ids=NEW_ERROR_IDS)
def test_each_new_error_sets_code_and_status_as_class_attributes__S012_001_DoD7(
    error_class: type[DomainError], code: str, status: int
) -> None:
    """012/001 DoD-7 — D13: the code and status are set on the subclass itself."""
    assert "code" in vars(error_class)
    assert "http_status" in vars(error_class)
    assert error_class.code == code
    assert error_class.http_status == status
    error = error_class()
    assert error.code == code
    assert error.http_status == status


@pytest.mark.parametrize(("error_class", "code", "status"), NEW_ERRORS, ids=NEW_ERROR_IDS)
def test_each_new_error_carries_a_default_message_and_an_empty_detail__S012_001_DoD7(
    error_class: type[DomainError], code: str, status: int
) -> None:
    """012/001 DoD-7 — D13: constructed with no arguments, the message is a non-empty string
    and `detail` is empty."""
    error = error_class()
    assert isinstance(error.message, str)
    assert error.message != ""
    assert error.detail == {}


@pytest.mark.parametrize(("error_class", "code", "status"), NEW_ERRORS, ids=NEW_ERROR_IDS)
def test_each_new_error_from_a_route_answers_its_status_in_the_wire_shape__S012_001_DoD7(
    error_class: type[DomainError], code: str, status: int
) -> None:
    """012/001 DoD-7 — raised with no arguments from a route on an application with the
    handlers registered, the answer is its status and
    `{"error": {"code": …, "message": <non-empty string>, "detail": {}}}`."""
    app = _app_raising(error_class())
    response = TestClient(app).get("/boom")

    assert response.status_code == status
    payload = response.json()
    assert set(payload) == ENVELOPE_KEYS
    assert set(payload["error"]) == ERROR_KEYS
    assert payload["error"]["code"] == code
    assert payload["error"]["detail"] == {}
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"] != ""


def test_the_five_new_codes_are_distinct__S012_001_DoD7() -> None:
    """012/001 DoD-7 — D13: five errors, five different codes."""
    assert len({error_class.code for error_class, _, _ in NEW_ERRORS}) == 5


# ====================================================================== DoD-8
# `MessageResponse` is the Wire contract's `Message`; `EntryListResponse` / `ZoneResponse`
# are the listing envelopes.


def test_message_response_serialises_both_ids_as_decimal_strings__S012_001_DoD8() -> None:
    """012/001 DoD-8 — `id` and `session_id` built from ints leave as the decimal strings of
    those ints, never as JSON numbers."""
    payload = _wire(_message(id=12_345, session_id=67_890))
    assert payload["id"] == "12345"
    assert payload["session_id"] == "67890"

    big_id = 7_205_759_403_792_793_600
    big_session = 7_205_759_403_792_793_601
    big = _wire(_message(id=big_id, session_id=big_session))
    assert big["id"] == str(big_id)
    assert big["session_id"] == str(big_session)
    assert isinstance(big["id"], str)
    assert isinstance(big["session_id"], str)


def test_message_response_serialises_null_kind_and_settled_at_as_null__S012_001_DoD8() -> None:
    """012/001 DoD-8 — a zone row: `kind` and `settled_at` `None` are JSON `null`."""
    payload = _wire(_message(kind=None, settled_at=None))
    assert "kind" in payload
    assert "settled_at" in payload
    assert payload["kind"] is None
    assert payload["settled_at"] is None


def test_message_response_passes_the_text_fields_through__S012_001_DoD8() -> None:
    """012/001 DoD-8 — `role`, `kind`, `text`, `settled_at` and both timestamps are the values
    given."""
    payload = _wire(
        _message(
            role="user",
            kind="partner",
            text="  verbatim ((ooc)) text  ",
            settled_at=SETTLED_AT,
            created_at=CREATED_AT,
            updated_at=UPDATED_AT,
        )
    )
    assert payload["role"] == "user"
    assert payload["kind"] == "partner"
    assert payload["text"] == "  verbatim ((ooc)) text  "
    assert payload["settled_at"] == SETTLED_AT
    assert payload["created_at"] == CREATED_AT
    assert payload["updated_at"] == UPDATED_AT


def test_message_response_has_exactly_the_eight_wire_keys__S012_001_DoD8__S022_001_DoD4() -> None:
    """012/001 DoD-8 (amended by 022 001 DoD-4) — the serialised object is exactly the
    eleven wire keys (the eight plus `tool_name`, `tool_status`, `tool_args`), with no
    `user_id`, `related_to`, `tool_payload` or `call_id`."""
    for model in (_message(), _message(kind=None, settled_at=None)):
        payload = _wire(model)
        assert set(payload) == MESSAGE_WIRE_KEYS
        for absent in NEVER_ON_THE_WIRE:
            assert absent not in payload


def test_entry_list_response_wraps_the_rows_under_entries_in_order__S012_001_DoD8__S022_001_DoD4() -> None:
    """012/001 DoD-8 — `EntryListResponse` serialises with the single key `entries`,
    preserving the given order."""
    first = _message(id=3, kind="partner")
    second = _message(id=1, kind="turn")
    third = _message(id=2, kind="decision")
    payload = _wire(EntryListResponse(entries=[first, second, third]))

    assert set(payload) == {"entries"}
    assert payload["entries"] == [_wire(first), _wire(second), _wire(third)]
    assert [row["id"] for row in payload["entries"]] == ["3", "1", "2"]
    assert all(set(row) == MESSAGE_WIRE_KEYS for row in payload["entries"])


def test_zone_response_wraps_the_rows_under_messages_in_order__S012_001_DoD8__S022_001_DoD4() -> None:
    """012/001 DoD-8 — `ZoneResponse` serialises with the single key `messages`, preserving
    the given order."""
    first = _message(id=20, kind=None, settled_at=None)
    second = _message(id=10, role="assistant", kind=None, settled_at=None)
    payload = _wire(ZoneResponse(messages=[first, second]))

    assert set(payload) == {"messages"}
    assert payload["messages"] == [_wire(first), _wire(second)]
    assert [row["id"] for row in payload["messages"]] == ["20", "10"]
    assert all(set(row) == MESSAGE_WIRE_KEYS for row in payload["messages"])


def test_empty_listings_serialise_as_empty_lists__S012_001_DoD8() -> None:
    """012/001 DoD-8 — no rows is the empty list under the same single key."""
    assert _wire(EntryListResponse(entries=[])) == {"entries": []}
    assert _wire(ZoneResponse(messages=[])) == {"messages": []}


# ====================================================================== DoD-9
# `SettleResponse` / `ReopenResponse`: every id, list elements included, is a decimal string.


@pytest.mark.parametrize("kind", ["turn", "decision"])
def test_settle_response_serialises_every_id_as_a_decimal_string__S012_001_DoD9(kind: str) -> None:
    """012/001 DoD-9 — `entry_id` and each element of `buried_ids` leave as decimal strings."""
    big = 7_205_759_403_792_793_600
    payload = _wire(SettleResponse(entry_id=big, kind=kind, buried_ids=[11, 12, big + 1]))
    assert payload == {
        "entry_id": str(big),
        "kind": kind,
        "buried_ids": ["11", "12", str(big + 1)],
    }


def test_settle_response_keeps_an_empty_buried_list_empty__S012_001_DoD9() -> None:
    """012/001 DoD-9 — an empty `buried_ids` stays `[]`."""
    payload = _wire(SettleResponse(entry_id=5, kind="turn", buried_ids=[]))
    assert payload["buried_ids"] == []
    assert payload["entry_id"] == "5"


def test_reopen_response_serialises_every_id_as_a_decimal_string__S012_001_DoD9() -> None:
    """012/001 DoD-9 — `reopened_id` and each element of `restored_ids` leave as decimal
    strings."""
    big = 7_205_759_403_792_793_600
    payload = _wire(ReopenResponse(reopened_id=big, restored_ids=[21, big + 2]))
    assert payload == {"reopened_id": str(big), "restored_ids": ["21", str(big + 2)]}


def test_reopen_response_keeps_an_empty_restored_list_empty__S012_001_DoD9() -> None:
    """012/001 DoD-9 — an empty `restored_ids` stays `[]`."""
    payload = _wire(ReopenResponse(reopened_id=7, restored_ids=[]))
    assert payload == {"reopened_id": "7", "restored_ids": []}


# ====================================================================== DoD-10
# `AppendMessageRequest` / `EditMessageRequest`: D9 — required, non-blank, verbatim, no
# maximum; unknown keys ignored.


@pytest.mark.parametrize("model", TEXT_REQUEST_MODELS, ids=TEXT_REQUEST_IDS)
def test_text_request_parses_plain_text__S012_001_DoD10(model: type[BaseModel]) -> None:
    """012/001 DoD-10 — `{"text": "x"}` parses."""
    request = model.model_validate({"text": "x"})
    assert request.model_dump()["text"] == "x"


@pytest.mark.parametrize("model", TEXT_REQUEST_MODELS, ids=TEXT_REQUEST_IDS)
def test_text_request_keeps_the_text_unchanged__S012_001_DoD10(model: type[BaseModel]) -> None:
    """012/001 DoD-10 — D9 / R12: `"  two  spaces  "` parses with the text **unchanged**, not
    trimmed and not normalised."""
    request = model.model_validate({"text": "  two  spaces  "})
    assert request.model_dump()["text"] == "  two  spaces  "


@pytest.mark.parametrize("model", TEXT_REQUEST_MODELS, ids=TEXT_REQUEST_IDS)
@pytest.mark.parametrize("body", BLANK_TEXT_BODIES, ids=BLANK_TEXT_IDS)
def test_text_request_refuses_missing_or_blank_text__S012_001_DoD10(
    model: type[BaseModel], body: dict[str, Any]
) -> None:
    """012/001 DoD-10 — `{}`, `""`, whitespace-only and `null` text each fail validation."""
    with pytest.raises(ValidationError):
        model.model_validate(body)


@pytest.mark.parametrize("model", TEXT_REQUEST_MODELS, ids=TEXT_REQUEST_IDS)
def test_text_request_accepts_a_million_characters__S012_001_DoD10(model: type[BaseModel]) -> None:
    """012/001 DoD-10 — R10 / US-035.AC-2: no maximum length; one million characters parse
    intact."""
    huge = "a" * 1_000_000
    request = model.model_validate({"text": huge})
    assert request.model_dump()["text"] == huge
    assert len(request.model_dump()["text"]) == 1_000_000


@pytest.mark.parametrize("model", TEXT_REQUEST_MODELS, ids=TEXT_REQUEST_IDS)
def test_text_request_ignores_unknown_keys__S012_001_DoD10(model: type[BaseModel]) -> None:
    """012/001 DoD-10 — `role`, `kind` and `session_id` are ignored, not rejected, and none
    appears on the parsed model."""
    request = model.model_validate(
        {"text": "hello", "role": "assistant", "kind": "decision", "session_id": "7250000000000000009"}
    )
    assert request.model_dump()["text"] == "hello"
    assert set(request.model_dump()) == {"text"}
    for absent in ("role", "kind", "session_id"):
        assert not hasattr(request, absent)
        assert absent not in type(request).model_fields


# ====================================================================== DoD-11
# `FilePartnerRequest`: `kind` is required and exactly `"partner"` (R11's single exception);
# `text` follows D9 and is taken literally (US-121.AC-2 — no parens handling).


def test_file_partner_request_parses_a_partner_block__S012_001_DoD11() -> None:
    """012/001 DoD-11 — `{"kind": "partner", "text": "x"}` parses."""
    request = FilePartnerRequest.model_validate({"kind": "partner", "text": "x"})
    assert request.kind == "partner"
    assert request.text == "x"


@pytest.mark.parametrize("kind", ["turn", "decision", "Partner", None], ids=["turn", "decision", "Partner", "null"])
def test_file_partner_request_refuses_any_kind_but_partner__S012_001_DoD11(kind: Any) -> None:
    """012/001 DoD-11 — `kind` `"turn"`, `"decision"`, `"Partner"` and `null` each fail
    validation."""
    with pytest.raises(ValidationError):
        FilePartnerRequest.model_validate({"kind": kind, "text": "x"})


def test_file_partner_request_refuses_an_absent_kind__S012_001_DoD11() -> None:
    """012/001 DoD-11 — `kind` is required: a body without it fails validation."""
    with pytest.raises(ValidationError):
        FilePartnerRequest.model_validate({"text": "x"})


@pytest.mark.parametrize(
    "text_value",
    ["", "   \n\t", None, "<absent>"],
    ids=["empty", "whitespace", "null", "absent"],
)
def test_file_partner_request_refuses_blank_text__S012_001_DoD11(text_value: Any) -> None:
    """012/001 DoD-11 — a blank, null or missing `text` fails as in DoD-10."""
    body: dict[str, Any] = {"kind": "partner"}
    if text_value != "<absent>":
        body["text"] = text_value
    with pytest.raises(ValidationError):
        FilePartnerRequest.model_validate(body)


def test_file_partner_request_keeps_ooc_parentheses_intact__S012_001_DoD11() -> None:
    """012/001 DoD-11 — US-121.AC-2: text containing `((ooc))` parses with the parentheses
    intact."""
    pasted = "He nods slowly. ((ooc: back in an hour))\n((ooc))"
    request = FilePartnerRequest.model_validate({"kind": "partner", "text": pasted})
    assert request.text == pasted
    assert "((ooc))" in request.text


def test_file_partner_request_keeps_the_text_unchanged__S012_001_DoD11() -> None:
    """012/001 DoD-11 — D9: the partner text is stored verbatim, surrounding whitespace
    included."""
    request = FilePartnerRequest.model_validate({"kind": "partner", "text": "  two  spaces  "})
    assert request.text == "  two  spaces  "
