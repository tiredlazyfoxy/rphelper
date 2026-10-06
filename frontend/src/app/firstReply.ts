// Feature fast/004 (D2): the one definition of the router `location.state` marker meaning
// "this session was just seeded from the character page". `CharacterComposer` writes it with
// `firstReplyState()` on its push to `/sessions/<id>`; `SessionScreen` — the only router
// reader on the session screen — recognises it with `isFirstReplyState`, so writer and
// reader cannot drift. Pure: no ids, no router import.

/** The router state value marking a session as just seeded from the character page. */
export type FirstReplyState = { readonly firstReply: true };

/** The marker value to pass as navigation state. */
export function firstReplyState(): FirstReplyState {
  return { firstReply: true };
}

/**
 * Whether an arbitrary `location.state` carries the first-reply marker. False for null,
 * undefined, non-objects and any other shape.
 */
export function isFirstReplyState(state: unknown): state is FirstReplyState {
  return (
    typeof state === "object" &&
    state !== null &&
    (state as { firstReply?: unknown }).firstReply === true
  );
}
