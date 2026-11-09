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

### DEC-035-13 — Two unlisted probe-type importers move to the gateway in step 002
- **Status:** accepted
- **Stage:** — · **Feature:** 035.llm-client-gateway · **Step:** 002
- **Date:** 2026-11-08 · **Decided by:** user
- **Question:** `app/models/admin_llm.py:39` and `tests/test_privacy_audit_logs.py:92` import `ProbeOutcome` / `ProbeResult` from `app.services.llm.client`, and no step lists them. Step 005 deletes `client.py` and requires that no app module imports it.
- **Decision:** Step 002's coder also switches the import in `backend/app/models/admin_llm.py` to `app.services.llm.gateway`. Step 002's test-coder does the same in `backend/tests/test_privacy_audit_logs.py`. Each is an import-line change only; the step's contract is unchanged.
- **Reason:** These are the same probe-type re-homing that step 002 already does for the shared fakes (DEC-035-2). Without it, step 005 would stop on its precondition.
- **Rejected:** Re-planning with /planner — a full re-plan cycle for two one-line import moves.
- **Lands in:** `backend/app/models/admin_llm.py`, `backend/tests/test_privacy_audit_logs.py`

### DEC-035-14 — Five unlisted test modules follow step 002's interface
- **Status:** accepted
- **Stage:** — · **Feature:** 035.llm-client-gateway · **Step:** 002
- **Date:** 2026-11-09 · **Decided by:** user
- **Question:** `tests/test_session_index.py:881` and `tests/test_record_keeping_embedding.py:797` define a three-argument exploding factory, and the import guards in `tests/test_memos_service.py`, `tests/test_messages_service.py` and `tests/test_settle_service.py` allow one `app.services` module each. Step 002's four-argument factory and its direct `LlmGateway` imports (002.context.md) break all five, and no step lists them.
- **Decision:** Step 002's test-coder adds `kind` as the first parameter of the two exploding factories, and lets the three import guards also accept `app.services.llm.gateway` (an approved deviation). These are mechanical edits only; no contract changes.
- **Reason:** These edits follow the plan's own rule to import `LlmGateway` directly and its four-argument factory (DEC-035-1). Re-exporting through the permitted modules would contradict 002.context.md and force a re-freeze.
- **Rejected:** Re-exporting `LlmGateway` through `embedding` / `session_index` — contradicts the plan and needs a re-freeze. Re-planning — a full cycle for mechanical test edits.
- **Lands in:** `backend/tests/test_session_index.py`, `backend/tests/test_record_keeping_embedding.py`, `backend/tests/test_memos_service.py`, `backend/tests/test_messages_service.py`, `backend/tests/test_settle_service.py`

### DEC-035-15 — Step 001 DoD-14's client-module identity check is retired with client.py
- **Status:** accepted
- **Stage:** — · **Feature:** 035.llm-client-gateway · **Step:** 001, 005
- **Date:** 2026-11-09 · **Decided by:** user
- **Question:** Step 001 DoD-14 requires `ProbeOutcome` from `app.services.llm.client` to be the gateway's object, and step 005 DoD-1 requires `client.py` not to exist. After step 005, `tests/test_llm_gateway_probe.py` cannot be collected.
- **Decision:** DoD-14's identity check through `client.py` was transitional. It is retired when step 005 deletes `client.py`. `backend/tests/test_llm_gateway_probe.py` joins step 005's Test files. Step 005's test-coder removes only the `client.py` import and the client-side identity checks, and keeps the gateway-side checks: `ProbeOutcome`'s four values, `ProbeResult`'s defaults and `EMBED_NO_VECTOR_REASON`.
- **Reason:** The identity guaranteed a safe hand-off while both modules existed; it has no meaning once one is gone. Retiring it restores DoD-4..13's coverage without touching production code.
- **Rejected:** Re-planning steps 001 and 005 with /planner — a full cycle for one transitional assertion. Keeping a `client.py` shim — contradicts step 005 DoD-1 and `DEC-arch-llm-client-library-1`.
- **Lands in:** `backend/tests/test_llm_gateway_probe.py`

## Observations

_appended by coder / fixer / reviser; each bullet tagged [product] | [architecture] | [decision]_
