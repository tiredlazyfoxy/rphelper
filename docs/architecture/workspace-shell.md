# Workspace shell

**Realizes:** FEAT-006, FEAT-007, FEAT-008, FEAT-009, FEAT-010, FEAT-011,
FEAT-012, FEAT-013, FEAT-017, FEAT-018, FEAT-020, UC-021, UC-023, UC-032,
UC-035, UC-036, UC-037, UC-039, UC-040, UC-048, UC-062, UC-063, UC-064, UC-069,
UC-070, UC-071, UC-072, UC-073, UC-074, UC-075, UC-076, UC-077, UC-078, UC-079,
UC-080, UC-081, UC-082, UC-083, UC-084, UC-085, UC-086, UC-088, US-026, US-035,
US-040, US-053, US-059, US-079, US-080, US-088, US-089, US-090, US-091, US-092,
US-093, US-094, US-095, US-096, US-097, US-098, US-099, US-100, US-101, US-102,
US-103, US-104, US-105, US-107, US-109, US-110, US-112, US-113, US-114, US-115,
US-116, US-117, US-118, US-119, US-120, US-121, US-123, US-124, US-125, US-126,
US-128, US-132, US-133, US-134, US-135, US-139, US-141, US-142, US-143, US-145

The `app` entry's one screen: three columns, a stream with a ruler through it, and
a wall of notes. This doc holds the **shell** — geometry, the columns, the wall's
two modes, layout persistence, and the anatomy of the stream and the current zone.

Two sibling docs hold what is not the shell. **`ui-conventions.md`** holds icons,
the icon table, the shared `IconButton`, the accessibility floor and async
feedback. **`forms-and-lists.md`** holds the CRUD conventions — tables, the modal
rule and its named exceptions, the MobX draft form, the confirm convention and
the never-optimistic rule. Read all three; none repeats another.

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

**The shell grid itself is two tracks, not three** (016 D1). `.app` is
`nav | main`; the wall is **not** a track of the shell. It belongs to the session
screen's own ready render, one level down inside `main`, where the screen's grid is
the "centre grid" the wall's two modes below describe. US-095 therefore holds
**by construction**: no route and no state other than a loaded session renders a
wall at all. Recorded because a reader looking for the wall in the shell component
will not find it there.

```css
.app                  { display: grid; gap: 1px;
                        grid-template-columns: var(--navw, 252px) minmax(0, 1fr);
                        transition: grid-template-columns 150ms; }
.app.nav-collapsed    { --navw: 48px; }
.app-nav              { grid-column: 1; }
.app-main             { grid-column: 2; }    /* explicit — see below */
.app.nav-overlay-open .app-nav { position: absolute; /* lifted above .app-main */ }
@media (width < 820px) { /* the narrow rules — see below */ }
```

Five as-built rules in that block are load-bearing and none is obvious:

- **`.app-main` is placed in track 2 explicitly.** Without it, lifting the nav
  column out of the grid as a narrow-width overlay would let `main` fall back into
  track 1. This is the same class of rule as `minmax(0, 1fr)` below: a line whose
  absence breaks a case nobody is looking at.
- **`minmax(0, 1fr)` on the second track** — without the `0` minimum, a long
  unbroken line in the stream establishes the track's minimum width and pushes the
  tree off-screen.
- **The `1px` grid `gap` over a line-coloured background draws the column
  dividers**, so no column owns a border and there is no double-border seam where
  two panes meet. **The pair of tokens that makes this work is named, both
  halves**: the gap shows `var(--mantine-color-default-border)` — the only colour
  reference in `shell.css` — and each column paints
  `bg="var(--mantine-color-body)"` as a Mantine style prop. State both or the next
  stylesheet edit reintroduces a literal, or the next component edit drops the
  background and the "divider" becomes a stripe of page.
- **The transition is on `grid-template-columns`**, so the browser animates the
  collapse on its own.
- **The media query is written `(width < 820px)`**, and the same string is
  exported to TypeScript as `NARROW_VIEWPORT_QUERY` (below).

**Collapse is a class that re-points one custom property** (UC-070, US-090). It is
not a stored width, not a measured value and not an animation of two separate
elements. The consequence that matters: there is exactly one number to change, the
browser transitions `grid-template-columns` on its own, and nothing in React
re-renders when the column moves.

Collapsed, the tree is replaced by a **rail** carrying my-search, new-character and
expand (US-090); the user button stays, reduced to its avatar. The rail is the
same column at a different width, not a second component. As built (008 D4) the
rail's create is **"New character" only** — an `IconPlus` that navigates to
`/characters/new` — and not a menu: a rail 48px wide has room for one noun, and
setups and sessions are both children of a character and so belong on its page.
The rail's search button navigates to `/search`, whose behaviour FEAT-017 owns.

**The expanded tree header's search is a text input, not a button** (029 U4);
Enter submits to `/search?q=…`. The collapsed rail keeps the icon button, because
a 48px rail cannot hold a field. Two affordances for one feature, which is exactly
what US-118 asks for.

### Below 820px — one column, lifted

As built (008 D3, D11), and recorded because the doc previously said only "the
tree becomes an off-canvas overlay":

- The left track is **always 48px**: the rail is the only tree at that width.
- The rail's expand **lifts the same nav column out of the track** as an overlay
  above the centre, through the class `nav-overlay-open` on `.app`. It is the same
  component at a third presentation, not a fourth component.
- **The overlay's open state is not persisted**, and `navCollapsed` is **neither
  read nor written** at that width. The stored preference describes a two-column
  layout that does not exist here, so touching it would mean a roleplayer's wide
  screen remembered a narrow screen's gesture.
- **Dismissal is the column's own collapse control, any in-entry navigation, or
  crossing the threshold back.** There is **no click-outside and no backdrop** —
  both would need a second dismissal owner, and the overlay is opened by a
  deliberate press and closed by the thing the roleplayer came to do.

---

## Geometry — everything is fixed; nothing resizes

| Thing | Value | Why this value |
|---|---|---|
| Tree column, expanded | `252px` | fits a character name, plus a session row's start-time label with a setup label beside it |
| Tree column, collapsed | `48px` | one 28px icon button plus its padding; nothing else fits, and nothing else belongs |
| Wall, floating | `min(320px, 84vw)` | 320px reads a note body at 12px without wrapping every line; the `84vw` cap keeps a sliver of stream visible on a narrow screen so the overlay reads as an overlay |
| Wall, pinned | `320px` | no `vw` term — pinned, it is a grid column and the grid already bounds it |
| Stream column | `max-width: 720px`, centred, `padding-inline: 18px` | a measure for prose, not for the viewport; the stream is read, not scanned |
| Composer | same 720px / 18px as the stream | the composer is the stream's last item visually and must share its left edge |
| Composer text area | `min-height: 42px`, **no max**, no handle | about two lines to start |
| Responsive threshold | `820px` | below it the tree becomes a 48px rail with a lifted overlay, and a pinned wall reverts to floating |

**The tree row holds a start time, not a title** (011 D4, US-145). A session is
identified by its **start time** — `created_at` rendered `YYYY-MM-DD HH:MM` in
local time — because `docs/product/` asks for no session title and `sessions` has
no `title` column (`data-model.md`). The 252px reasoning above used to cite "a
session title"; the measure is unchanged, because a fixed-width timestamp plus a
dimmed setup label is about the same width as the title it replaced, and both fit.

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

**What `shell.css` holds, as built, and what it must never hold.** The boundary is
"layout only", and it is now checkable rather than aspirational —
`tests/stylesheets.test.ts` asserts it.

