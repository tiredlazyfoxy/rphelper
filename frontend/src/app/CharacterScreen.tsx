// The centre column of the two character routes (009 step 007): `/characters/new` (new
// mode) and `/characters/:id` (existing mode). The screen holds no business logic of its
// own — it creates one `CharacterScreenState` (006) with `useState`, renders its fields,
// and calls 006's free functions. The workspace `CharactersState` (004, D11) is created
// once in `App` and passed down so a create/save/archive/restore applies to the tree.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import { runInAction } from "mobx";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Badge,
  Button,
  Center,
  Container,
  Group,
  Loader,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { IconArchive, IconArchiveOff, IconDeviceFloppy, IconPlus } from "@tabler/icons-react";

import { MarkdownEditor } from "../shared/MarkdownEditor";
import { isArchived } from "./charactersApi";
import type { CharactersState } from "./charactersState";
import {
  CharacterScreenState,
  canSubmit,
  isNewCharacter,
  loadCharacter,
  submitArchive,
  submitCreate,
  submitRestore,
  submitSave,
} from "./characterScreenState";
import { SetupsSection } from "./SetupsSection";
import { SessionsSection } from "./SessionsSection";
import { CharacterNotesSection } from "./CharacterNotesSection";
import type { SessionsState } from "./sessionsState";

/** The repo's "main" icon metrics (`IconButton`'s `ICON_SIZES.main` / `ICON_STROKE`). */
const ICON_SIZE = 18;
const ICON_STROKE = 1.5;

export type CharacterScreenProps = {
  /** The one workspace characters state `App` creates (D11); mutations apply into it. */
  characters: CharactersState;
  /** The `:id` route parameter verbatim, or `null` for new mode. Never parsed. */
  characterId: string | null;
  /**
   * The one workspace sessions state `App` creates (011 D15), handed to the Sessions
   * section so starting or archiving a session updates the tree with no refetch. Required
   * in both modes even though new mode renders no section: one prop, no optional branch.
   */
  sessions: SessionsState;
};

/**
 * The character screen. New mode renders "New character" with Name, Persona and Create;
 * existing mode loads on mount and renders loading / not-found / failed / ready, where
 * ready carries the saved name heading, the Archived badge, Name, Persona, Save,
 * Archive-or-Restore, 010's "Setups" section and 011's "Sessions" section. Failures render
 * inline (D12).
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

  // Existing mode loads on mount; the controller aborts on unmount so a late response
  // writes nothing. New mode makes no request until Create (D1).
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

  const character = state.character;
  const archived = character !== null && isArchived(character);
  const submitting = state.submitStatus === "submitting";

  const retry = (): void => {
    void loadCharacter(state, controllerRef.current?.signal);
  };

  // D1: `replace`, so Back does not return to an empty form whose Create would duplicate.
  // The id is the server's string, used exactly as received.
  const onCreated = (createdId: string): void => {
    void navigate(`/characters/${createdId}`, { replace: true });
  };

  const onCreate = (): void => {
    void submitCreate(state, characters, onCreated);
  };

  const onSave = (): void => {
    void submitSave(state, characters);
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

  /** The two draft fields, identical in both modes. The writes are MobX actions. */
  const renderFields = (): React.JSX.Element => (
    <>
      <TextInput
        label="Name"
        value={state.name}
        onChange={(event) => {
          const value = event.currentTarget.value;
          runInAction(() => {
            state.name = value;
          });
        }}
      />
      <MarkdownEditor
        label="Persona"
        value={state.sheet}
        onChange={(markdown) => {
          runInAction(() => {
            state.sheet = markdown;
          });
        }}
        readOnly={submitting}
      />
    </>
  );

  if (isNewCharacter(state)) {
    return (
      <Container size="md" py="md">
        <Stack gap="md">
          <Title order={2}>New character</Title>
          {renderError()}
          {renderFields()}
          <Group>
            {/* `canSubmit` is already false while a submit is in flight. */}
            <Button
              leftSection={<IconPlus size={ICON_SIZE} stroke={ICON_STROKE} />}
              disabled={!canSubmit(state)}
              onClick={onCreate}
            >
              Create
            </Button>
          </Group>
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

  return (
    <Container size="md" py="md">
      <Stack gap="md">
        <Group gap="sm">
          {/* The saved name, not the draft: the heading follows the server's row. */}
          <Title order={2}>{character === null ? "" : character.name}</Title>
          {archived && (
            <Badge color="gray" variant="light">
              Archived
            </Badge>
          )}
        </Group>
        {renderError()}
        {renderFields()}
        <Group>
          <Button
            leftSection={<IconDeviceFloppy size={ICON_SIZE} stroke={ICON_STROKE} />}
            disabled={!canSubmit(state)}
            onClick={onSave}
          >
            Save
          </Button>
          {/* D4: no confirm — archiving destroys nothing. */}
          {archived ? (
            <Button
              variant="default"
              leftSection={<IconArchiveOff size={ICON_SIZE} stroke={ICON_STROKE} />}
              disabled={submitting}
              onClick={onRestore}
            >
              Restore
            </Button>
          ) : (
            <Button
              variant="default"
              leftSection={<IconArchive size={ICON_SIZE} stroke={ICON_STROKE} />}
              disabled={submitting}
              onClick={onArchive}
            >
              Archive
            </Button>
          )}
        </Group>
        {/* 010 D1: the interim "Setups" section, between the persona/actions block and
            the Sessions heading, and only here — new mode, loading, not-found and failed
            render none. Keyed by the character id (010 D11) so a different character
            builds fresh section state even if this screen is ever rendered unkeyed. The
            id is the route's string, used verbatim; the null test is only strictness
            (existing mode returned above when it was null). */}
        {state.characterId !== null && (
          <SetupsSection key={state.characterId} characterId={state.characterId} />
        )}
        {/* 011 D1 / step 008: the real Sessions section, in the place 009's heading-only
            one held — after 010's Setups section and only here, so new mode, loading,
            not-found and failed render none. Its own "Sessions" heading (same
            `Title order={3}` level) takes the old heading's place, so 010's "Setups
            precedes the Sessions heading" stays true. Keyed by the character id (D15) so a
            different character builds fresh section state; the id is the route's string,
            used verbatim, and the null test is only strictness. */}
        {state.characterId !== null && (
          <SessionsSection
            key={state.characterId}
            characterId={state.characterId}
            sessions={sessions}
          />
        )}
        {/* 015 D1 / step 009: the character-level "Notes" section, after Sessions and only
            here. Keyed by the character id so a different character builds fresh state. */}
        {state.characterId !== null && (
          <CharacterNotesSection key={state.characterId} characterId={state.characterId} />
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
