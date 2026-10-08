# UI conventions

**Realizes:** FEAT-006, FEAT-007, FEAT-008, FEAT-009, FEAT-010, FEAT-011,
FEAT-012, FEAT-013, FEAT-017, FEAT-018, FEAT-020, UC-030, UC-032, UC-035,
UC-037, UC-039, UC-040, UC-043, UC-069, UC-070, UC-071, UC-072, UC-075, UC-082,
UC-085, US-015.AC-2, US-018.AC-3, US-018.AC-4, US-044.AC-3, US-044.AC-4,
US-044.AC-5, US-102, US-114, US-123, US-124

**The workspace shell lives in `workspace-shell.md`** — the three columns, all
geometry, the note wall's two modes, layout persistence, and the anatomy of the
stream and the current zone.

**The CRUD conventions left this file** at the finalization of plans 008..032 and
now live in **`forms-and-lists.md`**: tables and lists, the modal rule and its
named exceptions, the MobX draft form convention, the confirm convention, the
empty-state rule, the never-optimistic rule and the page-state convention.

This file holds what is left, and it is a coherent subject: **icons, the shared
`IconButton`, the accessibility floor, async feedback, and the inherited frontend
facts** a reader needs to build a screen.

This is a **contract**, not folklore. The conventions below were arrived at in the
sibling project these are inherited from, or designed here against a stated
requirement; each one that looks arbitrary has a reason recorded next to it. A plan
that "simplifies" one of these is changing behaviour, not style.

---

## Icons

**`@tabler/icons-react`** at `^3.40`. One family, for one visual weight.

### Sizing convention

| Context | Props |
|---|---|
| Main, header and composer actions | `size={18} stroke={1.5}` |
| Inline controls | `size={16} stroke={1.5}` |
| Smallest chevrons | `size={14} stroke={1.5}` |

**All three variants use stroke 1.5.** The section opens with "one family, for one
visual weight", and a stroke that changed between variants would be a second
weight in the same family. The table used to carry the stroke on the first row
only, because it does not change — which read as either an omission or a
deliberate difference, and a reader could not tell which.

A **`Menu.Item`'s `leftSection` icon takes the inline metrics**, not the main ones
(plan 010) — a menu item is an inline control. `forms-and-lists.md` holds the
table-row half of that rule.

Colour is left as `currentColor`; semantic colour is applied via the **wrapping
button's** `color` prop, never on the icon. One place decides colour, and it is
the place that also decides hover and disabled states.

### Every icon-only action goes through a shared `IconButton`

An icon-only button is `Tooltip` + Mantine `ActionIcon` + an `aria-label` that
serves as the accessible name.

**This is a deliberate deviation from the sibling project.** BookWriter has no
shared component: every call site repeats the `Tooltip`, the `ActionIcon`, the
`size`, the `stroke` and the `aria-label` inline. RPHelper has roughly **40
distinct icon actions** (tables below), several of them appearing in more than one
place, so the abstraction pays for itself immediately — and, more importantly, an
accessible name that is repeated at 20 call sites is an accessible name that is
wrong at two of them.

```tsx
type IconButtonProps = {
  icon: React.ComponentType<{ size?: number | string; stroke?: number }>;
  label: string;                     // tooltip text AND aria-label — one source
  onClick: () => void;
  disabled?: boolean;
  color?: MantineColor;              // semantic colour, applied to ActionIcon
  sizeVariant?: "main" | "inline" | "chevron";   // maps to 18/16/14 + stroke
};
```

**Call sites must go through `IconButton`.** A bare `ActionIcon` wrapping a Tabler
icon is a defect, because it is how an action ends up with a tooltip and no
`aria-label`, or with the two disagreeing. `label` is a single prop feeding both
precisely to prevent that.

Three things the props type does not carry, recorded because the component cannot
be written without choosing them and a choice made silently at implementation
time is one nobody can find later:

- **The `ActionIcon` variant is `"subtle"`.** An icon-only action is secondary
  chrome; Mantine's default filled variant would render roughly forty solid
  coloured boxes across the product.
- **`sizeVariant` defaults to `"main"`** — the sizing table's first and most
  common row.
- **The props type is deliberately not widened** with `children`, a `variant`
  escape hatch, a raw `size`, or an `aria-label` override. Each would reintroduce
  the divergence the `label`-feeds-both rule exists to prevent.

