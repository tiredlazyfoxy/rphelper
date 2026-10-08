# Fast feature 002 — vector-index-rebuild

| Status  | Verifier | Date |
|---------|----------|------|
| done    | PASS     | 2026-10-07 |

## Files Changed

- `backend/app/db/search_tables.py` — filled `drop_vector_tables` (DROP IF EXISTS both vec0 tables) and `rebuild_fts_indexes` (ensure, memo_fts 'rebuild', message_fts 'delete-all' + record-row back-fill)
- `backend/app/services/index_rebuild.py` — filled `rebuild_index` (one transaction: open handle, drop/re-create vec tables, chunked memo and session embedding, FTS rebuild) plus private `_embed_and_write` chunk helper
- `backend/app/models/admin_db.py` — `RebuiltTableName` + `RebuildReportResponse` (written complete by the skeleton; no coder change)
- `backend/app/routers/admin_db.py` — `POST /rebuild` route + module docstring (written complete by the skeleton; no coder change)
- `frontend/src/admin/databasePageState.ts` — filled `rebuildIndex`
- `frontend/src/admin/DatabasePage.tsx` — Rebuild index button, page-local confirm state, ConfirmModal, completion line, rebuild failure Alert

## Skeleton

### Frozen interface (2026-10-06)
- `backend/app/db/search_tables.py` — `drop_vector_tables(connection: Connection) -> None` — new
- `backend/app/db/search_tables.py` — `rebuild_fts_indexes(connection: Connection) -> None` — new
- `backend/app/services/index_rebuild.py` — `REBUILD_EMBED_BATCH_SIZE: int = 32` (not `Final`; read at call time so tests can monkeypatch) — new
- `backend/app/services/index_rebuild.py` — `rebuild_index(connection: Connection, *, client_factory: LlmClientFactory, timeout_seconds: float) -> RebuildReportResponse` — new (opens its own `with connection.begin():`)
- `backend/app/models/admin_db.py` — `RebuiltTableName = Literal["memo_vec", "session_vec", "memo_fts", "message_fts"]`; `class RebuildReportResponse(BaseModel): tables_rebuilt: list[RebuiltTableName]` — new
- `backend/app/routers/admin_db.py` — `@router.post("/rebuild", status_code=200) def rebuild_search_index(connection: Annotated[Connection, Depends(get_connection)], settings: Annotated[Settings, Depends(get_settings)], client_factory: Annotated[LlmClientFactory, Depends(get_llm_client_factory)]) -> RebuildReportResponse` — new; wired to call `rebuild_index(connection, client_factory=..., timeout_seconds=settings.llm_request_timeout_seconds)` (fails via the service stub). Module docstring updated ("Six routes"; the "no rebuild route" line replaced).
- `frontend/src/admin/databasePageState.ts` — `export type DatabaseRebuildStatus = "idle" | "rebuilding"` — new
- `frontend/src/admin/databasePageState.ts` — `DatabasePageState` fields `rebuildStatus: DatabaseRebuildStatus = "idle"`, `rebuildErrorMessage: string | null = null`, `rebuildComplete: boolean = false` — new. No store confirm-open flag: the Import confirm keeps no open flag in the store (its openness is derived), so the rebuild confirm's open state is page-local `useState` in `DatabasePage.tsx`, like the Sync confirm.
- `frontend/src/admin/databasePageState.ts` — `export const DATABASE_REBUILD_PATH = "/api/admin/database/rebuild"`; `export async function rebuildIndex(state: DatabasePageState, signal?: AbortSignal): Promise<void>` — new
- `frontend/src/admin/DatabasePage.tsx` — no signature change (UI only; coder adds the button, confirm, completion line and Alert).
- Caller-compile edits (out of Source-files scope): None.

## Tests

