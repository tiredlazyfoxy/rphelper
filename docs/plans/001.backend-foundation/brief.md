# 001.backend-foundation — Backend foundation
<!-- roadmap:start -->
- **Stage:** 001.instance · **Track:** multi-step · **Size:** M
- **Depends on:** —

## Definition
Stands the FastAPI application up as an empty but complete skeleton that everything later plugs into. After this feature a developer can start uvicorn, hit a readiness endpoint that touches the database, and get a typed error object back from a deliberate failure. It establishes the four conventions no later feature may re-decide: the snowflake id generator, the rule that an id is an int inside and a decimal string on the wire, the typed error hierarchy the SPA renders, and the table-definition registry that is the schema's source of truth.

## Scope
**In:**
- the app factory and router registration
- `pydantic-settings` `Settings` with `RPHELPER_` aliases and the cached accessor
- loguru sink configuration with the `InterceptHandler` and the absolute redaction rule
- the snowflake generator with its lock, config node id and backwards-clock refusal
- the `"$ENV_VAR"` secret-pointer resolver
- the typed error hierarchy and its exception handlers
- the SQLAlchemy Core engine with PRAGMAs and the `sqlite-vec` extension load
- the empty table-definition registry
- `GET /api/health`
- the `SnowflakeIn`/`SnowflakeOut` model aliases
- the routers/services split as an enforced convention

**Out:**
- any table definition (each content feature adds its own)
- any domain router or service
- the drift report and the DDL executor (`007`)
- authentication (`004`)
- the LLM client (`006`)
- `GET /api/me` (`004`)

## Open questions for the planner
- Which PRAGMAs are set at connect time and which per transaction, and whether WAL mode is set once at first open or asserted on every connection.
- Whether the registry is a module-level list of `Table` objects or a callable that builds them, given `007` must introspect it.
<!-- roadmap:end -->
