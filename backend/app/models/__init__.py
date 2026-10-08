"""Pydantic request and response models — the only layer that converts an id.

`models/` is imported by both `app.routers` and `app.services` and imports neither.

**Every id-typed field on a pydantic model uses one of the two aliases re-exported
here**: `SnowflakeOut` on a response model, `SnowflakeIn` on a request model. **A bare
`int` id field is the defect.** No handler hand-rolls the conversion — a route that
returns a plain `dict` or a `JSONResponse` bypasses this package and therefore bypasses
the rule, so routes return pydantic models. The rule reaches the places nobody thinks
of too: an id inside a `DomainError`'s `detail`, and the ids on SSE frames.

Import the aliases from this package, so there is one place to import them from.
"""

from app.models.ids import SnowflakeIn, SnowflakeOut

__all__ = ["SnowflakeIn", "SnowflakeOut"]
