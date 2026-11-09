# Feature 033 — character-page-tabs

| Step | File                              | Status  | Verifier | Date |
|------|-----------------------------------|---------|----------|------|
| 001  | `001.tabbed-shell.md` | done | PASS | 2026-10-08 |
| 002  | `002.notes-header-add.md` | done | PASS | 2026-10-08 |
| 003  | `003.setups-inline-create.md` | done | PASS | 2026-10-08 |
| 004  | `004.composer-setup-choice.md` | done | PASS | 2026-10-08 |
| 005  | `005.sessions-list-header.md` | done | PASS | 2026-10-08 |

## Files Changed

### Step 001 — tabbed shell
- `frontend/src/app/CharacterScreen.tsx` — ready mode = header (name, Archived badge, icon-only Archive/Restore + Export) + five Mantine Tabs (Sessions default; composer, Divider, sessions list; Main info with taller persona; Configuration; Notes; Setups)
- `frontend/src/shared/MarkdownEditor.tsx` — optional `contentMinHeight` applied as an inline min-height on the editable surface; omitted = unchanged
- `frontend/src/app/CharacterComposer.tsx` — section heading "Start a session" → "New session"

### Step 002 — notes header add
- `frontend/src/app/memoLevelState.ts` — `discardNewNote` closes an open, not-saving draft via `runInAction`, no request
- `frontend/src/app/MemoLevelGroup.tsx` — `headerAdd` mode: '+' `IconButton` beside the Title (ready only, disabled while a draft is open), no labelled button below the list, draft with Save/Cancel icon buttons and no blur-save; default render unchanged
- `frontend/src/app/CharacterNotesSection.tsx` — passes `headerAdd` and `layout="list"` (was `"grid"`)
### Step 003 — setups inline create
- `frontend/src/app/SetupCreateForm.tsx` — inline create form: fresh `SetupDraft` per mount, autofocused Name + Description editor, "Save setup" (enabled iff `canSubmit`) / "Cancel new setup" (disabled while submitting, no request) icon buttons, `draft.error` inline, submit aborted on unmount
- `frontend/src/app/SetupsSection.tsx` — header '+' `IconButton` "New setup" (disabled while open) replaces the labelled button; component-local flag mounts `SetupCreateForm` above the list; `onCreated` applies the row then closes; `SetupModal` mounted for edit only

### Step 004 — composer setup choice
- `frontend/src/app/sessionsApi.ts` — `startSessionWithMessage` posts `{ opening_message, setup_id }` with a setup id, exactly `{ opening_message }` without
- `frontend/src/app/characterComposerState.ts` — `loadComposerSetups` (non-archived only, stale selection → null, failure → "failed", abort-safe, never rejects), `selectComposerSetup` via `runInAction`; `sendCharacterComposer` passes `state.selectedSetupId`
- `frontend/src/app/CharacterComposer.tsx` — `size="xs"` "Setup" `Select` in `ComposerCore`'s `underArea` ("No setup" first, then working setups), loads on mount (aborted on unmount) and on dropdown open, disabled while sending; "Could not load setups to choose from." beside it on failure

### Step 005 — sessions list header
- `frontend/src/app/sessionsSectionState.ts` — removed `startSessionFromSection`, `START_FAILED`, `selectSetup`, `loadSetupChoices`, `SessionStartStatus` and fields `setups`/`setupsStatus`/`selectedSetupId`/`startStatus`/`startError` (and the `startSession`/`fetchSetups`/`Setup` imports); kept exports unchanged
- `frontend/src/app/SessionsSection.tsx` — header Group = "Sessions" Title, "Show archived sessions" switch, `IconButton` "Import session" (`IconUpload`) inside `FileButton` (render-prop `onClick`), disabled while importing; Setup select, Start session, labelled import row, setups-failed line, setups load/reload and start Alert removed

## Skeleton

