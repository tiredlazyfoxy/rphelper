// Fast feature 009 — Vite dev-server root routing (DoD-1..DoD-16).
// Expected values come from docs/plans/fast/009.vite-dev-root-routing/plan.md and context.md.
// Bindings come from the `## Skeleton` record in that plan's status.md.
// DoD-17 is covered by the existing build-config / entries / request-log / proxy-log tests,
// which run unedited; nothing here touches them.
import { EventEmitter } from "node:events";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi, type Mock } from "vitest";
import {
  ENTRY_ROUTING_PLUGIN_NAME,
  absolutizeModuleScriptSrc,
  createEntryRoutingMiddleware,
  devEntryRoutingPlugin,
  type EntryRoutingMiddleware,
  type EntryRoutingOptions,
  type EntryRoutingRequest,
  type EntryRoutingResponse,
} from "../dev/entryRouting.ts";
import { createRequestLogMiddleware } from "../dev/requestLog.ts";
import config from "../vite.config";

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

/** A root directory that need not exist; tests using it inject their own predicate. */
const FAKE_ROOT = path.resolve(os.tmpdir(), "rphelper-entry-routing-fake-root");

type FakeReq = EventEmitter & { method?: string; url?: string; headers: Record<string, string> };

function fakeReq(method: string | undefined, url: string | undefined, headers: Record<string, string> = {}): FakeReq {
  const req = Object.assign(new EventEmitter(), { headers }) as FakeReq;
  if (method !== undefined) req.method = method;
  if (url !== undefined) req.url = url;
  return req;
}

type FakeRes = EventEmitter & {
  statusCode: number;
  headers: Record<string, string | string[]>;
  end: Mock;
  write: Mock;
  writeHead: Mock;
  setHeader: Mock;
};

function fakeRes(statusCode = 200): FakeRes {
  return Object.assign(new EventEmitter(), {
    statusCode,
    headers: {},
    end: vi.fn(),
    write: vi.fn(),
    writeHead: vi.fn(),
    setHeader: vi.fn(),
  });
}

type Run = { req: FakeReq; res: FakeRes; next: Mock };

function makeMw(options: Partial<EntryRoutingOptions> = {}): EntryRoutingMiddleware {
  return createEntryRoutingMiddleware({ root: FAKE_ROOT, isFile: () => false, ...options });
}

function run(mw: EntryRoutingMiddleware, method: string | undefined, url: string | undefined): Run {
  const req = fakeReq(method, url);
  const res = fakeRes(200);
  const next = vi.fn();
  expect(() => mw(req, res, next)).not.toThrow();
  return { req, res, next };
}

/** "routes to X" per the plan's DoD preamble. */
function expectRoutedTo(r: Run, expected: string): void {
  expect(r.req.url).toBe(expected);
  expect(r.next).toHaveBeenCalledTimes(1);
  expect(r.next.mock.calls[0]).toHaveLength(0);
  expect(r.res.end).not.toHaveBeenCalled();
  expect(r.res.write).not.toHaveBeenCalled();
  expect(r.res.writeHead).not.toHaveBeenCalled();
  expect(r.res.setHeader).not.toHaveBeenCalled();
  expect(r.res.statusCode).toBe(200);
}

/** "untouched": routes to its own input URL. */
function expectUntouched(r: Run, input: string | undefined): void {
  expectRoutedTo(r, input as string);
}

function expectRedirect(r: Run, location: string): void {
  expect(r.res.statusCode).toBe(302);
  const locationCalls = r.res.setHeader.mock.calls.filter(
    (call) => typeof call[0] === "string" && (call[0] as string).toLowerCase() === "location",
  );
  expect(locationCalls).toHaveLength(1);
  expect(locationCalls[0]?.[1]).toBe(location);
  expect(r.res.end).toHaveBeenCalled();
  expect(r.next).not.toHaveBeenCalled();
}

