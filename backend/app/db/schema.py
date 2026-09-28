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

This module declares **no** table, view, index or trigger, and **executes no DDL**,
including at import. In this feature the registry ships empty, and that is correct: the
content features each add their own tables. DDL only ever runs through `007`'s
admin-triggered `Create` and `Sync` actions.
"""

from sqlalchemy import MetaData

#: The one registry. Every `Table(...)` in this project is bound to it; `007` walks
#: `metadata.tables` to produce the drift report.
metadata = MetaData()
