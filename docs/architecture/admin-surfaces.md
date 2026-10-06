# Admin surfaces

**Realizes:** FEAT-003, FEAT-004, FEAT-005, FEAT-018, FEAT-019,
FEAT-020 (the admin entry point only), ACT-001,
UC-002, UC-006, UC-007, UC-008, UC-009, UC-010, UC-011, UC-012, UC-013, UC-014,
UC-015, UC-016, UC-061, UC-065, UC-066, UC-071, UC-087, US-077

The `admin` Vite entry in full: its routes, its shell, its access gate, and the
three pages ACT-001 works in. Entry-level build reasoning is in
`frontend-structure.md`; the shared table/modal/form conventions this doc leans
on are in `ui-conventions.md`; every backend route named here obeys
`backend-structure.md`'s router/service split.

Most of what follows is **inherited** from the sibling project (BookWriter) and
is recorded so a page is built the same way twice. Where RPHelper **deviates**,
the deviation is marked and the reason is given — the admin gate in particular is
a genuine architectural difference, not a port.

---

## Scope — three pages and a 404

| Route | Page | Realizes |
|---|---|---|
| `/` | Users | FEAT-003 |
| `/llm-servers` | LLM Servers | FEAT-004 |
| `/database` | Database | FEAT-005, plus FEAT-018's whole-database granularity |
| `*` | Not found | — |

