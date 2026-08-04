import pytest
from app.repositories.vector import generate_point_id
from app.services.embedding import DemoEmbeddingService

def test_uuid_mapping():
    # UUIDv5 should be deterministic for the same input string
    id1 = generate_point_id("item_123")
    id2 = generate_point_id("item_123")
    id3 = generate_point_id("item_456")
    
    assert id1 == id2
    assert id1 != id3
    # Check it's a valid uuid format
    import uuid
    assert uuid.UUID(id1).version == 5

@pytest.mark.asyncio
async def test_demo_embeddings_deterministic():
    service = DemoEmbeddingService()
    
    emb1 = await service.get_embeddings(["hello world"])
    emb2 = await service.get_embeddings(["hello world"])
    emb3 = await service.get_embeddings(["different text"])
    
    assert len(emb1[0]) == service.dimensions
    assert emb1[0] == emb2[0]
    assert emb1[0] != emb3[0]
