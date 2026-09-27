<!-- product-spec:start -->
# FEAT-007 — Setups — use cases

### UC-020 — Create a setup under a character
- **Actor:** ACT-002
- **Feature:** FEAT-007
- **Preconditions:** Character exists.
- **Main flow:**
  1. Roleplayer opens a character.
  2. Roleplayer creates a setup under it.
  3. Instance saves the setup.
  4. Setup becomes available for sessions under that character.
- **Postconditions:** Setup exists, carrying its own memos (FEAT-012) and acting as a search anchor (FEAT-015).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 2, round 3.

### UC-021 — Start a session with a setup, or with none
- **Actor:** ACT-002
- **Feature:** FEAT-007
- **Preconditions:** Character exists; a setup under it may or may not exist.
- **Main flow:**
  1. Roleplayer starts a new session under a character.
  2. Roleplayer chooses an existing setup, or chooses none.
  3. Instance starts the session accordingly.
- **Postconditions:** A session with no setup works end to end — no flow requires choosing one before an RP can start.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 3, round 6.

### UC-022 — Reuse one setup across several sessions
- **Actor:** ACT-002
- **Feature:** FEAT-007
- **Preconditions:** Setup exists under a character.
- **Main flow:**
  1. Roleplayer starts a new session under the same character.
  2. Roleplayer chooses the existing setup.
  3. Instance attaches the setup to the new session.
- **Postconditions:** Both sessions carry the setup's memos and search anchor independently of each other.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 2, round 3.

### UC-068 — Archive and restore a setup
- **Actor:** ACT-002
- **Feature:** FEAT-007
- **Preconditions:** Setup exists.
- **Main flow:**
  1. Roleplayer archives a setup.
  2. Setup leaves the working setup list.
  3. Roleplayer restores it from the archive.
  4. Setup reappears in the working list.
- **Postconditions:** An archived setup is never destroyed and is always recoverable, same rule as FEAT-006 and FEAT-008.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 10.
<!-- product-spec:end -->
