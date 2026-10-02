// The workspace tree's header and character level (009 step 008, D4, D11, D13): it lives
// inside 008's expanded nav column, above the `UserMenu` footer, and is fed the one
// workspace `CharactersState` (004) that `App` creates — never a state of its own, so a
// create / save / archive / restore on the character screen shows here without a refetch.
// It sits outside `<Routes>`, so the current character is read from the location
// (`useMatch("/characters/:id")`), not from `useParams`. Ids are strings throughout.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import { Link, useMatch, useNavigate } from "react-router-dom";
import { Badge, Box, Button, Group, Loader, NavLink, Stack, Switch, Text } from "@mantine/core";
import { IconChevronDown, IconPlus, IconSearch } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import type { IconButtonProps } from "../shared/IconButton";
import { isArchived } from "./charactersApi";
import type { CharactersState } from "./charactersState";
import { loadCharacters, setShowArchived } from "./charactersState";
import { formatSessionStart } from "./sessionLabel";
import type { SessionsState } from "./sessionsState";
import { loadSessions, orderCharactersByUse, sessionsOfCharacter } from "./sessionsState";
import {
  readCollapsedCharacters,
  toggleCollapsedCharacter,
  writeCollapsedCharacters,
} from "./treeCollapse";
import type { LayoutStorage } from "./workspaceLayout";

/** The header's two in-entry destinations (D13); the same pair the rail offers. */
const SEARCH_PATH = "/search";
const NEW_CHARACTER_PATH = "/characters/new";

/**
 * The static segment `/characters/new` also matches the `:id` pattern; it is the create
 * form, not a row, so it never marks one active.
 */
const NEW_CHARACTER_SEGMENT = "new";

/**
 * The props `IconButton` hands to its `icon` component — nothing more (011 step 006, D7).
 * `sizeVariant` "chevron" means `size` 14 and `stroke` 1.5 arrive here.
 */
export type TreeChevronProps = {
  size?: number | string;
  stroke?: number;
};

/** The rotation the collapsed glyph carries — the one place the angle is written. */
const COLLAPSED_ROTATION = "rotate(-90deg)";

/**
 * The expanded glyph: `IconChevronDown` as it comes, with `size` / `stroke` forwarded.
 *
 * Typed as `IconButtonProps["icon"]` at the declaration, so assignability to `IconButton`'s
 * `icon` prop is proved here rather than at the call site.
 */
export const TreeChevronExpanded: IconButtonProps["icon"] = (props: TreeChevronProps) => (
  <IconChevronDown size={props.size} stroke={props.stroke} />
);

/**
 * The collapsed glyph: the **same** `IconChevronDown`, rotated `-90°` by a style on the
 * wrapper (`ui-conventions.md`'s "one chevron, rotated, not two icons"; `IconButton` has no
 * rotation prop and is deliberately not widened).
 */
export const TreeChevronCollapsed: IconButtonProps["icon"] = (props: TreeChevronProps) => (
  <IconChevronDown
    size={props.size}
    stroke={props.stroke}
    style={{ transform: COLLAPSED_ROTATION }}
  />
);

/**
 * Picks a row's chevron glyph from its collapsed state. Returns one of the two module-level
 * components, so the identity is stable across renders and the icon never remounts.
 */
export function treeChevronIcon(collapsed: boolean): IconButtonProps["icon"] {
  return collapsed ? TreeChevronCollapsed : TreeChevronExpanded;
}

export type CharacterTreeProps = {
  /** The one workspace characters state `App` creates (D11); read and reloaded, not owned. */
  characters: CharactersState;
  /**
   * The one workspace sessions state `App` creates (011 D15): the working sessions of every
   * character, for the session level. Loaded on mount by this component and read, never
   * owned, and never reloaded by the "Show archived" switch (011 D16).
   */
  sessions: SessionsState;
  /**
   * The persisted-layout storage, or `null` when none is available — the storage the
   * collapsed-characters record reads and writes under its own key (011 D7).
   */
  storage: LayoutStorage | null;
};

/**
 * The tree: a header carrying "Search", "New character" and the "Show archived" switch
 * (D13 — no chevron, no session rows), and below it the character level, which renders a
 * loader while loading, "Could not load characters" plus "Retry" on failure (inline, no
 * notification — D12), and otherwise a "Characters" list with one router link per
 * character in state order. Archived rows are dimmed and badged "Archived"; the row
 * matching the current `/characters/:id` is active and carries `aria-current="page"`.
 *
 * 011 step 006 adds the session level on top of that: the rows are ordered by newest
 * session use (D6); a character that has at least one working session carries a chevron
 * before its link (D7) and, while expanded, a nested "Sessions of <name>" list of
 * `/sessions/<id>` links labelled with the start time plus the setup label (D16). The
 * sessions load is its own effect — the "Show archived" switch never reloads it — and its
 * failure is one inline line plus "Retry", again with nothing notified (D18).
 */
