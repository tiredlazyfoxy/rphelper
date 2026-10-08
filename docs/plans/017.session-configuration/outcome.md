# Feature 017 — Session configuration · intended documentation changes

Planner section: the doc changes the architect applies once 017 ships. Grouped by target
file. "Dn" are `context.md` decisions in this folder.

## `docs/architecture/data-model.md`

| Section | Intended change | Reason |
|---|---|---|
| `characters` | Replace "`model_ref`, `system_prompt`, `tools`" with the as-built columns: `model_server_id` (id type, nullable, **no FK**), `model_name` (Text), named both-or-neither CHECK, `system_prompt` (Text, verbatim, blank stored as NULL), `tool_memo_search` / `tool_session_search` / `tool_web_search` (Boolean, nullable, no default). Keep the "no `rp_language` / `preferred_language`" paragraph unchanged | D4, D5, D6 |
| `sessions` | Replace the `model_ref` / `system_prompt` / `tools` rows with the same columns. Record `rp_language` / `preferred_language` as built (trimmed free text, blank = NULL, no language list) | D4, D5, D6 |
| `sessions` — encoding `_TBD:` | **Close it**: two columns, no FK (a deleted server must neither cascade into a session nor null its reference — the dead reference raises `model_not_enabled` at use, R4), both-or-neither CHECK. `model_ref` and `tools` as literal column names are deliberately absent | D4 |
| `sessions` — "no model enabled at creation" paragraph | **Close it**: the session is created with both columns NULL, which stay NULL until the roleplayer picks a model in the header. Nothing fills them later on its own. A character with a configured model is captured as-is even when nothing is enabled (US-139.AC-2) | D1 |
| `sessions` — capture paragraph | Add: the capture runs inside `start_session`'s one transaction after the character and setup checks. The character's pair is captured unvalidated. Otherwise the first enabled model (D7 order). Otherwise NULL. Prompt, tools and languages are never copied. Sessions created before 017 hold NULL (no backfill) | D1 |
| `characters` / `sessions` | Configuration is written only through the configuration routes. A character configuration write never touches a session row and never triggers the persona fan-out | D9, US-139.AC-1 |
| `users` | No change. Note that the user-settings write stamps `updated_at` in the fixed-width form | D11 |

## `docs/architecture/domain-rules.md`

| Section | Intended change | Reason |
|---|---|---|
| R1 | Name the two resolver functions as built (`resolve_assistant_chain(character, session)`, `resolve_language_chain(user, session)` in `services/configuration.py`), and that the per-level input shapes enforce the chains (the character input has no model and no language; the user input has only the two languages) | D8 |
| R1 | Add the tool rule: three independent nullable switches per level, NULL transparent, **a tool no level sets resolves to enabled** (level `default`) | D5 |
| R4 — creation `_TBD:` | **Close it** with D1 (NULL until picked, never filled silently), and record the use-time check order: no enabled model on the instance → `no_model_enabled`; NULL model → `model_not_chosen`; disabled → `model_not_enabled` | D1, D2 |
| R4 | Record that a captured model reports `level: "session"` in `model_not_enabled`, with D3's reasoning (the header picker is the only remedy; `character` would point to a screen that cannot reach this session) | D3 |
| R4 | Record set-time validation: a session or character model override is checked when set (409, nothing written) **and** at use. The session model is never cleared, only replaced | D10 |
| R4 | Flag for confirmation: D1's refinement of the orchestrator's user decision 1 against US-139.AC-2 | D1 |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| The error model — table | Add `no_model_enabled` (use-time: no model enabled on the instance; `detail` `{}`; FEAT-013, US-107) and `model_not_chosen` (use-time: the session has no model captured; `detail` `{}`; FEAT-013, UC-077) | D2 |
| The per-code status record | Add both at **409** (introduced by plan 017), with the same reasoning as `model_not_enabled`: well-formed request, conflicting registry / session state | D2 |
| The error model — `model_not_enabled` | Add that a captured session model reports `session`. `character` is reported only by the character configuration route's set-time check | D3, D10 |
| Layout / route surfaces | Add `routers/configuration.py` (seven routes, router-level `require_user`) and `services/configuration.py` (resolvers, reads, writes, `resolve_model_for_use`), and `models/configuration.py` | D13 |
| Routers versus services | Record the import exception: `services/sessions.py` and `services/configuration.py` import only `llm_registry`'s transaction-neutral reads, `ModelRefLevel`, `EnabledChatModel` and `UNSET`. Those reads are callable inside a caller's transaction | D12 |
| `GET /api/me` | Note: unchanged. User settings live at `GET` / `PATCH /api/me/settings` | D14 |
| Stream route table / 011's sessions surface | Note: `PATCH /api/sessions/{id}` still does not exist. Configuration is `…/configuration` | D9 |

