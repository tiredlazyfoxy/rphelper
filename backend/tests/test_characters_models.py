"""Feature 009, step 001 — `CharacterNotFoundError` and `app/models/characters.py`.

Expected values come from `docs/plans/009.characters/001.table-error-models.md` (DoD-5..9)
and feature 009's `context.md`: the **Wire contract** (`Character` on the wire) and **D8**
(one 404 `character_not_found`; `name` stripped then required non-empty; `sheet` verbatim;
unknown body keys ignored). Tests are suffixed `__S009_001_DoD<n>`.

`test_errors.py` is not this step's file, so the error class's own coverage lives here
alongside the models it answers for.
"""

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.errors import CharacterNotFoundError, DomainError, register_exception_handlers
from app.models.characters import (
    CharacterListResponse,
    CharacterResponse,
    CreateCharacterRequest,
    UpdateCharacterRequest,
)

# context.md: the fixed-width timestamp form, passed through as text.
CREATED_AT = "2026-09-29T12:00:00.000000+00:00"
UPDATED_AT = "2026-09-30T08:15:30.123456+00:00"
ARCHIVED_AT = "2026-10-01T09:00:00.000000+00:00"

# context.md "Wire contract" — `Character` on the wire has exactly these six keys.
WIRE_KEYS = {"id", "name", "sheet", "archived_at", "created_at", "updated_at"}

# The error envelope `errors.py` renders: one `error` key over exactly three.
ENVELOPE_KEYS = {"error"}
ERROR_KEYS = {"code", "message", "detail"}


def _app_raising(exc: BaseException) -> FastAPI:
    """A throwaway application with the handlers registered and one route that raises ``exc``."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise exc

    return app


def _wire(model: CharacterResponse | CharacterListResponse) -> Any:
    """What the model actually serialises to on the wire."""
    return json.loads(model.model_dump_json())


def _response(**overrides: Any) -> CharacterResponse:
    values: dict[str, Any] = {
        "id": 7_205_759_403_792_793_600,
        "name": "Aria",
        "sheet": "# Aria\n\nA sharp-tongued archivist.\n",
        "archived_at": None,
        "created_at": CREATED_AT,
        "updated_at": UPDATED_AT,
    }
    values.update(overrides)
    return CharacterResponse(**values)


# ====================================================================== DoD-5
# `CharacterNotFoundError`: a 404 `DomainError`, rendered as the wire envelope with an
# empty `detail` (D8, R5).


def test_character_not_found_is_a_domain_error_subclass__S009_001_DoD5() -> None:
    """009/001 DoD-5 — the not-found error follows the base's pattern as a subclass."""
    assert issubclass(CharacterNotFoundError, DomainError)
    assert isinstance(CharacterNotFoundError(), Exception)


def test_character_not_found_sets_code_and_status_as_class_attributes__S009_001_DoD5() -> None:
    """009/001 DoD-5 — code `character_not_found` and status 404 are set on the subclass itself."""
    assert "code" in vars(CharacterNotFoundError)
    assert "http_status" in vars(CharacterNotFoundError)
    assert CharacterNotFoundError.code == "character_not_found"
    assert CharacterNotFoundError.http_status == 404
    error = CharacterNotFoundError()
    assert error.code == "character_not_found"
    assert error.http_status == 404


def test_character_not_found_carries_an_empty_detail__S009_001_DoD5() -> None:
    """009/001 DoD-5 — D8: the error carries no structured detail."""
    assert CharacterNotFoundError().detail == {}


def test_character_not_found_from_a_route_answers_404_in_the_wire_shape__S009_001_DoD5() -> None:
    """009/001 DoD-5 — through the registered handler the response is 404 and the envelope
    `{"error": {"code": "character_not_found", …, "detail": {}}}`."""
    app = _app_raising(CharacterNotFoundError())
    response = TestClient(app).get("/boom")

    assert response.status_code == 404
    payload = response.json()
    assert set(payload) == ENVELOPE_KEYS
    assert set(payload["error"]) == ERROR_KEYS
    assert payload["error"]["code"] == "character_not_found"
    assert payload["error"]["detail"] == {}
    assert payload == CharacterNotFoundError().to_wire()


