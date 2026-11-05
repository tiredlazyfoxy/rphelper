# services

<!-- agent-ready:start -->

The domain layer: every business rule, ownership check and transaction lives here, so routers stay transport-only and tests can drive behaviour without HTTP.

## Glossary

**Subfolders:**
- `llm/` — the one OpenAI-compatible client (`client.py`), the neutral chat-message value type (`chat.py`) and SSE frame emission (`frames.py`) used by compose and translation.
- `search/` — hybrid search: the narrow port (`ports.py`), candidate filtering, the lexical (FTS5) and vector arms, fusion (`hybrid.py`), and the memo / session / my-search corpora built on it.
- `tools/` — the assistant's tools: the three declarations, the dispatch seam (`seam.py`) and the `memo_search`, `session_search` and `web_search` adapters.
- `web_search/` — the web search provider port (`provider.py`) and its one Google Custom Search provider.

**Files:**
- `__init__.py` — package marker.
- `auth.py` — authentication and the login-session lifecycle: authenticate, open, resolve, revoke.
- `bootstrap.py` — first-run bootstrap: the "is configured" fact and the create-first-administrator operation.
- `characters.py` — the roleplayer's characters: list, create, get, update, archive, restore.
- `compose.py` — the compose source (the tool-calling loop the SSE harness drains) and `begin_compose`.
- `configuration.py` — session configuration: the two resolver chains, the one read and the use-time model check.
- `context.py` — context assembly: what the assistant reads for one session, and in what order.
- `embedding.py` — the embedding seam: the designated model as a ready client, the sync bridge, vector rows.
- `health.py` — the readiness probe behind `GET /api/health`.
- `index_rebuild.py` — the administrator's vector-index rebuild.
- `llm_registry.py` — LLM server registrations, model enablement, the embedding designation and the connection probe.
- `memo_chain.py` — a session's memo chain (every level's notes in one read) and a note's reach.
- `memos.py` — a user's memos: create at a level, list one level, update, delete.
- `messages.py` — stream messages: read the record / zone / discussion, append, file a partner block, edit, and delete (`delete_message`: an owned zone message, or a settled entry with its buried group).
- `parens.py` — the `(( ))` parser: classify a message text and strip its instruction fragments.
- `passwords.py` — the password-hashing seam.
- `session_index.py` — the session side of the search index: composed session text, refresh, fan-out ids.
- `sessions.py` — RP sessions: start under a character, list, get, archive, restore.
- `settle.py` — settle and re-open, the only writers of the burial and settle columns.
- `setups.py` — a character's setups: list, create, get, update, archive, restore.
- `transfer.py` — export: the transfer envelope, the column-agnostic row serializer and the whole-database export.
- `transfer_import.py` — import: envelope validation, row deserialization and the owned / session / whole-database import writes.
- `translation.py` — partner-entry translation: the eligible-row read, the cache and the one model call.
- `users.py` — account management: list, create, disable, re-enable, set password, set role.

See also: docs/architecture/backend-structure.md, docs/architecture/session-stream.md, docs/architecture/search-and-retrieval.md, docs/architecture/llm-and-streaming.md

<!-- agent-ready:end -->
