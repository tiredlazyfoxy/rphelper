# Feature 028 — Web search tool · feature-wide context

## What this feature is

The assistant's `web_search` tool. Mid-discussion the assistant can look something up on
the web for one of the three justified uses: a real-world fact (a place, a weapon, a
procedure, a period detail), an idiom or naturalness check, or a direct request from the
roleplayer. The instance sends **only the query** to one search provider and returns the
results to the assistant as plain text. The tool is switched by the session's resolved
configuration (017's `tool_web_search`). It is also absent when the instance has no search
credentials. A failure is a tool result (`tool_fail`), and the exchange carries on (R9).

The agreed boundary is `brief.md` in this folder (Definition, Scope In/Out). It is not
widened. **Out:** sending any of the roleplayer's material beyond the query itself;
caching results; the loop, the seam and the declaration (`021`); the switch (`017`). The
brief's open question (which provider, what the credential looks like, and whether it
follows the `$ENV_VAR` pointer convention) is closed by **D1** and **D2**.

## Product ids

Delivers **FEAT-016**: UC-055, UC-056, UC-057; US-070, US-071, US-072, US-073.

| Criterion | Where it lands |
|---|---|
| US-070.AC-1, UC-055 main flow (lookup result returned to the assistant) | `002` (success through the real seam, provider faked at the transport) |
| US-071.AC-1, UC-056 (idiom / naturalness lookup returned) | `002`, same mechanism. The instance cannot tell the uses apart; only the query differs |
| US-072.AC-1, UC-057 (roleplayer asks, assistant calls and relays) | `002` `[manual/live]`. Whether a model decides to call the tool cannot be automated |
| US-073.AC-1 (disabled by the chain → cannot be called) | `002` (not offered: seam level and route level) |
| UC-055 exception flow (tool fails → told, discussion continues) | `001` (every provider failure becomes one typed error); `002` (through the real `dispatch` → `tool_fail`, no raise). End to end is `[manual/live]` |

## Build state — what is built and what is only planned

Features 001..015 are built. **016..027 are planned, not built.** 028 is built after 017,
021, 024, 025, 026 and 027 (roadmap order). When 028 is built, the production registry
therefore already holds `memo_search` and `session_search`.

**Binding rule for the 028 skeleton agent:** for every interface labelled **(B)** below,
bind to the exact identifier frozen in that plan's `status.md ## Skeleton` record. Only
when that record does not exist yet, fall back to the name used here (taken from the
plan's step-file prose). A frozen name that differs from the one below is not a 028 spec
problem; follow the frozen one.

### (A) Built source

- **`backend/pyproject.toml`**: `httpx>=0.27,<1.0` is a direct runtime dependency. Dev
  tools are pytest, mypy and ruff. There is **no** HTTP mocking library, and none is
  added: provider tests use `httpx.MockTransport`.
- **`app/services/llm/client.py`** is the pattern for outbound HTTP. `LlmClient(base_url,
  api_key, timeout_seconds, *, transport=None)` builds a fresh `httpx.AsyncClient(timeout=
  httpx.Timeout(t), transport=…)` per call. It maps `httpx.TimeoutException` and
  `(httpx.HTTPError, httpx.InvalidURL)` to a typed error. It resolves no secret and reads
  no settings.
- **`app/config.py`**: `Settings(BaseSettings)` with `SettingsConfigDict(env_file=".env",
  extra="ignore")`, one field per setting with an explicit `validation_alias`, and no
  `env_prefix`. `get_settings()` is `@lru_cache`d. Existing fields: `data_dir`,
  `db_filename`, `node_id`, `session_cookie_name`, `session_ttl_hours`,
  `llm_request_timeout_seconds` (30.0), and five `log_*` fields.
- **`tests/conftest.py`**: the autouse fixture `isolated_settings_environment` deletes every
  `RPHELPER_*` environment variable and calls `get_settings.cache_clear()` before and after
  each test. It does **not** touch any other variable (see D12).
- **`app/errors.py`**: `DomainError` subclasses with class-level `code` / `http_status`;
  `SecretRefError` (`secret_ref_missing`, 500); `LlmUnreachableError` (`llm_unreachable`,
  502).
- **Logging**: loguru. The redaction rule (`deployment.md` "The redaction rule") is a
  convention every call site follows; nothing enforces it mechanically.
- **Test idioms**: async code is driven by a `run(coro)` / `asyncio.run` helper from sync
  tests (no pytest-asyncio). `tests/test_llm_client.py` fakes the network with a
  recording wrapper around a `MockTransport` handler. Each module's AST convention tests
  live in that module's own test file (`module_tree()` / `imported_modules()`-style
  helpers). There is no central import allowlist.

