# Feature 011 — RP sessions · outcome

Intended changes to `docs/architecture/` once this feature ships, for the architect to
apply at finalization. Grouped by target file. Decisions referenced as D-n are in this
folder's `context.md`; "009 Dn" / "010 Dn" are in those plans' `context.md`.

## `docs/architecture/data-model.md`

| Section | Intended change | Reason |
|---|---|---|
| `sessions` | Add an **"As built by FEAT-008 (plan 011)"** block. The column list is delivered **in parts**: 011 declares `id`, `user_id` (FK `users.id`), `character_id` (FK `characters.id`), `setup_id` (FK `setups.id`, **nullable, no server default, no sentinel**), `last_used_at`, `archived_at` (nullable), `created_at`, `updated_at`; no FK has `ON DELETE`; one non-unique index on **`(user_id, character_id)`**, none on `setup_id`. **Deferred:** `title`, `partner_label` (no requirement sets them; the feature that lets the roleplayer label a session adds them, D4), and `rp_language`, `preferred_language`, `model_ref`, `system_prompt`, `tools` (`017`). Existing databases pick up the table through **Create**, later columns through **Sync** (D8). | The doc lists fourteen columns as one shape; without this a reader of the 011 registry sees six missing columns as drift. |
| `sessions` — `last_used_at` | Record the as-built rule: set at creation (= `created_at`); **bumped only by content writes** (append, settle, compose — from `012` on); **never** by opening/reading, archive or restore. There is no resume/touch route; resuming is a read (D3). Until `012`, last-use order equals creation order. | Closes brief open question 1; the doc said what the column drives, not what moves it. |
| `sessions` — `title` / `partner_label` | Record that neither is declared in 011 and why (D4); a session is labelled in the UI by its start time (`created_at`, `YYYY-MM-DD HH:MM` local). | Closes brief open question 2. |
| `sessions` — the `model_ref` `_TBD:` on encoding | Re-point the owner: FEAT-008's plan (011) does **not** write `model_ref`; the encoding decision moves to `017` (FEAT-013's plan) with the column. | The `_TBD:` named "FEAT-008's / FEAT-013's plans"; only one of them now can. |
| `sessions` — the read shape | Record that every session read carries `setup_name`, the referenced setup's **current** name by an owner-scoped LEFT JOIN, shown **even when the setup is archived** (D10, 010 D3). | US-088's label without a second request; a rename relabels sessions with no fan-out write. |
| FTS5 tables — `session_fts` | Note that `session_fts`'s indexed columns (`title`, `partner_label`) do not exist yet; FEAT-017's plan must either wait for the feature that adds them or choose other text (D4). | The declaration in the doc cannot be created against the 011 registry. |
| "… and the archive rule" | Record that sessions follow characters' and setups' as-built semantics (idempotent archive keeping the original `archived_at`; no-op writes nothing; a state change bumps `updated_at` and **not** `last_used_at`), and that archiving a session's character or setup leaves the session untouched and startable-under / labelled respectively (D2, D10, D13). | `012`+ must keep `last_used_at` out of archive. |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| New subsection beside the characters / setups route surfaces — **"The sessions route surface — FEAT-008"** | Add `context.md`'s Wire contract table: `GET /api/sessions`, `GET` / `POST /api/characters/{character_id}/sessions` (both lists with `include_archived`), `GET /api/sessions/{session_id}`, `POST …/archive`, `POST …/restore`; one router, router-level `require_user`, registered after setups; **no `PATCH`, no `DELETE` (405)**; wrapped lists `{ sessions: [...] }`; order `last_used_at DESC, id DESC`; `Session` carries `setup_name` (D9, D10, D14). | Third roleplayer-owned route family. |
| The stream route table — the `POST /api/characters/{character_id}/sessions` row and its two bullets ("Starting a session by writing…", "It is character-addressed…") | Amend: **011 ships this route without an opening message** — body omitted, `{}`, or `{ setup_id: string \| null }`, answering 201 with the session alone; a supplied `setup_id` must be the caller's setup under that character (404 `setup_not_found`) and working (409 `setup_archived`); an archived character is allowed. **`018` extends the same route and transaction** with the optional opening message (UC-080) and the seeded zone row in the response. **No `model_ref` capture yet**: the "resolve and capture `model_ref`" step lands with `017`. The bullet's "created with `setup_id` NULL" stays true for the UC-080 path. | The row describes 018's form; 011's form and the staged capture must be visible. |
| Same bullets — the `_TBD:` "whether that first message should also draw an assistant reply" | Note for `018` and the architect: **US-117.AC-3 now answers it** ("the assistant answers that message as it would any other discussion message"), so the route's media type question is live for `018`. 011 does not touch it. | A product answer has landed against an architecture `_TBD:`. |
| "Routers versus services" | Add `services/sessions.py` as the second service verifying a parent (and a chosen child of that parent) with its own owner-scoped selects in one transaction, importing no other service (D11, 010 D6). Record the naming rule: RP-session names avoid `services/auth.py`'s login-session vocabulary (`RpSession`, `start_session`, …). | The collision risk is permanent; the next contributor will meet both modules. |
| "The error model" — the named-errors table | Add `session_not_found` (a session route addresses an id that does not exist or belongs to another user; `detail` empty; FEAT-008, UC-024, UC-025) and `setup_archived` (a session start names the caller's archived setup; `detail` empty; FEAT-007, UC-021). | New codes. |
| "The per-code status record" | Add `session_not_found` → **404** (indistinguishable for nobody's / another user's, R5) and `setup_archived` → **409** (well formed, owned, state conflicts — as `username_taken`; not 404, the setup exists for the caller; not 422, no field is malformed) (D12). Introduced by plan 011. | Per-code record. |

## `docs/architecture/domain-rules.md`

| Section | Intended change | Reason |
|---|---|---|
| R2 | Add: as built (plan 011), a session starts with `setup_id` NULL unless one of the caller's **working** setups under that character is chosen; the start UI defaults to "No setup" and starts with an empty or failed setup list; nothing creates a setup or a sentinel at session start (tested). | Records the consequence "no flow may require choosing a setup" as built. |
| R4 — "The model is captured at session CREATION" and its `_TBD:` | Add a staging note: **sessions created by plan 011 carry no `model_ref`** (the column does not exist until `017`). `017` must decide what pre-existing sessions get (a backfill at its rollout, or NULL until the first successful resolution); that choice interacts with the open `_TBD:` on "no model enabled at creation". 011 decides nothing. | Otherwise `017` inherits rows that silently violate "captured at creation". |
| R6 | Add: as built for sessions (plan 011), both lists take `include_archived=true`, a by-id read answers archived rows whatever the character's state, archive/restore are idempotent and never move `last_used_at`; archived sessions surface only in the character page's Sessions section, never in the tree (D5, D13). | Completes R6's as-built record across all three entities. |

## `docs/architecture/frontend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| "Routing inside the `app` entry" — the archive-toggle `_TBD:` | **Close it entirely.** Sessions: a **"Show archived sessions"** switch in the character page's Sessions section header, not persisted; archived sessions shown dimmed with an "Archived" badge and a Restore row action; the tree never shows archived sessions; `/sessions/:id` opens an archived session directly with an "Archived" badge and no controls (D5). With 009's (characters) and 010's (setups) settlements, no part remains open. | The `_TBD:` asked FEAT-008's plan to place it. |
| "Routing inside the `app` entry" — "`/characters/:id` also starts sessions" | Record the interim: until `018`, sessions start from the Sessions section's inline **Setup** select + **Start session** (one POST, no message), navigating (push) to `/sessions/<id>` with the id as received; `018`'s composer later posts the opening message to the same route (D1, D2). | The paragraph describes 018's composer only. |
| "Routing inside the `app` entry" — `/sessions/:id` | Record what 011 renders there: the session's own screen (header with the character link, start-time label, setup label, Archived badge; "No entries yet."), keyed by id, read by `GET /api/sessions/{id}`; tree \| stream \| wall arrive with `012`–`016` (D17). | The route list describes the finished screen. |
| "State — MobX 6" / "Where a store's file lives" | Record the second workspace-level state, **`SessionsState`** (working sessions for the tree, created in `App`, passed as props), beside the section-owned **`SessionsSectionState`**, and the rule that a section mutation applies the returned row to **both** (effects take the workspace state as a parameter, never hold it as a field) (D15). | Confirms 010's "section state vs workspace state" guidance with a case that needs both. |
| A new short note under "Ids are strings" (or "State") | Record that client-side ordering of sessions and of characters-by-use compares fixed-width `last_used_at` text only, never ids (D6, D15). | The first client-side sort in the app entry; ids are the tempting key. |
| Persistence (cross-reference to `workspace-shell.md`) | Record the second localStorage key, **`rphelper.tree-collapsed`** (JSON array of collapsed character ids), in its own pure module `app/treeCollapse.ts`, deliberately **not** a field of `rphelper.workspace-layout` because that reader drops unknown keys (D7). | Two keys on one origin need a written reason. |

## `docs/architecture/workspace-shell.md`

| Section | Intended change | Reason |
|---|---|---|
| "The three columns" | Record the tree's session level as built: characters ordered by **newest session use** (max `last_used_at` of their working sessions, then sessionless characters in created order), derived client-side; per-character chevron (`IconChevronDown`, rotated `-90°` collapsed; **absent** for a character with no sessions), expanded by default, collapse persisted; session rows are links labelled with the start time and the setup name as dimmed text (nothing without a setup), `aria-current` on the open session; working sessions only (D6, D7, D16). Replaces 009 D10's interim order. | The doc describes the finished tree; this records the delivered second level. |
| "Layout persistence" | Add the second record: `rphelper.tree-collapsed`, same posture (total read, best-effort write, pure DOM-free module), separate key and why (D7). | The section says "one localStorage record". |
| "The character page" | Record what 011 adds: the **Sessions section** (inline Setup select defaulting to "No setup" + "Start session", "Show archived sessions" switch, table of sessions with a per-row Archive/Restore menu, "No sessions yet.") replacing 009's empty heading; `018` may rebuild it (D1, D5). | Partial delivery of the page's sessions block. |
| "The composer, and how a session starts here" — its `_TBD:` | Leave it `018`'s, with two notes: in 011 the **setup choice lives in the Sessions section's inline start**, not in a composer; and **US-117.AC-4 now states** the composer offers neither the kind switch nor a setup choice, which answers the `_TBD:` for `018` to apply. | A product answer has landed; the architect may close it now or at `018`. |
| "Geometry" — tree column row | Optional: note the expanded tree row now holds a start-time label (`YYYY-MM-DD HH:MM`) plus a setup label rather than a session title. | The 252px reasoning cites "a session title". |

## `docs/architecture/ui-conventions.md`

| Section | Intended change | Reason |
|---|---|---|
| Icon table | Record the as-built uses for FEAT-008: "Start session" as a **labelled button** with `IconPlus`; Archive / Restore (`IconArchive` / `IconArchiveOff`) as labelled items of a session row's overflow menu (`IconDots` trigger "Actions for <start-time label>"); the tree chevron as `IconChevronDown` rotated `-90°` via a local icon wrapper, labelled "Collapse <name>" / "Expand <name>", `sizeVariant` "chevron" (D5, D7). | Labels are the accessible names tests bind to. |
| "Create and edit are always a `Modal`" | Add starting a session as a **named exception**: a one-choice inline control (the Setup select + Start session) in the character page's Sessions section, not a form and not a modal (user decision, D1). Amend `workspace-shell.md`'s sentence "the modal rule continues to govern … session creation" to match. | Otherwise the doc says session creation is a modal. |
| "Loading, errors and empty states" — Empty state | Add "No sessions yet." as the second neutral empty line (D18). | Consistency with 010's record. |
| "Async feedback" | Add the Sessions section, the tree's sessions failure and the session screen as failures with a place of their own, including the non-blocking "Could not load setups to choose from."; 011 adds no `notifyFailure` call site (D18). | Consistency record. |
| The confirm convention — "Deliberately NOT confirmed" | Make archiving a session explicit (009 recorded it "by extension"). | Reads as decided. |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Error codes | Add `session_not_found` (404) and `setup_archived` (409). | Dense index. |
| Routes / paths | Add `/api/sessions`, `/api/sessions/{id}` (+ `/archive`, `/restore`), `/api/characters/{id}/sessions` (GET, POST). | Same. |
| Persistence keys (wherever `rphelper.workspace-layout` is listed) | Add `rphelper.tree-collapsed`. | Same. |

## Forward notes (not architecture changes; for the owning plans)

- **`012` / `013` (entries, zone, settle, compose):** every content write — append to the
  zone, file a partner block, settle, compose — **bumps `sessions.last_used_at`** in its
  own transaction (D3); opening and reading must not. The frontend's `applySession`
  already re-positions a row whose `last_used_at` moved. **US-027.AC-3's "every entry and
  settled answer intact"** half is delivered there, not here (no stand-in test was
  written). US-024.AC-2 is `012` / `021`'s.
