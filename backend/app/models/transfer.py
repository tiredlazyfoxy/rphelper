"""The two roleplayer import response models — nothing else.

Feature `031`, step `005` (`context.md` §"Wire contract"; FEAT-018; UC-062..UC-064; US-079.AC-2,
US-080.AC-2, US-082.AC-1, US-082.AC-2, US-136.AC-2).

**There is no request model here, and no export model at all.** Both import routes take the raw
JSON object as their body (`005.context.md` §"Why the bodies are raw objects"): the envelope is
column-agnostic, so no static model can describe it, and the service validates it. 030's three
`GET` export routes answer a raw `Response` attachment for the same reason. So this module holds
exactly the two **success answers** the two `POST` routes return, and the admin database import —
which answers **204** with no body — has no model at all.

**Every id leaves as a decimal string** (`backend-structure.md` §"The JSON id boundary"): the ids
use `SnowflakeOut`, never a bare `int`, because a snowflake passes `Number.MAX_SAFE_INTEGER` and
would silently round in the browser. Both models are **id-only**: no row content, no name, no
title, no timestamp and no `user_id` travels back, so there is nothing for the route to redact
(R5, `domain-rules.md`).

`OwnedImportGranularity` re-declares the two values `POST /api/import` accepts rather than
importing 030's four-value `ExportGranularity` from `app.services.transfer` — the same local
narrowing `models/admin_db.py` does with `TableStatusValue` against `app.db.drift.TableStatus`,
and it keeps this module free of any `app.services` import.

This module imports neither `app.services`, `app.routers`, `app.db` nor `fastapi`.
"""

from typing import Literal

from pydantic import BaseModel

from app.models.ids import SnowflakeOut

#: The granularities `POST /api/import` accepts — 030's `ExportGranularity` minus `database` and
#: `session`, which that route refuses with 400 `export_invalid` / `wrong_granularity`.
OwnedImportGranularity = Literal["user", "character"]


class OwnedImportResponse(BaseModel):
    """`POST /api/import`'s whole 200 answer — the wire form of `OwnedImportResult`.

    `character_ids` holds the **new** ids of every character the import created, ascending: exactly
    one entry for a `character` envelope, one per payload character for a `user` envelope, and an
    empty list when a `user` payload carried none (`context.md` §"Wire contract").
    """

    granularity: OwnedImportGranularity
    character_ids: list[SnowflakeOut]


class SessionImportResponse(BaseModel):
    """`POST /api/characters/{character_id}/import`'s whole 200 answer — the new session's id.

    One field and no more: the character the session landed under came from the path, and the
    session's content is read back through `GET /api/sessions/{session_id}` (US-082.AC-2).
    """

    session_id: SnowflakeOut
