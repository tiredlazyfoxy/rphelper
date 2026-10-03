"""Feature 015, step 001 (`001.table-errors-models.md`) — `MemoNotFoundError`, the scope
literal and the memo request / response models.

Expected values come from that step's DoD-6..10 and feature 015's context.md "Wire contract
— memos" (the nine `Memo` keys, ids as decimal strings, `sort_key` a JSON number, `user_id`
never on the wire), D10 (the four scopes, written twice and pinned equal), D12 (the error)
and D15 (non-blank, verbatim body). Tests are suffixed `__S015_001_DoD<n>`.
"""

import json
import typing
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Enum as SqlEnum

from app.db import schema
from app.errors import DomainError, MemoNotFoundError, register_exception_handlers
from app.models.memos import (
    CreateMemoRequest,
    MemoChainLevelResponse,
    MemoChainResponse,
    MemoListResponse,
    MemoResponse,
    MemoScope,
    UpdateMemoRequest,
)

SCOPES = {"user", "character", "setup", "session"}

MEMO_WIRE_KEYS = {
    "id",
    "scope",
    "scope_id",
    "body",
    "is_enabled",
    "is_forced",
    "sort_key",
    "created_at",
    "updated_at",
}

TIMESTAMP = "2026-10-02T09:30:15.123456+00:00"
LATER_TIMESTAMP = "2026-10-02T09:31:00.000001+00:00"

BIG_MEMO_ID = 7_250_000_000_000_000_201
BIG_CHARACTER_ID = 7_250_000_000_000_000_011


@dataclass(frozen=True)
class _MemoValue:
    """A stand-in for a service value: attributes only, no `user_id`."""

    id: int
    scope: str
    scope_id: int | None
    body: str
    is_enabled: bool
    is_forced: bool
    sort_key: int
    created_at: str
    updated_at: str


def _memo_value(**overrides: Any) -> _MemoValue:
    fields: dict[str, Any] = {
        "id": BIG_MEMO_ID,
        "scope": "character",
        "scope_id": BIG_CHARACTER_ID,
        "body": "# Aria\nKeeps her promises.\n",
        "is_enabled": True,
        "is_forced": False,
        "sort_key": 2,
        "created_at": TIMESTAMP,
        "updated_at": LATER_TIMESTAMP,
    }
    fields.update(overrides)
    return _MemoValue(**fields)


def _memo_response(**overrides: Any) -> MemoResponse:
    return MemoResponse.model_validate(_memo_value(**overrides), from_attributes=True)


def _wire(model: Any) -> Any:
    """The model as it crosses the wire: serialised to JSON text, then parsed."""
    return json.loads(model.model_dump_json())


# --- DoD-6: the CHECK's values equal the scope literal's ----------------------------------


def test_scope_literal_names_exactly_the_four_scopes__S015_001_DoD6() -> None:
    """015/001 DoD-6 — the scope literal's strings are exactly user, character, setup,
    session."""
    values = typing.get_args(MemoScope)
    assert len(values) == len(set(values))
    assert set(values) == SCOPES


def test_scope_check_values_equal_the_scope_literal__S015_001_DoD6() -> None:
    """015/001 DoD-6 — the `memos.scope` constraint permits exactly the literal's strings,
    and both are the four scopes."""
    scope_type = schema.metadata.tables["memos"].c.scope.type
    assert isinstance(scope_type, SqlEnum)
    permitted = set(scope_type.enums)
    assert permitted == set(typing.get_args(MemoScope))
    assert permitted == SCOPES


# --- DoD-7: MemoNotFoundError --------------------------------------------------------------


def test_memo_not_found_error_is_a_domain_error_with_its_code_and_status__S015_001_DoD7() -> None:
    """015/001 DoD-7 — a `DomainError`, code `memo_not_found`, HTTP status 404."""
    assert issubclass(MemoNotFoundError, DomainError)
    assert MemoNotFoundError.code == "memo_not_found"
    assert MemoNotFoundError.http_status == 404


def test_memo_not_found_error_raised_bare_has_a_message_and_empty_detail__S015_001_DoD7() -> None:
    """015/001 DoD-7 — D12: raised with no arguments it carries a non-empty message and an
    empty `detail`."""
    error = MemoNotFoundError()
    assert isinstance(error.message, str)
    assert error.message.strip()
    assert error.detail == {}


