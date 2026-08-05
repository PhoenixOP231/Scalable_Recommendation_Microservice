import time
from datetime import datetime, timezone
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel

from app.schemas.item import Item, ItemCreate
from app.schemas.interaction import InteractionCreate
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse
from app.core.security import verify_api_key, verify_cron_secret
from app.core.dependencies import (
    get_vector_repo, get_cache_repo, get_embedding_service, 
    get_recommendation_service, get_tmdb_service, require_production_dependencies
)
from app.repositories.vector import VectorRepository
from app.repositories.cache import CacheRepository
from app.services.embedding import EmbeddingService
from app.services.recommendation import RecommendationService
from app.services.tmdb import TMDBService
from app.api import demo
from app.core.settings import settings
import logging

logger = logging.getLogger("app")
router = APIRouter()
router.include_router(demo.router)

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
    # Endpoint is protected by ADMIN_API_KEY
        
    # Generate 150 movie items
    items = []
    genres = ["Action", "Sci-Fi", "Drama", "Comedy", "Thriller", "Horror", "Romance", "Documentary"]
    adjectives = ["Dark", "Lost", "Hidden", "Final", "First", "Eternal", "Neon", "Crimson", "Silent", "Iron", "Quantum", "Savage"]
    nouns = ["City", "Knight", "Planet", "Dream", "Star", "Shadow", "Hero", "Mission", "Dawn", "Legacy", "Code", "Echo"]
    
    for i in range(1, 151):
        adj = adjectives[i % len(adjectives)]
        noun = nouns[(i * 3) % len(nouns)]
        suffix = f" Part {1 + (i % 3)}" if i % 4 == 0 else ""
        
        movie_title = f"The {adj} {noun}{suffix}"
        
        items.append(ItemCreate(
            id=f"movie_{i}",
            title=movie_title,
            description=f"A critically acclaimed {genres[i % len(genres)]} film.",
            category=genres[i % len(genres)],
            tags=[f"director_{i%10}", f"year_{2000 + (i%24)}"],
            price=0.0,
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

@router.get("/v1/catalog/daily-sync", dependencies=[Depends(verify_cron_secret)])
@router.post("/v1/catalog/daily-sync", dependencies=[Depends(verify_cron_secret)])
async def daily_sync_tmdb(
    vector_repo: VectorRepository = Depends(get_vector_repo),
    cache_repo: CacheRepository = Depends(get_cache_repo),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    tmdb_service: TMDBService = Depends(get_tmdb_service)
):
    """Daily cron job to fetch popular TMDB movies, clear the DB, and populate."""
    try:
        # 1. Fetch real movies (top 8 pages = ~160 movies)
        items = await tmdb_service.fetch_popular_movies(pages=8)
        
        # 2. Re-create / clear the vector index
        await vector_repo.clear_collection()
        
        # 3. Batch insert new items
        chunk_size = 50
        for i in range(0, len(items), chunk_size):
            chunk = items[i:i+chunk_size]
            texts = [f"{item.title} {item.description} {item.category} {' '.join(item.tags)}" for item in chunk]
            embeddings = await embedding_service.get_embeddings(texts)
            item_models = [Item(**item.model_dump()) for item in chunk]
            await vector_repo.upsert_items(item_models, embeddings)
            
        # 4. Invalidate cache
        await cache_repo.increment_catalog_version()
        
        logger.info(f"Daily TMDB sync completed successfully. Synced {len(items)} items.")
        return {"status": "success", "synced_items": len(items)}
    except Exception as e:
        logger.error(f"Daily sync failed: {e}")
        raise HTTPException(status_code=500, detail="Daily sync failed")

@router.get("/v1/metrics", dependencies=[Depends(verify_api_key)])
async def get_metrics():
    """Basic instance-scoped metrics. Production should rely on structured logging."""
    return {
        "status": "ok", 
        "note": "Instance-scoped metrics. Use structured logs for distributed tracing."
    }
