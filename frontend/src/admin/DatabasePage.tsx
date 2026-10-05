// The Database page: the route-level mount (creates the store with a useState
// initializer), and the observer page that renders a store it receives as a prop.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import {
  Alert,
  Badge,
  Box,
  Button,
  Center,
  Container,
  FileButton,
  Group,
  Loader,
  Menu,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { IconDots, IconDownload, IconUpload } from "@tabler/icons-react";
import { ConfirmModal } from "../shared/ConfirmModal";
import { IconButton } from "../shared/IconButton";
import {
  type DriftTableRow,
  DatabasePageState,
  cancelImport,
  chooseImportFile,
  createDriftTable,
  differencesSummaryOf,
  exportDatabase,
  formatByteSize,
  importDatabase,
  isLossySync,
  loadDriftReport,
  statusBadgeOf,
  syncConsequenceOf,
  syncDriftTable,
} from "./databasePageState";

/** The repo's "main" icon metrics (`IconButton`'s `ICON_SIZES.main` / `ICON_STROKE`). */
const ICON_SIZE = 18;
const ICON_STROKE = 1.5;

/** The import file picker's filter: the extension and the media type, in that order. */
const IMPORT_ACCEPT = ".json,application/json";

/** The replace confirm's pinned text (`008.context.md`), used verbatim and nowhere else. */
const IMPORT_CONFIRM_TITLE = "Replace the whole database?";
const IMPORT_CONFIRM_CONSEQUENCE =
  "Everything in this instance, including your own account, is replaced by the contents of " +
  "the file, and you will be signed out.";
const IMPORT_CONFIRM_LABEL = "Replace database";

function ignoreRejection(): void {
  // Free functions never reject; this only keeps a surprise from going unhandled.
}

function openedByMenuTarget(): void {
  // The overflow trigger's click bubbles to the Menu.Target wrapper, which toggles the menu.
}

export type DatabasePageProps = {
  state: DatabasePageState;
};

