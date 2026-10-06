# Forms, lists and CRUD conventions

**Realizes:** FEAT-003, FEAT-004, FEAT-005, FEAT-006, FEAT-007, FEAT-008,
FEAT-012, FEAT-013, FEAT-018, FEAT-020, UC-014, UC-015, UC-020, UC-074, UC-078,
US-015.AC-2, US-018.AC-3, US-018.AC-4, US-097, US-104, US-109, US-110, US-115

**This doc was split out of `ui-conventions.md`** at the finalization of plans
008..032. It holds the CRUD half: tables and lists, the modal rule and its named
exceptions, the MobX draft form convention, the confirm convention, the
empty-state rule, the never-optimistic rule, and the page-state convention.
`ui-conventions.md` keeps icons, the icon table, the shared `IconButton`, the
accessibility floor and async feedback. Read both; neither repeats the other.
The workspace shell is a third doc, `workspace-shell.md`.

These govern every list-plus-modal screen. They were arrived at in the sibling
project and are mostly **inherited**; the admin area (`admin-surfaces.md`) is
their densest user, but the form convention in particular applies to the `app`
entry too. Deviations and additions are marked.

This is a **contract**, not folklore. A plan that "simplifies" one of these is
changing behaviour, not style.

---

## Tables

Plain Mantine **`Table`**, `striped highlightOnHover`. **No data-table library**
and **no card lists**. A table is a table: one element type, one place to look
for column definitions, and no third-party abstraction between the data and the
markup.

**Row actions** go in an overflow **`Menu`** behind an `IconDots` `ActionIcon`, in
a trailing **`w={60}`** column. Never a row of inline icon buttons — see the
boundary note in `ui-conventions.md`'s Icons section.

Two as-built firsts from the character page's Setups section, recorded so a later
list section does not re-decide them (plan 010):

- **A `Menu.Item` with a `leftSection` icon uses the "inline" metrics** —
  `size={16} stroke={1.5}`, the icon table's second row. A menu item is an inline
  control, not a main action.
- **A one-data-column action table carries no `Table.Thead`.** With one data
  column plus the `w={60}` action cell, a header row adds noise and one more
  announced row for no information. A table with two or more data columns keeps
  its header.

## No sorting, filtering or pagination — deliberate

**Every admin list loads and renders the full set.** No column sorting, no filter
box, no pagination, no virtualisation. The `app` entry's lists — characters,
setups, sessions, notes — follow the same rule, and the tree is the same shape
one level up.

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

My-search is the one surface with a cap, and it is a result cap rather than
pagination: at most **20** hits per group, with no "next page"
(`search-and-retrieval.md`).

## Loading, errors and empty states

- **Loading** — a centered Mantine `Loader`, gated on an explicit
  idle/loading status field rather than on "data is still null". An explicit
  status distinguishes "not asked yet" from "asked, nothing came back".
  `frontend-structure.md` names the four-value ladder new list stores copy.
- **Errors** — an inline red `Text` or `Alert` **above** the table. Not a modal,
  and **not also a notification**: a failure with a place to render in-page
  renders there and nowhere else. `ui-conventions.md`'s async-feedback section
  owns the transient channel, which is for failures that have no such place.
- **Empty state** — the sibling project has **no empty-state component**: an
  empty list renders an empty table body, with headers and nothing under them.
  Flagged as a **weak spot RPHelper may improve**, not mandated: a first-run
  administrator seeing an empty LLM-servers table with no "add your first server"
  hint is a real if minor failure. Nothing in `docs/product/` requires an empty
  state, so none is specified.

**Where the `app` entry did write one, it wrote a neutral line and not an
invitation**, and the reason is a constraint worth keeping (010 D13, 011 D18):

| Line | Where | Why neutral |
|---|---|---|
| "No setups yet." | the character page's Setups section | a setup is **optional** (R2 — no flow may require one), so an invitation to create one would nag the roleplayer about an object they may never want |
| "No sessions yet." | the character page's Sessions section | the section already carries the start control beside it; the line states a fact, not a call to action |

