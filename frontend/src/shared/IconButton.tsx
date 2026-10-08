import type * as React from "react";
import { ActionIcon, Tooltip } from "@mantine/core";
import type { MantineColor } from "@mantine/core";

export type IconButtonProps = {
  icon: React.ComponentType<{ size?: number | string; stroke?: number }>;
  label: string;                     // tooltip text AND aria-label — one source
  onClick: () => void;
  disabled?: boolean;
  color?: MantineColor;              // semantic colour, applied to ActionIcon
  sizeVariant?: "main" | "inline" | "chevron";   // maps to 18/16/14 + stroke
};

const ICON_SIZES: Record<NonNullable<IconButtonProps["sizeVariant"]>, number> = {
  main: 18,
  inline: 16,
  chevron: 14,
};

const ICON_STROKE = 1.5;

export function IconButton(props: IconButtonProps): React.JSX.Element {
  const { icon: Icon, label, onClick, disabled, color, sizeVariant = "main" } = props;
  return (
    <Tooltip label={label}>
      <ActionIcon
        variant="subtle"
        aria-label={label}
        color={color}
        disabled={disabled}
        onClick={onClick}
      >
        <Icon size={ICON_SIZES[sizeVariant]} stroke={ICON_STROKE} />
      </ActionIcon>
    </Tooltip>
  );
}
