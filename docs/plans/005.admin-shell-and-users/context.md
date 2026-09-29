# Feature 005 — Admin shell and users · feature-wide context

## What this feature is

Gives ACT-001 their own area and the first page in it. The `admin` entry makes one
identity round-trip before it mounts anything, so a non-administrator never sees an
administrative frame at all; a transport failure or a 5xx on that round-trip is a
not-ready-yet state, never a deny. Inside it the administrator creates accounts,
disables and re-enables them, resets passwords and changes roles; disabling an account
ends that user's live sessions in the same transaction as the flag flip. The account
list shows accounts and nothing else.

The agreed boundary is `brief.md` in this folder — its Definition and its Scope In/Out
lists bound every step here and are **not** restated or widened. Read it first. Three
departures from it are recorded below and nowhere else: **Change Role is in scope**
(D1), **`users` gains a `last_login_at` column and the login path stamps it** (D2), and
the "revoke every session for one user" operation that `004` anticipated but did not
build **is added here** (D4).

## Product ids

`FEAT-003`, via **UC-006**, **UC-007**, **UC-008**, **UC-009** and **US-008**,
**US-009**, **US-010**, **US-011**.

| Criterion | Where it lands |
|---|---|
| US-008.AC-1 (created **enabled**) | steps `002` (the service writes the flag true), `003` (the route), `007` (the form) |
| US-008.AC-2 (it appears in the list) | steps `003` (the list payload), `007` (the list refreshes after create) |
| US-009.AC-1 (disabling ends that user's active sessions immediately) | steps `002` (one transaction), `003` (observable: the target's cookie answers 401 next request) |
| US-009.AC-2 (a disabled account's login is rejected) | step `003` |
| UC-007 alternate flow (re-enable restores login ability) | step `003` |
| US-010.AC-1 (the old password no longer works) | step `003` |
| US-010.AC-2 (login with the new one succeeds) | step `003` |
| US-011.AC-1 (identity and enabled/disabled status shown) | steps `003` (the payload), `006` (the rendered table) |
| US-011.AC-2 (no character, session, setup or memo of any account is shown) | steps `003` (no such field and no such endpoint), `006` (no such column) |

A `[test]` Definition-of-done item cites the `US-###.AC-#` it verifies wherever one
applies. Items that are structural or architectural obligations rather than product
criteria stand on their own and cite the architecture document instead, as they do in
`001`–`004`. **No id is invented to make coverage look complete.**

**Related, cited where apt but not delivered here:** UC-065 / UC-066 and FEAT-019 (R5 —
the cross-cutting privacy audit is feature `032`'s), US-093 (the user-menu entry point —
feature `008`'s), UC-010..UC-016 (features `006` and `007`).

**Change Role realizes no product id.** `docs/product/quick-reference.md` gives FEAT-003
exactly UC-006..UC-009 and US-008..US-011, and none of them is a role change. The
capability is required by `admin-surfaces.md`'s Users-page section ("Change Role … the
backend refuses a self-targeted role change") and by `data-model.md`'s `users.role`
paragraph, and it is in scope by user decision (D1). Its Definition-of-done items
therefore cite **those two documents** and say plainly that they have no product id. A
`UC-###` or `US-###` attached to a role change would be a fabrication.

## Assumption every step rests on — only `001` is built

`backend/` exists and is built through `001.backend-foundation`. `frontend/` holds only
`002/001`'s output — `package.json`, both tsconfigs, `vite.config.ts`, `tests/setup.ts`,
`.gitignore`, `node_modules/` — and **there is no `frontend/src/` yet**. Features
`002.frontend-foundation`, `003.first-run-bootstrap` and `004.authentication-session`
are **planned, not built**: their contracts live in their step files and **no
`## Skeleton` record exists for them beyond `002`'s**, so nothing they deliver is a
frozen signature this plan may quote. Build order is `001 → 002 → fast/001 → 003 → 004
→ 005`.

Therefore:

- **No step here quotes an exact signature for anything `002`, `003` or `004`
  delivers.** Borrowed interfaces are named by **role and module path** in prose — "the
  `require_role` dependency factory in `app/dependencies.py`", "the open-session
  operation in `app/services/auth.py`", "the hashing seam in `app/services/passwords.py`",
  "the not-ready predicate in `frontend/src/shared/notReady.ts`", "the document-navigation
  seam exported by `frontend/src/shared/api.ts`" — and the **skeleton agent resolves the
  exact names against the delivered code**.
- The citation for every borrowed interface is the step file that delivers it:
  `docs/plans/002.frontend-foundation/00{3,4,5,6}.*.md`,
  `docs/plans/003.first-run-bootstrap/00{1,2,4}.*.md` and
  `docs/plans/004.authentication-session/00{1,2,3}.*.md`. Where a step needs a narrow
  fact from one of those, its `<SSS>.context.md` names the file and section rather than
  restating it.
- If the delivered `002`/`003`/`004` code contradicts what a step file assumes about it,
  that is a **skeleton hand-back**, not something a coder improvises around.

## Commands

From the root `CLAUDE.md`:

```
Backend  (run from backend/)
  test       .venv/Scripts/python -m pytest
  typecheck  .venv/Scripts/python -m mypy app
  lint       .venv/Scripts/python -m ruff check .
Frontend (run from frontend/)
  build      npm run build
  test       npm test
  typecheck  npm run typecheck
```

No step may leave the tree failing `mypy app` or `tsc --noEmit`.

## Architecture this binds to

- `docs/architecture/admin-surfaces.md` — **the authority for this feature**: the route
  table, the shell and its `AppShell` configuration, the shell-state note, the nav table
  and `isNavItemActive`, the gate and its pure/impure split, "Backend gating is
  independent and authoritative", the whole Users-page section, and "Conventions this
  page set depends on".
- `docs/architecture/ui-conventions.md` — icons and the sizing table, `IconButton` and
  the table-overflow-menu boundary, tables, no sorting/filtering/pagination, loading and
  error placement, create/edit is always a `Modal`, the MobX draft convention, no success
  toasts, mutations are never optimistic, **the confirm convention**, page state.
- `docs/architecture/frontend-structure.md` — the `admin` entry section (its Vite input,
  the `basename`, flat `<Routes>`, the back-to-app anchor, the boot sequence), "Ids are
  strings", "The API client", "State — MobX 6, per-page stores, no context".
- `docs/architecture/backend-structure.md` — Layout (`routers/admin_users.py`,
  `services/users.py`), "Routers versus services", "Authorization as router
  dependencies", the JSON id boundary, the error model, `GET /api/me`, Persistence access
  (Core, explicit `begin()`).
- `docs/architecture/data-model.md` — `users` and `auth_sessions`, and Identifiers.
- `docs/architecture/domain-rules.md` — the Roles ladder section and **R5**.
- `docs/architecture/deployment.md` — the `supervisord`/502 passage and the
  **not-ready-yet gate case** (lines ~150-175).
- `docs/product/use-cases/FEAT-003.*.md`, `docs/product/stories/FEAT-003.*.md`.

Cited, never copied. Where a step needs a declaration the architecture gives verbatim
(the `AppShell` prop block, the nav table, the `users` column list, the wire shape of a
domain error), the step context points at the section and the skeleton agent reproduces
it.

## Files this feature touches

```
backend/
  app/
    db/schema.py                  # + users.last_login_at                        (001)
    services/auth.py              # + the login stamp, + bulk revoke-for-user    (001)
    errors.py                     # + username_taken, user_not_found,
                                  #   self_role_change_refused                   (002)
    services/users.py             # NEW — list/create/disable/enable/
                                  #       set-password/set-role                  (002)
    models/admin_users.py         # NEW — request/response models                (003)
    routers/admin_users.py        # NEW — the guarded router                     (003)
    main.py                       # + include the admin-users router             (003)
frontend/
  src/
    admin/adminAccess.ts          # NEW — the gate: pure decisions + enforce     (004)
    admin/AdminNotReady.tsx       # NEW — not-ready / failed, with retry         (004)
    admin/main.tsx                # placeholder route table replaced             (004, 005)
    admin/adminShellState.ts      # NEW — navbarOpened + its free functions      (005)
    admin/navItems.ts             # NEW — the static table + isNavItemActive     (005)
    admin/AdminShell.tsx          # NEW — the AppShell frame                     (005)
    admin/NotFoundPage.tsx        # NEW — the 404 route element                  (005)
    admin/AdminApp.tsx            # NEW — the shell + the flat <Routes>          (005, 006)
    shared/ConfirmModal.tsx       # NEW — the one shared confirm dialog          (006)
    admin/usersPageState.ts       # NEW — the page store + load/disable/enable   (006)
    admin/UsersPage.tsx           # NEW — the table and the row menu             (006, 007, 008)
    admin/createUserDraft.ts      # NEW — draft, validators, submit              (007)
    admin/CreateUserModal.tsx     # NEW                                          (007)
    admin/setPasswordDraft.ts     # NEW                                          (008)
    admin/SetPasswordModal.tsx    # NEW                                          (008)
    admin/changeRoleDraft.ts      # NEW                                          (008)
    admin/ChangeRoleModal.tsx     # NEW                                          (008)
```

**`frontend/src/admin/index.html` is not touched.** `002/006` creates it with lang,
charset, viewport, a title, one mount element and a module script pointing at the
sibling `main.tsx`; nothing here changes any of that, so it appears in no step's Source
files. **`frontend/src/shell.css` and `frontend/src/global.css` are not touched** — see
"Cross-cutting constraints".

**Out of scope, and a step that creates one is out of scope:** the LLM Servers page and
any `admin_llm.py` / `services/llm_registry.py` (`006`); the Database page, `db/drift.py`,
`db/sync.py`, Alembic (`007`); the user-menu item that navigates here and any user menu
in the admin header (`008`, US-091/US-093); the cross-cutting privacy audit (`032`);
account **deletion** in any form (`data-model.md`: accounts disable and re-enable and are
never deleted); a password policy, a strength meter, a forced change at next login, an
email flow or a reset link (D6); a self-service change-password path (that is the
roleplayer's own surface and no product id here asks for it); user impersonation; a
session-listing or "sign out this device" surface; sorting, filtering or pagination;
an empty-state component; any new setting; any third stylesheet.

## Cross-cutting constraints every step holds

**R5 / UC-066 / US-011.AC-2 — the Users page shows accounts and nothing else.** No
character count, no session count, no "last active session", no preview of anything a
user wrote, and **no endpoint that could power one**. `admin-surfaces.md` names the
temptation explicitly ("3 characters, 11 sessions") and forbids it. The confirm modal's
consequence sentence **describes the action, never a count derived from other users'
data**. `last_login_at` is bookkeeping about an account's own use of the login route —
not user content — and stays R5-clean (D2).

**`require_role(Role.admin)` sits on the router, not the handlers**, so a route added
later cannot forget it (`backend-structure.md`; the pattern `003/003` set with
`require_unconfigured`, whose DoD-4 proves a second route on the same router is still
refused). Step `003` carries the same proof.

**The frontend gate is UX only.** Removing it must change nothing but the flash; every
endpoint refuses a `roleplayer` on its own. Step `003` carries that as a `[test]` item.

**Routers versus services stays strict.** The router owns path, method, models,
dependencies and status code, issues **no SQL** and holds no rule; the service takes
plain arguments, returns plain results or raises a typed error, and **never imports
`fastapi`, never sees a `Request`, never knows a status code**. Direction is one-way:
`routers → services → db`. The acting administrator's id reaches `services/users.py` as
a **plain argument**, never as a `CurrentUser` the service unpacks.

**Transaction boundaries are the service's own `with conn.begin():` blocks.** `001`'s
connection dependency opens none. **Disable is one transaction**: `users.is_enabled` goes
false **and** every live `auth_sessions` row for that user is revoked, together. A
disable that flipped the flag and left sessions alive is exactly what FEAT-003 rules out
(`data-model.md`).

**The JSON id boundary.** Every id is an `int` in Python and SQLite and a **decimal
string** in every JSON body and every `detail`. Response models use `001`'s outbound
alias; request bodies and **path parameters** use the inbound one (D9). A bare `int` id
field on a model is the defect. On the frontend an id is a `string` end to end — `id:
number` on a type, prop, store field or route param is a defect, and there is no
`parseInt` and no numeric sort anywhere in this feature.

**The redaction rule** (`deployment.md`) binds every log line: ids as decimal strings,
error codes, counts, statuses — **never a password, never a hash, never a session token,
never a username**. The revoked-row count from a disable may be logged; it may not be
returned or rendered (D4).

**No DDL at startup.** `main.py`'s lifespan still runs nothing. `users.last_login_at` is
added to the `Table(...)` literal in `db/schema.py` and reaches a fresh instance through
`003`'s `create_all`; an instance bootstrapped before `005` ships has a `users` table
without the column, which is drift and is `007`'s remediation to fix, not this feature's.

**The admin area adds no stylesheet.** The project rule is exactly two hand-written
stylesheets (root `CLAUDE.md`, `frontend-structure.md`); `shell.css` is app-entry-only
and ships empty. The admin shell is **Mantine `AppShell` and Mantine props alone** — no
third `.css` file, no `.module.css`, no style block. `002/006` DoD-11's scan stays true.

**Failures render in place, so `notifyFailure` is called nowhere in this feature.** Every
failure here has a place: the inline `Alert` above the table, a field error in a modal, or
the gate's own full-page state. `002/006` DoD-12's scan — Mantine's notification API is
imported by `shared/notifyFailure.ts` alone — stays true, unchanged and untouched.

**Mutations are never optimistic.** Every mutation is followed by a re-load of the list;
nothing is written into the store in anticipation. Handler invocations are `void`-ed with
a non-rethrowing catch, so a rejection becomes a rendered error rather than an unhandled
rejection. **There are no success toasts** — the modal closing and the list refreshing is
the success signal.

**Frontend is TypeScript only.** No `.js`, `.jsx`, `.mjs` or `.cjs` is authored anywhere
under `frontend/`, and there is no linter — `tsc --noEmit` is the only static gate.

## Decisions — settled, with their reasoning

### D1 — Change Role is in scope, and it realizes no product id

**User decision.** The row action, the role-change endpoint and the **server-side refusal
of a self-targeted role change** are all built here, per `admin-surfaces.md`. FEAT-003's
use cases and stories do not cover it (see "Product ids" above), so its Definition-of-done
items cite `admin-surfaces.md`'s Users-page section and `data-model.md`'s `users.role`
paragraph and say they have no product id.

The refusal is **server-side and authoritative**. `admin-surfaces.md` allows the UI to
hide the action on one's own row and calls that cosmetic; **this plan does not hide it**,
because hiding it requires the caller's identity in the page (which the gate otherwise
discards, see D11) and buys nothing the server does not already guarantee. The refusal
renders on the modal's general key like any other unmappable server error.

### D2 — `users` gains a nullable `last_login_at`, stamped when a session is opened

**User decision.** `admin-surfaces.md` puts a "last login" column on the Users table;
`data-model.md`'s `users` has no such column and `003/001` froze the table at exactly
nine. So `005` adds a **tenth** column: `last_login_at`, **nullable**, text, UTC ISO-8601,
matching the file's `*_at` convention.

**It is stamped in the open-session operation in `backend/app/services/auth.py`, inside
the `with conn.begin():` block that already exists there.** Two reasons for that site
rather than the credential-authentication path: that path is deliberately **read-only and
opens no transaction** (`004/001`), and giving it a write would make the uniform-refusal
path a writer; and opening a session is exactly the moment a login has **succeeded**,
which is what "last login" means. A useful consequence: the first administrator, created
and signed in by `004/004`'s widened bootstrap transaction, is stamped too.

**This is a deliberate cross-feature reach into code feature `004` owns.** It is named
here so it reads as decided rather than as a stray edit, the file is listed in step
`001`'s Source files, and the edit is kept to the minimum: one `UPDATE users SET
last_login_at = <the same now the row uses>` inside the existing block, and nothing else
in that module changes. **`updated_at` is deliberately not bumped by a login** — a column
that moves on every sign-in stops meaning "the account record changed".

`last_login_at` is **bookkeeping about an account**, not user content: it is derived from
the administrated account's own use of the login route and names nothing the person
wrote. R5 is untouched.

### D3 — `services/users.py` is the home of account management; `services/auth.py` keeps `auth_sessions`

`backend-structure.md`'s Layout assigns `services/users.py` to FEAT-003, and every
operation below lives there. The one exception is the bulk revoke (D4), which touches
`auth_sessions` and therefore stays in the module that owns that table.

Six operations, each taking a Core `Connection` as its first argument: **list**, **create**,
**disable**, **enable**, **set password**, **set role**.

### D4 — "Revoke every session for one user" is added here, as a helper in `services/auth.py` that opens no transaction

`004/001.context.md` anticipates this operation landing beside single-token revoke and
cites the `auth_sessions.user_id` index as being for exactly it — but `004` does not build
it. **`005` builds it**, and the shape is fixed by the transaction requirement:

- the helper lives in **`backend/app/services/auth.py`**, because that module owns
  `auth_sessions` and a second module writing that table would put the "who revokes" rule
  in two places;
- it **opens no transaction of its own** and takes the caller's `Connection`, because
  `data-model.md` requires the flag flip and the revocations to commit **together** and a
  helper that opened its own block would make that impossible;
- **`services/users.py`'s disable opens the single `with conn.begin():`** around both
  writes.

It sets `revoked_at` on the rows for that user where `revoked_at IS NULL`, **deletes
nothing** (a revocation must stay observable), is **idempotent**, and returns the number
of rows it revoked. That count exists for the **log line only** — it is not returned by
the route and never reaches the UI, because a count rendered beside a confirm is the
shape R5 forbids even when the count is the target's own.

### D5 — The URL surface is `/api/admin/users`, and the mutations are named action routes

No document fixes the path. The plan chooses **`/api/admin/users`**, the natural reading
of `backend-structure.md`'s `routers/admin_users.py` and the obvious sibling of
`/api/auth/login` and `/api/bootstrap/create`. It leaves `/api/admin/llm-servers` and
`/api/admin/database` free for `006` and `007` under one prefix that is also the obvious
thing to grep for "what is behind `require_role`".

| Route | Does | Answers |
|---|---|---|
| `GET /api/admin/users` | the whole list, no query parameters | 200, the list model |
| `POST /api/admin/users` | create an account, enabled | 201, the row model |
| `POST /api/admin/users/{user_id}/disable` | flip the flag **and** revoke the target's sessions | 200, the row model |
| `POST /api/admin/users/{user_id}/enable` | flip the flag back | 200, the row model |
| `POST /api/admin/users/{user_id}/password` | set a new password | 200, the row model |
| `POST /api/admin/users/{user_id}/role` | set the role, refusing a self-target | 200, the row model |

**Named action routes rather than one `PATCH /api/admin/users/{id}`.** A single partial-
update route would make "disable", "change role" and "reset password" one payload, so the
disable transaction, the self-target refusal and the password hash would all hang off
optional fields of one model — and a request that set two of them at once would have no
defined meaning. Four narrow routes each have one body, one rule and one transaction.
`GET` is the only read; **no route is keyed on anything but a user id**, which is the
mechanical form of R5's "no endpoint that could power a reverse lookup".

Every mutation answers with the **affected row model**, for `004`'s D10 reason (a route
that reports nothing about what just happened is a poorer contract for manual
verification) — never with the password, never with a token, never with a session count.

### D6 — Password reset: the administrator supplies the new password directly

**`brief.md`'s first open question, closed by `admin-surfaces.md` rather than decided
here.** Set Password is an administrator-initiated reset: **no current password is
required**, the new password travels as **plaintext in the request body** to the admin
endpoint, and there is **no email flow, no reset link and no forced change at next
login** — the product has no mail transport and `users` carries no must-change flag.
US-010's two criteria are exactly "the old password no longer works" and "login with the
new one succeeds", and nothing more is built.

**It does not revoke the target's sessions**, and that is a decision rather than an
oversight: no product id asks for it, UC-008 says nothing about sessions, and signing a
person out mid-roleplay is FEAT-003's *disable* behaviour, not its password behaviour.
Flip condition: if a requirement ever frames a reset as a compromise response, it reuses
D4's helper in the same transaction as the hash write — a two-line change at one site.

**No password policy is invented** (`003/context.md` D16 stands): the only server-side
rule is non-empty, expressed as a pydantic field constraint and answered by FastAPI's own
**422**, adding no domain error code. See D10 for what that means for the create modal's
by-status error mapping.

### D7 — The confirm modal is a shared component, built here

**`brief.md`'s second open question, closed by `ui-conventions.md` rather than decided
here.** That document requires **one shared mechanism**, "a component, not a per-page
hand-roll, so the wording shape and the button order cannot drift between pages". It is
built at **`frontend/src/shared/ConfirmModal.tsx`**, first used for disabling an account,
and `006` and `007` reuse it for deleting an LLM connection and rebuilding the vector
index.

It takes the action's title, a one-sentence consequence, a confirm label, an optional
confirm colour (red for a destroy, the action's own verb otherwise), and cancel/confirm
callbacks. **Cancel sits left of confirm** — fixing the order is half the reason the
component is shared.

**Only disable is confirmed.** `ui-conventions.md`'s table lists exactly three confirmed
actions and re-enable is not one of them: restoring access destroys nothing. Create and
Set Password are forms in their own modals and are not additionally confirmed.

### D8 — `ColorSchemeToggle` is **not** mounted here

**User decision.** `002` ships `frontend/src/shared/ColorSchemeToggle.tsx` exported and
mounted nowhere, naming `005` and `008` as candidate hosts (`002/context.md` seam S4).
The user chose to leave it unmounted: it does **not** go in the admin header. Recorded so
nobody re-adds it later as an oversight, and so `008` still finds it free to place.

### D9 — Path ids use the inbound snowflake alias

`backend-structure.md`'s JSON id boundary is written in terms of request and response
*models*; a path parameter is neither. Extending it is the only reading that keeps the
rule whole: `{user_id}` arrives as a decimal string and is declared with `001`'s
**inbound** annotated alias from `app/models/ids.py`, never as a bare `int` path type and
never as a `str` the handler calls `int()` on. `outcome.md` asks the architect to record
the extension.

### D10 — Create-modal server errors are mapped by status, and the password half of that mapping does not exist

`admin-surfaces.md` maps create-modal server errors **by status**: a conflict becomes
"username taken" on the username field, a bad request becomes a password-policy message
on the password field. The first half is built: **409 → the username field**.

The second half **cannot be built as written and is deliberately not faked**. There is no
password policy (D6, `003`'s D16), so the backend produces no password-policy failure;
the only non-conflict refusal a well-formed submit can draw is FastAPI's 422 backstop for
an empty field, which the client already prevents and which does not say *which* field it
was without parsing prose — precisely what the convention forbids. So **everything that is
not a 409 lands on the general key** and renders above the form. `outcome.md` asks the
architect to record that the password-field mapping awaits a password policy.

### D11 — The admin header carries the back-to-app anchor and no user menu

`admin-surfaces.md`'s Shell section puts "a real `<a href="/">` back-to-app link and a
user menu" on the right of the header. The anchor is built; **the user menu is not**.
`brief.md`'s Scope In does not list one, its Out list gives the user-menu entry point to
`008`, and the menu's contents are US-091/US-092/US-093 — all of them `008`'s and all of
them specified for the **app** entry's menu (`workspace-shell.md`). Building a second,
unspecified menu here would fix a shape `008` then has to match.

Consequence, stated so it is not read as a bug: **there is no sign-out control in the
admin area** in this feature; the way out is the back-to-app anchor. `outcome.md` records
it. A further consequence is that the identity the gate fetched is used for the access
decision and then discarded — nothing in the shell renders it (see D1).

### D12 — The nav table declares all three items now; two of them land on the 404

The nav is a **static declaration table** — Users `/` `IconUsers` exact; LLM Servers
`/llm-servers` `IconServer2`; Database `/database` `IconDatabase` — mapped to Mantine
`NavLink`s (`admin-surfaces.md`). **All three are declared here**, because the nav belongs
to the shell and `006`/`007` add only their pages. Until those features land, `/llm-servers`
and `/database` render the **404** element. Said plainly so nobody reads a dead link as a
bug or "fixes" it by deleting the rows.

`isNavItemActive(pathname, item)` is a **pure function of two plain arguments**,
deliberately not react-router's `end` prop, matching on `/`-delimited segments and
honouring the `exact` flag for the root item. `admin-surfaces.md` names the case that must
not regress — **`/database` versus `/database-backups`** — and step `005` gives it a
`[test]` item even though the `/database` page itself is `007`'s.

### D13 — The gate has five outcomes, and only two of them navigate

`deployment.md` is explicit that **a 502 or a transport failure on `/api/me` is not a
deny**. The trap is that the shared client turns a real 401 into a document navigation
*and* a throw, so the gate sees a throw in the deny case and in the not-ready case alike
and must tell them apart by the thrown value, not by the fact that it threw.

| Outcome | Condition | What happens |
|---|---|---|
| **granted** | `/api/me` resolves and the role is `admin` | mount the admin application |
| **denied — no session** | 401 | the shared client has **already** navigated to `/login`; the gate renders nothing and navigates **no second time** |
| **denied — not admin** | resolves, role below `admin` | one document navigation to `/` (the app area), nothing rendered |
| **not ready** | the not-ready predicate in `shared/notReady.ts` answers true — the transport-failure code, or the malformed-body code at status ≥ 500 | render the not-ready screen and re-probe; **never** navigate |
| **failed** | any other thrown value, including a well-formed 403 or 5xx envelope | render the failure screen with the error's message and a manual retry; **never** navigate |

The fifth outcome exists because 403 must not be treated as not-ready and must not be
treated as a deny either — a gate with four outcomes has to fold it into one of them and
both choices are wrong. The shape mirrors `003/004`'s five-phase bootstrap page exactly,
which is what `deployment.md` means by "consistent with FEAT-001's handling".

**The not-ready judgement is not re-decided here.** It is `003`'s named predicate in
`frontend/src/shared/notReady.ts`, written there precisely because "`005`'s admin gate
needs the same judgement" (`003/context.md` D10). This feature imports it and defines no
code string and no status literal of its own for it.

**Nothing is rendered while `/api/me` is in flight** — not a spinner, not the shell. That
preserves the no-flash-of-admin-content property at the cost of a blank document for one
request (`admin-surfaces.md`, `frontend-structure.md`).

**Retry posture** follows `003`'s D11, and the reason is that this is the same window:
while the gate is in the not-ready state it re-probes on a **fixed 2000 ms interval**,
uncapped, with no backoff, and both the not-ready and the failed screens carry a visible
manual retry. The failed state does **not** auto-retry. The interval literal lives in this
feature's gate module; `shared/notReady.ts` is a predicate and gains no timing constant,
and a shared constant module for two call sites would be premature.

### D14 — The pure/impure split, and the navigation seam

`admin-surfaces.md` fixes the split and this plan keeps it: a **pure, total**
`resolveAdminAccess(currentUser)`-shaped decision function over the fetched identity,
unit-testable with no network, no router and no DOM, plus an impure half that fetches and
navigates. This plan adds a **second pure function** classifying a thrown value into
not-ready or failed, so that all five of D13's outcomes are decided by pure code and the
impure half only fetches, navigates and mounts.

**The deny navigation goes through the document-navigation seam `shared/api.ts` already
exports** — the same one the client's 401 path uses (`002/status.md`'s step-004 Skeleton
record) — rather than touching `window.location` directly, so it is observable in a test
exactly as the 401 path is, and so there is one place in the codebase that leaves a
document.

### D15 — Two of `002`'s guard tests, and what actually has to change

**`frontend/tests/entries.test.tsx` — the admin clauses must be repaired here.** `002/006`
DoD-1 asserts each entry "renders only its own marker" and DoD-3 asserts the admin
`basename` by observing that marker at `/admin/users`. The admin entry stops being a
marker-only placeholder in step `004`, and from step `004` it renders **nothing at all**
without a `/api/me` answer. So the admin clauses of DoD-1..DoD-4 are edited **at clause
level** in step `004` — the pattern `003` used for `test_db_schema.py` — to stub
`GET /api/me` with an administrator identity before evaluating the entry. The
`bootstrap`, `login` and `app` clauses are untouched. The marker survives as the
mechanism: from step `004` the admin entry renders a stable `data-entry="admin"` marker
inside its `BrowserRouter`, and from step `005` that marker sits on the shell, **above**
the `<Routes>`, so it is present on every admin route including the 404 and a basename
mismatch still makes it absent.

**`frontend/tests/conventions.test.ts` needs no repair here, and this contradicts the
briefing.** The briefing states that the scan still fails on any `makeAutoObservable`, any
`*Draft.ts` module and any page-store class, and asks `005` to re-point it from absence
to shape. That premise is **already false by the time `005` runs**: `003/004` DoD-11
deletes `002/006` DoD-10 outright — "the clause is deleted and **not replaced**", a user
decision recorded at `003/context.md` D14, which also states that "from `003` onward the
store convention is **review-enforced, not test-enforced**". `003` ships the first store
and the first `*Draft.ts`; `004` ships a second. Re-introducing the rule as a shape scan
here would reverse that user decision on the planner's own authority, so this plan does
**not** do it. The two clauses of that file that survive — no forbidden styling mechanism,
and Mantine's notification API imported by `shared/notifyFailure.ts` alone — stay true
throughout this feature (see the cross-cutting constraints), so no step touches the file
at all. **If the orchestrator wants the shape scan, it is one added `[test]` item plus that
file in step `006`'s Test files, and nothing else in this plan moves.**

### D16 — MobX: `002`'s D2 wins over `ui-conventions.md`'s draft example, and the conflict is called out

`ui-conventions.md`'s `CreateUserDraft` sketch shows **computed getters** — `clientErrors`,
`errors`, `canSubmit`. **`002`'s D2 is stricter and it is what the codebase does**: a MobX
data class holds **observable fields only — no methods and no computed getters** —
`makeAutoObservable(this, {}, { autoBind: true })` in the constructor, with every
derivation a **pure free function taking the data object** (`clientErrors(draft)`,
`errors(draft)`, `canSubmit(draft)`) and every effect a free function taking the object
plus an optional `AbortSignal`, which `runInAction`s its writes and **early-returns on
`signal.aborted` before writing**. `003`'s D13 confirms it and fixes the placement: state
and draft modules live **under the entry folder beside `main.tsx`**, with their derivations
and effects in the **same module** as the class.

This is recorded so a coder reading `ui-conventions.md` alone does not write getters, and
`outcome.md` asks the architect to correct the example.

Everything else in the convention stands unchanged: one store per page via
`useState(() => new XState())`, **never `useMemo`**; stores passed **explicitly as
props**, no React context; `observer` on every component that reads an observable;
**modal open/target flags are component-local `useState`**, never page MobX state; a
**fresh draft instance per open** via `useState(() => new XDraft())` inside a
**conditionally mounted** modal body, never a long-lived draft reset on close.

### D17 — Eight steps, not six

The briefing proposes six. This plan uses eight, and the three splits each have a reason:

- **the schema delta plus the two `services/auth.py` edits get their own step** (`001`),
  separate from `services/users.py` (`002`), because the cross-feature reach into code
  `004` owns (D2, D4) should be one small, wholly visible commit, and because the two
  together would push the users service over 200 lines;
- **the three modals are two steps** (`007` create, `008` set-password and change-role),
  because three drafts plus three modal components plus three row-menu wirings is well
  over 200 lines of source change, and because the create modal is the only one with a
  field-mapping contract (D10) worth verifying on its own.

Backend before frontend; each step independently verifiable.

## Vocabulary

| Term | Means here |
|---|---|
| **account** | a row in `users`; never deleted, only disabled and re-enabled |
| **session** | a row in `auth_sessions` — never the RP-domain `sessions` entity, which this feature does not touch |
| **live session** | an `auth_sessions` row that is not revoked, not past `expires_at`, and whose `users` row is enabled (`004`'s D7) |
| **the gate** | the `admin` entry's pre-mount `/api/me` round-trip and its five outcomes (D13) |
| **not-ready** | the backend is starting and cannot answer at all yet (`003`'s D10 predicate); not a deny and not a failure |
| **the ladder** | `{roleplayer: 0, admin: 1}` (`domain-rules.md`), compared as "at least this rung" |
| **the acting administrator** | the caller `require_role` resolved; reaches a service as a plain id argument |

## Step map

| Step | Subject | Depends on |
|------|---------|------------|
| 001 | `users.last_login_at`, the login stamp, and the revoke-every-session-for-one-user helper | — |
| 002 | `username_taken` / `user_not_found` / `self_role_change_refused`, and `services/users.py`'s six operations | 001 |
| 003 | `models/admin_users.py`, `routers/admin_users.py` behind router-level `require_role(Role.admin)`, registration | 001, 002 |
| 004 | the gate — the pure decisions, the impure enforce, the five outcomes, the not-ready screen, `main.tsx` | — (binds to the `/api/me` contract) |
| 005 | the shell — `AppShell`, the MobX shell state, the static nav table, `isNavItemActive`, the flat `<Routes>`, the 404 | 004 |
| 006 | `shared/ConfirmModal.tsx`, the Users page store, the table and the row menu, disable/re-enable through the confirm | 003, 005 |
| 007 | the create-user modal, its draft and the header button | 006 |
| 008 | the set-password and change-role modals and their drafts | 006 |

## Test conventions inherited

**Backend** (`001`/`003`/`004`): tests live in `backend/tests/` as `test_<module>.py`,
with test functions named **`test_<behavior>__DoD<n>`** (`004/context.md`). `conftest.py`
provides an **autouse** `isolated_settings_environment` (clears every `RPHELPER_*`
variable and calls `get_settings.cache_clear()` around each test), `db_settings` (a real
`.sqlite` **file** under `tmp_path`, never `:memory:`) and `db_engine`. **There is no
shared app or client fixture** — each test module builds its own `TestClient` and
overrides settings through `app.dependency_overrides[get_settings]`, never by mutating a
global. `005` adds no setting and no fixture convention.

**Frontend** (`002`/`003`/`004`): **Vitest** configured inside `frontend/vite.config.ts`'s
`test` block — a separate `vitest.config.*` is forbidden by `002/001` DoD-14. `environment:
"jsdom"`, **`globals: false`**, so `describe`/`it`/`expect` are explicit imports from
`"vitest"`. Tests live under **`frontend/tests/`, outside `src/`, mirroring `src/`'s
tree**, named `*.test.ts` / `*.test.tsx`; `frontend/tests/setup.ts` is harness source and
never a test file. `@testing-library/react`, `/jest-dom` and `/user-event` are available;
`fetch` is stubbed per test with no network-mocking library. A component test rendering
Mantine wraps in `shared/AppProviders`. Tests assert **rendered behaviour**, not internal
structure. `npm test` is `vitest run`.
