"""Feature 017, step 001 (`001.columns-errors-models.md`) — the two use-time errors and the
configuration request / response models.

Expected values come from that step's DoD-6..10 and feature 017's context.md: D2 (the two
errors: 409, empty `detail`, fixed non-empty message), D6 (languages trimmed, blank -> null;
system prompt verbatim, blank -> null), D10 (the session PATCH refuses `model: null`, the
character PATCH accepts it as "clear") and the Wire contract (ids as decimal strings, the
`Setting` five keys, the seven `SessionConfiguration` keys, the three `EnabledModel` keys,
the five `CharacterConfiguration` keys, unknown request keys ignored). "Which keys were sent"
is pydantic's `model_fields_set` (step 001 `## Skeleton`). Tests are suffixed
`__S017_001_DoD<n>`.
"""

import json
import typing
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.errors import (
    DomainError,
    ModelNotChosenError,
    NoModelEnabledError,
    register_exception_handlers,
)
from app.models.configuration import (
    CharacterConfigurationResponse,
    ConfigurationLevel,
    EnabledModelListResponse,
    EnabledModelResponse,
    SessionConfigurationResponse,
    UpdateCharacterConfigurationRequest,
    UpdateSessionConfigurationRequest,
    UpdateUserSettingsRequest,
)

SERVER_ID_TEXT = "7250000000000000301"
SERVER_ID_INT = 7_250_000_000_000_000_301
OTHER_SERVER_ID_TEXT = "7250000000000000302"
OTHER_SERVER_ID_INT = 7_250_000_000_000_000_302

SETTING_KEYS = {"session", "inherited", "inherited_level", "value", "level"}
SESSION_CONFIGURATION_KEYS = {
    "model",
    "system_prompt",
    "tool_memo_search",
    "tool_session_search",
    "tool_web_search",
    "rp_language",
    "preferred_language",
}
CHARACTER_CONFIGURATION_KEYS = {
    "model",
    "system_prompt",
    "tool_memo_search",
    "tool_session_search",
    "tool_web_search",
}
ENABLED_MODEL_KEYS = {"server_id", "server_name", "model_name"}
TOOL_FIELDS = ("tool_memo_search", "tool_session_search", "tool_web_search")
LANGUAGE_FIELDS = ("rp_language", "preferred_language")

USE_TIME_ERRORS = [
    (NoModelEnabledError, "no_model_enabled"),
    (ModelNotChosenError, "model_not_chosen"),
]

# The two PATCH request models that share DoD-8's model / prompt / tool rules (DoD-9: "The
# other fields follow DoD-8").
ASSISTANT_REQUESTS = [UpdateSessionConfigurationRequest, UpdateCharacterConfigurationRequest]


def _wire(model: Any) -> Any:
    """The model as it crosses the wire: serialised to JSON text, then parsed."""
    return json.loads(model.model_dump_json())


# --- service-value stand-ins (attributes only), as `003` / `004` return them ---------------


@dataclass(frozen=True)
class _ModelRefValue:
    server_id: int
    model_name: str


@dataclass(frozen=True)
class _SettingValue:
    session: Any
    inherited: Any
    inherited_level: str | None
    value: Any
    level: str | None


@dataclass(frozen=True)
class _SessionConfigurationValue:
    model: _ModelRefValue | None
    system_prompt: _SettingValue
    tool_memo_search: _SettingValue
    tool_session_search: _SettingValue
    tool_web_search: _SettingValue
    rp_language: _SettingValue
    preferred_language: _SettingValue


@dataclass(frozen=True)
class _CharacterConfigurationValue:
    model: _ModelRefValue | None
    system_prompt: str | None
    tool_memo_search: bool | None
    tool_session_search: bool | None
    tool_web_search: bool | None


