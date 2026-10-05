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
//   header switch   a Mantine `Switch` labelled "Show archived sessions" (D5 — distinct from
//                   the tree's "Show archived" and 010's "Show archived setups", because all
//                   three are on screen at once). `onChange` calls `setShowArchived` and
//                   nothing else: the reload is the effect's job, and loading here too would
//                   double the request.
//   inline start    a "Setup" `Select` ("No setup" first, then the working setups in state
//                   order) plus a labelled "Start session" `Button`, disabled ONLY while the
//                   start is in flight — never because the choices are empty or failed
//                   (R2, US-024.AC-3). No modal: one choice is not a form (D1).
//   import session  (031 007) an "Import session" `Button` (`variant="default"`) in that same
//                   row, beside "Start session": the two session-creating actions read as a
//                   pair, and the row already aligns buttons against the labelled `Select`.
//                   It is wrapped in a Mantine `FileButton` accepting `.json`, and it shows a
//                   loading state from component-local `useState` while the import is in
//                   flight. No confirm — an import is additive and destroys nothing.
//   the alerts      `startError` and `error`, each when non-null, inline inside the region
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
  Select,
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
  IconPlus,
  IconUpload,
} from "@tabler/icons-react";
import { Link, useNavigate } from "react-router-dom";

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
  loadSetupChoices,
  restoreSectionRow,
  selectSetup,
  setShowArchived,
  startSessionFromSection,
} from "./sessionsSectionState";

/**
 * The "No setup" option's fixed value. Mantine's `Select` speaks strings and treats `null`
 * as "nothing selected", which would let the field be emptied, so the neutral choice needs
 * a value of its own. It can never equal a decimal snowflake, and it lives ONLY in this
 * module: it is mapped to `null` before it reaches `selectSetup`, so it never reaches the
 * section state, the API client or the wire (R2, "no sentinel").
 */
const NO_SETUP_VALUE = "none";

/**
 * 031 007: the file types the session import offers. An export is a `.json` document, and
 * both the extension and the media type are listed so a picker on either platform filters.
 */
const IMPORT_ACCEPT = ".json,application/json";

/** The repo's "main" icon metrics (`IconButton`'s `ICON_SIZES.main` / `ICON_STROKE`). */
const ICON_SIZE = 18;
/** The "inline" metric, for the icons inside the row menu's items. */
const MENU_ICON_SIZE = 16;
const ICON_STROKE = 1.5;

function openedByMenuTarget(): void {
  // The overflow trigger's click bubbles to the Menu.Target wrapper, which toggles the menu.
}

export type SessionsSectionProps = {
  /** The character whose sessions this section lists and starts. A string, never parsed. */
  characterId: string;
  /**
   * The one workspace sessions state `App` creates (D15). Passed straight to 007's start
   * and row-action effects so a mutated row lands in the tree with no refetch.
   */
  sessions: SessionsState;
};

