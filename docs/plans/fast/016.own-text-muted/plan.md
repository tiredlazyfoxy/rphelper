# Fast feature 016 — own-text-muted

## Goal

Render the roleplayer's own (user-role) message bodies in the chat in Mantine's
theme-aware dimmed gray, so they read apart from the assistant's rows — in the
current zone and in the read-only Discussion group that reuses the same row
(DEC-F016-1, DEC-F016-2).

## Source files

frontend/src/app/ZoneList.tsx — `ZoneMessage`: wrap the user-role body in a muted wrapper

## Test files

frontend/tests/app/ZoneListOwnTextTone.test.tsx — the muted tone on user rows in the zone and the Discussion group

## Interface intent

**`app/ZoneList.tsx`** (changed)

- **`ZoneMessage`** — props and exports unchanged. For a **user** row, the body
  (`MessageBody`, variant `"painted"`, unchanged) is rendered inside a Mantine `Box`
  carrying the dimmed colour (`c="dimmed"`) and the marker attribute
  **`data-tone="muted"`** (DEC-F016-2, DEC-F016-4). Exactly one such wrapper per
  user row, and it contains the row's rendered body text.
- **Assistant** and **tool** rows: body unchanged, no `data-tone` wrapper.
- **Editing** a user row: the edit `Textarea` replaces the body exactly as today and
  is not inside a `data-tone="muted"` element. On leaving the editor the muted body
  returns.
- Header (author label, edit / delete controls), list structure and labels are
  unchanged. `MessageBody`, `DiscussionGroup`, `StreamRecord` and `LiveMessage` are
  not edited (DEC-F016-3).

## Definition of done

1. `[test]` `ZoneList` over a zone `[user "Hi there", assistant "Hello back", tool
   "Found 2 memos." (memo_search, ok)]`: the "You" item contains exactly one
   `data-tone="muted"` element, and that element contains the text `Hi there`. The
   "Assistant" and "Tool" items contain no `data-tone="muted"` element.
   (DEC-F016-2, DEC-F016-4; US-114.AC-2)
2. `[test]` `ZoneMessage` rendered with `editable` false for a user row shows its body
   inside a `data-tone="muted"` element; for an assistant and a tool row, none.
   (DEC-F016-2; US-116.AC-1)
3. `[test]` `DiscussionGroup` expanded and answered `[user "Write me a reply",
   assistant "I wave back."]`: in the "Discussion messages" list the "You" item has
   its text inside a `data-tone="muted"` element and the "Assistant" item has none.
   (DEC-F016-2; US-040.AC-1)
4. `[test]` A user row whose text contains a `(( ))` fragment and an OOC block
   (shapes as in `MessageBody.test.tsx`) renders inside the muted wrapper with its
   `data-paren="fragment"` and `data-paren="ooc"` elements still present.
   (DEC-F016-3)
5. `[test]` Pressing "Edit message" on the user row shows the "Edit message text"
   textarea holding the row's text, and the textarea is not inside any
   `data-tone="muted"` element. (DEC-F016-4; US-115.AC-1)
6. `[test]` The existing suites `ZoneList.test.tsx`, `ZoneListAssistant.test.tsx`,
   `MessageBody.test.tsx`, `DiscussionGroup.test.tsx`,
   `StreamRecordDiscussion.test.tsx` and `tests/stylesheets.test.ts` pass unchanged;
   `npm run typecheck` and `npm run build` succeed.
7. `[manual/live]` In a browser, in both light and dark colour schemes: the
   roleplayer's own text in the zone and in an expanded Discussion group is a
   legible light gray matching the "You" label's tone; assistant text stays at
   normal contrast; fragment chips and OOC cards keep their accent colours; settled
   record entries are unchanged.

## Out of scope

- Settled record entries (turn, decision, partner) in `StreamRecord`.
- `LiveMessage` (assistant only).
- Any change to `MessageBody`'s props or rendering, or to the fragment / OOC chips.
- The composer and the edit `Textarea`'s colour.
- Any user setting to turn the tone off or choose a colour.
- Product or architecture doc edits (finalization only, per `outcome.md`).
