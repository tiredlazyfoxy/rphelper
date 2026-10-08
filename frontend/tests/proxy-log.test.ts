// Fast feature 007 — Vite dev-proxy request log (DoD-1..DoD-10).
// Expected values come from docs/plans/fast/007.vite-proxy-request-log/plan.md and context.md.
import { EventEmitter } from "node:events";
import { afterEach, describe, expect, it, vi } from "vitest";
import { attachProxyLogging, formatErrorLine, formatSuccessLine, redactPath } from "../dev/proxyLog";
import config from "../vite.config";

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

type FakeReq = { method?: string; url?: string; headers: Record<string, string> };

function fakeReq(method: string | undefined, url: string | undefined, headers: Record<string, string> = {}): FakeReq {
  return { method, url, headers };
}

function fakeProxyRes(statusCode: number, headers: Record<string, string | string[]> = {}): {
  statusCode: number;
  headers: Record<string, string | string[]>;
} {
  return { statusCode, headers };
}

type Harness = {
  proxy: EventEmitter;
  lines: string[];
  setNow: (ms: number) => void;
};

function makeHarness(startAt = 1000): Harness {
  const proxy = new EventEmitter();
  const lines: string[] = [];
  let now = startAt;
  attachProxyLogging(proxy, {
    sink: (line: string) => {
      lines.push(line);
    },
    now: () => now,
  });
  return {
    proxy,
    lines,
    setNow: (ms: number) => {
      now = ms;
    },
  };
}

const TARGET = "http://localhost:8184";

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// DoD-1 — path redaction
// ---------------------------------------------------------------------------

describe("redactPath (DoD-1)", () => {
  it("drops everything from the first ? (DoD-1)", () => {
    expect(redactPath("/api/search?q=hello world&x=1")).toBe("/api/search");
  });

  it("cuts at the first ? even when the query contains a second ? (DoD-1)", () => {
    expect(redactPath("/api/search?q=what?&x=why?")).toBe("/api/search");
  });

  it("drops a # fragment (DoD-1)", () => {
    expect(redactPath("/api/sessions#frag")).toBe("/api/sessions");
  });

  it("drops both a query and a fragment, in either order (DoD-1)", () => {
    expect(redactPath("/api/sessions?x=1#frag")).toBe("/api/sessions");
    expect(redactPath("/api/sessions#frag?x=1")).toBe("/api/sessions");
  });

  it("returns a URL without ? or # unchanged, without decoding (DoD-1)", () => {
    expect(redactPath("/api/sessions")).toBe("/api/sessions");
    expect(redactPath("/api/characters/42/memos")).toBe("/api/characters/42/memos");
    expect(redactPath("/api/a%20b/c%2Fd")).toBe("/api/a%20b/c%2Fd");
  });

  it("yields - for a missing or empty URL (DoD-1)", () => {
    expect(redactPath(undefined)).toBe("-");
    expect(redactPath("")).toBe("-");
  });
});

// ---------------------------------------------------------------------------
// DoD-2 — success-line formatter
// ---------------------------------------------------------------------------

describe("formatSuccessLine (DoD-2)", () => {
  it("produces exactly `GET /api/sessions 200 12ms` (DoD-2)", () => {
    expect(formatSuccessLine("GET", "/api/sessions?limit=5", 200, 12)).toBe("GET /api/sessions 200 12ms");
  });

  it("rounds a fractional duration to an integer (DoD-2)", () => {
    expect(formatSuccessLine("GET", "/api/sessions", 200, 12.4)).toBe("GET /api/sessions 200 12ms");
    expect(formatSuccessLine("GET", "/api/sessions", 200, 12.6)).toBe("GET /api/sessions 200 13ms");
  });

  it("renders a missing method as - (DoD-2)", () => {
    expect(formatSuccessLine(undefined, "/api/sessions", 200, 5)).toBe("- /api/sessions 200 5ms");
  });

  it("renders a missing status as - (DoD-2)", () => {
    expect(formatSuccessLine("POST", "/api/sessions", undefined, 5)).toBe("POST /api/sessions - 5ms");
  });

  it("renders a missing URL as - in the path position (DoD-2, DoD-1)", () => {
    expect(formatSuccessLine("GET", undefined, 404, 0)).toBe("GET - 404 0ms");
  });
});