# ====================================================================== DoD-6
# `CharacterResponse` is the wire contract's `Character`.


def test_character_response_serialises_id_as_the_decimal_string__S009_001_DoD6() -> None:
    """009/001 DoD-6 — an int id leaves as the decimal string of that int, never a number."""
    payload = _wire(_response(id=12_345))
    assert payload["id"] == "12345"
    assert isinstance(payload["id"], str)

    big = 7_205_759_403_792_793_600
    assert _wire(_response(id=big))["id"] == str(big)


def test_character_response_serialises_a_missing_archive_date_as_null__S009_001_DoD6() -> None:
    """009/001 DoD-6 — `archived_at` `None` is JSON `null`; a set one passes through as text."""
    assert _wire(_response(archived_at=None))["archived_at"] is None
    assert _wire(_response(archived_at=ARCHIVED_AT))["archived_at"] == ARCHIVED_AT


def test_character_response_has_exactly_the_six_wire_keys__S009_001_DoD6() -> None:
    """009/001 DoD-6 — the serialised object is exactly the Wire contract's six keys; in
    particular `user_id` is never on the wire."""
    payload = _wire(_response())
    assert set(payload) == WIRE_KEYS
    assert "user_id" not in payload


def test_character_response_passes_name_sheet_and_timestamps_through__S009_001_DoD6() -> None:
    """009/001 DoD-6 — the remaining four fields are the values given, as text."""
    payload = _wire(_response(name="Aria", sheet="# Aria\n", created_at=CREATED_AT, updated_at=UPDATED_AT))
    assert payload["name"] == "Aria"
    assert payload["sheet"] == "# Aria\n"
    assert payload["created_at"] == CREATED_AT
    assert payload["updated_at"] == UPDATED_AT


# ====================================================================== DoD-7
# `CharacterListResponse` is the listing envelope.


def test_character_list_response_wraps_the_rows_under_one_key__S009_001_DoD7() -> None:
    """009/001 DoD-7 — the serialised object's only key is `characters`."""
    payload = _wire(CharacterListResponse(characters=[_response(id=1), _response(id=2)]))
    assert set(payload) == {"characters"}


def test_character_list_response_keeps_the_given_order__S009_001_DoD7() -> None:
    """009/001 DoD-7 — the rows serialise in the order given, each as the six-key wire object."""
    first = _response(id=1, name="Aria")
    second = _response(id=2, name="Bo", archived_at=ARCHIVED_AT)
    payload = _wire(CharacterListResponse(characters=[first, second]))

    assert payload["characters"] == [_wire(first), _wire(second)]
    assert [row["id"] for row in payload["characters"]] == ["1", "2"]
    assert [row["name"] for row in payload["characters"]] == ["Aria", "Bo"]
    assert all(set(row) == WIRE_KEYS for row in payload["characters"])


def test_character_list_response_serialises_an_empty_list__S009_001_DoD7() -> None:
    """009/001 DoD-7 — no characters is the empty list under the same one key."""
    assert _wire(CharacterListResponse(characters=[])) == {"characters": []}


# ====================================================================== DoD-8
# `CreateCharacterRequest`: D8's name rule, the `sheet` default, unknown keys ignored.


def test_create_request_strips_the_name__S009_001_DoD8() -> None:
    """009/001 DoD-8 — D8: the stored name is the stripped value."""
    assert CreateCharacterRequest.model_validate({"name": "  Aria  "}).name == "Aria"


@pytest.mark.parametrize("body", [{"name": ""}, {"name": "   "}, {"sheet": "# Notes"}])
def test_create_request_rejects_a_blank_or_missing_name__S009_001_DoD8(body: dict[str, Any]) -> None:
    """009/001 DoD-8 — D8: empty, whitespace-only and absent names all fail validation."""
    with pytest.raises(ValidationError):
        CreateCharacterRequest.model_validate(body)


