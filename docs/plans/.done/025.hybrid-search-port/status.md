# Feature 025 — hybrid-search-port

| Step | File                                   | Status  | Verifier | Date |
|------|----------------------------------------|---------|----------|------|
| 001  | `001.port-contract.md`                 | done    | PASS        | 2026-10-04    |
| 002  | `002.candidates-and-lexical-arm.md`    | done    | PASS        | 2026-10-04    |
| 003  | `003.vector-arm.md`                    | done    | PASS        | 2026-10-04    |
| 004  | `004.search-entry-point.md`            | done    | PASS        | 2026-10-04    |

## Files Changed

### Step 001 — the port contract and its pure helpers

- `backend/app/services/search/__init__.py` — package marker; **verified, not changed** (docstring
  only, no statements after it; `app/services/__init__.py` untouched).
- `backend/app/services/search/ports.py` — filled the three frozen bodies and nothing else: no
  signature, declaration, constant or docstring touched, and no import added.
  - `rrf_fuse` — accumulates `1 / (k + rank)` per id with `rank` 1-based within each ranking, then
    sorts by score descending, id ascending (D1 ties). Empty input / only empty rankings → `[]`.
  - `build_fts_query` — `001.context.md` rules 1–6 verbatim: `str.split()`, every `"` removed per
    token, emptied tokens dropped, each survivor quoted, joined with ` OR `, `None` when none remain
    (the guard against `MATCH ''`, harvest headline 2). Case preserved; `"---"` kept, not filtered.
  - `leading_extract` — `" ".join(body.split())` (collapse + strip), then first `SNIPPET_CHARS`
    characters plus `…` (U+2026) when longer, giving length `SNIPPET_CHARS + 1`.

### Step 002 — the candidate sets and the lexical arm

- `backend/app/services/search/candidates.py` — filled `base_relation` (variant dispatch by
  `isinstance`: `schema.memos`, `schema.sessions`, `settled_entries.subquery()`) and `candidate_ids`
  (`select(relation.c["id"]).where(relation.c["user_id"] == scope.user_id)`, plus the builder's
  clause when a builder is present). Executes nothing; takes no connection. Added imports only:
  `sqlalchemy.select`, `app.db.schema.memos/sessions/settled_entries`,
  `ports.MemoSearchScope/SessionSearchScope` (`and_` was not needed — two `.where()` calls AND).
  **`base_relation` single-call discipline honoured:** `candidate_ids` calls it exactly **once**,
  binds the result to the local `relation`, and uses that same object for the id column, the owner
  predicate **and** the extra-predicate builder, so the entry variant's fresh `Subquery` is the one
  the select reads from. Verified on an in-memory DB: the compiled entry candidate select has a
  single `anon_1` FROM, no extra join.
- `backend/app/services/search/lexical.py` — filled `fts_table_exists` (inline
  `text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name LIMIT 1")`, no new
  module-level symbol) and `lexical_ranking`: `None` expression **or** absent table short-circuits
  to `[]` before any statement reaches the FTS table (U2; `MATCH ''` raises); otherwise one Core
  statement over a lightweight `table(table_name, column("rowid", Integer))` —
  `select(rowid, snippet(<name>, 0, '', '', '…', SNIPPET_TOKENS))`,
  `WHERE <name> MATCH :expr AND rowid IN (<candidate select>)`, `ORDER BY bm25(<name>), rowid`,
  `LIMIT :depth` — mapped to `LexicalMatch(id, snippet)`.
  - Decisions worth knowing: the bare table name on the left of `MATCH` and as `snippet()` /
    `bm25()`'s first argument is `literal_column(table_name)`, annotated `ColumnClause[str]` because
    mypy cannot infer the untyped form (`var-annotated`); it contributes no FROM, so the statement
    names the table once. `.match()` renders as ` MATCH ` on SQLite (probed). The candidate select is
    embedded as the `IN (…)` subquery, so D5 holds inside the query and no result is filtered after
    ranking. No table name is spelled in either module: `table_name` arrives from 024's constants.
  - Probed on `:memory:` databases only (never the file DB): BM25 order is term-frequency-in-a-
    shorter-body first, the long body's snippet ends in `…` and carries no `<>[]`, snowflake ids
    above 2^60 round-trip, `depth` caps, the other user's indexed memo is absent, and a database
    whose FTS tables were never ensured yields `[]` with `fts_table_exists` false.

**Gates:** `mypy app` → clean (79 source files). `ruff check .` → clean. pytest **not** run.

### Step 003 — the vector arm

