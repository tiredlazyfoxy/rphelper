# Feature 023 — Partner translation · feature-wide context

## What this feature is

A settled **partner** entry gets a flicker. The first flick translates the entry into the
session's resolved preferred language. The result is shown in place of the original and
cached server-side in a new `translations` table. Flicking again shows the original. A
later flick of the same entry shows the cached translation without a new request. A failed
translation leaves the original showing, raises a visible failure and caches nothing. While
a translation is pending, the flicker becomes its cancel control: pressing it aborts that
request and leaves the original showing, with no error. Editing a partner block discards
its cached translation on both server and client, so the next flick translates the new
text (US-111).

A translation never enters session context (R8). The table is separate, context assembly
never reads it, and nothing in this feature touches the assembler.

The agreed boundary is `brief.md` in this folder. Its Definition and Scope In/Out bound
every step and are **not** widened: no translation of turns or decisions, and nothing that
puts a translation into context. Its one open question (streamed or awaited whole) is
closed by **D1**.

## Product ids

Delivers **FEAT-011** (UC-039, UC-040, UC-041) and **US-111** of FEAT-009. Exercises
UC-085 / US-133.AC-2 for translations only (D4).

| Criterion | Where it lands |
|---|---|
| US-045.AC-1 (first flick shows the preferred-language translation) | `002` (service), `003` (route), `004` (effect), `005` (flicker) |
| US-046.AC-1 (second flick is instant, no new lookup) | `002` (server cache hit, no model call), `004` (client cache, no request), `005` |
| UC-040 (flick back shows the original, nothing changes, no request) | `004`, `005` |
| US-047.AC-1 (translation absent from what the assistant reads) | `002` (assembled context unchanged by a cached translation; structural import check) |
| US-048.AC-1 (failure → original shown with a visible error) | `002` (`translation_failed`, nothing cached), `003` (502 on the wire), `004` (`notifyFailure`, stays on original), `005` |
| US-048.AC-2 (after a failure the next flick tries again) | `002` (no row written on failure), `004` (nothing cached client-side) |
| US-111.AC-1 (editing a partner block discards its cached translation) | `001` (server delete in the edit transaction), `005` (client invalidation) |
| US-111.AC-2 (the next flick translates the new text) | `001` + `002` (cache miss after edit), `005` (next flick re-requests) |
| US-133.AC-2 (stopped translation: original stands; nothing cached) | `004` / `005` (cancel → original, no error: unconditional). **"Nothing cached" is best-effort only**: `002` checks the disconnect once, right before the write (D4). |

**US-133.AC-2's "nothing is cached" is a named divergence** (`llm-and-streaming.md`
"Named divergences from `docs/product/`"). No DoD may claim it as a guarantee. The `[test]`
covers only the path where the probe reports a disconnect before the write.

## Build prerequisites

001..015 are built. **016..022 are planned and not built.** The roadmap builds in numeric
order, so 023 binds to their **declared** interfaces, cited by plan, step and decision,
never re-specified.

