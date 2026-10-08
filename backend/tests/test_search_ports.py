"""Tests for ``app.services.search.ports`` — the hybrid-search port's types and pure helpers.

Every expected value comes from the spec, never from calling the code under test:
``docs/plans/025.hybrid-search-port/001.port-contract.md`` (Interface intent + Definition
of done), ``001.context.md`` (the six numbered FTS sanitising rules) and the feature
``context.md`` (U1 the variants and the owner/extra-predicate rule, U3 + D3 the hit shape,
D1 the fusion formula with ``k = 60`` and ties by ascending id, D4 the leading extract).
Bindings come from ``## Skeleton`` → "Step 001 — frozen interface" in ``status.md``:
``rrf_fuse(rankings, *, k=RRF_K)`` (``k`` is **keyword-only**), ``build_fts_query(query)``,
``leading_extract(body)``, and the three frozen scope variants with fields
``user_id`` (no default) and ``extra_predicate`` (default ``None``).

Covers step 001 DoD-1 … DoD-10. There is no ``[manual/live]`` item in this step.

DoD-7 runs the sanitiser's output as a real FTS5 ``MATCH``. The port creates no table, so
each such test builds its own throwaway ``fts5`` table on a private in-memory SQLite
connection (nothing under ``backend/data/`` is touched). ``conftest.py`` is untouched: this
module needs no database fixture.
"""

import ast
import inspect
import sqlite3
from collections.abc import Iterator

import pytest

from app.services.search import ports as ports_module
from app.services.search.ports import (
    ARM_DEPTH,
    RRF_K,
    SNIPPET_CHARS,
    EntrySearchScope,
    MemoSearchScope,
    SessionSearchScope,
    build_fts_query,
    leading_extract,
    rrf_fuse,
)

# The three frozen scope variants, exercised identically by DoD-1 (U1).
SCOPE_VARIANTS = [MemoSearchScope, SessionSearchScope, EntrySearchScope]

# DoD-7's eleven hostile inputs, verbatim from the step file.
HOSTILE_INPUTS = [
    "AND",
    "OR (",
    "NEAR(a b)",
    "col:term",
    "a*",
    "-x",
    "^start",
    '"unbalanced',
    ")(",
    "*",
    "---",
]


@pytest.fixture
def fts_connection() -> Iterator[sqlite3.Connection]:
    """A throwaway in-memory SQLite connection holding one real ``fts5`` table.

    DoD-7: the *test* creates the FTS5 table; the port never does.
    """
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE hostile_fts USING fts5(body)")
        connection.execute("INSERT INTO hostile_fts(body) VALUES ('a quick amber fox at the inn')")
        connection.commit()
        yield connection
    finally:
        connection.close()


# --- DoD-1: the scope variants require user_id, default no extra predicate, are frozen ---


@pytest.mark.parametrize("variant", SCOPE_VARIANTS)
def test_scope_variant_without_user_id_raises__S025_001_DoD1(variant: type) -> None:
    """U1 — every variant requires ``user_id``; it cannot be constructed without one."""
    with pytest.raises(TypeError):
        variant()


@pytest.mark.parametrize("variant", SCOPE_VARIANTS)
def test_scope_variant_with_only_user_id_has_no_extra_predicate__S025_001_DoD1(variant: type) -> None:
    """U1 — the extra predicate is optional and defaults to none."""
    scope = variant(user_id=4611686018427387905)

    assert scope.user_id == 4611686018427387905
    assert scope.extra_predicate is None


@pytest.mark.parametrize("variant", SCOPE_VARIANTS)
def test_scope_variant_is_immutable__S025_001_DoD1(variant: type) -> None:
    """U1 — each variant is a frozen value: assigning a field raises."""
    scope = variant(user_id=4611686018427387905)

    with pytest.raises(AttributeError):
        scope.user_id = 4611686018427387906
    with pytest.raises(AttributeError):
        scope.extra_predicate = None


# --- DoD-2: the fusion contract over two rankings (D1) --------------------------------

# Ids chosen so the b/d tie is observable and ascending-id order differs from input order:
# b (999) is seen first, d (303) is seen second, yet d must come out first.
_A = 101
_B = 999
_C = 202
_D = 303


def test_rrf_fuse_over_two_rankings_scores_and_order__S025_001_DoD2() -> None:
    """D1 — ``Σ 1/(k + rank)`` with ``k = 60``, rank 1-based; ties by ascending id."""
    fused = rrf_fuse([[_A, _B, _C], [_C, _D]])

    # Order: c (two arms) first, then a, then the tied pair by ascending id (d before b).
    assert [identifier for identifier, _ in fused] == [_C, _A, _D, _B]

    scores = dict(fused)
    assert scores[_A] == pytest.approx(1 / 61)
    assert scores[_B] == pytest.approx(1 / 62)
    assert scores[_C] == pytest.approx(1 / 63 + 1 / 61)
    assert scores[_D] == pytest.approx(1 / 62)


