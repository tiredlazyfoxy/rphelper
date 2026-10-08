# Feature 019 — Streaming transport and stop · outcome

Intended changes to `docs/architecture/` once this feature ships, for the architect to
apply at finalization. Grouped by target file. D-n refers to this folder's `context.md`.

## `docs/architecture/llm-and-streaming.md`

| Section | Intended change | Reason |
|---|---|---|
| "The SSE event protocol" — "Frames are constructed in one place" | Record as built: `services/llm/frames.py` holds seven immutable frame value types and **one encoder** (`data: ` + compact JSON with `event` first + `\n\n`, UTF-8, ids via `str()`). A source yields frame values, not strings. The `error` frame is built from a `DomainError`'s **inner** fields, not `to_wire()`'s wrapper (D2). | As built; it fixes where the id conversion happens. |
| "Four ways a stream ends" | Add the server-side resolution: a source that raises a non-domain exception, or exhausts without `error` or `done`, is ended by the harness with an `error` frame `llm_unreachable` and a fixed message. So the server **never** ends a stream silently, and silence always means the connection went away (D5). | The table assumed the source always ends with a terminal frame. |
| "Stopping model work in flight" — consequence 1 | Record the **widened persist rule**: the harness persists the accumulated `token` text whenever no `done` passed through. That covers disconnect, `error` (domain or synthesized) and terminal-less exhaustion, written **before** the `error` frame. Whitespace-only text writes no row. The success path's row is written by the source before it yields `done` (D4). | R10's extension to the assistant's side now also covers a mid-stream failure, not only a stop. Flagged for review. |
| "Stopping model work in flight" — mechanism | Record the disconnect detection: one `finally` keyed on "no terminal frame emitted", covering cancellation, generator close and an `is_disconnected()` poll before each write. Synchronous persist; shielded, error-suppressed `aclose()` of the source, which unwinds the upstream `httpx` request (D6). | Closes 019's brief question "how the server learns of the abort". |
| "Named divergences" | No change. Note that 019 binds neither US-133 AC. AC-1 falls to 021 (the loop dies with the socket) and AC-2 to 023 (best-effort check). | Status note. |

## `docs/architecture/backend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| Layout — `services/llm/frames.py` comment | Amend "SSE frame emission" to "SSE frame types + encoder, the streaming harness (`frame_stream`, `sse_response`) and `own_connection_persister`" (D1). No new module. | The harness lives there, by preference, rather than in a new module. |
| Layout — `services/messages.py` comment | Add "and append an assistant row" (`append_assistant_message`, D8). | New shared function. |
| "The streaming route" | Record the **harness signature 021 binds to**: `sse_response(request, source, own_connection_persister(get_engine(settings), generator, user_id, session_id))`. `request` is used only for `is_disconnected()`, `source` is an async iterator of frame values, and the persister is a **synchronous** callable taking the partial text. The response is `text/event-stream` with `X-Accel-Buffering: no` (D3, D7). | The interface 021 mounts. |
| "The streaming route" — rule 3 | Record that the partial-row write happens on the harness's **own short-lived connection** from `get_engine(settings)`, never the request-scoped `get_connection`, whose teardown relative to body iteration is unverified for the installed FastAPI. A persist failure is logged (ids and class only) and swallowed (D7). | Connection ownership was unstated. |
| "The streaming route" — "the same write the success path performs" | Name it: `append_assistant_message(connection, generator, user_id, session_id, text)`, role `assistant`, kind NULL, same ownership check and session bump as `append_message` (D8). | The shared write now has a name. |
| "The streaming route" | Record that **019 mounts no route** and leaves `routers/stream.py` untouched. **021** mounts `POST /api/sessions/{id}/zone/compose`, adds `chat_stream`, and owns R10's persist-before-call. | Ownership boundary. |

## `docs/architecture/frontend-structure.md`

