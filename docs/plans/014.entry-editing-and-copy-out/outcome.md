# Feature 014 — Entry editing and copy-out · outcome

Intended changes to `docs/architecture/` once this feature ships, for the architect to
apply at finalization. Grouped by target file. Decisions referenced as D-n are in this
folder's `context.md`; "012 Dn" / "013 Dn" are in those plans' `context.md`.

## `docs/architecture/ui-conventions.md`

| Section | Intended change | Reason |
|---|---|---|
| "Async feedback" — the rule and "The mechanism — one outlet, one call site" | Add a **third class** beside success (none) and failure: a **warning** — a transient notice that is neither success nor failure, raised through **`shared/notifyWarning`**, the **second sanctioned importer** of `@mantine/notifications`. It takes an identifier from a **closed set** (no free text, no colour, no timeout), so a success message still cannot be expressed; the outlet's `autoClose: 5000` applies; colour yellow. Its only user is the enormous-paste context-cost warning (US-035.AC-1). Record that `tests/conventions.test.ts` pins the importer set to exactly the two files (D4, user decision). | The doc says `notifyFailure` is the only way anything raises a notification. |
| Icon table — "Copy settled turn out" | Record the label **"Copy as plain text"**, on `turn` entries only (D7). The row "Copy as plain text (composer)" names a composer copy that no plan has built — mark it `_TBD:` or remove it, per the architect's reading. | As built; a composer copy is not in any brief. |
| Notes — the `IconCopy` paragraph | Add: absent on `partner` too (D7); the copy reads the stored text and strips by `app/plainText.ts`; on a non-secure origin it falls back to `execCommand("copy")` (D9); a clipboard failure goes through `notifyFailure`; success raises nothing. | As built. |
| Icon table — "Edit entry, message or note" | Record the settled entry's labels "Edit entry" / "Edit entry text", distinct from the zone's "Edit message" / "Edit message text" (013) (D10). | Two labels for one glyph, recorded so they are not merged. |

## `docs/architecture/workspace-shell.md`

| Section | Intended change | Reason |
|---|---|---|
| "The stream — the settled record" — the kinds / actions table | `partner` row: actions **edit** (and translate, FEAT-011) — **no copy**. Keep `turn`: edit, copy as plain text; `decision`: edit only (D7, user decision). | The table lists copy on partner; US-033 / UC-030 / UC-082 speak of the roleplayer's own answer. |
| Same section — "revealed on `:hover` **or** `:focus-within`" | Record the mechanism as built: **Mantine hooks, not CSS** — `useHover` + `useFocusWithin` (merged refs) + `useMediaQuery("(hover: none)")` for touch, applied as an **opacity** style prop so hidden controls stay in the DOM and the tab order, and tabbing into an entry reveals them. Re-open sits in the same group. No stylesheet selector exists for it (`tests/stylesheets.test.ts`) (D6, user decision). | The doc names CSS pseudo-classes the two-stylesheet rule cannot host. |
| Same section — "Editing is in place and saves on focus loss" | Record as built: "Edit entry" swaps the body for an autosizing plain textarea; blur commits; blank / unchanged sends nothing; the `PATCH` response replaces the one row; failure keeps the editor open with the typed text and re-reads the entries; an edit never re-parses `(( ))` and never changes `kind` (D1, D10). | As built. |
| Same section — "Copy yields plain text" | Point to `app/plainText.ts` as the one stripper and summarise its rule set: CommonMark as rendered without plugins (GFM left as typed), syntax removed, words and line breaks kept, unordered bullets → `• `, ordered numbers kept; the authoritative rules live in plan 014 `002.context.md` until the architect lifts them (D8). Record the consequence that asterisk-marked RP actions lose their asterisks under US-124.AC-1. | Location and scope of the stripping were unstated. |
| "The kind switch and settle" — partner bullet, or a new short paragraph | Record the enormous-paste warning: composer pastes in both positions, non-blank text over **32,000 estimated tokens (characters ÷ 4, i.e. over 128,000 characters)**, a yellow `notifyWarning`; never prevents, delays or alters the paste or the filing; editor pastes do not warn (D3, D5). | US-035.AC-1's mechanism had no location. |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| "The stream routes" — "`PATCH /api/messages/{message_id}` spans both views on purpose" | Record as built (plan 014): the service classifies through `message_states`; a settled row of any kind is edited (text and `updated_at` only — `kind`, `settled_at`, `related_to` never written) and read back through `settled_entries`; a zone row through `current_zone`; buried stays `message_not_editable`. Every accepted edit bumps the session (`last_used_at` + `updated_at`) (D1, D2). Remove any "until 014" wording carried in from 012's outcome. | 012 shipped the interim zone-only refusal. |
| "The two transaction rules" | Note that the degraded embedding path is still unbuilt after 014 — the edit is plain success / failure until `024` (US-112). | So the as-built state is not misread. |
| Error table — `message_not_editable` | Narrow its "when" to **buried rows only** (D1). | The settled-row case is gone. |

