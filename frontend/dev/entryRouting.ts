// Dev-only entry routing for the Vite dev server (fast/009): mirrors prod nginx so `/` and
// app client routes serve the `app` document, `/<entry>/…` serve their own entry document,
// and slash-less `/bootstrap`, `/login`, `/admin` get a relative 302.
// Side-effect-free: importing this module registers nothing and writes nothing.
// Compiled under both tsconfig.json and tsconfig.node.json — no DOM APIs, no env reads.
import { statSync } from "node:fs";
import { isAbsolute, relative, resolve, sep } from "node:path";
import type { Plugin } from "vite";

/** Structural request shape: Node's IncomingMessage and plain EventEmitter-based fakes both fit. */
export interface EntryRoutingRequest {
  url?: unknown;
  method?: unknown;
}

/**
 * Structural response shape: Node's ServerResponse and plain EventEmitter-based fakes both fit.
 * Members are `unknown` because the middleware must tolerate a response missing methods;
 * it uses `statusCode`, `setHeader(name, value)` and `end()` when present.
 */
export interface EntryRoutingResponse {
  statusCode?: unknown;
  setHeader?: unknown;
  end?: unknown;
}

/** Connect-style middleware; assignable to Vite's `server.middlewares.use` without a cast. */
export type EntryRoutingMiddleware = (
  req: EntryRoutingRequest,
  res: EntryRoutingResponse,
  next: () => void,
) => void;

/** Options for createEntryRoutingMiddleware. */
export interface EntryRoutingOptions {
  /** Absolute server root directory (Vite's `server.config.root`). */
  root: string;
  /**
   * File-existence predicate over an absolute path. Default: true only for an existing
   * regular file (stat-based); missing path, directory or error → false.
   */
  isFile?: (absolutePath: string) => boolean;
}

/** Frozen plugin name. Must not contain `react`. */
export const ENTRY_ROUTING_PLUGIN_NAME = "rphelper-dev-entry-routing";

/**
 * Routing middleware: passes through non-GET/HEAD, `/api`, `/@…`, `/__…`, `/node_modules/…`,
 * extension paths and existing files under root; 302s exact `/bootstrap|/login|/admin` to
 * `/<entry>/`; rewrites `/<entry>/…` to `/<entry>/index.html` and everything else to
 * `/app/index.html`. Never throws; calls `next()` at most once, synchronously, no argument.
 */
export function createEntryRoutingMiddleware(options: EntryRoutingOptions): EntryRoutingMiddleware {
  const root = readField(options, "root");
  const injected = readField(options, "isFile");
  const isFile =
    typeof injected === "function" ? (injected as (absolutePath: string) => boolean) : defaultIsFile;

  return (req, res, next) => {
    const originalUrl = readField(req, "url");
    let rewritten = false;
    try {
      const target = route(req, root, isFile);
      if (target.kind === "redirect") {
        if (sendRedirect(res, target.location)) return;
      } else if (target.kind === "rewrite") {
        rewritten = true;
        (req as { url?: unknown }).url = target.url;
      }
    } catch {
      if (rewritten) {
        try {
          (req as { url?: unknown }).url = originalUrl;
        } catch {
          // Unwritable request: nothing more to restore.
        }
      }
    }
    next();
  };
}

const ENTRY_NAMES: readonly string[] = ["bootstrap", "login", "admin"];

type RouteDecision =
  | { kind: "pass" }
  | { kind: "redirect"; location: string }
  | { kind: "rewrite"; url: string };

