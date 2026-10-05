"""Export — the transfer envelope, the column-agnostic row serializer, and the whole-database export.

Feature `030`, step `001` (FEAT-018, UC-061). Plain arguments in, a JSON-safe `ExportEnvelope`
out. This module imports nothing HTTP-shaped: routers (step `003`) do HTTP only and call in
here for every byte they send.

**It never names a column.** Rows are read with a Core `select(<Table>)` over the
`app.db.schema` Table objects, so a column added by a later feature flows through on its own
(`context.md` §"Build-order assumption"). Table *sets* are explicit; column lists are not. The
one exception is the optional `drop_columns` argument, which a caller uses to withhold named
columns from a serialized row.

`read_table` is the **only** place this module issues a `select`. Step `002` adds the user,
character and session exports on top of these four seams unchanged — the serializer, the table
reader, the envelope builder and the `_reading` snapshot — and contributes its own scoping
predicates through `read_table`'s `where` argument.

`app.db.search_tables` is deliberately **not** imported: 024's FTS5/vec0 tables carry no
`Table(...)` declaration and live outside `schema.metadata`, so a walk over
`metadata.sorted_tables` cannot reach them and vectors are absent by construction.

Transaction discipline. One export is one read transaction, so the file is a consistent
snapshot under WAL. A read on a Core connection autobegins, so every export body runs its
selects inside `_reading(connection)`, which ends a transaction this module opened
(`backend-structure.md` §"Transactional DDL").
"""

import json
from collections.abc import Collection, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Final, Literal, TypedDict

from sqlalchemy import Column, ColumnElement, Connection, Row, Table, and_, or_, select

from app.db import schema
from app.errors import CharacterNotFoundError, SessionNotFoundError

ExportGranularity = Literal["database", "user", "character", "session"]
"""The four granularities an envelope's `granularity` key may carry (`context.md` §"The envelope")."""

JsonScalar = str | int | float | bool | None
"""One serialized cell: ids and timestamps as text, booleans as booleans, other numbers as numbers."""

ExportRow = dict[str, JsonScalar]
"""One serialized row — column name to JSON-safe value."""

ExportPayload = dict[str, list[ExportRow]]
"""An envelope's `payload` — table name to its rows, keys in `schema.metadata.sorted_tables` order."""

EXPORT_FORMAT: Final[str] = "rphelper-export"
"""The envelope's `format` key — the literal that marks a file as an RPHelper export."""

ENVELOPE_VERSION: Final[int] = 1
"""The envelope's own format version. Bumped when the envelope shape or a serialization rule changes."""

SCHEMA_VERSION: Final[int] = 1
"""The registry-shape version. Bumped **by hand** whenever `app.db.schema` changes a table's shape.

Separate from `ENVELOPE_VERSION` on purpose: the two move independently (`context.md`
§"The envelope"). No other schema-version constant exists anywhere in the project.
"""

DATABASE_EXCLUDED_TABLES: Final[frozenset[str]] = frozenset({"auth_sessions", "translations"})
"""The tables the whole-database export skips: live login tokens, and the derived translation cache.

`auth_sessions` holds live session tokens; `translations` is a regenerable cache, excluded like
vectors are (`context.md` §"Granularity boundaries"). The exclusion is explicit, never implied by
a missing declaration. The user granularity (step `002`) keeps its own constants.
"""

USER_EXCLUDED_TABLES: Final[frozenset[str]] = frozenset({"auth_sessions", "translations"})
"""The tables that are **not** user material, so a `user` export never carries them.

Same two names as `DATABASE_EXCLUDED_TABLES` and a deliberately separate constant: the two
granularities justify their exclusions differently and may diverge. This is also the other half
of the user-granularity classification guard — every `metadata` table with a `user_id` column is
either in the user payload or named here, so a later feature that adds user-owned material has to
classify it (`002.owned-selections.md` DoD-5).
"""

USER_EXCLUDED_COLUMNS: Final[frozenset[str]] = frozenset({"password_hash", "role", "is_enabled"})
"""The `users` columns a `user` export withholds, passed to `read_table`'s `drop_columns`.

`role` and `is_enabled` are administrator-controlled account state, not material the roleplayer
owns: carrying `role` into a file they hold would put a privilege grant in their hands, ready for
an import path to apply. `password_hash` leaves for the obvious reason. `id` **stays** — it is the
`user_id` of every other row and the `scope_id` of every `scope='user'` memo, so 031 needs it to
remap (`002.context.md`). Every other `users` column, including any added later, flows through.
"""

