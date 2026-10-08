# Feature 014 — entry-editing-and-copy-out

| Step | File                            | Status  | Verifier | Date |
|------|---------------------------------|---------|----------|------|
| 001  | `001.settled-edit-backend.md` | done    | PASS     | 2026-10-02 |
| 002  | `002.plain-text.md` | done    | PASS     | 2026-10-02 |
| 003  | `003.paste-warning.md` | done    | PASS     | 2026-10-02 |
| 004  | `004.entry-effects.md` | done    | PASS     | 2026-10-02 |
| 005  | `005.entry-actions.md` | done    | PASS     | 2026-10-02 |

## Files Changed

### Step 001 — Settled rows become editable through the existing `PATCH`
- `backend/app/services/messages.py` — `edit_message_text` refuses only buried rows; settled rows are updated (text + `updated_at`), bump the session, and read back through `settled_entries`; module and function docstrings refreshed

### Step 002 — The pure markdown-to-plain-text module
- `frontend/src/app/plainText.ts` — `toPlainText` implemented as the spec's three stages (A line rules incl. fences, B inline rules per paragraph over protected-character cells, C whitespace tidy-up); module-private helpers only, imports nothing

### Step 003 — The enormous-paste warning
- `frontend/src/app/pasteCost.ts` — `estimateTokens` (ceil of length / 4) and `isEnormousPaste` (strictly above 32,000 tokens); imports nothing
- `frontend/src/shared/notifyWarning.ts` — closed id → sentence map; one yellow `notifications.show` per call, mirroring `notifyFailure`
- `frontend/src/app/Composer.tsx` — paste handler reads the text first (guarded against a missing `clipboardData`), warns synchronously when not blank and enormous (both positions), then the unchanged 013 partner filing / my-turn passthrough

### Step 004 — The settled-entry edit effect and the copy-out effect
- `frontend/src/app/streamState.ts` — `editEntry` mirrors `editZoneMessage` over `entries`: blank / unchanged → true with no request; settled response replaces that one row; non-settled response → `rereadBoth`; failure → notify, `rereadEntries`, false; writes nothing and notifies nothing once aborted; never sets `busy`
- `frontend/src/app/copyOut.ts` — `copyAsPlainText` converts with `toPlainText`, writes via `navigator.clipboard.writeText` when present, else the D9 off-screen read-only textarea + `execCommand("copy")` with removal and focus restore in `finally`; failures go to `notifyFailure`, resolves false, never rejects

### Step 005 — Settled-entry actions: reveal, in-place edit, copy on turns
- `frontend/src/app/StreamRecord.tsx` — `StreamEntry` reveals the always-rendered actions group (`data-revealed` + `opacity`) by `useHover` / `useFocusWithin` merged onto the `li` via `useMergedRef`, or `useMediaQuery("(hover: none)")`; "Edit entry" (absent while editing), "Copy as plain text" on turns calling `copyAsPlainText(entry.text)`, 013's re-open moved into the group unchanged; "Edit entry text" autosizing `Textarea` committing on blur through `editEntry`; header comment refreshed

## Skeleton

### Step 001 — frozen interface (2026-10-02)
- `backend/app/services/messages.py` — `edit_message_text(connection: Connection, user_id: int, message_id: int, text: str) -> StreamMessage` — unchanged (signature, return type and errors `MessageNotFoundError` / `MessageNotEditableError` as delivered by 012 `002`). Only the body's behaviour widens (settled rows proceed); no stub edit made, body left as-is for the coder.
- Caller-compile edits (out of Source-files scope): None.

### Step 002 — frozen interface (2026-10-02)
- `frontend/src/app/plainText.ts` — `export function toPlainText(text: string): string` — new (sole export; module imports nothing; stub body throws `Error("not implemented")`).
- Caller-compile edits (out of Source-files scope): None.

