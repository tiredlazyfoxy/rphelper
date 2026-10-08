<!-- product-spec:start -->
# FEAT-013 — Session configuration & inheritance — use cases

### UC-047 — Set user-level defaults
- **Actor:** ACT-002
- **Feature:** FEAT-013
- **Preconditions:** Roleplayer is authenticated.
- **Main flow:**
  1. Roleplayer opens their account defaults.
  2. Roleplayer sets the RP language and the preferred language — the only two settings at the user level.
  3. Instance saves the defaults.
- **Postconditions:** The two languages apply to every session that does not override them at the session level; model, system prompt and enabled tools have no user-level default (UC-048).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 2, round 5, round 10, round 13.

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
  2. Instance resolves the session's configuration: the MODEL is the value captured when the session was created — a character configured with a model afterwards does not change it — while the SYSTEM PROMPT and ENABLED TOOLS resolve live through `character → session`. At session creation, a character with no model configured resolves to the first enabled model, captured onto the new session.
  3. Instance resolves RP language and preferred language through `user → session`, skipping the character.
- **Alternate flows:**
  - No model is enabled anywhere on the instance when a session is created — the session is created with no model captured and creation is never refused. Nothing fills it later on its own; the roleplayer chooses a model from the session's header (UC-077, US-143).
  - No RP language or preferred language resolves at any level — the instance uses English rather than failing. English is a last resort, never a default anyone configured (US-142).
- **Postconditions:** The two chains share no level — there is no user-level default for model, system prompt or tools, and no character-level override for either language. The model/system-prompt/tools chain itself splits deliberately: the model is captured once at creation, while the system prompt and tools keep resolving live for every session, old or new.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 10, round 13, round 14; 2026-09-28, gap-closure round; finalization 2026-10-06, C43, C44.

### UC-077 — Choose the session's model from the stream's header
- **Actor:** ACT-002
- **Feature:** FEAT-013
- **Preconditions:** Session is open; at least one model is enabled (FEAT-004).
- **Main flow:**
  1. Roleplayer opens the model choice in the session's header.
  2. Roleplayer selects a model.
  3. Instance sets the session-level model override and persists it.
- **Alternate flows:**
  - No model is configured for the character or session — the header shows the first enabled model, resolved as the level's default, not a fallback.
- **Exception flows:**
  - No model is enabled at all — the roleplayer cannot send a message and is told why (US-107).
  - The session has no model captured while models are enabled on the instance — the roleplayer cannot send a message and is told no model has been chosen for this session, which is a different refusal from US-107's none-enabled one and from UC-012's disabled-model error (US-144).
- **Postconditions:** The choice is a session-level override; there is no per-turn transient override.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 11, round 14, round 15; finalization 2026-10-06, C44.
<!-- product-spec:end -->
