// The session stream (feature 013, step 007, D12, D13, D15): owns one `StreamState` per
// mount, loads it with an `AbortController` aborted on unmount, and renders by status — a
// centred loader, the in-place "Could not load the stream" / "Retry" failure, or, ready, the
// 720px column: `StreamRecord`, the single "Current zone" ruler, `KindSwitch`, `ZoneList`,
// `Composer`. Mounted by `SessionScreen`'s ready render; keyed per session by `SessionRoute`.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import { Box, Button, Center, Divider, Loader, Stack, Text } from "@mantine/core";

import { Composer } from "./Composer";
import { KindSwitch } from "./KindSwitch";
import { StreamRecord } from "./StreamRecord";
import { ZoneList } from "./ZoneList";
import { StreamState, loadStream } from "./streamState";

export type SessionStreamProps = {
  sessionId: string;
};

/** The ruler's visible label and accessible name — the stream's only separator (D12). */
const RULER_LABEL = "Current zone";

/** The session's record, ruler, kind switch, zone and composer (D12, D13, D15). */
export const SessionStream = observer(function SessionStream(
  props: SessionStreamProps,
): React.JSX.Element {
  // Created once per mount; `SessionRoute` keys the screen by session id, so another session
  // remounts the stream with fresh state.
  const [state] = useState(() => new StreamState(props.sessionId));
  const controllerRef = useRef<AbortController | null>(null);

  // One controller per mount, created inside the effect so a StrictMode double-mount aborts
  // the first and creates a second; a late response after unmount writes nothing.
  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadStream(state, controller.signal);
    return () => {
      controller.abort();
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    };
  }, [state]);

  const signal = controllerRef.current?.signal;

  const retry = (): void => {
    void loadStream(state, controllerRef.current?.signal);
  };

  // D15: the load failure has a place of its own, so it is rendered here, never notified.
  if (state.status === "failed") {
    return (
      <Stack gap="md" align="flex-start" maw={720} mx="auto" px={18}>
        <Text>Could not load the stream</Text>
        <Button onClick={retry}>Retry</Button>
      </Stack>
    );
  }

  if (state.status !== "ready") {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }

  // R6: archived sessions are not distinguished — the same stream renders and works.
  return (
    <Box maw={720} mx="auto" px={18} w="100%">
      <Stack gap="md">
        <StreamRecord state={state} signal={signal} />
        <Divider label={RULER_LABEL} labelPosition="center" aria-label={RULER_LABEL} />
        <KindSwitch state={state} />
        <ZoneList state={state} signal={signal} />
        <Composer state={state} signal={signal} />
      </Stack>
    </Box>
  );
});
