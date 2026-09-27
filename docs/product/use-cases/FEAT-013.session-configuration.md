<!-- product-spec:start -->
# FEAT-013 — Session configuration & inheritance — use cases

### UC-047 — Set user-level defaults
- **Actor:** ACT-002
- **Feature:** FEAT-013
- **Preconditions:** Roleplayer is authenticated.
- **Main flow:**
  1. Roleplayer opens their account defaults.
  2. Roleplayer sets default model, system prompt, enabled tools, RP language, and preferred language.
  3. Instance saves the defaults.
- **Postconditions:** Defaults apply to every character and session that does not override them.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 2, round 5, round 10.

### UC-048 — Override at character level
- **Actor:** ACT-002
- **Feature:** FEAT-013
- **Preconditions:** Character exists.
- **Main flow:**
  1. Roleplayer opens a character's configuration.
  2. Roleplayer overrides model, system prompt, or enabled tools for that character.
  3. Instance saves the override.
- **Postconditions:** RP language and preferred language are not offered here — they inherit `user → session`, skipping the character level (UC-050).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, round 10.

### UC-049 — Override at session level
- **Actor:** ACT-002
- **Feature:** FEAT-013
- **Preconditions:** Session exists.
- **Main flow:**
  1. Roleplayer opens a session's configuration.
  2. Roleplayer overrides model, system prompt, enabled tools, RP language, or preferred language for that session.
  3. Instance saves the override.
- **Postconditions:** Session-level override takes precedence over every level above it.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 2, round 5, round 10.

### UC-050 — Resolve the effective configuration for a session
- **Actor:** ACT-002
- **Feature:** FEAT-013
- **Preconditions:** Session is open.
- **Main flow:**
  1. Roleplayer opens a session.
  2. Instance resolves model, system prompt and enabled tools through `user → character → session`.
  3. Instance resolves RP language and preferred language through `user → session`, skipping the character.
- **Postconditions:** The two chains genuinely differ — a character-level language override does not exist and is never consulted.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 10.
<!-- product-spec:end -->
