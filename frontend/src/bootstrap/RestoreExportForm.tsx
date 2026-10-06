// The offer phase's "Restore from an export" choice: environment notice, `Export file` input,
// `Restore database` button and inline red failure Alert. State passed as a prop; owns its
// AbortController and aborts on unmount, mirroring `CreateAdminForm`.
import type * as React from "react";
import { useEffect, useId, useRef } from "react";
import { Alert, Button, Group, Input, Stack, Text } from "@mantine/core";
import { observer } from "mobx-react-lite";
import {
  chooseRestoreFile,
  submitRestoreExport,
  type RestoreExportState,
  type RestoreNavigation,
} from "./restoreExport";

export type RestoreExportFormProps = {
  state: RestoreExportState;
  /** The hand-off seam after a successful restore. Defaults to `documentNavigation`. */
  navigation?: RestoreNavigation;
};

const EXPORT_ACCEPT = ".json,application/json";

export const RestoreExportForm = observer(function RestoreExportForm(
  props: RestoreExportFormProps,
): React.JSX.Element {
  const { state, navigation } = props;
  const inputId = useId();
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, []);

  const onFileChange = (event: React.ChangeEvent<HTMLInputElement>): void => {
    const files = event.currentTarget.files;
    chooseRestoreFile(state, files !== null && files.length > 0 ? files[0] : null);
  };

  const onRestore = (): void => {
    if (state.file === null || state.submitting) {
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    void submitRestoreExport(state, controller.signal, navigation);
  };

  return (
    <Stack gap="sm">
      <Text size="sm">
        Credentials and API keys are not included in an export. Supply the environment (the .env
        file) separately so the restored instance can reach a model server.
      </Text>
      <Input.Wrapper label="Export file" id={inputId}>
        <input id={inputId} type="file" accept={EXPORT_ACCEPT} onChange={onFileChange} />
      </Input.Wrapper>
      <Group>
        <Button
          type="button"
          disabled={state.file === null || state.submitting}
          loading={state.submitting}
          onClick={onRestore}
        >
          Restore database
        </Button>
      </Group>
      {state.failureMessage !== null && (
        <Alert color="red" role="alert" title="The database was not restored">
          {state.failureMessage}
        </Alert>
      )}
    </Stack>
  );
});
