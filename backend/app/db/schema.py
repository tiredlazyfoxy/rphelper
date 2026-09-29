"""The table-definition registry — the single source of truth for the schema.

`docs/architecture/backend-structure.md` § Persistence access, reason 3: a Core
`MetaData` with `Table` objects **is** the declaration that `PRAGMA table_info` /
`index_list` are compared against, so `db/schema.py` stays "the single introspectable
source of truth and `db/drift.py` walks it directly".

The rule every later feature binds to, and which this module exists to state:

- **Every table in RPHelper is declared as a `Table(...)` literal in this file**, bound
  to the `metadata` object below. The two SQL views `data-model.md` declares live here
  too, with the features that own them.
- There are **no per-feature table modules**, no import-side-effect registration and no
  `build_registry()` builder callable. A single file has no import-order hazard, and
  nothing can be silently absent from the drift report because nobody imported it.
- Feature `007` walks `metadata.tables` directly — named, enumerable `Table` objects are
  the whole contract, and nothing beyond that is needed or should be built.

This module **executes no DDL**, including at import. The content features each add
their own tables here; DDL only ever runs through `007`'s admin-triggered `Create` and
`Sync` actions (and `003`'s first-run `create_all`).
"""

from sqlalchemy import BigInteger, Boolean, Column, Enum, ForeignKey, Index, Integer, MetaData, String, Table, Text

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
