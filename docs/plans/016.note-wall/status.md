# Feature 016 — note-wall

| Step | File                                    | Status  | Verifier | Date |
|------|-----------------------------------------|---------|----------|------|
| 001  | `001.reorder-backend.md` | done    | PASS     | 2026-10-03 |
| 002  | `002.reorder-state.md` | done    | PASS     | 2026-10-03 |
| 003  | `003.sortable-level-group.md` | done    | PASS     | 2026-10-03 |
| 004  | `004.drop-handler-and-chain-dnd.md` | done    | PASS     | 2026-10-03 |
| 005  | `005.note-wall-layout.md` | done    | PASS     | 2026-10-03 |
| 006  | `006.session-screen-wall.md` | done    | PASS     | 2026-10-03 |

## Files Changed

_populated by the coder as steps complete_

### Step 001 — Backend: new-note-first allocation and the level reorder route
- `backend/app/errors.py` — `MemoOrderMismatchError` default message, delegates to `DomainError`
- `backend/app/models/memos.py` — `ReorderMemosRequest` non-user-scope-needs-`scope_id` validator
- `backend/app/services/memos.py` — `create_memo` allocation `COALESCE(MIN(sort_key), 1) - 1`; `reorder_memos` (target check, owner-scoped set read, set/duplicate check, `sort_key`-only owner-scoped updates, ordered re-read, one transaction)
- `backend/app/routers/memos.py` — `PUT /api/memos/order` handler body (`scope_id` `None` for `"user"`, calls `reorder_memos`, answers `MemoListResponse`)

### Step 002 — The reorder call and the level state's optimistic reorder
- `frontend/src/shared/api.ts` — `apiPut` routed through `apiRequest(path, "PUT", body, signal)`
- `frontend/src/app/memosApi.ts` — `reorderMemos` PUTs `/api/memos/order` with `{ scope, scope_id, memo_ids }`, unwraps `memos`, no signal
- `frontend/src/app/memoLevelState.ts` — `isReorderInFlight` / `reorderFailure` derivations; `reorderMemoLevel` (in-flight / same-order guard, optimistic write, success merge by `updated_at`, revert to pre-drop relative order with "Could not reorder the notes.") via private pure helpers; `saveNewNote` prepends the created row (D5)

### Step 003 — The level group: new note on top with focus, and opt-in sortable cards
- `frontend/package.json` / `frontend/package-lock.json` — `@dnd-kit/core` ^6.3.1, `@dnd-kit/sortable` ^10.0.0, `@dnd-kit/utilities` ^3.2.2 (installed by the skeleton; unchanged by the coder)
- `frontend/src/shared/MarkdownEditor.tsx` — `autoFocus` carried as TipTap's `autofocus` option (`"end"` when true, `false` otherwise)
- `frontend/src/app/MemoLevelGroup.tsx` — card contents extracted to a private `NoteCardBody` shared by both shells; plain `li` shell when not `reorderable`; private `SortableNoteCard` (`useSortable` with role `listitem`, `aria-label` "Note n of total", keydown forwarded only when target is the `li`, disabled while its editor area has focus or `isReorderInFlight`, inline transform/transition) inside a per-level `SortableContext` when `reorderable`; new note listitem first with `autoFocus`; `reorderFailure(state)` text under the heading, outside the list

