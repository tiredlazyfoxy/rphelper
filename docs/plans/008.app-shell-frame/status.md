# Feature 008 — app-shell-frame

| Step | File                                    | Status  | Verifier | Date |
|------|-----------------------------------------|---------|----------|------|
| 001  | `001.identity-and-layout-record.md`     | done    | PASS     | 2026-10-01 |
| 002  | `002.shell-stylesheet-and-state.md`     | done    | PASS     | 2026-10-01 |
| 003  | `003.user-menu.md`                      | done    | PASS     | 2026-10-01 |
| 004  | `004.workspace-shell-and-routes.md`     | done    | PASS     | 2026-10-01 |
| 005  | `005.app-boot-gate.md`                  | done    | PASS     | 2026-10-01 |

## Files Changed

### Step 001 — Shared identity and the persisted layout record

- `frontend/src/shared/currentUser.ts` — `fetchCurrentUser` implemented as one
  `apiGet<CurrentUser>("/api/me", signal)` through the shared client, with no error
  handling of its own; the `CurrentUser` type is now defined only here.
- `frontend/src/admin/adminAccess.ts` — no edit needed: the skeleton had already
  re-pointed `enforceAdminAccess` at `fetchCurrentUser` and dropped `apiGet` / `ME_PATH`;
  filling `fetchCurrentUser` makes that re-point true with its behaviour unchanged.
- `frontend/src/app/workspaceLayout.ts` — `readWorkspaceLayout` implemented as a total,
  never-throwing read (null storage, throwing `getItem`, absent key, unparseable JSON,
  non-plain-object payload incl. `null` and arrays, and wrong-typed or missing fields each
  fall back per field; unknown keys ignored; result carries exactly the two fields);
  `writeWorkspaceLayout` merges the patch over a fresh read of the same storage, stores the
  two-field JSON under `rphelper.workspace-layout`, swallows every throw and no-ops on a
  null storage. Module still imports nothing and names no DOM global.

### Step 002 — `shell.css` and the shell state

- `frontend/src/shell.css` — filled with layout only: the `.app` grid (`display: grid`,
  `gap: 1px`, `grid-template-columns: var(--navw, 252px) minmax(0, 1fr)`, `height: 100vh`,
  `background: var(--mantine-color-default-border)` as the divider line, a transition on
  `grid-template-columns`), `.app.nav-collapsed` setting `--navw: 48px` and nothing else,
  `.app-nav` / `.app-main` each scrolling on their own with `.app-main` pinned to track 2
  at a zero minimum width, and `@media (width < 820px)` forcing `--navw: 48px` plus
  `.app.nav-overlay-open .app-nav` lifting the same nav column out of flow (`position:
  fixed`, left/full-height, `width: 252px`, `z-index: 100`). No colour literal, no font or
  typography property, no `@import` / `@font-face`, no selector beyond those five; the
  header comment now describes what the file holds.
- `frontend/src/app/shellState.ts` — bodies filled behind the frozen signatures:
  `createShellState` seeds `navCollapsed` from `readWorkspaceLayout(storage)` with the
  overlay closed; `showsRail` and `shellClassName` are pure (`app`, `nav-collapsed`,
  `nav-overlay-open` only when narrow and open); `expandTree` / `collapseTree` open or
  close the overlay at narrow width and write nothing, and at wide width set
  `navCollapsed` and `writeWorkspaceLayout` that one field (so `wallPinned` survives via
  the write's fresh read); `closeOverlay` closes the overlay only; `browserLayoutStorage`
  returns `window.localStorage` or `null` when the getter itself throws. Every observable
  write is inside `runInAction`; the class still has no methods and no getters.

### Step 003 — The user menu and logout

- `frontend/src/app/logout.ts` — `logOut` filled: one `apiPost("/api/auth/logout")` with no
  body through the shared client, then `documentNavigation.assign("/login")`; any throw goes
  to `notifyFailure(error)` with no navigation and no rethrow; an aborted signal (before or
  during the post) neither navigates nor notifies. A private `isAborted(signal)` helper reads
  the flag through a call so the compiler does not narrow it across the `await`. Names no
  `fetch`, no `window.location`, no `@mantine/notifications`.
- `frontend/src/app/UserMenu.tsx` — `UserMenu` filled as a plain function component: a
  `Menu position="top-start" withinPortal`; the trigger is an `UnstyledButton` with
  `aria-label="User menu"` holding an `Avatar` of the username's upper-cased initial plus,
  when `compact` is false, the username as `Text`; the dropdown holds Settings
  (`IconSettings`, `useNavigate("/settings")`), Admin area (`IconShield`,
  `Menu.Item component="a" href="/admin"` with no click handler, rendered only when
  `user.role === "admin"`) and Log out (`IconLogout`, `void logOut()`), in that order. Item
  icons at the inline size `16` / stroke `1.5`; no MobX state, no context, no `src/admin/`
  import.

### Step 004 — The workspace shell component and the in-entry routes

- `frontend/src/app/WorkspaceShell.tsx` — the `.app` grid element written as a plain `div`
  with `shellClassName(shell, narrow)` and exactly two children: a Mantine `Box
  component="nav"` with class `app-nav` and accessible name "Workspace navigation", and a
  `Box component="main"` with class `app-main` holding `children`. The one `ShellState`
  comes from `useState(() => createShellState(storage))`; narrow is
  `useMediaQuery(NARROW_VIEWPORT_QUERY, false, { getInitialValueInEffect: false }) ?? false`.
  The nav renders the rail (`IconButton`s "Search" → `navigate("/search")`, "New character"
  → `navigate("/characters/new")`, "Expand tree" → `expandTree`, then `UserMenu compact`)
  when `showsRail(shell, narrow)`, otherwise the expanded column ("Collapse tree" →
  `collapseTree` at the top, an empty `flex` body for 011, `UserMenu compact={false}` as the
  footer). Two `useEffect`s call `closeOverlay` — one keyed on `location.key`, one on
  `narrow` (D11). Both columns carry `bg="var(--mantine-color-body)"` so the `.app`
  background shows only through the `1px` gap. No wall column, no wall control, no
  `data-entry` marker.
- `frontend/src/app/App.tsx` — renders `WorkspaceShell` (user and storage passed through)
  around one flat `<Routes>`: `/`, `/sessions/:id`, `/characters/new`, `/characters/:id`,
  `/settings`, `/search` each `element={null}` (an empty centre), plus `*` rendering a
  Mantine `Text` reading "Page not found". No layout route, no `<Outlet/>`, no `basename`,
  no router of its own.

### Step 005 — The boot gate and the `app` entry's mount

- `frontend/src/app/appBootState.ts` — `classifyAppBootError` implemented as a pure
  three-way branch (an `ApiError` with code `not_authenticated` → `"unauthenticated"`,
  `isNotReady` → `"not-ready"`, everything else — a well-formed 403 or 5xx envelope, a
  non-`ApiError` — → `"failed"`); `probeCurrentUser` runs one `fetchCurrentUser(signal)`
  and writes `"ready"` plus the user on success or the classified outcome on failure, inside
  `runInAction`, returning without a write once the signal is aborted and never rethrowing,
  and never setting `"probing"` itself; `restartBoot` sets `status` back to `"probing"`.
  Imports nothing from `src/admin/` and names no DOM global.
- `frontend/src/app/AppBootScreens.tsx` — both full-page states written as Mantine
  `Container`/`Stack`/`Title`/`Text`/`Button`: `AppNotReady` with the title "RPHelper is not
  ready yet", the line "The server is not answering yet. Retrying automatically." and a
  "Retry now" button; `AppBootFailed` with the title "Could not load your account" and a
  "Retry" button. Neither imports `shared/notifyFailure` or `@mantine/notifications`.
- `frontend/src/app/AppBoot.tsx` — the gate: one `AppBootState` via `useState(() => …)`, one
  mount effect that owns an `AbortController`, the probe loop and the re-probe timer, and a
  render that maps status to output — `"probing"`/`"unauthenticated"` → `null` (no
  navigation of its own; the shared client has already gone to `/login`), `"not-ready"` →
  `AppNotReady` whose "Retry now" re-probes at once, `"failed"` → `AppBootFailed` whose
  "Retry" calls `restartBoot` then re-probes, `"ready"` → `App` with the user and the
  storage. The 2000 ms re-probe is armed **from each probe's completion** (not from an
  effect keyed on `status`, which a not-ready → not-ready outcome never changes); an
  in-flight flag keeps two probes from overlapping, the timer is cleared at the start of
  every probe and on unmount, and the unmount also aborts the controller so a late response
  writes nothing.
