# Planning files — layout, lifecycle, and contracts

Every planning and coding agent reads this file first and treats it as authoritative. Two tracks live here: multi-step features and fast features. Bug fixes run against an already-completed plan in either track.

## Tracks — when to use fast vs multi-step

- **Multi-step** (`<NNN>.<feature>/`) — work spanning more than one coherent change: cross-layer coordination, dependencies between sub-parts, design ambiguity needing mid-flight decisions, or more than ~300 LoC of source change. Decomposed into ordered steps by `/planner`. Built either step by step with `/coder` (each step verified before the next) or in one phased run with `/ultra-feature` (same step files and agents; harvest, red gate, test run and verification happen once for the whole feature; per-step phases run strictly in step order).
- **Fast** (`fast/<NNN>.<name>/`) — a single coder pass: one logical change, one or two test files, roughly 50–300 LoC, no internal step boundaries. Planned by `/fast-feature`. If you catch yourself writing "Phase 1 / Phase 2" or "first the schema, then the UI", it is multi-step — promote it.
- **Bug fix** — `/bug-fixer`, run against a `done` plan in either track. Adds no new scope; repairs the existing contract.

The two counters are independent: `fast/001` and `001.<feature>/` are unrelated.

## Layout

```
docs/plans/
  roadmap.md                    # optional; stage index (/roadmap)
  <NNN>.<feature>/              # multi-step
    brief.md                    # optional; short definition (/roadmap)
    context.md                  # feature-wide context
    <SSS>.<name>.md             # one step file per step
    <SSS>.context.md            # one per step (never skipped)
    outcome.md                  # intended doc changes, applied at finalization
    status.md                   # step table + lifecycle sections
  fast/
    <NNN>.<name>/               # fast feature
      brief.md                  # optional; short definition (/roadmap)
      context.md
      plan.md                   # the single plan (the step file's equivalent)
      outcome.md
      status.md
  backlog/                      # rough idea seeds; unsequenced, no commitment
```

`NNN` / `SSS` are 3-digit zero-padded. Letter suffixes (`001b`) are for splits/rework after the fact, not initial planning.

## Roadmap and briefs — optional

A project may use `/roadmap` to sequence features before planning them. It is optional; a project that never runs it has no `roadmap.md` and no `brief.md`, and nothing below applies.

Where it is used:

- **`roadmap.md`** — the stage index: one block per stage (goal + exit criteria) and a table of its features with track, size, delivered product ids, and feature-level dependencies. **No status column** — status is derived from the folder, never duplicated.
- **`brief.md`** — a feature's short definition, written *before* planning: stage, track, size, `Delivers:` (the `docs/product/` ids it realizes, omitted when there's no product layer), `Depends on:` (feature-level), a 3–6 sentence behavioural Definition, Scope In/Out, and Open questions for the planner. It is a definition, never a plan: no steps, no Definition of done, no signatures, no file lists.
- **A folder containing only `brief.md` is roadmapped, not planned.** The absence of `status.md` is the signal. `/roadmap` never creates a planner-owned file.

Derived feature state, for any agent that needs it:

| Folder contents | State |
|---|---|
| `brief.md` only | roadmapped — `/planner` or `/fast-feature` has not run |
| `status.md` present | planned — the pipeline owns it from here |
| `status.md` rows all `done` with verifier `PASS` | delivered |

`/planner` and `/fast-feature` **read `brief.md` when present** and treat its Definition and Scope as the feature's agreed boundary rather than re-deriving it — the Out list bounds the plan, and the Open questions are what the harvest must resolve. Neither ever edits it. A brief that turns out wrong is a `/roadmap` re-shape, not a plan-time correction.

`backlog/` and the roadmap are different states, not competitors: backlog is an unsequenced idea with no commitment; a brief is a feature committed to a stage. `/roadmap` promotes a backlog item into a stage.

## Step file / plan.md structure

A multi-step `<SSS>.<name>.md` and a fast `plan.md` carry the same behavioral contract:

- **Goal** — one or two sentences.
- **Source files** — explicit source paths, one per line. This list *is* the coder's scope; the coder touches nothing else.
- **Test files** — explicit test paths, one per line. This list *is* the test-coder's scope. **Must be disjoint from Source files** — neither role crosses into the other's list.
- **Interface intent** — each function / class / type / endpoint the work adds or changes, named with its responsibility and inputs/outputs **in prose**. No exact type signatures — the skeleton agent freezes those.
- **Definition of done** — a numbered checklist (DoD-1, DoD-2, …) of verifiable criteria. Tag each item `[test]` (the test-coder must cover it with a test citing the id) or `[manual/live]` (no automated test; the verifier records it as requires-live-run). The set of `[test]` items is the coverage contract.
- **Dependencies** (multi-step) — earlier steps relied on, or "none".
- **Out of scope** (fast) — short list of deliberate exclusions to bound creep.

