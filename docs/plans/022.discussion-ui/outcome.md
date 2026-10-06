# Feature 022 — Discussion UI · outcome

Intended changes to `docs/architecture/` once this feature ships, for the architect to apply
at finalization. Grouped by target file. D-n refers to this folder's `context.md`, and U1–U4
are the user-confirmed decisions it records.

## `docs/architecture/workspace-shell.md`

| Section | Intended change | Reason |
|---|---|---|
| "The stream — the settled record", buried-discussion paragraph | Replace "collapsed, labelled with its message count and marked read-only" with the as-built shape: every settled non-partner entry carries a collapsed "Discussion" header marked "Read-only"; the rows load lazily on first expand; the count is shown **once loaded** ("Discussion (N)"); an empty group says so; a load failure renders inline, not as a notification; rows render with no edit control (D11, U1). **Architect decides** whether "count once loaded" or "no count" is the documented form. | `GET …/entries` carries no count (U1), so a count cannot be shown before a fetch. |
| same paragraph | Record that 013 D4's accepted imprecision stands: re-open still shows on a lone directly-settled turn or decision and is refused there. The client still cannot see whether a group exists without fetching it (D1). | Flip condition unchanged. |
| "The ruler and the current zone", tool and thinking bullet | Record the as-built rule: blocks are **open in the live reply** and **collapsed on every persisted row** (zone and discussion). The open flag is component-local and initialised once, so the live → persisted swap is a remount, not a state change. A collapsed body is not rendered (D5). | Mechanism for US-114. |
| same section, new bullet | Record the **live reply**: while streaming, a read-only "Live reply" renders beneath the zone rows with live tool blocks (in arrival order), then the streaming text with its thinking open. It has no edit control (U4). The re-read on every outcome replaces it (019 D11 / D14), and the persisted row is then editable (D6). | Resolves "edit while streaming" (019 forward note). |
| same section, retry bullet | Record the retry as built: a labelled **"Regenerate"** button after the last zone row, present iff not streaming, not busy, and a non-tool zone row exists. It is absent, not disabled, otherwise. It issues a textless compose (021 D2). It is derived from persisted rows, so it survives a reload. **It is a general regenerate, available after any exchange, not only a failed one** (D8, U3). | US-044.AC-3 mechanism. Widening flagged for /product-spec below. |
| same section, editability bullet | Amend "Every message in the zone is editable … the assistant's included" with the exception that **tool rows carry no edit control** (021 D8). Assistant rows are edited as raw stored text, `<think>` tags included, which the server strips at settle (D10). | Tool rows' text summarises their payload. |
| "The kind switch and settle" | Record that `canSettle` and the settle preview's target count **non-tool** rows only, mirroring the server's head rule (D9, 021 D8). | Client and server agree on the head. |
| new short note under the zone | "Opening a discussion" has no separate control: the zone is the discussion, and it opens with the first message on *my turn*. The collapse on settle is the settle re-read moving the rows into the entry's Discussion group (D12). | UC-032 / US-113 mechanism as built. |

## `docs/architecture/ui-conventions.md`

| Section | Intended change | Reason |
|---|---|---|
| Icon table: "Collapse / expand a tool call" | Close the `_TBD:` tool glyph as **`IconTool`** (decorative, beside the tool name). The toggle is the rotated `IconChevronDown` `IconButton`, labelled "Show tool call" / "Hide tool call" (D14). | The `_TBD:` is closed by a build choice. Flagged for review. |
| Icon table: "Collapse / expand thinking" | As built: `IconBulb` beside "Thinking". Toggle labelled "Show thinking" / "Hide thinking" (D14). | As built. |
| Icon table, new row | "Regenerate (retry a compose)": a **labelled** subtle `Button` with `IconRefresh` as its left section, not an icon-only control (D14). | New control. Labelled like Send and Settle because it starts a model call. |
| Icon table, new row | "Show / hide a settled entry's discussion": rotated `IconChevronDown` `IconButton`, labels "Show discussion" / "Hide discussion" (D11). | New control. |
| "Async feedback" / "The tension with US-044.AC-3" | Record that the split holds as built: the reason goes through 019 / 021's `notifyFailure` path, and the retry is the "Regenerate" button in the zone (D8, D13). Add that a **discussion load failure** renders inline in its group and is not a notification, applying the "a failure with a place renders there" rule (D11). | As built. |
| `IconButton` section | Note the pattern for a rotated chevron under the unwidened props: pass a small module-level component that renders `IconChevronDown` with a rotation style (`004.context.md`). | Keeps the props type closed. |

