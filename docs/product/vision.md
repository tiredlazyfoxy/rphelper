<!-- product-spec:start -->
# Vision

## Problem

The user roleplays on external sites and Discord and is not a confident
writer in the language the roleplay is conducted in. They need help
composing their own side of the exchange — ideas, added detail, or plain
translation. `[confirmed: user]` interview 2026-09-27, round 0.

## Who has it

- **Roleplayer** (`ACT-002`) — roleplays on external sites and Discord,
  "anywhere", in a language they are not a confident writer in; needs help
  producing their own replies. `[confirmed: user]` interview 2026-09-27,
  round 0, round 1.

## What happens without it

Generation is already available today from three workarounds: pasting into
ChatGPT/Claude, a translator, and local LLM chat apps. `[confirmed: user]`
interview 2026-09-27, round 1. What none of them give is persistent,
per-character management of prompts, notes and memory — "it's hard to
manage different characters prompts, notes, memories etc." The cost is
re-explaining context on every single reply and having nowhere for a
character's material to live. The product's value is the persistent context
layer, not the generation. `[confirmed: user]` interview 2026-09-27, round 1.

## Success signals

Exactly three, all from the roleplayer's seat — no signal was invented to
cover a feature that isn't one of these three:

- **S1** — Starting a new session with an existing character requires zero
  re-typing of persona, notes or history. `[confirmed: user]` interview
  2026-09-27, round 3.
- **S2** — A reply takes minutes rather than tens of minutes. Today a good
  reply can take 20–40 minutes; the target is under 10. `_TBD: this is the
  user's own estimate of the 20–40 minute status quo, not a measurement._`
  `[confirmed: user]` interview 2026-09-27, round 3, round 4.
- **S3** — The user stops using ChatGPT / translators / local chat apps for
  RP. `[confirmed: user]` interview 2026-09-27, round 3.

**Enabler note.** `FEAT-001`..`FEAT-005` (the platform layer), `FEAT-018`
(export/import) and `FEAT-019` (privacy) trace to no success signal above.
Asked directly whether the vision was incomplete or the features
unjustified, the user answered: "they're enablers, not value." They are
justified by necessity, not by a signal invented to make the matrix tidy —
recorded plainly rather than papered over. `[confirmed: user]` interview
2026-09-27, round 9.

## Scope & non-goals

Full feature scope is the spine in `features.md` (`FEAT-001`..`FEAT-019`).
Non-goals below are boundaries meaningful against this vision, each with its
reason:

- **Not an RP engine.** The assistant never writes the partner's side. The
  partner's text is always pasted from outside, never generated.
  `[confirmed: user]` interview 2026-09-27, round 1.
- **No platform integration.** Manual paste only; the boundary is the
  clipboard. No Discord or RP-site connection exists or is planned.
  `[confirmed: user]` interview 2026-09-27, round 1.
- **No context compaction.** Session context grows forever with no ceiling,
  no warning and no pruning. The user knowingly chose this over three
  bounded alternatives and named compaction as a future request. `_TBD: a
  long RP will eventually exceed what the model can hold, and nothing warns
  the user first._` `[confirmed: user]` interview 2026-09-27, round 6, round
  8, challenge C3.
- **No cross-user visibility of any kind**, including for the administrator.
  `[confirmed: user]` interview 2026-09-27, round 1, round 2.
<!-- product-spec:end -->
