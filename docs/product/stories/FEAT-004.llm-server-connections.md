<!-- product-spec:start -->
# FEAT-004 — LLM server connections — stories

### US-012 — Register a connection
- **Actor:** ACT-001 · **Feature:** FEAT-004 · **Exercises:** UC-010
- **Story:** As an administrator, I want to register an LLM server connection, so that its models become available to the instance.
- **Acceptance criteria:**
  - **US-012.AC-1** — Given the administrator is authenticated, when they choose a connection kind (llamaswap or OpenAI) and supply its details, then the instance saves the connection.
  - **US-012.AC-2** — Given the connection was saved, when the administrator opens the connection list, then it appears there.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 7.

### US-013 — Test reports reachable or not
- **Actor:** ACT-001 · **Feature:** FEAT-004 · **Exercises:** UC-011
- **Story:** As an administrator, I want to test a registered connection, so that I know whether it is reachable before relying on it.
- **Acceptance criteria:**
  - **US-013.AC-1** — Given a connection is registered and reachable, when the administrator requests a test, then the instance reports it reachable.
  - **US-013.AC-2** — Given a connection is registered and unreachable, when the administrator requests a test, then the instance reports the failure and the connection stays registered.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 7.

### US-014 — Enabled models become selectable
- **Actor:** ACT-001 · **Feature:** FEAT-004 · **Exercises:** UC-012
- **Story:** As an administrator, I want to enable specific models on a connection, so that roleplayers can select them when configuring a session.
- **Acceptance criteria:**
  - **US-014.AC-1** — Given a connection exposes models, when the administrator enables one, then it becomes selectable when configuring a session.
  - **US-014.AC-2** — Given a model was previously enabled, when the administrator disables it, then it stops being selectable for new configuration.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 7.

### US-015 — Designate the embedding model
- **Actor:** ACT-001 · **Feature:** FEAT-004 · **Exercises:** UC-013
- **Story:** As an administrator, I want to designate which registered connection and model serve as the embedding model, so that the assistant's semantic tools have a model to rely on.
- **Acceptance criteria:**
  - **US-015.AC-1** — Given a connection exposes a usable model, when the administrator designates it as the embedding model, then the instance saves the designation.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 7.

### US-016 — Disabling a model a session is configured to use
- **Actor:** ACT-001 · **Feature:** FEAT-004 · **Exercises:** UC-012
- **Story:** As an administrator, I want to disable any model freely, so that I'm never blocked from managing models by what other users' sessions happen to depend on.
- **Acceptance criteria:**
  - **US-016.AC-1** — Given a session's resolved configuration depends on a model, when the administrator disables that model, then the disable proceeds and is never refused on account of that dependency.
  - **US-016.AC-2** — Given the model backing a session was disabled, when that session next tries to use it, then it shows an error rather than silently using a different model.
  - **US-016.AC-3** — Given a session shows the error, when the roleplayer resolves it, then they do so by choosing another model through the session's configuration chain (FEAT-013).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 7, round 11.
<!-- product-spec:end -->
