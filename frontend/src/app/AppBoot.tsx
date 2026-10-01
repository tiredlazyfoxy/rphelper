// The `app` entry's boot gate (008 context.md D2): nothing of the shell renders until
// `GET /api/me` resolves. Owns the one `AppBootState` (`useState(() => new AppBootState())`,
// never `useMemo`) and reads its observable fields, so it is an `observer`. Creates no
// router — the caller supplies one (`BrowserRouter` in `main.tsx`, `MemoryRouter` in tests).
//
// It never calls `documentNavigation` itself: on a 401 the shared client has already
// navigated to `/login`, and the gate adds no second navigation (DoD-6).
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react-lite";

import type { LayoutStorage } from "./workspaceLayout";
import {
  APP_BOOT_RETRY_INTERVAL_MS,
  AppBootState,
  probeCurrentUser,
  restartBoot,
} from "./appBootState";
import { AppBootFailed, AppNotReady } from "./AppBootScreens";
import { App } from "./App";

export type AppBootProps = {
  /** The persisted-layout storage, or `null`; handed to `App` once the probe succeeds. */
  storage: LayoutStorage | null;
};

/**
 * Probes `/api/me` once on mount with an `AbortController` aborted on unmount, then renders
 * by status: `"probing"` and `"unauthenticated"` render nothing; `"not-ready"` renders
 * `AppNotReady` and re-probes `APP_BOOT_RETRY_INTERVAL_MS` after each not-ready outcome
 * (never two probes in flight, cancelled on unmount and when the status leaves
 * `"not-ready"`); `"failed"` renders `AppBootFailed` with no automatic re-probe; `"ready"`
 * renders `App` with the user and the storage.
 *
 * The re-probe is armed from the **completion** of each probe rather than from an effect
 * keyed on `status`: a not-ready → not-ready probe leaves `status` untouched, so such an
 * effect would never re-arm (005.context.md, "The re-probe timer").
 */
export const AppBoot = observer(function AppBoot(
  props: AppBootProps,
): React.JSX.Element | null {
  const { storage } = props;
  const [state] = useState(() => new AppBootState());
  // The mount effect publishes its probe here, so both retries run the very same loop.
  const retryRef = useRef<() => void>(() => {});

  useEffect(() => {
    // One controller for every probe of this mount: a late response that lands after
    // unmount finds an aborted signal and writes nothing.
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;
    let mounted = true;

    const clearRetryTimer = (): void => {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    };

    const probe = async (): Promise<void> => {
      // Never two probes in flight: a manual retry during a request is a no-op, and the
      // pending timer is dropped because this probe's own completion re-arms it.
      if (!mounted || inFlight) {
        return;
      }
      clearRetryTimer();
      inFlight = true;
      await probeCurrentUser(state, controller.signal);
      inFlight = false;
      if (!mounted) {
        return;
      }
      if (state.status === "not-ready") {
        timer = setTimeout(() => {
          timer = null;
          void probe();
        }, APP_BOOT_RETRY_INTERVAL_MS);
      }
    };

    retryRef.current = (): void => {
      void probe();
    };
    void probe();

    return () => {
      mounted = false;
      clearRetryTimer();
      controller.abort();
      retryRef.current = () => {};
    };
  }, [state]);

  if (state.status === "ready" && state.user !== null) {
    return <App user={state.user} storage={storage} />;
  }
  if (state.status === "not-ready") {
    return (
      <AppNotReady
        onRetry={() => {
          retryRef.current();
        }}
      />
    );
  }
  if (state.status === "failed") {
    return (
      <AppBootFailed
        onRetry={() => {
          // The panel disappears while the request is in flight; its outcome replaces it.
          restartBoot(state);
          retryRef.current();
        }}
      />
    );
  }
  // `"probing"` and `"unauthenticated"`: nothing of its own. On a 401 the shared client is
  // already navigating to `/login`.
  return null;
});
