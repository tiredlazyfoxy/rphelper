// Fast feature 008 — Vite dev-server request log (DoD-1..DoD-13).
// Expected values come from docs/plans/fast/008.vite-dev-request-log/plan.md and context.md.
// DoD-10 also requires tests/build-config.test.ts and tests/proxy-log.test.ts to pass unedited;
// those files are run as-is by the suite and are not touched here.
import { EventEmitter } from "node:events";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";
import {
  REQUEST_LOG_PLUGIN_NAME,
  createRequestLogMiddleware,
  devRequestLogPlugin,
  type RequestLike,
  type ResponseLike,
} from "../dev/requestLog";
import config from "../vite.config";

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

const FRONTEND_ROOT = path.resolve(__dirname, "..");

function readText(relative: string): string {
  return readFileSync(path.join(FRONTEND_ROOT, relative), "utf8");
}

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

function fakeRes(statusCode = 200, headers: Record<string, string | string[]> = {}): FakeRes {
  return Object.assign(new EventEmitter(), {
    statusCode,
    headers,
    end: vi.fn(),
    write: vi.fn(),
    writeHead: vi.fn(),
    setHeader: vi.fn(),
  });
}

type Harness = {
  mw: (req: RequestLike, res: ResponseLike, next: () => void) => void;
  lines: string[];
  setNow: (ms: number) => void;
};

