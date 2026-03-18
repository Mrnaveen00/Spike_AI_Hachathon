"""
GA4 Data API Client
Handles credentials loading and GA4 RunReport API calls
"""

import os
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest,
    DateRange,
    Dimension,
    Metric,
)
from google.oauth2 import service_account

logger = logging.getLogger(__name__)
  

class GA4Client:
    """
    Client for Google Analytics 4 Data API
    
    Handles:
    - Credentials loading (runtime, not hardcoded)
    - RunReport API calls
    - Empty data handling
    """
    
    def __init__(self, credentials_path: Optional[str] = None):
        """
        Initialize GA4 client
        
        Args:
            credentials_path: Path to credentials.json (optional, will auto-detect)
        """
        self.client = None
        self.credentials_path = credentials_path
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """
        Initialize GA4 client with credentials
        
        Raises:
            FileNotFoundError: If credentials file not found
            ValueError: If credentials are invalid
        """
        # Step 1: Determine credentials path (NOT hardcoded)
        creds_path = self._find_credentials_path()
        
        if not creds_path or not os.path.exists(creds_path):
            raise FileNotFoundError(
                f"GA4 credentials not found. "
                f"Expected location: {creds_path or 'credentials.json in project root'}. "
                f"Evaluators should place credentials.json in the project root."
            )
        
        try:
            # Step 2: Load credentials
            logger.info(f"Loading GA4 credentials from: {creds_path}")
            credentials = service_account.Credentials.from_service_account_file(
                creds_path,
                scopes=["https://www.googleapis.com/auth/analytics.readonly"]
            )
            
            # Step 3: Initialize client
            self.client = BetaAnalyticsDataClient(credentials=credentials)
            logger.info("GA4 client initialized successfully")
        
        except Exception as e:
            raise ValueError(f"Failed to initialize GA4 client: {str(e)}")
    
    def _find_credentials_path(self) -> Optional[str]:
        """
        Find credentials.json path (auto-detect, NOT hardcoded)
        
        Priority:
        1. Provided path (constructor argument)
        2. Environment variable GOOGLE_APPLICATION_CREDENTIALS
        3. credentials.json in project root
        4. credentials.json in current directory
        
        Returns:
            Path to credentials.json or None
        """
        # Priority 1: Constructor argument
        if self.credentials_path:
            return self.credentials_path
        
        # Priority 2: Environment variable
        env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if env_path:
            logger.info(f"Using credentials from GOOGLE_APPLICATION_CREDENTIALS: {env_path}")
            return env_path
        
        # Priority 3: Project root (most common for evaluators)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        root_creds = os.path.join(project_root, "credentials.json")
        if os.path.exists(root_creds):
            logger.info(f"Found credentials.json in project root: {root_creds}")
            return root_creds
        
        # Priority 4: Current directory
        current_creds = os.path.join(os.getcwd(), "credentials.json")
        if os.path.exists(current_creds):
            logger.info(f"Found credentials.json in current directory: {current_creds}")
            return current_creds
        
        logger.warning("No credentials.json found in any standard location")
        return None
    
    def _parse_date_range(self, date_range_str: str) -> DateRange:
        """
        Parse date range string into GA4 DateRange object
        
        Args:
            date_range_str: Date range (e.g., "last7Days", "2024-01-01:2024-01-31")
            
        Returns:
            GA4 DateRange object
        """
        # Predefined ranges
        predefined_ranges = {
            "today": ("today", "today"),
            "yesterday": ("yesterday", "yesterday"),
            "last7Days": ("7daysAgo", "yesterday"),
            "last14Days": ("14daysAgo", "yesterday"),
            "last28Days": ("28daysAgo", "yesterday"),
            "last30Days": ("30daysAgo", "yesterday"),
            "last90Days": ("90daysAgo", "yesterday"),
            "last365Days": ("365daysAgo", "yesterday"),
        }
        
        # Check if predefined
        if date_range_str in predefined_ranges:
            start, end = predefined_ranges[date_range_str]
            return DateRange(start_date=start, end_date=end)
        
        # Custom range (YYYY-MM-DD:YYYY-MM-DD)
        if ":" in date_range_str:
            start_date, end_date = date_range_str.split(":")
            return DateRange(start_date=start_date, end_date=end_date)
        
        # Default to last 7 days
        logger.warning(f"Unknown date range '{date_range_str}', defaulting to last7Days")
        return DateRange(start_date="7daysAgo", end_date="yesterday")
    
    async def run_report(self, property_id: str, metrics: List[str], dimensions: List[str], date_range: str, filters: Optional[Dict[str, Any]] = None, limit: int = 10000) -> Dict[str, Any]:
        """
        Run GA4 report using Data API
        
        Args:
            property_id: GA4 property ID (e.g., "properties/123456789")
            metrics: List of metric names
            dimensions: List of dimension names
            date_range: Date range string
            filters: Optional filters (not implemented yet)
            limit: Row limit (default 10000)
            
        Returns:
            {
                "rows": [...],
                "summary": {
                    "total_rows": int,
                    "metrics": [...],
                    "dimensions": [...]
                }
            }
        
        Raises:
            RuntimeError: If client not initialized
            ValueError: If metrics or dimensions are empty
            NotImplementedError: If filters are provided (not supported yet)
        """
        if not self.client:
            raise RuntimeError("GA4 client not initialized")
        
        # CRITICAL: Enforce non-empty metrics (dimensions are optional for aggregated data)
        if not metrics:
            raise ValueError("At least one metric is required")
        # Note: Dimensions are OPTIONAL in GA4 API (allows aggregated queries without dimensions)
        
        # CRITICAL: Fail clearly if filters are provided but not supported
        if filters:
            raise NotImplementedError(
                "GA4 filters are not implemented yet. "
                "Remove filters from the query or implement filter support."
            )
        
        # Ensure property_id has correct format
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"
        
        logger.info(f"Running GA4 report for property: {property_id}")
        logger.debug(f"GA4 Request: metrics={metrics}, dimensions={dimensions}, date_range={date_range}")
        
        # Build request
        request = RunReportRequest(
            property=property_id,
            date_ranges=[self._parse_date_range(date_range)],
            metrics=[Metric(name=m) for m in metrics],
            dimensions=[Dimension(name=d) for d in dimensions],
            limit=limit
        )
        
        try:
            # CRITICAL: Use asyncio.to_thread to avoid blocking the event loop
            # BetaAnalyticsDataClient.run_report() is a blocking call
            logger.info(f"Calling GA4 API with {len(metrics)} metrics and {len(dimensions)} dimensions")
            response = await asyncio.to_thread(self.client.run_report, request)
            
            # Parse response
            result = self._parse_response(response, metrics, dimensions)
            
            logger.info(f"GA4 report completed: {result['summary']['total_rows']} rows returned")
            return result
        
        except Exception as e:
            logger.error(f"GA4 API call failed: {str(e)}")
            raise
    
    def _parse_response(self, response, metrics: List[str], dimensions: List[str]) -> Dict[str, Any]:
        """
        Parse GA4 API response into structured format
        
        Args:
            response: GA4 API response
            metrics: List of metric names
            dimensions: List of dimension names
            
        Returns:
            Structured result with rows and summary
        """
        rows = []
        
        # Handle empty data gracefully
        if not response.rows:
            logger.warning("GA4 API returned no data")
            return {
                "rows": [],
                "summary": {
                    "total_rows": 0,
                    "metrics": metrics,
                    "dimensions": dimensions,
                    "message": "No data available for the specified parameters"
                }
            }
        
        # Parse each row
        for row in response.rows:
            row_data = {}
            
            # Parse dimensions (keep as strings)
            for i, dimension_value in enumerate(row.dimension_values):
                if i < len(dimensions):
                    row_data[dimensions[i]] = dimension_value.value
            
            # CRITICAL: Parse metrics and convert to numbers
            # GA4 returns metrics as strings, but we need numbers for calculations
            for i, metric_value in enumerate(row.metric_values):
                if i < len(metrics):
                    value = metric_value.value
                    
                    # Try to convert to int first, then float, fallback to string
                    try:
                        value = int(value)
                    except ValueError:
                        try:
                            value = float(value)
                        except ValueError:
                            # Keep as string if conversion fails
                            pass
                    
                    row_data[metrics[i]] = value
            
            rows.append(row_data)
        
        # Build summary
        summary = {
            "total_rows": len(rows),
            "metrics": metrics,
            "dimensions": dimensions
        }
        
        return {
            "rows": rows,
            "summary": summary
        }


# Singleton instance
_ga4_client: Optional[GA4Client] = None


def get_ga4_client() -> GA4Client:
    """
    Get or create GA4 client singleton
    
    Returns:
        GA4Client instance
    """
    global _ga4_client
    if _ga4_client is None:
        _ga4_client = GA4Client()
    return _ga4_client
