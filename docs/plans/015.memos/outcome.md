# Feature 015 — Memos · outcome

Intended changes to `docs/architecture/` once 015 ships, for `/architect` to apply at
finalization. Grouped by target file. Decision ids (Dn) refer to this feature's
`context.md`. Requirements are cited, not restated.

## `backend-structure.md`

- **"Layout"** — add `routers/memos.py`, `services/memos.py` and `services/memo_chain.py`
  as built; `models/memos.py` beside them. *Reason:* the files exist (D9, D11).
- **The route surface (wherever the per-feature route lists live)** — record the memos
  wire contract from `context.md` "Wire contract — memos": `GET /api/memos?scope&scope_id`,
  `POST /api/memos` (201; flags ignored, created enabled / not forced), `PATCH
  /api/memos/{memo_id}` (any subset of `body`, `is_enabled`, `is_forced`; a `null` key is
  not supplied), `DELETE /api/memos/{memo_id}` (204), `GET
  /api/sessions/{session_id}/memo-chain` (three or four levels in fixed order). The
  nine-key `Memo` shape, `scope_id` null for the user level, `user_id` never on the wire.
  *Reason:* the contract 016, 017, 018, 020 and 026 build on.
- **"Routers versus services"** — record that routers group **by feature, not by path
  prefix**: the chain route lives in `routers/memos.py` though its path starts
  `/api/sessions/` (D9). Record the **one narrow service-to-service import**:
  `memo_chain.py` imports only `Memo` and the row mapper from `services/memos.py`, never an
  operation (D11), and the reason (one value type for one row shape; the no-import rule
  protects transaction ownership, which a pure mapper does not touch). *Reason:* otherwise
  the next reader "fixes" it in one direction or the other.
- **"The error model" / "The per-code status record"** — add **`memo_not_found` → 404**,
  empty `detail`, raised for a missing **or another user's** memo on PATCH / DELETE (D12,
  R5). Record that a missing or foreign *target level* reuses `character_not_found` /
  `setup_not_found` / `session_not_found`, and that blank body, unknown scope and a missing
  `scope_id` are plain 422s with no domain code. *Reason:* new code.
- **"The two transaction rules"** — forward note for `024`: memo create and body edit gain
  the embedding in the same transaction, and both routes then gain a
  `no_embedding_model` failure; **deleting a memo must delete its `memo_vec` and
  `memo_fts` rows in the same transaction** (D2). *Reason:* 015 introduces the delete that
  024 must extend.

## `data-model.md`

- **"### `memos`"** — record the as-built table (D10): ten columns, no `title` /
  `archived_at` / `state`; `scope` constrained by a CHECK over the four values (the
  `users.role` non-native-Enum form, with the reasoning that the four scopes **are** R2's
  chain and a fifth is an architecture change); `scope_id` with no FK; one non-unique
  index on `(user_id, scope, scope_id, sort_key)`. A user-level note stores `scope_id` =
  its owner's id. *Reason:* the doc names the columns but not these choices.
- **"### `memos`" — `sort_key` allocation** — a new note gets
  `COALESCE(MAX(sort_key), -1) + 1` over the owner's notes at the same
  `(user_id, scope, scope_id)`, inside the create transaction; lists order by
  `sort_key, id`; gaps left by deletes are harmless; **no unique constraint**, because
  `016`'s reorder rewrites a level's whole order as 0..n-1 in one transaction and a
  unique index would collide mid-rewrite (D4). *Reason:* closes brief open question 1;
  016 binds to it.
- **"### `memos`" — removal** — memos are removed by **explicit delete**
  (`DELETE /api/memos/{id}`), the only removal they have, and it is a hard delete.
  Contrast with R6 stated here as well: characters, setups and sessions never delete
  because they archive; memos have no archive state, so delete is their removal (D2).
  *Reason:* the doc currently says nothing about how a memo goes away.
- **"### `memos`" — the orphan-scope check** — the paragraph names "the feature that
  creates `memos`" as the owner. **015 did not build it** (D3, user decision); the
  ownership is open again and needs placing by `/roadmap` or `/architect`. Orphans cannot
  arise yet (nothing that a memo scopes to is ever deleted, R6; create validates the
  target). *Reason:* the doc's owner reference is now wrong.
- **"`translations`, `messages`, `memos` and the archive rule"** — confirm as built:
  archiving a character, setup or session changes nothing on its notes, and an archived
  parent is a valid target for list, create and chain (D8).

## `domain-rules.md`

- **R6, the contrast paragraph** — add one sentence: memos' removal is an explicit delete
  (D2), which does not contradict R6 because R6 governs the three archivable entities and
  memos are outside it by R6's own contrast. *Reason:* the first delete path in the
  product sits next to a rule that reads "no delete path at all".
- **R3** — note the as-built twin derivations `services/memo_chain.py` `memo_reach` and
  `app/memoReach.ts`, both testing `is_enabled` first, as the place 020 and 026 should
  reuse rather than re-derive (D7). *Reason:* R3 calls the disabled-plus-forced ordering
  the single most important thing to get right; naming the one implementation helps.

## `ui-conventions.md`

