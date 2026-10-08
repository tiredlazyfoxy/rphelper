"""The JSON id boundary — the only place an id crosses between `int` and string.

`docs/architecture/backend-structure.md` § The JSON id boundary declares both aliases
verbatim; they are reproduced here exactly. An id is an `int` in SQLite and in Python
and a **decimal string** in every JSON payload — request bodies, response bodies, a
`DomainError`'s `detail` and SSE frames alike. Nothing in the API surface exposes an id
as a JSON number: a snowflake passes `Number.MAX_SAFE_INTEGER` about 25 days after the
epoch, so an id reaching JavaScript as a number silently rounds, possibly onto another
row's id.

`SnowflakeOut` serialises an `int` field to a `str`; `SnowflakeIn` parses an inbound
value to `int` before validation.
"""

from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer

SnowflakeOut = Annotated[int, PlainSerializer(str, return_type=str)]
SnowflakeIn = Annotated[int, BeforeValidator(lambda v: int(v))]
