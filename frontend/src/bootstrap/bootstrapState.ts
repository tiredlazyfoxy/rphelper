// The bootstrap entry's store: a data class (observable fields only) plus free functions
// over it (002 D2, 003 context.md D13).
import { makeAutoObservable, runInAction } from "mobx";
import { apiGet } from "../shared/api";
import { isNotReady } from "../shared/notReady";

/** The five states the bootstrap entry renders. */
export type BootstrapPhase = "probing" | "offer" | "refusal" | "not-ready" | "failed";

/** The narrow slice of the `GET /api/health` body this entry reads — `configured` alone. */
export type HealthConfiguredResponse = {
  configured: boolean;
};

/** Fixed re-probe interval while the phase is not-ready (003 context.md D11). */
export const NOT_READY_RETRY_INTERVAL_MS = 2000;

export class BootstrapState {
  phase: BootstrapPhase = "probing";
  failureMessage: string | null = null;

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** Pure derivation: which of the five phases the page renders. */
export function bootstrapPhase(state: BootstrapState): BootstrapPhase {
  return state.phase;
}

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function failureMessageOf(error: unknown): string {
  if (error instanceof Error && error.message.length > 0) {
    return error.message;
  }
  return "The instance could not be checked.";
}

/**
 * One `GET /api/health` probe; `runInAction`s the resulting phase unless `signal` aborted.
 * Never rejects: every outcome is written onto the store, and an abort writes nothing.
 */
export async function probeHealth(state: BootstrapState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }

  let body: HealthConfiguredResponse | undefined;
  try {
    body = await apiGet<HealthConfiguredResponse | undefined>("/api/health", signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const notReady = isNotReady(error);
    runInAction(() => {
      if (notReady) {
        state.phase = "not-ready";
        state.failureMessage = null;
      } else {
        state.phase = "failed";
        state.failureMessage = failureMessageOf(error);
      }
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  const configured = body?.configured === true;
  runInAction(() => {
    state.phase = configured ? "refusal" : "offer";
    state.failureMessage = null;
  });
}

/** Handle for a running probe loop: the in-flight request's controller and the pending timer. */
export type ProbeLoop = {
  readonly controller: AbortController;
  timer: ReturnType<typeof setTimeout> | null;
};

/**
 * Probes immediately, then — while the phase is not-ready — re-probes every
 * NOT_READY_RETRY_INTERVAL_MS, uncapped. Also what the manual retry control calls.
 */
export function startProbeLoop(state: BootstrapState): ProbeLoop {
  const loop: ProbeLoop = { controller: new AbortController(), timer: null };
  const signal = loop.controller.signal;

  const run = (): void => {
    loop.timer = null;
    if (signal.aborted) {
      return;
    }
    void probeHealth(state, signal).then(() => {
      if (signal.aborted || state.phase !== "not-ready") {
        return;
      }
      loop.timer = setTimeout(run, NOT_READY_RETRY_INTERVAL_MS);
    });
  };

  run();
  return loop;
}

/** Cancels the loop's pending timer and aborts its in-flight request. */
export function stopProbeLoop(loop: ProbeLoop): void {
  if (loop.timer !== null) {
    clearTimeout(loop.timer);
    loop.timer = null;
  }
  loop.controller.abort();
}
