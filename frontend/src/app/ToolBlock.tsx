// The collapsible tool-call block (022 step 004, D5, D7, D14): a header with the rotated
// chevron toggle ("Show tool call" / "Hide tool call"), a decorative `IconTool`, the tool
// name (or "Unknown tool") and a status word ("Running" / "Done" / "Failed"); when open,
// "Arguments" with the pretty-printed arguments (or "No arguments.") and the summary. The
// open flag is component-local, initialised once; a status change never changes it.
import type * as React from "react";
import { useState } from "react";
import { Box, Code, Group, Stack, Text } from "@mantine/core";
import { IconChevronDown, IconTool } from "@tabler/icons-react";

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

const STATUS_WORDS: Record<"running" | "ok" | "failed", string> = {
  running: "Running",
  ok: "Done",
  failed: "Failed",
};

/** A tool call's status as a block shows it: live calls may still be running. */
export type ToolBlockStatus = "running" | "ok" | "failed";

export type ToolBlockProps = {
  /** The tool name; null or absent renders "Unknown tool". */
  name?: string | null;
  status: ToolBlockStatus;
  /** The call's arguments, pretty-printed as JSON when open. */
  args: Record<string, unknown>;
  /** The call's summary, rendered as plain text when open and non-null. */
  summary: string | null;
  /** Whether the block starts open (live reply) or collapsed (persisted row). Read once. */
  startsOpen: boolean;
};

export function ToolBlock(props: ToolBlockProps): React.JSX.Element {
  const { name, status, args, summary, startsOpen } = props;
  const [open, setOpen] = useState<boolean>(startsOpen);
  const hasArgs = Object.keys(args).length > 0;
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
            label={open ? "Hide tool call" : "Show tool call"}
            onClick={() => setOpen((value) => !value)}
            sizeVariant="chevron"
          />
          <IconTool size={16} stroke={1.5} aria-hidden="true" />
          <Text size="sm" fw={500}>
            {name ?? "Unknown tool"}
          </Text>
          <Text size="sm" c={status === "failed" ? "red" : "dimmed"}>
            {STATUS_WORDS[status]}
          </Text>
        </Group>
        {open ? (
          <Stack gap={4}>
            <Text size="xs" c="dimmed">
              Arguments
            </Text>
            {hasArgs ? (
              <Code block>{JSON.stringify(args, null, 2)}</Code>
            ) : (
              <Text size="sm" c="dimmed">
                No arguments.
              </Text>
            )}
            {summary !== null ? (
              <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
                {summary}
              </Text>
            ) : null}
          </Stack>
        ) : null}
      </Stack>
    </Box>
  );
}
