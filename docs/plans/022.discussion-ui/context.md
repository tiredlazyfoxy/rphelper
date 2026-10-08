# Feature 022 — Discussion UI · feature-wide context

## What this feature is

This feature lets the roleplayer see and work with the assistant in the stream.

- **The live reply.** While a compose streams, the in-flight assistant text renders
  read-only beneath the zone rows. Its thinking and its tool calls are shown **open**.
  When the compose ends, the re-read zone rows replace it, and their thinking and tool
  blocks render **collapsed** and can be re-expanded at any time.
- **Tool rows.** Persisted tool rows render as collapsible tool blocks. They carry no edit
  control.
- **Regenerate.** A persistent control in the zone re-runs generation over the zone as it
  stands. This is the retry at the failed exchange.
- **The collapsed discussion.** Every settled non-partner entry carries a collapsed,
  read-only "Discussion" group, loaded lazily through a new backend read.

The agreed boundary is `brief.md` in this folder. Its Definition and Scope In/Out bound every
step and are **not** widened. The brief has no open questions. The user confirmed U1–U4
(below) at planning time.

**Out, and kept out:**

- The server's settle and re-open rules (US-041, US-042 are `012`'s), and the re-open
  affordance (`013`).
- Context (`020`).
- The stop control and the Send/Stop slot (`019`).

## Product ids

Delivers **FEAT-010**: UC-032, UC-035, UC-036, UC-079, US-038, US-039, US-040, US-113,
US-114, US-116. Also exercises US-044.AC-2/3/4, US-115, US-126 and US-132. Ids were
verified against `docs/product/stories/FEAT-010.compose-discussion.md` and
`docs/product/quick-reference.md`.

| Criterion | Where it lands |
|---|---|
| US-113.AC-1 (discussion inline beneath its answer, in the stream) | `006`: the live reply and the Regenerate control render inside the zone region, beneath the zone rows (D12) |
| US-113.AC-2, US-039.AC-1 (settling collapses the discussion in place) | `007`: after settle, the zone rows are gone and the new entry carries a collapsed Discussion group |
| US-114.AC-1 (tool calls and thinking expanded while working) | `004` (blocks open when live), `005` (live tool calls fed by frames), `006` (live reply) |
| US-114.AC-2 (tucked away once finished) | `004`, `006` (persisted rows collapsed), `007` (rows in a discussion collapsed) |
| US-114.AC-3 (re-expandable at any later time) | `004`, `006`, `007` |
| US-040.AC-1 (every collapsed message still readable) | `002` (backend returns every buried row), `007` (rendered) |
| US-116.AC-1 (nothing in a collapsed discussion is editable) | `007` (no edit control). The backend refusal (PATCH on a buried row → `message_not_editable`) is `012`'s and is already built. |
| US-038.AC-1 (a candidate in the zone is editable) | `006` (an assistant zone row keeps its edit control; the editor holds the raw text, D10) |
| US-038.AC-2 (edited candidate settles as edited) | Server half: `012` / `021` `001`, already specified. `006` `[manual/live]` |
| US-044.AC-3 (retry possible) | `005` (`regenerate`, `showsRegenerate`), `006` (the control) (D8) |
| US-044.AC-2 / AC-4 (failure shown with a transient reason) | the existing `notifyFailure` path from 019 D14 / 021 D12. `005` pins it for `regenerate` |
| US-115.AC-1 (zone messages editable), narrowed by 021 D8 | `006` (edit hidden on tool rows only) |
| US-126.AC-1 (settle takes the last message), with 021 D8's non-tool head | `005` (the settle target is the last non-tool row) |
| UC-032 (open a discussion), UC-035 (promote / write / edit) | D12. No new control. Exercised by `006` |

## Build state this feature binds to

**001..014 are built** (committed or in the working tree). **015..021 are planned, not built,
and are built before 022.** 022 binds to built source and to the pending plans' declared
interfaces, cited by plan / step / decision id. Each fact below says which half it comes from.

**Built source** (from the harvest):