| Upstream | What 023 binds to | Needed by |
|---|---|---|
| 012 (built) `db/schema.py` `messages`, the `settled_entries` selectable; `errors.py` `MessageNotFoundError`; `services/messages.py` `edit_message_text` (widened by 014 `001`) | eligible-row read, the 404 path, the edit transaction the delete joins | `001`, `002` |
| 017 `001` / `003` | `get_session_configuration(conn, user_id, session_id)` (its `preferred_language.value`); `resolve_model_for_use(conn, user_id, session_id)` → `EnabledChatModel`; `NoModelEnabledError`, `ModelNotChosenError` | `002` |
| 020 `001` / `002` | `services/llm/chat.py` `ChatMessage` / `ChatRole`; `services/context.py` `assemble_context` (used by `002`'s US-047 test only) | `002` |
| 021 `001` | the `<think>` strip function in `services/llm/chat.py` (021 D4) | `002` |
| 021 `002` / `003` | `ChatMessage` with the `system` role (021 `003` DoD-1 sends one); `LlmClient.chat_stream(model, messages, tools)` → async iterator of `ChatDelta` (`content`, `reasoning`, `tool_calls`); `LlmUnreachableError` from it; the chat-client protocol and factory type and `open_chat_client(conn, model, timeout, factory)` in `services/llm_registry.py` | `002`, `003` |
| 021 `006` | the pattern of a chat-client factory as an overridable FastAPI dependency returning the real `LlmClient` class; `get_engine(settings)` with `Depends(get_settings)` | `003` |
| 013 / 014 (built) | `app/StreamRecord.tsx` `StreamEntry` (actions group, partner `Blockquote` body, `commit()` → `editEntry`); `app/SessionStream.tsx` (owns one `StreamState` per mount); `app/streamState.ts` effect conventions | `004`, `005` |

**021 is an effective build-order dependency of 023** even though `brief.md`'s
`Depends on:` omits it. The server-side call reuses 021's `chat_stream` and
`open_chat_client` (D2). The roadmap already orders 021 before 023. `brief.md` is not edited.

**Collision awareness, not dependencies:**

- 019 `004` / `005` own the composer's Send/Stop slot (`Composer.tsx`, the compose handle,
  `canSend`, `showsDiscard`). **023 touches none of them** (D4).
- 022 `007` also edits `StreamRecord.tsx` `StreamEntry`. It adds a `DiscussionGroup` under
  **non-partner** entries, while 023 changes **partner** entries only. The branches are
  disjoint, but the two edits sit in the same function, so expect a textual merge.

## Architecture this binds to

- `llm-and-streaming.md` "Translation" (not streamed; settled partner rows only; cache on
  success keyed `(message_id, target_language)`; `translation_failed`; discard on text
  change; never in context) and "Stopping a translation — best-effort", plus the US-133.AC-2
  entry in "Named divergences". "Context assembly" lists translations among the exclusions.
- `domain-rules.md` **R1** (preferred language resolves `user → session`), **R4**
  (resolve → validate → call, no fallback model), **R5** (owner scope in SQL; a foreign row
  is indistinguishable from a missing one), **R8**, **R11** (readers go through the views).
- `data-model.md` "`translations`" (only settled rows; unique pair; no state column; the
  invalidation `_TBD:` on non-partner edits, which this plan follows as designed).
- `backend-structure.md` layout (`services/translation.py`), "The error model"
  (`translation_failed`, detail = message id as a string), "The per-code status record",
  "The JSON id boundary", "Routers versus services".
- `workspace-shell.md` "The stream — the settled record" (partner actions include
  translate) and "The stop control" (a stopped translation leaves the original showing and
  the flicker un-flicked). D4 deviates from its claim that the composer Stop reaches
  translations.
- `ui-conventions.md` `IconButton`, the icon table (`IconLanguage`), the `_TBD:` on the
  flicker's state presentation (closed within this plan by D15), "Async feedback".
- `frontend-structure.md` "State — MobX 6", "Ids are strings", "The API client".
- `deployment.md` "The redaction rule" (never log text or translations; the
  `translate cached=… message=… ms=…` shape).
- Product: `stories/FEAT-011.partner-translation.md`,
  `use-cases/FEAT-011.partner-translation.md`, US-111 in
  `stories/FEAT-009.session-entries.md`, US-133 / UC-085 in the FEAT-010 files.

Cited, never copied.

## Files this feature touches

```
backend/
  app/db/schema.py               # + translations table                               (001)
  app/errors.py                  # + TranslationFailedError                           (001)
  app/models/translation.py      # NEW — response model                               (001)
  app/services/messages.py       # edit_message_text deletes the message's translations (001)
  app/services/translation.py    # NEW — translate flow, cache read/write             (002)
  app/routers/translation.py     # NEW — POST /api/messages/{id}/translation          (003)
  app/main.py                    # registers the translation router last              (003)
frontend/
  src/app/translationApi.ts      # NEW — translateMessage                             (004)
  src/app/translationState.ts    # NEW — per-row flicker state + effects              (004)
  src/app/StreamRecord.tsx       # the flicker on partner entries; edit invalidation  (005)
  src/app/SessionStream.tsx      # owns one TranslationState per mount                (005)
```

Test files are listed per step.