def test_create_request_defaults_a_missing_sheet_to_the_empty_string__S009_001_DoD8() -> None:
    """009/001 DoD-8 — an omitted `sheet` is `""`, which the service always writes."""
    assert CreateCharacterRequest.model_validate({"name": "Aria"}).sheet == ""


def test_create_request_keeps_the_sheet_verbatim__S009_001_DoD8() -> None:
    """009/001 DoD-8 — D8: markdown whitespace is significant, so `sheet` is never stripped."""
    assert CreateCharacterRequest.model_validate({"name": "Aria", "sheet": "  # Notes\n"}).sheet == "  # Notes\n"


def test_create_request_ignores_unknown_keys__S009_001_DoD8() -> None:
    """009/001 DoD-8 — D8: `user_id` and `archived_at` cannot be set through a body; they are
    ignored, not rejected."""
    request = CreateCharacterRequest.model_validate(
        {"name": "Aria", "sheet": "x", "user_id": 42, "archived_at": ARCHIVED_AT, "nonsense": True}
    )
    assert request.name == "Aria"
    assert request.sheet == "x"
    assert set(request.model_dump()) == {"name", "sheet"}
    assert not hasattr(request, "user_id")
    assert not hasattr(request, "archived_at")


# ====================================================================== DoD-9
# `UpdateCharacterRequest`: absent or null means "not supplied" (D7), same name rule (D8).


def test_update_request_parses_an_empty_body_with_both_fields_unset__S009_001_DoD9() -> None:
    """009/001 DoD-9 — D7: a PATCH supplying neither field parses, with both "not supplied"."""
    request = UpdateCharacterRequest.model_validate({})
    assert request.name is None
    assert request.sheet is None
    assert request.model_fields_set == set()


def test_update_request_treats_an_explicit_null_name_as_absent__S009_001_DoD9() -> None:
    """009/001 DoD-9 — D7: an explicit `null` means "not supplied", exactly as absence does."""
    explicit = UpdateCharacterRequest.model_validate({"name": None})
    assert explicit.name is None
    assert explicit == UpdateCharacterRequest.model_validate({})

    explicit_sheet = UpdateCharacterRequest.model_validate({"sheet": None})
    assert explicit_sheet.sheet is None
    assert explicit_sheet == UpdateCharacterRequest.model_validate({})


def test_update_request_strips_a_supplied_name__S009_001_DoD9() -> None:
    """009/001 DoD-9 — D8: a supplied name follows the same strip-then-non-empty rule."""
    assert UpdateCharacterRequest.model_validate({"name": " Bo "}).name == "Bo"


@pytest.mark.parametrize("name", ["   ", "", "\t\n "])
def test_update_request_rejects_a_blank_name__S009_001_DoD9(name: str) -> None:
    """009/001 DoD-9 — D8: a supplied whitespace-only or empty name fails validation."""
    with pytest.raises(ValidationError):
        UpdateCharacterRequest.model_validate({"name": name})


def test_update_request_keeps_the_sheet_verbatim__S009_001_DoD9() -> None:
    """009/001 DoD-9 — D8: a supplied `sheet` is kept exactly, and may be empty."""
    assert UpdateCharacterRequest.model_validate({"sheet": "  # Notes\n"}).sheet == "  # Notes\n"
    assert UpdateCharacterRequest.model_validate({"sheet": ""}).sheet == ""


def test_update_request_ignores_unknown_keys__S009_001_DoD9() -> None:
    """009/001 DoD-9 — D8: unknown body keys are ignored, not rejected."""
    request = UpdateCharacterRequest.model_validate(
        {"name": "Bo", "user_id": 42, "archived_at": ARCHIVED_AT, "nonsense": True}
    )
    assert request.name == "Bo"
    assert set(request.model_dump()) == {"name", "sheet"}
    assert not hasattr(request, "user_id")
    assert not hasattr(request, "archived_at")
