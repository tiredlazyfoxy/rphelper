// The set-password modal: a Mantine Modal, conditionally mounted by the Users page so its
// draft (useState(() => new SetPasswordDraft())) is fresh per open. No current-password
// field, no generated password, no email affordance, no force-change switch.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Group, Modal, PasswordInput, Stack, Text } from "@mantine/core";
import { runInAction } from "mobx";
import { observer } from "mobx-react-lite";
import {
  SetPasswordDraft,
  canSubmitSetPassword,
  setPasswordClientErrors,
  submitSetPassword,
  type SetPasswordField,
} from "./setPasswordDraft";
import type { AdminUserRow } from "./usersPageState";

export type SetPasswordModalProps = {
  /** The account being acted on (the row the menu was opened on); named in the modal. */
  target: AdminUserRow;
  /** Close without saving (Cancel, the close button, Escape, the overlay). */
  onClose: () => void;
  /** Called once after a successful reset; the page closes the modal and re-loads the list. */
  onSaved: (updated: AdminUserRow) => void;
};

export const SetPasswordModal = observer(function SetPasswordModal(
  props: SetPasswordModalProps,
): React.JSX.Element {
  const { target, onClose, onSaved } = props;
  const [draft] = useState(() => new SetPasswordDraft());
  const [touched, setTouched] = useState<Partial<Record<SetPasswordField, true>>>({});
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, []);

  const clientErrors = setPasswordClientErrors(draft);
  const canSubmit = canSubmitSetPassword(draft);
  const submitting = draft.submitStatus === "submitting";

  // A client error shows once its field holds something or has been left.
  const shownClientError = (field: SetPasswordField): string | undefined =>
    draft[field] !== "" || touched[field] === true ? clientErrors[field] : undefined;

  const markTouched = (field: SetPasswordField): void => {
    setTouched((current) => (current[field] === true ? current : { ...current, [field]: true }));
  };

  const onSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!canSubmitSetPassword(draft)) {
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    void submitSetPassword(draft, target.id, onSaved, controller.signal);
  };

  return (
    <Modal opened onClose={onClose} title={`Set password for ${target.username}`} centered>
      <form onSubmit={onSubmit} noValidate>
        <Stack gap="sm">
          {draft.serverErrors.general !== undefined && (
            <Alert color="red" title="The password was not set">
              {draft.serverErrors.general}
            </Alert>
          )}
          <Text size="sm">
            Set a new password for <b>{target.username}</b>.
          </Text>
          <PasswordInput
            label="New password"
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
            label="Confirm new password"
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
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit} loading={submitting}>
              Set password
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
});