- `frontend/src/app/main.tsx` — rewritten: `AppProviders` → `BrowserRouter` (still no
  `basename`) → `AppBoot` with `storage` from one `browserLayoutStorage()` call at mount.
  The `Routes`/`Route` placeholder rendering `<div data-entry="app" />` is gone; the
  `"../shell.css"` import and the throwing `#root` lookup are kept.

## Skeleton

### Step 001 — frozen interface

`frontend/src/shared/currentUser.ts` (new)

- `export type CurrentUser = { id: string; username: string; role: "roleplayer" | "admin" };`
- `export async function fetchCurrentUser(signal?: AbortSignal): Promise<CurrentUser>` — unimplemented body

`frontend/src/admin/adminAccess.ts` (changed)

- `export type { CurrentUser } from "../shared/currentUser";` — the own declaration removed, type re-exported (`isolatedModules` requires the `export type` form); every existing importer, including `tests/admin/adminAccess.test.ts`'s `type CurrentUser` import, compiles unchanged
- `export async function enforceAdminAccess(signal?: AbortSignal): Promise<AdminAccessResult>` — signature unchanged; the one call site now `await fetchCurrentUser(signal)` instead of `apiGet<CurrentUser>(ME_PATH, signal)`. The unused `apiGet` import and the unused private `const ME_PATH` were dropped (`noUnusedLocals`). `resolveAdminAccess`, `classifyAdminAccessError`, `failureMessage`, `AdminAccessDecision`, `AdminAccessResult`, `ADMIN_ACCESS_RETRY_INTERVAL_MS` untouched.

`frontend/src/app/workspaceLayout.ts` (new — imports nothing)

- `export type WorkspaceLayout = { navCollapsed: boolean; wallPinned: boolean };`
- `export type LayoutStorage = { getItem(key: string): string | null; setItem(key: string, value: string): void };`
- `export const WORKSPACE_LAYOUT_KEY = "rphelper.workspace-layout";` — real value
- `export const DEFAULT_WORKSPACE_LAYOUT: WorkspaceLayout = { navCollapsed: false, wallPinned: false };` — real value
- `export function readWorkspaceLayout(storage: LayoutStorage | null): WorkspaceLayout` — unimplemented body
- `export function writeWorkspaceLayout(storage: LayoutStorage | null, patch: Partial<WorkspaceLayout>): void` — unimplemented body

Notes: unimplemented bodies are `throw new Error("not implemented")`, preceded by `void <param>;` statements only so `noUnusedParameters` passes — the coder replaces the whole body and the `void` lines. Because `enforceAdminAccess` now routes through the unimplemented `fetchCurrentUser`, the existing `tests/admin/adminAccess.test.ts` clauses are red until the coder fills that body (expected at the red gate; DoD-3 is satisfied at the verify run).

Caller-compile edits (out of Source-files scope): None.

`npm run typecheck` passes.

### Step 002 — frozen interface

`frontend/src/app/shellState.ts` (new — imports `makeAutoObservable` from `mobx` and `type { LayoutStorage }` from `./workspaceLayout`)

- `export const NARROW_VIEWPORT_QUERY = "(width < 820px)";` — real value (D12); the same string must appear verbatim in `shell.css`
- `export class ShellState { navCollapsed: boolean; overlayOpen = false; constructor(navCollapsed: boolean) { this.navCollapsed = navCollapsed; makeAutoObservable(this, {}, { autoBind: true }); } }` — real shape: observable fields only, no methods, no getters
- `export function createShellState(storage: LayoutStorage | null): ShellState` — unimplemented body
- `export function showsRail(shell: ShellState, narrow: boolean): boolean` — unimplemented body
- `export function shellClassName(shell: ShellState, narrow: boolean): string` — unimplemented body
- `export function expandTree(shell: ShellState, narrow: boolean, storage: LayoutStorage | null): void` — unimplemented body
- `export function collapseTree(shell: ShellState, narrow: boolean, storage: LayoutStorage | null): void` — unimplemented body
- `export function closeOverlay(shell: ShellState): void` — unimplemented body
- `export function browserLayoutStorage(): LayoutStorage | null` — unimplemented body

`frontend/src/shell.css` — **no frozen interface**: a stylesheet carries no signature. Left exactly as built (its existing header comment only); the coder writes DoD-1..6's rules. Nothing imports it beyond the existing `src/app/main.tsx:5`.

Notes: unimplemented bodies use the house form — `void <param>;` lines then `throw new Error("not implemented")`. `runInAction`, `readWorkspaceLayout` and `writeWorkspaceLayout` are deliberately **not** imported yet (`noUnusedLocals` would fail); the coder adds those imports with the bodies. `ShellState`'s constructor assigns its one parameter because `strict`'s `strictPropertyInitialization` requires it — that assignment is shape, not behaviour.

Caller-compile edits (out of Source-files scope): None — `shellState.ts` is new and has no importer until `004`.

`npm run typecheck` passes.

### Step 003 — frozen interface

`frontend/src/app/logout.ts` (new — imports nothing)

- `export async function logOut(signal?: AbortSignal): Promise<void>` — unimplemented body

`frontend/src/app/UserMenu.tsx` (new — imports `type * as React` from `react` and `type { CurrentUser }` from `../shared/currentUser`)

- `export type UserMenuProps = { user: CurrentUser; compact: boolean };` — real shape; `user` is step 001's `CurrentUser` imported from `shared/currentUser`, `compact` is `true` on the rail
- `export function UserMenu(props: UserMenuProps): React.JSX.Element` — unimplemented body

`UserMenu`'s markup is deliberately unwritten: the trigger, the `Menu`'s `top-*` position, the three items and the admin item's conditional presence are the behaviour DoD-1..9 test, so rendering them now would make those clauses pass at the red gate.

Notes: both unimplemented bodies use the house form — `void <param>;` then `throw new Error("not implemented")`. `UserMenu` is a plain function component, not an `observer` (it reads no observable and holds no MobX state; no `ShellState` parameter). `apiPost`, `documentNavigation`, `notifyFailure`, `useNavigate`, the Mantine components and the Tabler icons are deliberately **not** imported yet (`noUnusedLocals` would fail); the coder adds those with the bodies.

Caller-compile edits (out of Source-files scope): None — both modules are new and have no importer until `004`.

`npm run typecheck` passes.

### Step 004 — frozen interface

`frontend/src/app/WorkspaceShell.tsx` (new — imports `type * as React` from `react`, `observer` from `mobx-react-lite`, `type { CurrentUser }` from `../shared/currentUser` and `type { LayoutStorage }` from `./workspaceLayout`)

- `export type WorkspaceShellProps = { user: CurrentUser; storage: LayoutStorage | null; children: React.ReactNode };` — real shape; all three required, `storage` nullable (there is no parameterless variant: 005 passes `browserLayoutStorage()`)
- `export const WorkspaceShell = observer(function WorkspaceShell(props: WorkspaceShellProps): React.JSX.Element { … });` — unimplemented body; the house observer form (`observer` from `mobx-react-lite`, assigned to an exported `const`)

`frontend/src/app/App.tsx` (new — imports `type * as React` from `react`, `type { CurrentUser }` from `../shared/currentUser` and `type { LayoutStorage }` from `./workspaceLayout`)

