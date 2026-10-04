"""Feature 011, step 001 — the two new domain errors and `app/models/sessions.py`.

Expected values come from `docs/plans/011.rp-sessions/001.table-errors-models.md`
(DoD-5..8) and feature 011's `context.md`: the **Wire contract** (`Session` on the wire —
eight keys, never `user_id`), **D12** (`session_not_found` → 404 and `setup_archived` →
409, each with an empty `detail`) and **D2** (the start body: omitted / `{}` /
`{ setup_id: string | null }`, unknown keys ignored). Tests are suffixed
`__S011_001_DoD<n>`.

`test_errors.py` is not this step's file, so the two error classes' own coverage lives here
alongside the models they answer for, exactly as 009 and 010 placed theirs.

Extended by feature 018, step 001 (`docs/plans/018.character-page/
001.zone-insert-and-models.md`, DoD-5 / DoD-6; feature `context.md` **D3** and the Wire
contract): `StartSessionRequest` gains an optional `opening_message`, and
`StartedSessionResponse` is the session's eight keys plus `opening_message`. Three 011
DoD-8 assertions that pinned the request's field set to exactly `setup_id` are widened to
include `opening_message` (user-approved mechanical amendment); those tests and the new
ones carry the suffix `__S018_001_DoD<n>`.

Key-set repaired by feature 024, step 005 (`docs/plans/024.embedding-lifecycle/context.md`
**Wire contract** and the regression-fallout protocol; authorised by `status.md`
`## Ultra phase` conflict (5)): the embedded `MessageResponse` gained the required boolean
`search_coverage_incomplete`, always present on the wire and `false` outside the
record-keeping routes, so the embedded message's key set is **twelve** keys. Only the
message key set, the message value and its expected wire object changed.
"""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.errors import DomainError, SessionNotFoundError, SetupArchivedError, register_exception_handlers
from app.models.sessions import (
    SessionListResponse,
    SessionResponse,
    StartedSessionResponse,
    StartSessionRequest,
)
from app.models.stream import MessageResponse

# context.md: the fixed-width timestamp form, passed through as text.
CREATED_AT = "2026-09-29T12:00:00.000000+00:00"
UPDATED_AT = "2026-09-30T08:15:30.123456+00:00"
LAST_USED_AT = "2026-09-29T12:00:00.000000+00:00"
ARCHIVED_AT = "2026-10-01T09:00:00.000000+00:00"

# context.md "Wire contract" — `Session` on the wire has exactly these eight keys.
WIRE_KEYS = {
    "id",
    "character_id",
    "setup_id",
    "setup_name",
    "archived_at",
    "last_used_at",
    "created_at",
    "updated_at",
}

# The error envelope `errors.py` renders: one `error` key over exactly three.
ENVELOPE_KEYS = {"error"}
ERROR_KEYS = {"code", "message", "detail"}

# 001.context.md "Gotcha — the nullable inbound snowflake": the decimal string DoD-8 pins.
SETUP_ID_TEXT = "7250000000000000001"
SETUP_ID_INT = 7250000000000000001


def _app_raising(exc: BaseException) -> FastAPI:
    """A throwaway application with the handlers registered and one route that raises ``exc``."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise exc

    return app


def _wire(model: SessionResponse | SessionListResponse) -> Any:
    """What the model actually serialises to on the wire."""
    return json.loads(model.model_dump_json())


def _response(**overrides: Any) -> SessionResponse:
    values: dict[str, Any] = {
        "id": 7_205_759_403_792_793_600,
        "character_id": 7_205_759_403_792_793_601,
        "setup_id": 7_205_759_403_792_793_602,
        "setup_name": "Tavern",
        "archived_at": None,
        "last_used_at": LAST_USED_AT,
        "created_at": CREATED_AT,
        "updated_at": UPDATED_AT,
    }
    values.update(overrides)
    return SessionResponse(**values)


# ====================================================================== DoD-5
# `SessionNotFoundError`: a 404 `DomainError` rendered as the wire envelope with an empty
# `detail` (D12, R5 — "no such session" and "another user's session" are indistinguishable).


def test_session_not_found_is_a_domain_error_subclass__S011_001_DoD5() -> None:
    """011/001 DoD-5 — the not-found error follows the base's pattern as a subclass."""
    assert issubclass(SessionNotFoundError, DomainError)
    assert isinstance(SessionNotFoundError(), Exception)


