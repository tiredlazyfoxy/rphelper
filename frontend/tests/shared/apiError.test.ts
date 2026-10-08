// Feature 002, step 004 — the typed API error (DoD-1..DoD-3).
import { describe, expect, it } from "vitest";
import { ApiError, isApiError } from "../../src/shared/apiError";

describe("ApiError", () => {
  it("is an Error, recognised by instanceof, exposing code/message/detail/status__DoD1", () => {
    const detail: Record<string, unknown> = { field: "name", conflicting_id: "77" };
    const err = new ApiError("zone_not_empty", "The zone is not empty.", 409, detail);

    expect(err).toBeInstanceOf(Error);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("zone_not_empty");
    expect(err.message).toBe("The zone is not empty.");
    expect(err.status).toBe(409);
    expect(err.detail).toEqual({ field: "name", conflicting_id: "77" });
    expect(err.name).toBe("ApiError");
  });

  it("stays recognisable by instanceof after being thrown and caught__DoD1", () => {
    let caught: unknown;
    try {
      throw new ApiError("already_configured", "Already configured.", 409, {});
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect(caught).toBeInstanceOf(Error);
    expect((caught as ApiError).code).toBe("already_configured");
    expect((caught as ApiError).status).toBe(409);
  });

  it("exposes an empty object as detail when constructed without one__DoD2", () => {
    const err = new ApiError("translation_failed", "Translation failed.", 502);
    expect(err.detail).not.toBeUndefined();
    expect(err.detail).not.toBeNull();
    expect(typeof err.detail).toBe("object");
    expect(err.detail).toEqual({});
  });

  it("exposes an empty object as detail when detail is passed as undefined__DoD2", () => {
    const err = new ApiError("zone_empty", "The zone is empty.", 409, undefined);
    expect(err.detail).not.toBeUndefined();
    expect(err.detail).not.toBeNull();
    expect(err.detail).toEqual({});
  });
});

describe("isApiError", () => {
  it("answers true for an ApiError__DoD3", () => {
    expect(isApiError(new ApiError("model_not_enabled", "Model not enabled.", 400, {}))).toBe(true);
    expect(isApiError(new ApiError("account_disabled", "Disabled.", 403))).toBe(true);
  });

  it("answers false for an ordinary Error__DoD3", () => {
    expect(isApiError(new Error("boom"))).toBe(false);
    expect(isApiError(new TypeError("Failed to fetch"))).toBe(false);
  });

  it("answers false for a plain object of the same shape__DoD3", () => {
    const lookalike = {
      name: "ApiError",
      code: "zone_not_empty",
      message: "The zone is not empty.",
      detail: {},
      status: 409,
    };
    expect(isApiError(lookalike)).toBe(false);
  });

  it("answers false for non-objects__DoD3", () => {
    expect(isApiError("zone_not_empty")).toBe(false);
    expect(isApiError(409)).toBe(false);
    expect(isApiError(true)).toBe(false);
    expect(isApiError(null)).toBe(false);
    expect(isApiError(undefined)).toBe(false);
  });
});
