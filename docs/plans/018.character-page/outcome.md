# Feature 018 — Character page · outcome

These are the intended changes to `docs/architecture/` once this feature ships. The
architect applies them at finalization. Entries are grouped by target file. D-n refers to
this folder's `context.md`.

## `docs/architecture/workspace-shell.md`

| Section | Intended change | Reason |
|---|---|---|
| "The character page" → "The composer, and how a session starts here" — the `_TBD:` on the kind switch / setup choice | **Close it, citing US-117.AC-4.** The page composer offers neither the kind switch nor a setup choice. The session it creates has `setup_id` NULL (R2). UC-080's postcondition gives the reasons. The Sessions section's own "Start session" with its Setup select (011 D1) remains the way to start **with** a setup (D1). | The gap-closure round added US-117.AC-4 after the `_TBD:` was written. The question is answered by product. |
| "The character page" | Record the body **as built**, in order: header → name + persona (+ Archive / Restore) → notes grid → setups → configuration → sessions → composer. Two columns hold by construction: the shell grid is nav + main, and the wall exists only in the session screen, so `shell.css` gained nothing (D10). | Records the delivered arrangement and why no layout code was needed. |
| "The character page" — notes | Record that the grid is **`MemoLevelGroup` with an opt-in grid layout** (rect sorting strategy when reorderable) inside the character section's **own** `DndContext`. The sensors and the position-only announcements are shared with the wall through `app/memoDnd.ts`. No second card or group component exists (D8). | Names the mechanism that keeps "same components, different arrangement" true. |
| "The character page" — composer | Record the **composer core**: `ComposerCore` holds the text area, the geometry, the labelled Send, the enormous-paste warning and the send-blocked reason. The stream's `Composer` and the page's `CharacterComposer` are its two hosts (D4). | The doc forbids a second composer. This names the one component both render. |
| "The character page" — draft page | Record the draft page **as built**: the "Draft" badge and marker line; Name + Persona only; the character is created when the Name field loses focus holding non-blank text (persona sent with it); fields read-only while the create is in flight; replace navigation to `/characters/:id`. Name and persona then **save on focus loss**. A blank name is refused client-side. Pending edits are flushed on leaving (D6, D7). | The "persists nothing until something is entered" rule now has a concrete trigger, and the trigger is an interpretation worth stating. |
| "The character page" — configuration | Record the configuration block: model (`Select`, "First enabled model" = unset), system prompt (blur-save, blank = unset) and three tool switches (Default / On / Off). Each shows its resolved value and whether it is set on the character. No language fields (US-061.AC-3). Inline failures (D9). | Realizes UC-048 / US-059's UI, which 017 left without a caller. |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| Stream route table — `POST /api/characters/{character_id}/sessions` row | Body: omitted, `{}`, `{ setup_id? , opening_message? }`. Answers **201 `StartedSession`**: the eight `Session` keys plus `opening_message` (012's `Message`, or null exactly when none was sent). A whitespace-only `opening_message` → 422 and nothing is created. | The route's shape changed. Its response is no longer `Session`. |
| "Starting a session by writing is one route and one transaction" | Record as built: one `with connection.begin():` runs the parent and setup checks, mints the session id, captures the model (017 D1), inserts the session, then inserts the opening message as a current-zone user row with the **same** timestamp. A failure in the message insert leaves no session (D3). | Confirms the design and the rollback behaviour that tests pin. |
| Same bullet / the first-reply `_TBD:` ("whether that first message should also draw an assistant reply") | **Close it: yes, per US-117.AC-3, owed by `021`.** 018 ships the JSON, no-model-call route. `021` composes on the session once it exists, so the route's media type does not change (D2). | Product answers the question, and the plan defers delivery of the reply. |
| "Routers versus services" (service isolation) | Record the **narrow service-import exception**: `services/sessions.py` imports only the transaction-neutral zone insert helper and the message value type from `services/messages.py`. The helper opens no transaction, checks nothing and bumps nothing. 012's `append_message` uses the same helper, so the zone insert exists once (D3). Same reasoning as 015 D11 and 017 D12. | A third instance of the exception. The rule's text should name the pattern rather than list cases. |