| In `shell.css` | Not in `shell.css` |
|---|---|
| `.app` (the grid, the `1px` gap, the transition), `.app.nav-collapsed`, `.app-nav`, `.app-main`, `.app.nav-overlay-open`'s lift, and the `(width < 820px)` media query (plan 008) | column backgrounds, padding and shadow — **Mantine style props** |
| the session screen's stream/wall layout: `.app-session`, `.app-session.wall-pinned`, `.app-stream`, `.app-wall`, `.app-wall.wall-open`, and `.app-session.wall-pinned .app-wall` (016 D11) | the wall's background and its drop shadow — Mantine's `Paper` |
| exactly one colour reference, the divider token above | any other colour, any typography, any component style |

016 added six selectors and **no new media query**: the narrow-width wall rule is
decided in TypeScript (below), not in a second query. `frontend-structure.md` owns
the two-stylesheet division as a convention.

---

## The wall has two modes

**Realizes:** UC-072, US-094, US-095

| Mode | CSS | Reads as |
|---|---|---|
| Floating | `position: absolute`, anchored to the stream's right edge, `transform: translateX(...)` + drop shadow, above the stream | a flyout you opened and will dismiss |
| Pinned | `position: relative`, a real column of the **session screen's** centre grid (`minmax(0,1fr) auto`), no shadow | part of the workspace |

Two modes rather than one because the two uses are different: glancing at a note
while writing a line, versus working through the notes themselves. The floating
mode must not cost the stream any width for a glance; the pinned mode must not
overlap the text the roleplayer is comparing against.

The transform-and-shadow floating mode is animated; the pinned mode is not,
because a grid column appearing is a layout change and animating it reflows the
stream on every frame.

**The state rules, as built** (016 D2) — each is a decision a reimplementation
would otherwise re-derive differently:

- **Opening never writes the layout record.** Opening is a glance.
- **The pin toggle writes it**, and the pin therefore survives a reload
  (US-094.AC-2) — it is the `wallPinned` boolean below. Whether the wall is *open*
  does not survive: pinning is a preference, and restoring a floating overlay over
  the stream on load would greet the roleplayer with a panel they have to dismiss.
- **Unpinning leaves the wall visible as a floating flyout.** Unpinning is a
  change of mode, not a dismissal.
- **Dismissing a pinned wall also unpins it** (UC-072 steps 4–5). Dismissal is the
  roleplayer saying they are done with the wall, and leaving the pin set would
  bring the column back on the next session they open.
- **The open flag resets per session.** It is a glance at *these* notes.
- **Below 820px a pinned wall is shown floating, only when opened, and dismissing
  it there only closes it** — so the **stored pin survives and widening restores
  the column**. This now cites `US-094.AC-3` and `US-094.AC-4`, which require
  exactly that; it was a planner interpretation when 016 shipped and the product
  has since ratified it.

**The wall is mounted while closed** (016 D3). It is slid out of view and carries
**`inert` plus `aria-hidden="true"`**; the **`hidden` attribute is deliberately
not used**, because it would kill the slide animation. Two consequences are the
point of the decision: the memo chain **loads once per session** rather than on
every open, and an **unsaved note edit survives a close**. The obvious
conditional render reloads the chain every time and throws the edit away.

**The narrow-width revert is decided in TypeScript, from
`NARROW_VIEWPORT_QUERY`** — the exact string `shell.css`'s media query uses
(016 D11) — and **not** by a second CSS media query. CSS alone cannot express "a
pinned wall at narrow width shows only when opened": that is a conjunction of a
stored preference, a transient open flag and a viewport condition, and only one of
the three is visible to CSS. Sharing the query string is what keeps the two
authorities from drifting apart; `useMediaQuery` reading it is a sanctioned
`@mantine/hooks` use (`ui-conventions.md`).

