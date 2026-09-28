# 018.character-page — Character page
<!-- roadmap:start -->
- **Stage:** 003.assistant · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-020 (UC-073, UC-074, US-096, US-097), FEAT-008 (UC-080, US-117)
- **Depends on:** `017.session-configuration`, `016.note-wall`, `013.stream-and-zone-ui`

## Definition
Brings everything about one character into a single place and makes it the natural place a roleplay begins. The page shows the persona, the character's notes as a grid of the same cards the wall uses, its setups, its resolved configuration and its sessions — two columns instead of three, with no wall beside it, because three of the wall's four levels mean nothing with no session open. Creating a character opens a draft page that persists nothing until something is entered. The page ends with the same composer as the stream's, and writing in it creates a session under the character with a turn already being drafted and the written message as its opening — there is no separate create-session step to press first.

## Scope
**In:**
- the two-column arrangement
- the persona, notes grid, setups list, resolved configuration and sessions list in one body
- the note card, in-place edit and reorder reused unchanged from the wall rather than forked
- the draft page and the rule that nothing persists until there is content
- the shared composer on the page
- the route that creates the session and seeds its zone in one transaction
- the navigation into the workspace once the session exists

**Out:**
- a second note component or a second composer, both explicitly forbidden
- the wall beside this page, which is not shown

## Open questions for the planner
- Whether this composer carries the kind switch or a setup choice. `docs/architecture/workspace-shell.md` records this as open — UC-080 and US-117 do not decide it — and states explicitly that this plan must either choose one or send the question back to `/product-spec`. Both are live options; neither is picked here.
<!-- roadmap:end -->
