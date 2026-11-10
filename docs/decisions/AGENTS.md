# Decisions Folder

The decision log for RPHelper: every technical decision **below architecture and
above code**. Read by `/planner`, `/fast-feature`, skeleton, coder, verifier and
`/architect` agents. Plans cite entries here by id and never restate them.

## The layer — what belongs here

| Layer | Folder | Holds |
|---|---|---|
| Product | `docs/product/` | what the product does, for whom, why; observable behaviour |
| Architecture | `docs/architecture/` | services, components, contracts between parts, cross-cutting rules, each with its reasoning |
| **Decisions** | **`docs/decisions/`** (this folder) | how a contract is realized inside one component; numeric defaults, bounds, timeouts, retry formulas; field shapes ("flag or nullable field"); library-specific mechanisms; orderings inside a transaction; test tolerances; rejected alternatives; the user's mid-flight calls; open questions at this altitude |

**The classification test**, in order:

1. Would an actor or the business notice if it changed? → product, not here.
2. Does it add, remove or change a service, a component, a contract between
   components, or a rule spanning components? → architecture, not here.
3. Would it still be true if the component were re-implemented with a different
   library or framework? Yes → architecture. No → **here**.
4. Does it name a type, method, field, default, timeout, event id, test id, step
   or DoD id? → **here**, unless the name *is* a public contract — then
   architecture names the contract and an entry here names the mechanism.
5. Otherwise it is a code comment or a plan note, not a record.

**A decision never introduces a contract, service, DTO or call structure.** An
entry that would is an architecture gap: it goes back to `/architect`, and
planning stops until the architecture holds it. A decision never fills a product
gap either.

**Below this layer** — a choice whose only reader is one block or one file is a
**code comment** citing the step, `DEC` id or architecture section it serves; a
choice every file in one code folder follows is a line in that folder's
`AGENTS.md` `## Conventions`. Nothing is recorded twice: a comment cites a `DEC`
id, never restates it.

## File layout

```
docs/decisions/
  AGENTS.md                 # this contract
  index.md                  # registry: one line per DEC id
  <NNN>.<feature>.md        # a multi-step feature's decisions
  fast-<NNN>.<name>.md      # a fast feature's decisions
  arch-<slug>.md            # decisions from an /architect session that sit below architecture
```

Each file opens with:

```
# Decisions — <NNN>.<feature>
**Stage:** <stage id from roadmap.md or brief.md, or —> · **Feature:** <feature id>
```

A feature is cited by its id (`003.checkout`, `fast/014.message-delete`), never
by a path inside `docs/plans/`. A finalized plan folder is archived to
`docs/plans/.done/`, which agents ignore, so such a link would dangle.

## Entry format

```
### DEC-<id> — <title>
- **Status:** open | accepted | superseded by DEC-… | rejected
- **Stage:** <id> · **Feature:** <feature id> · **Step:** <SSS> | —
- **Date:** YYYY-MM-DD · **Decided by:** user | planner | coder (confirmed: user)
- **Question:** what had to be settled
- **Decision:** the choice
- **Reason:** one or two sentences
- **Rejected:** alternatives and why not (omit if none weighed)
- **Supersedes:** an earlier entry, or a plan-local decision with no DEC id, named in text (omit if none)
- **Lands in:** code path(s) / config key(s)
- **Cites:** the architecture doc § realized inside the component; the `US-###.AC-#` or catalog test id a tolerance serves (optional; cite, never restate)
```

Status, Stage, Feature, Question, Decision, Reason and Lands in are required.

## Ids — permanent

| File | Id shape |
|---|---|
| `<NNN>.<feature>.md` | `DEC-<NNN>-<n>` |
| `fast-<NNN>.<name>.md` | `DEC-F<NNN>-<n>` — the `F` keeps the fast counter, which is independent of the multi-step one, from colliding with it |
| `arch-<slug>.md` | `DEC-arch-<slug>-<n>` |

`<n>` counts from 1 within its file and continues across later writes to that
file. **An id is never reused, renumbered or deleted.** To replace a decision:
write a new entry in the superseding feature's file, then flip the old entry's
Status to `superseded by DEC-…`. A rejected decision stays, with Status
`rejected`.

## Who writes, and when

- **Planner / fast-planner — at planning time.** Writes the feature's file with
  the decisions the plan rests on and lists their ids under `outcome.md`
  `## Decisions`.
- **Orchestrators — mid-flight, never here.** A decision taken during a build
  (escape valve, Fault SPEC, an ambiguity settled with the user) is appended to
  the feature's `outcome.md` `## Decisions` in this entry format. It reaches this
  folder at finalization.
- **The `architect` agent — at finalization and revision.** Applies the accepted
  `## Decisions` items and `[decision]` observations from `outcome.md` into the
  feature's file (creating it with its header if missing), flips superseded
  entries elsewhere, and writes `arch-<slug>.md` entries when a decision revision
  falls below architecture altitude.
- Everyone else reads. Coders, test-coders and verifiers never write here.

**`index.md` is regenerated from the entries on every write** — one row per id:
id · title · status · feature · stage. It is never hand-edited independently of
the files.
