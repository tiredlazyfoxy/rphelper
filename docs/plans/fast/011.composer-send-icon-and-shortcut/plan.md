# Fast feature 011 — composer-send-icon-and-shortcut

## Goal

Make the shared composer send on Ctrl/Cmd+Enter, turn Send into an icon inside
the text box, and make the box vertically resizable instead of auto-growing; on
the character page only, the composer fills its container width and is at least
10 lines high.

## Source files

- `frontend/src/app/ComposerCore.tsx` — keyboard send, in-box Send/slot, resize, two new optional layout props
- `frontend/src/app/CharacterComposer.tsx` — passes the full-width and 10-line props

## Test files

- `frontend/tests/app/ComposerCore.test.tsx` — existing; slot/order/Send assertions updated, new layout and in-box assertions
- `frontend/tests/app/ComposerCore.keyboard.test.tsx` — new; Ctrl/Cmd+Enter behaviour
- `frontend/tests/app/CharacterComposer.test.tsx` — existing; full width and 10 lines
- `frontend/tests/app/CharacterComposer.setup.test.tsx` — edit only if a "Send" lookup or order assertion breaks
- `frontend/tests/app/Composer.test.tsx` — edit only if a "Send" lookup or order assertion breaks
- `frontend/tests/app/ComposerStop.test.tsx` — edit only if a "Send"/"Stop" lookup or order assertion breaks
- `frontend/tests/app/SessionScreen.test.tsx` — edit only if a "Send" lookup breaks
- `frontend/tests/app/App.test.tsx` — edit only if a "Send" lookup breaks
- `frontend/tests/app/sessionFirstReply.test.tsx` — edit only if a "Send" lookup breaks

(Paths for the ComposerCore/Composer/ComposerStop/SessionScreen tests follow the
`frontend/tests/app/` convention of the others; if one lives elsewhere the
test-coder uses its real path — it is the same file.)

## Interface intent

**`ComposerCore` component** — existing props unchanged in name and meaning.
Two new **optional** props, whose defaults reproduce the session composer:

- a **full-width flag** (default off). Off: the composer keeps its centred
  720px / 18px-padded column. On: no max-width cap and no side padding — it fills
  whatever container it is placed in.
- a **minimum-rows number** (default 2). The text box starts at this many lines
  and cannot be dragged shorter than it.

Behaviour changes inside `ComposerCore`:

- **Text box**: no longer auto-grows; it is user-resizable **vertically only**.
  Accessible name stays "Composer". Its starting height is the minimum-rows value
  (native `rows`), and a minimum height equivalent to that many lines stops a drag
  below it. No maximum.
- **Send control**: an icon-only `IconButton` (`IconSend`, label "Send",
  `sizeVariant` "main") rendered **inside the text box, at its bottom-right**
  (Mantine right section of the `Textarea`, or an equivalent Mantine-only
  overlay), disabled under exactly the same condition as today (not
  `sendEnabled`, or a blocked reason set), calling `onSend` on click. The text
  must not run underneath it.
- **`sendSlot`**: when provided (Stop while streaming), it renders in the Send
  control's in-box position, replacing Send — same replacement rule as today.
- **Row under the box**: `underArea` still directly follows the text box; the
  right-justified row still holds the blocked-reason text and `besideSend`
  (Settle, Discard). Send is no longer in that row.
- **Keyboard send**: a key handler on the text box. Ctrl+Enter or Cmd+Enter
  (meta) calls `onSend` exactly once **iff** Send would be enabled and visible —
  `sendEnabled`, no blocked reason, and no `sendSlot` replacing Send. When it
  sends, or when it is the combo but sending is not allowed, the default is
  prevented so no newline is inserted. Ignored entirely while an IME composition
  is in progress. Plain Enter and Shift+Enter keep inserting a newline and never
  send.

**`CharacterComposer` component** — no prop change; passes the full-width flag on
and a minimum-rows value of 10 to `ComposerCore`. Setup select stays in
`underArea`.

## Definition of done

1. **DoD-1** `[test]` In `ComposerCore`, Ctrl+Enter in the "Composer" text box with Send enabled calls `onSend` exactly once.
2. **DoD-2** `[test]` Cmd+Enter (metaKey) behaves identically to DoD-1.
3. **DoD-3** `[test]` Ctrl+Enter calls nothing when `sendEnabled` is false, when `sendBlockedReason` is a string, or when `sendSlot` is provided.
4. **DoD-4** `[test]` Plain Enter and Shift+Enter never call `onSend`.
5. **DoD-5** `[test]` A Ctrl+Enter keydown that sends has its default prevented (the event reports `defaultPrevented`); a Ctrl+Enter keydown during IME composition (`isComposing`) does not call `onSend`.
6. **DoD-6** `[test]` The Send control is a button with accessible name exactly "Send", has no visible text label "Send", and is rendered inside the text box's input wrapper (a descendant of the same Mantine input root/wrapper that contains the "Composer" textarea), not in the row under it.
7. **DoD-7** `[test]` Send is disabled when `sendEnabled` is false or a blocked reason is set, enabled otherwise; clicking it when enabled calls `onSend`.
8. **DoD-8** `[test]` With `sendSlot` provided, no "Send" button exists and the slot's content renders inside the text box's input wrapper.
9. **DoD-9** `[test]` `besideSend` content (e.g. a labelled "Settle" button) and the blocked-reason text render outside the text box's input wrapper, after the text box and after `underArea` in document order; `underArea` follows the textarea.
10. **DoD-10** `[test]` The "Composer" textarea is vertically resizable: the rendered DOM carries a resize value of `vertical` (Mantine's `--input-resize` CSS variable or an inline `resize` style) and never `both`/`horizontal`.
11. **DoD-11** `[test]` With defaults, the "Composer" textarea's `rows` is 2 and the composer's outer wrapper carries a 720px max-width; with the minimum-rows prop set to N, `rows` is N.
12. **DoD-12** `[test]` With the full-width flag on, no ancestor of the "Composer" textarea inside `ComposerCore` carries a 720px max-width.
13. **DoD-13** `[test]` `CharacterComposer` renders its "Composer" textarea with `rows` ≥ 10 and without a 720px max-width ancestor from the composer; its "Setup" select still renders after the textarea.
14. **DoD-14** `[test]` Every existing test that finds Send by role and name "Send" still passes (session page, character page, stop, first-reply flows) — adjusted only where it assumed visible text or the old position.
15. **DoD-15** `[manual/live]` Visual: Send icon sits at the box's bottom-right inside the border, text never runs under it; Stop takes the same spot while streaming; Settle/Discard sit in the row under the box; character-page composer spans the tab panel width and starts at ~10 lines; session composer stays in the 720px column at ~2 lines.
16. **DoD-16** `[manual/live]` Drag-resize: the grip resizes vertically only, cannot go below the minimum lines, and typing does not snap the height back.
17. **DoD-17** `[manual/live]` `npm run typecheck`, `npm run build` and `npm test` pass from `frontend/`.

## Out of scope

- `Composer.tsx` (session host) — no edits; its defaults carry it.
- The stream's "Edit entry text" / zone "Edit message text" boxes — no shortcut.
- Any change to `IconButton`'s props.
- Any stylesheet change; no new stylesheet.
- Persisting the dragged height anywhere.
- Moving the Setup select or changing its contents/behaviour.
- Any backend or API change; any change to what Send/Stop/Settle do.
