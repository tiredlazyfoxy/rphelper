"""Web search — the provider seam the `web_search` tool depends on, and its one provider.

Feature `028`, step `001` (D4). Package marker only; holds no logic and re-exports nothing.
Import the names from their modules (`app.services.web_search.provider` for the result value
and the protocol, `app.services.web_search.google` for the Google Custom Search provider).

The package knows nothing of tools, sessions or users: it imports no `fastapi`, no
`app.config`, no `app.secrets`, no `app.db` and nothing from `app.services.tools`.
"""
