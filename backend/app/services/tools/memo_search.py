"""The `memo_search` tool — 021's `Tool` over the session's searchable notes.

Feature `026`, step `002` (FEAT-014; UC-051, UC-052; US-063..066, and the `memo_search` halves of
US-099 / US-100). Two public names and nothing else:

- **`format_hits`** — the pure formatter: ordered hits in, the model's content and the frame's
  summary out, one line per hit and no ids, names or titles anywhere (D4).
- **`MemoSearchTool`** — the adapter. It reads only `query` from the model's arguments and takes
  every id from the `ToolScope` the seam built (D6, R5), hands step `001`'s synchronous
  `search_memos` to a worker thread so the port's embedding bridge runs with no event loop under
  it (D3), and returns the formatted hits as a `ToolOutcome`. It never builds a failure outcome of
  its own: bad arguments raise `ToolFailedError` and the search's own errors propagate unchanged,
  for the seam to turn into the `tool_fail` frame while the exchange carries on (D5, R9).

The seam imports this module to put the adapter in its production registry, so this module must not
import the seam while it is being imported: the seam's types are imported for type checking only
and `ToolOutcome` is imported inside the method that constructs it. Neither this module nor the
seam reaches for a web framework, and this module runs no SQL of its own — the connection it is
handed is only passed through, and step `001` is what guarantees no transaction is left open.
"""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import Connection

from app.errors import ToolFailedError
from app.services.llm_registry import LlmClientFactory
from app.services.search.memo_search import search_memos
from app.services.search.ports import SearchHit
from app.services.tools.definitions import MEMO_SEARCH_NAME

if TYPE_CHECKING:  # Importing these at runtime would re-enter a half-initialised `seam`.
    from app.services.tools.seam import ToolOutcome, ToolScope


def format_hits(hits: Sequence[SearchHit]) -> tuple[str, str]:
    """What the model is told about `hits`: the content first, then the summary (D4).

    The content is one line per hit, in the given order - the port's fused-rank order, which is not
    re-sorted here - each line the hit's level literal in brackets followed by the hit's snippet
    with its whitespace runs collapsed to a single space and its ends stripped, so a snippet that
    straddles newlines or tabs still occupies exactly one line. No hits is a success and not a
    failure, and has its own fixed content. The summary counts the hits and carries no note text at
    all, because it is persisted and shown outside the model's own transcript (021 D6).
    """
    summary = f"{len(hits)} memos"
    if not hits:
        return "No matching notes.", summary
    # `memo_scope` and `snippet` are statically optional on a `SearchHit`, but `search_memos`
    # returns memo hits only, which always carry both; the fallbacks narrow them for `mypy`
    # without changing a real hit's line (`split()` already drops a snippet's own blank ends).
    lines = [f"[{hit.memo_scope or ''}] {' '.join((hit.snippet or '').split())}" for hit in hits]
    return "\n".join(lines), summary


@dataclass(frozen=True, kw_only=True)
class MemoSearchTool:
    """The `memo_search` implementation of 021's `Tool`: the chain's searchable notes (UC-051, D3).

    Both construction arguments are optional and exist only so a test can inject a fake embedder;
    each is `None` when it was not injected, which means "let `search_memos` apply its own default"
    rather than naming that default a second time here. A default-constructed instance is therefore
    the production one, and it is what the seam registers.
    """

    client_factory: LlmClientFactory | None = None
    """The LLM client factory to search through, or `None` to use `search_memos`' own default."""
    timeout_seconds: float | None = None
    """The embedding timeout in seconds, or `None` to use `search_memos`' own default."""

    name: ClassVar[str] = MEMO_SEARCH_NAME
    """The declared name this tool is registered and offered under (`definitions.py` owns it)."""

    async def run(
        self, scope: "ToolScope", connection: Connection, arguments: Mapping[str, object]
    ) -> "ToolOutcome":
        """Search `scope`'s chain for `arguments["query"]` and format the hits for the model (D3-D6).

        `arguments` is the model's own object, so exactly one key is read from it: `query`, which
        must be a string. Anything else in it - a user, session, character or setup id, a scope - is
        ignored, and every id the search receives comes from `scope` instead (D6, R5). A missing or
        non-string `query` is a `ToolFailedError` carrying this tool's name.

        The search itself is synchronous and embeds the query, so it runs on a worker thread rather
        than on this coroutine's loop (D3); `connection` is the seam's own open connection and is
        used by one thread at a time, which the engine's connect arguments allow. Errors propagate
        untouched, success returns the formatted content and summary, and either way the connection
        is left with no transaction open.
        """
        # Imported here, not at module level: the seam imports this module to build its registry,
        # so a module-level import would run against a half-initialised `seam`.
        from app.services.tools.seam import ToolOutcome

        query = arguments.get("query")
        if not isinstance(query, str):
            raise ToolFailedError(detail={"tool": MEMO_SEARCH_NAME})

        # Only what was injected is forwarded: `None` means "let `search_memos`' own default win".
        injected: dict[str, Any] = {}
        if self.client_factory is not None:
            injected["client_factory"] = self.client_factory
        if self.timeout_seconds is not None:
            injected["timeout_seconds"] = self.timeout_seconds

        hits = await asyncio.to_thread(
            search_memos,
            connection,
            user_id=scope.user_id,
            character_id=scope.character_id,
            setup_id=scope.setup_id,
            session_id=scope.session_id,
            query_text=query,
            **injected,
        )
        content, summary = format_hits(hits)
        return ToolOutcome(content, summary)