**Not touched. A step that touches one is out of scope:** `services/context.py`,
`services/compose.py`, `services/configuration.py`, `services/llm_registry.py`,
`services/llm/*`, `services/settle.py`, `routers/stream.py` (its stale "zone message"
docstring on the edit handler stays as is), `models/stream.py`, `dependencies.py`,
`db/engine.py`, `config.py`, `tests/conftest.py`; frontend `Composer.tsx`, `streamApi.ts`,
`streamState.ts`, `ZoneList.tsx`, `SessionScreen.tsx`, every `src/shared/*` module
(`IconButton.tsx`, `api.ts`, `notifyFailure.ts` included), every stylesheet,
`package.json` / lockfile, `tests/setup.ts`, `tests/conventions.test.ts`,
`tests/ids-are-strings.test.ts`, `tests/shared/notifyFailure.test.tsx`. **No new Python or
npm dependency.**

## Wire contract

`POST /api/messages/{message_id}/translation`. No request body. Router-level
`require_user`. Ids are decimal strings on the wire.

Success, 200:

```
Translation { message_id: "<decimal>", target_language: string, text: string, cached: boolean }
```

`cached` is `true` when the server answered from `translations` without a model call, and
`false` when this request produced the text.

Failures (`{ error: { code, message, detail } }`):

| Code | Status | When |
|---|---|---|
| `message_not_found` | 404 | the id is missing, another user's, a zone row, a buried row, or a settled `turn` / `decision` (D6) — all indistinguishable |
| `no_model_enabled` / `model_not_chosen` / `model_not_enabled` | 409 | cache miss and 017's use-time check refuses (D5) |
| `secret_ref_missing` | its existing status | cache miss and the server's key variable is unset (D5) |
| `translation_failed` | **502** | cache miss and the provider call failed, or the result was empty; `detail` `{ "message_id": "<decimal>" }` (D5) |
| `not_authenticated` | 401 | no login cookie |
| — | 422 | a non-numeric path id |

A cache hit answers 200 even when no model is enabled, because the check runs only on a
miss (D8).

## Cross-cutting constraints every step holds

- **R8 by construction.** No module that feeds the model imports `services/translation.py`
  or names the `translations` table. The table is read and written only by
  `services/translation.py`. The one exception is the delete in `services/messages.py`'s
  edit transaction (D11).
- **Owner scope in SQL (R5).** Every statement over `messages` / `translations` carries the
  caller's id in its own predicate. Another user's row takes the missing-row path.
- **Readers go through the views (R11).** The eligible-row read selects from
  `settled_entries`, never raw `messages`.
- **Nothing cached on failure (R8).** The only write to `translations` happens after a
  non-empty result, and only if the disconnect probe says the client is still there (D4).
- **Logs carry ids, booleans, codes and durations, never text.** No source text,
  translation, prompt or provider body at any level (`deployment.md`).
- **Routers own HTTP; services own SQL.** `services/translation.py` imports no `fastapi`.
  The disconnect probe reaches it as an injected async callable (D4).
- **Backend** is fully typed. `mypy app` and `ruff check .` stay green after every step.
- **Frontend:** TypeScript only, and `npm run typecheck` stays green. Pure data contracts
  (memory note): MobX classes hold observable fields only, and derivations and effects are
  free functions taking the state first. Effects `runInAction` after `await`, never reject,
  and recognise an abort as `signal?.aborted || (error instanceof Error && error.name ===
  "AbortError")`. Ids are strings compared by equality. **No success notification.**
  Every icon-only control goes through `shared/IconButton`.

## Decisions — settled, with their reasoning

U1–U4 are user-confirmed (binding). O-tagged items are orchestrator defaults. The rest are
planner decisions.

### D1 — Awaited whole, not streamed (U1; closes the brief's open question)

The translate route is a plain JSON request/response. A translation replaces the whole text
of a read-only flicker, so partial output has no use (`llm-and-streaming.md`). This plan
adds no SSE and no frame types.

### D2 — The server call reuses 021's `chat_stream`, joining content deltas (U2)

