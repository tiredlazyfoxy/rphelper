# fast/004.character-page-first-reply — Character page first reply
<!-- roadmap:start -->
- **Stage:** 006.repair · **Track:** fast · **Size:** S
- **Delivers:** FEAT-008 (UC-080 step 5, US-117.AC-3)
- **Depends on:** `018.character-page`, `021.compose-loop-and-tools`, `022.discussion-ui`

## Definition
Writing the first message on a character's page gets an answer. Today that message creates the session and lands as a current-zone row, and nothing answers it — the roleplayer has to send a second time on the session screen before a candidate appears. After this the assistant answers the opening message the way it answers any other discussion message, so the page's one job, starting a roleplay by typing into it, completes in a single send.

## Scope
**In:**
- an assistant reply drawn for the message that created the session, equivalent to a normal discussion compose
- whatever the page or the session screen needs for that reply to appear without a second send

**Out:**
- what `POST /api/characters/{id}/sessions` creates — the session, the zone row and the discussion are already correct
- the compose loop itself
- the note wall, the configuration chain, and everything else on the page

## Open questions for the planner
- Two shapes were anticipated and the plan must pick one and say why. `018` D2 kept the create route JSON deliberately so its media type would not change, and `018/outcome.md:61` expected the reply to come from `021`'s `composeZone` after creation — the session screen starting a compose when it opens on a just-seeded zone. The alternative makes the create route a streaming response and breaks that contract.
- `018` D4 left the page composer's `sendBlockedReason` prop (US-107) ready but unused. Once typing there triggers a model call, decide whether the page must show the same blocked reason the session screen does.
- Decide what the roleplayer sees if they reload, or arrive at the session, while that first compose is still running.
<!-- roadmap:end -->
