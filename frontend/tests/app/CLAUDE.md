# app

<!-- agent-ready:start -->

Vitest suites for the `app` entry (`src/app/`): one or more modules per component, state module or API client, split by concern where a source file has several features.

## Glossary

**Files:**
- `App.test.tsx` — the in-entry route table.
- `AppBoot.test.tsx` — the boot gate's outcomes.
- `AssistantBody.test.tsx` — the assistant body over the think-segment split.
- `CharacterComposer.setup.test.tsx` — the character page composer's optional setup choice.
- `CharacterComposer.test.tsx` — the character page composer.
- `CharacterConfigSection.test.tsx` — the character page's configuration block.
- `CharacterNotesSection.test.tsx` — the character page's Notes section.
- `CharacterScreen.export.test.tsx` — the character screen's Export button.
- `CharacterScreen.test.tsx` — the character screen and its two routes.
- `CharacterTree.test.tsx` — the tree header and character level.
- `Composer.test.tsx` — the session composer.
- `ComposerCore.keyboard.test.tsx` — Ctrl/Cmd+Enter send in the composer core.
- `ComposerCore.test.tsx` — the shared composer core.
- `ComposerPasteWarning.test.tsx` — the composer's enormous-paste warning.
- `ComposerStop.test.tsx` — Stop in Send's slot while streaming.
- `DiscussionGroup.test.tsx` — the Discussion group on its own.
- `KindSwitch.test.tsx` — the entry-kind switch.
- `LiveMessage.test.tsx` — the live reply beneath the zone rows.
- `MemoChainSection.test.tsx` — the session's Notes section.
- `MemoLevelGroup.headerAdd.test.tsx` — the level group's header add / autosave / toolbar flags.
- `MemoLevelGroup.test.tsx` — the shared level group component.
- `MessageBody.test.tsx` — the message renderer variants.
- `NoteWallLayout.test.tsx` — the session screen's stream column and note wall layout.
- `SearchScreen.test.tsx` — the search results page.
- `SessionConfigBar.test.tsx` — the session header configuration bar.
- `SessionConfigModal.test.tsx` — the session configuration modal.
- `SessionScreen.test.tsx` — the session screen at `/sessions/:id`.
- `SessionStream.test.tsx` — the assembled session stream.
- `SessionStreamCoverage.test.tsx` — the search-coverage banner above the record.
- `SessionStreamTranslation.test.tsx` — the stream's per-mount translation state.
- `SessionsSection.export.test.tsx` — the session row's Export item.
- `SessionsSection.import.test.tsx` — the Sessions section's Import session button.
- `SessionsSection.test.tsx` — the Sessions section.
- `SettingsScreen.test.tsx` — the settings screen.
- `SetupCreateForm.test.tsx` — the inline setup create form.
- `SetupModal.test.tsx` — the setup create / edit modal.
- `SetupsSection.test.tsx` — the Setups section.
- `StreamRecord.test.tsx` — the settled record.
- `StreamRecordActions.test.tsx` — settled-entry actions (edit, copy, delete).
- `StreamRecordDiscussion.test.tsx` — the Discussion group under settled entries.
- `StreamRecordTranslation.test.tsx` — the translate flicker on settled partner entries.
- `StreamRecordTranslationPending.test.tsx` — the translate flicker's pending indicator and the actions group revealed while a translation is pending.
- `ThinkingBlock.test.tsx` — the thinking block.
- `ToolBlock.test.tsx` — the tool-call block.
- `UserMenu.export.test.tsx` — the user menu's Export my data item.
- `UserMenu.import.test.tsx` — the user menu's Import item.
- `UserMenu.test.tsx` — the user menu.
- `WorkspaceShell.test.tsx` — the workspace shell component.
- `ZoneList.test.tsx` — the zone list with in-place edit and delete.
- `ZoneListAssistant.test.tsx` — role-aware zone rows, live-to-persisted transition and Regenerate.
- `ZoneListOwnTextTone.test.tsx` — the muted tone on the roleplayer's own message bodies (zone and Discussion group).
- `appBootState.test.ts` — the boot state module.
- `characterComposerState.test.ts` — the character composer state.
- `characterConfigState.test.ts` — the character configuration state.
- `characterScreenState.test.ts` — the character screen state.
- `charactersApi.test.ts` — the characters API client.
- `charactersState.test.ts` — the workspace characters state.
- `composeSend.test.ts` — Send on "my turn" composes.
- `composerHeights.test.ts` — the persisted composer heights record.
- `configurationApi.test.ts` — the configuration API client.
- `embeddingFailureSurfacing.test.ts` — authoring effects surfacing embedding-failure warnings.
- `entryEffects.test.ts` — settled-entry edit, copy-out and delete effects.
- `entryIsolation.test.ts` — source scans: the `app` entry's isolation from `src/admin` and DOM-free modules.
- `exportDownloads.test.ts` — the export module.
- `importUploads.test.ts` — the import effects.
- `logout.test.ts` — the logout effect.
- `memoChainState.test.ts` — the memo chain state.
- `memoDnd.test.ts` — the shared drag configuration.
- `memoLevelState.discard.test.ts` — memo level state after the removal of the new-note discard.
- `memoLevelState.test.ts` — one level's notes state.
- `memoReach.test.ts` — the reach helper.
- `memoReorder.test.ts` — the drop decision and drop effect.
- `memosApi.test.ts` — the memos API client.
- `noteWallState.test.ts` — the note wall state.
- `parens.test.ts` — the pure `(( ))` module.
- `pasteCost.test.ts` — the paste-size estimate.
- `plainText.test.ts` — the markdown-to-plain-text module.
- `searchApi.test.ts` — the my-search API client.
- `searchLanding.test.tsx` — landing on a session from a search hit (entry scroll / notes open).
- `searchState.test.ts` — the results page state.
- `sessionConfigDraft.test.ts` — the session configuration draft.
- `sessionConfigState.test.ts` — the session configuration state.
- `sessionFirstReply.test.tsx` — first reply after starting from the character page (component / router level).
- `sessionLabel.test.ts` — the start-time label formatter.
- `sessionScreenState.test.ts` — the session screen state.
- `sessionsApi.test.ts` — the sessions API client.
- `sessionsSectionState.test.ts` — the Sessions section state.
- `sessionsState.test.ts` — the workspace sessions state.
- `settingsState.test.ts` — the settings state.
- `setupDraft.test.ts` — the setup draft.
- `setupsApi.test.ts` — the setups API client.
- `setupsSectionState.test.ts` — the Setups section state.
- `shellState.test.ts` — the shell state.
- `streamApi.test.ts` — the stream API client.
- `streamApiDiscussion.test.ts` — the discussion read and client tool fields.
- `streamCompose.test.ts` — the compose effect and settle mid-stream.
- `streamComposeStoredRetry.test.ts` — bug repro: a failed send whose text was already stored must not leave the draft for a duplicate re-send.
- `streamCoverage.test.ts` — the search-coverage flag on the stream state.
- `streamFirstReply.test.ts` — the store-level first-reply compose.
- `streamLiveTools.test.ts` — live tool calls fed by compose frames.
- `streamMutations.test.ts` — the stream's mutation effects (including zone delete).
- `streamRegenerate.test.ts` — regenerate and its derivations.
- `streamState.test.ts` — the stream state: data class, derivations, load and synchronous actions.
- `streamStreaming.test.ts` — the compose call and the streaming state surface.
- `thinking.test.ts` — the think-segment parser.
- `translationApi.test.ts` — the translate call.
- `translationState.test.ts` — the per-row translation state.
- `treeCollapse.test.ts` — the collapsed-characters record.
- `workspaceLayout.test.ts` — the workspace-layout record.

See also: docs/architecture/frontend-structure.md

<!-- agent-ready:end -->
