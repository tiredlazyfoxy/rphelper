import { createTheme, type MantineThemeOverride } from "@mantine/core";

// The application's single Mantine theme: exactly three tokens (D3). Semantic
// colours come from Mantine's built-in palette; geometry lives in shell.css.
export const theme: MantineThemeOverride = createTheme({
  primaryColor: "blue",
  fontFamily:
    'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif',
  defaultRadius: "sm",
});