- **Backend.**
  - `db/schema.py`:
    - `messages` has `tool_name` and `tool_payload` columns.
    - The CHECK is `related_to IS NULL OR settled_at IS NULL`.
    - There are three module-level Core selectables: `settled_entries`, `current_zone`, and
      `message_states` (id, user_id, session_id, related_to, settled_at only).
    - No selectable returns buried rows with their text.
  - `services/messages.py`:
    - `StreamMessage`, `list_entries`, `list_zone`, `edit_message_text`, and the private
      `_list_session_rows`, `_require_session`, `_to_message`.
    - A guard test (`tests/test_messages_service.py`, S012_002_DoD13) AST-forbids any
      `select(...)` naming `messages` or `messages.c.*` in this module.
  - `routers/stream.py`:
    - The stream routes, including `PATCH /api/messages/{message_id}`.
    - The router does no SQL and imports no `app.db.schema` (AST guard in
      `tests/test_stream_router.py`).
    - Path ids are `SnowflakeIn`. `_message_to_response` is
      `MessageResponse.model_validate(..., from_attributes=True)`.
  - `models/stream.py`: `MessageResponse` (eight keys, ids `SnowflakeOut`), `ZoneResponse`,
    `EntryListResponse`.
  - `errors.py`: `MessageNotFoundError` (`message_not_found`, 404; unknown or foreign id,
    R5) and `MessageNotEditableError` (409).
- **Frontend.**
  - `src/app/streamState.ts`: `StreamState` and its derivations `canSettle`, `showsDiscard`,
    `showsReopen`, `settleTargetText`, `settlePreviewOf`. Its effects never reject.
  - `src/app/streamApi.ts`: `Message` and the seven calls.
  - `ZoneList.tsx`: `ZoneList` and the exported `ZoneMessage`, with an edit control on every
    row.
  - `StreamRecord.tsx` (`StreamEntry`, with 014's action group).
  - `MessageBody.tsx` (variants painted / decision / plain).
  - `SessionStream.tsx`.
  - `src/shared/IconButton.tsx` (`sizeVariant` is `"main"`, `"inline"` or `"chevron"`) and
    `src/shared/notifyFailure.ts`.

**Pending plans** (bind to their declared interfaces):

- **019.**
  - `003`: the `shared/sse.ts` consumer and its frame union, which includes
    `tool_start{tool, call_id, args}`, `tool_result{tool, call_id, summary}` and
    `tool_fail{tool, call_id, code}`; and the four outcomes (019 D9).
  - `004`: `composeZone`, the streaming text field (D11), the non-observable compose handle
    (D12), `isStreaming`, `stopCompose`, and the D13 derivation changes.
  - `005`: `composeMessage` (D14 outcome table, D15 `accepted`, D16 settle-mid-stream).
  - Tool frames are ignored in 019 (D18). **022 supersedes D18** (D7 below).
- **021.**
  - `001`: `StreamMessage` gains `tool_name` and `tool_payload` (default none). PATCH of a
    tool row → `message_not_editable`. The settle head is the last non-tool row. Its DoD-4
    asserts that no wire message carries tool keys. **022 `001` amends that test.**
  - `007`: `composeZone`'s text is optional (absent → body `{}`). Send on *my turn* →
    `composeMessage`.
  - 021 D2: a textless compose is the retry, sends no `accepted`, and is refused
    `zone_empty` when the zone has no non-tool row.
  - 021 D4: the `<think>` convention and its strip rule.
  - 021 D7: tool row columns and payload.
  - 021 D8: tool-row invariants.
- **017 `011`** adds a `sendBlockedReason` prop through `SessionStream` → `Composer`.
- **018 `003`** rebuilds `Composer` on `ComposerCore`.
- **022 touches neither Composer nor ComposerCore** (D16).

## Architecture this binds to

- `docs/architecture/workspace-shell.md`: "The stream — the settled record" (the buried
  discussion hangs under its entry, collapsed and read-only; where re-open sits); "The ruler
  and the current zone" (every zone message editable; collapsible tool and thinking blocks;
  transient reason plus persistent retry; R10); "The stop control".
- `docs/architecture/ui-conventions.md`:
  - The icon table: chevron `IconChevronDown` rotated; thinking `IconBulb`; the tool glyph is
    `_TBD:` (closed by D14).
  - `IconButton` is the only icon-only control.
  - "Async feedback" and "The tension with US-044.AC-3".
  - Loading, errors and empty states: a failure with an in-page place renders there only.
