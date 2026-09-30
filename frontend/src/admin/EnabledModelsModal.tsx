// The Select Models modal: a Mantine Modal over a ModelPicker and an EnabledModelsDraft the
// page constructs fresh per open (conditionally mounted; context.md D11 / D16 / D18).
import type * as React from "react";
import { useEffect, useRef } from "react";
import { Alert, Button, Center, Checkbox, Group, Loader, Modal, Stack, Text } from "@mantine/core";
import { runInAction } from "mobx";
import { observer } from "mobx-react-lite";
import { type ModelPicker, loadAvailableModels, modelOptionsOf } from "./modelPicker";
import {
  type EnabledModelsDraft,
  canSubmitEnabledModels,
  submitEnabledModels,
} from "./enabledModelsDraft";

export type EnabledModelsModalProps = {
  /** Fresh per open; the modal starts the probe on mount and aborts it on unmount. */
  picker: ModelPicker;
  /** Fresh per open; seeded from the row's `enabled_model_names`. */
  draft: EnabledModelsDraft;
  /** The target row's id (probe and save routes). */
  serverId: string;
  /** The target row's name (modal title). */
  serverName: string;
  /** Close without saving (Cancel, the close button, Escape, the overlay). */
  onClose: () => void;
  /** Called once after a successful save; the page closes the modal and re-loads the list. */
  onSaved: () => void;
};

function ignoreRejection(): void {
  // Free functions never reject; this only keeps a surprise from going unhandled.
}

export const EnabledModelsModal = observer(function EnabledModelsModal(
  props: EnabledModelsModalProps,
): React.JSX.Element {
  const { picker, draft, serverId, serverName, onClose, onSaved } = props;
  const submitControllerRef = useRef<AbortController | null>(null);

  // The probe: started once on mount, aborted on unmount so a closed modal writes nothing.
  useEffect(() => {
    const controller = new AbortController();
    void loadAvailableModels(picker, serverId, controller.signal).catch(ignoreRejection);
    return () => {
      controller.abort();
    };
  }, [picker, serverId]);

  useEffect(() => {
    return () => {
      submitControllerRef.current?.abort();
      submitControllerRef.current = null;
    };
  }, []);

  // The union of what the server offers and what is already enabled (from the list payload).
  const options = modelOptionsOf(picker.available, draft.loaded);
  const selected = new Set(draft.selected);
  const probing = picker.status === "loading";
  const submitting = draft.submitStatus === "submitting";
  const canSubmit = canSubmitEnabledModels(draft);

  const toggle = (name: string, checked: boolean): void => {
    runInAction(() => {
      if (checked) {
        if (!draft.selected.includes(name)) {
          draft.selected = [...draft.selected, name];
        }
      } else {
        draft.selected = draft.selected.filter((candidate) => candidate !== name);
      }
    });
  };

  const onSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!canSubmitEnabledModels(draft)) {
      return;
    }
    const controller = new AbortController();
    submitControllerRef.current = controller;
    void submitEnabledModels(draft, serverId, onSaved, controller.signal).catch(ignoreRejection);
  };

  return (
    <Modal opened onClose={onClose} title={`Select models — ${serverName}`} centered>
      <form onSubmit={onSubmit} noValidate>
        <Stack gap="sm">
          {draft.serverErrors.general !== undefined && (
            <Alert color="red" title="The enabled models were not saved">
              {draft.serverErrors.general}
            </Alert>
          )}
          {picker.status === "failed" && (
            <Alert color="red" title="The server's models could not be listed">
              {picker.errorMessage}
            </Alert>
          )}
          {probing && (
            <Center py="sm">
              <Loader size="sm" />
            </Center>
          )}
          {options.length === 0 && picker.status === "ready" && (
            <Text size="sm" c="dimmed">
              This server offers no models.
            </Text>
          )}
          {options.length > 0 && (
            <Stack gap="xs">
              {options.map((option) => (
                <Checkbox
                  key={option.name}
                  label={option.name}
                  description={option.offered ? undefined : "No longer offered by the server"}
                  checked={selected.has(option.name)}
                  onChange={(event) => toggle(option.name, event.currentTarget.checked)}
                />
              ))}
            </Stack>
          )}
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit} loading={submitting}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
});