def test_rrf_fuse_covers_every_id_exactly_once__S025_001_DoD2() -> None:
    """D1 — the result covers every id appearing in any ranking, with no duplicate."""
    fused = rrf_fuse([[_A, _B, _C], [_C, _D]])

    identifiers = [identifier for identifier, _ in fused]
    assert sorted(identifiers) == sorted([_A, _B, _C, _D])
    assert len(identifiers) == len(set(identifiers))


# --- DoD-3: a single ranking, an explicit k, and the two empty cases (D1) --------------


def test_rrf_fuse_single_ranking_keeps_order_and_scores__S025_001_DoD3() -> None:
    """D1 — a single-arm ranking still fuses: order preserved, score ``1/(60 + rank)``."""
    fused = rrf_fuse([[_A, _B, _C]])

    assert [identifier for identifier, _ in fused] == [_A, _B, _C]
    assert [score for _, score in fused] == pytest.approx([1 / 61, 1 / 62, 1 / 63])


def test_rrf_fuse_uses_explicit_k__S025_001_DoD3() -> None:
    """D1 — ``k`` is keyword-only; when given, the formula uses that ``k``."""
    fused = rrf_fuse([[_A, _B]], k=1)

    assert [identifier for identifier, _ in fused] == [_A, _B]
    assert [score for _, score in fused] == pytest.approx([1 / 2, 1 / 3])


def test_rrf_fuse_with_no_rankings_returns_empty__S025_001_DoD3() -> None:
    """D1 — an empty input returns an empty list."""
    assert rrf_fuse([]) == []


def test_rrf_fuse_with_only_empty_rankings_returns_empty__S025_001_DoD3() -> None:
    """D1 — only empty rankings return an empty list."""
    assert rrf_fuse([[], []]) == []


# --- DoD-4: ties break by ascending id regardless of input order (D1) -----------------


def test_rrf_fuse_tie_break_is_independent_of_input_order__S025_001_DoD4() -> None:
    """D1 — equal scores are broken by ascending id, whatever order the arms arrive in."""
    expected_ids = [303, 707, 999]

    one_way = rrf_fuse([[999], [303], [707]])
    other_way = rrf_fuse([[707], [999], [303]])

    assert [identifier for identifier, _ in one_way] == expected_ids
    assert [identifier for identifier, _ in other_way] == expected_ids
    assert [score for _, score in one_way] == pytest.approx([1 / 61, 1 / 61, 1 / 61])
    assert [score for _, score in other_way] == pytest.approx([1 / 61, 1 / 61, 1 / 61])


def test_rrf_fuse_tie_within_mixed_rankings_is_order_independent__S025_001_DoD4() -> None:
    """D1 — swapping the two rankings of DoD-2 changes nothing about the output."""
    swapped = rrf_fuse([[_C, _D], [_A, _B, _C]])

    assert [identifier for identifier, _ in swapped] == [_C, _A, _D, _B]


# --- DoD-5: no usable token → none (001.context.md rules 1-3, 6) ----------------------


def test_build_fts_query_returns_none_for_empty_text__S025_001_DoD5() -> None:
    """Rule 6 — no token remains, so there is no expression (``MATCH ''`` must never happen)."""
    assert build_fts_query("") is None


def test_build_fts_query_returns_none_for_whitespace_only_text__S025_001_DoD5() -> None:
    """Rules 1 + 6 — whitespace-only text splits into no token at all."""
    assert build_fts_query("   \t \n  ") is None


def test_build_fts_query_returns_none_for_quotes_and_whitespace_only__S025_001_DoD5() -> None:
    """Rules 2 + 3 + 6 — every token is empty once ``\"`` is stripped, so none remains."""
    assert build_fts_query('  ""  " \t """ \n ') is None


# --- DoD-6: the happy path (001.context.md rules 1-5) --------------------------------


def test_build_fts_query_quotes_and_or_joins_tokens__S025_001_DoD6() -> None:
    """Rules 4 + 5 — each token becomes a phrase; phrases join with ``" OR "``."""
    assert build_fts_query("Kaelith inn") == '"Kaelith" OR "inn"'


def test_build_fts_query_removes_every_quote_from_a_token__S025_001_DoD6() -> None:
    """Rule 2 — every ``\"`` inside a token is removed before the token is quoted."""
    assert build_fts_query('ka"el"i"th') == '"kaelith"'
    assert build_fts_query('"unbalanced') == '"unbalanced"'