**A rotated chevron is passed as a tiny module-level component, not as a new
prop** (022, `004.context.md`). Several controls need `IconChevronDown` rendered
with a rotation style; the as-built pattern is a module-level component that
renders the Tabler icon with the rotation applied, handed to `IconButton`'s
`icon`. Recorded because the obvious alternative is a `rotate` prop, and the
props type is deliberately closed.

**Two controls deliberately sit outside the rule**, each because it wraps no
Tabler icon:

- **The user-menu trigger** is an avatar button with a fixed accessible name
  ("User menu") — avatar plus username when the tree is expanded, avatar alone on
  the collapsed rail (008 D6). The `IconButton` rule does not reach it, and
  converting it would be a regression dressed as consistency.
- **My-search in the tree header is a text input**, not a button (029 U4). The
  collapsed rail keeps the icon button.

**The one boundary — `IconButton` versus the table overflow menu.** There is a
real tension between the rule above and `forms-and-lists.md`'s table convention,
and it is resolved by scope rather than left to taste:

| Place | Pattern |
|---|---|
| Toolbars, headers, the composer, inline controls | **`IconButton`** — an icon-only action with a tooltip and an accessible name |
| **Table rows** | a single **overflow `Menu`** behind one `IconDots` trigger; the row's actions are menu *items with text labels*, not icons |

So a table row contains exactly **one** icon-only control — the `IconDots`
trigger, which itself goes through `IconButton` and is labelled for its row
("Actions for &lt;name&gt;", plan 010; "Actions for &lt;start-time label&gt;",
plan 011) — and no others. The reason the two rules do not conflict: inside the
menu the actions are labelled text, so there is no accessible-name problem for
`IconButton` to solve, and a row of four icon buttons is both a discoverability
problem and the thing that makes a row layout collapse on a narrow viewport.

The stream is a third case and is governed by `workspace-shell.md`: an entry's
actions sit inside the entry as `IconButton`s, because an entry is a document, not
a row, and the overflow-menu rule exists to keep a *row* from collapsing.

### Icon table

| Action | Icon | Feature |
|---|---|---|
| Send message in discussion | **labelled button**, not an icon | FEAT-010 |
| Stop generation | `IconPlayerStop` | FEAT-010, UC-085 |
| Settle | **labelled primary button**, not an icon | FEAT-010 |
| **Copy settled turn out** | `IconCopy`, labelled "Copy as plain text" — on `turn` entries **only** | FEAT-009 |
| Regenerate (retry a compose) | **labelled subtle `Button`** with `IconRefresh` as its left section | FEAT-010, US-044 |
| Translate / flicker | `IconLanguage` | FEAT-011 |
| New session / character / setup | `IconPlus` | FEAT-006 / FEAT-007 / FEAT-008 |
| Archive / restore | `IconArchive` / `IconArchiveOff` | FEAT-006 / FEAT-007 / FEAT-008 |
| Session configuration | `IconSettings` | FEAT-013 |
| My search | `IconSearch` — the collapsed rail's button; the expanded tree header is a **text input** | FEAT-017 |
| Memos / the note wall | `IconNotes` | FEAT-012 / FEAT-020 |
| Edit entry, message or note | `IconEdit` | FEAT-009 / FEAT-010 / FEAT-012 |
| Save | `IconDeviceFloppy` | FEAT-013 |
| Collapse / expand (chevron) | `IconChevronDown`, rotated | FEAT-010 / FEAT-020 |
| Show / hide a settled entry's discussion | `IconChevronDown`, rotated; "Show discussion" / "Hide discussion" | FEAT-010, US-040 |
| Re-open a settled block | `IconArrowBackUp`, "Re-open last entry" | FEAT-010 |
| Overflow menu | `IconDots` | — |
| Export / import | `IconDownload` / `IconUpload` | FEAT-018 |
| Admin nav — Users | `IconUsers` | FEAT-003 |
| Admin nav — LLM Servers | `IconServer2` | FEAT-004 |
| Admin nav — Database | `IconDatabase` | FEAT-005 |

**The row "Copy as plain text (composer)" is removed.** It named a composer copy
action that **no plan built and no brief contains**. It is deleted rather than
turned into a `_TBD:`, because there is no open question here: the product's one
copy-out is the settled turn (below), and a second copy control was never
specified.

