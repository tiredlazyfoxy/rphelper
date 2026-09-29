// Feature 002, step 003 — the shared IconButton and the icon sizing convention (DoD-1..DoD-8).
// DoD-9 and DoD-10 are [manual/live] and have no test here.
import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode, SVGProps } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { IconButton, type IconButtonProps } from "../../src/shared/IconButton";

// ---------------------------------------------------------------------------
// Test double for the `icon` prop: records every props object it is rendered
// with, and renders an inspectable <svg>. Any prop beyond size/stroke is
// spread onto the <svg>, so a colour handed to the icon would surface on the
// icon element itself.
// ---------------------------------------------------------------------------
let received: Array<Record<string, unknown>> = [];

function ProbeIcon(props: { size?: number | string; stroke?: number }) {
  const all = { ...(props as Record<string, unknown>) };
  received.push(all);
  const { size, stroke, ...rest } = all;
  return (
    <svg
      {...(rest as unknown as SVGProps<SVGSVGElement>)}
      data-testid="probe-icon"
      data-size={String(size)}
      data-stroke={String(stroke)}
    />
  );
}

function lastIconProps(): Record<string, unknown> {
  expect(received.length).toBeGreaterThan(0);
  return received[received.length - 1];
}

function Wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider>{children}</MantineProvider>;
}

type Overrides = Partial<IconButtonProps>;

function renderIconButton(overrides: Overrides = {}, extra?: { before?: ReactNode; after?: ReactNode }) {
  const onClick = overrides.onClick ?? vi.fn<() => void>();
  const props: IconButtonProps = {
    icon: ProbeIcon,
    label: "Archive session",
    ...overrides,
    onClick,
  };
  const result = render(
    <>
      {extra?.before}
      <IconButton {...props} />
      {extra?.after}
    </>,
    { wrapper: Wrapper },
  );
  return { ...result, props, onClick };
}

beforeEach(() => {
  received = [];
});

// ---------------------------------------------------------------------------
describe("accessible name", () => {
  it("renders a button whose accessible name equals the label prop — DoD-1", () => {
    renderIconButton({ label: "Archive session" });
    const button = screen.getByRole("button", { name: "Archive session" });
    expect(button).toHaveAccessibleName("Archive session");
  });

  it("follows the label prop for a different label — DoD-1", () => {
    renderIconButton({ label: "Collapse notes rail" });
    const button = screen.getByRole("button");
    expect(button).toHaveAccessibleName("Collapse notes rail");
  });
});

// ---------------------------------------------------------------------------
describe("tooltip and accessible name share one source", () => {
  it("shows the label as tooltip text on hover, equal to the accessible name — DoD-2", async () => {
    const user = userEvent.setup();
    const label = "Regenerate reply draft";
    renderIconButton({ label });

    const button = screen.getByRole("button");
    expect(button).toHaveAccessibleName(label);

    await user.hover(button);
    const tip = await screen.findByText(label);
    expect(tip.textContent).toBe(label);
    // The tooltip content lives outside the button's own subtree.
    expect(button.contains(tip)).toBe(false);
  });

  it("tooltip text tracks a different label, still equal to the accessible name — DoD-2", async () => {
    const user = userEvent.setup();
    const label = "Copy to clipboard";
    renderIconButton({ label });

    const button = screen.getByRole("button");
    await user.hover(button);
    const tip = await screen.findByText(label);
    expect(button.contains(tip)).toBe(false);
    expect(button).toHaveAccessibleName(tip.textContent ?? "");
  });
});

// ---------------------------------------------------------------------------
describe("activation", () => {
  it("invokes onClick when the control is clicked — DoD-3", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn<() => void>();
    renderIconButton({ onClick });

    await user.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("invokes onClick once per activation — DoD-3", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn<() => void>();
    renderIconButton({ onClick });

    const button = screen.getByRole("button");
    await user.click(button);
    await user.click(button);
    expect(onClick).toHaveBeenCalledTimes(2);
  });
});

