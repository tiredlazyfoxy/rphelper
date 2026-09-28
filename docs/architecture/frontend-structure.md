# Frontend structure

**Realizes:** FEAT-001, FEAT-002, FEAT-003, FEAT-004, FEAT-005, FEAT-006,
FEAT-007, FEAT-008, FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013, FEAT-017,
FEAT-019, FEAT-020, ACT-001, ACT-002, ACT-003

React 19 + TypeScript, built by Vite as **four separate entries**. Component
library, state library and icon set are fixed in `overview.md`.

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
  vite.config.ts
  src/
    global.css              # hand-written stylesheet 1 of 2: resets only
    shell.css               # hand-written stylesheet 2 of 2: workspace layout
                            #   only; imported by the app entry alone
    shared/                 # api client, sse consumer, error rendering, IconButton
    bootstrap/  index.html  main.tsx  ...   # FEAT-001
    login/      index.html  main.tsx  ...   # FEAT-002
    admin/      index.html  main.tsx  ...   # FEAT-003, FEAT-004, FEAT-005
    app/        index.html  main.tsx  ...   # FEAT-006 .. FEAT-017, FEAT-020
```

```ts
// vite.config.ts (shape)
build: {
  rollupOptions: {
    input: {
      bootstrap: "src/bootstrap/index.html",
      login:     "src/login/index.html",
      admin:     "src/admin/index.html",
      app:       "src/app/index.html",
    },
  },
},
server: { port: 8193, proxy: { "/api": "http://localhost:8184" } },
```

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
| `login` | Sign in, sign out landing, disabled-account message | FEAT-002, UC-004, UC-005 |
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
- **Flat `<Routes>`** — three pages plus a catch-all 404, no nested layout route
  and no `<Outlet/>`. The shell renders above the `<Routes>`. With three sibling
  pages and no per-page layout variation, a layout route adds a level of
  indirection and buys nothing.
- **The back-to-app link is a real `<a href="/">`**, not a router `Link` — the app
  area is a different document (see "Navigation between entries" above), and an
  anchor is also what makes middle-click and ctrl-click behave correctly.

#### Boot sequence — one `/api/me` round-trip before mount

```
main.tsx
  └─ await GET /api/me
       ├─ 401 / no session            ──► document navigation to /login
       ├─ session, role !== "admin"   ──► document navigation to /        (app area)
       └─ session, role === "admin"   ──► createRoot(...).render(<AdminApp/>)
```

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

## State — MobX 6, per-page stores, no context

The convention, inherited and kept:

```tsx
// SessionWorkspacePage.tsx
class SessionWorkspaceState {
  constructor(readonly sessionId: string) {     // string — see "Ids are strings" below
    makeAutoObservable(this, {}, { autoBind: true });
  }
  // observables, computeds, actions
}

export const SessionWorkspacePage = observer(function SessionWorkspacePage(
  { sessionId }: { sessionId: string },
) {
  const [state] = useState(() => new SessionWorkspaceState(sessionId));
  return <SessionStream state={state} />;      // passed explicitly as a prop
});
```

Three rules:

1. **One `makeAutoObservable` class per page**, instantiated in the page component
   via `useState(() => new XState())`. `useState` with an initializer, not
   `useMemo` — `useMemo` is a cache with no guarantee of identity, and a store
   whose identity can change silently is a source of lost in-flight state.
2. **Stores are passed explicitly as props. There is no React context.** The
   reason is legibility of lifetime and of dependency: reading a component's props
   tells you exactly which store it touches, and a store's lifetime is visibly the
   page's. Context would make both invisible and would make it easy for a child
   to reach a store the page did not intend to give it.
3. **Components that read observables are wrapped in `observer`.** A component that
   is not an `observer` must not read an observable — the resulting missed render
   is the hardest bug in this stack to find.

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
- **`id: number` on a type, a prop, a store field or a route param is a defect** —
  the reviewable form of this rule is one grep over `frontend/src`.
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
  `account_disabled`. **`discussion_not_resumable` is gone** — it named a table
  that no longer exists and a condition that has changed; `zone_not_empty` is its
  replacement and the rename is not cosmetic (`backend-structure.md`).
  **Where a failure is not already rendered in place, its reason is shown as a
  transient notification** (US-044.AC-4, `ui-conventions.md`) — the client throws
  and renders exactly as before; what changed is only the surface some of these
  codes land on.
- A `401` triggers a document navigation to `/login`. A `403` does not — it is a
  genuine authorization failure and is rendered, not redirected.

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
| `src/global.css` | **resets only** | every entry |
| `src/shell.css` | **the `app` workspace's layout only** — the three-column grid and its `1px` gap, the `--navw` custom property and the collapsed-rail class that re-points it, the `820px` media query | the **`app` entry** alone |

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
