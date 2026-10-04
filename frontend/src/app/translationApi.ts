// The translation wire surface (feature 023, step 004): the `Translation` payload the
// translate route sends, and the one call that asks for it. Ids are decimal strings and are
// never parsed, coerced or compared numerically. Failures are the shared client's `ApiError`s,
// rethrown unchanged; an abort is rethrown raw, not wrapped (D4, the wire contract).
import { apiPost } from "../shared/api";

/**
 * `POST /api/messages/<id>/translation`'s body, exactly as the route sends it. `cached` is
 * `true` when the server answered from its cache without a model call.
 */
export type Translation = {
  message_id: string;
  target_language: string;
  text: string;
  cached: boolean;
};

/**
 * `POST /api/messages/<messageId>/translation` with **no request body**, threading `signal`.
 * Resolves to the served `Translation`. Rejects with `ApiError` on non-2xx (502
 * `translation_failed` included) and rethrows an abort raw.
 */
export async function translateMessage(
  messageId: string,
  signal?: AbortSignal,
): Promise<Translation> {
  // `undefined` as the body is how no request body is sent; the signal threads into `fetch`.
  return apiPost<Translation>(
    `/api/messages/${encodeURIComponent(messageId)}/translation`,
    undefined,
    signal,
  );
}