_ID_SUFFIX: Final[str] = "_id"
"""The reference-name pattern the id rule matches (`context.md` §"Row serialization rules").

Not a column name and not a column list: it is the shape that catches the three FK-less
references — `memos.scope_id` and 017's `model_server_id` on `characters` and on `sessions` —
without this module ever naming one of them, so a reference a later feature adds is caught on its
own.
"""

_ID_NAME: Final[str] = _ID_SUFFIX.removeprefix("_")
"""The same pattern without its separator: the bare reference name the id rule also matches.

Derived from `_ID_SUFFIX` rather than written out, because the one thing this module must never
spell is a column name. Every table in `schema.metadata` declares that name as its primary key, so
the primary-key arm of the rule reaches it as well.
"""

_FILENAME_TIMESTAMP: Final[str] = "%Y%m%dT%H%M%SZ"
"""The compact UTC stamp an export's file name carries: digits and letters only, no separator.

A `Content-Disposition` filename travels through quoting that `:` and `.` complicate, so
`created_at` is reformatted into this shape rather than embedded (`001.transfer-core.md` DoD-11).
"""

#: Three of R2's four memo levels, as `memos.scope` stores them (`app.models.memos.MemoScope`).
#: Scope *values*, not column names: they are what the character and session granularities filter
#: a `(scope, scope_id)` pair on (`data-model.md` ~L643-658). The fourth level, `user`, needs no
#: constant — the user granularity filters memos on ownership alone, at every scope.
_CHARACTER_SCOPE: Final[str] = "character"
_SETUP_SCOPE: Final[str] = "setup"
_SESSION_SCOPE: Final[str] = "session"


class ExportEnvelope(TypedDict):
    """The whole export file as one JSON object (`context.md` §"The envelope").

    A plain mapping, not a model: it is what `encode_envelope` dumps and what 031's import
    reads. There is no root-reference header field — at `user`, `character` and `session`
    granularity the payload's `users`, `characters` or `sessions` list holds exactly one row,
    and that row is the root.
    """

    format: str
    version: int
    granularity: ExportGranularity
    created_at: str
    schema_version: int
    payload: ExportPayload


def serialize_row(table: Table, row: Row[Any], *, drop_columns: Collection[str] = ()) -> ExportRow:
    """One selected row as a JSON-safe mapping of column name to value.

    Every column `table` declares is present, except any named in `drop_columns` (step `002`
    withholds three `users` columns that way). The rules are `context.md` §"Row serialization
    rules":

    - **Id columns become decimal strings**, so snowflakes survive a JSON number. An integer
      column is an id when it is part of the primary key, when it carries a foreign key, or
      when its name is `id` or ends in `_id`. A null id stays `None`.
    - **Enum members become their string value**, tested before the plain-string case, because
      `users.role` arrives as a `Role` member while `memos.scope` arrives as a plain `str`.
    - **Booleans stay booleans, timestamps stay the stored text, nulls stay null**, and other
      integers and floats (e.g. `models.embedding_dim`) pass through as numbers.

    Id detection reads `table`'s own metadata — its primary key, its foreign keys and its
    column names — and **never** a hard-coded column list, so a reference added by a later
    feature is caught without touching this module.
    """
    dropped = set(drop_columns)
    key_names = {column.name for column in table.primary_key.columns}
    values = row._mapping
    return {
        column.name: _serialize_value(values[column.name], is_id=is_id_column(column, key_names))
        for column in table.columns
        if column.name not in dropped
    }


def read_table(
    connection: Connection,
    table: Table,
    where: ColumnElement[bool] | None = None,
    *,
    drop_columns: Collection[str] = (),
) -> list[ExportRow]:
    """Every column of `table`'s matching rows, primary-key ascending, already serialized.

    The **one** place this module issues a `select`. `where` narrows the read and is `None` for
    an unscoped one: step `002` passes its owner-scoped (`user_id`) and id-scoped predicates —
    including `and_` / `or_` combinations and `in_` subqueries over sibling tables — through
    this argument, and `drop_columns` forwards to `serialize_row` for the user export's `users`
    row. No caller outside this module builds a statement.

    Assumes a read transaction is already open or will be ended by the caller's `_reading`.
    """
    statement = select(table).order_by(*table.primary_key.columns)
    if where is not None:
        statement = statement.where(where)
    return [
        serialize_row(table, row, drop_columns=drop_columns)
        for row in connection.execute(statement).all()
    ]


