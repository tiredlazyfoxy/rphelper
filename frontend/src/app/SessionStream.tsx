// The session stream (feature 013, step 007, D12, D13, D15): owns one `StreamState` per
// mount, loads it with an `AbortController` aborted on unmount, and renders by status — a
// centred loader, the in-place "Could not load the stream" / "Retry" failure, or, ready, the
// 720px column: `StreamRecord`, the single "Current zone" ruler, `KindSwitch`, `ZoneList`,
// `Composer`. Mounted by `SessionScreen`'s ready render; keyed per session by `SessionRoute`.
// Feature 023, step 005 (D13): it owns one `TranslationState` per mount the same way, hands it
// to `StreamRecord`, and disposes it — aborting every pending translate request — on unmount.
// Feature 029, step 006 (D8): it also forwards an optional `focusEntryId` straight through to
// `StreamRecord`. It deliberately reads no router hook — `SessionScreen` owns the URL.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import { Alert, Box, Button, Center, Divider, Loader, Stack, Text } from "@mantine/core";

import { Composer } from "./Composer";
import { KindSwitch } from "./KindSwitch";
import { StreamRecord } from "./StreamRecord";
import { ZoneList } from "./ZoneList";
import { StreamState, composeFirstReply, loadStream } from "./streamState";
import { TranslationState, disposeTranslations } from "./translationState";

export type SessionStreamProps = {
  sessionId: string;
  /** 017 D17: passed unchanged to `Composer`. Defaults to null. */
  sendBlockedReason?: string | null;
  /**
   * 029 `006` (D8): the `?entry=` message id this arrival should anchor on, passed unchanged
   * to `StreamRecord`. **Optional, defaults to none** — the stream reads no URL of its own
   * (it uses no router hook at all), so the id can only come from `SessionScreen`. Without it
   * nothing is scrolled to and nothing is highlighted, which is every other caller's case.
   */
  focusEntryId?: string | null;
  /**
   * fast/004 D2/D3: whether this arrival carried the character page's first-reply marker, as
   * decided once by `SessionScreen`. **Optional, absent means false.** When true, after the
   * load resolves ready the stream starts `composeFirstReply` with its own signal.
   */
  firstReply?: boolean;
};

/** The ruler's visible label and accessible name — the stream's only separator (D12). */
const RULER_LABEL = "Current zone";

/**
 * 024 step 007 (US-112.AC-2): the coverage banner's sentence, exactly as `007.context.md`
 * pins it. Non-blocking: it informs and disables nothing.
 */
const COVERAGE_BANNER_TEXT =
  "Search coverage is incomplete. Your latest change was saved, but it could not be indexed for search.";

/** The session's record, ruler, kind switch, zone and composer (D12, D13, D15). */
export const SessionStream = observer(function SessionStream(
  props: SessionStreamProps,
): React.JSX.Element {
  // Created once per mount; `SessionRoute` keys the screen by session id, so another session
  // remounts the stream with fresh state.
  const [state] = useState(() => new StreamState(props.sessionId));
  // 023 D13: one flicker state per mount too, so its per-row cache lives exactly as long as the
  // record it belongs to. Another session remounts and starts empty.
  const [translations] = useState(() => new TranslationState());
  const controllerRef = useRef<AbortController | null>(null);
  const firstReply = props.firstReply ?? false;

  // 023 D13: on unmount every pending translate request is aborted. Nothing is notified.
  useEffect(() => {
    return () => {
      disposeTranslations(translations);
    };
  }, [translations]);

  // One controller per mount, created inside the effect so a StrictMode double-mount aborts
  // the first and creates a second; a late response after unmount writes nothing.
  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    // fast/004 D3: once the load resolves ready, the first reply starts on this signal;
    // `composeFirstReply` itself guards readiness, the zone, the abort and the once-flag.
    void loadStream(state, controller.signal).then(() => {
      if (firstReply && !controller.signal.aborted && state.status === "ready") {
        void composeFirstReply(state, controller.signal);
      }
    });
    return () => {
      controller.abort();
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    };
  }, [state, firstReply]);

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
        {/*
          024 step 007 (D11, US-112.AC-2): the coverage notice, rendered only while the flag is
          set, immediately above the record and before the first entry in document order. No
          close button, no new prop, and nothing below it is disabled.
        */}
        {state.searchCoverageIncomplete ? (
          <Alert role="alert" color="yellow">
            {COVERAGE_BANNER_TEXT}
          </Alert>
        ) : null}
        <StreamRecord
          state={state}
          signal={signal}
          translations={translations}
          focusEntryId={props.focusEntryId ?? null}
        />
        <Divider label={RULER_LABEL} labelPosition="center" aria-label={RULER_LABEL} />
        <KindSwitch state={state} />
        <ZoneList state={state} signal={signal} />
        <Composer
          state={state}
          signal={signal}
          sendBlockedReason={props.sendBlockedReason ?? null}
        />
      </Stack>
    </Box>
  );
});
