import { localStorageColorSchemeManager } from "@mantine/core";
import type { MantineColorScheme, MantineColorSchemeManager } from "@mantine/core";

export const COLOR_SCHEME_STORAGE_KEY = "rphelper.color-scheme";

export const colorSchemeManager: MantineColorSchemeManager = localStorageColorSchemeManager({
  key: COLOR_SCHEME_STORAGE_KEY,
});

export const DEFAULT_COLOR_SCHEME = "dark" satisfies MantineColorScheme;