def test_build_fts_query_splits_on_whitespace_runs_without_empty_phrase__S025_001_DoD6() -> None:
    """Rules 1 + 3 — newlines, tabs and runs of spaces all separate tokens; no empty phrase."""
    expression = build_fts_query("  Kaelith\n\n\tthe   old   inn \t")

    assert expression == '"Kaelith" OR "the" OR "old" OR "inn"'
    assert '""' not in expression


def test_build_fts_query_keeps_a_token_that_tokenises_to_nothing__S025_001_DoD6() -> None:
    """``001.context.md`` — a phrase like ``"---"`` is legal FTS5 and is kept, not filtered."""
    assert build_fts_query("--- inn") == '"---" OR "inn"'


# --- DoD-7: no hostile input can produce an FTS5 syntax error ------------------------


@pytest.mark.parametrize("hostile", HOSTILE_INPUTS)
def test_hostile_input_never_raises_as_fts_match__S025_001_DoD7(
    fts_connection: sqlite3.Connection, hostile: str
) -> None:
    """The sanitiser's output, when not none, is always a safe ``MATCH`` expression."""
    expression = build_fts_query(hostile)

    if expression is None:
        return
    rows = fts_connection.execute(
        "SELECT rowid FROM hostile_fts WHERE hostile_fts MATCH ?", (expression,)
    ).fetchall()

    assert isinstance(rows, list)


def test_every_hostile_input_survives_a_single_match_sweep__S025_001_DoD7(
    fts_connection: sqlite3.Connection,
) -> None:
    """All eleven inputs in one pass — no error is raised for any of them."""
    for hostile in HOSTILE_INPUTS:
        expression = build_fts_query(hostile)
        if expression is None:
            continue
        fts_connection.execute(
            "SELECT rowid FROM hostile_fts WHERE hostile_fts MATCH ?", (expression,)
        ).fetchall()


# --- DoD-8: the leading extract (D4) -------------------------------------------------


def test_leading_extract_collapses_whitespace_and_strips_short_body__S025_001_DoD8() -> None:
    """D4 — a short body: every whitespace run becomes one space, both ends stripped."""
    assert leading_extract("  Kaelith\n\twaits   at\n\n the  inn.  ") == "Kaelith waits at the inn."


def test_leading_extract_returns_a_body_of_exactly_snippet_chars_unchanged__S025_001_DoD8() -> None:
    """D4 — "longer than ``SNIPPET_CHARS``" is strict: a body of exactly that length is kept."""
    body = "x" * SNIPPET_CHARS

    result = leading_extract(body)

    assert result == body
    assert len(result) == SNIPPET_CHARS


def test_leading_extract_truncates_a_longer_body_with_an_ellipsis__S025_001_DoD8() -> None:
    """D4 — longer: first ``SNIPPET_CHARS`` collapsed characters plus ``…`` (one character)."""
    body = "y" * (SNIPPET_CHARS + 40)

    result = leading_extract(body)

    assert result == "y" * SNIPPET_CHARS + "…"
    assert len(result) == SNIPPET_CHARS + 1


def test_leading_extract_collapses_before_truncating__S025_001_DoD8() -> None:
    """D4 — the collapse happens first, so the cut counts *collapsed* characters."""
    collapsed = " ".join(["ab"] * 70)  # 209 characters, longer than SNIPPET_CHARS
    assert len(collapsed) > SNIPPET_CHARS
    body = "   " + "ab   " * 70

    result = leading_extract(body)

    assert result == collapsed[:SNIPPET_CHARS] + "…"
    assert len(result) == SNIPPET_CHARS + 1


# --- DoD-9: the three module constants (D1) ------------------------------------------


def test_module_constants_have_their_specified_values__S025_001_DoD9() -> None:
    """D1 — ``RRF_K = 60``, ``ARM_DEPTH = 50``, ``SNIPPET_CHARS = 160``."""
    assert RRF_K == 60
    assert ARM_DEPTH == 50
    assert SNIPPET_CHARS == 160


# --- DoD-10: ports.py is a pure module ----------------------------------------------


def _imported_module_names() -> list[str]:
    """Every module name ``ports.py`` imports, via an AST walk of its source."""
    tree = ast.parse(inspect.getsource(ports_module))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    return imported


def test_ports_imports_no_fastapi_and_no_sqlite_vec__S025_001_DoD10() -> None:
    """Pure module — neither the web framework nor the vector extension is imported."""
    forbidden_roots = {"fastapi", "starlette", "sqlite_vec"}
    offenders = [name for name in _imported_module_names() if name.split(".")[0] in forbidden_roots]

    assert offenders == []


def test_ports_imports_nothing_from_app_db_engine__S025_001_DoD10() -> None:
    """Pure module — no connection source: nothing from ``app.db.engine``."""
    offenders = [
        name
        for name in _imported_module_names()
        if name == "app.db.engine" or name.startswith("app.db.engine.")
    ]

    assert offenders == []
