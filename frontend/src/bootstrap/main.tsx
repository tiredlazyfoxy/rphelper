// Entry module for the `bootstrap` document. Exports nothing; mounts on evaluation.
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppProviders } from "../shared/AppProviders";

const mount = document.getElementById("root");
if (mount === null) {
  throw new Error("bootstrap entry: mount element #root not found");
}

createRoot(mount).render(
  <AppProviders>
    <BrowserRouter>
      <Routes>
        <Route path="*" element={<div data-entry="bootstrap" />} />
      </Routes>
    </BrowserRouter>
  </AppProviders>,
);
