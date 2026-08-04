import json
import httpx
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod
from app.core.settings import settings
import logging

logger = logging.getLogger("app")

class CacheRepository(ABC):
    @abstractmethod
    async def get_recommendation(self, cache_key: str) -> Optional[Dict[str, Any]]:
        pass
        
    @abstractmethod
    async def set_recommendation(self, cache_key: str, data: Dict[str, Any], ttl: int) -> None:
        pass
        
    @abstractmethod
    async def get_user_interactions(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        pass
        
    @abstractmethod
    async def add_user_interaction(self, user_id: str, interaction: Dict[str, Any], max_history: int = 100) -> int:
        """Returns the new profile version"""
        pass
        
    @abstractmethod
    async def get_catalog_version(self) -> int:
        pass
        
    @abstractmethod
    async def increment_catalog_version(self) -> int:
        pass

class UpstashRedisRepository(CacheRepository):
    def __init__(self):
        self.url = settings.UPSTASH_REDIS_REST_URL.rstrip('/')
        self.token = settings.UPSTASH_REDIS_REST_TOKEN
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.timeout = settings.REDIS_TIMEOUT_SECONDS
        
    async def _request(self, command: str, *args) -> Any:
        # Upstash REST API takes POST requests with JSON payload: ["CMD", "arg1", "arg2"]
        payload = [command] + list(args)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(self.url, headers=self.headers, json=payload)
                response.raise_for_status()
                data = response.json()
                if "error" in data:
                    raise Exception(data["error"])
                return data.get("result")
            except Exception as e:
                logger.error(f"Redis request failed: {command} - {e}")
                raise

    async def get_recommendation(self, cache_key: str) -> Optional[Dict[str, Any]]:
        result = await self._request("GET", cache_key)
        if result:
            return json.loads(result)
        return None

    async def set_recommendation(self, cache_key: str, data: Dict[str, Any], ttl: int) -> None:
        await self._request("SET", cache_key, json.dumps(data), "EX", str(ttl))

    async def get_user_interactions(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        key = f"user:{user_id}:interactions"
        # Using Redis List. LRange returns a list of strings
        result = await self._request("LRANGE", key, "0", str(limit - 1))
        if result:
            return [json.loads(item) for item in result]
        return []

    async def add_user_interaction(self, user_id: str, interaction: Dict[str, Any], max_history: int = 100) -> int:
        key = f"user:{user_id}:interactions"
        val = json.dumps(interaction)
        
        # LPUSH, LTRIM, INCR version. We'll do it sequentially rather than a strict transaction
        # for Upstash REST simplicity. 
        await self._request("LPUSH", key, val)
        await self._request("LTRIM", key, "0", str(max_history - 1))
        
        version_key = f"user:{user_id}:version"
        new_version = await self._request("INCR", version_key)
        return int(new_version)

    async def get_catalog_version(self) -> int:
        result = await self._request("GET", "catalog:version")
        return int(result) if result else 0

    async def increment_catalog_version(self) -> int:
        result = await self._request("INCR", "catalog:version")
        return int(result)


class InMemoryCache(CacheRepository):
    def __init__(self):
        self._cache = {}
        self._interactions = {}
        self._user_versions = {}
        self._catalog_version = 0

    async def get_recommendation(self, cache_key: str) -> Optional[Dict[str, Any]]:
        return self._cache.get(cache_key)

    async def set_recommendation(self, cache_key: str, data: Dict[str, Any], ttl: int) -> None:
        # Ignoring TTL for in-memory simple demo cache
        self._cache[cache_key] = data

    async def get_user_interactions(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        return self._interactions.get(user_id, [])[:limit]

    async def add_user_interaction(self, user_id: str, interaction: Dict[str, Any], max_history: int = 100) -> int:
        if user_id not in self._interactions:
            self._interactions[user_id] = []
        self._interactions[user_id].insert(0, interaction)
        self._interactions[user_id] = self._interactions[user_id][:max_history]
        
        self._user_versions[user_id] = self._user_versions.get(user_id, 0) + 1
        return self._user_versions[user_id]

    async def get_catalog_version(self) -> int:
        return self._catalog_version

    async def increment_catalog_version(self) -> int:
        self._catalog_version += 1
        return self._catalog_version
