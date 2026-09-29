// Entry module for the `login` document. Exports nothing; mounts on evaluation.
import type * as React from "react";
import { useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppProviders } from "../shared/AppProviders";
import { LoginPage } from "./LoginPage";
import { LoginDraft } from "./loginDraft";

function LoginRoute(): React.JSX.Element {
  const [draft] = useState(() => new LoginDraft());
  return <LoginPage draft={draft} />;
}

const mount = document.getElementById("root");
if (mount === null) {
  throw new Error("login entry: mount element #root not found");
}

createRoot(mount).render(
  <AppProviders>
    <BrowserRouter>
      <Routes>
        <Route path="*" element={<LoginRoute />} />
      </Routes>
    </BrowserRouter>
  </AppProviders>,
);
