// The session screen's "Notes" region (feature 015, step 008, D1 / D16 / R2): creates and
// loads its own `MemoChainState`, then renders one `MemoLevelGroup` per chain level in the
// server's order (the setup group absent when the session has none), with its own loading
// and failed states. Mounted by `SessionScreen`'s ready render.
import type * as React from "react";
import { useEffect, useId, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import { Button, Loader, Stack, Text, Title } from "@mantine/core";
import { DndContext, type DragEndEvent } from "@dnd-kit/core";

import type { MemoScope } from "./memosApi";
import { MemoChainState, loadMemoChain } from "./memoChainState";
import { MemoLevelGroup } from "./MemoLevelGroup";
import { memoAnnouncements, useMemoDndSensors } from "./memoDnd";
import { applyMemoDrop } from "./memoReorder";

/** Each level's group title (private to this section). */
const LEVEL_TITLES: Record<MemoScope, string> = {
  user: "Your notes",
  character: "Character notes",
  setup: "Setup notes",
  session: "Session notes",
};

/** The chain's groups are always "ready", so their Retry is unreachable. */
const noop = (): void => {};

export type MemoChainSectionProps = {
  /** The loaded session's id. A string, never parsed. */
  sessionId: string;
};

export const MemoChainSection = observer(function MemoChainSection(
  props: MemoChainSectionProps,
): React.JSX.Element {
  // Created once, never with `useMemo`; `SessionRoute` keys the screen by the session id, so
  // a different session remounts this section with fresh chain state (D16).
  const [state] = useState(() => new MemoChainState(props.sessionId));
  const controllerRef = useRef<AbortController | null>(null);
  // The heading's id: `aria-labelledby` on the `<section>` names the region "Notes".
  const headingId = useId();
  // D8: the shared sensor set (6px pointer distance, keyboard path) from `memoDnd`.
  const sensors = useMemoDndSensors();

  const handleDragEnd = (event: DragEndEvent): void => {
    void applyMemoDrop(
      state.levels,
      String(event.active.id),
      event.over ? String(event.over.id) : null,
    );
  };

  // One load on mount; whichever controller is current aborts on unmount.
  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadMemoChain(state, controller.signal);
    return () => {
      controller.abort();
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [state]);

  const retry = (): void => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadMemoChain(state, controller.signal);
  };

  const renderBody = (): React.JSX.Element => {
    if (state.status === "failed") {
      // Inline only — nothing is notified.
      return (
        <Stack gap="xs" align="flex-start">
          <Text size="sm">Could not load notes</Text>
          <Button size="xs" variant="default" onClick={retry}>
            Retry
          </Button>
        </Stack>
      );
    }

    if (state.status !== "ready") {
      return <Loader size="sm" />;
    }

    // R2: whatever levels the server returned, in its order; scope is unique per chain.
    // D8: one `DndContext` over the whole chain; each group holds its own `SortableContext`.
    return (
      <DndContext
        sensors={sensors}
        onDragEnd={handleDragEnd}
        accessibility={{
          announcements: memoAnnouncements(
            state.levels.map((level) => ({
              title: LEVEL_TITLES[level.scope],
              ids: level.memos.map((memo) => memo.id),
            })),
          ),
        }}
      >
        <Stack gap="md">
          {state.levels.map((level) => (
            <MemoLevelGroup
              key={level.scope}
              state={level}
              title={LEVEL_TITLES[level.scope]}
              headingOrder={4}
              onRetry={noop}
              reorderable
            />
          ))}
        </Stack>
      </DndContext>
    );
  };

  return (
    <section aria-labelledby={headingId}>
      <Stack gap="xs">
        {/* One level below the session header's start-time heading (order 2). */}
        <Title order={3} id={headingId}>
          Notes
        </Title>
        {renderBody()}
      </Stack>
    </section>
  );
});
