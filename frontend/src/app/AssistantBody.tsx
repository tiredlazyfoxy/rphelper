// The assistant message body (022 step 004, D4, D5): splits the text with `splitThinking`
// and renders each think segment as a `ThinkingBlock` (open iff `live`) and each answer
// segment through `MessageBody` variant "painted", in order. Callers use it only for
// `role: "assistant"`.
import type * as React from "react";
import { Stack } from "@mantine/core";

import { MessageBody } from "./MessageBody";
import { ThinkingBlock } from "./ThinkingBlock";
import { splitThinking } from "./thinking";

export type AssistantBodyProps = {
  /** The assistant text, possibly holding `<think>` blocks. */
  text: string;
  /** True in the live reply (thinking starts open); false on a persisted row. */
  live: boolean;
};

export function AssistantBody(props: AssistantBodyProps): React.JSX.Element {
  const { text, live } = props;
  const segments = splitThinking(text);
  if (segments.length === 1 && segments[0].kind === "answer") {
    // No think block (D4 row 1): exactly the painted body as it rendered before 022.
    return <MessageBody text={segments[0].text} variant="painted" />;
  }
  return (
    <Stack gap="xs">
      {segments.map((segment, index) =>
        segment.kind === "think" ? (
          <ThinkingBlock
            key={index}
            text={segment.text}
            startsOpen={live}
            unterminated={!segment.closed}
          />
        ) : (
          <MessageBody key={index} text={segment.text} variant="painted" />
        ),
      )}
    </Stack>
  );
}
