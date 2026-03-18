"""
Orchestrator - Core Control Flow
Handles intent detection, tool planning, and result aggregation
"""

import logging
from typing import Dict, Any, Optional

from app.llm.client import get_llm_client

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Central orchestrator for query processing
    
    Responsibilities:
    - Receive query + propertyId
    - Detect intent via LLM
    - Create tool execution plan via LLM
    - Call MCP dispatcher for tool execution
    - Aggregate results
    - Generate explanation via LLM
    
    Does NOT:
    - Call GA4 directly
    - Read Sheets directly
    - Execute tools directly
    """
    
    def __init__(self):
        self.llm_client = get_llm_client()
    
    async def process(self, query: str, property_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Main orchestration flow
        
        Args:
            query: User query string
            property_id: Optional GA4 property ID
            
        Returns:
            {
                "answer": str,           # Natural language response
                "metadata": {            # Additional context
                    "intent": str,
                    "tools_used": list,
                    "property_id": str
                }
            }
        
        Raises:
            ValueError: For validation errors (e.g., missing property_id) - caller should convert to 400
        """
        logger.info(f"Processing query: {query[:100]}...")
        
        intent = "unknown"  # Track intent for error responses
        
        try:
            # Step 1: Detect intent using LLM
            intent_result = await self._detect_intent(query)
            intent = intent_result["intent"]
            logger.info(f"Intent detected: {intent}")
            
            # Step 2: Ask LLM to plan tool execution (validates property_id internally)
            tool_plan = await self._plan_tools(query, intent, property_id)
            logger.info(f"Tool plan created: {len(tool_plan.get('tools', []))} tools")
            
            # Step 3: Execute tools via MCP dispatcher
            tool_results = await self._execute_tools(tool_plan, property_id)
            
            # Step 4: Aggregate results (if multiple tools)
            aggregated_results = self._aggregate_results(tool_results)
            
            # Step 5: Generate explanation via LLM
            explanation = await self._generate_explanation(
                query, 
                aggregated_results, 
                intent
            )
            
            # Step 6: Return final response
            return {
                "answer": explanation,
                "metadata": {
                    "intent": intent,
                    "tools_used": [tool["name"] for tool in tool_plan.get("tools", [])],
                    "property_id": property_id
                }
            }
        
        except ValueError as e:
            # Validation errors (e.g., missing property_id) - re-raise for 400 handling
            logger.warning(f"Validation error: {str(e)}")
            raise  # Let FastAPI convert this to HTTPException(400)
        
        except Exception as e:
            logger.error(f"Orchestration failed: {str(e)}", exc_info=True)
            # Return error response with best-known intent
            return self._error_response(
                f"Failed to process query: {str(e)}",
                intent=intent
            )
    
    async def _detect_intent(self, query: str) -> Dict[str, str]:
        """
        Detect intent using LLM
        
        Args:
            query: User query
            
        Returns:
            {"intent": "analytics" | "seo" | "both"}
        """
        try:
            intent_data = await self.llm_client.detect_intent(query)
            return intent_data
        except Exception as e:
            logger.error(f"Intent detection failed: {e}")
            # Smart fallback: check for common keywords
            query_lower = query.lower()
            analytics_keywords = ["users", "sessions", "pageviews", "conversions", "bounce", "visits", "visitors"]
            seo_keywords = ["title", "description", "meta", "seo", "keywords", "indexability", "https", "http", "protocol", "url", "address", "status code", "canonical"]
            
            has_analytics = any(kw in query_lower for kw in analytics_keywords)
            has_seo = any(kw in query_lower for kw in seo_keywords)
            
            # Check for "traffic" + SEO context vs pure traffic
            has_traffic = "traffic" in query_lower
            traffic_with_seo = has_traffic and has_seo
            
            if traffic_with_seo or (has_analytics and has_seo):
                logger.info("Fallback: detected both intent from keywords")
                return {"intent": "both"}
            elif has_seo:
                logger.info("Fallback: detected seo intent from keywords")
                return {"intent": "seo"}
            elif has_analytics or has_traffic:
                logger.info("Fallback: detected analytics intent from keywords")
                return {"intent": "analytics"}
            else:
                logger.info("Fallback: using 'seo' as safe default for unknown queries")
                return {"intent": "seo"}  # Default to SEO for unknown queries (safer)
    
    async def _plan_tools(
        self, 
        query: str, 
        intent: str, 
        property_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Create tool execution plan using LLM
        
        Args:
            query: User query
            intent: Detected intent
            property_id: GA4 property ID
            
        Returns:
            Tool plan with actions and reasoning
        """
        try:
            plan = await self.llm_client.plan_tools(query, intent, property_id)
            return plan
        except Exception as e:
            logger.error(f"Tool planning failed: {e}")
            # Fallback: simple plan based on intent
            return self._fallback_plan(intent)
    
    def _fallback_plan(self, intent: str) -> Dict[str, Any]:
        """
        Create fallback tool plan if LLM planning fails
        
        Args:
            intent: Query intent
            
        Returns:
            Basic tool plan with default arguments and guaranteed metrics
        """
        if intent == "analytics":
            return {
                "tools": [{
                    "name": "ga4.run_report",
                    "arguments": {
                        "metrics": ["totalUsers", "sessions", "screenPageViews"],
                        "dimensions": ["date"],
                        "dateRange": "last30Days"
                    }
                }]
            }
        elif intent == "seo":
            return {"tools": [{"name": "seo.filter_urls", "arguments": {}}]}
        else:  # both
            return {
                "tools": [
                    {
                        "name": "ga4.run_report",
                        "arguments": {
                            "metrics": ["totalUsers", "sessions", "screenPageViews"],
                            "dimensions": ["date"],
                            "dateRange": "last30Days"
                        }
                    },
                    {"name": "seo.filter_urls", "arguments": {}}
                ]
            }
    
    async def _execute_tools(self, tool_plan: Dict[str, Any], property_id: Optional[str]) -> Dict[str, Any]:
        """
        Execute tools via MCP dispatcher
        
        Args:
            tool_plan: Tool execution plan
            property_id: GA4 property ID
            
        Returns:
            Results from tool execution
        """
        from app.mcp.dispatcher import get_dispatcher
        
        dispatcher = get_dispatcher()
        results = await dispatcher.execute_tools(tool_plan, property_id)
        
        return results
    
    def _aggregate_results(self, tool_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aggregate results from multiple tools
        
        Args:
            tool_results: Raw results from tool execution
            
        Returns:
            Aggregated and structured results
        """
        # Simple aggregation: combine all results
        # More sophisticated aggregation can be added later
        aggregated = {
            "tool_count": len(tool_results),
            "results": tool_results,
            "has_errors": any(
                result.get("status") == "error" 
                for result in tool_results.values()
            )
        }
        
        logger.info(f"Aggregated {len(tool_results)} tool results")
        return aggregated
    
    async def _generate_explanation(
        self,
        query: str,
        aggregated_results: Dict[str, Any],
        intent: str
    ) -> str:
        """
        Generate natural language explanation using LLM
        
        Args:
            query: Original query
            aggregated_results: Aggregated tool results
            intent: Query intent
            
        Returns:
            Natural language explanation
        """
        try:
            explanation = await self.llm_client.generate_explanation(
                query,
                aggregated_results,
                intent
            )
            return explanation
        except Exception as e:
            logger.error(f"Explanation generation failed: {e}")
            return f"Query processed with intent: {intent}. Tools executed but explanation generation failed."
    
    def _error_response(self, error_message: str, intent: str) -> Dict[str, Any]:
        """
        Create standardized error response
        
        Args:
            error_message: Error description
            intent: Detected intent
            
        Returns:
            Error response dictionary
        """
        return {
            "answer": error_message,
            "metadata": {
                "intent": intent,
                "tools_used": [],
                "error": True
            }
        }


# Singleton instance
_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    """Get or create orchestrator singleton"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
