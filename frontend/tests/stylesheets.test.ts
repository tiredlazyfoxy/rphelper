// Feature 002, step 002 — the two hand-written stylesheets (DoD-1..DoD-4).
// The stylesheets are read from disk: this step wires no import of either file.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

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

describe("shell.css is declared but empty", () => {
  it("exists — DoD-3", () => {
    expect(existsSync(SHELL_CSS)).toBe(true);
  });

  it("contains no CSS rule: comments and whitespace only — DoD-3", () => {
    const withoutComments = stripComments(readText(SHELL_CSS));
    expect(withoutComments).not.toContain("{");
    expect(withoutComments.trim()).toBe("");
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