def test_session_not_found_sets_code_and_status_as_class_attributes__S011_001_DoD5() -> None:
    """011/001 DoD-5 — code `session_not_found` and status 404 are set on the subclass itself."""
    assert "code" in vars(SessionNotFoundError)
    assert "http_status" in vars(SessionNotFoundError)
    assert SessionNotFoundError.code == "session_not_found"
    assert SessionNotFoundError.http_status == 404
    error = SessionNotFoundError()
    assert error.code == "session_not_found"
    assert error.http_status == 404


def test_session_not_found_carries_an_empty_detail__S011_001_DoD5() -> None:
    """011/001 DoD-5 — D12: the error carries no structured detail."""
    assert SessionNotFoundError().detail == {}


def test_session_not_found_from_a_route_answers_404_in_the_wire_shape__S011_001_DoD5() -> None:
    """011/001 DoD-5 — raised from a route on an application with the handlers registered, the
    answer is 404 and the envelope
    `{"error": {"code": "session_not_found", "message": …, "detail": {}}}`."""
    app = _app_raising(SessionNotFoundError())
    response = TestClient(app).get("/boom")

    assert response.status_code == 404
    payload = response.json()
    assert set(payload) == ENVELOPE_KEYS
    assert set(payload["error"]) == ERROR_KEYS
    assert payload["error"]["code"] == "session_not_found"
    assert payload["error"]["detail"] == {}
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"] != ""


# ====================================================================== DoD-6
# `SetupArchivedError`: D12's conflict — the request is well formed and the caller owns the
# setup, but its state conflicts with the operation, so 409 and not 404 or 422.


def test_setup_archived_is_a_domain_error_subclass__S011_001_DoD6() -> None:
    """011/001 DoD-6 — the conflict error is a `DomainError` subclass like the rest."""
    assert issubclass(SetupArchivedError, DomainError)
    assert isinstance(SetupArchivedError(), Exception)


def test_setup_archived_sets_code_and_status_as_class_attributes__S011_001_DoD6() -> None:
    """011/001 DoD-6 — code `setup_archived` and status 409 are set on the subclass itself."""
    assert "code" in vars(SetupArchivedError)
    assert "http_status" in vars(SetupArchivedError)
    assert SetupArchivedError.code == "setup_archived"
    assert SetupArchivedError.http_status == 409
    error = SetupArchivedError()
    assert error.code == "setup_archived"
    assert error.http_status == 409


def test_setup_archived_carries_an_empty_detail__S011_001_DoD6() -> None:
    """011/001 DoD-6 — D12: no field is malformed, so there is nothing to report in `detail`."""
    assert SetupArchivedError().detail == {}


def test_setup_archived_from_a_route_answers_409_in_the_wire_shape__S011_001_DoD6() -> None:
    """011/001 DoD-6 — raised from a route on an application with the handlers registered, the
    answer is 409 with code `setup_archived` and an empty `detail`."""
    app = _app_raising(SetupArchivedError())
    response = TestClient(app).get("/boom")

    assert response.status_code == 409
    payload = response.json()
    assert set(payload) == ENVELOPE_KEYS
    assert set(payload["error"]) == ERROR_KEYS
    assert payload["error"]["code"] == "setup_archived"
    assert payload["error"]["detail"] == {}
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"] != ""


