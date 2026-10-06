"""Import — envelope validation, the inverse of 030's row serializer, and (later) the writes.

Feature `031`. The sibling of `services/transfer.py` and its opposite: that module only reads
and serializes, this one validates untrusted JSON, mints ids, rewrites references and writes
(`context.md` §"Module placement"). The dependency runs one way only — this module imports the
format literal, both version constants, the exclusion sets and the id-column predicate from
`transfer.py`, and nothing in `transfer.py` imports this one.

Step `001` builds the pure half: the per-granularity table sets, the root-table mapping, the
row deserializer and `validate_envelope`. Step `002` adds the write half: the reference policy,
the remap engine, the payload writer and `import_owned`. Step `003` adds `import_session`, its
sibling session policy and the target-character lookup, reusing that engine and that writer
unchanged; step `004` adds `import_database`, the whole-database replace — the eligibility guard,
the memo-scope-target check, the wipe and the vector-table drop — on top of that same writer, handed
the validated rows unchanged so the export's own ids survive.

**Validation is total and happens before any write** (`context.md` §"The failure contract").
Every refusal is `ExportInvalidError` with one of the five reasons and nothing else on the
wire — no table name, no column, no cell value (R5, `deployment.md`'s redaction rule). The
deserializer is the only thing that can refuse a bad enum string, an id outside the signed
64-bit range or a JSON `1` in a Boolean column: the first two raise at bind time, as a
`StatementError` and an `OverflowError` rather than an `IntegrityError`, and the third is
silently accepted by SQLAlchemy and SQLite.

**It never names a column.** Like 030's serializer, every per-cell decision is read off the
`app.db.schema` Table — its primary key, its foreign keys, its column names, types and
nullability — so a column a later feature adds flows through on its own. Table *sets* are
explicit, except the `database` set, which is derived from `schema.metadata.sorted_tables`.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any, Final, get_args

from sqlalchemy import (
    Boolean,
    Column,
    Connection,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError

from app.db import schema
from app.db.search_tables import MEMO_VEC_TABLE, SESSION_VEC_TABLE, ensure_fts_tables, vector_table_dimension
from app.errors import (
    REASON_MALFORMED_PAYLOAD,
    REASON_NOT_AN_EXPORT,
    REASON_SCHEMA_MISMATCH,
    REASON_UNSUPPORTED_VERSION,
    REASON_WRONG_GRANULARITY,
    CharacterNotFoundError,
    DatabaseNotEmptyError,
    ExportInvalidError,
)
from app.ids import SnowflakeGenerator
from app.roles import Role
from app.services.transfer import (
    DATABASE_EXCLUDED_TABLES,
    ENVELOPE_VERSION,
    EXPORT_FORMAT,
    SCHEMA_VERSION,
    USER_EXCLUDED_COLUMNS,
    ExportGranularity,
    is_id_column,
)

ImportValue = str | int | bool | None
"""One deserialized cell: an id or other integer as `int`, a Boolean as `bool`, text and enum
values as `str`, a null as `None`. The inverse of 030's `JsonScalar`, minus `float`: no column
in `schema.metadata` is a float, so a JSON fraction is refused rather than carried."""

ImportRow = dict[str, ImportValue]
"""One deserialized row — column name to Python value, ready to pass to a Core insert."""

EXPORT_GRANULARITIES: Final[frozenset[ExportGranularity]] = frozenset(get_args(ExportGranularity))
"""The four granularity values at runtime: `database`, `user`, `character`, `session`.

030 declares `ExportGranularity` as a `Literal` type and no runtime constant, so the value set
is read back off the type itself rather than re-typed here — the two cannot drift.
"""

GRANULARITY_TABLES: Final[Mapping[ExportGranularity, frozenset[str]]] = {
    "database": frozenset(table.name for table in schema.metadata.sorted_tables)
    - DATABASE_EXCLUDED_TABLES,
    "user": frozenset(
        {
            schema.users.name,
            schema.characters.name,
            schema.setups.name,
            schema.sessions.name,
            schema.messages.name,
            schema.memos.name,
        }
    ),
    "character": frozenset(
        {
            schema.characters.name,
            schema.setups.name,
            schema.sessions.name,
            schema.messages.name,
            schema.memos.name,
        }
    ),
    "session": frozenset({schema.sessions.name, schema.messages.name, schema.memos.name}),
}
"""The payload key set a granularity's envelope must carry **exactly** — nothing missing, nothing
extra (`context.md` §"Granularity table sets").

The `database` set is **derived**: every `schema.metadata.sorted_tables` table minus 030's
`DATABASE_EXCLUDED_TABLES`, so a table a later feature declares joins the whole-database import
without an edit here. The three roleplayer sets are explicit, because they are a boundary
decision rather than a consequence of the registry, and they mirror 030's exporters table for
table. `llm_servers`, `models`, `auth_sessions` or `translations` in a roleplayer payload makes
the key set wrong, which is `malformed_payload`.
"""

ROOT_TABLES: Final[Mapping[ExportGranularity, str]] = {
    "user": schema.users.name,
    "character": schema.characters.name,
    "session": schema.sessions.name,
}
"""The table that must hold **exactly one** row, per granularity — the envelope's root row.

