# Feature 006 — LLM server connections · intended documentation changes

Written by the planner before implementation; applied by `/architect` at finalization.
Grouped by target file. The coder appends `## Observations` at the bottom.

---

## `docs/architecture/admin-surfaces.md`

### A1 — The LLM Servers page has no "active" column and no active switch

- **Section:** "LLM Servers page — FEAT-004", the columns sentence and the **Server form
  modal** paragraph.
- **Change:** remove **active** from the column list and the **active switch** from the
  form. Record that the page's columns are name, backend-type badge, base URL, has API
  key, enabled-model count, a last-test badge, and the trailing action column.
- **Reason:** `data-model.md`'s `llm_servers` declares no such column, no UC and no US
  asks for one, and a plan may not edit the table registry. Dropped by **user decision**
  (plan `context.md` D1). The two docs currently contradict each other, and the page spec
  is the one that is wrong.

### A2 — The last-test badge is part of the page, and the outcome values are its source

- **Section:** "LLM Servers page — FEAT-004", the DEVIATION paragraph and the result
  taxonomy.
- **Change:** record that the four-value taxonomy is **kept, not narrowed** (the doc allows
  FEAT-004's plan to narrow it to the product's two and this plan declines), and that
  `llm_servers.last_test_error` stores **the typed outcome value itself** — never a
  provider message and never prose. Record the ok mapping: `reachable` is true and each of
  the other three is false, because both extra values are kinds of not-reachable. Record
  that the closed value set is declared once, in `services/llm/client.py`, and reused by
  the registry, the router model and the frontend row type.
- **Reason:** the doc fixes the four values but not which of them counts as ok, nor what
  the column holds; both are needed by three layers and would otherwise be re-decided per
  layer.

### A3 — Clear Embedding is confirmed; saving an enabled-model set is not

- **Section:** "LLM Servers page — FEAT-004" → Embedding modal, cross-referenced with
  `ui-conventions.md`'s confirm table.
- **Change:** record that this feature adds **Clear Embedding** to the set of confirmed
  actions — it is irreversible in effect, since with no designation every semantic path
  fails as `no_embedding_model` and re-designating requires a fresh measuring call — and
  that **saving an enabled-model set is deliberately not confirmed**, being fully
  reversible and having no permissible informative consequence sentence under R5. Record
  that Clear Embedding is offered in the row menu, conditionally, and that no duplicate
  page-header action is built.
- **Reason:** `ui-conventions.md` explicitly invites FEAT-004's planner to revisit the
  confirmed set; this is the revision, and it should be visible in the table rather than
  only in a plan.

### A4 — Designation measures the dimension with one real embeddings call

- **Section:** "LLM Servers page — FEAT-004" → Embedding modal.
- **Change:** record that designating embeds one short fixed string against the chosen
  model, measures the returned vector's length and writes it to `models.embedding_dim`,
  and that a failed or non-embedding response **blocks the designation** with a typed
  error rather than recording a designation that cannot produce vectors. Record that this
  is why `LlmClient.embed` exists in FEAT-004 rather than only in FEAT-017's feature, and
  that the modal's copy says so.
- **Reason:** the dimension is not discoverable from a models listing on either provider
  kind, so the mechanism is not obvious from the schema, and a reader would otherwise
  assume it is read from metadata. **User decision** (plan `context.md` D2).

---

## `docs/architecture/backend-structure.md`

### B1 — Statuses for the three deferred codes, plus one new code

- **Section:** "The error model" → the named-errors table.
- **Change:** assign the statuses the table leaves open — `llm_unreachable` **502**,
  `no_embedding_model` **409**, `model_not_enabled` **409** — and add one row:

| `code` | Raised when | `detail` carries | Realizes |
|---|---|---|---|
| `llm_server_not_found` | An admin LLM route addresses a server id that does not exist | nothing | FEAT-004, UC-010..UC-013 |

  with status **404**. Record that `model_not_enabled`'s `detail` carries the **server id
  as a decimal string, the model name and the level**, the level constrained to `character`
  or `session`.
