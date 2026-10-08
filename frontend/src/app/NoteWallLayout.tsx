// The session screen's two-part layout (016 context.md D1, D2, D3, D11): a stream column
// and the note wall `aside`, with the wall's pin and close controls. The wall is mounted
// always, at the same place in the tree, and is inert and hidden from assistive technology
// while closed.
import type * as React from "react";
import { observer } from "mobx-react-lite";
import { Box, Group, Paper } from "@mantine/core";
import { IconPin, IconX } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import type { LayoutStorage } from "./workspaceLayout";
import {
  dismissWall,
  isWallVisible,
  sessionLayoutClassName,
  toggleWallPin,
  wallClassName,
  wallMode,
  type NoteWallState,
} from "./noteWallState";

/** The pin toggle's active-state colour while the wall is pinned (D10). */
const PINNED_COLOR = "blue";

export type NoteWallLayoutProps = {
  /** The screen's wall state, created once per session screen mount. */
  state: NoteWallState;
  /** True below the 820px threshold; computed by the caller. */
  narrow: boolean;
  /** The layout record's storage, written by the pin toggle and an unpinning dismiss. */
  storage: LayoutStorage | null;
  /** The stream column's content. */
  stream: React.ReactNode;
  /** The wall's content; never remounted across mode or visibility changes. */
  wall: React.ReactNode;
};

export const NoteWallLayout = observer(function NoteWallLayout(
  props: NoteWallLayoutProps,
): React.JSX.Element {
  const { state, narrow, storage, stream, wall } = props;
  const visible = isWallVisible(state, narrow);
  const floating = wallMode(state, narrow) === "floating";

  return (
    <div className={sessionLayoutClassName(state, narrow)}>
      <Box className="app-stream">{stream}</Box>
      <Paper
        component="aside"
        aria-label="Note wall"
        className={wallClassName(state, narrow)}
        shadow={floating && visible ? "md" : undefined}
        radius={0}
        inert={visible ? undefined : true}
        aria-hidden={visible ? undefined : "true"}
      >
        <Group justify="flex-end" gap="xs" wrap="nowrap" p="xs">
          <IconButton
            icon={IconPin}
            label={state.pinned ? "Unpin notes" : "Pin notes"}
            color={state.pinned ? PINNED_COLOR : undefined}
            onClick={() => {
              toggleWallPin(state, storage);
            }}
          />
          <IconButton
            icon={IconX}
            label="Close notes"
            onClick={() => {
              dismissWall(state, storage, narrow);
            }}
          />
        </Group>
        {wall}
      </Paper>
    </div>
  );
});
