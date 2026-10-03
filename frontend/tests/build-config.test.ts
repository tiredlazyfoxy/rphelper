// Feature 002, step 001 — build configuration, package manifest, tsconfigs and the
// TypeScript-only rule (DoD-1..DoD-5, DoD-7..DoD-11).
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import config from "../vite.config";

const FRONTEND_ROOT = path.resolve(__dirname, "..");

function readText(relative: string): string {
  return readFileSync(path.join(FRONTEND_ROOT, relative), "utf8");
}

function readJson(relative: string): Record<string, unknown> {
  return JSON.parse(readText(relative)) as Record<string, unknown>;
}

type PackageJson = {
  scripts?: Record<string, string>;
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
};

function readPackageJson(): PackageJson {
  return readJson("package.json") as PackageJson;
}

type TsConfig = {
  compilerOptions?: Record<string, unknown>;
  include?: string[];
};

function readTsConfig(name: string): TsConfig {
  return readJson(name) as TsConfig;
}

function stripDotSlash(p: string): string {
  return p.startsWith("./") ? p.slice(2) : p;
}

function toPosix(p: string): string {
  return p.replace(/\\/g, "/");
}

// Resolves a config path the way the tools do: a relative value against `base`, an
// absolute one to itself. Returns an OS-native absolute path.
function resolveFrom(base: string, value: string): string {
  return path.resolve(base, value);
}

function samePath(a: string, b: string): boolean {
  return path.relative(path.resolve(a), path.resolve(b)) === "";
}

// Minimal glob -> RegExp over forward-slash paths: `**/`, `**`, `*`, `?`, `{a,b}`.
function globToRegExp(glob: string): RegExp {
  let re = "";
  let i = 0;
  let braceDepth = 0;
  while (i < glob.length) {
    const c = glob[i] as string;
    if (c === "*") {
      if (glob[i + 1] === "*") {
        if (glob[i + 2] === "/") {
          re += "(?:[^/]+/)*";
          i += 3;
        } else {
          re += ".*";
          i += 2;
        }
      } else {
        re += "[^/]*";
        i += 1;
      }
    } else if (c === "?") {
      re += "[^/]";
      i += 1;
    } else if (c === "{") {
      re += "(?:";
      braceDepth += 1;
      i += 1;
    } else if (c === "}" && braceDepth > 0) {
      re += ")";
      braceDepth -= 1;
      i += 1;
    } else if (c === "," && braceDepth > 0) {
      re += "|";
      i += 1;
    } else {
      re += c.replace(/[.+^$()|[\]\\]/g, "\\$&");
      i += 1;
    }
  }
  return new RegExp(`^${re}$`, process.platform === "win32" ? "i" : "");
}

// ---------------------------------------------------------------------------
// vite.config.ts
// ---------------------------------------------------------------------------

describe("vite.config.ts — build inputs", () => {
  it("declares exactly the four named inputs, no fifth and no renamed key (DoD-1)", () => {
    const input = config.build?.rollupOptions?.input;
    expect(input).toBeTypeOf("object");
    expect(Array.isArray(input)).toBe(false);
    const record = input as Record<string, string>;

    expect(Object.keys(record).sort()).toEqual(["admin", "app", "bootstrap", "login"]);
  });

  it.each(["bootstrap", "login", "admin", "app"])(
    "input %s is an absolute path resolving to frontend/src/<name>/index.html (DoD-1)",
    (name) => {
      const record = (config.build?.rollupOptions?.input ?? {}) as Record<string, string>;
      const value = record[name];
      expect(typeof value).toBe("string");
      expect(path.isAbsolute(value as string), `input ${name} = "${String(value)}" is not absolute`).toBe(true);
      const expected = path.resolve(FRONTEND_ROOT, "src", name, "index.html");
      expect(
        samePath(value as string, expected),
        `input ${name} = "${String(value)}" does not resolve to ${expected}`,
      ).toBe(true);
    },
  );
});

