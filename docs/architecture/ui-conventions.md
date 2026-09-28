# UI conventions

**Realizes:** FEAT-006, FEAT-007, FEAT-008, FEAT-009, FEAT-010, FEAT-011,
FEAT-012, FEAT-013, FEAT-017, FEAT-018, FEAT-020, UC-030, UC-032, UC-035,
UC-037, UC-043, UC-069, UC-070, UC-071, UC-072, UC-075, UC-082, UC-085,
US-044.AC-3, US-044.AC-4

**The workspace shell lives in `workspace-shell.md`** — the three columns, all
geometry, the note wall's two modes, layout persistence, and the anatomy of the
stream and the current zone. This file holds everything that is not the shell:
icons, tables, modals, forms, feedback and page state.

This is a **contract**, not folklore. The conventions below were arrived at in the
sibling project these are inherited from, or designed here against a stated
requirement; each one that looks arbitrary has a reason recorded next to it. A plan
that "simplifies" one of these is changing behaviour, not style.

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
`size`, the `stroke` and the `aria-label` inline. RPHelper has roughly **30
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

The stream is a third case and is governed by `workspace-shell.md`: an entry's
actions sit inside the entry as `IconButton`s, because an entry is a document, not
a row, and the overflow-menu rule exists to keep a *row* from collapsing.

### Icon table

| Action | Icon | Feature |
|---|---|---|
| Send message in discussion | **labelled button**, not an icon | FEAT-010 |
| Stop generation | `IconPlayerStop` | FEAT-010, UC-085 |
| Settle | **labelled primary button**, not an icon | FEAT-010 |
| **Copy settled turn out** | `IconCopy` | FEAT-009 |
| Copy as plain text (composer) | `IconCopy` | FEAT-009 |
| Translate / flicker | `IconLanguage` | FEAT-011 |
| New session / character / setup | `IconPlus` | FEAT-006 / FEAT-007 / FEAT-008 |
| Archive / restore | `IconArchive` / `IconArchiveOff` | FEAT-006 / FEAT-007 / FEAT-008 |
| Session configuration | `IconSettings` | FEAT-013 |
| My search | `IconSearch` | FEAT-017 |
| Memos / the note wall | `_TBD:` — see the note below | FEAT-012 / FEAT-020 |
| Edit entry, message or note | `IconEdit` | FEAT-009 / FEAT-010 / FEAT-012 |
| Save | `IconDeviceFloppy` | FEAT-012 |
| Collapse / expand (chevron) | `IconChevronDown`, rotated | FEAT-010 / FEAT-020 |
| Re-open a settled block | `IconArrowBackUp` | FEAT-010 |
| Overflow menu | `IconDots` | — |
| Export / import | `IconDownload` / `IconUpload` | FEAT-018 |
| Admin nav — Users | `IconUsers` | FEAT-003 |
| Admin nav — LLM Servers | `IconServer2` | FEAT-004 |
| Admin nav — Database | `IconDatabase` | FEAT-005 |

Workspace additions (FEAT-020 and its neighbours). The mockup they come from draws
**inline SVG rather than importing Tabler components**, so it settles the glyph and
its meaning, not the import name. A Tabler name appears below only where the drawn
glyph maps onto one unambiguously; the rest are `_TBD:` rather than a guess.

| Action | Icon | Realizes |
|---|---|---|
| Kind switch — *partner* / *my turn* | **two labelled segments**, no icons | US-120 |
| Discard an **empty** current zone | `_TBD:` — the mockup predates UC-086 and draws no glyph; the control is **absent**, not disabled, once the zone holds anything (US-134.AC-2), on `IconArrowBackUp`'s precedent | UC-086, US-134 |
| Collapse the tree | `_TBD:` — glyph is a left chevron against a right-hand bar | UC-070, US-090 |
| Expand the tree from the rail | `IconMenu2` | UC-070, US-090 |
| Expand / collapse a character in the tree | `IconChevronDown`, rotated `-90°` when collapsed | UC-069, US-088 |
| Open the note wall | same glyph as Memos — `_TBD:` | UC-072 |
| Pin / unpin the wall | `IconPin`, **one icon with an active state** | UC-072, US-094 |
| Dismiss the wall | `IconX` | UC-072 |
| Note forced / not forced | `IconPin` — **the same glyph as the wall pin** | UC-075, US-098, US-099 |
| Note enabled / disabled | `_TBD:` — glyphs are a circle with a bar and a circle with a slash | UC-075, US-100, US-101 |
| Collapse / expand a tool call | `IconChevronDown`, rotated, plus a tool glyph `_TBD:` | US-114 |
| Collapse / expand thinking | `IconChevronDown`, rotated, plus `IconBulb` | US-114 |
| User menu — settings | `IconSettings` | UC-071, US-092 |
| User menu — admin area | `IconShield` | UC-071, US-093 |
| User menu — log out | `IconLogout` | UC-071, US-091 |

