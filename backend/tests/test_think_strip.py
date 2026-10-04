"""Tests for `strip_think` in `app/services/llm/chat.py` — feature 021, step 001 (DoD-9).

Every expected value comes from `docs/plans/021.compose-loop-and-tools/context.md` **D4**
(the strip rule and its worked-examples table) and the "Literals" table (`<think>` /
`</think>`). Bindings come from `status.md` `## Skeleton`, Step 001:
`strip_think(text: str) -> str`, `THINK_OPEN`, `THINK_CLOSE`.

Each test name ends `__S021_001_DoD<n>`.
"""

import pytest

from app.services.llm.chat import THINK_CLOSE, THINK_OPEN, strip_think

#: context.md D4 "Worked examples" — (input, output), verbatim.
WORKED_EXAMPLES: list[tuple[str, str]] = [
    ("<think>plan</think>\n\nHello", "Hello"),
    ("Hello", "Hello"),
    ("  Hello  ", "  Hello  "),
    ("<think>a</think>One<think>b</think> two", "One two"),
    ("Start<think>never closed", "Start"),
    ("<think>only</think>", ""),
    ("a </think> b", "a </think> b"),
    ("<think>x\ny</think>\n((ooc))", "((ooc))"),
]


@pytest.mark.parametrize(
    ("text", "expected"),
    WORKED_EXAMPLES,
    ids=[
        "block_then_blank_lines",
        "no_block",
        "no_block_whitespace_kept",
        "two_blocks",
        "unterminated",
        "only_a_block",
        "stray_close",
        "block_then_parens",
    ],
)
def test_strip_think_maps_each_worked_example__S021_001_DoD9(text: str, expected: str) -> None:
    """DoD-9 — D4: every row of the worked-examples table maps exactly."""
    assert strip_think(text) == expected


def test_the_tag_literals_are_the_convention__S021_001_DoD9() -> None:
    """DoD-9 — D4 / Literals: the tags are exactly `<think>` and `</think>`."""
    assert THINK_OPEN == "<think>"
    assert THINK_CLOSE == "</think>"