- `backend/app/services/search/vector.py` — filled the one frozen body; no signature, parameter,
  default or docstring touched. The five steps run in the contracted order inside a local `_reading`
  window (D7's posture, replicated from `services/memos.py`, never imported): `open_embedding_model`
  first (so a missing designation raises even when the vec table does not exist — U2, R4), then
  `vector_table_dimension` (`None` → `return []` with **no** embed call), then the table-vs-handle
  width guard (`NoEmbeddingModelError` with a fixed message and `detail {"reason":
  "dimension_mismatch"}`, still before embedding), then **one** `embed_texts(handle, [query_text])`
  unpacked as `(query_vector,)`, then the exact scan.
- **The source contains no `MATCH` substring** — verified by a scan of the written file: 0
  occurrences, docstrings and comments included, and no `fastapi` occurrence either (0). The
  constant holding the fixed width-guard message is therefore named `_DIMENSION_CONFLICT_MESSAGE`:
  the obvious `_DIMENSION_MISMATCH_MESSAGE` (024's own name) would have put `MATCH` into the source
  twice via `MISMATCH`. The `detail` value stays the mandated lowercase `"dimension_mismatch"`.
- The statement is the one permitted form, built as a lightweight
  `table(table_name, column(key_column, BigInteger), column("embedding"))` construct (the vec tables
  are outside `schema.metadata`): `select(key).where(key.in_(candidate_select))
  .order_by(func.vec_distance_l2(embedding, :blob), key).limit(depth)`. The candidate select is the
  `IN (…)` subquery, so the filter runs inside the statement and nothing is dropped afterwards (D5,
  D6). The query vector is `literal(sqlite_vec.serialize_float32(query_vector), LargeBinary)` — a
  bound blob; no extension loader call (`db/engine.py` already loads it per connection).
- Decisions worth knowing: the key column is resolved through a module-level
  `_KEY_COLUMNS: dict[str, str]` **keyed by 024's `MEMO_VEC_TABLE` / `SESSION_VEC_TABLE`
  constants** (the skeleton's first alternative) rather than by a second `pragma_table_info` read —
  existence is already answered by `vector_table_dimension`, so the pragma would be a redundant
  statement inside the read window. No table name is spelled as a literal in this module (0
  occurrences of either name as a string). `rowid` is never selected or ordered by: the key column
  is named outright, both in the projection and in the tie-break. The module creates nothing and
  writes nothing (no `CREATE`, no `INSERT`, and `app.db.search_tables` is imported for the two
  constants and the dimension reader only). Imports added: `collections.abc.Iterator`,
  `contextlib.contextmanager`, `sqlite_vec` (with the required `# type: ignore[import-untyped]`),
  five SQLAlchemy names plus `BigInteger` / `LargeBinary`, 024's reader and constants,
  `NoEmbeddingModelError`, `embed_texts` / `open_embedding_model`.
- Probed on throwaway temp-file databases only (the project `data/rphelper.sqlite` was never opened
  and is unchanged): L2 order with a hand-computed float32 L2; ties broken by ascending id; a
  non-candidate whose vector equals the query vector exactly stays absent; a candidate with no
  vector row is skipped without error; `depth` caps; an empty candidate subquery and an
  empty-but-present table give `[]`; an **absent** table gives `[]` with zero embed calls; no
  designated model raises with the client factory never called, table absent included; the 8-vs-16
  width conflict raises with the exact `detail` and zero embed calls; a scripted
  `LlmUnreachableError` propagates; success records exactly one embed call carrying the designated
  model name and the one query text; **200 snowflake candidates (ids above 2^60, non-contiguous)
  plus 200 non-candidates over four query texts matched the brute-force top-25 exactly**; and the
  read posture holds both ways (no transaction left open when none was, the caller's left open when
  there was).

**Gates:** `mypy app` → clean (79 source files). `ruff check .` → clean. pytest **not** run.

### Step 004 — the search entry point

- `backend/app/services/search/hybrid.py` — filled the one frozen body; no signature, parameter,
  default or docstring touched, and the module docstring's claims still hold (source scan: `fastapi`
  0, `FastAPI` 0, `sqlite` 0, `sqlite_vec` 0; imports are `app.db.schema`, `app.db.search_tables`,
  `app.services.embedding`, `app.services.llm.client`, `app.services.llm_registry`, the three 025
  arm/contract modules, `collections.abc`, `contextlib`, `sqlalchemy`, `typing` — **no** `ensure_*`
  name is imported, so "025 creates no table" holds at the import level).
- The six contracted behaviours in order: (1) `limit <= 0 or not query_text.strip()` → `[]` as the
  very first statement, before `candidate_ids` is even built — no model, no embed call, no
  statement; (2) **one** `candidate_ids(scope)` per search, bound to a local and handed to both
  arms; (3) the variant's arms, **vector first** for memo, inside one local `_reading` window;
  (4) `rrf_fuse(rankings)[:limit]`, with an empty fused set short-circuiting to `[]` so no
  hydration statement is issued; (5) one owner-scoped hydration read per kind; (6) the D3 / D4 hit.
- **`base_relation` single-call discipline.** `hybrid.py` calls `base_relation` in exactly one
  place — `_entry_hits` — binds the result to `relation` and uses that one object for the
  projection (`relation.c["id"]`, `relation.c["session_id"]`), the owner predicate
  (`relation.c["user_id"]`) and therefore the FROM alike. Verified by compiling that statement: the
  outer `SELECT` has a single `anon_1` FROM (the second `FROM` in the text is the subquery's own
  `FROM messages`), i.e. no silent extra FROM / cross join. The memo hydration read deliberately
  uses `app.db.schema.memos` directly — the identical object `base_relation` returns for that
  variant, so no second call exists to mint anything — and the session variant hydrates nothing.
- Private helpers added (all the coder's choice, none a new public symbol): `_reading` (D7's posture,
  **replicated locally** from `services/memos.py`, never imported — harvest C10), `_run_arms`
  (variant → arm dispatch, returning the id rankings plus a `dict[int, str]` of the lexical arm's
  own `snippet()` texts so FTS is never re-queried), `_memo_hits`, `_session_hits`, `_entry_hits`
  (one per kind, each owning its single hydration read and its D3 field set).
- Decisions worth knowing:
  - **A memo hit's `memo_scope_id` is the value stored in `memos.scope_id`, passed through
    unchanged** — including for a `"user"`-level memo, where the stored value is the owner's id.
    This follows the step file's DoD-4 ("carry `scope` `"user"` / `"session"` and **the stored**
    `scope_id`") and `004.context.md`'s hydration read. It differs from `services/memos.py`'s
    `Memo.scope_id` convention (`None` for the user level) — see `## Notes & Issues`.
  - A kept id absent from its hydration read is skipped with `continue`, never raised, so the
    result stays a prefix-consistent subsequence of the fused order.
  - The lexical snippet is looked up with `lexical_snippets.get(id)` and only replaced by
    `leading_extract(body)` when the lookup is `None`, so an FTS snippet that happens to be the
    empty string is still preferred over the body extract (a truthiness test would not be).
  - Rows are kept as `dict[int, Row[Any]]` for the memo read (`services/memos.py`'s `Row[Any]`
    idiom, which also keeps `row.scope` assignable to `SearchHit.memo_scope`'s `MemoScope`).
  - A `None` FTS expression is passed straight into `lexical_ranking`, which short-circuits before
    touching the table, so an unusable-lexical query (`"""`) yields the vector ranking alone rather
    than a second code path here.
- Probed on throwaway temp-file databases only, each deleted afterwards (`backend/data/rphelper.sqlite`
  was never opened and is unchanged, and `tests/` was neither read nor used): memo hybrid fusion
  order and scores matched hand-computed RRF for both a vector-only query and a token that the
  lexical arm rescues; `limit` cut and an `is_enabled` extra predicate; a vector-only memo's snippet
  equalled `leading_extract(body)` exactly while a lexical hit carried the FTS snippet; session
  scope succeeded with **neither FTS table present**, hits carrying `snippet` / `memo_scope` /
  `session_id` all none; entry scope succeeded with **no designated model** and the client factory
  called **zero** times, zone, buried and the other user's rows absent; memo and session scope both
  raised `no_embedding_model` with no model designated (memo raising although `memo_fts` held a
  match) and a scripted `LlmUnreachableError` propagated; all twelve early-exit combinations
  (`limit` 0, `-3`, `""`, whitespace × three variants) returned `[]` with zero factory calls; both
  tables absent → `[]`, FTS-only → the lexical matches alone; owner isolation held as an absence in
  every variant; and no transaction was left open after any path, success or raise.

**Gates:** `mypy app` → clean (79 source files). `ruff check .` → clean. pytest **not** run.

## Skeleton

### Step 001 — frozen interface (2026-10-04)

`backend/app/services/search/__init__.py` — **new**. Docstring only; re-exports nothing (no
statements after the docstring). `app/services/__init__.py` was **not** touched.

`backend/app/services/search/ports.py` — **new**. Every symbol below is frozen; the coder fills
the three function bodies and changes no signature. Imports are exactly
`collections.abc.Callable/Sequence`, `dataclasses.dataclass`, `typing.Final/Literal`,
`sqlalchemy.ColumnElement/FromClause`, `app.models.memos.MemoScope` — no `fastapi`, no
`sqlite_vec`, nothing from `app.db.engine` (DoD-10 holds as written).

**Constants** (DoD-9), all `Final[int]` with their real values:
- `RRF_K: Final[int] = 60`
- `ARM_DEPTH: Final[int] = 50`
- `SNIPPET_CHARS: Final[int] = 160`

**Types and values:**
- `SearchKind = Literal["memo", "session", "entry"]` — the hit-kind closed set.
- `ExtraPredicateBuilder = Callable[[FromClause], ColumnElement[bool]]` — the extra-predicate
  builder type.
- `MemoSearchScope`, `SessionSearchScope`, `EntrySearchScope` — three `@dataclass(frozen=True)`
  classes, each with **exactly** these two fields in this order:
  - `user_id: int` — **no default** (so construction without it is `TypeError`, DoD-1)
  - `extra_predicate: ExtraPredicateBuilder | None = None`
  `slots` is deliberately **not** used (optional per `001.context.md`; omitted so the frozen
  assignment raises plain `dataclasses.FrozenInstanceError`, verified).
- `SearchScope = MemoSearchScope | SessionSearchScope | EntrySearchScope` — the union `search`
  accepts.
- `SearchHit` — `@dataclass(frozen=True)`, fields in this order:
  - `kind: SearchKind`
  - `id: int`
  - `score: float`
  - `snippet: str | None = None`
  - `memo_scope: MemoScope | None = None`
  - `memo_scope_id: int | None = None`
  - `session_id: int | None = None`

  The four D3-optional fields default to `None` so a session hit is `SearchHit("session", i, s)`;
  the three always-present fields are defaultless. `MemoScope` is **imported** from
  `app.models.memos` (the precedent import path used by `services/memos.py:39` and
  `services/memo_chain.py:16`; `app/models/__init__.py` exports only the two id aliases and is
  read-only to this step), never re-declared.

**Functions** — exact signatures, bodies `raise NotImplementedError`:
- `def rrf_fuse(rankings: Sequence[Sequence[int]], *, k: int = RRF_K) -> list[tuple[int, float]]`
- `def build_fts_query(query: str) -> str | None`
- `def leading_extract(body: str) -> str`

**Frozen decisions and why:**
- **Variant names** — the step file's suggestions `MemoSearchScope` / `SessionSearchScope` /
  `EntrySearchScope` are adopted as frozen. They clash with nothing: the forbidden clash was with
  `models/memos.py`'s `MemoScope`, and `MemoSearchScope` is a distinct name that still reads as
  "the memo variant of a search scope", so `ports.py` can import `MemoScope` and declare
  `MemoSearchScope` side by side (it does).
- **`SearchHit`'s memo-level field names** — `memo_scope` / `memo_scope_id`, not bare `scope` /
  `scope_id`. Bare `scope` would read as the search *scope variant* on a module that also defines
  `SearchScope`; the `memo_` prefix also states at the call site that the pair is populated only
  for `kind == "memo"` (U3, D3).
- **Extra-predicate parameter type — `FromClause`.** It is the narrowest SQLAlchemy type that
  genuinely covers both relations step 002 passes: `Table` and `Subquery` are **both** subclasses
  of `FromClause` (verified: `issubclass(Table, FromClause) and issubclass(Subquery, FromClause)`
  is `True`), and `FromClause` is where `.c` / `.columns` is declared, which is the only thing a
  builder needs. `Selectable` would be looser without buying anything, and a bare `Select` — what
  `settled_entries` is at `db/schema.py:450` — is **not** a `FromClause`, which is exactly why
  `002.context.md` has step 002 call `.subquery()` before handing the relation to the builder.
  Return type is `ColumnElement[bool]`.
- **`k` is keyword-only on `rrf_fuse`**, default `RRF_K`. Keyword-only because an RRF call reads
  as "fuse these rankings" and a bare second positional `60` at a call site would be unreadable;
  it also matches the feature's keyword-only posture for tuning arguments (U1's `client_factory`
  / `timeout_seconds`). DoD-3's "with an explicit `k`" is therefore written `k=…`.
- `ExtraPredicateBuilder` and `SearchKind` are plain assignment aliases (no `TypeAlias`, no
  PEP 695 `type`), following `models/memos.py`'s `MemoScope` and `services/llm_registry.py:55`'s
  `LlmClientFactory`; ruff's `UP040` therefore does not apply.

**Gates:** `mypy app` → clean (75 files). `ruff check .` → clean. pytest not run.

**Caller-compile edits (out of Source-files scope):** None. Both files are new and nothing in the
repo imports `app.services.search` (harvest E16).

**Nothing withheld for F401:** every import in `ports.py` is used by a declaration, so the coder
adds no import to satisfy the stubs. Implementing the three bodies needs no import beyond the
standard library (`re` for the whitespace collapse is the coder's choice; `str.split()` /
`" ".join(...)` also suffices).

### Step 002 — frozen interface (2026-10-04)

Both files are **new**; nothing outside them was touched. Every symbol below is frozen — the coder
fills the four bodies and changes no signature.

`backend/app/services/search/candidates.py` — imports exactly `sqlalchemy.FromClause/Select` and
`app.services.search.ports.SearchScope`. No `fastapi`, no connection, no execution.

- `def base_relation(scope: SearchScope) -> FromClause` — **new**
- `def candidate_ids(scope: SearchScope) -> Select[tuple[int]]` — **new**

`backend/app/services/search/lexical.py` — imports exactly `dataclasses.dataclass`,
`typing.Final`, `sqlalchemy.Connection/Select`, `app.services.search.ports.ARM_DEPTH`. No
`fastapi`.

- `SNIPPET_TOKENS: Final[int] = 16` — **new**, the one declaration given its real value
  (`002.context.md` fixes the snippet window at 16 tokens; conventional, like D1's numbers). Name
  frozen; deliberately distinct from `ports.SNIPPET_CHARS` (160 **characters**, D4's leading
  extract) — the two are different units and must not be confused. The other fixed snippet
  parameters (column `0`, empty start/end markers, ellipsis `…`) stay inline in the statement and
  are **not** constants: only the token count was specified as one.
- `LexicalMatch` — **new**, `@dataclass(frozen=True)`, fields in this order, both defaultless:
  - `id: int` — the FTS `rowid`, which is `memos.id` / `messages.id` (external content,
    `content_rowid='id'`, harvest A2)
  - `snippet: str` — `snippet()`'s plain text
  Field names chosen to match `SearchHit.id` / `SearchHit.snippet` so step `004`'s hydration is a
  rename-free carry-over.
- `def fts_table_exists(connection: Connection, table_name: str) -> bool` — **new**
- `def lexical_ranking(connection: Connection, table_name: str, candidate_select: Select[tuple[int]], fts_expression: str | None, *, depth: int = ARM_DEPTH) -> list[LexicalMatch]` — **new**

**Frozen decisions and why:**

- **`base_relation` returns a fresh object for the entry variant, a shared one for the others — so
  it must be called once and its result reused.** `memos` and `sessions` are module-level `Table`
  singletons in `db/schema.py`, so repeated calls return the *identical* object; `settled_entries`
  is a `Select` (`db/schema.py:450`), and `.subquery()` mints a **new** `Subquery` on every call.
  Consequence, and the contract both `candidate_ids` and step `004` are bound by: **the object
  handed to `scope.extra_predicate` must be the very object the surrounding select reads from.**
  Two `base_relation(entry_scope)` calls give two distinct `Subquery` objects; a clause built
  against one and spliced into a select over the other compiles with an extra FROM (a silent
  cross join), not an error — exactly the failure mode `002.context.md`'s "one subquery object per
  call" sentence guards against. `candidate_ids` therefore calls `base_relation` **once** and
  passes that same object to the builder. No caching/memoisation of the subquery was added:
  a module-level cache keyed by scope would outlive the call and buy nothing, since one `search`
  call needs the relation once.
- **`.subquery()` is a new form in this codebase** (harvest B8: `session_index.py:86`,
  `messages.py:141-145`, `translation.py:188` all use `settled_entries` directly as a `Select` via
  `.selected_columns`, and none calls `.subquery()`). It is adopted here because the
  extra-predicate builder's parameter type is `FromClause` (frozen in step `001`) and a bare
  `Select` is **not** a `FromClause`. `IN (<subquery over settled_entries>)` was confirmed to work
  (harvest D15). Verified with mypy: `select(relation.c["id"]).where(relation.c["user_id"] == uid)`
  off a `FromClause` satisfies `Select[tuple[int]]` for both the `Table` and the `Subquery` case.
- **The delegated `SPEC` check is closed: no hand-back.** `settled_entries` projects `user_id`
  (harvest B7 — `select(messages)` projects every column; three existing services filter on it),
  so the entry variant's owner predicate reads the view and raw `messages` is never touched (R11).
- **`candidate_ids` returns `Select[tuple[int]]`**, the typing form already used in this codebase
  (`services/characters.py:222`, `sessions.py:291`, `setups.py:244`). It takes **no connection**,
  which is the signature-level statement that it executes nothing (D5).
- **`table_name: str`, not a `Literal["memo_fts", "message_fts"]`.** A `Literal` would re-type the
  virtual-table names as string literals inside a 025 module, which the feature forbids; the name
  arrives as one of `db/search_tables.py`'s constants and `lexical.py` imports nothing from
  `app.db` at all. Consequence: `lexical.py` names no table itself, so the "only through 024's
  constants" rule is held at the call site (step `004`) and in tests.
- **`depth` is keyword-only**, default `ARM_DEPTH` — same posture as step `001`'s `rrf_fuse(…, *,
  k=RRF_K)` and 024's `open_embedding_model` for tuning arguments. DoD-8 is therefore written
  `depth=…`. The other four parameters are positional-or-keyword, in the step file's order.
- **`fts_expression: str | None`** takes `build_fts_query`'s output *unchanged*, so the
  none-short-circuit lives in the arm rather than at every call site. This is load-bearing:
  `MATCH ''` raises `fts5: syntax error near ""` (harvest headline 2 / D14).
- **No per-variant public helpers** (`memo_candidates` etc.) were added — the two names in the
  Interface intent are the whole surface; variant dispatch is internal to `base_relation`.

**Deferred imports** (not present in the stubs, because every import must be used — ruff `F401`;
the coder adds them when filling the bodies):

- `candidates.py` — `sqlalchemy.select` / `and_`; `app.db.schema.memos`, `sessions`,
  `settled_entries`.
- `lexical.py` — the statement builders (`sqlalchemy.text` and/or `table` / `column` /
  `literal_column` / `func` / `select`, per `002.context.md`'s "`text()` or a lightweight
  `table()`/`column()` construct"). Nothing from `app.db` is needed. No `# type: ignore` is
  needed anywhere (`sqlite_vec` is step `003`'s problem, not this step's), which matters because
  `warn_unused_ignores` is on.

**Gates:** `mypy app` → clean (77 files). `ruff check .` → clean. pytest not run.

**Caller-compile edits (out of Source-files scope):** None. Both files are new and nothing imports
`app.services.search` (harvest E16).

### Step 003 — frozen interface (2026-10-04)

`backend/app/services/search/vector.py` — **new**, and the only file touched. One public symbol,
frozen; the coder fills the one body and changes no signature.

- `def vector_ranking(connection: Connection, table_name: str, candidate_select: Select[tuple[int]], query_text: str, *, depth: int = ARM_DEPTH, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> list[int]` — **new**

Imports present in the stub are exactly `sqlalchemy.Connection/Select`,
`app.services.embedding.DEFAULT_EMBED_TIMEOUT_SECONDS`, `app.services.llm.client.LlmClient`,
`app.services.llm_registry.LlmClientFactory`, `app.services.search.ports.ARM_DEPTH` — every one is
used by the signature itself, so none is withheld for `F401`. No `# type: ignore` is present (and
`warn_unused_ignores` is on, so none may be added speculatively).

**Frozen decisions and why:**

- **Return type is a plain `list[int]`** — the ranking itself, nothing richer. Three reasons, all
  from the contract: the step file says "returns a ranking: at most `depth` distinct ids"; step
  `004` feeds the result **straight into** `rrf_fuse(rankings: Sequence[Sequence[int]], …)` (frozen
  in step `001`), which takes rankings of ids, so `list[int]` is a zero-adaptation hand-off; and the
  vector arm has **no second payload to carry** — unlike the lexical arm, whose `LexicalMatch`
  exists only because FTS5's `snippet()` text has to reach hydration (D4). Distances are
  deliberately **not** returned: D1 fuses by rank only, so exposing a raw L2 value would invite
  exactly the score-mixing the architecture forbids, and a vector-only memo hit's snippet is the
  **leading extract of `body`** (D4), hydrated in step `004` from `memos`, not from this arm. The
  list is the ranking's order: ascending L2 distance, ties by ascending id.
- **No private helper is declared.** The Interface intent names one symbol and `003.context.md`
  specifies one statement; a `_key_column(...)` or `_scan(...)` stub would be surface the test-coder
  cannot bind to and the coder may not need in that shape. Private helpers are the coder's choice,
  as in step `004`'s step file. Nothing in the frozen contract depends on their existence.
- **`depth` is keyword-only**, default `ARM_DEPTH` — the same posture as step `002`'s
  `lexical_ranking(…, *, depth=ARM_DEPTH)` and step `001`'s `rrf_fuse(…, *, k=RRF_K)`. DoD-5 is
  therefore written `depth=…`.
- **`client_factory` / `timeout_seconds` are keyword-only too**, defaulting to `LlmClient` and
  `DEFAULT_EMBED_TIMEOUT_SECONDS` — 024 D9's pattern, copied from
  `open_embedding_model(connection, *, client_factory=LlmClient, timeout_seconds=DEFAULT_EMBED_TIMEOUT_SECONDS)`
  (harvest A3) so the three arguments pass straight through. The timeout default **references the
  constant**, never a numeric literal (its value is derived from `config.py` and was deliberately
  not looked up). `LlmClientFactory` is imported from `app.services.llm_registry` and `LlmClient`
  from `app.services.llm.client`, the two paths `embedding.py` already uses.
- **`table_name: str`, not a `Literal`** — identical reasoning to step `002`'s `lexical_ranking`: a
  `Literal["memo_vec", "session_vec"]` would re-type the virtual-table names as string literals
  inside a 025 module, which `context.md` forbids. The name arrives as one of
  `app.db.search_tables`'s constants, supplied by step `004` and by the tests, so `vector.py`'s
  stub names no table at all.
- **Parameter order and names** follow the Interface intent's prose order
  (connection, table, candidate select, query text) and step `002`'s names (`table_name`,
  `candidate_select`), so the two arms read alike at step `004`'s call sites. `query_text` rather
  than `query` distinguishes the raw text from the sanitised FTS expression the other arm takes.

**DoD-11 source-scan confirmations** (verified by `grep` on the written file):

- The source contains **no `MATCH` substring** — zero occurrences, including in the module
  docstring, the function docstring and comments. The forbidden vec0 nearest-neighbour form **is**
  documented (it is the reason the exact scan exists), but phrased without the token: "the one that
  pushes a `k` limit and an id restriction down into the virtual table".
- The source contains **no occurrence of the string `fastapi`** either — not just no import of it.
  The docstring says "imports nothing from the web framework", borrowing `embedding.py`'s phrasing,
  so DoD-11 holds whether the test-coder writes it as an import check or as a bare substring scan.
  (Step `001`'s `ports.py` docstring does spell the word; this module deliberately does not,
  because DoD-11 bundles the claim with a substring scan.)
- The stub creates and writes nothing: its only statement is `raise NotImplementedError`, and it
  imports nothing from `app.db` at all (so `ensure_vector_tables` is not even reachable from here).

**Deferred imports** (absent from the stub because every import must be used — ruff `F401`; the
coder adds them when filling the body):

- `import sqlite_vec  # type: ignore[import-untyped]` — the ignore **is** required
  (`embedding.py:44` is the precedent) and, with `warn_unused_ignores` on, must not be added until
  the import is. Used for `sqlite_vec.serialize_float32(vector)`, which yields the raw
  little-endian float32 `bytes` bound as `:query_vector` (harvest A4).
- `app.db.search_tables.vector_table_dimension`, plus `MEMO_VEC_TABLE` / `SESSION_VEC_TABLE` if the
  coder resolves the key column through a module-level mapping. **The key column per table is
  `memo_id` for `memo_vec` and `session_id` for `session_vec`** (024's private
  `_VECTOR_KEY_COLUMNS`, harvest A2); `rowid` is **unusable** on a vec0 table — `SELECT rowid FROM
  memo_vec` raises `no such column: rowid` (harvest A4, verified) — so the statement must name the
  key column, both in the projection and in the `ORDER BY` tiebreak. Deriving it via
  `pragma_table_info` (as 024's `write_vector` does) is the alternative and is equally acceptable;
  the skeleton does not freeze the mechanism, only the behaviour.
- `app.services.embedding.open_embedding_model` and `embed_texts` (`DEFAULT_EMBED_TIMEOUT_SECONDS`
  from the same module is already imported).
- `app.errors.NoEmbeddingModelError` for the pre-embed width guard. It has **no default message**
  (harvest C11), so the raise site passes a fixed one — `003.context.md` suggests "The embedding
  index was built for a different dimension; an administrator must rebuild it.", which is also 024's
  `_DIMENSION_MISMATCH_MESSAGE` text — with `detail` exactly `{"reason": "dimension_mismatch"}`.
  `errors.py` is not edited.
- The statement builders (`sqlalchemy.text` and/or `table` / `column` / `select`) and
  `contextlib.contextmanager` / `collections.abc.Iterator` if the coder replicates D7's local
  `_reading` helper — which is needed: `vector_table_dimension` **autobegins a read** (harvest A1),
  so a caller outside a transaction must roll back. `embed_texts` uses `asyncio.run`, so it must not
  be called from inside a running loop (no 025 caller is).

**Gates:** `mypy app` → clean (78 source files). `ruff check .` → clean. pytest **not** run.

**Caller-compile edits (out of Source-files scope):** None. `vector.py` is new, nothing in the repo
imports `app.services.search` (harvest E16), and no existing file was read-modified.

### Step 004 — frozen interface (2026-10-04)

`backend/app/services/search/hybrid.py` — **new**, and the only file touched. One public symbol,
frozen; the coder fills the one body and changes no signature.

- `def search(connection: Connection, scope: SearchScope, query_text: str, limit: int, *, client_factory: LlmClientFactory = LlmClient, timeout_seconds: float = DEFAULT_EMBED_TIMEOUT_SECONDS) -> list[SearchHit]` — **new**

Imports present in the stub are exactly `sqlalchemy.Connection`,
`app.services.embedding.DEFAULT_EMBED_TIMEOUT_SECONDS`, `app.services.llm.client.LlmClient`,
`app.services.llm_registry.LlmClientFactory`, `app.services.search.ports.SearchHit/SearchScope` —
every one is used by the signature itself, so none is withheld for `F401`. No `# type: ignore` is
present (`warn_unused_ignores` is on, so none may be added speculatively).

**READ THIS FIRST — `base_relation` must be called ONCE per statement and that one object reused.**
This is the subtlest trap in the feature, and this step's coder is the one who can trip it. For the
**entry** variant `base_relation` returns a **fresh `.subquery()` on every call** (step `002`'s
record; `memos` / `sessions` are module-level `Table` singletons, so only the entry variant bites).
A statement that calls it twice — once to reach `.c["user_id"]` / `.c["id"]`, once as the FROM —
compiles an **extra FROM**, i.e. a silent cross join, and **raises nothing**: the tests then fail as
wrong rows, not as an error. Every statement built in `hybrid.py` must therefore bind one
`base_relation(scope)` result to a local name and use that same object for its columns and its FROM.
The entry hydration read is the only place in this step that needs the relation at all
(`SELECT id, session_id FROM <one subquery> WHERE user_id = :u AND id IN (:kept)`); the memo
hydration read may equally use `app.db.schema.memos` directly, since that is the identical object
`base_relation` hands back for that variant. `candidate_ids(scope)` already holds the same discipline
internally, and is itself called **once** per search.

**Frozen decisions and why:**

- **`limit` is positional-or-keyword (the fourth positional parameter), required, with no default.**
  Three reasons. (a) It is a **required domain argument**, not a tuning knob: this feature's
  keyword-only posture (`rrf_fuse(*, k=RRF_K)`, `lexical_ranking(*, depth=ARM_DEPTH)`,
  `vector_ranking(*, depth=…, client_factory=…, timeout_seconds=…)`) is reserved for parameters that
  carry defaults, and `limit` deliberately has none — a default result count would hide a tool's
  budget from the four later callers (`026`–`029`) and make "how many did I ask for?" invisible at the
  call site. (b) U1's prose fixes the order: "a connection first, a scope, the query text and a limit,
  **plus** keyword-only `client_factory` and `timeout_seconds`" — the `*` goes exactly where the word
  "plus" is, so `limit` stays positional. (c) Positional-or-keyword is the superset: a caller that
  wants the ergonomics writes `search(conn, scope, text, limit=5)` (and `026`–`029` are encouraged to,
  since a bare trailing integer reads poorly), while a keyword-only `limit` would have forbidden the
  terse four-positional form. The three leading parameters are likewise positional-or-keyword, in U1's
  order.
- **`search` takes the raw query text** and owns both transformations — the vector arm embeds it
  verbatim, the lexical arm consumes `build_fts_query(query_text)`. Callers never pre-sanitise, so
  D2's blank-query exit has exactly one home.
- **No private helpers are frozen.** Per-kind hydration and arm dispatch are the coder's choice (the
  step file says so explicitly), and step `003` set the precedent: a `_hydrate_memos(...)` or
  `_run_arms(...)` stub would be surface the test-coder cannot bind to (the tests bind to `search`
  alone) and would pre-commit the coder to a decomposition that may not fit. Nothing in the frozen
  contract depends on any private name existing. The D7 `_reading` context manager is **not** declared
  either — its body is behaviour; it is listed under deferred imports below.
- **Return type is `list[SearchHit]`**, not a tuple or a wrapper: the Interface intent says "a list of
  at most `limit` `SearchHit` values", nothing carries a total count, and the ordering guarantees live
  in the docstring (descending fused score, ties by **ascending id**, D1). `SearchHit`'s field names
  (`kind`, `id`, `score`, `snippet`, `memo_scope`, `memo_scope_id`, `session_id`) and `MemoScope`'s
  typing are step `001`'s frozen record — this step re-declares nothing and adds no field (US-119: a
  memo hit has no title, ever).
