# Feature 008 — App shell frame · outcome

Intended changes to `docs/architecture/` once this feature ships, for the architect to
apply at finalization. Grouped by target file. Decisions referenced as D-n are in this
folder's `context.md`.

## `docs/architecture/workspace-shell.md`

| Section | Intended change | Reason |
|---|---|---|
| "The three columns" | Record the narrow behaviour as built: below 820px the left track is always 48px; the rail's expand lifts the **same** nav column out of the track as an overlay above the centre (class `nav-overlay-open` on `.app`); the overlay's open state is not persisted; `navCollapsed` is neither read nor written at that width; dismissal is the column's own collapse control, any in-entry navigation, or crossing the threshold — no click-outside, no backdrop (D3, D11). | Closes `brief.md`'s open question 2; the doc says only "the tree becomes an off-canvas overlay". |
| "The three columns" — the rail paragraph | Record that the rail's create is **"New character"** only (`IconPlus`, router navigation to `/characters/new`), not a menu, and that 008 ships the search trigger as a router navigation to `/search` whose behaviour `029` owns (D4). | Closes `brief.md`'s open question 1; records the split between the trigger (008) and my-search (029). |
| "The three columns" — the CSS block | Add the as-built rules beside the two shown: the `.app-nav` / `.app-main` column classes, `.app-main` placed explicitly in track 2 (so it keeps its track when the nav column is lifted), the divider colour as a Mantine CSS variable, the `transition` on `grid-template-columns`, and the media query written as `(width < 820px)` (D12). | The doc's block is a two-rule sketch; the explicit track placement is a non-obvious load-bearing rule of the same kind as `minmax(0, 1fr)`. |
| "Geometry" — "Where these rules live" | Name the five selectors `shell.css` holds and state that column backgrounds, padding and shadow are Mantine style props, not stylesheet rules. | Makes the "layout only" boundary checkable, as `tests/stylesheets.test.ts` now checks it. |
| "Layout persistence" | Record the as-built module `src/app/workspaceLayout.ts`, the storage passed as a parameter (a `getItem` / `setItem` interface, or `null`), that a throwing `getItem` is one of the per-field fallback cases, and that **a write drops unknown keys** because it serialises the total read (D8). | The doc says "pure, DOM-free" but not how a module that persists to `localStorage` stays DOM-free; the key-dropping consequence should read as intended. |
| "The user menu" | Record the trigger (avatar + username expanded, avatar alone on the rail, accessible name "User menu"), the upward position, and the logout failure posture — notify through `notifyFailure` and stay, never navigate on failure (D6, D7). | The doc lists the items but not the trigger or the failure path. |

## `docs/architecture/frontend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| "The multi-entry build" — the `shared/` comment | Add `currentUser` (the `CurrentUser` type and the `/api/me` fetch) to the list of `shared/` modules (D1). | New shared module; identity is now consumed by two entries. |
| "The `admin` entry" — "Boot sequence" | Note that `adminAccess.ts` obtains the user through `shared/currentUser.ts`; behaviour unchanged. | Keeps the gate's description pointing at where the fetch lives. |
| New subsection under the entries — "The `app` entry" | Record the app's boot sequence as built: one `/api/me` before the shell, the five outcomes of D2 (nothing in flight; 401 → nothing of its own; not-ready → screen, 2000 ms re-probe + manual retry; anything else → failure panel + manual retry; success either role → the shell with the user as a prop), the 401 branch keyed on `not_authenticated`, and that the gate is a component (`AppBoot`) mounted by `main.tsx` rather than a loop inside `main.tsx` (D2, D13). | `bootstrap`, `login` and `admin` each have such a subsection; `app` now has a boot sequence and none is written down. |
| "Routing inside the `app` entry" | Record that all six routes are declared, flat, with the shell rendered above `<Routes>`, each centre empty until its feature lands, plus a catch-all 404 inside the shell (D5). | The route list is design; this records that it is now built and that the 404 is inside the shell. |
| "State — MobX 6" / `ui-conventions.md`'s `@mantine/hooks` rule | Record `useMediaQuery` with the shared `NARROW_VIEWPORT_QUERY` constant as a sanctioned `@mantine/hooks` use: it reads the environment and drives no domain state; the CSS media query stays the layout authority (D3, D12). | `ui-conventions.md` says hooks are for non-stateful helpers only; this use needs to read as decided, not as a slip. |
| Conventions — a new rule beside "TypeScript only" | Record as a project convention that **no two module paths may differ only in letter case**. Reason to state: the development filesystem is case-insensitive while TypeScript's resolver is not, so from one extensionless specifier `tsc` picks the `.tsx` and Vite / Vitest pick the `.ts`, giving an `undefined` import at runtime with a green typecheck. Worked example: the near-miss `src/app/appBoot.ts` beside `src/app/AppBoot.tsx`, which is why the boot-state module ships as `appBootState.ts`. Note the escape that is *not* available — `allowImportingTsExtensions` is set in neither tsconfig. | An invariant `npm run typecheck` cannot enforce, and the symptom (React reporting an `undefined` element type) points nowhere near the cause. It has to be written where the next feature's planner reads it; `005`'s DoD-14 only guards `src/app/`. |

