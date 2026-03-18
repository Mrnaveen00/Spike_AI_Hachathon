"""
Analytics Agent - TIER 1 (MOST CRITICAL)
Executes GA4 analytics queries with validation and error handling
"""

import logging
from typing import Dict, Any, Optional

from app.ga4.client import get_ga4_client
from app.ga4.validator import validate_ga4_request, GA4ValidationError
from app.mcp.tools import set_ga4_executor

logger = logging.getLogger(__name__)


class AnalyticsAgent:
    """
    Agent for executing GA4 analytics queries
    
    Responsibilities:
    - Parse LLM-generated arguments
    - Validate metrics/dimensions/combinations
    - Call GA4 Data API
    - Return structured results
    - Handle errors gracefully
    """
    
    def __init__(self):
        """Initialize Analytics Agent"""
        self.ga4_client = None
        logger.info("Analytics Agent initialized")
    
    def _ensure_client(self):
        """Lazy-load GA4 client (only when needed)"""
        if self.ga4_client is None:
            try:
                self.ga4_client = get_ga4_client()
                logger.info("GA4 client loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load GA4 client: {e}")
                raise RuntimeError(
                    f"GA4 client initialization failed: {str(e)}. "
                    f"Ensure credentials.json exists in project root."
                ) from e
    
    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute GA4 analytics query
        
        Args:
            arguments: {
                "metrics": ["sessions", "totalUsers"],
                "dimensions": ["date", "country"],
                "dateRange": "last7Days",
                "filters": {...} (optional)
            }
            context: {
                "property_id": "properties/123456789"
            }
            
        Returns:
            {
                "rows": [...],
                "summary": {...}
            }
        """
        logger.info("Executing analytics query...")
        
        try:
            # Step 1: Extract and validate inputs
            metrics = arguments.get("metrics", [])
            dimensions = arguments.get("dimensions", [])
            date_range = arguments.get("dateRange", "last7Days")
            filters = arguments.get("filters")
            property_id = context.get("property_id")
            
            # Validate property ID first
            if not property_id:
                raise ValueError("Property ID is required in context")
            
            # CRITICAL FIX: Fallback for empty metrics (prevents validation failure)
            # Handle both missing metrics and explicitly empty metrics array
            if not metrics or (isinstance(metrics, list) and len(metrics) == 0):
                logger.warning("No metrics provided or empty metrics array, using fallback: totalUsers, sessions")
                metrics = ["totalUsers", "sessions"]
            
            # Fallback for empty dimensions (optional, but good practice)
            if dimensions is None:
                dimensions = []
            
            # Step 2: Validate GA4 request (CRITICAL - prevents API failures)
            logger.info("Validating GA4 request...")
            validate_ga4_request(metrics, dimensions, date_range)
            logger.info("Validation passed")
            
            # Step 3: Ensure GA4 client is initialized
            self._ensure_client()
            
            # Step 4: Call GA4 Data API
            logger.info(f"Calling GA4 API: {len(metrics)} metrics, {len(dimensions)} dimensions")
            result = await self.ga4_client.run_report(
                property_id=property_id,
                metrics=metrics,
                dimensions=dimensions,
                date_range=date_range,
                filters=filters
            )
            
            # Step 5: Return structured result
            logger.info(f"Analytics query successful: {result['summary']['total_rows']} rows")
            return result
        
        except GA4ValidationError as e:
            # Validation errors - clear message for LLM
            logger.error(f"GA4 validation failed: {e}")
            return {
                "rows": [],
                "summary": {
                    "total_rows": 0,
                    "error": "validation_error",
                    "message": str(e)
                }
            }
        
        except ValueError as e:
            # Input errors
            logger.error(f"Invalid input: {e}")
            return {
                "rows": [],
                "summary": {
                    "total_rows": 0,
                    "error": "invalid_input",
                    "message": str(e)
                }
            }
        
        except FileNotFoundError as e:
            # Credentials missing
            logger.error(f"Credentials error: {e}")
            return {
                "rows": [],
                "summary": {
                    "total_rows": 0,
                    "error": "credentials_missing",
                    "message": str(e)
                }
            }
        
        except Exception as e:
            # GA4 API errors or other failures
            logger.error(f"Analytics query failed: {e}", exc_info=True)
            return {
                "rows": [],
                "summary": {
                    "total_rows": 0,
                    "error": "execution_error",
                    "message": f"GA4 query failed: {str(e)}"
                }
            }


# ============================================================================
# AGENT SINGLETON AND MCP REGISTRATION
# ============================================================================

_analytics_agent: Optional[AnalyticsAgent] = None


def get_analytics_agent() -> AnalyticsAgent:
    """Get or create Analytics Agent singleton"""
    global _analytics_agent
    if _analytics_agent is None:
        _analytics_agent = AnalyticsAgent()
    return _analytics_agent


def initialize_analytics_agent():
    """
    Initialize Analytics Agent and register with MCP
    
    This function should be called on app startup to register
    the GA4 executor with the MCP tool registry
    """
    agent = get_analytics_agent()
    
    # Register executor with MCP tools
    set_ga4_executor(agent.execute)
    
    logger.info("Analytics Agent registered with MCP")


# Auto-initialize when module is imported
initialize_analytics_agent()