### Step 003 — frozen interface (2026-10-02)
- `frontend/src/app/pasteCost.ts` — `export const CHARS_PER_TOKEN = 4;` — new (value set; data, not behaviour).
- `frontend/src/app/pasteCost.ts` — `export const PASTE_WARNING_THRESHOLD_TOKENS = 32_000;` — new (value set).
- `frontend/src/app/pasteCost.ts` — `export function estimateTokens(text: string): number` — new (stub throws `Error("not implemented")`).
- `frontend/src/app/pasteCost.ts` — `export function isEnormousPaste(text: string): boolean` — new (stub throws). Module imports nothing.
- `frontend/src/shared/notifyWarning.ts` — `export type WarningId = "paste-context-cost";` — new (closed set; exactly one member; identifier literal **`"paste-context-cost"`** is the paste context-cost warning).
- `frontend/src/shared/notifyWarning.ts` — `export function notifyWarning(id: WarningId): void` — new (stub throws; the coder adds the `@mantine/notifications` import and the identifier → sentence map).
- `frontend/src/app/Composer.tsx` — no signature change; `Composer` and its internal `handlePaste` left as-is for the coder.
- Caller-compile edits (out of Source-files scope): None.

### Step 004 — frozen interface (2026-10-02)
- `frontend/src/app/streamState.ts` — `export async function editEntry(state: StreamState, messageId: string, text: string, signal?: AbortSignal): Promise<boolean>` — new (appended after `editZoneMessage`, same parameter order; stub is `async` and throws `Error("not implemented")`, i.e. returns a rejected promise; no existing function altered).
- `frontend/src/app/copyOut.ts` — `export async function copyAsPlainText(text: string): Promise<boolean>` — new (sole export; new module; stub is `async` and throws `Error("not implemented")`; the coder adds the `toPlainText` (`./plainText`) and `notifyFailure` (`../shared/notifyFailure`) imports).
- Caller-compile edits (out of Source-files scope): None.

### Step 005 — frozen interface (2026-10-02)
- `frontend/src/app/StreamRecord.tsx` — `export type StreamRecordProps = { state: StreamState; signal?: AbortSignal }` and `export const StreamRecord = observer(function StreamRecord(props: StreamRecordProps): React.JSX.Element)` — unchanged. Its list items are now rendered by `StreamEntry` (`key={entry.id}`, `isLast={index === lastIndex}`).
- `frontend/src/app/StreamRecord.tsx` — `type StreamEntryProps = { state: StreamState; entry: Message; isLast: boolean; signal?: AbortSignal }` — new (module-private).
- `frontend/src/app/StreamRecord.tsx` — `const StreamEntry = observer(function StreamEntry(props: StreamEntryProps): React.JSX.Element)` — new (module-private). Skeleton body renders exactly 013 `004`'s per-item markup (`li` → header `Group` with kind label and, when `isLast && showsReopen(state)`, "Re-open last entry" disabled while `busy` calling `reopenLast(state, signal)` → `EntryBody` by kind). Not yet implemented, left for the coder: the actions group, the reveal hooks, "Edit entry", "Copy as plain text" and the "Edit entry text" editor. Because they are simply not rendered, the new tests fail on missing elements.
- Test-facing contract (strings and attributes, exact):
  - list `aria-label` **"Settled record"** (unchanged); one `listitem` per entry.
  - **"Edit entry"** — `IconButton` (`IconEdit`) in each item's actions group, on every kind; absent while that item's editor is open.
  - **"Copy as plain text"** — `IconButton` (`IconCopy`) in the actions group on `turn` items only; absent (not disabled) on `partner` / `decision`.
  - **"Re-open last entry"** — 013's label, unchanged; moves into the last item's actions group; same presence rule, `disabled` while `busy`.
  - **"Edit entry text"** — the accessible label of the autosizing Mantine `Textarea` that replaces the body while editing.
  - The actions group element carries the attribute **`data-revealed`** with value `"true"` / `"false"` (plus style `opacity` 1 / 0). It is always rendered and is the only element in an item that carries `data-revealed`.
- Collaborators that the coder wires in (already frozen): `editEntry(state, messageId, text, signal?) : Promise<boolean>` (`./streamState`), `copyAsPlainText(text): Promise<boolean>` (`./copyOut`). The `tests/setup.ts` `matchMedia` stub is confirmed present, so `useMediaQuery` is usable in jsdom.
- Caller-compile edits (out of Source-files scope): None.

## Tests

