# Decision index

Registry of every `DEC` id. Regenerated from the entries on every write — never
edited independently of the files (`AGENTS.md`).

| Id | Title | Status | Feature | Stage |
|---|---|---|---|---|
| DEC-034-1 | The rename body's `name`: a required key, string or null, normalised on both sides | accepted | 034.session-names | — |
| DEC-034-2 | `extra="forbid"` on the rename request model: the one named exception | accepted | 034.session-names | — |
| DEC-034-3 | No length cap on a session name | accepted | 034.session-names | — |
| DEC-034-4 | `sessions.name` is a privacy-audit content carrier; the rename route is an owner route | accepted | 034.session-names | — |
| DEC-034-5 | The name is not part of the embedded session text; a rename embeds nothing | accepted | 034.session-names | — |
| DEC-034-6 | `RpSession.name` defaults to None and is declared last | accepted | 034.session-names | — |
| DEC-034-7 | The version-1 upgrade: the deserializer learns the file's version; only `sessions.name` may be absent | accepted | 034.session-names | — |
| DEC-034-8 | My-search wire keys and hydration: session hit `name`, entry hit `session_name`; name hits by name then id | accepted | 034.session-names | — |
| DEC-034-9 | The client label module: `sessionLabel`, a local-date fallback, `formatLocalDateTime` | accepted | 034.session-names | — |
| DEC-034-10 | Rename affordances: an `IconEdit` button on every tree session row and beside the header title | accepted | 034.session-names | — |
| DEC-034-11 | Rename editor semantics: unchanged sends nothing, one in flight, inline failure, apply the returned row | accepted | 034.session-names | — |
| DEC-034-12 | `applySession` orders `last_used_at` ties by id descending | accepted | 034.session-names | — |
| DEC-034-13 | The character page's Sessions list follows the workspace store by the apply-a-row rule | accepted | 034.session-names | — |
| DEC-034-14 | The workspace `SessionsState` is threaded to the session screen as a prop | accepted | 034.session-names | — |
| DEC-035-1 | The factory takes `kind` first; the gateway class is the production factory | accepted | 035.llm-client-gateway | — |
| DEC-035-2 | Probe value types move to the gateway; the delta types are deleted | accepted | 035.llm-client-gateway | — |
| DEC-035-3 | The gateway's test seam is a keyword-only map of library client classes | accepted | 035.llm-client-gateway | — |
| DEC-035-4 | `to_wire_message` is kept and builds the library's `messages` | accepted | 035.llm-client-gateway | — |
| DEC-035-5 | Library typing gaps are absorbed inside `gateway.py` only | accepted | 035.llm-client-gateway | — |
| DEC-035-6 | The chat-client protocol: `complete`, `compose`, and the tool bundle | accepted | 035.llm-client-gateway | — |
| DEC-035-7 | One unbounded queue, an end marker, and cancel-and-await on close | accepted | 035.llm-client-gateway | — |
| DEC-035-8 | How each operation maps library failures | accepted; superseded in part by DEC-035-20 (auth test), DEC-035-17 and DEC-arch-llm-client-library-15 (temporary-limitation cases), DEC-035-16 (exception set) | 035.llm-client-gateway | — |
| DEC-035-9 | Probe builds its library client with an empty model name | accepted | 035.llm-client-gateway | — |
| DEC-035-10 | `compose` uses the tool loop even when no tool is offered | accepted | 035.llm-client-gateway | — |
| DEC-035-11 | Base-URL normalisation rule | accepted | 035.llm-client-gateway | — |
| DEC-035-12 | Live tests port to the gateway, `kind` `llamaswap` | accepted | 035.llm-client-gateway | — |
| DEC-035-13 | Two unlisted probe-type importers move to the gateway in step 002 | accepted | 035.llm-client-gateway | — |
| DEC-035-14 | Five unlisted test modules follow step 002's interface | accepted | 035.llm-client-gateway | — |
| DEC-035-15 | Step 001 DoD-14's client-module identity check is retired with client.py | accepted | 035.llm-client-gateway | — |
| DEC-035-16 | Every exception out of the library, and a malformed tool declaration, surfaces as `llm_unreachable` / `unreachable` | accepted | 035.llm-client-gateway | — |
| DEC-035-17 | A model-side rejection reaches the compose source as its own stream value, `ComposeRejected` | accepted | 035.llm-client-gateway | — |
| DEC-035-18 | A model-side rejection is logged with the tool name and the kind only | accepted | 035.llm-client-gateway | — |
| DEC-035-19 | Explicit tool signatures stay under 0.2.1 | accepted | 035.llm-client-gateway | — |
| DEC-035-20 | The status-based auth split covers all four operations | accepted | 035.llm-client-gateway | — |
| DEC-F001-1 | The `/` seam is a copy in the image build, after a presence check | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-2 | No `location /app/` block | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-3 | Slash-less entry paths: exact-match locations returning a relative 302 | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-4 | `absolute_redirect off` at server level | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-5 | `location ^~ /api/` | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-6 | Path-only access log, declared inside the `server` block | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-7 | Deployment file layout and how the image installs its configs | accepted; compose layout superseded by DEC-F013-4 | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-8 | supervisord runs nginx and exactly one uvicorn, with no wait-for ordering | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F001-9 | `start.ps1`: two flags, two terminals, literal ports | accepted | fast/001.dev-and-container-harness | 001.instance |
| DEC-F002-1 | One blocking request; no job runner and no progress stream | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-2 | One transaction, all-or-nothing; the write lock is held across embedding | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-3 | The response is the fixed list of the four derived table names | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-4 | Always available; no designation fails with `no_embedding_model` | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-5 | Always drop and re-create both vector tables | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-6 | Order inside the transaction | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-7 | Chunked embedding with a fresh handle per chunk | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-8 | FTS: full rebuild for memos, record-rows-only refill for messages | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-9 | Placement: a service module, with public table helpers beside their constants | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F002-10 | Page-local confirm state; the confirm button is labelled "Rebuild" | accepted | fast/002.vector-index-rebuild | 004.retrieval |
| DEC-F003-1 | Schema creation and the import run in one transaction, through an extracted helper | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F003-2 | The restore route signs nobody in | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F003-3 | After the restore the operator is sent to `/login`; the environment notice is static copy | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F003-4 | The restore choice: a second offer item, no confirm modal (plan "Decision 4") | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F003-5 | Accepted consequences, deliberately not special-cased | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F003-6 | The restore's log line carries an outcome token only | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F003-7 | A native file input inside `Input.Wrapper`, not Mantine's `FileInput` | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F003-8 | `failureMessageOf` is exported from the restore module | accepted | fast/003.bootstrap-from-export | 005.portability |
| DEC-F004-1 | The session screen composes after arrival; the create route stays JSON | accepted | fast/004.character-page-first-reply | 006.repair |
| DEC-F004-2 | The trigger is a one-shot router-state marker, consumed on arrival | accepted | fast/004.character-page-first-reply | 006.repair |
| DEC-F004-3 | One textless compose through the existing path, at most once per stream state | accepted | fast/004.character-page-first-reply | 006.repair |
| DEC-F004-4 | Reload, or arriving mid-compose: no special handling | accepted | fast/004.character-page-first-reply | 006.repair |
| DEC-F004-5 | The page composer does not take a send-blocked reason | accepted | fast/004.character-page-first-reply | 006.repair |
| DEC-F005-1 | The caught set is a named tuple of three errors, not a base type | accepted | fast/005.degraded-embedding-path | 006.repair |
| DEC-F005-2 | A degraded write clears the session's vector, resolving its id owner-scoped first | accepted | fast/005.degraded-embedding-path | 006.repair |
| DEC-F006-1 | A registered SQLite function, not a stored folded column and not a collation | accepted | fast/006.unicode-name-matching | 006.repair |
| DEC-F006-2 | Registration sits between the sqlite-vec load and the PRAGMAs | accepted | fast/006.unicode-name-matching | 006.repair |
| DEC-F006-3 | Fold both sides and keep SQLAlchemy's autoescape, through one helper | accepted | fast/006.unicode-name-matching | 006.repair |
| DEC-F006-4 | Case folding only: no accent folding, no normalization | accepted | fast/006.unicode-name-matching | 006.repair |
| DEC-F006-5 | The session-name arm uses the same fold; correction of `DEC-arch-session-names-5` | accepted | fast/006.unicode-name-matching | 006.repair |
| DEC-F007-1 | Line shape, sink, and no prefix | accepted | fast/007.vite-proxy-request-log | — |
| DEC-F007-2 | Duration is measured to the response headers, not to the end | accepted | fast/007.vite-proxy-request-log | — |
| DEC-F007-3 | Start time from the earliest per-request event, keyed per request | accepted | fast/007.vite-proxy-request-log | — |
| DEC-F007-4 | At most one line per request | accepted | fast/007.vite-proxy-request-log | — |
| DEC-F007-5 | Redaction: path cut at `?` and `#`; an error carries its code only | accepted | fast/007.vite-proxy-request-log | — |
| DEC-F007-6 | Attach through the `/api` rule's `configure` hook; attaching is silent | accepted | fast/007.vite-proxy-request-log | — |
| DEC-F008-1 | A separate module; defaults shared with the proxy logger | accepted | fast/008.vite-dev-request-log | — |
| DEC-F008-2 | The skip rule mirrors the proxy's match exactly | accepted | fast/008.vite-dev-request-log | — |
| DEC-F008-3 | Duration to response end; status read at finish; an aborted request shows `-` | accepted | fast/008.vite-dev-request-log | — |
| DEC-F008-4 | A missing URL is logged, not skipped | accepted | fast/008.vite-dev-request-log | — |
| DEC-F008-5 | Registration: first in the chain, serve-only, silent, always `next()` | accepted | fast/008.vite-dev-request-log | — |
| DEC-F008-6 | `import.meta.dirname`, `.ts` specifiers, and `allowImportingTsExtensions` in both tsconfigs | accepted | fast/008.vite-dev-request-log | — |
| DEC-F009-1 | Plugin home, name and position | accepted | fast/009.vite-dev-root-routing | — |
| DEC-F009-2 | The routing predicate | accepted | fast/009.vite-dev-root-routing | — |
| DEC-F009-3 | Only `type="module"` script srcs are absolutized, by the plugin's own HTML hook | accepted | fast/009.vite-dev-root-routing | — |
| DEC-F009-4 | The request log keeps the browser's URL | accepted | fast/009.vite-dev-root-routing | — |
| DEC-F010-1 | The login probe leaves the form only on a strict `configured === false` (D1) | accepted | fast/010.unconfigured-to-bootstrap | — |
| DEC-F010-2 | The `{ configured }` reader stays entry-local in two places (D2) | accepted | fast/010.unconfigured-to-bootstrap | — |
| DEC-F010-3 | The probe's phase lives in a login-local MobX store (D3) | accepted | fast/010.unconfigured-to-bootstrap | — |
| DEC-F010-4 | The no-account guard's predicate is "any user exists", not `is_configured` (D4, amended) | accepted | fast/010.unconfigured-to-bootstrap | — |
| DEC-F010-5 | Placement: a guard in `dependencies.py`, its read in `services/bootstrap.py` (D4) | accepted | fast/010.unconfigured-to-bootstrap | — |
| DEC-F010-6 | Accepted cost: two small reads per cookie-bearing request | accepted | fast/010.unconfigured-to-bootstrap | — |
| DEC-F011-1 | Send is an icon-only control in the text box's bottom-right corner; Stop takes the same slot | accepted | fast/011.composer-send-icon-and-shortcut | — |
| DEC-F011-2 | The right section passes pointer events through except over the Send/Stop control | accepted | fast/011.composer-send-icon-and-shortcut | — |
| DEC-F011-3 | The dragged height is saved at drag end and restored on mount, per composer | accepted | fast/011.composer-send-icon-and-shortcut | — |
| DEC-F011-4 | Ctrl/Cmd+Enter sends when Send is shown and enabled; the text area is a fixed-rows, vertically resizable box | accepted | fast/011.composer-send-icon-and-shortcut | — |
| DEC-F012-1 | A flag click toggles only the flag; it does not save the body | accepted | fast/012.notes-autosave-toolbar-flags | — |
| DEC-F012-2 | One note behaviour supersedes plan 033's opt-in header-add mode | accepted | fast/012.notes-autosave-toolbar-flags | — |
| DEC-F012-3 | The shared markdown editor takes one optional trailing toolbar group | accepted | fast/012.notes-autosave-toolbar-flags | — |
| DEC-F012-4 | The note group's mechanics: header '+', focus-leave drafts, no Save/Cancel | accepted | fast/012.notes-autosave-toolbar-flags | — |
| DEC-F013-1 | The version comes from exactly one `vX.Y.Z` tag on HEAD | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F013-2 | `git tag --points-at HEAD`; two matching tags fail as ambiguous | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F013-3 | The store is `$DOCKER_STORE/rphelper` | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F013-4 | Compose restructure: dev takes the standard name; prod is image-based | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F013-5 | No `.env` templating; deploy refuses to restart without `.env` | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F013-6 | The archive is written to a temp file in the store and renamed on success | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F013-7 | `deploy.sh` mirrors BookWriter's `update.sh` | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F013-8 | Script conventions: strict mode, self-location, offline tests | accepted | fast/013.build-and-deploy-scripts | — |
| DEC-F014-1 | Build single-message delete now; the docs follow at finalization | accepted | fast/014.message-delete | — |
| DEC-F014-2 | Settled entries and current-zone messages are both deletable | accepted | fast/014.message-delete | — |
| DEC-F014-3 | A settled head takes its buried group with it, in the same transaction | accepted | fast/014.message-delete | — |
| DEC-F014-4 | The trash control confirms in red; a blank editor commit does not | accepted | fast/014.message-delete | — |
| DEC-F014-5 | Delete refusals mirror edit's — no new error code | accepted | fast/014.message-delete | — |
| DEC-F014-6 | 200 with `{deleted_ids, search_coverage_incomplete}`, not 204 | accepted | fast/014.message-delete | — |
| DEC-F014-7 | The service's order inside one transaction | accepted | fast/014.message-delete | — |
| DEC-F014-8 | Full-text upkeep follows the memo delete's placement | accepted | fast/014.message-delete | — |
| DEC-F014-9 | Frontend delete effects: never optimistic, never rejecting, never setting busy | accepted | fast/014.message-delete | — |
| DEC-F014-10 | A blank edit commit delegates to delete; unchanged text is a no-op | accepted | fast/014.message-delete | — |
| DEC-F014-11 | Trash icon placement, labels and gating | accepted | fast/014.message-delete | — |
| DEC-F014-12 | What single-message delete deliberately does not do | accepted | fast/014.message-delete | — |
| DEC-F014-13 | The trash control's disabled condition, and its untested half | accepted | fast/014.message-delete | — |
| DEC-F015-1 | Build the pending indicator in code; no product or architecture change now | accepted | fast/015.translate-pending-indicator | — |
| DEC-F015-2 | While pending, the flicker's glyph is a spinning loader instead of the language icon | accepted | fast/015.translate-pending-indicator | — |
| DEC-F015-3 | Label and accessibility semantics are unchanged while pending | accepted | fast/015.translate-pending-indicator | — |
| DEC-F015-4 | An entry's actions group is revealed while that entry's translation is pending | accepted | fast/015.translate-pending-indicator | — |
| DEC-F016-1 | Build the own-text tone in code; no product or architecture change now | accepted | fast/016.own-text-muted | — |
| DEC-F016-2 | The user-role row body is wrapped in a Mantine `Box` with `c="dimmed"` | accepted | fast/016.own-text-muted | — |
| DEC-F016-3 | Settled entries, the live reply and accent chips keep their colours | accepted | fast/016.own-text-muted | — |
| DEC-F016-4 | Test hook: `data-tone="muted"` on the wrapper | accepted | fast/016.own-text-muted | — |
| DEC-arch-llm-client-library-1 | Adopt `llm-client` 0.2.0 as a git dependency; Responses clients only, selected by `kind` | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-2 | One timeout: total time per request, default 600 s | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-3 | `auth_failed` is read from the library error's message | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-4 | The tool-loop cap is `max_loops=sys.maxsize` | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-5 | Minted call ids, and the persisted `arguments` | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-6 | Each wrapper carries an explicit signature from its declaration | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-7 | The wrapper never raises a tool's exception into the library | accepted; temporary-limitation clause superseded by DEC-arch-llm-client-library-15 | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-8 | How a compose exchange ends | accepted; temporary-limitation clause superseded by DEC-arch-llm-client-library-15 | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-9 | An OpenAI server with no credential | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-10 | Logging: the `aiohttp` logger tree is silenced | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-11 | Testing: fakes at the gateway/factory level | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-12 | No reasoning options are sent by default | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-13 | Pin `llm-client` `v0.2.1` | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-14 | `compose` passes `tool_errors="result"` explicitly | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-15 | Model-side tool mistakes become tool frames through the observer | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-16 | `auth_failed` is read from `LLMError.status` | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-llm-client-library-17 | 0.2.1 options left unused: `read_timeout`, the trace switch, the provider call id | accepted | arch-llm-client-library | architecture revision |
| DEC-arch-session-names-1 | Name storage: a nullable column, the default label computed by the client | accepted | arch-session-names | — |
| DEC-arch-session-names-2 | Route shape: a general `PATCH` that accepts `name` only | accepted | arch-session-names | — |
| DEC-arch-session-names-3 | Last-use display: local `YYYY-MM-DD HH:MM`, fixed width | accepted | arch-session-names | — |
| DEC-arch-session-names-4 | Rename interaction: in-place edit of the label | accepted | arch-session-names | — |
| DEC-arch-session-names-5 | My-search's session name arm: `LIKE`, merged ahead of vector hits | accepted; superseded in part by DEC-F006-5 (the D-05 case caveat) | arch-session-names | — |
| DEC-arch-session-names-6 | A rename bumps `updated_at` only | accepted | arch-session-names | — |
| DEC-arch-session-names-7 | Import accepts `schema_version` 1 through one named upgrade | accepted | arch-session-names | — |