Notes on individual choices:

- **`IconCopy` has no precedent in the sibling project** — BookWriter has no copy
  action at all. It is specified here because copying the settled turn out is
  RPHelper's **entire outbound boundary**: `vision.md` states "the boundary is the
  clipboard", and UC-030/UC-082/US-033.AC-1 is the one operation that crosses it.
  Not a convenience affordance — the last step of the product's main flow. It
  yields **plain text, never markdown** (US-124), and a `kind='decision'` entry
  offers **no copy action at all** (US-123) — absent, not disabled.
- **Settle and Send are labelled buttons, not icons.** This **resolves** the
  previous `_TBD:` that proposed `IconMessageCheck` for settle and noted a
  label-bearing button might be right instead. Settle is the most consequential
  action in the product (UC-035) and is the composer's primary button; Send is
  secondary beside it. `IconMessageCheck` is not used anywhere.
- **`IconArrowBackUp` for re-open** rather than an "expand" icon, because re-open
  is an **undo for a mis-click, not a workflow** (UC-037, R7). It should be absent
  — not merely disabled — once anything sits in the current zone, since at that
  point the action does not exist (US-128).
- **One chevron, rotated, not two icons.** The mockup rotates a single
  `IconChevronDown` by `-90°` rather than swapping to `IconChevronRight`: one icon
  animates between the two states, two icons cut. This supersedes the earlier
  `IconChevronDown` / `IconChevronRight` pair.
- **`IconSettings` (a gear) for session configuration**, not
  `IconAdjustmentsHorizontal` — the mockup draws the same gear for the session's
  settings and the user menu's, and two glyphs for "settings" in one shell reads as
  a bug.
- **Edit is one action with one icon** across settled entries, current-zone
  messages and notes — all three are the same in-place edit saved on focus loss
  (US-104, US-109, US-110, US-115). The mockup's glyph is a plain pencil
  (`IconPencil`); `IconEdit` is kept as the name because it was already this
  project's choice and the two differ only in whether the pencil sits in a frame.
  Substituting `IconPencil` is a glyph choice, not a behaviour change.
- `_TBD: the wall pin and the note "forced" flag are drawn with the same pin
  glyph — one means "keep this panel open", the other "put this note in the system
  prompt". Two unrelated meanings on one glyph in one screen. Unresolved: neither
  the mockup nor docs/product/ settles a second glyph._
- `_TBD: the enabled/disabled note toggle's glyphs (a circle with a bar, a circle
  with a slash) map onto no Tabler icon unambiguously, and whether the control is a
  two-icon swap or one icon with a struck state is also unsettled; the mockup swaps
  the glyph and additionally dims and strikes the note body._
- `_TBD: IconLanguage is proposed for the translation flicker (UC-039/UC-040),
  which is a two-state toggle rather than a one-shot action. Whether the flicked
  state is shown by a filled/active button, a different icon, or a text label is
  not specified._`
- `IconDots` traces to no feature — it is a container for actions that are
  themselves feature-bound, so it carries no id of its own.

### Accessibility floor

