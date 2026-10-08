// Entry module for the `bootstrap` document. Exports nothing; mounts on evaluation.
import type * as React from "react";
import { useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppProviders } from "../shared/AppProviders";
import { BootstrapPage } from "./BootstrapPage";
import { BootstrapState } from "./bootstrapState";

function BootstrapRoute(): React.JSX.Element {
  const [state] = useState(() => new BootstrapState());
  return <BootstrapPage state={state} />;
}

const mount = document.getElementById("root");
if (mount === null) {
  throw new Error("bootstrap entry: mount element #root not found");
}

createRoot(mount).render(
  <AppProviders>
    <BrowserRouter>
      <Routes>
        <Route path="*" element={<BootstrapRoute />} />
      </Routes>
    </BrowserRouter>
  </AppProviders>,
);
