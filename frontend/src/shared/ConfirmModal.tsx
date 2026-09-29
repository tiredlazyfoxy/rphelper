// The one shared confirm dialog. Stateless: the caller supplies every word and both
// callbacks; cancel sits left of confirm.
import type * as React from "react";
import { Button, Group, Modal, Text } from "@mantine/core";
import type { MantineColor } from "@mantine/core";

export type ConfirmModalProps = {
  opened: boolean;
  title: string;                     // names the action
  consequence: string;               // one sentence; no counts derived from other users' data
  confirmLabel: string;              // the confirm button's text
  confirmColor?: MantineColor;       // "red" for a destroy; the action's own colour otherwise
  loading?: boolean;                 // "in progress" flag for the confirm button
  onCancel: () => void;
  onConfirm: () => void;
};

export function ConfirmModal(props: ConfirmModalProps): React.JSX.Element {
  const { opened, title, consequence, confirmLabel, confirmColor, loading, onCancel, onConfirm } =
    props;
  return (
    <Modal opened={opened} onClose={onCancel} title={title} centered>
      <Text size="sm">{consequence}</Text>
      <Group justify="flex-end" mt="lg">
        <Button variant="default" onClick={onCancel} disabled={loading === true}>
          Cancel
        </Button>
        <Button color={confirmColor} onClick={onConfirm} loading={loading === true}>
          {confirmLabel}
        </Button>
      </Group>
    </Modal>
  );
}