**With no session open the wall is not shown at all** (US-095). It is not shown
empty and not shown disabled: three of its four levels exist only relative to a
session (R2's chain). As noted above, this is structural rather than a check.

**Arriving with `?notes=open` opens the wall** (029 D8) — the landing target for a
my-search memo hit at session level. This does not change the rule that "open"
does not survive a reload: the parameter is an instruction carried by the
navigation that brought the roleplayer here, not stored state.

---

## Layout persistence

**Two** localStorage records, under two keys, in two pure modules.

```ts
// src/app/workspaceLayout.ts  →  key "rphelper.workspace-layout"
type WorkspaceLayout = {
  navCollapsed: boolean;
  wallPinned: boolean;
};

// src/app/treeCollapse.ts     →  key "rphelper.tree-collapsed"
//   a JSON array of collapsed character ids (strings)
```

The `rphelper.` prefix is retained from the previous design, and the reason it was
renamed from the sibling project's still stands: two applications sharing a key on
one host would read each other's layout, and these two are designed to run side by
side (`deployment.md`'s port table).

**Two keys rather than one record, deliberately** (011 D7). The tree's collapsed
set could have been a third field of `WorkspaceLayout`, and it must not be: that
reader **drops unknown keys on write** (below), so any version of the client that
had not grown the field yet would silently delete another version's collapsed set.
Separate keys make the two records independent, and a reader that drops unknowns
is safe precisely because it owns everything in its own key.

**`WorkspaceLayout` is two booleans and no numbers.** `asideWidth` and
`answerBoxHeight` are **gone** — both described geometry that no longer exists
(see the reversal record).

Rules, carried over because they were right for reasons that have not changed, and
now stated against the as-built modules:

- **Read is total and never throws.** Absent key, unparseable JSON, wrong types,
  missing fields — each case falls back **per field** to that field's default. The
  function returns a complete record; there is no partial result and no `null`.
  There are no clamps left to apply, because there are no numbers left to clamp.
  **A `getItem` that itself throws is one of those per-field fallback cases**
  (008 D8), not an exception the caller handles: Safari's private mode throws on
  read as well as write.
- **A stored payload carrying `asideWidth` or `answerBoxHeight` must be tolerated
  and ignored**, never rejected and never allowed to fail the parse. An existing
  install will have one. Stated explicitly because the obvious strict-schema parse
  rejects the whole record over an unknown key and silently resets a roleplayer's
  layout.
- **A write drops unknown keys**, because it serialises the **total read** rather
  than merging into the raw stored object (008 D8). This is a consequence, not an
  accident, and it is the reason the tree's collapsed set has its own key. Stated
  so it reads as intended.
- **Write is best-effort**, wrapped in `try`/`catch` and swallowed — private
  browsing and quota exhaustion both throw, and neither is worth interrupting a
  click for. A write merges its patch over a **fresh total read**, so the two
  fields cannot clobber each other.
- The record is written **on the toggle**, which is now the only time it can
  change. The old "never mid-drag" rule has nothing left to constrain.

**Persistence stays in pure, DOM-free modules**, and the mechanism that makes that
true is worth naming: **the storage is passed in as a parameter** — a minimal
`getItem` / `setItem` interface, or `null` — rather than reached for as a global
(008 D8). So the modules touch no `document`, no `window` and no React, and every
fallback path above is unit-testable with no DOM, which is what the pipeline's
test-coder needs (`docs/plans/CLAUDE.md`). `App` owns the real storage and threads
it to the two readers: `WorkspaceShell` and, through `SessionRoute`,
`SessionScreen` (016 D2).

---

## The stream — the settled record

**Realizes:** FEAT-009, UC-078, UC-082, US-109, US-110, US-123, US-124

Above the ruler is the record, read from the **`settled_entries` selectable** and
ordered by **`id`** — a snowflake is k-sortable, so `ORDER BY id` *is* the stream
order and there is no `position` column to consult (`data-model.md`). Every reader
goes through a named selectable; raw `messages` is touched only by settle and
re-open (R11).

Three kinds render differently, because they are three different things:

| `kind` | Rendering | Actions in the entry |
|---|---|---|
| `partner` | the partner's block, quoted surface | translate (FEAT-011), edit — **no copy** |
| `turn` | the roleplayer's own settled turn | edit, **copy as plain text** |
| `decision` | a dashed, accent-coloured card — visibly not roleplay prose (UC-081) | edit only — **no copy at all** (US-123) |

**A `partner` entry offers no copy either** (014 D7, user decision). UC-030,
UC-082 and US-033 all speak of copying *the roleplayer's own answer*; a partner
block is text they did not write and have no reason to post back to the site it
came from. The action is **absent**, not disabled — the same posture as a
decision's.

**Every per-entry action lives inside the entry.** There is no row toolbar, no
context menu and no separate action column: the actions sit in the entry's own
header. **Edit, copy, the translation flicker and re-open are one revealed
group**, and the reveal is `ui-conventions.md`'s — Mantine's `useHover` +
`useFocusWithin` + a touch query, applied as opacity so the controls stay in the
DOM and the tab order. The stream is a column of documents, not a table, so
`forms-and-lists.md`'s table-row overflow-menu rule does not reach here — that
rule exists to keep a *row* from collapsing under four icon buttons.

**Editing is in place and saves on focus loss** (US-109, US-110). There is no
modal — which is a **named exception** to `forms-and-lists.md`'s "create and edit
are always a `Modal`" rule, recorded there with the reason the two do not
conflict. As built (014 D1, D10):

- **"Edit entry" swaps the body for an autosizing plain textarea.** A settled
  entry is edited as plain text, not through the markdown editor — the editor is
  for authoring a note or a persona, and swapping a paragraph of prose for a
  WYSIWYG surface mid-stream is a different interaction from the one UC-078 asks
  for.
- **Blur commits.** Blank or unchanged text **sends nothing**.
- **The `PATCH` response replaces that one row**, not the stream
  (`forms-and-lists.md`'s narrowed re-load). A full stream re-load on every blur
  would re-scroll the roleplayer away from the line they are writing.
- **On failure the editor stays open with the typed text** (R10 — nothing the
  roleplayer typed is lost to a failure) and the entries are re-read.
- **An edit never re-parses `(( ))` and never changes `kind`** (R12).

Bodies are rendered with **`react-markdown`** through the one renderer,
`app/MessageBody.tsx` (`frontend-structure.md`). **Copy yields plain text, never
markdown** (US-124): the destination is a chat box on someone else's site, where
markdown source is noise. This is the product's entire outbound boundary
(`vision.md`), so the copy path reads the **stored text** and strips, rather than
serialising the rendered DOM.

**The stripper is `app/plainText.ts`, and it is the only one** (014 D8). Its rule
set: CommonMark **as rendered, without plugins** — GFM constructs are left as
typed, because nothing renders them either; syntax removed; **words and line
breaks kept**; unordered bullets become `• `; ordered numbers kept. The
authoritative rule list lives in plan 014's `002.context.md` and has not been
lifted into this doc, because it is a table of constructs rather than a design
decision. **One consequence is visible to the roleplayer and is required:**
`US-124.AC-2` strips asterisk-marked action markers along with the markdown, so
`*smiles*` arrives as `smiles`. That is the criterion, not a side effect.
`app/copyOut.ts` is the one clipboard writer, and on a **non-secure origin** —
which is every LAN address today — `navigator.clipboard` does not exist, so it
falls back to `execCommand("copy")` (014 D9, `deployment.md`'s TLS note). A
clipboard failure goes through `notifyFailure`; success raises nothing.

**Each settled entry carries its message id as a data attribute** (029 D8).
Arriving with `?entry=<messageId>` — the landing target for a my-search entry hit
— scrolls that entry into view **once** and highlights it for **2000 ms**. One
scroll rather than a sustained anchor, because the roleplayer's next action is to
read around it.

### A settled entry's buried discussion

**Realizes:** UC-036, US-040, US-113, US-116

Every settled **non-partner** entry carries a collapsed **"Discussion"** header
marked **"Read-only"** (022 D11, U1). As built:

- **The rows load lazily, on the first expand.** The stream read does not carry
  them.
- **The count appears once loaded** — the header reads "Discussion", then
  "Discussion (N)" after the first expand. `GET …/entries` carries no count, so
  the only alternative was **no count at all**, and a count that arrives with the
  rows is more useful than none: it tells the roleplayer how much they just
  opened, and on every later expand of the same entry it is there before they
  look. This is the documented form.
  `US-040.AC-2` and `US-040.AC-3` now require that **no message is shown before
  the group is opened**, which is what the lazy read delivers — so the as-built
  shape satisfies the criterion rather than straining against it.
- **An empty group says so**, and a load failure renders **inline inside the
  group**, not as a notification (`ui-conventions.md`'s boundary — the group is on
  screen and is where the roleplayer is looking).
- **The rows render with no edit control.** The server half is the `PATCH`
  refusal of a buried row (`message_not_editable`, R7, R11).

**"Opening a discussion" has no control of its own** (022 D12). The zone *is* the
discussion: it opens with the first message written on *my turn*, and the collapse
on settling is the settle re-read moving those rows into the entry's Discussion
group. Nothing creates or names a discussion, which is the whole point of the
`discussions` table having been removed (`data-model.md`).

### Re-open

Re-open is offered **only while the current zone is empty** (US-128) — the
affordance is *absent*, not disabled, once anything is in the zone, because at
that point the action does not exist. R11 says what re-open does; this doc says
where the control is.

As built (013 D4, user decision): an **`IconArrowBackUp` `IconButton` labelled
"Re-open last entry"**, inside the **last** settled entry, present only when the
zone has no rows and that entry's kind is not `partner`. **The composer's content
does not gate it** — an unsent draft is not a zone row.

**The accepted imprecision, and why it is accepted.** The client cannot see
whether a buried group exists without fetching it, so the control also shows on a
**lone directly-settled turn or decision**, where the server refuses with
`nothing_to_reopen` (R11). The refusal is surfaced through `notifyFailure` and
followed by a re-read. The cost is a wasted click on an entry that has no
discussion; the alternative was a second request on every zone transition to
answer a question that is usually "no".

**The flip condition is now reachable and was deliberately not taken.** Plan 022
**built** the buried-group read (`GET /api/messages/{id}/discussion`), which would
let the client hide the control exactly, and **chose not to use it for this** — to
keep `GET …/entries` and re-open untouched. So the imprecision stands as a
decision, not as a limitation: closing it is a small client change against an
existing route whenever it is judged worth one request per zone-empty transition.

### The search-coverage banner

**Realizes:** US-112

A banner sits above the stream saying search coverage is incomplete. It never
blocks an edit — the edit saves either way, and the banner is the honest statement
of the consequence (`search-and-retrieval.md` and `session-stream.md` hold the
degraded write path, and `docs/plans/defects.md` records where that path falls
short of US-112.AC-1 and US-112.AC-3).

**As built the banner is narrower than "when no embedding model is configured",
and the narrowness is deliberate** (024 D11):

- It is driven by the **latest record-keeping write's response in this view** —
  settle, re-open, a settled edit, a partner filing — through the
  `search_coverage_incomplete` flag those responses carry
  (`session-stream.md`).
- It **starts hidden on mount**, because nothing persists staleness.
- It is **cleared by the next fully indexed write**.
- It has **no close button**: it is a statement about the last write, not a
  notice to acknowledge.

The consequence, stated plainly: **a model removed while the roleplayer only reads
shows no banner.** US-112.AC-2 is satisfied on the write that degrades, which is
what the criterion asks for. Whether the roleplayer should *also* be told on open,
with no write at all, is **not specified** — and it would need a persisted
staleness signal, which 024 U5 declined (no marker, no column). That absence is
left visible rather than papered over: this is the one place a reader would expect
to find the answer, and the answer is that the question is open at the product
layer, not that the design chose silence.

---

## The ruler and the current zone

**Realizes:** FEAT-010, UC-079, UC-083, US-114, US-115, US-125

**One visible separator**, and below it the live chat read from the
**`current_zone` selectable**. One ruler and one zone per session — the zone is
a set of rows, not a row, so there is nothing that can duplicate (R11,
`data-model.md`). As built the ruler is a Mantine **`Divider` labelled "Current
zone"**, and it is the stream's **only** `separator` role (013 D12) — so "one
visible separator" is checkable rather than descriptive.

### Editability

- **Every message in the zone is editable by the roleplayer, the assistant's
  included** (US-115). Edited in place, same as a settled entry. This is not a
  courtesy affordance — it is the mechanism R7 and R11 depend on, because settle
  reads whatever the row holds at that moment. As built (013 D10): an `IconEdit`
  control swaps the body for an autosizing textarea, blur commits, blank or
  unchanged text sends nothing, the `PATCH` response replaces that one row, and on
  failure the editor **stays open with the typed text** (R10) and the zone is
  re-read.
- **An assistant row is edited as its raw stored text, `<think>` tags included**
  (022 D10). The server strips them at settle (R12's parallel `<think>` rule), so
  what the roleplayer edits is what is stored and what they see is not a second,
  cleaned copy they cannot reach.
- **A tool row carries no edit control, and this is settled rather than a
  shortfall.** `US-115.AC-1` now carries a **`Constraint:`** stating that a tool's
  own record is not a message anyone wrote and is not editable. The build matches
  the criterion: a tool row's text summarises a payload the model produced and the
  server recorded, so an "edit" to it would be a forgery of a call that happened
  (021 D8, R11's head rule). **No defect.**
- **The live reply has no edit control, and that is `docs/plans/defects.md` D-02.**
  While streaming, the read-only live reply renders beneath the zone rows
  (below); only once the stream ends and the zone re-read brings in the persisted
  row is that row editable like any other zone message. **The reason the build
  gives is real, not an oversight** (022 D6, U4): an edit in flight would **race
  the server's own write of that row** (019 D11), and would be either lost or
  clobbering. Recorded as a defect against `US-115.AC-1`'s streaming half, with
  the note that **D-02 carries an open alternative reading** — that US-115.AC-1 is
  conditioned on a message *sitting in* the zone, which an unpersisted in-flight
  reply is not, in which case D-02 is a clarification of the criterion rather than
  a defect. That reading is **recorded and not resolved**; whichever way it goes,
  a repair must first decide what happens to an in-flight edit when the persisted
  row arrives.

### Tool and thinking blocks

**Tool calls and thinking are collapsible blocks** in the zone (US-114). They are
persisted rows (`role='tool'`, and `<think>` text inside the assistant row —
`data-model.md`), not transient UI state, which is why a reload does not lose
them.

As built (022 D5):

- **Open in the live reply, collapsed on every persisted row** — in the zone and
  in a settled entry's discussion group alike. Open while the assistant works,
  tucked away once it finishes, which is exactly US-114's shape.
- **The open flag is component-local and initialised once**, so the live →
  persisted swap is a **remount**, not a state change. That is what produces the
  collapse without any code that closes anything.
- **A collapsed body is not rendered at all**, rather than rendered and hidden.
- `IconTool` is decorative beside the tool's name, `IconBulb` beside "Thinking",
  and the rotated `IconChevronDown` is the control (`ui-conventions.md`).

### The live reply

**Realizes:** UC-079, US-132

While a generation streams, a **read-only "Live reply"** renders **beneath the
zone rows** (022 U4): the live tool blocks first, in arrival order, then the
streaming text with its thinking block open. It has **no edit control** (D-02
above).

The mechanism is `frontend-structure.md`'s: tokens append to a dedicated
observable **streaming text** field on `StreamState`, and the tool frames maintain
an observable **live tool list** keyed by call id — neither writes into `zone`.
**Every outcome of the stream replaces the live reply with the server's rows by a
zone re-read**, and the streaming text and the tool list are cleared in the same
action that applies them. So the live reply is a view of an in-flight response and
never a row the client invented; a client-minted id can never reach
`PATCH /api/messages/{id}`.

**This is 022's final shape and it supersedes 019's open question.** Plan 019
recorded the token-handling divergence and deferred the editability call to 022;
022 decided. There is no open question here.

### Failure, retry and the model gate

- A live assistant message streams into the zone through the SSE consumer
  (`frontend-structure.md`); an `error` frame leaves everything already in the
  zone intact (R10).
- **A failed generation shows its reason as a transient notification and leaves a
  persistent retry in the zone** (US-044.AC-2, AC-3, AC-4). The split is
  deliberate and `ui-conventions.md` owns it: the **reason** is what the product
  says must not persist, so it goes to the ~5s notification; the **retry** must
  remain available, so it sits in the zone.
- **The retry is a labelled "Regenerate" button after the last zone row**
  (022 D8, U3), present **iff** nothing is streaming, nothing else is in flight,
  and a **non-tool** zone row exists; **absent, not disabled**, otherwise. It
  issues a **textless** compose, inserting no row (R10, 021 D2), and it is
  **derived from persisted rows**, so it survives a reload — which a notification
  could not. **It is a general regenerate, available after any exchange and not
  only a failed one**, and `US-044.AC-3`'s widened form plus `US-044.AC-5` now
  require exactly that: the same control on any exchange, failed or not. The
  widening that 022 flagged is ratified.
  It is **not** gated by the send-blocked reason below: with no usable model a
  regenerate fails with the compose's own typed error through `notifyFailure` and
  the zone is untouched.
- **With no enabled model the composer cannot send and says why** (US-107). The
  typed error is R4's, surfaced here rather than swallowed. As built (017 D17) the
  gate is narrow and deliberately so: **Send is disabled with a fixed reason, and
  only on *my turn***. Settle, partner filing and a partner paste stay available,
  because none of them calls a model — a roleplayer with no model configured must
  still be able to keep their record. An **unknown** usability state (the model
  list still loading, or failed to load) **never blocks**: a list that could not
  load is not evidence that there is no model. `US-144` carries the companion
  refusal for a session holding no chosen model, which is a different refusal from
  US-107's.

---

## The kind switch and settle

**Realizes:** UC-035, UC-081, UC-084, US-120, US-121, US-126, US-129, US-130

A **two-position switch** above the zone — *partner* and *my turn* — declaring what
the zone will file.

**The default is the alternate of the last `partner` / `turn` entry, computed
client-side, with decisions skipped** (US-120, US-120.AC-3; 012 D5, 013 D8) —
because a roleplay alternates and the default should be right without a click. A
settled **decision** does not participate: it is not a side of the roleplay, so
alternating off it would mean the switch's position depended on whether the
roleplayer happened to record a note.

**With no such entry at all the default is *my turn*** (013 D8), and the reason is
an asymmetry of cost rather than a guess at intent: a wrong *partner* default
files the roleplayer's own first paste as a **partner block, which is born settled
and is not re-openable** (R11, US-121) — an error that cannot be undone from the
UI — while a wrong *my turn* default costs one click. `US-034` expects opening a
session with the roleplayer's own entry to work, so neither position is rare
enough to privilege on frequency. **The earlier `_TBD:` here is closed**:
`US-120.AC-3` settles what a settled decision does to the default, and 013 D8
settles the empty-record case.

A manual choice holds until the record's id sequence changes, or until Discard
resets it.

- On **partner**, a paste **files itself immediately** with no Settle press
  (US-121). As built (013 D7, 012 D14) the paste is intercepted and filed through
  `POST …/entries`, **the composer's content is untouched**, and **Send on
  *partner* files the typed text as a partner block**. There is no zone
  precondition either way. There is nothing to compose for text the roleplayer did
  not write, so the Settle control is disabled in this position rather than hidden
  — the switch's two positions must read as two modes of the same box.
- On **my turn**, **Send composes** (plan 021, step 007): it posts the typed text
  to `POST /api/sessions/{id}/zone/compose`, the one streaming route, so the
  roleplayer's message is committed and the assistant's reply streams back in one
  exchange (`session-stream.md`, `llm-and-streaming.md`). **It is not the plain
  append.** Plan 013 wired this control to the non-streaming
  `POST …/zone/messages` while no compose route existed; plan 021 mounted the
  route and moved it, and that is the as-built behaviour. The non-streaming
  sibling remains the route behind a partner filing and behind the character
  page's first message, neither of which calls a model — which is why the two
  routes are two routes (`session-stream.md`).
- On **my turn**, **Settle takes the last message in the zone, whoever wrote it**
  (US-126) — excluding `role='tool'` rows, which R11 explains.

**Settle's conditions, as built** (013 D2, user decision; 022 D9):

- On *my turn*, Settle is **enabled when the zone holds a non-tool row, or the
  composer holds non-blank text**. Pressing it with composer text **appends that
  text and then settles** — two requests, and a failed settle leaves the appended
  row sitting in the zone, which is the correct outcome under R10.
- It is **disabled while a mutation is in flight**. The doc's older sentence "its
  only disabled condition is an empty zone" was literally false once in-flight
  disabling existed, and is corrected here rather than quietly contradicted.
- **A generation in flight does not disable it** — see the stop control below.
- **The client counts non-tool rows**, exactly as the server's head rule does
  (022 D9, 021 D8), so `canSettle` and the server's `zone_empty` agree by
  construction rather than by coincidence.

**Settle never requires an assistant answer** (US-135). A zone holding only the
roleplayer's own message settles that text as-is; the button is not disabled while
waiting for a reply that may never come, and there is no "wait for the assistant"
state. Stated here because a Settle greyed out until an assistant row exists is
the obvious implementation and is exactly the trap US-134/US-135 were written to
close.

**Settle and Send are labelled buttons, not icons.** Settle is the most
consequential action in the product and is the primary button; Send is secondary.
This resolved the open `_TBD:` that proposed `IconMessageCheck`
(`ui-conventions.md`).

### The enormous-paste warning sits on the composer, and only there

**Realizes:** US-035

As built (014 D3, D5, user decision): a paste into the **composer**, in **either**
switch position, whose non-blank text exceeds the threshold raises a yellow
`notifyWarning` about the context cost. The threshold and its two named constants
are R10's (`app/pasteCost.ts`, an estimate of characters ÷ 4 against 32,000
tokens — roughly 128,000 characters); `ui-conventions.md` owns the warning
channel.

Two boundaries are the point of recording it here:

- **It never prevents, delays or alters the paste or the filing.** R10 forbids
  turning an advisory notice into a refusal, and a partner paste on *partner*
  files itself immediately regardless (US-121). The warning arrives beside an
  action that has already happened.
- **Pastes into an *editor* do not warn** — not a settled entry's, not a zone
  message's, not a note's. Editing existing text is not adding to the exchange's
  cost in the way a new paste is, and a warning on every long edit would be noise
  attached to the product's most ordinary action.

### The preview, and where `(( ))` is painted

The client **previews** what settling will do — whether the target will file as a
`turn` or a `decision`, and whether a `(( ))` fragment will be stripped. **The
client previews; the server decides** (R12's three-layer split). The preview
exists because the classification is invisible otherwise and the roleplayer finds
out only afterwards; it is never authoritative, and a client that disagreed with
the server would be a display bug, not a data one.

As built (013 D1, user decision):

- The preview is a **client-side port of the server's `(( ))` rules**, in the pure
  module **`app/parens.ts`** — the one client port, used by the preview and the
  zone painting and nothing else (R12's layer table).
- It renders as **one of three fixed sentences under the composer**, on *my turn*,
  when there is something to settle.
- It previews the **settle target**: the composer text when non-blank, otherwise
  the last zone message. So it previews what Settle will actually act on, not
  whichever is nearer to hand.

**Painting applies in the zone only** (013 D5). In the zone, a wholly-parenthesised
message renders as an out-of-character block and a fragment as an inline chip —
display over the stored text, since R12's "parse once, at settle" means nothing
here rewrites what is stored. **Above the ruler, nothing is painted from
parentheses**: a settled `decision` renders its dashed card **by `kind`**, and
settled `partner` and `turn` entries render plain markdown. Two reasons, and both
matter: partner parentheses are the **partner's own words** (US-121.AC-2) and
painting them would mark the partner's prose as an instruction, and painting a
settled turn would mean **re-parsing stored text**, which R12 forbids outright.

---

## The stop control

**Realizes:** FEAT-010, UC-085, US-132, US-133

An `IconPlayerStop` `IconButton` labelled **"Stop"** in the composer, reaching
**the model work the composer started** — a discussion generation and any tool
call it is waiting on (UC-085, US-133).

**It does not reach a partner-text translation.** A pending translation is
cancelled by **its own flicker**, which reads **"Cancel translation"** while
pending (023 D4, user decision; `ui-conventions.md`'s `IconLanguage` note). So
there are **two stop controls, one per thing that can be stopped**, and the
asymmetry is deliberate: a translation is started from a settled entry far up the
stream and may be one of several, so a single global stop could not say *which*
translation it was about to cancel, while the flicker that started this one is
sitting right beside the text it is translating. `llm-and-streaming.md` records
the decision, its reasoning and the server-side best-effort check; it is not
re-argued here.

**Stop replaces Send while a generation is streaming; it does not accompany it.**
Send and Stop occupy the same slot and are never both present — Send is **absent**
while streaming (019 D13). Reasoning, since both arrangements are defensible:

- The two are **mutually exclusive in fact** — there is nothing to send while a
  reply is streaming into the zone, and nothing to stop when none is. Rendering
  both means one is always inert, and an inert primary-adjacent control is worse
  than an absent one.
- It matches the existing treatment of a control whose action does not currently
  exist: `IconArrowBackUp` is **absent** rather than disabled once the zone is
  non-empty (US-128), and the discard affordance below is absent rather than
  disabled for the same reason.
- The slot is stable, so the roleplayer's pointer does not have to move between
  "send" and "stop" — which matters because stopping a runaway generation is an
  urgent action and the loop has no iteration cap to stop it for them
  (`llm-and-streaming.md`).

**Settle is unaffected and stays exactly where it is.** It remains the primary
labelled button beside the Send/Stop slot, enabled or not on its own rules above
— a generation in flight does not disable it, because the zone may already hold a
message worth settling.

**Pressing Settle mid-stream stops the compose first** (019 D16, user-confirmed),
exactly as Stop does and **with no notice**: it waits for the compose's own
post-stop zone re-read, then settles, then re-reads both lists. The roleplayer
asked to file what is there; interrupting them to say that a generation was
cancelled would be reporting an operation they implicitly ordered.

What pressing Stop does, in one line each (`llm-and-streaming.md` and
`session-stream.md` own the mechanism): it **aborts the in-flight `fetch()`** —
there is no stop request — the server persists whatever assistant text had
streamed as an ordinary zone message, and the client **reloads the zone** to pick
it up. The partial text is then a candidate like any other: editable, promotable,
settleable (US-132.AC-1). **No error is shown**, because nothing failed.

Three consequences visible on this surface:

- **A stop during a tool call ends the exchange** — no wrap-up, no final answer —
  and the candidate left behind may be **empty** if nothing had streamed yet. The
  zone is then an ordinary empty zone and is discardable below. `US-133.AC-1`
  states this, so it is a requirement the build meets rather than a deviation.
- **A stopped translation leaves the original text showing** and the flicker
  un-flicked, exactly as a failed translation does (R8).
- **The partial row's commit may land either side of a mid-stream settle, and this
  race is accepted** (019 D17, user-accepted). The server's disconnect-persist may
  commit before or after the settle. If after, the partial appears as a candidate
  in the **fresh** zone, below the entry just settled — **not lost, one zone
  later**. Likewise a plain stop's re-read may run before the persist commits, in
  which case the partial appears on the next re-read. Recorded rather than
  engineered around: the alternative is a handshake between a disconnect and a
  settle, for an outcome where nothing is lost either way.

---

## Discarding an empty current zone

**Realizes:** UC-086, US-134, US-135

An affordance beside the composer, and its reach is narrower than it looks.

**It is present only while the zone has no rows and the composer holds nothing but
whitespace.** Pressing it clears that whitespace and **resets the kind switch to
its computed default**. **It never discards typed text** — UC-086's postcondition
read literally, and `US-134.AC-2`. **Absent — not disabled — otherwise**
(013 D3, user decision).

So the control is not "throw away my draft". It is the exit from a zone that
exists but holds nothing: the one state a roleplayer can reach and then be unsure
how to leave. Stated this way because the doc's earlier wording — "clears the
unsent draft and resets the kind switch" — implied a discard of written text,
which the postcondition forbids, and because a control that *could* throw away a
paragraph is a control that eventually does.

The glyph is **`IconX`**, labelled **"Discard empty zone"** (013 D3). `IconX`
already means "dismiss" on the wall, and `IconTrash` would promise the deletion of
content that, by the rule above, is never there.

**It is frontend-only. There is no route and no backend surface.** An empty
current zone has **no rows at all** — R11 defines the zone as the rows matching
`related_to IS NULL AND settled_at IS NULL`, so an empty one is an empty set. The
server has nothing to discard, and **R11 is therefore unchanged**: raw `messages`
is still touched by exactly two operations, settle and re-open. A planner who
adds a discard route breaks that invariant for no gain, and this paragraph is
here to be cited when one proposes it.

The absent-not-disabled posture follows the existing precedent exactly: re-open's
`IconArrowBackUp` is **absent** rather than disabled once the zone is non-empty
(US-128), on the principle that a control for an action that does not currently
exist should not be drawn at all. A disabled discard button would also read as a
promise — "you could throw this away if you fixed something" — which is precisely
what US-134.AC-2 rules out.

**US-134 and US-135 are a pair, and the pairing is the point.** Together they
close an inescapable state: a zone holding text that could be neither discarded
(US-134.AC-2) nor settled would trap the roleplayer with no way forward.
US-135 is the escape — settling never requires an assistant answer — so *every*
zone has at least one exit at all times: empty ones discard, non-empty ones
settle. Neither rule is safe without the other, and removing either re-opens the
trap.

---

## The wall's contents

**Realizes:** FEAT-012, UC-075, UC-076, UC-088, US-098, US-099, US-100, US-101,
US-102, US-103, US-104, US-119, US-141

The wall's landmark is a **complementary region named "Note wall"**, holding the
"Notes" region the session screen already had (016 D4).

Notes are **sticky-note bars**: one body of text, no title field, no header
(US-119, and `memos` has no `title` column). A note is identified by its text, so
the text is the whole card.

**Two independent icons per note**, matching R3's two booleans exactly:
enabled/disabled and forced. They are two controls because they are two axes — a
disabled note keeps its forced flag, and a single tri-state control cannot express
that (R3, US-101). **Both are always visible** (`ui-conventions.md`'s
accessibility floor, where the deliberate difference from the stream's revealed
actions is recorded). A disabled note renders struck through and dimmed but keeps
its forced marker visible, so the state that will be restored on re-enable is
readable before re-enabling.

Each note carries a one-line statement of its current reach — forced, searchable
or disabled — because the two icons say what is *set* and the roleplayer needs to
know what it *does*. R3's predicate ordering is what that line states: `is_enabled`
gates first, and a disabled note reaches the assistant by no path whatever
`is_forced` says. **The wording describes forced and searchable behaviour that
only became real once context assembly and `memo_search` landed** (015 D7, plans
020 and 026) — written when neither existed, and true now.

Notes are **grouped by level in a fixed order — user, character, setup, session**
(US-103.AC-1), which is R2's chain order. The level headers are the only structure;
there is no collapsing, no filtering and no search inside the wall (my-search
covers finding a note, FEAT-017).

**The wall's chain state is separate from the character page's level state**
(016 D4) — the answer to the question plan 015 left open. They are **never on
screen together** (US-095: no session, no wall), and each loads on mount. One
shared store would exist only to serve a co-occurrence that cannot happen.

### Editing, creating and removing a note

**Edited in place, saved on focus loss** (US-104) — the same interaction as a
stream entry, for the same reason. As built (015):

- **Plus a flush on unmount**, because blur is not reliably fired when the element
  is removed — closing the wall, navigating away or settling can all remove a card
  mid-edit, and a blur-only save loses the last thing typed.
- **A new note opens at the top of its level, with focus in its body, and stays
  first once saved** (016 D5, D9; `US-102.AC-2` now requires exactly that — a
  newly created note holds the first position in its level until reordered). The
  focus half was 015's deferral: `shared/MarkdownEditor` had no focus hook, and
  016 added an optional `autoFocus` for it.
- **A blank new note is dropped with no request.** Nothing is persisted for an
  empty note until there is something to persist.
- **The unsaved new note shows no flag controls and no reach line** (015 D13).
  There is no row to toggle yet, and a reach statement about a note that does not
  exist would be a prediction.
- **Clearing all the text of a saved note deletes it** (UC-088, US-141). This was
  a plan-time user decision with no story behind it when 015 shipped; the product
  layer has since recorded it, and `US-141` is now the requirement — a saved note
  is removed by emptying it, and a new note with no text is never persisted. The
  two halves are one rule seen from either end.
- A note is created **enabled and not forced** (R3, US-053), directly in its level.

### `@dnd-kit` is finally used

Note reordering within a level (UC-076, US-102) is the project's **first and only**
drag interaction. `frontend-structure.md` records `@dnd-kit` as available with
nothing requiring it; US-102 is that requirement.

- **A note cannot cross a level boundary by dragging** (US-103.AC-2). The
  constraint is enforced in a **pure drop-decision function plus the drop
  effect**, not only signalled in the drag preview: `memos.sort_key` is scoped
  within `(scope, scope_id)` and nowhere wider (`data-model.md`), so a cross-level
  move is not expressible in the schema and must not be expressible in the UI
  either. The route carries one level per request, so it is inexpressible on the
  wire too (`session-stream.md`).
- Reordering is not decoration — it **changes what the system prompt contains**,
  because forced notes enter it in the arranged order within their level (R3,
  US-102). That is also why it must be reachable without a pointer: `@dnd-kit`'s
  keyboard sensor is required, not optional, on the same principle the deleted
  splitters were held to.
- **The mechanics, as built** (016 D8): one `DndContext` over the chain and one
  `SortableContext` per level; a `PointerSensor` with a **6px distance
  constraint** and a `KeyboardSensor` with sortable keyboard coordinates; the
  **whole card** is the drag surface, focusable, keeping role `listitem` and named
  "Note &lt;n&gt; of &lt;total&gt;"; announcements name **positions, never ids**.
- **A card is not draggable** while its editor has focus, while that level's
  reorder is in flight, or as the unsaved new note.
- **Reorder is opt-in on the shared group** (`reorderable`), which is how the
  character page's notes grid shares the same components without reordering until
  018 turned it on.
- **A reorder failure renders inline, per level** — "Could not reorder the
  notes." — and the order reverts. This is the product's one sanctioned optimistic
  mutation; `forms-and-lists.md` holds the rule, the user's reason and why it does
  not erode the never-optimistic rule.

**A press-and-move that begins on an unfocused card is a drag, and that is the
accepted reading** (016 D8, user decision 2026-10-06). This doc used to say
flatly that "a text selection inside [a card] must not start a drag". The accurate
rule is narrower: **selection works once the card's editor has focus** — at which
point the card is not draggable at all — while a press-and-move beginning on an
**unfocused** card **is** a drag, under the 6px distance constraint. The reason
this is accepted rather than tightened: the whole card is the drag surface by user
decision, because a separate grip handle on a card whose entire content is one
text body is a second affordance competing for the same few hundred pixels. The
6px constraint and the focus rule together mean the only lost gesture is
selecting text in a card you have not yet clicked into — one extra click, against
a drag target that is the whole card. Keyboard activation additionally fires only
when the card element itself is the event target, so keys typed in the editor
never start a drag.

---

## The character page

**Realizes:** UC-073, UC-074, UC-080, US-096, US-097, US-117

The same shell with **two columns instead of three**: tree, and a body that holds
the character's persona, its notes, its setups, its resolved configuration and its
sessions in one place (US-096).

**The two columns hold by construction, and `shell.css` gained nothing for this
page** (018 D10): the shell grid is `nav | main`, and the wall exists only inside
the session screen (US-095) — so a page that is not a session simply has no third
column to suppress.

**The body's order, as built** (018 D12):

```
header
  → name + persona  (+ Archive / Restore, + Export)
  → notes grid
  → setups
  → configuration
  → sessions
  → composer
```

**This is the same components in a different arrangement, not a second design.**
The note card, the in-place edit and the reorder behave identically in both
places; only the container differs. Stated because the obvious implementation
forks a second note component for the character page and the two then drift.

**The notes grid is the shared group with an opt-in grid layout** (018 D8) — the
same `MemoLevelGroup` the wall uses, with a rect sorting strategy when
reorderable, inside the character section's **own** `DndContext`. The sensors and
the position-only announcements are shared through one module,
`app/memoDnd.ts`, so two drag contexts keep **one** keyboard path. **No second
card component and no second group component exists**, which is what makes "same
components, different arrangement" a checkable claim rather than an intention.

### Setups, configuration and sessions

- **Setups** (plan 010, rebuilt by 018 into the page's setups block): "New setup"
  as a labelled `IconPlus` button, a "Show archived setups" switch, a table of
  setups with a per-row overflow menu (Edit / Archive / Restore), create and edit
  in a modal, and the neutral empty line "No setups yet."
  (`forms-and-lists.md`).
- **Configuration** (018 D9, realizing UC-048 / US-059's UI, which 017 left
  without a caller): the model as a `Select` whose unset option reads **"First
  enabled model"**, the system prompt with blur-save and blank meaning unset, and
  **three tool switches** reading Default / On / Off. Each control shows **its
  resolved value and whether it is set on the character**, which is what makes an
  inheritance chain legible at the level you are editing. **No language fields** —
  `US-061.AC-3` puts the two languages on the user and session levels only,
  skipping the character. Failures render in place.
- **Sessions** (plan 011): a "Show archived sessions" switch, a table of sessions
  with a per-row Archive / Restore / Export menu, the neutral empty line "No
  sessions yet.", an **"Import session"** button (plan 031), and the inline start
  control below.

**The archive toggle is section-local everywhere, and nothing persists it**
(018 D11, closing a question 009, 010 and 011 each answered a part of). The tree
header's "Show archived" covers characters; the Setups section's "Show archived
setups" covers setups; the Sessions section's "Show archived sessions" covers
sessions. Archived rows appear **dimmed with an "Archived" badge** and offer
Restore in place of Archive. An archived object stays reachable by direct URL —
`/characters/:id` and `/sessions/:id` both open one, with the badge and without
its controls. **The `_TBD:` that asked where the toggle sits is closed in full**:
three sections, three toggles, none persisted, and no part left open. Not
persisted because showing archived material is a lookup, not a preference — a
roleplayer who wanted it permanently would be asking for archive not to exist.

### Starting a session — the named exception to the modal rule

**Realizes:** UC-021, UC-023, US-026

Two ways in, and they are two because they answer two different questions.

**With a setup: the Sessions section's inline start control** (011 D1, user
decision) — a **Setup select** defaulting to "No setup", beside a **"Start
session"** button. One POST, no message, then a push navigation to
`/sessions/<id>`.

**This is a named exception to "create and edit are always a `Modal`"**
(`forms-and-lists.md` carries it with the other two). A one-choice inline control
is **not a form**: there is one optional select and one button, and a modal around
that is a dialog whose entire content is a dropdown. The earlier sentence in this
doc — that the modal rule "continues to govern every create … including character,
setup and session creation" — **is corrected**: it governs **setup** creation,
while character creation is the draft-page exception and session creation is this
one. Both halves are stated, so the two docs cannot disagree.

The control starts a session perfectly well with an **empty or failed** setup list
(R2): a list that could not load must not become a precondition, and the failure
line beside it is non-blocking. An **archived** setup is not offered
(`setup_archived`, UC-021), while an existing session whose setup was later
archived keeps showing its label — R6 does not cascade.

### The composer, and starting a session by writing

The body ends with a **composer**, and writing a message in it is the other way a
roleplay begins: the instance creates a new session under the character with the
written message already in its current zone (UC-080, US-117.AC-1, US-117.AC-2).
There is no separate "create session" step to press first — that is the whole
point of the affordance.

**It is the same composer as the stream's, not a second one**, and that is now
true at the file level (018 D4): **`ComposerCore`** holds the text area, the
geometry above, the labelled Send, the enormous-paste warning and the
send-blocked reason, and the stream's `Composer` and the page's
`CharacterComposer` are its **two hosts**, adding only their own controls through
slots. Stated this way because the obvious implementation writes a second composer
for this page and the two then drift on the first change to either — the same
failure the note cards above are protected from.

What differs is **where it posts**: the stream's composer addresses an existing
session, and this one addresses the character, because at the moment of writing
there is no session to address. `session-stream.md` settles the route and why
creation and seeding are one request; `frontend-structure.md` owns the navigation
that follows. Once the session exists the roleplayer is in the workspace on it, so
this composer is used at most once per session it creates. It is an entry point,
not a second place to write.

**The page composer carries neither the kind switch nor a setup choice**
(`US-117.AC-4`; 018 D1 — closing the `_TBD:` that stood here). The reasons are
UC-080's own: there is no partner block yet for the switch's alternating default
to read, and UC-080 names no setup — so the session it creates has **`setup_id`
NULL**, which R2 makes a first-class case rather than a degraded one. The
roleplayer who wants a setup uses the Sessions section's start control above,
which exists for exactly that choice.

**The opening message draws no assistant reply, and that is
`docs/plans/defects.md` D-01.** `US-117.AC-3` and UC-080 step 5 require the
assistant to answer that first message as it would any other discussion message.
As built, the route creates the session and writes the message as a current-zone
row and **nothing answers it**; the roleplayer must send again on the session
screen to get a candidate. The design question is **closed** — yes, it should
draw a reply, and the create route stays JSON because the compose happens on the
session once it exists (018 D2). What is missing is the code: 018 deferred the
reply to a later plan and no later plan took it. Recorded as a defect, not as work
owed by a shipped plan.

### The draft page

Creating a character opens a **draft page** and persists nothing until the
roleplayer enters something (UC-074, US-097). A draft page rather than a create
modal is a named exception to the modal rule, and the product states the reason:
nothing is persisted until there is content, so there is no form to submit.

**As built** (018 D6, D7) — and the trigger is an interpretation worth stating,
because "persists nothing until something is entered" does not by itself say
*when* something counts as entered:

- A **"Draft" badge and a marker line**; **Name + Persona only** — no notes, no
  setups, no configuration, no sessions, no composer, because none of them can
  hang off a row that does not exist.
- **The character is created when the Name field loses focus holding non-blank
  text**, and the persona is sent with it. Blur on a non-blank name is the
  earliest moment the roleplayer has demonstrably decided on an identity for the
  thing.
- Both fields are **read-only while the create is in flight**, so a second blur
  cannot create a second character.
- Then a **`replace` navigation** to `/characters/:id` — replace rather than push,
  so Back does not return to a draft page for a character that now exists.
- From there, **name and persona save on focus loss** like everything else, a
  blank name is refused client-side, and pending edits are flushed on leaving.
- There is **no Create button**. Plan 009 shipped one as an interim and 018
  removed it, which is what `/characters/new` was always specified to be.

**Export sits beside Archive / Restore** (plan 030) — a `variant="default"` button
with `IconDownload`, rendered under the same condition as those two and therefore
**absent on the draft page**: there is nothing to export until the row exists.

---

## The user menu

**Realizes:** UC-062, UC-063, UC-071, US-079, US-080, US-091, US-092, US-093

Bottom-left, under the tree, opening upward from the user button.

**The trigger is an avatar button with the fixed accessible name "User menu"**
(008 D6): avatar plus username while the tree is expanded, avatar alone on the
collapsed rail. It wraps no Tabler icon, so `ui-conventions.md`'s `IconButton`
rule does not reach it — recorded there so it is not "fixed" into one.

| Item | Goes to |
|---|---|
| Settings | `/settings` — the two languages and the user's own notes (US-092) |
| Export my data | downloads a `user`-granularity export (UC-062, US-079) |
| Import… | takes a `user` or `character` export (UC-063, US-080) |
| Admin area | `/admin` — **shown only to ACT-001** (US-093) |
| Log out | ends the session (US-091) |

**Settings, as built** (017 D15): a **Languages form edited on the page with an
explicit Save** — the RP language and the preferred language as trimmed free text,
with no language list — plus **"Your notes"**, the user level rendered with the
same `MemoLevelGroup` as the wall and **not reorderable** there. The explicit Save
is a *reading* of the draft-page exception rather than a third one, and
`forms-and-lists.md` records why: the route **is** the form. `US-142` is the
companion rule for what happens when neither language is set anywhere — English,
as the instance's last resort and never a configured default.

**Export and import are shown to every role**, administrator included (plans 030,
031): an administrator owns characters and sessions like any account (R5), so
their own data is theirs to take.

- **Export success is silent** — the browser's download is the signal — and a
  failure goes through `notifyFailure`.
- **Import takes a `user` or a `character` export and the server decides which**
  from the envelope; there is no "what kind of file is this" question in the UI.
  A **character import opens the new character**. Every successful import reloads
  **both** the characters list and the tree's session level, because a user export
  carries sessions too. It raises **one warning** that imported material will not
  appear in semantic search until the index is rebuilt
  (`ui-conventions.md`'s warning channel, and `transfer.md` for why no import
  embeds anything).
- The roleplayer imports are **deliberately not confirmed**: they are additive and
  destroy nothing (`forms-and-lists.md`). Only the administrator's
  whole-database **replace** is confirmed, and that is `admin-surfaces.md`'s
  surface.
- **The file input lives outside the menu**, hidden, because a file input inside a
  Mantine `Menu.Item` loses its change event when the dropdown unmounts
  (`ui-conventions.md`'s gotcha).

**The admin link is a cross-entry document navigation, not in-entry routing.**
`/admin` is a separate Vite entry and a separate document; the entries have no
shared router, and the HttpOnly session cookie travels with a document navigation
(`frontend-structure.md`). It is a real `<a href="/admin">`, which is also what
makes middle-click behave. The item is **absent** for a roleplayer, not disabled
(US-093.AC-2). Absence is the frontend half of the same posture as the separate
bundle: the roleplayer's document should not name the admin area at all. The
boundary itself is still the backend's `require_role` (R5,
`backend-structure.md`); hiding the link changes nothing but what is offered.

**Settings is an in-entry navigation performed imperatively** — `useNavigate()`
behind the `Menu.Item`'s `onClick` — and that is the accepted form here rather
than a slip against the declarative `component={Link}` used everywhere else in
`src/`. `frontend-structure.md` carries the rule and the reason: a menu item that
also carried an `href` would read as a cross-entry link and would sit one
attribute away from the admin item it is deliberately unlike.

**A failed logout notifies and stays** (008 D7). `notifyFailure` is the right
channel precisely because the menu that raised it has already closed, so there is
no place of its own left to render in — and the client **never navigates on a
failed logout**, because sending someone to `/login` while their session is
demonstrably still alive would be a lie the next request corrects.

Bottom-left rather than a header corner because the tree's footer is the one part
of the shell that survives collapse (US-090), so the menu stays reachable in both
states without a second placement.

---

## The model picker

**Realizes:** FEAT-013, UC-077, US-105, US-107, US-139

A select **above the stream**, in the session's header, showing the enabled models.
Choosing one **writes the session's override and it persists** (US-105) — it is not
a per-request choice and there is no "just this once".

R1 governs what the picker shows as current and R4 governs what happens when the
chosen reference stops being enabled; neither is restated here. Two consequences
for this surface specifically:

- The picker's value is the **captured model reference** — written at session
  **creation** and never moved by anything but this control (R4,
  `data-model.md`'s `model_server_id` / `model_name` pair). It is not a blank
  waiting to be filled, and it is not re-derived from the character on each open:
  **configuring the character with a different model afterwards does not change
  what this picker shows for an existing session** (US-139.AC-1). A picker that
  recomputed the chain on render would display a model the session is not using.
- With no enabled model at all the picker says so and the composer cannot send
  (US-107). It does not fall back and it does not hide. `US-143` is the companion
  rule on the other side: a session is **created** even when no model is enabled,
  and captures none until the roleplayer picks one here.

**As built** (017 D16, D18):

- A Mantine **`Select` labelled "Model"**, in a header bar after the title row.
- Options in **first-enabled order** (`llm_servers.id`, then `models.id` — the
  LLM Servers page's order), each labelled **"name (server)"**.
- A **captured model that is no longer enabled is shown as a disabled "(not
  enabled)" option**, so the picker tells the truth about what the session holds
  rather than silently showing something else.
- With an empty list the control is **disabled and reads "No model is enabled"**.
- A **failed choice renders inline under the picker** — it has a place of its own,
  so it raises no notification.

**Three tool badges sit beside it**, reading "&lt;Tool&gt;: on/off" from the
**resolved** values (FEAT-013). They are indicators, not switches. One of them can
disagree with what the assistant is actually offered, and `US-073.AC-2` ratifies
that: the badge reflects the **resolved chain**, not whether the instance holds
web-search credentials (`llm-and-streaming.md`).

**The gear (`IconSettings`) opens the session configuration modal** — every
setting with an explicit **Inherit** option and its inherited value shown beside
it. Full session configuration remains its own surface; the header carries the one
control UC-077 puts there, the indicators, and the door to the rest.

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
