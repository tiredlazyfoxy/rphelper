# 017.session-configuration — Session configuration
<!-- roadmap:start -->
- **Stage:** 003.assistant · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-013, FEAT-020 (US-092)
- **Depends on:** `011.rp-sessions`, `006.llm-server-connections`, `009.characters`

## Definition
Decides, for any given session, which model answers, what system prompt shapes it, which tools it may reach, and which two languages are in play. Two chains resolve, and they deliberately share no level: model, system prompt and tool switches inherit character to session with no user-level default, while the RP language and the preferred language inherit user to session, skipping the character. The model is captured once when the session is created and never changes afterwards, so configuring a character's model reaches only sessions made from that point on; the system prompt and tool switches keep resolving live for every session, old or new — both asymmetries are deliberate. A character with no model configured takes the first enabled model at creation time — a default for a level never configured, never a fallback for one since disabled — and with no enabled model at all the roleplayer cannot send and is told why.

## Scope
**In:**
- the configuration columns at user, character and session level
- the captured model reference on the session
- the resolver implementing both chains and their asymmetry
- the model picker in the stream's header setting a persisting session-level override
- the first-enabled-model default at creation
- the typed error when the resolved model is disabled and when no model is enabled
- the settings screen behind the user menu carrying the two languages and the roleplayer's own notes

**Out:**
- what the resolved prompt and notes are assembled into (`020`)
- the tools themselves (`026`, `027`, `028`)
- the configuration block on the character page (`018`)

## Open questions for the planner
- Where the tool switches live as columns — one boolean per tool or a set — given R9 fixes the assistant's reach at exactly three.
- Whether changing a session's model override re-validates against the enabled set at that moment or only at use.
<!-- roadmap:end -->