def _session_configuration_value(**overrides: Any) -> _SessionConfigurationValue:
    fields: dict[str, Any] = {
        "model": _ModelRefValue(server_id=SERVER_ID_INT, model_name="llama-3"),
        "system_prompt": _SettingValue(
            session=None, inherited="Be terse.", inherited_level="character", value="Be terse.", level="character"
        ),
        "tool_memo_search": _SettingValue(
            session=None, inherited=True, inherited_level="default", value=True, level="default"
        ),
        "tool_session_search": _SettingValue(
            session=False, inherited=True, inherited_level="character", value=False, level="session"
        ),
        "tool_web_search": _SettingValue(
            session=None, inherited=False, inherited_level="character", value=False, level="character"
        ),
        "rp_language": _SettingValue(
            session="French", inherited="Japanese", inherited_level="user", value="French", level="session"
        ),
        "preferred_language": _SettingValue(
            session=None, inherited=None, inherited_level=None, value=None, level=None
        ),
    }
    fields.update(overrides)
    return _SessionConfigurationValue(**fields)


def _session_response(**overrides: Any) -> SessionConfigurationResponse:
    return SessionConfigurationResponse.model_validate(
        _session_configuration_value(**overrides), from_attributes=True
    )


# ==========================================================================================
# DoD-6: the two use-time errors
# ==========================================================================================


@pytest.mark.parametrize(("error_class", "code"), USE_TIME_ERRORS)
def test_use_time_error_is_a_domain_error_with_its_code_and_409__S017_001_DoD6(
    error_class: type[DomainError], code: str
) -> None:
    """017/001 DoD-6 — D2: a `DomainError`, its code, HTTP 409."""
    assert issubclass(error_class, DomainError)
    assert error_class.code == code
    assert error_class.http_status == 409


@pytest.mark.parametrize(("error_class", "code"), USE_TIME_ERRORS)
def test_use_time_error_raised_bare_has_a_message_and_empty_detail__S017_001_DoD6(
    error_class: type[DomainError], code: str
) -> None:
    """017/001 DoD-6 — D2: raised with no arguments it carries a fixed non-empty message and an
    empty `detail`."""
    error = error_class()
    assert isinstance(error, DomainError)
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


@pytest.mark.parametrize(("error_class", "code"), USE_TIME_ERRORS)
def test_use_time_error_from_a_route_answers_the_409_envelope__S017_001_DoD6(
    error_class: type[DomainError], code: str
) -> None:
    """017/001 DoD-6 — raised from a route, it answers 409 with
    `{"error": {"code": <code>, "message": <non-empty>, "detail": {}}}`."""
    response = TestClient(_app_raising(error_class())).get("/boom")

    assert response.status_code == 409
    payload = response.json()
    assert set(payload) == {"error"}
    error = payload["error"]
    assert set(error) == {"code", "message", "detail"}
    assert error["code"] == code
    assert isinstance(error["message"], str)
    assert error["message"].strip()
    assert error["detail"] == {}


# ==========================================================================================
# DoD-7: UpdateUserSettingsRequest
# ==========================================================================================


def test_user_settings_language_is_trimmed__S017_001_DoD7() -> None:
    """017/001 DoD-7 — D6: `{"rp_language": "  Japanese "}` parses to `"Japanese"`."""
    request = UpdateUserSettingsRequest.model_validate({"rp_language": "  Japanese "})
    assert request.rp_language == "Japanese"
    assert request.model_fields_set == {"rp_language"}


def test_user_settings_preferred_language_is_trimmed__S017_001_DoD7() -> None:
    """017/001 DoD-7 — D6: the same rule holds for `preferred_language`."""
    request = UpdateUserSettingsRequest.model_validate({"preferred_language": "\tEnglish  "})
    assert request.preferred_language == "English"
    assert request.model_fields_set == {"preferred_language"}


@pytest.mark.parametrize("field", LANGUAGE_FIELDS)
def test_user_settings_blank_language_parses_to_null_marked_as_sent__S017_001_DoD7(field: str) -> None:
    """017/001 DoD-7 — D6: an all-whitespace language parses to null, and the key is marked sent
    (so it clears the level rather than changing nothing)."""
    request = UpdateUserSettingsRequest.model_validate({field: "   "})
    assert getattr(request, field) is None
    assert field in request.model_fields_set


def test_user_settings_empty_string_language_parses_to_null_marked_as_sent__S017_001_DoD7() -> None:
    """017/001 DoD-7 — D6: `""` is blank too."""
    request = UpdateUserSettingsRequest.model_validate({"rp_language": ""})
    assert request.rp_language is None
    assert request.model_fields_set == {"rp_language"}


