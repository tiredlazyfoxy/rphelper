// Feature 024, step 008: the one place that turns an authoring write's refusal into the
// sentence the UI shows. A memo create, a memo body edit, a persona edit and a setup-text
// edit are stored only if the searchable copy of the text can be made with them; when it
// cannot, the backend answers `no_embedding_model` (409) or `llm_unreachable` (502) and
// stores nothing (`024/context.md` D8 and its Wire contract). The two sentences therefore
// open with "Not saved:" — they report an outcome, not a warning.
// Pure and total: a free function over the caught value, holding no state, reaching for no
// notification API, and never deciding where its answer is rendered.
import { isApiError } from "./apiError";

/** The refusal code for "no designated, enabled embedding model is usable" (D8). */
const NO_EMBEDDING_MODEL_CODE = "no_embedding_model";

/** The refusal code for "the embed call itself failed" (D8). */
const LLM_UNREACHABLE_CODE = "llm_unreachable";

/**
 * What the UI says when nothing was stored because no embedding model is configured.
 * Verbatim from `024/008.context.md`; callers and tests use this constant, never a retyped
 * copy of the prose.
 */
export const NO_EMBEDDING_MODEL_SENTENCE =
  "Not saved: no embedding model is configured, so this text can't be indexed for search. Ask your administrator to set one.";

/**
 * What the UI says when nothing was stored because the embedding server was unreachable.
 * Verbatim from `024/008.context.md`.
 */
export const LLM_UNREACHABLE_SENTENCE =
  "Not saved: the embedding server could not be reached. Try again in a moment.";

/**
 * Pure: the sentence naming why an authoring write was refused, or null when the caught
 * value is not one of the two embedding refusals — in which case the caller keeps its own
 * generic failure sentence. Anything that is not an `ApiError`, and any other `ApiError`
 * code, answers null.
 */
export function embeddingFailureSentence(error: unknown): string | null {
  if (!isApiError(error)) {
    return null;
  }
  if (error.code === NO_EMBEDDING_MODEL_CODE) {
    return NO_EMBEDDING_MODEL_SENTENCE;
  }
  if (error.code === LLM_UNREACHABLE_CODE) {
    return LLM_UNREACHABLE_SENTENCE;
  }
  return null;
}
