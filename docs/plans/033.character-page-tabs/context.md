# Feature 033 — character-page-tabs — feature-wide context

## Goal

Redesign the character page (`/characters/:id`) from a single long scroll into a
**tabbed** page, in the user's words:

> "let's redesign the character page: Make it 'tabbed'. tabs:
> 1. Main info. Name, bigger texbox, archive + export as icons with tooltips in main header.
> 2. Configuration — model, prompt, tools.
> 3. Notes. List. '+' icon on header.
> 4. Setups. the same as 3
> 0. Sessions. Default. New session header, then new session textbox - on some visible devider, then previous sessions below. Achive toggle on list header."

Frontend only. **No backend change**: `POST /api/characters/{id}/sessions` already
accepts `setup_id` (optional) and `opening_message` (optional, non-blank) together
and returns `setup_not_found` (404) / `setup_archived` (409) for a bad setup.

## Requirements cited (never restated)

UC-073, UC-074, UC-080, US-096, US-097, US-117 (AC-1..AC-3 hold), US-102 (note
reorder), FEAT-007 (a setup is optional; R2), UC-021.

**Spec conflict, accepted by the user (D10):** US-117.AC-4 and UC-080's
postcondition say the page composer offers no setup choice and the session starts
with none. D8 below contradicts both. **No DoD item cites US-117.AC-4**; the
composer's setup choice is sourced from D8. `outcome.md` routes the amendment to
`/product-spec` and the architect.

## User-confirmed decisions (the plan's source of truth)

- **D1 — tabs.** Order: **Sessions** (default, selected on open), **Main info**,
  **Configuration**, **Notes**, **Setups**. Mantine `Tabs` (first use in the app;
  Mantine only, no new CSS). The active tab is **local component state only** —
  not in the URL, not persisted. Search hits for character/setup memos keep
  landing on plain `/characters/<id>`, i.e. on the Sessions tab.
- **D2 — `keepMounted`** stays at Mantine's default (true): every section still
  mounts and loads **once on page open**, as today. The draft page
  `/characters/new` still renders no tabs and no sections.
- **D3 — page header** (above the tabs): saved-name Title + "Archived" badge +
  **icon-only Archive/Restore and Export** through the shared `IconButton`
  (`IconArchive`, `IconArchiveOff`, `IconDownload`). Export stays busy (disabled)
  while exporting.
- **D4 — Main info tab:** Name `TextInput` (single line, unchanged) + Persona
  `MarkdownEditor` made **substantially taller**. Blur-save unchanged.
- **D5 — Configuration tab:** the existing `CharacterConfigSection`, moved as-is.
- **D6 — Notes tab:** notes as a **list** (layout "list", reorder stays). A '+'
  `IconButton` in the Notes section's **own** header; '+' opens the new-note draft
  **inline at the top of the list** with **Save and Cancel icon buttons**. An
  **opt-in prop on the shared `MemoLevelGroup`** — the session wall
  (`MemoChainSection`) and Settings ("Your notes") keep their labelled "New note"
  button and blur-save.
- **D7 — Setups tab:** '+' `IconButton` in the Setups header (replaces the labelled
  "New setup" button); the "Show archived setups" switch stays in the header. '+'
  opens an **inline create form at the top of the list** (Name + Description) with
  **Save/Cancel icon buttons**; failure inline. Edit stays in `SetupModal`.
- **D8 — Sessions tab**, top to bottom: "New session" heading, the composer with a
  small **Setup `Select`** in one of `ComposerCore`'s slots ("No setup" default,
  working setups as options), a visible `Divider`, then the sessions list whose
  header carries "Sessions", the "Show archived sessions" switch and **"Import
  session" as an icon button** (`IconUpload`, busy while importing). Sending
  creates the session **with the chosen setup and the opening message**.
- **D9 — the message-less start is dropped:** the Sessions section loses its
  inline Setup select, its "Start session" button and the
  `startSessionFromSection` path. Sessions start only by writing a first message.
- **D10** — the spec conflict above.

