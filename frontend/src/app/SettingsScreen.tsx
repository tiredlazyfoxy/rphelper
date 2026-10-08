// The settings screen at `/settings` (feature 017, step 007, D15 / D19): a "Settings"
// heading, the "Languages" form backed by `SettingsState`, and the user's own notes as the
// shared `MemoLevelGroup` titled "Your notes" (not reorderable). No notification anywhere.
import type * as React from "react";
import { useEffect, useId, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import { Alert, Button, Group, Loader, Stack, Text, TextInput, Title } from "@mantine/core";

import {
  SettingsState,
  canSave,
  loadSettings,
  saveSettings,
  setPreferredLanguage,
  setRpLanguage,
} from "./settingsState";
import { MemoLevelState, loadMemoLevel } from "./memoLevelState";
import { MemoLevelGroup } from "./MemoLevelGroup";

const LANGUAGE_DESCRIPTION = "Used by every session that does not set its own.";

export const SettingsScreen = observer(function SettingsScreen(): React.JSX.Element {
  const [settings] = useState(() => new SettingsState());
  const [notes] = useState(() => new MemoLevelState("user", null));
  const settingsControllerRef = useRef<AbortController | null>(null);
  const notesControllerRef = useRef<AbortController | null>(null);
  const languagesHeadingId = useId();

  // One load of each on mount; whichever controller is current aborts on unmount.
  useEffect(() => {
    const controller = new AbortController();
    settingsControllerRef.current = controller;
    void loadSettings(settings, controller.signal);
    return () => {
      controller.abort();
      settingsControllerRef.current?.abort();
      settingsControllerRef.current = null;
    };
  }, [settings]);

  useEffect(() => {
    const controller = new AbortController();
    notesControllerRef.current = controller;
    void loadMemoLevel(notes, controller.signal);
    return () => {
      controller.abort();
      notesControllerRef.current?.abort();
      notesControllerRef.current = null;
    };
  }, [notes]);

  const retrySettings = (): void => {
    settingsControllerRef.current?.abort();
    const controller = new AbortController();
    settingsControllerRef.current = controller;
    void loadSettings(settings, controller.signal);
  };

  const retryNotes = (): void => {
    notesControllerRef.current?.abort();
    const controller = new AbortController();
    notesControllerRef.current = controller;
    void loadMemoLevel(notes, controller.signal);
  };

  const renderLanguages = (): React.JSX.Element => {
    if (settings.status === "failed") {
      return (
        <Group gap="xs">
          <Text c="red">Could not load your settings</Text>
          <Button variant="default" onClick={retrySettings}>
            Retry
          </Button>
        </Group>
      );
    }
    if (settings.status !== "ready") {
      return <Loader />;
    }
    return (
      <Stack gap="sm">
        <TextInput
          label="RP language"
          description={LANGUAGE_DESCRIPTION}
          value={settings.rpLanguage}
          onChange={(event) => {
            setRpLanguage(settings, event.currentTarget.value);
          }}
        />
        <TextInput
          label="Preferred language"
          description={LANGUAGE_DESCRIPTION}
          value={settings.preferredLanguage}
          onChange={(event) => {
            setPreferredLanguage(settings, event.currentTarget.value);
          }}
        />
        {settings.saveFailure !== null && <Alert color="red">{settings.saveFailure}</Alert>}
        <Group>
          <Button
            disabled={!canSave(settings)}
            onClick={() => {
              void saveSettings(settings);
            }}
          >
            Save
          </Button>
        </Group>
      </Stack>
    );
  };

  // "Settings" at the centre screens' main heading level; both regions one level below.
  return (
    <Stack gap="lg">
      <Title order={2}>Settings</Title>
      <section aria-labelledby={languagesHeadingId}>
        <Stack gap="xs">
          <Title order={3} id={languagesHeadingId}>
            Languages
          </Title>
          {renderLanguages()}
        </Stack>
      </section>
      <MemoLevelGroup state={notes} title="Your notes" headingOrder={3} onRetry={retryNotes} />
    </Stack>
  );
});
