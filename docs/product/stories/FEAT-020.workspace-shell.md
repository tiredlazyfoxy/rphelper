<!-- product-spec:start -->
# FEAT-020 — Workspace shell & navigation — stories

### US-088 — The tree lists characters with their sessions
- **Actor:** ACT-002 · **Feature:** FEAT-020 · **Exercises:** UC-069
- **Story:** As a roleplayer, I want the left column to list my characters with their sessions, so that I can navigate straight to any of them.
- **Acceptance criteria:**
  - **US-088.AC-1** — Given a session has a setup, when the roleplayer views the tree, then that session's row shows the setup as a label.
  - **US-088.AC-2** — Given a session has no setup, when the roleplayer views the tree, then that session's row shows nothing where the label would be.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 12, round 13.

### US-089 — Sessions in the tree are ordered by last use
- **Actor:** ACT-002 · **Feature:** FEAT-020 · **Exercises:** UC-069
- **Story:** As a roleplayer, I want a character's sessions ordered by last use in the tree, so that the one I was just working on is easy to find.
- **Acceptance criteria:**
  - **US-089.AC-1** — Given a character has more than one session, when the roleplayer views its sessions in the tree, then they are ordered by last use, most recent first.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 12, round 13.

### US-090 — Collapsing the left column leaves search, create and the user menu reachable
- **Actor:** ACT-002 · **Feature:** FEAT-020 · **Exercises:** UC-070
- **Story:** As a roleplayer, I want search, create and my user menu to stay reachable when I collapse the left column, so that collapsing it costs me nothing.
- **Acceptance criteria:**
  - **US-090.AC-1** — Given the left column is collapsed to an icon rail, when the roleplayer looks at the rail, then search, create and the user menu are each reachable from it.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 14, round 15.

### US-091 — The user menu logs the roleplayer out
- **Actor:** ACT-002 · **Feature:** FEAT-020 · **Exercises:** UC-071
- **Story:** As a roleplayer, I want to log out from the user menu, so that I can end my session from anywhere in the app.
- **Acceptance criteria:**
  - **US-091.AC-1** — Given the roleplayer opens the user menu, when they choose logout, then their session ends and they return to login.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 13.

### US-092 — The user menu's settings screen carries the two languages and the user's own notes
- **Actor:** ACT-002 · **Feature:** FEAT-020 · **Exercises:** UC-071
- **Story:** As a roleplayer, I want my languages and my user-level notes together in one settings screen, so that I don't have to hunt for account-wide configuration.
- **Acceptance criteria:**
  - **US-092.AC-1** — Given the roleplayer opens the user menu's settings screen, when it renders, then it shows the RP language and preferred language settings and the roleplayer's user-level notes.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 13.

### US-093 — The admin entry point appears in the user menu only for ACT-001
- **Actor:** ACT-001 · **Feature:** FEAT-020 · **Exercises:** UC-071
- **Story:** As an administrator, I want an admin entry point in my user menu, so that I can reach administration without it cluttering every roleplayer's menu.
- **Acceptance criteria:**
  - **US-093.AC-1** — Given the user is an administrator, when they open the user menu, then an admin entry point is shown.
  - **US-093.AC-2** — Given the user is a roleplayer, not an administrator, when they open the user menu, then no admin entry point is shown.
- **Source:** `[confirmed: user]` original feature request — user menu:
  logout, settings (languages + notes), admin link if admin.

### US-094 — The note wall opens over the stream and can be pinned; the pin survives a reload
- **Actor:** ACT-002 · **Feature:** FEAT-020 · **Exercises:** UC-072
- **Story:** As a roleplayer, I want to pin the note wall open, so that it doesn't keep closing while I work.
- **Acceptance criteria:**
  - **US-094.AC-1** — Given a session is open, when the roleplayer opens the note wall, then it appears over the stream.
  - **US-094.AC-2** — Given the roleplayer pins the note wall, when they reload the page, then the wall is still pinned open.
  - **US-094.AC-3** — Given a pinned note wall on a window too narrow to hold its column, when the roleplayer dismisses the wall, then it closes and the pin is kept.
  - **US-094.AC-4** — Given the pin was kept while the window was too narrow, when the window widens past the threshold, then the wall is shown as a pinned column again.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 14; finalization 2026-10-06, C50.

### US-095 — With no session open, the note wall is not shown at all
- **Actor:** ACT-002 · **Feature:** FEAT-020 · **Exercises:** UC-072
- **Story:** As a roleplayer, I want the note wall absent when no session is open, so that I'm not shown controls for notes that have nowhere to attach.
- **Acceptance criteria:**
  - **US-095.AC-1** — Given no session is open, when the roleplayer views the workspace, then the note wall is absent — not empty, not disabled, not present at all.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 14.

### US-096 — A character's page shows its persona, its notes, its setups, its configuration and its sessions in one place
- **Actor:** ACT-002 · **Feature:** FEAT-020 · **Exercises:** UC-073
- **Story:** As a roleplayer, I want everything about a character on one page, so that I don't navigate between screens to manage it.
- **Acceptance criteria:**
  - **US-096.AC-1** — Given a character exists, when the roleplayer opens its page, then its persona, its notes, its setups, its configuration and its sessions are all shown on that one page.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 13.

### US-097 — Creating a character opens a draft page; nothing is persisted until the roleplayer enters something
- **Actor:** ACT-002 · **Feature:** FEAT-020 · **Exercises:** UC-074
- **Story:** As a roleplayer, I want character creation to open a draft I can walk away from, so that starting creation doesn't litter my character list with empty characters.
- **Acceptance criteria:**
  - **US-097.AC-1** — Given the roleplayer opens character creation, when the draft page opens with nothing entered, then no character is persisted yet.
  - **US-097.AC-2** — Given the draft page is open, when the roleplayer enters something real, then the character exists and appears in the character list.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 14.
<!-- product-spec:end -->
