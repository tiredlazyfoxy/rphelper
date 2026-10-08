# Feature 033 — character-page-tabs — outcome

Intended documentation changes once the feature ships. Grouped by target file.
Decision ids D1–D10 are this plan's (`context.md`).

## For `/product-spec` (not the architect — `docs/product/` is read-only here)

- **`docs/product/stories/FEAT-008.rp-sessions.md`, US-117.AC-4** — amend: the
  character page's composer still offers **no kind switch**, but **does** offer an
  optional setup choice, defaulting to none. Reason: D8/D10, user-accepted
  conflict.
- **`docs/product/use-cases/FEAT-008.rp-sessions.md`, UC-080 postcondition**
  ("…the session starts with none") — amend: the session starts with the setup
  chosen in the composer, or with none when none is chosen. Reason: D8/D10.
- **Review UC-023 / UC-021 wording** — the message-less "Start session" control is
  removed (D9); a session now starts only by writing the first message on the
  character page. Confirm neither use case requires a start without a message.
- **US-096 ("in one place")** — the page is now tabbed; confirm "one place" still
  reads as "one page" rather than "one scroll".

## `docs/architecture/workspace-shell.md`

- **§ "The character page" — "The body's order, as built" (018 D12)** — replace
  the single-scroll order with the tabbed structure: header (name, Archived badge,
  icon-only Archive/Restore and Export) above a Mantine `Tabs` with Sessions
  (default) · Main info · Configuration · Notes · Setups; active tab is
  component-local, not in the URL, not persisted; `keepMounted` so every section
  loads once on page open. Reason: D1–D3, D2.
- **Same section — notes "grid"** — the character page's notes now use the shared
  group's **list** layout with an opt-in header '+' and an inline draft saved by an
  explicit Save icon (Cancel discards, no blur-save in that mode); the wall and
  Settings keep the labelled "New note" + blur-save. The same-components rule
  (018 D8) still holds — one group component, an opt-in prop. Reason: D6.
- **§ "Setups, configuration and sessions" — Setups bullet** — "New setup" is now
  an icon-only '+' in the section header; **create is an inline form** at the top
  of the list with Save/Cancel icons; edit stays in the modal. Reason: D7.
- **Same section — Sessions bullet** — no inline start control; "Import session"
  is an icon button in the list header beside the archived switch; the Sessions
  tab reads composer → divider → list. Reason: D8, D9.
- **§ "Starting a session — the named exception to the modal rule"** — retire
  the inline start control (011 D1). A session is started only by writing in the
  page composer, optionally with a setup. Reason: D9.
- **§ "The composer, and starting a session by writing"** — reverse "carries
  neither the kind switch nor a setup choice": the composer carries an optional
  Setup select (default "No setup", working setups only, reloaded on dropdown
  open, non-blocking load failure line) and sends `setup_id` with the opening
  message in the one create request; still no kind switch. The heading reads
  "New session". Reason: D8, D10.
- **§ "The draft page" — "Export sits beside Archive / Restore"** — now icon-only
  `IconButton`s in the page header (still absent on the draft page); Export is
  disabled while in flight. Reason: D3.
- **Persona** — the Main info tab's persona editor uses a larger minimum height.
  Reason: D4.

## `docs/architecture/forms-and-lists.md`

- **§ "The named exceptions"** — remove the "Starting a session" row (011 D1
  retired). Add **"Inline setup create"** on the character page's Setups tab:
  conditionally mounted inline form, fresh `SetupDraft` per open, Save/Cancel
  icons, failure inline — the draft-lifetime half of the modal convention kept,
  the dialog dropped (user decision). Update "Every create … is still a modal"
  accordingly. Reason: D7, D9.
- **§ "Loading, errors and empty states" — "No sessions yet." rationale** — it
  cites "the start control beside it", which no longer exists; the composer sits
  above the list instead. Reason: D8, D9.
- **Optional:** record the notes' header-add draft (explicit Save/Cancel instead
  of blur-save) as an opt-in variant of the in-place edit exception. Reason: D6.

## `docs/architecture/ui-conventions.md`

- **Notes on `IconPlus`** ("a labelled button wherever it creates a child of the
  thing on screen — New setup, Start session, New note, Import session") — revise:
  on the character page "New note" and "New setup" are icon-only '+' in their
  section headers, "Import session" is icon-only `IconUpload`, and "Start session"
  no longer exists; the wall and Settings keep the labelled "New note". Reason:
  D6–D9.
- **Notes on `IconArchive` / `IconArchiveOff`** ("left sections of labelled
  buttons on the character page") — now icon-only header `IconButton`s, as is
  Export's `IconDownload`. Reason: D3.
- **Icon table** — add the inline-draft Save (`IconDeviceFloppy`, "Save new note"
  / "Save setup") and Cancel (`IconX`, "Cancel new note" / "Cancel new setup").
  Reason: D6, D7.
- **`IconButton` busy state** — record that an in-flight icon action is expressed
  as `disabled` (Export, Import session); the props type was not widened with
  `loading`. Reason: D3, D8.
- **Async-feedback worked examples** — the Sessions-section row's
  "Could not load setups to choose from." moves to the page composer; add the
  inline setup create form (failure inline). Reason: D7, D8.

## `docs/architecture/frontend-structure.md`

- **§ Routing — `/characters/:id`** — the page is tabbed; the active tab is
  component state, so every link to `/characters/<id>` (search hits included)
  lands on Sessions. Reason: D1.
- **Routing — "`/characters/:id` also starts sessions" (018 D5)** — the
  start-with-message call now carries an optional `setup_id`; the section's
  message-less `startSession` call has no caller. Reason: D8, D9.
- **§ Markdown — "One editor wrapper"** — `MarkdownEditor` gains an optional
  minimum-height input (first caller: the persona). Reason: D4.
- **Bundle/components** — first use of Mantine `Tabs`, with `keepMounted`
  default kept deliberately (every section loads once on open). Reason: D1, D2.

## `docs/architecture/quick-reference.md`

- **Decision "Whether the character page's composer carries the kind switch or a
  setup choice → Neither"** — reverse to: kind switch **no**; setup choice
  **yes**, optional, default none. Reason: D8, D10.
- Index the retirement of the inline start control (011 D1) and the new inline
  setup create exception. Reason: D7, D9.

## `docs/architecture/session-stream.md`

- **Create-and-seed** — no behaviour change; if the doc states that the
  character page sends only the opening message, note that it may now send
  `setup_id` with it. Reason: D8.