- `export type AppProps = { user: CurrentUser; storage: LayoutStorage | null };` — real shape; both required, no `children`
- `export function App(props: AppProps): React.JSX.Element` — unimplemented body; a plain function component, **not** an `observer` (it reads no observable itself), and it creates no router

Both component bodies are deliberately unwritten: the grid element and its class, the two columns with their accessible names, the rail's three controls, the expanded column's collapse control, the `UserMenu` footer in both states, the overlay-closing effects and the whole six-route table are the behaviour DoD-1..11 assert, so rendering any of it now would make those clauses pass at the red gate.

Notes: unimplemented bodies use the house form — `void props;` then `throw new Error("not implemented")` (`noUnusedParameters` is on). `useState`, `useEffect`, `useMediaQuery`, `useLocation`, `useNavigate`, `Route`/`Routes`, `IconButton`, `UserMenu`, the Tabler icons and every `shellState` symbol (`createShellState`, `showsRail`, `shellClassName`, `expandTree`, `collapseTree`, `closeOverlay`, `NARROW_VIEWPORT_QUERY`) are deliberately **not** imported yet (`noUnusedLocals` would fail); the coder adds those with the bodies. The installed `useMediaQuery(query, initialValue?, { getInitialValueInEffect }?)` returns `boolean | undefined`, so the coder must coerce narrow to a `boolean` before passing it into 002's functions.

Caller-compile edits (out of Source-files scope): None — both modules are new; `App`'s first importer is 005's `main.tsx`/`AppBoot`.

`npm run typecheck` passes.

### Step 005 — frozen interface (re-frozen 2026-10-01 after the `appBoot.ts` / `AppBoot.tsx` case-collision revision)

**Preparatory cleanup, performed by this pass** (the step file's `## Preparatory cleanup`): the previous freeze's `frontend/src/app/appBoot.ts` and the previous test-coder's `frontend/tests/app/appBoot.test.ts` were **deleted** before anything was written at the new path, so no stale file remains. `appBoot.ts` beside `AppBoot.tsx` was the case-only collision — TypeScript resolved `./AppBoot` to the `.tsx`, Vite/Vitest to the `.ts` sibling — and the stale test imported a module that no longer exists, which `include: ["src", "tests"]` would have failed. Symbols, signatures, types and fields are **unchanged by the rename**; only the module path moved.

`frontend/src/app/appBootState.ts` (new — renamed from `appBoot.ts`; imports `makeAutoObservable` from `mobx` and `type { CurrentUser }` from `../shared/currentUser`)

- `export const APP_BOOT_RETRY_INTERVAL_MS = 2000;` — real value; inferred as the literal type `2000`
- `export type AppBootOutcome = "unauthenticated" | "not-ready" | "failed";` — real type
- `export function classifyAppBootError(error: unknown): AppBootOutcome` — unimplemented body
- `export class AppBootState { status: "probing" | "unauthenticated" | "not-ready" | "failed" | "ready" = "probing"; user: CurrentUser | null = null; constructor() { makeAutoObservable(this, {}, { autoBind: true }); } }` — real shape: observable fields only, no methods, no getters. The five-member status union is declared **inline on the field** (the Interface intent names no separate status type); `AppBootOutcome` is assignable to it, so `probeCurrentUser` can write a classification straight into `status`
- `export async function probeCurrentUser(state: AppBootState, signal?: AbortSignal): Promise<void>` — unimplemented body
- `export function restartBoot(state: AppBootState): void` — unimplemented body

Importers spell this module **`./appBootState`** (from `src/app/`) or `../../src/app/appBootState` (from `tests/app/`) — unambiguous under both resolvers. Lowercased, `appbootstate`, `appboot`, `appbootscreens` and `main` are all distinct, so DoD-14's scan of `src/app/` has nothing to flag.

`frontend/src/app/AppBootScreens.tsx` (new — unchanged by this revision; imports `type * as React` from `react` and nothing else)

- `export type AppNotReadyProps = { onRetry: () => void };` — real shape
- `export type AppBootFailedProps = { onRetry: () => void };` — real shape; a separate alias per screen rather than one shared props type, so each screen's props can diverge without touching the other
- `export function AppNotReady(props: AppNotReadyProps): React.JSX.Element` — unimplemented body
- `export function AppBootFailed(props: AppBootFailedProps): React.JSX.Element` — unimplemented body

`frontend/src/app/AppBoot.tsx` (new — unchanged by this revision, and **it keeps its name**: `009` and `010` cite it. Imports `type * as React` from `react`, `observer` from `mobx-react-lite` and `type { LayoutStorage }` from `./workspaceLayout`)

- `export type AppBootProps = { storage: LayoutStorage | null };` — real shape; required, nullable, no `children`, no `user` (the gate fetches the user itself)
- `export const AppBoot = observer(function AppBoot(props: AppBootProps): React.JSX.Element | null { … });` — unimplemented body; the house observer form. The return type is `React.JSX.Element | null` — unlike every other component in the tree, whose return is a bare `React.JSX.Element` — because DoD-4 and DoD-6 require the `"probing"` and `"unauthenticated"` statuses to render **nothing**; `null` is the honest return for those branches (the coder may still return `<></>` if preferred, both satisfy the type)
- **No edit was required by the rename**: the stub does not yet import the state module (`noUnusedLocals`), so there was no old specifier to update. The coder writes `import { … } from "./appBootState";` with the body.

`frontend/src/app/main.tsx` — **left exactly as built; no frozen interface.** An entry module exports nothing, so there is no signature to freeze, and a `main.tsx` whose body threw would leave the `app` entry unable to mount at all. The rewrite (D2: `AppProviders` → `BrowserRouter` → `AppBoot` with `storage` from `browserLayoutStorage()`, the placeholder `<div data-entry="app" />` route gone, the `../shell.css` import and the `#root` guard kept, still no `basename`) is **the coder's**, and DoD-11/DoD-12 scan its content.

The two component files contain **no JSX**: the screens' titles and button labels, the status-to-screen mapping, the probe-on-mount, the 2000 ms re-probe loop, the two retries and the abort handling are the behaviour DoD-4..DoD-10 test, so rendering any of it now would make those clauses pass at the red gate. DoD-14's case-collision scan is the test-coder's to write; the deletions above are what make it pass.

Notes: unimplemented bodies use the house form — `void <param>;` lines then `throw new Error("not implemented")` (`noUnusedParameters` is on). `AppBootState`'s field initialisers satisfy `strictPropertyInitialization`, so its constructor takes no parameter — shape, not behaviour. `fetchCurrentUser`, `ApiError`/`isApiError`, `isNotReady`, `useEffect`/`useRef`/`useState`, `App`, `AppNotReady`, `AppBootFailed` and the Mantine components are deliberately **not** imported yet (`noUnusedLocals` would fail); the coder adds those with the bodies. Nothing here imports from `src/admin/` (001's DoD-4 scan) and nothing imports `shared/notifyFailure` or `@mantine/notifications` (D2: both screens are full-page states).

Caller-compile edits (out of Source-files scope): one, in a **Test file** — `frontend/tests/app/AppBoot.test.tsx` line 12's import specifier `../../src/app/appBoot` → `../../src/app/appBootState`. It was the only surviving reference to the deleted module; without it `npm run typecheck` failed with TS2305 plus TS1149 ("differs from already included file name only in casing"). The edit is one specifier and changes no assertion; the file is in this step's Test files, so the test-coder rewrites it this pass regardless. No source file outside the step's Source files was touched, and steps 001–004 were not touched at all.

`npm run typecheck` passes (exit 0, both `tsconfig.json` and `tsconfig.node.json`).

## Tests

### Step 001 — tests

`frontend/tests/shared/currentUser.test.ts` (new) — covers DoD-1, DoD-2

- `issues exactly one GET to /api/me and nothing else — DoD-1`
- `resolves to the body's id, username and role unchanged — DoD-1`
- `resolves a roleplayer's role unchanged too — DoD-1`
- `keeps the id a string, never a number — DoD-1`
- `two calls issue two requests, one each — DoD-1`
- `a well-formed 403 envelope rejects with an ApiError carrying the envelope's code — DoD-2`
- `a rejected fetch rejects with the client's transport-failure ApiError — DoD-2`
- `a failure is not swallowed into a resolved value — DoD-2`

