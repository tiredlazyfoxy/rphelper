// The one session label rule plus its two local-time formatters (feature 011 step 005;
// feature 034 step 004, DEC-034-9). A session is named on screen by `sessionLabel`: its
// stored name, or the local `YYYY-MM-DD` of its start when it has none. The time zone is a
// parameter so unit tests can pin exact values; components call without one and get the
// runtime's own zone. Pure: this module imports nothing and reads no browser global.

/** Anything that can be labelled as a session: a stored name (possibly null) and a start. */
export type SessionLabelSource = {
  name: string | null;
  created_at: string; // fixed-width UTC text, `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`
};

/**
 * The one session label (DEC-034-9, US-150): returns `source.name` verbatim when it is
 * non-null — even a name that looks like a date — otherwise `formatLocalDate(created_at,
 * timeZone)`, the local start date with no time. Never trims, never falls back on an empty
 * string (the server stores blank as null).
 *
 * @param source - any row carrying `name` and `created_at`.
 * @param timeZone - optional IANA zone name; omitted means the runtime's resolved zone.
 * @returns the label text.
 */
export function sessionLabel(source: SessionLabelSource, timeZone?: string): string {
  // Only `null` falls back: the server stores a blank name as null, so any string is shown.
  return source.name !== null ? source.name : formatLocalDate(source.created_at, timeZone);
}

/**
 * Formats one fixed-width timestamp (`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`) as the local
 * calendar date `YYYY-MM-DD` in `timeZone` when an IANA zone name is given, else in the
 * runtime's own resolved zone (DEC-arch-session-names-1). Zero-padded, never a time, never
 * locale-dependent text; the date is the local one, so it may differ from the UTC date
 * across a day boundary.
 */
export function formatLocalDate(timestamp: string, timeZone?: string): string {
  // Same Intl approach as `formatLocalDateTime`: `timeZone: undefined` means the runtime's
  // resolved zone, and the date is assembled by hand so locale ordering never leaks in.
  const parts = new Intl.DateTimeFormat(undefined, {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(timestamp));
  const field = (type: string): string => {
    const found = parts.find((part) => part.type === type);
    return found === undefined ? "" : found.value;
  };
  return `${field("year")}-${field("month")}-${field("day")}`;
}

/**
 * Formats one fixed-width timestamp (`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`) as
 * `YYYY-MM-DD HH:MM` (16 characters, zero-padded, 24-hour) in `timeZone` when an IANA zone
 * name is given, else in the runtime's own resolved zone. Never seconds, never a zone
 * suffix, never locale-dependent text, and never rounded up to the next minute. Formerly
 * `formatSessionStart`; renamed because it now formats the last use (DEC-034-9).
 */
export function formatLocalDateTime(createdAt: string, timeZone?: string): string {
  // The explicit `+00:00` offset makes the fixed-width form valid ISO-8601; microseconds
  // beyond milliseconds are truncated, which is immaterial at minute resolution.
  const instant = new Date(createdAt);
  // `timeZone: undefined` is what makes `Intl` use the runtime's own resolved zone, and
  // `hourCycle: "h23"` rather than `hour12: false` keeps midnight at `00` on every engine.
  const parts = new Intl.DateTimeFormat(undefined, {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(instant);
  // Assembled by hand: a locale's own separators and ordering shift between ICU versions.
  const field = (type: string): string => {
    const found = parts.find((part) => part.type === type);
    return found === undefined ? "" : found.value;
  };
  return `${field("year")}-${field("month")}-${field("day")} ${field("hour")}:${field("minute")}`;
}
