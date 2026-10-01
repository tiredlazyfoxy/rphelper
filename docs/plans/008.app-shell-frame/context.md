# Feature 008 — App shell frame · feature-wide context

## What this feature is

Gives the roleplayer the one screen they work in, **as an empty frame**. The `app` entry
stops being a placeholder `<div>`: it learns who is signed in (one `GET /api/me`), mounts a
hand-written CSS grid whose left column collapses to a 48px icon rail and restores, keeps
that collapse across a reload, and puts a user menu at the bottom of the left column with
settings, log out and (administrators only) a real link to the separate `/admin` document.
Below 820px the left column is always the rail, and the rail's expand opens the full
column as an overlay above the centre instead of widening the grid. Nothing is resizable.

The agreed boundary is `brief.md` in this folder. Its Definition and Scope In/Out bound
every step here and are **not** widened. Its two open questions are closed by **D3** and
**D4** below.

## Product ids

`FEAT-020`, via **UC-070** and **UC-071**.

| Criterion | Where it lands |
|---|---|
| US-090.AC-1 (collapsed rail keeps search, create and the user menu reachable) | `004` (the rail renders search, new-character and the reduced user menu) |
| US-091.AC-1 (log out from the menu ends the session and returns to login) | `003` (the logout effect and the menu item) |
| US-093.AC-1 (admin entry point shown to an administrator) | `003` |
| US-093.AC-2 (no admin entry point for a roleplayer) | `003` |

UC-070's "restores" and the brief's "the collapse survives a reload" are carried by
`001` (the persisted record), `002` (the state that writes it) and `004` (the shell that
reads it on mount). They have no AC id of their own beyond US-090.AC-1; the DoD items cite
UC-070.

