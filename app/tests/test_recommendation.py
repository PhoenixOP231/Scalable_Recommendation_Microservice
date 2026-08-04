import pytest
from datetime import datetime, timezone
from app.services.recommendation import RecommendationService
from app.repositories.vector import InMemoryVectorRepository
from app.repositories.cache import InMemoryCache
from app.schemas.recommendation import RecommendationRequest, Filters

@pytest.fixture
def mock_services():
    vector_repo = InMemoryVectorRepository()
    cache_repo = InMemoryCache()
    rec_service = RecommendationService(vector_repo, cache_repo)
    return vector_repo, cache_repo, rec_service

@pytest.mark.asyncio
async def test_recommendation_fallback(mock_services):
    vector_repo, cache_repo, rec_service = mock_services
    
    # Add dummy item
    from app.schemas.item import Item
    
    item = Item(
        id="item_1",
        title="Test item",
        description="desc",
        category="cat1",
        tags=["tag1"],
        price=10.0,
        popularity_score=80.0,
        created_at=datetime.now(timezone.utc),
        is_active=True
    )
    
    await vector_repo.upsert_items([item], [[1.0] + [0.0]*1535])
    
    req = RecommendationRequest(
        user_id="new_user",
        limit=10,
        seed_item_ids=[],
        excluded_categories=[],
        filters=Filters(min_price=0, max_price=100),
        diversity=0.0,
        cache_ttl_seconds=0
    )
    
    response = await rec_service.get_recommendations(req)
    assert len(response.recommendations) == 1
    assert response.recommendations[0].item_id == "item_1"
    # Fallback reason
    assert response.recommendations[0].scores.reason == "Popular and fresh item"

@pytest.mark.asyncio
async def test_cache_versioning(mock_services):
    vector_repo, cache_repo, rec_service = mock_services
    
    cat_ver_before = await cache_repo.get_catalog_version()
    assert cat_ver_before == 0
    
    await cache_repo.increment_catalog_version()
    cat_ver_after = await cache_repo.get_catalog_version()
    assert cat_ver_after == 1
    
    user_ver_1 = await cache_repo.add_user_interaction("u1", {"item_id": "i1"})
    assert user_ver_1 == 1
    
    user_ver_2 = await cache_repo.add_user_interaction("u1", {"item_id": "i2"})
    assert user_ver_2 == 2