- **`client_factory` / `timeout_seconds` keyword-only, defaulting to `LlmClient` and
  `DEFAULT_EMBED_TIMEOUT_SECONDS`** — 024 D9's pattern, identical to `vector_ranking`'s, so the two
  arguments pass straight through with no adaptation. The timeout default **references the constant**,
  never a numeric literal. They are accepted even by variants with no vector arm (the signature is one
  per port, not one per variant) and are simply never used there: U2's "the entry scope never touches
  the model" is a behaviour, not a signature difference.
- **Binding to the frozen arms is rename-free by construction:** `candidate_ids(scope) ->
  Select[tuple[int]]` feeds both arms; `vector_ranking(...) -> list[int]` is a ranking `rrf_fuse`
  consumes directly; `lexical_ranking(..., *, depth=ARM_DEPTH) -> list[LexicalMatch]` carries
  `LexicalMatch.id` / `.snippet`, whose names already match `SearchHit.id` / `.snippet`, so lexical
  snippets are **kept by id from the arm's return value** and FTS is never re-queried
  (`004.context.md`). `rrf_fuse`'s `k` is keyword-only.
- **Arm order inside a memo search is vector first**, recorded in the module docstring so the
  constraint survives into the implementation: it makes DoD-10's "raises even though `memo_fts` holds
  a match" the cheapest path.