`chat_stream` is called with the resolved model's name, two messages (D8) and **no tools**.
The `content` of every delta is concatenated in arrival order. `reasoning` and `tool_calls`
are ignored. This makes 021 `002` / `003` a build prerequisite (above). Reusing the one
streaming call keeps one HTTP path to the provider. It also means a cancelled handler
unwinds the httpx stream exactly as a compose stop does.

### D3 — No preferred language resolved → English (U3)

The target language is `get_session_configuration(...).preferred_language.value`. When that
is null at every level, the target is the literal `English`, held in **one named module
constant** in `services/translation.py`. The cache key uses the **effective** target, so a
fallback translation is stored under `English`. **Conflict, recorded in `outcome.md`:**
`docs/product/features.md`'s FEAT-013 note says English is "merely the common case, never
the rule". The user chose this fallback. It is flagged for `/product-spec` and for the
architect, not designed around.

### D4 — Stop: the flicker itself cancels; the server check is best-effort (U4)

- **Client.** While a row's translation is pending, its flicker is the cancel control.
  Pressing it aborts that row's fetch. The original stays showing, the flicker is
  un-flicked, and **no notification** is raised, because a stop is not a failure. 019's
  composer Stop slot, compose handle, `Composer.tsx`, `canSend` and `showsDiscard` are
  **not touched**. This deviates from `workspace-shell.md` "The stop control", which says
  the composer Stop reaches a translation. The deviation is recorded in `outcome.md` for the
  architect.
- **Server.** The handler injects an async probe bound to `request.is_disconnected()`. The
  service awaits it **once, immediately before the cache write**. If it reports a
  disconnect, nothing is written. **Best-effort, not a guarantee:** a disconnect that lands
  after the probe still gets its row written (`llm-and-streaming.md`). No compensating
  delete and no transaction across the model call. Both were rejected by the architecture.

### D5 — Model and failure mapping (O)

On a cache miss, the model is the session's, from 017's `resolve_model_for_use`. Its
errors (`session_not_found`, `no_model_enabled`, `model_not_chosen`, `model_not_enabled`)
and `open_chat_client`'s `secret_ref_missing` propagate **unchanged**. Only two outcomes
become **`TranslationFailedError`**:

- `LlmUnreachableError` raised by `chat_stream`;
- a joined result that is empty after D10's strip and whitespace trimming.

The error has code `translation_failed` and HTTP **502**, because the failing party is a
dependency, as with `llm_unreachable`. Its `detail` is `{"message_id": "<id as decimal
string>"}`. Its message says which of the two causes it was (fixed sentences, `002`). That
is how "a failure says why" (brief) reaches `notifyFailure`. Nothing is cached on any
failure.

### D6 — Eligibility (O)

Translatable means: visible through `settled_entries`, `kind = 'partner'`, and owned by the
caller. Everything else raises `MessageNotFoundError` (404), the same for every case: another
user's row, a zone row, a buried row, a turn, a decision, an unknown id (R5). Language
equality is **not** checked: a partner block already in the preferred language is still
translated when flicked.

### D7 — The `translations` table (O)

In `db/schema.py`, on the one `metadata`:

| Column | Shape |
|---|---|
| `id` | snowflake PK, the schema's id column idiom |
| `user_id` | FK `users.id`, NOT NULL, the owner column as on other tables |
| `message_id` | FK `messages.id`, NOT NULL, **no cascade** |
| `target_language` | Text NOT NULL |
| `text` | Text NOT NULL |
| `created_at` | Text NOT NULL, the fixed-width timestamp form |

`UniqueConstraint("message_id", "target_language",
name="uq_translations_message_id_target_language")`. No `updated_at`, because a row is never
updated, only inserted or deleted. No state column, because absence means "not
translated". The drift page picks the table up from `metadata` automatically. `user_id` is
an addition to `data-model.md`'s column list. It is recorded in `outcome.md`.

### D8 — The service shape (O; phase split chosen here)

`services/translation.py` holds the flow as **three phases**. No connection is held across
the provider await. That is 021's posture, and 021 `005`'s compose source is the precedent
for a service taking the **engine** for this reason. The sync helpers still take a
`Connection` first.

