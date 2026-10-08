# Feature 022 — discussion-ui

| Step | File                                     | Status  | Verifier | Date |
|------|------------------------------------------|---------|----------|------|
| 001  | `001.tool-fields-on-the-wire.md` | done    | PASS     | 2026-10-04 |
| 002  | `002.discussion-read.md` | done    | PASS     | 2026-10-04 |
| 003  | `003.api-and-think-parser.md` | done    | PASS     | 2026-10-04 |
| 004  | `004.thinking-and-tool-blocks.md` | done    | PASS     | 2026-10-04 |
| 005  | `005.live-tools-and-regenerate.md` | done    | PASS     | 2026-10-04 |
| 006  | `006.zone-rows-live-reply-regenerate.md` | done    | PASS     | 2026-10-04 |
| 007  | `007.discussion-group.md` | done    | PASS     | 2026-10-04 |

## Files Changed

### Step 001 — Tool name, status and arguments on the wire
- `backend/app/services/messages.py` — `tool_view` body (D3 derivation via private `_json_object`); `_to_message` and `append_tool_message` fill `tool_status` / `tool_args`
- `backend/app/models/stream.py` — no body change (skeleton's three `MessageResponse` fields are complete)

### Step 002 — The buried-group read
- `backend/app/services/messages.py` — `list_discussion` body (owned-settled check via `settled_entries`, else `MessageNotFoundError`; owner-scoped `buried_messages` read by `related_to`, ascending id, inside `_reading`); imports `buried_messages`
- `backend/app/routers/stream.py` — `get_discussion` body (maps `list_discussion` through `_message_to_response` into `DiscussionResponse`); imports `list_discussion`
- `backend/app/db/schema.py`, `backend/app/models/stream.py` — no change (skeleton declarations complete)

### Step 003 — Client wire: tool fields and `fetchDiscussion`; the pure think-segment parser
- `frontend/src/app/streamApi.ts` — `fetchDiscussion` body (`apiGet` on the encoded `/api/messages/<id>/discussion` path, unwraps `messages` in served order); private `DiscussionResponse` type
- `frontend/src/app/thinking.ts` — `splitThinking` body (single linear `indexOf` scan per D4; untrimmed single answer when no block, else trimmed non-empty answers; think text verbatim) plus private `pushAnswer` helper

### Step 004 — The collapsible thinking and tool blocks, and the assistant body
- `frontend/src/app/ThinkingBlock.tsx` — `ThinkingBlock` body (local `useState` open flag; "Show/Hide thinking" chevron `IconButton`, `IconBulb`, "Thinking"; verbatim pre-wrapped dimmed text only when open) plus private module-level open/collapsed chevron icons
- `frontend/src/app/ToolBlock.tsx` — `ToolBlock` body ("Show/Hide tool call" chevron, `IconTool`, name or "Unknown tool", Running/Done/Failed; open body "Arguments" + `Code block` pretty JSON or "No arguments.", then summary) plus private chevron icons and status-word map
- `frontend/src/app/AssistantBody.tsx` — `AssistantBody` body (`splitThinking` segments in order: `ThinkingBlock` open iff `live`, answers via `MessageBody` "painted"; a lone answer segment renders the bare `MessageBody`)

### Step 005 — Live tool calls, `regenerate`, and the non-tool zone derivations
- `frontend/src/app/streamState.ts` — compose run factored into private `runCompose(state, sent | undefined, signal)` shared by `composeMessage` and `regenerate` (textless run skips the draft on `accepted`, only re-reads); private `applyToolFrame` applies D7's table to `liveTools` (unknown call ids ignored, failed summary "The tool failed."); `liveTools` emptied at run start and in both terminal clearing actions; `showsRegenerate` / `regenerate` bodies; `canSettle` and `settleTargetText` skip tool rows via private `isNonToolRow`

### Step 006 — Role-aware zone rows, the live reply, and the Regenerate control
- `frontend/src/app/ZoneList.tsx` — `ZoneMessage`: `editable = true` default, "Edit message" only when editable and not a tool row, body by role (`MessageBody` / `AssistantBody` live false / collapsed `ToolBlock` from `tool_name`, `tool_status`, `tool_args ?? {}`, `text`); `ZoneList` returns a fragment: list when non-empty, `LiveMessage`, then subtle "Regenerate" `Button` (`IconRefresh` 16/1.5) calling `regenerate(state, signal)` when `showsRegenerate`
- `frontend/src/app/LiveMessage.tsx` — `LiveMessage` body (null unless `isStreaming`; `section` "Live reply" with "Assistant", one open `ToolBlock` per `liveTools` entry keyed by `callId`, then `AssistantBody` over `streamingText` with `live`)

### Step 007 — The collapsed, read-only Discussion group under settled entries
- `frontend/src/app/DiscussionGroup.tsx` — `DiscussionGroup` body (local `useState` open flag / `idle|loading|loaded|failed` status / rows; header with rotated chevron "Show/Hide discussion", "Discussion" or "Discussion (N)", "Read-only"; first expand calls `fetchDiscussion(entryId, signal)` on its own `AbortController`, aborted on unmount, with a mounted guard so nothing is written afterwards; `Loader`, then the "Discussion messages" list of `ZoneMessage` `editable={false}`, the empty line, or the inline failure line with no `notifyFailure`; a failure resets to idle on collapse so the next expand retries) plus private chevron icons
- `frontend/src/app/StreamRecord.tsx` — `StreamEntry` mounts `<DiscussionGroup key={entry.id} …/>` below the body for every non-partner entry; imports `DiscussionGroup`

## Skeleton

### Step 001 — frozen interface (2026-10-04)
- `backend/app/services/messages.py` — `ToolStatus = Literal["ok", "failed"]` — new (module-level type alias)
- `backend/app/services/messages.py` — `class ToolView(NamedTuple): tool_name: str | None; tool_status: ToolStatus | None; tool_args: dict[str, Any] | None` — new (a NamedTuple, so it compares equal to the plain tuple `(tool_name, tool_status, tool_args)`)
- `backend/app/services/messages.py` — `def tool_view(role: str, tool_name: str | None, tool_payload: str | None) -> ToolView` — new, public; stub raises `NotImplementedError`
- `backend/app/services/messages.py` — `StreamMessage` (frozen dataclass) — changed: appends `tool_status: ToolStatus | None = None` and `tool_args: dict[str, Any] | None = None` after `tool_payload` (was: ends at `tool_payload: str | None = None`)
- `backend/app/models/stream.py` — `MessageResponse` — changed: appends `tool_name: str | None = None`, `tool_status: Literal["ok", "failed"] | None = None`, `tool_args: dict[str, Any] | None = None` (was eight fields). Eleven wire keys. `tool_payload` is not a field. The defaults keep the existing eight-kwarg test constructors valid.
- What the coder still has to wire up (the bodies were left intact so the existing paths don't throw): `_to_message`, `append_tool_message`'s result (and so `edit_message_text`, which goes through `_to_message`) must fill `tool_status`/`tool_args` from `tool_view(...)`. The non-tool builders (`append_message` via `insert_zone_message`, `append_assistant_message`, `file_partner_entry`) already default to `None`. `messages.py` may not import `app.services.tools.seam._parse_object` (S012_002_DoD13 guard), so the JSON parsing goes in `messages.py` itself.
- Caller-compile edits (out of Source-files scope): None.
- Existing tests that now fail on the widened key set (they pin exactly eight keys): `test_stream_models.py` (3 S012_001_DoD8 tests), `test_sessions_models.py` (2 S018_001_DoD6 tests), `test_sessions_router.py` (1 S018_002_DoD6), `test_tool_rows.py` (S021_001_DoD4, in Test files), `test_stream_router.py` (8 tests via `MESSAGE_KEYS`/`_assert_message_shape`, in Test files). The first three files are outside this step's Test files. They are mechanical knock-ons under the 2026-10-03 policy.

### Step 002 — frozen interface (2026-10-04)
- `backend/app/db/schema.py` — `buried_messages = select(messages).where(messages.c.related_to.is_not(None))` — new (module-level Core `Select`, defined after `current_zone`, before `message_states`; every `messages` column, no owner/session filter, no ordering; declaration is complete, not a stub)
- `backend/app/services/messages.py` — `def list_discussion(connection: Connection, user_id: int, entry_id: int) -> list[StreamMessage]` — new; stub raises `NotImplementedError`. Raises `MessageNotFoundError` (from `app.errors`, already imported) when `entry_id` is not an owned settled row.
- `backend/app/models/stream.py` — `class DiscussionResponse(BaseModel): messages: list[MessageResponse]` — new (complete declaration)
- `backend/app/routers/stream.py` — `@router.get("/api/messages/{message_id}/discussion", status_code=200) def get_discussion(message_id: SnowflakeIn, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> DiscussionResponse` — new; stub raises `NotImplementedError`
- What the coder still has to wire up: import `buried_messages` into `messages.py` and `list_discussion` into `routers/stream.py` (left out so ruff F401 stays green).
- Caller-compile edits (out of Source-files scope): None.
- Existing tests: `test_db_schema.py`, `test_messages_service.py`, `test_stream_router.py`, `test_stream_models.py` show no new failures. The only failures are step 001's eight-key knock-ons (8 in `test_stream_router.py`, 3 in `test_stream_models.py`).

### Step 003 — frozen interface (2026-10-04)
- `frontend/src/app/streamApi.ts` — `export type ToolStatus = "ok" | "failed"` — new
- `frontend/src/app/streamApi.ts` — `Message` — changed: appends `tool_name?: string | null; tool_status?: ToolStatus | null; tool_args?: Record<string, unknown> | null` (was the eight fields only; those are unchanged). The three are optional (D15); `Record<string, unknown>` matches `SseFrame`'s `tool_start.args`.
- `frontend/src/app/streamApi.ts` — `export async function fetchDiscussion(entryId: string, signal?: AbortSignal): Promise<Message[]>` — new; stub throws `Error("not implemented")`. The coder adds a private `{ messages: Message[] }` response type, mirroring `ZoneResponse`.
- `frontend/src/app/thinking.ts` — `export const THINK_OPEN = "<think>"`, `export const THINK_CLOSE = "</think>"` — new (complete)
- `frontend/src/app/thinking.ts` — `export type ThinkingSegment = { kind: "answer"; text: string } | { kind: "think"; text: string; closed: boolean }` — new (discriminant `kind`)
- `frontend/src/app/thinking.ts` — `export function splitThinking(text: string): ThinkingSegment[]` — new; stub throws `Error("not implemented")`
- Caller-compile edits (out of Source-files scope): None. `npm run typecheck` is green.

### Step 004 — frozen interface (2026-10-04)
- `frontend/src/app/ThinkingBlock.tsx` — `export type ThinkingBlockProps = { text: string; startsOpen: boolean; unterminated?: boolean }` — new
- `frontend/src/app/ThinkingBlock.tsx` — `export function ThinkingBlock(props: ThinkingBlockProps): React.JSX.Element` — new; plain function (not an observer); stub throws `Error("not implemented")`
- `frontend/src/app/ToolBlock.tsx` — `export type ToolBlockStatus = "running" | "ok" | "failed"` — new
- `frontend/src/app/ToolBlock.tsx` — `export type ToolBlockProps = { name?: string | null; status: ToolBlockStatus; args: Record<string, unknown>; summary: string | null; startsOpen: boolean }` — new
- `frontend/src/app/ToolBlock.tsx` — `export function ToolBlock(props: ToolBlockProps): React.JSX.Element` — new; plain function; stub throws `Error("not implemented")`
- `frontend/src/app/AssistantBody.tsx` — `export type AssistantBodyProps = { text: string; live: boolean }` — new
- `frontend/src/app/AssistantBody.tsx` — `export function AssistantBody(props: AssistantBodyProps): React.JSX.Element` — new; plain function; stub throws `Error("not implemented")`
- Usage: `<ThinkingBlock text="plan" startsOpen={false} />`, `<ToolBlock name="memo_search" status="ok" args={{ query: "lighthouse" }} summary="Found 2 memos." startsOpen={false} />`, `<AssistantBody text="..." live={false} />`.
- What the coder still has to wire up: the module-level rotated-chevron icon components (two, open vs collapsed, typed `IconButtonProps["icon"]`, after `CharacterTree.tsx`'s `TreeChevronExpanded` / `TreeChevronCollapsed`), and the imports (`useState`, Mantine, `@tabler/icons-react`, `IconButton`, `MessageBody`, `splitThinking`). These were left out so the stubs carry no unused imports.
- Caller-compile edits (out of Source-files scope): None. `npm run typecheck` is green.

### Step 005 — frozen interface (2026-10-04)
- `frontend/src/app/streamState.ts` — `export type LiveToolStatus = "running" | "ok" | "failed"` — new (a separate type, not imported from `ToolBlock.tsx`, so the state module does not depend on a component; structurally identical to `ToolBlockStatus`)
- `frontend/src/app/streamState.ts` — `export type LiveToolCall = { callId: string; tool: string; args: Record<string, unknown>; status: LiveToolStatus; summary: string | null }` — new
- `frontend/src/app/streamState.ts` — `StreamState` — changed: adds `liveTools: LiveToolCall[] = []` (observable by default; the `makeAutoObservable` overrides stay `{ composeHandle: false }`)
- `frontend/src/app/streamState.ts` — `export function showsRegenerate(state: StreamState): boolean` — new; stub throws `Error("not implemented")`
- `frontend/src/app/streamState.ts` — `export async function regenerate(state: StreamState, signal?: AbortSignal): Promise<void>` — new; stub throws `Error("not implemented")` (so its promise rejects until filled)
- `frontend/src/app/streamState.ts` — `canSettle(state: StreamState): boolean`, `settleTargetText(state: StreamState): string | null`, `composeMessage(state: StreamState, signal?: AbortSignal): Promise<void>` — signatures unchanged. Their bodies were left as they are, so the existing tests do not throw.
- What the coder still has to do in these existing bodies:
  - `composeMessage`'s `onFrame` still ignores tool frames. It must apply D7's table to `liveTools`, and must not write after a mount abort.
  - The run must empty `liveTools` at start, in the same `runInAction` that sets `streamingText = ""`.
  - `liveTools` must also be emptied in both terminal clearing actions: the zone-write one and the fetch-failure one.
  - `canSettle` must count only non-tool zone rows. `settleTargetText` must take the last non-tool row.
  - Factoring the run into a private helper ("with text" or "textless") is the coder's choice.
- Caller-compile edits (out of Source-files scope): None. `npm run typecheck` is green.

### Step 006 — frozen interface (2026-10-04)
- `frontend/src/app/ZoneList.tsx` — `export type ZoneMessageProps = { state: StreamState; message: Message; signal?: AbortSignal; editable?: boolean }` — changed: `editable?: boolean` was added (its default is true). Before, the type had only `state`, `message` and `signal`.
- `frontend/src/app/ZoneList.tsx` — `export const ZoneMessage = observer(function ZoneMessage(props: ZoneMessageProps): React.JSX.Element)` — signature unchanged; body left intact
- `frontend/src/app/ZoneList.tsx` — `export type ZoneListProps = { state: StreamState; signal?: AbortSignal }` — unchanged
- `frontend/src/app/ZoneList.tsx` — `export const ZoneList = observer(function ZoneList(props: ZoneListProps): React.JSX.Element | null)` — signature unchanged; body left intact. A fragment fits the frozen return type, so the coder may return one.
- `frontend/src/app/LiveMessage.tsx` — `export type LiveMessageProps = { state: StreamState }` — new
- `frontend/src/app/LiveMessage.tsx` — `export const LiveMessage = observer(function LiveMessage(props: LiveMessageProps): React.JSX.Element | null)` — new; stub throws `Error("not implemented")`
- Usage: `<LiveMessage state={state} />`, `<ZoneMessage state={state} message={m} signal={signal} editable={false} />`.
- What the coder still has to do in `ZoneList.tsx`. Both bodies were left as they are, so the existing 013/019/021 tests do not throw.
  - `ZoneMessage`:
    - destructure `editable = true`;
    - render the "Edit message" `IconButton` iff `editable && message.role !== "tool"`;
    - choose the body by role. `user` gets `MessageBody` "painted". `assistant` gets `<AssistantBody text live={false} />`. `tool` gets `<ToolBlock name={tool_name} status={tool_status === "ok" ? "ok" : "failed"} args={tool_args ?? {}} summary={text} startsOpen={false} />`.
  - `ZoneList`:
    - return a fragment: the `ul` only when the zone is non-empty, then `<LiveMessage state={state} />`;
    - then, when `showsRegenerate(state)` is true, a subtle Mantine `Button` "Regenerate" with an `IconRefresh` left section at the inline size. Its `onClick` calls `void regenerate(state, signal)`.
  - Imports to add: `Button`, `IconRefresh`, `AssistantBody`, `ToolBlock`, `LiveMessage`, `showsRegenerate`, `regenerate`. They were left out so the stubs carry no unused imports.
- Caller-compile edits (out of Source-files scope): None. `npm run typecheck` is green.

### Step 007 — frozen interface (2026-10-04)
- `frontend/src/app/DiscussionGroup.tsx` — `export type DiscussionGroupProps = { entryId: string; state: StreamState }` — new
- `frontend/src/app/DiscussionGroup.tsx` — `export function DiscussionGroup(props: DiscussionGroupProps): React.JSX.Element` — new; plain function component (not an observer; its state is component-local `useState`); stub throws `Error("not implemented")`
- Usage: `<DiscussionGroup key={entry.id} entryId={entry.id} state={state} />`.
- `frontend/src/app/StreamRecord.tsx` — `StreamRecordProps`, `StreamRecord`, and the private `StreamEntry` / `StreamEntryProps` / `EntryBody` — signatures unchanged. The body was left intact so the existing 013/014 tests don't throw.
- What the coder still has to do:
  - `StreamRecord.tsx`: in `StreamEntry`, inside the `Stack` below the body/editor ternary, render `{entry.kind !== "partner" ? <DiscussionGroup key={entry.id} entryId={entry.id} state={state} /> : null}` and import `DiscussionGroup`. The kind label, actions group and re-open rule stay as they are.
  - `DiscussionGroup.tsx`: the body per the step's Interface intent. That means a rotated `IconChevronDown` chevron through `IconButton` (`sizeVariant "chevron"`, D14), `useState` for the open flag, status and rows, `fetchDiscussion(entryId, controller.signal)` with an unmount-aborted `AbortController`, a Mantine `Loader`, `ul[aria-label="Discussion messages"]` of `<ZoneMessage state={state} message={m} editable={false} />` rows, and the empty and failure lines. Imports were left out so the stub carries none unused.
- Caller-compile edits (out of Source-files scope): None. `npm run typecheck` is green.

## Tests

### Step 001 — tests (2026-10-04)
- `backend/tests/test_tool_wire_fields.py` — covers DoD-1, DoD-2, DoD-4, DoD-5, DoD-6 — `tool_view` over all twelve payload-table rows plus extra unreadable payloads (never raises, D3 rules), nested args, non-tool rows all-None; `list_zone` four-row zone tool view; `StreamMessage` new-field defaults; `GET …/entries` eleven keys with null tool fields on partner/turn/decision; zone failed tool row view and no internals; `PATCH` assistant row eleven keys/null tool fields; tool-row PATCH still 409 `message_not_editable`; `append_tool_message` ok/failed derived view, equal to the re-read.
- `backend/tests/test_tool_rows.py` — covers DoD-3 — amended in place: `test_the_zone_route_lists_a_tool_row_with_only_the_eight_keys__S021_001_DoD4__S022_001_DoD3` now asserts the four-row zone, exactly eleven keys, the ok row's `memo_search`/`ok`/`{"query":"lighthouse"}`, and no `tool_payload`/`call_id`/`call_1`/`Memo: the lighthouse keeper` in the body. Nothing else in the file changed (new module constants only).
- `backend/tests/test_stream_router.py` — covers DoD-4 (amendment clause) — `MESSAGE_KEYS` widened to the eleven keys (`_assert_message_shape` docstring updated, body unchanged); the eight tests calling `_assert_message_shape` chained `__S022_001_DoD4`: `test_append_answers_201_with_the_message__S012_004_DoD2`, `test_after_settle_the_zone_is_empty_and_the_entry_is_recorded__S012_004_DoD3`, `test_a_partner_block_is_filed_born_settled_and_verbatim__S012_004_DoD6`, `test_reopen_restores_the_group_in_its_original_order__S012_004_DoD10`, `test_patch_on_a_zone_message_answers_the_edited_message__S012_004_DoD13`, `test_patch_on_a_filed_partner_block_answers_the_edited_entry__S012_004_DoD13__S014_001_DoD10`, `test_patch_on_a_settled_decision_keeps_the_kind__S012_004_DoD13__S014_001_DoD10`, `test_patch_on_a_settled_turn_answers_200_with_the_edited_entry__S014_001_DoD9`. AST guards untouched.
- Approved deviations (2026-10-03 knock-on policy; outside Test files, key-set widening only, `__S022_001_DoD4` chained):
  - `backend/tests/test_stream_models.py` — `MESSAGE_WIRE_KEYS` widened to eleven; `NEVER_ON_THE_WIRE` is now `user_id`, `related_to`, `tool_payload`, `call_id` (`tool_name` is a wire key now); renamed `test_message_response_has_exactly_the_eight_wire_keys__S012_001_DoD8`, `test_entry_list_response_wraps_the_rows_under_entries_in_order__S012_001_DoD8`, `test_zone_response_wraps_the_rows_under_messages_in_order__S012_001_DoD8`.
  - `backend/tests/test_sessions_models.py` — `MESSAGE_WIRE_KEYS` widened to eleven and `EXPECTED_MESSAGE_WIRE` gains the three keys as null; renamed `test_started_response_with_a_message_serialises_the_eight_key_message__S018_001_DoD6`, `test_started_response_accepts_a_message_response__S018_001_DoD6`.
  - `backend/tests/test_sessions_router.py` — `MESSAGE_KEYS` widened to eleven; renamed `test_starting_with_an_opening_message_answers_the_started_session__S018_002_DoD6`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓

### Step 002 — tests (2026-10-04)
- `backend/tests/test_db_schema.py` — covers DoD-1 — new Feature 022/002 section: `buried_messages` is a module-level Core `Select` (not a `Table`), its name is not in `metadata.tables`, its result columns are exactly `MESSAGES_COLUMNS`; over one zone + one settled + two buried rows it returns exactly the two buried rows with text, `related_to` and NULL `settled_at` as stored; it carries no owner/session filter (another owner's buried row comes back too).
- `backend/tests/test_db_schema.py` — covers DoD-1 (amendment clause) — `SELECTABLE_NAMES` widened to include `buried_messages`; the three tests enumerating it chained `__S022_002_DoD1` (docstrings updated, bodies unchanged): `test_each_selectable_is_a_module_level_core_select__S012_001_DoD6`, `test_no_selectable_name_is_a_registry_table__S012_001_DoD6`, `test_create_all_creates_no_sql_view__S012_001_DoD6`.
- `backend/tests/test_discussion_read.py` — covers DoD-2, DoD-3, DoD-4, DoD-5, DoD-6, DoD-7, DoD-8 — `list_discussion` returns A's buried `[user, tool, assistant]` ascending by id (inserted out of order) with role/text as stored, `related_to` = entry checked on the seeded rows, tool row `memo_search`/`ok`/`{"query":"lighthouse"}`; `[]` for a settled partner and a lone settled turn; `MessageNotFoundError` for unknown id, B's entry as A, A's entry as B, zone row, buried row (no buried text in the error); another entry's buried rows excluded; GET as owner 200 `{"messages":[…]}` with eleven keys, string ids, id order, `related_to` checked on seeded rows, D3 tool fields and no tool internals; 404 `message_not_found` for unknown/foreign (both directions)/zone/buried ids; 200 `{"messages":[]}` for an owned partner block; 401 `not_authenticated` anonymous; GET and service read leave every row's `related_to`/`settled_at`/`text`/`updated_at` unchanged.
- Approved deviations: none (no assertion outside the Test files needed widening).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 [manual/live, no test]

### Step 003 — tests (2026-10-04)
- `frontend/tests/app/thinking.test.ts` — covers DoD-1, DoD-2, DoD-3 — `splitThinking` maps D4 rows 1–10 to exactly the listed segments (`kind`/`text`/`closed`), row 8's think text untrimmed, row 2 byte-for-byte; rows 3/4/6/8 answers joined with a space equal `Hello`/`One two`/``(none)/`((ooc))`, row 5 answers equal `Start`; uppercase `<THINK>loud</THINK>` is one unchanged answer segment.
- `frontend/tests/app/streamApiDiscussion.test.ts` — covers DoD-4, DoD-5, DoD-6 — `fetchDiscussion` issues exactly one `GET /api/messages/7250000000000000042/discussion`, unwraps `messages` in served (non-ascending) order, tool rows' `memo_search`/`ok`/`{"query":"lighthouse"}` and a failed `{}` row unchanged, `a/b` → `a%2Fb`, signal passed through; 404 `message_not_found` → `ApiError` of that code; mid-flight and pre-aborted signals reject with the unwrapped abort; type-level eight-key, eleven-key and null-tool `Message` literals plus a `@ts-expect-error` on `tool_status: "running"` (pinned by `npm run typecheck`).
- Approved deviations: none (no assertion outside the Test files needed widening; the tool fields are optional, so 013–021 fixtures still compile).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓

### Step 004 — tests (2026-10-04)
- `frontend/tests/app/ThinkingBlock.test.tsx` — covers DoD-1, DoD-2, DoD-3 — collapsed start: "Show thinking" + "Thinking", `plan` absent; toggling shows `plan` / "Hide thinking" and toggling back removes it; open start shows text + "Hide thinking"; `**bold** ((x))` appears literally with no `strong` and no `[data-paren]`.
- `frontend/tests/app/ToolBlock.test.tsx` — covers DoD-4, DoD-5, DoD-6 — collapsed `memo_search`/"Done"/"Show tool call" with neither `"query": "lighthouse"` nor `Found 2 memos.` in the document, then opened shows "Arguments", `JSON.stringify(args, null, 2)` and the summary; open running block shows "Running", args, "Hide tool call", and a rerender to `ok` + summary stays open with "Done" and the summary; failed/null-name/`{}` block shows "Failed", "Unknown tool", "No arguments.", `The tool failed.` (also for an absent name).
- `frontend/tests/app/AssistantBody.test.tsx` — covers DoD-7, DoD-8, DoD-9, DoD-10 — D4 row 3 not live (Hello, "Show thinking", `plan` absent) and live (`plan`, Hello, "Hide thinking"); row 4 two "Show thinking" toggles interleaved toggle/`One`/toggle/`two` in document order; row 8 one `[data-paren="ooc"]` card with "Out of character" holding `((ooc))`; rows 1 and 7 draw no thinking toggle and their text content equals `MessageBody` painted's for the same text.
- Approved deviations: none (no assertion outside the Test files needed widening).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 [manual/live, no test]

### Step 005 — tests (2026-10-04)
- `frontend/tests/app/streamLiveTools.test.ts` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5 — fresh `liveTools` is `[]`; during `composeMessage("Find it")` a held-open `tool_start` c1 gives exactly `[{callId:"c1", tool:"memo_search", args:{query:"lighthouse"}, status:"running", summary:null}]` and `zone` only ever holds served rows; `tool_result` → c1 `ok`/`Found 2 memos.`, c2 `tool_fail` → `failed`/`The tool failed.`, order `[c1, c2]`, unknown c9 result/fail changes nothing; on `done` an autorun never sees (zone has tool row, live list non-empty) or (streaming text null, live list non-empty), every state holding the final served list has an empty live list and null text, no notification; user stop empties the list with the streaming text, no notification; after a mount abort the list is never written (stays `[c1 running]`).
- `frontend/tests/app/streamRegenerate.test.ts` — covers DoD-6, DoD-7, DoD-8, DoD-9, DoD-10, DoD-11, DoD-12, DoD-13 — `showsRegenerate` true for `[user]`, `[user, assistant]`, `[user, tool, assistant]`, false for empty, `[tool]`, streaming `""`, busy; `regenerate` POSTs once with body `{}`, streams tokens, re-reads on `done`, draft `"half typed"` throughout, no `/zone/messages`; an `accepted` only re-reads (draft, `entries`, `busy`, `kindOverride` untouched); `error llm_unreachable` and 409 `zone_empty` notify once with the code, re-read, keep draft/entries, clear streaming text, `showsRegenerate` true again; no request for empty / tool-only / busy / streaming / already-in-flight; `stopCompose` aborts, no notification, re-read; `settleComposer` mid-regenerate gives `[GET zone, POST settle, {GET entries, GET zone}]`; `canSettle` `[user]`/`[user, tool]` true, `[tool]` false, `[tool]`+`"x"` true; settle target `Theirs` → "Settles as a turn.", `((ooc))` → "Settles as a decision (out of character)." (via `settlePreviewOf` mapped to 013's strings), tool-only = empty-zone "nothing to settle"; `composeMessage` still sends `{"text": draft}` and ends with an empty live list.
- `frontend/tests/app/streamState.test.ts` — not touched: no 013 assertion seeds a `role: "tool"` row (amendment rule in `005.context.md` does not trigger). DoD-13 is otherwise the unchanged 013/019/021 suites (`streamState`, `streamCompose`, `streamStreaming`, `composeSend`).
- Approved deviations: none.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓

### Step 006 — tests (2026-10-04)
- `frontend/tests/app/ZoneListAssistant.test.tsx` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-9, DoD-10 — zone `[user "Hi", assistant "<think>plan</think>\n\nHello there", tool "Found 2 memos." memo_search/ok/{query:lighthouse}]`: three items You/Assistant/Tool in order, assistant `Hello there` + "Show thinking", no `plan`; tool `memo_search`/"Done"/"Show tool call", no arguments; "Edit message" once on user and assistant, absent on tool; Show thinking reveals `plan`, Show tool call reveals `"query": "lighthouse"` + `Found 2 memos.`; the assistant editor holds exactly the raw think-tagged text, `Hello, friend` + blur sends only `PATCH /api/messages/<id>` `{"text":"Hello, friend"}` and the item shows the served text; `ZoneMessage editable={false}` for all three rows shows no "Edit message"/editor with DoD-1's bodies; live → persisted in one action removes the "Live reply" region, assistant `Here it is` with "Show thinking" and no `look up`, tool item collapsed; "Regenerate" follows the zone list (not inside it) when eligible, absent for empty / `[tool]` / streaming `""` / busy; pressing it issues one `POST …/zone/compose` with body `{}` (no `/zone/messages`), and after the mount signal aborts a further token is not written.
- `frontend/tests/app/LiveMessage.test.tsx` — covers DoD-6, DoD-7, DoD-8 — while streaming (`[user "Find it"]`, `<think>look up</think>Here it`, `[c1 memo_search running {query:lighthouse}]`) the "Live reply" region follows the "Zone messages" list (sibling; the list keeps one item), its text orders Assistant < memo_search < arguments < `look up` < `Here it`, with "Running", "Hide tool call", "Hide thinking", no `<think>`, and no "Edit message"/textbox; an appended token shows `Here it is` with the same "Hide thinking" element; c1 → ok + `Found 2 memos.` shows "Done" and the summary with the same "Hide tool call" element and the args still shown; empty zone + `""` renders the region with "Assistant" and no list; `null` renders no region (also `LiveMessage` alone renders no element).
- `frontend/tests/app/ZoneList.test.tsx` (013 `005`, in Test files) — covers DoD-2 (amendment clause) — DoD-1 test retitled `… — DoD-1 — DoD-2 (022 006)`: "Edit message" asserted on user and assistant items only, absent on the tool item.
- Approved deviations (knock-ons inside the same file, necessarily broken by DoD-1/D5's collapsed tool block, whose summary is not rendered): the eight-key tool fixture's summary `lookup` is no longer asserted as item text — dropped in the DoD-1 test; replaced by the "Tool" label in `… — DoD-6 — DoD-1 (022 006)` (013 DoD-6 test); dropped in `… — DoD-7 — DoD-1 (022 006)` (013 DoD-7 test; its `state.zone[2].text === "lookup"` check is kept). No other assertion changed; no file outside the Test files touched.
- DoD-11 is the unchanged 013 / 019 / 021 component suites (`ZoneList` apart from the above, `SessionStream`, `ComposerStop`, `Composer`, `StreamRecord*`).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓ (existing suites), DoD-12 [manual/live, no test], DoD-13 [manual/live, no test]

### Step 007 — tests (2026-10-04)
- `frontend/tests/app/StreamRecordDiscussion.test.tsx` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-8, DoD-9 — record `[partner "They wave.", turn "I wave back.", decision "((skip))"]`: turn and decision each carry one "Show discussion", the text "Discussion" and "Read-only", the partner none, no `/discussion` request, no "Discussion messages" list; expanding the turn issues exactly one `GET /api/messages/<turn id>/discussion`, three items You/Tool/Assistant in order (`Write me a reply`, `memo_search`, `I wave back.`), "Discussion (3)", "Hide discussion", decision group untouched; no "Edit message"/textbox in the list, "Show thinking" with `plan` absent, "Show tool call" with `"query": "lighthouse"` absent, then both revealed; hide removes the list, re-show shows the same three items with no second GET; `settleComposer` over `StreamRecord` + `ZoneList` sharing a *my turn* state removes "Zone messages", the new "My turn" entry shows `Final` with a collapsed header, no `Draft` in the document, expanding GETs the new entry's discussion and shows `Draft` (You) read-only; Re-open on the last non-partner entry (turn, decision) with an empty zone, absent with zone rows, headers still present. Record items are counted as direct children of "Settled record".
- `frontend/tests/app/DiscussionGroup.test.tsx` — covers DoD-5, DoD-6, DoD-7 — `{"messages":[]}` shows "No discussion behind this entry." and "Discussion (0)", no list; 404 `message_not_found` shows "The discussion could not be loaded.", no list, no `notifyFailure`, header exactly "Discussion"; collapse + expand issues a second GET whose rows show with "Discussion (2)"; unmount while the GET is pending aborts its signal with no `console.error` / `notifyFailure`, and a late answer after unmount writes nothing.
- `frontend/tests/app/StreamRecord.test.tsx` — not touched: no assertion counts all buttons in an entry or matches text that "Discussion" / "Read-only" would also match, and collapsed groups add no `listitem`s (amendment rule in `007.context.md` does not trigger).
- Approved deviations: none (no assertion outside the Test files was found to break; collapsed groups make no request and add only uniquely named controls/texts).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓ (plus the unchanged 013/014 `StreamRecord*` suites), DoD-10 [manual/live, no test]

## Notes & Issues

_populated by the coder when worth saying_

## Ultra phase

- orient: done 2026-10-04
- policy 2026-10-03 (user): mechanical knock-on test amendments outside a step's Test files are approved deviations, recorded under that step's ## Tests.
- harvest: done — docs/.cache/ultra/022.discussion-ui/harvest.md (1 report)
- skeleton: done — steps 001–007
- tests: done — steps 001–007
- red-gate: PASS (run 1)
- code: done — steps 001–007
- verify: PASS (run 1)