**DoD-15 and the feature constraints, verified on the written file:**

- `hybrid.py` imports no `fastapi` and nothing from the vector extension — the source contains
  **neither substring at all** (`'fastapi' in text` and `'sqlite' in text` are both `False`), so
  DoD-15 holds whether the test-coder writes it as an import check or as a source scan. The docstring
  says "nothing from the web framework and nothing from the vector extension (only the vector arm
  does)".
- It imports nothing from `app.db`, so 024's `ensure_fts_tables` / `ensure_vector_tables` are not even
  reachable from here — "025 creates no table" holds at the import level. The four virtual-table name
  constants are a **deferred** import: this step is where the tables are named, and the names must
  arrive from `app.db.search_tables`, never as string literals.
- `app/services/__init__.py` was **not** touched (harvest E17 / `test_config.py:198`).

**Deferred imports** (absent from the stub because every import must be used — ruff `F401`; the coder
adds them when filling the body):

- `app.db.search_tables.MEMO_FTS_TABLE`, `MESSAGE_FTS_TABLE`, `MEMO_VEC_TABLE`, `SESSION_VEC_TABLE` —
  the only permitted spelling of the four virtual-table names.
- `app.services.search.candidates.candidate_ids`, plus `base_relation` and/or `app.db.schema.memos`
  and `sqlalchemy.select` for the two hydration reads.
