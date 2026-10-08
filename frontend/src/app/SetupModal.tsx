// The setup create / edit modal (feature 010, step 005, D2 / D12): a Mantine `Modal`,
// conditionally mounted by its parent (step 006) so the draft built with `useState` is fresh
// per open (`ui-conventions.md` "Draft lifetime"). `setup` null is create mode, a row is edit
// mode. The modal never closes itself on success: `submitSetup` calls `onSaved(row)` and the
// parent applies the row and then unmounts the modal. No notification is raised anywhere and
// `shared/notifyFailure` is not imported — a submit failure renders in an inline `Alert`
// inside the dialog (D12).
//
// Accessible names are the contract the tests bind to:
//   dialog title   "New setup" (create) / "Edit setup" (edit)   — the `Modal`'s `title`
//   text input     "Name"
//   MarkdownEditor "Description"  (`readOnly` while submitting)
//   buttons        "Cancel"; "Create" (create, `IconPlus` left section) /
//                  "Save" (edit, `IconDeviceFloppy` left section), disabled unless
//                  `canSubmit(draft)`
// The submit is a labelled `Button`, so `shared/IconButton` does not apply; its left-section
// icon takes the repo's "main" metrics `size={18} stroke={1.5}` (`CharacterScreen.tsx:40-42`).
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Group, Modal, Stack, TextInput } from "@mantine/core";
import { IconDeviceFloppy, IconPlus } from "@tabler/icons-react";
import { observer } from "mobx-react-lite";

import { MarkdownEditor } from "../shared/MarkdownEditor";
import {
  SetupDraft,
  canSubmit,
  isEditing,
  setDraftDescription,
  setDraftName,
  submitSetup,
} from "./setupDraft";
import type { Setup } from "./setupsApi";

/** The repo's "main" icon metrics (`IconButton`'s `ICON_SIZES.main` / `ICON_STROKE`). */
const ICON_SIZE = 18;
const ICON_STROKE = 1.5;

export type SetupModalProps = {
  /** The character a created setup is filed under. A string, never parsed. */
  characterId: string;
  /** The setup to edit, or null to create one. */
  setup: Setup | null;
  /** Close without saving (Cancel, the close button, Escape, the overlay). */
  onClose: () => void;
  /** Called once with the server's row after a successful submit; the parent then closes. */
  onSaved: (saved: Setup) => void;
};

export const SetupModal = observer(function SetupModal(
  props: SetupModalProps,
): React.JSX.Element {
  const { characterId, setup, onClose, onSaved } = props;
  const [draft] = useState(() => new SetupDraft(characterId, setup));
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, []);

  const editing = isEditing(draft);
  const submitEnabled = canSubmit(draft);
  const submitting = draft.submitStatus === "submitting";

  const onSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!canSubmit(draft)) {
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    // The parent's `onSaved` applies the row and unmounts the modal; nothing closes here.
    void submitSetup(draft, onSaved, controller.signal);
  };

  return (
    <Modal opened onClose={onClose} title={editing ? "Edit setup" : "New setup"} centered>
      <form onSubmit={onSubmit} noValidate>
        <Stack gap="sm">
          {draft.error !== null && <Alert color="red">{draft.error}</Alert>}
          <TextInput
            label="Name"
            autoComplete="off"
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
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!submitEnabled}
              loading={submitting}
              leftSection={
                editing ? (
                  <IconDeviceFloppy size={ICON_SIZE} stroke={ICON_STROKE} />
                ) : (
                  <IconPlus size={ICON_SIZE} stroke={ICON_STROKE} />
                )
              }
            >
              {editing ? "Save" : "Create"}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
});
