# Fast feature 015 — translate-pending-indicator — outcome

Intended documentation changes, applied at finalization.

## Product

## Architecture

- **`ui-conventions.md`, Icon conventions — the `IconLanguage` / flicker note.**
  - **Change:** the "one icon, state carried by the label, not two glyphs" rule
    gains one exception: while a translation is pending, the flicker shows a
    spinning progress indicator in place of the language glyph. The label, the
    no-pressed-state rule, the translated colour and the unwidened shared button
    stay as they are; the control stays pressable to cancel.
  - **Reason:** user report — a translation queued behind a long generation looked
    like a button that switched with nothing happening; the label-only signal is
    invisible without hovering.
- **`ui-conventions.md`, Accessibility floor — the hover-reveal paragraph.**
  - **Change:** the stream's per-entry actions group is also revealed while that
    entry's translation is pending, not only on hover, focus, touch devices or an
    open editor. The mechanism (component hooks, opacity, no stylesheet) is
    unchanged.
  - **Reason:** a pending indicator hidden with the rest of the group would not be
    seen.

## Decisions

- DEC-F015-1 — Build the pending indicator in code; no product or architecture change now (user).
- DEC-F015-2 — While pending, the flicker's glyph is a spinning loader instead of the language icon; narrows 023 D15 for pending only.
- DEC-F015-3 — Label and accessibility semantics are unchanged while pending.
- DEC-F015-4 — An entry's actions group is revealed while that entry's translation is pending.

## Observations

_appended by coder / fixer / reviser; each bullet tagged [product] | [architecture] | [decision]_
