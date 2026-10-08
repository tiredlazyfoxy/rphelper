# Fast feature 011 — composer-send-icon-and-shortcut

| Status  | Verifier | Date |
|---------|----------|------|
| done    | PASS     | 2026-10-08 |

## Files Changed

- `frontend/src/app/ComposerCore.tsx` — Ctrl/Cmd+Enter send, in-box `IconSend` Send / `sendSlot` in the Textarea right section, vertical resize with `rows`/min-height from `minRows`, `fullWidth` drops the 720px column
- `frontend/src/app/CharacterComposer.tsx` — passes `fullWidth` and `minRows={10}` (landed with the skeleton; no further change)

## Bug Fixes

### Composer text box not resizable; heights not persisted (2026-10-08)
- `frontend/src/app/ComposerCore.tsx` — right section now `rightSectionPointerEvents="none"` with only the Send/Stop control re-enabled (`pointerEvents: auto` wrapper) and lifted clear of the corner (`paddingBottom` 18), so the native bottom-right resize grip is grabbable; new optional `heightField` / `storage` props restore a stored height as inline `style.height` on mount and save the inline px height on textarea `mouseup` / `pointerup` (drag end), never while typing
- `frontend/src/app/composerHeights.ts` — new pure module: `COMPOSER_HEIGHTS_KEY` "rphelper.composer-heights", total `readComposerHeights`, best-effort merging `writeComposerHeight`
- `frontend/src/app/Composer.tsx` — optional `storage` prop; passes `minRows={3}`, `heightField="chat"`, `storage`
- `frontend/src/app/CharacterComposer.tsx` — optional `storage` prop; passes `heightField="start"`, `storage` (keeps `minRows={10}`, `fullWidth`)
- `frontend/src/app/SessionStream.tsx`, `frontend/src/app/SessionScreen.tsx` — thread the screen's `storage` to `Composer` (new optional `SessionStreamProps.storage`)
- `frontend/src/app/CharacterScreen.tsx`, `frontend/src/app/App.tsx` — new optional `storage` on `CharacterScreenProps` / `CharacterRouteProps`, threaded from `App` to `CharacterComposer` (the screen did not previously receive it)

## Skeleton

### Frozen interface (2026-10-08)
- `frontend/src/app/ComposerCore.tsx` — `ComposerCoreProps.fullWidth?: boolean` (default `false`) — new. Off: outer wrapper keeps `maw 720`, `mx auto`, `px 18`. On: no max-width cap, no side padding.
- `frontend/src/app/ComposerCore.tsx` — `ComposerCoreProps.minRows?: number` (default `2`) — new. Textarea native `rows` = `minRows`; a min-height equivalent to that many lines stops a drag below it.
- `frontend/src/app/ComposerCore.tsx` — `ComposerCore(props: ComposerCoreProps): React.JSX.Element` — unchanged signature; all existing props (`draft`, `onDraftChange`, `onSend`, `sendEnabled`, `sendBlockedReason?: string | null` = null, `onPaste?`, `underArea?`, `sendSlot?`, `besideSend?`) unchanged in name, type and meaning. No new exported symbol; the key handler is internal.
- Stub state: both props are declared in the type only and not yet read by the component; current rendering is untouched (labelled Button "Send" in the row, `autosize`, `minRows 2`, `maw 720`). The coder implements all new behaviour.
- `frontend/src/app/CharacterComposer.tsx` — now passes `fullWidth` (true) and `minRows={10}` to `ComposerCore` (no observable effect until the coder consumes the props). Setup select stays in `underArea`.
- Caller-compile edits (out of Source-files scope): None. `Composer.tsx` untouched (defaults carry it).

