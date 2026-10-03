// The browser's only SSE consumer (019 D9): a `fetch()` POST read through
// `body.getReader()`, split on the blank line, every id kept a string. Failure decoding is
// `api.ts`'s (D10).
import { decodeErrorResponse, mapFetchRejection } from "./api";
import { ApiError, CLIENT_MALFORMED_ERROR, CLIENT_TRANSPORT_FAILED, isApiError } from "./apiError";

/** One wire frame, discriminated on `event`. Every id field is a `string`, never a number. */
export type SseFrame =
  | { event: "accepted"; message_id: string }
  | { event: "token"; text: string }
  | { event: "tool_start"; tool: string; call_id: string; args: Record<string, unknown> }
  | { event: "tool_result"; tool: string; call_id: string; summary: string }
  | { event: "tool_fail"; tool: string; call_id: string; code: string }
  | { event: "error"; code: string; message: string | null; detail?: Record<string, unknown> }
  | { event: "done"; message_id: string };

/** The non-terminal frames — the only ones the frame callback ever receives. */
export type SseProgressFrame = Exclude<SseFrame, { event: "error" } | { event: "done" }>;

/** The consumer's single result (D9). */
export type SseOutcome =
  | { kind: "done"; messageId: string }
  | { kind: "error"; error: ApiError }
  | { kind: "stopped" }
  | { kind: "unexpected_end" };

/**
 * POST `body` as JSON to `path` (an `/api/...` path) with `credentials: "same-origin"` and
 * `signal`, read the SSE body, deliver each non-terminal frame to `onFrame` in arrival
 * order, and resolve to exactly one outcome. Never rejects.
 */
export async function postSse(
  path: string,
  body: unknown,
  onFrame: (frame: SseProgressFrame) => void,
  signal: AbortSignal,
): Promise<SseOutcome> {
  if (!path.startsWith(API_PREFIX)) {
    throw new Error(`API path must begin with "${API_PREFIX}": ${path}`);
  }

  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "same-origin",
      signal,
    });
  } catch (error) {
    return rejectionOutcome(error, signal);
  }

  if (!response.ok) {
    return { kind: "error", error: await decodeErrorResponse(response) };
  }

  if (response.body === null) {
    return endOutcome(signal);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const finish = (outcome: SseOutcome): SseOutcome => {
    reader.cancel().catch(() => undefined);
    return outcome;
  };

  for (;;) {
    let chunk: ReadableStreamReadResult<Uint8Array>;
    try {
      chunk = await reader.read();
    } catch (error) {
      return rejectionOutcome(error, signal);
    }
    if (chunk.done) {
      // Flush the decoder; a trailing fragment with no blank-line terminator is discarded.
      decoder.decode();
      return endOutcome(signal);
    }
    buffer += decoder.decode(chunk.value, { stream: true });

    let separator = buffer.indexOf(FRAME_SEPARATOR);
    while (separator !== -1) {
      const raw = buffer.slice(0, separator);
      buffer = buffer.slice(separator + FRAME_SEPARATOR.length);
      separator = buffer.indexOf(FRAME_SEPARATOR);

      const data = frameData(raw);
      if (data === null) {
        continue;
      }
      let parsed: unknown;
      try {
        parsed = JSON.parse(data);
      } catch {
        return finish(malformedFrame(response.status));
      }
      if (!isPlainObject(parsed) || typeof parsed.event !== "string") {
        return finish(malformedFrame(response.status));
      }

      switch (parsed.event) {
        case "done": {
          const messageId = parsed.message_id;
          if (typeof messageId !== "string") {
            return finish(malformedFrame(response.status));
          }
          return finish({ kind: "done", messageId });
        }
        case "error": {
          const { code, message, detail } = parsed;
          if (typeof code !== "string") {
            return finish(malformedFrame(response.status));
          }
          return finish({
            kind: "error",
            error: new ApiError(
              code,
              typeof message === "string" ? message : "",
              response.status,
              isPlainObject(detail) ? detail : {},
            ),
          });
        }
        case "accepted":
        case "token":
        case "tool_start":
        case "tool_result":
        case "tool_fail":
          onFrame(parsed as SseProgressFrame);
          break;
        default:
          // Unknown event: skipped for forward compatibility.
          break;
      }
    }
  }
}

const API_PREFIX = "/api/";
const FRAME_SEPARATOR = "\n\n";
const DATA_FIELD = "data:";

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The frame's `data:` lines joined with `"\n"` (one leading space stripped), or `null` if none. */
function frameData(raw: string): string | null {
  const parts: string[] = [];
  for (const line of raw.split("\n")) {
    if (!line.startsWith(DATA_FIELD)) {
      continue;
    }
    const value = line.slice(DATA_FIELD.length);
    parts.push(value.startsWith(" ") ? value.slice(1) : value);
  }
  return parts.length === 0 ? null : parts.join("\n");
}

function malformedFrame(status: number): SseOutcome {
  return {
    kind: "error",
    error: new ApiError(
      CLIENT_MALFORMED_ERROR,
      `The server sent an unreadable stream frame (HTTP ${status}).`,
      status,
    ),
  };
}

function endOutcome(signal: AbortSignal): SseOutcome {
  return signal.aborted ? { kind: "stopped" } : { kind: "unexpected_end" };
}

function rejectionOutcome(error: unknown, signal: AbortSignal): SseOutcome {
  if (signal.aborted) {
    return { kind: "stopped" };
  }
  const mapped = mapFetchRejection(error, signal);
  return {
    kind: "error",
    error: isApiError(mapped)
      ? mapped
      : new ApiError(CLIENT_TRANSPORT_FAILED, "The server could not be reached.", 0),
  };
}