## `docs/architecture/domain-rules.md`

| Section | Intended change | Reason |
|---|---|---|
| R10 — the enormous-paste sentence | Record the threshold and its location: a client-side estimate of characters ÷ 4 against **32,000 tokens**, in `app/pasteCost.ts` (two named constants); advisory only, so its imprecision is harmless — nothing is refused (D3, user decision). Flip condition: a real tokenizer reaches the client, or the threshold proves too eager / too late in use. | R10 says "warned" without saying when. |
| R11 — "Raw `messages` is touched by exactly two operations" | Fold into 012's requested rewording (012 D16): the burial and settle columns are written only by settle / re-open; `PATCH` writes `text` / `updated_at` on zone **and settled** rows (D1). | 014 widens the update's reach. |
| R12 — the "an edit to it is taken literally" sentence | Add: the server keeps `kind` and `settled_at` on an edited row, and the client renders by kind, so an edit can never turn a turn into a decision or back (D1). | As built. |

## `docs/architecture/frontend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| "Where a store's file lives" / module list | Add `app/plainText.ts` (pure stripper), `app/pasteCost.ts` (pure estimate), `app/copyOut.ts` (the one clipboard writer), `shared/notifyWarning.ts`; `streamState.ts` gains `editEntry` (D4, D8, D9, D10). | New modules. |

## `docs/architecture/deployment.md`

| Section | Intended change | Reason |
|---|---|---|
| "TLS — none" | Add a consequence: `navigator.clipboard` does not exist on a non-secure origin, so copy-out uses an `execCommand` fallback on any LAN-address access; when TLS lands the fallback becomes dead code (D9). | The HTTP-only posture now has a visible feature consequence. |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Paths / frontend modules | Add `app/plainText.ts`, `app/pasteCost.ts`, `app/copyOut.ts`, `shared/notifyWarning.ts`. | Dense index. |
| Error codes | `message_not_editable` — buried rows only (D1). | Dense index. |
| Invariants / constants | Paste warning: > 32,000 estimated tokens (chars ÷ 4) (D3). | Dense index. |

## Forward notes (not architecture changes; for the owning plans)

- **`020` (context assembly):** US-032.AC-2 needs no 014 work — the edit overwrites
  `messages.text` and assembly reads `settled_entries`; nothing caches entry text.
- **`023` (partner translation):** US-111 hooks the partner-edit path — `PATCH` on a
  `kind='partner'` row is now accepted (D1), so the translation-cache discard belongs in
  the same `edit_message_text` transaction.
- **`024` (embedding lifecycle):** the settled-edit success path in `edit_message_text` is
  where re-index and the `no_embedding_model` degradation (US-112) attach; the
  coverage banner sits above `StreamRecord`. The client's `editEntry` will need to read a
  degraded-success signal from the `PATCH` response.
- **`022` (buried groups):** buried rows remain refused by `PATCH`; the read-only
  rendering is `022`'s.
- **Product follow-up, if wanted:** US-124.AC-1 strips asterisk-marked RP actions (D8);
  keeping them would be a change to US-124, not to this plan.

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B1 (the backend spine — `session-stream.md`, `transfer.md`, `backend-structure.md`, `data-model.md`, `domain-rules.md`), B3 (the frontend layer — `workspace-shell.md`, `frontend-structure.md`, `ui-conventions.md`, `forms-and-lists.md`), and the `deployment.md` item in B4.
Rejected items: The icon row "Copy as plain text (composer)" was removed outright rather than carried as a `_TBD:` — no plan built a composer copy and no brief contains one.
Notes: The `deployment.md` clipboard consequence (`navigator.clipboard` is absent on a non-secure origin, so copy-out falls back to `execCommand`, dead code once TLS lands) was orphaned by the orchestrator's batching and applied in B4.
