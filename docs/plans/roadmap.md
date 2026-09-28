# Roadmap

Status is derived from folder contents, never stored here: `brief.md` only =
roadmapped, `status.md` present = planned, `status.md` rows all `done` with
verifier `PASS` = delivered. See `docs/plans/CLAUDE.md`.

<!-- roadmap:start -->
## Stage 001.instance
**Goal:** the instance stands up and an administrator runs it.
**Exit criteria:** a fresh database is bootstrapped with a first administrator;
that administrator logs in, creates and disables accounts and resets
passwords, registers an LLM server and enables models including the embedding
designation, and sees and remediates per-table schema drift. No RP content
exists in the product yet.
**Not in it:** any roleplayer-facing surface; the `app` entry beyond its
scaffold; restoring from an export (UC-002); the vector-index rebuild
(UC-016), which has no vectors to rebuild until stage 004.

| Feature | Track | Size | Delivers | Depends on |
|---|---|---|---|---|
| `001.backend-foundation` | multi-step | M | — | — |
| `002.frontend-foundation` | multi-step | M | — | — |
| `fast/001.dev-and-container-harness` | fast | S | — | `001.backend-foundation`, `002.frontend-foundation` |
| `003.first-run-bootstrap` | multi-step | M | FEAT-001 | `001.backend-foundation`, `002.frontend-foundation` |
| `004.authentication-session` | multi-step | M | FEAT-002 | `003.first-run-bootstrap` |
| `005.admin-shell-and-users` | multi-step | M | FEAT-003 | `004.authentication-session` |
| `006.llm-server-connections` | multi-step | M | FEAT-004 | `005.admin-shell-and-users` |
| `007.schema-drift-and-remediation` | multi-step | M | FEAT-005 | `005.admin-shell-and-users` |

## Stage 002.record
**Goal:** a whole roleplay can be recorded by hand, with no assistant.
**Exit criteria:** a roleplayer logs in, creates a character and an optional
setup, starts a session, and builds the session's record by hand — partner
blocks, their own turns and decisions, added in any order, settled through
the ruler, edited in place afterwards and copied out — with standing notes
at all four levels on the note wall.
**Not in it:** the LLM in any form; search of any kind; translation; the
configuration chain; the character page.

| Feature | Track | Size | Delivers | Depends on |
|---|---|---|---|---|
| `008.app-shell-frame` | multi-step | M | FEAT-020 | `004.authentication-session`, `002.frontend-foundation` |
| `009.characters` | multi-step | M | FEAT-006 | `008.app-shell-frame` |
| `010.setups` | multi-step | M | FEAT-007 | `009.characters` |
| `011.rp-sessions` | multi-step | M | FEAT-008, FEAT-007, FEAT-020 | `009.characters`, `010.setups` |
| `012.messages-and-settle` | multi-step | M | FEAT-009, FEAT-010 | `011.rp-sessions` |
| `013.stream-and-zone-ui` | multi-step | M | FEAT-009, FEAT-010 | `012.messages-and-settle`, `008.app-shell-frame` |
| `014.entry-editing-and-copy-out` | multi-step | M | FEAT-009 | `013.stream-and-zone-ui` |
| `015.memos` | multi-step | M | FEAT-012 | `009.characters`, `010.setups`, `011.rp-sessions` |
| `016.note-wall` | multi-step | M | FEAT-012, FEAT-020 | `015.memos`, `008.app-shell-frame`, `013.stream-and-zone-ui` |

## Stage 003.assistant
**Goal:** the assistant composes the roleplayer's own reply.
**Exit criteria:** the configuration chain resolves model, system prompt,
tool switches and the two languages; the assistant streams a candidate into
the current zone and the roleplayer promotes, edits or overrides it and
settles; a settled discussion collapses and never reaches context again;
partner text translates on demand; any model work in flight can be stopped.
**Not in it:** the three tools' implementations (the dispatch seam exists,
unpopulated); any semantic or lexical search; export/import.

