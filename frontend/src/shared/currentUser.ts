// The one definition of the signed-in identity (008 context.md D1): the `GET /api/me`
// shape plus the probe that fetches it. Generic infrastructure — it names no entry's own
// route and adds no error handling of its own.
import { apiGet } from "./api";

/** The identity `GET /api/me` answers with. `id` is a decimal string and is never parsed. */
export type CurrentUser = {
  id: string;
  username: string;
  role: "roleplayer" | "admin";
};

const ME_PATH = "/api/me";

/**
 * Impure: one `GET /api/me` through the shared client. Every failure propagates exactly as
 * the client threw it — including the client's own 401 navigation to `/login`.
 */
export async function fetchCurrentUser(signal?: AbortSignal): Promise<CurrentUser> {
  return apiGet<CurrentUser>(ME_PATH, signal);
}
