// Entry module for the `admin` document. Exports nothing; mounts on evaluation.
// Nothing is rendered until the gate (`GET /api/me`) resolves.
import { createRoot, type Root } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AppProviders } from "../shared/AppProviders";
import {
  ADMIN_ACCESS_RETRY_INTERVAL_MS,
  enforceAdminAccess,
  type AdminAccessResult,
} from "./adminAccess";
import { AdminApp } from "./AdminApp";
import { AdminNotReady } from "./AdminNotReady";

const mountElement = document.getElementById("root");
if (mountElement === null) {
  throw new Error("admin entry: mount element #root not found");
}
const mount: HTMLElement = mountElement;

let root: Root | null = null;
let retryTimer: ReturnType<typeof setInterval> | null = null;
let latestProbe = 0;

function ensureRoot(): Root {
  if (root === null) {
    root = createRoot(mount);
  }
  return root;
}

function stopRetryTimer(): void {
  if (retryTimer !== null) {
    clearInterval(retryTimer);
    retryTimer = null;
  }
}

function startRetryTimer(): void {
  if (retryTimer === null) {
    retryTimer = setInterval(() => {
      void runGate();
    }, ADMIN_ACCESS_RETRY_INTERVAL_MS);
  }
}

function render(result: AdminAccessResult): void {
  const decision = result.decision;
  switch (decision) {
    case "granted":
      stopRetryTimer();
      ensureRoot().render(
        <AppProviders>
          <BrowserRouter basename="/admin">
            <AdminApp />
          </BrowserRouter>
        </AppProviders>,
      );
      break;
    case "denied-no-session":
    case "denied-not-admin":
      stopRetryTimer();
      if (root !== null) {
        root.unmount();
        root = null;
      }
      break;
    case "not-ready":
    case "failed":
      if (decision === "not-ready") {
        startRetryTimer();
      } else {
        stopRetryTimer();
      }
      ensureRoot().render(
        <AppProviders>
          <AdminNotReady
            variant={decision}
            message={result.decision === "failed" ? result.message : undefined}
            onRetry={() => {
              void runGate();
            }}
          />
        </AppProviders>,
      );
      break;
  }
}

async function runGate(): Promise<void> {
  latestProbe += 1;
  const probe = latestProbe;
  const result = await enforceAdminAccess();
  if (probe !== latestProbe) {
    return;
  }
  render(result);
}

void runGate();
