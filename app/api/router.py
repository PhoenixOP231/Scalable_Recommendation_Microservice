import time
from datetime import datetime, timezone
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel

from app.schemas.item import Item, ItemCreate
from app.schemas.interaction import InteractionCreate
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse
from app.core.security import verify_api_key
from app.core.dependencies import (
    get_vector_repo, get_cache_repo, get_embedding_service, 
    get_recommendation_service, require_production_dependencies
)
from app.repositories.vector import VectorRepository
from app.repositories.cache import CacheRepository
from app.services.embedding import EmbeddingService
from app.services.recommendation import RecommendationService
from app.core.settings import settings
import logging

logger = logging.getLogger("app")
router = APIRouter()

@router.get("/health", status_code=200)
async def health_check():
    """Process check"""
    return {"status": "ok", "mode": "demo" if settings.DEMO_MODE else "production"}

@router.get("/ready", status_code=200)
async def ready_check():
    """Dependency check"""
    require_production_dependencies()
    # In a real heavy production ready check we could ping Qdrant and Redis here
    # but for Vercel Serverless we want to fail fast and avoid extra latency if possible.
    # Just checking the configuration is often enough for serverless cold starts.
    return {"status": "ready"}

@router.post("/v1/items/upsert", dependencies=[Depends(verify_api_key)])
async def upsert_item(
    item: ItemCreate,
    vector_repo: VectorRepository = Depends(get_vector_repo),
    cache_repo: CacheRepository = Depends(get_cache_repo),
    embedding_service: EmbeddingService = Depends(get_embedding_service)
):
    embeddings = await embedding_service.get_embeddings([f"{item.title} {item.description} {item.category} {' '.join(item.tags)}"])
    await vector_repo.upsert_items([Item(**item.model_dump())], embeddings)
    await cache_repo.increment_catalog_version()
    return {"status": "success"}

@router.post("/v1/items/batch-upsert", dependencies=[Depends(verify_api_key)])
async def batch_upsert_items(
    items: List[ItemCreate],
    vector_repo: VectorRepository = Depends(get_vector_repo),
    cache_repo: CacheRepository = Depends(get_cache_repo),
    embedding_service: EmbeddingService = Depends(get_embedding_service)
):
    if len(items) > 50:
        raise HTTPException(status_code=400, detail="Batch size limit is 50 for synchronous requests")
        
    texts = [f"{item.title} {item.description} {item.category} {' '.join(item.tags)}" for item in items]
    embeddings = await embedding_service.get_embeddings(texts)
    
    item_models = [Item(**item.model_dump()) for item in items]
    await vector_repo.upsert_items(item_models, embeddings)
    await cache_repo.increment_catalog_version()
    return {"status": "success", "upserted": len(items)}

@router.post("/v1/interactions", dependencies=[Depends(verify_api_key)])
async def create_interaction(
    interaction: InteractionCreate,
    cache_repo: CacheRepository = Depends(get_cache_repo)
):
    interaction_data = interaction.model_dump()
    if not interaction_data.get("timestamp"):
        interaction_data["timestamp"] = datetime.now(timezone.utc).isoformat()
    elif isinstance(interaction_data["timestamp"], datetime):
         interaction_data["timestamp"] = interaction_data["timestamp"].isoformat()
         
    new_version = await cache_repo.add_user_interaction(interaction.user_id, interaction_data)
    return {"status": "success", "profile_version": new_version}

@router.post("/v1/recommendations")
async def get_recommendations(
    request: RecommendationRequest,
    fastapi_req: Request,
    rec_service: RecommendationService = Depends(get_recommendation_service)
) -> RecommendationResponse:
    try:
        response = await rec_service.get_recommendations(request)
        response.request_id = getattr(fastapi_req.state, "request_id", "unknown")
        return response
    except Exception as e:
        logger.error(f"Recommendation failed: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/v1/catalog/seed", dependencies=[Depends(verify_api_key)])
async def seed_catalog(
    vector_repo: VectorRepository = Depends(get_vector_repo),
    cache_repo: CacheRepository = Depends(get_cache_repo),
    embedding_service: EmbeddingService = Depends(get_embedding_service)
):
    if not settings.DEMO_MODE and not settings.ALLOW_SEED_ENDPOINT:
        raise HTTPException(status_code=403, detail="Seed endpoint is disabled in production")
        
    # Generate 150 dummy items
    items = []
    categories = ["electronics", "clothing", "books", "home"]
    for i in range(1, 151):
        items.append(ItemCreate(
            id=f"item_{i}",
            title=f"Sample Item {i}",
            description=f"A wonderful sample item {i} for testing.",
            category=categories[i % 4],
            tags=[f"tag_{i%10}"],
            price=10.0 + (i % 50),
            popularity_score=float(i % 100),
            created_at=datetime.now(timezone.utc),
            is_active=True
        ))
        
    # Batch upsert in chunks of 50
    chunk_size = 50
    for i in range(0, len(items), chunk_size):
        chunk = items[i:i+chunk_size]
        texts = [f"{item.title} {item.description} {item.category} {' '.join(item.tags)}" for item in chunk]
        embeddings = await embedding_service.get_embeddings(texts)
        item_models = [Item(**item.model_dump()) for item in chunk]
        await vector_repo.upsert_items(item_models, embeddings)
        
    await cache_repo.increment_catalog_version()
    return {"status": "success", "seeded": 150}

@router.get("/v1/metrics", dependencies=[Depends(verify_api_key)])
async def get_metrics():
    """Basic instance-scoped metrics. Production should rely on structured logging."""
    return {
        "status": "ok", 
        "note": "Instance-scoped metrics. Use structured logs for distributed tracing."
    }