`frontend/tests/admin/adminAccess.test.ts` (extended — existing 27 clauses untouched) — covers DoD-3

- `answering %s reaches the unchanged decision — DoD-3` (`it.each`: an administrator → granted, a roleplayer → denied-not-admin, a 401 → denied-no-session, a not-ready failure → not-ready, a well-formed 403 → failed)
- `answering %s requests /api/me exactly once — DoD-3` (`it.each`, the same five cases)
- `an administrator is granted and still navigates nothing — DoD-3`
- `a roleplayer is still navigated to /, once — DoD-3`
- `a 401 still yields the shared client's /login navigation alone — DoD-3`
- `a not-ready failure still navigates nothing — DoD-3`
- `a well-formed 403 still carries the envelope's message and navigates nothing — DoD-3`

`frontend/tests/app/entryIsolation.test.ts` (new) — covers DoD-4, DoD-13 (source scans over `src/app/`, `src/shared/currentUser.ts` and `src/app/workspaceLayout.ts`)

- `the scan reaches every .ts and .tsx file under src/app, recursively — DoD-4`
- `the scan sees the import specifiers of a module it reads — DoD-4`
- `no module under src/app imports from src/admin — DoD-4`
- `the admin-reaching check would flag a relative import of src/admin — DoD-4`
- `src/shared/currentUser.ts contains no /admin path string — DoD-4`
- `src/shared/currentUser.ts imports nothing from src/admin — DoD-4`
- `the scan reads src/app/workspaceLayout.ts — DoD-13`
- `src/app/workspaceLayout.ts references no %s — DoD-13` (`it.each`: a window reference, a document reference, a localStorage global, a sessionStorage global, a React import, a MobX import)

`frontend/tests/app/workspaceLayout.test.ts` (new) — covers DoD-5..DoD-12 (the storage is always an in-memory fake with spy-able `getItem`/`setItem`, or `null`)

- `the key is rphelper.workspace-layout — DoD-9`
- `both fields default to false — DoD-5`
- `a null storage yields the defaults — DoD-5`
- `a storage with no value under the key yields the defaults — DoD-5`
- `a storage holding other keys only yields the defaults — DoD-5`
- `a storage whose getItem throws yields the defaults and does not throw — DoD-5`
- `a stored %s yields the defaults — DoD-6` (`it.each`: unparseable JSON, an empty string, an array, an array of records, a string, a number, null, a boolean)
- `a stored %s never throws — DoD-6` (`it.each`, the same eight cases)
- `a valid navCollapsed survives a non-boolean wallPinned — DoD-7`
- `a valid wallPinned survives a non-boolean navCollapsed — DoD-7`
- `a record missing wallPinned keeps the stored navCollapsed — DoD-7`
- `a record missing navCollapsed keeps the stored wallPinned — DoD-7`
- `a record with both fields stored returns both — DoD-7`
- `an empty record yields the defaults — DoD-7`
- `a null field value falls back to that field's default — DoD-7`
- `asideWidth and answerBoxHeight beside both known fields are ignored — DoD-8`
- `the result carries no key besides navCollapsed and wallPinned — DoD-8`
- `an unknown key never fails the parse of the known fields — DoD-8`
- `only rphelper.workspace-layout is requested — DoD-9`
- `an absent value is still only one key asked for — DoD-9`
- `a navCollapsed patch stores the patched value under the key — DoD-10`
- `a navCollapsed patch keeps the previously stored wallPinned — DoD-10`
- `a navCollapsed patch over an empty storage round-trips with the other default — DoD-10`
- `a wallPinned patch keeps the previously stored navCollapsed — DoD-10`
- `a patch of both fields stores both — DoD-10`
- `two successive writes of one field each keep both values — DoD-10`
- `a stored asideWidth is dropped by the write — DoD-11`
- `a later read sees no unknown key either — DoD-11`
- `a storage whose setItem throws returns normally — DoD-12`
- `a storage whose getItem throws returns normally — DoD-12`
- `a null storage is a no-op that returns normally — DoD-12`
- `an empty patch returns normally — DoD-12`
- `a storage holding unparseable JSON is written without throwing — DoD-12`

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 [manual/live, no test].

### Step 002 — tests

`frontend/tests/stylesheets.test.ts` (extended; **one clause replaced**) — covers DoD-1..DoD-6.
The replaced clause is feature 002/002's `contains no CSS rule: comments and whitespace only — DoD-3`
(the only clause removed). **Kept untouched:** its sibling `exists — DoD-3` (its enclosing
`describe` title is now `"shell.css is declared"`), `global.css and shell.css are the only
.css files under src — DoD-4`, and every `global.css` resets / resets-only clause. No clause
about `global.css` was added. New helpers: `NARROW_MEDIA`, `splitNarrowMedia` (separates the
at-rule's body from the top-level rules), `canonicalSelector` (`>` reads as a descendant
combinator), `compactValue`; the file's existing `readText` / `stripComments` / `parseRules`
resolution is reused, so DoD-4 and DoD-5 ignore comment text.

- `makes .app a grid — DoD-1`
- `draws the divider as a 1px gap — DoD-1`
- `sizes the two tracks from --navw with a 252px fallback — DoD-1`
- `.app.nav-collapsed re-points --navw at 48px — DoD-2`
- `.app.nav-collapsed declares nothing besides --navw — DoD-2`
- `declares the @media (width < 820px) at-rule — DoD-3`
- `pins the narrow nav track to 48px regardless of the collapse class — DoD-3`
- `lifts .app.nav-overlay-open .app-nav inside the media query — DoD-3`
- `declares no literal colour value — DoD-4`
- `takes every colour from a Mantine custom property — DoD-4`
- `draws the divider line with a Mantine background variable on .app — DoD-4`
- `imports no other stylesheet — DoD-5`
- `declares no font face — DoD-5`
- `declares no font or typography property — DoD-5`
- `uses no selector beyond the shell's five — DoD-5`
- `NARROW_VIEWPORT_QUERY is the range query (width < 820px) — DoD-6`
- `shell.css spells the threshold with that very string — DoD-6` (the constant is the needle,
  so the two literals cannot drift)

`frontend/tests/app/shellState.test.ts` (new) — covers DoD-7..DoD-13. The storage is always a
passed-in in-memory fake with spy-able `getItem`/`setItem`, or `null`; `overlayOpen` is set
through `runInAction` when a derivation needs a given condition, never through an effect under
test.

