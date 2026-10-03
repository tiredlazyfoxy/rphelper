// The session's memo chain (feature 015, step 008, D16): the `MemoChainState` data class —
// observable fields only, no methods and no computed getters — and the `loadMemoChain`
// effect that fills it from one chain request, one `MemoLevelState` per returned level.
// Owned by the session screen's Notes section; never shared with the character page.
// Ids are decimal strings, used only as keys and compared only for equality.
import { makeAutoObservable, runInAction } from "mobx";

import { fetchMemoChain } from "./memosApi";
import type { MemoChainLevel } from "./memosApi";
import { MemoLevelState, populateMemoLevel } from "./memoLevelState";

/** Explicit load status: gates the loading and failure renders. */
export type MemoChainStatus = "idle" | "loading" | "ready" | "failed";

export class MemoChainState {
  /** The session whose chain this is. A string, never parsed. */
  sessionId: string;
  status: MemoChainStatus = "idle";
  /** One state per chain level, in the order the server returned them. */
  levels: MemoLevelState[] = [];

  constructor(sessionId: string) {
    this.sessionId = sessionId;
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/** Whether a rejection is the fetch layer's own abort, not a load failure. */
function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** Effect: loads the chain into `state`. Never rejects; writes nothing once aborted. */
export async function loadMemoChain(state: MemoChainState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  const sessionId = state.sessionId;
  runInAction(() => {
    state.status = "loading";
  });

  let levels: MemoChainLevel[];
  try {
    levels = await fetchMemoChain(sessionId, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    // Failure keeps whatever levels the state already holds.
    runInAction(() => {
      state.status = "failed";
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  runInAction(() => {
    // The server decides which levels exist (R2); the order received is kept verbatim.
    state.levels = levels.map((level) => {
      const levelState = new MemoLevelState(level.scope, level.scope_id);
      populateMemoLevel(levelState, level.memos);
      return levelState;
    });
    state.status = "ready";
  });
}
