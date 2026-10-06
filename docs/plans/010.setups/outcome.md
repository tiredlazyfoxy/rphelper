# Feature 010 — Setups · outcome

Intended changes to `docs/architecture/` once this feature ships, for the architect to
apply at finalization. Grouped by target file. Decisions referenced as D-n are in this
folder's `context.md`; "009 Dn" are in `docs/plans/009.characters/context.md`.

## `docs/architecture/data-model.md`

| Section | Intended change | Reason |
|---|---|---|
| `setups` | Add an **"As built by FEAT-007 (plan 010)"** block: the eight columns exactly as listed; `user_id` FK `users.id` and `character_id` FK `characters.id`, both NOT NULL, **no `ON DELETE`**; `description` Text NOT NULL with no server default (`""` when omitted, never stripped); one non-unique index on **`(user_id, character_id)`**; an existing database picks the table up through the drift page's **Create** (D7). `character_id` is fixed for a setup's life: no route moves a setup between characters (D5). | Records the as-built shape and the index choice, and makes the immutability of the parent explicit for `011`'s `sessions.setup_id`. |
| "`translations`, `messages`, `memos` and the archive rule" | Record that setups follow characters' as-built archive semantics (idempotent archive keeping the original `archived_at`; no-op writes nothing; editing an archived setup allowed), and that an archived **character** still lists and accepts new setups (D5, D9). | `011` should match; the archived-parent posture is not obvious. |
| Vector tables — the `session_vec` fan-out paragraph | Forward note: `services/setups.py`'s `update_setup` is the setup-text write the `session_vec` fan-out will hook (a `description` change is a fan-out invalidation input, as the paragraph and `search-and-retrieval.md` already state). **The feature that creates `session_vec`** adds the invalidation there. 010 has no vector write. | The write path now exists without its hook; nothing else will point at it. Same note 009 left for `update_character`. |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| New subsection beside the characters route surface — **"The setups route surface — FEAT-007"** | Add the route table from `context.md`'s Wire contract: `GET` / `POST /api/characters/{character_id}/setups` (with `include_archived`), `GET` / `PATCH /api/setups/{setup_id}`, `POST …/archive`, `POST …/restore`, one router with router-level `require_user`, **no `DELETE` (405)**. Record: nested collection + flat single-resource paths (D5); a missing/foreign parent answers `character_not_found`; listing and creating under an archived character are allowed; `character_id` is not patchable and unknown keys are ignored (D5, D8); the wrapped list `{ setups: [...] }`; order `created_at DESC, id DESC` (D10). | Second roleplayer-owned route family and the first child collection; `011` (sessions under a character) copies its shape. |
| "Routers versus services" | Record that a service verifies a parent with **its own owner-scoped select in its own transaction** and never calls another service's operation (D6). | A service owns its transaction; a cross-service call would nest `begin()` or split one decision across two transactions. `011` / `015` will face the same choice. |
| "The error model" — the named-errors table | Add `setup_not_found`: raised when a setup route addresses an id that does not exist **or belongs to another user**; `detail` empty; FEAT-007, UC-020, UC-068. | New code. |
| "The per-code status record" | Add `setup_not_found` → **404**, indistinguishable for "nobody's" and "another user's" (R5, D8). Introduced by plan 010. | The status record is per code. |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Error codes | Add `setup_not_found` (404). | The dense index lists every code. |
| Routes / paths (wherever the route index sits) | Add `/api/characters/{id}/setups` and `/api/setups/{id}` (plus `/archive`, `/restore`). | Same. |

## `docs/architecture/domain-rules.md`

| Section | Intended change | Reason |
|---|---|---|
| R6 | Add: **archiving a setup that sessions reference is always silent and always succeeds** — no warning, no refusal, no reference count. Archive does not cascade, so referencing sessions keep their `setup_id` and keep working (D3). Keeping counts out of the UI also keeps R5's reverse-lookup pattern off every surface. | Closes `brief.md`'s open question. R6 said nothing about referenced rows. |
| R2 | Add one sentence: as built (plan 010), nothing creates a setup except an explicit create; creating a character writes no setup row (tested). | Records that the no-sentinel consequence holds as built. |

