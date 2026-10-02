// Feature 009, step 005 — the shared markdown editor (DoD-1..DoD-5).
// DoD-6 (real typing / toolbar use calls onChange with markdown, and a save+reload
// round-trip) and DoD-7 (`npm run build` with the new dependencies, toolbar styled)
// are [manual/live] and have no test here: jsdom has no layout and only partial
// contenteditable / selection support, so driving ProseMirror through user-event is
// unreliable (context.md "TipTap in jsdom", 005.context.md "jsdom specifics").
//
// Expected behaviour comes from the step's Interface intent and Definition of done:
// a labelled textbox surface, markdown parsed in and rendered as real DOM, no onChange
// echo on mount or on an external `value`, and readOnly meaning "no toolbar, not
// editable". Bound to the frozen interface:
//   MarkdownEditorProps = { label; value; onChange(markdown); readOnly? }
//   export function MarkdownEditor(props): React.JSX.Element
//
// Recognition conventions: the editable surface is the element with role="textbox"
// and the `label` as its accessible name; ProseMirror renders the document as real
// DOM (h2, strong, li) inside that element; `useEditor` may return null on the first
// render, so the first assertion of each test awaits (findBy… / waitFor).
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../../src/shared/AppProviders";
import { MarkdownEditor, type MarkdownEditorProps } from "../../src/shared/MarkdownEditor";

afterEach(() => {
  vi.restoreAllMocks();
});

const LABEL = "Persona";

/** DoD-2's document: a level-2 heading, a paragraph with bold, a two-item bullet list. */
const RICH_MARKDOWN = [
  "## Voice",
  "",
  "A paragraph with **bold** inside it.",
  "",
  "- first item",
  "- second item",
  "",
].join("\n");

/** DoD-3's two documents: the second must replace the first entirely. */
const FIRST_MARKDOWN = ["## Alpha heading", "", "Alpha body text.", ""].join("\n");
const SECOND_MARKDOWN = ["## Beta heading", "", "Beta body text.", ""].join("\n");

function renderEditor(props: MarkdownEditorProps) {
  const view = render(
    <AppProviders>
      <MarkdownEditor {...props} />
    </AppProviders>,
  );
  const rerenderWith = (next: MarkdownEditorProps) =>
    view.rerender(
      <AppProviders>
        <MarkdownEditor {...next} />
      </AppProviders>,
    );
  return { ...view, rerenderWith };
}

