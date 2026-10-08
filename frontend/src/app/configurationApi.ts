// The configuration wire surface (feature 017, step 006): the enabled-model list, the
// user's own settings and a session's resolved configuration, as the server sends them, and
// one call per route over the shared client. Feature 018 (step 006) adds the character's
// own configuration: one fetch and one update call, and nothing else character-addressed.
// Ids are decimal strings and are never parsed, coerced or compared numerically.
// Failures are the shared client's `ApiError`s, rethrown unchanged; an abort is rethrown as
// the abort.
import { apiGet, apiPatch } from "../shared/api";

/** A chosen model: a server id and a model name on it. */
export type ModelRef = {
  server_id: string;
  model_name: string;
};

/** One enabled chat model, as `GET /api/models` lists it. */
export type EnabledModel = {
  server_id: string;
  server_name: string;
  model_name: string;
};

/** The user's own language settings. */
export type UserSettings = {
  rp_language: string | null;
  preferred_language: string | null;
};

/** The four levels a setting can be supplied by. */
export type ConfigLevel = "session" | "character" | "user" | "default";

/** One resolved setting: the session's own override, what is inherited, and the result. */
export type Setting<T extends string | boolean> = {
  session: T | null;
  inherited: T | null;
  inherited_level: ConfigLevel | null;
  value: T | null;
  level: ConfigLevel | null;
};

/** A session's resolved configuration: exactly the seven keys. */
export type SessionConfiguration = {
  model: ModelRef | null;
  system_prompt: Setting<string>;
  tool_memo_search: Setting<boolean>;
  tool_session_search: Setting<boolean>;
  tool_web_search: Setting<boolean>;
  rp_language: Setting<string>;
  preferred_language: Setting<string>;
};

/** The user settings update body: exactly the supplied keys are sent; null clears. */
export type UserSettingsPatch = {
  rp_language?: string | null;
  preferred_language?: string | null;
};

/**
 * The session configuration update body: exactly the supplied keys are sent; null clears
 * a level back to inherit. `model` is never null (D10).
 */
export type SessionConfigurationPatch = {
  model?: ModelRef;
  system_prompt?: string | null;
  tool_memo_search?: boolean | null;
  tool_session_search?: boolean | null;
  tool_web_search?: boolean | null;
  rp_language?: string | null;
  preferred_language?: string | null;
};

/**
 * A character's own configuration (018 D9): each key is the character's own value, or null
 * for "not set". Flat — not the session's `Setting<T>` shape. No language key.
 */
export type CharacterConfiguration = {
  model: ModelRef | null;
  system_prompt: string | null;
  tool_memo_search: boolean | null;
  tool_session_search: boolean | null;
  tool_web_search: boolean | null;
};

/**
 * The character configuration update body: exactly the supplied keys are sent; null clears
 * a key back to "not set" (`model: null` included, 017 D10). It admits no language key.
 */
export type CharacterConfigurationPatch = {
  model?: ModelRef | null;
  system_prompt?: string | null;
  tool_memo_search?: boolean | null;
  tool_session_search?: boolean | null;
  tool_web_search?: boolean | null;
};

/** The model listing route's body: `{ models: [...] }`. */
type EnabledModelListResponse = {
  models: EnabledModel[];
};

const MODELS_PATH = "/api/models";
const USER_SETTINGS_PATH = "/api/me/settings";

/** `/api/sessions/<sessionId>/configuration`; the id is only ever escaped, never parsed. */
function sessionConfigurationPath(sessionId: string): string {
  return `/api/sessions/${encodeURIComponent(sessionId)}/configuration`;
}

/** `/api/characters/<characterId>/configuration`; the id is only ever escaped, never parsed. */
function characterConfigurationPath(characterId: string): string {
  return `/api/characters/${encodeURIComponent(characterId)}/configuration`;
}

/** `GET /api/models` — resolves to the payload's `models` array, in server order. */
export async function fetchEnabledModels(signal?: AbortSignal): Promise<EnabledModel[]> {
  const body = await apiGet<EnabledModelListResponse | undefined>(MODELS_PATH, signal);
  return body?.models ?? [];
}

/** `GET /api/me/settings` — resolves to the user's settings. */
export async function fetchUserSettings(signal?: AbortSignal): Promise<UserSettings> {
  return apiGet<UserSettings>(USER_SETTINGS_PATH, signal);
}

/** `PATCH /api/me/settings` — sends exactly the keys present, resolves to the settings. */
export async function updateUserSettings(
  patch: UserSettingsPatch,
  signal?: AbortSignal,
): Promise<UserSettings> {
  return apiPatch<UserSettings>(USER_SETTINGS_PATH, patch, signal);
}

/** `GET /api/sessions/<sessionId>/configuration` — resolves to the configuration. */
export async function fetchSessionConfiguration(
  sessionId: string,
  signal?: AbortSignal,
): Promise<SessionConfiguration> {
  return apiGet<SessionConfiguration>(sessionConfigurationPath(sessionId), signal);
}

/**
 * `PATCH /api/sessions/<sessionId>/configuration` — sends exactly the keys present,
 * resolves to the configuration.
 */
export async function updateSessionConfiguration(
  sessionId: string,
  patch: SessionConfigurationPatch,
  signal?: AbortSignal,
): Promise<SessionConfiguration> {
  return apiPatch<SessionConfiguration>(sessionConfigurationPath(sessionId), patch, signal);
}

/** `GET /api/characters/<characterId>/configuration` — resolves to the configuration. */
export async function fetchCharacterConfiguration(
  characterId: string,
  signal?: AbortSignal,
): Promise<CharacterConfiguration> {
  return apiGet<CharacterConfiguration>(characterConfigurationPath(characterId), signal);
}

/**
 * `PATCH /api/characters/<characterId>/configuration` — sends exactly the keys present,
 * resolves to the configuration.
 */
export async function updateCharacterConfiguration(
  characterId: string,
  patch: CharacterConfigurationPatch,
  signal?: AbortSignal,
): Promise<CharacterConfiguration> {
  return apiPatch<CharacterConfiguration>(characterConfigurationPath(characterId), patch, signal);
}
