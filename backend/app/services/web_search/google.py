"""The Google Custom Search JSON API provider — one GET per search, one failure shape.

Feature `028`, step `001` (D1, D5, D6, D7, D9). Implements
`app.services.web_search.provider.WebSearchProvider` structurally, parameterised by an
already-plain API key and engine id; it reads no settings, resolves no secret, imports no
`fastapi` and touches no database.

Only the query, the engine id, the result count and the key leave the instance — the key in
the `X-goog-api-key` header, never in the URL, because a URL reaches exception text and proxy
logs (D6, `001.context.md`). Every failure — a timeout, a transport error, a non-2xx status,
an unparsable body or an unexpected shape — becomes one `ToolFailedError` with detail
`{"tool": "web_search"}`, raised `from None` so no httpx text (which carries the URL, and the
URL carries the query) reaches a traceback (D5). Nothing here logs and nothing is cached: two
identical searches make two requests (D7).
"""

from typing import Final

import httpx

from app.errors import ToolFailedError
from app.services.web_search.provider import WebResult

GOOGLE_CUSTOM_SEARCH_URL: Final = "https://www.googleapis.com/customsearch/v1"
"""The one endpoint: `cx`, `q` and `num` go in the query string, the key in a header (D1)."""

DEFAULT_TIMEOUT_SECONDS: Final[float] = 10.0
"""The default per-call timeout. A search is a short request and response, not a generation (D9)."""


class GoogleCustomSearchProvider:
    """Google Programmable Search over the Custom Search JSON API, for one engine and key.

    `api_key` and `engine_id` are used exactly as given — trimming and the "configured"
    decision belong to the factory in `app/services/tools/web_search.py` (D3). `transport`
    is the test seam: `None` means the real network, as in `app.services.llm.client`.
    """

    def __init__(
        self,
        api_key: str,
        engine_id: str,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._engine_id = engine_id
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def search(self, query: str, limit: int) -> list[WebResult]:
        """At most `limit` results for `query`, in response order; `[]` when there are none.

        One GET on a fresh `httpx.AsyncClient` built with this provider's timeout and
        transport. Raises `ToolFailedError`, detail `{"tool": "web_search"}` and no chained
        cause, on any failure (D5). Keeps no state between calls (D7).
        """
        try:
            # A fresh client per call: nothing is kept between searches, so two identical
            # searches make two requests (D7). `transport=None` means the real network.
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout_seconds),
                transport=self._transport,
            ) as http:
                response = await http.get(
                    GOOGLE_CUSTOM_SEARCH_URL,
                    # `params`, never string formatting: httpx encodes the query (D6). The key
                    # is a header, so it never becomes part of a URL.
                    params={"cx": self._engine_id, "q": query, "num": str(limit)},
                    headers={"X-goog-api-key": self._api_key},
                )
        # `TimeoutException` is itself an `HTTPError`, named for the mapping it shares with
        # every other transport failure (`001.context.md`, mirroring `app.services.llm.client`).
        except (httpx.TimeoutException, httpx.HTTPError, httpx.InvalidURL):
            raise _failed() from None

        # 2xx only: httpx follows no redirect by default, and none is expected (D5).
        if not response.is_success:
            raise _failed() from None
        try:
            body: object = response.json()
        except ValueError:
            raise _failed() from None
        if not isinstance(body, dict):
            raise _failed() from None

        if "items" not in body:
            return []  # No `items` key is Google's zero-results answer, not a failure.
        items = body["items"]
        if not isinstance(items, list):
            raise _failed() from None

        results: list[WebResult] = []
        for item in items:
            if len(results) >= limit:
                break
            if not isinstance(item, dict):
                continue
            link = item.get("link")
            if not isinstance(link, str):
                continue
            title = item.get("title")
            snippet = item.get("snippet")
            # The plain-text fields, never `htmlTitle` / `htmlSnippet`, and not normalised:
            # formatting is the adapter's (`002`).
            results.append(
                WebResult(
                    title=title if isinstance(title, str) else "",
                    url=link,
                    snippet=snippet if isinstance(snippet, str) else "",
                )
            )
        return results


def _failed() -> ToolFailedError:
    """The one failure shape: the tool name in `detail` and nothing interpolated (D5).

    No status, URL, body, query, key or engine id — the default message is the whole message.
    """
    return ToolFailedError(detail={"tool": "web_search"})
