# Feature 016 — Note wall · outcome

Intended changes to `docs/architecture/` once 016 ships, for `/architect` to apply at
finalization. Grouped by target file. Decision ids (Dn) refer to this feature's
`context.md`. Requirements are cited, not restated.

**Sequencing note for the architect:** 015's `outcome.md` records the `sort_key`
allocation as `COALESCE(MAX(sort_key), -1) + 1` (015 D4). **016 D5 supersedes it.** If
the two outcomes are applied together, record only 016's rule. If 015's has already been
applied, replace it.

## `workspace-shell.md`

- **"The wall has two modes"** — record the as-built placement. The wall belongs to the
  **session screen's ready render**, not to the shell. The shell grid stays two columns
  (`nav`, `main`). Inside `main` the session screen's own grid is the "centre grid": one
  column (`minmax(0,1fr)`) with the wall floating, `minmax(0,1fr) auto` with it pinned
  (D1). US-095 therefore holds by construction: no route or state other than a loaded
  session renders a wall. *Reason:* the doc's "a real column of the centre grid" is
  realised one level down, and a reader looking for the wall in `WorkspaceShell` will not
  find it.
- **"The wall has two modes"** — record the state rules (D2):
  - opening never writes the record;
  - the pin toggle writes it;
  - **unpinning leaves the wall visible as a floating flyout**;
  - **dismissing a pinned wall also unpins it** (UC-072 steps 4–5);
  - **below 820px a pinned wall is shown floating, only when opened, and dismissing it
    there only closes it**, so the stored pin survives and widening restores the column
    (planner interpretation, D2);
  - the open flag resets per session.

  *Reason:* these are the decisions a reimplementation would otherwise re-derive
  differently.
- **"The wall has two modes"** — record that the wall is **mounted while closed** (D3).
  It is slid out and carries `inert` plus `aria-hidden="true"`. It is never remounted by
  a mode change, so the chain loads once per session and an unsaved edit survives a
  close. The `hidden` attribute is deliberately not used, because it would kill the slide
  animation. *Reason:* the obvious conditional render reloads the chain on every open.
