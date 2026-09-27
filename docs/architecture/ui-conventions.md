# UI conventions

**Realizes:** FEAT-006, FEAT-007, FEAT-008, FEAT-009, FEAT-010, FEAT-011,
FEAT-012, FEAT-013, FEAT-017, FEAT-018, UC-030, UC-035, UC-043

This is a **contract**, not folklore. The geometry constants, the event-handling
choices and the performance strategies below were arrived at against real
browser and jsdom behaviour in the sibling project these conventions are
inherited from; each one that looks arbitrary has a reason recorded next to it.
A plan that "simplifies" one of these is changing behaviour, not style.

---

## Layout shell

Mantine `AppShell` with three regions: `navbar` (left), `Main` (center), `Aside`
(right). The aside is **hidden below the `md` breakpoint**.

RPHelper's mapping:

```
┌────────┬───────────────────────────┬──────────────────────────────┐
│ navbar │ main: session entry list  │ aside: compose discussion    │
│        │       (FEAT-009)          │        + answer box          │
│        │                           │        (FEAT-010)            │
└────────┴───────────────────────────┴──────────────────────────────┘
          ▲                          ▲
          │                    horizontal splitter (A)
      navigation                     │
                                vertical splitter (B) sits inside
                                the aside, between transcript and
                                answer box
```

The mapping is not incidental. FEAT-009's entry list is the roleplay's record and
FEAT-010's discussion is the workspace that produces the next item in it; both are
visible at once because the roleplayer works from the partner's text while
composing. Below `md` there is no room for both, so the aside hides and the
discussion becomes a full-width view.

---

## Two independent, hand-rolled resize behaviours

No resize library. **All geometry and persistence live in one pure, DOM-free
module** — the equivalent of the sibling project's `workspaceLayout.ts`. Its
functions take numbers and return numbers; they touch no `document`, no `window`
and no React. The reason is testability: every clamp, every edge case and every
persistence fallback below is unit-testable with no DOM at all, which is exactly
what the pipeline's test-coder needs (`docs/plans/CLAUDE.md` — tests written from
the spec, bound to frozen signatures).

The two behaviours are deliberately **not** unified. They differ in anchoring, in
geometry model, and in performance strategy, and each difference has a reason
recorded below. A shared abstraction would have to be parameterised on all three
and would obscure every one of them.

### (A) Aside width — horizontal splitter, right-anchored

**The handle.** A `Box role="separator"` absolutely positioned over the aside's
leading edge:

| Property | Value | Why |
|---|---|---|
| `width` | `6px` | wide enough to grab, narrow enough not to eat the aside's content |
| `cursor` | `col-resize` | |
| `touchAction` | `"none"` | otherwise the browser claims the gesture as a scroll and the pointer events stop arriving |

**Event handling.** `onPointerDown` calls `preventDefault()` **first**, then begins
the resize. The handlers attach `pointermove` / `pointerup` / `pointercancel` to
**`window`, deliberately NOT `setPointerCapture`**. Two reasons, both concrete:

- jsdom does not implement `setPointerCapture`, so a captured implementation is
  untestable without a browser.
- Window listeners keep tracking once the pointer has left the 6px handle — which
  it does immediately on any real drag.

`pointercancel` is handled alongside `pointerup` so a cancelled gesture ends the
drag and restores the body styles rather than leaving the page in a resizing
state.

**Geometry — right-anchored.** The aside is anchored to the right edge, so width
is measured from the right:

```
fraction = (viewportWidth - clientX) / viewportWidth
```

clamped to the range below. If `viewportWidth` is **non-finite or `<= 0`**, the
function returns the default rather than producing `Infinity` or a negative
width. That guard is not theoretical — a zero-size viewport is the normal state
in a headless test environment.

**Constants.**

| Constant | Value |
|---|---|
| default | `0.35` |
| min | `0.15` |
| max | `0.60` |
| keyboard step | `0.02` |