// ---------------------------------------------------------------------------
// DoD-3 — error-line formatter
// ---------------------------------------------------------------------------

describe("formatErrorLine (DoD-3)", () => {
  it("produces exactly `GET /api/sessions proxy error ECONNREFUSED` (DoD-3)", () => {
    const err = Object.assign(new Error("connect ECONNREFUSED"), { code: "ECONNREFUSED" });
    expect(formatErrorLine("GET", "/api/sessions?x=secret", err)).toBe("GET /api/sessions proxy error ECONNREFUSED");
  });

  it("accepts a plain object with a string code (DoD-3)", () => {
    expect(formatErrorLine("GET", "/api/sessions", { code: "ECONNRESET" })).toBe(
      "GET /api/sessions proxy error ECONNRESET",
    );
  });

  it("uses `unknown` for a plain Error without a code (DoD-3)", () => {
    expect(formatErrorLine("GET", "/api/sessions", new Error("boom"))).toBe("GET /api/sessions proxy error unknown");
  });

  it.each<[string, unknown]>([
    ["a string", "ECONNREFUSED"],
    ["null", null],
    ["undefined", undefined],
    ["a number", 42],
    ["an empty-string code", { code: "" }],
    ["a numeric code", { code: 111 }],
  ])("uses `unknown` when the error is %s (DoD-3)", (_label, err) => {
    expect(formatErrorLine("GET", "/api/sessions", err)).toBe("GET /api/sessions proxy error unknown");
  });

  it("never includes the error message, even when it embeds the URL and query (DoD-3)", () => {
    const message = "connect ECONNREFUSED http://localhost:8184/api/sessions?x=MSGSENTINEL";
    const withCode = Object.assign(new Error(message), { code: "ECONNREFUSED" });
    const withoutCode = new Error(message);

    const a = formatErrorLine("GET", "/api/sessions?x=secret", withCode);
    const b = formatErrorLine("GET", "/api/sessions?x=secret", withoutCode);

    expect(a).toBe("GET /api/sessions proxy error ECONNREFUSED");
    expect(b).toBe("GET /api/sessions proxy error unknown");
    for (const line of [a, b]) {
      expect(line).not.toContain("MSGSENTINEL");
      expect(line).not.toContain("secret");
      expect(line).not.toContain("8184");
    }
  });

  it("renders a missing method and URL as - (DoD-3)", () => {
    expect(formatErrorLine(undefined, undefined, { code: "ECONNREFUSED" })).toBe("- - proxy error ECONNREFUSED");
  });
});

// ---------------------------------------------------------------------------
// DoD-4 — start -> proxyRes on a plain EventEmitter
// ---------------------------------------------------------------------------