### Step 001 — frozen interface (2026-10-08)
- `frontend/src/shared/MarkdownEditor.tsx` — `MarkdownEditorProps.contentMinHeight?: number` (minimum height of the editable content area, in pixels; omitted = renders exactly as today) — new. Stub: `MarkdownEditor` throws `Error("not implemented: MarkdownEditor contentMinHeight")` when the prop is passed; no caller passes it yet.
- `frontend/src/app/CharacterScreen.tsx` — `CharacterScreen` props unchanged (`characters`, `characterId`, `sessions`); no new exported symbol. Ready-mode JSX restructure is left to the coder. Public contracts the tests bind to:
  - Tab list (`role="tablist"`) with exactly five `role="tab"` elements, accessible names in order: `"Sessions"`, `"Main info"`, `"Configuration"`, `"Notes"`, `"Setups"`; `"Sessions"` has `aria-selected="true"` on open; `keepMounted` default (inactive `tabpanel`s mounted but hidden); `Tabs` keyed by character id; active tab is not in the URL.
  - Page header: `Title order={2}` with the saved name; `"Archived"` badge text when archived.
  - Header icon buttons via shared `IconButton` (accessible name = tooltip = label): `"Archive"` (`IconArchive`) or `"Restore"` (`IconArchiveOff`), and `"Export"` (`IconDownload`, `disabled` while exporting). No labelled Archive/Restore/Export text buttons remain.
  - Panels: Sessions tabpanel = region `"New session"` then a Mantine `Divider` then region `"Sessions"`; Main info tabpanel = textbox `"Name"` + persona `MarkdownEditor` textbox `"Persona"` (label unchanged); Configuration / Notes / Setups tabpanels = regions `"Configuration"`, `"Notes"`, `"Setups"`.
  - `/characters/new` (draft mode): no tablist, no sections, no header icon actions.
