"""Feature 021 step 004 — the three tool declarations (`app/services/tools/definitions.py`).

Expected values come from `docs/plans/021.compose-loop-and-tools/004.tool-seam.md`
(Interface intent + DoD-1, DoD-10's `definitions.py` clause) and the feature `context.md`
(D5 names and offered order, D6 "tools never receive ids from the model", the Literals table).
Bindings come from `status.md` `## Skeleton` -> Step 004:

- `MEMO_SEARCH_NAME`, `SESSION_SEARCH_NAME`, `WEB_SEARCH_NAME`
- `MEMO_SEARCH`, `SESSION_SEARCH`, `WEB_SEARCH`: `ToolDeclaration` (`Mapping[str, object]`)
- `TOOL_DECLARATIONS: tuple[ToolDeclaration, ...]`

No database is needed.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from app.services.tools import definitions as definitions_module
from app.services.tools.definitions import (
    MEMO_SEARCH,
    MEMO_SEARCH_NAME,
    SESSION_SEARCH,
    SESSION_SEARCH_NAME,
    TOOL_DECLARATIONS,
    WEB_SEARCH,
    WEB_SEARCH_NAME,
)

#: D5 / Literals — the three names, in offered order.
EXPECTED_NAMES = ["memo_search", "session_search", "web_search"]

#: DoD-1 — words no declaration's parameters may mention (R9, D6: no ids from the model).
FORBIDDEN_WORDS = ["user_id", "session_id", "character_id", "setup_id", "scope"]


def _as_dict(value: object) -> dict[str, Any]:
    assert isinstance(value, Mapping), f"expected a mapping, got {type(value).__name__}"
    return dict(value)


def _function(declaration: object) -> dict[str, Any]:
    return _as_dict(_as_dict(declaration)["function"])


def _parameters(declaration: object) -> dict[str, Any]:
    return _as_dict(_function(declaration)["parameters"])


# =========================================================================================
# DoD-1: exactly three declarations, ordered, OpenAI tool shape, query-only parameters
# =========================================================================================


def test_name_constants_are_the_three_literals__S021_004_DoD1() -> None:
    """DoD-1 / Literals — the three tool names."""
    assert MEMO_SEARCH_NAME == "memo_search"
    assert SESSION_SEARCH_NAME == "session_search"
    assert WEB_SEARCH_NAME == "web_search"


def test_declarations_are_exactly_three_in_declaration_order__S021_004_DoD1() -> None:
    """DoD-1 / D5 — three declarations, ordered memo_search, session_search, web_search."""
    assert len(TOOL_DECLARATIONS) == 3
    assert [_function(declaration)["name"] for declaration in TOOL_DECLARATIONS] == EXPECTED_NAMES


def test_each_named_declaration_is_the_ordered_collections_member__S021_004_DoD1() -> None:
    """DoD-1 — `MEMO_SEARCH`, `SESSION_SEARCH`, `WEB_SEARCH` are the collection's members, in
    that order, and each carries its own name."""
    assert list(TOOL_DECLARATIONS) == [MEMO_SEARCH, SESSION_SEARCH, WEB_SEARCH]
    assert _function(MEMO_SEARCH)["name"] == "memo_search"
    assert _function(SESSION_SEARCH)["name"] == "session_search"
    assert _function(WEB_SEARCH)["name"] == "web_search"


@pytest.mark.parametrize("index", [0, 1, 2], ids=EXPECTED_NAMES)
def test_each_declaration_has_the_openai_function_shape__S021_004_DoD1(index: int) -> None:
    """DoD-1 — `{"type": "function", "function": {name, description, parameters}}`; the name
    matches; the description is a non-empty string; JSON-ready."""
    declaration = _as_dict(TOOL_DECLARATIONS[index])

    assert set(declaration) == {"type", "function"}
    assert declaration["type"] == "function"
    function = _function(declaration)
    assert set(function) == {"name", "description", "parameters"}
    assert function["name"] == EXPECTED_NAMES[index]
    assert isinstance(function["description"], str)
    assert function["description"].strip() != ""
    # JSON-ready: serialises with the stdlib encoder and round-trips to the same name.
    round_tripped = json.loads(json.dumps(declaration))
    assert round_tripped["type"] == "function"
    assert round_tripped["function"]["name"] == EXPECTED_NAMES[index]


@pytest.mark.parametrize("index", [0, 1, 2], ids=EXPECTED_NAMES)
def test_each_declaration_takes_exactly_one_required_string_query__S021_004_DoD1(
    index: int,
) -> None:
    """DoD-1 — `parameters`: type `object`, `properties` with exactly the key `query` (type
    `string`, with a description), `required` `["query"]`."""
    parameters = _parameters(TOOL_DECLARATIONS[index])

    assert parameters["type"] == "object"
    properties = _as_dict(parameters["properties"])
    assert list(properties) == ["query"]
    query = _as_dict(properties["query"])
    assert query["type"] == "string"
    assert isinstance(query.get("description"), str)
    assert query["description"].strip() != ""
    assert list(parameters["required"]) == ["query"]


@pytest.mark.parametrize("index", [0, 1, 2], ids=EXPECTED_NAMES)
def test_no_declaration_parameters_mention_an_id_or_scope__S021_004_DoD1(index: int) -> None:
    """DoD-1 / R9 / D6 — no declaration's parameters mention `user_id`, `session_id`,
    `character_id`, `setup_id` or `scope` anywhere (keys or values)."""
    serialised = json.dumps(_parameters(TOOL_DECLARATIONS[index]))

    for word in FORBIDDEN_WORDS:
        assert word not in serialised, word


# =========================================================================================
# DoD-10 (definitions.py clause): imports nothing from `app`
# =========================================================================================


def test_definitions_module_imports_nothing_from_app__S021_004_DoD10() -> None:
    """DoD-10 / D15 — `definitions.py` imports nothing from `app` (absolute or relative)."""
    module_file = definitions_module.__file__
    assert module_file is not None
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))

    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level > 0 or module == "app" or module.startswith("app."):
                offenders.append("." * node.level + module)
        elif isinstance(node, ast.Import):
            offenders.extend(
                alias.name
                for alias in node.names
                if alias.name == "app" or alias.name.startswith("app.")
            )
    assert offenders == []
