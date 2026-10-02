// The one start-time label formatter (feature 011, step 005, D4). A session carries no
// title, so its label is its `created_at` rendered as `YYYY-MM-DD HH:MM` — 24-hour,
// zero-padded, one space between date and time. The time zone is a parameter so the unit
// tests can pin exact values; components call it without one and get the runtime's own zone.
// Pure: this module imports nothing and reads no browser global.

/**
 * Formats one fixed-width timestamp (`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`) as
 * `YYYY-MM-DD HH:MM` in `timeZone` when an IANA zone name is given, else in the runtime's
 * own resolved zone. Never seconds, never a zone suffix, never locale-dependent text, and
 * never rounded up to the next minute.
 */
export function formatSessionStart(createdAt: string, timeZone?: string): string {
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