There is no root header field: the root is that single row (030's `ExportEnvelope` docstring).
`database` has no entry, because a whole-database payload has no root and every table's row
count is free.
"""


@dataclass(frozen=True)
class ValidatedExport:
    """A body that passed every header, payload, row and root check — the pure half's result.

    Carries no raw JSON: `rows` is already deserialized, so steps `002`–`004` never re-parse a
    cell and never see a JSON type. Frozen, because validation is write-free and its result is
    read by the remap engine and the writer without being amended.
    """

    granularity: ExportGranularity
    """The envelope's granularity, already checked against the caller's accepted set."""

    rows: Mapping[str, list[ImportRow]]
    """Table name to its deserialized rows, keys in `schema.metadata.sorted_tables` order and
    rows in the payload's own order. The order is what lets the writer insert parents first."""


def deserialize_row(
    table: Table,
    row: object,
    *,
    allow_missing: Collection[str] = (),
) -> ImportRow:
    """One raw payload row as a mapping of column name to Python value, or `malformed_payload`.

    The inverse of 030's `serialize_row` (`context.md` §"Deserialization"), with the same
    column-agnostic rule: an id column — 030's `is_id_column`, so the two directions cannot
    disagree — takes a decimal-digit string and yields an `int`; a `Boolean` column takes a JSON
    boolean only; an `Enum` column takes a string in its own value set; another `Integer` column
    takes a non-boolean JSON integer; a `String` column takes a string, timestamps included and
    verbatim; and a null is accepted only where the column is nullable.

    The row's key set must equal `table`'s column names minus `allow_missing` — a missing column
    and an extra one are both refused. `allow_missing` is 030's `USER_EXCLUDED_COLUMNS` for the
    `users` row of a `user` envelope, and empty everywhere else.

    Raises `ExportInvalidError(REASON_MALFORMED_PAYLOAD)` for every one of those failures, so
    the caller never learns which column or value was at fault.
    """
    if not isinstance(row, Mapping):
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    omitted = set(allow_missing)
    expected = {column.name for column in table.columns} - omitted
    # Exact equality, so a missing column and an extra one are the same refusal: a row whose
    # shape is not the table's shape cannot be written, and a guessed default would invent data.
    if set(row) != expected:
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    key_names = {column.name for column in table.primary_key.columns}
    return {
        column.name: _deserialize_value(
            column, row[column.name], is_id=is_id_column(column, key_names)
        )
        for column in table.columns
        if column.name not in omitted
    }


def validate_envelope(body: object, accepted: Collection[ExportGranularity]) -> ValidatedExport:
    """Check an untrusted body against `accepted` and deserialize its payload. Writes nothing.

    Pure: it reads no database, opens no transaction and mutates neither `body` nor anything
    else. `accepted` is the granularity set the calling route allows — `{user, character}` for
    `POST /api/import`, `{session}` for the character route, `{database}` for the admin one.

    The order of the checks is fixed and load-bearing (`context.md` §"The failure contract"):
    the first failure decides the reason, so a body with both a wrong `format` and a wrong
    `version` is `not_an_export`.

    1. `not_an_export` — the body is not an object; its key set is not exactly the six header
       keys; `format` is not 030's `EXPORT_FORMAT`; `granularity` is not in
       `EXPORT_GRANULARITIES`.
    2. `unsupported_version` — `version` is not an integer equal to `ENVELOPE_VERSION`.
    3. `schema_mismatch` — `schema_version` is not an integer equal to `SCHEMA_VERSION`.
    4. `wrong_granularity` — the granularity is real but not in `accepted`.
    5. `malformed_payload` — `payload` is not an object; its key set is not
       `GRANULARITY_TABLES[granularity]`; a table's value is not a list; a row fails
       `deserialize_row`; or `ROOT_TABLES[granularity]`'s list does not hold exactly one row.

    References are **not** checked here: whether a `user_id`, a `scope_id` or a `related_to`
    resolves to a payload row is the remap engine's and the database import's business
    (steps `002`–`004`).
    """
    if not isinstance(body, Mapping) or set(body) != _HEADER_KEYS:
        raise ExportInvalidError(REASON_NOT_AN_EXPORT)
    # The format and the granularity share one reason, so they are settled together: both say
    # "this is not one of our files" rather than "this file is one we cannot take".
    granularity = _granularity_of(body[_KEY_GRANULARITY])
    if body[_KEY_FORMAT] != EXPORT_FORMAT or granularity is None:
        raise ExportInvalidError(REASON_NOT_AN_EXPORT)
    if not _is_version(body[_KEY_VERSION], ENVELOPE_VERSION):
        raise ExportInvalidError(REASON_UNSUPPORTED_VERSION)
    if not _is_version(body[_KEY_SCHEMA_VERSION], SCHEMA_VERSION):
        raise ExportInvalidError(REASON_SCHEMA_MISMATCH)
    if granularity not in accepted:
        raise ExportInvalidError(REASON_WRONG_GRANULARITY)
    return ValidatedExport(granularity, _deserialize_payload(body[_KEY_PAYLOAD], granularity))


_MAX_ID: Final[int] = 2**63 - 1
"""The largest id a payload may carry: SQLite's signed 64-bit integer ceiling.

Checked here rather than left to the write, because a larger value raises `OverflowError` at
bind time — a Python error no write phase can translate into a reason (decision 15).
"""

_KEY_FORMAT: Final[str] = "format"
_KEY_VERSION: Final[str] = "version"
_KEY_GRANULARITY: Final[str] = "granularity"
_KEY_CREATED_AT: Final[str] = "created_at"
_KEY_SCHEMA_VERSION: Final[str] = "schema_version"
_KEY_PAYLOAD: Final[str] = "payload"
"""The six header keys of 030's `ExportEnvelope`, as the names a raw body is read by.

`created_at` is only ever part of the key set: its value is informational, so nothing here
inspects it and no import refuses a file over it.
"""

_HEADER_KEYS: Final[frozenset[str]] = frozenset(
    {
        _KEY_FORMAT,
        _KEY_VERSION,
        _KEY_GRANULARITY,
        _KEY_CREATED_AT,
        _KEY_SCHEMA_VERSION,
        _KEY_PAYLOAD,
    }
)
"""The header key set a body must carry **exactly** — one missing or one extra is `not_an_export`.

Strict both ways on purpose: a file with an unknown header key was written by something this
instance does not understand, and ignoring that key would be reading the file as if it were ours.
"""


def _granularity_of(value: object) -> ExportGranularity | None:
    """`value` as one of the four granularities, or `None` when it is not one of them.

    Matched against `EXPORT_GRANULARITIES` rather than cast: the loop both decides the question
    and produces a properly typed granularity, so no raw JSON value is ever carried into
    `ValidatedExport` under a type it has not been checked against.
    """
    for granularity in EXPORT_GRANULARITIES:
        if value == granularity:
            return granularity
    return None


def _is_version(value: object, expected: int) -> bool:
    """Whether `value` is an integer **equal** to `expected`, a boolean not counting as one.

    Equality only, in both directions: a newer file may carry rules this build does not apply and
    an older one rules it no longer applies, so neither can be read safely (`context.md`
    §"The failure contract"). `True` is excluded because `bool` is an `int` subclass and would
    otherwise pass for version 1.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def _deserialize_payload(
    payload: object, granularity: ExportGranularity
) -> dict[str, list[ImportRow]]:
    """A raw `payload` as deserialized rows per table, or `malformed_payload`.

    The key set must be exactly `GRANULARITY_TABLES[granularity]`, every value must be a list and
    every row must pass `deserialize_row`. Tables are walked in `schema.metadata.sorted_tables`
    order, so the result's keys come out in insert order and the walk hands over the `Table` each
    row is checked against. The `users` row of a `user` envelope is the one row allowed to be
    short, by exactly 030's `USER_EXCLUDED_COLUMNS`.

    Last comes the root count: the granularity's root table holds **exactly one** row, that row
    being the envelope's root. `database` has no root, so nothing is counted for it.
    """
    if not isinstance(payload, Mapping) or set(payload) != GRANULARITY_TABLES[granularity]:
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    rows: dict[str, list[ImportRow]] = {}
    for table in schema.metadata.sorted_tables:
        if table.name not in payload:
            continue
        table_rows = payload[table.name]
        if not isinstance(table_rows, list):
            raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
        allow_missing: Collection[str] = (
            USER_EXCLUDED_COLUMNS
            if granularity == "user" and table.name == schema.users.name
            else ()
        )
        rows[table.name] = [
            deserialize_row(table, row, allow_missing=allow_missing) for row in table_rows
        ]
    root = ROOT_TABLES.get(granularity)
    if root is not None and len(rows[root]) != 1:
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    return rows


def _deserialize_value(column: Column[Any], value: object, *, is_id: bool) -> ImportValue:
    """One raw cell as the Python value `column` takes, or `malformed_payload`.

    Arm order mirrors 030's `_serialize_value` exactly, which is what makes the two directions
    inverses. Null first, so a null reference stays null and a null is refused only where the
    column is NOT NULL. Then `Enum`, ahead of every other string arm because `Enum` **subclasses**
    `String`, and its value set is the only thing that can refuse a bad member at all — a write
    raises a `StatementError` wrapping `LookupError` instead (decision 15). Then `Boolean`, which
    takes a JSON boolean and nothing else, because SQLAlchemy and SQLite accept a `1` silently.
    Then an id, as decimal text. Then any other integer, a boolean **not** counting as one. Then
    a string, timestamps included and verbatim.

    A type family the registry does not currently declare — a float, or a JSON structure — falls
    through to the refusal rather than being carried untyped into a write.
    """
    if value is None:
        if column.nullable:
            return None
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    column_type = column.type
    if isinstance(column_type, Enum):
        if isinstance(value, str) and value in column_type.enums:
            return value
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    if isinstance(column_type, Boolean):
        if isinstance(value, bool):
            return value
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    if is_id:
        return _deserialize_id(value)
    if isinstance(column_type, Integer):
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    if isinstance(column_type, String) and isinstance(value, str):
        return value
    raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)


def _deserialize_id(value: object) -> int:
    """One id cell — a string of decimal digits — as an `int` inside the signed 64-bit range.

    The inverse of 030's id rule, which sends every id out as decimal text to keep a snowflake
    JS-safe (`backend-structure.md` §"The JSON id boundary"). A JSON **number** is refused, so a
    file that crossed a JS boundary and lost precision cannot be imported as though it had not.
    Digits and nothing else: a sign, surrounding whitespace, an empty string and a non-ASCII digit
    all fail. The range is checked here because `2**63` raises `OverflowError` at bind time rather
    than any database error a later step could translate.
    """
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    number = int(value)
    if not 0 <= number <= _MAX_ID:
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    return number


_SCOPE_USER: Final[str] = "user"
_SCOPE_CHARACTER: Final[str] = "character"
_SCOPE_SETUP: Final[str] = "setup"
_SCOPE_SESSION: Final[str] = "session"
"""The four `memos.scope` values (one docstring for the group above).

`memos.scope` is the registry's only `Enum` declared with `enum_class=None`, so a stored scope
reads back as a plain `str` and these compare against it directly — no member lookup. 030 keeps
the same three constants privately for its export selections; `user` joins them here, because an
import is the first thing that has to decide what a `scope='user'` memo resolves to.
"""

_MEMO_SCOPE_TABLES: Final[Mapping[str, str]] = {
    _SCOPE_CHARACTER: schema.characters.name,
    _SCOPE_SETUP: schema.setups.name,
    _SCOPE_SESSION: schema.sessions.name,
}
"""Which table a memo's `scope_id` names, per scope.

This is the one reference the registry cannot describe on its own: `memos.scope_id` carries **no**
foreign key (`002.context.md`), so the engine resolves it through the row's `scope` instead of
through `column.foreign_keys`. `_SCOPE_USER` deliberately has **no** entry — a `scope='user'` memo
resolves to the caller rather than to a payload row, the same way `ROOT_TABLES` has no `database`
key.
"""

_USER_MEMO_SCOPES: Final[frozenset[str]] = frozenset(_MEMO_SCOPE_TABLES) | {_SCOPE_USER}
"""The memo scopes a `user` envelope may carry: all four (`context.md` §"Remap rules")."""

_CHARACTER_MEMO_SCOPES: Final[frozenset[str]] = frozenset(_MEMO_SCOPE_TABLES)
"""The memo scopes a `character` envelope may carry: `character`, `setup` and `session`, each
targeting a payload row. A `scope='user'` memo in a character payload is `malformed_payload`: the
account-level notes are not part of a character, and there is no payload `users` row to own them."""

_OWNED_GRANULARITIES: Final[frozenset[ExportGranularity]] = frozenset({"user", "character"})
"""The accepted set `import_owned` validates against — `POST /api/import`'s two granularities
(`context.md` §"Wire contract"). Any other granularity is `wrong_granularity`; `session` belongs to
step `003`'s route and `database` to the admin one."""


@dataclass(frozen=True)
class _ReferencePolicy:
    """What one granularity allows, and how its out-of-payload references resolve.

    The whole purpose of this value is that `_remap_payload` holds **no** granularity `if` chain:
    everything that differs between a `user`, a `character` and (step `003`) a `session` import is
    one of the three fields below, so a new granularity supplies a policy and edits no engine code.

    Everything that is the **same** at every granularity stays in the engine and is deliberately
    not a field: a fresh snowflake for every row, every `users` target becoming the caller, the
    payload `users` row never being written, `memos.scope_id` resolving through
    `_MEMO_SCOPE_TABLES`, and the `(model_server_id, model_name)` pair being kept only when that
    pair exists in this instance's `models`.

    Built per call rather than once per module, because two of the three fields need a value only
    the request knows: the payload user's id, and step `003`'s target character. `_owned_policy`
    builds this step's two.
    """

    allowed_memo_scopes: frozenset[str]
    """The `memos.scope` values this granularity accepts. A payload memo whose scope falls outside
    the set is `malformed_payload`, decided before its `scope_id` is resolved."""

    required_user_id: int | None
    """The **old** user id that every `user_id` column, and every `scope='user'` memo's `scope_id`,
    must equal — or `None` for "any value is accepted".

    `None` does not mean "no substitution": every `user_id` becomes the caller's whatever this field
    holds, and it only turns the equality check off. A `user` envelope sets it to the payload
    `users` row's id, which is the sole use that row has — the row itself is never written, and a
    `characters` row carrying a different `user_id` is `malformed_payload` (`context.md` §"Remap
    rules"). A `character` or `session` envelope carries no `users` row to compare against, so it
    passes `None`.
    """

    column_overrides: Mapping[tuple[str, str], int | None]
    """The out-of-payload references this granularity resolves by decree, keyed by
    `(table name, column name)`.

    A key **present** with an `int` writes that id; present with `None` writes NULL; **absent**
    means the column is remapped the ordinary way. So the engine tests membership (`in`) and never
    truthiness — `None` is a value here, not a miss. Step `003`'s session policy is the first user:
    `{("sessions", "character_id"): <target id>, ("sessions", "setup_id"): None}`. This step's two
    policies pass an empty mapping, because a `user` or `character` payload is self-contained:
    every reference but `user_id` resolves inside it.
    """


@dataclass(frozen=True)
class OwnedImportResult:
    """What a finished `user` or `character` import reports — `POST /api/import`'s whole answer.

    Frozen and id-only: no row content travels back, so the route can serialize it without having
    to choose what to redact (R5).
    """

    granularity: ExportGranularity
    """The envelope's granularity, either `user` or `character` (`_OWNED_GRANULARITIES`)."""

    character_ids: list[int]
    """The **new** ids of every character the import created, ascending. Exactly one entry for a
    `character` envelope; for a `user` envelope one per payload character, and empty when the
    payload carried none (`context.md` §"Wire contract")."""


def import_owned(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    body: object,
) -> OwnedImportResult:
    """Import the caller's own `user` or `character` export under the caller's account.

    `body` is the untrusted request object, typed `object` for the same reason
    `validate_envelope`'s is. `user_id` is the caller's: every row written carries it, whatever
    `user_id` the payload held (R5).

    In order:

    1. `validate_envelope(body, _OWNED_GRANULARITIES)` — pure, and outside the transaction. A
       `session` or `database` envelope is `wrong_granularity` here.
    2. One `with connection.begin():` block holds everything that follows, so a refusal stores
       nothing.
    3. `_owned_policy(validated)` for the granularity's policy.
    4. `_remap_payload(...)` for the fresh ids and the rewritten references.
    5. `_write_payload(connection, ...)` for the inserts and the second self-reference pass.

    **The payload `users` row is never written** and nothing on the caller's account changes: not
    `username`, not `rp_language`, not `preferred_language` (US-136.AC-1). That row's id serves only
    as `_ReferencePolicy.required_user_id`.

    Raises `ExportInvalidError` — `wrong_granularity` for an unaccepted granularity,
    `malformed_payload` for a bad payload or a reference that resolves nowhere.
    """
    validated = validate_envelope(body, _OWNED_GRANULARITIES)
    with connection.begin():
        policy = _owned_policy(validated)
        remapped = _remap_payload(validated, policy, generator, user_id, connection)
        _write_payload(connection, remapped)
    # The ids are read off the engine's own output rather than counted during the write: the writer
    # is handed final rows, so what is reported is exactly what was stored.
    return OwnedImportResult(
        validated.granularity,
        sorted(_row_id(schema.characters, row) for row in remapped.get(schema.characters.name, [])),
    )


def _owned_policy(validated: ValidatedExport) -> _ReferencePolicy:
    """The policy for a `user` or a `character` envelope — the only branch on granularity there is.

    It lives out here rather than inside `_remap_payload` on purpose: the engine stays
    granularity-blind, so step `003` adds a policy of its own instead of an arm to a chain
    (`002.remap-and-owned-import.md` §"Interface intent").

    - `user` → `_USER_MEMO_SCOPES`, `required_user_id` the payload `users` row's id (validation has
      already guaranteed exactly one such row), and no column overrides.
    - `character` → `_CHARACTER_MEMO_SCOPES`, `required_user_id` `None`, and no column overrides.

    `validated.granularity` is one of `_OWNED_GRANULARITIES` whenever `import_owned` calls this.
    """
    if validated.granularity == "user":
        # Validation has already pinned the root count, so the one `users` row is there. Its id is
        # all this granularity takes from it — the row itself is never written.
        payload_user = validated.rows[schema.users.name][0]
        return _ReferencePolicy(
            allowed_memo_scopes=_USER_MEMO_SCOPES,
            required_user_id=_row_id(schema.users, payload_user),
            column_overrides={},
        )
    return _ReferencePolicy(
        allowed_memo_scopes=_CHARACTER_MEMO_SCOPES,
        required_user_id=None,
        column_overrides={},
    )


def _remap_payload(
    validated: ValidatedExport,
    policy: _ReferencePolicy,
    generator: SnowflakeGenerator,
    user_id: int,
    connection: Connection,
) -> dict[str, list[ImportRow]]:
    """Fresh ids and rewritten references — the rows `_write_payload` is to insert, per table.

    The returned mapping's keys are in `schema.metadata.sorted_tables` order, which is the order the
    writer inserts in, and each value is a list of complete `ImportRow`s ready for a Core insert.
    Row order within a table is the payload's.

    `connection` is read **only** for the model-pair lookup below. The engine issues no write and
    opens no transaction of its own, so it runs inside the caller's `with connection.begin():` and
    never goes through `transfer.py`'s `_reading` (`002.context.md` §"Existing names").

    Every per-column decision is read off the `app.db.schema` Table rather than from a list of
    column names:

    - **the primary key** gets a fresh snowflake from `generator`, minted per table in **ascending
      old-id order**, so the monotonic generator preserves relative order and the stream's
      `ORDER BY id` still reads an imported session the way it was exported;
    - **a foreign-key column** resolves through its own `column.foreign_keys`: a `users` target
      becomes `user_id` (the caller), any other target becomes the new id of the payload row it
      names. `messages.related_to` is such a column — a self-FK — and is rewritten here; only its
      two-pass *insert* belongs to the writer;
    - **`memos.scope_id`** carries no foreign key, so it resolves through the row's `scope`:
      `_SCOPE_USER` becomes `user_id`, the other three through `_MEMO_SCOPE_TABLES`. A scope outside
      `policy.allowed_memo_scopes` is refused;
    - **`characters.model_server_id` / `model_name`, and the `sessions` pair**, carry no foreign key
      either: the pair is **kept** when it exists in this instance's `models` (`server_id`,
      `model_name`) and otherwise **both** columns are nulled together, which is what
      `ck_characters_model_both_or_neither` and its sessions counterpart require. This pair is never
      "unresolved" — it is kept or nulled, never refused;
    - **`policy.column_overrides`** wins over all of the above for the `(table, column)` keys it
      holds;
    - **`policy.required_user_id`**, when it is not `None`, is the value every `user_id` and every
      `scope='user'` `scope_id` must already hold;
    - a **null** reference stays null, and every other column is carried across exactly as exported:
      `archived_at`, `created_at`, `updated_at`, `last_used_at`, `settled_at`, `sort_key`, the flags
      and the text.

    **The `users` table is never in the result**, at any granularity this engine serves. A payload
    `users` row is read for its id and then dropped, so the caller's account is untouched.

    Raises `ExportInvalidError(REASON_MALFORMED_PAYLOAD)` for a reference that resolves nowhere — a
    disallowed or unresolvable memo scope, a `user_id` that disagrees with
    `policy.required_user_id`, or a foreign key naming no payload row — and names neither the table,
    the column nor the value (R5).
    """
    known_pairs = _known_model_pairs(connection)
    new_ids = _mint_ids(validated.rows, generator)
    remapped: dict[str, list[ImportRow]] = {}
    for table in schema.metadata.sorted_tables:
        # `users` is dropped unconditionally, at every granularity this engine serves: nothing on
        # the caller's account is ever written (US-136.AC-1).
        if table.name == schema.users.name or table.name not in validated.rows:
            continue
        remapped[table.name] = [
            _remap_row(
                table,
                row,
                policy=policy,
                new_ids=new_ids,
                user_id=user_id,
                known_pairs=known_pairs,
            )
            for row in validated.rows[table.name]
        ]
    return remapped


def _write_payload(connection: Connection, rows: Mapping[str, list[ImportRow]]) -> None:
    """Insert already-final rows, parents first, with self-references set in a second pass.

    Call it **inside** the caller's `with connection.begin():`; it opens no transaction and commits
    nothing, so a later failure rolls its inserts back with everything else.

    `rows` is final: this writer mints nothing, substitutes nothing and resolves nothing, and it
    makes no assumption that ids were remapped at all. That is what lets step `004` hand it a
    `ValidatedExport.rows` unchanged, for a whole-database replace with **preserved** ids, while
    this step hands it `_remap_payload`'s output. A table absent from `rows` is simply not written.

    In order:

    1. 024's `ensure_fts_tables(connection)` (`app.db.search_tables`; the import is the coder's to
       add, since the stub does not use it), before the first insert, so the FTS triggers index
       every row this writer inserts — memo bodies, and record-row message text. A roleplayer import
       writes no `memo_vec` / `session_vec` row and ensures no vector table (U3).
    2. One insert per table, walking `schema.metadata.sorted_tables`, so a parent lands before its
       children. Foreign keys are immediate (`PRAGMA foreign_keys=ON`, nothing deferrable) and this
       writer does **not** toggle that pragma — inside a transaction it would be a no-op
       (`backend-structure.md` §"The FK posture of a rebuild").
    3. The **second pass** for self-referencing foreign-key columns, found from each Table's own
       foreign keys (today only `messages.related_to`): the first-pass insert writes the column
       NULL, then one UPDATE per row that actually carries a reference sets it. Both passes satisfy
       `ck_messages_buried_or_settled` (`related_to IS NULL OR settled_at IS NULL`), because a row
       whose `related_to` is set is buried and so carries a NULL `settled_at`.
    """
    ensure_fts_tables(connection)
    deferred: list[tuple[Table, ImportRow, ImportRow]] = []
    for table in schema.metadata.sorted_tables:
        table_rows = rows.get(table.name)
        if not table_rows:
            continue
        self_references = _self_reference_names(table)
        connection.execute(
            table.insert(),
            [{**row, **{name: None for name in self_references}} for row in table_rows],
        )
        for row in table_rows:
            pending: ImportRow = {
                name: row[name] for name in self_references if row[name] is not None
            }
            if pending:
                deferred.append((table, row, pending))
    # Pass two, inside the same transaction: a buried row's head carries a **higher** id, so the
    # reference cannot be written by the insert that created the row (030 outcome note). A row that
    # carries one is buried, hence has a NULL `settled_at`, so `ck_messages_buried_or_settled`
    # holds at both passes.
    for table, row, pending in deferred:
        key = _primary_key_column(table)
        connection.execute(table.update().where(key == row[key.name]).values(**pending))


_SCOPE_COLUMN: Final[str] = schema.memos.c.scope.name
_SCOPE_ID_COLUMN: Final[str] = schema.memos.c.scope_id.name
"""The two `memos` columns the engine has to name, read off the registry rather than typed.

`memos.scope_id` carries no foreign key, so it is the one reference `column.foreign_keys` cannot
describe: the engine reads the row's `scope` to learn which table the id names
(`002.context.md`).
"""

_MODEL_SERVER_COLUMN: Final[str] = schema.characters.c.model_server_id.name
_MODEL_NAME_COLUMN: Final[str] = schema.characters.c.model_name.name
"""The model-pair column names, likewise read off the registry (`sessions` declares the same two).

A table "carries the pair" only when it declares **both**, which is why `models` — which has a
`model_name` and a `server_id` — is never mistaken for one of them.
"""


def _primary_key_column(table: Table) -> Column[Any]:
    """`table`'s single primary-key column. Every `schema.metadata` table declares exactly one."""
    (key,) = table.primary_key.columns
    return key


def _row_id(table: Table, row: ImportRow) -> int:
    """A row's own primary-key value as an `int`, or `malformed_payload`.

    The deserializer has already turned every id cell into an `int` and refused a null in a NOT
    NULL column, so the refusal here is belt and braces: it keeps the engine's typing honest
    without a cast, and it names neither column nor value (R5).
    """
    value = row[_primary_key_column(table).name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    return value


def _mint_ids(
    rows: Mapping[str, list[ImportRow]], generator: SnowflakeGenerator
) -> dict[str, dict[int, int]]:
    """Old id to fresh snowflake, per table — the whole correspondence the rewrite reads.

    Minted **per table, in ascending old-id order**, walking `schema.metadata.sorted_tables`. The
    generator is monotonic, so rows keep their relative order and the stream's `ORDER BY id` reads
    an imported session exactly as it was exported (`context.md` §"Remap rules"). `users` is left
    out: a `users` target resolves to the caller, never through a map, and that row is never
    written.

    Two rows of one table sharing a primary key would collapse into one entry and then be inserted
    twice under one id, so the count is checked and a repeat is `malformed_payload`.
    """
    minted: dict[str, dict[int, int]] = {}
    for table in schema.metadata.sorted_tables:
        if table.name == schema.users.name or table.name not in rows:
            continue
        old_ids = sorted(_row_id(table, row) for row in rows[table.name])
        table_ids = {old_id: generator.next_id() for old_id in old_ids}
        if len(table_ids) != len(old_ids):
            raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
        minted[table.name] = table_ids
    return minted


def _known_model_pairs(connection: Connection) -> frozenset[tuple[int, str]]:
    """Every `(server_id, model_name)` pair this instance's `models` table holds.

    The engine's **one** read, and it runs inside the caller's `with connection.begin():` — no
    `_reading`, no second transaction (`002.context.md` §"Existing names"). One read of the whole
    registry rather than a query per row: `models` holds one row per model an administrator has
    registered, and the pair is checked for every imported character and session.
    """
    statement = select(schema.models.c.server_id, schema.models.c.model_name)
    return frozenset(
        (row.server_id, row.model_name) for row in connection.execute(statement).all()
    )


def _remap_row(
    table: Table,
    row: ImportRow,
    *,
    policy: _ReferencePolicy,
    new_ids: Mapping[str, Mapping[int, int]],
    user_id: int,
    known_pairs: frozenset[tuple[int, str]],
) -> ImportRow:
    """One payload row with a fresh id and every reference rewritten, or `malformed_payload`.

    The arms are tried in this order, and that order is the policy's whole power:

    1. `policy.column_overrides` — membership, never truthiness, so a present `None` writes NULL;
    2. the primary key — the fresh snowflake `_mint_ids` already minted;
    3. a foreign-key column — resolved through its own `column.foreign_keys`;
    4. `memos.scope_id` — resolved through the row's `scope`, the one reference the registry
       cannot describe;
    5. the model pair — kept whole or nulled whole;
    6. anything else — carried across exactly as exported: the flags, the text, `sort_key` and
       every timestamp, `archived_at` and `settled_at` included.
    """
    scope = _memo_scope(table, row, policy)
    keeps_pair = _keeps_model_pair(table, row, known_pairs)
    key_name = _primary_key_column(table).name
    remapped: ImportRow = {}
    for column in table.columns:
        name = column.name
        value = row[name]
        if (table.name, name) in policy.column_overrides:
            remapped[name] = policy.column_overrides[(table.name, name)]
        elif name == key_name:
            remapped[name] = new_ids[table.name][_row_id(table, row)]
        elif column.foreign_keys:
            remapped[name] = _resolve_foreign_key(
                column, value, policy=policy, new_ids=new_ids, user_id=user_id
            )
        elif scope is not None and name == _SCOPE_ID_COLUMN:
            remapped[name] = _resolve_scope_id(
                scope, value, policy=policy, new_ids=new_ids, user_id=user_id
            )
        elif _carries_model_pair(table) and name in (_MODEL_SERVER_COLUMN, _MODEL_NAME_COLUMN):
            remapped[name] = value if keeps_pair else None
        else:
            remapped[name] = value
    return remapped


def _memo_scope(table: Table, row: ImportRow, policy: _ReferencePolicy) -> str | None:
    """A `memos` row's allowed scope, or `None` for a row of any other table.

    Decided **before** `scope_id` is resolved, so a scope this granularity does not allow is
    refused on its own terms: a `scope='user'` memo in a character payload is `malformed_payload`
    whatever its `scope_id` holds (`context.md` §"Allowed memo scopes").
    """
    if table.name != schema.memos.name:
        return None
    scope = row[_SCOPE_COLUMN]
    if not isinstance(scope, str) or scope not in policy.allowed_memo_scopes:
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    return scope


def _resolve_foreign_key(
    column: Column[Any],
    value: ImportValue,
    *,
    policy: _ReferencePolicy,
    new_ids: Mapping[str, Mapping[int, int]],
    user_id: int,
) -> ImportValue:
    """One foreign-key cell rewritten: to the caller for a `users` target, else to the new id.

    The target is read off the column's own foreign key, so `messages.related_to` — a self-FK —
    needs no special case here; only its two-pass *insert* is the writer's business. A null stays
    null, and a target the payload does not carry is `malformed_payload`.
    """
    target = _target_table_name(next(iter(column.foreign_keys)))
    if target == schema.users.name:
        return _resolve_user_reference(value, policy=policy, user_id=user_id)
    if value is None:
        return None
    return _resolve_new_id(new_ids.get(target, {}), value)


def _resolve_user_reference(
    value: ImportValue, *, policy: _ReferencePolicy, user_id: int
) -> ImportValue:
    """An out-of-payload user reference: the caller's id, once `policy` is satisfied.

    Shared by every `user_id` column and by a `scope='user'` memo's `scope_id`, which is exactly
    the pair `_ReferencePolicy.required_user_id` governs. When that field holds an id the payload
    value must equal it; when it is `None` any value is accepted. **Either way the caller's id is
    what gets written** (R5) — the field turns off the equality check and nothing else.
    """
    if value is None:
        return None
    if policy.required_user_id is not None and value != policy.required_user_id:
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    return user_id


def _resolve_scope_id(
    scope: str,
    value: ImportValue,
    *,
    policy: _ReferencePolicy,
    new_ids: Mapping[str, Mapping[int, int]],
    user_id: int,
) -> ImportValue:
    """A memo's `scope_id` rewritten by its scope: the caller for `user`, else the new row's id."""
    if scope == _SCOPE_USER:
        return _resolve_user_reference(value, policy=policy, user_id=user_id)
    target = _MEMO_SCOPE_TABLES.get(scope)
    if target is None or value is None:
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    return _resolve_new_id(new_ids.get(target, {}), value)


def _resolve_new_id(table_ids: Mapping[int, int], value: ImportValue) -> int:
    """The new id of the row `value` names, or `malformed_payload` when it names none.

    The refusal carries neither the table, the column nor the id it failed on (R5): the caller
    learns only that the payload references something the payload does not contain.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    new_id = table_ids.get(value)
    if new_id is None:
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
    return new_id


def _carries_model_pair(table: Table) -> bool:
    """Whether `table` declares both model-pair columns — true for `characters` and `sessions`."""
    return _MODEL_SERVER_COLUMN in table.columns and _MODEL_NAME_COLUMN in table.columns


def _keeps_model_pair(
    table: Table, row: ImportRow, known_pairs: frozenset[tuple[int, str]]
) -> bool:
    """Whether this row's `(model_server_id, model_name)` pair survives the import.

    Kept only when that exact pair exists in this instance's `models`; otherwise **both** columns
    are nulled, which is what `ck_characters_model_both_or_neither` and its `sessions` counterpart
    require. `model_server_id` carries no foreign key, so the pair is never "unresolved" — it is
    kept or nulled, and no row is ever refused over it (`002.context.md`).
    """
    if not _carries_model_pair(table):
        return False
    server_id = row[_MODEL_SERVER_COLUMN]
    model_name = row[_MODEL_NAME_COLUMN]
    if not isinstance(server_id, int) or not isinstance(model_name, str):
        return False
    return (server_id, model_name) in known_pairs


def _self_reference_names(table: Table) -> list[str]:
    """`table`'s own self-referencing foreign-key columns — today only `messages.related_to`.

    Read off the registry, so a self-reference a later feature declares is two-passed without an
    edit here.
    """
    return [
        column.name
        for column in table.columns
        if any(
            _target_table_name(foreign_key) == table.name for foreign_key in column.foreign_keys
        )
    ]


def _target_table_name(foreign_key: ForeignKey) -> str:
    """The name of the table a foreign key points at."""
    return str(foreign_key.column.table.name)


_SESSION_MEMO_SCOPES: Final[frozenset[str]] = frozenset({_SCOPE_SESSION})
"""The memo scopes a `session` envelope may carry: `session` only (`context.md` §"Remap rules").

A `character`, `setup` or `user` memo in a session payload is `malformed_payload` — 030's
`export_session` emits none of them (US-081.AC-1), so a file carrying one did not come from an
export. **"The target must be the payload session" needs no field of its own**: `_SCOPE_SESSION`
resolves through `_MEMO_SCOPE_TABLES` to `sessions`, and a validated `session` payload holds
exactly one `sessions` row (`ROOT_TABLES`), so the only `scope_id` that resolves at all is that
session's — any other id already fails the engine's ordinary "resolves to no payload row" check.
"""

_SESSION_GRANULARITIES: Final[frozenset[ExportGranularity]] = frozenset({"session"})
"""The accepted set `import_session` validates against — `POST /api/characters/{character_id}/import`'s
single granularity (`context.md` §"Wire contract"). A `user`, `character` or `database` envelope given
to this entry point is `wrong_granularity`, decided by step `001`'s checker before any lookup."""


def import_session(
    connection: Connection,
    generator: SnowflakeGenerator,
    user_id: int,
    character_id: int,
    body: object,
) -> int:
    """Import a `session` export under the caller's character `character_id`. Returns its new id.

    `body` is the untrusted request object, typed `object` for the same reason
    `validate_envelope`'s and `import_owned`'s are. `user_id` is the caller's and is written on
    every row whatever the payload held; `character_id` is the character the roleplayer chose
    (U1), and the imported session lands under it rather than under the exported session's own
    character (US-082.AC-1).

    The order is fixed and load-bearing (`003.context.md` §"Order of checks"):

    1. `validate_envelope(body, _SESSION_GRANULARITIES)` — pure, and **outside** the transaction,
       so a wrong granularity or a `schema_version` mismatch is refused before the target is ever
       looked at, even when that target is foreign or missing.
    2. One `with connection.begin():` block holds everything that follows, so a refusal stores
       nothing.
    3. `_require_owned_character(connection, user_id, character_id)` — the target lookup.
    4. `_session_policy(character_id)` for the policy.
    5. `_remap_payload(...)` for the fresh ids and the rewritten references.
    6. `_write_payload(connection, ...)` for the inserts and the second self-reference pass.

    It returns the **new** id of the one `sessions` row, which is `_remap_payload`'s output for
    that table — step `005`'s response model serializes it as a `SnowflakeOut` decimal string.

    `services.sessions.start_session` is deliberately **not** reused: it mints a session *and*
    seeds a zone message, while an import inserts the rows exactly as exported — every message
    (settled, buried and current-zone) in its exported order, and `archived_at`, `last_used_at`,
    `rp_language`, `preferred_language` and `system_prompt` verbatim (`003.context.md`).

    Raises `ExportInvalidError` — `wrong_granularity` for any other granularity,
    `malformed_payload` for a bad payload, a disallowed memo scope or a reference that resolves
    nowhere — and `CharacterNotFoundError` for a target the caller does not own.
    """
    # Outside the transaction, and first: a wrong granularity or a `schema_version` mismatch is
    # refused before the target is read, so a foreign or missing character cannot mask it (DoD-9).
    validated = validate_envelope(body, _SESSION_GRANULARITIES)
    with connection.begin():
        _require_owned_character(connection, user_id, character_id)
        policy = _session_policy(character_id)
        remapped = _remap_payload(validated, policy, generator, user_id, connection)
        _write_payload(connection, remapped)
    # Validation has already pinned the root count, so the one `sessions` row is there, and its id
    # is read off the engine's own output: what is reported is exactly what was stored.
    return _row_id(schema.sessions, remapped[schema.sessions.name][0])


def _session_policy(character_id: int) -> _ReferencePolicy:
    """The policy for a `session` envelope — `_owned_policy`'s sibling, not an arm inside it.

    It is a sibling by design: `_owned_policy` holds this module's only branch on granularity, and
    a new granularity is meant to add a policy of its own rather than an arm to that chain
    (`002.remap-and-owned-import.md` §"Interface intent"). It takes only `character_id`, because
    unlike `_owned_policy` nothing here is read off the payload — a session policy is fully
    determined by the chosen target.

    The four session rules map onto `_ReferencePolicy`'s three frozen fields like this:

    - **only session-scoped memos, targeting the payload session** → `allowed_memo_scopes`
      `_SESSION_MEMO_SCOPES`. The "targeting the payload session" half is the engine's ordinary
      reference check, not a field (see that constant's docstring).
    - **every `user_id` becomes the caller, accepting any payload value** → `required_user_id`
      `None`. A session payload carries no `users` row to compare against, so there is nothing to
      require; `None` turns off the equality check **only**, and the engine still writes the
      caller's id on every row.
    - **`sessions.character_id` becomes the target** → `column_overrides`
      `(schema.sessions.name, "character_id") -> character_id`.
    - **`sessions.setup_id` becomes null** → the same mapping,
      `(schema.sessions.name, "setup_id") -> None`. The engine tests membership, so a present
      `None` writes NULL instead of remapping — which is why no setup row and no setup-scoped memo
      can ever come along (US-082.AC-2).

    - **the model pair follows the shared rule** → no field at all: `_remap_payload` keeps
      `(model_server_id, model_name)` only when that pair exists in this instance's `models` and
      otherwise nulls both, at every granularity.
    """
    return _ReferencePolicy(
        allowed_memo_scopes=_SESSION_MEMO_SCOPES,
        required_user_id=None,
        # Both keys are **present**: the engine tests membership, so `character_id` is written by
        # decree and `setup_id` is written NULL rather than remapped.
        column_overrides={
            (schema.sessions.name, schema.sessions.c.character_id.name): character_id,
            (schema.sessions.name, schema.sessions.c.setup_id.name): None,
        },
    )


def _require_owned_character(connection: Connection, user_id: int, character_id: int) -> None:
    """Assert the caller owns `character_id`, archived or not. Returns nothing; raises or passes.

    A direct `select` on `characters` filtered on **both** `id` and `user_id` — the scoping is in
    the query itself, so no foreign row is ever read (R5). It deliberately does **not** reuse
    `services.characters`' getter: that one may filter archived rows out, while R6 requires an
    archived target to accept the import (`003.context.md`). 030's `export_character` made the
    same choice for its export root.

    Called **inside** `import_session`'s `with connection.begin():`, after validation: it opens no
    transaction, writes nothing and toggles no pragma.

    Raises `CharacterNotFoundError` (`character_not_found`, 404, empty `detail`) when no such row
    exists. A missing id and another user's id are indistinguishable, and there is no 403. The
    import class is the coder's to add: `from app.errors import CharacterNotFoundError`, alongside
    the `select` this stub does not yet issue.
    """
    statement = select(schema.characters.c.id).where(
        schema.characters.c.id == character_id,
        schema.characters.c.user_id == user_id,
    )
    # No `archived_at` term: R6 takes an archived target, which is why `services.characters`' getter
    # is not reused.
    if connection.execute(statement).first() is None:
        raise CharacterNotFoundError()


_DATABASE_GRANULARITIES: Final[frozenset[ExportGranularity]] = frozenset({"database"})
"""The accepted set `import_database` validates against — `POST /api/admin/database/import`'s single
granularity (`context.md` §"Wire contract"). A `user`, `character` or `session` envelope given to this
entry point is `wrong_granularity`, decided by step `001`'s checker. `_OWNED_GRANULARITIES` and
`_SESSION_GRANULARITIES` are untouched: each entry point states its own set."""

_DATABASE_MEMO_SCOPE_TABLES: Final[Mapping[str, str]] = {
    **_MEMO_SCOPE_TABLES,
    _SCOPE_USER: schema.users.name,
}
"""Every memo scope to the payload table its `scope_id` must name, for a **whole-database** payload.

Step `002`'s `_MEMO_SCOPE_TABLES` has no `user` key on purpose: at the roleplayer granularities a
`scope='user'` memo resolves to the *caller*, not to a payload row. A database payload is the one
case where it resolves inside the payload, because the payload carries the `users` rows themselves
and their ids are preserved. So this map is `_MEMO_SCOPE_TABLES` plus that fourth entry, built from
it rather than beside it — a scope a later feature adds flows through both. All four keys are
present: `{'user': 'users', 'character': 'characters', 'setup': 'setups', 'session': 'sessions'}`.
"""

_VECTOR_TABLES: Final[tuple[str, ...]] = (MEMO_VEC_TABLE, SESSION_VEC_TABLE)
"""024's two `vec0` tables, by the name constants `app.db.search_tables` declares.

Naming them once, from 024's constants, is what keeps the `DROP` in `_drop_vector_tables` free of
any string that could come from a payload. They live outside `schema.metadata`, so the wipe's
registry walk never reaches them.
"""


def import_database(connection: Connection, body: object) -> None:
    """Replace the whole database with a `database` export, keeping the export's own ids.

    Feature `031` step `004`, the import half of 030's `export_database` (US-077.AC-2, UC-061). It
    takes **no request user and no generator**: nothing about it depends on who asked, which is what
    lets the later bootstrap restore (`fast/003`) call it on an instance that has no accounts at all.
    It returns nothing — the caller's only question is whether it raised.

    One `with connection.begin():` block holds every phase, so a refusal of any kind stores nothing
    and the instance is exactly as it was. The phases themselves live in
    `import_database_in_transaction`, which this function calls inside that block; its second caller
    is `app.services.bootstrap.restore_from_export` (`fast/003`), which runs schema creation and the
    import in its own single transaction. In this order (`004.database-replace.md`):

    1. **The eligibility guard, first** — `_require_replaceable_database(connection)`. An ineligible
       instance answers `DatabaseNotEmptyError` whatever the file holds (DoD-5), so the guard runs
       *before* validation. Validation is pure, so paying for it after costs nothing.
    2. **Validation** — step `001`'s `validate_envelope(body, _DATABASE_GRANULARITIES)`.
    3. **The scope-target check** — `_require_memo_scope_targets(validated.rows)`.
    4. **Ensure FTS** — 024's `ensure_fts_tables(connection)`, **before** the wipe. That covers both
       cases at once: tables that already existed have their old entries removed by the wipe's delete
       triggers, and tables that did not exist are created, back-filled from the rows that are about
       to be wiped, and then emptied by those same triggers. The FTS tables are never dropped, and
       their insert triggers index everything phase 6 writes (DoD-9).
    5. **The wipe** — `_wipe_registry_rows(connection)`, then `_drop_vector_tables(connection)`.
    6. **The insert, with ids preserved** — `_write_payload(connection, validated.rows)`, handed the
       validated rows **unchanged**. There is no identity policy value and no second writer: step
       `002`'s writer already takes final rows and assumes no minting happened, so "an identity
       remap" *is* passing `validated.rows` straight through. `_remap_payload` mints
       unconditionally and is deliberately **not** on this path. The two-pass self-reference is the
       writer's own, so a buried message keeps its `related_to` head id (DoD-10).
    7. **The constraint translation** — the insert, and only the insert, runs under
       `except IntegrityError`, re-raised as `ExportInvalidError(REASON_MALFORMED_PAYLOAD)` so the
       `with` block exits by exception and rolls back whole (DoD-6, DoD-11). That covers the FK,
       UNIQUE and CHECK refusals and nothing else: a bad enum string raises `StatementError`
       wrapping `LookupError`, an id above `2**63 - 1` raises `OverflowError` at bind time, and a
       JSON `1` in a Boolean column is silently accepted — all three are the deserializer's job,
       before any write. The driver's text reaches neither the error nor a log line (R5).

    Every column is written as exported, including `users.password_hash`, `users.role`,
    `llm_servers.api_key_ref`, `models.is_embedding_designated` and `models.embedding_dim`, so a
    restored password verifies through `services/passwords.py` unchanged (DoD-2). `auth_sessions`
    and `translations` are in 030's `DATABASE_EXCLUDED_TABLES`, so they are wiped and never
    re-filled: after a successful replace the importing admin's own session is gone, and step `005`'s
    route clears the cookie.

    It deviates deliberately from `data-model.md`'s "mint unconditionally" import policy, which was
    written for the roleplayer granularities (US-136); `outcome.md` records the deviation.

    Raises `DatabaseNotEmptyError` (409, empty `detail`) and `ExportInvalidError` —
    `wrong_granularity` for any other granularity, `malformed_payload` for a bad payload, a memo
    scope target that is absent, or a row the database itself refuses.

    The imports the coder adds for this phase, unused by the stub (`ruff` rejects an unused import,
    as recorded for steps `001`-`003`): `ensure_fts_tables` from `app.db.search_tables`,
    `ExportInvalidError` and `REASON_MALFORMED_PAYLOAD` from `app.errors`, and `IntegrityError` from
    `sqlalchemy.exc`.
    """
    with connection.begin():
        import_database_in_transaction(connection, body)


def import_database_in_transaction(connection: Connection, body: object) -> None:
    """Replace the whole database with a `database` export, inside the caller's open transaction.

    Services-layer only: the in-transaction body of `import_database`, extracted so that
    `app.services.bootstrap.restore_from_export` (`fast/003`) can run schema creation and the
    whole-database import in **one** transaction. `connection` must already be inside a
    transaction; this function never calls `begin()` and never commits.

    Runs exactly `import_database`'s sequence: `_require_replaceable_database` ->
    `validate_envelope(body, _DATABASE_GRANULARITIES)` -> `_require_memo_scope_targets` ->
    `ensure_fts_tables` -> `_wipe_registry_rows` -> `_drop_vector_tables` -> `_write_payload`, with
    the `IntegrityError` -> `ExportInvalidError(REASON_MALFORMED_PAYLOAD)` translation. Returns
    nothing; raises `DatabaseNotEmptyError` or `ExportInvalidError` exactly as `import_database` does.
    """
    # The guard is first on purpose: an instance that may not be replaced answers
    # `database_not_empty` whatever the file holds (DoD-5).
    _require_replaceable_database(connection)
    validated = validate_envelope(body, _DATABASE_GRANULARITIES)
    _require_memo_scope_targets(validated.rows)
    # Before the wipe, so the delete triggers clear whatever the FTS tables hold — whether they
    # existed already or were just created and back-filled from the rows about to go (DoD-9).
    ensure_fts_tables(connection)
    _wipe_registry_rows(connection)
    _drop_vector_tables(connection)
    try:
        # The identity path: the validated rows, unchanged. The writer mints nothing, so the
        # export's own ids survive (ruling 22) — no policy value and no second writer.
        _write_payload(connection, validated.rows)
    except IntegrityError as refusal:
        # FK, UNIQUE and CHECK only. The driver's text goes nowhere: no log line, and the error
        # carries exactly `{"reason": "malformed_payload"}` (R5, DoD-11). Raising here leaves the
        # `with` block by exception, so the wipe and the drop roll back with the inserts.
        raise ExportInvalidError(REASON_MALFORMED_PAYLOAD) from refusal


def _require_replaceable_database(connection: Connection) -> None:
    """Assert the instance may be replaced. Returns nothing; raises or passes.

    Allowed in exactly two states (U2, `004.context.md`):

    - `users` holds **no** row — the bootstrap path `fast/003` will use (DoD-3);
    - `users` holds **exactly one** row, whose `role` is the admin member of `app.roles.Role` —
      the importing administrator, who is about to replace themselves (DoD-1).

    Anything else — two rows whatever their roles, or one row that is a roleplayer — raises
    `DatabaseNotEmptyError` and nothing is touched (DoD-4). It reads `role` **as stored** and
    compares it against `Role.ADMIN`, the way `services/bootstrap.py` does; it does not re-derive a
    role from anything else.

    Called **first** inside `import_database`'s `with connection.begin():`, before validation, so an
    ineligible instance answers `database_not_empty` even for a malformed file (DoD-5). It reads
    only, writes nothing and toggles no pragma.

    The imports the coder adds, unused by the stub: `DatabaseNotEmptyError` from `app.errors` and
    `Role` from `app.roles`, alongside the `select` this stub does not yet issue.
    """
    # Two rows are enough to decide: anything past the second changes nothing.
    roles: list[Any] = list(connection.execute(select(schema.users.c.role).limit(2)).scalars())
    if not roles:
        return
    if len(roles) == 1 and roles[0] == Role.ADMIN:
        return
    raise DatabaseNotEmptyError()


def _require_memo_scope_targets(rows: Mapping[str, list[ImportRow]]) -> None:
    """Assert every memo's `(scope, scope_id)` names a row in the payload. Raises or passes.

    `memos.scope_id` carries no foreign key — it cannot express itself in the registry — so nothing
    the database does on insert would catch a memo pointing at an absent target. This check is the
    only thing that does, and it runs **before** the wipe, so a bad file never reaches a DELETE.

    `rows` is `ValidatedExport.rows`: already deserialized, so a `scope` is a plain `str` (step
    `002`'s decision 13) and a `scope_id` is an `int` or `None`. Each scope resolves through
    `_DATABASE_MEMO_SCOPE_TABLES` — `user` to a payload `users` id, the other three to a row of
    their own table — and the ids compared against are the payload's own, because this granularity
    preserves them. A miss raises `ExportInvalidError(REASON_MALFORMED_PAYLOAD)`, naming neither the
    scope, the table nor the id (R5; DoD-6's third case).

    It takes rows rather than the whole `ValidatedExport` because nothing here is
    granularity-dependent: the whole-database payload is the only one that reaches it, and there is
    nothing left in the envelope header to consult. Pure — no connection, no read, no write.

    The imports the coder adds, unused by the stub: `ExportInvalidError` and
    `REASON_MALFORMED_PAYLOAD` from `app.errors`.
    """
    memo_rows = rows.get(schema.memos.name)
    if not memo_rows:
        return
    # The payload's own ids, per table, because this granularity preserves them.
    payload_ids: dict[str, set[int]] = {
        table.name: {_row_id(table, row) for row in rows[table.name]}
        for table in schema.metadata.sorted_tables
        if table.name in rows
    }
    for row in memo_rows:
        scope = row[_SCOPE_COLUMN]
        target = _DATABASE_MEMO_SCOPE_TABLES.get(scope) if isinstance(scope, str) else None
        scope_id = row[_SCOPE_ID_COLUMN]
        if target is None or not isinstance(scope_id, int) or isinstance(scope_id, bool):
            raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)
        if scope_id not in payload_ids.get(target, set()):
            raise ExportInvalidError(REASON_MALFORMED_PAYLOAD)


def _wipe_registry_rows(connection: Connection) -> None:
    """Delete every row of every `schema.metadata` table, children before parents.

    One DELETE per table, walking `schema.metadata.sorted_tables` in **reverse**, which is
    `translations, messages, sessions, setups, models, memos, characters, auth_sessions, users,
    llm_servers`. That order puts every child ahead of its parent, so no FK is ever left dangling
    mid-wipe — including `translations`, which no payload carries and which is therefore wiped and
    not restored.

    One `DELETE FROM messages` is safe despite the self-reference, because SQLite checks an immediate
    foreign key at the **end** of the statement, by which point every row is gone.

    It does **not** toggle `PRAGMA foreign_keys`. FKs stay on through the wipe and the insert, and
    that is exactly what turns a dangling payload reference into an `IntegrityError` and so into a
    `malformed_payload` refusal (`004.context.md`). Called inside `import_database`'s
    `with connection.begin():`, after `ensure_fts_tables`, so the FTS delete triggers remove the old
    entries as the rows go.

    The import the coder adds, unused by the stub: `delete` from `sqlalchemy`, or each Table's own
    `.delete()`.
    """
    for table in reversed(schema.metadata.sorted_tables):
        connection.execute(table.delete())


def _drop_vector_tables(connection: Connection) -> None:
    """Drop `memo_vec` and `session_vec`, each only if it is there. The wipe's second half.

    They are **dropped, not cleared** (orchestrator decision, `004.context.md`): a `vec0` table's
    declared dimension is the *previous* designation's, and 024's ensure-on-write re-creates both at
    the then-designated model's `embedding_dim` on the next qualifying write. Dropping them is what
    stops a restored instance reporting `dimension_mismatch` purely because the restored designation
    has a different dimension (DoD-12). Nothing is lost: restored memos and sessions have no vectors
    until the administrator's rebuild (`fast/002`) either way (U3).

    Each name comes from `_VECTOR_TABLES`, i.e. from 024's own constants, and the statement goes
    through `text()`. **No value from the payload ever reaches it.** Presence is decided by 024's
    `vector_table_dimension(connection, name)` — `None` means absent, and an absent table is skipped
    rather than dropped with `IF EXISTS`, so "they did not exist before" is a no-op (DoD-8). Dropping
    a `vec0` virtual table takes its shadow tables with it.

    DDL is transactional (`backend-structure.md` §"Transactional DDL"), so a failed import leaves
    both tables, their rows and their original dimension exactly as they were — the drop rolls back
    with everything else.

    The imports the coder adds, unused by the stub: `text` from `sqlalchemy` and
    `vector_table_dimension` from `app.db.search_tables`.
    """
    for table_name in _VECTOR_TABLES:
        if vector_table_dimension(connection, table_name) is None:
            continue
        # `table_name` is one of 024's two constants, never a payload value, so the interpolation
        # cannot carry anything untrusted into the statement.
        connection.execute(text(f"DROP TABLE {table_name}"))
