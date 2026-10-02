// The setups wire surface (feature 010, step 004): the `Setup` row as the server sends it,
// one pure predicate, and the five calls over the shared client. Two path families, as the
// wire contract has them: `/api/characters/<character_id>/setups` for the listing and the
// create, `/api/setups/<setup_id>` for the update and the two actions. There is no
// single-setup GET: no 010 screen reads one setup by id.
// Ids are decimal strings and are never parsed, coerced or compared numerically.
// Failures are the shared client's `ApiError`s, rethrown unchanged.
import { apiGet, apiPatch, apiPost } from "../shared/api";

/** One setup, exactly as the setups routes send it. No renaming layer. */
export type Setup = {
  id: string;
  character_id: string;
  name: string;
  description: string;
  archived_at: string | null; // fixed-width UTC text, or null while working
  created_at: string;
  updated_at: string;
};

/** The listing route's body: `{ setups: [...] }`. */
export type SetupListResponse = {
  setups: Setup[];
};

/** The create body: both keys always sent. */
export type CreateSetupInput = {
  name: string;
  description: string;
};

/** The update body: exactly the supplied keys are sent. */
export type UpdateSetupPatch = {
  name?: string;
  description?: string;
};

const SETUPS_PATH = "/api/setups";

/** `/api/characters/<characterId>/setups`; the id is only ever escaped, never parsed. */
function characterSetupsPath(characterId: string): string {
  return `/api/characters/${encodeURIComponent(characterId)}/setups`;
}

/** `/api/setups/<setupId>` plus an optional action suffix; the id is only ever escaped. */
function setupPath(setupId: string, suffix = ""): string {
  return `${SETUPS_PATH}/${encodeURIComponent(setupId)}${suffix}`;
}

/** Pure: whether this setup is archived (`archived_at` non-null). */
export function isSetupArchived(setup: Setup): boolean {
  return setup.archived_at !== null;
}

/**
 * `GET /api/characters/<characterId>/setups`, with `?include_archived=true` only when
 * asked. Resolves to the payload's `setups` array, in the order received.
 */
export async function fetchSetups(
  characterId: string,
  includeArchived: boolean,
  signal?: AbortSignal,
): Promise<Setup[]> {
  const listing = characterSetupsPath(characterId);
  const path = includeArchived ? `${listing}?include_archived=true` : listing;
  const body = await apiGet<SetupListResponse | undefined>(path, signal);
  return body?.setups ?? [];
}

/** `POST /api/characters/<characterId>/setups` — resolves to the created setup. */
export async function createSetup(
  characterId: string,
  input: CreateSetupInput,
  signal?: AbortSignal,
): Promise<Setup> {
  return apiPost<Setup>(
    characterSetupsPath(characterId),
    { name: input.name, description: input.description },
    signal,
  );
}

/** `PATCH /api/setups/<setupId>` — sends exactly the supplied keys, resolves to the setup. */
export async function updateSetup(
  setupId: string,
  patch: UpdateSetupPatch,
  signal?: AbortSignal,
): Promise<Setup> {
  const body: UpdateSetupPatch = {};
  if (patch.name !== undefined) {
    body.name = patch.name;
  }
  if (patch.description !== undefined) {
    body.description = patch.description;
  }
  return apiPatch<Setup>(setupPath(setupId), body, signal);
}

/** `POST /api/setups/<setupId>/archive` — resolves to the setup. */
export async function archiveSetup(setupId: string, signal?: AbortSignal): Promise<Setup> {
  return apiPost<Setup>(setupPath(setupId, "/archive"), undefined, signal);
}

/** `POST /api/setups/<setupId>/restore` — resolves to the setup. */
export async function restoreSetup(setupId: string, signal?: AbortSignal): Promise<Setup> {
  return apiPost<Setup>(setupPath(setupId, "/restore"), undefined, signal);
}
