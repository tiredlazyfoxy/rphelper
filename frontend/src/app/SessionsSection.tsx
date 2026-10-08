// The "Sessions" section on 009's character screen (feature 011, step 008, D1 / D2 / D5 /
// D15 / D18 / D19). It owns one `SessionsSectionState` (007) created with `useState`, and
// holds no business logic of its own: every state change goes through 007's free functions,
// and what renders is what the server returned (never optimistic).
//
// `SetupsSection.tsx` (010 step 006) is the direct template for every shape here — the
// labelled `<section>`, the header `Group`, the `Alert`, the four list branches, and the
// `Box component="span"` wrapper inside `Menu.Target` (`IconButton` forwards no ref, so a
// bare `ActionIcon` is forbidden; `src/admin/UsersPage.tsx` is the precedent).
//
// The accessible names and texts below are the contract the tests bind to:
//
//   region          a `<section>` with `aria-labelledby` pointing at the heading's id, so
//                   its role is `region` and its accessible name is "Sessions".
//   heading         "Sessions" at `<Title order={3}>` — 010's "Setups" level, and the level
//                   009's heading-only section used, so the two read as siblings.
//   import session  (031 007, 033 D8) a shared `IconButton` "Import session" (`IconUpload`)
//                   in the header beside the switch, inside a Mantine `FileButton` accepting
//                   `.json`: the render-prop's `onClick` feeds the `IconButton`'s `onClick`.
//                   Disabled while the import is in flight (component-local `useState`).
//                   No confirm — an import is additive and destroys nothing. The section
//                   starts no session itself (033 D9): the composer's send is the only create.
//   header switch   a Mantine `Switch` labelled "Show archived sessions" (D5 — distinct from
//                   the tree's "Show archived" and 010's "Show archived setups", because all
//                   three are on screen at once). `onChange` calls `setShowArchived` and
//                   nothing else: the reload is the effect's job, and loading here too would
//                   double the request.
//   the alert       `error`, when non-null, inline inside the region
//                   (D18). No notification anywhere: 011 adds no notification call site
//                   and this module imports no notification helper.
//   the list        idle/loading to a `Loader`; failed to "Could not load sessions" plus a
//                   "Retry" button; ready-and-empty to the neutral line "No sessions yet."
//                   (no prompt to start one); ready-with-rows to a `Table` in state order.
//   a row           a router `Link` to `/sessions/<id>` whose text is the start-time label,
//                   the `setup_name` beside it or nothing at all (US-088.AC-2), dimmed with
//                   a `Badge` reading exactly "Archived" when archived, and one overflow
//                   `Menu` offering "Archive" or "Restore" with no confirm (D5), plus an
//                   "Export" item present in both states (030 006, also with no confirm).
import type * as React from "react";
import { useEffect, useId, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import {
  Alert,
  Badge,
  Box,
  Button,
  FileButton,
  Group,
  Loader,
  Menu,
  Stack,
  Switch,
  Table,
  Text,
  Title,
} from "@mantine/core";
import {
  IconArchive,
  IconArchiveOff,
  IconDots,
  IconDownload,
  IconUpload,
} from "@tabler/icons-react";
import { Link } from "react-router-dom";

import { IconButton } from "../shared/IconButton";
import { runExport, sessionExportPath } from "./exportDownloads";
import { runSessionImport } from "./importUploads";
import { formatSessionStart } from "./sessionLabel";
import { isSessionArchived } from "./sessionsApi";
import type { Session } from "./sessionsApi";
import type { SessionsState } from "./sessionsState";
import {
  SessionsSectionState,
  archiveSectionRow,
  loadSectionSessions,
  restoreSectionRow,
  setShowArchived,
} from "./sessionsSectionState";

/**
 * 031 007: the file types the session import offers. An export is a `.json` document, and
 * both the extension and the media type are listed so a picker on either platform filters.
 */
const IMPORT_ACCEPT = ".json,application/json";

/** The "inline" metric, for the icons inside the row menu's items. */
const MENU_ICON_SIZE = 16;
const ICON_STROKE = 1.5;

function openedByMenuTarget(): void {
  // The overflow trigger's click bubbles to the Menu.Target wrapper, which toggles the menu.
}

export type SessionsSectionProps = {
  /** The character whose sessions this section lists. A string, never parsed. */
  characterId: string;
  /**
   * The one workspace sessions state `App` creates (D15). Passed straight to 007's
   * row-action effects and the import so a mutated row lands in the tree with no refetch.
   */
  sessions: SessionsState;
};

/**
 * The character screen's Sessions section: the header (heading, "Show archived sessions"
 * switch, "Import session" icon button), the table of session rows with their
 * Archive / Restore / Export overflow menu, and the loading / failed / empty branches. Rendered only
 * in existing mode at status `"ready"` and keyed by the character id (D1, D15).
 */
export const SessionsSection = observer(function SessionsSection(
  props: SessionsSectionProps,
): React.JSX.Element {
  const { characterId } = props;
  // Created once, never with `useMemo`; `CharacterScreen` keys the section by the character
  // id, so a different character builds fresh section state (D15).
  const [state] = useState(() => new SessionsSectionState(characterId));
  // The heading's id: `aria-labelledby` on the `<section>` names the region "Sessions".
  const headingId = useId();
  const listControllerRef = useRef<AbortController | null>(null);
  // 031 007: the in-flight flag for the one import control. Component-local, never in the
  // section state — no store owns domain state about an import.
  const [importing, setImporting] = useState(false);
  // Mantine fills this with `FileButton`'s own reset, which clears the hidden input's value
  // so the same file can be chosen a second time.
  const importResetRef = useRef<() => void>(null);

  // Read during render, so the `observer` re-renders — and the effect re-runs — when the
  // switch flips. `loadSectionSessions` reads the same field for the query, so the two agree.
  const showArchived = state.showArchived;

  // One listing load on mount and one per `showArchived` change (D5). The previous run is
  // aborted by the cleanup, so a slow first response can never overwrite a later one, and an
  // unmount leaves nothing in flight.
  useEffect(() => {
    const controller = new AbortController();
    listControllerRef.current = controller;
    void loadSectionSessions(state, controller.signal);
    return () => {
      controller.abort();
      if (listControllerRef.current === controller) {
        listControllerRef.current = null;
      }
    };
  }, [state, showArchived]);

  const retry = (): void => {
    void loadSectionSessions(state, listControllerRef.current?.signal);
  };

  /**
   * 031 007: a chosen session export. It calls `importResetRef.current?.()` so the same file
   * can be chosen again, sets the local in-flight flag, runs `runSessionImport(characterId,
   * file, props.sessions, () => loadSectionSessions(state, listControllerRef.current?.signal))`
   * and clears the flag when that settles. An empty choice does nothing. `runSessionImport`
   * never rejects, so there is nothing to catch, and no confirm stands between the choice and
   * the request.
   */
  const onImportSessionFileChosen = (file: File | null): void => {
    if (file === null) {
      return;
    }
    // Reset straight away, not when the import settles: `FileButton` keeps the chosen file on
    // its hidden input, so until the value is cleared a second pick of the same file fires no
    // `change` and the repeat import would never start (US-136.AC-2).
    importResetRef.current?.();
    setImporting(true);
    void runSessionImport(characterId, file, props.sessions, () =>
      loadSectionSessions(state, listControllerRef.current?.signal),
    ).then(() => {
      // `runSessionImport` never rejects — success and handled failure both land here — so
      // the in-flight state is cleared on one path and there is nothing to catch.
      setImporting(false);
    });
  };

  const renderRow = (session: Session): React.JSX.Element => {
    const archived = isSessionArchived(session);
    const label = formatSessionStart(session.created_at);
    return (
      <Table.Tr key={session.id}>
        <Table.Td>
          <Group gap="xs" wrap="nowrap">
            <Text
              component={Link}
              to={`/sessions/${session.id}`}
              c={archived ? "dimmed" : undefined}
            >
              {label}
            </Text>
            {/* US-088: the setup's name beside the start time, and nothing at all where it
                would be when the session has none. */}
            {session.setup_name !== null && (
              <Text size="sm" c="dimmed">
                {session.setup_name}
              </Text>
            )}
            {archived && (
              <Badge color="gray" variant="light" size="sm">
                Archived
              </Badge>
            )}
          </Group>
        </Table.Td>
        <Table.Td w={60}>
          <Menu position="bottom-end" withinPortal>
            <Menu.Target>
              {/* `IconButton` forwards no ref, so the wrapper is the target (the admin
                  precedent, `src/admin/UsersPage.tsx`); a bare `ActionIcon` is forbidden. */}
              <Box component="span" display="inline-block">
                <IconButton
                  icon={IconDots}
                  label={`Actions for ${label}`}
                  sizeVariant="inline"
                  onClick={openedByMenuTarget}
                  disabled={state.pendingId === session.id}
                />
              </Box>
            </Menu.Target>
            <Menu.Dropdown>
              {/* D5: no confirm on either — archiving destroys nothing. */}
              {archived ? (
                <Menu.Item
                  leftSection={<IconArchiveOff size={MENU_ICON_SIZE} stroke={ICON_STROKE} />}
                  onClick={() => {
                    void restoreSectionRow(state, props.sessions, session.id);
                  }}
                >
                  Restore
                </Menu.Item>
              ) : (
                <Menu.Item
                  leftSection={<IconArchive size={MENU_ICON_SIZE} stroke={ICON_STROKE} />}
                  onClick={() => {
                    void archiveSectionRow(state, props.sessions, session.id);
                  }}
                >
                  Archive
                </Menu.Item>
              )}
              {/* 030 006: present for an active and for an archived row alike. No confirm
                  — an export destroys nothing — and success is the browser's download. */}
              <Menu.Item
                leftSection={<IconDownload size={MENU_ICON_SIZE} stroke={ICON_STROKE} />}
                onClick={() => {
                  // This row's id, used exactly as the server sent it. `runExport` never
                  // rejects, so the bare `void` is the whole handler.
                  void runExport(sessionExportPath(session.id));
                }}
              >
                Export
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Table.Td>
      </Table.Tr>
    );
  };

  const renderList = (): React.JSX.Element => {
    if (state.status === "idle" || state.status === "loading") {
      return (
        <Group justify="center" py="sm">
          <Loader size="sm" />
        </Group>
      );
    }

    if (state.status === "failed") {
      // D18: the load failure is inline — nothing is notified.
      return (
        <Stack gap="xs" align="flex-start">
          <Text size="sm">Could not load sessions</Text>
          <Button size="xs" variant="default" onClick={retry}>
            Retry
          </Button>
        </Stack>
      );
    }

    // D18: one neutral line, and nothing inviting the roleplayer to start their first one.
    if (state.sessions.length === 0) {
      return <Text size="sm">No sessions yet.</Text>;
    }

    // State order, verbatim ids, one row per session and no header row.
    return (
      <Table striped highlightOnHover>
        <Table.Tbody>{state.sessions.map(renderRow)}</Table.Tbody>
      </Table>
    );
  };

  return (
    <section aria-labelledby={headingId}>
      <Stack gap="xs">
        <Group gap="sm">
          <Title order={3} id={headingId}>
            Sessions
          </Title>
          {/* D5: section-only state, never persisted. The reload is the effect's job. */}
          <Switch
            size="xs"
            label="Show archived sessions"
            checked={showArchived}
            onChange={(event) => {
              setShowArchived(state, event.currentTarget.checked);
            }}
          />
          {/* 031 007, 033 D8: beside the switch. `FileButton` renders its own hidden input
              and works here — unlike in a `Menu`, nothing portals or unmounts the header on
              click. `IconButton` forwards no ref, so only the render-prop's `onClick` is
              passed on. */}
          <FileButton
            accept={IMPORT_ACCEPT}
            resetRef={importResetRef}
            onChange={onImportSessionFileChosen}
          >
            {(fileButtonProps) => (
              <IconButton
                icon={IconUpload}
                label="Import session"
                onClick={fileButtonProps.onClick}
                disabled={importing}
              />
            )}
          </FileButton>
        </Group>
        {/* D18: the row-action failure, inline inside the region. */}
        {state.error !== null && <Alert color="red">{state.error}</Alert>}
        {renderList()}
      </Stack>
    </section>
  );
});
