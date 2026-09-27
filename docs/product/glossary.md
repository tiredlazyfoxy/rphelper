<!-- product-spec:start -->
# Glossary

Domain vocabulary, drawn from the interview (rounds 0–10). "Memo" is the
domain word throughout this doc set — the user used "memo" and "note"
interchangeably, the assistant's tool is `memo_search`; "note" is not a
separate concept here.

- **RP language** — the language the roleplay is conducted in. The
  partner's text arrives in it, the settled answer is written in it, and it
  is the only language the session's model context holds.
- **Preferred language** — what the roleplayer thinks and discusses in, and
  what partner text is translated into. Defaults on the account,
  overridable per session.
- **Roleplayer** (`ACT-002`) — the account holder composing their own side
  of a roleplay.
- **Partner** — the other side of the roleplay. Free text, never a
  first-class entity; never touches the system directly.
- **Character** — a roleplayer's persona, reused across many setups and
  partners; the assistant composes replies as this character.
- **Setup** — an optional reusable object under a character, carrying its
  own memos and acting as a search anchor for a situation.
- **Session** — one roleplay run under a character, optionally with a
  setup; always resumable, ordered by last use.
- **Entry** — one independent item in a session: a partner entry or an
  answer entry, added in any order.
- **Partner entry** — a block of the partner's text, pasted in.
- **Answer entry** — the roleplayer's own settled reply.
- **Compose discussion** — the discussion attached to an answer entry where
  the roleplayer and the assistant work out its text.
- **Candidate** — a reply the assistant produces inside a compose
  discussion, in the RP language, for the roleplayer to promote, edit, or
  discard.
- **Settle** — to commit whatever the answer box holds as the entry's final
  text; collapses the discussion that produced it.
- **Collapse** — what a compose discussion does on settling: it stops
  reaching the assistant and stays readable, re-openable only while nothing
  follows it.
- **Flicker** — the toggle that shows a partner entry's translation instead
  of its original text, on demand.
- **Memo** — a standing note at the user, character, setup or session level,
  set to forced, searchable or disabled.
- **Forced / searchable / disabled** — the one setting a memo carries: always
  in the system prompt, reachable only by `memo_search`, or unreachable by
  any path.
- **Memo chain** — the memos a session's `memo_search` can reach: its own,
  its setup's (when present), its character's, and the user's.
- **Archive** — remove a character, setup or session from the working list
  without destroying it; always restorable.
<!-- product-spec:end -->
