"""Database access — SQLAlchemy **Core**, never the ORM.

Two modules and no more in this feature:

- `engine.py` — the one SQLite connection factory: the engine cache, the single
  `connect` listener that loads `sqlite-vec` and sets the PRAGMAs on **every**
  connection, and the request-scoped `get_connection` dependency.
- `schema.py` — the table-definition registry: one `MetaData`, and every table
  RPHelper will ever have declared as a `Table(...)` literal in that same file.

Nothing here declares a mapped class, opens a `Session`, or imports
`sqlalchemy.orm`. Transaction boundaries are `with conn.begin():` blocks at the
calling service's own level, never opened by this package.

`db/drift.py` and `db/sync.py` — the admin drift page's diagnosis and remediation —
arrive with feature `007`. No DDL is executed anywhere in this package, including at
import.
"""