| Feature | Track | Size | Delivers | Depends on |
|---|---|---|---|---|
| `017.session-configuration` | multi-step | M | FEAT-013, FEAT-020 | `011.rp-sessions`, `006.llm-server-connections`, `009.characters` |
| `018.character-page` | multi-step | M | FEAT-020, FEAT-008 | `017.session-configuration`, `016.note-wall`, `013.stream-and-zone-ui` |
| `019.streaming-transport-and-stop` | multi-step | M | FEAT-010 | `006.llm-server-connections`, `013.stream-and-zone-ui` |
| `020.context-assembly` | multi-step | M | FEAT-010, FEAT-012 | `015.memos`, `017.session-configuration`, `012.messages-and-settle` |
| `021.compose-loop-and-tools` | multi-step | M | FEAT-010 | `019.streaming-transport-and-stop`, `020.context-assembly` |
| `022.discussion-ui` | multi-step | M | FEAT-010 | `021.compose-loop-and-tools`, `013.stream-and-zone-ui` |
| `023.partner-translation` | multi-step | M | FEAT-011, FEAT-009 | `019.streaming-transport-and-stop`, `014.entry-editing-and-copy-out`, `017.session-configuration` |

## Stage 004.retrieval
**Goal:** nothing has to be re-explained.
**Exit criteria:** embeddings are maintained across every write path with
their invalidation fan-out; hybrid vector+FTS5 retrieval is fused by
reciprocal rank behind one narrow port; the assistant reaches exactly three
tools; the roleplayer finds anything of their own from any screen; and an
administrator can rebuild the vector index.
**Not in it:** export/import; the privacy audit.

| Feature | Track | Size | Delivers | Depends on |
|---|---|---|---|---|
| `024.embedding-lifecycle` | multi-step | M | FEAT-009 | `012.messages-and-settle`, `015.memos`, `006.llm-server-connections`, `014.entry-editing-and-copy-out` |
| `025.hybrid-search-port` | multi-step | M | — | `024.embedding-lifecycle` |
| `026.memo-search-tool` | multi-step | M | FEAT-014, FEAT-012 | `025.hybrid-search-port`, `021.compose-loop-and-tools`, `015.memos` |
| `027.session-search-tool` | multi-step | M | FEAT-015 | `025.hybrid-search-port`, `021.compose-loop-and-tools`, `011.rp-sessions` |
| `028.web-search-tool` | multi-step | M | FEAT-016 | `021.compose-loop-and-tools`, `017.session-configuration` |
| `029.my-search` | multi-step | M | FEAT-017 | `025.hybrid-search-port`, `008.app-shell-frame` |
| `fast/002.vector-index-rebuild` | fast | S | FEAT-005 | `024.embedding-lifecycle`, `007.schema-drift-and-remediation` |

## Stage 005.portability
**Goal:** the data moves, and the isolation guarantee is proven.
**Exit criteria:** export and import at all four granularities with imported
material arriving under fresh identity; an instance brought up from a
whole-database export at first run; and a cross-cutting privacy audit that
proves no screen, search, tool or administrative surface reaches another
user's material.
**Not in it:** nothing deferred beyond it — this stage closes v1.

| Feature | Track | Size | Delivers | Depends on |
|---|---|---|---|---|
| `030.export-granularities` | multi-step | M | FEAT-018 | `011.rp-sessions`, `015.memos`, `012.messages-and-settle`, `010.setups`, `009.characters` |
| `031.import-and-id-remapping` | multi-step | M | FEAT-018 | `030.export-granularities` |
| `fast/003.bootstrap-from-export` | fast | S | FEAT-001 | `031.import-and-id-remapping`, `003.first-run-bootstrap` |
| `032.privacy-isolation-audit` | multi-step | M | FEAT-019 | `026.memo-search-tool`, `027.session-search-tool`, `029.my-search`, `030.export-granularities`, `031.import-and-id-remapping`, `005.admin-shell-and-users` |

## Build order

`001` → `002` → `fast/001` → `003` → `004` → `005` → `006` → `007` → `008` →
`009` → `010` → `011` → `012` → `013` → `014` → `015` → `016` → `017` →
`018` → `019` → `020` → `021` → `022` → `023` → `024` → `025` → `026` →
`027` → `028` → `029` → `fast/002` → `030` → `031` → `fast/003` → `032`
<!-- roadmap:end -->
