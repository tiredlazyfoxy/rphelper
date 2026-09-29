// The change-role modal: a Mantine Modal, conditionally mounted by the Users page so its
// draft (useState(() => new ChangeRoleDraft(props.target.role))) is fresh per open.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Group, Modal, Select, Stack, Text } from "@mantine/core";
import { runInAction } from "mobx";
import { observer } from "mobx-react-lite";
import {
  ChangeRoleDraft,
  canSubmitChangeRole,
  changeRoleClientErrors,
  submitChangeRole,
} from "./changeRoleDraft";
import type { AdminUserRole, AdminUserRow } from "./usersPageState";

export type ChangeRoleModalProps = {
  /** The account being acted on; named in the modal, its `role` pre-selects the Select. */
  target: AdminUserRow;
  /** Close without saving (Cancel, the close button, Escape, the overlay). */
  onClose: () => void;
  /** Called once after a successful change; the page closes the modal and re-loads the list. */
  onSaved: (updated: AdminUserRow) => void;
};

/** The ladder's two rungs, lower first; values are the strings the backend stores. */
const ROLE_OPTIONS: { value: AdminUserRole; label: string }[] = [
  { value: "roleplayer", label: "roleplayer" },
  { value: "admin", label: "admin" },
];

function isRole(value: string | null): value is AdminUserRole {
  return value === "roleplayer" || value === "admin";
}

export const ChangeRoleModal = observer(function ChangeRoleModal(
  props: ChangeRoleModalProps,
): React.JSX.Element {
  const { target, onClose, onSaved } = props;
  const [draft] = useState(() => new ChangeRoleDraft(props.target.role));
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, []);

  const clientErrors = changeRoleClientErrors(draft);
  const canSubmit = canSubmitChangeRole(draft);
  const submitting = draft.submitStatus === "submitting";

  const onSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!canSubmitChangeRole(draft)) {
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    void submitChangeRole(draft, target.id, onSaved, controller.signal);
  };

  return (
    <Modal opened onClose={onClose} title={`Change role for ${target.username}`} centered>
      <form onSubmit={onSubmit} noValidate>
        <Stack gap="sm">
          {draft.serverErrors.general !== undefined && (
            <Alert color="red" title="The role was not changed">
              {draft.serverErrors.general}
            </Alert>
          )}
          <Text size="sm">
            Choose the role for <b>{target.username}</b>.
          </Text>
          <Select
            label="Role"
            data={ROLE_OPTIONS}
            value={draft.role}
            error={clientErrors.role}
            onChange={(value) => {
              const next = isRole(value) ? value : null;
              runInAction(() => {
                draft.role = next;
              });
            }}
          />
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit} loading={submitting}>
              Change role
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
});
