// The "Setups" section on 009's character screen (feature 010, step 006, D1 / D2 / D4 /
// D11 / D12 / D13). It owns one `SetupsSectionState` (004) created with `useState`, loads
// the listing on mount and on every `showArchived` change, renders the header, the list and
// the row actions, and conditionally mounts `SetupModal` (005). It holds no business logic
// of its own: every state change goes through 004's free functions, and what renders is
// what the server returned (never optimistic).
//
// The accessible names and texts below are the contract the tests bind to; the JSX that
// produces them is the coder's.
//
//   region          a `<section>` with `aria-labelledby` pointing at the heading's id, so
//                   its role is `region` and its accessible name is "Setups". First
//                   labelled region in the repo — a plan decision, not an oversight
//                   (`006.context.md`); `aria-label` is deliberately not used.
//   heading         "Setups" at `<Title order={3}>` — the same level as the screen's
//                   "Sessions" heading (`CharacterScreen.tsx`), so the two read as siblings.
//   header button   "New setup", a shared `IconButton` (`IconPlus`, 033 D7). It sets
//                   `createOpen` to true and is disabled while the inline form is open.
//   header switch   a Mantine `Switch` labelled "Show archived setups" (D4) — deliberately
//                   *not* the tree's "Show archived", because both are on screen at once.
//                   `checked={state.showArchived}`, `onChange` calls `setShowArchived` and
//                   nothing else: the reload is the effect's job, and calling `loadSetups`
//                   here too would double the request.
//   "idle"/"loading"  a Mantine `Loader`.
//   "failed"        the text "Could not load setups" and a "Retry" button re-running
//                   `loadSetups` (D12 — inline, never a notification).
//   "ready", empty  the single line "No setups yet." and nothing else. No prompt to create
//                   one: a setup is optional (R2, D13).
//   "ready", rows   a Mantine `Table`, one row per entry of `state.setups`, in state order.
//   a row           the setup's `name`, `c="dimmed"` when `isSetupArchived(setup)` (the
//                   repo's only dimming treatment) next to a `Badge` reading exactly
//                   "Archived"; and a trailing overflow control, the row's only icon-only
//                   control: `IconButton` with `icon={IconDots}`,
//                   `label={`Actions for ${setup.name}`}`, `sizeVariant="inline"` and
//                   `disabled` while `state.pendingId === setup.id`.
//   the row menu    a Mantine `Menu` (`position="bottom-end" withinPortal`) whose items are
//                   "Edit" (`IconEdit`, sets `editTarget` to that row), then "Archive"
//                   (`IconArchive`, `archiveRow`) for a working row or "Restore"
//                   (`IconArchiveOff`, `restoreRow`) for an archived one. Text labels with
//                   the icon as `leftSection` at the "inline" metrics `size={16}
//                   stroke={1.5}`. No confirm on either (D4, non-destructive).
//   the row error   `state.error`, when non-null, in an inline `Alert` inside the region (D12).
//
// `IconButton` does not forward refs, so it cannot be `Menu.Target`'s child directly. The
// sanctioned wrapper is the admin precedent (`src/admin/UsersPage.tsx:152-161`):
// `<Box component="span" display="inline-block">` inside `Menu.Target`, with the documented
// no-op `onClick` on the `IconButton` (the click bubbles to the wrapper, which toggles the
// menu). A bare `ActionIcon` is forbidden (`ui-conventions.md`). The trigger's accessible
// name stays "Actions for <name>".
//
// What is open is component-local `useState` — `createOpen: boolean` and
// `editTarget: Setup | null` — never MobX (`ui-conventions.md`, D2). Create is the inline
// `SetupCreateForm` (033 D7), mounted above the list only while `createOpen`; edit is
// `SetupModal`, mounted only while `editTarget` is set. Each is conditionally mounted, so its
// draft is fresh per open; on success the returned row is applied with `applySetup` and then
// the form / modal closes.
//
// No notification is raised anywhere and `shared/notifyFailure` is not imported: 010 adds no
// call site (D12).
import type * as React from "react";
import { useEffect, useId, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import {
  Alert,
  Badge,
  Box,
  Button,
  Group,
  Loader,
  Menu,
  Stack,
  Switch,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { IconArchive, IconArchiveOff, IconDots, IconEdit, IconPlus } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import { SetupCreateForm } from "./SetupCreateForm";
import { SetupModal } from "./SetupModal";
import { isSetupArchived } from "./setupsApi";
import type { Setup } from "./setupsApi";
import {
  SetupsSectionState,
  applySetup,
  archiveRow,
  loadSetups,
  restoreRow,
  setShowArchived,
} from "./setupsSectionState";

/** The "inline" metric, for the icons inside the row menu's items. */
const MENU_ICON_SIZE = 16;
const ICON_STROKE = 1.5;

function openedByMenuTarget(): void {
  // The overflow trigger's click bubbles to the Menu.Target wrapper, which toggles the menu.
}

export type SetupsSectionProps = {
  /** The character whose setups this section lists. A string, never parsed. */
  characterId: string;
};

export const SetupsSection = observer(function SetupsSection(
  props: SetupsSectionProps,
): React.JSX.Element {
  const { characterId } = props;
  // Created once, never with `useMemo`; `CharacterScreen` keys the section by the character
  // id, so a different character builds fresh section state (D11).
  const [state] = useState(() => new SetupsSectionState(characterId));
  // What is open is component-local state, never MobX (D2, 033 D7).
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Setup | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  // The heading's id: `aria-labelledby` on the `<section>` names the region "Setups".
  const headingId = useId();

  // Read during render, so the `observer` re-renders — and the effect re-runs — when the
  // switch flips. `loadSetups` reads the same field for the query, so the two agree.
  const showArchived = state.showArchived;

  // One load on mount and one per `showArchived` change (D4). The previous run is aborted by
  // the cleanup, so a slow first response can never overwrite a later one, and an unmount
  // leaves nothing in flight.
  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadSetups(state, controller.signal);
    return () => {
      controller.abort();
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    };
  }, [state, showArchived]);

  const retry = (): void => {
    void loadSetups(state, controllerRef.current?.signal);
  };

  const closeModal = (): void => {
    setEditTarget(null);
  };

  // D2: apply the server's row first, then close — what renders is what came back.
  const onSaved = (saved: Setup): void => {
    applySetup(state, saved);
    closeModal();
  };

  // 033 D7: the inline create form follows the same order — apply, then unmount.
  const onCreated = (created: Setup): void => {
    applySetup(state, created);
    setCreateOpen(false);
  };

  const renderRow = (setup: Setup): React.JSX.Element => {
    const archived = isSetupArchived(setup);
    return (
      <Table.Tr key={setup.id}>
        <Table.Td>
          <Group gap="xs" wrap="nowrap">
            <Text c={archived ? "dimmed" : undefined}>{setup.name}</Text>
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
                  label={`Actions for ${setup.name}`}
                  sizeVariant="inline"
                  onClick={openedByMenuTarget}
                  disabled={state.pendingId === setup.id}
                />
              </Box>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item
                leftSection={<IconEdit size={MENU_ICON_SIZE} stroke={ICON_STROKE} />}
                onClick={() => {
                  setEditTarget(setup);
                }}
              >
                Edit
              </Menu.Item>
              {/* D4: no confirm on either — archiving destroys nothing. */}
              {archived ? (
                <Menu.Item
                  leftSection={<IconArchiveOff size={MENU_ICON_SIZE} stroke={ICON_STROKE} />}
                  onClick={() => {
                    void restoreRow(state, setup.id);
                  }}
                >
                  Restore
                </Menu.Item>
              ) : (
                <Menu.Item
                  leftSection={<IconArchive size={MENU_ICON_SIZE} stroke={ICON_STROKE} />}
                  onClick={() => {
                    void archiveRow(state, setup.id);
                  }}
                >
                  Archive
                </Menu.Item>
              )}
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
      // D12: the load failure is inline — nothing is notified.
      return (
        <Stack gap="xs" align="flex-start">
          <Text size="sm">Could not load setups</Text>
          <Button size="xs" variant="default" onClick={retry}>
            Retry
          </Button>
        </Stack>
      );
    }

    // R2 / D13: one neutral line, and nothing inviting the user to create a setup.
    if (state.setups.length === 0) {
      return <Text size="sm">No setups yet.</Text>;
    }

    // State order, verbatim ids, one row per setup and no header row.
    return (
      <Table striped highlightOnHover>
        <Table.Tbody>{state.setups.map(renderRow)}</Table.Tbody>
      </Table>
    );
  };

  return (
    <section aria-labelledby={headingId}>
      <Stack gap="xs">
        <Group gap="sm">
          <Title order={3} id={headingId}>
            Setups
          </Title>
          <IconButton
            icon={IconPlus}
            label="New setup"
            disabled={createOpen}
            onClick={() => {
              setCreateOpen(true);
            }}
          />
          {/* D4: session-only, never persisted. The reload is the effect's job — calling
              `loadSetups` here too would double the request. */}
          <Switch
            size="xs"
            label="Show archived setups"
            checked={showArchived}
            onChange={(event) => {
              setShowArchived(state, event.currentTarget.checked);
            }}
          />
        </Group>
        {/* 033 D7: the inline create form, above the list output. */}
        {createOpen && (
          <SetupCreateForm
            characterId={characterId}
            onCreated={onCreated}
            onCancel={() => {
              setCreateOpen(false);
            }}
          />
        )}
        {/* D12: the row-action failure, inline inside the region. */}
        {state.error !== null && <Alert color="red">{state.error}</Alert>}
        {renderList()}
      </Stack>
      {/* Edit only; mounted only while a row is targeted, so the draft is fresh per open (D2). */}
      {editTarget !== null && (
        <SetupModal
          characterId={characterId}
          setup={editTarget}
          onClose={closeModal}
          onSaved={onSaved}
        />
      )}
    </section>
  );
});