describe("attachProxyLogging — basic success path (DoD-4)", () => {
  it("writes exactly one line for start then proxyRes (DoD-4)", () => {
    const h = makeHarness(1000);
    const req = fakeReq("GET", "/api/sessions?limit=5");
    const res = {};

    h.proxy.emit("start", req, res, TARGET);
    h.setNow(1025);
    h.proxy.emit("proxyRes", fakeProxyRes(200), req, res);

    expect(h.lines).toHaveLength(1);
  });

  it("the line carries method, redacted path, status and clock difference (DoD-4)", () => {
    const h = makeHarness(1000);
    const req = fakeReq("POST", "/api/search?q=hello");
    const res = {};

    h.proxy.emit("start", req, res, TARGET);
    h.setNow(1037);
    h.proxy.emit("proxyRes", fakeProxyRes(201), req, res);

    expect(h.lines).toEqual(["POST /api/search 201 37ms"]);
  });

  it("the sink receives the line without a trailing newline (DoD-4)", () => {
    const h = makeHarness(0);
    const req = fakeReq("GET", "/api/sessions");
    const res = {};

    h.proxy.emit("start", req, res, TARGET);
    h.setNow(3);
    h.proxy.emit("proxyRes", fakeProxyRes(200), req, res);

    expect(h.lines).toHaveLength(1);
    expect(h.lines[0]).toBe("GET /api/sessions 200 3ms");
    expect((h.lines[0] as string).endsWith("\n")).toBe(false);
  });

  it("attaching alone writes nothing (DoD-4)", () => {
    const h = makeHarness(0);
    expect(h.lines).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// DoD-5 — start-time fallback
// ---------------------------------------------------------------------------

describe("attachProxyLogging — start-time fallback (DoD-5)", () => {
  it("measures from proxyReq when no start was seen (DoD-5)", () => {
    const h = makeHarness(500);
    const req = fakeReq("GET", "/api/sessions");
    const res = {};

    h.proxy.emit("proxyReq", {}, req, res, { target: TARGET }, undefined);
    h.setNow(540);
    h.proxy.emit("proxyRes", fakeProxyRes(200), req, res);

    expect(h.lines).toEqual(["GET /api/sessions 200 40ms"]);
  });

  it("keeps the start time when both start and proxyReq are seen (DoD-5)", () => {
    const h = makeHarness(100);
    const req = fakeReq("GET", "/api/sessions");
    const res = {};

    h.proxy.emit("start", req, res, TARGET);
    h.setNow(110);
    h.proxy.emit("proxyReq", {}, req, res, { target: TARGET }, undefined);
    h.setNow(150);
    h.proxy.emit("proxyRes", fakeProxyRes(200), req, res);

    expect(h.lines).toEqual(["GET /api/sessions 200 50ms"]);
  });

  it("emits with 0ms when neither start nor proxyReq was seen (DoD-5)", () => {
    const h = makeHarness(9999);
    const req = fakeReq("DELETE", "/api/sessions/7");
    h.proxy.emit("proxyRes", fakeProxyRes(204), req, {});

    expect(h.lines).toEqual(["DELETE /api/sessions/7 204 0ms"]);
  });
});

// ---------------------------------------------------------------------------
// DoD-6 — interleaved requests
// ---------------------------------------------------------------------------

describe("attachProxyLogging — interleaved requests (DoD-6)", () => {
  it("gives each overlapping request its own duration and path (DoD-6)", () => {
    const h = makeHarness(1000);
    const reqA = fakeReq("GET", "/api/sessions?limit=5");
    const reqB = fakeReq("POST", "/api/search?q=private");
    const resA = {};
    const resB = {};

    h.proxy.emit("start", reqA, resA, TARGET); // A starts at 1000
    h.setNow(1010);
    h.proxy.emit("start", reqB, resB, TARGET); // B starts at 1010
    h.setNow(1030);
    h.proxy.emit("proxyRes", fakeProxyRes(200), reqB, resB); // B: 20ms
    h.setNow(1100);
    h.proxy.emit("proxyRes", fakeProxyRes(404), reqA, resA); // A: 100ms

    expect(h.lines).toEqual(["POST /api/search 200 20ms", "GET /api/sessions 404 100ms"]);
  });

  it("does not cross start times between requests sharing the same URL (DoD-6)", () => {
    const h = makeHarness(0);
    const req1 = fakeReq("GET", "/api/sessions");
    const req2 = fakeReq("GET", "/api/sessions");

    h.proxy.emit("start", req1, {}, TARGET);
    h.setNow(50);
    h.proxy.emit("start", req2, {}, TARGET);
    h.setNow(60);
    h.proxy.emit("proxyRes", fakeProxyRes(200), req1, {});
    h.setNow(65);
    h.proxy.emit("proxyRes", fakeProxyRes(200), req2, {});

    expect(h.lines).toEqual(["GET /api/sessions 200 60ms", "GET /api/sessions 200 15ms"]);
  });
});

// ---------------------------------------------------------------------------
// DoD-7 — error events, at most one line per request, no throws
// ---------------------------------------------------------------------------

describe("attachProxyLogging — errors and once-per-request (DoD-7)", () => {
  it("writes exactly one error line for an error event (DoD-7)", () => {
    const h = makeHarness(0);
    const req = fakeReq("GET", "/api/sessions?x=secret");
    const res = {};
    const err = Object.assign(new Error("connect ECONNREFUSED 127.0.0.1:8184"), { code: "ECONNREFUSED" });

    h.proxy.emit("start", req, res, TARGET);
    h.setNow(5);
    h.proxy.emit("error", err, req, res, TARGET);

    expect(h.lines).toEqual(["GET /api/sessions proxy error ECONNREFUSED"]);
  });

  it("writes one error line even without a preceding start (DoD-7)", () => {
    const h = makeHarness(0);
    const req = fakeReq("GET", "/api/sessions");
    h.proxy.emit("error", new Error("boom"), req, {}, TARGET);

    expect(h.lines).toEqual(["GET /api/sessions proxy error unknown"]);
  });

  it("proxyRes then error for the same request writes only the first line (DoD-7)", () => {
    const h = makeHarness(0);
    const req = fakeReq("GET", "/api/sessions");
    const res = {};

    h.proxy.emit("start", req, res, TARGET);
    h.setNow(8);
    h.proxy.emit("proxyRes", fakeProxyRes(200), req, res);
    h.proxy.emit("error", Object.assign(new Error("reset"), { code: "ECONNRESET" }), req, res, TARGET);

    expect(h.lines).toEqual(["GET /api/sessions 200 8ms"]);
  });

  it("error then proxyRes for the same request writes only the first line (DoD-7)", () => {
    const h = makeHarness(0);
    const req = fakeReq("GET", "/api/sessions");
    const res = {};

    h.proxy.emit("start", req, res, TARGET);
    h.proxy.emit("error", Object.assign(new Error("refused"), { code: "ECONNREFUSED" }), req, res, TARGET);
    h.setNow(8);
    h.proxy.emit("proxyRes", fakeProxyRes(200), req, res);

    expect(h.lines).toEqual(["GET /api/sessions proxy error ECONNREFUSED"]);
  });

  it("a repeated proxyRes for the same request writes only one line (DoD-7)", () => {
    const h = makeHarness(0);
    const req = fakeReq("GET", "/api/sessions");
    h.proxy.emit("start", req, {}, TARGET);
    h.proxy.emit("proxyRes", fakeProxyRes(200), req, {});
    h.proxy.emit("proxyRes", fakeProxyRes(200), req, {});

    expect(h.lines).toHaveLength(1);
  });

  it("does not throw for listener calls with missing or malformed arguments (DoD-7)", () => {
    const h = makeHarness(0);
    const malformed: unknown[][] = [
      [],
      [undefined],
      [null],
      [null, null, null],
      ["not-a-request", 42, true],
      [{}, {}, {}],
      [{ statusCode: "200" }, { method: 5, url: 7 }, {}],
      [undefined, { method: "GET" }, undefined],
      [Symbol("x"), 0n, () => undefined],
    ];

    for (const event of ["start", "proxyReq", "proxyRes", "error"]) {
      for (const args of malformed) {
        expect(() => h.proxy.emit(event, ...args), `${event}(${args.length} args)`).not.toThrow();
      }
    }
  });
});

// ---------------------------------------------------------------------------
// DoD-8 — nothing sensitive reaches the sink
// ---------------------------------------------------------------------------

describe("attachProxyLogging — redaction (DoD-8)", () => {
  const SENTINELS = [
    "QUERYSENTINEL",
    "FRAGSENTINEL",
    "HEADERSENTINEL",
    "COOKIESENTINEL",
    "RESHEADERSENTINEL",
    "SETCOOKIESENTINEL",
    "TARGETSENTINEL",
    "BODYSENTINEL",
    "ERRMSGSENTINEL",
  ];

  function sensitiveReq(): FakeReq & { body: string } {
    return {
      method: "POST",
      url: "/api/search?q=QUERYSENTINEL&x=1#FRAGSENTINEL",
      headers: {
        "x-custom": "HEADERSENTINEL",
        authorization: "Bearer HEADERSENTINEL",
        cookie: "session=COOKIESENTINEL",
      },
      body: "BODYSENTINEL",
    };
  }

  const target = "http://TARGETSENTINEL.invalid:8184/TARGETSENTINEL";

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

  it("a success line carries no query, fragment, header, cookie, body or target (DoD-8)", () => {
    const h = makeHarness(0);
    const req = sensitiveReq();
    const res = { body: "BODYSENTINEL" };

    h.proxy.emit("start", req, res, target);
    h.proxy.emit(
      "proxyReq",
      { headers: { cookie: "COOKIESENTINEL" }, path: "/api/search?q=QUERYSENTINEL" },
      req,
      res,
      { target },
      undefined,
    );
    h.setNow(10);
    h.proxy.emit(
      "proxyRes",
      { statusCode: 200, headers: { "x-res": "RESHEADERSENTINEL", "set-cookie": ["s=SETCOOKIESENTINEL"] }, body: "BODYSENTINEL" },
      req,
      res,
    );

    assertClean(h.lines);
    expect(h.lines).toEqual(["POST /api/search 200 10ms"]);
  });

  it("an error line carries no query, fragment, header, cookie, message or target (DoD-8)", () => {
    const h = makeHarness(0);
    const req = sensitiveReq();
    const res = {};
    const err = Object.assign(new Error(`connect ECONNREFUSED ${target}?q=QUERYSENTINEL ERRMSGSENTINEL`), {
      code: "ECONNREFUSED",
      address: "TARGETSENTINEL",
    });

    h.proxy.emit("start", req, res, target);
    h.proxy.emit("error", err, req, res, target);

    assertClean(h.lines);
    expect(h.lines).toEqual(["POST /api/search proxy error ECONNREFUSED"]);
  });
});

// ---------------------------------------------------------------------------
// DoD-9 — vite.config wiring and default sink
// ---------------------------------------------------------------------------

describe("vite.config.ts — /api proxy wiring (DoD-9)", () => {
  const proxyRecord = (): Record<string, unknown> => (config.server?.proxy ?? {}) as Record<string, unknown>;

  it("server.proxy has exactly one key, /api (DoD-9)", () => {
    expect(Object.keys(proxyRecord())).toEqual(["/api"]);
  });

  it("the /api rule is an object with target http://localhost:8184 and a configure function (DoD-9)", () => {
    const rule = proxyRecord()["/api"];
    expect(rule).not.toBeNull();
    expect(typeof rule).toBe("object");
    const obj = rule as { target?: unknown; configure?: unknown };
    expect(obj.target).toBe("http://localhost:8184");
    expect(typeof obj.configure).toBe("function");
  });

  it("configure + start -> proxyRes writes one newline-terminated line via process.stdout.write (DoD-9)", () => {
    const rule = proxyRecord()["/api"] as { configure?: unknown };
    expect(typeof rule.configure).toBe("function");
    const configure = rule.configure as (proxy: EventEmitter, options: unknown) => void;

    const proxy = new EventEmitter();
    const writeSpy = vi.spyOn(process.stdout, "write").mockImplementation(() => true);

    configure(proxy, rule);
    const req = fakeReq("GET", "/api/sessions?limit=5");
    const res = {};
    proxy.emit("start", req, res, "http://localhost:8184");
    proxy.emit("proxyRes", fakeProxyRes(200), req, res);

    const written = writeSpy.mock.calls.map((call) => String(call[0]));
    writeSpy.mockRestore();

    const ours = written.filter((chunk) => chunk.startsWith("GET /api/sessions"));
    expect(ours).toHaveLength(1);
    expect(ours[0]).toMatch(/^GET \/api\/sessions 200 \d+ms\n$/);
  });
});

// ---------------------------------------------------------------------------
// DoD-10 — importing the module has no side effects
// ---------------------------------------------------------------------------

describe("dev/proxyLog import (DoD-10)", () => {
  it("writes nothing to stdout on import (DoD-10)", async () => {
    vi.resetModules();
    const writeSpy = vi.spyOn(process.stdout, "write").mockImplementation(() => true);

    const mod = await import("../dev/proxyLog");

    const calls = writeSpy.mock.calls.length;
    writeSpy.mockRestore();

    expect(typeof mod.attachProxyLogging).toBe("function");
    expect(calls).toBe(0);
  });
});
