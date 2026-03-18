"""
Agents module - Auto-initializes all agents
"""

# Import agents to trigger auto-registration with MCP
from app.agents.analytics_agent import initialize_analytics_agent
from app.agents.seo_agent import initialize_seo_agent

# Auto-initialize on import
initialize_analytics_agent()
initialize_seo_agent()
