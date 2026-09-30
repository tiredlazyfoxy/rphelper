// The Database page: the route-level mount (creates the store with a useState
// initializer), and the observer page that renders a store it receives as a prop.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import { Alert, Badge, Box, Center, Container, Loader, Menu, Table, Title } from "@mantine/core";
import { IconDots } from "@tabler/icons-react";
import { ConfirmModal } from "../shared/ConfirmModal";
import { IconButton } from "../shared/IconButton";
import {
  type DriftTableRow,
  DatabasePageState,
  createDriftTable,
  differencesSummaryOf,
  isLossySync,
  loadDriftReport,
  statusBadgeOf,
  syncConsequenceOf,
  syncDriftTable,
} from "./databasePageState";

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
      <Title order={2} mb="md">
        Database
      </Title>

      {state.errorMessage !== null && (
        <Alert color="red" mb="md">
          {state.errorMessage}
        </Alert>
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
    </Container>
  );
});

/** The `/database` route element: owns the page store for the route's lifetime. */
export function DatabaseRoute(): React.JSX.Element {
  const [state] = useState(() => new DatabasePageState());
  return <DatabasePage state={state} />;
}
