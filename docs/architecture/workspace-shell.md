# Workspace shell

**Realizes:** FEAT-020, FEAT-008, FEAT-009, FEAT-010, FEAT-011, FEAT-012,
FEAT-013, FEAT-017, UC-035, UC-069, UC-070, UC-071, UC-072, UC-073, UC-074,
UC-075, UC-076, UC-077, UC-078, UC-080, UC-081, UC-082, UC-083, UC-084

The `app` entry's one screen: three columns, a stream with a ruler through it, and
a wall of notes. This doc holds the **shell** — geometry, the columns, the wall's
two modes, layout persistence, and the anatomy of the stream and the current zone.
It was split out of `ui-conventions.md`, which keeps everything that is not the
shell: icons and the shared `IconButton`, tables, modals, the MobX draft form
convention, the confirm convention and the inherited frontend facts. Read both;
neither repeats the other.

Behaviour is cited, never restated. The geometry below comes from the settled
interface mockup, which is the source for shape and for nothing else.

---

## The three columns

```
┌──────────────┬────────────────────────────────┬──────────────────┐
│ tree         │ stream                         │ notes wall       │
│              │                                │                  │
│ characters   │   settled record               │  your notes      │
│  └ sessions  │   ─────── ruler ───────        │  character       │
│              │   current zone                 │  setup           │
│ ┄┄┄┄┄┄┄┄┄┄┄┄ │   composer                     │  session         │
│ user menu    │                                │                  │
└──────────────┴────────────────────────────────┴──────────────────┘
  UC-069, UC-071          UC-083, R11              UC-072, UC-075
```

The left column lists **characters with their sessions** (UC-069, US-088), newest
use first (US-089, `sessions.last_used_at` in `data-model.md`). A setup appears as
a label on a session row, never as a level of the tree — the tree has two levels
because the product has two navigable levels here; a setup is a property of the
session, not a place to stand.

The centre column is the session stream (UC-083). The right column is the note
wall (UC-072). My-search sits at the top of the tree and is reachable whether the
column is expanded or collapsed (US-118), which is why it is duplicated onto the
collapsed rail rather than hidden with the rest of the tree.

**The shell is a hand-written CSS grid, not Mantine `AppShell`.** This reverses
the previous shell decision, and the reason is the wall: `AppShell`'s
navbar/main/aside model expresses one fixed nav plus an aside that hides at a
breakpoint, and it computes `Main`'s padding from both. A wall that is an absolute
overlay in one mode and a real grid column in the other fights that computation in
both directions. The old `transitionDuration = 0` workaround recorded in
`ui-conventions.md` was a symptom of the same fight. `admin-surfaces.md` keeps
`AppShell` for the `admin` entry, where the shell is exactly what `AppShell`
models — the asymmetry is deliberate and is not an inconsistency to tidy up.

```css
.app                  { display: grid; gap: 1px;
                        grid-template-columns: var(--navw, 252px) minmax(0, 1fr); }
.app.nav-collapsed    { --navw: 48px; }
```

**Collapse is a class that re-points one custom property** (UC-070, US-090). It is
not a stored width, not a measured value and not an animation of two separate
elements. The consequence that matters: there is exactly one number to change, the
browser transitions `grid-template-columns` on its own, and nothing in React
re-renders when the column moves. `minmax(0, 1fr)` on the second track is
load-bearing — without the `0` minimum a long unbroken line in the stream
establishes the track's minimum width and pushes the tree off-screen.

The `1px` grid `gap` over a line-coloured background draws the column dividers, so
no column owns a border and there is no double-border seam where two panes meet.

Collapsed, the tree is replaced by a **rail** carrying my-search, new-character and
expand (US-090); the user button stays, reduced to its avatar. The rail is the
same column at a different width, not a second component.

---

## Geometry — everything is fixed; nothing resizes

