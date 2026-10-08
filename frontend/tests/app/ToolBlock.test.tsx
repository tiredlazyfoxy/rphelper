// Feature 022, step 004 — the collapsible tool block (DoD-4..DoD-6).
//
// Expected behaviour comes from the step file's Interface intent and Definition of done plus
// context.md's D3, D5, D7 and the UI strings table:
//   - a header with the toggle "Show tool call" (collapsed) / "Hide tool call" (open), the tool
//     name (or "Unknown tool" when null or absent) and a status word: "Running", "Done" (ok)
//     or "Failed";
//   - when open, "Arguments", then the arguments as JSON.stringify(args, null, 2) or
//     "No arguments." for an object with no keys, then the summary when non-null;
//   - when collapsed, the body is not rendered (absence, D5);
//   - the open flag is initialised once; a status change while mounted does not change it.
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";
import { ToolBlock, type ToolBlockProps } from "../../src/app/ToolBlock";
import { AppProviders } from "../../src/shared/AppProviders";

const QUERY_PAIR = '"query": "lighthouse"';
const LIGHTHOUSE_ARGS = { query: "lighthouse" };
const PRETTY_LIGHTHOUSE = JSON.stringify(LIGHTHOUSE_ARGS, null, 2);

function tree(props: ToolBlockProps): ReactElement {
  return (
    <AppProviders>
      <ToolBlock {...props} />
    </AppProviders>
  );
}

describe("ToolBlock — collapsed start, then opened", () => {
  it("collapsed header shows memo_search, Done and a Show tool call button, with no arguments or summary — DoD-4", () => {
    const { container } = render(
      tree({
        name: "memo_search",
        status: "ok",
        args: LIGHTHOUSE_ARGS,
        summary: "Found 2 memos.",
        startsOpen: false,
      }),
    );

    expect(screen.getByText("memo_search")).toBeInTheDocument();
    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show tool call" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hide tool call" })).toBeNull();

    expect(container.textContent ?? "").not.toContain(QUERY_PAIR);
    expect(screen.queryByText("Found 2 memos.")).toBeNull();
    expect(container.textContent ?? "").not.toContain("Found 2 memos.");
    expect(screen.queryByText("Arguments")).toBeNull();
  });

  it("pressing Show tool call shows Arguments, the pretty-printed arguments and the summary — DoD-4", () => {
    const { container } = render(
      tree({
        name: "memo_search",
        status: "ok",
        args: LIGHTHOUSE_ARGS,
        summary: "Found 2 memos.",
        startsOpen: false,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Show tool call" }));

    expect(screen.getByText("Arguments")).toBeInTheDocument();
    const text = container.textContent ?? "";
    expect(text).toContain(QUERY_PAIR);
    expect(text).toContain(PRETTY_LIGHTHOUSE);
    expect(screen.getByText("Found 2 memos.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide tool call" })).toBeInTheDocument();
  });
});

describe("ToolBlock — open start and a live status change", () => {
  it("starts open while running: Running, the arguments and a Hide tool call button on first render — DoD-5", () => {
    const { container } = render(
      tree({
        name: "memo_search",
        status: "running",
        args: LIGHTHOUSE_ARGS,
        summary: null,
        startsOpen: true,
      }),
    );

    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("Arguments")).toBeInTheDocument();
    expect(container.textContent ?? "").toContain(PRETTY_LIGHTHOUSE);
    expect(screen.getByRole("button", { name: "Hide tool call" })).toBeInTheDocument();
  });

  it("re-rendered with status ok and a summary, it stays open, shows Done and the summary — DoD-5", () => {
    const { container, rerender } = render(
      tree({
        name: "memo_search",
        status: "running",
        args: LIGHTHOUSE_ARGS,
        summary: null,
        startsOpen: true,
      }),
    );

    rerender(
      tree({
        name: "memo_search",
        status: "ok",
        args: LIGHTHOUSE_ARGS,
        summary: "Found 2 memos.",
        startsOpen: true,
      }),
    );

    expect(screen.getByRole("button", { name: "Hide tool call" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show tool call" })).toBeNull();
    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.queryByText("Running")).toBeNull();
    expect(screen.getByText("Found 2 memos.")).toBeInTheDocument();
    expect(container.textContent ?? "").toContain(PRETTY_LIGHTHOUSE);
  });
});

describe("ToolBlock — failed, unnamed, no arguments", () => {
  it("opened, a failed call with name null and args {} shows Failed, Unknown tool, No arguments. and its summary — DoD-6", () => {
    render(
      tree({
        name: null,
        status: "failed",
        args: {},
        summary: "The tool failed.",
        startsOpen: false,
      }),
    );

    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Unknown tool")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show tool call" }));

    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Unknown tool")).toBeInTheDocument();
    expect(screen.getByText("No arguments.")).toBeInTheDocument();
    expect(screen.getByText("The tool failed.")).toBeInTheDocument();
  });

  it("an absent tool name also reads Unknown tool — DoD-6", () => {
    render(
      tree({
        status: "failed",
        args: {},
        summary: "The tool failed.",
        startsOpen: true,
      }),
    );

    expect(screen.getByText("Unknown tool")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("No arguments.")).toBeInTheDocument();
    expect(screen.getByText("The tool failed.")).toBeInTheDocument();
  });
});
