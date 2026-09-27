<!-- product-spec:start -->
# Features

Spine of `docs/product/`: one block per `FEAT-###`. Never splits. All 19 are
`Priority: must` — "must" means in-scope-for-v1; sequencing comes from the
dependency graph below, not from priority (challenge C4, rejected).

## Feature blocks

### FEAT-001 — First-run bootstrap
- **Purpose:** Bring an unconfigured instance to a usable state: create a new
  database with a first admin, or import an existing database export.
- **Actors:** ACT-003 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-001, UC-002, UC-003, US-001, US-002, US-003
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### FEAT-002 — Authentication & session
- **Purpose:** Let a created user log in, hold a session, and log out; a
  disabled account cannot log in.
- **Actors:** ACT-001, ACT-002 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-004, UC-005, US-004, US-005, US-006, US-007
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7.

### FEAT-003 — User management
- **Purpose:** Admin-gated account lifecycle: create an account, disable and
  re-enable it, reset its password, list accounts without reaching content.
- **Actors:** ACT-001 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-006, UC-007, UC-008, UC-009, US-008, US-009, US-010,
  US-011
- **Note:** Disabling an account ends that user's sessions. The account list
  shows accounts only, never a user's RP content — see FEAT-019.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 7.

### FEAT-004 — LLM server connections
- **Purpose:** Register and test LLM server connections (llamaswap or
  OpenAI); enable specific models; designate the embedding server and model.
- **Actors:** ACT-001 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-010, UC-011, UC-012, UC-013, US-012, US-013, US-014,
  US-015, US-016
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 7.

### FEAT-005 — Database consistency & management
- **Purpose:** Report per-table schema drift and let an admin remediate it
  (create missing tables, rebuild the vector index).
- **Actors:** ACT-001 · **Priority:** must
- **Status:** proposed
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
  (sessions).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 3,
  round 10.

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
- **Realized by:** UC-023, UC-024, UC-025, UC-026, US-026, US-027, US-028,
  US-029
- **Note:** No "finished" state — a session stays open indefinitely.
  Archiving removes it from the working list and is restorable, same rule as
  FEAT-006 and FEAT-007.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 3,
  round 7.

### FEAT-009 — Session entries & the RP flow
- **Purpose:** The independent entries that make up a session — partner
  blocks and the roleplayer's own answers, added in any order.
- **Actors:** ACT-002 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-027, UC-028, UC-029, UC-030, UC-031, US-030, US-031,
  US-032, US-033, US-034, US-035
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
  refused.
- **_TBD:** session context grows forever with no ceiling (challenge C3, see
  `vision.md` and FEAT-010) — entries accumulate without limit and nothing
  warns the roleplayer as a session's own size grows.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 4, round 6,
  round 7, round 9.

### FEAT-010 — Compose discussion
- **Purpose:** The discussion attached to an answer entry, where the
  roleplayer and the assistant work out the settled reply.
- **Actors:** ACT-002, ACT-004 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-032, UC-033, UC-034, UC-035, UC-036, UC-037, UC-038,
  US-036, US-037, US-038, US-039, US-040, US-041, US-042, US-043, US-044
- **Note:** Three paths into one answer box: the assistant produces a
  candidate, the roleplayer writes from scratch, or edits an assistant
  candidate. Settling takes whatever the box holds at that moment — the box
  is always the roleplayer's; the assistant never writes into the session
  directly. Discussion language: the assistant mirrors the language of each
  message — there is no fixed discussion language; candidates are
  nonetheless always produced in the RP language. Collapse rule: settling an
  answer collapses its discussion; a collapsed discussion stays readable but
  is re-openable only while nothing follows it — an undo for a mis-click,
  not a workflow. Once the next entry exists it is permanently
  non-resumable, and a settled discussion never reaches the assistant again.
  Deliberate asymmetry, stated so it is not "fixed" later: a settled answer
  (FEAT-009) is editable forever, while its discussion is re-openable only
  until the next entry exists. Exception flows: the LLM going away
  mid-discussion loses none of the roleplayer's text — the entry and
  discussion survive intact, the failure is visible, retry is possible; a
  failed tool does not end the discussion — the assistant is told the tool
  failed and carries on without it.
- **_TBD:** unbounded session context (challenge C3). Context grows forever
  with no ceiling, no warning and no pruning; a long RP will eventually
  exceed what the model can hold and nothing warns the roleplayer first.
  Context compaction is named as a future capability, deliberately out of
  this spec.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 4,
  round 7, round 8, round 9.

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
  text with a visible error, and nothing is cached.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 2,
  round 4, round 9.

### FEAT-012 — Memos
- **Purpose:** Standing memos at four levels — user, character, setup,
  session — that reach the assistant as forced, searchable, or disabled.
- **Actors:** ACT-002, ACT-004 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-042, UC-043, UC-044, UC-045, UC-046, US-049, US-050,
  US-051, US-052, US-053, US-054, US-055, US-056, US-057
- **Note:** One setting, three values: `forced` (always in the system
  prompt), `searchable` (reachable only by tool), `disabled` (reaches the
  assistant by no path). Default on creation is `searchable`. Markdown
  editor with live preview. Simpler than a two-axis active/archived model —
  there is no archived state for memos. A session's memo chain resolves with
  or without a setup — degrades to user + character + session with no gap
  when a setup is absent (FEAT-007).
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5,
  round 6.

