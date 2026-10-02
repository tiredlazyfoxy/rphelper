"""Feature 010, step 001 — `SetupNotFoundError` and `app/models/setups.py`.

Expected values come from `docs/plans/010.setups/001.table-error-models.md` (DoD-5..7) and
feature 010's `context.md`: the **Wire contract** (`Setup` on the wire — seven keys, never
`user_id`) and **D8** (one 404 `setup_not_found` with an empty `detail`; `name` stripped then
required non-empty; `description` verbatim; unknown body keys ignored) plus **D5** (a setup
cannot move, so `character_id` is not a field of either request model). Tests are suffixed
`__S010_001_DoD<n>`.

`test_errors.py` is not this step's file, so the error class's own coverage lives here
alongside the models it answers for, exactly as 009 placed it.
"""

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.errors import DomainError, SetupNotFoundError, register_exception_handlers
from app.models.setups import (
    CreateSetupRequest,
    SetupListResponse,
    SetupResponse,
    UpdateSetupRequest,
)

# context.md: the fixed-width timestamp form, passed through as text.
CREATED_AT = "2026-09-29T12:00:00.000000+00:00"
UPDATED_AT = "2026-09-30T08:15:30.123456+00:00"
ARCHIVED_AT = "2026-10-01T09:00:00.000000+00:00"

# context.md "Wire contract" — `Setup` on the wire has exactly these seven keys.
WIRE_KEYS = {"id", "character_id", "name", "description", "archived_at", "created_at", "updated_at"}

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


def _wire(model: SetupResponse | SetupListResponse) -> Any:
    """What the model actually serialises to on the wire."""
    return json.loads(model.model_dump_json())


def _response(**overrides: Any) -> SetupResponse:
    values: dict[str, Any] = {
        "id": 7_205_759_403_792_793_600,
        "character_id": 7_205_759_403_792_793_601,
        "name": "Tavern",
        "description": "# Scene\n\nA low-ceilinged tavern.\n",
        "archived_at": None,
        "created_at": CREATED_AT,
        "updated_at": UPDATED_AT,
    }
    values.update(overrides)
    return SetupResponse(**values)


# ====================================================================== DoD-5
# `SetupNotFoundError`: a 404 `DomainError`, rendered as the wire envelope with an empty
# `detail` (D8, R5).


def test_setup_not_found_is_a_domain_error_subclass__S010_001_DoD5() -> None:
    """010/001 DoD-5 — the not-found error follows the base's pattern as a subclass."""
    assert issubclass(SetupNotFoundError, DomainError)
    assert isinstance(SetupNotFoundError(), Exception)


def test_setup_not_found_sets_code_and_status_as_class_attributes__S010_001_DoD5() -> None:
    """010/001 DoD-5 — code `setup_not_found` and status 404 are set on the subclass itself."""
    assert "code" in vars(SetupNotFoundError)
    assert "http_status" in vars(SetupNotFoundError)
    assert SetupNotFoundError.code == "setup_not_found"
    assert SetupNotFoundError.http_status == 404
    error = SetupNotFoundError()
    assert error.code == "setup_not_found"
    assert error.http_status == 404


def test_setup_not_found_carries_an_empty_detail__S010_001_DoD5() -> None:
    """010/001 DoD-5 — D8: the error carries no structured detail."""
    assert SetupNotFoundError().detail == {}


def test_setup_not_found_from_a_route_answers_404_in_the_wire_shape__S010_001_DoD5() -> None:
    """010/001 DoD-5 — through the registered handler the response is 404 and the envelope
    `{"error": {"code": "setup_not_found", "message": …, "detail": {}}}`."""
    app = _app_raising(SetupNotFoundError())
    response = TestClient(app).get("/boom")

    assert response.status_code == 404
    payload = response.json()
    assert set(payload) == ENVELOPE_KEYS
    assert set(payload["error"]) == ERROR_KEYS
    assert payload["error"]["code"] == "setup_not_found"
    assert payload["error"]["detail"] == {}
    assert payload == SetupNotFoundError().to_wire()


