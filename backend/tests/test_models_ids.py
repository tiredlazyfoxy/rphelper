"""Tests for ``app.models.ids`` — the JSON id boundary.

Every expected value here comes from ``004.ids-and-json-boundary.md`` (Definition of
done), ``004.context.md`` § "Why the string boundary is not a style preference" and
``context.md`` § "The JSON id boundary": an id is an ``int`` in Python and a **decimal
string** in every JSON payload. Covers DoD-7 .. DoD-9.

The aliases are imported from the module that declares them, so that a missing
re-export fails only DoD-9's own tests rather than collecting the whole file away.
"""

import json

import pytest
from pydantic import BaseModel

import app.models as models_package
import app.models.ids as ids_module
from app.models.ids import SnowflakeIn, SnowflakeOut

# JavaScript's Number.MAX_SAFE_INTEGER; a JSON number beyond it rounds in a JS client.
MAX_SAFE_INTEGER = 2**53 - 1

# The first integer above the ceiling that a float64 cannot represent, and a realistic
# 63-bit snowflake. Both are compared digit for digit, never as floats.
UNSAFE_ID = MAX_SAFE_INTEGER + 2
SNOWFLAKE_ID = 7_312_345_678_901_234_567

ABOVE_THE_CEILING = [UNSAFE_ID, SNOWFLAKE_ID]


class OutboundModel(BaseModel):
    """A model whose id field uses the outbound alias."""

    id: SnowflakeOut


class InboundModel(BaseModel):
    """A model whose id field uses the inbound alias."""

    id: SnowflakeIn


# --------------------------------------------------------------------------- DoD-7


def test_outbound_field_serialises_to_a_decimal_string__DoD7() -> None:
    """DoD-7: an outbound-alias field lands on the wire as a JSON decimal string."""
    payload = json.loads(OutboundModel(id=12345).model_dump_json())
    assert isinstance(payload["id"], str)
    assert payload["id"] == "12345"


@pytest.mark.parametrize("value", ABOVE_THE_CEILING)
def test_value_above_the_safe_integer_is_quoted_in_the_json_text__DoD7(value: int) -> None:
    """DoD-7: the serialised text carries the digits quoted, never as a JSON number."""
    assert value > MAX_SAFE_INTEGER
    text = OutboundModel(id=value).model_dump_json()
    assert f'"{value}"' in text


@pytest.mark.parametrize("value", ABOVE_THE_CEILING)
def test_value_above_the_safe_integer_keeps_every_digit_on_the_wire__DoD7(value: int) -> None:
    """DoD-7: a value above Number.MAX_SAFE_INTEGER survives with every digit intact."""
    assert value > MAX_SAFE_INTEGER
    payload = json.loads(OutboundModel(id=value).model_dump_json())
    assert isinstance(payload["id"], str)
    assert payload["id"] == str(value)


@pytest.mark.parametrize("value", ABOVE_THE_CEILING)
def test_value_above_the_safe_integer_survives_the_round_trip__DoD7(value: int) -> None:
    """DoD-7: out to JSON and back in yields exactly the original integer."""
    payload = json.loads(OutboundModel(id=value).model_dump_json())
    returned = InboundModel(id=payload["id"])
    assert returned.id == value


# --------------------------------------------------------------------------- DoD-8


def test_inbound_field_accepts_a_decimal_string_and_yields_an_int__DoD8() -> None:
    """DoD-8: an inbound-alias field parses a decimal string into an ``int``."""
    model = InboundModel(id="12345")
    assert model.id == 12345
    assert isinstance(model.id, int)
    assert not isinstance(model.id, str)


@pytest.mark.parametrize("value", ABOVE_THE_CEILING)
def test_inbound_field_parses_a_string_above_the_safe_integer__DoD8(value: int) -> None:
    """DoD-8: a decimal string beyond the safe-integer ceiling parses digit for digit."""
    model = InboundModel(id=str(value))
    assert model.id == value
    assert isinstance(model.id, int)


def test_inbound_field_accepts_an_int_unchanged__DoD8() -> None:
    """DoD-8: an ``int`` is accepted as it stands."""
    model = InboundModel(id=12345)
    assert model.id == 12345
    assert isinstance(model.id, int)


@pytest.mark.parametrize("value", ABOVE_THE_CEILING)
def test_inbound_field_accepts_a_large_int_unchanged__DoD8(value: int) -> None:
    """DoD-8: a large ``int`` passes through with every digit intact."""
    assert InboundModel(id=value).id == value


def test_inbound_field_parses_a_string_from_a_json_body__DoD8() -> None:
    """DoD-8: validation from a parsed JSON body behaves the same as construction."""
    model = InboundModel.model_validate(json.loads('{"id": "9007199254740993"}'))
    assert model.id == 9007199254740993
    assert isinstance(model.id, int)


# --------------------------------------------------------------------------- DoD-9


@pytest.mark.parametrize("name", ["SnowflakeIn", "SnowflakeOut"])
def test_alias_is_importable_from_the_models_package__DoD9(name: str) -> None:
    """DoD-9: both aliases are reachable from ``app.models``, not only from its module."""
    assert hasattr(models_package, name)
    assert getattr(models_package, name) is getattr(ids_module, name)
