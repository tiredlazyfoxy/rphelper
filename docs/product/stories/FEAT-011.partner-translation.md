<!-- product-spec:start -->
# FEAT-011 — Partner-text translation — stories

### US-045 — First flick translates into my preferred language
- **Actor:** ACT-002 · **Feature:** FEAT-011 · **Exercises:** UC-039
- **Story:** As a roleplayer, I want to flick a partner entry to see it in my preferred language, so that I can read it comfortably without asking the assistant.
- **Acceptance criteria:**
  - **US-045.AC-1** — Given a partner entry exists in the RP language, when the roleplayer flicks it to translate, then the instance shows it translated into the roleplayer's preferred language.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 2, round 4.

### US-046 — The second flick is instant
- **Actor:** ACT-002 · **Feature:** FEAT-011 · **Exercises:** UC-041
- **Story:** As a roleplayer, I want a second look at a translation to be instant, so that flicking back and forth costs me nothing after the first time.
- **Acceptance criteria:**
  - **US-046.AC-1** — Given an entry has been translated once successfully, when the roleplayer flicks the same entry to translated again later, then the instance shows the cached translation instantly, with no new lookup.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 4.

### US-047 — A translation never enters session context
- **Actor:** ACT-002 · **Feature:** FEAT-011 · **Exercises:** UC-039
- **Story:** As a roleplayer, I want translated text to never enter session context, so that the assistant always works from the RP-language original.
- **Acceptance criteria:**
  - **US-047.AC-1** — Given a partner entry has been translated, when the assistant composes on any later turn, then the translated text is absent from what the assistant reads — session context holds only the RP-language original.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 2.

### US-048 — A failed translation shows the original with a visible error and caches nothing
- **Actor:** ACT-002 · **Feature:** FEAT-011 · **Exercises:** UC-039
- **Story:** As a roleplayer, I want a failed translation to fall back to the original with a visible error, so that I still have something to read and know it failed.
- **Acceptance criteria:**
  - **US-048.AC-1** — Given the roleplayer flicks a partner entry to translate it, when the translation fails, then the flicker shows the original RP-language text with a visible error.
  - **US-048.AC-2** — Given a translation failed, when the roleplayer flicks the same entry again, then the instance attempts the translation again rather than returning a cached result.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 9.
<!-- product-spec:end -->
