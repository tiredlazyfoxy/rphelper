// The `app` entry's application (008 context.md D5): one `WorkspaceShell` wrapped around a
// flat `<Routes>` — the shell sits above the route table, so there is no layout route and
// no `<Outlet/>`. Creates no router and declares no `basename`: the caller supplies the
// router (`BrowserRouter` in 005's `main.tsx`, `MemoryRouter` in tests). Reads no
// observable of its own, so it is a plain component rather than an `observer`.
import type * as React from "react";
import { Route, Routes } from "react-router-dom";
import { Text } from "@mantine/core";

import type { CurrentUser } from "../shared/currentUser";
import type { LayoutStorage } from "./workspaceLayout";
import { WorkspaceShell } from "./WorkspaceShell";

export type AppProps = {
  /** The signed-in identity, handed to `WorkspaceShell`. */
  user: CurrentUser;
  /** The persisted-layout storage, or `null`; handed to `WorkspaceShell`. */
  storage: LayoutStorage | null;
};

/**
 * Renders `WorkspaceShell` around the six declared in-entry routes — `/`,
 * `/sessions/:id`, `/characters/new`, `/characters/:id`, `/settings`, `/search`, each an
 * empty centre column — plus the `*` catch-all whose centre reads "Page not found".
 *
 * `/characters/new` is listed before `/characters/:id` for readability only; React Router
 * 7 ranks the static segment above the dynamic one regardless. Later features (009, 011,
 * 013, 017, 018, 029) fill the centres; in 008 every declared route's element is empty on
 * purpose — no placeholder pretends a feature exists.
 */
export function App(props: AppProps): React.JSX.Element {
  const { user, storage } = props;

  return (
    <WorkspaceShell user={user} storage={storage}>
      <Routes>
        <Route path="/" element={null} />
        <Route path="/sessions/:id" element={null} />
        <Route path="/characters/new" element={null} />
        <Route path="/characters/:id" element={null} />
        <Route path="/settings" element={null} />
        <Route path="/search" element={null} />
        <Route path="*" element={<Text p="md">Page not found</Text>} />
      </Routes>
    </WorkspaceShell>
  );
}