# ====================================================================== DoD-6
# `SetupResponse` is the wire contract's `Setup`; `SetupListResponse` is the listing envelope.


def test_setup_response_serialises_both_ids_as_decimal_strings__S010_001_DoD6() -> None:
    """010/001 DoD-6 — `id` and `character_id` both leave as the decimal string of the int,
    never as a JSON number."""
    payload = _wire(_response(id=12_345, character_id=67_890))
    assert payload["id"] == "12345"
    assert payload["character_id"] == "67890"
    assert isinstance(payload["id"], str)
    assert isinstance(payload["character_id"], str)

    big_id = 7_205_759_403_792_793_600
    big_parent = 7_205_759_403_792_793_601
    big = _wire(_response(id=big_id, character_id=big_parent))
    assert big["id"] == str(big_id)
    assert big["character_id"] == str(big_parent)


def test_setup_response_serialises_a_missing_archive_date_as_null__S010_001_DoD6() -> None:
    """010/001 DoD-6 — `archived_at` `None` is JSON `null`; a set one passes through as text."""
    assert _wire(_response(archived_at=None))["archived_at"] is None
    assert _wire(_response(archived_at=ARCHIVED_AT))["archived_at"] == ARCHIVED_AT


def test_setup_response_has_exactly_the_seven_wire_keys__S010_001_DoD6() -> None:
    """010/001 DoD-6 — the serialised object is exactly the Wire contract's seven keys; in
    particular `user_id` is never on the wire."""
    payload = _wire(_response())
    assert set(payload) == WIRE_KEYS
    assert "user_id" not in payload


def test_setup_response_passes_name_description_and_timestamps_through__S010_001_DoD6() -> None:
    """010/001 DoD-6 — the remaining four fields are the values given, as text."""
    payload = _wire(
        _response(name="Tavern", description="# Scene\n", created_at=CREATED_AT, updated_at=UPDATED_AT)
    )
    assert payload["name"] == "Tavern"
    assert payload["description"] == "# Scene\n"
    assert payload["created_at"] == CREATED_AT
    assert payload["updated_at"] == UPDATED_AT


def test_setup_list_response_wraps_the_rows_under_one_key__S010_001_DoD6() -> None:
    """010/001 DoD-6 — the serialised object's only key is `setups`."""
    payload = _wire(SetupListResponse(setups=[_response(id=1), _response(id=2)]))
    assert set(payload) == {"setups"}


def test_setup_list_response_keeps_the_given_order__S010_001_DoD6() -> None:
    """010/001 DoD-6 — the rows serialise in the order given, each as the seven-key wire object."""
    first = _response(id=1, name="Tavern")
    second = _response(id=2, name="Dockside", archived_at=ARCHIVED_AT)
    payload = _wire(SetupListResponse(setups=[first, second]))

    assert payload["setups"] == [_wire(first), _wire(second)]
    assert [row["id"] for row in payload["setups"]] == ["1", "2"]
    assert [row["name"] for row in payload["setups"]] == ["Tavern", "Dockside"]
    assert all(set(row) == WIRE_KEYS for row in payload["setups"])


def test_setup_list_response_serialises_an_empty_list__S010_001_DoD6() -> None:
    """010/001 DoD-6 — no setups is the empty list under the same one key."""
    assert _wire(SetupListResponse(setups=[])) == {"setups": []}


# ====================================================================== DoD-7
# `CreateSetupRequest` and `UpdateSetupRequest`: D8's name rule, the `description` default
# and verbatim rule, unknown keys ignored, and D5 (no `character_id` in a body).


def test_create_request_strips_the_name__S010_001_DoD7() -> None:
    """010/001 DoD-7 — D8: the stored name is the stripped value."""
    assert CreateSetupRequest.model_validate({"name": "  Tavern  "}).name == "Tavern"


@pytest.mark.parametrize("body", [{"name": ""}, {"name": "   "}, {"description": "# Scene"}])
def test_create_request_rejects_a_blank_or_missing_name__S010_001_DoD7(body: dict[str, Any]) -> None:
    """010/001 DoD-7 — D8: empty, whitespace-only and absent names all fail validation."""
    with pytest.raises(ValidationError):
        CreateSetupRequest.model_validate(body)


