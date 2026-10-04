"""Context assembly — what the assistant reads for one session, and in what order.

Feature `020`. Step `001` adds the pure part: the forced-note level value, the system-prompt
renderer and the message mapper. Step `002` adds the assembler. Stored text enters verbatim;
the only addition is the kind tag on settled rows (D1, R12). No logging, no caching, no
compaction (D11, D12).
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from sqlalchemy import Connection

from app.services import characters, configuration, memo_chain, messages, sessions
from app.services.llm.chat import ChatMessage, ChatRole, ToolCall, strip_think
from app.services.messages import StreamMessage

ForcedNoteScope = Literal["user", "character", "setup", "session"]
"""The four chain levels, as plain strings (the same values as 015's scope literal)."""

HEADING_SYSTEM_PROMPT: Final = "=== System prompt ==="
HEADING_CHARACTER_SHEET: Final = "=== Character sheet ==="
HEADING_FORCED_NOTES: Final = "=== Forced notes ==="
HEADING_MESSAGE_TAGS: Final = "=== Message tags ==="
HEADING_LANGUAGES: Final = "=== Languages ==="
HEADING_DOUBLE_PARENTHESES: Final = "=== Double parentheses ==="

LEVEL_HEADINGS: Final[dict[str, str]] = {
    "user": "--- User notes ---",
    "character": "--- Character notes ---",
    "setup": "--- Setup notes ---",
    "session": "--- Session notes ---",
}
NOTE_MARKER: Final = "[note]"

KIND_TAGS: Final[dict[str, str]] = {
    "partner": "[partner]",
    "turn": "[my turn]",
    "decision": "[decision]",
}

FALLBACK_LANGUAGE: Final = "English"

MESSAGE_TAGS_LINES: Final = (
    "- [partner]: a message starting with this tag is the partner's settled text, "
    "not the roleplayer's.",
    "- [my turn]: a message starting with this tag is the roleplayer's own settled turn "
    "in the record.",
    "- [decision]: a message starting with this tag is a settled out-of-character decision; "
    "treat it as standing context from that point on.",
    "- Untagged: a message without a tag belongs to the live current discussion below the "
    "record.",
)

CANDIDATES_LINE: Final = (
    "- Candidates: always write candidate prose for the roleplayer's turn in {language}, "
    "whatever language the discussion is in, out of character or not."
)
MIRRORING_LINE: Final = (
    "- Mirroring: answer each message in the language that message is written in."
)
OUT_OF_CHARACTER_LINE: Final = (
    "- Out of character: out-of-character exchanges are in {language}; answer them in kind."
)

DOUBLE_PARENTHESES_LINES: Final = (
    "- Wholly parenthesised: a message written entirely inside (( )) is out-of-character "
    "talk about the roleplay; answer it in kind, not with prose.",
    "- Fragment: a (( )) fragment inside a draft is an instruction to apply to the "
    "surrounding prose; never reproduce the fragment itself.",
)


@dataclass(frozen=True)
class ForcedNoteLevel:
    """One chain level's forced notes: its scope and the bodies, in order."""

    scope: ForcedNoteScope
    bodies: Sequence[str]


def render_system_prompt(
    system_prompt: str | None,
    sheet: str,
    forced_levels: Sequence[ForcedNoteLevel],
    rp_language: str | None,
    preferred_language: str | None,
) -> str:
    """Render the system-prompt string in the fixed six-section format. Pure; never raises."""
    sections: list[str] = []
    if system_prompt is not None:
        sections.append(HEADING_SYSTEM_PROMPT + "\n" + system_prompt)
    if sheet.strip():
        sections.append(HEADING_CHARACTER_SHEET + "\n" + sheet)

    blocks: list[str] = []
    for level in forced_levels:
        if not level.bodies:
            continue
        notes = "\n\n".join(NOTE_MARKER + "\n" + body for body in level.bodies)
        blocks.append(LEVEL_HEADINGS[level.scope] + "\n" + notes)
    if blocks:
        sections.append(HEADING_FORCED_NOTES + "\n" + "\n\n".join(blocks))

    sections.append(HEADING_MESSAGE_TAGS + "\n" + "\n".join(MESSAGE_TAGS_LINES))

    rp = rp_language if rp_language is not None else FALLBACK_LANGUAGE
    preferred = preferred_language if preferred_language is not None else FALLBACK_LANGUAGE
    language_lines = (
        CANDIDATES_LINE.format(language=rp),
        MIRRORING_LINE,
        OUT_OF_CHARACTER_LINE.format(language=preferred),
    )
    sections.append(HEADING_LANGUAGES + "\n" + "\n".join(language_lines))

    sections.append(HEADING_DOUBLE_PARENTHESES + "\n" + "\n".join(DOUBLE_PARENTHESES_LINES))
    return "\n\n".join(sections)


def to_chat_messages(
    entries: Sequence[StreamMessage],
    zone: Sequence[StreamMessage],
) -> list[ChatMessage]:
    """Merge settled and zone rows by id ascending into chat messages. Pure.

    A current-zone assistant row is think-stripped (feature `021` D4); a tool row is replayed
    as an assistant call plus its tool result, or skipped when it cannot be replayed (D9).
    """
    zone_ids = {row.id for row in zone}
    result: list[ChatMessage] = []
    for row in sorted([*entries, *zone], key=lambda message: message.id):
        if row.role == "tool":
            result.extend(_replay_tool_row(row))
            continue
        role: ChatRole
        if row.role == "user":
            role = "user"
        elif row.role == "assistant":
            role = "assistant"
        else:
            continue
        body = row.text
        if role == "assistant" and row.id in zone_ids:
            body = strip_think(body)
        tag = KIND_TAGS.get(row.kind) if row.kind is not None else None
        content = body if tag is None else tag + "\n" + body
        result.append(ChatMessage(role=role, content=content))
    return result


def _replay_tool_row(row: StreamMessage) -> list[ChatMessage]:
    """One tool row as its assistant call and tool result (D9); empty when not replayable."""
    if row.tool_name is None or row.tool_payload is None:
        return []
    try:
        payload = json.loads(row.tool_payload)
    except ValueError:
        return []
    if not isinstance(payload, dict):
        return []
    call_id = payload.get("call_id")
    arguments = payload.get("arguments")
    status = payload.get("status")
    if not isinstance(call_id, str) or not isinstance(arguments, str) or status is None:
        return []
    if status == "ok":
        content = payload.get("content")
        if not isinstance(content, str):
            return []
    else:
        content = "The tool failed. Continue without its result."
    return [
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=(ToolCall(call_id=call_id, name=row.tool_name, arguments=arguments),),
        ),
        ChatMessage(role="tool", content=content, tool_call_id=call_id),
    ]


