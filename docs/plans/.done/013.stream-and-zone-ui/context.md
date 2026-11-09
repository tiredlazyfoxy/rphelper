# Feature 013 — Stream and zone UI · feature-wide context

## What this feature is

The frontend half of the session stream. On `/sessions/:id` the centre column shows the
**settled record** (read through `GET …/entries`), one labelled **ruler**, the **kind
switch**, the **current zone** (read through `GET …/zone`) with every message editable in
place, and a **composer** that grows with its content. The roleplayer can send text into
the zone, settle it, paste a partner block that files itself immediately, discard an empty
zone, and re-open the last settled entry while the zone is empty. Settling is previewed
client-side (`(( ))` classification and stripping), and `(( ))` is painted in the zone as
display over stored text.

The agreed boundary is `brief.md` in this folder. Its Definition and Scope In/Out bound
every step and are **not** widened. Its one open question (client-computed versus fetched
preview) is closed by **D1**.

**Frontend only.** No backend file is touched; every route used is 012's.

## Product ids

Delivered (per brief): FEAT-009 — UC-027, US-030, US-120, US-121, US-123; FEAT-010 —
UC-086, US-115, US-125, US-134, US-135. Exercised from the UI (backend halves are 012's):
UC-083, UC-028 / US-031, US-126, US-128, UC-031, and US-129 / US-130 as **preview only**.

| Criterion | Where it lands |
|---|---|
| US-030.AC-1, US-121.AC-1 (a paste on *partner* files a partner entry, no Settle step) | `003` (effect), `006` (paste handler), `007` (end to end) |
| US-121.AC-2 (parens in partner text get no handling) | `004` (partner entries render plain, never painted — D5) |
| US-120.AC-1 / AC-2 / AC-3 (alternating default; decisions skipped) | `002` (pure default), `006` (switch shows it), `007` |
| US-123.AC-1 (no copy action on a decision) | `004` |
| US-125.AC-1 (one ruler, one zone) | `007` |
| US-115.AC-1 (any zone message, any role, edited in place) | `003` (effect), `005` (in-place editor) |
| US-134.AC-1 / AC-2 (empty zone discardable; holding text → no discard offered) | `002` (derivation), `006` (control present / absent) |
| US-135.AC-1 (settle with only the roleplayer's own text) | `002` (`canSettle` never needs an assistant row), `003`, `006` |
| UC-086 (abandon an empty zone; nothing written is discarded) | `002`, `006` (D3) |
| US-126.AC-1 / AC-2 (settle takes the last zone row, whoever wrote it) — UI half | `002` (settle target), `006` (preview reads it) |
| US-128.AC-1 / AC-2 (re-open only while the zone is empty) — UI half | `002` (derivation), `003` (effect), `004` (control present / absent) |
| US-031.AC-1 / UC-028 (write directly and settle) | `003`, `006`, `007` |
| US-034.AC-1 / UC-031 (any order; own entry first) | `002` (empty-record default is *my turn*, D8) |
| US-129.AC-1 / US-130.AC-1 — **preview only**; the server decides (R12) | `001` (pure rules), `006` (preview line) |

**Not delivered here (brief Out):** editing and copying settled entries and the
enormous-paste warning (US-035, US-109, US-110, US-124, US-033 — `014`); anything
streamed and the stop control (`019`, `022`); reading a buried group (US-040, US-113,
US-116 — `022`); the note wall (`016`); the model picker (`017`); the search-coverage
banner (`024`).

## Build prerequisite — 010, 011 and 012 are planned, not built

001..009 are built. **010, 011 and 012 are planned, not built.** 013 binds to their
**declared** interfaces, cited from their step files and not re-specified.

| Upstream artifact | What 013 relies on | Needed by |
|---|---|---|
| 012 `routers/stream.py` + `main.py` registration (012 `004`) | the seven stream routes, their bodies, response shapes and error codes — 012 `context.md` "Wire contract — the stream routes" | `001` (wire shapes only; tests stub `fetch`), `007` `[manual/live]` |
| 012 D8 + 012 `003.context.md` "The parser, as spec" | the exact `(( ))` rules the preview must match (D1) | `001` |
| 012 D2 (PATCH edits zone rows only), D5 (US-120 default computed client-side), D10 (re-open rule), D11 (settle / re-open return ids only), D14 (partner filing has no zone precondition) | behaviour the UI is shaped around | `002`, `003`, `004` |
| 011 `004` `frontend/src/app/sessionsApi.ts` | nothing imported by 013 — `Session` stays the session screen's | — |
| 011 `009` `frontend/src/app/SessionScreen.tsx`, `sessionScreenState.ts`, `SessionRoute` | the ready render that 013 extends (D13); `SessionRoute` keys the screen by id, so the stream remounts per session | `007` |
| 011 `009` tests `tests/app/SessionScreen.test.tsx`, `tests/app/App.test.tsx`, `tests/entries.test.tsx` | amended where 013 changes what they observe (`007.context.md`) | `007` |
| 008 delivered: `WorkspaceShell.tsx` main region (`<Box component="main" className="app-main">`) | the column the stream sits in | `007` |

- Steps `001`–`006` import only `shared/` modules and 013's own modules, so they can be
  built before 011 and 012 (their tests stub `fetch`).
- Step `007` edits 011's `SessionScreen.tsx` and amends 011's tests: needs **011 `009`
  delivered**. Its `[manual/live]` item needs **012 delivered**.

## Built state this feature reads

- `src/shared/api.ts`: `apiGet`, `apiPost`, `apiPatch` (path, optional body, optional
  signal); a 401 navigates to `/login` and throws. `src/shared/apiError.ts`: `ApiError`
  (`code`, `status`, `detail`), `isApiError`, client codes `client_malformed_error` /
  `client_transport_failed`. **Branch on `.code` only.**
- `src/shared/notifyFailure.ts`: `notifyFailure(error)` — the **only** importer of
  `@mantine/notifications` (enforced by `tests/conventions.test.ts`). No success path.
- `src/shared/IconButton.tsx`: props `icon`, `label`, `onClick`, `disabled?`, `color?`,
  `sizeVariant?` (`"main"` / `"inline"` / `"chevron"`).
- `src/app/characterScreenState.ts`: the state-module pattern to mirror (data class +
  `makeAutoObservable`, free-function effects that `runInAction`, check `signal?.aborted`,
  write fixed sentences rather than backend prose).
- `src/shared/MarkdownEditor.tsx` (TipTap) exists and is **not** used by 013: the composer
  and the zone editor are plain text.
- Not present today: any SSE consumer (none needed), `react-markdown` (added by `004`,
  D5), any use of Mantine `Textarea autosize`.

## Wire contract

**012 `context.md` "Wire contract — the stream routes" is the contract** — the route
table, the eight-key `Message`, the settle / re-open response shapes, and the failure
table. It is cited, not copied. The facts every 013 step leans on:

- `Message.role` is `"user"` / `"assistant"` / `"tool"`; `Message.kind` is `"partner"` /
  `"turn"` / `"decision"` or `null` (zone rows are `null`).
- Both reads answer **ascending by id**; the client renders the order it was given and
  never sorts (`frontend-structure.md` "Ids are strings").
- Settle and re-open answer **ids only** (012 D11); the client re-reads both lists.
- The codes the UI meets: `session_not_found`, `message_not_found`,
  `message_not_editable`, `zone_empty`, `zone_not_empty`, `nothing_to_reopen`; blank text
  → 422. **No code is branched on in 013** — every mutation failure takes the same path
  (D15).

## Architecture this binds to

- `docs/architecture/workspace-shell.md`: geometry table (stream column and composer
  720px / 18px, composer min height 42px, no max, no handle); "The stream — the settled
  record" (three kinds, `decision` dashed accent card, re-open placement and absence);
  "The ruler and the current zone" (US-115 every message editable); "The kind switch and
  settle" (two positions, partner paste files itself, Settle disabled not hidden on
  *partner*, preview line under the composer, `(( ))` painted in the zone, Settle / Send
  labelled, Settle never waits for an assistant); "Discarding an empty current zone"
  (frontend-only, absent not disabled — wording amended by D3, `outcome.md`).
- `docs/architecture/ui-conventions.md`: `IconButton` and the icon table (`IconArrowBackUp`
  re-open, `IconEdit` edit, Settle / Send labelled, discard glyph `_TBD:` closed by D3),
  "Async feedback" and `notifyFailure`, "Mutations are never optimistic" (narrowed to the
  edited row for in-place edits), "Page state".
- `docs/architecture/frontend-structure.md`: "State — MobX 6" (four rules), "Where a
  store's file lives", "Ids are strings", "The API client", "Markdown" (`react-markdown`
  for rendering), "The two stylesheets".
