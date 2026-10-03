// Feature 013, step 004 — the `react-markdown` dependency and the message renderer
// (DoD-1..DoD-6).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D1 and D5:
//   - "plain" renders markdown with no painting at all;
//   - "decision" renders the out-of-character card (data-paren="ooc", label
//     "Out of character") by kind, whatever the text;
//   - "painted" renders the card for a wholly-parenthesised text, otherwise prose as markdown
//     and each fragment as an inline chip (data-paren="fragment") holding the fragment
//     verbatim, in document order; an unclosed "((" is ordinary text.
import { readFileSync } from "node:fs";
import path from "node:path";
import { render, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MessageBody, type MessageBodyVariant } from "../../src/app/MessageBody";
import { AppProviders } from "../../src/shared/AppProviders";

const FRONTEND_ROOT = path.resolve(__dirname, "..", "..");

type PackageJson = {
  dependencies?: Record<string, string>;
};

function readPackageJson(): PackageJson {
  return JSON.parse(readFileSync(path.join(FRONTEND_ROOT, "package.json"), "utf8")) as PackageJson;
}

function renderBody(text: string, variant: MessageBodyVariant): HTMLElement {
  const { container } = render(
    <AppProviders>
      <MessageBody text={text} variant={variant} />
    </AppProviders>,
  );
  return container;
}

function parenElements(root: HTMLElement, value?: "ooc" | "fragment"): Element[] {
  const selector = value === undefined ? "[data-paren]" : `[data-paren="${value}"]`;
  return Array.from(root.querySelectorAll(selector));
}

/** The first text node under `root` whose content contains `needle`. */
function textNodeContaining(root: Node, needle: string): Text | null {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node !== null) {
    if ((node.textContent ?? "").includes(needle)) return node as Text;
    node = walker.nextNode();
  }
  return null;
}

function follows(earlier: Node, later: Node): boolean {
  return (earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

describe("react-markdown dependency", () => {
  it("frontend/package.json lists react-markdown under dependencies — DoD-1", () => {
    const deps = readPackageJson().dependencies ?? {};
    expect(Object.keys(deps)).toContain("react-markdown");
    expect(typeof deps["react-markdown"]).toBe("string");
    expect((deps["react-markdown"] ?? "").length).toBeGreaterThan(0);
  });
});

describe("MessageBody — plain", () => {
  it("renders markdown: **bold** becomes a strong element containing the word — DoD-2", () => {
    const root = renderBody("Some **bold** text", "plain");

    const strong = root.querySelector("strong");
    expect(strong).not.toBeNull();
    expect(strong?.textContent).toBe("bold");
    expect(root.textContent).toContain("Some");
    expect(root.textContent).toContain("text");
    expect(root.textContent).not.toContain("**");
  });

  it("paints nothing: ((hi)) stays ordinary text with no data-paren element — DoD-2", () => {
    const root = renderBody("She said ((hi))", "plain");

    expect(parenElements(root)).toEqual([]);
    expect(root.textContent).toContain("She said ((hi))");
  });
});

describe("MessageBody — painted", () => {
  it("renders exactly one fragment chip holding ((make it tense)) between the two prose sentences — DoD-3", () => {
    const root = renderBody("She walks. ((make it tense)) He waits.", "painted");

    expect(parenElements(root, "ooc")).toEqual([]);
    const chips = parenElements(root, "fragment");
    expect(chips).toHaveLength(1);
    const chip = chips[0] as Element;
    expect(chip.textContent).toBe("((make it tense))");

    const before = textNodeContaining(root, "She walks.");
    const after = textNodeContaining(root, "He waits.");
    expect(before).not.toBeNull();
    expect(after).not.toBeNull();
    expect(chip.contains(before as Node)).toBe(false);
    expect(chip.contains(after as Node)).toBe(false);

    expect(follows(before as Node, chip)).toBe(true);
    expect(follows(chip, after as Node)).toBe(true);
  });

  it("renders a wholly-parenthesised text as the out-of-character card, with no fragment chips — DoD-4", () => {
    const root = renderBody("((one)) and ((two))", "painted");

    const cards = parenElements(root, "ooc");
    expect(cards).toHaveLength(1);
    const card = cards[0] as HTMLElement;
    expect(within(card).getByText("Out of character")).toBeInTheDocument();
    expect(card.textContent).toContain("((one)) and ((two))");

    expect(parenElements(root, "fragment")).toEqual([]);
  });

  it("treats an unclosed (( as ordinary text: no data-paren element, text shown as is — DoD-5", () => {
    const root = renderBody("(( never closed", "painted");

    expect(parenElements(root)).toEqual([]);
    expect(root.textContent).toContain("(( never closed");
  });
});

describe("MessageBody — decision", () => {
  it("renders the out-of-character card for text with no parentheses — DoD-6", () => {
    const root = renderBody("plain words", "decision");

    const cards = parenElements(root, "ooc");
    expect(cards).toHaveLength(1);
    const card = cards[0] as HTMLElement;
    expect(within(card).getByText("Out of character")).toBeInTheDocument();
    expect(card.textContent).toContain("plain words");
    expect(parenElements(root, "fragment")).toEqual([]);
  });
});
