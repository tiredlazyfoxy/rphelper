# Feature 002 — Frontend foundation · feature-wide context

## What this feature is

Stands the four-entry Vite build up as four themed but **empty** documents, so every
later frontend feature has an entry to land in and a shared client to call through.
The agreed boundary is `brief.md` in this folder — its Definition and its Scope In/Out
lists bound every step here and are not restated. Read it first.

The conventions this feature freezes, which no later feature may re-decide: the
four-entry build and its emitted layout, the single `src/shared/` folder, the API
client's typed-error decode, the two stylesheets, the Mantine theme and its two colour
schemes, the shared `IconButton` and its icon sizing, the notifications channel, the
pure-data-contract rule for MobX, and the ids-are-strings rule with a real enforcement
mechanism.

## Product ids

**This feature delivers none.** `brief.md` records `Delivers: —` and the roadmap shows
`—`. No Definition-of-done item in any step cites a `FEAT-###`, `UC-###` or
`US-###.AC-#`, and none may be invented to fill the gap. The `[test]` criteria here are
structural and behavioural and stand in their own terms. This is the same situation as
`001.backend-foundation`.

## Greenfield — there is no existing code

`frontend/` does not exist. Only `docs/`, the root `CLAUDE.md` and feature `001`'s
planned `backend/` are in play. **Every file named in every step's Source files list is
a new file.** Nothing in this plan modifies anything, and no step may assume a module,
a dependency or a fixture that an earlier step in this same feature did not create.

## Commands

From the root `CLAUDE.md`, run from `frontend/`:

```
build      npm run build
test       npm test
typecheck  npm run typecheck
```

These three are the contract. Step `001` creates the `package.json` scripts that back
them. `npm test` must be **non-watching** — a watch-mode test command hangs the
verifier.

`npm run dev` is added as a convenience and is **not** one of the three. `deployment.md`
shows the dev server started by `start.ps1 -ui` running `npx vite --port 8193`
directly; `start.ps1` belongs to `fast/001`, not to this feature.

## Architecture this binds to

- `docs/architecture/frontend-structure.md` — the multi-entry build and its verbatim
  `src/` tree, the `vite.config.ts` shape, why four entries, navigation between
  entries, the `admin` entry's `basename`, the MobX convention, routing inside `app`,
  "Ids are strings", the API client, and the two-stylesheet division.
- `docs/architecture/ui-conventions.md` — icons and the sizing table, the shared
  `IconButton` and its props type, the accessibility floor, the CRUD conventions, the
  MobX draft convention, the notifications rule, and "mutations are never optimistic".
- `docs/architecture/deployment.md` — the ports, the single `/api` proxy prefix, and
  the per-entry nginx SPA fallbacks that the build's emitted layout must satisfy.

Cited, never copied. Where a step needs a declaration the architecture already gives
verbatim (the `IconButtonProps` type, the icon sizing table), the step context points at
the doc section and the skeleton agent reproduces it — this plan does not restate
signatures. The `rollupOptions.input` block is the one verbatim declaration this feature
deliberately does **not** reproduce as written: its keys are kept, its values are not
(D13).

## The layout every step writes into

```
frontend/
  package.json            # deps, devDeps, the four scripts
  package-lock.json       # generated, committed, never hand-edited
  tsconfig.json           # strict, covers src/ and tests/
  tsconfig.node.json      # covers vite.config.ts itself
  vite.config.ts          # 4 rollup inputs + root/outDir + /api proxy + react plugin + vitest block
  .gitignore
  src/                    # Vite's root (D13)
    global.css            # hand-written stylesheet 1 of 2: resets only
    shell.css             # hand-written stylesheet 2 of 2: declared empty here
    shared/
      theme.ts            # the Mantine theme — a minimal token set
      colorScheme.ts      # the localStorage colour-scheme manager + the default
      AppProviders.tsx    # MantineProvider + Notifications, used by all four entries
      ColorSchemeToggle.tsx
      IconButton.tsx      # the one icon-only-action component
      apiError.ts         # ApiError + the two synthetic client codes
      api.ts              # the fetch wrapper
      notifyFailure.ts    # the transient-failure-reason channel
    bootstrap/  index.html  main.tsx
    login/      index.html  main.tsx
    admin/      index.html  main.tsx
    app/        index.html  main.tsx
  tests/
    setup.ts              # test-harness source, owned by the coder (see D12)
    ...                   # every *.test.ts / *.test.tsx
  dist/                   # build output (D13), git-ignored
```

