// The `app` entry's application (008 context.md D5): one `WorkspaceShell` wrapped around a
// flat `<Routes>` — the shell sits above the route table, so there is no layout route and
// no `<Outlet/>`. Creates no router and declares no `basename`: the caller supplies the
// router (`BrowserRouter` in 005's `main.tsx`, `MemoryRouter` in tests). Reads no
// observable of its own, so it is a plain component rather than an `observer`.
import type * as React from "react";
import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import { Text } from "@mantine/core";

import type { CurrentUser } from "../shared/currentUser";
import type { LayoutStorage } from "./workspaceLayout";
import { WorkspaceShell } from "./WorkspaceShell";
import { CharacterRoute, CharacterScreen } from "./CharacterScreen";
import { SessionRoute } from "./SessionScreen";
import { SettingsScreen } from "./SettingsScreen";
import { SearchScreen } from "./SearchScreen";
import { CharactersState } from "./charactersState";
import { SessionsState } from "./sessionsState";

export type AppProps = {
  /** The signed-in identity, handed to `WorkspaceShell`. */
  user: CurrentUser;
  /** The persisted-layout storage, or `null`; handed to `WorkspaceShell`. */
  storage: LayoutStorage | null;
};

/**
 * Renders `WorkspaceShell` around the six declared in-entry routes — `/`,
 * `/sessions/:id`, `/characters/new`, `/characters/:id`, `/settings`, `/search` — plus
 * the `*` catch-all whose centre reads "Page not found".
 *
 * `/characters/new` is listed before `/characters/:id` for readability only; React Router
 * 7 ranks the static segment above the dynamic one regardless. Later features (013, 017,
 * 018) fill the remaining centres; their elements are empty on purpose — no
 * placeholder pretends a feature exists. 009 fills the two character routes, 011 step
 * 009 fills `/sessions/:id` with `SessionRoute`, and 029 step 005 fills `/search` with
 * `SearchScreen` — which, unlike the other screens, receives no props at all: it owns the
 * one page state it needs (029 decision 10).
 */
export function App(props: AppProps): React.JSX.Element {
  const { user, storage } = props;
  // The one workspace characters state (009 D11): created here, passed to the character
  // screen and (from 009 step 008) to the tree, so a mutation updates both.
  const [characters] = useState(() => new CharactersState());
  // The one workspace sessions state (011 D15): created here exactly once, passed down as a
  // prop — never a context and never a module singleton. The tree loads it; 011 step 008's
  // section applies mutated rows to it, so the tree updates with no refetch.
  const [sessions] = useState(() => new SessionsState());

  return (
    <WorkspaceShell
      user={user}
      storage={storage}
      characters={characters}
      sessions={sessions}
    >
      <Routes>
        <Route path="/" element={null} />
        <Route path="/sessions/:id" element={<SessionRoute characters={characters} storage={storage} />} />
        <Route
          path="/characters/new"
          element={
            <CharacterScreen
              characters={characters}
              characterId={null}
              sessions={sessions}
              storage={storage}
            />
          }
        />
        <Route
          path="/characters/:id"
          element={
            <CharacterRoute characters={characters} sessions={sessions} storage={storage} />
          }
        />
        <Route path="/settings" element={<SettingsScreen />} />
        <Route path="/search" element={<SearchScreen />} />
        <Route path="*" element={<Text p="md">Page not found</Text>} />
      </Routes>
    </WorkspaceShell>
  );
}
