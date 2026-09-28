"""The readiness probe — a service by construction, not a domain service (decision D10).

`backend-structure.md`'s services list does not name this module. It exists because the
probe issues SQL and the routers/services split this feature establishes forbids a
router from issuing SQL: "A router contains no business rule and issues no SQL." Nothing
here enforces a rule from `domain-rules.md` and nothing here takes a `user_id`, so
`brief.md`'s "no domain router or service" exclusion is untouched.

Being a service, this module **never imports `fastapi`, never sees a `Request` and never
knows a status code** — DoD-7 and DoD-14 both check exactly that. It takes a plain Core
`Connection` and a plain `MetaData` and returns a plain result.

The registry arrives as a **parameter, not a module import**: that is what makes the
`"missing"` branch reachable in a test today, before any table exists. Do not add
`from app.db.schema import metadata` here — the router passes it in.

The probe does the cheap `sqlite_master` read the architecture insists on — "a health
check that cannot fail tells an operator nothing" — and answers honestly (decision D3).
Against this feature's empty registry `schema` is trivially `"ok"`, which is correct and
not a stub: the probe answers the question it was asked, "is every declared table
present?", and with nothing declared the answer is yes. Feature `003` sharpens
`configured` and feature `007` adds the `"drift"` branch; both are widenings of this
function, not rewrites of it.
"""

from dataclasses import dataclass

from sqlalchemy import Connection, MetaData, text

from app.models.health import HealthStatus, SchemaState


@dataclass(frozen=True)
class HealthProbeResult:
    """The three values the probe reports, as plain data.

    Carries no transport concern: no status code, no headers, no request. The router
    maps it onto `app.models.health.HealthResponse` and does nothing else.
    """

    status: HealthStatus
    configured: bool
    schema: SchemaState


def probe_health(connection: Connection, registry: MetaData) -> HealthProbeResult:
    """Read `sqlite_master` and report what actually exists.

    - `configured` is true only once a `users` table is present **and** holds at least
      one row whose role is administrator. A present-but-empty `users` table is false.
    - `schema` is `"missing"` when any table in `registry` is absent from
      `sqlite_master`, and `"ok"` when every one is present. An empty registry is
      trivially `"ok"`.
    - `status` rolls the two up, in this precedence: a `schema` other than `"ok"` gives
      `"degraded"`; otherwise `configured` being false gives `"unconfigured"`;
      otherwise `"ok"`.

    Opens no transaction of its own beyond what the reads need, and writes nothing.
    """
    present = {
        str(row[0])
        for row in connection.execute(
            text("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
        ).fetchall()
    }

    configured = False
    if "users" in present:
        administrator = connection.execute(
            text("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1")
        ).first()
        configured = administrator is not None

    declared = {table.name for table in registry.tables.values()}
    schema: SchemaState = "ok" if declared <= present else "missing"

    if schema != "ok":
        status: HealthStatus = "degraded"
    elif not configured:
        status = "unconfigured"
    else:
        status = "ok"

    return HealthProbeResult(status=status, configured=configured, schema=schema)
