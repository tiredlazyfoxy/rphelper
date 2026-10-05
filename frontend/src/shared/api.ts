import { ApiError, CLIENT_MALFORMED_ERROR, CLIENT_TRANSPORT_FAILED } from "./apiError";

export type HttpMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

/**
 * The document-navigation seam. The 401 path navigates by calling
 * `documentNavigation.assign("/login")` through this object at call time, so a test
 * can replace it with `vi.spyOn(documentNavigation, "assign").mockImplementation(() => {})`
 * and jsdom never attempts a real navigation.
 */
export const documentNavigation: { assign(url: string): void } = {
  assign(url: string): void {
    window.location.assign(url);
  },
};

const API_PREFIX = "/api/";
const LOGIN_PATH = "/login";

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Decode the backend's `{ error: { code, message, detail } }` envelope, or `null` if the body is not one. */
function decodeEnvelope(text: string, status: number): ApiError | null {
  if (text.length === 0) {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return null;
  }
  if (!isPlainObject(parsed) || !isPlainObject(parsed.error)) {
    return null;
  }
  const { code, message, detail } = parsed.error;
  if (typeof code !== "string" || typeof message !== "string") {
    return null;
  }
  if (detail !== undefined && detail !== null && !isPlainObject(detail)) {
    return null;
  }
  return new ApiError(code, message, status, detail ?? undefined);
}

function malformed(status: number): ApiError {
  return new ApiError(
    CLIENT_MALFORMED_ERROR,
    `The server returned an unreadable error response (HTTP ${status}).`,
    status,
  );
}

/**
 * The non-2xx decode (019 D10), shared by `apiRequest` and `shared/sse.ts`. From a non-2xx
 * `Response`: navigates to `/login` first when the status is 401, then resolves to the
 * envelope's `ApiError` (real status) or the `client_malformed_error` fallback. Never rejects.
 */
export async function decodeErrorResponse(response: Response): Promise<ApiError> {
  if (response.status === 401) {
    documentNavigation.assign(LOGIN_PATH);
  }
  let text: string;
  try {
    text = await response.text();
  } catch {
    text = "";
  }
  return decodeEnvelope(text, response.status) ?? malformed(response.status);
}

/**
 * The rejection mapping (019 D10). Returns `error` unchanged when `signal` is aborted;
 * otherwise `ApiError(client_transport_failed, "The server could not be reached.", 0)`.
 */
export function mapFetchRejection(error: unknown, signal?: AbortSignal): unknown {
  if (signal?.aborted) {
    return error;
  }
  return new ApiError(CLIENT_TRANSPORT_FAILED, "The server could not be reached.", 0);
}

/**
 * The single entry point. Resolves to the parsed JSON body typed as `T` (caller-asserted,
 * not validated); resolves to `undefined` for a 204 or an empty 2xx body. A body is sent
 * iff `body !== undefined`.
 */
export async function apiRequest<T = unknown>(
  path: string,
  method: HttpMethod,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  if (!path.startsWith(API_PREFIX)) {
    throw new Error(`API path must begin with "${API_PREFIX}": ${path}`);
  }

  const init: RequestInit = { method, credentials: "same-origin" };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  if (signal !== undefined) {
    init.signal = signal;
  }

  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    throw mapFetchRejection(error, signal);
  }

  let text: string;
  try {
    text = response.status === 204 ? "" : await response.text();
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }
    if (response.ok) {
      throw new ApiError(CLIENT_TRANSPORT_FAILED, "The server response could not be read.", 0);
    }
    text = "";
  }

  if (response.ok) {
    if (text.length === 0) {
      return undefined as T;
    }
    try {
      return JSON.parse(text) as T;
    } catch {
      throw new ApiError(
        CLIENT_MALFORMED_ERROR,
        `The server returned an unreadable response (HTTP ${response.status}).`,
        response.status,
      );
    }
  }

  // The body is already read here (an aborted read above rethrows raw, before any 401
  // navigation), so the shared decode gets an equivalent, already-buffered response.
  throw await decodeErrorResponse(
    new Response(text.length === 0 ? null : text, { status: response.status }),
  );
}

export async function apiGet<T = unknown>(path: string, signal?: AbortSignal): Promise<T> {
  return apiRequest<T>(path, "GET", undefined, signal);
}