### (B) Pending plans

- **021 — the seam** (`app/services/tools/`):
  - `definitions.py` already declares `web_search`: one parameter, `query`, and a
    description limited to the three justified uses (021 `004` Interface intent). **028
    does not change it** (D11).
  - `seam.py`: `ToolScope(user_id, session_id, character_id, setup_id | None)`;
    `ToolOutcome(content, summary)`; the `Tool` protocol (`name`, async `run(scope,
    connection, arguments) -> ToolOutcome`); the **production registry**, a read-only
    name → `Tool` mapping; `offered_tools(configuration, registry)`, where a tool is
    offered iff its `tool_*` switch resolves true **and** its name is in the registry, in
    declaration order; `dispatch`. In `dispatch`, any `Exception` from `run` becomes a
    `tool_fail` frame with code `tool_failed`, the model message `The tool failed.
    Continue without its result.` and a failed tool row with text `The tool failed.`. A
    success becomes a `tool_result` frame carrying `summary`, and the model receives
    `content`. On failure the seam logs the tool name, the call id and the exception class
    only.
  - `app/errors.py` `ToolFailedError` (021 `001`): code `tool_failed`, HTTP 502, a fixed
    default message, `detail` per instance. 021's own example detail is
    `{"tool": "memo_search"}`.
  - `routers/stream.py` (021 `006`) has an **overridable dependency that returns the
    production tool registry**. The compose route passes its value to the compose source.
    Its exact name is not frozen yet.
- **017 — the switch**: `SessionConfiguration.tool_web_search` is a resolved
  `Setting<boolean>` whose `value` is never null (default on), resolved `character →
  session`. The column is `sessions.tool_web_search` (nullable boolean). 028 does not read
  it; `offered_tools` does.
- **026 / 027 — the adapter pattern 028 mirrors**:
  - each adapter registers by a **top-level import of its module in `seam.py`**;
  - the adapter module imports seam names only under `TYPE_CHECKING` (postponed
    annotations), and imports `ToolOutcome` inside the function that constructs it;
  - the constructor takes optional injection keywords;
  - `run` reads only `query`, and a missing or non-string one raises `ToolFailedError`;
  - errors propagate unchanged to the seam;
  - a module-level pure formatter builds the content and a `<N> <noun>` summary.

  After 027 the production registry constant holds exactly `memo_search` and
  `session_search`. Four tests pin that: 021 `004` DoD-2 (`test_tool_seam.py`), 021 `006`
  DoD-10 (`test_compose_route.py`), 026 `002` DoD-11 (`test_memo_search_tool.py`) and 027
  `003` DoD-11 (`test_session_search_tool.py`). **Under D3 all four stay true and are not
  amended.** The one earlier assertion 028 amends is listed in `002.context.md`.

## Architecture this binds to

- `llm-and-streaming.md`: "The tool-calling loop" (a failed tool is a tool result; a
  disabled tool is not offered, absent rather than refused; availability resolved live);
  "`web_search` — seam now, adapter deferred" (its `_TBD:` on the provider is closed by
  D1).
- `backend-structure.md`: "Configuration — `pydantic-settings`" (explicit aliases,
  `lru_cache`, routers depend on `get_settings`); "The `$ENV_VAR` secret-pointer pattern"
  (why pointers exist: DB rows get exported); "Routers versus services" (services take
  plain arguments and import no `fastapi`); "The error model" (`tool_failed` row: realizes
  FEAT-016; detail is the tool name).
- `deployment.md`: "Configuration conventions" (`env_file`; secrets never in the
  database); "The redaction rule" (no API key, no message text, no prompt payload in any
  log record at any level); "loguru's `diagnose` / backtrace must be off".
