"""The table-definition registry — the single source of truth for the schema.

`docs/architecture/backend-structure.md` § Persistence access, reason 3: a Core
`MetaData` with `Table` objects **is** the declaration that `PRAGMA table_info` /
`index_list` are compared against, so `db/schema.py` stays "the single introspectable
source of truth and `db/drift.py` walks it directly".

The rule every later feature binds to, and which this module exists to state:

- **Every table in RPHelper is declared as a `Table(...)` literal in this file**, bound
  to the `metadata` object below. The stream's named read selectables (`settled_entries`,
  `current_zone`, `message_states`) live here too: they are SQLAlchemy Core `select()`
  objects over `messages`, not SQL views, and execute no DDL (feature `012`, D1).
- There are **no per-feature table modules**, no import-side-effect registration and no
  `build_registry()` builder callable. A single file has no import-order hazard, and
  nothing can be silently absent from the drift report because nobody imported it.
- Feature `007` walks `metadata.tables` directly — named, enumerable `Table` objects are
  the whole contract, and nothing beyond that is needed or should be built.

This module **executes no DDL**, including at import. The content features each add
their own tables here; DDL only ever runs through `007`'s admin-triggered `Create` and
`Sync` actions (and `003`'s first-run `create_all`).
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    false,
    select,
    true,
)

from app.roles import Role

#: The one registry. Every `Table(...)` in this project is bound to it; `007` walks
#: `metadata.tables` to produce the drift report.
metadata = MetaData()


def _role_values(enum_class: type[Role]) -> list[str]:
    """Persist the enum's *values* (`roleplayer`, `admin`), never its member names."""
    return [member.value for member in enum_class]