- **Reason:** the table names the codes and assigns no status, deferring it to the
  introducing feature; this is that feature. `llm_server_not_found` is the sibling of
  FEAT-003's `user_not_found` and every id-addressed route here needs it.

### B2 — The admin LLM route surface

- **Section:** Layout (the `routers/admin_llm.py` and `services/llm_registry.py` lines) and
  "Authorization as router dependencies".
- **Change:** record the chosen prefix **`/api/admin/llm-servers`** and its nine routes —
  `GET` (list), `POST` (create, 201), `PATCH /{server_id}`, `DELETE /{server_id}` (204),
  `POST /{server_id}/test`, `GET /{server_id}/available-models`,
  `POST /{server_id}/models` (replace the enabled set), and
  `POST` / `DELETE /{server_id}/embedding-model`. Record four decisions embedded in it:
  **`PATCH` rather than FEAT-003's named-action-route pattern**, because a registration is
  one entity with one rule and the API-key contract is literally "which fields were
  supplied"; **`POST` rather than `PUT`** for the enabled set, because the shared frontend
  client's method union has no `PUT` and adding one for a single call site was out of
  scope; **no `GET /{server_id}/models`**, because the enabled names ride on the list
  payload, which is what makes failed-probe resilience structural; and a **server-scoped**
  clear-designation path, which cannot collide with `{server_id}` in the route table.
  Record that `require_role(Role.admin)` is attached once at router level, making
  `admin_llm.py` the second of the three `admin_*.py` routers the section anticipates.
- **Reason:** no document fixed the paths, and FEAT-001/002/003's plans set the precedent
  of recording a chosen route surface rather than leaving it to be discovered.

### B3 — The probe primitive, as built

- **Section:** "The connection probe — one primitive, two routes".
- **Change:** record how the split lands: the primitive resolves the pointer, builds a
  client through an injectable factory and returns a typed outcome, **writing nothing**;
  the **test** route writes `last_test_at` / `last_test_ok` / `last_test_error` and answers
  **200 even for a failing outcome**, because the test succeeded and the connection did
  not; the **available-models** route writes nothing and answers **502 `llm_unreachable`**
  for an unreachable or auth-failed server, because there is no useful partial answer to
  "what can it run". Record that opening a models modal therefore cannot overwrite the
  administrator's last deliberate test result.
- **Reason:** the section fixes the split but not the two routes' opposite error postures,
  which is exactly the pair a later reader would "harmonise".

### B4 — `secret_ref_missing` now has an administrator-facing call site

- **Section:** "The `"$ENV_VAR"` secret-pointer pattern" and the error table.
- **Change:** record that the write-time rejection of a non-`$` value is implemented as an
  annotated pydantic field type in **`app/models/secret_ref.py`**, answering FastAPI's own
  **422** and adding no domain error code, while `resolve_secret` is unchanged and handles
  read-time resolution alone. Record that the empty string is a **legal** value meaning
  "no pointer" on create and "clear the stored pointer" on update. Record that the test-
  connection route lets `secret_ref_missing` propagate as a **500** and records nothing on
  the row, because the failure is a configuration fault of the instance rather than a
  property of the connection.
  **Open question for the architect:** whether `secret_ref_missing` should keep its 500
  now that an administrator can reach it through a normal admin action. This plan did not
  re-map it, because FEAT-001 froze the status and a plan should not silently change a
  shipped code's contract.
- **Reason:** the section says "rejected on write" without saying where or with what
  status, and the 500 is the kind of thing a later reader reports as a bug.

### B5 — The first async code in the backend, and what it costs

- **Section:** "Database access" / "Persistence access — SQLAlchemy **Core**, not the ORM",
  or a short note near the Layout entry for `services/llm/client.py`.
- **Change:** record that `httpx` moved from the dev dependency group into the runtime
  dependencies with this feature — the first outbound-HTTP code in `app/` — and that the
  client is **`httpx.AsyncClient`**, chosen because FEAT-009/010's streaming goes through
  the same module and a sync client would have to be rewritten. Record the consequence:
  the three registry operations that reach the network are `async def` and so are their
  three routes, while the SQLAlchemy `Connection` they hold stays **sync**, so their small
  single-row reads and writes block the event loop briefly. **Flip condition:** if a
  request path ever needs a long or multi-statement transaction around an awaited call,
  the mix has to be resolved rather than extended — either by moving the database work off
  the loop or by adopting an async driver.
