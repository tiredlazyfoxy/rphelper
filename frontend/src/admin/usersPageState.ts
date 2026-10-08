// The Users page's data: observable fields only, no methods, no computed getters.
// Loads and mutations are the free functions below.
import { makeAutoObservable, runInAction } from "mobx";
import { apiGet, apiPost } from "../shared/api";

/** The backend ladder's stored values — never the Python enum member names. */
export type AdminUserRole = "roleplayer" | "admin";

/** One account, exactly as `GET /api/admin/users` sends it. `id` is a decimal string, never parsed. */
export type AdminUserRow = {
  id: string;
  username: string;
  role: AdminUserRole;
  is_enabled: boolean;
  last_login_at: string | null;      // UTC ISO-8601, or null when never signed in
};

/** The list route's body: `{ users: [...] }`. */
export type AdminUserListResponse = {
  users: AdminUserRow[];
};

/** Explicit load status: gates the Loader, not "rows are empty". */
export type UsersLoadStatus = "idle" | "loading" | "ready";

export class UsersPageState {
  rows: AdminUserRow[] = [];
  status: UsersLoadStatus = "idle";
  errorMessage: string | null = null;

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

function isAbortRejection(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function failureMessageOf(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return fallback;
}

/**
 * `GET /api/admin/users`; writes `rows` and `status` in `runInAction`. Returns without
 * writing when `signal` is aborted. A failure keeps the rendered rows and sets
 * `errorMessage`. Does not reject.
 */
export async function loadUsers(state: UsersPageState, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  if (state.status !== "ready") {
    runInAction(() => {
      state.status = "loading";
    });
  }

  let body: AdminUserListResponse | undefined;
  try {
    body = await apiGet<AdminUserListResponse | undefined>("/api/admin/users", signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const message = failureMessageOf(error, "The account list could not be loaded.");
    runInAction(() => {
      state.status = "ready";
      state.errorMessage = message;
    });
    return;
  }

  if (signal?.aborted) {
    return;
  }
  const rows = body?.users ?? [];
  runInAction(() => {
    state.rows = rows;
    state.status = "ready";
    state.errorMessage = null;
  });
}

async function mutateThenReload(
  state: UsersPageState,
  path: string,
  fallback: string,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    return;
  }
  try {
    await apiPost<unknown>(path, undefined, signal);
  } catch (error) {
    if (signal?.aborted || isAbortRejection(error)) {
      return;
    }
    const message = failureMessageOf(error, fallback);
    runInAction(() => {
      state.errorMessage = message;
    });
    return;
  }
  await loadUsers(state, signal);
}

/**
 * `POST /api/admin/users/{id}/disable`, then re-loads the list (never optimistic).
 * A failure sets `errorMessage` and leaves the rows as they were. Does not reject.
 */
export async function disableUser(
  state: UsersPageState,
  id: string,
  signal?: AbortSignal,
): Promise<void> {
  await mutateThenReload(
    state,
    `/api/admin/users/${encodeURIComponent(id)}/disable`,
    "The account could not be disabled.",
    signal,
  );
}

/**
 * `POST /api/admin/users/{id}/enable`, then re-loads the list (never optimistic).
 * A failure sets `errorMessage` and leaves the rows as they were. Does not reject.
 */
export async function enableUser(
  state: UsersPageState,
  id: string,
  signal?: AbortSignal,
): Promise<void> {
  await mutateThenReload(
    state,
    `/api/admin/users/${encodeURIComponent(id)}/enable`,
    "The account could not be re-enabled.",
    signal,
  );
}