**Not created here, and a step that creates one is out of scope:** any page component,
any MobX store or `*Draft.ts`, the SSE consumer, an `AppShell`, an admin gate, the
workspace grid's rules inside `shell.css`, a markdown editor, an ESLint config, a
`postcss.config.*`, a root `frontend/index.html`, a `frontend/src/index.html`.

## Cross-cutting constraints every step holds

**Both colour schemes are real, and dark is the default.** Every later feature must be
correct in **both** dark and light. A component that only looks right in one is a
defect, not a polish item. Hardcoded colour literals in `style` props or in either
stylesheet are the usual cause; semantic colour comes from the theme and from Mantine
component props.

**Ids are strings, end to end.** `id: number` on a type, a prop, a store field or a
route param is a defect (`frontend-structure.md`). No `parseInt`, no numeric sort, no
arithmetic. The API client never reviver-parses and never coerces; `useParams()`
already hands back `string`. In this feature the rule is enforced by an automated scan
(D5), not by a review note.

**No component library but Mantine.** No Tailwind, no CSS modules, no
styled-components, no data-table library, no second icon family. Exactly two
hand-written stylesheets and there is never a third; a rule that is neither a reset nor
workspace layout means a theme token was the right answer.

**Same-origin only.** The frontend never receives a backend base URL. Every call is to
`/api/...` on the current origin, in dev and in prod alike. There is no base-URL
variable, no environment-dependent host, and no `import.meta.env` read anywhere in this
feature. Ports are hardcoded literals in `vite.config.ts`, never environment variables.

**No success notifications.** `@mantine/notifications` exists for transient **failure
reasons only**, `autoClose: 5000`. *A notification whose message is a success is a
defect* — that is the whole test. A failure that already has a place to render (a field
error, an inline `Alert`) does not also raise a notification.

**Every icon-only action goes through `IconButton`.** A bare `ActionIcon` wrapping a
Tabler icon is a defect.

**No linter.** `npm run typecheck` (`tsc --noEmit`) is the only static gate. See D4.

## Decisions — settled, with their reasoning

Recorded here because later features inherit them and because a decision with no
recorded reason gets re-litigated.

### D1 — One `src/shared/` folder, imported by all four entries. *Resolved by the architecture, not decided by the planner.*

`brief.md`'s first open question asks whether the four entries share `src/shared/` or
duplicate the client, given `overview.md` requires the roleplayer's bundle to carry no
administrative code. **It is not actually open.** `frontend-structure.md` names
`shared/` in its verbatim `src/` tree and states "One module in `shared/`, used by every
entry" of the API client.

There is no tension with UC-066 / "admin code never ships to the roleplayer", because
that requirement is satisfied by **the entry split itself** — each entry is a separate
document with its own bundle and its own route table — and `shared/` holds only generic
infrastructure: an HTTP client, error rendering, and a button. It contains no
admin-specific component and, critically, **no route table naming `/admin`**, which is
the concrete thing `frontend-structure.md` says the roleplayer's document must not
contain. Duplicating the client per entry would buy nothing and would guarantee four
divergent error decoders.

### D2 — Pure data contracts: data is data, code is free functions.

**This resolves a divergence in the current docs.** `frontend-structure.md`'s
`SessionWorkspaceState` example carries "observables, computeds, actions";
`ui-conventions.md`'s `UsersPageState` carries **no methods**, with behaviour in free
functions. The second is chosen, and extended:

1. A data class holds **observable fields only**: `makeAutoObservable(this, {}, {
   autoBind: true })` in the constructor, initial values, and nothing else.
2. **No methods. No computed getters either.** The derivations `ui-conventions.md`
   shows as getters on a draft — `clientErrors`, `errors`, `canSubmit` — become **pure
   free functions taking the data object**: `clientErrors(draft)`, `errors(draft)`,
   `canSubmit(draft)`. They stay reactive: an `observer` component reading observables
   through a plain function still tracks them.
3. All effectful work is a free function taking the data object plus an optional
   `AbortSignal`: `submitCreateUser(draft, onSaved, signal?)`,
   `loadUsers(state, signal?)`.
4. Every such function `runInAction`s its writes — an `await` ends the enclosing action
   — and **early-returns on an aborted signal before writing**, so a late response
   cannot write into a dead store.