function isInside(root: string, candidate: string): boolean {
  const rel = path.relative(root, candidate);
  return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}

type HookFn = (server: unknown) => unknown;

function configureServerFn(plugin: unknown): HookFn {
  const hook = (plugin as { configureServer?: unknown }).configureServer;
  if (typeof hook === "function") return hook as HookFn;
  if (hook !== null && typeof hook === "object" && typeof (hook as { handler?: unknown }).handler === "function") {
    return (hook as { handler: HookFn }).handler;
  }
  throw new Error("plugin has no configureServer hook");
}

type FakeServer = { config: { root: string }; middlewares: { use: (...args: unknown[]) => unknown } };

function fakeServer(root: string): { server: FakeServer; calls: unknown[][] } {
  const calls: unknown[][] = [];
  const server: FakeServer = {
    config: { root },
    middlewares: {
      use: (...args: unknown[]) => {
        calls.push(args);
        return server.middlewares;
      },
    },
  };
  return { server, calls };
}

type HtmlHandler = (html: string, ctx: unknown) => unknown;

function transformHook(plugin: unknown): { order: unknown; handler: HtmlHandler } {
  const hook = (plugin as { transformIndexHtml?: unknown }).transformIndexHtml;
  if (typeof hook === "function") return { order: undefined, handler: hook as HtmlHandler };
  if (hook !== null && typeof hook === "object" && typeof (hook as { handler?: unknown }).handler === "function") {
    return { order: (hook as { order?: unknown }).order, handler: (hook as { handler: HtmlHandler }).handler };
  }
  throw new Error("plugin has no transformIndexHtml hook");
}

function flattenPlugins(value: unknown, out: unknown[] = []): unknown[] {
  if (Array.isArray(value)) {
    for (const item of value) flattenPlugins(item, out);
  } else if (value !== null && value !== undefined && value !== false) {
    out.push(value);
  }
  return out;
}

function pluginName(p: unknown): string | undefined {
  if (p !== null && typeof p === "object") {
    const name = (p as { name?: unknown }).name;
    return typeof name === "string" ? name : undefined;
  }
  return undefined;
}

/** Shaped like the four entry documents: one relative module script and a root div. */
function entryHtml(src: string): string {
  return [
    "<!doctype html>",
    '<html lang="en">',
    "  <head>",
    '    <meta charset="UTF-8" />',
    '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
    "    <title>RPHelper</title>",
    "  </head>",
    "  <body>",
    '    <div id="root"></div>',
    `    <script type="module" src="${src}"></script>`,
    "  </body>",
    "</html>",
    "",
  ].join("\n");
}

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// DoD-1 — slash-less entries redirect
// ---------------------------------------------------------------------------

describe("entry routing — slash-less entries redirect (DoD-1)", () => {
  it.each([
    ["/login", "/login/"],
    ["/bootstrap", "/bootstrap/"],
    ["/admin", "/admin/"],
  ])("GET %s gets 302 Location %s, ended, next not called (DoD-1)", (url, location) => {
    expectRedirect(run(makeMw(), "GET", url), location);
  });

  it("GET /login?next=x redirects to /login/ with the query dropped (DoD-1)", () => {
    expectRedirect(run(makeMw(), "GET", "/login?next=x"), "/login/");
  });

  it("HEAD /login gets the same 302 (DoD-1)", () => {
    expectRedirect(run(makeMw(), "HEAD", "/login"), "/login/");
  });
});

// ---------------------------------------------------------------------------
// DoD-2 — entry deep links
// ---------------------------------------------------------------------------

describe("entry routing — entry deep links (DoD-2)", () => {
  it.each([
    ["/admin/users", "/admin/index.html"],
    ["/login/reset?x=1", "/login/index.html"],
    ["/bootstrap/step/2", "/bootstrap/index.html"],
  ])("GET %s routes to %s (DoD-2)", (url, expected) => {
    expectRoutedTo(run(makeMw(), "GET", url), expected);
  });

  it("HEAD /admin/users routes to /admin/index.html as well (DoD-2)", () => {
    expectRoutedTo(run(makeMw(), "HEAD", "/admin/users"), "/admin/index.html");
  });
});