- `docs/architecture/domain-rules.md`: **R6** (archive is not a lock), **R7**, **R10**,
  **R11** (no discard route; re-open gated on an empty zone), **R12** (client previews,
  server decides; parse once; partner text gets no handling).
- Product: `stories/FEAT-009.session-entries.md`, `stories/FEAT-010.compose-discussion.md`,
  `use-cases/FEAT-009.session-entries.md`, `use-cases/FEAT-010.compose-discussion.md`.

Cited, never copied.

## Files this feature touches

```
frontend/
  package.json, package-lock.json      # + react-markdown                           (004)
  src/app/streamApi.ts                 # NEW — Message types + seven calls           (001)
  src/app/parens.ts                    # NEW — pure (( )) rules: classify, segments,
                                       #   strip, settle preview                     (001)
  src/app/streamState.ts               # NEW — data class, derivations, load, sync
                                       #   actions (002); mutation effects (003)
  src/app/MessageBody.tsx              # NEW — markdown + paren painting renderer    (004)
  src/app/StreamRecord.tsx             # NEW — the settled record + re-open control  (004)
  src/app/ZoneList.tsx                 # NEW — zone messages, in-place edit          (005)
  src/app/KindSwitch.tsx               # NEW — the two-position switch               (006)
  src/app/Composer.tsx                 # NEW — textarea, Send, Settle, preview,
                                       #   partner paste, discard                    (006)
  src/app/SessionStream.tsx            # NEW — owns the state; record, ruler, switch,
                                       #   zone, composer                            (007)
  src/app/SessionScreen.tsx            # mounts SessionStream in the ready render    (007)
  tests/app/streamApi.test.ts, tests/app/parens.test.ts                              (001)
  tests/app/streamState.test.ts                                                      (002)
  tests/app/streamMutations.test.ts                                                  (003)
  tests/app/MessageBody.test.tsx, tests/app/StreamRecord.test.tsx,
  tests/build-config.test.ts (checked; conditional)                                  (004)
  tests/app/ZoneList.test.tsx                                                        (005)
  tests/app/KindSwitch.test.tsx, tests/app/Composer.test.tsx                         (006)
  tests/app/SessionStream.test.tsx, tests/app/SessionScreen.test.tsx,
  tests/app/App.test.tsx, tests/entries.test.tsx (checked; conditional)              (007)
```

