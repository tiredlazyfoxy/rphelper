# Fast feature 004 — character-page-first-reply

| Status | Verifier | Date |
|--------|----------|------|
| done    | PASS     | 2026-10-07 |

## Files Changed

- `frontend/src/app/firstReply.ts` — marker constructor and predicate bodies
- `frontend/src/app/streamState.ts` — `composeFirstReply` body with its once-per-`StreamState` guard
- `frontend/src/app/CharacterComposer.tsx` — push to `/sessions/<id>` now carries the marker state
- `frontend/src/app/SessionScreen.tsx` — captures the marker once per id, clears it with a replace (path/search/hash kept), passes `firstReply`
- `frontend/src/app/SessionStream.tsx` — calls `composeFirstReply` after the load resolves ready in the load effect

## Skeleton

### Frozen interface (2026-10-07)
- `frontend/src/app/firstReply.ts` — `export type FirstReplyState = { readonly firstReply: true }` — new
- `frontend/src/app/firstReply.ts` — `export function firstReplyState(): FirstReplyState` — new (stub throws)
- `frontend/src/app/firstReply.ts` — `export function isFirstReplyState(state: unknown): state is FirstReplyState` — new (stub throws)
- `frontend/src/app/streamState.ts` — `export async function composeFirstReply(state: StreamState, signal: AbortSignal): Promise<void>` — new (stub throws)
- `frontend/src/app/streamState.ts` — `StreamState.firstReplyStarted: boolean` (initially `false`; excluded from observability alongside `composeHandle`) — new field, the once-flag
- `frontend/src/app/SessionStream.tsx` — `SessionStreamProps.firstReply?: boolean` (absent = false) — changed (was no such prop); declared only, not yet read
- `frontend/src/app/CharacterComposer.tsx`, `frontend/src/app/SessionScreen.tsx` — no signature change; the marker push, the once-per-id capture, the replace and the prop pass-through are the coder's wire-ups (not mounted as stubs, so existing tests stay green).
- Caller-compile edits (out of Source-files scope): None.

## Tests

### Tests (2026-10-07)
- `frontend/tests/app/streamFirstReply.test.ts` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5 — `composeFirstReply` against a faked fetch: one POST `…/zone/compose` with body `{}`, tokens as `streamingText`, zone re-read after `done`; once per `StreamState` (during and after, incl. a zone still ending in the user row) and a fresh `StreamState` unaffected; last non-tool row decides (trailing tool rows don't block), plus empty/tool-only/busy/not-ready/streaming gates; aborted signal makes no request (and does not consume the once-flag); 409 `no_model_enabled` resolves, `notifyFailure` once with that code, not streaming, opening row kept.
- `frontend/tests/app/sessionFirstReply.test.tsx` — covers DoD-6, DoD-7, DoD-8, DoD-9, DoD-10, DoD-11, DoD-12 — marker constructor/predicate (false for null/undefined/non-objects/other shapes); page composer push carries the marker (nav type PUSH, Back returns); `SessionRoute` arrival with marker composes once with `{}`, renders tokens, shows "Stop"; without marker none; marker cleared by REPLACE with pathname/search unchanged and Back landing on the character page; re-render and Back→Forward remount at the cleared entry compose no more; StrictMode yields one compose; answered zone composes nothing; `?notes=open&entry=<id>` survives the clearing.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 [verifier gate: typecheck + full suite, no dedicated test], DoD-14/15/16 [manual/live, no test]

## Notes & Issues

_populated by the coder when worth saying_
