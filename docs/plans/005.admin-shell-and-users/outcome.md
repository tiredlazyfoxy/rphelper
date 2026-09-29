# Feature 005 — Admin shell and users · intended documentation changes

Written by the planner before implementation; applied by `/architect` at finalization.
Grouped by target file. The coder appends `## Observations` at the bottom.

---

## `docs/architecture/data-model.md`

### D1 — `users` gains a `last_login_at` column

- **Section:** "Accounts and instance configuration" → `users`, the column table.
- **Change:** add a row — `last_login_at` | nullable; UTC ISO-8601 text; the instant the
  account's most recent session was opened; NULL until the account logs in for the first
  time.
- **Reason:** `admin-surfaces.md`'s Users page specifies a **last login** column and no
  backing column existed; `003/001` declared `users` with exactly nine columns. Added by
  **user decision** (plan `context.md` D2). The table's own preamble authorises it: *"a
  plan may add bookkeeping columns, but not remove or re-scope one named here."* It is
  bookkeeping about an account, **not user content**, so R5 is untouched.

### D2 — The login path stamps it, and `updated_at` does not move

- **Section:** `users` (the paragraph after the column table) and/or `auth_sessions`.
- **Change:** record that `last_login_at` is written by the **open-session operation in
  `services/auth.py`**, inside the same `with conn.begin():` that inserts the
  `auth_sessions` row and with the same instant that row's `created_at` carries — so the
  first administrator, created and signed in by FEAT-001's widened bootstrap
  transaction, is stamped too. Record that **`updated_at` is deliberately not bumped by a
  login**: a column that moves on every sign-in stops meaning "the account record
  changed".
- **Reason:** the stamp site is a design decision with two rejected alternatives (the
  credential-authentication path is deliberately read-only and opens no transaction; a
  separate write from the router would break the routers-versus-services split), and it
  is a cross-feature edit to code FEAT-002 owns, so it should be visible in the schema
  doc rather than only in a plan.

### D3 — Where "revoke every session for one user" lives

- **Section:** `auth_sessions`, the linkage bullets.
- **Change:** record that the bulk revocation is a **connection-taking helper in
  `services/auth.py` that opens no transaction of its own**, called by
  `services/users.py`'s disable inside the single `with conn.begin():` that also flips
  `users.is_enabled`. It sets `revoked_at` where it is NULL, deletes nothing, is
  idempotent, and returns a count used for logging only.
- **Reason:** the doc already requires the two writes to be one transaction but does not
  say where the operation lives; a helper that opened its own block would make the
  requirement unimplementable, so the placement is load-bearing rather than
  organisational.

---

## `docs/architecture/backend-structure.md`

### B1 — Three new codes in the error table

- **Section:** "The error model" → the named-errors table.
- **Change:** add three rows.

| `code` | Raised when | `detail` carries | Realizes |
|---|---|---|---|
| `username_taken` | An account is created with a username that already exists | nothing | FEAT-003, UC-006 |
| `user_not_found` | An admin route addresses an account id that does not exist | nothing | FEAT-003, UC-007, UC-008, UC-009 |
| `self_role_change_refused` | A role change whose target is the acting administrator | nothing | FEAT-003 (no UC/US — see A4) |

  With their statuses: `username_taken` **409**, `user_not_found` **404**,
  `self_role_change_refused` **409**.
- **Reason:** `003/context.md` D15 recorded that no duplicate-username path existed yet
  and that it "arrives with FEAT-003's account management"; it arrives here. 409 for both
  conflicts rather than 403, because the caller is authenticated and authorized and 403
  is already spoken for by `insufficient_role`.

### B2 — The admin users route surface

- **Section:** Layout (the `routers/admin_users.py` and `services/users.py` lines), and
  "Authorization as router dependencies".
- **Change:** record the chosen prefix **`/api/admin/users`** and its six routes — `GET`
  (list), `POST` (create, 201), and `POST …/{user_id}/{disable|enable|password|role}` —
  each answering with an account model and none taking a query parameter. Record that
  **named action routes were chosen over one `PATCH /api/admin/users/{id}`** so that the
  disable's transaction, the self-target refusal and the password hash each hang off
  their own body and rule. Record that `/api/admin/` is the intended prefix for
  `admin_llm.py` and `admin_db.py` too.
- **Reason:** no document fixed the path, and `003/outcome.md` and `004/outcome.md` both
  set the precedent of recording a chosen route surface rather than leaving it to be
  discovered.