| Section | Intended change | Reason |
|---|---|---|
| "The API client" | Record the two exported helpers in `shared/api.ts` that `apiRequest` and the SSE consumer share: the non-2xx decode (401 navigation included) and the rejection mapping (abort unchanged, else `client_transport_failed`) (D10). | One decode site, now with two callers. |
| "The SSE consumer" | Record as built: `shared/sse.ts`, one function that **never rejects** and resolves to exactly one outcome: done (message id string), error (`ApiError`), stopped (decided on `signal.aborted`), or unexpected end. A non-2xx is decoded exactly as `apiRequest` does. A malformed frame gives `client_malformed_error`; an unknown event is skipped; frames after a terminal one are never delivered. The caller renders unexpected end as `llm_unreachable` (D9). | The termination result type, as built. |
| "The SSE consumer" — token handling | **Divergence to record:** tokens append to a **dedicated observable streaming-text field** on `StreamState`, not to a placeholder row in `zone`. The reason: 013's `ZoneList` offers edit on every zone row, and a placeholder's client-minted id must never reach `PATCH /api/messages/{id}`. Every outcome replaces the in-flight text with the server's rows by a zone re-read. **"Edit while streaming" is therefore not possible as built.** Re-decide it in 022, which owns live rendering (D11). | It contradicts the doc's "writes into the same observable the editor binds to". |
| "The SSE consumer" — controller ownership | Record: the compose controller is **per compose**, held in a **non-observable** handle on `StreamState` together with a wound-down promise. It is linked to `SessionStream`'s mount controller so that unmount aborts it, and a mount abort writes nothing. `isStreaming` derives from the streaming-text field (D12). | Where the compose/stop controller lives. |
| "State — MobX 6" | Note the one sanctioned non-observable field (`makeAutoObservable` override `false`) for a controller and a promise, as non-data handles (D12). | The four rules say fields are observable. |

## `docs/architecture/workspace-shell.md`

| Section | Intended change | Reason |
|---|---|---|
| "The stop control" | Record as built: an `IconPlayerStop` `IconButton` labelled "Stop" occupies Send's slot while streaming, with Send **absent**. Settle stays enabled on its own rules (D13). | As built. |
| "The stop control" — Settle paragraph | Add (user-confirmed): **pressing Settle mid-stream stops the compose first**, as Stop does and with no notice. It waits for the compose's own post-stop zone re-read, then settles and re-reads both lists (D16). | What Settle mid-stream does was unspecified. |
| "The stop control" — consequences | Add the **accepted residual race** (user-accepted): the server's disconnect-persist of the partial row may commit before or after a mid-stream settle. If after, the partial appears as a candidate in the **fresh** zone below the settled entry: not lost, one zone later. Likewise a plain stop's re-read may run before the persist commits, in which case the partial appears on the next re-read (D17). | Known behaviour, recorded rather than engineered around. |

## `docs/architecture/quick-reference.md`

| Section | Intended change | Reason |
|---|---|---|
| Paths | Add `services/llm/frames.py` (frames + harness), `shared/sse.ts`. Note the compose call in `app/streamApi.ts` and the streaming fields in `app/streamState.ts`. | Dense index. |
| Icons | Stop → `IconPlayerStop`, now in use (Composer). | Dense index. |

## Forward notes (not architecture changes; for the owning plans)

- **021:**
  - Mount the route and return the `sse_response(...)` above.
  - The source writes the assistant row with `append_assistant_message` **before**
    yielding `done`, and must **not** write the partial row on any failure path. The
    harness does that (D4).
  - The request body is `{text}` as 019's `composeZone` sends it. That is a **binding
    point**: if 021 refines it, change `composeZone` and its DoD-1 together.
  - Switching Send to compose (with 022) means calling `composeMessage` from Send's
    handler; the Stop slot is already in place.
- **022:**
  - Render `StreamState`'s streaming text as the live assistant message.
  - Decide edit-while-streaming (D11).
  - Consume the tool frames that 019 ignores (D18).
- **023:** the translation stop is the best-effort `is_disconnected()` check before the
  cache write. Nothing in 019 is reused for it.
- **017:** `sendBlockedReason` gates Send only, never Stop (`context.md` "Build state").

---
Status: Applied 2026-10-06 — /architect finalization (with /product-spec finalization the same day)
Applied in: B1 (the backend spine — `session-stream.md`, `transfer.md`, `backend-structure.md`, `data-model.md`, `domain-rules.md`), B2 (the LLM/search/operations layer — `llm-and-streaming.md`, `search-and-retrieval.md`, `deployment.md`, `admin-surfaces.md`, `overview.md`) and B3 (the frontend layer — `workspace-shell.md`, `frontend-structure.md`, `ui-conventions.md`, `forms-and-lists.md`).
Rejected items: Its "Named divergences — no change" status note is rejected: both acceptance criteria were amended on 2026-10-06, so the divergence no longer exists.
Notes: The widened persist rule (D4), flagged for review, is accepted as a strict improvement on R10's extension. Its token-handling divergence (D11, "re-decide in 022") is not written as open — 022 decided, and only 022's final shape is recorded.
