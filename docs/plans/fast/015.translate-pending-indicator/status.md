# Fast feature 015 — translate-pending-indicator

| Status  | Verifier | Date |
|---------|----------|------|
| done    | PASS     | 2026-11-05 |

## Files Changed

- `frontend/src/app/StreamRecord.tsx` — `TranslationPendingGlyph` (Loader) filled and wired into `PartnerFlicker` while pending; `StreamEntry` reveals its actions group while its translation is pending; skeleton scaffolding line and `IconButtonProps` import removed

## Skeleton

### Frozen interface (2026-11-05)
- `frontend/src/app/StreamRecord.tsx` — `function TranslationPendingGlyph(props: { size?: number | string; stroke?: number }): React.JSX.Element` (module-local, not exported; must satisfy `IconButtonProps["icon"]`) — new; stub body throws `Error("Not implemented: TranslationPendingGlyph (fast 015)")`. Contract: renders a Mantine `Loader` at `props.size`, `data-testid="translation-pending"`, ignores `stroke`.
- `frontend/src/app/StreamRecord.tsx` — `const PartnerFlicker = observer(function PartnerFlicker(props: { translations: TranslationState; entry: Message }): React.JSX.Element)` — changed in behavior only (signature unchanged); pending → `icon={TranslationPendingGlyph}`, else `IconLanguage`. Not yet wired (wiring the throwing stub would break the existing pending-label tests).
- `frontend/src/app/StreamRecord.tsx` — `const StreamEntry = observer(function StreamEntry(props: StreamEntryProps): React.JSX.Element)` — changed in behavior only (signature and `StreamEntryProps` unchanged); `revealed` additionally true when `translations` is given and `translationView(translations, entry.id).status === "pending"`, read in this observer render. Not yet implemented.
- Added `import type { IconButtonProps } from "../shared/IconButton";` and a module-level scaffolding line `void (TranslationPendingGlyph satisfies IconButtonProps["icon"]);` (keeps `noUnusedLocals` green and pins the glyph's type). **The coder removes that line** (and the type import if then unused) when `PartnerFlicker` uses the glyph; the coder adds the `Loader` import.
- Caller-compile edits (out of Source-files scope): None.

## Tests

### Tests (2026-11-05)
- `frontend/tests/app/StreamRecordTranslationPending.test.tsx` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-6, DoD-7 — language glyph at rest / answered / after cancel; `translation-pending` loader (and no language glyph) inside the single enabled, non-`aria-pressed` "Cancel translation" while the POST is deferred; the flicked entry's one `[data-revealed]` reads "true" while pending (bare click, no hover/focus), the other entry "false", and back to "false" after answer, cancel and 502 `translation_failed`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 [verifier gate: existing suites via full `npm test`, no new test], DoD-9 [verifier gate: `npm run typecheck`, no new test], DoD-10 [manual/live, no test]

## Notes & Issues

_populated by the coder when worth saying_