### B3 — `require_role` has its first consumers

- **Section:** "Authorization as router dependencies".
- **Change:** note that `require_role(Role.admin)` is now attached, **once, at router
  level**, to `routers/admin_users.py` — the first of the three `admin_*.py` routers the
  section anticipates — and that the property proved by test is that a route on that
  router declaring nothing of its own is still refused.
- **Reason:** `004/context.md` C4 records that the factory shipped with zero consumers and
  names this feature as its first; the doc should stop reading as forward-looking.

### B4 — The JSON id boundary covers path parameters

- **Section:** "The JSON id boundary — every id crosses the wire as a string".
- **Change:** add that the rule covers **path parameters** as well as request and
  response models: an id in a path is declared with the inbound annotated alias from
  `models/ids.py`, never as a bare `int` path type and never as a `str` the handler calls
  `int()` on.
- **Reason:** the section is written in terms of models, and `/api/admin/users/{user_id}`
  is the first route in the product with an id in its path. Leaving it unsaid invites a
  bare `int`, which happens to work and quietly moves the boundary out of `models/`.

---

## `docs/architecture/admin-surfaces.md`

### A1 — The "last login" column now has a backing column

- **Section:** "Users page — FEAT-003", the columns sentence.
- **Change:** note that **last login** is backed by `users.last_login_at`
  (`data-model.md`), added by this feature, nullable, and rendered as an em dash when the
  account has never logged in.
- **Reason:** the page specified a column the schema did not have; the two docs should
  agree.

### A2 — Set Password does not revoke the target's sessions

- **Section:** "Users page — FEAT-003" → **Set Password**.
- **Change:** record the decision that a reset **does not end the target's sessions**, its
  reason (no product id asks for it; UC-008 says nothing about sessions; signing someone
  out mid-roleplay is FEAT-003's *disable* behaviour) and its flip condition (a
  requirement framing a reset as a compromise response reuses the disable's revoke helper
  in the same transaction).
- **Reason:** the absence is the kind of thing a later reader reports as a bug.

### A3 — The create modal's by-status mapping is half-built, deliberately

- **Section:** "Users page — FEAT-003" → **Create modal**.
- **Change:** record that **conflict → "username taken" on the username field** is built,
  and that the **"bad request → a password-policy message on the password field"** half
  is **not**, because no password policy exists (`003`'s D16: none was invented beyond
  non-empty, enforced as a pydantic constraint answered by FastAPI's own 422). Everything
  that is not a 409 lands on the general key. Mark the password-field mapping as pending
  a password policy rather than as missing.
- **Reason:** the doc specifies a mapping whose source error does not exist; implementing
  it would require parsing prose, which the same doc forbids.

### A4 — Change Role realizes no product id

- **Section:** "Users page — FEAT-003" → **Change Role** (and the section's **Realizes:**
  line, if the architect judges it worth annotating).
- **Change:** record plainly that the role change and its self-target refusal are
  required by this document and by `data-model.md`'s `users.role` paragraph and are
  realized by **no `UC-###` or `US-###`** — FEAT-003's ids are UC-006..UC-009 and
  US-008..US-011, none of which is a role change. It was built by **user decision**.
  Record also that the UI does **not** hide the action on one's own row (the doc calls
  that cosmetic) and that the 409 refusal renders on the modal's general key.
- **Reason:** so nobody later "corrects" the citation by attaching a loose id, and so
  `/product-spec` can see the gap if it wants to close it.

### A5 — The admin header has no user menu in this feature

- **Section:** "Shell — inherited unchanged" → Header.
- **Change:** note that the header ships with the `Burger`, the title and the real
  `<a href="/">` back-to-app anchor, and **no user menu** — its contents are US-091 /
  US-092 / US-093, all specified for the `app` entry's menu and all owned by feature
  `008`. Consequence, worth stating: **there is no sign-out control in the admin area**;
  the way out is the back-to-app link. Note also that `ColorSchemeToggle` is deliberately
  **not** mounted here (user decision), leaving `008` free to place it.
- **Reason:** the doc promises a user menu; the plan deliberately does not build one, and
  an unexplained absence reads as an omission.

### A6 — The nav table declares three items and two of them land on the 404

- **Section:** "Nav is a static table plus a pure active-match function".
- **Change:** note that all three rows are declared from this feature onward, and that
  `/llm-servers` and `/database` render the 404 element until features `006` and `007`
  ship their pages — a deliberate state, not a broken link.