def test_user_settings_explicit_null_is_marked_as_sent__S017_001_DoD7() -> None:
    """017/001 DoD-7 — `{"preferred_language": null}` marks that key sent and null, and only it."""
    request = UpdateUserSettingsRequest.model_validate({"preferred_language": None})
    assert request.preferred_language is None
    assert request.model_fields_set == {"preferred_language"}


def test_user_settings_empty_body_marks_nothing_sent__S017_001_DoD7() -> None:
    """017/001 DoD-7 — `{}` marks nothing sent (explicit null is not the same as absent)."""
    request = UpdateUserSettingsRequest.model_validate({})
    assert request.model_fields_set == set()
    assert request.rp_language is None
    assert request.preferred_language is None


def test_user_settings_ignores_unknown_keys__S017_001_DoD7() -> None:
    """017/001 DoD-7 — unknown keys (`model`, `system_prompt`) are ignored: accepted, nothing
    marked sent, nothing extra on the parsed model."""
    request = UpdateUserSettingsRequest.model_validate(
        {"model": {"server_id": SERVER_ID_TEXT, "model_name": "llama-3"}, "system_prompt": "Be terse."}
    )
    assert request.model_fields_set == set()
    assert request.model_dump() == {"rp_language": None, "preferred_language": None}
    assert not hasattr(request, "system_prompt")


def test_user_settings_ignores_unknown_keys_beside_a_known_one__S017_001_DoD7() -> None:
    """017/001 DoD-7 — an unknown key beside a known one leaves the known one parsed normally."""
    request = UpdateUserSettingsRequest.model_validate({"system_prompt": "x", "rp_language": " Japanese"})
    assert request.model_fields_set == {"rp_language"}
    assert request.model_dump() == {"rp_language": "Japanese", "preferred_language": None}


# ==========================================================================================
# DoD-8: UpdateSessionConfigurationRequest (the prompt / tool / model-object rules are shared
# with the character request per DoD-9 and parametrised over both where DoD-9 says so)
# ==========================================================================================


@pytest.mark.parametrize("request_class", ASSISTANT_REQUESTS)
def test_model_parses_with_server_id_as_the_int__S017_001_DoD8(request_class: Any) -> None:
    """017/001 DoD-8 / DoD-9 — `{"model": {"server_id": "7250000000000000301", "model_name":
    "llama-3"}}` parses with `server_id` the int and the key marked sent."""
    request = request_class.model_validate({"model": {"server_id": SERVER_ID_TEXT, "model_name": "llama-3"}})
    assert request.model is not None
    assert request.model.server_id == SERVER_ID_INT
    assert isinstance(request.model.server_id, int)
    assert request.model.model_name == "llama-3"
    assert request.model_fields_set == {"model"}


@pytest.mark.parametrize("request_class", ASSISTANT_REQUESTS)
def test_model_name_is_kept_verbatim__S017_001_DoD8(request_class: Any) -> None:
    """017/001 DoD-8 / DoD-9 — Interface intent: a non-blank `model_name` is kept verbatim (it
    must match the registry's name exactly)."""
    request = request_class.model_validate({"model": {"server_id": SERVER_ID_TEXT, "model_name": " Qwen2.5:7b "}})
    assert request.model is not None
    assert request.model.model_name == " Qwen2.5:7b "


def test_session_model_null_fails_validation__S017_001_DoD8() -> None:
    """017/001 DoD-8 — D10: on the session request an explicit `model: null` fails (the
    session's model is only ever replaced)."""
    with pytest.raises(ValidationError):
        UpdateSessionConfigurationRequest.model_validate({"model": None})


def test_session_model_absent_is_accepted_and_not_sent__S017_001_DoD8() -> None:
    """017/001 DoD-8 — refusing null does not make `model` required: absent is fine."""
    request = UpdateSessionConfigurationRequest.model_validate({})
    assert "model" not in request.model_fields_set


