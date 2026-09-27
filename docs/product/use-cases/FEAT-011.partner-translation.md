<!-- product-spec:start -->
# FEAT-011 — Partner-text translation — use cases

### UC-039 — Flick a partner entry into my preferred language
- **Actor:** ACT-002
- **Feature:** FEAT-011
- **Preconditions:** Partner entry exists in the RP language (UC-027).
- **Main flow:**
  1. Roleplayer flicks a partner entry to translate it.
  2. Instance translates it into the roleplayer's preferred language.
  3. Translated text is shown in place of the original.
- **Exception flows:**
  - Translation fails — the flicker falls back to the original text with a visible error, and nothing is cached.
- **Postconditions:** Translated text never enters session context; on failure, nothing is cached.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 2, round 9.

### UC-040 — Flick back to the original
- **Actor:** ACT-002
- **Feature:** FEAT-011
- **Preconditions:** Entry is currently showing its translation (UC-039).
- **Main flow:**
  1. Roleplayer flicks the entry again.
  2. Instance shows the original RP-language text.
- **Postconditions:** Original text shown; nothing about the entry changes.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 0, round 2.

### UC-041 — The translation is cached after first use
- **Actor:** ACT-002
- **Feature:** FEAT-011
- **Preconditions:** An entry has been translated once, successfully (UC-039).
- **Main flow:**
  1. Roleplayer flicks the same entry to translated again, later.
  2. Instance shows the cached translation instantly, with no new lookup.
- **Postconditions:** Second and later looks cost nothing further.
- **Source:** `[confirmed: user]` interview 2026-09-27, round 4.
<!-- product-spec:end -->