- **"The wall has two modes"** — record that the narrow revert is decided in TypeScript
  from `NARROW_VIEWPORT_QUERY` (the exact string `shell.css`'s media query uses), not by a
  second CSS media query. CSS alone cannot express "a pinned wall at narrow width shows
  only when opened" (D11).
- **"The wall's contents"** — record:
  - the wall's landmark is a complementary named **"Note wall"**, holding 015's region
    "Notes" (D4);
  - a **new note opens at the top of its level with focus in its body and stays first**
    once saved (D5, D9; closes 015's deferral of the focus);
  - the reorder failure line "Could not reorder the notes." is per level.
- **"The wall's contents"** — the **answer to 015 `outcome.md`'s open question**: the
  wall's chain state is **separate** from the character page's level state. They are
  never on screen together (US-095), and each loads on mount (D4).
- **"`@dnd-kit` is finally used"** — record the as-built mechanics (D8):
  - one `DndContext` over the chain, one `SortableContext` per level;
  - `PointerSensor` with a 6px distance constraint, and `KeyboardSensor` with sortable
    keyboard coordinates;
  - the whole card is the drag surface, focusable, keeping role `listitem`, named "Note
    <n> of <total>";
  - keyboard activation only when the card element itself is the event target, so keys
    typed in the editor never start a drag;
  - not draggable while its editor has focus, while the level's reorder is in flight, or
    as the unsaved new note;
  - cross-level refusal in a pure decision function plus the drop effect;
  - announcements name positions, never ids;
  - reorder is opt-in on the shared group (`reorderable`), so the character page does
    not reorder until `018` turns it on.
- **"`@dnd-kit` is finally used"** — **a tension to record or resolve.** The doc says "a
  text selection inside [a card] must not start a drag". Under the user's decision U2
  (whole-card drag surface with a distance constraint), that holds once the card's editor
  has focus. A press-and-move that **begins on the text of an unfocused card is a drag**
  (D8). The architect either records this as the accepted reading, or tightens the rule
  (for example, pointer drags never start inside the text body), which would be a change
  to U2 and needs the user.

## `ui-conventions.md`

- **"Mutations are never optimistic"** — record the **one exception: note reordering**
  (D7, user decision U1). On drop the level shows the new order at once. On failure it
  reverts to the pre-drop order, applied to the level as it then is (a note created
  meanwhile stays first, a note deleted meanwhile stays gone), with an inline level
  failure. Further drags in that level are disabled while the request is in flight.
  **Reason, the user's:** a dropped card that snaps back until the server answers reads
  as broken. *Why it does not erode the rule:* the request carries the whole level's
  order, the server either applies it or refuses it outright, and the revert is total.
  There is no partial state to reconcile.
- **Icon table, "Open the note wall"** — the `_TBD:` is **closed provisionally** by
  `IconNotes`, label "Open notes", present only while the wall is not visible (D10). The
  architect confirms or replaces it. The "Memos / the note wall" row's `_TBD:` can take
  the same glyph.
- **Icon table, "Pin / unpin the wall"** — as built: `IconPin`, labels "Pin notes" /
  "Unpin notes", active state = the `IconButton` colour while pinned. **"Dismiss the
  wall"**: `IconX`, "Close notes".
- **The pin-glyph `_TBD:`** (wall pin vs note forced) — **still open**. 016 ships both on
  `IconPin` as the table says. Not resolved here (D10).
- **"Accessibility floor"** — record that the keyboard reorder path is built (D8). Also
  an inconsistency to resolve: the floor says "the note's flag icons are hover-revealed".
  As built by 015 and kept by 016, they are **always shown**, not hover-revealed. The
  architect either records always-shown as the convention or keeps hover-reveal as a
  future refinement.

## `data-model.md`

- **"### `memos`" — `sort_key`** — record (D5, D6):
  - **allocation**: `COALESCE(MIN(sort_key), 1) - 1` over the owner's notes at the same
    `(user_id, scope, scope_id)`, inside the create transaction, so a new note lists
    first;
  - `sort_key` is a **signed** integer (first note 0, then -1, -2, …);
  - the **reorder rewrites one level to 0..n-1** in one transaction;
  - lists and the chain order by `sort_key, id`;
  - **no unique constraint**, still, because the rewrite passes through duplicates
    mid-transaction;
  - **a reorder does not move `updated_at`**: order is arrangement, not content.

  *Reason:* supersedes 015 D4's `MAX + 1` rule; user decision U3.

## `backend-structure.md`

- **The memos route surface** — add `PUT /api/memos/order`: body
  `{ scope, scope_id?, memo_ids: [string] }` with `scope_id` rules as on create; 200
  `{ memos: [Memo…] }` in the given order with `sort_key` 0..n-1; one request is one
  level, so a cross-level move is inexpressible (US-103.AC-2). It lives in
  `routers/memos.py`, declared before the `{memo_id}` handlers. `main.py` is unchanged.
  *Reason:* new route.
- **"The per-code status record"** — add **`memo_order_mismatch` → 409**, empty `detail`
  (it never lists the mismatched ids, R5). It is raised when `memo_ids` is not exactly the
  caller's notes at that level (missing, extra, foreign, nobody's, or duplicated): the
  client's view is stale. A missing or foreign target level reuses that level's 404 code.
  *Reason:* new code.
- **Create allocation** — note the changed rule (see `data-model.md` above) where 015's
  outcome put the memo create contract.

## `frontend-structure.md`

- **"Bundle-level constraints" — the `@dnd-kit` bullet** — record as built: the packages
  are `@dnd-kit/core`, `@dnd-kit/sortable` and `@dnd-kit/utilities`; the one use is the
  wall's chain (D8). Keep "nothing else may use it".
- **"The two stylesheets"** — `shell.css` now also holds the **session screen's
  stream/wall layout** (`.app-session`, `.app-session.wall-pinned`, `.app-stream`,
  `.app-wall`, `.app-wall.wall-open`, `.app-session.wall-pinned .app-wall`): still
  workspace layout only, colourless, no new media query. The wall's background and shadow
  are Mantine's (`Paper`) (D11). *Reason:* the table says "the three-column grid … only".
- **"Routing inside the `app` entry"** — `/sessions/:id` renders tree | stream | wall
  where the wall is the session screen's (D1). `App` passes its layout `storage` through
  `SessionRoute` to `SessionScreen`, the second reader of the layout record after
  `WorkspaceShell` (D2).
- **"The API client"** — the shared client gained `apiPut` (D12), with the same decode
  and error mapping as the other verbs.
- **"Markdown"** — `shared/MarkdownEditor` gained an optional `autoFocus` (D9).
- **"Where a store's file lives"** — `app/noteWallState.ts` (the wall's data class plus
  its free functions) beside `shellState.ts`, and `app/memoReorder.ts` (pure drop
  decision plus its effect) beside the memo modules.

## `quick-reference.md`

- **Error codes** — add `memo_order_mismatch` (409).
- **Paths / invariants** — add `PUT /api/memos/order`. Record that the wall lives in
  `SessionScreen` and that `shell.css` has six more selectors.

## Product flags — for `/product-spec`, not the architect

- **A new note is first in its level** (user decision U3, D5). A note created and then
  forced enters the system prompt **ahead** of its level's older forced notes until the
  roleplayer reorders it (US-102.AC-1's arranged order starts with the newest). Raised so
  the product layer can state the intended default position of a new note, which no
  `US-###.AC-#` currently does.
- **Dismissing a pinned wall at narrow width only closes it** (planner interpretation of
  UC-072 step 4 against the 820px revert, D2). If the product intends "dismiss always
  unpins", this needs a criterion.
- **US-102.AC-1 / US-103.AC-1** remain undelivered until `020` assembles forced notes in
  level order then `sort_key, id`. 016 delivers only the persisted order and the level
  order on the wall.

## Observations

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B1 (the backend spine — `session-stream.md`, `transfer.md`, `backend-structure.md`, `data-model.md`, `domain-rules.md`) and B3 (the frontend layer — `workspace-shell.md`, `frontend-structure.md`, `ui-conventions.md`, `forms-and-lists.md`).
Rejected items: none
Notes: Its `sort_key` rule supersedes 015's and is the only one written — 016 D5/D6 supersedes 015 D4, so this plan's rule is the one of record. Both product flags are discharged: the new-note-first rule is `US-102.AC-2`, and the narrow-width dismissal is `US-094.AC-3` / `US-094.AC-4`. The note-card drag tension and the always-shown flag icons were settled by the user (accept as built; always-shown becomes the convention), and the pin-glyph collision is closed as accepted and named.