@pytest.mark.parametrize("request_class", ASSISTANT_REQUESTS)
@pytest.mark.parametrize("model_name", ["", "  ", "\t\n"])
def test_model_with_a_blank_model_name_fails__S017_001_DoD8(request_class: Any, model_name: str) -> None:
    """017/001 DoD-8 / DoD-9 — a `model` whose `model_name` is blank fails."""
    with pytest.raises(ValidationError):
        request_class.model_validate({"model": {"server_id": SERVER_ID_TEXT, "model_name": model_name}})


@pytest.mark.parametrize("request_class", ASSISTANT_REQUESTS)
def test_model_without_a_model_name_fails__S017_001_DoD8(request_class: Any) -> None:
    """017/001 DoD-8 / DoD-9 — Wire contract: `model` is set as a whole object; no
    `model_name` fails."""
    with pytest.raises(ValidationError):
        request_class.model_validate({"model": {"server_id": SERVER_ID_TEXT}})


@pytest.mark.parametrize("request_class", ASSISTANT_REQUESTS)
@pytest.mark.parametrize("server_id", ["not-a-number", "12ab", ""])
def test_model_with_a_non_numeric_server_id_fails__S017_001_DoD8(request_class: Any, server_id: str) -> None:
    """017/001 DoD-8 / DoD-9 — a `model` with a non-numeric `server_id` fails."""
    with pytest.raises(ValidationError):
        request_class.model_validate({"model": {"server_id": server_id, "model_name": "llama-3"}})


@pytest.mark.parametrize("request_class", ASSISTANT_REQUESTS)
def test_system_prompt_is_kept_verbatim__S017_001_DoD8(request_class: Any) -> None:
    """017/001 DoD-8 / DoD-9 — D6: `{"system_prompt": "  Be terse.\\n"}` keeps those exact
    characters (whitespace can be content)."""
    request = request_class.model_validate({"system_prompt": "  Be terse.\n"})
    assert request.system_prompt == "  Be terse.\n"
    assert request.model_fields_set == {"system_prompt"}


@pytest.mark.parametrize("request_class", ASSISTANT_REQUESTS)
@pytest.mark.parametrize("blank", [" \n", "", "\t"])
def test_blank_system_prompt_parses_to_null_marked_as_sent__S017_001_DoD8(request_class: Any, blank: str) -> None:
    """017/001 DoD-8 / DoD-9 — D6: a blank system prompt (`" \\n"`) parses to null, marked as sent."""
    request = request_class.model_validate({"system_prompt": blank})
    assert request.system_prompt is None
    assert "system_prompt" in request.model_fields_set


@pytest.mark.parametrize("request_class", ASSISTANT_REQUESTS)
def test_system_prompt_explicit_null_is_marked_as_sent__S017_001_DoD8(request_class: Any) -> None:
    """017/001 DoD-8 / DoD-9 — Request rules: an explicit null clears the level: sent and null."""
    request = request_class.model_validate({"system_prompt": None})
    assert request.system_prompt is None
    assert request.model_fields_set == {"system_prompt"}


@pytest.mark.parametrize("request_class", ASSISTANT_REQUESTS)
def test_one_tool_false_sets_only_that_key__S017_001_DoD8(request_class: Any) -> None:
    """017/001 DoD-8 / DoD-9 — `{"tool_web_search": false}` sets only that key."""
    request = request_class.model_validate({"tool_web_search": False})
    assert request.tool_web_search is False
    assert request.model_fields_set == {"tool_web_search"}


@pytest.mark.parametrize("request_class", ASSISTANT_REQUESTS)
@pytest.mark.parametrize("field", TOOL_FIELDS)
def test_each_tool_accepts_true_false_and_null__S017_001_DoD8(request_class: Any, field: str) -> None:
    """017/001 DoD-8 / DoD-9 — each of the three tools is an optional, nullable boolean."""
    for value in (True, False, None):
        request = request_class.model_validate({field: value})
        assert getattr(request, field) is value
        assert request.model_fields_set == {field}


@pytest.mark.parametrize("request_class", ASSISTANT_REQUESTS)
def test_tool_explicit_null_is_marked_as_sent__S017_001_DoD8(request_class: Any) -> None:
    """017/001 DoD-8 / DoD-9 — `{"tool_memo_search": null}` marks it sent and null."""
    request = request_class.model_validate({"tool_memo_search": None})
    assert request.tool_memo_search is None
    assert request.model_fields_set == {"tool_memo_search"}