/** Lets the editor finish creating itself and any effect settle before asserting. */
async function settle(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

function surface(): HTMLElement {
  return screen.getByRole("textbox", { name: LABEL });
}

// ---------------------------------------------------------------------------
describe("the editable surface is labelled", () => {
  it("exposes a textbox whose accessible name is the label — DoD-1", async () => {
    renderEditor({ label: LABEL, value: "", onChange: vi.fn<(markdown: string) => void>() });

    expect(await screen.findByRole("textbox", { name: LABEL })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
describe("the markdown value is parsed and rendered", () => {
  it("renders the level-2 heading from the markdown — DoD-2", async () => {
    renderEditor({
      label: LABEL,
      value: RICH_MARKDOWN,
      onChange: vi.fn<(markdown: string) => void>(),
    });

    const editable = await screen.findByRole("textbox", { name: LABEL });
    await waitFor(() => {
      expect(within(editable).getByRole("heading", { level: 2, name: "Voice" })).toBeInTheDocument();
    });
  });

  it("renders a strong element reading 'bold' — DoD-2", async () => {
    renderEditor({
      label: LABEL,
      value: RICH_MARKDOWN,
      onChange: vi.fn<(markdown: string) => void>(),
    });

    const editable = await screen.findByRole("textbox", { name: LABEL });
    await waitFor(() => {
      const strongTexts = Array.from(editable.querySelectorAll("strong")).map(
        (element) => element.textContent,
      );
      expect(strongTexts).toContain("bold");
    });
  });

  it("renders the two bullet items as two list items — DoD-2", async () => {
    renderEditor({
      label: LABEL,
      value: RICH_MARKDOWN,
      onChange: vi.fn<(markdown: string) => void>(),
    });

    const editable = await screen.findByRole("textbox", { name: LABEL });
    await waitFor(() => {
      expect(within(editable).getAllByRole("listitem")).toHaveLength(2);
    });
    const itemTexts = within(editable)
      .getAllByRole("listitem")
      .map((item) => item.textContent);
    expect(itemTexts).toEqual(["first item", "second item"]);
  });
});

// ---------------------------------------------------------------------------
describe("the editor never echoes its value back", () => {
  it("does not call onChange on mount — DoD-3", async () => {
    const onChange = vi.fn<(markdown: string) => void>();
    renderEditor({ label: LABEL, value: FIRST_MARKDOWN, onChange });

    await screen.findByRole("textbox", { name: LABEL });
    await settle();

    expect(onChange).not.toHaveBeenCalled();
  });

  it("does not call onChange when a different value arrives from the parent — DoD-3", async () => {
    const onChange = vi.fn<(markdown: string) => void>();
    const { rerenderWith } = renderEditor({ label: LABEL, value: FIRST_MARKDOWN, onChange });

    await screen.findByRole("textbox", { name: LABEL });
    await settle();
    rerenderWith({ label: LABEL, value: SECOND_MARKDOWN, onChange });
    await screen.findByRole("heading", { name: "Beta heading" });
    await settle();

    expect(onChange).not.toHaveBeenCalled();
  });

  it("shows the new content and drops the old one after an external value change — DoD-3", async () => {
    const onChange = vi.fn<(markdown: string) => void>();
    const { rerenderWith } = renderEditor({ label: LABEL, value: FIRST_MARKDOWN, onChange });

    const editable = await screen.findByRole("textbox", { name: LABEL });
    await waitFor(() => {
      expect(within(editable).getByRole("heading", { name: "Alpha heading" })).toBeInTheDocument();
    });

    rerenderWith({ label: LABEL, value: SECOND_MARKDOWN, onChange });

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Beta heading" })).toBeInTheDocument();
    });
    expect(screen.queryByRole("heading", { name: "Alpha heading" })).toBeNull();
    expect(screen.queryByText("Alpha body text.")).toBeNull();
    expect(screen.getByText("Beta body text.")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
describe("readOnly hides the toolbar and locks the surface", () => {
  it("renders no button at all when readOnly is true — DoD-4", async () => {
    renderEditor({
      label: LABEL,
      value: RICH_MARKDOWN,
      onChange: vi.fn<(markdown: string) => void>(),
      readOnly: true,
    });

    await screen.findByRole("textbox", { name: LABEL });
    await settle();

    expect(screen.queryAllByRole("button")).toEqual([]);
  });

  it("marks the surface not editable when readOnly is true — DoD-4", async () => {
    renderEditor({
      label: LABEL,
      value: RICH_MARKDOWN,
      onChange: vi.fn<(markdown: string) => void>(),
      readOnly: true,
    });

    const editable = await screen.findByRole("textbox", { name: LABEL });
    await waitFor(() => {
      expect(editable).toHaveAttribute("contenteditable", "false");
    });
  });

  it("renders formatting buttons when readOnly is false — DoD-4", async () => {
    renderEditor({
      label: LABEL,
      value: RICH_MARKDOWN,
      onChange: vi.fn<(markdown: string) => void>(),
      readOnly: false,
    });

    await screen.findByRole("textbox", { name: LABEL });
    await waitFor(() => {
      expect(screen.getAllByRole("button").length).toBeGreaterThan(0);
    });
  });

  it("marks the surface editable when readOnly is false — DoD-4", async () => {
    renderEditor({
      label: LABEL,
      value: RICH_MARKDOWN,
      onChange: vi.fn<(markdown: string) => void>(),
      readOnly: false,
    });

    const editable = await screen.findByRole("textbox", { name: LABEL });
    await waitFor(() => {
      expect(editable).toHaveAttribute("contenteditable", "true");
    });
  });

  it("removes the buttons when readOnly flips from false to true — DoD-4", async () => {
    const onChange = vi.fn<(markdown: string) => void>();
    const { rerenderWith } = renderEditor({
      label: LABEL,
      value: RICH_MARKDOWN,
      onChange,
      readOnly: false,
    });

    await screen.findByRole("textbox", { name: LABEL });
    await waitFor(() => {
      expect(screen.getAllByRole("button").length).toBeGreaterThan(0);
    });

    rerenderWith({ label: LABEL, value: RICH_MARKDOWN, onChange, readOnly: true });

    await waitFor(() => {
      expect(screen.queryAllByRole("button")).toEqual([]);
    });
    expect(surface()).toHaveAttribute("contenteditable", "false");
  });
});

// ---------------------------------------------------------------------------
// DoD-5 — the dependency contract. package.json is configuration, not implementation.

const FRONTEND_ROOT = path.resolve(__dirname, "..", "..");
const PACKAGE_JSON = path.join(FRONTEND_ROOT, "package.json");

type PackageJson = {
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
};

const SIX_PACKAGES = [
  "@mantine/tiptap",
  "@tiptap/react",
  "@tiptap/pm",
  "@tiptap/starter-kit",
  "@tiptap/extension-link",
  "tiptap-markdown",
] as const;

function packageJson(): PackageJson {
  return JSON.parse(readFileSync(PACKAGE_JSON, "utf8")) as PackageJson;
}

function dependencies(): Record<string, string> {
  return packageJson().dependencies ?? {};
}

/** The major of a range like `7.17.8` or `^2.27.3`. */
function majorOf(range: string): number {
  const match = /(\d+)/.exec(range);
  return match === null ? Number.NaN : Number(match[1]);
}

/** Only generated output is exempt from the TypeScript-only rule. */
const GENERATED_DIRECTORIES = new Set(["node_modules", "dist", "coverage"]);

function authoredFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      return GENERATED_DIRECTORIES.has(entry.name) ? [] : authoredFiles(full);
    }
    return [full];
  });
}

describe("the six editor dependencies", () => {
  it.each(SIX_PACKAGES)("lists %s under dependencies — DoD-5", (name) => {
    expect(Object.keys(dependencies())).toContain(name);
  });

  it("gives @mantine/tiptap the same major as @mantine/core — DoD-5", () => {
    const deps = dependencies();
    const core = deps["@mantine/core"];
    const tiptap = deps["@mantine/tiptap"];
    expect(core).toBeDefined();
    expect(tiptap).toBeDefined();
    expect(majorOf(tiptap ?? "")).toBe(majorOf(core ?? ""));
  });

  it("keeps every @tiptap/* range on major 2 — DoD-5", () => {
    const offenders = Object.entries(dependencies())
      .filter(([name]) => name.startsWith("@tiptap/"))
      .filter(([, range]) => majorOf(range) !== 2);
    // The offending entry is the message: which package drifted off TipTap 2.
    expect(offenders).toEqual([]);
  });

  it("adds no .js / .mjs / .cjs file under frontend outside generated output — DoD-5", () => {
    const offenders = authoredFiles(FRONTEND_ROOT)
      .filter((file) => /\.(js|mjs|cjs)$/i.test(file))
      .map((file) => path.relative(FRONTEND_ROOT, file).split(path.sep).join("/"))
      .sort();
    expect(offenders).toEqual([]);
  });
});