## `docs/architecture/frontend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| "The SSE consumer", token bullet | Replace "the consumer writes into the same observable the editor binds to" with the as-built shape: tokens append to `StreamState`'s streaming text (019 D11), rendered read-only as the live reply. The persisted row becomes editable after the re-read (D6, U4). **"Edit while streaming" is deliberately not offered**, because an edit would race the server's own write of that row. | Resolves 019's forward note. |
| "The SSE consumer", tool bullet | Replace "`tool_start` / `tool_result` / `tool_fail` append or update a tool row" with: they maintain an observable **live tool list** on `StreamState` (`running` → `ok` / `failed`, keyed by call id). It is cleared in the same action as the streaming text, when the re-read brings in the persisted `role='tool'` rows (D7). | Tool frames never write `zone`. Supersedes 019 D18. |
| "The SSE consumer" | Record `regenerate`: a textless compose sharing the compose run (handle, stop, settle-mid-stream, outcome table). It never touches the draft (D8). | New effect. |
| "Markdown" | Note that assistant text is split into think and answer segments by a pure client parser (`app/thinking.ts`) consistent with 021 D4's strip rule. Think text renders as plain text, and answer segments through the painted `MessageBody` (D4, D5). | New rendering path. |
| "State — MobX 6" | Note that expand/collapse flags and a discussion group's loaded rows are component-local view state, with the lifetime of the entry's mount (D5, D11). | Same reasoning as modal flags. |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| "The stream routes" | Add `GET /api/messages/{message_id}/discussion`: an owner-scoped read of a settled entry's buried rows, ascending by id, `{"messages": [MessageResponse…]}`. An owned settled entry with nothing buried answers `[]`. An unknown or foreign id, a zone row or a buried row answers 404 `message_not_found`. Read-only (D1, U1). | New route. |
| "The stream routes", wire shape | `MessageResponse` gains `tool_name`, `tool_status` (`ok` / `failed`) and `tool_args` (the call's arguments as a JSON object, `{}` if unreadable), null on non-tool rows: **eleven keys**. `tool_payload`, `call_id` and the raw tool content never leave the backend. The derivation lives in `services/messages.py` (D3, U2). | Supersedes 021 D7's "not on the wire". |
| "The error model" | Note that `message_not_found` also answers the discussion read for a non-settled id (D1). No new code. | Widened meaning. |
| Layout, `services/messages.py` comment | Add "and read a settled entry's buried group (`list_discussion`)". | New function. |

## `docs/architecture/data-model.md`

| Section | Intended change | Reason |
|---|---|---|
| `messages`, "two SQL views" mitigation | Record the as-built state: the predicates are **named module-level Core selectables** in `db/schema.py`, not SQL views. There are now four: `settled_entries`, `current_zone`, `message_states`, and **`buried_messages`** (every column, `related_to IS NOT NULL`, new in 022). The one reader of buried rows is the discussion read. Raw `messages` is still **written** only by settle and re-open (D2). **Flag for review:** R11's "every reader goes through a view" now has a fourth named predicate. | Keeps the one-place-predicate rule true. |
| `messages`, tool rows | Note that the tool view on the wire is derived from `tool_payload` (D3). The column itself stays server-side. | As built. |

## `docs/architecture/domain-rules.md`

| Section | Intended change | Reason |
|---|---|---|
| R7, "A buried group stays readable" | Name the mechanism: the lazy discussion read over `buried_messages`, rendered with no edit control. The PATCH refusal of a buried row (`message_not_editable`, 012) is the server half (D1, D11, D12). | US-040 / US-116 mechanism. |
| R11, "The predicate lives in one place" | Add `buried_messages` to the list of named predicates, and note that it is read-only (D2). | Four predicates now. |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Routes | Add `GET /api/messages/{id}/discussion`. | Dense index. |
| Paths | Add `app/thinking.ts`, `ThinkingBlock.tsx`, `ToolBlock.tsx`, `AssistantBody.tsx`, `LiveMessage.tsx`, `DiscussionGroup.tsx`. Add the `buried_messages` selectable. | Dense index. |
| Icons | `IconTool` (tool block), `IconBulb` (thinking), `IconRefresh` (Regenerate, labelled). | Dense index. |

## Forward notes (not architecture changes; for the owning plans and the user)

- **The user, an inter-plan conflict that is not 022's.** 018 `003` rebuilds `Composer` on
  `ComposerCore`, which hard-renders Send. 019 `004` requires Send to be **absent** while
  streaming, with Stop in its slot. Whichever lands second must reconcile them. 022 touches
  neither file (D16).
- **017 `011`.** "Regenerate" is not gated by `sendBlockedReason`. With no usable model, a
  regenerate fails with the compose's own typed error through `notifyFailure`, and the zone is
  untouched. If the user wants Regenerate hidden or disabled with the reason, that is a
  follow-up touching `ZoneList` (D8).
- **Think-only settled head (021 forward note).** An assistant candidate that is only a think
  block settles as empty text (021 D4). 022 does not surface this before settle. The preview
  line shows the raw last row's classification. Candidate follow-up: a preview warning when
  the settle target's answer segments are empty.
- **/product-spec.**
  - US-044.AC-3's retry is realised as an always-available **Regenerate**, wider than "retry
    after a failure" (D8, U3).
  - The live reply is not editable while streaming (U4). US-115.AC-1 reads "a message in the
    current zone"; the in-flight reply is not yet a message.
  - Tool rows carry no edit control (021 D8), narrowing US-115.AC-1's "whoever wrote it".
  - The collapsed discussion's count appears only once opened (U1).

  These are plan-time decisions with no criterion behind them, raised so the product layer
  can record them or rule otherwise.
- **013 D4.** The re-open imprecision could now be closed client-side by fetching the last
  entry's discussion when the zone empties. It was not done, to keep `GET …/entries` and
  re-open untouched (brief Out).

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B1 (the backend spine — `session-stream.md`, `transfer.md`, `backend-structure.md`, `data-model.md`, `domain-rules.md`) and B3 (the frontend layer — `workspace-shell.md`, `frontend-structure.md`, `ui-conventions.md`, `forms-and-lists.md`).
Rejected items: Its "eleven-key `MessageResponse`" is superseded by 024's addition of `search_coverage_incomplete` — the recorded wire shape is twelve keys.
Notes: The `buried_messages` fourth-predicate flag is accepted and recorded as read-only, and the discussion count is documented as "count once loaded", which satisfies `US-040.AC-2` and `US-040.AC-3`. Two narrowings of `US-115.AC-1` are split: the tool-row exclusion is settled by that criterion's `Constraint:` (no defect), while the live reply's missing edit control is defect D-02, recorded with its race reason and with the open alternative reading left unresolved. Its unreconciled `ComposerCore` / Send conflict with 018 and 019 is recorded as a one-file check for a follow-up, not resolved.
