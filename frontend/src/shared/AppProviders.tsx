import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "../global.css";

import type * as React from "react";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";

import { colorSchemeManager, DEFAULT_COLOR_SCHEME } from "./colorScheme";
import { theme } from "./theme";

export function AppProviders(props: { children: React.ReactNode }): React.JSX.Element {
  return (
    <MantineProvider
      theme={theme}
      colorSchemeManager={colorSchemeManager}
      defaultColorScheme={DEFAULT_COLOR_SCHEME}
    >
      <Notifications autoClose={5000} />
      {props.children}
    </MantineProvider>
  );
}