describe("vite.config.ts — dev server", () => {
  it("uses port 8193 with strictPort enabled (DoD-2)", () => {
    expect(config.server?.port).toBe(8193);
    expect(config.server?.strictPort).toBe(true);
  });

  it("declares exactly one proxy rule, /api -> localhost:8184 (DoD-2)", () => {
    const proxy = config.server?.proxy as Record<string, unknown> | undefined;
    expect(proxy).toBeTypeOf("object");
    const prefixes = Object.keys(proxy ?? {});
    expect(prefixes).toEqual(["/api"]);

    const rule = (proxy ?? {})["/api"];
    let target: unknown;
    if (typeof rule === "string") {
      target = rule;
    } else if (rule !== null && typeof rule === "object") {
      target = (rule as { target?: unknown }).target;
    }
    expect(typeof target).toBe("string");
    const url = new URL(target as string);
    expect(url.hostname).toBe("localhost");
    expect(url.port).toBe("8184");
  });

  it("writes both ports as literals, never environment reads (DoD-3)", () => {
    const source = readText("vite.config.ts");
    expect(source).not.toMatch(/process\.env/);
    expect(source).not.toMatch(/import\.meta\.env/);
    expect(source).not.toMatch(/\bloadEnv\b/);
    expect(source).toMatch(/\b8193\b/);
    expect(source).toMatch(/\b8184\b/);
  });
});

describe("vite.config.ts — base, root and output", () => {
  it("sets no base, so it stays at Vite's default (DoD-4)", () => {
    expect("base" in config).toBe(false);
    expect(config.base).toBeUndefined();
  });

  it("sets root to the frontend/src directory (DoD-4)", () => {
    const root = config.root;
    expect(typeof root).toBe("string");
    const resolved = resolveFrom(FRONTEND_ROOT, root as string);
    expect(samePath(resolved, path.resolve(FRONTEND_ROOT, "src")), `root = "${String(root)}"`).toBe(true);
  });

  it("sets build.outDir to the frontend/dist directory, resolved against root (DoD-4)", () => {
    const root = resolveFrom(FRONTEND_ROOT, (config.root ?? ".") as string);
    const outDir = config.build?.outDir;
    expect(typeof outDir).toBe("string");
    // A relative outDir is resolved against root, as Vite resolves it.
    const resolved = resolveFrom(root, outDir as string);
    expect(samePath(resolved, path.resolve(FRONTEND_ROOT, "dist")), `build.outDir = "${String(outDir)}"`).toBe(
      true,
    );
  });

  it("sets build.emptyOutDir to true (DoD-4)", () => {
    expect(config.build?.emptyOutDir).toBe(true);
  });
});