// ---------------------------------------------------------------------------
// DoD-3 — bare entry directories
// ---------------------------------------------------------------------------

describe("entry routing — bare entry directories (DoD-3)", () => {
  it.each([
    ["/login/", "/login/index.html"],
    ["/admin/", "/admin/index.html"],
    ["/bootstrap/", "/bootstrap/index.html"],
  ])("GET %s routes to %s (DoD-3)", (url, expected) => {
    expectRoutedTo(run(makeMw(), "GET", url), expected);
  });
});

// ---------------------------------------------------------------------------
// DoD-4 — app navigations
// ---------------------------------------------------------------------------

describe("entry routing — app navigations (DoD-4)", () => {
  it.each(["/", "/sessions/5", "/characters/7?x=1", "/app/", "/loginx", "/apiary"])(
    "GET %s routes to /app/index.html (DoD-4)",
    (url) => {
      expectRoutedTo(run(makeMw(), "GET", url), "/app/index.html");
    },
  );

  it("HEAD / routes to /app/index.html (DoD-4)", () => {
    expectRoutedTo(run(makeMw(), "HEAD", "/"), "/app/index.html");
  });
});

// ---------------------------------------------------------------------------
// DoD-5 — /api is untouched
// ---------------------------------------------------------------------------

describe("entry routing — /api pass-through (DoD-5)", () => {
  it.each(["/api", "/api/", "/api/x", "/api/health?q=1"])("GET %s is untouched (DoD-5)", (url) => {
    expectUntouched(run(makeMw(), "GET", url), url);
  });

  it.each(["/api", "/api/x"])("GET %s is untouched even when the predicate says file (DoD-5)", (url) => {
    expectUntouched(run(makeMw({ isFile: () => true }), "GET", url), url);
  });
});

// ---------------------------------------------------------------------------
// DoD-6 — Vite internals are untouched
// ---------------------------------------------------------------------------

describe("entry routing — Vite internals pass-through (DoD-6)", () => {
  it.each([
    "/@vite/client",
    "/@fs/abs/path",
    "/__open-in-editor?file=a",
    "/__vite_ping",
    "/node_modules/x",
    "/node_modules/.vite/deps/react",
  ])("GET %s is untouched (DoD-6)", (url) => {
    expectUntouched(run(makeMw(), "GET", url), url);
  });
});

// ---------------------------------------------------------------------------
// DoD-7 — paths with an extension are untouched regardless of the predicate
// ---------------------------------------------------------------------------

describe("entry routing — extension pass-through (DoD-7)", () => {
  const urls = ["/missing.png", "/app/main.tsx", "/sessions/main.tsx", "/app/index.html", "/favicon.ico"];

  it.each(urls)("GET %s is untouched when the predicate says not-a-file (DoD-7)", (url) => {
    expectUntouched(run(makeMw({ isFile: () => false }), "GET", url), url);
  });

  it.each(urls)("GET %s is untouched when the predicate says file (DoD-7)", (url) => {
    expectUntouched(run(makeMw({ isFile: () => true }), "GET", url), url);
  });
});

// ---------------------------------------------------------------------------
// DoD-8 — injected predicate
// ---------------------------------------------------------------------------

