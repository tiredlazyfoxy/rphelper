// Stateless screen for the gate's two rendered outcomes: not-ready and failed.
import type * as React from "react";
import { Alert, Button, Container, Group, Stack, Text, Title } from "@mantine/core";
import type { AdminAccessDecision } from "./adminAccess";

export type AdminNotReadyProps = {
  variant: Extract<AdminAccessDecision, "not-ready" | "failed">;
  message?: string;
  onRetry: () => void;
};

const FALLBACK_FAILURE_MESSAGE = "Your access to the admin area could not be checked.";

export function AdminNotReady(props: AdminNotReadyProps): React.JSX.Element {
  const content =
    props.variant === "not-ready" ? (
      <>
        <Title order={1}>The instance is still starting</Title>
        <Text>
          Please wait a moment. This page keeps checking and will continue on its own once the
          instance is ready.
        </Text>
      </>
    ) : (
      <Alert color="red" title="The admin area could not be opened">
        {props.message ?? FALLBACK_FAILURE_MESSAGE}
      </Alert>
    );

  return (
    <Container size="sm" py="xl">
      <Stack gap="md">
        {content}
        <Group>
          <Button variant="default" onClick={props.onRetry}>
            Retry
          </Button>
        </Group>
      </Stack>
    </Container>
  );
}