#: Accounts (`data-model.md` § `users`). Every column is declared, including the two
#: language defaults `003` leaves NULL. `id` is a snowflake minted before the INSERT:
#: `BigInteger` in Core, rendered as `INTEGER PRIMARY KEY` (the rowid alias) on SQLite,
#: never auto-incrementing. `role` is a non-native enum: a text column plus a named CHECK
#: constraint on the table, storing the enum values.
users = Table(
    "users",
    metadata,
    Column("id", BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=False),
    Column("username", Text, nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column(
        "role",
        Enum(
            Role,
            name="users_role",
            native_enum=False,
            create_constraint=True,
            values_callable=_role_values,
            validate_strings=True,
            length=32,
        ),
        nullable=False,
    ),
    Column("is_enabled", Boolean, nullable=False),
    Column("rp_language", Text, nullable=True),
    Column("preferred_language", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("last_login_at", Text, nullable=True),
)


#: Server-side login sessions (`data-model.md` § `auth_sessions`). Exactly the six columns
#: that section names. `id` is a snowflake minted before the INSERT, stored exactly as
#: `users.id` is (rowid alias on SQLite, never auto-incrementing). `token_hash` holds the
#: SHA-256 digest of the session token, never the token; `created_at` / `expires_at` are
#: UTC ISO-8601 text; `revoked_at` is NULL until the row is revoked — rows are never
#: deleted, so a revocation stays observable. `token_hash` is uniquely indexed (the lookup
#: key on every authenticated request); `user_id` is indexed (FEAT-003's disable path
#: revokes every row for one user in one transaction).
auth_sessions = Table(
    "auth_sessions",
    metadata,
    Column("id", BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=False),
    Column(
        "user_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("users.id"),
        nullable=False,
    ),
    Column("token_hash", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("expires_at", Text, nullable=False),
    Column("revoked_at", Text, nullable=True),
    Index("ix_auth_sessions_token_hash", "token_hash", unique=True),
    Index("ix_auth_sessions_user_id", "user_id"),
)


#: Registered OpenAI-compatible servers (`data-model.md` § `llm_servers`). Exactly the ten
#: columns that section names — deliberately **no** `active` column (feature `006`'s D1).
#: `id` is a snowflake minted before the INSERT, stored exactly as `users.id` is. `kind` is
#: plain text with no `CHECK`: its two values are a pydantic literal at the router boundary
#: (D5). `api_key_ref` holds a `"$ENV_VAR"` **pointer**, never a credential, so the database
#: never contains an API key. The three `last_test_*` columns record UC-011's outcome and are
#: NULL until the first test; `last_test_error` stores the typed outcome value itself.
#: Timestamps are UTC ISO-8601 text.
llm_servers = Table(
    "llm_servers",
    metadata,
    Column("id", BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=False),
    Column("name", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("base_url", Text, nullable=False),
    Column("api_key_ref", Text, nullable=True),
    Column("last_test_at", Text, nullable=True),
    Column("last_test_ok", Boolean, nullable=True),
    Column("last_test_error", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)


#: Models known on a registered server (`data-model.md` § `models`). `server_id` is a
#: foreign key to `llm_servers.id` declared `ON DELETE CASCADE` — the structural truth
#: `db/drift.py` introspects; `006/003`'s delete also removes the rows explicitly so the
#: behaviour holds regardless of `PRAGMA foreign_keys`. Unique on `(server_id,
#: model_name)`. The two flags are non-nullable and default to false; `embedding_dim` is
#: meaningful only on the designated row (`vec0` tables have a fixed dimension).
models = Table(
    "models",
    metadata,
    Column("id", BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=False),
    Column(
        "server_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("llm_servers.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("model_name", Text, nullable=False),
    Column("is_enabled", Boolean, nullable=False, default=False, server_default=false()),
    Column("is_embedding_designated", Boolean, nullable=False, default=False, server_default=false()),
    Column("embedding_dim", Integer, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    UniqueConstraint("server_id", "model_name", name="uq_models_server_id_model_name"),
)


#: The roleplayer's characters (`data-model.md` § `characters`). Feature `009`'s D5 declared
#: seven columns; feature `017` adds the character level of the **assistant chain** (R1):
#: the model override as two columns (`017` D4) — `model_server_id` (the registry's id type,
#: **no foreign key**, so deleting an LLM server never cascades into or silently nulls a
#: reference, R4) and `model_name` — held both-NULL or both-non-NULL by the named CHECK;
#: `system_prompt`; and one nullable boolean per tool (`017` D5: `tool_memo_search`,
#: `tool_session_search`, `tool_web_search`). All six are nullable with no default — NULL
#: is "no override". The character's model matters only when a session is created (R4: it
#: is captured then, never re-walked). There is deliberately **no** `rp_language` or
#: `preferred_language` column — the language chain skips this level (R1).
#: `user_id` is a foreign key to `users.id` with **no `ON DELETE`**: nothing deletes a user
#: or a character (R6), so a cascade would describe an event that cannot happen. One
#: non-unique index on `user_id`, because every read is scoped by the owner (R5). `sheet` is
#: NOT NULL with **no server default** — the service always writes it, `""` when the request
#: omits it. `archived_at` is NULL for a working character and holds the instant it was
#: archived otherwise. Timestamps are the fixed-width UTC text form.
characters = Table(
    "characters",
    metadata,
    Column("id", BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=False),
    Column(
        "user_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("users.id"),
        nullable=False,
    ),
    Column("name", Text, nullable=False),
    Column("sheet", Text, nullable=False),
    Column("archived_at", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("model_server_id", BigInteger().with_variant(Integer(), "sqlite"), nullable=True),
    Column("model_name", Text, nullable=True),
    Column("system_prompt", Text, nullable=True),
    Column("tool_memo_search", Boolean, nullable=True),
    Column("tool_session_search", Boolean, nullable=True),
    Column("tool_web_search", Boolean, nullable=True),
    Index("ix_characters_user_id", "user_id"),
    CheckConstraint(
        "(model_server_id IS NULL AND model_name IS NULL)"
        " OR (model_server_id IS NOT NULL AND model_name IS NOT NULL)",
        name="ck_characters_model_both_or_neither",
    ),
)


#: A character's reusable situation descriptions (`data-model.md` § `setups`). Feature `010`'s
#: D7 declares exactly the eight columns that section names and **no configuration overrides**
#: (R1) — a setup is a name plus one markdown `description`. `user_id` is the direct owner
#: column every read scopes by (R5); `character_id` is the parent character, fixed for the
#: setup's life (D5). Both foreign keys are bare, with **no `ON DELETE`**: nothing deletes a
#: user, a character or a setup (R6), so a cascade would describe an event that cannot happen.
#: One **non-unique composite** index on `(user_id, character_id)` — the working-list query
#: filters both, and the leftmost `user_id` prefix also serves every by-owner scan, so one
#: index instead of two. `description` is NOT NULL with **no server default**: the service
#: always writes it, `""` when the request omits it. `archived_at` is NULL for a working setup
#: and holds the instant it was archived otherwise; there is no delete path (R6). Timestamps
#: are the fixed-width UTC text form.
setups = Table(
    "setups",
    metadata,
    Column("id", BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=False),
    Column(
        "user_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("users.id"),
        nullable=False,
    ),
    Column(
        "character_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("characters.id"),
        nullable=False,
    ),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("archived_at", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Index("ix_setups_user_id_character_id", "user_id", "character_id"),
)


#: One RP session — a run under one character (`data-model.md` § `sessions`). Feature `011`'s
#: D8 declares exactly **eight** of the columns that section names. Deliberately absent:
#: `title` and `partner_label` (D4 — no product id lets the roleplayer set either, and a
#: column with no writer would be a stored empty string forever; `session_fts` lands with the
#: feature that gives a session text). Feature `017` adds the session level of both chains
#: (R1): the **captured model** (R4, `017` D1 — written at creation and by the header picker
#: only, read as-is and validated at use) as `model_server_id` (the registry's id type, **no
#: foreign key**, D4) and `model_name`, held both-NULL or both-non-NULL by the named CHECK;
#: `system_prompt` and one nullable boolean per tool (D5), resolved live over the character;
#: and `rp_language` / `preferred_language` (D6: trimmed, blank stored as NULL), resolved over
#: the user. All eight are nullable with no default — NULL is "inherit" (or, for the model,
#: "none chosen"). There is **no status or state column** — `data-model.md` says a session is never finished,
#: so the only state is `archived_at`. `user_id` is the direct owner column every read scopes
#: by (R5); `character_id` is the parent character. `setup_id` is **nullable with no server
#: default and no sentinel** (R2): a session started with no setup simply has NULL, and no
#: flow makes choosing a setup a precondition. All three foreign keys are bare, with **no
#: `ON DELETE`**: nothing deletes a user, a character, a setup or a session (R6), so a cascade
#: would describe an event that cannot happen. One **non-unique composite** index on
#: `(user_id, character_id)` — the per-character list filters both, and the leftmost `user_id`
#: prefix also serves the all-sessions list and every by-owner scan, so one index instead of
#: two; `setup_id` carries none, because no query filters by it. `last_used_at` is set at
#: creation and bumped only by content writes (D3), which is a different instant from
#: `updated_at`; `archived_at` is NULL for a working session and holds the instant it was
#: archived otherwise. Timestamps are the fixed-width UTC text form.
sessions = Table(
    "sessions",
    metadata,
    Column("id", BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=False),
    Column(
        "user_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("users.id"),
        nullable=False,
    ),
    Column(
        "character_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("characters.id"),
        nullable=False,
    ),
    Column(
        "setup_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("setups.id"),
        nullable=True,
    ),
    Column("last_used_at", Text, nullable=False),
    Column("archived_at", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("model_server_id", BigInteger().with_variant(Integer(), "sqlite"), nullable=True),
    Column("model_name", Text, nullable=True),
    Column("system_prompt", Text, nullable=True),
    Column("tool_memo_search", Boolean, nullable=True),
    Column("tool_session_search", Boolean, nullable=True),
    Column("tool_web_search", Boolean, nullable=True),
    Column("rp_language", Text, nullable=True),
    Column("preferred_language", Text, nullable=True),
    Index("ix_sessions_user_id_character_id", "user_id", "character_id"),
    CheckConstraint(
        "(model_server_id IS NULL AND model_name IS NULL)"
        " OR (model_server_id IS NOT NULL AND model_name IS NOT NULL)",
        name="ck_sessions_model_both_or_neither",
    ),
)


#: Every row of a session's stream (`data-model.md` § `messages`; feature `012`, D1). `id` is
#: a snowflake and `ORDER BY id` **is** stream order — there is no position column. `user_id`
#: is the owner (R5), `session_id` the parent session, `related_to` a self-reference to the
#: settled head a buried row lies under. `role` and `kind` are plain text with **no** CHECK:
#: the pydantic boundary constrains what is written. `kind` and `settled_at` are NULL until a
#: row is settled; `tool_name` / `tool_payload` serve `role='tool'` rows only (R9) and have no
#: writer yet. The four states: NULL/NULL = current zone; `related_to` NULL + `settled_at` set
#: = record; `related_to` set + `settled_at` NULL = buried; both set = illegal (the named
#: CHECK). Every foreign key is bare, with **no `ON DELETE`** — nothing deletes a message
#: (R6). Two non-unique indexes: `(session_id, settled_at)` for the stream reads and
#: `(related_to)` for the group lookups of settle / re-open. Timestamps are the fixed-width
#: UTC text form.
messages = Table(
    "messages",
    metadata,
    Column("id", BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=False),
    Column(
        "user_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("users.id"),
        nullable=False,
    ),
    Column(
        "session_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("sessions.id"),
        nullable=False,
    ),
    Column("role", Text, nullable=False),
    Column("kind", Text, nullable=True),
    Column("text", Text, nullable=False),
    Column(
        "related_to",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("messages.id"),
        nullable=True,
    ),
    Column("settled_at", Text, nullable=True),
    Column("tool_name", Text, nullable=True),
    Column("tool_payload", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    CheckConstraint("related_to IS NULL OR settled_at IS NULL", name="ck_messages_buried_or_settled"),
    Index("ix_messages_session_id_settled_at", "session_id", "settled_at"),
    Index("ix_messages_related_to", "related_to"),
)


#: The roleplayer's notes (`data-model.md` § `memos`; feature `015`, D10). Exactly ten
#: columns. Deliberately absent: `title`, `name`, `archived_at` and any `state` / `status`
#: column — `data-model.md` forbids each, and a note is removed by a hard delete (D2), never
#: archived. `user_id` is the direct owner column every read scopes by; its foreign key is bare,
#: with **no `ON DELETE`** — nothing deletes a user. `scope` + `scope_id` is the polymorphic
#: level pair: `scope_id` is the caller, a character, a setup or a session id depending on
#: `scope`, so it carries **no foreign key** (the referential-integrity trade `data-model.md`
#: records). `scope` is a non-native enum with its CHECK created (the `users.role` form, D10):
#: the four values are R2's chain itself, and a row with any other scope would be a note no
#: chain query ever finds — the constraint makes it unwritable. The same four strings are the
#: scope literal in `models/memos.py` (`db/` never imports `models/`); a test pins the
#: equality. `sort_key` has no default and **no unique constraint**: the service allocates it
#: inside the create transaction (D4). `is_enabled` defaults true and `is_forced` false, each
#: with a matching server default. One **non-unique composite** index on
#: `(user_id, scope, scope_id, sort_key)`: the level list filters the first three and orders by
#: the fourth, each chain OR-term shares the three-column prefix, and the `MAX(sort_key)`
#: allocation is an index seek. Timestamps are the fixed-width UTC text form.
memos = Table(
    "memos",
    metadata,
    Column("id", BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=False),
    Column(
        "user_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("users.id"),
        nullable=False,
    ),
    Column(
        "scope",
        Enum(
            "user",
            "character",
            "setup",
            "session",
            name="memos_scope",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            length=16,
        ),
        nullable=False,
    ),
    Column("scope_id", BigInteger().with_variant(Integer(), "sqlite"), nullable=False),
    Column("body", Text, nullable=False),
    Column("is_enabled", Boolean, nullable=False, default=True, server_default=true()),
    Column("is_forced", Boolean, nullable=False, default=False, server_default=false()),
    Column("sort_key", Integer, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Index("ix_memos_user_id_scope_scope_id_sort_key", "user_id", "scope", "scope_id", "sort_key"),
)


#: Cached translations of settled partner rows (`data-model.md` § `translations`; feature
#: `023`, D7). Exactly six columns. `user_id` is the direct owner column every read scopes by
#: (R5). `message_id` is the translated row; its foreign key is bare, with **no `ON DELETE`** —
#: nothing deletes a message (R6), and an edit discards the row's translations explicitly
#: (D11). Unique on `(message_id, target_language)`: one cached text per row and language.
#: Deliberately absent: `updated_at` (a row is only ever inserted or deleted, never updated)
#: and any state column (absence means "not translated"). Timestamps are the fixed-width UTC
#: text form.
translations = Table(
    "translations",
    metadata,
    Column("id", BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=False),
    Column(
        "user_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("users.id"),
        nullable=False,
    ),
    Column(
        "message_id",
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("messages.id"),
        nullable=False,
    ),
    Column("target_language", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    UniqueConstraint("message_id", "target_language", name="uq_translations_message_id_target_language"),
)


#: The settled record (D1): every `messages` column of every row whose `settled_at` is set.
#: No session filter and no ordering — callers narrow and order it on its own columns.
settled_entries = select(messages).where(messages.c.settled_at.is_not(None))

#: The current zone (D1): every `messages` column of every row with `related_to` and
#: `settled_at` both NULL. No session filter and no ordering.
current_zone = select(messages).where(
    messages.c.related_to.is_(None),
    messages.c.settled_at.is_(None),
)

#: The buried rows (feature `022` D2): every `messages` column of every row whose
#: `related_to` is set. No owner or session filter and no ordering — callers narrow it.
buried_messages = select(messages).where(messages.c.related_to.is_not(None))

#: A row's state without its content (D7): only `id`, `user_id`, `session_id`, `related_to`
#: and `settled_at` — never `text` or `kind`. No filter and no ordering.
message_states = select(
    messages.c.id,
    messages.c.user_id,
    messages.c.session_id,
    messages.c.related_to,
    messages.c.settled_at,
)