**Not touched. A step that touches one is out of scope:** everything under `backend/`;
`src/shared/*` (including `api.ts`, `IconButton.tsx`, `notifyFailure.ts`,
`MarkdownEditor.tsx`); `src/global.css`, `src/shell.css` (**no stylesheet, no selector,
no `.css` file**); `src/app/App.tsx`, `WorkspaceShell.tsx`, `sessionScreenState.ts`,
`sessionsApi.ts`, `sessionsState.ts`, every character / setup / tree module;
`vite.config.ts`; `tests/setup.ts`, `tests/conventions.test.ts`,
`tests/stylesheets.test.ts`, `tests/ids-are-strings.test.ts`. The only new npm dependency
is `react-markdown` (D5).

## Cross-cutting constraints every step holds

**Pure data contracts (memory note; `frontend-structure.md` four rules).** `StreamState`
holds observable fields only — no methods, no computed getters. Every derivation is a pure
free function taking the state (or plain values); every effect is a free function taking
the state plus an optional `AbortSignal`, writes inside `runInAction`, early-returns on an
aborted signal before writing, and never rejects. One state instance per stream, created
with `useState(() => new …)`, passed as a prop; no React context; every component that
reads it is an `observer`.

**Never optimistic.** What renders is what the server returned: a list re-read, or — for a
zone edit — the `PATCH` response replacing that one row (`workspace-shell.md`'s narrowed
re-load). Nothing is written into `entries` or `zone` in anticipation of success.

