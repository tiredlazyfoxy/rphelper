"""The web search port's contract — one result value and one provider protocol.

Feature `028`, step `001` (D4). This module is the shape of a web lookup and nothing else:

- **`WebResult`** — one result, three plain-text strings (`title`, `url`, `snippet`).
- **`WebSearchProvider`** — the seam every provider implements structurally: one async
  `search`, returning the results in provider order or raising.

**A shape by contract.** No HTTP is made here: the module imports no `httpx`, no `fastapi`
and nothing from `app.config`, `app.secrets`, `app.db` or `app.services.tools`, so replacing
the provider (D1's is Google's, closed to new customers) touches `google.py` and the factory
in `app/services/tools/web_search.py` only.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WebResult:
    """One web search result, as plain text — never HTML, and never whitespace-normalised here."""

    title: str
    """The result's title. Empty when the provider gave none."""
    url: str
    """The result's link. Always a non-empty string: a result without one is not returned."""
    snippet: str
    """The provider's extract. Empty when the provider gave none."""


class WebSearchProvider(Protocol):
    """One web search backend, addressed by its own already-resolved credentials."""

    async def search(self, query: str, limit: int) -> list[WebResult]:
        """At most `limit` results for `query`, in provider order; `[]` when there are none.

        Raises on any failure — the provider decides the error (D5: the one built here raises
        `ToolFailedError`). Only the query leaves the instance (D6).
        """
        ...