- Every icon-only control has an accessible name (via `IconButton`'s `label`).
- **Actions revealed on hover must also be revealed on `:focus-within`.** The
  stream's per-entry actions and the note's flag icons are hover-revealed
  (`workspace-shell.md`); a hover-only reveal puts them out of reach of a keyboard
  entirely.
- **Note reordering must have a keyboard path.** `@dnd-kit`'s keyboard sensor is
  required, not optional, because reordering changes what the system prompt
  contains (R3, US-102) — it is a content operation wearing a drag gesture. This
  is the same principle the deleted resize splitters were held to, and it is now
  the only place it applies.
- `_TBD: no wider accessibility target (WCAG level, screen-reader matrix) is
  stated in docs/product/. The floor above is what the icon and interaction
  contracts require, not a considered accessibility posture._`

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
scrolling._

### Loading, errors and empty states

- **Loading** — a centered Mantine `Loader`, gated on an explicit
  idle/loading status field rather than on "data is still null". An explicit
  status distinguishes "not asked yet" from "asked, nothing came back".
- **Errors** — an inline red `Text` or `Alert` **above** the table. Not a modal,
  and **not also a notification**: a failure with a place to render in-page
  renders there and nowhere else. The transient-notification channel below is for
  failures that have no such place.
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

**Two named exceptions, both in the workspace and both detailed in
`workspace-shell.md`**: a settled entry, a current-zone message and a note are
**edited in place** where they sit (UC-078, US-104, US-109, US-110, US-115), and
creating a character opens a **draft page** (UC-074, US-097). Neither weakens the
rule, which exists to give a *form* a visible lifetime and one predictable place to
appear: the first is a single text field rendered where its content belongs, the
second persists nothing until there is content. Every create and every multi-field
edit is still a modal.

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

### Async feedback — no *success* toasts, and one narrow use of notifications

**This rule is rewritten, not deleted, and the change is narrow.** It used to
read "there is no toast system" and to list `@mantine/notifications` as not a
dependency. **US-044.AC-4 reverses half of it**: a failed generation must show
its reason, and **the reason must not persist once the notice has gone**. An
inline error above the stream cannot satisfy that — it either stays until
something replaces it or waits for a manual dismissal, and "does not persist" is
the criterion.

**The rule is now: no *success* toasts.**

- **Success feedback is unchanged.** The modal closes and the list refreshes.
  That pairing is the success signal — a list that visibly contains the new row
  says more than a toast saying it was created. The original reasoning was always
  about **success noise**, and that half holds exactly as written: nothing in
  `docs/product/` asks for a transient success message, and adding one introduces
  a second, timed, easily-missed channel for something the inline one already
  carries reliably.
- **`@mantine/notifications` IS a dependency**, added for **transient failure
  reasons only**, with **`autoClose: 5000`**.

**What it carries** — a failure's *reason*, for any typed failure that is not
already rendered in place: `llm_unreachable`, `model_not_enabled`,
`translation_failed`, `tool_failed`, and the rest of
`backend-structure.md`'s error table on the same condition. A failure that
already has a place to be rendered — a field error in a modal, the inline
`Alert` above an admin table, the no-embedding-model banner above the stream
(US-112) — keeps rendering there and does **not** also raise a notification.

**The boundary a reviewer can check, stated as one line:**

> **A notification whose message is a success is a defect.**

That is the whole test. It is phrased that way because "no toasts, except…" is a
rule nobody can apply, while "failures only" is a rule that is either satisfied
or visibly broken at the call site.

#### The tension with US-044.AC-3, and how it is resolved

US-044.AC-3 requires that a retry is **possible** after a failure. US-044.AC-4
requires the reason **not to persist**. Put both on the notification and they
contradict: if the notice carries the only retry affordance and auto-dismisses
after five seconds, the retry vanishes with it, and a roleplayer who looked away
has lost the action rather than the message.

**They are split, and the split is the design:**

| Carries | Where | Lifetime |
|---|---|---|
| The **reason** the generation failed (US-044.AC-4) | the transient notification | ~5s, then gone |
| The **retry** affordance (US-044.AC-3) | **in the stream, at the failed exchange** | persists until the exchange succeeds or is abandoned |

The retry belongs where the failure happened, because that is the only place that
still knows what to retry. The notification carries the reason precisely because
the reason is the thing the product says must not persist — and a reason without
its retry is a message, which is what a transient channel is for.

Nothing in the record is discarded on either path (R10): the failure notice and
the retry control are both additive to a zone and a settled record that survive
intact.

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

The workspace's in-place edits narrow the *scope* of the re-load to the edited row
rather than the whole stream, and the reasoning is in `workspace-shell.md`. The
rule's intent — what renders is what the server stored — is unchanged.

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
export async function disableUser(state: UsersPageState, id: string, signal?: AbortSignal) { ... }
//                                                            ^ string, never number
//                                                              (frontend-structure.md, "Ids are strings")
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
- **Mantine 7** — `@mantine/core`, `@mantine/hooks`, `@mantine/tiptap`,
  `@mantine/notifications`. No Tailwind, no CSS modules, no styled-components;
  two small hand-written stylesheets (`frontend-structure.md`).
  **`@mantine/form` is present as an inherited dependency but is deliberately not
  used** — forms go through the MobX draft convention above.
  **`@mantine/notifications` IS a dependency and IS used**, for transient
  **failure reasons only**, `autoClose` 5000 — this reverses the earlier "not a
  dependency at all, there is no toast system" note, narrowly, on US-044.AC-4.
  Success toasts remain forbidden; see the feedback section above for the
  boundary.
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
- **`@dnd-kit`** is used for exactly one interaction: reordering notes within a
  level on the wall (UC-076, US-102, US-103). See `workspace-shell.md`. It is not
  available for anything else without a requirement that asks for it.