describe("vite.config.ts — Vitest block", () => {
  // Vitest resolves setupFiles and include against the test block's own root.
  const testRoot = (): string => resolveFrom(FRONTEND_ROOT, (config.test?.root ?? ".") as string);

  it("sets its own root to the frontend directory (DoD-5)", () => {
    const root = config.test?.root;
    expect(typeof root).toBe("string");
    expect(samePath(resolveFrom(FRONTEND_ROOT, root as string), FRONTEND_ROOT), `test.root = "${String(root)}"`).toBe(
      true,
    );
  });

  it("uses the jsdom environment (DoD-5)", () => {
    expect(config.test?.environment).toBe("jsdom");
  });

  it("points setupFiles at ./tests/setup.ts, resolving to frontend/tests/setup.ts (DoD-5)", () => {
    const raw = config.test?.setupFiles;
    const files = raw === undefined ? [] : Array.isArray(raw) ? raw : [raw];
    expect(files.map((f) => stripDotSlash(toPosix(f)))).toEqual(["tests/setup.ts"]);
    expect(samePath(resolveFrom(testRoot(), files[0] as string), path.resolve(FRONTEND_ROOT, "tests", "setup.ts"))).toBe(
      true,
    );
  });

  it("has an include pattern matching *.test.ts and *.test.tsx under frontend/tests/ and nothing under frontend/src/ (DoD-5)", () => {
    const include = config.test?.include;
    expect(Array.isArray(include)).toBe(true);
    expect((include ?? []).length).toBeGreaterThan(0);

    // Each pattern resolved against the test root, then compared as forward-slash paths.
    const matchers = (include ?? []).map((pattern) => ({
      pattern,
      re: globToRegExp(toPosix(path.isAbsolute(pattern) ? pattern : path.join(testRoot(), stripDotSlash(pattern)))),
    }));
    const matches = (candidate: string): boolean => {
      const posix = toPosix(candidate);
      return matchers.some((m) => m.re.test(posix));
    };
    const under = (...segments: string[]): string => path.resolve(FRONTEND_ROOT, ...segments);

    const mustMatch = [
      under("tests", "build-config.test.ts"),
      under("tests", "entries.test.tsx"),
      under("tests", "shared", "api.test.ts"),
      under("tests", "shared", "IconButton.test.tsx"),
      under("tests", "a", "b", "deep.test.ts"),
      under("tests", "a", "b", "deep.test.tsx"),
    ];
    for (const file of mustMatch) {
      expect(matches(file), `include (${String(include)}) does not match ${file}`).toBe(true);
    }

    const mustNotMatch = [
      under("src", "x.test.ts"),
      under("src", "x.test.tsx"),
      under("src", "shared", "api.test.ts"),
      under("src", "shared", "IconButton.test.tsx"),
      under("src", "app", "main.test.tsx"),
      under("src", "tests", "x.test.ts"),
      under("src", "a", "tests", "b.test.tsx"),
    ];
    for (const file of mustNotMatch) {
      expect(matches(file), `include (${String(include)}) matches ${file} under frontend/src/`).toBe(false);
    }
  });
});

// ---------------------------------------------------------------------------
// package.json
// ---------------------------------------------------------------------------

describe("package.json — scripts", () => {
  it("declares exactly build, test, typecheck and dev (DoD-7)", () => {
    const scripts = readPackageJson().scripts ?? {};
    expect(Object.keys(scripts).sort()).toEqual(["build", "dev", "test", "typecheck"]);
  });

  it("runs Vitest once, without a watch flag (DoD-7)", () => {
    const testScript = readPackageJson().scripts?.test ?? "";
    expect(testScript).toMatch(/\bvitest\b/);
    // single-run mode: `vitest run` or `vitest --run`
    expect(testScript).toMatch(/\bvitest\s+(run\b|.*--run\b)/);
    expect(testScript).not.toMatch(/--watch\b/);
    expect(testScript).not.toMatch(/(^|\s)-w(\s|$)/);
    expect(testScript).not.toMatch(/\bvitest\s+watch\b/);
    expect(testScript).not.toMatch(/\bvitest\s+dev\b/);
  });
});

describe("package.json — excluded dependencies", () => {
  it("declares none of the deferred packages, @mantine/form, or any linter (DoD-8)", () => {
    const pkg = readPackageJson();
    const names = [...Object.keys(pkg.dependencies ?? {}), ...Object.keys(pkg.devDependencies ?? {})];

    // Rescoped by feature 009 step 005 (context.md D3): the markdown editor un-defers
    // `@mantine/tiptap`, `@tiptap/react`, `@tiptap/pm`, `@tiptap/starter-kit`,
    // `@tiptap/extension-link` and `tiptap-markdown`, which are now sanctioned runtime
    // dependencies. Everything else this clause forbade stays forbidden.
    // Rescoped again by feature 013 step 004 (context.md D5): `react-markdown` renders
    // message bodies and is a sanctioned runtime dependency; its presence is asserted in
    // tests/app/MessageBody.test.tsx (013 step 004 DoD-1).
    const forbidden = names.filter(
      (n) =>
        n === "@mantine/form" ||
        n === "eslint" ||
        n.startsWith("eslint-") ||
        n.startsWith("@dnd-kit/"),
    );
    expect(forbidden).toEqual([]);
  });
});

