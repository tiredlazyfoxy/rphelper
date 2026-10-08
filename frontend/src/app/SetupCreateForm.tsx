// The Setups section's inline create form (feature 033, step 003, D7): conditionally mounted by
// `SetupsSection` above its list, so the `SetupDraft` built with `useState` is fresh per open.
// Reuses `submitSetup` in create mode; on success calls `onCreated(row)` and the parent applies
// the row and then unmounts the form. Failures render inline, inside the form.
//
// Accessible names are the contract the tests bind to:
//   text input     "Name"         (focused on mount)
//   MarkdownEditor "Description"
//   IconButton     "Save setup"        (`IconDeviceFloppy`), enabled exactly when `canSubmit(draft)`
//   IconButton     "Cancel new setup"  (`IconX`), calls `onCancel` with no request
//   Both icon buttons are disabled while the draft is submitting.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { Alert, Group, Stack, TextInput } from "@mantine/core";
import { IconDeviceFloppy, IconX } from "@tabler/icons-react";
import { observer } from "mobx-react-lite";

import { IconButton } from "../shared/IconButton";
import { MarkdownEditor } from "../shared/MarkdownEditor";
import {
  SetupDraft,
  canSubmit,
  setDraftDescription,
  setDraftName,
  submitSetup,
} from "./setupDraft";
import type { Setup } from "./setupsApi";

export type SetupCreateFormProps = {
  /** The character the created setup is filed under. A string, never parsed. */
  characterId: string;
  /** Called once with the server's row after a successful create; the parent then unmounts the form. */
  onCreated: (created: Setup) => void;
  /** Discard the draft with no request; the parent unmounts the form. */
  onCancel: () => void;
};

export const SetupCreateForm = observer(function SetupCreateForm(
  props: SetupCreateFormProps,
): React.JSX.Element {
  const { characterId, onCreated, onCancel } = props;
  // Fresh per mount: the parent mounts this form only while its open flag is set.
  const [draft] = useState(() => new SetupDraft(characterId, null));
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, []);

  const submitting = draft.submitStatus === "submitting";

  const save = (): void => {
    if (!canSubmit(draft)) {
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    // The parent's `onCreated` applies the row and unmounts the form; nothing closes here.
    void submitSetup(draft, onCreated, controller.signal);
  };

  return (
    <Stack gap="sm">
      <TextInput
        label="Name"
        autoComplete="off"
        autoFocus
        value={draft.name}
        onChange={(event) => {
          setDraftName(draft, event.currentTarget.value);
        }}
      />
      <MarkdownEditor
        label="Description"
        value={draft.description}
        onChange={(markdown) => {
          setDraftDescription(draft, markdown);
        }}
        readOnly={submitting}
      />
      <Group gap="xs" wrap="nowrap">
        <IconButton
          icon={IconDeviceFloppy}
          label="Save setup"
          disabled={!canSubmit(draft)}
          onClick={save}
        />
        <IconButton icon={IconX} label="Cancel new setup" disabled={submitting} onClick={onCancel} />
      </Group>
      {/* D7 / D12: the failure renders inside the form, never as a notification. */}
      {draft.error !== null && <Alert color="red">{draft.error}</Alert>}
    </Stack>
  );
});