Workspace additions (FEAT-020 and its neighbours). The mockup they come from draws
**inline SVG rather than importing Tabler components**, so it settled the glyph and
its meaning, not the import name. Every row below now names a Tabler component as
built; **the glyph `_TBD:`s this table used to carry are all closed.**

| Action | Icon | Realizes |
|---|---|---|
| Kind switch — *partner* / *my turn* | **two labelled segments**, no icons | US-120 |
| Discard an **empty** current zone | `IconX`, labelled "Discard empty zone"; **absent**, not disabled, otherwise | UC-086, US-134 |
| Collapse the tree | `IconChevronLeft`, labelled "Collapse tree" | UC-070, US-090 |
| Expand the tree from the rail | `IconMenu2`, labelled "Expand tree" | UC-070, US-090 |
| New character (tree header and rail) | `IconPlus`, labelled "New character" | UC-074, US-090 |
| Expand / collapse a character in the tree | `IconChevronDown`, rotated `-90°` when collapsed, labelled "Collapse &lt;name&gt;" / "Expand &lt;name&gt;", `sizeVariant` `"chevron"`; **absent** for a character with no sessions | UC-069, US-088 |
| Open the note wall | `IconNotes`, labelled "Open notes"; present only while the wall is not visible | UC-072 |
| Pin / unpin the wall | `IconPin`, labelled "Pin notes" / "Unpin notes"; the active state is the `IconButton`'s colour while pinned | UC-072, US-094 |
| Dismiss the wall | `IconX`, labelled "Close notes" | UC-072 |
| Note forced / not forced | `IconPin`, labelled "Force note" / "Stop forcing note"; state in the button's colour | UC-075, US-098, US-099 |
| Note enabled / disabled | `IconCircleCheck` while enabled, `IconCircleOff` while disabled, labelled "Disable note" / "Enable note" | UC-075, US-100, US-101 |
| Collapse / expand a tool call | `IconTool` (decorative, beside the tool name) plus the rotated `IconChevronDown` toggle, labelled "Show tool call" / "Hide tool call" | US-114 |
| Collapse / expand thinking | `IconBulb` beside "Thinking", plus the rotated `IconChevronDown` toggle, labelled "Show thinking" / "Hide thinking" | US-114 |
| User menu — settings | `IconSettings` | UC-071, US-092 |
| User menu — admin area | `IconShield` | UC-071, US-093 |
| User menu — export my data | `IconDownload`, "Export my data" | UC-062, US-079 |
| User menu — import | `IconUpload`, "Import…" | UC-063, US-080 |
| User menu — log out | `IconLogout` | UC-071, US-091 |

Notes on individual choices:

- **`IconCopy` has no precedent in the sibling project** — BookWriter has no copy
  action at all. It is specified here because copying the settled turn out is
  RPHelper's **entire outbound boundary**: `vision.md` states "the boundary is the
  clipboard", and UC-030/UC-082/US-033.AC-1 is the one operation that crosses it.
  Not a convenience affordance — the last step of the product's main flow. It
  yields **plain text, never markdown** (US-124), and it is **absent — not
  disabled — on a `decision` entry** (US-123) **and on a `partner` entry too**
  (014 D7): UC-030, UC-082 and US-033 all speak of the roleplayer's *own* answer,
  and a partner block is text they did not write and have no reason to post back.
  `workspace-shell.md` holds the stripper and the clipboard fallback.
- **Settle and Send are labelled buttons, not icons.** This **resolves** the
  previous `_TBD:` that proposed `IconMessageCheck` for settle and noted a
  label-bearing button might be right instead. Settle is the most consequential
  action in the product (UC-035) and is the composer's primary button; Send is
  secondary beside it. `IconMessageCheck` is not used anywhere.
- **Regenerate is labelled rather than icon-only**, for the same reason Send and
  Settle are (022 D14): it **starts a model call**, and the three controls that
  spend a model call all carry words. The `IconRefresh` is a left section, not the
  control.
