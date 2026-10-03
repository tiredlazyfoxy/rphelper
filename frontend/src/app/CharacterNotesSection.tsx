// The character page's character-level "Notes" region (feature 015, step 009, D1 / D8 /
// D16): owns one `MemoLevelState` for scope "character" and the given id, loads it on mount
// (aborted on unmount), and renders the shared `MemoLevelGroup` titled "Notes" at the same
// heading order as the page's "Setups" and "Sessions" headings. Mounted by
// `CharacterScreen`'s existing-mode ready render after `SessionsSection`, keyed by the id.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react-lite";

import { MemoLevelState, loadMemoLevel } from "./memoLevelState";
import { MemoLevelGroup } from "./MemoLevelGroup";

export type CharacterNotesSectionProps = {
  /** The loaded character's id. A string, never parsed. */
  characterId: string;
};

export const CharacterNotesSection = observer(function CharacterNotesSection(
  props: CharacterNotesSectionProps,
): React.JSX.Element {
  // Created once; `CharacterScreen` keys this section by the character id, so a different
  // character remounts it with fresh state (D16: separate from the session screen's level).
  const [state] = useState(() => new MemoLevelState("character", props.characterId));
  const controllerRef = useRef<AbortController | null>(null);

  // One load on mount; whichever controller is current aborts on unmount.
  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadMemoLevel(state, controller.signal);
    return () => {
      controller.abort();
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [state]);

  const retry = (): void => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadMemoLevel(state, controller.signal);
  };

  // Same `Title order={3}` as the page's "Setups" and "Sessions" headings.
  return <MemoLevelGroup state={state} title="Notes" headingOrder={3} onRetry={retry} />;
});
