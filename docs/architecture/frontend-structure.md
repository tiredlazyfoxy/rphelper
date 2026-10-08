# Frontend structure

**Realizes:** FEAT-001, FEAT-002, FEAT-003, FEAT-004, FEAT-005, FEAT-006,
FEAT-007, FEAT-008, FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013, FEAT-017,
FEAT-019, FEAT-020, ACT-001, ACT-002, ACT-003, US-006.AC-3

React 19 + TypeScript, built by Vite as **four separate entries**. Component
library, state library and icon set are fixed in `overview.md`.

**TypeScript only.** No `.js` / `.jsx` / `.mjs` / `.cjs` file is authored anywhere
under `frontend/` — config included — and neither tsconfig enables `allowJs` or
`checkJs`. Reason in `overview.md`; the rule itself is in the root `CLAUDE.md`.

**No two module paths may differ only in letter case.** This is a second
project-wide naming rule, and it is here because `npm run typecheck` **cannot
enforce it** (008 D13). The development filesystem is case-insensitive while
TypeScript's resolver is not, so from **one** extensionless specifier `tsc` picks
the `.tsx` and Vite / Vitest pick the `.ts` — a green typecheck and an
`undefined` import at runtime. The worked example is the near-miss that produced
the rule: `src/app/appBoot.ts` beside `src/app/AppBoot.tsx`, which is why the boot
state module ships as **`appBootState.ts`**. Two things make this worth a
paragraph rather than a footnote: the symptom is **React reporting an `undefined`
element type**, which points nowhere near the cause; and the escape hatch is not
available — **`allowImportingTsExtensions` is set in neither tsconfig**, so a
specifier cannot disambiguate itself. A single test guards one folder (plan 005's
DoD-14, `src/app/`); the rule is the whole tree's.

**The `app` entry's visual shell is in `workspace-shell.md`** — the three columns,
all geometry, the note wall, layout persistence, and the anatomy of the stream and
the current zone. It is not described here. The conventions that are neither the
shell nor this doc's subject are split across two files:
**`ui-conventions.md`** (icons, the shared `IconButton`, the accessibility floor,
async feedback) and **`forms-and-lists.md`** (tables, the modal rule, the MobX
draft form, the confirm convention, the never-optimistic rule). **The "two resize
behaviours" the old pointer also named no longer exist** — no column and no
splitter in the workspace is user-resizable, and `workspace-shell.md`'s reversal
record says why they were deleted rather than moved. The one resizable thing is
the composer's text area, through the browser's native vertical handle
(2026-10-08; `workspace-shell.md`'s "Geometry") — not a splitter, and nothing this
doc's stores drive. This doc holds the build, the routing, the
stores, the API client and the SSE consumer.

## The multi-entry build

```
frontend/
  package.json  package-lock.json
  tsconfig.json             # strict; covers src/ and tests/
  tsconfig.node.json        # covers vite.config.ts (Node, not browser)
  vite.config.ts            # the build AND the Vitest block — no vitest.config.*
  src/                      # the build's root
    global.css              # hand-written stylesheet 1 of 2: resets only
    shell.css               # hand-written stylesheet 2 of 2: workspace layout
                            #   only; imported by the app entry alone
    shared/                 # api.ts (the client, apiPut/apiDownload, the two
                            #   exported decode helpers), sse.ts, apiError,
                            #   notReady, error rendering, IconButton,
                            #   AppProviders, notifyFailure, notifyWarning,
                            #   ConfirmModal, currentUser, MarkdownEditor,
                            #   importFile, embeddingFailure
    bootstrap/  index.html  main.tsx  ...   # FEAT-001
    login/      index.html  main.tsx  ...   # FEAT-002
    admin/      index.html  main.tsx  ...   # FEAT-003, FEAT-004, FEAT-005
    app/        index.html  main.tsx  ...   # FEAT-006 .. FEAT-017, FEAT-020
  tests/                    # mirrors src/; outside the build root (quick-reference.md)
    setup.ts                # harness source, not a test
  dist/                     # build output — outside the root
```

```ts
// vite.config.ts (shape)
// configDir = the directory holding vite.config.ts (frontend/)
plugins: [react()],                              // @vitejs/plugin-react
root: resolve(configDir, "src"),
build: {
  outDir: "../dist",                             // frontend/dist, relative to root
  emptyOutDir: true,                             // outDir lies outside root
  rollupOptions: {
    input: {                                     // ABSOLUTE paths, from configDir
      bootstrap: resolve(configDir, "src/bootstrap/index.html"),
      login:     resolve(configDir, "src/login/index.html"),
      admin:     resolve(configDir, "src/admin/index.html"),
      app:       resolve(configDir, "src/app/index.html"),
    },
  },
},
server: { port: 8193, strictPort: true, proxy: { "/api": "http://localhost:8184" } },
test: { root: configDir /* frontend/, so tests/ and tests/setup.ts are found */ },
```

**The build is rooted at `src/` — a deviation from this block's earlier form,
taken by user decision (2026-09-29, plan 002).** The block used to show the
default `root` (the package directory) with the literal relative inputs
`src/<entry>/index.html`. Built that way, Vite names each emitted document by its
input's path **relative to `root`**, and the first build emitted
`dist/src/<entry>/index.html` — which matches neither the emitted-layout contract
below nor `deployment.md`'s per-entry `location /<entry>/` blocks. The user chose
to root the build at `src/` rather than rename or move output after the fact.
Consequently:

- `root` is `frontend/src`; `build.outDir` is `frontend/dist` (`../dist` from the
  root) with **`build.emptyOutDir: true`**, because an output directory outside
  the root is otherwise neither emptied nor refused by Vite.
- `build.rollupOptions.input` keeps its four keys, but **each value is an absolute
  path resolved from the config file's directory**, so entry resolution does not
  depend on the working directory once the root is no longer the package
  directory. The input paths are **not** relative to the package root.
- The Vitest `test` block sets **its own root back to `frontend/`**, so the tests
  under `frontend/tests/` and the setup file are still found.

**The remaining Vite specifics**, which the block's `(shape)` label leaves partial
by design but no build can omit: `@vitejs/plugin-react` is the plugin; `base`
stays at its default; **`server.strictPort` is on**, so a busy 8193 fails loudly
instead of moving to 8194, where the proxy assumption silently stops holding; and
there is **exactly one** proxy rule, matching `deployment.md`'s "one prefix only".
**Knock-on of the root:** Vite's `publicDir` now defaults to `src/public`, which
does not exist yet — a feature that adds static assets puts them there or sets
`publicDir` explicitly.

### The emitted layout nginx depends on

The build emits exactly:

```
dist/bootstrap/index.html
dist/login/index.html
dist/admin/index.html
dist/app/index.html
```

which is precisely what `deployment.md`'s four per-entry `try_files` fallbacks
resolve against. **This layout is a consequence of the build's `root` being
`src/`** (above), so a later change to `root` or to the input values must re-check
it. It is the seam between the frontend build and the nginx configuration, and
getting it wrong is invisible until deployment — as plan 002's own first build
showed. The half of the seam that is **not** this doc's — serving the `app`
document at `/` and on its client routes — is decided in `deployment.md`'s "The
app document at `/` — prod and dev" (prod: the image build copies
`dist/app/index.html` to `dist/index.html`). In dev the same mapping is done by a
serve-only Vite plugin (`apply: "serve"`) that rewrites navigation URLs, and
`root` and the four inputs are unchanged.

### `src/shared/` is one folder for all four entries — and that does not violate UC-066

`shared/` is a single folder used by every entry. This does **not** weaken the
"admin code never ships to the roleplayer" property below: UC-066 is satisfied by
**the entry split itself** — separate documents, separate bundles, separate route
tables — and `shared/` holds only **generic infrastructure** (the HTTP client,
error rendering, `IconButton`, the providers, the failure notifier). It never
holds an admin-specific component and never a route table naming `/admin`, which
is the concrete thing the roleplayer's document must not contain. Written down
here because the apparent tension is legible enough that every planner would
otherwise raise it again.

### Why four entries and not one bundle

Two independent reasons, both product-driven:

1. **Admin code never ships in the roleplayer's bundle.** FEAT-019/UC-066 says
   administrative surfaces expose no user content. The converse — that the
   roleplayer's document contains no administrative surface at all, not even
   dead-code-eliminated remnants, not even a route table naming `/admin` — is free
   once the entries are separate. It removes a class of bug where a role check is
   the only thing standing between a roleplayer and an admin view.