export async function apiPost<T = unknown>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  return apiRequest<T>(path, "POST", body, signal);
}

export async function apiPatch<T = unknown>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  return apiRequest<T>(path, "PATCH", body, signal);
}

/** `PUT` with `apiPatch`'s exact shape and error mapping (016 D12). */
export async function apiPut<T = unknown>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  return apiRequest<T>(path, "PUT", body, signal);
}

export async function apiDelete<T = unknown>(path: string, signal?: AbortSignal): Promise<T> {
  return apiRequest<T>(path, "DELETE", undefined, signal);
}

/**
 * What one completed browser download reports back: the saved file's name and its byte count.
 * Never its content — the body is opaque to every caller (US-078).
 */
export type DownloadResult = {
  filename: string;
  size: number;
};

const FALLBACK_DOWNLOAD_FILENAME = "rphelper-export.json";

/**
 * The `filename="…"` parameter. The leading boundary keeps a `filename="…"` buried inside
 * another parameter's name (an `xfilename=`) from matching, and the group may be empty, which
 * the reader treats as absent.
 */
const CONTENT_DISPOSITION_FILENAME = /(?:^|[;\s])filename\s*=\s*"([^"]*)"/i;

/**
 * Pure. Reads the quoted filename out of a `Content-Disposition` header value, e.g.
 * `attachment; filename="rphelper-user-20261005T101112Z.json"`. Returns the fallback
 * `rphelper-export.json` when `header` is `null`, carries no `filename="…"`, or is otherwise
 * unparseable. Never throws.
 */
export function filenameFromContentDisposition(header: string | null): string {
  if (header === null) {
    return FALLBACK_DOWNLOAD_FILENAME;
  }
  const filename = CONTENT_DISPOSITION_FILENAME.exec(header)?.[1] ?? "";
  return filename.trim().length > 0 ? filename : FALLBACK_DOWNLOAD_FILENAME;
}

/**
 * Saves `blob` under `filename` through a temporary object URL and a clicked anchor, then
 * removes the anchor and revokes the URL on every exit. The anchor is in the document for the
 * click (so the click reaches the document) and never outlives it.
 */
function saveBlobAsFile(blob: Blob, filename: string): void {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    URL.revokeObjectURL(objectUrl);
  }
}

/**
 * The blob download, beside the JSON calls so it shares their one decode. `GET path` (an
 * `/api/...` path) with `credentials: "same-origin"`; on a 2xx the body is read as a `Blob` and
 * saved through a temporary object URL and a clicked `download=<filename>` anchor, which are then
 * removed and revoked, and the call resolves with that filename (from `Content-Disposition`, or
 * the fallback) and the blob's byte size. On a non-2xx it throws the same `ApiError` the JSON
 * calls throw, through `decodeErrorResponse` — so a well-formed envelope gives the backend code,
 * a malformed body gives `client_malformed_error`, and a 401 navigates to `/login` first. A
 * rejected `fetch` throws `client_transport_failed` through `mapFetchRejection`, and an abort
 * propagates unchanged and unwrapped. The body is never parsed as JSON and never reaches the
 * caller.
 */
export async function apiDownload(path: string, signal?: AbortSignal): Promise<DownloadResult> {
  const init: RequestInit = { method: "GET", credentials: "same-origin" };
  if (signal !== undefined) {
    init.signal = signal;
  }

  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    throw mapFetchRejection(error, signal);
  }

  if (!response.ok) {
    // The JSON calls' one decode: the envelope's own ApiError or the malformed fallback, with
    // the 401 navigation first. No object URL has been created on this path, and none is.
    throw await decodeErrorResponse(response);
  }

  const filename = filenameFromContentDisposition(response.headers.get("Content-Disposition"));

  let blob: Blob;
  try {
    // The body is read as bytes and never parsed; only its size leaves this function.
    blob = await response.blob();
  } catch (error) {
    throw mapFetchRejection(error, signal);
  }

  if (signal?.aborted) {
    // A caller that abandoned the download saves no file: the abort propagates unwrapped and
    // no object URL is created.
    throw signal.reason ?? new DOMException("The download was aborted.", "AbortError");
  }

  saveBlobAsFile(blob, filename);
  return { filename, size: blob.size };
}
