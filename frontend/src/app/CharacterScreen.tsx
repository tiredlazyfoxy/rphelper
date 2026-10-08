// The centre column of the two character routes (009 step 007, rebuilt by 018 step 009):
// `/characters/new` (the draft page, 018 D6) and `/characters/:id` (the character page,
// 018 D7 / D10). The screen holds no business logic of its own — it creates one
// `CharacterScreenState` (009 006, 018 008) with `useState`, renders its fields, and calls
// its free functions. The workspace `CharactersState` (004, D11) is created once in `App`
// and passed down so a create/save/archive/restore applies to the tree.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import { runInAction } from "mobx";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Badge,
  Box,
  Button,
  Center,
  Container,
  Divider,
  Group,
  Loader,
  Stack,
  Tabs,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { IconArchive, IconArchiveOff, IconDownload } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import { MarkdownEditor } from "../shared/MarkdownEditor";
import { isArchived } from "./charactersApi";
import type { CharactersState } from "./charactersState";
import {
  CharacterScreenState,
  commitName,
  commitPersona,
  flushCharacterEdits,
  isNewCharacter,
  loadCharacter,
  submitArchive,
  submitCreate,
  submitRestore,
} from "./characterScreenState";
import { characterExportPath, runExport } from "./exportDownloads";
import { SetupsSection } from "./SetupsSection";
import { SessionsSection } from "./SessionsSection";
import { CharacterNotesSection } from "./CharacterNotesSection";
import { CharacterConfigSection } from "./CharacterConfigSection";
import { CharacterComposer } from "./CharacterComposer";
import type { SessionsState } from "./sessionsState";

/** 033 D4: the Main info persona editor's minimum content height, in pixels. */
const PERSONA_MIN_HEIGHT = 360;

export type CharacterScreenProps = {
  /** The one workspace characters state `App` creates (D11); mutations apply into it. */
  characters: CharactersState;
  /** The `:id` route parameter verbatim, or `null` for new mode. Never parsed. */
  characterId: string | null;
  /**
   * The one workspace sessions state `App` creates (011 D15), handed to the Sessions
   * section and the page composer so starting a session updates the tree with no
   * refetch. Required in both modes even though the draft renders no section.
   */
  sessions: SessionsState;
};

/**
 * The character screen. New mode is the draft page: "New character", a "Draft" badge,
 * the marker line, Name and Persona, creating on the first committed non-blank name
 * (018 D6). Existing mode loads on mount and renders loading / not-found / failed / ready,
 * where ready carries the header (saved name, Archived badge, icon-only Archive-or-Restore
 * and Export, 033 D3), then five tabs (033 D1): Sessions (composer, divider, sessions
 * list), Main info (Name and Persona, saved on focus loss, 018 D7), Configuration, Notes,
 * Setups. Pending edits are flushed on unmount. Failures render inline (D12).
 */