So the improvement the doc welcomes is still welcome, with one bound: an
empty-state line for an optional object says that it is empty and no more.

## Create and edit are always a `Modal`

A Mantine **`Modal`** — never a drawer, never inline row editing, never a separate
route. One interaction model for every create and edit in the product, so a
reader of any page knows where the form will appear, and so a form's lifetime is
visibly the modal's.

**The worked example in the `app` entry is the setup modal** (010 D2), the first
modal outside the admin area, and it is the shape every later one copies:
conditionally mounted, a fresh draft per open, open/target flags in
component-local `useState`, a server failure rendered **inside** the modal, and on
success the returned row applied to the list and then the modal closed — in that
order, so the list is already correct when the form disappears.

### The named exceptions

Three, each detailed where it lives, and each narrow for a stated reason. None
weakens the rule, which exists to give a *form* a visible lifetime and one
predictable place to appear.

| Exception | Where | Why it is not a form |
|---|---|---|
| **In-place edit** of a settled entry, a current-zone message and a note (UC-078, US-104, US-109, US-110, US-115) | `workspace-shell.md` | one text field rendered in the position where its content belongs; UC-078 requires it to be edited *where it sits* |
| **The character draft page** (UC-074, US-097) | `workspace-shell.md` | it persists nothing until there is content, so there is nothing to submit |
| **Starting a session** (011 D1, user decision) | `workspace-shell.md`'s character page | a **one-choice inline control** — a Setup select plus a "Start session" button in the Sessions section header. One optional choice is not a form, and a modal around a single select is friction with nothing to hold |

Every create and every multi-field edit is still a modal.

**The settings page's Languages form is a reading of the second exception, not a
fourth one** (017 D15). `/settings` carries the two languages edited on the page
with an explicit **Save**, and the character page's persona block did the same
before blur-save replaced it. The reading: **the route *is* the form** — there is
no list the form appears over and no other content the modal would protect, so
the page's own lifetime is the form's lifetime, which is exactly what the modal
rule asks for. Written as a reading rather than a named exception because naming
a third exception would invite a fourth; the test a later screen must pass is
whether the route has any other subject.

**Blur-save replaced the character page's explicit Save, and the change is
deliberate** (009 D2 → 018 D7). Plan 009 shipped the persona with a labelled
`IconDeviceFloppy` **Save**; plan 018 retired it, so the page's name and persona
now **save on focus loss** like everything else in the workspace, with a
client-side blank-name refusal and a flush of pending edits on leaving the page.
The asymmetry was real while it lasted and is now gone: one interaction model for
editing content, one for forms. `/settings` keeps its explicit Save because it is
a form, not content.

### Modal open/target flags are component-local `useState`

Never page MobX state:

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

**The same reasoning covers every later expand/collapse flag** (022 D5, D11): a
tool block's open state, a thinking block's, and a settled entry's discussion
group — including the rows that group has fetched — are component-local, with the
lifetime of the entry's mount. That is why the live-reply-to-persisted-row swap
is a remount rather than a state change (`workspace-shell.md`).

## `@mantine/form` is NOT used — the MobX draft convention

This is the **project-wide form convention** and it applies well beyond the admin
area. **`@mantine/form` is not a dependency** (plan 002). "Inherited" described
the sibling project's tree; RPHelper's frontend is greenfield and has nothing to
inherit, so the package was simply not installed. A dependency the project-wide
form convention forbids using would be a version to maintain, a line in the
lockfile, and a standing invitation for someone to reach for it.

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
  // observable fields ONLY — no methods, no computed getters
}

// derivations are PURE FREE FUNCTIONS taking the draft:
export function clientErrors(draft: CreateUserDraft): Record<string, string> { /* pure validation over the fields */ }
export function errors(draft: CreateUserDraft): Record<string, string> { /* clientErrors merged with serverErrors */ }
export function canSubmit(draft: CreateUserDraft): boolean { /* no clientErrors && submitStatus !== "submitting" */ }

