# Fast feature 012 — notes-autosave-toolbar-flags — outcome

Intended documentation changes, applied by the architect at finalization.

## `docs/architecture/frontend-structure.md`

- **Section: Markdown → "One editor wrapper, and its two emit rules".** Add the
  new optional **toolbar actions** prop to the wrapper's prop list: arbitrary
  content rendered as one trailing `RichTextEditor.ControlsGroup` at the right end
  of the toolbar; omitted → toolbar unchanged; not rendered when `readOnly`
  (there is no toolbar). Record that notes use it for their flag controls and that
  the other callers (setup forms, persona) do not. Reason: user request fast/012 —
  the flag icons belong in the "header with markdown helper".

## `docs/architecture/workspace-shell.md`

- **Wherever the note group / note card is described (the note wall's contents,
  the character page's Notes tab, the Settings user-level notes).** Replace the
  description with the single behaviour: header '+' ("New note") beside the
  group title is the only way to open a draft, at every mount; no labelled
  "New note" button; the draft is the first list item and saves on focus leaving
  it (blank → dropped, no request); saved notes save on focus leaving them
  (blank → delete, no confirm); there are no Save/Cancel buttons. The flag
  controls sit at the right end of the note's editor toolbar; the reach line and
  failure text stay under the editor. Note that because the toolbar is inside
  the note's focus-leave boundary, a flag click toggles only the flag and does
  not save the body. Reason: user request fast/012.
- **Character page, Notes tab.** Remove the "opt-in header-add mode with explicit
  Save/Cancel" description recorded from plan 033 (D6); it is superseded by the
  one behaviour above. Record the supersession (033 D6 → fast/012, user decision).

## `docs/architecture/forms-and-lists.md`

- **Confirm convention / blur-save (wherever the note exception is named).**
  Confirm the note rule still holds and now has no exception: notes never have a
  Save button; blank-on-blur deletes without a confirm. If the doc names plan
  033's Save/Cancel draft as an exception to blur-save, remove that exception.
  Reason: user request fast/012.

## `docs/architecture/ui-conventions.md`

- **Icon table.** Remove the "Save new note" (`IconDeviceFloppy`) and "Cancel new
  note" (`IconX`) rows if present (plan 033 step 002). The "New note" (`IconPlus`)
  row now applies at every note mount, not only the character page. Flag icon
  rows unchanged in icon and label; amend their placement to "in the note's
  editor toolbar". Reason: user request fast/012.

## `docs/plans/` supersession record

- `docs/plans/033.character-page-tabs/002.notes-header-add.md` DoD-1, DoD-3..DoD-9
  and `docs/plans/033.character-page-tabs/context.md` D6 are superseded by
  fast/012; `docs/plans/015.memos/007.memo-level-group.md` DoD-4 (flag placement)
  and DoD-11/DoD-14 (labelled "New note" button) likewise. The architect records
  this where those decisions are cited; the plan files themselves stay as
  written.

## `docs/product/`

- No product change intended. The architect should confirm no story or use case
  (e.g. under UC-043, US-053, US-101, US-119) pins an explicit save button for
  notes or a particular placement for the flag controls; if one does, hand back
  to `/product-spec` rather than editing it. (Not verified by the planner.)

## Observations
