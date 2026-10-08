// The memos wire surface (feature 015, step 005): the `Memo` row and the chain level as the
// server sends them, and the five calls over the shared client. Two path families:
// `/api/memos` (listing by `?scope=…&scope_id=…`, create, and `/api/memos/<id>` for the
// update and the delete) and `/api/sessions/<session_id>/memo-chain` for the chain.
// Mutations take no abort signal (D5).
// Ids are decimal strings and are never parsed, coerced or compared numerically.
// Failures are the shared client's `ApiError`s, rethrown unchanged.
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "../shared/api";

/** The four levels a note can live at. */
export type MemoScope = "user" | "character" | "setup" | "session";

/** One note, exactly as the memos routes send it. No renaming layer. */
export type Memo = {
  id: string;
  scope: MemoScope;
  scope_id: string | null; // null exactly when scope is "user"
  body: string;
  is_enabled: boolean;
  is_forced: boolean;
  sort_key: number;
  created_at: string;
  updated_at: string;
};

/** One level of a session's memo chain. */
export type MemoChainLevel = {
  scope: MemoScope;
  scope_id: string | null;
  memos: Memo[];
};

/** The update body: exactly the supplied keys are sent. */
export type MemoPatch = {
  body?: string;
  is_enabled?: boolean;
  is_forced?: boolean;
};

/** The listing route's body: `{ memos: [...] }`. */
export type MemoListResponse = {
  memos: Memo[];
};

/** The chain route's body: `{ levels: [...] }`. */
export type MemoChainResponse = {
  levels: MemoChainLevel[];
};

const MEMOS_PATH = "/api/memos";

/** `/api/memos/<memoId>`; the id is only ever escaped, never parsed. */
function memoPath(memoId: string): string {
  return `${MEMOS_PATH}/${encodeURIComponent(memoId)}`;
}

/** `/api/sessions/<sessionId>/memo-chain`; the id is only ever escaped, never parsed. */
function memoChainPath(sessionId: string): string {
  return `/api/sessions/${encodeURIComponent(sessionId)}/memo-chain`;
}

/**
 * `GET /api/memos?scope=<scope>` plus `&scope_id=<scopeId>` only when non-null. Resolves to
 * the payload's `memos` array, in the order received.
 */
export async function fetchMemos(
  scope: MemoScope,
  scopeId: string | null,
  signal?: AbortSignal,
): Promise<Memo[]> {
  const query = new URLSearchParams();
  query.append("scope", scope);
  if (scopeId !== null) {
    query.append("scope_id", scopeId);
  }
  const body = await apiGet<MemoListResponse | undefined>(
    `${MEMOS_PATH}?${query.toString()}`,
    signal,
  );
  return body?.memos ?? [];
}

/** `POST /api/memos` with exactly `{ scope, scope_id, body }` — resolves to the created memo. */
export async function createMemo(
  scope: MemoScope,
  scopeId: string | null,
  body: string,
): Promise<Memo> {
  return apiPost<Memo>(MEMOS_PATH, { scope, scope_id: scopeId, body });
}

/** `PATCH /api/memos/<memoId>` — sends exactly the keys present, resolves to the memo. */
export async function updateMemo(memoId: string, patch: MemoPatch): Promise<Memo> {
  return apiPatch<Memo>(memoPath(memoId), patch);
}

/** `DELETE /api/memos/<memoId>` — resolves to `undefined` on 204. */
export async function deleteMemo(memoId: string): Promise<void> {
  await apiDelete<undefined>(memoPath(memoId));
}

/**
 * `PUT /api/memos/order` with exactly `{ scope, scope_id, memo_ids }` (016). Resolves to the
 * payload's `memos` array, in the order received. Takes no signal (015 D5).
 */
export async function reorderMemos(
  scope: MemoScope,
  scopeId: string | null,
  memoIds: string[],
): Promise<Memo[]> {
  const body = await apiPut<MemoListResponse | undefined>(`${MEMOS_PATH}/order`, {
    scope,
    scope_id: scopeId,
    memo_ids: memoIds,
  });
  return body?.memos ?? [];
}

/**
 * `GET /api/sessions/<sessionId>/memo-chain` — resolves to the payload's `levels` array,
 * in the order received.
 */
export async function fetchMemoChain(
  sessionId: string,
  signal?: AbortSignal,
): Promise<MemoChainLevel[]> {
  const body = await apiGet<MemoChainResponse | undefined>(memoChainPath(sessionId), signal);
  return body?.levels ?? [];
}
