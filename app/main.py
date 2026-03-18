from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logging for production
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import agents to trigger auto-registration with MCP
import app.agents  # Registers analytics agent with MCP tools

app = FastAPI(
    title="Spike AI Analytics API",
    description="Production-ready AI backend for GA4 and SEO queries",
    version="1.0.0"
)


class QueryRequest(BaseModel):
    query: str
    propertyId: str | None = None


class QueryResponse(BaseModel):
    answer: str
    metadata: dict | None = None


@app.get("/health")
async def health_check():
    """Health check endpoint for deployment verification"""
    # Check critical environment variables
    # has_llm_key = bool(os.getenv("LITELLM_API_KEY"))
    has_llm_key = bool(os.getenv("GOOGLE_AI_API_KEY"))
    has_seo_url = bool(os.getenv("SEO_SHEET_URL"))
    
    return {
        "status": "ok", 
        "service": "spike-ai-backend",
        "config": {
            "llm_api_key_configured": has_llm_key,
            "seo_sheet_url_configured": has_seo_url
        }
    }


@app.post("/query", response_model=QueryResponse)
async def handle_query(request: QueryRequest):
    from app.orchestrator import get_orchestrator
    
    logger.info(f"Received query: {request.query[:100]}...")  # Log first 100 chars
    
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    if len(request.query) > 5000:  # Reasonable limit
        raise HTTPException(status_code=400, detail="Query too long (max 5000 characters)")
    
    # Route to orchestrator
    orchestrator = get_orchestrator()
    
    try:
        orchestrator_response = await orchestrator.process(request.query, request.propertyId)
        
        return QueryResponse(
            answer=orchestrator_response.get("answer", "No response generated"),
            metadata=orchestrator_response.get("metadata")
        )
    
    except ValueError as e:
        # Validation errors (e.g., missing property_id for analytics queries)
        logger.warning(f"Validation error in query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))