### Tests (2026-10-06)
- `backend/tests/test_admin_db_rebuild.py` — covers DoD-1..DoD-14 — route 200 + fixed four-name body; memo/session vectors for two owners (blank memo none); orphans dropped; re-declare at designated dim from other-dim and from absent tables; batch-size monkeypatch (1, 2) loses nothing and caps each embed call; lost memo/record FTS rows restored; zone/buried never in `message_fts`; memo created via API after rebuild is FTS-searchable (memo triggers dropped beforehand); 409 `no_embedding_model` and 502 `llm_unreachable` leave vector rows, dims and FTS contents unchanged; 403/401 change nothing; empty vs populated response identical and free of user text.
- `frontend/tests/admin/databasePageRebuild.test.ts` — covers DoD-15, DoD-16 — `rebuildIndex` POSTs exactly the route, sets completion/idle/null error on 200; on 409 and network failure stores a non-empty message, completion false, idle, no reject, drift/import/export slots untouched; in flight it is rebuilding with completion and error cleared.
- Re-route (2026-10-06, TEST fault): backend seed's buried message now has `settled_at=None` (schema CHECK `ck_messages_buried_or_settled`); removed the two stub-green declaration/default DoD-15 store tests. Coverage map unchanged.
- `frontend/tests/admin/DatabasePage.rebuild.test.tsx` — covers DoD-17..DoD-20 — Rebuild index button in the Export/Import group, enabled in in-sync/drifted/missing/loading/failed report states; confirm mentions the expense, Cancel sends nothing; confirm loading while pending, closes on 200 with a count-free "rebuild complete" line; failure closes the confirm and shows a red inline Alert distinct from the drift alert, no notification.
- Coverage: DoD-1 ✓, DoD-2 ✓, DoD-3 ✓, DoD-4 ✓, DoD-5 ✓, DoD-6 ✓, DoD-7 ✓, DoD-8 ✓, DoD-9 ✓, DoD-10 ✓, DoD-11 ✓, DoD-12 ✓, DoD-13 ✓, DoD-14 ✓, DoD-15 ✓, DoD-16 ✓, DoD-17 ✓, DoD-18 ✓, DoD-19 ✓, DoD-20 ✓, DoD-21 [manual/live, no test]

### Tests (2026-10-07) — DoD-22, pre-existing tests updated to the rebuild surface
- `backend/tests/test_admin_db_router.py` — covers DoD-22 — `POST /rebuild` added to `EXPECTED_OPERATIONS` and the no-path-parameter arm; DoD-14 surface guard renamed `test_route_surface_has_no_vector_route_one_import_route_and_one_rebuild_route__DoD14`, admits `rebuild` on that one operation only (`vector`/`vec0` still rejected everywhere, import half unchanged); documentation guard narrowed to skip only the rebuild operation (non-vacuity assert added); `POST .../rebuild` removed from the out-of-scope list (other rebuild-shaped paths still armed). Tagged `F002_DoD22`.
- `backend/tests/privacy_audit_support.py` — covers DoD-22 — row 74 `POST /api/admin/database/rebuild` added to `ENUMERATED_ROUTES` as `admin`; `EXCLUDED_ROWS` now `{5}`; row 74 removed from `UNBUILT_SURFACES`.
- `backend/tests/test_privacy_audit_routes.py` — covers DoD-22 — `EXPECTED_ROW_COUNT` 72 -> 73, `EXCLUDED_ROWS == {5}`, rebuild operation enumerated; unbuilt guard now row 5 only.
- `backend/tests/test_privacy_audit_admin.py` — covers DoD-22 (and plan DoD-14 via 032's DoD-7 slot) — DoD-7 is now behavioural: ADM rebuild before and after extra seeding answers 200 with exactly `{"tables_rebuilt": ["memo_vec","session_vec","memo_fts","message_fts"]}`, identical, no number, no sentinel of A or B; row 74 enumerated as admin and registered. DoD-3 mutation sweep holds the rebuild out by name (like import) since its response is swept by DoD-7; the 14-mutation count is unchanged.
- `frontend/tests/admin/databasePage.test.tsx` — covers DoD-22 — "nothing out of scope on the page": control/readable-text clauses admit exactly one `Rebuild index` control and its label, any other rebuild/re-index still fails; outside-table controls = Export, Import (order kept) + exactly one Rebuild index; source-literal clause now rejects re-index wording only; `ALLOWED_FIELDS` + `rebuildComplete`, `rebuildErrorMessage`, `rebuildStatus`.
- `frontend/tests/admin/databaseActions.test.tsx` — covers DoD-22 — page-wide "no Rebuild/Re-index control" inverted to "exactly the one page-level Rebuild index control" (row menu open; row-menu clause keeps forbidding Rebuild); `ALLOWED_FIELDS` + the three rebuild fields.
- Coverage: DoD-22 ✓ (suite-green half is the verifier's run)

## Notes & Issues

- Added private helper `_embed_and_write` in `services/index_rebuild.py` (chunking loop shared by memos and sessions); no public symbol added. The confirm button label is "Rebuild" (not "Rebuild index") so it does not collide with the page button's accessible name while the modal is open.
- Plan amendment (2026-10-07, user-approved): Test files widened with an "Update existing" list — `backend/tests/test_admin_db_router.py`, `backend/tests/privacy_audit_support.py`, `backend/tests/test_privacy_audit_routes.py`, `backend/tests/test_privacy_audit_admin.py`, `frontend/tests/admin/databasePage.test.tsx`, `frontend/tests/admin/databaseActions.test.tsx` — so the test-coder can update pre-existing tests that encode the earlier "no rebuild surface" rule this feature overturns. New DoD-22 `[test]` covers it (suites green, no other assertion weakened). Source code is unchanged by the amendment; DoD-22 is not yet covered.
