# Feature 028 — Web search tool · outcome

Intended changes to `docs/architecture/` once this feature ships, for the architect to apply
at finalization. Grouped by target file. D-n refers to this folder's `context.md`. U1–U3
are the user-confirmed decisions it records.

## `docs/architecture/llm-and-streaming.md`

| Section | Intended change | Reason |
|---|---|---|
| "`web_search` — seam now, adapter deferred" | Retitle (e.g. "`web_search` — the provider seam and Google") and replace the `_TBD:` with the as-built design: a provider protocol in `services/web_search/` (search(query, limit) → ordered plain-text results), with one implementation, the Google Custom Search JSON API (`GET …/customsearch/v1`, params `cx`, `q`, `num`; the key in the `X-goog-api-key` header, never in the URL); 5 results; 10 s timeout; no caching (D1, D4, D9, U1) | Closes the `_TBD:` |
| same section | Record the offering rule: `web_search` is offered iff the instance has both search credentials **and** `tool_web_search` resolves true. An unconfigured instance never offers it, because a tool the model cannot see cannot be attempted. Mechanism: the stream router's registry dependency builds the registry per request from settings (static registry + `web_search` when configured); 021's `offered_tools` is unchanged (D3, U3) | New availability condition beside the switch |
| same section | Record the failure shape: every provider failure is `ToolFailedError` (`tool_failed`, detail `{"tool": "web_search"}`), raised with no chained cause and carrying no query, key, URL or body; the seam's `tool_fail` path does the rest (D5) | As built |
| same section | Record the outbound boundary: only the query (plus engine id, count, key) leaves the instance; no ids or other material; neither the provider nor the adapter logs anything (D6, D7) | Brief Out, as built |
| same section | **Known risk:** Google has closed the Custom Search JSON API to new customers, and existing customers must transition by **2027-01-01**. The seam keeps a replacement to one provider class plus the factory in `tools/web_search.py`. Flip condition: the API stops answering for this key, or the transition date arrives. A new provider then becomes a plan | Recorded risk |
| "The tool-calling loop" | Note that the three tools are now all implemented (026, 027, 028), and that `web_search` is the one tool that is not a scoped read of the user's data. It reads no scope ids and is bounded instead by D6's outbound rule | Accuracy of the "every dispatch is a scoped read" bullet |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| Layout — `services/` | Add the package `web_search/` (`provider.py`: web result + provider protocol; `google.py`: the Google provider) and `tools/web_search.py` (the adapter, its formatter, and the factory that decides "configured") (D3, D4) | New modules |
| "Configuration — `pydantic-settings`" | Add the two fields: the search API key (alias **`SEARCH_CSE_KEY`**, a secret-string type masked in `repr`) and the engine id (alias **`SEARCH_CSE_ID`**), both optional, default none (D2) | New settings |
| same section | Record the **deliberate exception to the `RPHELPER_` alias prefix**: these two names are the user's existing environment names, user-confirmed. The explicit-alias rule still holds and only the prefix differs. Say so, so that nobody "fixes" it to `RPHELPER_SEARCH_CSE_KEY` and silently unconfigures web search (D2, U2) | Deliberate asymmetry, named |
| "The `$ENV_VAR` secret-pointer pattern" | Add a paragraph: the web-search credential deliberately does **not** use a pointer. Pointers exist because DB rows are exported; a `Settings` field is never stored or exported, so it is read from the environment directly. Rotation is an environment change plus a restart, as for pointers (D2) | Answers 028's brief question in the doc that owns the pattern |
| "Routers versus services" | Note that `routers/stream.py`'s registry dependency is the only reader of the search settings; the builder (`tools/seam.py`) and the factory take plain strings (D3) | Keeps services settings-free, as stated |
| "The error model" — `tool_failed` row | Note that 028 raises it from the web-search provider and adapter as well as from the tools themselves; detail is `{"tool": "web_search"}`; never chained to the transport exception (D5) | As built |

## `docs/architecture/deployment.md`

