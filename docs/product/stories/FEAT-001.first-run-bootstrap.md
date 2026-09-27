<!-- product-spec:start -->
# FEAT-001 — First-run bootstrap — stories

### US-001 — Fresh instance with a first admin
- **Actor:** ACT-003 · **Feature:** FEAT-001 · **Exercises:** UC-001
- **Story:** As a first-run operator, I want to create a new database with a first administrator, so that I have a usable instance to sign into.
- **Acceptance criteria:**
  - **US-001.AC-1** — Given no database exists, when the operator chooses to create a new database and supplies the first administrator's credentials, then the instance creates the database and the administrator account.
  - **US-001.AC-2** — Given the first administrator account was just created, when bootstrap finishes, then the operator is signed in as that administrator.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### US-002 — Instance from an export
- **Actor:** ACT-003 · **Feature:** FEAT-001 · **Exercises:** UC-002
- **Story:** As a first-run operator, I want to bring up an instance from an existing database export, so that I can restore a prior instance instead of starting empty.
- **Acceptance criteria:**
  - **US-002.AC-1** — Given no database exists and the operator holds a whole-database export, when they supply it to bootstrap, then the instance restores the database, including every user and administrator it contained.
  - **US-002.AC-2** — Given the restore completed, when the operator signs in, then they can sign in as one of the restored administrators.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7, round 1, round 2.

### US-003 — Bootstrap refused once configured
- **Actor:** ACT-003 · **Feature:** FEAT-001 · **Exercises:** UC-003
- **Story:** As a first-run operator, I want bootstrap to refuse a second run once the instance is configured, so that an existing database can never be overwritten by mistake.
- **Acceptance criteria:**
  - **US-003.AC-1** — Given the instance already has a database and at least one administrator, when someone reaches the bootstrap entry point, then the instance refuses to create a new database or import an export.
  - **US-003.AC-2** — Given bootstrap was refused, when the refusal is shown, then the person is directed to sign in instead.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.
<!-- product-spec:end -->
