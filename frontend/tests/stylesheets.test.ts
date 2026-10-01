// Feature 002, step 002 — the two hand-written stylesheets (DoD-1..DoD-4).
// The stylesheets are read from disk: this step wires no import of either file.
//
// Extended by feature 008, step 002 — `shell.css`'s workspace layout rules
// (008/002 DoD-1..DoD-6). Feature 002/002's "shell.css contains no CSS rule"
// clause is replaced by those; its "exists" clause and the "exactly two
// stylesheets" and "global.css holds resets only" clauses are unchanged.
// jsdom applies no stylesheet, so every clause here is a scan of the source text.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { NARROW_VIEWPORT_QUERY } from "../src/app/shellState";

const FRONTEND_ROOT = path.resolve(__dirname, "..");
const SRC_ROOT = path.join(FRONTEND_ROOT, "src");
const GLOBAL_CSS = path.join(SRC_ROOT, "global.css");
const SHELL_CSS = path.join(SRC_ROOT, "shell.css");

function readText(file: string): string {
  return readFileSync(file, "utf8");
}

function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

type Rule = {
  selectors: string[];
  declarations: Map<string, string>;
};

function normalizeSelector(selector: string): string {
  return selector.trim().replace(/\s+/g, " ").toLowerCase();
}

function parseRules(css: string): Rule[] {
  const rules: Rule[] = [];
  const blockPattern = /([^{}]*)\{([^{}]*)\}/g;
  for (const match of stripComments(css).matchAll(blockPattern)) {
    const selectors = match[1]
      .split(",")
      .map(normalizeSelector)
      .filter((s) => s.length > 0);
    const declarations = new Map<string, string>();
    for (const raw of match[2].split(";")) {
      const colon = raw.indexOf(":");
      if (colon < 0) continue;
      const property = raw.slice(0, colon).trim().toLowerCase();
      const value = raw
        .slice(colon + 1)
        .trim()
        .replace(/\s*!important\s*$/i, "")
        .replace(/\s+/g, " ")
        .toLowerCase();
      if (property.length > 0) declarations.set(property, value);
    }
    rules.push({ selectors, declarations });
  }
  return rules;
}

/** All declarations that apply to a selector, merged in source order (later wins). */
function declarationsFor(rules: Rule[], ...selectors: string[]): Map<string, string> {
  const merged = new Map<string, string>();
  for (const rule of rules) {
    if (!rule.selectors.some((s) => selectors.includes(s))) continue;
    for (const [property, value] of rule.declarations) merged.set(property, value);
  }
  return merged;
}

function allDeclarations(rules: Rule[]): Array<[string, string]> {
  return rules.flatMap((rule) => [...rule.declarations.entries()]);
}

const ZERO = new Set(["0", "0px"]);
const FULL_HEIGHT = new Set(["100%", "100vh", "100dvh", "100svh", "100lvh"]);

function hasFullHeight(decls: Map<string, string>): boolean {
  const height = decls.get("height");
  const minHeight = decls.get("min-height");
  return (
    (height !== undefined && FULL_HEIGHT.has(height)) ||
    (minHeight !== undefined && FULL_HEIGHT.has(minHeight))
  );
}

function walkFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkFiles(full));
    else if (entry.isFile()) out.push(full);
  }
  return out;
}

// ------------------------------------------------- feature 008/002 helpers

/**
 * Locates the narrow-viewport at-rule tolerantly (whitespace inside the
 * condition is CSS-insignificant); DoD-6 is what pins the literal spelling.
 */
const NARROW_MEDIA = /@media\s*\(\s*width\s*<\s*820px\s*\)/i;

/**
 * Splits comment-stripped CSS into the narrow at-rule's body (`null` when the
 * at-rule is absent) and everything outside it, so a declaration inside the
 * media query can never be mistaken for a top-level one.
 */
function splitNarrowMedia(css: string): { body: string | null; outside: string } {
  const match = NARROW_MEDIA.exec(css);
  if (match === null) {
    return { body: null, outside: css };
  }
  const open = css.indexOf("{", match.index + match[0].length);
  if (open < 0) {
    return { body: null, outside: css };
  }
  let depth = 0;
  for (let i = open; i < css.length; i += 1) {
    const char = css.charAt(i);
    if (char === "{") {
      depth += 1;
      continue;
    }
    if (char !== "}") {
      continue;
    }
    depth -= 1;
    if (depth === 0) {
      return {
        body: css.slice(open + 1, i),
        outside: css.slice(0, match.index) + css.slice(i + 1),
      };
    }
  }
  return { body: css.slice(open + 1), outside: css.slice(0, match.index) };
}