Routes are relative to the entry's `basename="/admin"`, so `/llm-servers` is
served at `/admin/llm-servers` (`deployment.md`'s per-entry nginx fallback).

**Deliberately dropped from the inherited set.** BookWriter's admin area also has
an `AssistantModesPage` and a `SubAgentsPage`. Both are authoring-domain
surfaces — they configure a book-writing assistant's modes and its sub-agent
roster — and RPHelper has **no analogue**: ACT-004's reach is fixed at exactly
three tools (R9 in `domain-rules.md`), and a "mode" is not a concept anywhere in
`docs/product/`. They are named here as **deliberately dropped** so that nobody
re-adds them by pattern-matching against the sibling project.

Two of their *patterns* are worth remembering in case a later requirement needs
them, which is the only reason they are mentioned at all:

- the **"no create, edit-only, fixed seeded rows"** list variant — a table whose
  row set is fixed by a seed and where the only action is edit;
- a **generic pick-from-a-catalogue multi-select** widget — probe a catalogue,
  render checkboxes over it, save the selected subset. The LLM Servers models
  modal below is an instance of the same shape.

Neither is built now. No requirement asks for either.

---

## How ACT-001 gets here

**Realizes:** FEAT-020 (the admin entry point only), UC-071, US-093

The way in is one item in the app's **user menu, bottom-left** (UC-071, US-093).
Two of its properties belong to this doc, because they are properties of *the
entry* rather than of the menu:

- **It is a cross-entry document navigation to `/admin` — a real
  `<a href="/admin">`, never in-entry routing.** `/admin` is its own Vite entry and
  its own document; `frontend-structure.md` states the client-side half and why no
  router can route to it. The HttpOnly session cookie travels with the navigation,
  so this entry needs no auth handoff of its own.
- **For a non-admin the item is absent, not disabled** (US-093.AC-2) — the
  roleplayer's document does not name this area at all, which is the frontend half
  of the separate-bundle posture. It changes only what is *offered*; the boundary
  is the pre-mount gate below and, authoritatively, `require_role`.

The menu itself is `workspace-shell.md`'s.

---

## Shell — inherited unchanged

A separate Vite entry: `admin/index.html` → `src/admin/main.tsx`
(`frontend-structure.md`). Inside it, `BrowserRouter basename="/admin"` and a
Mantine **`AppShell`**, configured:

```tsx
<AppShell
  header={{ height: 56 }}
  navbar={{ width: 220, breakpoint: "sm", collapsed: { mobile: !navbarOpened } }}
>
```

- **`padding` is omitted deliberately.** Each page supplies its own
  `Container size="lg" py="md"`, so a page controls its own measure. A shell-level
  padding plus a page-level container produces two nested gutters and a
  content column nobody intended.
- **No `aside`.** The admin area has no three-column workspace; that geometry
  belongs to `/sessions/:id` only (`workspace-shell.md`).

**`AppShell` now lives here and only here — a deliberate asymmetry, not drift.**
The app entry's workspace moved to a **hand-written CSS grid**
(`workspace-shell.md`), so the two entries no longer share a shell, and
`frontend-structure.md`'s earlier claim that this entry uses "the same Mantine
`AppShell` as the app area" was false and has been corrected there. Each side kept
what fits it: the admin area *is* a fixed navbar plus a main region, which is what
`AppShell` models; the workspace left because its wall is a floating overlay in
one mode and a real grid column in the other, and the collapse rail re-points a
single custom property — neither survives `AppShell`'s navbar/main/aside
computation. Recorded so nobody harmonises the two entries in either direction.

**Header.** On mobile, a `Burger` bound to the shell state; then a
`Title order={4}`. On the right, a **real `<a href="/">`** back-to-app link. The
plain anchor is deliberate and is *not* a router `Link`: the app area is a
**different document** (`frontend-structure.md`), so a router link would be wrong
anyway — and an anchor is what makes middle-click and ctrl-click open a new tab,
which is exactly how an administrator flips between the admin area and their own
app view.

**No user menu, as built by FEAT-003 (plan 005).** This header used to promise
one. Its contents are US-091 / US-092 / US-093, all specified for the `app`
entry's menu and all owned by feature `008`. The consequence is worth stating
plainly: **there is no sign-out control in the admin area** — the way out is the
back-to-app link. **`ColorSchemeToggle` is deliberately not mounted here** (user
decision), leaving `008` free to place it.

**No breadcrumbs.** Three flat pages, each one click from the navbar; a
breadcrumb trail would always be one segment long.

**Flat `<Routes>`.** Four route elements, no nested layout route and no
`<Outlet/>`. The shell is rendered once above the `<Routes>` rather than as a
parent route. With three sibling pages and no per-page layout variation, a layout
route buys nothing and costs a level of indirection when reading where a page
mounts.

### Shell state is a MobX class, not `useDisclosure`

```tsx
class AdminShellState {
  navbarOpened = false;
  constructor() { makeAutoObservable(this, {}, { autoBind: true }); }
}
const [shell] = useState(() => new AdminShellState());
```

Mantine's `useDisclosure` would be the obvious choice and is **not** used.
**Convention, recorded because it is project-wide and not obvious:** custom hooks
must not hold reactive state in this codebase. State lives in MobX observable
classes instantiated with `useState(() => new X())` and passed explicitly as
props (`frontend-structure.md`). A hook holding state hides both its lifetime and
its identity, and mixing two state mechanisms in one tree means a reader cannot
tell from a component's props what makes it re-render.

### Nav is a static table plus a pure active-match function

The navbar is a **static declaration table** mapped to Mantine `NavLink`s:

| Item | Path | Icon | `exact` |
|---|---|---|---|
| Users | `/` | `IconUsers` | yes |
| LLM Servers | `/llm-servers` | `IconServer2` | no |
| Database | `/database` | `IconDatabase` | no |

**All three rows have been declared since FEAT-003 (plan 005).** `/llm-servers`
and `/database` rendered the 404 element until features `006` and `007` shipped
their pages — a deliberate interim state, not a broken link. Both pages now exist.

Active state comes from a **pure** function, not from react-router:

```
isNavItemActive(pathname: string, item: NavItem) -> boolean
```

It matches on `/`-delimited path segments so a descendant route highlights its
parent item, and honours an `exact` flag for the root item (otherwise `/` matches
everything). Deliberately **not** react-router's `end` prop: a pure function of
two plain arguments is unit-testable with no router, no DOM and no render, which
is precisely what the pipeline's test-coder can write against from the spec alone
(`docs/plans/CLAUDE.md`). Every `/`-prefix matcher gets the `/database` vs
`/database-backups` case wrong the first time; the point of extracting it is that
the wrong answer is a failing test rather than a mis-highlighted link nobody
files.

---

## The admin gate — RPHelper deviates

This is the one place where the inherited design **cannot** be copied.

### What BookWriter does

Its admin entry decodes a **JWT client-side, before `createRoot`**:

| Condition | Action |
|---|---|
| no token | redirect `/login/` |
| token present but undecodable | redirect `/login/` |
| `role !== "admin"` | redirect `/` — **without clearing tokens** |

The third case not clearing the token is deliberate there: the session is
perfectly valid for the non-admin application, so signing the user out would be a
punishment for visiting the wrong URL. The valuable property of the whole
arrangement is that **a non-admin never mounts the admin bundle** — there is no
flash of admin chrome before the redirect.

### Why RPHelper cannot do that, for two independent reasons

1. **The session is an HttpOnly `SameSite=Lax` cookie** (FEAT-002,
   `overview.md`). JavaScript cannot read it, so there is no token to decode and
   no client-side claim to inspect.
2. **FEAT-003 requires that disabling an account ends that user's sessions**, and
   a stateless JWT cannot be revoked before it expires — you can only wait it
   out. That is the same reason `auth_sessions` exists as a server-side table
   (`data-model.md`), and it is a *product* requirement, not a consequence of the
   cookie choice. Even if the session were a readable token, RPHelper would still
   need server-side session rows, and therefore a server round-trip to know
   whether a session is still live.

Both reasons are recorded because the first alone reads like a reversible
implementation preference and the second does not.

### What RPHelper does instead

`src/admin/main.tsx` **awaits `GET /api/me`** before mounting, then mounts or
redirects. One round-trip before mount, rendering nothing at all in the meantime
— which preserves BookWriter's "no flash of admin content" property, at the cost
of a blank document for the duration of one request.

The **pure/impure split is kept**, now asynchronous:

```
resolveAdminAccess(currentUser: CurrentUser | null) -> AdminAccessDecision   // pure
enforceAdminAccess(): Promise<AdminAccessDecision>                            // impure
```

`resolveAdminAccess` is a total function over the fetched identity and returns a
decision; `enforceAdminAccess` performs the fetch and navigates on deny. The
split survives the change to async for the same reason it existed: the decision
table is testable without a network, a router or a DOM, and the navigation is a
one-line effect with nothing to get wrong.

The same three deny cases, mapped onto cookie-session semantics:

| BookWriter | RPHelper | Action |
|---|---|---|
| no token | **no session** — `/api/me` answers 401 | redirect `/login` |
| token undecodable | **session but no resolvable user** — the account is gone or disabled | redirect `/login` |
| `role !== "admin"` | **role is not `admin`** | redirect `/` (app area) |

The second case is where the two designs genuinely differ in *behaviour*, not
just mechanism: a revoked or disabled account fails here at the server, which is
the FEAT-003 guarantee working as specified. A JWT holder would have sailed past
it.

A `401` already triggers a document navigation to `/login` in the shared API
client (`frontend-structure.md`), so the gate's no-session branch is that
existing behaviour rather than a second redirect path.

### Backend gating is independent and authoritative

The frontend gate is **UX only**. The real boundary is a FastAPI dependency
factory on **every** admin route:

```
require_role(min_role: Role) -> Callable[..., CurrentUser]
```

It resolves the caller from the session cookie and compares their role against a
**numeric ladder**:

```
{ roleplayer: 0, admin: 1 }
```

`roleplayer` is ACT-002, `admin` is ACT-001. This **replaces** BookWriter's
`{author, admin}` ladder — the low rung is renamed to RPHelper's actor, not
re-purposed. A numeric ladder rather than a set of boolean flags because the
comparison a route wants to express is "at least this much", and a ladder makes
adding a rung a one-line change instead of an audit of every route's flag
conjunction.

Two things must stay true, and both are stated as constraints rather than left to
care:

- **Frontend routing is never the authorization.** Removing the gate must change
  nothing but the flash; every admin endpoint refuses a `roleplayer` on its own.
- **R5 applies to every route behind `require_role(admin)`**: an admin route
  exposes no user content — no character, setup, session, entry or memo, and no
  count derived from them (FEAT-019, UC-065, UC-066).

### Two properties of this entry are now proved rather than intended (plan 032)

- **The `admin` entry's own files call only `/api/admin/`, `/api/me`,
  `/api/auth/` and `/api/health`** — and that is **Vitest-enforced**, not a
  convention. It is the frontend half of the separate-bundle posture: the
  roleplayer's document does not name the admin area, and the admin document does
  not reach a roleplayer route. A test rather than a review rule because the
  tempting addition is small and plausible — one call to
  `GET /api/characters` to make a page "more useful" — and R5's boundary is
  exactly what it would cross.
- **Admin responses are invariant under user content**: the admin surfaces answer
  identically before and after roleplayer material exists, and a test asserts it.
  That is the positive form of "no count derived from user content" — not "we
  looked and found no counts", but "creating content changes nothing an
  administrator can see". It is the strongest statement available about an
  absence, which is why R5 names it as its own enforcement point
  (`domain-rules.md`).

`require_role(Role.admin)` is what `backend-structure.md`'s authorization table
previously called `require_admin`; see that doc for how it sits alongside
`require_unconfigured` and `require_user`.

---

## Users page — FEAT-003

**Realizes:** FEAT-003, FEAT-019, UC-006, UC-007, UC-008, UC-009, UC-066,
UC-087, US-010.AC-3, US-140

A table of accounts. Columns: **username**, **role** (badge), **last login**,
**active**. Row overflow menu (`IconDots`, `ui-conventions.md`): Set Password,
Change Role, Disable, **Re-enable**. A header **Create user** button.

**Last login** is backed by **`users.last_login_at`** (`data-model.md`), added by
FEAT-003 (plan 005) because this column was specified with no backing column. It
is nullable and renders as an **em dash** when the account has never logged in.

**Create modal.** Fields: username, password, password confirmation, role
select. Client validation: username required, password at or above a minimum
length, confirmation must match. Server errors are mapped **by status**, never by
parsing a message, which keeps the UI from breaking when the backend's prose
changes. **As built (plan 005) the mapping is half-built, deliberately:**

- **Built:** a conflict (`username_taken`, 409) becomes "username taken" on the
  username field.
- **Pending a password policy, not missing:** "a bad request becomes a
  password-policy message on the password field". No password policy exists —
  none was invented beyond non-empty (plan 003), enforced as a pydantic
  constraint and answered by FastAPI's own 422 — so there is no source error to
  map, and implementing the mapping would require parsing prose.
- **Everything that is not a 409 lands on the general key.**

**Set Password.** An administrator-initiated reset: **no current password is
required**, and the new password travels as plaintext in the request body to the
admin endpoint. There is **no email flow and no reset link** — the product has no
mail transport and `docs/product/` asks for none. Recorded explicitly so the
absence is not read as a missing feature.

**A reset does not end the target's sessions** — **US-010.AC-3** requires the
user's live sessions to stay active. Plan 005 first took this as a design
decision (signing someone out mid-roleplay is the *disable*'s behaviour, not the
reset's); `docs/product/` has since made it a requirement. **Flip condition:** a
product change to US-010 — for example a reset framed as a compromise response —
would reuse the disable's revoke helper (`data-model.md`'s `auth_sessions`) in the
same transaction.

**Change Role** (UC-087, US-140). A `Select` over the ladder. The **backend
refuses a self-targeted role change** with `self_role_change_refused` (409,
US-140.AC-2) — an administrator cannot demote themselves, which is what keeps an
instance from ending up with zero administrators through a single mis-click. The
check belongs on the server. **The UI does not hide the action on one's own row**
— hiding it would be cosmetic — and the 409 renders on the modal's **general
key**. The new role takes effect on the target's next request without a new
login (US-140.AC-3), because `require_user` reads the role live
(`backend-structure.md`). This action used to be recorded as realizing no product
id; UC-087 / US-140 now specify it.

**DEVIATION — re-enable must be added.** BookWriter's admin API has
`disableUser` and **no `enableUser`, and no delete at all**. FEAT-003 explicitly
requires disable **and re-enable**. So this is a case of
**required-by-spec-and-absent-from-the-inherited-pattern**: the endpoint, the row
action and its test do not exist upstream and must be written. `users.is_enabled`
is already a flag rather than a deletion for exactly this reason
(`data-model.md`).

**Disabling must also terminate that user's login sessions.** FEAT-003's own note
requires it, and the mechanism is the `auth_sessions` table
(`data-model.md`) — the disable service revokes the user's rows in the same
transaction as the flag flip. This is the requirement that made a server-side
session table necessary and that rules out the JWT gate above; it is cross-
referenced in both places so neither can be simplified in isolation.

Disabling an account is **destructive in effect** (it signs the person out mid-
roleplay), so it takes the confirm step below.

**Per R5 / FEAT-019 / UC-066:** this page shows **accounts only**. No character
count, no session count, no "last active session", no preview of anything the
user wrote. The temptation here is a helpful "3 characters, 11 sessions" column;
it is forbidden.

---

## LLM Servers page — FEAT-004

**Realizes:** FEAT-004, FEAT-019, UC-010, UC-011, UC-012, UC-013,
US-015.AC-2, US-015.AC-3, US-015.AC-4

A table of registered servers. Columns: **name**, **backend type** (badge),
**base URL**, **has API key**, **enabled-model count**, a **last-test badge**, and
the trailing action column. Row overflow menu: Edit, Select Models, Set
Embedding, Clear Embedding (conditional), Delete, **Test connection**.

**There is no "active" column and no active switch** (plan 006, user decision).
This page used to list both; `data-model.md`'s `llm_servers` declares no such
column, no UC or US asks for one, and of the two contradicting docs the page spec
was the wrong one.

The enabled-model count is a count of *models on this server*, which is
administrative data. It is not a count of anything user-owned — see the R5 note
at the end of this section.

**Server form modal.** Name, backend type `Select` (`llamaswap` | `OpenAI`,
matching `llm_servers.kind` in `data-model.md`), base URL, API key as a
`PasswordInput`. No active switch (above).

**The API-key round-trip rule — inherited, and the single easiest thing to get
wrong.** The key is **never returned by the server**. Therefore, on edit:

| Field state on submit | Meaning |
|---|---|
| left empty / untouched | **leave the stored value unchanged** |
| an explicit empty string (cleared by the user) | **clear the stored value** |
| a value | replace the stored value |

The distinction between "untouched" and "explicitly cleared" has to survive into
the request payload — typically as an omitted key versus a present empty
string — because a form that sends `""` for an untouched field silently deletes
the credential on every save.

Combine this with RPHelper's **`"$ENV_VAR"` secret-pointer pattern**
(`backend-structure.md`), which the inherited pattern does not have, and the
interaction becomes explicit: what this field holds is **a pointer, not a
secret** — the literal text `$OPENAI_API_KEY`. So

- a value not starting with `$` is **rejected on write**, and the field's
  description says so;
- "has API key" in the table means **a pointer is recorded**, not that it
  resolves — a pointer naming an absent variable fails later as
  `secret_ref_missing` at call time, by design. Reached through **Test
  connection**, it answers **500**, renders as a **failure panel** rather than a
  field error, and records nothing on the row — `backend-structure.md`'s "500
  posture", decided at the finalization of plans 001..007;
- a `PasswordInput` is still the right control even though the contents are not a
  secret, because the field sits where an operator expects to paste a key and
  masking it discourages exactly that mistake.

**Models modal (UC-012).** Probes the server's available models when it opens,
then renders a checkbox list over **`available ∪ already-enabled`** and saves the
enabled set. The union matters: a model that was enabled but is no longer offered
by the server must still be visible and still be un-checkable, otherwise the
administrator cannot see, let alone clear, a stale enablement.

**Failed-probe resilience.** A probe failure surfaces an error and **clears the
available list**, but **must not disturb the existing selection**. Stated as a
requirement because the naive implementation — set `available = []` and derive
the checkboxes from it — silently presents "nothing enabled" and saves that.
As built (plan 006) it holds **by construction**: the already-enabled set arrives
with the page's list payload, and the probe writes only the *available* list
(`ui-conventions.md`).

**Saving an enabled-model set is deliberately NOT confirmed** — it is fully
reversible, and it has no permissible informative consequence sentence under R5.

**Embedding modal (UC-013).** The same probe-on-open shape, but **single**
select: at most one model is designated across the whole table
(`models.is_embedding_designated`, `data-model.md`).

**Designation measures the dimension with one real embeddings call** (plan 006,
user decision). Designating embeds one short fixed string against the chosen
model, measures the returned vector's length and writes it to
`models.embedding_dim`. A failed or non-embedding response **blocks the
designation** with a typed error, and nothing is saved — the previous designation,
if any, stands (US-015.AC-3, US-015.AC-4). The dimension is not discoverable
from a models listing on either provider kind, which is why `LlmClient.embed`
exists in FEAT-004 rather than only in FEAT-017's feature, and the modal's copy
says so.

**Clear Embedding is confirmed** (US-015.AC-2). It is offered in the **row menu,
conditionally**, and no duplicate page-header action is built. Clearing is not a
no-op: with no designation, every semantic path fails as `no_embedding_model`
rather than substituting a model (R4), because vectors from a different model
are not comparable with the stored ones (`search-and-retrieval.md`) — and
re-designating requires a fresh measuring call. Designation is independent of
`is_enabled` (`data-model.md`'s `models`).

**DEVIATION — Test connection is its own endpoint and its own action.** See
decision 5 in `overview.md`. BookWriter tests a connection by reusing the
model-listing probe; RPHelper does not, because FEAT-004's purpose line treats
testing a connection as **its own capability** (UC-011), and overloading
model-listing conflates two concerns: "can I reach this server and authenticate"
and "what can it run". The **backend probe primitive is reused** — there is one
piece of code that talks to an OpenAI-compatible server — but it is exposed as
its **own route with its own typed result**, and surfaced in the UI as a badge or
alert **without opening the models list**. The result is recorded on
`llm_servers.last_test_at` / `last_test_ok` / `last_test_error`
(`data-model.md`), and per UC-011 registration is unaffected either way: a failed
test never blocks or removes a registration.

**Result taxonomy — a recorded design decision that deliberately exceeds the
requirement. This is no longer a `_TBD:`.**

```
reachable | unreachable | auth_failed | model_list_empty
```

The four values stand. What changed is their **status**: they were carried as an
open question because no acceptance criterion specified a taxonomy, and
`docs/product/` has now spoken. **UC-011's amended postcondition commits the
product to two outcomes only — reachable / unreachable — and states explicitly
that "a finer distinction is a design choice, not a requirement."** That is an
authorization, not a contradiction: the product fixes the floor and hands the
ceiling to design.

So the four-value taxonomy is **an authorized design proposal that exceeds the
requirement on purpose**, kept for the reason it was proposed: `auth_failed` and
`model_list_empty` are things the probe **can actually distinguish**, and
collapsing them into `unreachable` would make the UI tell an administrator with a
wrong API key to check their base URL. The two extra values map onto the
product's two: both are kinds of not-reachable, so a consumer that only
understands reachable/unreachable is never wrong, only less specific.

Two constraints survive from the `_TBD:`: the route returns a **typed value**,
never a free-text message the UI has to parse; and FEAT-004's plan could have
narrowed the set to the product's two.

**FEAT-004's plan (006) kept all four, and fixed what the doc left open:**

- **The ok mapping:** `reachable` is ok; each of the other three is not ok,
  because both extra values are kinds of not-reachable.
- **`llm_servers.last_test_error` stores the typed outcome value itself** — never
  a provider message and never prose. The **last-test badge** on the page renders
  from it.
- **The closed value set is declared once**, in `services/llm/client.py`, and
  reused by the registry, the router model and the frontend row type — so three
  layers do not each re-decide it.

**Cross-references that belong on this page, because this is where the mistakes
get made:**

- **R4.** Enabling and disabling models *here* is precisely what makes R4's
  use-time validation necessary. Disabling a model is a flag flip and is **never
  refused** on account of dependent sessions; the consequence surfaces later, in
  the affected session, as `model_not_enabled`.
- **R5.** A **`model → dependent sessions` lookup must not exist on this page**,
  in any form. The tempting string is literally
  **"Are you sure? N sessions use this model"** — and it is **forbidden**: the
  count is derived from other users' data, so rendering it is a cross-user
  disclosure (FEAT-019, UC-012, UC-065, UC-066). There is no endpoint to power
  it, and none may be added. Named here because this page — a delete/disable
  confirm dialog wanting a blast radius — is the exact site where a developer
  would add it in good faith.

---

## Database page — FEAT-005 + FEAT-018's admin half

**Realizes:** FEAT-005, FEAT-018, FEAT-019, UC-014, UC-015, UC-016, UC-061,
UC-066, US-018.AC-3..AC-7

A **per-table drift report**: one row per table, a coloured status badge, and a
summary of missing and extra columns. It is rendered from the `PRAGMA`-based
introspection of `db/drift.py` against the `db/schema.py` registry
(`data-model.md`, `backend-structure.md`) — which is why the registry is the
single introspectable source of truth and why the ORM decision below was
constrained by it.

### What the page holds, action by action

| Action | State |
|---|---|
| the drift report, per-row **Create** and **Sync** | delivered (plan 007) |
| **Export** — the whole-database export | **delivered** (plan 030) |
| **Import** — the whole-database replace | **delivered** (plan 031) |
| **Rebuild index** (UC-016 / US-019) | **not built** — `fast/002.vector-index-rebuild` |

Plan 007 shipped the report and its row actions and **nothing else**, with **no
disabled placeholder** for the other three — a control that explains nothing is
worse than an absent one. Two of the three have since arrived.

**Rebuild index is still absent.** It was deferred to `fast/002` because there
were no vectors to rebuild until stage 004 created the `vec0` tables; they exist
now (plan 024), so the remaining dependency is the plan itself. (Plan 006's
`context.md` calls UC-016 "feature `007`'s"; that cross-reference is stale —
`007`'s `brief.md` defers it to `fast/002`.) The page-level actions table further
down is the design `fast/002` builds to.

**Three statuses, fixed: in sync, missing, drifted.** Declared once in
`db/drift.py` and reused by the router model and the frontend row type. The
fourth, `seed-missing`, and the `Seed` action were looked at by FEAT-005's plan
and **declined**, for the reason the Seed `_TBD:` below gives. The `_TBD:` stays
open.

**What a row compares — the granularity is the administrator's whole signal**
(user decision, plan 007):

- **Compared:** the table's **column set**; each surviving column's **declared
  SQLite type** and **NOT NULL** flag; its **index set keyed on (column list,
  uniqueness)**, not on index name.
- **Deliberately NOT compared:** server defaults, `CHECK` constraint text and
  foreign-key clauses. SQLite stores them as raw SQL text that does not
  round-trip against a SQLAlchemy declaration, and a false `drifted` row invites a
  destructive rebuild that fixes nothing.
- **Two normalisations, without which a correct database reports drift
  forever:** the declared type is compiled **through the SQLite dialect** (so a
  `BigInteger().with_variant(Integer(), "sqlite")` matches a live `INTEGER`), and
  the indexes SQLite creates implicitly for a `UNIQUE` constraint or a `PRIMARY
  KEY` are **not** counted as live indexes.
- **The per-table report carries no row count, no byte size and no timestamp.**

**The status badge's colours:** **in sync → `green`, drifted → `yellow`, missing
→ `red`.** No document specified them before. The order matches `/api/health`'s
severity precedence (missing outranks drift — `backend-structure.md`), so the
page and the roll-up cannot disagree about which state is worse: `red` because
nothing works against a table that is not there, `yellow` because a drifted table
works, just not as declared. **The badge renders the status word as text, and
colour is redundant to it** — a colour-only status column fails
`ui-conventions.md`'s accessibility floor. The mapping is one pure helper, so the
component maps nothing.

**One recorded gap — the derived tables.** The report walks **`metadata.tables`
only**, and the `vec0` / FTS5 virtual tables live **outside `metadata`**, in
`db/search_tables.py` (plan 024, `data-model.md`). So **`memo_vec`,
`session_vec`, `memo_fts` and `message_fts` are not in the drift report at all**,
and nothing on this page reports their presence, their shape or their dimension.

**The views half of this gap is gone, because the views are.** This section used
to record two gaps and name the second as "the two SQL views (`settled_entries`,
`current_zone`)". **There are no SQL views anywhere in this schema** — plan 012
built four **named Core selectables** instead, which execute no DDL and are
therefore nothing the drift report could describe (`data-model.md`,
`backend-structure.md`). The companion warning that a Sync rename could break a
view is gone with it: no view exists to be re-parsed.

**The surviving gap has a sharper edge than the one it replaced** (024 D2). A
Sync rebuild of `memos` or `messages` is a create-copy-drop-rename, and **the
drop takes that table's FTS triggers with it**. The next ensure-on-write restores
the triggers but does **not** back-fill an already-existing FTS table — so between
the Sync and the next full rebuild, that lexical index is **stale for every row
written in between**, and the page that caused it says nothing about it.

- **The repair is `fast/002.vector-index-rebuild` rebuilding both FTS tables**,
  which makes **rebuild-after-Sync an operational step** rather than an optional
  tidy-up.
- **Why the tables are outside `metadata` in the first place:** a `vec0` table's
  dimension is measured when an administrator designates an embedding model, so no
  `Table` literal can declare it (`data-model.md`). That is a reason, not an
  oversight, which is why the gap is recorded rather than closed by moving them.
- **Ownership:** extending the report to cover virtual tables belongs to whichever
  feature first needs it; a virtual-table comparison designed against the four
  instances that now exist is at least possible, which it was not when this gap
  was first written.

### The page's full design — page-level actions, Create/Sync, scope

**The page-level actions sit in one group beside the Database title** (plan 030),
and Import and Rebuild index join that same group rather than each finding its own
corner:

| Action | Behaviour | State | Realizes |
|---|---|---|---|
| Export | download the whole-database export | delivered, plan 030 | FEAT-018, UC-061 |
| Import | file picker → confirm → upload → redirect to `/login` | delivered, plan 031 | FEAT-018, UC-002, UC-061 |
| Rebuild index | re-embed everything; reports completion | **not built** — `fast/002` | FEAT-005, UC-016 |

**Import is a four-step sequence, not a picker-and-upload** (plan 031):

1. a **file picker**;
2. a **red `ConfirmModal`** — "Replace the whole database?" — stating that
   everything is replaced **including the administrator's own account**, and that
   they will be **signed out**;
3. the upload;
4. a **redirect to `/login`**.

The redirect is not a courtesy: the import wipes `auth_sessions`, the caller's row
included, and the route answers **204 with the session cookie cleared**
(`transfer.md`). Step 2 is the confirm convention applying to the most destructive
action in the product — `ui-conventions.md` owns the wording rules — and the
realizes column carries **UC-061 alongside UC-002**, because this is the restore
half of the whole-database granularity and not only bootstrap's import.

**Failures render in their own inline red `Alert`**, separate from the drift
report's error, and **never as a notification** — including `database_not_empty`,
which is the common one (the instance already holds content, `US-077.AC-3`).
Separate from the report's error because the two are unrelated operations on one
page, and one shared error slot would have a Sync failure overwritten by an import
failure.

**`fast/002`'s response is expected to carry no count, and that is a requirement
on that plan rather than an as-built fact** (plan 032's audit question;
`fast/002` is unbuilt). UC-016 asks for completion to be reported, and R5 forbids
an administrative surface from showing **a count derived from user content** — and
a rebuild's "N rows indexed" is derived from every user's content, so it discloses
that other users have material and roughly how much. What "counts and completion
only" permits is therefore narrower than it sounds: completion, and at most counts
that are **not** derived from user content. A rebuilt-table count would qualify; a
row, memo or session count would not.

**Rebuild is always available, with no precondition beyond authentication.**
UC-016's postcondition says so in those words, and it is the remedy for **any**
embedding problem — including a changed embedding designation (UC-013), whose
stale vectors nothing else indicates or repairs (`search-and-retrieval.md`). The
button is therefore:

- **never gated on drift state** — a drifted or in-sync report does not enable or
  disable it, and the two are independent operations on this page
  (`data-model.md`: remediation fixes structure, rebuild recomputes content);
- **never gated on an embedding model being designated.** The earlier phrasing of
  this row — "fails when no embedding provider is designated" — read as a
  precondition and is corrected. **Availability and outcome are different
  things**: the action is always offered, and with no designation it **runs and
  fails** with `no_embedding_model` (R4, `search-and-retrieval.md`'s rebuild step
  1), which is a reported failure the administrator can act on rather than a
  disabled control that explains nothing.

Its report is **completion and nothing derived from user content** — no per-user
breakdown, no sample, no progress line naming a character, and no row count
(UC-066, R5; the expectation above). Rebuild is expensive and
touches every user's content, so it takes the **confirm step** below.

**Rebuild-after-restore is a normal operational step, not a repair** (plan 031).
A whole-database import **drops** `memo_vec` and `session_vec` inside its
transaction and **embeds nothing**, so immediately after a restore the vector
tables are **absent** and the restored material has no vectors. They are
re-created at the then-designated model's dimension by the next qualifying write
(ensure-on-write, `data-model.md`), and the restored material comes back into
coverage only when the rebuild runs. So an administrator who restores an export
and wants semantic search should expect to press this button — and until
`fast/002` exists, there is no button to press. The confirm
is a **designed addition required by no acceptance criterion**
(`ui-conventions.md`) and it **may stay** — a confirm is not a precondition: it
does not gate availability, it asks about an expensive action the administrator
has already chosen.

**There is no CLI alternative.** A standalone recalc-vectors script was
considered and declined: this button is the single surface, so there is one
implementation and one place the privacy rules above are enforced. The
operational consequence is recorded in `deployment.md` — the remedy requires a
running application, and is therefore unavailable exactly when the app will not
start.

**Scope discipline — do not silently expand this page.** BookWriter's report
carries **four** statuses (`ok` / `drift` / `missing` / `seed-missing`) with
per-row **Create**, **Sync** and **Seed** actions. FEAT-005 asks for three
things: per-table drift reporting (UC-014), creating missing tables (UC-015), and
rebuilding the vector index (UC-016).

**`Sync` is authorized.** It is no longer an inherited action looking for a
justification: it is **the mechanism by which RPHelper's schema changes shape at
all** (`backend-structure.md`'s Schema evolution section, `data-model.md`). The
registry in `db/schema.py` is the source of truth, there is no migration history
and no automatic upgrade at startup, so the only path from a drifted table to a
correct one is an administrator reading this page and pressing `Sync` on that
row. `Create` is its sibling and is exactly UC-015's "creating missing tables";
`Sync` covers the case UC-015 does not name — an existing table whose shape
moved. The human-in-the-loop gate is the point, not an accident of the inherited
design: a DDL rebuild of a table holding the roleplayer's own material is not
something to run silently at boot.

Both are per-row actions, as in the inherited pattern. Their executor is
`db/sync.py` — Alembic's batch operations, because SQLite cannot drop or retype
a column in place, and nothing else Alembic offers.

**Create and Sync, defined by postcondition** (plan 007). Both are **idempotent
and total** over a table's current state:

- **Create** guarantees the table exists with the declared shape and **never
  drops anything in any state** — it does nothing when the table already exists.
- **Sync** guarantees the table matches the declared shape — creating it when
  absent, rebuilding it when drifted, doing nothing when in sync.

So there is **no state precondition and no "wrong state" error code** on either
route. Sync is a superset of Create; Create exists separately because UC-015
names creating missing tables as its own thing and because **only one of the two
can lose data**. The page **offers each action only in the state it applies to —
absent rather than disabled** — and an **in-sync row renders no action trigger at
all**, rather than a menu of no-ops.

**What the administrator agrees to when pressing Sync on a drifted table.** The
execution shape is the user's own — *"create a temporal table, move data,
re-create table, move data back"* — i.e. Alembic's `batch_alter_table` in
**recreate mode**:

- **Data in every column that survives the rebuild is preserved**; only columns
  the registry no longer declares lose theirs (US-018.AC-5).
- **A lossy Sync — one that drops at least one undeclared column — names those
  columns and needs a confirm** (US-018.AC-3, US-018.AC-4); a Sync with nothing
  to drop applies directly. The confirm's wording rules are `ui-conventions.md`'s.
- **A rebuild that cannot complete completes not at all.** A failed cast or a
  nullability tightening over existing NULLs rolls the transaction back, leaves
  the table byte-for-byte as it was, leaves no `_alembic_tmp_*` table behind and
  raises `schema_apply_failed` (US-018.AC-6, US-018.AC-7). A best-effort partial
  apply is rejected because a half-rebuilt table is a worse state than a drifted
  one.
- **"A value that will not cast" is a post-copy type probe**, applied only when a
  column's type changes to an `INTEGER` / `REAL` / `NUMERIC` / `DECIMAL` /
  `BOOLEAN` declaration. `DATE` / `TIME` / `JSON` and text targets are never
  refused.
- **The failure renders as a failure panel**, not a field error:
  `schema_apply_failed` is a **500** by the shared posture in
  `backend-structure.md` ("The 500 posture") — nothing about the request was
  malformed; the instance failed to do what it offered — and its `detail` names
  the table and the operation, never the driver's message.

`_TBD: Seed alone remains unrequired. It exists in the inherited pattern —
BookWriter's fourth per-row status is seed-missing — and RPHelper has no seed
data in docs/product/ at all, so there is nothing for the action to insert. It is
recorded here as available prior art and deliberately NOT written up as a
requirement; inventing a use for it is not the architect's call. The report's
status set is correspondingly three values, not BookWriter's four. FEAT-005's
plan (007) looked and declined, for this reason; it did not resolve the question,
so it stays open here._`

**Export/import here is the whole-database granularity only.** FEAT-018's
per-user, per-character and per-session exports are **roleplayer-side** (ACT-002,
UC-062/UC-063/UC-064) and live in the `app` entry. Their full contract is no
longer deferred — it is **`transfer.md`**, which owns the envelope, the
granularity table, the id-serialization rules and the import policy for every
granularity including this one.

**The whole-database export is opaque to the administrator.** FEAT-018/UC-061
produces the one artifact that necessarily contains every user's data, and R5
keeps it compatible with FEAT-019 by offering **no viewer, no search and no
rendering** of it. This page therefore has no export preview, no export diff and
no export browser, now or later. It downloads a file and says how large it was;
it never shows what is inside. The export also carries **no credentials** — only
`"$ENV_VAR"` pointers — so a restored instance needs its environment supplied
separately (`data-model.md`, `deployment.md`).

**As built, in both directions** (plans 030, 031):

- After a successful export the page renders **a single inline size line** — "Export
  downloaded — 12.3 KB", formatted 1024-based — and **nothing else**. **No
  content, no table name, no row count, and a test asserts it.**
- An **export failure** renders in its own inline red `Alert`, separate from the
  drift report's error, and **never as a notification**.
- **The size line does not break the no-success-toast rule**, because it is
  **inline page text** rather than a notification. The rule is about transient
  success noise (`ui-conventions.md`); a byte count sitting on the page is the
  answer to "did that work and how big was it", which is the one question a
  download leaves open.
- **The import shows nothing of the file either** — no preview, no counts, no
  table list, **before or after**. The administrator chooses a file, confirms, and
  learns only that it succeeded or failed. The failure's `detail` carries a single
  `reason` token and never a table name, a column name or row content
  (`export_invalid`, `backend-structure.md`).

A byte size is the one number permitted here, and the reason it is permitted is
worth stating: it is a property of the *artifact*, not an aggregate over anybody's
content. "12.3 KB" tells an administrator the download was not empty; it does not
tell them how many users exist or what they wrote.

---

## Conventions this page set depends on

The full statements live in `ui-conventions.md`, which is the authority. The
short list, so a reader of this doc knows what shape to expect:

- **Tables** — plain Mantine `Table`, `striped highlightOnHover`. No data-table
  library, no cards.
- **Row actions** — an overflow `Menu` behind an `IconDots` `ActionIcon` in a
  trailing `w={60}` column; never inline icon buttons in the row.
- **No sorting, filtering or pagination** anywhere in the admin area. Every list
  loads and renders the full set.
- **Loading** — a centered `Loader` gated on an idle/loading status.
  **Errors** — an inline red `Text`/`Alert` above the table.
- **Create/edit is always a Mantine `Modal`** — never a drawer, never inline row
  editing, never a separate route.
- **`@mantine/form` is not used.** Every modal has a hand-rolled MobX **draft
  class** in a same-named `*Draft.ts` sibling, and the effectful submit is an
  external function, never a method.
- **No *success* toasts.** Success is implicit: the modal closes and the list
  refreshes. `@mantine/notifications` **is** a dependency now, used for transient
  **failure reasons only** and only where a failure has no in-page place to
  render — which on these three pages it always has (the inline `Alert` above the
  table, or a field error in a modal), so the admin area raises no notifications
  in practice. The rule and its boundary are `ui-conventions.md`'s.
- **Mutations are never optimistic** — re-load after every mutation.
- **Confirm step** on destructive admin actions, through the shared
  `shared/ConfirmModal.tsx`: disabling an account (FEAT-003), deleting an LLM
  connection and clearing the embedding designation (FEAT-004), a **lossy** Sync
  (FEAT-005, conditional on data loss), **the whole-database replace**
  (FEAT-018, plan 031 — the red confirm above), and rebuilding the vector index
  (FEAT-005, not yet realized). Re-enable, saving an enabled-model set, `Create`
  and the **export** are deliberately **not** confirmed — an export destroys
  nothing.
- **Page state** — one `makeAutoObservable` class with **no methods**, driven by
  free functions from a page-level `useEffect` with an `AbortController`.
