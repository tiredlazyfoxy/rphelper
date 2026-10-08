# fast/004.character-page-first-reply — outcome

Intended doc changes, for the architect to apply at finalization.

## docs/architecture/session-stream.md

- **Section:** "It is character-addressed, and it creates nothing settled". The paragraph
  "The opening message draws no assistant reply, and that is defect D-01".
  **Change:** Replace the defect paragraph with the as-built record:
  - The route stays JSON and makes no model call (018 D2, unchanged).
  - The reply is drawn by the **session screen**, which issues one textless
    `POST /api/sessions/{id}/zone/compose` (`{}`) on arrival from the character page.
  - That compose emits no `accepted` frame and is otherwise an ordinary compose.
  - Remove "Nothing in this doc should be read as describing a reply that exists".

  Point to `frontend-structure.md` for the trigger.
  **Reason:** D-01 closed by fast/004 (US-117.AC-3, UC-080 step 5).

## docs/architecture/frontend-structure.md

- **Section:** "Routing inside the `app` entry". The "`/characters/:id` also starts
  sessions" as-built list.
  **Change:**
  - Amend the push bullet: the push carries a one-shot router-state marker (defined once
    in `app/firstReply.ts`).
  - Add a bullet on what happens at arrival. `SessionScreen`, the only router reader,
    captures the marker once per session id and immediately clears it by **replacing**
    the session entry (same path and search, null state). It passes a boolean to
    `SessionStream`, which stays router-free (029 decision 9).
  - After the load resolves ready, `SessionStream` calls `streamState.ts`'s
    `composeFirstReply`. That starts at most one textless compose per `StreamState`, and
    only when the zone's last non-tool row is the roleplayer's.

  Record the rejected alternative, a zone-derived trigger for any session: it would
  compose on every reopened session with an unanswered row.
  **Reason:** As-built record of the trigger; the rejection is recorded so it is not
  re-litigated.

## docs/architecture/workspace-shell.md

- **Section:** The character page, "The composer, and how a session starts here".
  **Change:**
  - State that a send from the page now ends with the assistant answering on the session
    screen, with no second send.
  - Record the decision that the **page composer does not take `sendBlockedReason`**:
    creating the session needs no model, and the page has no models list. A refused
    auto-compose surfaces on the session screen through `notifyFailure` and the session
    composer's own blocked reason, and the opening message is kept (R10).

  This closes 018 D4's open prop as a deliberate asymmetry with the session composer.
  **Reason:** Closes the brief's US-107 question; names the asymmetry as deliberate.
- **Section:** The stream / stop control (wherever arrival on a session is described).
  **Change:** One sentence: reloading or leaving while the first reply is streaming
  behaves like any stop. The partial text persists as a candidate, nothing re-fires on
  return (the marker is consumed), and Regenerate is the way to redraw.
  **Reason:** Records the accepted answer to "reload or arrive mid-compose".

## docs/architecture/llm-and-streaming.md

- **Section:** The frame table, `accepted` row (or the textless-compose note beside it).
  **Change:** Name the second caller of the textless compose, the character page's first
  reply, alongside the retry/regenerate.
  **Reason:** The textless compose is no longer retry-only.

## docs/architecture/quick-reference.md

- **Section:** The defects block.
  **Change:** Mark D-01 closed by `fast/004.character-page-first-reply`.
  **Reason:** Defect repaired.

## Flags for other owners (not architecture changes)

- **`/product-spec`:** `docs/product/features.md` FEAT-008's `**Remaining:**` line should
  drop US-117.AC-3 / UC-080 step 5 once this plan is `done`. `docs/plans/defects.md` itself
  needs no edit: by its own rule a defect is closed by the plan that fixes it, and this
  plan's `status.md` is that record.

## Observations

