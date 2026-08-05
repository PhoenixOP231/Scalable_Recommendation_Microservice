import uuid
import hashlib
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels
from app.schemas.item import Item
from app.core.settings import settings
import logging

logger = logging.getLogger("app")

def generate_point_id(item_id: str) -> str:
    """Generate a stable UUIDv5 point ID for Qdrant from the external item_id."""
    return str(uuid.uuid5(uuid.NAMESPACE_OID, item_id))

class VectorRepository(ABC):
    @abstractmethod
    async def upsert_items(self, items: List[Item], embeddings: List[List[float]]) -> None:
        pass
        
    @abstractmethod
    async def search(
        self, 
        query_vector: List[float], 
        limit: int, 
        exclude_item_ids: List[str] = None,
        exclude_categories: List[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        pass
        
    @abstractmethod
    async def get_items_vectors(self, item_ids: List[str]) -> Dict[str, List[float]]:
        pass

    @abstractmethod
    async def get_catalog(self, limit: int = 50) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def clear_collection(self) -> None:
        pass

class QdrantRepository(VectorRepository):
    def __init__(self):
        # Async client with configured timeout
        self.client = AsyncQdrantClient(
            url=settings.QDRANT_URL.strip() if settings.QDRANT_URL else None,
            api_key=settings.QDRANT_API_KEY.strip() if settings.QDRANT_API_KEY else None,
            timeout=settings.QDRANT_TIMEOUT_SECONDS
        )
        self.collection_name = settings.QDRANT_COLLECTION_NAME

    async def _ensure_collection(self) -> None:
        try:
            if not await self.client.collection_exists(self.collection_name):
                from qdrant_client.http.models import VectorParams, Distance
                await self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=settings.EMBEDDING_DIMENSIONS, distance=Distance.COSINE)
                )
        except Exception as e:
            logger.warning(f"Could not check or create collection (it might already exist): {e}")

    async def clear_collection(self) -> None:
        """Deletes and recreates the collection to wipe all points."""
        try:
            if await self.client.collection_exists(self.collection_name):
                await self.client.delete_collection(self.collection_name)
                
            from qdrant_client.http.models import VectorParams, Distance
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=settings.EMBEDDING_DIMENSIONS, distance=Distance.COSINE)
            )
        except Exception as e:
            logger.error(f"Failed to clear collection: {e}")
            raise

    async def upsert_items(self, items: List[Item], embeddings: List[List[float]]) -> None:
        await self._ensure_collection()
        points = []
        for item, embedding in zip(items, embeddings):
            payload = {
                "item_id": item.id,
                "title": item.title,
                "category": item.category,
                "price": item.price,
                "is_active": item.is_active,
                "popularity_score": item.popularity_score,
                "created_at": item.created_at.isoformat(),
                "tags": item.tags,
                "image_url": item.image_url
            }
            points.append(
                qmodels.PointStruct(
                    id=generate_point_id(item.id),
                    vector=embedding,
                    payload=payload
                )
            )
            
        try:
            await self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True
            )
        except Exception as e:
            logger.error(f"Failed to upsert to Qdrant: {e}")
            raise
            
    async def search(
        self, 
        query_vector: List[float], 
        limit: int, 
        exclude_item_ids: List[str] = None,
        exclude_categories: List[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        
        must_conditions = []
        must_not_conditions = []
        
        must_not_conditions = []
            
        if min_price is not None or max_price is not None:
            range_kwargs = {}
            if min_price is not None:
                range_kwargs["gte"] = min_price
            if max_price is not None:
                range_kwargs["lte"] = max_price
                
            must_conditions.append(
                qmodels.FieldCondition(
                    key="price",
                    range=qmodels.Range(**range_kwargs)
                )
            )
            
        filter_query = qmodels.Filter(
            must=must_conditions,
            must_not=must_not_conditions
        )
        
        try:
            search_result = await self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=filter_query,
                limit=limit,
                with_payload=True
            )
            
            results = []
            for hit in search_result.points:
                res = hit.payload.copy()
                res["vector_score"] = hit.score
                results.append(res)
            return results
        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            raise

    async def get_items_vectors(self, item_ids: List[str]) -> Dict[str, List[float]]:
        if not item_ids:
            return {}
            
        point_ids = [generate_point_id(i) for i in item_ids]
        try:
            points = await self.client.retrieve(
                collection_name=self.collection_name,
                ids=point_ids,
                with_vectors=True,
                with_payload=True
            )
            
            res = {}
            for pt in points:
                item_id = pt.payload.get("item_id")
                if item_id and pt.vector:
                    res[item_id] = pt.vector
            return res
        except Exception as e:
            logger.error(f"Qdrant retrieve failed: {e}")
            raise

    async def get_catalog(self, limit: int = 50) -> List[Dict[str, Any]]:
        results, _ = await self.client.scroll(
            collection_name=self.collection_name,
            limit=limit,
            with_payload=True,
            with_vectors=False
        )
        return [
            {
                "id": hit.id,
                "metadata": hit.payload
            }
            for hit in results
        ]

class InMemoryVectorRepository(VectorRepository):
    def __init__(self):
        self.points = {}

    async def clear_collection(self) -> None:
        self.points = {}

    def _cosine_sim(self, v1: List[float], v2: List[float]) -> float:
        import math
        dot = sum(a*b for a,b in zip(v1, v2))
        norm1 = math.sqrt(sum(a*a for a in v1))
        norm2 = math.sqrt(sum(b*b for b in v2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    async def upsert_items(self, items: List[Item], embeddings: List[List[float]]) -> None:
        for item, emb in zip(items, embeddings):
            self.points[item.id] = {
                "item_id": item.id,
                "title": item.title,
                "category": item.category,
                "price": item.price,
                "is_active": item.is_active,
                "popularity_score": item.popularity_score,
                "created_at": item.created_at.isoformat(),
                "tags": item.tags,
                "image_url": item.image_url,
                "vector": emb
            }

    async def search(
        self, 
        query_vector: List[float], 
        limit: int, 
        exclude_item_ids: List[str] = None,
        exclude_categories: List[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        
        exclude_item_ids = set(exclude_item_ids or [])
        exclude_categories = set(exclude_categories or [])
        
        results = []
        for item_id, data in self.points.items():
            if not data["is_active"]:
                continue
            if item_id in exclude_item_ids:
                continue
            if data["category"] in exclude_categories:
                continue
            if min_price is not None and data["price"] < min_price:
                continue
            if max_price is not None and data["price"] > max_price:
                continue
                
            score = self._cosine_sim(query_vector, data["vector"])
            res = data.copy()
            del res["vector"]
            res["vector_score"] = score
            results.append(res)
            
        results.sort(key=lambda x: x["vector_score"], reverse=True)
        return results[:limit]

    async def get_items_vectors(self, item_ids: List[str]) -> Dict[str, List[float]]:
        res = {}
        for i in item_ids:
            if i in self.points:
                res[i] = self.points[i]["vector"]
        return res

    async def get_catalog(self, limit: int = 50) -> List[Dict[str, Any]]:
        results = []
        for p_id, data in list(self.points.items())[:limit]:
            results.append({
                "id": generate_point_id(p_id),
                "metadata": data
            })
        return results