## Architecture to read (and not edit)

- `docs/architecture/workspace-shell.md` § "The character page" — 018 D12 body
  order (being replaced), 018 D8 same-components rule (still binding: no second
  note card, no second group component), 018 D11 section-local archive toggles
  (still binding), 011 D1 inline start control (being retired).
- `docs/architecture/forms-and-lists.md` — the modal rule and its named
  exceptions; draft-class convention (observable fields only, free-function
  submit, fresh draft per open via conditional mount); never-optimistic; neutral
  empty lines "No setups yet." / "No sessions yet." (both stay).
- `docs/architecture/ui-conventions.md` — `IconButton` (label = tooltip **and**
  accessible name; props deliberately not widened), icon sizes, failure placement
  table.
- `docs/architecture/frontend-structure.md` — MobX rules (no methods/getters,
  free functions, `runInAction`, abort early-return), section-owned stores,
  `src/shared/MarkdownEditor.tsx`, routing (`/characters/:id`, `/characters/new`).

## Cross-cutting constraints

- **TypeScript only** under `frontend/`; Mantine components and style props only —
  no new stylesheet, no CSS selectors (`tests/stylesheets.test.ts` pins the two
  sheets).
- **Every icon-only control goes through `frontend/src/shared/IconButton.tsx`.**
  Its props are `icon`, `label`, `onClick`, `disabled?`, `color?`, `sizeVariant?`
  and are **not widened** by this feature (no `loading`, no ref forwarding). A
  "busy" icon control is expressed as **`disabled` while the operation is in
  flight**. Header/section-header actions use the default `"main"` size.
- **Inline-draft vocabulary (steps 002, 003):** the "Save" icon is
  `IconDeviceFloppy` (the icon table's Save), the "Cancel" icon is `IconX`. Both
  are `IconButton`s. Cancel discards with **no request**. Save and Cancel are
  disabled while the save is in flight. Failures render **inline**, inside the
  draft/form, never as a notification.
- **Section-owned stores stay section-owned** (010 D11); the active tab is
  component state, not a store field.
- Sibling sections in `CharacterScreen` keep **distinct keys** (commit 8f86926
  fixed regions duplicating on every keystroke); the exactly-once region guarantee
  must survive the restructure.
- Ids are strings end to end.

## Files touched across the feature (by step)

| File (under `frontend/`) | Steps |
|---|---|
| `src/app/CharacterScreen.tsx` | 001 |
| `src/shared/MarkdownEditor.tsx` | 001 |
| `src/app/CharacterComposer.tsx` | 001 (heading), 004 |
| `src/app/MemoLevelGroup.tsx`, `src/app/memoLevelState.ts`, `src/app/CharacterNotesSection.tsx` | 002 |
| `src/app/SetupsSection.tsx`, `src/app/SetupCreateForm.tsx` (new) | 003 |
| `src/app/characterComposerState.ts`, `src/app/sessionsApi.ts` | 004 |
| `src/app/SessionsSection.tsx`, `src/app/sessionsSectionState.ts` | 005 |

## Tests — feature-wide notes

- Tests live in `frontend/tests/app/` (Vitest + Testing Library).
- **Mantine `Tabs` with `keepMounted` renders inactive panels hidden**
  (`display: none`). Role queries exclude hidden elements by default, so a test
  that needs a region in an inactive tab must either activate its tab first or
  query including hidden elements. Assert the tab structure by `tab` /
  `tabpanel` roles and `aria-selected`, not by "every region is visible".
- **`frontend/tests/app/CharacterScreen.test.tsx` and
  `frontend/tests/app/App.test.tsx` appear in several steps' Test files lists.**
  Step 001 rewrites the page-structure assertions; each later step lists them only
  so the test-coder can adjust an existing assertion that the step's own change
  invalidates (a renamed control, a removed control, a request count). Source and
  Test lists remain disjoint within every step.
- Commands (root `CLAUDE.md`, run from `frontend/`): `npm test`,
  `npm run typecheck`, `npm run build`.
