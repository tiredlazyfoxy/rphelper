// Feature 002, step 006 — the four entry documents and their routers (DoD-1..DoD-8).
// DoD-13..DoD-16 are [manual/live] and have no test here.
//
// Entries are evaluated per the frozen recipe: vi.resetModules, a fresh <div id="root">,
// history.pushState to the location under test, then `await act(async () => import(...))`.
// BrowserRouter reads the real jsdom location — no MemoryRouter substitute.
//
// Feature 005, step 004 DoD-11 repairs the admin clauses only: `mountEntry("admin", …)` stubs
// GET /api/me with an administrator identity and waits for the gated render. The bootstrap,
// login and app clauses are unchanged.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { act, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { theme } from "../src/shared/theme";

type Entry = "bootstrap" | "login" | "admin" | "app";

const ENTRIES: Entry[] = ["bootstrap", "login", "admin", "app"];
const NON_ADMIN_ENTRIES: Entry[] = ["bootstrap", "login", "app"];

const FRONTEND_ROOT = path.resolve(__dirname, "..");
const SRC_ROOT = path.join(FRONTEND_ROOT, "src");

const LOADERS: Record<Entry, () => Promise<unknown>> = {
  bootstrap: () => import("../src/bootstrap/main"),
  login: () => import("../src/login/main"),
  admin: () => import("../src/admin/main"),
  app: () => import("../src/app/main"),
};

/** A pathname at which each entry's own document is served. */
const HOME_PATH: Record<Entry, string> = {
  bootstrap: "/",
  login: "/",
  admin: "/admin/",
  app: "/",
};

function mountElement(): HTMLElement {
  const root = document.getElementById("root");
  if (root === null) throw new Error("test setup: #root missing");
  return root;
}

/**
 * Feature 005, step 004 — DoD-11 (context.md D15): from 005/004 the admin entry awaits a
 * GET /api/me gate before it creates a root, so its clauses of DoD-1..DoD-4 stub that request
 * with an administrator identity and wait for the render. Other entries are untouched.
 */
function stubAdminIdentity(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (new URL(raw, "http://localhost").pathname !== "/api/me") {
        return Promise.reject(new TypeError("unexpected request in admin entry test"));
      }
      return Promise.resolve(
        new Response(JSON.stringify({ id: "9007199254740993", username: "mira", role: "admin" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }),
  );
}

async function settle(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => setImmediate(resolve));
    });
  }
}

async function mountEntry(entry: Entry, pathname: string): Promise<void> {
  vi.resetModules();
  document.body.innerHTML = '<div id="root"></div>';
  window.history.pushState({}, "", pathname);
  if (entry === "admin") stubAdminIdentity(); // 005/004 DoD-11
  await act(async () => {
    await LOADERS[entry]();
  });
  if (entry === "admin") await settle(); // 005/004 DoD-11: the gate resolves before the mount
}

function markersIn(container: ParentNode): string[] {
  return Array.from(container.querySelectorAll("[data-entry]")).map(
    (el) => el.getAttribute("data-entry") ?? "",
  );
}

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function readSource(file: string): string {
  return readFileSync(file, "utf8");
}

/** Every module specifier a source file imports (static, side-effect, dynamic, re-export, require). */
function importSpecifiers(source: string): string[] {
  const pattern = /(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']/g;
  return Array.from(stripComments(source).matchAll(pattern), (m) => m[1]);
}

function entryMain(entry: Entry): string {
  return path.join(SRC_ROOT, entry, "main.tsx");
}

function entryHtml(entry: Entry): string {
  return path.join(SRC_ROOT, entry, "index.html");
}

function parseHtml(file: string): Document {
  return new DOMParser().parseFromString(readSource(file), "text/html");
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-mantine-color-scheme");
  document.querySelectorAll("style").forEach((style) => style.remove());
});

afterEach(async () => {
  const { notifications } = await import("@mantine/notifications");
  act(() => {
    notifications.clean();
  });
  document.body.innerHTML = "";
  window.history.pushState({}, "", "/");
  window.localStorage.clear();
  vi.unstubAllGlobals(); // 005/004 DoD-11: drop the admin clauses' /api/me stub
});

