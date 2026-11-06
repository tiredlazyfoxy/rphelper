# app

<!-- agent-ready:start -->

The `app` Vite entry — the roleplayer's workspace: the shell and tree, character and session screens, the session stream with its composer, notes, search and settings. Components render; MobX data classes (observable fields only) plus free-function effects in `*State.ts` hold the logic; `*Api.ts` modules are the wire surface.

## Glossary

**Files:**
- `App.tsx` — the entry's application: `WorkspaceShell` around the flat route table.
- `AppBoot.tsx` — the boot gate: nothing of the shell renders until `GET /api/me` resolves.
- `AppBootScreens.tsx` — the two full-page boot screens (not-ready and failure).
- `AssistantBody.tsx` — assistant message body: think segments as `ThinkingBlock`s, answer segments painted.
- `CharacterComposer.tsx` — the character page's "New session" composer (with optional setup choice) that starts a session.
- `CharacterConfigSection.tsx` — the character page's "Configuration" region (model, system prompt, tool switches).
- `CharacterNotesSection.tsx` — the character page's character-level "Notes" region.
- `CharacterScreen.tsx` — centre column of `/characters/new` and `/characters/:id`.
- `CharacterTree.tsx` — the workspace tree's header and character / session level in the nav column.
- `Composer.tsx` — the session composer: send, settle, settle preview, partner-paste filing, discard, stop.
- `ComposerCore.tsx` — the shared presentational composer core (resizable text area, in-box Send, Ctrl/Cmd+Enter).
- `DiscussionGroup.tsx` — the collapsed, lazily loaded read-only Discussion group under a settled entry.
- `KindSwitch.tsx` — the "Partner" / "My turn" entry-kind switch.
- `LiveMessage.tsx` — the read-only live assistant reply (with live tool blocks) while streaming.
- `MemoChainSection.tsx` — the session screen's "Notes" region: one `MemoLevelGroup` per chain level.
- `MemoLevelGroup.tsx` — one level's notes as a titled region: markdown editors, flag toggles, add, and opt-in drag reorder.
- `MessageBody.tsx` — the one message renderer with "plain", "decision" and "painted" variants.
- `NoteWallLayout.tsx` — the session screen's stream column plus the pinnable / closable note wall.
- `SearchScreen.tsx` — the my-search results page at `/search`.
- `SessionConfigBar.tsx` — the session header's configuration bar (model picker, tool badges).
- `SessionConfigModal.tsx` — the session configuration modal.
- `SessionNameEditor.tsx` — the inline "Session name" input that renames a session in place, editing a host-owned `SessionRenameState`.
- `SessionScreen.tsx` — centre column of `/sessions/:id`: header plus the session stream.
- `SessionStream.tsx` — the session stream: owns one `StreamState` and renders record, ruler, kind switch, zone and composer.
- `SessionsSection.tsx` — the character page's "Sessions" section (list, archive / restore, export, import).
- `SettingsScreen.tsx` — the `/settings` screen: languages form and the user's own notes.
- `SetupCreateForm.tsx` — the Setups section's inline create form.
- `SetupModal.tsx` — the setup create / edit modal.
- `SetupsSection.tsx` — the character page's "Setups" section.
- `StreamRecord.tsx` — the settled record: one item per entry with its actions (edit, copy, translate, delete) and Discussion group; the translate flicker shows a pending indicator while a translation is in flight, keeping that entry's actions revealed.
- `ThinkingBlock.tsx` — the collapsible "Thinking" block.
- `ToolBlock.tsx` — the collapsible tool-call block.
- `UserMenu.tsx` — the user menu at the foot of the nav column (settings, admin link, export / import, logout).
- `WorkspaceShell.tsx` — the workspace frame: nav column / rail and the centre column.
- `ZoneList.tsx` — the current zone's messages, each with in-place edit and delete (role-aware, with Regenerate); the roleplayer's own message bodies render in a muted tone so they read apart from the assistant's.
- `appBootState.ts` — boot gate state: classification of a failed `GET /api/me` and its effects.
- `characterComposerState.ts` — the character page composer's state and send effect.
- `characterConfigState.ts` — the character configuration block's state and effects.
- `characterScreenState.ts` — the character screen's state (mode, load, draft, submit).
- `charactersApi.ts` — the `/api/characters` wire surface.
- `charactersState.ts` — the one workspace characters list, its load and upsert.
- `composerHeights.ts` — the persisted per-composer text-area heights record.
- `configurationApi.ts` — the configuration wire surface (models, settings, resolved configuration).
- `copyOut.ts` — copy-out: the one place that writes the clipboard (plain text, insecure-origin fallback).
- `exportDownloads.ts` — the shared export-download effect and path builders.
- `firstReply.ts` — the router `location.state` marker for "session just seeded from the character page".
- `importUploads.ts` — the two roleplayer import effects.
- `index.html` — the `app` entry document.
- `logout.ts` — the logout effect.
- `main.tsx` — entry module: mounts the `app` document.
- `memoChainState.ts` — the session's memo chain state and its load.
- `memoDnd.ts` — the notes' shared drag sensors and announcements.
- `memoLevelState.ts` — one level's notes state and its effects.
- `memoReach.ts` — pure derivation of a note's reach and its one-line statement.
- `memoReorder.ts` — the note wall's drop decision and drop effect.
- `memosApi.ts` — the memos wire surface.
- `noteWallState.ts` — the note wall's state, derivations and actions.
- `parens.ts` — the pure `(( ))` rules (classify, segment, strip).
- `pasteCost.ts` — the pure enormous-paste token estimate.
- `plainText.ts` — pure markdown-to-plain-text stripper for copy-out.
- `searchApi.ts` — the my-search wire surface.
- `searchState.ts` — the results page's state and helpers.
- `sessionConfigDraft.ts` — the session configuration modal's draft.
- `sessionConfigState.ts` — the session configuration state shared by the header bar and Send gate.
- `sessionLabel.ts` — the session display-label module: `sessionLabel` (the stored name, else the local start date), `formatLocalDate`, `formatLocalDateTime`.
- `sessionRenameState.ts` — in-place session rename state, one per host (tree, session header): `SessionRenameState` plus `beginRename` / `cancelRename` / `commitRename`.
- `sessionScreenState.ts` — the session screen's state and load.
- `sessionsApi.ts` — the sessions wire surface (list, read, start, `renameSession`, archive / restore).
- `sessionsSectionState.ts` — the Sessions section's state and effects.
- `sessionsState.ts` — the one workspace sessions list for the tree, ordered by last use (`applySession` upserts a session into it).
- `settingsState.ts` — the settings languages form state.
- `setupDraft.ts` — the setup modal's draft.
- `setupsApi.ts` — the setups wire surface.
- `setupsSectionState.ts` — the Setups section's state.
- `shellState.ts` — the workspace shell's state, derivations and effects.
- `streamApi.ts` — the stream wire surface (messages, settle / re-open, compose, edit, `deleteMessage`).
- `streamState.ts` — the session stream's state: derivations (`canSend`, `isStreaming`, …) and effects (send, compose, settle, re-open, edit, `deleteEntry`, `deleteZoneMessage`); a failed send whose text the zone already holds clears the draft, so the retry regenerates instead of re-sending the text.
- `thinking.ts` — the pure `<think>` segment parser.
- `translationApi.ts` — the translation wire surface.
- `translationState.ts` — the per-row partner translation flicker state.
- `treeCollapse.ts` — the persisted collapsed-characters record.
- `workspaceLayout.ts` — the persisted workspace-layout record.

See also: docs/architecture/frontend-structure.md, docs/architecture/session-stream.md, docs/architecture/workspace-shell.md

<!-- agent-ready:end -->

## Conventions

- The delete icons are disabled on `state.busy || isStreaming(state)`, because compose never sets `busy` and `composeHandle` is not observable; this mirrors `canSend` / `showsRegenerate` (fast/014).
- A session is named on screen only through `sessionLabel` (`sessionLabel.ts`) — never by formatting `created_at` or reading `name` directly at a call site (DEC-034-9).