describe("entry routing — injected file predicate (DoD-8)", () => {
  it.each(["/LICENSE", "/docs/readme", "/sessions/5"])(
    "GET %s is untouched when the predicate returns true (DoD-8)",
    (url) => {
      expectUntouched(run(makeMw({ isFile: () => true }), "GET", url), url);
    },
  );

  it("an entry deep link for which the predicate returns true is untouched (DoD-8)", () => {
    expectUntouched(run(makeMw({ isFile: () => true }), "GET", "/admin/users"), "/admin/users");
  });

  it.each(["/LICENSE", "/docs/readme"])("GET %s routes to /app/index.html when the predicate returns false (DoD-8)", (url) => {
    expectRoutedTo(run(makeMw({ isFile: () => false }), "GET", url), "/app/index.html");
  });

  it("the predicate receives the absolute path inside root for the pathname (DoD-8)", () => {
    const isFile = vi.fn((_p: string) => true);
    const r = run(createEntryRoutingMiddleware({ root: FAKE_ROOT, isFile }), "GET", "/docs/readme?x=1");
    expectUntouched(r, "/docs/readme?x=1");
    const args = isFile.mock.calls.map((call) => call[0]);
    expect(args).toContain(path.join(FAKE_ROOT, "docs", "readme"));
    for (const a of args) {
      expect(path.isAbsolute(a)).toBe(true);
      expect(isInside(FAKE_ROOT, a)).toBe(true);
    }
  });

  it("the predicate receives the percent-decoded pathname (DoD-8)", () => {
    const isFile = vi.fn((_p: string) => false);
    const r = run(createEntryRoutingMiddleware({ root: FAKE_ROOT, isFile }), "GET", "/caf%C3%A9/my%20notes");
    expectRoutedTo(r, "/app/index.html");
    const args = isFile.mock.calls.map((call) => call[0]);
    expect(args).toContain(path.join(FAKE_ROOT, "café", "my notes"));
  });
});

// ---------------------------------------------------------------------------
// DoD-9 — default predicate against a real temporary root
// ---------------------------------------------------------------------------

describe("entry routing — default predicate on a real root (DoD-9)", () => {
  let root = "";

  beforeAll(() => {
    root = mkdtempSync(path.join(os.tmpdir(), "rphelper-entry-routing-"));
    writeFileSync(path.join(root, "LICENSE"), "license text");
    mkdirSync(path.join(root, "sessions"));
    writeFileSync(path.join(root, "sessions", "README"), "readme text");
    mkdirSync(path.join(root, "login"));
    writeFileSync(path.join(root, "login", "index.html"), "<!doctype html>");
    mkdirSync(path.join(root, "notes"));
  });

  afterAll(() => {
    if (root !== "") rmSync(root, { recursive: true, force: true });
  });

  it("an existing extensionless file is untouched (DoD-9)", () => {
    const mw = createEntryRoutingMiddleware({ root });
    expectUntouched(run(mw, "GET", "/LICENSE"), "/LICENSE");
  });

  it("a nested existing extensionless file is untouched (DoD-9)", () => {
    const mw = createEntryRoutingMiddleware({ root });
    expectUntouched(run(mw, "GET", "/sessions/README"), "/sessions/README");
  });

  it("/login/ (an existing directory) still routes to /login/index.html (DoD-9)", () => {
    const mw = createEntryRoutingMiddleware({ root });
    expectRoutedTo(run(mw, "GET", "/login/"), "/login/index.html");
  });

  it("/login (an existing directory, slash-less) still redirects to /login/ (DoD-9)", () => {
    const mw = createEntryRoutingMiddleware({ root });
    expectRedirect(run(mw, "GET", "/login"), "/login/");
  });

  it("a non-entry directory is not a file and routes to /app/index.html (DoD-9)", () => {
    const mw = createEntryRoutingMiddleware({ root });
    expectRoutedTo(run(mw, "GET", "/notes"), "/app/index.html");
  });

  it("a missing path routes to /app/index.html (DoD-9)", () => {
    const mw = createEntryRoutingMiddleware({ root });
    expectRoutedTo(run(mw, "GET", "/sessions/5"), "/app/index.html");
  });

  it("/ (the root directory itself) routes to /app/index.html (DoD-9)", () => {
    const mw = createEntryRoutingMiddleware({ root });
    expectRoutedTo(run(mw, "GET", "/"), "/app/index.html");
  });
});

