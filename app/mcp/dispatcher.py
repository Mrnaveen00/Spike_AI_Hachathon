"""
MCP Dispatcher
Validates and executes tools safely
"""

import logging
from typing import Dict, Any, List, Optional

from app.mcp.tools import get_tool, list_tools

logger = logging.getLogger(__name__)


class MCPDispatcher:
    """
    Dispatcher for MCP tools
    
    Responsibilities:
    - Validate tool name
    - Validate arguments
    - Execute correct agent
    - Catch errors
    - Return structured JSON
    """
    
    def __init__(self):
        """Initialize MCP dispatcher"""
        logger.info("MCP Dispatcher initialized")
    
    async def execute_tools(self, tool_plan: Dict[str, Any], property_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute tools from a tool plan
        
        Args:
            tool_plan: Tool execution plan with {"tools": [...]}
            property_id: Optional GA4 property ID
            
        Returns:
            {
                "tool_name": {
                    "status": "success" | "error",
                    "data": {...} | None,
                    "error": str | None
                },
                ...
            }
        """
        tools = tool_plan.get("tools", [])
        
        if not tools:
            logger.warning("No tools in plan")
            return {}
        
        results = {}
        
        for tool_spec in tools:
            tool_name = tool_spec.get("name")
            tool_args = tool_spec.get("arguments", {})
            
            # Execute tool and store result
            result = await self.execute_tool(tool_name, tool_args, property_id)
            results[tool_name] = result
        
        logger.info(f"Executed {len(results)} tools")
        return results
    
    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any], property_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute a single tool
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            property_id: Optional GA4 property ID
            
        Returns:
            {
                "status": "success" | "error",
                "data": {...} | None,
                "error": str | None
            }
        """
        try:
            # Step 1: Validate tool name (also checks executor is registered)
            tool_def = self._validate_tool_name(tool_name)
            
            # Step 2: Validate arguments (basic validation)
            self._validate_arguments(tool_name, arguments, tool_def.input_schema)
            
            # Step 3: Execute tool via agent
            logger.info(f"Executing tool: {tool_name}")
            
            # Build execution context
            context = {"property_id": property_id} if property_id else {}
            
            # Call executor
            data = await tool_def.executor(arguments, context)
            
            # Step 4: Return structured success response
            return {
                "status": "success",
                "data": data,
                "error": None
            }
        
        except Exception as e:
            # Step 6: Catch errors and return structured error response
            logger.error(f"Tool execution failed ({tool_name}): {str(e)}")
            return {
                "status": "error",
                "data": None,
                "error": str(e)
            }
    
    def _validate_tool_name(self, tool_name: str):
        """
        Validate tool name exists in registry and executor is registered
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Tool definition
            
        Raises:
            ValueError: If tool name is invalid or empty
            RuntimeError: If tool executor not registered
        """
        if not tool_name:
            raise ValueError("Tool name cannot be empty")
        
        try:
            tool_def = get_tool(tool_name)  # Also checks executor is registered
            logger.debug(f"Tool validated: {tool_name}")
            return tool_def
        except ValueError as e:
            allowed_tools = list_tools()
            raise ValueError(
                f"Invalid tool: {tool_name}. Allowed tools: {allowed_tools}"
            ) from e
    
    def _validate_arguments(self, tool_name: str, arguments: Dict[str, Any], schema: Dict[str, Any]) -> None:
        """
        Validate tool arguments against schema (basic validation)
        
        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            schema: Input schema
            
        Raises:
            ValueError: If arguments are invalid
        """
        # Basic validation: ensure arguments is a dictionary
        if not isinstance(arguments, dict):
            raise ValueError(f"Arguments must be a dictionary for tool: {tool_name}")
        
        # More sophisticated schema validation can be added here
        # For now, we trust the LLM to generate valid arguments
        # and rely on the agent to handle invalid values
        
        logger.debug(f"Arguments validated for: {tool_name}")


# Singleton instance
_dispatcher: Optional[MCPDispatcher] = None


def get_dispatcher() -> MCPDispatcher:
    """Get or create MCP dispatcher singleton"""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = MCPDispatcher()
    return _dispatcher