def test_create_request_defaults_a_missing_description_to_the_empty_string__S010_001_DoD7() -> None:
    """010/001 DoD-7 — an omitted `description` is `""`, which the service always writes."""
    assert CreateSetupRequest.model_validate({"name": "Tavern"}).description == ""


def test_create_request_keeps_the_description_verbatim__S010_001_DoD7() -> None:
    """010/001 DoD-7 — D8: markdown whitespace is significant, so `description` is never stripped."""
    parsed = CreateSetupRequest.model_validate({"name": "Tavern", "description": "  # Scene\n"})
    assert parsed.description == "  # Scene\n"


def test_create_request_ignores_unknown_keys__S010_001_DoD7() -> None:
    """010/001 DoD-7 — D8/D5: `user_id`, `character_id` and `archived_at` cannot be set through a
    body; they are ignored, not rejected, and none of them lands on the parsed model."""
    request = CreateSetupRequest.model_validate(
        {
            "name": "Tavern",
            "description": "x",
            "user_id": 42,
            "character_id": 77,
            "archived_at": ARCHIVED_AT,
            "nonsense": True,
        }
    )
    assert request.name == "Tavern"
    assert request.description == "x"
    assert set(request.model_dump()) == {"name", "description"}
    assert not hasattr(request, "user_id")
    assert not hasattr(request, "character_id")
    assert not hasattr(request, "archived_at")


def test_update_request_parses_an_empty_body_with_both_fields_unset__S010_001_DoD7() -> None:
    """010/001 DoD-7 — a PATCH supplying neither field parses, with both "not supplied"."""
    request = UpdateSetupRequest.model_validate({})
    assert request.name is None
    assert request.description is None
    assert request.model_fields_set == set()


def test_update_request_treats_an_explicit_null_as_absent__S010_001_DoD7() -> None:
    """010/001 DoD-7 — an explicit `null` means "not supplied", exactly as absence does."""
    explicit = UpdateSetupRequest.model_validate({"name": None})
    assert explicit.name is None
    assert explicit == UpdateSetupRequest.model_validate({})

    explicit_description = UpdateSetupRequest.model_validate({"description": None})
    assert explicit_description.description is None
    assert explicit_description == UpdateSetupRequest.model_validate({})


def test_update_request_strips_a_supplied_name__S010_001_DoD7() -> None:
    """010/001 DoD-7 — D8: a supplied name follows the same strip-then-non-empty rule."""
    assert UpdateSetupRequest.model_validate({"name": " Inn "}).name == "Inn"


@pytest.mark.parametrize("name", ["   ", "", "\t\n "])
def test_update_request_rejects_a_blank_name__S010_001_DoD7(name: str) -> None:
    """010/001 DoD-7 — D8: a supplied whitespace-only or empty name fails validation."""
    with pytest.raises(ValidationError):
        UpdateSetupRequest.model_validate({"name": name})


def test_update_request_keeps_the_description_verbatim__S010_001_DoD7() -> None:
    """010/001 DoD-7 — D8: a supplied `description` is kept exactly, and may be empty."""
    assert UpdateSetupRequest.model_validate({"description": "  # Scene\n"}).description == "  # Scene\n"
    assert UpdateSetupRequest.model_validate({"description": ""}).description == ""


def test_update_request_ignores_unknown_keys_including_character_id__S010_001_DoD7() -> None:
    """010/001 DoD-7 — D5: a setup cannot move, so a body carrying `character_id` is ignored like
    any other unknown key."""
    request = UpdateSetupRequest.model_validate(
        {"name": "Inn", "user_id": 42, "character_id": 77, "archived_at": ARCHIVED_AT, "nonsense": True}
    )
    assert request.name == "Inn"
    assert set(request.model_dump()) == {"name", "description"}
    assert not hasattr(request, "user_id")
    assert not hasattr(request, "character_id")
    assert not hasattr(request, "archived_at")
