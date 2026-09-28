<!-- product-spec:start -->
# Actors

### ACT-001 — Administrator
- **One-line:** Stands the instance up and keeps it running; can never read
  another user's content.
- **Goal:** Bootstrap an instance, manage user accounts, connect LLM
  servers, keep the database healthy, move or restore data by export/import.
- **Context:** Acts through administrative surfaces once authenticated.
- **Constraints:** Never sees another user's characters, sessions, setups or
  memos — no viewer, no search, no rendering; even the whole-database export
  is opaque to them.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 2,
  round 7.

### ACT-002 — Roleplayer
- **One-line:** Composes their own RP replies in the RP language with
  assistance; owns every character, setup, session and memo.
- **Goal:** Compose their own side of a roleplay — with translation of the
  partner's text, standing memory, and search — without re-explaining
  context every reply.
- **Context:** Roleplays on external sites and Discord; pastes the
  partner's text in and copies the finished answer out.
- **Constraints:** Never sees another user's content; the assistant never
  writes the partner's side for them.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 1,
  round 3.

### ACT-003 — First-run operator
- **One-line:** Faces an unconfigured instance with no database and no
  users.
- **Goal:** Get a usable instance running — create a new database with a
  first admin, or import an existing database export.
- **Context:** Acts before any user or database exists; becomes `ACT-001` on
  success.
- **Constraints:** Only available while the instance is unconfigured.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### ACT-004 — Composition assistant
- **One-line:** Non-human. Helps compose the roleplayer's own answer inside
  a compose discussion.
- **Goal:** Produce candidate replies in the RP language, and reach material
  the roleplayer did not hand it directly, through three tools.
- **Context:** Consumes forced memos and the session's RP-language entries;
  never acts outside a session the roleplayer opened.
- **Constraints:** Reaches anything else only through `memo_search`,
  `session_search` and `web_search`; nothing reaches the session record
  without the roleplayer settling it.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 9.

## Non-actors

Stated explicitly so nobody adds them later:

- **The RP partner** — never touches the system. Their words arrive only as
  text the roleplayer pastes in. `[confirmed: user]` interview 2026-09-27,
  round 1.
- **The external RP platform** (Discord, RP sites) — no integration exists;
  the boundary is the clipboard. `[confirmed: user]` interview 2026-09-27,
  round 1.
<!-- product-spec:end -->