describe("package.json — required dependencies", () => {
  const RUNTIME = [
    "react",
    "react-dom",
    "@mantine/core",
    "@mantine/hooks",
    "@mantine/notifications",
    "@tabler/icons-react",
    "react-router-dom",
    "mobx",
    "mobx-react-lite",
  ];
  const DEV = [
    "typescript",
    "vite",
    "@vitejs/plugin-react",
    "vitest",
    "jsdom",
    "@testing-library/react",
    "@testing-library/jest-dom",
    "@testing-library/user-event",
    "@types/react",
    "@types/react-dom",
    "@types/node",
  ];

  it("declares every D14 runtime package in dependencies (DoD-9)", () => {
    const deps = readPackageJson().dependencies ?? {};
    const missing = RUNTIME.filter((n) => !(n in deps));
    expect(missing).toEqual([]);
  });

  it("declares every D14 development package in devDependencies (DoD-9)", () => {
    const devDeps = readPackageJson().devDependencies ?? {};
    const missing = DEV.filter((n) => !(n in devDeps));
    expect(missing).toEqual([]);
  });

  it("constrains @tabler/icons-react to ^3.40 (DoD-9)", () => {
    expect(readPackageJson().dependencies?.["@tabler/icons-react"]).toBe("^3.40");
  });

  it("constrains react-router-dom to major version 7 (DoD-9)", () => {
    const range = readPackageJson().dependencies?.["react-router-dom"] ?? "";
    expect(range).toMatch(/^[\^~]?7(\.|$)/);
  });
});

// ---------------------------------------------------------------------------
// tsconfigs
// ---------------------------------------------------------------------------

describe("tsconfig.json", () => {
  it("enables strict and the three lint-shaped flags, and sets noEmit (DoD-10)", () => {
    const opts = readTsConfig("tsconfig.json").compilerOptions ?? {};
    expect(opts.strict).toBe(true);
    expect(opts.noUnusedLocals).toBe(true);
    expect(opts.noUnusedParameters).toBe(true);
    expect(opts.noFallthroughCasesInSwitch).toBe(true);
    expect(opts.noEmit).toBe(true);
  });

  it("declares no paths aliases (DoD-10)", () => {
    const opts = readTsConfig("tsconfig.json").compilerOptions ?? {};
    expect("paths" in opts).toBe(false);
  });

  it("includes both src and tests (DoD-10)", () => {
    const include = (readTsConfig("tsconfig.json").include ?? []).map((p) => stripDotSlash(p.replace(/\\/g, "/")));
    const covers = (dir: string): boolean => include.some((p) => p === dir || p.startsWith(`${dir}/`));
    expect(covers("src")).toBe(true);
    expect(covers("tests")).toBe(true);
  });

  it.each(["tsconfig.json", "tsconfig.node.json"])("%s enables neither allowJs nor checkJs (DoD-10)", (name) => {
    const opts = readTsConfig(name).compilerOptions ?? {};
    expect(opts.allowJs === true).toBe(false);
    expect(opts.checkJs === true).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// TypeScript only
// ---------------------------------------------------------------------------

describe("TypeScript-only rule", () => {
  it("has no .js/.jsx/.mjs/.cjs file under frontend/ outside node_modules, dist, coverage (DoD-11)", () => {
    const EXCLUDED = new Set(["node_modules", "dist", "coverage"]);
    const JS_EXT = /\.(js|jsx|mjs|cjs)$/i;
    const offenders: string[] = [];

    const walk = (dir: string): void => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          // Generated output is exempt (context.md D4).
          if (EXCLUDED.has(entry.name)) continue;
          walk(full);
        } else if (JS_EXT.test(entry.name)) {
          offenders.push(path.relative(FRONTEND_ROOT, full).replace(/\\/g, "/"));
        }
      }
    };
    walk(path.resolve(FRONTEND_ROOT));

    expect(offenders, `JavaScript files found: ${offenders.join(", ")}`).toEqual([]);
  });
});