- **Reason:** the doc's persistence section is written on the assumption that everything is
  sync; the first exception should be visible with its reasoning and its limit rather than
  discovered in a diff.

---

## `docs/architecture/data-model.md`

### D1 — What the two FEAT-004 tables look like as built

- **Section:** `llm_servers` and `models`.
- **Change:** record the constraints the plan fixed and the doc leaves implicit: `models`
  carries a **unique constraint on (server_id, model_name)** (already stated) and its
  `server_id` foreign key is declared **`ON DELETE CASCADE`**, while the delete operation
  *also* removes the child rows explicitly inside its own transaction so the behaviour does
  not depend on a connection pragma. Record that `llm_servers.kind` is plain text with **no
  `CHECK`** — the two-member constraint lives at the pydantic boundary, because a database
  `CHECK` would make a third provider a schema change, which contradicts "a label, not a
  dispatch key". Record that **`models` rows are never deleted by an enable or a disable**,
  which is what makes the models modal's `available ∪ already-enabled` union work.
- **Reason:** three properties that several later features will rely on and that are
  currently inferable only from the plan.

### D2 — Designation is independent of `is_enabled`, and validation is at use time

- **Section:** `models`, the paragraph after the column table.
- **Change:** record the resolution of `brief.md`'s first open question (**user decision**,
  plan `context.md` D4): disabling a model **never** clears a designation and is never
  refused; designating does **not** enable; and the use-time embedding validator requires
  the designated model to be **both designated and enabled**, raising `no_embedding_model`
  otherwise. There is **no cross-table cascade** in FEAT-004.
- **Reason:** the doc states the disable rule but is silent on the designation's
  interaction with it, which is the question a planner had to close.

### D3 — `sessions.model_ref`'s packed form is still open

- **Section:** `sessions`, the `model_ref` paragraph.
- **Change:** carry forward, as a `_TBD:`, that the **encoding** of `model_ref` is not
  fixed anywhere: a bare model name is ambiguous across two registered servers that offer
  the same name, since `models` is unique on the pair. Record that FEAT-004's use-time
  validator deliberately takes the **server id and model name as two plain arguments** so
  the encoding decision stays with the feature that writes the column (FEAT-008/FEAT-013's
  plans).
- **Reason:** the gap is invisible today because nothing reads the column, and it becomes a
  silent ambiguity the moment two servers are registered.

---

## `docs/architecture/llm-and-streaming.md`

### L1 — The client as built, and what is deliberately absent

- **Section:** "One OpenAI-compatible client", the sketch.
- **Change:** record that FEAT-004 builds construction, `probe()` and `embed()`, and that
  **`chat_stream` is not stubbed** — a stub with no caller is dead code FEAT-009/010 would
  rewrite. Record that `probe()` **returns** its outcome and raises nothing, while `embed`
  **raises** `llm_unreachable`, with the reason: every probe state including total failure
  is an answer UC-011 requires to be reported, whereas an embedding has no useful partial
  result. Record that base-URL composition tolerates a trailing slash and an already-present
  `/v1`, because an administrator types the URL by hand and a wrong composition presents as
  `unreachable` against a healthy host.
- **Reason:** the sketch shows three operations with no note on which feature builds which,
  and the raise/return asymmetry is the kind of thing a later contributor would "tidy".

### L2 — The use-time validators ship with no call site

- **Section:** "The model registry and use-time validation".
- **Change:** record that both validators live in `services/llm_registry.py` and were built
  by FEAT-004 **with no consumer** — sessions arrive with FEAT-008/FEAT-013's features and
  embeddings with FEAT-014/015's — so they are covered by tests against the service rather
  than through a session. Record that this is expected and is not an unfinished path.
- **Reason:** a reader auditing coverage would otherwise read the missing end-to-end test as
  a gap, and might "fix" it by wiring a premature call site.

