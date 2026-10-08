import { notifications } from "@mantine/notifications";

import { isApiError } from "./apiError";

const GENERIC_FAILURE_REASON = "Something went wrong. Please try again.";

export function notifyFailure(error: unknown): void {
  const message = isApiError(error) && error.message ? error.message : GENERIC_FAILURE_REASON;
  notifications.show({ message, color: "red" });
}