def _app_raising(exc: BaseException) -> FastAPI:
    """A throwaway application with the handlers registered and one route that raises `exc`."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise exc

    return app


def test_memo_not_found_error_from_a_route_answers_the_404_envelope__S015_001_DoD7() -> None:
    """015/001 DoD-7 — raised from a route, it answers 404 with
    `{"error": {"code": "memo_not_found", "message": <non-empty>, "detail": {}}}`."""
    response = TestClient(_app_raising(MemoNotFoundError())).get("/boom")

    assert response.status_code == 404
    payload = response.json()
    assert set(payload) == {"error"}
    error = payload["error"]
    assert set(error) == {"code", "message", "detail"}
    assert error["code"] == "memo_not_found"
    assert isinstance(error["message"], str)
    assert error["message"].strip()
    assert error["detail"] == {}


# --- DoD-8: the response models on the wire ------------------------------------------------


def test_memo_response_serialises_ids_as_decimal_strings__S015_001_DoD8() -> None:
    """015/001 DoD-8 — int `id` and `scope_id` (beyond 2^53) cross as their decimal strings."""
    wire = _wire(_memo_response())
    assert wire["id"] == "7250000000000000201"
    assert wire["scope_id"] == "7250000000000000011"


def test_memo_response_serialises_a_none_scope_id_as_null__S015_001_DoD8() -> None:
    """015/001 DoD-8 — a user-level note's `scope_id` `None` serialises as JSON `null`."""
    wire = _wire(_memo_response(scope="user", scope_id=None))
    assert "scope_id" in wire
    assert wire["scope_id"] is None
    assert '"scope_id":null' in _memo_response(scope="user", scope_id=None).model_dump_json()


def test_memo_response_keeps_sort_key_a_json_number__S015_001_DoD8() -> None:
    """015/001 DoD-8 — `sort_key` is not an id: it stays a JSON number."""
    wire = _wire(_memo_response(sort_key=2))
    assert wire["sort_key"] == 2
    assert isinstance(wire["sort_key"], int)
    assert not isinstance(wire["sort_key"], bool)


def test_memo_response_has_exactly_the_nine_wire_keys_and_no_user_id__S015_001_DoD8() -> None:
    """015/001 DoD-8 — exactly the nine `Memo` keys; `user_id` is never on the wire."""
    wire = _wire(_memo_response())
    assert set(wire) == MEMO_WIRE_KEYS
    assert "user_id" not in wire


def test_memo_response_carries_the_values_it_was_built_from__S015_001_DoD8() -> None:
    """015/001 DoD-8 — built from a value by attribute, the other seven keys pass through."""
    wire = _wire(_memo_response(is_enabled=False, is_forced=True))
    assert wire["scope"] == "character"
    assert wire["body"] == "# Aria\nKeeps her promises.\n"
    assert wire["is_enabled"] is False
    assert wire["is_forced"] is True
    assert wire["created_at"] == TIMESTAMP
    assert wire["updated_at"] == LATER_TIMESTAMP


def test_memo_list_response_has_the_single_key_memos__S015_001_DoD8() -> None:
    """015/001 DoD-8 — `MemoListResponse` serialises with the single key `memos`."""
    listing = MemoListResponse(memos=[_memo_response(id=1), _memo_response(id=2)])
    wire = _wire(listing)
    assert set(wire) == {"memos"}
    assert [memo["id"] for memo in wire["memos"]] == ["1", "2"]
    for memo in wire["memos"]:
        assert set(memo) == MEMO_WIRE_KEYS


def test_memo_list_response_with_no_memos_is_an_empty_list__S015_001_DoD8() -> None:
    """015/001 DoD-8 — an empty level is `{"memos": []}`."""
    assert _wire(MemoListResponse(memos=[])) == {"memos": []}