- `app.services.search.lexical.lexical_ranking` (and `LexicalMatch`, if the coder annotates an
  intermediate mapping), `app.services.search.vector.vector_ranking`.
- `app.services.search.ports.build_fts_query`, `leading_extract`, `rrf_fuse`. `ARM_DEPTH` is **not**
  needed here — both arms default to it.
- `contextlib.contextmanager` and `collections.abc.Iterator` for the **locally replicated** `_reading`
  (harvest C10 — five existing private copies are the precedent; it is private and is **never**
  imported from another module). It is needed for the same reason as in the vector arm: every read
  autobegins, and `vector_table_dimension` autobegins one too (harvest A1).

**Gates:** `mypy app` → clean (79 source files). `ruff check .` → clean. pytest **not** run.

**Caller-compile edits (out of Source-files scope):** None. `hybrid.py` is new, nothing in the repo
imports `app.services.search` (harvest E16), and no existing file was read-modified.

## Tests

### Step 001 — tests (2026-10-04)

`backend/tests/test_search_ports.py` — **new**, the only file written. Covers DoD-1 … DoD-10
(no `[manual/live]` item in this step). Bound to the `## Skeleton` step-001 signatures
(`rrf_fuse(rankings, *, k=RRF_K)` — `k` keyword-only, `build_fts_query(query)`,
`leading_extract(body)`, the three variants' `user_id` / `extra_predicate` fields). No DB
fixture is used and `tests/conftest.py` is untouched; the DoD-7 FTS5 table is built on a
private `sqlite3.connect(":memory:")` connection (`backend/data/` never touched). pytest
**not** run.

| Test | DoD | Asserts |
|---|---|---|
| `test_scope_variant_without_user_id_raises__S025_001_DoD1` (×3 variants) | 1 | `TypeError` without `user_id` |
| `test_scope_variant_with_only_user_id_has_no_extra_predicate__S025_001_DoD1` (×3) | 1 | `extra_predicate is None` by default |
| `test_scope_variant_is_immutable__S025_001_DoD1` (×3) | 1 | assigning either field raises `AttributeError` (covers `FrozenInstanceError`) |
| `test_rrf_fuse_over_two_rankings_scores_and_order__S025_001_DoD2` | 2 | `[[101,999,202],[202,303]]` → order `202, 101, 303, 999`; scores `1/61`, `1/62`, `1/63+1/61`, `1/62` within float tolerance; ids picked so the `999`/`303` tie must break by **ascending id**, not insertion order |
| `test_rrf_fuse_covers_every_id_exactly_once__S025_001_DoD2` | 2 | every id from any ranking appears exactly once |
| `test_rrf_fuse_single_ranking_keeps_order_and_scores__S025_001_DoD3` | 3 | one ranking → same order, `1/(60+rank)` |
| `test_rrf_fuse_uses_explicit_k__S025_001_DoD3` | 3 | `k=1` → `1/2`, `1/3` (keyword-only call) |
| `test_rrf_fuse_with_no_rankings_returns_empty__S025_001_DoD3` | 3 | `rrf_fuse([]) == []` |
| `test_rrf_fuse_with_only_empty_rankings_returns_empty__S025_001_DoD3` | 3 | `rrf_fuse([[], []]) == []` |
| `test_rrf_fuse_tie_break_is_independent_of_input_order__S025_001_DoD4` | 4 | three all-tied ids in two input orders → identical ascending-id output |
| `test_rrf_fuse_tie_within_mixed_rankings_is_order_independent__S025_001_DoD4` | 4 | DoD-2's rankings swapped → identical order |
| `test_build_fts_query_returns_none_for_empty_text__S025_001_DoD5` | 5 | `""` → none (rule 6) |
| `test_build_fts_query_returns_none_for_whitespace_only_text__S025_001_DoD5` | 5 | spaces/tabs/newlines → none |
| `test_build_fts_query_returns_none_for_quotes_and_whitespace_only__S025_001_DoD5` | 5 | only `"` + whitespace → none |
| `test_build_fts_query_quotes_and_or_joins_tokens__S025_001_DoD6` | 6 | `"Kaelith inn"` → `"Kaelith" OR "inn"` exactly |
| `test_build_fts_query_removes_every_quote_from_a_token__S025_001_DoD6` | 6 | every `"` removed before quoting |
| `test_build_fts_query_splits_on_whitespace_runs_without_empty_phrase__S025_001_DoD6` | 6 | newline/tab/space runs separate tokens; no `""` in the output |
| `test_build_fts_query_keeps_a_token_that_tokenises_to_nothing__S025_001_DoD6` | 6 | `---` is kept as a phrase, not filtered |
| `test_hostile_input_never_raises_as_fts_match__S025_001_DoD7` (×11 inputs) | 7 | each hostile input's non-none expression runs as `MATCH` against a test-created `fts5` table without raising |
| `test_every_hostile_input_survives_a_single_match_sweep__S025_001_DoD7` | 7 | all eleven in one sweep, no error |
| `test_leading_extract_collapses_whitespace_and_strips_short_body__S025_001_DoD8` | 8 | whitespace runs → one space, ends stripped |
| `test_leading_extract_returns_a_body_of_exactly_snippet_chars_unchanged__S025_001_DoD8` | 8 | exactly `SNIPPET_CHARS` → unchanged (the "longer than" is strict) |
| `test_leading_extract_truncates_a_longer_body_with_an_ellipsis__S025_001_DoD8` | 8 | longer → first `SNIPPET_CHARS` + `…`, total `SNIPPET_CHARS + 1` |
| `test_leading_extract_collapses_before_truncating__S025_001_DoD8` | 8 | the cut counts *collapsed* characters |
| `test_module_constants_have_their_specified_values__S025_001_DoD9` | 9 | `RRF_K == 60`, `ARM_DEPTH == 50`, `SNIPPET_CHARS == 160` |
| `test_ports_imports_no_fastapi_and_no_sqlite_vec__S025_001_DoD10` | 10 | AST import walk (`test_bootstrap_service.py:529-548` idiom) finds no `fastapi`/`starlette`/`sqlite_vec` |
| `test_ports_imports_nothing_from_app_db_engine__S025_001_DoD10` | 10 | same walk finds no `app.db.engine` import |

- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓

### Step 002 — tests (2026-10-04)

`backend/tests/test_search_lexical.py` — **new**, the only file written. Covers DoD-1 … DoD-11
(no `[manual/live]` item in this step). Bound to the `## Skeleton` step-002 signatures
(`candidate_ids(scope)`, `LexicalMatch(id, snippet)`, `fts_table_exists(connection, table_name)`,
`lexical_ranking(connection, table_name, candidate_select, fts_expression, *, depth=ARM_DEPTH)` —
`depth` keyword-only, `SNIPPET_TOKENS`) and step 001's three scope variants plus
`ExtraPredicateBuilder`. `base_relation` is exercised only through `candidate_ids`, which the frozen
record says calls it **once** and hands that same object to the builder — so no test ever builds a
clause against a second `base_relation` call (the silent extra-FROM trap). pytest **not** run.

Mechanics: `db_settings` / `db_engine` only — **`tests/conftest.py` untouched**; every fixture and
seeding helper is file-local and raw-inserts rows with ids **above 2^60**; **two users** throughout;
the FTS tables are created only via 024's `ensure_fts_tables` in a committed transaction *after* the
inserts (back-fill), and the two DoD-10 tests never ensure. The virtual tables are named only
through 024's `MEMO_FTS_TABLE` / `MESSAGE_FTS_TABLE`. No monkeypatching, no embedding model, no
network. The single-token FTS expression is the file-local literal `"kaelith"` — exactly step 001's
documented output shape — so step 002 is falsifiable without step 001's body.

| Test | DoD | Asserts |
|---|---|---|
| `test_memo_candidates_are_only_the_scope_users__S025_002_DoD1` | 1 | memo candidates == the scope user's two ids; the other owner's id absent |
| `test_session_candidates_are_only_the_scope_users__S025_002_DoD1` | 1 | session candidates == the scope user's two sessions; the other owner's absent |
| `test_entry_candidates_are_only_the_scope_users__S025_002_DoD1` | 1 | entry candidates == the scope user's two record rows; the other owner's absent |
| `test_other_users_candidates_are_never_visible_in_either_direction__S025_002_DoD1` | 1 | the absence is symmetric — each owner sees exactly their own id |
| `test_memo_extra_predicate_excludes_a_disabled_memo__S025_002_DoD2` | 2 | `is_enabled` builder drops the same user's disabled memo; the other owner's **enabled** memo is still dropped (owner clause ANDed) |
| `test_session_extra_predicate_selects_one_character__S025_002_DoD2` | 2 | `character_id = X` drops the same user's other-character session; a `USER_B` session seeded under `CHARACTER_A1` (satisfies the extra predicate) is still dropped |
| `test_entry_extra_predicate_selects_one_session__S025_002_DoD2` | 2 | `session_id = S` drops the same user's record row in the other session; a `USER_B` record row inside `USER_A`'s session is still dropped |
| `test_entry_candidates_exclude_zone_and_buried_rows__S025_002_DoD3` | 3 | same user + same session: record row in; zone (`settled_at` null) and buried (`related_to` set, `settled_at` null per the CHECK) out |
| `test_lexical_ranking_orders_the_stronger_bm25_match_first__S025_002_DoD4` | 4 | token twice in a 3-token body **before** token once in a 49-token body (BM25's definition); the non-matching memo absent. Ids chosen so an id-ordered result would be reversed; **no magnitude asserted** |
| `test_lexical_ranking_omits_another_users_indexed_memo__S025_002_DoD5` | 5 | the other user's memo with the same token is absent although `memo_fts` indexes every memo |
| `test_lexical_ranking_omits_a_memo_excluded_by_the_extra_predicate__S025_002_DoD5` | 5 | an indexed but extra-predicate-excluded memo of the **same** user is absent |
| `test_snippets_are_plain_text_containing_the_token__S025_002_DoD6` | 6 | each snippet is a `str` containing the token with none of `<`, `>`, `[`, `]` |
| `test_a_body_longer_than_the_snippet_window_is_cut_with_an_ellipsis__S025_002_DoD6` | 6 | a body of `SNIPPET_TOKENS * 3 + 1` tokens yields a snippet containing `…` and the token, and not the whole body |
| `test_entry_lexical_ranking_returns_the_matching_record_row__S025_002_DoD7` | 7 | over `message_fts`, the entry candidate set yields exactly the matching record row's message id, snippet containing the token |
| `test_depth_caps_the_number_of_matches__S025_002_DoD8` | 8 | 5 matching candidates, `depth=3` (keyword-only) → exactly 3 distinct ids, all from the seeded set |
| `test_a_snowflake_id_round_trips_through_the_lexical_arm__S025_002_DoD9` | 9 | the returned id `==` the inserted id above 2^60, exactly |
| `test_a_snowflake_id_round_trips_through_the_candidate_set__S025_002_DoD9` | 9 | the same id through `candidate_ids` and through `message_fts` |
| `test_an_absent_fts_table_yields_no_matches_and_no_error__S025_002_DoD10` | 10 | never ensured: `lexical_ranking` → `[]` for both tables, raising nothing (rows that would match exist) |
| `test_fts_table_exists_is_false_before_the_ensure_and_true_after__S025_002_DoD10` | 10 | `fts_table_exists` `is False` before the ensure and `is True` after, for both tables |
| `test_a_none_fts_expression_yields_no_matches__S025_002_DoD11` | 11 | expression `None` → `[]` with the table present and holding a match (the guard that keeps `MATCH ''` from ever being issued) |

- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓

### Step 003 — tests (2026-10-04)

`backend/tests/test_search_vector.py` — **new**, the only file written. Covers DoD-1 … DoD-11
(no `[manual/live]` item in this step). Bound to the `## Skeleton` step-003 signature
`vector_ranking(connection, table_name, candidate_select, query_text, *, depth=ARM_DEPTH,
client_factory=LlmClient, timeout_seconds=DEFAULT_EMBED_TIMEOUT_SECONDS) -> list[int]` —
**`depth` / `client_factory` keyword-only**, return value a plain id list — plus step 002's
`candidate_ids(scope)`, step 001's `MemoSearchScope` / `SessionSearchScope` /
`ExtraPredicateBuilder` / `ARM_DEPTH`. pytest **not** run.

**How the expected order is derived (no implementation was consulted).** Every ranked row's
stored vector is `llm_fakes.embedding_vector(<source text>, 8)`; the test computes the expected
ranking itself with a plain-Python L2 (`math.dist`) and ties by **ascending id**. The comparison
is exact with no tolerance, and that is sound rather than lucky: components are multiples of
`2**-8` in `(-1, 1)`, so each squared difference is a multiple of `2**-16` and the 8-term sum is
an integer multiple of `2**-16` below 8 — exactly representable in float32. Distinct distances
therefore differ far beyond float32 resolution, and mathematically equal distances are
bit-identical, so a tie falls through to the ascending-id tiebreak on both sides. A row whose
"source text" *is* the query text therefore stores the query vector exactly (distance 0) — the
device DoD-3 and DoD-4 use.

Mechanics (`context.md` "Test conventions"): `db_settings` / `db_engine` only — **`conftest.py`
untouched**, **`llm_fakes.py` untouched**; every fixture and helper is file-local; all ids are
**above 2^60**; **two users** throughout; vec tables created only via 024's
`ensure_vector_tables` and written only via 024's `write_vector`, named only through 024's
`MEMO_VEC_TABLE` / `SESSION_VEC_TABLE`; a designated model is a raw `llm_servers` + `models` pair
(`is_enabled`, `is_embedding_designated`, `embedding_dim=8`) with `api_key_ref=None`, so no
environment variable and **no monkeypatching** anywhere; the provider arrives through
`client_factory=` (`fake_factory` / `unreachable_factory`). No network.

| Test | DoD | Asserts |
|---|---|---|
| `test_the_ranking_is_ordered_by_ascending_l2_distance__S025_003_DoD1` | 1 | four of one user's memos, `memo_vec` at 8 → ranking **==** the test's brute-force ascending-L2 order |
| `test_every_ranked_id_is_the_exact_snowflake_id_written__S025_003_DoD1` | 1 | the ids round-trip through the vec0 key column exactly (all above 2^60) |
| `test_no_true_candidate_is_missing_at_snowflake_ids__S025_003_DoD2` | 2 | **the snowflake-correctness proof.** **200 candidates + 200 non-candidates** (400 rows, all with vectors), ids above 2^60 with a **prime stride (104 729) and interleaved** so no range separates the sets, `depth=25` ≪ 200; for **8 distinct query texts** the ranking **==** the brute-force top-25 over the **candidates only**, and is disjoint from the non-candidates |
| `test_a_nearer_non_candidate_does_not_displace_a_candidate__S025_003_DoD2` | 2 | same 400 rows, **8 query texts**: asserts the fixture is *discriminating* — at least one query has a non-candidate strictly nearer than the furthest kept candidate — and the kept set is still candidate-only top-25 |
| `test_another_users_exact_match_is_absent_from_the_memo_ranking__S025_003_DoD3` | 3 | the other owner's vector **equals the query vector exactly** (distance 0) and is still absent; the rest equals brute force |
| `test_a_memo_excluded_by_the_extra_predicate_is_absent_at_distance_zero__S025_003_DoD3` | 3 | same owner, disabled, vector == query vector → absent under the `is_enabled` builder |
| `test_the_session_ranking_is_only_the_scope_users_sessions__S025_003_DoD4` | 4 | `session_vec` + session variant: the other owner's distance-0 session absent, order == brute force |
| `test_the_session_ranking_honours_the_character_extra_predicate__S025_003_DoD4` | 4 | `character_id` builder: the other character's session **and** a `USER_B` session seeded under `USER_A`'s character (satisfies the extra predicate) are both absent though both carry the query vector exactly |
| `test_depth_caps_the_ranking__S025_003_DoD5` | 5 | 5 vectored candidates, `depth=3` (keyword-only) → exactly 3 distinct ids == brute-force top-3 |
| `test_a_candidate_without_a_vector_row_is_simply_not_ranked__S025_003_DoD5` | 5 | a candidate with **no vector row** is absent and **nothing raises** |
| `test_an_empty_but_present_vec_table_returns_no_ranking__S025_003_DoD5` | 5 | table ensured at 8, zero rows, candidates exist → `[]` for both vec tables |
| `test_no_designated_model_raises_and_builds_no_client__S025_003_DoD6` | 6 | `NoEmbeddingModelError` and `factory.call_count == 0` with the table present and populated |
| `test_no_designated_model_raises_even_with_the_vec_table_absent__S025_003_DoD6` | 6 | **model first, table second**: still raises with `memo_vec` absent (pinned via `vector_table_dimension(...) is None`), `call_count == 0` — no silent degrade |
| `test_an_undesignated_model_row_still_raises__S025_003_DoD6` | 6 | an enabled-but-undesignated registry row is no substitute (R4) |
| `test_an_unreachable_provider_propagates_its_error__S025_003_DoD7` | 7 | `unreachable_factory` → `LlmUnreachableError` propagates; one recorded `embed` call proves the embed step was reached |
| `test_an_absent_vec_table_returns_no_ranking_and_embeds_nothing__S025_003_DoD8` | 8 | table absent **with** a designated model → `[]` for both vec tables and `factory.embed_calls == []` (the table check sits after opening the model, before embedding) |
| `test_a_table_narrower_than_the_designation_raises_dimension_mismatch__S025_003_DoD9` | 9 | table at 8, model designated at 16 → `NoEmbeddingModelError`, `code == "no_embedding_model"`, `detail == {"reason": "dimension_mismatch"}` **exactly**, `embed_calls == []`, non-empty fixed message |
| `test_exactly_one_embed_call_carries_the_model_and_the_query__S025_003_DoD10` | 10 | `factory.embed_calls == [(MODEL_NAME, (QUERY_TEXT,))]` — exactly one call, the designated model name, exactly the one query text |
| `test_the_vector_module_contains_no_match_operator__S025_003_DoD11` | 11 | plain substring scan: `"MATCH" not in inspect.getsource(vector_module)` |
| `test_the_vector_module_imports_no_fastapi__S025_003_DoD11` | 11 | AST import walk finds no `fastapi` / `starlette` import |
| `test_the_vector_module_binds_no_fastapi_symbol__S025_003_DoD11` | 11 | no module-level name is a fastapi/starlette object |

- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓

### Step 004 — tests (2026-10-04)

`backend/tests/test_search_hybrid.py` — **new**, the only file written. Covers DoD-1 … DoD-15 (no
`[manual/live]` item in this step). Bound to the `## Skeleton` step-004 signature
`search(connection, scope, query_text, limit, *, client_factory=LlmClient,
timeout_seconds=DEFAULT_EMBED_TIMEOUT_SECONDS) -> list[SearchHit]` — **`limit` is the fourth
positional-or-keyword parameter and defaultless** (both the positional and the `limit=` form are
exercised, DoD-14), `client_factory` keyword-only — plus step 001's `SearchHit` (its seven field
names) and the three scope variants. pytest **not** run.

**How the expectations are derived (no implementation was consulted).** D1's fusion is
re-implemented **locally** as `_rrf_fuse` from the plan's words (`Σ 1/(k + rank)`, 1-based rank,
`k = 60`, ties by ascending id) and D4's leading extract as `_leading_extract`, so no expected
value comes from `ports`. `RRF_K` / `ARM_DEPTH` / `SNIPPET_CHARS` appear as the spec's literals
(60 / 50 / 160). The vector arm's ranking is brute-forced by the test from `llm_fakes`'
**pure** `embedding_vector(text, 8)` plus `math.dist`, ties by ascending id, cut at `ARM_DEPTH`
(exact, no tolerance — the fake's components are exactly float32-representable). Lexical
membership is "which bodies contain the token"; where BM25's order would be ambiguous the fixture
seeds **exactly one** match, otherwise it uses the one ordering BM25's *definition* fixes (token
twice in a 3-token body before once in a 49-token body). **No BM25 magnitude is ever asserted.**
Score comparisons use `pytest.approx`; id/order comparisons are exact.

