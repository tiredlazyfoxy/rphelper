# Quick reference

Dense, agent-first index of `docs/architecture/`. Exempt from the doc-length
rule. Every line here is a pointer or a fact — the reasoning lives in the doc
named beside it. **Where this file and another doc disagree, the other doc wins.**

Recomputed at the finalization of plans 008..032 (2026-10-06), after that pass's
four batches landed.

## Doc map — where to look for what

**Fifteen docs.**

| Doc | Read it when you need |
|---|---|
| `overview.md` | System context, actor→surface map, **the outbound surface in full (the three destinations, including the search provider)**, topology, **the full stack decision list with rationale** including the six post-first-pass decisions, the deferred list, the non-functional posture |
| `quick-reference.md` | This file — the index |
| `data-model.md` | Tables and columns, **snowflake identifiers** (+ the sparse-rowid verification and the one forbidden query form), the one fixed-width timestamp form (+ its known `users` deviation), ownership/isolation columns **and what they do not guarantee**, `users` / `auth_sessions` / `llm_servers` / `models` as built, `characters` / `setups` / `sessions` as built (the captured model pair, **no `title`**), the merged `messages` table and **the four named Core selectables over it — not SQL views**, `translations`, `memos` (`sort_key`'s allocation, the orphan-scope check), archive semantics, the `vec0` tables, the two FTS5 tables and their exact trigger conditions (`session_fts` **declared and never created**), drift as built |
| `domain-rules.md` | **The role ladder + R1–R12, the cross-cutting invariants.** Read before touching any feature |
| `backend-structure.md` | FastAPI layout, routers/services split **and the service-to-service import pattern**, the JSON id boundary **and its two named exceptions**, `require_role` / `require_user` / `require_unconfigured`, the bootstrap / auth / three admin / six roleplayer route surfaces, **every route is classified at build time**, the typed error model and **the per-code status record**, the 500 posture, `/api/health`, configuration (`Settings`) and the `"$ENV_VAR"` secret pointer, database access (engine, PRAGMAs, transactional DDL, `get_connection`), **SQLAlchemy Core**, schema evolution (registry + admin-applied Alembic batch DDL), the two transaction rules and their asymmetry, the logging call site |
| `session-stream.md` | **The session stream's backend**: the route surface and the twelve-key wire shape, `PATCH`'s reach, create-and-seed (UC-080), settle and re-open, the degraded embedding path, the `(( ))` seam, the compose route and its streaming harness, the tool seam and dispatch, the discussion read |
| `transfer.md` | **Export and import**: the envelope, the id-serialization rules, the two version constants, the four granularities, what is never exported, the export and import route surfaces, the import policy (mint + remap), the whole-database replace |
| `frontend-structure.md` | Vite multi-entry (`root: src/`, the emitted layout), the four entries' boot shapes, **the case-collision naming rule**, pure-data-contract MobX (four rules + five conventions + which store a list belongs to), routing inside the `app` entry, **"ids are strings" and the test that enforces it**, the API client (`ApiError`, `apiPut` / `apiDownload` / `importFile`, the `client_*` codes), the SSE consumer's four outcomes and frame handling, markdown (the one `MarkdownEditor` and its emit rules, the one `MessageBody`), the two stylesheets |
| `workspace-shell.md` | The `app` entry's screens: the three columns, **all geometry**, the narrow-width behaviour, the wall's two modes, layout persistence, the stream and its per-entry actions, the buried-discussion group, the search-coverage banner, the ruler and the current zone (editability, tool/thinking blocks, the live reply, Regenerate, the model gate), the kind switch and settle, the `(( ))` preview and painting, the stop control, discarding an empty zone, the wall's contents and note drag, **the character page**, **the draft page**, **the user menu**, **the model picker**, and the reversal record for the deleted splitters |
| `ui-conventions.md` | Icons + the shared `IconButton` + the full icon table, the accessibility floor, **async feedback** (no success toasts, the failure channel, the one bounded warning, the two sanctioned importers), the inherited frontend facts. **The CRUD conventions are no longer here** |
| `forms-and-lists.md` | Tables and lists, **no sorting/filtering/pagination**, loading / error / empty states, **create and edit are always a `Modal`** and its three named exceptions, the MobX draft convention, **mutations are never optimistic** and its one exception (note reordering), the confirm convention and what is deliberately not confirmed, page state |
| `admin-surfaces.md` | The `admin` entry in full: 3 routes + 404, shell (no user menu, no sign-out), the admin gate and why it deviates, the Users / LLM Servers / Database pages each with its as-built state, the drift report's granularity and statuses, Create/Sync postconditions, the surviving derived-tables gap, the whole-database export/import controls and their opacity |
| `llm-and-streaming.md` | The one LLM client (`chat_stream` / `embed` / `probe`), use-time validation and `resolve_model_for_use`, the SSE frame protocol, **the four ways a stream ends**, the `<think>` convention, **"Stopping, and what a stop is not"** (UC-085), the tool loop (**no iteration cap**), `web_search`'s provider seam, **context assembly** and its exclusions, language handling, translation |
| `search-and-retrieval.md` | Hybrid vec+FTS+RRF, the narrow port and its **three variants**, **the forbidden KNN form**, `memo_search`, `session_search` (**vector arm only**), my-search (three port variants + two `LIKE` corpora), the persona-edit fan-out, the embedding lifecycle and its two write postures, rebuild |
| `deployment.md` | Ports, TLS (none — **and the clipboard consequence**), the three dev launch paths (`start.ps1`, `start.sh`, `docker-compose.dev.yml`), prod topology, the single-generator guarantee, nginx directives (the five deliberate deviations, **the app document at `/` in prod and dev — one URL space, the dev routing plugin**, and the two open seams), compose, configuration conventions (incl. the two unprefixed search variables), **logging** (loguru, two sinks, the redaction rule, the access-log filter), operational notes |

Requirements are **not** here. They are in `docs/product/` and are cited by id.
The id registry is `docs/product/quick-reference.md`.

**Splitting note.** A doc splits when it has come to cover **two subjects**, not
when it crosses a line count (`CLAUDE.md`).

**Three splits were authorized and are done** at this finalization: the twelve
docs became fifteen. `session-stream.md` and `transfer.md` came out of
`backend-structure.md` (and `data-model.md`'s export/import contract);
`forms-and-lists.md` came out of `ui-conventions.md`. Each origin doc keeps a
one-line pointer where the content left.

**Three further splits are identified and NOT authorized** — a new top-level doc
must come from the architect's briefing. They are recorded in
`docs/architecture/CLAUDE.md` with their real line counts and the seam each
names: `backend-structure.md` (route surfaces vs the application and persistence
layer), `workspace-shell.md` (the character page), and `llm-and-streaming.md`
(context assembly → `context-assembly.md`). **None is done.**
`search-and-retrieval.md` is a recorded deliberate exception under pressure, not
a candidate — splitting it would overturn the exception's own reason.

## Ports

| Role | Port |
|---|---|
| uvicorn / FastAPI (dev; loopback-only in prod) | **8184** |
| Vite dev server | **8193** |
| nginx published by compose | **8193** → container `:80` |

RPHelper = BookWriter minus 1, so both run in parallel. **Vite dev server and
dev-compose nginx share 8193 — run one or the other, never both.** No TLS
anywhere (`_TBD:` in `deployment.md`).

## Commands

Canonical source is the **root `CLAUDE.md`**. Repeated here for lookup only:

```
Backend  (run from backend/)
  test       .venv/Scripts/python -m pytest
  typecheck  .venv/Scripts/python -m mypy app
  lint       .venv/Scripts/python -m ruff check .
Frontend (run from frontend/)
  build      npm run build
  test       npm test
  typecheck  npm run typecheck
```

Dev: `start.ps1 -app` and `start.ps1 -ui` in **separate terminals**.

## Backend toolchain and packaging

- **One PEP 621 `backend/pyproject.toml`** holds runtime deps, dev deps and the
  `[tool.ruff]` / `[tool.mypy]` / `[tool.pytest.ini_options]` config. **No
  `requirements.txt`, no separate tool config files.**
- Virtualenv at **`backend/.venv`** via `uv venv`; dependencies installed with
  **`uv sync`**; **`uv.lock` committed**, regenerated by `uv sync`, never
  hand-edited.
- **Minimum Python 3.12.**
- **`sqlite-vec==0.1.9`**, pinned exactly; a failed load raises
  (`ExtensionLoadError`) rather than handing out a connection without it.
- **`alembic` is a RUNTIME dependency** (plan 007) — batch DDL only. Its four
  negatives are verifier-checked: **no `versions/`, no revision chain, no version
  table, no startup upgrade**. Only `MigrationContext` + `Operations` +
  `batch_alter_table` (recreate mode) are used.
- **`httpx` is a RUNTIME dependency** (plan 006) — `httpx.AsyncClient`, the first
  outbound-HTTP and first async code in `app/`.
- **Two async postures, and they must not be mixed** (`backend-structure.md`):
  the three network-reaching registry operations and their routes are `async def`
  over a **sync** `Connection`; the **embedding writes are sync services calling
  `LlmClient.embed` through `asyncio.run`**, which is legal only because the
  routes above them are sync `def` — **making one of those `async def` raises**.

## Configuration

- **`RPHELPER_LLM_REQUEST_TIMEOUT_SECONDS`** — default **30.0** (plan 006). It is
  also what the **streaming** call uses, 30 s per httpx phase including the read
  between chunks (open `_TBD:`, `llm-and-streaming.md`).
- **Five logging fields** — `RPHELPER_LOG_CONSOLE_LEVEL` (`DEBUG`),
  `RPHELPER_LOG_FILE_LEVEL` (`WARNING`), `RPHELPER_LOG_FILE_PATH`
  (`data/logs/rphelper.log`), `RPHELPER_LOG_FILE_ROTATION` (`"10 MB"`),
  `RPHELPER_LOG_FILE_RETENTION` (`5`).
- **`SEARCH_CSE_KEY` and `SEARCH_CSE_ID`** (plan 028) — Google Custom Search's
  API key (a secret-string type, **masked in `repr`**) and engine id (`cx`). Both
  **optional with no default**; **both blank or missing → `web_search` is simply
  not offered**, with no error and no degraded mode.
  **They deliberately carry NO `RPHELPER_` prefix** — a named exception, user
  confirmed, because they are the user's existing environment variable names.
  "Fixing" them to `RPHELPER_SEARCH_CSE_*` breaks nothing loudly and **silently
  unconfigures web search** on every working instance.
  `routers/stream.py`'s registry dependency is the only reader of either field.
- The full `Settings` model is `backend-structure.md`'s. Explicit validation
  aliases, `lru_cache` accessor, env file relative to the backend working
  directory. **Ports are not settings.**

## Backend test conventions

- **The database fixture is a real `.sqlite` file under pytest's `tmp_path`, one
  per test**, obtained through the same engine factory production uses. Not
  `:memory:` — that makes WAL a no-op and takes a different extension-load path.
  Not a shared session-scoped database — that leaks DDL state between tests.
- **Environment isolation:** every `RPHELPER_*` variable and the settings
  accessor's `lru_cache` are cleared around each test.
- **The shared isolation also sets `SEARCH_CSE_KEY` and `SEARCH_CSE_ID` to `""`
  for every test** (028 D12). They carry no `RPHELPER_` prefix, so the sweep above
  does not reach them — and without this a developer's own `.env` would let a test
  reach Google. Any new unprefixed setting needs the same treatment explicitly.
- Two named enforcement tests for the redaction rule:
  **`backend/tests/test_logging_redaction.py`** and
  **`backend/tests/test_privacy_audit_logs.py`** (a dynamic sentinel sweep at
  level 0). Two more for R5: **`test_privacy_audit_routes.py`** (the
  route-classification guard — **an unclassified route fails the build**) and
  **`test_privacy_audit_search_tools.py`** (cross-user proof for my-search, the
  port, the three tools and the vector/FTS write paths).

## Frontend toolchain, packaging and tests

- **One `frontend/package.json`** — dependencies and four scripts (`build`,
  `test`, `typecheck`, `dev`); **`package-lock.json` committed**.
- **Two tsconfigs**: `tsconfig.json` (`strict`, `src/` + `tests/`) and
  `tsconfig.node.json` (`vite.config.ts`). No `paths` aliases.
  `noUnusedLocals` / `noUnusedParameters` / `noFallthroughCasesInSwitch` on;
  **`exactOptionalPropertyTypes` and `noUncheckedIndexedAccess` deliberately
  OFF**. **`allowImportingTsExtensions` is set in neither.**
- **One `vite.config.ts` that also carries the Vitest block** — there is no
  `vitest.config.*`. The build is **rooted at `frontend/src`** and emits to
  **`frontend/dist`**; the Vitest block keeps **`frontend/`** as its root.
- Test stack: **Vitest + Testing Library + jsdom**; `npm test` runs once and
  exits. **No ESLint, no JS linter** — `tsc --noEmit` is the gate, and a rule a
  linter would have grepped becomes a Vitest test.
- **Tests live under `frontend/tests/`, outside `src/`, mirroring it.**
  `frontend/tests/setup.ts` is harness source, not a test.
- **Three convention tests to know about:** the ids scan (an `id`-suffixed binding
  annotated `number`, `parseInt`, `Number.parseInt` — no exception list, no
  suppression comment), **`tests/stylesheets.test.ts`** (what `shell.css` may
  hold), and **`tests/conventions.test.ts`** (the `@mantine/notifications`
  importer set).
- **No two module paths may differ only in letter case** (008 D13). The
  filesystem is case-insensitive and TypeScript's resolver is not, so `tsc` picks
  the `.tsx` and Vite/Vitest pick the `.ts` from one specifier — a green typecheck
  and an `undefined` import at runtime, reported as "React says the element type
  is undefined". The worked example: `appBoot.ts` beside `AppBoot.tsx`, which is
  why the boot state ships as **`appBootState.ts`**.

## Paths

```
backend/app/{routers,services,models,db}/     backend code (mypy target: app)
backend/app/ids.py                            the snowflake generator (not services/, not db/)
backend/app/roles.py                          Role enum + ROLE_LADDER + pure rung comparison; NO fastapi
backend/app/dependencies.py                   CurrentUser, require_user, require_role(min_role),
                                              the session-cookie set/clear writers, get_llm_client_factory
backend/app/errors.py                         the typed hierarchy + register_exception_handlers(app);
                                              the ONE framework-coupled leaf every service may import
backend/app/logging.py                        loguru sinks + InterceptHandler + _SILENCED_LOGGERS /
                                              _PROPAGATING_LOGGERS; called ONCE from main.py
backend/app/secrets.py                        "$ENV_VAR" pointer resolution
backend/app/db/{schema,drift,sync}.py          registry + the four named selectables / introspection /
                                              Alembic batch DDL; sync.py may import drift.py, never the reverse
backend/app/db/search_tables.py               the vec0 + FTS5 tables and the FTS triggers — OUTSIDE metadata
backend/app/db/engine.py                      one connect listener, per-path engine cache, get_connection
backend/app/models/secret_ref.py              the "$"-pointer field type — a non-"$" value is FastAPI's 422
backend/app/models/ids.py                     SnowflakeOut / SnowflakeIn — the ONLY id conversion site
backend/app/routers/bootstrap.py              also declares require_unconfigured (its only consumer)
backend/app/routers/stream.py                 the stream + the chat-client and tool-registry dependencies
backend/app/routers/{characters,setups,sessions}.py       FEAT-006 / 007 / 008
backend/app/routers/{configuration,translation,memos,search,transfer}.py
backend/app/services/parens.py                the (( )) parser: classify + strip. Pure, no I/O
backend/app/services/settle.py                settle + re-open — the ONLY writers of the burial/settle columns
backend/app/services/messages.py              zone append, append_assistant_message, edit text, partner
                                              filing, list_discussion, the tool-view derivation
backend/app/services/context.py               context assembly — no router; its only caller is compose.py
backend/app/services/compose.py               compose_stream + begin_compose
backend/app/services/memo_chain.py            resolve_chain + memo_reach + the chain CLAUSE BUILDER (R2's one home)
backend/app/services/{embedding,session_index}.py          the embed call + vector upsert/delete; session_vec + the fan-out
backend/app/services/tools/{definitions,seam,memo_search,session_search,web_search}.py
backend/app/services/web_search/{provider,google}.py       the provider protocol + Google Custom Search
backend/app/services/search/{ports,candidates,lexical,vector,hybrid}.py     the hybrid port
backend/app/services/search/{memo_search,session_search,my_search}.py       its three callers
backend/app/services/llm/{client,chat,frames}.py           the one client; ChatMessage + strip_think;
                                                           the frame types, encoder and streaming harness
backend/app/services/{transfer,transfer_import}.py         export only (read-only) / import + the replace
backend/tests/                                pytest target
backend/pyproject.toml + backend/uv.lock      backend deps + tool config; lock committed

frontend/src/{bootstrap,login,admin,app}/     the four Vite entries
frontend/src/shared/                          api.ts (+ apiPut, apiDownload, the two exported decode
                                              helpers), sse.ts, apiError, notReady, IconButton,
                                              AppProviders, notifyFailure, notifyWarning, ConfirmModal,
                                              currentUser, MarkdownEditor, importFile, embeddingFailure
frontend/src/shared/notReady.ts               the one not-ready-yet predicate; used by bootstrap AND the admin gate
frontend/src/shared/ConfirmModal.tsx          the one confirm component; cancel left of confirm
frontend/src/shared/importFile.ts             readExportFile (parses client-side) + postExportFile; NO FormData
frontend/src/admin/                           gate, not-ready screen, shell state, nav table, shell, 404,
                                              app, page store, drafts — all beside main.tsx
frontend/src/app/appBootState.ts              the app entry's boot state (named for the case-collision rule)
frontend/src/app/{shellState,workspaceLayout,treeCollapse}.ts        the shell + two of the three PURE persistence modules
frontend/src/app/composerHeights.ts           PURE — the third persistence module (suggested name; NOT YET BUILT, 2026-10-08)
frontend/src/app/{charactersState,sessionsState}.ts                  the two workspace-level list stores
frontend/src/app/{sessionScreenState,sessionsSectionState}.ts
frontend/src/app/{streamState,streamApi}.ts   the stream's store (one per SessionStream mount) + its seven calls
frontend/src/app/parens.ts                    PURE — the one client port of the (( )) rules
frontend/src/app/{plainText,pasteCost,copyOut}.ts    PURE stripper, PURE paste estimate, the one clipboard writer
frontend/src/app/thinking.ts                  PURE — splits assistant text into think/answer segments
frontend/src/app/{memoReach,memoReorder,memoDnd}.ts  the reach derivation, the pure drop decision + effect,
                                              the SHARED sensors + position-only announcements
frontend/src/app/noteWallState.ts             the wall's data class + free functions
frontend/src/app/translationState.ts          one per SessionStream mount; flick / cancel / invalidate / dispose
frontend/src/app/{characterComposerState,characterConfigState}.ts    the character page's two section stores
frontend/src/app/{searchState,searchApi}.ts   my-search's page store + client
frontend/src/app/importUploads.ts             the three roleplayer import effects
frontend/src/app/MessageBody.tsx              the stream's ONE renderer, three variants
frontend/src/app/{StreamRecord,ZoneList,KindSwitch,Composer,SessionStream}.tsx
frontend/src/app/{AssistantBody,ThinkingBlock,ToolBlock,LiveMessage,DiscussionGroup,SearchScreen}.tsx
frontend/src/<entry>/<page>State.ts, *Draft.ts   a single-entry store lives in its entry folder beside main.tsx
frontend/tests/                               Vitest target — outside src/, mirrors it
frontend/dist/{bootstrap,login,admin,app}/index.html   the emitted layout nginx resolves against
frontend/src/global.css                       hand-written stylesheet 1 of 2 — resets only; imported by AppProviders
frontend/src/shell.css                        hand-written stylesheet 2 of 2 — workspace layout only;
                                              imported by src/app/main.tsx alone
data/rphelper.sqlite                          state 1 of 2; /app/data in prod
data/logs/rphelper.log                        state 2 of 2 — the rotating sink (data/ is the only writable volume)
docs/product/                                 requirements — read-only
docs/product/quick-reference.md               the id registry
docs/architecture/                            this doc set
docs/plans/CLAUDE.md                          the pipeline contract
docs/plans/defects.md                         the five defects' file of record (the product round's artifact)
```

**`ComposerCore` is the shared composer** (018 D4) — the text area, the geometry,
the labelled Send, the enormous-paste warning and the send-blocked reason — with
the stream's `Composer` and the character page's `CharacterComposer` as its two
hosts, adding their own controls through slots. No second composer exists. The
per-host default line count (3 / 10) and persisted-height field (`chat` /
`start`) are a **parameter** of `ComposerCore` (2026-10-08; prop shape is the
building plan's call).

localStorage keys — **four keys, never consolidated**:

| Key | Module | Scope |
|---|---|---|
| **`rphelper.workspace-layout`** | `app/workspaceLayout.ts` | the `app` entry only — `{ navCollapsed, wallPinned }`, two booleans and no numbers |
| **`rphelper.tree-collapsed`** | `app/treeCollapse.ts` | the `app` entry only — a JSON array of collapsed character ids (strings) |
| **`rphelper.composer-heights`** | `app/composerHeights.ts` (suggested; **not yet built**) | the `app` entry only — `{ chat: number \| null, start: number \| null }`, pixel heights, `null` = default rows; written on drag end; no upper clamp |
| **`rphelper.color-scheme`** | Mantine's `localStorageColorSchemeManager` (`overview.md`) | all four entries; both schemes, dark default |

**The three `app` records are three keys deliberately** (011 D7, extended
2026-10-08): the layout reader **drops unknown keys on write**, so a client
version that had not grown a `treeCollapsed` field — or the composer heights —
would silently delete another version's data. A reader that drops unknowns is
safe only while it owns everything in its own key.
Folding the colour scheme into any of them would make the login page's scheme
depend on a workspace record.

All three `app` modules are **pure and DOM-free — the storage is passed in as a
parameter** (008 D8), a minimal `getItem`/`setItem` interface or `null`. Read is
**total and never throws** (a throwing `getItem` is a per-field fallback case, not
an exception); write is **best-effort** over a fresh total read — on the toggle
for the first two, on drag end for the composer heights.

## Ids — the one rule that fails silently

**Every primary key is a snowflake** minted in application code before the INSERT
(`data-model.md`'s Identifiers section; 41-bit ms epoch `2026-01-01Z` / 10-bit node
id / 12-bit sequence). No `AUTOINCREMENT`, no `position` column — `ORDER BY id`
**is** the stream order.

**The boundary rule, stated in four docs because it fails silently and late:**

```
int64      in SQLite and in Python
decimal    STRING in every JSON payload — request body, response body,
           a DomainError's `detail`, every SSE frame, and the export envelope
string     in TypeScript, end to end
```

- **A TypeScript `id: number` anywhere is a defect**, and **a test enforces it**
  (`frontend-structure.md`). No `parseInt`, no numeric sort, no arithmetic.
- **A bare `int` id field on a pydantic model is the defect on the backend side.**
  `models/` converts, and only `models/` (`SnowflakeOut` / `SnowflakeIn`) —
  **including path parameters**, never a bare `int` path type.
- Reason: a snowflake passes `Number.MAX_SAFE_INTEGER` about **25 days** after the
  epoch, so an id reaching JS as a number rounds — possibly onto another row's id.
- **SSE frames carry the rule in full**: `accepted.message_id` and
  `done.message_id` are strings, and they name **different rows** (the
  roleplayer's committed message, and the assistant's). `call_id` is **not** an id
  in this sense — it is the provider's opaque tool-call identifier, with a
  `call_<n>` fallback when the provider supplies none.
- **The export envelope carries it too**, and by a **name rule** as well as by
  metadata: an integer column is stringified when it is part of the primary key,
  **or** carries a foreign key, **or** is named `id` / `*_id`. The name rule
  exists for exactly two FK-less references — **`memos.scope_id`** and
  **`model_server_id`** on `characters` and `sessions` (`transfer.md`).
- **Two named exceptions to "routes return and take pydantic models"**, both
  FEAT-018's: the export routes return a raw `Response`, the import routes take a
  raw JSON object body. The id boundary still holds — the serializer stringifies
  before the router sees the body, and the deserializer accepts decimal strings
  only.
- **Ids are not secrets**, and that grants nothing: every read path is scoped by
  `user_id` at the query level (R5), and **refusal identity** makes a foreign id
  answer identically to an unknown one.
- **Import mints FRESH ids at the roleplayer's three granularities and PRESERVES
  them at the fourth.** `US-136.AC-2` plus `US-136`'s `Constraint:` scope
  minting to `user` / `character` / `session`; the **whole-database import is a
  replace that preserves the export's own ids** (`UC-061`, `US-077.AC-2`).
  Minting is **per table in ascending old-id order**, so a session's stream order
  survives (`transfer.md`).
- **Ordering never comes from an id on the client.** The one client-side sort —
  the tree, by newest session use — compares **fixed-width `last_used_at` text**.

**Flip condition:** the layout *and* the string boundary assume **exactly one
generator process per node id** (one container, one uvicorn — `deployment.md`). A
second worker or a syncing second instance re-opens both.

## Timestamps — one fixed-width text form

Every stored timestamp is UTC ISO-8601 **text**, **microsecond precision, explicit
`+00:00`** (`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`) — because these columns are
compared **as text** (`auth_sessions.expires_at` on every request, and the tree's
sort reads `last_used_at` as a string), and mixed forms compare silently wrong
(`data-model.md`). **Known deviation, not yet fixed:** `users.created_at` /
`updated_at` from plan 003 use plain `isoformat()` (microseconds dropped when
zero) — a **pre-existing defect** owned by a `/bug-fixer` pass against plan 003.
It is **not** one of the five defects below.

**Every write in one operation uses one instant**, and each service carries its
own private `_now_text()` rather than importing a sibling's.

## Stack

FastAPI + `pydantic-settings` · **uv** (committed `uv.lock`) · **SQLAlchemy Core
(not the ORM)** · SQLite (one file: rows + `sqlite-vec` **`==0.1.9`** `vec0` +
FTS5) · **Alembic — batch DDL only, not a migration framework** (no `versions/`,
no version table, no startup upgrade; `db/schema.py` is the source of truth and
the admin drift page applies) · **`loguru`** (two sinks: console `DEBUG` +
rotating file `WARNING` at `data/logs/`; the **`InterceptHandler` is
load-bearing**; **`diagnose=False` and `backtrace=False` on BOTH sinks**;
**absolute redaction rule at every level** — `deployment.md`) ·
`httpx.AsyncClient` · **Argon2id via `argon2-cffi`, library defaults** (passwords
only) · **pysqlite with transactional DDL** (`begin()` covers `CREATE TABLE`) ·
React 19 + TS + Vite multi-entry · Mantine 7
(`core`/`hooks`/`tiptap`/**`notifications`**; **`form` is NOT a dependency**;
**`AppShell` in the `admin` entry only**) · MobX 6 + `mobx-react-lite` ·
`react-router-dom` 7 · `@tabler/icons-react` `^3.40` · TipTap (**pinned to major
2**) + `tiptap-markdown` (edit) + **`react-markdown`** (render, a real dependency
since plan 013) · **`@dnd-kit/core` + `@dnd-kit/sortable` + `@dnd-kit/utilities`**
· SSE over POST · HttpOnly `SameSite=Lax` cookie over **server-side
`auth_sessions`** (opaque 32-byte token, stored as a SHA-256 digest, absolute
720 h) · nginx + uvicorn under `supervisord` in one container.

No Tailwind / CSS modules / styled-components. **Exactly two hand-written
stylesheets:** `global.css` (resets only, imported by `shared/AppProviders`
*after* Mantine's sheets so resets win the cascade) and `shell.css` (the `app`
workspace's layout only, imported by `src/app/main.tsx` alone). Everything else
is Mantine. **`postcss-preset-mantine` is not installed.**

**TypeScript only — no JavaScript source.** Every authored file under `frontend/`
— components, stores, tests, and Node-side config such as `vite.config.ts` — is
`.ts` / `.tsx`. No `.js` / `.jsx` / `.mjs` / `.cjs`, no `allowJs`, no `checkJs`.

### Dependencies with a bounded sanctioned use

| Dependency | Bound |
|---|---|
| **`@mantine/notifications`** | **exactly TWO sanctioned importers — `shared/notifyFailure.ts` and `shared/notifyWarning.ts` — and `tests/conventions.test.ts` pins the set.** The outlet is mounted once by `shared/AppProviders` with `autoClose: 5000`, so no call site picks a timeout. Neither function has a success path or a colour parameter |
| **`@dnd-kit`** (three packages) | **one interaction, two mount points**: reordering notes within a level, on the wall and on the character page's notes grid. Sensors and position-only announcements shared through `app/memoDnd.ts`, so two `DndContext`s keep **one** keyboard path. Nothing else may use it without a requirement |
| **`react-markdown`** | read surfaces only — settled entries, zone messages, read-only notes, through the one `app/MessageBody.tsx`. **Search snippets render as plain text, not markdown** (029 D7): a snippet is a cut fragment and may open a structure it never closes |
| **TipTap + `tiptap-markdown` + `@mantine/tiptap`** | editing only, through the one `shared/MarkdownEditor.tsx`. **Pinned to TipTap major 2** |
| **`@mantine/hooks`** | **non-stateful helpers only** — a custom hook must not hold reactive state. Three sanctioned uses: `useMediaQuery(NARROW_VIEWPORT_QUERY)`, `useHover` + `useFocusWithin` for the stream's revealed actions, and `useMediaQuery("(hover: none)")` beside them. `useDisclosure` appears nowhere |

## The four frontend entries

| Entry | Actor | Realizes |
|---|---|---|
| `bootstrap` | ACT-003, pre-database | FEAT-001 |
| `login` | unauthenticated | FEAT-002 |
| `admin` | ACT-001 | FEAT-003, FEAT-004, FEAT-005, FEAT-018 (admin half) |
| `app` | ACT-002 | FEAT-006..FEAT-013, FEAT-017, FEAT-018 (user half), FEAT-020 |

Why: admin code never ships in the roleplayer's bundle (FEAT-019), and the
pre-database bootstrap state need not coexist with the authenticated shell.
Cross-entry navigation is a **document** navigation; the cookie travels with it.
**`bootstrap`, `login` and `app` declare no basename**; `admin` declares
`"/admin"` with **no** trailing slash while nginx serves `/admin/` **with** one —
two near-identical strings in two files, and making them agree breaks the match.

**The `app` entry's boot has five outcomes**, the same five the `admin` gate has:
nothing rendered in flight; 401 (**branched on the code `not_authenticated`**, not
the status) → the shared client has already navigated; not-ready → re-probe every
2000 ms; anything else thrown → failure panel + manual retry; success for
**either role** → the shell. **There is no role branch.**

## Routing inside the `app` entry

```
/                       the workspace, no session open — tree + empty stream, NO wall (US-095)
/sessions/:id           tree | stream | wall
   ?entry=<messageId>     scroll that settled entry into view once + highlight 2000 ms
   ?notes=open            open the note wall on arrival
/characters/:id         the character page — two columns (UC-073, US-096)
/characters/new         the character draft page (UC-074, US-097)
/settings               the two languages and the user's own notes (US-092)
/search?q=<text>        my-search results (FEAT-017)
```

Six routes, **declared flat and from the start**, shell above `<Routes>`, the
catch-all 404 **inside** the shell. **Setups have no route.** `/memos` is gone.
**Only the screen component reads the URL; its children take props** (plan 029) —
`SessionScreen` may call a router hook, `SessionStream` and `StreamRecord` may
not, because they are mounted router-free in seven delivered test suites.
`useNavigate` is the accepted form when a navigation follows from choosing a
control rather than following a link (the user menu's Settings item).

## Roles — the ladder

```
{ roleplayer: 0, admin: 1 }        roleplayer = ACT-002, admin = ACT-001
```

`users.role` is an enum column, not an `is_admin` boolean. Backend:
`require_role(min_role)` dependency **factory** at **router level** on all three
admin routers. Frontend gating is **UX only**. `app/roles.py` = enum + ladder +
pure comparison, **no `fastapi`** (`db/schema.py` imports it);
`app/dependencies.py` = `CurrentUser`, `require_user`, `require_role`, the two
cookie writers, `get_llm_client_factory`. `require_user` resolves cookie → digest
→ live, unrevoked, unexpired `auth_sessions` row → enabled `users` row → **role
read live**, so a role change or disable bites on the **next request**.
`require_unconfigured` lives in `routers/bootstrap.py`.

**An admin calling a roleplayer route is an ordinary owner, never a
super-reader** (R5, asserted by plan 032's audit).

## Route surfaces — the whole API

All under `/api`. Ids in paths use the `models/ids.py` inbound alias. Lists are
**wrapped** (`{ characters: [...] }` …) so a list response can grow a sibling key.
**No entity has a `DELETE` except a memo.** Archive and restore are **named action
routes**, never a `PATCH` of a status field. Routers group **by feature, not by
path prefix**.

### Bootstrap, auth and health

| Route | Answers |
|---|---|
| `POST /api/bootstrap/create` | **201** + identity **+ `Set-Cookie`** (same transaction as `create_all` + the admin insert); no token in the body; router-level `require_unconfigured` |
| `POST /api/bootstrap/import` | reserved — `fast/003.bootstrap-from-export` (UC-002 deferred) |
| `POST /api/auth/login` | **200** + identity + `Set-Cookie`; **never 401**; any failure = `invalid_credentials` **400**, uniform for unknown user / wrong password / disabled (US-006.AC-3) |
| `POST /api/auth/logout` | **204**, idempotent, **no `require_user`**, revokes the calling session only |
| `GET /api/me` | `{id, username, role}`, `id` a decimal string; **401** `not_authenticated`. **Unchanged by FEAT-013** — settings are their own pair |
| `GET /api/health` | unauthenticated roll-up, **200 whatever it says**; `schema` precedence `missing` > `drift` > `ok` |

### Admin — `require_role(Role.admin)` once per router

| Prefix | Routes |
|---|---|
| `/api/admin/users` (plan 005) | `GET`, `POST` (201), `POST /{user_id}/{disable\|enable\|password\|role}` — **six**, named actions, not one `PATCH`; no query params |
| `/api/admin/llm-servers` (plan 006) | **nine**: `GET` (rows carry enabled model names), `POST` (201), `PATCH /{id}`, `DELETE /{id}` (204), `POST /{id}/test`, `GET /{id}/available-models`, `POST /{id}/models` (replace set; POST not PUT), `POST` / `DELETE /{id}/embedding-model` |
| `/api/admin/database` (plans 007, 030, 031) | **five**: `GET /tables`, `POST /tables/{table_name}/create`, `POST /tables/{table_name}/sync` (all 200, no body, no query, no ids on the wire; the apply answers the **re-derived** row; `{table_name}` resolved **in `db/sync.py`**, never interpolated), `GET /export` (the whole-database export as a file attachment), `POST /import` (**204** + the session cookie cleared; the **first** admin-database route with a body, and a raw JSON object) |

### Roleplayer — router-level `require_user`

| Family | Routes |
|---|---|
| **characters** (009) | `GET /api/characters` (`include_archived`; order `created_at DESC, id DESC`) · `POST` (201) · `GET` / `PATCH /{character_id}` (a null key is absent; an empty `PATCH` is a no-op) · `POST /{character_id}/archive` · `/restore` (idempotent) |
| **setups** (010) | `GET` / `POST /api/characters/{character_id}/setups` (`include_archived`) · `GET` / `PATCH /api/setups/{setup_id}` · `POST /api/setups/{setup_id}/archive` · `/restore`. **Nested collection, flat single resource** — `character_id` is fixed for a setup's life |
| **sessions** (011) | `GET /api/sessions` · `GET /api/characters/{character_id}/sessions` · `GET /api/sessions/{session_id}` · `POST /api/sessions/{session_id}/archive` · `/restore`. **No `PATCH` and no `DELETE`.** Lists order `last_used_at DESC, id DESC`; every row carries `setup_name` by an owner-scoped LEFT JOIN, shown even when the setup is archived |
| **the stream** (012, 014, 019, 021, 022 — `routers/stream.py`, `session-stream.md`) | `GET /api/sessions/{id}/entries` · `POST /api/sessions/{id}/entries` (201; `kind` **required and exactly `"partner"`**, every other value a native 422) · `GET /api/sessions/{id}/zone` · `POST /api/sessions/{id}/zone/messages` (201, **no model call**) · **`POST /api/sessions/{id}/zone/compose` (the ONE streaming route)** · `POST /api/sessions/{id}/settle` · `POST /api/sessions/{id}/reopen` · `PATCH /api/messages/{message_id}` · `GET /api/messages/{message_id}/discussion` (read-only). **Eight JSON routes plus compose.** No stop route, no discard route, and none may be added |
| **create-and-seed** (018) | `POST /api/characters/{character_id}/sessions` — owned by `routers/sessions.py`; body omitted / `{}` / `{ setup_id?, opening_message? }`; **201 `StartedSession`** = the eight `Session` keys plus `opening_message` (a `MessageResponse` or null). One transaction; a whitespace-only `opening_message` is a 422 and nothing is created |
| **memos** (015, 016) | `GET /api/memos?scope&scope_id` · `POST` (201; flags on the body are **ignored** — created enabled, not forced) · `PATCH /{memo_id}` (any subset of `body` / `is_enabled` / `is_forced`; a null key is "not supplied") · `DELETE /{memo_id}` (204 — the only delete path in the product) · **`PUT /api/memos/order`** (body `{ scope, scope_id?, memo_ids: [string] }`; 200 `{ memos: [...] }` with `sort_key` 0..n−1; declared **before** the `{memo_id}` handlers so `order` is not read as an id; **one request is one level**) · `GET /api/sessions/{session_id}/memo-chain` |
| **configuration** (017 — `routers/configuration.py`) | **seven**: `GET` / `PATCH /api/characters/{character_id}/configuration` · `GET` / `PATCH /api/sessions/{session_id}/configuration` · `GET` / `PATCH /api/me/settings` · **`GET /api/models`** (the enabled set, in first-enabled order `llm_servers.id` then `models.id`). `model: null` clears |
| **translation** (023) | `POST /api/messages/{message_id}/translation` — an `async def` handler with its own overridable chat-client factory, **no request body** (the target is resolved server-side), 200 `{ message_id, target_language, text, cached }` |
| **my-search** (029) | **`GET /api/search?q=<text>`** — a **sync `def`** handler; 200 `{ characters, setups, sessions, entries, memos }`, ids as strings; **a blank `q` returns five empty lists and makes no embedding call**; errors 401, **409** `no_embedding_model`, **502** `llm_unreachable` / `secret_ref_missing`. **It fails whole**, never partially |
| **export** (030 — `transfer.md`) | **four**: `GET /api/export` (the caller's `user` export) · `GET /api/characters/{character_id}/export` · `GET /api/sessions/{session_id}/export` · `GET /api/admin/database/export`. None takes a body, a query parameter or an id beyond the entity. Each sets `Content-Disposition: attachment; filename="rphelper-<granularity>-<UTC timestamp>.json"` — **the filename never embeds user content** |
| **import** (031 — `transfer.md`) | **three**: `POST /api/import` (accepts `user` **or** `character`; 200 `{granularity, character_ids}`) · `POST /api/characters/{character_id}/import` (accepts `session`; 200 `{session_id}`) · `POST /api/admin/database/import` (accepts `database`; 204 + cookie cleared). **The server decides the granularity from the envelope** |

### Wire shapes

- **`MessageResponse` carries TWELVE keys** (`session-stream.md`), and the
  structure is kept visible because they arrived from three plans for three
  reasons:
  - **eight message fields** (plan 012) — no `user_id`, no `related_to`, no raw
    tool columns;
  - **three tool fields** (plan 022 D3, superseding 021's "not on the wire") —
    `tool_name`, `tool_status` (`ok` / `failed`) and `tool_args` (the call's
    arguments as an object, `{}` when unreadable), **all null on a non-tool row**,
    derived in `services/messages.py`. `tool_payload`, the provider's `call_id`
    and the raw tool content **never leave the backend**;
  - **the coverage flag** (plan 024) — `search_coverage_incomplete: bool`,
    **false for zone rows and plain appends**.
- **`SettleResponse` and `ReopenResponse` carry `search_coverage_incomplete`
  too**, as does the `PATCH` response — every record-keeping write reports it in
  its own response. `SettleResponse` = `{ entry_id, kind, buried_ids,
  search_coverage_incomplete }`; `ReopenResponse` = `{ reopened_id, restored_ids,
  search_coverage_incomplete }`. **Both return the ids they moved and nothing
  else**; the client re-reads both lists.
- **The nine-key `Memo`** carries `scope_id` **null for the user level** (the
  column stores the owner's own id — the API's choice, not the column's) and
  **never `user_id`**.
- **Every `Session` read carries `setup_name`.** The create-and-seed route answers
  the eight `Session` keys plus `opening_message`.
- **Request validation that is not a domain error** (009 D8): a blank or
  whitespace-only required text field is stripped and refused by **FastAPI's own
  422**, with no domain code. **Unknown body keys are ignored**, not refused. **A
  query parameter is a plain typed parameter with a default, placed last, with no
  `Query(...)` wrapper.**

## Admin area at a glance — `admin-surfaces.md`

| Route (under `/admin`) | Page | Realizes |
|---|---|---|
| `/` | Users | FEAT-003 |
| `/llm-servers` | LLM Servers | FEAT-004 |
| `/database` | Database | FEAT-005 + FEAT-018 whole-database |
| `*` | Not found | — |

- `BrowserRouter basename="/admin"`, Mantine **`AppShell`** (`header` 56, `navbar`
  220 / `sm`), **no `padding`** (pages bring `Container size="lg" py="md"`), no
  `aside`, no breadcrumbs, **flat `<Routes>`**. Back-to-app is a real
  `<a href="/">`. **`AppShell` lives here and only here** — the `app` entry's
  shell is a hand-written CSS grid. The asymmetry is deliberate.
- **Gate:** `main.tsx` awaits `GET /api/me`, then mounts or redirects — nothing
  rendered meanwhile. Pure `resolveAdminAccess` + impure `enforceAdminAccess`,
  reading the user through `shared/currentUser.ts`. **Five boot outcomes**; **a
  502/network failure is not a deny**.
- **Header:** `Burger`, title, `<a href="/">` — **no user menu, so no sign-out in
  the admin area**; `ColorSchemeToggle` not mounted.
- **Nav:** static declaration table → `NavLink`s, pure
  `isNavItemActive(pathname, item)` (segment match + `exact` for root), **not**
  react-router's `end`. Icons `IconUsers` / `IconServer2` / `IconDatabase`.
  Shell state is a MobX `AdminShellState { navbarOpened }` via
  `useState(() => new …)` — **not `useDisclosure`**.
- **Users:** **last login** = `users.last_login_at` (em dash when NULL), stamped
  in the open-session transaction, `updated_at` not bumped. **A password reset
  keeps live sessions** (US-010.AC-3). **Change Role = UC-087 / US-140**; self
  target → `self_role_change_refused` 409 on the modal's general key, and the
  action is **not** hidden on one's own row.
- **LLM Servers:** **two** routes over **one** probe primitive. **Test answers 200
  even for a failing outcome** and writes `last_test_*`; **available-models writes
  nothing and answers 502 `llm_unreachable`**. Probe outcomes are **four** —
  `reachable` / `unreachable` / `auth_failed` / `model_list_empty`; ok =
  `reachable` only. **No "active" column.** Designation **measures** the dimension
  with one real embeddings call and is **independent of `is_enabled`**; the
  use-time validator needs **only the designation with its dimension** —
  `is_enabled` is the chat set only, and an embedding model need not (should not)
  be enabled (revised 2026-10-08; code pending a plan-006 bug fix). API key never returned; empty/untouched = leave,
  explicit empty string = clear; a non-`$` value is FastAPI's 422. The models
  modal renders `available ∪ already-enabled`, and **a failed probe must not
  disturb the selection** — structurally, because the enabled set rides on the
  list payload.
- **Database page:** the drift report plus per-row `Create` / `Sync`, **plus
  Export and Import** (plans 030, 031). **Rebuild index (UC-016 / US-019) is still
  absent** — `docs/plans/fast/002.vector-index-rebuild`.
  - **Statuses (three, fixed):** in sync → **`green`**, drifted → **`yellow`**,
    missing → **`red`**; the status word is rendered as text, colour is redundant.
    The fourth, `seed-missing`, was looked at and declined (the Seed `_TBD:`).
  - **Compared:** column set, declared SQLite type (compiled through the SQLite
    dialect), NOT NULL, index set keyed on (columns, uniqueness). **Not
    compared:** defaults, `CHECK` text, FK clauses. Implicit UNIQUE/PK indexes are
    not live indexes. **No row count, size or timestamp.**
  - **Create and Sync are idempotent and total** — no state precondition, no
    "wrong state" code; Create never drops anything; each action is offered only
    in its state (**absent, not disabled**), and an in-sync row has no trigger.
  - **Sync = recreate-mode rebuild:** surviving columns' data kept
    (US-018.AC-5); a **lossy** Sync names the lost columns and needs a confirm
    (US-018.AC-3/AC-4); a failed apply rolls back completely, no
    `_alembic_tmp_*` left (US-018.AC-6/AC-7). The cast refusal is a post-copy
    probe only for `INTEGER`/`REAL`/`NUMERIC`/`DECIMAL`/`BOOLEAN` targets.
    **FK posture:** `foreign_keys = OFF` **outside** the transaction, rebuild,
    `foreign_key_check` before commit, `ON` restored on both paths. This is the
    **one** code path that suspends that pragma.
  - **The surviving derived-tables gap, with a sharper edge** (024 D2): the report
    walks `metadata.tables` only, so `memo_vec`, `session_vec`, `memo_fts` and
    `message_fts` are outside it — **and a Sync rebuild of `memos` or `messages`
    drops that table's FTS triggers.** The next ensure-on-write restores the
    triggers but does **not** back-fill, so that lexical index is stale for every
    row written until a full rebuild. **The views half of this gap is gone**: no
    SQL view exists anywhere in the schema.
  - **Export/import are opaque.** After an export the page renders **one inline
    size line** ("Export downloaded — 12.3 KB", 1024-based) and nothing else; the
    **import shows nothing of the file at all**, before or after. Import is a
    four-step sequence: **file picker → red confirm → upload → redirect to
    `/login`**. Failures render in their **own** inline red `Alert`, separate from
    the drift report's, and never as a notification.
  - **`fast/002`'s response is expected to carry no count** — a requirement on
    that unbuilt plan, not an as-built fact. "Counts and completion" permits
    completion, and **at most counts not derived from user content**.
- **Dropped from BookWriter, deliberately:** `AssistantModesPage`,
  `SubAgentsPage`. Do not re-add.

## Key invariants — the short list

Numbers are the `domain-rules.md` rule ids. **Read that doc for the reasoning; do
not act on these one-liners alone.**

| # | Invariant |
|---|---|
| **R1** | **The two chains share NO level.** Model / system prompt / tools inherit **`character → session`** — there is **no user-level default** (UC-050); RP language + preferred language inherit `user → session`, **skipping character**. Schema-enforced on both sides — `characters` has no language columns, `users` has no model/prompt/tools columns. The resolver is **two functions** whose per-level input shapes carry only their own chain's fields. Lowest non-null level wins; a level with no value is transparent. **Tool switches are three independent nullable booleans per level and the floor is ENABLED**, reported at level `default` |
| **R2** | Memo chain is a **union** over user + character + setup? + session. With no setup it degrades to user+character+session **with no gap** — same query, one fewer OR-term. No sentinel setup row. **The disjunction has one home: a public clause builder in `services/memo_chain.py`**, used by `resolve_chain` and by `memo_search` |
| **R3** | A note's reach is **two independent booleans, `is_enabled` and `is_forced`** — not one three-valued column. Defaults `is_enabled = true`, `is_forced = false`. Disabling **preserves** `is_forced`, so re-enabling restores the mode (US-101). **`is_enabled` gates first; `is_forced` is consulted only afterwards.** `NOT is_enabled` reaches the assistant by **NO path**. **One derivation, `memo_reach`, exists in two languages and both test `is_enabled` first**; its two backend consumers are `services/context.py` (which writes **no hand-rolled conjunction**, pinned by a source test) and `services/search/memo_search.py`. **Constrains the assistant only: my-search applies neither flag.** Order is a third axis (`sort_key`). Memos never archive |
| **R4** | **No silent model fallback.** Resolution yields a model *reference*, unvalidated; validation happens at **use time** and raises typed errors. **The MODEL is captured at session CREATION** onto `sessions.model_server_id` / `model_name` — the character's pair as-is, else the **first enabled model**, else **both NULL** (`US-143`) — and a character configured afterwards reaches **only sessions created from then on** (US-139). **The SYSTEM PROMPT and TOOLS keep resolving LIVE.** **The split is deliberate — harmonising it either way is a defect.** `resolve_model_for_use`'s three refusals run **instance → session → reference**: `no_model_enabled` / `model_not_chosen` / `model_not_enabled`. A captured session model reports `level: "session"`. **Validation also runs at set time** (409, nothing written), and **the session's model is never cleared, only replaced**. Same no-fallback rule for the embedding designation → `no_embedding_model` |
| **R5** | **A `model → dependent sessions` query must not exist** on any admin surface. "Are you sure? N sessions use this model" is a forbidden UI pattern, and **the LLM Servers page's confirm dialog is where it will be attempted**. Every read path scoped by owner **in the query**. **An admin on a roleplayer route is an ordinary owner.** Proved by three mechanisms: the route-classification guard (**an unclassified route fails the build**), the **admin-response invariance** test, and cross-user proof for the search layer. **Refusal identity** is the companion property. `export_database` / `import_database` are the **only** services taking no `user_id` — compatible through **opacity**, not scoping |
| **R6** | Archive = out of the working list, never destroyed, always restorable. `archived_at` nullable, **no delete path** for characters/setups/sessions. Flag named `include_archived=true` on every list that has one; a **by-id read answers archived rows**. Idempotent, a no-op writes nothing, archive never moves `last_used_at`. Archiving a referenced setup is **silent, always succeeds, no reference count**. Archived sessions appear **only on the character page**, never in the tree. Memos are the contrast: they do not archive, and their removal is a hard delete |
| **R7** | Settling **buries** the group under the settled head; re-open is allowed **only while the current zone below is empty**; a buried group **never reaches the assistant again**. A buried group stays readable through the lazy discussion read and is **not editable** — enforced at both boundaries. Deliberate asymmetry: a settled turn is editable forever and the assistant reads the current version |
| **R8** | Translations are a success-only cache keyed `(message, target language)`, in their own table, and **never enter context**. Only settled rows are translatable — in practice only `kind='partner'`. The write is **insert-or-ignore, and only if the message's text still equals what was translated** |
| **R9** | The assistant's reach is **exactly three tools**, all implemented and registered. **`ToolScope` is built only by the seam, from an owner-scoped session read, and tool arguments never carry ids.** A failed tool is a tool *result* — the exchange continues. **`web_search` is the one tool that is not a scoped read** — no scope ids, no database access, only the query leaves — and it additionally needs **instance credentials** to be offered at all, so on an unconfigured instance the reach is two tools. The assistant never files anything into the record |
| **R10** | The roleplayer's text is committed **before** any model call; the `accepted` frame makes that observable, and it arrives on the failure path too. **Model-resolution failures arrive INSIDE the stream**, after `accepted`. **The harness persists accumulated `token` text whenever no `done` passed through** — disconnect, domain error, synthesized error, terminal-less exhaustion — written **before** the error frame; whitespace-only text writes no row. Retry re-runs generation **without re-inserting anything**. An enormous paste warns but is **never refused** |
| **R11** | **The ruler: settle is the only door into the record**, with one exception — a pasted partner block, born settled. The **current zone is a set, not a row** (`related_to IS NULL AND settled_at IS NULL`), so US-125 needs no constraint. **Settle's head is the last NON-TOOL zone row; a zone holding only tool rows is `zone_empty`**, and tool rows are buried with the group. **Settling never requires an assistant answer.** Re-open is settle's exact inverse, gated on an empty zone, and applies only to a head that **has** a buried group — otherwise `nothing_to_reopen`, which covers a pasted partner block, a lone directly-settled turn and a lone decision. **Abandoning an empty zone is frontend-only — no route, no backend surface.** Four facts about `messages`: every read outside settle/re-open goes through a **selectable**; the burial and settle columns are written **only** by settle and re-open; inserts are the zone append, the partner filing, the assistant row and the character page's opening message; `text`/`updated_at` are the edit route's |
| **R12** | `(( ))` is **parsed once, at settle, and stored text is never re-parsed.** Wholly parenthesised (after trimming, starts `((` and ends `))`) → `kind='decision'`, filed **verbatim**; otherwise `kind='turn'` with every shortest fragment stripped along with the spaces and tabs before it. **A fragment-free turn is filed byte-for-byte; a turn can never strip to empty.** **Partner text gets no special treatment.** Three layers: server decides (`services/parens.py`, called from exactly one place), system prompt instructs, client previews and paints **in the zone only** (`app/parens.ts`) and is never authoritative. **An edit can never turn a turn into a decision or back.** Recorded constraint: the convention assumes double parentheses never occur in the roleplayer's own prose (US-130's `Constraint:`) |

**The parallel `<think>` rule** (R12's neighbour, `US-146`): reasoning streams as
ordinary `token` frames wrapped in `<think>` … `</think>` and is **persisted** on
the current-zone assistant row. **`strip_think` is applied in exactly THREE
places** — settle (an `assistant` head, **before** `(( ))` classification),
context assembly (current-zone **assistant** rows), and translation (the result
before caching). **User text and settled text are never think-stripped**, and a
head whose stripped text is empty **still settles**.

## SSE frame protocol

```
accepted | token | tool_start | tool_result | tool_fail | error | done
```

- **`accepted` is emitted once, before the first `token`, and only when the
  compose carried text** — a textless retry emits none, because no row was
  inserted. It carries the **roleplayer's** committed zone row id.
- `done` is mandatory on success and carries the **assistant's** row id. **Both
  ids are decimal strings, and they name different rows.**
- **Four ways a stream ends:** `done` (success), `error` (server-side failure),
  an unexpected close (the client renders `llm_unreachable`), and **a stop
  (UC-085), for which the server emits nothing**. **A client that initiated the
  stop must not surface `llm_unreachable` for it** — the distinction is made on
  the consumer's own `AbortController` state, never on the bytes.
- **The server never ends a stream silently.** A source that raises a non-domain
  exception, or exhausts with no terminal frame, is ended by the harness with a
  **synthesized `error` frame (`llm_unreachable`, fixed message)**. So silence
  always means the connection went away.
- **The stop is `controller.abort()` on the existing `fetch()`. No stop route, no
  registry of in-flight work, no new frame.** The server persists the partial
  assistant text as an ordinary zone row and unwinds; **a stop during a tool call
  ends the exchange** and the candidate may be empty (`US-133.AC-1`).
- `error` and `done` are mutually exclusive and terminal — of the terminations the
  *server* produces. **`tool_fail` is NOT terminal** (R9).
- `error` carries the same `{code, message, detail}` shape as JSON errors, built
  from the `DomainError`'s **inner** fields and **not** from `to_wire()`'s wrapper.
- `tool_result` carries a **summary**, never raw retrieved content.
- **Frames are built in one place, `services/llm/frames.py`** — seven immutable
  frame value types and **one** encoder (`data: ` + compact JSON with `event`
  first + `\n\n`, UTF-8, every id through `str()`). **A source yields frame
  *values*, never strings**, so no producer can hand-roll a line or forget the id
  conversion. The same module holds the harness (`frame_stream`, `sse_response`,
  `own_connection_persister`).
- One streaming route: **`POST /api/sessions/{id}/zone/compose`**, body
  `{ text? }` — absent or null means **retry**, a blank string is a 422. Its
  non-streaming sibling `POST /api/sessions/{id}/zone/messages` makes no model
  call and returns JSON.
- POST + JSON body → the client uses `fetch()` + `body.getReader()` +
  `TextDecoder({stream:true})`, split on `"\n\n"`, keeping the trailing partial
  frame. **Not `EventSource`** (GET-only). `shared/sse.ts` **never rejects** and
  resolves to one of four outcomes — **done / error / stopped / unexpected end**.
  An **unknown `event` is skipped**, and **frames after a terminal one are never
  delivered**.
- App sets `X-Accel-Buffering: no`; nginx also sets `proxy_buffering off`.
- **No tool-iteration cap** — the stop bounds a runaway loop, because the loop
  dies with the socket.
- **The harness writes the partial row on its OWN short-lived connection** from
  `get_engine(settings)`, never the request-scoped `get_connection`, whose
  teardown relative to body iteration is unverified for the installed FastAPI.
  The **tool seam** dispatches on its own short-lived connection too. These are
  the two named deviations from "the request's own connection".

## Context assembly — what is in, what is out

**In:** resolved system prompt (live, `character → session`) + character sheet +
**enabled AND forced** memos (level order user → character → setup? → session,
then by `sort_key`) + **three fixed instruction sections, never omitted** — the
message tags, the languages, the double parentheses; and, as the message list,
the **union of the `settled_entries` and `current_zone` selectables** for this
session, `ORDER BY id`. A `kind='decision'` row is context like any other settled
row (US-122).

- **The union is two reads MERGED BY ID**, not one query and not a concatenation
  — the two lists can interleave (a partner block filed while a draft sits in the
  zone).
- **Each settled row is prefixed `[partner]` / `[my turn]` / `[decision]` plus a
  line feed**; zone rows carry no tag. Necessary because partner blocks and the
  roleplayer's own turns are **both `role='user'`**. **Stored text is never
  changed** — the tag exists only on the way into the request.
- **Tool rows are REPLAYED, not skipped** (021 D9, superseding 020 D3): each zone
  tool row becomes **two** messages — an assistant message with empty content
  carrying that one call, then a `tool` message with the payload content (or the
  fixed failed literal). **An unreplayable row is skipped**, not reconstructed.
- **Tool descriptions are NOT in the prompt** — enabled tools reach the model
  through the API's `tools` parameter. **Two further deliberate absences: no setup
  description and no character name.**
- **Prompt layout is the contract** (020 D10): section headings, a heading per
  memo level, a `[note]` delimiter between notes, a fixed lead-in per instruction
  section. **Tests bind to the markers, never to the instruction prose.**
- Omitted when absent: the system prompt section entirely (**there is no default
  persona**), an empty sheet, the whole notes section when the chain yields none.
- **No pruning, no summarisation, no token count, no truncation** — context
  compaction is a recorded non-goal.
- **The sub-reads are separate reads, not one snapshot — accepted** (020 D11).

**Out, each with the rule that forbids it:** memos where `NOT is_enabled` (R3 —
absolute, whatever `is_forced` says) · memos where `is_enabled AND NOT is_forced`
(R3 — `memo_search` only) · **buried rows, excluded by construction** at the
selectable boundary rather than by a predicate assembly writes (R7/R11/UC-038) ·
translations (R8) · other users' material (R5) · other characters' sessions
(UC-054).

Assembly names **no table** — a query here selecting from raw `messages` is a
defect. Messages and forced memos are read **live**; nothing is cached.

**Language handling:** candidates are always in the **RP language**; the assistant
**mirrors** each zone message's language, and nothing records one; OOC text is in
the **preferred** language (US-131), so decisions are never translated. **With no
language resolved at any level the instruction names English — `US-142`, a last
resort and never a configured default**, and nothing is refused. The same fallback
governs translation's target, held in **one constant in
`services/translation.py`**, and the cache key uses the **effective** target.

## Search at a glance

| Surface | Arms | Scope | Notes |
|---|---|---|---|
| `memo_search` (FEAT-014) | vec + FTS, RRF | `user_id`, `is_enabled AND NOT is_forced`, the 4-level chain | `is_enabled` gates first, pinned by a test **on the compiled clause**. At most **8 hits**, no paging; the declaration stays `query` only. The model receives `[<level>] <snippet>` per line — **scope literal only, no names, no ids**. Zero hits is a **success** (`No matching notes.`); the `tool_result` summary is `<N> memos` |
| `session_search` (FEAT-015) | **vec only — no BM25, no RRF blend** | `user_id`, `character_id`, `id != current`, `archived_at IS NULL` — **four terms** | Semantic-only is a product decision (challenge C5). At most **5 hits** (lower than 8 because each carries a long excerpt). One block per hit: `### Session <YYYY-MM-DD> · setup: <name>` plus **the last 1500 characters** of the session's `settled_entries` text, blank-line joined, decisions included, a cut excerpt starting `…`; `(no settled entries)` when there are none. **No persona, no setup description, no ids.** The setup's name shows even when archived. **The excerpt is the tool's own owner-scoped read, not a port feature** |
| my-search (FEAT-017) | vec + FTS, RRF **within each kind** | `user_id` only | ACT-002 UI, **not** a tool. **The product's count of five corpora is unchanged; the mechanism is three port variants plus two `LIKE` corpora** (029 U2). Grouped by kind in UC-059's order, **at most 20 per group**, no paging. **Applies no `is_enabled`/`is_forced` predicate at all** (ratified by US-137); a disabled hit is **dimmed, struck through, with a gray "Disabled" badge**. **Archived material is included and marked "Archived"** — the deliberate asymmetry with `session_search`. **Fails whole** on a vector-arm error. **Known cost: each search embeds the query twice** |

**Three port variants, and the variant fixes the arms** — no caller chooses:
**memo** (vec + lexical, fused), **session** (vector only), **entry** (lexical
only, over `message_fts` scoped to `settled_entries`). **Characters and setups are
not variants**: no index exists, so they are matched by an **escaped,
case-insensitive, non-tokenised `LIKE` substring outside the port** — `name` +
`sheet`, `name` + `description`. That is the one deviation from "all surfaces go
through one port", and the flip condition is named.

**The port applies `user_id` itself, in every statement including hit
hydration**; beyond that a variant accepts an **optional clause builder** which
the port **ANDs** with the owner predicate, neither adding nor reordering it.
**`SearchHit`** = kind, id, fused score, snippet, plus a memo's `scope` /
`scope_id` and an entry's `session_id`. **A session hit has no snippet** —
`sessions` has no text column. **The port does no name join.**

**Filter first (relational), then rank.** `sqlite-vec` KNN is **exact** — no
recall tuning. **RRF with `k = 60`, ranks only, per-arm candidate depth 50, ties
on ascending id; a single-arm scope is still fused over its one ranking** so
`score` means the same thing everywhere.

> **FORBIDDEN: a `vec0` KNN with a pushed-down id constraint** —
> `… WHERE embedding MATCH ? AND k = ? AND <id> IN (...)`. On sqlite-vec 0.1.9 it
> **silently drops true candidates** for ids above roughly 2^50 — false negatives
> only, in 18–36% of queries, and snowflake ids are in that range from the start.
> Recorded **once**, in `search-and-retrieval.md`; `data-model.md`
> cross-references it.

The two correct forms: **(a) an exact scan over the candidate set** —
`… WHERE memo_id IN (SELECT id FROM candidates) ORDER BY vec_distance_l2(...)
LIMIT :n`, no `MATCH`, no `k` — which is what plan 025 built; and **(b) an
over-fetching KNN then a join, or `+memo_id IN (...)`** — the **unary plus is
what blocks the pushdown**, and without it form (b) *is* the forbidden form.

**User text can never raise an FTS5 syntax error**: split on whitespace, remove
`"`, quote each token as a **phrase**, OR-join. **No usable token means the
lexical arm is skipped entirely.**

**Index tables:** `memo_fts(body)` — **`body` alone, because `memos` has no
`title` column** (US-119); `message_fts(text)` — **renamed from `entry_fts`**,
external content on base `messages`, **restricted to settled rows by the triggers
rather than by the declaration**; and **`session_fts` is declared in doc history
and was NEVER created** (024 U7) — its declaration names `title` and
`partner_label`, columns `sessions` does not have (011 D4, `US-145`). It waits on
the feature that gives a session text columns; **nobody creates it because the
declaration exists.** Vector tables are `memo_vec` and `session_vec`.

**Trigger conditions, exactly** — an unconditional update trigger corrupts
external-content FTS5: `memo_fts` on insert, delete and **`UPDATE OF body`
only**; `message_fts` insert when the row is **born** a record row, delete iff OLD
was a record row, and **one** update trigger issuing `'delete'` with OLD iff OLD
was a record row then inserting NEW iff NEW is one. Back-fill is `'rebuild'` for
`memo_fts` and an `INSERT…SELECT` of record rows only for `message_fts`.

**The `vec0` / FTS5 tables have no user column**, so reads are safe only because
the port's candidate set is owner-scoped first — and **every write to a derived
store must resolve the row ids it will touch through an owner-scoped query
first** (plan 032, step 004). `write_vector` / `delete_vector` take **no user
id**. This is **the one leak the audit found**, and a fix to defect D-04 is
directly bound by it.

**`session_vec`'s text spans three sources, and the ORDER is load-bearing:**
**persona (`characters.sheet`) → setup text (`setups.description`, absent with no
setup) → the session's settled entries** (`settled_entries`, id order, decisions
included). Empty parts are dropped and the rest joined with a blank line.
**Persona and setup lead so that model-side truncation of a long session cannot
drop them** — `US-138.AC-2`'s "similar person" half is satisfiable only from the
persona. **An empty composed text means no `session_vec` row at all.**

**The persona-edit fan-out — the system's first one-to-many invalidation.**
Editing a character's persona (or a setup's text) invalidates **every** session
vector under that character. **Re-embedded inline, in the same transaction**, so
search is never stale, at a stated cost: **N sessions = N embedding calls inside
one request**. **One embed request carries all N texts**, not N requests.
**Archived sessions participate — no archive predicate** (024 U4), so a restored
session's vector is never silently stale. **Validation and fail-hard apply only
when N > 0**, where N means at least one non-empty session text — so creating a
character, editing one with no sessions, a name-only edit and an unchanged sheet
need **no embedding model at all**.

**The deliberate write asymmetry — authoring act vs record-keeping, not which
table.** A memo create/body edit **and a character persona / setup text edit**
with no embedding model **fail the whole transaction**; a settled-entry edit,
settle, re-open and a **partner filing** **succeed, degraded** (US-112), with
`search_coverage_incomplete` in the write's own response. **The caught set on the
degraded path is `no_embedding_model` (including the `dimension_mismatch` form)
and `llm_unreachable`**; the strict path catches neither and lets both propagate
at **409** and **502**. Do not harmonise the two.
**A memo without a vector is a normal post-import state** after plan 031, so "no
vector" is no longer diagnostic on its own.

**The query-side no-model rule:** whenever a variant's vector arm runs the
designated embedding model is **required** — `no_embedding_model`,
`secret_ref_missing` and `llm_unreachable` **propagate unchanged** and there is
**no lexical-only fallback**. An absent or empty `vec`/FTS table is **not** an
error (that arm yields no hits); a dimension mismatch raises
`{"reason": "dimension_mismatch"}` **before any provider call**.

**Changing the embedding designation neither forces nor prompts a rebuild**
(UC-013) — existing vectors came from the superseded model, are not comparable,
and **nothing indicates this**. Remedy: UC-016, always available.

**The tool registry holds three tools, all implemented and registered**
(plans 026, 027, 028) — offered order **`memo_search`, `session_search`,
`web_search`**. **Availability is an intersection:** the resolved switch is on
**and** an implementation is registered — **and, for `web_search` only, the
instance holds both search credentials.** A disabled tool is **absent from the
tool list**, not present-and-refused. The registry is built **per request from
settings** by `routers/stream.py`'s dependency.

**`web_search` as built:** Google Custom Search JSON API, `GET
…/customsearch/v1` with `cx` / `q` / `num`, the **key in the `X-goog-api-key`
header and never in the URL**, **five results, a 10 s timeout, no caching**.
Failures become `tool_failed` with `detail {"tool": "web_search"}`, **never
chained to the transport exception** and carrying no query, key, URL or body.
**Neither the provider nor the adapter logs anything.**

## Typed errors

Wire shape: `{ "error": { "code", "message", "detail" } }`. The error table is
`backend-structure.md`'s and carries **no status column by design**; statuses live
in its **per-code status record**, where the feature that introduces a code
decides it. One handler on the `DomainError` base class, installed by
`errors.py`'s `register_exception_handlers(app)` from the app factory.
`BackwardsClockError` and `ExtensionLoadError` are **not** `DomainError`s —
operational 500s.

Every code with its status:

| 400 | 401 | 403 | 404 | 409 | 500 | 502 |
|---|---|---|---|---|---|---|
| `invalid_credentials` · **`export_invalid`** | `not_authenticated` | `insufficient_role` | `user_not_found` · `llm_server_not_found` · `unknown_table` · **`character_not_found`** · **`setup_not_found`** · **`session_not_found`** · **`message_not_found`** · **`memo_not_found`** | `already_configured` · `username_taken` · `self_role_change_refused` · `model_not_enabled` · `no_embedding_model` · **`setup_archived`** · **`zone_empty`** · **`zone_not_empty`** · **`nothing_to_reopen`** · **`message_not_editable`** · **`memo_order_mismatch`** · **`no_model_enabled`** · **`model_not_chosen`** · **`database_not_empty`** | `secret_ref_missing` · `schema_apply_failed` | `llm_unreachable` · **`tool_failed`** · **`translation_failed`** |

What each of the newer ones means, where it is not obvious:

- **`setup_archived`** — a session start names the caller's *archived* setup. Not
  404 (it exists for the caller) and not 422 (nothing is malformed).
- **`zone_empty`** — settle with nothing in the zone, **or a zone holding only
  `role='tool'` rows**; also the textless retry compose when no non-tool zone row
  exists, answered **as JSON before any stream opens**.
- **`message_not_editable`** — **exactly two meanings: a buried row (US-116) and a
  `role='tool'` row** (`US-115.AC-1`'s `Constraint:`). The settled case plan 012
  shipped as an interim was removed by plan 014.
- **`nothing_to_reopen`** — no settled row at all, or a last settled row with no
  buried group (a pasted partner block, a lone directly-settled turn, a lone
  decision).
- **`memo_order_mismatch`** — the reorder's `memo_ids` is not **exactly** the
  caller's notes at that level. **It never lists the mismatched ids** (R5).
- **`model_not_enabled`** — carries the server id **as a string**, the model name,
  and **which level set it**, constrained to `character` or `session`, **never
  `user`**. A captured session model reports `session`, because the only remedy is
  the header picker.
- **`no_embedding_model`** — also raised when the live `vec0` table's declared
  dimension does not match the designation's, with
  `{"reason": "dimension_mismatch"}`.
- **`tool_failed`** — **502**, a dependency's failure. **Never an HTTP response as
  built**: it is the `tool_fail` frame's code, and the status is recorded for the
  first route that ever raises it. **It is never a notification** either
  (`ui-conventions.md`).
- **`export_invalid`** — **the codebase's first typed 400 for malformed input**;
  everything else malformed is FastAPI's own 422. `detail` is exactly
  `{"reason": …}`, one of `not_an_export`, `unsupported_version`,
  `schema_mismatch`, `wrong_granularity`, `malformed_payload`, and **never** a
  table name, a column name or row content. A database-import constraint refusal
  maps to `malformed_payload` and never forwards the driver's message.
- **`database_not_empty`** — a whole-database import onto an instance holding
  content (`US-077.AC-3`).

**`account_disabled` is struck** — nothing raises it; `invalid_credentials`
covers all three causes. **`discussion_not_resumable` is gone** — it named a table
that no longer exists; `zone_not_empty` replaces it and the rename is not
cosmetic.

**The five stream codes each carry a fixed default `message`** (012 D13),
following `already_configured`'s pattern, so a code raised with no arguments
still renders a non-empty `message`.

**The 500 posture** (user decision H1): `secret_ref_missing` and
`schema_apply_failed` are **one deliberate posture** — nothing about the request
is malformed; the instance failed to do what it offered, or its environment is
misconfigured. Both render as a failure panel. **Flip:** an admin surface needing
either as an actionable, field-level message moves that code to a 4xx. A non-`$`
secret pointer is **FastAPI's 422**, not a domain code.

Three rules about `detail` that are privacy rules, not formatting preferences:
it **never** carries another user's data or a count derived from it (R5), **never**
memo body text for a note where `is_enabled` is false (R3), and **any id in it is
a decimal string**.

**Frontend: call sites branch on `ApiError.code`** — never on `status`, never on
the message. `status` is carried for diagnostics and for the by-status half of a
draft's field mapping. **An exported type guard is the one sanctioned way a
`catch` narrows.** **Most codes are not branched on, and that is fine** — a code
reaches `notifyFailure` and renders its server message unless a surface needs to
do something *different*. As built: the stream branches on none of `zone_empty` /
`zone_not_empty` / `nothing_to_reopen` / `message_not_editable`;
`translation_failed` likewise; plan 017 branches on `model_not_enabled` alone.

**Three client-side codes no backend produces:**

| Code | Status | Raised when |
|---|---|---|
| **`client_malformed_error`** | the real status | a non-2xx whose body is absent, not JSON, or not the envelope |
| **`client_transport_failed`** | **`0`** | `fetch` itself rejects |
| **`client_unreadable_file`** | **`0`** | `shared/importFile.ts` — the chosen file is not readable JSON at all. Anything that parses but is not an export is the server's `export_invalid` |

**An abort is not an error and is not wrapped.** **Not-ready-yet** =
`client_transport_failed`, **or** `client_malformed_error` at status **≥ 500**
(`shared/notReady.ts`) — a well-formed backend envelope can never match. Fixed
**2000 ms** re-probe, uncapped, plus a manual retry.

## UI geometry constants — `workspace-shell.md`

**No column and no splitter in the workspace resizes.** The two hand-rolled
splitters and the fixed-height answer box are **deleted**, with a reversal record
and a flip condition. `docs/product/` asks for no resizable column anywhere; the
only drag it requires is note reordering. **The one exception is the composer's
text area**, via the browser's native vertical handle (2026-10-08) — not a
splitter, and its stored height sizes nothing else.

| Thing | Value |
|---|---|
| Tree column, expanded | `252px` |
| Tree column, collapsed (icon rail) | `48px` |
| Wall, floating (absolute overlay + shadow) | `min(320px, 84vw)` |
| Wall, pinned (a real grid column) | `320px` |
| Stream column | `max-width: 720px`, centred, `padding-inline: 18px` |
| Composer | same 720px / 18px; text area starts at `rows` **3** (session) / **10** (character page start composer), **native vertical handle**, **no auto-grow**, internal scroll, dragged height persisted |
| Responsive threshold | `820px` (= 252 + 720 + 320; **not** a Mantine token) |

- The shell is a **hand-written CSS grid, not `AppShell`**, and **two tracks, not
  three** — `nav | main`. **The wall is not a track of the shell**: it belongs to
  the session screen's own ready render, which is why US-095 holds **by
  construction**.
- **Collapse is a class that re-points one custom property** (`--navw`): one
  number, a browser-driven transition on `grid-template-columns`, zero React
  re-renders. `minmax(0, 1fr)` on the second track is load-bearing, and so is
  placing `.app-main` in track 2 **explicitly**.
- **The `1px` grid `gap` over a line-coloured background draws the dividers** —
  the gap shows `var(--mantine-color-default-border)` (**the only colour reference
  in `shell.css`**) and each column paints `bg="var(--mantine-color-body)"` as a
  Mantine style prop. **Both halves or the divider becomes a stripe of page.**
- **Below 820px:** the left track is **always 48px**; the rail's expand **lifts
  the same nav column out of the track** as an overlay (`nav-overlay-open`); the
  overlay's open state is **not persisted** and `navCollapsed` is **neither read
  nor written** at that width; dismissal is the collapse control, any in-entry
  navigation, or crossing back — **no click-outside and no backdrop**.
- **The composer does not grow with its content; the roleplayer drags it**
  (user decision 2026-10-08, superseding the "grows with its content" reversal —
  do not re-add Mantine `autosize`, which re-sets the height on every keystroke
  and so cannot coexist with a dragged one). Default `rows` 3 in `Composer`, 10 in
  `CharacterComposer`, both through `ComposerCore` with the default and the
  persistence field as a parameter. Height persisted **on drag end** under
  **`rphelper.composer-heights`** = `{ chat: number | null, start: number | null }`
  (`null` = default rows), its own pure module (suggested `app/composerHeights.ts`):
  total read, per-field fallback to `null` on absent/bad JSON/wrong type/
  non-finite/non-positive, **no upper clamp**, storage passed as a parameter. A
  third key, not a field of `rphelper.workspace-layout`, because that reader drops
  unknown keys on write (011 D7's reasoning). **Not yet built** — 013/006 D9 and
  018/003 shipped the old rule; a follow-up fast feature delivers it.
- With **no session open the wall is not shown at all** (US-095).

**`shell.css` holds eleven selectors and one media query, and nothing else.**
Plan 008's five — `.app` (the grid, the `1px` gap, the transition),
`.app.nav-collapsed`, `.app-nav`, `.app-main`, `.app.nav-overlay-open .app-nav` —
plus the **`(width < 820px)`** media query; and plan 016's six —
`.app-session`, `.app-session.wall-pinned`, `.app-stream`, `.app-wall`,
`.app-wall.wall-open`, `.app-session.wall-pinned .app-wall` — **with no new media
query**. Column backgrounds, padding, shadow and the wall's `Paper` are Mantine
style props. `tests/stylesheets.test.ts` pins the boundary.

**The media query string is exported to TypeScript as `NARROW_VIEWPORT_QUERY`**
(008 D3, D12; 016 D11) and read through `useMediaQuery`. **The narrow-width wall
revert is decided in TypeScript, not in a second media query**, because it is a
conjunction of a stored pin, a transient open flag and the viewport, and CSS sees
only the third. One threshold, two readers, one string.

## Icons

`@tabler/icons-react` `^3.40`. `size={18}` main/header/composer, `size={16}`
inline (**including a `Menu.Item`'s `leftSection`**), `size={14}` chevrons —
**`stroke={1.5}` on all three** (one family, one visual weight). Colour via the
wrapping button's `color`, never on the icon.

**Every icon-only action goes through the shared `IconButton`** (`Tooltip` +
`ActionIcon` + `aria-label` from one `label` prop) — a deliberate deviation from
BookWriter, which has none. Variant **`"subtle"`**; `sizeVariant` defaults to
`"main"`; **the props type is deliberately not widened** with `children`, a
`variant` escape hatch, a raw `size` or an `aria-label` override. **A rotated
chevron is passed as a tiny module-level component, not as a new prop.**

**Three scopes:** `IconButton` governs toolbar / header / composer / inline
actions; **table rows use the overflow `Menu`**, so a row holds exactly one
icon-only control (the labelled `IconDots` trigger); **the stream's per-entry
actions sit inside the entry as `IconButton`s** — an entry is a document, not a
row. **Two controls sit outside the rule because neither wraps a Tabler icon:**
the **user-menu trigger** (an avatar button named "User menu") and **my-search's
tree-header text input**.

| Action | Icon / form |
|---|---|
| Send message in discussion | **labelled button**, not an icon |
| Settle | **labelled primary button**, not an icon |
| Regenerate (retry a compose) | **labelled subtle `Button`** with `IconRefresh` as its left section |
| Kind switch — *partner* / *my turn* | **two labelled segments**, no icons |
| Stop generation | `IconPlayerStop` — **replaces Send while streaming; never both** |
| Copy a settled turn out | `IconCopy`, "Copy as plain text" — on **`turn` entries only** |
| Translate / flicker | `IconLanguage` — "Show translation" / "Cancel translation" / "Show original" |
| Discard an **empty** current zone | `IconX`, "Discard empty zone"; **absent**, not disabled, otherwise |
| Re-open a settled block | `IconArrowBackUp`, "Re-open last entry" |
| Edit entry, message or note | `IconEdit` — one glyph, **two label families** ("Edit entry" / "Edit message") |
| Save | `IconDeviceFloppy` |
| Collapse / expand (generic) | `IconChevronDown`, **rotated** — one icon, not a pair |
| Show / hide a settled entry's discussion | `IconChevronDown` rotated; "Show discussion" / "Hide discussion" |
| Expand / collapse a character in the tree | `IconChevronDown` rotated `-90°`, "Collapse &lt;name&gt;" / "Expand &lt;name&gt;", `sizeVariant` `"chevron"`; **absent** for a character with no sessions |
| Collapse the tree | `IconChevronLeft`, "Collapse tree" |
| Expand the tree from the rail | `IconMenu2`, "Expand tree" |
| New character (tree header and rail) | `IconPlus`, "New character" |
| New session / setup / note / import-session | `IconPlus` as a **labelled** button |
| Archive / restore | `IconArchive` / `IconArchiveOff` — left sections on the character page, menu items in a table row |
| Session configuration | `IconSettings` |
| My search | `IconSearch` on the collapsed rail; the expanded tree header is a **text input** |
| Memos / open the note wall | `IconNotes`, "Open notes"; present only while the wall is not visible |
| Pin / unpin the wall | `IconPin`, "Pin notes" / "Unpin notes"; active state is the button's colour |
| Dismiss the wall | `IconX`, "Close notes" |
| Note forced / not forced | `IconPin`, "Force note" / "Stop forcing note" |
| Note enabled / disabled | `IconCircleCheck` while enabled, `IconCircleOff` while disabled; "Disable note" / "Enable note" |
| Collapse / expand a tool call | `IconTool` (**decorative**) plus the rotated `IconChevronDown` toggle |
| Collapse / expand thinking | `IconBulb` beside "Thinking", plus the rotated `IconChevronDown` toggle |
| Overflow menu | `IconDots` — traces to no feature |
| Export / import | `IconDownload` / `IconUpload` |
| User menu — settings · admin area · export my data · import · log out | `IconSettings` · `IconShield` · `IconDownload` · `IconUpload` · `IconLogout` |
| Admin nav — Users · LLM Servers · Database | `IconUsers` · `IconServer2` · `IconDatabase` |

**Every glyph `_TBD:` this table used to carry is closed.** `IconMessageCheck` is
**not used anywhere**. **The row "Copy as plain text (composer)" is removed, not
deferred** — no plan built a composer copy and no brief contains one.
**`IconPin`'s collision is accepted and named** (user decision): the wall's pin
and a note's "forced" flag are the same glyph and **do co-occur on one screen**,
disambiguated by **label** and **location**.

**Accessibility floor:** every icon-only control has an accessible name, and one
serving many rows names its row. **Hover-revealed actions must also reveal on
`:focus-within`** — the mechanism is **Mantine hooks, not CSS** (`useHover` +
`useFocusWithin` + `useMediaQuery("(hover: none)")`, applied as **opacity**, so
the controls stay in the DOM and the tab order; no stylesheet selector exists for
it and none may be added). **A note's flag icons are always shown, and that is the
convention** — the deliberate difference from the stream's revealed actions is
recorded. **Note reordering has a keyboard path and it is required, not
optional.** A status badge sits **beside** its link, never inside it; a named list
is a `ul` + `aria-label`; a region holding several blocks is
`<section aria-labelledby>`.

## Async feedback — the boundary in one line

> **A notification whose message is a success is a defect.**

**No *success* toasts.** Success = the modal closes and the list refreshes.
`@mantine/notifications` **is** a dependency, for **transient failure reasons**
(`autoClose: 5000` on the outlet) and **one bounded warning**. A failure with a
place of its own — a field error, an inline `Alert`, a full-page state, the
coverage banner — renders **there and not also as a notification**.

- **`shared/notifyFailure(thrown)`** — the only way a failure is raised. No
  success path, no colour parameter.
- **`shared/notifyWarning`** — the second **and final** sanctioned importer; takes
  an **identifier from a closed set**, no free text, no colour, no timeout.
  Its two users: the **enormous-paste context-cost warning** (US-035.AC-1) and the
  **post-import coverage caveat**. The second is the worked example that **a
  warning attached to a success is permitted**.
- **The four compose failure codes reach `notifyFailure` with the server's own
  message** — `no_model_enabled`, `model_not_chosen`, `model_not_enabled`,
  `secret_ref_missing`, raised inside the stream and arriving as `error` frames.
- **`tool_failed` is never a notification** — the `tool_fail` frame is
  non-terminal and 019's effect **ignores tool frames**. The outcome shows in the
  live tool block and then in the persisted `role='tool'` row.
- **US-044's split is the design:** the **reason** goes to the ~5 s notification
  (it must not persist, US-044.AC-4); the **retry** is the labelled **Regenerate**
  in the zone (it must persist, US-044.AC-3 / AC-5, and it is derived from
  persisted rows so it survives a reload).

## CRUD conventions — `forms-and-lists.md`

Plain Mantine `Table` `striped highlightOnHover`, **no data-table library and no
card lists** · row actions in an overflow `Menu` behind `IconDots` in a trailing
`w={60}` column, **never** inline icon buttons · **a one-data-column action table
carries no `Table.Thead`** · **no sorting / filtering / pagination anywhere**
(small cardinality; open `_TBD:`) · my-search's **20 per group** is a result cap,
not pagination · centered `Loader` gated on an explicit status field · inline red
`Text`/`Alert` **above** the table, and **not also a notification** ·
**no empty-state component** (an inherited weak spot), and where the `app` entry
wrote one it wrote **a neutral line, not an invitation** ("No setups yet.", "No
sessions yet.").

**Create and edit are always a `Modal`**, with **three named exceptions**:
in-place edit of a settled entry / zone message / note; the character **draft
page**; and **starting a session** (a one-choice inline control — a Setup select
plus a "Start session" button). **The settings page's Languages form is a
*reading* of the draft-page exception, not a fourth one** — the route *is* the
form. **Blur-save replaced the character page's explicit Save** (009 D2 → 018 D7);
`/settings` keeps its Save because it is a form, not content.

**`@mantine/form` is NOT a dependency** — per-modal MobX `*Draft.ts` class
(**observable fields only**, no methods, **no getters**) with **pure free
functions** `clientErrors(draft)` / `errors(draft)` / `canSubmit(draft)` and an
**external** `submitX(draft, …, onSaved, signal?)`, never a method.
**A component writes a draft field inside `runInAction` at the input's
`onChange`**; state modules export **derivations and effects, not setters**.
`serverErrors` is keyed by field **plus a general key**, mapped **by status or
code, never by parsing prose**. **Fresh draft per open** via conditional mount;
modal open/target flags are component-local `useState` (view state, not domain
state) — **as are every expand/collapse flag and a discussion group's fetched
rows**, which is why the live-reply→persisted-row swap is a **remount**.

**Mutations are never optimistic** — re-load after every mutation, `void` + a
non-rethrowing catch. The workspace **narrows the scope** rather than skipping it:
settle, re-open and partner filing re-read the affected lists; an **edit replaces
exactly one row from the `PATCH` response**; every stream mutation failure goes
through `notifyFailure` **and then re-reads**; and **a returned row is applied
only if its `updated_at` is not older than the one already held** (015 D5).
**The one sanctioned exception is note reordering** (016 D7, U1) — optimistic on
drop, a **total** revert on failure applied to the level as it then is, further
drags in that level disabled while in flight, and an inline per-level failure
line. It does not erode the rule because the request carries **the whole level's
order** and the server either applies it or refuses it outright
(`memo_order_mismatch`).

**Confirm step** via **`shared/ConfirmModal.tsx`** (cancel left of confirm) on:
disable account · delete LLM connection · **clear embedding** (US-015.AC-2) · **a
lossy Sync, only when a column will be dropped** (US-018.AC-3/AC-4) · **replace
the whole database** (red, step 2 of four) · rebuild index (**not yet
realized**). **Deliberately NOT confirmed:** re-enable · saving an enabled-model
set · `Create` · archiving a character, a setup or a session (named one by one) ·
**the three roleplayer imports** (additive, they destroy nothing) · the export.
A confirm **may name structure** (table, column, index columns, type) and **never
content** — forbidden strings include "N rows will be lost", "N rows will be
rebuilt", "rows affected" and every variant of "N sessions use this model".

**Page state** = `makeAutoObservable` class **with no methods and no computed
getters** + free `loadX`/`xAction(state, …, signal?)` that `runInAction` and
early-return on abort, driven from `useEffect` + `AbortController`. **A new list
store copies `charactersState`** — the **four-value** ladder `"idle" | "loading" |
"ready" | "failed"`, **no message field**, and an **unconditional** `"loading"`
write so a retry visibly shows loading. **The submit effect has one shape**:
in-flight guard → `runInAction` setting `"submitting"` and clearing the error →
`try`/`catch` with two abort checks → `finally` back to `"idle"` unless aborted →
success handling **after** the `try`/`finally`. **Which store a list belongs to is
a scope question**: workspace-level when two regions of the shell read the same
rows, section-owned when nothing outside does, page-owned when the page is the
only reader — and **effects take the workspace state as a parameter, never hold it
as a field**. **One sanctioned non-observable field per store**, for non-data
handles only (the compose `AbortController` and its wound-down promise).

**A probe-backed picker gets its selection from the list payload, never from the
probe** — failed-probe resilience by construction, one shared picker module.
**The `MarkdownEditor`'s two emit rules:** `onChange` from `onUpdate` **only**,
and **every programmatic content or editability write passes `emitUpdate: false`**
— both library defaults go the wrong way, and either alone makes an unedited note
write itself back on mount. **A file input inside a Mantine `Menu.Item` loses its
change event when the dropdown unmounts**, so the user menu's "Import…" triggers
a hidden input **outside** the menu.

## Constants and invariants worth having in one place

| Thing | Value / rule |
|---|---|
| `memos.sort_key` allocation | **`COALESCE(MIN(sort_key), 1) - 1`** over the owner's notes at the same `(user_id, scope, scope_id)`, inside the create transaction, **so a new note lists first** (`US-102.AC-2`). **Signed**, running downwards 0, −1, −2 … — so the column may not be made unsigned. **A reorder rewrites one whole level to `0..n-1`**, **no unique constraint** (the rewrite passes through duplicates mid-transaction), lists order by **`sort_key, id`**, gaps are harmless, and **a reorder does not move `updated_at`**. This **supersedes** plan 015's `MAX + 1` and that rule must not be reinstated |
| Paste warning threshold | **> 32,000 estimated tokens**, estimated as **characters ÷ 4** — roughly **128,000 characters** — two named constants in **`app/pasteCost.ts`**. **Advisory only**: nothing is refused, delayed or altered, which is why no tokenizer ships to the client. A paste into an **editor** never warns |
| RRF | **`k = 60`**, per-arm candidate depth **50**, result counts **8** (`memo_search`) / **5** (`session_search`) / **20 per group** (my-search). Ranks only, no score normalisation, ties on **ascending id**. **All conventional and unmeasured** — one consolidated `_TBD:` |
| `session_search`'s scope | **four terms**: `user_id` (the port's own), `character_id`, `id != :current_session_id`, `archived_at IS NULL`. Excerpt bound **1500 characters**, applied in the service |
| `session_vec` composition | **persona → setup → settled entries**, in that order, blank-line joined, empty parts dropped. Empty composed text → **no row at all** |
| `<think>` stripping | **exactly three places** — settle (assistant head, before `(( ))`), context assembly (current-zone assistant rows), translation (before caching) |
| The forbidden `vec0` form | `… MATCH ? AND k = ? AND <id> IN (...)` — silently drops true candidates above ~2^50. Recorded **once**, in `search-and-retrieval.md` |
| Derived-store writes | **every write to a `vec0` or FTS table must resolve its row ids through an owner-scoped query first** — those tables have **no user column** |
| Settle's head | the **last non-tool** row of `current_zone`; a tool-only zone is `zone_empty`. The client counts non-tool rows the same way, so `canSettle` and the server agree by construction |
| Settle's order | **bury (step 4) before stamping the head (step 5)** — once the head carries `settled_at` it is no longer in the zone and the burial set stops identifying itself. Driven by the id list read from `current_zone` **in the same transaction** |
| The tool registry | **three tools**, offered order `memo_search`, `session_search`, `web_search`; `web_search` additionally needs **instance credentials** |
| `session_fts` | **declared in doc history and never created** — its columns `title` / `partner_label` do not exist on `sessions`. Waits on the feature that gives a session text columns |
| Language of last resort | **English**, `US-142` — **a last resort, never a configured default**. Nothing writes it to a column or offers it in a picker. One constant in `services/translation.py`; the same fallback governs the prompt's instruction |
| Narrow viewport | the media query is written **`(width < 820px)`**, and the identical string is exported as **`NARROW_VIEWPORT_QUERY`** |
| `rphelper-export` | `format: "rphelper-export"`, **six header keys and no more** (`format`, `version`, `granularity`, `created_at`, `schema_version`, `payload`) — **no root-reference field**, because the root *is* the single row in the granularity's root table. Payload tables in `metadata.sorted_tables` order, rows in PK order, every column read by a **column-agnostic `select(Table)`**. **Two version constants, kept separate:** `version` (the envelope shape and the serialization rules) and `schema_version` (**a HAND BUMP whenever `db/schema.py` changes a table's shape**). Folding them would make every change to either look like a change to both. **Flip condition: if a hand bump is ever missed in practice, derive `schema_version` from the registry** |
| Never exported | credentials (only `"$ENV_VAR"` pointers travel; the web-search key is not even a pointer) · `auth_sessions` · `translations` · **every `vec0` and FTS5 table**. The one thing a reader expects to be stripped and is not: **`users.password_hash` at `database` granularity**, which is what lets restored users sign in (`US-077.AC-2`) |
| The whole-database replace | allowed **only** on an instance with no users, or exactly one user who is an administrator — otherwise `database_not_empty`. In one transaction it wipes every `metadata` table plus `auth_sessions` and `translations`, **drops** `memo_vec` and `session_vec`, and inserts the export's rows **with their own ids**. Answers **204 with the cookie cleared**. **The vec0 tables' absence after a restore is a legitimate state transition, not drift** |
| Import mechanics | fresh snowflakes **per table in ascending old-id order**; every FK plus `messages.related_to` and `memos.scope_id` rewritten; `user_id` (and a `scope='user'` memo's `scope_id`) set to the caller; **the payload's `users` row is never written**; a model pair kept only if it exists in the importing instance's `models`, else **both columns nulled**; timestamps and archived state preserved; **the self-reference written in two passes** (insert with `related_to` null, then `UPDATE`) because foreign keys are **immediate**. **Importing the same export twice yields duplicates and nothing warns** |
| FTS on import | **`ensure_fts_tables` runs inside the import transaction and the triggers index the inserts** — lexical search works immediately, semantic does not. **No import embeds anything**, at any granularity |

## Flip-condition index

Decisions taken under uncertainty, with what would have to become true for each to
be wrong. The doc named beside it owns the reasoning.

| Flip condition | Decision it would overturn | Doc |
|---|---|---|
| **A `sqlite-vec` release that fixes pushdown at large rowids** | the forbidden KNN form becomes available again; form (b) becomes worth revisiting if candidate sets grow | `search-and-retrieval.md`, `data-model.md` |
| **The SQLite write lock held across the provider round trip becoming visible** | embeddings-in-the-same-transaction → **mark-stale-plus-rebuild** (also the fan-out's runner-up, so the two move together — and taking it means adding the staleness column that was declined) | `search-and-retrieval.md`, `backend-structure.md` |
| **A whole-database export no longer fitting comfortably in process memory** | the export is built and encoded in memory as one response → a streamed response, at which point the column-agnostic `select(Table)` walk has to become incremental | `transfer.md` |
| **An export exceeding nginx's `64m` in practice** | raise the limit, or move to a streamed upload — and the streamed upload is the same change the export's memory posture needs | `deployment.md`, `transfer.md` |
| **A requirement to MERGE a whole-database export into a populated instance** | the replace-that-preserves-ids → a remap like the other three, and the single-admin guard becomes a merge policy | `transfer.md` |
| **A hand bump of `schema_version` being missed in practice** | the hand bump → derive it mechanically from the registry | `transfer.md` |
| **The first per-entity delete path** | the orphan-scope check having no reason to exist; an orphaned `(scope, scope_id)` becomes reachable | `data-model.md` |
| **A real tokenizer reaching the client, or the threshold proving too eager or too late** | chars ÷ 4 against 32,000 tokens | `domain-rules.md` R10 |
| **A request path needing a long or multi-statement transaction around an awaited call** | the async/sync mix is extended rather than resolved → move the database work off the loop, or adopt an async driver | `backend-structure.md` |
| **Google's Custom Search transition date, `2027-01-01`** — or the API ceasing to answer for this key | the one Google provider behind the seam → a new provider class plus the factory. **The first symptom is operational**: `web_search` starts failing as `tool_failed` while everything else works | `llm-and-streaming.md`, `deployment.md` |
| **Characters or setups gaining an FTS or vector index** | the `LIKE` path outside the port → they become port variants and the `LIKE` path goes | `search-and-retrieval.md` |
| **FEAT-015's promise needing lexical recall in real use** | `session_search`'s vector-only arm — **and it is no longer one switch**: it needs giving a session text columns and an index first | `search-and-retrieval.md`, `overview.md` |
| **My-search's duplicate query embedding becoming visible in latency or cost** | the port taking text rather than a vector | `search-and-retrieval.md` |
| **The `InterceptHandler` bridge proving fragile, or structured logs being needed** | `loguru` → stdlib `logging` + `dictConfig`; one module's rewrite, no call-site change | `deployment.md` |
| **`/api/health`'s PRAGMA walk showing against the healthcheck interval** | the roll-up narrows back to presence and the drift branch moves behind the admin route. **Caching the probe stays rejected** | `backend-structure.md` |
| **An admin surface needing `secret_ref_missing` or `schema_apply_failed` as an actionable, field-level message** | the shared **500 posture** → that code moves to a 4xx | `backend-structure.md` |
| **TLS termination anywhere in front of the application** | the cookie's `Secure` **off** → mandatory (one setter); **and the `execCommand("copy")` clipboard fallback becomes dead code** | `deployment.md`, `backend-structure.md` |
| **Sessions needing to survive activity beyond the absolute 720 h window** | no sliding expiry and no refresh route → a **bounded touch** (rewrite `expires_at` at most once per N minutes), never a write per request | `backend-structure.md` |
| **`argon2-cffi` becoming unmaintained, or its defaults being raised** | the seam module is the whole change surface — and raised defaults make a **rehash-on-verify** path necessary, which no feature owns | `overview.md` |
| **The registry no longer expressing a structure the product needs, or an UNATTENDED upgrade becoming a requirement** | registry-plus-a-button → migration files, because both cases want an ordered, replayable history | `overview.md` |
| **More than one generator process per node id** — a second uvicorn worker, or a second instance that syncs rather than imports | the 41/10/12 layout **and** the JSON string boundary both need re-examining before that change ships | `overview.md`, `data-model.md`, `deployment.md` |
| **`session_search` needing per-entry embeddings AND unscoped cross-character search** | `sqlite-vec` over a separate store; N climbs and approximate indexing starts to matter — which is why the port is narrow | `overview.md` |
| **A concurrency target, or a second concurrent writer per session** | context assembly's five separate sub-reads → one snapshot, worth its lock | `llm-and-streaming.md` |
| **A roleplayer legitimately writing `(( ))` inside RP prose** | R12's parse-once rule **silently drops it** → an escape mechanism becomes necessary (a sequence, a per-session switch, or a confirmed preview) | `domain-rules.md` R12 |
| **A list no longer fitting in one screenful of scrolling** | no sorting / filtering / pagination | `forms-and-lists.md` |
| **Moving off the stdlib `sqlite3` driver, or a release making transactional DDL the default** | the explicit transactional-DDL setting; `test_db_engine.py`'s DDL-rollback test is the check | `backend-structure.md` |
| **A third raw-dict route appearing** | the two named pydantic-boundary exceptions. Plan 030's original flip — extract the serializer into `models/` — is **already discharged**: the shared mechanism turned out to be the id-column predicate | `backend-structure.md`, `transfer.md` |
| **One request per zone-empty transition being judged worth it** | re-open's accepted imprecision (the control also shows on a lone settled turn, where the server refuses `nothing_to_reopen`). The route it would use **exists** — plan 022 built it and deliberately did not use it for this | `workspace-shell.md` |
| **The roleplayer asking to widen the wall or the tree** | no column resizes → splitter (A) returns on that one boundary, and `WorkspaceLayout` regains a number plus its clamp. **(B) does not return**; its subject no longer exists. **(C) has already returned in modified form** (2026-10-08): no auto-grow, internal scroll, but a native vertical handle rather than `resize: "none"` | `workspace-shell.md` |

## Deferred / non-goals

- ~~FEAT-018's four export granularities in full detail~~ — **no longer deferred**;
  the contract is `transfer.md`.
- ~~FEAT-016's `web_search` provider adapter~~ — **no longer deferred**; Google
  Custom Search behind a provider seam.
- **FEAT-002 deliberately does not build** (`overview.md`): session refresh /
  sliding expiry; rate limiting, lockout, attempt counting; "remember me";
  password reset / change-password (FEAT-003's); **rehash-on-verify (owned by no
  feature)**; session listing / sign-out-everywhere.
- **Frontend dependencies the foundation deliberately did not install**, each
  owned by the feature that first needed it — all now installed except
  **`postcss-preset-mantine`**, which has no call site.
- **Context compaction — an explicit non-goal, and no longer a `_TBD:`**
  (`vision.md`, restated in FEAT-009 and FEAT-010). Context grows forever; nothing
  warns first; a context-window refusal arrives as an ordinary generation failure
  whose reason is shown (US-044). **Decided, not open** — the reasoning stays
  visible because a planner still needs it.
- **TLS** — HTTP-only posture inherited, with the clipboard consequence recorded.
- **Metrics and alerting** — unspecified, and recorded as an **absence** rather
  than a `_TBD:`. Logging **is** specified.
- **Rebuild index (UC-016 / US-019)** — designed, **not built**; owned by
  `docs/plans/fast/002.vector-index-rebuild`. There is **no CLI alternative**, so
  the remedy needs a running application.
- **`POST /api/bootstrap/import` (UC-002)** — reserved, not built; owned by
  `docs/plans/fast/003.bootstrap-from-export`.
- **Abandoning a current zone is NOT here** — it is **resolved** (UC-086, US-134,
  US-135), frontend-only, no route, R11 unchanged.

## Open `_TBD:` items across the doc set

| Where | What |
|---|---|
| `search-and-retrieval.md` | **The retrieval constants, consolidated into one `_TBD:`**: `k = 60`, the per-arm depth of 50, and the counts 8 / 5 / 20 are conventional and user-confirmed, **not measured**. No relevance data and no corpus exists to tune them against |
| `search-and-retrieval.md` | **A progress surface for a long persona edit.** Inline re-embedding makes the edit one long request with no feedback. `docs/product/` describes no progress indication for any operation except UC-016's completion report, which is an admin surface. Raised for `/product-spec` |
| `search-and-retrieval.md` | **The COST of the per-write `session_vec` refresh on a long session, and it has no owner.** It was handed to "FEAT-015's plan"; **plan 027 did not close it** — no measurement of re-embed cost against session length exists, and bounding the *composed* text would be 024's code, not the tool's. **Re-pointed to the embedding owner or to a measured follow-up.** What is **not** open is *whether* the refresh happens (`US-110.AC-2` requires it), and plan 027's 1500-character **result excerpt** is a read-side bound with no effect on embedding cost |
| `admin-surfaces.md` | **Seed** exists in the inherited drift report and is **required by no UC** — RPHelper has no seed data at all, so it is recorded as prior art and deliberately not written up as a requirement. FEAT-005's plan (007) looked and declined without resolving it, so it stays open; the status set is correspondingly three values, not BookWriter's four |
| `overview.md`, `deployment.md` | **TLS / the exposure model.** Nothing in `docs/product/` states an exposure model. The cookie's `Secure` flag is no longer part of it (shipped off with a flip condition) and neither is the clipboard fallback (recorded with the same flip) |
| `deployment.md` | **`client_max_body_size 64m` is a judgement, not a measured figure.** `docs/product/` states no size bound, only that a paste is never refused. Raise it if a real import exceeds it; never lower it below what US-035.AC-2 implies |
| `deployment.md` | **Two nginx seams, one owner — `fast/001.dev-and-container-harness`, pending its finalization:** the **`location /app/` block**, which serves a URL space the root-mounted `app` entry never uses; and **`/login` without a trailing slash**, the exact target of the client's 401 navigation and the bootstrap refusal link, which does not match `location /login/` (the required behaviour — a relative 302 to `/login/` — is now fixed by the decided routing contract; only the prod directive's record is pending) |
| `deployment.md` | **NEW — nginx's own `access_log` still records full request URIs including query strings**, so `GET /api/search?q=<user text>` lands in it even though the application's access log no longer does. The fix — a `log_format` without `$args` / `$request_uri`, or `access_log off` for `/api/` — belongs to the deployment surface and is **owned by `fast/001`**. Found during plan 032's planning and explicitly out of its scope |
| `llm-and-streaming.md` | **NEW — the streaming read timeout.** The streaming call reuses `llm_request_timeout_seconds` — **30 s per httpx phase, including the READ between chunks**. Whether a slow first token on a large context needs a longer read timeout than a connect or a write is **unmeasured** (021 D10); no requirement states a latency bound, and splitting one setting into four before anything is observed would be a guess with four numbers instead of one |
| `ui-conventions.md` | **No wider accessibility target** (WCAG level, screen-reader matrix) is stated in `docs/product/`. The floor is what the icon and interaction contracts require, not a considered accessibility posture |
| `forms-and-lists.md` | **No sorting, filtering or pagination**, assuming small cardinality. `docs/product/` states no cardinality bound; a deployment with many accounts, or any future admin list over content-scale data, needs this revisited. **(This row's file changed — it used to be `ui-conventions.md`'s.)** |
| `overview.md` | **No concurrency target exists.** The design assumes one active roleplayer at a time per instance, which SQLite's single-writer model suits; `docs/product/` states no multi-user-concurrency expectation either way |

**That is the whole list. Everything else is closed, a defect, or an absence.**

### Closed in THIS pass — do not re-open, do not re-list

Each was an open `_TBD:` (or a flagged-for-another-owner note) in this doc set at
the start of plans 008..032 and is now **closed**. Re-adding any of them is a
regression, and a plan treating one as unanswered is reading a stale copy.

| Was open | Now |
|---|---|
| **Sparse snowflake rowids in `vec0` / FTS5** (`data-model.md`) | **Measured and verified** (024 D3, U6): sqlite-vec 0.1.9 / SQLite 3.47.1, 5000 × 768-d — insert, size and **unfiltered** KNN identical for dense and snowflake ids; FTS5 external content passes `integrity-check` at ~2^60. **Snowflakes stay the keys, no surrogate dense key.** One real defect came with it — **the forbidden pushdown form** |
| **Whether editing a NON-partner settled message discards its cached translation** (`data-model.md`) | **`US-111.AC-3` requires exactly what the build does**: editing **any** settled entry discards it. `edit_message_text` deletes on any text change, inside the edit transaction. The design inference became the requirement |
| **Whether `characters` / `setups` get FTS tables** (`data-model.md`) | **No.** Both are matched by a SQLite `LIKE` substring over their own columns (`name` + `sheet`, `name` + `description`); **no FTS table, no vectors, no schema change** (029 U2). The as-built `LIKE` limitation is **defect D-05** |
| **What session creation does when NO model is enabled** (R4, `data-model.md`) | **`US-143`:** the session **is created** and **captures none** until the roleplayer picks one — both columns NULL, and **nothing fills them later on its own**. Creation is never refused for want of a model, which keeps UC-080 reachable on a fresh instance. The refusal moves to **send** time, as `model_not_chosen` (`US-144`) |
| **The ENCODING of `sessions.model_ref`** (`data-model.md`) | **Two columns with a both-or-neither CHECK and no FK** — `model_server_id` + `model_name` (017 D4). `model_ref` and `tools` as literal column names are **deliberately absent** from the schema |
| **Whether UC-080's first message also draws an assistant reply** (`backend-structure.md`) | **Design closed: yes**, and the route **stays JSON** because the compose happens on the session once it exists (018 D2). **The code is missing — recorded as defect D-01**, not as work owed by a shipped plan |
| **Where the archive toggle sits** (`frontend-structure.md`) | **Closed in full** (018 D11): **three section-local toggles** — the tree header's "Show archived" for characters, "Show archived setups", "Show archived sessions" — **none persisted**, because showing archived material is a lookup, not a preference |
| **Whether the character page's composer carries the kind switch or a setup choice** (`workspace-shell.md`) | **Neither** (`US-117.AC-4`, 018 D1). There is no partner block yet for the switch's default to read, and UC-080 names no setup — so the session is created with `setup_id` NULL, which R2 makes first-class |
| **US-120's settled-decision default for the kind switch** (`workspace-shell.md`) | **`US-120.AC-3`:** a settled **decision** does not participate in the alternation. **And 013 D8 settles the empty-record case**: with no `partner`/`turn` entry at all the default is ***my turn***, because a wrong *partner* default files the roleplayer's own paste as a partner block, which is born settled and **not re-openable** |
| **The discard-empty-zone glyph** (`ui-conventions.md`) | **`IconX`**, labelled "Discard empty zone" (013 D3). `IconX` already means "dismiss" on the wall, and `IconTrash` would promise deleting content that by the rule is never there |
| **The enabled/disabled note toggle's glyphs** (`ui-conventions.md`) | **`IconCircleCheck` / `IconCircleOff`** (015 D14) — a two-icon swap whose labels name the **action**; the card additionally dims and strikes a disabled note's body, so the state is legible without reading the button |
| **`IconLanguage`'s toggle-state presentation** (`ui-conventions.md`) | **One icon, state in the label** (023 D15): "Show translation" / "Cancel translation" / "Show original", a distinct colour while translated, and **no `aria-pressed`** — a toggle whose accessible *name* changes must not also carry a pressed state |
| **The pin-glyph collision** (`ui-conventions.md`) | **Accepted and named** (user decision). The wall's pin and a note's "forced" flag are both `IconPin` and **do co-occur on one screen**; they are disambiguated by **label** and **location**, and the alternative was a second glyph for a concept that is genuinely "pin this" |
| **The "Collapse tree" glyph** (`ui-conventions.md`) | **`IconChevronLeft` is the decision of record** (008 D10) — confirmed, not replaced, because changing it now would be a code change a finalization must not require, and the mockup's intent is satisfied in spirit. **`IconLayoutSidebarLeftCollapse` is the named rejected alternative**; it loses on consistency, every other collapse control being a chevron |
| **No `web_search` provider chosen** (`llm-and-streaming.md`) | **Google Custom Search behind a provider seam** (plan 028) — one protocol, one implementation, five results, a 10 s timeout, no caching, the key in a header. Credentials from the environment without the `RPHELPER_` prefix; an unconfigured instance simply does not offer the tool |
| **How a disabled memo hit is marked in my-search** (`search-and-retrieval.md`) | **Dimmed and struck through, plus a gray "Disabled" badge** (029 D7) — the note wall's own idiom, so nothing new has to be learned. **Enabled and forced hits carry no marker at all** |
| **Whether ARCHIVED sessions participate in the persona-edit fan-out** (`search-and-retrieval.md`) | **They do — no archive predicate** (024 U4). Skipping them would make a restored session's vector silently stale, and "re-embed on restore" would make restore a write needing an embedding model, letting a platform gap block a pure R6 operation. The price is a fan-out proportional to a character's **whole** history |
| **Whether a per-session staleness marker earns a column** (`search-and-retrieval.md`) | **No marker and no column** (024 U5), and the recorded remedy is the whole-index rebuild. **The *consequence* was then reversed by `US-112.AC-3`**, which requires existing vectors to be **cleared** — the build leaves them stale, which is **defect D-04**. The recording decision stands; the behaviour does not satisfy the criterion |
| **Whether non-ASCII case-insensitive matching is required** (`search-and-retrieval.md`, 029 D3) | **`US-147` says yes — in any script.** SQLite's `LIKE` folds case for ASCII only, so the build does not satisfy it. **Recorded as defect D-05, NOT carried as an open `_TBD:`** |
| **The two named divergences from `docs/product/`** — a stopped tool call, and a stopped translation's cache (`llm-and-streaming.md`) | **Both acceptance criteria were amended on 2026-10-06 and now state what the build does.** `US-133.AC-1`: a stopped tool call **ends** the exchange. `US-133.AC-2` + its `Constraint:`: not caching a stopped translation is **best-effort**. The section is retitled **"Stopping, and what a stop is not"** and is settled design — the engineering reasons are kept, and **no doc in this folder now records either as awaiting a product change** |
| **UC-012's `user → character → session` inconsistency** (R4, and flagged here) | **Reconciled by the product round (challenge C42).** UC-012's exception flow no longer names a user level for the model, so the doc set no longer has to choose between it and UC-050/UC-047. Nothing about the prohibition changed — it never turned on which reading was right |
| **No frame carried the id of the roleplayer's own committed row** (`llm-and-streaming.md`) | **The `accepted` frame**, emitted **once, before the first `token`, and only when the compose carried text**. It makes R10's ordering observable and arrives on the failure path too, so an in-place edit of a just-sent message can `PATCH` without waiting for a reload (US-115) |
| **`@dnd-kit` available with nothing requiring it** (`frontend-structure.md`) | **Used — US-102 is the requirement.** One interaction, **two** mount points (the wall and the character page's notes grid), three packages, shared sensors and position-only announcements in `app/memoDnd.ts` |

**Also closed, in the previous delta, and still closed:** the observability
posture · `sessions.model_ref` after the character is configured with a model
(`US-139`) · the tool-iteration cap · unbounded context growth · abandoning a
current zone · what text composes `session_vec` (`US-138`) · the import
collision / merge policy (`US-136`) · whether changing the embedding designation
forces a rebuild · R12's double-parentheses assumption · UC-011's connection-test
taxonomy · `secret_ref_missing`'s status posture · whether Change Role realizes a
product id · whether a password reset revokes sessions · whether my-search shows
disabled memos (`US-137`) · the `session_vec` refresh *policy* · `IconMessageCheck`
for settle · the ORM choice · whether `session_search` gets a lexical arm ·
schema evolution · where the shell's layout CSS lives · `ui-conventions.md`'s
`id: number` page-state snippet.

**Closed since this pass (decision revision, 2026-10-07):** **the catch-all `/`
fallback and the app document** (`deployment.md`) — the app answers at `/` and
on its client routes **in dev and prod alike**. Prod: the image build copies
`dist/app/index.html` to `dist/index.html` (built by `fast/001`). Dev: a
serve-only Vite plugin rewrites navigation URLs to the same URL space as nginx
(to be built by an upcoming fast feature); `root: src/` and the four inputs are
unchanged. The old "host Vite does not serve `/`" reading is superseded — see
`deployment.md`'s Decision history.

**Revised (decision revision, 2026-10-08): the composer's text area.** "The
composer grows with its content" is **superseded**: no auto-grow, a native
vertical handle, default `rows` 3 (session) / 10 (character page start
composer), dragged height persisted under `rphelper.composer-heights`. Code
pending a follow-up fast feature — see `workspace-shell.md`'s "Geometry" and the
reversal record's decision history for (C).

## Defects — specified but unsatisfied, and NOT `_TBD:` items

**A defect is not an open question.** The design question is answered and the
requirement is settled; only the code is short. None of the five below may be
filed as a `_TBD:`, and none may be written up as though the specified behaviour
shipped.

**`docs/plans/defects.md` is the file of record.** It is the product round's
artifact: cite it, never edit it.

| Defect | Unsatisfied criterion | Recorded in |
|---|---|---|
| **D-01** | `US-117.AC-3` / UC-080 step 5 — the character page's opening message **draws no assistant reply**. The design is closed (yes, and the route stays JSON) and the trigger is missing; plan 018 deferred it and no later plan took it | `session-stream.md`, `workspace-shell.md` |
| **D-02** | `US-115.AC-1`'s streaming half — **the live reply has no edit control**. The build's reason is real: an edit would race the server's own write of that row (019 D11). **An open alternative reading is recorded and NOT resolved** — that US-115.AC-1 is conditioned on a message *sitting in* the zone, which an unpersisted in-flight reply is not, in which case D-02 is a clarification rather than a defect | `session-stream.md`, `workspace-shell.md`, `frontend-structure.md` |
| **D-03** | `US-112.AC-1` widened ("credentials the instance cannot use") — **the degraded embedding path does not catch `secret_ref_missing`**. The built catch set is `no_embedding_model` and `llm_unreachable` only, so an unset `$ENV_VAR` key makes a settle or a settled edit fail with a **500** and refuses the roleplayer's own text | `session-stream.md`, `backend-structure.md`, `search-and-retrieval.md` |
| **D-04** | `US-112.AC-3` — **a failed degraded embed leaves existing vectors stale instead of clearing them.** "No marker, no column" stands as the recording decision; the product reversed the consequence. Any fix is bound by the owner-scoped-ids rule, because the derived tables carry no user column | `session-stream.md`, `backend-structure.md`, `search-and-retrieval.md` |
| **D-05** | `US-147` — **my-search's `LIKE` folds case for ASCII letters only**, so a character or setup named in a non-Latin script matches only in the case typed. It matters more than it looks: `vision.md`'s premise is a roleplayer composing in a language they are not confident in. Any fix must preserve the escape handling — user input may never act as a wildcard | `search-and-retrieval.md` |

**Separately, and not one of the five:** the **`users.created_at` /
`updated_at` fixed-width timestamp deviation** (`data-model.md`). It predates
this round, came out of the finalization of plans 001..007, and is a
**pre-existing known defect owned by a `/bug-fixer` pass against plan 003**. It is
**not** a `_TBD:` and **not** `D-06`. Until it lands, nothing may compare those
two columns as text against a fixed-width value.

## Not `_TBD:` but flagged for another owner

- **024's banner-scope flag is NOT discharged.** The search-coverage banner is
  driven by the latest record-keeping write's response in the current view, so **a
  model removed while the roleplayer only reads shows no banner**. US-112.AC-2 is
  satisfied on the write that degrades, which is what the criterion asks. Whether
  the roleplayer should *also* be told on open, with no write at all, is
  **unspecified at the product layer** — and it would need the persisted staleness
  signal 024 U5 declined. The absence is left visible
  (`workspace-shell.md`).
- **The residual question behind the rebuild report's wording** — whether UC-016's
  completion report may carry an aggregate over all users' material at all — binds
  the **unbuilt `fast/002`** and is surfaced to the user rather than decided here.
  The conservative reading is written in both places: completion, and at most
  counts **not** derived from user content.
- **The `ComposerCore` / Send reconciliation is an open one-file check.** 018
  step 003 is recorded as rebuilding `Composer` on `ComposerCore`, which hard-
  renders Send, while 019 step 004 requires Send **absent** while streaming with
  Stop in its slot. Both shipped and **no outcome records how they were
  reconciled**; the docs state both facts in a form consistent with either
  reconciliation. **Not resolved here** — finalization does not harvest source.
- **The confirm step** on destructive admin actions is architectural judgement
  except where an AC now requires it — **clear embedding (US-015.AC-2)** and **a
  lossy Sync (US-018.AC-3/AC-4)**. The rest may be revisited by a later planner.
- **The derived-tables drift gap** (`admin-surfaces.md`): extending the report to
  cover `vec0` / FTS5 tables belongs to whichever feature first needs it. A
  virtual-table comparison designed against the four instances that now exist is
  at least possible, which it was not when the gap was first written.
- **`memos`' orphan-scope check is not built, and this doc set deliberately names
  no owner.** An orphan cannot arise today — nothing a memo scopes to is ever
  deleted, create validates its target, and the one whole-instance delete wipes
  both sides of every scope. Flip condition: the first per-entity delete path.