- **`015` (notes):** session-level notes hang off `sessions.id`; a session's character is
  fixed and its setup is fixed after start (no route changes either), which the memo scope
  check can rely on. US-025.AC-2 is `015` / `026` / `027`'s.
- **`017` (configuration):** adds `rp_language`, `preferred_language`, `model_ref`,
  `system_prompt`, `tools` to `sessions` (Sync on existing databases), fixes `model_ref`'s
  encoding, puts the capture into `start_session`'s transaction, and **decides what
  sessions created before `017` get** for `model_ref` (backfill or NULL until first
  resolution).
- **`018` (character page):** extends `POST /api/characters/{id}/sessions` with the
  optional opening message in the same transaction (UC-080, US-117), and may rebuild 011's
  Sessions section into the page's sessions block. US-117.AC-3 / AC-4 answer the two
  `_TBD:`s noted above.
- **FEAT-017's plan (my-search):** `session_fts` needs `title` / `partner_label`, which do
  not exist; a session is labelled by its start time until a feature adds a title.
- **US-021.AC-2** (`020`) and **US-117 / UC-080** (`018`) are not delivered here.
- **FEAT-007** becomes delivered for US-023.AC-2, US-024.AC-1, US-024.AC-3, US-025.AC-1
  with this plan; US-024.AC-2 and US-025.AC-2 remain. **FEAT-008** is partially delivered
  (UC-080 / US-117 remain, and US-027.AC-3's entries half). **FEAT-020** gains UC-069 /
  US-088 / US-089.

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B1 (the backend spine — `session-stream.md`, `transfer.md`, `backend-structure.md`, `data-model.md`, `domain-rules.md`) and B3 (the frontend layer — `workspace-shell.md`, `frontend-structure.md`, `ui-conventions.md`, `forms-and-lists.md`).
Rejected items: none
Notes: The session-creation named exception to the modal rule is recorded, and `workspace-shell.md`'s sentence saying the modal rule governs session creation is amended to match. `US-145` now carries the start-time label against the Geometry row's "session title" reasoning.