Reason, in the user's terms: separate data from code; a functional-like style, despite
MobX, at least for the data contracts. The practical payoff is that validation is
testable by constructing a value and calling a function, with no render and no network,
and that anything which can fail, await or navigate is visibly a call.

**`002` ships no store and no draft class**, because `brief.md` puts all page content
out of scope and inventing one against no real page would freeze a shape against no
requirement. The convention is recorded here as the binding contract every later
feature follows, and step `006` asserts its own compliance by absence.

Unchanged and still binding from the docs: one store per page instantiated with
`useState(() => new XState())` (never `useMemo`); stores passed **explicitly as props**,
no React context; components that read observables wrapped in `observer`; modal
open/target flags are component-local `useState`, not store state; a fresh draft
instance per modal open.

### D3 — Mantine theme: a minimal token set, both schemes, dark by default.

The theme carries `primaryColor`, `fontFamily` and a default radius, and nothing else.
**No component `defaultProps`, no invented palette, no type scale.** Semantic colours
come from Mantine's own built-in palette — notably `red` for destructive confirms,
which `ui-conventions.md` names — and are not redefined. Geometry lives in `shell.css`
(`008`'s), never in the theme.

`primaryColor` is set **explicitly** to Mantine's built-in `"blue"` rather than left to
the implicit default, so that a later feature changing it is a visible edit to a named
token rather than a discovery.

**Both dark and light are implemented, dark is the default**
(`defaultColorScheme="dark"`), and a toggle exists. The choice is persisted with
Mantine's own `localStorageColorSchemeManager` under the key **`rphelper.color-scheme`**
— a distinct key, not a second mechanism, and deliberately **not** folded into the
`rphelper.workspace-layout` record: that record is `008`'s and is app-entry-only, while
colour scheme applies to all four entries.

### D4 — No ESLint. TypeScript only.

The project has no JS linter — not ESLint, not an ESLint plugin, not a replacement.
`npm run typecheck` is `tsc --noEmit` and is the type gate. This is general and
emphatic: a later feature adding a linter for any reason is changing the project's
posture, not tidying it.

Because there is no linter, `tsconfig.json` carries the compiler's own lint-shaped
flags — `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch` — on top
of `strict`. `exactOptionalPropertyTypes` and `noUncheckedIndexedAccess` are
**deliberately off**: both fight Mantine's prop types at every call site, and neither
catches a defect this project has. Recorded so they are neither turned on as a tidy-up
nor assumed to have been forgotten.

**TypeScript only** is the other half of this decision, and equally emphatic. Every
authored file under `frontend/` is `.ts` or `.tsx` — sources, tests, the Vitest setup
module and Node-side configuration alike. No `.js`, `.jsx`, `.mjs` or `.cjs` file is
written, and neither tsconfig enables `allowJs` or `checkJs`. With no linter, the
compiler is the only static gate, and a JavaScript file bypasses it. A tool whose
scaffolding emits a JavaScript config (`postcss.config.js`, `eslint.config.js`, …) is
given a `.ts` config or not adopted. Generated output — `node_modules/`, `dist/`,
`coverage/` — is exempt. The rule is enforced by a `[test]` in step `001`, the same
"grep becomes a Vitest test" pattern as D5.

### D5 — The ids rule is enforced by a test, not a lint rule.

`frontend-structure.md` says "the reviewable form of this rule is one grep over
`frontend/src`". That grep is automated as a **Vitest test** that reads every `.ts` and
`.tsx` file under `frontend/src` and fails on the forbidden patterns, naming the
offending file and line. Zero new dependencies, and the rule becomes a real `[test]`
Definition-of-done item rather than a review note. The exact pattern set is in
`006.context.md`.

### D6 — The typed-error decode happens once, in the client; field mapping is the draft's.

`brief.md`'s second open question. `frontend-structure.md` puts the decode in the
client: it "parses `{ error: { code, message, detail } }` into a typed `ApiError` and
**throws it**". What lives outside the client is a **different, second step**: the
draft-form convention's mapping of an `ApiError` onto `serverErrors` **field keys**,
which `ui-conventions.md` places in each `submitX` free function, "by status or code,
not by parsing prose", with anything unmappable landing on a general key.

So: **one decode, in the client. One field-mapping, per draft.** Both halves are
recorded because the failure mode is a later feature putting the decode in a store and
producing a second, divergent error shape.

### D7 — `ApiError`'s shape. *The docs define none.*

A class extending `Error`, carrying `code: string` (the branch key), the inherited
`message: string`, `detail` as an object of unknown values, and the HTTP `status:
number`. Call sites branch on `.code`, never on a status number and never on a message
string. `status` is carried for diagnostics and for the by-status half of D6's field
mapping, not as a branch key.

`detail` is an object because `backend-structure.md`'s wire shape makes it one; any id
inside it is a **decimal string** and stays one.

### D8 — 5xx and transport failure get synthetic client codes. *No doc rule exists.*

So that **every** call site branches on `.code` uniformly:

| Situation | `code` | `status` |
|---|---|---|
| Non-2xx with a well-formed `{error:{code,message,detail}}` body | the backend's own code | the real status |
| Non-2xx whose body is absent, not JSON, or not that shape (an nginx 502 page, an empty 500, an HTML error) | `client_malformed_error` | the real status |
| `fetch` itself rejects — network down, DNS, connection refused | `client_transport_failed` | `0` |

Both synthetic codes are prefixed `client_` so it is unmistakable that no backend
produces them, and neither collides with `backend-structure.md`'s code table.
`client_transport_failed` is deliberately **not** named `llm_unreachable`-adjacent:
that is a backend domain code about a different subject.

**An abort is not an error and is not wrapped.** If the caller's `AbortSignal` fires,
the original `AbortError` propagates unchanged, so that `signal.aborted` checks and
D2's early-return-on-abort rule work as written. A wrapped abort would be indisting-
uishable from a transport failure and would render an error for an action the user took
deliberately.

This feature defines **no** behaviour for the admin gate's "502 is not a deny" rule —
that belongs to `005`.

### D9 — Providers live in one shared component. *Placement is unspecified in the docs.*

`shared/AppProviders.tsx` wraps `MantineProvider` (the theme, the colour-scheme manager,
`defaultColorScheme="dark"`) and renders `<Notifications autoClose={5000} />` above its
children. All four entries' `main.tsx` use it. That is why the theme and the
notification configuration exist in exactly one place and cannot drift between entries.

`AppProviders` also owns the stylesheet imports — Mantine's own CSS, the notifications
CSS, then `src/global.css` **last**, so the resets land after Mantine's base sheet with
a deterministic cascade order decided in one file rather than by import-statement order
in four. `global.css` still reaches every entry, transitively, exactly as
`frontend-structure.md`'s table requires. `shell.css` is the exception and is imported
by `src/app/main.tsx` **alone**, because only the `app` entry has a workspace.

### D10 — Test stack: Vitest + Testing Library + jsdom. *The docs name no test tooling.*

Vitest reuses `vite.config.ts`, so there is no second build pipeline, no second
resolver and no second set of aliases to keep in step. Testing Library + jsdom so that
later features can test components and so the pipeline's test-coder can bind to
**rendered behaviour** rather than to implementation details. `npm test` runs Vitest
once and exits.

`globals` is **off** — `describe` / `it` / `expect` are imported explicitly. One fewer
ambient type surface, and an import that names its source is the same argument the rest
of this project makes about props versus context.

`002`'s own tests cover the API client's error decoding, the 401/403 rules,
`IconButton`'s accessible name, the theme's two schemes, the emitted build layout, and
the ids scan.

### D11 — Tests live in `frontend/tests/`, outside `src/`.

Not co-located. Two reasons, both structural: D5's scan is scoped to `frontend/src`, so
keeping tests out of `src` means no test fixture can ever trip it and no exclusion list
has to be maintained; and the Vite build's root is `src/` itself (D13), so keeping
non-shipping code out of `src/` means nothing test-only is reachable from a bundle.
The `tests/` tree mirrors `src/`.

### D12 — `frontend/tests/setup.ts` is a **Source** file, not a test file.

It is test-harness configuration referenced from `vite.config.ts`'s `test.setupFiles`,
in the same category as the config itself, and it is created in step `001` by the
coder. The test-coder's scope is `frontend/tests/**/*.test.ts` and `*.test.tsx` only.
This keeps the two roles' file lists disjoint at the path level and keeps step `001`'s
coder from depending on a file outside their own scope.

### D13 — Vite specifics. *`base`, `root`, `outDir` and the plugin list are unspecified in the docs.*

*Revised 2026-09-29 by user decision.* The original plan left `root` at its default
(`frontend/`) on the reasoning that the architecture's input paths are written relative
to it. That reasoning is what broke the build: Vite names each emitted HTML file by its
input's path **relative to `root`**, so the input `src/app/index.html` emitted
`dist/src/app/index.html`, while `deployment.md`'s per-entry `location /<entry>/` blocks
and step `006` DoD-13 need `dist/app/index.html`. The user chose to move the root rather
than rename output after the fact.

- `@vitejs/plugin-react` is added; no doc names a plugin and a React build needs one.
- **`root` is `frontend/src`.** Each entry's HTML is then `<entry>/index.html` relative
  to the root and is emitted at `dist/<entry>/index.html` — exactly
  `dist/{bootstrap,login,admin,app}/index.html`, with no `src/` segment.
- **`build.outDir` resolves to `frontend/dist`** — the same destination as before
  (`../dist` relative to the new root), which is what `deployment.md` copies into nginx.
- **`build.emptyOutDir` is `true`.** Vite only clears an output directory that lies
  inside `root` by default, and warns and leaves it alone otherwise; with `dist` now
  outside `src`, stale hashed bundles from earlier builds would accumulate without it.
- **`build.rollupOptions.input` keeps its four keys** — `bootstrap`, `login`, `admin`,
  `app` — and each value is an **absolute path**, resolved from the config file's own
  directory, to `frontend/src/<entry>/index.html`. Absolute so that where an input
  lands never depends on the working directory or on how a relative input is resolved
  once `root` is no longer the package directory. This is a deliberate deviation from
  `frontend-structure.md`'s verbatim `src/<entry>/index.html` values, recorded in
  `outcome.md` for the architect. `root` and `outDir` are written the same way.
- **Vitest keeps `frontend/` as its own root.** The `test` block sets its root to the
  `frontend` directory, because otherwise Vitest inherits `src` and would resolve the
  `tests/**` include and `./tests/setup.ts` under `src/`, finding nothing. The D11
  layout — tests in `frontend/tests/`, the include matching nothing under `src/` — is
  unchanged.
- `base` stays at its default `/`.
- A consequence to know: Vite's `publicDir` defaults to `<root>/public`, i.e.
  `frontend/src/public`. None exists in this feature; a later feature that adds static
  assets either puts them there or sets `publicDir` explicitly.
- `server.strictPort` is **true**: a busy 8193 must fail loudly rather than silently
  move to 8194, where the dev proxy assumption quietly stops holding.
- Exactly **one** proxy rule, `/api` → `http://localhost:8184`. `deployment.md` says
  "one prefix only"; a second rule is a defect.

### D14 — Dependencies: only what `002` needs.

**Installed:** `react`, `react-dom`, `@mantine/core`, `@mantine/hooks`,
`@mantine/notifications`, `@tabler/icons-react` `^3.40`, `react-router-dom` 7, `mobx`,
`mobx-react-lite`. Dev: `typescript`, `vite`, `@vitejs/plugin-react`, `vitest`, `jsdom`,
`@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`,
`@types/react`, `@types/react-dom`, `@types/node`.

**Deliberately not installed here**, each with its owner: TipTap, `tiptap-markdown` and
`@mantine/tiptap` (`015`'s markdown editor), `react-markdown` (`015`), `@dnd-kit`
(`008`'s note reordering — and `frontend-structure.md` names no sub-package or version,
so the feature that needs it chooses). An unused dependency in a foundation is a
version pinned against no call site and a bundle weighed down for nothing.

`mobx` and `mobx-react-lite` **are** installed despite `002` shipping no store, because
`brief.md` puts "the MobX per-page-store and draft-form conventions" **in scope** — the
convention is this feature's to fix, so the library it names belongs to the foundation.
That is the distinction from the five above, none of which `brief.md` mentions.

**`@mantine/form` is not installed.** The root `CLAUDE.md`'s stack table lists it, but
`ui-conventions.md` says it is deliberately not used ("the MobX draft convention") and
`quick-reference.md` calls it "present but unused". A dependency that the
project-wide form convention forbids using is not an inherited dependency here — this
is a greenfield tree with nothing to inherit. `outcome.md` carries the recommendation
that the architect drop it from the stack table.

**`postcss-preset-mantine` is not installed.** It is only needed to author CSS using
Mantine's mixins; Mantine 7's components ship pre-built CSS, `global.css` is resets and
`shell.css` is empty here. If `008` wants the mixins for the workspace grid it adds the
dependency then, with a call site.

## Seams with other features

**S1 — the `/` → app-document mapping is `fast/001`'s, not this feature's.**
`deployment.md`'s nginx block ends with `location / { try_files $uri $uri/ /index.html; }`,
and `frontend-structure.md` mounts the `app` entry's routes at `/`, `/sessions/:id`,
`/characters/:id` and so on with **no basename**. The Vite build emits the app document
at `dist/app/index.html` (D13), so something must make it answer at `dist/index.html`
too — a copy in the image build, or an nginx `root`/`alias` adjustment. **That mapping
belongs to `fast/001`'s nginx and image configuration.** This feature deliberately does
**not** create a fifth root HTML document (`frontend/index.html` or
`frontend/src/index.html`): that would be an entry the architecture's input list does
not have. The consequence in dev is that `http://localhost:8193/` does not resolve; the
dev server's root is `src/` (D13), so the entries are reached at `/<entry>/index.html`
— for example `http://localhost:8193/admin/index.html`. That is a known wart on the
same seam.

Step `006` makes the emitted layout a Definition-of-done item precisely because this
seam is invisible until deployment.

**S2 — the admin basename versus the admin URL.** nginx serves the admin entry under
`/admin/` (trailing slash); `frontend-structure.md` states `BrowserRouter
basename="/admin"` (no trailing slash). These are two different strings for two
different mechanisms and neither may be copied from the other.

**S3 — `shell.css` ships empty.** `008` fills it with the three-column grid, the `1px`
gap, the `--navw` custom property, the collapsed-rail class and the `820px` media
query. `002` creates the file and wires its import so that `008` has nothing structural
to decide.

**S4 — `ColorSchemeToggle` is exported and mounted nowhere.** `brief.md` puts page
content out of scope in every entry, so no entry mounts it. `005` (the admin shell) and
`008` (the workspace's user menu) place it. It is covered by a unit test, like
`IconButton`, which is also exported and mounted nowhere in this feature.

## Deviations from the orchestrator's suggested decomposition

One, forced by a dependency direction:

**`IconButton` moves ahead of the providers step.** The suggested order put
`AppProviders` plus the colour-scheme toggle at step 3 and `IconButton` at step 5. The
toggle is an icon-only action, and `ui-conventions.md` makes a bare `ActionIcon`
wrapping a Tabler icon a defect — so the toggle must go through `IconButton`, and
`IconButton` must exist first. The order is therefore scaffold → stylesheets and theme
→ `IconButton` → API client → providers, toggle and `notifyFailure` → entries. The
ordering constraint the orchestrator named still holds: the scaffold comes first, and
the entries come last because they integrate everything.

## Step map

| Step | Subject | Depends on |
|------|---------|------------|
| 001 | `package.json`, both tsconfigs, `vite.config.ts` (four inputs, `root`/`outDir`, `/api` proxy, react plugin, vitest block), the test setup file, `.gitignore` | — |
| 002 | `global.css` resets, `shell.css` declared empty, `shared/theme.ts` | 001 |
| 003 | `shared/IconButton.tsx` and the icon sizing convention | 001 |
| 004 | `shared/apiError.ts` + `shared/api.ts` — the client, the decode, 401/403/5xx/transport | 001 |
| 005 | `shared/colorScheme.ts`, `shared/AppProviders.tsx`, `shared/ColorSchemeToggle.tsx`, `shared/notifyFailure.ts` | 001, 002, 003, 004 |
| 006 | the four `index.html` + `main.tsx` pairs, and the ids-are-strings guard | 001–005 |

## Test conventions later features inherit

- Tests live under `frontend/tests/`, mirroring `src/` (D11). `frontend/tests/setup.ts`
  is harness source, not a test (D12).
- The setup file registers `@testing-library/jest-dom`'s matchers against Vitest's
  `expect` and runs Testing Library's `cleanup` after each test.
- A component test that reads the theme or renders a Mantine component must render it
  inside a provider. `shared/AppProviders` is available from step `005`; before that a
  bare `MantineProvider` from `@mantine/core` is the wrapper.
- Tests assert **rendered behaviour** — an accessible name, a visible element, a thrown
  value — not internal structure. The test-coder never reads source.
- `fetch` is stubbed per test rather than by a network-mocking library; no such library
  is a dependency and none is added.