- `frontend/src/app/CharacterComposer.tsx` — `CharacterComposer` props unchanged; contract: its `<section>` region accessible name becomes `"New session"` (was `"Start a session"`). Not changed by the skeleton (text change is the coder's behaviour).
- Caller-compile edits (out of Source-files scope): None.

### Step 002 — frozen interface (2026-10-08)
- `frontend/src/app/memoLevelState.ts` — `export function discardNewNote(state: MemoLevelState): void` — new. Stub throws `Error("not implemented: discardNewNote")`. Contract: open, not-saving draft → `state.newNote = null` via `runInAction`, no request; `newNote.saving === true` → unchanged; `newNote === null` → no-op.
- `frontend/src/app/MemoLevelGroup.tsx` — `MemoLevelGroupProps.headerAdd?: boolean` (default `false`; destructured as `headerAdd = false`) — new. Stub: `MemoLevelGroup` throws `Error("not implemented: MemoLevelGroup headerAdd")` when `headerAdd` is true; when false/omitted it renders exactly as before. `MemoLevelGroup` / `MemoLevelLayout` otherwise unchanged. Accessible names the tests bind to, when `headerAdd` is true (all via shared `IconButton`, accessible name = tooltip = label):
  - `"New note"` — `IconPlus`, in the section header beside the `Title`, ready state only, `disabled` while `state.newNote !== null`, calls `openNewNote(state)`. The labelled `"New note"` `Button` below the list is NOT rendered.
  - `"Save new note"` — `IconDeviceFloppy`, inside the draft `listitem` (first item of the list), calls `saveNewNote(state)`, `disabled` while `newNote.saving`.
  - `"Cancel new note"` — `IconX`, inside the draft `listitem`, calls `discardNewNote(state)`, `disabled` while `newNote.saving`.
  - Draft editor: `MarkdownEditor` label `"Note"` (unchanged), `autoFocus`; no blur-save; `newNote.failure` text renders inside the draft `listitem`.
- `frontend/src/app/CharacterNotesSection.tsx` — `CharacterNotesSection` props unchanged (`characterId: string`). Not edited by the skeleton (passing `headerAdd` would make the stub throw on every character page); the coder switches its `<MemoLevelGroup>` to `headerAdd` and `layout="list"` (was `"grid"`), keeping `reorderable`, its own `DndContext` and the `memoDnd` sensors.
- Caller-compile edits (out of Source-files scope): None (`MemoChainSection.tsx`, `SettingsScreen.tsx` do not pass the new optional prop).

### Step 003 — frozen interface (2026-10-08)
- `frontend/src/app/SetupCreateForm.tsx` — new:
  - `export type SetupCreateFormProps = { characterId: string; onCreated: (created: Setup) => void; onCancel: () => void; }` (`Setup` from `./setupsApi`).
  - `export const SetupCreateForm = observer(function SetupCreateForm(props: SetupCreateFormProps): React.JSX.Element)` — stub throws `Error("not implemented: SetupCreateForm")`.
  - Contract: builds `new SetupDraft(characterId, null)` in `useState` (fresh per mount); fields written via `setDraftName` / `setDraftDescription`; Save runs `submitSetup(draft, onCreated, signal)` (abort on unmount); `draft.error` renders inside the form. Accessible names the tests bind to:
    - text input `"Name"` (Mantine `TextInput`, focused on mount);
    - `MarkdownEditor` label `"Description"`;
    - `IconButton` `"Save setup"` (`IconDeviceFloppy`) — `disabled` unless `canSubmit(draft)` (so also disabled while submitting);
    - `IconButton` `"Cancel new setup"` (`IconX`) — calls `onCancel`, no request; `disabled` while `draft.submitStatus === "submitting"`.
    - No `role="dialog"` is rendered.
- `frontend/src/app/SetupsSection.tsx` — `SetupsSectionProps` unchanged (`characterId: string`); no new exported symbol. Not edited by the skeleton (mounting the throwing stub would break every character page); the coder does the restructure. Contract:
  - Header `Group`: `Title order={3}` `"Setups"`, shared `IconButton` `"New setup"` (`IconPlus`, `disabled` while the inline form is open), `Switch` `"Show archived setups"` unchanged. The labelled `"New setup"` `Button` is removed.
  - Component-local `useState` open flag mounts `<SetupCreateForm characterId={characterId} onCreated={…} onCancel={…} />` below the header and above the list output (above the loader, the failed state, "No setups yet." and the table). `onCreated` = `applySetup(state, created)` then close the flag; `onCancel` closes the flag.
  - `SetupModal` mounted only for edit (`editTarget !== null`, `setup={editTarget}`); never for create.
- Caller-compile edits (out of Source-files scope): None.

### Step 004 — frozen interface (2026-10-08)
- `frontend/src/app/sessionsApi.ts` — `export async function startSessionWithMessage(characterId: string, openingText: string, setupId: string | null = null, signal?: AbortSignal): Promise<StartedSession>` — changed (was `startSessionWithMessage(characterId: string, openingText: string, signal?: AbortSignal)`). Stub: throws `Error("not implemented: startSessionWithMessage setupId")` only when `setupId !== null`; null/omitted posts exactly `{ opening_message }` as before. Contract: non-null → body `{ opening_message: <text verbatim>, setup_id: <id string> }`; return/error behaviour unchanged. `startSession` left untouched.
- `frontend/src/app/characterComposerState.ts`:
  - `export type CharacterComposerSetupsStatus = "idle" | "loading" | "ready" | "failed"` — new.
  - `CharacterComposerState` gains observable fields — new: `setups: Setup[] = []` (working setups only; `Setup` from `./setupsApi`), `setupsStatus: CharacterComposerSetupsStatus = "idle"`, `selectedSetupId: string | null = null` (null = "No setup"). Existing `characterId`, `draft`, `sending` and the constructor unchanged.
  - `export async function loadComposerSetups(state: CharacterComposerState, signal?: AbortSignal): Promise<void>` — new. Stub throws `Error("not implemented: loadComposerSetups")`. Contract: aborted signal → no writes; sets `setupsStatus` "loading", calls `fetchSetups(state.characterId, false, signal)`, then in one action `setups` = non-archived ones (server order), `setupsStatus` "ready", and `selectedSetupId` reset to null if no longer among `setups`; failure → `setupsStatus` "failed", previous choices and selection kept; nothing written once aborted; never rejects.
  - `export function selectComposerSetup(state: CharacterComposerState, setupId: string | null): void` — new (setter added so the component never writes the observable outside an action, mirroring `selectSetup` in `sessionsSectionState.ts`). Stub throws `Error("not implemented: selectComposerSetup")`. Contract: sets `selectedSetupId` via `runInAction`; no request.
  - `sendCharacterComposer(state, sessions, onStarted)` — signature unchanged; contract change left to the coder: calls `startSessionWithMessage(state.characterId, state.draft, state.selectedSetupId)`; success/failure handling unchanged.
- `frontend/src/app/CharacterComposer.tsx` — `CharacterComposerProps` unchanged (`characterId`, `sessions`); not edited by the skeleton. Contract the tests bind to:
  - A Mantine `Select` (size `xs`/`sm`) with accessible label `"Setup"`, rendered through `ComposerCore`'s `underArea` or `besideSend` slot (no `ComposerCore` change). Options: first `"No setup"` (maps to `selectedSetupId === null`), then `state.setups` by `name`. Selected value on open is `"No setup"`. Changes go through `selectComposerSetup`.
  - `loadComposerSetups(state, signal)` once on mount (aborted on unmount) and again on the Select's `onDropdownOpen`.
  - Select `disabled` while `state.sending`.
  - When `state.setupsStatus === "failed"`, the non-blocking text `"Could not load setups to choose from."` renders beside the select; Send still works with "No setup".
  - No kind switch.
- Caller-compile edits (out of Source-files scope): None (the only production caller, `sendCharacterComposer`, passes two args; `tests/app/sessionsApi.test.ts` calls also pass two args).

### Step 005 — frozen interface (2026-10-08)
- No source edit by the skeleton: the step is removal-only plus a JSX change, and `tsconfig.json` includes `tests/`, so removing any symbol now would break `npm run typecheck` via `tests/app/sessionsSectionState.test.ts` (imports `loadSetupChoices`, `selectSetup`, `startSessionFromSection`; reads `setups`, `setupsStatus`, `selectedSetupId`, `startStatus`, `startError`). All removals are deferred to the coder. Typecheck green at freeze.
- `frontend/src/app/sessionsSectionState.ts` — exports kept unchanged: `SessionsSectionLoadStatus`, `class SessionsSectionState` (constructor `(characterId: string)`; fields `characterId`, `sessions`, `status`, `showArchived`, `error`, `pendingId`), `loadSectionSessions(state, signal?)`, `setShowArchived(state, showArchived)`, `applySectionSession(state, session)`, `archiveSectionRow(state, workspace, sessionId, signal?)`, `restoreSectionRow(state, workspace, sessionId, signal?)`. **Removed (coder):**
  - `startSessionFromSection(state, workspace, onStarted, signal?)` and the private `START_FAILED`;
  - `selectSetup(state, setupId)` and field `selectedSetupId`;
  - `loadSetupChoices(state, signal?)` and fields `setups`, `setupsStatus` — no other reader in the section (`setupOptions` was the only reader of `state.setups`; the per-row setup label reads `session.setup_name`), so they go per the intent's "unless" clause; the `fetchSetups` / `Setup` imports go with them;
  - `export type SessionStartStatus` and fields `startStatus`, `startError` — written only by the start path, so dead once it goes; the `startSession` import goes (`startSession` itself stays in `sessionsApi.ts`).
- `frontend/src/app/SessionsSection.tsx` — `SessionsSectionProps` unchanged (`characterId: string`, `sessions: SessionsState`); `SessionsSection` export unchanged. Coder removes `NO_SETUP_VALUE`, `reloadSetupChoices` / choices effect / `choicesControllerRef`, `start`, `setupOptions`, `useNavigate` if unused, the `startError` Alert, and the `Select` / `IconPlus` imports. Public contract the tests bind to:
  - region `"Sessions"` (`<section aria-labelledby>`), header `Group`: `Title order={3}` `"Sessions"`, `Switch` `"Show archived sessions"` (unchanged), and shared `IconButton` `"Import session"` (`IconUpload`; accessible name = tooltip = label) rendered inside the existing `FileButton` (`accept=".json,application/json"`, `resetRef`), the render-prop's `onClick` passed to `IconButton`'s `onClick`; `disabled` while the import is in flight (was `loading`).
  - No `"Setup"` select, no `"Start session"` button, no labelled `"Import session"` text button row, never the text `"Could not load setups to choose from."`; mounting issues no setups request and no message-less session create.
  - Below the header unchanged: `error` Alert, Loader / "Could not load sessions" + "Retry" / "No sessions yet." / table with row menu (`"Actions for <label>"`; Archive / Restore / Export).
- Caller-compile edits (out of Source-files scope): None.

## Tests

### Step 001 — tests (2026-10-08)
- `frontend/tests/app/CharacterScreen.test.tsx` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-6, DoD-7, DoD-8, DoD-9, DoD-10, DoD-11, DoD-12, DoD-13 — new "033 step 001" block (five tabs in order; Sessions `aria-selected` on open; tab changes leave the URL alone and another character lands on Sessions; every section mounted at open, one notes memos GET, no request on tab switching; Sessions panel = "New session" region, divider, "Sessions" region; Main info / Configuration / Notes / Setups panel contents; Main info blur-save + blank-name refusal; header name, badge, icon-only Archive/Restore/Export and no text labels; header Archive/Restore round-trip; draft page has no tablist/sections/header actions; composer region "New session"). Existing clauses rewritten: body-order `precedes()` checks replaced by tab-panel placement (010 DoD-10, 011 DoD-12, 015 DoD-4, 018 DoD-6, bug-fix exactly-once, now tagged 033 DoD-10), Name/Persona clauses open "Main info" first, Setups/Notes interactions open their tab (and reopen after navigation), "no X region" queries include hidden elements, archived-page clause also checks the five tabs (033 DoD-11).
- `frontend/tests/app/CharacterScreen.export.test.tsx` — covers DoD-8, DoD-9, DoD-12 — Export/Archive/Restore are icon-only (no text) and in the page header, before the tab list and outside every panel (replaces 030's same-`Group` clause); Export still downloads; Export disabled while the held export is in flight and enabled after; no Export on the draft page.
- `frontend/tests/app/CharacterComposer.test.tsx` — covers DoD-13 — the region and its heading are "New session"; no "Start a session" region/heading.
- `frontend/tests/app/App.test.tsx` — covers DoD-4, DoD-6, DoD-7, DoD-13 — the 015/018 region-order clause is now per-tab-panel placement with one notes listing and none added by opening Notes; Name clauses open "Main info" first; composer region constant is "New session"; Notes presence on arrival queried with `hidden: true`.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 [manual/live, no test], DoD-15 [manual/live, no test]
- Out-of-scope breakage to route: `frontend/tests/app/sessionFirstReply.test.tsx:457` queries region "Start a session" and is not in step 001's Test files, so it will fail once the composer heading becomes "New session" (DoD-13).
- `frontend/tests/app/sessionFirstReply.test.tsx` — covers DoD-13 — follow-up: composer region lookup (~line 457) renamed "Start a session" to "New session"; this test renders `CharacterComposer` directly (no tabbed page), so no tab-dependent lookups needed changing. Resolves the out-of-scope note above.
- Rework (TEST fault, DoD-7): the "033 step 001" Main-info clause in `frontend/tests/app/CharacterScreen.test.tsx` now asserts the "Aria Vale" heading right after the name update and before the persona update (its stateless backend answers the persona PATCH with the pre-rename name); the sent-PATCH assertions are unchanged.

### Step 002 — tests (2026-10-08)
- `frontend/tests/app/memoLevelState.discard.test.ts` — covers DoD-1 — `discardNewNote` closes an open not-saving draft (typed, empty, failed) with no request; leaves an in-flight draft unchanged; no-op with no draft.
- `frontend/tests/app/MemoLevelGroup.headerAdd.test.tsx` — covers DoD-2, DoD-3, DoD-4, DoD-5, DoD-6, DoD-7, DoD-8, DoD-9 — `headerAdd` on: one icon-only "New note" in the heading's row before the list, none while loading/failed; '+' opens an empty autofocused draft first with "Save new note"/"Cancel new note", '+' disabled; Cancel = no request, '+' re-enabled; Save = exactly one character-level POST, new note first, draft closed; blank/untouched Save = no request, draft closed; focus leaving = no request, draft kept; in-flight Save/Cancel disabled, failure inside the draft, text kept. `headerAdd` omitted/false: labelled "New note" after the list, no Save/Cancel, blur-save still POSTs.
- `frontend/tests/app/CharacterNotesSection.test.tsx` — covers DoD-2, DoD-3, DoD-4, DoD-5, DoD-6, DoD-7, DoD-8, DoD-10 — new "033 step 002" block: the same header/draft clauses on the section; DoD-10 keyboard drag start in the list layout plus a full keyboard reorder (stacked row rects stubbed on `getBoundingClientRect`; Space, ArrowDown, Space on the first card) sending one `PUT /api/memos/order` with all three ids in the new order. Existing 015 DoD-2 clause amended (Save new note instead of blur); MarkdownEditor stub now passes `autoFocus`; "grid" describe titles renamed to "list".
- `frontend/tests/app/CharacterScreen.test.tsx` — covers DoD-2, DoD-5 — archived-character Notes clause: one icon-only "New note" beside the heading, then "Save new note" (was blur-save) still POSTs with that character's id.
- `frontend/tests/app/App.test.tsx` — no change needed (no assertion on the old "New note" button or the blur-save).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 [manual/live, no test]
- Rework (TEST fault, DoD-10): the keyboard-reorder clause in `frontend/tests/app/CharacterNotesSection.test.tsx` no longer expects an exact `{memo_ids}` body. It now checks for one `PUT /api/memos/order` whose body matches `{scope: "character", scope_id: <C>, memo_ids: [2nd, 1st, 3rd]}`, following the 016 wire contract.

### Step 003 — tests (2026-10-08)
- `frontend/tests/app/SetupCreateForm.test.tsx` — covers DoD-2, DoD-3, DoD-4, DoD-5, DoD-6, DoD-7 — new: the form alone renders an empty Name / Description, icon-only "Save setup" / "Cancel new setup", no dialog, Name focused on mount; Cancel = `onCancel` once, no request; Save = one POST `/api/characters/<id>/setups` with name (+ description), `onCreated` once with the server row; in-flight Save/Cancel disabled, "Could not create the setup." inside the form, values kept, no `onCreated`, no notification; Save disabled for blank / whitespace-only name, enabled with a name; a remount starts empty.
- `frontend/tests/app/SetupsSection.test.tsx` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-6, DoD-7, DoD-8 — new "033 step 003" blocks: header = heading, icon-only '+' "New setup", switch (in that order, one Group), no labelled "New setup"; '+' opens the inline form (empty fields, Save/Cancel, no dialog, '+' disabled) above the table / "No setups yet." / "Could not load setups" / the loader; Cancel closes with no request; Save from an empty list lists the row and closes; in-flight disable + failure inside the open form; submit guard; fresh draft after cancel and after save; Edit still opens the prefilled "Edit setup" modal with no inline form. Existing 010 clauses rewritten for the inline form: DoD-2 (sole region button is the '+'), DoD-4 (create via inline Save, form closes, row first, no refetch), DoD-6 ×2 (failure inside the form; Cancel then reopen empty); DoD-2/5/7/8 titles also tagged 033 step 003 DoD-8.
- `frontend/tests/app/CharacterScreen.test.tsx` — covers DoD-4 — archived-character Setups clause (010 DoD-11) now creates through '+' and the inline "Save setup" (no dialog), and checks the row is listed and the form closed.
- `frontend/tests/app/App.test.tsx` — no change needed (no assertion on "New setup" or the setup create modal).
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 [manual/live, no test]

### Step 004 — tests (2026-10-08)
- `frontend/tests/app/CharacterComposer.setup.test.tsx` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5, DoD-6, DoD-7, DoD-8, DoD-9 — new: `startSessionWithMessage` with a setup id posts once with `{ opening_message, setup_id }` (string id) and returns the served row; omitted / null id sends exactly `{ opening_message }`; 409 `setup_archived` still rejects with that ApiError code. Composer: "Setup" select inside the "New session" region reads "No setup" on open; options = "No setup" first then working setups by name, archived not offered; "No setup" send (also after choosing then un-choosing) posts no `setup_id` and navigates; chosen setup send posts one `{ opening_message, setup_id }` and lands on `/sessions/<id>`; failed setups load shows "Could not load setups to choose from." and "No setup" send still succeeds (line absent on success); opening the dropdown re-requests setups and offers a setup added since mount; refused send (409 `setup_archived`) notifies once, keeps the draft, no navigation; select disabled while a held send is in flight; no kind switch.
- `frontend/tests/app/CharacterComposer.test.tsx` — covers DoD-2, DoD-9 — existing 018 clauses adjusted for the mount-time setups GET (stubs answer it with `{ setups: [] }`; `seen`/`sentBody` look at the sessions POST only; paste clause asserts no non-listing request); the 018 DoD-7 absence clause no longer forbids a Setup select and now asserts it reads "No setup" (D10).
- `frontend/tests/app/App.test.tsx` — covers DoD-2, DoD-4, DoD-9 — 018 DoD-8 composer clause amended: Setup select reads "No setup" (was: no Setup choice), send still posts exactly `{ opening_message }` (keys checked).
- `frontend/tests/app/CharacterScreen.test.tsx` — covers DoD-2 — new "033 step 004" clause: the Sessions tab's "New session" composer shows a "Setup" select reading "No setup"; existing setups-listing assertions were already "at least once", no other change needed.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 [manual/live, no test]

### Step 005 — tests (2026-10-08)
- `frontend/tests/app/SessionsSection.test.tsx` — covers DoD-1, DoD-2, DoD-4, DoD-5 — 011's start / Setup-select / choices-reload / failed-start clauses (011 DoD-4..DoD-8) retired; mount requests exactly the sessions listing (no setups GET, no create); no Setup select, "No setup", "Start session" or "Could not load setups to choose from." (also with failing setups and after the archived toggle); no session POST on mount, retry, toggle or archive; header = heading + switch + icon-only "Import session" sharing a container above the table / "No sessions yet."; archive/restore/toggle/empty-line clauses tagged DoD-5, plus row menu still offers Archive + Export.
- `frontend/tests/app/SessionsSection.import.test.tsx` — covers DoD-1, DoD-2, DoD-3 — "beside Start session" clause rewritten (in the header beside the switch, no Start session); name clause now icon-only (accessible name exactly "Import session", no text), upload icon kept; new held-import clauses: disabled while the import POST is held, re-enabled after success (session listed) and after a refusal; full import via the icon button lists the session and raises the coverage caveat.
- `frontend/tests/app/CharacterScreen.test.tsx` — covers DoD-1, DoD-2, DoD-4 — 011 DoD-13 archived-character clause now starts through the "New session" composer (POST body `{ opening_message }`, no Start session button, no create before Send); new "033 step 005" block: Sessions region has no Setup select / Start session / setups-failed line, one "Import session" button, and opening the page sends no session POST.
- `frontend/tests/app/App.test.tsx` — covers DoD-1, DoD-4 — 011 DoD-15 clause starts via the composer's Send (no Start session button, no create before Send, exactly one create, none message-less) and keeps the tree/no-second-listing assertions.
- `frontend/tests/app/sessionsSectionState.test.ts` — compile follow-up for D9 (no new DoD) — removed the `loadSetupChoices`, `selectSetup`, `startSessionFromSection` blocks, their fixtures/helpers, and `setups`/`setupsStatus`/`selectedSetupId`/`startStatus`/`startError` from the snapshot and assertions; remaining 011 clauses unchanged.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 [manual/live, no test]

## Notes & Issues

_populated by the coder when worth saying_

### Step 005 — skeleton: test file outside the step's Test files breaks on the intended removals
- **Step**: 005.sessions-list-header.
- **What intent asked for**: "`startSessionFromSection` and the selected-setup field are removed. The setup-choices field and its load are removed unless something else in the section still reads them" (nothing else does).
- **What conflicts**: `frontend/tests/app/sessionsSectionState.test.ts` imports `loadSetupChoices`, `selectSetup`, `startSessionFromSection` and asserts on `setups` / `setupsStatus` / `selectedSetupId` / `startStatus` / `startError`, and `tsconfig.json` includes `tests/`. It is not in step 005's Test files, so neither the test-coder nor the coder may edit it; once the coder removes the symbols, `npm run typecheck` fails.
- **Suggested resolutions**: (a) add `frontend/tests/app/sessionsSectionState.test.ts` to step 005's Test files so the test-coder deletes the start / setup-choice / selectSetup blocks and the removed fields from its snapshots (preferred; small, mechanical); (b) keep the state symbols and remove only the UI (contradicts the intent, leaves dead exports).

## Ultra phase

- orient: done 2026-10-08
- harvest: done — docs/.cache/ultra/033.character-page-tabs/harvest.md (2 reports)
- skeleton: done — steps 001, 002, 003, 004, 005
- tests: done — steps 001, 002, 003, 004, 005   (plan amended via planner: 005 Test files += sessionsSectionState.test.ts; 001 Test files += sessionFirstReply.test.tsx)
- red-gate: PASS (run 1)
- code: done — steps 001, 002, 003, 004, 005
- verify: FAIL (run 1) — 001 TEST, 002 TEST
- verify: PASS (run 2)
