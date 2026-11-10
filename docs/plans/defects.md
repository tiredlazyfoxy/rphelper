# Defects — delivered behaviour that does not satisfy its criterion

Raised by `/product-spec`'s finalization of features 008..032 (2026-10-06) — D-06
and D-07 by the finalization of 2026-11-09 — and recorded here because each one is work for `docs/plans/`, not a change to
`docs/product/`. Every entry names the criterion it violates, what the build
does instead, where the decision was taken, and the vehicle that should repair
it.

Status is not tracked here. A defect is closed by the plan that fixes it; the
owning `status.md` records the repair, and the `**Remaining:**` line in
`docs/product/features.md` is what says a criterion is still unsatisfied.

| # | Criterion | FEAT | Owning plan | Vehicle |
|---|---|---|---|---|
| D-01 | US-117.AC-3 / UC-080 step 5 | FEAT-008 | `018.character-page` | `/fast-feature` |
| D-02 | US-115.AC-1 (streaming half) | FEAT-010 | `022.discussion-ui` | `/bug-fixer` |
| D-03 | US-112.AC-1 (widened) | FEAT-009 | `024.embedding-lifecycle` | `/bug-fixer` |
| D-04 | US-112.AC-3 | FEAT-009 | `024.embedding-lifecycle` | `/bug-fixer` |
| D-05 | US-147 | FEAT-017 | `029.my-search` | `/bug-fixer` |
| D-06 | timestamp form (`data-model.md`) | FEAT-003 | `003.first-run-bootstrap` | `/bug-fixer` |
| D-07 | DEC-027-5 (excerpt body) | FEAT-015 | `027.session-search-tool` | `/bug-fixer` |

---

## D-01 — The character page's opening message draws no assistant reply

**Criterion.** US-117.AC-3 — *Given the roleplayer writes the first message on a
character's page, when the session is created, then the assistant answers that
message as it would any other discussion message.* UC-080 step 5 states the same.

**What the build does.** `018` ships `POST /api/characters/{id}/sessions` as a
JSON create-and-seed route that makes no model call: the session is created, the
message is written as a current-zone row, and nothing answers it. The roleplayer
must send again on the session screen to get a candidate.

**Where it was decided, and how it was lost.** `018` deliberately deferred the
reply rather than dropping it:

- 018.character-page (docs/decisions/018.character-page.md), DEC-018-2 — "**US-117.AC-3 / UC-080 step 5**
  (the assistant answers the opening message) — `021`, …"
- 018.character-page (docs/decisions/018.character-page.md), DEC-018-2 — "US-117.AC-3 is deferred to
  `021`, which composes on the session once it exists."
- 018.character-page (docs/decisions/018.character-page.md) — "**`021`** owes
  **US-117.AC-3** (UC-080 step 5)".

**`021` never took it.** Its `## Product ids` section
(021.compose-loop-and-tools (docs/decisions/021.compose-loop-and-tools.md)) delivers FEAT-010 via UC-034,
US-037 and US-044 only. Neither `021` nor any later plan cites US-117 or UC-080.
The criterion fell through the handoff.

**Why `/fast-feature` and not `/bug-fixer`.** There is no existing implementation
to repair — the behaviour was never built. `/bug-fixer` adds no new scope by
contract. This needs a small plan of its own.

**What the fix must settle.** DEC-018-2 kept the create route JSON precisely so its
media type would not change. Either the reply is triggered after creation (the
session screen starts a compose when it opens on a just-seeded zone), or the create
route becomes a streaming response — the first keeps `018`'s contract intact and is
what 018.character-page (docs/decisions/018.character-page.md) anticipated. `021`'s `composeZone` already exists to call.
Also decide whether the page composer takes `sendBlockedReason` (US-107) once
sending there triggers a model call; DEC-018-4 left the prop ready.

---

## D-02 — A reply still streaming is not editable

**Criterion.** US-115.AC-1 — *Given a message sits in the current zone, whoever
wrote it, when the roleplayer edits its text, then the instance saves the edit in
place.* Confirmed at finalization as standing unamended for this half.

**What the build does.** While streaming, `022` renders a **live reply** beneath
the zone rows with **no edit control**
(022.discussion-ui (docs/decisions/022.discussion-ui.md), DEC-022-6, from user decision U4). Once
the stream ends, DEC-019-14's zone re-read replaces it with the persisted row, and
**that row is editable like any other zone message**.

**The hazard the fix must solve.** DEC-022-6 gives a real reason, not an oversight: an
edit racing the server's own write of that row would either be lost or clobber it
(DEC-019-11). A fix that simply exposes the editor re-introduces that race. Any
repair has to decide what happens to an in-flight edit when the persisted row
arrives.

**A reading that would close this without code.** US-115.AC-1 is conditioned on a
message *sitting in* the current zone. An in-flight reply has no persisted row yet,
which is exactly the argument 022.discussion-ui (docs/decisions/022.discussion-ui.md) made. If that reading is accepted,
D-02 is not a defect but an amendment — and the criterion needs one clarifying
clause rather than a fix. Recorded so the choice is deliberate.

---

## D-03 — An unusable embedding credential blocks record-keeping

**Criterion.** US-112.AC-1, as widened at finalization (2026-10-06) from "no
embedding model configured" to **any** embedding-side failure — a missing model, an
unreachable server, or credentials the instance cannot use. The edit or settle must
still save, and the roleplayer is told search coverage is incomplete, never refused.