function makeHarness(startAt = 1000): Harness {
  const lines: string[] = [];
  let now = startAt;
  const mw = createRequestLogMiddleware({
    sink: (line: string) => {
      lines.push(line);
    },
    now: () => now,
  });
  return {
    mw,
    lines,
    setNow: (ms: number) => {
      now = ms;
    },
  };
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

type FakeServer = { middlewares: { use: (...args: unknown[]) => unknown } };

function fakeServer(): { server: FakeServer; calls: unknown[][] } {
  const calls: unknown[][] = [];
  const server: FakeServer = {
    middlewares: {
      use: (...args: unknown[]) => {
        calls.push(args);
        return server.middlewares;
      },
    },
  };
  return { server, calls };
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

function relativeSpecifiers(source: string): string[] {
  const specs: string[] = [];
  const patterns = [
    /\bfrom\s*["'](\.{1,2}\/[^"']*)["']/g,
    /\bimport\s*["'](\.{1,2}\/[^"']*)["']/g,
    /\bimport\s*\(\s*["'](\.{1,2}\/[^"']*)["']\s*\)/g,
  ];
  for (const re of patterns) {
    for (const m of source.matchAll(re)) specs.push(m[1] as string);
  }
  return specs;
}

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// DoD-1 — basic non-/api request through finish
// ---------------------------------------------------------------------------

describe("request-log middleware — basic finish path (DoD-1)", () => {
  it("writes nothing until finish, then exactly `GET /app/ 200 42ms` (DoD-1)", () => {
    const h = makeHarness(1000);
    const req = fakeReq("GET", "/app/?q=SENTINEL#frag");
    const res = fakeRes(200);

    h.mw(req, res, vi.fn());
    expect(h.lines).toEqual([]);
    h.setNow(1042);
    expect(h.lines).toEqual([]);
    res.emit("finish");

    expect(h.lines).toEqual(["GET /app/ 200 42ms"]);
  });

  it("the line has no trailing newline and carries neither sentinel nor fragment (DoD-1)", () => {
    const h = makeHarness(0);
    const req = fakeReq("GET", "/app/?q=SENTINEL#frag");
    const res = fakeRes(200);

    h.mw(req, res, vi.fn());
    h.setNow(5);
    res.emit("finish");

    expect(h.lines).toHaveLength(1);
    const line = h.lines[0] as string;
    expect(line.endsWith("\n")).toBe(false);
    expect(line).not.toContain("SENTINEL");
    expect(line).not.toContain("frag");
    expect(line).not.toContain("?");
    expect(line).not.toContain("#");
  });
});

// ---------------------------------------------------------------------------
// DoD-2 — status read at finish time
// ---------------------------------------------------------------------------

describe("request-log middleware — status at finish time (DoD-2)", () => {
  it("logs the statusCode set after the middleware ran (DoD-2)", () => {
    const h = makeHarness(100);
    const req = fakeReq("GET", "/");
    const res = fakeRes(200);

    h.mw(req, res, vi.fn());
    res.statusCode = 404;
    h.setNow(107);
    res.emit("finish");

    expect(h.lines).toEqual(["GET / 404 7ms"]);
  });
});

// ---------------------------------------------------------------------------
// DoD-3 — /api requests are skipped
// ---------------------------------------------------------------------------

describe("request-log middleware — /api skip rule (DoD-3)", () => {
  it.each(["/api", "/api/sessions?x=1", "/apiary"])("writes no line for %s, but calls next (DoD-3)", (url) => {
    const h = makeHarness(0);
    const req = fakeReq("GET", url);
    const res = fakeRes(200);
    const next = vi.fn();

    h.mw(req, res, next);
    h.setNow(10);
    res.emit("finish");
    res.emit("close");

    expect(h.lines).toEqual([]);
    expect(next).toHaveBeenCalledTimes(1);
  });

  it("does not skip paths that merely contain /api later on (DoD-3)", () => {
    const h = makeHarness(0);
    const req = fakeReq("GET", "/app/api");
    const res = fakeRes(200);

    h.mw(req, res, vi.fn());
    h.setNow(1);
    res.emit("finish");

    expect(h.lines).toEqual(["GET /app/api 200 1ms"]);
  });
});

// ---------------------------------------------------------------------------
// DoD-4 — next() exactly once, synchronously, no argument; response untouched
// ---------------------------------------------------------------------------

describe("request-log middleware — next() contract (DoD-4)", () => {
  it.each(["/app/", "/api/sessions"])("calls next once, synchronously, with no argument for %s (DoD-4)", (url) => {
    const h = makeHarness(0);
    const req = fakeReq("GET", url);
    const res = fakeRes(200);
    const next = vi.fn();

    h.mw(req, res, next);
    // Checked before any response event fires: the call must already have happened.
    expect(next).toHaveBeenCalledTimes(1);
    expect(next).toHaveBeenCalledWith();
    expect(next.mock.calls[0]).toHaveLength(0);

    res.emit("finish");
    res.emit("close");
    expect(next).toHaveBeenCalledTimes(1);
  });

  it.each(["/app/", "/api/sessions"])("never ends or writes to the response itself for %s (DoD-4)", (url) => {
    const h = makeHarness(0);
    const req = fakeReq("GET", url);
    const res = fakeRes(200);

    h.mw(req, res, vi.fn());
    res.emit("finish");
    res.emit("close");

    expect(res.end).not.toHaveBeenCalled();
    expect(res.write).not.toHaveBeenCalled();
    expect(res.writeHead).not.toHaveBeenCalled();
    expect(res.setHeader).not.toHaveBeenCalled();
    expect(res.statusCode).toBe(200);
  });
});

// ---------------------------------------------------------------------------
// DoD-5 — finish/close: at most one line; close-only renders status as -
// ---------------------------------------------------------------------------

describe("request-log middleware — finish/close handling (DoD-5)", () => {
  it("finish followed by close writes exactly one line (DoD-5)", () => {
    const h = makeHarness(0);
    const req = fakeReq("GET", "/app/");
    const res = fakeRes(200);

    h.mw(req, res, vi.fn());
    h.setNow(12);
    res.emit("finish");
    h.setNow(20);
    res.emit("close");

    expect(h.lines).toEqual(["GET /app/ 200 12ms"]);
  });

  it("repeated finish/close events still write only one line (DoD-5)", () => {
    const h = makeHarness(0);
    const req = fakeReq("GET", "/app/");
    const res = fakeRes(200);

    h.mw(req, res, vi.fn());
    h.setNow(3);
    res.emit("finish");
    res.emit("finish");
    res.emit("close");
    res.emit("close");

    expect(h.lines).toHaveLength(1);
  });

  it("close without a prior finish writes one line with status - (DoD-5)", () => {
    const h = makeHarness(50);
    const req = fakeReq("GET", "/@vite/client");
    const res = fakeRes(200);

    h.mw(req, res, vi.fn());
    h.setNow(57);
    res.emit("close");

    expect(h.lines).toEqual(["GET /@vite/client - 7ms"]);
  });

  it("close then finish writes only the close line (DoD-5)", () => {
    const h = makeHarness(0);
    const req = fakeReq("GET", "/app/");
    const res = fakeRes(200);

    h.mw(req, res, vi.fn());
    h.setNow(4);
    res.emit("close");
    h.setNow(9);
    res.emit("finish");

    expect(h.lines).toEqual(["GET /app/ - 4ms"]);
  });

  it("a response that emits neither finish nor close writes nothing (DoD-5)", () => {
    const h = makeHarness(0);
    const req = fakeReq("GET", "/app/");
    const res = fakeRes(200);

    h.mw(req, res, vi.fn());
    h.setNow(1000);

    expect(h.lines).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// DoD-6 — interleaved requests
// ---------------------------------------------------------------------------

describe("request-log middleware — interleaved requests (DoD-6)", () => {
  it("each request gets its own path, status and duration (DoD-6)", () => {
    const h = makeHarness(1000);
    const reqA = fakeReq("GET", "/app/?a=1");
    const resA = fakeRes(200);
    const reqB = fakeReq("POST", "/src/main.tsx?t=2");
    const resB = fakeRes(200);

    h.mw(reqA, resA, vi.fn()); // A starts at 1000
    h.setNow(1010);
    h.mw(reqB, resB, vi.fn()); // B starts at 1010
    resB.statusCode = 304;
    resA.statusCode = 404;
    h.setNow(1030);
    resB.emit("finish"); // B: 20ms, 304
    h.setNow(1100);
    resA.emit("finish"); // A: 100ms, 404

    expect(h.lines).toEqual(["POST /src/main.tsx 304 20ms", "GET /app/ 404 100ms"]);
  });

  it("does not cross start times between requests sharing the same URL (DoD-6)", () => {
    const h = makeHarness(0);
    const req1 = fakeReq("GET", "/app/");
    const res1 = fakeRes(200);
    const req2 = fakeReq("GET", "/app/");
    const res2 = fakeRes(200);

    h.mw(req1, res1, vi.fn());
    h.setNow(50);
    h.mw(req2, res2, vi.fn());
    h.setNow(60);
    res1.emit("finish");
    h.setNow(65);
    res2.emit("close");

    expect(h.lines).toEqual(["GET /app/ 200 60ms", "GET /app/ - 15ms"]);
  });
});

// ---------------------------------------------------------------------------
// DoD-7 — missing url/method logged with -, malformed inputs never throw
// ---------------------------------------------------------------------------

describe("request-log middleware — missing and malformed fields (DoD-7)", () => {
  it("a request with no url is logged with - as the path (DoD-7)", () => {
    const h = makeHarness(0);
    const req = fakeReq("GET", undefined);
    const res = fakeRes(200);
    const next = vi.fn();

    expect(() => h.mw(req, res, next)).not.toThrow();
    h.setNow(3);
    expect(() => res.emit("finish")).not.toThrow();

    expect(next).toHaveBeenCalledTimes(1);
    expect(h.lines).toEqual(["GET - 200 3ms"]);
  });

  it("a request with no method is logged with - as the method (DoD-7)", () => {
    const h = makeHarness(0);
    const req = fakeReq(undefined, "/app/");
    const res = fakeRes(200);

    expect(() => h.mw(req, res, vi.fn())).not.toThrow();
    h.setNow(3);
    expect(() => res.emit("finish")).not.toThrow();

    expect(h.lines).toEqual(["- /app/ 200 3ms"]);
  });

  it("a request with neither url nor method is logged as `- - <status>` (DoD-7)", () => {
    const h = makeHarness(0);
    const req = fakeReq(undefined, undefined);
    const res = fakeRes(500);

    expect(() => h.mw(req, res, vi.fn())).not.toThrow();
    h.setNow(2);
    expect(() => res.emit("finish")).not.toThrow();

    expect(h.lines).toEqual(["- - 500 2ms"]);
  });

  it("does not throw for malformed request/response objects (DoD-7)", () => {
    const cases: Array<[string, unknown, unknown]> = [
      ["empty req and empty res", {}, {}],
      ["empty req, emitter res", {}, new EventEmitter()],
      ["numeric url and object method", { url: 42, method: {} }, fakeRes(200)],
      ["symbol method", { url: "/app/", method: Symbol("m") }, fakeRes(200)],
      ["null url and method", { url: null, method: null }, fakeRes(200)],
      ["string statusCode", fakeReq("GET", "/app/"), Object.assign(new EventEmitter(), { statusCode: "abc" })],
      ["object statusCode", fakeReq("GET", "/app/"), Object.assign(new EventEmitter(), { statusCode: {} })],
      ["no statusCode", fakeReq("GET", "/app/"), new EventEmitter()],
      ["res.on is not a function", fakeReq("GET", "/app/"), { on: 5, statusCode: 200 }],
      ["res without on", fakeReq("GET", "/app/"), { statusCode: 200 }],
    ];

    for (const [label, req, res] of cases) {
      const h = makeHarness(0);
      expect(() => h.mw(req as RequestLike, res as ResponseLike, () => undefined), label).not.toThrow();
      if (res instanceof EventEmitter) {
        expect(() => res.emit("finish", "unexpected", 1), `${label} finish`).not.toThrow();
        expect(() => res.emit("close", null), `${label} close`).not.toThrow();
      }
    }
  });
});

// ---------------------------------------------------------------------------
// DoD-8 — redaction sentinel sweep
// ---------------------------------------------------------------------------

describe("request-log middleware — redaction (DoD-8)", () => {
  const SENTINELS = [
    "QUERYSENTINEL",
    "FRAGSENTINEL",
    "REQHEADERSENTINEL",
    "COOKIESENTINEL",
    "RESHEADERSENTINEL",
    "SETCOOKIESENTINEL",
    "REQBODYSENTINEL",
    "RESBODYSENTINEL",
  ];

  function sensitiveReq(): FakeReq {
    return fakeReq("POST", "/src/search?q=QUERYSENTINEL&x=1#FRAGSENTINEL", {
      "x-custom": "REQHEADERSENTINEL",
      authorization: "Bearer REQHEADERSENTINEL",
      cookie: "session=COOKIESENTINEL",
    });
  }

  function sensitiveRes(): FakeRes {
    return fakeRes(200, {
      "x-res": "RESHEADERSENTINEL",
      "set-cookie": ["s=SETCOOKIESENTINEL"],
    });
  }

  function assertClean(lines: string[]): void {
    expect(lines.length).toBeGreaterThan(0);
    for (const line of lines) {
      for (const s of SENTINELS) {
        expect(line, `sink output "${line}" leaks ${s}`).not.toContain(s);
      }
      expect(line).not.toContain("?");
      expect(line).not.toContain("#");
    }
  }

  it("a finish line carries no query, fragment, header, cookie or body (DoD-8)", () => {
    const h = makeHarness(0);
    const req = sensitiveReq();
    const res = sensitiveRes();

    h.mw(req, res, vi.fn());
    req.emit("data", "REQBODYSENTINEL");
    req.emit("end");
    res.write("RESBODYSENTINEL");
    res.end("RESBODYSENTINEL");
    h.setNow(10);
    res.emit("finish");

    assertClean(h.lines);
    expect(h.lines).toEqual(["POST /src/search 200 10ms"]);
  });

  it("a close-only line carries no query, fragment, header, cookie or body (DoD-8)", () => {
    const h = makeHarness(0);
    const req = sensitiveReq();
    const res = sensitiveRes();

    h.mw(req, res, vi.fn());
    req.emit("data", "REQBODYSENTINEL");
    res.write("RESBODYSENTINEL");
    h.setNow(6);
    res.emit("close");

    assertClean(h.lines);
    expect(h.lines).toEqual(["POST /src/search - 6ms"]);
  });
});

// ---------------------------------------------------------------------------
// DoD-9 — plugin factory
// ---------------------------------------------------------------------------

describe("devRequestLogPlugin (DoD-9)", () => {
  it("has the frozen name and apply: serve (DoD-9)", () => {
    const plugin = devRequestLogPlugin();
    expect(REQUEST_LOG_PLUGIN_NAME).toBe("rphelper-dev-request-log");
    expect(plugin.name).toBe("rphelper-dev-request-log");
    expect(plugin.apply).toBe("serve");
  });

  it("configureServer registers exactly one function, returns undefined and writes nothing (DoD-9)", () => {
    const plugin = devRequestLogPlugin();
    const hook = configureServerFn(plugin);
    const { server, calls } = fakeServer();
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

  it("the registered middleware writes one newline-terminated line via process.stdout.write (DoD-9)", () => {
    const plugin = devRequestLogPlugin();
    const hook = configureServerFn(plugin);
    const { server, calls } = fakeServer();
    hook.call(plugin, server);
    expect(calls).toHaveLength(1);
    const registered = (calls[0] as unknown[]).find((a) => typeof a === "function") as
      | ((req: unknown, res: unknown, next: () => void) => void)
      | undefined;
    expect(typeof registered).toBe("function");

    const writeSpy = vi.spyOn(process.stdout, "write").mockImplementation(() => true);
    const req = fakeReq("GET", "/app/?q=PLUGINSENTINEL");
    const res = fakeRes(200);
    const next = vi.fn();
    (registered as (req: unknown, res: unknown, next: () => void) => void)(req, res, next);
    res.emit("finish");

    const written = writeSpy.mock.calls.map((call) => String(call[0]));
    writeSpy.mockRestore();

    expect(next).toHaveBeenCalledTimes(1);
    const ours = written.filter((chunk) => chunk.startsWith("GET /app/"));
    expect(ours).toHaveLength(1);
    expect(ours[0]).toMatch(/^GET \/app\/ 200 \d+ms\n$/);
    expect(written.join("")).not.toContain("PLUGINSENTINEL");
  });

  it("passes injected options through to the registered middleware (DoD-9)", () => {
    const lines: string[] = [];
    let now = 10;
    const plugin = devRequestLogPlugin({
      sink: (line: string) => {
        lines.push(line);
      },
      now: () => now,
    });
    const hook = configureServerFn(plugin);
    const { server, calls } = fakeServer();
    hook.call(plugin, server);
    const registered = (calls[0] as unknown[]).find((a) => typeof a === "function") as (
      req: unknown,
      res: unknown,
      next: () => void,
    ) => void;

    const req = fakeReq("GET", "/app/");
    const res = fakeRes(200);
    registered(req, res, vi.fn());
    now = 25;
    res.emit("finish");

    expect(lines).toEqual(["GET /app/ 200 15ms"]);
  });
});

// ---------------------------------------------------------------------------
// DoD-10 — vite.config wiring
// ---------------------------------------------------------------------------

describe("vite.config.ts — request-log plugin wiring (DoD-10)", () => {
  it("has exactly one request-log plugin, placed after the React plugin(s) (DoD-10)", () => {
    const plugins = flattenPlugins((config as { plugins?: unknown }).plugins);
    const names = plugins.map(pluginName);

    const logIdx = names.reduce<number[]>((acc, n, i) => (n === "rphelper-dev-request-log" ? [...acc, i] : acc), []);
    expect(logIdx).toHaveLength(1);

    const reactIdx = names.reduce<number[]>(
      (acc, n, i) => (typeof n === "string" && n.toLowerCase().includes("react") ? [...acc, i] : acc),
      [],
    );
    expect(reactIdx.length).toBeGreaterThan(0);
    expect(logIdx[0] as number).toBeGreaterThan(Math.max(...reactIdx));
  });
});

// ---------------------------------------------------------------------------
// DoD-11 — source-text checks
// ---------------------------------------------------------------------------

describe("source text — no __dirname, .ts import specifiers (DoD-11)", () => {
  it("vite.config.ts does not mention __dirname (DoD-11)", () => {
    expect(readText("vite.config.ts")).not.toMatch(/\b__dirname\b/);
  });

  it("vite.config.ts uses import.meta.dirname (DoD-11)", () => {
    expect(readText("vite.config.ts")).toContain("import.meta.dirname");
  });

  it("every relative import specifier in vite.config.ts ends in .ts (DoD-11)", () => {
    const specs = relativeSpecifiers(readText("vite.config.ts"));
    expect(specs.length).toBeGreaterThan(0);
    for (const s of specs) {
      expect(s.endsWith(".ts"), `vite.config.ts imports "${s}"`).toBe(true);
    }
  });

  it("every relative import specifier in frontend/dev/*.ts ends in .ts (DoD-11)", () => {
    const devFiles = readdirSync(path.join(FRONTEND_ROOT, "dev")).filter((f) => f.endsWith(".ts"));
    expect(devFiles).toEqual(expect.arrayContaining(["proxyLog.ts", "requestLog.ts"]));

    let total = 0;
    for (const file of devFiles) {
      const specs = relativeSpecifiers(readText(path.join("dev", file)));
      total += specs.length;
      for (const s of specs) {
        expect(s.endsWith(".ts"), `dev/${file} imports "${s}"`).toBe(true);
      }
    }
    // requestLog.ts reuses proxyLog.ts, so at least one relative specifier exists.
    expect(total).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// DoD-12 — tsconfig flags
// ---------------------------------------------------------------------------

describe("tsconfigs — allowImportingTsExtensions (DoD-12)", () => {
  it.each(["tsconfig.json", "tsconfig.node.json"])(
    "%s has allowImportingTsExtensions true and noEmit true (DoD-12)",
    (file) => {
      const json = JSON.parse(readText(file)) as { compilerOptions?: Record<string, unknown> };
      expect(json.compilerOptions?.allowImportingTsExtensions).toBe(true);
      expect(json.compilerOptions?.noEmit).toBe(true);
    },
  );
});

// ---------------------------------------------------------------------------
// DoD-13 — importing the module has no side effects
// ---------------------------------------------------------------------------

describe("dev/requestLog import (DoD-13)", () => {
  it("writes nothing to stdout on a fresh import (DoD-13)", async () => {
    vi.resetModules();
    const writeSpy = vi.spyOn(process.stdout, "write").mockImplementation(() => true);

    const mod = await import("../dev/requestLog");

    const calls = writeSpy.mock.calls.length;
    writeSpy.mockRestore();

    expect(typeof mod.createRequestLogMiddleware).toBe("function");
    expect(typeof mod.devRequestLogPlugin).toBe("function");
    expect(calls).toBe(0);
  });
});
