// The `/api/characters` wire surface (feature 009, step 004): the `Character` row as the
// server sends it, one pure predicate, and the six calls over the shared client.
// Ids are decimal strings and are never parsed, coerced or compared numerically.
import { apiGet, apiPatch, apiPost } from "../shared/api";

/** One character, exactly as `/api/characters` sends it. No renaming layer. */
export type Character = {
  id: string;
  name: string;
  sheet: string;
  archived_at: string | null; // fixed-width UTC text, or null while working
  created_at: string;
  updated_at: string;
};

/** The listing route's body: `{ characters: [...] }`. */
export type CharacterListResponse = {
  characters: Character[];
};

/** The create body: both keys always sent. */
export type CreateCharacterInput = {
  name: string;
  sheet: string;
};

/** The update body: exactly the supplied keys are sent. */
export type UpdateCharacterPatch = {
  name?: string;
  sheet?: string;
};

const CHARACTERS_PATH = "/api/characters";

/** `/api/characters/<id>`; the id is a string and is only ever escaped, never parsed. */
function characterPath(characterId: string, suffix = ""): string {
  return `${CHARACTERS_PATH}/${encodeURIComponent(characterId)}${suffix}`;
}

/** Pure: whether this character is archived (`archived_at` non-null). */
export function isArchived(character: Character): boolean {
  return character.archived_at !== null;
}

/** `GET /api/characters`, with `?include_archived=true` only when asked. */
export async function fetchCharacters(
  includeArchived: boolean,
  signal?: AbortSignal,
): Promise<Character[]> {
  const path = includeArchived ? `${CHARACTERS_PATH}?include_archived=true` : CHARACTERS_PATH;
  const body = await apiGet<CharacterListResponse | undefined>(path, signal);
  return body?.characters ?? [];
}

/** `GET /api/characters/<characterId>` — archived or not. */
export async function fetchCharacter(characterId: string, signal?: AbortSignal): Promise<Character> {
  return apiGet<Character>(characterPath(characterId), signal);
}

/** `POST /api/characters` — resolves to the created character. */
export async function createCharacter(
  input: CreateCharacterInput,
  signal?: AbortSignal,
): Promise<Character> {
  return apiPost<Character>(CHARACTERS_PATH, { name: input.name, sheet: input.sheet }, signal);
}

/** `PATCH /api/characters/<characterId>` — resolves to the updated character. */
export async function updateCharacter(
  characterId: string,
  patch: UpdateCharacterPatch,
  signal?: AbortSignal,
): Promise<Character> {
  const body: UpdateCharacterPatch = {};
  if (patch.name !== undefined) {
    body.name = patch.name;
  }
  if (patch.sheet !== undefined) {
    body.sheet = patch.sheet;
  }
  return apiPatch<Character>(characterPath(characterId), body, signal);
}

/** `POST /api/characters/<characterId>/archive` — resolves to the character. */
export async function archiveCharacter(characterId: string, signal?: AbortSignal): Promise<Character> {
  return apiPost<Character>(characterPath(characterId, "/archive"), undefined, signal);
}

/** `POST /api/characters/<characterId>/restore` — resolves to the character. */
export async function restoreCharacter(characterId: string, signal?: AbortSignal): Promise<Character> {
  return apiPost<Character>(characterPath(characterId, "/restore"), undefined, signal);
}
