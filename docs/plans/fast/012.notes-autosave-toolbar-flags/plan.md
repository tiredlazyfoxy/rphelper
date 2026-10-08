# Fast feature 012 — notes-autosave-toolbar-flags

## Goal

Give every note group (character Notes tab, session note wall, Settings "Your
notes") one behaviour: a header '+' opens a draft, drafts and saved notes save on
focus leaving them with no Save/Cancel buttons (trimmed-blank drops a draft or
deletes a saved note), and a saved note's disable/force flags sit in its markdown
editor's toolbar.

## Source files

- `frontend/src/shared/MarkdownEditor.tsx` — new optional toolbar-actions prop, rendered as a trailing controls group
- `frontend/src/app/MemoLevelGroup.tsx` — header '+' always, no labelled button, blur-save draft, flags passed into the editor toolbar, `headerAdd` removed
- `frontend/src/app/memoLevelState.ts` — remove `discardNewNote`
- `frontend/src/app/CharacterNotesSection.tsx` — stop passing `headerAdd`

## Test files

- `frontend/tests/shared/MarkdownEditor.test.tsx` — real editor; toolbar-actions slot present/absent
- `frontend/tests/app/MemoLevelGroup.test.tsx` — group behaviour: header '+', blur-save draft, toolbar flags, no Save/Cancel
- `frontend/tests/app/MemoLevelGroup.headerAdd.test.tsx` — rewrite for the single behaviour (or fold into `MemoLevelGroup.test.tsx` and delete; test-coder's choice)
- `frontend/tests/app/memoLevelState.discard.test.ts` — delete
- `frontend/tests/app/CharacterNotesSection.test.tsx` — Save-new-note tests become blur tests; stub renders the slot
- `frontend/tests/app/CharacterScreen.test.tsx` — "Save new note" usage becomes blur; stub renders the slot
- `frontend/tests/app/SettingsScreen.test.tsx` — header '+' instead of labelled button; flag lookups via stub slot
- `frontend/tests/app/MemoChainSection.test.tsx` — header '+' instead of labelled button; flag lookups via stub slot
- `frontend/tests/app/SessionScreen.test.tsx` — stub renders the slot; adjust only if a note lookup breaks
- `frontend/tests/app/sessionFirstReply.test.tsx` — stub renders the slot; adjust only if a note lookup breaks
- `frontend/tests/app/searchLanding.test.tsx` — stub renders the slot; adjust only if a note lookup breaks
- `frontend/tests/app/App.test.tsx` — stub renders the slot; adjust only if a note lookup breaks
- `frontend/tests/app/CharacterScreen.export.test.tsx` — stub renders the slot; adjust only if a note lookup breaks

(If one of the "adjust only if" files lives at a different path under
`frontend/tests/`, the test-coder uses its real path — it is the same file. Any
other file with a `MarkdownEditor` stub that renders no note needs no change.)

## Interface intent

**`MarkdownEditor` (shared)** — one new **optional** prop, *toolbar actions*: any
React content. When provided and the editor is not read-only, it renders inside
the editor's toolbar as one extra controls group after the four existing groups,
pushed to the toolbar's right end. When omitted, the toolbar is exactly as today.
When `readOnly`, no toolbar renders (unchanged), so the content does not render
either. No other prop changes; the never-echo rule is untouched.

**`MemoLevelGroup`** — the `headerAdd` prop is **removed**; all other props
unchanged. Behaviour, identical at every mount:

- **Header**: the group's Title with a '+' `IconButton` (`IconPlus`, label
  "New note") beside it, rendered in the ready state only, disabled while a draft
  is open. Calls the existing `openNewNote`.
- **No labelled "New note" button** anywhere in the group.
- **Draft**: the first item of the list, editor autofocused, inside a focus-leave
  wrapper that calls the existing `saveNewNote` when focus leaves it (trimmed
  blank → draft dropped, no request; otherwise one create; on failure the draft
  keeps its text and shows its failure text). No Save/Cancel buttons, no flag
  controls, no toolbar actions passed.
- **Saved note (`NoteCardBody`)**: the focus-leave wrapper around the editor is
  unchanged (`saveNote`: trimmed blank → delete with no confirm; changed → body
  patch; unchanged → nothing). The two flag `IconButton`s — same labels, icons,
  colour and in-flight disabling as today — are passed to the editor as its
  toolbar actions instead of rendering in the row beneath it. The reach line and
  the failure text stay beneath the editor. A flag click calls the existing
  `toggleEnabled` / `toggleForced` only.
- Reorder, layouts, `flushMemoLevel` on unmount — unchanged.
- `IconDeviceFloppy` / `IconX` imports and the labelled `Button` import go if
  nothing else uses them.

**`memoLevelState.ts`** — `discardNewNote` is **removed**. Everything else
unchanged.

**`CharacterNotesSection`** — no longer passes `headerAdd`; otherwise unchanged
(`title="Notes"`, `headingOrder` 3, list layout, reorderable).

**Test stubs** — every `MarkdownEditor` stub in a file that renders notes renders
the toolbar-actions prop inside its own root element (so focus moving from the
textarea to a flag stays inside the note's wrapper, as in the real editor).

## Definition of done

1. **DoD-1** `[test]` Real `MarkdownEditor`: content passed as toolbar actions renders inside the editor's toolbar (a descendant of the toolbar element, after the Bold control in document order). (UC-043)
2. **DoD-2** `[test]` Real `MarkdownEditor`: without toolbar actions the toolbar renders its existing controls and no extra content; with `readOnly` and toolbar actions, neither the toolbar nor the actions render.
3. **DoD-3** `[test]` In each of the three mounts (character Notes section, a `MemoChainSection` level, Settings "Your notes"), a button named "New note" renders in the group header beside the title in the ready state, and there is exactly one "New note" button (no labelled button below the list).
4. **DoD-4** `[test]` Activating "New note" opens an empty draft as the first list item with focus in its editor; "New note" is disabled while the draft is open; the draft shows no flag buttons.
5. **DoD-5** `[test]` No button named "Save new note" or "Cancel new note" renders in any state of any mount.
6. **DoD-6** `[test]` Draft with non-blank text, focus leaving it → exactly one create request for that level; on success the note appears first in the list, the draft closes and "New note" is enabled again. (US-053)
7. **DoD-7** `[test]` Draft empty or whitespace-only, focus leaving it → no request; the draft closes and "New note" is enabled again.
8. **DoD-8** `[test]` A failed draft create keeps the draft open with its typed text and shows the failure text inside the draft item.
9. **DoD-9** `[test]` Saved note: text cleared to whitespace-only, focus leaving it → exactly one delete request for that note and no confirm dialog; the note leaves the list on success. Changed non-blank text → one body patch; unchanged → no request. (US-101)
10. **DoD-10** `[test]` Saved note: "Disable note"/"Enable note" and "Force note"/"Stop forcing note" render inside the note's editor root (in the real editor, inside its toolbar; under stubs, inside the stub's rendered toolbar-actions content), not in a row after the editor; labels follow the flag state as today; both are disabled while a flag write is in flight. (US-119)
11. **DoD-11** `[test]` Editing a saved note's text and then clicking a flag button sends only that flag's patch — no body patch — and the note's edited text is still present; the body is saved when focus later leaves the note.
12. **DoD-12** `[test]` The reach line and the failure text of a saved note render after the editor, outside the toolbar.
13. **DoD-13** `[test]` Notes remain keyboard-reorderable in the character Notes section and on the wall, and a reorder still sends the level's whole order. (US-102)
14. **DoD-14** `[test]` Every existing note test across the listed test files passes after its stub renders the toolbar-actions prop — flag lookups by role and name still resolve.
15. **DoD-15** `[manual/live]` `discardNewNote` no longer exists in `memoLevelState.ts`, `MemoLevelGroup` has no `headerAdd` prop, and no caller passes it — confirmed by `npm run typecheck` passing and a source search.
16. **DoD-16** `[manual/live]` Visual, light and dark colour schemes: the flag icons sit at the right end of each saved note's editor toolbar, aligned with the formatting controls; the orange forced pin and the disabled-note state read clearly; '+' sits beside each group title on the character page, the wall and Settings; the draft saves on clicking elsewhere and a blank draft disappears.
17. **DoD-17** `[manual/live]` `SetupModal`, `SetupCreateForm` and the character persona editor show an unchanged toolbar.
18. **DoD-18** `[manual/live]` `npm run typecheck`, `npm run build` and `npm test` pass from `frontend/`.

## Out of scope

- Any edit to `MemoChainSection.tsx`, `SettingsScreen.tsx`, `NoteWall`, or the other `MarkdownEditor` callers (`SetupModal`, `SetupCreateForm`, `CharacterScreen` persona).
- Flag controls on the draft; a confirm on blank-delete; an undo for deletes.
- Changing what `saveNewNote`, `saveNote`, `toggleEnabled`, `toggleForced` or `flushMemoLevel` do.
- Changing the reach line, the failure text wording, the drag surface or the list/grid layouts.
- Any change to `IconButton`'s props, any stylesheet change, any backend/API change.
