// The second notification outlet (feature 014, step 003, D4): a yellow, transient warning
// chosen from a closed set of identifiers — never free text, so no success can pass here.
import { notifications } from "@mantine/notifications";

export type WarningId = "paste-context-cost";

const WARNING_MESSAGES: Record<WarningId, string> = {
  "paste-context-cost":
    "This paste is very large and will take up a lot of the assistant's context.",
};

export function notifyWarning(id: WarningId): void {
  notifications.show({ message: WARNING_MESSAGES[id], color: "yellow" });
}
