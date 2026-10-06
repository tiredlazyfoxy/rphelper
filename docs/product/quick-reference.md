<!-- product-spec:start -->
# Quick reference

## What this file is

The sole canonical id registry for `docs/product/`: every `ACT-###`,
`FEAT-###`, `UC-###`, `US-###` (and its `AC-#`s), one-liner, status, owning
feature/actor. Exempt from the ~400-line budget.

Where this file and a feature/use-case/story file disagree, **the other file
wins** — this is a derived index, not a source. Ids are permanent: never
renumbered, never reused; gaps stay if a number is ever withdrawn or skipped.

## Doc map

| File | Holds |
|---|---|
| `vision.md` | Problem, who has it, what happens without it, 3 success signals, scope & non-goals |
| `actors.md` | ACT-001..ACT-004 blocks, plus 2 named non-actors |
| `features.md` | FEAT-001..FEAT-020 blocks + `## Relationships` (dependency graph, overlaps, boundary, conflicts). Never a registry, never splits. |
| `use-cases/<FEAT-###>.<slug>.md` | UC-001..UC-088, one file per feature |
| `stories/<FEAT-###>.<slug>.md` | US-001..US-140 plus US-141..US-147, with `US-###.AC-#` criteria, one file per feature |
| `glossary.md` | Domain terms, one line each |
| `quick-reference.md` (this file) | The id registry |

Feature → filename slug (use-cases and stories share the slug):

| FEAT | Slug |
|---|---|
| FEAT-001 | `first-run-bootstrap` |
| FEAT-002 | `authentication-session` |
| FEAT-003 | `user-management` |
| FEAT-004 | `llm-server-connections` |
| FEAT-005 | `database-consistency` |
| FEAT-006 | `characters` |
| FEAT-007 | `setups` |
| FEAT-008 | `rp-sessions` |
| FEAT-009 | `session-entries` |
| FEAT-010 | `compose-discussion` |
| FEAT-011 | `partner-translation` |
| FEAT-012 | `memos` |
| FEAT-013 | `session-configuration` |
| FEAT-014 | `memo-search-tool` |
| FEAT-015 | `session-search-tool` |
| FEAT-016 | `web-search-tool` |
| FEAT-017 | `my-search` |
| FEAT-018 | `export-import` |
| FEAT-019 | `privacy-isolation` |
| FEAT-020 | `workspace-shell` |

## Actors

| ACT | Name | One-liner | Touches (FEAT) |
|---|---|---|---|
| ACT-001 | Administrator | Stands the instance up and keeps it running; can never read another user's content. | FEAT-002, FEAT-003, FEAT-004, FEAT-005, FEAT-018, FEAT-019, FEAT-020 (admin entry point only) |
| ACT-002 | Roleplayer | Composes their own RP replies in the RP language with assistance; owns every character, setup, session and memo. | FEAT-002, FEAT-006, FEAT-007, FEAT-008, FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013, FEAT-014, FEAT-015, FEAT-016, FEAT-017, FEAT-018, FEAT-019, FEAT-020 |
| ACT-003 | First-run operator | Faces an unconfigured instance with no database and no users. | FEAT-001 |
| ACT-004 | Composition assistant | Non-human. Helps compose the roleplayer's own answer inside a compose discussion. | FEAT-010, FEAT-012, FEAT-014, FEAT-015, FEAT-016 |

**Non-actors** (named explicitly in `actors.md` so nobody adds them later):
- **The RP partner** — never touches the system; their words arrive only as pasted text.
- **The external RP platform** (Discord, RP sites) — no integration exists; the boundary is the clipboard.

## Features

All 20 are `Priority: must`. Sequencing comes from the dependency graph below,
not from priority. 14 are `delivered` (FEAT-002, 003, 004, 006, 007, 011, 012,
013, 014, 015, 016, 018, 019, 020) and 6 are `partially delivered` (FEAT-001,
005, 008, 009, 010, 017). No FEAT is `proposed` any more — see the Status
column below and each block's `**Delivered:**`/`**Remaining:**` lines in
`features.md`. FEAT-009, FEAT-010 and FEAT-017 are `partially delivered`
because shipped behaviour does not satisfy a named criterion (recorded in
`docs/plans/defects.md`); the lifecycle has no "delivered but defective"
value.

