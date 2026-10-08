# Feature 019 — streaming-transport-and-stop

| Step | File                                   | Status  | Verifier | Date |
|------|----------------------------------------|---------|----------|------|
| 001  | `001.frames-and-assistant-append.md` | done    | PASS     | 2026-10-04 |
| 002  | `002.sse-harness.md` | done    | PASS     | 2026-10-04 |
| 003  | `003.sse-consumer.md` | done    | PASS     | 2026-10-04 |
| 004  | `004.streaming-state-and-stop-slot.md` | done    | PASS     | 2026-10-04 |
| 005  | `005.compose-effect.md` | done    | PASS     | 2026-10-04 |

## Files Changed

### Step 001 — Frame value types, the encoder, and the shared assistant append
- `backend/app/services/llm/frames.py` — filled `encode_frame` (event-first compact JSON, `ensure_ascii=False`, `message_id` as `str`) and `error_frame` (inner `code`/`message`/`detail`); added `import json`
- `backend/app/services/messages.py` — filled `append_assistant_message` (one transaction: session check, insert `role='assistant'` with kind/related_to/settled_at unset, session bump); `append_message` and `insert_zone_message` untouched
- `backend/app/models/stream.py` — not touched: `MessageResponse.role` is already `str`

### Step 002 — The SSE harness and the own-connection persister
- `backend/app/services/llm/frames.py` — filled `frame_stream` (poll before each write, token accumulation, D4/D5 endings with persist-before-error, at-most-once persist flag, `finally` persist + shielded/suppressed `aclose()`), `sse_response` (`text/event-stream`, `X-Accel-Buffering: no`) and `own_connection_persister` (own `engine.connect()`, `append_assistant_message`, log session id + exception class, swallow); added imports `asyncio`, `contextlib`, `loguru.logger`, `append_assistant_message` and the two D5 message constants

### Step 003 — The SSE consumer and the shared failure decode
- `frontend/src/shared/api.ts` — filled `decodeErrorResponse` (401 navigation, body read with failure as empty, envelope or `client_malformed_error`) and `mapFetchRejection`; `apiRequest` now throws `mapFetchRejection` on fetch rejection and, for non-2xx, keeps its own body read (raw rethrow on an aborted read, before any navigation) then hands an equivalent buffered `Response` to `decodeErrorResponse`
- `frontend/src/shared/sse.ts` — filled `postSse` (JSON POST, `getReader()` + streaming `TextDecoder`, `\n\n` framing, `data:` join, terminal/malformed frames cancel the reader and resolve, unknown events skipped, four outcomes, never rejects for a valid `/api/` path); added private helpers and imports from `./api` / `./apiError`