def test_memo_chain_response_has_the_single_key_levels_in_the_order_given__S015_001_DoD8() -> None:
    """015/001 DoD-8 — `MemoChainResponse` serialises with the single key `levels`; each level
    has exactly `scope`, `scope_id`, `memos`, and the levels keep the order given."""
    user_level = MemoChainLevelResponse(
        scope="user", scope_id=None, memos=[_memo_response(id=11, scope="user", scope_id=None)]
    )
    character_level = MemoChainLevelResponse(
        scope="character", scope_id=BIG_CHARACTER_ID, memos=[_memo_response(id=12)]
    )
    session_level = MemoChainLevelResponse(scope="session", scope_id=30, memos=[])
    chain = MemoChainResponse(levels=[user_level, character_level, session_level])

    wire = _wire(chain)

    assert set(wire) == {"levels"}
    assert [level["scope"] for level in wire["levels"]] == ["user", "character", "session"]
    for level in wire["levels"]:
        assert set(level) == {"scope", "scope_id", "memos"}
    assert wire["levels"][0]["scope_id"] is None
    assert wire["levels"][1]["scope_id"] == "7250000000000000011"
    assert wire["levels"][2]["scope_id"] == "30"
    assert [memo["id"] for memo in wire["levels"][0]["memos"]] == ["11"]
    assert set(wire["levels"][1]["memos"][0]) == MEMO_WIRE_KEYS
    assert wire["levels"][2]["memos"] == []


# --- DoD-9: CreateMemoRequest --------------------------------------------------------------


def test_create_request_parses_a_character_note_with_its_scope_id_as_an_int__S015_001_DoD9() -> None:
    """015/001 DoD-9 — a decimal-string `scope_id` parses to the int it names."""
    request = CreateMemoRequest.model_validate(
        {"scope": "character", "scope_id": "7250000000000000001", "body": "x"}
    )
    assert request.scope == "character"
    assert request.scope_id == 7_250_000_000_000_000_001
    assert isinstance(request.scope_id, int)
    assert request.body == "x"


def test_create_request_parses_a_user_note_without_scope_id__S015_001_DoD9() -> None:
    """015/001 DoD-9 — `{"scope": "user", "body": "x"}` parses."""
    request = CreateMemoRequest.model_validate({"scope": "user", "body": "x"})
    assert request.scope == "user"
    assert request.scope_id is None
    assert request.body == "x"


def test_create_request_accepts_a_scope_id_on_a_user_note__S015_001_DoD9() -> None:
    """015/001 DoD-9 — Wire contract: for `scope` "user" a supplied `scope_id` is accepted
    (it has no effect downstream)."""
    request = CreateMemoRequest.model_validate({"scope": "user", "scope_id": "42", "body": "x"})
    assert request.scope == "user"


@pytest.mark.parametrize("scope", ["character", "setup", "session"])
def test_create_request_refuses_a_non_user_scope_without_scope_id__S015_001_DoD9(scope: str) -> None:
    """015/001 DoD-9 — a non-user `scope` with no `scope_id` fails validation."""
    with pytest.raises(ValidationError):
        CreateMemoRequest.model_validate({"scope": scope, "body": "x"})


def test_create_request_refuses_a_non_user_scope_with_a_null_scope_id__S015_001_DoD9() -> None:
    """015/001 DoD-9 — `scope_id` sent as `null` on a non-user scope is still "without"."""
    with pytest.raises(ValidationError):
        CreateMemoRequest.model_validate({"scope": "character", "scope_id": None, "body": "x"})


def test_create_request_refuses_an_unknown_scope__S015_001_DoD9() -> None:
    """015/001 DoD-9 — `{"scope": "world", "scope_id": "1", "body": "x"}` fails."""
    with pytest.raises(ValidationError):
        CreateMemoRequest.model_validate({"scope": "world", "scope_id": "1", "body": "x"})


def test_create_request_refuses_a_non_numeric_scope_id__S015_001_DoD9() -> None:
    """015/001 DoD-9 — Wire contract: a non-numeric id is a validation failure (422)."""
    with pytest.raises(ValidationError):
        CreateMemoRequest.model_validate({"scope": "character", "scope_id": "not-a-number", "body": "x"})


@pytest.mark.parametrize("body", ["", "  \n"])
def test_create_request_refuses_a_blank_body__S015_001_DoD9(body: str) -> None:
    """015/001 DoD-9 — D15: an empty or whitespace-only `body` fails."""
    with pytest.raises(ValidationError):
        CreateMemoRequest.model_validate({"scope": "user", "body": body})


def test_create_request_refuses_a_missing_body__S015_001_DoD9() -> None:
    """015/001 DoD-9 — `body` is required."""
    with pytest.raises(ValidationError):
        CreateMemoRequest.model_validate({"scope": "user"})


