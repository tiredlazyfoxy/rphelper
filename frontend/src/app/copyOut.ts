// Copy-out (feature 014, step 004): the one place in `src/` that touches the clipboard.
// Puts a text on the clipboard as plain text, with the insecure-origin fallback (D8, D9,
// UC-030). Reads no state, writes none, makes no network request.
import { notifyFailure } from "../shared/notifyFailure";

import { toPlainText } from "./plainText";

const FALLBACK_FAILURE = "The text could not be copied to the clipboard.";

/** The D9 fallback: an off-screen read-only textarea, selected, `execCommand("copy")`. */
function copyWithTextarea(plain: string): boolean {
  const previous = document.activeElement;
  const area = document.createElement("textarea");
  area.value = plain;
  area.readOnly = true;
  area.setAttribute("aria-hidden", "true");
  area.style.position = "fixed";
  area.style.top = "-10000px";
  area.style.left = "-10000px";
  area.style.opacity = "0";

  try {
    document.body.appendChild(area);
    area.select();
    if (!document.execCommand("copy")) {
      notifyFailure(new Error(FALLBACK_FAILURE));
      return false;
    }
    return true;
  } catch (error) {
    notifyFailure(error);
    return false;
  } finally {
    area.remove();
    if (previous instanceof HTMLElement && previous.isConnected) {
      previous.focus();
    }
  }
}

/** Effect: copies the text as plain text; resolves to whether the copy succeeded; never rejects. */
export async function copyAsPlainText(text: string): Promise<boolean> {
  let plain: string;
  try {
    plain = toPlainText(text);
  } catch (error) {
    notifyFailure(error);
    return false;
  }

  const clipboard = typeof navigator === "undefined" ? undefined : navigator.clipboard;
  if (clipboard !== undefined && clipboard !== null && typeof clipboard.writeText === "function") {
    try {
      await clipboard.writeText(plain);
      return true;
    } catch (error) {
      notifyFailure(error);
      return false;
    }
  }
  return copyWithTextarea(plain);
}