### Step 004 — Streaming state, the stop action, and Stop in Send's slot
- `frontend/src/app/streamApi.ts` — filled `composeZone` (`postSse(sessionPath(id, "/zone/compose"), { text }, onFrame, signal)`, outcome unchanged); added `postSse` import
- `frontend/src/app/streamState.ts` — filled `isStreaming` (`streamingText !== null`) and `stopCompose` (aborts the handle's controller if any, writes nothing); `canSend` and `showsDiscard` gain `&& !isStreaming(state)`; `canSettle` untouched
- `frontend/src/app/Composer.tsx` — while streaming passes `sendSlot` = Stop `IconButton` (`IconPlayerStop`, "Stop", `sizeVariant="main"`, calls `stopCompose`) and `sendBlockedReason` null; otherwise unchanged
- `frontend/src/app/ComposerCore.tsx` — (user-approved deviation, `## Ultra phase`) renders `sendSlot` in place of the "Send" button when not `undefined`; default unchanged

### Step 005 — The compose effect and Settle-mid-stream
- `frontend/src/app/streamState.ts` — filled `composeMessage` (no-op when mount-aborted, streaming or blank; own controller linked to the mount signal and unlinked at the end; `accepted` clears an unchanged draft and starts a `rereadZone` on the mount signal; tokens append to `streamingText`; tool frames ignored; after the outcome awaits the accepted re-read, notifies per D14, then one `fetchZone` whose result is written with `streamingText`/`composeHandle` cleared in the same action, cleared anyway on failure; wound-down promise always resolves in `finally`); `settleComposer` gains the D16 prefix before `draft` is read (busy, `stopCompose`, await `woundDown`, return if mount-aborted); added imports `ApiError`, `composeZone`, `SseOutcome`/`SseProgressFrame` types

## Skeleton

### Step 001 — frozen interface (2026-10-03)
- `backend/app/services/llm/frames.py` — new module; imports `Mapping` (collections.abc), `dataclass`, `field`, `Any`, `DomainError` (app.errors).
  - `@dataclass(frozen=True) class AcceptedFrame: message_id: int` — new
  - `@dataclass(frozen=True) class TokenFrame: text: str` — new
  - `@dataclass(frozen=True) class ToolStartFrame: tool: str; call_id: str; args: Mapping[str, Any]` — new
  - `@dataclass(frozen=True) class ToolResultFrame: tool: str; call_id: str; summary: str` — new
  - `@dataclass(frozen=True) class ToolFailFrame: tool: str; call_id: str; code: str` — new
  - `@dataclass(frozen=True) class ErrorFrame: code: str; message: str | None; detail: Mapping[str, Any] = field(default_factory=dict)` — new
  - `@dataclass(frozen=True) class DoneFrame: message_id: int` — new
  - `Frame = AcceptedFrame | TokenFrame | ToolStartFrame | ToolResultFrame | ToolFailFrame | ErrorFrame | DoneFrame` (plain module-level union alias; usable with `isinstance`) — new
  - `def encode_frame(frame: Frame) -> str` — new (stub raises `NotImplementedError`)
  - `def error_frame(error: DomainError) -> ErrorFrame` — new (stub raises `NotImplementedError`)
- `backend/app/services/messages.py` — `def append_assistant_message(connection: Connection, generator: SnowflakeGenerator, user_id: int, session_id: int, text: str) -> StreamMessage` — new (stub raises `NotImplementedError`; placed after `append_message`). `append_message`, `insert_zone_message` and every other symbol unchanged. No new imports; AST guards (no select on messages, no delete, no fastapi/app.services imports, no related_to) hold.
- `backend/app/models/stream.py` — not touched: `MessageResponse.role` is already `str`, so `"assistant"` serialises as-is.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `mypy app` clean (61 files), `ruff check .` clean, full `pytest` 3137 passed.

### Step 002 — frozen interface (2026-10-04)
- `backend/app/services/llm/frames.py` — added imports `AsyncGenerator`, `AsyncIterator`, `Callable` (collections.abc), `Protocol` (typing), `StreamingResponse` (fastapi.responses), `Engine` (sqlalchemy), `SnowflakeGenerator` (app.ids). Step 001 symbols unchanged.
  - `class DisconnectProbe(Protocol): async def is_disconnected(self) -> bool: ...` — new (the D3 "request" type; a Starlette `Request` satisfies it structurally; any test fake with that async method does too)
  - `async def frame_stream(request: DisconnectProbe, source: AsyncIterator[Frame], on_partial: Callable[[str], None]) -> AsyncGenerator[str, None]` — new; a real async generator (so `__anext__`/`aclose()` are available on the result). Stub raises `NotImplementedError` on first `__anext__`.
  - `def sse_response(request: DisconnectProbe, source: AsyncIterator[Frame], on_partial: Callable[[str], None]) -> StreamingResponse` — new (stub raises `NotImplementedError`)
  - `def own_connection_persister(engine: Engine, generator: SnowflakeGenerator, user_id: int, session_id: int) -> Callable[[str], None]` — new (stub raises `NotImplementedError`)
  - Coder will need to add `asyncio`, `contextlib` (if used), `from loguru import logger` and `from app.services.messages import append_assistant_message`; not imported in the stub to keep ruff F401 clean.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `mypy app` clean (61 files), `ruff check .` clean, full `pytest` 3137 passed.

### Step 003 — frozen interface (2026-10-04)
- `frontend/src/shared/api.ts` — `export async function decodeErrorResponse(response: Response): Promise<ApiError>` — new (D10 non-2xx decode; 401 navigates via `documentNavigation.assign("/login")`; stub throws)
- `frontend/src/shared/api.ts` — `export function mapFetchRejection(error: unknown, signal?: AbortSignal): unknown` — new (D10 rejection mapping; returns `error` unchanged when `signal?.aborted`, else the `client_transport_failed` `ApiError`; stub throws)
- `frontend/src/shared/api.ts` — `apiRequest`, `apiGet/Post/Patch/Put/Delete`, `documentNavigation`, `HttpMethod` — unchanged in signature and, in the stub, in body (the coder rewires `apiRequest` onto the two helpers; observable behaviour must not change). Private `decodeEnvelope`/`malformed` stay private.
- `frontend/src/shared/sse.ts` — new module, imports `ApiError` from `./apiError`:
  - `export type SseFrame = { event: "accepted"; message_id: string } | { event: "token"; text: string } | { event: "tool_start"; tool: string; call_id: string; args: Record<string, unknown> } | { event: "tool_result"; tool: string; call_id: string; summary: string } | { event: "tool_fail"; tool: string; call_id: string; code: string } | { event: "error"; code: string; message: string | null; detail?: Record<string, unknown> } | { event: "done"; message_id: string }` — new
  - `export type SseProgressFrame = Exclude<SseFrame, { event: "error" } | { event: "done" }>` — new (what the callback receives)
  - `export type SseOutcome = { kind: "done"; messageId: string } | { kind: "error"; error: ApiError } | { kind: "stopped" } | { kind: "unexpected_end" }` — new
  - `export async function postSse(path: string, body: unknown, onFrame: (frame: SseProgressFrame) => void, signal: AbortSignal): Promise<SseOutcome>` — new (stub throws)
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean.

### Step 004 — frozen interface (2026-10-04)
- `frontend/src/app/streamApi.ts` — `export async function composeZone(sessionId: string, text: string, onFrame: (frame: SseProgressFrame) => void, signal: AbortSignal): Promise<SseOutcome>` — new (stub throws; adds `import type { SseOutcome, SseProgressFrame } from "../shared/sse"`). Coder: `postSse(sessionPath(sessionId, "/zone/compose"), { text }, onFrame, signal)`, outcome returned unchanged.
- `frontend/src/app/streamState.ts` — `export type ComposeHandle = { controller: AbortController; woundDown: Promise<void> }` — new
- `frontend/src/app/streamState.ts` — `StreamState.streamingText: string | null = null` (observable) — new field
- `frontend/src/app/streamState.ts` — `StreamState.composeHandle: ComposeHandle | null = null` (not observable: `makeAutoObservable(this, { composeHandle: false }, { autoBind: true })`) — new field; constructor overrides changed (was `{}`)
- `frontend/src/app/streamState.ts` — `export function isStreaming(state: StreamState): boolean` — new (stub throws)
- `frontend/src/app/streamState.ts` — `export function stopCompose(state: StreamState): void` — new sync action (stub throws)
- `frontend/src/app/streamState.ts` — `canSend(state: StreamState): boolean`, `showsDiscard(state: StreamState): boolean` — signatures unchanged; bodies left as-is in the stub. Coder adds `&& !isStreaming(state)` to each. `canSettle` stays untouched.
- `frontend/src/app/ComposerCore.tsx` (user-approved deviation, `## Ultra phase`) — `ComposerCoreProps.sendSlot?: React.ReactNode` — new optional prop. Contract: when not `undefined`, it is rendered in place of the "Send" `Button` (Send absent; `sendEnabled`/`onSend` not consulted); the send-blocked reason text still follows `sendBlockedReason`; when `undefined` (default) everything renders exactly as 018. Stub declares the prop only; coder renders it.
- `frontend/src/app/Composer.tsx` — `ComposerProps` unchanged (`{ state; signal?; sendBlockedReason? }`). Coder: when `isStreaming(state)`, pass `sendSlot={<IconButton icon={IconPlayerStop} label="Stop" sizeVariant="main" onClick={() => { stopCompose(state); }} />}` and `sendBlockedReason={null}` (017's reason gates Send only, never Stop); otherwise pass no `sendSlot` and the existing props. Settle/Discard in `besideSend` unchanged. Not wired in the stub so existing Composer tests keep passing.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean; `vitest run tests/app` 65 files / 1894 tests passed (no existing test affected).

### Step 005 — frozen interface (2026-10-04)
- `frontend/src/app/streamState.ts` — `export async function composeMessage(state: StreamState, signal?: AbortSignal): Promise<void>` — new effect (`signal` is the mount signal; stub rejects with `Error("not implemented: composeMessage")`; placed after `settleComposer`). Coder adds imports `composeZone` (from `./streamApi`), `ApiError` (from `../shared/apiError`) and, if used, `import type { SseProgressFrame } from "../shared/sse"`; not imported in the stub so the stub stays minimal. Re-reads use the existing private `rereadZone(state, signal)` with the **mount** signal; draft clearing reuses `clearDraftIfUnchanged`.
- `frontend/src/app/streamState.ts` — `export async function settleComposer(state: StreamState, signal?: AbortSignal): Promise<void>` — signature unchanged; body left byte-for-byte as before in the stub (013 settle tests unaffected). Coder inserts the D16 prefix after the initial `signal?.aborted` guard and before the existing flow: if `state.composeHandle !== null` → `setBusy(state, true)`, `stopCompose(state)`, `await handle.woundDown`, return if `signal?.aborted`; then the existing flow unchanged (its own `setBusy(state, true)` re-set is harmless). Note: `text = state.draft` must be read **after** the wait (or the prefix placed before that line), since the compose's `accepted` may have cleared the draft.
- `isStreaming`, `stopCompose`, `ComposeHandle`, `streamingText`, `composeHandle` — unchanged from Step 004's freeze.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean.

## Tests

### Step 001 — tests (2026-10-04)
- `backend/tests/test_llm_frames.py` — covers DoD-1, DoD-2, DoD-3, DoD-4 — exact wire bytes for accepted/done (ids as JSON strings), token (parsed form, Cyrillic unescaped, single terminator, no blank line inside), the three tool frames, and `error_frame` from `LlmUnreachableError` (inner fields, no wrapper, `null`/`{}` defaults).
- `backend/tests/test_assistant_append.py` — covers DoD-5, DoD-6, DoD-7, DoD-8 — assistant row value + `current_zone`/`list_zone` read-back; `SessionNotFoundError` with no write for foreign/unknown session; `GET /api/sessions/{id}/zone` lists user then assistant row with string ids; `append_message` still writes role `user`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓ (existing `append_message` tests untouched).
- Pre-existing tests amended: none.

### Step 002 — tests (2026-10-04)
- `backend/tests/test_llm_sse_harness.py` — covers DoD-1, DoD-2 — throwaway `FastAPI()` POST route over `sse_response`: 200, `text/event-stream`, `x-accel-buffering: no`, body exactly accepted+token+token+done wire bytes; `on_partial` never called (via TestClient and via `frame_stream` directly).
- same file — covers DoD-3, DoD-4, DoD-5, DoD-6 — `DomainError` -> two tokens + one `llm_unreachable`/"down" frame, persist logged before the error frame; `RuntimeError` -> fixed "The reply could not be completed." with `{}` and no leaked text; exhaustion -> fixed "The reply ended before it was complete."; source `error` passed verbatim as last frame, source never pulled again; nothing after `done`, no persist.
- same file — covers DoD-7, DoD-8, DoD-9, DoD-10 — disconnect by poll / by `aclose()` / by task cancel (all bounded by `asyncio.wait_for`/`asyncio.wait`): no further and no terminal frame, `on_partial` once with joined text, source `finally` ran, cancel stays cancelled; parametrized no-token and whitespace-only cases persist nothing on each path.
- same file — covers DoD-11, DoD-12 — `own_connection_persister` writes one `assistant`/kind NULL current-zone row; a missing session returns normally with no write; poll-disconnect stream wired to the persister leaves exactly one new assistant row "Half a reply".
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 [manual/live, no test]
- Pre-existing tests amended: none.

### Step 003 — tests (2026-10-04)
- `frontend/tests/shared/sse.test.ts` — covers DoD-1 — `postSse` fetch call: exact path, POST, JSON content type, `JSON.stringify(body)`, `credentials: "same-origin"`, the given signal.
- same file — covers DoD-2, DoD-3 — accepted/token/token/done gives the three progress frames in order (ids exact strings, `done` never delivered) and `{kind:"done", messageId}`; identical result for a split inside `data:`, between the two `\n`, one chunk, one byte per chunk; `"Привет 🙂"` intact when split inside multi-byte chars; jsdom TextEncoder/TextDecoder sanity check.
- same file — covers DoD-4, DoD-5, DoD-6 — `error` frame resolves to an `ApiError` (code/message/detail, status 200; non-string message -> `""`, absent detail -> `{}`); body end without terminal -> `{kind:"unexpected_end"}`, nothing notified; abort mid-body, abort before fetch resolves, and pre-aborted signal -> `{kind:"stopped"}`.
- same file — covers DoD-7, DoD-8, DoD-9 — 409 envelope / 502 HTML -> error with envelope fields / `client_malformed_error`, callback never called; 401 -> `documentNavigation.assign("/login")` once + envelope code; rejected fetch and rejected body read -> `client_transport_failed`, status 0.
- same file — covers DoD-10, DoD-11 — bad-JSON and missing/non-string `event` frames -> `client_malformed_error` (later `done` ignored); unknown `thinking` skipped; `: keepalive` ignored; nothing delivered after `done` (also with the body still open).
- same file — covers DoD-12 — `apiGet` for 401/409/malformed 500/transport/abort keeps its rejections; direct checks of `decodeErrorResponse` (401 navigation, malformed fallback) and `mapFetchRejection` (abort unchanged, else transport error with the fixed message, status 0).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓
- Pre-existing tests amended: none.

### Step 004 — tests (2026-10-04)
- `frontend/tests/app/streamStreaming.test.ts` — covers DoD-1 — `composeZone`: one POST to exactly `/api/sessions/7250000000000000042/zone/compose`, body exactly `{"text":"Hi ((short))"}`, the given signal; resolves to `{kind:"done", messageId:"7250000000000000099"}` with the accepted frame passed to the callback; `a/b` id -> `a%2Fb` in the path.
- same file — covers DoD-2 — fresh state: `streamingText` null, `composeHandle` null, `isStreaming` false; `""` -> true, back to null -> false; `streamingText` observable, `composeHandle` not; `isStreaming` reactive via autorun.
- same file — covers DoD-3, DoD-4, DoD-5 — `canSend` true/false off/while streaming (draft "Hello", busy false); `canSettle` true both ways with one my-turn zone row, false both ways on empty zone + blank draft; `showsDiscard` true/false off/while streaming.
- same file — covers DoD-6 — `stopCompose` aborts the fresh controller; streaming text, zone, entries, draft, busy (and the handle itself) unchanged, no fetch, no `notifyFailure`; busy true stays true; no handle -> no throw, nothing changes.
- `frontend/tests/app/ComposerStop.test.tsx` (new) — covers DoD-7, DoD-8, DoD-9 — while streaming "Stop" present and no "Send" (absent, not disabled), "Stop" between the textbox and "Settle", Send->Stop on streaming start; pressing "Stop" aborts the handle's controller with no request/notification; my turn + one zone row -> "Settle" enabled while streaming; not streaming -> "Send" present, no "Stop", and Send returns when streaming text goes null.
- `frontend/tests/app/ComposerCore.test.tsx` (user-approved deviation, `## Ultra phase`) — new describe "019 step 004" — covers DoD-7, DoD-9 — a given `sendSlot` renders in Send's place (after under-area, before beside-Send), "Send" absent whatever `sendEnabled`, `onSend` not called, send-blocked reason still shown; omitted/`undefined` `sendSlot` keeps 018's labelled Send.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 [manual/live, no test]
- Pre-existing tests amended: `ComposerCore.test.tsx` gained one additive describe block and a header note (the approved deviation); no existing assertion changed. `Composer.test.tsx` untouched.

### Step 005 — tests (2026-10-04)
- `frontend/tests/app/streamCompose.test.ts` (new) — covers DoD-1 — one POST to exactly `/api/sessions/s1/zone/compose` with body exactly `{"text":"Write me a reply"}`; `isStreaming` true while the body is held open; `busy` false at every observed value.
- same file — covers DoD-2, DoD-3 — after `accepted` the draft is `""` and one zone GET issued; tokens `"Once "`+`"upon"` give streaming text exactly `"Once upon"`; every observed `zone` holds only served/seeded ids (no placeholder) and no `/api/messages/...` request; a draft retyped to `"Write me a reply!"` before `accepted` is kept.
- same file — covers DoD-4 — with the accepted zone GET gated, `done` issues no second zone GET until it resolves; then last request is a zone GET, `zone` equals the final list (with the assistant row), streaming text null, `isStreaming` false, no notification.
- same file — covers DoD-5, DoD-6 — `error` frame `llm_unreachable`: notified once with that code, zone re-read, `entries` identity/content unchanged and never fetched, streaming null; 409 `model_not_enabled` compose: notified with that code, draft kept, zone re-read; terminal-less end: `llm_unreachable` notified before the zone GET, then re-read, streaming null.
- same file — covers DoD-7, DoD-8 — user stop after one token: no notification, zone becomes the served list with the partial assistant row, streaming text and handle null, busy never true, `canSend` true and a second compose POSTs `{"text":"Another line"}`; mount abort: compose request signal aborted, no further request, no notification, no write to `zone`/streaming text (reaction count 0, late accepted GET discarded); pre-aborted mount signal -> no request.
- same file — covers DoD-9 — empty / whitespace draft, a manually set streaming state, and a second call during a real compose all make no request.
- same file — covers DoD-10 — settle mid-stream: `canSettle` true while streaming; the handle's controller aborted; no notification; requests after the settle call are post-stop zone GET, then `POST /settle`, then entries + zone GETs (no zone/messages); ends streaming null, busy false, lists equal the settle's re-reads.
- same file — covers DoD-11 — no compose in flight: exactly 4 requests (zone/messages, settle, both GETs) with draft, exactly 3 (settle, both GETs) with a blank draft; handle stays null. 013's `streamMutations.test.ts` settle tests left unchanged.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 [manual/live, no test]
- Pre-existing tests amended: none.

## Notes & Issues

_populated by the coder when worth saying_

## Ultra phase

- orient: done 2026-10-03
- policy 2026-10-03 (user): mechanical knock-on test amendments outside a step's Test files are approved deviations, recorded under that step's ## Tests.
- deviation 2026-10-03 (user-approved): 019 was planned before 018 moved Send into ComposerCore.tsx. Step 004 may also edit frontend/src/app/ComposerCore.tsx (one optional prop that replaces the Send button; defaults keep 018 behaviour) and frontend/tests/app/ComposerCore.test.tsx. 017's sendBlockedReason gates Send only, never Stop.
- harvest: done — docs/.cache/ultra/019.streaming-transport-and-stop/harvest.md (1 report)
- skeleton: done — steps 001–005
- tests: done — steps 001–005   (003 re-dispatched after a user interrupt; first attempt left nothing)
- red-gate: PASS (run 2; run 1 FAIL — 003 DoD-3 cross-realm instanceof, fixed)
- note 2026-10-04: step 002 coder saw the `## Tests` inventory (titles only, no test source) via a whole-file read; it reported not using it.
- code: done — steps 001–005
- verify: PASS (run 1)