- `a stored collapsed nav starts collapsed — DoD-7`
- `a stored expanded nav starts expanded — DoD-7`
- `no storage at all starts expanded — DoD-7`
- `an empty storage starts expanded — DoD-7`
- `a state built over a stored record starts with the overlay closed — DoD-7`
- `a state built over no storage starts with the overlay closed — DoD-7`
- `wide: an expanded nav shows the full column, overlay flag %s/%s notwithstanding — DoD-8` (`it.each`, 2 cases)
- `wide: a collapsed nav shows the rail, overlay flag %s/%s notwithstanding — DoD-8` (`it.each`, 2 cases)
- `narrow: a closed overlay shows the rail whatever navCollapsed (%s) is — DoD-8` (`it.each`, 2 cases)
- `narrow: an open overlay shows the full column whatever navCollapsed (%s) is — DoD-8` (`it.each`, 2 cases)
- `an expanded wide shell is plain app — DoD-9`
- `a collapsed wide shell is app nav-collapsed — DoD-9`
- `a narrow shell with the overlay open adds nav-overlay-open — DoD-9`
- `a narrow collapsed shell with the overlay open carries both classes — DoD-9`
- `a narrow shell with the overlay closed adds nothing — DoD-9`
- `a wide shell never carries nav-overlay-open, navCollapsed %s — DoD-9` (`it.each`, 2 cases)
- `every class string begins with app — DoD-9`
- `collapseTree collapses the nav — DoD-10`
- `collapseTree writes the collapse to the record — DoD-10`
- `expandTree expands the nav — DoD-10`
- `expandTree writes the expansion to the record — DoD-10`
- `a collapse write preserves a pinned wall — DoD-10`
- `an expand write preserves a pinned wall — DoD-10`
- `a collapse and an expand round-trip the record — DoD-10`
- `a wide toggle over no storage still changes the state — DoD-10`
- `expandTree opens the overlay, stored collapse %s — DoD-11` (`it.each`, 2 cases)
- `expandTree leaves navCollapsed (%s) untouched — DoD-11` (`it.each`, 2 cases)
- `expandTree writes nothing to storage, stored collapse %s — DoD-11` (`it.each`, 2 cases)
- `collapseTree closes the overlay, stored collapse %s — DoD-11` (`it.each`, 2 cases)
- `collapseTree leaves navCollapsed (%s) untouched — DoD-11` (`it.each`, 2 cases)
- `neither narrow toggle writes to storage, stored collapse %s — DoD-11` (`it.each`, 2 cases)
- `closeOverlay closes the overlay and writes nothing, stored collapse %s — DoD-11` (`it.each`, 2 cases)
- `closeOverlay on an already closed overlay keeps it closed — DoD-11`
- `an autorun reading showsRail re-runs after a wide collapseTree — DoD-12`
- `an autorun reading showsRail re-runs after a narrow collapseTree — DoD-12`
- `an autorun reading shellClassName re-runs after a narrow expandTree — DoD-12`
- `returns the document's localStorage — DoD-13`
- `the returned storage reads and writes the document's localStorage — DoD-13`
- `returns null when accessing window.localStorage throws — DoD-13`
- `does not rethrow when accessing window.localStorage throws — DoD-13`
- `recovers the real localStorage once the access stops throwing — DoD-13` (the redefined
  `window.localStorage` getter is restored in a `finally`, so no state leaks to other files)

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 [manual/live, no test],
DoD-15 [manual/live, no test].

Note for the red gate: DoD-5 is a purely prohibitive clause set (`@import`, `@font-face`,
typography, selectors), so three of its four clauses are vacuously green against the
comment-only `shell.css`; its selector clause also asserts the file carries at least one rule
(required by DoD-1..DoD-3), which is red until the coder fills the stylesheet. The same holds
for the two negative DoD-4 scans — the positive DoD-4 clause (the Mantine background variable)
is red.

### Step 003 — tests

`frontend/tests/app/logout.test.ts` (new) — covers DoD-6, DoD-7, DoD-8. `fetch` is stubbed per
test with `vi.stubGlobal`; `documentNavigation.assign` is a restored `vi.spyOn`;
`shared/notifyFailure` is replaced by a mock module (`vi.mock`), so `@mantine/notifications` is
never imported here.

- `issues exactly one POST to /api/auth/logout and nothing else — DoD-6`
- `sends no request body — DoD-6`
- `navigates the document to exactly /login, once — DoD-6`
- `resolves without throwing on a 204 with an empty body — DoD-6`
- `a successful logout raises no notification — DoD-6`
- `a transport failure notifies with the thrown error — DoD-7`
- `a transport failure navigates the document nowhere — DoD-7`
- `a transport failure resolves without throwing — DoD-7`
- `a well-formed 500 envelope notifies with the thrown error — DoD-7`
- `a well-formed 500 envelope navigates the document nowhere — DoD-7`
- `a well-formed 500 envelope resolves without throwing — DoD-7`
- `navigates the document nowhere — DoD-8` (already-aborted signal)
- `raises no notification — DoD-8` (already-aborted signal)

`frontend/tests/app/UserMenu.test.tsx` (new) — covers DoD-1..DoD-6, DoD-9. Rendered as
`AppProviders > MemoryRouter > UserMenu + LocationProbe`; the router's location is read from the
probe; the portal-rendered dropdown is opened by clicking the "User menu" trigger and then
queried from the document.

- `a %s sees Settings and Log out — DoD-1` (`it.each`: roleplayer, admin)
- `an administrator sees an Admin area item — DoD-2`
- `the open menu holds no Admin area item at all — DoD-3`
- `the rendered output holds no element with href /admin — DoD-3`
- `is an anchor element whose href is exactly /admin — DoD-4`
- `activating it leaves the in-entry router's location unchanged — DoD-4`
- `choosing it moves the in-entry router to /settings — DoD-5`
- `choosing it performs no document navigation — DoD-5`
- `posts to /api/auth/logout and then navigates the document to exactly /login — DoD-6`
- `expanded, it shows the username as visible text — DoD-9`
- `compact, it shows no username text — DoD-9`
- `it is found by the accessible name User menu, compact %s — DoD-9` (`it.each`, 2 cases)
- `it opens the same menu, compact %s — DoD-9` (`it.each`, 2 cases)

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
DoD-10 [manual/live, no test], DoD-11 [manual/live, no test], DoD-12 [manual/live, no test].

### Step 004 — tests

`frontend/tests/app/WorkspaceShell.test.tsx` (new) — covers DoD-1..DoD-9. Rendered as
`AppProviders > MemoryRouter > WorkspaceShell + LocationProbe`; the storage is always an
in-memory fake `LayoutStorage` with spy-able `getItem`/`setItem` (never jsdom's
`localStorage`), so "no write happened" is assertable; the grid element is reached as the
nav column's parent and asserted by **class membership and rendered content only** (jsdom
applies no `shell.css`). Every control is found by its accessible name — no test names a
glyph (D10). Narrow tests replace `window.matchMedia` with a stub reporting
`matches: true` for exactly `NARROW_VIEWPORT_QUERY` and the original is restored in the
file-level `afterEach`.

- `renders the Workspace navigation nav and a main region holding the centre — DoD-1`
- `gives the grid element the app class without nav-collapsed — DoD-1`
- `shows the Collapse tree control and the User menu trigger with the username — DoD-1`
- `adds nav-collapsed to the grid element — DoD-2`
- `replaces the expanded column with the rail's search, create and expand — DoD-2`
- `the User menu trigger opens the menu with Settings and Log out — DoD-3`
- `New character moves the in-entry router to /characters/new — DoD-4`
- `Search moves the in-entry router to /search — DoD-4`
- `a collapse is stored, restored on a fresh mount, and reversed by Expand tree — DoD-5`
- `an expanded stored record still shows the rail — DoD-6`
- `Expand tree shows the expanded column and adds nav-overlay-open — DoD-6`
- `opening the overlay writes nothing to the storage — DoD-6`
- `Collapse tree closes it and shows the rail again — DoD-7`
- `closing the overlay writes nothing to the storage — DoD-7`
- `an in-entry navigation from the user menu closes it — DoD-7`
- `a fresh shell over the same storage starts with the overlay closed — DoD-8`
- `the expanded shell's grid element has exactly two child elements — DoD-9`
- `the collapsed shell's grid element has exactly two child elements — DoD-9`
- `no wall control is rendered in either column state — DoD-9`

`frontend/tests/app/App.test.tsx` (new) — covers DoD-10, DoD-11. Rendered as
`AppProviders > MemoryRouter > App` with `storage={null}`; `App` creates no router, so the
test supplies `MemoryRouter initialEntries`. "No centre content" is asserted as the main
region's trimmed `textContent` being empty, and the 404 text is asserted **inside** the
main region.

- `renders the shell at %s — DoD-10` (`it.each`: `/`, `/sessions/1`, `/characters/1`,
  `/characters/new`, `/settings`, `/search`)
- `renders no centre content at %s — DoD-10` (`it.each`, the same six paths)
- `renders the shell with Page not found inside the main region — DoD-11`

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
DoD-10 ✓, DoD-11 ✓, DoD-12 [manual/live, no test], DoD-13 [manual/live, no test].

### Step 005 — tests (re-bound 2026-10-01 to `app/appBootState.ts`)

