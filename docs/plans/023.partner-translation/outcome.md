# Feature 023 — Partner translation · intended documentation changes

Planner section: the doc changes the architect applies once 023 ships. Grouped by target
file. "Dn" are `context.md` decisions in this folder.

## `docs/architecture/data-model.md`

| Section | Intended change | Reason |
|---|---|---|
| `translations` | Replace the column line with the as-built set. Add `user_id` (FK `users.id`, NOT NULL), the owner column the list omitted. `message_id` is a FK with **no cascade**. `created_at` is Text in the fixed-width form. The unique constraint is named `uq_translations_message_id_target_language`. There is no `updated_at`, because rows are only inserted or deleted | D7 |
| `translations` | Record that the write is insert-or-ignore on the unique pair, and only if the message's current text still equals the translated text (no stale row after a concurrent edit) | D8, D9 |
| `translations` — invalidation `_TBD:` | As built: `edit_message_text` deletes the message's rows on **any** text change, inside the edit transaction. The `_TBD:` (non-partner edits, UC-029 vs UC-041) stays open for `/product-spec`. The design inference is now code | D11 |
| Export / import contract | Flag: decide whether `translations` rows are exported. They are a cache and are rebuildable on demand. This plan does not touch FEAT-018 | D7 |

## `docs/architecture/llm-and-streaming.md`

| Section | Intended change | Reason |
|---|---|---|
| Translation | As built: the call reuses `chat_stream` with **no tools**. Content deltas are joined, while reasoning and tool-call deltas are ignored. The call uses one system message (faithful translation into the target, output only the translation) and the stored text verbatim as the user message | D2, D8 |
| Translation | Add the **fallback**: no preferred language at any level → target `English`, held in one constant in `services/translation.py`. The cache key uses the effective target | D3 |
| Translation | A cache hit answers with **no** model resolution, so a cached translation still shows when the session's model is disabled. Only a miss runs 017's use-time check | D8 |
| Translation | Failure mapping: only a provider failure from `chat_stream`, or an empty result after the `<think>` strip, becomes `translation_failed`. 017's model errors and `secret_ref_missing` propagate under their own codes | D5 |
| Translation | Three phases. No connection or transaction is held across the provider await. The service takes the engine (021 `005` precedent) | D8 |
| The `<think>` convention (021 D4) | "Applied in exactly two places" becomes **three**: the translation result is also stripped before caching | D10 |
| Stopping a translation | As built: the probe is injected into the FastAPI-free service as an async callable and awaited once before the write. The log line gains ` written=false` when the write is skipped | D4 |

## `docs/architecture/workspace-shell.md`

| Section | Intended change | Reason |
|---|---|---|
| The stop control | **Deviation to reconcile:** the composer's `IconPlayerStop` does **not** reach a translation. A pending translation is cancelled by its own flicker, which reads "Cancel translation" while pending. The user chose this. Reword "reaching any model work in flight … or a partner-text translation", and the "Realizes" line, accordingly. The second consequence bullet (original showing, un-flicked) holds as written | D4 |
| The stream — the settled record | Partner actions as built: the flicker (`IconLanguage`) sits beside Edit in the same revealed actions group. The body switches between original and translation, and the editor always edits the original. A partner entry still has no copy (014 D7) | D15 |

## `docs/architecture/ui-conventions.md`

| Section | Intended change | Reason |
|---|---|---|
| Icon table notes — `IconLanguage` `_TBD:` | **Close it:** one icon. The state is carried by the **label**: "Show translation", "Cancel translation" (pending) and "Show original". The label is also the tooltip and `aria-label`. The state also shows in a distinct colour while translated. No `aria-pressed`, because a toggle whose name changes must not also be pressed-state. `IconButton`'s props are not widened | D15 |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| Layout | Add `routers/translation.py` (the one translate route) and `models/translation.py`. `services/translation.py` is as listed | D12 |
| The per-code status record | `translation_failed` → **502** (introduced by plan 023): a dependency's failure, like `llm_unreachable` | D5 |
| Route surfaces | Add `POST /api/messages/{message_id}/translation`: an `async def` handler, router-level `require_user`, its own overridable chat-client factory dependency, no request body, and the 200 `{message_id, target_language, text, cached}` shape | D12 |
| Routers versus services | Record `services/translation.py`'s imports (`configuration`, `llm_registry`, `llm.chat`, `llm.client`) as a deliberate exception of the 021 D15 kind. Record that `services/messages.py` deletes from `translations` in the edit transaction | D8, D11 |

## `docs/architecture/frontend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| State — MobX 6 / store files | Add `app/translationState.ts`: one `TranslationState` per `SessionStream` mount, with free-function effects (flick, cancel, invalidate, dispose) | D13 |
| State | **Accepted limitation:** the client cache is keyed by message id for one mount. A preferred-language change mid-mount keeps showing the old-language translation until the stream remounts | D13 |
| The API client | Add `app/translationApi.ts` `translateMessage`, and `translation_failed` to the codes the UI meets. It is shown through `notifyFailure`, with no branch | D5 |

## `docs/architecture/deployment.md`

| Section | Intended change | Reason |
|---|---|---|
| The redaction rule — allowed shapes | The as-built translate line is `translate cached=<bool> message=<id> ms=<n>`, plus ` written=false` when skipped, plus a `translate failed … code=translation_failed` line. There is no `status=` field: the service has no HTTP status | D4, `002.context.md` |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Typed errors | `translation_failed` at 502 | D5 |
| Doc map / paths | Add the translate route and the three new backend modules | D12 |
| Open `_TBD:` table | Remove the `ui-conventions.md` `IconLanguage` row and add it to "Closed in this pass" | D15 |

## Flags for other owners

- **`/product-spec` — English fallback conflict.** `docs/product/features.md`'s FEAT-013
  note says English is "merely the common case, never the rule". The user chose a literal
  `English` fallback for translations when no preferred language resolves (D3). Please
  reconcile: either amend the note, or state the fallback as a FEAT-011 rule.
- **`/product-spec` — US-133.AC-2 / UC-085.** "Nothing is cached" remains best-effort (the
  named divergence, unchanged). The stop for a translation is the flicker's cancel, not
  the composer's stop control (D4). If UC-085 / US-133 wording implies one stop control
  for all model work, it needs amending.
- **`/product-spec` — `data-model.md` `_TBD:`** on discarding translations when a
  non-partner settled row is edited is still open. The build deletes on any edit (D11).
- **021:** its D4 "exactly two places" statement is now three (D10).

## Observations

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B1 (the backend spine — `session-stream.md`, `transfer.md`, `backend-structure.md`, `data-model.md`, `domain-rules.md`), B2 (the LLM/search/operations layer — `llm-and-streaming.md`, `search-and-retrieval.md`, `deployment.md`, `admin-surfaces.md`, `overview.md`) and B3 (the frontend layer — `workspace-shell.md`, `frontend-structure.md`, `ui-conventions.md`, `forms-and-lists.md`).
Rejected items: Its "named divergence unchanged" status note is rejected (as 019's and 021's).
Notes: The English-fallback conflict it raised for `/product-spec` is discharged by `US-142`, and its `data-model.md` translation-invalidation `_TBD:` is closed rather than carried — `US-111.AC-3` now requires what the build does. The stop-control deviation is recorded as design in both `llm-and-streaming.md` and `workspace-shell.md`, whose sentence claiming the composer's Stop reaches a translation is corrected and FEAT-011 removed from that section's `Realizes:` line.
