// The second notification outlet (feature 014, step 003, D4): a yellow, transient warning
// chosen from a closed set of identifiers — never free text, so no success can pass here.
import { notifications } from "@mantine/notifications";

export type WarningId = "paste-context-cost" | "import-search-coverage";

const WARNING_MESSAGES: Record<WarningId, string> = {
  "paste-context-cost":
    "This paste is very large and will take up a lot of the assistant's context.",
  // 031 step 006: the one caveat a successful roleplayer import raises. An import embeds nothing,
  // so the material it brought in stays outside the vector index until an administrator rebuilds
  // it. A caveat about coverage, not a success message, so the no-success-toast rule holds.
  "import-search-coverage":
    "Imported material won't appear in semantic search until an administrator rebuilds the search index.",
};

export function notifyWarning(id: WarningId): void {
  notifications.show({ message: WARNING_MESSAGES[id], color: "yellow" });
}