Multi-step size budget: 50–200 LoC of source change per step (test volume isn't counted). Fast: 50–300 LoC total.

## Pipeline and ownership — the air gap

Plans run through a chain of single-purpose agents with a strict separation between who writes tests and who writes code:

1. **planner / fast-planner** — writes the plan (sections above). Owns the plan file and the seeded `status.md`.
2. **skeleton / fast-skeleton** — reads Interface intent + code, writes compilable stubs (unimplemented bodies), and **freezes the exact signatures** into a `## Skeleton` record in `status.md`. Owns `## Skeleton`.
3. **test-coder / fast-test-coder** — writes tests from the spec ALONE, bound to the `## Skeleton` signatures, each tagged to a `[test]` DoD id. **Never reads source.** Owns `## Tests` and the Test files.
4. **verifier (red-gate run)** — runs the new tests against the stubs: confirms they compile, cover every `[test]` item, and fail for the right reason.
5. **coder / fast-coder** — fills the stub bodies, **blind to the tests**, runs build/typecheck only. Owns `## Files Changed` and the Source files. May not change a frozen signature (re-route to skeleton if it must).
6. **verifier (verify run)** — the **only** role that runs the tests as a gate. Emits PASS/FAIL plus a **Fault**: `CODE` (back to coder), `TEST` (back to test-coder, then re-red-gate), or `SPEC` (back to the user — the plan itself is wrong). Failure summaries are by-DoD-clause and never quote test internals, so the air gap holds.

The invariant: **expected values come from the spec, never from code; the interface tells you only how to call, never what to expect.** The test-coder never sees the implementation; the coder never sees the tests; the verifier is the sole bridge and relays results, never code or test source.

## status.md

Seeded by the planner. Multi-step:

```
# Feature <NNN> — <name>

| Step | File            | Status  | Verifier | Date |
|------|-----------------|---------|----------|------|
| 001  | `001.<name>.md` | pending | —        | —    |

## Files Changed

_populated by the coder as steps complete_

## Notes & Issues

_populated by the coder when worth saying_
```

Fast:

```
# Fast feature <NNN> — <name>

| Status  | Verifier | Date |
|---------|----------|------|
| pending | —        | —    |

## Files Changed

_populated by the coder when implementation lands_

## Notes & Issues

_populated by the coder when worth saying_
```

As the pipeline runs, agents append their own sections (below `## Files Changed`): `## Skeleton` (frozen signatures, skeleton), `## Tests` (test inventory, each tagged to a DoD id, test-coder), and `## Bug Fixes` (one entry per bug fix against a `done` plan, coder/fixer). A multi-step feature built by `/ultra-feature` also carries `## Ultra phase` (orchestrator-owned resume record: which phase completed for which steps).

### Status lifecycle

`pending` → `wip` (coder may set mid-step) → `done` (orchestrator, on verifier PASS) or `blocked` (skeleton/coder escape valve, or Fault: SPEC). Only these four values. A bug fix never un-completes a `done` plan — its record is the `## Bug Fixes` and `## Tests` entries.

## Ownership summary

| File / section               | Written by                    | Everyone else          |
|------------------------------|-------------------------------|------------------------|
| roadmap.md, brief.md         | roadmap (optional layer)      | read-only              |
| plan / step file             | planner / fast-planner        | read-only              |
| context.md, `<SSS>.context`  | planner / fast-planner        | read-only              |
| outcome.md (top)             | planner; applied by architect | read-only              |
| outcome.md `## Observations` | coder / fixer                 | read-only              |
| status.md row                | orchestrator                  | —                      |
| `## Ultra phase`             | ultra-feature orchestrator    | read-only              |
| `## Skeleton`                | skeleton                      | read-only ground truth |
| `## Tests`                   | test-coder                    | coder never reads      |
| `## Files Changed`           | coder / fixer                 | —                      |
| `## Bug Fixes`               | coder / fixer                 | —                      |

`docs/architecture/` is the architect's domain — plans reference it, never edit it.
