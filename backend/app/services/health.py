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

The probe touches the database as the architecture insists — "a health check that
cannot fail tells an operator nothing" — and answers honestly (decision D3). Since
feature `007` its `schema` answer is `db/drift.py`'s report over the registry, uncached.
Against this feature's empty registry `schema` is trivially `"ok"`, which is correct and
not a stub: the probe answers the question it was asked, "is every declared table
present?", and with nothing declared the answer is yes. Feature `003` sharpens
`configured` and feature `007` adds the `"drift"` branch; both are widenings of this
function, not rewrites of it.
"""

from dataclasses import dataclass

from sqlalchemy import Connection, MetaData

from app.db.drift import build_drift_report, report_has_drift, report_has_missing
from app.models.health import HealthStatus, SchemaState
from app.services.bootstrap import is_configured


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
    """Report what actually exists, reading the registry's drift report.

    - `configured` is true only once a `users` table is present **and** holds at least
      one row whose role is administrator. A present-but-empty `users` table is false.
    - `schema` is `"missing"` when any table in `registry` is absent, `"drift"` when
      every one is present and at least one differs from its declaration, and `"ok"`
      otherwise (feature 007, D10). An empty registry is trivially `"ok"`. The answer
      is one word and names no table.
    - `status` rolls the two up, in this precedence: a `schema` other than `"ok"` gives
      `"degraded"`; otherwise `configured` being false gives `"unconfigured"`;
      otherwise `"ok"`.

    Opens no transaction of its own beyond what the reads need, and writes nothing.
    """
    # The one definition of the fact lives in `services/bootstrap.py`; the probe and the
    # bootstrap guard must never disagree, so this branch delegates rather than copies.
    configured = is_configured(connection)

    # Missing outranks drift: a table that does not exist fails every query against it.
    report = build_drift_report(connection, registry)
    schema: SchemaState
    if report_has_missing(report):
        schema = "missing"
    elif report_has_drift(report):
        schema = "drift"
    else:
        schema = "ok"

    if schema != "ok":
        status: HealthStatus = "degraded"
    elif not configured:
        status = "unconfigured"
    else:
        status = "ok"

    return HealthProbeResult(status=status, configured=configured, schema=schema)
