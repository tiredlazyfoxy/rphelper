"""Tests for step 001 of feature 007 — the drift report's value types and the two shape readers.

Step file: ``docs/plans/007.schema-drift-and-remediation/001.drift-value-types-and-shape-readers.md``.
Feature context: ``context.md`` D1 (compared set, normalisation, implicit indexes), D2 (three
statuses, no ``seed-missing``), R5 (no counts).

Every database test runs against a real ``.sqlite`` file from the ``db_engine`` fixture, never
``:memory:`` and never a mock: what is under test is what SQLite's own pragmas report. Tables
are purpose-made ``MetaData`` / ``Table`` objects, plus the real registry's ``users`` table where
the step context names its properties (DoD-4, DoD-6).
"""

import ast
import dataclasses
import inspect
import re
from collections.abc import Iterator
from enum import StrEnum
from typing import Any

import pytest
from sqlalchemy import (
    BigInteger,
    Column,
    Connection,
    Engine,
    Enum,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.types import UserDefinedType

from app.db import drift as drift_module
from app.db import schema
from app.db.drift import (
    ColumnShape,
    DriftReport,
    IndexShape,
    TableReport,
    TableShape,
    TableStatus,
    normalize_type_text,
    read_declared_shape,
    read_live_shape,
)

# --------------------------------------------------------------------------- helpers


def _create(engine: Engine, *tables: Table) -> None:
    """Create exactly ``tables`` on the per-test SQLite file, in one committed transaction."""
    with engine.connect() as conn:
        with conn.begin():
            for table in tables:
                table.create(conn)


def _live(engine: Engine, table_name: str) -> TableShape | None:
    with engine.connect() as conn:
        return read_live_shape(conn, table_name)


def _by_name(shape: TableShape) -> dict[str, ColumnShape]:
    return {column.name: column for column in shape.columns}


class Mood(StrEnum):
    CALM = "calm"
    ANGRY = "angry"


def _plain_table(metadata: MetaData, name: str = "notes") -> Table:
    """A purpose-made table with a spread of types and nullabilities and no index."""
    return Table(
        name,
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("name", Text, nullable=False),
        Column("note", Text, nullable=True),
        Column("score", Integer, nullable=True),
        Column("label", String(50), nullable=False),
    )


EXPECTED_PLAIN_COLUMNS = (
    ColumnShape(name="id", type_text="INTEGER", not_null=True),
    ColumnShape(name="name", type_text="TEXT", not_null=True),
    ColumnShape(name="note", type_text="TEXT", not_null=False),
    ColumnShape(name="score", type_text="INTEGER", not_null=False),
    ColumnShape(name="label", type_text="VARCHAR(50)", not_null=True),
)


# =========================================================================== DoD-1


def test_status_set_has_exactly_in_sync_missing_and_drifted__DoD1() -> None:
    """DoD-1 — the status value set has exactly three members: in sync, missing, drifted.

    Step 001 DoD-1 (US-017.AC-1; context.md D2).
    """
    members = list(TableStatus)
    assert len(members) == 3
    assert {member.value for member in members} == {"in_sync", "missing", "drifted"}
    assert TableStatus.IN_SYNC.value == "in_sync"
    assert TableStatus.MISSING.value == "missing"
    assert TableStatus.DRIFTED.value == "drifted"


def test_status_set_has_no_seed_missing_member__DoD1() -> None:
    """DoD-1 — no member named or meaning ``seed-missing`` (context.md D2 declines it).

    Step 001 DoD-1.
    """
    for member in TableStatus:
        assert "seed" not in member.name.lower()
        assert "seed" not in member.value.lower()
    assert "SEED_MISSING" not in TableStatus.__members__


# =========================================================================== DoD-2


def test_live_reader_reports_name_type_and_not_null_per_column__DoD2(db_engine: Engine) -> None:
    """DoD-2 — the live reader returns each column's name, normalised type text and NOT NULL flag
    for a table created from a ``Table`` on a real SQLite file.

    Step 001 DoD-2 (UC-014; context.md D1).
    """
    table = _plain_table(MetaData())
    _create(db_engine, table)

    shape = _live(db_engine, "notes")

    assert shape is not None
    assert shape.columns == EXPECTED_PLAIN_COLUMNS


def test_live_reader_reports_no_index_for_a_table_without_one__DoD2(db_engine: Engine) -> None:
    """DoD-2 — a table created with no index reports an empty index set alongside its columns.

    Step 001 DoD-2 (the shape is the column shapes and the index shapes together).
    """
    table = _plain_table(MetaData())
    _create(db_engine, table)

    shape = _live(db_engine, "notes")

    assert shape is not None
    assert shape.indexes == frozenset()


# =========================================================================== DoD-3


def test_declared_reader_returns_the_expected_columns_without_a_database__DoD3() -> None:
    """DoD-3 — the declared reader answers from the ``Table`` object alone; no engine exists here.

    Step 001 DoD-3 (UC-014; context.md D1).
    """
    table = _plain_table(MetaData())

    shape = read_declared_shape(table)

    assert shape.columns == EXPECTED_PLAIN_COLUMNS
    assert shape.indexes == frozenset()


def test_fresh_table_compares_identical_on_both_readers__DoD3(db_engine: Engine) -> None:
    """DoD-3 — a table freshly created from a ``Table`` compares identical, field for field, on
    both sides.

    Step 001 DoD-3.
    """
    table = _plain_table(MetaData())
    declared = read_declared_shape(table)
    _create(db_engine, table)

    live = _live(db_engine, "notes")

    assert live is not None
    assert live.columns == declared.columns
    for live_column, declared_column in zip(live.columns, declared.columns, strict=True):
        assert live_column.name == declared_column.name
        assert live_column.type_text == declared_column.type_text
        assert live_column.not_null == declared_column.not_null


def test_every_registry_table_compares_identical_when_created_fresh__DoD3(db_engine: Engine) -> None:
    """DoD-3 — for every table the real registry declares, a fresh ``create_all`` compares
    identical on both readers (columns and indexes).

    Step 001 DoD-3.
    """
    with db_engine.connect() as conn:
        with conn.begin():
            schema.metadata.create_all(conn)

    for name, table in schema.metadata.tables.items():
        live = _live(db_engine, name)
        assert live is not None, name
        assert live == read_declared_shape(table), name


# =========================================================================== DoD-4


def test_variant_enum_and_text_types_match_across_readers_on_a_purpose_table__DoD4(
    db_engine: Engine,
) -> None:
    """DoD-4 — ``BigInteger().with_variant(Integer(), "sqlite")``, a non-native ``Enum`` and a
    ``Text`` column each report the same normalised type text from both readers.

    Step 001 DoD-4 (context.md D1 — compiled through the SQLite dialect).
    """
    table = Table(
        "typed",
        MetaData(),
        Column("id", BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=False),
        Column("mood", Enum(Mood, native_enum=False, length=16), nullable=False),
        Column("body", Text, nullable=True),
    )
    declared = _by_name(read_declared_shape(table))
    _create(db_engine, table)
    live_shape = _live(db_engine, "typed")
    assert live_shape is not None
    live = _by_name(live_shape)

    for name in ("id", "mood", "body"):
        assert declared[name].type_text == live[name].type_text, name

    assert declared["id"].type_text == "INTEGER"
    assert re.fullmatch(r"VARCHAR\(\d+\)", declared["mood"].type_text)
    assert declared["body"].type_text == "TEXT"


def test_users_id_role_and_text_columns_match_across_readers__DoD4(db_engine: Engine) -> None:
    """DoD-4 — on the real registry's ``users`` table: the varianted ``id`` is ``INTEGER`` on both
    sides (not ``BIGINT``), the non-native ``role`` Enum is its ``VARCHAR(n)`` form on both
    sides, and ``Text`` columns agree.

    Step 001 DoD-4 (001.context.md: users.id, users.role).
    """
    users = schema.metadata.tables["users"]
    declared = _by_name(read_declared_shape(users))
    _create(db_engine, users)
    live_shape = _live(db_engine, "users")
    assert live_shape is not None
    live = _by_name(live_shape)

    assert declared["id"].type_text == "INTEGER"
    assert live["id"].type_text == "INTEGER"
    assert re.fullmatch(r"VARCHAR\(\d+\)", declared["role"].type_text)
    assert declared["role"].type_text == live["role"].type_text
    assert declared["username"].type_text == "TEXT"
    assert live["username"].type_text == "TEXT"
    assert declared == live


# =========================================================================== DoD-5


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("text", "TEXT"),
        ("Text", "TEXT"),
        ("VARCHAR (50)", "VARCHAR(50)"),
        ("varchar (50)", "VARCHAR(50)"),
        ("DOUBLE  PRECISION", "DOUBLE PRECISION"),
        ("double\tprecision", "DOUBLE PRECISION"),
    ],
)
def test_case_and_internal_whitespace_are_not_differences__DoD5(left: str, right: str) -> None:
    """DoD-5 — type text differing only in case or internal whitespace normalises to the same text.

    Step 001 DoD-5 (context.md D1: upper-case and whitespace-normalise).
    """
    assert normalize_type_text(left) == normalize_type_text(right)