@pytest.mark.parametrize("request_class", ASSISTANT_REQUESTS)
@pytest.mark.parametrize("field", TOOL_FIELDS)
def test_tool_given_a_string_fails__S017_001_DoD8(request_class: Any, field: str) -> None:
    """017/001 DoD-8 / DoD-9 — `{"tool_memo_search": "yes"}` fails (a non-boolean tool value
    is a 422)."""
    with pytest.raises(ValidationError):
        request_class.model_validate({field: "yes"})


@pytest.mark.parametrize("request_class", ASSISTANT_REQUESTS)
@pytest.mark.parametrize("field", TOOL_FIELDS)
def test_tool_given_a_json_string_on_the_wire_fails__S017_001_DoD8(request_class: Any, field: str) -> None:
    """017/001 DoD-8 / DoD-9 — the same holds for a body parsed from JSON text."""
    with pytest.raises(ValidationError):
        request_class.model_validate_json(json.dumps({field: "yes"}))


def test_session_languages_are_trimmed__S017_001_DoD8() -> None:
    """017/001 DoD-8 — languages trim as in DoD-7."""
    request = UpdateSessionConfigurationRequest.model_validate(
        {"rp_language": "  Japanese ", "preferred_language": " English\n"}
    )
    assert request.rp_language == "Japanese"
    assert request.preferred_language == "English"
    assert request.model_fields_set == {"rp_language", "preferred_language"}


@pytest.mark.parametrize("field", LANGUAGE_FIELDS)
def test_session_blank_language_parses_to_null_marked_as_sent__S017_001_DoD8(field: str) -> None:
    """017/001 DoD-8 — as in DoD-7: blank -> null, key marked sent."""
    request = UpdateSessionConfigurationRequest.model_validate({field: "   "})
    assert getattr(request, field) is None
    assert request.model_fields_set == {field}


@pytest.mark.parametrize("field", LANGUAGE_FIELDS)
def test_session_language_explicit_null_is_marked_as_sent__S017_001_DoD8(field: str) -> None:
    """017/001 DoD-8 — as in DoD-7: explicit null is sent and null."""
    request = UpdateSessionConfigurationRequest.model_validate({field: None})
    assert getattr(request, field) is None
    assert request.model_fields_set == {field}


def test_session_empty_body_marks_nothing_sent__S017_001_DoD8() -> None:
    """017/001 DoD-8 — which keys were sent is recoverable: `{}` marks none."""
    request = UpdateSessionConfigurationRequest.model_validate({})
    assert request.model_fields_set == set()


def test_session_ignores_unknown_keys__S017_001_DoD8() -> None:
    """017/001 DoD-8 — Interface intent: unknown keys are ignored."""
    request = UpdateSessionConfigurationRequest.model_validate({"title": "Night", "tools": ["web"]})
    assert request.model_fields_set == set()


def test_session_full_body_marks_every_key_sent__S017_001_DoD8() -> None:
    """017/001 DoD-8 — all seven keys at once parse, each by its own rule, all marked sent."""
    request = UpdateSessionConfigurationRequest.model_validate(
        {
            "model": {"server_id": OTHER_SERVER_ID_TEXT, "model_name": "llama-3"},
            "system_prompt": "  Be terse.\n",
            "tool_memo_search": None,
            "tool_session_search": True,
            "tool_web_search": False,
            "rp_language": " French ",
            "preferred_language": "  ",
        }
    )
    assert request.model_fields_set == SESSION_CONFIGURATION_KEYS
    assert request.model is not None
    assert request.model.server_id == OTHER_SERVER_ID_INT
    assert request.model.model_name == "llama-3"
    assert request.system_prompt == "  Be terse.\n"
    assert request.tool_memo_search is None
    assert request.tool_session_search is True
    assert request.tool_web_search is False
    assert request.rp_language == "French"
    assert request.preferred_language is None


# ==========================================================================================
# DoD-9: UpdateCharacterConfigurationRequest
# ==========================================================================================


