// The `app` entry's boot gate state (008 context.md D2, D13): a pure classification of a
// failed `GET /api/me`, a MobX data class with observable fields only, and the two effects
// that write it. The class has no methods and no computed getters; every derivation and
// every effect is a free function in this module taking the state.
//
// The module is `appBootState.ts`, not `appBoot.ts`: a `.ts` sibling differing from
// `AppBoot.tsx` only in letter case is resolved differently by TypeScript and by
// Vite/Vitest on this case-insensitive filesystem, which left the component binding
// `undefined` at runtime while typecheck stayed green (005.context.md, "Why the state
// module is `appBootState.ts`"). The name also follows step 002's `app/shellState.ts`
// precedent — a MobX data class plus free functions in one module.
//
// This module mirrors the admin entry's boot loop behaviourally and imports nothing from
// `src/admin/` — the two bundles stay separate (008 context.md, "Cross-cutting
// constraints").
import { makeAutoObservable, runInAction } from "mobx";

import { isApiError } from "../shared/apiError";
import { fetchCurrentUser, type CurrentUser } from "../shared/currentUser";
import { isNotReady } from "../shared/notReady";

/**
 * The delay between two consecutive not-ready probes: `2000` ms, uncapped, no backoff.
 * The same interval the admin entry uses, declared independently.
 */
export const APP_BOOT_RETRY_INTERVAL_MS = 2000;

/** What a thrown `GET /api/me` failure means to the gate. */
export type AppBootOutcome = "unauthenticated" | "not-ready" | "failed";

/**
 * The backend code behind a missing or dead session (D13): `NotAuthenticatedError`, raised
 * by `require_user`, which `GET /api/me` depends on. The branch is on the code, never on
 * the status — the shared client's rule.
 */
const NOT_AUTHENTICATED_CODE = "not_authenticated";

/**
 * Pure. Classifies a value thrown by `fetchCurrentUser`: `"unauthenticated"` for an
 * `ApiError` whose code is `not_authenticated` (D13), `"not-ready"` when `isNotReady`
 * holds, `"failed"` for anything else — a well-formed 403 or 5xx envelope, or a value that
 * is not an `ApiError` at all. Touches no network and no DOM.
 */
export function classifyAppBootError(error: unknown): AppBootOutcome {
  if (isApiError(error) && error.code === NOT_AUTHENTICATED_CODE) {
    return "unauthenticated";
  }
  if (isNotReady(error)) {
    return "not-ready";
  }
  return "failed";
}

/**
 * The boot gate's state. `status` starts `"probing"` — nothing of the shell renders until
 * it leaves that value — and `user` is non-`null` exactly when `status` is `"ready"`.
 */
export class AppBootState {
  status: "probing" | "unauthenticated" | "not-ready" | "failed" | "ready" = "probing";
  user: CurrentUser | null = null;

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/**
 * Read through a call so the compiler does not narrow `aborted` for the rest of the body:
 * the flag can flip while the request is in flight.
 */
function isAborted(signal: AbortSignal | undefined): boolean {
  return signal?.aborted === true;
}

/**
 * Effect. One `fetchCurrentUser(signal)`: on success writes `status` `"ready"` and the
 * user; on failure writes `classifyAppBootError`'s outcome. Writes nothing once the signal
 * is aborted, and never rethrows. Does **not** set `"probing"` itself, so a re-probe from
 * the not-ready screen leaves that screen up.
 */
export async function probeCurrentUser(
  state: AppBootState,
  signal?: AbortSignal,
): Promise<void> {
  let user: CurrentUser;
  try {
    user = await fetchCurrentUser(signal);
  } catch (error) {
    // An aborted probe belongs to a gate that is gone; its outcome is not news.
    if (isAborted(signal)) {
      return;
    }
    const outcome = classifyAppBootError(error);
    runInAction(() => {
      state.status = outcome;
    });
    return;
  }

  if (isAborted(signal)) {
    return;
  }
  runInAction(() => {
    state.status = "ready";
    state.user = user;
  });
}

/**
 * Effect. Sets `status` back to `"probing"` — the failure panel's retry, so the panel
 * disappears while the next request is in flight.
 */
export function restartBoot(state: AppBootState): void {
  runInAction(() => {
    state.status = "probing";
  });
}