export const CharacterScreen = observer(function CharacterScreen(
  props: CharacterScreenProps,
): React.JSX.Element {
  const { characters, characterId, sessions } = props;
  // Created once, never with `useMemo`; the route keys this component by the id, so a
  // different character mounts a fresh screen rather than reusing this draft.
  const [state] = useState(() => new CharacterScreenState(characterId));
  const navigate = useNavigate();
  const controllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(false);

  // Existing mode loads on mount; the controller aborts on unmount so a late response
  // writes nothing. New mode makes no request on mount (018 D6).
  useEffect(() => {
    if (isNewCharacter(state)) {
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadCharacter(state, controller.signal);
    return () => {
      controller.abort();
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    };
  }, [state]);

  // 018 D7 / R10: leaving the page saves pending edits — blur is unreliable when an
  // element leaves the DOM (015 D5). After a create the state is no longer a draft, so the
  // flush on the replace navigation's unmount sends nothing.
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      void flushCharacterEdits(state, characters);
    };
  }, [state, characters]);

  const character = state.character;
  const archived = character !== null && isArchived(character);
  const submitting = state.submitStatus === "submitting";
  // 030 006: the Export button's in-flight flag. Component-local on purpose — an export
  // owns no domain state, so `CharacterScreenState` learns nothing about it.
  const [exporting, setExporting] = useState(false);

  /**
   * 030 006: the Export click. One click goes straight to the request — no confirm, no
   * success text and no notification on success. `runExport` never rejects, so the flag is
   * cleared from a `finally` that runs on a completed download and on a handled failure
   * alike. The id is the screen's, used exactly as the route gave it.
   */
  const onExport = (): void => {
    const exportId = state.characterId;
    if (exportId === null) {
      return;
    }
    setExporting(true);
    void runExport(characterExportPath(exportId)).finally(() => {
      setExporting(false);
    });
  };

  const retry = (): void => {
    void loadCharacter(state, controllerRef.current?.signal);
  };

  // D1 / 018 D6: `replace`, so Back does not return to the draft page. The id is the
  // server's string, used exactly as received; skipped once the screen has unmounted.
  const onCreated = (createdId: string): void => {
    if (!mountedRef.current) {
      return;
    }
    void navigate(`/characters/${createdId}`, { replace: true });
  };

  const onArchive = (): void => {
    void submitArchive(state, characters);
  };

  const onRestore = (): void => {
    void submitRestore(state, characters);
  };

  /** The inline failure (D12): never a notification, and always above the form. */
  const renderError = (): React.JSX.Element | null => {
    if (state.error === null) {
      return null;
    }
    return <Alert color="red">{state.error}</Alert>;
  };

  const onNameChange = (event: React.ChangeEvent<HTMLInputElement>): void => {
    const value = event.currentTarget.value;
    runInAction(() => {
      state.name = value;
    });
  };

  const onSheetChange = (markdown: string): void => {
    runInAction(() => {
      state.sheet = markdown;
    });
  };

  if (isNewCharacter(state)) {
    // The draft page (018 D6): nothing else renders — every section needs an id. The
    // persona rides along with the create; its own focus loss saves nothing here.
    return (
      <Container size="md" py="md">
        <Stack gap="md">
          <Group gap="sm">
            <Title order={2}>New character</Title>
            <Badge color="blue" variant="light">
              Draft
            </Badge>
          </Group>
          <Text c="dimmed">Nothing is saved until you enter a name.</Text>
          {renderError()}
          <TextInput
            label="Name"
            value={state.name}
            onChange={onNameChange}
            onBlur={() => {
              void submitCreate(state, characters, onCreated);
            }}
            readOnly={submitting}
          />
          <MarkdownEditor
            label="Persona"
            value={state.sheet}
            onChange={onSheetChange}
            readOnly={submitting}
          />
        </Stack>
      </Container>
    );
  }

  if (state.status === "loading") {
    return (
      <Container size="md" py="md">
        <Center py="xl">
          <Loader />
        </Center>
      </Container>
    );
  }

  // The 404 is terminal: retrying an id that is not ours cannot start answering.
  if (state.status === "not-found") {
    return (
      <Container size="md" py="md">
        <Text>Character not found</Text>
      </Container>
    );
  }

  if (state.status === "failed") {
    return (
      <Container size="md" py="md">
        <Stack gap="md" align="flex-start">
          <Text>Could not load the character</Text>
          <Button onClick={retry}>Retry</Button>
        </Stack>
      </Container>
    );
  }

  // Existing mode returned above when the id was null; the test is only strictness.
  const id = state.characterId;

  /**
   * The persona editor exposes no blur hook: the wrapper's focus-leave commits only when
   * focus moves outside it, not into the editor's own toolbar (015 `007`).
   */
  const onPersonaBlur = (event: React.FocusEvent<HTMLDivElement>): void => {
    const next = event.relatedTarget;
    if (next instanceof Node && event.currentTarget.contains(next)) {
      return;
    }
    void commitPersona(state, characters);
  };

  return (
    <Container size="md" py="md">
      <Stack gap="md">
        {/* 033 D3: the page header — saved name, the Archived badge and the icon-only
            actions. The draft page returns above, so it offers none of them. */}
        <Group gap="sm" justify="space-between" wrap="nowrap">
          <Group gap="sm">
            {/* The saved name, not the draft: the heading follows the server's row. */}
            <Title order={2}>{character === null ? "" : character.name}</Title>
            {archived && (
              <Badge color="gray" variant="light">
                Archived
              </Badge>
            )}
          </Group>
          <Group gap="xs" wrap="nowrap">
            {/* D4: no confirm — archiving destroys nothing. */}
            {archived ? (
              <IconButton
                icon={IconArchiveOff}
                label="Restore"
                disabled={submitting}
                onClick={onRestore}
              />
            ) : (
              <IconButton
                icon={IconArchive}
                label="Archive"
                disabled={submitting}
                onClick={onArchive}
              />
            )}
            {/* 030 006: rendered under Archive/Restore's condition. No confirm: an export
                is not lossy. Busy is expressed as disabled while the export is in flight. */}
            <IconButton icon={IconDownload} label="Export" disabled={exporting} onClick={onExport} />
          </Group>
        </Group>
        {renderError()}
        {/* 033 D1 / D2: five tabs, Sessions selected on open. The active tab is local
            component state (not in the URL); keyed by the id so another character starts
            on Sessions. `keepMounted` stays at its default, so every section mounts and
            loads once on page open. Each section keeps its own distinct key prefix — a
            shared sibling key made React duplicate the regions on every re-render. */}
        {id !== null && (
          <Tabs key={`tabs-${id}`} defaultValue="sessions">
            <Tabs.List>
              <Tabs.Tab value="sessions">Sessions</Tabs.Tab>
              <Tabs.Tab value="main">Main info</Tabs.Tab>
              <Tabs.Tab value="config">Configuration</Tabs.Tab>
              <Tabs.Tab value="notes">Notes</Tabs.Tab>
              <Tabs.Tab value="setups">Setups</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="sessions" pt="md">
              <Stack gap="md">
                <CharacterComposer key={`composer-${id}`} characterId={id} sessions={sessions} />
                <Divider />
                <SessionsSection key={`sessions-${id}`} characterId={id} sessions={sessions} />
              </Stack>
            </Tabs.Panel>
            <Tabs.Panel value="main" pt="md">
              <Stack gap="md">
                <TextInput
                  label="Name"
                  value={state.name}
                  onChange={onNameChange}
                  onBlur={() => {
                    void commitName(state, characters);
                  }}
                  error={state.nameError}
                />
                <Box onBlur={onPersonaBlur}>
                  <MarkdownEditor
                    label="Persona"
                    value={state.sheet}
                    onChange={onSheetChange}
                    readOnly={submitting}
                    contentMinHeight={PERSONA_MIN_HEIGHT}
                  />
                </Box>
              </Stack>
            </Tabs.Panel>
            <Tabs.Panel value="config" pt="md">
              <CharacterConfigSection key={`config-${id}`} characterId={id} headingOrder={3} />
            </Tabs.Panel>
            <Tabs.Panel value="notes" pt="md">
              <CharacterNotesSection key={`notes-${id}`} characterId={id} />
            </Tabs.Panel>
            <Tabs.Panel value="setups" pt="md">
              <SetupsSection key={`setups-${id}`} characterId={id} />
            </Tabs.Panel>
          </Tabs>
        )}
      </Stack>
    </Container>
  );
});

export type CharacterRouteProps = {
  /** Passed straight through to `CharacterScreen`. */
  characters: CharactersState;
  /** Passed straight through to `CharacterScreen` (011 D15). */
  sessions: SessionsState;
};

/**
 * The `/characters/:id` element: reads the `:id` parameter (a string, used verbatim) and
 * renders `CharacterScreen` for it, keyed by the id so moving between characters builds a
 * fresh screen state rather than reusing the previous character's draft.
 */
export function CharacterRoute(props: CharacterRouteProps): React.JSX.Element {
  const { characters, sessions } = props;
  const params = useParams();
  const characterId = params.id ?? "";

  return (
    <CharacterScreen
      key={characterId}
      characters={characters}
      characterId={characterId}
      sessions={sessions}
    />
  );
}