def ordered_table_names(included: Collection[str]) -> list[str]:
    """The given table names in `schema.metadata.sorted_tables` order.

    The order is read from the registry, never from a literal list, because `sorted_tables` is
    a topological sort (`memos` precedes `setups`, `sessions` and `messages`) that shifts when
    a foreign key is added. Payload keys follow it so that 031 can insert parents first
    (`context.md` §"Row serialization rules").
    """
    wanted = set(included)
    return [table.name for table in schema.metadata.sorted_tables if table.name in wanted]


def build_envelope(granularity: ExportGranularity, payload: ExportPayload) -> ExportEnvelope:
    """Wrap an already-ordered payload in the envelope, stamping `created_at` as of now.

    `format`, `version` and `schema_version` come from this module's constants; `created_at`
    is `_now_text()`, the same UTC ISO-8601 shape the other services write. The payload's key
    order is the caller's — `ordered_table_names` is what produces it — and is preserved here.
    """
    return ExportEnvelope(
        format=EXPORT_FORMAT,
        version=ENVELOPE_VERSION,
        granularity=granularity,
        created_at=_now_text(),
        schema_version=SCHEMA_VERSION,
        payload=payload,
    )


def export_database(connection: Connection) -> ExportEnvelope:
    """The whole instance as a `database` envelope. Admin only; takes **no** `user_id`.

    Every table in `schema.metadata.sorted_tables` that is not in `DATABASE_EXCLUDED_TABLES`,
    with every row and every column, including `users.password_hash` and `llm_servers`'
    `api_key_ref` pointer (carried as stored — a resolved secret never appears). This is the
    one deliberately unscoped read in the feature (R5 by opacity).
    """
    with _reading(connection):
        rows_by_table = {
            table.name: read_table(connection, table)
            for table in schema.metadata.sorted_tables
            if table.name not in DATABASE_EXCLUDED_TABLES
        }
        payload = _ordered_payload(rows_by_table)
    return build_envelope("database", payload)


def export_user(connection: Connection, user_id: int) -> ExportEnvelope:
    """One roleplayer's own material as a `user` envelope. Every select filters on `user_id`.

    The payload holds the caller's single `users` row minus `USER_EXCLUDED_COLUMNS`, and their
    `characters`, `setups`, `sessions`, `messages` and **all** their `memos` — every scope,
    `user` included (`context.md` §"Granularity boundaries"). Archived characters, setups and
    sessions are included (R6). There are no `llm_servers` or `models` rows, and nothing from
    `USER_EXCLUDED_TABLES`.

    Payload key order is whatever `ordered_table_names` returns for that table set, computed
    from `schema.metadata`: never a literal sequence, because `sorted_tables` is a topological
    sort in which `memos` precedes `setups`, `sessions` and `messages`.

    Runs its selects inside `_reading(connection)`, so the file is one snapshot.
    """
    with _reading(connection):
        rows_by_table = {
            schema.users.name: read_table(
                connection,
                schema.users,
                schema.users.c.id == user_id,
                drop_columns=USER_EXCLUDED_COLUMNS,
            ),
            schema.characters.name: read_table(connection, schema.characters, schema.characters.c.user_id == user_id),
            schema.setups.name: read_table(connection, schema.setups, schema.setups.c.user_id == user_id),
            schema.sessions.name: read_table(connection, schema.sessions, schema.sessions.c.user_id == user_id),
            schema.messages.name: read_table(connection, schema.messages, schema.messages.c.user_id == user_id),
            schema.memos.name: read_table(connection, schema.memos, schema.memos.c.user_id == user_id),
        }
        payload = _ordered_payload(rows_by_table)
    return build_envelope("user", payload)


