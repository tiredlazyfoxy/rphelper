// The create-account modal: a Mantine Modal, conditionally mounted by the Users page so
// its draft (useState(() => new CreateUserDraft())) is fresh per open.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Group, Modal, PasswordInput, Select, Stack, TextInput } from "@mantine/core";
import { runInAction } from "mobx";
import { observer } from "mobx-react-lite";
import {
  CreateUserDraft,
  canSubmitCreateUser,
  createUserClientErrors,
  submitCreateUser,
  type CreateUserField,
} from "./createUserDraft";
import type { AdminUserRole, AdminUserRow } from "./usersPageState";

export type CreateUserModalProps = {
  /** Close without saving (Cancel, the close button, Escape, the overlay). */
  onClose: () => void;
  /** Called once after a successful create; the page closes the modal and re-loads the list. */
  onSaved: (created: AdminUserRow) => void;
};

/** The ladder's two rungs, lower first; values are the strings the backend stores. */
const ROLE_OPTIONS: { value: AdminUserRole; label: string }[] = [
  { value: "roleplayer", label: "roleplayer" },
  { value: "admin", label: "admin" },
];

function isRole(value: string | null): value is AdminUserRole {
  return value === "roleplayer" || value === "admin";
}

export const CreateUserModal = observer(function CreateUserModal(
  props: CreateUserModalProps,
): React.JSX.Element {
  const { onClose, onSaved } = props;
  const [draft] = useState(() => new CreateUserDraft());
  const [touched, setTouched] = useState<Partial<Record<CreateUserField, true>>>({});
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, []);

  const clientErrors = createUserClientErrors(draft);
  const canSubmit = canSubmitCreateUser(draft);
  const submitting = draft.submitStatus === "submitting";

  // A client error shows once its field holds something or has been left; an untouched
  // empty form is not shouted at.
  const shownClientError = (field: CreateUserField): string | undefined =>
    draft[field] !== "" || touched[field] === true ? clientErrors[field] : undefined;

  const markTouched = (field: CreateUserField): void => {
    setTouched((current) => (current[field] === true ? current : { ...current, [field]: true }));
  };

  const onSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!canSubmitCreateUser(draft)) {
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    void submitCreateUser(draft, onSaved, controller.signal);
  };

  return (
    <Modal opened onClose={onClose} title="Create user" centered>
      <form onSubmit={onSubmit} noValidate>
        <Stack gap="sm">
          {draft.serverErrors.general !== undefined && (
            <Alert color="red" title="The account was not created">
              {draft.serverErrors.general}
            </Alert>
          )}
          <TextInput
            label="Username"
            autoComplete="off"
            value={draft.username}
            error={shownClientError("username") ?? draft.serverErrors.username}
            onChange={(event) => {
              const value = event.currentTarget.value;
              runInAction(() => {
                draft.username = value;
              });
            }}
            onBlur={() => markTouched("username")}
          />
          <PasswordInput
            label="Password"
            autoComplete="new-password"
            value={draft.password}
            error={shownClientError("password")}
            onChange={(event) => {
              const value = event.currentTarget.value;
              runInAction(() => {
                draft.password = value;
              });
            }}
            onBlur={() => markTouched("password")}
          />
          <PasswordInput
            label="Confirm password"
            autoComplete="new-password"
            value={draft.confirmation}
            error={shownClientError("confirmation")}
            onChange={(event) => {
              const value = event.currentTarget.value;
              runInAction(() => {
                draft.confirmation = value;
              });
            }}
            onBlur={() => markTouched("confirmation")}
          />
          <Select
            label="Role"
            data={ROLE_OPTIONS}
            value={draft.role}
            allowDeselect={false}
            onChange={(value) => {
              if (isRole(value)) {
                runInAction(() => {
                  draft.role = value;
                });
              }
            }}
          />
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit} loading={submitting}>
              Create
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
});