def test_the_two_new_codes_are_distinct_from_each_other__S011_001_DoD6() -> None:
    """011/001 DoD-5/DoD-6 — D12: each code names what the request addressed, so the
    not-found and the conflict never share a code or a status."""
    assert SessionNotFoundError.code != SetupArchivedError.code
    assert SessionNotFoundError.http_status != SetupArchivedError.http_status


# ====================================================================== DoD-7
# `SessionResponse` is the Wire contract's `Session`; `SessionListResponse` is the listing
# envelope. Ids leave as decimal strings (data-model.md Identifiers), `user_id` never does.


def test_session_response_serialises_all_three_ids_as_decimal_strings__S011_001_DoD7() -> None:
    """011/001 DoD-7 — `id`, `character_id` and `setup_id` each leave as the decimal string of
    the int given, never as a JSON number."""
    payload = _wire(_response(id=12_345, character_id=67_890, setup_id=24_680))
    assert payload["id"] == "12345"
    assert payload["character_id"] == "67890"
    assert payload["setup_id"] == "24680"
    assert isinstance(payload["id"], str)
    assert isinstance(payload["character_id"], str)
    assert isinstance(payload["setup_id"], str)

    big_id = 7_205_759_403_792_793_600
    big_parent = 7_205_759_403_792_793_601
    big_setup = 7_205_759_403_792_793_602
    big = _wire(_response(id=big_id, character_id=big_parent, setup_id=big_setup))
    assert big["id"] == str(big_id)
    assert big["character_id"] == str(big_parent)
    assert big["setup_id"] == str(big_setup)


def test_session_response_serialises_the_three_nullable_fields_as_null__S011_001_DoD7() -> None:
    """011/001 DoD-7 — with `setup_id`, `setup_name` and `archived_at` `None`, each is JSON
    `null` (a session with no setup, R2's "no sentinel"; a working session)."""
    payload = _wire(_response(setup_id=None, setup_name=None, archived_at=None))
    assert payload["setup_id"] is None
    assert payload["setup_name"] is None
    assert payload["archived_at"] is None


def test_session_response_passes_a_set_setup_name_and_archive_date_through__S011_001_DoD7() -> None:
    """011/001 DoD-7 — D10: a joined `setup_name` and a set `archived_at` pass through as text."""
    payload = _wire(_response(setup_name="Tavern", archived_at=ARCHIVED_AT))
    assert payload["setup_name"] == "Tavern"
    assert payload["archived_at"] == ARCHIVED_AT


def test_session_response_has_exactly_the_eight_wire_keys__S011_001_DoD7() -> None:
    """011/001 DoD-7 — the serialised object is exactly the Wire contract's eight keys; in
    particular `user_id` is never on the wire."""
    payload = _wire(_response())
    assert set(payload) == WIRE_KEYS
    assert "user_id" not in payload

    without_setup = _wire(_response(setup_id=None, setup_name=None))
    assert set(without_setup) == WIRE_KEYS


def test_session_response_declares_no_deferred_or_owner_field__S011_001_DoD7() -> None:
    """011/001 DoD-7 — D4 / R4: no `title`, no `partner_label`, no `model_ref`, and no
    `user_id`, on the model or on the wire."""
    payload = _wire(_response())
    for absent in ("user_id", "title", "partner_label", "model_ref", "status"):
        assert absent not in payload
        assert absent not in SessionResponse.model_fields


def test_session_response_passes_the_three_timestamps_through__S011_001_DoD7() -> None:
    """011/001 DoD-7 — `last_used_at`, `created_at` and `updated_at` are the values given, as
    text in the fixed-width form."""
    payload = _wire(
        _response(last_used_at=LAST_USED_AT, created_at=CREATED_AT, updated_at=UPDATED_AT)
    )
    assert payload["last_used_at"] == LAST_USED_AT
    assert payload["created_at"] == CREATED_AT
    assert payload["updated_at"] == UPDATED_AT


