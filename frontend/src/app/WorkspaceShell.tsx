// The workspace frame (008 context.md D3, D4, D10, D11): the `.app` grid element with
// exactly two children — the left `nav` column, which renders either the expanded column
// or the 48px rail, and the `main` centre column holding the active route's content. Owns
// the one `ShellState` for the shell (`useState(() => createShellState(storage))`, never
// `useMemo`) and reads the observable fields off it, so it is an `observer`. The signed-in
// user and the layout storage both arrive as props — this component never reaches for
// `window.localStorage` and never puts the user in React context.
import type * as React from "react";
import { useEffect, useState } from "react";
import { observer } from "mobx-react-lite";
import { useLocation, useNavigate } from "react-router-dom";
import { Box, Group, Stack } from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { IconChevronLeft, IconMenu2, IconPlus, IconSearch } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import type { CurrentUser } from "../shared/currentUser";
import type { LayoutStorage } from "./workspaceLayout";
import {
  NARROW_VIEWPORT_QUERY,
  closeOverlay,
  collapseTree,
  createShellState,
  expandTree,
  shellClassName,
  showsRail,
} from "./shellState";
import { UserMenu } from "./UserMenu";
import { CharacterTree } from "./CharacterTree";
import type { CharactersState } from "./charactersState";
import type { SessionsState } from "./sessionsState";

/**
 * Both columns carry the body background as a Mantine style prop, so the `.app` element's
 * line-coloured background shows only through the grid's `1px` gap (the divider).
 */
const COLUMN_BG = "var(--mantine-color-body)";

/** In-entry router destinations the rail offers (D4). */
const SEARCH_PATH = "/search";
const NEW_CHARACTER_PATH = "/characters/new";

export type WorkspaceShellProps = {
  /** The signed-in identity, passed straight down to `UserMenu` in both column states. */
  user: CurrentUser;
  /** The persisted-layout storage, or `null` when none is available (005 supplies it). */
  storage: LayoutStorage | null;
  /**
   * The one workspace characters state `App` creates (009 D11); fed to `CharacterTree`, and
   * (031 007) on to `UserMenu` in both column states so an import can reload the list.
   */
  characters: CharactersState;
  /**
   * The one workspace sessions state `App` creates (011 D15); passed straight to
   * `CharacterTree` with `storage`, and (031 007) on to `UserMenu` in both column states,
   * whose "Import…" item reloads it after an import.
   */
  sessions: SessionsState;
  /** The centre column's content — the active route's element. */
  children: React.ReactNode;
};

/**
 * The grid element (class `shellClassName(state, narrow)`), the "Workspace navigation"
 * nav column (rail or expanded column, `UserMenu` as its footer in both) and the `main`
 * centre column. Narrow comes from `useMediaQuery(NARROW_VIEWPORT_QUERY, …)` with
 * `getInitialValueInEffect: false`; the overlay closes on any in-entry location change and
 * whenever narrow changes value.
 */
export const WorkspaceShell = observer(function WorkspaceShell(
  props: WorkspaceShellProps,
): React.JSX.Element {
  const { user, storage, characters, sessions, children } = props;
  const [shell] = useState(() => createShellState(storage));
  const navigate = useNavigate();
  const location = useLocation();

  // `getInitialValueInEffect: false` so the very first render already reads `matchMedia`;
  // deferring it renders the wide layout for one frame after a reload at narrow width.
  // The hook's return is `boolean | undefined`, and 002's functions take a `boolean`.
  const narrow =
    useMediaQuery(NARROW_VIEWPORT_QUERY, false, { getInitialValueInEffect: false }) ?? false;

  // D11 (b): any change of the in-entry route dismisses the overlay.
  useEffect(() => {
    closeOverlay(shell);
  }, [shell, location.key]);

  // D11: crossing the threshold in either direction dismisses it too, so a stale open flag
  // can never reappear on the way back.
  useEffect(() => {
    closeOverlay(shell);
  }, [shell, narrow]);

  return (
    <div className={shellClassName(shell, narrow)}>
      <Box
        component="nav"
        aria-label="Workspace navigation"
        className="app-nav"
        bg={COLUMN_BG}
      >
        {showsRail(shell, narrow) ? (
          <Stack h="100%" gap="xs" p="xs" align="center">
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
            <IconButton
              icon={IconMenu2}
              label="Expand tree"
              onClick={() => {
                expandTree(shell, narrow, storage);
              }}
            />
            <Box mt="auto" w="100%">
              <UserMenu
                user={user}
                compact
                charactersState={characters}
                sessionsState={sessions}
              />
            </Box>
          </Stack>
        ) : (
          <Stack h="100%" gap="xs" p="xs">
            <Group justify="flex-end" gap="xs" wrap="nowrap">
              <IconButton
                icon={IconChevronLeft}
                label="Collapse tree"
                onClick={() => {
                  collapseTree(shell, narrow, storage);
                }}
              />
            </Group>
            {/* The tree's header, character level and (011 step 006) session level. */}
            <Box flex={1}>
              <CharacterTree characters={characters} sessions={sessions} storage={storage} />
            </Box>
            <Box w="100%">
              <UserMenu
                user={user}
                compact={false}
                charactersState={characters}
                sessionsState={sessions}
              />
            </Box>
          </Stack>
        )}
      </Box>
      <Box component="main" className="app-main" bg={COLUMN_BG}>
        {children}
      </Box>
    </div>
  );
});