Expressed in **`vw` units**, so a window resize needs no listener at all — the
browser re-evaluates the unit. Values are **rounded to 2 decimals** to avoid
float noise accumulating in the persisted record and in the CSS string.

**No collapse-to-zero.** The minimum is `0.15`, and there is no separate collapse
state for the aside. The discussion is the working surface; a resize gesture must
not be able to make it disappear.

**Keyboard.** The separator is focusable. `ArrowLeft` **widens** the aside,
`ArrowRight` **narrows** it — because the aside is right-anchored, so moving the
boundary left makes it bigger. Stated explicitly because the mapping reads
backwards until you remember the anchor.

**Performance — CSS custom property driven by a single `autorun`.** The live width
is pushed to a CSS custom property by one MobX `autorun`:

```ts
autorun(() => {
  document.documentElement.style.setProperty("--rph-aside-width", `${state.asideWidthVw}vw`);
});
```

so **a pointer-move never re-renders the shell**. The aside's `width` prop is a
**frozen constant string computed once**:

```ts
const ASIDE_WIDTH = `calc(var(--rph-aside-width, 35vw))`;
```

**Gotcha, recorded because it will otherwise be "cleaned up":** the `calc(...)`
wrapper is **load-bearing**. Mantine's `rem()` processes the `width` prop, and it
mangles comma-bearing strings — a bare `var(--rph-aside-width, 35vw)` does not
survive it, while the same expression inside `calc(...)` does. Do not remove the
`calc`. Do not inline the fallback differently. Do not pass the raw `var()`.

**`AppShell` `transitionDuration` must be `0` while resizing.** Mantine animates
the shell's padding; with a non-zero duration the panel rubber-bands behind the
pointer for the whole drag. Set it to `0` on drag start and restore it on drag
end.

**Body styles for the drag duration.** `document.body` gets
`userSelect: "none"` and `cursor: "col-resize"`, both restored when the drag
ends (including on `pointercancel`). Without `userSelect: none` the drag selects
the transcript text it passes over.

### (B) Answer-box height — vertical splitter

**The handle.** An **ordinary flow child**, not absolutely positioned, sitting
between the discussion transcript and the answer box:

| Property | Value | Why |
|---|---|---|
| `height` | `12px` | a comfortable hit target for a horizontal grab |
| `marginBlock` | `-3px` | reclaims layout footprint from the surrounding stack gap, so a 12px hit target does not add 12px of visual space |
| inner line | 2px, `pointer-events: none` | the visible affordance must not intercept the gesture aimed at the 12px target |
| `cursor` | `row-resize` | |
| `touchAction` | `"none"` | same reason as (A) |

A flow child rather than an absolute overlay because the answer box's height is
part of the aside's vertical stack; an absolutely positioned handle would have to
track a position that the stack already computes.

**Geometry — delta-based, not absolute.**

```
height = clamp(startHeight + (startY - clientY))
```

Dragging **up grows** the box. Delta-based rather than absolute because the
handle's own position moves as the box grows; an absolute
`viewportHeight - clientY` model makes the box drift relative to the pointer
whenever the surrounding layout is not flush against the viewport bottom.

**Constants.**

| Constant | Value | Why |
|---|---|---|
| min | `64px` | about two lines — the box must always be usable |
| default | `96px` | about three lines |
| max | `0.5 × viewportHeight` | the transcript can never be squeezed out |
| keyboard step | `24px` | about one line |

**Clamp rule — the lower bound wins.** When the upper bound
(`0.5 × viewportHeight`) would fall **below** the lower bound (`64px`), the clamp
must return the lower bound. This is the short-screen edge case: on a very short
viewport, half the height is less than two lines, and the correct answer is a
usable box rather than an unusably small one. A naive
`Math.min(Math.max(v, min), max)` gets this wrong and returns `max`. State and
test it.

**No collapse-to-zero.**

**Keyboard.** `ArrowUp` grows the box, `ArrowDown` shrinks it.