### Step 001 — tests (2026-10-02)
- `backend/tests/test_messages_service.py` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-6, DoD-7, DoD-8 — weeks-old settled turn edited (kind/settled_at/created_at kept, updated_at later, same entries position, not in zone); partner block and decision/turn edited literally with kind kept; bump equals row `updated_at`; buried still refused (012 DoD-9 amended: settled-refusal cases removed, `test_a_refused_edit_leaves_the_reads_unchanged__S012_002_DoD9` and `test_refused_operations_do_not_bump_any_session__S012_002_DoD10` narrowed to the buried row); another user's settled row not found; archived session edit succeeds; AST check that no `update(...)` statement assigns `kind` / `settled_at` / `related_to` (plus a non-vacuity check that an `update(...)` exists). `_insert_message` gained optional `created_at` / `updated_at` (defaults unchanged).
- `backend/tests/test_stream_router.py` — covers DoD-9, DoD-10, DoD-11, DoD-12 — settled turn PATCH 200 with same `settled_at`, same entries position, zone unchanged; 012 DoD-13's partner/settled-turn 409 tests replaced by partner-block and settled-decision 200 successes (titles keep `__S012_004_DoD13`, add `__S014_001_DoD10`); buried 409 kept; blank/missing 422 and 500 000 chars 200 on a settled entry; last use not earlier after settled PATCH, unchanged after buried refusal; user B gets 404 `message_not_found`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 [manual/live, no test]

### Step 002 — tests (2026-10-02)
- `frontend/tests/app/plainText.test.ts` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-6 — `toPlainText` returns exactly the outputs of 002.context.md examples E1–E11, B1–B10, C1–C8, W1–W5 (one `it` per example, literals transcribed verbatim, bullet written as `•`); L1–L6 returned byte-for-byte unchanged; raw-source read of `src/app/plainText.ts` finds no import / re-export / require / dynamic import and no react, mobx, @mantine or shared/ specifier (parens.ts technique).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓

### Step 003 — tests (2026-10-02)
- `frontend/tests/app/pasteCost.test.ts` — covers DoD-1, DoD-2, DoD-3 — `CHARS_PER_TOKEN` 4, `PASTE_WARNING_THRESHOLD_TOKENS` 32 000; `estimateTokens` "" → 0, "abcd" → 1, "abcde" → 2, 128 000 chars → 32 000; `isEnormousPaste` 128 000 → false, 128 001 → true, 500 000 → true, "" → false; raw-source read finds no import / re-export / require / dynamic import.
- `frontend/tests/shared/notifyWarning.test.ts` — covers DoD-4 — mocks `@mantine/notifications` (original spread, `notifications.show` replaced); `notifyWarning("paste-context-cost")` calls `show` exactly once with `message` exactly the UI-strings sentence and `color` "yellow" (not "red"), returns undefined; `@ts-expect-error` guard that free text is rejected (closed set).
- `frontend/tests/conventions.test.ts` — covers DoD-5 — only the notification-importer test amended: retitled "…imported by exactly shared/notifyFailure.ts and shared/notifyWarning.ts", keeps its 002/006 suffix plus this step's (`— DoD-12, DoD-5`); importer list sorted and must equal exactly the two files. No other test changed.
- `frontend/tests/app/ComposerPasteWarning.test.tsx` — covers DoD-6, DoD-7, DoD-8, DoD-9 — mocks `src/shared/notifyWarning` and `src/shared/notifyFailure`, fetch stubbed by exact path + method, `Composer` in `AppProviders`, partner chosen with `chooseKind`; partner 128 001 chars: warns once (synchronously) with "paste-context-cost", POSTs …/entries with exactly `{"kind":"partner","text":…}`, default prevented, draft unchanged; partner 128 000 chars: same POST, no warning; my turn 128 001: warns once, no request, not default-prevented; my turn short paste: no warning, no request, not prevented; 128 001 whitespace: no warning in either position.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓ (conventions + notifyFailure guard), DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 [manual/live, no test]
- `frontend/tests/shared/notifyFailure.test.tsx` — covers DoD-5 — scope widened by user approval (2026-10-02): guard missed by the plan. Only the 002/005 DoD-15 guard test amended: allowed callers of Mantine's notification API are exactly `shared/notifyFailure.ts` and `shared/notifyWarning.ts` (closed list, any third caller fails); retitled "…but shared/notifyFailure.ts and shared/notifyWarning.ts calls…", suffix `— DoD-15, DoD-5`. No other test changed.

