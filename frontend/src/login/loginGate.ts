// The login entry's mount gate: a data class (observable phase only) plus a free async probe
// over it (fast/010 D1, D2, D3). Sends an unconfigured instance on to `/bootstrap/`.
import { makeAutoObservable, runInAction } from "mobx";
import { apiGet } from "../shared/api";

/** The three phases of the gate; only "form" shows the sign-in form. */
export type LoginGatePhase = "probing" | "form" | "leaving";

/** The narrow, login-local slice of the `GET /api/health` body — `configured` alone (D2). */
export type LoginHealthResponse = {
  configured: boolean;
};

export class LoginGate {
  phase: LoginGatePhase = "probing";

  constructor() {
    makeAutoObservable(this, {}, { autoBind: true });
  }
}

/**
 * One `GET /api/health`: strictly `configured === false` → phase "leaving" and
 * `navigate("/bootstrap/")` once; anything else → phase "form". Aborted → no write, no
 * navigation. Never rejects.
 */
export async function probeLoginGate(
  gate: LoginGate,
  signal: AbortSignal,
  navigate: (url: string) => void,
): Promise<void> {
  let configured: unknown;
  try {
    const body = await apiGet<Partial<LoginHealthResponse> | null>("/api/health", signal);
    configured = typeof body === "object" && body !== null ? body.configured : undefined;
  } catch {
    // Every failure falls through to the form (D1): no retry, no notification.
    configured = undefined;
  }
  if (signal.aborted) {
    return;
  }
  if (configured === false) {
    runInAction(() => {
      gate.phase = "leaving";
    });
    navigate("/bootstrap/");
    return;
  }
  runInAction(() => {
    gate.phase = "form";
  });
}
