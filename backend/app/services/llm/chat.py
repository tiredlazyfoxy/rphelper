"""The neutral chat-message value type — what the assembler returns and the client consumes.

Feature `020`, step `001`. A sibling of `client.py` so feature `021`'s client can import the
type without importing the assembler. Imports nothing from any `app.services.` module (D9).
"""

from dataclasses import dataclass
from typing import Literal

ChatRole = Literal["user", "assistant"]
"""The two chat roles a mapped message can carry."""


@dataclass(frozen=True)
class ChatMessage:
    """One chat message: its role and its content, verbatim."""

    role: ChatRole
    content: str