**Performance — a plain MobX observable, NOT a CSS custom property.** This is
**deliberately different from (A)**, and the reasoning is the point, not the
mechanism: the answer box already re-renders on every keystroke, because it is a
controlled textarea holding the roleplayer's text. A per-pointermove re-render of
that same subtree therefore costs no more than ordinary typing does. Paying the
extra complexity of a CSS-variable channel would buy nothing here, while in (A) it
buys avoiding a re-render of the **entire shell** — a much larger tree that is
otherwise idle. Two different answers because the two subtrees have different
baseline render costs, recorded so neither is "made consistent" with the other.

### (C) The answer textarea deliberately does NOT auto-grow

Fixed height, driven entirely by (B):

- `resize: "none"`
- **no** `autosize`
- **no** `minRows` / `maxRows`
- it **scrolls internally** past its height

`resize: "none"` is **not cosmetic.** A fixed-height textarea keeps the browser's
native bottom-right resize grip unless it is disabled — and that grip would sit
directly under the Send icon, and would compete with the (B) handle for the same
gesture. Two resize affordances on one element, one of them native and
unstyleable, is a worse experience than one explicit handle. Stated here so it is
not "fixed" later by re-enabling autosize or the native grip.

The roleplayer controls the box's height explicitly through (B); auto-growth would
fight that control on every keystroke.

---

## Layout persistence

**One** localStorage record under the key **`rphelper.workspace-layout`**.

