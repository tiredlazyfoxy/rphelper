# llm

<!-- agent-ready:start -->

The LLM layer: the gateway that is the one module knowing the `llm-client` library, the neutral chat-message value type, and SSE frame emission used by compose and translation.

## Glossary

**Files:**
- `__init__.py` — package marker; holds no logic.
- `chat.py` — the neutral chat-message value type (`ChatMessage`, `ToolCall`, `to_wire_message`) the context assembler returns and the gateway consumes, plus think-block stripping (`strip_think`).
- `frames.py` — SSE frame values, the one encoder `encode_frame`, and the SSE harness that drains a compose or translation source.
- `gateway.py` — `LlmGateway` (the production client factory, selected per server `kind`): `probe`, `embed`, `complete` and `compose`; the compose-stream values `ComposeText` and `ComposeTools`; the probe values `ProbeOutcome`, `ProbeResult` and `EMBED_NO_VECTOR_REASON`.

See also: docs/architecture/llm-and-streaming.md §The LLM gateway over `llm-client`, docs/architecture/llm-and-streaming.md §The SSE event protocol, docs/architecture/llm-and-streaming.md §The tool-calling loop, DEC-arch-llm-client-library-1..12, DEC-035-1..12

<!-- agent-ready:end -->
