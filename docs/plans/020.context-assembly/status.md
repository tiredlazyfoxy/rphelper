# Feature 020 — context-assembly

| Step | File                         | Status  | Verifier | Date |
|------|------------------------------|---------|----------|------|
| 001  | `001.render-and-map.md` | done    | PASS     | 2026-10-04 |
| 002  | `002.assemble-context.md` | done    | PASS     | 2026-10-04 |

## Files Changed

### Step 001 — Chat value type, system-prompt renderer, message mapper
- `backend/app/services/llm/chat.py` — `ChatRole` / `ChatMessage` (skeleton already complete; no body change)
- `backend/app/services/context.py` — instruction-line constants; `render_system_prompt` and `to_chat_messages` bodies

### Step 002 — The assembler: `assemble_context`
- `backend/app/services/context.py` — `from app.services import characters, configuration, memo_chain, messages, sessions`; `assemble_context` body (session → configuration → character → chain filtered by `memo_reach == "forced"` → list_entries/list_zone → render + map)

## Skeleton

### Step 001 — frozen interface (2026-10-04)
- `backend/app/services/llm/chat.py` — `ChatRole = Literal["user", "assistant"]` — new
- `backend/app/services/llm/chat.py` — `@dataclass(frozen=True) class ChatMessage: role: ChatRole; content: str` — new
- `backend/app/services/context.py` — `ForcedNoteScope = Literal["user", "character", "setup", "session"]` — new
- `backend/app/services/context.py` — `@dataclass(frozen=True) class ForcedNoteLevel: scope: ForcedNoteScope; bodies: Sequence[str]` — new
- `backend/app/services/context.py` — `render_system_prompt(system_prompt: str | None, sheet: str, forced_levels: Sequence[ForcedNoteLevel], rp_language: str | None, preferred_language: str | None) -> str` — new (stub raises `NotImplementedError`)
- `backend/app/services/context.py` — `to_chat_messages(entries: Sequence[StreamMessage], zone: Sequence[StreamMessage]) -> list[ChatMessage]` — new (stub raises `NotImplementedError`); `StreamMessage` from `app.services.messages`
- `backend/app/services/context.py` — module constants (exact literals from `context.md`; names are not a test contract, D10): `HEADING_SYSTEM_PROMPT`, `HEADING_CHARACTER_SHEET`, `HEADING_FORCED_NOTES`, `HEADING_MESSAGE_TAGS`, `HEADING_LANGUAGES`, `HEADING_DOUBLE_PARENTHESES`, `LEVEL_HEADINGS: dict[str, str]` (scope -> `--- X notes ---`), `NOTE_MARKER = "[note]"`, `KIND_TAGS: dict[str, str]` (kind -> tag), `FALLBACK_LANGUAGE = "English"`. Instruction lead-in lines and their prose are the coder's to add as constants.
- Caller-compile edits (out of Source-files scope): None.

### Step 002 — frozen interface (2026-10-04)
- `backend/app/services/context.py` — `@dataclass(frozen=True) class AssembledContext: system_prompt: str; messages: Sequence[ChatMessage]` — new
- `backend/app/services/context.py` — `assemble_context(connection: Connection, user_id: int, session_id: int) -> AssembledContext` — new (stub raises `NotImplementedError`); `Connection` from `sqlalchemy`; raises `SessionNotFoundError` (`app.errors`) per intent
- Imports added: `from sqlalchemy import Connection` only. The coder adds the `app.services` imports (`sessions`, `characters`, `configuration`, `memo_chain`) as modules; `get_character` was confirmed to return archived characters (DoD-12 gotcha clear).
- Caller-compile edits (out of Source-files scope): None.

## Tests