export const DatabasePage = observer(function DatabasePage(
  props: DatabasePageProps,
): React.JSX.Element {
  const { state } = props;
  // The lossy-Sync confirm: open flag and the row awaiting confirmation.
  const [syncConfirmOpen, setSyncConfirmOpen] = useState(false);
  const [syncTarget, setSyncTarget] = useState<DriftTableRow | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  // Mantine fills this with `FileButton`'s own reset, which clears the hidden input's value so
  // the same file can be chosen again after a cancel or a failure.
  const importResetRef = useRef<() => void>(null);

  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadDriftReport(state, controller.signal).catch(ignoreRejection);
    return () => {
      controller.abort();
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    };
  }, [state]);

  const currentSignal = (): AbortSignal | undefined => controllerRef.current?.signal;

  // No notification and no confirm: an export is not lossy, and a failure renders inline.
  const startExport = (): void => {
    void exportDatabase(state, currentSignal()).catch(ignoreRejection);
  };

  /**
   * A chosen import file. It calls `chooseImportFile(state, file)` — which opens the replace
   * confirm, since the confirm is open exactly while `state.importFile` is non-null — and then
   * `importResetRef.current?.()` so the same file can be chosen again. An empty choice does
   * nothing. No request is made here: only the confirm's Replace button starts one.
   */
  const onImportFileChosen = (file: File | null): void => {
    if (file === null) {
      return;
    }
    chooseImportFile(state, file);
    importResetRef.current?.();
  };

  /** The replace confirm's Cancel: `cancelImport(state)` and nothing else. No request. */
  const cancelImportChoice = (): void => {
    cancelImport(state);
  };

  /**
   * The replace confirm's Replace: `importDatabase(state, currentSignal())`, which posts the
   * chosen file and navigates to `/login` on success. No notification, ever.
   */
  const confirmImport = (): void => {
    void importDatabase(state, currentSignal()).catch(ignoreRejection);
  };

  const createTable = (row: DriftTableRow): void => {
    void createDriftTable(state, row.table_name, currentSignal()).catch(ignoreRejection);
  };

  const runSync = (tableName: string): void => {
    void syncDriftTable(state, tableName, currentSignal()).catch(ignoreRejection);
  };

  const requestSync = (row: DriftTableRow): void => {
    if (isLossySync(row)) {
      setSyncTarget(row);
      setSyncConfirmOpen(true);
      return;
    }
    runSync(row.table_name);
  };

  const cancelSync = (): void => {
    setSyncConfirmOpen(false);
    setSyncTarget(null);
  };

  const confirmSync = (): void => {
    const target = syncTarget;
    setSyncConfirmOpen(false);
    setSyncTarget(null);
    if (target === null) {
      return;
    }
    runSync(target.table_name);
  };

  return (
    <Container size="lg" py="md">
      <Group justify="space-between" align="center" mb="md" wrap="nowrap">
        <Title order={2}>Database</Title>
        {/* The page-level action group. 031 adds Import beside Export; `fast/002` adds Rebuild
            index to this same group and is not rendered here, not even as a placeholder. */}
        <Group gap="sm" wrap="nowrap">
          <Button
            variant="default"
            leftSection={<IconDownload size={ICON_SIZE} stroke={ICON_STROKE} />}
            loading={state.exportStatus === "exporting"}
            onClick={startExport}
          >
            Export
          </Button>
          {/* `FileButton` renders its own hidden file input — unnamed, and the only input on
              this page — then the Button its render prop returns. Nothing portals this row. */}
          <FileButton
            accept={IMPORT_ACCEPT}
            resetRef={importResetRef}
            onChange={onImportFileChosen}
          >
            {(fileButtonProps) => (
              <Button
                {...fileButtonProps}
                variant="default"
                leftSection={<IconUpload size={ICON_SIZE} stroke={ICON_STROKE} />}
                loading={state.importStatus === "importing"}
              >
                Import
              </Button>
            )}
          </FileButton>
        </Group>
      </Group>

      {state.errorMessage !== null && (
        <Alert color="red" mb="md">
          {state.errorMessage}
        </Alert>
      )}

      {/* An export failure, inline and above the table — never also a notification. */}
      {state.exportErrorMessage !== null && (
        <Alert color="red" mb="md">
          {state.exportErrorMessage}
        </Alert>
      )}

      {/* An import failure, in its own slot so it never overwrites the drift or export message.
          Inline and never also a notification (031 008 DoD-5, DoD-6). */}
      {state.importErrorMessage !== null && (
        <Alert color="red" mb="md">
          {state.importErrorMessage}
        </Alert>
      )}

      {/* The one permitted report about an export: the saved file's size. Nothing about its
          content, no table name, no row count (US-078). */}
      {state.exportSizeBytes !== null && (
        <Text size="sm" c="dimmed" mb="md">
          {`Export downloaded — ${formatByteSize(state.exportSizeBytes)}`}
        </Text>
      )}

      {state.status !== "ready" ? (
        <Center py="xl">
          <Loader />
        </Center>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Table</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Columns</Table.Th>
              <Table.Th>Indexes</Table.Th>
              <Table.Th w={60} />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {state.rows.map((row) => {
              const badge = statusBadgeOf(row);
              const summary = differencesSummaryOf(row);
              const applying = state.applyingTable === row.table_name;
              return (
                <Table.Tr key={row.table_name}>
                  <Table.Td>{row.table_name}</Table.Td>
                  <Table.Td>
                    <Badge variant="light" color={badge.color}>
                      {badge.label}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{summary.columns}</Table.Td>
                  <Table.Td>{summary.indexes}</Table.Td>
                  <Table.Td w={60}>
                    {row.status !== "in_sync" && (
                      <Menu position="bottom-end" withinPortal>
                        <Menu.Target>
                          <Box component="span" display="inline-block">
                            <IconButton
                              icon={IconDots}
                              label={`Actions for ${row.table_name}`}
                              onClick={openedByMenuTarget}
                              disabled={applying}
                            />
                          </Box>
                        </Menu.Target>
                        <Menu.Dropdown>
                          {row.status === "missing" && (
                            <Menu.Item onClick={() => createTable(row)}>Create</Menu.Item>
                          )}
                          {row.status === "drifted" && (
                            <Menu.Item onClick={() => requestSync(row)}>Sync</Menu.Item>
                          )}
                        </Menu.Dropdown>
                      </Menu>
                    )}
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      )}

      <ConfirmModal
        opened={syncConfirmOpen && syncTarget !== null}
        title={syncTarget !== null ? `Sync ${syncTarget.table_name}?` : "Sync table?"}
        consequence={syncTarget !== null ? syncConsequenceOf(syncTarget) : ""}
        confirmLabel="Sync"
        confirmColor="red"
        loading={syncTarget !== null && state.applyingTable === syncTarget.table_name}
        onCancel={cancelSync}
        onConfirm={confirmSync}
      />

      {/* The replace confirm. Its openness is derived from the chosen file, so the store keeps
          no open flag. The text names the action only — no count, no table, nothing from the
          file (R5, US-078). */}
      <ConfirmModal
        opened={state.importFile !== null}
        title={IMPORT_CONFIRM_TITLE}
        consequence={IMPORT_CONFIRM_CONSEQUENCE}
        confirmLabel={IMPORT_CONFIRM_LABEL}
        confirmColor="red"
        loading={state.importStatus === "importing"}
        onCancel={cancelImportChoice}
        onConfirm={confirmImport}
      />
    </Container>
  );
});

/** The `/database` route element: owns the page store for the route's lifetime. */
export function DatabaseRoute(): React.JSX.Element {
  const [state] = useState(() => new DatabasePageState());
  return <DatabasePage state={state} />;
}