| FEAT | Name | Actors | Realized by (UC) | Realized by (US) | Status |
|---|---|---|---|---|---|
| FEAT-001 | First-run bootstrap | ACT-003 | UC-001–003 | US-001–003 | partially delivered |
| FEAT-002 | Authentication & session | ACT-001, ACT-002 | UC-004–005 | US-004–007 | delivered |
| FEAT-003 | User management | ACT-001 | UC-006–009, UC-087 | US-008–011, US-140 | delivered |
| FEAT-004 | LLM server connections | ACT-001 | UC-010–013 | US-012–016 | delivered |
| FEAT-005 | Database consistency & management | ACT-001 | UC-014–016 | US-017–019 | partially delivered |
| FEAT-006 | Characters | ACT-002 | UC-017–019, UC-067 | US-020–022, US-086 | delivered |
| FEAT-007 | Setups | ACT-002 | UC-020–022, UC-068 | US-023–025, US-087 | delivered |
| FEAT-008 | RP sessions | ACT-002 | UC-023–026, UC-080 | US-026–029, US-117, US-145 | partially delivered |
| FEAT-009 | Session entries & the RP flow | ACT-002 | UC-027–031, UC-078, UC-081–082 | US-030–035, US-109–112, US-120–124 | partially delivered |
| FEAT-010 | Compose discussion | ACT-002, ACT-004 | UC-032–038, UC-079, UC-083–086 | US-036–044, US-113–116, US-125–135, US-146 | partially delivered |
| FEAT-011 | Partner-text translation | ACT-002 | UC-039–041 | US-045–048 | delivered |
| FEAT-012 | Memos | ACT-002, ACT-004 | UC-042–046, UC-075–076, UC-088 | US-049–057, US-098–104, US-119, US-141 | delivered |
| FEAT-013 | Session configuration & inheritance | ACT-002 | UC-047–050, UC-077 | US-058–062, US-105–108, US-139, US-142–144 | delivered |
| FEAT-014 | `memo_search` tool | ACT-002, ACT-004 | UC-051–052 | US-063–066 | delivered |
| FEAT-015 | `session_search` tool | ACT-002, ACT-004 | UC-053–054 | US-067–069, US-138 | delivered |
| FEAT-016 | `web_search` tool | ACT-002, ACT-004 | UC-055–057 | US-070–073 | delivered |
| FEAT-017 | My search | ACT-002 | UC-058–060 | US-074–076, US-118, US-137, US-147 | partially delivered |
| FEAT-018 | Export & import | ACT-001, ACT-002 | UC-061–064 | US-077–082, US-136 | delivered |
| FEAT-019 | Privacy & isolation | ACT-001, ACT-002 | UC-065–066 | US-083–085 | delivered |
| FEAT-020 | Workspace shell & navigation | ACT-002 (primary), ACT-001 (admin entry point only) | UC-069–074 | US-088–097 | delivered |

