// The Discussion group under a settled entry (022 step 007, D11, D12, U1): collapsed by
// default with a "Show discussion" chevron, the "Discussion" / "Discussion (N)" label and a
// "Read-only" marker. The first expand lazily loads the entry's buried rows through
// `fetchDiscussion` (own AbortController, aborted on unmount) and renders them read-only
// through `ZoneMessage` with `editable` false, or the empty line, or an inline failure line.
// Open flag, load status and rows are component-local `useState`.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { Box, Group, Loader, Stack, Text } from "@mantine/core";
import { IconChevronDown } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import type { IconButtonProps } from "../shared/IconButton";
import { fetchDiscussion } from "./streamApi";
import type { Message } from "./streamApi";
import type { StreamState } from "./streamState";
import { ZoneMessage } from "./ZoneList";

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

/** Where the lazy load stands (D11). A failure is forgotten on collapse. */
type LoadStatus = "idle" | "loading" | "loaded" | "failed";

export type DiscussionGroupProps = {
  /** The settled entry's id; the discussion is `GET /api/messages/<entryId>/discussion`. */
  entryId: string;
  /** Passed through to `ZoneMessage`. */
  state: StreamState;
};

export function DiscussionGroup(props: DiscussionGroupProps): React.JSX.Element {
  const { entryId, state } = props;
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<LoadStatus>("idle");
  const [rows, setRows] = useState<Message[] | null>(null);

  // The in-flight request's controller, and whether the group is still mounted: nothing is
  // written after unmount, and the pending request is aborted.
  const controllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(false);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, []);

  function load(): void {
    const controller = new AbortController();
    controllerRef.current = controller;
    setStatus("loading");
    fetchDiscussion(entryId, controller.signal).then(
      (messages) => {
        if (!mountedRef.current || controller.signal.aborted) {
          return;
        }
        controllerRef.current = null;
        setRows(messages);
        setStatus("loaded");
      },
      () => {
        if (!mountedRef.current || controller.signal.aborted) {
          return;
        }
        controllerRef.current = null;
        setStatus("failed");
      },
    );
  }

  function toggle(): void {
    if (open) {
      setOpen(false);
      if (status === "failed") {
        setStatus("idle"); // the failure is forgotten, so the next expand retries (D11)
      }
      return;
    }
    setOpen(true);
    if (status === "idle" || status === "failed") {
      load();
    }
  }

  const label = rows === null ? "Discussion" : `Discussion (${rows.length})`;

  let body: React.ReactNode = null;
  if (open) {
    if (status === "loading" || status === "idle") {
      body = <Loader size="sm" />;
    } else if (status === "failed") {
      body = (
        <Text size="sm" c="dimmed">
          The discussion could not be loaded.
        </Text>
      );
    } else if (rows !== null && rows.length > 0) {
      body = (
        <Box component="ul" aria-label="Discussion messages" m={0} p={0} style={{ listStyle: "none" }}>
          {rows.map((message) => (
            <ZoneMessage key={message.id} state={state} message={message} editable={false} />
          ))}
        </Box>
      );
    } else {
      body = (
        <Text size="sm" c="dimmed">
          No discussion behind this entry.
        </Text>
      );
    }
  }

  return (
    <Stack gap={4}>
      <Group gap={6} wrap="nowrap">
        <IconButton
          icon={open ? ChevronOpen : ChevronCollapsed}
          label={open ? "Hide discussion" : "Show discussion"}
          onClick={toggle}
          sizeVariant="chevron"
        />
        <Text size="sm" c="dimmed">
          {label}
        </Text>
        <Text size="xs" c="dimmed" fs="italic">
          Read-only
        </Text>
      </Group>
      {body}
    </Stack>
  );
}
