# Feature 002 — frontend-foundation · intended documentation changes

Written by the planner before implementation; applied by `/architect` at finalization.
Entries are grouped by target file. Nothing here is a product-layer change — this
feature delivers no product ids and cites none.

Four kinds of entry appear below and are marked so they are not confused:

- **gap closure** — the docs left something unspecified and a plan had to choose;
- **planner inference** — a decision the docs do not state and could not be read off
  them, recorded so it is not re-inferred differently;
- **divergence resolution** — two docs disagreed and the user chose;
- **deviation** — the doc states something verbatim, and the build could not follow it
  as written; the user chose the replacement.

The first entry is the largest and is a real change to the design, not a note.

---

## `docs/architecture/frontend-structure.md`

### § State — MobX 6, per-page stores, no context (**divergence resolution — the largest change here**)

**Change.** Replace the `SessionWorkspaceState` example's `// observables, computeds,
actions` comment and rewrite the three rules into four, establishing **pure data
contracts**:

1. A data class holds **observable fields only** — `makeAutoObservable(this, {}, {
   autoBind: true })` in the constructor, initial values, and nothing else.
2. **No methods, and no computed getters either.** Derivations are **pure free
   functions taking the data object**. They remain reactive: an `observer` component
   reading observables through a plain function still tracks them.
3. All effectful work is a free function taking the data object plus an optional
   `AbortSignal`. Each `runInAction`s its writes, because an `await` ends the enclosing
   action, and each early-returns on an aborted signal before writing.
4. Unchanged: one store per page via `useState(() => new XState())` (never `useMemo`);
   stores passed explicitly as props with no React context; components reading
   observables wrapped in `observer`.

State the rationale in the doc's own voice: separate data from code — a functional-like
style, despite MobX, at least for the data contracts. The payoff is that validation is
testable by constructing a value and calling a function, with no render and no network,
and that anything which can fail, await or navigate is visibly a call rather than a
method reached through an object.

**Reason.** The two docs contradicted each other. `frontend-structure.md`'s example
carried "observables, computeds, actions"; `ui-conventions.md`'s carried **no methods**
with behaviour in free functions. A convention stated two ways is a convention nobody
can be held to, and the second is the one the user chose. The paired change to
`ui-conventions.md` is below; **the two must land together** or the divergence simply
moves.

### § The API client — the `ApiError` shape (**gap closure**)

**Change.** State it concretely: a class extending `Error` carrying `code: string` (the
branch key), the inherited `message`, a `detail` object of unknown values defaulting to
empty, and the HTTP `status: number`. Call sites branch on `.code`, never on a status
number and never on a message string; `status` is carried for diagnostics and for the
by-status half of the draft's field mapping, not as a branch key. An exported type
guard is the one sanctioned way a `catch` block narrows.

**Reason.** The doc says the client "parses … into a typed `ApiError` and throws it" and
never defines the type. Four features would otherwise define four.

### § The API client — 5xx, transport failure and abort (**gap closure**)

**Change.** Add the uniformity rule and its table, so that **every** call site branches
on `.code`:

| Situation | `code` | `status` |
|---|---|---|
| non-2xx with a well-formed envelope | the backend's own code | the real status |
| non-2xx whose body is absent, not JSON, or not the envelope | `client_malformed_error` | the real status |
| `fetch` itself rejects | `client_transport_failed` | `0` |

Both synthetic codes are prefixed `client_` so no reader mistakes one for a backend
code, and neither collides with `backend-structure.md`'s table.

Add the abort rule explicitly: **an abort is not an error and is not wrapped** — the
original abort rejection propagates unchanged, so `signal.aborted` checks and the
early-return-on-abort rule work as written. Cross-reference the SSE consumer's identical
reasoning, where a stop is deliberately not a failure.

**Reason.** The doc gives a 401 rule and a 403 rule and nothing for the other two ways a
call fails. Without this, a 502 from nginx and a dropped connection each reach call
sites as a different shape, and the branch-on-code contract quietly stops holding at
exactly the moments it matters. The admin gate's "502 is not a deny" rule stays `005`'s
and is untouched.

### § The API client — where the decode happens, and where it does not (**gap closure; `brief.md`'s second open question**)

**Change.** Record the two-step boundary in one sentence each: **one decode, in the
client** — it parses the envelope and throws a typed `ApiError`; **one field-mapping,
per draft** — `ui-conventions.md`'s `submitX` free function maps that `ApiError` onto
`serverErrors` field keys by status or code, never by parsing prose, with anything
unmappable landing on the general key.

**Reason.** `brief.md` asked whether the decoder lives in the client or in each store.
The doc already answers the first half and is silent on the second, which is where the
mistake actually gets made: a store that re-decodes produces a second, divergent error
shape.

### § The multi-entry build — the `vite.config.ts` shape: `root`, `outDir` and the input values (**deviation — user decision 2026-09-29**)

**Change.** Amend the `(shape)` block so that it matches what was built:

- `root` is the `frontend/src` directory;
- `build.outDir` is the `frontend/dist` directory (`../dist` relative to the root), and
  `build.emptyOutDir` is `true`, because the output directory lies outside the root and
  Vite otherwise neither empties it nor fails;
- `build.rollupOptions.input` keeps its four keys (`bootstrap`, `login`, `admin`,
  `app`), but each value is an **absolute path resolved from the config file's
  directory** to `src/<entry>/index.html`, rather than the literal relative string
  `src/<entry>/index.html` the block currently shows;
- the Vitest `test` block sets its own root to the `frontend/` directory, so the tests
  under `frontend/tests/` and the setup file are still found.

Replace, rather than add to, any wording that says the input paths are relative to the
package root.

**Reason.** With the block as written — default `root` (the package directory) and
inputs `src/<entry>/index.html` — Vite names each emitted document by its input's path
relative to `root`, and the build emitted `dist/src/<entry>/index.html`. That does not
match the emitted-layout contract below, nor `deployment.md`'s per-entry
`location /<entry>/` blocks. The user chose to root the build at `src/` rather than
rename or move output after the fact. Absolute input values keep entry resolution
independent of the working directory once the root is no longer the package directory.

### § The multi-entry build — Vite specifics (**gap closure**)

**Change.** Add to the `(shape)` block's surrounding prose: `@vitejs/plugin-react` is
the plugin; `base` stays at its default; `root`, `outDir` and `emptyOutDir` are as in
the deviation entry above; `server.strictPort` is enabled so a busy 8193 fails loudly
rather than moving to 8194 where the proxy assumption silently stops holding; and there
is **exactly one** proxy rule, matching `deployment.md`'s "one prefix only". Note the
knock-on of the root: Vite's `publicDir` defaults to `src/public`, which does not exist
yet — a feature that adds static assets puts them there or sets `publicDir`
explicitly.

**Reason.** The doc marks its config block `(shape)` and is therefore partial by
design; these are things a build cannot omit.

### § The multi-entry build — the emitted layout nginx depends on (**gap closure**)

**Change.** State the output contract: the build emits `dist/bootstrap/index.html`,
`dist/login/index.html`, `dist/admin/index.html` and `dist/app/index.html`, which is
precisely what `deployment.md`'s four per-entry `try_files` fallbacks resolve against.
State that this layout is a consequence of the build's `root` being `src/` (see the
deviation entry above), so a later change to `root` or to the input values must
re-check it.

**Reason.** It is the seam between the frontend build and the nginx configuration, and
getting it wrong is invisible until deployment — as this feature's own first build
showed. See the `deployment.md` entry below for the half that is not this doc's.

### § Navigation between entries / the `admin` entry — basename versus URL (**gap closure**)

**Change.** Add one explicit sentence beside the existing `basename="/admin"`: nginx
serves the document under `/admin/` **with** a trailing slash while the router's
basename has **none**, and the two strings belong to two mechanisms — React Router
strips the basename before matching, so a trailing slash there breaks the match. Also
record that `bootstrap`, `login` and `app` declare no basename, `app`'s routes being
mounted at the origin root.

**Reason.** The two strings differ by one character and sit in two files, which is the
shape of a bug someone "fixes" by making them agree.

### § The multi-entry build — `src/shared/` is one folder for all four entries (**gap closure; `brief.md`'s first open question**)

**Change.** Add a short paragraph stating it explicitly and saying why it does not
violate UC-066: the requirement is satisfied by **the entry split itself** — separate
documents, separate bundles, separate route tables — and `shared/` holds only generic
infrastructure (the HTTP client, error rendering, `IconButton`), never an
admin-specific component and never a route table naming `/admin`, which is the concrete
thing the doc says the roleplayer's document must not contain.

**Reason.** `brief.md` raised it as open. It is not open — the doc's own verbatim tree
and its "one module in `shared/`, used by every entry" already answer it — but the
apparent tension is legible enough that the next planner will raise it again unless the
answer is written down where the tension is.

### § The two stylesheets — who performs the imports (**planner inference**)

**Change.** Amend the table's "Imported by" column with the mechanism: `global.css` is
imported by **`shared/AppProviders`**, after Mantine's core and notifications
stylesheets, and therefore reaches every entry transitively; `shell.css` is imported by
**`src/app/main.tsx`** alone and is the one stylesheet an entry imports directly.

**Reason.** Resets must land after Mantine's base sheet to win the cascade. Leaving that
to import-statement order in four separate entry modules makes the cascade depend on a
line someone can reorder while tidying. One file owns it; the table's claim that
`global.css` reaches every entry is unchanged.

### § Ids are strings — how the rule is enforced (**gap closure**)

**Change.** Replace "the reviewable form of this rule is one grep over `frontend/src`"
with the mechanised form: that grep **is a test**, under `frontend/tests`, which scans
every `.ts` and `.tsx` file under `frontend/src` and fails naming the offending file and
line. Record the three patterns it catches — an `id`/`Id`-suffixed binding annotated
`number` or `number[]`, `parseInt`, and `Number.parseInt` — and record that there is no
exception list and no suppression comment: a genuine need changes the architecture
first. Record also what it deliberately does **not** catch — numeric sort and arithmetic
on ids, which are not textually detectable without type information and stay a review
matter.

**Reason.** The doc calls this "the single most forgettable rule in the doc set" and
then enforces it with a habit. The project has no linter (see `overview.md` below), so a
test is the only automated form available — and it costs no dependency.

---

## `docs/architecture/ui-conventions.md`

### § `@mantine/form` is NOT used — the MobX draft convention (**divergence resolution — pairs with the `frontend-structure.md` entry above**)

**Change.** Rewrite the `CreateUserDraft` example and rule 1. The draft class holds
**observable fields only** — no methods **and no computed getters**. `clientErrors`,
`errors` and `canSubmit` become **pure free functions taking the draft**:
`clientErrors(draft)`, `errors(draft)`, `canSubmit(draft)`. Rule 1's stated payoff is
unchanged and in fact strengthened: validation is testable by constructing a draft and
calling a function, with no render and no network. Rules 2, 3 and 4 stand as written.

Apply the same edit to § "Page state — the same MobX convention as the app area": the
`UsersPageState` example is already methodless and needs only the getter rule made
explicit and a cross-reference to `frontend-structure.md`'s now-matching statement.

**Reason.** The same divergence, from the other side. This doc's example was the one the
user chose; what changes here is only the getters. **Land this with the
`frontend-structure.md` MobX entry or the contradiction moves rather than closes.**

### § `@mantine/form` is NOT used — drop the dependency entirely (**recommendation**)

**Change.** Change "`@mantine/form` is a listed dependency and is deliberately not used"
to "`@mantine/form` is **not a dependency**", and make the same edit in § "Other
inherited frontend facts" where it reads "present as an inherited dependency but
deliberately not used". Recommend the matching edit to the root `CLAUDE.md` stack table
(below).

**Reason.** "Inherited" described the sibling project's tree. RPHelper's frontend is
greenfield and has nothing to inherit, so the package was simply not installed. A
dependency the project-wide form convention forbids using is a version to maintain, a
line in the lockfile, and a standing invitation for someone to reach for it.

### § Icons — the sizing convention's missing stroke (**gap closure**)

**Change.** Add the stroke to the two rows that lack it: **all three variants use
stroke 1.5.** State the reason inline — the section opens with "One family, for one
visual weight", and a stroke that changed between variants would be a second weight in
the same family. The table omitted it on the smaller rows because it does not change.

**Reason.** Only the `"main"` row carried a stroke, which reads as either an omission or
a deliberate difference, and a reader cannot tell which.

### § Every icon-only action goes through a shared `IconButton` — the unspecified bits (**gap closure**)

**Change.** Record three things the props type does not carry: the `ActionIcon` variant
is **`"subtle"`** (an icon-only action is secondary chrome; Mantine's default filled
variant would render roughly thirty solid coloured boxes across the product);
`sizeVariant` **defaults to `"main"`**, the table's first and most common row; and the
props type is deliberately **not** widened with `children`, a `variant` escape hatch, a
raw `size`, or an `aria-label` override — each would reintroduce the divergence the
`label`-feeds-both rule exists to prevent.

**Reason.** The variant is not optional in practice — the component cannot be written
without choosing one — and a choice made silently at implementation time is a choice
nobody can find later.

### § Async feedback — provider placement and the single call site (**gap closure**)

**Change.** Record where the notifications channel lives: the outlet is mounted by
**`shared/AppProviders`**, configured with `autoClose: 5000` **on the outlet** so no
call site can pick a different value, and it reaches all four entries through that one
component. Record that **`shared/notifyFailure`** is the only sanctioned way anything
raises a notification, and that its shape is what makes the rule structural: it takes a
thrown value and has **no success path and no colour parameter**, so a success
notification is not something a call site can express.

**Reason.** The doc states the rule — "a notification whose message is a success is a
defect. That is the whole test" — and specifies no mechanism. A rule enforced only by
review is one an unfamiliar contributor breaks first. Placement was unspecified
entirely.

---

## `docs/architecture/overview.md`

### Stack decision list — the frontend toolchain (**gap closure**)

**Change.** Add three rows with their reasons:

- **Vitest + Testing Library + jsdom** as the test stack. Vitest reuses `vite.config.ts`
  so there is no second build pipeline, no second resolver and no second alias set to
  keep in step; Testing Library + jsdom so tests bind to **rendered behaviour** rather
  than to implementation details, which is what the pipeline's test-coder — who never
  reads source — must bind to. `npm test` runs once and exits.
- **No ESLint, and no JS linter at all — the project is TypeScript-only.**
  `npm run typecheck` (`tsc --noEmit`) is the static gate. Because there is no linter,
  `tsconfig.json` carries the compiler's lint-shaped flags: `noUnusedLocals`,
  `noUnusedParameters`, `noFallthroughCasesInSwitch`. Record that
  `exactOptionalPropertyTypes` and `noUncheckedIndexedAccess` are **deliberately off** —
  both fight Mantine's prop types at every call site and neither catches a defect this
  project has — so they are not turned on as a tidy-up nor assumed forgotten.
- **The TypeScript configuration layout**: a root `frontend/tsconfig.json` with `strict`
  covering `src/` and `tests/`, plus `frontend/tsconfig.node.json` covering
  `vite.config.ts` itself, because the config runs in Node while everything under `src/`
  runs in a browser and one `lib` cannot honestly describe both. **No `paths` aliases** —
  four entries and one `shared/` folder do not need them, and nothing asks for one.

**Reason.** The doc set names **no** test tooling anywhere — a grep across all of
`docs/architecture/` and `docs/product/` for vitest, jest, testing-library, playwright,
cypress, storybook, jsdom and happy-dom returns zero hits — and names no linter posture
either. Both are stack decisions, and the stack decision list is where a reader looks
for one.

### Stack decision list — the colour scheme (**gap closure**)

**Change.** Record that **both** colour schemes are implemented with **dark as the
default**, that the choice is persisted by Mantine's own
`localStorageColorSchemeManager` under the key `rphelper.color-scheme`, and that this is
deliberately **not** folded into `rphelper.workspace-layout` — that record is the `app`
entry's alone while the colour scheme applies to all four entries. Add the standing
constraint: **every feature must be correct in both schemes**, and a component that only
looks right in one is a defect rather than a polish item.

**Reason.** No doc stated a colour-scheme posture at all, and "dark only" versus "both"
is a constraint every later feature inherits whether or not it is written down.

### Deferrals — dependencies not installed at the foundation (**gap closure**)

**Change.** Record which frontend dependencies the foundation deliberately does **not**
install, each with its owning feature: TipTap, `tiptap-markdown` and `@mantine/tiptap`
(the markdown editor, `015`); `react-markdown` (`015`); `@dnd-kit` (note reordering,
`008` — and the doc names no sub-package or version, so the feature that needs it
chooses). Also record that `postcss-preset-mantine` is not installed: it is needed only
to author CSS with Mantine's mixins, and with `global.css` holding resets and
`shell.css` empty there is no call site; `008` adds it if the workspace grid wants the
mixins. Record that `mobx` and `mobx-react-lite` **are** installed despite the
foundation shipping no store, because the MobX conventions are the foundation's to fix.

**Reason.** An unused dependency in a foundation is a version pinned against no call
site and a bundle weighed down for nothing — and the next planner will otherwise have to
re-derive why five packages the docs name are absent.

---

## `docs/architecture/quick-reference.md`

### Frontend toolchain, packaging and test conventions

**Change.** Add a compact block: one `frontend/package.json` carrying dependencies and
the four scripts (`build`, `test`, `typecheck`, `dev`); `package-lock.json` committed;
two tsconfigs; one `vite.config.ts` that also carries the Vitest block, so there is no
`vitest.config.*`; the build is rooted at `frontend/src` and emits to `frontend/dist`,
while the Vitest block keeps `frontend/` as its root; **tests live under
`frontend/tests/`, outside `src/`**, mirroring it; `frontend/tests/setup.ts` is harness
source rather than a test. Note the two reasons tests are not co-located: the ids scan
is scoped to `frontend/src` so no fixture can trip it and no exclusion list is needed,
and the build's root is `src/` so nothing test-only is reachable from a bundle.

**Reason.** Every later frontend feature adds a test and must know where it goes. The
three commands themselves stay in the root `CLAUDE.md` and are not duplicated here.

### Storage keys

**Change.** Record `rphelper.color-scheme` alongside `rphelper.workspace-layout`, with
their scopes: all four entries, and the `app` entry only.

**Reason.** Two keys in two features with no shared list is how a third feature
consolidates them and makes the login page's scheme depend on a workspace record.

### The `ApiError` branch key

**Change.** Add one line to whatever error-code material this index carries: call sites
branch on `ApiError.code`, and `client_malformed_error` / `client_transport_failed` are
client-side codes no backend produces.

**Reason.** The index is where an agent looks up an error code, and two of them now do
not appear in `backend-structure.md`'s table.

---

## `docs/architecture/deployment.md`

### nginx — the `/` fallback and the app document (**gap closure; a real open seam**)

**Change.** Close, explicitly, the gap between the emitted layout and the last fallback
rule. The build emits the app document at `dist/app/index.html`, while
`location / { try_files $uri $uri/ /index.html; }` resolves against `dist/index.html`,
and `frontend-structure.md` mounts the `app` entry's routes at the origin root with no
basename. State which mechanism bridges them — a copy in the image build, an nginx
`root`/`alias`, or a fifth build input — and name the feature that owns it
(`fast/001`'s nginx and image configuration). Record the dev-side consequence of leaving
it unbridged: the dev server's root is `src/`, so `http://localhost:8193/` does not
resolve and the entries are reached at `/<entry>/index.html`.

