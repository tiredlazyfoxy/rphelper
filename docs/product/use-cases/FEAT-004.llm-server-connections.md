<!-- product-spec:start -->
# FEAT-004 — LLM server connections — use cases

### UC-010 — Register a server connection (llamaswap or OpenAI)
- **Actor:** ACT-001
- **Feature:** FEAT-004
- **Preconditions:** Administrator is authenticated.
- **Main flow:**
  1. Administrator opens server connection management.
  2. Administrator chooses the connection kind — llamaswap or OpenAI — and supplies its details.
  3. Instance saves the connection.
  4. Connection appears in the list of registered connections.
- **Postconditions:** Connection registered, available to test (UC-011) and to expose models (UC-012).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 7.

### UC-011 — Test a connection
- **Actor:** ACT-001
- **Feature:** FEAT-004
- **Preconditions:** A connection is registered.
- **Main flow:**
  1. Administrator selects a registered connection.
  2. Administrator requests a test.
  3. Instance reports the connection reachable.
- **Alternate flows:**
  - Connection unreachable — instance reports the failure; connection stays registered for retry.
- **Postconditions:** Reachability outcome shown; registration unaffected either way. The product commits to reachable / unreachable only — no richer result taxonomy is required; a finer distinction is a design choice, not a requirement.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 7; 2026-09-28, gap-closure round.

### UC-012 — Enable and disable specific models
- **Actor:** ACT-001
- **Feature:** FEAT-004
- **Preconditions:** A connection is registered and exposes models.
- **Main flow:**
  1. Administrator opens the model list for a connection.
  2. Administrator enables one or more models.
  3. Enabled models become selectable when configuring a session (FEAT-013).
- **Alternate flows:**
  - Administrator disables a previously enabled model — the model stops being selectable for new configuration.
- **Exception flows:**
  - Administrator disables a model that a session's resolved configuration (FEAT-013) depends on — the disable proceeds regardless; it is never refused on account of sessions depending on the model, since refusing would require telling the administrator about other users' sessions, which FEAT-019 forbids. There is no silent fallback up the `character → session` chain — the session never quietly changes model. UC-050 owns resolution and states that the model has no user level at all. The next time that session tries to use the model, it shows an error; the roleplayer resolves it by choosing another model through FEAT-013's chain.
- **Postconditions:** Enabled models are selectable; disabled models are not. A session whose resolved model has been disabled shows an error on use, never a silent substitution.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 7, round 11; finalization 2026-10-06, C42.

### UC-013 — Designate the embedding server and model
- **Actor:** ACT-001
- **Feature:** FEAT-004
- **Preconditions:** A connection is registered and exposes a usable model.
- **Main flow:**
  1. Administrator opens embedding configuration.
  2. Administrator designates which registered connection and model serve as the embedding model.
  3. Instance saves the designation.
- **Alternate flows:**
  - Administrator clears the designation after a confirm step — no embedding model is designated; the semantic tools (FEAT-014, FEAT-015) cannot work until one is designated again.
- **Exception flows:**
  - The chosen model cannot produce an embedding — the designation is refused with an error and the previous state is kept.
- **Postconditions:** The designated model is the one the assistant's semantic tools (FEAT-014, FEAT-015) rely on. Changing the designation neither forces nor prompts a rebuild — existing vectors were produced by the superseded model and are not comparable, and nothing indicates this; the remedy is UC-016, always available.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 7; 2026-09-28, gap-closure round; finalization 2026-10-01, C32, C33.
<!-- product-spec:end -->
