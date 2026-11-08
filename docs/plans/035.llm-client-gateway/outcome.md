# Outcome — 035.llm-client-gateway

## Product

## Architecture

- `docs/architecture/backend-structure.md` § Layout — mark the LLM gateway module as built and the in-house HTTP client module as removed. Reason: this plan realizes the move the revision of 2026-11-08 recorded as not yet built.
- `docs/architecture/llm-and-streaming.md` § The LLM gateway over `llm-client` and § Decision history — record the gateway as built: all four operations, client selection by connection kind, and all model traffic going through the external library. Reason: same as above.
- `docs/architecture/llm-and-streaming.md` § How one exchange runs — record that the existing chat-message-to-wire mapping is kept as the one source of the library's message history, including replayed tool pairs. Reason: the revision left open whether that mapping would survive the move, and this plan keeps it.
- `docs/architecture/session-stream.md` § The compose source — record that the compose source no longer assembles rounds, tool-call fragments or thinking markers. It drains the gateway's ordered stream and owns the per-call tool rules (start, dispatch, result or failure). Reason: the plan realizes the split between the gateway and the compose source that the revision describes.

## Decisions

- DEC-035-1 — The factory takes `kind` first; the gateway class is the production factory
- DEC-035-2 — Probe value types move to the gateway; the delta types are deleted
- DEC-035-3 — The gateway's test seam is a keyword-only map of library client classes
- DEC-035-4 — `to_wire_message` is kept and builds the library's `messages`
- DEC-035-5 — Library typing gaps are absorbed inside `gateway.py` only
- DEC-035-6 — The chat-client protocol: `complete`, `compose`, and the tool bundle
- DEC-035-7 — One unbounded queue, an end marker, and cancel-and-await on close
- DEC-035-8 — How each operation maps library failures
- DEC-035-9 — Probe builds its library client with an empty model name
- DEC-035-10 — `compose` uses the tool loop even when no tool is offered
- DEC-035-11 — Base-URL normalisation rule
- DEC-035-12 — Live tests port to the gateway, `kind` `llamaswap`

## Observations

_appended by coder / fixer / reviser; each bullet tagged [product] | [architecture] | [decision]_
