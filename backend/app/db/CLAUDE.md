# db

<!-- agent-ready:start -->

Database access over SQLAlchemy Core (never the ORM): the SQLite engine, the schema registry that is the single source of truth, the FTS5 / `vec0` virtual tables, and the admin drift diagnosis and remediation.

## Glossary

**Files:**
- `__init__.py` — package marker (documents the Core-only rule).
- `drift.py` — schema drift diagnosis: compares the live database against the registry (diagnosis only).
- `engine.py` — the SQLite connection factory, its connect listener and the connection dependency.
- `schema.py` — the table-definition registry, the single source of truth for the relational schema.
- `search_tables.py` — the virtual-table layer: FTS5 and `vec0` DDL plus the triggers that keep the full-text indexes in step with memos and settled messages, ensured on write.
- `sync.py` — schema remediation: the Alembic-batch DDL executor behind the drift page's Sync / Create.

See also: docs/architecture/data-model.md, docs/architecture/search-and-retrieval.md

<!-- agent-ready:end -->
