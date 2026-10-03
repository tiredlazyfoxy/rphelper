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