**Not delivered here:** US-092 (the settings screen's content) is `017`'s — only the menu
item that navigates to `/settings` is in scope. UC-069 / US-088 / US-089 (the tree's
contents) are `011`'s. UC-072 / US-094 / US-095 (the note wall) are `016`'s. My-search's
behaviour (US-118, FEAT-017) is `029`'s — see D4 for the one trigger 008 does render.

## Built state this feature reads (all of 001..007 is built)

| Module | What this feature uses |
|---|---|
| `frontend/src/app/main.tsx` | Today: imports `AppProviders` and `"../shell.css"`, mounts `AppProviders` → `BrowserRouter` → `Routes` with one `path="*"` route rendering `<div data-entry="app" />` on `#root` (throws if `#root` is missing). No `/api/me`, no `basename` — the app's routes are mounted at the origin root. **Rewritten by `005`.** |
| `frontend/src/shell.css` | Exists, comment-only; its header comment says feature 008 fills it. **Filled by `002`.** |
| `frontend/src/shared/api.ts` | `apiGet` / `apiPost` / `apiPatch` / `apiDelete` (path, optional body, optional signal); paths must start `/api/`. **On a 401 the client itself calls `documentNavigation.assign("/login")` and then throws** — no caller ever re-navigates on 401. A 204 resolves to `undefined` without parsing a body. `documentNavigation` (an object with `assign(url)`) is the test seam for every document navigation. |
| `frontend/src/shared/apiError.ts` | `ApiError` (`code`, `status`, `detail`, `message`), `isApiError`. Call sites branch on `.code`, never on `.status`. |
| `frontend/src/shared/notReady.ts` | `isNotReady(error)` — the one not-ready predicate. |
| `frontend/src/shared/notifyFailure.ts` | The **only** importer of `@mantine/notifications` (enforced by `tests/conventions.test.ts`). Takes a thrown value; no success path. |
| `frontend/src/shared/IconButton.tsx` | Props `icon`, `label`, `onClick`, optional `disabled`, `color`, `sizeVariant`. Every icon-only action goes through it. |
| `frontend/src/shared/AppProviders.tsx` | The Mantine wrapper every entry and every component test uses. |
| `frontend/src/admin/adminAccess.ts` | Today defines `CurrentUser` (`id: string`, `username`, `role: "roleplayer" \| "admin"`) and fetches `/api/me` inside `enforceAdminAccess`. **Re-pointed by `001`** (D1). |

Backend surfaces, unchanged by this feature (no backend file is touched):

- `GET /api/me` → `{ id, username, role }`; `id` is a decimal **string**. 401
  `not_authenticated` when there is no session or the account is disabled.
- `POST /api/auth/logout` → always **204**, idempotent, clears the cookie, does **not**
  require a session.

## Commands

From the root `CLAUDE.md` (frontend only — this feature touches no backend file):

```
Frontend (run from frontend/)
  build      npm run build
  test       npm test
  typecheck  npm run typecheck
```

No step may leave the tree failing `tsc --noEmit` (`npm run typecheck`).

## Architecture this binds to

- `docs/architecture/workspace-shell.md` — **"The three columns"** (the grid block, the
  collapse-is-one-class rule, the `1px` gap divider, the rail), **"Geometry"** (252 / 48 /
  820, nothing resizes, where the rules live), **"Layout persistence"** in full, **"The user
  menu"** in full. "The wall has two modes" only for why `wallPinned` exists.
- `docs/architecture/frontend-structure.md` — "Navigation between entries", "The `admin`
  entry" and its **"Boot sequence"** (the five outcomes `005` mirrors), **"State — MobX 6,
  per-page stores, no context"**, "Where a store's file lives", **"Routing inside the `app`
  entry"**, **"The two stylesheets"**, "Ids are strings", the API client.
- `docs/architecture/ui-conventions.md` — Icons (sizing, `IconButton`, the workspace icon
  table), the accessibility floor, **async feedback** (the notification rule), `@mantine/hooks`
  for non-stateful helpers only.
- `docs/product/use-cases/FEAT-020.workspace-shell.md` (UC-070, UC-071),
  `docs/product/stories/FEAT-020.workspace-shell.md` (US-090, US-091, US-093).

Cited, never copied.

## Files this feature touches

```
frontend/
  src/
    shared/currentUser.ts        # NEW — CurrentUser type + the /api/me fetch     (001)
    admin/adminAccess.ts         # re-pointed at shared/currentUser               (001)
    app/workspaceLayout.ts       # NEW — the pure persisted-layout record         (001)
    shell.css                    # filled — grid, --navw, collapse class, 820px   (002)
    app/shellState.ts            # NEW — shell data class + free functions        (002)
    app/logout.ts                # NEW — the logout effect                        (003)
    app/UserMenu.tsx             # NEW — trigger + three items                    (003)
    app/WorkspaceShell.tsx       # NEW — the grid element, tree column / rail     (004)
    app/App.tsx                  # NEW — the in-entry routes inside the shell     (004)
    app/appBootState.ts          # NEW — boot state, classification, probe        (005)
    app/AppBootScreens.tsx       # NEW — not-ready screen + failure panel         (005)
    app/AppBoot.tsx              # NEW — the gate component                       (005)
    app/main.tsx                 # rewritten                                      (005)
  tests/
    shared/currentUser.test.ts, app/workspaceLayout.test.ts,
    app/entryIsolation.test.ts, admin/adminAccess.test.ts (extended)              (001)
    stylesheets.test.ts (one clause replaced), app/shellState.test.ts             (002)
    app/logout.test.ts, app/UserMenu.test.tsx                                     (003)
    app/WorkspaceShell.test.tsx, app/App.test.tsx                                 (004)
    app/appBootState.test.ts, app/AppBoot.test.tsx,
    entries.test.tsx (app clauses)                                                (005)
```

**Not touched; a step that touches one is out of scope:** every file under `backend/`,
`frontend/src/global.css` (resets only — **no colour, no layout**), `frontend/vite.config.ts`,
`frontend/src/app/index.html`, every `frontend/src/shared/*` module other than the new
`currentUser.ts`, every `frontend/src/admin/*` module other than `adminAccess.ts`,
`frontend/tests/conventions.test.ts`, `frontend/tests/ids-are-strings.test.ts`,
`frontend/tests/setup.ts`. No new npm dependency.

## Cross-cutting constraints every step holds

**No context, no methods.** Shell state is a MobX data class with **observable fields
only** (`makeAutoObservable(this, {}, { autoBind: true })`), derivations are pure free
functions taking it, effects are free functions taking it. One instance per shell via
`useState(() => …)`, **never `useMemo`**; passed explicitly as a prop; every component that
reads an observable is an `observer`. The signed-in user travels **as a prop**, never through
React context.

**The `app` entry imports nothing from `src/admin/`.** The bundles are separate on purpose
(`frontend-structure.md`, UC-066's converse). Identity therefore lives in
`src/shared/currentUser.ts` (D1), which names no `/admin` route. Guarded by a test in `001`.

**Cross-entry navigation is a document navigation.** `/admin` and `/login` are other
documents: the admin link is a real `<a href="/admin">`, and logout lands on `/login` via
`documentNavigation.assign`. Neither is ever a router `Link` / `navigate`. In-entry
destinations (`/settings`, `/search`, `/characters/new`) are router navigations.

**Every icon-only control goes through `shared/IconButton`.** Tooltip text and accessible
name are one `label`. Tests find controls by their accessible name; the names fixed in this
plan are the contract.

**Notifications only for failures with no place of their own**, through
`shared/notifyFailure` and nothing else. No success toast anywhere. The boot failures
render as full-page states and raise no notification (D2).

**Ids are strings.** `CurrentUser.id` is `string`; no `parseInt`, no `id: number` anywhere
(`tests/ids-are-strings.test.ts` must keep passing).

**TypeScript only.** No `.js` / `.jsx` / `.mjs` / `.cjs`.

**No two module paths may differ only in letter case.** The filesystem this project is
developed on is case-insensitive; TypeScript's resolver is not. A pair such as `appBoot.ts`
beside `AppBoot.tsx` therefore resolves to the `.tsx` under `tsc` and to the `.ts` under
Vite and Vitest **from the identical specifier**, so the import is `undefined` at runtime
while `npm run typecheck` still passes, and the failure surfaces as React reporting an
`undefined` element type. This is an invariant typecheck cannot enforce; `005`'s DoD-14
guards `src/app/` with a filename scan.

**No wall.** The note wall — its column, overlay, open state and pin control — is `016`'s.
The grid in 008 is `tree | centre`. `wallPinned` is carried in the persisted record (D8)
but nothing in 008 reads or writes it.

## Decisions — settled, with their reasoning

### D1 — Identity moves to `shared/currentUser.ts`

**User decision.** The `CurrentUser` type and the `/api/me` fetch move out of
`admin/adminAccess.ts` into a new `frontend/src/shared/currentUser.ts`; `adminAccess.ts`
imports them from there and **its observable behaviour is unchanged** — same request, same
decisions, same not-ready and failure classification, the existing admin suite still passes.
`adminAccess.ts` keeps re-exporting the `CurrentUser` type so every existing importer
compiles unchanged.

Reason: one definition of the `/api/me` shape, and identity is not admin-specific. The
`app` entry needs it and may not import from `src/admin/`. `shared/` holds generic
infrastructure and must never name an `/admin` route; this module names `/api/me` only.

### D2 — The `app` entry gates on `/api/me`, mirroring admin's boot minus the role deny

**User decision.** Nothing of the shell renders until `GET /api/me` resolves. Outcomes:

```
AppBoot
  └─ GET /api/me
       ├─ in flight                         ──► nothing rendered
       ├─ 401 (code not_authenticated)      ──► nothing of its own — the shared client
       │                                         has already navigated to /login
       ├─ not-ready (shared/notReady)       ──► not-ready screen; re-probe every 2000 ms,
       │                                         plus a manual retry; navigates nothing
       ├─ anything else thrown              ──► failure panel + manual retry; navigates
       │   (incl. a well-formed 403 / 5xx)       nothing
       └─ success, either role              ──► the shell, with the user passed as a prop
```

The pure/impure split is kept: a pure classification of a thrown value (testable with no
network), an effect that probes and writes the outcome into a small MobX boot-state object.
Both screens are full-page states, so **neither raises a notification**
(`ui-conventions.md`). The gate is UX only; the backend's `require_user` is the boundary.

Unlike the admin entry, which runs its loop inside `main.tsx`, the app's gate is a
component (`AppBoot`) that `main.tsx` mounts — the observable behaviour is the same
(nothing visible while probing), and the component form is what makes the five outcomes
testable by mounting it. Recorded in `outcome.md`.

### D3 — Below 820px: always the rail, and expand opens an overlay — brief open question 2, closed

**User decision.** Below the threshold the grid's left track is **always 48px**, regardless
of `navCollapsed`. The rail's expand control opens the full left column **as an overlay
above the centre column** rather than widening the track. It is **the same column and the
same markup** — the nav element renders the expanded content and is lifted out of the track
by a class — **not a third component**.

- The overlay's open state is **not persisted** (the same reasoning as the wall's open
  state: restoring an overlay on load greets the roleplayer with a panel to dismiss).
- At narrow width `navCollapsed` is **neither read nor written**. Collapsing a wide layout,
  narrowing the window, expanding the overlay and widening again returns the wide layout
  the roleplayer last chose.
- **The CSS media query in `shell.css` is the layout authority.** JS needs to know the width
  only to decide what expand / collapse *mean*, and uses Mantine's `useMediaQuery` with the
  **identical query string** (D12). This is a user-sanctioned use of `@mantine/hooks`.

### D4 — The rail's create is "New character"; the rail's search is a plain trigger — brief open question 1, closed

**User decision.** The rail's create action addresses **characters only** — `IconPlus`,
label **"New character"** — and is an in-entry router navigation to `/characters/new`. It is
not a menu: `009` (sessions) has not shipped, and a session is started from a character's
page (UC-080), so "new character" is the one creation the rail can honestly offer.

The rail also renders the search trigger — `IconSearch`, label **"Search"** — as an in-entry
router navigation to `/search`. **Only the trigger**: US-090.AC-1 requires search to be
reachable from the rail, and `workspace-shell.md` puts the trigger in the rail's markup.
What my-search *does* (query entry, results) is `029`'s, which may replace the trigger's
action. This narrows the brief's Out item "my-search on the rail (`029`)" to "my-search's
behaviour" — the orchestrator was told.

The expanded column in 008 carries **only** its collapse control and the user-menu footer:
the tree's header (where search and create also sit when expanded) is part of the tree's
contents, which are `011`'s.

### D5 — All six routes are declared now, each an empty centre in the same shell

**User decision.** `App` declares `/`, `/sessions/:id`, `/characters/:id`,
`/characters/new`, `/settings`, `/search` — flat `<Routes>`, the shell rendered **above**
them (the admin entry's shape), no layout route, no `<Outlet/>`. Each route's element is an
**empty centre column** — no placeholder text pretending a feature exists. A catch-all `*`
renders, inside the same shell, a centre column saying **"Page not found"**.

`/characters/new` is declared before `/characters/:id` only for readability — React Router
7 ranks static segments above dynamic ones. Later features fill the centre: `009`, `011`,
`013`, `017`, `018`, `029`.

### D6 — The user menu

**User decision.** Bottom-left, the footer of the left column, a Mantine `Menu` opening
**upward** (a `top-*` position). The trigger shows an avatar plus the username when the
column is expanded, the avatar alone on the rail; its accessible name is **"User menu"** in
both states. Three items, in this order:

| Item | Icon | Action |
|---|---|---|
| **Settings** | `IconSettings` | in-entry router navigation to `/settings` |
| **Admin area** | `IconShield` | a real `<a href="/admin">` — **rendered only when `role === "admin"`**; absent, not disabled, for a roleplayer (US-093.AC-2) |
| **Log out** | `IconLogout` | D7 |

The admin item **must never become a router `Link`**: `/admin` is another document with
its own router (`frontend-structure.md`, "Navigation between entries"), and an anchor is
what makes middle-click work.

### D7 — Logout: post, then navigate; on failure, notify and stay

`apiPost("/api/auth/logout")`, then `documentNavigation.assign("/login")`.

**On failure the roleplayer is told and stays where they are** — `notifyFailure(error)`,
no navigation. Reasoning: the endpoint is idempotent and always answers 204, so a failure
is a transport failure or a 5xx, and in both cases the cookie very probably still exists.
Navigating to `/login` anyway would *look* like a logout while leaving the session live,
which contradicts US-091.AC-1 ("their session ends"). A failure from a menu item has no
place of its own to render in once the menu closes, which is exactly the condition
`ui-conventions.md` reserves the notification channel for. The roleplayer can press it
again; the endpoint is idempotent. (A 401 cannot occur — the route requires no session —
and if one did, the shared client would already be navigating to `/login`.)

### D8 — The persisted record: `src/app/workspaceLayout.ts`, pure and DOM-free

**User decision**, binding `workspace-shell.md`'s "Layout persistence" exactly:

- Key **`rphelper.workspace-layout`**; record `{ navCollapsed: boolean; wallPinned: boolean }`;
  defaults **`navCollapsed: false`, `wallPinned: false`**.
- **Read is total and never throws**: absent key, unparseable JSON, a non-object payload,
  wrong field types, missing fields, and a storage whose `getItem` itself throws each fall
  back **per field** to that field's default. Always a complete record; never `null`.
- **Unknown stored keys are tolerated and ignored**, `asideWidth` and `answerBoxHeight`
  named explicitly — never rejected, never allowed to fail the parse.
- **Write is best-effort**: a patch of either field, merged over a **fresh total read**,
  serialised and stored inside a swallowed `try` / `catch`. Because the read is total and
  carries the two known fields only, **a write drops unknown keys** — the stale
  `asideWidth` of an old install disappears on the first toggle. Stated so it reads as
  intended.
- **DOM-free by parameter**: both functions take the storage as an argument — a minimal
  interface with `getItem` and `setItem` — or `null` when no storage is available (read →
  defaults, write → no-op). The module touches no `window`, no `document`, no React, so
  every fallback path is a plain unit test.
- `wallPinned` is carried and round-trips through a write of `navCollapsed`; **nothing in
  008 writes it** (`016` will).

### D9 — Shell state: a MobX data class, written on the toggle

**User decision.** The shell's state (the persisted `navCollapsed`, the non-persisted
overlay-open flag) is a data class with observable fields only, plus free functions in the
same module (`src/app/shellState.ts`). Collapse is **a class on the `.app` grid element**
re-pointing `--navw`; the persisted record is written **on the toggle**, and only on a
toggle that changes `navCollapsed` (D3: overlay open/close never writes).

### D10 — The collapse glyph stays `_TBD:`, with a provisional choice

`ui-conventions.md`'s workspace icon table leaves "Collapse the tree" as
`_TBD: glyph is a left chevron against a right-hand bar_`. **Carried forward, not
resolved.** As a **glyph choice under that `_TBD:`**, the coder uses `IconChevronLeft` —
a left chevron, per the mockup — and the control's label is fixed as **"Collapse tree"**.
No test asserts the glyph; tests find the control by its label. `outcome.md` asks the
architect to settle the glyph. Expand from the rail is `IconMenu2`, label **"Expand tree"**
(settled in the icon table).

### D11 — Dismissing the overlay: its own collapse control, or any in-entry navigation

Minimal and stated: the overlay is closed by **(a)** the expanded column's "Collapse tree"
control — the same control, which at narrow width closes the overlay instead of writing
`navCollapsed` — and **(b)** any change of the in-entry route (choosing Settings, a rail
action, a future tree row). It also closes whenever the viewport crosses the threshold in
either direction, so a stale open flag can never reappear. **No click-outside dismissal and
no backdrop** — one more interaction to test for no requirement asking for it; flip
condition: the roleplayer asks for it.

### D12 — The threshold is one string, written twice

The media query is **`(width < 820px)`** — range syntax, so the literal `820px` from
`workspace-shell.md` appears verbatim and "below 820px" means strictly below. The same
string is the `@media` condition in `shell.css` and the query `useMediaQuery` receives
(exported as one constant from `shellState.ts`). Not a Mantine breakpoint token —
`workspace-shell.md` records why `md` would be wrong.

### D13 — The 401 code is `not_authenticated` — verified

D2's 401 branch is keyed on the backend code **`not_authenticated`**, not on `.status` —
the client's branch-on-code rule. **Verified from source:** `NotAuthenticatedError` in
`backend/app/errors.py:111-120` has `code = "not_authenticated"` and HTTP 401, and is raised
by `require_user`, which `GET /api/me` depends on.

### D14 — Five steps

Sized against the 50–200 LoC budget. The briefing's band 1 (identity, ~35 LoC) is below the
floor and is merged with band 2 (persistence) into `001` — both are foundation modules with
no dependency between them. The briefing's band 3 (CSS + frame) would exceed 200 with the
narrow overlay, so it is cut into `002` (stylesheet + state, no component) and `004`
(the component and the routes); the user menu (`003`) is ordered before the shell because
the shell renders it.

## Vocabulary

| Term | Means here |
|---|---|
| **the shell** | the `.app` grid element and its two columns; rendered on every in-entry route |
| **the left column / nav column** | the grid's first track; renders either the expanded column or the rail |
| **expanded column** | the left column at 252px: collapse control on top, an empty body (`011` fills it), the user menu as footer |
| **the rail** | the left column at 48px: search, new character, expand; the user menu reduced to its avatar as footer |
| **the overlay** | below 820px only: the expanded column lifted above the centre, the track staying 48px |
| **narrow / wide** | viewport matching / not matching `(width < 820px)` |
| **the record** | the persisted `WorkspaceLayout` under `rphelper.workspace-layout` |
| **the centre column** | the grid's second track; empty in 008 except for the 404 text |

## Step map

| Step | Subject | Depends on |
|------|---------|------------|
| 001 | `shared/currentUser.ts` + admin gate re-pointed; `app/workspaceLayout.ts` | — |
| 002 | `shell.css` rules; `app/shellState.ts` (data class, derivations, toggles, storage accessor) | 001 |
| 003 | `app/logout.ts` + `app/UserMenu.tsx` | 001 |
| 004 | `app/WorkspaceShell.tsx` (grid element, expanded column / rail, overlay) + `app/App.tsx` (routes) | 002, 003 |
| 005 | `app/appBootState.ts`, `app/AppBootScreens.tsx`, `app/AppBoot.tsx`, `app/main.tsx` rewrite | 001, 002, 004 |

## Test conventions inherited

Vitest configured inside `frontend/vite.config.ts` (`environment: "jsdom"`,
**`globals: false`** — `describe` / `it` / `expect` / `vi` are explicit imports from
`"vitest"`). Tests live under `frontend/tests/` mirroring `src/` — `tests/app/` is new in
this feature, `tests/shared/` and `tests/admin/` exist. Named `*.test.ts` / `*.test.tsx`;
each `it` title ends **`— DoD-N`** of its own step. `tests/setup.ts` polyfills
`matchMedia`, `ResizeObserver` and `scrollIntoView` and cleans up after each test.
`@testing-library/react`, `/jest-dom` and `/user-event` are available; **`fetch` is stubbed
per test with `vi.stubGlobal`**, no network-mocking library. Document navigations are
asserted through the `documentNavigation` seam in `shared/api.ts`. A component test
rendering Mantine wraps in `shared/AppProviders`; one that needs a router wraps in a
`MemoryRouter`. Tests assert rendered behaviour, never internal structure.
