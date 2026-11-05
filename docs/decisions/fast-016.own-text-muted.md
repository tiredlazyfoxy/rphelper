# Decisions — fast-016.own-text-muted
**Stage:** — · **Feature:** fast/016.own-text-muted

The roleplayer's own rows in the chat (the current zone, and the read-only
Discussion group that reuses the same row component) render their body in a muted
gray so they read apart from the assistant's rows. The role-aware zone rows are
022 `006`'s contract (US-114.AC-2, US-115.AC-1, US-116.AC-1); the Discussion group
is 022 `007`'s (US-040.AC-1). No story AC covers telling own text from assistant
text; the entries below are a presentation refinement inside the `app` entry.

### DEC-F016-1 — Build the own-text tone in code; no product or architecture change now
- **Status:** accepted
- **Stage:** — · **Feature:** fast/016.own-text-muted · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** user
- **Question:** No story AC requires the roleplayer's own chat text to look different from the assistant's (FEAT-009 / FEAT-010 checked). Should the product spec or architecture be revised before building it?
- **Decision:** No. Build it in code and record it as a technical decision ("it's not so big for the spec"). At finalization `/architect` adds a line to `ui-conventions.md` on the tone of the roleplayer's own text in the chat; the product layer is untouched.
- **Reason:** User decision. It changes how existing rows are shown, not what the product does.
- **Lands in:** `frontend/src/app/ZoneList.tsx`; `docs/architecture/ui-conventions.md` (at finalization)
- **Cites:** US-114.AC-2, US-115.AC-1, US-116.AC-1 (role-aware rows, via 022 `006`); US-040.AC-1 (Discussion group, via 022 `007`)

### DEC-F016-2 — The user-role row body is wrapped in a Mantine `Box` with `c="dimmed"`
- **Status:** accepted
- **Stage:** — · **Feature:** fast/016.own-text-muted · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** user (orchestrator default under the user's direction)
- **Question:** Where and how is the roleplayer's own text made light gray?
- **Decision:** In `ZoneMessage`, the user-role body only: the existing `MessageBody` (variant `"painted"`) is wrapped in a Mantine `Box` with `c="dimmed"`, the theme-aware gray already used by the row's "You" author label, so it follows light and dark colour schemes. The colour inherits into the rendered prose. `MessageBody`'s props are not widened. Assistant and tool bodies and the in-place edit `Textarea` are unchanged. Because `DiscussionGroup` renders its rows through `ZoneMessage` (editable off), user rows in the Discussion group get the same tone — intended, it is the same chat.
- **Reason:** One wrapper at the one place that decides a row's body by role; no shared renderer changes and no stylesheet (two-stylesheet rule, `ui-conventions.md` Accessibility floor / `tests/stylesheets.test.ts`).
- **Rejected:** a colour prop on `MessageBody` — widens a renderer shared with the settled record; a hard-coded gray palette token — not theme-adaptive; styling settled record entries — out of scope (DEC-F016-3).
- **Lands in:** `frontend/src/app/ZoneList.tsx` (`ZoneMessage`)
- **Cites:** `ui-conventions.md` (colour decided in one place; no new stylesheet); 022 `006` Interface intent (`ZoneMessage` body by role)

### DEC-F016-3 — Settled entries, the live reply and accent chips keep their colours
- **Status:** accepted
- **Stage:** — · **Feature:** fast/016.own-text-muted · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** user (orchestrator default under the user's direction)
- **Question:** What else could the tone reach, and does it?
- **Decision:** Settled record entries (turn, decision, partner in `StreamRecord`) are not toned; `LiveMessage` (assistant only) is not toned. Inside a muted user row, the `(( ))` fragment chip and the OOC card keep the explicit accent colours they set themselves — nothing is changed in `MessageBody` for them.
- **Reason:** The request is about the chat with the assistant; the settled record is the document the roleplayer posts and stays at full contrast. The chips already decide their own colour.
- **Lands in:** `frontend/src/app/ZoneList.tsx` (by not touching the others)

### DEC-F016-4 — Test hook: `data-tone="muted"` on the wrapper
- **Status:** accepted
- **Stage:** — · **Feature:** fast/016.own-text-muted · **Step:** —
- **Date:** 2026-11-05 · **Decided by:** planner
- **Question:** How do tests tell a muted body from an unmuted one without binding to a computed colour?
- **Decision:** The wrapper `Box` carries `data-tone="muted"`. Exactly one such element per user row, containing that row's rendered body; assistant and tool rows carry none. The edit `Textarea`, while open, is not inside a muted wrapper.
- **Reason:** The test suites bind to `data-*` markers, not colours; jsdom does not resolve Mantine's theme variables.
- **Lands in:** `frontend/src/app/ZoneList.tsx` (`ZoneMessage`); `frontend/tests/app/ZoneListOwnTextTone.test.tsx`
