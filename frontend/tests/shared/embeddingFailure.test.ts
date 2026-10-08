// Feature 024, step 008 — the code → sentence helper (DoD-1).
//
// Expected values come from the spec alone: `008.context.md` pins the two sentences
// verbatim, and `008.authoring-failure-sentences.md`'s Interface intent + DoD-1 pin the
// mapping ("nothing (null) for anything else"). The two exported constants are compared
// against the spec's texts, written out below as literals taken from `008.context.md`.
// `context.md`'s Wire contract / D8 supply the two codes (`no_embedding_model` 409,
// `llm_unreachable` 502) and the dimension-mismatch `detail`.
//
// The helper is pure, so this file constructs `ApiError` values directly and stubs no
// `fetch` (`008.context.md`, "Test shape"). `ApiError`'s constructor is
// `new ApiError(code, message, status, detail?)`, per the `## Skeleton` record.
import { describe, expect, it } from "vitest";
import { ApiError } from "../../src/shared/apiError";
import {
  embeddingFailureSentence,
  LLM_UNREACHABLE_SENTENCE,
  NO_EMBEDDING_MODEL_SENTENCE,
} from "../../src/shared/embeddingFailure";

// ---------------------------------------------------------------- the spec's two sentences
// Copied from `008.context.md` "The two sentences (exact)". Nothing else may define them.
const NO_EMBEDDING_MODEL_TEXT =
  "Not saved: no embedding model is configured, so this text can't be indexed for search. Ask your administrator to set one.";
const LLM_UNREACHABLE_TEXT = "Not saved: the embedding server could not be reached. Try again in a moment.";

// ---------------------------------------------------------------------------
describe("the two exported sentence constants", () => {
  it("NO_EMBEDDING_MODEL_SENTENCE is 008.context.md's no_embedding_model text, exactly — DoD-1", () => {
    expect(NO_EMBEDDING_MODEL_SENTENCE).toBe(NO_EMBEDDING_MODEL_TEXT);
  });

  it("LLM_UNREACHABLE_SENTENCE is 008.context.md's llm_unreachable text, exactly — DoD-1", () => {
    expect(LLM_UNREACHABLE_SENTENCE).toBe(LLM_UNREACHABLE_TEXT);
  });

  it("the two sentences differ, so neither test below can pass by coincidence — DoD-1", () => {
    expect(NO_EMBEDDING_MODEL_TEXT).not.toBe(LLM_UNREACHABLE_TEXT);
  });
});

// ---------------------------------------------------------------------------
describe("embeddingFailureSentence — the two embedding codes", () => {
  it("answers the no_embedding_model sentence for an ApiError with that code at status 409 — DoD-1", () => {
    const error = new ApiError("no_embedding_model", "refused: no_embedding_model", 409);
    expect(embeddingFailureSentence(error)).toBe(NO_EMBEDDING_MODEL_TEXT);
  });

  it("answers the same sentence when the 409 carries the dimension_mismatch detail — DoD-1", () => {
    // D8: a dimension mismatch is raised as `no_embedding_model` with this exact detail.
    const error = new ApiError("no_embedding_model", "refused: no_embedding_model", 409, {
      reason: "dimension_mismatch",
    });
    expect(embeddingFailureSentence(error)).toBe(NO_EMBEDDING_MODEL_TEXT);
  });

  it("answers the llm_unreachable sentence for an ApiError with that code at status 502 — DoD-1", () => {
    const error = new ApiError("llm_unreachable", "refused: llm_unreachable", 502);
    expect(embeddingFailureSentence(error)).toBe(LLM_UNREACHABLE_TEXT);
  });
});

// ---------------------------------------------------------------------------
describe("embeddingFailureSentence — everything else is null", () => {
  it("answers null for an ApiError whose code is memo_not_found — DoD-1", () => {
    const error = new ApiError("memo_not_found", "refused: memo_not_found", 404);
    expect(embeddingFailureSentence(error)).toBeNull();
  });

  it("answers null for an ApiError whose code is not_authenticated — DoD-1", () => {
    const error = new ApiError("not_authenticated", "refused: not_authenticated", 401);
    expect(embeddingFailureSentence(error)).toBeNull();
  });

  it("answers null for a plain Error — DoD-1", () => {
    expect(embeddingFailureSentence(new Error("Failed to fetch"))).toBeNull();
  });

  it("answers null for undefined — DoD-1", () => {
    expect(embeddingFailureSentence(undefined)).toBeNull();
  });
});