1. **Read phase** (one short-lived connection, no transaction left open):
   - the eligible-row read (D6);
   - the target language (D3);
   - the cache lookup. **A hit returns `cached: true` here**, with no model resolution and
     no model call.
   - On a miss: `resolve_model_for_use`, then `open_chat_client` with
     `settings.llm_request_timeout_seconds`'s value and the injected factory.
2. **Call phase** (no connection): `chat_stream` joined (D2), mapped per D5. The iterator
   is always closed.
3. **Write phase:** the disconnect probe (D4), then one short write transaction. It does an
   insert-or-ignore on the unique pair, guarded by D9. Two concurrent first flicks therefore
   never answer 500. The service returns `cached: false` with the text it produced.

The system message instructs a faithful translation into the target language and to output
only the translation. The user message is the row's stored text, verbatim (`002` holds the
literal).

### D9 — No stale cache row after a concurrent edit (planner)

The write transaction inserts only if the message is still a settled partner row of the
caller **and its current text equals the text that was translated**. Otherwise it writes
nothing and still returns the produced text. Without this guard, an edit landing during the
model call (which deletes nothing yet, D11) would be followed by a cache row for text that
no longer exists, which is exactly what US-111 forbids. The guard is one comparison inside
the write transaction, and it adds no new code path.

### D10 — Reasoning stripped from the joined text (planner; flagged)

The joined content goes through 021 D4's `<think>` strip function before the empty check and
before caching. Some models emit inline `<think>` in content, and a flicker must not show
or cache reasoning. 021 D4 says the strip runs in "exactly two places". This makes a third,
and `outcome.md` flags it for the architect.

### D11 — Server-side invalidation on edit (O; US-111.AC-1)

`services/messages.py` `edit_message_text` deletes every `translations` row for the edited
`message_id`. The delete runs **inside its existing `with connection.begin():`, after the
`messages` update**, so the edit and the discard commit or fail together. It applies on
**any** text change of any kind, per `data-model.md`'s design inference: zone rows and
turns have no rows, so the delete is a no-op for them. A refused edit (not found, buried,
blank) deletes nothing.

### D12 — The route (O)

`POST /api/messages/{message_id}/translation` lives in a **new** `routers/translation.py`,
so `routers/stream.py` stays out of scope. It has router-level `require_user`, is an
**`async def`** (it needs `Request` for the probe), and takes:

- the caller (`require_user`);
- settings through `Depends(get_settings)`, giving the engine via `get_engine(settings)`
  and the timeout;
