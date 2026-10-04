"""The three tool declarations — what the model sees, owned by the seam.

Feature `021`, step `004` (D5). Each declaration is a JSON-ready OpenAI tool object
`{"type": "function", "function": {"name", "description", "parameters"}}` whose `parameters`
is a JSON-schema object with exactly one property, `query` (a string), required, no
additional properties. Declarations only: no behaviour. This module imports nothing from
`app`.
"""

from collections.abc import Mapping
from typing import Final

ToolDeclaration = Mapping[str, object]
"""One JSON-ready OpenAI tool object, as sent in the chat request's `tools` list."""

MEMO_SEARCH_NAME: Final = "memo_search"
SESSION_SEARCH_NAME: Final = "session_search"
WEB_SEARCH_NAME: Final = "web_search"


def _declaration(name: str, description: str, query_description: str) -> ToolDeclaration:
    """One OpenAI function tool taking exactly one required string `query`."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": query_description},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }


MEMO_SEARCH: Final[ToolDeclaration] = _declaration(
    MEMO_SEARCH_NAME,
    "Search the roleplayer's searchable notes for this session. Use it to recall facts, "
    "names, places or agreements the roleplayer has written down for this roleplay.",
    "What to look for in the session's notes, in plain words.",
)
SESSION_SEARCH: Final[ToolDeclaration] = _declaration(
    SESSION_SEARCH_NAME,
    "Search past sessions of the same character, by meaning. Use it to recall what happened "
    "earlier with this character in other sessions.",
    "What to look for in the character's past sessions, described by meaning.",
)
WEB_SEARCH: Final[ToolDeclaration] = _declaration(
    WEB_SEARCH_NAME,
    "Search the web. Use it only for one of three reasons: to check a real-world fact; to "
    "check an idiom or whether a phrasing sounds natural; or for a lookup the roleplayer "
    "asked for directly. Do not use it for anything else.",
    "The web search query.",
)

TOOL_DECLARATIONS: Final[tuple[ToolDeclaration, ...]] = (MEMO_SEARCH, SESSION_SEARCH, WEB_SEARCH)
"""The three declarations in offered order: `memo_search`, `session_search`, `web_search`."""
