// The session header bar (feature 017, step 011, D16, UC-077): the "Session configuration"
// group in `SessionScreen`'s ready header — the "Model" picker over the enabled models, the
// "Tools" badges from the resolved tool values, and the gear that opens
// `SessionConfigModal`. Loads its `SessionConfigState` on mount with an `AbortController`
// aborted on unmount; failures render inline with a Retry, never notified.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import { Badge, Button, Group, Loader, Select, Stack, Text } from "@mantine/core";
import { IconSettings } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import type { ModelRef, Setting } from "./configurationApi";
import { SessionConfigModal } from "./SessionConfigModal";
import {
  applySessionConfiguration,
  chooseModel,
  loadSessionConfig,
  sameModel,
} from "./sessionConfigState";
import type { SessionConfigState } from "./sessionConfigState";

export type SessionConfigBarProps = {
  /** The one `SessionConfigState` the session screen owns; loaded by this bar on mount. */
  state: SessionConfigState;
};

/** Select values are strings: `"<server_id>:<model_name>"`, split at the first `:`. */
function encodeModel(model: ModelRef): string {
  return `${model.server_id}:${model.model_name}`;
}

function decodeModel(value: string): ModelRef | null {
  const at = value.indexOf(":");
  if (at < 0) {
    return null;
  }
  return { server_id: value.slice(0, at), model_name: value.slice(at + 1) };
}

function toolLabel(name: string, setting: Setting<boolean>): string {
  return `${name}: ${setting.value === true ? "on" : "off"}`;
}

/** The model picker, tool indicators and configuration gear for one session (D16). */
export const SessionConfigBar = observer(function SessionConfigBar(
  props: SessionConfigBarProps,
): React.JSX.Element {
  const { state } = props;
  const [modalOpen, setModalOpen] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadSessionConfig(state, controller.signal);
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [state]);

  const retry = (): void => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadSessionConfig(state, controller.signal);
  };

  const loading =
    state.configStatus === "idle" ||
    state.configStatus === "loading" ||
    state.modelsStatus === "idle" ||
    state.modelsStatus === "loading";
  const failed = state.configStatus === "failed" || state.modelsStatus === "failed";
  const configuration = state.configStatus === "ready" ? state.configuration : null;
  const captured = configuration?.model ?? null;

  let picker: React.JSX.Element | null = null;
  if (state.modelsStatus === "ready") {
    const empty = state.models.length === 0;
    const options: { value: string; label: string; disabled?: boolean }[] = state.models.map(
      (model) => ({
        value: encodeModel(model),
        label: `${model.model_name} (${model.server_name})`,
      }),
    );
    if (captured !== null && !state.models.some((model) => sameModel(model, captured))) {
      options.push({
        value: encodeModel(captured),
        label: `${captured.model_name} (not enabled)`,
        disabled: true,
      });
    }
    picker = (
      <Stack gap={4}>
        <Select
          label="Model"
          data={options}
          value={captured === null ? null : encodeModel(captured)}
          placeholder={empty ? "No model is enabled" : "Choose a model"}
          disabled={empty || state.modelSaving}
          allowDeselect={false}
          onChange={(value) => {
            if (value === null) {
              return;
            }
            const model = decodeModel(value);
            if (model !== null) {
              void chooseModel(state, model);
            }
          }}
        />
        {state.modelFailure !== null ? (
          <Text size="sm" c="red">
            {state.modelFailure}
          </Text>
        ) : null}
      </Stack>
    );
  }

  return (
    <Group role="group" aria-label="Session configuration" gap="sm" align="flex-end">
      {loading ? <Loader size="sm" /> : null}
      {failed ? (
        <Group gap="xs">
          <Text size="sm">Could not load the session configuration</Text>
          <Button size="xs" variant="default" onClick={retry}>
            Retry
          </Button>
        </Group>
      ) : null}
      {picker}
      {configuration !== null ? (
        <Group role="group" aria-label="Tools" gap="xs">
          <Badge variant="light">{toolLabel("Memo search", configuration.tool_memo_search)}</Badge>
          <Badge variant="light">
            {toolLabel("Session search", configuration.tool_session_search)}
          </Badge>
          <Badge variant="light">{toolLabel("Web search", configuration.tool_web_search)}</Badge>
        </Group>
      ) : null}
      <IconButton
        icon={IconSettings}
        label="Session configuration"
        disabled={configuration === null}
        onClick={() => {
          setModalOpen(true);
        }}
      />
      {configuration !== null ? (
        <SessionConfigModal
          opened={modalOpen}
          sessionId={state.sessionId}
          configuration={configuration}
          onClose={() => {
            setModalOpen(false);
          }}
          onSaved={(saved) => {
            applySessionConfiguration(state, saved);
          }}
        />
      ) : null}
    </Group>
  );
});