export const CharacterTree = observer(function CharacterTree(
  props: CharacterTreeProps,
): React.JSX.Element {
  const { characters, sessions, storage } = props;
  const navigate = useNavigate();
  const controllerRef = useRef<AbortController | null>(null);
  const sessionsControllerRef = useRef<AbortController | null>(null);

  // D7: the collapsed set is component-local view state, seeded once from its own persisted
  // record. The tree remounts whenever the column expands, so the read re-runs then — which
  // is exactly why the set is persisted rather than kept in a store.
  const [collapsed, setCollapsed] = useState<string[]>(() => readCollapsedCharacters(storage));

  // Read during render, so the `observer` re-renders — and the effect re-runs — when the
  // flag flips. `loadCharacters` reads the same field for the query, so the two agree.
  const showArchived = characters.showArchived;

  // Read during render too, so the `observer` re-renders when the sessions load settles.
  // There is deliberately no sessions loader: the characters show at once and the session
  // rows appear when they arrive (D16).
  const sessionsFailed = sessions.status === "failed";

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

  // 011 D16: a **separate** effect, loaded once on mount and with no `showArchived`
  // dependency — folding it into the characters effect would refetch every session on every
  // flip of the switch, and the workspace list is the working list either way (D5).
  useEffect(() => {
    const controller = new AbortController();
    sessionsControllerRef.current = controller;
    void loadSessions(sessions, controller.signal);
    return () => {
      controller.abort();
      if (sessionsControllerRef.current === controller) {
        sessionsControllerRef.current = null;
      }
    };
  }, [sessions]);

  // Outside `<Routes>`: the current row comes from the location, and only from a real id.
  const match = useMatch("/characters/:id");
  const matchedId = match?.params.id ?? null;
  const currentId = matchedId === NEW_CHARACTER_SEGMENT ? null : matchedId;

  // The active session row, read from the location the same way (011 D16).
  const sessionMatch = useMatch("/sessions/:id");
  const currentSessionId = sessionMatch?.params.id ?? null;

  const retry = (): void => {
    void loadCharacters(characters, controllerRef.current?.signal);
  };

  const retrySessions = (): void => {
    void loadSessions(sessions, sessionsControllerRef.current?.signal);
  };

  // One press: the next set, the local state, and the record — in that order (D7).
  const toggleCollapsed = (characterId: string): void => {
    const next = toggleCollapsedCharacter(collapsed, characterId);
    setCollapsed(next);
    writeCollapsedCharacters(storage, next);
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

    // Ready: D6's order (which falls back to the state's own while the sessions are still
    // loading, failed or empty), verbatim ids, no placeholder when the list is empty.
    const ordered = orderCharactersByUse(characters.characters, sessions.sessions);
    return (
      <Box
        component="ul"
        aria-label="Characters"
        m={0}
        p={0}
        style={{ listStyle: "none" }}
      >
        {ordered.map((character) => {
          const archived = isArchived(character);
          const active = character.id === currentId;
          // D16: the working sessions the workspace state holds for this character, in the
          // order the server sent them (last use first). A failed load shows none.
          const own = sessionsFailed ? [] : sessionsOfCharacter(sessions.sessions, character.id);
          const hasSessions = own.length > 0;
          const rowCollapsed = collapsed.includes(character.id);
          return (
            <Box component="li" key={character.id}>
              <Group gap="xs" wrap="nowrap">
                {/* D7: no sessions, no chevron — a control for an action that does not
                    currently exist is absent, not inert. The label carries the state. */}
                {hasSessions && (
                  <IconButton
                    icon={treeChevronIcon(rowCollapsed)}
                    label={`${rowCollapsed ? "Expand" : "Collapse"} ${character.name}`}
                    sizeVariant="chevron"
                    onClick={() => {
                      toggleCollapsed(character.id);
                    }}
                  />
                )}
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
              {hasSessions && !rowCollapsed && (
                <Box
                  component="ul"
                  aria-label={`Sessions of ${character.name}`}
                  m={0}
                  p={0}
                  pl="md"
                  style={{ listStyle: "none" }}
                >
                  {own.map((session) => {
                    const sessionActive = session.id === currentSessionId;
                    return (
                      <Box component="li" key={session.id}>
                        <NavLink
                          component={Link}
                          to={`/sessions/${session.id}`}
                          label={formatSessionStart(session.created_at)}
                          // US-088: the setup's name as dimmed small text beside the start
                          // time, and nothing at all where it would be when there is none.
                          description={session.setup_name ?? undefined}
                          active={sessionActive}
                          aria-current={sessionActive ? "page" : undefined}
                        />
                      </Box>
                    );
                  })}
                </Box>
              )}
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
      {/* D18: the sessions failure is inline here, beside the character level, which keeps
          rendering; nothing is notified and there is no sessions loader. */}
      {sessionsFailed && (
        <Stack gap="xs" align="flex-start" px="xs">
          <Text size="sm">Could not load sessions</Text>
          <Button size="xs" variant="default" onClick={retrySessions}>
            Retry
          </Button>
        </Stack>
      )}
      {renderLevel()}
    </Stack>
  );
});