| Section | Intended change | Reason |
|---|---|---|
| "Configuration conventions" | Add `SEARCH_CSE_KEY` and `SEARCH_CSE_ID`: read directly from the environment (`env_file` in prod, the backend's `.env` in dev); optional; when either is missing or blank, web search is simply not offered (no error, no startup failure). Note the non-`RPHELPER_` names as a deliberate exception (D2, D3) | Operator-facing environment contract |
| "Configuration conventions" — "Secrets are never in the database" bullet | Extend: the search API key is a secret that is not a pointer either, because it lives only in the environment (D2) | Accuracy |
| "The redaction rule" | Add to the forbidden list: web-search queries (they are composed from message text) and web-search results. The search API key is already covered by "API keys" (D7) | Makes the rule explicit for the new outbound surface |
| "Operational notes" | Add: a restored export needs `SEARCH_CSE_KEY` / `SEARCH_CSE_ID` supplied with the rest of the environment if web search is wanted. Add the 2027-01-01 Google transition as an operational watch item (D1, D2) | Operational consequence |

## `docs/architecture/overview.md`

| Section | Intended change | Reason |
|---|---|---|
| Deferred list / the stack decisions (wherever the web-search adapter is recorded as deferred to FEAT-016's plan) | Replace the deferral with the decision: Google Custom Search JSON API behind a provider seam, credentials read from the environment, unconfigured means not offered; reason and flip condition as in `llm-and-streaming.md` (D1–D3) | The deferral is closed |
| System context / outbound boundary | `_TBD: the architect should check whether overview.md's statement of the instance's outbound surface (the clipboard boundary, the LLM servers) names the search provider; if not, add it as the one outbound call that carries roleplayer-derived text other than to the LLM — the query only (D6)_` | The planner did not read `overview.md` in full |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| "Configuration additions" | Add `SEARCH_CSE_KEY`, `SEARCH_CSE_ID` (optional; no `RPHELPER_` prefix, deliberately; both blank → `web_search` not offered) | Dense index |
| "Backend test conventions" — environment isolation | Amend: the shared isolation also sets `SEARCH_CSE_KEY` / `SEARCH_CSE_ID` to `""` for every test (environment beats `.env`, so a developer's `.env` can never make a test reach Google) (D12) | The isolation rule as built |
| Paths | Add `backend/app/services/web_search/` (provider seam + Google) and `backend/app/services/tools/web_search.py` | Dense index |

## `docs/architecture/domain-rules.md`

| Section | Intended change | Reason |
|---|---|---|
| R9 | Add: `web_search` reads no user data and receives no scope ids; its only outbound content is the query (D6, D8). Availability additionally requires instance credentials (D3) | Completes R9 for the third tool |

## Forward notes (not architecture changes)

- **021 / definitions:** step `002` DoD-15 reviews whether the shipped `web_search`
  description states the three justified uses. A shortfall is a defect against 021 `004`
  (D11).
- **Frontend (no owner yet):** 017's "Web search: on" indicator shows the resolved switch
  even on an instance without credentials, where the tool is never offered. Whether the
  indicator should reflect instance configuration is a product question, not taken here.
  `_TBD: no requirement covers showing instance-level tool availability in the session
  header._`
- **/product-spec:** no change requested. FEAT-016's criteria are covered as mapped in
  `context.md` "Product ids". US-072.AC-1 is `[manual/live]` only, because a model's
  decision to call a tool cannot be automated.

## Observations

- Step 002: `routers/stream.py` now imports `build_tool_registry` from
  `app.services.tools.seam` directly, while the line above it still imports `ToolRegistry` from
  the `app.services.tools` package — the package's twelve re-exports were out of scope here
  (orchestrator decision 3). Possible impact: either add the builder to
  `app/services/tools/__init__.py`'s `__all__` in a later feature, or record in
  `backend/CLAUDE.md` / `backend-structure.md` that importing a tools module directly is allowed.
- Step 001 (scope extension, `app/logging.py`): `deployment.md`'s redaction rule now has a named
  mechanism — **a URL can carry message text**, so the HTTP client's *own* request log is part of
  the rule's surface, not just the log lines this codebase writes. 028 is the first feature to put
  message text in a query string (`q=<the roleplayer's query>`), and `configure_logging`'s stdlib
  bridge carried httpx's request record straight into both sinks at `DEBUG`. Possible impact: add a
  sentence to `deployment.md` § "The redaction rule" naming third-party request logs as in scope,
  and record in `backend-structure.md` that **`app/logging.py` owns third-party logger
  suppression** (constant `_SILENCED_LOGGERS`, alongside `_PROPAGATING_LOGGERS`) — no service
  module may touch a third-party logger.
