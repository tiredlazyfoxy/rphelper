// The `app` entry's two boot screens (008 context.md D2): the not-ready state and the
// failure panel. Both are full-page states, so neither raises a notification — this file
// must never import `shared/notifyFailure` or `@mantine/notifications`
// (`ui-conventions.md`: a failure with a full-page state of its own is not also a toast).
// Plain function components: they read no observable and hold no MobX state.
import type * as React from "react";
import { Button, Container, Group, Stack, Text, Title } from "@mantine/core";

export type AppNotReadyProps = {
  /** Invoked by "Retry now"; the caller re-probes at once. */
  onRetry: () => void;
};

export type AppBootFailedProps = {
  /** Invoked by "Retry"; the caller restarts the boot and re-probes. */
  onRetry: () => void;
};

/**
 * The not-ready full-page state: the title "RPHelper is not ready yet", the line "The
 * server is not answering yet. Retrying automatically." and a "Retry now" button.
 *
 * The automatic re-probe is the gate's; this screen only says that it happens and offers
 * the manual shortcut.
 */
export function AppNotReady(props: AppNotReadyProps): React.JSX.Element {
  return (
    <Container size="sm" py="xl">
      <Stack gap="md">
        <Title order={1}>RPHelper is not ready yet</Title>
        <Text>The server is not answering yet. Retrying automatically.</Text>
        <Group>
          <Button variant="default" onClick={props.onRetry}>
            Retry now
          </Button>
        </Group>
      </Stack>
    </Container>
  );
}

/**
 * The failure full-page state: the title "Could not load your account" and a "Retry"
 * button. No automatic re-probe is armed from here — that is the gate's decision.
 */
export function AppBootFailed(props: AppBootFailedProps): React.JSX.Element {
  return (
    <Container size="sm" py="xl">
      <Stack gap="md">
        <Title order={1}>Could not load your account</Title>
        <Group>
          <Button variant="default" onClick={props.onRetry}>
            Retry
          </Button>
        </Group>
      </Stack>
    </Container>
  );
}
