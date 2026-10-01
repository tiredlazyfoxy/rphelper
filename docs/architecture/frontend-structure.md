# Frontend structure

**Realizes:** FEAT-001, FEAT-002, FEAT-003, FEAT-004, FEAT-005, FEAT-006,
FEAT-007, FEAT-008, FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013, FEAT-017,
FEAT-019, FEAT-020, ACT-001, ACT-002, ACT-003, US-006.AC-3

React 19 + TypeScript, built by Vite as **four separate entries**. Component
library, state library and icon set are fixed in `overview.md`.

**TypeScript only.** No `.js` / `.jsx` / `.mjs` / `.cjs` file is authored anywhere
under `frontend/` — config included — and neither tsconfig enables `allowJs` or
`checkJs`. Reason in `overview.md`; the rule itself is in the root `CLAUDE.md`.

**The `app` entry's visual shell is in `workspace-shell.md`** — the three columns,
all geometry, the note wall, layout persistence, and the anatomy of the stream and
the current zone. It is not described here, and the pointer that used to send
readers to `ui-conventions.md` for it is wrong: that file now holds only what is
*not* the shell. **The "two resize behaviours" it also named no longer exist** —
nothing in the workspace is user-resizable, and `workspace-shell.md`'s reversal
record says why they were deleted rather than moved. This doc holds the build, the
routing, the stores, the API client and the SSE consumer.

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
    shared/                 # api client, sse consumer, error rendering, IconButton,
                            #   AppProviders, notifyFailure, notReady,
                            #   ConfirmModal (plan 005)
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
showed. The half of the seam that is **not** this doc's — the catch-all `/`
fallback, for which no `dist/index.html` exists — is an open seam recorded in
`deployment.md`.

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
| `admin` | Account list + lifecycle; LLM servers, connection test, enabled models, embedding designation; drift report + remediation + vector rebuild; whole-database export/import | FEAT-003, FEAT-004, FEAT-005, FEAT-018 (admin half), UC-006..UC-016, UC-061 |
| `app` | The workspace — tree, stream and note wall (`workspace-shell.md`); the character page; settings; session configuration; my-search; user/character/session export | FEAT-006..FEAT-013, FEAT-017, FEAT-018 (user half), FEAT-020 |

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
no DOM.

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
section is **deleted**: there is no aside, no splitter, and nothing in the
workspace resizes (`workspace-shell.md`'s reversal record). The citation is
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
/characters/:id         the character page — two columns (UC-073, US-096); its
                          composer starts a session (UC-080, US-117)
/characters/new         the character draft page (UC-074, US-097)
/settings               the two languages and the user's own notes (US-092, UC-047)
/search                 my-search results (FEAT-017)
```

**Every one of these routes renders the same shell.** The shell is not a property
of a route — the tree is present on all of them, and what changes is the centre
column and whether the wall exists. Geometry, collapse and the wall's two modes
are `workspace-shell.md`'s and are not described here.

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
- **Setups have no route.** The character page holds the persona, notes, setups,
  resolved configuration and sessions in one place (US-096).
- **`/memos` is gone.** User-level notes live on the settings screen (US-092); the
  other three levels live on the wall (UC-072, UC-075).

**`/characters/:id` also starts sessions.** Writing in the character page's
composer (`workspace-shell.md`) posts **once**, to
`POST /api/characters/{id}/sessions` (`backend-structure.md`), which creates the
session and seeds its current zone in one transaction. **The new session's id
comes back in that response**, and the client navigates to `/sessions/:id` with
it. The id is a **`string`** and is used exactly as received — see "Ids are
strings" below; there is nothing to parse and nothing to assemble client-side,
and the `useParams()` value on arrival is that same string. The navigation is an
in-entry router navigation, not a document navigation: the character page and the
workspace are both the `app` entry. What the client must **not** do is create the
session and then post the message as two calls — that sequence can fail between
them and leave an empty session behind, which is why the backend exposes one
route.

`/characters/new` is this doc's **design inference**, not a requirement: UC-074 and
US-097 require a **draft page** that persists nothing until the roleplayer types
something, and a page needs an address. The path is architecture's to choose; the
behaviour is the product's.

My-search is reachable **from any screen** (UC-058) and from the tree expanded or
collapsed (US-118), so its trigger lives at the top of the tree — duplicated onto
the collapsed rail — rather than only on `/search` (`workspace-shell.md`).

Archived objects are reached by an explicit toggle, never by a separate route —
archive is a filter on the working list, not a different place (R6).
`_TBD: where that toggle sits is not settled. It used to hang on a character list
and a session list and both are gone; the tree (UC-069) and the character page
(UC-073) now show those objects, but docs/product/ places the toggle on neither.
FEAT-006 / FEAT-007 / FEAT-008's plans must place it — R6 already fixes the
behaviour, so this is a placement question, not a design one._

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

The one place in the doc set that contradicted this rule — `ui-conventions.md`'s
page-state example writing `disableUser(state, id: number, ...)` — has been
corrected to `id: string`. **That `_TBD:` is closed**; the rule here remains the
authoritative statement of it.

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
  codes the UI must branch on specifically are `model_not_enabled`,
  `no_embedding_model`, `translation_failed`, `zone_empty`, `zone_not_empty`,
  `nothing_to_reopen`, `message_not_editable`, `already_configured` and
  `invalid_credentials`. **`discussion_not_resumable` is gone** — it named a table
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
draft's field mapping (`ui-conventions.md`), not as a branch key. **An exported
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
2. **One field-mapping, per draft.** `ui-conventions.md`'s `submitX` free function
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
**`POST /api/sessions/{id}/zone/compose`** (`backend-structure.md`). The old
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
  (`llm-and-streaming.md`, `backend-structure.md`). The controller is owned by
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
  `ui-conventions.md`'s never-optimistic re-load rule applying to a mutation
  whose result the client did not observe, not a special case; the same rule
  already governs every other mutation in the product.
- **The stop clears nothing.** R10's prohibition covers this path too: aborting
  must not discard the in-flight assistant text already rendered, the roleplayer's
  own zone messages, or the settled record — the reload replaces the in-flight
  message with the persisted row, it does not empty the zone first.

Frame handling maps onto the **current zone** store (`workspace-shell.md`):

- **`token` appends to the in-flight assistant message in the zone.** There is no
  answer box to append to — the product removed it. The message the tokens build
  is an ordinary zone message the roleplayer may **edit in place before settling**
  (US-115), so the consumer writes into the same observable the editor binds to,
  not into a separate streaming buffer copied over at `done`. A separate buffer
  makes an edit during streaming either impossible or silently discarded.
- **`tool_start` / `tool_result` / `tool_fail` append or update a tool row**,
  rendered as the collapsible blocks US-114 describes. These are persisted
  `role='tool'` rows server-side (`data-model.md`), not transient UI state, so a
  reload does not lose them.
- **`error` renders a visible failure without discarding anything already in the
  zone or in the settled record above the ruler** (R10, UC-032) — the one rule
  here that is a product guarantee rather than a transport detail.
- **`done` finalises**, and its `message_id` is a **decimal string** (above).

The protocol itself is defined in `llm-and-streaming.md` — this module's contract
is only that it never drops roleplayer text on any frame.

## Markdown

- **Editing** (memo bodies, character sheets): TipTap via `@mantine/tiptap`, plus
  `tiptap-markdown` for markdown in and out. This is what satisfies UC-043's
  markdown editor with live preview.
- **Rendering** (notes shown read-only, settled entries and current-zone messages,
  search result snippets): `react-markdown`.

Two libraries rather than one because the editing surface needs a document model
and a toolbar while the read surfaces need neither, and loading an editor to
render a search snippet is a poor trade.

## Bundle-level constraints worth stating

- **`@dnd-kit` is used for exactly one interaction: reordering notes within a
  level on the note wall** (UC-076, US-102). The previous `_TBD:` here — "do not
  build reorder until a requirement asks for it" — is **closed**: US-102 is that
  requirement, and it is the project's first and only drag interaction
  (`workspace-shell.md`). Four constraints come with it:
  - **A note cannot cross a level boundary by dragging** (US-103.AC-2), enforced
    in the drop handler, not merely signalled in the drag preview.
  - The ordering column is **`memos.sort_key`**, scoped within `(scope, scope_id)`
    and nowhere wider (`data-model.md`) — the one mutable ordering in the schema.
    The `position` column this bullet used to cite **does not exist**:
    `data-model.md` dropped it, because `ORDER BY id` on a k-sortable snowflake is
    the stream order and nothing in `docs/product/` permits reordering entries.
  - **Reordering is not decoration: it changes what the system prompt contains**
    (R3, US-102, `llm-and-streaming.md`), which is why `@dnd-kit`'s keyboard sensor
    is required rather than optional (`ui-conventions.md`'s accessibility floor).
  - Nothing else may use `@dnd-kit` without a requirement that asks for it.
- No component library other than Mantine, no Tailwind, no CSS modules, no
  styled-components (`overview.md`).

### The two stylesheets — the whole division

**Decided; this doc owns the convention.** There are **exactly two** hand-written
stylesheets and there is no third:

| File | Holds | Imported by |
|---|---|---|
| `src/global.css` | **resets only** | every entry — imported by **`shared/AppProviders`**, after Mantine's core and notifications stylesheets, and so reaching every entry transitively |
| `src/shell.css` | **the `app` workspace's layout only** — the three-column grid and its `1px` gap, the `--navw` custom property and the collapsed-rail class that re-points it, the `820px` media query | the **`app` entry** alone — imported directly by **`src/app/main.tsx`**, the one stylesheet an entry imports itself |

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
