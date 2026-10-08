# Feature 014 — Entry editing and copy-out · feature-wide context

## What this feature is

The settled record becomes mutable forever, and text gets back out. On `/sessions/:id`
every settled entry — partner block, turn or decision — carries an **edit** control that
swaps its body for a plain textarea where it sits; **blur saves** through the existing
`PATCH /api/messages/{id}`, which the backend now accepts for settled rows as well as zone
rows. A settled **turn** also carries a **copy** control that puts the entry's text on the
clipboard as **plain text** (markdown syntax stripped client-side, no request). The entry
actions (edit, copy, and 013's re-open) are revealed while the entry is hovered or holds
focus. An **enormous paste** into the composer raises a transient warning about context
cost and is never blocked or delayed.

The agreed boundary is `brief.md` in this folder. Its Definition and Scope In/Out bound
every step and are **not** widened. Its two open questions are closed by **D3** (the
threshold — user decision) and **D2** (`last_used_at` — orchestrator default).

**Mostly frontend.** One backend module changes (`services/messages.py`, step `001`); no
route, model, table or error is added.

## Product ids

Delivered (per brief): FEAT-009 — UC-029, UC-030, UC-078, UC-082; US-032.AC-1,
US-033.AC-1, US-035.AC-1, US-035.AC-2, US-109.AC-1, US-110.AC-1, US-124.AC-1.
**US-123.AC-1 must keep holding** (a decision offers no copy) — 013 pinned it; 014 adds
copy next to it and re-pins it.

| Criterion | Where it lands |
|---|---|
| US-032.AC-1 / UC-029 (a settled answer from weeks ago is edited and saved) | `001` (backend accepts the settled row), `004` (effect), `005` (in-place editor) |
| US-109.AC-1 (partner block edited in place, saved on blur) | `001`, `004`, `005` |
| US-110.AC-1 / UC-078 steps 1–3 (any settled kind edited in place, saved on blur) | `001`, `004`, `005` |
| US-033.AC-1 / UC-030 (one click puts the turn's RP-language text on the clipboard; nothing else changes) | `004` (copy effect, no request), `005` (control) |
| US-124.AC-1 / UC-082 (the clipboard holds plain text, no markdown syntax) | `002` (the stripper), `004`, `005` |
| US-123.AC-1 (no copy on a decision — must keep holding) | `005` (absent, not disabled; amends 013 `004` DoD-9) |
| US-035.AC-1 / UC-027 exception flow (an enormous paste warns about context cost) | `003` |
| US-035.AC-2 (the paste is never refused — the entry is added regardless) | `003` (the filing request is still made; 012 D9 already has no maximum length) |

**Not delivered here (brief Out, or later features):**

- **US-032.AC-2** (the assistant reads the edited text) falls out of context assembly in
  `020`: the edit overwrites `messages.text`, and there is no other copy to read. No 014
  work; recorded so nobody adds a "context refresh".
- **US-109.AC-2 / US-110.AC-2** and UC-078's "search thereafter reflects the new text"
  (`session_search`, re-indexing) — `024` / `027`.
- **US-111** (discard a partner block's cached translation on edit) — `023`.
- **US-112** and UC-078's exception flow (no embedding model → edit saves, coverage notice)
  — `024`. 014's edit is plain success / failure; `backend-structure.md`'s degraded
  embedding path does not exist yet.
- Editing a collapsed (buried) discussion — forbidden (US-116), read surface is `022`.
  Buried rows stay `message_not_editable`.

## Build prerequisite — 011, 012 and 013 are planned, not built

001..010 are built. **011, 012 and 013 exist only as step files.** 014 binds to their
**declared** interfaces, cited from their step files and not re-specified.

| Upstream artifact | What 014 relies on | Needed by |
|---|---|---|
| 012 `001` — `db/schema.py` `message_states`, `settled_entries`, `current_zone`; `errors.py` `MessageNotFoundError` / `MessageNotEditableError`; `models/stream.py` `EditMessageRequest`, `MessageResponse` | the classifier, the two read-backs, the unchanged request / response models (012 D7, D9) | `001` |
| 012 `002` — `services/messages.py` `edit_message_text` and `tests/test_messages_service.py` | the function 014 widens; DoD-9's settled-refusal cases are amended | `001` |
| 012 `004` — `routers/stream.py` `PATCH /api/messages/{message_id}` and `tests/test_stream_router.py` | the route, unchanged; DoD-13's settled-refusal cases are amended | `001` |
| 012 D3 ("every content write bumps the session") | the precedent D2 extends | `001` |
| 013 `001` — `app/streamApi.ts` `Message`, `editMessage`, `fetchEntries`, `fetchZone` | the PATCH call and the re-reads; **no new API function** | `004` |
| 013 `002` / `003` — `app/streamState.ts` `StreamState`, `applyEntries`, `effectiveKind`, `isBlank`, `chooseKind`; `editZoneMessage` as the pattern | the state 014's effect writes; the override rule it must not disturb | `003`, `004` |
| 013 `004` — `app/StreamRecord.tsx`, `app/MessageBody.tsx`; `tests/app/StreamRecord.test.tsx` | the entry rendering 014 extends; DoD-9 ("no Copy anywhere") is amended | `005` |
| 013 `005` — `app/ZoneList.tsx` | the in-place editor **pattern** (not imported) | `005` |
| 013 `006` — `app/Composer.tsx` | the paste handler the warning attaches to | `003` |
| 013 `007` — `app/SessionStream.tsx` | the mounted stream, for the `[manual/live]` items | `003`, `005` |

- Step `002` imports nothing and can be built today.
- Step `001` needs **012 `001`, `002`, `004` delivered** (it edits 012's module and
  amends 012's test files).
- Steps `003`, `004`, `005` need **013 `001`–`006` delivered** (they edit 013's modules or
  amend 013's test files). Their `[manual/live]` items need **012 and 013 delivered** and
  step `001` done.

## Built state this feature reads

- `src/shared/IconButton.tsx`: props `icon`, `label` (also its tooltip and
  `aria-label`), `onClick`, `disabled?`, `color?`, `sizeVariant?` (`"main"` / `"inline"`
  / `"chevron"`).
- `src/shared/notifyFailure.ts`: `notifyFailure(error)` → `notifications.show({ message,
  color: "red" })`. No success path, no colour parameter. **No warning helper exists.**
- `src/shared/api.ts`: `apiGet` / `apiPost` / `apiPatch` / `apiDelete`; paths start
  `/api/`; failures are `ApiError`.
- `tests/conventions.test.ts`: the test "Mantine's notification API is imported by
  shared/notifyFailure.ts alone" fails on any other `@mantine/notifications` importer.
  No clipboard guard.
- `tests/stylesheets.test.ts`: `shell.css` may hold only its five selectors and there are
  exactly two `.css` files — **so no CSS `:hover` / `:focus-within` rule is possible**
  (D6).
- `package.json`: no markdown-to-text library (no remark / unified / strip-markdown /
  remove-markdown). `react-markdown` arrives with 013 `004`, **without `remark-gfm`**.
- No `navigator.clipboard` use anywhere in `src/`; `tests/setup.ts` does not mock it.

## Architecture this binds to

- `docs/architecture/workspace-shell.md` "The stream — the settled record": the three
  kinds and the actions table (amended by D7 — copy on turns only), actions inside the
  entry header revealed on hover **or** focus-within (mechanism by D6), in-place edit with
  blur commit and **no modal** (a bounded exception), a commit re-reads the edited row
  only, copy strips the settled text rather than serialising the DOM.
- `docs/architecture/ui-conventions.md`: icon table (`IconCopy` "Copy settled turn out",
  `IconEdit` one edit icon for entries, messages and notes), the `IconCopy` notes
  (absent, not disabled, on a decision), "Async feedback" (failure-only through
  `shared/notifyFailure`; "a notification whose message is a success is a defect") —
  extended by D4.
- `docs/architecture/backend-structure.md` "The stream routes": "`PATCH
  /api/messages/{message_id}` spans both views on purpose"; buried → `message_not_editable`.
  "The two transaction rules" (degraded embedding path) — **not built until `024`**.
- `docs/architecture/domain-rules.md`: **R5**, **R6**, **R7** (a settled turn is editable
  forever), **R10** (an enormous paste is warned, never refused; the warning is a
  client-side notice), **R11**, **R12** (an edit is taken literally — never re-parsed).
- `docs/architecture/deployment.md` "client_max_body_size 64m" (the nginx half of
  never-refused) and "TLS — none" (D9).
- `docs/architecture/frontend-structure.md` "State — MobX 6" (four rules).
- `docs/architecture/llm-and-streaming.md` (an enormous paste warns; the session's own
  size never does).
- Product: `stories/FEAT-009.session-entries.md`, `use-cases/FEAT-009.session-entries.md`.

Cited, never copied.

## Files this feature touches

```
backend/
  app/services/messages.py              # edit_message_text accepts settled rows      (001)
  tests/test_messages_service.py        # 012 DoD-9 amended + 014 cases               (001)
  tests/test_stream_router.py           # 012 DoD-13 amended + 014 cases              (001)
frontend/
  src/app/plainText.ts                  # NEW — pure markdown → plain text            (002)
  src/app/pasteCost.ts                  # NEW — pure token estimate + threshold       (003)
  src/shared/notifyWarning.ts           # NEW — the second notification outlet        (003)
  src/app/Composer.tsx                  # paste handler warns (both positions)        (003)
  src/app/streamState.ts                # + editEntry effect                          (004)
  src/app/copyOut.ts                    # NEW — copy as plain text to the clipboard   (004)
  src/app/StreamRecord.tsx              # entry actions: reveal, edit, copy           (005)
  tests/app/plainText.test.ts                                                         (002)
  tests/app/pasteCost.test.ts, tests/shared/notifyWarning.test.ts,
  tests/conventions.test.ts (amended), tests/app/ComposerPasteWarning.test.tsx        (003)
  tests/app/entryEffects.test.ts                                                      (004)
  tests/app/StreamRecordActions.test.tsx, tests/app/StreamRecord.test.tsx (amended)   (005)
```

**Not touched. A step that touches one is out of scope:** `backend/app/routers/stream.py`,
`models/stream.py`, `db/schema.py`, `errors.py`, `services/settle.py`,
`services/parens.py`, `main.py` and every other backend module; `src/shared/*` other than
the new `notifyWarning.ts` (`notifyFailure.ts`, `IconButton.tsx`, `api.ts`,
`AppProviders`); `src/app/streamApi.ts`, `parens.ts`, `MessageBody.tsx`, `ZoneList.tsx`,
`KindSwitch.tsx`, `SessionStream.tsx`, `SessionScreen.tsx`; `src/global.css`,
`src/shell.css` (**no stylesheet, no selector, no `.css` file**); `vite.config.ts`;
`tests/setup.ts`, `tests/stylesheets.test.ts`. **No new npm or Python dependency.**

## Cross-cutting constraints every step holds

**Edits are taken literally (R12).** Nothing in 014 parses `(( ))` in an edit, on either
side. The server keeps `kind` and `settled_at` exactly as they were; the client renders the
served row by its kind (013 D5), never by re-reading the text.

**Never optimistic, narrowed to the row.** A successful settled-entry edit replaces that
one row in `entries` from the `PATCH` response (`workspace-shell.md`: "a commit re-reads
the edited row rather than the stream"); a failure re-reads the entries. Nothing is
written into `entries` in anticipation of success.

**Nothing typed is lost (R10).** A failed edit keeps the editor open with the typed text.
The paste warning never prevents, delays or alters a paste or a filing.

**Copy changes nothing (UC-030 postcondition).** No request, no state write, no "sent"
mark.

**Notifications.** Failures go through `notifyFailure` with the thrown value; the paste
warning goes through `notifyWarning` (D4); **no success notification anywhere** —
including after a copy and after a save.

**Pure data contracts (memory note; `frontend-structure.md`).** `StreamState` stays
fields-only; effects are free functions taking the state and an optional signal, writing
inside `runInAction`, writing nothing once aborted, never rejecting. Which entry is being
edited and its draft are component-local view state (013 D10).

**Every icon-only control goes through `shared/IconButton`.** Tests find controls by
accessible name; the UI strings below are the contract.

**Styling is Mantine only** — props and style props; no `.css`, no selector (D6).

**Ids are strings**, compared by equality. **TypeScript only**; `npm run typecheck` and
backend `mypy app` stay green after every step.

## UI strings — the contract tests bind to

Exact text. 013's table (`docs/plans/013.stream-and-zone-ui/context.md`) still applies;
these are 014's additions.

| Where | String | Role / element |
|---|---|---|
| Settled entry edit | **"Edit entry"** | `IconButton`, `IconEdit`, in each entry's header (`005`) |
| Settled entry editor | **"Edit entry text"** | autosizing Mantine `Textarea` (`005`) |
| Settled turn copy | **"Copy as plain text"** | `IconButton`, `IconCopy`, on `turn` entries only (`005`) |
| Paste warning | **"This paste is very large and will take up a lot of the assistant's context."** | the `notifyWarning` message (`003`) |

The zone's **"Edit message"** / **"Edit message text"** (013) are deliberately distinct, so
a test finding one never matches the other. A copy failure goes through `notifyFailure`
with the thrown value and is not asserted as text.

## Decisions — settled, with their reasoning

"012 Dn" are in `docs/plans/012.messages-and-settle/context.md`; "013 Dn" in
`docs/plans/013.stream-and-zone-ui/context.md`. Each heading says who decided.

### D1 — `PATCH` accepts settled rows of all three kinds; buried stays refused (orchestrator default)

`edit_message_text` (012 `002`) classifies through `message_states` as before: none →
`message_not_found`; buried → `message_not_editable` (US-116, unchanged); **settled →
proceeds** (US-110.AC-1 names all three kinds); zone → proceeds as before. The update
writes `text` (verbatim) and `updated_at` only — **`kind`, `settled_at` and `related_to`
are never written**, so a turn edited into `((whole))` stays a turn and a decision edited
into prose stays a decision (R12). The row is read back through the selectable that
matches its classified state: `current_zone` for a zone row, **`settled_entries` for a
settled row** (the settled row is not in `current_zone`). Same response model, same route,
same 422 for blank text, no maximum length (012 D9). This is
`backend-structure.md`'s "spans both views on purpose" as built; it replaces 012 D2's
interim refusal.

### D2 — A settled edit bumps the session (orchestrator default; closes the brief's second open question)

By 012 D3's precedent ("every content write bumps the session"): editing a settled row
sets `sessions.last_used_at` **and** `updated_at` to the operation's instant, in the same
transaction, exactly as a zone edit does. A refused edit writes nothing. Reasoning: an edit
to a weeks-old turn is the roleplayer working in that session now; one rule for every
content write is simpler than a per-row-state exception, and `updated_at` "moves on any
write" (`data-model.md`).

### D3 — The enormous-paste threshold: ~32K tokens, estimated as characters ÷ 4 (user decision; closes the brief's first open question)

No tokenizer exists client-side. Two named constants in a pure, DOM-free module
(`app/pasteCost.ts`): **characters per token = 4** and **warning threshold = 32,000
tokens**. The estimate is `ceil(length / 4)` where length is the string's `length`
(UTF-16 code units, as typed — no trimming). A paste is **enormous** iff its estimate is
**strictly greater than** 32,000 — i.e. it fires above **128,000 characters**. Boundary
examples (tests take these, never the module): 128,000 characters → no warning; 128,001 →
warning. Reasoning: a quarter of a token per character is the common English heuristic and
errs toward warning; 32K tokens is a large fraction of most local models' context, which
is what "context cost" means. The heuristic is advisory only — nothing depends on its
precision, because nothing is ever refused (R10).

### D4 — The warning goes through a new `shared/notifyWarning` (user decision; closed-set shape is a planner refinement)

A second sanctioned notification outlet, `src/shared/notifyWarning.ts`, beside
`notifyFailure`: transient (the outlet's existing `autoClose: 5000` — no per-call
override), **yellow** (not failure red), and it takes **a warning identifier from a closed
set, not free text**. The set has exactly one member today — the paste context-cost
warning — and the module owns its fixed sentence (UI strings table). Reasoning:
`ui-conventions.md` makes "a success notification is a defect" structural by giving
`notifyFailure` no way to express success; a `notifyWarning(message: string)` would
reopen that door, while a closed set keeps it shut — adding a warning is an edit to this
one module, visible in review. `tests/conventions.test.ts` is amended to allow **exactly**
`notifyFailure.ts` and `notifyWarning.ts` as importers of `@mantine/notifications`.
`outcome.md` asks the architect to add the warning class to "Async feedback".

### D5 — Where the paste warning fires (orchestrator default)

On **composer** pastes, in **both** positions, and only when the pasted plain text is not
blank and is enormous (D3):

- *partner* — inside 013 `006`'s interception: the warning is raised, then the filing
  proceeds exactly as before (013 D7). The warning is a synchronous fire-and-forget call;
  the filing is never awaited on it, gated by it or delayed by it (US-035.AC-2).
- *my turn* — the handler inspects the size and raises the warning; it **does not**
  prevent the default insertion (013 D7's "a paste behaves normally" holds).

Pastes into the in-place editors (zone message, settled entry) **do not warn** — out of
scope; their text is already in the session, and the brief names the composer paste.

### D6 — Entry actions revealed with Mantine hooks, by opacity (user decision on hooks; mechanism details are planner refinements)

Each settled entry's header holds one actions group — **edit**, **copy** (turns only) and
013's **re-open** (last entry only, 013 D4). The group is revealed while the entry is
**hovered** (`@mantine/hooks` `useHover`) **or has focus within** (`useFocusWithin`), the
two refs merged onto the entry element (`useMergedRef`), plus **always** on a device that
cannot hover (`useMediaQuery` on `(hover: none)`) so touch users are not left with
invisible controls. The reveal state is a boolean rendered as the group's
`data-revealed="true" | "false"` attribute (the stable test contract) and applied as a
style prop **`opacity`** (0 hidden, 1 revealed) — **never `display: none`, `visibility:
hidden`, conditional rendering or `disabled`**. Reasoning: an opacity-0 button stays in
the DOM and in the tab order, so tabbing to it puts focus within the entry, which reveals
it — keyboard reach (`workspace-shell.md`'s reason for `:focus-within`) holds without a
stylesheet, which `tests/stylesheets.test.ts` forbids. Consequence: 013's re-open tests
(present / absent in the DOM, pressing it) are unaffected — absence is still absence, and
a hidden control is still present. The visual reveal is `[manual/live]` (jsdom has no
layout). `outcome.md` asks the architect to record the mechanism (hooks, not CSS).

### D7 — Copy on turns only (user decision)

The **"Copy as plain text"** `IconButton` (`IconCopy`) is rendered on `kind='turn'`
entries only — **absent, not disabled**, on `decision` (US-123.AC-1) **and on `partner`**.
Reasoning: US-033 / UC-030 / UC-082 speak of the roleplayer's own settled answer; the
partner's text already came from the destination. `workspace-shell.md`'s actions table
lists copy on partner; `outcome.md` asks the architect to reconcile it.

### D8 — Plain text by a hand-written, pure CommonMark-subset stripper (orchestrator default; the rules are the planner's)

`app/plainText.ts` — pure, DOM-free, no dependency (parallel to 013's `parens.ts`) —
converts a settled text to plain text. **What counts as syntax is what the record's
renderer treats as syntax:** `react-markdown` without plugins, i.e. **CommonMark, not
GFM** — so `~~x~~`, tables, task lists and bare-URL autolinks are not syntax and are left
as typed. The principle: **remove the syntax, keep the author's words and line
structure**; where a marker's visible effect would otherwise vanish (an unordered list
bullet) substitute the plain character the renderer shows (`• `); ordered-list numbers are
already plain and stay. Single line breaks inside a paragraph are **kept** (the author typed
them and chat boxes honour them), deliberately unlike the rendered reflow. The exact rules
and worked examples are `002.context.md` "The stripping rules, as spec" — the authority.
Copy reads the **stored** text and strips (`workspace-shell.md`), never the rendered DOM.

**A recorded consequence, not a gap:** RP prose often marks actions with asterisks
(`*She smiles*`). Under US-124.AC-1 these are markdown emphasis and are stripped
(`She smiles`). The product criterion is literal ("no markdown syntax"); if the roleplayer
wants the asterisks kept, that is a product change to US-124, not a plan fix.

### D9 — The clipboard write, with a fallback for an insecure origin (planner decision — flagged)

`app/copyOut.ts` writes the plain text with `navigator.clipboard.writeText` when the API
exists. **When `navigator.clipboard` is absent** — which it is on any non-secure origin,
and `deployment.md` records the instance as HTTP-only on a trusted LAN, so any access by
LAN address rather than `localhost` — it falls back to a temporary off-screen textarea,
selection and `document.execCommand("copy")`, removing the element afterwards and
returning focus to where it was. A `writeText` rejection, a fallback that reports `false`
or throws → `notifyFailure` (it is a failure with no place of its own). Success raises
nothing. Reasoning: the clipboard is the product's **entire outbound boundary**
(`vision.md`, `ui-conventions.md`'s `IconCopy` note); a copy that fails on every LAN
client would defeat the feature on the documented deployment. `execCommand` is deprecated
but universally implemented, and it is used only where the modern API cannot exist. Flip
condition: TLS lands (`deployment.md`'s `_TBD:`) — then the fallback is dead code and may
go.

### D10 — The settled-entry editor reuses 013 D10's pattern (orchestrator default)

**"Edit entry"** (`IconEdit`) swaps the entry's body for an autosizing plain Mantine
`Textarea` **"Edit entry text"** (not TipTap), holding the stored text, focused. The
editing flag and draft are component-local. **Blur commits** through a new effect
`editEntry` (`004`): blank or unchanged → no request, editor closes; otherwise `PATCH`;
success → the response replaces **that one row** in `entries` (same id sequence, so 013
D8's kind override is untouched) and the editor closes; failure → `notifyFailure`, the
entries are re-read, and the editor **stays open with the typed text**. If the success
response is not a settled row (`settled_at` null — the row was re-opened from another tab),
the entry has left the record: the effect re-reads entries **and** zone instead of
writing the row into `entries`. While an entry's editor is open its "Edit entry" control is
absent (pressing it mid-edit would reset the draft). Edits do not set `busy`.

### D11 — Five steps

The backend widening alone (~30 LoC — below the 50-line floor, kept separate because it is
the only backend step and runs a different toolchain and test suite); the pure stripper
alone (it is the largest pure module and has no dependency, so it can be built today); the
paste warning with its helper and the composer hook (three small pieces with one user);
the two effects (edit, copy); the record UI.

## Step map

| Step | Subject | Est. LoC | Depends on |
|------|---------|----------|------------|
| 001 | `services/messages.py` — settled rows editable; 012 tests amended | ~30 | 012 `001`, `002`, `004` delivered |
| 002 | `app/plainText.ts` — pure markdown → plain text | ~120 | none |
| 003 | `app/pasteCost.ts`, `shared/notifyWarning.ts`, `Composer.tsx` paste warning | ~60 | 013 `002`, `006` delivered |
| 004 | `streamState.ts` `editEntry` + `app/copyOut.ts` | ~80 | 002; 013 `001`–`003` delivered |
| 005 | `StreamRecord.tsx` — reveal, in-place edit, copy on turns | ~140 | 004; 013 `004` delivered; `001` + 012 / 013 delivered for `[manual/live]` |

`001`, `002` and `003` are independent of each other.

## Test conventions

**Backend** — inherited from 012 `context.md` "Test conventions" (pytest from `backend/`,
no shared fixtures added, schema from `create_all`, file-local `_insert_user` / `_login`,
two users, raw-insert FK chain, timestamps asserted by shape and by equality /
non-decrease). 014 **amends 012's test files in place**: the cases that asserted a
settled-row refusal are rewritten as successes; the buried-row refusals stay.

**Frontend** — inherited from 013 `context.md` "Test conventions" (Vitest, `globals:
false`, `tests/` mirrors `src/`, each `it` title ends **`— DoD-N`** of its own step,
`fetch` stubbed per file with exact path + method, `notifyFailure` observed by `vi.mock`,
file-local payload builders with all eight `Message` keys and string ids, `AppProviders`
around rendered components, expected values from this plan). Additions for 014:

- **Amended 013 tests keep their 013 title suffix** and are listed in the amending step's
  Test files; new tests carry 014's ids.
- **`notifyWarning`** is observed by `vi.mock` of `src/shared/notifyWarning` (relative to
  the test file); only its own test mocks `@mantine/notifications`.
- **Clipboard.** No global mock exists and `tests/setup.ts` is not touched: a test file
  that copies installs `navigator.clipboard` with `Object.defineProperty(navigator,
  "clipboard", { value: { writeText: vi.fn() }, configurable: true })` (or deletes it to
  exercise the fallback, with `document.execCommand` stubbed) and restores it afterwards.
- **Large pastes** are built with `"a".repeat(n)` from the boundary numbers in D3.
- **Reveal.** Hover with `fireEvent.mouseEnter` / `mouseLeave` on the entry's `listitem`;
  focus with `element.focus()` (inside `act`); assert the actions group's `data-revealed`.
  Visual opacity is `[manual/live]`.
- **Default-prevented pastes**: `fireEvent.paste(...)` returns `false` iff the handler
  prevented the default.

## Vocabulary

| Term | Means here |
|---|---|
| **entry** / **record** | a settled row (`kind` set), from `GET …/entries` (013) |
| **settled edit** | `PATCH /api/messages/{id}` on a settled row (D1) |
| **actions group** | the entry header's edit / copy / re-open controls, revealed together (D6) |
| **reveal** | the actions group's visible state — hovered, focus within, or a no-hover device (D6) |
| **plain text** | a settled text with CommonMark syntax removed by `002`'s rules (D8) |
| **enormous paste** | a non-blank pasted text whose estimate exceeds 32,000 tokens — over 128,000 characters (D3) |
| **bump** | setting `sessions.last_used_at` and `updated_at` to the operation's instant (012 D3, D2) |
| **blank** | empty or whitespace only (JavaScript `trim`, 013 D16) |
