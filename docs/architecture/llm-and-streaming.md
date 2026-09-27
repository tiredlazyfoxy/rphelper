# LLM integration and streaming

**Realizes:** FEAT-004, FEAT-010, FEAT-011, FEAT-012, FEAT-013, FEAT-014,
FEAT-015, FEAT-016, ACT-004, UC-010..UC-013, UC-032..UC-038, UC-045, UC-051,
UC-053, UC-055..UC-057

One client abstraction for every provider, the SSE frame protocol, the tool loop,
what goes into context and — just as importantly — what must never go into it.

---

## One OpenAI-compatible client

**Realizes:** FEAT-004, UC-010, UC-011, UC-012, UC-013

Both provider kinds RPHelper supports — **llamaswap** and **OpenAI** — speak the
OpenAI chat-completions and embeddings wire format. So there is **one** client, not
one per provider, parameterised by base URL and credential:

```
LlmClient(base_url, api_key)
  chat_stream(model, messages, tools) -> async iterator of provider deltas
  embed(model, texts)                -> list[vector]
  probe()                            -> reachability result   # UC-011
```

One client because the difference between the two kinds is configuration, not
protocol. Writing two adapters would create two code paths that must be kept
behaviourally identical, with no compensating benefit. `llm_servers.kind`
(`data-model.md`) is therefore a **label** used for admin-facing presentation and
for provider-specific defaults, not a dispatch key that selects an implementation.

The credential arrives through `resolve_secret(api_key_ref)` at call time —
the `"$ENV_VAR"` pointer pattern in `backend-structure.md`. A missing variable is
`secret_ref_missing`, raised before any network call.