- **`IconChevronLeft` is the decision of record for "Collapse tree"** (008 D10).
  Plan 008 shipped it as a provisional choice under the `_TBD:` this table used to
  carry, and it is **confirmed rather than replaced**: changing the glyph now
  would be a code change that a finalization pass must not require, and the
  mockup's drawn glyph — a left chevron against a right-hand bar — is **satisfied
  in spirit** by a left chevron sitting at the right edge of the tree column,
  which is where the control is. **`IconLayoutSidebarLeftCollapse` is the
  rejected alternative**, and it is a real candidate: it draws the bar explicitly
  and is the closer literal match. It loses on consistency — every other
  collapse/expand control in the product is a chevron
  (`IconChevronDown` rotated, the tree's characters, the tool and thinking blocks,
  the discussion group), and a second visual vocabulary for "collapse" on the one
  control that collapses a *column* would read as a different kind of action. A
  later plan may still swap it; that would be a glyph change with a one-line
  reason, not a reopened question.
- **`IconArrowBackUp` for re-open** rather than an "expand" icon, because re-open
  is an **undo for a mis-click, not a workflow** (UC-037, R7). It should be absent
  — not merely disabled — once anything sits in the current zone, since at that
  point the action does not exist (US-128).
- **One chevron, rotated, not two icons.** The mockup rotates a single
  `IconChevronDown` by `-90°` rather than swapping to `IconChevronRight`: one icon
  animates between the two states, two icons cut. This supersedes the earlier
  `IconChevronDown` / `IconChevronRight` pair, and it is now used by the tree, the
  tool and thinking blocks and the settled entry's discussion group alike.
- **`IconSettings` (a gear) for session configuration**, not
  `IconAdjustmentsHorizontal` — the mockup draws the same gear for the session's
  settings and the user menu's, and two glyphs for "settings" in one shell reads as
  a bug. As built the same glyph carries both (017 D16): the user menu's Settings
  item and the session header's configuration gear.
- **Edit is one action with one icon** across settled entries, current-zone
  messages and notes — all three are the same in-place edit saved on focus loss
  (US-104, US-109, US-110, US-115). The mockup's glyph is a plain pencil
  (`IconPencil`); `IconEdit` is kept as the name because it was already this
  project's choice and the two differ only in whether the pencil sits in a frame.
  Substituting `IconPencil` is a glyph choice, not a behaviour change.
  **The labels differ by surface and must not be merged** (014 D10): a settled
  entry's are "Edit entry" / "Edit entry text", a zone message's are
  "Edit message" / "Edit message text". One glyph, two accessible names, because
  the two sit one above the other across a ruler and a reader of either must know
  which side of the record they are on.
- **`IconArchive` / `IconArchiveOff` and `IconDeviceFloppy` appear as left
  sections of labelled buttons** on the character page (plan 009), and
  **`IconArchive` / `IconArchiveOff` also appear as labelled items of a table
  row's overflow menu** for setups and sessions (plans 010, 011). The glyph is the
  same; whether it is a button or a menu item is the table rule above.
- **`IconPlus` is a labelled button, not an icon-only control, wherever it creates
  a child of the thing on screen** — "New setup", "Start session", "New note",
  "Import session" (plans 010, 011, 016, 031). It is icon-only in the tree header
  and the collapsed rail, where there is no room for words and the surrounding
  context supplies the noun.