// the effectful half is a FREE FUNCTION, never a method:
export async function submitCreateUser(
  draft: CreateUserDraft,
  onSaved: () => void,
  signal?: AbortSignal,
): Promise<void> { /* call the API, map errors into draft.serverErrors, then onSaved() */ }
```

Four rules, each with its reason:

1. **The draft class holds observable fields only — no methods and no computed
   getters.** `clientErrors`, `errors` and `canSubmit` are **pure free functions
   taking the draft**: `clientErrors(draft)`, `errors(draft)`, `canSubmit(draft)`.
   They stay reactive — an `observer` component reading the draft through them
   still tracks it — and the validation rules are testable by constructing a
   draft and calling a function, with no render and no network. This is
   `frontend-structure.md`'s pure-data-contract rule applied to drafts; the two
   docs used to disagree about getters and now say the same thing (plan 002).
2. **The submit is an external function `submitX(draft, ..., onSaved, signal?)`,
   never a method on the draft.** This is the repo's MobX rule — **no effectful
   class methods** — and it holds for page stores too (`frontend-structure.md`,
   which also names the submit effect's as-built shape: the in-flight guard, the
   pre-request status write, the two abort checks and the `finally`).
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

**A component writes a draft field inside `runInAction` at the input's
`onChange`** (009 D, step 007), rather than through a per-field setter exported
from the draft module. `frontend-structure.md` owns that rule for every MobX
class; it is repeated here because a form is where a reader meets it first.

**A probe-backed picker keeps the selection out of the probe's reach — by
construction** (plan 006). `admin-surfaces.md`'s failed-probe rule — a probe
failure must not disturb the existing selection — holds structurally, not by
care: the **already-enabled set arrives with the page's list payload**, which
involves no outbound call, and the probe writes only the *available* list. There
is no code path by which a probe failure can reach the selection. The two model
modals share **one picker module** for the probe, the `available ∪
already-enabled` union and the failure behaviour, and differ only in their
`*Draft.ts`. Naming the shape that cannot go wrong is more durable than warning
against the one that can.

**Draft lifetime — a fresh instance per open.** `useState(() => new XDraft(...))`
inside a **conditionally mounted** modal body, so opening the modal constructs a
draft and closing it discards one. **Not** a long-lived draft that is reset on
close: a reset function is one more thing to keep in step with the field list, and
a forgotten field is a stale value shown to the next user of the dialog.

## Mutations are never optimistic

Every mutation is followed by a **re-load** of the affected list or report.
Nothing is written into the local store in anticipation of success.

- Failures land in the page's **error field** and are rendered above the table,
  or — where the failure has no place of its own — go through
  `ui-conventions.md`'s `notifyFailure`.
- Invocations from event handlers are **`void`-ed with a non-rethrowing catch**,
  so a rejected promise becomes a rendered error rather than an unhandled
  rejection.

Optimistic updates are declined because the value they buy — hiding one round-trip
on a local-network, single-instance application — is small, while the cost is a
second source of truth for every list plus a rollback path per mutation. A
re-load also means the list reflects whatever the server actually did, including
side effects the client did not predict (a disable that also revoked sessions, a
role change the server refused).

### The narrowed re-load — a row rather than a list

The workspace narrows the *scope* of the re-load rather than skipping it, and the
rule's intent — **what renders is what the server stored** — is unchanged. As
built (013 D15, 014 D1, 015 D5):

- **Settle, re-open and partner filing re-read the affected lists.** Settle and
  re-open return ids only, so there is nothing to apply from the response.
- **An edit replaces exactly one row from the `PATCH` response** — a settled
  entry or a zone message. A full stream re-load on every blur would re-scroll
  the roleplayer away from the line they are writing
  (`workspace-shell.md`).
- **Every stream mutation failure goes through `notifyFailure` and then
  re-reads**, so a failed mutation never leaves the client's view of the stream
  diverged from the server's.
- **The apply-a-row rule, for items with concurrent writes** (015 D5): a returned
  row is applied **only if its `updated_at` is not older than the one already
  held**. A note being edited while a flag toggle is in flight is the real case —
  two writes to one row, two responses, and without the comparison the older one
  can land last and reinstate text the roleplayer has moved past.

### The one sanctioned exception — note reordering

**Note reordering on the wall is optimistic, by user decision** (016 D7, U1), and
it is the only such case in the product.

- On drop the level shows the new order **at once**.
- On failure it **reverts to the pre-drop order, applied to the level as it then
  is** — a note created meanwhile stays first, a note deleted meanwhile stays
  gone — with an inline per-level failure line ("Could not reorder the notes.").
- Further drags in that level are **disabled while the request is in flight**.

**The user's reason:** a dropped card that snaps back to its old position until
the server answers reads as broken, and a drag is a direct manipulation where the
pointer has already made the promise.

**Why it does not erode the rule.** The request carries **the whole level's
order**, the server either applies it or refuses it outright
(`memo_order_mismatch`, `session-stream.md`), and the revert is **total**. There
is no partial state to reconcile, which is the specific cost the
never-optimistic rule exists to avoid. The exception is bounded by the shape of
the request, not by care at the call site — which is why it does not generalise
to any mutation whose server half is a partial apply.

## The confirm convention

**The sibling project has no confirm pattern anywhere**: every delete and every
disable is a single unconfirmed click. RPHelper **adds one**, so this is
**designed, not inherited**.

**One shared mechanism**, used everywhere a destructive action appears: a small
confirm `Modal` — consistent with the rule that all dialogs are modals — taking
the action's title, a one-sentence consequence, a labelled confirm button
(`color="red"` for a destroy, the action's own verb otherwise), and a cancel. It
is a component, not a per-page hand-roll, so the wording shape and the button
order cannot drift between pages.

**The component is `frontend/src/shared/ConfirmModal.tsx`** (built by FEAT-003,
plan 005; first used for disabling an account). It takes the title, the
one-sentence consequence, the confirm label, an optional confirm colour and the
two callbacks. **Cancel sits left of confirm**, fixed in the component.

The actions that use it, and why each is destructive:

| Action | Feature | Consequence that earns the confirm |
|---|---|---|
| Disable an account | FEAT-003 | it **ends that user's login sessions** — someone is signed out mid-roleplay |
| Delete an LLM connection | FEAT-004 | irreversible removal of a registration and its enabled-model set |
| Clear the embedding designation | FEAT-004, US-015.AC-2 | every semantic feature stops working until a model is designated again, and re-designating requires a fresh measuring call (plan 006) |
| **A lossy `Sync`** on the drift page — **conditional** | FEAT-005, US-018.AC-3, US-018.AC-4 | the rebuild drops the columns the registry no longer declares, and their data goes with them; every surviving column's data is preserved (plan 007) |
| **Replace the whole database (import)** | FEAT-018, UC-061 | it replaces **every** row, including the administrator's own account, and signs them out (plan 031) |
| Rebuild the vector index — **not yet realized** | FEAT-005 | expensive: re-embeds every memo and session, real time and real metered LLM calls (UC-016). UC-016 is deferred to `fast/002.vector-index-rebuild` |

**The lossy-Sync confirm is conditioned on data loss, not on the action's
name.** It fires only when the row lists **at least one extra column**; a Sync
with nothing to drop applies directly.

**The database-replace confirm is red and sits inside a four-step sequence**
(plan 031): file picker → confirm → upload → redirect to `/login`. The confirm is
step 2 rather than step 1 because the administrator should know what they are
replacing *with* before being asked whether to replace; `admin-surfaces.md` holds
the page's half.

**Deliberately NOT confirmed**, so each reads as decided rather than forgotten:

- **Re-enabling an account** (plan 005) — it destroys nothing.
- **Saving an enabled-model set** (plan 006) — fully reversible, and it has no
  permissible informative consequence sentence under R5.
- **`Create` on the drift page, in any state** (plan 007) — it is provably
  incapable of dropping anything (`admin-surfaces.md`'s postconditions). The same
  shape as re-enable.
- **Archiving a character** (plan 009), **a setup** (plan 010) and **a session**
  (plan 011) — non-destructive and reversible by Restore (R6). Named one by one
  rather than "and by extension", because an "and by extension" is how one of
  three quietly grows a confirm later.
- **The three roleplayer imports** — user, character and session (plan 031).
  They are **additive** and destroy nothing: every payload row is minted a fresh
  id and nothing existing is touched (`transfer.md`, US-136). The contrast with
  the database replace above is the whole reason both are listed.

**The confirm text must not name a blast radius it is not allowed to know.** R5
forbids "N sessions use this model" (`domain-rules.md`, `admin-surfaces.md`) — the
consequence sentence describes the action, never a count derived from other users'
data.

**The line is between structure and content, not between specific and vague**
(plan 007). The drift page is the first surface where a confirm legitimately names
something. **A table name, a column name, an index's column list and a SQLite
type are administrative data** — identical on every instance, declared in
`db/schema.py`, and UC-014 is unanswerable without them — so the lossy-Sync
confirm **names the columns it will drop** (US-018.AC-3). **A row count is
content** and stays forbidden — in the confirm, in the report, in an apply
response and in a log line. Forbidden strings, beside the one above:
**"N rows will be lost"**, **"N rows will be rebuilt"**, **"rows affected"**.
The database-replace confirm obeys the same line: it names *what kind of thing*
is replaced and never how much of it (plan 031).

**Acceptance criteria now require two of these confirms** — clearing the
embedding designation (US-015.AC-2) and the lossy Sync (US-018.AC-3, US-018.AC-4).
The lossy-Sync confirm was a user decision in plan 007 before `docs/product/`
recorded it. **The others are still architectural judgement** about irreversible
and expensive operations, and a later planner may revisit them — including
dropping one whose plan argues the friction is not worth it. Stated plainly so
none is treated as a requirement it is not, nor quietly deleted as an accident.

**BookWriter is internally inconsistent here and should not be copied either
way:** its sub-agents use disable-only-with-no-delete, while its LLM servers use a
hard delete. RPHelper makes a **deliberate choice per entity**: accounts disable
and re-enable and are never deleted (FEAT-003, `data-model.md`); characters,
setups and sessions archive and are never deleted (R6); notes are **removed by
emptying them** (UC-088, US-141 — `workspace-shell.md`); LLM connections **are**
deleted, because a registration is administrative configuration with no content
hanging off it and no restore requirement anywhere in `docs/product/`.

## Page state — the same MobX convention as the app area

Identical to `frontend-structure.md`'s rule, restated because the admin pages are
its simplest instance:

```ts
class UsersPageState {
  users: UserRow[] = [];
  status: "idle" | "loading" | "ready" = "idle";
  error: string | null = null;
  constructor() { makeAutoObservable(this, {}, { autoBind: true }); }   // NO methods, NO getters
}

export async function loadUsers(state: UsersPageState, signal?: AbortSignal) { ... }
export async function disableUser(state: UsersPageState, id: string, signal?: AbortSignal) { ... }
//                                                            ^ string, never number
//                                                              (frontend-structure.md, "Ids are strings")
```

- **`makeAutoObservable` class with no methods and no computed getters.**
  Behaviour is free functions taking the state as their first argument, and so is
  every derivation — a value computed from the state is a pure function of it,
  not a getter on it. This is the same statement `frontend-structure.md`'s four
  MobX rules now make; the two are one convention.
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

**Which store a list belongs to is a scope question, and
`frontend-structure.md` answers it** — a workspace-level store when two regions
of the shell read the same rows, a section-owned store when nothing outside the
section does. The admin pages are the simple case: one page, one store.