## `docs/architecture/frontend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| "Routing inside the `app` entry" — the archive-toggle `_TBD:` | **Close it**: placement is **section-local**. The tree header's "Show archived" covers characters (009 D4), the Setups section's "Show archived setups" covers setups (010), and the Sessions section's "Show archived sessions" covers sessions (011 D5). None is persisted (D11). | Answered piece by piece as 009 / 010 / 011 shipped. Nothing in 018 changes it. |
| "Routing inside the `app` entry" — `/characters/new` | Replace 009's interim note with the draft page as built (D6): no Create button, create on the first committed non-blank name, `replace` navigation to `/characters/<id>`. | 009's outcome said `018` would replace Create. It has. |
| "Routing inside the `app` entry" — "`/characters/:id` also starts sessions" | Record as built: `sessionsApi.ts`'s start-with-message call posts once. The returned session's eight keys are applied to the workspace `SessionsState`. The client **pushes** `/sessions/<id>` (Back returns to the character page). The returned opening message is **not** used to pre-seed the stream, because the session screen re-reads its zone on mount. `startSession` resolves to exactly the eight `Session` keys (D5). | Settles push versus replace and what the client does with the seeded message. |
| "State — MobX 6" / "Where a store's file lives" | Add the page-local composer state (`characterComposerState.ts`) and the configuration block state (`characterConfigState.ts`) as examples of a section owning its own small store, created with `useState` and never shared. | Two more instances of the per-section store pattern. |
| `@dnd-kit` bullet under "Bundle-level constraints" | Note the second `DndContext` (the character page's notes) and the shared `app/memoDnd.ts` (sensors + announcements), so both contexts keep one keyboard path (D8). | `@dnd-kit` now has two mount points, and their configuration is shared rather than duplicated. |

## `docs/architecture/ui-conventions.md`

| Section | Intended change | Reason |
|---|---|---|
| Composer conventions (auto-grow, no handle, labelled Send) | State that the conventions live in **one component**, `ComposerCore`, and hosts add only their own controls through slots (D4). | Makes "one composer" checkable at the file level. |
| "Create and edit are always a `Modal`" — the draft-page exception | Record the exception as built for `/characters/new` (D6). | The exception now has a concrete behaviour. |
| Blur-save / "Page state" | Record that the character page's name and persona now **save on focus loss** (009 D2's explicit Save is retired, D7), with a client-side blank-name refusal and a flush on leaving. | Brings the character page in line with the workspace's blur-save. |
| "Async feedback" | Add worked examples: the page composer's send failure goes to `notifyFailure` (no place of its own, 013 D15). The configuration block's failures render in place and raise no notification (D9). | Two more call-site examples on each side of the boundary. |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Open items — the row for "does the character page's first message draw an assistant reply" (US-117 / UC-080 first reply) | Move it to **owned by `021`** (US-117.AC-3), with 018 shipping the no-reply route (D2). | It is no longer an open design question. |
| Error / route index (if it lists `POST /api/characters/{id}/sessions`) | Note the `StartedSession` response. | Keeps the index in step with `backend-structure.md`. |

## `docs/architecture/domain-rules.md`

| Section | Intended change | Reason |
|---|---|---|
| R11 | One sentence: as built (plan 018), the character page's opening message is inserted as a **current-zone** row through the same helper as the stream's append. It is never settled, so R11's two doors are unchanged. | Shows the invariant holds at the one route not addressed through a session. |

## Forward notes (not architecture changes; for the owning plans)

- **`021`** owes **US-117.AC-3** (UC-080 step 5): the assistant answers the opening
  message. Compose on the session after create-and-seed, or have the session screen start
  a compose when it opens on a just-seeded zone. Whichever is chosen, the create route
  stays JSON. `021` should also decide whether the page composer takes the core's
  `sendBlockedReason` (US-107) once sending there triggers a model call (D4 leaves the prop
  ready).
- **`024`** (embeddings): the opening message is a zone row like any append, so it gets no
  embedding at insert, consistent with "refresh at settle / re-open / edit".
- **Product** (`/product-spec`): FEAT-008 is **partially delivered** by 018 until `021`
  lands US-117.AC-3. FEAT-020's UC-073 / UC-074 / US-096 / US-097 are delivered.

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B1 (the backend spine — `session-stream.md`, `transfer.md`, `backend-structure.md`, `data-model.md`, `domain-rules.md`) and B3 (the frontend layer — `workspace-shell.md`, `frontend-structure.md`, `ui-conventions.md`, `forms-and-lists.md`).
Rejected items: Its "owed by `021`" framing for UC-080's first reply was not written — `021` never took it.
Notes: The design question is closed (yes, and the route stays JSON), but delivery is recorded as defect D-01 against `US-117.AC-3`, pointing at `docs/plans/defects.md`.
