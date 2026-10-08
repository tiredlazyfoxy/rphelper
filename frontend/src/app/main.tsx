// Entry module for the `app` document. Exports nothing; mounts on evaluation.
// Nothing is rendered until the boot gate's `GET /api/me` resolves (008 context.md D2);
// the gate is the component `AppBoot`, mounted inside the router.
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AppProviders } from "../shared/AppProviders";
import { AppBoot } from "./AppBoot";
import { browserLayoutStorage } from "./shellState";
import "../shell.css";

const mount = document.getElementById("root");
if (mount === null) {
  throw new Error("app entry: mount element #root not found");
}

// The one point this feature reaches the real `localStorage`; read once, at mount.
const storage = browserLayoutStorage();

// No `basename`: the `app` entry's routes are mounted at the origin root.
createRoot(mount).render(
  <AppProviders>
    <BrowserRouter>
      <AppBoot storage={storage} />
    </BrowserRouter>
  </AppProviders>,
);