def test_character_model_null_parses_as_sent_and_null__S017_001_DoD9() -> None:
    """017/001 DoD-9 — D10: `{"model": null}` on the character request is accepted: sent and
    null (clear the override)."""
    request = UpdateCharacterConfigurationRequest.model_validate({"model": None})
    assert request.model is None
    assert request.model_fields_set == {"model"}


def test_character_model_absent_is_not_sent__S017_001_DoD9() -> None:
    """017/001 DoD-9 — absent `model` is distinguishable from an explicit null."""
    request = UpdateCharacterConfigurationRequest.model_validate({})
    assert request.model is None
    assert request.model_fields_set == set()


def test_character_request_drops_both_language_keys__S017_001_DoD9() -> None:
    """017/001 DoD-9 — US-061.AC-3: `{"rp_language": "French", "preferred_language": "English"}`
    parses with nothing sent and no language attribute on the model."""
    request = UpdateCharacterConfigurationRequest.model_validate(
        {"rp_language": "French", "preferred_language": "English"}
    )
    assert request.model_fields_set == set()
    assert not hasattr(request, "rp_language")
    assert not hasattr(request, "preferred_language")
    dumped = request.model_dump()
    assert "rp_language" not in dumped
    assert "preferred_language" not in dumped


def test_character_request_drops_languages_beside_known_keys__S017_001_DoD9() -> None:
    """017/001 DoD-9 — a language key sent beside an assistant key changes nothing of its own."""
    request = UpdateCharacterConfigurationRequest.model_validate(
        {"rp_language": "French", "tool_web_search": True}
    )
    assert request.model_fields_set == {"tool_web_search"}
    assert request.tool_web_search is True
    assert not hasattr(request, "rp_language")


def test_character_request_declares_exactly_the_five_assistant_fields__S017_001_DoD9() -> None:
    """017/001 DoD-9 — R1 by shape: the character request carries model, system prompt and the
    three tools, and no language."""
    assert set(UpdateCharacterConfigurationRequest.model_fields) == CHARACTER_CONFIGURATION_KEYS


# ==========================================================================================
# DoD-10: the response models on the wire
# ==========================================================================================


def test_session_configuration_serialises_model_server_id_as_a_decimal_string__S017_001_DoD10() -> None:
    """017/001 DoD-10 — built from values carrying an int `server_id`, `model.server_id`
    serialises as its decimal string."""
    wire = _wire(_session_response())
    assert wire["model"] == {"server_id": SERVER_ID_TEXT, "model_name": "llama-3"}
    assert isinstance(wire["model"]["server_id"], str)


def test_session_configuration_serialises_a_null_model_as_json_null__S017_001_DoD10() -> None:
    """017/001 DoD-10 — `model` null serialises as JSON `null` (the key is present)."""
    response = _session_response(model=None)
    wire = _wire(response)
    assert "model" in wire
    assert wire["model"] is None
    assert '"model":null' in response.model_dump_json()


def test_session_configuration_has_exactly_the_seven_wire_keys__S017_001_DoD10() -> None:
    """017/001 DoD-10 — the top level has exactly the seven keys of the Wire contract."""
    assert set(_wire(_session_response())) == SESSION_CONFIGURATION_KEYS
    assert set(_wire(_session_response(model=None))) == SESSION_CONFIGURATION_KEYS


@pytest.mark.parametrize("field", sorted(SESSION_CONFIGURATION_KEYS - {"model"}))
def test_each_setting_serialises_exactly_its_five_keys__S017_001_DoD10(field: str) -> None:
    """017/001 DoD-10 — each setting serialises exactly session, inherited, inherited_level,
    value, level."""
    wire = _wire(_session_response())
    assert set(wire[field]) == SETTING_KEYS


