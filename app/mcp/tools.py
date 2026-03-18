"""
MCP Tool Registry
Defines allowed tools with schemas to prevent hallucinated API calls
"""

import logging
from typing import Dict, Any, List, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """Definition of a tool with name, schema, and executor"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    executor: Callable  # Async function that executes the tool


# Tool Registry - Single source of truth for allowed tools
TOOL_REGISTRY: Dict[str, ToolDefinition] = {}


def register_tool(tool_def: ToolDefinition) -> None:
    """
    Register a tool in the registry
    
    Args:
        tool_def: Tool definition with name, schema, and executor
    """
    TOOL_REGISTRY[tool_def.name] = tool_def
    logger.info(f"Registered tool: {tool_def.name}")


def get_tool(tool_name: str) -> ToolDefinition:
    """
    Get tool definition by name
    
    Args:
        tool_name: Name of the tool
        
    Returns:
        Tool definition
        
    Raises:
        ValueError: If tool not found
        RuntimeError: If tool executor not registered
    """
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool: {tool_name}. Allowed tools: {list(TOOL_REGISTRY.keys())}")
    
    tool = TOOL_REGISTRY[tool_name]
    
    # CRITICAL: Enforce that executor MUST be set before execution
    if tool.executor is None:
        raise RuntimeError(
            f"Tool '{tool_name}' is registered but has no executor attached. "
            f"Agents must register executors before use."
        )
    
    return tool


def list_tools() -> List[str]:
    """
    List all registered tool names
    
    Returns:
        List of tool names
    """
    return list(TOOL_REGISTRY.keys())


# ============================================================================
# TOOL DEFINITIONS
# ============================================================================

# Tool 1: GA4 Analytics Report
GA4_RUN_REPORT = ToolDefinition(
    name="ga4.run_report",
    description="Fetch Google Analytics 4 data (metrics, dimensions, date ranges)",
    input_schema={
        "type": "object",
        "required": ["metrics", "dimensions", "dateRange"],
        "properties": {
            "metrics": {
                "type": "array",
                "items": {"type": "string"},
                "description": "GA4 metrics (e.g., sessions, totalUsers, screenPageViews)",
                "minItems": 1
            },
            "dimensions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "GA4 dimensions (e.g., date, pagePath, country)"
            },
            "dateRange": {
                "type": "string",
                "description": "Date range (e.g., last7Days, last30Days, YYYY-MM-DD:YYYY-MM-DD)"
            },
            "filters": {
                "type": "object",
                "description": "Optional filters for the report"
            }
        }
    },
    executor=None  # Will be set when analytics agent is implemented
)

# Tool 2: SEO URL Filter
SEO_FILTER_URLS = ToolDefinition(
    name="seo.filter_urls",
    description="Query SEO metadata from Google Sheets (titles, descriptions, keywords)",
    input_schema={
        "type": "object",
        "properties": {
            "filters": {
                "type": "object",
                "description": "Filters to apply (e.g., url, title, status)"
            },
            "columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Columns to return (e.g., url, title, meta_description)",
                "minItems": 1
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "minimum": 1,
                "maximum": 1000
            }
        }
    },
    executor=None  # Will be set when SEO agent is implemented
)


# ============================================================================
# INITIALIZE REGISTRY
# ============================================================================

def initialize_registry():
    """Initialize the tool registry with all available tools"""
    register_tool(GA4_RUN_REPORT)
    register_tool(SEO_FILTER_URLS)
    logger.info(f"Tool registry initialized with {len(TOOL_REGISTRY)} tools")


# Auto-initialize on import
initialize_registry()


# ============================================================================
# EXECUTOR SETTERS (called by agents when they're initialized)
# ============================================================================

def set_ga4_executor(executor: Callable):
    """
    Set the executor function for GA4 tool
    
    Args:
        executor: Async function that executes GA4 queries
    """
    GA4_RUN_REPORT.executor = executor
    TOOL_REGISTRY["ga4.run_report"] = GA4_RUN_REPORT
    logger.info("GA4 executor registered")


def set_seo_executor(executor: Callable):
    """
    Set the executor function for SEO tool
    
    Args:
        executor: Async function that executes SEO queries
    """
    SEO_FILTER_URLS.executor = executor
    TOOL_REGISTRY["seo.filter_urls"] = SEO_FILTER_URLS
    logger.info("SEO executor registered")
