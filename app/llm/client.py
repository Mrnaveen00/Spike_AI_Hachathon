# LLM Client for LiteLLM Proxy
# Handles communication with Gemini models via LiteLLM

"""
LLM Client for Google AI (Gemini)
Handles communication with Gemini models via Google AI SDK
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

logger = logging.getLogger(__name__)


# System prompts (centralized for easier debugging)
INTENT_DETECTION_PROMPT = """You are an intent classifier for analytics and SEO queries.

Classify the user query into one of these intents:
- "analytics": Questions about website traffic, user behavior, metrics, conversions, GA4 data, page views, sessions, users, trends, time-based analytics
- "seo": Questions about SEO metadata, page titles, meta descriptions, keywords, content optimization, indexability, URLs, protocols (HTTP/HTTPS), technical SEO issues
- "both": Questions requiring both analytics data AND SEO metadata together (e.g., "top pages by traffic with their titles")

CRITICAL RULES (MUST FOLLOW):
1. If the query is about traffic, users, sessions, page views, conversions, bounce rate, or any numerical metrics → "analytics" ONLY
2. If the query is about titles, descriptions, meta tags, keywords, SEO metadata, URLs, HTTPS/HTTP, indexability, status codes, technical SEO, grouping pages → "seo" ONLY
3. ONLY return "both" if the query EXPLICITLY asks for:
   - Analytics metrics (traffic/users/pageviews/sessions) COMBINED WITH
   - SEO metadata (titles/descriptions/meta tags)
4. Questions about "URLs", "pages", "addresses" without traffic metrics → "seo"
5. Questions about HTTPS, protocols, grouping, counting, technical SEO → "seo"
6. "Top pages by traffic/views/users WITH titles/descriptions" → "both"
7. When in doubt between "seo" and "both", prefer "seo"
8. When in doubt between "analytics" and "both", prefer "analytics"

Examples:
- "Give me total users and sessions in the last 7 days" → analytics (pure metrics query)
- "Show me page views this month" → analytics (page views are metrics, not metadata)
- "What are my top 10 pages by traffic?" → analytics (traffic is a metric, no SEO data requested)
- "Show me pages with missing meta descriptions" → seo (SEO metadata only)
- "Which URLs do not use HTTPS?" → seo (protocol/URL question)
- "Group pages by indexability status" → seo (technical SEO grouping)
- "Group all pages by indexability status and provide a count" → seo (SEO analysis, no analytics metrics)
- "Top 5 pages by traffic with their titles and meta descriptions" → both (traffic metric + SEO metadata)
- "What are the top 10 pages by page views with their title tags?" → both (page views metric + title tags metadata)
- "Top 10 pages by views with title tags" → both (views + titles explicitly requested)
- "What pages have the most users?" → analytics (users is a metric, no SEO data requested)
- "List all URLs" → seo (URL/page listing)

Respond ONLY with valid JSON in this exact format:
{"intent": "analytics"}
or
{"intent": "seo"}
or
{"intent": "both"}"""

TOOL_PLANNING_PROMPT = """You are a tool planner for analytics and SEO queries.

Intent: {intent}

Available tools:
1. ga4.run_report - Fetch GA4 analytics data (metrics, dimensions, date ranges)
2. seo.filter_urls - Query SEO metadata from Google Sheets (titles, descriptions, keywords, indexability)

CRITICAL RULES FOR GA4 QUERIES:
1. You MUST infer metrics from the user query
2. NEVER return an empty metrics list - ALWAYS include at least one metric
3. Dimensions are OPTIONAL - if no grouping is needed, use an empty array []
4. If date period is mentioned, extract dateRange (last7Days, last30Days, last90Days, today, yesterday)

Common GA4 metrics mapping:
- "users" → ["totalUsers"]
- "sessions" → ["sessions"]
- "page views" / "pageviews" → ["screenPageViews"]
- "users and sessions" → ["totalUsers", "sessions"]
- "traffic" → ["totalUsers", "sessions", "screenPageViews"]
- "conversions" → ["conversions"]
- "bounce rate" → ["bounceRate"]

Common dimensions:
- "by date" / "over time" → ["date"]
- "by page" / "by URL" → ["pagePath"]
- "by country" → ["country"]
- "by device" → ["deviceCategory"]

