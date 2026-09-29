// The admin entry's 404 route element: a statement and a link back to Users.
import type * as React from "react";
import { Link } from "react-router-dom";
import { Anchor, Container, Stack, Text, Title } from "@mantine/core";

export function NotFoundPage(): React.JSX.Element {
  return (
    <Container size="lg" py="md">
      <Stack gap="sm">
        <Title order={2}>Page not found</Title>
        <Text>This page does not exist.</Text>
        <Anchor component={Link} to="/">
          Back to Users
        </Anchor>
      </Stack>
    </Container>
  );
}
