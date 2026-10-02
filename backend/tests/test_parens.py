"""Tests for `app/services/parens.py` — feature 012, step 003 (DoD-1..6).

Every expected value comes from `docs/plans/012.messages-and-settle/003.parser-and-settle.md`
(its Definition of done) and from `003.context.md` "The parser, as spec" (D8). No expected
value is computed by calling the parser. Each test name ends `__S012_003_DoD<n>` with the
DoD item it covers.
"""

import ast
from pathlib import Path

import pytest

from app.services import parens as parens_module
from app.services.parens import classify, strip_fragments

# --- DoD-1: decisions ---------------------------------------------------------------------

DECISIONS = [
    "((I need to step away for a bit))",
    "  ((ooc))  \n",
    "((first line\nsecond line))",
    "((one)) ((two))",
    "((a)) prose ((b))",
    "(())",
    # Further decisions the spec lists ("The parser, as spec").
    "((x))",
    "(((x)))",
]


@pytest.mark.parametrize("text", DECISIONS)
def test_classify_wholly_parenthesised_text_is_a_decision__S012_003_DoD1(text: str) -> None:
    """DoD-1 — after trimming, starts with `((` and ends with `))` → decision."""
    assert classify(text) == "decision"


# --- DoD-2: turns -------------------------------------------------------------------------

TURNS = [
    "She walks in.",
    "She walks. ((be dramatic)) Then sits.",
    "((hint)) She walks.",
    "She walks. ((x))",
    "(( never closed",
    "a single (paren) pair",
    "",
]


@pytest.mark.parametrize("text", TURNS)
def test_classify_anything_else_is_a_turn__S012_003_DoD2(text: str) -> None:
    """DoD-2 — a text that does not both start with `((` and end with `))` (trimmed) is a
    turn, including the empty text."""
    assert classify(text) == "turn"


# --- DoD-3: no fragment → unchanged -------------------------------------------------------

UNCHANGED = [
    "  She  walks.\n\n\n\nShe sits.  ",
    "(( never closed",
    # Further fragment-free texts under the same rule (spec rule 1).
    "",
    "She walks in.",
    "a single (paren) pair",
    "x )) y",
    "\t  leading and trailing whitespace \n\n",
]


@pytest.mark.parametrize("text", UNCHANGED)
def test_strip_fragments_returns_fragment_free_text_unchanged__S012_003_DoD3(text: str) -> None:
    """DoD-3 — with no fragment the text comes back byte-for-byte: outer whitespace,
    internal double spaces and runs of blank lines all kept (US-135.AC-1 "as-is")."""
    assert strip_fragments(text) == text


# --- DoD-4: stripping examples ------------------------------------------------------------

STRIP_EXAMPLES = [
    ("She walks. ((be dramatic)) Then sits.", "She walks. Then sits."),
    ("((hint)) She walks.", "She walks."),
    ("She walks ((x)), then sits.", "She walks, then sits."),
    ("She walks. ((x))", "She walks."),
    ("Text ((note\nspanning)) more", "Text more"),
    ("Para one.\n\n((instruction))\n\nPara two.", "Para one.\n\nPara two."),
]


@pytest.mark.parametrize(("text", "expected"), STRIP_EXAMPLES)
def test_strip_fragments_dod_examples__S012_003_DoD4(text: str, expected: str) -> None:
    """DoD-4 — the DoD's worked examples (US-130.AC-1)."""
    assert strip_fragments(text) == expected


SPEC_RULE_EXAMPLES = [
    # Rule 2: the run of spaces *and tabs* before a fragment goes with it.
    ("a\t \t((x)) b", "a b"),
    # Rule 2: line breaks before a fragment are not removed.
    ("Line one.\n((x))\nLine two.", "Line one.\n\nLine two."),
    # Every fragment is removed, left to right.
    ("a ((x)) b ((y)) c", "a b c"),
    # Shortest span: a fragment ends at the first `))` after its `((`.
    ("a ((x)) b)) c", "a b)) c"),
    # Rule 3: three or more `\n` separated only by spaces / tabs collapse to `\n\n`.
    ("A\n \n\t\nB ((x))", "A\n\nB"),
    # Rule 3: exactly one blank line is left as it is.
    ("A\n\nB ((x))", "A\n\nB"),
    # Rule 4: the whole result is trimmed.
    ("  \n((x)) She walks.  \n", "She walks."),
]


@pytest.mark.parametrize(("text", "expected"), SPEC_RULE_EXAMPLES)
def test_strip_fragments_applies_the_stated_tidy_up__S012_003_DoD4(text: str, expected: str) -> None:
    """DoD-4 — the stripping rules of "The parser, as spec": fragment plus the preceding
    spaces/tabs removed, shortest span, blank-line runs collapsed, result trimmed."""
    assert strip_fragments(text) == expected


# --- DoD-5: malformed turns never strip to empty ------------------------------------------

MALFORMED = [
    ("((a)) ((", "(("),
    ("x ((a))", "x"),
]


@pytest.mark.parametrize(("text", "expected"), MALFORMED)
def test_malformed_turn_strips_to_non_empty_text__S012_003_DoD5(text: str, expected: str) -> None:
    """DoD-5 — an unbalanced `((` and text outside every fragment survive stripping."""
    assert strip_fragments(text) == expected


@pytest.mark.parametrize(("text", "expected"), MALFORMED)
def test_malformed_turn_classifies_as_turn__S012_003_DoD5(text: str, expected: str) -> None:
    """DoD-5 — both malformed texts are turns, not decisions."""
    del expected
    assert classify(text) == "turn"


# --- DoD-6: the parser imports nothing from app / sqlalchemy / fastapi --------------------

_FORBIDDEN_ROOTS = ("app", "sqlalchemy", "fastapi")


def _is_forbidden(module: str) -> bool:
    return any(module == root or module.startswith(f"{root}.") for root in _FORBIDDEN_ROOTS)


def test_parser_source_imports_nothing_from_app_sqlalchemy_or_fastapi__S012_003_DoD6() -> None:
    """DoD-6 — read `app/services/parens.py` from disk; no absolute import from `app`,
    `sqlalchemy` or `fastapi`, and no relative import (which could only reach `app`)."""
    module_file = parens_module.__file__
    assert module_file is not None
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))

    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level > 0 or _is_forbidden(module):
                offenders.append(ast.unparse(node))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden(alias.name):
                    offenders.append(ast.unparse(node))

    assert offenders == []
