// Step 002/001 — the Vitest harness is live (DoD-6).
import { describe, expect, it } from "vitest";

describe("test harness", () => {
  it("provides a writable, readable DOM document (DoD-6)", () => {
    expect(typeof document).toBe("object");
    const el = document.createElement("div");
    el.id = "harness-probe";
    el.textContent = "hello harness";
    document.body.appendChild(el);

    const found = document.getElementById("harness-probe");
    expect(found).not.toBeNull();
    expect(found?.textContent).toBe("hello harness");
  });

  it("has @testing-library/jest-dom matchers registered on expect (DoD-6)", () => {
    const el = document.createElement("p");
    el.textContent = "matcher probe";
    document.body.appendChild(el);

    expect(el).toBeInTheDocument();
    expect(el).toHaveTextContent("matcher probe");

    el.remove();
    expect(el).not.toBeInTheDocument();
  });
});
