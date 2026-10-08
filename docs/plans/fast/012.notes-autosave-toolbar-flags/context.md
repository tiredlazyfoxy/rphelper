# Fast feature 012 — notes-autosave-toolbar-flags — context

Frontend only (`app` entry plus `shared/MarkdownEditor`). No backend, no API, no
schema change.

## The request, as interpreted (user-approved)

User request: "update the design for notes in character (and reuse it anywhere) -
no "save button" empty trimmed => delete. Non-empty => save on focus lost simple
and easy. Force and disable icons to the header with markdown helper".

The user approved this reading:

- **One note behaviour, in the shared `MemoLevelGroup`, at all three mounts.**
  The character page's Notes tab (`CharacterNotesSection`), the session note
  wall's levels (`MemoChainSection`) and Settings' "Your notes"
  (`SettingsScreen`). No per-mount mode: the `headerAdd` opt-in prop is removed.
- **Header '+' everywhere.** The '+' icon button ("New note", `IconPlus`) beside
  the group title — ready state only, disabled while a draft is open — is the one
  way to open a draft. The labelled "New note" button below the list is removed.
- **No Save / Cancel.** The draft (first list item, editor autofocused) saves on
  focus leaving it through the existing `saveNewNote`: trimmed-blank drops the
  draft with no request; otherwise one create. Saved notes keep their existing
  focus-leave `saveNote`: trimmed-blank deletes (no confirm), changed text
  patches the body, unchanged text sends nothing. "Save new note" / "Cancel new
  note" go, and with them `discardNewNote` (its only caller was Cancel).
- **"Header with markdown helper" = the markdown editor's toolbar.** The two flag
  controls of a saved note (disable/enable, force/stop forcing) move out of the
  row under the editor and into the editor's own toolbar, as an extra controls
  group at its end (pushed right). The reach line and the red failure text stay
  under the editor. The draft gets no flag controls (unchanged — 015 D13).
- **Flag clicks no longer save the body.** The toolbar is inside the note's
  focus-leave wrapper, so focus moving from the editor to a flag button stays
  inside the wrapper and does not trigger the body save. Accepted as desired:
  a flag click only toggles its flag. The body still saves when focus later
  leaves the note.

## Contracts this supersedes

Record of supersession (the old plans are `done` and are not edited):

- `docs/plans/033.character-page-tabs/002.notes-header-add.md` — DoD-1 (the
  `discardNewNote` function), DoD-3 (Save/Cancel in the draft), DoD-4 (Cancel),
  DoD-5/DoD-6 (save by the Save button), DoD-7 (no blur-save in the draft),
  DoD-8 (Save/Cancel disabled in flight), DoD-9 (opt-in mode; wall and Settings
  keep the labelled button). DoD-2 (header '+', no labelled button) now holds for
  every mount. DoD-10 (keyboard reorder) still holds.
- `docs/plans/033.character-page-tabs/context.md` **D6** — the opt-in "header
  add" mode with explicit Save/Cancel. Replaced by: one behaviour, header '+',
  blur-save draft.
- `docs/plans/015.memos/007.memo-level-group.md` — DoD-4's placement wording for
  the flag controls (now in the editor toolbar), and DoD-11 / DoD-14 (the
  labelled "New note" button → the header '+').

## Files involved (from the harvest)

- `frontend/src/shared/MarkdownEditor.tsx` — the one markdown editing wrapper
  (`frontend-structure.md` "One editor wrapper"). Props today: `label`, `value`,
  `onChange`, `readOnly?`, `autoFocus?`, `contentMinHeight?`. When not
  `readOnly` it renders `RichTextEditor.Toolbar` with four
  `RichTextEditor.ControlsGroup`s (Bold+Italic, H2+H3, bullet+ordered list,
  Link+Unlink); no slot for extra content. Read-only renders no toolbar.
  Other callers — `SetupModal`, `SetupCreateForm`, `CharacterScreen` (persona) —
  must stay unchanged.
- `frontend/src/app/MemoLevelGroup.tsx` — the shared level group (`observer`).
  Props: `state`, `title`, `headingOrder`, `onRetry`, `reorderable?`,
  `layout?: "list" | "grid"`, `headerAdd?`. Pieces:
  - `onFocusLeave(save)` helper — skips when `relatedTarget` is inside the
    wrapper (`currentTarget`).
  - `NoteCardBody` — a `Box` focus-leave wrapper around `MarkdownEditor`, then a
    `Group` with the two flag `IconButton`s and the reach `Text`, then the
    failure `Text`. Flag labels: "Disable note" / "Enable note"
    (`IconCircleCheck` / `IconCircleOff`); "Force note" / "Stop forcing note"
    (`IconPin`, orange while forced); disabled while a flag write is in flight.
  - Draft: in `headerAdd` mode an editor without blur wrapper plus Save/Cancel
    (`IconDeviceFloppy` / `IconX`); in default mode a blur wrapper → `saveNewNote`.
  - Labelled "New note" `Button` below the list when `!headerAdd`.
  - Header: with `headerAdd`, a `Group` of Title + '+' `IconButton` (ready only).
  - Reorder: `SortableNoteCard` — whole `li` is the drag surface,
    `useSortable({ disabled: editing || isReorderInFlight })`. Unmount →
    `flushMemoLevel`.
- `frontend/src/app/memoLevelState.ts` — `openNewNote`, `setNewNoteText`,
  `saveNewNote` (blank → draft null, no request), `discardNewNote` (to remove),
  `saveNote` (blank → DELETE), `toggleEnabled`, `toggleForced`,
  `flushMemoLevel`, `isBlank`.
- Mounts: `CharacterNotesSection.tsx` (`title="Notes" headingOrder={3}
  layout="list" reorderable headerAdd` — drops `headerAdd`),
  `MemoChainSection.tsx` (`headingOrder={4} reorderable`) and
  `SettingsScreen.tsx` (`title="Your notes" headingOrder={3}`) — the latter two
  need **no** source edit; they inherit the new behaviour.

## Test-harness fact that drives the test churn

Fourteen test files `vi.mock("../../src/shared/MarkdownEditor")` with a stub
rendering `div > label + textarea` and nothing else. Once the flag buttons are
passed through the new toolbar prop, **they vanish from the DOM under any stub
that does not render that prop**. Every stub in a file that renders notes must
render the toolbar-actions prop (inside the stub's root, so it stays inside the
note's focus-leave wrapper). Files with stubs that render no notes may stay as
they are; the test-coder updates a stub only where a note is rendered or a
lookup breaks. `tests/shared/MarkdownEditor.test.tsx` exercises the real editor
and is where the toolbar slot itself is tested.

## Constraints

- Every icon-only action goes through the shared `IconButton`; labels unchanged
  so existing role/name lookups for the flags keep resolving.
- Mantine only (`RichTextEditor.ControlsGroup`, style props). No stylesheet
  change.
- The "never echo" rule of `MarkdownEditor` (`frontend-structure.md`) is
  untouched — the new prop renders content, it does not write the editor.
- TypeScript only; `npm run typecheck` is the gate.
- Product ids cited by the originating plans and still the governing ones:
  UC-043, US-053, US-056, US-101, US-102, US-119.
