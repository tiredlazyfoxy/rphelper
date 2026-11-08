# routers

<!-- agent-ready:start -->

The HTTP transport layer: each module maps `/api/...` routes onto service calls and wire models, with auth / role guards, and holds no business logic.

## Glossary

**Files:**
- `__init__.py` — package marker.
- `admin_db.py` — `/api/admin/database`: schema drift report and remediation, export / import and index rebuild; administrator-guarded.
- `admin_llm.py` — `/api/admin/llm-servers`: the LLM registry's transport layer; administrator-guarded.
- `admin_users.py` — `/api/admin/users`: account management's transport layer; administrator-guarded.
- `auth.py` — `/api/auth/login`, `/api/auth/logout` and `/api/me`.
- `bootstrap.py` — `/api/bootstrap`: first-run create-administrator and restore-from-export; guarded to the unconfigured instance.
- `characters.py` — `/api/characters`: the roleplayer's characters.
- `configuration.py` — `/api/models`, `/api/me/settings` and the session / character configuration routes.
- `health.py` — `GET /api/health`, the readiness probe.
- `memos.py` — `/api/memos...` and `/api/sessions/{session_id}/memo-chain`.
- `search.py` — `GET /api/search`, my-search's one route.
- `sessions.py` — `/api/sessions...` and `/api/characters/{character_id}/sessions`.
- `setups.py` — `/api/characters/{character_id}/setups` and `/api/setups/...`.
- `stream.py` — the session stream: entries, zone, discussion, compose, settle, re-open, and `/api/messages/{message_id}` edit and delete.
- `transfer.py` — the roleplayer's export and import routes.
- `translation.py` — `POST /api/messages/{message_id}/translation`, the partner-entry translate route.

See also: docs/architecture/backend-structure.md

<!-- agent-ready:end -->
