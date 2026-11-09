# Fast feature 016 — own-text-muted — outcome

Intended documentation changes, applied at finalization.

## Product

## Architecture

- **`ui-conventions.md` — a line on the tone of the roleplayer's own text in the chat.**
  - **Change:** in the chat with the assistant (the current zone and the read-only
    Discussion group under settled entries), the roleplayer's own messages are shown
    in the theme's muted text tone, so they read apart from the assistant's; the
    assistant's and tool rows keep normal contrast, inline accent chips keep their
    own colours, and the settled record is not toned. Done with component props, no
    stylesheet.
  - **Reason:** user request — own and assistant text were hard to tell apart.

## Decisions

- DEC-F016-1 — Build the own-text tone in code; no product or architecture change now (user).
- DEC-F016-2 — The user-role row body is wrapped in a Mantine `Box` with `c="dimmed"`.
- DEC-F016-3 — Settled entries, the live reply and accent chips keep their colours.
- DEC-F016-4 — Test hook: `data-tone="muted"` on the wrapper.

## Observations

_appended by coder / fixer / reviser; each bullet tagged [product] | [architecture] | [decision]_
