"""The `web_search` tool — 021's `Tool` over one web search provider.

Feature `028`, step `002` (FEAT-016; UC-055, UC-056, UC-057; US-070..073). Three public names
and nothing else:

- **`format_results`** — the pure formatter: the provider's ordered results in, the model's
  content and the frame's summary out, one block per result and no numbering, no ids and no
  echo of the query anywhere (`002.context.md`).
- **`WebSearchTool`** — the adapter. It reads only `query` from the model's arguments, uses
  neither the `ToolScope` nor the connection the seam hands it (D8: a web lookup is not a
  scoped read of the roleplayer's data), and awaits its injected provider for `RESULT_COUNT`
  results. It never builds a failure outcome of its own: a bad `query` raises
  `ToolFailedError` before any request, and the provider's own failures propagate unchanged,
  for the seam to turn into the `tool_fail` frame while the exchange carries on (D5, R9).
- **`configured_web_search_tool`** — the factory, and the one place that decides what
  "configured" means (D3): both credentials present and non-blank after trimming, or no tool
  at all. `seam.py`'s registry builder is its only production caller.

Only the query, the result count and the provider's own credentials leave the instance (D6),
and nothing here logs: the query is composed from the discussion and so counts as message
text under the redaction rule (D7).

The seam imports this module for the factory, so this module must not import the seam while it
is being imported: the seam's types are imported for type checking only and `ToolOutcome` is
imported inside the method that constructs it. Step `001`'s `app.services.web_search` modules
are imported at the top instead - they import nothing from `app.services.tools`, so no cycle
arises. Neither this module nor the seam reaches for a web framework, this module reads no
settings and touches no database, and the connection it is handed is simply unused.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Final

from sqlalchemy import Connection

from app.errors import ToolFailedError
from app.services.tools.definitions import WEB_SEARCH_NAME
from app.services.web_search.google import GoogleCustomSearchProvider
from app.services.web_search.provider import WebResult, WebSearchProvider

if TYPE_CHECKING:  # Importing these at runtime would re-enter a half-initialised `seam`.
    from app.services.tools.seam import ToolOutcome, ToolScope

RESULT_COUNT: Final = 5
"""How many results the adapter asks its provider for. No paging, no count argument (D9)."""


def format_results(results: Sequence[WebResult]) -> tuple[str, str]:
    """What the model is told about `results`: the content first, then the summary (D9).

    The content is one block per result, in the given order - the provider's own order, which is
    not re-sorted here - and the blocks are joined by one blank line. A block is the title line,
    the url line and the snippet line; the snippet line is absent when the snippet is blank, and
    a blank title renders as a fixed placeholder. A title and a snippet each have their
    whitespace runs collapsed to a single space and their ends stripped, so one that straddles
    newlines or tabs still occupies exactly one line; the url is trimmed and otherwise verbatim.
    No results is a success and not a failure, and has its own fixed content. The summary counts
    the results and carries no title, url, snippet or query text at all, because it is persisted
    and shown outside the model's own transcript (021 D6, D7). Pure: the results are all it is
    given, and the exact literals are `002.context.md`'s table.
    """
    # Not pluralised: `<N> results` is the literal the frame carries, `0 results` included.
    summary = f"{len(results)} results"
    if not results:
        return "No web results.", summary
    blocks = []
    for result in results:
        # `split()` on no separator is the whitespace collapse *and* the end trim in one step, so
        # a title or snippet straddling newlines and tabs still occupies exactly one line. One that
        # is empty afterwards is "blank": a title gets the placeholder, a snippet gets no line.
        title = " ".join(result.title.split()) or "(untitled)"
        snippet = " ".join(result.snippet.split())
        # The url is trimmed and otherwise verbatim: it is an address, not prose.
        block = f"{title}\n{result.url.strip()}"
        if snippet:
            # A blank snippet leaves no line at all - no trailing newline and no empty line.
            block = f"{block}\n{snippet}"
        blocks.append(block)
    return "\n\n".join(blocks), summary


@dataclass(frozen=True)
class WebSearchTool:
    """The `web_search` implementation of 021's `Tool`: one lookup through one provider (D3-D9).

    Unlike 026's and 027's adapters, which take optional injection keywords and otherwise reach
    for their port's own defaults, this one takes the **whole provider** as its single required
    argument: there is no port here, the provider is the only collaborator, and it already owns
    its credentials, its timeout and its transport seam (step `001`). So there is no production
    default to name a second time and nothing to make optional - a default-constructed instance
    would have no way to search. The field is positional-or-keyword rather than keyword-only for
    the same reason: with exactly one required argument there is no ordering to get wrong, and
    `WebSearchTool(provider)` and `WebSearchTool(provider=provider)` both read correctly. The
    production instance is the one `configured_web_search_tool` builds; a test passes a Google
    provider over an `httpx.MockTransport`, or any object satisfying the protocol.
    """

    provider: WebSearchProvider
    """The web search backend every call goes through. Required: there is no sensible default."""

    name: ClassVar[str] = WEB_SEARCH_NAME
    """The declared name this tool is registered and offered under (`definitions.py` owns it)."""

    async def run(
        self, scope: "ToolScope", connection: Connection, arguments: Mapping[str, object]
    ) -> "ToolOutcome":
        """Search the web for `arguments["query"]` and format the results for the model (D5-D9).

        `arguments` is the model's own object, so exactly one key is read from it: `query`, which
        must be a string that is non-blank after trimming. Anything else in it - a user, session,
        character or setup id - is ignored and never reaches the provider, and neither `scope` nor
        `connection` is read at all: a web lookup is not a scoped read of the roleplayer's data,
        and this adapter issues no SQL (D6, D8, R5). A missing, non-string or blank `query` is a
        `ToolFailedError` carrying this tool's name, raised before any request, so a pointless
        outbound call is never made (`002.context.md`).

        The query reaches the provider exactly as given - untrimmed, verbatim - together with
        `RESULT_COUNT`. The provider's errors propagate untouched for the seam to turn into the
        `tool_fail` frame (D5), success returns the formatted content and summary, and nothing is
        logged or cached either way (D7).
        """
        # The `ToolOutcome` this returns is imported *here*, inside the method, not at module
        # level: the seam imports this module to build its registry, so a module-level import
        # would run against a half-initialised `seam`.
        from app.services.tools.seam import ToolOutcome

        # Exactly one key is read, and `scope` and `connection` are deliberately untouched (D8).
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            # Raised before any request: a blank search is a bad argument, not an outbound call.
            raise ToolFailedError(detail={"tool": WEB_SEARCH_NAME})

        # The query goes over verbatim - untrimmed - so what the model asked for is what is
        # searched for; the provider's own failures propagate from here untouched (D5).
        results = await self.provider.search(query, RESULT_COUNT)
        content, summary = format_results(results)
        return ToolOutcome(content, summary)


def configured_web_search_tool(api_key: str | None, engine_id: str | None) -> WebSearchTool | None:
    """The adapter for these credentials, or `None` when the instance is not configured (D3).

    The one place "configured" is decided: both values present and non-blank after trimming. When
    they are, the returned adapter holds step `001`'s Google provider built from the **trimmed**
    values with that provider's own defaults - its timeout, and the real network (D1, D9). When
    either is absent or blank, there is no adapter, so `seam.py`'s builder leaves `web_search` out
    of the registry, `offered_tools` cannot offer it and the model never sees a tool whose every
    call would fail (D3, `llm-and-streaming.md`).

    Takes plain strings, never a `Settings`: only `routers/stream.py` reads settings
    (`backend-structure.md` "Routers versus services"). Replacing Google means changing the
    provider this builds and nothing else - not the adapter, not the format, not their tests (D1).
    """
    key = "" if api_key is None else api_key.strip()
    identifier = "" if engine_id is None else engine_id.strip()
    if not key or not identifier:
        return None
    # The trimmed values, and the provider's own defaults: no timeout and no transport here.
    return WebSearchTool(GoogleCustomSearchProvider(key, identifier))
