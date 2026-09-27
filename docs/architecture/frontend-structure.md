# Frontend structure

**Realizes:** FEAT-001, FEAT-002, FEAT-003, FEAT-004, FEAT-005, FEAT-006,
FEAT-007, FEAT-008, FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013, FEAT-017,
FEAT-019, ACT-001, ACT-002, ACT-003

React 19 + TypeScript, built by Vite as **four separate entries**. Component
library, state library and icon set are fixed in `overview.md`; the visual shell
and the resize behaviours are in `ui-conventions.md`.

## The multi-entry build

```
frontend/
  vite.config.ts
  src/
    global.css              # the only hand-written stylesheet (resets)
    shared/                 # api client, sse consumer, error rendering, IconButton
    bootstrap/  index.html  main.tsx  ...   # FEAT-001
    login/      index.html  main.tsx  ...   # FEAT-002
    admin/      index.html  main.tsx  ...   # FEAT-003, FEAT-004, FEAT-005
    app/        index.html  main.tsx  ...   # FEAT-006 .. FEAT-017
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

### Per-entry responsibilities

| Entry | Screens | Realizes |
|---|---|---|
| `bootstrap` | Create-new-database (with first admin), import-an-export, and the already-configured refusal | FEAT-001, UC-001, UC-002, UC-003 |
| `login` | Sign in, sign out landing, disabled-account message | FEAT-002, UC-004, UC-005 |
| `admin` | Account list + lifecycle; LLM servers, connection test, enabled models, embedding designation; drift report + remediation + vector rebuild; whole-database export/import | FEAT-003, FEAT-004, FEAT-005, FEAT-018 (admin half), UC-006..UC-016, UC-061 |
| `app` | Character list, setups, session list, session workspace (entry list + compose discussion + answer box), memo editors, session configuration, my-search, user/character/session export | FEAT-006..FEAT-013, FEAT-017, FEAT-018 (user half) |

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
- **`BrowserRouter basename="/admin"`** and the **same Mantine `AppShell`** as the
  app area, with `header` and `navbar` only — no `aside`, and no shell-level
  `padding` (each page brings its own `Container`).
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
  constructor(readonly sessionId: number) {
    makeAutoObservable(this, {}, { autoBind: true });
  }
  // observables, computeds, actions
}

export const SessionWorkspacePage = observer(function SessionWorkspacePage(
  { sessionId }: { sessionId: number },
) {
  const [state] = useState(() => new SessionWorkspaceState(sessionId));
  return <SessionEntryList state={state} />;   // passed explicitly as a prop
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

The choice of MobX over a reducer store is justified concretely by
`ui-conventions.md` (A): the aside width is pushed to a CSS custom property by a
single `autorun`, so a pointer-move causes **zero** component re-renders. That is a
natural MobX expression and an awkward one in a dispatch-based store.

## Routing inside the `app` entry

```
/                       session list, ordered by last use (UC-026)
/characters             character list (working + archive toggle)
/characters/:id         character detail, config overrides, memos
/characters/:id/setups  setups under the character
/sessions/:id           the session workspace — the product's main screen
/memos                  user-level memos
/settings               user-level defaults (UC-047)
/search                 my-search results (FEAT-017)
```

`/sessions/:id` is the three-pane workspace: navbar, the session entry list in
`Main`, and compose-discussion + answer box in `Aside` (`ui-conventions.md`).
My-search is reachable **from any screen** (UC-058), so its trigger lives in the
shell header rather than only on `/search`.

Archived objects are reached by an explicit toggle on each list, never by a
separate route — archive is a filter on the working list, not a different place
(R6).

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
  `no_embedding_model`, `translation_failed`, `discussion_not_resumable`,
  `already_configured` and `account_disabled`.
- A `401` triggers a document navigation to `/login`. A `403` does not — it is a
  genuine authorization failure and is rendered, not redirected.

`model_not_enabled` gets a dedicated presentation, because it is product
behaviour and not an incident: UC-012 requires the roleplayer be able to fix it by
choosing another model through FEAT-013's chain, and the error's `detail` names
which level set the dead reference — so the UI links straight to that level's
configuration screen. **It never offers "use a different model just this once"**,
because that is the silent fallback R4 forbids.

## The SSE consumer

**Realizes:** FEAT-010, UC-032, UC-034

One module in `shared/`. The request is a **POST with a JSON body**, so native
`EventSource` (GET-only) cannot be used — discussion text would have to go into a
URL. Instead:

```ts
const res = await fetch("/api/discussions/{id}/messages", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
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
- **The consumer is cancellable** via an `AbortController`, which is what the stop
  control (`IconPlayerStop`) uses.
- **A stream that ends without a `done` frame is a failure**, surfaced as
  `llm_unreachable`. Silence is not success.

Frame handling maps onto the transcript store: `token` appends to the in-flight
assistant message, `tool_start` / `tool_result` / `tool_fail` append or update a
tool row, `error` renders a visible failure **without discarding anything already
in the transcript or the answer box** (R10, UC-032), and `done` finalises. The
protocol itself is defined in `llm-and-streaming.md` — this module's contract is
only that it never drops roleplayer text on any frame.

## Markdown

- **Editing** (memo bodies, character sheets): TipTap via `@mantine/tiptap`, plus
  `tiptap-markdown` for markdown in and out. This is what satisfies UC-043's
  markdown editor with live preview.
- **Rendering** (memos shown read-only, settled answers, search result snippets):
  `react-markdown`.

Two libraries rather than one because the editing surface needs a document model
and a toolbar while the read surfaces need neither, and loading an editor to
render a search snippet is a poor trade.

## Bundle-level constraints worth stating

- `@dnd-kit` is available for reorder interactions. Nothing in FEAT-001..019
  currently requires drag reordering — `_TBD: entries carry a position column
  (data-model.md) but docs/product/ does not state that the roleplayer may reorder
  them; UC-031 only says entries are added in any order. Do not build reorder
  until a requirement asks for it._`
- No component library other than Mantine, no Tailwind, no CSS modules, no
  styled-components (`overview.md`). `global.css` holds resets only; anything else
  in it is a sign a Mantine theme token was the right answer.