def test_session_list_response_wraps_the_rows_under_one_key__S011_001_DoD7() -> None:
    """011/001 DoD-7 — the serialised object's only key is `sessions`."""
    payload = _wire(SessionListResponse(sessions=[_response(id=1), _response(id=2)]))
    assert set(payload) == {"sessions"}


def test_session_list_response_keeps_the_given_order__S011_001_DoD7() -> None:
    """011/001 DoD-7 — the rows serialise in the order given, each as the eight-key wire
    object."""
    first = _response(id=1, setup_name="Tavern")
    second = _response(id=2, setup_id=None, setup_name=None, archived_at=ARCHIVED_AT)
    payload = _wire(SessionListResponse(sessions=[first, second]))

    assert payload["sessions"] == [_wire(first), _wire(second)]
    assert [row["id"] for row in payload["sessions"]] == ["1", "2"]
    assert [row["setup_name"] for row in payload["sessions"]] == ["Tavern", None]
    assert all(set(row) == WIRE_KEYS for row in payload["sessions"])


def test_session_list_response_serialises_an_empty_list__S011_001_DoD7() -> None:
    """011/001 DoD-7 — no sessions is the empty list under the same one key."""
    assert _wire(SessionListResponse(sessions=[])) == {"sessions": []}


# ====================================================================== DoD-8
# `StartSessionRequest`: D2's body semantics. Absent and `null` both mean "no setup"; a
# decimal string becomes the int; a non-numeric string is a validation error; unknown keys
# are ignored, never rejected (`character_id`, `user_id`, `last_used_at`, `title` cannot be
# set through a body).


def test_start_request_parses_an_empty_body_with_no_setup__S011_001_DoD8() -> None:
    """011/001 DoD-8 — `{}` parses, and `setup_id` is unset / `None`: a session with no
    setup (R2)."""
    request = StartSessionRequest.model_validate({})
    assert request.setup_id is None
    assert request.model_fields_set == set()


def test_start_request_treats_an_explicit_null_setup_id_as_no_setup__S011_001_DoD8__S018_001_DoD5() -> None:
    """011/001 DoD-8 — `{"setup_id": null}` parses the same way as `{}`: no setup, no error,
    and no sentinel value. Amended by 018/001 DoD-5: the dump now also carries the new
    optional `opening_message` (None)."""
    request = StartSessionRequest.model_validate({"setup_id": None})
    assert request.setup_id is None
    assert request.model_dump() == {"setup_id": None, "opening_message": None}
    assert request.model_dump() == StartSessionRequest.model_validate({}).model_dump()


def test_start_request_parses_a_decimal_string_setup_id_to_an_int__S011_001_DoD8() -> None:
    """011/001 DoD-8 — the JSON id boundary: a decimal string becomes the int the service
    takes."""
    request = StartSessionRequest.model_validate({"setup_id": SETUP_ID_TEXT})
    assert request.setup_id == SETUP_ID_INT
    assert isinstance(request.setup_id, int)


@pytest.mark.parametrize("value", ["abc", "7a", ""])
def test_start_request_rejects_a_non_numeric_setup_id__S011_001_DoD8(value: str) -> None:
    """011/001 DoD-8 — a non-numeric `setup_id` fails validation (which the route answers as
    422), rather than escaping as anything else."""
    with pytest.raises(ValidationError):
        StartSessionRequest.model_validate({"setup_id": value})


def test_start_request_ignores_unknown_keys__S011_001_DoD8__S018_001_DoD5() -> None:
    """011/001 DoD-8 — D2: `character_id`, `user_id`, `last_used_at` and `title` cannot be set
    through a body. They are ignored, not rejected, and none lands on the parsed model.
    Amended by 018/001 DoD-5: the field set is now `setup_id` plus `opening_message`."""
    request = StartSessionRequest.model_validate(
        {
            "setup_id": SETUP_ID_TEXT,
            "character_id": "7250000000000000009",
            "user_id": "42",
            "last_used_at": LAST_USED_AT,
            "title": "A night at the tavern",
            "nonsense": True,
        }
    )
    assert request.setup_id == SETUP_ID_INT
    assert set(request.model_dump()) == {"setup_id", "opening_message"}
    for absent in ("character_id", "user_id", "last_used_at", "title", "nonsense"):
        assert not hasattr(request, absent)
        assert absent not in StartSessionRequest.model_fields