/** A child combinator reads the same as a descendant one for the allow-list. */
function canonicalSelector(selector: string): string {
  return selector
    .replace(/\s*>\s*/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Comma spacing inside a value is insignificant; compare values compacted. */
function compactValue(value: string): string {
  return value
    .replace(/\s*,\s*/g, ",")
    .replace(/\s+/g, " ")
    .trim();
}

describe("global.css resets", () => {
  it("applies border-box sizing to every element — DoD-1", () => {
    const rules = parseRules(readText(GLOBAL_CSS));
    const universal = declarationsFor(rules, "*");
    const documentRoot = declarationsFor(rules, "html", ":root");
    const direct = universal.get("box-sizing") === "border-box";
    const inherited =
      universal.get("box-sizing") === "inherit" &&
      documentRoot.get("box-sizing") === "border-box";
    expect(direct || inherited).toBe(true);
  });

  it("removes the default margin of the document — DoD-1", () => {
    const rules = parseRules(readText(GLOBAL_CSS));
    const margin = declarationsFor(rules, "html", ":root").get("margin");
    expect(margin !== undefined && ZERO.has(margin)).toBe(true);
  });

  it("removes the default margin of the body — DoD-1", () => {
    const rules = parseRules(readText(GLOBAL_CSS));
    const margin = declarationsFor(rules, "body").get("margin");
    expect(margin !== undefined && ZERO.has(margin)).toBe(true);
  });

  it("gives the document full height — DoD-1", () => {
    const rules = parseRules(readText(GLOBAL_CSS));
    expect(hasFullHeight(declarationsFor(rules, "html", ":root"))).toBe(true);
  });

  it("gives the body full height — DoD-1", () => {
    const rules = parseRules(readText(GLOBAL_CSS));
    expect(hasFullHeight(declarationsFor(rules, "body"))).toBe(true);
  });

  it("gives the mount node (#root) full height — DoD-1", () => {
    const rules = parseRules(readText(GLOBAL_CSS));
    expect(hasFullHeight(declarationsFor(rules, "#root"))).toBe(true);
  });
});

describe("global.css holds resets only", () => {
  const COLOUR_PROPERTIES = new Set([
    "color",
    "border-color",
    "border-top-color",
    "border-right-color",
    "border-bottom-color",
    "border-left-color",
    "outline-color",
    "text-decoration-color",
    "column-rule-color",
    "caret-color",
    "accent-color",
    "fill",
    "stroke",
  ]);
  const HEX_COLOUR = /#[0-9a-f]{3,8}\b/i;
  const COLOUR_FUNCTION = /\b(rgba?|hsla?|hwb|lab|lch|oklab|oklch|color|color-mix)\(/i;
  const NAMED_COLOUR =
    /\b(black|white|red|green|blue|gray|grey|yellow|orange|purple|pink|silver|navy|teal|maroon|olive|lime|aqua|fuchsia|cyan|magenta)\b/i;

  it("declares no colour value — DoD-2", () => {
    const decls = allDeclarations(parseRules(readText(GLOBAL_CSS)));
    const offenders = decls.filter(
      ([property, value]) =>
        COLOUR_PROPERTIES.has(property) ||
        HEX_COLOUR.test(value) ||
        COLOUR_FUNCTION.test(value) ||
        NAMED_COLOUR.test(value),
    );
    expect(offenders).toEqual([]);
  });

  it("declares no font family — DoD-2", () => {
    const decls = allDeclarations(parseRules(readText(GLOBAL_CSS)));
    const offenders = decls.filter(
      ([property]) => property === "font-family" || property === "font",
    );
    expect(offenders).toEqual([]);
  });

  it("declares no background — DoD-2", () => {
    const decls = allDeclarations(parseRules(readText(GLOBAL_CSS)));
    const offenders = decls.filter(([property]) => property.startsWith("background"));
    expect(offenders).toEqual([]);
  });

  it("contains no media query — DoD-2", () => {
    const css = stripComments(readText(GLOBAL_CSS));
    expect(css).not.toMatch(/@media\b/i);
  });

  it("declares no CSS custom property — DoD-2", () => {
    const decls = allDeclarations(parseRules(readText(GLOBAL_CSS)));
    const offenders = decls.filter(([property]) => property.startsWith("--"));
    expect(offenders).toEqual([]);
  });
});

describe("shell.css is declared", () => {
  it("exists — DoD-3", () => {
    expect(existsSync(SHELL_CSS)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Feature 008, step 002 — shell.css carries the workspace grid and nothing else.

describe("shell.css declares the workspace grid", () => {
  it("makes .app a grid — DoD-1", () => {
    const outside = splitNarrowMedia(stripComments(readText(SHELL_CSS))).outside;
    const app = declarationsFor(parseRules(outside), ".app");
    expect(app.get("display")).toBe("grid");
  });

  it("draws the divider as a 1px gap — DoD-1", () => {
    const outside = splitNarrowMedia(stripComments(readText(SHELL_CSS))).outside;
    const app = declarationsFor(parseRules(outside), ".app");
    expect(app.get("gap")).toBe("1px");
  });

  it("sizes the two tracks from --navw with a 252px fallback — DoD-1", () => {
    const outside = splitNarrowMedia(stripComments(readText(SHELL_CSS))).outside;
    const app = declarationsFor(parseRules(outside), ".app");
    const tracks = app.get("grid-template-columns");
    expect(tracks).toBeDefined();
    expect(compactValue(tracks ?? "")).toBe("var(--navw,252px) minmax(0,1fr)");
  });
});

describe("shell.css collapses the nav column with one class", () => {
  it(".app.nav-collapsed re-points --navw at 48px — DoD-2", () => {
    const outside = splitNarrowMedia(stripComments(readText(SHELL_CSS))).outside;
    const collapsed = declarationsFor(parseRules(outside), ".app.nav-collapsed");
    expect(collapsed.get("--navw")).toBe("48px");
  });

  it(".app.nav-collapsed declares nothing besides --navw — DoD-2", () => {
    const outside = splitNarrowMedia(stripComments(readText(SHELL_CSS))).outside;
    const collapsed = declarationsFor(parseRules(outside), ".app.nav-collapsed");
    expect([...collapsed.keys()].sort()).toEqual(["--navw"]);
  });
});

describe("shell.css carries the narrow-viewport media query", () => {
  it("declares the @media (width < 820px) at-rule — DoD-3", () => {
    const css = stripComments(readText(SHELL_CSS));
    expect(splitNarrowMedia(css).body).not.toBeNull();
  });

  it("pins the narrow nav track to 48px regardless of the collapse class — DoD-3", () => {
    const body = splitNarrowMedia(stripComments(readText(SHELL_CSS))).body;
    const narrow = declarationsFor(parseRules(body ?? ""), ".app");
    expect(narrow.get("--navw")).toBe("48px");
  });

  it("lifts .app.nav-overlay-open .app-nav inside the media query — DoD-3", () => {
    const body = splitNarrowMedia(stripComments(readText(SHELL_CSS))).body;
    const overlay = parseRules(body ?? "").filter((rule) =>
      rule.selectors.some(
        (selector) => canonicalSelector(selector) === ".app.nav-overlay-open .app-nav",
      ),
    );
    expect(overlay.length).toBeGreaterThan(0);
    expect(overlay.some((rule) => rule.declarations.size > 0)).toBe(true);
  });
});

describe("shell.css names no colour of its own", () => {
  const SHELL_COLOUR_PROPERTIES = new Set([
    "background",
    "background-color",
    "color",
    "border-color",
    "border-top-color",
    "border-right-color",
    "border-bottom-color",
    "border-left-color",
    "outline-color",
    "text-decoration-color",
    "column-rule-color",
    "caret-color",
    "accent-color",
    "fill",
    "stroke",
  ]);
  const SHELL_HEX_COLOUR = /#[0-9a-f]{3,8}\b/i;
  const SHELL_COLOUR_FUNCTION = /\b(rgba?|hsla?|hwb|lab|lch|oklab|oklch|color-mix)\(/i;
  const SHELL_NAMED_COLOUR =
    /\b(black|white|red|green|blue|gray|grey|yellow|orange|purple|pink|silver|navy|teal|maroon|olive|lime|aqua|fuchsia|cyan|magenta)\b/i;
  const MANTINE_VARIABLE = /var\(\s*--mantine-[a-z0-9-]+\s*\)/;

  /** A `var(--…)` reference is a token reference, not a colour literal. */
  function withoutVariables(value: string): string {
    return value.replace(/var\(\s*--[^()]*\)/g, "");
  }

  it("declares no literal colour value — DoD-4", () => {
    const decls = allDeclarations(parseRules(readText(SHELL_CSS)));
    const offenders = decls.filter(([, value]) => {
      const bare = withoutVariables(value);
      return (
        SHELL_HEX_COLOUR.test(bare) ||
        SHELL_COLOUR_FUNCTION.test(bare) ||
        SHELL_NAMED_COLOUR.test(bare)
      );
    });
    expect(offenders).toEqual([]);
  });

  it("takes every colour from a Mantine custom property — DoD-4", () => {
    const decls = allDeclarations(parseRules(readText(SHELL_CSS)));
    const offenders = decls.filter(
      ([property, value]) =>
        SHELL_COLOUR_PROPERTIES.has(property) && !MANTINE_VARIABLE.test(value),
    );
    expect(offenders).toEqual([]);
  });

  it("draws the divider line with a Mantine background variable on .app — DoD-4", () => {
    const outside = splitNarrowMedia(stripComments(readText(SHELL_CSS))).outside;
    const app = declarationsFor(parseRules(outside), ".app");
    const background = app.get("background") ?? app.get("background-color");
    expect(background).toBeDefined();
    expect(background ?? "").toMatch(MANTINE_VARIABLE);
  });
});

describe("shell.css holds workspace layout only", () => {
  const ALLOWED_SELECTORS = [
    ".app",
    ".app.nav-collapsed",
    ".app-nav",
    ".app-main",
    ".app.nav-overlay-open .app-nav",
  ];
  const TYPOGRAPHY_PROPERTIES = new Set([
    "line-height",
    "letter-spacing",
    "word-spacing",
    "text-align",
    "text-decoration",
    "text-indent",
    "text-transform",
  ]);

  it("imports no other stylesheet — DoD-5", () => {
    expect(stripComments(readText(SHELL_CSS))).not.toMatch(/@import\b/i);
  });

  it("declares no font face — DoD-5", () => {
    expect(stripComments(readText(SHELL_CSS))).not.toMatch(/@font-face\b/i);
  });

  it("declares no font or typography property — DoD-5", () => {
    const decls = allDeclarations(parseRules(readText(SHELL_CSS)));
    const offenders = decls.filter(
      ([property]) => property.startsWith("font") || TYPOGRAPHY_PROPERTIES.has(property),
    );
    expect(offenders).toEqual([]);
  });

  it("uses no selector beyond the shell's five — DoD-5", () => {
    const selectors = parseRules(readText(SHELL_CSS)).flatMap((rule) => rule.selectors);
    // The file does carry rules (DoD-1..DoD-3), and every one of them is on the list.
    expect(selectors.length).toBeGreaterThan(0);
    const offenders = selectors.filter(
      (selector) => !ALLOWED_SELECTORS.includes(canonicalSelector(selector)),
    );
    // The offending selector is the message: the coder needs to know which rule tripped.
    expect(offenders).toEqual([]);
  });
});

describe("the narrow threshold is one string", () => {
  it("NARROW_VIEWPORT_QUERY is the range query (width < 820px) — DoD-6", () => {
    expect(NARROW_VIEWPORT_QUERY).toBe("(width < 820px)");
  });

  it("shell.css spells the threshold with that very string — DoD-6", () => {
    // The constant itself is the needle, so the two can never drift.
    expect(stripComments(readText(SHELL_CSS))).toContain(NARROW_VIEWPORT_QUERY);
  });
});

describe("exactly two hand-written stylesheets", () => {
  it("global.css and shell.css are the only .css files under src — DoD-4", () => {
    const cssFiles = walkFiles(SRC_ROOT)
      .filter((file) => file.toLowerCase().endsWith(".css"))
      .map((file) => path.relative(SRC_ROOT, file).split(path.sep).join("/"))
      .sort();
    expect(cssFiles).toEqual(["global.css", "shell.css"]);
  });
});