`probe()` implements UC-011: it reports reachability and **registration is
unaffected either way** (UC-011's postcondition and alternate flow). The result is
recorded on the row (`last_test_at`, `last_test_ok`, `last_test_error`) so the admin
sees the last known state without re-probing on every page load.

### The model registry and use-time validation

**Realizes:** FEAT-004, FEAT-013, UC-012, UC-050 — see `domain-rules.md` R4

The request path for every generation is exactly three steps, in this order:

```
1. resolve   config_resolver → a model REFERENCE (user → character → session)
2. validate  llm_registry    → is that reference an enabled model right now?
3. call      LlmClient       → chat_stream
```

- Step 1 **does not** consult the enabled-models registry and **does not** skip a
  level whose model is disabled. Skipping is the silent fallback UC-012 forbids.
- Step 2 is where a dead reference is caught, and it raises
  **`model_not_enabled`** carrying the reference **and which level set it**, so the
  roleplayer can go and change it (`backend-structure.md`'s error model).
- There is no step that substitutes a model. Not a default, not "the first enabled
  one", not the previous session's model.

The same applies to embeddings, with a sharper reason. The designated embedding
model (UC-013) is validated at use time and a missing or changed designation raises
**`no_embedding_model`** rather than falling back to another model — because
vectors produced by a different embedding model are **not comparable** with the
stored ones, so a silent substitution would return confidently wrong search
results rather than an error. See `search-and-retrieval.md`.

---

## The SSE event protocol

**Realizes:** FEAT-010, FEAT-014, FEAT-015, FEAT-016, UC-032, UC-034

One streaming endpoint (`POST` with a JSON body, `discussions.py`), one frame
vocabulary. Frames are `data:` lines terminated by a blank line, so the client
splits on `"\n\n"` (`frontend-structure.md`).

```
data: {"event":"token","text":"..."}                                  \n\n
data: {"event":"tool_start","tool":"memo_search","call_id":"c1","args":{...}} \n\n
data: {"event":"tool_result","tool":"memo_search","call_id":"c1","summary":"3 memos"} \n\n
data: {"event":"tool_fail","tool":"web_search","call_id":"c2","code":"tool_failed"}   \n\n
data: {"event":"error","code":"llm_unreachable","message":"...","detail":{}}  \n\n
data: {"event":"done","message_id":123}                                \n\n
```

| Event | Meaning | Client effect |
|---|---|---|
| `token` | an increment of assistant text | append to the in-flight message |
| `tool_start` | a tool call has been issued | show the tool as running |
| `tool_result` | the tool returned | mark it complete |
| `tool_fail` | the tool failed; **the discussion continues** | mark it failed, keep streaming |
| `error` | the exchange failed | render the failure; **discard nothing** |
| `done` | the exchange completed and is persisted | finalise; `message_id` identifies the stored row |

Rules the protocol enforces:

- **`done` is mandatory on success.** A stream that closes without it is treated as
  `llm_unreachable` by the client. Silence is never success.
- **`error` and `done` are mutually exclusive and terminal.** Exactly one of them
  ends every stream.
- **`tool_fail` is not terminal.** This is the protocol expression of UC-051's and
  UC-053's exception flows: a failed tool does not end the discussion. It is a
  distinct event from `error` precisely so the client cannot conflate them.
- **`error` uses the same `{code, message, detail}` shape** as the JSON error body,
  so the SPA has one error renderer (`backend-structure.md`).
- **`tool_result` carries a summary, never the raw retrieved content.** The content
  goes to the model, not to the screen. Two reasons: the transcript should show
  that a search happened, not paste its results into the reading surface; and a raw
  payload on the wire is an easy way for content to reach a surface it was not
  scoped for.
- `X-Accel-Buffering: no` is set on the response by the application
  (`deployment.md`), independently of nginx's `proxy_buffering off`.

### Ordering guarantee that protects the roleplayer's text

Before the response begins, the handler has already committed the roleplayer's
message row (`domain-rules.md` R10, UC-032). Consequently an `error` frame — at any
point, including before the first `token` — loses nothing: the entry and the
discussion survive intact, the failure is visible, and retry is possible. The
client's `error` handler is forbidden from clearing the transcript or the answer
box.

---

## The tool-calling loop

**Realizes:** ACT-004, FEAT-013, FEAT-014, FEAT-015, FEAT-016

Three tools, and only three (`domain-rules.md` R9): `memo_search`,
`session_search`, `web_search`. The loop:

```
 assemble context ──► chat_stream ──┬── text delta ──────────────► token frame
                        ▲           │
                        │           └── tool call ──► tool_start frame
                        │                              │
                        │                     dispatch (scoped read)
                        │                              │
                        │                   ┌──────────┴──────────┐
                        │                success                fail
                        │                   │                     │
                        │            tool_result frame      tool_fail frame
                        │                   │                     │
                        │            append tool result    append "tool failed"
                        │            message to the        message to the
                        │            conversation          conversation
                        └───────────────────┴─────────────────────┘
                                   re-enter with the tool output
 ...until the model produces a final answer ──► done frame
```

Rules:

- **A failed tool is a tool *result*, not a stream error.** The loop appends a
  message telling the model the tool failed, and continues (UC-051, UC-053
  exception flows; FEAT-010's exception flows). The assistant carries on without
  it. This is the single most commonly mis-implemented rule in this document, and
  it is tested by making a tool fail and asserting the discussion still produces
  an answer.
- **Tool availability comes from the resolved configuration** (FEAT-013's
  `user → character → session` chain, R1). A disabled tool is **not offered to the
  model** — it is absent from the tool list, not present-and-refused. A tool the
  model cannot see cannot be attempted, which is a cheaper and more honest
  enforcement than rejecting the call.
- **Every tool dispatch is a scoped read** carrying the authenticated `user_id`,
  and `session_search` additionally carries `character_id` (UC-054). The assistant
  has no other database path (R9), which is what makes FEAT-019's isolation
  enforceable at three points rather than everywhere.
- **The assistant never writes into the session.** No tool mutates anything. A
  candidate reaches the roleplayer's answer box and nowhere else (UC-035); only the
  roleplayer's settle action commits an entry.
- `_TBD: no iteration cap is stated in docs/product/. A bounded number of tool
  rounds per exchange is an implementation necessity — an unbounded loop can spin —
  but no limit is specified, so the plan that builds FEAT-010 must choose one and
  record it. Note that a cap is a loop guard, not context compaction, which is a
  non-goal (overview.md)._`

### `web_search` — seam now, adapter deferred

FEAT-016 is last in the dependency graph. What is specified now:

- Its **tool definition** and its place in the loop, identical in shape to the other
  two.
- Its **switch** in the configuration chain (FEAT-013/UC-048, UC-049) — it is
  disabled like any other tool.
- Its **failure behaviour** — `tool_fail`, discussion continues.
- Its three justified uses, recorded so the tool description given to the model
  matches the product: a real-world fact; an idiom or naturalness check; a direct,
  roleplayer-initiated lookup (FEAT-016, challenge C2).

What is **not** specified: the provider adapter. `_TBD: no search provider is
chosen; docs/product/ names none. The adapter is deferred to FEAT-016's plan
(overview.md)._`

---

## Context assembly — what the assistant reads

**Realizes:** FEAT-009, FEAT-010, FEAT-011, FEAT-012, FEAT-013, UC-029, UC-034,
UC-038, UC-045

ACT-004 "consumes forced memos and the session's RP-language entries"
(`actors.md`). That is the whole list, and it is a closed list.

```
system prompt  = resolved system_prompt (R1: user → character → session)
               + character sheet
               + all FORCED memos in the session's chain (R2/R3, UC-045)
               + RP-language instruction (resolved rp_language, R1: user → session)
               + tool descriptions for ENABLED tools only

messages       = the session's entries, in order, current text  (UC-029)
               + the OPEN discussion's messages
```

### What must NOT be in context — each with the requirement that forbids it

| Excluded | Why |
|---|---|
| `searchable` memos | reachable only through `memo_search` (R3, FEAT-012) |
| `disabled` memos | reach the assistant by **no path** (R3, UC-052) — not context, not tools, not error payloads |
| Collapsed discussions' messages | a settled discussion never reaches the assistant again, then or later (UC-038, R7) — context assembly has **no join** to `discussions` at all except the currently-open one |
| Translations | a translation never enters session context; context holds only the RP language (R8, FEAT-011) — assembly never reads the `translations` table |
| Any other user's material | FEAT-019, UC-065; assembly is scoped by `user_id` |
| Another character's sessions | FEAT-015/UC-054 boundary; assembly reads only this session |

The absences are the invariant. A test that proves the right things are present is
half a test here; the negative cases above are the ones that protect product
guarantees.

### Two facts that follow from mutability

- **Entries are read live.** A settled answer is editable forever and the assistant
  always reads the current version (UC-029, US-032.AC-2), so assembly reads
  `entries.text` at request time and never caches a snapshot.
- **Forced memos are read live too.** A memo flipped to `forced` or to `disabled`
  takes effect on the next message in every session in its scope (UC-044, UC-045),
  with no invalidation step, because nothing was cached.

### Language handling

- **Candidates are always produced in the RP language** (UC-034), regardless of the
  language the roleplayer is discussing in. That instruction is part of the system
  prompt, and it is separate from the mirroring rule below.
- **The assistant mirrors the language of each discussion message** (UC-033). There
  is **no fixed discussion language** and none is stored
  (`data-model.md` — `discussion_messages` has no language column). The mirroring is
  a system-prompt instruction, not a detected-and-recorded setting; the roleplayer
  may switch language message to message and the assistant keeps mirroring.
- **Context holds only the RP language** — which is why R8 keeps translations out.

### No context compaction

Session context grows forever: no ceiling, no warning, no pruning. This is an
explicit **non-goal** (`vision.md`), knowingly chosen by the user over three bounded
alternatives, and nothing in the assembly above mitigates it.

`_TBD: a long RP will eventually exceed what the model can hold, and nothing warns
the roleplayer first — carried from vision.md's non-goals and FEAT-009/FEAT-010's
own _TBD:. An enormous paste warns about context cost (US-035.AC-1) but the
session's own accumulated size does not._`

Note what this means concretely for anyone building FEAT-010: a provider error
caused by exceeding the context window arrives as `llm_unreachable` or a
provider-specific failure, and the design contains no special handling that
distinguishes it. That is a consequence of the non-goal, recorded rather than
quietly fixed.

---

## Translation

**Realizes:** FEAT-011, UC-039, UC-040, UC-041

Translation uses the same `LlmClient` and the same resolve→validate→call path as
generation, against the session's resolved model, targeting the session's resolved
**preferred language** (R1's two-level chain).

It is **not streamed**. A translation is a whole-text replacement for a
read-only flicker (UC-039), so partial output has no use — the flicker either shows
the translation or shows the original.

- On **success**, the result is cached in `translations` keyed by
  `(entry_id, target_language)` (UC-041), so the second look is instant.
- On **failure**, `translation_failed` is raised, the flicker falls back to the
  original text with a visible error, and **nothing is cached** (UC-039's exception
  flow).
- The translation never enters context (R8).
