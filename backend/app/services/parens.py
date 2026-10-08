"""The `(( ))` parser — classify a message text and strip its instruction fragments.

Feature `012`, step `003` (D8). Two pure functions over `str`: no I/O, no connection, no
`user_id`, and no imports from `app`, `sqlalchemy` or `fastapi` (`backend-structure.md`
"The `(( ))` seam"). Settle (`app.services.settle`) is the only caller and decides which of
the two applies: a decision is filed verbatim, a turn has its fragments stripped.
"""

import re
from typing import Literal

Kind = Literal["turn", "decision"]
"""What `classify` returns, and the `kind` a settled head is stamped with."""

_FRAGMENT = re.compile(r"\(\(.*?\)\)", re.DOTALL)
"""The shortest `((`...`))` span, which may cross line breaks."""

_FRAGMENT_WITH_LEAD = re.compile(r"[ \t]*\(\(.*?\)\)", re.DOTALL)
"""A fragment together with the run of spaces and tabs immediately before it."""

_BLANK_LINE_RUN = re.compile(r"\n(?:[ \t]*\n){2,}")
"""Three or more line breaks separated only by spaces and tabs."""


def classify(text: str) -> Kind:
    """`"decision"` iff the trimmed text starts with `((` and ends with `))`, else `"turn"`."""
    trimmed = text.strip()
    if trimmed.startswith("((") and trimmed.endswith("))"):
        return "decision"
    return "turn"


def strip_fragments(text: str) -> str:
    """Remove every `((...))` fragment and tidy whitespace; return `text` unchanged when none."""
    if _FRAGMENT.search(text) is None:
        return text
    stripped = _FRAGMENT_WITH_LEAD.sub("", text)
    stripped = _BLANK_LINE_RUN.sub("\n\n", stripped)
    return stripped.strip()
