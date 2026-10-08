# Feature 020 — Context assembly · feature-wide context

## What this feature is

Decides exactly what the assistant reads for one session, and in what order. One backend
service entry point takes a connection, the caller's user id and a session id, and
returns an **assembled context**: a system-prompt string plus an ordered list of chat
messages. Nothing calls it in 020; `021` (the compose loop) is its only future caller.

Backend only: no router, no route, no frontend, no schema change, no new dependency.

The agreed boundary is `brief.md` in this folder. Its Definition and Scope In/Out bound
every step and are **not** widened. Out, and kept out:

- issuing the model request and the tool loop (`021`), including `resolve_model_for_use`
  (017's use-time check). `021` calls it, 020 does not;
- tool definitions and tool descriptions. `021` sends the enabled tools through the API's
  `tools` parameter, so **the prompt text carries no tool descriptions** (D2). This
  narrows `llm-and-streaming.md`'s "+ tool descriptions for ENABLED tools only", recorded
  in `outcome.md`;
- the tools themselves (`026`, `027`, `028`) and the searchable half of notes (`026`);
- translation (`023`). Assembly never reads translations (R8).

## Product ids

Delivers **FEAT-010** via UC-033, UC-038 and **FEAT-012** via UC-045, plus the prompt
halves `016` deferred.

| Criterion | Where it lands |
|---|---|
| US-036.AC-1..AC-3 (mirror the language of each message) | `001` (the mirroring instruction is in the prompt, `[test]`); `002` (the model actually mirrors, `[manual/live]`) |
| US-131.AC-2, AC-3 (out-of-character in the preferred language) | `001` (instruction names the preferred language, `[test]`); `002` (`[manual/live]`). AC-1 is withdrawn |
| US-043.AC-1, AC-2 (a buried discussion never reaches the assistant) | `002` (buried rows absent; UC-038, R7, R11) |
| US-054.AC-1 (a forced note is in the system prompt) | `001` (rendering), `002` (selection) |
| US-055.AC-1 (a searchable note is not in the system prompt) | `002`. AC-2 is `memo_search`'s (`026`) |
| US-098.AC-1 (a disabled note never reaches the assistant) | `002`, including disabled **and** forced (R3) |
| US-102.AC-1 (reordered forced notes enter in the new order) | `002` (016 delivered the persisted order) |
| US-103.AC-1 (level order user → character → setup → session) | `001` (renders levels in the order given), `002` (supplies chain order) |

Cited as related, not delivered as separate criteria: US-122 / UC-081 (a decision is
context, D7), US-129 / US-130 / UC-084 (the `(( ))` reading instruction, D10),
UC-029 / US-110 / US-115 (read live, D11), R8 (translations never), and `vision.md`'s
"No context compaction" non-goal (D12).

**Language-behaviour criteria are model behaviour.** Their DoD items are `[test]` only for
"the instruction is present in the assembled prompt", and `[manual/live]` for "the model
actually does it". The live checks need `021` to issue requests.

## Build prerequisites

Built and committed: 001..013. **014..019 are planned, not built.** 020 binds to their
declared interfaces, cited from their plan files.

| Step | Needs built first | Why |
|---|---|---|
| `001` | nothing beyond the committed code | pure functions over 012's `StreamMessage` and plain values; new modules only |
| `002` | **015 `001`–`003`**, **017 `001`–`003`** (016 `001` if it has landed; it changes only `sort_key` allocation) | calls `resolve_chain` / `memo_reach` (015) and `get_session_configuration` (017); tests raw-insert into the `memos` table and 017's configuration columns |

**Build-order precondition:** step `002` cannot be built, red-gated or verified until 015
and 017 are delivered. Step `001` can be built at any time. 019's
`append_assistant_message` is **not** needed: tests raw-insert `role='assistant'` rows.

## Built state both steps read

`backend/app/services/messages.py` (012, built):

- **`StreamMessage`**: frozen dataclass with `id` (int), `session_id` (int), `role` (str),
  `kind` (str or None), `text` (str), `settled_at` (str or None), `created_at` (str),
  `updated_at` (str).
- `role` values in the table: `'user'`, `'assistant'`, `'tool'` (`data-model.md`). Today
  012 writes only `'user'`; 019 adds `'assistant'` zone rows; `021` will write `'tool'`
  rows.
- `kind` is `'partner'`, `'turn'` or `'decision'` on a settled row and **NULL** on a
  current-zone row. A pasted partner block is `role='user'`, `kind='partner'`.
- Settled turns are already `(( ))`-stripped at settle; decisions are stored verbatim with
  their `(( ))` (R12). The assembler never re-parses either.

Services are synchronous and take a SQLAlchemy Core `Connection` first; reads leave no
transaction open. `SessionNotFoundError` is in `app/errors.py` (404).

## The prompt format — the contract both steps' tests bind to

Exact literals. Tests assert headings and lead-ins as whole lines / line starts, order by
position, verbatim user text as substrings, and absence. They do **not** assert the prose
after a lead-in's colon, except where a language name must appear.

### System-prompt sections, in this fixed order

| # | Heading line (exact) | Content | Present when |
|---|---|---|---|
| 1 | `=== System prompt ===` | the resolved system prompt, verbatim | the resolved value is not null (D5) |
| 2 | `=== Character sheet ===` | the character's `sheet`, verbatim | the sheet is not empty or whitespace only (D5) |
| 3 | `=== Forced notes ===` | the level blocks below | at least one level has at least one forced note |
| 4 | `=== Message tags ===` | four lead-in lines (below) | always |
| 5 | `=== Languages ===` | three lead-in lines (below) | always |
| 6 | `=== Double parentheses ===` | two lead-in lines (below) | always |

Layout: a section is its heading line, a newline, then its content. Sections are joined by
one blank line. Every heading and every lead-in starts at the beginning of a line.

### Forced-notes level blocks

One block per level that has at least one forced note, in the order the levels are given
(the chain's order: user, character, setup when present, session). A level with no forced
note has **no** heading. Level heading lines (exact):

| Scope | Heading line |
|---|---|
| `user` | `--- User notes ---` |
| `character` | `--- Character notes ---` |
| `setup` | `--- Setup notes ---` |
| `session` | `--- Session notes ---` |

Within a level, each note is a line `[note]` followed on the next line by the note's body,
verbatim, in the order given. Notes and level blocks are separated by one blank line.

### Instruction lead-ins (exact line starts; the prose after the colon is the coder's, fixed English)

| Section | Lead-in | What the line tells the model | Must contain |
|---|---|---|---|
| Message tags | `- [partner]:` | the partner's settled text, not the roleplayer's | — |
| Message tags | `- [my turn]:` | the roleplayer's own settled turn in the record | — |
| Message tags | `- [decision]:` | a settled out-of-character decision; standing context from that point on | — |
| Message tags | `- Untagged:` | the live current discussion below the record | — |
| Languages | `- Candidates:` | candidate prose for the roleplayer's turn is always in the RP language, whatever language the discussion is in, OOC or not | the RP language name (D4) |
| Languages | `- Mirroring:` | answer each message in the language that message is written in | — |
| Languages | `- Out of character:` | out-of-character exchanges are in the preferred language, answered in kind | the preferred language name (D4) |
| Double parentheses | `- Wholly parenthesised:` | a message entirely in `(( ))` is out-of-character talk about the roleplay; answer in kind, not with prose | — |
| Double parentheses | `- Fragment:` | a `(( ))` fragment inside a draft is an instruction to apply to the surrounding prose; never reproduce the fragment | — |

The prompt names no tool (`memo_search`, `session_search`, `web_search`) and no setup
description (D2).

### Kind tags on settled messages (D1)

| Stored `kind` | Tag literal |
|---|---|
| `partner` | `[partner]` |
| `turn` | `[my turn]` |
| `decision` | `[decision]` |

A settled row's chat content is **the tag, one line feed, then the stored text verbatim**
(for example `[partner]` + `\n` + text). A current-zone row (kind NULL) carries no tag: its
content is the stored text verbatim. The chat role is always the row's stored role.

## Commands

From the root `CLAUDE.md` (run from `backend/`):

```
test       .venv/Scripts/python -m pytest
typecheck  .venv/Scripts/python -m mypy app
lint       .venv/Scripts/python -m ruff check .
```

No step may leave `mypy app` or `ruff check .` failing.

## Architecture this binds to

- `docs/architecture/llm-and-streaming.md` "Context assembly — what the assistant reads":
  the system-prompt / messages shape; "The message list is the union of the two views";
  "Decisions are context like anything else"; "What must NOT be in context" (the
  exclusion table: the absences are the invariant); "Forced-memo selection: `is_enabled`
  gates first"; "Forced-memo order is part of this contract"; "The `(( ))` convention is a
  system-prompt responsibility"; "Two facts that follow from mutability"; "Language
  handling"; "No context compaction".
- `docs/architecture/domain-rules.md`: **R1** (configuration resolves through 017's
  resolver, never re-derived), **R2** (chain order; no-setup degrades with no gap),
  **R3** (`is_enabled` gates first; disabled reaches the assistant by no path),
  **R5** (owner scope), **R7** / **R11** (buried rows never reach the assistant; only the
  views read `messages`), **R8** (translations never enter context), **R12** (parse once
  at settle; never re-parse stored text).
- `docs/architecture/data-model.md` "### `messages`" (columns, the three states, the two
  views).
- `docs/architecture/backend-structure.md` "Layout" (`services/` and `services/llm/`).

Cited, never copied.

## Files this feature touches

```
backend/
  app/services/llm/chat.py        # NEW — the chat-message value type             (001)
  app/services/context.py         # NEW — renderer + mapper (001); assembler (002)
  tests/test_context_render.py    # NEW                                            (001)
  tests/test_context_assembly.py  # NEW                                            (002)
```

**Not touched. A step that touches one is out of scope:** every existing module under
`app/` (`db/schema.py`, `errors.py`, `services/messages.py`, `services/sessions.py`,
`services/characters.py`, `services/settle.py`, `services/parens.py`,
`services/llm/__init__.py`, `services/llm/client.py`, every router, `main.py`), every 015 /
016 / 017 / 019 module once built (`services/memos.py`, `services/memo_chain.py`,
`services/configuration.py`, `services/llm/frames.py`), `backend/tests/conftest.py`, every
existing test file, and the whole frontend. No new Python dependency.

## Cross-cutting constraints every step holds

**Assembly names no table.** `services/context.py` selects nothing itself. Every row it
sees comes from an existing owner-scoped service read: 012's two list reads (which go
through the `settled_entries` / `current_zone` views), 015's chain, 017's configuration,
011's session read and 009's character read. Buried rows are excluded by those views, not
by a predicate written here (R11).

**Stored text is never changed or re-parsed (R12).** The system prompt, the sheet, note
bodies and message texts enter verbatim. The only addition is the kind tag prefix on
settled rows (D1). Nothing classifies or strips `(( ))`; `services/parens.py` is not
imported.

**Nothing is cached.** Every call reads live (D11).

**No text in a log line.** 020 adds no logging.

**Synchronous.** Like every service, the assembler is sync and takes the connection first,
with `user_id` a required positional argument.

## Decisions — settled, with their reasoning

U1–U4 are user decisions confirmed for this feature; O-decisions are the orchestrator's;
the rest are planner decisions. All are binding.

### D1 — The record is presented as tagged chat messages (U1)

Every settled row stays a chat message with its **stored role** (`user` / `assistant`),
and its content is prefixed with a short kind tag (the Kind tags table). The system
prompt's "Message tags" section explains the tags. Current-zone rows carry no tag. The tag
is added at assembly; stored text is never changed (R12). Reason: a partner block and the
roleplayer's own turn are both `role='user'`, so without a tag the model cannot tell the
partner's words from the roleplayer's. A tag keeps the chat shape the provider expects.
The tag is followed by a line feed rather than a space so a multi-paragraph text keeps its
first line intact.

### D2 — Prompt parts: system prompt, sheet, forced notes, instructions (U2, O)

The system prompt carries exactly the six sections in the format table. **No setup
description** (the architecture's list has none), **no character name** (the sheet is the
persona), **no tool descriptions** (`021` passes enabled tools through the API `tools`
parameter). Tool switches resolved by 017 are not read by 020.

### D3 — Tool rows are skipped (U3)

`role='tool'` rows (written by `021`) are left out of the message list; only `user` and
`assistant` rows map. Any role other than `user` or `assistant` is skipped. `021` extends
the mapper with tool-row replay, because pairing a tool row with its tool-call id is
`021`'s seam. Recorded in `outcome.md`.

### D4 — A null language names English (U4)

When the resolved RP language or preferred language is null, the instruction names
**`English`** in its place. Nothing is refused and nothing raises. The two fall back
independently.

### D5 — Empty parts are omitted, never defaulted (O)

A null resolved system prompt omits section 1: no invented default persona. A character
sheet that is empty or whitespace only omits section 2 (the orchestrator said empty; a
whitespace-only sheet carries no content either, and a heading over nothing is noise). No
forced note anywhere omits section 3. The three instruction sections are always present,
so the system prompt is never empty.

### D6 — Forced-note selection reuses 015, with no second predicate (O)

The assembler takes the levels from 015's `resolve_chain` (fixed level order, `sort_key,
id` within a level, setup level present only when the session has one) and keeps a note
**only when 015's `memo_reach` of its two flags is `"forced"`**. It never writes its own
`is_enabled` / `is_forced` conjunction: R3 calls a hand-written copy the place the
disabled-and-forced bug comes back. The kept order is the chain's order, so a reorder on
the wall (016) changes the prompt (US-102.AC-1).

### D7 — The message list reuses 012's two reads, merged by id (O)

`messages.list_entries` (settled record) and `messages.list_zone` (current zone), both
owner-scoped, both through the views, merged and ordered by `id` (a snowflake is stream
order). A partner block can be filed while the zone holds rows, so the two lists can
interleave, hence the merge rather than concatenation. A `kind='decision'` row arrives
through the settled read like any other and needs no special case (US-122, UC-081).

### D8 — Configuration and the sheet come from existing reads (O, refined)

- Resolved system prompt and both languages: 017's `get_session_configuration` (R1: never
  re-derived here). Only `system_prompt`, `rp_language` and `preferred_language` values
  are used.
- The sheet: 011's `sessions.get_session` gives the session's `character_id`, then 009's
  `characters.get_character` gives the `sheet`. `get_session` runs **first**, so a missing
  or foreign session raises `SessionNotFoundError` before anything else is read.
- Archived sessions and characters assemble normally (R6: archive is not a lock).

### D9 — Module placement (O, accepted)

- `app/services/llm/chat.py` (new): the chat-message value type and its role literal. A
  neutral module so `021`'s client can import the type without importing the assembler.
- `app/services/context.py` (new): the renderer, the mapper and the assembler. Not in
  `backend-structure.md`'s layout; recorded in `outcome.md`.
- **Service-import exception, taken deliberately.** `context.py` imports read operations
  from five services (`sessions`, `characters`, `configuration`, `memo_chain`,
  `messages`) plus `llm/chat.py`. The no-import rule exists because a service operation
  owns its transaction (010 D6). The assembler opens **no transaction of its own** and
  only calls reads that leave none open, so the reason does not apply. It is a read
  composition, like `compose.py` will be. Recorded in `outcome.md`.

### D10 — Instruction texts are fixed English constants, tested by marker (O)

The instruction prose lives as fixed English constants in `context.py`. Tests bind to the
exact headings and lead-ins in the format tables and to the language names, never to the
prose after a lead-in. Rewording an instruction therefore breaks no test; removing one
does.

### D11 — Read live, no snapshot, no transaction of its own (O)

Every call re-reads everything: an edit to a settled or zone row, a memo flag flip, a
`sort_key` move or a character's prompt change between two calls shows in the second
(UC-029, US-110, US-115, UC-044, UC-076). The sub-reads are separate reads, not one
snapshot. A concurrent edit landing mid-assembly could yield a mixed view; with one
roleplayer per account that is accepted rather than paid for with an outer transaction
that the reused reads do not expect.

### D12 — No compaction: a deliberate absence

No pruning, no summarisation, no token count, no budget, no truncation of any text
(`vision.md` "No context compaction"; `llm-and-streaming.md` "No context compaction").
The whole record and the whole zone go through un-truncated. Tests may assert that a
large record arrives whole. This is a design fact, not a gap to fill.

### D13 — Two steps

| Step | Subject | Est. LoC | Depends on |
|------|---------|----------|------------|
| 001 | `llm/chat.py`; `context.py` pure part: forced-note level value, system-prompt renderer, message mapper | ~150 | none |
| 002 | `context.py` assembler: the result value and `assemble_context` | ~60 | 001; 015 `001`–`003`, 017 `001`–`003` built |

The orchestrator suggested three steps (renderer; mapper; assembler). The mapper alone is
about 35 lines, below the 50-line floor, so it joins the renderer: both are pure and share
no dependency on unbuilt code. The assembler stays separate although it is small, because
it is the only part that needs 015 and 017 built. Merging it would block the pure part on
them.

## Test conventions

Inherited from 012 / 015 / 017 (`context.md` "Test conventions"): pytest from `backend/`,
`conftest.py` untouched and no shared fixtures added, a file-local `engine` fixture doing
`schema.metadata.create_all`, file-local raw-insert helpers (`_insert_user`,
`_insert_character`, `_insert_session`, `_insert_message`, … as in
`tests/test_messages_service.py`), two users for isolation. Additions for 020:

- **Test names:** `test_<behavior>__S020_<SSS>_DoD<n>`.
- **Expected values come from this plan**: the format tables, the Kind tags table, D4's
  fallback. Never call the renderer or the mapper to compute an expectation in the
  assembler's tests.
- **Prompt assertions** find heading and lead-in lines by exact text (line starts), compare
  positions to assert order, and check verbatim user text as substrings. Bodies and texts
  used in one test are distinct strings so a substring cannot match the wrong item.
- **Absence** is asserted against the whole result: the system prompt **and** every
  message's content.

## Vocabulary

| Term | Means here |
|---|---|
| **assembled context** | the system-prompt string plus the ordered chat messages for one session |
| **record** / **settled row** | a row read through `list_entries` (`settled_entries` view): kind non-null |
| **zone row** | a row read through `list_zone` (`current_zone` view): kind NULL |
| **buried row** | a row pointing at a settled head (`related_to` set); in neither view |
| **forced note** | a memo whose `memo_reach` is `"forced"` (enabled and forced) |
| **kind tag** | the literal prefixed to a settled row's content (D1) |
| **lead-in** | the exact line start of one instruction rule (format table) |
