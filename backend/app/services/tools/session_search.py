"""The `session_search` tool — 021's `Tool` over the character's past sessions.

Feature `027`, step `003` (FEAT-015; UC-053, UC-054; US-067, US-068, US-069, US-138). Two public
names and nothing else:

- **`format_excerpts`** — the pure formatter: the ordered excerpt records step `002`'s read returned
  in, the model's content and the frame's summary out, one block of a header line plus a body per
  record and no persona text, no setup description and no ids anywhere (D3).
- **`SessionSearchTool`** — the adapter. It reads only `query` from the model's arguments and takes
  every id from the `ToolScope` the seam built - the scope's session being the one that is excluded
  (D7, R5) - hands step `001`'s synchronous `search_sessions` and step `002`'s excerpt read to a
  worker thread together, in a single call, so the port's embedding bridge runs with no event loop
  under it and the connection is never passed back and forth (D6), and returns the formatted blocks
  as a `ToolOutcome`. It never builds a failure outcome of its own: bad arguments raise
  `ToolFailedError` and the search's own errors propagate unchanged, for the seam to turn into the
  `tool_fail` frame while the exchange carries on (D5, R9).

The seam imports this module to put the adapter in its production registry, so this module must not
import the seam while it is being imported: the seam's types are imported for type checking only
and `ToolOutcome` is imported inside the method that constructs it. Neither this module nor the
seam reaches for a web framework, and this module runs no SQL of its own — the connection it is
handed is only passed through, and steps `001` and `002` are what guarantee no transaction is left
open.
"""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import Connection

from app.errors import ToolFailedError
from app.services.llm_registry import LlmClientFactory
from app.services.search.session_search import SessionExcerpt, list_session_excerpts, search_sessions
from app.services.tools.definitions import SESSION_SEARCH_NAME

if TYPE_CHECKING:  # Importing these at runtime would re-enter a half-initialised `seam`.
    from app.services.tools.seam import ToolOutcome, ToolScope


def format_excerpts(excerpts: Sequence[SessionExcerpt]) -> tuple[str, str]:
    """What the model is told about `excerpts`: the content first, then the summary (D3).

    The content is one block per record, in the given order - the port's rank order, carried through
    step `002`'s read and not re-sorted here - and the blocks are joined by one blank line. A block is
    its header line, a newline, and its body: the header names the session's creation date as an ISO
    calendar date and either the setup's name or that there is no setup, and the body is the record's
    bounded excerpt, or a fixed line in its place when the session has no settled entries. No record
    is a success and not a failure, and has its own fixed content. The summary counts the blocks and
    carries no entry text at all, because it is persisted and shown outside the model's own transcript
    (021 D6). Pure: it reads nothing, and the records are all it is given.
    """
    # Not pluralised: `<N> sessions` is the literal the frame carries, `0 sessions` included (D3).
    summary = f"{len(excerpts)} sessions"
    if not excerpts:
        return "No matching sessions.", summary
    blocks = []
    for record in excerpts:
        # The header's separator is a space, U+00B7 MIDDLE DOT and a space; the date is the record's
        # already-parsed, already-reduced calendar date, rendered and never re-derived (step `002`).
        shown_setup = "no setup" if record.setup_name is None else f"setup: {record.setup_name}"
        header = f"### Session {record.created_date.isoformat()} · {shown_setup}"
        # The excerpt is already joined and already bounded by step `002`: never cut again here.
        body = record.excerpt if record.excerpt else "(no settled entries)"
        blocks.append(f"{header}\n{body}")
    return "\n\n".join(blocks), summary


@dataclass(frozen=True, kw_only=True)
class SessionSearchTool:
    """The `session_search` implementation of 021's `Tool`: the character's past sessions (UC-053, D6).

    Both construction arguments are optional and exist only so a test can inject a fake embedder;
    each is `None` when it was not injected, which means "let `search_sessions` apply its own default"
    rather than naming that default a second time here. A default-constructed instance is therefore
    the production one, and it is what the seam registers.
    """

    client_factory: LlmClientFactory | None = None
    """The LLM client factory to search through, or `None` to use `search_sessions`' own default."""
    timeout_seconds: float | None = None
    """The embedding timeout in seconds, or `None` to use `search_sessions`' own default."""

    name: ClassVar[str] = SESSION_SEARCH_NAME
    """The declared name this tool is registered and offered under (`definitions.py` owns it)."""

    async def run(
        self, scope: "ToolScope", connection: Connection, arguments: Mapping[str, object]
    ) -> "ToolOutcome":
        """Search `scope`'s character's past sessions for `arguments["query"]`, formatted (D3, D5-D7).

        `arguments` is the model's own object, so exactly one key is read from it: `query`, which must
        be a string. Anything else in it - a user, session, character or setup id, a current session -
        is ignored, and every id the search receives comes from `scope` instead, the scope's own
        session being the one excluded as the session being composed in (D7, R5). A missing or
        non-string `query` is a `ToolFailedError` carrying this tool's name.

        The search and the excerpt read are both synchronous and the search embeds the query, so the
        two run together on one worker thread rather than on this coroutine's loop, in a single call
        and in that order (D6); `connection` is the seam's own open connection and is used by one
        thread at a time, which the engine's connect arguments allow. Errors propagate untouched,
        success returns the formatted content and summary, and either way the connection is left with
        no transaction open.
        """
        # Imported here, not at module level: the seam imports this module to build its registry,
        # so a module-level import would run against a half-initialised `seam`.
        from app.services.tools.seam import ToolOutcome

        query = arguments.get("query")
        if not isinstance(query, str):
            raise ToolFailedError(detail={"tool": SESSION_SEARCH_NAME})

        # Only what was injected is forwarded: `None` means "let `search_sessions`' own default win".
        injected: dict[str, Any] = {}
        if self.client_factory is not None:
            injected["client_factory"] = self.client_factory
        if self.timeout_seconds is not None:
            injected["timeout_seconds"] = self.timeout_seconds

        # One call for both reads, so `connection` stays on the one worker thread (D6). Every id is
        # the scope's, the scope's own session being the current one the search excludes (D7).
        excerpts = await asyncio.to_thread(
            _search_and_hydrate,
            connection,
            scope.user_id,
            scope.character_id,
            scope.session_id,
            query,
            injected,
        )
        content, summary = format_excerpts(excerpts)
        return ToolOutcome(content, summary)


def _search_and_hydrate(
    connection: Connection,
    user_id: int,
    character_id: int,
    current_session_id: int,
    query_text: str,
    injected: Mapping[str, Any],
) -> list[SessionExcerpt]:
    """The search and then the excerpt read, sequentially, on the one thread they are handed to (D6).

    All of `run`'s synchronous work in a single callable, so the connection is never passed back to
    the loop thread between the two reads. `injected` holds only the injections that were actually
    set. The hits' ids reach the read in the port's rank order, and the records come back in that
    same order; both reads leave no transaction open, and nothing else is issued on `connection`.
    """
    hits = search_sessions(connection, user_id, character_id, current_session_id, query_text, **injected)
    return list_session_excerpts(connection, user_id, [hit.id for hit in hits])