// ---------------------------------------------------------------------------
// DoD-10 — path escape
// ---------------------------------------------------------------------------

describe("entry routing — path escape is never an existing file (DoD-10)", () => {
  it.each(["/../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/sessions/../../../outside", "/%2E%2E/%2E%2E/%2E%2E/secret"])(
    "GET %s is not passed through even if the predicate says outside paths exist (DoD-10)",
    (url) => {
      // The predicate answers true ONLY for paths outside root: a pass-through would mean an
      // outside path was consulted and its true result honoured.
      const isFile = vi.fn((p: string) => !isInside(FAKE_ROOT, p));
      const r = run(createEntryRoutingMiddleware({ root: FAKE_ROOT, isFile }), "GET", url);
      expect(r.req.url).not.toBe(url);
      expectRoutedTo(r, "/app/index.html");
    },
  );
});

// ---------------------------------------------------------------------------
// DoD-11 — non-GET/HEAD requests are untouched
// ---------------------------------------------------------------------------

describe("entry routing — non-GET/HEAD untouched (DoD-11)", () => {
  it.each([
    ["POST", "/"],
    ["PUT", "/login"],
    ["DELETE", "/sessions/5"],
    ["POST", "/admin/users"],
  ])("%s %s is untouched (DoD-11)", (method, url) => {
    expectUntouched(run(makeMw(), method, url), url);
  });

  it.each(["/", "/login", "/sessions/5"])("a request with no method for %s is untouched (DoD-11)", (url) => {
    expectUntouched(run(makeMw(), undefined, url), url);
  });
});

// ---------------------------------------------------------------------------
// DoD-12 — the middleware never throws
// ---------------------------------------------------------------------------

