// Dev-only request logger for Vite's `/api` proxy (fast/007).
// Side-effect-free: importing this module registers nothing and writes nothing.
// Compiled under both tsconfig.json and tsconfig.node.json — no DOM APIs, no env reads.
import type { ProxyOptions } from "vite";

/** Minimal structural emitter: Vite's ProxyServer and a plain Node EventEmitter both fit. */
export interface ProxyEmitter {
  on(event: string, listener: (...args: unknown[]) => void): unknown;
}

/** Optional injection points for attachProxyLogging. */
export interface ProxyLogOptions {
  /** Receives one finished line with no trailing newline. Default: process.stdout.write(line + "\n"). */
  sink?: (line: string) => void;
  /** Current time in milliseconds. */
  now?: () => number;
}

function readString(obj: unknown, key: string): string | undefined {
  if (typeof obj !== "object" || obj === null) return undefined;
  try {
    const value: unknown = (obj as Record<string, unknown>)[key];
    return typeof value === "string" ? value : undefined;
  } catch {
    return undefined;
  }
}

function readNumber(obj: unknown, key: string): number | undefined {
  if (typeof obj !== "object" || obj === null) return undefined;
  try {
    const value: unknown = (obj as Record<string, unknown>)[key];
    return typeof value === "number" && Number.isFinite(value) ? value : undefined;
  } catch {
    return undefined;
  }
}

/** Default line sink shared with fast/008's request logger: `process.stdout.write(line + "\n")`. */
function defaultSink(line: string): void {
  process.stdout.write(line + "\n");
}

/** Default clock shared with fast/008's request logger: `performance.now()`. */
function defaultNow(): number {
  return performance.now();
}

/** Path with everything from the first `?` and first `#` removed; `-` for a missing/empty URL. */
export function redactPath(url: string | undefined): string {
  if (typeof url !== "string" || url === "") return "-";
  let end = url.length;
  const q = url.indexOf("?");
  if (q !== -1) end = q;
  const h = url.indexOf("#");
  if (h !== -1 && h < end) end = h;
  const path = url.slice(0, end);
  return path === "" ? "-" : path;
}

/** `<METHOD> <path> <status> <ms>ms`. */
export function formatSuccessLine(
  method: string | undefined,
  url: string | undefined,
  status: number | undefined,
  durationMs: number,
): string {
  const m = typeof method === "string" && method !== "" ? method : "-";
  const s = typeof status === "number" && Number.isFinite(status) ? String(status) : "-";
  const ms = Number.isFinite(durationMs) ? Math.max(0, Math.round(durationMs)) : 0;
  return `${m} ${redactPath(url)} ${s} ${ms}ms`;
}

/** `<METHOD> <path> proxy error <CODE>`; CODE is err.code when a non-empty string, else `unknown`. */
export function formatErrorLine(
  method: string | undefined,
  url: string | undefined,
  err: unknown,
): string {
  const m = typeof method === "string" && method !== "" ? method : "-";
  const code = readString(err, "code");
  return `${m} ${redactPath(url)} proxy error ${code !== undefined && code !== "" ? code : "unknown"}`;
}

/** Subscribes to `start`, `proxyReq`, `proxyRes`, `error`; emits at most one line per request. */
export function attachProxyLogging(proxy: ProxyEmitter, options?: ProxyLogOptions): void {
  const sink = options?.sink ?? defaultSink;
  const now = options?.now ?? defaultNow;
  const started = new WeakMap<object, number>();
  const logged = new WeakSet<object>();

  const isKey = (value: unknown): value is object =>
    (typeof value === "object" && value !== null) || typeof value === "function";

  const emit = (req: unknown, line: () => string): void => {
    if (isKey(req)) {
      if (logged.has(req)) return;
      logged.add(req);
    }
    sink(line());
  };

  const durationFor = (req: unknown): number => {
    if (!isKey(req)) return 0;
    const t0 = started.get(req);
    return t0 === undefined ? 0 : now() - t0;
  };

  const guard =
    (fn: (...args: unknown[]) => void) =>
    (...args: unknown[]): void => {
      try {
        fn(...args);
      } catch {
        // A logging failure must never disturb the proxy.
      }
    };

  proxy.on(
    "start",
    guard((req) => {
      if (isKey(req) && !started.has(req)) started.set(req, now());
    }),
  );
  proxy.on(
    "proxyReq",
    guard((_proxyReq, req) => {
      if (isKey(req) && !started.has(req)) started.set(req, now());
    }),
  );
  proxy.on(
    "proxyRes",
    guard((proxyRes, req) => {
      emit(req, () =>
        formatSuccessLine(
          readString(req, "method"),
          readString(req, "url"),
          readNumber(proxyRes, "statusCode"),
          durationFor(req),
        ),
      );
    }),
  );
  proxy.on(
    "error",
    guard((err, req) => {
      emit(req, () => formatErrorLine(readString(req, "method"), readString(req, "url"), err));
    }),
  );
}

/**
 * Ready-made `configure` hook for vite.config.ts: attaches the logger with default sink and clock.
 * Vite calls `configure` whenever it creates a server with proxy middleware — this includes
 * Vitest's own internal server at startup — so this hook only subscribes listeners and never throws.
 */
export const configureProxyLogging: NonNullable<ProxyOptions["configure"]> = (proxy) => {
  try {
    attachProxyLogging(proxy);
  } catch {
    // Never let the dev logger break server startup.
  }
};
