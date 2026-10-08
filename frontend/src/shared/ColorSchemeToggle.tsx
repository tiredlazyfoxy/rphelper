import type * as React from "react";
import { useComputedColorScheme, useMantineColorScheme } from "@mantine/core";
import { IconMoon, IconSun } from "@tabler/icons-react";

import { DEFAULT_COLOR_SCHEME } from "./colorScheme";
import { IconButton } from "./IconButton";

export function ColorSchemeToggle(): React.JSX.Element {
  const { setColorScheme } = useMantineColorScheme();
  const computed = useComputedColorScheme(DEFAULT_COLOR_SCHEME);
  const isDark = computed === "dark";

  return (
    <IconButton
      icon={isDark ? IconSun : IconMoon}
      label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => setColorScheme(isDark ? "light" : "dark")}
      sizeVariant="main"
    />
  );
}
