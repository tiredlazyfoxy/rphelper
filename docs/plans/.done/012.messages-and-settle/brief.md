# 012.messages-and-settle — Messages and settle
<!-- roadmap:start -->
- **Stage:** 002.record · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-009 (UC-028, UC-031, UC-081, US-031, US-034, US-122), FEAT-010 (UC-037, UC-083, UC-084, US-041, US-042, US-126, US-127, US-128, US-129, US-130)
- **Depends on:** `011.rp-sessions`

## Definition
Builds the one door into a session's record and the rules that guard it. A session's rows live in one table read through two views — the settled record and the single current zone — and settle is the only operation that moves anything from the second into the first, stamping every row it buries in one transaction. Settling takes the last message in the zone whoever wrote it, classifies a wholly-parenthesised message as a decision rather than a turn, and strips a doubly-parenthesised fragment so it never appears in the settled text. Re-open is the mirror, permitted only while the zone below is still empty. Entries are independent, so the roleplayer can open a roleplay themselves or answer twice running.

## Scope
**In:**
- the `messages` table with its self-referencing burial column and settle timestamp, plus the settled-record and current-zone views
- appending to the zone
- settle and re-open as one transaction each, the only writers of raw rows
- the parenthesis parser as a pure classify-and-strip function applied once at settle
- the three entry kinds including decisions
- the refusal to re-open once the zone below is non-empty

**Out:**
- every user-visible surface — the stream, the ruler, the kind switch and the composer are `013`
- editing a settled entry (`014`)
- anything the assistant writes (`020`, `021`, `022`)
- what reaches the model (`020`)

## Open questions for the planner
- What `US-120`'s carried-forward question resolves to — what a settled decision does to the kind switch's alternating default. This is carried forward unresolved from `docs/product/` (US-120) and `docs/architecture/workspace-shell.md`; the planner must resolve it, it is not answered by either doc.
- Whether the two views are SQL views or query builders, given `007`'s registry must describe whatever they are.
<!-- roadmap:end -->