describe("entry routing — never throws (DoD-12)", () => {
  it.each(["/%E0%A4%A", "/sessions/%ZZ", "/admin/%E0%A4%A"])(
    "a malformed percent-encoding (%s) leaves req.url unchanged and calls next once (DoD-12)",
    (url) => {
      expectUntouched(run(makeMw(), "GET", url), url);
    },
  );

  it.each<[string, unknown]>([
    ["number", 42],
    ["null", null],
    ["object", { pathname: "/" }],
    ["array", ["/"]],
  ])("a %s url is left as-is and next is called once (DoD-12)", (_label, url) => {
    const mw = makeMw();
    const req = { method: "GET", url } as EntryRoutingRequest;
    const res = fakeRes(200);
    const next = vi.fn();
    expect(() => mw(req, res, next)).not.toThrow();
    expect(req.url).toBe(url);
    expect(next).toHaveBeenCalledTimes(1);
    expect(next.mock.calls[0]).toHaveLength(0);
    expect(res.end).not.toHaveBeenCalled();
    expect(res.setHeader).not.toHaveBeenCalled();
  });

  it("a missing url stays absent and next is called once (DoD-12)", () => {
    const r = run(makeMw(), "GET", undefined);
    expect(r.req.url).toBeUndefined();
    expect(r.next).toHaveBeenCalledTimes(1);
    expect(r.next.mock.calls[0]).toHaveLength(0);
    expect(r.res.end).not.toHaveBeenCalled();
  });

  it("an empty request object does not throw and calls next once (DoD-12)", () => {
    const mw = makeMw();
    const req = {} as EntryRoutingRequest;
    const next = vi.fn();
    expect(() => mw(req, fakeRes(200), next)).not.toThrow();
    expect(req.url).toBeUndefined();
    expect(next).toHaveBeenCalledTimes(1);
  });

  it.each(["/sessions/5", "/admin/users", "/LICENSE"])(
    "a throwing predicate leaves %s unchanged and calls next once (DoD-12)",
    (url) => {
      const mw = createEntryRoutingMiddleware({
        root: FAKE_ROOT,
        isFile: () => {
          throw new Error("predicate boom");
        },
      });
      expectUntouched(run(mw, "GET", url), url);
    },
  );

  it.each<[string, unknown]>([
    ["an empty object", {}],
    ["non-function setHeader/end", { statusCode: 200, setHeader: 5, end: "x" }],
    ["only statusCode", { statusCode: 200 }],
  ])("a response that is %s does not throw on a redirect path; url unchanged, next once (DoD-12)", (_label, res) => {
    const mw = makeMw();
    const req = fakeReq("GET", "/login");
    const next = vi.fn();
    expect(() => mw(req, res as EntryRoutingResponse, next)).not.toThrow();
    expect(req.url).toBe("/login");
    expect(next).toHaveBeenCalledTimes(1);
    expect(next.mock.calls[0]).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// DoD-13 — script-src absolutizer
// ---------------------------------------------------------------------------

describe("absolutizeModuleScriptSrc (DoD-13)", () => {
  it("./main.tsx against /app/index.html becomes /app/main.tsx; the rest is byte-identical (DoD-13)", () => {
    const input = entryHtml("./main.tsx");
    expect(absolutizeModuleScriptSrc(input, "/app/index.html")).toBe(entryHtml("/app/main.tsx"));
  });

  it("./main.tsx against /bootstrap/index.html becomes /bootstrap/main.tsx (DoD-13)", () => {
    expect(absolutizeModuleScriptSrc(entryHtml("./main.tsx"), "/bootstrap/index.html")).toBe(
      entryHtml("/bootstrap/main.tsx"),
    );
  });

  it.each([
    ["main.tsx", "/app/index.html", "/app/main.tsx"],
    ["main.tsx", "/admin/index.html", "/admin/main.tsx"],
    ["../shared/x.ts", "/app/index.html", "/shared/x.ts"],
    ["../shared/x.ts", "/bootstrap/index.html", "/shared/x.ts"],
    ["../x.ts", "/app/index.html", "/x.ts"],
    ["./main.tsx", "/login/index.html", "/login/main.tsx"],
  ])("src %s against %s becomes %s (DoD-13)", (src, doc, expected) => {
    expect(absolutizeModuleScriptSrc(entryHtml(src), doc)).toBe(entryHtml(expected));
  });

  it.each([
    "/app/main.tsx",
    "//cdn.example.com/x.js",
    "http://example.com/x.js",
    "https://example.com/x.js",
    "data:text/javascript,console.log(1)",
  ])("a non-relative src (%s) is unchanged (DoD-13)", (src) => {
    const input = entryHtml(src);
    expect(absolutizeModuleScriptSrc(input, "/app/index.html")).toBe(input);
  });

  it("a non-module script is unchanged while the module script is rewritten (DoD-13)", () => {
    const input = [
      "<body>",
      '<div id="root"></div>',
      '<script src="./legacy.js"></script>',
      '<script type="module" src="./main.tsx"></script>',
      "</body>",
    ].join("\n");
    const expected = [
      "<body>",
      '<div id="root"></div>',
      '<script src="./legacy.js"></script>',
      '<script type="module" src="/app/main.tsx"></script>',
      "</body>",
    ].join("\n");
    expect(absolutizeModuleScriptSrc(input, "/app/index.html")).toBe(expected);
  });

  it("a lone non-module script is unchanged (DoD-13)", () => {
    const input = '<html><body><script src="./legacy.js"></script></body></html>';
    expect(absolutizeModuleScriptSrc(input, "/app/index.html")).toBe(input);
  });

  it("every relative module script is rewritten (DoD-13)", () => {
    const input = '<script type="module" src="./a.ts"></script>\n<script type="module" src="b.ts"></script>';
    const expected = '<script type="module" src="/app/a.ts"></script>\n<script type="module" src="/app/b.ts"></script>';
    expect(absolutizeModuleScriptSrc(input, "/app/index.html")).toBe(expected);
  });

  it("quote style is preserved (DoD-13)", () => {
    const input = "<div id=\"root\"></div><script type=\"module\" src='./main.tsx'></script>";
    const expected = "<div id=\"root\"></div><script type=\"module\" src='/app/main.tsx'></script>";
    expect(absolutizeModuleScriptSrc(input, "/app/index.html")).toBe(expected);
  });

  it("other attributes are left as they are (DoD-13)", () => {
    const input = '<script src="./main.tsx" type="module" crossorigin data-x="1"></script>';
    const expected = '<script src="/app/main.tsx" type="module" crossorigin data-x="1"></script>';
    expect(absolutizeModuleScriptSrc(input, "/app/index.html")).toBe(expected);
  });

  it("an inline module script without src is unchanged (DoD-13)", () => {
    const input = '<script type="module">import "./x.ts";</script>';
    expect(absolutizeModuleScriptSrc(input, "/app/index.html")).toBe(input);
  });

  it.each(["/app/index.html?x=1", "/app/index.html#frag", "/app/index.html?a=1&b=2#f"])(
    "a query or fragment on the document path (%s) is ignored (DoD-13)",
    (doc) => {
      expect(absolutizeModuleScriptSrc(entryHtml("./main.tsx"), doc)).toBe(entryHtml("/app/main.tsx"));
    },
  );

  it.each<[string, unknown]>([
    ["undefined", undefined],
    ["null", null],
    ["a number", 42],
    ["an object", { path: "/app/index.html" }],
  ])("an unusable document path (%s) returns the input unchanged without throwing (DoD-13)", (_label, doc) => {
    const input = entryHtml("./main.tsx");
    let out: unknown = "sentinel-not-called";
    expect(() => {
      out = absolutizeModuleScriptSrc(input, doc as string);
    }).not.toThrow();
    expect(out).toBe(input);
  });
});

// ---------------------------------------------------------------------------
// DoD-14 — plugin factory
// ---------------------------------------------------------------------------

describe("devEntryRoutingPlugin (DoD-14)", () => {
  it("has the frozen name (no `react` in it) and apply: serve (DoD-14)", () => {
    const plugin = devEntryRoutingPlugin();
    expect(ENTRY_ROUTING_PLUGIN_NAME).toBe("rphelper-dev-entry-routing");
    expect(plugin.name).toBe(ENTRY_ROUTING_PLUGIN_NAME);
    expect(plugin.name.toLowerCase()).not.toContain("react");
    expect(plugin.apply).toBe("serve");
  });

  it("transformIndexHtml is ordered pre and absolutizes the module script for ctx.path (DoD-14)", async () => {
    const plugin = devEntryRoutingPlugin();
    const hook = transformHook(plugin);
    expect(hook.order).toBe("pre");
    const input = entryHtml("./main.tsx");
    const out = await Promise.resolve(
      hook.handler.call(plugin, input, { path: "/app/index.html", filename: path.join(FAKE_ROOT, "app", "index.html") }),
    );
    expect(typeof out).toBe("string");
    expect(out as string).toContain('src="/app/main.tsx"');
    expect(out as string).not.toContain('src="./main.tsx"');
  });

  it("configureServer registers exactly one function, returns undefined and writes nothing (DoD-14)", () => {
    const plugin = devEntryRoutingPlugin();
    const hook = configureServerFn(plugin);
    const { server, calls } = fakeServer(path.resolve(os.tmpdir(), "rphelper-entry-routing-missing-root"));
    const writeSpy = vi.spyOn(process.stdout, "write").mockImplementation(() => true);

    let returned: unknown = "sentinel-not-called";
    expect(() => {
      returned = hook.call(plugin, server);
    }).not.toThrow();

    const writes = writeSpy.mock.calls.length;
    writeSpy.mockRestore();

    expect(returned).toBeUndefined();
    expect(writes).toBe(0);
    expect(calls).toHaveLength(1);
    const fns = (calls[0] as unknown[]).filter((a) => typeof a === "function");
    expect(fns).toHaveLength(1);
  });

  it("the registered middleware routes GET / to /app/index.html (DoD-14)", () => {
    const plugin = devEntryRoutingPlugin();
    const hook = configureServerFn(plugin);
    const { server, calls } = fakeServer(path.resolve(os.tmpdir(), "rphelper-entry-routing-missing-root"));
    hook.call(plugin, server);
    expect(calls).toHaveLength(1);
    const registered = (calls[0] as unknown[]).find((a) => typeof a === "function") as
      | EntryRoutingMiddleware
      | undefined;
    expect(typeof registered).toBe("function");

    expectRoutedTo(run(registered as EntryRoutingMiddleware, "GET", "/"), "/app/index.html");
  });
});

// ---------------------------------------------------------------------------
// DoD-15 — request-log interplay
// ---------------------------------------------------------------------------

describe("entry routing — request-log interplay (DoD-15)", () => {
  function chain(url: string, startAt: number, endAt: number): { lines: string[]; req: FakeReq } {
    const lines: string[] = [];
    let now = startAt;
    const logMw = createRequestLogMiddleware({
      sink: (line: string) => {
        lines.push(line);
      },
      now: () => now,
    });
    const routeMw = makeMw();
    const req = fakeReq("GET", url);
    const res = fakeRes(200);
    const finalNext = vi.fn();

    logMw(req, res, () => {
      routeMw(req, res, finalNext);
    });
    expect(finalNext).toHaveBeenCalledTimes(1);

    now = endAt;
    res.statusCode = 200;
    res.emit("finish");
    return { lines, req };
  }

  it("GET / logs `GET / 200 <d>ms`, not the rewritten /app/index.html (DoD-15)", () => {
    const { lines, req } = chain("/", 1000, 1007);
    expect(req.url).toBe("/app/index.html");
    expect(lines).toEqual(["GET / 200 7ms"]);
  });

  it("GET /sessions/5?q=SECRET logs `GET /sessions/5 200 <d>ms` (DoD-15)", () => {
    const { lines, req } = chain("/sessions/5?q=SECRET", 50, 62);
    expect(req.url).toBe("/app/index.html");
    expect(lines).toEqual(["GET /sessions/5 200 12ms"]);
    expect(lines.join("")).not.toContain("SECRET");
    expect(lines.join("")).not.toContain("index.html");
  });
});

// ---------------------------------------------------------------------------
// DoD-16 — wiring and hygiene
// ---------------------------------------------------------------------------

describe("vite.config.ts — entry-routing plugin wiring (DoD-16)", () => {
  it("has exactly one entry-routing plugin, placed after the request-log plugin (DoD-16)", () => {
    const plugins = flattenPlugins((config as { plugins?: unknown }).plugins);
    const names = plugins.map(pluginName);

    const routeIdx = names.reduce<number[]>((acc, n, i) => (n === "rphelper-dev-entry-routing" ? [...acc, i] : acc), []);
    expect(routeIdx).toHaveLength(1);

    const logIdx = names.indexOf("rphelper-dev-request-log");
    expect(logIdx).toBeGreaterThanOrEqual(0);
    expect(routeIdx[0] as number).toBeGreaterThan(logIdx);
  });
});

describe("dev/entryRouting import (DoD-16)", () => {
  it("writes nothing to stdout on a fresh import (DoD-16)", async () => {
    vi.resetModules();
    const writeSpy = vi.spyOn(process.stdout, "write").mockImplementation(() => true);

    const mod = await import("../dev/entryRouting.ts");

    const calls = writeSpy.mock.calls.length;
    writeSpy.mockRestore();

    expect(typeof mod.createEntryRoutingMiddleware).toBe("function");
    expect(typeof mod.absolutizeModuleScriptSrc).toBe("function");
    expect(typeof mod.devEntryRoutingPlugin).toBe("function");
    expect(calls).toBe(0);
  });
});
