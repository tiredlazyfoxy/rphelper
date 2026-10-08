"""Searching the session's memo chain for the notes the assistant can still be told about.

Feature `026`, step `001` (FEAT-014; UC-051, UC-052). Three things and nothing else:

- **`MEMO_SEARCH_LIMIT`** — the fixed result cap, passed to the port as `limit`. No paging, no
  offset, no count argument (D1).
- **`searchable_chain_predicate`** — the extra predicate the port's memo scope variant accepts:
  searchable (`is_enabled` first, then the negated `is_forced` — R3) AND the chain disjunction
  `services/memo_chain.py` owns (R2, D2). Forced notes are already in the system prompt and
  disabled notes reach the assistant by no path, so both are excluded here.
- **`search_memos`** — the synchronous wrapper: build the memo scope for the owner and the chain,
  call the port once with the fixed limit, return its hits unchanged, order included.

This module is service-layer only: it imports no web framework, nothing from the tool layer and
nothing from the vector extension, so it can be exercised with a connection and nothing else. The
owner predicate is the port's own (D6, R5) and is not restated here. Reads only, writes nothing,
and leaves the connection with no transaction open on return **and** on raise - 026's standing
guarantee to the seam, independent of the port's error path (D3, 025 D7).
"""

from typing import Final

from sqlalchemy import ColumnElement, Connection, FromClause, and_, not_

from app.services.embedding import DEFAULT_EMBED_TIMEOUT_SECONDS
from app.services.llm.client import LlmClient
from app.services.llm_registry import LlmClientFactory
from app.services.memo_chain import chain_clause
from app.services.search.hybrid import search
from app.services.search.ports import ExtraPredicateBuilder, MemoSearchScope, SearchHit

MEMO_SEARCH_LIMIT: Final[int] = 8
"""How many hits one memo search returns at most. Conventional, not measured; no paging (D1)."""


def searchable_chain_predicate(
    user_id: int,
    character_id: int,
    setup_id: int | None,
    session_id: int,
) -> ExtraPredicateBuilder:
    """The port's extra predicate for one chain: searchable notes at the chain's levels (R3, R2, D2).

    The returned builder takes the relation the port selects candidates from and answers
    `is_enabled AND NOT is_forced AND <chain clause over that relation>`. Both flag terms are always
    present and in R3's order - `is_enabled` is the first term and is never dropped as implied by
    the second, and `is_forced` appears negated.

    The four ids are the chain's **stored** ids, as `memo_chain.chain_clause` wants them: the user
    level's is `user_id`, and `setup_id` is `None` for a session with no setup (one fewer term).
    Owner scoping is the port's (D6, R5), so it is not part of this predicate.
    """

    def build(relation: FromClause) -> ColumnElement[bool]:
        # R3's order is literal here: `is_enabled` is written first and `is_forced` is negated
        # rather than folded into one flag, so the compiled text carries the rule in that order.
        return and_(
            relation.c["is_enabled"],
            not_(relation.c["is_forced"]),
            chain_clause(relation, user_id, character_id, setup_id, session_id),
        )

    return build


def search_memos(
    connection: Connection,
    user_id: int,
    character_id: int,
    setup_id: int | None,
    session_id: int,
    query_text: str,
    *,
    client_factory: LlmClientFactory = LlmClient,
    timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS,
) -> list[SearchHit]:
    """The searchable notes of one session's whole chain that match `query_text`, best first (D1, D3).

    The four ids are the chain's stored ids (`setup_id` `None` for a session with no setup) and come
    from the caller's own owner-scoped read, never from the assistant's arguments (D6). `query_text`
    is the raw text: the port embeds it verbatim and sanitises its own lexical form of it. At most
    `MEMO_SEARCH_LIMIT` hits are returned, in the port's fused-rank order, exactly as the port built
    them - nothing is re-read, re-ranked, truncated further or reshaped here.

    Synchronous, and it embeds through the port, so it must not run on a thread with a running event
    loop; an async caller hands it to a worker thread (D3). The port's errors propagate unchanged
    (`no_embedding_model`, `llm_unreachable`, `secret_ref_missing`); on every exit, raise included,
    an autobegun read transaction is rolled back so the connection has none open.
    """
    scope = MemoSearchScope(
        user_id=user_id,
        extra_predicate=searchable_chain_predicate(user_id, character_id, setup_id, session_id),
    )
    try:
        # The hits are returned as the port built them: same objects, same order, no further cut.
        return search(
            connection,
            scope,
            query_text,
            MEMO_SEARCH_LIMIT,
            client_factory=client_factory,
            timeout_seconds=timeout_seconds,
        )
    finally:
        # 026's own guarantee to the seam, on the error path too: never depend on the port's
        # rollback, because an exception may escape before or around it (D3, 025 D7).
        if connection.in_transaction():
            connection.rollback()
