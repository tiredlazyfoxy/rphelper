"""`GET /api/health` — the readiness probe's transport layer, and the only router here.

Unauthenticated by design: the body names no table contents and no user, and the
`bootstrap` entry has to be able to ask whether bootstrap is on offer before any session
exists. There is deliberately **no authentication dependency of any kind** in this
module — `require_unconfigured`, `require_user` and `require_role` belong to feature
`004`.

All three `status` values answer **200**. The body *is* the answer and all three
consumers need to read it; `"degraded"` returned as a 503 would make the SPA's fetch
path treat a reportable condition as a transport failure and discard the very body that
explains it. A probe that cannot read the database at all is a different thing — an
operational fault, which surfaces as a 500, and is what makes this endpoint capable of
failing at all.

The route **issues no SQL** and holds no rule: it takes step `005`'s connection
dependency, hands it and the registry to `app.services.health.probe_health`, and maps
the plain result onto the response model. This module is where `metadata` is imported
and passed in, so that the service keeps the registry as a parameter.

It returns the **pydantic model**, never a plain `dict` and never a `JSONResponse`. That
is not tidiness: a route returning a `dict` bypasses `models/` and therefore bypasses
the JSON id boundary. No id appears in this response, which is exactly why holding the
rule at the first router costs nothing.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Connection

from app.db.engine import get_connection
from app.db.schema import metadata
from app.models.health import HealthResponse
from app.services.health import probe_health

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def read_health(connection: Annotated[Connection, Depends(get_connection)]) -> HealthResponse:
    """Answer the readiness probe. Always 200; the body carries the verdict.

    A synchronous path operation on purpose: the probe's `sqlite_master` read is
    blocking I/O, so FastAPI runs this in its threadpool rather than on the event loop.

    It issues no SQL itself: it hands the connection and the registry to the probe and
    maps the plain result onto the response model.
    """
    result = probe_health(connection, metadata)
    return HealthResponse(status=result.status, configured=result.configured, schema_=result.schema)