def test_start_request_ignores_unknown_keys_on_an_otherwise_empty_body__S011_001_DoD8__S018_001_DoD5() -> None:
    """011/001 DoD-8 — unknown keys alone still parse, still mean "no setup", and still leave
    nothing on the model. Amended by 018/001 DoD-5: the field set is now `setup_id` plus
    `opening_message`."""
    request = StartSessionRequest.model_validate({"title": "t", "character_id": "9"})
    assert request.setup_id is None
    assert set(request.model_dump()) == {"setup_id", "opening_message"}
    assert not hasattr(request, "title")


# ============================================================= 018/001 DoD-5
# `StartSessionRequest.opening_message`: optional `NonBlankText`. Absent and `null` both mean
# "none"; a present value is non-blank and kept verbatim; `setup_id` keeps 011's rules and
# unknown keys are still ignored (018 Wire contract).

# 018 context.md "Test conventions" — ids are "7250000000000000101"-style strings.
SEEDED_SETUP_ID_TEXT = "7250000000000000201"
SEEDED_SETUP_ID_INT = 7250000000000000201


def test_start_request_with_an_empty_body_has_no_opening_message__S018_001_DoD5() -> None:
    """018/001 DoD-5 — `{}` gives no opening message."""
    request = StartSessionRequest.model_validate({})
    assert request.opening_message is None
    assert request.setup_id is None


def test_start_request_with_a_null_opening_message_has_none__S018_001_DoD5() -> None:
    """018/001 DoD-5 — `{"opening_message": null}` gives no opening message, no error."""
    request = StartSessionRequest.model_validate({"opening_message": None})
    assert request.opening_message is None


def test_start_request_with_the_field_omitted_has_no_opening_message__S018_001_DoD5() -> None:
    """018/001 DoD-5 — a body that sets only `setup_id` (the field omitted) gives no opening
    message, and the setup is kept as 011 parses it."""
    request = StartSessionRequest.model_validate({"setup_id": SEEDED_SETUP_ID_TEXT})
    assert request.opening_message is None
    assert request.setup_id == SEEDED_SETUP_ID_INT


def test_start_request_keeps_the_opening_message_verbatim__S018_001_DoD5() -> None:
    """018/001 DoD-5 — `{"opening_message": "  Hello\\n"}` keeps the text verbatim, leading
    spaces and trailing newline included."""
    request = StartSessionRequest.model_validate({"opening_message": "  Hello\n"})
    assert request.opening_message == "  Hello\n"


@pytest.mark.parametrize("value", ["   ", ""], ids=["whitespace", "empty"])
def test_start_request_rejects_a_blank_opening_message__S018_001_DoD5(value: str) -> None:
    """018/001 DoD-5 — a present but blank (empty or whitespace-only) opening message fails
    validation (which the route answers as 422)."""
    with pytest.raises(ValidationError):
        StartSessionRequest.model_validate({"opening_message": value})


def test_start_request_keeps_both_setup_and_opening_message__S018_001_DoD5() -> None:
    """018/001 DoD-5 — `{"setup_id": "7250000000000000201", "opening_message": "Hi"}` keeps
    both: the setup id as the int, the message as given."""
    request = StartSessionRequest.model_validate(
        {"setup_id": SEEDED_SETUP_ID_TEXT, "opening_message": "Hi"}
    )
    assert request.setup_id == SEEDED_SETUP_ID_INT
    assert isinstance(request.setup_id, int)
    assert request.opening_message == "Hi"


