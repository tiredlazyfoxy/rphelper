// The Users page: its own store (useState initializer), the page-level load effect,
// the table, the row overflow menu, the disable confirm and the three account modals.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import { Alert, Badge, Box, Button, Center, Container, Group, Loader, Menu, Table, Title } from "@mantine/core";
import { IconDots } from "@tabler/icons-react";
import { ConfirmModal } from "../shared/ConfirmModal";
import { IconButton } from "../shared/IconButton";
import { ChangeRoleModal } from "./ChangeRoleModal";
import { CreateUserModal } from "./CreateUserModal";
import { SetPasswordModal } from "./SetPasswordModal";
import {
  type AdminUserRow,
  UsersPageState,
  disableUser,
  enableUser,
  loadUsers,
} from "./usersPageState";

const EM_DASH = "—";

function formatLastLogin(value: string | null): string {
  if (value === null || value.length === 0) {
    return EM_DASH;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function ignoreRejection(): void {
  // Free functions never reject; this only keeps a surprise from going unhandled.
}

function openedByMenuTarget(): void {
  // The overflow trigger's click bubbles to the Menu.Target wrapper, which toggles the menu.
}

export const UsersPage = observer(function UsersPage(): React.JSX.Element {
  const [state] = useState(() => new UsersPageState());
  const [disableTarget, setDisableTarget] = useState<AdminUserRow | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [passwordTarget, setPasswordTarget] = useState<AdminUserRow | null>(null);
  const [roleTarget, setRoleTarget] = useState<AdminUserRow | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadUsers(state, controller.signal).catch(ignoreRejection);
    return () => {
      controller.abort();
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    };
  }, [state]);

  const currentSignal = (): AbortSignal | undefined => controllerRef.current?.signal;

  const cancelDisable = (): void => {
    setDisableTarget(null);
  };

  const confirmDisable = (): void => {
    const target = disableTarget;
    setDisableTarget(null);
    if (target === null) {
      return;
    }
    void disableUser(state, target.id, currentSignal()).catch(ignoreRejection);
  };

  const reEnable = (row: AdminUserRow): void => {
    void enableUser(state, row.id, currentSignal()).catch(ignoreRejection);
  };

  const closeCreate = (): void => {
    setCreateOpen(false);
  };

  const onCreated = (): void => {
    setCreateOpen(false);
    void loadUsers(state, currentSignal()).catch(ignoreRejection);
  };

  const closePassword = (): void => {
    setPasswordTarget(null);
  };

  const onPasswordSaved = (): void => {
    setPasswordTarget(null);
    void loadUsers(state, currentSignal()).catch(ignoreRejection);
  };

  const closeRole = (): void => {
    setRoleTarget(null);
  };

  const onRoleSaved = (): void => {
    setRoleTarget(null);
    void loadUsers(state, currentSignal()).catch(ignoreRejection);
  };

  return (
    <Container size="lg" py="md">
      <Group justify="space-between" mb="md">
        <Title order={2}>Users</Title>
        <Button onClick={() => setCreateOpen(true)}>Create user</Button>
      </Group>

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
              <Table.Th>Username</Table.Th>
              <Table.Th>Role</Table.Th>
              <Table.Th>Last login</Table.Th>
              <Table.Th>Active</Table.Th>
              <Table.Th w={60} />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {state.rows.map((row) => (
              <Table.Tr key={row.id}>
                <Table.Td>{row.username}</Table.Td>
                <Table.Td>
                  <Badge variant="light" color={row.role === "admin" ? "grape" : "blue"}>
                    {row.role}
                  </Badge>
                </Table.Td>
                <Table.Td>{formatLastLogin(row.last_login_at)}</Table.Td>
                <Table.Td>
                  <Badge variant="light" color={row.is_enabled ? "green" : "gray"}>
                    {row.is_enabled ? "Enabled" : "Disabled"}
                  </Badge>
                </Table.Td>
                <Table.Td w={60}>
                  <Menu position="bottom-end" withinPortal>
                    <Menu.Target>
                      <Box component="span" display="inline-block">
                        <IconButton
                          icon={IconDots}
                          label={`Actions for ${row.username}`}
                          onClick={openedByMenuTarget}
                        />
                      </Box>
                    </Menu.Target>
                    <Menu.Dropdown>
                      <Menu.Item onClick={() => setPasswordTarget(row)}>Set Password</Menu.Item>
                      <Menu.Item onClick={() => setRoleTarget(row)}>Change Role</Menu.Item>
                      {row.is_enabled ? (
                        <Menu.Item color="red" onClick={() => setDisableTarget(row)}>
                          Disable
                        </Menu.Item>
                      ) : (
                        <Menu.Item onClick={() => reEnable(row)}>Re-enable</Menu.Item>
                      )}
                    </Menu.Dropdown>
                  </Menu>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <ConfirmModal
        opened={disableTarget !== null}
        title={disableTarget !== null ? `Disable ${disableTarget.username}?` : "Disable account?"}
        consequence="This person is signed out immediately and cannot sign in until the account is re-enabled."
        confirmLabel="Disable"
        confirmColor="red"
        onCancel={cancelDisable}
        onConfirm={confirmDisable}
      />

      {createOpen && <CreateUserModal onClose={closeCreate} onSaved={onCreated} />}
      {passwordTarget !== null && (
        <SetPasswordModal target={passwordTarget} onClose={closePassword} onSaved={onPasswordSaved} />
      )}
      {roleTarget !== null && (
        <ChangeRoleModal target={roleTarget} onClose={closeRole} onSaved={onRoleSaved} />
      )}
    </Container>
  );
});