### FEAT-013 — Session configuration & inheritance
- **Purpose:** Model, system prompt, tool switches, and the two languages,
  each resolved for a session from user defaults down.
- **Actors:** ACT-002 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-047, UC-048, UC-049, UC-050, US-058, US-059, US-060,
  US-061, US-062
- **Note:** Two languages: the **RP language** is what the roleplay is
  conducted in — the partner's text arrives in it, the final answer is
  written in it, and it is the only language the session's model context
  holds. The **preferred language** is what the roleplayer thinks and
  discusses in, and what partner text is translated into (FEAT-011). English
  is merely the common case, never the rule. **Deliberate inheritance
  asymmetry, stated so it is not "fixed" later:** model, system prompt and
  tool switches inherit `user → character → session`; the RP language and
  the preferred language inherit `user → session`, skipping the character
  level.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 2, round 5,
  round 10.

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
  carries on.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 5,
  round 9.

### FEAT-015 — `session_search` tool
- **Purpose:** The assistant finds past sessions under the same character by
  meaning.
- **Actors:** ACT-002, ACT-004 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-053, UC-054, US-067, US-068, US-069
- **Note:** Semantic only — no structured matching on partner name or setup,
  because the partner is free text and the setup is optional (challenge C5).
  Semantic search is what keeps the "same person or situation" promise true
  when neither is present. Results never cross a character or user boundary.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, challenge
  C5.

### FEAT-016 — `web_search` tool
- **Purpose:** The assistant looks up real-world information on the
  roleplayer's behalf.
- **Actors:** ACT-002, ACT-004 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-055, UC-056, UC-057, US-070, US-071, US-072, US-073
- **Note:** Three justified uses (challenge C2): a real-world fact (a place,
  a weapon, a procedure, a period detail); an idiom or naturalness check
  (does this phrasing sound natural); a direct, roleplayer-initiated lookup.
  Disabled by the configuration chain (FEAT-013) like any other tool.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 5, round 6,
  challenge C2.

### FEAT-017 — My search
- **Purpose:** One search box reaching everything the roleplayer owns, from
  any screen.
- **Actors:** ACT-002 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-058, UC-059, UC-060, US-074, US-075, US-076
- **Note:** Distinct from FEAT-014/FEAT-015, not an overlap (challenge C7,
  rejected by the user: "tool search is the content search, my search is on
  user level UI to find the sessions i did. Totally different
  functionality"). FEAT-014/015 are content retrieval performed by the
  assistant mid-discussion; this is a user-level UI for finding sessions the
  roleplayer ran. Results grouped by kind; never include another user's
  material.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 7, round 8,
  challenge C7.

### FEAT-018 — Export & import
- **Purpose:** Move or restore data at four granularities — whole database,
  per-user, per-character, per-session — each carrying its own memos.
- **Actors:** ACT-001, ACT-002 · **Priority:** must
- **Status:** proposed
- **Realized by:** UC-061, UC-062, UC-063, UC-064, US-077, US-078, US-079,
  US-080, US-081, US-082
- **Note:** Owns export/import at every granularity — see the Relationships
  boundary below against FEAT-005, which owns drift, remediation and
  vector-index rebuild. The whole-database export is opaque to the
  administrator: the product offers no viewer, no search, no rendering of
  another user's content; the export exists to move or restore an instance.
  This is how challenge C1's conflict with FEAT-019's privacy guarantee was
  settled.
- **_TBD:** a single-session export carries only that session's own memos
  (challenge C12), so an imported session arrives without the character
  persona and setup that gave it meaning. Accepted knowingly, recorded here
  as a known consequence, not a defect.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 1, round 2,
  challenge C12.

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

## Relationships

**Coverage:** no orphan actors, no orphan features — every `FEAT-###` above
realizes at least one UC/US and traces to at least one actor.

**Depends on / build order** (no cycles): `FEAT-001 → FEAT-002 → FEAT-003 →
FEAT-019 → FEAT-004 → FEAT-005 → FEAT-006 → FEAT-007 → FEAT-008 → FEAT-009 →
FEAT-012 → FEAT-013 → FEAT-010 → FEAT-011 → FEAT-014 → FEAT-015 → FEAT-016 →
FEAT-017 → FEAT-018`.

**Overlaps (accepted):** FEAT-012 (forced memos) × FEAT-013 (system prompt)
— a memo records *what to remember*, the prompt shapes *how the assistant
behaves*.

**Boundary:** FEAT-018 owns export/import at every granularity; FEAT-005
owns drift, remediation and vector-index rebuild.

**Distinction (not an overlap — challenge C7 rejected):** FEAT-014/FEAT-015
are content retrieval performed by the assistant mid-discussion; FEAT-017 is
a user-level UI for finding sessions the roleplayer ran.

**Configuration asymmetry, deliberate (FEAT-013):** model, system prompt and
tool switches inherit `user → character → session`; the RP language and the
preferred language inherit `user → session`, skipping the character.

**Conflicts:** None open.
<!-- product-spec:end -->