Mechanics (`context.md` "Test conventions"): `db_engine` only — **`tests/conftest.py` and
`tests/llm_fakes.py` untouched**; every fixture and helper file-local; all ids **above 2^60**;
**two users** throughout; the four virtual tables created only via 024's `ensure_fts_tables` /
`ensure_vector_tables` (FTS always *after* the inserts, so the back-fill indexes them; never
ensured twice), written only via `write_vector`, named only through 024's constants; a designated
model is a raw `llm_servers` + `models` pair (`is_enabled`, `is_embedding_designated`,
`embedding_dim=8`, `api_key_ref=None`); the provider arrives through `client_factory=`
(`fake_factory` / `unreachable_factory`). **No monkeypatching**, no network. Table *absence* is
asserted with a file-local `sqlite_master` probe rather than through step 002's helper.

| Test | DoD | Asserts |
|---|---|---|
| `test_memo_hybrid_ids_order_and_scores_are_the_fused_arms__S025_004_DoD1` | 1 | 4 vectored + FTS-indexed memos, exactly one body holding the token (so its lexical rank is unambiguously 1): ids, order **and** scores == local `_rrf_fuse([vector_ranking, [MEMO_TWO]])[:3]` |
| `test_every_memo_hit_carries_its_level_no_session_and_a_snippet__S025_004_DoD1` | 1 | every hit: kind `"memo"`, `memo_scope`/`memo_scope_id`, `session_id is None`, snippet a **non-empty** `str` |
| `test_lexical_rescues_a_memo_outside_the_vector_arm__S025_004_DoD2` | 2 | **60 memos** (`RESCUE_MEMO_COUNT = 59 fillers + 1 target` > `ARM_DEPTH` 50), all vectored. The 59 filler vectors take the pool texts **nearest** the query vector and the target's the **farthest**, so the target's rank is 60 **by construction**; the test then verifies it from the pure function (`full_order.index(target) + 1 == 60` and `> ARM_DEPTH`, `target not in vector_arm`, `len(vector_arm) == ARM_DEPTH`). The target's body is the only one holding the rare token ⇒ present with score **exactly `1/(60+1)`**, and the whole result == the fused prefix |
| `test_memo_snippet_shapes_per_arm__S025_004_DoD3` | 3 | lexically-found hit's snippet **contains** the token; vector-only hit's snippet **==** `_leading_extract(body)` (messy whitespace + >160 chars ⇒ collapsed and truncated, length `SNIPPET_CHARS + 1`) |
| `test_no_hit_carries_a_title_or_any_field_beyond_the_hit_shape__S025_004_DoD3` | 3 | `dataclasses.fields(SearchHit)` == exactly D3's seven names; no hit has `title`/`name` (US-119) |
| `test_memo_hits_carry_the_stored_scope_and_scope_id__S025_004_DoD4` | 4 | a user-level and a session-level memo report `("user", USER_A)` / `("session", SESSION_A1)`; no field name contains "name" (U3 — no level name) |
| `test_session_search_is_the_vector_ranking_with_no_fts_table_present__S025_004_DoD5` | 5 | **neither FTS table created** (probed absent) and the search still succeeds: kind `"session"`, ids == the test's vector ranking, scores `1/61`, `1/62`, snippet/memo level/`session_id` all `None` |
| `test_entry_search_is_lexical_only_and_opens_no_model__S025_004_DoD6` | 6 | **no designated model at all**: `factory.call_count == 0`, `embed_calls == []`, and hits are the two record rows containing the token (BM25 definition order), each with its `session_id` and a snippet containing the token |
| `test_another_owners_memo_matching_both_arms_is_absent__S025_004_DoD7` | 7 | `USER_B`'s memo holds the token **and** stores the query vector exactly (distance 0) — absent; result still == the fused expectation |
| `test_another_owners_session_matching_the_vector_arm_is_absent__S025_004_DoD7` | 7 | `USER_B`'s session at distance 0 absent from the session variant's one arm |
| `test_another_owners_entry_matching_the_lexical_arm_is_absent__S025_004_DoD7` | 7 | `USER_B`'s record row with the token absent from the entry variant's one arm |
| `test_memo_extra_predicate_excludes_the_disabled_and_the_forced__S025_004_DoD8` | 8 | `is_enabled AND NOT is_forced`: the disabled and the forced memo both match on **both** arms (token body + query vector) and are both absent; the kept memo scores `2/(60+1)` |
| `test_session_extra_predicate_excludes_the_other_character_and_the_current__S025_004_DoD8` | 8 | `character_id = :c AND id != :current`: the other character's session and the current one are both at distance 0 and both absent |
| `test_zone_and_buried_rows_are_never_entry_hits__S025_004_DoD9` | 9 | same owner, same session, all three bodies hold the token: only the record row appears |
| `test_memo_search_without_a_model_raises_even_though_fts_matches__S025_004_DoD10` | 10 | `memo_fts` present **and holding a match** ⇒ still `NoEmbeddingModelError`, `call_count == 0` — the no-silent-degrade clause |
| `test_session_search_without_a_model_raises__S025_004_DoD10` | 10 | session scope with no designation raises, builds no client |
| `test_an_unreachable_provider_propagates_from_a_memo_search__S025_004_DoD10` | 10 | `unreachable_factory` ⇒ `LlmUnreachableError` propagates from a memo search |
| `test_early_exits_return_nothing_and_open_nothing__S025_004_DoD11` (3 variants × 4 inputs = 12) | 11 | `limit` 0, `limit` -3, `""`, whitespace-only ⇒ `[]` for memo/session/entry with `call_count == 0` and `embed_calls == []`, over a corpus that would otherwise match |
| `test_a_punctuation_only_query_returns_the_vector_arm_alone__S025_004_DoD12` | 12 | `'"""'` sanitises to none (so `MATCH ''` is never issued): ids == the vector ranking, scores `1/(60+rank)`, nothing raised, every snippet == `_leading_extract(body)`; `memo_fts` confirmed present |
| `test_memo_search_with_neither_memo_table_present_returns_nothing__S025_004_DoD13` | 13 | designation present, `memo_fts`/`memo_vec` probed absent ⇒ `[]`, no error |
| `test_memo_search_with_only_memo_fts_returns_the_lexical_matches__S025_004_DoD13` | 13 | `memo_vec` absent ⇒ lexical matches alone, order by BM25's definition (long body given the **lower** id), scores `1/61`,`1/62`, FTS snippets (short body == whole body, long body contains `…`) |
| `test_entry_search_with_message_fts_absent_returns_nothing__S025_004_DoD13` | 13 | record rows with the token exist, index does not ⇒ `[]` |
| `test_a_limit_larger_than_the_fused_set_returns_all_of_it__S025_004_DoD14` | 14 | `limit=100` (keyword form) ⇒ the whole fused set, ids and scores |
| `test_a_smaller_limit_returns_the_prefix_of_the_fused_set__S025_004_DoD14` | 14 | `limit` 2 ⇒ exactly the first two of the same fused list |
| `test_the_six_search_modules_are_all_present_to_scan__S025_004_DoD15` | 15 | the package directory's `*.py` set == the six files of `context.md` "Files this feature touches" (so the scan is not vacuous) |
| `test_no_search_module_imports_fastapi__S025_004_DoD15` | 15 | AST import walk over all six: no `fastapi` / `starlette` root |
| `test_only_the_vector_module_imports_sqlite_vec__S025_004_DoD15` | 15 | same walk: no module **other than** `vector.py` imports `sqlite_vec` |

- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓,
  DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓

## Notes & Issues

- Step 004: `ports.py`'s frozen docstring for `SearchHit.memo_scope_id` says "`None` for the
  `"user"` level", following `services/memos.py`'s `Memo.scope_id` convention, while step 004's
  DoD-4 and `004.context.md`'s hydration read say the hit carries **the stored** `scope_id` (a
  user-level row stores the owner's id). The implementation passes the stored value through, as the
  step file is the behavioural contract; the `ports.py` docstring sentence is therefore stale.
  Out of this step's scope to edit (`ports.py` is step 001's source file) — worth a one-line
  docstring correction, or a plan decision if `None` was actually meant.

## Ultra phase

- orient: done 2026-10-04
- prerequisite confirmed: 024 is delivered and committed (2f9ff35), so the names 025 binds to
  (`db/search_tables.py`'s four constants + `vector_table_dimension`, `services/embedding.py`'s
  `open_embedding_model` / `embed_texts` / `DEFAULT_EMBED_TIMEOUT_SECONDS` / `write_vector`, and
  `tests/llm_fakes.py`) all exist as **frozen** rather than planned. Where 024's `## Skeleton`
  froze an exact name, 025 binds to the frozen one, per `context.md`.
- regression surface: small by construction. 025 creates no table, writes no row, adds no
  route and touches **no existing file** — all six source files are new under
  `app/services/search/`. No existing test should change; a break in one is a `SPEC` hand-back.