2. **The bootstrap state need not coexist with the authenticated shell.**
   ACT-003 acts **before a database exists** (UC-001, UC-002). The bootstrap entry
   has no session, no user, no characters and no API surface beyond `/api/health`
   and the bootstrap routes. Bundling it with the authenticated app would mean
   every store and every fetch in that bundle has to tolerate a world with no
   schema — a permanent tax on the main application to serve a screen that is
   shown at most once per instance and then never again (UC-003).

`login` is separate for a smaller reason, stated so it is not mistaken for
symmetry-for-its-own-sake: it is the only surface reachable unauthenticated on a
configured instance, so keeping it its own document keeps the authenticated app's
bundle out of the hands of an unauthenticated caller.

### Navigation between entries

Within an entry: `react-router-dom` 7. **Between** entries: a plain document
navigation (`window.location.assign`). The entries are separate documents, so
there is no shared router and no client-side transition between them. This costs a
full page load on login, which happens once per session, and buys the isolation
above.

The HttpOnly `SameSite=Lax` session cookie is carried automatically by that
document navigation — which is exactly why the split is safe and why no entry
contains auth-token plumbing (`overview.md`).

**The user menu's "Admin area" item is one of these navigations, not a router
link.** UC-071/US-093 puts an admin entry point in the workspace's user menu
(`workspace-shell.md`), and `/admin` is a different entry and a different document
— no shared router can route to it. It is a real `<a href="/admin">`, for the same
two reasons every cross-entry link is. Connected here explicitly because an item
sitting in a menu *inside* the app's router is exactly what someone converts to a
`<Link>` while tidying up, producing a client-side route that does not exist. The
item is **absent** for a roleplayer, not disabled (US-093.AC-2); the boundary is
still the backend's `require_role` (`backend-structure.md`, R5).

### Per-entry responsibilities

| Entry | Screens | Realizes |
|---|---|---|
| `bootstrap` | Create-new-database (with first admin), import-an-export, and the already-configured refusal | FEAT-001, UC-001, UC-002, UC-003 |
| `login` | Sign in — one form; being signed out *is* arriving at it (see "The `login` entry" below) | FEAT-002, UC-004, UC-005 |
| `admin` | Account list + lifecycle; LLM servers, connection test, enabled models, embedding designation; drift report + remediation; whole-database export **and** import — both built (plans 030, 031); the vector rebuild remains unbuilt (`fast/002`) | FEAT-003, FEAT-004, FEAT-005, FEAT-018 (admin half), UC-006, UC-007, UC-008, UC-009, UC-010, UC-011, UC-012, UC-013, UC-014, UC-015, UC-061 |
| `app` | The workspace — tree, stream and note wall (`workspace-shell.md`); the character page; settings; session configuration; my-search; user/character/session export **and** import — both built (plans 030, 031), the import effects in `app/importUploads.ts` | FEAT-006, FEAT-007, FEAT-008, FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013, FEAT-017, FEAT-018 (user half), FEAT-020 |

The `admin` entry contains **no** component that renders a character, setup,
session, entry or memo (UC-066). Not a preview, not a count of them per user, and
not a "sessions using this model" panel (R5 in `domain-rules.md`). Recorded here
as a frontend constraint as well as a backend one, because the temptation to add it
appears in the UI first.

### The `admin` entry

Full detail — routes, pages, per-page behaviour and the inherited conventions —
is in **`admin-surfaces.md`**. What belongs here is the entry's own shape:

- **Its own Vite input**: `src/admin/index.html` → `src/admin/main.tsx`, served
  under `/admin/` with its own nginx fallback (`deployment.md`).
- **`BrowserRouter basename="/admin"`** and a Mantine **`AppShell`** with `header`
  and `navbar` only — no `aside`, and no shell-level `padding` (each page brings
  its own `Container`). **`AppShell` survives here and only here**: the `app`
  entry's shell is now a hand-written CSS grid (`workspace-shell.md`), so the two
  entries no longer share a shell component. The asymmetry is deliberate — the
  admin area *is* a fixed navbar plus a main region, which is exactly what
  `AppShell` models, while the workspace's wall is not.
- **The basename and the URL differ by one character, on purpose.** nginx serves
  the document under `/admin/` **with** a trailing slash; the router's basename is
  `"/admin"` with **none**. The two strings belong to two mechanisms: React Router
  strips the basename before matching, so a trailing slash on the basename breaks
  the match. Two near-identical strings in two files is the shape of a bug someone
  "fixes" by making them agree — do not. `bootstrap`, `login` and `app` declare
  **no basename**; the `app` entry's routes are mounted at the origin root.
- **Flat `<Routes>`** — three pages plus a catch-all 404, no nested layout route
  and no `<Outlet/>`. The shell renders above the `<Routes>`. With three sibling
  pages and no per-page layout variation, a layout route adds a level of
  indirection and buys nothing.
- **The back-to-app link is a real `<a href="/">`**, not a router `Link` — the app
  area is a different document (see "Navigation between entries" above), and an
  anchor is also what makes middle-click and ctrl-click behave correctly.
- **Its modules, as built (plan 005), all live under `src/admin/` beside
  `main.tsx`**: the gate, the not-ready screen, the shell state, the nav table,
  the shell, the 404, the app component, the page store and the three drafts.
  This is plan 003's placement convention ("Where a store's file lives", below) —
  the admin entry is its first multi-page instance and confirms it.

#### Boot sequence — one `/api/me` round-trip before mount

```
main.tsx
  └─ await GET /api/me
       ├─ 401 / no session            ──► nothing of its own — the shared client
       │                                   has already navigated to /login
       ├─ session, role !== "admin"   ──► document navigation to /        (app area)
       ├─ session, role === "admin"   ──► createRoot(...).render(<AdminApp/>)
       ├─ not-ready (shared/notReady) ──► not-ready screen; re-probe every 2000 ms;
       │                                   navigates nothing
       └─ anything else thrown        ──► failure panel + manual retry;
                                           navigates nothing
```

**Five outcomes, not three** (plan 005). The diagram used to show three and so
contradicted `deployment.md`'s rule by omission:

- **The 401 branch performs no navigation of its own**: the shared API client
  has already navigated to `/login` (below). A second redirect path here would be
  a second owner of the same behaviour.
- **Not-ready** is exactly the `shared/notReady.ts` predicate — transport failure,
  or a malformed body at status ≥ 500 — rendering a not-ready screen that
  re-probes on the fixed 2000 ms interval and **navigates nothing**.
- **Failed** is anything else thrown, **including a well-formed 403 or 5xx
  envelope**: a failure panel with a manual retry, navigating nothing. This fifth
  outcome exists because a 403 must be treated as **neither a deny nor a
  not-ready**.

Nothing is rendered while the request is in flight — not a spinner, not the shell.
That is deliberate: it preserves the **no flash of admin content** property, at
the cost of a blank document for one request.

**This is a deviation from the sibling project, and the reason is architectural,
not stylistic.** BookWriter decodes a **JWT client-side before `createRoot`** and
so makes the same three decisions with no network call at all. RPHelper cannot:

1. the session is an **HttpOnly `SameSite=Lax` cookie**, so there is no token
   JavaScript can read; and
2. **FEAT-003 requires that disabling an account ends that user's sessions**,
   which a stateless token cannot do at any price — hence the server-side
   `auth_sessions` table (`data-model.md`). Even a readable token would still need
   a server round-trip to know whether the session is live.

The **pure/impure split is kept**, now async: a pure `resolveAdminAccess(currentUser)`
returning a decision, and an impure `enforceAdminAccess()` that fetches and
navigates on deny. The pure half is unit-testable with no network, no router and
no DOM. **`adminAccess.ts` obtains the user through `shared/currentUser.ts`**
(008 D1) — the `CurrentUser` type and the `/api/me` fetch moved to `shared/` once
a second entry needed them. The gate's behaviour is unchanged; only where the
fetch lives moved.

**The gate is UX only.** The authorization boundary is the backend's
`require_role(Role.admin)` on every admin route (`backend-structure.md`); removing
the gate must change nothing but the flash.

### The `bootstrap` entry

**Realizes:** FEAT-001, UC-001, UC-003

