# Feature 013 — Stream and zone UI · outcome

Intended changes to `docs/architecture/` once this feature ships, for the architect to
apply at finalization. Grouped by target file. Decisions referenced as D-n are in this
folder's `context.md`; "012 Dn" are in `docs/plans/012.messages-and-settle/context.md`.

## `docs/architecture/workspace-shell.md`

| Section | Intended change | Reason |
|---|---|---|
| "Discarding an empty current zone" — first paragraph | Replace "clears the unsent draft and resets the kind switch" with: the control is **present only while the zone has no rows and the composer holds nothing but whitespace**; pressing it clears that whitespace and **resets the kind switch to its computed default**. It never discards typed text — UC-086's postcondition read literally. Absent, not disabled, otherwise (US-134.AC-2). Still frontend-only, no route (D3, user decision). | The old wording implied Discard throws away an unsent draft, which UC-086's postcondition forbids. |
| "Discarding an empty current zone" | Record the glyph: **`IconX`** through `IconButton`, labelled "Discard empty zone" — `IconX` already means "dismiss" on the wall; `IconTrash` would promise a deletion of content that does not exist (D3). | Closes the glyph `_TBD:` (mirrored in `ui-conventions.md`). |
| "The stream — the settled record" — the re-open paragraph | Record placement: an `IconArrowBackUp` `IconButton` labelled "Re-open last entry" inside the **last** settled entry, present only when the zone has no rows and that entry's kind is not `partner`; the composer's content does not gate it. Record the **accepted imprecision**: the client cannot see whether a buried group exists, so the control shows on a lone directly-settled turn or decision and the server refuses with `nothing_to_reopen`, surfaced through `notifyFailure` and followed by a re-read (D4, user decision; 012 D10). Flip condition: a buried-group read (`022`) lets the client hide it exactly. | Placement and the trade-off were unstated. |
| "The kind switch and settle" — the carried US-120 `_TBD:` (~line 302) | Remove it if 012's finalization has not: US-120.AC-3 answers it (012 D5). Record as built: the default is the alternate of the last `partner` / `turn` entry, decisions skipped, computed client-side; **with no such entry the default is *my turn*** — a wrong *partner* default files the roleplayer's own paste as an un-re-openable partner block, a wrong *my turn* default costs one click (D8). A manual choice holds until the record's id sequence changes or Discard resets it. | Stale `_TBD:`; the empty-record default was unspecified. |
| "The kind switch and settle" — the preview paragraph | Record: the preview is a **client-side port** of the server's `(( ))` rules (`app/parens.ts`), shown as one of three fixed sentences under the composer on *my turn* when there is something to settle; it previews the **settle target** — the composer text when non-blank, else the last zone message (D1, user decision; closes `013`'s brief question). | Location and source of the preview were open. |
| "The kind switch and settle" — Settle's disabled conditions | Amend "Its only disabled condition is an empty zone": Settle on *my turn* is enabled when the zone has a row **or the composer holds non-blank text**; pressing it with composer text **appends that text, then settles** (two requests; a failed settle leaves the appended row in the zone). Disabled while a mutation is in flight (D2, user decision; D15). | Unsent composer text was not covered; "only disabled condition" was literally false once in-flight disabling exists. |
| "The kind switch and settle" — partner bullet | Record: on *partner* a paste is intercepted and filed through `POST …/entries`; the composer's content is untouched; Send on *partner* files the typed text as a partner block; no zone precondition (012 D14) (D7). | As built. |
| "The kind switch and settle" — painting paragraph | Record that painting applies **in the zone only**: settled `decision` entries render the same dashed card **by kind**; settled `partner` and `turn` entries render plain markdown — partner parens are the partner's words (US-121.AC-2) and painting a settled turn would re-parse stored text (R12) (D5). | "Painted inside the zone" did not say what the record does. |
| "The ruler and the current zone" | Record as built: zone messages are edited by an `IconEdit` control that swaps the body for an autosizing textarea; blur commits; blank or unchanged text sends nothing; the `PATCH` response replaces that one row; on failure the editor **stays open with the typed text** (R10) and the zone is re-read (D10). The edit control is always visible in 013 (no stylesheet for a hover reveal). | As built; the failure posture is a refinement. |
| "The ruler and the current zone" — first paragraph | Record the ruler as built: a Mantine `Divider` labelled "Current zone", the stream's only `separator` (D12). | As built. |

## `docs/architecture/ui-conventions.md`

