# Decisions — fast-011.composer-send-icon-and-shortcut
**Stage:** — · **Feature:** fast/011.composer-send-icon-and-shortcut

Send becomes an icon-only control inside the composer's text box, Ctrl/Cmd+Enter
sends, the character page's start composer fills its container, and the composer
rule of 2026-10-08 (no auto-grow, a native vertical handle, a persisted dragged
height) is built — including its bug fix of the same day, which made the resize
grip reachable and added the height persistence. The contracts are
`workspace-shell.md` "Geometry", "Layout persistence" and "Send, Stop and the
keyboard", and `ui-conventions.md`'s icon table (Send). The entries below are the
mechanisms inside the shared composer component.

### DEC-F011-1 — Send is an icon-only control in the text box's bottom-right corner; Stop takes the same slot
- **Status:** accepted
- **Stage:** — · **Feature:** fast/011.composer-send-icon-and-shortcut · **Step:** —
- **Date:** 2026-10-08 · **Decided by:** user
- **Question:** Where and in what form does the composer's Send control sit, and how does Stop replace it while a compose streams?
- **Decision:** Send is an `IconButton` (`IconSend`, accessible name exactly "Send", the `main` size variant) rendered in the `Textarea`'s right section, anchored to its bottom-right. The host's `sendSlot` (Stop while streaming) replaces it in the same spot. The blocked reason, Settle and Discard stay in the row beneath the box; on the character page the Setup select sits under the box. This supersedes "Send on the same line as the Setup select" (plan 018's start-composer layout, named in text; no DEC entry exists for it).
- **Reason:** User decision. Keeping the accessible name exactly "Send" keeps every existing lookup by name working, so the move did not ripple into callers. Send becomes the one exception to "a control that spends a model call carries words" (`ui-conventions.md`), with Ctrl/Cmd+Enter as its primary path.
- **Lands in:** `frontend/src/app/ComposerCore.tsx`
- **Cites:** `workspace-shell.md` "Send, Stop and the keyboard"; `ui-conventions.md` icon table (Send), Regenerate note

### DEC-F011-2 — The right section passes pointer events through except over the Send/Stop control
- **Status:** accepted
- **Stage:** — · **Feature:** fast/011.composer-send-icon-and-shortcut · **Step:** — (bug fix, 2026-10-08)
- **Date:** 2026-10-08 · **Decided by:** planner (bug fix)
- **Question:** The in-box Send/Stop control sat over the native bottom-right resize grip, so the grip could not be grabbed. How do both stay usable?
- **Decision:** The `Textarea` sets `rightSectionPointerEvents="none"`; only the Send/Stop wrapper sets `pointerEvents: auto`, and it is lifted clear of the grip with a bottom padding of 18 px.
- **Reason:** The right section spans the box's full height, so without pass-through it swallowed the drag on the grip; letting events through everywhere except the control itself keeps both the grip and the button reachable with no custom resize handle.
- **Lands in:** `frontend/src/app/ComposerCore.tsx`
- **Cites:** `workspace-shell.md` "Geometry" (the native vertical handle)

### DEC-F011-3 — The dragged height is saved at drag end and restored on mount, per composer
- **Status:** accepted
- **Stage:** — · **Feature:** fast/011.composer-send-icon-and-shortcut · **Step:** — (bug fix, 2026-10-08)
- **Date:** 2026-10-08 · **Decided by:** planner (bug fix)
- **Question:** How is the composer's dragged height captured, stored and restored without writing on every keystroke?
- **Decision:** The height is read as the textarea's inline pixel height and saved on both the textarea's `mouseup` and `pointerup` (the end of a drag), never while typing. It is restored as the inline `style.height` on mount, through the composer's `heightField` and `storage` parameters, and written through `composerHeights.ts` (`COMPOSER_HEIGHTS_KEY` = `"rphelper.composer-heights"`; a total read that tolerates a missing or malformed value, and a merging write that keeps the other field). Hosts: the session composer passes `minRows` 3 and `heightField` `"chat"`; the character page's start composer passes `minRows` 10, `heightField` `"start"` and full width. The storage is threaded App → SessionScreen → SessionStream → Composer, and App → CharacterScreen → CharacterComposer.
- **Reason:** A native resize fires no resize event on the element, so the end of the pointer gesture is the only cheap, reliable moment to read the new height. **Both events are bound** so the drag end is caught whichever of the two the browser and input type report; a duplicate write is harmless because the write merges idempotently. _This reason was reconstructed at finalization (2026-11-09): neither the plan nor the code states it, and the code carries no comment for the double binding._
- **Lands in:** `frontend/src/app/ComposerCore.tsx`, `frontend/src/app/composerHeights.ts`, `frontend/src/app/Composer.tsx`, `frontend/src/app/CharacterComposer.tsx`, the App → screen storage threading; localStorage key `rphelper.composer-heights`
- **Cites:** `workspace-shell.md` "Layout persistence"; `frontend-structure.md` module table (`composerHeights.ts`)

### DEC-F011-4 — Ctrl/Cmd+Enter sends when Send is shown and enabled; the text area is a fixed-rows, vertically resizable box
- **Status:** accepted
- **Stage:** — · **Feature:** fast/011.composer-send-icon-and-shortcut · **Step:** —
- **Date:** 2026-10-08 · **Decided by:** user
- **Question:** Which keystroke sends, under which conditions, and how is the box sized now that it no longer grows with its content?
- **Decision:** An `onKeyDown` on the textarea: Enter with `ctrlKey` or `metaKey`, and not `nativeEvent.isComposing`, calls `preventDefault` and sends once if `sendEnabled && sendBlockedReason === null && sendSlot === undefined` — so never while Stop shows, never with a blocked reason. IME composition is ignored entirely. Plain Enter and Shift+Enter neither send nor prevent the default (they insert a newline). Cmd is treated as Ctrl for macOS. The stream's in-place edit boxes get no shortcut. Sizing: `autosize` is removed; `rows` = the host's `minRows` with a matching min-height; `resize="vertical"`; the full-width option drops the 720 px max-width / 18 px side-padding wrapper (Mantine 7.17.8 facts).
- **Reason:** User decision: plain Enter stays a newline. Guarding on the same condition that enables the Send control keeps the shortcut and the button from disagreeing; ignoring composition keeps an IME's confirming Enter from sending.
- **Lands in:** `frontend/src/app/ComposerCore.tsx`
- **Cites:** `workspace-shell.md` "Geometry", "Send, Stop and the keyboard"
