# Fast feature 011 — composer-send-icon-and-shortcut — outcome

Intended documentation changes, applied by the architect at finalization.

## `docs/architecture/ui-conventions.md`

- **Section: Icon table, row "Send message in discussion".** Change from
  "labelled button, not an icon" to `IconSend`, labelled "Send", `IconButton`
  `sizeVariant` "main", **inside the composer text box at its bottom-right**.
  Reason: user request (fast/011) — Send must be an icon inside the chat box, not
  a big button.
- **Section: Notes, "Settle and Send are labelled buttons, not icons."** Narrow to
  Settle only; record that Send became icon-only in-box (fast/011, user decision)
  and why Settle stays labelled (most consequential action, UC-035).
- **Section: Notes, "Regenerate is labelled rather than icon-only … the three
  controls that spend a model call all carry words".** Amend: Send no longer
  carries words; the rule now covers Regenerate (and Settle's own reasoning),
  with Send named as the deliberate exception and its reason (it sits inside the
  box it sends from, and Ctrl/Cmd+Enter is its primary path).

## `docs/architecture/workspace-shell.md`

- **Section: Geometry table, row "Composer".** "same 720px / 18px as the stream"
  → keep for the session page; add the deliberate exception: the character
  page's "New session" composer fills its container (no 720px cap, no 18px
  padding). Reason: user request; on the character page there is no stream whose
  left edge it must share.
- **Section: Geometry table, row "Composer text area".** "min-height 42px, no
  max, no handle" → vertically resizable (native grip, `resize: vertical`), no
  auto-grow; starts at and cannot shrink below 2 lines on the session page, 10
  lines on the character page; no max.
- **Section: paragraph "The composer grows with its content."** Replace: the
  composer is drag-resizable vertically and does not auto-grow, because autosize
  and a native grip fight (autosize overwrites the dragged height). Record as a
  user decision (fast/011).
- **Section: "Nothing in the shell is user-resizable."** Add the composer text box
  as the named exception (vertical only, not persisted).
- **Section: Reversal record, (C) No auto-grow.** Record that (C)'s reversal is
  itself partly reversed: auto-grow removed again, but unlike old (C) the box has
  a native vertical grip and no internal hard height. Update "(B) and (C) do not
  return" accordingly. Reason: user request fast/011.
- **Composer / send behaviour (wherever the composer's send is described, and the
  character page section).** Add: Ctrl+Enter and Cmd+Enter in the composer text
  box send exactly when Send is enabled and shown (not while streaming / Stop is
  shown); plain Enter inserts a newline; ignored during IME composition. The
  stream's edit boxes have no shortcut. Send and, while streaming, Stop sit
  inside the box at its bottom-right; blocked-reason text, Settle and Discard sit
  in the row beneath. On the character page the Setup select sits under the box.

## `docs/architecture/quick-reference.md`

- **Section: geometry.** Mirror the two workspace-shell geometry row changes
  (character-page composer full width, 10 lines; text box vertical resize, no
  auto-grow).

## `docs/product/`

- No product change intended. The architect should confirm no story or use case
  pins Send as a labelled button or the composer as auto-growing; if one does,
  hand back to `/product-spec` rather than editing it. (Not verified by the
  planner.)

## Observations
