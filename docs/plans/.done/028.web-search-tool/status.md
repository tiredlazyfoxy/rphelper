# Feature 028 — web-search-tool

| Step | File                                        | Status  | Verifier | Date |
|------|---------------------------------------------|---------|----------|------|
| 001  | `001.search-settings-and-google-provider.md` | done    | PASS     | 2026-10-05 |
| 002  | `002.web-search-tool-and-registration.md`    | done    | PASS     | 2026-10-05 |

## Files Changed

### Step 001 — Search settings and the Google provider behind the provider seam

- `backend/app/config.py` — the two credential fields (`search_cse_key` / `search_cse_id`); complete
  as frozen by the skeleton, no coder change needed.
- `backend/app/services/web_search/__init__.py` — package marker, docstring only; no coder change.
- `backend/app/services/web_search/provider.py` — `WebResult` + the `WebSearchProvider` protocol;
  no coder change (the frozen declarations are the whole module).
- `backend/app/services/web_search/google.py` — **implemented `GoogleCustomSearchProvider.search`**:
  one GET per call on a fresh `AsyncClient(timeout=httpx.Timeout(...), transport=...)`; `params`
  exactly `cx` / `q` / `num` with the key in the `X-goog-api-key` header; 2xx + JSON object is
  success, absent `items` is an empty list, non-object / linkless items skipped, missing `title` /
  `snippet` becomes `""`, truncation to `limit`, no whitespace normalisation. Added the withheld
  `from app.errors import ToolFailedError` and a private `_failed()` helper (the `_unreachable`
  pattern from `app/services/llm/client.py`); every failure path raises it `from None` with detail
  `{"tool": "web_search"}` and nothing interpolated. No logger, no state between calls.