function route(
  req: EntryRoutingRequest,
  root: unknown,
  isFile: (absolutePath: string) => boolean,
): RouteDecision {
  const method = readField(req, "method");
  const url = readField(req, "url");
  if ((method !== "GET" && method !== "HEAD") || typeof url !== "string") return { kind: "pass" };
  if (!url.startsWith("/")) return { kind: "pass" };

  const end = url.search(/[?#]/);
  const pathname = decodeURIComponent(end === -1 ? url : url.slice(0, end));

  if (pathname === "/api" || pathname.startsWith("/api/")) return { kind: "pass" };
  if (pathname.startsWith("/@") || pathname.startsWith("/__") || pathname.startsWith("/node_modules/")) {
    return { kind: "pass" };
  }
  const lastSegment = pathname.slice(pathname.lastIndexOf("/") + 1);
  if (lastSegment.includes(".")) return { kind: "pass" };
  if (existsUnderRoot(root, pathname, isFile)) return { kind: "pass" };

  for (const entry of ENTRY_NAMES) {
    if (pathname === `/${entry}`) return { kind: "redirect", location: `/${entry}/` };
    if (pathname.startsWith(`/${entry}/`)) return { kind: "rewrite", url: `/${entry}/index.html` };
  }
  return { kind: "rewrite", url: "/app/index.html" };
}

function existsUnderRoot(
  root: unknown,
  pathname: string,
  isFile: (absolutePath: string) => boolean,
): boolean {
  if (typeof root !== "string" || root === "") return false;
  const rootDir = resolve(root);
  const candidate = resolve(rootDir, `.${pathname}`);
  const rel = relative(rootDir, candidate);
  if (rel === "" || rel === ".." || rel.startsWith(`..${sep}`) || isAbsolute(rel)) return false;
  return isFile(candidate) === true;
}

function defaultIsFile(absolutePath: string): boolean {
  try {
    return statSync(absolutePath, { throwIfNoEntry: false })?.isFile() === true;
  } catch {
    return false;
  }
}

/** Sends a 302; returns false (nothing begun) when the response lacks the needed methods. */
function sendRedirect(res: EntryRoutingResponse, location: string): boolean {
  const setHeader = readField(res, "setHeader");
  const end = readField(res, "end");
  if (typeof setHeader !== "function" || typeof end !== "function") return false;
  (res as { statusCode?: unknown }).statusCode = 302;
  (setHeader as (name: string, value: string) => unknown).call(res, "Location", location);
  try {
    (end as () => unknown).call(res);
  } catch {
    // The response has begun; never fall through to next().
  }
  return true;
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
 * Pure: rewrites every relative `src` of a `<script type="module">` in `html` to an absolute
 * path resolved against the directory of `documentPath` (query/fragment ignored). Everything
 * else is returned byte-identical. Never throws; an unusable `documentPath` returns `html`.
 */
export function absolutizeModuleScriptSrc(html: string, documentPath: string): string {
  try {
    if (typeof html !== "string" || typeof documentPath !== "string") return html;
    const end = documentPath.search(/[?#]/);
    const docPath = end === -1 ? documentPath : documentPath.slice(0, end);
    if (!docPath.startsWith("/") || docPath.startsWith("//") || docPath.includes("\\")) return html;
    const base = new URL(docPath, "http://localhost");

    return html.replace(SCRIPT_OPEN_TAG, (tag: string) => {
      if (!MODULE_TYPE_ATTR.test(tag)) return tag;
      return tag.replace(
        SRC_ATTR,
        (whole: string, prefix: string, dq?: string, sq?: string, bare?: string): string => {
          const value = dq ?? sq ?? bare ?? "";
          if (!isRelativeSrc(value)) return whole;
          const resolved = new URL(value, base);
          const absolute = `${resolved.pathname}${resolved.search}${resolved.hash}`;
          if (dq !== undefined) return `${prefix}"${absolute}"`;
          if (sq !== undefined) return `${prefix}'${absolute}'`;
          return `${prefix}${absolute}`;
        },
      );
    });
  } catch {
    return html;
  }
}

const SCRIPT_OPEN_TAG = /<script\b[^>]*>/gi;
const MODULE_TYPE_ATTR = /\stype\s*=\s*(?:"module"|'module'|module(?=[\s/>]))/i;
const SRC_ATTR = /(\ssrc\s*=\s*)(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))/i;

function isRelativeSrc(src: string): boolean {
  if (src.trim() === "") return false;
  if (src.startsWith("/") || src.startsWith("\\")) return false;
  return !/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(src);
}

/**
 * Vite plugin (`apply: "serve"`) whose `configureServer` registers exactly one middleware from
 * createEntryRoutingMiddleware directly on `server.middlewares` (root = `server.config.root`)
 * and returns nothing, plus a `pre` `transformIndexHtml` hook delegating to
 * absolutizeModuleScriptSrc(html, ctx.path). Vitest runs `configureServer` at startup, so
 * attaching must never write or throw.
 */
export function devEntryRoutingPlugin(): Plugin {
  return {
    name: ENTRY_ROUTING_PLUGIN_NAME,
    apply: "serve",
    configureServer(server): void {
      server.middlewares.use(createEntryRoutingMiddleware({ root: server.config.root }));
    },
    transformIndexHtml: {
      order: "pre",
      handler(html, ctx): string {
        return absolutizeModuleScriptSrc(html, ctx.path);
      },
    },
  };
}
