// The live reply (022 step 006, D6, U4): while streaming, a read-only "Live reply" region
// beneath the zone rows with the author label "Assistant", one open `ToolBlock` per live
// tool call in list order, then `AssistantBody` over the streaming text with `live` true.
// Renders nothing when not streaming. No edit control, no other control.
import type * as React from "react";
import { observer } from "mobx-react-lite";
import { Box, Stack, Text } from "@mantine/core";

import { AssistantBody } from "./AssistantBody";
import { ToolBlock } from "./ToolBlock";
import { isStreaming } from "./streamState";
import type { StreamState } from "./streamState";

export type LiveMessageProps = {
  state: StreamState;
};

export const LiveMessage = observer(function LiveMessage(
  props: LiveMessageProps,
): React.JSX.Element | null {
  const { state } = props;
  if (!isStreaming(state)) {
    return null;
  }

  return (
    <Box component="section" aria-label="Live reply" mb="md">
      <Stack gap="xs">
        <Text size="sm" fw={600} c="dimmed">
          Assistant
        </Text>
        {state.liveTools.map((call) => (
          <ToolBlock
            key={call.callId}
            name={call.tool}
            status={call.status}
            args={call.args}
            summary={call.summary}
            startsOpen
          />
        ))}
        <AssistantBody text={state.streamingText ?? ""} live />
      </Stack>
    </Box>
  );
});
