// The register / edit connection modal: a Mantine Modal over a ServerFormDraft the page
// constructs fresh per open (conditionally mounted; context.md D16).
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Group, Modal, PasswordInput, Select, Stack, TextInput } from "@mantine/core";
import { runInAction } from "mobx";
import { observer } from "mobx-react-lite";
import type { LlmServerKind } from "./llmServersPageState";
import {
  type ServerFormDraft,
  type ServerFormField,
  canSubmitServerForm,
  serverFormClientErrors,
  submitServerForm,
} from "./serverFormDraft";

export type ServerFormModalProps = {
  /** Fresh per open; `draft.original` null = register mode, non-null = edit mode. */
  draft: ServerFormDraft;
  /** Close without saving (Cancel, the close button, Escape, the overlay). */
  onClose: () => void;
  /** Called once after a successful save; the page closes the modal and re-loads the list. */
  onSaved: () => void;
};

/** Exactly the two kinds `llm_servers.kind` accepts; the value is the wire literal. */
const KIND_OPTIONS: { value: LlmServerKind; label: string }[] = [
  { value: "llamaswap", label: "llamaswap" },
  { value: "openai", label: "OpenAI" },
];

function isKind(value: string | null): value is LlmServerKind {
  return value === "llamaswap" || value === "openai";
}

const POINTER_DESCRIPTION =
  "A pointer to an environment variable, such as $OPENAI_API_KEY — not a key. Leave empty when the server needs none.";
const POINTER_EDIT_DESCRIPTION =
  "A pointer to an environment variable, such as $OPENAI_API_KEY — not a key. Leaving this field untouched keeps the stored pointer; clearing it removes the stored pointer.";

export const ServerFormModal = observer(function ServerFormModal(
  props: ServerFormModalProps,
): React.JSX.Element {
  const { draft, onClose, onSaved } = props;
  const [touched, setTouched] = useState<Partial<Record<ServerFormField, true>>>({});
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, []);

  const editing = draft.original !== null;
  const clientErrors = serverFormClientErrors(draft);
  const canSubmit = canSubmitServerForm(draft);
  const submitting = draft.submitStatus === "submitting";

  const fieldValue = (field: ServerFormField): string =>
    field === "name" ? draft.name : field === "baseUrl" ? draft.baseUrl : draft.pointer;

  // A client error shows once its field holds something or has been visited; an untouched
  // empty form is not shouted at.
  const shownError = (field: ServerFormField): string | undefined =>
    (fieldValue(field) !== "" || touched[field] === true ? clientErrors[field] : undefined) ??
    draft.serverErrors[field];

  const markTouched = (field: ServerFormField): void => {
    setTouched((current) => (current[field] === true ? current : { ...current, [field]: true }));
  };

  const onSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!canSubmitServerForm(draft)) {
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    void submitServerForm(draft, draft.original?.id ?? null, onSaved, controller.signal);
  };

  return (
    <Modal
      opened
      onClose={onClose}
      title={draft.original !== null ? `Edit ${draft.original.name}` : "Register LLM server"}
      centered
    >
      <form onSubmit={onSubmit} noValidate>
        <Stack gap="sm">
          {draft.serverErrors.general !== undefined && (
            <Alert color="red" title="The connection was not saved">
              {draft.serverErrors.general}
            </Alert>
          )}
          <TextInput
            label="Name"
            autoComplete="off"
            value={draft.name}
            error={shownError("name")}
            onChange={(event) => {
              const value = event.currentTarget.value;
              runInAction(() => {
                draft.name = value;
              });
              markTouched("name");
            }}
            onBlur={() => markTouched("name")}
          />
          <Select
            label="Kind"
            data={KIND_OPTIONS}
            value={draft.kind}
            allowDeselect={false}
            onChange={(value) => {
              if (isKind(value)) {
                runInAction(() => {
                  draft.kind = value;
                });
              }
            }}
          />
          <TextInput
            label="Base URL"
            autoComplete="off"
            placeholder="http://host:port/v1"
            value={draft.baseUrl}
            error={shownError("baseUrl")}
            onChange={(event) => {
              const value = event.currentTarget.value;
              runInAction(() => {
                draft.baseUrl = value;
              });
              markTouched("baseUrl");
            }}
            onBlur={() => markTouched("baseUrl")}
          />
          <PasswordInput
            label="API key pointer"
            autoComplete="off"
            description={editing ? POINTER_EDIT_DESCRIPTION : POINTER_DESCRIPTION}
            value={draft.pointer}
            error={shownError("pointer")}
            onChange={(event) => {
              const value = event.currentTarget.value;
              runInAction(() => {
                draft.pointer = value;
                draft.pointerTouched = true;
              });
              markTouched("pointer");
            }}
            onBlur={() => markTouched("pointer")}
          />
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit} loading={submitting}>
              {editing ? "Save" : "Register"}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
});