Date range extraction:
- "last 7 days" → "last7Days"
- "last 30 days" / "this month" → "last30Days"
- "last 90 days" → "last90Days"
- "today" → "today"
- "yesterday" → "yesterday"

CRITICAL RULES FOR SEO QUERIES:
1. The seo.filter_urls tool queries Screaming Frog data from Google Sheets
2. Always specify relevant columns to return (url, title, meta_description, indexability, etc.)
3. Use filters sparingly - let the LLM filter results in explanation phase
4. Set reasonable limit (default 1000 for most queries)

Common SEO columns:
- "url" - Page URL
- "title" - Page title tag
- "meta_description" - Meta description tag
- "indexability" - Whether page is indexable
- "protocol" - HTTP vs HTTPS
- "status_code" - HTTP status code
- "content_type" - MIME type
- "canonical_link" - Canonical URL

Examples:

Query: "Give me total users and sessions in the last 7 days"
Response:
{{
  "tools": [
    {{
      "name": "ga4.run_report",
      "arguments": {{
        "metrics": ["totalUsers", "sessions"],
        "dimensions": ["date"],
        "dateRange": "last7Days"
      }}
    }}
  ]
}}

Query: "What are total users this month?"
Response:
{{
  "tools": [
    {{
      "name": "ga4.run_report",
      "arguments": {{
        "metrics": ["totalUsers"],
        "dimensions": [],
        "dateRange": "last30Days"
      }}
    }}
  ]
}}

Query: "Show me page views by date this month"
Response:
{{
  "tools": [
    {{
      "name": "ga4.run_report",
      "arguments": {{
        "metrics": ["screenPageViews"],
        "dimensions": ["date"],
        "dateRange": "last30Days"
      }}
    }}
  ]
}}

Query: "Top pages by traffic"
Response:
{{
  "tools": [
    {{
      "name": "ga4.run_report",
      "arguments": {{
        "metrics": ["screenPageViews", "totalUsers"],
        "dimensions": ["pagePath"],
        "dateRange": "last30Days"
      }}
    }}
  ]
}}

SEO AGENT EXAMPLES:

Query: "Which URLs do not use HTTPS?"
Response:
{{
  "tools": [
    {{
      "name": "seo.filter_urls",
      "arguments": {{
        "filters": {{}},
        "columns": ["url", "protocol"],
        "limit": 1000
      }}
    }}
  ]
}}

Query: "Show me all pages with missing meta descriptions"
Response:
{{
  "tools": [
    {{
      "name": "seo.filter_urls",
      "arguments": {{
        "filters": {{}},
        "columns": ["url", "meta_description", "indexability"],
        "limit": 1000
      }}
    }}
  ]
}}

Query: "Group pages by indexability status"
Response:
{{
  "tools": [
    {{
      "name": "seo.filter_urls",
      "arguments": {{
        "filters": {{}},
        "columns": ["indexability", "url"],
        "limit": 1000
      }}
    }}
  ]
}}

MULTI-AGENT EXAMPLES (when intent is "both"):

Query: "What are the top 10 pages by views with their title tags?"
Response:
{{
  "tools": [
    {{
      "name": "ga4.run_report",
      "arguments": {{
        "metrics": ["screenPageViews", "totalUsers"],
        "dimensions": ["pagePath"],
        "dateRange": "last30Days"
      }}
    }},
    {{
      "name": "seo.filter_urls",
      "arguments": {{
        "filters": {{}},
        "columns": ["url", "title", "meta_description"],
        "limit": 1000
      }}
    }}
  ]
}}

Based on the user query, create a tool execution plan following these examples.
Respond with JSON containing ONLY the tools array:"""

EXPLANATION_PROMPT = """You are an AI assistant that explains analytics and SEO data in natural language.

Given the user's query and the tool results, provide a clear, human-readable explanation.

CRITICAL RULES:
- ALWAYS provide a natural language response, NEVER return raw JSON
- Answer the user's question directly and conversationally
- Use specific numbers and data from results when available
- If data is empty, explain why in simple terms (e.g., "No data available for this time period")
- Be concise but complete (2-5 sentences for simple queries, more for complex ones)
- Format lists with bullet points or numbered items for readability
- Highlight key insights and trends