### Test-facing contract
- Textarea: `aria-label="Composer"`; `rows` attribute = `minRows` (2 default, 10 on character page); no `autosize`; `resize="vertical"` (Mantine `--input-resize: vertical`), never `both`/`horizontal`.
- Send: `IconButton` (`icon` = `IconSend`, `label="Send"`, `sizeVariant="main"`) — accessible name exactly "Send", no visible text — rendered in the Textarea's `rightSection` (pointer events enabled, positioned bottom-right), i.e. a descendant of the same Mantine input wrapper as the textarea. Disabled iff `!sendEnabled || sendBlockedReason !== null`; click calls `onSend`.
- `sendSlot` (when not `undefined`): renders in that same in-box position and replaces Send (no "Send" button).
- Row under the box (right-justified `Group`, after `underArea`, outside the input wrapper): blocked-reason `Text` then `besideSend`. Order: textarea → `underArea` → row.
- Wrapper: default outer `Box` carries `maw 720`; with `fullWidth` no ancestor of the textarea inside `ComposerCore` carries 720px max-width.
- Keyboard: `onKeyDown` on the textarea. Enter with `ctrlKey || metaKey`, not `nativeEvent.isComposing` → `preventDefault()`; then calls `onSend` exactly once iff `sendEnabled && sendBlockedReason === null && sendSlot === undefined`. During IME composition: ignored entirely (no send). Plain Enter / Shift+Enter: never send, default not prevented.

## Tests

### Tests (2026-10-08)
- `frontend/tests/app/ComposerCore.keyboard.test.tsx` — new — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5 — Ctrl/Cmd+Enter sends once iff enabled/no reason/no slot; default prevented on the combo; IME ignored; plain/Shift+Enter never send and are not prevented.
- `frontend/tests/app/ComposerCore.test.tsx` — covers DoD-6..DoD-12, DoD-14 — icon-only "Send" inside the Mantine input wrapper; enable/disable/click; sendSlot in-box; blocked reason + besideSend outside the box after underArea; resize `vertical` only; `rows` 2 / N; 720px max-width by default, none with `fullWidth`; `buttonNames()` now reads aria-labels and the 018 DoD-4 / 019 DoD-7 order cases assert "inside the box".
- `frontend/tests/app/CharacterComposer.test.tsx` — covers DoD-13 — rows >= 10, no 720px max-width ancestor, Setup select after the textarea.
- `frontend/tests/app/Composer.test.tsx` — covers DoD-14 — two 018 step 003 order cases: Send in the box, preview before Settle (no longer before Send).
- `frontend/tests/app/ComposerStop.test.tsx` — covers DoD-14 — "Stop where Send sits" now asserts Stop inside the input wrapper, before Settle.
- Unchanged (role/name "Send" lookups still resolve; DoD-14): `CharacterComposer.setup.test.tsx`, `SessionScreen.test.tsx`, `App.test.tsx`, `sessionFirstReply.test.tsx`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 [manual/live, no test], DoD-16 [manual/live, no test], DoD-17 [manual/live, no test]

### Repro test (2026-10-08)
- reproduces: "character sessions page main text box of start must be resizable (vertical) but it's not" — bug-fix: architecture 2026-10-08 composer rule (workspace-shell.md Geometry + Layout persistence `ComposerHeights`), superseding this plan's session default 2 / no persistence.
- `frontend/tests/app/composerHeights.test.ts` — new — covers DoD-16 — key `rphelper.composer-heights`; total read with independent per-field null fallback (null storage, throwing getItem, absent key, bad JSON, non-object, wrong type, non-finite, <= 0), no upper clamp; write merges one field over a fresh read, swallows a throwing setItem, writes nothing for a non-size, no-op on null storage.
- `frontend/tests/app/ComposerCore.test.tsx` — covers DoD-10, DoD-11, DoD-16 — `heightField` + `storage`: stored height applied as inline px on mount; mouseup / pointerup drag end writes the field and keeps the other; typing (keyboard only) writes nothing; no heightField means nothing read or written; still vertical resize. ComposerCore's own default rows 2 case unchanged.
- `frontend/tests/app/Composer.test.tsx` — covers DoD-10, DoD-11, DoD-16 — session composer rows 3, vertical resize; stored `{"chat":260,"start":400}` gives 260px, drag to 300px stores chat 300 keeping start 400; typing writes nothing.
- `frontend/tests/app/CharacterComposer.test.tsx` — covers DoD-10, DoD-13, DoD-16 — start composer rows 10, vertical resize; stored `{"start":400}` gives 400px, drag end writes `start` not `chat`; typing writes nothing.
- Coverage: DoD-10 ✓, DoD-11 ✓ (session host now rows 3), DoD-13 ✓, DoD-16 ✓ (persistence part now under test; the visual drag stays manual/live)

## Notes & Issues

_populated by the coder when worth saying_
