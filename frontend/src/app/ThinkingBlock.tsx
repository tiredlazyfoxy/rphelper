// The collapsible thinking block (022 step 004, D5, D14): a header with the rotated chevron
// toggle ("Show thinking" / "Hide thinking"), a decorative `IconBulb` and the label
// "Thinking"; when open, the think text verbatim as plain pre-wrapped dimmed text (no
// markdown, no `(( ))` painting). The open flag is component-local, initialised once.
import type * as React from "react";
import { useState } from "react";
import { Box, Group, Stack, Text } from "@mantine/core";
import { IconBulb, IconChevronDown } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import type { IconButtonProps } from "../shared/IconButton";

/** The props `IconButton` hands to its `icon` component (size 14 / stroke 1.5 for "chevron"). */
type ChevronProps = {
  size?: number | string;
  stroke?: number;
};

/** The open glyph: `IconChevronDown` pointing down. */
const ChevronOpen: IconButtonProps["icon"] = (props: ChevronProps) => (
  <IconChevronDown size={props.size} stroke={props.stroke} />
);

/** The collapsed glyph: the same chevron, rotated `-90°` (one chevron, rotated — D14). */
const ChevronCollapsed: IconButtonProps["icon"] = (props: ChevronProps) => (
  <IconChevronDown size={props.size} stroke={props.stroke} style={{ transform: "rotate(-90deg)" }} />
);

export type ThinkingBlockProps = {
  /** The think text, rendered verbatim when open. */
  text: string;
  /** Whether the block starts open (live reply) or collapsed (persisted row). Read once. */
  startsOpen: boolean;
  /** Whether the thought is still unterminated (no closing tag yet). Optional, cosmetic. */
  unterminated?: boolean;
};

export function ThinkingBlock(props: ThinkingBlockProps): React.JSX.Element {
  const { text, startsOpen, unterminated = false } = props;
  const [open, setOpen] = useState<boolean>(startsOpen);
  return (
    <Box
      style={{
        border: "1px solid var(--mantine-color-default-border)",
        borderRadius: "var(--mantine-radius-sm)",
      }}
      px="xs"
      py={4}
    >
      <Stack gap={4}>
        <Group gap={6} wrap="nowrap">
          <IconButton
            icon={open ? ChevronOpen : ChevronCollapsed}
            label={open ? "Hide thinking" : "Show thinking"}
            onClick={() => setOpen((value) => !value)}
            sizeVariant="chevron"
          />
          <IconBulb size={16} stroke={1.5} aria-hidden="true" />
          <Text size="sm" c="dimmed" fs={unterminated ? "italic" : undefined}>
            Thinking
          </Text>
        </Group>
        {open ? (
          <Text size="sm" c="dimmed" style={{ whiteSpace: "pre-wrap" }}>
            {text}
          </Text>
        ) : null}
      </Stack>
    </Box>
  );
}
