# fast/004.character-page-first-reply — plan

Read `context.md` first. Its Decisions D1–D6 are binding.

## Goal

When the roleplayer sends the first message from a character's page, the session screen
they land on automatically starts one textless compose. The assistant answers that
opening message like any other discussion message, with no second send (US-117.AC-3,
UC-080 step 5; closes D-01). This is frontend only, and the create route stays JSON.

## Source files

- `frontend/src/app/firstReply.ts`: **new.** The one definition of the router-state marker
  that means "just seeded from the character page". It has a constructor and a reader, so
  the writer and the reader cannot drift.
- `frontend/src/app/CharacterComposer.tsx`: attaches the marker to the existing push to
  `/sessions/<id>`.
- `frontend/src/app/SessionScreen.tsx`: reads the marker once per session id, clears it
  from history with a replace, and passes the intent to `SessionStream` as a prop.
- `frontend/src/app/SessionStream.tsx`: accepts the intent prop. After its load resolves
  ready, it starts the first-reply compose with its own abort signal.
- `frontend/src/app/streamState.ts`: the new exported first-reply compose, plus its
  once-per-`StreamState` guard.

Read-only reference (not edited): `sessionsApi.ts`, `characterComposerState.ts`,
`streamApi.ts`, `sessionConfigState.ts`, `ComposerCore`/`Composer`.

## Test files

- `frontend/tests/app/streamFirstReply.test.ts`: store-level tests of the first-reply
  compose against a faked fetch.
- `frontend/tests/app/sessionFirstReply.test.tsx`: component and router tests. They cover
  the page composer's navigation marker, and `SessionScreen`/`SessionStream` arriving with
  and without the marker, including under StrictMode.

## Interface intent

- **First-reply marker (`firstReply.ts`).**
  - A function that produces the router `location.state` value marking a session as just
    seeded from the character page, for example `{ firstReply: true }`.
  - A predicate that takes an arbitrary `location.state` (unknown) and answers whether it
    carries that marker. It returns false for null, undefined, non-objects and any other
    shape.
- **`CharacterComposer`.** Its `onStarted` navigation stays a push to `/sessions/<id>` (id
  used as received). It now passes the marker as navigation state. Nothing else on the
  page changes, and the page composer still renders without `sendBlockedReason` (D5).
- **`SessionScreen`.**
  - On opening a session id, it decides once whether the arrival carried the marker and
    holds that boolean for the lifetime of that session id's view.
  - If the marker was present, it immediately replaces the current history entry with the
    same pathname and search params (so `?entry=` and `?notes=open` survive) and with no
    state.
  - It passes the held boolean to `SessionStream` as a new optional prop (for example
    `firstReply`). Absent means false.
- **`SessionStream`.**
  - Gains the optional boolean prop.
  - In the same effect that loads the stream, once `loadStream` has resolved and the state
    is ready, if the prop is true and its signal is not aborted, it calls the store's
    first-reply compose with that signal.
  - It uses no router hook.
- **`composeFirstReply` (`streamState.ts`, exported).**
  - Inputs: a `StreamState` and an `AbortSignal`.
  - It starts one textless compose (the same path `runCompose(state, undefined, signal)`
    takes; no text, request body `{}`). It starts only when all of these hold:
    - the state is ready;
    - it is not streaming or busy;
    - the zone's last non-tool row has role `"user"`;
    - the signal is not aborted;
    - no first-reply compose has been started on this `StreamState` before.
  - When it does not start, it is a no-op and makes no request.
  - Like `runCompose`, it never rejects. Failure is reported through `notifyFailure`, and
    the zone is re-read at the end.
  - The once-flag lives on the `StreamState` instance, so a fresh `StreamState` (a
    different session) is unaffected.

## Definition of done

Store level (`streamFirstReply.test.ts`):

- **DoD-1 [test]**: On a ready `StreamState` whose zone holds only one `role: "user"` row,
  `composeFirstReply` issues exactly one `POST /api/sessions/<id>/zone/compose` with JSON
  body `{}`. The streamed `token` text appears as the live reply while streaming. After
  `done`, the zone is re-read and holds the assistant row.
- **DoD-2 [test]**: Calling `composeFirstReply` a second time on the same `StreamState`
  issues no further compose request, both while the first is streaming and after it has
  finished.
- **DoD-3 [test]**: When the zone's last non-tool row is `role: "assistant"`,
  `composeFirstReply` issues no compose request. Trailing `role: "tool"` rows after a user
  row do not block it, because the last *non-tool* row decides.
- **DoD-4 [test]**: An already-aborted signal causes no compose request.
- **DoD-5 [test]**: A compose refused by the server (non-2xx with an error body, for
  example 409 `no_model_enabled`) does not reject. It surfaces through the same failure
  notification path a discussion compose uses. The state ends not streaming, and the
  user's opening row is still in the zone.

Component and router level (`sessionFirstReply.test.tsx`):

- **DoD-6 [test]**: Sending on the character page's composer navigates (push) to
  `/sessions/<id>` with `location.state` carrying the first-reply marker, as recognised by
  the marker predicate.
- **DoD-7 [test]**: Mounting the session route with the marker in `location.state`, on a
  zone ending in the user's row, issues exactly one compose request with body `{}`. The
  streamed tokens render on screen, and the Stop control is shown while it streams.
- **DoD-8 [test]**: Mounting the session route without the marker, on the same zone,
  issues no compose request.
- **DoD-9 [test]**: After arrival with the marker:
  - the current location's state no longer carries the marker;
  - pathname and search params are unchanged;
  - the history length did not grow, so it was a replace.

  A subsequent re-render, or a remount of the session route at that cleared location,
  issues no further compose request.
- **DoD-10 [test]**: Under `<React.StrictMode>`, arrival with the marker yields exactly one
  compose request.
- **DoD-11 [test]**: Arrival with the marker on a zone whose last non-tool row is the
  assistant's issues no compose request.
- **DoD-12 [test]**: The search params present on arrival (for example `?notes=open`)
  survive the marker clearing.

Gates:

- **DoD-13 [test]**: `npm run typecheck` and the full `npm test` suite pass, including the
  existing `CharacterComposer`, `SessionScreen`, `SessionStream`, `streamCompose` and
  `streamRegenerate` tests unchanged (verifier gate).

Live:

- **DoD-14 [manual/live]**: Against a running instance with an enabled model:
  - writing on a character page lands on the new session;
  - the assistant's reply streams in without a second send;
  - Back returns to the character page;
  - reloading after the reply finished does not compose again.
- **DoD-15 [manual/live]**: Reloading while the first reply is still streaming leaves a
  persisted partial assistant row. No new compose starts, and Regenerate is offered.
- **DoD-16 [manual/live]**: With no model enabled:
  - sending on the character page still creates the session;
  - on arrival the refusal surfaces as a failure notification, and the session composer
    shows its blocked reason;
  - the opening message is intact.

## Out of scope

- Any backend change, including what `POST /api/characters/{id}/sessions` creates, its
  media type, and the compose route or loop.
- Turning the create route into a streaming response (rejected, D1).
- Composing automatically for any session opened without the marker, including a reopened
  zone ending in an unanswered user row (D2).
- `sendBlockedReason` or a models list on the character page (D5).
- Reattaching to, or showing, an in-flight compose after reload. No registry (D4).
- Pre-seeding the stream with the returned opening message (018 D5 keeps the re-read).
- The note wall, the configuration chain, and everything else on the character page.
- Editing `docs/architecture/` or `docs/plans/defects.md` (finalization, via
  `outcome.md`).
