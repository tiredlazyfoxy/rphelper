// Feature 022, step 004 — the assistant body over splitThinking (DoD-7..DoD-10).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D4 worked examples, D5 and the UI strings table:
//   - the segments of splitThinking(text) render in order: each think segment as a thinking
//     block that starts open iff `live`, each answer segment through 013's MessageBody
//     variant "painted";
//   - a text with no think block renders exactly as MessageBody painted renders it (D4 row 1);
//   - a stray </think> is literal answer text, so it draws no thinking toggle (D4 row 7);
//   - a wholly-parenthesised answer is 013's out-of-character card (D4 row 8, 013 D5).
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AssistantBody } from "../../src/app/AssistantBody";
import { MessageBody } from "../../src/app/MessageBody";
import { AppProviders } from "../../src/shared/AppProviders";

function renderAssistant(text: string, live: boolean): HTMLElement {
  const { container } = render(
    <AppProviders>
      <AssistantBody text={text} live={live} />
    </AppProviders>,
  );
  return container;
}

/** The text content MessageBody "painted" produces for `text`, rendered in isolation. */
function paintedTextContent(text: string): string {
  const { container, unmount } = render(
    <AppProviders>
      <MessageBody text={text} variant="painted" />
    </AppProviders>,
  );
  const content = container.textContent ?? "";
  unmount();
  return content;
}

function precedes(earlier: Node, later: Node): boolean {
  return (earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

function thinkingToggles(): HTMLElement[] {
  return [
    ...screen.queryAllByRole("button", { name: "Show thinking" }),
    ...screen.queryAllByRole("button", { name: "Hide thinking" }),
  ];
}

describe("AssistantBody — one think block then an answer (D4 row 3)", () => {
  it("not live: Hello is shown, the thinking is collapsed behind Show thinking and plan is absent — DoD-7", () => {
    renderAssistant("<think>plan</think>\n\nHello", false);

    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show thinking" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hide thinking" })).toBeNull();
    expect(screen.queryByText("plan")).toBeNull();
  });

  it("live: plan and Hello are both visible and Hide thinking is present — DoD-7", () => {
    renderAssistant("<think>plan</think>\n\nHello", true);

    expect(screen.getByText("plan")).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide thinking" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show thinking" })).toBeNull();
  });
});

describe("AssistantBody — two think blocks interleaved with answers (D4 row 4)", () => {
  it("renders two Show thinking toggles and the answers One and two, all in segment order — DoD-8", () => {
    renderAssistant("<think>a</think>One<think>b</think> two", false);

    const toggles = screen.getAllByRole("button", { name: "Show thinking" });
    expect(toggles).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Hide thinking" })).toBeNull();

    const one = screen.getByText("One");
    const two = screen.getByText("two");
    const [firstToggle, secondToggle] = toggles as [HTMLElement, HTMLElement];

    expect(precedes(firstToggle, one)).toBe(true);
    expect(precedes(one, secondToggle)).toBe(true);
    expect(precedes(secondToggle, two)).toBe(true);
    expect(precedes(one, two)).toBe(true);

    expect(screen.queryByText("a")).toBeNull();
    expect(screen.queryByText("b")).toBeNull();
  });
});

describe("AssistantBody — an out-of-character answer after thinking (D4 row 8)", () => {
  it("renders the answer ((ooc)) as 013's out-of-character card — DoD-9", () => {
    const container = renderAssistant("<think>x\ny</think>\n((ooc))", false);

    const cards = Array.from(container.querySelectorAll('[data-paren="ooc"]'));
    expect(cards).toHaveLength(1);
    const card = cards[0] as HTMLElement;
    expect(within(card).getByText("Out of character")).toBeInTheDocument();
    expect(card.textContent ?? "").toContain("((ooc))");

    expect(screen.getByRole("button", { name: "Show thinking" })).toBeInTheDocument();
  });
});

describe("AssistantBody — no think block (D4 rows 1 and 7)", () => {
  it("Hello renders with no thinking toggle, exactly as MessageBody painted renders it — DoD-10", () => {
    const expected = paintedTextContent("Hello");
    const container = renderAssistant("Hello", false);

    expect(thinkingToggles()).toEqual([]);
    expect(screen.queryByText("Thinking")).toBeNull();
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(container.textContent ?? "").toBe(expected);
  });

  it("a stray </think> draws no thinking toggle and the text renders as MessageBody painted renders it — DoD-10", () => {
    const expected = paintedTextContent("a </think> b");
    const container = renderAssistant("a </think> b", false);

    expect(thinkingToggles()).toEqual([]);
    expect(screen.queryByText("Thinking")).toBeNull();
    const text = container.textContent ?? "";
    expect(text).toBe(expected);
    expect(text).toContain("a");
    expect(text).toContain("b");
  });

  it("with live true, a text with no think block still draws no thinking toggle — DoD-10", () => {
    renderAssistant("Hello", true);

    expect(thinkingToggles()).toEqual([]);
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });
});