**Nothing typed is lost (R10).** A failed Send, append or edit leaves the roleplayer's text
where it was (composer draft, or the open editor). No operation clears the composer except
a **successful** Send / append, and Discard, which is only offered when the composer holds
nothing but whitespace (D3).

**No discard route, no stop route, no SSE (R11, brief Out).** Discard touches no network.
Nothing streams.

**Client previews, server decides (R12).** The preview and the paint never rewrite text
that is sent, stored or displayed as the row's text; a disagreement with the server is a
display bug only.

**Every icon-only control goes through `shared/IconButton`.** Tests find controls by
accessible name; the names in the UI strings table below are the contract.

**Styling is Mantine only.** Component props and style props (`maw`, `mx`, `px`, `style`);
no `.css` file, no new selector in `shell.css` or `global.css`.

**Ids are strings.** `Message.id` and `session_id` are strings, compared by equality,
never parsed, never used to sort.

**TypeScript only.** No `.js` / `.jsx` / `.mjs` / `.cjs`. No step may leave
`npm run typecheck` failing.

## UI strings — the contract tests bind to

Every fixed string a test may look for. Exact text; components render these and nothing
else for these purposes.

| Where | String | Role / element |
|---|---|---|
| Stream load | **"Could not load the stream"** + button **"Retry"** | in place of the stream (`007`) |
| Settled record | list labelled **"Settled record"** | `list`; each entry a `listitem` (`004`) |
| Settled record, empty | **"No entries yet."** | text (kept from 011 D17) (`004`) |
| Entry kind labels | **"Partner"**, **"My turn"**, **"Decision"** | text in the entry header (`004`) |
| Re-open | **"Re-open last entry"** | `IconButton`, `IconArrowBackUp` (`004`) |
| Out-of-character card label | **"Out of character"** | text inside the card (`004`) |
| Ruler | **"Current zone"** | the one `separator` (accessible name and visible label) (`007`) |
| Zone list | list labelled **"Zone messages"** | `list`; each message a `listitem` (`005`) |
| Zone author labels | **"You"** (`user`), **"Assistant"** (`assistant`), **"Tool"** (`tool`) | text (`005`) |
| Zone edit | **"Edit message"** (`IconButton`, `IconEdit`); editor textbox **"Edit message text"** | (`005`) |
| Kind switch | group **"Entry kind"**; radios **"Partner"** and **"My turn"** | Mantine `SegmentedControl` (`006`) |
| Composer | textbox **"Composer"** | Mantine `Textarea` (`006`) |
| Buttons | **"Send"** (secondary), **"Settle"** (primary) | labelled buttons (`006`) |
| Discard | **"Discard empty zone"** | `IconButton`, `IconX` (`006`, D3) |
| Preview line | **"Settles as a turn."** / **"Settles as a turn; the (( )) instructions will be removed."** / **"Settles as a decision (out of character)."** | text under the composer (`006`, D1) |