// ---------------------------------------------------------------------------
describe("disabled", () => {
  it("is disabled when disabled is set — DoD-4", () => {
    renderIconButton({ disabled: true });
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("does not invoke onClick when a disabled control is activated — DoD-4", async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const onClick = vi.fn<() => void>();
    renderIconButton({ disabled: true, onClick });

    const button = screen.getByRole("button");
    await user.click(button);
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("is enabled when disabled is omitted — DoD-4", () => {
    renderIconButton();
    expect(screen.getByRole("button")).toBeEnabled();
  });
});

// ---------------------------------------------------------------------------
describe("icon sizing convention", () => {
  it.each([
    ["main", 18],
    ["inline", 16],
    ["chevron", 14],
  ] as const)(
    'sizeVariant="%s" renders the icon at size %d with stroke 1.5 — DoD-5',
    (sizeVariant, expectedSize) => {
      renderIconButton({ sizeVariant });
      const props = lastIconProps();
      expect(Number(props.size)).toBe(expectedSize);
      expect(props.stroke).toBe(1.5);
    },
  );

  it("renders the icon inside the button — DoD-5", () => {
    renderIconButton({ sizeVariant: "inline" });
    const button = screen.getByRole("button");
    const icon = screen.getByTestId("probe-icon");
    expect(button.contains(icon)).toBe(true);
  });

  it("omitting sizeVariant renders the icon at size 18 with stroke 1.5 — DoD-6", () => {
    renderIconButton();
    const props = lastIconProps();
    expect(Number(props.size)).toBe(18);
    expect(props.stroke).toBe(1.5);
  });

  it('omitting sizeVariant gives the icon the same size and stroke as "main" — DoD-6', () => {
    const { unmount } = renderIconButton({ sizeVariant: "main" });
    const main = lastIconProps();
    unmount();
    received = [];

    renderIconButton();
    const omitted = lastIconProps();
    expect(Number(omitted.size)).toBe(Number(main.size));
    expect(omitted.stroke).toBe(main.stroke);
  });
});

// ---------------------------------------------------------------------------
describe("colour goes to the button, never to the icon", () => {
  const COLOUR_KEY = /^(colou?r|c|fill)$/i;

  it("the icon component receives no colour prop — DoD-7", () => {
    renderIconButton({ color: "grape" });
    for (const props of received) {
      expect(Object.keys(props).filter((key) => COLOUR_KEY.test(key))).toEqual([]);
    }
    expect(received.length).toBeGreaterThan(0);
  });

  it("no colour is set on the icon element itself — DoD-7", () => {
    renderIconButton({ color: "grape" });
    const icon = screen.getByTestId("probe-icon");
    expect(icon.getAttribute("color")).toBeNull();
    expect(icon.getAttribute("fill")).toBeNull();
    expect(icon.style.color).toBe("");
    expect(icon.outerHTML).not.toMatch(/grape/i);
  });

  it("the colour is applied to the button — DoD-7", () => {
    renderIconButton({ color: "grape" });
    const button = screen.getByRole("button");
    const buttonMarkup = button.cloneNode(false) as HTMLElement;
    expect(buttonMarkup.outerHTML).toMatch(/grape/i);
  });
});

// ---------------------------------------------------------------------------
describe("keyboard reachability", () => {
  it("is reached by tab order when enabled — DoD-8", async () => {
    const user = userEvent.setup();
    renderIconButton({}, { before: <button type="button">before</button> });

    await user.tab();
    expect(screen.getByRole("button", { name: "before" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Archive session" })).toHaveFocus();
  });

  it("is activated from the keyboard with Enter and Space — DoD-8", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn<() => void>();
    renderIconButton({ onClick });

    await user.tab();
    expect(screen.getByRole("button")).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onClick).toHaveBeenCalledTimes(1);
    await user.keyboard(" ");
    expect(onClick).toHaveBeenCalledTimes(2);
  });

  it("is removed from tab order when disabled — DoD-8", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn<() => void>();
    renderIconButton(
      { disabled: true, onClick },
      {
        before: <button type="button">before</button>,
        after: <button type="button">after</button>,
      },
    );

    await user.tab();
    expect(screen.getByRole("button", { name: "before" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "after" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Archive session" })).not.toHaveFocus();
    expect(onClick).not.toHaveBeenCalled();
  });
});
