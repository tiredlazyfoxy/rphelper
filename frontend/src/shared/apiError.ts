/** Synthetic code: a non-2xx whose body is absent, not JSON, or not the error envelope. */
export const CLIENT_MALFORMED_ERROR = "client_malformed_error";

/** Synthetic code: `fetch` itself rejected (network down, DNS, connection refused). Status is `0`. */
export const CLIENT_TRANSPORT_FAILED = "client_transport_failed";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly detail: Record<string, unknown>;

  constructor(code: string, message: string, status: number, detail?: Record<string, unknown>) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.detail = detail ?? {};
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}
