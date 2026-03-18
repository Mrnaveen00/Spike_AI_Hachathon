"""
GA4 Validator - CRITICAL Component
Validates metrics, dimensions, and combinations to prevent GA4 API failures
"""

import logging
from typing import List, Set, Dict, Any, Tuple

logger = logging.getLogger(__name__)


# ============================================================================
# ALLOWLISTS - Valid GA4 Metrics and Dimensions
# ============================================================================

# Common GA4 Metrics (from official GA4 Data API documentation)
VALID_METRICS: Set[str] = {
    # User metrics
    "activeUsers",
    "totalUsers",
    "newUsers",
    "returningUsers",
    
    # Session metrics
    "sessions",
    "sessionsPerUser",
    "bounceRate",
    "engagementRate",
    "engagedSessions",
    "averageSessionDuration",
    "sessionConversionRate",
    
    # Page/Screen metrics
    "screenPageViews",
    "screenPageViewsPerSession",
    "screenPageViewsPerUser",
    
    # Event metrics
    "eventCount",
    "eventCountPerUser",
    "eventsPerSession",
    
    # Conversion metrics
    "conversions",
    "totalRevenue",
    "purchaseRevenue",
    "transactions",
    "transactionsPerPurchaser",
    
    # Engagement metrics
    "userEngagementDuration",
    "averageEngagementTime",
    "averageEngagementTimePerSession",
}

# Common GA4 Dimensions (from official GA4 Data API documentation)
VALID_DIMENSIONS: Set[str] = {
    # Time dimensions
    "date",
    "year",
    "month",
    "week",
    "day",
    "hour",
    "yearMonth",
    "yearWeek",
    
    # Geography dimensions
    "country",
    "region",
    "city",
    "continent",
    
    # Technology dimensions
    "browser",
    "deviceCategory",
    "operatingSystem",
    "platform",
    "mobileDeviceModel",
    "screenResolution",
    
    # Page/Screen dimensions
    "pagePath",
    "pageTitle",
    "landingPage",
    "hostName",
    "pagePathPlusQueryString",
    "pageLocation",
    
    # Traffic source dimensions
    "source",
    "medium",
    "campaign",
    "campaignId",
    "sourceMedium",
    "sessionSource",
    "sessionMedium",
    "sessionCampaign",
    "firstUserSource",
    "firstUserMedium",
    "firstUserCampaign",
    
    # Event dimensions
    "eventName",
    "eventAction",
    
    # User dimensions
    "userId",
    "sessionId",
    "language",
    "userAgeBracket",
    "userGender",
}

# Incompatible combinations (metrics that don't work with certain dimensions)
INCOMPATIBLE_COMBINATIONS: List[Tuple[str, str]] = [
    # Add known incompatible combinations here
    # Format: (metric, dimension)
    # Example: ("bounceRate", "eventName")
]


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

class GA4ValidationError(Exception):
    """Custom exception for GA4 validation errors"""
    pass


def validate_metrics(metrics: List[str]) -> None:
    """
    Validate that metrics are in the allowlist
    
    Args:
        metrics: List of metric names
        
    Raises:
        GA4ValidationError: If any metric is invalid
    """
    if not metrics:
        raise GA4ValidationError("At least one metric is required")
    
    if len(metrics) > 10:
        raise GA4ValidationError(f"Too many metrics: {len(metrics)}. Maximum 10 metrics allowed.")
    
    invalid_metrics = [m for m in metrics if m not in VALID_METRICS]
    
    if invalid_metrics:
        raise GA4ValidationError(
            f"Invalid metrics: {invalid_metrics}. "
            f"Valid metrics: {sorted(list(VALID_METRICS))[:20]}... (showing first 20)"
        )
    
    logger.debug(f"Validated {len(metrics)} metrics: {metrics}")


def validate_dimensions(dimensions: List[str]) -> None:
    """
    Validate that dimensions are in the allowlist
    
    Args:
        dimensions: List of dimension names
        
    Raises:
        GA4ValidationError: If any dimension is invalid
    """
    # Dimensions are optional
    if not dimensions:
        logger.debug("No dimensions provided (valid - will aggregate all data)")
        return
    
    if len(dimensions) > 10:
        raise GA4ValidationError(f"Too many dimensions: {len(dimensions)}. Maximum 10 dimensions allowed.")
    
    invalid_dimensions = [d for d in dimensions if d not in VALID_DIMENSIONS]
    
    if invalid_dimensions:
        raise GA4ValidationError(
            f"Invalid dimensions: {invalid_dimensions}. "
            f"Valid dimensions: {sorted(list(VALID_DIMENSIONS))[:20]}... (showing first 20)"
        )
    
    logger.debug(f"Validated {len(dimensions)} dimensions: {dimensions}")


def validate_combinations(metrics: List[str], dimensions: List[str]) -> None:
    """
    Validate that metric-dimension combinations are compatible
    
    Args:
        metrics: List of metric names
        dimensions: List of dimension names
        
    Raises:
        GA4ValidationError: If any combination is incompatible
    """
    # Check for known incompatible combinations
    for metric in metrics:
        for dimension in dimensions:
            if (metric, dimension) in INCOMPATIBLE_COMBINATIONS:
                raise GA4ValidationError(
                    f"Incompatible combination: metric '{metric}' with dimension '{dimension}'"
                )
    
    logger.debug("Metric-dimension combinations validated successfully")


def validate_date_range(date_range: str) -> None:
    """
    Validate date range format
    
    Args:
        date_range: Date range string (e.g., "last7Days", "2024-01-01:2024-01-31")
        
    Raises:
        GA4ValidationError: If date range is invalid
    """
    if not date_range:
        raise GA4ValidationError("Date range is required")
    
    # Valid predefined ranges (aligned with GA4 client support)
    predefined_ranges = {
        "today", "yesterday", "last7Days", "last14Days", "last28Days", 
        "last30Days", "last90Days", "last365Days"
    }
    
    # Check if it's a predefined range
    if date_range in predefined_ranges:
        logger.debug(f"Validated predefined date range: {date_range}")
        return
    
    # Check if it's a custom range (YYYY-MM-DD:YYYY-MM-DD)
    if ":" in date_range:
        parts = date_range.split(":")
        if len(parts) == 2:
            start_date, end_date = parts
            # Basic format check (YYYY-MM-DD)
            if len(start_date) == 10 and len(end_date) == 10:
                logger.debug(f"Validated custom date range: {date_range}")
                return
    
    raise GA4ValidationError(
        f"Invalid date range: '{date_range}'. "
        f"Use predefined ranges (e.g., 'last7Days') or custom format (YYYY-MM-DD:YYYY-MM-DD)"
    )


def validate_ga4_request(
    metrics: List[str],
    dimensions: List[str],
    date_range: str
) -> None:
    """
    Validate complete GA4 request
    
    Args:
        metrics: List of metric names
        dimensions: List of dimension names
        date_range: Date range string
        
    Raises:
        GA4ValidationError: If any validation fails
    """
    logger.debug("Validating GA4 request...")
    
    # Validate each component
    validate_metrics(metrics)
    validate_dimensions(dimensions)
    validate_date_range(date_range)
    validate_combinations(metrics, dimensions)
    
    logger.debug("GA4 request validation complete: PASSED")