The key is **renamed** from the sibling project's and **must not be copied
verbatim** — two applications sharing a localStorage key on the same host would
read each other's geometry, and these two projects are explicitly designed to run
side by side (`deployment.md`'s port table).

Shape:

```ts
type WorkspaceLayout = {
  navCollapsed: boolean;
  asideWidth: number;       // vw fraction, 2 decimals
  answerBoxHeight: number;  // px
};
```

**Read is total and never throws.** Absent key, unparseable JSON, wrong types,
missing fields, out-of-range numbers — every case falls back **per field** to that
field's default, and every numeric field is **clamped on read** using the same
clamps as (A) and (B). A stored record from an older version, or from a much larger
monitor, therefore produces a usable layout rather than a broken one. The function
returns a complete record; there is no partial result and no `null`.

**Write is best-effort.** Wrapped in `try`/`catch` and **swallowed** — private
browsing modes and quota exhaustion both throw, and neither is a reason to
interrupt a resize. A write merges its patch over a **fresh total read**, so two
independently-persisted fields cannot clobber each other.

**Written once on pointer-up, never mid-drag.** A localStorage write per
pointermove is both wasteful and a jank source.

---

## Icons

**`@tabler/icons-react`** at `^3.40`. One family, for one visual weight.

### Sizing convention

| Context | Props |
|---|---|
| Main, header and composer actions | `size={18} stroke={1.5}` |
| Inline controls | `size={16}` |
| Smallest chevrons | `size={14}` |

Colour is left as `currentColor`; semantic colour is applied via the **wrapping
button's** `color` prop, never on the icon. One place decides colour, and it is
the place that also decides hover and disabled states.

### Every icon-only action goes through a shared `IconButton`

An icon-only button is `Tooltip` + Mantine `ActionIcon` + an `aria-label` that
serves as the accessible name.

**This is a deliberate deviation from the sibling project.** BookWriter has no
shared component: every call site repeats the `Tooltip`, the `ActionIcon`, the
`size`, the `stroke` and the `aria-label` inline. RPHelper has roughly **15
distinct icon actions** (table below), several of them appearing in more than one
place, so the abstraction pays for itself immediately — and, more importantly, an
accessible name that is repeated at 20 call sites is an accessible name that is
wrong at two of them.

```tsx
type IconButtonProps = {
  icon: React.ComponentType<{ size?: number | string; stroke?: number }>;
  label: string;                     // tooltip text AND aria-label — one source
  onClick: () => void;
  disabled?: boolean;
  color?: MantineColor;              // semantic colour, applied to ActionIcon
  sizeVariant?: "main" | "inline" | "chevron";   // maps to 18/16/14 + stroke
};
```

**Call sites must go through `IconButton`.** A bare `ActionIcon` wrapping a Tabler
icon is a defect, because it is how an action ends up with a tooltip and no
`aria-label`, or with the two disagreeing. `label` is a single prop feeding both
precisely to prevent that.

**The one boundary — `IconButton` versus the table overflow menu.** There is a
real tension between the rule above and the table convention below, and it is
resolved by scope rather than left to taste:

| Place | Pattern |
|---|---|
| Toolbars, headers, the composer, inline controls | **`IconButton`** — an icon-only action with a tooltip and an accessible name |
| **Table rows** | a single **overflow `Menu`** behind one `IconDots` trigger; the row's actions are menu *items with text labels*, not icons |

So a table row contains exactly **one** icon-only control — the `IconDots`
trigger, which itself goes through `IconButton` — and no others. The reason the
two rules do not conflict: inside the menu the actions are labelled text, so
there is no accessible-name problem for `IconButton` to solve, and a row of four
icon buttons is both a discoverability problem and the thing that makes a row
layout collapse on a narrow viewport.

### Icon table

| Action | Icon | Feature |
|---|---|---|
| Send message in discussion | `IconSend` | FEAT-010 |
| Stop generation | `IconPlayerStop` | FEAT-010 |
| Settle answer | `IconMessageCheck` | FEAT-010 |
| **Copy settled answer out** | `IconCopy` | FEAT-009 |
| Translate / flicker | `IconLanguage` | FEAT-011 |
| New session / character / setup | `IconPlus` | FEAT-006 / FEAT-007 / FEAT-008 |
| Archive / restore | `IconArchive` / `IconArchiveOff` | FEAT-006 / FEAT-007 / FEAT-008 |
| Session configuration | `IconAdjustmentsHorizontal` | FEAT-013 |
| My search | `IconSearch` | FEAT-017 |
| Memos | `IconNotes` | FEAT-012 |
| Edit entry | `IconEdit` | FEAT-009 |
| Save | `IconDeviceFloppy` | FEAT-012 |
| Collapse / expand | `IconChevronDown` / `IconChevronRight` | FEAT-010 |
| Re-open discussion | `IconArrowBackUp` | FEAT-010 |
| Overflow menu | `IconDots` | — |
| Export / import | `IconDownload` / `IconUpload` | FEAT-018 |
| Admin nav — Users | `IconUsers` | FEAT-003 |
| Admin nav — LLM Servers | `IconServer2` | FEAT-004 |
| Admin nav — Database | `IconDatabase` | FEAT-005 |

Notes on individual choices:

- **`IconCopy` has no precedent in the sibling project** — BookWriter has no copy
  action at all. It is specified here rather than inherited, because copying the
  settled answer out is RPHelper's **entire outbound boundary**: `vision.md` states
  "the boundary is the clipboard", and UC-030/US-033.AC-1 is the one operation that
  crosses it. It is not a convenience affordance; it is the last step of the
  product's main flow, and it should be as prominent as Send.
- **`IconArrowBackUp` for re-open** rather than an "expand" icon, because re-open
  is an **undo for a mis-click, not a workflow** (UC-037, R7). The icon should say
  "undo", and it should be absent — not merely disabled — once an entry follows the
  answer, since at that point the action does not exist.
- `_TBD: IconMessageCheck for "settle" is a proposal. Settling is the most
  consequential action in the product (UC-035) and no icon was validated against a
  user; a label-bearing button may be the right answer instead of an icon-only
  one._`
- `_TBD: IconLanguage is proposed for the translation flicker (UC-039/UC-040),
  which is a two-state toggle rather than a one-shot action. Whether the flicked
  state is shown by a filled/active button, a different icon, or a text label is
  not specified._`
- `IconDots` traces to no feature — it is a container for actions that are
  themselves feature-bound, so it carries no id of its own.

### Accessibility floor

- Every icon-only control has an accessible name (via `IconButton`'s `label`).
- Both splitters are `role="separator"`, focusable, and keyboard-operable with the
  arrow keys and steps given in (A) and (B). A pointer-only resize would put the
  workspace layout out of reach entirely for keyboard users.
- `_TBD: no wider accessibility target (WCAG level, screen-reader matrix) is
  stated in docs/product/. The floor above is what the resize and icon contracts
  require, not a considered accessibility posture._`

---

## Lists, modals and forms — the CRUD conventions

These govern every list-plus-modal screen. They were arrived at in the sibling
project and are mostly **inherited**; the admin area
(`admin-surfaces.md`) is their densest user, but the form convention in
particular applies to the `app` entry too. Deviations and additions are marked.

### Tables

Plain Mantine **`Table`**, `striped highlightOnHover`. **No data-table library**
and **no card lists**. A table is a table: one element type, one place to look
for column definitions, and no third-party abstraction between the data and the
markup.

**Row actions** go in an overflow **`Menu`** behind an `IconDots` `ActionIcon`, in
a trailing **`w={60}`** column. Never a row of inline icon buttons — see the
boundary note in the Icons section above.

### No sorting, filtering or pagination — deliberate

**Every admin list loads and renders the full set.** No column sorting, no filter
box, no pagination, no virtualisation.

This is a **deliberate simplification**, not an omission: nothing in
`docs/product/` asks for any of the three, and each one adds a query parameter, a
piece of URL state and a class of off-by-one bug. The assumption it rests on,
stated so it can be checked: **small cardinality** — a self-hosted,
single-instance product (`overview.md`) has a handful of accounts and a handful of
LLM servers.

`_TBD: the no-pagination decision assumes a small user count and a small server
count. docs/product/ states no cardinality bound. A deployment with a large
number of accounts — or any future admin list over content-scale data — needs this
revisited; the flip condition is a list that no longer fits in one screenful of
scrolling._`

### Loading, errors and empty states

- **Loading** — a centered Mantine `Loader`, gated on an explicit
  idle/loading status field rather than on "data is still null". An explicit
  status distinguishes "not asked yet" from "asked, nothing came back".
- **Errors** — an inline red `Text` or `Alert` **above** the table. Not a toast,
  not a modal (see below).
- **Empty state** — the sibling project has **no empty-state component**: an
  empty list renders an empty table body, with headers and nothing under them.
  Flagged as a **weak spot RPHelper may improve**, not mandated: a first-run
  administrator seeing an empty LLM-servers table with no "add your first server"
  hint is a real if minor failure. Nothing in `docs/product/` requires an empty
  state, so none is specified here — an improvement is welcome and is not a
  deviation.

### Create and edit are always a `Modal`

A Mantine **`Modal`** — never a drawer, never inline row editing, never a separate
route. One interaction model for every create and edit in the product, so a
reader of any page knows where the form will appear, and so a form's lifetime is
visibly the modal's.

**Modal open/target flags are component-local `useState`**, never page MobX state:

```tsx
const [createOpen, setCreateOpen] = useState(false);
const [editTarget, setEditTarget] = useState<UserRow | null>(null);
```

The reasoning, recorded because it looks like an inconsistency against the
"state lives in MobX" rule: **which modal is open is view state, not domain
state.** It has no meaning outside the component that renders it, it is not read
by anything else, and putting it in the page store would make the store's shape
depend on the page's visual arrangement. Domain data goes in the MobX class;
"is this dialog showing" does not.

### `@mantine/form` is NOT used — the MobX draft convention

This is the **project-wide form convention** and it applies well beyond the admin
area. `@mantine/form` is a listed dependency (`overview.md`) and is deliberately
not used for these forms.

Every modal has a hand-rolled MobX **draft class** in a same-named `*Draft.ts`
sibling module:

```ts
// CreateUserDraft.ts
export class CreateUserDraft {
  username = "";
  password = "";
  passwordConfirm = "";
  role: Role = "roleplayer";
  serverErrors: Record<string, string> = {};   // field name -> message, plus a general key
  submitStatus: "idle" | "submitting" | "done" = "idle";

  constructor() { makeAutoObservable(this, {}, { autoBind: true }); }

  get clientErrors(): Record<string, string> { /* pure validation over the fields */ }
  get errors(): Record<string, string> { /* clientErrors merged with serverErrors */ }
  get canSubmit(): boolean { /* no clientErrors && submitStatus !== "submitting" */ }
}

// the effectful half is a FREE FUNCTION, never a method:
export async function submitCreateUser(
  draft: CreateUserDraft,
  onSaved: () => void,
  signal?: AbortSignal,
): Promise<void> { /* call the API, map errors into draft.serverErrors, then onSaved() */ }
```

Four rules, each with its reason:

1. **The draft class holds observable fields and getters only.** `clientErrors`,
   `errors` and `canSubmit` are **computed getters over pure validation** — so the
   validation rules are testable by constructing a draft and reading a getter,
   with no render and no network.
2. **The submit is an external function `submitX(draft, ..., onSaved, signal?)`,
   never a method on the draft.** This is the repo's MobX rule — **no effectful
   class methods** — and it holds for page stores too (`frontend-structure.md`).
   The payoff is that the observable object stays a data structure: anything that
   can fail, await or navigate is a function you can see being called.
3. **`serverErrors` is keyed by field name, plus a general form key.** The submit
   function maps API errors (`backend-structure.md`'s
   `{code, message, detail}`) onto field keys — by **status or code**, not by
   parsing prose — and anything unmappable lands on the general key and renders
   above the form. A form that can only show field errors swallows the ones that
   matter most.
4. **On success the submit invokes the page's refresh callback.** The draft does
   not know about the list; the page passes `onSaved`.

**Draft lifetime — a fresh instance per open.** `useState(() => new XDraft(...))`
inside a **conditionally mounted** modal body, so opening the modal constructs a
draft and closing it discards one. **Not** a long-lived draft that is reset on
close: a reset function is one more thing to keep in step with the field list, and
a forgotten field is a stale value shown to the next user of the dialog.

### Async feedback is inline — there is no toast system

**`@mantine/notifications` is not used and is not a dependency.** Feedback is
inline, in the form or above the table.

**Success is implicit**: the modal closes and the list refreshes. That pairing is
the success signal — a list that visibly contains the new row says more than a
toast that says it was created. Kept deliberately, and recorded so it is not
"improved": nothing in `docs/product/` asks for transient notifications, and a
toast system introduces a second, timed, easily-missed channel for messages that
the inline one already carries reliably.

### Mutations are never optimistic

Every mutation is followed by a **re-load** of the affected list or report.
Nothing is written into the local store in anticipation of success.

- Failures land in the page's **error field** and are rendered above the table.
- Invocations from event handlers are **`void`-ed with a non-rethrowing catch**,
  so a rejected promise becomes a rendered error rather than an unhandled
  rejection.

Optimistic updates are declined because the value they buy — hiding one round-trip
on a local-network, single-instance application — is small, while the cost is a
second source of truth for every list plus a rollback path per mutation. A
re-load also means the list reflects whatever the server actually did, including
side effects the client did not predict (a disable that also revoked sessions, a
role change the server refused).

### NEW — the confirm convention

**The sibling project has no confirm pattern anywhere**: every delete and every
disable is a single unconfirmed click. RPHelper **adds one**, so this is
**designed, not inherited**.

**One shared mechanism**, used everywhere a destructive action appears: a small
confirm `Modal` — consistent with the rule that all dialogs are modals — taking
the action's title, a one-sentence consequence, a labelled confirm button
(`color="red"` for a destroy, the action's own verb otherwise), and a cancel. It
is a component, not a per-page hand-roll, so the wording shape and the button
order cannot drift between pages.

The actions that use it, and why each is destructive:

| Action | Feature | Consequence that earns the confirm |
|---|---|---|
| Disable an account | FEAT-003 | it **ends that user's login sessions** — someone is signed out mid-roleplay |
| Delete an LLM connection | FEAT-004 | irreversible removal of a registration and its enabled-model set |
| Rebuild the vector index | FEAT-005 | expensive: re-embeds every memo and session, real time and real metered LLM calls (UC-016) |

**The confirm text must not name a blast radius it is not allowed to know.** R5
forbids "N sessions use this model" (`domain-rules.md`, `admin-surfaces.md`) — the
consequence sentence describes the action, never a count derived from other users'
data.

**No acceptance criterion requires any of this.** It is an architectural
judgement about irreversible and expensive operations, so **FEAT-003, FEAT-004 and
FEAT-005's planners may revisit it** — including dropping it for an action whose
plan argues the friction is not worth it. Stated plainly so it is neither treated
as a requirement nor quietly deleted as an accident.

**BookWriter is internally inconsistent here and should not be copied either
way:** its sub-agents use disable-only-with-no-delete, while its LLM servers use a
hard delete. RPHelper makes a **deliberate choice per entity**: accounts disable
and re-enable and are never deleted (FEAT-003, `data-model.md`); characters,
setups and sessions archive and are never deleted (R6); LLM connections **are**
deleted, because a registration is administrative configuration with no content
hanging off it and no restore requirement anywhere in `docs/product/`.

### Page state — the same MobX convention as the app area

Identical to `frontend-structure.md`'s rule, restated because the admin pages are
its simplest instance:

```ts
class UsersPageState {
  users: UserRow[] = [];
  status: "idle" | "loading" | "ready" = "idle";
  error: string | null = null;
  constructor() { makeAutoObservable(this, {}, { autoBind: true }); }   // NO methods
}

export async function loadUsers(state: UsersPageState, signal?: AbortSignal) { ... }
export async function disableUser(state: UsersPageState, id: number, signal?: AbortSignal) { ... }
```

- **`makeAutoObservable` class with no methods.** Behaviour is free functions
  taking the state as their first argument.
- Every free function **`runInAction`s its writes** — an `await` ends the
  enclosing action, so a post-await assignment outside `runInAction` is a MobX
  strict-mode violation and, worse, an untracked write.
- Every free function **early-returns on an aborted signal** before writing, so a
  response that arrives after unmount cannot write into a dead store.
- Driven from a **page-level `useEffect` with an `AbortController` cleanup**:

```tsx
useEffect(() => {
  const ac = new AbortController();
  void loadUsers(state, ac.signal).catch(() => {});   // error already in state.error
  return () => ac.abort();
}, [state]);
```

---

## Other inherited frontend facts

Recorded here so `ui-conventions.md` is self-sufficient for someone building a
screen:

- **React 19**, TypeScript.
- **Mantine 7** — `@mantine/core`, `@mantine/hooks`, `@mantine/tiptap`. No
  Tailwind, no CSS modules, no styled-components; one small hand-written
  `global.css` for resets. **`@mantine/form` is present as an inherited dependency
  but is deliberately not used** — forms go through the MobX draft convention
  above. **`@mantine/notifications` is not a dependency at all** — there is no
  toast system.
- **`@mantine/hooks` is used for non-stateful helpers only.** A custom hook must
  not hold reactive state (`admin-surfaces.md`'s shell-state note): reactive state
  lives in a MobX class instantiated with `useState(() => new X())`. This is why
  `useDisclosure` does not appear anywhere in this codebase even though it would
  fit several call sites.
- **MobX 6** + `mobx-react-lite`. Per-page store classes, passed as props, no
  context (`frontend-structure.md`).
- **`react-router-dom` 7** within an entry.
- **TipTap + `tiptap-markdown`** for editing and **`react-markdown`** for
  rendering — together these cover FEAT-012/UC-043's markdown editor with live
  preview.
- **`@dnd-kit`** is available for reorder interactions; nothing currently requires
  it (`frontend-structure.md`).