- `docs/architecture/frontend-structure.md`: "State — MobX 6", "Ids are strings", "The API
  client", "The SSE consumer", "Markdown".
- `docs/architecture/data-model.md` `messages` and its views. Raw `messages` is touched only
  by settle and re-open, and every reader goes through a named predicate.
- `docs/architecture/domain-rules.md` **R7** (a buried group stays readable and is never
  editable), **R10**, **R11**, **R12**.
- `docs/architecture/backend-structure.md`: the stream routes, "The JSON id boundary", the
  error model.

Cited, never copied.

## Files this feature touches

```
backend/
  app/services/messages.py      # tool view derivation; StreamMessage tool fields (001);
                                #   list_discussion (002)
  app/models/stream.py          # MessageResponse tool fields (001); DiscussionResponse (002)
  app/db/schema.py              # + buried_messages selectable (002)
  app/routers/stream.py         # + GET /api/messages/{message_id}/discussion (002)
frontend/
  src/app/streamApi.ts          # Message tool fields; fetchDiscussion (003)
  src/app/thinking.ts           # NEW — pure think-segment parser (003)
  src/app/ThinkingBlock.tsx     # NEW (004)
  src/app/ToolBlock.tsx         # NEW (004)
  src/app/AssistantBody.tsx     # NEW (004)
  src/app/streamState.ts        # liveTools, tool frames, regenerate, derivations (005)
  src/app/ZoneList.tsx          # role-aware rows, editable flag, live reply, Regenerate (006)
  src/app/LiveMessage.tsx       # NEW (006)
  src/app/DiscussionGroup.tsx   # NEW (007)
  src/app/StreamRecord.tsx      # mounts DiscussionGroup in non-partner entries (007)
```

**Not touched. A step that touches one is out of scope:**

- Backend: `services/settle.py`; every router other than `stream.py`; `errors.py` (no new
  code); `main.py`; `tests/conftest.py`.
- Frontend: `Composer.tsx`, `ComposerCore.tsx`, `KindSwitch.tsx`, `SessionScreen.tsx`,
  `SessionStream.tsx`, `MessageBody.tsx`.
- Frontend shared and config: `src/shared/*` (including `sse.ts`, `api.ts`, `IconButton.tsx`
  and `notifyFailure.ts`); `src/global.css`, `src/shell.css`; `vite.config.ts`.
- Frontend guard tests: `tests/conventions.test.ts`, `tests/stylesheets.test.ts`,
  `tests/build-config.test.ts`.

No new dependency on either side: Mantine, `@tabler/icons-react` (which ships `IconBulb`,
`IconTool`, `IconChevronDown` and `IconRefresh`), `mobx` and `react-markdown` are all
present.

## Cross-cutting constraints every step holds

- **R11 predicate discipline.** No query in `services/messages.py` names `messages`
  directly. Every read goes through a named module-level selectable in `db/schema.py`. The
  router does no SQL and imports no schema.
- **R5 owner scoping.** Every read is filtered by the authenticated user at the query.
  A foreign id is indistinguishable from an unknown one (`message_not_found`, 404).
- **Tool internals never leave the backend.** `call_id`, the raw tool `content` and the raw
  `tool_payload` string are never wire fields (D3).
- **Never optimistic.** What renders is what the server served. The live reply is a view of
  the streaming text, never a row in `zone`, and it is replaced by a zone re-read (019 D11 /
  D14).
- **Nothing typed is lost (R10).** No new path clears the draft, `zone` or `entries`.
  `regenerate` never touches the draft.
- **Pure data contracts (MobX).** `StreamState` holds observable fields only, plus 019's one
  non-observable handle. Derivations and effects are free functions; effects write in
  `runInAction`, never reject, and write nothing after the mount signal aborts. Expand/collapse
  flags and a discussion group's loaded rows are **component-local view state** (D5, D11).
- **Every icon-only control goes through `shared/IconButton`.** Its props are not widened. A
  rotated chevron is passed as the `icon` component (`004.context.md`).
- **Styling is Mantine only.** Component and style props; no `.css` file and no new selector.
  `tests/stylesheets.test.ts` pins exactly two stylesheets.
