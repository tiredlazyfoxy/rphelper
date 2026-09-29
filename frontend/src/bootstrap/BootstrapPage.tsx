// The bootstrap entry's page: renders exactly one of the five phases. Store passed as a prop.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { Alert, Anchor, Button, Container, Group, List, Loader, Stack, Text, Title } from "@mantine/core";
import { observer } from "mobx-react-lite";
import {
  bootstrapPhase,
  startProbeLoop,
  stopProbeLoop,
  type BootstrapState,
  type ProbeLoop,
} from "./bootstrapState";
import { CreateAdminForm } from "./CreateAdminForm";
import { CreateAdminDraft } from "./createAdminDraft";

export type BootstrapPageProps = {
  state: BootstrapState;
};

function RetryButton(props: { onRetry: () => void }): React.JSX.Element {
  return (
    <Group>
      <Button variant="default" onClick={props.onRetry}>
        Retry
      </Button>
    </Group>
  );
}

/** The offer state's form mount: a fresh draft per mount, created once. */
function CreateAdminMount(props: { state: BootstrapState }): React.JSX.Element {
  const [draft] = useState(() => new CreateAdminDraft());
  return <CreateAdminForm state={props.state} draft={draft} />;
}

export const BootstrapPage = observer(function BootstrapPage(
  props: BootstrapPageProps,
): React.JSX.Element {
  const { state } = props;
  const loopRef = useRef<ProbeLoop | null>(null);

  useEffect(() => {
    loopRef.current = startProbeLoop(state);
    return () => {
      if (loopRef.current !== null) {
        stopProbeLoop(loopRef.current);
        loopRef.current = null;
      }
    };
  }, [state]);

  const retry = (): void => {
    if (loopRef.current !== null) {
      stopProbeLoop(loopRef.current);
    }
    loopRef.current = startProbeLoop(state);
  };

  const phase = bootstrapPhase(state);
  let content: React.JSX.Element;
  switch (phase) {
    case "probing":
      content = (
        <Group gap="sm">
          <Loader size="sm" />
          <Text c="dimmed">Checking the instance…</Text>
        </Group>
      );
      break;
    case "offer":
      content = (
        <Stack gap="md">
          <Title order={1}>This instance is not configured yet</Title>
          <Text>Choose how to set it up.</Text>
          <List>
            <List.Item>
              <Stack gap="xs">
                <Text fw={600}>Create a new database</Text>
                <Text c="dimmed" size="sm">
                  Start fresh with an empty database and an administrator account.
                </Text>
                <CreateAdminMount state={state} />
              </Stack>
            </List.Item>
          </List>
        </Stack>
      );
      break;
    case "refusal":
      content = (
        <Stack gap="md">
          <Title order={1}>This instance is already configured</Title>
          <Text>Setup has already been done here, so there is nothing to set up again.</Text>
          <Text>
            <Anchor href="/login">Sign in</Anchor> to continue.
          </Text>
        </Stack>
      );
      break;
    case "not-ready":
      content = (
        <Stack gap="md">
          <Title order={1}>The instance is still starting</Title>
          <Text>
            Please wait a moment. This page keeps checking and will continue on its own once the
            instance is ready.
          </Text>
          <RetryButton onRetry={retry} />
        </Stack>
      );
      break;
    case "failed":
      content = (
        <Stack gap="md">
          <Alert color="red" title="The instance could not be checked">
            {state.failureMessage}
          </Alert>
          <RetryButton onRetry={retry} />
        </Stack>
      );
      break;
  }

  return (
    <div data-entry="bootstrap">
      <Container size="sm" py="xl">
        {content}
      </Container>
    </div>
  );
});
