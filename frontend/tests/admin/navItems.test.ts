// Feature 005, step 005 — the admin nav table and its pure matcher (DoD-1..DoD-4).
// DoD-5 lives in adminShellState.test.ts; DoD-6..DoD-14 in AdminApp.test.tsx;
// DoD-15..DoD-18 are [manual/live].
//
// Expected values come from the step's Interface intent and DoD and from context.md D12:
// whole-segment matching, the `exact` flag on the root item, and `/database` versus
// `/database-backups` as the case that must not regress. Every call here is a plain call with
// two plain arguments — no router, no render.
import { readFileSync } from "node:fs";
import path from "node:path";
import { IconDatabase, IconServer2, IconUsers } from "@tabler/icons-react";
import { describe, expect, it } from "vitest";
import { NAV_ITEMS, isNavItemActive, type NavItem } from "../../src/admin/navItems";

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const NAV_ITEMS_SOURCE = path.join(FRONTEND_ROOT, "src", "admin", "navItems.ts");

const NoIcon: NavItem["icon"] = () => null;

/** A hand-built item — a plain object, not taken from the table. */
function item(itemPath: string, exact = false, label = "Probe"): NavItem {
  return Object.freeze({ label, path: itemPath, icon: NoIcon, exact });
}

function tableItem(label: string): NavItem {
  const found = NAV_ITEMS.find((entry) => entry.label === label);
  if (found === undefined) throw new Error(`nav table has no item labelled ${label}`);
  return found;
}

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

