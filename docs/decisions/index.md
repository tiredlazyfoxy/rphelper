# Decision index

Registry of every `DEC` id. Regenerated from the entries on every write — never
edited independently of the files (`CLAUDE.md`).

| Id | Title | Status | Feature | Stage |
|---|---|---|---|---|
| DEC-034-1 | The rename body's `name`: a required key, string or null, normalised on both sides | accepted | 034.session-names | — |
| DEC-034-2 | `extra="forbid"` on the rename request model: the one named exception | accepted | 034.session-names | — |
| DEC-034-3 | No length cap on a session name | accepted | 034.session-names | — |
| DEC-034-4 | `sessions.name` is a privacy-audit content carrier; the rename route is an owner route | accepted | 034.session-names | — |
| DEC-034-5 | The name is not part of the embedded session text; a rename embeds nothing | accepted | 034.session-names | — |
| DEC-034-6 | `RpSession.name` defaults to None and is declared last | accepted | 034.session-names | — |
| DEC-034-7 | The version-1 upgrade: the deserializer learns the file's version; only `sessions.name` may be absent | accepted | 034.session-names | — |
| DEC-034-8 | My-search wire keys and hydration: session hit `name`, entry hit `session_name`; name hits by name then id | accepted | 034.session-names | — |
| DEC-034-9 | The client label module: `sessionLabel`, a local-date fallback, `formatLocalDateTime` | accepted | 034.session-names | — |
| DEC-034-10 | Rename affordances: an `IconEdit` button on every tree session row and beside the header title | accepted | 034.session-names | — |
| DEC-034-11 | Rename editor semantics: unchanged sends nothing, one in flight, inline failure, apply the returned row | accepted | 034.session-names | — |
| DEC-034-12 | `applySession` orders `last_used_at` ties by id descending | accepted | 034.session-names | — |
| DEC-034-13 | The character page's Sessions list follows the workspace store by the apply-a-row rule | accepted | 034.session-names | — |
| DEC-034-14 | The workspace `SessionsState` is threaded to the session screen as a prop | accepted | 034.session-names | — |
| DEC-F014-1 | Build single-message delete now; the docs follow at finalization | accepted | fast/014.message-delete | — |
| DEC-F014-2 | Settled entries and current-zone messages are both deletable | accepted | fast/014.message-delete | — |
| DEC-F014-3 | A settled head takes its buried group with it, in the same transaction | accepted | fast/014.message-delete | — |
| DEC-F014-4 | The trash control confirms in red; a blank editor commit does not | accepted | fast/014.message-delete | — |
| DEC-F014-5 | Delete refusals mirror edit's — no new error code | accepted | fast/014.message-delete | — |
| DEC-F014-6 | 200 with `{deleted_ids, search_coverage_incomplete}`, not 204 | accepted | fast/014.message-delete | — |
| DEC-F014-7 | The service's order inside one transaction | accepted | fast/014.message-delete | — |
| DEC-F014-8 | Full-text upkeep follows the memo delete's placement | accepted | fast/014.message-delete | — |
| DEC-F014-9 | Frontend delete effects: never optimistic, never rejecting, never setting busy | accepted | fast/014.message-delete | — |
| DEC-F014-10 | A blank edit commit delegates to delete; unchanged text is a no-op | accepted | fast/014.message-delete | — |
| DEC-F014-11 | Trash icon placement, labels and gating | accepted | fast/014.message-delete | — |
| DEC-F014-12 | What single-message delete deliberately does not do | accepted | fast/014.message-delete | — |
| DEC-F014-13 | The trash control's disabled condition, and its untested half | accepted | fast/014.message-delete | — |
| DEC-F015-1 | Build the pending indicator in code; no product or architecture change now | accepted | fast/015.translate-pending-indicator | — |
| DEC-F015-2 | While pending, the flicker's glyph is a spinning loader instead of the language icon | accepted | fast/015.translate-pending-indicator | — |
| DEC-F015-3 | Label and accessibility semantics are unchanged while pending | accepted | fast/015.translate-pending-indicator | — |
| DEC-F015-4 | An entry's actions group is revealed while that entry's translation is pending | accepted | fast/015.translate-pending-indicator | — |
| DEC-F016-1 | Build the own-text tone in code; no product or architecture change now | accepted | fast/016.own-text-muted | — |
| DEC-F016-2 | The user-role row body is wrapped in a Mantine `Box` with `c="dimmed"` | accepted | fast/016.own-text-muted | — |
| DEC-F016-3 | Settled entries, the live reply and accent chips keep their colours | accepted | fast/016.own-text-muted | — |
| DEC-F016-4 | Test hook: `data-tone="muted"` on the wrapper | accepted | fast/016.own-text-muted | — |
| DEC-arch-session-names-1 | Name storage: a nullable column, the default label computed by the client | accepted | arch-session-names | — |
| DEC-arch-session-names-2 | Route shape: a general `PATCH` that accepts `name` only | accepted | arch-session-names | — |
| DEC-arch-session-names-3 | Last-use display: local `YYYY-MM-DD HH:MM`, fixed width | accepted | arch-session-names | — |
| DEC-arch-session-names-4 | Rename interaction: in-place edit of the label | accepted | arch-session-names | — |
| DEC-arch-session-names-5 | My-search's session name arm: `LIKE`, merged ahead of vector hits | accepted | arch-session-names | — |
| DEC-arch-session-names-6 | A rename bumps `updated_at` only | accepted | arch-session-names | — |
| DEC-arch-session-names-7 | Import accepts `schema_version` 1 through one named upgrade | accepted | arch-session-names | — |
