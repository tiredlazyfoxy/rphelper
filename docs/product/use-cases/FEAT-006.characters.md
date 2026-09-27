<!-- product-spec:start -->
# FEAT-006 — Characters — use cases

### UC-017 — Create a character
- **Actor:** ACT-002
- **Feature:** FEAT-006
- **Preconditions:** Roleplayer is authenticated.
- **Main flow:**
  1. Roleplayer opens character creation.
  2. Roleplayer supplies persona details — name, appearance, backstory, voice, writing style.
  3. Instance saves the character.
  4. New character appears in the roleplayer's character list.
- **Postconditions:** Character exists, available for setups (FEAT-007) and sessions (FEAT-008).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 3.

### UC-018 — Edit a character's persona
- **Actor:** ACT-002
- **Feature:** FEAT-006
- **Preconditions:** Character exists.
- **Main flow:**
  1. Roleplayer opens an existing character.
  2. Roleplayer edits persona details.
  3. Instance saves the changes.
- **Postconditions:** Later sessions under the character use the updated persona.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 3.

### UC-019 — List my characters
- **Actor:** ACT-002
- **Feature:** FEAT-006
- **Preconditions:** Roleplayer is authenticated.
- **Main flow:**
  1. Roleplayer opens the character list.
  2. Instance shows only the roleplayer's own characters.
- **Postconditions:** No other user's character is shown (FEAT-019).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 3.

### UC-067 — Archive and restore a character
- **Actor:** ACT-002
- **Feature:** FEAT-006
- **Preconditions:** Character exists.
- **Main flow:**
  1. Roleplayer archives a character.
  2. Character leaves the working character list.
  3. Roleplayer restores it from the archive.
  4. Character reappears in the working list.
- **Postconditions:** An archived character is never destroyed and is always recoverable, same rule as FEAT-007 and FEAT-008.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 10.
<!-- product-spec:end -->