**Build order** (transcribed verbatim from `features.md`'s `## Relationships`):

`FEAT-001 → FEAT-002 → FEAT-003 → FEAT-019 → FEAT-004 → FEAT-005 → FEAT-006 →
FEAT-007 → FEAT-008 → FEAT-009 → FEAT-012 → FEAT-013 → FEAT-010 → FEAT-011 →
FEAT-014 → FEAT-015 → FEAT-016 → FEAT-017 → FEAT-018 → FEAT-020`

New edges: FEAT-020 depends on FEAT-002, FEAT-006, FEAT-008, FEAT-012,
FEAT-017. No cycles.

This order is the dependency graph's, not a priority ranking — every feature
above is `must`, so priority carries no sequencing information on its own.

## Use cases

UC-001..UC-088, grouped by owning feature, id order. One-liners are the use
case's own heading text, verbatim. Every UC below is `Status: delivered`
except the ones tagged inline: UC-002, UC-016 are `deferred`; UC-080 is
`partially delivered` (step 5 is the US-117.AC-3 defect, see
`docs/plans/defects.md`).

**FEAT-001**
- UC-001 — Create a new database with the first administrator · **Status:** delivered
- UC-002 — Bring up an instance from an existing export · **Status:** deferred → docs/plans/fast/003.bootstrap-from-export/
- UC-003 — Bootstrap is unavailable once the instance is configured · **Status:** delivered

**FEAT-002**
- UC-004 — Log in · **Status:** delivered
- UC-005 — Log out and session expiry · **Status:** delivered

**FEAT-003**
- UC-006 — Create an account · **Status:** delivered
- UC-007 — Disable and re-enable an account · **Status:** delivered
- UC-008 — Reset a user's password · **Status:** delivered
- UC-009 — List accounts without reaching any content · **Status:** delivered
- UC-087 — Change an account's role · **Status:** delivered

**FEAT-004**
- UC-010 — Register a server connection (llamaswap or OpenAI) · **Status:** delivered
- UC-011 — Test a connection · **Status:** delivered
- UC-012 — Enable and disable specific models · **Status:** delivered
- UC-013 — Designate the embedding server and model · **Status:** delivered

**FEAT-005**
- UC-014 — View a per-table drift report · **Status:** delivered
- UC-015 — Remediate drift · **Status:** delivered
- UC-016 — Rebuild the vector index · **Status:** deferred → docs/plans/fast/002.vector-index-rebuild/

**FEAT-006**
- UC-017 — Create a character
- UC-018 — Edit a character's persona
- UC-019 — List my characters
- UC-067 — Archive and restore a character

**FEAT-007**
- UC-020 — Create a setup under a character
- UC-021 — Start a session with a setup, or with none
- UC-022 — Reuse one setup across several sessions
- UC-068 — Archive and restore a setup

**FEAT-008**
- UC-023 — Start a session under a character
- UC-024 — Resume a session
- UC-025 — Archive and restore a session
- UC-026 — See sessions ordered by last use
- UC-080 — Start a session by writing the first message on a character's page · **Status:** partially delivered → docs/plans/defects.md

**FEAT-009**
- UC-027 — Add a partner entry by pasting
- UC-028 — Add my own answer entry directly
- UC-029 — Edit any entry at any time
- UC-030 — Copy a settled answer
- UC-031 — Add entries in any order (open the RP myself, or answer twice running)
- UC-078 — Edit a session entry where it sits in the stream
- UC-081 — Record a decision in the session
- UC-082 — Copy a settled turn for posting outside

**FEAT-010**
- UC-032 — Open a discussion on an answer
- UC-033 — Discuss in any language, the assistant mirrors each message
- UC-034 — The assistant produces a candidate reply in the RP language
- UC-035 — Promote, write or edit in the current zone and settle
- UC-036 — The discussion collapses on settling and stays readable
- UC-037 — Re-open a collapsed discussion while nothing follows it
- UC-038 — A settled discussion never reaches context again
- UC-079 — Follow a live discussion inline beneath the answer it belongs to
- UC-083 — Work in the current zone below the ruler
- UC-084 — Give the assistant a fast instruction inside a draft
- UC-085 — Stop model work in flight
- UC-086 — Abandon a current zone without settling

**FEAT-011**
- UC-039 — Flick a partner entry into my preferred language
- UC-040 — Flick back to the original
- UC-041 — The translation is cached after first use

**FEAT-012**
- UC-042 — Create a memo at any of the four levels
- UC-043 — Edit a memo in markdown with live preview
- UC-044 — Set a memo's state
- UC-045 — Forced memos reach the system prompt
- UC-046 — Resolve a session's memo chain, with or without a setup
- UC-075 — Change a note's forced and enabled state from the wall
- UC-076 — Reorder notes within a level
- UC-088 — Remove a note by emptying it · **Status:** delivered

**FEAT-013**
- UC-047 — Set user-level defaults
- UC-048 — Override at character level
- UC-049 — Override at session level
- UC-050 — Resolve the effective configuration for a session
- UC-077 — Choose the session's model from the stream's header

**FEAT-014**
- UC-051 — The assistant searches searchable memos across the session's chain
- UC-052 — Forced and disabled memos are excluded from results

**FEAT-015**
- UC-053 — The assistant finds past sessions under the same character by meaning
- UC-054 — Results never leave the character or the user

**FEAT-016**
- UC-055 — Look up a real-world fact
- UC-056 — Check an idiom or whether phrasing sounds natural
- UC-057 — The roleplayer asks directly for a lookup

**FEAT-017**
- UC-058 — Search everything of mine from any screen
- UC-059 — Read results grouped by kind
- UC-060 — Jump from a result to the session or entry

**FEAT-018**
- UC-061 — Export and import the whole database, opaque to the administrator
- UC-062 — Export and import my own user data with memos
- UC-063 — Export and import a character with its memos
- UC-064 — Export and import a single session with its own memos

**FEAT-019**
- UC-065 — Every listing, search and tool is scoped to the owning user
- UC-066 — Administrative surfaces expose no user content

**FEAT-020**
- UC-069 — Navigate characters and their sessions from the left column
- UC-070 — Collapse the left column to an icon rail and restore it
- UC-071 — Open the user menu and reach logout, settings, or the admin area
- UC-072 — Open, pin and dismiss the note wall beside the stream
- UC-073 — Work on a character's page — persona, notes, setups, settings, sessions
- UC-074 — Create a character from a draft page

Total: 88, UC-001..UC-088, no gaps.

## Stories

US-001..US-147, grouped by owning feature, id order. `ACs` is the count of
`US-###.AC-#` criteria on that story. One-liners are the story's own heading
text, verbatim. Every US below is `Status: delivered` except the ones tagged
inline: US-002, US-019 are `deferred`; US-112 (AC-1's widened half and AC-3),
US-115 (AC-1's streaming half), US-117 (AC-3) and US-147 (name matching folds
case ASCII-only) are `partially delivered` — each points at
`docs/plans/defects.md`.

**FEAT-001**
- US-001 — Fresh instance with a first admin (ACs: 2) · **Status:** delivered
- US-002 — Instance from an export (ACs: 2) · **Status:** deferred → docs/plans/fast/003.bootstrap-from-export/
- US-003 — Bootstrap refused once configured (ACs: 2) · **Status:** delivered

**FEAT-002**
- US-004 — Log in with correct credentials (ACs: 2) · **Status:** delivered
- US-005 — Rejected with wrong credentials (ACs: 2) · **Status:** delivered
- US-006 — A disabled account cannot log in (ACs: 3) · **Status:** delivered
- US-007 — Session ends, return to login (ACs: 2) · **Status:** delivered

**FEAT-003**
- US-008 — Admin creates an account (ACs: 2) · **Status:** delivered
- US-009 — Disabling ends that user's sessions (ACs: 2) · **Status:** delivered
- US-010 — Admin resets a password (ACs: 3) · **Status:** delivered
- US-011 — The account list shows no RP content (ACs: 2) · **Status:** delivered
- US-140 — Admin changes an account's role (ACs: 3) · **Status:** delivered

**FEAT-004**
- US-012 — Register a connection (ACs: 2) · **Status:** delivered
- US-013 — Test reports reachable or not (ACs: 2) · **Status:** delivered
- US-014 — Enabled models become selectable (ACs: 2) · **Status:** delivered
- US-015 — Designate the embedding model (ACs: 4) · **Status:** delivered
- US-016 — Disabling a model a session is configured to use (ACs: 3) · **Status:** delivered

**FEAT-005**
- US-017 — Drift report lists per-table status (ACs: 1) · **Status:** delivered
- US-018 — Remediation creates missing tables (ACs: 7) · **Status:** delivered
- US-019 — Vector index rebuild (ACs: 1) · **Status:** deferred → docs/plans/fast/002.vector-index-rebuild/

**FEAT-006**
- US-020 — Create a character (ACs: 2)
- US-021 — Edit the persona (ACs: 2)
- US-022 — The character list is mine alone (ACs: 1)
- US-086 — Archive a character and restore it (ACs: 3)

**FEAT-007**
- US-023 — Create a setup under a character (ACs: 2)
- US-024 — A session with no setup works end to end (ACs: 3)
- US-025 — Two sessions share one setup (ACs: 2)
- US-087 — Archive a setup and restore it (ACs: 2)

**FEAT-008**
- US-026 — Start a session (ACs: 1)
- US-027 — Archive then restore and resume (ACs: 3)
- US-028 — List ordered by last use (ACs: 1)
- US-029 — Sessions are mine alone (ACs: 1)
- US-117 — Writing the first message on a character's page creates the session (ACs: 4) · **Status:** partially delivered → docs/plans/defects.md
- US-145 — A session is identified by its start time, not a title (ACs: 2)

**FEAT-009**
- US-030 — Paste a partner block (ACs: 1)
- US-031 — Post an answer with no discussion (ACs: 1)
- US-032 — Edit a settled answer from weeks ago (ACs: 2)
- US-033 — Copy the settled answer in the RP language (ACs: 1)
- US-034 — Open a session with my own entry first (ACs: 1)
- US-035 — An enormous paste warns but is never refused (ACs: 2)
- US-109 — A partner block is edited in place and saved when focus leaves it; search reflects the new text (ACs: 2)
- US-110 — Any settled entry is edited in place and saved when focus leaves it; search reflects the new text (ACs: 2)
- US-111 — Editing any settled entry discards its cached translation (ACs: 3)
- US-112 — Whatever stops an embedding being produced, an edit still saves, and the roleplayer is told search coverage is incomplete (ACs: 3) · **Status:** partially delivered → docs/plans/defects.md
- US-120 — The current zone's kind switch has two positions with an alternating default (ACs: 3)
- US-121 — A pasted partner block files itself immediately; double parentheses in partner text get no special treatment (ACs: 2)
- US-122 — A settled decision sits in the record, reaches the assistant as context, and is found by session search (ACs: 2)
- US-123 — A settled decision offers no copy-out (ACs: 1)
- US-124 — Copying a settled turn yields plain text, not markdown (ACs: 2)

**FEAT-010**
- US-036 — The assistant mirrors the language of each message (ACs: 3)
- US-037 — Candidates are produced in the RP language (ACs: 1)
- US-038 — Promote a candidate and edit it before settling (ACs: 2)
- US-039 — Settling collapses the discussion (ACs: 1)
- US-040 — A collapsed discussion is readable (ACs: 3)
- US-041 — Re-open succeeds while it is last (ACs: 1)
- US-042 — Re-open is refused once another entry exists (ACs: 1)
- US-043 — Only the settled answer enters session context (ACs: 2)
- US-044 — The LLM going away mid-discussion loses none of my text (ACs: 5)
- US-113 — A discussion appears beneath its answer in the same stream, and collapses there when the answer is settled (ACs: 2)
- US-114 — The assistant's tool calls and thinking are visible while it works and are tucked away once it finishes (ACs: 3)
- US-115 — Any message in the current zone is edited in place, the assistant's included, not findable by session search, with no new reply (ACs: 3) · **Status:** partially delivered → docs/plans/defects.md
- US-116 — A collapsed discussion cannot be edited (ACs: 1)
- US-125 — A ruler separates the settled record above from exactly one current zone below (ACs: 1)
- US-126 — Settle takes the last message in the current zone, whoever wrote it (ACs: 2)
- US-127 — Settling files the entry, moves the ruler below it, and opens an empty current zone (ACs: 2)
- US-128 — A settled block is re-openable only while the current zone below it is still empty (ACs: 2)
- US-129 — A wholly-parenthesised message is out-of-character; settling one files a decision, not a turn (ACs: 1)
- US-130 — A double-parenthesised fragment inside a draft is an instruction that never appears in the settled turn (ACs: 2)
- US-131 — OOC messages are in the preferred language; the assistant answers OOC in kind, while candidates stay in the RP language (ACs: 3, AC-1 withdrawn)
- US-132 — Stopping keeps the partial text as a usable candidate (ACs: 2)
- US-133 — The stop reaches any model work (ACs: 2)
- US-134 — An empty zone is discarded; one holding text must be settled (ACs: 2)
- US-135 — Settling with no assistant answer settles the roleplayer's own text (ACs: 1)
- US-146 — The assistant's thinking never enters the settled record (ACs: 2)

**FEAT-011**
- US-045 — First flick translates into my preferred language (ACs: 1)
- US-046 — The second flick is instant (ACs: 1)
- US-047 — A translation never enters session context (ACs: 1)
- US-048 — A failed translation shows the original with a visible error and caches nothing (ACs: 2)

**FEAT-012**
- US-049 — Memo at user level (ACs: 1)
- US-050 — Memo at character level (ACs: 1)
- US-051 — Memo at setup level (ACs: 1)
- US-052 — Memo at session level (ACs: 1)
- US-053 — A new memo defaults to enabled and not forced (ACs: 1)
- US-054 — An enabled, forced memo appears in the system prompt (ACs: 1)
- US-055 — A disabled memo reaches the assistant by no path (ACs: 2)
- US-056 — Markdown with live preview (ACs: 1)
- US-057 — The memo chain resolves with no setup present (ACs: 1)
- US-098 — An enabled, forced note is in the system prompt for every request in that session (ACs: 1)
- US-099 — An enabled, not-forced note is reachable only by `memo_search` (ACs: 2)
- US-100 — A disabled note reaches the assistant by no path, whatever its forced flag says (ACs: 2)
- US-101 — Re-enabling a note restores the forced state it had when it was disabled (ACs: 2)
- US-102 — Forced notes enter the system prompt in the roleplayer's arranged order within their level (ACs: 2)
- US-103 — Levels keep a fixed order and a note cannot move between levels by dragging (ACs: 2)
- US-104 — A note's text is edited where it sits and is saved when focus leaves it (ACs: 1)
- US-119 — A note is one body of text, with no title, name or header field (ACs: 1)
- US-141 — Emptying a saved note removes it (ACs: 2)

**FEAT-013**
- US-058 — Set user defaults (ACs: 1)
- US-059 — Character-level model, system prompt and tool settings apply to its sessions (ACs: 2)
- US-060 — Session overrides character (ACs: 1)
- US-061 — RP language and preferred language are two independent settings inheriting user → session, skipping character (ACs: 3)
- US-062 — Tool switches follow the model/prompt chain (ACs: 2)
- US-105 — Choosing a model in the header sets the session's override and it persists (ACs: 2)
- US-106 — A character with no model configured resolves to the first enabled model (ACs: 1)
- US-107 — With no enabled model at all, the roleplayer cannot send a message and is told why (ACs: 2)
- US-108 — Model, system prompt and tool switches inherit character → session; the two languages inherit user → session (ACs: 2)
- US-139 — Configuring a character's model does not reach existing sessions (ACs: 2)
- US-142 — With no language configured anywhere, the instance falls back to English (ACs: 2)
- US-143 — A session is created even when no model is enabled (ACs: 2)
- US-144 — A session holding no chosen model says so when it refuses the send (ACs: 2)

**FEAT-014**
- US-063 — Returns searchable memos from all four levels (ACs: 1)
- US-064 — Never returns another user's memos (ACs: 1)
- US-065 — Works when the session has no setup (ACs: 1)
- US-066 — A tool failure does not end the discussion (ACs: 1)

**FEAT-015**
- US-067 — Finds a past session with a similar person or situation (ACs: 1)
- US-068 — Purely semantic — works with no setup and no partner field (ACs: 1)
- US-069 — Never crosses a character or user boundary (ACs: 2)
- US-138 — `session_search` matches entries plus the character's persona and setup (ACs: 2)

**FEAT-016**
- US-070 — Real-world fact lookup (ACs: 1)
- US-071 — Idiom / naturalness check (ACs: 1)
- US-072 — A direct user request to search (ACs: 1)
- US-073 — Disabled by the configuration chain (ACs: 2)

**FEAT-017**
- US-074 — Find a session by a half-remembered detail (ACs: 1)
- US-075 — Results grouped by kind (ACs: 1)
- US-076 — Results never include another user's material (ACs: 1)
- US-118 — My search is reachable whether the left column is expanded or collapsed (ACs: 2)
- US-137 — My-search returns disabled memos, marked as disabled (ACs: 2)
- US-147 — Name matching is case-insensitive in any script (ACs: 1) · **Status:** partially delivered → docs/plans/defects.md

**FEAT-018**
- US-077 — Admin exports the whole database (ACs: 3)
- US-078 — The administrator can read no user content anywhere in the product (ACs: 3)
- US-079 — A user exports their own data with memos (ACs: 2)
- US-080 — Character export and import (ACs: 2)
- US-081 — A session export carries only its own memos (ACs: 1)
- US-082 — An imported session arrives under a character the roleplayer chooses, without the source's context (ACs: 2)
- US-136 — A roleplayer's own import merges as new items and never reuses an id (ACs: 2)

**FEAT-019**
- US-083 — No screen shows another user's characters, sessions or memos (ACs: 1)
- US-084 — User management shows accounts, never content (ACs: 1)
- US-085 — Search and tools never cross the user boundary (ACs: 1)

**FEAT-020**
- US-088 — The tree lists characters with their sessions (ACs: 2)
- US-089 — Sessions in the tree are ordered by last use (ACs: 1)
- US-090 — Collapsing the left column leaves search, create and the user menu reachable (ACs: 1)
- US-091 — The user menu logs the roleplayer out (ACs: 1)
- US-092 — The user menu's settings screen carries the two languages and the user's own notes (ACs: 1)
- US-093 — The admin entry point appears in the user menu only for ACT-001 (ACs: 2)
- US-094 — The note wall opens over the stream and can be pinned; the pin survives a reload (ACs: 4)
- US-095 — With no session open, the note wall is not shown at all (ACs: 1)
- US-096 — A character's page shows its persona, its notes, its setups, its configuration and its sessions in one place (ACs: 1)
- US-097 — Creating a character opens a draft page; nothing is persisted until the roleplayer enters something (ACs: 2)

Total: 147, US-001..US-147, no gaps. Total numbered ACs across all stories:
267, of which 266 are active and 1 (`US-131.AC-1`) is withdrawn.

## Open `_TBD:` items

Every `_TBD:` currently in `docs/product/`, by file and id. The gap-closure
round (2026-09-28) closed nine; exactly one survives, by choice — it was not
revisited that round and remains an accepted consequence. The finalization
(2026-10-06) narrowed it; it was not closed.

- `features.md`, FEAT-018 — a single-session export carries only that session's own memos (challenge C12), so none of the source's character persona or setup travels with it; narrowed at finalization — the roleplayer chooses the character the session is imported into, so it arrives with a persona, just not the one it was written against, and with no setup at all; accepted knowingly, recorded as a known consequence, not a defect.

## `[inferred]` requirements

None. The gap-closure round (2026-09-28) confirmed both requirements that
carried the tag (US-120, US-103) directly with the user; `docs/product/`
carries no inferred requirement.

## Next free ids

- `ACT-005`
- `FEAT-021`
- `UC-089`
- `US-148`
<!-- product-spec:end -->
