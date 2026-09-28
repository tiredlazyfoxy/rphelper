"""Step 005 — the table-definition registry (`app/db/schema.py`).

Covers DoD-7: `db.schema` exposes a module-level metadata object whose table collection
is empty in this feature and is enumerable by name — the shape feature 007 will walk.
"""

from collections.abc import Mapping

from sqlalchemy import MetaData

from app.db import schema


def test_schema_module_exposes_a_module_level_metadata_object__DoD7() -> None:
    """DoD-7 — the registry is a module-level `MetaData` on `app.db.schema`."""
    assert hasattr(schema, "metadata")
    assert isinstance(schema.metadata, MetaData)


def test_registry_table_collection_is_empty_in_this_feature__DoD7() -> None:
    """DoD-7 — zero tables are declared in feature 001."""
    assert dict(schema.metadata.tables) == {}
    assert list(schema.metadata.sorted_tables) == []


def test_registry_table_collection_is_enumerable_by_name__DoD7() -> None:
    """DoD-7 — the collection is a name-keyed mapping, which is what 007 walks."""
    tables = schema.metadata.tables
    assert isinstance(tables, Mapping)
    names = list(tables)
    assert names == []
    assert all(isinstance(name, str) for name in names)
    assert [table.name for table in tables.values()] == []
