// The character page's "Configuration" region (feature 018, step 007, D9): the model, the
// system prompt and the three tool switches, each with its resolved value and whether it is
// set on this character, edited in place over one `CharacterConfigState`.
import type * as React from "react";
import { useEffect, useId, useRef, useState } from "react";
import type { TitleOrder } from "@mantine/core";
import {
  Button,
  Group,
  Loader,
  SegmentedControl,
  Select,
  Stack,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { observer } from "mobx-react-lite";

import type { CharacterConfiguration } from "./configurationApi";
import type { CharacterConfigKeyPatch, CharacterToolKey, ToolChoice } from "./characterConfigState";
import {
  CharacterConfigState,
  commitPromptDraft,
  loadCharacterConfig,
  modelChoices,
  modelLine,
  promptLine,
  saveCharacterConfig,
  selectedModelValue,
  setPromptDraft,
  toolChoice,
  toolLine,
  toolPatchValue,
} from "./characterConfigState";

export type CharacterConfigSectionProps = {
  /** The loaded character's id. A string, never parsed. */
  characterId: string;
  /** The heading order the page uses for its sections ("Setups", "Sessions", "Notes"). */
  headingOrder: TitleOrder;
};

const TOOL_CHOICES: ToolChoice[] = ["Default", "On", "Off"];

const TOOLS: { key: CharacterToolKey; label: string }[] = [
  { key: "tool_memo_search", label: "Memo search" },
  { key: "tool_session_search", label: "Session search" },
  { key: "tool_web_search", label: "Web search" },
];

function isToolChoice(value: string): value is ToolChoice {
  return (TOOL_CHOICES as string[]).includes(value);
}

type ToolControlProps = {
  label: string;
  value: boolean | null;
  disabled: boolean;
  onChoose: (choice: ToolChoice) => void;
};

/** A labelled `SegmentedControl`: the visible label names the radio group. */
function ToolControl(props: ToolControlProps): React.JSX.Element {
  const labelId = useId();
  return (
    <Stack gap={4}>
      <Text id={labelId} size="sm" fw={500}>
        {props.label}
      </Text>
      <SegmentedControl
        aria-labelledby={labelId}
        data={TOOL_CHOICES}
        value={toolChoice(props.value)}
        disabled={props.disabled}
        onChange={(value) => {
          if (isToolChoice(value)) {
            props.onChoose(value);
          }
        }}
      />
      <Text size="sm" c="dimmed">
        {toolLine(props.value)}
      </Text>
    </Stack>
  );
}

export const CharacterConfigSection = observer(function CharacterConfigSection(
  props: CharacterConfigSectionProps,
): React.JSX.Element {
  const { headingOrder } = props;
  // Created once; the page keys this section by the character id.
  const [state] = useState(() => new CharacterConfigState(props.characterId));
  const controllerRef = useRef<AbortController | null>(null);
  // The heading's id: `aria-labelledby` on the `<section>` names the region "Configuration".
  const headingId = useId();

  // One load on mount; whichever controller is current aborts on unmount.
  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadCharacterConfig(state, controller.signal);
    return () => {
      controller.abort();
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [state]);

  const retry = (): void => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadCharacterConfig(state, controller.signal);
  };

  const save = (patch: CharacterConfigKeyPatch): void => {
    void saveCharacterConfig(state, patch);
  };

  const renderControls = (configuration: CharacterConfiguration): React.JSX.Element => {
    const choices = modelChoices(state);
    return (
      <Stack gap="md">
        <Stack gap={4}>
          <Select
            label="Model"
            description="Applies to sessions started from now on. Existing sessions keep their model."
            data={choices.map((choice) => ({
              value: choice.value,
              label: choice.label,
              disabled: choice.disabled,
            }))}
            value={selectedModelValue(state)}
            allowDeselect={false}
            disabled={state.savingKey === "model"}
            onChange={(value) => {
              if (value === null || value === selectedModelValue(state)) {
                return;
              }
              const choice = choices.find((candidate) => candidate.value === value);
              if (choice === undefined || choice.disabled) {
                return;
              }
              save({ model: choice.model });
            }}
          />
          <Text size="sm" c="dimmed">
            {modelLine(configuration)}
          </Text>
        </Stack>
        <Stack gap={4}>
          <Textarea
            label="Character system prompt"
            autosize
            minRows={2}
            value={state.promptDraft}
            onChange={(event) => setPromptDraft(state, event.currentTarget.value)}
            onBlur={() => {
              void commitPromptDraft(state);
            }}
          />
          <Text size="sm" c="dimmed">
            {promptLine(configuration)}
          </Text>
        </Stack>
        {TOOLS.map((tool) => (
          <ToolControl
            key={tool.key}
            label={tool.label}
            value={configuration[tool.key]}
            disabled={state.savingKey === tool.key}
            onChoose={(choice) => {
              const value = toolPatchValue(choice);
              switch (tool.key) {
                case "tool_memo_search":
                  save({ tool_memo_search: value });
                  break;
                case "tool_session_search":
                  save({ tool_session_search: value });
                  break;
                case "tool_web_search":
                  save({ tool_web_search: value });
                  break;
              }
            }}
          />
        ))}
        {state.failure !== null && <Text c="red">{state.failure}</Text>}
      </Stack>
    );
  };

  const renderBody = (): React.JSX.Element => {
    if (state.configStatus === "failed" || state.modelsStatus === "failed") {
      return (
        <Group gap="sm">
          <Text>Could not load the configuration</Text>
          <Button variant="default" size="xs" onClick={retry}>
            Retry
          </Button>
        </Group>
      );
    }
    if (
      state.configStatus !== "ready" ||
      state.modelsStatus !== "ready" ||
      state.configuration === null
    ) {
      return <Loader size="sm" />;
    }
    return renderControls(state.configuration);
  };

  return (
    <section aria-labelledby={headingId}>
      <Stack gap="xs">
        <Title order={headingOrder} id={headingId}>
          Configuration
        </Title>
        {renderBody()}
      </Stack>
    </section>
  );
});
