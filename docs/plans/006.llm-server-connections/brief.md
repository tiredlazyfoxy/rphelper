# 006.llm-server-connections — LLM server connections
<!-- roadmap:start -->
- **Stage:** 001.instance · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-004
- **Depends on:** `005.admin-shell-and-users`

## Definition
Lets the administrator tell the instance which model servers exist and which of their models may be used. A connection is registered against a base URL with its API key held as an environment-variable pointer rather than a stored secret, and a dedicated test reports reachable or not without opening a model picker. Models discovered on a server are individually enabled, and one server and model are designated for embeddings. Disabling a model that a session was configured to use produces a visible error on that session rather than a silent substitution.

## Scope
**In:**
- the `llm_servers` and `models` tables
- the registration, test, model-listing, enable/disable and embedding-designation routes
- the connection probe primitive exposed as its own typed route
- the one OpenAI-compatible client's construction and model-listing call
- secret resolution from the environment-variable pointer at call time
- the LLM Servers page
- the confirm step on deleting a connection
- the typed error a disabled-but-configured model raises

**Out:**
- streaming completions (`019`)
- the compose loop (`021`)
- embedding generation (`024`)
- how a session resolves its model (`017`)

## Open questions for the planner
- Whether a designated embedding model that is later disabled is refused at designation time, at use time, or both.
- What the probe actually calls on a llamaswap server versus an OpenAI one, given the probe is one primitive over two provider shapes.
<!-- roadmap:end -->