- **No success notification.** **022 adds no `notifyFailure` call site of its own.** Compose
  and regenerate failures go through 019 D14's existing path. A discussion load failure has an
  in-page place and renders there (D11).
- **Ids are strings**, compared by equality, never sorted. The client renders served order.
- Backend fully typed (`mypy app`, `ruff check .`). Frontend TypeScript only
  (`npm run typecheck`).

## Decisions — settled, with their reasoning

U1–U4 are user-confirmed. The rest are planner decisions; the ones that touch architecture are
flagged in `outcome.md`.

### D1 — The buried group is read lazily through a message-addressed route (U1)

`GET /api/messages/{message_id}/discussion` answers `{"messages": [...]}`. The list holds the
rows whose `related_to` is that id, owned by the caller, ascending by id, each a
`MessageResponse` (with D3's tool fields).

| The id names… | Answer |
|---|---|
| an owned **settled** row with buried rows | 200, those rows in id order |
| an owned settled row with nothing buried (a partner block, a lone directly-settled turn) | 200, `{"messages": []}` |
| an owned **zone** row or an owned **buried** row | 404 `message_not_found` |
| an unknown id, or another user's row (any state) | 404 `message_not_found` (R5) |
| unauthenticated | 401 (the existing auth dependency) |

- **Why `message_not_found` for a zone or buried id** (planner, confirming the briefing's
  recommendation): the route reads "the discussion of a settled entry", and only a settled
  row is an entry. A distinct code would tell the client nothing actionable, and reusing the
  existing 404 adds no error code.
- **`GET …/entries` is unchanged.** It carries no count and no flag. The client cannot see
  whether a group exists until it asks. So 013 D4's accepted imprecision on re-open stands,
  and the count is shown only once loaded (D11).
- **Why message-addressed:** the group belongs to its head row, not to the session. The PATCH
  route already addresses a message the same way.

### D2 — A fourth named selectable, `buried_messages` (U1; flagged for /architect)

`db/schema.py` gains a module-level Core selectable named **`buried_messages`**. It returns
every `messages` column for rows where `related_to IS NOT NULL`, with no owner or session
filter, like its siblings. Owner filtering happens at the query, in the service.

**Why:** the service guard forbids `select(messages…)`, and `data-model.md` treats a query
naming raw `messages` outside settle and re-open as a defect. A named selectable keeps the
predicate in one place, exactly as `settled_entries` and `current_zone` do. Raw `messages` is
still written only by settle and re-open. This adds a **reader** of buried rows; it does not
weaken R11. The name must not collide with any registry table.

### D3 — Tool fields on the wire: name, status, arguments (U2)

`StreamMessage` and `MessageResponse` gain three fields, all null on a non-tool row:

| Field | On a `role='tool'` row |
|---|---|
| `tool_name` | the column value as stored (a string, or null if absent) |
| `tool_status` | `"ok"` when the payload parses as a JSON object whose `status` is exactly `"ok"`; **`"failed"` otherwise** (status `"failed"`, any other status, no status, a null or unparseable payload, a payload that is not an object) |
| `tool_args` | the payload's `arguments` member (a raw JSON string, per 021 D7) parsed. If that parses to a JSON **object**, it is that object. Otherwise (missing, not a string, unparseable, an array or scalar) it is `{}` |

- **Never on the wire:** `tool_payload`, `call_id`, `content`, `code`. The summary is already
  the row's `text`.
- **Why a parsed object:** it is the same shape as 019's `tool_start.args`, which is the
  parsed object or `{}` per 021 D6. So a live tool block and a persisted one render arguments
  identically.
- **Why "failed" when the payload is unreadable:** a row whose success cannot be confirmed
  must not claim success. 021's writer always writes a readable payload, so this is a
  defensive rule only.
- The derivation lives in `services/messages.py`, so every `StreamMessage` the service
  returns carries it. The router keeps mapping attributes. `MessageResponse` therefore has
  **eleven** keys.
- **Amended tests:** 021 `001` DoD-4 (no tool keys on the wire), and any 012-era assertion
  pinning the message key set to exactly eight keys. Each is amended with a chained suffix
  (`001.context.md`).

### D4 — The client's think parse is consistent with 021 D4

`src/app/thinking.ts` is pure and DOM-free. It splits an **assistant** text into ordered
segments. It is only ever applied to `role: "assistant"` text; user text is never parsed.

- A **think segment** is the text between `<think>` and the **nearest following**
  `</think>`, verbatim (not trimmed), flagged **closed**. An unterminated `<think>` runs to the
  end of the text, flagged **not closed**. Tags are exactly `<think>` and `</think>`,
  lowercase and case-sensitive.
- **Answer segments** are the text outside think blocks.
  - **If no think block is found**, the result is **exactly one answer segment holding the
    text byte-for-byte**, even when it is empty.
  - If at least one block is found, each answer segment is trimmed of surrounding whitespace,
    and empty ones are dropped. This mirrors 021 D4's "trim only if something was removed".
- A stray `</think>` with no opener is literal answer text.
- Think segments are kept even when empty. `<think>` alone, the first token of a reasoning run,
  is a live signal that the assistant is reasoning.

**Worked examples** (tests in `003`, `004` and `006` bind to these):

| # | Input | Segments, in order |
|---|---|---|
| 1 | `Hello` | answer `Hello` |
| 2 | `  Hello  ` | answer `  Hello  ` |
| 3 | `<think>plan</think>\n\nHello` | think `plan` (closed); answer `Hello` |
| 4 | `<think>a</think>One<think>b</think> two` | think `a` (closed); answer `One`; think `b` (closed); answer `two` |
| 5 | `Start<think>never closed` | answer `Start`; think `never closed` (not closed) |
| 6 | `<think>only</think>` | think `only` (closed) |
| 7 | `a </think> b` | answer `a </think> b` |
| 8 | `<think>x\ny</think>\n((ooc))` | think `x\ny` (closed); answer `((ooc))` |
| 9 | `<think>` | think `` (empty, not closed) |
| 10 | `` (empty) | answer `` (empty) |

### D5 — Thinking and tool blocks: open when live, collapsed when persisted (orchestrator default)

- A **thinking block** shows a header (chevron toggle, `IconBulb`, the label "Thinking") and,
  when open, the think text as plain pre-wrapped dimmed text. No markdown and no `(( ))`
  painting: it is the model's scratch text.
- A **tool block** shows a header (chevron toggle, `IconTool`, the tool name, a status word)
  and, when open, the arguments and the summary.
- **Whether a block starts open is fixed by where it renders:**
  - In the **live reply**, every block starts open (US-114.AC-1).
  - On a **persisted row** (zone or discussion), every block starts collapsed
    (US-114.AC-2).
  - Any block toggles at any time (US-114.AC-3).
- **The open flag is component-local `useState`, initialised once.** The live → persisted
  transition needs no code. When the compose ends, the live reply unmounts, the re-read rows
  mount, and their blocks start collapsed.
- **A collapsed block's body is not rendered.** It is conditionally rendered, not hidden by
  CSS or `Collapse`. "Tucked away" is then observable as absence, and no stylesheet is needed.
  The chevron rotation carries the state visually.

### D6 — The live reply is read-only and sits beneath the zone rows (U4)

While `isStreaming(state)`, the zone region renders a **live reply** beneath the last zone row.
It has the author label "Assistant", then one open tool block per live tool call (D7) in
arrival order, then the streaming text rendered through the assistant body with its thinking
open.

- It has **no edit control**. That resolves `frontend-structure.md`'s "the editor binds to
  the in-flight message" for the as-built shape: an edit racing the server's own write of
  that row would be lost or would clobber it (019 D11).
- On every outcome, 019 D14's zone re-read replaces it with the persisted rows, and the
  persisted assistant row is editable like any zone message.
- **Tool blocks come before the text** because that is the persisted order. 021 writes each
  tool row when its call completes, and the one assistant row at the end (021 D7, D11). The
  live reply therefore previews the order the re-read will show.

### D7 — Live tool calls are observable state fed by the tool frames (supersedes 019 D18)

`StreamState` gains an observable list of **live tool calls**. Each entry holds: call id,
tool name, arguments object, status (`running` / `ok` / `failed`) and summary (string or
null). The compose run's frame handler maintains it:

| Frame | Effect on the list |
|---|---|
| `tool_start` | append `{call id, tool, args, running, summary null}` |
| `tool_result` | the entry with that call id → `ok`, summary = the frame's summary |
| `tool_fail` | the entry with that call id → `failed`, summary = `The tool failed.` (021's failed-row literal, so live and persisted read alike) |
| `tool_result` / `tool_fail` for an unknown call id | ignored |

- The list is emptied when a compose run starts.
- It is emptied **in the same action** that clears the streaming text, so the live tool
  blocks and the live text leave together and are replaced by the re-read rows.
- Nothing is written after a mount abort.
- Tool frames never touch `zone`.

### D8 — Regenerate: the persistent retry, widened into a general regenerate (U3)

- **`showsRegenerate(state)`** is true iff all of the following hold:
  - not streaming;
  - not `busy`;
  - `zone` holds at least one row whose role is not `"tool"`.

  It is derived from persisted zone rows, so it survives a reload. That is the "persistent
  retry at the failed exchange" (US-044.AC-3, `ui-conventions.md`'s split).
- **`regenerate(state, mountSignal?)`** is a textless compose:
  - It calls `composeZone` with no text (body `{}`, 021 `007`), going through the **same run
    machinery** as `composeMessage`: the same compose handle (so Stop and 019 D16's
    settle-mid-stream apply unchanged), the same token handling, D7's tool handling, and
    019 D14's outcome table and terminal zone re-read.
  - It **never reads or writes the draft**.
  - No `accepted` frame is expected (021 D2). If one arrives, it only triggers 019 D15's zone
    re-read.
  - It is a no-op when `showsRegenerate` is false.
  - A refusal (for example 409 `zone_empty` from a stale view) is the outcome table's error
    row: `notifyFailure` plus a zone re-read.
- The control is a **labelled button "Regenerate"** (D14), placed after the last zone row and
  absent (not disabled) when `showsRegenerate` is false. That follows the re-open and discard
  precedent: a control for an action that does not currently exist is not drawn.
- **Widening, recorded:** the control is available after any exchange, not only a failed one.
  The server cannot distinguish the two (021 D2), and a "failed" marker would need persisted
  state that does not exist. `outcome.md` raises it for `/product-spec`.
- Regenerate is not gated by 017's `sendBlockedReason`. A blocked model surfaces as the
  compose's own typed error through `notifyFailure`.

### D9 — Tool rows in the zone derivations (021 D8 forward note)

- **`canSettle`**: *my turn*, not `busy`, and (a **non-tool** zone row exists **or** the draft
  is non-blank). The rule was "the zone is non-empty"; it now mirrors the server's head rule.
- **The settle target** (013 D1's `settleTargetText`, read by the preview) is the **last
  non-tool** zone row's text when the draft is blank.
- **`showsDiscard`** is unchanged: a zone holding only tool rows is non-empty and not
  discardable.
- **No trap:** a tool-only zone is unreachable in practice, because tool rows are written only
  inside a compose that already has a non-tool row (021 D2). Even if one existed, typing a
  draft enables Settle, which appends then settles.

### D10 — Editing an assistant row edits its raw text, think tags included (planner)

The zone editor holds the row's stored text verbatim, including any `<think>…</think>`.

- **Why:** the editor edits the stored row, and the server strips think blocks at settle
  (021 D4).
- A roleplayer who wants the reasoning gone deletes it. One who leaves it loses nothing: it
  never reaches the record.
- Rendering parsed segments in the editor would make the edit lossy.

### D11 — The collapsed Discussion group under a settled entry (U1)

- **Where it renders.** Every settled entry whose kind is not `partner` renders a Discussion
  group below its body. A partner block is born settled with nothing buried (R11), so it gets
  none.
- **Collapsed.** It shows only its header:
  - a chevron toggle;
  - the label "Discussion", or "Discussion (N)" once loaded, with N the number of rows;
  - the marker "Read-only".

  No request is made while collapsed.
- **On first expand.** It fetches `GET /api/messages/{id}/discussion` once and shows a Mantine
  `Loader` until the answer arrives. Then it renders one of:
  - the rows as a list labelled "Discussion messages", each through 013's row component in
    **read-only mode** (D12 below, step `006`) with blocks collapsed;
  - "No discussion behind this entry." for an empty list;
  - "The discussion could not be loaded." **inline** on failure. `notifyFailure` is **not**
    called, because a failure with an in-page place renders there only
    (`ui-conventions.md`).
- **Collapse and re-expand.**
  - Loaded rows are kept for the component's lifetime, so re-expanding makes no second
    request.
  - A failure is forgotten on collapse, so the next expand fetches again. That is the retry.
- **The state is component-local.** The open flag, the load status and the loaded rows are
  `useState`, and in-flight fetches abort on unmount. Their lifetime is exactly the entry's
  mount:
  - re-opening unmounts the entry, because it leaves `entries`;
  - a re-settle mounts a fresh entry with a fresh group.

  So no cache in `StreamState` can go stale.
- **Re-open.** It keeps 013 D4's flip condition unchanged.

### D12 — Opening a discussion, inline placement, and the collapse (orchestrator default)

- **There is no separate "open a discussion" control.** The current zone *is* the discussion
  on the answer being worked out, and it opens with the first message sent on *my turn*
  (UC-032).
- **Inline placement (US-113.AC-1)** is the zone below the ruler, beneath the record, with the
  live reply and Regenerate inside the zone region.
- **The collapse (US-039.AC-1, US-113.AC-2)** is what settle's re-read already does:
  - the buried rows leave `zone`;
  - the new entry appears in the record with its Discussion group collapsed.

  No animation and no client-side move happen.
- **The read-only rendering (US-116.AC-1)** is the zone's row component with editing
  switched off. The edit control is **absent**, not disabled.

### D13 — Failure notice and retry (US-044)

- **The transient reason** is 019 D14 / 021 D12's existing `notifyFailure`. 022 adds no call
  site.
- **The persistent retry** is D8.
- Nothing in the zone or the record is discarded on either path (R10).

### D14 — Icons and controls (closes `ui-conventions.md` `_TBD:`s; flagged)

| Control | Rendering |
|---|---|
| Expand / collapse (thinking, tool call, discussion) | `IconButton`, `IconChevronDown`, `sizeVariant "chevron"`, rotated `-90°` when collapsed; label per the strings table |
| Thinking glyph | `IconBulb` (decorative, beside the label) |
| Tool glyph | **`IconTool`** (decorative). This closes the icon table's `_TBD:` |
| Regenerate | a **labelled** Mantine `Button` "Regenerate", subtle, with `IconRefresh` as its left section at the inline size. It is not icon-only, so it is not an `IconButton`. Labelled like Send and Settle because it starts a model call |

### D15 — Client `Message` tool fields are optional (planner)

`Message` gains `tool_name`, `tool_status` and `tool_args`, each **optional** and nullable.
Absent is treated exactly as null.

**Why optional:** the backend always sends all three, but 013–021's test fixtures build
eight-key `Message` literals. Making the fields required would break `npm run typecheck`
across files no 022 step owns.

### D16 — 022 does not touch the Composer (flagged forward)

The Send/Stop slot is 019's, and `sendBlockedReason` is 017's. **There is an inter-plan
conflict that is not 022's to fix:**

- 018 `003` rebuilds `Composer` on `ComposerCore`, which hard-renders Send.
- 019 `004` requires Send to be absent while streaming.

It is recorded in `outcome.md` for the user. 022 keeps out of both files.

## Step map

| Step | Subject | Est. source LoC | Depends on |
|------|---------|-----------------|------------|
| 001 | Backend: tool view derivation; `StreamMessage` / `MessageResponse` tool fields | ~60 | none (021 `001` built) |
| 002 | Backend: `buried_messages`; `list_discussion`; `GET …/discussion`; `DiscussionResponse` | ~80 | 001 |
| 003 | Frontend: `Message` tool fields; `fetchDiscussion`; `thinking.ts` | ~70 | none (wire per 001 / 002; tests stub `fetch`) |
| 004 | Frontend: `ThinkingBlock`, `ToolBlock`, `AssistantBody` | ~150 | 003 |
| 005 | Frontend state: live tool calls; `regenerate`; `showsRegenerate`; non-tool `canSettle` and settle target | ~120 | 003; 019 `004` / `005`, 021 `007` built |
| 006 | Frontend: role-aware `ZoneMessage` (editable flag, no edit on tool rows); `LiveMessage`; Regenerate in `ZoneList` | ~130 | 004, 005 |
| 007 | Frontend: `DiscussionGroup` under settled entries in `StreamRecord` | ~120 | 003, 004, 006 |

The backend steps (`001`, `002`) and the frontend steps (`003`–`007`) are independent of each
other for tests. The `[manual/live]` items need both halves.

## Test conventions

**Backend**, run from `backend/`:

- pytest, flat `tests/`. Names are `test_<snake>__S022_<SSS>_DoD<n>`. An amended existing test
  keeps its name and chains a suffix, for example
  `…__S021_001_DoD4__S022_001_DoD3`.
- A file-local `engine` fixture over conftest's `db_engine`, with `_insert_user`,
  `_insert_character` and `_insert_session`. Messages are seeded raw with explicit
  `related_to` / `settled_at`, so buried and settled states are built directly.
- Two users for isolation.
- Router tests use `_login_token`, `_player_a` / `_player_b`, and
  `_assert_envelope(response, status, code)`.
- Ids are compared as JSON strings on the wire.
- **Expected values come from this plan:** D1's table, D3's table, and the payloads in
  `001.context.md`.

**Frontend**, run from `frontend/`:

- Vitest/jsdom. `tests/` mirrors `src/`. Each file opens with the header comment
  "Feature 022, step NNN — … (DoD-x..y)", and each `it` title ends `— DoD-N`.
- `fetch` is stubbed per file with `vi.stubGlobal`, keyed on exact pathname + method.
  Streamed bodies are a `Response` over a `ReadableStream` of `Uint8Array` chunks.
- `notifyFailure` is observed through `vi.hoisted` + `vi.mock`, asserting the `ApiError` code
  only.
- The store is seeded with `runInAction`. Components render inside `<AppProviders>`.
- Ids are string literals like `"7250000000000000042"`.
- **Expected values come from this plan:** D4's table, D3's shapes, and the strings table
  below.
- Controls are found by accessible name.
- An amended 013–021 test keeps its title and appends ` — DoD-N (022 SSS)`.

## UI strings — the contract tests bind to

| Where | String | Element |
|---|---|---|
| Thinking toggle | **"Show thinking"** (collapsed) / **"Hide thinking"** (open) | `IconButton` |
| Thinking label | **"Thinking"** | text |
| Tool toggle | **"Show tool call"** (collapsed) / **"Hide tool call"** (open) | `IconButton` |
| Tool status | **"Running"** / **"Done"** (`ok`) / **"Failed"** | text in the tool header |
| Tool name fallback | **"Unknown tool"** (tool name null or absent) | text |
| Tool body | **"Arguments"**, then the arguments as `JSON.stringify(args, null, 2)`, or **"No arguments."** when the object has no keys; then the summary text when non-null | text / code block |
| Live reply | region with accessible name **"Live reply"**; author label **"Assistant"** | `region` / `section` |
| Regenerate | **"Regenerate"** | labelled button |
| Discussion toggle | **"Show discussion"** (collapsed) / **"Hide discussion"** (open) | `IconButton` |
| Discussion header | **"Discussion"**, or **"Discussion (N)"** once loaded; marker **"Read-only"** | text |
| Discussion list | list labelled **"Discussion messages"** | `list`; each row a `listitem` |
| Discussion empty | **"No discussion behind this entry."** | text |
| Discussion failure | **"The discussion could not be loaded."** | text |

013's strings ("Zone messages", "You" / "Assistant" / "Tool", "Edit message", "Edit message
text", "Settled record") are unchanged.

## Vocabulary

| Term | Means here |
|---|---|
| **live reply** | the read-only rendering of the streaming text and the live tool calls while streaming (D6) |
| **live tool call** | one entry of `StreamState`'s live tool list, fed by tool frames (D7) |
| **segment** | one piece of a parsed assistant text: think (closed or not) or answer (D4) |
| **block** | the collapsible thinking or tool rendering (D5) |
| **discussion** / **buried group** | the rows whose `related_to` is a settled entry's id (R7) |
| **regenerate** | a textless compose over the zone as it stands (D8, 021 D2) |
| **tool view** | D3's `tool_name` / `tool_status` / `tool_args` derived from a tool row |