**What the build does.** The degraded path catches exactly two errors —
`NoEmbeddingModelError` (409) and `LlmUnreachableError` (502)
(024.embedding-lifecycle (docs/decisions/024.embedding-lifecycle.md), DEC-024-8, user decision U3).
"Any other exception propagates as before." So if the designated server's
`$ENV_VAR` API key is unset, `secret_ref_missing` escapes: a settle or a settled
edit fails with a 500 and the roleplayer's own text is refused — the one thing
US-112 exists to prevent.

**Flagged by the plan itself.** 024.embedding-lifecycle (docs/decisions/024.embedding-lifecycle.md),
"Flags for other owners": "If the designated server's `$ENV_VAR` key is unset, a
settle or settled edit therefore fails with 500 instead of saving degraded.
US-112's spirit ('a platform gap never blocks my own record-keeping') arguably
covers it. Decide whether the degraded path should also catch it." It does.

**What the fix must do.** Widen the degraded path's catch so no embedding-side
failure reaches the caller as a refusal. The strict path is unaffected — it is
allowed to fail loudly.

---

## D-04 — A degraded write leaves a stale vector instead of clearing it

**Criterion.** US-112.AC-3, new at finalization (2026-10-06) — *Given material
cannot be embedded, when the write commits, then the material's existing vectors
are cleared rather than left in place.*

**What the build does.** The opposite, by an explicit earlier decision:

> 024.embedding-lifecycle (docs/decisions/024.embedding-lifecycle.md), DEC-024-13 — "How a failed degraded
> embed is recorded so the rebuild can find it. It is **not recorded** (user
> decision U5). A degraded write leaves any existing `session_vec` row **as it is,
> which makes it stale**, and writes nothing else. There is no staleness column."

So after a degraded edit, semantic search can still return that session on the
strength of text it no longer contains.

**This reverses decision DEC-024-13 (024 U5).** The finalization decision was *"save and clear the
vectors in this case"* — absent from search is preferred to present under
superseded text. DEC-024-13 is superseded, not misapplied; the plan did what it was
told at the time.

**Accepted consequence of the fix.** Material that could not be embedded drops out
of semantic search entirely until the whole-index rebuild
(`fast/002.vector-index-rebuild`, UC-016) runs. This is recorded in
`docs/product/features.md`'s Relationships section as an accepted consequence, not
a defect in its own right.

**What the fix must do.** On the degraded path, delete the affected rows from the
derived stores instead of leaving them. Note `032`'s finding: every write to the
`vec0` / FTS tables must resolve its row ids through an owner-scoped query first,
because those tables carry no user column — the one leak `032` found was exactly
that predicate missing on a delete.

---

## D-05 — My-search matches names case-insensitively in ASCII only

**Criterion.** US-147, new at finalization (2026-10-06) — *Given a character or
setup whose name is written in any script, when the roleplayer searches for it in
a different case, then it is matched.*

**What the build does.** Character and setup matching is a SQLite `LIKE`
substring, and SQLite's `LIKE` folds case for **ASCII letters only**:

> 029.my-search (docs/decisions/029.my-search.md), DEC-029-7 — "Case-insensitivity is
> SQLite `LIKE`'s: **ASCII letters only**. A non-ASCII name matches only in the
> case typed. Recorded as a known limitation in `outcome.md`, not fixed here."

**Why it matters more here than it looks.** `docs/product/vision.md`'s premise is
a roleplayer composing in a language they are **not** a confident writer in. A
non-Latin RP language is the expected case, not an edge one, so "matches only in
the case typed" is a real failure of UC-058 for the product's own core user.

**What the fix must settle.** The two hit kinds affected are `character`
(`characters.name`, `characters.sheet`) and `setup` (`setups.name`,
`setups.description`) — 029.my-search (docs/decisions/029.my-search.md). Entries and memos go through the
FTS/vector arms and are not affected. The escape-character handling in DEC-029-7 must
survive the fix: user input can never be allowed to act as a wildcard.

---

## D-06 — `users` timestamps drop zero microseconds

**Criterion.** The stored-timestamp form in `docs/architecture/data-model.md` —
UTC ISO-8601 text at microsecond precision with an explicit `+00:00`, fixed width,
because these columns are compared as text. `quick-reference.md` states the same.

**What the build does.** `users.created_at` and `users.updated_at`, as written by
`003`'s first-administrator insert, use plain `isoformat()`, which drops the
microseconds when they are zero — so those values do not share the fixed width.
Both architecture docs name it as a known deviation, not yet fixed.

**Status.** Open; no plan has taken it. Until it is fixed, nothing may compare
those two columns as text against a fixed-width value.

**What the fix must do.** Write both columns in the fixed-width form every other
timestamp uses.

---

## D-07 — A whitespace-only settled row renders a whitespace excerpt body

**Criterion.** DEC-027-5 — 027.session-search-tool
(docs/decisions/027.session-search-tool.md). The session-search excerpt is meant
to follow the joining 024 uses (DEC-027-3), and 024 drops whitespace-only parts
with `strip()`.

**What the build does.** `027` skips only `""`. A whitespace-only settled row is
joined as stored, so a session whose only settled rows are whitespace renders a
whitespace body instead of `(no settled entries)`.

**Status.** Open — accepted at the time as a divergence, not a re-code; a
strip-based rule is the better reading.

**What the fix must do.** Skip parts that are empty after `strip()`, matching 024.