No success notification exists anywhere. Mutation failures go through `notifyFailure`
with the thrown error (D15) and are therefore not asserted as text.

## Decisions — settled, with their reasoning

"012 Dn" are in `docs/plans/012.messages-and-settle/context.md`; "011 Dn" in
`docs/plans/011.rp-sessions/context.md`.

### D1 — The settle preview is a client-side port of 012 D8 (user decision; closes the brief's open question)

A pure, DOM-free module (`app/parens.ts`) mirrors 012 D8 / 012 `003.context.md` "The
parser, as spec" exactly: **decision** iff the trimmed text starts with `((` and ends with
`))` (kept verbatim); otherwise a **turn**, whose fragments (shortest `((`…`))` spans,
equivalent to the lazy, dot-matches-newline pattern applied left to right) are stripped by
012's four-step tidy-up. The preview reports the kind and whether anything will be
stripped. It is a line of text under the composer, shown on *my turn* when there is
something to settle, and it previews **what Settle will take**: the composer text when it
holds non-whitespace (D2), otherwise the last zone message (US-126).

Reasoning: a fetched preview would need a route 012 does not have and a round trip per
keystroke; the rules are short and fully specified. The preview is never authoritative — a
disagreement with the server is a display bug, not a data one (R12). Tests take expected
values from `001.context.md`'s worked examples (copied from 012's spec and derived from its
rules), never from calling the module.

### D2 — Settle with unsent composer text appends it, then settles (user decision)

On *my turn*, Settle is enabled when the zone holds a row **or** the composer holds
non-whitespace text. With composer text, Settle first `POST …/zone/messages` with the text
(verbatim), clears the composer on success, then `POST …/settle`. Whatever happens, both
lists are re-read afterwards (012 D11). If the append fails, settle is not attempted and
the text stays in the composer. If the append succeeds and settle fails, the message simply
stays in the zone, settleable — nothing is lost (R10). Settle is **never** gated on an
assistant reply (US-135). It is disabled when the zone is empty and the composer is blank,
while a mutation is in flight, and always on the *partner* position (disabled, not hidden —
`workspace-shell.md`).

### D3 — Discard is offered only for an empty zone with a blank composer, and resets the switch (user decision)

The Discard control is **present** only while the zone has no rows **and** the composer
holds nothing but whitespace; otherwise it is **absent**, not disabled (US-134.AC-2).
Pressing it clears the (whitespace-only) composer and **resets the kind switch to its
computed default**. It never throws away typed text — UC-086's postcondition read
literally: "nothing the roleplayer wrote is ever discarded by abandoning". It makes **no
request** (R11: an empty zone is the empty set; there is nothing to discard). Glyph:
**`IconX`** through `IconButton`, labelled **"Discard empty zone"** — closing
`ui-conventions.md`'s `_TBD:`; `IconX` already means "dismiss" on the wall, which is the
same gesture, while `IconTrash` would promise a deletion of content that does not exist.
`outcome.md` asks the architect to amend `workspace-shell.md`'s "clears the unsent draft"
wording and record the glyph.

### D4 — Re-open is a control on the last settled entry, frontend-gated on the zone (user decision)

`IconArrowBackUp` through `IconButton`, labelled **"Re-open last entry"**, inside the
**last** settled entry, **present** only when the zone has no rows and that entry's kind
is not `partner`; absent (not disabled) otherwise (US-128, `workspace-shell.md`). The
composer's content does not gate it — re-open depends on zone rows only (R11). Pressing it
`POST …/reopen`, then re-reads both lists. A refusal — `nothing_to_reopen` (a lone
directly-settled turn or decision, 012 D10), `zone_not_empty`, or anything else — goes
through `notifyFailure` and the lists are re-read. **Accepted imprecision:** the control
shows on a lone directly-settled turn or decision and is refused there, because the client
cannot see whether a buried group exists (no buried-read route until `022`). No backend
change. `outcome.md` records it.

