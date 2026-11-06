// The inline session-name editor (feature 034, step 005, DEC-034-11): one single-line input
// that renames a session in place. It holds no logic of its own — it edits a host-owned
// `SessionRenameState` and calls the host's commit wiring; the host (tree, header, step 006)
// owns the open affordance, the workspace store and the abort controller.
import type * as React from "react";
import { TextInput } from "@mantine/core";
import { runInAction } from "mobx";
import { observer } from "mobx-react-lite";

import type { SessionRenameState } from "./sessionRenameState";
import { cancelRename } from "./sessionRenameState";

/** Props of {@link SessionNameEditor}. */
export type SessionNameEditorProps = {
  /** The host's rename state; the editor renders only while `state.editingId` is non-null. */
  state: SessionRenameState;
  /**
   * The host's commit wiring, called on Enter and on blur. The host calls `commitRename`
   * with its workspace `SessionsState`, its success callback and its signal.
   */
  onCommit: () => void;
};

/**
 * Renders a Mantine `TextInput` labelled "Session name", pre-filled from `state.draft` and
 * focused on mount. Typing writes the draft through `runInAction`; Enter and blur call
 * `onCommit`; Escape calls `cancelRename` (no request). `state.error` renders inline under
 * the input (the input's `error`). The input is read-only while `state.pending`.
 */
export const SessionNameEditor = observer(function SessionNameEditor(
  props: SessionNameEditorProps,
): React.JSX.Element {
  const { state, onCommit } = props;
  return (
    <TextInput
      label="Session name"
      value={state.draft}
      // The host mounts the editor only when the roleplayer asked to rename, so taking focus
      // on mount is the expected move, not a surprise.
      autoFocus
      readOnly={state.pending}
      error={state.error}
      onChange={(event) => {
        const value = event.currentTarget.value;
        runInAction(() => {
          state.draft = value;
        });
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          onCommit();
        } else if (event.key === "Escape") {
          event.preventDefault();
          cancelRename(state);
        }
      }}
      // Blur commits too; `commitRename`'s pending guard turns Enter-then-blur into one request.
      onBlur={onCommit}
    />
  );
});