def test_start_request_with_an_opening_message_ignores_an_unknown_key__S018_001_DoD5() -> None:
    """018/001 DoD-5 — an unknown key is ignored, not rejected, and never lands on the model."""
    request = StartSessionRequest.model_validate(
        {"opening_message": "Hi", "session_id": "7250000000000000101", "nonsense": True}
    )
    assert request.opening_message == "Hi"
    assert request.setup_id is None
    assert set(request.model_dump()) == {"setup_id", "opening_message"}
    for absent in ("session_id", "nonsense"):
        assert not hasattr(request, absent)
        assert absent not in StartSessionRequest.model_fields


# ============================================================= 018/001 DoD-6
# `StartedSessionResponse`: exactly `SessionResponse`'s eight keys (same types, ids as
# decimal strings) plus `opening_message` — 012's eight-key `Message` or null (D3).

STARTED_SESSION_ID = 7250000000000000101
STARTED_CHARACTER_ID = 7250000000000000102
STARTED_SETUP_ID = 7250000000000000103
OPENING_MESSAGE_ID = 7250000000000000104

#: Amended by feature 022, step 001 (D3, DoD-4): 012's `Message` gains `tool_name`,
#: `tool_status` and `tool_args` — eleven keys, all three null on a non-tool row.
#: Amended by feature 024, step 005 (`context.md` **Wire contract**: `search_coverage_incomplete`
#: is a boolean **always present** on the backend wire, and `false` on any route other than the
#: record-keeping ones) — twelve keys. Authorised by `status.md` `## Ultra phase` conflict (5).
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
    "search_coverage_incomplete",
}


