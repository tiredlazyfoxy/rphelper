// The shared file-import helper (feature 031, step 006). Both entries import a chosen export
// file the same way: read its text, `JSON.parse` it, and post the parsed object as the JSON body
// through the existing `apiPost`. There is no multipart and no new dependency — the transport is
// the one `shared/api.ts` already owns (`031/context.md` §Transport).
//
// This module raises **no notification** and imports neither `notifyFailure` nor
// `@mantine/notifications`. It throws, and each entry routes the thrown value its own way:
// `notifyFailure` in `app`, the inline red `Alert` in `admin`. If it notified, the admin Database
// page would start raising notifications and break its inline-only rule.
//
// Ids are strings end to end: nothing here parses, widens or re-formats one.
import { apiPost } from "./api";
import { ApiError } from "./apiError";

/** Synthetic code: the chosen file could not be read, is not JSON, or is not a JSON object. */
export const CLIENT_UNREADABLE_FILE = "client_unreadable_file";

/**
 * The one message every unreadable-file failure carries. Its three causes are deliberately
 * indistinguishable, so nothing about the chosen file's content reaches the roleplayer.
 */
const UNREADABLE_FILE_MESSAGE = "The chosen file is not a readable export.";

/**
 * The only failure this module raises itself. Status `0` because no request was made: the file
 * never left the browser, so there is no HTTP status to report.
 */
function unreadableFile(): ApiError {
  return new ApiError(CLIENT_UNREADABLE_FILE, UNREADABLE_FILE_MESSAGE, 0);
}

/**
 * The one thing a chosen export file must offer: an async `text()`.
 *
 * A real `File` (what Mantine's `FileButton` hands to its `onChange`) satisfies this through
 * `Blob.prototype.text`, so every call site can pass one unchanged. Typing the structural
 * contract rather than `File` keeps the helper independent of the DOM file picker.
 */
export type ReadableTextFile = {
  text(): Promise<string>;
};

/**
 * Reads the chosen file and resolves to the parsed JSON **object**. It sends nothing.
 *
 * Rejects with an `ApiError` carrying code `CLIENT_UNREADABLE_FILE`, status `0` and the message
 * exactly `The chosen file is not a readable export.` when `text()` rejects, when the text is not
 * JSON, or when the parsed value is not a plain object — `null` and arrays included.
 *
 * @param file anything with an async `text()`.
 */
export async function readExportFile(file: ReadableTextFile): Promise<Record<string, unknown>> {
  let text: string;
  try {
    text = await file.text();
  } catch {
    throw unreadableFile();
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(text) as unknown;
  } catch {
    throw unreadableFile();
  }

  // The plain-object test `api.ts` keeps module-private, restated here: `typeof null` is
  // `"object"` and an array is an object too, so both need naming explicitly.
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw unreadableFile();
  }

  return parsed as Record<string, unknown>;
}

/**
 * Effect: reads `file` with `readExportFile`, then posts the parsed object to `path` through the
 * existing `apiPost(path, parsed, signal)`, and resolves to its decoded result.
 *
 * It adds no failure handling of its own. The unreadable-file `ApiError` from `readExportFile`
 * and every `ApiError` `apiPost` already throws — including its 401, which navigates to `/login`
 * on the way out — propagate unchanged, and so does an abort.
 *
 * @param path an `/api/...` import route.
 * @param file the chosen export file.
 * @param signal optional; passed straight to `apiPost`.
 */
export async function postExportFile<T = unknown>(
  path: string,
  file: ReadableTextFile,
  signal?: AbortSignal,
): Promise<T> {
  const parsed = await readExportFile(file);
  return await apiPost<T>(path, parsed, signal);
}