def test_create_request_keeps_the_body_verbatim__S015_001_DoD9() -> None:
    """015/001 DoD-9 — D15: `"  # h\\n"` parses and keeps those exact characters (not
    stripped)."""
    request = CreateMemoRequest.model_validate({"scope": "user", "body": "  # h\n"})
    assert request.body == "  # h\n"


def test_create_request_ignores_unknown_keys__S015_001_DoD9() -> None:
    """015/001 DoD-9 — US-053.AC-1 / US-119.AC-1: `user_id`, `is_enabled`, `is_forced`,
    `sort_key`, `title` are ignored and do not appear on the parsed model."""
    unknown = {"user_id": "99", "is_enabled": False, "is_forced": True, "sort_key": 7, "title": "Heading"}
    request = CreateMemoRequest.model_validate(
        {"scope": "character", "scope_id": "7250000000000000001", "body": "x", **unknown}
    )

    dumped = request.model_dump()
    for key in unknown:
        assert key not in dumped
        assert key not in request.model_fields_set
        assert not hasattr(request, key)
    assert request.scope == "character"
    assert request.scope_id == 7_250_000_000_000_000_001
    assert request.body == "x"


# --- DoD-10: UpdateMemoRequest -------------------------------------------------------------


def test_update_request_parses_an_empty_object_with_no_field_set__S015_001_DoD10() -> None:
    """015/001 DoD-10 — `{}` parses with no field set."""
    request = UpdateMemoRequest.model_validate({})
    assert request.model_fields_set == set()
    assert request.body is None
    assert request.is_enabled is None
    assert request.is_forced is None


def test_update_request_sets_only_is_enabled__S015_001_DoD10() -> None:
    """015/001 DoD-10 — `{"is_enabled": false}` sets only `is_enabled`."""
    request = UpdateMemoRequest.model_validate({"is_enabled": False})
    assert request.model_fields_set == {"is_enabled"}
    assert request.is_enabled is False
    assert request.is_forced is None
    assert request.body is None


def test_update_request_sets_only_is_forced__S015_001_DoD10() -> None:
    """015/001 DoD-10 — `{"is_forced": true}` sets only `is_forced`."""
    request = UpdateMemoRequest.model_validate({"is_forced": True})
    assert request.model_fields_set == {"is_forced"}
    assert request.is_forced is True
    assert request.is_enabled is None
    assert request.body is None


def test_update_request_sets_only_body__S015_001_DoD10() -> None:
    """015/001 DoD-10 — `{"body": "y"}` sets only `body`."""
    request = UpdateMemoRequest.model_validate({"body": "y"})
    assert request.model_fields_set == {"body"}
    assert request.body == "y"
    assert request.is_enabled is None
    assert request.is_forced is None


def test_update_request_keeps_a_supplied_body_verbatim__S015_001_DoD10() -> None:
    """015/001 DoD-10 — D15: a supplied body is not stripped."""
    request = UpdateMemoRequest.model_validate({"body": "  # h\n"})
    assert request.body == "  # h\n"


@pytest.mark.parametrize("body", ["", "   "])
def test_update_request_refuses_a_blank_body__S015_001_DoD10(body: str) -> None:
    """015/001 DoD-10 — `{"body": ""}` and `{"body": "   "}` fail validation."""
    with pytest.raises(ValidationError):
        UpdateMemoRequest.model_validate({"body": body})


def test_update_request_accepts_a_null_body_as_not_supplied_in_effect__S015_001_DoD10() -> None:
    """015/001 DoD-10 — a key sent as `null` parses (the router treats it as not supplied)."""
    request = UpdateMemoRequest.model_validate({"body": None, "is_enabled": None, "is_forced": None})
    assert request.body is None
    assert request.is_enabled is None
    assert request.is_forced is None


def test_update_request_ignores_unknown_keys__S015_001_DoD10() -> None:
    """015/001 DoD-10 — `scope`, `scope_id`, `sort_key`, `user_id` are ignored."""
    unknown = {"scope": "session", "scope_id": "30", "sort_key": 4, "user_id": "99"}
    request = UpdateMemoRequest.model_validate({"is_enabled": True, **unknown})

    assert request.model_fields_set == {"is_enabled"}
    dumped = request.model_dump()
    for key in unknown:
        assert key not in dumped
        assert not hasattr(request, key)
    assert request.is_enabled is True
