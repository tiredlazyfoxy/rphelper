// The shared abort predicate: an `Error` named "AbortError" (what an aborted `fetch` rejects
// with) is an abort; anything else — another error, an `ApiError`, a non-Error value — is not.
import { describe, expect, it } from "vitest";
import { isAbortError } from "../../src/shared/abort";
import { ApiError } from "../../src/shared/apiError";

describe("isAbortError", () => {
  // No DOMException case: jsdom's DOMException is not an `Error` instance, so the answer would
  // depend on the environment (the browser's is one).
  it("is true for an Error named AbortError", () => {
    const error = new Error("aborted");
    error.name = "AbortError";
    expect(isAbortError(error)).toBe(true);
  });

  it("is false for an ordinary Error and for an ApiError", () => {
    expect(isAbortError(new Error("boom"))).toBe(false);
    expect(isAbortError(new ApiError("internal", "boom", 500))).toBe(false);
  });

  it("is false for non-Error values, even one shaped like an abort", () => {
    expect(isAbortError({ name: "AbortError" })).toBe(false);
    expect(isAbortError("AbortError")).toBe(false);
    expect(isAbortError(null)).toBe(false);
    expect(isAbortError(undefined)).toBe(false);
  });
});
