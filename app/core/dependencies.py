from fastapi import Depends, HTTPException, status
from functools import lru_cache
from app.core.settings import settings
from app.repositories.vector import VectorRepository, QdrantRepository, InMemoryVectorRepository
from app.repositories.cache import CacheRepository, UpstashRedisRepository, InMemoryCache
from app.services.embedding import EmbeddingService, OpenAIEmbeddingService, DemoEmbeddingService
from app.services.recommendation import RecommendationService
from app.services.tmdb import TMDBService
import logging

logger = logging.getLogger("app")

# Singletons for in-memory structures to persist across requests in Demo mode
_in_memory_vector = InMemoryVectorRepository()
_in_memory_cache = InMemoryCache()

@lru_cache()
def get_vector_repo() -> VectorRepository:
    if settings.DEMO_MODE:
        return _in_memory_vector
    return QdrantRepository()

def get_cache_repo() -> CacheRepository:
    if settings.DEMO_MODE:
        return _in_memory_cache
    return UpstashRedisRepository()
    
def get_embedding_service() -> EmbeddingService:
    if settings.DEMO_MODE:
        return DemoEmbeddingService()
    return OpenAIEmbeddingService()

def get_recommendation_service(
    vector_repo: VectorRepository = Depends(get_vector_repo),
    cache_repo: CacheRepository = Depends(get_cache_repo),
    embedding_service: EmbeddingService = Depends(get_embedding_service)
) -> RecommendationService:
    return RecommendationService(vector_repo, cache_repo, embedding_service)

@lru_cache()
def get_tmdb_service() -> TMDBService:
    return TMDBService()

def require_production_dependencies():
    """Raises 503 if we are not in DEMO_MODE but missing critical prod dependencies"""
    if not settings.DEMO_MODE:
        if not settings.QDRANT_URL or not settings.OPENAI_API_KEY or not settings.UPSTASH_REDIS_REST_URL:
            logger.error("Missing production dependencies (QDRANT_URL, OPENAI_API_KEY, UPSTASH_REDIS_REST_URL)")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Production dependencies not configured"
            )
