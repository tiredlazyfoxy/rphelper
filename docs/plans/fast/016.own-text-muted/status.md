# Fast feature 016 — own-text-muted

| Status  | Verifier | Date |
|---------|----------|------|
| done    | PASS     | 2026-11-05 |

## Files Changed

- `frontend/src/app/ZoneList.tsx` — `ZoneMessage` wraps the user-role body in a `Box c="dimmed" data-tone="muted"` (DEC-F016-2/4)

## Skeleton

### Frozen interface (2026-11-05)
- `frontend/src/app/ZoneList.tsx` — `ZoneMessage = observer(function ZoneMessage(props: ZoneMessageProps): React.JSX.Element)` with `ZoneMessageProps = { state: StreamState; message: Message; signal?: AbortSignal; editable?: boolean }` — unchanged (no new or changed signature; the feature is a render change inside `ZoneMessage` only). `ZoneList` / `ZoneListProps` and all exports unchanged. No stub written; no code edit.
- Frozen test hook: for a **user** row, the body (`MessageBody`, variant `"painted"`) sits inside exactly one Mantine `Box` with `c="dimmed"` and the DOM attribute `data-tone="muted"`; assistant and tool rows carry no `data-tone` element; the edit `Textarea` is never inside a `data-tone="muted"` element.
- Caller-compile edits (out of Source-files scope): None.

## Tests

### Tests (2026-11-05)
- `frontend/tests/app/ZoneListOwnTextTone.test.tsx` — covers DoD-1, DoD-2, DoD-3, DoD-4, DoD-5 — exactly one `data-tone="muted"` wrapper holding the body on user rows (zone, read-only `ZoneMessage`, expanded `DiscussionGroup`), none on assistant/tool rows; fragment chip and OOC card survive inside it; the edit textarea is outside any muted element and the muted body returns on blur
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓ (two user rows: fragment shape and wholly-parenthesised shape, since the painter cannot yield both in one text), DoD-5 ✓, DoD-6 [covered by the named existing suites + typecheck/build run unchanged, no new test], DoD-7 [manual/live, no test]

## Notes & Issues

_populated by the coder when worth saying_
