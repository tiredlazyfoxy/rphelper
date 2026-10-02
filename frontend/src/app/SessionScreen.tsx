// The centre column of `/sessions/:id` (feature 011, step 009, D17): the session's own
// screen, which in 011 is a header plus the line "No entries yet." — entries, the ruler, the
// composer and the zone are 012 / 013's, and the wall is 015 / 016's. The screen holds no
// business logic of its own: it creates one `SessionScreenState` (this step) with `useState`
// and calls that module's one effect. `CharacterScreen.tsx` (009 step 007) is the template.
//
// The session comes from one `GET /api/sessions/{id}` and never from the workspace
// `SessionsState`: that list is the tree's working list, and an archived session reached by
// URL is not in it. Reading never bumps `last_used_at` (D3). The workspace `CharactersState`
// is read ONLY to label the character link — when it does not hold that character the link
// text is the neutral "Character" and no second request is made for a name (D17).
//
// Deliberately absent, per D5 / D17 / D18: any Archive, Restore or "Actions for …" control
// (archiving a session lives on the character screen only), any textbox, any stream, ruler,
// composer, zone or wall, and any notification API import — the failure branch renders its
// one fixed sentence inline with a Retry, and the ready centre holds no button at all.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import { Link, useParams } from "react-router-dom";
import {
  Anchor,
  Badge,
  Button,
  Center,
  Container,
  Group,
  Loader,
  Stack,
  Text,
  Title,
} from "@mantine/core";

import type { CharactersState } from "./charactersState";
import { isSessionArchived } from "./sessionsApi";
import { formatSessionStart } from "./sessionLabel";
import { SessionScreenState, loadSessionScreen } from "./sessionScreenState";

/** The link text when the workspace list does not hold this session's character (D17). */
const UNKNOWN_CHARACTER = "Character";

export type SessionScreenProps = {
  /** The `:id` route parameter verbatim. A string, never parsed. */
  sessionId: string;
  /**
   * The one workspace characters state `App` creates (009 D11), read only — it supplies the
   * character link's text when it already holds that character, and nothing is fetched when
   * it does not (D17). The screen never writes to it.
   */
  characters: CharactersState;
};

/**
 * The session's own screen: the header (character link, start-time heading, setup label and
 * the "Archived" badge) plus "No entries yet.", with the loading, not-found and failed
 * branches. Keyed by the session id by `SessionRoute`, so each session gets fresh state.
 */
export const SessionScreen = observer(function SessionScreen(
  props: SessionScreenProps,
): React.JSX.Element {
  const { characters } = props;
  // Created once, never with `useMemo`; `SessionRoute` keys the screen by the session id, so
  // a different session builds fresh screen state rather than reusing this one.
  const [state] = useState(() => new SessionScreenState(props.sessionId));
  const controllerRef = useRef<AbortController | null>(null);

  // One read on mount; the controller aborts on unmount so a late response writes nothing.
  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadSessionScreen(state, controller.signal);
    return () => {
      controller.abort();
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    };
  }, [state]);

  const retry = (): void => {
    void loadSessionScreen(state, controllerRef.current?.signal);
  };

  // The 404 is terminal: retrying an id that is not ours cannot start answering, so this
  // branch carries no Retry (and nothing anywhere notifies — D18).
  if (state.status === "not-found") {
    return (
      <Container size="md" py="md">
        <Text>Session not found</Text>
      </Container>
    );
  }

  if (state.status === "failed") {
    return (
      <Container size="md" py="md">
        <Stack gap="md" align="flex-start">
          <Text>Could not load the session</Text>
          <Button onClick={retry}>Retry</Button>
        </Stack>
      </Container>
    );
  }

  const session = state.session;
  // "idle" and "loading" both show the loader; so would the impossible ready-without-a-row,
  // which keeps the ready render free of a null branch.
  if (state.status !== "ready" || session === null) {
    return (
      <Container size="md" py="md">
        <Center py="xl">
          <Loader />
        </Center>
      </Container>
    );
  }

  // D17: the name only when the workspace list already holds that character, matched by
  // string equality on the id — never a second request just for a label.
  const character = characters.characters.find((row) => row.id === session.character_id);
  const characterName = character === undefined ? UNKNOWN_CHARACTER : character.name;

  return (
    <Container size="md" py="md">
      <Stack gap="md">
        <Stack gap="xs">
          {/* The link works either way: its target is the session's own `character_id`,
              used verbatim, and only its text depends on the loaded list. */}
          <Anchor component={Link} to={`/characters/${session.character_id}`}>
            {characterName}
          </Anchor>
          <Group gap="sm">
            {/* D4: a session has no title, so its heading is the start-time label, in the
                browser's own zone — the formatter is called with no zone argument. */}
            <Title order={2}>{formatSessionStart(session.created_at)}</Title>
            {/* US-088: the setup's name beside the start time, and nothing at all where it
                would be when the session has none. */}
            {session.setup_name !== null && (
              <Text size="sm" c="dimmed">
                {session.setup_name}
              </Text>
            )}
            {/* D5: an archived session reached by URL says so — and still offers no
                archive or restore control of its own. */}
            {isSessionArchived(session) && (
              <Badge color="gray" variant="light">
                Archived
              </Badge>
            )}
          </Group>
        </Stack>
        {/* 012 / 013 replace this line with the entry stream, the ruler and the zone. */}
        <Text c="dimmed">No entries yet.</Text>
      </Stack>
    </Container>
  );
});

export type SessionRouteProps = {
  /** Passed straight through to `SessionScreen`. */
  characters: CharactersState;
};

/**
 * The `/sessions/:id` element: reads the `:id` parameter (a string, used verbatim — nothing
 * parses it) and renders `SessionScreen` for it, keyed by the id so moving between sessions
 * in-entry builds a fresh screen state and a fresh load rather than showing the previous
 * session's header.
 */
export function SessionRoute(props: SessionRouteProps): React.JSX.Element {
  const { characters } = props;
  const params = useParams();
  const sessionId = params.id ?? "";

  return <SessionScreen key={sessionId} sessionId={sessionId} characters={characters} />;
}