// ---------------------------------------------------------------------------
describe("each entry mounts its own marker", () => {
  it.each(ENTRIES)("%s renders its own marker on #root — DoD-1", async (entry) => {
    await mountEntry(entry, HOME_PATH[entry]);
    expect(mountElement().querySelector(`[data-entry="${entry}"]`)).not.toBeNull();
  });

  it.each(ENTRIES)("%s renders no other entry's marker — DoD-1", async (entry) => {
    await mountEntry(entry, HOME_PATH[entry]);
    expect(markersIn(document)).toEqual([entry]);
  });

  it.each(ENTRIES)("%s renders its marker for a deep link too — DoD-1", async (entry) => {
    const deep = entry === "admin" ? "/admin/users/abc123" : "/sessions/abc123";
    await mountEntry(entry, deep);
    expect(markersIn(document)).toEqual([entry]);
  });
});

// ---------------------------------------------------------------------------
describe("each entry renders inside AppProviders", () => {
  it.each(ENTRIES)("%s applies Mantine's colour scheme, dark by default — DoD-2", async (entry) => {
    await mountEntry(entry, HOME_PATH[entry]);
    expect(document.documentElement.getAttribute("data-mantine-color-scheme")).toBe("dark");
  });

  it.each(ENTRIES)("%s carries the shared theme into Mantine's CSS variables — DoD-2", async (entry) => {
    await mountEntry(entry, HOME_PATH[entry]);
    const css = Array.from(document.querySelectorAll("style"))
      .map((style) => style.textContent ?? "")
      .filter((text) => text.includes("--mantine-"))
      .join("\n");
    const fontMatch = /--mantine-font-family:\s*([^;}]+)[;}]/.exec(css);
    expect(fontMatch).not.toBeNull();
    expect(fontMatch?.[1].trim()).toBe(theme.fontFamily);
  });

  it.each(ENTRIES)("%s has the notifications outlet mounted — DoD-2", async (entry) => {
    await mountEntry(entry, HOME_PATH[entry]);
    // Same module registry as the entry just evaluated.
    const { notifications } = await import("@mantine/notifications");
    act(() => {
      notifications.show({ message: `outlet probe ${entry}` });
    });
    expect(await screen.findByText(`outlet probe ${entry}`)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Each admin clause below runs behind the administrator /api/me stub (005/004 DoD-11).
describe("the admin entry's basename is exactly /admin", () => {
  it("a location of /admin/users resolves against the basename — DoD-3", async () => {
    await mountEntry("admin", "/admin/users");
    expect(markersIn(mountElement())).toEqual(["admin"]);
  });

  it("the bare /admin (no trailing slash) resolves, so the basename has none — DoD-3", async () => {
    await mountEntry("admin", "/admin");
    expect(markersIn(mountElement())).toEqual(["admin"]);
  });

  it("a location outside /admin renders nothing, so a basename is in effect — DoD-3", async () => {
    await mountEntry("admin", "/users");
    expect(markersIn(document)).toEqual([]);
  });

  it("the origin root renders nothing under the admin router — DoD-3", async () => {
    await mountEntry("admin", "/");
    expect(markersIn(document)).toEqual([]);
  });

  it("a sibling path sharing the prefix (/administrator) is not under the basename — DoD-3", async () => {
    await mountEntry("admin", "/administrator");
    expect(markersIn(document)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
describe("bootstrap, login and app declare no basename", () => {
  const PATHS = ["/", "/admin/users", "/sessions/abc123", "/login", "/bootstrap"];

  for (const entry of NON_ADMIN_ENTRIES) {
    it.each(PATHS)(`${entry} renders its marker at %s — DoD-4`, async (pathname) => {
      await mountEntry(entry, pathname);
      expect(markersIn(mountElement())).toEqual([entry]);
    });
  }

  it.each(NON_ADMIN_ENTRIES)("%s/main.tsx declares no basename — DoD-4", (entry) => {
    const source = stripComments(readSource(entryMain(entry)));
    expect(source).not.toMatch(/\bbasename\b/);
  });
});

// ---------------------------------------------------------------------------
describe("shell.css and global.css imports", () => {
  function allSourceFiles(dir: string): string[] {
    return readdirSync(dir, { withFileTypes: true }).flatMap((dirent) => {
      const full = path.join(dir, dirent.name);
      if (dirent.isDirectory()) return allSourceFiles(full);
      return /\.(ts|tsx)$/.test(dirent.name) ? [full] : [];
    });
  }

  function specNames(spec: string, fileName: string): boolean {
    return path.posix.basename(spec.split("?")[0]) === fileName;
  }

  function importersOf(fileName: string): string[] {
    return allSourceFiles(SRC_ROOT)
      .filter((file) => importSpecifiers(readSource(file)).some((spec) => specNames(spec, fileName)))
      .map((file) => path.relative(FRONTEND_ROOT, file).split(path.sep).join("/"));
  }

  it("src/app/main.tsx imports src/shell.css — DoD-5", () => {
    const specs = importSpecifiers(readSource(entryMain("app"))).filter((spec) => specNames(spec, "shell.css"));
    expect(specs.length).toBe(1);
    const resolved = path.resolve(path.dirname(entryMain("app")), specs[0]);
    expect(resolved).toBe(path.join(SRC_ROOT, "shell.css"));
  });

  it("no other module under frontend/src imports shell.css — DoD-5", () => {
    expect(importersOf("shell.css")).toEqual(["src/app/main.tsx"]);
  });

  it.each(ENTRIES)("%s/main.tsx does not import global.css — DoD-6", (entry) => {
    const specs = importSpecifiers(readSource(entryMain(entry)));
    expect(specs.filter((spec) => specNames(spec, "global.css"))).toEqual([]);
  });

  it("global.css reaches the entries through AppProviders — DoD-6", () => {
    const providers = path.join(SRC_ROOT, "shared", "AppProviders.tsx");
    const resolved = importSpecifiers(readSource(providers))
      .filter((spec) => spec.startsWith("."))
      .map((spec) => path.resolve(path.dirname(providers), spec));
    expect(resolved).toContain(path.join(SRC_ROOT, "global.css"));
  });
});

// ---------------------------------------------------------------------------
describe("the four index.html documents", () => {
  it.each(ENTRIES)("%s/index.html has exactly one mount element — DoD-7", (entry) => {
    const doc = parseHtml(entryHtml(entry));
    expect(doc.querySelectorAll("#root").length).toBe(1);
    expect(doc.querySelectorAll('[id="root"]').length).toBe(1);
  });

  it.each(ENTRIES)("%s/index.html has exactly one script, a module script — DoD-7", (entry) => {
    const doc = parseHtml(entryHtml(entry));
    expect(doc.querySelectorAll('script[type="module"]').length).toBe(1);
    expect(doc.querySelectorAll("script").length).toBe(1);
  });

  it.each(ENTRIES)("%s/index.html's module script resolves to the sibling main.tsx — DoD-7", (entry) => {
    const doc = parseHtml(entryHtml(entry));
    const script = doc.querySelector('script[type="module"]');
    expect(script).not.toBeNull();
    const src = script?.getAttribute("src") ?? "";
    expect(src).not.toBe("");
    const resolved = src.startsWith("/")
      ? path.join(FRONTEND_ROOT, src)
      : path.resolve(path.dirname(entryHtml(entry)), src);
    expect(path.normalize(resolved)).toBe(entryMain(entry));
    expect(existsSync(resolved)).toBe(true);
  });

  it.each(ENTRIES)("%s/index.html declares a language — DoD-8", (entry) => {
    const doc = parseHtml(entryHtml(entry));
    expect((doc.documentElement.getAttribute("lang") ?? "").trim()).not.toBe("");
  });

  it.each(ENTRIES)("%s/index.html declares a character set — DoD-8", (entry) => {
    const raw = readSource(entryHtml(entry));
    const doc = parseHtml(entryHtml(entry));
    const metaCharset = (doc.querySelector("meta[charset]")?.getAttribute("charset") ?? "").trim();
    const httpEquiv = /<meta[^>]+http-equiv\s*=\s*["']?content-type["']?[^>]*charset\s*=/i.test(raw);
    expect(metaCharset !== "" || httpEquiv).toBe(true);
  });

  it.each(ENTRIES)("%s/index.html contains no inline script — DoD-8", (entry) => {
    const doc = parseHtml(entryHtml(entry));
    for (const script of Array.from(doc.querySelectorAll("script"))) {
      expect((script.getAttribute("src") ?? "").trim()).not.toBe("");
      expect((script.textContent ?? "").trim()).toBe("");
    }
    const handlers = Array.from(doc.querySelectorAll("*")).flatMap((el) =>
      Array.from(el.attributes)
        .map((attr) => attr.name)
        .filter((name) => name.toLowerCase().startsWith("on")),
    );
    expect(handlers).toEqual([]);
  });

  it.each(ENTRIES)("%s/index.html contains no inline style — DoD-8", (entry) => {
    const doc = parseHtml(entryHtml(entry));
    expect(doc.querySelectorAll("style").length).toBe(0);
    expect(doc.querySelectorAll("[style]").length).toBe(0);
  });
});