### D5 — `react-markdown` renders bodies; `(( ))` is painted in the zone only (user decision; scope of painting refined here)

`react-markdown` becomes a frontend dependency (`004`). One renderer component
(`app/MessageBody.tsx`) has three variants:

- **painted** — every **zone** message (any role): a wholly-parenthesised text (D1's
  decision rule) renders as the **out-of-character card** (dashed, accent-coloured border,
  label "Out of character", the text verbatim inside); otherwise the text is cut into
  prose and fragment segments by the same scanner as D1, prose rendered through
  `react-markdown`, each fragment as an inline chip showing the fragment verbatim.
- **decision** — a settled `kind='decision'` entry renders as the same card **because of
  its kind**, not by re-parsing (R12).
- **plain** — a settled `partner` or `turn` entry renders through `react-markdown` with
  **no painting**. Partner text's parentheses are the partner's words (US-121.AC-2, R12);
  a settled turn's fragments were already stripped, and painting a later-edited turn would
  re-parse stored text, which R12 forbids. `workspace-shell.md` locates painting "inside
  the zone".

Display only: the stored text is never rewritten, and the text sent to the server is the
text as typed.

### D6 — Send appends without a model call; Settle is the primary button (planner decision)

**Send** (labelled, secondary) on *my turn* is `POST …/zone/messages` with the composer
text verbatim — the non-streaming sibling of compose; no model call. On success the
composer clears and the zone is re-read. On failure the text stays in the composer.
Streaming compose, the stop control and retries are out (`019`, `022`). **Settle** is the
labelled primary button. Send is enabled when the composer holds non-whitespace text and no
mutation is in flight, on either position.

### D7 — The *partner* position files immediately (planner decision; 012 D14)

On *partner*, a **paste** into the composer files the pasted plain text at once through
`POST …/entries` `{kind:"partner", text}`: the default paste insertion is prevented and the
composer's content is unchanged. A paste with no non-whitespace text sends nothing.
**Send** on *partner* files the typed composer text as a partner block and clears the
composer on success. After a filing (success or failure) the entries are re-read. There is
**no zone precondition and no UI guard** (012 D14) — filing works with zone rows present.
On a failed paste the text is not re-inserted into the composer: the clipboard still holds
it, and inserting it would put partner text where *my turn* text is composed. The
enormous-paste warning is `014`'s.

### D8 — The kind switch and its default (planner decision; default with an empty record chosen here)

A Mantine `SegmentedControl` above the zone with two labelled segments, **Partner** and
**My turn** (`ui-conventions.md`: two labelled segments, no icons). The **computed
default** is the alternate of the last entry whose kind is `partner` or `turn` — decisions
are skipped (US-120.AC-1..AC-3, 012 D5). **With no such entry the default is *my turn*.**
Reasoning: UC-031 allows either opening, and the two wrong guesses cost differently — a
wrong *partner* default turns the roleplayer's first paste of their own text into a filed
partner block that cannot be re-opened (012 D10) and cannot be edited before `014`, while
a wrong *my turn* default costs one click on the switch.

A manual choice (the **override**) holds until the record changes — an entries re-read
whose id sequence differs from the held one — or Discard resets it. Zone-only re-reads
(Send, edit) never clear it.

### D9 — The composer (planner decision; geometry from `workspace-shell.md`)

