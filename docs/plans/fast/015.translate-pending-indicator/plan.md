# Fast feature 015 — translate-pending-indicator

## Goal

Make a pending partner-text translation visible: while an entry's translation is
pending its flicker shows a spinning loader in place of the language glyph, and
that entry's actions group is revealed without hover (US-045.AC-1;
DEC-F015-1 .. DEC-F015-4).

## Source files

frontend/src/app/StreamRecord.tsx — `PartnerFlicker` pending glyph; `StreamEntry` reveal-while-pending

## Test files

frontend/tests/app/StreamRecordTranslationPending.test.tsx — new; the pending glyph, its cancel, and reveal-while-pending

## Interface intent

**`frontend/src/app/StreamRecord.tsx`** (changed)

- **Pending glyph (new, module-local, not exported).** A small component
  compatible with `IconButton`'s `icon` prop: given the size (and ignoring the
  stroke) `IconButton` passes, it renders a Mantine `Loader` at that size, carrying
  `data-testid="translation-pending"` (DEC-F015-2).
- **`PartnerFlicker`** (changed). Inputs unchanged (translation state + entry).
  When the entry's `translationView` status is pending, it passes the pending glyph
  as `icon`; otherwise `IconLanguage` as today. Label, colour and click behaviour
  are unchanged ("Show translation" / "Cancel translation" / "Show original";
  teal while translated; press calls `flickTranslation`). `IconButton` is used as
  is (DEC-F015-3).
- **`StreamEntry`** (changed). Its `revealed` additionally becomes true when it
  was given a translation state and that state's view for this entry is pending
  (DEC-F015-4). The existing reveal conditions, the single `data-revealed`
  attribute and the opacity style are otherwise unchanged. The pending read must
  happen in an observer render so the reveal reacts when the pending set changes.

No change to `IconButton`, `translationState.ts`, `translationApi.ts` or
`SessionStream.tsx`.

## Definition of done

1. `[test]` With a translation state, a partner entry at rest (no request made)
   shows its "Show translation" button containing the language glyph and no
   element with test id `translation-pending`. (D15 unchanged for original)
2. `[test]` After pressing "Show translation" while the POST is unresolved, the
   single "Cancel translation" button contains an element with test id
   `translation-pending` and does not contain the language glyph; the body still
   shows the original text. (US-045.AC-1, DEC-F015-2)
3. `[test]` While pending, the "Cancel translation" button is enabled, has no
   `aria-pressed` attribute, and is the only button with that accessible name in
   the entry. (DEC-F015-3)
4. `[test]` Pressing "Cancel translation" while pending returns the button to
   "Show translation" with the language glyph and no `translation-pending`
   element. (DEC-F015-2, workspace-shell "The stop control")
5. `[test]` When the POST answers with text, the button reads "Show original",
   contains the language glyph and no `translation-pending` element.
   (US-045.AC-1)
6. `[test]` With two partner entries, pressing "Show translation" on the first
   (no hover, no focus) makes the first entry's single `[data-revealed]` read
   "true" while the request is unresolved; the second entry's reads "false".
   (DEC-F015-4)
7. `[test]` After that pending request resolves — separately for: answered with
   text, cancelled via "Cancel translation", and failed (502
   `translation_failed`) — the entry's `[data-revealed]` reads "false" again,
   absent hover. Each entry keeps exactly one `[data-revealed]` throughout.
   (DEC-F015-4, US-048.AC-1)
8. `[test]` The existing suites pass unchanged:
   `frontend/tests/app/StreamRecordTranslation.test.tsx`,
   `frontend/tests/app/SessionStreamTranslation.test.tsx`,
   `frontend/tests/app/StreamRecordActions.test.tsx`,
   `frontend/tests/shared/IconButton.test.tsx`, `frontend/tests/stylesheets.test.ts`
   (verifier runs the full `npm test`).
9. `[test]` `npm run typecheck` is clean (verifier gate).
10. `[manual/live]` In a browser with a real model busy composing, pressing the
    flicker on a partner entry shows a spinner in the button, the actions group
    stays visible without hover until the translation lands, and the button does
    not change size between glyphs.

## Out of scope

- Any change to `IconButton` (no loading prop, no widened props).
- `aria-busy`, live-region announcements, or any new accessible text.
- A pending colour, an elapsed-time display, or a marker outside the actions group.
- Any change to translation state, the API client, the backend, or the queuing /
  timeout behaviour itself.
- New stylesheet rules; product or architecture doc edits (finalization only).
- Modifying the existing test files listed in DoD-8.
