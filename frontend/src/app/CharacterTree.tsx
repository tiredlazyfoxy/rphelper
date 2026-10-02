// The workspace tree's header and character level (009 step 008, D4, D11, D13): it lives
// inside 008's expanded nav column, above the `UserMenu` footer, and is fed the one
// workspace `CharactersState` (004) that `App` creates — never a state of its own, so a
// create / save / archive / restore on the character screen shows here without a refetch.
// It sits outside `<Routes>`, so the current character is read from the location
// (`useMatch("/characters/:id")`), not from `useParams`. Ids are strings throughout.
import type * as React from "react";
import { useEffect, useRef } from "react";
import { observer } from "mobx-react-lite";
import { Link, useMatch, useNavigate } from "react-router-dom";
import { Badge, Box, Button, Group, Loader, NavLink, Stack, Switch, Text } from "@mantine/core";
import { IconPlus, IconSearch } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import { isArchived } from "./charactersApi";
import type { CharactersState } from "./charactersState";
import { loadCharacters, setShowArchived } from "./charactersState";

/** The header's two in-entry destinations (D13); the same pair the rail offers. */
const SEARCH_PATH = "/search";
const NEW_CHARACTER_PATH = "/characters/new";

/**
 * The static segment `/characters/new` also matches the `:id` pattern; it is the create
 * form, not a row, so it never marks one active.
 */
const NEW_CHARACTER_SEGMENT = "new";

export type CharacterTreeProps = {
  /** The one workspace characters state `App` creates (D11); read and reloaded, not owned. */
  characters: CharactersState;
};

/**
 * The tree: a header carrying "Search", "New character" and the "Show archived" switch
 * (D13 — no chevron, no session rows), and below it the character level, which renders a
 * loader while loading, "Could not load characters" plus "Retry" on failure (inline, no
 * notification — D12), and otherwise a "Characters" list with one router link per
 * character in state order. Archived rows are dimmed and badged "Archived"; the row
 * matching the current `/characters/:id` is active and carries `aria-current="page"`.
 */
export const CharacterTree = observer(function CharacterTree(
  props: CharacterTreeProps,
): React.JSX.Element {
  const { characters } = props;
  const navigate = useNavigate();
  const controllerRef = useRef<AbortController | null>(null);

  // Read during render, so the `observer` re-renders — and the effect re-runs — when the
  // flag flips. `loadCharacters` reads the same field for the query, so the two agree.
  const showArchived = characters.showArchived;

  // One load on mount and one per `showArchived` change (D4). The previous run is aborted
  // by the cleanup, so a slow first response can never overwrite a later one, and an
  // unmount (collapsing the column) leaves nothing in flight.
  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadCharacters(characters, controller.signal);
    return () => {
      controller.abort();
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    };
  }, [characters, showArchived]);

  // Outside `<Routes>`: the current row comes from the location, and only from a real id.
  const match = useMatch("/characters/:id");
  const matchedId = match?.params.id ?? null;
  const currentId = matchedId === NEW_CHARACTER_SEGMENT ? null : matchedId;

  const retry = (): void => {
    void loadCharacters(characters, controllerRef.current?.signal);
  };

  const renderLevel = (): React.JSX.Element => {
    if (characters.status === "idle" || characters.status === "loading") {
      return (
        <Group justify="center" py="sm">
          <Loader size="sm" />
        </Group>
      );
    }

    if (characters.status === "failed") {
      // D12: the tree's failure is inline — nothing is notified.
      return (
        <Stack gap="xs" align="flex-start" px="xs">
          <Text size="sm">Could not load characters</Text>
          <Button size="xs" variant="default" onClick={retry}>
            Retry
          </Button>
        </Stack>
      );
    }

    // Ready: state order, verbatim ids, no placeholder when the list is empty.
    return (
      <Box
        component="ul"
        aria-label="Characters"
        m={0}
        p={0}
        style={{ listStyle: "none" }}
      >
        {characters.characters.map((character) => {
          const archived = isArchived(character);
          const active = character.id === currentId;
          return (
            <Box component="li" key={character.id}>
              <Group gap="xs" wrap="nowrap">
                <NavLink
                  component={Link}
                  to={`/characters/${character.id}`}
                  label={character.name}
                  active={active}
                  aria-current={active ? "page" : undefined}
                  c={archived ? "dimmed" : undefined}
                  flex={1}
                  miw={0}
                />
                {archived && (
                  <Badge color="gray" variant="light" size="sm">
                    Archived
                  </Badge>
                )}
              </Group>
            </Box>
          );
        })}
      </Box>
    );
  };

  return (
    <Stack gap="xs" h="100%">
      <Group gap="xs" wrap="nowrap">
        <IconButton
          icon={IconSearch}
          label="Search"
          onClick={() => {
            void navigate(SEARCH_PATH);
          }}
        />
        <IconButton
          icon={IconPlus}
          label="New character"
          onClick={() => {
            void navigate(NEW_CHARACTER_PATH);
          }}
        />
        {/* D4: session-only, never persisted, and the only caller of `setShowArchived`.
            The reload is the effect's job — toggling here too would double the request. */}
        <Switch
          size="xs"
          label="Show archived"
          checked={showArchived}
          onChange={(event) => {
            setShowArchived(characters, event.currentTarget.checked);
          }}
        />
      </Group>
      {renderLevel()}
    </Stack>
  );
});