// ---------------------------------------------------------------------------
describe("an item's own path and its descendants match; unrelated paths do not", () => {
  it.each([
    ["LLM Servers", "/llm-servers"],
    ["Database", "/database"],
  ])("the %s item is active on its own path %s — DoD-1", (label, pathname) => {
    expect(isNavItemActive(pathname, tableItem(label))).toBe(true);
  });

  it.each([
    ["LLM Servers", "/llm-servers/anything"],
    ["LLM Servers", "/llm-servers/a/b/c"],
    ["Database", "/database/tables"],
    ["Database", "/database/tables/users"],
  ])("the %s item is active on the descendant path %s — DoD-1", (label, pathname) => {
    expect(isNavItemActive(pathname, tableItem(label))).toBe(true);
  });

  it.each([
    ["LLM Servers", "/llm-servers/"],
    ["Database", "/database/"],
  ])("the %s item is active on its own path with a trailing slash (%s) — DoD-1", (label, pathname) => {
    expect(isNavItemActive(pathname, tableItem(label))).toBe(true);
  });

  it.each([
    ["LLM Servers", "/database"],
    ["LLM Servers", "/nope"],
    ["LLM Servers", "/"],
    ["Database", "/llm-servers"],
    ["Database", "/llm-servers/database"],
    ["Database", "/nope"],
    ["Database", "/"],
  ])("the %s item is not active on the unrelated path %s — DoD-1", (label, pathname) => {
    expect(isNavItemActive(pathname, tableItem(label))).toBe(false);
  });

  it("a hand-built non-exact item matches itself and its descendants only — DoD-1", () => {
    const probe = item("/alpha/beta");
    expect(isNavItemActive("/alpha/beta", probe)).toBe(true);
    expect(isNavItemActive("/alpha/beta/gamma", probe)).toBe(true);
    expect(isNavItemActive("/alpha", probe)).toBe(false);
    expect(isNavItemActive("/alpha/other", probe)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("a prefix that is not a whole segment is not a match", () => {
  it("/database-backups is not active for the Database item — DoD-2", () => {
    expect(isNavItemActive("/database-backups", tableItem("Database"))).toBe(false);
  });

  it("a descendant of /database-backups is not active for the Database item — DoD-2", () => {
    expect(isNavItemActive("/database-backups/latest", tableItem("Database"))).toBe(false);
  });

  it("/databases is not active for the Database item — DoD-2", () => {
    expect(isNavItemActive("/databases", tableItem("Database"))).toBe(false);
  });

  it("the other direction: /database is not active for a /database-backups item — DoD-2", () => {
    const backups = item("/database-backups", false, "Backups");
    expect(isNavItemActive("/database", backups)).toBe(false);
    expect(isNavItemActive("/database/", backups)).toBe(false);
    // and the item still matches its own path, so the false above is not a blanket false
    expect(isNavItemActive("/database-backups", backups)).toBe(true);
  });

  it("/llm-servers-old is not active for the LLM Servers item — DoD-2", () => {
    expect(isNavItemActive("/llm-servers-old", tableItem("LLM Servers"))).toBe(false);
  });
});

// ---------------------------------------------------------------------------
describe("the root item is matched exactly", () => {
  it("/ is active for the Users item — DoD-3", () => {
    expect(isNavItemActive("/", tableItem("Users"))).toBe(true);
  });

  it.each(["/llm-servers", "/database", "/llm-servers/anything", "/database/tables", "/nope"])(
    "%s is not active for the Users item — DoD-3",
    (pathname) => {
      expect(isNavItemActive(pathname, tableItem("Users"))).toBe(false);
    },
  );

  it("an exact hand-built item does not match its descendants — DoD-3", () => {
    const exactItem = item("/alpha", true);
    expect(isNavItemActive("/alpha", exactItem)).toBe(true);
    expect(isNavItemActive("/alpha/", exactItem)).toBe(true);
    expect(isNavItemActive("/alpha/beta", exactItem)).toBe(false);
  });

  it("the same path without the exact flag does match its descendants — DoD-3", () => {
    expect(isNavItemActive("/alpha/beta", item("/alpha", false))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
describe("a pure function of two plain arguments, and the three declared items", () => {
  it("returns a boolean for plain arguments, with no router and no render — DoD-4", () => {
    const results = [
      isNavItemActive("/", { label: "Users", path: "/", icon: NoIcon, exact: true }),
      isNavItemActive("/x", { label: "X", path: "/x", icon: NoIcon, exact: false }),
      isNavItemActive("/y", { label: "X", path: "/x", icon: NoIcon, exact: false }),
    ];
    expect(results).toEqual([true, true, false]);
    for (const result of results) expect(typeof result).toBe("boolean");
  });

  it("is repeatable and does not modify its item (frozen items are accepted) — DoD-4", () => {
    const frozen = item("/llm-servers");
    const snapshot = { ...frozen };
    expect(isNavItemActive("/llm-servers/a", frozen)).toBe(true);
    expect(isNavItemActive("/llm-servers/a", frozen)).toBe(true);
    expect(isNavItemActive("/database", frozen)).toBe(false);
    expect({ ...frozen }).toEqual(snapshot);
  });

  it("the nav module imports no router and no DOM renderer — DoD-4", () => {
    const source = stripComments(readFileSync(NAV_ITEMS_SOURCE, "utf8"));
    expect(source).not.toMatch(/["']react-router(?:-dom)?["']/);
    expect(source).not.toMatch(/["']react-dom(?:\/[^"']*)?["']/);
  });

  it("the table declares exactly three items, in order, with their labels and paths — DoD-4", () => {
    expect(NAV_ITEMS.map((entry) => ({ label: entry.label, path: entry.path }))).toEqual([
      { label: "Users", path: "/" },
      { label: "LLM Servers", path: "/llm-servers" },
      { label: "Database", path: "/database" },
    ]);
  });

  it("the root item carries the exact flag and the other two do not — DoD-4", () => {
    expect(NAV_ITEMS.map((entry) => [entry.path, entry.exact])).toEqual([
      ["/", true],
      ["/llm-servers", false],
      ["/database", false],
    ]);
  });

  it("each item carries its Tabler icon — DoD-4", () => {
    expect(NAV_ITEMS.map((entry) => entry.icon)).toEqual([IconUsers, IconServer2, IconDatabase]);
  });
});
