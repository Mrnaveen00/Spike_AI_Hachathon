"""
MCP (Model Context Protocol) module
Tool registry and dispatcher for safe tool execution
"""

from app.mcp.tools import (
    get_tool,
    list_tools,
    set_ga4_executor,
    set_seo_executor,
    ToolDefinition
)
from app.mcp.dispatcher import get_dispatcher, MCPDispatcher

__all__ = [
    "get_tool",
    "list_tools",
    "set_ga4_executor",
    "set_seo_executor",
    "ToolDefinition",
    "get_dispatcher",
    "MCPDispatcher"
]
