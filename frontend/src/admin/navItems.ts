// The admin nav: a static declaration table and its pure whole-segment matcher.
import type * as React from "react";
import { IconDatabase, IconServer2, IconUsers } from "@tabler/icons-react";

export type NavItem = {
  label: string;
  path: string;
  icon: React.ComponentType<{ size?: number | string; stroke?: number }>;
  exact: boolean;
};

export const NAV_ITEMS: readonly NavItem[] = [
  { label: "Users", path: "/", icon: IconUsers, exact: true },
  { label: "LLM Servers", path: "/llm-servers", icon: IconServer2, exact: false },
  { label: "Database", path: "/database", icon: IconDatabase, exact: false },
];

/** Pure: whole-`/`-segment match; `exact` items match only their own path. */
export function isNavItemActive(pathname: string, item: NavItem): boolean {
  const current = normalizePath(pathname);
  const target = normalizePath(item.path);
  if (current === target) {
    return true;
  }
  if (item.exact) {
    return false;
  }
  const prefix = target === "/" ? "/" : `${target}/`;
  return current.startsWith(prefix);
}

function normalizePath(path: string): string {
  const trimmed = path.replace(/\/+$/, "");
  return trimmed === "" ? "/" : trimmed;
}
