"""Tools — the three declarations and the dispatch seam (feature `021`, step `004`)."""

from app.services.tools.seam import (
    PRODUCTION_TOOL_REGISTRY,
    TOOL_FAILED_CONTENT,
    TOOL_FAILED_ROW_TEXT,
    DispatchResult,
    Tool,
    ToolOutcome,
    ToolRegistry,
    ToolScope,
    build_tool_scope,
    dispatch,
    offered_tools,
    tool_start_frame,
)

__all__ = [
    "PRODUCTION_TOOL_REGISTRY",
    "TOOL_FAILED_CONTENT",
    "TOOL_FAILED_ROW_TEXT",
    "DispatchResult",
    "Tool",
    "ToolOutcome",
    "ToolRegistry",
    "ToolScope",
    "build_tool_scope",
    "dispatch",
    "offered_tools",
    "tool_start_frame",
]
