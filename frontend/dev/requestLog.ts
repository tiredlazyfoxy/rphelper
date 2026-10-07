// Dev-only request logger for every request the Vite dev server receives (fast/008).
// Side-effect-free: importing this module registers nothing and writes nothing.
// Compiled under both tsconfig.json and tsconfig.node.json — no DOM APIs, no env reads.
import type { Plugin } from "vite";
import { defaultNow, defaultSink, formatSuccessLine } from "./proxyLog.ts";
import type { ProxyLogOptions } from "./proxyLog.ts";

/** Structural request shape: Node's IncomingMessage and plain EventEmitter-based fakes both fit. */
export interface RequestLike {
  url?: unknown;
  method?: unknown;
}

/** Structural response shape: Node's ServerResponse and plain EventEmitter-based fakes both fit. */
export interface ResponseLike {
  statusCode?: unknown;
  on(event: string, listener: (...args: unknown[]) => void): unknown;
}

/** Connect-style middleware; assignable to Vite's `server.middlewares.use` without a cast. */
export type RequestLogMiddleware = (req: RequestLike, res: ResponseLike, next: () => void) => void;

/** Frozen plugin name. */
export const REQUEST_LOG_PLUGIN_NAME = "rphelper-dev-request-log";

/**
 * Middleware that logs `<METHOD> <path> <status> <ms>ms` on the first of `finish`/`close`;
 * skips URLs starting with `/api`. Defaults: proxyLog's `defaultSink` and `defaultNow`.
 */
export function createRequestLogMiddleware(options?: ProxyLogOptions): RequestLogMiddleware {
  const sink = options?.sink ?? defaultSink;
  const now = options?.now ?? defaultNow;

  return (req, res, next) => {
    try {
      const url = readField(req, "url");
      if (!(typeof url === "string" && url.startsWith("/api"))) {
        const method = readField(req, "method");
        const start = now();
        let logged = false;
        const log = (status: number | undefined): void => {
          try {
            if (logged) return;
            logged = true;
            sink(
              formatSuccessLine(
                typeof method === "string" ? method : undefined,
                typeof url === "string" ? url : undefined,
                status,
                now() - start,
              ),
            );
          } catch {
            // A logging failure must never disturb the dev server.
          }
        };
        res.on("finish", () => {
          const status = readField(res, "statusCode");
          log(typeof status === "number" && Number.isFinite(status) ? status : undefined);
        });
        res.on("close", () => {
          log(undefined);
        });
      }
    } catch {
      // Malformed request/response: skip logging, still hand off to the next middleware.
    }
    next();
  };
}

function readField(obj: unknown, key: string): unknown {
  if (typeof obj !== "object" || obj === null) return undefined;
  try {
    return (obj as Record<string, unknown>)[key];
  } catch {
    return undefined;
  }
}

/**
 * Vite plugin (`apply: "serve"`) whose `configureServer` registers one middleware from
 * createRequestLogMiddleware directly on `server.middlewares` and returns nothing.
 * Vitest runs `configureServer` at startup, so attaching must never write or throw.
 */
export function devRequestLogPlugin(options?: ProxyLogOptions): Plugin {
  return {
    name: REQUEST_LOG_PLUGIN_NAME,
    apply: "serve",
    configureServer(server): void {
      server.middlewares.use(createRequestLogMiddleware(options));
    },
  };
}