@pytest.mark.parametrize("already_normal", ["TEXT", "INTEGER", "VARCHAR(50)", "BOOLEAN"])
def test_normalised_text_is_upper_case__DoD5(already_normal: str) -> None:
    """DoD-5 — normalisation upper-cases: an upper-case, whitespace-free type text is its own
    normal form, and a lower-case spelling normalises to it.

    Step 001 DoD-5.
    """
    assert normalize_type_text(already_normal) == already_normal
    assert normalize_type_text(already_normal.lower()) == already_normal


def test_live_reader_normalises_hand_written_type_text__DoD5(db_engine: Engine) -> None:
    """DoD-5 — a table hand-created with lower-case, spaced type text reads the same as the
    registry declaration of the same shape: the live reader normalises before reporting.

    Step 001 DoD-5.
    """
    with db_engine.connect() as conn:
        with conn.begin():
            conn.execute(text("CREATE TABLE loose (label varchar (50) NOT NULL, body text)"))
    declared = Table(
        "loose",
        MetaData(),
        Column("label", String(50), nullable=False),
        Column("body", Text, nullable=True),
    )

    live = _live(db_engine, "loose")

    assert live is not None
    assert live.columns == read_declared_shape(declared).columns


class _SpacedLowerVarchar(UserDefinedType[str]):
    """A declared type whose SQLite compile is lower-case with internal whitespace."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "varchar  (50)"


def test_declared_reader_normalises_compiled_type_text__DoD5(db_engine: Engine) -> None:
    """DoD-5 — a declared type compiling to ``varchar  (50)`` reports the same column shape as a
    live ``VARCHAR(50)`` column: the declared reader normalises before reporting.

    Step 001 DoD-5.
    """
    spaced = Table("spaced", MetaData(), Column("label", _SpacedLowerVarchar(), nullable=False))
    plain = Table("plain", MetaData(), Column("label", String(50), nullable=False))
    _create(db_engine, plain)

    live = _live(db_engine, "plain")

    assert live is not None
    assert read_declared_shape(spaced).columns == live.columns
    assert read_declared_shape(spaced).columns == read_declared_shape(plain).columns


# =========================================================================== DoD-6


def test_unique_column_and_primary_key_are_not_live_indexes__DoD6(db_engine: Engine) -> None:
    """DoD-6 — a table whose only uniqueness comes from a ``unique=True`` column, a table-level
    unique constraint and a (non-rowid) primary key reports no index from either reader.

    Step 001 DoD-6 (context.md D1: only explicitly created indexes count).
    """
    table = Table(
        "codes",
        MetaData(),
        Column("code", Text, primary_key=True),
        Column("username", Text, nullable=False, unique=True),
        Column("a", Text, nullable=False),
        Column("b", Text, nullable=False),
        UniqueConstraint("a", "b", name="uq_codes_a_b"),
    )
    _create(db_engine, table)

    live = _live(db_engine, "codes")

    assert live is not None
    assert live.indexes == frozenset()
    assert read_declared_shape(table).indexes == frozenset()


def test_users_reports_no_index_on_either_reader__DoD6(db_engine: Engine) -> None:
    """DoD-6 — the real ``users`` table (``username`` is ``unique=True``, no ``Index(...)``)
    reports no index on a fresh, correct database, and the declared reader agrees.

    Step 001 DoD-6 (001.context.md: users.username).
    """
    users = schema.metadata.tables["users"]
    _create(db_engine, users)

    live = _live(db_engine, "users")

    assert live is not None
    assert live.indexes == frozenset()
    assert read_declared_shape(users).indexes == frozenset()


def test_explicit_indexes_are_reported_by_both_readers__DoD6(db_engine: Engine) -> None:
    """DoD-6 — explicitly declared ``Index(...)`` objects are reported (column list in
    declaration order + uniqueness) by the live reader, while the ``unique=True`` column's
    implicit index is not; the declared reader agrees on both counts.

    Step 001 DoD-6.
    """
    table = Table(
        "sessions",
        MetaData(),
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("username", Text, nullable=False, unique=True),
        Column("token", Text, nullable=False),
        Column("b", Text, nullable=False),
        Column("a", Text, nullable=False),
        Index("ix_sessions_token", "token", unique=True),
        Index("ix_sessions_b_a", "b", "a"),
    )
    expected = frozenset(
        {
            IndexShape(columns=("token",), unique=True),
            IndexShape(columns=("b", "a"), unique=False),
        }
    )
    _create(db_engine, table)

    live = _live(db_engine, "sessions")
    declared = read_declared_shape(table)

    assert live is not None
    assert live.indexes == expected
    assert declared.indexes == expected
    assert live == declared


# =========================================================================== DoD-7


def test_index_shapes_with_same_columns_and_uniqueness_are_equal__DoD7() -> None:
    """DoD-7 — an index shape's identity is its column list and uniqueness.

    Step 001 DoD-7 (context.md D1: keyed on (column list, uniqueness), not on name).
    """
    first = IndexShape(columns=("a", "b"), unique=True)
    second = IndexShape(columns=("a", "b"), unique=True)

    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1
    assert IndexShape(columns=("a", "b"), unique=True) != IndexShape(columns=("a", "b"), unique=False)
    assert IndexShape(columns=("a", "b"), unique=False) != IndexShape(columns=("b", "a"), unique=False)


def test_differently_named_indexes_over_same_columns_are_the_same_shape__DoD7(db_engine: Engine) -> None:
    """DoD-7 — a live index and a declared index over the same columns with the same uniqueness
    but different names are the same shape.

    Step 001 DoD-7.
    """
    live_table = Table(
        "pairs",
        MetaData(),
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("a", Text, nullable=False),
        Column("b", Text, nullable=False),
        Index("some_name_sqlite_holds", "a", "b", unique=True),
    )
    declared_table = Table(
        "pairs",
        MetaData(),
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("a", Text, nullable=False),
        Column("b", Text, nullable=False),
        Index("ix_a_completely_different_name", "a", "b", unique=True),
    )
    _create(db_engine, live_table)

    live = _live(db_engine, "pairs")

    assert live is not None
    assert live.indexes == read_declared_shape(declared_table).indexes
    assert live == read_declared_shape(declared_table)


def test_two_live_indexes_with_different_names_same_shape_collapse__DoD7(db_engine: Engine) -> None:
    """DoD-7 — two live indexes over the same columns and uniqueness, differently named, are one
    shape (the name carries no identity).

    Step 001 DoD-7.
    """
    table = Table(
        "twins",
        MetaData(),
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("a", Text, nullable=False),
        Index("ix_twins_first", "a"),
        Index("ix_twins_second", "a"),
    )
    _create(db_engine, table)

    live = _live(db_engine, "twins")

    assert live is not None
    assert live.indexes == frozenset({IndexShape(columns=("a",), unique=False)})


# =========================================================================== DoD-8


def test_absent_table_is_reported_absent_on_an_empty_database__DoD8(db_engine: Engine) -> None:
    """DoD-8 — a table that does not exist is reported as absent (``None``) and nothing is raised.

    Step 001 DoD-8 (US-017.AC-1, UC-014).
    """
    assert _live(db_engine, "no_such_table") is None


def test_absent_table_is_reported_absent_beside_other_tables__DoD8(db_engine: Engine) -> None:
    """DoD-8 — with other tables present, an undeclared-on-disk name still reads as absent.

    Step 001 DoD-8.
    """
    _create(db_engine, _plain_table(MetaData()))

    assert _live(db_engine, "no_such_table") is None
    assert _live(db_engine, "notes") is not None


# =========================================================================== DoD-9


def _populated(engine: Engine) -> Table:
    table = Table(
        "diary",
        MetaData(),
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("entry", Text, nullable=False),
        Column("tag", Text, nullable=True),
        Index("ix_diary_tag", "tag"),
    )
    _create(engine, table)
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                table.insert(),
                [
                    {"id": 1, "entry": "first", "tag": "x"},
                    {"id": 2, "entry": "second", "tag": None},
                    {"id": 3, "entry": "third", "tag": "y"},
                ],
            )
    return table


def _snapshot(engine: Engine) -> tuple[Any, ...]:
    """sqlite_master, the schema version and every row of ``diary``, from a separate connection."""
    with engine.connect() as conn:
        master = conn.execute(
            text("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")
        ).all()
        version = conn.execute(text("PRAGMA schema_version")).scalar()
        rows = conn.execute(text("SELECT id, entry, tag FROM diary ORDER BY id")).all()
        conn.rollback()
    return (tuple(master), version, tuple(rows))


def test_reader_without_begin_leaves_schema_and_rows_untouched__DoD9(db_engine: Engine) -> None:
    """DoD-9 — the live reader is callable on a connection with no ``begin()`` around it, and
    running it against a populated database leaves ``sqlite_master`` and every row untouched.

    Step 001 DoD-9 (backend-structure.md: the drift/sync split).
    """
    _populated(db_engine)
    before = _snapshot(db_engine)

    with db_engine.connect() as conn:
        changes_before = conn.execute(text("SELECT total_changes()")).scalar()
        conn.rollback()
        shape = read_live_shape(conn, "diary")
        changes_after = conn.execute(text("SELECT total_changes()")).scalar()

    assert shape is not None
    assert [column.name for column in shape.columns] == ["id", "entry", "tag"]
    assert changes_after == changes_before
    assert _snapshot(db_engine) == before


class _Recorder:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.events: list[str] = []


@pytest.fixture
def recorded_connection(db_engine: Engine) -> Iterator[tuple[Connection, _Recorder]]:
    """A connection with listeners recording every cursor statement and transaction event."""
    recorder = _Recorder()
    with db_engine.connect() as conn:

        def on_statement(
            _conn: Connection, _cursor: Any, statement: str, _params: Any, _context: Any, _many: bool
        ) -> None:
            recorder.statements.append(statement)

        def recording(event_name: str) -> Any:
            def on_event(*_args: Any) -> None:
                recorder.events.append(event_name)

            return on_event

        event.listen(conn, "before_cursor_execute", on_statement)
        for name in ("begin", "commit", "rollback", "savepoint", "release_savepoint", "rollback_savepoint"):
            event.listen(conn, name, recording(name))
        yield conn, recorder


def test_reader_inside_callers_transaction_opens_none_and_commits_nothing__DoD9(
    db_engine: Engine, recorded_connection: tuple[Connection, _Recorder]
) -> None:
    """DoD-9 — called inside the caller's own transaction, the reader begins, commits, rolls back
    and savepoints nothing: the caller's transaction is still the one in force afterwards, and
    the caller's uncommitted change is still undone by the caller's rollback.

    Step 001 DoD-9 (opens no transaction; writes nothing).
    """
    _populated(db_engine)
    before = _snapshot(db_engine)
    conn, recorder = recorded_connection

    outer = conn.begin()
    conn.execute(text("INSERT INTO diary (id, entry, tag) VALUES (99, 'uncommitted', NULL)"))
    recorder.statements.clear()
    recorder.events.clear()

    shape = read_live_shape(conn, "diary")

    assert shape is not None
    assert recorder.events == []
    assert conn.get_transaction() is outer
    assert outer.is_active
    outer.rollback()
    assert _snapshot(db_engine) == before


def test_reader_issues_only_pragma_reads_and_selects__DoD9(
    db_engine: Engine, recorded_connection: tuple[Connection, _Recorder]
) -> None:
    """DoD-9 — every statement the reader issues is a ``PRAGMA`` read or a ``SELECT``: no DDL,
    no DML, no transaction control, no pragma assignment.

    Step 001 DoD-9 (interface intent: PRAGMA reads and SELECTs only; writes nothing).
    """
    _populated(db_engine)
    conn, recorder = recorded_connection

    with conn.begin():
        recorder.statements.clear()
        read_live_shape(conn, "diary")
        read_live_shape(conn, "no_such_table")
        issued = list(recorder.statements)

    assert issued, "the live reader issued no statement at all"
    for statement in issued:
        head = statement.lstrip().upper()
        assert head.startswith(("PRAGMA", "SELECT")), statement
        if head.startswith("PRAGMA"):
            assert "=" not in head, statement


# =========================================================================== DoD-10

_FORBIDDEN_FIELD = re.compile(r"count|rows|size|bytes|time|date|_at$", re.IGNORECASE)


def test_table_report_carries_exactly_the_specified_fields__DoD10() -> None:
    """DoD-10 — the per-table report carries the table name, status, missing/extra/changed columns
    and missing/extra indexes, and nothing else — no row count, no byte size, no timestamp.

    Step 001 DoD-10 (R5, UC-066; context.md D2).
    """
    names = {field.name for field in dataclasses.fields(TableReport)}

    assert names == {
        "table_name",
        "status",
        "missing_columns",
        "extra_columns",
        "changed_columns",
        "missing_indexes",
        "extra_indexes",
    }
    assert [name for name in names if _FORBIDDEN_FIELD.search(name)] == []


def test_report_value_types_carry_no_count_size_or_timestamp_field__DoD10() -> None:
    """DoD-10 — the whole report is its per-table reports and nothing beside them, and no value
    type the report is built from carries a count, size or timestamp field.

    Step 001 DoD-10 (R5).
    """
    assert {field.name for field in dataclasses.fields(DriftReport)} == {"tables"}
    for value_type in (TableReport, DriftReport, TableShape, ColumnShape, IndexShape):
        offenders = [f.name for f in dataclasses.fields(value_type) if _FORBIDDEN_FIELD.search(f.name)]
        assert offenders == [], value_type.__name__


_COUNT_CALL = re.compile(r"\bcount\s*\(", re.IGNORECASE)


def test_module_source_contains_no_count_query__DoD10() -> None:
    """DoD-10 — ``db/drift.py`` issues no ``COUNT(*)`` of any kind: no string in the module
    spells a ``COUNT(`` call, and no SQLAlchemy ``func.count`` is referenced.

    Step 001 DoD-10 (R5; context.md cross-cutting: no SELECT COUNT(*) in db/drift.py).
    """
    tree = ast.parse(inspect.getsource(drift_module))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and _COUNT_CALL.search(node.value):
            offenders.append(node.value)
        elif isinstance(node, ast.Attribute) and node.attr == "count" and ast.unparse(node.value).endswith("func"):
            offenders.append(ast.unparse(node))
        elif isinstance(node, ast.ImportFrom) and any(alias.name == "count" for alias in node.names):
            offenders.append(f"from {node.module} import count")
    assert offenders == []


def test_reader_issues_no_count_statement__DoD10(
    db_engine: Engine, recorded_connection: tuple[Connection, _Recorder]
) -> None:
    """DoD-10 — running the live reader against a populated table issues no ``COUNT`` statement.

    Step 001 DoD-10 (R5).
    """
    _populated(db_engine)
    conn, recorder = recorded_connection

    with conn.begin():
        recorder.statements.clear()
        read_live_shape(conn, "diary")
        issued = list(recorder.statements)

    assert [statement for statement in issued if _COUNT_CALL.search(statement)] == []


# =========================================================================== DoD-11


def _imported_names() -> list[str]:
    """Every module (and ``module.name``) the drift module imports, relative imports resolved."""
    tree = ast.parse(inspect.getsource(drift_module))
    package_parts = drift_module.__name__.split(".")[:-1]  # ["app", "db"]
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = package_parts[: len(package_parts) - (node.level - 1)]
                base = ".".join(base_parts + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            imported.append(base)
            imported.extend(f"{base}.{alias.name}" for alias in node.names)
    return imported


@pytest.mark.parametrize("forbidden", ["app.db.sync", "app.db.schema"])
def test_drift_module_imports_neither_sync_nor_schema__DoD11(forbidden: str) -> None:
    """DoD-11 — ``db/drift.py`` imports neither ``app.db.sync`` nor ``app.db.schema``.

    Step 001 DoD-11 (backend-structure.md: "the code path that only reports cannot write").
    """
    offenders = [name for name in _imported_names() if name == forbidden or name.startswith(forbidden + ".")]
    assert offenders == []


def test_drift_module_holds_no_registry_or_table_of_its_own__DoD11() -> None:
    """DoD-11 — the registry and every ``Table`` reach the module as arguments: the module holds
    no ``MetaData`` instance, no ``Table`` instance and no reference to the schema or sync
    modules at module level.

    Step 001 DoD-11 (context.md cross-cutting constraints).
    """
    held = [
        name
        for name, value in vars(drift_module).items()
        if isinstance(value, MetaData | Table)
        or getattr(value, "__name__", None) in {"app.db.schema", "app.db.sync"}
    ]
    assert held == []
