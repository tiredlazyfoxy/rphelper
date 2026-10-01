<!-- product-spec:start -->
# Features

Spine of `docs/product/`: one block per `FEAT-###`. Never splits. All 20 are
`Priority: must` — "must" means in-scope-for-v1; sequencing comes from the
dependency graph below, not from priority (challenge C4, rejected).

## Feature blocks

### FEAT-001 — First-run bootstrap
- **Purpose:** Bring an unconfigured instance to a usable state: create a new
  database with a first admin, or import an existing database export.
- **Actors:** ACT-003 · **Priority:** must
- **Status:** partially delivered
- **Delivered:** docs/plans/003.first-run-bootstrap/ (2026-09-29); US-001.AC-2 by docs/plans/004.authentication-session/ (2026-09-29)
- **Remaining:** UC-002, US-002 → docs/plans/fast/003.bootstrap-from-export/
- **Realized by:** UC-001, UC-002, UC-003, US-001, US-002, US-003
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### FEAT-002 — Authentication & session
- **Purpose:** Let a created user log in, hold a session, and log out; a
  disabled account cannot log in.
- **Actors:** ACT-001, ACT-002 · **Priority:** must
- **Status:** partially delivered
- **Delivered:** docs/plans/004.authentication-session/ (2026-09-29)
- **Remaining:** US-007.AC-1's logout affordance → docs/plans/008.app-shell-frame/
- **Realized by:** UC-004, UC-005, US-004, US-005, US-006, US-007
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### FEAT-003 — User management
- **Purpose:** Admin-gated account lifecycle: create an account, disable and
  re-enable it, reset its password, change its role, list accounts without
  reaching content.
- **Actors:** ACT-001 · **Priority:** must
- **Status:** delivered
- **Delivered:** docs/plans/005.admin-shell-and-users/ (2026-09-29)
- **Realized by:** UC-006, UC-007, UC-008, UC-009, UC-087, US-008, US-009,
  US-010, US-011, US-140
- **Note:** Disabling an account ends that user's sessions. The account list
  shows accounts only, never a user's RP content — see FEAT-019.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 7; finalization 2026-10-01, C31.

### FEAT-004 — LLM server connections
- **Purpose:** Register and test LLM server connections (llamaswap or
  OpenAI); enable specific models; designate the embedding server and model.
- **Actors:** ACT-001 · **Priority:** must
- **Status:** partially delivered
- **Delivered:** docs/plans/006.llm-server-connections/ (2026-09-30)
- **Remaining:** US-014 + US-016.AC-3 session-configuration half →
  docs/plans/017.session-configuration/; US-016.AC-2 error shown on the
  session → the session surface (docs/plans/011.rp-sessions/,
  docs/plans/019.streaming-transport-and-stop/)
- **Realized by:** UC-010, UC-011, UC-012, UC-013, US-012, US-013, US-014,
  US-015, US-016
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 7.

### FEAT-005 — Database consistency & management
- **Purpose:** Report per-table schema drift and let an admin remediate it
  (create missing tables, rebuild the vector index).
- **Actors:** ACT-001 · **Priority:** must
- **Status:** partially delivered
- **Delivered:** docs/plans/007.schema-drift-and-remediation/ (2026-09-30)
- **Remaining:** UC-016, US-019 → docs/plans/fast/002.vector-index-rebuild/
- **Realized by:** UC-014, UC-015, UC-016, US-017, US-018, US-019
- **Note:** Owns drift, remediation and vector-index rebuild — see the
  Relationships boundary below against FEAT-018, which owns export/import.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### FEAT-006 — Characters
- **Purpose:** A roleplayer's persona — a character sheet reused across many
  setups and partners, that the assistant composes replies as.
- **Actors:** ACT-002 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-017, UC-018, UC-019, UC-067, US-020, US-021, US-022,
  US-086
- **Note:** Archives and restores — out of the working list, nothing
  destroyed, always recoverable. Same rule as FEAT-007 (setups) and FEAT-008
  (sessions). Creation opens a draft page; nothing persists until the
  roleplayer enters something (FEAT-020, US-097).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 3,
  round 10, round 14.

