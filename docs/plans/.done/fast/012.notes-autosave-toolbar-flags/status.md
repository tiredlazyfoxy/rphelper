# Fast feature 012 — notes-autosave-toolbar-flags

| Status  | Verifier | Date |
|---------|----------|------|
| done    | PASS     | 2026-10-08 |

## Files Changed

- `frontend/src/shared/MarkdownEditor.tsx` — renders `toolbarActions` as a trailing `ml="auto"` controls group in the toolbar
- `frontend/src/app/MemoLevelGroup.tsx` — header '+' always, blur-save draft only, flags passed as editor toolbar actions, shim and Save/Cancel/labelled button removed
- `frontend/src/app/memoLevelState.ts` — `discardNewNote` removed (skeleton)
- `frontend/src/app/CharacterNotesSection.tsx` — no longer passes `headerAdd` (skeleton)

## Skeleton

### Frozen interface (2026-10-08)
- `frontend/src/shared/MarkdownEditor.tsx` — `export type MarkdownEditorProps = { label: string; value: string; onChange: (markdown: string) => void; readOnly?: boolean; autoFocus?: boolean; contentMinHeight?: number; toolbarActions?: React.ReactNode }` — changed (added optional `toolbarActions?: React.ReactNode`). `MarkdownEditor(props: MarkdownEditorProps): React.JSX.Element` signature unchanged; the body does not render `toolbarActions` yet (coder's job).
- `frontend/src/app/MemoLevelGroup.tsx` — `export type MemoLevelGroupProps = { state: MemoLevelState; title: string; headingOrder: TitleOrder; onRetry: () => void; reorderable?: boolean; layout?: MemoLevelLayout }` — changed (was the same plus `headerAdd?: boolean`). Compile shim, to be removed by the coder: a local `const headerAdd: boolean = false;` in the component body keeps the old branches compiling, so for now all three mounts use the old default (labelled-button) behaviour. The old header-add draft's Cancel `onClick` now throws `Error("Not implemented: fast 012 removes Cancel new note")`, and that branch can't run while the shim is false. The `discardNewNote` import was removed.
- `frontend/src/app/memoLevelState.ts` — `discardNewNote(state: MemoLevelState): void` — removed.
- Caller-compile edits: `frontend/src/app/CharacterNotesSection.tsx` stopped passing `headerAdd` (this file is in Source files). No edits outside Source files.
- Typecheck: `npm run typecheck` is clean for `src/`. Two expected test-file errors remain for the test-coder: `tests/app/MemoLevelGroup.headerAdd.test.tsx(215)` passes the removed `headerAdd` prop, and `tests/app/memoLevelState.discard.test.ts(12)` imports the removed `discardNewNote`.

## Tests

### Tests (2026-10-08)
- `frontend/tests/shared/MarkdownEditor.test.tsx` — covers DoD-1, DoD-2 — real editor: toolbar actions render inside `.mantine-RichTextEditor-toolbar` after Bold and every built-in control, outside the four built-in groups; omitted → exactly four controls groups and nothing else; `readOnly` (or flipping to it) → no toolbar and no actions.
- `frontend/tests/app/MemoLevelGroup.headerAdd.test.tsx` — rewritten for the single behaviour — covers DoD-3, DoD-4, DoD-5, DoD-6, DoD-7, DoD-8, DoD-9, DoD-10, DoD-11, DoD-12 — header '+' (one, icon-only, beside Title, ready only), draft first/focused/no flags, blur-save create/drop/failure, no Save/Cancel in any state, saved-note delete (no confirm)/patch/no-op, flags inside the editor root and disabled in flight, flag click sends only the flag patch then the body on later focus leave, reach line and failure text after the editor.
- `frontend/tests/app/MemoLevelGroup.test.tsx` — covers DoD-14 — stub renders `toolbarActions` inside its root; existing 015/016/018 tests unchanged.
- `frontend/tests/app/memoLevelState.discard.test.ts` — covers DoD-7 (state level) — rewritten (could not delete with this role's tools): `discardNewNote` not exported; blank/whitespace draft dropped by `saveNewNote` with no request. Plan lists it for deletion — the orchestrator may `rm` it instead.
- `frontend/tests/app/CharacterNotesSection.test.tsx` — covers DoD-3, DoD-4, DoD-5, DoD-6, DoD-7, DoD-8, DoD-10, DoD-12, DoD-13, DoD-14 — Save/Cancel tests became blur tests; flags inside editor root; keyboard reorder sends the whole order.
- `frontend/tests/app/MemoChainSection.test.tsx` — covers DoD-3, DoD-5, DoD-6, DoD-10, DoD-13, DoD-14 — one header '+' per wall level; no Save/Cancel; flags inside editor root; keyboard move of a Session note sends that level's whole order.
- `frontend/tests/app/SettingsScreen.test.tsx` — covers DoD-3, DoD-5, DoD-10, DoD-14 — "Your notes" header '+', no Save/Cancel, flags inside editor root.
- `frontend/tests/app/CharacterScreen.test.tsx` — covers DoD-5, DoD-6, DoD-14 — archived-character new note saved by blur, no "Save new note"; stub renders the slot.
- `frontend/tests/app/SessionScreen.test.tsx`, `sessionFirstReply.test.tsx`, `searchLanding.test.tsx`, `App.test.tsx`, `CharacterScreen.export.test.tsx` — cover DoD-14 — stub renders the toolbar-actions slot; no other change.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15..DoD-18 [manual/live, no test]

## Notes & Issues

_populated by the coder when worth saying_