def export_character(connection: Connection, user_id: int, character_id: int) -> ExportEnvelope:
    """One character and everything under it as a `character` envelope, scoped to its owner.

    The root row is read by this module's **own** full-row select filtered on both `id` and
    `user_id` — not `services.characters.get_character` — because the full row is needed for the
    payload anyway, the lookup belongs inside this export's single read snapshot, and R6 requires
    an archived character to export regardless of what that getter filters. When no row comes
    back, raises `CharacterNotFoundError` (`character_not_found`, 404): a foreign id and a missing
    id are indistinguishable, and there is no 403 (`002.context.md`).

    Beyond the one `characters` row the payload carries its `setups`, its `sessions` (archived
    included) and those sessions' `messages`, plus the `memos` scoped to the character, to its
    setups or to its sessions — an empty id list contributes no term. No `scope='user'` memo and
    no sibling character's material appears. There is no `users` key, so the rows' `user_id`
    dangles by design (031 decides remap or null).

    Payload key order comes from `ordered_table_names` over `schema.metadata`, never a literal.
    """
    with _reading(connection):
        character_rows = read_table(
            connection,
            schema.characters,
            and_(schema.characters.c.id == character_id, schema.characters.c.user_id == user_id),
        )
        if not character_rows:
            raise CharacterNotFoundError()
        setup_rows = read_table(
            connection,
            schema.setups,
            and_(schema.setups.c.user_id == user_id, schema.setups.c.character_id == character_id),
        )
        session_rows = read_table(
            connection,
            schema.sessions,
            and_(schema.sessions.c.user_id == user_id, schema.sessions.c.character_id == character_id),
        )
        setup_ids = _row_ids(schema.setups, setup_rows)
        session_ids = _row_ids(schema.sessions, session_rows)
        message_rows: list[ExportRow] = []
        if session_ids:
            message_rows = read_table(
                connection,
                schema.messages,
                and_(
                    schema.messages.c.user_id == user_id,
                    schema.messages.c.session_id.in_(session_ids),
                ),
            )
        scope_terms = _character_memo_scopes(character_id, setup_ids, session_ids)
        memo_rows = read_table(
            connection,
            schema.memos,
            and_(schema.memos.c.user_id == user_id, or_(*scope_terms)),
        )
        payload = _ordered_payload(
            {
                schema.characters.name: character_rows,
                schema.setups.name: setup_rows,
                schema.sessions.name: session_rows,
                schema.messages.name: message_rows,
                schema.memos.name: memo_rows,
            }
        )
    return build_envelope("character", payload)


def export_session(connection: Connection, user_id: int, session_id: int) -> ExportEnvelope:
    """One RP session as a `session` envelope, scoped to its owner.

    The root row is read by this module's own full-row select filtered on both `id` and `user_id`,
    for the same three reasons as `export_character`, and an archived session still exports (R6).
    When no row comes back, raises `SessionNotFoundError` (`session_not_found`, 404); foreign and
    missing are indistinguishable and there is no 403.

    The payload carries that one `sessions` row, **all** of its `messages` — settled, buried and
    current-zone, read from the raw `messages` Table by `session_id`, never through
    `settled_entries` or `current_zone`, which drop buried rows and would leave `related_to`
    dangling — and only the `memos` with `scope='session'` and this session's `scope_id`. Its
    `character_id` and `setup_id` refs dangle by design (the C12 consequence, UC-064).

    Payload key order comes from `ordered_table_names` over `schema.metadata`, never a literal.
    """
    with _reading(connection):
        session_rows = read_table(
            connection,
            schema.sessions,
            and_(schema.sessions.c.id == session_id, schema.sessions.c.user_id == user_id),
        )
        if not session_rows:
            raise SessionNotFoundError()
        message_rows = read_table(
            connection,
            schema.messages,
            and_(schema.messages.c.user_id == user_id, schema.messages.c.session_id == session_id),
        )
        memo_rows = read_table(
            connection,
            schema.memos,
            and_(
                schema.memos.c.user_id == user_id,
                schema.memos.c.scope == _SESSION_SCOPE,
                schema.memos.c.scope_id == session_id,
            ),
        )
        payload = _ordered_payload(
            {
                schema.sessions.name: session_rows,
                schema.messages.name: message_rows,
                schema.memos.name: memo_rows,
            }
        )
    return build_envelope("session", payload)


def encode_envelope(envelope: ExportEnvelope) -> bytes:
    """The envelope as the UTF-8 JSON bytes a route streams out. Non-ASCII text survives as itself."""
    return json.dumps(envelope, ensure_ascii=False).encode("utf-8")


def export_filename(envelope: ExportEnvelope) -> str:
    """`rphelper-<granularity>-<compact UTC timestamp>.json`, for the `Content-Disposition` header.

    Derived **only** from the envelope's `granularity` and `created_at`, so the name can carry
    no row content — no name, no title, no id (US-078 opacity). The compact form is
    `created_at` without its separators and offset, e.g. `20261005T142530Z`.
    """
    stamp = datetime.fromisoformat(envelope["created_at"]).astimezone(UTC).strftime(_FILENAME_TIMESTAMP)
    granularity = envelope["granularity"]
    return f"rphelper-{granularity}-{stamp}.json"


