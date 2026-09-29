// Entry module for the `admin` document. Exports nothing; mounts on evaluation.
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppProviders } from "../shared/AppProviders";

const mount = document.getElementById("root");
if (mount === null) {
  throw new Error("admin entry: mount element #root not found");
}

createRoot(mount).render(
  <AppProviders>
    <BrowserRouter basename="/admin">
      <Routes>
        <Route path="*" element={<div data-entry="admin" />} />
      </Routes>
    </BrowserRouter>
  </AppProviders>,
);
