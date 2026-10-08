// The session configuration modal (feature 017, step 010, D18 / D19, UC-049): a Mantine
// `Modal` titled "Session configuration" whose observer body is mounted only while open and
// builds a fresh `SessionConfigDraft` per open with `useState`. Edits the system prompt, the
// three tool switches, the RP language and the preferred language, each with an explicit
// Inherit choice and the inherited line read from the loaded configuration. No model
// control, no notification, no confirm.
import type * as React from "react";
import { useId, useState } from "react";
import { observer } from "mobx-react-lite";
import { runInAction } from "mobx";
import {
  Alert,
  Button,
  Group,
  Modal,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  Textarea,
} from "@mantine/core";

import type { SessionConfiguration, Setting } from "./configurationApi";
import { SessionConfigDraft, canSubmit, errors, submitSessionConfig } from "./sessionConfigDraft";
import type { TextSource, ToolChoice } from "./sessionConfigDraft";

const TEXT_SEGMENTS: { label: string; value: TextSource }[] = [
  { label: "Inherit", value: "inherit" },
  { label: "Set", value: "set" },
];

const TOOL_SEGMENTS: { label: string; value: ToolChoice }[] = [
  { label: "Inherit", value: "inherit" },
  { label: "On", value: "on" },
  { label: "Off", value: "off" },
];

/** Long inherited text wraps inside the modal instead of widening it. */
const WRAP_STYLE: React.CSSProperties = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" };

function isTextSource(value: string): value is TextSource {
  return value === "inherit" || value === "set";
}

function isToolChoice(value: string): value is ToolChoice {
  return value === "inherit" || value === "on" || value === "off";
}

function toolInheritedLine(setting: Setting<boolean>): string {
  if (setting.inherited_level === "character") {
    return `Inherited from the character: ${setting.inherited === true ? "on" : "off"}`;
  }
  return "Inherited: on (default)";
}

function languageInheritedLine(setting: Setting<string>): string {
  if (setting.inherited_level === "user" && setting.inherited !== null) {
    return `Inherited from your settings: ${setting.inherited}`;
  }
  return "Nothing to inherit: no default in your settings.";
}

type SourceControlProps<V extends string> = {
  label: string;
  data: { label: string; value: V }[];
  value: V;
  onChange: (value: string) => void;
};

/** A labelled `SegmentedControl`: the visible label names the radio group. */
function SourceControl<V extends string>(props: SourceControlProps<V>): React.JSX.Element {
  const labelId = useId();
  return (
    <Stack gap={4}>
      <Text id={labelId} size="sm" fw={500}>
        {props.label}
      </Text>
      <SegmentedControl
        aria-labelledby={labelId}
        data={props.data}
        value={props.value}
        onChange={props.onChange}
      />
    </Stack>
  );
}

type ToolControlProps = {
  label: string;
  value: ToolChoice;
  setting: Setting<boolean>;
  onChange: (value: ToolChoice) => void;
};

function ToolControl(props: ToolControlProps): React.JSX.Element {
  return (
    <Stack gap={4}>
      <SourceControl
        label={props.label}
        data={TOOL_SEGMENTS}
        value={props.value}
        onChange={(value) => {
          if (isToolChoice(value)) {
            props.onChange(value);
          }
        }}
      />
      <Text size="sm" c="dimmed">
        {toolInheritedLine(props.setting)}
      </Text>
    </Stack>
  );
}

type SessionConfigBodyProps = {
  sessionId: string;
  configuration: SessionConfiguration;
  onClose: () => void;
  onSaved: (saved: SessionConfiguration) => void;
};

