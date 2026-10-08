// Feature 002, step 005 — notifyFailure, the failure-reason channel (DoD-12..DoD-15).
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { notifications } from "@mantine/notifications";
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ApiError } from "../../src/shared/apiError";
import { AppProviders } from "../../src/shared/AppProviders";
import * as notifyFailureModule from "../../src/shared/notifyFailure";
import { notifyFailure } from "../../src/shared/notifyFailure";

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const SRC_ROOT = path.join(FRONTEND_ROOT, "src");
const NOTIFICATION_ROOT = ".mantine-Notification-root";

function renderOutlet() {
  return render(
    <AppProviders>
      <span>page</span>
    </AppProviders>,
  );
}

function notificationRoots(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>(NOTIFICATION_ROOT));
}

/** Red is Mantine's `red` palette colour, carried on the notification's own markup. */
function expectRed(root: HTMLElement): void {
  const own = root.cloneNode(false) as HTMLElement;
  expect(own.outerHTML).toMatch(/\bred\b/);
}

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    return /\.(ts|tsx)$/.test(entry.name) ? [full] : [];
  });
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  act(() => {
    notifications.clean();
  });
});

// ---------------------------------------------------------------------------
describe("given an ApiError", () => {
  it("shows a notification carrying the error's message — DoD-12", async () => {
    renderOutlet();
    act(() => {
      notifyFailure(new ApiError("llm_unreachable", "The model server did not answer.", 502));
    });
    const text = await screen.findByText("The model server did not answer.", { exact: false });
    expect(text.closest(NOTIFICATION_ROOT)).not.toBeNull();
  });

  it("the notification is red — DoD-12", async () => {
    renderOutlet();
    act(() => {
      notifyFailure(new ApiError("tool_failed", "The lookup tool gave up.", 500));
    });
    const text = await screen.findByText("The lookup tool gave up.", { exact: false });
    const root = text.closest<HTMLElement>(NOTIFICATION_ROOT);
    expect(root).not.toBeNull();
    expectRed(root as HTMLElement);
  });

  it("carries each error's own message — DoD-12", async () => {
    renderOutlet();
    act(() => {
      notifyFailure(new ApiError("model_not_enabled", "That model is not enabled.", 409));
      notifyFailure(new ApiError("translation_failed", "Translation could not complete.", 502));
    });
    expect(await screen.findByText("That model is not enabled.", { exact: false })).toBeInTheDocument();
    expect(
      await screen.findByText("Translation could not complete.", { exact: false }),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
describe("given a non-ApiError thrown value", () => {
  const NON_API_VALUES: Array<[string, unknown]> = [
    ["a plain Error", new Error("internal-detail-zq41")],
    ["a TypeError", new TypeError("internal-detail-zq42")],
    ["a string", "internal-detail-zq43"],
    ["undefined", undefined],
    ["null", null],
    ["a plain object", { code: "internal-detail-zq44", message: "internal-detail-zq45" }],
  ];

  it.each(NON_API_VALUES)("%s does not throw — DoD-13", (_name, value) => {
    renderOutlet();
    expect(() => {
      act(() => {
        notifyFailure(value);
      });
    }).not.toThrow();
  });

  it.each(NON_API_VALUES)(
    "%s shows a red notification with a non-empty generic reason — DoD-13",
    async (_name, value) => {
      renderOutlet();
      act(() => {
        notifyFailure(value);
      });
      await waitFor(() => expect(notificationRoots().length).toBe(1));
      const root = notificationRoots()[0];
      expect((root.textContent ?? "").trim().length).toBeGreaterThan(0);
      expect(root.textContent).not.toMatch(/internal-detail-zq4\d/);
      expectRed(root);
    },
  );

  it("every non-ApiError value gets the same generic reason — DoD-13", async () => {
    renderOutlet();
    act(() => {
      notifyFailure(new Error("internal-detail-zq41"));
      notifyFailure("internal-detail-zq43");
      notifyFailure(undefined);
    });
    await waitFor(() => expect(notificationRoots().length).toBe(3));
    const texts = notificationRoots().map((root) => (root.textContent ?? "").trim());
    expect(new Set(texts).size).toBe(1);
  });

  it("the generic reason is not an ApiError's message — DoD-13", async () => {
    renderOutlet();
    act(() => {
      notifyFailure(new Error("internal-detail-zq41"));
      notifyFailure(new ApiError("llm_unreachable", "The model server did not answer.", 502));
    });
    await waitFor(() => expect(notificationRoots().length).toBe(2));
    const texts = notificationRoots().map((root) => (root.textContent ?? "").trim());
    expect(texts[0]).not.toBe(texts[1]);
  });
});

// ---------------------------------------------------------------------------
describe("no success path by construction", () => {
  it("notifyFailure is the module's only export — DoD-14", () => {
    expect(Object.keys(notifyFailureModule)).toEqual(["notifyFailure"]);
  });

  it("declares exactly one parameter, the thrown value — DoD-14", () => {
    expect(typeof notifyFailure).toBe("function");
    expect(notifyFailure.length).toBe(1);
  });

  it("returns nothing — DoD-14", () => {
    renderOutlet();
    let result: unknown = "sentinel";
    act(() => {
      result = notifyFailure(new ApiError("tool_failed", "The lookup tool gave up.", 500));
    });
    expect(result).toBeUndefined();
  });

  it("an extra colour/success argument cannot change the notification — DoD-14", async () => {
    renderOutlet();
    const loose = notifyFailure as unknown as (...args: unknown[]) => void;
    act(() => {
      loose(new ApiError("tool_failed", "The lookup tool gave up.", 500), "green", {
        color: "green",
        success: true,
      });
    });
    const text = await screen.findByText("The lookup tool gave up.", { exact: false });
    const root = text.closest<HTMLElement>(NOTIFICATION_ROOT);
    expect(root).not.toBeNull();
    expectRed(root as HTMLElement);
    const own = (root as HTMLElement).cloneNode(false) as HTMLElement;
    expect(own.outerHTML).not.toMatch(/green/);
  });

  it("the signature rejects a second argument at compile time — DoD-14", () => {
    // Checked by `npm run typecheck`; never executed.
    void (() => {
      // @ts-expect-error — notifyFailure takes only the thrown value (DoD-14)
      notifyFailure(new Error("x"), { color: "green" });
    });
    expect(notifyFailure.length).toBe(1);
  });
});

// ---------------------------------------------------------------------------
describe("the single call site for Mantine's notification API", () => {
  const EXEMPT = path.join(SRC_ROOT, "shared", "notifyFailure.ts");

  const FORBIDDEN: Array<[string, RegExp]> = [
    ["notifications.<store call>", /\bnotifications\s*\??\.\s*(show|hide|update|clean|cleanQueue|updateState)\b/],
    [
      "legacy notification function",
      /\b(showNotification|hideNotification|updateNotification|cleanNotifications|cleanNotificationsQueue)\b/,
    ],
    ["notifications store", /\b(notificationsStore|createNotificationsStore|useNotifications)\b/],
    [
      "imports the notifications store API",
      /import\s*(type\s+)?\{[^}]*\bnotifications\b[^}]*\}\s*from\s*["']@mantine\/notifications["']/,
    ],
    ["namespace import of @mantine/notifications", /import\s*\*\s*as\s+\w+\s+from\s*["']@mantine\/notifications["']/],
  ];

  it("notifyFailure.ts exists under src/shared — DoD-15", () => {
    expect(sourceFiles(SRC_ROOT)).toContain(EXEMPT);
  });

  // Amended by feature 014, step 003 (D4): the allowed set is exactly the two sanctioned
  // outlets; any third caller fails. Keeps 002/005's DoD-15 suffix and adds 014/003's DoD-5.
  it("no file under frontend/src but shared/notifyFailure.ts and shared/notifyWarning.ts calls Mantine's notification API — DoD-15, DoD-5", () => {
    const allowed = new Set([EXEMPT, path.join(SRC_ROOT, "shared", "notifyWarning.ts")]);
    const files = sourceFiles(SRC_ROOT).filter((file) => !allowed.has(file));
    expect(files.length).toBeGreaterThan(0);
    const offenders: string[] = [];
    for (const file of files) {
      const source = stripComments(readFileSync(file, "utf8"));
      for (const [name, pattern] of FORBIDDEN) {
        if (pattern.test(source)) {
          offenders.push(`${path.relative(FRONTEND_ROOT, file)} (${name})`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
