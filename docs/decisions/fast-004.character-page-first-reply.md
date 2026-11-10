# Decisions — fast-004.character-page-first-reply
**Stage:** 006.repair · **Feature:** fast/004.character-page-first-reply

The assistant's first reply to a session started from the character page (closes
defect D-01). The contracts are `session-stream.md` "It is character-addressed,
and it creates nothing settled", `frontend-structure.md` "Routing inside the
`app` entry" and `workspace-shell.md`'s character page. Written at finalization
(2026-11-09). The plan's D1–D5 are `DEC-F004-1` .. `-5`, in that order.

### DEC-F004-1 — The session screen composes after arrival; the create route stays JSON
- **Status:** accepted
- **Stage:** 006.repair · **Feature:** fast/004.character-page-first-reply · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Where is the first reply drawn — by the create-and-seed route, or by the session screen once the session exists?
- **Decision:** By the session screen: one textless `POST /api/sessions/{id}/zone/compose` with body `{}` on arrival from the character page. The create route stays JSON and makes no model call (018 D2). Nothing in `backend/` changes.
- **Reason:** The textless compose already does the job; turning the create route into a streaming response would change a delivered contract and add a second streaming harness for one call site.
- **Rejected:** Making `POST /api/characters/{id}/sessions` stream the reply.
- **Lands in:** `frontend/src/app/streamState.ts`; `frontend/src/app/SessionStream.tsx`
- **Cites:** `session-stream.md` § create-and-seed; `llm-and-streaming.md` § the frame table (the textless compose)

### DEC-F004-2 — The trigger is a one-shot router-state marker, consumed on arrival
- **Status:** accepted
- **Stage:** 006.repair · **Feature:** fast/004.character-page-first-reply · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** How does the session screen know a session was just seeded from the character page?
- **Decision:** `CharacterComposer` keeps its push to `/sessions/<id>` and adds a router `location.state` marker, defined once in `app/firstReply.ts`. `SessionScreen`, the only router reader, captures the marker once for the session id it opened on, passes a boolean prop to `SessionStream`, and immediately consumes the marker by **replacing** the history entry with the same path and search and a null state. `SessionStream` stays router-free (029 decision 9).
- **Reason:** A reload, Back/Forward or re-render then never fires again. Capturing once per session id keeps the intent alive across the re-render that clearing the history causes. The replace leaves the character-page entry beneath intact, so Back still returns there (018 D5).
- **Rejected:** A zone-derived trigger — composing whenever a session opens on a zone ending with an unanswered user row. That would change behaviour for every reopened session in that state, which is a legitimate resting state (after a stop, or a send the server refused).
- **Lands in:** `frontend/src/app/firstReply.ts`; `frontend/src/app/CharacterComposer.tsx`; `frontend/src/app/SessionScreen.tsx`
- **Cites:** `frontend-structure.md` § Routing inside the `app` entry

### DEC-F004-3 — One textless compose through the existing path, at most once per stream state
- **Status:** accepted
- **Stage:** 006.repair · **Feature:** fast/004.character-page-first-reply · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** When exactly does the first-reply compose start, and how is a double start prevented?
- **Decision:** After the stream's load resolves ready, `composeFirstReply` starts the compose only when all hold: the intent is set; the stream's own signal is not aborted; the zone's last non-tool row is the roleplayer's; nothing is streaming or busy. It runs through the same private compose path as a discussion compose, so the reply renders as the ordinary live reply, Stop is available, failure goes through `notifyFailure` and the zone is re-read at the end. A once-flag per `StreamState` makes it fire at most once.
- **Reason:** One compose path means one frame consumer and one failure channel. The once-flag defeats StrictMode's double effect: the first mount's load is aborted before it resolves and the second is guarded.
- **Lands in:** `frontend/src/app/streamState.ts`; `frontend/src/app/SessionStream.tsx`

### DEC-F004-4 — Reload, or arriving mid-compose: no special handling
- **Status:** accepted
- **Stage:** 006.repair · **Feature:** fast/004.character-page-first-reply · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** What happens when the roleplayer reloads or leaves while the first reply streams?
- **Decision:** It behaves like any stop. The fetch aborts, the server persists the partial text as an ordinary current-zone assistant row, and on return the marker is gone, so nothing re-fires. Regenerate is the way to redraw.
- **Reason:** There is no in-flight registry to reattach to, and `llm-and-streaming.md` rejects one by design.
- **Lands in:** `frontend/src/app/SessionScreen.tsx`
- **Cites:** `llm-and-streaming.md` § Stopping, and what a stop is not

### DEC-F004-5 — The page composer does not take a send-blocked reason
- **Status:** accepted
- **Stage:** 006.repair · **Feature:** fast/004.character-page-first-reply · **Step:** —
- **Date:** 2026-10-07 · **Decided by:** planner
- **Question:** Should the character page's composer refuse to send when no usable model is configured, as the session composer does?
- **Decision:** No. `CharacterComposer` does not take `sendBlockedReason`; 018 D4's unused prop stays unused. A refused auto-compose (for example no model enabled) surfaces on the session screen twice: through `notifyFailure`, and, once config loads, through the session composer's own blocked reason. The opening message is a persisted zone row either way (R10).
- **Reason:** Creating the session makes no model call and needs no model, and the character page has no models list to compute a reason from; loading one there is out of scope. The asymmetry with the session composer is deliberate.
- **Lands in:** `frontend/src/app/CharacterComposer.tsx`
- **Cites:** `workspace-shell.md` § the character page's composer; `domain-rules.md` R10