**Reason.** This is the one place the plan found the docs genuinely incomplete rather
than merely silent: as written, the four `try_files` rules and the four emitted files do
not line up for the root case, and nothing in the doc set says who fixes it. Feature
`002` deliberately did not create a root HTML document, because that would be a fifth
entry the architecture's input list does not have.

### Dev server — `strictPort`

**Change.** One line beside the existing dev topology: the Vite dev server runs with
`strictPort`, so a busy 8193 fails rather than moving to 8194.

**Reason.** The `/api` proxy is the only thing connecting the frontend to the backend in
dev, and a silently relocated dev server appears to work until the first API call.

---

## Root `CLAUDE.md`

### Stack table — drop `@mantine/form` (**recommendation; the architect's briefing must grant this file**)

**Change.** Remove `/form` from the `Components` row's `@mantine/core`, `/form`,
`/hooks`, `/tiptap` list, and add `@mantine/notifications` in its place.

**Reason.** The project-wide form convention is the MobX draft
(`ui-conventions.md`), which forbids using `@mantine/form`; the package is not
installed. `@mantine/notifications` **is** a dependency and **is** used, and the stack
table currently names the one that is not and omits the one that is — which is exactly
backwards for a table whose whole job is telling an agent what it may reach for.

---

_Nothing below this line is written by the planner._

## Observations

- Step 005: `notifyFailure` shows no title — only the reason as `message` — and falls back to the generic reason "Something went wrong. Please try again." for a non-`ApiError` value and for an `ApiError` whose message is empty. `ColorSchemeToggle` labels are "Switch to light theme" / "Switch to dark theme", and it passes `"dark"` as the computed-scheme fallback. Possible impact: record the generic-reason text and label wording in `ui-conventions.md` if they should be canonical.

---
Status: Applied 2026-10-01 — /architect finalization (with /product-spec finalization the same day)
Applied items: 25 (all planner entries; the nginx `/` fallback entry with modification)
Rejected items: 1 (`## Observations` — notifyFailure fallback text and ColorSchemeToggle labels are copy text, not architecture)
Notes: applied in batch 1, except the root `CLAUDE.md` stack-table entry, held as H3 and applied in batch 3 (Components row now `@mantine/core`, `/hooks`, `/notifications`, `/tiptap`; the same grant also refreshed the root file's id range). The nginx `/` fallback is recorded as an open seam owned by `fast/001.dev-and-container-harness`, mechanism not chosen. Both MobX entries landed together.
