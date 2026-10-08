# Defects — delivered behaviour that does not satisfy its criterion

Raised by `/product-spec`'s finalization of features 008..032 (2026-10-06) and
recorded here because each one is work for `docs/plans/`, not a change to
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

- `docs/plans/018.character-page/context.md:45` — "**US-117.AC-3 / UC-080 step 5**
  (the assistant answers the opening message) — `021`, …"
- `docs/plans/018.character-page/context.md:298` — "US-117.AC-3 is deferred to
  `021`, which composes on the session once it exists."
- `docs/plans/018.character-page/outcome.md:61` — "**`021`** owes
  **US-117.AC-3** (UC-080 step 5)".

**`021` never took it.** Its `## Product ids` section
(`docs/plans/021.compose-loop-and-tools/context.md`) delivers FEAT-010 via UC-034,
US-037 and US-044 only. Neither `021` nor any later plan cites US-117 or UC-080.
The criterion fell through the handoff.

**Why `/fast-feature` and not `/bug-fixer`.** There is no existing implementation
to repair — the behaviour was never built. `/bug-fixer` adds no new scope by
contract. This needs a small plan of its own.

**What the fix must settle.** `018` D2 kept the create route JSON precisely so its
media type would not change. Either the reply is triggered after creation (the
session screen starts a compose when it opens on a just-seeded zone), or the create
route becomes a streaming response — the first keeps `018`'s contract intact and is
what `018/outcome.md:61` anticipated. `021`'s `composeZone` already exists to call.
Also decide whether the page composer takes `sendBlockedReason` (US-107) once
sending there triggers a model call; `018` D4 left the prop ready.

---

## D-02 — A reply still streaming is not editable

**Criterion.** US-115.AC-1 — *Given a message sits in the current zone, whoever
wrote it, when the roleplayer edits its text, then the instance saves the edit in
place.* Confirmed at finalization as standing unamended for this half.

**What the build does.** While streaming, `022` renders a **live reply** beneath
the zone rows with **no edit control**
(`docs/plans/022.discussion-ui/context.md:327`, D6, from user decision U4). Once
the stream ends, `019` D14's zone re-read replaces it with the persisted row, and
**that row is editable like any other zone message**.

**The hazard the fix must solve.** D6 gives a real reason, not an oversight: an
edit racing the server's own write of that row would either be lost or clobber it
(`019` D11). A fix that simply exposes the editor re-introduces that race. Any
repair has to decide what happens to an in-flight edit when the persisted row
arrives.

**A reading that would close this without code.** US-115.AC-1 is conditioned on a
message *sitting in* the current zone. An in-flight reply has no persisted row yet,
which is exactly the argument `022/outcome.md` made. If that reading is accepted,
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
(`docs/plans/024.embedding-lifecycle/context.md:295`, D8, user decision U3).
"Any other exception propagates as before." So if the designated server's
`$ENV_VAR` API key is unset, `secret_ref_missing` escapes: a settle or a settled
edit fails with a 500 and the roleplayer's own text is refused — the one thing
US-112 exists to prevent.

**Flagged by the plan itself.** `docs/plans/024.embedding-lifecycle/outcome.md`,
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

> `docs/plans/024.embedding-lifecycle/context.md:49-52` — "How a failed degraded
> embed is recorded so the rebuild can find it. It is **not recorded** (user
> decision U5). A degraded write leaves any existing `session_vec` row **as it is,
> which makes it stale**, and writes nothing else. There is no staleness column."

So after a degraded edit, semantic search can still return that session on the
strength of text it no longer contains.

**This reverses decision U5.** The finalization decision was *"save and clear the
vectors in this case"* — absent from search is preferred to present under
superseded text. `024`'s U5 is superseded, not misapplied; the plan did what it was
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

> `docs/plans/029.my-search/context.md:184-191` (D3) — "Case-insensitivity is
> SQLite `LIKE`'s: **ASCII letters only**. A non-ASCII name matches only in the
> case typed. Recorded as a known limitation in `outcome.md`, not fixed here."

**Why it matters more here than it looks.** `docs/product/vision.md`'s premise is
a roleplayer composing in a language they are **not** a confident writer in. A
non-Latin RP language is the expected case, not an edge one, so "matches only in
the case typed" is a real failure of UC-058 for the product's own core user.

**What the fix must settle.** The two hit kinds affected are `character`
(`characters.name`, `characters.sheet`) and `setup` (`setups.name`,
`setups.description`) — `029/context.md:135-136`. Entries and memos go through the
FTS/vector arms and are not affected. The escape-character handling in D3 must
survive the fix: user input can never be allowed to act as a wildcard.
