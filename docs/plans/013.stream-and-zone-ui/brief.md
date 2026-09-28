# 013.stream-and-zone-ui — Stream and zone UI
<!-- roadmap:start -->
- **Stage:** 002.record · **Track:** multi-step · **Size:** M
- **Delivers:** FEAT-009 (UC-027, US-030, US-120, US-121, US-123), FEAT-010 (UC-086, US-115, US-125, US-134, US-135)
- **Depends on:** `012.messages-and-settle`, `008.app-shell-frame`

## Definition
Makes the session visible and writable. The centre column shows the settled record above a single labelled ruler and the current zone below it, with a composer that grows with its content and never scrolls internally. A two-position switch above the zone declares whether what is written will file as a partner block or as the roleplayer's own turn, defaulting to the alternate of the last one; on the partner position a paste files itself immediately with no settle press. Every message in the zone is editable in place. An empty zone can be discarded and a zone holding text can always be settled, so the roleplayer is never trapped.

## Scope
**In:**
- the stream reading the settled-record view ordered by id
- the ruler
- the zone reading the current-zone view
- the composer with its minimum height, no maximum and no handle
- the kind switch with its alternating default and the disabled settle on the partner position
- immediate filing of a pasted partner block
- labelled settle and send buttons
- the client-side preview of what settling will do
- parenthesis painting as display over stored text
- the discard affordance, visible only while the zone is empty and absent otherwise
- in-place editing of zone messages
- the re-open affordance, absent once the zone is non-empty

**Out:**
- editing and copying settled entries (`014`)
- the enormous-paste warning (`014`)
- anything streamed (`019`, `022`)
- the stop control (`019`)
- the note wall (`016`)

## Open questions for the planner
- Whether the settle preview is computed client-side from the same rules as the server parser or fetched, given the client previews and the server decides and a disagreement must be a display bug only.
<!-- roadmap:end -->