- **The wall's pin and a note's "forced" flag are the same glyph, and the
  collision is accepted.** `IconPin` means "keep this panel open" on the wall's
  header and "put this note in the system prompt" on a note card. **They do
  co-occur on one screen** — the wall's header sits directly above its note cards
  — so this is an accepted collision, not an avoided one. It is accepted because
  the two are disambiguated by the things that actually carry meaning here: the
  **label** ("Pin notes" / "Unpin notes" versus "Force note" / "Stop forcing
  note", each the tooltip and the accessible name) and the **location** (one in a
  panel header, one in a card's own controls). The alternative was a second glyph
  for a concept that is genuinely "pin this", chosen only to avoid a repetition
  the labels already resolve — which trades a real loss of meaning for a cosmetic
  gain. **The `_TBD:` that carried this question is closed by that decision**
  (user decision, 2026-10-06).
- **`IconCircleCheck` / `IconCircleOff` for the enabled/disabled note toggle**
  (015 D14), the nearest unambiguous Tabler pair to the mockup's "circle with a
  bar" and "circle with a slash". It is a **two-icon swap**, and the labels name
  the **action** rather than the state ("Disable note" while enabled), which is
  the `IconButton` convention everywhere else. The card additionally dims and
  strikes a disabled note's body, so the state is legible without reading the
  button at all — the glyph swap is the control, the body treatment is the state.
- **`IconLanguage` is one icon with the state carried by the label** (023 D15),
  not two glyphs and not a pressed state. The three labels are **"Show
  translation"**, **"Cancel translation"** (while a translation is pending) and
  **"Show original"**; each is both the tooltip and the `aria-label`. A **distinct
  colour** marks the translated state. **No `aria-pressed`**, deliberately: a
  toggle whose accessible *name* changes must not also carry a pressed state, or a
  screen-reader user is told the same thing twice and in two vocabularies.
  `IconButton`'s props are not widened for it. **The `_TBD:` that asked how the
  flicked state is shown is closed.**
- **`IconTool` for a tool block** (022 D14) is **decorative**, beside the tool's
  name; the control is the rotated chevron. Recorded because a decorative icon
  next to an icon-only toggle is exactly the pair someone merges into one
  labelled button.
- `IconDots` traces to no feature — it is a container for actions that are
  themselves feature-bound, so it carries no id of its own.

### Accessibility floor

- Every icon-only control has an accessible name (via `IconButton`'s `label`),
  and where one control serves many rows the name names its row ("Actions for
  &lt;name&gt;", "Collapse &lt;name&gt;").
- **Actions revealed on hover must also be revealed on `:focus-within`.** This
  reaches the **stream's per-entry actions** — edit, copy, the translation
  flicker and re-open, which sit in one revealed group inside the entry — and a
  hover-only reveal would put them out of a keyboard's reach entirely.
  **The mechanism is Mantine hooks, not CSS** (014 D6, user decision): `useHover`
  + `useFocusWithin` with merged refs, plus `useMediaQuery("(hover: none)")` so a
  touch device shows them outright, applied as an **opacity** style prop. The
  controls therefore **stay in the DOM and in the tab order** while hidden, and
  tabbing into an entry reveals them. No stylesheet selector exists for it, and
  none may be added — the two-stylesheet rule (`frontend-structure.md`) has
  nowhere to host one, and `tests/stylesheets.test.ts` pins that.
- **A note's flag icons are always shown, and that is the convention** (user
  decision, 2026-10-06). This floor used to require hover-reveal for them; the
  requirement is removed rather than the code changed, because **always-visible
  controls are the more accessible of the two options** and a floor must not
  carry a rule the build does not meet.
  **The difference from the stream's entry actions is deliberate.** A note card is
  small, holds exactly two controls, and its two flags *are* the information the
  roleplayer scans the wall for — the reach line under the card restates them in
  words precisely because they matter at a glance. A settled entry is a document
  with four controls that are chrome over prose, and hiding chrome over a page of
  text is what keeps the stream readable. Two surfaces, two answers, each stated
  so neither is "corrected" into the other.
- **Note reordering must have a keyboard path, and it is built.** `@dnd-kit`'s
  `KeyboardSensor` with sortable keyboard coordinates is required, not optional,
  because reordering changes what the system prompt contains (R3, US-102) — it is
  a content operation wearing a drag gesture. This is the same principle the
  deleted resize splitters were held to. As built (016 D8) the card keeps role
  `listitem` and is named "Note &lt;n&gt; of &lt;total&gt;", drag announcements
  name **positions and never ids**, and keyboard activation fires **only when the
  card element itself is the event target**, so keys typed in the note's editor
  never start a drag.
- **A status badge sits beside its link, never inside it** (plan 009, step 008).
  The tree's "Archived" badge is a sibling of the `NavLink`, so the link's
  accessible name stays exactly the character's name while the row still reads as
  archived. A badge inside the link would append a word to every such name.
- **A named list is a `ul` with an `aria-label`** (plan 009, step 008) — the tree's
  characters list is `Box component="ul" aria-label="Characters"` with an inline
  `listStyle: "none"` as its only presentation, because there is no stylesheet to
  put a list reset in (`shell.css` is layout-only and no third stylesheet is
  allowed).
- **A region holding several blocks is a labelled landmark** (plan 010, step 006)
  — `<section aria-labelledby={headingId}>` with the heading carrying the id. The
  character page's Setups section was the first; the page now holds several at
  once, which is why the rule is written rather than left to each section. Use
  `aria-label` on a `Box` only where there is no visible heading to point at.
- `_TBD: no wider accessibility target (WCAG level, screen-reader matrix) is
  stated in docs/product/. The floor above is what the icon and interaction
  contracts require, not a considered accessibility posture._

---

## Async feedback — no *success* toasts, failures, and one narrow warning

**This rule is rewritten, not deleted, and the change is narrow.** It used to
read "there is no toast system" and to list `@mantine/notifications` as not a
dependency. **US-044.AC-4 reverses half of it**: a failed generation must show
its reason, and **the reason must not persist once the notice has gone**. An
inline error above the stream cannot satisfy that — it either stays until
something replaces it or waits for a manual dismissal, and "does not persist" is
the criterion.

**The rule is now: no *success* toasts.**

- **Success feedback is unchanged.** The modal closes and the list refreshes.
  That pairing is the success signal — a list that visibly contains the new row
  says more than a toast saying it was created. The original reasoning was always
  about **success noise**, and that half holds exactly as written: nothing in
  `docs/product/` asks for a transient success message, and adding one introduces
  a second, timed, easily-missed channel for something the inline one already
  carries reliably.
- **`@mantine/notifications` IS a dependency**, added for **transient failure
  reasons**, with **`autoClose: 5000`** — and for exactly one kind of warning
  (below).

**What the failure channel carries** — a failure's *reason*, for any typed failure
that is not already rendered in place: `llm_unreachable`, `model_not_enabled`,
`no_model_enabled`, `model_not_chosen`, `translation_failed`, and the rest of
`backend-structure.md`'s error table on the same condition. A failure
that already has a place to be rendered — a field error in a modal, the inline
`Alert` above an admin table, the no-embedding-model banner above the stream
(US-112) — keeps rendering there and does **not** also raise a notification.

**The four compose failure codes reach `notifyFailure` carrying the server's own
message** (plan 021). `no_model_enabled`, `model_not_chosen`, `model_not_enabled`
and `secret_ref_missing` are raised by `resolve_model_for_use` **inside** the
stream, after `accepted`, so they arrive as `error` frames rather than as an HTTP
status (`llm-and-streaming.md`, R10). The consumer turns an `error` frame into an
`ApiError` exactly as the JSON client does (`frontend-structure.md`), and the
compose effect hands it to `notifyFailure` — so the roleplayer sees the reason the
server gave, not a house sentence, and nothing in the zone or the record is
discarded. There is no inline place for these: the stream is the content, not a
form.

**`tool_failed` is never a notification, and this is the one code the list above
deliberately excludes.** It is not a failure of the exchange at all — the
`tool_fail` frame is **non-terminal** (R9: a failed tool is a tool *result*, the
assistant carries on without it), and the stream effect that drives the
notification channel **ignores tool frames entirely** (plan 019). The tool's
outcome is shown where it belongs: the live tool block marks the call `failed`
while streaming, and the persisted `role='tool'` row renders the server's "The
tool failed." summary afterwards (`workspace-shell.md`, `data-model.md`). Raising
a notification for it would tell the roleplayer something failed when the reply
they are reading is still arriving — and would do so for an event the product
treats as ordinary. Named explicitly because `tool_failed` sits in
`backend-structure.md`'s error table with a **502** beside it and therefore reads
like a candidate for the failure channel; its status is recorded for the first
route that ever raises it as an HTTP response, of which there is none.

**The same holds for a failure that has a full-page state of its own** — a
not-ready-yet screen, a refusal, a form's inline alert: it is rendered there and
is **not** also a notification. The rule is "a failure with no place of its own",
never "every thrown error gets a toast".

**The boundary a reviewer can check, stated as one line:**

> **A notification whose message is a success is a defect.**

That is the whole test. It is phrased that way because "no toasts, except…" is a
rule nobody can apply, while "failures only" is a rule that is either satisfied
or visibly broken at the call site.

### Worked examples on each side of the boundary

Both columns are as built, and the list is long on purpose: the boundary is easy
to state and easy to get wrong, and twelve decided cases are more useful than the
rule alone.

| Surface | Channel | Why |
|---|---|---|
| FEAT-001's `bootstrap` entry (plan 003) | **nothing** — five states and a form, and **no `notifyFailure` call site at all** | every failure it has is a full-page state or the form's inline alert |
| Log out failing from the user menu (008 D7) | `notifyFailure`, and the client **stays** — it never navigates on a failed logout | the menu that raised it has already closed, so there is no place of its own left to render in |
| The character screen and the tree (plan 009) | **inline** — a screen `Alert`, tree text plus Retry, "Character not found" | each failure has a place; plan 009 adds no `notifyFailure` call site |
| The Setups section and its modal (plan 010) | **inline**, inside the section or inside the modal | same; plan 010 adds none either |
| The Sessions section, the tree's sessions load, the session screen (plan 011) | **inline**, including the non-blocking "Could not load setups to choose from." | a list that could not load must not become a precondition for starting a session |
| Loading the stream (013 D15) | **inline** — "Could not load the stream" plus Retry | a place of its own exists |
| Every stream **mutation** failure — settle, re-open, partner filing, a zone edit, re-open's refusal (013 D15) | `notifyFailure`, then a re-read | a mutation has no region of its own; the stream is the content, not a form |
| A clipboard failure on copy-out (014 D9) | `notifyFailure`; **success raises nothing** | the clipboard is the whole outbound boundary and a silent failure would be invisible |
| The character page's composer send (018 D4) | `notifyFailure` | same as the stream's composer |
| The character page's configuration block (018 D9) | **inline**, under the control that failed | each control has its own place |
| A discussion group's lazy load (022 D11) | **inline, inside the group** | the group is on screen and is where the roleplayer is looking |
| A failed generation's **reason** (US-044.AC-4) | `notifyFailure` | the criterion is that it must not persist |
| An **export** — `app` entry or admin page (plan 030) | **nothing in the `app` entry**: the browser's own download is the success signal. The admin page renders an inline size line ("Export downloaded — 12.3 KB") | page text is not a notification, so the size line does not break the no-success-toast rule |
| A failed export (plan 030) | **inline** red `Alert`, separate from the drift report's error | it has a page to render on |
| A successful **import** (plan 031) | `notifyWarning` — the coverage caveat below | the import succeeded; the warning is about what the import does *not* yet do |
| My-search's own failure (plan 029) | **inline** on the results page | the page exists and must say why it is empty |

### The third class — a warning, and the one thing that raises it

Beside success (none) and failure, there is a **warning**: a transient notice that
is neither (014 D4, user decision).

- It is raised through **`shared/notifyWarning`**, the **second — and final —
  sanctioned importer** of `@mantine/notifications`.
- It takes an **identifier from a closed set**. No free text, no colour
  parameter, no timeout. So a success message is still not something a call site
  can express.
- The outlet's `autoClose: 5000` applies; the colour is yellow.
- **`tests/conventions.test.ts` pins the importer set to exactly those two
  files.**

Its two users:

1. **The enormous-paste context-cost warning** (US-035.AC-1) — a composer paste
   over the threshold. It never prevents, delays or alters the paste or the
   filing (R10, `workspace-shell.md`).
2. **The post-import coverage caveat** (plan 031) — after a successful import,
   one warning that imported material will not appear in semantic search until
   the index rebuild.

**The second is the worked example that settles a question the rule leaves
open: a warning attached to a *success* is permitted.** The import succeeded and
says so by reloading the lists; the warning carries a true caveat about the
result, not a celebration of it. A success *notification* remains a defect. The
test that distinguishes them is whether removing the notice would remove
information the roleplayer cannot get from the screen — the caveat passes it, "Saved!"
does not.

### The mechanism — one outlet, two call sites

The rule above is made **structural**, not left to review (plan 002, plan 014):

- **The notifications outlet is mounted by `shared/AppProviders`**, and reaches
  all four entries through that one component. It is configured with
  **`autoClose: 5000` on the outlet**, so no call site can pick a different value.
- **`shared/notifyFailure` is the only sanctioned way anything raises a
  *failure*.** It takes a **thrown value** and has **no success path and no
  colour parameter** — so a success notification is not something a call site can
  express at all. Its generic fallback text for a non-`ApiError` value is a
  module-private constant; `frontend-structure.md` records that an inline-failure
  page needs that text exported rather than repeated.
- **`shared/notifyWarning` is the only other importer**, bounded as above.

A rule enforced only by review is one an unfamiliar contributor breaks first; the
shape of the two functions is what turns "a notification whose message is a
success is a defect" from a review check into something that cannot be written.

### The tension with US-044.AC-3, and how it is resolved

US-044.AC-3 requires that a retry is **possible** after a failure. US-044.AC-4
requires the reason **not to persist**. Put both on the notification and they
contradict: if the notice carries the only retry affordance and auto-dismisses
after five seconds, the retry vanishes with it, and a roleplayer who looked away
has lost the action rather than the message.

**They are split, and the split is the design:**

| Carries | Where | Lifetime |
|---|---|---|
| The **reason** the generation failed (US-044.AC-4) | the transient notification | ~5s, then gone |
| The **retry** affordance (US-044.AC-3, US-044.AC-5) | **in the stream** — the labelled **Regenerate** button after the last zone row | persists until the exchange succeeds or is abandoned |

The retry belongs in the zone because the zone is what a retry re-composes over,
and because it is **derived from persisted rows and therefore survives a
reload** — which a transient notice cannot. The notification carries the reason
precisely because the reason is the thing the product says must not persist, and a
reason without its retry is a message, which is what a transient channel is for.

**The split holds as built** (022 D8, D13): the reason comes through the
compose's own `notifyFailure` path and the control is Regenerate.
`US-044.AC-3`'s widened form and `US-044.AC-5` now require that control on **any**
exchange, failed or not — which is what the build already does, so the as-built
general Regenerate is ratified rather than merely tolerated
(`workspace-shell.md`).

Nothing in the record is discarded on either path (R10): the failure notice and
the retry control are both additive to a zone and a settled record that survive
intact.

---

## Other inherited frontend facts

Recorded here so a reader building a screen has the stack in one place:

- **React 19**, TypeScript.
- **Mantine 7** — `@mantine/core`, `@mantine/hooks`, `@mantine/tiptap`,
  `@mantine/notifications`. No Tailwind, no CSS modules, no styled-components;
  two small hand-written stylesheets (`frontend-structure.md`).
  **`@mantine/form` is not a dependency** — forms go through the MobX draft
  convention in `forms-and-lists.md`, which forbids it.
  **`@mantine/notifications` IS a dependency and IS used**, for transient
  **failure reasons and the one bounded warning**, `autoClose` 5000 — this
  reverses the earlier "not a dependency at all, there is no toast system" note,
  narrowly, on US-044.AC-4. Success toasts remain forbidden; see the feedback
  section above for the boundary.
- **`@mantine/hooks` is used for non-stateful helpers only.** A custom hook must
  not hold reactive state (`admin-surfaces.md`'s shell-state note): reactive state
  lives in a MobX class instantiated with `useState(() => new X())`. This is why
  `useDisclosure` does not appear anywhere in this codebase even though it would
  fit several call sites.
  **Three sanctioned uses, each reading the environment rather than holding
  state:** `useMediaQuery` with the shared **`NARROW_VIEWPORT_QUERY`** constant
  (008 D3, D12 — the exact string `shell.css`'s media query uses, so the CSS stays
  the layout authority and the TypeScript only *reads* the same condition);
  `useHover` and `useFocusWithin` for the stream's revealed actions (014 D6); and
  `useMediaQuery("(hover: none)")` beside them for touch. Named as sanctioned so
  none reads as a slip against the rule.
- **A file input inside a Mantine `Menu.Item` loses its change event when the
  dropdown unmounts** (plan 031). The user menu's "Import…" therefore triggers a
  **hidden input that lives outside the menu**. Recorded as a gotcha because the
  obvious implementation works until the first file is chosen, and then fails
  silently.
- **MobX 6** + `mobx-react-lite`. Per-page store classes, passed as props, no
  context (`frontend-structure.md`).
- **`react-router-dom` 7** within an entry.
- **TipTap + `tiptap-markdown`** for editing and **`react-markdown`** for
  rendering — together these cover FEAT-012/UC-043's markdown editor with live
  preview. `frontend-structure.md` owns the shared `MarkdownEditor` wrapper and
  its emit rules.
- **`@dnd-kit`** is used for exactly two mount points and one interaction:
  reordering notes within a level, on the wall and on the character page's notes
  grid (UC-076, US-102, US-103), with the sensors and announcements shared through
  one module. See `workspace-shell.md` and `frontend-structure.md`. It is not
  available for anything else without a requirement that asks for it.