| Thing | Value | Why this value |
|---|---|---|
| Tree column, expanded | `252px` | fits a character name plus a session title with a setup label and an age |
| Tree column, collapsed | `48px` | one 28px icon button plus its padding; nothing else fits, and nothing else belongs |
| Wall, floating | `min(320px, 84vw)` | 320px reads a note body at 12px without wrapping every line; the `84vw` cap keeps a sliver of stream visible on a narrow screen so the overlay reads as an overlay |
| Wall, pinned | `320px` | no `vw` term — pinned, it is a grid column and the grid already bounds it |
| Stream column | `max-width: 720px`, centred, `padding-inline: 18px` | a measure for prose, not for the viewport; the stream is read, not scanned |
| Composer | same 720px / 18px as the stream | the composer is the stream's last item visually and must share its left edge |
| Composer text area | `min-height: 42px`, **no max**, no handle | about two lines to start |
| Responsive threshold | `820px` | below it the tree becomes an off-canvas overlay and a pinned wall reverts to floating |

**The composer grows with its content.** It has a minimum height and no maximum,
no drag handle and no internal scroll until the viewport runs out. This is a
**deliberate reversal** of the old (C) — see the reversal record at the end of this
doc.

`820px` rather than a Mantine breakpoint token: the number is the point at which
252 + 720 + 320 stops fitting, which is a property of these three constants and not
of a general breakpoint scale. Recorded so it is not "corrected" to `md` (992px),
which would collapse the tree while both other columns still fit.

Nothing in the shell is user-resizable. `docs/product/` asks for no resizable
column anywhere; the only drag it requires is note reordering (US-102, US-103).

**Where these rules live — decided: `frontend/src/shell.css`, a second
hand-written stylesheet beside `global.css`.** The earlier `_TBD:` here is closed
by a user decision.

The reason is that every alternative is worse in a specific way. `global.css`'s
stated job is **resets**, and widening it to carry the workspace grid erodes a
convention that was set deliberately — once one layout rule is in there, the next
has no argument against it. Inline style objects cannot express these rules at
all: the grid template, the `--navw` custom property with its collapsed value,
and the `820px` threshold are a class toggle and a media query, not per-element
style. CSS Modules, Tailwind and styled-components are forbidden by the root
`CLAUDE.md` and `overview.md`. A second named file is the only option left that
keeps the styling authority visible in one place.

`shell.css` holds exactly the workspace's layout and nothing else: the
three-column grid and its `1px` gap, the `--navw` custom property and the
collapsed-rail class that re-points it, and the `820px` media query. Everything
that is not layout stays Mantine. The division between the two files is stated as
a convention in `frontend-structure.md`, which owns the frontend's file layout.

---

## The wall has two modes

**Realizes:** UC-072, US-094, US-095

| Mode | CSS | Reads as |
|---|---|---|
| Floating | `position: absolute`, anchored to the stream's right edge, `transform: translateX(...)` + drop shadow, above the stream | a flyout you opened and will dismiss |
| Pinned | `position: relative`, a real column of the centre grid (`minmax(0,1fr) auto`), no shadow | part of the workspace |

Two modes rather than one because the two uses are different: glancing at a note
while writing a line, versus working through the notes themselves. The floating
mode must not cost the stream any width for a glance; the pinned mode must not
overlap the text the roleplayer is comparing against.

The transform-and-shadow floating mode is animated; the pinned mode is not,
because a grid column appearing is a layout change and animating it reflows the
stream on every frame.

**The pin survives a reload** (US-094.AC-2) — it is the `wallPinned` boolean below.
Whether the wall is *open* does not survive: opening is a glance, pinning is a
preference, and restoring a floating overlay over the stream on load would greet
the roleplayer with a panel they have to dismiss.

