# Feature 020 — Context assembly · intended documentation changes

Planner section: the doc changes the architect applies once 020 ships. Grouped by target
file. "Dn" are `context.md` decisions in this folder; U1–U4 are the user decisions it
records.

## `docs/architecture/llm-and-streaming.md`

| Section | Intended change | Reason |
|---|---|---|
| Context assembly — the `system prompt =` block | **Remove "+ tool descriptions for ENABLED tools only"** from the prompt. Enabled tools reach the model through the API's `tools` parameter, which `021` sets from 017's resolved switches; the prompt text carries no tool description | D2 (narrowing, orchestrator-scoped) |
| Context assembly — the `system prompt =` block | Record the as-built parts and order: resolved system prompt, character sheet, forced notes, then three fixed instruction sections (message tags, languages, double parentheses). **No setup description and no character name**, deliberately | D2, U2 |
| Context assembly — new subsection "Layout" | Record the section headings, the per-level note headings, the `[note]` delimiter and the instruction lead-ins (`context.md` "The prompt format"), and that tests bind to those markers, not to the instruction prose | D10 |
| Context assembly — omitted parts | Record: a null resolved system prompt omits that section (no default persona); an empty or whitespace-only sheet omits the sheet; no forced note omits the notes section; the instruction sections are always present | D5 |
| The message list is the union of the two views | Record the **kind-tag presentation**: each settled row keeps its stored role and its content is prefixed `[partner]` / `[my turn]` / `[decision]` plus a line feed; zone rows carry no tag; the prompt explains the tags; stored text is never changed (R12). Reason: partner blocks and the roleplayer's turns are both `role='user'` | D1, U1 |
| The message list is the union of the two views | Record that the union is read through 012's `list_entries` + `list_zone` and merged by id (the lists can interleave), and that **`role='tool'` rows are skipped in 020**; `021` extends the mapper with tool-row replay, because tool-call id pairing is `021`'s seam | D3, D7, U3 |
| Forced-memo selection | Record as built: selection is `resolve_chain` filtered by `memo_reach(...) == "forced"`; no hand-written conjunction exists in the assembler, and a source test pins that | D6 |
| Language handling | Record the **English fallback**: a null resolved RP language or preferred language names English in the instruction; nothing is refused | D4, U4 |
| Two facts that follow from mutability | Record that the sub-reads are separate reads, not one snapshot, and why that is accepted | D11 |
| No context compaction | Confirm as built: no pruning, summary, token count or truncation anywhere in assembly; the full record goes through | D12 |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| Layout — `services/` | Add `context.py` (context assembly: system-prompt renderer, message mapper, `assemble_context`; no router, its only caller is `compose.py` in `021`) | D9 |
| Layout — `services/llm/` | Add `chat.py` (the chat-message value type and role literal; neutral so the client imports it without the assembler) | D9 |
| Routers versus services | Record the import exception: `services/context.py` imports read operations from `sessions`, `characters`, `configuration`, `memo_chain` and `messages`. It opens no transaction of its own and calls only reads that leave none open, so the transaction-ownership reason for the no-import rule does not apply. It is a read composition, like `compose.py` | D9 |

## `docs/architecture/domain-rules.md`

| Section | Intended change | Reason |
|---|---|---|
| R3 | Name `services/context.py` as the context-assembly consumer of `memo_reach`, beside `026`'s future `memo_search` | D6 |
| R12 — the responsibility table, "System prompt" row | Point at the as-built "Double parentheses" section and its two lead-ins | D10 |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Paths | Add `services/context.py` and `services/llm/chat.py` | D9 |

## Flags for other owners

- **`021`**: call `assemble_context` for the prompt and messages; extend `ChatMessage` /
  `to_chat_messages` with tool-row replay (D3); send enabled tools via the API `tools`
  parameter (D2); call `resolve_model_for_use` itself. An empty session (no rows) yields
  an empty message list.
- **`/product-spec`**: the kind-tag presentation (U1) and the English fallback for a null
  language (U4) are plan-time user decisions with no criterion behind them. Raised so the
  product layer can record them or rule otherwise.

## Observations

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B2 (the LLM/search/operations layer — `llm-and-streaming.md`, `search-and-retrieval.md`, `deployment.md`, `admin-surfaces.md`, `overview.md`), plus three `backend-structure.md` and two `domain-rules.md` items in B3.
Rejected items: Its "tool rows are skipped in context" rule is superseded by 021 D9's replay and was not written.
Notes: Five items were orphaned by the orchestrator's batching and applied in B3, including `services/context.py`'s absence from the module tree and its missing row in the service-to-service import table. The English fallback is recorded as realizing `US-142` rather than as a plan-time choice.
