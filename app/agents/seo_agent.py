"""
SEO Agent - TIER 2
Executes SEO metadata queries from Google Sheets
"""

import logging
from typing import Dict, Any, Optional, List
import pandas as pd

from app.seo.sheets_reader import get_sheets_reader
from app.mcp.tools import set_seo_executor

logger = logging.getLogger(__name__)


class SEOAgent:
    """
    Agent for executing SEO metadata queries
    
    Responsibilities:
    - Load Google Sheets data
    - Apply filters, grouping, aggregation
    - Return structured results
    - Handle schema changes dynamically
    """
    
    def __init__(self):
        """Initialize SEO Agent"""
        self.sheets_reader = None
        self.cached_df = None
        logger.info("SEO Agent initialized")
    
    def _ensure_reader(self):
        """Lazy-load Sheets reader"""
        if self.sheets_reader is None:
            try:
                self.sheets_reader = get_sheets_reader()
                logger.info("Sheets reader loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load Sheets reader: {e}")
                raise RuntimeError(f"Sheets reader initialization failed: {str(e)}") from e
    
    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute SEO query
        
        Args:
            arguments: {
                "filters": {"url": "...", "status": "..."},
                "columns": ["url", "title", "meta_description"],
                "limit": 100
            }
            context: {}
            
        Returns:
            {
                "rows": [...],
                "summary": {...}
            }
        """
        logger.info("Executing SEO query...")
        
        try:
            # Step 1: Ensure Sheets reader is initialized
            self._ensure_reader()
            
            # Step 2: Extract arguments
            filters = arguments.get("filters", {})
            columns = arguments.get("columns", [])
            limit = arguments.get("limit", 1000)
            
            # Step 3: Load sheet data
            df = await self.sheets_reader.read_sheet()
            
            if df.empty:
                return {
                    "rows": [],
                    "summary": {
                        "total_rows": 0,
                        "message": "No data available in sheet"
                    }
                }
            
            # Step 4: Apply filters
            df_filtered = self._apply_filters(df, filters)
            
            # Step 5: Select columns (if specified)
            if columns:
                # Normalize requested columns
                normalized_cols = [col.lower().replace(" ", "_").replace("-", "_") for col in columns]
                # Only select columns that exist
                available_cols = [col for col in normalized_cols if col in df_filtered.columns]
                if available_cols:
                    df_filtered = df_filtered[available_cols]
                else:
                    logger.warning(f"Requested columns not found: {columns}")
            
            # Step 6: Apply limit
            if limit and limit > 0:
                df_filtered = df_filtered.head(limit)
            
            # Step 7: Convert to records
            rows = df_filtered.to_dict('records')
            
            # Step 8: Return structured result
            result = {
                "rows": rows,
                "summary": {
                    "total_rows": len(rows),
                    "columns": df_filtered.columns.tolist()
                }
            }
            
            logger.info(f"SEO query successful: {len(rows)} rows")
            return result
        
        except FileNotFoundError as e:
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
            logger.error(f"SEO query failed: {e}", exc_info=True)
            return {
                "rows": [],
                "summary": {
                    "total_rows": 0,
                    "error": "execution_error",
                    "message": f"SEO query failed: {str(e)}"
                }
            }
    
    def _apply_filters(self, df: pd.DataFrame, filters: Dict[str, Any]) -> pd.DataFrame:
        """
        Apply filters to DataFrame
        
        Args:
            df: Input DataFrame
            filters: Filter conditions
            
        Returns:
            Filtered DataFrame
        """
        if not filters:
            return df
        
        df_result = df.copy()
        
        for column, value in filters.items():
            # Normalize column name
            norm_col = column.lower().replace(" ", "_").replace("-", "_")
            
            if norm_col not in df_result.columns:
                logger.warning(f"Filter column not found: {column}")
                continue
            
            # Apply filter (exact match for now)
            if isinstance(value, list):
                # Multiple values (OR condition)
                df_result = df_result[df_result[norm_col].isin(value)]
            else:
                # Single value
                df_result = df_result[df_result[norm_col] == value]
            
            logger.debug(f"Applied filter: {norm_col} = {value}, {len(df_result)} rows remaining")
        
        return df_result


# ============================================================================
# AGENT SINGLETON AND MCP REGISTRATION
# ============================================================================

_seo_agent: Optional[SEOAgent] = None


def get_seo_agent() -> SEOAgent:
    """Get or create SEO Agent singleton"""
    global _seo_agent
    if _seo_agent is None:
        _seo_agent = SEOAgent()
    return _seo_agent


def initialize_seo_agent():
    """Initialize SEO Agent and register with MCP"""
    agent = get_seo_agent()
    set_seo_executor(agent.execute)
    logger.info("SEO Agent registered with MCP")


# Auto-initialize when module is imported
initialize_seo_agent()