## `docs/architecture/frontend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| "Routing inside the `app` entry" — the archive-toggle `_TBD:` | **Settle it for FEAT-007**: a **"Show archived setups" switch in the character screen's Setups section header**, not persisted; archived setups appear dimmed with an "Archived" badge and offer Restore (D4). With 009's settlement for FEAT-006, leave the `_TBD:` open **for sessions only** (`011`). | The `_TBD:` asked FEAT-007's plan to place it. |
| "Routing inside the `app` entry" — "Setups have no route" | Record that this holds as built: setups live in a section of `/characters/:id` (D1). | Confirms the line with its realisation. |
| "Where a store's file lives" / "State — MobX 6" | Record the section-owned state precedent: a section of a page with its own list creates its own state with `useState`, keyed by the parent id, when nothing outside the section reads it (D11). Contrast 009's workspace-level `CharactersState`, shared by tree and screen. | Tells `011` / `015` when a list needs workspace state and when it does not. |

## `docs/architecture/workspace-shell.md`

| Section | Intended change | Reason |
|---|---|---|
| "The character page" | Record what 010 adds: a **"Setups" section** between the persona block and the Sessions heading (existing mode only): "New setup" (labelled, `IconPlus`), "Show archived setups" switch, a table of setups with a per-row overflow menu (Edit / Archive / Restore), create and edit in a modal, the neutral empty line "No setups yet." (D1, D2, D4, D13). `018` rebuilds it into the page's setups block. | Partial delivery of the page's setups block. |

## `docs/architecture/ui-conventions.md`

| Section | Intended change | Reason |
|---|---|---|
| Icon table | Record the as-built uses for FEAT-007: "New setup" as a **labelled button** with `IconPlus`; Edit (`IconEdit`), Archive / Restore (`IconArchive` / `IconArchiveOff`) as **labelled items of a table row's overflow menu** (`IconDots` trigger "Actions for <name>") (D2, D13). | Labels are the accessible names tests bind to. |
| "Create and edit are always a `Modal`" | Add the setup modal as an `app`-entry worked example: conditionally mounted, fresh draft per open, flags in component-local `useState`, server failure inside the modal, apply-the-row then close (D2). | First modal in the `app` entry. |
| "Loading, errors and empty states" — Empty state | Record the first empty-state line: "No setups yet.", deliberately not an invitation, because the object is optional (R2, D13). | The doc welcomes empty-state improvements; this one records the "don't nag about optional objects" constraint. |
| "Async feedback" | Add the Setups section and modal as examples of failures with a place of their own; 010 adds no `notifyFailure` call site (D12). | Consistency record. |
| The confirm convention — "Deliberately NOT confirmed" | Make archiving a setup explicit (009 recorded it "by extension"). | Reads as decided. |

## Forward notes (not architecture changes; for the owning plans)

- **`011` (sessions):** the session-start setup picker reads
  `GET /api/characters/{character_id}/setups` (working list by default). **US-023.AC-2 is
  delivered there**, not here, and FEAT-007 is **partially delivered** until then. An
  **archived setup is not offered** when starting a new session, but an existing session
  whose setup was archived **keeps showing its label** (D3; R6 does not cascade).
  `sessions.setup_id` must stay nullable with no sentinel (R2). `011` also adds the setup
  label on a session row in the tree, and owns UC-021, UC-022, US-024, US-025.
- **`018` (character page):** rebuilds 010's Setups section into the character page's
  setups block, and may revisit the table-plus-menu layout and the section-local state.
- **`015` (notes):** setup-level notes hang off `setups.id`; the setup's parent is fixed
  (D5), which the memo scope check can rely on.
- **The feature that creates `session_vec`:** hook the invalidation fan-out into
  `update_setup` (a `description` change), per `search-and-retrieval.md`.
- **US-023.AC-2 is not delivered.** No stand-in test was written.

## Observations

- Step 006: the Setups section is the repo's first labelled landmark — a plain
  `<section aria-labelledby={headingId}>` whose heading carries the id, where the existing
  convention is `aria-label` on a Mantine `Box` (`CharacterTree`'s `aria-label="Characters"`).
  Possible impact: add to `docs/architecture/ui-conventions.md` as the rule for naming a
  region on a screen that holds several blocks (`018` will need several at once).
- Step 006: two as-built firsts inside the row table — `Menu.Item` with a `leftSection` icon
  at the "inline" metrics (`size={16} stroke={1.5}`), and a `Table` with **no** `Table.Thead`
  (one data column plus the `w={60}` action cell, so a header row would only add noise and an
  extra `row`). Possible impact: record both under `ui-conventions.md` "Tables", so later
  list sections do not re-decide them.

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B1 (the backend spine — `session-stream.md`, `transfer.md`, `backend-structure.md`, `data-model.md`, `domain-rules.md`) and B3 (the frontend layer — `workspace-shell.md`, `frontend-structure.md`, `ui-conventions.md`, `forms-and-lists.md`).
Rejected items: none
Notes: Both `## Observations` applied. The Setups section is folded into 018's as-built page order rather than written as a delivery stage.
