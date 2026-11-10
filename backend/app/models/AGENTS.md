# models

<!-- agent-ready:start -->

Pydantic request and response models — the wire contract of every router, and the only layer that converts ids between `int` and decimal strings.

## Glossary

**Files:**
- `__init__.py` — package marker (documents the id-conversion rule).
- `admin_db.py` — the `/api/admin/database` response models.
- `admin_llm.py` — the `/api/admin/llm-servers` request and response models.
- `admin_users.py` — the `/api/admin/users` request and response models.
- `auth.py` — the login request and `/api/me` response models.
- `bootstrap.py` — the `POST /api/bootstrap/create` request and response models.
- `characters.py` — the `/api/characters` request and response models.
- `configuration.py` — the configuration request and response models (models list, settings, resolved configuration).
- `health.py` — the `/api/health` response model and its permitted-value types.
- `ids.py` — the JSON id boundary: the one place an id crosses between `int` and string.
- `memos.py` — the memo and memo-chain request and response models.
- `search.py` — my-search's grouped response models.
- `secret_ref.py` — the write-time half of the `"$ENV_VAR"` secret-pointer pattern.
- `sessions.py` — the RP-session request and response models.
- `setups.py` — the setups request and response models.
- `stream.py` — the stream request and response models (messages, zone, discussion, compose, settle / re-open, edit, and `DeleteMessageResponse`).
- `transfer.py` — the two roleplayer import response models.
- `translation.py` — the translate route's response model.

See also: docs/architecture/backend-structure.md

<!-- agent-ready:end -->

## Conventions

- Request models ignore unknown body keys (`ConfigDict(extra="ignore")`); the one named exception is the session rename body, which uses `extra="forbid"` so an unexpected key is a 422 (DEC-034-2).
