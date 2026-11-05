# Decisions — fast-015.translate-pending-indicator
**Stage:** — · **Feature:** fast/015.translate-pending-indicator

A visible "waiting" state on a settled partner entry's translation flicker while
its translation request is pending (the request of US-045.AC-1, which can queue
behind a long compose on the same model). The flicker's contract is
`ui-conventions.md`'s `IconLanguage` note (023 D15) and the accessibility floor's
hover-reveal paragraph; `workspace-shell.md` "The stop control" (the flicker as
the translation's own cancel). The entries below refine D15 for the pending state
only.

### DEC-F015-1 — Build the pending indicator in code; no product or architecture change now
- **Status:** accepted
- **Stage:** — · **Feature:** fast/015.translate-pending-indicator · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** user
- **Question:** No story AC requires a visible pending indicator (US-045..US-048 cover first flick, cached flick, no context leak, failure). Should the product spec or architecture be revised before building it?
- **Decision:** No. Build it in code and record the refinement as a technical decision ("it's not so big for the spec"). At finalization `/architect` amends `ui-conventions.md`'s flicker note and hover-reveal paragraph to match; the product layer is untouched.
- **Reason:** User decision. The indicator changes how an existing state (pending, already labelled "Cancel translation") is shown, not what the product does.
- **Lands in:** `frontend/src/app/StreamRecord.tsx`; `docs/architecture/ui-conventions.md` (at finalization)
- **Cites:** US-045.AC-1; `ui-conventions.md` icon table "Translate / flicker", `IconLanguage` note (023 D15)

### DEC-F015-2 — While pending, the flicker's glyph is a spinning loader instead of the language icon
- **Status:** accepted
- **Stage:** — · **Feature:** fast/015.translate-pending-indicator · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** planner (orchestrator default under the user's direction)
- **Question:** How is "a translation is pending" made visible on the flicker, given D15 says one icon with the state carried by the label?
- **Decision:** While the entry's translation view is pending, `PartnerFlicker` passes a module-local wrapper component as `IconButton`'s `icon`; the wrapper renders a Mantine `Loader` at the size `IconButton` hands it, and carries `data-testid="translation-pending"` as its stable test hook. Original and translated states keep `IconLanguage` (translated keeps its teal colour). `IconButton`'s props are not widened and the component is not edited.
- **Reason:** A spinner is the repo's existing "work in flight" signal (Mantine `Loader` elsewhere in the `app` entry) and is visible without reading a tooltip; routing it through the existing `icon` prop keeps D15's "IconButton is not widened for it".
- **Rejected:** Mantine `ActionIcon`'s `loading` prop — it disables the button, which breaks pressing "Cancel translation" (023 D4); a pending colour only — too weak a signal next to the translated colour; widening `IconButton` with a loading prop — 40 call sites and D15 explicitly declines it.
- **Supersedes:** narrows 023 D15 ("one icon, state carried by the label, not two glyphs") for the pending state only; original and translated are unchanged.
- **Lands in:** `frontend/src/app/StreamRecord.tsx` (`PartnerFlicker` and its module-local pending glyph)
- **Cites:** `ui-conventions.md` `IconLanguage` note; US-045.AC-1

### DEC-F015-3 — Label and accessibility semantics are unchanged while pending
- **Status:** accepted
- **Stage:** — · **Feature:** fast/015.translate-pending-indicator · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** planner (orchestrator default under the user's direction)
- **Question:** Does the visual change bring any change to the flicker's name, enabled state or ARIA attributes?
- **Decision:** No. While pending the flicker is still one button named "Cancel translation" (tooltip and `aria-label`), enabled, pressable to cancel, with no `aria-pressed`, no `aria-busy` and no extra accessible name or second button. The loader glyph is presentational inside the button.
- **Reason:** D15's reasoning about not announcing the same state twice still holds; the change is for sighted users who did not hover.
- **Rejected:** adding `aria-busy` — redundant with the accessible name already saying "Cancel translation".
- **Lands in:** `frontend/src/app/StreamRecord.tsx` (`PartnerFlicker`)
- **Cites:** `ui-conventions.md` `IconLanguage` note and Accessibility floor

### DEC-F015-4 — An entry's actions group is revealed while that entry's translation is pending
- **Status:** accepted
- **Stage:** — · **Feature:** fast/015.translate-pending-indicator · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** planner (orchestrator default under the user's direction)
- **Question:** The flicker sits in a hover-revealed group; how is its pending state seen without hovering?
- **Decision:** `StreamEntry`'s `revealed` becomes the existing conditions (hover, focus-within, no-hover device, editor open) OR "this entry has a translation state and its view is pending". Exactly one `data-revealed` attribute per entry, unchanged; it reads "false" at rest when nothing is pending and returns to "false" once the translation resolves, is cancelled or fails (absent hover/focus). Other entries are unaffected.
- **Reason:** The loader is useless if hidden at opacity 0; revealing the whole group reuses the one reveal mechanism rather than adding a second visible element.
- **Rejected:** a separate always-visible pending marker outside the actions group — adds a second element and a second convention for one state.
- **Supersedes:** narrows `ui-conventions.md`'s hover-reveal paragraph (014 D6) by one extra reveal condition; the mechanism (Mantine hooks, opacity, no stylesheet) is unchanged.
- **Lands in:** `frontend/src/app/StreamRecord.tsx` (`StreamEntry`'s `revealed`)
- **Cites:** `ui-conventions.md` Accessibility floor (hover-reveal); `workspace-shell.md` "Every per-entry action lives inside the entry"