- the chat-client factory through **this router's own** overridable dependency, which
  returns the real `LlmClient` class (021 `006`'s pattern);
- the request.

It answers `TranslationResponse` (`models/translation.py`) built from the service result.
It is registered in `main.py` after every router already present.

### D13 — Client state: one `TranslationState` per stream mount, cache per mount (O; staleness accepted)

`SessionStream` owns one instance, as it owns `StreamState`. Per message id the instance
holds:

- whether the translation is shown;
- the translated text from the last success;
- whether a request is pending;
- that request's `AbortController`, held in a non-observable field.

A flick of a row with cached text shows it **with no request** (US-046.AC-1). Failures cache
nothing (US-048.AC-2).

**Accepted limitation, recorded in `outcome.md`:** the client cache is keyed by message id
only and lives for one mount. A preferred-language change made in 017's modal during the
same mount keeps showing translations in the old language until the stream remounts. The
server cache is keyed correctly, so a remount re-requests and gets the new language. Keying
the client cache by language would mean reading 017's configuration into the stream, for an
edge the roleplayer can clear by navigating.

### D14 — Client-side invalidation on edit (O; least-invasive wiring)

`StreamEntry` in `StreamRecord.tsx` calls the invalidate effect for a **partner** entry
after it hands that entry's draft to 014's `editEntry` and the effect settles. The call is
unconditional, made on success or failure alike. **`editEntry`'s signature and
`streamState.ts` are unchanged.** Invalidation aborts a pending request for that row, drops
its cached text and un-flicks it. On a failed edit this costs one extra request that the
server answers as a cache hit. That is cheaper than widening `editEntry` to report success.

### D15 — The flicker's presentation (planner; closes `ui-conventions.md`'s `IconLanguage` `_TBD:` within this plan)

The control is one `IconButton` with `IconLanguage` in the partner entry's actions group,
beside 014's Edit. The state shows in the **label**, which feeds tooltip and `aria-label`,
and in its **colour**. The three labels are "Show translation", "Show original" and
"Cancel translation" (`005`).

`shared/IconButton.tsx` is **not** widened. `ui-conventions.md` deliberately refuses a
`variant` escape hatch and further props. And under the ARIA toggle-button pattern, a
control whose name changes with its state must **not** also carry `aria-pressed`. The
architect records the choice via `outcome.md`. Turn and decision entries get no flicker
(US-131, brief Out).

### D16 — Five steps

| Step | Subject | Est. source LoC | Depends on |
|------|---------|-----------------|------------|
| 001 | `translations` table, `TranslationFailedError`, `TranslationResponse`, edit invalidation | ~60 | none (012 / 014 built) |
| 002 | `services/translation.py` | ~140 | 001; 017 `003`, 020 `001`–`002`, 021 `001`–`003` built |
| 003 | `routers/translation.py` + `main.py` | ~55 | 002; 021 `006` built (pattern) |
| 004 | `translationApi.ts` + `translationState.ts` (state, flick, cancel, invalidate, dispose) | ~140 | 003 (wire; tests stub `fetch`) |
| 005 | flicker in `StreamRecord.tsx`, ownership in `SessionStream.tsx`, edit invalidation | ~70 | 004; 022 `007` merged if built |

The server-side invalidation (~10 LoC) rides in `001`, because the table it deletes from is
born there and the step stays above the floor. `003` sits near the floor, but it is the
only HTTP layer and has its own test seam.

## Test conventions

**Backend** (from `backend/`): pytest, flat `tests/`, names
`test_<behavior>__S023_<SSS>_DoD<n>`. No shared fixtures, and `conftest.py` is untouched.
Each file has its own engine with `schema.metadata.create_all`, raw-insert helpers
(`_insert_user`, `_insert_character`, `_insert_session`, `_insert_message` with `kind`,
`settled_at`, `related_to`; registry rows `llm_servers` + `models` per 017's conventions)
and two users for isolation. Async service code runs through `asyncio.run(...)` from sync
tests (no async plugin).

The provider fake is a file-local fake chat client. It yields scripted `ChatDelta`s or
raises `LlmUnreachableError`, records each call's model name, messages and tools and
whether its iterator was closed, and is built by a file-local factory that records its
`(base_url, api_key, timeout)`. Router tests build `create_app()` with `dependency_overrides`
for `get_settings` (a file-local DB) and the translation router's factory dependency, and
log in with a file-local `_as(...)` client, modelled on `tests/test_stream_router.py`.

**Frontend** (from `frontend/`): Vitest/jsdom, `tests/` mirrors `src/`, each `it` title ends
`— DoD-N`. `fetch` is stubbed per test with `vi.stubGlobal`, keyed on exact pathname and
method. `notifyFailure` is observed through `vi.mock` of `src/shared/notifyFailure`, and
tests assert the `ApiError` code only, never prose. Rendered components sit inside
`<AppProviders>`. Ids are strings like `"7250000000000000101"`. Payload builders are
file-local: `Message` with all its keys, `Translation` with all four.

**Expected values come from this plan** (the wire contract, D3's literal, the strings in
`005.context.md`), never from calling the code under test.

## Vocabulary

| Term | Means here |
|---|---|
| **flick** | one press of a partner entry's translate control |
| **flicker** | that control plus the body it switches |
| **shown** | the row is displaying its translation rather than the original |
| **eligible row** | a settled, caller-owned `kind='partner'` row (D6) |
| **target language** | the resolved preferred language, else `English` (D3) |
| **cache hit / miss** | a `translations` row exists / does not for `(message_id, target_language)` |
| **disconnect probe** | the injected async callable the service awaits before writing (D4) |
| **invalidate** | drop a row's cached translation: server delete on edit (D11), client drop (D14) |
