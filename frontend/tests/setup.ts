// Vitest setup module — test-harness source (context.md D12), not a test.
// Registers jest-dom's matchers on Vitest's `expect` (the `/vitest` entry also
// supplies the matcher types) and unmounts Testing Library renders after each test.
// No fetch stub and no mock registry live here; tests that need them own them.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});

// Minimal jsdom gaps that Mantine 7 relies on. jsdom implements none of these, and
// Mantine calls them while rendering (color-scheme / media-query hooks, ScrollArea
// and floating layers). Each is installed only when absent, and is inert.
if (typeof window.matchMedia !== "function") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string): MediaQueryList => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

if (typeof globalThis.ResizeObserver !== "function") {
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  globalThis.ResizeObserver = ResizeObserverStub;
}

if (typeof Element.prototype.scrollIntoView !== "function") {
  Element.prototype.scrollIntoView = () => {};
}