`frontend/tests/app/appBootState.test.ts` (new — written fresh at the renamed path; the
previous pass's `tests/app/appBoot.test.ts` was deleted by the re-freeze) — covers DoD-1,
DoD-2, DoD-3, DoD-14. No component, no timers. Each thrown value DoD-1 classifies is
produced by the **real client** — `fetchCurrentUser` over a stubbed `fetch` — so the fixture
is the very value `shared/api.ts` throws for that condition rather than a hand-made
look-alike built from a guessed constructor or synthetic code. `fetch` is stubbed per test
with `vi.stubGlobal`; `documentNavigation.assign` is a restored `vi.spyOn` (the client
navigates on a 401 itself). The abort clauses drive a deferred `fetch` so the response (or
rejection) settles **after** `controller.abort()`.

- `a 401 whose code is not_authenticated is unauthenticated — DoD-1` (code and status 401
  asserted on the fixture first)
- `the client's transport-failure ApiError is not-ready — DoD-1`
- `a malformed-body ApiError at status 502 is not-ready — DoD-1` (a gateway's HTML 502 page)
- `a well-formed 403 envelope is failed — DoD-1`
- `a well-formed 500 envelope is failed — DoD-1`
- `a plain Error is failed — DoD-1`
- `a thrown non-Error value is failed too — DoD-1`
- `classifies an already-thrown value with no request of its own — DoD-1`
- `a fresh boot state is probing with no user — DoD-2`
- `a %s identity is written as ready — DoD-2` (`it.each`: roleplayer, admin)
- `keeps the fetched id a string — DoD-2`
- `issues exactly one GET /api/me — DoD-2`
- `a successful probe navigates nothing — DoD-2`
- `%s writes its classified status — DoD-3` (`it.each`: a 401 envelope → unauthenticated, a
  transport failure → not-ready, a raw 502 page → not-ready, a well-formed 403 → failed, a
  well-formed 500 → failed)
- `%s is never rethrown — DoD-3` (`it.each`, the same five cases)
- `%s leaves the user null — DoD-3` (`it.each`, the same five cases)
- `a response that settles after the abort is not written — DoD-3`
- `a failure that settles after the abort is not written either — DoD-3`
- `an already-aborted signal writes nothing — DoD-3`
- `an abort does not stop a later probe over a fresh signal — DoD-3`
- `the scan reaches every .ts and .tsx file under src/app, recursively — DoD-14` (names
  `main.tsx`, `appBootState.ts`, `AppBoot.tsx`, `AppBootScreens.tsx` — the scan is live)
- `no two module paths under src/app are equal once lowercased — DoD-14`
- `the check flags a constructed colliding pair — DoD-14` (`appBoot.ts` vs `AppBoot.tsx`, so
  the clause above cannot pass vacuously)
- `the check flags a collision in a nested folder too — DoD-14`
- `the check leaves paths differing by more than case alone — DoD-14`

DoD-14's comparison is over the **extensionless module path** (`.ts` / `.tsx` stripped, then
lowercased), which is the specifier the two resolvers disagree about and the reading
`005.context.md` fixes ("Lowercased, `appbootstate`, `appboot`, `appbootscreens` and `main`
are all distinct"). Compared with extensions the guard would be vacuous — `appboot.ts` and
`appboot.tsx` are already unequal — and would not flag the defect it exists for.

`frontend/tests/app/AppBoot.test.tsx` (kept from the previous pass; its import of the state
module now reads `../../src/app/appBootState` and its header comment points at the new test
file — no assertion changed, DoD-4..DoD-10 are byte-identical in the revised step) — covers
DoD-4..DoD-10. Rendered as
`AppProviders > MemoryRouter > AppBoot storage={null}`; the shell is found by the nav column's
accessible name ("Workspace navigation") and the screens by their contract strings, never by
structure. `shared/notifyFailure` is replaced by a mock module (`vi.mock`), so
`@mantine/notifications` is never imported here and "no notification" is assertable. Timer
tests use the house pattern — `vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout",
"setInterval", "clearInterval"] })` with a real `setImmediate` draining promises in `flush`,
`advanceTimersByTimeAsync` inside `act`, and `vi.useRealTimers()` first in the file-level
`afterEach`. Retries are clicked with `fireEvent`.

- `renders no shell, no not-ready screen and no failure panel — DoD-4` (pending-forever probe)
- `renders nothing of its own and navigates nowhere while pending — DoD-4`
- `a %s sees the workspace navigation and the user menu with the username — DoD-5` (`it.each`:
  roleplayer, admin)
- `a %s is not denied: no document navigation — DoD-5` (`it.each`, both roles)
- `renders no shell and neither boot screen — DoD-6`
- `the shared client's /login navigation is the only one — DoD-6` (exactly one call)
- `the re-probe interval is a fixed 2000 ms — DoD-7`
- `shows the screen, re-probes at 2000 ms and renders the shell when that probe succeeds — DoD-7`
  (nothing at 1999 ms, the second probe at 2000 ms)
- `re-probes again 2000 ms after a second not-ready outcome, then stops once ready — DoD-7`
- `recovering from not-ready navigates nowhere and raises no notification — DoD-7`
- `Retry now requests /api/me immediately — DoD-8`
- `Retry now, not the 2000 ms timer, issues the second probe — DoD-8`
- `shows the panel and never re-probes on its own — DoD-9` (unchanged request count after
  2000 ms and after 20000 ms)
- `Retry requests /api/me again and the shell renders on success — DoD-9`
- `the failure path navigates nowhere and raises no notification — DoD-9`
- `no further /api/me request is made after unmount — DoD-10`

`frontend/tests/entries.test.tsx` (the `app` clauses replaced; **unchanged by this re-bind** —
it names no module path the rename touched, and the `bootstrap`, `login` and `admin` clauses
are not this step's) — covers DoD-11, DoD-12.

- **Replaced:** the `app` case of the three marker clauses in `describe("each entry mounts its
  own marker")` (`%s renders its own marker on #root — DoD-1`, `%s renders no other entry's
  marker — DoD-1`, `%s renders its marker for a deep link too — DoD-1`) now run over a new
  `MARKER_ENTRIES` (`bootstrap`, `login`, `admin`), and the `${entry} renders its marker at %s
  — DoD-4` loop over a new `MARKER_NON_ADMIN_ENTRIES` (`bootstrap`, `login`). Reason: 005
  removes the placeholder `<div data-entry="app" />` and no step's spec gives the marker a new
  home, so no clause may assert one for `app`; the new DoD-11 clauses assert the shell instead.
  `mountEntry` gained an `app` branch (a `/api/me` stub, overridable per clause, plus the same
  `settle()` the admin gate uses) and a third defaulted parameter.
- **Untouched:** every `bootstrap`, `login` and `admin` clause — their titles, bodies and order,
  including all five admin-basename clauses and `stubAdminIdentity`. Also untouched: the three
  `— DoD-2` provider clauses, `%s/main.tsx declares no basename — DoD-4`, both `— DoD-5`
  `shell.css` clauses, both `— DoD-6` clauses and all seven `index.html` clauses (`app` still
  runs in each).
- **New:** `renders the workspace shell into #root for a signed-in roleplayer — DoD-11`
- **New:** `renders the shell at %s too — DoD-11` (`it.each`: `/`, `/sessions/abc123`,
  `/settings`, `/search`)
- **New:** `renders nothing into #root when /api/me answers 401 — DoD-11` (no element at all
  besides Mantine's injected `<style>` tags)
- **New:** `src/app/main.tsx imports ../shell.css and no other stylesheet — DoD-12`
- **New:** `src/app/main.tsx declares no basename — DoD-12`

Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 [manual/live, no test], DoD-14 ✓.

Note for the red gate: DoD-11 and DoD-12 are red by construction — `src/app/main.tsx` is
deliberately left as the built placeholder (`## Ultra phase`, deliberate red 3), so the app
entry neither probes `/api/me` nor mounts the shell until the coder rewrites it in Phase 5.
DoD-14 is **green at the red gate** and that is not a tautology: it is a prohibitive invariant
over filenames, which the skeleton's deletions already satisfy. Its liveness is pinned by two
sibling clauses — the scan must list the four real `src/app` modules, and the same comparison
must flag a constructed `appBoot.ts` / `AppBoot.tsx` pair — so it cannot pass over an empty
file list or a dead comparison.

## Notes & Issues

- Step 002: at wide width `expandTree` / `collapseTree` write the record unconditionally,
  as the step file's Interface intent states ("Wide: sets `navCollapsed` false and writes
  `{ navCollapsed: false }`"); the "only on a toggle that changes `navCollapsed`" rule of D9
  is honoured by the narrow branches, which never read or write `navCollapsed`.
- Step 002: Vite's minifier emits the range query as `@media (width<820px)` in `dist`;
  the source string stays verbatim, so `NARROW_VIEWPORT_QUERY` and `shell.css` still match.

## Ultra phase

- orient: done 2026-10-01
- harvest: done — docs/.cache/ultra/008.app-shell-frame/harvest.md (2 reports)
- skeleton: done — steps 001, 002, 003, 004, 005
  - unimplemented-body house form: `void <param>;` lines then `throw new Error("not implemented")`
    (`noUnusedParameters` / `noUnusedLocals` are on, so a stub imports nothing it does not yet use —
    the coder adds those imports together with the bodies).
  - **Three deliberate reds the red gate must not read as regressions.** Each exists so the step's
    `[test]` clauses cannot pass against a stub:
    1. Step 001 re-points `enforceAdminAccess` at the still-unimplemented `fetchCurrentUser`, so the
       **existing** `tests/admin/adminAccess.test.ts` clauses are red too. Without the re-point, 001's
       DoD-3 would pass at the gate.
    2. `frontend/src/shell.css` is left comment-only (the skeleton froze no CSS), so 002's DoD-1..6
       content scans are red.
    3. `frontend/src/app/main.tsx` is left as the built placeholder (`<div data-entry="app" />`, no
       `/api/me`), so 005's DoD-11 and DoD-12 are red. Both files are the coder's to fill in Phase 5.
- tests: done — steps 001, 002, 003, 004, 005
  - The `app` entry's `data-entry="app"` marker is **gone by design**, not an unspecified gap: `005`'s
    Interface intent states "the placeholder `<div data-entry="app" />` route is gone", and `004` gives
    `WorkspaceShell` no marker. `005`'s DoD-11 sanctions updating `entries.test.tsx`'s `app` clauses, so
    asserting the shell by its accessible name in place of the marker is the contract. The other three
    entries keep their marker clauses untouched.
  - Prohibition clauses that are vacuously green against an empty `shell.css` (002's DoD-4 negative
    scans, DoD-5's three prohibitions) are inherent to a prohibition, not a tautology fault.
- red-gate: FAIL (run 1) — 001, 002, 003, 004 PASS; **005 FAIL, Fault TEST with an uncleared Spec concern**
  - Steps 001–004 compile, trace every `[test]` id, and are red for the right reason. 004 is clean with
    no green clause at all. The three deliberate reds and the vacuous prohibitions were observed exactly
    as recorded and counted against nobody.
  - **005 is blocked on a plan-level defect, not a test defect.** Step 005's Source files name
    `frontend/src/app/appBoot.ts` and `frontend/src/app/AppBoot.tsx` — two module paths differing **only
    in letter case**. TypeScript resolves `./AppBoot` to the `.tsx` file, but Vite/Vitest on this
    case-insensitive filesystem resolves the same specifier to the `.ts` sibling, so the component
    binding is `undefined` at runtime. Every clause of DoD-4..DoD-10 dies before reaching the gate's
    stub. Verified empirically by the red-gate verifier: the extensionless specifier yields
    `appBoot.ts`'s export list and no component export.
  - **Why the test-side fix is not available.** An explicit `./AppBoot.tsx` specifier requires
    `allowImportingTsExtensions`, which is set in neither tsconfig (`moduleResolution: "bundler"`,
    `verbatimModuleSyntax` unset). Adding it is a project-wide compiler-flag change to paper over a
    filename collision, and `npm run typecheck` is a gate. So no in-contract test rewrite clears this.
  - **The hazard is not confined to the tests.** `main.tsx` must import the gate in Phase 5 and would
    collapse the same way, and `typecheck` can never catch it — TS and Vite disagree by design here.
    Features `011`, `013` and `016` would inherit the trap.
  - **Suggested resolution (`/planner`):** rename one of the pair so the two no longer differ only in
    case — e.g. `app/appBoot.ts` → `app/appBootState.ts` (it holds the boot state, the classifier and
    the two effects; `AppBoot.tsx` keeps the component). That edits step 005's Source files, Interface
    intent and DoD-12's neighbourhood, so it is the planner's change, not this run's.
  - Steps 001–004 remain `pending`: Phase 5 may not begin until the global red gate passes.
- replan: 2026-10-01 — `/planner` revised step 005 and cleared the defect. `app/appBoot.ts` →
  **`app/appBootState.ts`** (the component `AppBoot.tsx` keeps its name, because `009`'s step 008 and
  `010`'s step 006 cite it); `tests/app/appBoot.test.ts` → `tests/app/appBootState.test.ts`; a new
  `## Preparatory cleanup` section requires the stale stub and stale test at the **old** paths to be
  deleted by the re-freeze, or the colliding pair survives on disk; a new **DoD-14** `[test]` guards
  the invariant with a recursive filename scan of `src/app/`. DoD-1..13 are byte-identical, so steps
  001–004 need nothing. No symbol, signature or behaviour changed. Row 005 → `pending`.
  Resume: re-freeze 005 → re-bind 005's tests → global red gate (run 2). Harvest is not re-run.
- skeleton: re-frozen — step 005 at `app/appBootState.ts` (six symbols reproduced verbatim; only the
  module path changed). Stale `src/app/appBoot.ts` and `tests/app/appBoot.test.ts` deleted per the step's
  `## Preparatory cleanup`, so lowercased `appbootstate` / `appboot` / `appbootscreens` / `main` are now
  all distinct under `src/app/`. `AppBoot.tsx`, `AppBootScreens.tsx` and `main.tsx` untouched; steps
  001–004 untouched. `npm run typecheck` exit 0.
  - **A skeleton-made edit sits inside a Test file.** After the deletions, `tests/app/AppBoot.test.tsx`
    line 12 was the last reference to the removed module and typecheck failed `TS2305` + `TS1149`
    ("differs from already included file name only in casing"). The skeleton changed that one import
    specifier — `"../../src/app/appBoot"` → `"../../src/app/appBootState"` — and no assertion. The plan's
    cleanup section anticipated this for `appBoot.test.ts` but not for `AppBoot.test.tsx`. That file is in
    step 005's Test files and the test-coder rewrites it this pass, so the edit is transient; recorded
    because a non-owning role touched an owned file.
- tests: re-bound — step 005 (revised plan). `tests/app/appBootState.test.ts` written fresh (the deleted
  `appBoot.test.ts` was not resurrected): DoD-1 ×8, DoD-2 ×5 + an `it.each` over both roles, DoD-3 ×3
  `it.each` over the five failure answers + 4 abort clauses, DoD-14 ×5. `tests/app/AppBoot.test.tsx` kept
  — DoD-4..DoD-10 are byte-identical in the revised step, so no assertion changed; only its header comment
  was re-pointed, and the skeleton's line-12 specifier edit was confirmed as the correct binding.
  `tests/entries.test.tsx` unchanged — its `app` clauses already match and it names no renamed path.
  Coverage: DoD-1..12 ✓, DoD-13 `[manual/live, no test]`, DoD-14 ✓. Steps 001–004 untouched.
  - **Two red-gate reading notes.** (a) DoD-1's six network-built clauses fail with `not implemented`
    raised by `fetchCurrentUser`, not by `classifyAppBootError`: the frozen record exposes no `ApiError`
    constructor and the two synthetic codes are not in the spec, so each thrown fixture is obtained by
    stubbing `fetch` and catching what `fetchCurrentUser` throws — by construction the very value the DoD
    names. Both stubs are unimplemented, so the red is correct but is not an assertion failure.
    (b) **DoD-14 is green at the red gate by nature.** It is a prohibitive filename invariant that the
    skeleton's two deletions already satisfy — the same class as 002's negative content scans, which the
    previous gate accepted. Liveness is pinned by two siblings: the scan must list the four real `src/app`
    modules, and the same comparison must flag a constructed `appBoot.ts` / `AppBoot.tsx` pair. The scan
    compares **extensionless** specifiers, because over full filenames `appboot.ts` vs `appboot.tsx` are
    already unequal and the guard would be vacuous for the exact defect it exists for; `005.context.md`
    fixes that reading.
- red-gate: **PASS (run 2)** — all five steps pass all four gates. `npm run typecheck` exit 0 (both
  tsconfigs). 001–004 were unchanged since run 1 and not re-litigated; 005 was re-verified in full
  against the revised plan, skeleton and tests.
  - **Defect closure confirmed on disk.** The stale pair is gone; `src/app/` now holds `App.tsx`,
    `AppBoot.tsx`, `AppBootScreens.tsx`, `appBootState.ts`, `logout.ts`, `main.tsx`, `shellState.ts`,
    `UserMenu.tsx`, `WorkspaceShell.tsx`, `workspaceLayout.ts` — all distinct lowercased and
    extensionless. `appboot` now collides only with the fixture the DoD-14 scan constructs on purpose.
  - Both run-3 reading notes were judged, not taken on trust. DoD-1's fixture-stage red accepted as
    correct red. DoD-14 verified **live, not vacuous**: its clauses enumerate the real `src/app/` files,
    and two siblings exercise the same comparison against a fabricated `appBoot.ts` / `AppBoot.tsx` pair
    and a nested-folder case, so the guard cannot pass over an empty list or a dead comparison. DoD-7's
    2000 ms clause and DoD-12's two `main.tsx` scans were also checked as frozen-constant / baseline
    greens rather than tautologies.
  - Clause counts: **413 total / 268 failed / 145 passed**, against run 1's 428 / 289 / 139. The shift is
    step 005's only — `appBootState.test.ts` was written fresh with a different clause count than the
    deleted `appBoot.test.ts`. No step outside 005 moved.
  - Accounting note for Phase 6: this run described its scope as "nine step test files" while the feature
    owns thirteen. Steps 001–004's gates were established in run 1 and the verifier deliberately did not
    re-litigate them, so the PASS stands — but the **global verify must run the whole suite**, which is
    its contract anyway. Worth comparing its total against 413 to confirm nothing was skipped.
- code: done — steps 001, 002, 003, 004, 005 (no re-freeze; no escape valve from any step).
  Every step reported `npm run typecheck` exit 0 on both tsconfigs and `npm run build` succeeding, and
  no coder read or ran a test file. Per-step detail is under `## Files Changed`.
  - 001 — `fetchCurrentUser` = `apiGet<CurrentUser>("/api/me", signal)` with no error handling of its own,
    so the client's 401 navigation and `ApiError`s propagate unchanged; `workspaceLayout` total on read,
    best-effort on write, still DOM-free. `adminAccess.ts` needed **no edit** — the skeleton's re-point
    became true the moment `fetchCurrentUser` had a body, which is how that deliberate red was meant to
    resolve.
  - 002 — `shell.css` filled, five selectors, layout only; the one colour reference is the divider
    (`var(--mantine-color-default-border)`), which `outcome.md` already asks the architect to record.
    Vite minifies the range query to `(width<820px)` in the bundle; the source string is verbatim.
    **Judgement call resolved by me, not the coder:** at wide width the record is written unconditionally,
    per DoD-10 and the Interface intent. D9's parenthetical draws the contrast toggle-vs-overlay, not
    changed-value-vs-same-value, and the narrow branches never read or write `navCollapsed`. No guard added.
  - 003 — `logOut` posts then navigates; on failure `notifyFailure` and stay; an aborted signal neither
    navigates nor notifies. A private `isAborted(signal)` helper was needed because a direct
    `signal?.aborted === true` early return narrowed the getter to `false | undefined` and failed `TS2367`
    at the post-await check. `UserMenu` plain (not observer), "Admin area" an `<a href="/admin">` with no
    click handler, rendered only for `role === "admin"`.
  - 004 — the grid element is a raw `div`, deliberately not a Mantine `Box`, so its class attribute is
    exactly what `shellClassName` returns — which is what the collapse-is-one-class rule depends on.
    Overlay dismissal is two `useEffect`s (`location.key`, `narrow`) and nothing else.
  - 005 — the re-probe timer is armed **from each probe's completion** (`status === "not-ready"` after the
    await), not from an effect keyed on `status`, which is what makes a not-ready → not-ready outcome
    re-arm; an `inFlight` flag prevents overlap, each probe clears the pending timer first, and the effect
    cleanup clears the timer and aborts the controller so a late response neither writes nor re-arms.
    No `documentNavigation` call anywhere in `AppBoot.tsx`. `main.tsx`'s placeholder route and its
    `Routes`/`Route` imports are gone. `src/app/` still has no case-colliding module names.
- verify: **PASS (run 1)** — all five steps PASS every gate; no CODE, TEST or SPEC fault, no fix round.
  `npm run typecheck` exit 0 (both tsconfigs), `npm run build` exit 0, and `npx vitest run` over the
  **whole** frontend suite exit 0: **51 files, 1999 clauses, 1999 passed, 0 failed, 0 skipped**.
  - **Nothing was skipped.** The feature's own thirteen files total **413 clauses — exactly the red gate's
    run-2 total** — and the whole 413 flipped from 268-failed to 0-failed. That closes the accounting note
    I raised after the red gate described its scope as nine files.
  - `tests/conventions.test.ts` and `tests/ids-are-strings.test.ts` are untouched and green.
    `tests/admin/adminAccess.test.ts` is **+60 / −0**: the original clauses are byte-identical and all 48 of
    their executed cases pass (the "27 clauses" figure counted `it` declarations, which `it.each` expands to
    48 at run time). `tests/entries.test.tsx`'s edits are confined to 005's DoD-11-sanctioned `app` clauses.
  - All eight behavioural checks I asked for were verified against behaviour, not the coders' prose —
    including the single 401 navigation, zero notifications on both boot failures, the re-probe counting
    1 → 2 → 3 across two 2000 ms advances with nothing at 1999 ms and nothing after unmount, and DoD-14's
    scan walking the real `src/app/` and flagging both a constructed `appBoot.ts`/`AppBoot.tsx` pair and a
    nested-folder pair.
  - **Scope: no deviation.** Every changed source and test file belongs to a step's list; `global.css`,
    `vite.config.ts`, `src/app/index.html`, `tests/setup.ts`, `package.json` and `package-lock.json` are
    untouched, and nothing under `backend/` was changed.
  - **Nine `[manual/live]` items are outstanding, not one** — my verify briefing miscounted them as only
    005's DoD-13. The full set: 001 DoD-14; 002 DoD-14, DoD-15; 003 DoD-10, DoD-11, DoD-12; 004 DoD-12,
    DoD-13; 005 DoD-13. Of these, 005's DoD-13 needs a running backend *and* a deliberate outage, and 003's
    DoD-12 needs a running backend; the rest are browser-geometry and middle-click checks.
  - Advisory, carried to `outcome.md` rather than fixed here: D9's "only on a toggle that changes
    `navCollapsed`" wording should be tightened so a later feature does not re-litigate it (the step file
    decides it unconditionally and the implementation is spec-faithful); `tests/entries.test.tsx` carries
    one stale `describe` title (`"bootstrap, login and app declare no basename"` now loops over two entries,
    the app's invariant having moved to 005's DoD-12) — coverage intact, title a word out of date; and
    `backend/out2.txt` is an untracked stray that predates this run and should not be committed with the
    feature.
