# fast/004.character-page-first-reply — context

Brief: `brief.md` (this folder). Its Definition and Scope In/Out are the boundary and
are not restated here.
Delivers: FEAT-008 — UC-080 step 5, US-117.AC-3. Closes defect **D-01**
(`docs/plans/defects.md`).
Design: `docs/architecture/session-stream.md` ("The opening message draws no assistant
reply, and that is defect D-01"), `docs/architecture/frontend-structure.md` ("Routing
inside the `app` entry": `/characters/:id` also starts sessions),
`docs/architecture/llm-and-streaming.md` (the frame table, the textless compose;
"Stopping model work in flight — UC-085"). Prior decisions: `018.character-page`
`context.md` D2 (create route stays JSON) and D4 (page composer's `sendBlockedReason`
left unused), `018/outcome.md` "Forward notes".

**Frontend only.** No backend file changes.

## What exists today (harvested, verified)

### Backend (read-only for this feature)

- `POST /api/characters/{id}/sessions` (`backend/app/routers/sessions.py`, 201 JSON) with
  `{ opening_message }` calls `start_seeded_session`: one transaction creates the session
  row and one current-zone `role='user'` message. **No model call.**
- `POST /api/sessions/{id}/zone/compose` with body `{}` is a **textless compose**. On a
  zone holding only the roleplayer's seeded message it is allowed: `begin_compose` raises
  `ZoneEmptyError` only when the zone has no non-tool row. A textless compose emits **no
  `accepted` frame**, because no row is inserted. The rest of the frames (`token`,
  `tool_*`, `error`, `done`) are as in `llm-and-streaming.md`.
- There is no server-side in-flight registry and no concurrency guard. A client abort or
  disconnect persists the partial text as an ordinary current-zone assistant row. Nothing
  keeps running server-side that a client could reattach to.

### Frontend

- **Page composer.** `frontend/src/app/sessionsApi.ts` has `startSessionWithMessage`.
  `frontend/src/app/characterComposerState.ts` has `sendCharacterComposer(state, sessions,
  onStarted)`. `frontend/src/app/CharacterComposer.tsx` (around lines 45-51) calls
  `void navigate(`/sessions/${id}`)` from `onStarted`. That is a bare push with no router
  state. The push (not replace) is deliberate (018 D5): Back returns to the character page.
- **Session screen.** `frontend/src/app/SessionScreen.tsx` is the **only router reader**
  on the session screen. It uses `useSearchParams` for `?entry=` and `?notes=open`,
  creates `SessionConfigState`, and passes `sendBlockedReason(configState)` to
  `SessionStream`.
- `frontend/src/app/SessionStream.tsx` creates one `StreamState`, owns the abort
  `controllerRef`, and calls `loadStream(state, signal)` in an effect. Under StrictMode the
  double mount aborts the first load. It deliberately uses **no router hook** (029
  decision 9). That must stay true.
- `frontend/src/app/streamState.ts`:
  - `loadStream` (~189) fetches entries and zone;
  - `composeMessage` (~488);
  - private `runCompose(state, text | undefined, signal)` (~537), which never rejects,
    reports failure through `notifyFailure` and re-reads the zone at the end;
  - `regenerate(state, signal?)` (~653), which is already a textless compose, gated by
    `showsRegenerate(state)` (not streaming, not busy, zone has a non-tool row).
- `frontend/src/app/streamApi.ts` (~124) has `composeZone(sessionId, text | undefined,
  onFrame, signal)`, which POSTs `/api/sessions/<id>/zone/compose`. The body is `{}` when
  there is no text.
- `frontend/src/app/sessionConfigState.ts` (~201) has `sendBlockedReason(state)`. It
  returns reasons for: no model enabled, model not chosen, model not enabled. An unknown
  state never blocks. Config loads in `SessionConfigBar` after the first ready render.

### Existing test conventions (for the test-coder)

- `frontend/tests/app/CharacterComposer.test.tsx` uses `AppProviders` and `MemoryRouter`,
  with a `/sessions/:id` probe route. It observes navigation through the location and
  stubs fetch with `stubFetch`.
- `frontend/tests/app/SessionScreen.test.tsx` serves entries and zone for any id.
- `streamRegenerate.test.ts` asserts the textless `{}` body.
- `streamCompose.test.ts` and `SessionStream.test.tsx` fake streams as a `Response` over a
  `ReadableStream` of encoded SSE chunks. Routes are keyed `"METHOD path"`.

## Decisions (settled by the orchestrator; binding)

**D1 — Shape: the session screen composes after arrival. The create route stays JSON.**
`018` D2 kept the route's media type fixed, and `session-stream.md` records the question
as **closed** in that direction. The rejected alternative is turning the create route into
a streaming response. That would change a delivered contract and add a second streaming
harness, all for one call site, while `composeZone` already does the job. As a result,
nothing in `backend/` changes.

**D2 — Trigger: a one-shot router-state marker, not something derived from the zone.**
- `CharacterComposer` keeps its push to `/sessions/<id>` and adds a router `location.state`
  marker meaning "this session was just seeded from the character page".
- `SessionScreen`, the only router reader, reads the marker and passes a boolean prop to
  `SessionStream`.
- `SessionScreen` then **consumes the marker at once**: it replaces the current history
  entry with the same path and search, and with the state cleared. A reload, Back/Forward
  or re-render therefore never fires again.
- Rejected: composing whenever a session opens on a zone that ends with an unanswered
  user row. That would change behaviour for every session reopened in that condition,
  which this feature does not own. Such a zone is a legitimate resting state, for example
  after a stopped compose or a send the server refused.

**D3 — Start: one textless compose through the existing machinery, idempotent per
`StreamState`.**
- After `loadStream` resolves to ready, the compose starts only when **all** of these hold:
  - the intent is set;
  - the stream's own signal is not aborted;
  - the zone's last non-tool row is the roleplayer's (`role === "user"`);
  - nothing is already streaming or busy.
- It goes through the same private compose path as a discussion compose. It is not a
  second client and not a second frame consumer. So the reply renders as the ordinary
  live reply, Stop is available, failure goes through `notifyFailure`, and the zone is
  re-read at the end.
- It fires at most once per `StreamState`, so StrictMode's double effect cannot start two
  requests. The first mount's load is aborted before it resolves, and the second is
  guarded by the once-flag.
- The intent must survive the marker being cleared from history. Clearing the history
  re-renders `SessionScreen`, and that must not drop the intent before the load resolves.
  `SessionScreen` therefore captures it once for the session id it opened on. It does not
  re-read it from `location.state` on every render.

**D4 — Reload, or arriving mid-compose: no special handling.**
- Leaving the page or reloading aborts the fetch. The server persists whatever partial
  text exists as an ordinary current-zone assistant row (`llm-and-streaming.md`
  consequence 1).
- On return the marker is gone (D2), so nothing re-fires. The roleplayer sees the partial
  row and can use Regenerate (US-132-style, as for any stopped reply).
- There is no in-flight registry to reattach to, and adding one is outside this feature
  (`llm-and-streaming.md` rejects a registry by design).
- This is the accepted answer to the brief's third open question.

**D5 — Blocked reason: the page composer does not take `sendBlockedReason`.**
- Creating the session makes no model call and needs no model.
- The character page has no models list to compute a reason from, and loading one there
  is out of scope.
- If the auto-compose is refused (for example, no model enabled gives a 409 error), the
  session screen shows it two ways. `runCompose`'s existing failure path reports the
  refusal through `notifyFailure`. Once config loads, the session `Composer`'s own blocked
  reason explains why.
- The opening message is never lost (R10): it is a persisted zone row either way.
- This is the accepted answer to the brief's second open question. `018` D4's unused prop
  stays unused.

**D6 — Docs are touched only through `outcome.md`.** Neither `docs/architecture/` nor
`docs/plans/defects.md` is edited by this feature. D-01 is closed by this plan's
`status.md` (per `defects.md`'s own rule). `outcome.md` records the architecture prose
that describes the reply as missing and must be rewritten.

## Constraints

- TypeScript only. `npm run typecheck` is a gate. No new dependency.
- `SessionStream` stays free of router hooks (029 decision 9). Only `SessionScreen` reads
  or writes router state.
- The page's navigation stays a **push** (018 D5). The marker clearing is a **replace** of
  the session entry, which leaves the character-page entry underneath intact.
- Mutations are never optimistic: the reply appears only as the streamed live reply, then
  the re-read persisted row.
- No change to `sessionsApi.ts`, `characterComposerState.ts`, `streamApi.ts` or any
  backend file.