### Step 004 — tests (2026-10-02)
- `frontend/tests/app/entryEffects.test.ts` — covers DoD-1..DoD-12 — `editEntry`: turn / partner / decision ("Skip to morning.") edits send exactly `PATCH /api/messages/<id>` `{text}` and replace only that entry with the served settled row (ids, order, other entries unchanged, no GET, true, no notify); `"  She ((really)) waits.  "` sent verbatim; `""`, `"  \n"`, unchanged text → no request, true; `kindOverride` / `effectiveKind` unchanged after `chooseKind` + successful edit; 409 `message_not_editable` → one `ApiError` notify, `[PATCH, GET …/entries]` only, entries = served list, false; non-settled served row → PATCH then both GETs, row not written into entries, true, no notify; abort (fetch rejects, or late settled / non-settled / 409 answer) → nothing written, no notify, resolves false; `busy` false while pending and after every outcome. `copyAsPlainText`: clipboard stub receives exactly `"Scene\n\nShe smiles and waits."`, true, no fetch, no notify; `writeText` rejection → notify once with that value, false; clipboard absent + `execCommand` stub → at `"copy"` exactly one attached textarea with the plain text, removed afterwards, focus back on the prior button, true; `execCommand` false / throwing → notify once (thrown value when thrown), textarea removed, false. `navigator.clipboard` and `document.execCommand` own-property descriptors restored after each test.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓

### Step 005 — tests (2026-10-02)
- `frontend/tests/app/StreamRecordActions.test.tsx` — covers DoD-1, DoD-2, DoD-4, DoD-5, DoD-6, DoD-7, DoD-8, DoD-9, DoD-10 — `[partner P1, turn T1, decision ((D1))]`: one "Edit entry" per item; "Copy as plain text" only in the turn item, absent (queryByRole / queryByLabelText null) in partner and decision; turn edit opens focused "Edit entry text" holding "T1" with the item's "Edit entry" gone, blur with "T1 fixed" logs exactly `PATCH /api/messages/<turn id>` body `{"text":"T1 fixed"}`, no GET, editor closes, served text shown (separate test with a differing served text), other items unchanged; partner served text inside a `blockquote`; decision "plain words" served → `[data-paren="ooc"]` card; unchanged / whitespace blur → no request, editor closes, "T1" shown; 409 `message_not_editable` → one `ApiError` notify with that code, `GET …/entries` after the PATCH, editor holds "T1 fixed"; copy of `"# Scene\n\n*She smiles* and **waits**."` → stubbed `navigator.clipboard.writeText` called once with `"Scene\n\nShe smiles and waits."`, no fetch, no notify (fireEvent only — no userEvent, whose setup replaces the clipboard; descriptor restored after); reveal via the item's single `[data-revealed]` element: false at rest, mouseEnter/mouseLeave true/false, `focus()` on "Edit entry" true / `blur()` false, hidden controls present, not disabled, reachable by role and inside the group (re-open too, on the last item); editor open (opened by fireEvent.click, then mouseLeave) → true. Fetch stubbed by exact method + path with PATCH routed; `notifyFailure` mocked (its only export).
- `frontend/tests/app/StreamRecord.test.tsx` — covers DoD-3 — only 013 `004`'s two DoD-9 tests amended: Copy assertions scoped to the partner and decision items (with and without a zone row); the "none anywhere" assertions removed. Titles keep 013's suffix and append this step's: `— DoD-9 — DoD-3`. Describe heading and file header comment updated to match; no other test changed.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 [manual/live, no test]

## Notes & Issues

- Step 001: stale docstrings still describe the old settled-row refusal outside this step's Source files — `backend/app/routers/stream.py` (~l.153, PATCH route) and `backend/app/errors.py` (~l.400, `MessageNotEditableError`). Not edited (out of scope).

## Ultra phase

- orient: done 2026-10-02
- harvest: done — docs/.cache/ultra/014.entry-editing-and-copy-out/harvest.md (2 reports)
- skeleton: done — steps 001, 002, 003, 004, 005
- tests: done — steps 001, 002, 003, 004, 005   (003 scope widened by user: tests/shared/notifyFailure.test.tsx guard)
- red-gate: PASS (run 1)
- code: done — steps 001, 002, 003, 004, 005   (no re-freeze; 003 coder saw the ## Tests inventory before narrowing — air-gap slip, verify adjudicates)
- verify: PASS (run 1)