def _session_value(**overrides: Any) -> SimpleNamespace:
    """A session value (attributes, not a dict), as the router hands the response; it also
    carries the owner, which must never reach the wire."""
    values: dict[str, Any] = {
        "id": STARTED_SESSION_ID,
        "user_id": 42,
        "character_id": STARTED_CHARACTER_ID,
        "setup_id": STARTED_SETUP_ID,
        "setup_name": "Tavern",
        "archived_at": None,
        "last_used_at": LAST_USED_AT,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _message_value() -> SimpleNamespace:
    """The opening message value: a current-zone user row (kind and settled_at null).

    024/005 Wire contract: `search_coverage_incomplete` is required on `MessageResponse`, and a
    zone row always carries `false`.
    """
    return SimpleNamespace(
        id=OPENING_MESSAGE_ID,
        session_id=STARTED_SESSION_ID,
        role="user",
        kind=None,
        text="  Hello\n",
        settled_at=None,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
        search_coverage_incomplete=False,
    )


EXPECTED_SESSION_WIRE: dict[str, Any] = {
    "id": "7250000000000000101",
    "character_id": "7250000000000000102",
    "setup_id": "7250000000000000103",
    "setup_name": "Tavern",
    "archived_at": None,
    "last_used_at": LAST_USED_AT,
    "created_at": CREATED_AT,
    "updated_at": CREATED_AT,
}

EXPECTED_MESSAGE_WIRE: dict[str, Any] = {
    "id": "7250000000000000104",
    "session_id": "7250000000000000101",
    "role": "user",
    "kind": None,
    "text": "  Hello\n",
    "settled_at": None,
    "created_at": CREATED_AT,
    "updated_at": CREATED_AT,
    "tool_name": None,
    "tool_status": None,
    "tool_args": None,
    # 024/005 Wire contract: always present; `false` for a zone row.
    "search_coverage_incomplete": False,
}


def _started_from_attributes(session: SimpleNamespace, message: Any) -> StartedSessionResponse:
    source = SimpleNamespace(**vars(session), opening_message=message)
    return StartedSessionResponse.model_validate(source, from_attributes=True)


def test_started_response_without_a_message_is_eight_keys_plus_null__S018_001_DoD6() -> None:
    """018/001 DoD-6 — built from a session value and no message, it serialises to exactly
    the eight session keys plus `opening_message: null`, ids as decimal strings."""
    payload = _wire(_started_from_attributes(_session_value(), None))

    assert payload == {**EXPECTED_SESSION_WIRE, "opening_message": None}
    assert set(payload) == WIRE_KEYS | {"opening_message"}
    assert "user_id" not in payload
    for key in ("id", "character_id", "setup_id"):
        assert isinstance(payload[key], str)


def test_started_response_built_by_keyword_without_a_message__S018_001_DoD6() -> None:
    """018/001 DoD-6 — the same answer when built from the session's eight fields and
    `opening_message=None` directly."""
    fields = {key: value for key, value in vars(_session_value()).items() if key != "user_id"}
    payload = _wire(StartedSessionResponse(**fields, opening_message=None))

    assert payload == {**EXPECTED_SESSION_WIRE, "opening_message": None}


def test_started_response_with_a_null_setup_keeps_the_nulls__S018_001_DoD6() -> None:
    """018/001 DoD-6 — the eight session keys keep `SessionResponse`'s types: a session with
    no setup serialises `setup_id` and `setup_name` as null."""
    payload = _wire(_started_from_attributes(_session_value(setup_id=None, setup_name=None), None))

    assert payload == {
        **EXPECTED_SESSION_WIRE,
        "setup_id": None,
        "setup_name": None,
        "opening_message": None,
    }


def test_started_response_with_a_message_serialises_the_eight_key_message__S018_001_DoD6__S022_001_DoD4() -> None:
    """018/001 DoD-6 (amended by 022 001 DoD-4, then by 024 005) — built with a message value,
    `opening_message` is 012's message object, now twelve keys with the three tool fields null
    and `search_coverage_incomplete` false, with string ids; the session keys are unchanged."""
    payload = _wire(_started_from_attributes(_session_value(), _message_value()))

    assert set(payload) == WIRE_KEYS | {"opening_message"}
    assert {key: payload[key] for key in WIRE_KEYS} == EXPECTED_SESSION_WIRE
    message = payload["opening_message"]
    assert message == EXPECTED_MESSAGE_WIRE
    assert set(message) == MESSAGE_WIRE_KEYS
    assert isinstance(message["id"], str)
    assert isinstance(message["session_id"], str)


def test_started_response_accepts_a_message_response__S018_001_DoD6__S022_001_DoD4() -> None:
    """018/001 DoD-6 (amended by 022 001 DoD-4, then by 024 005) — `opening_message` is a 012
    `MessageResponse`: one given directly serialises to the same (now twelve-key) object."""
    fields = {key: value for key, value in vars(_session_value()).items() if key != "user_id"}
    message = MessageResponse(**vars(_message_value()))
    payload = _wire(StartedSessionResponse(**fields, opening_message=message))

    assert payload == {**EXPECTED_SESSION_WIRE, "opening_message": EXPECTED_MESSAGE_WIRE}


def test_started_response_session_keys_serialise_as_session_response__S018_001_DoD6() -> None:
    """018/001 DoD-6 — its eight session keys serialise identically to `SessionResponse`
    built from the same session value."""
    session = _session_value()
    started = _wire(_started_from_attributes(session, None))
    plain = _wire(SessionResponse.model_validate(session, from_attributes=True))

    assert {key: started[key] for key in WIRE_KEYS} == plain


def test_session_response_still_serialises_exactly_eight_keys__S018_001_DoD6() -> None:
    """018/001 DoD-6 — `SessionResponse` itself is unchanged: exactly its eight keys, no
    `opening_message`."""
    payload = _wire(SessionResponse.model_validate(_session_value(), from_attributes=True))

    assert payload == EXPECTED_SESSION_WIRE
    assert set(payload) == WIRE_KEYS
    assert "opening_message" not in payload
    assert "opening_message" not in SessionResponse.model_fields
