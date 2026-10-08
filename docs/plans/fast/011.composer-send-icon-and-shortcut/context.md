# Fast feature 011 — composer-send-icon-and-shortcut — context

Frontend only (`app` entry). No backend, no API, no store change.

## The request, as interpreted

The user asked (two messages) for: the character page's "New session" text box
to be full width and at least 10 lines high; Send on the same line as the Setup
select; Ctrl+Enter to send "anywhere in the chat"; Send to be an icon **inside**
the chat box rather than a big button; the box to be vertically adjustable; full
width **only** on the character page, the session page keeping its margins.

Interpretations recorded (user-authorised orchestrator defaults):

- **"Same line as the Setup select" is superseded by "icon inside the chat
  box".** Send sits at the text box's bottom-right, inside the box, so it reads on
  the line directly above the Setup row. The Setup select stays under the box.
- **"Anywhere in the chat" = both hosts of the shared composer** (session page
  and character page). There is no other chat input with a send action: the
  stream's "Edit entry text" and the zone's "Edit message text" boxes are
  blur-commit edit boxes and are untouched; discussion and translation have no
  input.
- **Vertical resize replaces auto-grow.** Mantine's `autosize` and a native
  resize grip conflict (autosize overwrites the dragged height on every
  keystroke), so `autosize` goes. The session composer keeps a ~2-line starting
  and minimum height and no longer grows with content; the roleplayer drags it.
- **Cmd+Enter (metaKey) is treated as Ctrl+Enter** for macOS.

## Files involved

- `frontend/src/app/ComposerCore.tsx` — the shared composer. Used only by
  `Composer.tsx` (session page, ~l.85) and `CharacterComposer.tsx` (character
  page "New session", ~l.94).
- `frontend/src/app/CharacterComposer.tsx` — character-page host; passes
  `underArea` (the Setup `Select` size `xs` plus the "Could not load setups to
  choose from." text); no `sendSlot`/`besideSend`. Sits inside CharacterScreen's
  Sessions tab panel (`Container size="md"`); the 720px/18px narrowing comes only
  from ComposerCore's own wrapper `Box`.
- `frontend/src/app/Composer.tsx` — session-page host. **Not edited.** Passes
  `sendSlot` = Stop `IconButton` (`IconPlayerStop`, "Stop", `sizeVariant`
  "main") only while streaming, else `undefined`; `besideSend` = labelled filled
  "Settle" `Button` + optional "Discard empty zone" `IconButton`;
  `sendBlockedReason` only when not streaming and kind is turn.
- `frontend/src/shared/IconButton.tsx` — props `icon, label, onClick, disabled?,
  color?, sizeVariant?`. **Not widened** (`ui-conventions.md`).

## Current ComposerCore shape (from harvest)

Props: `draft`, `onDraftChange`, `onSend`, `sendEnabled`, `sendBlockedReason`
(string or null, default null), `onPaste?`, `underArea?`, `sendSlot?` (replaces
Send when not `undefined`), `besideSend?`.

Layout: a `Box` (`maw 720`, `mx auto`, `px 18`, full width) holding a `Stack`:
the `Textarea` (aria-label "Composer", `autosize`, `minRows 2`), then
`underArea`, then a right-justified `Group` with the blocked-reason `Text`, then
`sendSlot ?? <Button variant="default">Send</Button>` (disabled when
`!sendEnabled` or a blocked reason is set), then `besideSend`. No `onKeyDown`
anywhere; Enter inserts a newline.

## Mantine facts (7.17.8)

- `Textarea` takes `resize` (CSS `resize`, default `none`), and the base input's
  `rightSection`, `rightSectionWidth`, `rightSectionPointerEvents`. The section
  defaults to non-interactive pointer events — an interactive control inside it
  needs pointer events enabled. The section is vertically centred by default;
  bottom-right placement needs a `styles`/`style` adjustment on the section.
- `minRows`/`maxRows` are ignored without `autosize`. Without autosize the native
  `rows` attribute sets the starting height; a `min-height` on the input is what
  stops a drag below the minimum.
- Under vitest/jsdom `autosize` is a no-op and there is no layout: tests assert on
  attributes, props and inline styles/CSS variables, never pixels.

## Tests that currently find "Send"

About 21 role/name lookups of "Send" across: `ComposerStop`, `ComposerCore`,
`App`, `SessionScreen`, `Composer`, `CharacterComposer`,
`CharacterComposer.setup`, `sessionFirstReply` tests. Keeping the accessible name
exactly "Send" on the new `IconButton` keeps `getByRole("button", { name: "Send" })`
lookups resolving. `ComposerCore.test.tsx` has document-order tests (underArea
after the textarea, sendSlot where Send sat, besideSend after Send); a lookup by
visible text "Send", or an order assertion that assumed Send sits after
`underArea`, will break and is the test-coder's to adjust.

## Constraints

- Mantine props/styles only. No new stylesheet; `global.css`/`shell.css` are
  untouched (`frontend-structure.md`, `tests/stylesheets.test.ts` pins the set).
- Every icon-only action goes through `IconButton`; `IconSend` from
  `@tabler/icons-react` is currently unused. Main-size metrics (`sizeVariant`
  "main").
- TypeScript only; `npm run typecheck` is the gate.
- The architecture currently says the opposite on three points (Send is a
  labelled button; the composer grows and has no handle; the composer shares the
  stream's 720px column everywhere). Those are amended via `outcome.md`, not here.