def test_settings_carry_their_values_through_to_the_wire__S017_001_DoD10() -> None:
    """017/001 DoD-10 — nested settings are built by attribute and serialised as given: text
    settings as strings or null, boolean settings as JSON booleans, levels as their strings."""
    wire = _wire(_session_response())
    assert wire["system_prompt"] == {
        "session": None,
        "inherited": "Be terse.",
        "inherited_level": "character",
        "value": "Be terse.",
        "level": "character",
    }
    assert wire["tool_memo_search"] == {
        "session": None,
        "inherited": True,
        "inherited_level": "default",
        "value": True,
        "level": "default",
    }
    assert wire["tool_session_search"] == {
        "session": False,
        "inherited": True,
        "inherited_level": "character",
        "value": False,
        "level": "session",
    }
    assert wire["rp_language"] == {
        "session": "French",
        "inherited": "Japanese",
        "inherited_level": "user",
        "value": "French",
        "level": "session",
    }
    assert wire["preferred_language"] == {
        "session": None,
        "inherited": None,
        "inherited_level": None,
        "value": None,
        "level": None,
    }


def test_setting_with_an_unknown_level_is_refused__S017_001_DoD10() -> None:
    """017/001 DoD-10 — Interface intent: `level` is the level literal or null; any other
    string is not a level."""
    bogus = _SettingValue(session=None, inherited="x", inherited_level="global", value="x", level="global")
    with pytest.raises(ValidationError):
        SessionConfigurationResponse.model_validate(
            _session_configuration_value(system_prompt=bogus), from_attributes=True
        )


def test_level_literal_names_exactly_the_four_levels__S017_001_DoD10() -> None:
    """017/001 DoD-10 — Wire contract `Level`: exactly session, character, user, default."""
    values = typing.get_args(ConfigurationLevel)
    assert len(values) == len(set(values))
    assert set(values) == {"session", "character", "user", "default"}


def test_enabled_model_list_serialises_models_with_exactly_three_keys__S017_001_DoD10() -> None:
    """017/001 DoD-10 — `{ "models": [...] }`, each item exactly server_id (string),
    server_name, model_name."""
    response = EnabledModelListResponse(
        models=[
            EnabledModelResponse(server_id=SERVER_ID_INT, server_name="local", model_name="llama-3"),
            EnabledModelResponse(server_id=OTHER_SERVER_ID_INT, server_name="remote", model_name="qwen"),
        ]
    )
    wire = _wire(response)
    assert set(wire) == {"models"}
    assert wire["models"] == [
        {"server_id": SERVER_ID_TEXT, "server_name": "local", "model_name": "llama-3"},
        {"server_id": OTHER_SERVER_ID_TEXT, "server_name": "remote", "model_name": "qwen"},
    ]
    for item in wire["models"]:
        assert set(item) == ENABLED_MODEL_KEYS
        assert isinstance(item["server_id"], str)


def test_enabled_model_list_serialises_an_empty_list__S017_001_DoD10() -> None:
    """017/001 DoD-10 — Wire contract: `[]` when none is enabled."""
    assert _wire(EnabledModelListResponse(models=[])) == {"models": []}


def test_character_configuration_has_exactly_its_five_keys__S017_001_DoD10() -> None:
    """017/001 DoD-10 — built from a value by attribute: exactly model, system_prompt and the
    three tools; `model.server_id` a decimal string."""
    value = _CharacterConfigurationValue(
        model=_ModelRefValue(server_id=SERVER_ID_INT, model_name="llama-3"),
        system_prompt="Be terse.",
        tool_memo_search=True,
        tool_session_search=None,
        tool_web_search=False,
    )
    wire = _wire(CharacterConfigurationResponse.model_validate(value, from_attributes=True))
    assert set(wire) == CHARACTER_CONFIGURATION_KEYS
    assert wire == {
        "model": {"server_id": SERVER_ID_TEXT, "model_name": "llama-3"},
        "system_prompt": "Be terse.",
        "tool_memo_search": True,
        "tool_session_search": None,
        "tool_web_search": False,
    }


def test_character_configuration_with_nothing_set_serialises_nulls__S017_001_DoD10() -> None:
    """017/001 DoD-10 — no override at all: every one of the five keys is present and null."""
    value = _CharacterConfigurationValue(
        model=None, system_prompt=None, tool_memo_search=None, tool_session_search=None, tool_web_search=None
    )
    wire = _wire(CharacterConfigurationResponse.model_validate(value, from_attributes=True))
    assert wire == {key: None for key in CHARACTER_CONFIGURATION_KEYS}