**With no session open the wall is not shown at all** (US-095). It is not shown
empty and not shown disabled: three of its four levels exist only relative to a
session (R2's chain).

Below `820px` a pinned wall reverts to floating, because at that width a 320px
column leaves no measure for the stream.

---

## Layout persistence

**One** localStorage record under the key **`rphelper.workspace-layout`** — the key
is retained from the previous design, and the reason it was renamed from the
sibling project's still stands: two applications sharing a key on one host would
read each other's layout, and these two are designed to run side by side
(`deployment.md`'s port table).

```ts
type WorkspaceLayout = {
  navCollapsed: boolean;
  wallPinned: boolean;
};
```

**Two booleans and no numbers.** `asideWidth` and `answerBoxHeight` are **gone** —
both described geometry that no longer exists (see the reversal record).

Rules, carried over because they were right for reasons that have not changed:

- **Read is total and never throws.** Absent key, unparseable JSON, wrong types,
  missing fields — each case falls back **per field** to that field's default. The
  function returns a complete record; there is no partial result and no `null`.
  There are no clamps left to apply, because there are no numbers left to clamp.
- **A stored payload carrying `asideWidth` or `answerBoxHeight` must be tolerated
  and ignored**, never rejected and never allowed to fail the parse. An existing
  install will have one. Stated explicitly because the obvious strict-schema parse
  rejects the whole record over an unknown key and silently resets a roleplayer's
  layout.
- **Write is best-effort**, wrapped in `try`/`catch` and swallowed — private
  browsing and quota exhaustion both throw, and neither is worth interrupting a
  click for. A write merges its patch over a **fresh total read**, so the two
  fields cannot clobber each other.
- The record is written **on the toggle**, which is now the only time it can
  change. The old "never mid-drag" rule has nothing left to constrain.

Persistence stays in a **pure, DOM-free module** — functions that take and return
values, touching no `document`, no `window` and no React. The reason is unchanged
and is now the only reason: every fallback path above is unit-testable with no DOM,
which is what the pipeline's test-coder needs (`docs/plans/CLAUDE.md`).

---

## The stream — the settled record

**Realizes:** FEAT-009, UC-078, UC-082, US-109, US-110, US-123, US-124

Above the ruler is the record, read from the **`settled_entries` view** and ordered
by **`id`** — a snowflake is k-sortable, so `ORDER BY id` *is* the stream order and
there is no `position` column to consult (`data-model.md`). Every reader goes
through the view; raw `messages` is touched only by settle and re-open (R11).

Three kinds render differently, because they are three different things:

| `kind` | Rendering | Actions in the entry |
|---|---|---|
| `partner` | the partner's block, quoted surface | translate (FEAT-011), edit, copy |
| `turn` | the roleplayer's own settled turn | edit, **copy as plain text** |
| `decision` | a dashed, accent-coloured card — visibly not roleplay prose (UC-081) | edit only — **no copy at all** (US-123) |

**Every per-entry action lives inside the entry.** There is no row toolbar, no
context menu and no separate action column: the actions sit in the entry's own
header and are revealed on `:hover` **or** `:focus-within`, so they are reachable
by keyboard as well as pointer. The stream is a column of documents, not a table,
so `ui-conventions.md`'s table-row overflow-menu rule does not reach here — that
rule exists to keep a *row* from collapsing under four icon buttons.

**Editing is in place and saves on focus loss** (US-109, US-110). The entry's body
becomes editable where it sits; blur commits. There is no modal — which is a
**deliberate, bounded exception** to `ui-conventions.md`'s "create and edit are
always a `Modal`" rule. The reason the two do not conflict: the modal rule exists
so a form has a visible lifetime and one predictable place to appear, and a settled
entry is not a form — it is one text field rendered in the position where its
content belongs, and UC-078 requires it to be edited *where it sits*. The modal
rule continues to govern every create and every multi-field edit, including
character, setup and session creation.

A commit **re-reads the edited row** rather than the stream.
`ui-conventions.md`'s "mutations are never optimistic" rule is satisfied in its
intent — what renders is what the server stored, not what the client typed — while
a full stream re-load on every blur would re-scroll the roleplayer away from the
line they are writing.

Bodies are rendered with **`react-markdown`** (`frontend-structure.md`). **Copy
yields plain text, never markdown** (US-124): the destination is a chat box on
someone else's site, where markdown source is noise. This is the product's entire
outbound boundary (`vision.md`), so the copy path reads the settled text and
strips, rather than serialising the rendered DOM.

A settled entry's buried discussion (R7) hangs under it, collapsed, labelled with
its message count and marked read-only (US-113, US-116). Re-open is offered **only
while the current zone is empty** (US-128) — the affordance is *absent*, not
disabled, once anything is in the zone, because at that point the action does not
exist. R11 says what re-open does; this doc only says where the control is.

When no embedding model is configured, a banner sits above the stream saying
search coverage is incomplete (US-112). It never blocks an edit — the edit saves
either way, and the banner is the honest statement of the consequence. The backend
signal is `no_embedding_model` (`backend-structure.md`).

---

## The ruler and the current zone

**Realizes:** FEAT-010, UC-083, US-125, US-114, US-115

**One visible separator**, a labelled hairline, and below it the live chat read
from the **`current_zone` view**. One ruler and one zone per session — the zone is
a set of rows, not a row, so there is nothing that can duplicate (R11,
`data-model.md`).

- **Every message in the zone is editable by the roleplayer, the assistant's
  included** (US-115). Edited in place, same as a settled entry. This is not a
  courtesy affordance — it is the mechanism R7 and R11 depend on, because settle
  reads whatever the row holds at that moment.
- **Tool calls and thinking are collapsible blocks** in the zone, open while the
  assistant works and tucked away when it finishes (US-114). They remain
  re-openable afterwards; they are persisted rows (`role='tool'`,
  `data-model.md`), not transient UI state, which is why a reload does not lose
  them.
- A live assistant message streams into the zone through the SSE consumer
  (`frontend-structure.md`); an `error` frame leaves everything already in the zone
  intact (R10).
- With no enabled model the composer cannot send and says why (US-107). The typed
  error is R4's, surfaced here rather than swallowed.

---

## The kind switch and settle

**Realizes:** UC-035, UC-081, UC-084, US-120, US-121, US-126

A **two-position switch** above the zone — *partner* and *my turn* — declaring what
the zone will file. It defaults to the alternate of the last partner-or-turn entry
(US-120), because a roleplay alternates and the default should be right without a
click. `US-120` carries a `_TBD:` in `docs/product/` about what a settled
*decision* does to that default; carried forward here, not resolved.

- On **partner**, a paste **files itself immediately** with no Settle press
  (US-121). There is nothing to compose for text the roleplayer did not write, so
  the Settle control is disabled in this position rather than hidden — the
  switch's two positions must read as two modes of the same box.
- On **my turn**, **Settle takes the last message in the zone, whoever wrote it**
  (US-126).

The client **previews** what settling will do — whether the last message will file
as a `turn` or a `decision`, and whether a `(( ))` fragment will be stripped — as a
line of text under the composer. **The client previews; the server decides**
(R12's three-layer split). The preview exists because the classification is
invisible otherwise and the roleplayer finds out only afterwards; it is never
authoritative, and a client that disagreed with the server would be a display bug,
not a data one.

`(( ))` is also painted inside the zone: a wholly-parenthesised message renders as
an out-of-character block, a fragment as an inline chip. Both are display over the
stored text — R12's "parse once, at settle" means nothing here rewrites what is
stored.

**Settle and Send are labelled buttons, not icons.** Settle is the most
consequential action in the product and is the primary button; Send is secondary.
This resolves the open `_TBD:` in `ui-conventions.md` that proposed
`IconMessageCheck` and noted a label-bearing button might be right instead — the
mockup settles it as a label.

---

## The wall's contents

**Realizes:** FEAT-012, UC-075, UC-076, US-098..US-104, US-119

Notes are **sticky-note bars**: one body of text, no title field, no header
(US-119, and `memos` has no `title` column). A note is identified by its text, so
the text is the whole card.

**Two independent icons per note**, matching R3's two booleans exactly:
enabled/disabled and forced. They are two controls because they are two axes — a
disabled note keeps its forced flag, and a single tri-state control cannot express
that (R3, US-101). A disabled note renders struck through and dimmed but keeps its
forced marker visible, so the state that will be restored on re-enable is
readable before re-enabling.

Each note carries a one-line statement of its current reach — forced, searchable
or disabled — because the two icons say what is *set* and the roleplayer needs to
know what it *does*. R3's predicate ordering is what that line states: `is_enabled`
gates first, and a disabled note reaches the assistant by no path whatever
`is_forced` says.

Notes are **grouped by level in a fixed order — user, character, setup, session**
(US-103.AC-1), which is R2's chain order. The level headers are the only structure;
there is no collapsing, no filtering and no search inside the wall (my-search
covers finding a note, FEAT-017).

**Edited in place, saved on focus loss** (US-104) — the same interaction as a
stream entry, for the same reason.

A note is created enabled and not forced (R3, US-053), directly in its level, and
focus lands in the empty body. Nothing is persisted for an empty note until there
is something to persist.

### `@dnd-kit` is finally used

Note reordering within a level (UC-076, US-102) is the project's **first and only**
drag interaction. `frontend-structure.md` records `@dnd-kit` as available with
nothing requiring it; US-102 is that requirement.

- **A note cannot cross a level boundary by dragging** (US-103.AC-2). The
  constraint is enforced in the drop handler, not only signalled in the drag
  preview: `memos.sort_key` is scoped within `(scope, scope_id)` and nowhere wider
  (`data-model.md`), so a cross-level move is not expressible in the schema and
  must not be expressible in the UI either.
- Reordering is not decoration — it **changes what the system prompt contains**,
  because forced notes enter it in the arranged order within their level (R3,
  US-102). That is also why it must be reachable without a pointer: `@dnd-kit`'s
  keyboard sensor is required, not optional, on the same principle the deleted
  splitters were held to.
- A note being edited is not draggable. One card is both a text surface and a drag
  handle, and a text selection inside it must not start a drag.

---

## The character page

**Realizes:** UC-073, UC-074, UC-080, US-096, US-097, US-117

The same shell with **two columns instead of three**: tree, and a body that holds
the character's persona, its notes, its setups, its resolved configuration and its
sessions in one place (US-096). The notes move **into** the body as a grid of the
same note cards — the wall is not shown beside it (US-095), because three of its
four levels have no meaning with no session open.

**This is the same components in a different arrangement, not a second design.**
The note card, the in-place edit and the reorder behave identically in both places;
only the container differs. Stated because the obvious implementation forks a
second note component for the character page and the two then drift.

Creating a character opens a **draft page** and persists nothing until the
roleplayer enters something (UC-074, US-097). The page is marked as a draft while
that is true. A draft page rather than a create modal is a deliberate exception to
the modal rule, and the product states the reason: nothing is persisted until there
is content, so there is no form to submit.

### The composer, and how a session starts here

The body ends with a **composer**, and writing a message in it is how a roleplay
begins: the instance creates a new session under the character with a turn
already being drafted, and the written message becomes the opening message of
that turn's discussion (UC-080, US-117.AC-1, US-117.AC-2). There is no separate
"create session" step to press first — that is the whole point of the affordance.

**It is the same composer as the stream's, not a second one.** The geometry above
applies unchanged, as do `ui-conventions.md`'s conventions for it — the
auto-growing text area with no handle, and a labelled Send rather than an icon.
What differs is **where it posts**: the stream's composer addresses an existing
session, and this one addresses the character, because at the moment of writing
there is no session to address (`backend-structure.md` settles the route and why
creation and seeding are one request). Stated because the obvious implementation
writes a second composer for this page, and the two then drift on the first
change to either — the same failure the note cards above are protected from.

Once the session exists the roleplayer is in the workspace on it;
`frontend-structure.md` owns that navigation. So this composer is used at most
once per session it creates. It is an entry point, not a second place to write.

`_TBD: docs/product/ does not say whether this composer carries the kind switch
or a setup choice, and neither is decidable from UC-080 or US-117. There is no
partner block yet for the switch's alternating default (US-120) to read, and
UC-080 names no setup — so the created session has none, which R2 makes a
first-class case rather than a degraded one. FEAT-008's plan must choose, or the
question goes back to /product-spec._

---

## The user menu

**Realizes:** UC-071, US-091, US-092, US-093

Bottom-left, under the tree, opening upward from the user button. Three items:

| Item | Goes to |
|---|---|
| Settings | the two languages and the user's own notes (US-092) |
| Admin area | `/admin` — **shown only to ACT-001** (US-093) |
| Log out | ends the session (US-091) |

**The admin link is a cross-entry document navigation, not in-entry routing.**
`/admin` is a separate Vite entry and a separate document; the entries have no
shared router, and the HttpOnly session cookie travels with a document navigation
(`frontend-structure.md`). It is a real `<a href="/admin">`, which is also what
makes middle-click behave.

The item is **absent** for a roleplayer, not disabled (US-093.AC-2). Absence is
the frontend half of the same posture as the separate bundle: the roleplayer's
document should not name the admin area at all. The boundary itself is still the
backend's `require_role` (R5, `backend-structure.md`); hiding the link changes
nothing but what is offered.

Bottom-left rather than a header corner because the tree's footer is the one part
of the shell that survives collapse (US-090), so the menu stays reachable in both
states without a second placement.

---

## The model picker

**Realizes:** FEAT-013, UC-077, US-105

A select **above the stream**, in the session's header, showing the enabled models.
Choosing one **writes the session's override and it persists** (US-105) — it is not
a per-request choice and there is no "just this once".

R1 governs what the picker shows as current and R4 governs what happens when the
chosen reference stops being enabled; neither is restated here. Two consequences
for this surface specifically:

- The picker's value is the **resolved reference** (R1), which for a session that
  has composed at least once is the materialised `sessions.model_ref`
  (`data-model.md`). It is not a blank waiting to be filled.
- With no enabled model at all the picker says so and the composer cannot send
  (US-107). It does not fall back and it does not hide.

The session's tool switches sit beside it as indicators of the resolved
configuration (FEAT-013). Full session configuration remains its own surface; the
header carries the one control UC-077 puts there and no more.

---

## Reversal record — the two splitters and the fixed-height answer box

`ui-conventions.md` carried three interlocking decisions that are **deleted, not
moved**. Recorded here with their reasoning, because a deletion with no record
reads as an oversight and gets restored.

| Deleted | What it was |
|---|---|
| **(A) Aside width** | A hand-rolled horizontal splitter, right-anchored, `vw`-based, driven through a CSS custom property by one MobX `autorun`; default `0.35`, min `0.15`, max `0.60`, keyboard step `0.02`; the `calc(var(--rph-aside-width, 35vw))` wrapper recorded as load-bearing against Mantine's `rem()`; `AppShell transitionDuration = 0` while dragging |
| **(B) Answer-box height** | A hand-rolled vertical splitter, delta-based, on a plain MobX observable; min `64px`, default `96px`, max `0.5 × viewportHeight`, step `24px`; the short-screen clamp where the lower bound wins |
| **(C) No auto-grow** | The answer textarea deliberately did not auto-grow: `resize: "none"`, no `autosize`, no `minRows`/`maxRows`, scrolling internally |

**Why they go.** `docs/product/` specifies **no** resizable column anywhere. The
only drag it requires is note reordering on the wall (US-102, US-103), and the
settled mockup uses fixed widths throughout. Two hand-rolled splitters, two stored
numbers, two clamp functions and two distinct performance strategies existed to
serve a layout the product no longer asks for. (B) went further than obsolete: its
subject, the answer box, was removed from the product outright — there is no
dedicated answer box, only the current zone and a composer.

**(C) is reversed, not merely deleted.** The composer grows with its content. The
old reasoning was sound *given* (B): auto-growth fights an explicitly-set height on
every keystroke, and a native resize grip would have collided with the (B) handle.
With (B) gone, both arguments go with it, and the remaining fact is that a
roleplayer writing a paragraph should not be typing into a two-line box that
scrolls. Named as a reversal so nobody restores `resize: "none"` by citing the old
paragraph.

**What was genuinely lost.** (A)'s custom-property channel gave a pointer-move
zero component re-renders, and `frontend-structure.md` cited it as the concrete
justification for MobX over a reducer store — which this deletion turned into a
live reference to a section that no longer existed. That has since been dealt
with in the pass that revised `frontend-structure.md`: the citation was **removed
rather than re-pointed**, because there is no text at the other end of it, and
MobX was re-argued there on three grounds that survive the deletion (the SSE
consumer's per-token writes, per-page stores with no context, and blur-save round
trips that touch one row). No replacement measurement was invented; (A) was that
doc's one measurement-shaped claim and it is simply gone.

**Flip condition.** If the roleplayer later asks to widen the wall or the tree,
(A) returns: a splitter on that one boundary, and `WorkspaceLayout` regains a
number plus its clamp and its clamped read. The removed design — handle geometry,
the pointer-event choices, the `calc()` gotcha, the clamp edge cases — is
recoverable in full from git history, and should be recovered rather than
re-derived. (B) and (C) do not return; their subject no longer exists.