## `docs/architecture/ui-conventions.md`

| Section | Intended change | Reason |
|---|---|---|
| Workspace icon table — "Collapse the tree" | Settle the glyph. 008 ships `IconChevronLeft` as a **provisional glyph choice under the carried `_TBD:`** (D10); the architect either confirms it or names the Tabler icon that matches "a left chevron against a right-hand bar" (`IconLayoutSidebarLeftCollapse` is a candidate). Record the label "Collapse tree". | The `_TBD:` is still open; 008 needed a glyph to ship. |
| Workspace icon table | Add the rail's labels as built: "Search" (`IconSearch`), "New character" (`IconPlus`), "Expand tree" (`IconMenu2`). | Labels are the accessible names tests bind to. |
| "Every icon-only action goes through a shared `IconButton`" | Note the user-menu trigger is an avatar button with a fixed accessible name, not an `IconButton` — it wraps no Tabler icon, so the rule does not reach it. | Avoids a reviewer "fixing" it into an `IconButton`. |
| "Async feedback" | Add logout's failure as a worked example of a failure with no place of its own (a menu item that has closed) → `notifyFailure` (D7). | A second concrete call site makes the rule's boundary easier to apply. |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Geometry / paths | Add `rphelper.workspace-layout`'s module path, the `(width < 820px)` query string, and the `shell.css` class names. | Quick lookups agents will need when `011`, `013` and `016` extend the shell. |

## Carried forward, not resolved

- `_TBD:` — the collapse-tree glyph (above).
- `_TBD:` — `frontend-structure.md`'s placement of the archive toggle: 008 renders no tree,
  so it does not place it; still `011` / the character page's to place.


## Observations

- Step 002: the divider colour the planner left as "a Mantine CSS variable" is as built
  `var(--mantine-color-default-border)`, the only colour reference in `shell.css`. Possible
  impact: name that token in `workspace-shell.md`'s "The three columns" CSS block alongside
  the overlay rule, so a later stylesheet edit does not reintroduce a literal.

- Step 003: `UserMenu`'s Settings item is the tree's first imperative in-entry navigation —
  `useNavigate()` behind a `Menu.Item`'s `onClick`, where every existing in-entry navigation
  under `src/` is declarative (`component={Link} to=…`). A menu item that also carried an
  `href` would read as a cross-entry link and sit one attribute away from the admin item it
  is deliberately unlike. Possible impact: record in `frontend-structure.md`'s "Routing
  inside the `app` entry" that `useNavigate` is the accepted form when the navigation is a
  consequence of choosing a control rather than a link, so the declarative-only reading of
  the existing code is not mistaken for a rule.

- Step 004: `workspace-shell.md` says column backgrounds are Mantine style props but names
  no token, and there was no precedent under `src/` — the shell's two columns are as built
  `bg="var(--mantine-color-body)"`, which is what makes the `1px` gap read as a divider.
  Possible impact: name that token beside `var(--mantine-color-default-border)` in "The
  three columns", so the gap-as-divider rule states both halves of the pair.

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B3 (the frontend layer — `workspace-shell.md`, `frontend-structure.md`, `ui-conventions.md`, `forms-and-lists.md`).
Rejected items: none
Notes: Three `## Observations` were applied as conventions — the two colour tokens behind the gap-as-divider rule, and `useNavigate` as the accepted form when navigation follows from choosing a control. The collapse-tree glyph `_TBD:` is closed on `IconChevronLeft` as built, with `IconLayoutSidebarLeftCollapse` recorded as the rejected alternative, and the case-collision convention (no two module paths differing only in letter case) is recorded where a planner reads it.