A Mantine `Textarea` with `autosize`, a `minRows` that gives about 42px, **no `maxRows`**,
no resize handle (Mantine's default `resize` of none), plain text — not TipTap. It shares
the stream's column: `maw={720}`, centred, `px={18}` — Mantine style props, no stylesheet.
The draft lives in `StreamState` so the derivations (`canSettle`, discard, preview) read
it.

### D10 — Zone messages are edited in place (planner decision; failure posture refined here)

Each zone message, any role (US-115.AC-1), carries an `IconEdit` `IconButton` labelled
**"Edit message"** that swaps the rendered body for an autosizing `Textarea` labelled
**"Edit message text"**, holding the row's text and focused. **Blur commits**: a blank or
unchanged text closes the editor with no request; otherwise `PATCH /api/messages/{id}`,
and the response replaces that one row in the zone. On failure: `notifyFailure`, the zone
is re-read, and the **editor stays open holding the typed text** (planner refinement on
R10: a failed save must not lose the edit; blurring again retries). If the row has left
the zone (e.g. `message_not_editable` after a settle elsewhere), the re-read removes it and
its editor with it. Which message is being edited and its draft are **component-local
view state** (`ui-conventions.md`'s modal-flag reasoning). The edit control is always
visible: a hover / `:focus-within` reveal needs a stylesheet, and the settled-entry action
reveal is `014`'s.

### D11 — Settled entries are read-only in 013, with no copy action anywhere (planner decision)

Editing and copying settled entries are `014`'s (brief Out). A settled entry renders its
kind label and body, and the last one may carry the re-open control (D4). No entry renders
a copy control, so US-123.AC-1 holds for decisions trivially; `004` still pins it with a
test so `014` cannot add copy to a decision unnoticed.

### D12 — One ruler (planner decision)

A Mantine `Divider` with the visible label **"Current zone"**, exposed as the stream's
**only** element with role `separator`, accessible name "Current zone", placed between the
record and the kind switch. One per session screen (US-125.AC-1).

### D13 — State placement: a sibling module owned by the stream component (planner decision)

`app/streamState.ts` holds `StreamState` (data), its derivations and its effects, rather
than growing 011's `sessionScreenState.ts`: the session header and the stream load and fail
independently, and 011's module stays one GET. `app/SessionStream.tsx` creates the state
once per mount and loads on mount with an `AbortController` aborted on unmount; 011's
`SessionScreen.tsx` renders it **in place of the "No entries yet." line** in its ready
render, for archived sessions too (R6 — archive is not a lock). `SessionRoute` already keys
the screen by session id, so navigating between sessions remounts the stream with a fresh
state.

### D14 — The API module (planner decision)

`app/streamApi.ts` mirrors the wire: the `Message` type field for field, the settle and
re-open result types, and one function per route (seven), each taking string ids and an
optional signal, resolving to the unwrapped payload, rethrowing the shared client's
`ApiError` unchanged.

### D15 — Feedback, busy and failure handling (planner decision)

- **Load failure** renders in place: **"Could not load the stream"** + **"Retry"** (a
  failure with a place of its own is not also a notification).
- **Every mutation failure** (send, file partner, append, settle, re-open, edit) and any
  **re-read failure after a mutation** goes through `notifyFailure(error)` — it has no
  place of its own — followed by the re-read the mutation calls for. No code is branched
  on.
- **No success notification**, ever (`ui-conventions.md`: "a notification whose message is
  a success is a defect").
- `StreamState.busy` is true while a send / file / settle / re-open is in flight; Send,
  Settle and Re-open are disabled while it is. Edits do not set it.

### D16 — Whitespace: JavaScript's trim, not Python's `isspace` (planner decision)

012 D8 defines whitespace as Python's `str.isspace`. The client trims with JavaScript's
`String.prototype.trim` / `\s`. The two sets differ only on rare code points (U+001C–U+001F
and U+0085 are Python-only; U+FEFF is JavaScript-only). Any resulting preview disagreement
is a display bug only (R12, D1) and is accepted rather than hand-building Python's set. No
test pins these code points.

### D17 — Seven steps

The two pure modules (API, parens) together; the state split in two (data + derivations +
load, then the mutation effects) because together they exceed 200 LoC; the renderer with
the record (it is the first renderer user and brings the dependency); the zone; the switch
with the composer; the stream assembly with the session-screen hook. The suggested five to
six became seven for the state split.

## Step map

| Step | Subject | Est. LoC | Depends on |
|------|---------|----------|------------|
| 001 | `streamApi.ts` + `parens.ts` | ~150 | none (012 wire shapes; tests stub `fetch`) |
| 002 | `streamState.ts` — data class, derivations, load, sync actions | ~120 | 001 |
| 003 | `streamState.ts` — mutation effects | ~150 | 001, 002 |
| 004 | `react-markdown`; `MessageBody.tsx`; `StreamRecord.tsx` | ~150 (lockfile not counted) | 001, 002, 003 |
| 005 | `ZoneList.tsx` — zone messages with in-place edit | ~100 | 002, 003, 004 |
| 006 | `KindSwitch.tsx` + `Composer.tsx` | ~160 | 001, 002, 003 |
| 007 | `SessionStream.tsx` + ruler + `SessionScreen.tsx` hook + 011 test amendments | ~80 | 002–006; 011 `009` delivered; 012 delivered for `[manual/live]` |

`005` and `006` are independent of each other.

## Test conventions

Inherited from 011 `context.md` "Test conventions" (frontend paragraph, via 009): Vitest,
`globals: false`, `tests/` mirrors `src/`, each `it` title ends **`— DoD-N`** of its own
step, `fetch` stubbed per test file with `vi.stubGlobal` and file-local helpers (no shared
helpers module), `AppProviders` around rendered components, `MemoryRouter` where routed,
assertions on rendered behaviour only. Additions for 013:

- **Stubs by exact path and method.** `/api/sessions/<id>`, `/api/sessions/<id>/entries`,
  `/api/sessions/<id>/zone`, `/api/sessions/<id>/zone/messages`, `…/settle`, `…/reopen`
  and `/api/messages/<id>` share prefixes; a stub or request log keys on the exact pathname
  plus method, never a prefix. Request **order** is asserted from the stub's log where a
  DoD says "then".
- **`notifyFailure` is observed by `vi.mock`** of `src/shared/notifyFailure` (relative to
  the test file), asserting it was called with an `ApiError` carrying the stubbed code — or
  not called at all. No test asserts notification text.
- **Payload builders** are file-local: a `Message` with all eight keys, string ids
  (`"7250000000000000101"` style), `kind` null for zone rows.
- **Expected values come from this plan** — the parens worked examples in `001.context.md`,
  the strings table above — never from calling `parens.ts` or a derivation to compute an
  expectation.
- **Scoping.** The session screen's main region also holds 011's header; stream assertions
  scope to the main region and then to the named lists ("Settled record", "Zone
  messages").
- **Mantine `SegmentedControl`** renders radio inputs: choose with
  `getByRole("radio", { name: "Partner" })`. Pasting is simulated with
  `fireEvent.paste(textbox, { clipboardData: { getData: () => text } })`.
- **Geometry** (720px, 18px, 42px min, no max) is `[manual/live]`; jsdom does not lay out.

## Vocabulary

| Term | Means here |
|---|---|
| **record** / **entries** | the session's settled rows, from `GET …/entries` |
| **zone** | the session's current-zone rows, from `GET …/zone` |
| **composer** / **draft** | the textarea below the zone and its unsent text (`StreamState.draft`) |
| **blank** | empty or whitespace only (JavaScript `trim`, D16) |
| **position** | the kind switch's value: *partner* or *my turn* (`"partner"` / `"turn"`) |
| **default** / **override** | the computed position (D8) / a manual choice that supersedes it until the record changes or Discard |
| **settle target** | the text Settle will take: the draft if non-blank, else the last zone row's text (D1, D2) |
| **fragment** | the shortest `((`…`))` span (012 D8) |
| **painting** | rendering fragments as chips and wholly-parenthesised text as the out-of-character card — display only (D5) |
| **re-read** | `GET …/entries` and / or `GET …/zone` replacing the held list with the server's |