### FEAT-007 — Setups
- **Purpose:** An optional reusable object under a character, carrying its
  own memos and acting as a search anchor for a situation.
- **Actors:** ACT-002 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-020, UC-021, UC-022, UC-068, US-023, US-024, US-025,
  US-087
- **Note:** Setup is optional — a genuine absence, not a default that is
  usually filled in. A session may have no setup at all and everything must
  work: the memo chain degrades to user + character + session with no gap;
  `memo_search` returns correct results with no setup level present;
  `session_search` still finds past sessions by the same person or situation
  when neither has a setup; no flow may require choosing a setup before an
  RP can start. Archives and restores, same rule as FEAT-006 and FEAT-008.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 2, round 3,
  round 6, round 10.

### FEAT-008 — RP sessions
- **Purpose:** A roleplay run under a character, optionally with a setup;
  always resumable, ordered by last use.
- **Actors:** ACT-002 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-023, UC-024, UC-025, UC-026, UC-080, US-026, US-027,
  US-028, US-029, US-117
- **Note:** No "finished" state — a session stays open indefinitely.
  Archiving removes it from the working list and is restorable, same rule as
  FEAT-006 and FEAT-007. A session can also start by writing the first
  message on its character's page (FEAT-020): the message creates the
  session with a turn being drafted and opens that message's discussion.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 3,
  round 7, round 15.

### FEAT-009 — Session entries & the RP flow
- **Purpose:** The independent entries that make up a session — partner
  blocks, the roleplayer's own turns, and decisions — three kinds, still
  independent and still addable in any order.
- **Actors:** ACT-002 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-027, UC-028, UC-029, UC-030, UC-031, UC-078, UC-081,
  UC-082, US-030, US-031, US-032, US-033, US-034, US-035, US-109, US-110,
  US-111, US-112, US-120, US-121, US-122, US-123, US-124
- **Note:** Entries are independent — partner blocks and the roleplayer's
  answers are separate items added in any order; a compose discussion
  attaches to whichever answer is being worked on. The roleplayer can
  therefore open an RP themselves, post two answers running, or paste
  several partner blocks in sequence — there is no mandatory
  partner-block → discussion → answer triple. A settled answer is editable
  at any time, including one from weeks ago — the assistant always reads the
  current version, so a later edit changes what session context says
  happened; a deliberate asymmetry against FEAT-010's collapsed-discussion
  rule (see there). An enormous paste warns about context cost but is never
  refused. A third kind, decisions, joined the roleplayer's turns and
  partner blocks: something settled about the roleplay itself (a tone or
  situation change), positioned in time — everything before it still reads
  the old way. A decision reaches the assistant as context from that point
  on and is found by session search, but offers no copy-out. Any settled
  entry — partner block, turn or decision — is edited in place and saved,
  with search reflecting the new text; editing a partner block discards its
  cached translation, so the next flick re-translates the new text. With no
  embedding model configured, an edit still saves and the roleplayer is told
  search coverage is incomplete, never refused. Copying a settled turn
  yields plain text, never markdown. Context is unbounded by choice — nothing
  warns the roleplayer as a session's own size grows; see `vision.md`'s "No
  context compaction" non-goal and FEAT-010.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 4, round 6,
  round 7, round 9, round 12, round 13; 2026-09-28, round 17, gap-closure
  round.

### FEAT-010 — Compose discussion
- **Purpose:** The discussion attached to an answer entry, where the
  roleplayer and the assistant work out the settled reply.
- **Actors:** ACT-002, ACT-004 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-032, UC-033, UC-034, UC-035, UC-036, UC-037, UC-038,
  UC-079, UC-083, UC-084, UC-085, UC-086, US-036, US-037, US-038, US-039,
  US-040, US-041, US-042, US-043, US-044, US-113, US-114, US-115, US-116,
  US-125, US-126, US-127, US-128, US-129, US-130, US-131, US-132, US-133,
  US-134, US-135
