<!-- product-spec:start -->
# Glossary

Domain vocabulary, drawn from the interview (rounds 0–17). "Memo" is the
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
- **Entry** — one independent item in a session: a partner block, the
  roleplayer's own turn, or a decision — three kinds, added in any order.
- **Partner entry** — a block of the partner's text, pasted in.
- **Answer entry** — the roleplayer's own settled reply.
- **Compose discussion** — the discussion attached to an answer entry where
  the roleplayer and the assistant work out its text.
- **Candidate** — a reply the assistant produces inside a compose
  discussion, in the RP language, for the roleplayer to promote, edit, or
  discard.
- **Settle** — to commit the last message in the current zone, whoever wrote
  it, as the entry's final text; collapses the discussion that produced it.
- **Collapse** — what a compose discussion does on settling: it stops
  reaching the assistant and stays readable, re-openable only while nothing
  follows it.
- **Flicker** — the toggle that shows a partner entry's translation instead
  of its original text, on demand.
- **Memo** — a standing note at the user, character, setup or session level;
  independently forced or not-forced, and enabled or disabled.
- **Forced / enabled** — the two axes a memo carries: forced or not-forced,
  and enabled or disabled. Disabled wins — a disabled memo reaches the
  assistant by no path regardless of its forced flag; the forced flag is
  remembered while disabled and restored on re-enable.
- **Memo chain** — the memos a session's `memo_search` can reach: its own,
  its setup's (when present), its character's, and the user's.
- **Archive** — remove a character, setup or session from the working list
  without destroying it; always restorable.
- **Note** — the roleplayer's own word for a memo. Same concept as memo, two
  names — recorded here rather than treated as a second concept (round 16,
  challenge C16).
- **The stream** — the session's merged centre column: the settled record,
  the ruler, and the current zone.
- **The wall** — the note panel beside the stream.
- **The ruler** — the boundary between the settled record above and the
  current zone below.
- **The current zone** — the single working area below the ruler; its
  messages are not yet part of the record.
- **Decision** — a third kind of session entry: something settled about the
  roleplay itself (a tone or situation change) rather than RP prose,
  positioned in time — everything before it still reads the old way.
- **Turn** — the roleplayer's own entry in the record. FEAT-009's and
  FEAT-010's earlier wording calls this an "answer" or "settled answer";
  they are the same thing.
- **Out-of-character (OOC)** — the roleplayer speaking as themselves rather
  than as the character, marked by wrapping the whole message in double
  parentheses.
<!-- product-spec:end -->