---

## `docs/architecture/ui-conventions.md`

### U1 — The confirm table gains a fourth row

- **Section:** "NEW — the confirm convention", the table of confirmed actions.
- **Change:** add **Clear the embedding designation** (FEAT-004) with its consequence:
  every semantic feature stops working until a model is designated again, and
  re-designating requires a fresh measuring call. Note that **saving an enabled-model set
  is explicitly not confirmed**, so the decision reads as taken rather than forgotten.
- **Reason:** the section invites FEAT-004's planner to revisit the set and this is the
  result; a fourth confirmed action that appears only in a plan will drift.

### U2 — The failed-probe rule is satisfied structurally, and the doc can say how

- **Section:** the list/modal conventions, cross-referenced with `admin-surfaces.md`'s
  "Failed-probe resilience".
- **Change:** record the implementation shape that makes the rule hold by construction
  rather than by care: the **already-enabled set arrives with the page's list payload**,
  which involves no outbound call, while the probe writes only the *available* list — so
  there is no code path by which a probe failure can reach the selection. Record that the
  two model modals share one picker module for the probe, the union and the failure
  behaviour, and differ only in their `*Draft.ts`.
- **Reason:** the rule is currently stated as a warning against a specific naive
  implementation; naming the shape that cannot go wrong is more durable than naming the one
  that can.

---

## `docs/architecture/quick-reference.md`

### Q1 — Index the new surfaces

- **Change:** add `llm_unreachable` (502), `no_embedding_model` (409), `model_not_enabled`
  (409) and `llm_server_not_found` (404) to the error-code list; add the
  `/api/admin/llm-servers` route surface; add the `llm_servers` and `models` tables
  wherever the schema is summarised; add `RPHELPER_LLM_REQUEST_TIMEOUT_SECONDS` (default
  30.0) to the configuration list; add the four-value probe outcome set.
- **Reason:** the file is the dense agent-first index and these are exactly the facts an
  agent looks up there rather than reading three long docs.

---

## Notes for the architect, not doc changes

- **Nine steps rather than the six-to-eight the briefing aimed for.** Two of the briefing's
  suggested bands split on size, not on disagreement: the registry service is two steps
  (registrations plus the probe; models, designation and the validators), and the two
  `available ∪ already-enabled` modals are two steps — the briefing authorised keeping them
  together "only if they fit the budget", and they do not. Reasoning is in plan
  `context.md` D15.
- **The use-time validators have no call site in this feature, and that is by design.**
  Their DoD items are tested directly against the service. See L2 above.
- **`_TBD:` carried, not resolved:** `sessions.model_ref`'s packed form (D3 above), and
  `ui-conventions.md`'s no-pagination `_TBD:` — an LLM-server list is the smallest list in
  the product and holds comfortably, so that doc's flip condition is unchanged.
- **One status the architect may want to revisit:** `secret_ref_missing`'s 500, now
  reachable through a normal administrator action. See B4.
- **`docs/product/` gap worth noting, not closing here:** US-014's "becomes selectable when
  configuring a session" and US-016.AC-3's "the roleplayer resolves it through FEAT-013's
  chain" are only half-realizable by FEAT-004 — the registry half. The consuming half
  belongs to FEAT-013's feature and to the session surface. The plan's `context.md` says so
  rather than claiming full coverage.

---
Status: Applied 2026-10-01 — /architect finalization (with /product-spec finalization the same day)
Applied items: 17 (A1–A4, B1–B5, D1–D3, L1–L2, U1–U2, Q1; A3, A4 and B4 with modification)
Rejected items: 0
Notes: A3 cites US-015.AC-2 for Clear Embedding; A4 cites US-015.AC-3/AC-4 for the blocked designation. B4's open question on `secret_ref_missing`'s 500 was held (H1) and resolved by the user: 500 kept, recorded once as a shared posture with `schema_apply_failed` in `backend-structure.md`'s error model and referenced from `admin-surfaces.md`. The `docs/product/` gap note is closed by `/product-spec` (US-014 / US-016 partially delivered); no architecture change beyond L2.