@dataclass(frozen=True)
class AssembledContext:
    """What `021` sends to the model: the rendered system prompt and the ordered messages."""

    system_prompt: str
    messages: Sequence[ChatMessage]


def assemble_context(connection: Connection, user_id: int, session_id: int) -> AssembledContext:
    """Assemble one session's context from owner-scoped reads, live (D11).

    Raises `SessionNotFoundError` for a missing or another user's session before anything
    else is read. Opens no transaction of its own, writes nothing, caches nothing.
    """
    session = sessions.get_session(connection, user_id, session_id)
    config = configuration.get_session_configuration(connection, user_id, session_id)
    character = characters.get_character(connection, user_id, session.character_id)
    forced_levels = [
        ForcedNoteLevel(
            scope=level.scope,
            bodies=tuple(
                memo.body
                for memo in level.memos
                if memo_chain.memo_reach(memo.is_enabled, memo.is_forced) == "forced"
            ),
        )
        for level in memo_chain.resolve_chain(connection, user_id, session_id)
    ]
    entries = messages.list_entries(connection, user_id, session_id)
    zone = messages.list_zone(connection, user_id, session_id)
    system_prompt = render_system_prompt(
        config.system_prompt.value,
        character.sheet,
        forced_levels,
        config.rp_language.value,
        config.preferred_language.value,
    )
    return AssembledContext(
        system_prompt=system_prompt,
        messages=tuple(to_chat_messages(entries, zone)),
    )
