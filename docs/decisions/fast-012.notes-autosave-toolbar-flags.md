# Decisions — fast-012.notes-autosave-toolbar-flags
**Stage:** — · **Feature:** fast/012.notes-autosave-toolbar-flags

One note behaviour at every mount: the note group's header '+' is the only way to
open a draft, drafts and saved notes save on focus leave, there is no Save/Cancel,
and a note's two flag controls move into its markdown editor's toolbar. The
contracts are `workspace-shell.md` "One note behaviour at every mount" and the
wall's contents, `ui-conventions.md`'s icon table (note flags, New note) and
`frontend-structure.md` "An optional trailing toolbar group".

### DEC-F012-1 — A flag click toggles only the flag; it does not save the body
- **Status:** accepted
- **Stage:** — · **Feature:** fast/012.notes-autosave-toolbar-flags · **Step:** —
- **Date:** 2026-10-08 · **Decided by:** user
- **Question:** With the flags inside the editor's toolbar, does clicking one count as leaving the note and so save the body too?
- **Decision:** No. The toolbar is inside the note's focus-leave wrapper, and the focus-leave handler skips when the `relatedTarget` is inside the wrapper's `currentTarget`, so moving focus to a flag is not a leave. The click sends the flag change alone.
- **Reason:** User accepted the planner's reading: a flag is a separate one-field write, and the apply-a-row rule already handles a flag response racing a body save.
- **Lands in:** `frontend/src/app/MemoLevelGroup.tsx`
- **Cites:** `workspace-shell.md` "One note behaviour at every mount"; `forms-and-lists.md` the apply-a-row rule (015 D5)

### DEC-F012-2 — One note behaviour supersedes plan 033's opt-in header-add mode
- **Status:** accepted
- **Stage:** — · **Feature:** fast/012.notes-autosave-toolbar-flags · **Step:** —
- **Date:** 2026-10-08 · **Decided by:** user
- **Question:** Plan 033 gave the character page's notes an opt-in header-add mode with explicit Save/Cancel, and plan 015 placed the flags beside the card and added a labelled "New note" button. Which survives?
- **Decision:** Neither. Every mount follows one behaviour (DEC-F012-4).
- **Supersedes (named in text; no DEC entry exists for any of them to flip):** plan 033 D6 (the opt-in header-add mode with Save/Cancel); 033 step 002 DoD-1 and DoD-3 .. DoD-9 (DoD-2 now holds for every mount; DoD-10 still holds); plan 015 step 007 DoD-4 (flag placement), DoD-11 and DoD-14 (the labelled "New note" button).
- **Reason:** User decision: a note behaves the same at every mount, and the blur-save rule already governs the character page's other content.
- **Lands in:** `frontend/src/app/MemoLevelGroup.tsx`, `frontend/src/app/memoLevelState.ts`, `frontend/src/app/CharacterNotesSection.tsx`
- **Cites:** `workspace-shell.md` "One note behaviour at every mount"; `forms-and-lists.md` "Deliberately NOT confirmed" (emptied in-place editor)

### DEC-F012-3 — The shared markdown editor takes one optional trailing toolbar group
- **Status:** accepted
- **Stage:** — · **Feature:** fast/012.notes-autosave-toolbar-flags · **Step:** —
- **Date:** 2026-10-08 · **Decided by:** planner
- **Question:** How do a note's flag controls get into the editor's toolbar without forking the shared editor?
- **Decision:** `MarkdownEditor` gains an optional `toolbarActions` parameter, rendered as one trailing `RichTextEditor.ControlsGroup` at the right end of the toolbar and not rendered at all when the editor is read-only. SetupModal, SetupCreateForm and the CharacterScreen persona editor do not pass it.
- **Reason:** One optional slot keeps the editor single-sourced ("one editor wrapper"); it never writes editor content, so the two emit rules (`onChange` from `onUpdate` only, `emitUpdate: false` on programmatic writes) are untouched.
- **Lands in:** `frontend/src/shared/MarkdownEditor.tsx`
- **Cites:** `frontend-structure.md` "One editor wrapper" / "An optional trailing toolbar group"

### DEC-F012-4 — The note group's mechanics: header '+', focus-leave drafts, no Save/Cancel
- **Status:** accepted
- **Stage:** — · **Feature:** fast/012.notes-autosave-toolbar-flags · **Step:** —
- **Date:** 2026-10-08 · **Decided by:** user
- **Question:** What exactly does the single note behaviour consist of in the group component and its state module?
- **Decision:** The `headerAdd` parameter is removed. The header '+' `IconButton` (`IconPlus`, accessible name "New note") shows in the ready state only and is disabled while a draft is open. The labelled "New note" button below the list is removed. Save/Cancel (`IconDeviceFloppy` / `IconX`) and `discardNewNote` are removed. The draft is the first item and saves through `saveNewNote` on focus leave; a blank draft sends no request and is dropped. Saved notes keep `saveNote` (blank → `DELETE`, no confirm). The draft carries no flags (015 D13). The mounts CharacterNotesSection (which drops `headerAdd`), MemoChainSection and SettingsScreen inherit the behaviour unchanged.
- **Reason:** User decision (DEC-F012-2). The header '+' is the one entry point so a draft can never be opened twice; blank-drops-the-draft mirrors blank-deletes-the-note, so the editor behaves one way for new and saved notes.
- **Lands in:** `frontend/src/app/MemoLevelGroup.tsx`, `frontend/src/app/memoLevelState.ts`, `frontend/src/app/CharacterNotesSection.tsx`
- **Cites:** `workspace-shell.md` "One note behaviour at every mount"; `ui-conventions.md` `IconPlus` note
