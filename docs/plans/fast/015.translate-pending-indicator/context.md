# Fast feature 015 — translate-pending-indicator — context

## Why

A partner-text translation (US-045.AC-1) can queue behind a long compose
generation on the same model, up to the provider timeout. Today the only sign it
is pending is the flicker's tooltip / `aria-label` switching to "Cancel
translation", on a button inside a hover-hidden actions group — so the user saw
"the button switched but the text is untranslated". This feature makes the
pending state visible: a spinning glyph on the flicker, and the entry's actions
group revealed while that entry is pending. User direction: do it in code, record
it as a technical decision, no spec change (DEC-F015-1).

## Decisions this plan rests on

DEC-F015-1 .. DEC-F015-4 in `docs/decisions/fast-015.translate-pending-indicator.md`.
They narrow 023 D15 ("one icon, state carried by the label") and the hover-reveal
rule (014 D6) for the pending state only. Read them; the plan does not restate them.

## Architecture binding (cite, do not edit)

- `docs/architecture/ui-conventions.md` — icon table row "Translate / flicker"
  (`IconLanguage`); the `IconLanguage` note (three labels, teal translated colour,
  no `aria-pressed`, `IconButton` not widened); Accessibility floor, hover-reveal
  paragraph (Mantine `useHover` + `useFocusWithin` + `(hover: none)`, opacity, no
  stylesheet selector, pinned by `tests/stylesheets.test.ts`).
- `docs/architecture/workspace-shell.md` — "Every per-entry action lives inside
  the entry" (one revealed group); "The stop control" (the flicker is the
  translation's own cancel; a stopped translation leaves the original showing).
- Originating contract: 023 step 004 (translation client state, `translationView`)
  and step 005 (flicker UI, D13–D15).

## Code facts (from the harvest; do not go fishing)

- `frontend/src/app/StreamRecord.tsx`
  - `TRANSLATED_COLOR = "teal"` (~:103).
  - `PartnerFlicker` (~:113-135): an `observer` taking `translations: TranslationState`
    and `entry: Message`; label from `translationView(translations, entry.id)`;
    renders `<IconButton icon={IconLanguage} label=… color=… onClick=flickTranslation…>`.
  - `StreamEntry` derives `revealed` (~:225) from `useHover` / `useFocusWithin` /
    `useMediaQuery("(hover: none)")` / editor-open; it receives the optional
    translation state. The actions `Group` (~:276-281) carries
    `data-revealed={revealed ? "true" : "false"}` and `style={{ opacity: revealed ? 1 : 0 }}`;
    `PartnerFlicker` is mounted inside it (~:285-287) for partner entries when a
    translation state is given.
  - The file carries uncommitted fast/014 edits (delete icon). Plan against the
    on-disk state; do not disturb the delete control.
- `frontend/src/shared/IconButton.tsx`: props `icon`, `label`, `onClick`,
  `disabled?`, `color?`, `sizeVariant?` ("main" | "inline" | "chevron" → 18 / 16 / 14,
  stroke 1.5); renders a `Tooltip` around a subtle `ActionIcon`, calling `icon`
  with a size and stroke. 40 call sites — **not changed** by this feature.
- `frontend/src/app/translationState.ts` (~:65): `translationView(state, id)` →
  original | pending | translated(text); pending is the observable `state.pending` Set.
  `StreamEntry` must read it inside an observer render so the reveal reacts.
- Loader convention in the repo: Mantine `<Loader size="sm" />`
  (`CharacterTree.tsx`, `SessionConfigBar.tsx`). The pending glyph renders a
  `Loader` at the numeric size `IconButton` passes so the button does not resize.
- Tabler icons render an `<svg>` whose class includes `tabler-icon-language` —
  usable by tests to detect the language glyph's presence/absence. The pending
  glyph's test hook is `data-testid="translation-pending"` (DEC-F015-2).

## Constraints

- Frontend only; TypeScript only; Mantine only; **no new stylesheet rules**.
- Exactly one `[data-revealed]` per entry; "false" at rest with nothing pending.
- While pending the flicker stays one enabled button named "Cancel translation",
  no `aria-pressed` (DEC-F015-3).
- Existing tests must keep passing untouched:
  `frontend/tests/app/StreamRecordTranslation.test.tsx` (one button per label,
  pending label + original body, press "Cancel translation" while pending, exactly
  one `[data-revealed]` "false" at rest and "true" on hover, no aria-pressed),
  `SessionStreamTranslation.test.tsx`, `StreamRecordActions.test.tsx`,
  `frontend/tests/shared/IconButton.test.tsx`, `frontend/tests/stylesheets.test.ts`.
  Note: the existing "false at rest" assertion is taken with no translation pending;
  if any existing test asserts `data-revealed="false"` *while* a translation is
  pending, that is a SPEC conflict to report, not a test to edit.
- Test helpers available in the existing translation test (for the test-coder to
  mirror in the new file): `stubFetch(router)` with deferred `call(i).respond(...)`,
  `renderRecord(state, translations?)`, `partnerItem()`, `flicker(label)`, `press(label)`.

## Commands (root `CLAUDE.md`, run from `frontend/`)

`npm test`, `npm run typecheck`.