- **The icon table, "Note enabled / disabled"** — the `_TBD:` is **closed provisionally**
  by D14: `IconCircleCheck` while enabled, `IconCircleOff` while disabled (the mockup's
  "circle with a slash"), labels "Disable note" / "Enable note" naming the action. The
  architect records this pair or replaces it. Also record the forced control as one
  `IconPin` whose state is carried by the button's colour and the label ("Force note" /
  "Stop forcing note"). *Reason:* the `_TBD:` needs a decision of record.
- **"Async feedback" / "Mutations are never optimistic"** — record 015's pattern for
  in-place editing as a precedent: per-item inline failures, no notification, and the
  apply-a-row rule (a returned row is applied only if its `updated_at` is not older than
  the held one) for items with concurrent writes (D5). *Reason:* 016's wall cards and any
  later in-place editor need the same rule.

## `workspace-shell.md`

- **"The wall's contents"** — record what 015 built and what it deferred: notes are
  edited in place and saved on focus loss (plus a flush on unmount, because blur is not
  reliably fired on removal); a blank new note is dropped with no request; **clearing a
  saved note deletes it** (D2); the unsaved new note shows no flag controls and no reach
  line (D13); the three reach statements' wording (D7), which describes forced and
  searchable behaviour that only exists once 020 and 026 land. **Deferred to 016:** moving
  focus into the new note's body on "New note" — `shared/MarkdownEditor` exposes no focus
  hook (D13). *Reason:* the wall inherits these behaviours.
- **"The character page"** — 015 adds a character-level "Notes" section after Sessions,
  using the same `MemoLevelGroup` and `MemoLevelState` as the session screen (D1). Forward
  for `018`: the card grid rearranges these components, it does not fork them.
- **Forward for `016`** — the wall's level cards reuse `MemoLevelState` / `MemoLevelGroup`
  (or wrap them); 016 moves the session screen's "Notes" section (`MemoChainSection`) into
  the wall column and adds the **reorder route**, which rewrites one level's `sort_key`s
  as 0..n-1 in one transaction (D4). Open question for 016, recorded so it is asked: the
  session screen's character level and the character page hold **separate** level states
  over the same rows, each loaded on mount (D16); whether the wall shares one is 016's
  call.

## `frontend-structure.md`

- **"Markdown"** — confirm `shared/MarkdownEditor` (TipTap WYSIWYG) is the notes' editor
  and its rendering is the live preview (US-056.AC-1). *Reason:* first use for notes.
- **Forward for `017`** — the settings screen mounts the **user level** with
  `MemoLevelGroup` over a `MemoLevelState("user", null)`; until then user-level notes are
  edited on the session screen's "Your notes" group (D1). *Reason:* closes brief open
  question 2.

## `llm-and-streaming.md`

- **"Forced-memo selection: is_enabled gates first"** — forward note for `020`: select
  `is_enabled AND is_forced` over the session's chain **in level order (user, character,
  setup when present, session), then `sort_key, id` within a level**; `resolve_chain`
  (`services/memo_chain.py`) already returns that order and degrades to three levels with
  no setup, and `memo_reach` is the derivation to reuse. *Reason:* 015 built the chain 020
  consumes.

## `search-and-retrieval.md`

- **`memo_search`** — forward note for `026`: the predicate is
  `is_enabled AND NOT is_forced` (`memo_reach == "searchable"`), over the chain's levels
  as `resolve_chain` resolves them, tested against a no-setup session (R2).
- **Embedding lifecycle** — forward note for `024`: memo create and body edit embed in one
  transaction with the row; a memo delete removes its `memo_vec` and `memo_fts` rows in
  the same transaction (D2).

## `quick-reference.md`

- **Error codes** — add `memo_not_found` (404).
- **Invariants / paths** — add the memos routes and `services/memo_chain.py` as R2's
  implementation site.

## Product flag — for `/product-spec`, not the architect

- **"Clearing all text of a saved note deletes it"** is a **plan-time user decision
  (2026-10-02)** with **no story behind it** (D2). `docs/product/` has no delete-a-note
  story and no criterion for how a note is removed. Raised so `/product-spec` can add a
  story (or rule otherwise) and the behaviour stops resting on a plan decision alone.
- **Also noted:** the "nothing persisted for an empty note" rule comes from
  `workspace-shell.md`, not from a `US-###.AC-#`; the brief lists it in scope. If the
  product layer wants it as a criterion, it has no id today.

## Observations

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B1 (the backend spine — `session-stream.md`, `transfer.md`, `backend-structure.md`, `data-model.md`, `domain-rules.md`), B2 (the LLM/search/operations layer — `llm-and-streaming.md`, `search-and-retrieval.md`, `deployment.md`, `admin-surfaces.md`, `overview.md`) and B3 (the frontend layer — `workspace-shell.md`, `frontend-structure.md`, `ui-conventions.md`, `forms-and-lists.md`).
Rejected items: Its `sort_key` allocation rule (`COALESCE(MAX(sort_key), -1) + 1`) is superseded by 016 D5/D6 and was not written anywhere.
Notes: The delete-a-note flag raised for `/product-spec` is discharged — `UC-088` and `US-141` now specify it, and the behaviour is recorded as realizing them rather than as a plan decision. The orphan-scope check is re-recorded as not built and unable to arise while no per-entity delete exists, with no owner assigned. On `sort_key`, 016 D5/D6 supersedes this plan's D4, so the rule of record is 016's and none of 015's is written.