### Step 001 — tests (2026-10-04)
- `backend/tests/test_context_render.py` — covers DoD-1 — `ChatMessage` holds both roles + content; field assignment raises
- `backend/tests/test_context_render.py` — covers DoD-2, DoD-3, DoD-10 — six headings as whole lines in order; system prompt / sheet verbatim inside their own section; null prompt and empty / whitespace sheet omit only their heading; minimal prompt starts with `=== Message tags ===` and holds exactly the three instruction headings
- `backend/tests/test_context_render.py` — covers DoD-4, DoD-5 — level headings in given order, bodies verbatim in order after a `[note]` line; empty levels unheaded; no-setup with session directly after character; empty / all-empty sequence omits `=== Forced notes ===`
- `backend/tests/test_context_render.py` — covers DoD-6, DoD-7, DoD-8, DoD-9, DoD-11 — lead-in lines after their section heading; language names and independent `English` fallback; no tool names for any inputs
- `backend/tests/test_context_render.py` — covers DoD-12..DoD-16 — kind tags + stored role, untagged zone rows, id merge across lists (incl. empties), `tool` rows skipped, verbatim `(( ))` / whitespace, 2,000 rows with a 200,000-char text whole
- `backend/tests/test_context_render.py` — covers DoD-17 — AST import checks on `llm/chat.py` (nothing from `app.services`) and `context.py` (no `parens`, no `fastapi`), no `translation` substring
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓, DoD-17 ✓

### Step 002 — tests (2026-10-04)
- `backend/tests/test_context_assembly.py` — covers DoD-1 — `AssembledContext` returned; `"P"` / `"S"` as the line after their headings; six headings in order with lead-ins after their sections; four forced bodies after `[note]` under their level headings in level order; `messages` equals the exact tagged-record-then-zone list
- `backend/tests/test_context_assembly.py` — covers DoD-2, DoD-3, DoD-4, DoD-5 — disabled-forced / disabled / searchable bodies absent at every level; level order then `sort_key`, `id` (tie, out-of-order inserts, user sort_keys larger than session's); `sort_key` swap reorders on the next call; no-setup session has no setup heading and drops a same-character setup note
- `backend/tests/test_context_assembly.py` — covers DoD-6, DoD-7, DoD-8 — buried rows absent (empty zone and newer zone row); other user's memos at the session's scopes, sibling session's rows/notes and other character's notes absent; foreign and unknown session ids raise `SessionNotFoundError`
- `backend/tests/test_context_assembly.py` — covers DoD-9, DoD-10, DoD-11, DoD-12 — raw edits (row texts, character prompt, `is_enabled`) show on the second call; session prompt beats character's, none omits the section; Japanese / Russian / French override / `English` fallback on the `- Candidates:` and `- Out of character:` lines; empty sheet omits its heading; archived session + character assemble
- `backend/tests/test_context_assembly.py` — covers DoD-13, DoD-14, DoD-15 — `tool` zone row skipped, interleaved settled/zone order kept; 300 settled rows incl. a 100,000-char text plus zone rows arrive whole in id order; no open transaction after success and after `SessionNotFoundError`, `messages` / `memos` unchanged
- `backend/tests/test_context_assembly.py` — covers DoD-16 — AST: no `app.db` / `fastapi` import, only `Connection` from `sqlalchemy`, no `select`/`insert`/`update`/`delete`/`text` call (AST, since `assemble_context(` contains the substring `text(`), `app.services` imports exactly the six, every `is_enabled`/`is_forced` access inside `memo_reach(...)` arguments; substring check for `settled_entries`, `current_zone`, `translation`
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓, DoD-17..DoD-20 [manual/live, no test]

## Notes & Issues

_populated by the coder when worth saying_

## Ultra phase

- orient: done 2026-10-04
- policy 2026-10-03 (user): mechanical knock-on test amendments outside a step's Test files are approved deviations, recorded under that step's ## Tests.
- harvest: done — docs/.cache/ultra/020.context-assembly/harvest.md (1 report)
- skeleton: done — steps 001, 002
- tests: done — steps 001, 002
- red-gate: PASS (run 1)
- code: done — steps 001, 002
- verify: FAIL (run 1) — 002 TEST (DoD-14 final assertion expects the wrong kind tag)
- verify: PASS (run 2)
