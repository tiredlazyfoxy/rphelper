"""Filters first: the candidate id select each arm ranks inside (feature `025`, step `002`).

A scope variant names a corpus; this module turns it into the two things both arms need:

- **`base_relation`** — the FROM object the variant's rows come from (`memos`, `sessions`, or a
  subquery over the `settled_entries` selectable — never raw `messages`, R11).
- **`candidate_ids`** — a Core select of that relation's single id column, carrying the owner
  predicate (D6) and the caller's extra predicate (U1), and nothing else.

Nothing here executes SQL: `candidate_ids` hands back a `Select` that the lexical arm
(`lexical.py`) and the vector arm (`vector.py`) each consume as an `IN (…)` subquery, so the
relational filter always runs **before** ranking and never after it (D5,
`search-and-retrieval.md` "Query shape"). The module imports no `fastapi`.
"""

from sqlalchemy import FromClause, Select, select

from app.db.schema import memos, sessions, settled_entries
from app.services.search.ports import MemoSearchScope, SearchScope, SessionSearchScope


def base_relation(scope: SearchScope) -> FromClause:
    """Return the FROM object `scope`'s candidates come from (U1, R11).

    `MemoSearchScope` gives the `memos` table, `SessionSearchScope` the `sessions` table, and
    `EntrySearchScope` a **subquery over the `settled_entries` selectable** — the view is a
    `Select`, which is not a `FromClause`, and raw `messages` is forbidden (R11): the zone and
    buried rows must not be findable (US-115, UC-038).

    The returned object is the **same** object the scope's extra-predicate builder is called
    with, so the builder's column references bind to the FROM the candidate select uses. For the
    entry variant a **fresh** subquery is produced on every call, so a caller that needs both the
    relation and a predicate over it must hold **one** result and reuse it rather than calling
    this function twice.
    """
    if isinstance(scope, MemoSearchScope):
        return memos
    if isinstance(scope, SessionSearchScope):
        return sessions
    # The entry variant: `settled_entries` is a `Select`, which is not a `FromClause`, so it is
    # taken as a subquery — a **new** one per call, hence the single-call discipline above.
    return settled_entries.subquery()


def candidate_ids(scope: SearchScope) -> Select[tuple[int]]:
    """Return the select of candidate ids for `scope` — the set each arm ranks within (D5).

    A single-column select of the base relation's `id`, filtered by
    `user_id = scope.user_id` (applied by the port itself, never a caller option — D6, R5,
    UC-065, US-085) ANDed with the clause `scope.extra_predicate` returns for that base relation
    when a builder is present (U1). The builder is called exactly once, with the one
    `base_relation` object this select reads from.

    Executes nothing, opens no transaction and takes no connection: both arms embed the result as
    a subquery.
    """
    # Called **once**, and the one object is reused for the FROM, the owner predicate and the
    # builder alike: for the entry variant a second call would mint a second subquery and splice
    # a silent extra FROM into the statement instead of failing.
    relation = base_relation(scope)
    statement = select(relation.c["id"]).where(relation.c["user_id"] == scope.user_id)
    if scope.extra_predicate is not None:
        statement = statement.where(scope.extra_predicate(relation))
    return statement