/** The modal body: owns the per-open draft (mounted only while the modal is open). */
const SessionConfigBody = observer(function SessionConfigBody(
  props: SessionConfigBodyProps,
): React.JSX.Element {
  const { sessionId, configuration, onClose, onSaved } = props;
  const [draft] = useState(() => new SessionConfigDraft(sessionId, configuration));

  const fieldErrors = errors(draft);
  const submitEnabled = canSubmit(draft);
  const submitting = draft.submitStatus === "submitting";

  const onSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!canSubmit(draft)) {
      return;
    }
    void submitSessionConfig(draft, (saved) => {
      onSaved(saved);
      onClose();
    });
  };

  const systemPrompt = configuration.system_prompt;

  return (
    <form onSubmit={onSubmit} noValidate>
      <Stack gap="md">
        <Stack gap={4}>
          <SourceControl
            label="System prompt"
            data={TEXT_SEGMENTS}
            value={draft.systemPromptSource}
            onChange={(value) => {
              if (isTextSource(value)) {
                runInAction(() => {
                  draft.systemPromptSource = value;
                });
              }
            }}
          />
          {draft.systemPromptSource === "set" && (
            <Textarea
              label="Session system prompt"
              autosize
              minRows={3}
              value={draft.systemPrompt}
              error={fieldErrors.systemPrompt}
              onChange={(event) => {
                const text = event.currentTarget.value;
                runInAction(() => {
                  draft.systemPrompt = text;
                });
              }}
            />
          )}
          {systemPrompt.inherited_level === "character" && systemPrompt.inherited !== null ? (
            <Stack gap={2}>
              <Text size="sm" c="dimmed">
                Inherited from the character:
              </Text>
              <Text size="sm" style={WRAP_STYLE}>
                {systemPrompt.inherited}
              </Text>
            </Stack>
          ) : (
            <Text size="sm" c="dimmed">
              Nothing to inherit: the character has no system prompt.
            </Text>
          )}
        </Stack>

        <ToolControl
          label="Memo search"
          value={draft.toolMemoSearch}
          setting={configuration.tool_memo_search}
          onChange={(value) => {
            runInAction(() => {
              draft.toolMemoSearch = value;
            });
          }}
        />
        <ToolControl
          label="Session search"
          value={draft.toolSessionSearch}
          setting={configuration.tool_session_search}
          onChange={(value) => {
            runInAction(() => {
              draft.toolSessionSearch = value;
            });
          }}
        />
        <ToolControl
          label="Web search"
          value={draft.toolWebSearch}
          setting={configuration.tool_web_search}
          onChange={(value) => {
            runInAction(() => {
              draft.toolWebSearch = value;
            });
          }}
        />

        <Stack gap={4}>
          <SourceControl
            label="RP language"
            data={TEXT_SEGMENTS}
            value={draft.rpLanguageSource}
            onChange={(value) => {
              if (isTextSource(value)) {
                runInAction(() => {
                  draft.rpLanguageSource = value;
                });
              }
            }}
          />
          {draft.rpLanguageSource === "set" && (
            <TextInput
              label="Session RP language"
              autoComplete="off"
              value={draft.rpLanguage}
              error={fieldErrors.rpLanguage}
              onChange={(event) => {
                const text = event.currentTarget.value;
                runInAction(() => {
                  draft.rpLanguage = text;
                });
              }}
            />
          )}
          <Text size="sm" c="dimmed" style={WRAP_STYLE}>
            {languageInheritedLine(configuration.rp_language)}
          </Text>
        </Stack>

        <Stack gap={4}>
          <SourceControl
            label="Preferred language"
            data={TEXT_SEGMENTS}
            value={draft.preferredLanguageSource}
            onChange={(value) => {
              if (isTextSource(value)) {
                runInAction(() => {
                  draft.preferredLanguageSource = value;
                });
              }
            }}
          />
          {draft.preferredLanguageSource === "set" && (
            <TextInput
              label="Session preferred language"
              autoComplete="off"
              value={draft.preferredLanguage}
              error={fieldErrors.preferredLanguage}
              onChange={(event) => {
                const text = event.currentTarget.value;
                runInAction(() => {
                  draft.preferredLanguage = text;
                });
              }}
            />
          )}
          <Text size="sm" c="dimmed" style={WRAP_STYLE}>
            {languageInheritedLine(configuration.preferred_language)}
          </Text>
        </Stack>

        {fieldErrors.general !== undefined && <Alert color="red">{fieldErrors.general}</Alert>}

        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!submitEnabled} loading={submitting}>
            Save
          </Button>
        </Group>
      </Stack>
    </form>
  );
});

export type SessionConfigModalProps = {
  /** Whether the modal is open; the body (and its draft) exists only while true. */
  opened: boolean;
  /** The session being configured. A string, never parsed. */
  sessionId: string;
  /** The loaded configuration the draft is seeded from and the inherited lines read. */
  configuration: SessionConfiguration;
  /** Close without saving (Cancel, the close button, Escape, the overlay). */
  onClose: () => void;
  /** Called with the saved configuration after a successful Save, before `onClose`. */
  onSaved: (saved: SessionConfiguration) => void;
};

export function SessionConfigModal(props: SessionConfigModalProps): React.JSX.Element {
  const { opened, sessionId, configuration, onClose, onSaved } = props;
  return (
    <Modal opened={opened} onClose={onClose} title="Session configuration" centered>
      {opened && (
        <SessionConfigBody
          sessionId={sessionId}
          configuration={configuration}
          onClose={onClose}
          onSaved={onSaved}
        />
      )}
    </Modal>
  );
}
