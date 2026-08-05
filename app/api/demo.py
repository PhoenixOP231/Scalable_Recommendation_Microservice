import uuid
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from app.core.settings import settings
from app.core.dependencies import get_cache_repo, get_vector_repo, get_recommendation_service
from app.repositories.cache import CacheRepository
from app.repositories.vector import VectorRepository
from app.services.recommendation import RecommendationService
from app.schemas.interaction import InteractionCreate
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse
from pydantic import BaseModel
import logging

logger = logging.getLogger("app")

router = APIRouter(prefix="/v1/demo", tags=["Demo"])

DEMO_SESSION_COOKIE = "demo_session_id"

def get_demo_session(request: Request, response: Response) -> str:
    if not settings.PUBLIC_DEMO_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Public demo is disabled")
        
    session_id = request.cookies.get(DEMO_SESSION_COOKIE)
    if not session_id:
        session_id = str(uuid.uuid4())
        # Secure in production, Lax for local
        is_secure = not settings.DEMO_MODE
        response.set_cookie(
            key=DEMO_SESSION_COOKIE,
            value=session_id,
            httponly=True,
            secure=is_secure,
            samesite="lax",
            path="/",
            max_age=86400 # 24 hours
        )
    return session_id

async def rate_limit(request: Request, cache: CacheRepository = Depends(get_cache_repo)):
    if not settings.PUBLIC_DEMO_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Public demo is disabled")
        
    ip = request.client.host if request.client else "unknown"
    is_allowed = await cache.check_rate_limit(f"ip:{ip}", max_requests=100, window=60)
    if not is_allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

class DemoCatalogResponse(BaseModel):
    items: List[Dict[str, Any]]

@router.get("/catalog", response_model=DemoCatalogResponse)
async def get_demo_catalog(
    session_id: str = Depends(get_demo_session),
    _=Depends(rate_limit),
    vector_repo: VectorRepository = Depends(get_vector_repo)
):
    try:
        items = await vector_repo.get_catalog(limit=50)
        # Filter only safe fields
        safe_items = []
        for item in items:
            meta = item.get("metadata", {})
            if not meta.get("is_active", True):
                continue
            safe_items.append({
                "item_id": meta.get("item_id"),
                "title": meta.get("title"),
                "category": meta.get("category"),
                "price": meta.get("price"),
                "tags": meta.get("tags")
            })
        return DemoCatalogResponse(items=safe_items)
    except Exception as e:
        import traceback
        error_str = str(e)
        if "Not found: Collection" in error_str or "doesn't exist" in error_str or "404" in error_str:
            logger.warning("Qdrant collection does not exist yet. Returning empty catalog.")
            return DemoCatalogResponse(items=[])
            
        logger.error(f"Catalog error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@router.post("/interactions")
async def save_demo_interaction(
    interaction: InteractionCreate,
    session_id: str = Depends(get_demo_session),
    _=Depends(rate_limit),
    cache: CacheRepository = Depends(get_cache_repo)
):
    await cache.add_demo_interaction(
        session_id=session_id,
        interaction=interaction.model_dump(mode='json'),
        ttl=86400
    )
    return {"status": "ok"}

@router.post("/recommendations", response_model=RecommendationResponse)
async def get_demo_recommendations(
    request: RecommendationRequest,
    session_id: str = Depends(get_demo_session),
    _=Depends(rate_limit),
    rec_service: RecommendationService = Depends(get_recommendation_service),
    cache: CacheRepository = Depends(get_cache_repo)
):
    # Fetch demo interactions instead of regular interactions
    interactions = await cache.get_demo_interactions(session_id=session_id)
    
    # We call the service with the incoming request and provide the demo history
    # The session_id serves as the user_id for the request
    request.user_id = session_id
    response = await rec_service.get_recommendations(
        request=request,
        demo_history=interactions
    )
    
    return response

@router.post("/reset")
async def reset_demo(
    session_id: str = Depends(get_demo_session),
    _=Depends(rate_limit),
    cache: CacheRepository = Depends(get_cache_repo)
):
    await cache.reset_demo_session(session_id)
    return {"status": "reset"}
