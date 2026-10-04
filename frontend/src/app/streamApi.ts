// The stream wire surface (feature 013, step 001): the `Message` row as the stream routes
// send it, the settle / re-open results, and the seven calls over the shared client (D14).
// Ids are decimal strings and are never parsed, coerced or compared numerically. Text is sent
// verbatim. Failures are the shared client's `ApiError`s, rethrown unchanged.
import { apiGet, apiPatch, apiPost } from "../shared/api";
import { postSse } from "../shared/sse";
import type { SseOutcome, SseProgressFrame } from "../shared/sse";

/** A message's role, as the wire carries it. */
export type MessageRole = "user" | "assistant" | "tool";

/** A stream entry's kind, as the wire carries it (zone rows carry `null`). */
export type MessageKind = "partner" | "turn" | "decision";

/** A tool row's outcome, as the wire carries it (022 D3). */
export type ToolStatus = "ok" | "failed";

/**
 * One message, exactly as the stream routes send it. No renaming layer. The three tool fields
 * are optional (022 D15): absent means the same as null; all three are null on a non-tool row.
 */
export type Message = {
  id: string;
  session_id: string;
  role: MessageRole;
  kind: MessageKind | null;
  text: string;
  settled_at: string | null;
  created_at: string;
  updated_at: string;
  tool_name?: string | null;
  tool_status?: ToolStatus | null;
  tool_args?: Record<string, unknown> | null;
};

/** `POST /api/sessions/<id>/settle`'s body: ids only (012 D11). */
export type SettleResult = {
  entry_id: string;
  kind: MessageKind;
  buried_ids: string[];
};

/** `POST /api/sessions/<id>/reopen`'s body: ids only (012 D11). */
export type ReopenResult = {
  reopened_id: string;
  restored_ids: string[];
};

/** `GET …/entries`'s body: `{ entries: [...] }`. */
type EntriesResponse = {
  entries: Message[];
};

/** `GET …/zone`'s body: `{ messages: [...] }`. */
type ZoneResponse = {
  messages: Message[];
};

/** `GET /api/messages/<id>/discussion`'s body: `{ messages: [...] }` (022 D1). */
type DiscussionResponse = {
  messages: Message[];
};

/** `/api/sessions/<sessionId>` plus a suffix; the id is only ever escaped, never parsed. */
function sessionPath(sessionId: string, suffix: string): string {
  return `/api/sessions/${encodeURIComponent(sessionId)}${suffix}`;
}

/** `GET /api/sessions/<sessionId>/entries` — the payload's `entries`, in the order received. */
export async function fetchEntries(sessionId: string, signal?: AbortSignal): Promise<Message[]> {
  const body = await apiGet<EntriesResponse | undefined>(sessionPath(sessionId, "/entries"), signal);
  return body?.entries ?? [];
}

/** `GET /api/sessions/<sessionId>/zone` — the payload's `messages`, in the order received. */
export async function fetchZone(sessionId: string, signal?: AbortSignal): Promise<Message[]> {
  const body = await apiGet<ZoneResponse | undefined>(sessionPath(sessionId, "/zone"), signal);
  return body?.messages ?? [];
}

/** `POST /api/sessions/<sessionId>/entries` with `{ kind: "partner", text }`. */
export async function filePartnerEntry(
  sessionId: string,
  text: string,
  signal?: AbortSignal,
): Promise<Message> {
  return apiPost<Message>(sessionPath(sessionId, "/entries"), { kind: "partner", text }, signal);
}

/** `POST /api/sessions/<sessionId>/zone/messages` with `{ text }`. */
export async function appendZoneMessage(
  sessionId: string,
  text: string,
  signal?: AbortSignal,
): Promise<Message> {
  return apiPost<Message>(sessionPath(sessionId, "/zone/messages"), { text }, signal);
}

/** `POST /api/sessions/<sessionId>/settle`, no body. */
export async function settleZone(sessionId: string, signal?: AbortSignal): Promise<SettleResult> {
  return apiPost<SettleResult>(sessionPath(sessionId, "/settle"), undefined, signal);
}

/** `POST /api/sessions/<sessionId>/reopen`, no body. */
export async function reopenLastEntry(
  sessionId: string,
  signal?: AbortSignal,
): Promise<ReopenResult> {
  return apiPost<ReopenResult>(sessionPath(sessionId, "/reopen"), undefined, signal);
}

/**
 * 019 004: `POST /api/sessions/<sessionId>/zone/compose` with `{ text }` — or exactly `{}`
 * when no text is given (021 D2, D12) — over `003`'s SSE consumer; resolves to the consumer's
 * outcome unchanged. The signal is required (D12).
 */
export async function composeZone(
  sessionId: string,
  text: string | undefined,
  onFrame: (frame: SseProgressFrame) => void,
  signal: AbortSignal,
): Promise<SseOutcome> {
  const body = text === undefined ? {} : { text };
  return postSse(sessionPath(sessionId, "/zone/compose"), body, onFrame, signal);
}

/**
 * 022 D1: `GET /api/messages/<entryId>/discussion` — the payload's `messages`, unwrapped, in
 * the served order (never re-sorted). The shared client's `ApiError` is rethrown unchanged.
 */
export async function fetchDiscussion(entryId: string, signal?: AbortSignal): Promise<Message[]> {
  const body = await apiGet<DiscussionResponse | undefined>(
    `/api/messages/${encodeURIComponent(entryId)}/discussion`,
    signal,
  );
  return body?.messages ?? [];
}

/** `PATCH /api/messages/<messageId>` with `{ text }`. */
export async function editMessage(
  messageId: string,
  text: string,
  signal?: AbortSignal,
): Promise<Message> {
  return apiPatch<Message>(`/api/messages/${encodeURIComponent(messageId)}`, { text }, signal);
}