| Section | Intended change | Reason |
|---|---|---|
| Icon table — "Discard an **empty** current zone" | Replace the `_TBD:` with **`IconX`** (D3); keep the absent-not-disabled note. | Glyph chosen. |
| "Mutations are never optimistic" | Add the stream as an instance of the narrowed re-load: settle, re-open and partner filing re-read the affected lists (settle / re-open return ids only); a zone edit replaces the one row from the `PATCH` response; every stream mutation failure goes through `notifyFailure`, then re-reads (D15). | The workspace's first real instance. |
| "Async feedback" | Add the stream as a `notifyFailure` call site (mutation failures have no place of their own), and the stream load as an in-place failure ("Could not load the stream" + Retry) (D15). | New call site, recorded as the doc does for others. |

## `docs/architecture/frontend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| "Markdown" | Record that **`react-markdown` is now a dependency** (added by plan 013) and that the one renderer is `app/MessageBody.tsx`, with three variants (painted for zone messages, decision card, plain) (D5). | The doc named the library before it was installed. |
| "Where a store's file lives" / "State — MobX 6" | Record `app/streamState.ts` as the session stream's store — data class, derivations and effects in one module, owned by `app/SessionStream.tsx` (one per mount), separate from 011's `sessionScreenState.ts` (D13). Note the `(( ))` rules as a pure module `app/parens.ts` shared by the preview and the painter (D1). | New store and pure module. |
| "The API client" | Record `app/streamApi.ts` as the stream's client (seven calls, ids as strings) (D14); note that no code is branched on in 013 — the codes listed there (`zone_empty`, `zone_not_empty`, `nothing_to_reopen`, `message_not_editable`) all reach `notifyFailure` uniformly. | As built; the listed branch codes are not yet branched on. |
| "Ids are strings" | Add: client-side whitespace in the `(( ))` port is JavaScript's `trim`, not Python's `isspace`; the rare differing code points are an accepted display-only divergence (D16). | Recorded so the difference is not "fixed" into a hand-built set. |

## `docs/architecture/domain-rules.md`

| Section | Intended change | Reason |
|---|---|---|
| R11 — the abandoning bullet | Align with D3: abandoning resets the kind switch and clears a whitespace-only composer; it is **not offered** while the composer holds text, so it never discards anything written. | The bullet says it "clears the client's unsent composer draft". |
| R12 — the layer table, "Client" row | Point to `app/parens.ts` as the one client port, used by the preview and the zone painting only (D1, D5). | As built. |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| The US-120 `_TBD:` (~line 810) | Remove if still present (012's outcome already asks); add "empty record → *my turn*" (D8). | Stale. |
| Paths / frontend modules | Add `app/streamApi.ts`, `app/parens.ts`, `app/streamState.ts`, `app/MessageBody.tsx`, `app/StreamRecord.tsx`, `app/ZoneList.tsx`, `app/KindSwitch.tsx`, `app/Composer.tsx`, `app/SessionStream.tsx`. | Dense index. |
| Dependencies | Add `react-markdown` (D5). | Dense index. |
| Icons | Discard → `IconX` (D3). | Dense index. |

## Forward notes (not architecture changes; for the owning plans)

- **`014` (edit and copy settled entries, enormous-paste warning):** settled entries are
  read-only in 013 and render through `MessageBody` `"plain"` / `"decision"`; `014` adds
  the in-entry edit (reuse `005`'s editor pattern and `editMessage` once the backend
  widens `PATCH`) and copy as plain text for `turn` (and partner) entries only — a
  `decision` entry must keep offering **no** copy action (`004` DoD-9 pins it). The
  hover / `:focus-within` reveal of entry actions needs either a Mantine-only approach or
  an architect decision on a stylesheet selector. The enormous-paste warning attaches to
  `006`'s paste handler (partner position) and must never block the filing (R10).
- **`019` / `022` (streaming compose, stop):** Send on *my turn* is the non-streaming
  append today; compose replaces or sits beside it in the same slot, and the stop control
  replaces Send while streaming (`workspace-shell.md`). Streamed tokens should write into
  `StreamState.zone`'s in-flight row so `005`'s editor binds to it. `busy` currently
  disables Settle during a send; `workspace-shell.md` says a generation in flight does
  **not** disable Settle — `019` must separate "streaming" from `busy`.
- **`022` (buried-group reading — US-040, US-113, US-116):** a buried-read route would also
  let `004` show "Re-open last entry" only where a group exists, removing D4's
  imprecision.
- **`021` (assistant / tool rows):** zone rows with `role='assistant'` / `'tool'` already
  render and are editable (`005`); the collapsible tool / thinking blocks (US-114) are
  not designed in 013.
- **`024` (search-coverage banner, US-112):** sits above `StreamRecord` in
  `SessionStream`.
- **`017` (model picker):** belongs in 011's session header, above the stream; nothing in
  013 occupies that slot.