### Step 004 — The drop decision and the chain's drag context
- `frontend/src/app/memoReorder.ts` — `decideMemoDrop` (null on absent over / same id / unknown id / cross-level; else the level's key and a copied `arrayMove` order); `applyMemoDrop` (builds `{ key: scope, ids }` from `memos`, decides, calls `reorderMemoLevel` on the matching level, nothing on refusal)
- `frontend/src/app/MemoChainSection.tsx` — one `DndContext` around the ready groups (`PointerSensor` distance 6, `KeyboardSensor` with `sortableKeyboardCoordinates`), `onDragEnd` → `applyMemoDrop(state.levels, String(active.id), over ? String(over.id) : null)`, private position/group-title announcements (never ids), `reorderable` on every `MemoLevelGroup`

### Step 005 — The wall's state, its layout component and its stylesheet rules
- `frontend/src/app/noteWallState.ts` — `createNoteWallState` from `readWorkspaceLayout(storage).wallPinned`; pure `wallMode` / `isWallVisible` / `sessionLayoutClassName` / `wallClassName`; `openWall`, `toggleWallPin`, `dismissWall` (unpins and writes only when effectively pinned) writing through `runInAction` + `writeWorkspaceLayout`
- `frontend/src/app/NoteWallLayout.tsx` — root with `sessionLayoutClassName`; `Box.app-stream`; always-mounted `Paper component="aside"` "Note wall" with `wallClassName`, `shadow="md"` only while floating and visible, `radius={0}`, `inert` + `aria-hidden="true"` while not visible; header `Group` with "Pin notes"/"Unpin notes" (`IconPin`, `color="blue"` while pinned) and "Close notes" (`IconX`)
- `frontend/src/shell.css` — six D11 rules appended after the media block (`.app-session` with `height: 100%` and a `minmax(0, 1fr)` row, `.app-session.wall-pinned`, `.app-stream`, `.app-wall`, `.app-wall.wall-open`, `.app-session.wall-pinned .app-wall`); `.app-main` unchanged (a stretched grid item already gives `height: 100%` a definite base); no existing rule or the media query touched

### Step 006 — The wall on the session screen
- `frontend/src/app/SessionScreen.tsx` — `useState(() => createNoteWallState(storage))` and `useMediaQuery(NARROW_VIEWPORT_QUERY, false, { getInitialValueInEffect: false }) ?? false` at the top (every branch); ready render is one `NoteWallLayout` (stream slot: the unchanged header `Container` + `SessionStream`; wall slot: `MemoChainSection`, removed from the main column); "Open notes" `IconButton` (`IconNotes`, `openWall`) at the end of the header's badge row while `!isWallVisible`; non-ready branches unchanged; file-header comment updated
- `frontend/src/app/App.tsx` — unchanged by the coder (the skeleton's `storage` pass-through on `/sessions/:id` already satisfies the step)

## Skeleton

### Step 001 — frozen interface (2026-10-03)
- `backend/app/errors.py` — `class MemoOrderMismatchError(DomainError)`: `code = "memo_order_mismatch"`, `http_status = 409`, `def __init__(self, message: str | None = None, detail: Mapping[str, Any] | None = None) -> None` (stub body raises; coder supplies the default message as `MemoNotFoundError` does) — new
- `backend/app/models/memos.py` — `class ReorderMemosRequest(BaseModel)`: `model_config = ConfigDict(extra="ignore")`; `scope: MemoScope`; `scope_id: OptionalScopeIdIn = None`; `memo_ids: list[SnowflakeIn]` (required, may be empty); `@model_validator(mode="after") def _require_scope_id_for_non_user_scope(self) -> Self` (stub raises) — new. Response reuses `MemoListResponse`.
- `backend/app/services/memos.py` — `def reorder_memos(connection: Connection, user_id: int, scope: MemoScope, scope_id: int | None, memo_ids: list[int]) -> list[Memo]` — new (stub raises)
- `backend/app/services/memos.py` — `create_memo(connection, generator, user_id, scope, scope_id, body) -> Memo` — signature unchanged; allocation behavior change (min - 1, else 0) left to the coder; current body untouched.
- `backend/app/routers/memos.py` — `@router.put("/api/memos/order", status_code=200) def reorder_own_memos(body: ReorderMemosRequest, current_user: Annotated[CurrentUser, Depends(require_user)], connection: Annotated[Connection, Depends(get_connection)]) -> MemoListResponse` — new (stub raises), declared before the `PATCH` / `DELETE /api/memos/{memo_id}` handlers.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `mypy app` clean, `ruff check .` clean; existing memo tests still pass.

### Step 002 — frozen interface (2026-10-03)
- `frontend/src/shared/api.ts` — `export type HttpMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE"` — changed (was without `"PUT"`)
- `frontend/src/shared/api.ts` — `export async function apiPut<T = unknown>(path: string, body?: unknown, signal?: AbortSignal): Promise<T>` — new (stub throws; coder routes it through `apiRequest(path, "PUT", body, signal)` as `apiPatch` does)
- `frontend/src/app/memosApi.ts` — `export async function reorderMemos(scope: MemoScope, scopeId: string | null, memoIds: string[]): Promise<Memo[]>` — new (stub throws; sends `{ scope, scope_id, memo_ids }`, unwraps `MemoListResponse.memos`; coder adds the `apiPut` import)
- `frontend/src/app/memoLevelState.ts` — `MemoLevelState` gains observable fields `reorderInFlight: boolean = false` and `reorderFailureText: string | null = null` — changed (class otherwise unchanged; constructor unchanged)
- `frontend/src/app/memoLevelState.ts` — `export function isReorderInFlight(state: MemoLevelState): boolean` — new (stub throws)
- `frontend/src/app/memoLevelState.ts` — `export function reorderFailure(state: MemoLevelState): string | null` — new (stub throws)
- `frontend/src/app/memoLevelState.ts` — `export async function reorderMemoLevel(state: MemoLevelState, memoIds: string[]): Promise<void>` — new (stub throws; coder adds the `reorderMemos` import)
- `frontend/src/app/memoLevelState.ts` — `export async function saveNewNote(state: MemoLevelState): Promise<void>` — signature unchanged; the append → prepend behavior change (D5) is left to the coder; current body untouched.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean.

### Step 003 — frozen interface (2026-10-03)
- `frontend/package.json` / `frontend/package-lock.json` — dependencies `"@dnd-kit/core": "^6.3.1"`, `"@dnd-kit/sortable": "^10.0.0"`, `"@dnd-kit/utilities": "^3.2.2"` installed (peer `react >=16.8.0`, React 19 compatible); lockfile adds only these three — new
- `frontend/src/shared/MarkdownEditor.tsx` — `export type MarkdownEditorProps = { label: string; value: string; onChange: (markdown: string) => void; readOnly?: boolean; autoFocus?: boolean }` — changed (was without `autoFocus`); default `autoFocus = false`. `export function MarkdownEditor(props: MarkdownEditorProps): React.JSX.Element` unchanged. Stub: `autoFocus` true throws; omitted/false behaves as before.
- `frontend/src/app/MemoLevelGroup.tsx` — `export type MemoLevelGroupProps = { state: MemoLevelState; title: string; headingOrder: TitleOrder; onRetry: () => void; reorderable?: boolean }` — changed (was without `reorderable`); default `reorderable = false`. `export const MemoLevelGroup = observer(function MemoLevelGroup(props: MemoLevelGroupProps): React.JSX.Element)` unchanged. Stub: `reorderable` true throws; false renders as 015 `007`.
- Left to the coder (behavior, not frozen): new note's listitem first + `autoFocus` passed to its editor; the reorder-failure line (`reorderFailure(state)`); the sortable wrapper (internal, non-exported — name and props are the coder's choice; one shared card body, two outer shells per `003.context.md`).
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean.

### Step 004 — frozen interface (2026-10-03)
- `frontend/src/app/memoReorder.ts` — `export type MemoDropLevel = { key: string; ids: readonly string[] }` — new (the decision's per-level input; `key` is the level's `scope`)
- `frontend/src/app/memoReorder.ts` — `export type MemoDropDecision = { key: string; ids: string[] }` — new (the accepted level's key and its new id order)
- `frontend/src/app/memoReorder.ts` — `export function decideMemoDrop(levels: readonly MemoDropLevel[], activeId: string, overId: string | null): MemoDropDecision | null` — new (stub throws; pure, no DOM, no MobX; absent over id is `null`)
- `frontend/src/app/memoReorder.ts` — `export async function applyMemoDrop(levels: readonly MemoLevelState[], activeId: string, overId: string | null): Promise<void>` — new (stub throws; builds `{ key: level.scope, ids: level.memos.map(m => m.id) }`, calls `decideMemoDrop`, on non-null calls `reorderMemoLevel(level, decision.ids)`; coder adds the `reorderMemoLevel` value import)
- `frontend/src/app/MemoChainSection.tsx` — `export type MemoChainSectionProps = { sessionId: string }` and `export const MemoChainSection = observer(function MemoChainSection(props: MemoChainSectionProps): React.JSX.Element)` — signature unchanged; file untouched by the skeleton. Left to the coder (behavior, not frozen): the one `DndContext` (`PointerSensor` distance 6, `KeyboardSensor` with `sortableKeyboardCoordinates`), `onDragEnd` → `void applyMemoDrop(state.levels, String(event.active.id), event.over ? String(event.over.id) : null)`, the private position/group-title announcements, and `reorderable` on every `MemoLevelGroup`.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean.

### Step 005 — frozen interface (2026-10-03)
- `frontend/src/app/noteWallState.ts` — `export type WallMode = "pinned" | "floating"` — new
- `frontend/src/app/noteWallState.ts` — `export class NoteWallState { pinned: boolean; open = false; constructor(pinned: boolean) }` — new (data class, observable fields only via `makeAutoObservable(this, {}, { autoBind: true })`, mirroring `ShellState`; the constructor is structural and implemented)
- `frontend/src/app/noteWallState.ts` — `export function createNoteWallState(storage: LayoutStorage | null): NoteWallState` — new (stub throws)
- `frontend/src/app/noteWallState.ts` — `export function wallMode(state: NoteWallState, narrow: boolean): WallMode` — new (stub throws)
- `frontend/src/app/noteWallState.ts` — `export function isWallVisible(state: NoteWallState, narrow: boolean): boolean` — new (stub throws)
- `frontend/src/app/noteWallState.ts` — `export function sessionLayoutClassName(state: NoteWallState, narrow: boolean): string` — new (stub throws)
- `frontend/src/app/noteWallState.ts` — `export function wallClassName(state: NoteWallState, narrow: boolean): string` — new (stub throws)
- `frontend/src/app/noteWallState.ts` — `export function openWall(state: NoteWallState): void` — new (stub throws)
- `frontend/src/app/noteWallState.ts` — `export function toggleWallPin(state: NoteWallState, storage: LayoutStorage | null): void` — new (stub throws)
- `frontend/src/app/noteWallState.ts` — `export function dismissWall(state: NoteWallState, storage: LayoutStorage | null, narrow: boolean): void` — new (stub throws; argument order state, storage, narrow per Interface intent)
- `frontend/src/app/NoteWallLayout.tsx` — `export type NoteWallLayoutProps = { state: NoteWallState; narrow: boolean; storage: LayoutStorage | null; stream: React.ReactNode; wall: React.ReactNode }` — new
- `frontend/src/app/NoteWallLayout.tsx` — `export const NoteWallLayout = observer(function NoteWallLayout(props: NoteWallLayoutProps): React.JSX.Element)` — new (stub throws)
- `frontend/src/shell.css` — untouched by the skeleton; the six D11 rules (and any `.app-main` height/display tweak) are the coder's.
- Caller-compile edits (out of Source-files scope): None.
- Gates: `npm run typecheck` clean.

### Step 006 — frozen interface (2026-10-03)
- `frontend/src/app/SessionScreen.tsx` — `export type SessionScreenProps = { sessionId: string; characters: CharactersState; storage: LayoutStorage | null }` — changed (was `{ sessionId: string; characters: CharactersState }`, 011 `009` freeze); `storage` required; `LayoutStorage` is a type import from `./workspaceLayout`.
- `frontend/src/app/SessionScreen.tsx` — `export const SessionScreen = observer(function SessionScreen(props: SessionScreenProps): React.JSX.Element)` — signature unchanged (only its props type changed). Body untouched by the skeleton: `props.storage` is accepted but not yet read. Left to the coder (behavior, not frozen): `useState(() => createNoteWallState(storage))` and `useMediaQuery(NARROW_VIEWPORT_QUERY, false, { getInitialValueInEffect: false })` at the top, the ready render as one `NoteWallLayout` (header + `SessionStream` in `stream`, `MemoChainSection` moved into `wall`), and the "Open notes" `IconButton` (`IconNotes`, `openWall`) shown while `!isWallVisible(state, narrow)`. Not wired as a throwing stub because 005's `createNoteWallState` stub throws and would break the unchanged non-ready branches; the new tests go red on the wall / "Open notes" being absent.
- `frontend/src/app/SessionScreen.tsx` — `export type SessionRouteProps = { characters: CharactersState; storage: LayoutStorage | null }` — changed (was `{ characters: CharactersState }`, 011 `009` freeze); `storage` required.
- `frontend/src/app/SessionScreen.tsx` — `export function SessionRoute(props: SessionRouteProps): React.JSX.Element` — signature unchanged; body now passes `storage` through: `<SessionScreen key={sessionId} sessionId={sessionId} characters={characters} storage={storage} />` (still reads `params.id ?? ""`, still keyed by the id). Implemented — pure pass-through.
- `frontend/src/app/App.tsx` — `/sessions/:id` route element is `<SessionRoute characters={characters} storage={storage} />` (the `storage` from `AppProps`) — changed; `AppProps`, `WorkspaceShell` props and other routes untouched. Implemented — pure pass-through.
- Caller-compile edits (out of Source-files scope): None (the only source caller, `App.tsx`, is a Source file).
- Gates: `npm run typecheck` — all `src/` clean; the remaining errors are in the test file `frontend/tests/app/SessionScreen.test.tsx` (lines 384, 400: `SessionRoute` / `SessionScreen` rendered without `storage`), the test-coder's DoD-12 amendment.

## Tests

### Step 001 — tests (2026-10-03)
- `backend/tests/test_memos_service.py` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-6, DoD-7, DoD-14 — allocation MIN-1 (015 `002` DoD-4 tests rewritten, `__S016_001_DoD1` appended; gap test amended likewise); newest-first listing (015 `002` DoD-13 delete test's listing amended, `__S016_001_DoD2` appended); `reorder_memos` order/keys 0..n-1, no other column (incl. `updated_at`) written, other levels untouched; all four levels, user-level `scope_id` ignored, empty level `[]`; six mismatch cases raise `MemoOrderMismatchError` with no `sort_key` changed; foreign/unknown targets raise the level's not-found; another user's same-scope row keeps its key; no open transaction after each refusal; service still imports no fastapi / no `app.services.*`
- `backend/tests/test_memos_models.py` — covers DoD-8, DoD-9 — `MemoOrderMismatchError` code/409/default message/empty detail and its 409 envelope; `ReorderMemosRequest` parsing, refusals and ignored keys
- `backend/tests/test_memos_router.py` — covers DoD-10, DoD-11, DoD-12, DoD-13, DoD-14 — `PUT /api/memos/order` 200 in the sent order (list + chain agree); 401 / 404 per level / 409 four stale-set cases (empty detail, order unchanged) / 422 four invalid bodies; 015 `004` DoD-14 rewritten and 015 `004` DoD-12's listing amended to newest first (both `__S016_001_DoD12` appended); PATCH/DELETE/GET still answer; router has no SQL construct (AST, the `router.delete` decorator excepted)
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 [manual/live, no test]

### Step 002 — tests (2026-10-03)
- `frontend/tests/shared/api.test.ts` — covers DoD-1 — `apiPut` sends PUT to the exact path with a JSON content type and JSON body, resolves the parsed body (204 → undefined); non-2xx envelope → `ApiError` with backend code + status; transport failure → `client_transport_failed`
- `frontend/tests/app/memosApi.test.ts` — covers DoD-2, DoD-3 — `reorderMemos` PUTs `/api/memos/order` with exactly `{scope, scope_id, memo_ids}` (character id and user `null`), resolves the unwrapped `memos` in order with ids as identical strings; no abort signal; 409 `memo_order_mismatch` → `ApiError` of that code
- `frontend/tests/app/memoLevelState.test.ts` — covers DoD-4..DoD-12 — fresh reorder fields; optimistic C,A,B + in flight + one PUT body; success applies returned rows, no refetch; 500 / transport / 409 each revert to A,B,C with "Could not reorder the notes.", resolve, later success clears; in-flight and same-order calls send nothing; revert keeps a meanwhile-created D first and a meanwhile-deleted B absent; success merge keeps a newer held row at the returned position, keeps an absent held note first, drops a returned id no longer held; new note prepended; autoruns on memos / reorderFailure. 015 amendments: `006` DoD-10 test retitled `… the row lands first — DoD-11` (asserts `memos[0]`); `006` DoD-18 saveNewNote autorun test retitled `… — DoD-11` with its id order `[NEW_MEMO, MEMO_A]` (a D5 consequence not listed in D5's table)
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓

### Step 003 — tests (2026-10-03)
- `frontend/tests/app/MemoLevelGroup.test.tsx` — covers DoD-1..DoD-10 — MarkdownEditor mock extended to record `autoFocus` (and mirror it as `data-autofocus`); 015 `007` DoD-11 tests amended (two saved notes, new listitem **first**, blank blur drops it, no request) → `— DoD-1`; new-note editor gets `autoFocus` true, saved editors never (incl. after the save) → DoD-2; 015 `007` DoD-12 (character-level) and DoD-13 amended to the **first** listitem → `— DoD-3`; without `reorderable` (omitted and explicit false, no `DndContext`) no `tabindex` / `aria-roledescription` / "Note n of m" name → DoD-4; with `reorderable` inside a test `DndContext` (KeyboardSensor + `onDragStart` spy): cards are listitems, `tabIndex` 0, named "Note 1..3 of 3" in order, keep textbox + flags, new note unnamed/unfocusable → DoD-5; Space/Enter on textbox or flag buttons never start a drag, Space on the focused card does with its id → DoD-6; editor focus disables, blur re-enables → DoD-7; pending `PUT /api/memos/order` disables Space on every card, textbox/flags stay usable, settles → drag again → DoD-8; failed reorder shows "Could not reorder the notes." in the region outside every listitem, no notification, cleared by a later success → DoD-9; cards follow `reorderMemoLevel`'s order (twice) → DoD-10. Also amended (locator only, D5 consequence not listed in D5's table): 015 `007` DoD-16 "new note holding Later" flush test now types into the first listitem → `— DoD-1`
- `frontend/tests/build-config.test.ts` — **user-approved deviation (2026-10-03)**: file added as an extra Test file for step 003. Only the "declares none of the deferred packages…" assertion is amended: it now allows `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities` (016 D8 / `frontend-structure.md`); any other `@dnd-kit/*` and every other deferred package stays forbidden. Retitled to cite 016 D8; nothing else in the file changed
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 [manual/live, no test]

### Step 004 — tests (2026-10-03)
- `frontend/tests/app/memoReorder.test.ts` — covers DoD-1..DoD-6 — `decideMemoDrop` on literal `{ key, ids }` levels (user [u1,u2], character [c1,c2,c3], session [s1]): c1→c3 = character [c2,c3,c1], c3→c1 = [c3,c1,c2] → DoD-1; c1→u2, u1→s1, s1→c2 each `null` → DoD-2; over `null`, same id, unknown active, unknown over each `null`, inputs deep-equal after accepted and refused calls → DoD-3; `applyMemoDrop` on populated `MemoLevelState`s with `fetch` stubbed by exact method + path: cross-level drops send no request and leave every level's rows unchanged → DoD-4; c1 over c3 shows c2,c3,c1 before the response, exactly one `PUT /api/memos/order` `{scope:"character", scope_id:<C>, memo_ids:["c2","c3","c1"]}`, user/session rows untouched, effect resolves on a 500 → DoD-5; a second/third drop in the in-flight level sends nothing more; after a failed reorder sets "Could not reorder the notes.", seven refused drops leave every level's `reorderFailure` as it was → DoD-6
- `frontend/tests/app/MemoChainSection.test.tsx` — covers DoD-7, DoD-8, DoD-9 — 015 `008` DoD-5 create test amended to find the new/saved note at the **first** listitem (D5), retitled `… (015 008 DoD-5, amended by 016 D5) — DoD-7`; other 015 assertions unchanged; every saved listitem in all four groups has `tabIndex` 0 and is named "Note n of total" for its own group, region / group names / order still hold → DoD-7; three-level chain: exactly three groups, all reorderable, no "Setup notes" → DoD-8; Space on a focused saved card (via the section's own `DndContext`) makes the `role="status"` live region non-empty and free of every chain memo id → DoD-9
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 [manual/live, no test]

### Step 005 — tests (2026-10-03)
- `frontend/tests/app/noteWallState.test.ts` — covers DoD-1..DoD-6 — `createNoteWallState` pinned from a stored `wallPinned` true, false for null / absent / unparseable / stored false, `open` always false, no write → DoD-1; `wallMode` / `isWallVisible` over all eight (pinned, narrow, open) rows → DoD-2; exact `"app-session wall-pinned"` / `"app-session"` and `"app-wall wall-open"` / `"app-wall"` per mode and visibility → DoD-3; `openWall` sets `open`, no `setItem`, raw record unchanged → DoD-4; `toggleWallPin` from unpinned sets `pinned` (open unchanged) and stores `wallPinned: true` under `"rphelper.workspace-layout"` keeping `navCollapsed: true`, from pinned sets `pinned` false + `open` true and stores `wallPinned: false`, null storage still toggles → DoD-5; `dismissWall` wide pinned → open/pinned false + stored false (navCollapsed kept); narrow pinned open → closes, keeps pinned, no write, widening restores pinned mode; unpinned open → closes, no write at either width → DoD-6. Writes asserted by parsing the stored JSON
- `frontend/tests/app/NoteWallLayout.test.tsx` — covers DoD-7..DoD-11 — closed floating: stream button accessible inside `.app-stream` under an `app-session` root, no complementary without `hidden`, with `hidden` the "Note wall" `aside` has `inert` (not `"false"`) + `aria-hidden="true"`, holds the wall content, follows the stream column inside the root, `app-wall` without `wall-open` → DoD-7; after `openWall`: accessible, "Pin notes" + "Close notes", no `inert` / `aria-hidden`, `wall-open`, root lacks `wall-pinned` → DoD-8; pinned wide: root `wall-pinned`, "Unpin notes", no `wall-open`; same state narrow: no `wall-pinned`, not accessible until `openWall`; a narrow rerender flip reverts and restores → DoD-9; clicking "Pin notes" stores `wallPinned: true` and relabels "Unpin notes"; "Unpin notes" stores false and leaves it accessible floating open; "Close notes" hides it (floating, and wide pinned with stored false) → DoD-10; a `useEffect([])` mount counter stays at 1 across open, close, pin, narrow flip both ways, unpin, close; an uncontrolled input keeps typed text across "Close notes" and `openWall` → DoD-11
- `frontend/tests/stylesheets.test.ts` — covers DoD-12 — `ALLOWED_SELECTORS` amended to the five plus exactly `.app-session`, `.app-session.wall-pinned`, `.app-stream`, `.app-wall`, `.app-wall.wall-open`, `.app-session.wall-pinned .app-wall` (selector guard retitled `… (008 DoD-5, amended by 016 005) — DoD-12`); new block: each of the six declared with declarations outside the media query, none inside it, exactly one `@media`. Every other guard (two stylesheets, no colour, no font/typography, no import, no `@font-face`, the media query string via `NARROW_VIEWPORT_QUERY`) unchanged
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 [manual/live, no test]

### Step 006 — tests (2026-10-03)
- `frontend/tests/app/SessionScreen.test.tsx` — covers DoD-1..DoD-8, DoD-10, DoD-11, DoD-12 — `renderRoute` / `renderScreen` now pass the required `storage` (default `null`, else a file-local in-memory fake); narrow = `window.matchMedia` stub matching exactly `(width < 820px)`, restored after each test. New block: ready with empty storage shows header + "Open notes" (inside the header block) + stream, no accessible complementary, hidden "Note wall" in main holding "Notes", one memo-chain GET → DoD-1; "Open notes" → wall accessible in main, Notes with Your/Character/Setup/Session notes listing the chain's notes per group (no-setup session: no "Setup notes"), "Open notes" gone, no 2nd chain GET, no `setItem` → DoD-2; "Pin notes" stores `wallPinned: true` (navCollapsed kept), reads "Unpin notes", reload shows wall unprompted, no "Open notes" → DoD-3; open-not-pinned reload → closed + "Open notes" → DoD-4; pinned "Close notes" → hidden, "Open notes", stored false; "Unpin notes" → still accessible, stored false → DoD-5; narrow + stored pin → closed + "Open notes", open/close work, record still true, no `setItem` → DoD-6; open/pin/unpin/close keep chain GETs at 1; typed (fireEvent.change) text survives close + reopen → DoD-7; loading / not found / 500 / transport with empty and pinned storage: no wall even hidden, no "Open notes", no chain GET → DoD-8; stored pin a→b: b's wall pinned ("Unpin notes"), b's notes only → DoD-10; `SessionScreen` with `null` and with a pinned fake → DoD-12. Amended 015 `008`: DoD-7 ready clause → Notes inside the hidden wall in main, after header/stream (`— DoD-11`); DoD-7 loading/not-found/failed clauses query Notes with `{ hidden: true }` (`— DoD-8`); DoD-8 a→b opens the wall first and gains the open-resets clause (`— DoD-10`); DoD-9 opens the wall before typing (`— DoD-11`). Every other 011 / 013 / 015 assertion unchanged (DoD-12)
- `frontend/tests/app/App.test.tsx` — covers DoD-9, DoD-11 — `renderApp` takes an optional `storage` (default `null`); with a stored `wallPinned: true`: `/`, `/characters/<id>`, `/settings`, `/search` have no "Note wall" (even hidden) and no "Open notes"; `/sessions/1` shows the wall accessible inside main with "Unpin notes" and Notes, no "Open notes", its `.app-session` root has `wall-pinned`, and the `.app` grid has exactly nav + main → DoD-9. 015 `008` DoD-7 `/sessions/1` clause amended to find Notes inside the hidden "Note wall" → DoD-11. No other assertion changed
- `frontend/tests/app/WorkspaceShell.test.tsx` — covers DoD-13 — the "two columns … (no wall in 008)" describe re-titled to say the shell grid never holds the wall (it lives inside the session screen), no "008" scoping; every assertion unchanged
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 [manual/live, no test]
- TEST-fault round 1 (2026-10-03): closed-wall lookups in `SessionScreen.test.tsx` / `App.test.tsx` now query `complementary` with `hidden: true` and no name, filtered by `aria-label === "Note wall"` (exactly one); DoD-8/DoD-9 absence checks now assert no complementary (hidden included) and no `[aria-label="Note wall"]` element. No inventory change.

## Notes & Issues

_populated by the coder when worth saying_

## Ultra phase

- orient: done 2026-10-03
- harvest: done — docs/.cache/ultra/016.note-wall/harvest.md (1 report)
- skeleton: done — steps 001, 002, 003, 004, 005, 006
- tests: done — steps 001, 002, 003, 004, 005, 006   (003 also amends tests/build-config.test.ts — user-approved deviation 2026-10-03)
- red-gate: PASS (run 1)
- code: done — steps 001, 002, 003, 004, 005, 006
- verify: FAIL (run 1) — 005 TEST, 006 TEST
- verify: FAIL (run 2) — 005 TEST
- verify: PASS (run 3)
