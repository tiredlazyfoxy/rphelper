// Feature 022, step 004 — the collapsible thinking block (DoD-1..DoD-3).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D5 and the UI strings table:
//   - a header with the toggle "Show thinking" (collapsed) / "Hide thinking" (open) and the
//     label "Thinking";
//   - when open, the think text verbatim as plain text: no markdown, no (( )) painting;
//   - when collapsed, the text is not rendered at all (absence, D5);
//   - the open flag starts from the `startsOpen` prop and pressing the toggle flips it.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThinkingBlock } from "../../src/app/ThinkingBlock";
import { AppProviders } from "../../src/shared/AppProviders";

function renderBlock(text: string, startsOpen: boolean): HTMLElement {
  const { container } = render(
    <AppProviders>
      <ThinkingBlock text={text} startsOpen={startsOpen} />
    </AppProviders>,
  );
  return container;
}

describe("ThinkingBlock — collapsed start", () => {
  it("starts collapsed: a Show thinking button and the Thinking label, with the text absent — DoD-1", () => {
    renderBlock("plan", false);

    expect(screen.getByRole("button", { name: "Show thinking" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hide thinking" })).toBeNull();
    expect(screen.getByText("Thinking")).toBeInTheDocument();
    expect(screen.queryByText("plan")).toBeNull();
  });

  it("pressing Show thinking reveals the text and relabels the toggle; pressing again removes it — DoD-1", () => {
    renderBlock("plan", false);

    fireEvent.click(screen.getByRole("button", { name: "Show thinking" }));

    expect(screen.getByText("plan")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide thinking" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show thinking" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Hide thinking" }));

    expect(screen.queryByText("plan")).toBeNull();
    expect(screen.getByRole("button", { name: "Show thinking" })).toBeInTheDocument();
    expect(screen.getByText("Thinking")).toBeInTheDocument();
  });
});

describe("ThinkingBlock — open start", () => {
  it("starts open: the text and a Hide thinking button on first render — DoD-2", () => {
    renderBlock("plan", true);

    expect(screen.getByText("plan")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide thinking" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show thinking" })).toBeNull();
    expect(screen.getByText("Thinking")).toBeInTheDocument();
  });
});

describe("ThinkingBlock — verbatim text", () => {
  it("renders **bold** ((x)) as that literal string, with no strong element and no fragment chip — DoD-3", () => {
    const container = renderBlock("**bold** ((x))", true);

    expect(screen.getByText("**bold** ((x))")).toBeInTheDocument();
    expect(container.querySelector("strong")).toBeNull();
    expect(container.querySelector("[data-paren]")).toBeNull();
  });
});
