// Feature 014, step 003 — notifyWarning, the second notification outlet (DoD-4).
//
// Expected values come from the step's Definition of done, context.md D4 and the UI strings
// table: one `notifications.show` call per warning, message exactly the paste sentence,
// colour "yellow" (never failure red). The identifier set is closed — no free text.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { notifyWarning } from "../../src/shared/notifyWarning";

const showSpy = vi.hoisted(() => vi.fn<(data: unknown) => string>(() => "notification-id"));

vi.mock("@mantine/notifications", async (importOriginal) => {
  const original = await importOriginal<typeof import("@mantine/notifications")>();
  return {
    ...original,
    notifications: { ...original.notifications, show: showSpy },
  };
});

const PASTE_SENTENCE = "This paste is very large and will take up a lot of the assistant's context.";

beforeEach(() => {
  showSpy.mockClear();
});

function onlyShowArgument(): Record<string, unknown> {
  expect(showSpy).toHaveBeenCalledTimes(1);
  const [data] = showSpy.mock.calls[0] ?? [];
  expect(data).toBeTypeOf("object");
  return data as Record<string, unknown>;
}

describe("notifyWarning — the paste context-cost warning (D4, US-035.AC-1)", () => {
  it("calls notifications.show exactly once — DoD-4", () => {
    notifyWarning("paste-context-cost");

    expect(showSpy).toHaveBeenCalledTimes(1);
  });

  it("the message is exactly the paste sentence — DoD-4", () => {
    notifyWarning("paste-context-cost");

    expect(onlyShowArgument().message).toBe(PASTE_SENTENCE);
  });

  it('the colour is "yellow", never "red" — DoD-4', () => {
    notifyWarning("paste-context-cost");

    const data = onlyShowArgument();
    expect(data.color).toBe("yellow");
    expect(data.color).not.toBe("red");
  });

  it("returns nothing — DoD-4", () => {
    const result: unknown = notifyWarning("paste-context-cost");

    expect(result).toBeUndefined();
  });

  it("each call raises its own single notification — DoD-4", () => {
    notifyWarning("paste-context-cost");
    notifyWarning("paste-context-cost");

    expect(showSpy).toHaveBeenCalledTimes(2);
    for (const [data] of showSpy.mock.calls) {
      expect((data as Record<string, unknown>).message).toBe(PASTE_SENTENCE);
      expect((data as Record<string, unknown>).color).toBe("yellow");
    }
  });

  it("the identifier set is closed: free text is rejected at compile time — DoD-4", () => {
    // Checked by `npm run typecheck`; never executed.
    void (() => {
      // @ts-expect-error — notifyWarning takes an identifier from a closed set, not free text (DoD-4)
      notifyWarning("Something went fine!");
    });
    expect(showSpy).not.toHaveBeenCalled();
  });
});