/**
 * The character screen's Sessions section: the inline start (the "Setup" select and "Start
 * session"), the "Show archived sessions" switch, the table of session rows with their
 * Archive / Restore overflow menu, and the loading / failed / empty branches. Rendered only
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
  const navigate = useNavigate();
  // One controller per load kind: the two loads are independent, so aborting a choices
  // reload must never cancel the listing (and the other way round).
  const listControllerRef = useRef<AbortController | null>(null);
  const choicesControllerRef = useRef<AbortController | null>(null);
  // 031 007: the in-flight flag for the one import control. Component-local, never in the
  // section state — no store owns domain state about an import.
  const [importing, setImporting] = useState(false);
  // Mantine fills this with `FileButton`'s own reset, which clears the hidden input's value
  // so the same file can be chosen a second time.
  const importResetRef = useRef<() => void>(null);

  // Read during render, so the `observer` re-renders — and the effect re-runs — when the
  // switch flips. `loadSectionSessions` reads the same field for the query, so the two agree.
  const showArchived = state.showArchived;

  /**
   * Starts a choices load with a fresh controller, aborting any in-flight one, so the last
   * opening of the Select is the one that wins. The current options stay rendered while it
   * runs (D19).
   */
  const reloadSetupChoices = (): void => {
    choicesControllerRef.current?.abort();
    const controller = new AbortController();
    choicesControllerRef.current = controller;
    void loadSetupChoices(state, controller.signal);
  };

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

  // The choices: one load on mount, and after that only `onDropdownOpen` (D19) — no second
  // render effect, which would turn every unrelated re-render into a request.
  useEffect(() => {
    reloadSetupChoices();
    return () => {
      choicesControllerRef.current?.abort();
      choicesControllerRef.current = null;
    };
  }, [state]);

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
      // the loading state is cleared on one path and there is nothing to catch.
      setImporting(false);
    });
  };

  const start = (): void => {
    void startSessionFromSection(state, props.sessions, (sessionId) => {
      // D1: a push, not a `replace` — the character page stays a valid place to come back
      // to. The id string goes into the path exactly as it was received.
      navigate(`/sessions/${sessionId}`);
    });
  };

  // "No setup" first, then the working setups' names in state order with their id strings as
  // values (R2: no sentinel row exists — the neutral choice is this module's own value).
  const setupOptions = [
    { value: NO_SETUP_VALUE, label: "No setup" },
    ...state.setups.map((setup) => ({ value: setup.id, label: setup.name })),
  ];

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
        </Group>
        {/* D1: the inline start. One choice is not a form, so there is no modal. */}
        <Stack gap={4}>
          <Group gap="sm" align="flex-end">
            <Select
              label="Setup"
              data={setupOptions}
              // `allowDeselect={false}`: the field can never be emptied, so the displayed
              // value is always either a setup id or this module's "No setup".
              allowDeselect={false}
              value={state.selectedSetupId ?? NO_SETUP_VALUE}
              onChange={(value) => {
                // "No setup" (and a cleared field) is `null` on the wire — no sentinel.
                selectSetup(state, value === null || value === NO_SETUP_VALUE ? null : value);
              }}
              // D19: the choices reload on each open, so a setup just saved in the Setups
              // section above is choosable without a remount.
              onDropdownOpen={reloadSetupChoices}
            />
            <Button
              leftSection={<IconPlus size={ICON_SIZE} stroke={ICON_STROKE} />}
              // Disabled only while the start is in flight: an empty or failed choices load
              // must never block starting with no setup (US-024.AC-3, R2).
              disabled={state.startStatus === "submitting"}
              onClick={start}
            >
              Start session
            </Button>
            {/* 031 007: beside "Start session", because both bring a session into being.
                `FileButton` renders its own hidden input and works here — unlike in a
                `Menu`, nothing portals or unmounts this row on click. */}
            <FileButton
              accept={IMPORT_ACCEPT}
              resetRef={importResetRef}
              onChange={onImportSessionFileChosen}
            >
              {(fileButtonProps) => (
                <Button
                  {...fileButtonProps}
                  variant="default"
                  leftSection={<IconUpload size={ICON_SIZE} stroke={ICON_STROKE} />}
                  loading={importing}
                >
                  Import session
                </Button>
              )}
            </FileButton>
          </Group>
          {/* D18: a silent failure would hide why the list holds only "No setup". No retry,
              and no effect at all on starting (R2, US-024.AC-3). */}
          {state.setupsStatus === "failed" && (
            <Text size="sm" c="dimmed">
              Could not load setups to choose from.
            </Text>
          )}
        </Stack>
        {/* D18: the start failure and the row-action failure, inline inside the region. */}
        {state.startError !== null && <Alert color="red">{state.startError}</Alert>}
        {state.error !== null && <Alert color="red">{state.error}</Alert>}
        {renderList()}
      </Stack>
    </section>
  );
});