- `domain-rules.md` **R9** (three tools; a failure does not end the discussion), **R5**
  (tools get their scope from the seam, never from arguments).
- 021 `context.md` D5, D6, D13 and its literals table; 026 `context.md` D3–D6; 027
  `context.md` D5–D7; 017 `context.md` D5.

Cited, never copied.

## Files this feature touches

```
backend/app/config.py                       # + two search settings                       (001)
backend/app/services/web_search/__init__.py # NEW package marker                          (001)
backend/app/services/web_search/provider.py # NEW — result value + provider protocol      (001)
backend/app/services/web_search/google.py   # NEW — the Google Custom Search provider     (001)
backend/app/services/tools/web_search.py    # NEW — the Tool adapter, formatter, factory  (002)
backend/app/services/tools/seam.py          # + the request-time registry builder
                                            #   (021-owned; the one edit to it)           (002)
backend/app/routers/stream.py               # registry dependency reads settings
                                            #   (021-owned; the one edit to it)           (002)
```

Test files are listed per step. `tests/conftest.py` is amended in step `001` (D12).
`tests/test_tool_seam.py` (021's) is amended in step `002` at one assertion only.

**Not touched. A step that touches one is out of scope:** `app/services/tools/
definitions.py`, `memo_search.py`, `session_search.py`, `__init__.py`; everything under
`app/services/search/`; `app/services/llm/*`; `app/services/compose.py`;
`app/services/configuration.py`; `app/errors.py` (no new error code); `app/secrets.py`;
`app/db/*`; `app/main.py`; `app/dependencies.py`; every other router; `backend/
pyproject.toml` and `uv.lock` (**no new dependency**); `test_compose_route.py`,
`test_memo_search_tool.py`, `test_session_search_tool.py`, `test_tool_definitions.py`. No
frontend: 017's "Web search: on/off" indicator already exists and is unchanged.

## Decisions

U1–U3 are user-confirmed. The rest are planner decisions.

### D1 — Provider: Google Programmable Search, the Custom Search JSON API (U1)

One concrete provider: `GET https://www.googleapis.com/customsearch/v1` with the
parameters `cx` (engine id), `q` (query) and `num` (result count). The response's
`items[]` carry `title`, `link` and `snippet`. A response with no `items` key means zero
results. The request and parse rules are in `001.context.md`.

**Known risk, not a blocker:** Google has closed this API to new customers, and existing
customers must move off it by **2027-01-01**. That is why the provider sits behind its own
seam (D4). Replacing it means writing one new provider class and changing the factory
that builds it (`002`). The tool, its format and its tests stay as they are. Recorded in
`outcome.md`.

### D2 — Credentials are read from the environment, directly (U2)

`Settings` gains two optional fields whose `validation_alias` values are **exactly**
`SEARCH_CSE_KEY` (the API key) and `SEARCH_CSE_ID` (the engine id, `cx`). Both default to
none. The user's `.env` already holds both. In prod they come from compose's `env_file`.

- **There is no `$ENV_VAR` pointer layer, no database row and no admin UI.** This closes
  the brief's open question. The pointer convention exists because `llm_servers` rows are
  **exported** (FEAT-018), so a stored key would make every export carry a secret. A
  `Settings` field is never exported, so the pointer would only add a level of
  indirection. Rotating the key is an environment change plus a restart, which is the same
  operational answer the pointer pattern gives.
- **A deliberate exception to the `RPHELPER_` alias prefix.** The names are the ones the
  user's environment already uses, and the user confirmed them. The explicit-alias
  convention still holds (each name is greppable in `config.py`); only the prefix differs.
  `RPHELPER_SEARCH_CSE_KEY` is **not** read. Recorded in `outcome.md` for
  `backend-structure.md` and `deployment.md`.
- The key field is a **secret-string type whose `repr` masks the value**, so logging or
  printing a `Settings` cannot leak it. The engine id is a plain string. Neither is a
  secret pointer, and `resolve_secret` is not involved.

### D3 — Unconfigured → not offered; the registry is built per request (U3)

`web_search` is offered iff **both** credentials are non-blank (after trimming) **and**
the session's `tool_web_search` resolves true. A tool the model cannot see cannot be
attempted (`llm-and-streaming.md`), so an unconfigured instance never makes a call that
would only fail.

Mechanism. It leaves 021's `offered_tools` rule and the static registry constant
unchanged:

- **`tools/web_search.py`** owns "configured". A factory takes the key and the engine id.
  When both are present and non-blank it returns the adapter over a Google provider built
  from them. Otherwise it returns none.
- **`seam.py`** gains a **registry builder**. It takes the two credential values and
  returns a new read-only mapping: every entry of the production registry constant, plus
  `web_search` when the factory returned an adapter. The constant itself is unchanged and
  still holds exactly `memo_search` and `session_search`. That is why the four registry
  tests named in (B) stay true.
- **`routers/stream.py`**: the existing registry dependency now also depends on
  `get_settings` and returns the builder's result for the two settings values. The
  credentials are therefore read **at request time** through `get_settings`, never
  captured at import. Tests can flip them by overriding `get_settings` (or by clearing the
  cache), and they can still override the registry dependency itself.

Services stay settings-free. The builder and the factory take plain strings, and only the
router reads `Settings` (`backend-structure.md` "Routers versus services").

### D4 — The provider seam

The package `app/services/web_search/` is the seam the product depends on (brief
Definition):

- `provider.py` holds a **web result** value (title, url, snippet; plain text) and a
  **provider protocol** with one async operation, search(query, limit), that returns an
  ordered list of web results or raises.
- `google.py` holds the one implementation (D1).

The package imports no `fastapi`, no `app.config`, no `app.secrets`, no `app.db` and
nothing from `app.services.tools`. It knows nothing of tools, sessions or users.

### D5 — Failure has one shape

Every provider failure raises **`ToolFailedError` with detail `{"tool": "web_search"}`**.
That covers a timeout, a transport error, a non-2xx status and an unparsable body or
shape. The adapter raises the same error for bad arguments (`002`). No new error code is
added. The provider exists only to serve this tool, so 021's typed tool failure is the
honest code, and a new `DomainError` would need its own status record for an error that is
never an HTTP response.

The error carries **no query, no key, no engine id, no URL and no response body** in its
message or detail. It is raised **without a chained cause** (`raise … from None`). An
httpx exception's text can contain the request URL, and the URL contains the query. A
cause chain is exactly what a traceback formatter prints. The seam turns the error into
`tool_fail` (021 D6), and the exchange continues (UC-055 exception flow, R9).

### D6 — The outbound boundary: the query and nothing else

The only things that leave the instance are the query string, the engine id, the result
count and the key (the key in a header, D1 / `001.context.md`). No user id, session id,
character id, setup id, message text, memo or persona is sent (brief Out).

### D7 — Nothing logs the query, the results or the key

The query counts as message text under the redaction rule (it is composed from the
discussion). The provider and the adapter emit **no** log records. The only failure log is
the seam's existing one (tool name, call id, exception class). Results are not logged,
not persisted beyond 021's tool row, and **not cached** (brief Out): two identical calls
make two requests.

### D8 — The scope is unused; only `query` is read

The adapter accepts `ToolScope` (the protocol requires it) and uses none of it: web search
is not a scoped read of the user's data. It reads exactly one key from the arguments,
`query`. Every other key (`user_id`, `session_id` and so on) is ignored and never reaches
the provider. This mirrors 026 D6 and 027 D7.

### D9 — Timeout and result count are constants

- The Google provider's default timeout is a module constant, **10 seconds**, overridable
  through its constructor. The LLM timeout is not reused: a search call is a short request
  and response, not a long generation. No setting is added, because no requirement asks
  for one. Flip condition: an operator needs to tune it.
- The adapter asks for **5** results (a module constant in `tools/web_search.py`), with no
  paging and no count argument. The declaration stays `query` only, as with 026 / 027.

### D10 — Two steps

| Step | Subject | Est. source LoC | Depends on |
|------|---------|-----------------|------------|
| 001 | two settings; `services/web_search/` (result, protocol, Google provider) | ~120 | none (021 `001` built) |
| 002 | `tools/web_search.py` (adapter, formatter, factory); registry builder in `seam.py`; registry dependency in `routers/stream.py` | ~110 | 001; 021 `004` / `006`, 017 `003`, 026 `002`, 027 `003` built |

### D11 — The declaration is 021's and is unchanged

021 `004` specifies the `web_search` description as stating only the three justified uses
(a real-world fact; an idiom or naturalness check; a lookup the roleplayer asked for). The
brief's "three uses reflected in the description" is therefore delivered by 021's
`definitions.py`. 028 does not edit it. Step `002` carries a `[manual/live]` review item
that confirms the shipped wording. A shortfall there is a defect against 021 `004`, not a
028 edit.

### D12 — Test isolation for the two non-prefixed variables

pydantic-settings gives environment variables priority over the `.env` file. The shared
autouse isolation in `tests/conftest.py` is extended (step `001`) to **set both
`SEARCH_CSE_KEY` and `SEARCH_CSE_ID` to the empty string** for every test and restore them
afterwards. Deleting the variables would not be enough, because a developer's `.env`
would still supply the values. With the empty strings in place, every test sees an
**unconfigured** instance unless it passes values explicitly (init arguments, a
`get_settings` override, or its own `monkeypatch.setenv`). No test can reach Google by
accident. Credential values used in tests are obvious fakes (for example `test-key` /
`test-cx`), and every provider in a test runs over a `MockTransport`.

## Literals — shared by both steps

| Name | Exact value | Used by |
|---|---|---|
| tool name | `web_search` | D3, D5 (`001`, `002`) |
| failure error | `ToolFailedError`, code `tool_failed`, detail `{"tool": "web_search"}`, no chained cause | D5 (`001`, `002`) |
| env variable — API key | `SEARCH_CSE_KEY` | D2 (`001`, `002`) |
| env variable — engine id | `SEARCH_CSE_ID` | D2 (`001`, `002`) |
| switch (017's) | `tool_web_search` | D3 (`002`) |
| failed model message (021's) | `The tool failed. Continue without its result.` | D5 (`002`) |

Step-only literals (the request shape, the content format, the summary) are in each
step's context file.

## Cross-cutting constraints

- Backend fully typed; `mypy app` and `ruff check .` green after every step (commands in
  the root `CLAUDE.md`).
- Services import no `fastapi` and read no settings. Only `routers/stream.py` reads the two
  settings (D3).
- No new dependency. `httpx` only, a fresh `AsyncClient` per call, with `transport=`
  injection as in `LlmClient`.
- Every test network call goes through `httpx.MockTransport`. No test may make a real
  request (D12). No monkeypatching of httpx.

## Test conventions

From `backend/`. pytest, flat `tests/`, names `test_<behavior>__S028_<SSS>_DoD<n>`.

- Async code runs through `asyncio.run(...)` from sync tests (no async plugin).
- Fake the provider network with `httpx.MockTransport` and a file-local recording handler
  (method, URL, query params, headers, body, and `request.extensions["timeout"]`), as in
  `tests/test_llm_client.py`.
- **Log capture**: add a loguru sink at the lowest level inside the test (a list-appending
  callable) and remove it afterwards. Assert on the captured messages, including any
  exception text a record carries.
- Seam and route tests build their engine file-locally (`schema.metadata.create_all`) with
  file-local raw-insert helpers, two users and ids above 2^60, as 021 / 026 / 027 tests do.
- Expected values come from this plan (the literals, D-rules and the step context files)
  and from the faked responses, never from calling the code under test.

## Vocabulary

| Term | Means here |
|---|---|
| **credentials** | the pair `SEARCH_CSE_KEY` + `SEARCH_CSE_ID` |
| **configured** | both credentials present and non-blank after trimming |
| **provider** | an implementation of D4's protocol. The one built here is Google's |
| **web result** | one result: title, url, snippet, plain text |
| **the adapter** | the `web_search` `Tool` implementation (`002`) |
| **static registry** | 021's production registry constant (memo + session after 027) |
| **request registry** | the builder's per-request mapping: the static registry plus `web_search` when configured |