Examples:
Query: "Give me total users and sessions"
BAD: "Query processed with intent: analytics. Results: {..."
GOOD: "I couldn't retrieve the total users and sessions because no data was available for the specified parameters."

Query: "Which URLs use HTTP?"
BAD: "Query processed with intent: seo. Results: {..."  
GOOD: "Based on the SEO data, the following URL uses HTTP instead of HTTPS: http://example.com/page"

Always respond as if speaking to a human user, not outputting debug information."""


def is_retryable_exception(exc):
    """Check if exception should be retried (rate limiting or resource exhausted)"""
    # Google AI SDK raises ResourceExhausted for rate limits
    exc_str = str(exc).lower()
    return (
        "resource exhausted" in exc_str or 
        "429" in exc_str or 
        "quota" in exc_str or
        "rate limit" in exc_str
    )


class LLMClient:
    # """Client for interacting with LiteLLM proxy"""
    """Client for interacting with Google AI (Gemini)"""
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash",
        timeout: int = 60
    ):
        """
        Initialize LLM client
        
        Args:
            # base_url: LiteLLM proxy base URL
            # api_key: API key (from env or config)
            # model: Model name (hackathon-provided models: gemini-2.5-flash, gemini-2.5-pro, gemini-3-pro-preview)
            api_key: Google AI API key (from env or config)
            model: Model name (gemini-2.0-flash-exp, gemini-1.5-flash, gemini-1.5-pro)
            timeout: Request timeout in seconds
        """
        # self.base_url = base_url.rstrip('/')
        # self.api_key = api_key or os.getenv("LITELLM_API_KEY", "")
        # self.model = model
        self.api_key = api_key or os.getenv("GOOGLE_AI_API_KEY", "")
        self.model_name = model
        self.timeout = timeout
        
        # CRITICAL: Warn if API key is missing
        if not self.api_key:
            # logger.error("LITELLM_API_KEY not found in environment! Set it in .env file or as environment variable.")
            # logger.error("All LLM requests will fail with 401 Unauthorized until API key is configured.")
            logger.error("GOOGLE_AI_API_KEY not found in environment! Set it in .env file or as environment variable.")
            logger.error("All LLM requests will fail until API key is configured.")
        else:
            # Configure the Google AI SDK
            genai.configure(api_key=self.api_key)
            logger.info(f"Google AI SDK configured with model: {model}")
        
        # Validate Gemini model (hackathon-provided models)
        # allowed_models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-pro-preview"]
        # if model not in allowed_models:
        #     logger.warning(f"Model {model} not in allowed list. Proceeding anyway.")

        # Initialize the model
        self.model = None
        if self.api_key:
            try:
                self.model = genai.GenerativeModel(
                    model_name=self.model_name,
                    safety_settings={
                        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                    }
                )
                logger.info("Gemini model initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini model: {e}")
    
    def _messages_to_prompt(self, messages: list) -> str:
        """
        Convert OpenAI-style messages to a prompt for Gemini
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            
        Returns:
            Formatted prompt string
        """
        prompt_parts = []
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                prompt_parts.append(f"SYSTEM INSTRUCTIONS:\n{content}\n")
            elif role == "user":
                prompt_parts.append(f"USER:\n{content}\n")
            elif role == "assistant":
                prompt_parts.append(f"ASSISTANT:\n{content}\n")
        
        return "\n".join(prompt_parts)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(is_retryable_exception),
        reraise=True
    )
    async def _make_request(self, messages: list, response_format: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make request to Google AI (Gemini) with retry logic
        
        Args:
            messages: List of message dictionaries (OpenAI format)
            response_format: Optional response format specification (not fully supported by Gemini)
            
        Returns:
            API response dictionary in OpenAI format for compatibility
        """
        if not self.model:
            raise ValueError("Gemini model not initialized. Check your GOOGLE_AI_API_KEY.")
        
        # Convert messages to prompt
        prompt = self._messages_to_prompt(messages)
        
        # Configure generation settings
        gen_config = genai.types.GenerationConfig(
            temperature=0.1,  # Low temperature for consistent reasoning
            max_output_tokens=8192,
        )
        
        # Add JSON instruction if response_format is specified
        if response_format and response_format.get("type") == "json_object":
            prompt += "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanations, no code blocks."
            # Note: response_mime_type is only available in some Gemini models
            # gen_config.response_mime_type = "application/json"
        
        try:
            # Generate content (blocking call, so wrap in asyncio.to_thread)
            logger.debug(f"Sending request to Gemini ({self.model_name})")
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config=gen_config
            )
            
            # Extract text from response
            if not response.text:
                logger.error("Empty response from Gemini")
                raise ValueError("Empty response from Gemini API")
            
            # Return in OpenAI-compatible format
            return {
                "choices": [{
                    "message": {
                        "content": response.text.strip()
                    }
                }]
            }
        
        except Exception as e:
            error_msg = str(e).lower()
            
            # Check for rate limiting
            if "resource exhausted" in error_msg or "429" in error_msg or "quota" in error_msg:
                logger.warning("Rate limited by Google AI. Retrying...")
                raise  # Retry via tenacity
            
            # Check for other common errors
            if "api key not valid" in error_msg or "api_key_invalid" in error_msg:
                logger.error("Invalid Google AI API key. Get one from: https://makersuite.google.com/app/apikey")
                raise ValueError("Invalid Google AI API key")
            
            logger.error(f"Gemini API request failed: {str(e)}")
            raise
    
    async def detect_intent(self, query: str) -> Dict[str, str]:
        """
        Detect intent from user query
        
        Args:
            query: User query string
            
        Returns:
            {"intent": "analytics" | "seo" | "both"}
        """
        messages = [
            {
                "role": "system",
                "content": INTENT_DETECTION_PROMPT
            },
            {
                "role": "user",
                "content": f"Classify this query:\n\n{query}"
            }
        ]
        
        try:
            response = await self._make_request(messages)
            content = response["choices"][0]["message"]["content"].strip()
            
            # Remove markdown code blocks if present (Gemini often wraps JSON in ```json ... ```)
            if content.startswith("```"):
                # Extract JSON from markdown code block
                lines = content.split("\n")
                # Remove first line (```json or ```) and last line (```)
                content = "\n".join(lines[1:-1]).strip()
            
            # Parse JSON response
            intent_data = json.loads(content)
            
            # Validate intent value
            if intent_data.get("intent") not in ["analytics", "seo", "both"]:
                raise ValueError(f"Invalid intent: {intent_data.get('intent')}")
            
            logger.info(f"Detected intent: {intent_data['intent']}")
            return intent_data
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse intent JSON: {e}")
            logger.error(f"Raw response: {content[:200]}")
            # Fallback: analyze query text
            query_lower = query.lower()
            
            # Analytics keywords
            if any(kw in query_lower for kw in ["traffic", "views", "pageviews", "sessions", "users", "conversions", "bounce", "visitors"]):
                return {"intent": "analytics"}
            
            # SEO keywords (including "pages", "urls", "addresses")
            elif any(kw in query_lower for kw in ["title", "description", "meta", "seo", "keywords", "pages", "urls", "url", "address", "indexability", "https", "http", "protocol"]):
                return {"intent": "seo"}
            
            # Default to SEO for unknown queries (safer than "both")
            else:
                logger.warning(f"Could not classify query, defaulting to 'seo': {query}")
                return {"intent": "seo"}
    
    async def plan_tools(self, query: str, intent: str, property_id: Optional[str]) -> Dict[str, Any]:
        """
        Ask LLM to create a tool execution plan
        
        Args:
            query: User query
            intent: Detected intent (analytics/seo/both)
            property_id: GA4 property ID (required for analytics queries)
            
        Returns:
            Tool execution plan: {"tools": [...]}
        
        Raises:
            ValueError: If property_id missing for analytics queries
        """
        # CRITICAL: Validate property_id before calling LLM
        if intent in ["analytics", "both"] and not property_id:
            raise ValueError("GA4 property ID is required for analytics queries")
        
        messages = [
            {
                "role": "system",
                "content": TOOL_PLANNING_PROMPT.format(intent=intent)
            },
            {
                "role": "user",
                "content": f"Query: {query}\nProperty ID: {property_id or 'Not provided'}"
            }
        ]
        
        try:
            response = await self._make_request(messages)
            content = response["choices"][0]["message"]["content"].strip()
            
            # Remove markdown code blocks if present
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1]).strip()
            
            # Parse JSON response
            plan = json.loads(content)
            
            # Validate structure
            if "tools" not in plan:
                raise ValueError("Tool plan missing 'tools' key")
            
            logger.info(f"Tool plan created: {len(plan.get('tools', []))} tools")
            return plan
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse tool plan JSON: {e}")
            logger.error(f"Raw LLM response: {content[:200]}...")
            # Fallback: basic plan based on intent with default metrics
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
            else:
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
        
        except Exception as e:
            logger.error(f"Tool planning failed: {e}")
            # Fallback: basic plan with guaranteed metrics
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
            else:
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
    
    async def generate_explanation(self, query: str, tool_results: Dict[str, Any], intent: str) -> str:
        """
        Generate natural language explanation from tool results
        
        Args:
            query: Original user query
            tool_results: Structured results from tools
            intent: Query intent
            
        Returns:
            Natural language explanation
        """
        # Truncate tool results if too large (LLM context limits)
        tool_results_str = json.dumps(tool_results, indent=2)
        if len(tool_results_str) > 10000:
            logger.warning(f"Tool results too large ({len(tool_results_str)} chars), truncating...")
            tool_results_str = tool_results_str[:10000] + "\n... (truncated)"
        
        messages = [
            {
                "role": "system",
                "content": EXPLANATION_PROMPT
            },
            {
                "role": "user",
                "content": f"""Query: {query}

Intent: {intent}

Tool Results:
{tool_results_str}

Provide a clear explanation:"""
            }
        ]
        
        try:
            logger.info("Generating explanation via LLM...")
            response = await self._make_request(messages)
            explanation = response["choices"][0]["message"]["content"].strip()
            logger.info(f"Generated explanation successfully ({len(explanation)} chars)")
            return explanation
        
        except (httpx.TimeoutException, httpx.ReadTimeout, TimeoutError) as e:
            logger.error(f"LLM timeout during explanation generation: {e}")
            return self._generate_simple_explanation(query, tool_results, intent)
        
        except Exception as e:
            logger.error(f"Failed to generate explanation: {e}", exc_info=True)
            return self._generate_simple_explanation(query, tool_results, intent)
    
    def _generate_simple_explanation(
        self,
        query: str,
        tool_results: Dict[str, Any],
        intent: str
    ) -> str:
        """
        Generate a simple fallback explanation when LLM fails
        
        Args:
            query: Original query
            tool_results: Tool results
            intent: Query intent
            
        Returns:
            Simple human-readable explanation
        """
        # Extract key information from results
        results = tool_results.get("results", {})
        
        if not results:
            return "I couldn't process your query. Please try again."
        
        # Check for errors
        has_errors = tool_results.get("has_errors", False)
        if has_errors:
            return "There was an error processing your query. Please check your parameters and try again."
        
        # Check for empty data
        all_empty = True
        for tool_name, tool_result in results.items():
            if tool_result.get("status") == "success":
                data = tool_result.get("data", {})
                rows = data.get("rows", [])
                if rows:
                    all_empty = False
                    break
        
        if all_empty:
            return f"I processed your query but found no data available. This could be because there's no matching data for the time period or filters specified."
        
        # Generate basic explanation based on intent
        if intent == "analytics":
            return "I successfully retrieved analytics data for your query. The system processed your request but encountered an issue generating a detailed explanation. Please check the metadata for technical details."
        elif intent == "seo":
            total_rows = sum(
                len(r.get("data", {}).get("rows", [])) 
                for r in results.values() 
                if r.get("status") == "success"
            )
            return f"I successfully retrieved SEO data for your query. Found {total_rows} results. The system processed your request but encountered an issue generating a detailed explanation."
        else:
            return "I successfully processed your multi-agent query combining analytics and SEO data. The system encountered an issue generating a detailed explanation, but the data was retrieved successfully."


# Singleton instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create LLM client singleton"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