- **Note:** Three paths into one current-zone message: the assistant
  produces a candidate, the roleplayer writes from scratch, or edits a
  candidate. Settle takes the last message in the current zone, whoever
  wrote it. **Restated, not dropped:** there is no dedicated answer box —
  nothing reaches the session record without the roleplayer settling it,
  and every message in the current zone, the assistant's included, is the
  roleplayer's to rewrite first. Discussion language: the assistant mirrors
  the language of each message — there is no fixed discussion language;
  candidates are nonetheless always produced in the RP language. Tool calls
  and the assistant's thinking are visible while it works, tucked away once
  it finishes, re-openable at any time. The current zone's kind switch
  (partner / my turn) defaults by alternating — partner after a turn of
  mine, my turn after a partner block — skipping decisions when it works
  out which. A wholly-parenthesised message is out-of-character: settling
  one files a decision, not a turn; a parenthesised fragment inside a draft
  is a fast instruction that never appears in the settled turn and the
  assistant does not reproduce it in the prose. OOC messages are in the
  preferred language; the assistant answers OOC in kind, while candidates
  stay in the RP language. A partner block gets no `(( ))` treatment — it
  is just text. The `(( ))` convention assumes double parentheses never
  occur in the roleplayer's own fiction — examined and confirmed by the
  roleplayer, not an unexamined assumption. Collapse rule: settling
  collapses the discussion in place; a collapsed discussion stays readable
  but is re-openable only while the current zone below it is still empty —
  an undo for a mis-click, not a workflow. Once the current zone below it
  holds something, it is permanently non-resumable, and a settled discussion
  never reaches the assistant again. Deliberate asymmetry, stated so it is
  not "fixed" later: a settled turn (FEAT-009) is editable forever, while
  its discussion is re-openable only until the current zone below it is no
  longer empty. An empty current zone can be abandoned and discarded; a
  zone holding text cannot be discarded at all and must be settled —
  settling never requires an assistant answer, so the zone can never trap
  the roleplayer (UC-086). Context is unbounded by choice — nothing warns
  the roleplayer as a session grows; see `vision.md`'s "No context
  compaction" non-goal and FEAT-009. The roleplayer can stop any model work
  in flight — a discussion generation, a tool call being waited on, or a
  partner-text translation — and whatever text was produced stays as a
  usable candidate; there is no cap on tool iterations, the stop is what
  bounds a runaway loop (UC-085). FEAT-010 owns the stop even where it
  interrupts a FEAT-011 translation or a FEAT-014/015/016 tool call.
  Exception flows: the LLM going away mid-discussion loses none of the
  roleplayer's text — the entry and discussion survive intact, the failure
  is visible, retry is possible; a failed tool does not end the discussion —
  the assistant is told the tool failed and carries on without it; a failed
  generation of any kind shows its reason, and the reason does not persist
  once the notice has gone.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 4,
  round 7, round 8, round 9, round 11, round 12, round 14; 2026-09-28,
  round 17, gap-closure round.

### FEAT-011 — Partner-text translation
- **Purpose:** A read-only flicker that translates a pasted partner entry
  into the roleplayer's preferred language, on demand.
- **Actors:** ACT-002 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-039, UC-040, UC-041, US-045, US-046, US-047, US-048
- **Note:** Nothing is translated until the roleplayer flicks it; the result
  is cached after first use so the second look is instant and costs nothing.
  A translation never enters session context — context holds only the RP
  language. Exception flow: a failed translation falls back to the original
  text with a visible error, and nothing is cached. A translation in flight
  can be stopped (FEAT-010) — the original text stands and nothing is
  cached, the same as a failed translation.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 2,
  round 4, round 9; 2026-09-28, gap-closure round.