The counterpart to the `admin` entry's boot sequence (plan 003, hand-off amended
by plan 004):

- **One `GET /api/health` on mount, reading `configured` alone** — never
  `status` or `schema`, because a genuinely pre-bootstrap instance answers
  `status: "degraded"` (`backend-structure.md`'s `/api/health`).
- **Five states:** *probing* (neither the offer nor the refusal rendered), *the
  offer*, *the already-configured refusal* — with a real `<a href="/login">`, not
  a router link — *not-ready-yet*, and a *failure* that is not not-ready (the
  envelope's own message).
- **After a successful create, a document navigation to `/`.** The create
  response sets the session cookie (`backend-structure.md`'s bootstrap route
  surface), so the operator arrives signed in; there is no detour through
  `/login`. A create refused with `already_configured` flips the page to the
  refusal state instead.
- **No `basename`**, no stylesheet import of its own, and no API surface beyond
  `/api/health` and the bootstrap routes.
- **The refusal is UX over a server-side guard**, exactly as the admin gate is:
  `require_unconfigured` is the boundary.
- It adds **no notification call site**: every failure it has is a full-page
  state or the form's inline alert (`ui-conventions.md`'s notification rule).

### The `login` entry

**Realizes:** FEAT-002, UC-004, UC-005, US-006.AC-3

- **No request on mount at all** — no `/api/me`, no probe, no gate. One form, one
  route (`POST /api/auth/login`), every failure rendered **in place** in the
  form's general alert.
- **A document navigation to `/` on success, for both roles, with no role
  branch.** An administrator reaches `/admin` from the user menu, which is
  FEAT-020's surface.
- **No not-ready-yet state**, because it makes no request before the user acts —
  the condition that created that state for the `bootstrap` entry and the `admin`
  gate.
- **No disabled-account screen.** A disabled account receives the identical
  refusal, rendered identically, as a wrong password (US-006.AC-3,
  `invalid_credentials`). The entry's screen list used to name a
  "disabled-account message"; it must not be built.
- **"Sign out landing" is the sign-in form itself**, not a second screen. Nothing
  in `docs/product/` asks for a confirmation page.

### The `app` entry

**Realizes:** FEAT-020, ACT-001, ACT-002

The fourth entry's own shape, recorded because the other three each have a
subsection and this one has had a boot sequence since plan 008 (D2, D13):

- **One `GET /api/me` before the shell mounts**, through `shared/currentUser.ts`.
  **Five outcomes**, the same five the `admin` gate has, for the same reasons:

```
AppBoot (a component, mounted by main.tsx)
  └─ await GET /api/me
       ├─ nothing rendered while in flight   ──► not a spinner, not the shell
       ├─ 401 (code not_authenticated)       ──► nothing of its own — the shared
       │                                          client has already navigated to /login
       ├─ not-ready (shared/notReady)        ──► not-ready screen; re-probe every
       │                                          2000 ms + a manual retry; navigates nothing
       ├─ anything else thrown               ──► failure panel + manual retry;
       │                                          navigates nothing
       └─ success, EITHER role               ──► the shell, with the user as a prop
```

- **There is no role branch.** An administrator gets the workspace like anyone
  else and reaches `/admin` from the user menu (US-093), which is FEAT-020's
  surface. This is the mirror of the `login` entry's no-branch rule.
- **The 401 branch is keyed on the error *code* `not_authenticated`**, not on the
  status number — the branch-on-code contract below, applied at the one place a
  status would have been tempting.
- **The gate is a component (`AppBoot`) mounted by `main.tsx`**, not a loop inside
  `main.tsx`. The reason is testability rather than taste: a component can be
  mounted in a test with a stubbed client, while a top-level `await` in an entry
  module cannot be driven at all. It is also why the boot *state* lives in
  `appBootState.ts` and not `appBoot.ts` — see the case-collision rule at the top
  of this doc.
- **All six routes are declared from the start, flat, with the shell rendered
  above `<Routes>`** and a catch-all 404 **inside** the shell (008 D5). The 404 is
  inside rather than instead of the shell because a mistyped URL should still
  leave the roleplayer their tree.

## State — MobX 6, per-page stores, no context

**Pure data contracts.** Data is separated from code — a functional-like style,
despite MobX, at least for the data contracts. A store class is a data structure;
everything that derives from it or acts on it is a free function taking it.

```tsx
// SessionWorkspacePage.tsx — field and function names are illustrative, the shape is the rule
class SessionWorkspaceState {
  messages: ZoneMessage[] = [];
  status: "idle" | "loading" | "ready" = "idle";
  constructor(readonly sessionId: string) {     // string — see "Ids are strings" below
    makeAutoObservable(this, {}, { autoBind: true });
  }
  // observable fields ONLY — no methods, no computed getters
}

// a derivation: pure, takes the data object, still reactive under observer
export function isZoneEmpty(state: SessionWorkspaceState): boolean { ... }

// an effect: free function, data object + optional signal, runInAction, abort-aware
export async function loadZone(state: SessionWorkspaceState, signal?: AbortSignal): Promise<void> { ... }

export const SessionWorkspacePage = observer(function SessionWorkspacePage(
  { sessionId }: { sessionId: string },
) {
  const [state] = useState(() => new SessionWorkspaceState(sessionId));
  return <SessionStream state={state} />;      // passed explicitly as a prop
});
```

Four rules:

1. **A data class holds observable fields only** — `makeAutoObservable(this, {},
   { autoBind: true })` in the constructor, initial values, and nothing else.
2. **No methods, and no computed getters either.** Derivations are **pure free
   functions taking the data object**. They remain reactive: an `observer`
   component that reads observables through a plain function still tracks them.
3. **All effectful work is a free function taking the data object plus an
   optional `AbortSignal`.** Each one `runInAction`s its writes — an `await` ends
   the enclosing action, so a post-await write outside `runInAction` is untracked
   — and each **early-returns on an aborted signal before writing**, so a response
   that arrives after unmount cannot write into a dead store.
4. **Unchanged from the inherited convention:**
   - **one store per page**, instantiated via `useState(() => new XState())`.
     `useState` with an initializer, not `useMemo` — `useMemo` is a cache with no
     guarantee of identity, and a store whose identity can change silently is a
     source of lost in-flight state;
   - **stores passed explicitly as props, no React context.** Reading a
     component's props tells you exactly which store it touches, and a store's
     lifetime is visibly the page's; context would make both invisible and would
     let a child reach a store the page did not intend to give it;
   - **components that read observables are wrapped in `observer`.** A component
     that is not an `observer` must not read an observable — the resulting missed
     render is the hardest bug in this stack to find.

**The payoff:** validation and every other derivation are testable by
constructing a value and calling a function, with no render and no network; and
anything that can fail, await or navigate is visibly a call rather than a method
reached through an object.

### Five conventions the four rules leave open

Each was decided once, in code, and is written down here so the next screen copies
it rather than choosing again.

- **A component writes a field inside `runInAction` at the input's `onChange`**
  (plan 009, step 007): `runInAction(() => { state.name = value; })`. **State
  modules export derivations and effects, not setters.** The alternative — a pair
  of setter free functions per field — adds a function per field for exactly the
  same effect, and makes the module's surface grow with the form.
- **A new list store uses the four-value status ladder** (plan 009, step 004).
  The repo has two shapes and they are not equivalent: `admin/usersPageState`
  keeps `status: "idle" | "loading" | "ready"` plus an `errorMessage` string and
  guards its loading write with `if (state.status !== "ready")`;
  `charactersState` uses **`"idle" | "loading" | "ready" | "failed"`** with **no
  message field** — because every failure has its own place in the UI
  (`ui-conventions.md`) — and an **unconditional** `"loading"` write, so a retry
  visibly shows loading. **Copy `charactersState`.** The explicit `"failed"` value
  is what lets a page render a retry without inventing a fourth state out of
  "ready with no rows".
- **The submit effect has one shape** (plan 009, step 006), generalised from
  `admin/createUserDraft.ts`: an in-flight guard → `runInAction` setting
  `"submitting"` and clearing the error **before** the request → `try` / `catch`
  with the two abort checks → `finally` returning to `"idle"` unless aborted →
  **success handling after the `try`/`finally`**, so the server's returned row is
  applied only once the state is back to idle. Four effects in one module already
  repeat it. Where two effects write the same slice they share a private helper
  (archive and restore do); where they write different slices they do not (create
  adopts the draft, save preserves it).
- **One sanctioned non-observable field per store**, and only for non-data
  handles (019 D12): the compose **`AbortController`** and its wound-down
  **promise** live on `StreamState` through a `makeAutoObservable` override of
  `false`. They are not data — nothing renders them, and making a controller
  observable would mean every token write touched an observable nobody reads.
  `isStreaming` is **derived from the streaming-text field** instead, which is
  data. Named as sanctioned because rule 1 says fields are observable, and an
  unexplained `false` override reads as a mistake.
- **View state stays component-local, with the lifetime of its mount.** Modal
  open/target flags (`forms-and-lists.md`), and equally a tool block's or a
  thinking block's expanded flag and **a settled entry's discussion group,
  including the rows it has fetched** (022 D5, D11). The reasoning is the modal
  rule's: it has no meaning outside the component that renders it. The payoff is
  concrete in one place — because the flag is initialised once per mount, the
  live-reply-to-persisted-row swap collapses the blocks by **remounting** rather
  than by any code that closes them (`workspace-shell.md`).

### Which store a list belongs to — scope, not size

Three precedents, in the order they were set, because the choice recurs on every
screen:

| Shape | When | Example |
|---|---|---|
| **Workspace-level** — created in `App`, passed as props | two or more regions of the shell read the same rows | **`CharactersState`** (009 D11): the tree and the character screen. **`SessionsState`** (011 D15): the tree's session level |
| **Section-owned** — created with `useState`, keyed by the parent id | nothing outside the section reads it | **`SessionsSectionState`** (011), the character page's Setups section (010 D11), `characterComposerState.ts` and `characterConfigState.ts` (018) |
| **Page-owned** — one store per route | the page is the only reader | `app/streamState.ts` (013 D13), `app/searchState.ts` (029), `admin/usersPageState` |

**A section mutation applies the returned row to both stores where both exist**
(011 D15), and the rule that makes that safe is: **effects take the workspace
state as a parameter, never hold it as a field.** A store holding another store is
a hidden edge in the dependency graph and makes the section untestable on its own.

**Mutations apply the server's returned row through one upsert rule rather than
refetching the list** (009 D11) — which is the narrowed re-load
`forms-and-lists.md` describes, not an exception to it.

### Where a store's file lives

Precedent set by FEAT-001 (plan 003), extended by FEAT-002 (plan 004):

- **A page's state and draft modules live under the entry's own folder, beside
  `main.tsx`** — `src/bootstrap/bootstrapState.ts`,
  `src/bootstrap/createAdminDraft.ts` — **with the pure derivations and the
  effectful free functions in the same module as the data class they operate
  on.** A store is a data class plus free functions over it, which is one
  subject; and the entry folder is already the unit of bundling, so a
  single-entry store has no business in `shared/`.
- **A page whose entire state *is* its form holds a draft module and no
  page-state module** — `src/login/loginDraft.ts`, with no `loginState.ts`. A
  store holding no field the draft does not already hold is a store somebody will
  later find a use for. The convention is "one subject, one module", not "one
  page, two modules" — do not add an empty page store for symmetry.

The `app` entry's modules, as built, so a reader can find one without a search.
Every one of them is a data class plus its own free functions, or a pure module
with no class at all:

| Module | Holds |
|---|---|
| `app/appBootState.ts` | the boot state above |
| `app/shellState.ts`, `app/workspaceLayout.ts`, `app/treeCollapse.ts` | the shell's state and two of the three pure persistence modules (`workspace-shell.md`) |
| `app/composerHeights.ts` (suggested name; **not yet built**, 2026-10-08) | **pure** — the third persistence module: the two composers' dragged heights (`workspace-shell.md`) |
| `app/charactersState.ts`, `app/sessionsState.ts` | the two workspace-level list stores |
| `app/sessionScreenState.ts`, `app/sessionsSectionState.ts` | the session screen and the character page's Sessions section |
| `app/streamState.ts`, `app/streamApi.ts` | the stream's store (one per `SessionStream` mount) and its client — seven calls, ids as strings |
| `app/parens.ts` | **pure** — the client port of the `(( ))` rules, used by the preview and the zone painting only (R12) |
| `app/plainText.ts`, `app/pasteCost.ts`, `app/copyOut.ts` | **pure** stripper, **pure** paste estimate, and the one clipboard writer |
| `app/thinking.ts` | **pure** — splits assistant text into think and answer segments (022 D4) |
| `app/memoReach.ts`, `app/memoReorder.ts`, `app/memoDnd.ts` | the reach derivation (R3's twin), the pure drop decision plus its effect, and the shared sensors + announcements |
| `app/noteWallState.ts` | the wall's data class and free functions |
| `app/translationState.ts` | one `TranslationState` per `SessionStream` mount, with flick / cancel / invalidate / dispose as free functions (023 D13) |
| `app/characterComposerState.ts`, `app/characterConfigState.ts` | two section-owned stores on the character page |
| `app/searchState.ts`, `app/searchApi.ts` | my-search's page store and client |
| `app/importUploads.ts` | the three roleplayer import effects (plan 031) |
| `app/MessageBody.tsx`, `StreamRecord.tsx`, `ZoneList.tsx`, `KindSwitch.tsx`, `Composer.tsx`, `SessionStream.tsx`, `AssistantBody.tsx`, `ThinkingBlock.tsx`, `ToolBlock.tsx`, `LiveMessage.tsx`, `DiscussionGroup.tsx`, `SearchScreen.tsx` | the stream's components |

**Three localStorage keys, three pure modules, and a written reason for not being
one** (008 D8, 011 D7, extended 2026-10-08): `rphelper.workspace-layout` in
`app/workspaceLayout.ts`, `rphelper.tree-collapsed` in `app/treeCollapse.ts`, and
`rphelper.composer-heights` in `app/composerHeights.ts` (suggested name; not yet
built). The tree's collapsed set and the composer heights are **deliberately not
fields of the layout record**, because that reader drops unknown keys on write.
`workspace-shell.md` holds all three records' shapes, the total-read rules and the
storage-as-a-parameter mechanism that keeps the modules DOM-free.

**`app/translationState.ts` carries an accepted limitation** (023 D13): the client
translation cache is keyed by message id **for one mount**, so a preferred-language
change mid-mount keeps showing the old-language translation until the stream
remounts. The server's cache key is the full `(message, target language)` pair
(`data-model.md`), so nothing is wrong in storage — the staleness is one
component's, and it clears on navigation. Recorded rather than fixed because the
alternative is a cache that watches the configuration chain.

**This resolves a divergence, by user decision (plan 002).** This doc's example
used to carry `// observables, computeds, actions`, while `ui-conventions.md`'s
carried **no methods** with behaviour in free functions. A convention stated two
ways is one nobody can be held to; the second is the one chosen, extended to
getters. `ui-conventions.md`'s draft and page-state conventions now say the same
thing, and **the two must stay in step** or the contradiction simply moves.

### Why MobX over a reducer store — re-argued, because the old reason is gone

**The original justification no longer applies and is not repaired.** This doc
used to cite `ui-conventions.md`'s section (A) — the aside width pushed to a CSS
custom property by one `autorun`, so a pointer-move caused zero re-renders. That
section is **deleted**: there is no aside, no splitter, and no column in the
workspace resizes (`workspace-shell.md`'s reversal record). The composer's native
text-area handle (2026-10-08) does not revive the argument — the browser drags it
with no store involved, and its height is stored once, on drag end. The citation is
removed rather than re-pointed, because there is no text at the other end of it.
Said plainly so nobody hunts for a withdrawn paragraph, and so the deletion is not
mistaken for an editing slip.

Three reasons that do still hold:

1. **The SSE consumer appends tokens to an observable, not to component state.**
   A reply arrives as many small `token` frames (`llm-and-streaming.md`), and
   appending each to an observable message re-renders only the component observing
   that message — the tree, the wall, the settled record and every sibling message
   are untouched. A dispatch-based store's natural expression is a new state object
   per token, and holding the rest of the workspace still then becomes a
   memoisation exercise repeated at every level.
2. **Per-page stores with no context are a MobX-shaped design.** One
   `makeAutoObservable` class per page, passed as a prop, gets fine-grained
   observation with no provider, no selector and no equality callback. A reducer
   store's read path is a selector, and a selector is a second place the shape of
   the state is written down.
3. **Blur-save round trips touch one row.** Every edit in the workspace saves on
   focus loss and re-reads the edited row rather than the list
   (`workspace-shell.md`). Writing one field of one observable and re-rendering
   exactly that entry is the direct expression of the rule.

**No benchmark is claimed and none was run.** These are legibility arguments about
a stack already chosen in `overview.md`. The deleted (A) was this doc's one
measurement-shaped claim, and it is not replaced with an invented one.

## Routing inside the `app` entry

```
/                       the workspace with no session open — tree + empty stream,
                          and NO wall at all (US-095)
/sessions/:id           the workspace with a session open — tree | stream | wall
   ?entry=<messageId>     scroll that settled entry into view once + highlight 2000 ms
   ?notes=open            open the note wall on arrival
/characters/:id         the character page — two columns (UC-073, US-096); its
                          composer starts a session (UC-080, US-117)
/characters/new         the character draft page (UC-074, US-097)
/settings               the two languages and the user's own notes (US-092, UC-047)
/search?q=<text>        my-search results (FEAT-017)
```

All six are **declared flat and from the start**, with the shell above `<Routes>`
and a catch-all 404 inside it (see "The `app` entry" above).

**Every one of these routes renders the same shell.** The shell is not a property
of a route — the tree is present on all of them, and what changes is the centre
column and whether the wall exists. Geometry, collapse and the wall's two modes
are `workspace-shell.md`'s and are not described here.

**Only the screen component reads the URL; its children take props** (plan 029,
step 006). `SessionScreen` is the one module in the session chain that may call a
router hook: `SessionStream` and `StreamRecord` receive the focus entry id as a
**plain prop**, because they are mounted **router-free** in seven delivered test
suites and a `useSearchParams` or `useLocation` call inside either would throw
there. Stated as a rule rather than an observation, because the next feature that
wants a query parameter will reach for the hook at the component that needs the
value. Plan 029 is also the first caller of `useSearchParams` and the first
`scrollIntoView` in `src/`.

**`useNavigate` is the accepted form when a navigation follows from choosing a
control rather than from following a link** (plan 008, step 003). Every in-entry
navigation under `src/` before it was declarative (`component={Link} to=…`), and
the user menu's Settings item is the first imperative one — a `useNavigate()`
behind a `Menu.Item`'s `onClick`. It is deliberate, not an inconsistency: a menu
item that also carried an `href` would read as a cross-entry link and would sit
one attribute away from the admin item it is pointedly unlike
(`workspace-shell.md`). Recorded so the declarative-only reading of the existing
code is not mistaken for a rule.

Four corrections against the previous route list:

- **`/sessions/:id` is not "three panes in `Main` and `Aside`".** It renders one
  screen of tree | stream | wall, and **the wall is not an `Aside` in Mantine's
  sense**: the `app` shell is a hand-written CSS grid, not `AppShell`, because a
  panel that is an absolute overlay in one mode and a real grid column in the
  other fights `AppShell`'s navbar/main/aside model (`workspace-shell.md`).
  `admin-surfaces.md` keeps `AppShell` for the `admin` entry. The asymmetry is
  deliberate and is not an inconsistency to tidy up.
- **There is no separate session list and no separate character list.** The tree
  lists characters with their sessions, newest use first (UC-069, UC-026, US-088,
  US-089), so a route whose whole content is one of those lists would render the
  left column twice.
- **Setups have no route**, and that holds as built (010 D1). The character page
  holds the persona, notes, setups, resolved configuration and sessions in one
  place (US-096).
- **`/memos` is gone.** User-level notes live on the settings screen (US-092); the
  other three levels live on the wall (UC-072, UC-075).

**`/settings` is built** (017 D15) — `SettingsScreen`, with the Languages form and
the user level's notes (`workspace-shell.md`).

**`/characters/:id` also starts sessions.** Writing in the character page's
composer (`workspace-shell.md`) posts **once**, to
`POST /api/characters/{id}/sessions` (`session-stream.md`), which creates the
session and seeds its current zone in one transaction. What the client must **not**
do is create the session and then post the message as two calls — that sequence can
fail between them and leave an empty session behind, which is why the backend
exposes one route.

As built (018 D5), through `app/sessionsApi.ts`'s start-with-message call:

- **The response's eight `Session` keys are applied to the workspace
  `SessionsState`**, so the tree shows the new session without a list reload.
- **The client pushes `/sessions/<id>`** — push, not replace, so **Back returns to
  the character page** the roleplayer started from. (Contrast the draft page
  below, which replaces for the opposite reason.)
- **The returned opening message is not used to pre-seed the stream**, because the
  session screen re-reads its zone on mount anyway. Seeding it would be a second
  source for rows the next request overwrites.
- The id is a **`string`** and is used exactly as received — see "Ids are strings"
  below; there is nothing to parse and nothing to assemble client-side, and the
  `useParams()` value on arrival is that same string. The navigation is an
  in-entry router navigation, not a document navigation: the character page and
  the workspace are both the `app` entry.

**`/characters/new` is this doc's design inference, not a requirement**: UC-074 and
US-097 require a **draft page** that persists nothing until the roleplayer types
something, and a page needs an address. The path is architecture's to choose; the
behaviour is the product's. **As built** (018 D6) it is the draft page in full —
**no Create button**, the character created on the **first committed non-blank
name**, then a **`replace`** navigation to `/characters/<id>` so Back does not
return to a draft page for a character that now exists. Plan 009's interim
explicit **Create** is gone. `workspace-shell.md` holds the page's behaviour.

**My-search's URL carries the query** (029 U4, D8, D9). `/search?q=<text>`, and
the query lives in the URL rather than in a store **because the tree remounts when
it expands** — a query held in component state would vanish on a collapse toggle.
A blank `q` makes **no request**. The trigger is reachable from any screen
(UC-058) and from the tree expanded or collapsed (US-118): a **text input in the
tree header** (Enter submits) and the **icon button on the collapsed rail**, which
navigates to `/search`. The results page focuses its own box on every arrival, so
arriving from the rail lands the cursor where the roleplayer is about to type.

**Archived objects are reached by an explicit toggle, never by a separate route** —
archive is a filter on the working list, not a different place (R6). **Placement
is section-local, and the `_TBD:` that asked where is closed in full** (009 D4,
010 D4, 011 D5, 018 D11): the tree header's "Show archived" for characters, the
Setups section's "Show archived setups", the Sessions section's "Show archived
sessions". **None is persisted.** `workspace-shell.md` holds the rendering and the
reason persistence was declined.

## Ids are strings, everywhere in the frontend

**An id is a TypeScript `string` end to end. Never a `number`. No arithmetic, no
`parseInt`, no numeric sort.** A section rather than a bullet because this doc
owns the API client and the stores, so it is where a reader looking for "what type
is an id" will come — and because it is the single most forgettable rule in the
doc set: it fails silently, late, and in production data rather than in a test.

The reason is `data-model.md`'s **Identifiers** section, not restated beyond its
one load-bearing fact: RPHelper's keys are snowflakes, and a snowflake passes
`Number.MAX_SAFE_INTEGER` (2^53−1) roughly 25 days after the epoch, so an id
deserialized into a JS `number` rounds — possibly onto another row's id. Nothing
throws and nothing warns.

- **The API client never reviver-parses or coerces.** `JSON.parse` leaves an id as
  the string the backend serialized (`backend-structure.md`'s JSON id boundary),
  and it stays that string through the store, the props, the route params and back
  into a request body. `useParams()` already hands back `string`; that is correct,
  not a conversion someone forgot.
- **`id: number` on a type, a prop, a store field or a route param is a defect.**
  **The rule is enforced by a test, not by a habit** (plan 002). The project has no
  linter (`overview.md`), so a test is the only automated form available, and it
  costs no dependency. A test under `frontend/tests` scans every `.ts` and `.tsx`
  file under `frontend/src` and fails naming the offending file and line. It
  catches three patterns:
  - an `id`/`Id`-suffixed binding annotated `number` or `number[]`;
  - `parseInt`;
  - `Number.parseInt`.

  **There is no exception list and no suppression comment** — a genuine need
  changes the architecture first. **What it deliberately does not catch:** numeric
  sort and arithmetic on ids, which are not textually detectable without type
  information and stay a review matter. The scan is scoped to `frontend/src` and
  the tests live outside it, so no fixture can trip it and no exclusion list is
  needed.
- **SSE frames are bound by the same rule.** `done.message_id` arrives as a
  decimal string (`llm-and-streaming.md`) and is used as one. A frame is the
  easiest place to overlook — it is hand-built JSON, not a serialized model.
- **Ordering never comes from an id.** The backend orders the stream by `id`
  (`data-model.md`); the client renders the order it was given. A client-side sort
  on an id string is lexicographic and wrong; on a parsed id it is the defect
  above.
  **The one client-side sort in the `app` entry obeys this** (011 D6, D15): the
  tree orders sessions, and characters by newest session use, by comparing
  **fixed-width `last_used_at` text** — which sorts correctly as a string because
  the timestamp format is fixed-width by schema rule (`data-model.md`). An id was
  the tempting key here, since the tree already has one on every row, and it would
  have been wrong twice over: lexicographically as a string, and roundingly as a
  number.
- **One divergence between the client port and the server, and it is accepted as
  display-only** (013 D16): `app/parens.ts` trims with JavaScript's `trim`, while
  the server uses Python's `isspace`. The two disagree on a handful of rare code
  points. It is accepted because the client's copy is a **preview and is never
  authoritative** (R12), so the worst case is a preview sentence that disagrees
  with what settle does on a character almost nobody types. Recorded so the
  difference is not "fixed" into a hand-built code-point set, which would be a new
  thing to keep in step with CPython.

The one place in the doc set that contradicted this rule — the admin page-state
example writing `disableUser(state, id: number, ...)` — has been corrected to
`id: string` (it now lives in `forms-and-lists.md`). **That `_TBD:` is closed**;
the rule here remains the authoritative statement of it.

## The API client

One module in `shared/`, used by every entry:

- Always calls **same-origin `/api/...`**. There is no base-URL variable and no
  environment-dependent host; dev and prod are both single-origin
  (`deployment.md`).
- Sends cookies by default; sets no `Authorization` header, because the session is
  an HttpOnly cookie (FEAT-002).
- On a non-2xx, parses `{ error: { code, message, detail } }`
  (`backend-structure.md`) into a typed `ApiError` and **throws it**, so call sites
  branch on `error.code` rather than on a status number or a message string. The
  codes the UI may branch on are `model_not_enabled`, `no_model_enabled`,
  `model_not_chosen`, `no_embedding_model`, `llm_unreachable`,
  `translation_failed`, `zone_empty`, `zone_not_empty`, `nothing_to_reopen`,
  `message_not_editable`, `already_configured`, `not_authenticated` and
  `invalid_credentials`.
  **Most of them are not branched on, and that is fine.** A code reaches
  `notifyFailure` and renders its server message unless some surface needs to do
  something *different* for it. As built: the stream branches on none of
  `zone_empty` / `zone_not_empty` / `nothing_to_reopen` / `message_not_editable`
  — all four go through `notifyFailure` uniformly (013 D14); `translation_failed`
  likewise, with no branch (023 D5); plan 017 branches on `model_not_enabled`
  alone, for the model picker's inline failure line, and the compose's
  presentation of the three model errors is plan 021's.
  **`discussion_not_resumable` is gone** — it named a table
  that no longer exists and a condition that has changed; `zone_not_empty` is its
  replacement and the rename is not cosmetic (`backend-structure.md`).
  **`account_disabled` is gone too** (plan 004): no backend code raises it, so a
  branch on it could never be exercised. `invalid_credentials` replaces it, and
  the only surface that branches on it is the `login` entry's form, which renders
  **one fixed message** that never says which of the three causes applied
  (US-006.AC-3).
  **Where a failure is not already rendered in place, its reason is shown as a
  transient notification** (US-044.AC-4, `ui-conventions.md`) — the client throws
  and renders exactly as before; what changed is only the surface some of these
  codes land on.
- A `401` triggers a document navigation to `/login`. A `403` does not — it is a
  genuine authorization failure and is rendered, not redirected. (This is why the
  login route's own refusal is a 400, never a 401 — `backend-structure.md`.) The
  navigation target is exactly `/login`, without a trailing slash, which nginx
  must resolve — an open seam recorded in `deployment.md`.

### The verbs and the two non-JSON additions

`shared/api.ts` grew three times, and each addition stayed **inside** the client
rather than becoming a module of its own — because each needs the **one** error
decode, the 401 → `/login` navigation and the `client_*` codes below:

| Addition | Plan | What it is |
|---|---|---|
| `apiPut` | 016 D12 | an ordinary verb, same decode and error mapping as the others; the note-reorder route is the only caller |
| **two exported helpers** | 019 D10 | the **non-2xx decode** (401 navigation included) and the **rejection mapping** (an abort propagates unchanged, anything else becomes `client_transport_failed`). `apiRequest` and the SSE consumer are their two callers, so the decode exists once for both transports |
| `apiDownload(path, signal?)` | 030 | the **first non-JSON call**: it reads a blob, saves it through a temporary object URL and an `<a download>` anchor, and resolves to `{ filename, size }`. The filename comes from `Content-Disposition`, falling back to `rphelper-export.json`. An abort is not wrapped |

**`shared/importFile.ts` is the one module that sits beside the client rather than
inside it** (plan 031): `readExportFile` reads the chosen file **as text and parses
it client-side**, and `postExportFile` sends the parsed object through the ordinary
`apiPost`. **There is no `FormData` and no multipart anywhere in the product** —
the import body is JSON like every other body, which is why the practical size
bound is nginx's `client_max_body_size` (`deployment.md`) rather than an upload
pipeline. It adds **one** client code, **`client_unreadable_file`** (status `0`,
"The chosen file is not a readable export."), for a file that is not JSON at all;
anything that parses but is not an export is the server's `export_invalid`
(`transfer.md`).

**`shared/embeddingFailure.ts` maps two codes to sentences** (024 D10):
`no_embedding_model` and `llm_unreachable`, for the **authoring** surfaces that can
degrade — a memo, a character, a setup. It is a presentation module, not a branch
table: the codes are shown, not handled. The stream's own types carry the optional
`search_coverage_incomplete` flag that drives the coverage banner
(`workspace-shell.md`).

**An inline-failure page needs the generic fallback text exported** (plan 029,
step 004). The house sentence for a thrown value that is **not** an `ApiError` —
"Something went wrong. Please try again." — lives as a module-private constant
inside `shared/notifyFailure.ts`, and my-search's results page must not notify, so
`searchState.ts` repeats the literal. **The duplication is the defect to remove,
not the rule**: export it from `shared/apiError.ts` (or from `notifyFailure`) the
next time a page needs it, so the two channels cannot drift into two different
sentences for the same condition.

### Not-ready-yet — one shared classification

**`shared/notReady.ts` exports one pure predicate** answering whether a thrown
value is the not-ready-yet condition (plan 003):

```
not-ready  =  code client_transport_failed
           or code client_malformed_error  with status >= 500
```

- **Widened from "a 502"**, deliberately. `supervisord` has no wait-for ordering
  (`deployment.md`); 502, 503, 504 and a response that died mid-body are the same
  "running but not answering" condition, and keying on one number would make the
  screen depend on one proxy's choice.
- **A well-formed backend envelope can never match**, whatever its status,
  because its code is a backend code — a real 500 from the application is a
  failure, not not-ready. An abort never matches either (it is not wrapped).
- **Retry posture, as FEAT-001 chose it:** a fixed **2000 ms** re-probe,
  **uncapped, no backoff**, plus a visible manual retry, all cancelled on
  unmount.

`deployment.md` states the requirement in two places — the bootstrap entry's
not-ready-yet state and the admin gate's "a 502 is not a deny" — and this is what
the rule *is*. **Both consumers use this predicate**: the `bootstrap` entry
(plan 003) and the `admin` gate (plan 005, the boot sequence above). Any further
surface that needs the condition uses it too, rather than re-deriving it.

### The `ApiError` shape

`ApiError` is a class extending `Error`, carrying:

- **`code: string`** — the branch key;
- the inherited **`message`**;
- **`detail`** — an object of unknown values, defaulting to empty;
- **`status: number`** — the HTTP status.

**Call sites branch on `.code`, never on a status number and never on a message
string.** `status` is carried for diagnostics and for the by-status half of a
draft's field mapping (`forms-and-lists.md`), not as a branch key. **An exported
type guard is the one sanctioned way a `catch` block narrows** to `ApiError`. The
doc used to say the client throws "a typed `ApiError`" without defining the type;
four features would otherwise have defined four.

### Every failure is an `ApiError` — 5xx, malformed bodies and transport failures

So that **every** call site can branch on `.code`, the client produces an
`ApiError` for every way a call can fail, not only for a well-formed error body:

| Situation | `code` | `status` |
|---|---|---|
| non-2xx with a well-formed envelope | the backend's own code | the real status |
| non-2xx whose body is absent, not JSON, or not the envelope | `client_malformed_error` | the real status |
| `fetch` itself rejects | `client_transport_failed` | `0` |

Both synthetic codes are prefixed **`client_`** so no reader mistakes one for a
backend code, and neither collides with `backend-structure.md`'s table. Without
this, a 502 from nginx and a dropped connection each reach call sites as a
different shape, and the branch-on-code contract quietly stops holding at exactly
the moments it matters. The admin gate's "a 502 is not a deny" rule is
`admin-surfaces.md`'s and is untouched by this table.

**An abort is not an error and is not wrapped.** The original abort rejection
propagates unchanged, so `signal.aborted` checks and the early-return-on-abort
rule (the MobX rules above) work as written. This is the same reasoning as the
SSE consumer below, where a stop is deliberately not a failure.

### One decode in the client, one field-mapping per draft

The error path has exactly two steps, and each happens in exactly one place:

1. **One decode, in the client.** It parses the envelope and throws a typed
   `ApiError`. Nothing else parses an error body.
2. **One field-mapping, per draft.** `forms-and-lists.md`'s `submitX` free function
   maps that `ApiError` onto `serverErrors` field keys **by status or code, never
   by parsing prose**; anything unmappable lands on the general key.

The second half is where the mistake actually gets made: a store that re-decodes
the response produces a second, divergent error shape.

`model_not_enabled` gets a dedicated presentation, because it is product
behaviour and not an incident: UC-012 requires the roleplayer be able to fix it by
choosing another model through FEAT-013's chain, and the error's `detail` names
which level set the dead reference — so the UI links straight to that level's
configuration screen. **It never offers "use a different model just this once"**,
because that is the silent fallback R4 forbids.

## The SSE consumer

**Realizes:** FEAT-010, UC-032, UC-034, UC-083, UC-085, US-132, US-133

One module in `shared/`, speaking to exactly one route:
**`POST /api/sessions/{id}/zone/compose`** (`session-stream.md`). The old
`/api/discussions/{id}/messages` is gone with the `discussions` table — there is
no discussion id to address, and the zone has no id of its own either, so every
zone operation is addressed through its session. The sibling append route
`POST /api/sessions/{id}/zone/messages` makes no model call and returns JSON; it
goes through the ordinary API client, not this module — the whole point of the two
routes being two routes.

The request is a **POST with a JSON body**, so native `EventSource` (GET-only)
cannot be used — the roleplayer's message would have to go into a URL. Instead:

```ts
const controller = new AbortController();        // the stop control aborts this
const res = await fetch(`/api/sessions/${sessionId}/zone/compose`, {   // id: string
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
  signal: controller.signal,
});
const reader = res.body!.getReader();
const decoder = new TextDecoder();
let buffer = "";
for (;;) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const frames = buffer.split("\n\n");
  buffer = frames.pop() ?? "";          // keep the trailing partial frame
  for (const frame of frames) handle(parseFrame(frame));
}
```

Four details that are all load-bearing:

- **`TextDecoder` with `{ stream: true }`**, because a chunk boundary can land in
  the middle of a multi-byte character — and the RP language is frequently not
  ASCII, so this is a routine case here, not an exotic one.
- **Frames are split on `"\n\n"`** and the trailing fragment is kept in the
  buffer. A frame is not guaranteed to arrive whole.
- **The consumer is cancellable** via an `AbortController`, and that abort **is**
  the stop control (`IconPlayerStop`, UC-085). There is no stop route and nothing
  to notify — the server detects the closed connection, persists the partial
  assistant text as an ordinary zone row and unwinds
  (`llm-and-streaming.md`, `session-stream.md`). The controller is owned by
  the same store that owns the in-flight message, so the control knows whether
  there is anything to stop.
- **A stream that ends without a `done` frame is a failure — unless this client
  aborted it.** That qualifier is new and it is load-bearing: a stop is now a
  fourth way a stream ends (`llm-and-streaming.md`'s termination table), and the
  old blanket inference would render `llm_unreachable` for an action the
  roleplayer just took deliberately.

  **The distinction is made on the consumer's own state, never on the stream.**
  The consumer records that it called `abort()` — equivalently, it catches the
  `AbortError` the `fetch()`/`reader.read()` rejects with and checks
  `controller.signal.aborted`. There is nothing in the bytes to inspect, which is
  the point: to the server the three silent cases are identical, and the client
  is the only party that knows which one happened.

  ```
  stream ends, no `done`  ──┬── signal.aborted  ──►  a stop: no error is shown
                            └── otherwise       ──►  llm_unreachable
  ```
- **After a stop the consumer re-reads the zone** —
  `GET /api/sessions/{id}/zone` — because no `done` frame arrived and therefore
  no `message_id` names the persisted partial row (US-132.AC-1). This is
  `forms-and-lists.md`'s never-optimistic re-load rule applying to a mutation
  whose result the client did not observe, not a special case; the same rule
  already governs every other mutation in the product.
- **The stop clears nothing.** R10's prohibition covers this path too: aborting
  must not discard the in-flight assistant text already rendered, the roleplayer's
  own zone messages, or the settled record — the reload replaces the in-flight
  message with the persisted row, it does not empty the zone first.

### The module's own contract — one function, four outcomes, never a rejection

As built (019 D9) the consumer is **`shared/sse.ts`**, one function that **never
rejects** and resolves to exactly one of four outcomes:

| Outcome | Carries | Decided by |
|---|---|---|
| **done** | the message id, a **decimal string** | a `done` frame |
| **error** | an `ApiError` | an `error` frame, or a non-2xx decoded **exactly as `apiRequest` decodes it** (the shared helper above), or a malformed frame → `client_malformed_error` |
| **stopped** | nothing | `signal.aborted` — the consumer's own state, never the bytes |
| **unexpected end** | nothing; the caller renders it as `llm_unreachable` | the stream ended with no terminal frame and no abort |

Two frame-level rules go with it: **an unknown `event` is skipped**, not treated
as an error, so the server can add a frame type without breaking an old client;
and **frames after a terminal one are never delivered**, so a trailing byte cannot
reopen a finished exchange.

**The controller is per compose, and it lives in a non-observable handle** on
`StreamState` beside a wound-down promise (019 D12, and the sanctioned
non-observable field above). It is **linked to `SessionStream`'s mount
controller**, so unmount aborts a compose in flight — and a **mount abort writes
nothing**, which is what keeps a response arriving after navigation from writing
into a dead store. `isStreaming` derives from the streaming-text field, not from
the controller.

### Frame handling — what each frame writes

Mapped onto the **stream** store (`workspace-shell.md` for what it renders):

- **`token` appends to a dedicated observable streaming-text field on
  `StreamState`** — **not** to a placeholder row in `zone`. This is the final
  shape (019 D11, settled by 022 D6 and user decision U4), and the reason is
  concrete: 013's `ZoneList` offers an edit control on **every** zone row, and a
  placeholder's **client-minted id must never reach
  `PATCH /api/messages/{id}`**. The streaming text renders **read-only** as the
  live reply, and every outcome of the stream replaces it with the server's rows
  by a **zone re-read**; **the persisted row is then editable like any other zone
  message.**
  **"Edit while streaming" is deliberately not offered**, because an edit would
  **race the server's own write of that row**. That narrowing of `US-115.AC-1`'s
  streaming half is recorded as **`docs/plans/defects.md` D-02**, together with
  the open alternative reading of the criterion; `workspace-shell.md` carries
  both halves. Nothing here is an open design question — 019 deferred the call to
  022 and 022 made it.
- **`tool_start` / `tool_result` / `tool_fail` maintain an observable live tool
  list on `StreamState`, keyed by call id** — `running` → `ok` / `failed`
  (022 D7, superseding 019 D18). **They never write `zone`.** The list is
  **cleared in the same action as the streaming text**, when the re-read brings in
  the persisted `role='tool'` rows (`data-model.md`) — so there is exactly one
  moment at which the live view becomes the stored view, and no window in which
  both are rendered. The persisted rows are what a reload shows, which is why the
  live list can be discarded outright rather than reconciled.
- **`regenerate` is a textless compose that shares the compose run** (022 D8) —
  the same handle, the same stop, the same settle-mid-stream behaviour, the same
  outcome table. **It never touches the composer's draft.** It is a second entry
  point into one effect, not a second effect.
- **`error` renders a visible failure without discarding anything already in the
  zone or in the settled record above the ruler** (R10, UC-032) — the one rule
  here that is a product guarantee rather than a transport detail.
- **`done` finalises**, and its `message_id` is a **decimal string** (above).

The protocol itself is defined in `llm-and-streaming.md` and the server half in
`session-stream.md` — this module's contract is only that it never drops
roleplayer text on any frame.

## Markdown

- **Editing** (memo bodies, character sheets): TipTap via `@mantine/tiptap`, plus
  `tiptap-markdown` for markdown in and out. This is what satisfies UC-043's
  markdown editor with live preview, and the editor's own rendering **is** that
  preview (US-056.AC-1) — there is no second preview pane.
- **Rendering** (notes shown read-only, settled entries and current-zone
  messages): `react-markdown`, which **is** a dependency as of plan 013 — this
  doc named the library before it was installed.
- **Search result snippets render as plain text, not markdown** (029 D7). This
  **corrects** the older line that listed them under `react-markdown`: a snippet
  is a **cut fragment** of a markdown body and may open a structure it never
  closes, so rendering it would let one result's unterminated emphasis or code
  fence reformat the rest of the page.

Two libraries rather than one because the editing surface needs a document model
and a toolbar while the read surfaces need neither.

### One editor wrapper, and its two emit rules

**`src/shared/MarkdownEditor.tsx`** is the one wrapper (009 D3): a label, a
markdown `value`, `onChange(markdown)`, `readOnly`, and an optional **`autoFocus`**
(016 D9) over `@mantine/tiptap` + `tiptap-markdown`, importing the stylesheet
itself. **Every markdown editing surface reuses it** — notes (015), the user
level's notes on `/settings` (017), the character persona (018). **TipTap is
pinned to major 2**, because both peers bind to it and a routine install of 3
breaks them.

**The "never echo" rule, and the two library defaults that both go the wrong
way** (plan 009, step 005). `onChange` is emitted **from `onUpdate` only**, and
**every programmatic content or editability write passes `emitUpdate: false`**:

- `editor.setEditable(editable)` defaults `emitUpdate` to **true**;
- `editor.commands.setContent(content)` must be given `emitUpdate: false`
  **explicitly**.

Either default alone makes `onChange` fire on mount, which in a blur-save world
means an unedited note writes itself back to the server the moment it appears.
Recorded for every future consumer of the wrapper, because the symptom is a write
nobody asked for rather than a visible error.

### One renderer, three variants

**`app/MessageBody.tsx`** is the stream's only renderer (013 D5), with three
variants: **painted** (zone messages, where `(( ))` is marked up —
`workspace-shell.md`), the **decision card**, and **plain** (settled `partner` and
`turn` entries). The variant is chosen by `kind` and by which side of the ruler
the row sits on, never by re-parsing the text (R12).

**Assistant text is split before it reaches the renderer** (022 D4, D5) by a
**pure** client parser, `app/thinking.ts`, consistent with 021 D4's strip rule.
Think segments render as **plain text** — they are the model's scratch work and
marking them up would dress them as prose — and answer segments go through the
painted `MessageBody`.

## Bundle-level constraints worth stating

- **`@dnd-kit` is used for exactly one interaction — reordering notes within a
  level — at two mount points** (UC-076, US-102). The previous `_TBD:` here — "do
  not build reorder until a requirement asks for it" — is **closed**: US-102 is
  that requirement, and it is the project's first and only drag interaction
  (`workspace-shell.md`). As built the packages are **`@dnd-kit/core`,
  `@dnd-kit/sortable` and `@dnd-kit/utilities`** (016 D8). Five constraints come
  with it:
  - **A note cannot cross a level boundary by dragging** (US-103.AC-2), enforced
    in a **pure drop-decision function plus the drop effect**, not merely
    signalled in the drag preview.
  - The ordering column is **`memos.sort_key`**, scoped within `(scope, scope_id)`
    and nowhere wider (`data-model.md`) — the one mutable ordering in the schema.
    The `position` column this bullet used to cite **does not exist**:
    `data-model.md` dropped it, because `ORDER BY id` on a k-sortable snowflake is
    the stream order and nothing in `docs/product/` permits reordering entries.
  - **Reordering is not decoration: it changes what the system prompt contains**
    (R3, US-102, `llm-and-streaming.md`), which is why `@dnd-kit`'s keyboard sensor
    is required rather than optional (`ui-conventions.md`'s accessibility floor).
  - **There are two `DndContext`s — the note wall's and the character page's notes
    grid — and their configuration is shared, not duplicated** (018 D8). The
    sensors and the position-only announcements live in **`app/memoDnd.ts`**, so
    the two mount points keep **one** keyboard path. Two contexts with two sensor
    sets is how one of them silently loses its keyboard sensor.
  - Nothing else may use `@dnd-kit` without a requirement that asks for it.
- No component library other than Mantine, no Tailwind, no CSS modules, no
  styled-components (`overview.md`).

### The two stylesheets — the whole division

**Decided; this doc owns the convention.** There are **exactly two** hand-written
stylesheets and there is no third:

| File | Holds | Imported by |
|---|---|---|
| `src/global.css` | **resets only** | every entry — imported by **`shared/AppProviders`**, after Mantine's core and notifications stylesheets, and so reaching every entry transitively |
| `src/shell.css` | **the `app` workspace's layout only** — the shell grid and its `1px` gap, the `--navw` custom property and the collapsed-rail class that re-points it, the narrow-width overlay, the `(width < 820px)` media query, **and the session screen's stream/wall layout** | the **`app` entry** alone — imported directly by **`src/app/main.tsx`**, the one stylesheet an entry imports itself |

**`shell.css` grew by six selectors and no new media query** (016 D11). Plan 016
added the session screen's own grid — `.app-session`,
`.app-session.wall-pinned`, `.app-stream`, `.app-wall`, `.app-wall.wall-open` and
`.app-session.wall-pinned .app-wall` — which is still **workspace layout only** and
still **colourless**: the wall's background and drop shadow are Mantine's
(`Paper`). The table's older wording, "the three-column grid … only", understated
it; the boundary that matters is *layout, not decoration*, and
`tests/stylesheets.test.ts` is what checks it. `workspace-shell.md` lists every
selector the file holds and names the one colour token it is allowed.

**The narrow-width wall rule is the one layout condition that is *not* in CSS**,
and deliberately: it is a conjunction of a stored pin, a transient open flag and
the viewport, and CSS can see only the third. TypeScript reads the **same query
string**, exported as `NARROW_VIEWPORT_QUERY`, so there is one threshold and not
two (`workspace-shell.md`).

**Who performs the imports is fixed** (decided in plan 002). Resets must land
**after** Mantine's base sheet to win the cascade. Leaving that to
import-statement order in four separate entry modules would make the cascade
depend on a line someone can reorder while tidying; one file owns it instead. The
claim that `global.css` reaches every entry is unchanged.

**Everything else is Mantine** — theme tokens, `style` props and component props.
A rule that is neither a reset nor workspace layout belongs in neither file;
reaching for a third file, or for a `.css` beside a component, is the signal that
a Mantine theme token was the right answer.

The reason for a second file rather than a wider `global.css`: `global.css`'s
stated job is resets, and putting layout in it erodes a convention set
deliberately — once one layout rule lands there, the next has no argument against
it. The rules could not go inline either, because a grid template, a custom
property re-pointed by a class, and a media query are not per-element style; and
CSS Modules are forbidden above. `workspace-shell.md` carries the same decision
against the geometry it governs. The `_TBD:` this doc used to carry forward on
that doc's behalf is **closed**.

`shell.css` is imported by the `app` entry only, because no other entry has a
workspace — `admin`'s shell is Mantine's `AppShell` (`admin-surfaces.md`), and
`bootstrap` and `login` have no multi-column layout at all.