## `docs/architecture/llm-and-streaming.md`

| Section | Intended change | Reason |
|---|---|---|
| The model registry and use-time validation | Record the **enabled set** (`is_enabled` and server exists, embedding designation irrelevant) and **first-enabled order** (`llm_servers.id`, then `models.id`, ascending, the LLM Servers page's order), used by the capture and by `GET /api/models` | D7 |
| Same | Record `resolve_model_for_use` (step 1 read + step 2 validate, with D2's order) as built **with no call site until `021`**, in the same posture as 006's validators | D2 |
| Same | Record that the system prompt and tool switches resolve live through `get_session_configuration`, which `020` / `021` consume | D8 |

## `docs/architecture/workspace-shell.md`

| Section | Intended change | Reason |
|---|---|---|
| The model picker | As built: `Select` "Model" in a header bar after the title row; options in first-enabled order labelled "name (server)"; a captured model that is not enabled shown as a disabled "(not enabled)" option; disabled "No model is enabled" with an empty list; a failed choice renders inline under the picker | D16 |
| The model picker | Tool indicators as built: three badges "<Tool>: on/off" from the resolved values. The gear (`IconSettings`) opens the session configuration modal (every setting with an explicit Inherit and its inherited value) | D16, D18 |
| The ruler and the current zone — US-107 bullet | As built: Send is disabled with a fixed reason only on *my turn*. Settle, partner filing and paste stay available. Unknown usability (loading / failed) never blocks. The backend refusal is `021`'s wiring | D17 |
| The user menu | Settings as built: `/settings` with a Languages form (on-page Save) and "Your notes" (`MemoLevelGroup`, not reorderable) | D15 |

## `docs/architecture/frontend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| Routing inside the `app` entry | `/settings` is built (`SettingsScreen`) | D15 |
| The API client | Add `no_model_enabled` and `model_not_chosen` to the codes the UI may branch on (the branch arrives with `021`). Record that 017 branches only on `model_not_enabled` (the picker's failure line) | D2, D16 |
| `model_not_enabled` presentation paragraph | Note that the dedicated presentation for a failed compose is `021`'s. 017 surfaces a dead captured model in the header picker and the Send gate | D16, D17 |

## `docs/architecture/ui-conventions.md`

| Section | Intended change | Reason |
|---|---|---|
| Create and edit are always a `Modal` | Record the settings page's Languages form as edited on the page with an explicit Save, like the character page's persona block: the route *is* the form (`frontend-structure.md`). Decide whether this is a third named exception or a reading of the existing ones | D15 |
| Icon table | `IconSettings` is now used for both the user-menu settings item and the session configuration gear, as the table already says | D16 |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Typed errors | Add `no_model_enabled` (409) and `model_not_chosen` (409) | D2 |
| Open `_TBD:` table | Remove the `data-model.md` (`sessions`) encoding row and the `domain-rules.md` R4 creation row; add both to "Closed in this pass" | D1, D4 |
| Doc map / paths | Add `routers/configuration.py`, `services/configuration.py`, `models/configuration.py`, and the roleplayer route `GET /api/models` | D13 |

## Flags for other owners

- **`/product-spec`**: D1 refines the orchestrator's user decision 1 so that US-139.AC-2
  holds when nothing is enabled. Please confirm. The UC-012 "user → character → session"
  wording flagged in R4 is still open and untouched by 017.
- **`018`**: the character configuration routes exist (`GET` / `PATCH
  /api/characters/{id}/configuration`, `model: null` clears). No frontend call exists yet
  (D20).
- **`020` / `021`**: consume `get_session_configuration` and `resolve_model_for_use`.
  `021` wires the latter into compose and renders `no_model_enabled` /
  `model_not_chosen` / `model_not_enabled`.

## Observations

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B1 (the backend spine — `session-stream.md`, `transfer.md`, `backend-structure.md`, `data-model.md`, `domain-rules.md`), B2 (the LLM/search/operations layer — `llm-and-streaming.md`, `search-and-retrieval.md`, `deployment.md`, `admin-surfaces.md`, `overview.md`) and B3 (the frontend layer — `workspace-shell.md`, `frontend-structure.md`, `ui-conventions.md`, `forms-and-lists.md`).
Rejected items: none
Notes: The flag asking `/product-spec` to confirm D1 against `US-139.AC-2` is discharged by `US-143`. The settings page's Languages form is recorded as a reading of the existing route-is-the-form exception, not as a third named exception.