def is_id_column(column: Column[Any], primary_key_names: Collection[str]) -> bool:
    """Whether `column` holds a reference, so its value leaves as decimal text.

    The three arms of `context.md`'s rule, each read off the column itself: it is part of its
    table's primary key, it carries a foreign key (which is the only arm that catches
    `messages.related_to`), or its name matches the reference-name pattern.

    Public, not private, because 031's `services.transfer_import` deserializes a cell with the
    **same** predicate, so the two directions of the id rule cannot disagree
    (`031/context.md` §"Deserialization"). Its behaviour is unchanged by that exposure.
    """
    name = column.name
    return (
        name in primary_key_names
        or bool(column.foreign_keys)
        or name == _ID_NAME
        or name.endswith(_ID_SUFFIX)
    )


def _serialize_value(value: Any, *, is_id: bool) -> JsonScalar:
    """One selected cell as JSON-safe data, under `context.md` §"Row serialization rules".

    Arm order is load-bearing. Null wins first, so a null reference stays null rather than
    becoming `"None"`. An **enum member** is converted before the plain-string case, because
    `Role` is a `StrEnum` and would otherwise pass through as an enum instance. A bool is
    settled before the id arm, since `bool` is an `int` subclass. Only then does an id integer
    become decimal text, keeping a snowflake JS-safe (`backend-structure.md` §"The JSON id
    boundary"). Everything else — timestamp text, non-id integers, floats — passes through.
    """
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, bool):
        return value
    if is_id and isinstance(value, int):
        return str(value)
    if isinstance(value, str | int | float):
        return value
    return str(value)


def _character_memo_scopes(
    character_id: int,
    setup_ids: Collection[int],
    session_ids: Collection[int],
) -> list[ColumnElement[bool]]:
    """The `(scope, scope_id)` terms a character export's memos may match, as an or-able list.

    One term per level the character reaches: itself, its setups, its sessions. **An empty id
    list contributes no term** rather than an `IN ()`, which carries no rows but does carry a
    needless always-false clause into the statement. The character term is always present, so the
    list is never empty and `or_` always has something to combine (`002.context.md`).
    """
    terms: list[ColumnElement[bool]] = [
        and_(schema.memos.c.scope == _CHARACTER_SCOPE, schema.memos.c.scope_id == character_id)
    ]
    if setup_ids:
        terms.append(
            and_(schema.memos.c.scope == _SETUP_SCOPE, schema.memos.c.scope_id.in_(setup_ids))
        )
    if session_ids:
        terms.append(
            and_(schema.memos.c.scope == _SESSION_SCOPE, schema.memos.c.scope_id.in_(session_ids))
        )
    return terms


def _ordered_payload(rows_by_table: Mapping[str, list[ExportRow]]) -> ExportPayload:
    """The same rows, re-keyed in `schema.metadata.sorted_tables` order.

    Every export assembles its tables in whatever order its own reads need — the character
    export has to hold its setup and session ids before it can scope memos — and hands the
    result through here, so payload key order is the registry's and never an export's.
    """
    return {name: rows_by_table[name] for name in ordered_table_names(rows_by_table)}


def _row_ids(table: Table, rows: list[ExportRow]) -> list[int]:
    """The primary-key values of already-serialized rows, back as the ints a predicate needs.

    The key name comes from `table.primary_key`, never from a literal, and `serialize_row` has
    already written it as decimal text. This keeps `read_table` the module's only `select`: a
    scope that depends on sibling ids reuses the rows it has already read.
    """
    key_names = [column.name for column in table.primary_key.columns]
    ids: list[int] = []
    for row in rows:
        for name in key_names:
            value = row[name]
            if isinstance(value, str):
                ids.append(int(value))
    return ids


def _now_text() -> str:
    """Now as the fixed-width UTC ISO-8601 text the other services write."""
    return datetime.now(UTC).isoformat(timespec="microseconds")


@contextmanager
def _reading(connection: Connection) -> Iterator[None]:
    """A read on a Core connection autobegins; end it again when the caller had none open."""
    opened_here = not connection.in_transaction()
    try:
        yield
    finally:
        if opened_here and connection.in_transaction():
            connection.rollback()
