// Feature 003, step 004 — the not-ready-yet predicate (DoD-7).
// The condition (context.md D10): an ApiError whose code is the transport-failure synthetic
// code, or the malformed-body synthetic code with a status of 500 or above. Nothing else.
import { describe, expect, it } from "vitest";
import {
  ApiError,
  CLIENT_MALFORMED_ERROR,
  CLIENT_TRANSPORT_FAILED,
} from "../../src/shared/apiError";
import { isNotReady } from "../../src/shared/notReady";

describe("isNotReady answers true for the not-ready-yet condition", () => {
  it("the transport-failure code (status 0) — DoD-7", () => {
    expect(isNotReady(new ApiError(CLIENT_TRANSPORT_FAILED, "The server could not be reached.", 0))).toBe(true);
  });

  it.each([500, 502, 503, 504])("the malformed-body code at status %i — DoD-7", (status) => {
    expect(isNotReady(new ApiError(CLIENT_MALFORMED_ERROR, "Unexpected response.", status))).toBe(true);
  });
});

describe("isNotReady answers false for everything else", () => {
  it.each([400, 401, 403, 404, 409, 422, 429, 499])(
    "the malformed-body code at 4xx status %i — DoD-7",
    (status) => {
      expect(isNotReady(new ApiError(CLIENT_MALFORMED_ERROR, "Unexpected response.", status))).toBe(false);
    },
  );

  it("a well-formed backend envelope: already_configured (409) — DoD-7", () => {
    expect(
      isNotReady(new ApiError("already_configured", "This instance is already configured.", 409, {})),
    ).toBe(false);
  });

  it.each([
    ["internal_error", 500],
    ["llm_unreachable", 502],
    ["service_unavailable", 503],
    ["upstream_timeout", 504],
  ])("a well-formed backend envelope %s at %i is not matched — DoD-7", (code, status) => {
    expect(isNotReady(new ApiError(code, "The backend answered with its own error.", status))).toBe(false);
  });

  it("an abort (DOMException AbortError) — DoD-7", () => {
    expect(isNotReady(new DOMException("The operation was aborted.", "AbortError"))).toBe(false);
  });

  it("an abort raised from an aborted AbortSignal — DoD-7", () => {
    const controller = new AbortController();
    controller.abort();
    expect(isNotReady(controller.signal.reason)).toBe(false);
  });

  const NON_API_VALUES: Array<[string, unknown]> = [
    ["a plain Error", new Error("boom")],
    ["a TypeError like a raw fetch rejection", new TypeError("Failed to fetch")],
    ["a string", CLIENT_TRANSPORT_FAILED],
    ["undefined", undefined],
    ["null", null],
    ["a plain object shaped like a transport failure", { code: CLIENT_TRANSPORT_FAILED, status: 0, message: "x" }],
    ["a plain object shaped like a malformed 502", { code: CLIENT_MALFORMED_ERROR, status: 502, message: "x" }],
  ];

  it.each(NON_API_VALUES)("a non-ApiError value: %s — DoD-7", (_name, value) => {
    expect(isNotReady(value)).toBe(false);
  });
});
