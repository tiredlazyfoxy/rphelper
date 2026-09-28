<!-- product-spec:start -->
# FEAT-013 — Session configuration & inheritance — stories

### US-058 — Set user defaults
- **Actor:** ACT-002 · **Feature:** FEAT-013 · **Exercises:** UC-047
- **Story:** As a roleplayer, I want to set my user-level language defaults, so that every session I create starts from them.
- **Acceptance criteria:**
  - **US-058.AC-1** — Given the roleplayer is authenticated, when they set a default RP language and preferred language, then the instance saves the defaults.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 2, round 5, round 10, round 13.

### US-059 — Character-level model, system prompt and tool settings apply to its sessions
- **Actor:** ACT-002 · **Feature:** FEAT-013 · **Exercises:** UC-048
- **Story:** As a roleplayer, I want to override model, system prompt or tools at the character level, so that a character can differ from other characters of mine.
- **Acceptance criteria:**
  - **US-059.AC-1** — Given a character has no override set, when a session is created under it, then no character-level value is applied to model, system prompt or tools for that session (the resulting model default is US-106); the model this captures at creation does not change afterwards, while the character's system prompt and tools keep resolving live.
  - **US-059.AC-2** — Given the roleplayer overrides model, system prompt or enabled tools at the character level, when a session under that character resolves configuration, then it uses the character-level override.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, round 10, round 13, round 14; 2026-09-28, gap-closure round, challenge C25, challenge C26.

### US-060 — Session overrides character
- **Actor:** ACT-002 · **Feature:** FEAT-013 · **Exercises:** UC-049
- **Story:** As a roleplayer, I want to override model, system prompt or tools at the session level, so that a single session can differ from its character.
- **Acceptance criteria:**
  - **US-060.AC-1** — Given a session overrides model, system prompt or enabled tools, when the session's configuration resolves, then the session-level override takes precedence over the character level.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 2, round 5, round 10, round 13.

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
  - **US-062.AC-2** — Given the roleplayer sets an enabled-tools override at the session level, when that session resolves configuration, then the session-level tool switches take precedence over the character level.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, round 10, round 13.

### US-105 — Choosing a model in the header sets the session's override and it persists
- **Actor:** ACT-002 · **Feature:** FEAT-013 · **Exercises:** UC-077
- **Story:** As a roleplayer, I want to change the model right from the session's header, so that I don't have to leave the stream to switch models.
- **Acceptance criteria:**
  - **US-105.AC-1** — Given a session is open, when the roleplayer chooses a model from the header, then the instance sets it as the session-level model override.
  - **US-105.AC-2** — Given the roleplayer chose a model from the header, when they reopen the session later, then that model is still the resolved model.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 11, round 14, round 15.

### US-106 — A character with no model configured resolves to the first enabled model
- **Actor:** ACT-002 · **Feature:** FEAT-013 · **Exercises:** UC-077, UC-050
- **Story:** As a roleplayer, I want a brand-new character to have a usable model by default, so that I can start composing without configuring anything first.
- **Acceptance criteria:**
  - **US-106.AC-1** — Given a character has no model override and no session-level override exists either, when its session resolves configuration, then the resolved model is the first enabled model.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 14.

### US-107 — With no enabled model at all, the roleplayer cannot send a message and is told why
- **Actor:** ACT-002 · **Feature:** FEAT-013 · **Exercises:** UC-077
- **Story:** As a roleplayer, I want to be told plainly when no model is enabled, so that I understand why I can't send anything rather than guessing.
- **Acceptance criteria:**
  - **US-107.AC-1** — Given no model is enabled anywhere on the instance, when the roleplayer tries to send a message, then the instance refuses to send it.
  - **US-107.AC-2** — Given the send was refused for lack of an enabled model, when the roleplayer sees the refusal, then it states that refusal is because no model is enabled.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 15.

### US-108 — Model, system prompt and tool switches inherit character → session; the two languages inherit user → session
- **Actor:** ACT-002 · **Feature:** FEAT-013 · **Exercises:** UC-050
- **Story:** As a roleplayer, I want the two inheritance chains stated plainly, so that I know which level to change to affect what.
- **Acceptance criteria:**
  - **US-108.AC-1** — Given a session with no model, system prompt or tools override, when it resolves configuration, then it uses the character-level value for each, or the first enabled model if the character has none.
  - **US-108.AC-2** — Given a session with no RP-language or preferred-language override, when it resolves configuration, then it uses the user-level default for each, never a character-level value.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 13, round 14.

### US-139 — Configuring a character's model does not reach existing sessions
- **Actor:** ACT-002 · **Feature:** FEAT-013 · **Exercises:** UC-050
- **Story:** As a roleplayer, I want a character's model change to leave my existing sessions alone, so that a session I'm mid-way through never switches models under me.
- **Acceptance criteria:**
  - **US-139.AC-1** — Given a session was created while its character had no model configured, when the character is afterwards configured with a model, then the session keeps the model it captured at creation.
  - **US-139.AC-2** — Given the same character, when a new session is created under it, then that session captures the character's configured model.
- **Source:** `[confirmed: user]` interview 2026-09-28, gap-closure round, challenge C25, challenge C26.
<!-- product-spec:end -->