- `backend/app/logging.py` — **added to step 001's scope by the user's decision on the SPEC fault
  (decision 6)**, and the only file changed in that pass. Two module constants beside the existing
  `_PROPAGATING_LOGGERS` — `_SILENCED_LOGGERS = ("httpx",)` and `_SILENCED_LEVEL =
  logging.CRITICAL + 1` — plus a third loop at the end of `configure_logging` that does
  `logging.getLogger(name).setLevel(_SILENCED_LEVEL)` for each. That stops httpx's own request log
  (emitted by `httpx._client`, which inherits the parent's level) from ever being created, so no
  record carrying a request URL reaches a loguru sink; the comment at the site records *why* — a URL
  can carry message text, so the HTTP client's request log is part of the redaction rule's surface.
  Chosen over a filter because logger-attached filters are not applied to records that merely
  *propagate* from a child, so a filter on `httpx` would have missed `httpx._client` entirely; the
  level is set above `CRITICAL` so the suppression has no level exception, matching
  `deployment.md`. Narrow by construction: no other logger's level is set, propagation is untouched,
  the root bridge and both sinks are unchanged, and `LlmClient` is unaffected. No signature changed.

### Step 002 — The `web_search` Tool adapter and its configuration-gated registration

- `backend/app/services/tools/web_search.py` — **implemented all three frozen bodies** and added the
  two withheld imports (`app.errors.ToolFailedError`,
  `app.services.web_search.google.GoogleCustomSearchProvider`) plus the function-local
  `from app.services.tools.seam import ToolOutcome` inside `run`. `format_results`: `<N> results`
  (never pluralised), `No web results.` for none, one block per result joined by one blank line,
  title and snippet collapsed with `" ".join(x.split())`, url `.strip()`ed only, `(untitled)` for a blank
  title, no snippet line at all when the snippet is blank. `run`: reads only `query`, raises
  `ToolFailedError(detail={"tool": WEB_SEARCH_NAME})` before any request when it is missing,
  non-`str` or blank after trimming, awaits `provider.search(query, RESULT_COUNT)` with the query
  **untrimmed**, returns `ToolOutcome(content, summary)`; no logging, no scope or connection use.
  `configured_web_search_tool`: trims both values, returns `None` unless both are non-blank,
  otherwise `WebSearchTool(GoogleCustomSearchProvider(key, identifier))` with that provider's own
  defaults (no timeout, no transport).
- `backend/app/services/tools/seam.py` — **implemented `build_tool_registry`** and added
  `from app.services.tools.web_search import configured_web_search_tool` after the `session_search`
  import. The body builds a fresh `dict(PRODUCTION_TOOL_REGISTRY)` per call (a shallow copy, so each
  value is the constant's own instance), adds `WEB_SEARCH_NAME` only when the factory returns an
  adapter, and returns `MappingProxyType(...)`. The constant is never written to. Nothing else in the
  seam changed.
- `backend/app/routers/stream.py` — **implemented `get_tool_registry`'s body** and added
  `from app.services.tools.seam import build_tool_registry` (the module, not the package — decision
  3). Returns `build_tool_registry(None if key is None else key.get_secret_value(),
  settings.search_cse_id)` for `key = settings.search_cse_key`: no trimming, no "configured" test and
  no caching here, so a `get_settings` override takes effect per request.

## Skeleton

### Step 001 — frozen interface (2026-10-05)

`backend/app/config.py` — changed, two fields appended after the existing eleven (now 13):

- `search_cse_key: SecretStr | None = Field(default=None, validation_alias="SEARCH_CSE_KEY")` — new.
  `from pydantic import Field, SecretStr`. Unwrap with `settings.search_cse_key.get_secret_value()`;
  `SecretStr("")` is **falsy** and `repr`/`str` render `**********`, so a blank or absent credential is
  `if not settings.search_cse_key`. First `SecretStr` in the repo.
- `search_cse_id: str | None = Field(default=None, validation_alias="SEARCH_CSE_ID")` — new.
- Both deliberately drop the `RPHELPER_` prefix (D2); `get_settings` and the other eleven fields are
  untouched. An empty environment value stays an empty value (`SecretStr("")` / `""`), not `None`
  (verified: `env_ignore_empty` is not set).

`backend/app/services/web_search/__init__.py` — new. Package marker, docstring only, **re-exports
nothing** (the `app/services/search/` convention). Import from the modules below.

`backend/app/services/web_search/provider.py` — new. Imports `dataclasses.dataclass` and
`typing.Protocol` only (no `httpx`, DoD-12):

- `@dataclass(frozen=True) class WebResult` — fields in order `title: str`, `url: str`, `snippet: str`.
- `class WebSearchProvider(Protocol)` — `async def search(self, query: str, limit: int) -> list[WebResult]`
  (body `...`, as `seam.py`'s `Tool`).

`backend/app/services/web_search/google.py` — new. Imports `typing.Final`, `httpx` and
`app.services.web_search.provider.WebResult` only:

- `GOOGLE_CUSTOM_SEARCH_URL: Final = "https://www.googleapis.com/customsearch/v1"` — new.
- `DEFAULT_TIMEOUT_SECONDS: Final[float] = 10.0` — new (D9).
- `class GoogleCustomSearchProvider` — new; satisfies `WebSearchProvider` structurally (checked with
  mypy outside the gate). No base class.
  - `def __init__(self, api_key: str, engine_id: str, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    transport: httpx.AsyncBaseTransport | None = None) -> None` — stores the four values on
    `_api_key` / `_engine_id` / `_timeout_seconds` / `_transport`; no other behaviour.
  - `async def search(self, query: str, limit: int) -> list[WebResult]` — body `raise NotImplementedError`.
- `ToolFailedError` is **not** imported yet: only the unimplemented body needs it and `F401` is on. The
  coder adds `from app.errors import ToolFailedError`.

Caller-compile edits (out of Source-files scope): None.

Gates from `backend/`: `mypy app` — Success, 86 files. `ruff check .` — All checks passed. pytest not run
(red gate's job); `tests/test_config.py` still pins eleven fields and will fail until the test-coder
amends it (orchestrator decision 1).

### Step 002 — frozen interface (2026-10-05)

`backend/app/services/tools/web_search.py` — new. Top-level imports: `collections.abc.Mapping`,
`collections.abc.Sequence`, `dataclasses.dataclass`, `typing.TYPE_CHECKING`, `typing.ClassVar`,
`typing.Final`, `sqlalchemy.Connection`, `app.services.tools.definitions.WEB_SEARCH_NAME`, and
`app.services.web_search.provider.WebResult, WebSearchProvider`. Under `if TYPE_CHECKING:` only:
`from app.services.tools.seam import ToolOutcome, ToolScope`, used as the string annotations
`"ToolScope"` / `"ToolOutcome"` (no `from __future__ import annotations`, as in 026 / 027).

- `RESULT_COUNT: Final = 5` — new. The count the adapter asks its provider for (D9). The value is
  part of the freeze.
- `def format_results(results: Sequence[WebResult]) -> tuple[str, str]` — new. Returns
  `(content, summary)`, as 026's `format_hits` and 027's `format_excerpts` do. Module-level, pure.
  Body `raise NotImplementedError`.
- `@dataclass(frozen=True) class WebSearchTool` — new; satisfies `seam.Tool` structurally (checked
  with mypy outside the gate). No base class, **not** `kw_only`.
  - `provider: WebSearchProvider` — the single **required positional-or-keyword** field, so both
    `WebSearchTool(provider)` and `WebSearchTool(provider=provider)` type-check and run. Why it
    differs from 026 / 027's optional `client_factory` / `timeout_seconds` keywords: there is no
    port here and no production default to re-name — the provider is the only collaborator and it
    already owns its credentials, timeout and transport seam (step `001`), so a default-constructed
    adapter could not search at all. With exactly one required argument there is no ordering to get
    wrong, so keyword-only would only cost the test-coder a spelling.
  - `name: ClassVar[str] = WEB_SEARCH_NAME` — the `definitions.py` constant, not a literal; its
    value is `web_search`.
  - `async def run(self, scope: "ToolScope", connection: Connection, arguments: Mapping[str, object]) -> "ToolOutcome"`
    — the protocol's parameter names and types exactly. Body `raise NotImplementedError`.
- `def configured_web_search_tool(api_key: str | None, engine_id: str | None) -> WebSearchTool | None`
  — new. The factory, and the one place that decides "configured" (D3); positional, in that order.
  Body `raise NotImplementedError`.

`backend/app/services/tools/seam.py` — changed (one addition, nothing else):

- `def build_tool_registry(api_key: str | None, engine_id: str | None) -> ToolRegistry` — new,
  placed immediately after `PRODUCTION_TOOL_REGISTRY` and its docstring. Plain values, never a
  `Settings` (`## Ultra phase` decision 4). Body `raise NotImplementedError`; the coder returns
  `MappingProxyType({**PRODUCTION_TOOL_REGISTRY, ...})` — a new mapping, the constant never
  mutated, the result read-only so assignment raises (DoD-8).
- Unchanged, deliberately: the constant, `ToolRegistry`, `Tool`, `ToolScope`, `ToolOutcome`,
  `_switches`, `_NAMED_DECLARATIONS`, `offered_tools`, `build_tool_scope`, `dispatch`, every
  literal. `WEB_SEARCH_NAME` was already imported (`seam.py:29`).

`backend/app/routers/stream.py` — changed:

- `def get_tool_registry(settings: Annotated[Settings, Depends(get_settings)]) -> ToolRegistry` —
  changed (was `def get_tool_registry() -> ToolRegistry`). `Annotated`, `Depends`, `Settings` and
  `get_settings` were all already imported. Body `raise NotImplementedError`; the coder returns
  `build_tool_registry(key, settings.search_cse_id)` where `key` is
  `settings.search_cse_key.get_secret_value()` when the field is not `None` and `None` otherwise
  (step `001` typed it `SecretStr | None`). No trimming and no "configured" test here, and no
  caching — per-request is what makes a `get_settings` override take effect (D3).
- `from app.services.tools import PRODUCTION_TOOL_REGISTRY, ToolRegistry` → `from app.services.tools
  import ToolRegistry` (`stream.py:69`). The constant is no longer named in this file at all: the
  builder owns it. Nothing else imports it from here (swept: `app/` and `tests/`).
- `compose_zone` and every route are untouched; `registry: Annotated[ToolRegistry,
  Depends(get_tool_registry)]` still resolves, FastAPI resolving the nested `Depends`.

**Three imports are deliberately withheld** — each is needed only by a body, and `F401` is on (the
same handling step `001` recorded for `ToolFailedError`). The coder adds, at the top in isort order:

- `web_search.py`: `from app.errors import ToolFailedError` and
  `from app.services.web_search.google import GoogleCustomSearchProvider`;
- `seam.py`: `from app.services.tools.web_search import configured_web_search_tool`, at line 34,
  after the `session_search` import — the import that DoD-14's allow-set amendment licenses;
- `stream.py`: `from app.services.tools.seam import build_tool_registry` — imported from the module,
  **not** the package (`## Ultra phase` decision 3: `app/services/tools/__init__.py` is out of
  scope, so the builder is not re-exported). A recorded departure from `stream.py:69`'s
  package-level style.

Also the coder's, inside `WebSearchTool.run`: `from app.services.tools.seam import ToolOutcome`, the
function-local import that keeps the seam out of this module's runtime import graph. A comment in
the stub body marks the spot.

**Cycle proof.** With all of the above inserted temporarily and then reverted, each of
`app.services.tools.web_search`, `...seam`, `...memo_search`, `...session_search`,
`app.services.tools`, `app.routers.stream` and `app.main` imported cleanly **alone** in a fresh
interpreter, and `web_search` + `seam` imported cleanly in both orders. The committed stubs pass the
same probes. No module-level runtime edge runs from `tools/web_search.py` to `tools/seam.py`.

Caller-compile edits (out of Source-files scope): None. No test file touched.

Gates from `backend/`: `mypy app` — Success, 87 files. `ruff check .` — All checks passed. pytest not
run (red gate's job). **Known transient:** stubbing `get_tool_registry` rather than leaving it
returning the constant — which would falsely satisfy every unconfigured assertion in DoD-8 / DoD-10
— makes `test_compose_route.py`'s three 021 `006` DoD-10 tests (the ones that
`.pop(get_tool_registry)`) fail with `NotImplementedError` against the skeleton. They are not
amended and must pass again once the coder fills the body; a failure there after that is a CODE
fault.

## Tests

### Step 001 — tests (2026-10-05)

New files:

- `backend/tests/test_search_settings.py` — covers DoD-1, DoD-2, DoD-3, DoD-4 — 6 tests:
  the unprefixed variables populate both fields (`k-123` / `cx-456`, DoD-1); the
  `RPHELPER_`-prefixed names populate neither (DoD-1); both aliases are declared exactly
  (DoD-1); both fields are none with the variables deleted and `_env_file=None` (DoD-2);
  neither `repr` nor `str` of a `Settings` carries `k-123` (DoD-3); under a `chdir`'d temp
  folder whose `.env` sets both to non-empty values, `get_settings()` reports neither a
  non-blank key nor a non-blank engine id, with `RPHELPER_DB_FILENAME` from that same
  `.env` as the control proving the file was read (DoD-4).
- `backend/tests/test_web_search_google.py` — covers DoD-5 .. DoD-12 — 18 test functions
  (40 collected cases with parametrisation): the endpoint constant and the one-GET request shape
  (method, scheme/host/path, the exact parameter set `{cx, q, num}`, the
  `X-goog-api-key` header, an empty body) plus the key appearing nowhere in the URL
  (DoD-5); three items become three ordered `WebResult`s (DoD-6); four parsing edges — no
  `items` key, skipped non-object / non-string-`link` items, missing or non-string
  `title` / `snippet` becoming `""`, truncation to `limit` (DoD-7); eight failure cases
  (403, 429, 500, `ConnectError`, `ReadTimeout`, non-JSON body, JSON array, non-list
  `items`) each raising `ToolFailedError` with code `tool_failed`, detail
  `{"tool": "web_search"}`, `__cause__ is None` and `__suppress_context__ is True`, and a
  second sweep over the same eight asserting the query, key, engine id and `googleapis`
  appear in neither `str`, message nor detail (DoD-8); the default 10.0 and a constructed
  2.5 on all four `request.extensions["timeout"]` phases, plus the constant (DoD-9); two
  identical searches make two requests (DoD-10); a loguru sink at level 0 capturing
  message, `extra` and exception values over one success and one 500 sees none of the
  three secrets (DoD-11); AST import bans on `provider.py` and `google.py`, and no
  `httpx` in `provider.py` (DoD-12).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
  DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 [manual/live, no test].

Amendments:

- `backend/tests/conftest.py` — inside `isolated_settings_environment` only: after the
  `RPHELPER_*` delete loop and before the first `get_settings.cache_clear()`, both
  `SEARCH_CSE_KEY` and `SEARCH_CSE_ID` are set to `""` with `monkeypatch.setenv` (new
  module constant `SEARCH_CREDENTIAL_VARIABLES`); docstring extended with D12's reason.
  The delete loop and both `cache_clear()` calls are unchanged. (D12)
- `backend/tests/test_config.py` (orchestrator decision 1) — `EXPECTED_FIELDS` gains the
  two names (default `None`, aliases `SEARCH_CSE_KEY` / `SEARCH_CSE_ID`); `OVERRIDES`
  gains `("k-123", SecretStr("k-123"))` and `("cx-456", "cx-456")`; the declared-field
  count `11` → `13`; `ORIGINAL_TEN_FIELDS` keeps its ten by excluding the two new names;
  new `PREFIXED_FIELDS` (the eleven prefixed fields) now drives
  `test_unprefixed_variable_does_not_populate_the_field__DoD3` (the new aliases *are*
  `field_name.upper()`), `test_each_field_carries_its_recorded_default__DoD1` and
  `test_unrelated_environment_variables_do_not_break_construction__DoD4` (the autouse
  isolation leaves the two present-but-blank, so a `_env_file=None` `Settings` cannot see
  their declared default — that default is asserted in `test_search_settings.py` instead);
  three tests added — one alias test per new field and one masked-value sweep
  (`repr`, `str`, `model_dump(mode="json")`). Every existing id tag is kept and every
  other test in the file is untouched.

**Recorded deviation beyond decision 1:** the two defaults-reading parametrisations
(`__DoD1` defaults and `__DoD4`) also had to exclude the two new fields. Decision 1 listed
only three breaking sites; these two break for a different reason — the conftest blanking,
not the alias collision — and the exclusion is documented in each test's docstring.

**DoD-11 widened + one test added, after the verify run's Fault SPEC (2026-10-05, user
decision criteria 3 and 4).** Nothing weakened, nothing removed; both changes are additive.

- *Widened.* `test_neither_a_success_nor_a_failure_logs_the_query_or_the_credentials__S028_001_DoD11`
  swept the captured lines for `QUERY` / `API_KEY` / `ENGINE_ID` as raw substrings only. A new
  file-local helper `_forbidden_forms(*secrets)` now yields each secret **and** its
  `urllib.parse.quote_plus` form (de-duplicated), and the sweep runs over that. Reason: the three
  travel in a request URL, where a query-string value is percent-encoded — so a record quoting
  that URL carries the engine id verbatim but the query with `+` for spaces, which the raw form
  missed entirely, and the query is the item D7 names first (it is message text composed from the
  discussion). The encoded form is produced with the stdlib, never written out, so the check stays
  honest if the `QUERY` literal changes. Every previous assertion is still made (the raw forms are
  still in the tuple) and the id tag is unchanged.
- *Added.* `test_an_httpx_request_record_reaches_no_loguru_sink__S028_001_DoD11` — 2 cases,
  parametrised over `("httpx", "httpx._client")` (httpx has emitted its request record through each
  across `httpx>=0.27,<1.0`; the clause is about httpx's request log, not one spelling of its
  logger name). With the application's own logging configured, it emits one `HTTP Request: GET
  <the provider's URL with cx and q>` record through that stdlib logger at the level httpx's
  request log uses, and asserts the capturing loguru sink saw neither `HTTP Request` nor any
  forbidden form. A control record through `rphelper.tests.redaction` must be present, so absence
  proves suppression rather than a dead sink. It pins the **property** (nothing reaches the sink),
  not the mechanism — a raised level, a filter or a `propagate` change all satisfy it equally. A
  file-local `_application_logging` context manager snapshots and restores loguru's handlers and
  the stdlib root logger, redirects `sys.stderr` to a `StringIO` and points the file sink inside
  `tmp_path`, the same discipline `tests/test_logging.py` uses; `tests/test_logging.py` itself is
  **not** touched (out of 028's scope). Coverage line unchanged: DoD-11 ✓.

### Step 002 — tests (2026-10-05)

New files:

- `backend/tests/test_web_search_tool.py` — covers DoD-1 .. DoD-7, DoD-11, DoD-12, DoD-13 —
  32 test functions (61 collected cases): the three-block content, its order and the
  whitespace collapse, alone and beside plain results (DoD-1); `(untitled)` over four blank
  forms, the snippet line dropped over the same four, both at once, and the separator
  unaffected by a two-line block (DoD-2); `No web results.` / `0 results` (DoD-3);
  `3 results`, `1 results`, no title/url/snippet marker in a summary and no query echo in a
  summary built through `run` (DoD-4); `RESULT_COUNT == 5`, one request whose `q` is the
  query verbatim and whose `num` is 5, no decimal id of the scope or the arguments anywhere
  in the URL or headers, the outcome equal to `format_results` over the two faked items, and
  the query passed untrimmed (DoD-5); `{}` / `{"query": 7}` / `{"query": "   "}` each raising
  `ToolFailedError` with detail `{"tool": "web_search"}` and code `tool_failed` while the
  transport receives nothing (DoD-6); twelve unusable credential combinations giving `None`
  and `test-key` / `test-cx` giving an adapter named `web_search` (DoD-7); through 021's real
  `dispatch` on a file-local engine — a `tool_result` frame with summary `3 results`, the
  formatter's content as the tool message, one ok row named `web_search` with the summary as
  its text (DoD-11); a 500 and an `httpx.ConnectError` each giving a `tool_fail` frame with
  code `tool_failed`, the exact failure sentence, one failed row, and a level-0 loguru sink
  (message, `extra` and exception value) carrying neither the query nor either credential,
  on the failure and the success paths (DoD-12); four fresh-interpreter subprocess imports
  (each module alone and both orders) plus source/AST checks that neither module imports
  `fastapi`/`starlette` and that the adapter imports nothing from `app.config`,
  `app.secrets` or `app.db` (DoD-13).
- `backend/tests/test_web_search_offering.py` — covers DoD-8, DoD-9, DoD-10 — 14 test
  functions (29 collected cases): eight unconfigured credential combinations each giving
  exactly `memo_search` and `session_search` with each value identical (`is`) to the
  constant's, the configured builder giving those two plus `web_search` with the two still
  identical, the constant left with exactly its two keys afterwards, and assignment into the
  returned mapping raising `TypeError` (DoD-8); `offered_tools` over the configured registry
  giving the three declarations in declaration order with the `web_search` one equal to
  `definitions.py`'s, the switch off giving the first two, and the unconfigured registry with
  every switch on giving the first two (DoD-9); the real `get_tool_registry` through
  `POST …/zone/compose` on `create_app()` with a logged-in `TestClient`, a `get_settings`
  override carrying the credentials from `monkeypatch.setenv` (never a real `.env`) and a
  fake chat client that records its tools and yields one text delta — three declarations in
  order when configured with no switch set, `web_search` absent with a raw
  `UPDATE sessions SET tool_web_search = 0`, and absent again with the switch on and either
  the key or the engine id blank (DoD-10). No test in either file makes a network request:
  every provider runs over `httpx.MockTransport` and the fake chat client never calls a tool.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓,
  DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓ (the amendment below),
  DoD-15 [manual/live, no test], DoD-16 [manual/live, no test], DoD-17 [manual/live, no test].

**DoD-12 repaired after red-gate round 1 (Fault TEST, 2026-10-05).** All nine DoD-12 cases
passed vacuously against the skeleton: each asserted only the frame, the message, the row and
the captured log lines, and 021's `dispatch` turns the stub's `NotImplementedError` into
exactly the same `tool_fail` frame, code, sentence and single failed row — so the tests could
not distinguish "the provider turned a 500 or a transport error into `ToolFailedError`" (the
content of DoD-12) from "`run` does not exist yet". Repair, derived from the plan alone: the
four parametrised cases now also assert `len(recorder.requests) == 1`, so the transport is
provably reached (DoD-12's setup is "the transport answering 500" / "the transport raising",
and DoD-5 pins exactly one request; the `Recorder` appends before the handler runs, so this
holds for the raising case too); the log-failure case additionally pins the frame as
`ToolFailFrame`; and `test_a_successful_dispatch_logs_neither_the_query_nor_a_credential` now
asserts the outcome it is named for before inspecting the sink — one request, a
`ToolResultFrame` for `web_search` with summary `3 results` (DoD-11's literal for three
items). Nothing was weakened or removed; the case count is unchanged at 61.

Amendments:

- `backend/tests/test_tool_seam.py` (021's) — **one assertion, as `002.context.md` directs**:
  `ALLOWED_SERVICE_MODULES` gains `"app.services.tools.web_search"`, with an
  `# Added by 028 step 002 (S028_002_DoD14)` comment beside it in the style 026 and 027 used
  for their own additions, recording that only this module is added (the seam does not import
  `app.services.web_search` itself). The set is read by
  `test_seam_service_imports_are_within_the_allowed_set__S021_004_DoD10`, whose id tag is
  kept. **Nothing else in the file is touched** — in particular
  `test_seam_imports_no_fastapi__S021_004_DoD10` and the 021 `004` DoD-2 registry assertions
  are unchanged, because the builder returns a new mapping and never mutates the constant.
- `test_compose_route.py`, `test_memo_search_tool.py`, `test_session_search_tool.py` and
  `test_compose_source.py` are **not** touched (`002.context.md` "Deliberately not amended").

**DoD-12's two log tests widened, after the verify run's Fault SPEC (2026-10-05, user decision
criterion 3).** Additive only; the case count is unchanged at 61 and no assertion was removed.
`test_no_log_record_of_the_failure_carries_the_query_or_a_credential__S028_002_DoD12` (2 cases)
and `test_a_successful_dispatch_logs_neither_the_query_nor_a_credential__S028_002_DoD12` each
swept the captured lines for `SEAM_QUERY` / `API_KEY` / `ENGINE_ID` as raw substrings; a new
file-local `_forbidden_forms(*secrets)` helper now adds each secret's `urllib.parse.quote_plus`
form and the sweep runs over the combined, de-duplicated tuple. Same reason as step 001's
widening: the query and the engine id travel in the provider's request URL, where the query is
percent-encoded (`+` for spaces), so the raw form missed the graver of the two leaks. The
assertions the round-1 TEST repair added are **kept untouched** — `len(recorder.requests) == 1`
on both, the `ToolFailFrame` shape on the failure case, and the `ToolResultFrame` / `web_search`
/ `3 results` triple on the success case — since those are what make these tests non-vacuous.
Both id tags unchanged. Coverage line unchanged: DoD-12 ✓. The suppression itself is pinned by
the new step 001 test (criterion 4), which also satisfies this clause.

## Notes & Issues

- Step 002: gates from `backend/` green — `mypy app` Success (87 files), `ruff check .` all passed.
  Fresh-interpreter probes: `app.services.tools.web_search`, `...seam`, `app.services.tools`,
  `app.routers.stream` and `app.main` each import cleanly alone, and `web_search` + `seam` import
  cleanly in both orders. Behaviour was exercised only through an `httpx.MockTransport` scratch
  probe and `Settings(_env_file=None, ...)`; no network request and no database file touched.
- Step 002: DoD-15 / DoD-16 / DoD-17 are `[manual/live]` and were not exercised — DoD-15 reads
  `definitions.py`, which is out of this step's scope, and the other two need a real model and the
  user's real credentials.

## Ultra phase

- orient: done 2026-10-05
- harvest: done — docs/.cache/ultra/028.web-search-tool/harvest.md (1 report, incl. the sweep)
- skeleton: done — steps 001, 002
- tests: done — steps 001, 002 (approved deviations: step 001 amends `conftest.py`'s autouse
  fixture and **`test_config.py`** — the latter per decision 1, widened by the test-coder to five
  sites, not three: beyond the field-count, `OVERRIDES` and unprefixed-alias breaks, the two
  "recorded default" sweeps also break because the conftest blanking makes the new fields read
  `SecretStr("")` / `""` rather than `None`. The harvest's "SURVIVES" verdict on those two was
  evaluated before the blanking existed. Step 002 amends `test_tool_seam.py`'s allow-set only.)
- red-gate: PASS (run 2) — 4202 collected; run 1 FAIL: **002 TEST**, and a real one. All nine
  DoD-12 cases were **green against the bare skeleton**: they asserted only the frame, message,
  row and log lines, so they could not tell "the provider mapped a 500 or a transport error into
  `ToolFailedError`" — DoD-12's whole content — from "`run` is not implemented", because 021's
  `dispatch` funnels any `Exception` into the identical tool-fail frame. One was even named
  *successful* dispatch and passed while observing a tool-fail frame. The repair was spec-derived
  (DoD-12's own setup plus DoD-5's "exactly one request"): assert the transport was reached, and
  give the success test the frame and `3 results` summary it is named for. Run 2: all nine fail on
  the new assertion, the other 101 failures unchanged, ruff and mypy clean.
- code: done — steps 001, 002 (no re-freeze, no escape valve)
- verify: **FAIL (run 1) — Fault SPEC, both steps, one shared cause.** 4199 passed / 3 failed / 0
  errored; mypy clean (87 files); ruff clean; **zero regressions** — the three accepted-red
  `test_compose_route.py` DoD-10 tests and step 002's DoD-11 pair all went green, so the true-red
  trade closed exactly as recorded. Both rows set `blocked`.

### The SPEC fault — the query reaches a log record (028)

**Failing:** step 001 DoD-11 and step 002 DoD-12's log clause (3 cases). Nothing else.

**The implementation is correct against what the plan specifies.** D7 says "the provider and the
adapter emit no log records", and they emit none — neither `app/services/web_search/google.py` nor
`app/services/tools/web_search.py` imports `logging` or `loguru` at all. The key never enters a
URL; every failure path raises `from None`.

**What happens anyway.** `app/logging.py`'s `configure_logging` clears the stdlib **root** logger's
handlers, installs `InterceptHandler` and sets root to `NOTSET`. `httpx` logs every completed
request through its own `httpx._client` logger, which propagates to that root and so reaches
loguru's sinks. The record is the **full request URL** — and by D1 the request shape puts
`cx=<engine id>` and `q=<query>` in the query string. `log_console_level` defaults to `DEBUG`, so
in production **every web search logs the roleplayer's query to the console**. That is exactly what
`deployment.md` § "The redaction rule — a prohibition, with no level exception" forbids, and D7
states the query *is* message text. It only fires where an HTTP response was received, which is why
DoD-12's connect-error case passes while its 500 and success cases fail.

**Why SPEC, not CODE or TEST.** The only correct home for a fix is `app/logging.py`, whose own
docstring says no other module adds, removes or reconfigures a sink — and that file is in
**neither** step's Source files and is named nowhere in the plan. The in-scope alternative (a
provider mutating a third-party logger's level or `propagate` at import) would smuggle a global
logging change into a service module and silently change logging for `LlmClient` and every other
httpx caller. The coder had no correct move. The tests transcribe their DoD clause faithfully and
the clause transcribes `deployment.md` faithfully, so this must **not** be routed to the test-coder
— weakening it would hide a redaction breach.

**Why it never surfaced before.** `LlmClient` is the only other httpx caller and puts its payload in
the request **body**; its URL line leaks nothing. 028 is the first feature to put message text into
a URL.

**Also worth fixing in whatever clause is written:** the engine id appears verbatim, but the query
appears **URL-encoded** (`+` for spaces), so the current raw-substring check misses the graver of
the two leaks. And DoD-17's `[manual/live]` second half is the live form of this same clause — do
not attempt it as written until this is settled.

### User decision on the SPEC fault — fix `app/logging.py` (2026-10-05)

Asked to choose between fixing the bridge, amending `deployment.md`'s prohibition, or changing
D1's request shape, the user chose **fix `app/logging.py`**. It is the only route that breaks no
existing commitment: D1's request shape, D7 and the redaction rule all stay as written.

**Scope extension, recorded as decision 6.** Step `001`'s Source files gain
**`backend/app/logging.py`** — the module that owns the stdlib-to-loguru bridge and whose own
docstring reserves sink configuration to itself. Assigned to step `001` because the failing clause
(DoD-11) is step `001`'s and the provider's request is what puts the query in a URL; step `002`'s
DoD-12 log clause is satisfied by the same fix.

**Acceptance criteria for the extension** (recorded here rather than in the step file, which is
`/planner`-owned and which I do not edit):

1. `httpx`'s own request log must not reach any loguru sink — suppressed in `app/logging.py`, by
   raising that logger's level or filtering it, in the same place the module already handles
   third-party loggers. No service module may touch a third-party logger.
2. The suppression must be narrow: `LlmClient` and every other `httpx` caller keep working, and no
   other library's logging changes.
3. The existing DoD-11 / DoD-12 checks must be **widened to the URL-encoded form of the query**
   (`+` for spaces), because the raw-substring form misses the graver of the two leaks — the engine
   id appears verbatim, the query does not.
4. A test must pin the suppression itself, so a future change to `app/logging.py` cannot silently
   re-open the leak.

`outcome.md` carries the finding forward for the architect: `deployment.md`'s redaction rule now
has a named mechanism (a URL can carry message text, so the HTTP client's own request log is part
of the rule's surface), and `backend-structure.md` gains the note that `app/logging.py` owns
third-party logger suppression.

### Resolution verified — verify PASS (run 2), 2026-10-05

- verify: **PASS (run 2)** — **4204 passed / 0 failed / 0 errored** (4202 plus the new suppression
  test's 2 cases); mypy clean (87 files); **ruff clean**, and that was its first run over the widened
  tests. Frontend untouched, gates correctly not run. Both rows `done`.
- **All four acceptance criteria met.** The suppression lives in `app/logging.py` (+17/−0, purely
  additive) and is the only logger configuration anywhere under `backend/app/`; it names **one**
  logger, `httpx`, and relies on level inheritance; `_PROPAGATING_LOGGERS`, the root bridge, both
  sinks and every other library are untouched; the checks now sweep each secret **and** its
  `quote_plus` form; and a 2-case test pins the observable property with a mandatory control record
  so absence proves suppression rather than a dead sink.
- **The mechanism was independently re-derived by the verifier, not taken on trust.** A `logging`
  `Filter` on a parent logger does **not** see a child's propagated record — `Logger.handle` filters
  only on the originating logger, while `callHandlers` walks ancestors' *handlers*. A **level** is
  inherited by a child at `NOTSET`. So a filter on `httpx` would have missed `httpx._client`, which
  is where the request line is emitted; the level is the correct instrument. `CRITICAL + 1` rather
  than an in-scale threshold because `deployment.md`'s rule has **no level exception** — a threshold
  of `CRITICAL` would still pass a `CRITICAL` record and reintroduce the level-conditioned rule that
  section rejects. Accepted cost, recorded deliberately: a genuine httpx warning or error record is
  also dropped (none exists today; errors reach the app as exceptions).
- **`tests/test_logging.py` — the file the fix could most plausibly have broken — is untouched and
  green.** Its `MANAGED_LOGGERS` is `("uvicorn", "uvicorn.access", "uvicorn.error", "sqlalchemy")`,
  disjoint from the silenced tree, which is why the change is invisible to it.
- **`[manual/live]` outstanding: 4.** 001 DoD-13 (the live API accepts the `X-goog-api-key` header);
  002 DoD-15 (the shipped declaration's three justified uses — a shortfall there is a 021 `004`
  defect, not a 028 edit), DoD-16 (a real model electing to call the tool), DoD-17 (failure end to
  end). **DoD-17 is now satisfiable exactly as written**, which round 1 warned it was not: the
  leaking record is never created, and after the full suite the real log file contains zero
  occurrences of `HTTP Request`, `customsearch`, either fake credential or any seeded query.
- **Air-gap smudge, adjudicated and recorded.** The step-001 fix coder disclosed, unprompted, that a
  wide `sed` range over `status.md` scrolled the `## Tests` section past it while it was reading the
  `## Ultra phase` records I had directed it to. It opened no file under `backend/tests/`. The
  verifier judged the result sound on three grounds: the test accepts *any* mechanism, so it offered
  no shape to copy; the cheapest way to satisfy a test parametrised over two logger names would have
  been to list both, and the coder instead silenced one and reasoned about propagation; and
  `CRITICAL + 1` is stricter than the test requires (it emits at `INFO`). The code is not shaped like
  the test, and is narrower and stricter in two respects. Exposure recorded, result kept.
- **Carried forward for a later plan, not 028:** the level mechanism lapses if a future httpx release
  sets an explicit level on a child logger (inheritance stops); nothing restores
  `getLogger("httpx").level` between tests, so once any test configures logging it stays silenced for
  the process; and the `app/logging.py` invariant is currently pinned from
  `tests/test_web_search_google.py`, whose natural long-term home is
  `032.privacy-isolation-audit`'s logging-redaction-hardening step.
- **Record nits left in their owners' sections** (I do not edit another agent's record): step 001's
  `## Tests` header still says 18 functions / 40 cases, now 19 / 42 — the amendment paragraph beneath
  it is correct; and `## Skeleton` carries no entry for `app/logging.py` because the scope extension
  post-dates the freeze. Nothing needed re-freezing: no signature changed and both additions are
  private module constants.

### Accepted true-red trade (028 step 002 skeleton)

The skeleton stubbed `get_tool_registry`'s **body** (`raise NotImplementedError`) instead of
leaving `return PRODUCTION_TOOL_REGISTRY`. Reason: the constant is exactly the right answer for
every *unconfigured* assertion in step 002's DoD-8 and DoD-10, so leaving the old body would let
both pass vacuously against a skeleton that gates nothing. I accept the trade — it is the same
choice 024 made when it left dispatch conditions uncoded so "no vector work" could not pass
vacuously.

**Consequence the red gate must expect, not fault:** `test_compose_route.py`'s three
021 `006` DoD-10 tests pop the registry override and exercise the real dependency, so they fail
with `NotImplementedError` until the coder fills the body. That file is deliberately **not**
amended (028 `002.context.md` lists it under "Deliberately not amended"). **At the verify run all
three must be green again** — a failure there afterwards is a `CODE` fault, most likely the
constant being mutated or the credentials being read at import rather than per request.

### Orchestrator decisions at harvest (028)

1. **Step `001`'s Test files are extended by `backend/tests/test_config.py`.** The plan lists only
   `conftest.py`, `test_search_settings.py` and `test_web_search_google.py`, but `test_config.py`
   pins `Settings` and **cannot pass unamended**, in three places:
   - `test_settings_declares_exactly_the_named_fields__DoD1` asserts
     `set(Settings.model_fields) == set(EXPECTED_FIELDS)` and `len(...) == 11` → both break; the
     count becomes 13 and `EXPECTED_FIELDS` gains the two names with their defaults and aliases.
   - `test_field_is_populated_from_its_prefixed_environment_variable__DoD2` is parametrised over
     `EXPECTED_FIELDS` and reads `OVERRIDES`, so the new names need `OVERRIDES` entries or the
     parametrisation raises `KeyError`.
   - `test_unprefixed_variable_does_not_populate_the_field__DoD3` is a **hard break by
     construction**: it does `monkeypatch.setenv(field_name.upper(), raw)` and asserts the field
     keeps its default. For the new fields `field_name.upper()` **is** the real alias, so the
     field is populated and the assertion fails. **Exclude the two new fields from that
     parametrisation**, with a comment recording that D2 deliberately drops the `RPHELPER_`
     prefix for them. This is a recorded deviation, not a weakening: the convention the test
     guards still holds for the other eleven fields.
   Two new tests belong there too — one per alias (copying the existing
   `Settings.model_fields[...].validation_alias == ...` spelling) and one masked-`repr` test.
2. **The masked type is `pydantic.SecretStr`**, per D2 ("a secret-string type whose `repr` masks
   the value") and `001.context.md` ("pydantic's secret string"). **There is no `SecretStr` use
   anywhere in the repo today**, so this is a new convention; the only existing precedent is
   behavioural (`tests/test_secrets.py` asserts a value appears in no `repr`, `str`, `message`,
   `detail` or wire body). Step `002`'s router unwraps with `.get_secret_value()`.
3. **`routers/stream.py` imports the registry builder from `app.services.tools.seam` directly**,
   not through the package. `context.md`'s "Not touched" list names
   `app/services/tools/__init__.py` explicitly, so adding the builder to its twelve re-exports
   and `__all__` is out of scope. This is a deliberate, recorded departure from that file's
   existing package-level import style (`stream.py:69`). No test pins `stream.py`'s imports.
4. **The builder takes two plain `str | None` values**, not a `Settings` — the plan's own
   Interface intent, and it keeps the seam settings-free like `app/services/llm/client.py`.
   Importing `app.config` into `seam.py` would in fact pass the DoD-10 allow-set test (it
   constrains only `app.services.*`), which makes the discipline worth stating rather than
   relying on the test.
5. **The `conftest.py` blanking is load-bearing for *existing* tests, not only new ones.** The
   four registry assertions 028 deliberately does not amend (021 `004` DoD-2, 021 `006` DoD-10,
   026 `002` DoD-11, 027 `003` DoD-11) survive **only** because every test sees an unconfigured
   instance. In particular `test_compose_route.py`'s three DoD-10 tests pop the registry
   override and seed all three switches on, so on a developer machine with real
   `SEARCH_CSE_KEY` / `SEARCH_CSE_ID` exported they would start failing **without** the
   blanking. `monkeypatch.setenv(name, "")` is required rather than `delenv`, because
   pydantic-settings reads the environment above `env_file` and a blank present value is what
   stops `backend/.env` supplying a real credential.