- one `SPEC` check delegated to step 002's skeleton by `002.context.md`: confirm the
  `settled_entries` selectable's projection includes `user_id`; if it does not, hand back
  rather than reading raw `messages` (R11).
- harvest: done — docs/.cache/ultra/025.hybrid-search-port/harvest.md (1 report, empirically verified)
- the harvest settled the plan's premises rather than assuming them: the FTS sanitiser rule holds
  for all eleven hostile inputs; the vec0 exact-scan form works at ids above 2^60 with a
  `serialize_float32` bound blob and no `MATCH`; a width mismatch really raises
  (`OperationalError: Vector dimension mistmatch`), so step 003's pre-embed guard is necessary; and
  the delegated `SPEC` check **passes** — `settled_entries` projects `user_id`, so no step needs raw
  `messages`. Two cautions carried to every step: `MATCH ''` **raises**, so `build_fts_query`
  returning none (and the arm skipping) is load-bearing; and `rowid` is **unusable** on a vec0
  table, so the vector arm must name `memo_id` / `session_id`.
- one file is off-limits that the plan does not mention: `test_config.py:198` asserts
  `app/services/__init__.py` has no statements after its docstring, so 025 must not edit it.
  Creating `app/services/search/__init__.py` is unaffected (`app/services/llm/` is the precedent).
- skeleton: done — steps 001, 002, 003, 004
- tests: done — steps 001, 002, 003, 004 (no deviation needed: 025 touches no existing file)
- red-gate: PASS (run 1) — 104 reds, every one `NotImplementedError`; no pre-existing test failed anywhere (backend suite minus the four new files fully green, frontend 4020/4020); both high-value fixtures audited sound (003 DoD-2's ids are interleaved by a prime stride and the fixture is provably discriminating; 004 DoD-2's rank verification is present); `[manual/live]` set is empty for this feature
- code: done — steps 001, 002, 003, 004 (no re-freeze, no escape valve)
- verify: PASS (run 1) — 47/47 `[test]` DoD items met, 122 new tests, 0 failures; full suites green (backend 3916, frontend 4020) and `git diff --stat` empty, so no existing file was touched; `[manual/live]` set empty
