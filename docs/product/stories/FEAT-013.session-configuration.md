<!-- product-spec:start -->
# FEAT-013 — Session configuration & inheritance — stories

### US-058 — Set user defaults
- **Actor:** ACT-002 · **Feature:** FEAT-013 · **Exercises:** UC-047
- **Story:** As a roleplayer, I want to set my user-level defaults, so that every character and session I create starts from them.
- **Acceptance criteria:**
  - **US-058.AC-1** — Given the roleplayer is authenticated, when they set default model, system prompt, enabled tools, RP language and preferred language, then the instance saves the defaults.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 2, round 5, round 10.

### US-059 — Character overrides user for model/prompt/tools
- **Actor:** ACT-002 · **Feature:** FEAT-013 · **Exercises:** UC-048
- **Story:** As a roleplayer, I want to override model, system prompt or tools at the character level, so that a character can differ from my general defaults.
- **Acceptance criteria:**
  - **US-059.AC-1** — Given a character has no override set, when a session under it resolves configuration, then it uses the user-level model, system prompt and tools.
  - **US-059.AC-2** — Given the roleplayer overrides model, system prompt or enabled tools at the character level, when a session under that character resolves configuration, then it uses the character-level override instead of the user default.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, round 10.

### US-060 — Session overrides character
- **Actor:** ACT-002 · **Feature:** FEAT-013 · **Exercises:** UC-049
- **Story:** As a roleplayer, I want to override model, system prompt or tools at the session level, so that a single session can differ from its character.
- **Acceptance criteria:**
  - **US-060.AC-1** — Given a session overrides model, system prompt or enabled tools, when the session's configuration resolves, then the session-level override takes precedence over the character and user levels.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 2, round 5, round 10.

### US-061 — RP language and preferred language are two independent settings inheriting user → session, skipping character
- **Actor:** ACT-002 · **Feature:** FEAT-013 · **Exercises:** UC-050
- **Story:** As a roleplayer, I want the RP language and preferred language to inherit straight from my user default to a session, skipping the character level, so that language never gets tangled with a character's model/prompt/tool overrides.
- **Acceptance criteria:**
  - **US-061.AC-1** — Given the roleplayer has not set a session-level RP language or preferred language, when the session resolves configuration, then both languages inherit directly from the user-level default, skipping the character level.
  - **US-061.AC-2** — Given the roleplayer sets an RP language or preferred language override at the session level, when the session resolves configuration, then the session-level override takes precedence over the user default.
  - **US-061.AC-3** — Given a character's configuration screen, when the roleplayer looks for an RP-language or preferred-language override there, then no such override exists to set.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 2, round 10.

### US-062 — Tool switches follow the model/prompt chain
- **Actor:** ACT-002 · **Feature:** FEAT-013 · **Exercises:** UC-048
- **Story:** As a roleplayer, I want tool switches to inherit through the same chain as model and system prompt, so that enabling or disabling a tool behaves consistently with the rest of my configuration.
- **Acceptance criteria:**
  - **US-062.AC-1** — Given the roleplayer sets an enabled-tools override at the character level, when a session under that character with no session-level tools override resolves configuration, then it uses the character-level tool switches.
  - **US-062.AC-2** — Given the roleplayer sets an enabled-tools override at the session level, when that session resolves configuration, then the session-level tool switches take precedence over the character and user levels.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, round 10.
<!-- product-spec:end -->
