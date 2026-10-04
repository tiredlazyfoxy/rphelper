"""The translate route's response model — nothing else (feature `023`, wire contract).

`TranslationResponse` is the wire `Translation`: exactly four keys. `message_id` uses the
outbound snowflake alias, so it leaves as a **decimal string**. `cached` is true when the
server answered from `translations` without a model call. It is built from a service
result's attributes.

This module imports neither `app.services`, `app.routers`, `app.db` nor `fastapi`.
"""

from pydantic import BaseModel, ConfigDict

from app.models.ids import SnowflakeOut


class TranslationResponse(BaseModel):
    """One partner row's translation on the wire: `message_id`, `target_language`, `text`,
    `cached`."""

    model_config = ConfigDict(from_attributes=True)

    message_id: SnowflakeOut
    target_language: str
    text: str
    cached: bool
