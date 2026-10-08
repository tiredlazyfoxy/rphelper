// The Set Embedding modal: a Mantine Modal over a ModelPicker and an EmbeddingDraft the page
// constructs fresh per open (conditionally mounted; context.md D2 / D11 / D16).
import type * as React from "react";
import { useEffect, useRef } from "react";
import { Alert, Button, Center, Group, Loader, Modal, Radio, Stack, Text } from "@mantine/core";
import { runInAction } from "mobx";
import { observer } from "mobx-react-lite";
import { type ModelPicker, loadAvailableModels, modelOptionsOf } from "./modelPicker";
import {
  type EmbeddingDraft,
  canSubmitEmbedding,
  submitEmbeddingDesignation,
} from "./embeddingDraft";

export type EmbeddingModalProps = {
  /** Fresh per open; the modal starts the probe on mount and aborts it on unmount. */
  picker: ModelPicker;
  /** Fresh per open; seeded from the row's `embedding_model_name`. */
  draft: EmbeddingDraft;
  /** The target row's id (probe and designation routes). */
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

export const EmbeddingModal = observer(function EmbeddingModal(
  props: EmbeddingModalProps,
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

  // The union of what the server offers and the current designation (from the list payload).
  const options = modelOptionsOf(picker.available, draft.designated !== null ? [draft.designated] : []);
  const probing = picker.status === "loading";
  const submitting = draft.submitStatus === "submitting";
  const canSubmit = canSubmitEmbedding(draft);

  const choose = (name: string): void => {
    runInAction(() => {
      draft.selected = name;
    });
  };

  const onSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!canSubmitEmbedding(draft)) {
      return;
    }
    const controller = new AbortController();
    submitControllerRef.current = controller;
    void submitEmbeddingDesignation(draft, serverId, onSaved, controller.signal).catch(ignoreRejection);
  };

  return (
    <Modal opened onClose={onClose} title={`Set embedding model — ${serverName}`} centered>
      <form onSubmit={onSubmit} noValidate>
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            Designating a model measures its embedding dimension with one real call to the server.
            A model that cannot produce embeddings will be refused.
          </Text>
          {draft.serverErrors.general !== undefined && (
            <Alert color="red" title="The embedding model was not designated">
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
            <Radio.Group value={draft.selected} onChange={choose} label="Embedding model">
              <Stack gap="xs" mt="xs">
                {options.map((option) => (
                  <Radio
                    key={option.name}
                    value={option.name}
                    label={option.name}
                    description={option.offered ? undefined : "No longer offered by the server"}
                  />
                ))}
              </Stack>
            </Radio.Group>
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