### FEAT-012 — Memos
- **Purpose:** Standing memos (the roleplayer's word: notes) at four levels
  — user, character, setup, session — each independently forced or not, and
  enabled or disabled.
- **Actors:** ACT-002, ACT-004 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-042, UC-043, UC-044, UC-045, UC-046, UC-075, UC-076,
  US-049, US-050, US-051, US-052, US-053, US-054, US-055, US-056, US-057,
  US-098, US-099, US-100, US-101, US-102, US-103, US-104, US-119
- **Note:** Two axes, not one setting with three values — forced/not-forced
  and enabled/disabled. Disabled wins: a disabled note reaches the assistant
  by no path whatever its forced flag says. The forced flag is remembered
  while disabled and restored on re-enable. Default on creation is enabled
  and not forced. Enabled+forced notes enter the system prompt;
  enabled+not-forced notes are reachable only by `memo_search`. Forced notes
  enter the system prompt in the roleplayer's arranged order within a fixed
  level order — user, character, setup, session; a note reorders only
  within its own level, never across levels. A note is one body of text —
  no title, name or header field; any heading the roleplayer wants is
  markdown they type inside it. A note's text is edited where it sits and
  saved when focus leaves it. Markdown editor with live preview. Simpler
  than an active/archived model — there is no archived state for notes. A
  session's memo chain resolves with or without a setup — degrades to
  user + character + session with no gap when a setup is absent (FEAT-007).
  Because a note has no title, `memo_search` (FEAT-014) and my-search
  (FEAT-017) identify a note by a snippet of its text and its level.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5,
  round 6, round 11, round 12, round 16.

### FEAT-013 — Session configuration & inheritance
- **Purpose:** The model is captured once, when a session is created, and
  never changes afterwards; system prompt and tool switches resolve live
  `character → session`; the RP language and the preferred language resolve
  live `user → session`.
- **Actors:** ACT-002 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-047, UC-048, UC-049, UC-050, UC-077, US-058, US-059,
  US-060, US-061, US-062, US-105, US-106, US-107, US-108, US-139
- **Note:** Two languages: the **RP language** is what the roleplay is
  conducted in — the partner's text arrives in it, the final answer is
  written in it, and it is the only language the session's model context
  holds. The **preferred language** is what the roleplayer thinks and
  discusses in, and what partner text is translated into (FEAT-011). English
  is merely the common case, never the rule. **Deliberate inheritance
  asymmetry, stated so it is not "fixed" later:** model, system prompt and
  tool switches inherit `character → session` only — there is no user-level
  default for these three; the RP language and the preferred language
  inherit `user → session`, skipping the character. The two chains now share
  no level at all. Choosing a model from the session's header sets the
  session-level override and it persists — no per-turn transient override.
  A character with no model configured resolves to the first enabled model
  **at the moment a session is created**: a **default for a level that was
  never configured**, never a fallback for a configured model that has since
  been disabled — a session whose configured model is disabled still shows
  an error (UC-012). With no enabled model at all, the roleplayer cannot
  send a message and is told why. **Resolution split, deliberate, one chain
  and two behaviours:** the MODEL is captured once, at session creation, and
  never changes afterwards — configuring a character with a model
  afterwards reaches only sessions created from that point on, never a
  session that already exists (US-139). The SYSTEM PROMPT and ENABLED TOOLS
  keep resolving live through `character → session` for every session, old
  or new, whatever the character is configured with today.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 2, round 5,
  round 10, round 11, round 13, round 14, round 15; 2026-09-28, gap-closure
  round.

### FEAT-014 — `memo_search` tool
- **Purpose:** The assistant searches searchable memos across the session's
  memo chain.
- **Actors:** ACT-002, ACT-004 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-051, UC-052, US-063, US-064, US-065, US-066
- **Note:** Forced memos are excluded because they are already in context;
  disabled memos are excluded because they reach the assistant by no path.
  Works correctly with no setup level present (FEAT-007). Exception flow: a
  failed tool does not end the discussion — the assistant is told and
  carries on. A tool call being waited on can be stopped (FEAT-010); there
  is no limit on how many times the assistant may call tools before
  answering.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5,
  round 9; 2026-09-28, gap-closure round.

### FEAT-015 — `session_search` tool
- **Purpose:** The assistant finds past sessions under the same character by
  meaning.
- **Actors:** ACT-002, ACT-004 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-053, UC-054, US-067, US-068, US-069, US-138
- **Note:** Semantic only — no structured matching on partner name or setup,
  because the partner is free text and the setup is optional (challenge C5).
  Semantic search is what keeps the "same person or situation" promise true
  when neither is present. Results never cross a character or user boundary.
  A match considers a session's entries together with its character's
  persona and setup — this is what lets a query about a similar person, not
  just a similar situation, find the right session. A tool call being
  waited on can be stopped (FEAT-010); there is no limit on how many times
  the assistant may call tools before answering.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, challenge
  C5; 2026-09-28, gap-closure round.

### FEAT-016 — `web_search` tool
- **Purpose:** The assistant looks up real-world information on the
  roleplayer's behalf.
- **Actors:** ACT-002, ACT-004 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-055, UC-056, UC-057, US-070, US-071, US-072, US-073
- **Note:** Three justified uses (challenge C2): a real-world fact (a place,
  a weapon, a procedure, a period detail); an idiom or naturalness check
  (does this phrasing sound natural); a direct, roleplayer-initiated lookup.
  Disabled by the configuration chain (FEAT-013) like any other tool. A tool
  call being waited on can be stopped (FEAT-010); there is no limit on how
  many times the assistant may call tools before answering.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, round 6,
  challenge C2; 2026-09-28, gap-closure round.

### FEAT-017 — My search
- **Purpose:** One search box reaching everything the roleplayer owns, from
  any screen.
- **Actors:** ACT-002 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-058, UC-059, UC-060, US-074, US-075, US-076, US-118,
  US-137
- **Note:** Distinct from FEAT-014/FEAT-015, not an overlap (challenge C7,
  rejected by the user: "tool search is the content search, my search is on
  user level UI to find the sessions i did. Totally different
  functionality"). FEAT-014/015 are content retrieval performed by the
  assistant mid-discussion; this is a user-level UI for finding sessions the
  roleplayer ran. Results grouped by kind; never include another user's
  material. Reachable whether the workspace shell's left column (FEAT-020)
  is expanded or collapsed. My-search returns memos regardless of their
  enabled or forced state — note state never filters a result out — and a
  result that is currently disabled is shown as disabled.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7, round 8,
  round 14, challenge C7; 2026-09-28, gap-closure round.

### FEAT-018 — Export & import
- **Purpose:** Move or restore data at four granularities — whole database,
  per-user, per-character, per-session — each carrying its own memos.
- **Actors:** ACT-001, ACT-002 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-061, UC-062, UC-063, UC-064, US-077, US-078, US-079,
  US-080, US-081, US-082, US-136
- **Note:** Owns export/import at every granularity — see the Relationships
  boundary below against FEAT-005, which owns drift, remediation and
  vector-index rebuild. The whole-database export is opaque to the
  administrator: the product offers no viewer, no search, no rendering of
  another user's content; the export exists to move or restore an instance.
  This is how challenge C1's conflict with FEAT-019's privacy guarantee was
  settled. Import merges as new items alongside what is already there and
  never reuses an id — imported material always arrives under fresh
  identity, and can never overwrite or merge into an existing row. Importing
  the same export twice yields duplicates, and nothing warns about it.
- **_TBD:** a single-session export carries only that session's own memos
  (challenge C12), so an imported session arrives without the character
  persona and setup that gave it meaning. Accepted knowingly, recorded here
  as a known consequence, not a defect.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 2,
  challenge C12; 2026-09-28, gap-closure round, challenge C29.

### FEAT-019 — Privacy & isolation
- **Purpose:** No screen, search, tool or export view ever shows another
  user's material.
- **Actors:** ACT-001, ACT-002 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-065, UC-066, US-083, US-084, US-085
- **Note:** Absolute — every listing, search and tool is scoped to the
  owning user; administrative surfaces expose no user content. This is how
  challenge C1's conflict with FEAT-018's whole-database export was settled:
  privacy is a product guarantee, and the export is opaque to the
  administrator by FEAT-018's own rule.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 1,
  round 2.

### FEAT-020 — Workspace shell & navigation
- **Purpose:** The single shell the roleplayer works in — navigation, the
  merged stream, the note wall, the user menu — and what stays reachable
  when it is collapsed.
- **Actors:** ACT-002 (primary), ACT-001 (admin entry point only) ·
  **Priority:** must
- **Status:** proposed
- **Realized by:** UC-069, UC-070, UC-071, UC-072, UC-073, UC-074, US-088,
  US-089, US-090, US-091, US-092, US-093, US-094, US-095, US-096, US-097
- **Note:** Left column lists characters with their sessions (setup shown as
  a label on a session row, or nothing when it has none), sessions ordered
  by last use. Collapsing the left column to an icon rail still leaves
  search, create and the user menu reachable. The user menu logs the
  roleplayer out, opens a settings screen carrying the two languages and the
  roleplayer's own notes, and — for ACT-001 only — the admin entry point.
  The note wall opens over the stream and can be pinned, the pin surviving a
  reload; with no session open, the wall is not shown at all. A character's
  page shows its persona, its notes, its setups, its configuration and its
  sessions in one place. Creating a character opens a draft page; nothing
  persists until the roleplayer enters something.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 11, round 12,
  round 13, round 14, round 15.

## Relationships

**Coverage:** no orphan actors, no orphan features — every `FEAT-###` above
realizes at least one UC/US and traces to at least one actor.

**Depends on / build order** (no cycles): `FEAT-001 → FEAT-002 → FEAT-003 →
FEAT-019 → FEAT-004 → FEAT-005 → FEAT-006 → FEAT-007 → FEAT-008 → FEAT-009 →
FEAT-012 → FEAT-013 → FEAT-010 → FEAT-011 → FEAT-014 → FEAT-015 → FEAT-016 →
FEAT-017 → FEAT-018 → FEAT-020`.

**Depends on (new edges):** FEAT-020 depends on FEAT-002, FEAT-006, FEAT-008,
FEAT-012, FEAT-017. No cycles.

**Overlaps (accepted):**
- FEAT-012 (forced memos) × FEAT-013 (system prompt) — a memo records *what
  to remember*, the prompt shapes *how the assistant behaves*.
- FEAT-012 × FEAT-020 — FEAT-012 owns what a note is and what the assistant
  receives; FEAT-020 owns where the wall appears and whether it is
  reachable.
- FEAT-017 × FEAT-020 — FEAT-017 owns what my-search returns; FEAT-020 owns
  that its trigger survives a collapse.
- FEAT-009 (decision entries) × FEAT-012 (session notes) — a decision is
  positioned in time and everything before it still reads the old way; a
  note is standing context, true throughout the session.
- FEAT-010 (stop) × FEAT-011 (translation) — FEAT-010 owns the stop and
  what survives it; FEAT-011 owns what a translation is.
- FEAT-010 (stop) × FEAT-014/015/016 (tools) — FEAT-010 owns stopping a
  tool wait in progress; the tool features own what each tool does and what
  a failed tool means. A stopped tool is the roleplayer's choice; a failed
  tool is the tool's own.

**Boundary:** FEAT-018 owns export/import at every granularity; FEAT-005
owns drift, remediation and vector-index rebuild.

**Distinction (not an overlap — challenge C7 rejected):** FEAT-014/FEAT-015
are content retrieval performed by the assistant mid-discussion; FEAT-017 is
a user-level UI for finding sessions the roleplayer ran.

**Configuration asymmetry, deliberate (FEAT-013):** model, system prompt and
tool switches inherit `character → session` only, with no user-level
default; the RP language and the preferred language inherit `user →
session`, skipping the character. The two chains now share no level at all.

**Accepted consequences (gap-closure round, 2026-09-28):**
- Configuring a character's model does not reach sessions that already
  exist (US-139).
- A session that captured a model later disabled by the administrator falls
  under US-107 — told why, never silently substituted.
- An overflow retry always fails, and the reason for any failure is
  transient — nothing persists after the notice fades.
- Nothing indicates that the vector index was built by a superseded
  embedding model; semantic results degrade silently until the rebuild
  (UC-016) is run.
- Importing the same export twice yields duplicates, with no warning.

**Conflicts:** None open in `docs/product/`. Dependency edges and the build
order are unchanged by this round. Five items conflict with
`docs/architecture/` and are routed to `/architect` — they are architecture
decisions, not product conflicts.
<!-- product-spec:end -->