- **Reason:** a dead nav link is otherwise filed as a bug against this feature.

---

## `docs/architecture/frontend-structure.md`

### F1 — The admin boot sequence has five outcomes, not three

- **Section:** "The `admin` entry" → "Boot sequence — one `/api/me` round-trip before
  mount", and its diagram.
- **Change:** extend the three-branch diagram with the two `deployment.md` already
  requires: a **not-ready** branch (the not-ready predicate in `shared/notReady.ts` —
  transport failure, or a malformed body at status ≥ 500 — renders a not-ready screen,
  re-probes on a fixed 2000 ms interval and **navigates nothing**) and a **failed**
  branch (anything else thrown, including a well-formed 403 or 5xx envelope — renders a
  failure panel with a manual retry and navigates nothing). Note that the 401 branch
  performs **no navigation of its own**: the shared client has already navigated.
- **Reason:** `deployment.md` states the rule and this doc's diagram contradicts it by
  omission; the fifth outcome exists because a 403 must be treated as neither a deny nor
  a not-ready.

### F2 — Where the admin entry's modules live

- **Section:** "The `admin` entry".
- **Change:** record the entry's module set as built — the gate, the not-ready screen,
  the shell state, the nav table, the shell, the 404, the app component, the page store
  and the three drafts — all under `src/admin/` beside `main.tsx`, per `003`'s D13
  placement convention.
- **Reason:** the convention was recorded by `003` for the `bootstrap` entry; the admin
  entry is its first multi-page instance and confirms it.

---

## `docs/architecture/ui-conventions.md`

### U1 — The draft example's computed getters contradict the rule the code follows

- **Section:** "`@mantine/form` is NOT used — the MobX draft convention", the
  `CreateUserDraft` sketch and rule 1, plus the "Page state" example.
- **Change:** correct the example: a MobX data class holds **observable fields only — no
  methods and no computed getters** — and `clientErrors`, `errors` and `canSubmit` are
  **pure free functions taking the draft**, not getters. This is `002`'s D2, confirmed by
  `003`'s D13 and followed by every store and draft in features `003`, `004` and `005`.
- **Reason:** a coder reading `ui-conventions.md` alone writes getters and diverges from
  the entire codebase. The doc is the authority, so the authority should say what the code
  does. (The same section's `disableUser(state, id: string, …)` correction is already
  applied; this is the remaining half of the divergence.)

### U2 — The shared confirm component now exists

- **Section:** "NEW — the confirm convention".
- **Change:** record that the component is `frontend/src/shared/ConfirmModal.tsx`, built
  by feature `005` and first used for disabling an account; that it takes the title, the
  one-sentence consequence, the confirm label, an optional confirm colour and the two
  callbacks; and that **cancel sits left of confirm**. Note that **re-enable is not
  confirmed** (it destroys nothing), so the table's three confirmed actions stand
  unchanged.
- **Reason:** the convention says "a component, not a per-page hand-roll" without naming
  one; features `006` and `007` need to know what to reuse and where the button order is
  fixed.

---

## `docs/architecture/quick-reference.md`

### Q1 — Index the new surfaces

- **Change:** add `username_taken` (409), `user_not_found` (404) and
  `self_role_change_refused` (409) to the error-code list; add the `/api/admin/users`
  route surface; add `users.last_login_at` wherever the schema's columns are summarised.
- **Reason:** the file is the dense agent-first index and these are exactly the facts an
  agent looks up there rather than reading two long docs.

---

## Notes for the architect, not doc changes

- **A briefing premise this plan did not act on.** The briefing asked `005` to re-point
  `frontend/tests/conventions.test.ts` from asserting the *absence* of
  `makeAutoObservable` / `*Draft.ts` / page-store classes to asserting their *shape*.
  `003/004` DoD-11 already **deletes** that clause outright, on the user decision recorded
  at `003/context.md` D14 ("deleted and not replaced"; "from `003` onward the store
  convention is review-enforced, not test-enforced"). This plan honours that decision and
  adds no shape scan. If the decision is revisited, the scan is one `[test]` item plus
  that file in step `006`'s Test files.
- **`_TBD:` carried, not resolved:** `ui-conventions.md`'s no-pagination `_TBD:` (it
  assumes a small account count). This feature's Users page is the first list it applies
  to and it holds comfortably; the flip condition in that doc is unchanged.
